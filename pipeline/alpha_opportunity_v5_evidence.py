"""Evidence layer of the alpha-opportunity-model-v5 execution harness. Research only.

This module turns evaluated predictions into the registered confirmatory
intervals and claim statuses. It reads no file and no price panel of its own:
it is handed already-built arrays, so every function is exercisable on synthetic
data, and it is OUTSIDE the sealed preregistration's dependency closure (the
reviewed harness is a separate change from the frozen protocol).

WHAT IS CALLED, NOT COPIED. The interval is the calibrated one:
`alpha_inference_calibration_v4.calendar_time_sn_interval` (the frozen
ALPHA_INFERENCE_CALIBRATION_V5 engine file, pinned by hash in the sealed spec),
called with the sealed U1 critical value and near-zero tolerance. The rank weights
of `rankWeightedSpread` are `alpha_inference_calibration_v4._centred_rank_weights`.
The only thing this module adds is the REAL-DATA attribution of each cohort's
realised relative return to calendar weeks.

WHY THE ATTRIBUTION IS NOT THE ENGINE'S `calendar_time_series`. The calibration
simulates additive daily returns that every cohort shares. The frozen target is a
compounded ratio, `Close[exit]/Close[entry]-1` minus the benchmark's. It has an
exact additive decomposition that is still linear in prices with weights fixed at
the signal date: the increment realised in session s is
`(Close[s]-Close[s-1]) / Close[entry]` for the stock minus the same for the
benchmark, and these telescope to the frozen label exactly. The increment is
cohort-specific (it is divided by that cohort's own entry price), so the engine's
shared-panel einsum cannot be used, but `calendar_time_attribution` below is the
same identity and is proven equal to the engine's `calendar_time_series` on
additive synthetic data. Both estimator and estimand are unchanged: the sum of D
over calendar weeks is asserted equal to the sum of the signal-date statistic on
every series, to floating tolerance, or the run raises.

A session with no printed close carries a zero increment and the whole move shows
on the next session that has one (the level is never used as a return, price or
endpoint substitute: entry and exit closes are still required to exist).
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from . import alpha_inference_calibration_v4 as ENGINE
from .alpha_inference_calibration_v3 import _self_normalized_interval

PASS = "PASS"
FAIL = "FAIL"
INCONCLUSIVE = "INCONCLUSIVE"
DATA_INSUFFICIENT = "DATA_INSUFFICIENT"
INFRASTRUCTURE_ERROR = "INFRASTRUCTURE_ERROR"
NOT_EVALUATED = "NOT_EVALUATED"

# Frozen in the sealed spec (`claims.primary.precedenceWithinClaim` and
# `claims.overall.rule`); tests compare both tuples with the spec's own text.
CLAIM_PRECEDENCE = (INFRASTRUCTURE_ERROR, DATA_INSUFFICIENT, FAIL, INCONCLUSIVE, PASS)
OVERALL_PRECEDENCE = (INFRASTRUCTURE_ERROR, FAIL, INCONCLUSIVE, DATA_INSUFFICIENT, PASS)

# The three confirmatory conjuncts of CREDIBLE_INCREMENTAL_EXPECTED_RETURN.
CONJUNCTS = ("pairedMseImprovement_B4_vs_B0", "pairedMseImprovement_B4_vs_B2", "rankWeightedSpread_B4")

LOWER_ABOVE_ZERO = "LOWER_BOUND_ABOVE_ZERO"
CONTAINS_ZERO = "CONTAINS_ZERO"
REFUTED = "UPPER_BOUND_BELOW_ZERO"
UNDEFINED = "UNDEFINED"

ECONOMIC_MIN_SELECTED_DATES = 52
ECONOMIC_STATUSES = ("ECONOMIC_CANDIDATE_SUPPORTED", "NOT_SUPPORTED", "PERIOD_CONCENTRATED",
                     "DATA_INSUFFICIENT_SELECTED_DATES", "NOT_EVALUATED")


# --------------------------------------------------------------------------- #
# Interval states, claim status, overall status: the frozen state machine.
# --------------------------------------------------------------------------- #
def interval_state(interval) -> str:
    """Where an interval sits against the outside option's own value, zero."""
    if not interval or interval.get("lower") is None or interval.get("upper") is None:
        return UNDEFINED
    lower, upper = interval["lower"], interval["upper"]
    if not (math.isfinite(lower) and math.isfinite(upper)):
        return UNDEFINED
    if lower > 0:
        return LOWER_ABOVE_ZERO
    if upper < 0:
        return REFUTED
    return CONTAINS_ZERO


