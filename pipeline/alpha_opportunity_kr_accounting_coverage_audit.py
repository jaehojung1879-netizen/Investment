"""Why each KR accounting feature is missing, per filing and per name-date.

THIS IS A DATA-FOUNDATION AUDIT, NOT A STUDY. It reads filing metadata
(fiscal year, report code, receipt date, CFS/OFS, which accounts a stored
filing carries) and computes nothing about a price after a signal date: no
label, return, IC or model output exists anywhere in this module, and the
report it feeds carries none.

THE FEATURE PATH IS CALLED, NEVER RE-IMPLEMENTED. Whether a field is present
on a name-date is decided by `alpha_opportunity_features.accounting_at` itself
-- the exact sealed function the v4 harness's coverage gate reads. This module
only EXPLAINS an absence by walking the same chain `accounting_quality.
derive_kr_fields` and `dart_derive.trailing_twelve_months` walk, and it raises
`AUDIT_DISAGREES_WITH_FEATURE_PATH` if its own walk ever says "derivable"
where the sealed path produced nothing, or the reverse. A second opinion that
can drift from the thing it audits would be a second definition of coverage.

WHAT THE STORE CAN AND CANNOT SAY. `dart_fundamentals.build_record` keeps only
the statement rows whose label exactly matched `WANTED_ACCOUNTS`, so a filing
whose net income DART served under another label carries no trace of that
row. "The account is not in the stored record" is therefore the most this
audit can establish from the sealed store; whether DART supplied the account
under a different label is answered only by re-reading DART's raw rows
(`pipeline.dart_raw_statements`). The reason codes say exactly that and no
more.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from . import accounting_quality as AQ
from . import alpha_opportunity_features as AF
from . import dart_derive as DD
from . import dart_fundamentals as DF

CONTRACT = "KR_ACCOUNTING_COVERAGE_AUDIT_V1"
FEATURES = ("ocfToNetIncomePct", "assetGrowthPct", "debtGrowthPct")
NET_INCOME, OCF = "당기순이익", "영업활동현금흐름"
ASSETS, LIABILITIES = "자산총계", "부채총계"
LEVEL_ACCOUNT = {"assetGrowthPct": ASSETS, "debtGrowthPct": LIABILITIES}
ANNUAL = DD.ANNUAL
STAGE_ORDER = {"11013": 1, "11012": 2, "11014": 3, "11011": 4}
INCOME_STATEMENTS = ("IS", "CIS")

# Every reason code, frozen here so a report can only ever contain one of them.
TICKER_NOT_IN_DART_COLLECTION = "TICKER_NOT_IN_DART_COLLECTION"
NO_FILING_VISIBLE_YET = "NO_FILING_VISIBLE_YET"
FILING_REJECTED_RECEIPT_MISMATCH = "FILING_REJECTED_RECEIPT_MISMATCH"
CURRENT_ACCOUNT_MISSING = "CURRENT_ACCOUNT_MISSING"
PRIOR_BEFORE_DART_SERVICE = "PRIOR_FILING_BEFORE_DART_SERVICE_START"
PRIOR_2015_QUARTERLY_NOT_SERVED = "PRIOR_FILING_2015_QUARTERLY_RECORDED_ABSENT"
PRIOR_RECORDED_ABSENT = "PRIOR_FILING_RECORDED_ABSENT_BY_DART"
PRIOR_NOT_COLLECTED = "PRIOR_FILING_NOT_COLLECTED"
PRIOR_NOT_VISIBLE = "PRIOR_FILING_NOT_VISIBLE_AT_AS_OF"
PRIOR_ACCOUNT_MISSING = "PRIOR_ACCOUNT_MISSING"
PRIOR_LEVEL_NONPOSITIVE = "PRIOR_LEVEL_NONPOSITIVE"
NET_INCOME_ZERO = "NET_INCOME_ZERO"
# For a name-date with no stored filing at all, what the CALENDAR alone would
# still block: the filing a timely filer would have had visible (latest by
# statutory deadline), or a prior it needs, predates DART's statement service
# or is a fiscal-2015 quarterly. An ASSUMPTION (on-time filing), used only to
# bound what collection could recover, never to decide availability.
CALENDAR_BEFORE_DART_SERVICE = "CALENDAR_REQUIRES_FILING_BEFORE_DART_SERVICE_START"
CALENDAR_2015_QUARTERLY = "CALENDAR_REQUIRES_2015_QUARTERLY"
REASON_CODES = (
    TICKER_NOT_IN_DART_COLLECTION, NO_FILING_VISIBLE_YET, FILING_REJECTED_RECEIPT_MISMATCH,
    CURRENT_ACCOUNT_MISSING, PRIOR_BEFORE_DART_SERVICE, PRIOR_2015_QUARTERLY_NOT_SERVED,
    PRIOR_RECORDED_ABSENT, PRIOR_NOT_COLLECTED, PRIOR_NOT_VISIBLE, PRIOR_ACCOUNT_MISSING,
    PRIOR_LEVEL_NONPOSITIVE, NET_INCOME_ZERO, CALENDAR_BEFORE_DART_SERVICE,
    CALENDAR_2015_QUARTERLY,
)

# Which decision class each reason code belongs to. A reason code is a fact
# about the store; the class is what can be done about it.
DATA_COLLECTION_GAP_REPAIRABLE = "DATA_COLLECTION_GAP_REPAIRABLE"
PARSER_OR_DERIVATION_DEFECT_REPAIRABLE = "PARSER_OR_DERIVATION_DEFECT_REPAIRABLE"
PRIMARY_SOURCE_DOES_NOT_SUPPLY_REQUIRED_HISTORY = "PRIMARY_SOURCE_DOES_NOT_SUPPLY_REQUIRED_HISTORY"
SEMANTICALLY_NOT_DERIVABLE = "SEMANTICALLY_NOT_DERIVABLE"
REQUIRES_EXTERNAL_DATA_SOURCE = "REQUIRES_EXTERNAL_DATA_SOURCE"
UNRESOLVED = "UNRESOLVED"
DECISION_CLASSES = (
    DATA_COLLECTION_GAP_REPAIRABLE, PARSER_OR_DERIVATION_DEFECT_REPAIRABLE,
    PRIMARY_SOURCE_DOES_NOT_SUPPLY_REQUIRED_HISTORY, SEMANTICALLY_NOT_DERIVABLE,
    REQUIRES_EXTERNAL_DATA_SOURCE, UNRESOLVED,
)


def absence_index(absent: dict) -> dict[tuple[str, int, str], dict]:
    """`absent.json` keyed the way the audit asks, ticker x fiscal year x code."""
    out = {}
    for row in (absent or {}).values():
        if row.get("ticker") and row.get("fiscalYear") is not None and row.get("reportCode"):
            out[(str(row["ticker"]), int(row["fiscalYear"]), str(row["reportCode"]))] = row
    return out


def statutory_current_filing(as_of: str) -> tuple[int, str]:
    """The latest filing whose statutory deadline is strictly before `as_of`."""
    year = int(as_of[:4])
    due = [(y, c) for y in (year - 2, year - 1, year) for c in STAGE_ORDER
           if DF.filing_deadline(y, c) < as_of]
    return max(due, key=lambda k: (k[0], STAGE_ORDER[k[1]]))


def calendar_blockers(as_of: str, feature: str) -> list[str]:
    """What an on-time filer's calendar alone blocks for `feature` on `as_of`."""
    year, code = statutory_current_filing(as_of)
    needs = [(year, code)]
    if feature in LEVEL_ACCOUNT:
        needs.append((year - 1, code))
    elif code != ANNUAL:
        needs += [(year - 1, ANNUAL), (year - 1, code)]
    out = set()
    for y, c in needs:
        if y < DF.FIRST_SERVED_YEAR:
            out.add(CALENDAR_BEFORE_DART_SERVICE)
        elif y == DF.FIRST_SERVED_YEAR and c != ANNUAL:
            out.add(CALENDAR_2015_QUARTERLY)
    return [f"CALENDAR:{r}" for r in sorted(out)]


