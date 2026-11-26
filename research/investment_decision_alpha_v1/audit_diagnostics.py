"""Audit diagnostics for PR #355 (no new rule, no new outcome claim; reads the same inputs as S1/S3).

    python -m research.investment_decision_alpha_v1.audit_diagnostics --private <#353-corrected dir>

1. PIT check of the 943 #353 share-count corrections: was each SEC filing accepted before the decision-day close?
2. IC-4 decomposition: on dates the BOOM exclusion changed the BASE book, compare the removed names with the names
   that replaced them (price-score percentile, forward 126-session return minus SPY). This says WHY the exclusion lost.
3. S3 exposure checks: momentum percentile of trimmed names vs the other held names at the trim date, and the value
   moved by the BOOM trim vs the random trims; number of independent 252-session blocks after 2023.
Outputs aggregates only (no per-name returns) to results/audit-diagnostics.json.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from research.investment_decision_alpha_v1 import s1_industry_cycle as S1
from research.investment_decision_alpha_v1 import s3_trim as S3
from research.kr_us_public_buys_v1 import wat_sources
from research.us_selection_value_v1 import evaluate as EV
from research.us_selection_value_v1 import restored_compare as RCMP

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def pit_corrections():
    c = pd.read_csv(ROOT / "research/kr_us_public_buys_v1/results/WAT/corrected-caps.csv", parse_dates=["date"])
    acc = pd.to_datetime(c["acceptedET"], utc=True)

    def close_utc(d):
        t = pd.Timestamp(wat_sources.decision_close(d))
        return t.tz_convert("UTC") if t.tzinfo else t.tz_localize("UTC")
    close = pd.Series([close_utc(d) for d in c["date"]], index=c.index)
    ok = acc < close
    lag = (c["date"] - pd.to_datetime(c["shareAsOf"])).dt.days
    return {"rows": int(len(c)), "acceptedBeforeDecisionClose": int(ok.sum()), "violations": int((~ok).sum()),
            "shareAsOfToDecisionDays": {"median": float(lag.median()), "max": int(lag.max())},
            "ratioCorrectedOverOriginal": {"below0.01": int((c.correctedMarketCap / c.previousMarketCap < .01).sum()),
                                           "above100": int((c.correctedMarketCap / c.previousMarketCap > 100).sum())},
            "byTicker": c.groupby("ticker").size().to_dict()}


def ic4_decomposition(close, secs, st):
    rows = []
    idx = close.index
    for d, x in secs.items():
        bm = S1.boom_members(st, d)
        if bm is None:
            continue
        base = EV.book(x, "PRICE_CONFIRMED", "TOP5")
        y = x.copy()
        y.loc[y.index.isin(list(bm)) & y["PRICE_CONFIRMED"].notna(), "PRICE_CONFIRMED"] = np.nan
        excl = EV.book(y, "PRICE_CONFIRMED", "TOP5")
        removed, added = sorted(set(base) - set(excl)), sorted(set(excl) - set(base))
        if not removed:
            continue
        pos = idx.get_loc(d)
        if pos + 1 + 126 >= len(idx):
            continue
        e, z = idx[pos + 1], idx[pos + 1 + 126]
        r = close.loc[z] / close.loc[e] - 1
        spy = float(r["SPY"])
        pc = x["PRICE_CONFIRMED"].rank(pct=True)
        rr, ra = r.reindex(removed), r.reindex(added)
        if rr.isna().any() or ra.isna().any():
            continue
        rows.append({"date": d, "nRemoved": len(removed), "removedPct": float(pc.reindex(removed).mean()), "addedPct": float(pc.reindex(added).mean()),
                     "removedMinusSpy": float(rr.mean()) - spy, "addedMinusSpy": float(ra.mean()) - spy,
                     "removedMom": float(x["momentum252"].reindex(removed).mean()), "addedMom": float(x["momentum252"].reindex(added).mean()),
                     "removedSectors": ",".join(sorted(x.loc[removed, "sector"])), "year": d.year})
    df = pd.DataFrame(rows)
    out = {"datesChanged": int(len(df)), "meanNamesSwapped": float(df["nRemoved"].mean()),
           "priceScorePercentile": {"removed": float(df["removedPct"].mean()), "added": float(df["addedPct"].mean())},
           "momentum252": {"removed": float(df["removedMom"].mean()), "added": float(df["addedMom"].mean())},
           "forward126MinusSpy": {"removed": float(df["removedMinusSpy"].mean()), "added": float(df["addedMinusSpy"].mean())},
           "removedSectorShare": pd.Series(",".join(df["removedSectors"]).split(",")).value_counts(normalize=True).round(3).head(6).to_dict(),
           "byPeriod": {k: {"removedMinusSpy": float(g["removedMinusSpy"].mean()), "addedMinusSpy": float(g["addedMinusSpy"].mean()), "dates": int(len(g))}
                        for k, g in (("BEFORE_2023", df[df.date < "2023-01-01"]), ("FROM_2023", df[df.date >= "2023-01-01"]))}}
    return out


def s3_checks(close, secs, st, feats):
    st_dates = np.array(sorted(st), dtype="datetime64[ns]")
    boom = {d: {t for m in s.loc[s["BOOM"], "members"] for t in m} for d, s in st.items()}
    mom = feats.pivot_table(index="date", columns="ticker", values="momentum252")
    idx = close.index
    trimmed_pct, other_pct = [], []
    for d in sorted(secs):
        if d not in st:
            continue
        names = EV.book(secs[d], "PRICE_CONFIRMED", "TOP5")
        pos = idx.get_loc(d) + 1
        if not names or pos + S3.H >= len(idx):
            continue
        done = set()
        for t in range(S3.STEP, S3.H, S3.STEP):
            day = idx[pos + t]
            s_day = st_dates[np.searchsorted(st_dates, np.datetime64(day), side="right") - 1]
            hit = [nm for nm in names if nm in boom[pd.Timestamp(s_day)] and nm not in done]
            if not hit:
                continue
            done |= set(hit)
            mrow = mom.loc[:day].iloc[-1]
            pct = mrow.rank(pct=True)
            trimmed_pct += [float(pct.get(h, np.nan)) for h in hit]
            other_pct += [float(pct.get(o, np.nan)) for o in names if o not in hit]
    s3 = json.loads((HERE / "results" / "s3-trim.json").read_text())
    return {"momentumPercentileAtTrim": {"trimmed": float(np.nanmean(trimmed_pct)), "otherHeld": float(np.nanmean(other_pct)),
                                         "nTrimmed": len(trimmed_pct)},
            "independentBlocks": {k: {"all": s3[k]["all"]["independentBlocks"], "from2023": s3[k]["FROM_2023"].get("independentBlocks"),
                                      "from2023n": s3[k]["FROM_2023"].get("n")} for k in ("trimMinusHold", "trimMinusRandom")}}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--private", required=True)
    a = ap.parse_args(argv)
    P = Path(a.private)
    out = {"label": "AUDIT_DIAGNOSTIC_NOT_A_NEW_CLAIM", "pitCorrections": pit_corrections()}
    print("pit", {k: v for k, v in out["pitCorrections"].items() if k != "byTicker"}, flush=True)
    close, feats, _, _ = EV.load(P / "us")
    feats["date"] = pd.to_datetime(feats["date"])
    st = S1.states(feats, S1.sic_map(HERE / "inputs" / "us-sic.csv"))
    secs = RCMP.sections_of(feats)
    out["ic4Decomposition"] = ic4_decomposition(close, secs, st)
    print("ic4", out["ic4Decomposition"], flush=True)
    out["s3Checks"] = s3_checks(close, secs, st, feats)
    print("s3", out["s3Checks"], flush=True)
    (HERE / "results" / "audit-diagnostics.json").write_text(json.dumps(out, indent=1, sort_keys=True, default=str) + "\n")


if __name__ == "__main__":
    main()
