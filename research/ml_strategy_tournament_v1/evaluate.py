"""Step 4: turn every strategy's out-of-sample scores into the SAME 0-5 name + ETF book, value it daily and rank it.

    python research/ml_strategy_tournament_v1/evaluate.py --scratch <dir> [--h252]

Writes <dir>/eval[-h252].pkl (NAV paths, contributions, trades, holdings) and results/leaderboard[-h252].json (every strategy, no filtering).
"""
from __future__ import annotations

import argparse
import json
import math
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import tournament as T  # noqa: E402

EVAL_START = pd.Timestamp(T.CONFIG["walkForward"]["portfolioEvaluationStart"])


def load(scratch, h252=False):
    blob = pickle.loads((Path(scratch) / "dataset.pkl").read_bytes())
    df = blob["df"]
    df["_q"] = T.quality_mask(df).to_numpy()
    preds = {}
    folds = {}
    for p in sorted((Path(scratch) / ("preds-h252" if h252 else "preds")).glob("*.npz")):
        z = np.load(p, allow_pickle=False)
        preds[p.stem] = z["scores"].astype(float)
        folds[p.stem] = json.loads(str(z["folds"]))
    return blob, df, preds, folds


def rebalance_dates(df):
    dates = sorted(d for d in df["date"].unique() if pd.Timestamp(d) >= EVAL_START)
    return [pd.Timestamp(d) for d in dates[::4]]


def next_session(sessions, d):
    i = sessions.searchsorted(d, side="right")
    return sessions[i] if i < len(sessions) else None


def build_schedule(df, by_date, col, h, rdates, sessions, gate=True, max_names=5, cost_mult=1.0, exclude=()):
    calib, exits = T.calibration_table(df, col, h)
    sched, diag = {}, {}
    for d in rdates:
        e = next_session(sessions, d)
        if e is None:
            continue
        w, info = T.decide(by_date[d], col, calib, exits, d, h, max_names=max_names, gate=gate, cost_mult=cost_mult, exclude=exclude)
        sched[e] = w
        diag[str(d.date())] = info.get("reason"), len(w)
    return sched, diag


def yearly(nav, bench):
    b = bench.reindex(nav.index)
    out = {}
    for y, g in nav.groupby(nav.index.year):
        i0 = nav.index.get_loc(g.index[0])
        base = nav.iloc[i0 - 1] if i0 > 0 else 1.0
        bb = b.iloc[i0 - 1] if i0 > 0 else b.iloc[0]
        out[int(y)] = {"ret": g.iloc[-1] / base - 1, "etf": b.loc[g.index[-1]] / bb - 1}
        out[int(y)]["excess"] = out[int(y)]["ret"] - out[int(y)]["etf"]
    return out


def stability(nav, bench, contrib, years):
    b = bench.reindex(nav.index)
    yr = yearly(nav, bench)
    pos_years = np.mean([v["excess"] > 0 for v in yr.values()])
    mid = len(nav) // 2
    h1 = (nav.iloc[mid] / nav.iloc[0]) ** (252 / mid) - (b.iloc[mid] / b.iloc[0]) ** (252 / mid)
    h2 = (nav.iloc[-1] / nav.iloc[mid]) ** (252 / (len(nav) - mid - 1)) - (b.iloc[-1] / b.iloc[mid]) ** (252 / (len(nav) - mid - 1))
    roll = (nav / nav.shift(252)) - (b / b.shift(252))
    roll = roll.dropna()
    stock = {t: a for t, a in contrib.items() if t != T.BENCH}
    top = sorted(stock, key=lambda t: -stock[t].sum())[:5]
    r = nav.pct_change().fillna(0).to_numpy()
    adj = r - sum(stock[t] for t in top) if top else r
    adj_nav = np.cumprod(1 + adj)
    yrs = (len(nav) - 1) / 252
    ex_top5 = adj_nav[-1] ** (1 / yrs) - (b.iloc[-1] / b.iloc[0]) ** (1 / yrs)
    total_stock = sum(a.sum() for a in stock.values())
    return {"positiveExcessYearShare": float(pos_years), "excessCagrFirstHalf": float(h1), "excessCagrSecondHalf": float(h2),
            "minHalfExcessCagr": float(min(h1, h2)), "rolling252PositiveShare": float((roll > 0).mean()) if len(roll) else None,
            "excessCagrExTop5Names": float(ex_top5), "top5Names": top,
            "top5ShareOfStockContribution": float(sum(stock[t].sum() for t in top) / total_stock) if total_stock > 0 else None,
            "yearly": {y: {k: round(float(v), 6) for k, v in d.items()} for y, d in yr.items()}}


