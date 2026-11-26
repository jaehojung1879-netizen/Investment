"""The 010060.KS split-off reconciliation applied to the S2 holding ledger: four-account NAV before and after.

    python research/alpha_mechanism_decomposition_v1/kr_followup/oci_corrected_nav.py --scratch <dir used by analyze.py>

CORRECTION. `010060-corporate-action-reconciliation.json` measured the holder's economic return across the 2023-04-27..05-26 halt
(-20.65%, both successor securities at the relisting close) against the replay's -13.45%. The corrected panel multiplies every
010060.KS close from the relisting session on by k = (1 + economic) / (1 + replay), so the relisting-session return equals the
economic one and later daily returns are unchanged. Economically: the 456040.KS shares are valued at their relisting close and
rolled into 010060.KS at that close with no cost. That roll is a stated simplification (the new OCI's later returns are not
tracked); it is exact for every book that sold 010060 at the relisting session and an approximation for one that kept it.

Nothing else moves: books, dates, costs, benchmark and engine are the frozen ones (`analyze.four_account`), so the difference
between the two runs is the correction and nothing else.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
sys.path.insert(0, str(STUDY.parents[1]))


def _load(name, path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


A = _load("amd_analyze", STUDY / "analyze.py")
REC = _load("kr_four_book_recorder", STUDY / "prospective/recorder.py")
OCI = "010060.KS"


def corrected_closes(closes, rec):
    t = rec["timeline"]
    h = rec["holderReturnLastTradeToRelistingClose"]
    k = (1 + h["economicBothSecurities"]) / (1 + h["replayV16Conditional"])
    out = closes.copy()
    relist = pd.Timestamp(t["relisting"])
    out.loc[out.index >= relist, OCI] = out.loc[out.index >= relist, OCI] * k
    return out, k


def books(I, ctx, phases):
    by_phase = {b: {} for b in REC.BOOKS}
    for p, R in phases.items():
        for b in REC.BOOKS:
            by_phase[b][p] = {}
        for d in sorted(R["weights"][A.SMS]):
            out = REC.decide(ctx.by[d])
            for b in REC.BOOKS:
                by_phase[b][p][d] = out[b]["weights"]
    by_phase["SLEEVE_MOMENTUM_SWITCH"] = {p: {d: A.policy_book(phases[p], A.SMS, d) for d in phases[p]["weights"][A.SMS]} for p in phases}
    by_phase["STATIC_EW4"] = {p: {d: A.policy_book(phases[p], "STATIC_EW4", d) for d in phases[p]["weights"]["STATIC_EW4"]} for p in phases}
    return by_phase


def held_across(by_phase, rec, sessions):
    t = rec["timeline"]
    first, last = pd.Timestamp(t["haltFirst"]), pd.Timestamp(t["lastTradeBeforeHalt"])
    out = {}
    for b, phases in by_phase.items():
        hits = []
        for p, sched in phases.items():
            dates = sorted(sched)
            for i, d in enumerate(dates):
                e = A.M.next_session(sessions, d)
                nxt = A.M.next_session(sessions, dates[i + 1]) if i + 1 < len(dates) else None
                if e is not None and e <= last and (nxt is None or nxt >= first) and sched[d].get(OCI, 0) > 1e-12:
                    hits.append({"phase": p, "signal": str(d.date()), "weight": round(float(sched[d][OCI]), 6)})
        out[b] = hits
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--scratch", required=True)
    a = ap.parse_args(argv)
    rec = json.loads((HERE / "010060-corporate-action-reconciliation.json").read_text())
    I = A.load(a.scratch)
    ctx = A.Ctx(I)
    phases = {p: A.run_phase(I, p) for p in range(4)}
    by_phase = books(I, ctx, phases)
    by_phase["ETF_ONLY"] = {p: {d: {A.M.ETF: 1.0} for d in phases[p]["weights"][A.SMS]} for p in phases}
    out = {"label": "CONDITIONAL_EXPOSED_HISTORY_CORPORATE_ACTION_CORRECTION", "security": OCI,
           "method": "four equal accounts on their own 4-week phases, NAVs summed (analyze.four_account); only the 010060.KS close path differs",
           "heldIntoTheHalt": held_across(by_phase, rec, I["sessions"]), "runs": {}}
    closes_fixed, k = corrected_closes(I["closes"], rec)
    out["closeMultiplierFromRelisting"] = k
    for label, cl in (("BEFORE_REPLAY_V16", I["closes"]), ("AFTER_ECONOMIC_CORRECTION", closes_fixed)):
        I2 = dict(I, closes=cl)
        ctx2 = A.Ctx(I2)
        res = {b: A.four_account(I2, ctx2, phases, by_phase[b]) for b in by_phase}
        etf = res["ETF_ONLY"]
        out["runs"][label] = {b: {"cagr": r["cagr"], "excessCagrVsEtf": r["cagr"] - etf["cagr"], "mdd": r["mdd"], "sharpe": r["sharpe"],
                                  "endNav": float(r["nav"].iloc[-1]), "start": r["start"], "end": r["end"]} for b, r in res.items()}
    b4, af = out["runs"]["BEFORE_REPLAY_V16"], out["runs"]["AFTER_ECONOMIC_CORRECTION"]
    out["change"] = {b: {"cagr": af[b]["cagr"] - b4[b]["cagr"], "excessCagrVsEtf": af[b]["excessCagrVsEtf"] - b4[b]["excessCagrVsEtf"],
                         "endNav": af[b]["endNav"] - b4[b]["endNav"]} for b in b4}
    (HERE / "oci-corrected-four-account-nav.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps({b: {k2: round(v, 5) for k2, v in c.items()} for b, c in out["change"].items()}, indent=0))


if __name__ == "__main__":
    main()
