"""Synthetic-only inference calibration for the US H63 controlled factor spread (prerequisite P3).

WHAT IS CALIBRATED. `us-cash-profitability-signal-v1` (PROPOSED_NOT_REGISTERED) names one primary statistic: on each weekly
signal date t, the within-date percentile rank of the feature is OLS-residualised on sector dummies and the percentile ranks of
four controls; weights proportional to the residual, scaled to gross exposure 2 ($1 long / $1 short), earn
S_t = sum_i w(t,i) * Y(t,i) over the next 63 sessions. The estimand is theta = E[S_t] in RETURN units (fraction per H63; x4
annualised). H0: theta <= 0, H1: theta > 0, alpha 0.05 one-sided; the decision interval is the pair of one-sided 95% bounds of one
interval (equivalently a two-sided 90% interval): lower > 0 -> SUPPORTED, upper <= 0 -> REFUTED.

This module asks only whether an interval for theta keeps its nominal error rates under the study's geometry. It reads no file,
no price, no return, no label and no model output: every return here is INVENTED from seeded RNG streams. Real outcome-blind
geometry (names per date, sector shares, feature/control rank correlations, sector share of rank variance) enters only as
constants in the protocol dictionary, copied from committed readiness reports. Nothing here is investment performance.

WHAT IS REUSED. Calendar-time attribution (`alpha_inference_calibration_v4.calendar_time_series`), its self-normalised interval
(`calendar_time_sn_interval`), the signal-date SN interval (`alpha_inference_calibration_v3._self_normalized_interval`) and the
three-state Monte Carlo decision rule (`alpha_inference_mc_decision`) are called, not copied. New here: the US geometry, the
residualised weights, the characteristic and return processes, missing names, unresolved terminal events, and the comparator
intervals (signal-date and calendar-time Newey-West, calendar-time circular block bootstrap).
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy.signal import lfilter
from scipy.stats import norm

from pipeline import alpha_inference_mc_decision as mc
from pipeline.alpha_inference_calibration_v3 import _self_normalized_interval
from pipeline.alpha_inference_calibration_v4 import calendar_time_series, calendar_time_sn_interval

CONTRACT = "US_H63_INFERENCE_CALIBRATION_V1"
HORIZON = 63
STEP = 5
CHARACTERISTICS = ("feature", "accrualProfitability", "tradedValue", "momentum", "volatility")
CONTROLS = CHARACTERISTICS[1:]
METHODS = ("CT_SN", "SD_SN", "SD_NW_L12", "CT_NW_AUTO", "CT_CBB13")
PRIMARY_METHOD = "CT_SN"
BURN_IN = 300


# --------------------------------------------------------------------------
# geometry
# --------------------------------------------------------------------------
def sector_assignment(universe: int, shares: dict[str, float]) -> np.ndarray:
    """Deterministic sector index per name, proportional to the measured sector shares (largest remainder)."""
    names = sorted(shares)
    total = sum(shares.values())
    exact = np.array([shares[n] / total * universe for n in names])
    counts = np.floor(exact).astype(int)
    for k in np.argsort(-(exact - counts))[: universe - counts.sum()]:
        counts[k] += 1
    return np.repeat(np.arange(len(names)), counts)


def innovation_correlation(target: np.ndarray, phi: np.ndarray) -> np.ndarray:
    """Innovation correlation that makes a diagonal VAR(1) with coefficients `phi` have stationary correlation `target`."""
    a = np.sqrt(1.0 - phi**2)
    out = target * (1.0 - np.outer(phi, phi)) / np.outer(a, a)
    np.fill_diagonal(out, 1.0)
    if np.min(np.linalg.eigvalsh(out)) <= 0:
        raise ValueError("innovation correlation is not positive definite")
    return out


def centred_ranks(values: np.ndarray, available: np.ndarray) -> np.ndarray:
    """Percentile ranks centred on zero among available names; 0 for unavailable names."""
    out = np.zeros_like(values, dtype=float)
    idx = np.flatnonzero(available)
    n = len(idx)
    if n:
        order = np.argsort(np.argsort(values[idx], kind="stable"), kind="stable")
        out[idx] = (order + 0.5) / n - 0.5
    return out


def residual_weights(feature_rank: np.ndarray, control_ranks: np.ndarray, sectors: np.ndarray,
                     available: np.ndarray) -> np.ndarray:
    """Gross-2 weights proportional to the OLS residual of the feature rank on sector dummies and control ranks."""
    w = np.zeros(len(feature_rank))
    idx = np.flatnonzero(available)
    if len(idx) == 0:
        return w
    sec = sectors[idx]
    present = np.unique(sec)
    design = np.column_stack([(sec == k).astype(float) for k in present] + [control_ranks[idx, j]
                                                                           for j in range(control_ranks.shape[1])])
    coef, *_ = np.linalg.lstsq(design, feature_rank[idx], rcond=None)
    resid = feature_rank[idx] - design @ coef
    gross = np.abs(resid).sum()
    if gross <= 1e-12:
        return w
    w[idx] = 2.0 * resid / gross
    return w


# --------------------------------------------------------------------------
# synthetic panel
# --------------------------------------------------------------------------
def _innov(rng: np.random.Generator, size, tail: str, nu: float) -> np.ndarray:
    if tail == "GAUSSIAN":
        return rng.standard_normal(size)
    return rng.standard_t(nu, size) * math.sqrt((nu - 2.0) / nu)


def _ar1(x: np.ndarray, phi: float) -> np.ndarray:
    """Stationary unit-variance AR(1) of unit-variance innovations along axis 0, burn-in dropped."""
    return lfilter([1.0], [1.0, -phi], x * math.sqrt(1.0 - phi * phi), axis=0)[BURN_IN:]


def simulate(geometry: dict[str, Any], dgp: dict[str, Any], *, weeks: int, seed_key: tuple[int, ...],
             effect_annual: float = 0.0) -> dict[str, Any]:
    """One invented panel: daily returns, weekly gross-2 residual weights, and the defined-cohort mask."""
    universe = int(dgp.get("universe", geometry["universe"]))
    sectors = sector_assignment(universe, geometry["sectorShares"])
    n_sec = int(sectors.max()) + 1
    sessions = (weeks - 1) * STEP + HORIZON
    root = np.random.SeedSequence(list(seed_key))
    char_seed, ret_seed, miss_seed, term_seed = root.spawn(4)
    crng, rrng, mrng, trng = (np.random.default_rng(s) for s in (char_seed, ret_seed, miss_seed, term_seed))
    tail, nu = dgp["innovation"], float(dgp.get("studentTDegreesOfFreedom", 4.0))

    # --- characteristics (weekly latent VAR(1) + sector effects; quarterly refresh for accounting variables) ---
    target = np.array(dgp.get("characteristicCorrelation", geometry["characteristicCorrelation"]), dtype=float)
    phi = np.array([geometry["weeklyPersistence"][c] for c in CHARACTERISTICS])
    chol = np.linalg.cholesky(innovation_correlation(target, phi))
    eps = crng.standard_normal((weeks + BURN_IN, universe, len(CHARACTERISTICS))) @ chol.T
    latent = np.empty((weeks, universe, len(CHARACTERISTICS)))
    for j in range(len(CHARACTERISTICS)):
        latent[:, :, j] = _ar1(eps[:, :, j], phi[j])
    share = dgp.get("sectorShareOfRankVariance", geometry["sectorShareOfRankVariance"])
    sector_effect = crng.standard_normal((n_sec, len(CHARACTERISTICS)))
    rho = float(target[0, 1])                                        # sector levels of feature and accrual profitability correlate
    sector_effect[:, 1] = rho * sector_effect[:, 0] + math.sqrt(1.0 - rho * rho) * sector_effect[:, 1]
    for j, name in enumerate(CHARACTERISTICS):
        s = float(share[name])
        latent[:, :, j] = math.sqrt(1.0 - s) * latent[:, :, j] + math.sqrt(s) * sector_effect[sectors, j][None, :]
    observed = latent.copy()
    phase = crng.integers(0, 13, universe)                           # staggered filing calendar
    for j, name in enumerate(CHARACTERISTICS):
        if name in geometry["quarterlyRefreshed"]:
            for t in range(weeks):
                stale = (t - phase) % 13 != 0
                if t > 0:
                    observed[t, stale, j] = observed[t - 1, stale, j]

    # --- availability: persistent missingness and unresolved terminal events ---
    p_miss, stay = float(dgp["missingRate"]), float(geometry["missingPersistence"])
    enter = p_miss * (1.0 - stay) / (1.0 - p_miss)
    missing = np.zeros((weeks, universe), dtype=bool)
    missing[0] = mrng.random(universe) < p_miss
    for t in range(1, weeks):
        u = mrng.random(universe)
        missing[t] = np.where(missing[t - 1], u < stay, u < enter)
    alive_until = np.full(universe, sessions)                        # first session a name no longer has a return
    defined = np.ones(weeks, dtype=bool)
    rate = float(dgp["unresolvedTerminalPerYear"])
    n_events = trng.poisson(rate * sessions / 252.0)
    for _ in range(n_events):
        name, session = int(trng.integers(universe)), int(trng.integers(sessions))
        if session < alive_until[name]:
            alive_until[name] = session
    available = ~missing
    for t in range(weeks):
        available[t] &= alive_until > t * STEP
    for name in np.flatnonzero(alive_until < sessions):
        s = alive_until[name]
        first = max(0, -(-(s - HORIZON + 1) // STEP))
        last = min(weeks - 1, s // STEP)
        for t in range(first, last + 1):
            if available[t, name]:
                defined[t] = False                                   # UNRESOLVED: the cohort's statistic is missing

    # --- weekly residualised weights and centred control ranks (rank-linear exposures) ---
    weights = np.zeros((weeks, universe))
    zranks = np.zeros((weeks, universe, len(CONTROLS)))
    for t in range(weeks):
        ranks = np.column_stack([centred_ranks(observed[t, :, j], available[t]) for j in range(len(CHARACTERISTICS))])
        zranks[t] = ranks[:, 1:]
        weights[t] = residual_weights(ranks[:, 0], ranks[:, 1:], sectors, available[t])

    # --- daily returns ---
    ret = dgp["returns"]
    week_of = np.arange(sessions) // STEP
    week_of = np.minimum(week_of, weeks - 1)
    vol_regime = _ar1(rrng.standard_normal((sessions + BURN_IN, 1)), float(ret["logVolPersistence"]))
    vol_regime = np.exp(float(ret["logVolSd"]) * vol_regime - 0.5 * float(ret["logVolSd"]) ** 2)
    market = float(ret["marketMean"]) + float(ret["marketSd"]) * _ar1(_innov(rrng, (sessions + BURN_IN, 1), tail, nu),
                                                                      float(ret["dailyPersistence"]))
    sector_ret = float(ret["sectorSd"]) * _ar1(_innov(rrng, (sessions + BURN_IN, n_sec), tail, nu),
                                               float(ret["dailyPersistence"]))
    premia = np.array([float(ret["controlPremia"][c]) for c in CONTROLS])
    control_ret = premia + float(ret["controlSd"]) * _ar1(_innov(rrng, (sessions + BURN_IN, len(CONTROLS)), tail, nu),
                                                          float(ret["dailyPersistence"]))
    if ret.get("exposureBasis", "RANK") == "RANK":
        expo = zranks[week_of]                                       # exposures linear in the same ranks the weights use
        beta = 1.0 + float(ret["betaOnVolatilityRank"]) * zranks[week_of, :, CONTROLS.index("volatility")]
    else:                                                            # non-gating construct stress: exposures on latent values
        lat = latent[week_of][:, :, 1:]
        expo = np.tanh(lat) * 0.5
        beta = 1.0 + float(ret["betaOnVolatilityRank"]) * np.tanh(latent[week_of][:, :, CHARACTERISTICS.index("volatility")])
    idio_scale = float(ret["idioSd"]) * np.exp(float(ret["idioOnVolatility"]) * latent[week_of][:, :, CHARACTERISTICS.index("volatility")])
    idio = idio_scale * vol_regime * _innov(rrng, (sessions, universe), tail, nu)
    daily = (beta * market + sector_ret[:, sectors] + np.einsum("sij,sj->si", expo, control_ret) + idio)
    alive = np.arange(sessions)[:, None] < alive_until[None, :]
    drift = np.zeros_like(daily)
    if effect_annual:
        w_now = weights[week_of]
        norm2 = np.maximum((w_now**2).sum(axis=1, keepdims=True), 1e-12)
        drift = np.where(alive, (effect_annual / 252.0) * w_now / norm2, 0.0)   # the current cohort earns effect/252 per session
    daily = np.where(alive, daily + drift, 0.0)
    last = available[-1]
    return {"daily": daily, "drift": drift, "weights": weights, "defined": defined, "available": available, "aliveUntil": alive_until,
            "featureAccrualRankCorrelationLastWeek": float(np.corrcoef(
                centred_ranks(observed[-1, :, 0], last)[last], zranks[-1, last, 0])[0, 1])}


def resolve_dgp(protocol: dict[str, Any], dgp: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """(geometry, dgp) with the DGP's overrides applied; the protocol dictionary is not mutated."""
    geometry = {**protocol["geometry"]}
    corr = np.array(geometry["characteristicCorrelation"], dtype=float)
    if "featureAccrualCorrelation" in dgp:
        corr[0, 1] = corr[1, 0] = float(dgp["featureAccrualCorrelation"])
    share = dict(geometry["sectorShareOfRankVariance"])
    if "sectorShareOfRankVarianceFeature" in dgp:
        share["feature"] = float(dgp["sectorShareOfRankVarianceFeature"])
    resolved = {**dgp, "characteristicCorrelation": corr.tolist(), "sectorShareOfRankVariance": share,
                "returns": {**protocol["baseReturns"], **dgp.get("returns", {})}}
    return geometry, resolved


