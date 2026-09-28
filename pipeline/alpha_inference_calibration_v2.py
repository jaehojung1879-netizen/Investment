"""Synthetic-only inference calibration v2.

V2 preserves the v1 synthetic data-generating processes, block grid, horizons,
statistics, replication budget and acceptance tolerances.  It changes only the
finite-sample interval mechanics: circular moving blocks remove endpoint
inclusion asymmetry and a basic interval is formed from centered bootstrap
errors.
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


def _circular_bootstrap_plan(
    n: int,
    block: int,
    draws: int,
    seed_parts: list[int],
) -> tuple[np.ndarray, int]:
    """Uniform circular block starts for draws of exactly ``n`` observations."""
    if block <= 0 or block > n:
        raise ValueError("block must satisfy 1 <= block <= n")
    count = math.ceil(n / block)
    rng = np.random.default_rng(np.random.SeedSequence(seed_parts))
    starts = rng.integers(0, n, size=(draws, count), dtype=np.int32)
    return starts, n - block * (count - 1)


def _circular_bootstrap_means(
    series: np.ndarray,
    starts: np.ndarray,
    block: int,
    final_length: int,
) -> np.ndarray:
    """Means of circular moving-block samples without materializing indices."""
    n = len(series)
    if block <= 0 or block > n:
        raise ValueError("block must satisfy 1 <= block <= n")
    if final_length <= 0 or final_length > block:
        raise ValueError("final_length must satisfy 1 <= final_length <= block")

    # Duplicating the first block-1 observations makes every wrapped block a
    # contiguous slice while retaining a uniform start probability over 0..n-1.
    extended = np.concatenate([series, series[: block - 1]]) if block > 1 else series
    prefix = np.concatenate(([0.0], np.cumsum(extended, dtype=float)))
    full = prefix[starts + block] - prefix[starts]
    partial = prefix[starts + final_length] - prefix[starts]

    if starts.shape[1] == 1:
        total = partial[:, 0]
    else:
        total = full[:, :-1].sum(axis=1) + partial[:, -1]
    return total / n


def _basic_interval(
    series: np.ndarray,
    starts: np.ndarray,
    block: int,
    final_length: int,
    tail: float,
) -> dict[str, float] | None:
    """Circular moving-block basic interval using centered bootstrap errors."""
    if not np.isfinite(series).all():
        return None
    estimate = float(np.mean(series))
    draws = _circular_bootstrap_means(series, starts, block, final_length)
    if not np.isfinite(draws).all():
        return None
    errors = draws - estimate
    q_lo, q_hi = np.quantile(errors, [tail, 1.0 - tail])
    lo = estimate - q_hi
    hi = estimate - q_lo
    return {
        "estimate": estimate,
        "lower": float(lo),
        "upper": float(hi),
        "width": float(hi - lo),
    }


def run_calibration(spec: dict[str, Any]) -> dict[str, Any]:
    """Execute the frozen v2 synthetic protocol without repository data reads."""
    if spec.get("contract") != "ALPHA_INFERENCE_CALIBRATION_V2" or not spec.get("outcomeFree"):
        raise ValueError("INVALID_CALIBRATION_PROTOCOL")
    interval_cfg = spec.get("intervalConstruction", {})
    if interval_cfg.get("resampler") != "CIRCULAR_MOVING_BLOCK_BOOTSTRAP":
        raise ValueError("INVALID_V2_RESAMPLER")
    if interval_cfg.get("interval") != "BASIC_CENTERED_ERROR":
        raise ValueError("INVALID_V2_INTERVAL")

    sims = int(spec["simulationReplicates"])
    draws = int(spec["bootstrapDraws"])
    tail = float(spec["confidence"]["tailQuantile"])
    min_blocks = int(spec["minimumEffectiveBlocks"])
    acceptance = spec["acceptance"]
    cells: list[dict[str, Any]] = []
    primary_failures: list[dict[str, Any]] = []

    for dgp_index, dgp in enumerate(spec["dgps"]):
        for horizon_cfg in spec["horizons"].values():
            horizon = int(horizon_cfg["forwardSessions"])
            for weeks in horizon_cfg["calendarWeeks"]:
                weeks = int(weeks)
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
                for block_value in horizon_cfg["candidateBlocks"]:
                    block = int(block_value)
                    effective_blocks = weeks // block
                    primary = block == int(horizon_cfg["primaryBlock"])
                    cell: dict[str, Any] = {
                        "dgp": dgp["name"],
                        "horizonSessions": horizon,
                        "calendarWeeks": weeks,
                        "blockWeeks": block,
                        "primary": primary,
                        "effectiveBlockFloor": effective_blocks,
                    }
                    if effective_blocks < min_blocks:
                        cell.update({"status": "DATA_INSUFFICIENT_DEPTH", "metrics": None})
                        cells.append(cell)
                        if primary:
                            primary_failures.append({**cell, "reason": "PRIMARY_DEPTH_BELOW_FLOOR"})
                        continue

                    starts, final_length = _circular_bootstrap_plan(
                        weeks,
                        block,
                        draws,
                        [int(spec["seed"]), 8002, dgp_index, horizon, weeks, block],
                    )
                    metrics: dict[str, Any] = {}
                    cell_failures: dict[str, list[str]] = {}
                    for statistic in STATISTICS:
                        records = [
                            _basic_interval(rep_stats[statistic], starts, block, final_length, tail)
                            for rep_stats in stats_by_rep
                        ]
                        aggregate = _aggregate(records, sims)
                        ok, failures = _passes_metric(aggregate, acceptance)
                        metrics[statistic] = aggregate
                        if not ok:
                            cell_failures[statistic] = failures
                    cell.update(
                        {
                            "status": "PASS" if not cell_failures else "FAIL",
                            "metrics": metrics,
                            "failures": cell_failures,
                        }
                    )
                    cells.append(cell)
                    if primary and cell_failures:
                        primary_failures.append(cell)

    return {
        "contract": spec["contract"],
        "outcomeFree": True,
        "intervalConstruction": spec["intervalConstruction"],
        "simulationReplicates": sims,
        "bootstrapDraws": draws,
        "statistics": list(STATISTICS),
        "cells": cells,
        "primaryStatus": "PASS" if not primary_failures else "FAIL",
        "primaryFailures": primary_failures,
        "interpretation": (
            "PASS validates only the frozen v2 synthetic null behavior of these interval mechanics. "
            "It is not evidence of historical Alpha, model profitability, or deployability."
        ),
    }