def _missing_filing_reason(ticker, year, code, all_index, absences) -> str:
    """Why the filing (year, code) is not in the visible index."""
    if year < DF.FIRST_SERVED_YEAR:
        return PRIOR_BEFORE_DART_SERVICE
    if (year, code) in all_index:
        return PRIOR_NOT_VISIBLE
    if (ticker, year, code) in absences:
        if year == DF.FIRST_SERVED_YEAR and code != ANNUAL:
            return PRIOR_2015_QUARTERLY_NOT_SERVED
        return PRIOR_RECORDED_ABSENT
    return PRIOR_NOT_COLLECTED


def _flow_chain(index, all_index, absences, ticker, year, code, account) -> list[str]:
    """Blockers on `dart_derive.trailing_twelve_months` for one flow account."""
    current = index[(year, code)]
    if DD.cumulative_amount(current, account) is None:
        return [f"{account}:CURRENT:{CURRENT_ACCOUNT_MISSING}"]
    if code == ANNUAL:
        return []
    blockers = []
    for role, key in (("PRIOR_ANNUAL", (year - 1, ANNUAL)), ("PRIOR_SAME_STAGE", (year - 1, code))):
        filing = index.get(key)
        if filing is None:
            blockers.append(f"{account}:{role}:"
                            + _missing_filing_reason(ticker, key[0], key[1], all_index, absences))
        elif DD.cumulative_amount(filing, account) is None:
            blockers.append(f"{account}:{role}:{PRIOR_ACCOUNT_MISSING}")
    return blockers


