#!/usr/bin/env python3
"""DEVELOPMENT_ONLY analytic diagnosis of the closed v1/v2/v3 calibration failures.

Reads only the frozen v3 synthetic protocol (for its invented DGP parameters) and
computes exact Gaussian coverage of the ``dateMean`` intervals by Imhof's
formula.  No Monte Carlo, no market data, no Alpha result.  Nothing here is a
calibration verdict: v1, v2 and v3 remain closed FAILs whatever these numbers say.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
from scipy.stats import binom, norm

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline import alpha_inference_mc_decision as mc  # noqa: E402
from pipeline.alpha_inference_exact_coverage import (  # noqa: E402
    calendar_map,
    circular_block_normal_form,
    daily_autocovariance,
    gaussian_coverage,
    self_normalized_form,
    signal_date_covariance,
)

V3_SPEC = ROOT / "research_specs/alpha-inference-calibration-v3.json"
V4_SPEC = ROOT / "research_specs/alpha-inference-calibration-v4.json"
DEFAULT_OUTPUT = ROOT / "docs/results/alpha-inference-calibration-v4-development-diagnostics.json"
U1_975 = 66.57


def _long_run_variance(dgp: dict, horizon: int, step: int, names: int) -> tuple[float, float]:
    """Per-date variance and long-run variance of the overlapping dateMean series."""
    j = np.arange(-(horizon - 1), horizon)
    weights = horizon - np.abs(j)
    lags = np.arange(0, 4 * (horizon // step + 1) + 400)
    gamma = np.array([np.sum(weights * daily_autocovariance(step * k + j, dgp, names)) for k in lags])
    return float(gamma[0]), float(gamma[0] + 2.0 * gamma[1:].sum())


def _normalizer_bias(covariance: np.ndarray, lrv: float) -> dict[str, float]:
    """E[W_n] and Var(sqrt(n) ybar) relative to their fixed-b limits."""
    n = len(covariance)
    one = np.ones(n)
    partial = np.tril(np.ones((n, n))) @ (np.eye(n) - np.outer(one, one) / n)
    expected_w = float(np.trace(partial.T @ partial @ covariance)) / n**2
    numerator = float(one @ covariance @ one) / n
    return {
        "expectedNormalizerOverLimit": expected_w / (lrv / 6.0),
        "numeratorVarianceOverLimit": numerator / lrv,
    }


def _acceptance_operating_characteristic() -> dict[str, dict[str, float]]:
    """P(observed coverage < 0.95) for a cell whose true coverage is p, at R replicates."""
    table: dict[str, dict[str, float]] = {}
    for replicates in (300, 2000):
        threshold_misses = replicates - math.ceil(0.95 * replicates) + 1
        table[str(replicates)] = {
            f"{p:.3f}": float(binom.sf(threshold_misses - 1, replicates, 1.0 - p))
            for p in (0.940, 0.945, 0.950, 0.955, 0.958, 0.960, 0.965, 0.970, 0.975)
        }
    return table


def _state_thresholds(replicates: int, kind: str, threshold: float, pass_alpha: float, fail_alpha: float) -> list[str]:
    """State for every possible success count, from the production classifier itself."""
    return [
        mc.classify_metric(k, replicates, kind=kind, threshold=threshold,
                           pass_alpha=pass_alpha, fail_alpha=fail_alpha)["state"]
        for k in range(replicates + 1)
    ]


def _state_probabilities(states: list[str], replicates: int, p: float) -> dict[str, float]:
    pmf = binom.pmf(np.arange(replicates + 1), replicates, p)
    return {state: float(sum(pmf[i] for i, st in enumerate(states) if st == state))
            for state in (mc.PASS, mc.INCONCLUSIVE, mc.FAIL)}


def _three_state_operating_characteristic(cells: list[dict]) -> dict:
    """State probabilities of the revision-2 Monte Carlo decision rule (DEVELOPMENT_ONLY).

    Depends only on the frozen levels, the replicate count and the thresholds; the
    per-cell rows additionally use the exact Gaussian dateMean coverage of the v4
    interval, which is disclosed, not tuned against.
    """
    spec = json.loads(V4_SPEC.read_text())
    cfg = spec["monteCarloDecision"]
    replicates = int(spec["simulationReplicates"])
    pass_alpha = float(cfg["passSideOneSidedAlpha"])
    fail_alpha = mc.fail_side_alpha(float(cfg["failSideFamilywiseAlpha"]), int(cfg["failSideDecisionCount"]))
    floor = float(spec["acceptance"]["materialCoverageFloor"])
    ceiling = float(spec["acceptance"]["directionalFalsePositiveCeiling"])

    floor_states = _state_thresholds(replicates, mc.FLOOR, floor, pass_alpha, fail_alpha)
    ceiling_states = _state_thresholds(replicates, mc.CEILING, ceiling, pass_alpha, fail_alpha)
    min_pass = next(k for k, st in enumerate(floor_states) if st == mc.PASS)
    max_fail = max(k for k, st in enumerate(floor_states) if st == mc.FAIL)

    rows = []
    product = 1.0
    for cell in cells:
        if cell["dgp"] not in {d["name"] for d in json.loads(V3_SPEC.read_text())["dgps"]}:
            continue
        probs = _state_probabilities(floor_states, replicates, cell["exactCoverageV4CalendarTimeSN"])
        product *= probs[mc.PASS]
        rows.append({
            "dgp": cell["dgp"], "horizonSessions": cell["horizonSessions"], "calendarWeeks": cell["calendarWeeks"],
            "exactGaussianCoverageV4": cell["exactCoverageV4CalendarTimeSN"], **probs,
        })
    return {
        "label": "DEVELOPMENT_ONLY",
        "replicates": replicates,
        "passSideOneSidedAlpha": pass_alpha,
        "failSideOneSidedAlpha": fail_alpha,
        "coverageFloor": floor,
        "coverageMinCoveredForPass": min_pass,
        "coverageMinObservedForPass": min_pass / replicates,
        "coverageMaxCoveredForFail": max_fail,
        "coverageMaxObservedForFail": max_fail / replicates,
        "coverageByTrueValue": {
            f"{p:.3f}": _state_probabilities(floor_states, replicates, p)
            for p in (0.90, 0.92, 0.93, 0.94, 0.945, 0.95, 0.955, 0.957, 0.96, 0.965, 0.97, 0.975)
        },
        "falsePositiveCeilingByTrueRate": {
            f"{p:.3f}": _state_probabilities(ceiling_states, replicates, p)
            for p in (0.01, 0.0125, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07)
        },
        "dateMeanCoverageAtExactV4GaussianValue": rows,
        "illustrativeProbabilityAllInheritedDateMeanCoverageCellsPass": product,
        "illustrativeCaveat": (
            "dateMean coverage only, the 16 inherited-DGP cells with exact Gaussian values, treated as independent "
            "(distinct seeds). The other four confirmatory statistics, the two added DGPs and the false-positive and "
            "undefined-frequency metrics are not analysed here. Read it as: cells whose true coverage lies within about "
            "one Monte Carlo half-width of the 0.95 floor are expected to be INCONCLUSIVE, by design."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    raw = V3_SPEC.read_bytes()
    spec = json.loads(raw)
    step = int(spec["signalStepSessions"])
    names = int(spec["namesPerDate"])
    z = float(norm.ppf(0.9875))

    cells = []
    for dgp in spec["dgps"]:
        for horizon_cfg in spec["horizons"].values():
            horizon = int(horizon_cfg["forwardSessions"])
            for weeks in horizon_cfg["calendarWeeks"]:
                weeks = int(weeks)
                overlap = math.ceil(horizon / step)
                sigma = signal_date_covariance(dgp, horizon, weeks, step, names)
                variance, lrv = _long_run_variance(dgp, horizon, step, names)
                v3 = gaussian_coverage(sigma, self_normalized_form(np.ones(weeks), U1_975))

                mapping, exposure = calendar_map(weeks, horizon, step)
                lags = np.arange(mapping.shape[1])
                daily = daily_autocovariance(lags[:, None] - lags[None, :], dgp, names)
                calendar_sigma = mapping @ daily @ mapping.T
                v4 = gaussian_coverage(calendar_sigma, self_normalized_form(exposure, U1_975))
                middle = len(exposure) // 2

                cell = {
                    "dgp": dgp["name"],
                    "horizonSessions": horizon,
                    "calendarWeeks": weeks,
                    "overlappingSignalDates": overlap,
                    "nonOverlappingWindows": round(weeks * step / horizon, 3),
                    "dateMeanLag1Autocorrelation": float(sigma[0, 1] / sigma[0, 0]),
                    "longRunVarianceOverVariance": lrv / variance,
                    **_normalizer_bias(sigma, lrv),
                    "exactCoverageV3SignalDateSN": v3,
                    "calendarWeeksV4": len(exposure),
                    "calendarInteriorLag1Autocorrelation": float(
                        calendar_sigma[middle, middle + 1] / calendar_sigma[middle, middle]
                    ),
                    "exactCoverageV4CalendarTimeSN": v4,
                }
                primary_block = 52 if horizon == 126 else None
                if primary_block and weeks % primary_block == 0:
                    cell["approxCoverageV2CircularBlock52NormalQuantile"] = gaussian_coverage(
                        sigma, circular_block_normal_form(weeks, primary_block, z)
                    )
                    cell["v2PrimaryBlocks"] = weeks // primary_block
                cells.append(cell)
                print(json.dumps({k: (round(v, 4) if isinstance(v, float) else v) for k, v in cell.items()}))

    result = {
        "label": "DEVELOPMENT_ONLY",
        "purpose": (
            "Analytic reconstruction of why the closed v1/v2/v3 synthetic calibrations failed. "
            "Exact Gaussian coverage of dateMean intervals under the frozen v3 DGPs; not a calibration verdict "
            "and not used to choose any v4 parameter."
        ),
        "sourceSpec": str(V3_SPEC.relative_to(ROOT)),
        "sourceSpecSha256": hashlib.sha256(raw).hexdigest(),
        "nominalCoverage": 0.975,
        "u1CriticalValue": U1_975,
        "cells": cells,
        "acceptanceRuleOperatingCharacteristic": {
            "definition": "P(observed Monte Carlo coverage < 0.95 floor | true coverage p) per statistic cell",
            "byReplicates": _acceptance_operating_characteristic(),
        },
        "threeStateRuleOperatingCharacteristic": _three_state_operating_characteristic(cells),
        "chronologyNote": (
            "These diagnostics, including the exact Gaussian coverage of the v4 calendar-time interval, were computed "
            "before the revision-1 protocol freeze commit and are disclosed in full. Nothing in them selected a "
            "parameter, threshold, DGP, depth, statistic partition, critical value or tuning parameter."
        ),
        "outcomeFree": True,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
