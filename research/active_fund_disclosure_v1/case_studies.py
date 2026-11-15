"""Long-run outperforming funds as CASE STUDIES (PREREGISTRATION.md section 6). Chosen after the fact; never used by the signal.

    python -m research.active_fund_disclosure_v1.case_studies --private <dir> --out research/active_fund_disclosure_v1/results

Fund return proxy: the reported equity weights held from one report date to the next (gross of fees, no intra-quarter trading),
against the S&P 500 (SPY total return) over the same dates. Characteristics come from the holdings; fees, reported turnover and
manager tenure are in N-CEN / prospectuses on www.sec.gov, which refuses this environment, and are reported as missing.
"""
from __future__ import annotations

import argparse
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

MIN_Q, MAX_GAP, TOP = 16, 120, 5


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--private", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    P, OUT = Path(a.private), Path(a.out)
    F = pd.read_parquet(P / "nport" / "filings.parquet")
    F = F[F["inSample"]].sort_values(["series_id", "report_date"])
    h = pd.read_parquet(P / "nport" / "sample-holdings.parquet", columns=["accession_number", "tk", "currency_value", "investment_country"])
    h = h[(h["investment_country"] == "US") & h["tk"].notna() & h["accession_number"].isin(F["accession"])]
    W = {acc: g.groupby("tk")["currency_value"].sum() / g["currency_value"].sum() for acc, g in h.groupby("accession_number")}
    close = pickle.load(open(P / "us" / "close.pkl", "rb"))["close"]
    feats = pd.read_pickle(P / "us" / "features.pkl")[["date", "ticker", "sector"]]
    sector = feats.drop_duplicates("ticker", keep="last").set_index("ticker")["sector"]
    rows = []
    for sid, g in F.groupby("series_id"):
        g = g[g["accession"].isin(W)]
        recs = list(g.itertuples())
        for r0, r1 in zip(recs, recs[1:]):
            gap = (r1.report_date - r0.report_date).days
            if gap > MAX_GAP:
                continue
            w0, w1 = W[r0.accession], W[r1.accession]
            names = [t for t in w0.index if t in close.columns]
            p0, p1 = close[names].asof(r0.report_date), close[names].asof(r1.report_date)
            ok = (p0 > 0) & (p1 > 0)
            ww = w0[names][ok.values] / w0[names][ok.values].sum()
            ret = float((ww * (p1[ok] / p0[ok] - 1)).sum())
            spy = float(close["SPY"].asof(r1.report_date) / close["SPY"].asof(r0.report_date) - 1)
            u = w0.index.union(w1.index)
            rows.append({"series_id": sid, "name": r0.series_name, "registrant": r0.registrant, "r0": r0.report_date, "r1": r1.report_date,
                         "ret": ret, "spy": spy, "turnover": 0.5 * float((w1.reindex(u).fillna(0) - w0.reindex(u).fillna(0)).abs().sum()),
                         "nav": r0.netAssets, "activeShare": r0.activeShare, "n": r0.nEquity, "acc": r0.accession})
    Q = pd.DataFrame(rows)
    agg = []
    for sid, g in Q.groupby("series_id"):
        if len(g) < MIN_Q:
            continue
        yrs = (g["r1"].max() - g["r0"].min()).days / 365.25
        fund, spy = float(np.prod(1 + g["ret"])), float(np.prod(1 + g["spy"]))
        accs = g["acc"].tolist()
        sec = pd.concat([W[x].groupby(W[x].index.map(sector)).sum() for x in accs], axis=1).fillna(0).mean(axis=1)
        top10 = float(np.mean([W[x].nlargest(10).sum() for x in accs]))
        agg.append({"series_id": sid, "name": g["name"].iloc[-1], "registrant": g["registrant"].iloc[-1], "quarters": int(len(g)),
                    "from": str(g["r0"].min().date()), "to": str(g["r1"].max().date()),
                    "annualExcessVsSpy": fund ** (1 / yrs) - spy ** (1 / yrs), "medianNetAssetsBn": float(g["nav"].median() / 1e9),
                    "meanActiveShare": float(g["activeShare"].mean()), "medianHoldings": float(g["n"].median()),
                    "quarterlyTurnoverProxy": float(g["turnover"].mean()), "holdingPeriodYearsProxy": float(1 / (4 * g["turnover"].mean())) if g["turnover"].mean() > 0 else None,
                    "top10Weight": top10, "largestSector": str(sec.idxmax()), "largestSectorWeight": float(sec.max()), "_sec": sec, "_accs": accs})
    A = pd.DataFrame(agg).sort_values("annualExcessVsSpy", ascending=False)
    cases = []
    for _, c in A.head(TOP).iterrows():
        others = A[A["series_id"] != c["series_id"]].copy()
        cos = others["_sec"].map(lambda s: float(np.dot(s.reindex(c["_sec"].index.union(s.index)).fillna(0), c["_sec"].reindex(c["_sec"].index.union(s.index)).fillna(0))
                                               / (np.linalg.norm(s) * np.linalg.norm(c["_sec"]))))
        others["cos"] = cos
        near = others.nlargest(10, "cos")
        peer = near.iloc[(np.log(near["medianNetAssetsBn"]) - np.log(c["medianNetAssetsBn"])).abs().argsort().iloc[0]]
        last = W[c["_accs"][-1]]
        clean = {k: v for k, v in c.items() if not k.startswith("_")}
        clean["topHoldingsLastReport"] = {t: round(float(v), 4) for t, v in last.nlargest(5).items()}
        clean["peer"] = {k: (v if not isinstance(v, float) else float(v)) for k, v in peer.items() if not k.startswith("_") and k != "cos"}
        clean["peer"]["sectorCosine"] = float(peer["cos"])
        cases.append(clean)
    dist = A["annualExcessVsSpy"]
    out = {"label": "CASE_STUDY_SELECTED_AFTER_THE_FACT_NOT_A_SIGNAL", "fundsWithAtLeast16Quarters": int(len(A)),
           "annualExcessDistribution": {"p10": float(dist.quantile(.1)), "median": float(dist.median()), "p90": float(dist.quantile(.9)),
                                        "shareAboveZero": float((dist > 0).mean())},
           "missingFields": ["fees (N-CEN / prospectus)", "reported portfolio turnover", "manager tenure", "prospectus benchmark"],
           "cases": cases}
    (OUT / "us-case-studies.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(json.dumps(out, indent=1, default=str)[:4000])


if __name__ == "__main__":
    main()