def _level_chain(index, all_index, absences, ticker, year, code, account) -> list[str]:
    """Blockers on `accounting_quality._growth_pct` for one balance-sheet level."""
    blockers = []
    if DD.level_amount(index[(year, code)], account) is None:
        blockers.append(f"{account}:CURRENT:{CURRENT_ACCOUNT_MISSING}")
    prior = index.get((year - 1, code))
    if prior is None:
        blockers.append(f"{account}:PRIOR_SAME_STAGE:"
                        + _missing_filing_reason(ticker, year - 1, code, all_index, absences))
    else:
        level = DD.level_amount(prior, account)
        if level is None:
            blockers.append(f"{account}:PRIOR_SAME_STAGE:{PRIOR_ACCOUNT_MISSING}")
        elif level <= 0:
            blockers.append(f"{account}:PRIOR_SAME_STAGE:{PRIOR_LEVEL_NONPOSITIVE}")
    return blockers


def diagnose_name_date(ticker: str, records: list[dict], share_records: list[dict],
                       as_of: str, absences: dict) -> dict:
    """Each feature's availability on one KR name-date, and every blocker if not.

    `fields` comes from the sealed `accounting_at`. The blocker walk is checked
    against it for every feature and raises on any disagreement.
    """
    fields, provenance = AF.accounting_at(records, as_of, "KR", share_records)
    out = {"features": {}, "currentFiling": None, "fsDiv": None, "availableFrom": None}
    if not records:
        for name in FEATURES:
            out["features"][name] = {"available": False, "blockers": [TICKER_NOT_IN_DART_COLLECTION]
                                     + calendar_blockers(as_of, name)}
        return _check(out, fields)
    visible = AF.visible_filings(records, as_of, "KR")
    if not visible:
        dated = [r for r in records if r.get("availableFrom") and r["availableFrom"] < as_of]
        code = FILING_REJECTED_RECEIPT_MISMATCH if dated else NO_FILING_VISIBLE_YET
        for name in FEATURES:
            out["features"][name] = {"available": False,
                                     "blockers": [code] + calendar_blockers(as_of, name)}
        return _check(out, fields)

    index = DD.index_filings(visible)
    all_index = DD.index_filings(records)
    year, code = max(index, key=lambda k: (k[0], STAGE_ORDER[k[1]]))
    filing = index[(year, code)]
    out.update({"currentFiling": f"{year}-{code}", "fsDiv": filing.get("fsDiv"),
                "availableFrom": filing.get("availableFrom")})

    ocf = (_flow_chain(index, all_index, absences, ticker, year, code, NET_INCOME)
           + _flow_chain(index, all_index, absences, ticker, year, code, OCF))
    if not ocf:
        net_income, _ = DD.trailing_twelve_months(index, year, code, NET_INCOME)
        if net_income == 0:
            ocf = [f"{NET_INCOME}:TTM:{NET_INCOME_ZERO}"]
    out["features"]["ocfToNetIncomePct"] = {"available": not ocf, "blockers": ocf}
    for name, account in LEVEL_ACCOUNT.items():
        blockers = _level_chain(index, all_index, absences, ticker, year, code, account)
        out["features"][name] = {"available": not blockers, "blockers": blockers}
    return _check(out, fields)


