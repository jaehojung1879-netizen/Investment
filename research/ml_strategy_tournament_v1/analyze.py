"""Step 5: winner anatomy and overfitting diagnostics over the full leaderboard. Reads only what evaluate.py and run_tournament.py wrote.

    python research/ml_strategy_tournament_v1/analyze.py --scratch <dir>

Writes results/winner-analysis.json and results/overfit-diagnostics.json.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import evaluate as E  # noqa: E402
import tournament as T  # noqa: E402

RULES = ["RULE_FOUR_FACTOR", "RULE_MOMENTUM", "RULE_LOW_VOL", "RULE_VALUE", "RULE_QUALITY", "RULE_INDUSTRY_MOMENTUM"]


def _r(x, n=6):
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return None
    return round(float(x), n)


def cfg_of(sid):
    for g in T.grid() + T.grid_h252():
        if g["id"] == sid:
            return g
    raise KeyError(sid)


# --------------------------------------------------------------------------- #
# Overfitting diagnostics
# --------------------------------------------------------------------------- #
def daily_excess_matrix(paths, bench_nav):
    navs = pd.DataFrame({s: p["nav"].astype(float) for s, p in paths.items()})
    r = navs.pct_change().iloc[1:]
    b = bench_nav.reindex(navs.index).pct_change().iloc[1:]
    return r, r.sub(b, axis=0)


def effective_trials(returns):
    """Two readings: eigenvalue participation ratio of the daily-return correlation matrix, and the number of clusters at |rho| >= 0.9."""
    x = returns.loc[:, returns.std() > 0]
    c = np.corrcoef(x.to_numpy().T)
    ev = np.clip(np.linalg.eigvalsh(c), 0, None)
    pr = ev.sum() ** 2 / (ev ** 2).sum()
    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import squareform
    d = 1 - c
    np.fill_diagonal(d, 0)
    z = linkage(squareform(np.clip(d, 0, None), checks=False), "average")
    clusters = len(set(fcluster(z, t=0.1, criterion="distance")))
    return {"participationRatio": float(pr), "clustersAtCorr0.9": int(clusters), "strategiesWithVariance": int(x.shape[1])}


def deflated_sharpe(series, all_sr_daily, n_eff):
    r = series.dropna()
    sr = r.mean() / r.std()
    g3 = float(((r - r.mean()) ** 3).mean() / r.std() ** 3)
    g4 = float(((r - r.mean()) ** 4).mean() / r.std() ** 4)
    v = np.var(all_sr_daily, ddof=1)
    em = 0.5772156649
    sr0 = math.sqrt(v) * ((1 - em) * norm.ppf(1 - 1 / n_eff) + em * norm.ppf(1 - 1 / (n_eff * math.e)))
    z = (sr - sr0) * math.sqrt(len(r) - 1) / math.sqrt(1 - g3 * sr + (g4 - 1) / 4 * sr ** 2)
    return {"dailySharpe": float(sr), "annualSharpe": float(sr * math.sqrt(252)), "expectedMaxSharpeUnderNullDaily": float(sr0),
            "expectedMaxSharpeUnderNullAnnual": float(sr0 * math.sqrt(252)), "nEffective": float(n_eff), "skew": g3, "kurtosis": g4,
            "deflatedSharpeProbability": float(norm.cdf(z))}


def cscv_pbo(excess, blocks=16):
    """Bailey et al. CSCV on daily excess returns (vs ETF); performance = mean daily excess within the sub-sample."""
    x = excess.to_numpy()
    n = len(x) // blocks * blocks
    parts = np.array_split(np.arange(n), blocks)
    means = np.stack([x[p].mean(axis=0) for p in parts])          # blocks x strategies
    lam, deg = [], []
    for combo in itertools.combinations(range(blocks), blocks // 2):
        is_ = np.zeros(blocks, bool)
        is_[list(combo)] = True
        perf_is = means[is_].mean(axis=0)
        perf_oos = means[~is_].mean(axis=0)
        best = int(np.argmax(perf_is))
        rank = (perf_oos < perf_oos[best]).sum() + 0.5 * ((perf_oos == perf_oos[best]).sum() - 1)
        w = (rank + 0.5) / len(perf_oos)
        lam.append(math.log(w / (1 - w)))
        deg.append((perf_is[best], perf_oos[best]))
    lam = np.array(lam)
    deg = np.array(deg)
    slope = np.polyfit(deg[:, 0], deg[:, 1], 1)[0]
    return {"blocks": blocks, "combinations": len(lam), "pbo": float((lam <= 0).mean()), "medianLogitOosRank": float(np.median(lam)),
            "isToOosSlope": float(slope), "meanOosDailyExcessOfIsWinner": float(deg[:, 1].mean())}


def block_bootstrap(diff, block=126, reps=2000, seed=11):
    """Date-synchronised circular block bootstrap of an annualised mean daily difference."""
    x = diff.dropna().to_numpy()
    n = len(x)
    rng = np.random.default_rng(seed)
    k = int(math.ceil(n / block))
    stats = np.empty(reps)
    for i in range(reps):
        starts = rng.integers(0, n, k)
        idx = (starts[:, None] + np.arange(block)[None, :]).ravel()[:n] % n
        stats[i] = x[idx].mean() * 252
    return {"annualisedMeanDiff": float(x.mean() * 252), "ci95": [float(np.percentile(stats, 2.5)), float(np.percentile(stats, 97.5))],
            "shareBootstrapAtOrBelowZero": float((stats <= 0).mean()), "blockSessions": block, "reps": reps}


def nested_selection(paths, results, bench_nav, rf, criterion="cagr"):
    """At each January from the second evaluation year, pick the strategy with the best criterion over ALL earlier evaluation sessions only,
    hold its realised daily returns for that year. This is what running the tournament repeatedly in real time would have delivered."""
    navs = pd.DataFrame({s: p["nav"].astype(float) for s, p in paths.items() if not s.endswith("ETF_ONLY")})
    r = navs.pct_change().fillna(0)
    years = sorted(set(navs.index.year))
    out, picks = [], []
    for y in years[1:]:
        past = navs[navs.index.year < y]
        if criterion == "cagr":
            score = past.iloc[-1] / past.iloc[0]
        else:
            pr = past.pct_change().dropna()
            score = pr.mean() / pr.std()
        best = score.idxmax()
        picks.append({"year": int(y), "picked": best, "pastRankAbs": int(results[best]["rankAbs"]) if "rankAbs" in results[best] else None})
        out.append(r.loc[r.index.year == y, best])
    ser = pd.concat(out)
    nav = (1 + ser).cumprod()
    nav = pd.concat([pd.Series([1.0], index=[navs.index[navs.index.year < years[1]][-1]]), nav])
    m = T.metrics(nav, bench_nav, rf)
    return {"criterion": criterion, "picks": picks, "metrics": {k: _r(v) for k, v in m.items()}, "distinctPicks": len({p["picked"] for p in picks})}


def factor_regression(r_win, r_bench, rule_returns):
    """OLS of the winner's daily return on the ETF and the rule-strategy active returns; Newey-West (10 lags) SE on the intercept."""
    X = pd.concat([r_bench.rename("ETF")] + [(rule_returns[c] - r_bench).rename(c) for c in rule_returns], axis=1).dropna()
    y = r_win.reindex(X.index)
    A = np.column_stack([np.ones(len(X)), X.to_numpy()])
    beta, *_ = np.linalg.lstsq(A, y.to_numpy(), rcond=None)
    e = y.to_numpy() - A @ beta
    L = 10
    XtXi = np.linalg.inv(A.T @ A)
    S = (A * e[:, None]).T @ (A * e[:, None])
    for lag in range(1, L + 1):
        w = 1 - lag / (L + 1)
        G = (A[lag:] * e[lag:, None]).T @ (A[:-lag] * e[:-lag, None])
        S += w * (G + G.T)
    V = XtXi @ S @ XtXi
    se = np.sqrt(np.diag(V))
    names = ["alpha"] + list(X.columns)
    r2 = 1 - (e ** 2).sum() / ((y - y.mean()) ** 2).sum()
    return {"coefficients": {n: _r(b, 6) for n, b in zip(names, beta)}, "tStats": {n: _r(b / s, 3) for n, b, s in zip(names, beta, se)},
            "annualisedAlpha": _r(beta[0] * 252), "alphaT": _r(beta[0] / se[0], 3), "r2": _r(r2, 4), "neweyWestLags": L}


