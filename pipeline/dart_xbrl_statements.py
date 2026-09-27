"""Parse a served `fnlttXbrl.xml` ZIP for the four gate accounts. CANDIDATE_UNCONFIRMED.

WHY THIS MODULE'S OUTPUT CARRIES `endpointConfidence: CANDIDATE_UNCONFIRMED`,
THE SAME TIER `alotMatter.json` CARRIED BEFORE ITS OWN LIVE PROBE. The live
probe this repair ran (see `dart_xbrl_originals.py`'s docstring) confirmed
`fnlttXbrl.xml` serves a real ZIP for 6 of 8 sampled 2015 Q3 filings -- but it
recorded only the outer envelope (byte 0-1 == `PK`, total size), never the
ZIP's CONTENTS. `DART_API_KEY` is not available in this development
environment and `opendart.fss.or.kr` is blocked from this sandbox's egress
(the same block this repository's other DART modules already record), so
this module's account-extraction logic has NEVER been run against a real
served package in this session. Its shape is built from GENERAL, PUBLIC
XBRL/K-IFRS conventions (a ZIP holding an XBRL instance document; facts
tagged by taxonomy element, referencing a `<context>` for their period, a
quarterly filing's flow concept typically carrying BOTH a single-quarter and
a year-to-date duration context, mirroring exactly what the JSON statement
endpoint already exposes as `thstrm_amount`/`thstrm_add_amount`) and from
element identifiers this repository has ALREADY confirmed live via that JSON
endpoint's own `account_id` field (`dart_canonical_accounts.ELEMENT_RULES`)
-- never a fuzzy label guess. That is corroboration, not confirmation, and
every record this module builds says so. `scripts/collect_dart_xbrl_
originals.py --dump-entries` is what a live run against real ZIPs would use
to promote this to CONFIRMED_LIVE, the same two-step this repository's other
DART endpoints have already gone through.

MATCHING IS BY EXACT LOCAL NAME, NAMESPACE-AGNOSTIC, NEVER BY SUBSTRING.
`TARGET_LOCAL_NAMES` is derived from `dart_canonical_accounts.ELEMENT_RULES`
by stripping each element id's known taxonomy prefix (`ifrs-full_`, `ifrs_`)
-- the same equivalence that module already treats as one account, applied
here to the tag's local part after an XML parser splits `{namespace}Local`.
`ProfitLossAttributableToOwnersOfParent` does not equal `ProfitLoss`;
`CurrentAssets` does not equal `Assets`; a component or subtotal element is
never matched.

THE CONTEXT WINDOW DECIDES THE COLUMN, THE SAME RULE `dart_derive.
cumulative_amount` ALREADY USES, NEVER A SECOND ONE. A balance-sheet account
(자산총계/부채총계) needs an INSTANT context equal to the filing's own period
end. A flow account (당기순이익/영업활동현금흐름) needs a DURATION context
running from the fiscal year's own start to that same period end -- the
cumulative reading, not the standalone quarter -- and is stored under
exactly the amount-field name `dart_derive.cumulative_amount` would read for
that statement (`thstrm_add_amount` for net income's CIS/IS branch,
`thstrm_amount` for cash flow's single-column branch, per this repository's
own measured column semantics). Any other duration window a same-named
concept may carry (a standalone quarter, a prior comparative) is never
consulted.

WHAT THIS MODULE DOES NOT ATTEMPT. DART's JSON statement endpoint records
`sj_div` (which financial statement a row belongs to) per row; nothing
inspected here shows an equivalent, directly-read "which statement" marker
on an XBRL fact, so `statement` is set to the value `dart_derive` itself
needs to read the right column (CIS/CF), never inferred from the element's
usual accounting role.

NEVER SYNTHESISED. A context with no matching window, a document with no
parseable XML entry, or more than one candidate surviving the window filter
with disagreeing values, all leave the account unavailable -- `NOT_FOUND` or
`AMBIGUOUS`, never a picked value.

DIMENSIONAL QUALIFIERS ARE AN ALLOWLIST, NEVER A BLOCKLIST -- MEASURED FROM A
REAL LIVE PROBE (GitHub Actions run 36304452901, `raw-probe-2015`, 18 served
2015 Q1/H1/Q3 packages, real `DART_API_KEY`, `--dump-entries`). The first cut
of this module read only a context's `instant`/`startDate`/`endDate`, so any
`<scenario>`/`<segment>` dimensional qualifier on a context was invisible --
and real DART filings for this era's smaller/general-corp filers tag MULTIPLE
contexts with the exact same literal dates, distinguished only by such a
qualifier, so every one of them "matched the window" and the account read
AMBIGUOUS: 15 of 18 served filings, all four accounts, every one of them the
same 5 issuers on every stage (all-or-nothing per issuer, never per-stage --
a filer-level XBRL-authoring-style fact, not a per-account or per-quarter
one). The three axis families actually observed:
  - `ifrs:ConsolidatedAndSeparateFinancialStatementsAxis` (`ConsolidatedMember`
    / `SeparateMember`) -- the SAME Consolidated-vs-Separate distinction
    `dart_derive`'s own PIT-fundamentals invariants already resolve for the
    JSON statement endpoint ("Consolidated is preferred ... which answered is
    RECORDED"), reused here rather than re-decided.
  - `dart-gcd:PeriodAxis` (`PeriodCoveredbyLastFiscalYearMember` /
    `PeriodCoveredbyTheYearBeforeLastFiscalYearMember`) -- every member
    actually observed names a PRIOR reporting period; DART's own general-corp
    comparative-disclosure template reuses one literal date range as a
    boilerplate label across a comparative table, so the qualifier's own name
    is the only real signal of which period a fact belongs to, and neither
    observed member ever named the current period.
  - `ifrs:ComponentsOfEquityAxis` -- a statement-of-changes-in-equity
    component row (e.g. `EquityAttributableToOwnersOfParentMember`), exactly
    the SCE-component-row shape this repository's own `dart_canonical_
    accounts` already refuses for the JSON-row path, reused here rather than
    re-decided a second way.
A context is an ELIGIBLE candidate only if its scenario/segment content is
EMPTY, or is EXACTLY one `ConsolidatedAndSeparateFinancialStatementsAxis`
member -- an allowlist of the two shapes this evidence and this repository's
own prior rules can account for. Any other qualifier (the two above, or any
future one this module has never evaluated) is excluded, and that exclusion
is its own status (`AXIS_EXCLUDED_ONLY`) rather than collapsing into
`NOT_FOUND` -- "the filing states this account only under a qualifier we do
not admit" and "the filing never states this account at all" are different
facts. Among eligible survivors, an unqualified fact is preferred first (the
filer never dual-reported this account under the axis at all); only when
every eligible survivor carries the Consolidated/Separate axis is Consolidated
preferred over Separate, and the winning basis is recorded per account
(`statementBasis`) -- never inferred for the whole filing, since different
accounts in the same filing may resolve under different bases. This can only
ever REMOVE a candidate from ambiguity, never invent one: a residual
disagreement inside the preferred pool still reports `AMBIGUOUS`, exactly as
before this evidence was read.
"""
from __future__ import annotations

