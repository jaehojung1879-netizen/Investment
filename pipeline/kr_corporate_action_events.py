"""Raw KR corporate-action disclosure discovery and dividend-section parsing.

WHAT THIS IS FOR. `alpha-opportunity-model-v3`'s sealed survivorship audit
found 22 KR terminated securities with zero dividend events and no terminal
value on record (`docs/alpha-opportunity-v3-data-repair-plan.md`). This module
is the read/parse half of the repair: it never calls a network, exactly the
split `dart_fundamentals.py` and `dart_ownership_events.py` already use
between "fetch" and "parse" (`scripts/probe_*` and `scripts/collect_*` do the
fetching).

TWO CONFIDENCE TIERS, NEVER BLURRED.

1. **CONFIRMED.** `list.json` (DART's disclosure-index endpoint, API group
   DS001) is already used live in this repository —
   `probe_dart_ownership_events.official_filing_depth` calls it and reads
   `rcept_no`, `rcept_dt`, `report_nm`, `corp_code` from a real response. This
   module's `filing_index_rows`/`candidate_disclosures` read the exact same
   confirmed fields. Nothing here parses a STRUCTURED disclosure field (an
   amount, a ratio, a record date) from `list.json` — it carries only a
   report's name and its receipt.

2. **CANDIDATE, PENDING A LIVE PROBE.** `alotMatter.json` (배당에 관한 사항,
   dividend information) is DART's own documented dividend-section endpoint.
   WebFetch of `opendart.fss.or.kr` itself is blocked from this sandbox's
   egress — the exact block `dart_ownership_events.py`'s docstring already
   records for the same host — so its field names here
   (`ALOTMATTER_CANDIDATE_FIELDS`) are corroborated from independent
   third-party OpenDART client documentation, the same standard
   `dart_ownership_events.py` used for `majorstock.json` before
   `scripts/probe_dart_ownership_events.py` confirmed it live. They are
   marked `endpointConfidence: CANDIDATE_UNCONFIRMED` on every row this
   module builds, and stay that way until `scripts/probe_kr_corporate_actions
   .py` runs against the real API with a real key.

WHAT IS DELIBERATELY NOT HERE. Structured endpoints for merger, share
exchange/transfer, tender offer and delisting decisions are a further DART
API family this sandbox could not reach or corroborate with confidence
(`docs/kr-terminated-security-total-return-foundation-v1.md` records the
attempt). Guessing an endpoint path or field map for them would be exactly
the defect this repository's vendor-refusal and PIT-fundamentals invariants
warn against — so this module discovers THOSE disclosures only by their
report NAME, through the confirmed `list.json` endpoint, and leaves
structured extraction to a later probe. A report-name match is a reading
list for a human reviewer, never a termination-type verdict — see
`classify_disclosure_family`.

DATE ROLES ARE NEVER COLLAPSED. Every record in this module keeps the seven
roles below as separate fields; a role DART did not state stays `None`
rather than being filled from a different role:

    receiptDate      -- public disclosure availability (PIT)
    decisionDate      -- board/shareholder decision date, if stated
    recordDate        -- entitlement record date (e.g. 배당기준일)
    exDate            -- economic ex-date; see EX_DATE_STATUS_BLOCKED below
    effectiveDate      -- merger/exchange/delisting/settlement economic date
    lastTradingDate
    paymentDate

`exDate` is never derived from `recordDate` by assumption. No sealed, dated
Korean settlement-cycle rule exists anywhere in this repository from which an
ex-date could be computed, and this sandbox could not reach an authoritative
source to establish one (KRX's own settlement-cycle history was searched;
nothing citable was found — see the doc above). `EX_DATE_STATUS_BLOCKED`
stays the status for every record until a primary, dated source is read and
cited in a future change.
"""
from __future__ import annotations

from . import dart_fundamentals as DF

