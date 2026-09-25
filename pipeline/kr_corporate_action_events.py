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
from . import dart_ownership_universe as DOU

# Reused directly, exactly as `dart_ownership_events.receipt_date` reuses it —
# a control that is called is safer than one reproduced.
receipt_date = DF.receipt_date

# DART's own "no data found" status (`dart_fundamentals.STATUS_MEANING`:
# "조회된 데이터 없음") — the answer `list.json` gives a ticker with zero
# matching disclosures. Reused, not reinvented: this is the exact code
# `dart_fundamentals.build_record`'s docstring already documents for the
# statement endpoint, and `list.json` shares DART's one status-code table.
NO_DATA_STATUS = "013"

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

    Status `013` ("no data found") is DART's own answer for a ticker with
    zero matching disclosures — a valid, common outcome (most tickers have
    no merger/tender/delisting filing) — and returns `([], "")`, never an
    error. A response that is neither `013` nor carrying a `list` key is a
    different fact (a schema DART did not document) and IS an error.
    """
    if not isinstance(payload, dict):
        return [], f"payload was {type(payload).__name__}, not an object"
    if str(payload.get("status") or "") == NO_DATA_STATUS:
        return [], ""
    rows = payload.get("list")
    if rows is None:
        return [], "no 'list' key in payload"
    if not isinstance(rows, list):
        return [], f"'list' was {type(rows).__name__}, not a list"
    return rows, ""


class PaginationError(RuntimeError):
    """The result set could not be walked deterministically to completion."""


# Corroborated (not confirmed) field names for `list.json` (DS001)'s own
# pagination — direct access to `opendart.fss.or.kr` is blocked from this
# sandbox's egress, so these are read from independent third-party OpenDART
# client documentation (three separate WebSearch-surfaced sources agree:
# a Postman collection, the `dart-fss` client docs, and general usage
# writeups), the same evidentiary standard `ALOTMATTER_CANDIDATE_FIELDS`
# above and `dart_ownership_events.py`'s original `majorstock.json` fields
# used before their own live probes ran. `scripts/probe_kr_corporate_actions
# .py` is what promotes this from corroborated to confirmed.
PAGINATION_FIELDS = ("page_no", "page_count", "total_count", "total_page")


def parse_pagination_metadata(payload: dict) -> tuple[dict | None, str]:
    """(meta, error) from a `list.json` response's own pagination fields.

    Every field is required and must parse as a non-negative integer; a
    missing or non-numeric field is a hard error rather than an assumed
    value — "we don't know how many pages there are" must never be silently
    read as "there is exactly one". `totalCount`/`totalPage` are
    cross-checked for internal consistency (zero results imply zero or one
    page; a nonzero count implies at least one page).
    """
    if not isinstance(payload, dict):
        return None, f"payload was {type(payload).__name__}, not an object"
    missing = [field for field in PAGINATION_FIELDS if field not in payload]
    if missing:
        return None, f"missing pagination field(s): {missing}"
    parsed: dict[str, int] = {}
    for field in PAGINATION_FIELDS:
        value = payload[field]
        try:
            parsed[field] = int(value)
        except (TypeError, ValueError):
            return None, f"pagination field {field!r} is not an integer: {value!r}"
        if parsed[field] < 0:
            return None, f"pagination field {field!r} is negative: {value!r}"
    meta = {"pageNo": parsed["page_no"], "pageCount": parsed["page_count"],
            "totalCount": parsed["total_count"], "totalPage": parsed["total_page"]}
    if meta["totalCount"] == 0:
        if meta["totalPage"] not in (0, 1):
            return None, f"totalCount is 0 but totalPage is {meta['totalPage']}"
    elif meta["totalPage"] < 1:
        return None, f"totalCount is {meta['totalCount']} but totalPage is {meta['totalPage']}"
    return meta, ""


def pagination_consistent(first_meta: dict, later_meta: dict) -> bool:
    """Whether a later page's totalCount/totalPage still match the first
    page's. If not, the underlying result set changed mid-walk — most likely
    a new filing landed between calls — and the whole fetch must be refused
    rather than silently mixing rows from two different result sets.
    """
    return (first_meta["totalCount"] == later_meta["totalCount"]
            and first_meta["totalPage"] == later_meta["totalPage"])


def merge_paginated_rows(pages: list[list[dict]]) -> list[dict]:
    """Flatten every page's raw rows, deduplicated by `rcept_no`.

    Keeps each row's first occurrence, in page order (`list.json` is
    requested `sort=date&sort_mth=asc`, so within a page rows are already
    chronological; `candidate_disclosures` resorts the merged result
    explicitly rather than trusting page order alone).
    """
    seen: set = set()
    merged: list[dict] = []
    for page in pages:
        for row in page:
            rcept_no = row.get("rcept_no")
            if rcept_no in seen:
                continue
            seen.add(rcept_no)
            merged.append(row)
    return merged


def fetch_all_pages(fetch_page) -> tuple[list[dict], dict]:
    """Walk every page of a `list.json` result set to completion.

    `fetch_page(page_no)` must return one raw JSON payload for that page —
    network-free here, exactly the fetch/parse split this module keeps
    everywhere else; the caller (a probe or collector script) supplies the
    real HTTP call. Raises `PaginationError` — never returns a partial
    result silently — on a missing/inconsistent pagination field, a
    row-parse failure on any page, or the result set changing mid-walk.
    """
    first_payload = fetch_page(1)
    rows, error = filing_index_rows(first_payload)
    if error:
        raise PaginationError(f"page 1: {error}")
    status = str(first_payload.get("status") or "")
    if status == NO_DATA_STATUS:
        return [], {"status": status, "pageNo": 1, "pageCount": 0, "totalCount": 0,
                    "totalPage": 0, "pagesFetched": 0, "rowsFetched": 0}
    meta, meta_error = parse_pagination_metadata(first_payload)
    if meta_error:
        raise PaginationError(f"page 1: {meta_error}")
    pages = [rows]
    total_page = meta["totalPage"]
    for page_no in range(2, total_page + 1):
        payload = fetch_page(page_no)
        page_rows, page_error = filing_index_rows(payload)
        if page_error:
            raise PaginationError(f"page {page_no}: {page_error}")
        page_meta, page_meta_error = parse_pagination_metadata(payload)
        if page_meta_error:
            raise PaginationError(f"page {page_no}: {page_meta_error}")
        if not pagination_consistent(meta, page_meta):
            raise PaginationError(
                f"page {page_no}: pagination metadata changed mid-walk "
                f"(totalCount {meta['totalCount']}->{page_meta['totalCount']}, "
                f"totalPage {meta['totalPage']}->{page_meta['totalPage']})")
        pages.append(page_rows)
    merged = merge_paginated_rows(pages)
    return merged, {**meta, "status": status, "pagesFetched": total_page,
                    "rowsFetched": len(merged)}


# --------------------------------------------------------------------------- #
# Historical DART issuer identity — reused, never reimplemented
# --------------------------------------------------------------------------- #
EXACT_STOCK_CODE = "EXACT_STOCK_CODE"
UNIQUE_NORMALIZED_NAME = "UNIQUE_NORMALIZED_NAME"
UNRESOLVED = "UNRESOLVED"
RESOLVED = "RESOLVED"
IDENTITY_BASES = (EXACT_STOCK_CODE, UNIQUE_NORMALIZED_NAME, UNRESOLVED)


def resolve_historical_dart_identity(stock_code: str, krx_name: str | None,
                                     dart_directory: list[dict]) -> dict:
    """One security's DART issuer identity, by the repository's EXISTING
    historical-identity hierarchy — `dart_ownership_universe._resolve_security`
    /`_unique_index`, called directly (not reimplemented) rather than a
    second, weaker path. Resolving a terminated/delisted KR security only by
    its CURRENT `corpCode.xml` stock code is too weak, because DART blanks a
    corp's `stock_code` field once it delists — this hierarchy is exactly
    why `dart_ownership_universe.py` was built for the whole KR ownership
    collector, and it is reused here rather than rebuilt:

        1. exact stock code (Korean 6-digit codes are stable identifiers
           that do not change or get reused the way US tickers do)
        2. a UNIQUE exact normalized historical company name — never fuzzy,
           and an ambiguous match (more than one candidate) stays unresolved
        3. otherwise unresolved

    `stock_code` is the bare 6-digit code (no `.KS` suffix). `krx_name` is
    the ticker's own KRX name as already carried on the termination
    inventory (`krxName`) — never a guessed or stemmed variant.

    Calls `dart_ownership_universe`'s module-private `_resolve_security`/
    `_unique_index` directly rather than adding a public alias to that
    module: `alpha-opportunity-model-v1`'s sealed dependency closure pins
    `dart_ownership_universe.py`'s own file hash, and even an additive,
    behaviour-preserving edit to that file would raise
    `SEALED_DEPENDENCY_CHANGED` on load — calling its private functions by
    name changes nothing on disk there while still reusing its exact logic,
    never a second implementation of it.
    """
    security = {"stockCode": stock_code, "names": [krx_name] if krx_name else []}
    by_stock = DOU._unique_index(dart_directory, "stockCode")
    by_name = DOU._unique_index(dart_directory, "corpName")
    row, provenance = DOU._resolve_security(security, by_stock, by_name)
    if row is None:
        return {"status": UNRESOLVED, "corpCode": None, "corpName": None,
               "basis": UNRESOLVED, "provenance": provenance}
    basis = (EXACT_STOCK_CODE if provenance.get("method") == "DART_STOCK_CODE_EXACT"
             else UNIQUE_NORMALIZED_NAME)
    return {"status": RESOLVED, "corpCode": row["corpCode"],
           "corpName": row.get("corpName"), "basis": basis, "provenance": provenance}


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
