"""us-macro-cocktail-v1 errata v1 — corrections found by the #333 integration audit.

The original results/ files are left byte-identical. This module recomputes only
what #333 showed to be wrong or unlabelled, from the same frozen raw snapshot:

E1  KRW translation. The original code applied the FIRST DEXKOUS observation
    dated after each US session and called it "no look-ahead". An observation
    date is not an availability time: H.10 publishes the previous week's daily
    rates on Monday 16:15 ET (next business day if Monday is a federal holiday),
    so the original rule used a rate published up to a week later. FX is not a
    strategy input, so USD results are unaffected. Two honest definitions are
    published instead:
      ACCOUNTING_SAME_DAY  — ex-post valuation at the same-day noon observation
                             (a translation of a historical path, never decision
                             information);
      AVAILABLE_AT_SESSION — the last observation whose H.10 release was public
                             by that session's US close (16:00 ET). H.10 weekly
                             publication was suspended 2006-05-22..2009-01; that
                             span is flagged AVAILABILITY_UNVERIFIED.
E2  Average-weight twin. The last primary target (decision 2026-10-30) executes
    on 2026-11-02, after the evaluation end; the original twin averaged 131
    targets. The twin is rebuilt from the 130 targets executed in the window.
E3  Units. CAGR gaps and arithmetic-mean gaps are reported separately and named.
E4  Risk-matched comparison (#333: "동일 위험 대조는 없음"). Each dynamic rule is
    compared with its average-weight twin de-levered with BIL to the SAME
    realised monthly volatility (ex-post matching: a diagnostic of whether a
    drawdown difference is more than lower risk, never a tradable rule).
E5  Independent price verification. A second vendor was attempted and was not
    reachable; an FRED-yield plausibility check of IEF/SHY/BIL is reported as a
    PLAUSIBILITY check, not as price verification.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
sys.path.insert(0, str(STUDY))
import cocktail as C  # noqa: E402

OUT = HERE / "results"
END = "2026-10-30"
WINDOWS = {"primary": "2015-12-31", "extended": "2008-05-30"}
H10_SUSPENDED = (pd.Timestamp("2006-05-22"), pd.Timestamp("2009-01-31"))


# ----------------------------------------------------------------------------- E1
def h10_release(obs_date: pd.Timestamp, holidays: set) -> pd.Timestamp:
    """Release time (ET, naive) of a daily H.10 observation: Monday after its week, 16:15 ET."""
    monday = obs_date + pd.Timedelta(days=7 - obs_date.weekday())
    while monday in holidays or monday.weekday() >= 5:
        monday += pd.Timedelta(days=1)
    return monday + pd.Timedelta(hours=16, minutes=15)


def fx_available(sessions: pd.DatetimeIndex, fx: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Last observation whose H.10 release was public by each session's 16:00 ET close.

    Release time is monotone in the observation date (Monday after its week), so the
    released set at any instant is a prefix of the date-sorted series.
    """
    from pandas.tseries.holiday import USFederalHolidayCalendar
    hol = set(USFederalHolidayCalendar().holidays(start="1980-01-01", end="2027-12-31"))
    release = pd.DatetimeIndex([h10_release(d, hol) for d in fx.index])
    if not release.is_monotonic_increasing:
        raise RuntimeError("H10_RELEASE_NOT_MONOTONE")
    pos = release.searchsorted(sessions + pd.Timedelta(hours=16), side="right") - 1
    vals = [fx.iloc[k] if k >= 0 else np.nan for k in pos]
    obs = [fx.index[k] if k >= 0 else pd.NaT for k in pos]
    return pd.Series(vals, index=sessions), pd.Series(obs, index=sessions)


# ----------------------------------------------------------------------------- helpers
def window_targets(p, state, wf, first):
    sched = C.schedule(p, first, END)
    pos = {d: i for i, d in enumerate(wf.dec)}
    return sched, {name: {d: C.target_weights(name, pos[d], p, state, wf)[0] for d in sched.decisions}
                   for name in C.STRATEGIES}


def executed_targets(sched, targets, end):
    """Targets whose execution session falls on or before the evaluation end."""
    return {d: w for (d, w), e in zip(targets.items(), sched.executions) if e <= pd.Timestamp(end)}


def avg_weights(targets: dict) -> dict:
    w = pd.DataFrame(list(targets.values())).fillna(0.0).mean()
    return {k: float(v) for k, v in w.items() if v > 1e-12}


def scaled_static(weights: dict, scale: float) -> dict:
    risky = {k: v * scale for k, v in weights.items() if k != "BIL"}
    bil = 1.0 - sum(risky.values())
    out = dict(risky)
    if bil > 1e-12:
        out["BIL"] = bil
    return out


def monthly_vol(nav: pd.Series) -> float:
    return float(C.month_end_series(nav).pct_change().dropna().std(ddof=1) * np.sqrt(12))


