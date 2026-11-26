"""US active-fund overweight disclosure signal (OW_BREADTH) against the frozen US baselines — PREREGISTRATION.md sections 2-5.

    python -m research.active_fund_disclosure_v1.evaluate_us --private <dir with nport/ and us/> --out research/active_fund_disclosure_v1/results

Reuses the frozen sleeves (evaluate.score / evaluate.book), the fixed 25% cocktail and U1 (alpha_search_round6_v1.us), evaluate.net
costs for fixed holding and us_decision_pilot.simulate for staggered ledgers.
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
from research.active_fund_disclosure_v1 import sample as SM  # noqa: E402
from research.alpha_search_round6_v1 import common as CM  # noqa: E402
from research.alpha_search_round6_v1 import us as R6  # noqa: E402
from research.us_selection_value_v1 import evaluate as EV  # noqa: E402
from research.us_selection_value_v1 import followup as FU  # noqa: E402
from research.us_selection_value_v1 import restored_compare as RCMP  # noqa: E402

VALID_DAYS, MIN_FUNDS = 200, 30
AI_LED = pd.Timestamp("2023-01-03")
STRATS = ("OW_TOP5", "OW_MATCHED", "PRICE_CONFIRMED", "PRICE_CONFIRMED_OW", "COCKTAIL", "COCKTAIL_OW", "U1", "U1_OW")
PAIRS = {"A_OW_TOP5_vs_MATCHED": ("OW_TOP5", "OW_MATCHED"), "B_PRICE_CONFIRMED_OW_vs_BASE": ("PRICE_CONFIRMED_OW", "PRICE_CONFIRMED"),
         "C_COCKTAIL_OW_vs_BASE": ("COCKTAIL_OW", "COCKTAIL"), "D_U1_OW_vs_U1": ("U1_OW", "U1")}
PRIMARY = ("A_OW_TOP5_vs_MATCHED", "B_PRICE_CONFIRMED_OW_vs_BASE", "C_COCKTAIL_OW_vs_BASE")


# --------------------------------------------------------------------------- per-filing active weights
def filing_active(P):
    F = pd.read_parquet(P / "nport" / "filings.parquet")
    F = F[F["inSample"]]
    h = pd.read_parquet(P / "nport" / "sample-holdings.parquet")
    bench = pickle.load(open(P / "nport" / "bench.pkl", "rb"))
    close = pickle.load(open(P / "us" / "close.pkl", "rb"))["close"]
    bdates = np.array(sorted(bench))
    out = {}
    for acc, g in h[h["accession_number"].isin(F["accession"]) & (h["investment_country"] == "US")].groupby("accession_number"):
        r = g["report_date"].iloc[0]
        eqv = float(g["currency_value"].sum())
        w = g[g["tk"].notna()].groupby("tk")["currency_value"].sum() / eqv
        b = bdates[(bdates <= np.datetime64(r)) & (bdates >= np.datetime64(r - pd.Timedelta(days=SM.BENCH_LAG)))]
        bw = SM.drift(bench[pd.Timestamp(b[-1])], close, pd.Timestamp(b[-1]), r)
        u = w.index.union(bw.index)
        out[acc] = (w.reindex(u).fillna(0.0) - bw.reindex(u).fillna(0.0))
    meta = F.set_index("accession")[["series_id", "report_date", "filing_date"]]
    return meta.loc[list(out)], out


def ow_breadth(meta, active, d, universe):
    m = meta[(meta["filing_date"] < d) & (meta["report_date"] >= d - pd.Timedelta(days=VALID_DAYS))]
    m = m.sort_values("filing_date").groupby("series_id").tail(1)
    if len(m) < MIN_FUNDS:
        return None, len(m)
    A = pd.concat([active[a].reindex(universe).fillna(np.nan) for a in m.index], axis=1)
    # a universe name absent from a fund's active vector is a name neither held nor in the IVV proxy: not overweight, active 0
    A = A.fillna(0.0)
    breadth = (A > 0).mean(axis=1)
    return breadth + 1e-9 * A.mean(axis=1).rank(pct=True), len(m)


# --------------------------------------------------------------------------- books
def masked(x, keep):
    y = x.copy()
    for c in ("PRICE", "PRICE_CONFIRMED", "WITHIN_SECTOR_VALUE", "CASH_PROFITABILITY", "SECTOR_MOMENTUM_BASKET"):
        y[c] = y[c].where(keep)
    return y


def matched(x, names):
    used, out = set(names), []
    for t in names:
        c = x[(x["sector"] == x.at[t, "sector"]) & ~x.index.isin(used)]
        if c.empty:
            return None
        m = (np.log(c["marketCap"].astype(float)) - np.log(float(x.at[t, "marketCap"]))).abs().idxmin()
        used.add(m)
        out.append(m)
    return out


def eq(names):
    return {t: 1 / len(names) for t in names} if names else {"SPY": 1.0}


def books_for(x, ow):
    x = x.copy()
    x["OW"] = ow.reindex(x.index).fillna(0.0)
    keep = x["OW"].rank(pct=True, method="average") >= 0.5
    xo = masked(x, keep)
    top = EV.book(x, "OW", "TOP5")
    mt = matched(x, top)
    b = {"OW_TOP5": eq(top), "OW_MATCHED": eq(mt) if mt else None,
         "PRICE_CONFIRMED": eq(EV.book(x, "PRICE_CONFIRMED", "TOP5")), "PRICE_CONFIRMED_OW": eq(EV.book(xo, "PRICE_CONFIRMED", "TOP5")),
         "COCKTAIL": R6.sleeve_book(x, R6.EQUAL), "COCKTAIL_OW": R6.sleeve_book(xo, R6.EQUAL)}
    b["U1"] = R6.top5_neutral(x, b["COCKTAIL"])[0]
    b["U1_OW"] = R6.top5_neutral(x, b["COCKTAIL_OW"])[0]
    return b


def exposure(w, x, top10):
    sec = defaultdict(float)
    for t, v in w.items():
        sec[x.at[t, "sector"] if t in x.index else "SPY"] += v
    caps = [(v, np.log(float(x.at[t, "marketCap"]))) for t, v in w.items() if t in x.index]
    return {"top10Weight": sum(v for t, v in w.items() if t in top10), "largestSectorWeight": max(sec.values()),
            "meanLogCap": sum(v * c for v, c in caps) / sum(v for v, _ in caps) if caps else np.nan, "sectors": dict(sec)}


# --------------------------------------------------------------------------- run
def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--private", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    P, OUT = Path(a.private), Path(a.out)
    close, feats, qqq, _ = EV.load(P / "us")
    secs = RCMP.sections_of(feats)
    meta, active = filing_active(P)
    cap = feats.copy()
    cap["marketCap"] = pd.to_numeric(cap["marketCap"], errors="coerce")
    top10 = {pd.Timestamp(d): set(g.dropna(subset=["marketCap"]).sort_values("marketCap", ascending=False).head(10)["ticker"])
             for d, g in cap[cap["identity"].isin(["MEMBERSHIP_CIK", "PIT_SINGLE_CIK"])].groupby("date")}
    books, nfunds, expo = {s: {} for s in STRATS}, {}, defaultdict(list)
    for d in sorted(secs):
        x = secs[d]
        ow, n = ow_breadth(meta, active, d, x.index)
        nfunds[d] = n
        if ow is None:
            continue
        b = books_for(x, ow)
        if b["OW_MATCHED"] is None:
            continue
        for s in STRATS:
            books[s][d] = b[s]
        for pair, (s1, s0) in PAIRS.items():
            e1, e0 = exposure(b[s1], x, top10.get(d, set())), exposure(b[s0], x, top10.get(d, set()))
            secs_u = set(e1["sectors"]) | set(e0["sectors"])
            expo[pair].append({"date": d, "dTop10": e1["top10Weight"] - e0["top10Weight"],
                               "dLargestSector": e1["largestSectorWeight"] - e0["largestSectorWeight"],
                               "sectorShift": 0.5 * sum(abs(e1["sectors"].get(k, 0) - e0["sectors"].get(k, 0)) for k in secs_u),
                               "dMeanLogCap": e1["meanLogCap"] - e0["meanLogCap"]})
    dates = sorted(books["OW_TOP5"])
    res = {"studyId": "active-fund-disclosure-v1", "market": "US", "label": "EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_HISTORY",
           "signalDates": [str(dates[0].date()), str(dates[-1].date()), len(dates)],
           "validFundsPerDate": {"min": int(min(nfunds[d] for d in dates)), "median": float(np.median([nfunds[d] for d in dates])),
                                 "max": int(max(nfunds[d] for d in dates))},
           "exposureChange": {p: {k: float(pd.DataFrame(v)[k].mean()) for k in ("dTop10", "dLargestSector", "sectorShift", "dMeanLogCap")}
                              for p, v in expo.items()},
           "fixed": {}, "ledgers": {}}
    for H in (126, 252):
        rows, unres = [], []
        for d in dates:
            cs = {s: R6.cohort_w(close, qqq, books[s][d], d, H) for s in STRATS}
            if any(v is None for v in cs.values()):
                continue
            if any("unresolved" in v for v in cs.values()):
                unres.append({"date": str(d.date()), **{k: v["unresolved"] for k, v in cs.items() if "unresolved" in v}})
                continue
            rows.append({"date": d, "entry": cs["COCKTAIL"]["entry"], "spy": cs["COCKTAIL"]["spy"], "qqq": cs["COCKTAIL"]["qqq"],
                         **{f"{s}_net": v["net"] for s, v in cs.items()}})
        df = pd.DataFrame(rows)
        block = FU.spec_block(H)
        samples = {"FULL": df, "BEFORE_2023": df[df["entry"] < AI_LED], "AI_LED_FROM_2023": df[df["entry"] >= AI_LED]}
        cell = {"unresolvedCohorts": unres}
        for nm, s in samples.items():
            if s.empty:
                continue
            row = {"cohorts": int(len(s)), "first": str(s["date"].iloc[0].date()), "last": str(s["date"].iloc[-1].date())}
            for st in STRATS:
                row[st] = {"vsSPY": CM.boot((s[f"{st}_net"] - s["spy"]).tolist(), block), "vsQQQ": float((s[f"{st}_net"] - s["qqq"]).mean())}
            row["increments"] = {p: CM.boot((s[f"{a1}_net"] - s[f"{a0}_net"]).tolist(), block) for p, (a1, a0) in PAIRS.items()}
            cell[nm] = row
        res["fixed"][str(H)] = cell
        print("fixed", H, {n: {p: round(c["increments"][p]["mean"] * 100, 2) for p in PAIRS} for n, c in cell.items() if isinstance(c, dict) and "increments" in c}, flush=True)
    (OUT / "us-disclosure.json").write_text(json.dumps(res, indent=1, sort_keys=True, default=str) + "\n")
    start, end = dates[0], close.index[-1]
    for every in (26, 52):
        for s in STRATS:
            res["ledgers"][f"L{every}|{s}"] = R6.ledger_w(close, books[s], every, start, end)
            v = res["ledgers"][f"L{every}|{s}"]
            print("ledger", every, s, round(v.get("excess", np.nan) * 100, 2), round(v.get("mdd", np.nan) * 100, 1), flush=True)
    full = res["fixed"]["126"]
    adj = CM.holm({p: full["FULL"]["increments"][p]["pOneSided"] for p in PRIMARY})
    verdict = {}
    for p in PRIMARY:
        inc = full["FULL"]["increments"][p]
        halves = [full[k]["increments"][p]["mean"] for k in ("BEFORE_2023", "AI_LED_FROM_2023") if k in full]
        rest = inc["mean"] > 0 and len(halves) == 2 and all(h > 0 for h in halves)
        verdict[p] = {"mean": inc["mean"], "pOneSided": inc["pOneSided"], "holmP": adj[p], "halves": halves,
                      "verdict": "DISCLOSURE_INCREMENT_SUPPORTED" if rest and adj[p] < 0.05 else "DIRECTIONAL_ONLY" if rest else "NOT_SUPPORTED"}
    res["judgement"] = verdict
    (OUT / "us-disclosure.json").write_text(json.dumps(res, indent=1, sort_keys=True, default=str) + "\n")
    print(json.dumps(verdict, indent=1, default=str))


if __name__ == "__main__":
    main()
