"""us-selection-value-v1 evaluation: the frozen spec.json applied to the point-in-time cross-sections from features.py.

    python -m research.us_selection_value_v1.evaluate --private <dir outside git> --out research/us_selection_value_v1/results

Only aggregates are written to --out; per-name forward returns stay in --private.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import pickle
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pipeline import us_decision_pilot as UP  # noqa: E402
from pipeline.benchmark_alpha import REALISTIC_COSTS  # noqa: E402

HERE = Path(__file__).resolve().parent
SPEC = json.loads((HERE / "spec.json").read_text())
POL = REALISTIC_COSTS["US"]
BUY = (POL["commissionBps"] + POL["spreadBps"] / 2) / 1e4
SELL = BUY + POL["sellTaxBps"] / 1e4
HS = (126, 252)
STRATS = ("PRICE", "SECTOR_MOMENTUM_BASKET", "WITHIN_SECTOR_VALUE", "CASH_PROFITABILITY", "VALUE_CONFIRMED", "PRICE_CONFIRMED", "B2_MULTIFACTOR")
BOOKS = ("TOP5", "TOP_QUINTILE")
PERIODS = {**{k: tuple(v) for k, v in SPEC["periods"].items()}, "ALL": ("2013-01-01", "2026-12-31")}   # ALL: the whole window, added for the report
REQ = ["momentum252", "vol252", *UP.ACCOUNTING, "netIncomeTTM", "operatingCashFlowTTM", "operatingCashFlowTTMPrior", "marketCap", "equity"]
QQQ_FIX = ("2020-09-21", 0.38824)


# --------------------------------------------------------------------------- scores and books (signal-time only)
def common(g: pd.DataFrame) -> pd.DataFrame:
    x = g[g["inCommonUniverse"] & g["identity"].isin(["MEMBERSHIP_CIK", "PIT_SINGLE_CIK"])].copy()
    for c in REQ:
        x[c] = pd.to_numeric(x[c], errors="coerce")
    x = x.replace([np.inf, -np.inf], np.nan).dropna(subset=REQ)
    x = x[x["marketCap"] > 0].set_index("ticker")
    return x


def score(x: pd.DataFrame) -> pd.DataFrame:
    s = UP.scores(x[["momentum252", "vol252", *UP.ACCOUNTING, "sector"]].copy())
    x = x.loc[s.index].copy()
    x["PRICE"] = s["B1"]
    x["B2_MULTIFACTOR"] = s["B2"]
    x["earningsYield"] = x["netIncomeTTM"] / x["marketCap"]
    x["bookYield"] = x["equity"] / x["marketCap"]
    by = x.groupby("sector")
    x["WITHIN_SECTOR_VALUE"] = (by["earningsYield"].rank(pct=True) + by["bookYield"].rank(pct=True)) / 2
    x["CASH_PROFITABILITY"] = by["cashOperatingProfitability"].rank(pct=True)
    x["confirmed"] = (x["netIncomeTTM"] > 0) & (x["operatingCashFlowTTM"] > 0) & (x["operatingCashFlowTTM"] > x["operatingCashFlowTTMPrior"])
    x["VALUE_CONFIRMED"] = x["WITHIN_SECTOR_VALUE"].where(x["confirmed"])
    x["PRICE_CONFIRMED"] = x["PRICE"].where(x["confirmed"])
    sec = by["momentum252"].mean()
    top_sector = sorted(sec.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    x["SECTOR_MOMENTUM_BASKET"] = (x["sector"] == top_sector).astype(float).where(x["sector"] == top_sector)
    x["capTercile"] = by["marketCap"].transform(lambda v: pd.qcut(v.rank(method="first"), 3, labels=False) if len(v) >= 3 else 0)
    return x


def book(x: pd.DataFrame, strat: str, kind: str) -> list[str]:
    s = x[strat].dropna()
    if s.empty:
        return []
    if strat == "SECTOR_MOMENTUM_BASKET":
        return sorted(s.index)
    order = sorted(s.index, key=lambda t: (-s[t], t))
    if kind == "TOP_QUINTILE":
        return order[:max(1, math.ceil(len(s) / 5))]
    out, per = [], Counter()
    for t in order:
        if per[x.at[t, "sector"]] >= 2:
            continue
        out.append(t)
        per[x.at[t, "sector"]] += 1
        if len(out) == 5:
            break
    return out


# --------------------------------------------------------------------------- outcomes
def load(private: Path):
    close = pickle.load(open(private / "close.pkl", "rb"))["close"]
    feats = pd.read_pickle(private / "features.pkl")
    raw = pd.read_csv(ROOT / "data/research/us-dual-benchmark-v1/spy-qqq-total-return.csv.gz")
    q = raw[raw.ticker == "QQQ"].set_index("date")
    prev = q.loc[:QQQ_FIX[0]].iloc[-2]          # the session before the ex-date
    factor = 1 + QQQ_FIX[1] / float(prev["rawClose"])
    qqq = close["QQQ"].copy()
    qqq[qqq.index >= pd.Timestamp(QQQ_FIX[0])] *= factor
    return close, feats, qqq, {"qqqDistributionFactor": factor}


def net(gross):
    return (1 - BUY) * (1 + gross) * (1 - SELL) - 1


def cohort(close, qqq, day, x, H):
    pos = close.index.get_loc(day)
    e, z = pos + 1, pos + 1 + H
    if z >= len(close):
        return None, "NOT_MATURED"
    a, b = close.iloc[e], close.iloc[z]
    r = (b / a - 1).reindex(x.index)
    spy = float(close["SPY"].iloc[z] / close["SPY"].iloc[e] - 1)
    qq = float(qqq.iloc[z] / qqq.iloc[e] - 1)
    return {"r": r, "spy": spy, "qqq": qq, "entry": close.index[e], "exit": close.index[z]}, "MATURED"


def attribution(x, names, r):
    """gross book return decomposed against the equal-weight common universe (names without an exit are left out of the universe means)."""
    u = x.assign(r=r).dropna(subset=["r"])
    Ru = u["r"].mean()
    sec_u = u.groupby("sector")["r"].mean()
    wu = u.groupby("sector").size() / len(u)
    b = x.loc[names].assign(r=r.loc[names])
    wb = b.groupby("sector").size() / len(b)
    Rb_s = b.groupby("sector")["r"].mean()
    alloc = float(sum((wb.get(s, 0) - wu.get(s, 0)) * (sec_u.get(s, Ru) - Ru) for s in set(wb.index) | set(wu.index)))
    select = float(sum(wb[s] * (Rb_s[s] - sec_u.get(s, np.nan)) for s in wb.index))
    peers = []
    for t in names:
        grp = u[(u["sector"] == x.at[t, "sector"]) & (u["capTercile"] == x.at[t, "capTercile"])]
        grp = grp.drop(index=t, errors="ignore")
        if len(grp):
            peers.append(r[t] - grp["r"].mean())
    return {"universeEW": float(Ru), "sectorAllocation": alloc, "withinSectorSelection": select,
            "peerSelection": float(np.mean(peers)) if peers else None, "universeNames": int(len(u))}


def block_ci(series, block, draws=2000, seed=20261115):
    v = np.asarray([s for s in series if s is not None and np.isfinite(s)], float)
    n = len(v)
    if n < 2 * block or block < 1:
        return None
    rng = np.random.default_rng(seed)
    means = []
    for _ in range(draws):
        idx = []
        while len(idx) < n:
            st = rng.integers(0, n - block + 1)
            idx.extend(range(st, st + block))
        means.append(v[idx[:n]].mean())
    return [float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))]


def greedy_nonoverlap(dates, H_weeks):
    count, last = 0, None
    for d in dates:
        if last is None or (d - last).days >= H_weeks * 7:
            count, last = count + 1, d
    return count


def summarise(rows, H):
    if not rows:
        return {"cohorts": 0}
    ex = np.array([r["netExcessSPY"] for r in rows])
    block = max(1, round(H / 5 / 5))   # H sessions ~ H/5 weeks; block of a fifth of that
    out = {"cohorts": len(rows), "first": rows[0]["date"], "last": rows[-1]["date"],
           "nonOverlapping": greedy_nonoverlap([pd.Timestamp(r["date"]) for r in rows], H / 5),
           "meanNetExcessSPY": float(ex.mean()), "medianNetExcessSPY": float(np.median(ex)), "winRateSPY": float((ex > 0).mean()),
           "p10NetExcessSPY": float(np.percentile(ex, 10)), "sdNetExcessSPY": float(ex.std(ddof=1)) if len(ex) > 1 else None,
           "meanNetExcessQQQ": float(np.mean([r["netExcessQQQ"] for r in rows])),
           "meanNetBook": float(np.mean([r["net"] for r in rows])), "meanNetSPY": float(np.mean([r["spyNet"] for r in rows])),
           "ciMeanNetExcessSPY": block_ci(ex, block), "meanNames": float(np.mean([r["names"] for r in rows])),
           "meanNameOverlapWithPreviousCohort": float(np.nanmean([r["overlap"] for r in rows if r["overlap"] is not None])) if any(r["overlap"] is not None for r in rows) else None}
    for k in ("largeCapAndUniverse", "sectorAllocation", "withinSectorSelection", "costs", "peerSelection"):
        v = [r[k] for r in rows if r[k] is not None]
        out["mean_" + k] = float(np.mean(v)) if v else None
    pv = [r["peerSelection"] for r in rows if r["peerSelection"] is not None]
    out["ciMeanPeerSelection"] = block_ci(pv, block)
    out["infoRatioCohort"] = float(ex.mean() / ex.std(ddof=1)) if len(ex) > 1 and ex.std(ddof=1) > 0 else None
    return out


def period_of(day):
    t = str(day)[:10]
    return [k for k, (a, b) in PERIODS.items() if a <= t <= b]


# --------------------------------------------------------------------------- rebalancing NAV
def nav_paths(close, orders_by_strat, start, end):
    prices = close.loc[start:end]
    out = {}
    for name, sched in orders_by_strat.items():
        accts, fail = [], None
        for k in range(4):
            orders = {prices.index[1]: {"SPY": 1.0}} if name != "SPY" else {prices.index[1]: {"SPY": 1.0}}
            if name != "SPY":
                for d, w in sched[k].items():
                    if d in prices.index and d >= prices.index[1]:
                        orders[d] = w
            cols = sorted({t for w in orders.values() for t in w})
            try:
                accts.append(UP.simulate(prices[cols], orders))
            except ValueError as e:
                fail = str(e)
                break
        if fail:
            out[name] = {"status": "NOT_ESTIMABLE", "reason": fail}
            continue
        navs = sum(a["nav"] for a in accts) / 4
        turnover = sum(a["twoWayTurnover"] for a in accts) / 4
        cost = sum(a["costInitialCapital"] for a in accts) / 4
        out[name] = {"nav": navs, "turnover": turnover, "cost": cost}
    return out


def nav_metrics(p, spy):
    nav = p["nav"]
    r = nav.pct_change().iloc[1:]
    rs = spy.pct_change().iloc[1:]
    yrs = len(r) / 252
    act = r - rs
    yearly = {}
    for y, g in nav.groupby(nav.index.year):
        s = spy.loc[g.index]
        prev = nav[nav.index < g.index[0]]
        sprev = spy[spy.index < g.index[0]]
        a0 = prev.iloc[-1] if len(prev) else g.iloc[0]
        b0 = sprev.iloc[-1] if len(sprev) else s.iloc[0]
        yearly[str(y)] = {"book": float(g.iloc[-1] / a0 - 1), "spy": float(s.iloc[-1] / b0 - 1)}
    cagr = float((nav.iloc[-1] / nav.iloc[0]) ** (1 / yrs) - 1)
    scagr = float((spy.iloc[-1] / spy.iloc[0]) ** (1 / yrs) - 1)
    return {"start": str(nav.index[0].date()), "end": str(nav.index[-1].date()), "cagr": cagr, "spyCagr": scagr, "cagrMinusSpy": cagr - scagr,
            "vol": float(r.std() * np.sqrt(252)), "trackingError": float(act.std() * np.sqrt(252)),
            "infoRatio": float(act.mean() * 252 / (act.std() * np.sqrt(252))) if act.std() > 0 else None,
            "sharpe0": float(r.mean() / r.std() * np.sqrt(252)), "mdd": float((nav / nav.cummax() - 1).min()),
            "spyMdd": float((spy / spy.cummax() - 1).min()),
            "oneWayTurnoverPerYear": float(p["turnover"].sum() / 2 / yrs), "costPerYear": float(p["cost"].sum() / yrs), "yearly": yearly}


# --------------------------------------------------------------------------- main
def run(private: Path):
    close, feats, qqq, fx = load(private)
    dates = sorted(feats["date"].unique())
    sections, funnel_year = {}, defaultdict(Counter)
    for d in dates:
        g = feats[feats["date"] == d]
        x = common(g)
        y = d[:4]
        funnel_year[y]["signalWeeks"] += 1
        funnel_year[y]["pricedMemberRows"] += len(g)
        funnel_year[y]["commonUniverseRows"] += len(x)
        if len(x) < SPEC["universe"]["minimumNames"]:
            funnel_year[y]["weeksBelowMinimum"] += 1
            continue
        funnel_year[y]["eligibleWeeks"] += 1
        sections[pd.Timestamp(d)] = score(x)
    # cohorts
    per = {(s, b, H): [] for s in STRATS for b in BOOKS for H in HS}
    states = {(s, b, H): Counter() for s in STRATS for b in BOOKS for H in HS}
    prev_names = {}
    private_rows = []
    for day, x in sections.items():
        for H in HS:
            c, st = cohort(close, qqq, day, x, H)
            for s in STRATS:
                for b in BOOKS:
                    key = (s, b, H)
                    names = book(x, s, b)
                    if not names:
                        states[key]["NO_ELIGIBLE_NAME"] += 1
                        continue
                    if c is None:
                        states[key][st] += 1
                        continue
                    rr = c["r"].loc[names]
                    if rr.isna().any():
                        states[key]["UNRESOLVED_HELD_EXIT"] += 1
                        continue
                    states[key]["RESOLVED"] += 1
                    gross = float(rr.mean())
                    att = attribution(x, names, c["r"])
                    nb, ns, nq = net(gross), net(c["spy"]), net(c["qqq"])
                    pn = prev_names.get(key)
                    row = {"date": str(day.date()), "names": len(names), "gross": gross, "net": nb, "spyNet": ns,
                           "netExcessSPY": nb - ns, "netExcessQQQ": nb - nq,
                           "largeCapAndUniverse": att["universeEW"] - c["spy"], "sectorAllocation": att["sectorAllocation"],
                           "withinSectorSelection": att["withinSectorSelection"], "costs": nb - gross - (ns - c["spy"]),
                           "peerSelection": att["peerSelection"],
                           "overlap": (len(set(names) & set(pn)) / len(names)) if pn else None}
                    per[key].append(row)
                    prev_names[key] = names
                    private_rows.append({"strategy": s, "book": b, "H": H, **row, "held": names,
                                         "contrib": {t: float(rr[t] / len(names)) for t in names}})
    return close, qqq, sections, per, states, funnel_year, private_rows, fx


def topk_control(close, feats):
    out = {}
    g_all = feats[feats["identity"].isin(["MEMBERSHIP_CIK", "PIT_SINGLE_CIK"])].copy()
    g_all["marketCap"] = pd.to_numeric(g_all["marketCap"], errors="coerce")
    g_all = g_all.dropna(subset=["marketCap"])
    for H in HS:
        rows = defaultdict(list)
        for d, g in g_all.groupby("date"):
            day = pd.Timestamp(d)
            pos = close.index.get_loc(day)
            if pos + 1 + H >= len(close) or len(g) < 100:
                continue
            e, z = pos + 1, pos + 1 + H
            g = g.sort_values(["marketCap", "ticker"], ascending=[False, True])
            spy = net(float(close["SPY"].iloc[z] / close["SPY"].iloc[e] - 1))
            for K in (5, 10, 100):
                top = g.head(K)
                r = (close.iloc[z][top.ticker] / close.iloc[e][top.ticker] - 1)
                if r.isna().any():
                    continue
                w = top.set_index("ticker")["marketCap"]
                rows[(K, "cap")].append((d, net(float((r * w / w.sum()).sum())) - spy))
                rows[(K, "equal")].append((d, net(float(r.mean())) - spy))
        for (K, wt), v in rows.items():
            for pname, (a, b) in PERIODS.items():
                vv = [e for d, e in v if a <= d <= b]
                if vv:
                    out.setdefault(str(H), {}).setdefault(f"TOP{K}_{wt}", {})[pname] = {"cohorts": len(vv), "meanNetExcessSPY": float(np.mean(vv)),
                                                                                       "winRate": float(np.mean(np.array(vv) > 0))}
    return out


def ai_capex(close, sections):
    rows, hist = [], []
    for day, x in sections.items():
        sp = x[x["sector"].isin(["Information Technology", "Communication Services", "Consumer Discretionary"])].copy()
        sp["capexTTM"] = pd.to_numeric(sp["capexTTM"], errors="coerce").abs()
        sp["capexTTMPrior"] = pd.to_numeric(sp["capexTTMPrior"], errors="coerce").abs()
        sp = sp.dropna(subset=["capexTTM", "capexTTMPrior"])
        if len(sp) < 10:
            continue
        top = sp.sort_values(["capexTTM"], ascending=False).head(10)
        g = float(top["capexTTM"].sum() / top["capexTTMPrior"].sum() - 1)
        regime = None
        if len(hist) >= 52:
            regime = "HIGH" if g > float(np.median(hist)) else "LOW"
        hist.append(g)
        it = sorted(x.index[x["sector"] == "Information Technology"])
        rows.append({"day": day, "growth": g, "regime": regime, "spenders": list(top.index), "itProxy": it})
    out = {}
    for H in HS:
        acc = defaultdict(list)
        for r in rows:
            if r["regime"] is None:
                continue
            pos = close.index.get_loc(r["day"])
            if pos + 1 + H >= len(close):
                continue
            e, z = pos + 1, pos + 1 + H
            spy = net(float(close["SPY"].iloc[z] / close["SPY"].iloc[e] - 1))
            for basket in ("spenders", "itProxy"):
                names = r[basket]
                rr = close.iloc[z][names] / close.iloc[e][names] - 1
                if rr.isna().any() or not names:
                    continue
                per = [k for k, (a, b) in PERIODS.items() if a <= str(r["day"].date()) <= b and k not in ("exclude2023Plus", "ALL")]
                for p in per + ["ALL"]:
                    acc[(basket, r["regime"], p)].append(net(float(rr.mean())) - spy)
        out[str(H)] = {f"{b}|{reg}|{p}": {"cohorts": len(v), "meanNetExcessSPY": float(np.mean(v)), "winRate": float(np.mean(np.array(v) > 0))}
                       for (b, reg, p), v in sorted(acc.items())}
    latest = rows[-1] if rows else None
    return out, {"growthSeries": [{"date": str(r["day"].date()), "spenderCapexGrowth": r["growth"], "regime": r["regime"]} for r in rows[::4]],
                 "latest": {"date": str(latest["day"].date()), "growth": latest["growth"], "regime": latest["regime"], "spenders": latest["spenders"]} if latest else None}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--private", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    private, outdir = Path(a.private), Path(a.out)
    outdir.mkdir(parents=True, exist_ok=True)
    close, qqq, sections, per, states, funnel_year, prows, fx = run(private)
    feats = pd.read_pickle(private / "features.pkl")
    res = {"studyId": SPEC["studyId"], "evidenceClass": SPEC["evidenceClass"], "specSha256": hashlib.sha256((HERE / "spec.json").read_bytes()).hexdigest(),
           "costs": {"buy": BUY, "sell": SELL}, "benchmarkAdjustments": fx, "fixedHolding": {}, "states": {}, "pairedPriceVsFinancial": {}}
    for (s, b, H), rows in per.items():
        res["states"][f"{s}|{b}|{H}"] = dict(states[(s, b, H)])
        for pname, (lo, hi) in PERIODS.items():
            rr = [r for r in rows if lo <= r["date"] <= hi]
            res["fixedHolding"][f"{s}|{b}|{H}|{pname}"] = summarise(rr, H)
    pairs = {"B2_MULTIFACTOR-PRICE": ("B2_MULTIFACTOR", "PRICE"), "VALUE_CONFIRMED-WITHIN_SECTOR_VALUE": ("VALUE_CONFIRMED", "WITHIN_SECTOR_VALUE"),
             "PRICE_CONFIRMED-PRICE": ("PRICE_CONFIRMED", "PRICE")}
    for label, (A, B) in pairs.items():
        for b in BOOKS:
            for H in HS:
                da = {r["date"]: r for r in per[(A, b, H)]}
                db = {r["date"]: r for r in per[(B, b, H)]}
                for pname, (lo, hi) in PERIODS.items():
                    common_d = sorted(d for d in set(da) & set(db) if lo <= d <= hi)
                    diff = [da[d]["netExcessSPY"] - db[d]["netExcessSPY"] for d in common_d]
                    pdiff = [da[d]["peerSelection"] - db[d]["peerSelection"] for d in common_d
                             if da[d]["peerSelection"] is not None and db[d]["peerSelection"] is not None]
                    res["pairedPriceVsFinancial"][f"{label}|{b}|{H}|{pname}"] = {
                        "commonCohorts": len(common_d), "meanDiffNetExcess": float(np.mean(diff)) if diff else None,
                        "ci": block_ci(diff, max(1, round(H / 25))), "meanDiffPeerSelection": float(np.mean(pdiff)) if pdiff else None}
    # yearly by signal year
    yearly = {}
    for (s, b, H), rows in per.items():
        for y in sorted({r["date"][:4] for r in rows}):
            v = [r["netExcessSPY"] for r in rows if r["date"][:4] == y]
            yearly[f"{s}|{b}|{H}|{y}"] = {"cohorts": len(v), "meanNetExcessSPY": float(np.mean(v))}
    res["yearlyBySignalYear"] = yearly
    # leave-one-year-out and top-contributor dependence (TOP5 and TOP_QUINTILE, both H)
    dep = {}
    pr = pd.DataFrame(prows)
    for (s, b, H), rows in per.items():
        if not rows:
            continue
        ex = pd.Series({r["date"]: r["netExcessSPY"] for r in rows})
        yrs = sorted({d[:4] for d in ex.index})
        loyo = {y: float(ex[[d for d in ex.index if d[:4] != y]].mean()) for y in yrs if len(ex[[d for d in ex.index if d[:4] != y]])}
        sub = pr[(pr.strategy == s) & (pr.book == b) & (pr.H == H)]
        contrib = Counter()
        for _, r in sub.iterrows():
            for t, c in r["contrib"].items():
                contrib[t] += c
        top = [t for t, _ in contrib.most_common(5)]
        # mean excess after removing the top-5 contributing names from every book (equal re-weighting of the rest; dropped if empty)
        alt = []
        for _, r in sub.iterrows():
            keep = [t for t in r["held"] if t not in top]
            if keep:
                g = sum(r["contrib"][t] for t in keep) * r["names"] / len(keep)
                alt.append(net(g) - r["spyNet"])
        dep[f"{s}|{b}|{H}"] = {"mean": float(ex.mean()), "leaveOneSignalYearOut": loyo,
                               "yearsWhoseRemovalFlipsSign": [y for y, v in loyo.items() if np.sign(v) != np.sign(ex.mean())],
                               "topContributors": top, "meanWithoutTopContributors": float(np.mean(alt)) if alt else None,
                               "cohortsWithoutTopContributors": len(alt)}
    res["dependence"] = dep
    # missing-cohort bounds: weeks with a signal date but no resolved cohort, filled at the worst / best observed excess
    bounds = {}
    all_dates = [str(d.date()) for d in sections]
    for (s, b, H), rows in per.items():
        if not rows:
            continue
        have = {r["date"] for r in rows}
        last_mature = max(have)
        miss = [d for d in all_dates if d not in have and d <= last_mature]
        ex = np.array([r["netExcessSPY"] for r in rows])
        lo = (ex.sum() + len(miss) * ex.min()) / (len(ex) + len(miss))
        hi = (ex.sum() + len(miss) * ex.max()) / (len(ex) + len(miss))
        bounds[f"{s}|{b}|{H}"] = {"missingCohorts": len(miss), "observedMean": float(ex.mean()), "worstFill": float(lo), "bestFill": float(hi),
                                  "signFlipsWithinBounds": bool(np.sign(lo) != np.sign(hi))}
    res["missingCohortBounds"] = bounds
    # NAV: four staggered accounts, every period separately and the full window
    sched = {}
    sec_days = sorted(sections)
    for s in STRATS:
        for b in BOOKS:
            acc = [{}, {}, {}, {}]
            for i, d in enumerate(sec_days):
                names = book(sections[d], s, b)
                pos = close.index.get_loc(d)
                if pos + 1 < len(close) and names:
                    acc[i % 4][close.index[pos + 1]] = {t: 1 / len(names) for t in names}
            sched[f"{s}|{b}"] = acc
    res["nav"] = {}
    for pname, (lo, hi) in PERIODS.items():
        days = [d for d in sec_days if lo <= str(d.date()) <= hi]
        if len(days) < 8:
            continue
        start, end = days[0], min(close.index[-1], pd.Timestamp(hi))
        paths = nav_paths(close, sched, start, end)
        spy = close["SPY"].loc[start:end]
        for k, p in paths.items():
            res["nav"][f"{k}|{pname}"] = p if "status" in p else nav_metrics(p, spy)
    res["topKControl"] = topk_control(close, feats)
    res["aiCapex"], res["aiCapexSeries"] = ai_capex(close, sections)
    res["yearSample"] = {y: dict(c) for y, c in sorted(funnel_year.items())}
    meta = json.load(open(private / "features-meta.json"))
    fy = defaultdict(Counter)
    for d, c in meta["funnel"].items():
        fy[d[:4]].update(c)
    res["exclusionReasonsByYear"] = {y: dict(c) for y, c in sorted(fy.items())}
    res["cikRuleValidation"] = meta["cikRuleValidation"]
    res["asTradedStatus"] = meta["asTradedStatus"]
    (outdir / "result.json").write_text(json.dumps(res, indent=1, sort_keys=True, default=str) + "\n")
    pd.DataFrame(prows).drop(columns=["contrib"]).to_pickle(private / "cohorts.pkl")
    print(json.dumps({k: v for k, v in res["fixedHolding"].items() if k.endswith("|ALL")} or {"done": True})[:200])


if __name__ == "__main__":
    main()
