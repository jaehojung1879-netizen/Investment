"""Quarterly earnings events with point-in-time dates, KR and US.

Values come from the existing PIT stores (US Finnhub financials-reported raw filings, KR DART fnlttSinglAcntAll records); the earliest
filing per (fiscal year, stage) is used, so a later restatement never replaces the number that was visible. Standalone quarters are
cumulative differences (Q2 = H1 - Q1, Q4 = FY - 9M), never annualised.

  US value = net income (finnhub_derive.FLOWS['netIncome'] chain).  KR value = 영업이익 (operating income), the headline figure of
  Korean provisional-earnings disclosures.
  SUE (seasonal random walk, Foster-Olsen-Shevlin / Bernard-Thomas):  (V_q - V_{q-4}) / sd(V_{q-k} - V_{q-k-4}, k=1..8), at least 4
  prior differences; undefined (None) when the history is shorter or the dispersion is zero.
  Dates: filingDate = the periodic filing's availableFrom (strict PIT, the date the number itself can be read from our source);
  announceDate = the earliest earnings release inside (period end, filing date]: US 8-K carrying Item 2.02 (acceptance time; after
  16:00 New York time counts from the next session), KR original (not [기재정정]) 영업(잠정)실적 fair disclosure (receipt date).
"""
from __future__ import annotations

import gzip
import json
import pickle
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline import dart_derive as DD
from pipeline import finnhub_derive as FD
from pipeline import finnhub_fundamentals as FF

US_ORDER = (FF.Q1, FF.Q2, FF.Q3, FF.FY)
KR_ORDER = ("11013", "11012", "11014", "11011")
KR_END = {"11013": "03-31", "11012": "06-30", "11014": "09-30", "11011": "12-31"}
MIN_HIST, MAX_HIST = 4, 8


def quarterly_from_cumulative(cum: dict[tuple[int, int], float]) -> dict[tuple[int, int], float]:
    """{(year, stage 1..4): cumulative} -> {(year, stage): standalone quarter}; a quarter needs its own and the previous stage."""
    out = {}
    for (y, s), v in cum.items():
        if v is None:
            continue
        if s == 1:
            out[(y, s)] = v
        elif (y, s - 1) in cum and cum[(y, s - 1)] is not None:
            out[(y, s)] = v - cum[(y, s - 1)]
    return out


def sue_series(q: dict[tuple[int, int], float]) -> dict[tuple[int, int], float]:
    keys = sorted(q)
    diffs = {k: q[k] - q[(k[0] - 1, k[1])] for k in keys if (k[0] - 1, k[1]) in q}
    out = {}
    for k in sorted(diffs):
        y, s = k
        prev = []
        yy, ss = y, s
        for _ in range(MAX_HIST):
            ss -= 1
            if ss == 0:
                yy, ss = yy - 1, 4
            if (yy, ss) in diffs:
                prev.append(diffs[(yy, ss)])
        if len(prev) >= MIN_HIST:
            sd = float(np.std(prev, ddof=1))
            if sd > 0:
                out[k] = diffs[k] / sd
    return out


def us_events(private: Path) -> pd.DataFrame:
    raw = pickle.load(open(private / "us" / "filings.pkl", "rb"))["raw"]
    sec, chain = FD.FLOWS["netIncome"]
    rows = []
    for t, recs in raw.items():
        by = FD.index_filings(recs)
        cum, meta = {}, {}
        for (y, stage), r in by.items():
            s = US_ORDER.index(stage) + 1
            cum[(y, s)] = FD.amount(r, sec, chain)
            meta[(y, s)] = r
        q = quarterly_from_cumulative(cum)
        sue = sue_series(q)
        for k, v in q.items():
            r = meta[k]
            rows.append({"ticker": t, "fyear": k[0], "stage": k[1], "periodEnd": r.get("periodEnd"), "value": v,
                         "sue": sue.get(k), "filingDate": r.get("availableFrom"), "cik": r.get("cik")})
    df = pd.DataFrame(rows)
    for c in ("periodEnd", "filingDate"):
        df[c] = pd.to_datetime(df[c])
    return df


def kr_events(private: Path) -> pd.DataFrame:
    recs = defaultdict(list)
    for p in sorted((private / "data" / "raw" / "accounting").glob("dart-*.jsonl.gz")):
        for line in gzip.open(p, "rt"):
            r = json.loads(line)
            recs[r["ticker"]].append(r)
    rows = []
    for t, rs in recs.items():
        by = {}
        for r in sorted(rs, key=lambda r: str(r.get("availableFrom"))):        # earliest filing per key wins
            by.setdefault((int(r["fiscalYear"]), str(r["reportCode"])), r)
        cum, meta = {}, {}
        for (y, code), r in by.items():
            if code not in KR_ORDER:
                continue
            s = KR_ORDER.index(code) + 1
            cum[(y, s)] = DD.cumulative_amount(r, "영업이익")
            meta[(y, s)] = r
        q = quarterly_from_cumulative(cum)
        sue = sue_series(q)
        for k, v in q.items():
            r = meta[k]
            rows.append({"ticker": t, "fyear": k[0], "stage": k[1], "periodEnd": f"{k[0]}-{KR_END[KR_ORDER[k[1] - 1]]}", "value": v,
                         "sue": sue.get(k), "filingDate": r.get("availableFrom"), "corpCode": r.get("corpCode"), "fsDiv": r.get("fsDiv")})
    df = pd.DataFrame(rows)
    for c in ("periodEnd", "filingDate"):
        df[c] = pd.to_datetime(df[c])
    return df


def attach_us_announcements(ev: pd.DataFrame, path: Path) -> pd.DataFrame:
    d = json.loads(path.read_text())["tickers"]
    ann = {}
    for t, v in d.items():
        ts = pd.to_datetime([r["acceptanceDateTime"] for r in v["rows"]], utc=True).tz_convert("America/New_York")
        ann[t] = sorted(ts)
    out = []
    for r in ev.itertuples():
        cand = [x for x in ann.get(r.ticker, []) if x.tz_localize(None).normalize() > r.periodEnd and x.tz_localize(None).normalize() <= r.filingDate]
        if cand:
            a = cand[0]
            eff = a.tz_localize(None).normalize() + (pd.Timedelta(days=1) if a.hour >= 16 else pd.Timedelta(0))
            out.append((a.tz_localize(None), eff))
        else:
            out.append((pd.NaT, pd.NaT))
    ev = ev.copy()
    ev["announceTime"] = [x[0] for x in out]
    ev["announceEffective"] = [x[1] for x in out]          # first calendar day whose session can react
    return ev


def attach_kr_announcements(ev: pd.DataFrame, path: Path) -> pd.DataFrame:
    d = json.loads(path.read_text())["tickers"]
    ann = {}
    for t, v in d.items():
        ok = [r for r in v["rows"] if not r["report_nm"].startswith("[") and "영업(잠정)실적" in r["report_nm"]]
        ann[t] = sorted(pd.Timestamp(r["rcept_dt"]) for r in ok)
    out = []
    for r in ev.itertuples():
        cand = [x for x in ann.get(r.ticker, []) if r.periodEnd < x <= r.filingDate]
        out.append(cand[0] if cand else pd.NaT)
    ev = ev.copy()
    ev["announceTime"] = out
    ev["announceEffective"] = out                          # receipt time unknown: the receipt day's session may or may not react
    return ev
