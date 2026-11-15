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


def load_static(private: Path):
    close = pickle.load(open(private / "us" / "close.pkl", "rb"))["close"]
    feats = pd.read_pickle(private / "us" / "features.pkl")[["date", "ticker", "inCommonUniverse"]]
    return close, feats


def originals(funds):
    f = funds.dropna(subset=["series_id", "report_date", "filing_date"]).sort_values(["series_id", "report_date", "filing_date", "accession_number"])
    first = f.drop_duplicates(["series_id", "report_date"], keep="first")
    return first, int(len(f) - len(first))


def read_candidates(x: Path, accs):
    cols = ["accession_number", "series_id", "issuer_cusip", "identifier_ticker", "currency_value", "investment_country"]
    for p in sorted(x.glob("ec-*.parquet")):
        t = pd.read_parquet(p, columns=cols, filters=[("accession_number", "in", list(accs))])
        if len(t):
            yield p.name, t


def cusip_map(x: Path, accs, known):
    pairs = []
    for _, t in read_candidates(x, accs):
        tk = t["identifier_ticker"].map(norm_ticker)
        ok = tk.isin(known) & t["issuer_cusip"].notna()
        pairs.append(pd.DataFrame({"c": t.loc[ok, "issuer_cusip"], "t": tk[ok]}).drop_duplicates())
    m = pd.concat(pairs).drop_duplicates().groupby("c")["t"].agg(list)
    return {c: v[0] for c, v in m.items() if len(v) == 1}


def link(t, known, cmap):
    h = t.copy()
    h["tk"] = h["identifier_ticker"].map(norm_ticker)
    ok = h["tk"].isin(known)
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
    x = private / "nport" / "x"
    close, feats = load_static(private)
    funds = pd.read_parquet(x / "funds.parquet")
    orig, n_amend = originals(funds)
    orig = orig.copy()
    orig["passiveName"] = orig["series_name"].fillna("").map(lambda n: bool(PASSIVE.search(n)))
    cand = orig[((~orig["passiveName"]) & (orig["net_assets"] >= MIN_NAV)) | (orig["series_id"] == IVV)]
    accs = set(cand["accession_number"])
    known = set(close.columns)
    cmap = cusip_map(x, accs, known)
    meta = cand.set_index("accession_number")
    memb = {pd.Timestamp(d): set(g.loc[g["inCommonUniverse"].astype(bool), "ticker"]) for d, g in feats.groupby("date")}
    mdates = np.array(sorted(memb), dtype="datetime64[ns]")
    kept_hold, bench = [], {}
    for _, t in read_candidates(x, {a for a in accs if meta.at[a, "series_id"] == IVV}):
        h = link(t, known, cmap)
        for acc, g in h[h["tk"].notna()].groupby("accession_number"):
            bench[meta.at[acc, "report_date"]] = g.groupby("tk")["currency_value"].sum() / g["currency_value"].sum()
        kept_hold.append(h)
    bdates = np.array(sorted(bench), dtype="datetime64[ns]")
    rows, weights, bcache = [], {}, {}
    for fname, t in read_candidates(x, accs - set(meta.index[meta["series_id"] == IVV])):
        h = link(t, known, cmap)
        keep_acc = []
        for acc, g in h.groupby("accession_number"):
            m = meta.loc[acc]
            r = m["report_date"]
            us = g[g["investment_country"] == "US"]
            nav = float(m["net_assets"])
            k = mdates[mdates <= np.datetime64(r)]
            mem = memb[pd.Timestamp(k[-1])] if len(k) else set()
            b = bdates[(bdates <= np.datetime64(r)) & (bdates >= np.datetime64(r - pd.Timedelta(days=BENCH_LAG)))]
            if r not in bcache:
                bcache[r] = drift(bench[pd.Timestamp(b[-1])], close, pd.Timestamp(b[-1]), r) if len(b) else None
            bw = bcache[r]
            eqv = float(us["currency_value"].sum())
            lk = us[us["tk"].notna()]
            w = lk.groupby("tk")["currency_value"].sum() / eqv if eqv > 0 else pd.Series(dtype=float)
            sp = float(w[w.index.isin(mem)].sum())
            active = None
            if bw is not None and eqv > 0:
                u = w.index.union(bw.index)
                active = 0.5 * float((w.reindex(u).fillna(0) - bw.reindex(u).fillna(0)).abs().sum() + (1 - w.sum()))
            row = {"accession": acc, "series_id": m["series_id"], "series_name": m["series_name"], "cik": m["cik"],
                   "registrant": m["registrant_name"], "report_date": r, "filing_date": m["filing_date"], "netAssets": nav,
                   "nEquity": int(us["issuer_cusip"].nunique()), "usEquityShare": eqv / nav if nav > 0 else np.nan,
                   "linkedValueShare": float(lk["currency_value"].sum() / eqv) if eqv > 0 else np.nan,
                   "linkedByCusipShare": float(lk.loc[lk["linkBy"] == "CUSIP", "currency_value"].sum() / eqv) if eqv > 0 else np.nan,
                   "sp500Share": sp, "activeShare": active, "benchmarkFound": bw is not None, "passiveName": False}
            row["qualifies"] = bool(nav >= MIN_NAV and row["usEquityShare"] >= MIN_EQ and row["nEquity"] >= MIN_N
                                    and sp >= MIN_SP and active is not None and active >= MIN_AS)
            rows.append(row)
            if row["qualifies"]:
                weights[acc] = w
                keep_acc.append(acc)
        hk = h[h["accession_number"].isin(keep_acc)].copy()
        hk = hk.merge(meta[["report_date", "filing_date"]], left_on="accession_number", right_index=True)
        kept_hold.append(hk)
        print(fname, len(rows), len(weights), flush=True)
    F = pd.DataFrame(rows)
    F["clone"] = False
    for r, g in F[F["qualifies"]].groupby("report_date"):
        accl = g.sort_values("netAssets", ascending=False)["accession"].tolist()
        if len(accl) < 2:
            continue
        cols = sorted(set().union(*[weights[a].index for a in accl]))
        ix = {t: i for i, t in enumerate(cols)}
        M = sparse.lil_matrix((len(accl), len(cols)))
        for i, a in enumerate(accl):
            for t, v in weights[a].items():
                M[i, ix[t]] = v
        M = M.tocsr()
        nrm = np.sqrt(M.multiply(M).sum(axis=1)).A.ravel()
        S = (M @ M.T).toarray() / np.outer(nrm, nrm)
        kept = []
        for i, a in enumerate(accl):
            if any(S[i, j] >= CLONE_COS for j in kept):
                F.loc[F["accession"] == a, "clone"] = True
            else:
                kept.append(i)
    F["inSample"] = F["qualifies"] & ~F["clone"]
    passive_counts = {"originalFilingsAll": int(len(orig)), "passiveNameFilings": int(orig["passiveName"].sum()),
                      "nonPassiveBelowMinNav": int(((~orig["passiveName"]) & (orig["net_assets"] < MIN_NAV)).sum())}
    h = pd.concat(kept_hold, ignore_index=True)
    return F, h, bench, n_amend, close, passive_counts


