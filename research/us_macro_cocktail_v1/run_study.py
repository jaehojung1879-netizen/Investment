"""Run us-macro-cocktail-v1 Track A from the frozen snapshot and write results/.

python research/us_macro_cocktail_v1/run_study.py
Deterministic: no network, fixed seeds. Re-running reproduces results byte for byte.
"""
from __future__ import annotations

import gzip
import io
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cocktail as C  # noqa: E402
import relations as R  # noqa: E402

OUT = C.HERE / "results"
END = "2026-10-30"
WINDOWS = {"primary": "2015-12-31", "extended": "2008-05-30"}


def _round(obj):
    if isinstance(obj, float):
        return None if not np.isfinite(obj) else round(obj, 6)
    if isinstance(obj, dict):
        return {k: _round(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_round(v) for v in obj]
    if isinstance(obj, (np.floating,)):
        return _round(float(obj))
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    return obj


def dump(name: str, obj) -> None:
    OUT.mkdir(exist_ok=True)
    (OUT / name).write_text(json.dumps(_round(obj), indent=1, sort_keys=True, ensure_ascii=False) + "\n")


def krw_nav(nav: pd.Series, fx: pd.Series) -> pd.Series:
    k = nav * fx.reindex(nav.index)
    return k / k.iloc[0]


def run_window(p: C.Panel, state: pd.DataFrame, wf_all: C.WalkForward, label: str, first: str) -> dict:
    sched = C.schedule(p, first, END)
    # decision index inside the full walk-forward schedule
    pos = {d: i for i, d in enumerate(wf_all.dec)}
    targets, info = {}, {}
    for name in C.STRATEGIES:
        targets[name], info[name] = {}, {}
        for d in sched.decisions:
            w, meta = C.target_weights(name, pos[d], p, state, wf_all)
            targets[name][d] = w
            info[name][d] = meta
    res = {}
    navs = {}
    for name in C.STRATEGIES:
        bt = C.backtest(targets[name], sched, p, END)
        bt2 = C.backtest(targets[name], sched, p, END, cost_mult=2.0)
        navs[name] = bt["nav"]
        w = pd.DataFrame(targets[name]).T.fillna(0.0)
        avg = w.mean().to_dict()
        res[name] = {"costTotalPctOfInitial": bt["costTotalFrac"] * 100,
                     "turnoverTwoWayPerYear": bt["turnoverPerYear"],
                     "averageTargetWeights": {k: v for k, v in sorted(avg.items()) if v > 1e-9},
                     "averageEquityWeight": float(w.reindex(columns=C.ASSETS, fill_value=0.0)[["SPY", "QQQ"]].sum(axis=1).mean()),
                     "navCost2x": bt2["nav"]}
    # single-asset buy-and-hold references (monthly rebalanced 100% = buy and hold, costs on build only)
    for a in C.ASSETS:
        bt = C.backtest({d: {a: 1.0} for d in sched.decisions}, sched, p, END)
        navs[f"ASSET_{a}"] = bt["nav"]
    bil, spy = navs["ASSET_BIL"], navs["ASSET_SPY"]
    out = {"window": label, "firstDecision": str(sched.decisions[0].date()),
           "firstExecution": str(sched.executions[0].date()), "end": END,
           "decisions": int(len(sched.decisions)), "strategies": {}, "assets": {}}
    fx_next, fx_same = p.fx_next, p.fx_same
    for a in C.ASSETS:
        out["assets"][a] = {"USD": C.metrics(navs[f"ASSET_{a}"], bil, spy),
                            "KRW": C.metrics(krw_nav(navs[f"ASSET_{a}"], fx_next), krw_nav(bil, fx_next), krw_nav(spy, fx_next))}
    fx_nav = fx_next.loc[navs["S1_SPY"].index] / fx_next.loc[navs["S1_SPY"].index].iloc[0]
    out["usdkrw"] = {"startRate": float(fx_next.loc[navs["S1_SPY"].index[0]]), "endRate": float(fx_next.loc[navs["S1_SPY"].index[-1]]),
                     "fxCagrPct": float(((fx_nav.iloc[-1]) ** (365.25 / (fx_nav.index[-1] - fx_nav.index[0]).days) - 1) * 100),
                     "conversion": "first DEXKOUS print dated after each US session (no look-ahead)"}
    for name in C.STRATEGIES:
        nav = navs[name]
        twin_w = res[name]["averageTargetWeights"]
        twin = C.backtest({d: twin_w for d in sched.decisions}, sched, p, END)["nav"]
        m_usd = C.metrics(nav, bil, spy)
        m_usd2 = C.metrics(res[name]["navCost2x"], bil, spy)
        m_krw = C.metrics(krw_nav(nav, fx_next), krw_nav(bil, fx_next), krw_nav(spy, fx_next))
        m_krw_same = C.metrics(krw_nav(nav, fx_same), krw_nav(bil, fx_same), krw_nav(spy, fx_same))
        twin_m = C.metrics(twin, bil, spy)
        s4 = navs["S4_BALANCED"]
        out["strategies"][name] = {
            "USD": m_usd, "USD_cost2x": m_usd2, "KRW_unhedged": m_krw,
            "KRW_unhedged_sameDayFxSensitivity": {"cagrPct": m_krw_same["cagrPct"], "maxDrawdownPct": m_krw_same["maxDrawdownPct"]},
            "KRW_hedged": "NOT_COMPUTED_NO_VERIFIED_HEDGE_INSTRUMENT_OR_COST",
            "fxContributionCagrPct": m_krw["cagrPct"] - m_usd["cagrPct"],
            "turnoverTwoWayPerYear": res[name]["turnoverTwoWayPerYear"],
            "costTotalPctOfInitial": res[name]["costTotalPctOfInitial"],
            "averageTargetWeights": twin_w, "averageEquityWeight": res[name]["averageEquityWeight"],
            "vsS4": C.paired(nav, s4) if name != "S4_BALANCED" else None,
            "vsSPY": C.paired(nav, spy) if name != "S1_SPY" else None,
            "averageWeightTwin": {"USD": {k: twin_m[k] for k in ("cagrPct", "volPct", "sharpeOverBil", "maxDrawdownPct")},
                                  "strategyMinusTwin": C.paired(nav, twin),
                                  "cagrGapPct": m_usd["cagrPct"] - twin_m["cagrPct"],
                                  "arithGapPct": m_usd["arithAnnualPct"] - twin_m["arithAnnualPct"],
                                  "compoundingGapPct": m_usd["compoundingTermPct"] - twin_m["compoundingTermPct"]},
            "decompositionVsS4": {"cagrGapPct": m_usd["cagrPct"] - C.metrics(s4, bil, spy)["cagrPct"],
                                  "arithGapPct": m_usd["arithAnnualPct"] - C.metrics(s4, bil, spy)["arithAnnualPct"],
                                  "compoundingGapPct": m_usd["compoundingTermPct"] - C.metrics(s4, bil, spy)["compoundingTermPct"]},
        }
        if name in ("D4_RIDGE_SIGN", "D5_TREE_SIGN", "D6_FORECAST_VOL_SLEEVE"):
            fb = [d for d, m in info[name].items() if m.get("fallback") or m.get("volSource") == "TRAILING_63_FALLBACK"]
            out["strategies"][name]["fallbackDecisions"] = len(fb)
            out["strategies"][name]["firstModelDecision"] = next((str(d.date()) for d, m in info[name].items()
                                                                   if not (m.get("fallback") or m.get("volSource") == "TRAILING_63_FALLBACK")), None)
        if name == "D3_STATE_RULES":
            from collections import Counter
            c = Counter(r for m in info[name].values() for r in m["fired"])
            out["strategies"][name]["ruleFiredMonths"] = dict(c)
    out["regimeSplits"] = R.regime_splits(navs, p, state, sched)
    out["calendarYearsUSD"] = R.calendar_years(navs)
    return out, navs, targets, info


def main() -> None:
    OUT.mkdir(exist_ok=True)
    ident = C.verify_inputs()
    p = C.build_panel()
    state = C.state_frame(p)
    full = C.schedule(p, WINDOWS["extended"], END)
    wf = C.WalkForward(p, state, full.decisions, full.executions)
    results = {"identity": ident, "windows": {}}
    monthly = {}
    for label, first in WINDOWS.items():
        out, navs, targets, info = run_window(p, state, wf, label, first)
        results["windows"][label] = out
        mm = pd.DataFrame({k: C.month_end_series(v) for k, v in navs.items()})
        monthly[label] = mm
        if label == "primary":
            weights = []
            for name in C.STRATEGIES:
                for d, w in targets[name].items():
                    weights.append({"strategy": name, "decision": str(d.date()), **{a: round(w.get(a, 0.0), 6) for a in C.ASSETS}})
            buf = io.StringIO()
            pd.DataFrame(weights).to_csv(buf, index=False, lineterminator="\n")
            (OUT / "primary-target-weights.csv.gz").write_bytes(gzip.compress(buf.getvalue().encode(), mtime=0))
    OUT.mkdir(exist_ok=True)
    for label, mm in monthly.items():
        buf = io.StringIO()
        (mm / mm.iloc[0]).round(8).to_csv(buf, index_label="monthEnd", lineterminator="\n")
        (OUT / f"{label}-monthly-nav-usd.csv").write_text(buf.getvalue())
    # latest research allocation (decision on the last month-end in the data)
    last_i = len(wf.dec) - 1
    latest = {"decision": str(wf.dec[last_i].date()), "execution": str(wf.exe[last_i].date()),
              "status": "RESEARCH_ONLY_NOT_A_RECOMMENDATION_NO_PRODUCTION_EFFECT",
              "state": {k: float(v) for k, v in state.loc[wf.dec[last_i]].items()}, "weights": {}}
    for name in C.STRATEGIES:
        w, meta = C.target_weights(name, last_i, p, state, wf)
        latest["weights"][name] = {"weights": w, "meta": meta}
    results["latestAllocation"] = latest
    dump("result.json", results)
    dump("data-audit.json", R.data_audit(p))
    dump("relations.json", R.relations(p, state))
    dump("risk-forecast.json", R.risk_forecast(p, state))
    print(json.dumps({k: {n: v["USD"]["cagrPct"] for n, v in w["strategies"].items()} for k, w in results["windows"].items()}, indent=1))


if __name__ == "__main__":
    main()
