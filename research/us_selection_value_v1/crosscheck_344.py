"""Independent re-computation of the #344 numbers that the in-repository inputs can reach (no #344 private packet exists here).

    python -m research.us_selection_value_v1.crosscheck_344 --private <dir outside git> --pr344-ref <git ref of #344's head>

What is recomputed, from the ORIGINAL pilot inputs (replay-v16 prices, Finnhub filings, membership CIK), not #344's corrected pool:
  B2 control   pilot complete cases (MEMBERSHIP_CIK identity, four accounting fields, momentum/vol, non-financial), the pilot's
               B2 top ceil(N/5) equal weight, net of 8.0/8.3 bp, minus SPY net, H126/H252, signal years 2023/2024/2025(Q1)
  Top-K pool   the same pilot pool ranked by this study's market-cap proxy (Finnhub weighted diluted shares x as-traded close),
               Top 5/10 cap- and equal-weighted, same costs and horizons
#344 used SEC companyfacts outstanding shares, its own corrected price paths (PARA, mixed-CIK removal, SEC asset supplement) and
selects within its corrected pool, so agreement is expected in sign and rough size, not to the basis point. Every difference is
reported; nothing here edits #344.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import pickle
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pipeline import us_decision_pilot as UP  # noqa: E402

from research.us_selection_value_v1 import evaluate as EV  # noqa: E402

HERE = Path(__file__).resolve().parent
START, END = "2023-04-14", "2025-03-07"


def pr344_csv(ref, name):
    raw = subprocess.check_output(["git", "show", f"{ref}:research/us_topk_market_cap_v1/results/{name}"], cwd=ROOT).decode()
    return list(csv.DictReader(io.StringIO(raw)))


def pr344_json(ref, name):
    return json.loads(subprocess.check_output(["git", "show", f"{ref}:research/us_topk_market_cap_v1/results/{name}"], cwd=ROOT))


def pilot_pool(g):
    x = g[g["inCommonUniverse"] & (g["identity"] == "MEMBERSHIP_CIK")].copy()
    req = ["momentum252", "vol252", *UP.ACCOUNTING]
    for c in req + ["marketCap"]:
        x[c] = pd.to_numeric(x[c], errors="coerce")
    x = x.replace([np.inf, -np.inf], np.nan).dropna(subset=req).set_index("ticker")
    return x


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--private", required=True)
    ap.add_argument("--pr344-ref", required=True)
    a = ap.parse_args(argv)
    P = Path(a.private)
    close = pickle.load(open(P / "close.pkl", "rb"))["close"]
    feats = pd.read_pickle(P / "features.pkl")
    feats = feats[(feats["date"] >= START) & (feats["date"] <= END)]
    rows = {k: [] for k in ("B2", "TOP5_cap", "TOP5_equal", "TOP10_cap", "TOP10_equal")}
    rows = {(k, H): [] for k in rows for H in (126, 252)}
    pool_sizes = []
    for d, g in feats.groupby("date"):
        x = pilot_pool(g)
        if len(x) < UP.MIN_NAMES:
            continue
        s = UP.scores(x[["momentum252", "vol252", *UP.ACCOUNTING]].copy())
        pool_sizes.append(len(s))
        b2 = sorted(s.index, key=lambda t: (-s.at[t, "B2"], t))[:max(1, math.ceil(len(s) / 5))]
        capped = x.dropna(subset=["marketCap"]).sort_values(["marketCap"], ascending=False)
        day = pd.Timestamp(d)
        pos = close.index.get_loc(day)
        for H in (126, 252):
            if pos + 1 + H >= len(close):
                continue
            e, z = pos + 1, pos + 1 + H
            spy = EV.net(float(close["SPY"].iloc[z] / close["SPY"].iloc[e] - 1))
            r = close.iloc[z] / close.iloc[e] - 1
            rb = r.reindex(b2)
            if not rb.isna().any():
                rows[("B2", H)].append((d, EV.net(float(rb.mean())) - spy))
            for K in (5, 10):
                top = capped.head(K)
                rr = r.reindex(top.index)
                if len(top) < K or rr.isna().any():
                    continue
                w = top["marketCap"] / top["marketCap"].sum()
                rows[(f"TOP{K}_cap", H)].append((d, EV.net(float((rr * w).sum())) - spy))
                rows[(f"TOP{K}_equal", H)].append((d, EV.net(float(rr.mean())) - spy))
    ours = {}
    for (k, H), v in rows.items():
        for y in ("2023", "2024", "2025", "ALL"):
            vv = [e for d, e in v if y == "ALL" or d[:4] == y]
            if vv:
                ours[f"{k}|{H}|{y}"] = {"cohorts": len(vv), "meanNetExcessSPY": float(np.mean(vv))}
    theirs = {}
    for r in pr344_csv(a.pr344_ref, "fixed-holding-performance.csv"):
        if r["pool"] != "CORRECTED_FINANCIAL_POOL" or r["k"] not in ("5", "10") or not r["mean_excess"]:
            continue
        wt = "cap" if r["weighting"] == "company_market_cap" else "equal"
        theirs[f"TOP{r['k']}_{wt}|{r['horizon']}|{r['signal_year']}"] = {"cohorts": int(r["complete_cohorts"]), "meanNetExcessSPY": float(r["mean_excess"])}
    for r in pr344_json(a.pr344_ref, "financial-control-summary.json"):
        if r.get("mean_excess") is not None:
            theirs[f"B2|{r['horizon']}|{r['signal_year']}"] = {"cohorts": r["complete_cohorts"], "meanNetExcessSPY": r["mean_excess"]}
    comp = {}
    for k in sorted(set(ours) | set(theirs)):
        o, t = ours.get(k), theirs.get(k)
        comp[k] = {"thisRecompute": o, "pr344": t,
                   "difference": (o["meanNetExcessSPY"] - t["meanNetExcessSPY"]) if o and t else None,
                   "sameSign": bool(np.sign(o["meanNetExcessSPY"]) == np.sign(t["meanNetExcessSPY"])) if o and t else None}
    out = {"label": "INDEPENDENT_RECOMPUTE_OF_PR344_FROM_ORIGINAL_PILOT_INPUTS", "pr344Ref": a.pr344_ref,
           "window": [START, END], "meanPilotPoolSize": float(np.mean(pool_sizes)) if pool_sizes else None, "comparison": comp,
           "signAgreement": {"agree": sum(1 for v in comp.values() if v["sameSign"] is True), "disagree": sum(1 for v in comp.values() if v["sameSign"] is False)},
           "basisDifferences": ["#344 shares: SEC companyfacts outstanding; here: Finnhub weighted diluted (proxy)",
                                "#344 prices: corrected private paths (PARA, WBD/KVUE packets); here: replay-v16 as sealed",
                                "#344 pool: corrected single-CIK pool with 599 SEC asset fills and 171 mixed-CIK pairs removed; here: original pilot pool",
                                "#344 Top-K ranks companies (classes merged); here: tickers by proxy cap"]}
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results/crosscheck-pr344.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(json.dumps({k: v for k, v in comp.items() if k.endswith("|ALL") or k.startswith("B2")}, default=str)[:3000])


if __name__ == "__main__":
    main()
