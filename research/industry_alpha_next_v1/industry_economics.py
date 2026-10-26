"""What an industry rank spread is worth to a long-only book, separated from market beta and industry momentum.

SYNTHETIC ONLY. No market data, price, return or outcome of any real security or industry is read. This is the
economics half of the alternative design (`alternative_design.py` is its inference half): it fixes, before any real
number exists, how a calendar-time industry spread would be turned into a statement an investor can act on.

* PURE SELECTION is the intercept of the monthly active return regressed on the market's excess return and on an
  industry-momentum spread built by the SAME construction from REL_MOM_126 ranks. A signal that only tilts toward
  high-beta industries, or only re-labels momentum, has a raw spread and no intercept.
* LONG-ONLY. The book is the equal-weight industry benchmark plus a bounded active tilt in the spread's direction
  (gross active 50%, at most 10 points per industry, no short position). That is what a Top120 investor can hold.
  KR sector ETFs track a different classification, so industries are held as constituent baskets and every unit of
  industry weight traded pays the stock-level cost.
* COSTS are the repository's own dated KR schedule (`benchmark_alpha.REALISTIC_COSTS`, sell tax 30bp to 15bp) charged
  by `portfolio_validation._turnover_cost`, the function the replay charges, on the month-to-month change in weights.
  Drift between rebalances is ignored, which understates turnover slightly.
* CONCENTRATION is reported, not optimised: the largest active weight, the active HHI and the share of months whose
  largest active weight sits in one industry.

The world here is a small monthly model, separate from the frozen calibration's daily world (which carries no market
return to regress on, and whose code is pinned by its formal result): r[g,m] = beta[g] x M[m] + kappa x s[g,m-1] + e.
"""
from __future__ import annotations

import argparse
import json
import math
import sys

import numpy as np

from pipeline import benchmark_alpha as BA
from pipeline import portfolio_validation as PV

from . import alternative_design as A
from . import inference_calibration as C

INDUSTRIES = 12
ACTIVE_GROSS = 0.50
ACTIVE_CAP = 0.10
HOLDING_MONTHS = 6            # H126
MARKET_MONTHLY = (0.006, 0.055)   # mean, sd of the market's monthly excess return (assumption)
IDIO_MONTHLY = 0.035          # industry idiosyncratic sd, the frozen world's 0.008 daily x sqrt(21)
BETA_RANGE = (0.7, 1.3)
RHO = 0.95
FIRST_DATE = "2015-01-31"


# --------------------------------------------------------------------------- #
# World
# --------------------------------------------------------------------------- #
def world(rng, months, ic, *, beta_loading=0.0, signal="PLANTED"):
    """Monthly industry returns and signals. `ic` is the signal's correlation with next month's idiosyncratic return."""
    beta = rng.uniform(*BETA_RANGE, size=INDUSTRIES)
    bz = (beta - beta.mean()) / beta.std()
    s = np.zeros((months + 1, INDUSTRIES))
    s[0] = rng.standard_normal(INDUSTRIES)
    for m in range(1, months + 1):
        s[m] = RHO * s[m - 1] + math.sqrt(1 - RHO ** 2) * rng.standard_normal(INDUSTRIES)
    kappa = ic / math.sqrt(1 - ic * ic) * IDIO_MONTHLY
    market = rng.normal(*MARKET_MONTHLY, size=months + 1)
    eps = rng.normal(0, IDIO_MONTHLY, size=(months + 1, INDUSTRIES))
    r = beta[None, :] * market[:, None] + eps
    r[1:] += kappa * s[:-1]
    mom = np.full_like(r, np.nan)
    for m in range(6, months + 1):
        mom[m] = (r[m - 5:m + 1] - r[m - 5:m + 1].mean(axis=1, keepdims=True)).sum(axis=0)
    observed = {"PLANTED": s, "BETA": np.tile(bz, (months + 1, 1)), "MOMENTUM": mom}[signal].copy()
    if beta_loading:
        observed = beta_loading * bz[None, :] + math.sqrt(1 - beta_loading ** 2) * observed
    return {"returns": r, "market": market, "signal": observed, "momentum": mom, "beta": beta}