def _check(out: dict, fields: dict) -> dict:
    for name in FEATURES:
        if out["features"][name]["available"] != (fields.get(name) is not None):
            raise ValueError(f"AUDIT_DISAGREES_WITH_FEATURE_PATH: {name}")
    return out


def reason_of(blocker: str) -> str:
    """The reason code at the tail of a blocker string."""
    return blocker.rsplit(":", 1)[-1]


def primary_blocker(blockers: list[str]) -> str | None:
    """The first blocker in walk order -- current filing before its priors."""
    return blockers[0] if blockers else None


def filing_inventory(records: list[dict], absences: dict, universe_tickers,
                     years) -> list[dict]:
    """One row per ticker x fiscal year x report code the PIT universe could need.

    COLLECTED rows describe the stored filing and what it can derive on its
    own chain (every prior filing the store holds, no as-of cut): that is a
    property of the filing set, not of any signal date. Name-date availability,
    which does apply the as-of cut, is `diagnose_name_date`'s job.
    """
    by_ticker: dict[str, list[dict]] = defaultdict(list)
    for row in records:
        by_ticker[row["ticker"]].append(row)
    out = []
    for ticker in sorted(set(universe_tickers) | set(by_ticker)):
        held = by_ticker.get(ticker, [])
        index = DD.index_filings(held)
        for year in years:
            for code in ("11013", "11012", "11014", "11011"):
                filing = index.get((year, code))
                base = {"ticker": ticker, "fiscalYear": year, "reportCode": code,
                        "reportName": DF.REPORT_CODES[code]}
                if filing is None:
                    absent = absences.get((ticker, year, code))
                    if year < DF.FIRST_SERVED_YEAR:
                        status = "BEFORE_DART_SERVICE_START"
                    elif absent:
                        status = "RECORDED_ABSENT_BY_DART"
                    elif not held:
                        status = "TICKER_NOT_IN_DART_COLLECTION"
                    else:
                        status = "NOT_COLLECTED"
                    attempts = (absent or {}).get("attempts") or []
                    out.append({**base, "filingStatus": status,
                                "absenceStatus": (absent or {}).get("status") or (
                                    "/".join(f"{a.get('fsDiv')}={a.get('status')}" for a in attempts)
                                    or None),
                                "absenceCheckedAt": (absent or {}).get("checkedAt")})
                    continue
                accounts = filing.get("accounts") or {}
                ni = accounts.get(NET_INCOME) or {}
                fields, basis = AQ.derive_kr_fields(index, year, code)
                reasons = {}
                for name in FEATURES:
                    if fields.get(name) is not None:
                        continue
                    if name == "ocfToNetIncomePct":
                        chain = (_flow_chain(index, index, absences, ticker, year, code, NET_INCOME)
                                 + _flow_chain(index, index, absences, ticker, year, code, OCF))
                        reasons[name] = chain or [f"{NET_INCOME}:TTM:{NET_INCOME_ZERO}"]
                    else:
                        reasons[name] = _level_chain(index, index, absences, ticker, year, code,
                                                     LEVEL_ACCOUNT[name])
                out.append({
                    **base, "filingStatus": "COLLECTED",
                    "availableFrom": filing.get("availableFrom"),
                    "receiptNos": filing.get("receiptNos"),
                    "fsDiv": filing.get("fsDiv"),
                    "accountsPresent": sorted(accounts),
                    "requiredAccountsMissing": sorted(a for a in (NET_INCOME, OCF, ASSETS, LIABILITIES)
                                                      if a not in accounts),
                    "netIncomeStatement": ni.get("statement"),
                    "netIncomeLabel": ni.get("label"),
                    "netIncomeAccountId": ni.get("accountId"),
                    "incomeStatementOtherAccountsPresent": sorted(
                        a for a, e in accounts.items()
                        if a != NET_INCOME and e.get("statement") in INCOME_STATEMENTS),
                    "derivationBasis": {"netIncome": basis.get("netIncome"),
                                        "cashFlow": basis.get("cashFlow"),
                                        "priorAssetsAvailable": basis.get("priorAssetsAvailable"),
                                        "priorDebtAvailable": basis.get("priorDebtAvailable")},
                    "featureAvailability": {name: fields.get(name) is not None for name in FEATURES},
                    "unavailableReasons": reasons,
                })
    return out