# Reused directly, exactly as `dart_ownership_events.receipt_date` reuses it —
# a control that is called is safer than one reproduced.
receipt_date = DF.receipt_date

DATE_ROLES = (
    "receiptDate", "decisionDate", "recordDate", "exDate",
    "effectiveDate", "lastTradingDate", "paymentDate",
)

EX_DATE_STATUS_BLOCKED = "DIVIDEND_EX_DATE_LINEAGE_BLOCKED"

# --------------------------------------------------------------------------- #
# Disclosure-family classification -- report_nm TEXT only, via the already-
# confirmed list.json endpoint. Never a termination-type verdict.
# --------------------------------------------------------------------------- #
MERGER = "MERGER"
SHARE_EXCHANGE_OR_TRANSFER = "SHARE_EXCHANGE_OR_TRANSFER"
SPINOFF_OR_SPLIT_MERGER = "SPINOFF_OR_SPLIT_MERGER"
BUSINESS_TRANSFER = "BUSINESS_TRANSFER"
TENDER_OFFER = "TENDER_OFFER"
DELISTING = "DELISTING"
DIVIDEND_DECISION = "DIVIDEND_DECISION"

# Every keyword is a report-name substring DART is documented to use for the
# named disclosure family (corroborated the same way the endpoint names
# above are — third-party OpenDART documentation, direct access blocked).
# This dict decides which filings a human goes to READ; see module docstring.
DISCLOSURE_FAMILY_KEYWORDS: dict[str, tuple[str, ...]] = {
    MERGER: ("합병결정", "합병 등 종료보고서"),
    SHARE_EXCHANGE_OR_TRANSFER: ("주식교환", "주식이전"),
    SPINOFF_OR_SPLIT_MERGER: ("분할합병결정", "회사분할결정"),
    BUSINESS_TRANSFER: ("영업양수", "영업양도"),
    TENDER_OFFER: ("공개매수",),
    DELISTING: ("상장폐지", "정리매매"),
    DIVIDEND_DECISION: ("현금ㆍ현물배당결정", "현금·현물배당결정",
                        "현금배당결정", "현물배당결정"),
}

AMENDMENT_MARKERS = ("정정",)


def classify_disclosure_family(report_nm) -> tuple[str, ...]:
    """Which disclosure families a `report_nm` string matches, if any.

    A name can match more than one family (rare, but not impossible for a
    combined report); every match is kept rather than picking one, sorted for
    determinism.
    """
    text = str(report_nm or "")
    return tuple(sorted(family for family, keywords in DISCLOSURE_FAMILY_KEYWORDS.items()
                        if any(keyword in text for keyword in keywords)))


def is_amendment(report_nm) -> bool:
    return any(marker in str(report_nm or "") for marker in AMENDMENT_MARKERS)


def filing_index_rows(payload: dict) -> tuple[list[dict], str]:
    """Parse a `list.json` (DS001) response into its raw rows, or (empty, reason).

    Mirrors `probe_dart_ownership_events.official_filing_depth`'s own read of
    this endpoint: `rows key must be exactly "list"` is what DART actually
    serves, confirmed live in this repository already.
    """
    if not isinstance(payload, dict):
        return [], f"payload was {type(payload).__name__}, not an object"
    rows = payload.get("list")
    if rows is None:
        return [], "no 'list' key in payload"
    if not isinstance(rows, list):
        return [], f"'list' was {type(rows).__name__}, not a list"
    return rows, ""


