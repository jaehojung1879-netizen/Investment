"""A separate hypothesis: S2 candidates exist, but when the S2 rule's own net expectation is weak the book holds 0 names (100% 069500).

    python research/alpha_mechanism_decomposition_v1/kr_followup/zero_gate.py --scratch <dir used by analyze.py>

RULE (ZG1, written before it was evaluated; POST_HOC_EXPLORATORY because the S2 history it is evaluated on was already seen):
  at each of S2's own signal dates d, read the S2 sleeve's NET NAV (frozen engine, costs included) and the 069500 NAV over the
  252 sessions ending at d's close. If S2 trailed 069500 over that window (excess <= 0, the outside option's own value), the
  book is {069500: 1} — zero stock names; otherwise it is the unchanged S2 book (0-5 names, empty slots in 069500).
  With fewer than 252 sessions of S2 history the rule abstains and keeps the S2 book. No threshold other than 0, no window
  search: 252 sessions is the one window the KR market-risk studies already use for the slow layer.
The gate reads only prices up to d. It is the one simple stand-in for "expected net performance" this repository can compute
point-in-time: no calibrated S2 forecast with a standard error exists (recorder.decide carries none), which is stated, not hidden.

Evaluated on the OCI-corrected close panel (oci_corrected_nav.corrected_closes) with the frozen four-account engine; the
uncorrected panel is reported beside it.
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


OC = _load("kr_oci_corrected_nav", HERE / "oci_corrected_nav.py")
A, REC = OC.A, OC.REC
S2 = "S2_VALUE_CONFIRMED"
WINDOW = 252


def gate_books(I, ctx, phases):
    sess = I["sessions"]
    out, log = {}, []
    for p, R in phases.items():
        nav = R["navs"][S2]
        etf = pd.Series(R["px"].etf, index=sess)
        out[p] = {}
        for d in sorted(R["weights"][A.SMS]):
            s2_book = REC.decide(ctx.by[d])["B1_S2_ORIGINAL"]["weights"]
            hist = nav.loc[:d].dropna()
            if len(hist) <= WINDOW:
                state, excess = "ABSTAIN_SHORT_HISTORY", None
            else:
                a, b = hist.index[-WINDOW - 1], hist.index[-1]
                excess = float(hist.loc[b] / hist.loc[a] - etf.loc[b] / etf.loc[a])
                state = "HOLD_S2" if excess > 0 else "ZERO_NAMES_069500"
            book = {A.M.ETF: 1.0} if state == "ZERO_NAMES_069500" else s2_book
            out[p][d] = book
            log.append({"phase": p, "signal": str(d.date()), "state": state, "trailingExcess": excess,
                        "s2StockNames": sum(1 for t in s2_book if t not in (A.M.ETF, A.M.CASH))})
    return out, log


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--scratch", required=True)
    a = ap.parse_args(argv)
    rec = json.loads((HERE / "010060-corporate-action-reconciliation.json").read_text())
    I = A.load(a.scratch)
    ctx = A.Ctx(I)
    phases = {p: A.run_phase(I, p) for p in range(4)}
    gated, log = gate_books(I, ctx, phases)
    s2 = {p: {d: REC.decide(ctx.by[d])["B1_S2_ORIGINAL"]["weights"] for d in phases[p]["weights"][A.SMS]} for p in phases}
    etf = {p: {d: {A.M.ETF: 1.0} for d in phases[p]["weights"][A.SMS]} for p in phases}
    fixed, _ = OC.corrected_closes(I["closes"], rec)
    out = {"label": "POST_HOC_EXPLORATORY_SEPARATE_HYPOTHESIS", "rule": "ZG1 trailing-252-session S2 net excess over 069500 <= 0 -> 0 names",
           "decisions": {"total": len(log), "zeroNames": sum(r["state"] == "ZERO_NAMES_069500" for r in log),
                         "abstain": sum(r["state"] == "ABSTAIN_SHORT_HISTORY" for r in log)},
           "byYearZeroShare": {}, "runs": {}}
    df = pd.DataFrame(log)
    df["year"] = df["signal"].str[:4]
    out["byYearZeroShare"] = {y: round(float((g["state"] == "ZERO_NAMES_069500").mean()), 4) for y, g in df.groupby("year")}
    for label, cl in (("OCI_CORRECTED", fixed), ("REPLAY_V16_UNCORRECTED", I["closes"])):
        I2 = dict(I, closes=cl)
        ctx2 = A.Ctx(I2)
        res = {"S2": A.four_account(I2, ctx2, phases, s2), "S2_ZERO_GATE": A.four_account(I2, ctx2, phases, gated),
               "ETF_ONLY": A.four_account(I2, ctx2, phases, etf)}
        bd = res["ETF_ONLY"]["nav"].pct_change()
        run = {k: A.summarise_accounts(v, None if k == "ETF_ONLY" else bd) for k, v in res.items()}
        r_s2, r_g = res["S2"]["nav"].pct_change().dropna(), res["S2_ZERO_GATE"]["nav"].pct_change().dropna()
        run["gateMinusS2"] = A.C.block_bootstrap(r_g - r_s2.reindex(r_g.index))
        yearly = {}
        for k, v in res.items():
            nv = v["nav"]
            yearly[k] = {int(y): round(float(g.iloc[-1] / (nv.iloc[nv.index.get_loc(g.index[0]) - 1] if nv.index.get_loc(g.index[0]) else nv.iloc[0]) - 1), 6)
                         for y, g in nv.groupby(nv.index.year)}
        run["calendarYearReturns"] = yearly
        out["runs"][label] = run
    (HERE / "zero-gate-comparison.json").write_text(json.dumps(out, indent=1, ensure_ascii=False, default=str) + "\n")
    df.to_csv(HERE / "zero-gate-decisions.csv", index=False)
    r = out["runs"]["OCI_CORRECTED"]
    print(json.dumps({k: {m: r[k].get(m) for m in ("cagr", "excessCagr", "mdd", "sharpe")} for k in ("S2", "S2_ZERO_GATE", "ETF_ONLY")}, default=str))


if __name__ == "__main__":
    main()
