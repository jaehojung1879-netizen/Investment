"""The cost hurdle has to reflect what the strategy actually does.

`estimate_transaction_cost` multiplies a round trip by an assumed turnover, and
the result is subtracted from every candidate's expected return before Kelly
sizes it (`net = raw - cost`, kelly_portfolio). config.json assumed 25%. The
replay measured 59.3% for the production selector at the 63-day horizon — the
same frequency `rebalanceDays` names — so the hurdle every candidate cleared
was 42% of the real one, and each one was sized against the shortfall.

Replacing 25 with 59.3 would only be a better guess. The replay already
measures it, so the measurement is used and its provenance is published.
"""
from __future__ import annotations

import pytest

from pipeline import kelly_portfolio as KP


BASE = {"horizonDays": 126,
        "transactionCosts": {
            "US": {"commissionBps": 5, "sellTaxBps": 3, "spreadBps": 10,
                   "assumedTurnoverPct": 25, "rebalanceDays": 63},
            "KR": {"commissionBps": 5, "sellTaxBps": 20, "spreadBps": 12,
                   "assumedTurnoverPct": 25, "rebalanceDays": 63}}}


def _report(turnover, *, horizon="63", selector=KP.SELECTION_METHOD,
            available=True):
    return {"portfolioReplay": {"selectors": {selector: {"horizons": {
        horizon: {"path": {"available": available,
                           "averageTurnoverPct": turnover}}}}}}}


# --------------------------------------------------------------------------- #
# Reading the measurement
# --------------------------------------------------------------------------- #
def test_the_measured_turnover_replaces_the_assumption():
    value, source, _ = KP.measured_turnover_pct(_report(59.33), BASE)

    assert value == pytest.approx(59.33)
    assert source == KP.TURNOVER_MEASURED


def test_the_horizon_must_match_the_rebalance_frequency():
    """A 21-day path turns over less per rebalance and a 252-day path more.

    Taking whichever horizon happened to mature would make the cost hurdle a
    function of the ledger's maturity rather than of the strategy.
    """
    value, source, detail = KP.measured_turnover_pct(
        _report(48.42, horizon="21"), BASE)

    assert value is None and source == KP.TURNOVER_ASSUMED
    assert detail["turnoverNote"] == "NO_MEASURED_PATH_AT_63D"


def test_a_challenger_selectors_turnover_is_not_used():
    value, _, _ = KP.measured_turnover_pct(
        _report(48.42, selector="SOME_CHALLENGER"), BASE)

    assert value is None, "production is sized on production's own behaviour"


def test_an_unavailable_path_is_not_a_measurement():
    value, source, detail = KP.measured_turnover_pct(
        _report(None, available=False), BASE)

    assert value is None and source == KP.TURNOVER_ASSUMED
    assert "NO_MEASURED_PATH" in detail["turnoverNote"]


def test_no_report_at_all_falls_back_to_the_assumption():
    value, source, _ = KP.measured_turnover_pct(None, BASE)
    assert value is None and source == KP.TURNOVER_ASSUMED


def test_an_implausible_turnover_is_refused():
    """900% per rebalance is a different definition, not a busy quarter."""
    value, source, detail = KP.measured_turnover_pct(_report(900.0), BASE)

    assert value is None and source == KP.TURNOVER_ASSUMED
    assert detail["turnoverNote"] == "MEASURED_TURNOVER_IMPLAUSIBLE"


def test_regions_rebalancing_on_different_clocks_are_refused():
    """One portfolio-level turnover cannot describe two rebalance frequencies."""
    cfg = {"horizonDays": 126, "transactionCosts": {
        "US": dict(BASE["transactionCosts"]["US"], rebalanceDays=63),
        "KR": dict(BASE["transactionCosts"]["KR"], rebalanceDays=21)}}

    value, _, detail = KP.measured_turnover_pct(_report(59.33), cfg)

    assert value is None
    assert detail["turnoverNote"] == "REBALANCE_DAYS_DIFFER_BY_REGION"


# --------------------------------------------------------------------------- #
# Applying it
# --------------------------------------------------------------------------- #
def test_the_config_is_copied_not_mutated():
    resolved = KP.with_measured_turnover(BASE, _report(59.33))

    assert resolved["transactionCosts"]["US"]["assumedTurnoverPct"] == pytest.approx(59.33)
    assert BASE["transactionCosts"]["US"]["assumedTurnoverPct"] == 25


def test_every_region_carries_the_source():
    resolved = KP.with_measured_turnover(BASE, _report(59.33))

    for region in ("US", "KR"):
        assert resolved["transactionCosts"][region]["turnoverSource"] == KP.TURNOVER_MEASURED


def test_without_a_measurement_the_configured_value_survives():
    resolved = KP.with_measured_turnover(BASE, None)

    assert resolved["transactionCosts"]["US"]["assumedTurnoverPct"] == 25
    assert resolved["transactionCosts"]["US"]["turnoverSource"] == KP.TURNOVER_ASSUMED


# --------------------------------------------------------------------------- #
# What it does to the hurdle
# --------------------------------------------------------------------------- #
def test_the_hurdle_more_than_doubles_on_the_real_turnover():
    assumed = KP.estimate_transaction_cost({"region": "US"}, BASE)
    measured = KP.estimate_transaction_cost(
        {"region": "US"}, KP.with_measured_turnover(BASE, _report(59.33)))

    # US round trip: 5*2 commission + 10*2 spread + 3 sell tax = 33bps,
    # over 126/63 = 2 cycles.
    assert assumed["estimatedCostPct"] == pytest.approx(0.165, abs=1e-3)
    assert measured["estimatedCostPct"] == pytest.approx(0.392, abs=1e-3)
    assert measured["estimatedCost"] > assumed["estimatedCost"]


