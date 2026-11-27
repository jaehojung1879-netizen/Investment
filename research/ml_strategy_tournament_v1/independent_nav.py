"""Independent NAV recomputation of a strategy from its RECORDED post-trade holdings and the raw closes.

It does not import tournament.simulate. Accounting is in share units: after each recorded rebalance, units = weight x NAV / close; between
rebalances value = units x close (suspended sessions carry the last close). Costs are recomputed here from the weight changes and the dated
tax schedule copied from config.json. A held name whose closes end (terminated) is worth zero after its last close (the engine's primary
lower-bound mode). The recorded weights are rounded to 1e-6, so agreement is expected to ~1e-5, not to machine precision.

    python research/ml_strategy_tournament_v1/independent_nav.py --scratch <dir> --view gated --strategy <id>
"""
from __future__ import annotations

import argparse
import json
import pickle
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
CFG = json.loads((HERE / "config.json").read_text())
BENCH = CFG["benchmark"]


def tax(date):
    rows = [r for r in CFG["portfolio"]["costs"]["stock"]["sellTaxSchedule"] if r["effectiveDate"] <= str(date.date())]
    return max(rows, key=lambda r: r["effectiveDate"])["sellTaxBps"]


def recompute(closes, holdings, start, end):
    c = closes.loc[start:end]
    carry = c.ffill()
    last_valid = {t: c[t].last_valid_index() for t in c.columns}
    end_bench = c[BENCH].last_valid_index()
    stock_cost = CFG["portfolio"]["costs"]["stock"]
    etf_cost = CFG["portfolio"]["costs"]["etf"]
    by_date = {pd.Timestamp(h["date"]): h for h in holdings}
    units = {BENCH: 1.0 / carry[BENCH].iloc[0]}
    navs = []
    for d in c.index:
        def value(t):
            lv = last_valid[t]
            if t != BENCH and lv is not None and (end_bench - lv).days > 7 and d > lv:
                return 0.0
            return units[t] * carry.at[d, t]
        nav = sum(value(t) for t in units)
        if d in by_date:
            h = by_date[d]
            cur = {t: value(t) / nav for t in units}
            new = {**h["weights"], BENCH: h["etf"]}
            cost = 0.0
            for t in set(cur) | set(new):
                dw = new.get(t, 0.0) - cur.get(t, 0.0)
                if abs(dw) < 1e-9:
                    continue
                if t == BENCH:
                    cost += abs(dw) * (etf_cost["commissionBps"] + etf_cost["spreadBps"] / 2) / 1e4
                else:
                    bps = stock_cost["commissionBps"] + stock_cost["spreadBps"] / 2 + (tax(d) if dw < 0 else 0.0)
                    cost += abs(dw) * bps / 1e4
            nav *= 1 - cost
            units = {t: w * nav / carry.at[d, t] for t, w in new.items() if w > 0}
        navs.append(nav)
    return pd.Series(navs, index=c.index)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--scratch", required=True)
    ap.add_argument("--view", default="gated")
    ap.add_argument("--strategy", action="append", required=True)
    a = ap.parse_args(argv)
    s = Path(a.scratch)
    blob = pickle.loads((s / "dataset.pkl").read_bytes())
    ev = pickle.loads((s / f"eval-{a.view}.pkl").read_bytes())
    out = {}
    for sid in a.strategy:
        p = ev["paths"][sid]
        engine = p["nav"].astype(float)
        nav = recompute(blob["closes"], p["holdings"], engine.index[0], engine.index[-1])
        yrs = (len(nav) - 1) / 252
        diff = (nav / engine - 1).abs()
        out[sid] = {"engineFinalNav": float(engine.iloc[-1]), "independentFinalNav": float(nav.iloc[-1]),
                    "engineCagr": float(engine.iloc[-1] ** (1 / yrs) - 1), "independentCagr": float(nav.iloc[-1] ** (1 / yrs) - 1),
                    "maxAbsRelativeDailyDifference": float(diff.max()), "sessions": int(len(nav)), "rebalances": len(p["holdings"]),
                    "weightSumMax": float(max(sum(h["weights"].values()) + h["etf"] for h in p["holdings"])) if p["holdings"] else None,
                    "minEtfWeight": float(min(h["etf"] for h in p["holdings"])) if p["holdings"] else None,
                    "status": "INDEPENDENTLY_REPRODUCED" if float(diff.max()) < 1e-4 else "MISMATCH"}
        print(sid, json.dumps(out[sid]))
    path = HERE / "results" / f"independent-nav-{a.view}.json"
    prev = json.loads(path.read_text()) if path.exists() else {}
    prev.update(out)
    path.write_text(json.dumps({k: v for k, v in sorted(prev.items())}, indent=1) + "\n")


if __name__ == "__main__":
    main()