def cohort_weights(signal_row, control_row=None):
    """Centred-rank weights (sum 0, gross 1) on the signal, residualised on the control within the date."""
    x = signal_row.copy()
    if control_row is not None and np.isfinite(control_row).all():
        X = np.column_stack([np.ones(len(x)), control_row])
        x = x - X @ np.linalg.lstsq(X, x, rcond=None)[0]
    return A.centred_rank_weights(x)


def composite(w, start, end):
    """Calendar-time composite at month m: mean of the cohorts formed at m-K+1..m."""
    return w[start:end].mean(axis=0)


def long_only(spread_weights):
    """Equal-weight benchmark plus the spread scaled to gross active ACTIVE_GROSS, shrunk (never reshaped) until no
    active weight exceeds ACTIVE_CAP and no industry goes short. Scaling keeps the active weights summing to zero."""
    bench = np.full(INDUSTRIES, 1.0 / INDUSTRIES)
    gross = float(np.abs(spread_weights).sum())
    if gross == 0:
        return bench, np.zeros(INDUSTRIES)
    w = spread_weights / gross
    scale = min(ACTIVE_GROSS, ACTIVE_CAP / max(w.max(), 1e-12), bench[0] / max(-w.min(), 1e-12))
    return bench + scale * w, scale * w


def evaluate(path, *, control_momentum=True, first_date=FIRST_DATE):
    """Monthly active returns, turnover, dated cost and the market / momentum decomposition of one path."""
    r, market, signal, mom = path["returns"], path["market"], path["signal"], path["momentum"]
    months = r.shape[0] - 1
    cohorts = np.zeros((months + 1, INDUSTRIES))
    mom_cohorts = np.zeros_like(cohorts)
    for m in range(6, months + 1):
        cohorts[m] = cohort_weights(signal[m], mom[m] if control_momentum else None)
        mom_cohorts[m] = cohort_weights(mom[m])
    start = 6 + HOLDING_MONTHS - 1
    dates = _month_ends(first_date, months + 1)
    cfg = BA.cost_config({})
    gross, net, spread, mom_spread, turnover, cost, max_active, hhi, top = [], [], [], [], [], [], [], [], []
    prior = None
    for m in range(start, months):
        w_spread = composite(cohorts, m - HOLDING_MONTHS + 1, m + 1)
        w_long, active = long_only(w_spread)
        nxt = r[m + 1] - r[m + 1].mean()
        spread.append(float(w_spread @ nxt))
        mom_spread.append(float(composite(mom_cohorts, m - HOLDING_MONTHS + 1, m + 1) @ nxt))
        weights = {f"G{g}": float(w_long[g]) for g in range(INDUSTRIES)}
        trade = PV._turnover_cost(weights, prior or {}, [{"ticker": k, "region": "KR"} for k in weights], cfg,
                                  as_of=dates[m]) if prior is not None else {"turnover": 0.0, "cost": 0.0}
        prior = weights
        g_ret = float(active @ nxt)
        gross.append(g_ret)
        net.append(g_ret - trade["cost"])
        turnover.append(trade["turnover"])
        cost.append(trade["cost"])
        max_active.append(float(np.abs(active).max()))
        hhi.append(float(((active / np.abs(active).sum()) ** 2).sum()) if np.abs(active).sum() > 0 else 0.0)
        top.append(int(np.argmax(active)))
    y = np.asarray(net)
    X = np.column_stack([np.ones(len(y)), market[start + 1:months + 1], np.asarray(mom_spread)])
    coef = np.linalg.lstsq(X, y, rcond=None)[0]
    resid = y - X @ coef
    xtx = np.linalg.inv(X.T @ X)
    lrv = C.bartlett_lrv(resid * (X @ xtx[:, 0]) * len(y), A.NW_LAG)
    alpha_se = math.sqrt(float(lrv) / len(y))
    share_top = max(np.bincount(top, minlength=INDUSTRIES)) / len(top)
    return {"months": len(y), "grossActivePctYr": 1200 * float(np.mean(gross)), "netActivePctYr": 1200 * float(np.mean(net)),
            "costPctYr": 1200 * float(np.mean(cost)), "oneWayTurnoverPerYr": 12 * float(np.mean(turnover)),
            "spreadPctYr": 1200 * float(np.mean(spread)),
            "alphaPctYr": 1200 * float(coef[0]), "alphaT": float(coef[0] / alpha_se) if alpha_se > 0 else 0.0,
            "marketBeta": float(coef[1]), "momentumLoading": float(coef[2]),
            "maxActiveWeight": float(np.max(max_active)), "meanActiveHhi": float(np.mean(hhi)),
            "shareOfMonthsLargestTiltInModalIndustry": float(share_top)}


