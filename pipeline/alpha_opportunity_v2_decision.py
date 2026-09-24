"""Benchmark-as-outside-option decision contract for alpha-opportunity-model-v2.

Research only. No production module may import this, and nothing here sizes,
weights, counts or ranks a position. The question answered per stock is one
comparison against one competitor for the same capital:

    is holding stock i a better use of this capital than holding its own
    regional passive benchmark, net of the cost of switching into it?

The benchmark is IN the choice set with expected net alpha exactly 0, so a
universe can have a best stock and no active opportunity at all. Every
threshold below is either the outside option's own value (0 for a return
difference, 0.5 for the probability that a difference is positive) or a
quantity inherited unchanged from the sealed v1 contract (the 5th/95th
bootstrap quantiles). Nothing is a hurdle chosen to let some number of names
through, and nothing here reads a realized outcome.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

# The outside option's own values, not tunable parameters. A benchmark held
# against itself has relative return 0 by identity; a return difference whose
# median is positive has P(difference > 0) > 0.5 by definition of the median.
OUTSIDE_OPTION_NET_ALPHA = 0.0
PROBABILITY_INDIFFERENCE = 0.5

ACTIVE = "ACTIVE_OPPORTUNITY"
UNRESOLVED = "POSITIVE_BUT_NOT_DISTINGUISHABLE_FROM_BENCHMARK"
DISAGREE = "HEADS_DISAGREE_BENCHMARK_RETAINED"
BENCHMARK = "BENCHMARK_PREFERRED"
NOT_TRADABLE = "NOT_TRADABLE"
UNMEASURED = "UNMEASURED"
CLASSES = (ACTIVE, UNRESOLVED, DISAGREE, BENCHMARK, NOT_TRADABLE, UNMEASURED)
# Only ACTIVE moves capital out of the benchmark. Every other class leaves it
# in the outside option — that is the default, not a failure to find an idea.
ACTIVE_CLASSES = frozenset({ACTIVE})

# Fields a decision may never carry: sizing, counts and allocation belong to a
# separate portfolio layer that this contract does not define or optimise.
PORTFOLIO_FIELDS = frozenset({
    "position", "positions", "weight", "weights", "targetWeight", "kellyFraction",
    "allocation", "capital", "notional", "orderNotional", "portfolioValue",
    "rank", "topN", "regionQuota", "sectorQuota", "NAV", "CAGR", "Sharpe",
})


def _finite(*values):
    try:
        return all(v is not None and math.isfinite(float(v)) for v in values)
    except (TypeError, ValueError):
        return False


def round_trip_cost(policy):
    """(2 x commission + full spread + sell tax) / 10000, as v1 sealed it.

    The benchmark alternative is charged nothing: its own holding cost is not
    subtracted from the stock's hurdle, which errs toward the benchmark.
    """
    return (2 * float(policy["commissionBps"]) + float(policy["spreadBps"])
            + float(policy["sellTaxBps"])) / 10000


def dated_round_trip_cost(region, date, spec):
    """Signal-date cost from the public dated schedule known on that date."""
    from .portfolio_validation import _dated_cost_policy
    return round_trip_cost(_dated_cost_policy(spec["transactionCosts"][region], date))


def net_alpha(gross_expected_alpha, cost):
    """E[R_i - R_b - c] = E[R_i - R_b] - c: the cost is known at the signal."""
    if not _finite(gross_expected_alpha, cost) or cost < 0:
        return None
    return float(gross_expected_alpha) - float(cost)


def tradability(closes, volumes, *, window):
    """Basic PIT tradability, independent of capital size and of any alpha.

    ``closes``/``volumes`` are the ``window`` regional exchange sessions ending
    on the signal date, reindexed to the exchange calendar WITHOUT fills. The
    name must have printed a positive close and positive share volume on every
    one of them. Share volume is used as traded/not-traded evidence only; it is
    never multiplied by the forward total-return index to impersonate traded
    cash value (v1's refusal stands).
    """
    closes = pd.to_numeric(pd.Series(closes, dtype=float), errors="coerce")
    volumes = pd.to_numeric(pd.Series(volumes, dtype=float), errors="coerce")
    if len(closes) < window or len(volumes) < window:
        return False, "INSUFFICIENT_TRADING_HISTORY"
    c, v = closes.iloc[-window:].to_numpy(), volumes.iloc[-window:].to_numpy()
    if not np.isfinite(c[-1]) or c[-1] <= 0:
        return False, "NO_SIGNAL_DATE_PRICE"
    if not (np.isfinite(c).all() and (c > 0).all()):
        return False, "MISSING_OR_NONPOSITIVE_CLOSE_IN_WINDOW"
    if not (np.isfinite(v).all() and (v > 0).all()):
        return False, "ZERO_OR_MISSING_VOLUME_IN_WINDOW"
    return True, "TRADABLE"


def classify(*, tradable, expected_net_alpha, probability, net_alpha_lower, probability_lower):
    """One stock versus its benchmark. Never a rank, a count or a percentile.

    ``probability`` is the model's P(R_i - R_b - cost > 0); the lower bounds are
    the sealed 5th percentiles of the training-only bootstrap refits.
    """
    if not tradable:
        return NOT_TRADABLE
    if not _finite(expected_net_alpha, probability):
        return UNMEASURED
    mean_favours = expected_net_alpha > OUTSIDE_OPTION_NET_ALPHA
    prob_favours = probability > PROBABILITY_INDIFFERENCE
    if not mean_favours and not prob_favours:
        return BENCHMARK
    if mean_favours != prob_favours:
        return DISAGREE
    if not _finite(net_alpha_lower, probability_lower):
        # Positive point estimates without a measured interval are not enough
        # to leave the outside option.
        return UNMEASURED
    if (net_alpha_lower > OUTSIDE_OPTION_NET_ALPHA
            and probability_lower > PROBABILITY_INDIFFERENCE):
        return ACTIVE
    return UNRESOLVED


def decide(row, *, cost):
    """Decision record for one name-date; carries no sizing field by design."""
    gross = row.get("grossExpectedAlpha")
    expected = net_alpha(gross, cost)
    lower = net_alpha(row.get("grossExpectedAlphaLower"), cost)
    upper = net_alpha(row.get("grossExpectedAlphaUpper"), cost)
    label = classify(tradable=bool(row.get("tradable")), expected_net_alpha=expected,
                     probability=row.get("probabilityNetOutperform"),
                     net_alpha_lower=lower, probability_lower=row.get("probabilityLower"))
    record = {"roundTripCost": cost, "expectedNetAlpha": expected,
              "expectedNetAlphaLower": lower, "expectedNetAlphaUpper": upper,
              "outsideOptionNetAlpha": OUTSIDE_OPTION_NET_ALPHA,
              "opportunityClass": label, "activeOpportunity": label in ACTIVE_CLASSES}
    assert not PORTFOLIO_FIELDS & record.keys()
    return record


def opportunity_set(decisions):
    """Names that beat the outside option; may be empty, one, or many.

    ``decisions`` is an iterable of (ticker, opportunityClass). There is no
    target count, no top-N and no region slot: an empty set means the capital
    stays in the benchmark for that region-date.
    """
    active = sorted(t for t, label in decisions if label in ACTIVE_CLASSES)
    return {"activeOpportunities": active, "count": len(active),
            "state": "ACTIVE_OPPORTUNITIES" if active else "NO_ACTIVE_OPPORTUNITY"}