import io
import xml.etree.ElementTree as ET
import zipfile

from . import dart_canonical_accounts as C
from . import dart_fundamentals as DF

CONTRACT = "DART_XBRL_CANDIDATE_STATEMENTS_V1"
ENDPOINT_CONFIDENCE = "CANDIDATE_UNCONFIRMED"

# Local part of a QName only -- `dart_canonical_accounts.ELEMENT_RULES`'s
# ids already record which prefixes are equivalent for each account; this
# strips them once rather than re-deciding equivalence a second way.
_KNOWN_PREFIXES = ("ifrs-full_", "ifrs_")

INSTANT_ACCOUNTS = ("자산총계", "부채총계")
# (amountField, statement) `dart_derive`'s own column rule expects for the
# CUMULATIVE (year-to-date) reading of each flow account.
DURATION_ACCOUNTS = {"당기순이익": ("thstrm_add_amount", "CIS"),
                     "영업활동현금흐름": ("thstrm_amount", "CF")}


def _local_names(account: str) -> frozenset[str]:
    names = set()
    for element_id in C.ELEMENT_RULES[account]["elementIds"]:
        for prefix in _KNOWN_PREFIXES:
            if element_id.startswith(prefix):
                names.add(element_id[len(prefix):])
                break
    return frozenset(names)


