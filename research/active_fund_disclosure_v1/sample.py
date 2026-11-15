"""US active large-cap fund sample from N-PORT, with S&P 500 active weights. Reads no return; links holdings to prices only to
check that a price EXISTS at the public date.

    python -m research.active_fund_disclosure_v1.sample --private <dir holding nport/x and us/> --out research/active_fund_disclosure_v1/results

Definitions (all decided from what a filing itself shows on its public date, so they are knowable at that time):
  ORIGINAL FILING   per (series_id, report_date) the accession with the earliest filing_date. Later accessions for the same series and
                    report date are amendments and are counted, not used. A series is one portfolio, so its share classes are one vote.
  PUBLIC DATE       filing_date (EDGAR acceptance date of the NPORT-P). A signal on date d may use a filing only if filing_date < d, and
                    the book trades at the close of the session after d, so at least one full session passes after publication.
  TICKER LINK       identifier_ticker normalised ('.', '/', ' ' -> '-'); if absent or unknown, the CUSIP -> ticker map learned from
                    the filings' own ticker-linked rows (a CUSIP mapped to more than one ticker is dropped).
  BENCHMARK         S&P 500 constituent weights from the iShares Core S&P 500 ETF's own N-PORT holdings (IVV, series S000004310),
                    taken from its latest report on or before the fund's report date (at most 100 days earlier) and drifted to the
                    fund's report date by price. Stated as a proxy: prospectus benchmarks are on www.sec.gov, which refuses this
                    environment, so every fund is measured against the S&P 500.
  ACTIVE LARGE-CAP  a filing qualifies when ALL hold: series name without index/ETF/passive words; net assets >= $100m; long US common
                    equity >= 80% of net assets; >= 20 equity holdings; >= 70% of equity value in linked S&P 500 names (the PIT
                    membership of the replay universe); active share vs the S&P 500 proxy >= 0.40.
  CLONES            on one report date, qualifying series whose equity weight vectors have cosine similarity >= 0.95 are one portfolio;
                    the largest by net assets is kept (feeder/VIT/retail clones of one manager decision are not counted twice).
"""
from __future__ import annotations

import argparse
import json
import pickle
import re
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse

PASSIVE = re.compile(r"\bINDEX\b|\bIDX\b|\bETF\b|S&P|S & P|RUSSELL|NASDAQ|\bDOW\b|TOTAL STOCK|TOTAL MARKET|EXTENDED MARKET|"
                     r"EQUAL WEIGHT|\b500\b|\b1000\b|\b2000\b|\b3000\b|PASSIVE|TRACKER|MSCI|CRSP|FTSE|SPDR|ISHARES|PROSHARES|"
                     r"DIREXION|LEVERAGED|INVERSE|\b2X\b|\b3X\b|BUFFER|DEFINED OUTCOME|TARGET DATE|\b20[2-6]\d\b|RETIREMENT", re.I)
IVV = "S000004310"
MIN_NAV, MIN_EQ, MIN_N, MIN_SP, MIN_AS, CLONE_COS, BENCH_LAG = 1e8, 0.80, 20, 0.70, 0.40, 0.95, 100


def norm_ticker(t):
    if not isinstance(t, str) or not t.strip():
        return None
    return re.sub(r"[./ ]", "-", t.strip().upper())


def load(private: Path):
    x = private / "nport" / "x"
    funds = pd.read_parquet(x / "funds.parquet")
    hold = pd.concat([pd.read_parquet(p) for p in sorted(x.glob("ec-*.parquet"))], ignore_index=True)
    close = pickle.load(open(private / "us" / "close.pkl", "rb"))["close"]
    feats = pd.read_pickle(private / "us" / "features.pkl")[["date", "ticker", "inCommonUniverse", "marketCap", "sector"]]
    return funds, hold, close, feats


def originals(funds):
    f = funds.dropna(subset=["series_id", "report_date", "filing_date"]).sort_values(["series_id", "report_date", "filing_date", "accession_number"])
    first = f.drop_duplicates(["series_id", "report_date"], keep="first")
    return first, int(len(f) - len(first))


