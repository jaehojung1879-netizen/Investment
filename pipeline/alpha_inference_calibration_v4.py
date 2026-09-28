"""Synthetic-only calendar-time self-normalized inference calibration v4.

V3 applied a tuning-free self-normalized (SN) pivot to the signal-date series
of each statistic.  At the 126-session horizon that series is a weekly sample
of overlapping forward sums, so consecutive observations share up to 25 of 26
weeks of the same realized returns, and a 312-week calendar contains only about
twelve non-overlapping windows.  The SN pivot's U1 limit is reached only when
the dependence span is negligible against the sample, which it is not there.

V4 changes one thing.  Every statistic confirmed here is LINEAR in forward
returns with weights fixed at the signal date, so its sum over signal dates can
be rewritten exactly as a sum over calendar weeks of the returns REALIZED in
each week by every cohort then active (the calendar-time portfolio device of
overlapping-holding-period studies).  Each realized shock then enters exactly
one observation: the mechanical overlap is removed without changing the
estimator, and the remaining dependence is only the return process's own.  The
unchanged v3 pivot is then applied to that series with its known exposure
profile.  Spearman rank IC is not linear in returns, cannot be attributed this
way, and is reported descriptively only.

This module reads no files.  It accepts an already-loaded protocol dictionary
and generates invented data from seeded RNG streams.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy.signal import lfilter

from pipeline.alpha_inference_calibration_v1 import (
    _aggregate,
    _passes_metric,
    _row_rank_correlation,
)
from pipeline.alpha_inference_calibration_v3 import _self_normalized_interval

CONTRACT = "ALPHA_INFERENCE_CALIBRATION_V4"
METHOD = "CALENDAR_TIME_ATTRIBUTION_SELF_NORMALIZED"
CONFIRMATORY = (
    "dateMean",
    "selectedMean",
    "selectedMinusUniverse",
    "pairedMseImprovement",
    "rankWeightedSpread",
)
DESCRIPTIVE = ("rankIC",)
BURN_IN = 512
STATUSES = ("PASS", "FAIL", "DATA_INSUFFICIENT")


# --------------------------------------------------------------------------
# protocol
# --------------------------------------------------------------------------
def validate_spec(spec: dict[str, Any]) -> None:
    """Refuse any protocol that is not the v4 contract as frozen."""
    def fail(reason: str) -> None:
        raise ValueError(f"INVALID_V4_PROTOCOL: {reason}")

    if spec.get("contract") != CONTRACT or spec.get("outcomeFree") is not True:
        fail("contract/outcomeFree")
    cfg = spec.get("intervalConstruction", {})
    if cfg.get("method") != METHOD:
        fail("interval method")
    if cfg.get("blockLength") != "NONE" or int(cfg.get("bootstrapDraws", -1)) != 0:
        fail("v4 has no block length and no bootstrap")
    if float(cfg.get("U1CriticalValue", 0.0)) != 66.57:
        fail("U1 critical value")
    stats = spec.get("statistics", {})
    if tuple(stats.get("confirmatory", ())) != CONFIRMATORY or tuple(stats.get("descriptive", ())) != DESCRIPTIVE:
        fail("statistic partition")
    for key, horizon_cfg in spec.get("horizons", {}).items():
        depth = spec.get("minimumConfirmatoryDepth", {}).get(key)
        if depth is None:
            fail(f"no minimum confirmatory depth for horizon {key}")
        if int(horizon_cfg["forwardSessions"]) != int(key):
            fail("horizon key/forwardSessions mismatch")
    for dgp in spec.get("dgps", []):
        if dgp.get("innovation") not in ("GAUSSIAN", "STUDENT_T"):
            fail(f"innovation for {dgp.get('name')}")
        if dgp["innovation"] == "STUDENT_T" and float(dgp.get("studentTDegreesOfFreedom", 0)) <= 2:
            fail("Student-t innovations need more than two degrees of freedom")
        if not 0.0 <= float(dgp.get("phiPredictor", -1)) < 1.0:
            fail("phiPredictor")
    if int(spec.get("simulationReplicates", 0)) < 1:
        fail("simulationReplicates")


def confirmatory_depth_status(spec: dict[str, Any], horizon_sessions: int, evaluation_weeks: int) -> str:
    """ELIGIBLE, or DATA_INSUFFICIENT_FOR_CONFIRMATORY_H{h}_INFERENCE below the calibrated floor."""
    floor = spec["minimumConfirmatoryDepth"].get(str(int(horizon_sessions)))
    if floor is None:
        return f"DATA_INSUFFICIENT_FOR_CONFIRMATORY_H{int(horizon_sessions)}_INFERENCE"
    if int(evaluation_weeks) >= int(floor["calendarWeeks"]):
        return "ELIGIBLE"
    return f"DATA_INSUFFICIENT_FOR_CONFIRMATORY_H{int(horizon_sessions)}_INFERENCE"


# --------------------------------------------------------------------------
# synthetic null
# --------------------------------------------------------------------------
def _innovations(rng: np.random.Generator, size: tuple[int, int], dgp: dict[str, Any]) -> np.ndarray:
    """Unit-variance innovations; Student-t is rescaled by sqrt((nu-2)/nu)."""
    if dgp["innovation"] == "GAUSSIAN":
        return rng.standard_normal(size)
    nu = float(dgp["studentTDegreesOfFreedom"])
    return rng.standard_t(nu, size) * math.sqrt((nu - 2.0) / nu)


def _ar(innovations: np.ndarray, phi: float, sigma: float) -> np.ndarray:
    """Stationary AR(1) with stationary s.d. `sigma`, burn-in discarded."""
    scaled = innovations * sigma * math.sqrt(max(0.0, 1.0 - phi * phi))
    return lfilter([1.0], [1.0, -phi], scaled, axis=0)[BURN_IN:]


def simulate_replicate(
    spec: dict[str, Any],
    dgp: dict[str, Any],
    *,
    horizon: int,
    weeks: int,
    replicate: int,
    dgp_index: int,
) -> dict[str, np.ndarray]:
    """Invented daily returns and signal-date scores for one Monte Carlo replicate.

    Returns and predictors come from separately spawned streams; no predictor is
    a function of any return innovation, so every population null is exactly zero.
    """
    names = int(spec["namesPerDate"])
    step = int(spec["signalStepSessions"])
    sessions = (weeks - 1) * step + horizon
    root = np.random.SeedSequence([int(spec["seed"]), dgp_index, horizon, weeks, replicate])
    outcome_seed, predictor_seed = root.spawn(2)
    out_rng = np.random.default_rng(outcome_seed)
    pred_rng = np.random.default_rng(predictor_seed)

    shared = _ar(_innovations(out_rng, (sessions + BURN_IN, 1), dgp), float(dgp["phiShared"]), float(dgp["sigmaShared"]))
    idio = _ar(
        _innovations(out_rng, (sessions + BURN_IN, names), dgp),
        float(dgp["phiIdiosyncratic"]),
        float(dgp["sigmaIdiosyncratic"]),
    )
    daily = shared + idio

    phi_pred = float(dgp["phiPredictor"])
    scores = {
        key: _ar(pred_rng.standard_normal((weeks + BURN_IN, names)), phi_pred, 1.0)
        for key in ("scoreA", "scoreB", "selectionScore")
    }
    return {"daily": daily, **scores}


def forward_sums(daily: np.ndarray, weeks: int, horizon: int, step: int) -> np.ndarray:
    """Y[t, i] = sum of daily returns over sessions [step*t, step*t + horizon)."""
    if daily.shape[0] != (weeks - 1) * step + horizon:
        raise ValueError("daily panel length does not match weeks/horizon/step")
    cumulative = np.vstack([np.zeros((1, daily.shape[1])), np.cumsum(daily, axis=0)])
    starts = np.arange(weeks) * step
    return cumulative[starts + horizon] - cumulative[starts]


def _centred_rank_weights(score: np.ndarray) -> np.ndarray:
    """Dollar-neutral weights from centred within-date ranks; long leg sums to one."""
    ranks = np.argsort(np.argsort(score, axis=1, kind="stable"), axis=1, kind="stable").astype(float)
    centred = ranks - (score.shape[1] - 1) / 2.0
    long_leg = np.where(centred > 0, centred, 0.0).sum(axis=1, keepdims=True)
    return centred / long_leg


def statistic_designs(spec: dict[str, Any], draw: dict[str, np.ndarray]) -> dict[str, dict[str, Any]]:
    """Signal-date weights and forecast-only terms for every confirmatory statistic.

    Each statistic equals, per signal date t, sum_i weights[t, i] * Y[t, i] + signalTerm[t].
    Selection is taken once at the signal date and held for the whole window.
    """
    score_a, score_b, selection = draw["scoreA"], draw["scoreB"], draw["selectionScore"]
    weeks, names = score_a.shape
    scale = float(spec["syntheticForecastScale"])
    pred_a, pred_b = scale * score_a, scale * score_b

    count = max(1, int(math.ceil(names * float(spec["selectionFraction"]))))
    chosen = np.argpartition(selection, names - count, axis=1)[:, -count:]
    selected = np.zeros((weeks, names))
    np.put_along_axis(selected, chosen, 1.0 / count, axis=1)
    universe = np.full((weeks, names), 1.0 / names)
    none = np.zeros(weeks)
    return {
        "dateMean": {"weights": universe, "signalTerm": none},
        "selectedMean": {"weights": selected, "signalTerm": none},
        "selectedMinusUniverse": {"weights": selected - universe, "signalTerm": none},
        # (pb - y)^2 - (pa - y)^2 = pb^2 - pa^2 - 2 y (pb - pa): the y^2 terms cancel.
        "pairedMseImprovement": {
            "weights": -2.0 * (pred_b - pred_a) / names,
            "signalTerm": np.mean(pred_b**2 - pred_a**2, axis=1),
        },
        "rankWeightedSpread": {"weights": _centred_rank_weights(score_a), "signalTerm": none},
    }


# --------------------------------------------------------------------------
# realization-time attribution and interval
# --------------------------------------------------------------------------
def calendar_time_series(
    daily: np.ndarray,
    weights: np.ndarray,
    horizon: int,
    step: int,
    signal_term: np.ndarray | None = None,
    defined: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Attribute every realized contribution to the calendar week it occurs in.

    Returns (D, x): D[w] is the sum over sessions s in week w of
    sum_i A[s, i] r[s, i], where A[s, i] sums the weights of every defined cohort
    whose window [step*t, step*t + horizon) contains s, plus each defined
    cohort's forecast-only term at its signal week; x[w] is the defined
    cohort-session count in week w divided by the horizon.
    sum(D) equals the sum of the signal-date statistic over defined dates.
    """
    weeks, names = weights.shape
    sessions = daily.shape[0]
    if sessions != (weeks - 1) * step + horizon or daily.shape[1] != names:
        raise ValueError("daily panel does not match cohort weights")
    mask = np.ones(weeks, dtype=bool) if defined is None else np.asarray(defined, dtype=bool)
    live = np.where(mask[:, None], weights, 0.0)
    if not np.isfinite(live).all() or not np.isfinite(daily).all():
        raise ValueError("non-finite synthetic input")

    cum_weights = np.vstack([np.zeros((1, names)), np.cumsum(live, axis=0)])
    cum_count = np.concatenate([[0], np.cumsum(mask.astype(int))])
    s = np.arange(sessions)
    first = np.maximum(0, -(-(s - horizon + 1) // step))
    last = np.minimum(weeks - 1, s // step)
    exposure_weights = cum_weights[last + 1] - cum_weights[first]
    active = (cum_count[last + 1] - cum_count[first]).astype(float)

    calendar_weeks = -(-sessions // step)
    week_of = s // step
    contributions = np.einsum("si,si->s", exposure_weights, daily)
    series = np.bincount(week_of, weights=contributions, minlength=calendar_weeks)
    exposure = np.bincount(week_of, weights=active, minlength=calendar_weeks) / horizon
    if signal_term is not None:
        series[:weeks] += np.where(mask, np.asarray(signal_term, dtype=float), 0.0)
    return series, exposure


def signal_date_series(
    forward: np.ndarray,
    weights: np.ndarray,
    signal_term: np.ndarray | None = None,
) -> np.ndarray:
    """The statistic on each signal date: sum_i weights * Y + forecast-only term."""
    values = np.einsum("ti,ti->t", weights, forward)
    return values if signal_term is None else values + signal_term


def calendar_time_sn_interval(
    series: np.ndarray,
    exposure: np.ndarray,
    critical_value: float,
    near_zero_tolerance: float,
) -> dict[str, float] | None:
    """Self-normalized interval for theta in E[D(w)] = theta * x(w).

    theta_hat = sum D / sum x; residual partial sums R_t = sum_{w<=t} (D - theta_hat x);
    interval theta_hat +/- sqrt(c * sum_t R_t^2 / N) / sum x.  With x identically one
    this is exactly v3's `_self_normalized_interval`.
    """
    d = np.asarray(series, dtype=float)
    x = np.asarray(exposure, dtype=float)
    if not math.isfinite(critical_value) or critical_value <= 0:
        raise ValueError("critical_value must be finite and positive")
    if d.ndim != 1 or d.shape != x.shape or len(d) < 2:
        return None
    if not (np.isfinite(d).all() and np.isfinite(x).all()) or (x < 0).any():
        return None
    total_exposure = float(x.sum())
    if total_exposure <= 0.0:
        return None

    n_obs = len(d)
    estimate = float(d.sum() / total_exposure)
    partial = np.cumsum(d - estimate * x)
    normalizer = float(np.dot(partial, partial))
    scale = n_obs * n_obs * float(np.mean(d * d))
    if not math.isfinite(normalizer) or normalizer <= 0.0 or normalizer <= near_zero_tolerance * scale:
        return None
    half_width = math.sqrt(critical_value * normalizer / n_obs) / total_exposure
    return {
        "estimate": estimate,
        "lower": estimate - half_width,
        "upper": estimate + half_width,
        "width": 2.0 * half_width,
        "selfNormalizer": normalizer,
    }


# --------------------------------------------------------------------------
# calibration
# --------------------------------------------------------------------------
def replicate_intervals(
    spec: dict[str, Any],
    dgp: dict[str, Any],
    *,
    horizon: int,
    weeks: int,
    replicate: int,
    dgp_index: int,
) -> dict[str, dict[str, Any]]:
    """Primary (calendar-time) and comparator (v3 signal-date) intervals for one replicate."""
    step = int(spec["signalStepSessions"])
    cfg = spec["intervalConstruction"]
    critical = float(cfg["U1CriticalValue"])
    tolerance = float(cfg["nearZeroNormalizerRelativeTolerance"])

    draw = simulate_replicate(spec, dgp, horizon=horizon, weeks=weeks, replicate=replicate, dgp_index=dgp_index)
    forward = forward_sums(draw["daily"], weeks, horizon, step)
    out: dict[str, dict[str, Any]] = {}
    for name, design in statistic_designs(spec, draw).items():
        d, x = calendar_time_series(draw["daily"], design["weights"], horizon, step, design["signalTerm"])
        by_date = signal_date_series(forward, design["weights"], design["signalTerm"])
        gap = abs(float(d.sum()) - float(by_date.sum()))
        if gap > 1e-8 * max(1.0, float(np.abs(by_date).sum())):
            raise RuntimeError(f"ATTRIBUTION_IDENTITY_BROKEN: {name} {gap}")
        out[name] = {
            "primary": calendar_time_sn_interval(d, x, critical, tolerance),
            "comparator": _self_normalized_interval(by_date, critical),
        }
    rank_ic = _row_rank_correlation(draw["scoreA"], forward)
    out["rankIC"] = {"primary": None, "comparator": _self_normalized_interval(rank_ic, critical)}
    return out


def run_calibration(spec: dict[str, Any], *, progress: Any = None) -> dict[str, Any]:
    """Execute the frozen v4 synthetic protocol.  No repository data are accepted."""
    validate_spec(spec)
    sims = int(spec["simulationReplicates"])
    acceptance = spec["acceptance"]
    cells: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    insufficient: list[dict[str, Any]] = []

    for dgp_index, dgp in enumerate(spec["dgps"]):
        for horizon_cfg in spec["horizons"].values():
            horizon = int(horizon_cfg["forwardSessions"])
            for weeks_value in horizon_cfg["calendarWeeks"]:
                weeks = int(weeks_value)
                cell: dict[str, Any] = {
                    "dgp": dgp["name"],
                    "horizonSessions": horizon,
                    "calendarWeeks": weeks,
                    "depthStatus": confirmatory_depth_status(spec, horizon, weeks),
                    "nonOverlappingWindows": round(weeks * int(spec["signalStepSessions"]) / horizon, 3),
                }
                if cell["depthStatus"] != "ELIGIBLE":
                    cell.update({"status": "DATA_INSUFFICIENT", "metrics": None, "failures": {}})
                    cells.append(cell)
                    insufficient.append(cell)
                    continue

                records = [
                    replicate_intervals(spec, dgp, horizon=horizon, weeks=weeks, replicate=r, dgp_index=dgp_index)
                    for r in range(sims)
                ]
                metrics: dict[str, Any] = {}
                comparator: dict[str, Any] = {}
                cell_failures: dict[str, list[str]] = {}
                for statistic in CONFIRMATORY:
                    aggregate = _aggregate([rec[statistic]["primary"] for rec in records], sims)
                    ok, why = _passes_metric(aggregate, acceptance)
                    metrics[statistic] = aggregate
                    if not ok:
                        cell_failures[statistic] = why
                for statistic in CONFIRMATORY + DESCRIPTIVE:
                    comparator[statistic] = _aggregate([rec[statistic]["comparator"] for rec in records], sims)
                cell.update({
                    "status": "PASS" if not cell_failures else "FAIL",
                    "metrics": metrics,
                    "failures": cell_failures,
                    "descriptive": {"rankIC": comparator["rankIC"]},
                    "nonGatingV3SignalDateComparator": comparator,
                })
                cells.append(cell)
                if cell_failures:
                    failures.append({k: cell[k] for k in ("dgp", "horizonSessions", "calendarWeeks", "failures")})
                if progress is not None:
                    progress(cell)

    if failures:
        status = "FAIL"
    elif insufficient:
        status = "DATA_INSUFFICIENT"
    else:
        status = "PASS"
    return {
        "contract": spec["contract"],
        "outcomeFree": True,
        "intervalConstruction": spec["intervalConstruction"],
        "simulationReplicates": sims,
        "statistics": spec["statistics"],
        "cells": cells,
        "primaryStatus": status,
        "primaryFailures": failures,
        "interpretation": acceptance["interpretationRule"],
    }