def claim_status(states, *, data_insufficient_reason=None, infrastructure_reason=None) -> str:
    """PASS / FAIL / INCONCLUSIVE / DATA_INSUFFICIENT / INFRASTRUCTURE_ERROR for one claim.

    Precedence is the frozen `precedenceWithinClaim`: a machinery failure, then a
    registered data/gate/depth/undefined-interval shortfall, then refutation, then
    'not established'. An undefined conjunct is DATA_INSUFFICIENT and is never
    dropped: a claim is a conjunction, so a missing member cannot pass and must not
    read as a refutation either.
    """
    states = list(states)
    if infrastructure_reason:
        return INFRASTRUCTURE_ERROR
    if data_insufficient_reason or len(states) != len(CONJUNCTS) or UNDEFINED in states:
        return DATA_INSUFFICIENT
    if REFUTED in states:
        return FAIL
    if CONTAINS_ZERO in states:
        return INCONCLUSIVE
    return PASS


def overall_status(claim_statuses) -> str:
    """INFRASTRUCTURE_ERROR > FAIL > INCONCLUSIVE > DATA_INSUFFICIENT > PASS; PASS needs every claim."""
    statuses = list(claim_statuses)
    if not statuses:
        return DATA_INSUFFICIENT
    for label in OVERALL_PRECEDENCE[:-1]:
        if label in statuses:
            return label
    return PASS if all(s == PASS for s in statuses) else DATA_INSUFFICIENT


def economic_tier(claim, *, selected_minus_universe, selected_mean, selected_dates, half_estimates) -> dict:
    """ECONOMIC_CANDIDATE_FINDING, evaluated only when the primary claim is PASS.

    A conditional candidate-date opportunity, never a portfolio, deployability or capacity
    claim (meaning, margin, notional, ADV and slippage stay blocked in the spec).
    """
    base = {"name": "ECONOMIC_CANDIDATE_FINDING", "portfolioEvidence": False,
            "limits": "conditional candidate-date opportunity; margin, notional, ADV and slippage blocked"}
    if claim != PASS:
        return {**base, "status": "NOT_EVALUATED", "reason": "PRIMARY_CLAIM_NOT_PASS"}
    states = (interval_state(selected_minus_universe), interval_state(selected_mean))
    if selected_dates < ECONOMIC_MIN_SELECTED_DATES or UNDEFINED in states:
        return {**base, "status": "DATA_INSUFFICIENT_SELECTED_DATES",
                "definedSelectedDates": int(selected_dates)}
    if any(s != LOWER_ABOVE_ZERO for s in states):
        return {**base, "status": "NOT_SUPPORTED", "definedSelectedDates": int(selected_dates)}
    halves_positive = all(h is not None and h > 0 for h in half_estimates)
    return {**base, "status": "ECONOMIC_CANDIDATE_SUPPORTED" if halves_positive else "PERIOD_CONCENTRATED",
            "definedSelectedDates": int(selected_dates), "halfEstimates": list(half_estimates)}


# --------------------------------------------------------------------------- #
# Signal-date designs: every confirmatory statistic is sum_i w(t,i) Y(t,i) + f(t).
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Design:
    weights: np.ndarray
    signal_term: float
    defined: bool


def paired_mse_design(baseline, alternative) -> Design:
    """(p_base - y)^2 - (p_alt - y)^2 = p_base^2 - p_alt^2 - 2 y (p_base - p_alt); y^2 cancels."""
    n = len(baseline)
    return Design(-2.0 * (baseline - alternative) / n, float(np.mean(baseline**2 - alternative**2)), True)


def rank_weighted_spread_design(score, tickers) -> Design:
    """Dollar-neutral centred within-date rank weights; ties broken by ticker ascending.

    The rows are put into ticker order first, so a stable argsort breaks ties by ticker and
    the result cannot depend on the order the caller supplied.
    """
    order = np.argsort(np.asarray(tickers, dtype=object), kind="stable")
    ranked = np.asarray(score, dtype=float)[order][None, :]
    weights_sorted = ENGINE._centred_rank_weights(ranked)[0]
    weights = np.empty_like(weights_sorted)
    weights[order] = weights_sorted
    return Design(weights, 0.0, True)


