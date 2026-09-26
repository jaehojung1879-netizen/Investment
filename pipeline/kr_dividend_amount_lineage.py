"""Decode `alotMatter.json`'s `se`/`stock_knd` raw category labels into a
DIVIDEND AMOUNT lineage, from LIVE-OBSERVED values only.

WHY THIS IS A SEPARATE MODULE FROM `kr_corporate_action_events.py`. That
module confirms the ENDPOINT and its field NAMES live
(`endpointConfidence: CONFIRMED_LIVE`) but deliberately keeps `se`/
`stock_knd` RAW and uninterpreted — exactly the two-step promotion
`dart_ownership_events.py`'s `report_tp` went through (workflow-hygiene
invariants, v2.25): confirm the endpoint first, decode a raw enum's VALUES
only from what a live response actually served, never from documentation or
plausible guessing. This module is that second step, and it exists only
because a real collection run now has real values to read.

`KNOWN_SE_RAW_VALUES` below is exhaustive over 6,150 real rows collected
2026-09-25 (`collect_kr_dividend_sections.py`, signal-history commit
`dfeb098e26ff71d3b8149199677417a78eda42d6`, 47/47 tickers) — every distinct
`categoryRaw` string that endpoint has ever actually served to this
repository. A category this catalog does not name is UNKNOWN, and a row
carrying it is preserved raw but never decoded into an amount: this module
never invents a thirteenth category from a plausible-looking label.

TWO DIFFERENT TRANSLATION RISKS, NOT ONE. `report_tp`'s "일반"/"약식" was a
DART-INTERNAL enum code with no public meaning outside DART's own system —
guessing what it meant was guessing at an implementation detail. `se`'s
values here (`주당 현금배당금(원)`, `현금배당수익률(%)`, ...) and
`stock_knd`'s (`보통주`, `우선주`, ...) are standard, dictionary-level
Korean financial-market vocabulary used identically across every Korean
listed company's own investor-relations material — "주당 현금배당금" is
literally "cash dividend per share", not a DART-specific abbreviation
requiring reverse engineering. This catalog is therefore a LITERAL reading
of what each label states, not an inference about an opaque code, and each
entry's translation is a plain dictionary gloss, checkable independently of
this repository.

ONLY CASH_DPS AND STOCK_DPS ARE "DIVIDEND AMOUNT LINEAGE". The other ten
confirmed categories (yield %, payout ratio %, net income, EPS, par value,
total distribution amounts) are real, live-observed, decoded facts — kept
and classified — but they describe COMPANY-LEVEL or RATIO facts, not what
one shareholder received per share, so `dividend_amount_lineage_for_ticker`
reads only the two per-share distribution amounts.

NO EX-DATE, RECORD DATE, DECISION DATE OR PAYMENT DATE IS EVER PRODUCED
HERE. `alotMatter.json` states a FISCAL-PERIOD amount, dated only by its
filing's own receipt — `kr_corporate_action_events.build_dividend_section_
row` already sets every date-role field but `receiptDate` to `None`, and
this module reads that record, never invents one. Dividend EVENT-DATE
lineage (`exDateSemanticsResolved`) stays `DIVIDEND_EX_DATE_LINEAGE_BLOCKED`
regardless of what this module resolves — see
`kr_termination_inventory.completeness_row`'s own rule, unchanged.
"""
from __future__ import annotations

import datetime as _dt