# --------------------------------------------------------------------------- #
# Winner anatomy
# --------------------------------------------------------------------------- #
def contributions(path, nav_index, df):
    contrib = path["contrib"]
    idx = nav_index
    ind = df.groupby("ticker")["industry"].agg(lambda s: s.dropna().iloc[-1] if s.notna().any() else None).to_dict()
    total = {t: float(a.sum()) for t, a in contrib.items()}
    by_year = {}
    for t, a in contrib.items():
        s = pd.Series(a, index=idx)
        for y, v in s.groupby(s.index.year).sum().items():
            by_year.setdefault(int(y), {})[t] = float(v)
    names = sorted((t for t in total if t != T.BENCH), key=lambda t: -total[t])
    by_ind = {}
    for t in names:
        by_ind[ind.get(t) or "UNCLASSIFIED"] = by_ind.get(ind.get(t) or "UNCLASSIFIED", 0.0) + total[t]
    return {"sumOfDailyContributions": {"stocks": _r(sum(total[t] for t in names)), "etf": _r(total.get(T.BENCH, 0.0))},
            "byName": [{"ticker": t, "industry": ind.get(t), "contribution": _r(total[t])} for t in names],
            "byYear": {y: {"stocks": _r(sum(v for t, v in d.items() if t != T.BENCH)), "etf": _r(d.get(T.BENCH, 0.0)),
                           "topNames": [[t, _r(v)] for t, v in sorted(((t, v) for t, v in d.items() if t != T.BENCH), key=lambda kv: -kv[1])[:3]]}
                       for y, d in sorted(by_year.items())},
            "byIndustry": {k: _r(v) for k, v in sorted(by_ind.items(), key=lambda kv: -kv[1])},
            "note": "contributions are sums of daily (weight x return) in NAV units; they add to the sum of daily NAV returns, not to the compounded CAGR"}


