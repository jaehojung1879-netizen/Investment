"""adaptive-cocktail-v1 runner: sleeves, fixed and learned cocktails, controls, Q1 predictability, attribution, diagnostics.

    python research/adaptive_cocktail_v1/run.py --scratch <dir>

<dir>/dataset.pkl is the ml-strategy-tournament-v1 prepared dataset (PIT matrix + labels + closes); <dir>/macro_panel.pkl and
<dir>/vix_fx.pkl are the replay-v16 macro, vix and fx components (see load_sources.py). Results go to research/adaptive_cocktail_v1/results/.
"""
from __future__ import annotations

import argparse
import json
import math
import pickle
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))
import cocktail as C  # noqa: E402

EVAL_START = pd.Timestamp(C.CONFIG["evaluation"]["cocktailEvaluationStart"][:10])
POST_HOC_INDUSTRIES = ("CAPITAL_GOODS_DEFENSE", "ELECTRONICS_ELECTRICAL")


def r6(x, n=6):
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return None
    return round(float(x), n)


def load(scratch):
    s = Path(scratch)
    blob = pickle.loads((s / "dataset.pkl").read_bytes())
    df = blob["df"].copy()
    closes, vols, sessions = blob["closes"].copy(), blob["volumes"].copy(), blob["sessions"]
    corrected = json.loads((C.ROOT / "docs/audits/kr-alpha-atlas-phase-c-integrity/corrected-inputs.json").read_text())
    fixed = 0
    for q in corrected["finalSessionQuotes"]:
        d, t = pd.Timestamp(q["date"]), q["ticker"]
        if t in closes.columns and d in closes.index:
            closes.at[d, t] = float(q["Close"])
            fixed += 1
    macro = pd.read_pickle(s / "macro_panel.pkl")
    vf = pd.read_pickle(s / "vix_fx.pkl")
    bok = json.loads((C.ROOT / "data/bok-policy-rates.json").read_text())["events"]
    ev = pd.Series({pd.Timestamp(e["date"]): float(e["annualRatePct"]) for e in bok}).sort_index()
    rate = ev.reindex(ev.index.union(sessions)).ffill().reindex(sessions)
    rf = rate / 100 / 252
    rows = pickle.loads((s / "matrix.pkl").read_bytes())["matrix"].rows[["date", "ticker", "b08Confirmed"]].copy()
    rows["date"] = pd.to_datetime(rows["date"])
    df = df.merge(rows, on=["date", "ticker"], how="left", validate="one_to_one")
    df["_q"] = C.quality_mask(df).to_numpy()
    return df, closes, vols, sessions, macro, vf["vix"], vf["fx"], rf, {"finalSessionQuotesApplied": fixed, "identity": blob["identity"]["sha256"],
                                                                         "matrixDigest": blob["matrixDigest"]}


def decision_dates(df, phase=0):
    """Every 4th weekly signal date from the first 2014 date (phase 0 = the frozen primary). Phases 1-3 shift the same cycle by 1-3 weeks."""
    weekly = sorted(pd.Timestamp(d) for d in df["date"].unique() if pd.Timestamp(d).year >= 2014)
    return weekly[phase::4]


def nxt(sessions, d):
    i = sessions.searchsorted(d, side="right")
    return sessions[i] if i < len(sessions) else None


def build_books(df, dates, exclude=(), xgb=None):
    by = {d: g for d, g in df.groupby("date")}
    books = {k: {} for k in C.CHOICE + (["SX_XGB_SENSITIVITY"] if xgb is not None else [])}
    withheld_hits = {k: 0 for k in books}
    for d in dates:
        g = by[d]
        for k in books:
            if k == "SX_XGB_SENSITIVITY":
                w, _, would = C.sleeve_book(k, g, exclude, score=pd.Series(xgb[g.index], index=g.index))
            else:
                w, _, would = C.sleeve_book(k, g, exclude)
            books[k][d] = w
            withheld_hits[k] += bool(would)
    return books, withheld_hits


def schedule_of(per_date_weights, sessions):
    return {nxt(sessions, d): w for d, w in per_date_weights.items() if nxt(sessions, d) is not None}


def sleeve_navs(px, books, sessions, start, end):
    out = {}
    for k, b in books.items():
        out[k] = C.simulate(px, schedule_of(b, sessions), start, end)["nav"]
    return out


