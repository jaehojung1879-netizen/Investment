"""KR alpha discovery tournament v1 — evaluation, multiplicity diagnostics and the frozen verdict.

Every function here reads OUTCOMES (realised labels or valued paths) and is reached by the execution harness only behind its permit and durable lock.
The statistics are standard and implemented in full here so that their assumptions are visible:

* moving-block bootstrap of the daily log-growth difference (block 126 sessions: the label overlap);
* Deflated Sharpe Ratio (Bailey & Lopez de Prado 2014) on NON-overlapping 21-session blocks;
* Probability of Backtest Overfitting by combinatorially symmetric cross-validation (Bailey, Borwein, Lopez de Prado, Zhu 2017);
* Hansen (2005) Superior Predictive Ability, consistent p-value, stationary bootstrap (Politis & Romano 1994).

Classification accuracy is reported as a diagnostic only and decides nothing.
"""
from __future__ import annotations

import itertools
import math

import numpy as np
from scipy.stats import norm, rankdata

from . import kr_alpha_tournament as T
from . import kr_alpha_tournament_models as M
from . import kr_industry_anatomy as I

EULER_GAMMA = 0.5772156649015329


# --------------------------------------------------------------------------- #
# Prediction quality (outer)
# --------------------------------------------------------------------------- #
def prediction_diagnostics(forecasts, labels, round_trip_cost, secondary_column=None):
    """Per outer anchor with an ensemble forecast: rank IC of the ensemble's calibrated mean forecast against the realised H126 rank, top-minus-bottom
    quintile spread of the economic label, decile monotonicity, cross-sectional OOS R^2, calibration by forecast quintile, top-tail precision,
    disagreement, and a classification-accuracy DIAGNOSTIC. Rows without a matured, eligible label are skipped (never zero)."""
    ic, spread, mono, r2_num, r2_den, precision, accuracy, disagreement, secondary = {}, {}, {}, 0.0, 0.0, [], [], [], {}
    calib = {q: [] for q in range(5)}
    for day in sorted(forecasts):
        f = forecasts[day]
        if "mu" not in f:
            continue
        rows = f["rows"]
        ok = labels["eligible"].to_numpy(bool)[rows] & np.isfinite(labels["yEcon"].to_numpy(float)[rows])
        if ok.sum() < T.SELECTION["minNamesPerIcDate"]:
            continue
        mu, post = f["mu"][ok], f["muPost"][ok]
        y = labels["yEcon"].to_numpy(float)[rows][ok]
        c = labels["C_CROSS_SECTIONAL_RANK"].to_numpy(float)[rows][ok]
        ic[day] = M.spearman(mu, c)
        pct = (rankdata(mu, method="average") - 0.5) / len(mu)
        q = np.minimum((pct * 5).astype(int), 4)
        means = [float(np.mean(y[q == k])) if (q == k).any() else np.nan for k in range(5)]
        spread[day] = means[4] - means[0]
        dec = np.minimum((pct * 10).astype(int), 9)
        dmeans = [float(np.mean(y[dec == k])) for k in range(10) if (dec == k).any()]
        if len(dmeans) == 10:
            mono[day] = float(np.mean(np.diff(dmeans) > 0))
        for k in range(5):
            if (q == k).any():
                calib[k].append((float(np.mean(mu[q == k])), means[k]))
        r2_num += float(np.sum((y - y.mean() - (mu - mu.mean())) ** 2))
        r2_den += float(np.sum((y - y.mean()) ** 2))
        admitted = post > round_trip_cost
        if admitted.any():
            precision.append(float(np.mean(y[admitted] > 0)))
        accuracy.append(float(np.mean((mu > 0) == (y > 0))))
        disagreement.append(float(np.mean(np.sqrt(f["disagreement"]))))
        if secondary_column is not None:
            s = labels[secondary_column].to_numpy(float)[rows][ok]
            secondary[day] = M.spearman(mu, s)
    series = np.array([v for v in ic.values() if np.isfinite(v)])
    hac = I.newey_west_mean(series, T.OUTER_IC_HAC_LAG) if len(series) else {"mean": None, "se": None, "n": 0}
    lower = hac["mean"] - 1.959963984540054 * hac["se"] if hac.get("se") is not None else None
    sec = np.array([v for v in secondary.values() if np.isfinite(v)])
    return {"rankIc": {"dates": int(len(series)), "mean": hac["mean"], "median": float(np.median(series)) if len(series) else None,
                       "ir": float(series.mean() / series.std(ddof=1)) if len(series) > 2 and series.std(ddof=1) > 0 else None,
                       "hacSe": hac.get("se"), "hacLag": T.OUTER_IC_HAC_LAG, "lower95": lower,
                       "positiveShare": float(np.mean(series > 0)) if len(series) else None},
            "topMinusBottomQuintile": _mean_dict(spread), "decileMonotonicity": _mean_dict(mono),
            "crossSectionalOosR2": 1 - r2_num / r2_den if r2_den > 0 else None,
            "calibrationByForecastQuintile": {str(k): {"meanForecast": float(np.mean([a for a, _ in v])) if v else None,
                                                       "meanRealised": float(np.nanmean([b for _, b in v])) if v else None} for k, v in calib.items()},
            "topTailPrecision": float(np.mean(precision)) if precision else None,
            "meanForecastDisagreementSd": float(np.mean(disagreement)) if disagreement else None,
            "classificationAccuracyDiagnosticOnly": float(np.mean(accuracy)) if accuracy else None,
            "secondaryH252RankIc": {"dates": int(len(sec)), "mean": float(sec.mean()) if len(sec) else None,
                                    "role": "DESCRIPTIVE_SECONDARY_HORIZON_OF_THE_SAME_H126_PROCESS"},
            "perAnchorIc": {k: (v if np.isfinite(v) else None) for k, v in ic.items()}}


