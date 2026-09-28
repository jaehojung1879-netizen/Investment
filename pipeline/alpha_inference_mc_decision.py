"""Monte Carlo-uncertainty-aware acceptance decisions for synthetic calibrations.

A calibration cell estimates a probability (coverage, false-positive rate,
undefined frequency) from ``n`` independent Monte Carlo replicates.  Comparing
that estimate with a threshold as if it were exact makes the verdict depend on
simulation noise in a way nothing in the artifact reveals: a method whose true
coverage is 0.958 reads below a 0.95 floor about one time in five at 300
replicates, and one at 0.945 reads above it about one time in six at 2,000.

Each metric is therefore classified three ways from exact one-sided
Clopper-Pearson bounds on the true probability:

* PASS          - the bound on the SAFE side clears the threshold;
* FAIL          - the bound on the UNSAFE side is already past it;
* INCONCLUSIVE  - the simulation cannot tell which side the truth is on.

The two sides use different error levels.  PASS is an intersection of per-metric
claims, so the per-metric level already bounds the chance of a false PASS.  FAIL
is a union, so its level is a familywise budget divided over every decision
(Bonferroni).  These levels concern only Monte Carlo classification error; they
are unrelated to the 97.5% level of the statistical interval whose coverage is
being measured.

Pure functions; no I/O.
"""
from __future__ import annotations

import math
from typing import Any

from scipy.stats import beta

PASS = "PASS"
FAIL = "FAIL"
INCONCLUSIVE = "INCONCLUSIVE"
DATA_INSUFFICIENT = "DATA_INSUFFICIENT"
INFRASTRUCTURE_ERROR = "INFRASTRUCTURE_ERROR"
STATES = (PASS, FAIL, INCONCLUSIVE, DATA_INSUFFICIENT, INFRASTRUCTURE_ERROR)

FLOOR = "FLOOR"
CEILING = "CEILING"


def _check_counts(successes: int, n: int) -> None:
    if not (isinstance(successes, int) and isinstance(n, int)):
        raise TypeError("successes and n must be integers")
    if n < 0 or successes < 0 or successes > n:
        raise ValueError("require 0 <= successes <= n")


def _check_alpha(alpha: float) -> None:
    if not (0.0 < alpha < 0.5):
        raise ValueError("one-sided alpha must lie in (0, 0.5)")


def clopper_pearson_lower(successes: int, n: int, alpha: float) -> float:
    """Exact one-sided lower confidence bound at level 1 - alpha (0 when no successes)."""
    _check_counts(successes, n)
    _check_alpha(alpha)
    if n == 0 or successes == 0:
        return 0.0
    return float(beta.ppf(alpha, successes, n - successes + 1))


def clopper_pearson_upper(successes: int, n: int, alpha: float) -> float:
    """Exact one-sided upper confidence bound at level 1 - alpha (1 when all successes)."""
    _check_counts(successes, n)
    _check_alpha(alpha)
    if n == 0 or successes == n:
        return 1.0
    return float(beta.ppf(1.0 - alpha, successes + 1, n - successes))


def wald_half_width(successes: int, n: int) -> float:
    """95% normal half-width of the estimate; the precision diagnostic kept from v1-v3."""
    _check_counts(successes, n)
    if n == 0:
        return float("nan")
    p = successes / n
    return float(1.96 * math.sqrt(max(0.0, p * (1.0 - p)) / n))


