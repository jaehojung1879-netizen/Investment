"""Alpha-layer contract for alpha-opportunity-model-v3. Research only.

The alpha layer answers exactly one economic question per stock:

    is E[R_i - R_benchmark(i)] - roundTripCost_i > 0 ?

The regional benchmark is the outside option with expected net alpha 0, so
that sign alone decides POSITIVE_EXPECTED_ALPHA versus
BENCHMARK_EXPECTED_VALUE_PREFERRED. v2 additionally required
P(net alpha > 0) > 0.5 and bootstrap lower bounds above their outside-option
values; that turned a payoff-shape question and an estimation-confidence
question into hidden hurdles on the existence of expected value. A payoff of
40% x +30% and 60% x -8% has positive expectation and a median below zero.
v3 keeps both readings and publishes them BESIDE the expected-value class,
never as a veto on it. Risk preference, sizing and confidence weighting belong
to a later portfolio layer that this module does not define.
"""
from __future__ import annotations

import math

OUTSIDE_OPTION_NET_ALPHA = 0.0

POSITIVE = "POSITIVE_EXPECTED_ALPHA"
BENCHMARK = "BENCHMARK_EXPECTED_VALUE_PREFERRED"
NOT_TRADABLE = "NOT_TRADABLE"
UNMEASURED = "UNMEASURED"
EXPECTED_VALUE_CLASSES = (POSITIVE, BENCHMARK, NOT_TRADABLE, UNMEASURED)

# Descriptive only. P(net alpha > 0) > 0.5 is the statement that the MEDIAN of
# the predicted net relative return is positive; it describes payoff shape.
MEDIAN_AND_MEAN_POSITIVE = "EXPECTATION_POSITIVE_MEDIAN_POSITIVE"
MEAN_POSITIVE_MEDIAN_NOT = "EXPECTATION_POSITIVE_MEDIAN_NOT_POSITIVE"
MEAN_NOT_MEDIAN_POSITIVE = "EXPECTATION_NOT_POSITIVE_MEDIAN_POSITIVE"
NEITHER_POSITIVE = "EXPECTATION_NOT_POSITIVE_MEDIAN_NOT_POSITIVE"
PROBABILITY_UNAVAILABLE = "PROBABILITY_UNAVAILABLE"

# Descriptive only. Fitted-value SAMPLING uncertainty of the conditional mean
# (training-only bootstrap refits), not a range for the stock's own return.
FITTED_INTERVAL_ABOVE_ZERO = "FITTED_INTERVAL_ENTIRELY_ABOVE_OUTSIDE_OPTION"
FITTED_INTERVAL_SPANS_ZERO = "FITTED_INTERVAL_SPANS_OUTSIDE_OPTION"
FITTED_INTERVAL_BELOW_ZERO = "FITTED_INTERVAL_ENTIRELY_AT_OR_BELOW_OUTSIDE_OPTION"
FITTED_INTERVAL_UNAVAILABLE = "FITTED_INTERVAL_UNAVAILABLE"

UNCERTAINTY_KINDS = {
    "expectedNetAlphaLower": "FITTED_VALUE_SAMPLING_5TH_PERCENTILE",
    "expectedNetAlphaUpper": "FITTED_VALUE_SAMPLING_95TH_PERCENTILE",
    "probabilityLower": "FITTED_VALUE_SAMPLING_5TH_PERCENTILE",
    "probabilityUpper": "FITTED_VALUE_SAMPLING_95TH_PERCENTILE",
    "predictiveResidualRms": "PREDICTIVE_OUTCOME_DISPERSION_PAST_MATURED_OOF",
}

PORTFOLIO_FIELDS = frozenset({
    "position", "positions", "weight", "weights", "targetWeight", "kellyFraction",
    "allocation", "capital", "notional", "orderNotional", "portfolioValue",
    "topN", "regionQuota", "sectorQuota", "investedFraction", "riskAversion",
    "confidenceWeight", "NAV", "CAGR", "Sharpe",
})


def finite(*values):
    try:
        return all(v is not None and math.isfinite(float(v)) for v in values)
    except (TypeError, ValueError):
        return False


def dated_cost_policy(policy, as_of):
    """Sell-tax schedule entry effective on `as_of` (portfolio_validation semantics).

    Re-stated here so the alpha layer's sealed closure does not import the
    portfolio/replay module graph; tests prove identity with the original.
    """
    resolved = dict(policy or {})
    if not as_of:
        return resolved
    effective = [r for r in resolved.get("sellTaxSchedule", [])
                 if r.get("effectiveDate") and r["effectiveDate"] <= as_of]
    if effective:
        resolved["sellTaxBps"] = float(max(effective, key=lambda r: r["effectiveDate"])["sellTaxBps"])
    return resolved


