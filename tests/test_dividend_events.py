"""US dividend-change events, and the TTM rollforward they actually need.

The central fact this file pins: `CommonStockDividendsPerShareDeclared` is
stated CUMULATIVE from the fiscal year start (measured on real AAPL FY2013
filings: 2, 5, 8, 11 at 90/181/272/363 days) — so reading a quarter's raw
value as that quarter's own declared dividend, rather than rolling it
forward the same way `finnhub_derive` already does for net income/revenue,
would treat Q3's nine-month total as a single quarter's dividend.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import dividend_events as DE  # noqa: E402
from pipeline import finnhub_fundamentals as FF  # noqa: E402

# quarter_stage() reads periodDays, not the form or fiscalQuarter — matching
# tests/test_finnhub_derive.py's own fixture bucket midpoints exactly.
DAYS = {FF.Q1: 90, FF.Q2: 181, FF.Q3: 273, FF.FY: 365}


def _filing(year, stage, dividend_per_share=None, available=None):
    statements = {"ic": [], "bs": [], "cf": []}
    if dividend_per_share is not None:
        statements["ic"].append({
            "concept": "us-gaap_CommonStockDividendsPerShareDeclared",
            "unit": "usd/share", "value": dividend_per_share,
            "label": "Common Stock Dividends Per Share Declared",
        })
    return {
        "id": f"AAA-{year}-{stage}", "ticker": "AAA", "fiscalYear": year,
        "form": "10-K" if stage == FF.FY else "10-Q",
        "periodDays": DAYS[stage],
        "periodEnd": f"{year}-12-31", "availableFrom": available or f"{year + 1}-02-15",
        "source": "finnhub/financials-reported", "collectedAt": "2026-09-14T00:00:00Z",
        "statements": statements,
    }


def test_per_share_amount_is_read_only_from_the_per_share_class():
    filing = _filing(2020, FF.Q1, dividend_per_share=0.5)
    assert DE._per_share_amount(filing) == 0.5


def test_per_share_amount_is_none_when_the_concept_is_absent():
    filing = _filing(2020, FF.FY, dividend_per_share=None)
    assert DE._per_share_amount(filing) is None


def test_ttm_rollforward_matches_the_measured_cumulative_pattern():
    # Mirrors the real AAPL FY2013 pattern: 2, 5, 8, 11 cumulative from the
    # fiscal year start. TTM at Q3 = FY(prior) - cum(prior, Q3) + cum(this, Q3).
    by_key = {
        (2012, FF.FY): _filing(2012, FF.FY, dividend_per_share=10.0),
        (2012, FF.Q3): _filing(2012, FF.Q3, dividend_per_share=8.0),
        (2013, FF.Q3): _filing(2013, FF.Q3, dividend_per_share=8.5),
    }
    ttm, basis = DE.trailing_twelve_months_per_share(by_key, 2013, FF.Q3)
    assert ttm == 10.0 - 8.0 + 8.5
    assert basis == DE.BASIS_ROLLFORWARD


def test_ttm_is_the_annual_figure_outright_for_an_fy_filing():
    by_key = {(2013, FF.FY): _filing(2013, FF.FY, dividend_per_share=11.0)}
    ttm, basis = DE.trailing_twelve_months_per_share(by_key, 2013, FF.FY)
    assert ttm == 11.0
    assert basis == DE.BASIS_ANNUAL


def test_ttm_is_none_without_both_prior_year_filings():
    by_key = {(2013, FF.Q3): _filing(2013, FF.Q3, dividend_per_share=8.5)}
    ttm, basis = DE.trailing_twelve_months_per_share(by_key, 2013, FF.Q3)
    assert ttm is None
    assert basis == DE.BASIS_INCOMPLETE


# --------------------------------------------------------------------------- #
# Event classification: a genuine zero-vs-positive transition, never a None
# --------------------------------------------------------------------------- #
def test_classify_initiated_and_suspended():
    assert DE.classify_change(current=1.0, prior=0.0) == DE.DIVIDEND_INITIATED
    assert DE.classify_change(current=0.0, prior=1.0) == DE.DIVIDEND_SUSPENDED
    assert DE.classify_change(current=0.0, prior=0.0) == DE.DIVIDEND_NONE


def test_classify_is_none_not_a_guess_when_either_reading_is_missing():
    assert DE.classify_change(current=None, prior=1.0) is None
    assert DE.classify_change(current=1.0, prior=None) is None


def test_classify_increase_decrease_use_the_threshold_not_any_change():
    # A change inside the threshold band is UNCHANGED, so integer-rounding
    # noise in the source (measured on the real store) is not read as a
    # policy change.
    assert DE.classify_change(current=1.01, prior=1.0) == DE.DIVIDEND_UNCHANGED
    assert DE.classify_change(current=1.10, prior=1.0) == DE.DIVIDEND_INCREASED
    assert DE.classify_change(current=0.90, prior=1.0) == DE.DIVIDEND_DECREASED


def test_build_for_ticker_skips_a_filing_with_nothing_to_compare():
    # A ticker's very first filing in the store has no prior year at all.
    records = [_filing(2020, FF.FY, dividend_per_share=2.0)]
    rows = DE.build_for_ticker(records)
    assert rows == []


def test_build_for_ticker_produces_a_classified_row_once_a_prior_exists():
    records = [
        _filing(2019, FF.FY, dividend_per_share=2.0),
        _filing(2020, FF.FY, dividend_per_share=2.2),
    ]
    rows = DE.build_for_ticker(records)
    assert len(rows) == 1
    assert rows[0]["event"] == DE.DIVIDEND_INCREASED
    assert rows[0]["ticker"] == "AAA"


def test_coverage_counts_events_by_label_not_a_single_number():
    rows = [{"event": DE.DIVIDEND_INCREASED}, {"event": DE.DIVIDEND_INCREASED},
            {"event": DE.DIVIDEND_UNCHANGED}]
    report = DE.coverage(rows)
    assert report["eventCounts"][DE.DIVIDEND_INCREASED] == 2
    assert report["eventCounts"][DE.DIVIDEND_UNCHANGED] == 1