def selected_designs(expected, cost, n):
    """S_t: predicted gross relative return minus the ex-ante round trip strictly above zero."""
    chosen = (np.asarray(expected, dtype=float) - float(cost)) > 0
    count = int(chosen.sum())
    universe = np.full(n, 1.0 / n)
    if count == 0:
        zero = np.zeros(n)
        empty = Design(zero, 0.0, False)
        return chosen, empty, empty, empty
    picked = np.where(chosen, 1.0 / count, 0.0)
    return (chosen,
            Design(picked, -float(cost), True),                       # net target: Y - c
            Design(picked - universe, 0.0, True),                     # gross, same-date selection value
            Design(picked, -2.0 * float(cost), True))                 # descriptive cost x2 stress


def date_designs(group, *, has_b3, has_b5=True) -> tuple[dict[str, Design], dict]:
    """All designs for one signal date. `group` must be one date's rows in ticker order."""
    n = len(group)
    tickers = group.ticker.to_numpy()
    p = {name: group[name].to_numpy(float) for name in ("pB0", "pB1", "pB2", "pB4")}
    designs = {
        "dateMean": Design(np.full(n, 1.0 / n), 0.0, True),
        "pairedMseImprovement_B4_vs_B0": paired_mse_design(p["pB0"], p["pB4"]),
        "pairedMseImprovement_B4_vs_B2": paired_mse_design(p["pB2"], p["pB4"]),
        "rankWeightedSpread_B4": rank_weighted_spread_design(p["pB4"], tickers),
        "pairedMseImprovement_B4_vs_B1": paired_mse_design(p["pB1"], p["pB4"]),
    }
    if has_b5:
        designs["pairedMseImprovement_B5_vs_B4"] = paired_mse_design(p["pB4"], group["pB5"].to_numpy(float))
    if has_b3:
        designs["pairedMseImprovement_B4_vs_B3"] = paired_mse_design(group["pB3"].to_numpy(float), p["pB4"])
    cost = float(group.roundTripCost.iloc[0])
    chosen, selected_mean, selected_minus, selected_x2 = selected_designs(p["pB4"], cost, n)
    designs["selectedMean"] = selected_mean
    designs["selectedMinusUniverse"] = selected_minus
    designs["selectedMeanCostX2"] = selected_x2
    return designs, {"selectedCount": int(chosen.sum()), "names": n, "roundTripCost": cost}


# --------------------------------------------------------------------------- #
# Realisation-time attribution of real, compounded cohort returns.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Cohort:
    first_session: int
    gross: np.ndarray        # length H: sum_i w_i * increment_i(k), k = 1..H
    signal_term: float
    signal_week: int
    defined: bool


def calendar_time_attribution(cohorts, session_week, horizon, n_weeks):
    """(D, x): contribution and exposure per calendar week. Same identity as the engine's
    `calendar_time_series`, generalised to per-cohort increments."""
    d = np.zeros(n_weeks)
    x = np.zeros(n_weeks)
    for c in cohorts:
        if not c.defined:
            continue
        weeks = np.asarray(session_week[c.first_session:c.first_session + horizon])
        if len(weeks) != horizon or (weeks < 0).any():
            raise ValueError("COHORT_WINDOW_OUTSIDE_CALENDAR")
        np.add.at(d, weeks, c.gross)
        np.add.at(x, weeks, 1.0)
        d[c.signal_week] += c.signal_term
    return d, x / horizon


def session_weeks(days) -> np.ndarray:
    """Consecutive integer id of each session's calendar week (weeks without a session get none)."""
    codes, _ = pd.factorize(pd.DatetimeIndex(days).to_period("W"))
    return codes.astype(int)


def aligned_close(frame, days) -> np.ndarray:
    """Close on every calendar session; missing and non-positive closes are NaN, never filled."""
    close = pd.to_numeric(frame["Close"], errors="coerce").reindex(days).to_numpy(float)
    close[~np.isfinite(close) | (close <= 0)] = np.nan
    return close


def _levels(window):
    """(n, H+1) closes -> level carried across sessions with no print. Endpoints must exist."""
    if not np.isfinite(window[:, 0]).all() or not np.isfinite(window[:, -1]).all():
        raise ValueError("ENDPOINT_MISSING_FOR_MATURED_LABEL")
    valid = np.isfinite(window)
    index = np.where(valid, np.arange(window.shape[1]), -1)
    last = np.maximum.accumulate(index, axis=1)
    return np.take_along_axis(window, last, axis=1)


def cohort_increments(closes, bench, first_entry, horizon):
    """(n, H) per-session contributions to each name's gross relative return, telescoping to Y."""
    window = np.vstack([c[first_entry:first_entry + horizon + 1] for c in closes])
    b_window = bench[first_entry:first_entry + horizon + 1][None, :]
    if window.shape[1] != horizon + 1 or b_window.shape[1] != horizon + 1:
        raise ValueError("CALENDAR_TOO_SHORT")
    stock, b = _levels(window), _levels(b_window)
    stock_inc = np.diff(stock, axis=1) / stock[:, [0]]
    bench_inc = np.diff(b, axis=1) / b[:, [0]]
    return stock_inc - bench_inc


