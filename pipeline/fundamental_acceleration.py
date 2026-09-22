"""Point-in-time fundamental ACCELERATION -- filing-over-filing change in a
company's own profitability, margins and growth, read strictly from
``FundamentalStore``'s existing per-filing history.

WHAT THIS MODULE IS
--------------------
The single shared implementation of "find the current filing, find the
immediately preceding CONSECUTIVE filing, both PIT-visible, and compute the
change" -- used identically by the historical discovery study
(``fundamental_acceleration_discovery.py``) and by the prospective sealing
script, so the two never drift into two different definitions of the same
signal.

No new collection, no new vendor, no new normalization scheme. It reads
``FundamentalStore``'s already-production-proven ``PIT_FUNDAMENTALS_V1``
records (DART for KR via ``dart_derive.py``, Finnhub for US via
``finnhub_derive.py``) exactly as ``challenger-2-fundamental-acceleration-v1
-design.md`` pre-registered.

PIT SEMANTICS, ASSERTED NOT ASSUMED
------------------------------------
``FundamentalStore._records[ticker]`` is already sorted ascending by
``available_from`` at construction (``FundamentalStore.__init__``). A
candidate's CURRENT filing is the one with the latest REPORT PERIOD among
all filings visible (``available_from <= as_of``) -- not simply the one
with the latest ``available_from`` -- because a severely delayed filing can
in principle arrive out of period order; ordering by fiscal period after
filtering to the visible set is the conservative reading. The PREVIOUS
filing must be the one immediately preceding it in the region's own fixed
report-code sequence (strict one-step adjacency, same fiscal year, or the
prior year's final period rolling into the new year's first) -- a
non-consecutive gap (a skipped quarter) is reported as ``NOT_CONSECUTIVE``
and contributes no acceleration reading, never a value computed across the
gap.

Both legs are asserted (not merely assumed) to satisfy
``available_from <= as_of`` -- automatically true once the current filing
itself clears the PIT gate, since it is chosen from the same visible-filtered
set, but the assertion is explicit rather than implicit, exactly as
``contraction_holds`` is asserted for the confidence weight in
``alpha_reliability.py``.

AMENDMENTS/RESTATEMENTS
------------------------
Grouped by ``report_period`` among VISIBLE filings only, keeping the
max-``available_from`` record per period group (the latest restatement that
had actually become visible by ``as_of``) before chronological period
ordering. Measured directly against the real sealed ledger
(``pit-kr.jsonl``, ``pit-us.jsonl``): zero duplicate ``(ticker,
reportPeriod)`` filings exist in either region (0 of 4,302 KR keys, 0 of
33,832 US keys) as of this study, so this resolution step is a required
defensive-correctness guarantee, exercised by synthetic fixtures in the test
suite, and changes no real historical-discovery number on this ledger.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass

import pandas as pd

from . import pit_data

VERSION = "fundamental-acceleration-v1"

PRIMARY_FIELDS = ("roe", "operatingMargin", "profitMargin", "earningsGrowth")
DIAGNOSTIC_FIELDS = ("debtToEquity",)
ALL_FIELDS = PRIMARY_FIELDS + DIAGNOSTIC_FIELDS
MIN_PRIMARY_FIELDS = 3
WINSOR = 2.5

# Region-specific canonical report-period ordering. Index is the position in
# one fiscal year's filing cadence; consecutiveness is defined purely on this
# index plus the fiscal year, never inferred per company.
ORDER_INDEX: dict[str, dict[str, int]] = {
    "US": {"Q1": 0, "Q2": 1, "Q3": 2, "FY": 3},
    "KR": {"11013": 0, "11012": 1, "11014": 2, "11011": 3},
}

NO_FILING_VISIBLE = "NO_FILING_VISIBLE"
NO_PREVIOUS_FILING = "NO_PREVIOUS_FILING"
NOT_CONSECUTIVE = "NOT_CONSECUTIVE"
UNPARSEABLE_PERIOD = "UNPARSEABLE_PERIOD"
OK = "OK"


def parse_report_period(report_period: str, region: str) -> tuple[int, int] | None:
    """``"2019-11014"`` (KR) / ``"2019-Q3"`` (US) -> ``(fiscal_year, order_index)``.

    ``None`` when the region's code table does not recognise the code, or the
    string does not split into exactly a year and a code.
    """
    order = ORDER_INDEX.get(region)
    if not order or not report_period:
        return None
    parts = str(report_period).rsplit("-", 1)
    if len(parts) != 2:
        return None
    year_part, code = parts
    try:
        year = int(year_part)
    except ValueError:
        return None
    idx = order.get(code)
    if idx is None:
        return None
    return year, idx


def is_consecutive(previous: tuple[int, int], current: tuple[int, int]) -> bool:
    """Strict one-step adjacency: same year at idx+1, or the prior year's
    final period (idx 3) rolling into the new year's first period (idx 0).
    A skipped period (e.g. KR Q1 -> Q3 with no half-year filing) is NOT
    consecutive -- deliberately conservative, per this study's own design.
    """
    prev_year, prev_idx = previous
    curr_year, curr_idx = current
    if curr_year == prev_year and curr_idx == prev_idx + 1:
        return True
    return curr_year == prev_year + 1 and prev_idx == 3 and curr_idx == 0


@dataclass(frozen=True)
class FilingPair:
    status: str
    current: pit_data.FundamentalRecord | None = None
    previous: pit_data.FundamentalRecord | None = None


def _visible_slice(records: list[pit_data.FundamentalRecord], as_of) -> list[pit_data.FundamentalRecord]:
    """``records`` is pre-sorted ascending by ``available_from``
    (``FundamentalStore.__init__``); binary-search the cutoff rather than a
    linear scan."""
    if not records:
        return []
    cutoff = str(pd.Timestamp(as_of).normalize().date())
    stamps = [str(pd.Timestamp(r.available_from).normalize().date()) for r in records]
    idx = bisect_right(stamps, cutoff)
    return records[:idx]


def resolve_filing_pair(store: pit_data.FundamentalStore, ticker: str, region: str, as_of) -> FilingPair:
    """The current filing and its immediately preceding CONSECUTIVE filing,
    both PIT-visible as of ``as_of``, with amendments resolved.
    """
    records = store._records.get(ticker) or []  # noqa: SLF001 -- see module docstring
    visible = _visible_slice(records, as_of)
    if not visible:
        return FilingPair(NO_FILING_VISIBLE)

    # Amendment resolution: among VISIBLE filings, keep only the
    # max-available_from record per reportPeriod.
    latest_per_period: dict[str, pit_data.FundamentalRecord] = {}
    for record in visible:
        existing = latest_per_period.get(record.report_period)
        if existing is None or str(record.available_from) > str(existing.available_from):
            latest_per_period[record.report_period] = record

    parsed: list[tuple[tuple[int, int], pit_data.FundamentalRecord]] = []
    for record in latest_per_period.values():
        key = parse_report_period(record.report_period, region)
        if key is not None:
            parsed.append((key, record))
    if not parsed:
        return FilingPair(UNPARSEABLE_PERIOD)
    parsed.sort(key=lambda item: item[0])

    current_key, current = parsed[-1]
    for record in visible:
        # The current filing must itself have been visible unmodified --
        # asserted explicitly rather than assumed, per this module's own
        # docstring.
        if record is current and not record.visible_on(as_of):
            raise AssertionError(f"current filing for {ticker} not actually PIT-visible")

    if len(parsed) < 2:
        return FilingPair(NO_PREVIOUS_FILING, current=current)
    previous_key, previous = parsed[-2]
    if not previous.visible_on(as_of):
        raise AssertionError(f"previous filing for {ticker} not actually PIT-visible")
    if not is_consecutive(previous_key, current_key):
        return FilingPair(NOT_CONSECUTIVE, current=current, previous=previous)
    return FilingPair(OK, current=current, previous=previous)


def compute_deltas(current: pit_data.FundamentalRecord, previous: pit_data.FundamentalRecord) -> dict[str, float | None]:
    """``f(current) - f(previous)`` per field; ``None`` when either leg lacks
    the field. A missing prior value is never treated as zero."""
    deltas: dict[str, float | None] = {}
    for field in ALL_FIELDS:
        cur = current.fields.get(field)
        prev = previous.fields.get(field)
        if cur is None or prev is None:
            deltas[field] = None
            continue
        try:
            deltas[field] = float(cur) - float(prev)
        except (TypeError, ValueError):
            deltas[field] = None
    return deltas


def acceleration_reading(store: pit_data.FundamentalStore, ticker: str, region: str, as_of) -> dict:
    """One name-date's full acceleration reading: status, filing identifiers
    and raw per-field deltas. The composite z-score is NOT computed here --
    that is a cross-sectional operation over many readings, done by the
    discovery/sealing callers.
    """
    pair = resolve_filing_pair(store, ticker, region, as_of)
    deltas = compute_deltas(pair.current, pair.previous) if pair.status == OK else dict.fromkeys(ALL_FIELDS)
    primary_present = sum(1 for f in PRIMARY_FIELDS if deltas.get(f) is not None) if pair.status == OK else 0
    return {
        "ticker": ticker,
        "region": region,
        "asOf": str(pd.Timestamp(as_of).normalize().date()),
        "status": pair.status,
        "currentReportPeriod": pair.current.report_period if pair.current else None,
        "currentAvailableFrom": pair.current.available_from if pair.current else None,
        "previousReportPeriod": pair.previous.report_period if pair.previous else None,
        "previousAvailableFrom": pair.previous.available_from if pair.previous else None,
        "deltas": deltas,
        "primaryFieldsPresent": primary_present,
        "dataSufficient": pair.status == OK and primary_present >= MIN_PRIMARY_FIELDS,
    }
