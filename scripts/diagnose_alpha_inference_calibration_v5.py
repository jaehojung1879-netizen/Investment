#!/usr/bin/env python3
"""DEVELOPMENT_ONLY precision diagnostics for the v5 replication budget.

Derives the replicate count from the general precision rule and tabulates the
exact operating characteristic of the frozen v4 three-state decision rule at
GENERIC true-probability values around the thresholds.  It reads only the frozen
v4 protocol (for the Monte Carlo levels and thresholds) and computes no
simulation, no coverage of any registered cell and nothing from any market or
Alpha result.  The generic grid is not tuned to any v4 cell.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scipy.stats import norm  # noqa: E402

from pipeline import alpha_inference_calibration_v5 as v5  # noqa: E402
from pipeline import alpha_inference_mc_decision as mc  # noqa: E402

V4_SPEC = ROOT / "research_specs/alpha-inference-calibration-v4.json"
DEFAULT_OUTPUT = ROOT / "docs/results/alpha-inference-calibration-v5-precision-diagnostics.json"

FLOOR_GRID = (0.920, 0.930, 0.940, 0.945, 0.950, 0.955, 0.960, 0.965, 0.970, 0.975)
CEILING_GRID = (0.010, 0.020, 0.030, 0.040, 0.050, 0.060, 0.070)
COMPARISON_BUDGETS = (2000, 7500, 8000)


def _round(obj):
    if isinstance(obj, float):
        return round(obj, 10)
    if isinstance(obj, dict):
        return {k: _round(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_round(v) for v in obj]
    return obj


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    spec = json.loads(V4_SPEC.read_text())
    cfg = spec["monteCarloDecision"]
    pass_alpha = float(cfg["passSideOneSidedAlpha"])
    fail_alpha = mc.fail_side_alpha(float(cfg["failSideFamilywiseAlpha"]), int(cfg["failSideDecisionCount"]))
    floor = float(spec["acceptance"]["materialCoverageFloor"])
    ceiling = float(spec["acceptance"]["directionalFalsePositiveCeiling"])
    z = float(norm.ppf(0.975))

    normal_min = v5.required_replicates_normal()
    exact_min = v5.required_replicates_exact()
    chosen = v5.chosen_replicates()

    half_widths = {
        str(r): {
            "normalApproximation": 1.96 * math.sqrt(0.95 * 0.05 / r),
            "exactClopperPearsonTwoSided95": v5.exact_cp_half_width(r),
            "meetsTargetNormal": 1.96 * math.sqrt(0.95 * 0.05 / r) <= v5.PRECISION_TARGET_HALF_WIDTH,
            "meetsTargetExact": v5.exact_cp_half_width(r) <= v5.PRECISION_TARGET_HALF_WIDTH,
        }
        for r in sorted({2000, normal_min, 7500, exact_min, chosen, 10000})
    }

    operating = {}
    for r in COMPARISON_BUDGETS:
        kw = {"pass_alpha": pass_alpha, "fail_alpha": fail_alpha}
        operating[str(r)] = {
            "coverageFloorBoundaries": v5.decision_boundaries(r, kind=mc.FLOOR, threshold=floor, **kw),
            "coverageByTrueValue": {
                f"{p:.3f}": v5.state_probabilities(r, p, kind=mc.FLOOR, threshold=floor, **kw)
                for p in FLOOR_GRID
            },
            "ceilingBoundaries": v5.decision_boundaries(r, kind=mc.CEILING, threshold=ceiling, **kw),
            "falsePositiveCeilingByTrueRate": {
                f"{p:.3f}": v5.state_probabilities(r, p, kind=mc.CEILING, threshold=ceiling, **kw)
                for p in CEILING_GRID
            },
        }

    result = {
        "label": "DEVELOPMENT_ONLY",
        "purpose": (
            "Derive the v5 replicate count from a general Monte Carlo precision rule and disclose the exact "
            "operating characteristic of the frozen v4 decision rule at generic true-probability values. "
            "Computed before the v5 protocol was frozen. Uses no simulation, no registered-cell coverage and no "
            "market or Alpha data; the grid is generic and was not tuned to any v4 cell."
        ),
        "sourceProtocol": str(V4_SPEC.relative_to(ROOT)),
        "precisionRule": {
            "statement": (
                "The 95% Monte Carlo half-width of a probability estimate at p = 0.95 must be at most 0.5 "
                "percentage points, by BOTH the normal approximation and the exact two-sided Clopper-Pearson "
                "interval; the budget is the smallest multiple of 500 satisfying both."
            ),
            "targetHalfWidth": v5.PRECISION_TARGET_HALF_WIDTH,
            "atProbability": v5.PRECISION_AT_PROBABILITY,
            "confidenceLevel": v5.PRECISION_LEVEL,
            "zValue": z,
            "normalApproximationFormula": "z * sqrt(p (1 - p) / R) <= targetHalfWidth",
            "normalApproximationRealMinimum": (z / v5.PRECISION_TARGET_HALF_WIDTH) ** 2 * 0.95 * 0.05,
            "normalApproximationMinimumR": normal_min,
            "exactClopperPearsonMinimumR": exact_min,
            "exactRule": "k = round(0.95 R) successes; half-width of the exact two-sided 95% interval",
            "roundingUnit": v5.ROUNDING_UNIT,
            "chosenReplicates": chosen,
            "note": (
                "7,500 satisfies the normal approximation but misses the exact half-width by 1.3e-7 "
                "(exact minimum 7,501), so the rounded budget is 8,000. The choice follows from the rule and "
                "was not made by asking what would classify any cell."
            ),
        },
        "halfWidthByBudget": half_widths,
        "decisionLevels": {
            "passSideOneSidedAlpha": pass_alpha,
            "failSideOneSidedAlpha": fail_alpha,
            "coverageFloor": floor,
            "directionalFalsePositiveCeiling": ceiling,
        },
        "operatingCharacteristicByBudget": operating,
        "outcomeFree": True,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(_round(result), indent=2, sort_keys=True) + "\n")

    at = operating[str(chosen)]
    print(json.dumps({
        "normalMinR": normal_min, "exactMinR": exact_min, "chosen": chosen,
        "coverageBoundaries": at["coverageFloorBoundaries"],
    }))
    for p, probs in at["coverageByTrueValue"].items():
        print(p, {k: round(v, 4) for k, v in probs.items()})


if __name__ == "__main__":
    main()