def crisis_dd(nav: pd.Series, start: str, end: str) -> float | None:
    """Worst drawdown inside [start, end] against the running peak since inception."""
    dd = nav / nav.cummax() - 1
    seg = dd.loc[start:end]
    return float(seg.min() * 100) if len(seg) else None


CRISES = {"GFC_2008-09_2009-03": ("2008-09-01", "2009-03-31"), "COVID_2020-02_2020-04": ("2020-02-01", "2020-04-30"),
          "RATES_2022": ("2022-01-01", "2022-12-31")}


# ----------------------------------------------------------------------------- main
def run() -> dict:
    ident = C.verify_inputs()
    p = C.build_panel()
    state = C.state_frame(p)
    full = C.schedule(p, WINDOWS["extended"], END)
    wf = C.WalkForward(p, state, full.decisions, full.executions)
    fx = C.load_fred("DEXKOUS")
    fx_avail, fx_avail_obs = fx_available(p.sessions, fx)
    original = json.loads((STUDY / "results" / "result.json").read_text())
    out = {"errataId": "us-macro-cocktail-v1-errata-v1", "auditSource": "PR #333 research_integration_audit_20261111 (HEAD 61d0d3f6)",
           "originalResultsUnchanged": True, "inputIdentity": ident, "windows": {}}
    for label, first in WINDOWS.items():
        sched, targets = window_targets(p, state, wf, first)
        navs = {n: C.backtest(targets[n], sched, p, END)["nav"] for n in C.STRATEGIES}
        bil = C.backtest({d: {"BIL": 1.0} for d in sched.decisions}, sched, p, END)["nav"]
        spy = C.backtest({d: {"SPY": 1.0} for d in sched.decisions}, sched, p, END)["nav"]
        idx = navs["S1_SPY"].index
        avail_flag = bool(((idx >= H10_SUSPENDED[0]) & (idx <= H10_SUSPENDED[1])).any())
        win = {"firstDecision": str(sched.decisions[0].date()), "end": END,
               "targetsInWindow": len(sched.decisions),
               "targetsExecutedInWindow": len(executed_targets(sched, targets["S1_SPY"], END)),
               "krw": {}, "twin": {}, "riskMatched": {}}
        # E1
        for n in C.STRATEGIES:
            nav = navs[n]
            same = C.metrics(nav * p.fx_same.reindex(idx) / (nav.iloc[0] * p.fx_same.reindex(idx).iloc[0]), bil, spy)
            av = fx_avail.reindex(idx)
            avail = C.metrics(nav * av / (nav.iloc[0] * av.iloc[0]), bil, spy) if av.notna().all() else None
            orig = original["windows"][label]["strategies"][n]["KRW_unhedged"]
            win["krw"][n] = {
                "ACCOUNTING_SAME_DAY": {k: same[k] for k in ("cagrPct", "volPct", "maxDrawdownPct")},
                "AVAILABLE_AT_SESSION": ({k: avail[k] for k in ("cagrPct", "volPct", "maxDrawdownPct")} if avail else None),
                "AVAILABLE_AT_SESSION_status": "AVAILABILITY_UNVERIFIED_H10_WEEKLY_SUSPENDED_2006_2009" if avail_flag else "H10_RELEASE_RULE_APPLIED",
                "ORIGINAL_NEXT_OBSERVATION_WITHDRAWN": {k: orig[k] for k in ("cagrPct", "maxDrawdownPct")},
                "usdCagrPct": original["windows"][label]["strategies"][n]["USD"]["cagrPct"],
            }
        last = idx[-1]
        win["fxAtEnd"] = {"session": str(last.date()), "sameDayObservation": float(p.fx_same[last]),
                          "originalNextObservation": float(p.fx_next[last]),
                          "availableAtSessionClose": float(fx_avail[last]),
                          "availableObservationDate": str(fx_avail_obs[last].date())}
        # E2/E3/E4
        for n in C.STRATEGIES:
            if not n.startswith(("D", "S6", "S7")):
                continue
            ex = executed_targets(sched, targets[n], END)
            tw = avg_weights(ex)
            twin = C.backtest({d: tw for d in sched.decisions}, sched, p, END)["nav"]
            m_s, m_t = C.metrics(navs[n], bil, spy), C.metrics(twin, bil, spy)
            pair = C.paired(navs[n], twin)
            win["twin"][n] = {"targetsAveraged": len(ex), "twinWeights": {k: round(v, 6) for k, v in sorted(tw.items())},
                              "strategyCagrPct": m_s["cagrPct"], "twinCagrPct": m_t["cagrPct"],
                              "cagrGapPct": round(m_s["cagrPct"] - m_t["cagrPct"], 3),
                              "arithmeticMeanGapPctPerYear": pair["meanAnnualDiffPct"],
                              "arithmeticMeanGapCi95": pair["ci95AnnualPct"],
                              "strategyMddPct": m_s["maxDrawdownPct"], "twinMddPct": m_t["maxDrawdownPct"]}
            # E4: de-lever the twin to the strategy's realised monthly vol
            target_vol = monthly_vol(navs[n])
            lo, hi = 0.0, 1.0
            for _ in range(40):
                mid = (lo + hi) / 2
                v = monthly_vol(C.backtest({d: scaled_static(tw, mid) for d in sched.decisions}, sched, p, END)["nav"])
                lo, hi = (mid, hi) if v < target_vol else (lo, mid)
            scale = (lo + hi) / 2
            rm = C.backtest({d: scaled_static(tw, scale) for d in sched.decisions}, sched, p, END)["nav"]
            m_r = C.metrics(rm, bil, spy)
            pr = C.paired(navs[n], rm)
            win["riskMatched"][n] = {
                "method": "average-weight twin de-levered into BIL to the strategy's realised monthly vol (EX_POST diagnostic)",
                "twinRiskyScale": round(scale, 4), "strategyVolPct": m_s["volPct"], "matchedVolPct": m_r["volPct"],
                "strategy": {k: m_s[k] for k in ("cagrPct", "maxDrawdownPct", "calmar", "sharpeOverBil")},
                "riskMatchedStatic": {k: m_r[k] for k in ("cagrPct", "maxDrawdownPct", "calmar", "sharpeOverBil")},
                "cagrGapPct": round(m_s["cagrPct"] - m_r["cagrPct"], 3),
                "arithmeticMeanGapPctPerYear": pr["meanAnnualDiffPct"], "arithmeticMeanGapCi95": pr["ci95AnnualPct"],
                "mddGapPct": round(m_s["maxDrawdownPct"] - m_r["maxDrawdownPct"], 3),
                "crisisDrawdownPct": {k: {"strategy": crisis_dd(navs[n], a, b), "riskMatchedStatic": crisis_dd(rm, a, b),
                                          "S4": crisis_dd(navs["S4_BALANCED"], a, b), "SPY": crisis_dd(spy, a, b)}
                                      for k, (a, b) in CRISES.items() if pd.Timestamp(a) >= idx[0]},
            }
        out["windows"][label] = win
    out["independentPriceVerification"] = plausibility(p)
    return out


