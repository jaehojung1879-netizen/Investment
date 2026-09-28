"""Precision-only replication of the frozen v4 calendar-time calibration.

V4 completed and returned INCONCLUSIVE, not FAIL: two H21 / 78-week cells sat
too close to the frozen 0.95 coverage floor for 2,000 replicates to certify
under the predeclared exact Clopper-Pearson rule.  V5 asks only whether the
SAME method can be classified more precisely with a larger Monte Carlo budget.

Nothing scientific changes.  The v4 engine (`pipeline.alpha_inference_calibration_v4`
and the files it imports) is CALLED, not copied; this module changes only the
protocol identity, the seed and the replicate count, and it can prove that:

* `semantic_differences` compares a v5 protocol with the v4 protocol key by key
  and reports any scientific key that differs and any key nobody classified;
* the runner pins the sha256 of every engine file (see `FORMAL_PINS`).

This module reads no files and accepts only already-loaded dictionaries.
"""
from __future__ import annotations

import math
from typing import Any

from scipy.stats import beta, binom, norm

from pipeline import alpha_inference_calibration_v4 as v4
from pipeline import alpha_inference_mc_decision as mc

CONTRACT = "ALPHA_INFERENCE_CALIBRATION_V5"
PREDECESSOR_CONTRACT = v4.CONTRACT

# Seeds already consumed by closed protocols; v5 must differ from all of them.
PRIOR_SEEDS = {"v1": 20260928, "v2": 20260929, "v3": 20260930, "v4": 20261001}

# The general precision rule.  It is stated about a probability estimate at the
# coverage floor and is NOT derived from any v4 cell.
PRECISION_TARGET_HALF_WIDTH = 0.005
PRECISION_AT_PROBABILITY = 0.95
PRECISION_LEVEL = 0.95
ROUNDING_UNIT = 500

FORMAL_PINS: dict[str, Any] = {
    "seed": 20261002,
    "simulationReplicates": 8000,
    "predecessorSpecSha256": "012e43177b8e8ec7143eff30d7280c4cf8015b32b464bcddd87c09f75c984a5d",
    # sha256 of every file the v4 engine executes; the runner verifies the bytes.
    "engineFiles": {
        "pipeline/alpha_inference_calibration_v1.py": "87a6990fd6fc5217824ee00205ee247abe88006a2445d41b5a6086709f551186",
        "pipeline/alpha_inference_calibration_v3.py": "5afa9a03dbfb5343be522d282a1b2050cbbd01722dc7b8eae1e6e06b55c2bf13",
        "pipeline/alpha_inference_calibration_v4.py": "024231e1adeeb4d29ea047d187eb7eb5478fd21c442991bd1c8963d6a38cd601",
        "pipeline/alpha_inference_mc_decision.py": "6d131e20e2bcc212247a95fce2c5f733faa7f1624991b364d9fea96b4962f61e",
    },
}

# Top-level protocol keys that define the science.  Every one must be identical
# to v4's.  A test fails if any differs.
SCIENTIFIC_KEYS = (
    "outcomeFree",
    "namesPerDate",
    "signalStepSessions",
    "confidence",
    "horizons",
    "minimumConfirmatoryDepth",
    "dgps",
    "dgpRationale",
    "nullConstruction",
    "selectionFraction",
    "syntheticForecastScale",
    "statistics",
    "intervalConstruction",
    "descriptiveIntervalConstruction",
    "undefinedStatistics",
    "acceptance",
    "monteCarloDecision",
)

# Keys that may differ from v4 (identity, budget, provenance and prose).
PERMITTED_DIFFERENCE_KEYS = (
    "contract",
    "protocolStatus",
    "purpose",
    "methodologyRecord",
    "sourceReview",
    "seed",
    "simulationReplicates",
    "simulationReplicatesRationale",
    "precisionCriterion",
    "replicationOf",
    "predecessorSpecPath",
    "predecessorSpecSha256",
    "engineIdentity",
    "stoppingRule",
    "developmentDiagnostics",
    "v1FailureReference",
    "v2FailureReference",
    "v3FailureReference",
    "v4FormalResult",
    "prohibitions",
    "preMergeRevision",
)


# --------------------------------------------------------------------------
# precision rule
# --------------------------------------------------------------------------
def required_replicates_normal(
    half_width: float = PRECISION_TARGET_HALF_WIDTH,
    p: float = PRECISION_AT_PROBABILITY,
    level: float = PRECISION_LEVEL,
) -> int:
    """Smallest R with z * sqrt(p (1-p) / R) <= half_width (normal approximation)."""
    if not (0.0 < half_width < 1.0 and 0.0 < p < 1.0 and 0.5 < level < 1.0):
        raise ValueError("half_width and p must lie in (0, 1) and level in (0.5, 1)")
    z = float(norm.ppf(0.5 + level / 2.0))
    return math.ceil((z / half_width) ** 2 * p * (1.0 - p))