def forward_rel(navs, sessions, dates, h):
    """rel_k(d) = sleeve k over S0 from the session after d to h sessions later; exit session date."""
    pos = {s: i for i, s in enumerate(sessions)}
    rows = {}
    for d in dates:
        e = nxt(sessions, d)
        if e is None:
            continue
        ie = pos[e]
        ix = ie + h
        if ix >= len(sessions):
            rows[d] = {"exit": None}
            continue
        x = sessions[ix]
        rec = {"exit": x}
        s0 = navs["S0_ETF"]
        for k, nv in navs.items():
            if e in nv.index and x in nv.index:
                rec[k] = float(nv.loc[x] / nv.loc[e] - s0.loc[x] / s0.loc[e])
        rows[d] = rec
    return rows


def trailing_rel(navs, d, h):
    out = {}
    s0 = navs["S0_ETF"].loc[:d]
    for k, nv in navs.items():
        v = nv.loc[:d]
        if len(v) > h:
            out[k] = float(v.iloc[-1] / v.iloc[-1 - h] - s0.iloc[-1] / s0.iloc[-1 - h])
    return out


def features(states, navs, d, k, cols):
    row = states.loc[:d].iloc[-1]
    x = [row[c] for c in cols]
    if k is not None:
        x += [trailing_rel(navs, d, 63).get(k, np.nan), trailing_rel(navs, d, 126).get(k, np.nan)]
    return np.array(x, float)


def learned_policy(kind, states, navs, dates, labels, cols):
    import lightgbm as lgb
    out, diag = {}, {}
    feat_cache = {(d, k): features(states, navs, d, k, cols) for d in dates for k in C.RISKY}
    for d in dates:
        if d < EVAL_START:
            continue
        train = [x for x in dates if x < d and labels[x].get("exit") is not None and labels[x]["exit"] < d]
        if len(train) < 36:
            out[d] = {"S0_ETF": 1.0}
            diag[d] = {"reason": "INSUFFICIENT_MATURED_HISTORY", "n": len(train)}
            continue
        mu, se = {}, {}
        for k in C.RISKY:
            rows = [x for x in train if k in labels[x]]
            X = np.array([feat_cache[(x, k)] for x in rows])
            y = np.array([labels[x][k] for x in rows])
            m = X.mean(axis=0, where=np.isfinite(X)) if len(X) else None
            m = np.where(np.isfinite(m), m, 0.0)
            X = np.where(np.isfinite(X), X, m)
            sd = X.std(axis=0)
            sd[sd == 0] = 1.0
            Z = (X - m) / sd
            xn = feat_cache[(d, k)]
            xn = np.where(np.isfinite(xn), xn, m)
            zn = (xn - m) / sd
            p, s = C.ridge_fit_predict(Z, y, zn)
            if kind == "B2_LGBM_ALL_STATES":
                model = lgb.LGBMRegressor(n_estimators=50, max_depth=2, num_leaves=4, learning_rate=0.05, min_child_samples=10, subsample=0.8,
                                          subsample_freq=1, random_state=7, n_jobs=1, verbose=-1).fit(Z, y)
                p = float(model.predict(zn.reshape(1, -1))[0])
            mu[k], se[k] = p, s
        w, edges = C.learned_weights(mu, se, C.round_trip_hurdle(d))
        out[d] = w
        diag[d] = {"mu": mu, "se": se, "edges": edges, "n": len(train)}
    return out, diag


def fixed_policies(states, navs, dates):
    a1, a2, mom = {}, {}, {}
    for d in dates:
        if d < EVAL_START:
            continue
        row = states.loc[:d].iloc[-1]
        rebound = row["MKT_TREND_252"] < 0 and row["MKT_TREND_63"] > 0
        hot = row["VOL63_PCTL_EXPANDING"] > 0.80
        a1[d] = {"S0_ETF": 1.0} if (rebound or hot) else {"S1_INDUSTRY_MOMENTUM": 1.0}
        inv = {}
        for k in C.CHOICE:
            r = navs[k].loc[:d].pct_change().dropna().tail(63)
            inv[k] = 1 / r.std() if len(r) == 63 and r.std() > 0 else 0.0
        tot = sum(inv.values())
        a2[d] = {k: v / tot for k, v in inv.items()}
        tr = {k: navs[k].loc[:d] for k in C.CHOICE}
        best = max(C.CHOICE, key=lambda k: tr[k].iloc[-1] / tr[k].iloc[-127] if len(tr[k]) > 127 else -1)
        mom[d] = {best: 1.0}
    return a1, a2, mom