def summarize_name_dates(diagnosed: list[dict]) -> dict:
    """Coverage and blocker tallies by year and feature, from diagnosed rows.

    Each input row carries `date` and the `features` dict of
    `diagnose_name_date`. Rows must already be restricted to the gate's
    denominator (tradable KR name-dates).
    """
    by_year: dict[str, dict] = {}
    for row in diagnosed:
        year = row["date"][:4]
        slot = by_year.setdefault(year, {"universeRows": 0, "features": {
            name: {"observed": 0, "primaryBlocker": Counter(), "anyBlocker": Counter(),
                   "reasonSet": Counter()} for name in FEATURES}})
        slot["universeRows"] += 1
        for name in FEATURES:
            info, tally = row["features"][name], slot["features"][name]
            if info["available"]:
                tally["observed"] += 1
                continue
            blockers = info["blockers"]
            tally["primaryBlocker"][primary_blocker(blockers)] += 1
            for reason in {reason_of(b) for b in blockers}:
                tally["anyBlocker"][reason] += 1
            tally["reasonSet"]["|".join(sorted({reason_of(b) for b in blockers}))] += 1
    out = {}
    for year, slot in sorted(by_year.items()):
        rows = slot["universeRows"]
        out[year] = {"universeRows": rows, "features": {}}
        for name, tally in slot["features"].items():
            out[year]["features"][name] = {
                "observed": tally["observed"],
                "coverage": tally["observed"] / rows if rows else None,
                "primaryBlocker": dict(sorted(tally["primaryBlocker"].items())),
                "rowsWithReason": dict(sorted(tally["anyBlocker"].items())),
                "rowsByReasonSet": dict(sorted(tally["reasonSet"].items())),
            }
    return out


def upper_bound_if_resolved(summary: dict, reasons) -> dict:
    """Coverage if EVERY name-date whose blockers all lie in `reasons` became available.

    An upper bound on what resolving those reasons could buy, never a
    projection: a re-collected filing may still lack the account, and a name
    with any blocker outside `reasons` is not counted.
    """
    reasons = set(reasons)
    out = {}
    for year, slot in summary.items():
        out[year] = {}
        for name, tally in slot["features"].items():
            gain = sum(n for key, n in tally["rowsByReasonSet"].items()
                       if set(key.split("|")) <= reasons)
            rows = slot["universeRows"]
            out[year][name] = (tally["observed"] + gain) / rows if rows else None
    return out
