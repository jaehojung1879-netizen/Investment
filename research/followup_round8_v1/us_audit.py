"""US — look-ahead audit of the #347 disclosure sample and the point-in-time rebuild (PREREGISTRATION.md A1). Reads no return.

    python -m research.followup_round8_v1.us_audit --private <dir with nport/ and us/> --out research/followup_round8_v1/results

Builds three signal inputs, each {accession: active-weight vector} plus filing metadata, into <private>/nport/round8/:
  O   #347 as published: benchmark = latest IVV report <= fund report date (IVV publication ignored), CUSIP map learned from all filings,
      clones resolved by size.
  C1  the SAME in-sample filings, active weights recomputed with L1 (IVV published on or before the fund) and L2 (CUSIP pairs seen in
      filings published on or before the fund) corrected.
  C2  the screens, active share and clone removal re-run with L1, L2 and L3 (clones resolved in publication order) corrected.
"""
from __future__ import annotations

import argparse
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse

from research.active_fund_disclosure_v1 import sample as SM


def candidates(x: Path):
    funds = pd.read_parquet(x / "funds.parquet")
    orig, _ = SM.originals(funds)
    orig = orig.copy()
    orig["passiveName"] = orig["series_name"].fillna("").map(lambda n: bool(SM.PASSIVE.search(n)))
    cand = orig[((~orig["passiveName"]) & (orig["net_assets"] >= SM.MIN_NAV)) | (orig["series_id"] == SM.IVV)]
    return cand.set_index("accession_number")


def pair_first_seen(x: Path, meta, known):
    """(cusip, ticker) pairs with the earliest publication date of a filing that showed them (ticker in the price panel)."""
    parts = []
    for _, t in SM.read_candidates(x, set(meta.index)):
        tk = t["identifier_ticker"].map(SM.norm_ticker)
        ok = tk.isin(known) & t["issuer_cusip"].notna()
        p = pd.DataFrame({"cusip": t.loc[ok, "issuer_cusip"], "tk": tk[ok], "seen": t.loc[ok, "accession_number"].map(meta["filing_date"])})
        parts.append(p.groupby(["cusip", "tk"])["seen"].min().reset_index())
    return pd.concat(parts).groupby(["cusip", "tk"])["seen"].min().reset_index()


def link_pit(t, known, pairs, fdate):
    """Direct ticker match, else the CUSIP's ticker among pairs seen in filings published on or before this filing (unique only)."""
    h = t.copy().reset_index(drop=True)
    h["F"] = h["accession_number"].map(fdate)
    h["tk"] = h["identifier_ticker"].map(SM.norm_ticker)
    direct = h["tk"].isin(known)
    rest = h[~direct & h["issuer_cusip"].notna()][["issuer_cusip", "F"]].reset_index()
    m = rest.merge(pairs, left_on="issuer_cusip", right_on="cusip")
    m = m[m["seen"] <= m["F"]]
    u = m.groupby("index")["tk"].agg(lambda s: s.iloc[0] if s.nunique() == 1 else None).dropna()
    h["linkBy"] = np.where(direct, "TICKER", "NONE")
    h.loc[~direct, "tk"] = None
    h.loc[u.index, "tk"] = u.values
    h.loc[u.index, "linkBy"] = "CUSIP"
    return h


def ivv_reports(x: Path, meta, known, pairs, close):
    """IVV weights per report date with its own publication date (PIT-linked at its publication)."""
    ivv = meta[meta["series_id"] == SM.IVV]
    out = {}
    for _, t in SM.read_candidates(x, set(ivv.index)):
        h = link_pit(t, known, pairs, meta["filing_date"])
        for acc, g in h[h["tk"].notna()].groupby("accession_number"):
            out[meta.at[acc, "report_date"]] = (meta.at[acc, "filing_date"], g.groupby("tk")["currency_value"].sum() / g["currency_value"].sum())
    return out


def bench_for(r, F, ivv, close, cache):
    """L1: latest IVV report on or before r (within 100 days) whose PUBLICATION is on or before the fund's publication F."""
    ok = [d for d, (fd, _) in ivv.items() if d <= r and d >= r - pd.Timedelta(days=SM.BENCH_LAG) and fd <= F]
    if not ok:
        return None
    d0 = max(ok)
    key = (d0, r)
    if key not in cache:
        cache[key] = SM.drift(ivv[d0][1], close, d0, r)
    return cache[key]


