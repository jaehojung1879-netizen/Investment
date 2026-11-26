"""Validate published US source receipts, accounting identities and coverage.

No new strategy, matching choice, hypothesis, or return estimator is introduced.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--private", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=HERE / "results/US")
    a = ap.parse_args(argv)
    public = HERE / "inputs/US"
    manifest = json.loads((public / "spy-source-manifest.json").read_text())
    assert len(manifest["receipts"]) == 28
    assert all(r["httpStatus"] == 200 and r["actualSha256"] == r["source_sha256"] for r in manifest["receipts"])
    assert sha(public / "spy-normalized-holdings.csv.gz") == manifest["normalizedSha256"]
    normalized = pd.read_csv(public / "spy-normalized-holdings.csv.gz", dtype={"cusip": str})
    assert len(normalized) == 14120 and normalized.accession.nunique() == 28
    status = json.loads((a.out / "input-status.json").read_text())
    assert sha(a.private / "close.pkl") == status["priceRepair"]["originalClosePklSha256"]
    assert sha(a.private / "features.pkl") == status["unchangedFeatureSha256"]
    bridge = json.loads((a.out / "prior-350-bridge.json").read_text())
    bridge_max = max(v[k] for h in bridge.values() for v in h.values() for k in ("maxAbsoluteError", "peerMaxAbsoluteError") if k in v)
    assert bridge_max < 1e-12
    with gzip.open(a.out / "funding-book-schedules.json.gz", "rt") as f:
        schedules = json.load(f)
    count, weight_error, minimum = 0, 0., 1.
    for book in schedules.values():
        for weights in book.values():
            count += 1
            weight_error = max(weight_error, abs(sum(weights.values()) - 1))
            minimum = min(minimum, min(weights.values()))
    assert weight_error < 1e-10 and minimum >= 0
    summary = json.loads((a.out / "summary.json").read_text())
    identities = {}
    for h, expected in ((126, 630), (252, 604)):
        f = pd.read_csv(a.out / f"cohorts-{h}.csv.gz", parse_dates=["date"])
        assert f.config.nunique() == 7
        finite = f[["funded", "passive", "active", "legacy", "fundedMinusLegacy"]].notna().all(axis=1)
        assert int(finite.sum()) == expected * 7
        e = float((f.funded - f.passive - f.active).abs().max())
        e2 = float((f.funded - f.legacy - f.fundedMinusLegacy).abs().max())
        assert max(e, e2) < 1e-12
        selection = pd.read_csv(a.out / f"selection-{h}.csv.gz", index_col=0)
        for signal, values in selection.items():
            observed = values.dropna()
            s = summary["horizons"][str(h)]["selection"][signal]
            assert len(observed) == s["n"] and abs(observed.mean() - s["mean"]) < 1e-12
        identities[str(h)] = {"commonCohortsPerBook": expected, "F_minus_ETF_equals_active_plus_B_minus_ETF_maxError": e,
                              "F_minus_legacy_maxError": e2}
    components = pd.read_csv(a.out / "native-component-reconciliation.csv.gz")
    component_error = float(components.error.abs().max())
    assert component_error < 1e-12
    actual = pd.read_csv(a.out / "actual-spy-partial-exposure-audit.csv.gz", parse_dates=["date", "publicFrom"])
    assert actual.config.nunique() == 16 and actual.date.nunique() == 353
    assert (actual.publicFrom < actual.date).all() and actual.reportAgeDays.le(180).all()
    assert not actual.mappingIsPITProved.any() and not actual.actualFullReplicaReturnEstimable.any()
    mega = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "GOOG", "META", "AVGO", "TSLA"]
    mega_error = float((actual[[f"total_{t}_conditional" for t in mega]].sum(axis=1) - actual.totalMegaConditionalWeight).abs().max())
    assert mega_error < 1e-12
    etf = actual[actual.config.eq("ETF")]
    assert etf.conditionalActualSectorL1Difference.abs().max() < 1e-12
    assert (etf.totalMegaConditionalWeight - etf.reportedMegaConditionalBaseWeight).abs().max() < 1e-12
    result = {"status": "VALIDATED_WITH_EXPLICIT_SOURCE_LIMITS", "prior350MaximumEndpointError": bridge_max,
              "fundingBooksChecked": count, "maximumWeightSumError": weight_error, "minimumLongOnlyWeight": minimum,
              "accountingIdentities": identities, "maximumComponentReconciliationError": component_error,
              "actualPartialWeeks": 353, "actualFullReplicaWeeks": 0, "actualPartialConfigs": 16,
              "actualPartialMaximumMegaSumError": mega_error,
              "sourceAndCodeSha256": {str(p.relative_to(HERE)): sha(p) for p in sorted(public.glob("*")) if p.is_file()},
              "limitations": ["Current CUSIP mapping is conditional, not dated identity proof", "Proxy cap subset is not full actual SPY replication",
                              "Original feature freshness, issuer linkage and price-history admission limits retained", "Past data already examined; no prospective validation claimed"]}
    for p in sorted(HERE.glob("us*.py")):
        result["sourceAndCodeSha256"][p.name] = sha(p)
    (a.out / "us-validation.json").write_text(json.dumps(result, indent=1, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k not in ("sourceAndCodeSha256", "limitations")}))


if __name__ == "__main__":
    main()