def link(hold, known):
    h = hold.copy()
    h["tk"] = h["identifier_ticker"].map(norm_ticker)
    ok = h["tk"].isin(known)
    cmap = h[ok & h["issuer_cusip"].notna()].groupby("issuer_cusip")["tk"].agg(lambda s: s.unique().tolist())
    cmap = {c: v[0] for c, v in cmap.items() if len(v) == 1}
    fill = ~ok & h["issuer_cusip"].map(cmap).notna()
    h.loc[fill, "tk"] = h.loc[fill, "issuer_cusip"].map(cmap)
    h["linkBy"] = np.where(ok, "TICKER", np.where(fill, "CUSIP", "NONE"))
    h.loc[h["linkBy"] == "NONE", "tk"] = None
    return h


def drift(w, close, d0, d1):
    names = [t for t in w.index if t in close.columns]
    r = (close[names].asof(d1) / close[names].asof(d0)).reindex(w.index)
    v = w * r.fillna(1.0)
    return v / v.sum()


def build(private: Path):
    funds, hold, close, feats = load(private)
    orig, n_amend = originals(funds)
    known = set(close.columns)
    h = link(hold[hold["accession_number"].isin(orig["accession_number"])], known)
    h = h.merge(orig[["accession_number", "series_id", "series_name", "cik", "registrant_name", "report_date", "filing_date", "net_assets"]],
                on=["accession_number", "series_id"], how="left")
    memb = {d: set(g.loc[g["inCommonUniverse"].astype(bool), "ticker"]) for d, g in feats.groupby("date")}
    mdates = np.array(sorted(memb))
    # benchmark weights from IVV's own filings
    ivv = h[(h["series_id"] == IVV) & h["tk"].notna()]
    bench = {r: g.groupby("tk")["currency_value"].sum() / g["currency_value"].sum() for r, g in ivv.groupby("report_date")}
    bdates = np.array(sorted(bench))
    rows, weights = [], {}
    for acc, g in h.groupby("accession_number"):
        r = g["report_date"].iloc[0]
        us = g[g["investment_country"] == "US"]
        nav = float(g["net_assets"].iloc[0]) if pd.notna(g["net_assets"].iloc[0]) else np.nan
        k = mdates[mdates <= np.datetime64(r)]
        mem = memb[pd.Timestamp(k[-1])] if len(k) else set()
        b = bdates[(bdates <= np.datetime64(r)) & (bdates >= np.datetime64(r - pd.Timedelta(days=BENCH_LAG)))]
        bw = drift(bench[pd.Timestamp(b[-1])], close, pd.Timestamp(b[-1]), r) if len(b) else None
        eqv = float(us["currency_value"].sum())
        lk = us[us["tk"].notna()]
        w = lk.groupby("tk")["currency_value"].sum() / eqv if eqv > 0 else pd.Series(dtype=float)
        sp = float(w[w.index.isin(mem)].sum())
        active = None
        if bw is not None and eqv > 0:
            u = w.index.union(bw.index)
            active = 0.5 * float((w.reindex(u).fillna(0) - bw.reindex(u).fillna(0)).abs().sum() + (1 - w.sum()))
        name = str(g["series_name"].iloc[0])
        row = {"accession": acc, "series_id": g["series_id"].iloc[0], "series_name": name, "cik": g["cik"].iloc[0],
               "registrant": g["registrant_name"].iloc[0], "report_date": r, "filing_date": g["filing_date"].iloc[0],
               "netAssets": nav, "nEquity": int(us["issuer_cusip"].nunique()), "usEquityShare": eqv / nav if nav and nav > 0 else np.nan,
               "linkedValueShare": float(lk["currency_value"].sum() / eqv) if eqv > 0 else np.nan,
               "linkedByCusipShare": float(lk.loc[lk["linkBy"] == "CUSIP", "currency_value"].sum() / eqv) if eqv > 0 else np.nan,
               "sp500Share": sp, "activeShare": active, "benchmarkFound": bw is not None, "passiveName": bool(PASSIVE.search(name))}
        row["qualifies"] = bool(not row["passiveName"] and nav >= MIN_NAV and row["usEquityShare"] >= MIN_EQ and row["nEquity"] >= MIN_N
                                and sp >= MIN_SP and active is not None and active >= MIN_AS)
        rows.append(row)
        if row["qualifies"]:
            weights[acc] = w
    F = pd.DataFrame(rows)
    # clones on the same report date
    F["clone"] = False
    for r, g in F[F["qualifies"]].groupby("report_date"):
        accs = g.sort_values("netAssets", ascending=False)["accession"].tolist()
        if len(accs) < 2:
            continue
        cols = sorted(set().union(*[weights[a].index for a in accs]))
        ix = {t: i for i, t in enumerate(cols)}
        M = sparse.lil_matrix((len(accs), len(cols)))
        for i, a in enumerate(accs):
            for t, v in weights[a].items():
                M[i, ix[t]] = v
        M = M.tocsr()
        nrm = np.sqrt(M.multiply(M).sum(axis=1)).A.ravel()
        S = (M @ M.T).toarray() / np.outer(nrm, nrm)
        kept = []
        for i, a in enumerate(accs):
            if any(S[i, j] >= CLONE_COS for j in kept):
                F.loc[F["accession"] == a, "clone"] = True
            else:
                kept.append(i)
    F["inSample"] = F["qualifies"] & ~F["clone"]
    return F, h, bench, weights, n_amend, close