def candidate_disclosures(rows: list[dict], *, ticker: str | None = None) -> list[dict]:
    """Every filing-index row matching a known disclosure-family keyword.

    A reading list for a human reviewer, tagged with the receipt date the
    match became public. Never assigns a termination type — see module
    docstring. A row with no receipt date is refused, the same rule
    `dart_fundamentals.build_record` applies to a financial statement.
    """
    out = []
    for row in rows:
        families = classify_disclosure_family(row.get("report_nm"))
        if not families:
            continue
        available_from = receipt_date(row.get("rcept_no"))
        if available_from is None:
            continue
        out.append({
            "ticker": ticker,
            "corpCode": row.get("corp_code"),
            "corpName": row.get("corp_name"),
            "reportName": row.get("report_nm"),
            "disclosureFamilies": list(families),
            "receiptNo": row.get("rcept_no"),
            "receiptDate": available_from,
            "filerName": row.get("flr_nm"),
            "isAmendment": is_amendment(row.get("report_nm")),
        })
    return sorted(out, key=lambda r: (str(r["receiptDate"]), str(r["receiptNo"])))


def amendment_chain(disclosures: list[dict]) -> list[dict]:
    """Group same-family disclosures for one issuer by receipt order.

    Every row is kept — this never collapses a chain to "the latest wins".
    `priorFilingsInChain` lets a downstream reader see the full history; which
    filing's TERMS to trust is a decision for the record built from it, not
    for this function. PIT availability of any one filing is always its own
    receipt date, never the original's — see module docstring section on
    amendments.
    """
    seen_by_key: dict[tuple, list[dict]] = {}
    out = []
    for row in sorted(disclosures, key=lambda r: (str(r["receiptDate"]), str(r["receiptNo"]))):
        key = (row.get("corpCode"), tuple(sorted(row.get("disclosureFamilies") or ())))
        history = seen_by_key.setdefault(key, [])
        marked = dict(row)
        marked["priorFilingsInChain"] = [r["receiptNo"] for r in history]
        history.append(row)
        out.append(marked)
    return out


# --------------------------------------------------------------------------- #
# alotMatter.json (배당에 관한 사항) -- CANDIDATE, PENDING A LIVE PROBE
# --------------------------------------------------------------------------- #
ALOTMATTER_CANDIDATE_FIELDS = ("rcept_no", "corp_code", "corp_name", "se",
                               "thstrm", "frmtrm", "lwfr", "stock_knd")
CANDIDATE_UNCONFIRMED = "CANDIDATE_UNCONFIRMED"


def build_dividend_section_row(row: dict, *, ticker: str | None,
                               collected_at: str) -> tuple[dict | None, str]:
    """One `alotMatter.json` row, raw-preserved, iff it carries a receipt.

    `se` ("구분", DART's own row-category label — e.g. the DPS line itself
    versus a payout-ratio line) is kept RAW and never interpreted, the same
    discipline `dart_ownership_events.reportTypeRaw` uses for `report_tp`:
    guessing a category's meaning before a live response confirms its actual
    values is the exact defect the workflow-hygiene invariants (v2.25)
    record and fix for that field.

    This gives a fiscal-period DPS reading, dated by the report's receipt —
    never a record date or an ex-date, which this endpoint is not documented
    to carry.
    """
    rcept_no = str(row.get("rcept_no") or "").strip()
    if not rcept_no:
        return None, "NO_RECEIPT_NO"
    available_from = receipt_date(rcept_no)
    if available_from is None:
        return None, "NO_RECEIPT_DATE"
    return {
        "id": f"dart-dividend-section:{rcept_no}:{row.get('se')}:{row.get('stock_knd')}",
        "ticker": ticker,
        "corpCode": row.get("corp_code"),
        "corpName": row.get("corp_name"),
        "receiptNo": rcept_no,
        "receiptDate": available_from,
        "categoryRaw": row.get("se"),
        "stockKindRaw": row.get("stock_knd"),
        "currentPeriodRaw": row.get("thstrm"),
        "priorPeriodRaw": row.get("frmtrm"),
        "priorPriorPeriodRaw": row.get("lwfr"),
        "decisionDate": None, "recordDate": None, "exDate": None,
        "effectiveDate": None, "lastTradingDate": None, "paymentDate": None,
        "endpointConfidence": CANDIDATE_UNCONFIRMED,
        "source": "DART:alotMatter",
        "collectedAt": collected_at,
    }, ""