TARGET_LOCAL_NAMES: dict[str, frozenset[str]] = {a: _local_names(a) for a in C.ELEMENT_RULES}
ALL_TARGET_LOCAL_NAMES = frozenset().union(*TARGET_LOCAL_NAMES.values())

NOT_FOUND, AMBIGUOUS, RESOLVED = "NOT_FOUND", "AMBIGUOUS", "RESOLVED"
NO_PARSEABLE_XML_ENTRY = "NO_PARSEABLE_XML_ENTRY"
# A context whose ONLY eligible candidates were excluded by an unrecognised
# dimensional qualifier -- a different fact from NOT_FOUND (no matching
# window at all). See the module docstring's "DIMENSIONAL QUALIFIERS" section.
AXIS_EXCLUDED_ONLY = "AXIS_EXCLUDED_ONLY"

# The one dimensional qualifier this module admits, because this repository
# already resolves it for the JSON statement endpoint (prefer Consolidated).
# Local names only, matching this module's own namespace-agnostic discipline.
CONSOLIDATED_SEPARATE_AXIS = "ConsolidatedAndSeparateFinancialStatementsAxis"
CONSOLIDATED_MEMBER = "ConsolidatedMember"
SEPARATE_MEMBER = "SeparateMember"


def _qname(tag: str) -> tuple[str | None, str]:
    if tag.startswith("{"):
        ns, local = tag[1:].split("}", 1)
        return ns, local
    return None, tag


def unzip_entries(raw: bytes) -> tuple[list[tuple[str, bytes]], str]:
    """(entries, error). Every entry kept; a caller decides which parse."""
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            return [(name, archive.read(name)) for name in archive.namelist()], ""
    except zipfile.BadZipFile as exc:
        return [], f"{type(exc).__name__}: {exc}"


def _parse_xml_entries(entries: list[tuple[str, bytes]]) -> list[ET.Element]:
    roots = []
    for _, data in entries:
        try:
            roots.append(ET.fromstring(data))
        except ET.ParseError:
            continue
    return roots


def _dimensions(context_element: ET.Element) -> tuple[tuple[str, str], ...]:
    """Every `(axisLocalName, memberLocalName)` an XBRL context's own
    `<scenario>`/`<segment>` carries, from `xbrldi:explicitMember`'s
    `dimension` attribute and its text content -- both by local name only,
    namespace-agnostic, matching this module's own element-matching rule.
    A `typedMember` (no known real instance) or a member whose `dimension`
    attribute is missing is recorded with an empty axis name rather than
    dropped silently, so it still fails the eligibility allowlist below
    instead of being read as if it were unqualified.
    """
    dims = []
    for element in context_element.iter():
        _, local = _qname(element.tag)
        if local not in ("scenario", "segment"):
            continue
        for child in element.iter():
            _, child_local = _qname(child.tag)
            if child_local == "explicitMember":
                # `dimension`/the member text are literal QName strings
                # (`prefix:LocalName`), never Clark-notation -- an XML
                # attribute value and element text are not tag names, so
                # ElementTree never expands them against the namespace map.
                axis = (child.get("dimension") or "").split(":")[-1]
                member = (child.text or "").strip().split(":")[-1]
                dims.append((axis, member))
            elif child_local == "typedMember":
                dims.append(("", ""))
    return tuple(sorted(dims))


def _contexts(root: ET.Element) -> dict[str, dict]:
    """contextId -> {instant, startDate, endDate, dims}, by local name only."""
    out: dict[str, dict] = {}
    for element in root.iter():
        _, local = _qname(element.tag)
        if local != "context":
            continue
        context_id = element.get("id")
        if context_id is None:
            continue
        period = {"instant": None, "startDate": None, "endDate": None}
        for child in element.iter():
            _, child_local = _qname(child.tag)
            if child_local in period and child.text:
                period[child_local] = child.text.strip()
        period["dims"] = _dimensions(element)
        out[context_id] = period
    return out