def classify_metric(
    successes: int,
    n: int,
    *,
    kind: str,
    threshold: float,
    pass_alpha: float,
    fail_alpha: float,
    max_half_width: float | None = None,
) -> dict[str, Any]:
    """Three-state decision for one Monte Carlo-estimated probability.

    ``FLOOR``: the truth must be >= threshold (coverage).
      PASS if lower(pass_alpha) >= threshold; FAIL if upper(fail_alpha) < threshold.
    ``CEILING``: the truth must be <= threshold (false-positive, undefined frequency).
      PASS if upper(pass_alpha) <= threshold; FAIL if lower(fail_alpha) > threshold.

    ``max_half_width`` is a separate usability check: an estimate too imprecise to
    be a calibration reading can never PASS, though it can still FAIL because the
    FAIL bound already carries its own uncertainty.
    """
    if kind not in (FLOOR, CEILING):
        raise ValueError("kind must be FLOOR or CEILING")
    _check_counts(successes, n)
    _check_alpha(pass_alpha)
    _check_alpha(fail_alpha)
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("threshold must lie in [0, 1]")

    record: dict[str, Any] = {
        "kind": kind,
        "threshold": threshold,
        "successes": successes,
        "n": n,
        "estimate": (successes / n) if n else None,
        "lowerBoundPassSide": clopper_pearson_lower(successes, n, pass_alpha),
        "upperBoundPassSide": clopper_pearson_upper(successes, n, pass_alpha),
        "lowerBoundFailSide": clopper_pearson_lower(successes, n, fail_alpha),
        "upperBoundFailSide": clopper_pearson_upper(successes, n, fail_alpha),
        "halfWidth95": wald_half_width(successes, n) if n else None,
    }
    if n == 0:
        record.update({"state": INCONCLUSIVE, "reason": "NO_MEASURABLE_REPLICATES"})
        return record

    if kind == FLOOR:
        is_fail = record["upperBoundFailSide"] < threshold
        is_pass = record["lowerBoundPassSide"] >= threshold
    else:
        is_fail = record["lowerBoundFailSide"] > threshold
        is_pass = record["upperBoundPassSide"] <= threshold

    if is_fail:
        record.update({"state": FAIL, "reason": "FAIL_BOUND_PAST_THRESHOLD"})
    elif is_pass and max_half_width is not None and record["halfWidth95"] > max_half_width:
        record.update({"state": INCONCLUSIVE, "reason": "MONTE_CARLO_PRECISION_INSUFFICIENT"})
    elif is_pass:
        record.update({"state": PASS, "reason": "PASS_BOUND_CLEARS_THRESHOLD"})
    else:
        record.update({"state": INCONCLUSIVE, "reason": "MONTE_CARLO_INTERVAL_OVERLAPS_THRESHOLD"})
    return record


def combine_states(states: list[str]) -> str:
    """Conjunction over decisions: FAIL beats INCONCLUSIVE beats PASS (empty is PASS-vacuous, refused)."""
    if not states:
        raise ValueError("cannot combine an empty list of states")
    unknown = set(states) - {PASS, FAIL, INCONCLUSIVE}
    if unknown:
        raise ValueError(f"unexpected metric states: {sorted(unknown)}")
    if FAIL in states:
        return FAIL
    if INCONCLUSIVE in states:
        return INCONCLUSIVE
    return PASS


def top_level_status(
    *,
    cell_states: list[str],
    insufficient_depth_cells: int,
    infrastructure_error: bool = False,
) -> str:
    """Protocol verdict with the frozen precedence.

    1. infrastructure failure            -> INFRASTRUCTURE_ERROR
    2. any evaluated cell FAIL           -> FAIL
    3. any evaluated cell INCONCLUSIVE   -> INCONCLUSIVE
    4. any registered cell below depth   -> DATA_INSUFFICIENT
    5. otherwise                         -> PASS

    A definite refutation of an evaluated cell outranks everything; an evaluated
    cell the simulation cannot resolve outranks an unevaluated one because it is
    information about the method, whereas a depth shortfall is information about
    the calendar.  Both are non-PASS and neither licenses confirmatory inference.
    """
    if infrastructure_error:
        return INFRASTRUCTURE_ERROR
    if insufficient_depth_cells < 0:
        raise ValueError("insufficient_depth_cells must be non-negative")
    if FAIL in cell_states:
        return FAIL
    if INCONCLUSIVE in cell_states:
        return INCONCLUSIVE
    if insufficient_depth_cells > 0:
        return DATA_INSUFFICIENT
    if not cell_states:
        raise ValueError("no cells were evaluated and none was insufficient")
    if set(cell_states) - {PASS}:
        raise ValueError(f"unexpected cell states: {sorted(set(cell_states) - {PASS})}")
    return PASS


def fail_side_alpha(familywise_alpha: float, decision_count: int) -> float:
    """Bonferroni share of the familywise FAIL budget for each of ``decision_count`` decisions."""
    if decision_count < 1:
        raise ValueError("decision_count must be at least 1")
    _check_alpha(familywise_alpha)
    return familywise_alpha / decision_count