def round_trip_cost(region, date, costs):
    """(2 x commission + full spread + dated sell tax) / 10000; benchmark pays 0."""
    p = dated_cost_policy(costs[region], date)
    return (2 * float(p["commissionBps"]) + float(p["spreadBps"]) + float(p["sellTaxBps"])) / 10000


def net(value, cost):
    if not finite(value, cost) or cost < 0:
        return None
    return float(value) - float(cost)


def expected_value_class(*, tradable, pit_valid, expected_net_alpha):
    """The ONLY alpha-existence rule: the sign of expected net alpha."""
    if not tradable:
        return NOT_TRADABLE
    if not pit_valid or not finite(expected_net_alpha):
        return UNMEASURED
    return POSITIVE if expected_net_alpha > OUTSIDE_OPTION_NET_ALPHA else BENCHMARK


def distribution_state(expected_net_alpha, probability):
    if not finite(expected_net_alpha) or not finite(probability):
        return PROBABILITY_UNAVAILABLE
    mean_pos = expected_net_alpha > OUTSIDE_OPTION_NET_ALPHA
    median_pos = probability > 0.5
    return {(True, True): MEDIAN_AND_MEAN_POSITIVE, (True, False): MEAN_POSITIVE_MEDIAN_NOT,
            (False, True): MEAN_NOT_MEDIAN_POSITIVE, (False, False): NEITHER_POSITIVE}[(mean_pos, median_pos)]


def fitted_uncertainty_state(lower, upper):
    if not finite(lower, upper):
        return FITTED_INTERVAL_UNAVAILABLE
    if lower > OUTSIDE_OPTION_NET_ALPHA:
        return FITTED_INTERVAL_ABOVE_ZERO
    if upper <= OUTSIDE_OPTION_NET_ALPHA:
        return FITTED_INTERVAL_BELOW_ZERO
    return FITTED_INTERVAL_SPANS_ZERO


def describe(row, *, cost):
    """One name-date's alpha-layer record. Carries no sizing field by design."""
    expected = net(row.get("grossExpectedAlpha"), cost)
    lower = net(row.get("grossExpectedAlphaLower"), cost)
    upper = net(row.get("grossExpectedAlphaUpper"), cost)
    probability = row.get("probabilityNetOutperform")
    record = {
        "roundTripCost": cost, "outsideOptionNetAlpha": OUTSIDE_OPTION_NET_ALPHA,
        "expectedNetAlpha": expected,
        "expectedValueClass": expected_value_class(tradable=bool(row.get("tradable")),
                                                   pit_valid=row.get("pitValid", True) is True,
                                                   expected_net_alpha=expected),
        "probabilityNetOutperform": probability if finite(probability) else None,
        "probabilityLower": row.get("probabilityLower") if finite(row.get("probabilityLower")) else None,
        "probabilityUpper": row.get("probabilityUpper") if finite(row.get("probabilityUpper")) else None,
        "distributionState": distribution_state(expected, probability),
        "expectedNetAlphaLower": lower, "expectedNetAlphaUpper": upper,
        "fittedUncertaintyState": fitted_uncertainty_state(lower, upper),
        "predictiveResidualRms": row.get("predictiveResidualRms") if finite(row.get("predictiveResidualRms")) else None,
        "uncertaintyKinds": UNCERTAINTY_KINDS,
    }
    record["positiveExpectedAlpha"] = record["expectedValueClass"] == POSITIVE
    assert not PORTFOLIO_FIELDS & record.keys()
    return record


def opportunity_surface(records):
    """All positive-expected-alpha names, ordered by expectedNetAlpha.

    ``records`` is an iterable of (ticker, describe(...) output). The order is
    for downstream analysis only; there is no cut, count, quota or slot, and
    an empty surface means the benchmark is preferred in expected value for
    every tradable name on that date.
    """
    positive = [(t, r["expectedNetAlpha"]) for t, r in records if r["expectedValueClass"] == POSITIVE]
    positive.sort(key=lambda x: (-x[1], x[0]))
    return {"positiveExpectedAlpha": [t for t, _ in positive], "count": len(positive),
            "state": "POSITIVE_EXPECTED_ALPHA_PRESENT" if positive else "NO_POSITIVE_EXPECTED_ALPHA"}