def _is_eligible_axis_shape(dims: tuple[tuple[str, str], ...]) -> bool:
    """No dimensional qualifier at all, or exactly the Consolidated/Separate
    axis this repository already knows how to prefer -- see the module
    docstring. Anything else (an unrecognised axis, more than one axis, a
    typedMember) is excluded rather than guessed at.
    """
    if not dims:
        return True
    return dims == ((CONSOLIDATED_SEPARATE_AXIS, CONSOLIDATED_MEMBER),) or \
        dims == ((CONSOLIDATED_SEPARATE_AXIS, SEPARATE_MEMBER),)


def extract_facts(root: ET.Element) -> list[dict]:
    """Every fact whose local name is a target, with its raw context/unit/value."""
    facts = []
    for element in root.iter():
        ns, local = _qname(element.tag)
        if local not in ALL_TARGET_LOCAL_NAMES:
            continue
        context_ref = element.get("contextRef")
        if context_ref is None or element.text is None:
            continue
        facts.append({"localName": local, "namespace": ns, "contextRef": context_ref,
                      "unitRef": element.get("unitRef"), "decimals": element.get("decimals"),
                      "rawText": element.text.strip()})
    return facts


def _matches_instant(period: dict, period_end: str) -> bool:
    return period["instant"] == period_end


def _matches_cumulative_duration(period: dict, fiscal_year_start: str, period_end: str) -> bool:
    return period["startDate"] == fiscal_year_start and period["endDate"] == period_end


def _window_matched_candidates(entries: list[tuple[str, bytes]], account: str, *,
                               fiscal_year_start: str, period_end: str) -> list[dict] | None:
    """Every fact matching `account`'s target element AND its required
    window, across every parseable XML entry. `None` (not `[]`) when no XML
    entry parsed at all -- a different fact from a document that parsed but
    named no such fact.
    """
    local_names = TARGET_LOCAL_NAMES[account]
    is_instant = account in INSTANT_ACCOUNTS
    roots = _parse_xml_entries(entries)
    if not roots:
        return None
    candidates = []
    for root in roots:
        contexts = _contexts(root)
        for fact in extract_facts(root):
            if fact["localName"] not in local_names:
                continue
            period = contexts.get(fact["contextRef"])
            if period is None:
                continue
            matched = (_matches_instant(period, period_end) if is_instant
                      else _matches_cumulative_duration(period, fiscal_year_start, period_end))
            if matched:
                candidates.append({**fact, "period": period})
    return candidates


def describe_candidates(entries: list[tuple[str, bytes]], account: str, *,
                        fiscal_year_start: str, period_end: str) -> list[dict]:
    """Every window-matched candidate for `account`, contextRef/dims/value/
    eligibility only -- for a human reviewing why an account resolved,
    stayed ambiguous, or was axis-excluded. Never used to build a record;
    `resolve_account` is the only function that decides a value.
    """
    candidates = _window_matched_candidates(entries, account, fiscal_year_start=fiscal_year_start,
                                            period_end=period_end) or []
    return [{"contextRef": c["contextRef"], "dims": list(c["period"]["dims"]), "rawText": c["rawText"],
             "eligibleAxisShape": _is_eligible_axis_shape(c["period"]["dims"])} for c in candidates]