def exact_cp_half_width(
    replicates: int,
    p: float = PRECISION_AT_PROBABILITY,
    level: float = PRECISION_LEVEL,
) -> float:
    """Half-width of the exact two-sided Clopper-Pearson interval when round(p R) succeed."""
    if replicates < 1 or not 0.0 < p < 1.0 or not 0.5 < level < 1.0:
        raise ValueError("invalid replicates, p or level")
    k = round(p * replicates)
    tail = (1.0 - level) / 2.0
    lower = float(beta.ppf(tail, k, replicates - k + 1)) if k > 0 else 0.0
    upper = float(beta.ppf(1.0 - tail, k + 1, replicates - k)) if k < replicates else 1.0
    return (upper - lower) / 2.0


def required_replicates_exact(
    half_width: float = PRECISION_TARGET_HALF_WIDTH,
    p: float = PRECISION_AT_PROBABILITY,
    level: float = PRECISION_LEVEL,
    search_limit: int = 200_000,
) -> int:
    """Smallest R whose exact Clopper-Pearson half-width is <= half_width, starting at the normal value.

    The exact half-width is not monotone in R in general (round(p R) is a sawtooth),
    so the answer is the smallest R from which the criterion holds for every larger R
    checked up to twice the answer; the scan aborts if that never happens.
    """
    start = max(1, required_replicates_normal(half_width, p, level) - 200)
    candidate = None
    for r in range(start, search_limit):
        if exact_cp_half_width(r, p, level) <= half_width:
            candidate = r
            break
    if candidate is None:
        raise ValueError("no replicate count satisfies the exact criterion within the search limit")
    if any(exact_cp_half_width(r, p, level) > half_width for r in range(candidate, candidate + 1000)):
        raise ValueError("exact half-width criterion is not stable beyond the first crossing")
    return candidate


def round_up_to_unit(value: int, unit: int = ROUNDING_UNIT) -> int:
    if value < 1 or unit < 1:
        raise ValueError("value and unit must be positive")
    return int(math.ceil(value / unit) * unit)


def chosen_replicates() -> int:
    """The frozen budget: the smallest multiple of the rounding unit meeting BOTH criteria."""
    return round_up_to_unit(max(required_replicates_normal(), required_replicates_exact()))


def state_probabilities(
    replicates: int,
    true_p: float,
    *,
    kind: str,
    threshold: float,
    pass_alpha: float,
    fail_alpha: float,
) -> dict[str, float]:
    """P(PASS), P(INCONCLUSIVE), P(FAIL) for a metric whose TRUE probability is `true_p`."""
    if not 0.0 <= true_p <= 1.0:
        raise ValueError("true_p must lie in [0, 1]")
    probabilities = {mc.PASS: 0.0, mc.INCONCLUSIVE: 0.0, mc.FAIL: 0.0}
    for k in range(replicates + 1):
        state = mc.classify_metric(
            k, replicates, kind=kind, threshold=threshold, pass_alpha=pass_alpha, fail_alpha=fail_alpha
        )["state"]
        probabilities[state] += float(binom.pmf(k, replicates, true_p))
    return probabilities


def decision_boundaries(
    replicates: int, *, kind: str, threshold: float, pass_alpha: float, fail_alpha: float
) -> dict[str, int | None]:
    """Smallest success count that PASSes and largest that FAILs (floor); mirrored for a ceiling."""
    states = [
        mc.classify_metric(
            k, replicates, kind=kind, threshold=threshold, pass_alpha=pass_alpha, fail_alpha=fail_alpha
        )["state"]
        for k in range(replicates + 1)
    ]
    passing = [k for k, s in enumerate(states) if s == mc.PASS]
    failing = [k for k, s in enumerate(states) if s == mc.FAIL]
    if kind == mc.FLOOR:
        return {"minSuccessesForPass": min(passing) if passing else None,
                "maxSuccessesForFail": max(failing) if failing else None}
    return {"maxEventsForPass": max(passing) if passing else None,
            "minEventsForFail": min(failing) if failing else None}


