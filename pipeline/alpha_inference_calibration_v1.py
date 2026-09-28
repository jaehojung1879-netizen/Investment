"""Synthetic-only inference calibration for the future Alpha v5 design.

This module is deliberately incapable of reading repository market data.  It
accepts only an already-loaded protocol dictionary, generates invented shocks,
and measures moving-block interval behavior under exact nulls.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy.signal import lfilter


STATISTICS = (
    "dateMean",
    "pairedMseImprovement",
    "rankIC",
    "selectedMean",
    "selectedMinusUniverse",
)


def _ar_series(rng: np.random.Generator, length: int, phi: float, sigma: float, width: int = 1) -> np.ndarray:
    """Stationary Gaussian AR(1), using an invented burn-in only."""
    burn = 512
    innovation_sigma = sigma * math.sqrt(max(0.0, 1.0 - phi * phi))
    eps = rng.normal(0.0, innovation_sigma, size=(length + burn, width))
    values = lfilter([1.0], [1.0, -phi], eps, axis=0)
    return values[burn:]


def _row_rank_correlation(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Fast Spearman correlation for continuous synthetic rows (ties have probability zero)."""
    rx = np.argsort(np.argsort(x, axis=1, kind="stable"), axis=1, kind="stable").astype(float)
    ry = np.argsort(np.argsort(y, axis=1, kind="stable"), axis=1, kind="stable").astype(float)
    rx -= rx.mean(axis=1, keepdims=True)
    ry -= ry.mean(axis=1, keepdims=True)
    denom = np.sqrt((rx * rx).sum(axis=1) * (ry * ry).sum(axis=1))
    out = np.divide((rx * ry).sum(axis=1), denom, out=np.full(len(x), np.nan), where=denom > 0)
    return out


def simulate_null_date_statistics(
    spec: dict[str, Any],
    dgp: dict[str, Any],
    *,
    horizon: int,
    weeks: int,
    replicate: int,
    dgp_index: int,
) -> dict[str, np.ndarray]:
    """Generate per-date statistics whose population null is exactly zero.

    Outcome and predictor RNG streams are spawned separately.  No predictor is
    a function of any target innovation, including the serial shared shock.
    """
    names = int(spec["namesPerDate"])
    step = int(spec["signalStepSessions"])
    total_sessions = (weeks - 1) * step + horizon
    root = np.random.SeedSequence([int(spec["seed"]), dgp_index, horizon, weeks, replicate])
    outcome_seed, predictor_seed = root.spawn(2)
    out_rng = np.random.default_rng(outcome_seed)
    pred_rng = np.random.default_rng(predictor_seed)

    shared = _ar_series(out_rng, total_sessions, float(dgp["phiShared"]), float(dgp["sigmaShared"]))[:, 0]
    idio = _ar_series(
        out_rng,
        total_sessions,
        float(dgp["phiIdiosyncratic"]),
        float(dgp["sigmaIdiosyncratic"]),
        width=names,
    )
    daily = shared[:, None] + idio
    cumulative = np.vstack([np.zeros((1, names)), np.cumsum(daily, axis=0)])
    starts = np.arange(weeks) * step
    y = cumulative[starts + horizon] - cumulative[starts]

    score_a = pred_rng.normal(size=(weeks, names))
    score_b = pred_rng.normal(size=(weeks, names))
    selection_score = pred_rng.normal(size=(weeks, names))
    scale = float(spec["syntheticForecastScale"])
    pred_a, pred_b = scale * score_a, scale * score_b

    selection_count = max(1, int(math.ceil(names * float(spec["selectionFraction"]))))
    selected_idx = np.argpartition(selection_score, names - selection_count, axis=1)[:, -selection_count:]
    selected_y = np.take_along_axis(y, selected_idx, axis=1)
    universe_mean = y.mean(axis=1)

    return {
        "dateMean": universe_mean,
        "pairedMseImprovement": np.mean((pred_b - y) ** 2 - (pred_a - y) ** 2, axis=1),
        "rankIC": _row_rank_correlation(score_a, y),
        "selectedMean": selected_y.mean(axis=1),
        "selectedMinusUniverse": selected_y.mean(axis=1) - universe_mean,
    }


def _bootstrap_plan(n: int, block: int, draws: int, seed_parts: list[int]) -> tuple[np.ndarray, int]:
    """Starts for the repository's non-circular moving-block bootstrap."""
    count = math.ceil(n / block)
    rng = np.random.default_rng(np.random.SeedSequence(seed_parts))
    starts = rng.integers(0, n - block + 1, size=(draws, count), dtype=np.int32)
    return starts, n - block * (count - 1)


def _bootstrap_means(series: np.ndarray, starts: np.ndarray, block: int, final_length: int) -> np.ndarray:
    """Exact mean of block_sample_indices without materializing every sampled date."""
    n = len(series)
    prefix = np.concatenate(([0.0], np.cumsum(series, dtype=float)))
    full = prefix[block:] - prefix[:-block]
    partial = prefix[final_length:] - prefix[:-final_length]
    if starts.shape[1] == 1:
        total = partial[starts[:, 0]]
    else:
        total = full[starts[:, :-1]].sum(axis=1) + partial[starts[:, -1]]
    return total / n


def _interval(series: np.ndarray, starts: np.ndarray, block: int, final_length: int, tail: float) -> dict[str, float] | None:
    if not np.isfinite(series).all():
        return None
    draws = _bootstrap_means(series, starts, block, final_length)
    if not np.isfinite(draws).all():
        return None
    lo, hi = np.quantile(draws, [tail, 1.0 - tail])
    return {
        "estimate": float(np.mean(series)),
        "lower": float(lo),
        "upper": float(hi),
        "width": float(hi - lo),
    }