def weights_of(g):
    us = g[g["investment_country"] == "US"]
    eqv = float(us["currency_value"].sum())
    lk = us[us["tk"].notna()]
    w = lk.groupby("tk")["currency_value"].sum() / eqv if eqv > 0 else pd.Series(dtype=float)
    return us, eqv, lk, w


def active_vec(w, bw):
    u = w.index.union(bw.index)
    return w.reindex(u).fillna(0.0) - bw.reindex(u).fillna(0.0)


def dedupe(F, weights, pit):
    """Size rule (#347) or publication-order rule (L3). Returns the set of dropped accessions and, for the size rule, the drops whose
    keeper was published later than the dropped filing."""
    dropped, late_keeper = set(), 0
    for r, g in F[F["qualifies"]].groupby("report_date"):
        g = g.sort_values(["filing_date", "netAssets"], ascending=[True, False]) if pit else g.sort_values("netAssets", ascending=False)
        accl = g["accession"].tolist()
        if len(accl) < 2:
            continue
        cols = sorted(set().union(*[weights[a].index for a in accl]))
        ix = {t: i for i, t in enumerate(cols)}
        Mx = sparse.lil_matrix((len(accl), len(cols)))
        for i, a in enumerate(accl):
            for t, v in weights[a].items():
                Mx[i, ix[t]] = v
        Mx = Mx.tocsr()
        nrm = np.sqrt(Mx.multiply(Mx).sum(axis=1)).A.ravel()
        S = (Mx @ Mx.T).toarray() / np.outer(nrm, nrm)
        fd = g["filing_date"].tolist()
        kept = []
        for i, a in enumerate(accl):
            hits = [j for j in kept if S[i, j] >= SM.CLONE_COS and (not pit or fd[j] <= fd[i])]
            if hits:
                dropped.add(a)
                if not pit and any(fd[j] > fd[i] for j in hits):
                    late_keeper += 1
            else:
                kept.append(i)
    return dropped, late_keeper


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--private", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    P, OUT = Path(a.private), Path(a.out)
    x = P / "nport" / "x"
    R = P / "nport" / "round8"
    R.mkdir(parents=True, exist_ok=True)
    close, feats = SM.load_static(P)
    known = set(close.columns)
    meta = candidates(x)
    pairs = pair_first_seen(x, meta, known)
    ivv = ivv_reports(x, meta, known, pairs, close)
    # ---------------- O: #347 inputs as published, and the leak measurements on them
    F0 = pd.read_parquet(P / "nport" / "filings.parquet")
    S0 = F0[F0["inSample"]]
    h0 = pd.read_parquet(P / "nport" / "sample-holdings.parquet")
    h0 = h0[h0["accession_number"].isin(S0["accession"])]
    ivv_rep = sorted(ivv)
    l1 = []
    for row in S0.itertuples():
        ok = [d for d in ivv_rep if d <= row.report_date and d >= row.report_date - pd.Timedelta(days=SM.BENCH_LAG)]
        if ok:
            fd = ivv[max(ok)][0]
            l1.append((fd - row.filing_date).days)
    l1 = np.array(l1)
    fdate = S0.set_index("accession")["filing_date"]
    hl = h0[(h0["linkBy"] == "CUSIP") & (h0["investment_country"] == "US")][["accession_number", "issuer_cusip", "tk", "currency_value"]].copy()
    hl["F"] = hl["accession_number"].map(fdate)
    hl = hl.merge(pairs.rename(columns={"cusip": "issuer_cusip"}), on=["issuer_cusip", "tk"], how="left")
    fut = hl["seen"] > hl["F"]
    tot_us = h0[h0["investment_country"] == "US"].groupby("accession_number")["currency_value"].sum()
    fut_share = (hl[fut].groupby("accession_number")["currency_value"].sum() / tot_us).reindex(tot_us.index).fillna(0)
    # ---------------- C1: same filings, L1 + L2 corrected
    bcache, c1, c1_missing = {}, {}, 0
    t = h0[["accession_number", "series_id", "issuer_cusip", "identifier_ticker", "currency_value", "investment_country"]]
    hp = link_pit(t, known, pairs, fdate)
    for acc, g in hp.groupby("accession_number"):
        r, F = S0.set_index("accession").at[acc, "report_date"], fdate[acc]
        bw = bench_for(r, F, ivv, close, bcache)
        if bw is None:
            c1_missing += 1
            continue
        c1[acc] = active_vec(weights_of(g)[3], bw)
    meta1 = S0.set_index("accession").loc[list(c1), ["series_id", "report_date", "filing_date"]]
    pickle.dump((meta1, c1), open(R / "C1.pkl", "wb"))
    # ---------------- C2: screens and clones re-run with L1, L2, L3 corrected
    memb = {pd.Timestamp(d): set(g.loc[g["inCommonUniverse"].astype(bool), "ticker"]) for d, g in feats.groupby("date")}
    mdates = np.array(sorted(memb), dtype="datetime64[ns]")
    rows, weights, actv = [], {}, {}
    for fname, tt in SM.read_candidates(x, set(meta.index[meta["series_id"] != SM.IVV])):
        h = link_pit(tt, known, pairs, meta["filing_date"])
        for acc, g in h.groupby("accession_number"):
            m = meta.loc[acc]
            r, F, nav = m["report_date"], m["filing_date"], float(m["net_assets"])
            us, eqv, lk, w = weights_of(g)
            k = mdates[mdates <= np.datetime64(r)]
            mem = memb[pd.Timestamp(k[-1])] if len(k) else set()
            bw = bench_for(r, F, ivv, close, bcache)
            sp = float(w[w.index.isin(mem)].sum())
            act = None
            if bw is not None and eqv > 0:
                av = active_vec(w, bw)
                act = 0.5 * float(av.abs().sum() + (1 - w.sum()))
            q = bool(nav >= SM.MIN_NAV and eqv / nav >= SM.MIN_EQ and us["issuer_cusip"].nunique() >= SM.MIN_N and sp >= SM.MIN_SP
                     and act is not None and act >= SM.MIN_AS)
            rows.append({"accession": acc, "series_id": m["series_id"], "report_date": r, "filing_date": F, "netAssets": nav, "qualifies": q,
                         "benchmarkFound": bw is not None})
            if q:
                weights[acc] = w
                actv[acc] = av
        print(fname, len(rows), len(weights), flush=True)
    F2 = pd.DataFrame(rows)
    drop_pit, _ = dedupe(F2, weights, pit=True)
    drop_size, late = dedupe(F2, weights, pit=False)
    F2["inSample"] = F2["qualifies"] & ~F2["accession"].isin(drop_pit)
    keep = F2.loc[F2["inSample"], "accession"]
    meta2 = F2.set_index("accession").loc[list(keep), ["series_id", "report_date", "filing_date"]]
    pickle.dump((meta2, {k: actv[k] for k in keep}), open(R / "C2.pkl", "wb"))
    F2.to_parquet(R / "C2-filings.parquet", index=False)
    s0, s2 = set(S0["accession"]), set(keep)
    out = {
        "L1_benchmarkPublishedAfterFund": {"inSampleFilings": int(len(l1)), "ivvPublishedLater": int((l1 > 0).sum()),
                                           "share": float((l1 > 0).mean()), "medianDaysLaterWhenLater": float(np.median(l1[l1 > 0])) if (l1 > 0).any() else 0.0,
                                           "maxDaysLater": int(l1.max())},
        "L2_cusipLinkLearnedLater": {"filingsWithAnyFutureLearnedLink": int((fut_share > 0).sum()), "filings": int(len(fut_share)),
                                     "meanUsEquityValueShare": float(fut_share.mean()), "p90": float(fut_share.quantile(.9)), "max": float(fut_share.max())},
        "L3_cloneKeptPublishedLater": {"sizeRuleDropsOnCorrectedQualifiers": len(drop_size), "ofWhichKeeperPublishedLater": int(late),
                                       "pitRuleDrops": len(drop_pit)},
        "C1": {"filings": int(len(c1)), "droppedNoPublishedBenchmark": int(c1_missing)},
        "C2": {"qualifying": int(F2["qualifies"].sum()), "inSample": int(F2["inSample"].sum()), "series": int(F2.loc[F2["inSample"], "series_id"].nunique()),
               "noPublishedBenchmark": int((~F2["benchmarkFound"]).sum())},
        "sampleOverlap": {"O": len(s0), "C2": len(s2), "both": len(s0 & s2), "onlyO": len(s0 - s2), "onlyC2": len(s2 - s0)},
    }
    (OUT / "us-audit.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