def stats(F, h, n_amend, close):
    S = F[F["inSample"]].copy()
    S["lagDays"] = (S["filing_date"] - S["report_date"]).dt.days
    hs = h[h["accession_number"].isin(S["accession"]) & (h["investment_country"] == "US")]
    priced = hs["tk"].notna() & hs.apply(lambda r: r["tk"] in close.columns and pd.notna(close[r["tk"]].asof(r["filing_date"])) if r["tk"] else False, axis=1)
    last = F[F["inSample"]].groupby("series_id")["report_date"].max()
    lastq = F["report_date"].max()
    yr = S.groupby(S["report_date"].dt.year).agg(series=("series_id", "nunique"), filings=("accession", "count"),
                                                 medianNetAssetsBn=("netAssets", lambda v: float(v.median() / 1e9)),
                                                 medianActiveShare=("activeShare", "median"))
    return {
        "sourceRelease": "GCAP Public Security-Level Data on U.S. Fund Holdings (Cavani, Maggiori, Schreger 2025), N-PORT public flat files",
        "reportDates": [str(F["report_date"].min().date()), str(F["report_date"].max().date())],
        "allSeriesWithEquity": int(F["series_id"].nunique()), "allOriginalFilings": int(len(F)), "amendmentsIgnored": n_amend,
        "screens": {"passiveName": int(F["passiveName"].sum()), "qualifyingFilings": int(F["qualifies"].sum()),
                    "cloneFilingsDropped": int(F["clone"].sum()), "inSampleFilings": int(len(S)), "inSampleSeries": int(S["series_id"].nunique()),
                    "inSampleRegistrants": int(S["cik"].nunique())},
        "byReportYear": {int(k): {kk: (round(vv, 3) if isinstance(vv, float) else int(vv)) for kk, vv in v.items()} for k, v in yr.to_dict("index").items()},
        "disclosureLagDays": {"p10": float(S["lagDays"].quantile(.1)), "median": float(S["lagDays"].median()), "p90": float(S["lagDays"].quantile(.9)),
                              "max": int(S["lagDays"].max())},
        "publicDateConfirmedShare": float(S["filing_date"].notna().mean()),
        "benchmarkLinkShare": float(F.loc[F["qualifies"], "benchmarkFound"].mean()),
        "linkRates": {"tickerOrCusipValueShare": float(S["linkedValueShare"].median()), "viaCusipValueShare": float(S["linkedByCusipShare"].median()),
                      "pricedAtPublicDateHoldingShare": float(priced.mean())},
        "seriesEndedBeforeLastQuarter": int((last < lastq - pd.Timedelta(days=200)).sum()),
        "seriesInSample": int(len(last)),
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--private", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    P, OUT = Path(a.private), Path(a.out)
    OUT.mkdir(parents=True, exist_ok=True)
    F, h, bench, weights, n_amend, close = build(P)
    F.to_parquet(P / "nport" / "filings.parquet", index=False)
    h[h["accession_number"].isin(F.loc[F["inSample"], "accession"]) | (h["series_id"] == IVV)].to_parquet(P / "nport" / "sample-holdings.parquet", index=False)
    pickle.dump(bench, open(P / "nport" / "bench.pkl", "wb"))
    st = stats(F, h, n_amend, close)
    (OUT / "us-sample.json").write_text(json.dumps(st, indent=1, default=str) + "\n")
    print(json.dumps(st, indent=1, default=str))


if __name__ == "__main__":
    main()
