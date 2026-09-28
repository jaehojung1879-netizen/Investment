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

from pipeline.alpha_inference_exact_coverage import (  # noqa: E402
    calendar_map,
    circular_block_normal_form,
    daily_autocovariance,
    gaussian_coverage,
    self_normalized_form,
    signal_date_covariance,
)

V3_SPEC = ROOT / "research_specs/alpha-inference-calibration-v3.json"
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
        "outcomeFree": True,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