def forward_sums(daily: np.ndarray, weeks: int) -> np.ndarray:
    cumulative = np.vstack([np.zeros((1, daily.shape[1])), np.cumsum(daily, axis=0)])
    starts = np.arange(weeks) * STEP
    return cumulative[starts + HORIZON] - cumulative[starts]


# --------------------------------------------------------------------------
# intervals (all return one-sided 95% bounds as {lower, upper}, i.e. a two-sided 90% interval)
# --------------------------------------------------------------------------
def _bartlett_lrv(e: np.ndarray, lags: int) -> float:
    n = len(e)
    v = float(np.dot(e, e)) / n
    for k in range(1, min(lags, n - 1) + 1):
        v += 2.0 * (1.0 - k / (lags + 1.0)) * float(np.dot(e[k:], e[:-k])) / n
    return v


def newey_west_lags(n: int) -> int:
    """Newey-West (1994) plug-in-free Bartlett rule floor(4 (n/100)^(2/9))."""
    return int(math.floor(4.0 * (n / 100.0) ** (2.0 / 9.0)))


def interval_sd_nw(values: np.ndarray, lags: int, z: float) -> dict[str, float] | None:
    if len(values) < 3:
        return None
    m = float(values.mean())
    se = math.sqrt(max(_bartlett_lrv(values - m, lags), 0.0) / len(values))
    return None if se <= 0 else {"lower": m - z * se, "upper": m + z * se}