def _month_ends(first, n):
    y, mo = int(first[:4]), int(first[5:7])
    out = []
    for _ in range(n):
        out.append(f"{y:04d}-{mo:02d}-28")
        mo += 1
        if mo == 13:
            y, mo = y + 1, 1
    return out


# --------------------------------------------------------------------------- #
# Screen
# --------------------------------------------------------------------------- #
# `ic` is the H126 information coefficient of the frozen calibration's scale, converted to this world's one-month IC
# by the same `matched_monthly_ic` the alternative design uses (H126 0.10 is a one-month 0.046).
def _m(ic):
    return A.matched_monthly_ic(ic, 126, RHO)


SCENARIOS = {
    "NULL": dict(ic=0.0),
    "PURE_IC05": dict(ic=_m(0.05)), "PURE_IC10": dict(ic=_m(0.10)), "PURE_IC20": dict(ic=_m(0.20)),
    "BETA_TILT_ONLY": dict(ic=0.0, signal="BETA"),
    "MOMENTUM_RELABEL": dict(ic=_m(0.10), signal="MOMENTUM", residualise=False),
    "IC10_HALF_BETA_LOADED": dict(ic=_m(0.10), beta_loading=0.5),
}


def run(replicates=500, seed=None, lengths=(132, 300)):
    protocol = C.load_protocol(formal=True)
    seed = protocol["seeds"]["development"] + 13 if seed is None else seed
    out = {}
    for months in lengths:
        for name, kw in SCENARIOS.items():
            rows = []
            for rep in range(replicates):
                rng = np.random.default_rng(np.random.SeedSequence([seed, months, list(SCENARIOS).index(name), rep]))
                kw = dict(kw)
                residualise = kw.pop("residualise", True)
                rows.append(evaluate(world(rng, months + 6, **kw), control_momentum=residualise))
            keys = rows[0].keys()
            cell = {k: round(float(np.median([r[k] for r in rows])), 4) for k in keys}
            cell["alphaRejectRateOneSided5"] = round(float(np.mean([r["alphaT"] > 1.645 for r in rows])), 4)
            cell["netActivePositiveShare"] = round(float(np.mean([r["netActivePctYr"] > 0 for r in rows])), 4)
            out[f"M{months}_{name}"] = cell
    return {"schema": "INDUSTRY_SPREAD_ECONOMICS_SCREEN_V1", "evidenceClass": "SYNTHETIC_DESIGN_SCREEN_NOT_A_FORMAL_CALIBRATION",
            "historicalOutcomesRead": 0, "seed": seed, "replicates": replicates,
            "assumptions": {"industries": INDUSTRIES, "activeGross": ACTIVE_GROSS, "activeCap": ACTIVE_CAP,
                            "holdingMonths": HOLDING_MONTHS, "marketMonthlyMeanSd": list(MARKET_MONTHLY),
                            "industryIdioMonthly": IDIO_MONTHLY, "costs": "benchmark_alpha.REALISTIC_COSTS[KR], dated",
                            "driftIgnored": True},
            "cells": out}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--replicates", type=int, default=500)
    ap.add_argument("--output")
    args = ap.parse_args(argv)
    text = json.dumps(run(args.replicates), indent=1, sort_keys=True)
    if args.output:
        with open(args.output, "w") as fh:
            fh.write(text + "\n")
    else:
        sys.stdout.write(text + "\n")


if __name__ == "__main__":
    main()
