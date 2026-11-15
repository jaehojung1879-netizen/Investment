"""us-selection-value-v1 follow-up audit. Re-reads the saved cohorts; adds controls; changes no score, book or cost.

    python -m research.us_selection_value_v1.followup --private <dir outside git> --out research/us_selection_value_v1/results

1. BLOCK LENGTH. spec.json fixes the moving block at H/5 WEEKS (H126 -> 25, H252 -> 50 weeks); evaluate.py used round(H/25)
   (5 / 10 weeks). Every interval is recomputed here at the spec length and the old one is kept beside it.
2. PRICE vs PRICE+CONFIRMATION, TOP5. Same signal dates, common universe, five-name/two-per-sector rule, equal weight, costs.
   When fewer than five confirmed names survive the sector cap, the confirmed book holds the names it has, equally weighted and
   fully invested (no cash, no fill-in). Reported on all dates and on dates where both books hold five. Windows: all cohorts,
   cohorts whose EXIT session is on or before 2022-12-31, cohorts whose ENTRY session is on or after 2023-01-01.
3. B2 ATTRIBUTION, per horizon, reconciled from the cohort rows: net excess = universe-SPY + allocation + selection + costs, with
   the residual printed; the peer-relative selection beside it.
4. MATCHED CONTROL. For every held name of a TOP5 book: the unheld common-universe name of the same sector nearest in market cap
   (each control used once per date). Same count, same equal weights, same entry/exit, same costs. Selection vs matched = book - control.
   Market-cap exposure of each book (mean within-date cap percentile) is reported against the Top-K controls.
5. IDENTITY. Top 5/10 rebuilt at the COMPANY level (tickers sharing one filing CIK merged, e.g. GOOG/GOOGL) to measure the
   ticker-level double count; and the share of S&P member-dates without a price panel (departed issuers), by year.
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.us_selection_value_v1 import evaluate as EV  # noqa: E402

HS = (126, 252)
WINDOWS = {"ALL": None, "EXIT_BY_2022": "exit", "ENTRY_FROM_2023": "entry", "SIGNAL_2013_2022": "sig22", "SIGNAL_2023_ON": "sig23"}


def spec_block(H):
    return int(round(H / 5))          # weeks of weekly cohorts (spec: "block H/5 weeks")


def old_block(H):
    return max(1, round(H / 5 / 5))


def ci(v, H, old=False):
    return EV.block_ci(v, old_block(H) if old else spec_block(H))


def dates_of(close, sig, H):
    pos = close.index.get_loc(pd.Timestamp(sig))
    return close.index[pos + 1], close.index[pos + 1 + H]


def in_window(w, sig, entry, exit_):
    if w == "ALL":
        return True
    if w == "EXIT_BY_2022":
        return exit_ <= pd.Timestamp("2022-12-31")
    if w == "ENTRY_FROM_2023":
        return entry >= pd.Timestamp("2023-01-01")
    if w == "SIGNAL_2013_2022":
        return sig <= "2022-12-31"
    return sig >= "2023-01-01"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--private", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    P, OUT = Path(a.private), Path(a.out)
    close, feats, qqq, _ = EV.load(P)
    co = pd.read_pickle(P / "cohorts.pkl")
    res = json.loads((OUT / "result.json").read_text())
    out = {"studyId": "us-selection-value-v1", "label": "FOLLOWUP_AUDIT_EXPLORATORY"}
    ent = {}
    for (sig, H) in co[["date", "H"]].drop_duplicates().itertuples(index=False):
        ent[(sig, H)] = dates_of(close, sig, H)
    co["entry"] = [ent[(s, h)][0] for s, h in zip(co["date"], co["H"])]
    co["exit"] = [ent[(s, h)][1] for s, h in zip(co["date"], co["H"])]
    # ---- 1. block length ---------------------------------------------------------------------------------------------- #
    blk = {}
    for (s, b, H), g in co.groupby(["strategy", "book", "H"]):
        for pname, (lo, hi) in EV.PERIODS.items():
            gg = g[(g["date"] >= lo) & (g["date"] <= hi)].sort_values("date")
            if gg.empty:
                continue
            ex, pv = gg["netExcessSPY"].tolist(), gg["peerSelection"].dropna().tolist()
            blk[f"{s}|{b}|{H}|{pname}"] = {"cohorts": len(gg), "mean": float(np.mean(ex)),
                                          "ciSpecBlock": ci(ex, H), "ciOldBlock": ci(ex, H, old=True),
                                          "peerMean": float(np.mean(pv)) if pv else None, "peerCiSpecBlock": ci(pv, H), "peerCiOldBlock": ci(pv, H, old=True)}
    flips = {k: v for k, v in blk.items() if v["ciSpecBlock"] and v["ciOldBlock"]
             and ((v["ciOldBlock"][0] > 0) != (v["ciSpecBlock"][0] > 0) or (v["ciOldBlock"][1] < 0) != (v["ciSpecBlock"][1] < 0))}
    out["blockLength"] = {"spec": "H/5 weeks: 25 (H126), 50 (H252)", "implementationBefore": "round(H/25): 5, 10", "cells": blk,
                          "cellsWhoseZeroExclusionChanged": sorted(flips)}
    # patch result.json in place: spec-length intervals, old ones kept under *_oldBlock
    for k, v in res["fixedHolding"].items():
        c = blk.get(k)
        if not c:
            continue
        v["ciMeanNetExcessSPY_oldBlock"] = v.get("ciMeanNetExcessSPY")
        v["ciMeanPeerSelection_oldBlock"] = v.get("ciMeanPeerSelection")
        v["ciMeanNetExcessSPY"], v["ciMeanPeerSelection"] = c["ciSpecBlock"], c["peerCiSpecBlock"]
    pairs = {"B2_MULTIFACTOR-PRICE": ("B2_MULTIFACTOR", "PRICE"), "VALUE_CONFIRMED-WITHIN_SECTOR_VALUE": ("VALUE_CONFIRMED", "WITHIN_SECTOR_VALUE"),
             "PRICE_CONFIRMED-PRICE": ("PRICE_CONFIRMED", "PRICE")}
    for k, v in res["pairedPriceVsFinancial"].items():
        lab, b, H, pname = k.split("|")
        A_, B_ = pairs[lab]
        lo, hi = EV.PERIODS[pname]
        da = co[(co.strategy == A_) & (co.book == b) & (co.H == int(H))].set_index("date")
        db = co[(co.strategy == B_) & (co.book == b) & (co.H == int(H))].set_index("date")
        cd = sorted(d for d in set(da.index) & set(db.index) if lo <= d <= hi)
        diff = [da.at[d, "netExcessSPY"] - db.at[d, "netExcessSPY"] for d in cd]
        v["ci_oldBlock"] = v.get("ci")
        v["ci"] = ci(diff, int(H))
    res["blockLengthCorrection"] = "intervals recomputed at the spec block H/5 weeks by followup.py; *_oldBlock keeps the round(H/25) values"
    (OUT / "result.json").write_text(json.dumps(res, indent=1, sort_keys=True, default=str) + "\n")
    # ---- 2. price vs price + confirmation, TOP5 ----------------------------------------------------------------------- #
    pc = {}
    for H in HS:
        a_ = co[(co.strategy == "PRICE") & (co.book == "TOP5") & (co.H == H)].set_index("date")
        b_ = co[(co.strategy == "PRICE_CONFIRMED") & (co.book == "TOP5") & (co.H == H)].set_index("date")
        common = sorted(set(a_.index) & set(b_.index))
        short = [d for d in common if b_.at[d, "names"] < 5]
        for w in WINDOWS:
            for sub, ds in (("ALL_DATES", common), ("BOTH_FIVE", [d for d in common if b_.at[d, "names"] == 5 and a_.at[d, "names"] == 5])):
                ds = [d for d in ds if in_window(w, d, a_.at[d, "entry"], a_.at[d, "exit"])]
                if not ds:
                    pc[f"{H}|{w}|{sub}"] = {"cohorts": 0}
                    continue
                pe, ce = a_.loc[ds, "netExcessSPY"], b_.loc[ds, "netExcessSPY"]
                pq, cq = a_.loc[ds, "netExcessQQQ"], b_.loc[ds, "netExcessQQQ"]
                d_ = (ce - pe).tolist()
                pc[f"{H}|{w}|{sub}"] = {"cohorts": len(ds), "first": ds[0], "last": ds[-1],
                                        "priceVsSPY": float(pe.mean()), "priceConfirmedVsSPY": float(ce.mean()),
                                        "priceVsQQQ": float(pq.mean()), "priceConfirmedVsQQQ": float(cq.mean()),
                                        "diff": float(np.mean(d_)), "diffCi": ci(d_, H), "diffCiOldBlock": ci(d_, H, old=True),
                                        "diffWinRate": float(np.mean(np.array(d_) > 0)),
                                        "peerPrice": float(a_.loc[ds, "peerSelection"].mean()), "peerConfirmed": float(b_.loc[ds, "peerSelection"].mean())}
        pc[f"{H}|shortDates"] = {"datesWithFewerThanFiveConfirmed": len(short), "ofDates": len(common),
                                 "namesHeldOnShortDates": {str(k): int(v) for k, v in pd.Series([b_.at[d, "names"] for d in short]).value_counts().sort_index().items()},
                                 "handling": "confirmed book holds the names it has, equal weight, fully invested; no cash, no substitute"}
    nav = res["nav"]
    navt = {}
    for s in ("PRICE", "PRICE_CONFIRMED"):
        for pname in ("ALL", "exclude2023Plus", "P3"):
            x = nav.get(f"{s}|TOP5|{pname}")
            if not x or "status" in x:
                continue
            st, en = pd.Timestamp(x["start"]), pd.Timestamp(x["end"])
            q = qqq.loc[st:en]
            yrs = (len(q) - 1) / 252
            navt[f"{s}|{pname}"] = {**{k: x[k] for k in ("start", "end", "cagr", "spyCagr", "cagrMinusSpy", "vol", "trackingError", "infoRatio", "mdd", "spyMdd",
                                                          "oneWayTurnoverPerYear", "costPerYear")},
                                    "qqqCagr": float((q.iloc[-1] / q.iloc[0]) ** (1 / yrs) - 1),
                                    "qqqMdd": float((q / q.cummax() - 1).min())}
    out["priceVsConfirmedTop5"] = {"fixedHolding": pc, "rebalancingNav": navt}
    # ---- 3. B2 attribution by horizon --------------------------------------------------------------------------------- #
    att = {}
    for b in ("TOP5", "TOP_QUINTILE"):
        for H in HS:
            g = co[(co.strategy == "B2_MULTIFACTOR") & (co.book == b) & (co.H == H)]
            for pname, (lo, hi) in EV.PERIODS.items():
                gg = g[(g["date"] >= lo) & (g["date"] <= hi)]
                if gg.empty:
                    continue
                parts = {k: float(gg[k].mean()) for k in ("netExcessSPY", "largeCapAndUniverse", "sectorAllocation", "withinSectorSelection", "costs")}
                parts["residual"] = parts["netExcessSPY"] - parts["largeCapAndUniverse"] - parts["sectorAllocation"] - parts["withinSectorSelection"] - parts["costs"]
                pv = gg["peerSelection"].dropna().tolist()
                att[f"{b}|{H}|{pname}"] = {"cohorts": len(gg), **parts, "netExcessCi": ci(gg["netExcessSPY"].tolist(), H),
                                           "peerSelection": float(np.mean(pv)), "peerCi": ci(pv, H)}
    out["b2AttributionByHorizon"] = att
    # ---- 4. matched control (same sector, nearest cap, same count) ---------------------------------------------------- #
    sections = {}
    for d, g in feats.groupby("date"):
        x = EV.common(g)
        if len(x) >= 30:
            sections[d] = EV.score(x)
    held = co[co.book == "TOP5"][["strategy", "H", "date", "held", "gross", "spyNet", "netExcessSPY"]]
    mc, unmatched = defaultdict(list), defaultdict(int)
    capexp = defaultdict(list)
    for r in held.itertuples(index=False):
        x = sections.get(r.date)
        if x is None:
            continue
        e, z = dates_of(close, r.date, r.H)
        rr = close.loc[z] / close.loc[e] - 1
        used, ctrl = set(r.held), []
        for t in r.held:
            cand = x[(x["sector"] == x.at[t, "sector"]) & ~x.index.isin(used)]
            cand = cand[rr.reindex(cand.index).notna().values]
            if cand.empty:
                continue
            j = (np.log(cand["marketCap"]) - np.log(x.at[t, "marketCap"])).abs().sort_values(kind="mergesort")
            c = sorted(j.index[j == j.iloc[0]])[0]
            used.add(c)
            ctrl.append((t, c))
        if len(ctrl) != len(r.held):
            unmatched[f"{r.strategy}|{r.H}"] += 1
            continue
        book_g = float(np.mean([rr[t] for t, _ in ctrl]))
        ctrl_g = float(np.mean([rr[c] for _, c in ctrl]))
        mc[(r.strategy, r.H)].append({"date": r.date, "entry": e, "exit": z, "sel": EV.net(book_g) - EV.net(ctrl_g), "ctrlVsSpy": EV.net(ctrl_g) - r.spyNet})
        if r.H == 126:
            pct = x["marketCap"].rank(pct=True)
            capexp[r.strategy].append(float(pct.loc[list(r.held)].mean()))
    mct = {}
    for (s, H), rows in mc.items():
        df = pd.DataFrame(rows).sort_values("date")
        for w in WINDOWS:
            m = df[[in_window(w, d, e, z) for d, e, z in zip(df["date"], df["entry"], df["exit"])]]
            if len(m):
                mct[f"{s}|{H}|{w}"] = {"cohorts": len(m), "selectionVsMatched": float(m["sel"].mean()), "ci": ci(m["sel"].tolist(), H),
                                       "matchedControlVsSPY": float(m["ctrlVsSpy"].mean()), "winRate": float((m["sel"] > 0).mean())}
    out["matchedControlTop5"] = {"cells": mct, "unmatchedCohorts": dict(unmatched),
                                 "meanCapPercentileOfHeldNames": {s: float(np.mean(v)) for s, v in capexp.items()}}
    # ---- 5. identity: company-level Top-K, departed share ------------------------------------------------------------- #
    raw = pickle.load(open(P / "filings.pkl", "rb"))["raw"]
    cik = {t: rs[-1].get("cik") for t, rs in raw.items() if rs}
    g_all = feats[feats["identity"].isin(["MEMBERSHIP_CIK", "PIT_SINGLE_CIK"])].copy()
    g_all["marketCap"] = pd.to_numeric(g_all["marketCap"], errors="coerce")
    g_all = g_all.dropna(subset=["marketCap"])
    g_all["cik"] = g_all["ticker"].map(cik)
    tk = defaultdict(list)
    dup_dates = 0
    for d, g in g_all.groupby("date"):
        pos = close.index.get_loc(pd.Timestamp(d))
        if pos + 127 >= len(close) or len(g) < 100:
            continue
        e, z = close.index[pos + 1], close.index[pos + 127]
        spy = EV.net(float(close["SPY"].loc[z] / close["SPY"].loc[e] - 1))
        g = g.sort_values(["marketCap", "ticker"], ascending=[False, True])
        comp = g.drop_duplicates(subset=["cik"], keep="first")
        if len(comp) != len(g) and set(g.head(10)["ticker"]) != set(comp.head(10)["ticker"]):
            dup_dates += 1
        for lab, frame in (("TICKER", g), ("COMPANY", comp)):
            for K in (5, 10):
                top = frame.head(K)
                r = close.loc[z, top["ticker"]] / close.loc[e, top["ticker"]] - 1
                if r.isna().any():
                    continue
                w = top.set_index("ticker")["marketCap"]
                tk[(lab, K, "cap")].append((d, EV.net(float((r * w / w.sum()).sum())) - spy))
                tk[(lab, K, "equal")].append((d, EV.net(float(r.mean())) - spy))
    idt = {}
    for (lab, K, wt), v in tk.items():
        for w in ("ALL", "SIGNAL_2013_2022", "SIGNAL_2023_ON"):
            vv = [x for d, x in v if in_window(w, d, None, None)] if w != "ALL" else [x for _, x in v]
            idt[f"{lab}|TOP{K}|{wt}|{w}"] = {"cohorts": len(vv), "meanNetExcessSPY": float(np.mean(vv))}
    meta = json.loads((P / "features-meta.json").read_text())
    dep = defaultdict(lambda: [0, 0])
    for d, c in meta["funnel"].items():
        dep[d[:4]][0] += c.get("NO_PRICE_PANEL", 0)
        dep[d[:4]][1] += c.get("memberDates", 0)
    out["identity"] = {"topKTickerVsCompany_H126": idt, "datesWhereCompanyMergeChangesTop10": dup_dates,
                       "departedMemberDateShareByYear": {y: round(a_ / b_, 4) for y, (a_, b_) in sorted(dep.items()) if b_}}
    (OUT / "followup.json").write_text(json.dumps(out, indent=1, sort_keys=True, default=str) + "\n")
    print(json.dumps({"zeroExclusionChanged": len(flips), "price_vs_confirmed": {k: (v.get("diff"), v.get("diffCi")) for k, v in pc.items() if "BOTH" in k or "ALL_DATES" in k}}, default=str)[:3000])


if __name__ == "__main__":
    main()
