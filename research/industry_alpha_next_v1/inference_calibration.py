"""Full paired-OOF synthetic calibration of the Industry Alpha inference: type I error and power.

SYNTHETIC ONLY. No git object, price, membership, return or outcome of any real security or industry is read.

What is calibrated is the WHOLE registered chain, not a proxy series. Every replicate:

1. simulates daily industry returns on the real KR session calendar (`replay_calendar`), so H126/H252 forward labels
   overlap exactly as they would (one monthly signal, 6 or 12 months of shared future);
2. builds the 12 registered H1 columns at each month-end signal, with REL_MOM_126 and DOWNSIDE_VOL_126 computed from
   the simulated past returns and the slow accounting / concentration / liquidity columns as persistent AR(1) panels;
3. applies MCAR industry attrition, the calendar maturity rule and the registered thin-date rule through the UNCHANGED
   `evaluate.admit`;
4. fits the base and the alternative with the UNCHANGED `evaluate.oof_predictions` (yearly walk-forward, purge plus
   21-session embargo, train-only preprocessing, weighted ridge) and forms the UNCHANGED `evaluate.loss_differential`;
5. hands that one per-date series to every candidate test.

So the candidates differ in exactly one thing - the test applied to the same d - and the registered evaluator is called,
never copied. The registered test itself is `evaluate.moving_block_bootstrap_p` with its registered constants.

The protocol (candidates, DGP grid, effect sizes, seeds, replicate counts, decision rule) is frozen in
`inference-calibration-protocol.json` and its digest is checked before a FORMAL run. Nothing here changes the registered
test, threshold or support rule; a recommendation is an input to a future owner decision, never an amendment.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from pipeline import alpha_inference_mc_decision as MC
from pipeline import replay_calendar as RC

from . import evaluate as E
from . import study as S

HERE = Path(__file__).resolve().parent
PROTOCOL_PATH = HERE / "inference-calibration-protocol.json"
RESULT_PATH = HERE / "inference-calibration-result.json"
TESTED_BLOCK = "PROFIT"
PLANTED_COLUMN = "MEDIAN_netIncomeToAssets"
SESSIONS_PER_MONTH = 21


# --------------------------------------------------------------------------- #
# Protocol
# --------------------------------------------------------------------------- #
def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def protocol_digest(protocol):
    body = {k: v for k, v in protocol.items() if k != "frozenDigest"}
    return hashlib.sha256(canonical(body)).hexdigest()


def load_protocol(path=PROTOCOL_PATH, *, formal=True):
    protocol = json.loads(Path(path).read_text())
    if formal and protocol.get("frozenDigest") != protocol_digest(protocol):
        raise ValueError("PROTOCOL_DIGEST_MISMATCH")
    if protocol.get("registeredTest", {}).get("bootstrap") != S.BOOTSTRAP:
        raise ValueError("REGISTERED_BOOTSTRAP_CONSTANTS_CHANGED")
    if protocol["tested"]["block"] != TESTED_BLOCK or protocol["tested"]["plantedColumn"] != PLANTED_COLUMN:
        raise ValueError("TESTED_SLOT_CHANGED")
    return protocol


# --------------------------------------------------------------------------- #
# Critical values of the two fixed-b-type statistics (pure mathematics, no data)
# --------------------------------------------------------------------------- #
def kvb_statistic(x):
    """Kiefer-Vogelsang-Bunzel t: Bartlett long-run variance with bandwidth n, i.e. n^-2 sum_t S_t(demeaned)^2 x 2."""
    x = np.asarray(x, float)
    n = x.shape[-1]
    m = x.mean(axis=-1, keepdims=True)
    partial = np.cumsum(x - m, axis=-1)
    lrv = 2.0 * (partial ** 2).sum(axis=-1) / n ** 2
    return np.sqrt(n) * m[..., 0] / np.sqrt(lrv)


def sn_statistic(x):
    """Lobato (2001) / Shao (2010) self-normalised t: sqrt(n) mean / sqrt(n^-2 sum_t S_t(demeaned)^2)."""
    x = np.asarray(x, float)
    n = x.shape[-1]
    m = x.mean(axis=-1, keepdims=True)
    partial = np.cumsum(x - m, axis=-1)
    return np.sqrt(n) * m[..., 0] / np.sqrt((partial ** 2).sum(axis=-1) / n ** 2)


def limit_critical_values(*, paths=200_000, length=2_000, seed=20261025, chunk=2_000):
    """Upper quantiles of the KVB and SN statistics under IID N(0,1) at a long length (their fixed-b limits).

    Also returns P(SN^2 > 66.57), the critical value the repository's sealed v4 calibration pins for a two-sided
    97.5% self-normalised interval, as an independent check that this simulation reproduces a known constant."""
    rng = np.random.default_rng(seed)
    kvb, sn = [], []
    for _ in range(paths // chunk):
        x = rng.standard_normal((chunk, length))
        kvb.append(kvb_statistic(x))
        sn.append(sn_statistic(x))
    kvb, sn = np.concatenate(kvb), np.concatenate(sn)
    return {"paths": paths, "length": length, "seed": seed,
            "kvbOneSided95": float(np.quantile(kvb, 0.95)), "kvbOneSided99": float(np.quantile(kvb, 0.99)),
            "snOneSided95": float(np.quantile(sn, 0.95)), "snOneSided99": float(np.quantile(sn, 0.99)),
            "kvbOneSidedHolmFirst": float(np.quantile(kvb, 1 - 0.05 / 36)),
            "snOneSidedHolmFirst": float(np.quantile(sn, 1 - 0.05 / 36)),
            "snSquaredExceeds66_57": float(np.mean(sn ** 2 > 66.57))}


# --------------------------------------------------------------------------- #
# Candidate tests: each maps the per-date loss differential d (positive = alternative better) to a one-sided p or
# to a reject decision at the protocol's levels. They see d and nothing else.
# --------------------------------------------------------------------------- #
def _circular_indices(n, block, draws, rng):
    k = math.ceil(n / block)
    starts = rng.integers(0, n, size=(draws, k))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]) % n
    return idx.reshape(draws, -1)[:, :n]


def bartlett_lrv(x, lag):
    """Newey-West long-run variance (Bartlett weights) of the rows of x (last axis = time), demeaned per row."""
    x = np.asarray(x, float)
    n = x.shape[-1]
    z = x - x.mean(axis=-1, keepdims=True)
    lrv = (z * z).sum(axis=-1) / n
    for j in range(1, min(lag, n - 1) + 1):
        lrv = lrv + 2.0 * (1.0 - j / (lag + 1.0)) * (z[..., j:] * z[..., :-j]).sum(axis=-1) / n
    return lrv


def p_registered_mbb(d, cfg):
    return float(E.moving_block_bootstrap_p(d))


def p_circular_bb(d, cfg):
    """One change from the registered test: circular blocks (every observation equally likely), same block, draws, seed."""
    x = np.asarray(d, float)
    n = len(x)
    b = cfg["bootstrap"]
    idx = _circular_indices(n, min(b["blockSignals"], n), b["draws"], np.random.default_rng(b["seed"]))
    observed = x.mean()
    hits = int(((x - observed)[idx].mean(axis=1) >= observed).sum())
    return (1 + hits) / (b["draws"] + 1)


def p_studentized_cbb(d, cfg):
    """C1 plus studentisation: bootstrap the HAC t of the mean (Bartlett, lag = block - 1) instead of the mean."""
    x = np.asarray(d, float)
    n = len(x)
    b = cfg["bootstrap"]
    block = min(b["blockSignals"], n)
    lag = block - 1
    observed_t = x.mean() / math.sqrt(max(float(bartlett_lrv(x, lag)), 1e-300) / n)
    idx = _circular_indices(n, block, b["draws"], np.random.default_rng(b["seed"]))
    xs = x[idx]
    se = np.sqrt(np.maximum(bartlett_lrv(xs, lag), 1e-300) / n)
    t_star = (xs.mean(axis=1) - x.mean()) / se
    hits = int((t_star >= observed_t).sum())
    return (1 + hits) / (b["draws"] + 1)


def p_nw_hac_normal(d, cfg, horizon):
    x = np.asarray(d, float)
    lag = horizon // SESSIONS_PER_MONTH
    t = x.mean() / math.sqrt(max(float(bartlett_lrv(x, lag)), 1e-300) / len(x))
    return float(stats.norm.sf(t))


def batch_means_p(d, horizon):
    """Ibragimov-Mueller style: contiguous non-overlapping batches of H/21 months, earliest remainder dropped,
    one-sided Student t on the batch means with q - 1 degrees of freedom. None when q < 2."""
    x = np.asarray(d, float)
    length = horizon // SESSIONS_PER_MONTH
    q = len(x) // length
    if q < 2:
        return None, q
    means = x[len(x) - q * length:].reshape(q, length).mean(axis=1)
    sd = means.std(ddof=1)
    if sd == 0:
        return (0.0 if means.mean() > 0 else 1.0), q
    t = means.mean() / (sd / math.sqrt(q))
    return float(stats.t.sf(t, q - 1)), q


CANDIDATES = ("C0_REGISTERED_MBB", "C1_CIRCULAR_BB", "C2_STUDENTIZED_CBB", "C3_NW_HAC_NORMAL", "C4_FIXED_B_KVB",
              "C5_SELF_NORMALIZED", "C6_BATCH_MEANS_T")


def decisions(d, protocol, horizon):
    """{candidate: {'p': p or None, 'reject': {alpha: bool}}} for one replicate's series."""
    cfg = protocol["registeredTest"]
    alphas = protocol["alphas"]
    cv = protocol["criticalValues"]
    out = {}
    if len(d) < 2 or not np.isfinite(d).all():
        return {c: {"p": None, "reject": {str(a): False for a in alphas}, "undefined": True} for c in CANDIDATES}
    pvals = {"C0_REGISTERED_MBB": p_registered_mbb(d, cfg), "C1_CIRCULAR_BB": p_circular_bb(d, cfg),
             "C2_STUDENTIZED_CBB": p_studentized_cbb(d, cfg), "C3_NW_HAC_NORMAL": p_nw_hac_normal(d, cfg, horizon)}
    bm, _ = batch_means_p(d, horizon)
    pvals["C6_BATCH_MEANS_T"] = bm
    for c, p in pvals.items():
        undefined = p is None
        out[c] = {"p": p, "undefined": undefined,
                  "reject": {str(a): (not undefined) and p <= a for a in alphas}}
    kvb, sn = float(kvb_statistic(d)), float(sn_statistic(d))
    out["C4_FIXED_B_KVB"] = {"p": None, "statistic": kvb, "undefined": not math.isfinite(kvb),
                             "reject": {str(a): math.isfinite(kvb) and kvb > cv["kvb"][str(a)] for a in alphas}}
    out["C5_SELF_NORMALIZED"] = {"p": None, "statistic": sn, "undefined": not math.isfinite(sn),
                                 "reject": {str(a): math.isfinite(sn) and sn > cv["sn"][str(a)] for a in alphas}}
    return out


