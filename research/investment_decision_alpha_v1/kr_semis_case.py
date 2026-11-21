"""Korean semiconductor case (descriptive only; Phase D closed KR return testing on price/financial information).

    python -m research.investment_decision_alpha_v1.kr_semis_case --private <dir with data/>

For 005930 (Samsung Electronics) and 000660 (SK Hynix): quarterly operating income, revenue and capex rebuilt from DART
cumulative statements (earliest filing per period), the date each became public, and the share price at that date and
126 sessions later. Price peaks and troughs (moves of 30%+ between turning points) are listed beside the fundamental
turning points so the lead/lag can be read. No rule is fitted and nothing here is a trading signal.
"""
from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline import dart_derive as DD
from research.kr_us_earnings_expectations_v1 import analysis as AN
from research.kr_us_earnings_expectations_v1.events import KR_ORDER, quarterly_from_cumulative

HERE = Path(__file__).resolve().parent
NAMES = {"005930.KS": "삼성전자", "000660.KS": "SK하이닉스"}
ACCOUNTS = ("영업이익", "매출액", "유형자산의취득")


def quarters(private: Path, ticker: str) -> pd.DataFrame:
    recs = []
    for p in sorted((private / "data" / "raw" / "accounting").glob("dart-*.jsonl.gz")):
        for line in gzip.open(p, "rt"):
            r = json.loads(line)
            if r["ticker"] == ticker:
                recs.append(r)
    by = {}
    for r in sorted(recs, key=lambda r: str(r.get("availableFrom"))):
        by.setdefault((int(r["fiscalYear"]), str(r["reportCode"])), r)
    cols, avail = {}, {}
    for acc in ACCOUNTS:
        cum = {}
        for (y, code), r in by.items():
            if code in KR_ORDER:
                s = KR_ORDER.index(code) + 1
                cum[(y, s)] = DD.cumulative_amount(r, acc)
                avail[(y, s)] = r.get("availableFrom")
        cols[acc] = quarterly_from_cumulative(cum)
    keys = sorted(set().union(*[set(v) for v in cols.values()]))
    df = pd.DataFrame([{"fyear": k[0], "q": k[1], "available": avail.get(k), **{a: cols[a].get(k) for a in ACCOUNTS}} for k in keys])
    df["available"] = pd.to_datetime(df["available"])
    for a in ACCOUNTS:
        df[a] = pd.to_numeric(df[a], errors="coerce")
        df[a + "_ttm"] = df[a].abs().rolling(4).sum() if a == "유형자산의취득" else df[a].rolling(4).sum()
        df[a + "_yoy"] = df[a + "_ttm"] / df[a + "_ttm"].shift(4) - 1
    df["opMargin_ttm"] = df["영업이익_ttm"] / df["매출액_ttm"]
    return df


def turning_points(px: pd.Series, move=0.30):
    """Alternating peaks/troughs where the price moved at least `move` from the previous turning point."""
    pts, mode = [], None
    hi_i, hi = lo_i, lo = px.index[0], float(px.iloc[0])
    for d, v in px.items():
        v = float(v)
        if mode != "down" and v > hi:
            hi_i, hi = d, v
        if mode != "up" and v < lo:
            lo_i, lo = d, v
        if mode != "down" and v <= hi * (1 - move):
            pts.append(("PEAK", hi_i, hi))
            mode, lo_i, lo = "down", d, v
        elif mode != "up" and v >= lo * (1 + move):
            pts.append(("TROUGH", lo_i, lo))
            mode, hi_i, hi = "up", d, v
    return [{"type": a, "date": str(b.date()), "price": c} for a, b, c in pts]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--private", required=True)
    ap.add_argument("--out", default=str(HERE / "results"))
    a = ap.parse_args(argv)
    P = Path(a.private)
    mk = AN.KR(P)
    close = mk.close
    out = {"label": "DESCRIPTIVE_CASE_NOT_A_TEST", "names": {}}
    frames = []
    for t, nm in NAMES.items():
        q = quarters(P, t)
        px = close[t].dropna()
        sess = px.index
        rows = []
        for r in q.itertuples():
            if pd.isna(r.available):
                continue
            i = sess.searchsorted(r.available, side="right")
            if i >= len(sess):
                continue
            j = i + 126
            fwd = float(px.iloc[j] / px.iloc[i] - 1) if j < len(sess) else np.nan
            etf = close[mk.M.ETF]
            fe = float(etf.loc[sess[j]] / etf.loc[sess[i]] - 1) if j < len(sess) and sess[j] in etf.index else np.nan
            rows.append({"ticker": t, "name": nm, "fyear": r.fyear, "q": r.q, "available": str(r.available.date()),
                         "opIncomeTTM": r._asdict()["영업이익_ttm"], "opIncomeTTMyoy": r._asdict()["영업이익_yoy"],
                         "revenueTTMyoy": r._asdict()["매출액_yoy"], "capexTTMyoy": r._asdict()["유형자산의취득_yoy"],
                         "opMarginTTM": r.opMargin_ttm, "fwd126": fwd, "fwd126MinusEtf": fe if np.isnan(fe) else fwd - fe})
        f = pd.DataFrame(rows)
        frames.append(f)
        oi = f["opIncomeTTM"].to_numpy(float)
        peaks = [f["available"].iloc[i] for i in range(1, len(f) - 1) if np.isfinite(oi[i - 1:i + 2]).all() and oi[i] > oi[i - 1] and oi[i] >= oi[i + 1]]
        troughs = [f["available"].iloc[i] for i in range(1, len(f) - 1) if np.isfinite(oi[i - 1:i + 2]).all() and oi[i] < oi[i - 1] and oi[i] <= oi[i + 1]]
        # turning-point DATES only: prices and per-name returns stay outside git (repository data policy)
        tp = [{"type": x["type"], "date": x["date"]} for x in turning_points(px[px.index >= "2016-01-01"])]
        out["names"][t] = {"name": nm, "quarters": int(len(f)), "pricePeaksTroughs30pct": tp,
                           "opIncomeTTMpeaksByPublicationDate": peaks, "opIncomeTTMtroughsByPublicationDate": troughs}
    full = pd.concat(frames)
    full.to_csv(P / "kr-semis-case-quarters-with-returns.csv", index=False)
    full.drop(columns=["fwd126", "fwd126MinusEtf"]).to_csv(Path(a.out) / "kr-semis-case-quarters.csv", index=False)
    (Path(a.out) / "kr-semis-case.json").write_text(json.dumps(out, indent=1, ensure_ascii=False, default=str) + "\n")
    print(json.dumps(out, ensure_ascii=False, default=str)[:3000])


if __name__ == "__main__":
    main()