def resolve_account(entries: list[tuple[str, bytes]], account: str, *,
                    fiscal_year_start: str, period_end: str) -> tuple[str | None, dict]:
    """(rawText, provenance) for one account across every parseable XML entry.

    An instant account needs its context's `instant` equal to `period_end`.
    A flow account needs a DURATION context running exactly from
    `fiscal_year_start` to `period_end` -- the cumulative reading -- never a
    standalone-quarter window a same-named concept may also carry.
    """
    candidates = _window_matched_candidates(entries, account, fiscal_year_start=fiscal_year_start,
                                            period_end=period_end)
    if candidates is None:
        return None, {"status": NO_PARSEABLE_XML_ENTRY, "candidates": 0}
    if not candidates:
        return None, {"status": NOT_FOUND, "candidates": 0}
    eligible = [c for c in candidates if _is_eligible_axis_shape(c["period"]["dims"])]
    if not eligible:
        return None, {"status": AXIS_EXCLUDED_ONLY, "candidates": len(candidates), "eligibleCandidates": 0}
    unqualified = [c for c in eligible if not c["period"]["dims"]]
    consolidated = [c for c in eligible
                   if c["period"]["dims"] == ((CONSOLIDATED_SEPARATE_AXIS, CONSOLIDATED_MEMBER),)]
    if unqualified:
        pool, basis = unqualified, None
    elif consolidated:
        pool, basis = consolidated, DF.FS_CONSOLIDATED
    else:
        pool, basis = eligible, DF.FS_SEPARATE
    distinct_values = {c["rawText"] for c in pool}
    if len(distinct_values) > 1:
        return None, {"status": AMBIGUOUS, "candidates": len(candidates), "eligibleCandidates": len(eligible)}
    fact = pool[0]
    return fact["rawText"], {"status": RESOLVED, "candidates": len(candidates),
                             "eligibleCandidates": len(eligible),
                             "localName": fact["localName"], "contextRef": fact["contextRef"],
                             "unitRef": fact["unitRef"], "decimals": fact["decimals"],
                             "statementBasis": basis}


def canonical_record_from_xbrl(*, ticker: str, stock_code: str, corp_code: str,
                               fiscal_year: int, report_code: str, entries: list[tuple[str, bytes]],
                               original_receipt_no: str, original_receipt_date: str,
                               zip_sha256: str, collected_at: str) -> tuple[dict | None, dict]:
    """One `DART_RAW_FILINGS_V1`-shaped candidate record from a served original ZIP.

    Every account carries `endpointConfidence: CANDIDATE_UNCONFIRMED`; the
    record's own envelope fields (id, availableFrom, receiptNos, source)
    match `dart_fundamentals.build_record`'s shape exactly, so `dart_derive`/
    `accounting_quality`/`alpha_opportunity_features` read it unchanged.
    """
    period_end = DF.period_end(fiscal_year, report_code)
    fiscal_year_start = f"{int(fiscal_year):04d}-01-01"
    accounts: dict[str, dict] = {}
    provenance: dict[str, dict] = {}
    for account in INSTANT_ACCOUNTS:
        value, how = resolve_account(entries, account, fiscal_year_start=fiscal_year_start,
                                     period_end=period_end)
        provenance[account] = how
        if value is not None and DF.parse_amount(value) is not None:
            accounts[account] = {"amounts": {"thstrm_amount": DF.parse_amount(value)},
                                 "accountId": how["localName"], "statement": "BS", "label": None}
    for account, (field, statement) in DURATION_ACCOUNTS.items():
        value, how = resolve_account(entries, account, fiscal_year_start=fiscal_year_start,
                                     period_end=period_end)
        provenance[account] = how
        if value is not None and DF.parse_amount(value) is not None:
            accounts[account] = {"amounts": {field: DF.parse_amount(value)},
                                 "accountId": how["localName"], "statement": statement, "label": None}
    if not accounts:
        return None, provenance
    return {
        "id": DF.record_id(ticker, fiscal_year, report_code),
        "ticker": ticker, "stockCode": stock_code, "corpCode": corp_code,
        "fiscalYear": int(fiscal_year), "reportCode": report_code,
        "reportName": DF.REPORT_CODES.get(report_code, report_code),
        "availableFrom": original_receipt_date,
        "receiptNos": [original_receipt_no],
        # Not asserted at the filing envelope level: each account resolves
        # independently and records its OWN `statementBasis` in `provenance`
        # (CFS/OFS/unqualified) -- a single filing-level fsDiv would assume
        # every account agreed, which nothing here has established.
        "fsDiv": None,
        "currency": "KRW",
        "source": "DART:fnlttXbrl.xml:ORIGINAL",
        "collectedAt": collected_at,
        "accounts": accounts, "accountsFound": len(accounts), "accountsWanted": len(DURATION_ACCOUNTS) + len(INSTANT_ACCOUNTS),
        "canonicalization": {"contract": CONTRACT, "endpointConfidence": ENDPOINT_CONFIDENCE,
                             "zipSha256": zip_sha256, "accounts": provenance},
    }, provenance
