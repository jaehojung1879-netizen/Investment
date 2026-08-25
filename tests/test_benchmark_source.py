"""Regression tests for the benchmark failures that actually happened.

Each test here reproduces a shape observed in production, not a hypothesis:

* ``one_row``      — what ``^KS200`` returned on 08-24 and 08-25.
* ``shifted``      — the calendar-mixing story the previous fix assumed; kept
                     because it is still a real way to lose exact-session joins.
* ``partial``      — a vendor that drops part of the history but not all of it.

The previous round of tests asserted that ``ignore_tz`` was passed and that the
benchmark was fetched in its own batch. Both were true, both shipped, and the
next run still failed — because neither statement is about the failure. A test
that cannot fail on the observed defect is not covering it.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pipeline import benchmark_source as BS
from pipeline import historical_outcomes as outcomes


FULL = pd.bdate_range("2013-01-01", "2026-08-24")


def _series(index, base=100.0):
    return pd.Series(np.linspace(base, base * 2, len(index)), index=index, dtype=float)


def _fetchers(**by_symbol):
    """Build a fetcher table from {symbol: series-or-None} per source kind."""
    def make(kind):
        def fetch(symbol, start):
            return by_symbol.get(f"{kind}:{symbol}")
        return fetch
    return {kind: make(kind) for kind in ("yahoo", "fdr")}


# --------------------------------------------------------------------------- #
# Plausibility
# --------------------------------------------------------------------------- #
def test_one_row_vendor_response_is_rejected_not_accepted_as_history():
    """The 08-24 failure: 1 session offered in place of thirteen years."""
    one_row = _series(pd.DatetimeIndex(["2026-08-24"]))

    verdict = BS.evaluate_candidate(one_row, None, start="2013-01-01")

    assert verdict["accepted"] is False
    assert verdict["reason"] == "implausibly_short_for_requested_span"
    assert verdict["sessions"] == 1
    assert verdict["minimumSessions"] > 1000


def test_one_row_response_is_rejected_even_against_a_known_calendar():
    """Bounding the window at the candidate's last session must not excuse it."""
    verdict = BS.evaluate_candidate(
        _series(pd.DatetimeIndex(["2026-08-24"])), _series(FULL), start="2013-01-01")

    assert verdict["accepted"] is False
    assert verdict["reason"] == "below_known_session_calendar"
    assert verdict["snapshotCoveragePct"] == pytest.approx(0.0, abs=0.03)


def test_a_vendor_merely_a_day_behind_is_still_accepted():
    """A source that has not published today yet is late, not broken."""
    behind = _series(FULL[:-1])

    verdict = BS.evaluate_candidate(behind, _series(FULL), start="2013-01-01")

    assert verdict["accepted"] is True
    assert verdict["snapshotCoveragePct"] == 100.0