def round_trips(trades, closes):
    """Pair each buy with the following sell of the same name (weights are fixed 20% sleeves, so a name is entered once and exited once)."""
    open_, out = {}, []
    for t in trades:
        if t["side"] == "buy" and t["fromWeight"] < 1e-9:
            open_[t["ticker"]] = t
        elif t["side"] == "sell" and t["toWeight"] < 1e-9 and t["ticker"] in open_:
            b = open_.pop(t["ticker"])
            bench = closes[T.BENCH]
            ret = t["close"] / b["close"] - 1
            bret = bench.loc[pd.Timestamp(t["date"])] / bench.loc[pd.Timestamp(b["date"])] - 1
            out.append({"ticker": t["ticker"], "entry": b["date"], "exit": t["date"], "entryClose": b["close"], "exitClose": t["close"],
                        "returnTotal": _r(ret), "etfReturnSameWindow": _r(bret), "excess": _r(ret - bret)})
    for tk, b in open_.items():
        out.append({"ticker": tk, "entry": b["date"], "exit": None, "entryClose": b["close"], "openAtEnd": True})
    return out


def refit_scores(cfg, df, layers, ranked, drop=()):
    lay = {k: [c for c in v if c not in drop] for k, v in layers.items()}
    scores = np.full(len(df), np.nan)
    shap_rows = []
    for year in T.CONFIG["walkForward"]["outerFoldYears"]:
        train, test = T.fold_split(df, year, cfg["horizon"])
        if test.empty:
            continue
        pred, _, model, cols = T.fit_predict(cfg, train, test, ranked.loc[train.index], ranked.loc[test.index], lay)
        scores[test.index] = pred
        if not drop and cfg["family"] in ("LGBM", "XGB"):
            Xte, _ = T._tree_matrix(test, ranked.loc[test.index], cols, lay)
            if cfg["family"] == "LGBM":
                contrib = model.predict(Xte, pred_contrib=True) if cfg["objective"] != "RANK" else model.booster_.predict(Xte, pred_contrib=True)
            else:
                import xgboost as xgb
                contrib = model.get_booster().predict(xgb.DMatrix(Xte), pred_contribs=True)
            mkt_cols = [c for c in cols if c in lay["market"]]
            cross = [c for c in cols if c not in mkt_cols]
            ordered = cross + mkt_cols
            shap_rows.append(pd.DataFrame(contrib[:, :-1], index=test.index, columns=ordered))
    shap = pd.concat(shap_rows) if shap_rows else None
    return scores, shap