def test_the_cost_detail_says_where_the_turnover_came_from():
    detail = KP.estimate_transaction_cost(
        {"region": "KR"}, KP.with_measured_turnover(BASE, _report(59.33)))

    assert detail["turnoverSource"] == KP.TURNOVER_MEASURED
    assert detail["turnoverMeasuredAtHorizonDays"] == 63
    assert detail["assumedTurnoverPct"] == pytest.approx(59.33)


def test_an_unresolved_config_still_reports_a_source():
    """Silence would read as "measured" to anyone auditing the output."""
    detail = KP.estimate_transaction_cost({"region": "US"}, BASE)
    assert detail["turnoverSource"] == KP.TURNOVER_ASSUMED


# --------------------------------------------------------------------------- #
# Per-region turnover
#
# The sleeves do not turn over alike. Measured on the v5 replay ledger over 50
# rebalances at the 63-day horizon, the production selector replaced 85.3% of
# its US sleeve per rebalance (median 100% — more than half the time, whole)
# against 63.1% of its Korean one, while the portfolio-level figure was 58.1%.
# Both sleeves are ABOVE the portfolio figure, because the book carries cash and
# a position does not, so one number applied to both understated both.
# --------------------------------------------------------------------------- #
def _regional_report(by_region, counts, *, portfolio=58.08, horizon="63",
                     selector=KP.SELECTION_METHOD):
    return {"portfolioReplay": {"selectors": {selector: {"horizons": {
        horizon: {"path": {"available": True,
                           "averageTurnoverPct": portfolio,
                           "averageTurnoverPctByRegion": by_region,
                           "turnoverRebalancesByRegion": counts}}}}}}}


def test_each_region_gets_its_own_measured_rate():
    resolved = KP.with_measured_turnover(
        BASE, _regional_report({"US": 85.28, "KR": 63.07}, {"US": 50, "KR": 50}))
    costs = resolved["transactionCosts"]

    assert costs["US"]["assumedTurnoverPct"] == pytest.approx(85.28)
    assert costs["KR"]["assumedTurnoverPct"] == pytest.approx(63.07)
    for region in ("US", "KR"):
        assert costs[region]["turnoverSource"] == KP.TURNOVER_MEASURED_REGIONAL


def test_the_us_hurdle_rises_by_half_again_on_its_own_rate():
    """The whole point: the sleeve that churns hardest was charged the least."""
    pooled = KP.estimate_transaction_cost(
        {"region": "US"}, KP.with_measured_turnover(BASE, _report(58.08)))
    regional = KP.estimate_transaction_cost(
        {"region": "US"},
        KP.with_measured_turnover(
            BASE, _regional_report({"US": 85.28, "KR": 63.07}, {"US": 50, "KR": 50})))

    # US round trip 33bps over 126/63 = 2 cycles.
    assert pooled["estimatedCostPct"] == pytest.approx(0.383, abs=1e-3)
    assert regional["estimatedCostPct"] == pytest.approx(0.563, abs=1e-3)
    assert regional["estimatedCost"] > pooled["estimatedCost"]


def test_a_thin_regional_sample_falls_back_to_the_portfolio_rate():
    """2-3 names a side: a handful of rebalances is one swap wearing a decimal."""
    resolved = KP.with_measured_turnover(
        BASE, _regional_report({"US": 85.28, "KR": 100.0},
                               {"US": 50, "KR": 3}))
    costs = resolved["transactionCosts"]

    assert costs["US"]["assumedTurnoverPct"] == pytest.approx(85.28)
    assert costs["KR"]["assumedTurnoverPct"] == pytest.approx(58.08), "portfolio rate"
    assert costs["KR"]["turnoverSource"] == KP.TURNOVER_MEASURED
    assert costs["KR"]["turnoverNote"] == "NO_REGIONAL_MEASUREMENT_PORTFOLIO_RATE_USED"


def test_a_region_wearing_another_sleeves_rate_says_so():
    """Silence would read as its own measurement."""
    resolved = KP.with_measured_turnover(
        BASE, _regional_report({"US": 85.28}, {"US": 50}))

    assert resolved["transactionCosts"]["KR"]["turnoverNote"] == (
        "NO_REGIONAL_MEASUREMENT_PORTFOLIO_RATE_USED")
    assert resolved["transactionCosts"]["US"]["turnoverNote"] is None


def test_an_implausible_regional_rate_is_refused_like_the_portfolio_one():
    resolved = KP.with_measured_turnover(
        BASE, _regional_report({"US": 900.0, "KR": 63.07}, {"US": 50, "KR": 50}))
    costs = resolved["transactionCosts"]

    assert costs["US"]["assumedTurnoverPct"] == pytest.approx(58.08)
    assert costs["KR"]["assumedTurnoverPct"] == pytest.approx(63.07)


def test_a_challengers_regional_turnover_is_not_used():
    assert KP.measured_turnover_by_region(
        _regional_report({"US": 85.28}, {"US": 50}, selector="SOME_CHALLENGER"),
        BASE) == {}


def test_the_wrong_horizon_disqualifies_the_regional_rate_too():
    assert KP.measured_turnover_by_region(
        _regional_report({"US": 85.28}, {"US": 50}, horizon="21"), BASE) == {}


def test_regions_on_different_clocks_get_no_regional_rate_either():
    cfg = {"horizonDays": 126, "transactionCosts": {
        "US": dict(BASE["transactionCosts"]["US"], rebalanceDays=63),
        "KR": dict(BASE["transactionCosts"]["KR"], rebalanceDays=21)}}

    assert KP.measured_turnover_by_region(
        _regional_report({"US": 85.28}, {"US": 50}), cfg) == {}