def apply_band(weights_by_date, band=0.10):
    out, prev = {}, None
    for d in sorted(weights_by_date):
        w = weights_by_date[d]
        if prev is not None:
            keys = set(w) | set(prev)
            if 0.5 * sum(abs(w.get(k, 0) - prev.get(k, 0)) for k in keys) <= band:
                w = prev
        out[d] = w
        prev = w
    return out


def policy_books(sleeve_weights, books):
    return {d: C.combine({k: books[k][d] for k in w}, w) for d, w in sleeve_weights.items()}


def decompose(dyn_w, static_w, sleeve_daily, dyn_nav, static_nav, bench_nav, dyn_cost, static_cost):
    days = dyn_nav.index
    dates = sorted(dyn_w)
    wd = pd.DataFrame(index=days, columns=C.CHOICE, dtype=float)
    for i, d in enumerate(dates):
        nd = days[days > d]
        if not len(nd):
            continue
        end = dates[i + 1] if i + 1 < len(dates) else days[-1] + pd.Timedelta(days=1)
        span = nd[nd <= end] if i + 1 < len(dates) else nd
        for k in C.CHOICE:
            wd.loc[span, k] = dyn_w[d].get(k, 0.0) - static_w.get(k, 0.0)
    wd = wd.shift(1).fillna(0.0)          # weights decided at d earn returns from the day after execution
    rs = pd.DataFrame({k: sleeve_daily[k].reindex(days) for k in C.CHOICE}).fillna(0.0)
    timing = (wd * rs).sum(axis=1)
    diff = dyn_nav.pct_change().fillna(0) - static_nav.pct_change().fillna(0)
    rb = bench_nav.reindex(days).pct_change().fillna(0)
    s1x = (sleeve_daily["S1_INDUSTRY_MOMENTUM"] - sleeve_daily["S0_ETF"]).reindex(days).fillna(0)
    X = np.column_stack([np.ones(len(days)), rb.to_numpy(), s1x.to_numpy()])
    b = np.linalg.lstsq(X, diff.to_numpy(), rcond=None)[0]
    yrs = (len(days) - 1) / 252
    g = lambda nav: (nav.iloc[-1] / nav.iloc[0]) ** (1 / yrs) - 1  # noqa: E731
    arith = diff.mean() * 252
    return {"grossCagrGap": r6(g(dyn_nav) - g(static_nav)), "arithmeticMeanDailyGapAnnualised": r6(arith),
            "compoundingTerm": r6(g(dyn_nav) - g(static_nav) - arith),
            "sleeveTimingEffectAnnualised": r6(timing.mean() * 252),
            "marketBetaOfDifference": r6(b[1], 4), "marketExposureContributionAnnualised": r6(b[1] * rb.mean() * 252),
            "industryMomentumBetaOfDifference": r6(b[2], 4), "industryExposureContributionAnnualised": r6(b[2] * s1x.mean() * 252),
            "regressionInterceptAnnualised": r6(b[0] * 252), "stockSelectionEffect": 0.0,
            "costDifferencePerYear": r6((dyn_cost - static_cost) / yrs),
            "note": "timing = sum((w_dyn - w_static) . sleeve daily returns) with target weights held between decisions; the rest of the gap is drift, netting of overlapping names and costs. Stock selection is identical by construction (same fixed sleeves)."}