def test_a_vendor_that_dropped_a_third_of_history_is_rejected():
    partial = _series(FULL[len(FULL) // 3:])

    verdict = BS.evaluate_candidate(partial, _series(FULL), start="2013-01-01")

    assert verdict["accepted"] is False
    assert verdict["reason"] == "below_known_session_calendar"
    assert verdict["snapshotCoveragePct"] < 70.0


def test_a_single_halted_session_does_not_reject_a_good_panel():
    gapped = _series(FULL).drop(FULL[500])

    verdict = BS.evaluate_candidate(gapped, _series(FULL), start="2013-01-01")

    assert verdict["accepted"] is True


# --------------------------------------------------------------------------- #
# Source resolution
# --------------------------------------------------------------------------- #
def test_second_vendor_rescues_a_truncated_first_vendor(tmp_path):
    fetchers = _fetchers(**{
        "yahoo:^KS200": _series(pd.DatetimeIndex(["2026-08-25"])),
        "fdr:KS200": _series(FULL),
    })

    series, diagnostics = BS.resolve(
        {"KR": "^KS200"}, {"^KS200": [{"kind": "yahoo", "symbol": "^KS200"},
                                      {"kind": "fdr", "symbol": "KS200"}]},
        start="2013-01-01", ledger_dir=tmp_path, fetchers=fetchers)

    assert len(series["^KS200"]) == len(FULL)
    row = diagnostics["byRegion"]["KR"]
    assert row["status"] == BS.STATUS_VENDOR
    assert row["source"] == "fdr"
    assert [c["accepted"] for c in row["candidates"]] == [False, True]
    assert diagnostics["degradedRegions"] == []


def test_every_vendor_down_falls_back_to_the_committed_snapshot(tmp_path):
    good = _fetchers(**{"yahoo:^KS200": _series(FULL)})
    BS.resolve({"KR": "^KS200"}, None, start="2013-01-01",
               ledger_dir=tmp_path, fetchers=good)

    # Next night the vendor offers one row, exactly as on 08-24.
    broken = _fetchers(**{"yahoo:^KS200": _series(pd.DatetimeIndex(["2026-08-25"]))})
    series, diagnostics = BS.resolve(
        {"KR": "^KS200"}, None, start="2013-01-01",
        ledger_dir=tmp_path, fetchers=broken)

    assert len(series["^KS200"]) == len(FULL)          # a decade, not one row
    assert diagnostics["byRegion"]["KR"]["status"] == BS.STATUS_SNAPSHOT
    assert diagnostics["degradedRegions"] == ["KR"]
    assert diagnostics["snapshotsUpdated"] == []       # an outage never shortens it


def test_no_vendor_and_no_snapshot_is_unavailable_never_a_substitute(tmp_path):
    series, diagnostics = BS.resolve(
        {"KR": "^KS200"}, None, start="2013-01-01", ledger_dir=tmp_path,
        fetchers=_fetchers())

    assert series == {}
    assert diagnostics["byRegion"]["KR"]["status"] == BS.STATUS_UNAVAILABLE
    assert diagnostics["unavailableRegions"] == ["KR"]


def test_an_accepted_series_is_used_alone_never_stitched_to_the_snapshot(tmp_path):
    """One adjustment vintage per published series.

    Adjusted closes are rescaled retroactively on every dividend, so splicing a
    fresh fetch onto stored history puts two adjustment factors in one series
    and every return across the join is wrong.
    """
    BS.resolve({"US": "SPY"}, None, start="2013-01-01", ledger_dir=tmp_path,
               fetchers=_fetchers(**{"yahoo:SPY": _series(FULL, base=100.0)}))

    rescaled = _series(FULL, base=137.0).drop(FULL[10])
    series, _ = BS.resolve(
        {"US": "SPY"}, None, start="2013-01-01", ledger_dir=tmp_path,
        fetchers=_fetchers(**{"yahoo:SPY": rescaled}))

    assert len(series["SPY"]) == len(rescaled)
    assert FULL[10] not in series["SPY"].index      # not back-filled from storage
    assert float(series["SPY"].iloc[0]) == pytest.approx(137.0)


# --------------------------------------------------------------------------- #
# Snapshot storage
# --------------------------------------------------------------------------- #
def test_snapshot_round_trips_and_is_byte_stable(tmp_path):
    original = _series(FULL)

    assert BS.write_snapshot(tmp_path, "^KS200", original) is True
    assert BS.write_snapshot(tmp_path, "^KS200", original) is False  # no git churn

    restored = BS.read_snapshot(tmp_path, "^KS200")
    assert len(restored) == len(original)
    assert restored.index.equals(original.index)
    assert float(restored.iloc[-1]) == pytest.approx(float(original.iloc[-1]))


def test_distinct_tickers_never_share_a_snapshot_file(tmp_path):
    assert BS.snapshot_path(tmp_path, "^KS200") != BS.snapshot_path(tmp_path, "KS200")


def test_snapshot_index_carries_no_timestamp(tmp_path):
    """An unchanged snapshot must not produce a diff every night."""
    fetchers = _fetchers(**{"yahoo:^KS200": _series(FULL)})
    BS.resolve({"KR": "^KS200"}, None, start="2013-01-01",
               ledger_dir=tmp_path, fetchers=fetchers)
    first = (BS.snapshot_root(tmp_path) / BS.SNAPSHOT_INDEX).read_bytes()

    BS.resolve({"KR": "^KS200"}, None, start="2013-01-01",
               ledger_dir=tmp_path, fetchers=fetchers)

    assert (BS.snapshot_root(tmp_path) / BS.SNAPSHOT_INDEX).read_bytes() == first


# --------------------------------------------------------------------------- #
# Determinism, end to end
# --------------------------------------------------------------------------- #
def test_outcomes_survive_a_vendor_outage_unchanged(tmp_path):
    """The property the whole module exists for.

    On 08-19 and 08-20 the same commit produced 452/452 and then 0/452 KR
    benchmark coverage. With a snapshot on record, the second night must
    reproduce the first night's numbers.
    """
    stock_dates = pd.bdate_range("2013-01-01", "2026-08-24")
    prices = {"005930.KS": pd.DataFrame({"Close": _series(stock_dates, base=50.0)})}
    signals = [{"id": "s1", "date": "2015-06-01", "ticker": "005930.KS",
                "region": "KR", "benchmark": "^KS200"}]

    good = _fetchers(**{"yahoo:^KS200": _series(FULL)})
    series, _ = BS.resolve({"KR": "^KS200"}, None, start="2013-01-01",
                           ledger_dir=tmp_path, fetchers=good)
    first = outcomes.compute_outcomes(signals, prices, {"^KS200": series["^KS200"]})

    outage = _fetchers(**{"yahoo:^KS200": _series(pd.DatetimeIndex(["2026-08-25"]))})
    series, diagnostics = BS.resolve({"KR": "^KS200"}, None, start="2013-01-01",
                                     ledger_dir=tmp_path, fetchers=outage)
    second = outcomes.compute_outcomes(signals, prices, {"^KS200": series["^KS200"]})

    assert diagnostics["byRegion"]["KR"]["status"] == BS.STATUS_SNAPSHOT
    assert first == second
    assert first[0]["horizons"]["126"]["excessReturn"] is not None


def test_preflight_passes_on_the_snapshot_that_a_broken_vendor_would_have_failed(tmp_path):
    stock_dates = pd.bdate_range("2013-01-01", "2026-08-24")
    good = _fetchers(**{"yahoo:^KS200": _series(FULL)})
    BS.resolve({"KR": "^KS200"}, None, start="2013-01-01",
               ledger_dir=tmp_path, fetchers=good)

    outage = _fetchers(**{"yahoo:^KS200": _series(pd.DatetimeIndex(["2026-08-25"]))})
    series, _ = BS.resolve({"KR": "^KS200"}, None, start="2013-01-01",
                           ledger_dir=tmp_path, fetchers=outage)

    prices = {"005930.KS": pd.DataFrame({"Close": _series(stock_dates, base=50.0)}),
              "^KS200": pd.DataFrame({"Close": series["^KS200"]})}
    result = outcomes.benchmark_session_preflight(
        prices, {"KR": ["005930.KS"]}, {"KR": "^KS200"},
        start="2014-01-01", horizon=126, min_history_rows=273)

    assert result["eligible"] is True
    assert result["regions"]["KR"]["coveragePct"] == 100.0


# --------------------------------------------------------------------------- #
# Coverage history
# --------------------------------------------------------------------------- #
def test_coverage_history_makes_a_collapse_a_one_line_diff(tmp_path):
    def row(pct):
        return {"signalsByRegion": {"KR": 100},
                "benchmarkCoverageByRegion": {"KR": {"126": {
                    "coveragePct": pct, "matchedBenchmarkReturns": int(pct),
                    "maturedAbsoluteReturns": 100}}}}

    BS.record_coverage(tmp_path, run_date="2026-08-19", horizon=126,
                       coverage=row(100.0), benchmark_diagnostics={})
    history = BS.record_coverage(tmp_path, run_date="2026-08-20", horizon=126,
                                 coverage=row(0.0), benchmark_diagnostics={})

    regression = BS.coverage_regression(history, region="KR")
    assert regression["dropPctPoints"] == 100.0
    assert regression["previousDate"] == "2026-08-19"
    assert BS.coverage_regression(history, region="US") is None


def test_rerunning_the_same_day_replaces_rather_than_duplicates(tmp_path):
    def row(pct):
        return {"signalsByRegion": {"US": 10},
                "benchmarkCoverageByRegion": {"US": {"126": {"coveragePct": pct}}}}

    BS.record_coverage(tmp_path, run_date="2026-08-20", horizon=126,
                       coverage=row(10.0), benchmark_diagnostics={})
    history = BS.record_coverage(tmp_path, run_date="2026-08-20", horizon=126,
                                 coverage=row(99.0), benchmark_diagnostics={})

    assert len(history) == 1
    assert history[0]["coveragePct"] == 99.0