def evaluate(scratch, h252=False, only=None):
    blob, df, preds, folds = load(scratch, h252)
    h = 252 if h252 else 126
    sessions = blob["sessions"]
    closes, vols = blob["closes"], blob["volumes"]
    tickers = [t for t in closes.columns]
    prices = {t: pd.DataFrame({"Close": closes[t], "Volume": vols[t]}) for t in tickers}
    book = T.PriceBook(prices, tickers, sessions, closes[T.BENCH])
    rdates = rebalance_dates(df)
    start = next_session(sessions, rdates[0])
    end = book.bench.last_valid_index()
    rf = pd.Series(T.bok_rate_series(sessions, json.loads((HERE.parents[1] / "data/bok-policy-rates.json").read_text())["events"]).to_numpy() / 100 / 252,
                   index=sessions)
    bench_nav = book.bench / book.bench.loc[start]
    results, paths = {}, {}
    for sid in sorted(preds):
        if only and sid not in only:
            continue
        df["_s"] = preds[sid]
        by_date = {d: g for d, g in df.groupby("date")}
        if sid.endswith("ETF_ONLY"):
            sched = {next_session(sessions, d): {} for d in rdates}
            diag = {}
        else:
            sched, diag = build_schedule(df, by_date, "_s", h, rdates, sessions)
        sim = T.simulate(book, sched, start, end, "ZERO", record=True)
        alt = T.simulate(book, sched, start, end, "LAST")
        m = T.metrics(sim["nav"], bench_nav, rf, sim["stockTurnover"])
        m_alt = T.metrics(alt["nav"], bench_nav, rf, alt["stockTurnover"])
        st = stability(sim["nav"], bench_nav, sim["contrib"], m["years"])
        names_held = [len(x["weights"]) for x in sim["holdings"]]
        oos = [f.get("oosIC") for f in folds.get(sid, []) if f.get("oosIC") is not None and f["year"] >= 2016]
        ins = [f.get("isIC") for f in folds.get(sid, []) if f.get("isIC") is not None and f["year"] >= 2016]
        results[sid] = {**{k: (float(v) if v is not None else None) for k, v in m.items()},
                        "cagrUpperBoundTerminalAtLastClose": float(m_alt["cagr"]), "terminalHits": sim["terminalHits"],
                        "meanNamesHeld": float(np.mean(names_held)) if names_held else 0.0,
                        "etfOnlyRebalanceShare": float(np.mean([n == 0 for n in names_held])) if names_held else 1.0,
                        "oosRankIcMean": float(np.mean(oos)) if oos else None, "inSampleRankIcMean": float(np.mean(ins)) if ins else None,
                        "costDrag": float(sim["costs"] / m["years"]), **st}
        paths[sid] = {"nav": sim["nav"].astype(np.float32), "contrib": {t: a.astype(np.float32) for t, a in sim["contrib"].items()},
                      "trades": sim["trades"], "holdings": sim["holdings"], "decisions": diag}
        print(f"{sid:40s} CAGR {m['cagr']*100:6.2f}% ex {m['excessCagr']*100:6.2f}% SR {m['sharpe']:.2f} MDD {m['mdd']*100:6.1f}% names {results[sid]['meanNamesHeld']:.2f}", flush=True)
    return results, paths, {"start": str(start.date()), "end": str(end.date()), "rebalances": len(rdates), "sessions": len(sim["nav"])}


def rank_tables(results):
    sids = [s for s in results]
    frame = pd.DataFrame(results).T
    frame["rankAbs"] = frame["cagr"].rank(ascending=False, method="min")
    frame["rankRisk"] = frame["sharpe"].rank(ascending=False, method="min")
    parts = [frame["positiveExcessYearShare"].rank(ascending=False), frame["minHalfExcessCagr"].rank(ascending=False),
             frame["rolling252PositiveShare"].rank(ascending=False), frame["excessCagrExTop5Names"].rank(ascending=False)]
    frame["stabilityScore"] = pd.concat(parts, axis=1).mean(axis=1)
    frame["rankStability"] = frame["stabilityScore"].rank(method="min")
    return frame.loc[sids]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--scratch", required=True)
    ap.add_argument("--h252", action="store_true")
    a = ap.parse_args(argv)
    results, paths, window = evaluate(a.scratch, a.h252)
    frame = rank_tables(results)
    suffix = "-h252" if a.h252 else ""
    (Path(a.scratch) / f"eval{suffix}.pkl").write_bytes(pickle.dumps({"results": results, "paths": paths, "window": window}))
    cols = ["cagr", "etfCagr", "excessCagr", "vol", "sharpe", "sortino", "mdd", "trackingError", "informationRatio", "annualStockTurnover",
            "meanNamesHeld", "etfOnlyRebalanceShare", "oosRankIcMean", "inSampleRankIcMean", "cagrUpperBoundTerminalAtLastClose",
            "positiveExcessYearShare", "minHalfExcessCagr", "rolling252PositiveShare", "excessCagrExTop5Names", "top5ShareOfStockContribution",
            "costDrag", "rankAbs", "rankRisk", "stabilityScore", "rankStability"]
    board = {sid: {c: (None if (isinstance(frame.at[sid, c], float) and math.isnan(frame.at[sid, c])) else frame.at[sid, c]) for c in cols}
             | {"top5Names": results[sid]["top5Names"], "terminalHitCount": len(results[sid]["terminalHits"]), "yearly": results[sid]["yearly"]}
             for sid in frame.sort_values("rankAbs").index}
    out = {"studyId": T.CONFIG["studyId"], "evidenceClass": T.CONFIG["evidenceClass"], "horizon": 252 if a.h252 else 126, "window": window,
           "strategies": len(board), "leaderboard": board}
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / f"leaderboard{suffix}.json").write_text(json.dumps(out, indent=1, default=float, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