def run_all(df, closes, vols, sessions, macro, vix, fx, rf, xgb=None, exclude=(), cost_mult=1.0, label="PRIMARY", phase=0):
    px = C.Prices(closes, vols, sessions, rf)
    dates = decision_dates(df, phase)
    mdf = df.groupby("date")[["H09_marketBreadth", "H05_crossIndustryDispersion", "H10_marketConcentrationTop2", "H07_leadershipPersistence",
                              "I01_kospiTrendVolState"]].first().reset_index()
    states = C.state_panel(sessions, closes[C.ETF], macro, vix, fx, mdf)
    books, withheld_hits = build_books(df, dates, exclude, xgb)
    start_hist = nxt(sessions, dates[0])
    end = closes[C.ETF].last_valid_index()
    navs = sleeve_navs(px, books, sessions, start_hist, end)
    labels = {h: forward_rel({k: navs[k] for k in C.CHOICE}, sessions, dates, h) for h in (21, 63, 126)}
    eval_dates = [d for d in dates if d >= EVAL_START]
    w = {}
    w["S0_ETF"] = {d: {"S0_ETF": 1.0} for d in eval_dates}
    for k in C.RISKY:
        w[k] = {d: {k: 1.0} for d in eval_dates}
    w["STATIC_EW4"] = {d: {k: 0.25 for k in C.CHOICE} for d in eval_dates}
    w["STATIC_50_ETF_50_S1"] = {d: {"S0_ETF": 0.5, "S1_INDUSTRY_MOMENTUM": 0.5} for d in eval_dates}
    a1, a2, mom = fixed_policies(states, navs, dates)
    w["A1_MOMENTUM_CRASH_GUARD"] = apply_band(a1)
    w["A2_INVERSE_VOL_RISK_BUDGET"] = apply_band(a2)
    w["SLEEVE_MOMENTUM_SWITCH"] = mom
    diags = {}
    for kind, cols in (("B1_RIDGE_ALL_STATES", C.ALL_STATES), ("B2_LGBM_ALL_STATES", C.ALL_STATES), ("B3_RIDGE_KR_ONLY", C.KR_STATES)):
        raw, diags[kind] = learned_policy(kind, states, navs, dates, labels[63], cols)
        w[kind] = apply_band(raw)
    sched = {name: schedule_of(policy_books(ws, books), sessions) for name, ws in w.items()}
    sched["TREND_200_CASH"] = {nxt(sessions, d): ({C.ETF: 1.0} if states.loc[:d].iloc[-1]["MA200_ABOVE"] == 1 else {C.CASH: 1.0}) for d in eval_dates}
    mdf_i = mdf.set_index("date")["I01_kospiTrendVolState"]
    sched["S4_RISK_MANAGED_ETF"] = {nxt(sessions, d): {C.ETF: float(mdf_i.loc[d]), C.CASH: 1 - float(mdf_i.loc[d])} for d in eval_dates}
    if xgb is not None:
        sched["SX_XGB_SENSITIVITY"] = schedule_of({d: books["SX_XGB_SENSITIVITY"][d] for d in eval_dates}, sessions)
    start = nxt(sessions, eval_dates[0])
    bench_nav = pd.Series(px.etf, index=sessions).loc[start:end]
    bench_nav = bench_nav / bench_nav.iloc[0]
    sims = {name: C.simulate(px, s, start, end, cost_mult=cost_mult, record=(label == "PRIMARY")) for name, s in sched.items()}
    sims_last = {name: C.simulate(px, s, start, end, terminal_mode="LAST", cost_mult=cost_mult) for name, s in sched.items()} if label == "PRIMARY" else {}
    return {"px": px, "dates": dates, "evalDates": eval_dates, "states": states, "books": books, "withheldHits": withheld_hits, "navs": navs,
            "labels": labels, "weights": w, "diags": diags, "sims": sims, "simsLast": sims_last, "bench": bench_nav, "start": start, "end": end}