def _relative(interval):
    return None if interval is None else {k: float(v) for k, v in interval.items()}


def calendar_interval(series, exposure, critical, tolerance):
    return _relative(ENGINE.calendar_time_sn_interval(series, exposure, critical, tolerance))


def signal_date_interval(values, critical):
    return _relative(_self_normalized_interval(np.asarray(values, dtype=float), critical))


def horizon_evidence(table, *, days, closes_by_ticker, bench_close, horizon, critical, tolerance, has_b3,
                     has_b5=True):
    """Every registered interval for one horizon cell from its evaluation table.

    `table` holds ONLY evaluation rows (matured, eligible, exit at or before the cutoff, dates
    with enough names) with the columns `date`, `ticker`, `forwardRelativeReturn`,
    `roundTripCost` and one prediction column per rung. Returns the intervals plus the per-date
    values the descriptive layer reuses.
    """
    days = pd.DatetimeIndex(days)
    week_of = session_weeks(days)
    cohorts: dict[str, list[Cohort]] = {}
    values: dict[str, list[tuple[str, float | None]]] = {}
    counts = []
    for date in sorted(table.date.unique()):
        group = table.loc[table.date.eq(date)].sort_values("ticker", kind="stable")
        entry = int(days.searchsorted(pd.Timestamp(date), side="right"))
        signal_pos = int(days.searchsorted(pd.Timestamp(date), side="left"))
        if signal_pos >= len(days) or days[signal_pos] != pd.Timestamp(date):
            raise ValueError("SIGNAL_DATE_NOT_A_SESSION: " + str(date))
        y = group.forwardRelativeReturn.to_numpy(float)
        increments = cohort_increments([closes_by_ticker[t] for t in group.ticker], bench_close, entry, horizon)
        if not np.allclose(increments.sum(axis=1), y, rtol=0.0, atol=1e-9):
            raise ValueError("ATTRIBUTION_IDENTITY_BROKEN: increments do not telescope to the label on " + str(date))
        designs, meta = date_designs(group, has_b3=has_b3, has_b5=has_b5)
        counts.append({"date": str(date), **meta})
        for name, design in designs.items():
            gross = design.weights @ increments if design.defined else np.zeros(horizon)
            cohorts.setdefault(name, []).append(
                Cohort(entry + 1, gross, design.signal_term, int(week_of[signal_pos]), design.defined))
            values.setdefault(name, []).append(
                (str(date), float(design.weights @ y + design.signal_term) if design.defined else None))
    first_week = min(c.signal_week for c in next(iter(cohorts.values())))
    last_week = max(int(week_of[c.first_session + horizon - 1]) for c in next(iter(cohorts.values())))
    intervals = {}
    for name, series in cohorts.items():
        d, x = calendar_time_attribution(series, week_of, horizon, int(week_of.max()) + 1)
        d, x = d[first_week:last_week + 1], x[first_week:last_week + 1]
        defined_values = np.array([v for _, v in values[name] if v is not None], dtype=float)
        gap = abs(float(d.sum()) - float(defined_values.sum()))
        if gap > 1e-8 * max(1.0, float(np.abs(defined_values).sum())):
            raise ValueError(f"ATTRIBUTION_IDENTITY_BROKEN: {name} {gap}")
        interval = calendar_interval(d, x, critical, tolerance) if len(defined_values) else None
        intervals[name] = ({**interval, "calendarWeeks": int(len(d)), "definedSignalDates": int(len(defined_values)),
                            "signalDates": len(values[name])} if interval else
                           {"status": UNDEFINED, "calendarWeeks": int(len(d)),
                            "definedSignalDates": int(len(defined_values)), "signalDates": len(values[name])})
    return {"intervals": intervals, "perDate": values, "selection": counts}