# --------------------------------------------------------------------------
# semantic equivalence with v4
# --------------------------------------------------------------------------
def semantic_differences(predecessor: dict[str, Any], spec: dict[str, Any]) -> dict[str, list[str]]:
    """Compare a v5 protocol with the v4 protocol.

    Returns `scientificMismatches` (a science key that differs) and
    `unclassifiedKeys` (a key present in either protocol that is neither
    scientific nor a permitted difference).  Both must be empty.
    """
    scientific_mismatches = [
        key for key in SCIENTIFIC_KEYS if predecessor.get(key) != spec.get(key)
    ]
    classified = set(SCIENTIFIC_KEYS) | set(PERMITTED_DIFFERENCE_KEYS)
    unclassified = sorted((set(predecessor) | set(spec)) - classified)
    return {"scientificMismatches": scientific_mismatches, "unclassifiedKeys": unclassified}


# --------------------------------------------------------------------------
# protocol validation and execution
# --------------------------------------------------------------------------
def engine_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """The protocol the unchanged v4 engine executes: v5's, under the v4 contract label."""
    return {**spec, "contract": PREDECESSOR_CONTRACT}


def validate_spec(
    spec: dict[str, Any],
    *,
    predecessor_spec: dict[str, Any] | None = None,
    predecessor_spec_sha256: str | None = None,
    formal: bool = True,
) -> None:
    """Refuse any protocol that is not the frozen v5 replication of v4.

    Method, thresholds, critical value, statistic partition and Monte Carlo
    decision rule are checked in BOTH modes by the v4 validator; a formal run
    additionally pins the seed, budget, predecessor and engine identity and
    requires semantic equivalence with the v4 protocol.
    """
    def fail(reason: str) -> None:
        raise ValueError(f"INVALID_V5_PROTOCOL: {reason}")

    if spec.get("contract") != CONTRACT or spec.get("outcomeFree") is not True:
        fail("contract/outcomeFree")
    try:
        v4.validate_spec(engine_spec(spec), formal=False)
    except ValueError as exc:
        fail(str(exc))
    if int(spec.get("simulationReplicates", 0)) < 1:
        fail("simulationReplicates")
    if not formal:
        return

    if spec.get("seed") != FORMAL_PINS["seed"]:
        fail("seed")
    if spec.get("seed") in PRIOR_SEEDS.values():
        fail("seed reuses a closed protocol's seed")
    if spec.get("simulationReplicates") != FORMAL_PINS["simulationReplicates"]:
        fail("simulationReplicates")
    if spec.get("simulationReplicates") != chosen_replicates():
        fail("simulationReplicates does not satisfy the frozen precision rule")
    criterion = spec.get("precisionCriterion", {})
    if criterion.get("chosenReplicates") != spec.get("simulationReplicates"):
        fail("precisionCriterion.chosenReplicates")
    if criterion.get("targetHalfWidth") != PRECISION_TARGET_HALF_WIDTH:
        fail("precisionCriterion.targetHalfWidth")
    if criterion.get("atProbability") != PRECISION_AT_PROBABILITY:
        fail("precisionCriterion.atProbability")
    if spec.get("predecessorSpecSha256") != FORMAL_PINS["predecessorSpecSha256"]:
        fail("predecessorSpecSha256")
    if predecessor_spec_sha256 != FORMAL_PINS["predecessorSpecSha256"]:
        fail("the predecessor protocol on disk is not the frozen v4 protocol")
    if spec.get("engineIdentity", {}).get("files") != FORMAL_PINS["engineFiles"]:
        fail("engineIdentity.files")
    if predecessor_spec is None:
        fail("a formal run needs the v4 protocol to prove equivalence")
    differences = semantic_differences(predecessor_spec, spec)
    if differences["scientificMismatches"]:
        fail(f"scientific keys differ from v4: {differences['scientificMismatches']}")
    if differences["unclassifiedKeys"]:
        fail(f"unclassified protocol keys: {differences['unclassifiedKeys']}")


def run_calibration(
    spec: dict[str, Any],
    *,
    predecessor_spec: dict[str, Any] | None = None,
    predecessor_spec_sha256: str | None = None,
    progress: Any = None,
    formal: bool = True,
) -> dict[str, Any]:
    """Execute the frozen v5 protocol with the unchanged v4 engine.  No repository data are accepted."""
    validate_spec(
        spec,
        predecessor_spec=predecessor_spec,
        predecessor_spec_sha256=predecessor_spec_sha256,
        formal=formal,
    )
    result = v4.run_calibration(engine_spec(spec), progress=progress, formal=False)
    result["contract"] = CONTRACT
    result["engine"] = {
        "contract": PREDECESSOR_CONTRACT,
        "module": "pipeline.alpha_inference_calibration_v4",
        "changedFromV4": ["contract label", "seed", "simulationReplicates"],
    }
    result["replicationOf"] = spec.get("replicationOf")
    result["precisionCriterion"] = spec.get("precisionCriterion")
    result["seedUsed"] = spec["seed"]
    return result
