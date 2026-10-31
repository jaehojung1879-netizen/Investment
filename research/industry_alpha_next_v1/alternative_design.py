"""Design screen for ONE alternative industry study: a calendar-time, fit-free, rank-weighted industry spread.

SYNTHETIC ONLY. No market data, price, return or outcome of any real security or industry is read.

Why an alternative is needed (measured in `inference-calibration-result.json` and the post-hoc diagnostic): the
registered contrast compares out-of-fold forecast errors of two models refitted every year. Each refit carries one
estimation error that is shared by all its test months (26-41% of the loss-differential variance), and the H126/H252
labels overlap 6/12 months, so the KR history holds about 6 (H126) or 4 (H252) effectively independent observations.
No test can be both size-valid and powerful on that; the frozen result shows power <= 15% at a true IC of 0.10.

The alternative removes both sources of dependence by construction instead of correcting for them:

* NO FIT. The signal is a pre-specified block characteristic with a pre-specified sign, cross-sectionally
  residualised on industry momentum (REL_MOM_126) WITHIN each signal date (a per-date regression that uses only that
  date's features), so it measures the block's information INCREMENTAL to momentum but has no time-series estimation
  error and therefore no fold component. Within-date centring removes the market's common move.
* CALENDAR TIME. Each month, a new cohort of centred-rank weights (long the top-ranked industries, short the bottom,
  gross 1) is formed and held for H/21 months; the portfolio return of month m averages the K live cohorts applied to
  month m's one-month industry returns. Every realised return enters the series exactly once, so the series has no
  label overlap (the overlapping-portfolio construction; the repository's v4 calendar-time decomposition rests on the
  same identity), and all ~140 KR months are test months.

The test is a one-sided Newey-West t (Bartlett lag 4, the n^(2/9) rule at n ~ 140) with a self-normalised t
(the repository's SN family) reported beside it. This module only measures size and power on the SAME synthetic worlds
the frozen calibration used; it changes nothing registered and authorises nothing.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from scipy import stats

from . import evaluate as E
from . import inference_calibration as C

MONTHLY_HORIZON = 21
NW_LAG = 4
# With 6-12 industries per date a per-date regression can carry only one or two controls. The one the incremental
# question is about is the existing industry momentum; the common market move is already removed by centring.
CONTROLS = ("REL_MOM_126",)
DGPS = ("N1_GAUSS_CONST", "N2_T4_VOL_REGIME", "N3_T4_REGIME_BETA_LOADED",
        "P05_T4_VOL_REGIME", "P10_T4_VOL_REGIME", "P20_T4_VOL_REGIME")


def matched_monthly_ic(ic, horizon, rho):
    """The `ic` that makes `effect_kappa` at the 21-session horizon equal its value at `horizon`: the SAME planted world."""
    if ic == 0:
        return 0.0
    def mult(h):
        return C.SESSIONS_PER_MONTH * sum(rho ** k for k in range(h // C.SESSIONS_PER_MONTH))
    x = ic / math.sqrt(1 - ic * ic) * (math.sqrt(horizon) / mult(horizon)) * (mult(MONTHLY_HORIZON) / math.sqrt(MONTHLY_HORIZON))
    return x / math.sqrt(1 + x * x)


def residual_signal(group, signal_col, controls):
    """Per-date OLS residual of the signal on the control columns (rank-free, uses only this date's rows)."""
    y = group[signal_col].to_numpy(float)
    X = group[controls].to_numpy(float)
    X = np.column_stack([np.ones(len(y)), (X - X.mean(axis=0)) / np.where(X.std(axis=0) > 0, X.std(axis=0), 1.0)])
    if len(y) <= X.shape[1] + 1:
        return None
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    return y - X @ beta


def centred_rank_weights(values):
    r = np.argsort(np.argsort(values)).astype(float)
    w = r - r.mean()
    s = np.abs(w).sum()
    return w / s if s > 0 else w


def calendar_time_series(frame, signal_col, controls, holding_months, leg_adjust=None):
    """Monthly calendar-time spread return: mean over the K live cohorts of sum_i w_{i,cohort} * r_{i,month}.

    `leg_adjust(month, cohort, industries, weights, month_returns)`, when given, returns an additive change to one
    cohort's leg (used by `inclusion_bound` to place unclassified names); None leaves the series unchanged."""
    pop = frame[frame["cwStatus"].eq("MATURED")]
    dates = sorted(pop["date"].unique())
    weights, returns = {}, {}
    for d, g in pop.groupby("date"):
        if len(g) < E.S.MIN_INDUSTRIES_PER_DATE:
            continue
        res = residual_signal(g, signal_col, controls)
        if res is None:
            continue
        weights[d] = dict(zip(g["industry"], centred_rank_weights(res)))
        y = g["cwRelative"].to_numpy(float)
        returns[d] = dict(zip(g["industry"], y - y.mean()))
    series = []
    for i, d in enumerate(dates):
        if d not in returns or i < holding_months - 1:
            continue
        legs = []
        for k in range(holding_months):
            cohort = dates[i - k]
            w = weights.get(cohort)
            if not w:
                continue
            common = [g for g in w if g in returns[d]]
            if len(common) < 2:
                continue
            wc = np.array([w[g] for g in common])
            wc = wc - wc.mean()
            s = np.abs(wc).sum()
            if s == 0:
                continue
            leg = float((wc / s) @ np.array([returns[d][g] for g in common]))
            if leg_adjust is not None:
                leg += leg_adjust(d, cohort, common, wc / s, returns[d])
            legs.append(leg)
        if legs:
            series.append(float(np.mean(legs)))
    return np.asarray(series)


def tests(x):
    n = len(x)
    lrv = float(C.bartlett_lrv(x, NW_LAG))
    t = x.mean() / math.sqrt(max(lrv, 1e-300) / n)
    return {"nwT": t, "nwReject": bool(stats.norm.sf(t) <= 0.05), "nwRejectHolmFirst": bool(stats.norm.sf(t) <= 0.05 / 36),
            "snT": float(C.sn_statistic(x)), "n": n}


def _one(args):
    protocol, dgp_name, horizon, replicate, seed = args
    dgp = dict(protocol["dgps"][dgp_name])
    dgp["ic"] = matched_monthly_ic(dgp["ic"], horizon, protocol["world"]["plantedRho"])
    rng = np.random.default_rng(np.random.SeedSequence([seed, DGPS.index(dgp_name), horizon, replicate]))
    frame, _ = C.simulate_world(rng, dgp, protocol["world"], MONTHLY_HORIZON, protocol["lengths"]["KR"]["firstSignalMonth"])
    controls = list(CONTROLS)
    x = calendar_time_series(frame, C.PLANTED_COLUMN, controls, horizon // C.SESSIONS_PER_MONTH)
    return tests(x)


def run(replicates=400, workers=4, seed=None):
    protocol = C.load_protocol(formal=True)
    seed = protocol["seeds"]["development"] + 7 if seed is None else seed
    sn_cv = protocol["criticalValues"]["sn"]["0.05"]
    out = {}
    for horizon in (126, 252):
        for dgp in DGPS:
            jobs = [(protocol, dgp, horizon, r, seed) for r in range(replicates)]
            with ProcessPoolExecutor(max_workers=workers) as ex:
                rows = list(ex.map(_one, jobs))
            hits = sum(r["nwReject"] for r in rows)
            out[f"KR_H{horizon}_{dgp}"] = {
                "replicates": replicates, "medianMonths": float(np.median([r["n"] for r in rows])),
                "nwRejectRate": hits / replicates,
                "nwClopperPearson95": [C.MC.clopper_pearson_lower(hits, replicates, 0.025),
                                       C.MC.clopper_pearson_upper(hits, replicates, 0.025)],
                "nwRejectRateHolmFirstStep": float(np.mean([r["nwRejectHolmFirst"] for r in rows])),
                "snRejectRate": float(np.mean([r["snT"] > sn_cv for r in rows]))}
    return {"schema": "INDUSTRY_ALTERNATIVE_DESIGN_SCREEN_V1",
            "evidenceClass": "SYNTHETIC_DESIGN_SCREEN_NOT_A_FORMAL_CALIBRATION",
            "historicalOutcomesRead": 0, "seed": seed, "design": "CALENDAR_TIME_FIT_FREE_RESIDUAL_RANK_SPREAD",
            "nwLag": NW_LAG, "worlds": "the frozen calibration's world and DGPs, KR length, kappa matched to the H126/H252 cell",
            "comparatorFrozenResult": "inference-calibration-result.json (registered C0 power at IC 0.10: H126 15.2%, H252 14.1%)",
            "cells": out}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--replicates", type=int, default=400)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--output")
    args = ap.parse_args(argv)
    text = json.dumps(run(args.replicates, args.workers), indent=1, sort_keys=True)
    if args.output:
        with open(args.output, "w") as fh:
            fh.write(text + "\n")
    else:
        sys.stdout.write(text + "\n")


if __name__ == "__main__":
    main()
