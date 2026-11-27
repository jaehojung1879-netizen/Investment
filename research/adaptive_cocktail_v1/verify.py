"""Independent checks on the adaptive-cocktail-v1 run (writes results/verification.json).

1. S0 path == the reconciled 069500 series (the ETF leg of the engine).
2. SLEEVE_MOMENTUM_SWITCH and STATIC_EW4 re-chained from sleeve daily returns with the recorded weights (no combined book, no netting):
   a different calculation, so agreement is expected to within netting and cost, not to machine precision.
3. The phase-0 bootstrap repeated on every rebalance phase for the policies that matter.
4. Real-data leak canary: every 63-session label whose exit is on or after 2022-01-03 is replaced by +1.0; every learned decision dated
   before that day must be unchanged.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))
import cocktail as C  # noqa: E402
import run as R  # noqa: E402


def chain(weights, sleeves, sessions, start, end):
    days = sessions[(sessions >= start) & (sessions <= end)]
    ret = pd.DataFrame({k: v.pct_change() for k, v in sleeves.items()}).reindex(days).fillna(0)
    w = pd.DataFrame(0.0, index=days, columns=list(sleeves))
    for d, wd in sorted(weights.items()):
        e = R.nxt(sessions, d)
        for k in sleeves:
            w.loc[w.index > e, k] = wd.get(k, 0.0)
    nav = (1 + (w[list(C.CHOICE)] * ret[list(C.CHOICE)]).sum(axis=1)).cumprod()
    return nav


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--scratch", required=True)
    a = ap.parse_args(argv)
    df, closes, vols, sessions, macro, vix, fx, rf, _ = R.load(a.scratch)
    ev = pd.read_pickle(Path(a.scratch) / "cocktail-eval.pkl")
    out = {}
    s0 = ev["navs"]["S0_ETF"]
    etf = closes[C.ETF].reindex(s0.index)
    out["s0EqualsReconciledEtf"] = {"maxRelDiff": float((s0 / s0.iloc[0] / (etf / etf.iloc[0]) - 1).abs().max())}
    yrs = (len(s0) - 1) / 252
    cg = lambda n: float((n.iloc[-1] / n.iloc[0]) ** (1 / yrs) - 1)  # noqa: E731
    for name in ("SLEEVE_MOMENTUM_SWITCH", "STATIC_EW4", "A1_MOMENTUM_CRASH_GUARD", "B1_RIDGE_ALL_STATES"):
        ch = chain(ev["weights"][name], ev["sleeves"], sessions, s0.index[0], s0.index[-1])
        out[f"rechain_{name}"] = {"engineCagr": cg(ev["navs"][name]), "rechainedCagrNoNettingNoPolicyCost": cg(ch)}
    boot = {}
    for ph in (0, 1, 2, 3):
        P = R.run_all(df, closes, vols, sessions, macro, vix, fx, rf, label=f"PHASE{ph}", phase=ph)
        r = {n: s["nav"].pct_change() for n, s in P["sims"].items()}
        boot[ph] = {n: {"vsStaticEW4": C.block_bootstrap(r[n] - r["STATIC_EW4"]), "vsS0": C.block_bootstrap(r[n] - r["S0_ETF"])}
                    for n in ("SLEEVE_MOMENTUM_SWITCH", "A1_MOMENTUM_CRASH_GUARD", "B2_LGBM_ALL_STATES", "S2_VALUE_CONFIRMED")}
    out["bootstrapByPhase"] = boot
    # leak canary
    P = R.run_all(df, closes, vols, sessions, macro, vix, fx, rf, label="CANARY")
    cut = pd.Timestamp("2022-01-03")
    poisoned = {d: ({**lab, **{k: 1.0 for k in C.CHOICE if k in lab}} if lab.get("exit") is not None and lab["exit"] >= cut else lab)
                for d, lab in P["labels"][63].items()}
    navs = P["navs"]
    same = {}
    for kind, cols in (("B1_RIDGE_ALL_STATES", C.ALL_STATES), ("B2_LGBM_ALL_STATES", C.ALL_STATES)):
        base, _ = R.learned_policy(kind, P["states"], navs, P["dates"], P["labels"][63], cols)
        pois, _ = R.learned_policy(kind, P["states"], navs, P["dates"], poisoned, cols)
        early = [d for d in base if d < cut]
        later = [d for d in base if d >= pd.Timestamp("2022-07-01")]
        same[kind] = {"decisionsBeforeCut": len(early), "identicalBeforeCut": all(base[d] == pois[d] for d in early),
                      "laterDecisionsThatChanged": sum(base[d] != pois[d] for d in later), "laterDecisions": len(later)}
    out["leakCanary"] = {"cut": str(cut.date()), **same,
                         "reading": "decisions before the cut cannot see labels exiting after it; later decisions must react to the poison (proof the canary bites)"}
    (HERE / "results" / "verification.json").write_text(json.dumps(out, indent=1, default=float) + "\n")
    print(json.dumps({k: v for k, v in out.items() if k != "bootstrapByPhase"}, indent=1, default=float))
    for ph, v in boot.items():
        print(ph, {n: (round(x["vsStaticEW4"]["annualisedMeanDiff"] * 100, 1), [round(c * 100, 1) for c in x["vsStaticEW4"]["ci95"]]) for n, x in v.items()})


if __name__ == "__main__":
    main()