CASH_DPS = "CASH_DPS"
STOCK_DPS = "STOCK_DPS"
CASH_DIVIDEND_YIELD_PCT = "CASH_DIVIDEND_YIELD_PCT"
STOCK_DIVIDEND_YIELD_PCT = "STOCK_DIVIDEND_YIELD_PCT"
CONSOLIDATED_NET_INCOME_MM = "CONSOLIDATED_NET_INCOME_MM"
CONSOLIDATED_PAYOUT_RATIO_PCT = "CONSOLIDATED_PAYOUT_RATIO_PCT"
PAR_VALUE_PER_SHARE = "PAR_VALUE_PER_SHARE"
STOCK_DIVIDEND_TOTAL_MM = "STOCK_DIVIDEND_TOTAL_MM"
CASH_DIVIDEND_TOTAL_MM = "CASH_DIVIDEND_TOTAL_MM"
CONSOLIDATED_EPS = "CONSOLIDATED_EPS"
SEPARATE_NET_INCOME_MM = "SEPARATE_NET_INCOME_MM"
UNSPECIFIED_EPS = "UNSPECIFIED_EPS"
INDIVIDUAL_NET_INCOME_MM = "INDIVIDUAL_NET_INCOME_MM"

# Every `categoryRaw` value this endpoint has ever actually served to this
# repository (6,150/6,150 rows covered, zero UNKNOWN as of the commit
# above). A literal dictionary gloss of standard Korean dividend-disclosure
# vocabulary -- see module docstring for why this is not the same
# translation risk `report_tp` posed.
KNOWN_SE_RAW_VALUES: dict[str, str] = {
    "주당 현금배당금(원)": CASH_DPS,
    "현금배당수익률(%)": CASH_DIVIDEND_YIELD_PCT,
    "주당 주식배당(주)": STOCK_DPS,
    "주식배당수익률(%)": STOCK_DIVIDEND_YIELD_PCT,
    "(연결)당기순이익(백만원)": CONSOLIDATED_NET_INCOME_MM,
    "(연결)현금배당성향(%)": CONSOLIDATED_PAYOUT_RATIO_PCT,
    "주당액면가액(원)": PAR_VALUE_PER_SHARE,
    "주식배당금총액(백만원)": STOCK_DIVIDEND_TOTAL_MM,
    "현금배당금총액(백만원)": CASH_DIVIDEND_TOTAL_MM,
    "(연결)주당순이익(원)": CONSOLIDATED_EPS,
    "(별도)당기순이익(백만원)": SEPARATE_NET_INCOME_MM,
    "주당순이익(원)": UNSPECIFIED_EPS,
    "(개별)당기순이익(백만원)": INDIVIDUAL_NET_INCOME_MM,
}

# The two metrics that ARE a per-share distribution amount, as opposed to a
# ratio, a company-level total, or an earnings figure.
AMOUNT_LINEAGE_METRICS = frozenset({CASH_DPS, STOCK_DPS})

COMMON = "COMMON"
PREFERRED = "PREFERRED"
OTHER_CLASS_SHARE = "OTHER_CLASS_SHARE"
UNSPECIFIED_CLASS = "UNSPECIFIED_CLASS"

# Every `stockKindRaw` value this endpoint has ever actually served
# (6,150/6,150 rows covered). "보통주"/"우선주" and their compounds are
# literally "common stock"/"preferred stock" in standard Korean corporate
# vocabulary. `종류주식` ("class stock") is a distinct Korean Commercial Act
# term for a broader family of special share classes that is NOT
# synonymous with preferred stock, so it is kept as its own class rather
# than folded into PREFERRED -- exactly the conservatism this catalog's
# sibling (`KNOWN_SE_RAW_VALUES`) also applies. A row with `-` states no
# class at all (the figure is company-wide, e.g. net income or a payout
# ratio) and is UNSPECIFIED_CLASS, never assumed to mean common stock.
KNOWN_STOCK_KIND_RAW_VALUES: dict[str, str] = {
    "-": UNSPECIFIED_CLASS,
    "보통주": COMMON,
    "보통주식": COMMON,
    "의결권 있는 보통주": COMMON,
    "보통주 (주1)": COMMON,
    "보통주 \n(주1)": COMMON,
    "우선주": PREFERRED,
    "우선주식": PREFERRED,
    "의결권 없는 우선주": PREFERRED,
    "1우선주": PREFERRED,
    "2우선주": PREFERRED,
    "배당우선상환주식": PREFERRED,
    "배당우선전환주식": PREFERRED,
    "우선주\n(주1)": PREFERRED,
    "우선주\n(주2)": PREFERRED,
    "우선주\n (주1) ": PREFERRED,
    "우선주\n (주2) ": PREFERRED,
    "종류주식": OTHER_CLASS_SHARE,
}


