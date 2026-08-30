"""The parts of the KR delisting-coverage measurement that must not need a vendor.

The measurement itself is a network job that only CI can run. What can be
pinned here is everything that decides what the resulting number MEANS: which
names belong in the denominator, how the sample is drawn, and an interval that
stays inside [0, 1] at the extremes this measurement is expected to land on.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "measure_kr_delisting_coverage", ROOT / "scripts" / "measure_kr_delisting_coverage.py")
M = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = M
_spec.loader.exec_module(M)


def _listing(rows):
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# The denominator
# --------------------------------------------------------------------------- #
def test_names_gone_before_the_replay_began_are_not_a_gap():
    """3,010 is every KRX delisting since 1960, not the replay's need.

    A name that stopped trading in 1998 was never in a cross-section the replay
    builds, so it cannot be missing from one. Counting it would understate
    coverage against a need that does not exist.
    """
    rows = M.candidates(_listing([
        {"Symbol": "000001", "DelistingDate": "1998-04-02", "Market": "KOSPI"},
        {"Symbol": "000002", "DelistingDate": "2017-06-15", "Market": "KOSPI"},
    ]), "2013-01-01")

    assert [r["inReplayWindow"] for r in rows] == [False, True]


def test_a_name_delisted_on_the_replay_start_is_in_the_window():
    rows = M.candidates(_listing([
        {"Symbol": "000003", "DelistingDate": "2013-01-01", "Market": "KOSPI"}]),
        "2013-01-01")
    assert rows[0]["inReplayWindow"] is True


def test_non_numeric_and_undated_rows_are_dropped():
    rows = M.candidates(_listing([
        {"Symbol": "KOSPI200", "DelistingDate": "2017-01-01", "Market": "KOSPI"},
        {"Symbol": "000004", "DelistingDate": "nan", "Market": "KOSPI"},
        {"Symbol": "000005", "DelistingDate": "2017-01-01", "Market": "KOSPI"},
    ]), "2013-01-01")

    assert [r["symbol"] for r in rows] == ["000005"]


def test_the_column_names_are_matched_case_and_underscore_insensitively():
    """The vendor's listing has changed shape before; a rename must not read as zero."""
    rows = M.candidates(_listing([
        {"code": "000006", "delisting_date": "2019-03-03", "exchange": "KOSDAQ"}]),
        "2013-01-01")
    assert rows[0]["symbol"] == "000006"
    assert rows[0]["market"] == "KOSDAQ"


def test_unexpected_columns_report_rather_than_return_a_confident_zero():
    assert M.candidates(_listing([{"nope": 1, "still_nope": 2}]), "2013-01-01") == []


# --------------------------------------------------------------------------- #
# The sample
# --------------------------------------------------------------------------- #
def test_the_sample_is_stratified_so_no_era_can_dominate():
    """The need is front-loaded; a sample of recent delistings reports a
    coverage the early cross-sections never see."""
    rows = ([{"symbol": f"a{i}", "year": 2013, "delisted": "2013-05-05"} for i in range(90)]
            + [{"symbol": f"b{i}", "year": 2024, "delisted": "2024-05-05"} for i in range(10)])

    picked = M.stratified(rows, 20, seed=11)
    years = [r["year"] for r in picked]

    assert len(picked) == 20
    assert 2013 in years and 2024 in years
    # Proportional, not equal: 90/10 in the population.
    assert years.count(2024) <= 5


def test_a_sample_larger_than_the_population_returns_everything():
    rows = [{"symbol": "a", "year": 2013, "delisted": "2013-01-01"}]
    assert M.stratified(rows, 150, seed=11) == rows


def test_the_sample_is_reproducible_from_the_seed():
    rows = [{"symbol": f"a{i}", "year": 2013 + i % 5, "delisted": "2015-01-01"}
            for i in range(60)]
    assert ([r["symbol"] for r in M.stratified(rows, 20, seed=7)]
            == [r["symbol"] for r in M.stratified(rows, 20, seed=7)])


# --------------------------------------------------------------------------- #
# The interval
# --------------------------------------------------------------------------- #
def test_the_interval_survives_zero_successes():
    """Where this measurement is expected to land. A normal interval returns
    a width of zero here, which would read as certainty."""
    low, high = M.wilson(0, 150)
    assert low == 0.0
    assert high > 0.0