def portfolio_from_scores(df, scores, h, rdates, sessions, book, start, end, bench_nav, rf, gate=True, max_names=5, exclude=(), cost_mult=1.0):
    df = df.assign(_s=scores)
    by_date = {d: g for d, g in df.groupby("date")}
    sched, _ = E.build_schedule(df, by_date, "_s", h, rdates, sessions, gate=gate, max_names=max_names, exclude=exclude, cost_mult=cost_mult)
    sim = T.simulate(book, sched, start, end, "ZERO", cost_mult=cost_mult)
    return T.metrics(sim["nav"], bench_nav, rf, sim["stockTurnover"]), sim


def shap_summary(shap, df, top=12):
    mean_abs = shap.abs().mean().sort_values(ascending=False)
    feats = list(mean_abs.index[:top])
    regime = np.where(df.loc[shap.index, "MKT_trend126"] > 0, "MARKET_UP_126D", "MARKET_DOWN_126D")
    vol = df.loc[shap.index, "MKT_vol63"]
    vol_reg = np.where(vol > vol.median(), "HIGH_VOL", "LOW_VOL")
    out = {"meanAbsShapTop": {f: _r(mean_abs[f]) for f in feats}, "conditional": {}}
    ranked = df.loc[shap.index]
    for f in feats[:6]:
        if f.startswith("MKT_") or f not in ranked:
            continue
        q = ranked.groupby("date")[f].rank(pct=True)
        qb = np.minimum((q * 5).fillna(-1).astype(int), 4)
        tab = {}
        for name, reg in (("trend", regime), ("vol", vol_reg)):
            for r in sorted(set(reg)):
                m = reg == r
                tab[r] = {int(b): _r(shap.loc[m & (qb == b), f].mean()) for b in range(5)}
        out["conditional"][f] = tab
    out["note"] = "SHAP explains the model's predictions, not returns; it is not a causal statement. Rows are the model's own out-of-sample fold predictions."
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--scratch", required=True)
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--view", choices=["gated", "forced"], default="gated")
    ap.add_argument("--subject", default=None, help="strategy to dissect (default: rank 1 by CAGR)")
    a = ap.parse_args(argv)
    s = Path(a.scratch)
    ev = pickle.loads((s / f"eval-{a.view}.pkl").read_bytes())
    gate = a.view == "gated"
    results, paths = ev["results"], ev["paths"]
    frame = E.rank_tables(results)
    for sid in results:
        results[sid]["rankAbs"] = frame.at[sid, "rankAbs"]
    blob, df, preds, folds = E.load(s)
    sessions = blob["sessions"]
    closes, vols = blob["closes"], blob["volumes"]
    book = T.PriceBook({t: pd.DataFrame({"Close": closes[t], "Volume": vols[t]}) for t in closes.columns}, list(closes.columns), sessions, closes[T.BENCH])
    rdates = E.rebalance_dates(df)
    start = E.next_session(sessions, rdates[0])
    end = book.bench.last_valid_index()
    bench_nav = book.bench / book.bench.loc[start]
    rf = pd.Series(T.bok_rate_series(sessions, json.loads((HERE.parents[1] / "data/bok-policy-rates.json").read_text())["events"]).to_numpy() / 100 / 252,
                   index=sessions)
    layers = blob["layers"]
    ranked = T.rank_transform(df, layers["company"] + layers["industry"])

    order = frame.sort_values("rankAbs")
    top_abs = list(order.index[: a.top])
    winner = a.subject or top_abs[0]
    tag = a.view + (f"-{a.subject}" if a.subject else "")
    r_all, ex_all = daily_excess_matrix(paths, bench_nav)
    r_bench = bench_nav.pct_change().reindex(r_all.index)

    # ---------------- overfitting ----------------
    eff_raw = effective_trials(r_all.drop(columns=[c for c in r_all if c.endswith("ETF_ONLY")]))
    # Everything co-moves with the market, so independence is measured on returns IN EXCESS of the ETF.
    eff = effective_trials(ex_all.drop(columns=[c for c in ex_all if c.endswith("ETF_ONLY")]))
    sr_daily = (ex_all.mean() / ex_all.std()).replace([np.inf, -np.inf], np.nan).dropna()
    abs_sr_daily = ((r_all.mean()) / r_all.std()).dropna()
    over = {"trials": {"strategies": len(results), "mlConfigurations": sum(1 for x in results if not x.startswith("RULE_")),
                       "fitsPerformed": int(sum(len([f for f in folds[x] if f.get("trainRows")]) for x in folds)),
                       "onExcessReturns": eff, "onRawReturns": eff_raw,
                       "strategiesIdenticalToEtf": int(sum(1 for x in results if results[x]["etfOnlyRebalanceShare"] == 1.0))}}
    over["deflatedSharpeWinnerAbsolute"] = {lbl: deflated_sharpe(r_all[winner], abs_sr_daily.to_numpy(), n) for lbl, n in
                                            (("nAll", len(abs_sr_daily)), ("nParticipationRatio", max(2.0, eff["participationRatio"])),
                                             ("nClusters", max(2, eff["clustersAtCorr0.9"])))}
    over["deflatedSharpeWinnerExcessVsEtf"] = {lbl: deflated_sharpe(ex_all[winner], sr_daily.to_numpy(), n) for lbl, n in
                                               (("nAll", len(sr_daily)), ("nParticipationRatio", max(2.0, eff["participationRatio"])),
                                                ("nClusters", max(2, eff["clustersAtCorr0.9"])))}
    over["cscvPbo"] = cscv_pbo(ex_all.drop(columns=[c for c in ex_all if c.endswith("ETF_ONLY")]))
    best_rule = max((x for x in RULES if x != winner), key=lambda x: results[x]["cagr"])
    over["blockBootstrap"] = {"winnerMinusEtf": block_bootstrap(r_all[winner] - r_bench),
                              "winnerMinusBestRule": {"rule": best_rule, **block_bootstrap(r_all[winner] - r_all[best_rule])},
                              "winnerMinusFourFactor": block_bootstrap(r_all[winner] - r_all["RULE_FOUR_FACTOR"]) if winner != "RULE_FOUR_FACTOR" else None}
    over["nestedSelection"] = {"byPastCagr": nested_selection(paths, results, bench_nav, rf, "cagr"),
                               "byPastSharpe": nested_selection(paths, results, bench_nav, rf, "sharpe")}
    ins = [(x, results[x]["inSampleRankIcMean"], results[x]["oosRankIcMean"]) for x in top_abs if results[x]["inSampleRankIcMean"] is not None]
    over["trainVsOosRankIc"] = [{"strategy": x, "inSample": _r(i, 4), "outOfSample": _r(o, 4)} for x, i, o in ins]
    over["oosRankIcAll"] = {"mean": _r(np.nanmean([results[x]["oosRankIcMean"] for x in results if results[x]["oosRankIcMean"] is not None]), 4),
                            "shareNegative": _r(np.mean([results[x]["oosRankIcMean"] < 0 for x in results if results[x]["oosRankIcMean"] is not None]), 4)}
    corr = ex_all[top_abs].corr()
    over["top20ExcessCorrelation"] = {"meanOffDiagonal": _r(corr.to_numpy()[np.triu_indices(len(top_abs), 1)].mean(), 3),
                                      "minOffDiagonal": _r(corr.to_numpy()[np.triu_indices(len(top_abs), 1)].min(), 3)}
    rules = {c: r_all[c] for c in RULES if c != winner}
    over["factorRegressionWinner"] = factor_regression(r_all[winner], r_bench, rules)
    # ---------------- winner anatomy ----------------
    wp = paths[winner]
    nav_idx = wp["nav"].index
    anat = {"winner": winner, "config": cfg_of(winner) if not winner.startswith("RULE_") else {"rule": winner},
            "metrics": {k: _r(v) for k, v in results[winner].items() if not isinstance(v, (dict, list))},
            "yearly": results[winner]["yearly"],
            "navMonthEnd": {str(d.date()): [_r(v, 5), _r(bench_nav.loc[d], 5)] for d, v in
                            wp["nav"].astype(float).groupby(wp["nav"].index.to_period("M")).tail(1).items()},
            "contributions": contributions(wp, nav_idx, df), "holdings": wp["holdings"], "trades": wp["trades"],
            "roundTrips": round_trips(wp["trades"], closes), "decisions": {k: list(v) for k, v in wp["decisions"].items()}}
    # holdings exposure vs eligible universe
    expo_cols = ["E02_logAdv60", "A07_momentum12_1", "F03_beta252", "F02_downsideVol126", "B01_bookToMarket", "C02_returnOnEquity", "H01_industryRelMom126"]
    pct = df.groupby("date")[expo_cols].rank(pct=True)
    held_pct = []
    for h in wp["holdings"]:
        d = pd.Timestamp(h["date"])
        sig = df["date"][df["date"] < d].max()
        rows = df[(df["date"] == sig) & df["ticker"].isin(list(h["weights"]))]
        held_pct.append(pct.loc[rows.index])
    held = pd.concat(held_pct) if held_pct else pd.DataFrame(columns=expo_cols)
    anat["heldExposurePercentiles"] = {c: _r(held[c].mean(), 3) for c in expo_cols}
    # leave-one-name-out (actual reruns with the name excluded from every decision) and leave-one-year-out
    h = 126
    top_names = [x["ticker"] for x in anat["contributions"]["byName"][:5]]
    sc = preds[winner]
    lono = {}
    for t in top_names:
        m, _ = portfolio_from_scores(df, sc, h, rdates, sessions, book, start, end, bench_nav, rf, gate=gate, exclude=(t,))
        lono[t] = {"cagr": _r(m["cagr"]), "excessCagr": _r(m["excessCagr"])}
    m, _ = portfolio_from_scores(df, sc, h, rdates, sessions, book, start, end, bench_nav, rf, gate=gate, exclude=tuple(top_names))
    lono["ALL_TOP5"] = {"cagr": _r(m["cagr"]), "excessCagr": _r(m["excessCagr"])}
    anat["leaveNamesOut"] = lono
    rw = r_all[winner]
    rb = r_bench
    loyo = {}
    for y in sorted(set(rw.index.year)):
        keep = rw.index.year != y
        yrs = keep.sum() / 252
        loyo[int(y)] = {"cagrWithoutYear": _r((1 + rw[keep]).prod() ** (1 / yrs) - 1), "etfWithoutYear": _r((1 + rb[keep]).prod() ** (1 / yrs) - 1)}
    anat["leaveOneYearOut"] = loyo
    # concentration and cost sensitivity
    conc = {}
    for k in (1, 3, 5):
        m, _ = portfolio_from_scores(df, sc, h, rdates, sessions, book, start, end, bench_nav, rf, gate=False, max_names=k)
        conc[f"forcedTop{k}"] = {"cagr": _r(m["cagr"]), "excessCagr": _r(m["excessCagr"]), "mdd": _r(m["mdd"]), "sharpe": _r(m["sharpe"])}
    m, _ = portfolio_from_scores(df, sc, h, rdates, sessions, book, start, end, bench_nav, rf, gate=gate, cost_mult=2.0)
    conc["sameViewCostX2"] = {"cagr": _r(m["cagr"]), "excessCagr": _r(m["excessCagr"])}
    anat["concentrationAndCostSensitivity"] = conc
    # ablations and SHAP (ML winners only)
    if not winner.startswith("RULE_"):
        cfg = cfg_of(winner)
        base_scores, shap = refit_scores(cfg, df, layers, ranked)
        same = np.allclose(np.nan_to_num(base_scores), np.nan_to_num(sc), atol=1e-4)
        anat["refitReproducesStoredScores"] = bool(same)
        abl = {}
        for fam, pred in T.FAMILIES.items():
            drop = [c for c in layers["company"] + layers["industry"] + layers["market"] if pred(c)]
            s2, _ = refit_scores(cfg, df, layers, ranked, drop=drop)
            m, _ = portfolio_from_scores(df, s2, h, rdates, sessions, book, start, end, bench_nav, rf, gate=gate)
            ic = T.spearman_by_date(df.assign(_s=s2)[df["date"].dt.year >= 2016], "_s", "y126").mean()
            abl[fam] = {"featuresDropped": len(drop), "cagr": _r(m["cagr"]), "excessCagr": _r(m["excessCagr"]), "sharpe": _r(m["sharpe"]), "oosRankIc": _r(ic, 4)}
        anat["familyAblation"] = abl
        if shap is not None:
            anat["shap"] = shap_summary(shap, df)
        lin = f"RIDGE_{cfg['fs']}_{'REG' if cfg['objective'] == 'REG' else 'RANK'}_a2"
        anat["linearCounterpart"] = {"strategy": lin, "cagr": _r(results[lin]["cagr"]), "excessCagr": _r(results[lin]["excessCagr"]),
                                     "sharpe": _r(results[lin]["sharpe"]), "oosRankIc": _r(results[lin]["oosRankIcMean"], 4),
                                     "winnerMinusLinear": block_bootstrap(r_all[winner] - r_all[lin])}
    # ---------------- top-20 common conditions ----------------
    held_sets = {}
    for x in top_abs:
        held_sets[x] = {(hh["date"], t) for hh in paths[x]["holdings"] for t in hh["weights"]}
    jac = [len(held_sets[i] & held_sets[j]) / max(1, len(held_sets[i] | held_sets[j])) for i, j in itertools.combinations(top_abs, 2)]
    name_count = {}
    for x in top_abs:
        for t in {t for _, t in held_sets[x]}:
            name_count[t] = name_count.get(t, 0) + 1
    pcorr = []
    sub = df[df["date"].dt.year >= 2016]
    for i, j in itertools.combinations([x for x in top_abs if not x.endswith("ETF_ONLY")], 2):
        a_, b_ = preds[i][sub.index], preds[j][sub.index]
        tmp = pd.DataFrame({"d": sub["date"].to_numpy(), "a": a_, "b": b_}).dropna()
        pcorr.append(tmp.groupby("d")[["a", "b"]].apply(lambda g: g["a"].rank().corr(g["b"].rank())).mean())
    common = {"top": top_abs,
              "familyCount": pd.Series([cfg_of(x)["family"] if not x.startswith("RULE_") else "RULE" for x in top_abs]).value_counts().to_dict(),
              "featureSetCount": pd.Series([cfg_of(x)["fs"] if not x.startswith("RULE_") else "RULE" for x in top_abs]).value_counts().to_dict(),
              "objectiveCount": pd.Series([cfg_of(x)["objective"] if not x.startswith("RULE_") else "RULE" for x in top_abs]).value_counts().to_dict(),
              "meanHoldingJaccard": _r(np.mean(jac), 3), "meanPredictionRankCorrelation": _r(np.nanmean(pcorr), 3),
              "namesHeldByMostTopStrategies": sorted(name_count.items(), key=lambda kv: -kv[1])[:15]}
    imp = {}
    for x in top_abs:
        if x.startswith(("LGBM", "XGB")):
            cfg = cfg_of(x)
            train, test = T.fold_split(df, 2026, 126)
            _, _, model, cols = T.fit_predict(cfg, train, test, ranked.loc[train.index], ranked.loc[test.index], layers)
            mkt = [c for c in cols if c in layers["market"]]
            ordered = [c for c in cols if c not in mkt] + mkt
            gains = model.booster_.feature_importance("gain") if x.startswith("LGBM") else np.array(
                [model.get_booster().get_score(importance_type="gain").get(f"f{i}", 0.0) for i in range(len(ordered))])
            share = pd.Series(gains / gains.sum(), index=ordered)
            imp[x] = share.sort_values(ascending=False).head(10).round(4).to_dict()
            for fam, pred in T.FAMILIES.items():
                imp.setdefault("_familyShare", {}).setdefault(fam, []).append(float(share[[c for c in ordered if pred(c)]].sum()))
    if "_familyShare" in imp:
        imp["_familyShare"] = {k: _r(np.mean(v), 4) for k, v in imp["_familyShare"].items()}
    common["gainImportanceLastFold"] = imp
    tables = {}
    for key, col, asc in (("absoluteTop10", "rankAbs", True), ("riskAdjustedTop10", "rankRisk", True), ("stabilityTop10", "rankStability", True)):
        sel = frame.sort_values(col).head(10)
        tables[key] = [{"strategy": x, **{c: _r(frame.at[x, c]) for c in ["cagr", "etfCagr", "excessCagr", "sharpe", "informationRatio", "vol", "trackingError",
                                                                          "mdd", "annualStockTurnover", "meanNamesHeld", "positiveExcessYearShare",
                                                                          "minHalfExcessCagr", "rolling252PositiveShare", "excessCagrExTop5Names",
                                                                          "top5ShareOfStockContribution", "cagrUpperBoundTerminalAtLastClose", "rankAbs", "rankRisk",
                                                                          "rankStability"]}} for x in sel.index]
    for x in RULES + ["RULE_ETF_ONLY"]:
        tables.setdefault("ruleBaselines", []).append({"strategy": x, **{c: _r(frame.at[x, c]) for c in ["cagr", "excessCagr", "sharpe", "mdd", "rankAbs"]}})
    out = HERE / "results"
    (out / f"rankings-{a.view}.json").write_text(json.dumps({"evidenceClass": T.CONFIG["evidenceClass"], "view": a.view, "window": ev["window"], **tables}, indent=1, ensure_ascii=False, default=float) + "\n")
    (out / f"winner-analysis-{tag}.json").write_text(json.dumps({"evidenceClass": T.CONFIG["evidenceClass"], "view": a.view, "subject": winner, "subjectRankAbs": int(frame.at[winner, "rankAbs"]), "anatomy": anat, "top20Common": common},
                                                         indent=1, ensure_ascii=False, default=float) + "\n")
    (out / f"overfit-diagnostics-{tag}.json").write_text(json.dumps({"evidenceClass": T.CONFIG["evidenceClass"], "view": a.view, "subject": winner, **over}, indent=1, ensure_ascii=False, default=float) + "\n")
    print(json.dumps({"winner": winner, "pbo": over["cscvPbo"]["pbo"], "nested": over["nestedSelection"]["byPastCagr"]["metrics"]}, default=float))


if __name__ == "__main__":
    main()
