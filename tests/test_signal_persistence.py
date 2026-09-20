"""Smoothing must look backward only, and the diagnostic must pair within a date.

Two ways this study could fool itself. A smoother that reached forward would
hand the ranking information it did not have, and would do it invisibly — the
path would simply look better. And an ADDED-versus-RETAINED comparison pooled
across dates would measure which months were kind rather than which names the
ranking had just picked. Both are tested here rather than asserted in prose.
"""
from __future__ import annotations

import numpy as np
import pytest

from pipeline import signal_persistence as SP


# --------------------------------------------------------------------------- #
# PercentileSmoother
# --------------------------------------------------------------------------- #
def test_the_window_averages_only_what_has_already_been_observed():
    smoother = SP.PercentileSmoother(3)
    smoother.observe("A", 90.0, "2020-01-01")
    assert smoother.smoothed("A", 90.0) == pytest.approx(90.0)
    smoother.observe("A", 60.0, "2020-02-01")
    assert smoother.smoothed("A", 60.0) == pytest.approx(75.0)
    smoother.observe("A", 30.0, "2020-03-01")
    assert smoother.smoothed("A", 30.0) == pytest.approx(60.0)


def test_the_window_forgets_beyond_k_blocks():
    smoother = SP.PercentileSmoother(2)
    for date, value in (("2020-01-01", 0.0), ("2020-02-01", 100.0), ("2020-03-01", 100.0)):
        smoother.observe("A", value, date)
    # The 0.0 has fallen out of a two-block window.
    assert smoother.smoothed("A", 100.0) == pytest.approx(100.0)
    assert smoother.depth("A") == 2


def test_a_name_seen_for_the_first_time_gets_its_raw_percentile():
    """The smoother never invents history, so k=1 and k=6 agree on a new name."""
    smoother = SP.PercentileSmoother(6)
    assert smoother.smoothed("NEW", 77.0) == 77.0
    assert smoother.depth("NEW") == 0


def test_replaying_a_block_cannot_double_count_it():
    """`run_rung` presents each block once, but a re-presented one must be inert."""
    smoother = SP.PercentileSmoother(3)
    smoother.observe("A", 90.0, "2020-01-01")
    smoother.observe("A", 90.0, "2020-01-01")
    smoother.observe("A", 30.0, "2020-02-01")
    assert smoother.depth("A") == 2
    assert smoother.smoothed("A", 30.0) == pytest.approx(60.0)


def test_a_name_that_leaves_the_pool_and_returns_keeps_its_own_history():
    """The question is how noisy the ranking is about a company, not how
    recently the screen happened to surface it."""
    smoother = SP.PercentileSmoother(3)
    smoother.observe("A", 100.0, "2020-01-01")
    smoother.observe("B", 0.0, "2020-02-01")          # A absent this block
    smoother.observe("A", 0.0, "2020-03-01")
    assert smoother.smoothed("A", 0.0) == pytest.approx(50.0)


def test_a_missing_percentile_is_skipped_rather_than_counted_as_zero():
    smoother = SP.PercentileSmoother(3)
    smoother.observe("A", 80.0, "2020-01-01")
    smoother.observe("A", None, "2020-02-01")
    smoother.observe("A", float("nan"), "2020-03-01")
    assert smoother.depth("A") == 1
    assert smoother.smoothed("A", None) == pytest.approx(80.0)


def test_a_window_below_one_block_is_refused():
    with pytest.raises(ValueError):
        SP.PercentileSmoother(0)


# --------------------------------------------------------------------------- #
# smoothed_candidates
# --------------------------------------------------------------------------- #
def test_scoring_and_selection_are_handed_the_same_number():
    """Ranking on a smoothed percentile while capping on the raw one would rank
    names by one quantity and constrain them by another, invisibly."""
    smoother = SP.PercentileSmoother(2)
    first = [{"ticker": "A", "region": "US", "alphaPercentile": 100.0}]
    SP.smoothed_candidates(first, smoother, "2020-01-01")
    second = SP.smoothed_candidates(
        [{"ticker": "A", "region": "US", "alphaPercentile": 0.0}], smoother, "2020-02-01")

    assert second[0]["alphaPercentile"] == pytest.approx(50.0)
    assert second[0]["rawAlphaPercentile"] == 0.0
    assert second[0]["smoothingDepth"] == 2


def test_the_original_candidate_rows_are_not_mutated():
    """The contexts are shared across rungs; a rung that edited them in place
    would silently contaminate every rung after it."""
    smoother = SP.PercentileSmoother(3)
    original = [{"ticker": "A", "region": "US", "alphaPercentile": 90.0}]
    SP.smoothed_candidates(original, smoother, "2020-01-01")
    assert original[0]["alphaPercentile"] == 90.0
    assert "rawAlphaPercentile" not in original[0]


def test_a_one_block_window_reproduces_the_raw_percentile_exactly():
    """k=1 is the control, so it must be the production ranking untouched."""
    smoother = SP.PercentileSmoother(SP.WINDOW[SP.LATEST])
    rows = SP.smoothed_candidates(
        [{"ticker": "A", "region": "US", "alphaPercentile": 73.0}], smoother, "2020-01-01")
    assert rows[0]["alphaPercentile"] == pytest.approx(73.0)


# --------------------------------------------------------------------------- #
# incumbency_outcomes
# --------------------------------------------------------------------------- #
def _priced(date, table):
    return {date: {ticker: {"excessReturn": value} for ticker, value in table.items()}}