# --------------------------------------------------------------------------- #
# Descriptive-only instruments. None of these can pass, fail or rescue a claim.
# --------------------------------------------------------------------------- #
def per_date_descriptives(table):
    """rankIC (Spearman), within-date slope and pooled absolute calibration, from B4's forecasts."""
    rows = []
    for date in sorted(table.date.unique()):
        g = table.loc[table.date.eq(date)].sort_values("ticker", kind="stable")
        mu, y = g.pB4.to_numpy(float), g.forwardRelativeReturn.to_numpy(float)
        ic = float(spearmanr(mu, y).statistic) if np.ptp(mu) > 0 and np.ptp(y) > 0 else None
        variance = float(np.var(mu))
        slope = float(np.mean((mu - mu.mean()) * (y - y.mean())) / variance) if variance > 0 else None
        rows.append({"date": str(date), "rankIC": ic, "withinDateSlope": slope, "sMu": float(mu.mean()),
                     "sY": float(y.mean()), "sMu2": float(np.mean(mu**2)), "sMuY": float(np.mean(mu * y))})
    return pd.DataFrame(rows)


def _mean_interval(values, critical):
    finite = np.array([v for v in values if v is not None and math.isfinite(v)], dtype=float)
    if len(finite) < 2:
        return {"status": UNDEFINED, "dates": int(len(finite))}
    interval = signal_date_interval(finite, critical)
    return ({**interval, "dates": int(len(finite))} if interval else {"status": UNDEFINED, "dates": int(len(finite))})


def descriptive_summary(table, critical):
    per_date = per_date_descriptives(table)
    mu_bar, y_bar = per_date.sMu.mean(), per_date.sY.mean()
    variance = per_date.sMu2.mean() - mu_bar**2
    covariance = per_date.sMuY.mean() - mu_bar * y_bar
    slope = float(covariance / variance) if variance > 1e-18 else None
    return {
        "rankIC": {"role": "DESCRIPTIVE_ONLY_NEVER_A_GATE", "interval": "SIGNAL_DATE_SELF_NORMALIZED",
                   **_mean_interval(per_date.rankIC.tolist(), critical)},
        "withinDateSlope": {"role": "DESCRIPTIVE_ONLY", "interval": "SIGNAL_DATE_SELF_NORMALIZED",
                            **_mean_interval(per_date.withinDateSlope.tolist(), critical)},
        "absoluteCalibration": {"role": "DESCRIPTIVE_ONLY", "interval": "POINT_ESTIMATE_ONLY",
                                "slope": slope,
                                "intercept": None if slope is None else float(y_bar - slope * mu_bar)},
    }


def logistic_descriptives(table, critical):
    """Brier, log loss and pooled date-balanced ECE of the separate Logistic head. Never a gate."""
    from . import alpha_opportunity_v2_evaluation as E
    probability = table.prob.to_numpy(float)
    if not np.isfinite(probability).all():
        return {"status": "UNAVAILABLE", "reason": "LOGISTIC_HEAD_NOT_FITTED_FOR_EVERY_EVALUATION_FOLD",
                "role": "DESCRIPTIVE_ONLY_NEVER_A_GATE"}
    rows = []
    frame = table.assign(probabilityNetOutperform=table.prob, grossExpectedAlpha=table.pB4,
                         trainingBaseRate=table.baseRate, trainingMeanReturn=table.pB0)
    for date in sorted(frame.date.unique()):
        rows.append({"date": str(date), **E.date_summary(frame.loc[frame.date.eq(date)])})
    summary = pd.DataFrame(rows)
    return {"status": "MEASURED", "role": "DESCRIPTIVE_ONLY_NEVER_A_GATE",
            "brierImprovement": _mean_interval(summary.brierImprovement.tolist(), critical),
            "logLossImprovement": _mean_interval(summary.logLossImprovement.tolist(), critical),
            "pooledEce": float(E.pooled_ece(summary)), "dates": int(len(summary))}


def annual_estimates(per_date, names):
    """Per-year mean of each per-date statistic and the fraction of years with a positive mean."""
    out = {}
    for name in names:
        if name not in per_date:
            continue
        frame = pd.DataFrame(per_date[name], columns=["date", "value"]).dropna()
        if frame.empty:
            out[name] = {"byYear": {}, "fractionPositive": None}
            continue
        by_year = frame.groupby(frame.date.str[:4]).value.mean()
        out[name] = {"byYear": {str(k): float(v) for k, v in by_year.items()},
                     "fractionPositive": float((by_year > 0).mean())}
    return out


def half_estimates(per_date_values, dates):
    """Point estimate of a statistic in each chronological half of the scheduled date list."""
    dates = sorted(dates)
    middle = len(dates) // 2
    lookup = {d: v for d, v in per_date_values}
    halves = []
    for part in (dates[:middle], dates[middle:]):
        vals = [lookup[d] for d in part if lookup.get(d) is not None]
        halves.append(float(np.mean(vals)) if vals else None)
    return halves