def parse_amount(raw) -> float | None:
    """A `thstrm`/`frmtrm`/`lwfr`-style figure: `"-"` (or blank) is "not
    stated", never zero; a comma-grouped number parses to a float,
    preserving a leading minus sign."""
    text = str(raw or "").strip()
    if not text or text == "-":
        return None
    cleaned = text.replace(",", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def decode_row(record: dict) -> dict:
    """One `build_dividend_section_row` output, with its category/class
    DECODED where a live-observed value exists, alongside the untouched raw
    fields. `metric`/`shareClass` are `None` — never guessed — for any
    value not in `KNOWN_SE_RAW_VALUES`/`KNOWN_STOCK_KIND_RAW_VALUES`.
    """
    metric = KNOWN_SE_RAW_VALUES.get(record.get("categoryRaw"))
    share_class = KNOWN_STOCK_KIND_RAW_VALUES.get(record.get("stockKindRaw"))
    return {
        **record,
        "metric": metric,
        "shareClass": share_class,
        "currentPeriodValue": parse_amount(record.get("currentPeriodRaw")),
        "priorPeriodValue": parse_amount(record.get("priorPeriodRaw")),
        "priorPriorPeriodValue": parse_amount(record.get("priorPriorPeriodRaw")),
    }


def dividend_amount_lineage_for_ticker(rows: list[dict]) -> dict:
    """One ticker's dividend AMOUNT lineage: every real (non-`None`)
    CASH_DPS/STOCK_DPS observation, by fiscal year and share class, cited
    to its own filing receipt. A fiscal year with no stated figure in any
    filing that could have reported it is absent from `entries` — never
    filled with 0.0, which this repository's measurement-absence
    invariants (v2.11) forbid for exactly this shape of gap.

    `selfConsistency` cross-checks each entry's CURRENT-period figure
    against any LATER filing's PRIOR-period figure for the same
    (fiscalYear, shareClass, metric) -- two independent filings stating the
    same historical figure agreeing is corroboration the collection is
    reading the right column; a disagreement is published, never resolved
    by picking one.
    """
    decoded = [decode_row(r) for r in rows]
    entries: dict[tuple, dict] = {}
    for row in decoded:
        if row["metric"] not in AMOUNT_LINEAGE_METRICS:
            continue
        year = row.get("bsnsYear")
        share_class = row["shareClass"]
        value = row["currentPeriodValue"]
        if value is None or year is None:
            continue
        key = (year, share_class, row["metric"])
        entries[key] = {
            "fiscalYear": year, "shareClass": share_class, "metric": row["metric"],
            "value": value, "sourceReceiptNumber": row["receiptNo"],
            "sourceReceiptDate": row["receiptDate"],
        }

    # Self-consistency: does a LATER filing's own prior-period column agree
    # with the value the filing FOR that year itself stated?
    consistency: list[dict] = []
    for row in decoded:
        if row["metric"] not in AMOUNT_LINEAGE_METRICS or row.get("bsnsYear") is None:
            continue
        prior_year = row["bsnsYear"] - 1
        prior_value = row["priorPeriodValue"]
        if prior_value is None:
            continue
        key = (prior_year, row["shareClass"], row["metric"])
        primary = entries.get(key)
        if primary is None:
            continue
        agrees = abs(primary["value"] - prior_value) < 1e-6
        consistency.append({
            "fiscalYear": prior_year, "shareClass": row["shareClass"],
            "metric": row["metric"], "primaryValue": primary["value"],
            "laterFilingPriorPeriodValue": prior_value,
            "citingReceiptNumber": row["receiptNo"], "agrees": agrees,
        })

    return {
        "entries": sorted(entries.values(), key=lambda e: (e["fiscalYear"], e["shareClass"] or "",
                                                            e["metric"])),
        "selfConsistency": consistency,
        "selfConsistencyDisagreements": sum(1 for c in consistency if not c["agrees"]),
    }


# --------------------------------------------------------------------------- #
# Fiscal-year cross-validation against real Yahoo distribution events
# --------------------------------------------------------------------------- #
EXACT_MATCH = "EXACT_MATCH"
AMOUNT_MISMATCH = "AMOUNT_MISMATCH"
NO_YAHOO_EVENT_IN_WINDOW = "NO_YAHOO_EVENT_IN_WINDOW"

# A Korean common-stock fiscal-year dividend's RECORD date sits at the
# fiscal year's own close (measured directly: 000100.KS's real sealed
# corporate-events show a 2015-12-29 event of 2000.0000383... against this
# module's own FY2015 CASH_DPS COMMON reading of 2000.0 -- an exact match
# to five significant figures), while the alotMatter FILING that STATES
# that figure is not submitted until ~3 months into the following year
# (`receiptDate` 2016-03-30 for the same figure). `kr_dividend_
# reconciliation.match_events`'s 10-day point-date tolerance was designed
# for a `recordDate` reasonably close to the economic event; matching it
# against `receiptDate` instead (the only date this endpoint states) is
# therefore a near-guaranteed non-match ON TIMING ALONE, not evidence the
# AMOUNT is wrong. This function cross-validates the AMOUNT over the
# economically plausible window instead, and is a diagnostic ADDITIONAL to
# `kr_dividend_reconciliation`, never a replacement for it -- once a real
# record/ex-date exists (Section 13's DIRECT-only rule), the point-date
# matcher is the correct instrument again.
FISCAL_YEAR_WINDOW_START_OFFSET_MONTHS = 0   # December 1 of the fiscal year
FISCAL_YEAR_WINDOW_END_OFFSET_MONTHS = 6     # through June 30 of year+1


def _fiscal_year_window(fiscal_year: int) -> tuple[_dt.date, _dt.date]:
    start = _dt.date(fiscal_year, 12, 1)
    end = _dt.date(fiscal_year + 1, 6, 30)
    return start, end


def cross_validate_against_yahoo_by_fiscal_year(
        dart_entries: list[dict], yahoo_events: list[dict], *,
        amount_tolerance_pct: float = 1.0) -> list[dict]:
    """For every COMMON-class CASH_DPS entry, sum the real Yahoo dividend
    events whose date falls in that fiscal year's economically plausible
    window (December of the fiscal year through the following June -- a
    Korean fiscal-year-end common dividend's own record date, never
    assumed to be exact without this being read as an ex-date lineage
    claim; see module docstring) and classify the agreement.

    Every DART entry is classified into exactly one of `EXACT_MATCH`,
    `AMOUNT_MISMATCH`, `NO_YAHOO_EVENT_IN_WINDOW` -- never silently
    dropped, and no disagreement is resolved by picking a side.
    """
    out = []
    for entry in dart_entries:
        if entry["metric"] != CASH_DPS or entry["shareClass"] != COMMON:
            continue
        start, end = _fiscal_year_window(entry["fiscalYear"])
        window_events = [
            e for e in yahoo_events
            if start <= _dt.date.fromisoformat(str(e["date"])[:10]) <= end
        ]
        yahoo_sum = sum(e["amountPerShare"] for e in window_events) if window_events else None
        if yahoo_sum is None:
            status = NO_YAHOO_EVENT_IN_WINDOW
        else:
            denom = max(abs(entry["value"]), abs(yahoo_sum)) or 1.0
            close = abs(entry["value"] - yahoo_sum) / denom * 100.0 <= amount_tolerance_pct
            status = EXACT_MATCH if close else AMOUNT_MISMATCH
        out.append({
            "fiscalYear": entry["fiscalYear"], "dartValue": entry["value"],
            "yahooWindowSum": yahoo_sum, "yahooEventsInWindow": len(window_events),
            "sourceReceiptNumber": entry["sourceReceiptNumber"], "status": status,
        })
    return out