def _mean_dict(values):
    v = np.array([x for x in values.values() if np.isfinite(x)])
    return {"dates": int(len(v)), "mean": float(v.mean()) if len(v) else None}


# --------------------------------------------------------------------------- #
# Economic quality of a valued path
# --------------------------------------------------------------------------- #
def daily_returns(path):
    nav = np.array([r["nav"] for r in path], float)
    return np.r_[0.0, nav[1:] / nav[:-1] - 1.0]


def max_drawdown(nav):
    nav = np.asarray(nav, float)
    return float(np.min(nav / np.maximum.accumulate(nav) - 1.0)) if len(nav) else None


def path_metrics(path):
    nav = np.array([r["nav"] for r in path], float)
    r = daily_returns(path)[1:]
    years = len(r) / 252
    log_growth = float(np.sum(np.log1p(r)) / years) if years > 0 else None
    downside = r[r < 0]
    trades = [p["trade"] for p in path if p["trade"]]
    return {"sessions": len(path), "netReturn": float(nav[-1] - 1.0), "cagr": float(nav[-1] ** (1 / years) - 1) if years > 0 else None,
            "annualLogGrowth": log_growth, "annualVolatility": float(np.std(r, ddof=1) * math.sqrt(252)) if len(r) > 2 else None,
            "downsideVolatility": float(math.sqrt(np.mean(np.minimum(r, 0) ** 2)) * math.sqrt(252)) if len(r) else None,
            "maxDrawdown": max_drawdown(nav), "costDrag": float(sum(t["costFraction"] for t in trades) / years) if years > 0 else None,
            "oneWayTurnoverPerYear": float(sum(t["turnover"] for t in trades) / years) if years > 0 else None,
            "meanActiveWeight": float(np.mean([p["activeWeight"] for p in path])), "meanActiveNames": float(np.mean([p["activeNames"] for p in path])),
            "shareOfSessionsFullyPassive": float(np.mean([p["activeNames"] == 0 for p in path])),
            "maxActiveWeight": float(max(p["maxActiveWeight"] for p in path)), "meanActiveHhi": float(np.mean([p["activeHhi"] for p in path])),
            "downsideObservations": int(len(downside))}


def log_growth_difference(path, passive_path):
    """Daily log-return difference (path minus passive) on the common session set."""
    a = {p["date"]: v for p, v in zip(path, np.log1p(daily_returns(path)))}
    b = {p["date"]: v for p, v in zip(passive_path, np.log1p(daily_returns(passive_path)))}
    days = sorted(set(a) & set(b))[1:]
    return days, np.array([a[d] - b[d] for d in days])


def annualised_pp(diff):
    return float(np.mean(diff) * 252 * 100) if len(diff) else None


def period_slices(days, diff):
    out = {}
    for name, (lo, hi) in T.PERIODS.items():
        sel = np.array([lo <= d <= hi for d in days], bool)
        out[name] = {"sessions": int(sel.sum()), "gPp": annualised_pp(diff[sel]) if sel.any() else None}
    return out


