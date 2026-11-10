"""Step 2: join the PIT matrix with market state and forward labels; write the eligibility / coverage report.

    python research/ml_strategy_tournament_v1/prepare_dataset.py --scratch <dir>

Reads <dir>/matrix.pkl (build_features.py) and the verified raw inputs under <dir>/raw (re-verified by the sealed loader), writes
<dir>/dataset.pkl and research/ml_strategy_tournament_v1/results/data-eligibility.json.
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

from pipeline import kr_model_portfolio_execution as X  # noqa: E402
from pipeline import kr_model_raw_snapshot as K  # noqa: E402
from pipeline import replay_calendar as RC  # noqa: E402
import tournament as T  # noqa: E402

ROOT = HERE.parents[1]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--scratch", required=True)
    a = ap.parse_args(argv)
    s = Path(a.scratch)
    blob = pickle.loads((s / "matrix.pkl").read_bytes())
    matrix = blob["matrix"]
    spec = K.frozen_spec()
    _, memberships, _, prices = X.load_sources(s / "raw", spec)
    sessions = RC.sessions("2013-01-01", "2026-12-31", "KR")
    bench_end = T.closes_on(prices, T.BENCH, sessions).last_valid_index()
    sessions = sessions[sessions <= bench_end]
    bok = json.loads((ROOT / "data/bok-policy-rates.json").read_text())["events"]
    corrected = json.loads((ROOT / "docs/audits/kr-alpha-atlas-phase-c-integrity/benchmark-reconciliation-corrected.json").read_text())
    q = pd.Series({pd.Timestamp(r["date"]): float(r["Close"]) for r in corrected["correctedBenchmarkQuotes"]}).sort_index()
    sessions = sessions[sessions <= q.index.max()]
    reconciled = q.reindex(sessions)
    if reconciled.isna().any():
        raise SystemExit("RECONCILED_BENCHMARK_MISSING_SESSIONS: " + str(list(reconciled[reconciled.isna()].index[:5])))
    replay_bench = T.closes_on(prices, T.BENCH, sessions)
    prices = dict(prices)
    prices["069500.KS@replay-v16"] = prices[T.BENCH]
    prices[T.BENCH] = pd.DataFrame({"Close": reconciled, "Volume": T.volumes_on(prices, "069500.KS@replay-v16", sessions).fillna(1.0)})
    df, bench = T.assemble(matrix, prices, sessions, bok)
    layers, coverage = T.feature_layers(df)
    tickers = sorted(set(df["ticker"]) | {T.BENCH, "069500.KS@replay-v16"})
    closes = pd.DataFrame({t: T.closes_on(prices, t, sessions) for t in tickers})
    vols = pd.DataFrame({t: T.volumes_on(prices, t, sessions) for t in tickers})
    (s / "dataset.pkl").write_bytes(pickle.dumps({"df": df, "layers": layers, "closes": closes, "volumes": vols, "sessions": sessions,
                                                  "identity": blob["identity"], "matrixDigest": matrix.digest()}))
    df["year"] = df["date"].dt.year
    feats = layers["company"] + layers["industry"] + layers["market"]
    by_year = df.groupby("year")[feats].apply(lambda g: g.notna().mean()).round(4)
    first_cov = {}
    for c in feats:
        ok = by_year[c][by_year[c] >= 0.5]
        first_cov[c] = int(ok.index.min()) if len(ok) else None
    lab = {}
    for h in (126, 252):
        y = df[f"y{h}"]
        has_exit = df[f"exit{h}"].notna()
        lab[f"H{h}"] = {"rows": int(len(df)), "labelled": int(y.notna().sum()), "exitBeyondPriceEnd": int((~has_exit).sum()),
                        "withheldDespiteExit": int((has_exit & y.isna()).sum()),
                        "withheldTickers": sorted(df.loc[has_exit & y.isna(), "ticker"].unique().tolist()),
                        "lastLabelledSignal": str(df.loc[y.notna(), "date"].max().date()), "byYearLabelled": df.groupby("year")[f"y{h}"].apply(lambda v: int(v.notna().sum())).to_dict()}
    book_terminal = T.PriceBook({t: pd.DataFrame({"Close": closes[t], "Volume": vols[t]}) for t in tickers}, tickers, sessions, closes[T.BENCH]).terminal
    q = T.quality_mask(df)
    report = {
        "studyId": T.CONFIG["studyId"], "evidenceClass": T.CONFIG["evidenceClass"],
        "inputs": {"signalHistoryCommit": "4ea107ed0cde289f0a049a65ff13d2441a786710", "inputIdentitySha256": blob["identity"]["sha256"],
                   "matrixDigest": matrix.digest(), "tradingValueBasis": blob["tradingValueBasis"], "configSha256": T.sha256_file(HERE / "config.json"),
                   "accountingContentSha256": blob["identity"]["accountingContentSha256"], "replayManifestSha256": blob["identity"]["replayManifestSha256"],
                   "benchmarkSourceSha256": T.sha256_file(ROOT / "docs/audits/kr-alpha-atlas-phase-c-integrity/benchmark-reconciliation-corrected.json"),
                   "replayVsReconciledBenchmarkAnnual": {int(y): [round(float(a), 4), round(float(b), 4)] for y, a, b in zip(
                       range(2013, 2027), replay_bench.groupby(replay_bench.index.year).last().pct_change().reindex(range(2013, 2027)),
                       reconciled.groupby(reconciled.index.year).last().pct_change().reindex(range(2013, 2027)))},
                   "bokPolicyRateFileSha256": T.sha256_file(ROOT / "data/bok-policy-rates.json")},
        "universe": {"signalDates": int(df["date"].nunique()), "firstSignal": str(df["date"].min().date()), "lastSignal": str(df["date"].max().date()),
                     "rows": int(len(df)), "securities": int(df["ticker"].nunique()), "qualityEligibleShare": round(float(q.mean()), 4),
                     "qualityEligibleByYear": df.assign(q=q).groupby("year")["q"].mean().round(4).to_dict(),
                     "priceEnd": str(sessions[-1].date())},
        "terminatedInPricePanel": {t: str(d.date()) for t, d in sorted(book_terminal.items())},
        "labels": lab,
        "featureLayers": {k: len(v) for k, v in layers.items()},
        "featuresExcludedBelowCoverage": sorted(c for c in coverage.index if coverage[c] < T.CONFIG["features"]["minimumCoverageToEnter"]),
        "featureCoverageOverall": coverage.round(4).to_dict(),
        "firstYearWithCoverageAtLeast50pct": first_cov,
        "coverageByYear": {c: by_year[c].to_dict() for c in feats},
        "notes": [
            "Korean DART accounting is dark 2013-2015 and partial in 2016-2017; trees see NaN, linear models see the cross-sectional median plus a missing-share indicator.",
            "The 22 audited terminated securities have unresolved terminal consideration; a label whose exit has no close is withheld, and a held terminating name is valued at zero in the primary NAV (lower bound) and at its last close into the ETF in the sensitivity (upper bound).",
            "Trading value is the as-traded close x volume proxy (official KRX ACC_TRDVAL is not in git).",
            "No macro series other than the dated BOK policy rate is used: no vintage-safe Korean macro panel exists in the repository.",
            "US single stocks are excluded (survivorship defect unresolved, alpha-opportunity-model-v3).",
        ],
    }
    out = HERE / "results"
    out.mkdir(exist_ok=True)
    (out / "data-eligibility.json").write_text(json.dumps(report, indent=1, sort_keys=True, default=str, ensure_ascii=False) + "\n")
    print(json.dumps({k: report[k] for k in ("universe", "featureLayers")}, default=str)[:2000])
    print({k: {kk: vv for kk, vv in v.items() if kk != "byYearLabelled" and kk != "withheldTickers"} for k, v in lab.items()})
    print(np.round(df.groupby("year")[["y126", "y252"]].apply(lambda g: g.notna().mean()), 3))


if __name__ == "__main__":
    main()
