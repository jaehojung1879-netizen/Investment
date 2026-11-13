"""Relation, regime, data-audit and risk-forecast analyses for us-macro-cocktail-v1.

Every table labels whether its conditioning information was available at the
start of the period it describes (EX_ANTE) or only alongside it (CONCURRENT,
an ex-post explanation). The two are never pooled into one claim.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import cocktail as C

REL_ASSETS = ["SPY", "QQQ", "IEF", "TLT", "SHY", "GLD", "UUP", "BIL"]


# ----------------------------------------------------------------------------- helpers
def monthly_returns(p: C.Panel, start: str = "2007-06-29", end: str = "2026-10-30") -> pd.DataFrame:
    me = C.month_end_sessions(p.sessions)
    me = me[(me >= pd.Timestamp(start)) & (me <= pd.Timestamp(end))]
    return (p.tr.loc[me] / p.tr.loc[me].shift(1) - 1).dropna()


def _ols(y: np.ndarray, X: np.ndarray) -> tuple[np.ndarray, float]:
    X1 = np.column_stack([np.ones(len(X)), X])
    beta, *_ = np.linalg.lstsq(X1, y, rcond=None)
    resid = y - X1 @ beta
    r2 = 1 - resid @ resid / ((y - y.mean()) @ (y - y.mean()))
    return beta, float(r2)


def _cond_table(ret: pd.DataFrame, mask: pd.Series, cols: list[str]) -> dict:
    sub = ret[mask.reindex(ret.index).fillna(False).astype(bool)]
    return {"months": int(len(sub)), **{f"{c}MeanPct": float(sub[c].mean() * 100) for c in cols},
            **{f"{c}UpShare": float((sub[c] > 0).mean()) for c in cols}}


# ----------------------------------------------------------------------------- data audit
def data_audit(p: C.Panel) -> dict:
    sess = C.xnys_sessions("1993-01-01", "2026-11-09")
    out = {"assets": {a: C.audit_asset(a, sess) for a in C.ASSETS},
           "crossVendor": C.cross_vendor_checks(),
           "repoSnapshot": C.compare_with_repo_snapshot(p.tr), "fred": {}}
    window = p.sessions[(p.sessions >= pd.Timestamp("2008-01-01")) & (p.sessions <= pd.Timestamp("2026-10-30"))]
    for s in C.FRED_STATE + ["SP500", "NASDAQ100"]:
        raw = C.load_fred(s)
        obs = raw.index
        pos = obs.searchsorted(window, side="left") - 1  # strictly earlier observation
        age = [(d - obs[k]).days if k >= 0 else None for d, k in zip(window, pos)]
        stale = sum(1 for a in age if a is None or a > 5)
        out["fred"][s] = {"first": str(obs[0].date()), "last": str(obs[-1].date()), "observations": int(len(raw)),
                          "sessions2008to2026": int(len(window)), "sessionsWhoseLaggedValueIsOlderThan5Days": int(stale)}
    out["fredVintagePolicy"] = {
        "classification": "MARKET_OBSERVED_VINTAGE_UNVERIFIED",
        "detail": ("DGS10/DGS2/DGS3MO/DTB3 (H.15), T10YIE, DFII10, VIXCLS and DEXKOUS (H.10) are market observations. "
                   "ALFRED was unreachable from this environment (empty replies on alfredgraph.csv and series pages), so per-series "
                   "vintage histories were NOT verified here; the repository's 2026-09-04 ALFRED measurement found several daily "
                   "panel series that ALFRED does not carry at all. Mitigation: a one-session publication lag on every FRED value. "
                   "DTWEXBGS is excluded from all signals: its current definition was first published in 2019 with revisable weights."),
    }
    out["tradingHours"] = {
        "etfs": "NYSE Arca/Nasdaq-listed ETFs, regular session 09:30-16:00 ET; closes used for valuation and execution",
        "usdkrw": ("DEXKOUS is the Federal Reserve H.10 noon New York buying rate. A US close (16:00 ET) falls after that day's noon print "
                   "and after the Seoul session of the same calendar date, so KRW NAV uses the next print dated after the session. "
                   "A KRW investor's actual conversion happens in Seoul hours (KST = ET+13/14); the next-print rule is an observable, "
                   "no-look-ahead proxy, not a quote the investor could trade at."),
    }
    out["holdingCosts"] = {"basis": "expense ratios are inside the traded price and are not charged again",
                           "publishedExpenseRatiosPct": {"SPY": 0.0945, "QQQ": 0.20, "IEF": 0.15, "TLT": 0.15, "SHY": 0.15,
                                                          "BIL": 0.1356, "GLD": 0.40, "UUP": 0.78},
                           "expenseRatioSource": "issuer fact sheets as commonly published; quoted for context only, not used in any computation"}
    return out


# ----------------------------------------------------------------------------- regime splits on strategy paths
def regime_splits(navs: dict, p: C.Panel, state: pd.DataFrame, sched: C.Schedule) -> dict:
    m = pd.DataFrame({k: C.month_end_series(v) for k, v in navs.items()}).pct_change().dropna()
    me = m.index
    prev = C.month_end_sessions(p.sessions)
    prev = pd.Series(prev, index=prev).shift(1).reindex(me)
    y10 = p.fred["DGS10"]
    rising = pd.Series((y10.reindex(me).values - y10.reindex(prev.values).values) > 0, index=me)
    spy_down = m["ASSET_SPY"] < 0
    uup_up = m["ASSET_UUP"] > 0
    peak = p.tr["SPY"].cummax()
    dd_state = pd.Series(((p.tr["SPY"] / peak - 1).reindex(prev.values).values <= -0.10), index=me)
    labels = {"risingTenYearConcurrent": rising, "spyDownMonthConcurrent": spy_down,
              "uupUpMonthConcurrent": uup_up, "spyDrawdown10ExAnte": dd_state}
    out = {"labelTiming": {"risingTenYearConcurrent": "CONCURRENT", "spyDownMonthConcurrent": "CONCURRENT",
                           "uupUpMonthConcurrent": "CONCURRENT", "spyDrawdown10ExAnte": "EX_ANTE"}}
    cols = [c for c in m.columns if not c.startswith("ASSET_")]
    for name, mask in labels.items():
        for flag in (True, False):
            sub = m[mask == flag]
            key = f"{name}={flag}"
            out[key] = {"months": int(len(sub)),
                        "meanMonthlyPct": {c: float(sub[c].mean() * 100) for c in cols},
                        "shareBeatingS4": {c: float((sub[c] > sub["S4_BALANCED"]).mean()) for c in cols if c != "S4_BALANCED"}}
    return out


def calendar_years(navs: dict) -> dict:
    m = pd.DataFrame({k: C.month_end_series(v) for k, v in navs.items() if not k.startswith("ASSET_") or k in ("ASSET_SPY", "ASSET_QQQ", "ASSET_IEF", "ASSET_GLD", "ASSET_UUP", "ASSET_BIL", "ASSET_TLT")})
    y = m.groupby(m.index.year).tail(1)
    first = m.iloc[[0]]
    y = pd.concat([first, y])
    yr = y.pct_change().dropna()
    return {str(d.year): {c: float(yr.at[d, c] * 100) for c in yr.columns} for d in yr.index}


# ----------------------------------------------------------------------------- relations Q1-Q4
def _runs(sign: pd.Series, min_len: int = 63) -> list[dict]:
    s = sign.dropna()
    runs = []
    start = s.index[0]
    cur = s.iloc[0]
    prev_d = start
    for d, v in s.items():
        if v != cur:
            runs.append([start, prev_d, cur])
            start, cur = d, v
        prev_d = d
    runs.append([start, prev_d, cur])
    merged: list[list] = []
    for r in runs:
        length = len(s.loc[r[0]:r[1]])
        if merged and (length < min_len or merged[-1][2] == r[2]):
            merged[-1][1] = r[1]
        else:
            merged.append(list(r))
    out = []
    for a, b, v in merged:
        out.append({"start": str(a.date()), "end": str(b.date()), "sign": "POSITIVE" if v else "NEGATIVE",
                    "sessions": int(len(s.loc[a:b]))})
    return out


def relations(p: C.Panel, state: pd.DataFrame) -> dict:
    r = p.ret
    mr = monthly_returns(p)
    me = mr.index
    allme = C.month_end_sessions(p.sessions)
    prev = pd.Series(allme, index=allme).shift(1).reindex(me)
    st_prev = state.reindex(prev.values)
    st_prev.index = me
    f = p.fred
    d_y10 = pd.Series(f["DGS10"].reindex(me).values - f["DGS10"].reindex(prev.values).values, index=me)
    d_real = pd.Series(f["DFII10"].reindex(me).values - f["DFII10"].reindex(prev.values).values, index=me)
    d_be = pd.Series(f["T10YIE"].reindex(me).values - f["T10YIE"].reindex(prev.values).values, index=me)
    curve = f["DGS10"] - f["DGS3MO"]
    d_curve = pd.Series(curve.reindex(me).values - curve.reindex(prev.values).values, index=me)
    out: dict = {"sampleMonths": int(len(mr)), "firstMonth": str(me[0].date()), "lastMonth": str(me[-1].date())}

    # yearly daily-return correlations
    yearly = {}
    for y, g in r.loc["2007-06-01":"2026-10-30"].groupby(r.loc["2007-06-01":"2026-10-30"].index.year):
        yearly[str(y)] = {f"SPY_{b}": float(g["SPY"].corr(g[b])) for b in ("IEF", "TLT", "GLD", "UUP", "QQQ")}
        yearly[str(y)]["IEF_GLD"] = float(g["IEF"].corr(g["GLD"]))
    out["yearlyDailyCorrelations"] = yearly

    # Q1 equity up and dollar up together
    both = (mr["SPY"] > 0) & (mr["UUP"] > 0)
    q1 = {"unconditionalShare": float(both.mean()), "months": int(len(mr)),
          "spyUpShare": float((mr["SPY"] > 0).mean()), "uupUpShare": float((mr["UUP"] > 0).mean()),
          "independenceBenchmark": float((mr["SPY"] > 0).mean() * (mr["UUP"] > 0).mean()), "conditional": {}}
    conds = {
        "EX_ANTE corrSpyUup126>0": st_prev["corrSpyUup126"] > 0,
        "EX_ANTE corrSpyUup126<=0": st_prev["corrSpyUup126"] <= 0,
        "EX_ANTE vix>=20 (conventional level)": st_prev["vix"] >= 20,
        "EX_ANTE vix<20": st_prev["vix"] < 20,
        "EX_ANTE dY10_63>0": st_prev["dY10_63"] > 0,
        "EX_ANTE dY10_63<=0": st_prev["dY10_63"] <= 0,
        "EX_ANTE spyEx12>0": st_prev["spyEx12"] > 0,
        "EX_ANTE spyEx12<=0": st_prev["spyEx12"] <= 0,
        "CONCURRENT d10y>0": d_y10 > 0,
        "CONCURRENT d10y<=0": d_y10 <= 0,
        "CONCURRENT dRealYield>0": d_real > 0,
        "CONCURRENT dRealYield<=0": d_real <= 0,
    }
    for k, mask in conds.items():
        sub = both[mask.fillna(False)]
        q1["conditional"][k] = {"months": int(len(sub)), "shareSpyUpAndUupUp": float(sub.mean()) if len(sub) else None,
                                "meanUupPctWhenSpyUp": float(mr.loc[mask.fillna(False) & (mr["SPY"] > 0), "UUP"].mean() * 100)}
    out["Q1_equityUpDollarUp"] = q1

    # Q2 stock-bond correlation regimes and their concurrent / ex-ante correlates
    corr126 = r["SPY"].rolling(126).corr(r["IEF"])
    corr126 = corr126.loc["2008-01-01":"2026-10-30"]
    out["Q2_stockBond"] = {
        "regimesSpyIef126": _runs(corr126 > 0),
        "regimesSpyTlt126": _runs((r["SPY"].rolling(126).corr(r["TLT"]).loc["2008-01-01":"2026-10-30"]) > 0),
    }
    # concurrent explanation: month-end 126d corr vs same-date yield level, breakeven level, real yield level
    mc = corr126.reindex(me).dropna()
    Xc = pd.DataFrame({"y10": f["DGS10"].reindex(mc.index), "breakeven": f["T10YIE"].reindex(mc.index),
                       "realYield": f["DFII10"].reindex(mc.index)}).dropna()
    beta, r2 = _ols(mc.reindex(Xc.index).values, Xc.values)
    out["Q2_stockBond"]["concurrentLevelsRegression"] = {
        "timing": "CONCURRENT (ex-post explanation; overlapping 126-session windows, no inference)",
        "months": int(len(Xc)), "r2": r2, "coef": dict(zip(["const", "y10", "breakeven", "realYield"], beta.tolist()))}
    for k, mask in {"y10>=3 at month end": f["DGS10"].reindex(mc.index) >= 3,
                    "y10<3 at month end": f["DGS10"].reindex(mc.index) < 3,
                    "breakeven>=2.5": f["T10YIE"].reindex(mc.index) >= 2.5,
                    "breakeven<2.5": f["T10YIE"].reindex(mc.index) < 2.5}.items():
        out["Q2_stockBond"].setdefault("concurrentLevelSplits", {})[k] = {
            "months": int(mask.sum()), "meanCorr126": float(mc[mask].mean()), "sharePositive": float((mc[mask] > 0).mean())}
    out["Q2_stockBond"]["levelThresholdNote"] = "3% and 2.5% are round conventional levels fixed while writing this table; they are descriptive splits, not fitted breakpoints"

    # Q3 gold when equities fall
    down = mr["SPY"] < 0
    q3 = {"spyDownMonths": int(down.sum()), "gldMeanPctInSpyDown": float(mr.loc[down, "GLD"].mean() * 100),
          "gldUpShareInSpyDown": float((mr.loc[down, "GLD"] > 0).mean()),
          "gldMeanPctInSpyUp": float(mr.loc[~down, "GLD"].mean() * 100), "conditional": {}}
    for k, mask in {"CONCURRENT dRealYield>0": d_real > 0, "CONCURRENT dRealYield<=0": d_real <= 0,
                    "CONCURRENT UUP up": mr["UUP"] > 0, "CONCURRENT UUP down": mr["UUP"] <= 0,
                    "EX_ANTE uup6>0": st_prev["uup6"] > 0, "EX_ANTE uup6<=0": st_prev["uup6"] <= 0,
                    "EX_ANTE corrSpyGld126>0": st_prev["corrSpyGld126"] > 0,
                    "EX_ANTE corrSpyGld126<=0": st_prev["corrSpyGld126"] <= 0}.items():
        mk = down & mask.fillna(False)
        q3["conditional"][k] = {"months": int(mk.sum()), "gldMeanPct": float(mr.loc[mk, "GLD"].mean() * 100) if mk.sum() else None,
                                "gldUpShare": float((mr.loc[mk, "GLD"] > 0).mean()) if mk.sum() else None}
    worst = mr["SPY"].nsmallest(10)
    q3["worst10SpyMonths"] = [{"month": str(d.date())[:7], "SPY": float(mr.at[d, "SPY"] * 100), "GLD": float(mr.at[d, "GLD"] * 100),
                               "IEF": float(mr.at[d, "IEF"] * 100), "TLT": float(mr.at[d, "TLT"] * 100), "UUP": float(mr.at[d, "UUP"] * 100)}
                              for d in worst.index]
    out["Q3_goldInEquityDeclines"] = q3

    # Q4 rates: concurrent explanation vs ex-ante prediction
    q4 = {"concurrent": {}, "exAnteWalkForward": {}}
    Xcon = pd.DataFrame({"d10y": d_y10, "dCurve10y3m": d_curve, "dBreakeven": d_be}).dropna()
    for a in ["SPY", "QQQ", "IEF", "TLT", "GLD", "UUP"]:
        y = mr[a].reindex(Xcon.index)
        beta, r2 = _ols(y.values, Xcon.values)
        q4["concurrent"][a] = {"timing": "CONCURRENT", "months": int(len(y)), "r2": r2,
                               "coefPctPerPctPoint": dict(zip(["const", "d10y", "dCurve10y3m", "dBreakeven"], (beta * 100).tolist()))}
    lag_cols = ["y10", "dY10_63", "curve10y3m", "dBreakeven63"]
    Xa = st_prev[lag_cols]
    for a in ["SPY", "QQQ", "IEF", "TLT", "GLD", "UUP"]:
        ex = (mr[a] - mr["BIL"]).values
        preds, means, truth, dates = [], [], [], []
        for i in range(len(me)):
            tr_idx = [j for j in range(i) if Xa.iloc[j].notna().all()]
            if len(tr_idx) < C.MIN_TRAIN or Xa.iloc[i].isna().any():
                continue
            Xtr = Xa.iloc[tr_idx].values
            mu, sd = Xtr.mean(0), Xtr.std(0)
            sd[sd == 0] = 1
            beta, _ = _ols(ex[tr_idx], (Xtr - mu) / sd)
            preds.append(beta[0] + ((Xa.iloc[i].values - mu) / sd) @ beta[1:])
            means.append(ex[tr_idx].mean())
            truth.append(ex[i])
            dates.append(me[i])
        preds, means, truth = map(np.array, (preds, means, truth))
        oos = 1 - ((truth - preds) ** 2).sum() / ((truth - means) ** 2).sum()
        ok = Xa.notna().all(axis=1).values
        _, ins = _ols(ex[ok], Xa.values[ok])
        dlt = (truth - means) ** 2 - (truth - preds) ** 2
        mu_d, t_d = C.newey_west_t(dlt, 1)
        q4["exAnteWalkForward"][a] = {"timing": "EX_ANTE", "features": lag_cols, "firstForecast": str(dates[0].date()),
                                      "months": int(len(truth)), "oosR2VsExpandingMean": float(oos),
                                      "nwTStatSquaredErrorGain": t_d, "inSampleR2SameFeatures": ins}
    out["Q4_rates"] = q4

    # SPY-GLD and SPY-UUP correlation regimes
    out["regimesSpyGld126"] = _runs(r["SPY"].rolling(126).corr(r["GLD"]).loc["2008-01-01":"2026-10-30"] > 0)
    out["regimesSpyUup126"] = _runs(r["SPY"].rolling(126).corr(r["UUP"]).loc["2008-01-01":"2026-10-30"] > 0)
    return out


# ----------------------------------------------------------------------------- risk forecasting
def _target(r: pd.DataFrame, w4: np.ndarray, kind: str, a: int, b: int) -> float:
    seg = r.iloc[a:b]
    if kind == "corrSpyIef":
        return float(np.arctanh(np.clip(seg["SPY"].corr(seg["IEF"]), -0.999, 0.999)))
    if kind == "corrSpyGld":
        return float(np.arctanh(np.clip(seg["SPY"].corr(seg["GLD"]), -0.999, 0.999)))
    if kind == "corrSpyUup":
        return float(np.arctanh(np.clip(seg["SPY"].corr(seg["UUP"]), -0.999, 0.999)))
    if kind == "logVolSpy":
        return float(np.log(seg["SPY"].std() * np.sqrt(252)))
    if kind == "logVolS4":
        port = seg[["SPY", "IEF", "GLD", "BIL"]].values @ w4
        return float(np.log(port.std(ddof=1) * np.sqrt(252)))
    raise KeyError(kind)


def risk_forecast(p: C.Panel, state: pd.DataFrame) -> dict:
    from sklearn.linear_model import Ridge
    r = p.ret
    sess = p.sessions
    sched = C.schedule(p, "2008-05-30", "2026-10-30")
    dpos = sess.get_indexer(sched.decisions)
    epos = sess.get_indexer(sched.executions)
    w4 = np.array([C.S4["SPY"], C.S4["IEF"], C.S4["GLD"], C.S4["BIL"]])
    X = state.loc[sched.decisions, C.STATE_COLS].values
    last = sess.get_loc(pd.Timestamp("2026-10-30"))
    out = {"design": "walk-forward ridge(alpha=1) on [naive trailing estimate + 15 state variables]; correlations on Fisher-z, vols in logs",
           "results": {}}
    for h in (21, 63, 126):
        for kind in ("corrSpyIef", "corrSpyGld", "corrSpyUup", "logVolSpy", "logVolS4"):
            naive = np.array([_target(r, w4, kind, d - h + 1, d + 1) for d in dpos])
            tgt = np.array([_target(r, w4, kind, e + 1, e + h + 1) if e + h <= last else np.nan for e in epos])
            end_pos = epos + h
            feats = np.column_stack([naive, X])
            pred, nv, mean, truth, dates = [], [], [], [], []
            for i in range(len(dpos)):
                ok = (end_pos[:i] <= dpos[i]) & np.isfinite(tgt[:i]) & np.isfinite(feats[:i]).all(1)
                if ok.sum() < C.MIN_TRAIN or not np.isfinite(tgt[i]) or not np.isfinite(feats[i]).all():
                    continue
                Ftr, ytr = feats[:i][ok], tgt[:i][ok]
                mu, sd = Ftr.mean(0), Ftr.std(0)
                sd[sd == 0] = 1
                m = Ridge(alpha=1.0).fit((Ftr - mu) / sd, ytr)
                pred.append(float(m.predict(((feats[i] - mu) / sd)[None, :])[0]))
                nv.append(naive[i])
                mean.append(ytr.mean())
                truth.append(tgt[i])
                dates.append(sched.decisions[i])
            pred, nv, mean, truth = map(np.array, (pred, nv, mean, truth))
            dates = pd.DatetimeIndex(dates)
            lag = h // 21 + 1

            def summary(sel):
                t, pm, pn, pmean = truth[sel], pred[sel], nv[sel], mean[sel]
                sse_m, sse_n, sse_mean = ((t - pm) ** 2).sum(), ((t - pn) ** 2).sum(), ((t - pmean) ** 2).sum()
                mu_d, t_d = C.newey_west_t((t - pn) ** 2 - (t - pm) ** 2, lag)
                return {"forecasts": int(sel.sum()), "first": str(dates[sel][0].date()), "last": str(dates[sel][-1].date()),
                        "oosR2ModelVsNaive": float(1 - sse_m / sse_n), "oosR2ModelVsExpandingMean": float(1 - sse_m / sse_mean),
                        "oosR2NaiveVsExpandingMean": float(1 - sse_n / sse_mean), "nwTStatModelBeatsNaive": t_d}
            allsel = np.ones(len(truth), bool)
            rec = {"timing": "EX_ANTE", "all": summary(allsel), "from2016": summary(dates >= pd.Timestamp("2016-01-01"))}
            okall = np.isfinite(tgt) & np.isfinite(feats).all(1)
            _, ins = _ols(tgt[okall], feats[okall])
            rec["inSampleR2SameFeaturesExPost"] = ins
            out["results"][f"{kind}_h{h}"] = rec
            if kind == "corrSpyIef" and h == 126:
                s_true = truth > 0
                rec["signTest"] = {"naiveSignHitRate": float(((nv > 0) == s_true).mean()),
                                   "modelSignHitRate": float(((pred > 0) == s_true).mean()),
                                   "majorityClassBaseRate": float(max(s_true.mean(), 1 - s_true.mean())),
                                   "note": "overlapping 126-session windows on monthly decisions; hit rates are descriptive"}
    return out