def q1(states, labels, dates):
    rows, pvals = [], []
    pairs = {"S1-S0": ("S1_INDUSTRY_MOMENTUM", None), "S2-S0": ("S2_VALUE_CONFIRMED", None), "S3-S0": ("S3_FOUR_FACTOR", None),
             "S1-S3": ("S1_INDUSTRY_MOMENTUM", "S3_FOUR_FACTOR")}
    st = pd.DataFrame([states.loc[:d].iloc[-1] for d in dates], index=dates)[C.ALL_STATES]
    # expanding standardisation (past-only mean and sd) so the regressor is itself PIT
    z = (st - st.expanding(12).mean().shift(1)) / st.expanding(12).std().shift(1)
    for h in (21, 63, 126):
        for pname, (a, b) in pairs.items():
            y = np.array([labels[h][d].get(a, np.nan) - (labels[h][d].get(b, 0.0) if b else 0.0) if labels[h][d].get("exit") is not None else np.nan
                          for d in dates])
            for v in C.ALL_STATES:
                res = C.newey_west_slope(z[v].to_numpy(), y, max(1, h // 20))
                if res is None:
                    continue
                rows.append({"horizon": h, "pair": pname, "state": v, **{k: r6(x, 5) for k, x in res.items()}})
                pvals.append(res["p"])
    adj = C.by_adjust(pvals)
    for r, a in zip(rows, adj):
        r["byAdjustedP"] = r6(a, 5)
    return rows


def oos_r2(diags, labels, dates):
    out = {}
    for k in C.RISKY:
        pred, hist, real = [], [], []
        for d in dates:
            dg = diags.get(d, {})
            if "mu" not in dg or labels[d].get("exit") is None or k not in labels[d]:
                continue
            train = [x for x in dates if x < d and labels[x].get("exit") is not None and labels[x]["exit"] < d and k in labels[x]]
            pred.append(dg["mu"][k])
            hist.append(np.mean([labels[x][k] for x in train]))
            real.append(labels[d][k])
        pred, hist, real = map(np.array, (pred, hist, real))
        if len(real) > 5:
            out[k] = {"n": int(len(real)), "oosR2VsExpandingMean": r6(1 - ((real - pred) ** 2).sum() / ((real - hist) ** 2).sum(), 4),
                      "signHitRate": r6(np.mean(np.sign(pred) == np.sign(real)), 3)}
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--scratch", required=True)
    a = ap.parse_args(argv)
    t0 = time.time()
    df, closes, vols, sessions, macro, vix, fx, rf, ident = load(a.scratch)
    xgbp = Path(a.scratch) / "preds" / "XGB_CI_RANK_h1.npz"
    xgb = np.load(xgbp)["scores"].astype(float) if xgbp.exists() else None
    R = run_all(df, closes, vols, sessions, macro, vix, fx, rf, xgb=xgb)
    rfs = rf
    bench = R["bench"]
    res = {"studyId": C.CONFIG["studyId"], "evidenceClass": C.CONFIG["evidenceClass"], "inputs": ident,
           "window": {"start": str(R["start"].date()), "end": str(R["end"].date()), "decisions": len(R["evalDates"]),
                      "sleeveHistoryStart": str(R["navs"]["S0_ETF"].index[0].date())},
           "withheldWouldHavePickedRebalances": R["withheldHits"]}
    perf = {}
    for name, s in R["sims"].items():
        m = C.metrics(s["nav"], bench, rfs)
        perf[name] = {k: r6(v) for k, v in m.items()} | {"costPerYear": r6(s["costs"] / m["years"]), "turnoverPerYear": r6(s["turnover"] / m["years"]),
                                                          "terminalHits": len(s["terminalHits"]),
                                                          "cagrTerminalAtLastClose": r6(C.metrics(R["simsLast"][name]["nav"], bench, rfs)["cagr"]),
                                                          "yearly": {y: {k: r6(v) for k, v in d.items()} for y, d in C.yearly(s["nav"], bench).items()}}
    res["performance"] = perf
    dyn = ["A1_MOMENTUM_CRASH_GUARD", "A2_INVERSE_VOL_RISK_BUDGET", "B1_RIDGE_ALL_STATES", "B2_LGBM_ALL_STATES", "B3_RIDGE_KR_ONLY", "SLEEVE_MOMENTUM_SWITCH"]
    r = {n: s["nav"].pct_change() for n, s in R["sims"].items()}
    boot = {}
    for n in dyn:
        boot[n] = {"vsStaticEW4": C.block_bootstrap(r[n] - r["STATIC_EW4"]), "vsS0": C.block_bootstrap(r[n] - r["S0_ETF"])}
    ps = sorted((boot[n]["vsStaticEW4"]["twoSidedP"], n) for n in dyn)
    m_ = len(ps)
    running = 0
    for i, (p, n) in enumerate(ps):
        running = max(running, min(1.0, p * (m_ - i)))
        boot[n]["vsStaticEW4"]["holmP"] = r6(running, 4)
    res["inference"] = boot
    sleeve_daily = {k: R["navs"][k].pct_change().fillna(0) for k in C.CHOICE}
    res["decompositionVsStaticEW4"] = {n: decompose(R["weights"][n], {k: 0.25 for k in C.CHOICE}, sleeve_daily, R["sims"][n]["nav"],
                                                                R["sims"]["STATIC_EW4"]["nav"], bench, R["sims"][n]["costs"], R["sims"]["STATIC_EW4"]["costs"])
                                       for n in dyn}
    # decisions, switches, regret, uncertainty
    lab63 = R["labels"][63]
    beh = {}
    for n in dyn + ["STATIC_EW4"]:
        ws = R["weights"][n]
        ds = sorted(ws)
        changes = [0.5 * sum(abs(ws[d].get(k, 0) - ws[p].get(k, 0)) for k in C.CHOICE) for p, d in zip(ds, ds[1:])]
        dom = [max(ws[d], key=ws[d].get) for d in ds]
        regret, realised = [], []
        for d in ds:
            lab = lab63.get(d, {})
            if lab.get("exit") is None:
                continue
            vals = {k: (lab.get(k, 0.0) if k != "S0_ETF" else 0.0) for k in C.CHOICE}
            got = sum(ws[d].get(k, 0) * vals[k] for k in C.CHOICE)
            realised.append(got)
            regret.append(max(vals.values()) - got)
        after = []
        navd = R["sims"][n]["nav"]
        ew = R["sims"]["STATIC_EW4"]["nav"]
        for p, d, c in zip(ds, ds[1:], changes):
            if c >= 0.25:
                e = nxt(sessions, d)
                seg = navd.loc[e:].iloc[:64]
                seg_ew = ew.loc[e:].iloc[:64]
                if len(seg) == 64:
                    after.append(float(seg.iloc[-1] / seg.iloc[0] - seg_ew.iloc[-1] / seg_ew.iloc[0]))
        beh[n] = {"decisions": len(ds), "weightChangesAboveBand": int(sum(c > 0 for c in changes)), "largeSwitches": int(sum(c >= 0.25 for c in changes)),
                  "dominantSleeveChangeShare": r6(np.mean([a != b for a, b in zip(dom, dom[1:])]), 3),
                  "dominantSleeveCounts": pd.Series(dom).value_counts().to_dict(),
                  "meanRealised63dRelativeVsS0": r6(np.mean(realised)), "meanRegretVsBestSleeve63d": r6(np.mean(regret)),
                  "after63dRelativeToEW4AfterLargeSwitch": {"n": len(after), "mean": r6(np.mean(after)) if after else None,
                                                             "hitRate": r6(np.mean([x > 0 for x in after]), 3) if after else None}}
    for n in ("B1_RIDGE_ALL_STATES", "B2_LGBM_ALL_STATES", "B3_RIDGE_KR_ONLY"):
        dg = R["diags"][n]
        unc, conf = [], []
        for d, g in dg.items():
            if "mu" not in g or lab63.get(d, {}).get("exit") is None:
                continue
            k = max(g["mu"], key=lambda x: g["mu"][x])
            val = lab63[d].get(k, np.nan)
            (conf if abs(g["mu"][k]) > g["se"][k] * math.sqrt(63 / 20) else unc).append(val)
        beh[n]["topPickRealised63dWhenWithinOwnSE"] = {"n": len(unc), "mean": r6(np.mean(unc)) if unc else None}
        beh[n]["topPickRealised63dWhenOutsideSE"] = {"n": len(conf), "mean": r6(np.mean(conf)) if conf else None}
        beh[n]["oosForecast"] = oos_r2(dg, lab63, R["dates"])
    res["behaviour"] = beh
    # state-bucket performance (pre-defined buckets)
    st_daily = R["states"]
    buckets = {"TREND_252_UP": st_daily["MKT_TREND_252"] > 0, "TREND_252_DOWN": st_daily["MKT_TREND_252"] <= 0,
               "VOL_HIGH_80PCT": st_daily["VOL63_PCTL_EXPANDING"] > 0.8, "VOL_NOT_HIGH": st_daily["VOL63_PCTL_EXPANDING"] <= 0.8,
               "USDKRW_RISING_63": st_daily["USDKRW_CHG_63"] > 0, "USDKRW_FALLING_63": st_daily["USDKRW_CHG_63"] <= 0,
               "UST10_RISING_63": st_daily["UST10_CHG_63"] > 0, "UST10_FALLING_63": st_daily["UST10_CHG_63"] <= 0}
    bt = {}
    rb = bench.pct_change()
    for bn, mask in buckets.items():
        msk = mask.shift(1).reindex(bench.index).fillna(False).astype(bool)
        bt[bn] = {"sessions": int(msk.sum())}
        for n in ["S0_ETF"] + C.RISKY + ["STATIC_EW4"] + dyn:
            bt[bn][n] = r6(((r[n] - rb)[msk]).mean() * 252)
    res["stateBuckets"] = {"definition": "annualised mean daily excess vs 069500 on sessions whose PREVIOUS-session state fell in the bucket", **bt}
    res["q1Predictability"] = q1(R["states"], R["labels"], R["dates"])
    res["sleeveStandaloneFull"] = {k: r6((nv.iloc[-1] / nv.iloc[0]) ** (252 / (len(nv) - 1)) - 1) for k, nv in R["navs"].items()}
    # current state and hypothetical choice
    last = R["dates"][-1]
    cur = R["states"].loc[:last].iloc[-1]
    res["currentState"] = {"signalDate": str(last.date()), "states": {k: r6(cur[k], 5) for k in C.ALL_STATES},
                           "policyWeights": {n: {k: r6(v, 4) for k, v in R["weights"][n][max(R["weights"][n])].items()} for n in dyn},
                           "sleeveBooks": {k: R["books"][k][last] for k in C.CHOICE},
                           "learnedDiagnostics": {n: {kk: ({k: r6(v, 5) for k, v in vv.items()} if isinstance(vv, dict) else vv)
                                                      for kk, vv in R["diags"][n][max(R["diags"][n])].items()} for n in R["diags"]}}
    # decisions log
    res["decisionLog"] = {n: {str(d.date()): {k: r6(v, 4) for k, v in w.items()} for d, w in sorted(R["weights"][n].items())} for n in dyn}
    # post-hoc diagnostics
    post = {}
    yrs_wo = {}
    for n in ["S0_ETF"] + C.RISKY + ["STATIC_EW4"] + dyn:
        x = r[n].dropna()
        keep = x.index.year != 2025
        yrs_wo[n] = r6((1 + x[keep]).prod() ** (252 / keep.sum()) - 1)
    post["cagrWithout2025"] = yrs_wo
    E = run_all(df, closes, vols, sessions, macro, vix, fx, rf, exclude=POST_HOC_INDUSTRIES, label="EXCL")
    post["excludeDefenseAndElectronics"] = {n: r6(C.metrics(s["nav"], E["bench"], rfs)["cagr"]) for n, s in E["sims"].items()}
    K = run_all(df, closes, vols, sessions, macro, vix, fx, rf, cost_mult=2.0, label="COSTX2")
    post["costX2"] = {n: r6(C.metrics(s["nav"], K["bench"], rfs)["cagr"]) for n, s in K["sims"].items()}
    phases = {}
    for ph in (0, 1, 2, 3):
        P = R if ph == 0 else run_all(df, closes, vols, sessions, macro, vix, fx, rf, label=f"PHASE{ph}", phase=ph)
        phases[ph] = {n: {k: r6(v) for k, v in C.metrics(s["nav"], P["bench"], rfs).items() if k in ("cagr", "excessCagr", "sharpe", "mdd")}
                      for n, s in P["sims"].items()}
        phases[ph]["_window"] = {"start": str(P["start"].date()), "firstDecision": str(P["evalDates"][0].date())}
    post["rebalancePhase"] = {"note": "the same frozen rules on the other three 4-week phases; phase 0 is the frozen primary. Added after the S1 sleeve was "
                                      "found to differ from ml-strategy-tournament-v1 only by phase (see config postOutcomeAdditions)", "byPhase": phases}
    post["label"] = "POST_HOC: diagnostics only; never used to choose a policy"
    res["postHoc"] = post
    res["runtimeSeconds"] = round(time.time() - t0, 1)
    out = HERE / "results"
    out.mkdir(exist_ok=True)
    (out / "results.json").write_text(json.dumps(res, indent=1, ensure_ascii=False, default=str) + "\n")
    pd.to_pickle({"navs": {n: s["nav"] for n, s in R["sims"].items()}, "sleeves": R["navs"], "holdings": {n: s.get("holdings") for n, s in R["sims"].items()},
                  "states": R["states"], "weights": R["weights"], "bench": bench}, Path(a.scratch) / "cocktail-eval.pkl")
    print(json.dumps({n: {k: perf[n][k] for k in ("cagr", "excessCagr", "sharpe", "mdd")} for n in perf}, indent=0))


if __name__ == "__main__":
    main()
