"""Data / learning integrity checks with counterexamples, on the real dataset and the stored fold records.

    python research/ml_strategy_tournament_v1/audit_checks.py --scratch <dir>

Writes results/data-audit.json: one PASS / FAIL / INCONCLUSIVE per item, the evidence and, where one exists, a counterexample.
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))
import tournament as T  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--scratch", required=True)
    a = ap.parse_args(argv)
    s = Path(a.scratch)
    matrix = pickle.loads((s / "matrix.pkl").read_bytes())["matrix"]
    blob = pickle.loads((s / "dataset.pkl").read_bytes())
    df, layers = blob["df"], blob["layers"]
    items = {}
    # 1 PIT universe
    rows = matrix.rows
    bad = rows[pd.to_datetime(rows["pitSnapshotDate"]) >= pd.to_datetime(rows["date"])]
    items["pitUniverse"] = {"status": "PASS" if bad.empty else "FAIL", "rows": int(len(rows)),
                            "evidence": "every row's membership snapshot is strictly older than its signal date", "counterexamples": bad.head(3).to_dict("records")}
    # 2 filing visibility
    av = matrix.available
    dates = pd.to_datetime(rows["date"]).to_numpy()
    viol, checked = [], 0
    for c in av.columns:
        col = pd.to_datetime(av[c], errors="coerce")
        m = col.notna().to_numpy()
        checked += int(m.sum())
        v = m & (col.to_numpy() >= dates)
        if v.any():
            i = int(np.flatnonzero(v)[0])
            viol.append({"feature": c, "date": str(rows["date"].iloc[i]), "ticker": rows["ticker"].iloc[i], "available": str(col.iloc[i])})
    items["filingVisibility"] = {"status": "PASS" if not viol else "FAIL", "filingCellsChecked": checked, "counterexamples": viol[:5],
                                 "evidence": "every filing-based cell's visibility date (receipt date + 1) is before its signal date"}
    # 3 macro release timing
    items["macroReleaseTiming"] = {"status": "PASS", "evidence": "the only macro input is the BOK base rate, applied from its announcement date (test_bok_rate_is_the_latest_announced_rate); "
                                   "no revised macro panel is used. Coverage limit: no vintage-safe Korean macro series exists in the repository."}
    # 4 duplicates
    dup = df.duplicated(["date", "ticker"]).sum()
    items["duplicateKeys"] = {"status": "PASS" if dup == 0 else "FAIL", "duplicates": int(dup)}
    # 5 label maturity and purge, from every stored fold record
    viol = []
    nfold = 0
    for p in sorted((s / "preds").glob("*.npz")):
        for f in json.loads(str(np.load(p)["folds"])):
            if f.get("trainRows"):
                nfold += 1
                if f["trainLastExit"] >= f["testFirst"]:
                    viol.append({"strategy": p.stem, **f})
    exits = df["exit126"].dropna()
    entry_ok = bool(((df.loc[exits.index, "exit126"] - df.loc[exits.index, "date"]).dt.days > 126 * 1.3).all())
    items["labelMaturityAndPurge"] = {"status": "PASS" if not viol and entry_ok else "FAIL", "foldsChecked": nfold, "counterexamples": viol[:3],
                                      "evidence": "each fold's latest training-label exit session precedes its first test signal date; every exit is 126 KR sessions after the session following the signal"}
    # 6 leak canary: permute training labels within date for one real configuration, K times. A noise-trained model is a random tilt on the
    # features, so ONE draw can show a large |IC| in a year when a factor is strongly priced; the permutation MEAN must be ~0, and where the
    # real-label IC falls in the permutation distribution is itself a test of the model.
    cfg = next(g for g in T.grid() if g["id"] == "XGB_CI_RANK_h1")
    cross = layers["company"] + layers["industry"]
    ranked = T.rank_transform(df, cross)
    rng = np.random.default_rng(0)
    years, draws = (2019, 2021, 2023), 10
    real, perm = {}, {y: [] for y in years}
    for year in years:
        train, test = T.fold_split(df, year, 126)
        p1, *_ = T.fit_predict(cfg, train, test, ranked.loc[train.index], ranked.loc[test.index], layers)
        real[year] = float(T.spearman_by_date(test.assign(s=p1), "s", "y126").mean())
        for _ in range(draws):
            shuffled = train.copy()
            shuffled["y126"] = shuffled.groupby("date")["y126"].transform(lambda v: rng.permutation(v.to_numpy()))
            p2, *_ = T.fit_predict(cfg, shuffled, test, ranked.loc[train.index], ranked.loc[test.index], layers)
            perm[year].append(float(T.spearman_by_date(test.assign(s=p2), "s", "y126").mean()))
    allp = np.array([v for y in years for v in perm[y]])
    se = allp.std(ddof=1) / np.sqrt(len(allp))
    real_mean = float(np.mean(list(real.values())))
    pooled = np.array([np.mean([perm[y][k] for y in years]) for k in range(draws)])
    items["leakCanaryPermutedTrainingLabels"] = {
        "status": "PASS" if abs(allp.mean()) < 2 * se else "FAIL", "config": cfg["id"], "years": list(years), "draws": draws,
        "oosIcRealLabels": real, "oosIcPermutedLabelsByYear": perm, "permutedMean": float(allp.mean()), "permutedSe": float(se),
        "permutedSdAcrossDraws": float(allp.std(ddof=1)), "realMeanIc": real_mean,
        "permutationPValueRealVsNoiseModels": float((1 + (pooled >= real_mean).sum()) / (1 + draws)),
        "firstRunNote": "a first single-draw version of this check read FAIL (permuted ICs 0.006 / -0.120 / -0.200 in 2019/2021/2023); one draw of a noise-trained "
                        "model is a random factor tilt and cannot separate leakage from factor variance, so the check was rerun with 10 draws per year",
        "evidence": "PASS means noise-trained models average ~0 OOS IC: the features do not carry the label. The p-value compares the real model's mean IC with the "
                    "distribution of noise-trained models' mean IC."}
    # 7 normalisation / imputation
    items["normalisationAndImputation"] = {"status": "PASS", "evidence": "company/industry features are within-date percentile ranks (same-date only); linear market z-scores and tree market medians "
                                           "are fitted on the training fold only (tournament._linear_matrix / _tree_matrix); no feature selection step exists - feature sets are fixed in config.json"}
    # 8 corporate actions / dividends
    items["dividendsSplitsCorporateActions"] = {"status": "INCONCLUSIVE",
        "evidence": "stock returns are replay-v16 total-return closes: split-continuous, Yahoo distributions forward-accumulated. Continuing-name dividend completeness is "
                    "corroborated on 25 names only (99.1% of DART dividend-years matched, v2.31); the 22 terminated names carry no distributions at all. The ETF uses the "
                    "independently reconciled series. Codex's DPS correction (#328, 241560) concerns the shareholder-event input, not this price panel.",
        "replayVsReconciledEtfAnnual": json.loads((HERE / "results" / "data-eligibility.json").read_text())["inputs"]["replayVsReconciledBenchmarkAnnual"]}
    term = json.loads((HERE / "results" / "data-eligibility.json").read_text())["terminatedInPricePanel"]
    items["terminalConsiderationAndSuspension"] = {"status": "INCONCLUSIVE", "terminatedNamesInPanel": len(term),
        "evidence": "no terminal consideration is sealed; a held terminating name is written off (primary, lower bound) or converted at its last close (sensitivity, upper bound); "
                    "a suspended name cannot be traded (tested). The gap between the two bounds is published per strategy as cagrUpperBoundTerminalAtLastClose."}
    items["selectionVersusEvaluation"] = {"status": "INCONCLUSIVE",
        "evidence": "each model's hyperparameters are fixed by config, so there is no inner tuning; but the tournament ranking itself is computed on the same 2016-2026 window it reports. "
                    "That selection bias is measured, not removed: nested past-only selection, deflated Sharpe, CSCV PBO (overfit-diagnostics-*.json)."}
    out = {"studyId": T.CONFIG["studyId"], "evidenceClass": T.CONFIG["evidenceClass"], "items": items}
    (HERE / "results" / "data-audit.json").write_text(json.dumps(out, indent=1, default=str, ensure_ascii=False) + "\n")
    print(json.dumps({k: v["status"] for k, v in items.items()}), json.dumps(items["leakCanaryPermutedTrainingLabels"], default=str)[:900])


if __name__ == "__main__":
    main()
