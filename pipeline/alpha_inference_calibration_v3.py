"""Synthetic-only self-normalized inference calibration v3.

V3 closes the two failed block-bootstrap calibration contracts and removes the
block-length tuning parameter from the primary inferential mechanism.  It uses
the scalar self-normalized statistic of Shao (2010) / Lobato (2001) for each
registered date-level mean statistic.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

from pipeline.alpha_inference_calibration_v1 import (
    STATISTICS,
    _aggregate,
    _passes_metric,
    simulate_null_date_statistics,
)


def _self_normalized_interval(
    series: np.ndarray,
    critical_value: float,
) -> dict[str, float] | None:
    """Return the scalar self-normalized CI for the arithmetic mean.

    For x_1,...,x_n, let S_t be the prefix sum and

        W_n = n^-2 sum_t (S_t - (t/n) S_n)^2.

    The pivotal statistic is n (xbar-theta)^2 / W_n, so the confidence interval
    is xbar +/- sqrt(c * W_n / n), where c is the frozen U1 upper critical
    value.  A zero/invalid normalizer is reported undefined rather than being
    converted into a falsely degenerate interval.
    """
    values = np.asarray(series, dtype=float)
    if values.ndim != 1 or len(values) < 2 or not np.isfinite(values).all():
        return None
    if not math.isfinite(critical_value) or critical_value <= 0:
        raise ValueError("critical_value must be finite and positive")

    n = len(values)
    prefix = np.cumsum(values, dtype=float)
    t = np.arange(1, n + 1, dtype=float)
    centered_prefix = prefix - (t / n) * prefix[-1]
    w_n = float(np.dot(centered_prefix, centered_prefix) / (n * n))
    if not math.isfinite(w_n) or w_n <= 0.0:
        return None

    estimate = float(prefix[-1] / n)
    half_width = float(math.sqrt(critical_value * w_n / n))
    return {
        "estimate": estimate,
        "lower": estimate - half_width,
        "upper": estimate + half_width,
        "width": 2.0 * half_width,
        "selfNormalizer": w_n,
    }


def run_calibration(spec: dict[str, Any]) -> dict[str, Any]:
    """Execute the frozen v3 synthetic protocol without repository outcome reads."""
    if spec.get("contract") != "ALPHA_INFERENCE_CALIBRATION_V3" or not spec.get("outcomeFree"):
        raise ValueError("INVALID_CALIBRATION_PROTOCOL")

    interval_cfg = spec.get("intervalConstruction", {})
    if interval_cfg.get("method") != "SELF_NORMALIZED_FIXED_B_BARTLETT_B1":
        raise ValueError("INVALID_V3_INTERVAL_METHOD")
    if interval_cfg.get("blockLength") != "NONE":
        raise ValueError("V3_MUST_NOT_HAVE_BLOCK_LENGTH")
    if int(interval_cfg.get("bootstrapDraws", -1)) != 0:
        raise ValueError("V3_MUST_NOT_BOOTSTRAP_EVALUATION_INTERVALS")

    critical_value = float(interval_cfg["U1CriticalValue"])
    sims = int(spec["simulationReplicates"])
    acceptance = spec["acceptance"]
    cells: list[dict[str, Any]] = []
    registered_failures: list[dict[str, Any]] = []

    for dgp_index, dgp in enumerate(spec["dgps"]):
        for horizon_cfg in spec["horizons"].values():
            horizon = int(horizon_cfg["forwardSessions"])
            for weeks_value in horizon_cfg["calendarWeeks"]:
                weeks = int(weeks_value)
                stats_by_rep = [
                    simulate_null_date_statistics(
                        spec,
                        dgp,
                        horizon=horizon,
                        weeks=weeks,
                        replicate=replicate,
                        dgp_index=dgp_index,
                    )
                    for replicate in range(sims)
                ]

                metrics: dict[str, Any] = {}
                cell_failures: dict[str, list[str]] = {}
                for statistic in STATISTICS:
                    records = [
                        _self_normalized_interval(rep_stats[statistic], critical_value)
                        for rep_stats in stats_by_rep
                    ]
                    aggregate = _aggregate(records, sims)
                    ok, failures = _passes_metric(aggregate, acceptance)
                    metrics[statistic] = aggregate
                    if not ok:
                        cell_failures[statistic] = failures

                cell: dict[str, Any] = {
                    "dgp": dgp["name"],
                    "horizonSessions": horizon,
                    "calendarWeeks": weeks,
                    "status": "PASS" if not cell_failures else "FAIL",
                    "metrics": metrics,
                    "failures": cell_failures,
                }
                cells.append(cell)
                if cell_failures:
                    registered_failures.append(cell)

    return {
        "contract": spec["contract"],
        "outcomeFree": True,
        "intervalConstruction": spec["intervalConstruction"],
        "simulationReplicates": sims,
        "statistics": list(STATISTICS),
        "cells": cells,
        "primaryStatus": "PASS" if not registered_failures else "FAIL",
        "primaryFailures": registered_failures,
        "interpretation": spec["acceptance"]["interpretationRule"],
    }
