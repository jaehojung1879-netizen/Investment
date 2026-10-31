"""Independent read-only audit of #286 `c2-aggregate-falsification-v2` (POST_OUTCOME aggregate only).

Reads nothing but the published `research/c2_aggregate_evidence_v1/result-v2.json` (at a pinned #286 commit, via git)
and the repository's dated BOK policy-rate file. No ledger, price, label or path is read; no model is fitted to any
unpublished outcome. Everything here re-reads numbers #286 already published and asks whether its readings survive a
change of exposure assumption.

    python -m research.independent_audit_c2_marketc_v1.c2_beta_audit
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PR286_COMMIT = "97aa2cfe2cabace05796f9179f2711cf83698d42"
SOURCE_PATH = "research/c2_aggregate_evidence_v1/result-v2.json"
OUT = HERE / "c2-beta-audit.json"


def load_source(blob=None):
    raw = blob if blob is not None else subprocess.run(
        ["git", "show", f"{PR286_COMMIT}:{SOURCE_PATH}"], cwd=ROOT, check=True, capture_output=True).stdout
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def mean_policy_rate(start, end, path=ROOT / "data/bok-policy-rates.json"):
    events = json.loads(Path(path).read_text())["events"]
    s = pd.Series({pd.Timestamp(e["date"]): float(e["annualRatePct"]) for e in events}).sort_index()
    days = pd.date_range(start, end, freq="D")
    return float(s.reindex(s.index.union(days)).ffill().reindex(days).mean())


def ols(y, x):
    X = np.column_stack([np.ones(len(x)), x])
    b = np.linalg.lstsq(X, y, rcond=None)[0]
    e = y - X @ b
    s2 = float(e @ e) / (len(y) - 2)
    se = np.sqrt(np.diag(s2 * np.linalg.inv(X.T @ X)))
    return {"n": int(len(y)), "intercept": float(b[0]), "interceptSe": float(se[0]),
            "beta": float(b[1]), "betaSe": float(se[1])}


def audit(src, rf):
    rows = src["publishedCalendarContext"]["rows"]
    year = np.array([int(r["year"]) for r in rows])
    c2 = np.array([r["c2ReturnPct"] for r in rows], float)
    p0 = np.array([r["passiveReturnPct"] for r in rows], float)
    samples = {"ALL_14_ROWS": np.ones(len(rows), bool),
               "INTERIOR_EXCLUDING_BOOKENDS": np.array([not r["isWindowBookendYear"] for r in rows]),
               "2013_2024_EXCLUDING_2025_2026": year <= 2024}
    fits = {}
    for name, sel in samples.items():
        f = ols(c2[sel], p0[sel])
        f["jensenAlphaPpPerYear"] = f["intercept"] - (1 - f["beta"]) * rf
        pred_win = (f["intercept"] + (f["beta"] - 1) * p0[sel]) > 0
        f["yearsWhereFittedBetaAloneAndInterceptPredictTheObservedWinLossSign"] = int((pred_win == (c2[sel] > p0[sel])).sum())
        fits[name] = f
    loo = {}
    for i in range(len(rows)):
        keep = np.arange(len(rows)) != i
        loo[str(year[i])] = ols(c2[keep], p0[keep])["beta"]
    down = p0 < 0
    beta_only = fits["ALL_14_ROWS"]["beta"]
    obs = src["observed"]
    return {
        "auditId": "independent-audit-c2-beta-v1",
        "evidenceClass": "POST_OUTCOME_READ_ONLY_RE_READING_OF_PUBLISHED_AGGREGATES",
        "source": {"pr": 286, "commit": PR286_COMMIT, "path": SOURCE_PATH},
        "riskFreeProxy": {"series": "data/bok-policy-rates.json (BOK base rate, NOT an investable cash return)",
                          "meanPctPerYear2013_2026": rf},
        "publishedExposureBound": src["exposureBound"]["absoluteBetaUpperBound"],
        "annualRowRegression_C2_on_069500": fits,
        "leaveOneYearOutBeta": {"byOmittedYear": loo, "min": min(loo.values()), "max": max(loo.values()),
                                "reading": "Beta from 14 published annual/partial-year returns is a SENSITIVITY reading, "
                                           "not a verified daily exposure: one year moves it from 0.38 to 0.69."},
        "c2StockLegBetaImplied": {
            "averageEtfWeightPct": obs["C2"]["averageBenchmarkWeightPct"],
            "stockLegBetaIfEtfBetaIsOne": (beta_only - obs["C2"]["averageBenchmarkWeightPct"] / 100)
            / (1 - obs["C2"]["averageBenchmarkWeightPct"] / 100)},
        "downYearReading": {
            "publishedDownYearWins": src["publishedCalendarContext"]["allYears"]["DOWN"]["wins"],
            "downYears": int(down.sum()),
            "mechanicalExcessFromBetaAloneInDownYearsPp": [round((beta_only - 1) * float(p), 3) for p in p0[down]],
            "reading": "With beta < 1 a down benchmark year produces positive excess mechanically, (1 - beta) x |R_m|; the "
                       "5/5 down-year and 2/9 up-year counts are the signature of the exposure, not separate evidence "
                       "of selection or timing."},
        "costStressUnderExposureAdjustment": {
            "published3xUnitBetaEdgeUpperPp": next(b["edgeUpperPp"] for b in src["costBounds"] if b["multiplier"] == 3),
            "extraCostDragAt3xPpApprox": 2 * obs["C2"]["annualizedCostDragPct"],
            "jensenAlphaAfter3xApproxPp": {k: v["jensenAlphaPpPerYear"] - 2 * obs["C2"]["annualizedCostDragPct"]
                                           for k, v in fits.items()},
            "reading": "ILLUSTRATION ONLY. The -1.470pp bound is against a unit-beta 069500 path. Against the C2 book's own "
                       "annual-row exposure the 3x point estimate stays positive. This is not executable alpha, not a "
                       "confidence interval and does not separate stock selection from defensive style, timing or cash. "
                       "Neither comparator is registered; the original fixed C2 method is unchanged."},
        "limitations": [
            "14 annual rows, two bookend partial years, 2025/2026 high leverage; no daily C2 path is published.",
            "Arithmetic annual regression vs CAGR-based bounds: magnitudes are approximate and not additive.",
            "The intercept cannot separate stock-specific selection from a defensive / low-beta factor premium.",
            "Outcome-exposed history; no promotion, no rerun, no new path built."],
    }


def main():
    src, digest = load_source()
    out = audit(src, mean_policy_rate("2013-01-07", "2026-09-14"))
    out["source"]["sha256"] = digest
    OUT.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    print(json.dumps(out["annualRowRegression_C2_on_069500"], indent=1))


if __name__ == "__main__":
    main()