# ----------------------------------------------------------------------------- E5
def plausibility(p: C.Panel) -> dict:
    me = C.month_end_sessions(p.sessions)
    me = me[(me >= pd.Timestamp("2008-01-31")) & (me <= pd.Timestamp(END))]
    tr = p.tr.loc[me]
    r = tr.pct_change().dropna()
    raw = {s: C.load_fred(s) for s in ("DGS10", "DGS2", "DTB3")}
    yld = pd.DataFrame({s: v.reindex(v.index.union(me)).ffill().reindex(me) for s, v in raw.items()})
    out = {"secondVendorAttempts": [
        {"vendor": "Nasdaq quote historical API", "result": "HTTP 200 with totalRecords 0 for IEF/SPY across 2016-2025 date ranges"},
        {"vendor": "Stooq CSV", "result": "JavaScript proof-of-work challenge page instead of data"}],
        "priceVerificationStatus": "INDEPENDENT_VENDOR_UNREACHABLE_SINGLE_SOURCE_YAHOO",
        "plausibility": {}}
    specs = {"IEF": ("DGS10", 7.5), "SHY": ("DGS2", 1.9)}
    for etf, (series, dur) in specs.items():
        y = yld[series] / 100
        implied = (y.shift(1) / 12 - dur * y.diff()).dropna()
        a = r[etf].reindex(implied.index)
        out["plausibility"][etf] = {"basis": f"carry {series}/12 minus duration {dur} x monthly change (approximation, different construct)",
                                    "months": int(len(a)), "correlation": round(float(np.corrcoef(a, implied)[0, 1]), 4),
                                    "meanAbsDiffPctPerMonth": round(float((a - implied).abs().mean() * 100), 4)}
    bil_imp = (yld["DTB3"].shift(1) / 100 / 12).dropna()
    a = r["BIL"].reindex(bil_imp.index)
    out["plausibility"]["BIL"] = {"basis": "DTB3/12 accrual", "months": int(len(a)),
                                  "annualisedDiffPct": round(float((a.mean() - bil_imp.mean()) * 1200), 4),
                                  "correlation": round(float(np.corrcoef(a, bil_imp)[0, 1]), 4)}
    out["notCovered"] = ["TLT", "GLD", "UUP"]
    out["meaning"] = "Consistency with an independent construct; it cannot verify a vendor's daily closes or distributions."
    return out


def _clean(o):
    if isinstance(o, float):
        return None if not np.isfinite(o) else round(o, 6)
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, np.floating):
        return _clean(float(o))
    if isinstance(o, np.bool_):
        return bool(o)
    return o


if __name__ == "__main__":
    res = run()
    OUT.mkdir(exist_ok=True)
    (OUT / "errata-v1.json").write_text(json.dumps(_clean(res), indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    w = res["windows"]
    print(json.dumps({k: {"fxAtEnd": v["fxAtEnd"], "targets": [v["targetsInWindow"], v["targetsExecutedInWindow"]]} for k, v in w.items()}, indent=1))