def _mc_half_width(p: float, n: int) -> float:
    return float(1.96 * math.sqrt(max(0.0, p * (1.0 - p)) / n))


def _aggregate(records: list[dict[str, float] | None], simulations: int) -> dict[str, float]:
    measured = [r for r in records if r is not None]
    undefined = 1.0 - len(measured) / simulations
    if not measured:
        return {
            "coverage": float("nan"),
            "positiveFalsePositive": float("nan"),
            "twoSidedRejection": float("nan"),
            "medianWidth": float("nan"),
            "undefinedFrequency": undefined,
            "coverageMc95HalfWidth": float("nan"),
            "positiveFpMc95HalfWidth": float("nan"),
        }
    coverage = float(np.mean([r["lower"] <= 0.0 <= r["upper"] for r in measured]))
    positive_fp = float(np.mean([r["lower"] > 0.0 for r in measured]))
    rejection = float(np.mean([not (r["lower"] <= 0.0 <= r["upper"]) for r in measured]))
    return {
        "coverage": coverage,
        "positiveFalsePositive": positive_fp,
        "twoSidedRejection": rejection,
        "medianWidth": float(np.median([r["width"] for r in measured])),
        "undefinedFrequency": undefined,
        "coverageMc95HalfWidth": _mc_half_width(coverage, len(measured)),
        "positiveFpMc95HalfWidth": _mc_half_width(positive_fp, len(measured)),
    }


def _passes_metric(metric: dict[str, float], acceptance: dict[str, Any]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    if metric["coverage"] < float(acceptance["materialCoverageFloor"]):
        failures.append("MATERIAL_UNDERCOVERAGE")
    if metric["positiveFalsePositive"] > float(acceptance["directionalFalsePositiveCeiling"]):
        failures.append("DIRECTIONAL_FALSE_POSITIVE_EXCESS")
    if metric["undefinedFrequency"] > float(acceptance["undefinedFrequencyCeiling"]):
        failures.append("UNDEFINED_FREQUENCY_EXCESS")
    max_mc = float(acceptance["maximumMonteCarlo95HalfWidth"])
    if metric["coverageMc95HalfWidth"] > max_mc or metric["positiveFpMc95HalfWidth"] > max_mc:
        failures.append("MONTE_CARLO_PRECISION_INSUFFICIENT")
    return not failures, failures


def run_calibration(spec: dict[str, Any]) -> dict[str, Any]:
    """Execute the frozen synthetic protocol.  No repository data are accepted."""
    if spec.get("contract") != "ALPHA_INFERENCE_CALIBRATION_V1" or not spec.get("outcomeFree"):
        raise ValueError("INVALID_CALIBRATION_PROTOCOL")
    sims = int(spec["simulationReplicates"])
    draws = int(spec["bootstrapDraws"])
    tail = float(spec["confidence"]["tailQuantile"])
    min_blocks = int(spec["minimumEffectiveBlocks"])
    acceptance = spec["acceptance"]
    cells: list[dict[str, Any]] = []
    primary_failures: list[dict[str, Any]] = []

    for dgp_index, dgp in enumerate(spec["dgps"]):
        for horizon_key, horizon_cfg in spec["horizons"].items():
            horizon = int(horizon_cfg["forwardSessions"])
            for weeks in horizon_cfg["calendarWeeks"]:
                stats_by_rep = [
                    simulate_null_date_statistics(
                        spec,
                        dgp,
                        horizon=horizon,
                        weeks=int(weeks),
                        replicate=replicate,
                        dgp_index=dgp_index,
                    )
                    for replicate in range(sims)
                ]
                for block in horizon_cfg["candidateBlocks"]:
                    block = int(block)
                    effective_blocks = int(weeks) // block
                    primary = block == int(horizon_cfg["primaryBlock"])
                    cell: dict[str, Any] = {
                        "dgp": dgp["name"],
                        "horizonSessions": horizon,
                        "calendarWeeks": int(weeks),
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
                    starts, final_length = _bootstrap_plan(
                        int(weeks),
                        block,
                        draws,
                        [int(spec["seed"]), 7001, dgp_index, horizon, int(weeks), block],
                    )
                    metrics: dict[str, Any] = {}
                    cell_failures: dict[str, list[str]] = {}
                    for statistic in STATISTICS:
                        records = [
                            _interval(rep_stats[statistic], starts, block, final_length, tail)
                            for rep_stats in stats_by_rep
                        ]
                        aggregate = _aggregate(records, sims)
                        ok, failures = _passes_metric(aggregate, acceptance)
                        metrics[statistic] = aggregate
                        if not ok:
                            cell_failures[statistic] = failures
                    cell.update({
                        "status": "PASS" if not cell_failures else "FAIL",
                        "metrics": metrics,
                        "failures": cell_failures,
                    })
                    cells.append(cell)
                    if primary and cell_failures:
                        primary_failures.append(cell)

    return {
        "contract": spec["contract"],
        "outcomeFree": True,
        "simulationReplicates": sims,
        "bootstrapDraws": draws,
        "statistics": list(STATISTICS),
        "cells": cells,
        "primaryStatus": "PASS" if not primary_failures else "FAIL",
        "primaryFailures": primary_failures,
        "interpretation": (
            "PASS validates only the frozen synthetic null behavior of these interval mechanics. "
            "It is not evidence of historical Alpha, model profitability, or deployability."
        ),
    }
