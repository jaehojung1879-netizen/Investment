"""us-rank-independent-check-v1 — audit Codex's US top-K ranking/return outputs WITHOUT re-implementing them.

Inputs Codex is expected to publish (column names below; a file missing a column skips only the checks that need it):
  holdings  CSV/JSON rows: date (signal or holding date), ticker, rank, weight[, periodStart, periodEnd, totalReturn]   one row per held name
  weekly    CSV/JSON rows: week (period end), k, portfolioReturn, benchmarkReturn[, ticker contributions as contrib:<TICKER> columns]

Checks (each returns a plain dict; nothing here produces a ranking, a weight or a strategy return of its own):
  rank_weight_check    Codex top-K on a SPY holding date vs the SPY SEC snapshot (company level, share classes merged)
  return_check         a sample of Codex's dividend-inclusive name returns vs Yahoo adjusted closes (a different vendor path)
  concentration        how much of the portfolio-minus-benchmark result is carried by its top names and by any single year
  missing_week_bounds  whether the sign of the result can flip once the missing weeks are bounded at the worst / best observed week
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
SNAPSHOTS = HERE / "results" / "spy-reference-snapshots.json"


def _read(path):
    p = Path(path)
    if p.suffix == ".json":
        return pd.DataFrame(json.loads(p.read_text()))
    return pd.read_csv(p)


def norm(t):
    return None if t is None or (isinstance(t, float) and math.isnan(t)) else str(t).upper().replace("/", ".").replace("-", ".")


def company_of(snapshot):
    """ticker -> company key on this snapshot (GOOGL and GOOG share one key)."""
    out = {}
    for c in snapshot["top100"]:
        for t in c["tickers"]:
            if t:
                out[norm(t)] = c["issuerKey"]
    return out


def rank_weight_check(holdings, snapshots, ks=(5, 10, 100), max_gap_days=0):
    h = holdings.copy()
    h["date"] = pd.to_datetime(h["date"])
    out = []
    for s in snapshots:
        day = pd.Timestamp(s["holdingAsOf"])
        dates = h["date"].drop_duplicates()
        near = dates[(dates - day).abs() <= pd.Timedelta(days=max_gap_days)]
        if near.empty:
            out.append({"holdingAsOf": s["holdingAsOf"], "status": "NO_CODEX_DATE_WITHIN_%dD" % max_gap_days})
            continue
        d = near.iloc[(near - day).abs().argmin()]
        g = h[h["date"] == d].sort_values("rank")
        comp = company_of(s)
        ref = [c["issuerKey"] for c in s["top100"]]
        rec = {"holdingAsOf": s["holdingAsOf"], "codexDate": str(d.date()), "byK": {}}
        for k in ks:
            codex_keys, unmapped = [], []
            for t in g["ticker"]:
                key = comp.get(norm(t))
                if key is None:
                    unmapped.append(t)
                elif key not in codex_keys:
                    codex_keys.append(key)
                if len(codex_keys) >= k:
                    break
            ref_k = ref[:k]
            rec["byK"][str(k)] = {"overlap": len(set(codex_keys) & set(ref_k)), "k": k,
                                  "codexOnly": sorted(set(codex_keys) - set(ref_k)), "spyOnly": sorted(set(ref_k) - set(codex_keys)),
                                  "codexTickersNotOnSpyTop100": unmapped}
        if "weight" in g.columns:
            w = g.assign(key=g["ticker"].map(lambda t: comp.get(norm(t)))).dropna(subset=["key"]).groupby("key")["weight"].sum()
            spy = pd.Series({c["issuerKey"]: c["weight"] for c in s["top100"]})
            both = w.index.intersection(spy.index)
            if len(both):
                a, b = w[both] / w[both].sum(), spy[both] / spy[both].sum()
                rec["weightsWithinCommonNames"] = {"names": int(len(both)), "maxAbsDiff": float((a - b).abs().max()), "meanAbsDiff": float((a - b).abs().mean())}
        out.append(rec)
    return out


def yahoo_total_return(ticker, start, end, downloader=None):
    """Close-to-close total return from Yahoo adjusted closes (dividends and splits reinvested by the vendor)."""
    if downloader is None:
        import yfinance as yf
        downloader = lambda t, a, b: yf.download(t, start=a, end=b, auto_adjust=False, progress=False)  # noqa: E731
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    d = downloader(ticker.replace(".", "-"), str((s - pd.Timedelta(days=7)).date()), str((e + pd.Timedelta(days=2)).date()))
    if d is None or len(d) == 0:
        return None
    adj = d["Adj Close"]
    adj = adj.iloc[:, 0] if isinstance(adj, pd.DataFrame) else adj
    a, b = adj.loc[:s], adj.loc[:e]
    if a.empty or b.empty or a.index[-1] != s or b.index[-1] != e:
        return None                                    # never substitute a neighbouring session silently
    return float(b.iloc[-1] / a.iloc[-1] - 1)


def return_check(holdings, n=20, seed=7, tolerance=0.002, downloader=None):
    h = holdings.dropna(subset=["periodStart", "periodEnd", "totalReturn"])
    if h.empty:
        return {"status": "NO_RETURN_COLUMNS"}
    sample = h.sample(min(n, len(h)), random_state=seed)
    rows = []
    for _, r in sample.iterrows():
        y = yahoo_total_return(r["ticker"], r["periodStart"], r["periodEnd"], downloader)
        rows.append({"ticker": r["ticker"], "periodStart": str(r["periodStart"]), "periodEnd": str(r["periodEnd"]), "codex": float(r["totalReturn"]),
                     "yahoo": y, "absDiff": None if y is None else abs(float(r["totalReturn"]) - y)})
    ok = [x for x in rows if x["absDiff"] is not None]
    return {"sampled": len(rows), "compared": len(ok), "withinTolerance": sum(x["absDiff"] <= tolerance for x in ok), "tolerance": tolerance,
            "maxAbsDiff": max((x["absDiff"] for x in ok), default=None), "rows": rows}


def _ann_excess(weekly):
    r = (1 + weekly["portfolioReturn"]).prod() ** (52 / len(weekly)) - 1
    b = (1 + weekly["benchmarkReturn"]).prod() ** (52 / len(weekly)) - 1
    return r - b


def concentration(weekly, top=5):
    w = weekly.copy()
    w["week"] = pd.to_datetime(w["week"])
    out = {"weeks": int(len(w)), "annualisedExcess": _ann_excess(w)}
    contrib = [c for c in w.columns if c.startswith("contrib:")]
    if contrib:
        tot = w[contrib].sum().sort_values(ascending=False)
        out["topNames"] = []
        for c in tot.index[:top]:
            ww = w.copy()
            ww["portfolioReturn"] = ww["portfolioReturn"] - ww[c].fillna(0)       # the name's contribution removed, its weight left in cash-like zero
            out["topNames"].append({"ticker": c.split(":", 1)[1], "sumContribution": float(tot[c]), "annualisedExcessWithout": _ann_excess(ww)})
    out["leaveOneYearOut"] = {}
    for y in sorted(w["week"].dt.year.unique()):
        ww = w[w["week"].dt.year != y]
        out["leaveOneYearOut"][int(y)] = _ann_excess(ww) if len(ww) > 10 else None
    signs = [np.sign(v) for v in out["leaveOneYearOut"].values() if v is not None]
    out["yearThatFlipsSign"] = [y for y, v in out["leaveOneYearOut"].items() if v is not None and np.sign(v) != np.sign(out["annualisedExcess"])]
    out["allLeaveOneYearOutSameSign"] = len(set(signs)) <= 1
    return out


def missing_week_bounds(weekly, expected_weeks):
    """Fill every expected-but-missing week with (benchmark, benchmark), with the worst observed excess week and with the best one."""
    w = weekly.copy()
    w["week"] = pd.to_datetime(w["week"])
    have = set(w["week"])
    miss = [pd.Timestamp(x) for x in expected_weeks if pd.Timestamp(x) not in have]
    if not miss:
        return {"missingWeeks": 0}
    ex = w["portfolioReturn"] - w["benchmarkReturn"]
    worst, best = w.loc[ex.idxmin()], w.loc[ex.idxmax()]
    bench_mean = float(w["benchmarkReturn"].mean())
    out = {"missingWeeks": len(miss), "observedWeeks": int(len(w)), "observedAnnualisedExcess": _ann_excess(w)}
    for label, pr, br in (("NEUTRAL", bench_mean, bench_mean), ("WORST_OBSERVED_WEEK", worst["portfolioReturn"], worst["benchmarkReturn"]),
                          ("BEST_OBSERVED_WEEK", best["portfolioReturn"], best["benchmarkReturn"])):
        fill = pd.DataFrame({"week": miss, "portfolioReturn": pr, "benchmarkReturn": br})
        out[label] = _ann_excess(pd.concat([w[["week", "portfolioReturn", "benchmarkReturn"]], fill]).sort_values("week"))
    out["signFlipsWithinBounds"] = len({np.sign(out[k]) for k in ("NEUTRAL", "WORST_OBSERVED_WEEK", "BEST_OBSERVED_WEEK", "observedAnnualisedExcess")}) > 1
    return out


def run(holdings_path=None, weekly_path=None, expected_weeks=None):
    snaps = json.loads(SNAPSHOTS.read_text())["snapshots"]
    out = {"studyId": "us-rank-independent-check-v1", "artifact": "CODEX_OUTPUT_CROSS_CHECK"}
    if holdings_path:
        h = _read(holdings_path)
        out["rankWeight"] = rank_weight_check(h, snaps)
        out["returns"] = return_check(h) if {"periodStart", "periodEnd", "totalReturn"} <= set(h.columns) else {"status": "NO_RETURN_COLUMNS"}
    if weekly_path:
        w = _read(weekly_path)
        out["concentration"] = concentration(w)
        if expected_weeks is not None:
            out["missingWeeks"] = missing_week_bounds(w, expected_weeks)
    return out


def external_index_segments(levels, launch_date):
    """Official index levels (S&P 500 Top 10 total return, exported by a person from spglobal.com: this environment receives HTTP 403) split at the
    index LAUNCH date: values before it are S&P's back-test (hypothetical, computed after the fact), values from it on are live. Each segment's
    annualised return is reported separately and never chained into one figure. `levels`: DataFrame with `date` and `level` columns."""
    lv = levels.copy()
    lv["date"] = pd.to_datetime(lv["date"])
    lv = lv.sort_values("date").set_index("date")["level"].astype(float)
    launch = pd.Timestamp(launch_date)
    out = {"launchDate": str(launch.date())}
    for name, seg in (("BACKTESTED_BEFORE_LAUNCH", lv[lv.index < launch]), ("LIVE_FROM_LAUNCH", lv[lv.index >= launch])):
        if len(seg) < 2:
            out[name] = None
            continue
        yrs = (seg.index[-1] - seg.index[0]).days / 365.25
        out[name] = {"start": str(seg.index[0].date()), "end": str(seg.index[-1].date()), "totalReturn": float(seg.iloc[-1] / seg.iloc[0] - 1),
                     "annualised": float((seg.iloc[-1] / seg.iloc[0]) ** (1 / yrs) - 1) if yrs > 0 else None}
    return out