def stats(F, h, n_amend, close, pc):
    S = F[F["inSample"]].copy()
    S["lagDays"] = (S["filing_date"] - S["report_date"]).dt.days
    hs = h[h["accession_number"].isin(S["accession"]) & (h["investment_country"] == "US")]
    first = close.apply(lambda s: s.first_valid_index())
    lastv = close.apply(lambda s: s.last_valid_index())
    priced = hs["tk"].map(first).le(hs["filing_date"]) & hs["tk"].map(lastv).ge(hs["filing_date"])
    last = F[F["inSample"]].groupby("series_id")["report_date"].max()
    lastq = F["report_date"].max()
    yr = S.groupby(S["report_date"].dt.year).agg(series=("series_id", "nunique"), filings=("accession", "count"),
                                                 medianNetAssetsBn=("netAssets", lambda v: float(v.median() / 1e9)),
                                                 medianActiveShare=("activeShare", "median"))
    return {
        "sourceRelease": "GCAP Public Security-Level Data on U.S. Fund Holdings (Cavani, Maggiori, Schreger 2025), N-PORT public flat files",
        "reportDates": [str(F["report_date"].min().date()), str(F["report_date"].max().date())],
        "amendmentsIgnored": n_amend, "originalFilingsAllFunds": pc["originalFilingsAll"],
        "screens": {"passiveNameFilings": pc["passiveNameFilings"], "nonPassiveBelowMinNav": pc["nonPassiveBelowMinNav"],
                    "screenedEquityFilings": int(len(F)), "screenedEquitySeries": int(F["series_id"].nunique()),
                    "qualifyingFilings": int(F["qualifies"].sum()),
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
    F, h, bench, n_amend, close, pc = build(P)
    F.to_parquet(P / "nport" / "filings.parquet", index=False)
    h[h["accession_number"].isin(F.loc[F["inSample"], "accession"]) | (h["series_id"] == IVV)].to_parquet(P / "nport" / "sample-holdings.parquet", index=False)
    pickle.dump(bench, open(P / "nport" / "bench.pkl", "wb"))
    st = stats(F, h, n_amend, close, pc)
    (OUT / "us-sample.json").write_text(json.dumps(st, indent=1, default=str) + "\n")
    print(json.dumps(st, indent=1, default=str))


if __name__ == "__main__":
    main()