def test_the_interval_stays_inside_the_unit_range_at_both_extremes():
    for successes, trials in ((0, 30), (30, 30), (1, 200)):
        low, high = M.wilson(successes, trials)
        assert 0.0 <= low <= high <= 100.0


def test_no_trials_is_no_interval_rather_than_a_fabricated_one():
    assert M.wilson(0, 0) is None


def test_the_interval_narrows_as_the_sample_grows():
    narrow = M.wilson(50, 500)
    wide = M.wilson(5, 50)
    assert (narrow[1] - narrow[0]) < (wide[1] - wide[0])


# --------------------------------------------------------------------------- #
# What "usable" means
# --------------------------------------------------------------------------- #
def test_usable_is_the_replays_own_bar_not_merely_a_returned_frame():
    """A delisted name whose history starts three months before it died is
    useless to the replay however complete the frame looks."""
    from pipeline.longterm import MIN_HISTORY

    assert M.MIN_HISTORY == MIN_HISTORY == 273


def test_the_summary_reports_both_vendors_per_bucket():
    results = [
        {"year": 2013, "market": "KOSPI", "fdrUsable": True, "yahooUsable": False},
        {"year": 2013, "market": "KOSPI", "fdrUsable": False, "yahooUsable": False},
        {"year": 2020, "market": "KOSDAQ", "fdrUsable": True, "yahooUsable": True},
    ]
    by_year = M.summarise(results, lambda r: r["year"])

    assert by_year["2013"]["tested"] == 2
    assert by_year["2013"]["fdrUsablePct"] == 50.0
    assert by_year["2013"]["yahooUsablePct"] == 0.0
    assert by_year["2020"]["fdrUsablePct"] == 100.0
    assert by_year["2013"]["fdrUsableCI"] is not None


# --------------------------------------------------------------------------- #
# The market filter
#
# The first real run pooled markets and reported 53.33% where KOSPI alone —
# the only list `universe.resolve` screens — was 34.55%. The pooled figure sat
# above the ~50% decision threshold and the real one sat entirely below it, so
# the headline answered the question with the opposite sign.
# --------------------------------------------------------------------------- #
def test_the_replay_market_is_the_one_the_universe_is_drawn_from():
    """If `universe.resolve` ever screens a different list this must move with it."""
    source = (ROOT / "pipeline" / "universe.py").read_text(encoding="utf-8")
    assert f'StockListing("{M.REPLAY_MARKET}")' in source


def test_other_markets_are_context_not_denominator():
    rows = M.candidates(_listing([
        {"Symbol": "000010", "DelistingDate": "2017-01-01", "Market": "KOSPI"},
        {"Symbol": "000011", "DelistingDate": "2017-01-01", "Market": "KOSDAQ"},
        {"Symbol": "000012", "DelistingDate": "2017-01-01", "Market": "KONEX"},
    ]), "2013-01-01")

    on_market = [r for r in rows
                 if (r["market"] or "").upper() == M.REPLAY_MARKET]

    assert [r["symbol"] for r in on_market] == ["000010"]
    assert len(rows) == 3, "the others are still read, just not counted"


def test_the_pooled_and_market_figures_can_disagree_about_the_decision():
    """The exact shape of the first run, in miniature.

    Two markets, one of them irrelevant and much better served. Pooled clears a
    50% bar; the market the replay screens does not.
    """
    results = ([{"market": "KOSPI", "fdrUsable": False, "yahooUsable": False}] * 13
               + [{"market": "KOSPI", "fdrUsable": True, "yahooUsable": False}] * 7
               + [{"market": "KOSDAQ", "fdrUsable": True, "yahooUsable": False}] * 20)
    by_market = M.summarise(results, lambda r: r["market"])
    pooled = M.summarise(results, lambda r: "ALL")

    assert by_market["KOSPI"]["fdrUsablePct"] == 35.0
    assert pooled["ALL"]["fdrUsablePct"] == 67.5
    assert by_market["KOSPI"]["fdrUsablePct"] < 50 < pooled["ALL"]["fdrUsablePct"]