def leave_largest_contributor_out(g_pp, contributions, sessions):
    """G minus the annualised arithmetic active contribution of the single largest positive contributor (approximate; registered)."""
    if not contributions:
        return {"gPp": g_pp, "largest": None, "contributionPp": 0.0}
    largest = max(sorted(contributions), key=lambda t: contributions[t])
    pp = contributions[largest] * 252 / max(1, sessions) * 100
    return {"gPp": g_pp - max(0.0, pp), "largest": largest, "contributionPp": pp}


def blocks(diff, size=T.STRIDE_KR_SESSIONS):
    n = len(diff) // size
    return np.array([diff[i * size:(i + 1) * size].sum() for i in range(n)])


# --------------------------------------------------------------------------- #
# Multiplicity
# --------------------------------------------------------------------------- #
def moving_block_bootstrap(diff, draws=T.BOOTSTRAP_DRAWS, block=T.BOOTSTRAP_BLOCK_SESSIONS, seed=T.RANDOM_SEED):
    diff = np.asarray(diff, float)
    n = len(diff)
    if n < 2 * block:
        return {"status": "TOO_SHORT", "lower95": None, "upper95": None}
    rng = np.random.default_rng(seed)
    k = math.ceil(n / block)
    stats = np.empty(draws)
    for b in range(draws):
        starts = rng.integers(0, n - block + 1, k)
        sample = np.concatenate([diff[s:s + block] for s in starts])[:n]
        stats[b] = sample.mean() * 252 * 100
    return {"status": "OK", "draws": draws, "blockSessions": block, "lower95": float(np.quantile(stats, 0.025)),
            "upper95": float(np.quantile(stats, 0.975))}


def deflated_sharpe(block_returns, trial_sharpes, n_trials):
    x = np.asarray(block_returns, float)
    n = len(x)
    if n < 10 or x.std(ddof=1) == 0:
        return {"status": "TOO_SHORT", "dsr": None}
    sr = float(x.mean() / x.std(ddof=1))
    skew = float(np.mean((x - x.mean()) ** 3) / x.std(ddof=0) ** 3)
    kurt = float(np.mean((x - x.mean()) ** 4) / x.std(ddof=0) ** 4)
    trials = np.asarray([s for s in trial_sharpes if np.isfinite(s)], float)
    var = float(trials.var(ddof=1)) if len(trials) > 1 else 0.0
    n_trials = max(int(n_trials), 2)
    sr0 = math.sqrt(var) * ((1 - EULER_GAMMA) * norm.ppf(1 - 1 / n_trials) + EULER_GAMMA * norm.ppf(1 - 1 / (n_trials * math.e)))
    denom = 1 - skew * sr + (kurt - 1) / 4 * sr ** 2
    if denom <= 0:
        return {"status": "DEGENERATE_MOMENTS", "dsr": None}
    z = (sr - sr0) * math.sqrt(n - 1) / math.sqrt(denom)
    return {"status": "OK", "blockSharpe": sr, "sr0": sr0, "trialSharpeVariance": var, "nTrials": n_trials, "blocks": n, "skew": skew,
            "kurtosis": kurt, "dsr": float(norm.cdf(z))}