# --------------------------------------------------------------------------- #
# Synthetic industry world
# --------------------------------------------------------------------------- #
def month_end_signals(sessions, first_month):
    s = pd.DatetimeIndex(sessions)
    frame = pd.Series(s, index=s).groupby(s.to_period("M")).max()
    return [str(d.date()) for d in frame if str(d.date())[:7] >= first_month]


def _ar1_panel(rng, months, industries, rho, *, init=None):
    out = np.empty((months, industries))
    out[0] = rng.standard_normal(industries) if init is None else init
    scale = math.sqrt(1 - rho * rho)
    for t in range(1, months):
        out[t] = rho * out[t - 1] + scale * rng.standard_normal(industries)
    return out


def effect_kappa(ic, horizon, sigma_cross, rho_monthly):
    """Daily drift per unit of the planted (unit-variance) signal giving cross-sectional IC = ic at this horizon.

    Forward H-return signal part ~ kappa * 21 * sum_{k<H/21} rho^k * x; noise sd ~ sigma_cross * sqrt(H)."""
    if ic == 0:
        return 0.0
    mult = SESSIONS_PER_MONTH * sum(rho_monthly ** k for k in range(horizon // SESSIONS_PER_MONTH))
    return ic * sigma_cross * math.sqrt(horizon) / (mult * math.sqrt(1 - ic * ic))


def simulate_world(rng, dgp, world, horizon, first_month):
    """One synthetic industry-date frame with every column the H1 contrast reads, and its target/status.

    Returns (frame, realised mean date IC of the planted column against the centred target)."""
    sessions_all = RC.sessions(world["calendarStart"], world["calendarEnd"], "KR")
    signals = month_end_signals(sessions_all, first_month)
    days = pd.DatetimeIndex(sessions_all)
    n_s, G = len(days), world["industries"]
    heavy, regime = dgp["shocks"] == "STUDENT_T4", dgp["volRegime"]
    def shocks(shape):
        if heavy:
            return rng.standard_t(4, size=shape) / math.sqrt(2.0)
        return rng.standard_normal(shape)
    vol = np.ones(n_s)
    if regime:
        state, stay = 0, world["regimeStayProbability"]
        for s in range(n_s):
            if rng.random() > stay:
                state = 1 - state
            vol[s] = world["highVolMultiplier"] if state else 1.0
    beta = rng.uniform(world["betaLow"], world["betaHigh"], size=G)
    market = world["marketDailyVol"] * vol * shocks(n_s)
    idio = world["idioDailyVol"] * vol[:, None] * shocks((n_s, G))
    # Monthly persistent signal panels, indexed by calendar month of the whole session range.
    months, m_of = np.unique(days.to_period("M").asi8, return_inverse=True)
    T = len(months)
    rho = world["plantedRho"]
    planted = _ar1_panel(rng, T, G, rho)
    if dgp["betaLoading"]:
        bz = (beta - beta.mean()) / beta.std()
        planted = dgp["betaLoading"] * bz[None, :] + math.sqrt(1 - dgp["betaLoading"] ** 2) * planted
    change_noise = _ar1_panel(rng, T, G, 0.5)
    cash = _ar1_panel(rng, T, G, 0.95)
    value = _ar1_panel(rng, T, G, 0.97)
    hhi = _ar1_panel(rng, T, G, 0.98)
    top1 = 0.8 * hhi + 0.6 * _ar1_panel(rng, T, G, 0.98)
    count = _ar1_panel(rng, T, G, 0.99)
    adv = _ar1_panel(rng, T, G, 0.95)
    breadth_noise = _ar1_panel(rng, T, G, 0.8)
    # Cross-sectional daily noise: idiosyncratic plus beta dispersion times the market, scaled by the regime's mean
    # variance multiplier (unit-variance shocks in both shock families).
    mean_var = (1 + world["highVolMultiplier"] ** 2) / 2 if regime else 1.0
    beta_var = (world["betaHigh"] - world["betaLow"]) ** 2 / 12
    sigma_cross = math.sqrt(mean_var * (world["idioDailyVol"] ** 2 + beta_var * world["marketDailyVol"] ** 2))
    kappa = effect_kappa(dgp["ic"], horizon, sigma_cross, rho)
    # Drift on session s uses the planted value of the month BEFORE s's month (known at the prior month-end signal).
    prior = np.clip(m_of - 1, 0, None)
    drift = kappa * planted[prior]
    returns = beta[None, :] * market[:, None] + idio + drift
    bench = returns.mean(axis=1)
    wealth = np.vstack([np.zeros(G), np.cumsum(np.log1p(returns), axis=0)])
    bwealth = np.concatenate([[0.0], np.cumsum(np.log1p(bench))])
    present = rng.random((len(signals), G)) < world["presenceProbability"]
    rows = []
    for i, d in enumerate(signals):
        pos = int(days.searchsorted(pd.Timestamp(d)))          # signal session index
        mi = m_of[pos]
        entry, exit_ = pos + 1, pos + 1 + horizon
        past = slice(max(pos - 125, 0), pos + 1)
        mom = (wealth[pos + 1] - wealth[max(pos - 125, 0)]) - (bwealth[pos + 1] - bwealth[max(pos - 125, 0)])
        neg = np.minimum(returns[past], 0.0)
        dvol = np.sqrt((neg ** 2).mean(axis=0)) * math.sqrt(252)
        rel = (returns[past] - bench[past, None])
        breadth = 0.5 * np.sign(rel).mean(axis=0) + 0.5 * breadth_noise[mi]
        lev = planted[mi]
        lev12 = planted[max(mi - 12, 0)]
        matured = exit_ <= n_s - 1
        if matured:
            fwd = np.expm1(wealth[exit_ + 1] - wealth[entry + 1]) - np.expm1(bwealth[exit_ + 1] - bwealth[entry + 1])
        for g in range(G):
            if not present[i, g]:
                continue
            rows.append({"date": d, "industry": f"G{g}",
                         "REL_MOM_126": mom[g], "BREADTH_ABOVE_MA_126": breadth[g],
                         "MEDIAN_netIncomeToAssets": lev[g],
                         "MEDIAN_netIncomeImprovementToAssets": lev[g] - lev12[g] + 0.3 * change_noise[mi, g],
                         "MEDIAN_ocfToAssets": cash[mi, g], "MEDIAN_ocfImprovementToAssets": cash[mi, g] - cash[max(mi - 12, 0), g],
                         "MEDIAN_bookToMarketProxy": value[mi, g], "HHI": hhi[mi, g], "TOP1_CAP_SHARE": top1[mi, g],
                         "DOWNSIDE_VOL_126": dvol[g], "LOG_CONSTITUENT_COUNT": count[mi, g],
                         "MEDIAN_LOG_ADV60": adv[mi, g],
                         "cwRelative": fwd[g] if matured else np.nan,
                         "cwStatus": "MATURED" if matured else "NOT_MATURED"})
    frame = pd.DataFrame(rows)
    return frame, sessions_all


def realised_ic(frame):
    ok = frame[frame["cwStatus"].eq("MATURED")]
    vals = []
    for _, g in ok.groupby("date"):
        if len(g) >= 3:
            y = g["cwRelative"] - g["cwRelative"].mean()
            vals.append(np.corrcoef(g[PLANTED_COLUMN], y)[0, 1])
    return float(np.nanmean(vals)) if vals else None


def replicate(protocol, cell, replicate_index, seed):
    """One replicate of one cell: the registered chain on a fresh world, then every candidate on the same d."""
    dgp = protocol["dgps"][cell["dgp"]]
    world = protocol["world"]
    horizon = cell["horizon"]
    first_month = protocol["lengths"][cell["length"]]["firstSignalMonth"]
    ss = np.random.SeedSequence([seed, cell["index"], replicate_index])
    rng = np.random.default_rng(ss)
    frame, sessions = simulate_world(rng, dgp, world, horizon, first_month)
    base, alt = E.h1_columns(TESTED_BLOCK)
    pop, attrition = E.admit(frame, "cwRelative", "cwStatus")
    pb, _ = E.oof_predictions(pop, base, "cwRelative", sessions, horizon)
    pa, _ = E.oof_predictions(pop, alt, "cwRelative", sessions, horizon)
    d = E.loss_differential(pop, "cwRelative", pb, pa).to_numpy(float)
    return {"testDates": int(len(d)), "supportBlocks": int(E.support_blocks(range(len(d)))),
            "meanLossReduction": float(d.mean()) if len(d) else None,
            "realisedIC": realised_ic(frame), "admittedRows": attrition["admittedRows"],
            "thinDates": attrition["thinDates"], "decisions": decisions(d, protocol, horizon)}


def cells(protocol):
    out, k = [], 0
    for length in protocol["lengths"]:
        for horizon in protocol["horizons"]:
            for dgp in protocol["dgps"]:
                out.append({"index": k, "dgp": dgp, "horizon": horizon, "length": length,
                            "replicates": protocol["replicates"][length]})
                k += 1
    return out


def _run_cell(args):
    protocol, cell, seed, limit = args
    reps = cell["replicates"] if limit is None else min(limit, cell["replicates"])
    return cell, [replicate(protocol, cell, r, seed) for r in range(reps)]


def summarise_cell(protocol, cell, reps):
    """Rejection counts with exact Clopper-Pearson bounds, classified by the frozen decision rule."""
    rule = protocol["decisionRule"]
    is_null = protocol["dgps"][cell["dgp"]]["ic"] == 0
    summary = {"cell": cell, "replicatesRun": len(reps), "isNull": is_null,
               "medianTestDates": float(np.median([r["testDates"] for r in reps])),
               "medianSupportBlocks": float(np.median([r["supportBlocks"] for r in reps])),
               "meanRealisedIC": float(np.nanmean([r["realisedIC"] for r in reps if r["realisedIC"] is not None])),
               "candidates": {}}
    for c in CANDIDATES:
        per_alpha = {}
        for a in protocol["alphas"]:
            key = str(a)
            hits = sum(bool(r["decisions"][c]["reject"][key]) for r in reps)
            undefined = sum(bool(r["decisions"][c]["undefined"]) for r in reps)
            n = len(reps)
            entry = {"rejections": hits, "n": n, "rate": hits / n if n else None, "undefined": undefined,
                     "clopperPearson95": [MC.clopper_pearson_lower(hits, n, 0.025), MC.clopper_pearson_upper(hits, n, 0.025)]}
            if a == rule["primaryAlpha"]:
                if is_null:
                    entry["sizeDecision"] = MC.classify_metric(hits, n, kind=MC.CEILING, threshold=rule["sizeCeiling"],
                                                               pass_alpha=rule["passAlpha"], fail_alpha=rule["failAlpha"])["state"]
                else:
                    entry["powerDecision"] = MC.classify_metric(hits, n, kind=MC.FLOOR, threshold=rule["powerFloor"],
                                                                pass_alpha=rule["passAlpha"], fail_alpha=rule["failAlpha"])["state"]
            per_alpha[key] = entry
        summary["candidates"][c] = per_alpha
    return summary


def verdicts(protocol, summaries):
    """Frozen selection rule applied to the summaries: size validity first, then power, then the declared tie order."""
    rule = protocol["decisionRule"]
    a = str(rule["primaryAlpha"])
    out = {}
    for length in protocol["lengths"]:
        for horizon in protocol["horizons"]:
            group = [s for s in summaries if s["cell"]["length"] == length and s["cell"]["horizon"] == horizon]
            nulls = [s for s in group if s["isNull"]]
            effects = [s for s in group if not s["isNull"]]
            per = {}
            for c in CANDIDATES:
                states = [s["candidates"][c][a]["sizeDecision"] for s in nulls]
                size = MC.combine_states(states) if states else MC.INCONCLUSIVE
                primary = [s for s in effects if s["cell"]["dgp"] == rule["primaryPowerDgp"]]
                power = primary[0]["candidates"][c][a]["rate"] if primary else None
                per[c] = {"sizeState": size, "worstNullRate": max(s["candidates"][c][a]["rate"] for s in nulls),
                          "primaryPower": power,
                          "powerByDgp": {s["cell"]["dgp"]: s["candidates"][c][a]["rate"] for s in effects}}
            valid = [c for c in CANDIDATES if per[c]["sizeState"] == MC.PASS]
            ranked = sorted(valid, key=lambda c: (-(per[c]["primaryPower"] or 0.0), rule["tieOrder"].index(c)))
            best = ranked[0] if ranked else None
            adequate = best is not None and per[best]["primaryPower"] is not None and per[best]["primaryPower"] >= rule["powerFloor"]
            out[f"{length}_H{horizon}"] = {"candidates": per, "sizeValid": valid, "recommended": best,
                                           "recommendedPowerAdequate": adequate}
    return out


def run(protocol, *, seed, limit=None, workers=1, formal=False):
    started = time.time()
    jobs = [(protocol, c, seed, limit) for c in cells(protocol)]
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            results = list(ex.map(_run_cell, jobs))
    else:
        results = [_run_cell(j) for j in jobs]
    summaries = [summarise_cell(protocol, c, reps) for c, reps in results]
    return {"schema": "INDUSTRY_INFERENCE_CALIBRATION_RESULT_V1",
            "evidenceClass": "SYNTHETIC_CALIBRATION_FORMAL" if formal else "SYNTHETIC_CALIBRATION_DEVELOPMENT_ONLY",
            "historicalOutcomesRead": 0, "registeredTestChanged": False,
            "protocolDigest": protocol_digest(protocol), "seed": seed, "replicateLimit": limit,
            "codeSha256": {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest()
                           for name in ("inference_calibration.py", "evaluate.py", "study.py")},
            "elapsedSeconds": round(time.time() - started, 1),
            "cells": summaries, "verdicts": verdicts(protocol, summaries)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("mode", choices=("critical-values", "development", "formal"))
    ap.add_argument("--limit", type=int)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--output")
    args = ap.parse_args(argv)
    if args.mode == "critical-values":
        out = limit_critical_values()
    else:
        formal = args.mode == "formal"
        protocol = load_protocol(formal=formal)
        seed = protocol["seeds"]["formal" if formal else "development"]
        if formal and args.limit is not None:
            raise SystemExit("FORMAL_RUN_CANNOT_LIMIT_REPLICATES")
        out = run(protocol, seed=seed, limit=args.limit, workers=args.workers, formal=formal)
    text = json.dumps(out, indent=1, sort_keys=True, allow_nan=False, default=float)
    if args.output:
        Path(args.output).write_text(text + "\n")
    else:
        sys.stdout.write(text + "\n")


if __name__ == "__main__":
    main()