def test_added_and_retained_are_compared_within_one_rebalance():
    """Pooling across dates would measure which months were kind."""
    decisions = [
        {"date": "2020-02-01", "added": ["NEW"], "retained": ["OLD"],
         "regionByTicker": {"NEW": "US", "OLD": "US"}},
    ]
    priced = _priced("2020-02-01", {"NEW": -0.02, "OLD": 0.03})
    blob = SP.incumbency_outcomes(decisions, priced)

    assert blob["available"]
    assert blob["pairedRebalances"] == 1
    assert blob["addedMeanExcessPct"] == pytest.approx(-2.0)
    assert blob["retainedMeanExcessPct"] == pytest.approx(3.0)
    assert blob["addedMinusRetainedPct"] == pytest.approx(-5.0)


def test_a_rebalance_with_only_one_side_contributes_no_paired_observation():
    """An arrival with nothing to compare against is not a within-date difference."""
    decisions = [
        {"date": "2020-01-01", "added": ["A", "B"], "retained": [],
         "regionByTicker": {"A": "US", "B": "US"}},
        {"date": "2020-02-01", "added": ["C"], "retained": ["A"],
         "regionByTicker": {"C": "US", "A": "US"}},
    ]
    priced = {**_priced("2020-01-01", {"A": 0.10, "B": 0.10}),
              **_priced("2020-02-01", {"C": -0.01, "A": 0.01})}
    blob = SP.incumbency_outcomes(decisions, priced)

    # The initial build still contributes to the group means, but only the
    # second rebalance can produce a paired difference.
    assert blob["pairedRebalances"] == 1
    assert blob["addedMinusRetainedPct"] == pytest.approx(-2.0)


def test_a_name_the_cross_section_cannot_price_is_dropped_not_zeroed():
    decisions = [{"date": "2020-02-01", "added": ["NEW", "UNPRICED"], "retained": ["OLD"],
                  "regionByTicker": {"NEW": "US", "UNPRICED": "US", "OLD": "US"}}]
    priced = _priced("2020-02-01", {"NEW": -0.02, "OLD": 0.03})
    blob = SP.incumbency_outcomes(decisions, priced)

    assert blob["addedObservations"] == 1
    assert blob["addedMeanExcessPct"] == pytest.approx(-2.0)


def test_the_split_is_reported_per_region():
    decisions = [{"date": "2020-02-01", "added": ["USNEW", "KRNEW"],
                  "retained": ["USOLD", "KROLD"],
                  "regionByTicker": {"USNEW": "US", "KRNEW": "KR",
                                     "USOLD": "US", "KROLD": "KR"}}]
    priced = _priced("2020-02-01", {"USNEW": -0.04, "KRNEW": -0.01,
                                    "USOLD": 0.02, "KROLD": 0.01})
    blob = SP.incumbency_outcomes(decisions, priced)["byRegion"]

    assert blob["US"]["differencePct"] == pytest.approx(-6.0)
    assert blob["KR"]["differencePct"] == pytest.approx(-2.0)


def test_no_rebalance_at_all_is_unavailable_rather_than_zero():
    assert SP.incumbency_outcomes([], {})["available"] is False


# --------------------------------------------------------------------------- #
# percentile_movement
# --------------------------------------------------------------------------- #
def test_movement_measures_consecutive_appearances_of_one_name():
    contexts = {
        "s1": ([{"ticker": "A", "alphaPercentile": 90.0}], {}),
        "s2": ([{"ticker": "A", "alphaPercentile": 85.0}], {}),
        "s3": ([{"ticker": "A", "alphaPercentile": 95.0}], {}),
    }
    calendar = [{"date": f"2020-0{i}-01", "signalDate": f"s{i}"} for i in (1, 2, 3)]
    blob = SP.percentile_movement(contexts, calendar)

    assert blob["available"]
    assert blob["observations"] == 2                 # first appearance has no predecessor
    assert blob["meanAbsoluteMove"] == pytest.approx(7.5)


def test_movement_is_unavailable_when_nothing_repeats():
    contexts = {"s1": ([{"ticker": "A", "alphaPercentile": 90.0}], {})}
    calendar = [{"date": "2020-01-01", "signalDate": "s1"}]
    assert SP.percentile_movement(contexts, calendar)["available"] is False


# --------------------------------------------------------------------------- #
# Freeze manifest
# --------------------------------------------------------------------------- #
def test_the_horizon_window_is_the_forecast_span_in_blocks_not_a_swept_value():
    """126 forecast sessions / 21 sessions per block = 6."""
    assert SP.HORIZON_BLOCKS == 6
    assert SP.WINDOW[SP.SMOOTHED_6] == SP.HORIZON_BLOCKS
    assert SP.WINDOW[SP.LATEST] == 1


def test_the_ladder_carries_its_control_and_promotes_nothing():
    manifest = SP.freeze_manifest()
    assert SP.LADDER[0] == SP.LATEST
    assert manifest["hurdleApplied"] is False
    assert manifest["promotionEligible"] is False
    assert manifest["liveValidated"] is False
    assert manifest["productionChanged"] is False


def test_the_two_axis_combination_is_not_a_rung_of_the_ladder():
    """A number produced by moving two things cannot be attributed to either."""
    assert SP.COMBINED not in SP.LADDER
    assert SP.freeze_manifest()["reportedSeparately"] == SP.COMBINED


def test_run_rung_refuses_a_name_it_does_not_know():
    with pytest.raises(ValueError):
        SP.run_rung("NOT_A_RUNG", contexts={}, calibrator=None, calendar=[],
                    cfg_pf={}, valuation=None)


def test_mean_pct_reports_absence_rather_than_zero():
    assert SP._mean_pct([]) is None
    assert SP._mean_pct(np.array([0.01, 0.03])) == pytest.approx(2.0)