def pbo_cscv(matrix, groups=T.PBO_GROUPS):
    """matrix: (blocks x configurations) active block returns. Returns the PBO and the logit distribution summary."""
    M_ = np.asarray(matrix, float)
    keep = np.isfinite(M_).all(axis=0)
    M_ = M_[:, keep]
    t, n = M_.shape
    if n < 2 or t < groups * 2:
        return {"status": "TOO_SMALL", "pbo": None, "configurations": int(n)}
    parts = np.array_split(np.arange(t), groups)
    sx = np.vstack([M_[p].sum(axis=0) for p in parts])
    sxx = np.vstack([(M_[p] ** 2).sum(axis=0) for p in parts])
    cnt = np.array([len(p) for p in parts], float)
    logits = []
    for combo in itertools.combinations(range(groups), groups // 2):
        ins = np.zeros(groups, bool)
        ins[list(combo)] = True

        def sharpe(mask):
            c = cnt[mask].sum()
            m = sx[mask].sum(axis=0) / c
            v = sxx[mask].sum(axis=0) / c - m ** 2
            return m / np.sqrt(np.maximum(v, 1e-300))
        sr_in, sr_out = sharpe(ins), sharpe(~ins)
        best = int(np.lexsort((np.arange(n), -sr_in))[0])
        omega = (rankdata(sr_out)[best]) / (n + 1)
        logits.append(math.log(omega / (1 - omega)))
    logits = np.array(logits)
    return {"status": "OK", "pbo": float(np.mean(logits <= 0)), "combinations": int(len(logits)), "configurations": int(n), "blocks": int(t),
            "medianLogit": float(np.median(logits))}


def stationary_bootstrap_indices(n, mean_block, rng):
    p = 1.0 / mean_block
    idx = np.empty(n, int)
    idx[0] = rng.integers(0, n)
    for i in range(1, n):
        idx[i] = rng.integers(0, n) if rng.random() < p else (idx[i - 1] + 1) % n
    return idx


def spa_test(differentials, draws=T.BOOTSTRAP_DRAWS, mean_block=T.SPA_MEAN_BLOCK, seed=T.RANDOM_SEED):
    """Hansen SPA (consistent). differentials: (blocks x strategies) performance minus the benchmark's (here: active block log returns, so the
    benchmark is 0). H0: no strategy has a positive expected differential."""
    d = np.asarray(differentials, float)
    d = d[:, np.isfinite(d).all(axis=0)]
    n, m = d.shape
    if n < 20 or m < 1:
        return {"status": "TOO_SHORT", "pValue": None}
    rng = np.random.default_rng(seed)
    dbar = d.mean(axis=0)
    boots = np.empty((draws, m))
    for b in range(draws):
        boots[b] = d[stationary_bootstrap_indices(n, mean_block, rng)].mean(axis=0)
    omega = np.sqrt(n) * boots.std(axis=0, ddof=0)
    omega = np.where(omega > 0, omega, np.inf)
    t_obs = max(0.0, float(np.max(np.sqrt(n) * dbar / omega)))
    threshold = -np.sqrt((omega ** 2 / n) * 2 * math.log(math.log(n)))
    g = np.where(dbar <= threshold, dbar, 0.0)          # Hansen's mu^c: only clearly poor strategies keep their (negative) mean
    t_star = np.maximum(0.0, np.max(np.sqrt(n) * (boots - dbar + g) / omega, axis=1))
    return {"status": "OK", "pValue": float(np.mean(t_star >= t_obs)), "statistic": t_obs, "strategies": int(m), "blocks": int(n),
            "meanBlock": mean_block, "draws": draws}


# --------------------------------------------------------------------------- #
# The frozen verdict
# --------------------------------------------------------------------------- #
def verdict(evidence):
    """`evidence` keys: integrity {pathsComplete, identityUnchanged, signalCoveragePercent}, gPp, bootstrapLower, gCostX2Pp, periodsPositive,
    gLeaveLargestOutPp, dsr, spaUniverseP, pbo, icLower95. Returns {code, verdict, checks}. Missing evidence never passes a check.
    The SPA check reads the TOURNAMENT-WIDE Hansen SPA p-value (`spaUniverseP`); the one-strategy primary comparison is descriptive only and is
    not an input here."""
    integ = evidence["integrity"]
    if not integ["pathsComplete"] or not integ["identityUnchanged"] or integ["signalCoveragePercent"] < T.MIN_SIGNAL_COVERAGE_PERCENT:
        return {"code": "E", "verdict": T.VERDICTS["E"], "checks": {"integrity": integ}}

    def gt(x, bound):
        return x is not None and np.isfinite(x) and x > bound

    def ge(x, bound):
        return x is not None and np.isfinite(x) and x >= bound

    def le(x, bound):
        return x is not None and np.isfinite(x) and x <= bound
    g = evidence["gPp"]
    checks = {"gAtLeastMeaningful": ge(g, T.MEANINGFUL_G_PP), "bootstrapLowerAboveZero": gt(evidence["bootstrapLower"], 0.0),
              "costX2Positive": gt(evidence["gCostX2Pp"], 0.0), "periodsPositive": (evidence["periodsPositive"] or 0) >= T.MIN_PERIODS_POSITIVE,
              "leaveLargestOutPositive": gt(evidence["gLeaveLargestOutPp"], 0.0), "dsr": ge(evidence["dsr"], T.DSR_MIN),
              "spaUniverse": le(evidence["spaUniverseP"], T.SPA_MAX_P), "pbo": le(evidence["pbo"], T.PBO_MAX), "predictiveIc": gt(evidence["icLower95"], 0.0)}
    checks = {k: bool(v) for k, v in checks.items()}
    if all(checks.values()):
        code = "A"
    elif gt(g, 0.0):
        code = "B"
    elif checks["predictiveIc"]:
        code = "C"
    else:
        code = "D"
    return {"code": code, "verdict": T.VERDICTS[code], "checks": checks, "nextStep": T.STOP_RULES["INFORMATION_LIMITED"] if code == "D"
            else T.STOP_RULES["ANY_VERDICT"]}