def interval_ct_nw(d: np.ndarray, x: np.ndarray, z: float) -> dict[str, float] | None:
    total = float(x.sum())
    if total <= 0 or len(d) < 3:
        return None
    theta = float(d.sum()) / total
    e = d - theta * x
    se = math.sqrt(max(_bartlett_lrv(e, newey_west_lags(len(e))), 0.0) * len(e)) / total
    return None if se <= 0 else {"lower": theta - z * se, "upper": theta + z * se}


def interval_ct_block_bootstrap(d: np.ndarray, x: np.ndarray, block: int, draws: int, alpha: float,
                                rng: np.random.Generator) -> dict[str, float] | None:
    """Circular block bootstrap of calendar weeks; ratio estimator; percentile one-sided bounds."""
    n = len(d)
    if n < 2 * block or float(x.sum()) <= 0:
        return None
    blocks = -(-n // block)
    starts = rng.integers(0, n, (draws, blocks))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(draws, -1)[:, :n] % n
    dx, xx = d[idx].sum(axis=1), x[idx].sum(axis=1)
    ok = xx > 0
    if ok.sum() < draws // 2:
        return None
    theta = dx[ok] / xx[ok]
    return {"lower": float(np.quantile(theta, alpha)), "upper": float(np.quantile(theta, 1.0 - alpha))}


def replicate_intervals(geometry: dict[str, Any], dgp: dict[str, Any], *, weeks: int, seed_key: tuple[int, ...],
                        methods_cfg: dict[str, Any], effect_annual: float = 0.0, interim_weeks: int | None = None
                        ) -> dict[str, Any]:
    """Intervals of every method for one replicate, plus the attribution identity check."""
    sim = simulate(geometry, dgp, weeks=weeks, seed_key=seed_key, effect_annual=effect_annual)
    daily, weights, defined = sim["daily"], sim["weights"], sim["defined"]
    forward = forward_sums(daily, weeks)
    by_date = np.einsum("ti,ti->t", weights, forward)
    d, x = calendar_time_series(daily, weights, HORIZON, STEP, None, defined)
    gap = abs(float(d.sum()) - float(by_date[defined].sum()))
    if gap > 1e-9 * max(1.0, float(np.abs(by_date[defined]).sum())):
        raise RuntimeError(f"ATTRIBUTION_IDENTITY_BROKEN: {gap}")
    s = by_date[defined]
    crit, tol = float(methods_cfg["snCriticalValue"]), float(methods_cfg["nearZeroNormalizerRelativeTolerance"])
    z = float(norm.ppf(1.0 - float(methods_cfg["oneSidedAlpha"])))
    boot_rng = np.random.default_rng(np.random.SeedSequence(list(seed_key) + [999]))
    out = {
        "CT_SN": calendar_time_sn_interval(d, x, crit, tol),
        "SD_SN": _self_normalized_interval(s, crit) if len(s) >= 2 else None,
        "SD_NW_L12": interval_sd_nw(s, int(methods_cfg["signalDateNeweyWestLags"]), z),
        "CT_NW_AUTO": interval_ct_nw(d, x, z),
        "CT_CBB13": interval_ct_block_bootstrap(d, x, int(methods_cfg["blockWeeks"]), int(methods_cfg["bootstrapDraws"]),
                                                float(methods_cfg["oneSidedAlpha"]), boot_rng),
    }
    record = {m: (None if r is None else {"lower": r["lower"], "upper": r["upper"]}) for m, r in out.items()}
    record["_estimate"] = float(s.mean()) if len(s) else None
    record["_effectTheta"] = (float(np.einsum("ti,ti->t", weights, forward_sums(sim["drift"], weeks))[defined].mean())
                              if effect_annual and defined.any() else 0.0)
    record["_definedFraction"] = float(defined.mean())
    record["_sdOfS"] = float(s.std(ddof=1)) if len(s) > 1 else None
    if interim_weeks is not None:
        interim = defined[:interim_weeks]
        record["_interimEstimate"] = float(by_date[:interim_weeks][interim].mean()) if interim.any() else None
    return record


# --------------------------------------------------------------------------
# decisions
# --------------------------------------------------------------------------
def decide(records: list[dict[str, Any]], method: str, theta: float, acceptance: dict[str, Any],
           mc_cfg: dict[str, Any], decision_count: int) -> dict[str, Any]:
    """PASS/FAIL/INCONCLUSIVE for coverage of theta, both one-sided error rates, and undefined frequency."""
    reps = len(records)
    rows = [r[method] for r in records if r[method] is not None]
    n = len(rows)
    covered = sum(1 for r in rows if r["lower"] <= theta <= r["upper"])
    low_err = sum(1 for r in rows if r["lower"] > theta)
    up_err = sum(1 for r in rows if r["upper"] < theta)
    common = {"pass_alpha": float(mc_cfg["passSideOneSidedAlpha"]),
              "fail_alpha": mc.fail_side_alpha(float(mc_cfg["failSideFamilywiseAlpha"]), decision_count)}
    hw = float(acceptance["maximumMonteCarlo95HalfWidth"])
    metrics = {
        "coverage90": mc.classify_metric(covered, n, kind=mc.FLOOR, threshold=float(acceptance["coverageFloor"]),
                                         max_half_width=hw, **common),
        "lowerBoundError": mc.classify_metric(low_err, n, kind=mc.CEILING, threshold=float(acceptance["oneSidedErrorCeiling"]),
                                              max_half_width=hw, **common),
        "upperBoundError": mc.classify_metric(up_err, n, kind=mc.CEILING, threshold=float(acceptance["oneSidedErrorCeiling"]),
                                              max_half_width=hw, **common),
        "undefinedFrequency": mc.classify_metric(reps - n, reps, kind=mc.CEILING,
                                                 threshold=float(acceptance["undefinedFrequencyCeiling"]), **common),
    }
    return {"state": mc.combine_states([m["state"] for m in metrics.values()]),
            "estimates": {k: m["estimate"] for k, m in metrics.items()}, "metrics": metrics}


def lobato_u1_quantile(probability: float, draws: int, steps: int, seed: int) -> float:
    """Monte Carlo quantile of U1 = B(1)^2 / int_0^1 (B(r) - r B(1))^2 dr (check on the tabulated value; no data)."""
    rng = np.random.default_rng(seed)
    out = np.empty(draws)
    chunk = 2000
    r = np.arange(1, steps + 1) / steps
    for start in range(0, draws, chunk):
        m = min(chunk, draws - start)
        b = np.cumsum(rng.standard_normal((m, steps)), axis=1) / math.sqrt(steps)
        bridge = b - r[None, :] * b[:, -1:]
        out[start:start + m] = b[:, -1] ** 2 / np.mean(bridge**2, axis=1)
    return float(np.quantile(out, probability))
