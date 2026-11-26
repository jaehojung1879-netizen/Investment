"""Verify the frozen source, prospective state and checked-in research artifacts."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / "results"
BASE = "0eceb6f135dd3bd08f35950997d36129bfe67f65"
DESIGN = "47548b1"
PRIOR = ROOT / "research/kr_us_exposure_preserving_v1"
CHECK_DATE_KST = "2026-11-20"


def digest(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def save(path, content):
    path.write_text(json.dumps(content, ensure_ascii=False, allow_nan=False, indent=2) + "\n")


def prospective():
    source = json.loads((PRIOR / "results/prospective-status.json").read_text())
    for path, expected in source["existingFilesSha256"].items():
        assert digest(ROOT / path) == expected, path
    result = dict(source, checkedOnKST=CHECK_DATE_KST, comparisonBase=BASE,
                  existingFilesByteUnchanged=True, newLiveReceipts=0)
    return result


def source_verification():
    design_path = HERE / "DESIGN-ko.md"
    original = subprocess.check_output(["git", "show", f"{DESIGN}:{design_path.relative_to(ROOT)}"], cwd=ROOT)
    assert original == design_path.read_bytes()
    changed = subprocess.check_output(["git", "diff", "--name-only", BASE], cwd=ROOT, text=True).splitlines()
    assert all(p.startswith("research/kr_us_replica_filter_v1/") or
               p.startswith("tests/test_kr_us_replica_filter_") for p in changed), changed
    source_paths = [
        PRIOR / "REPORT-ko.md", PRIOR / "TABLES-ko.md", PRIOR / "results/manifest.json",
        PRIOR / "results/KR/summary.json", PRIOR / "results/US/summary.json",
        PRIOR / "results/US/funded-ledgers.json", PRIOR / "inputs/US/spy-source-manifest.json",
    ]
    return {"base": BASE, "designCommit": DESIGN, "designSHA256": digest(design_path),
            "priorTrackedFilesByteUnchanged": True,
            "sourceSHA256": {str(p.relative_to(ROOT)): digest(p) for p in source_paths}}


def check_identity(error, tolerance=1e-10):
    largest = error.abs().max()
    if pd.isna(largest):
        return None
    assert largest < tolerance, largest
    return float(largest)


def check_us(path, summary):
    from research.kr_us_replica_filter_v1.us import COMPONENTS

    coverage = pd.read_csv(path / "report-coverage.csv.gz", parse_dates=["date", "publicFrom", "holdingAsOf"])
    assert len(coverage) == 654 and coverage.date.is_unique
    published = coverage.loc[coverage.status.eq("LATEST_PUBLIC_LAGGED_REPORT")]
    assert len(published) == summary["reportCoverage"]["decisionWeeks"]
    assert published.publicFrom.lt(published.date).all()
    assert (published.date-published.holdingAsOf).dt.days.le(180).all()
    accounted = published[["knownEquityNetWeight", "unmappedNetWeight",
                           "mappedNoDecisionPriceNetWeight", "mappedPricedNoSectorNetWeight"]].sum(axis=1)
    receipts = {"publishedReportWeeks": len(published),
                "publishedWeightPartitionMaxError": check_identity(accounted-published.reportEquityNetWeight)}
    for h, expected in zip((126, 252), (630, 604), strict=True):
        frame = pd.read_csv(path / f"cohorts-{h}.csv.gz").set_index("date")
        assert len(frame) == 654 and frame.index.is_unique
        assert frame.netExcess.notna().sum() == expected
        gross_factor = (1-summary["buy"]) * (1-summary["sell"])
        checks = {
            "cohortWeeks": expected,
            "priorMaxError": check_identity(frame.netExcess-frame.originalPassive),
            "netGrossMaxError": check_identity(frame.netExcess-gross_factor*frame.grossExcess),
            "fundedPriorMaxError": check_identity(frame.originalPriceConfirmedBridgeError),
            "priceDistributionMaxError": check_identity(frame.grossExcess-frame.yahooPriceOnlyExcess
                                                        -frame.yahooDistributionGap-frame.grossMinusYahooAdjusted),
        }
        attribution = pd.read_csv(path / f"full-contribution-{h}.csv.gz")
        weighted_return = attribution.groupby("date").netExcessContribution.sum()
        assert set(weighted_return.index) == set(frame.netExcess.dropna().index)
        checks["tickerSumMaxError"] = check_identity(weighted_return-frame.netExcess)
        for mode in ("strict", "endpointObserved"):
            bridge = pd.read_csv(path / f"bridge-{mode}-{h}.csv.gz").set_index("date")
            assert bridge.index.equals(frame.index)
            observed = bridge.loc[bridge.status.eq("MEASURED")]
            assert observed[list(COMPONENTS)].notna().all().all()
            n = summary["horizons"][str(h)]["bridge"][mode]["components"]["proxyNetExcess"]["n"]
            assert len(observed) == n
            within = check_identity(observed[list(COMPONENTS)].sum(axis=1)-observed.proxyNetExcess)
            same = check_identity(observed.proxyNetExcess-frame.loc[observed.index, "netExcess"])
            outside = frame.loc[~frame.index.isin(observed.index), "netExcess"].sum()
            together = (observed[list(COMPONENTS)].sum().sum()+outside)/expected
            assert abs(together-frame.netExcess.mean()) < 1e-10
            checks[mode] = {"weeks": len(observed), "componentMaxError": within, "sameDatesMaxError": same}
        receipts[str(h)] = checks
    return receipts


def check_kr(path, summary):
    audit = pd.read_csv(path / "matching-audit.csv.gz")
    measured = audit.loc[audit.reason.eq("MATCHED")]
    assert measured.capRatio.between(.5, 2., inclusive="both").all()
    assert not measured.duplicated(["date", "config", "failTicker"]).any()
    assert not measured.duplicated(["date", "config", "passTicker"]).any()
    candidates = pd.read_csv(path / "candidate-audit.csv.gz")
    for ticker, expected in (("passTicker", "PASS"), ("failTicker", "MEASURED_FAIL")):
        matched = measured[["date", ticker, "industry"]].merge(
            candidates[["date", "ticker", "industry", "status"]], validate="many_to_one",
            left_on=["date", ticker, "industry"], right_on=["date", "ticker", "industry"], how="left")
        assert matched.status.eq(expected).all()
    receipts = {"fixedPairs": len(measured)}
    for h in (126, 252):
        frame = pd.read_csv(path / f"cohorts-{h}.csv.gz")
        assert len(frame) == 454*(1+len(summary["seeds"]))
        complete = frame.loc[frame.status.eq("MEASURED")]
        assert complete[["selection", "replacement", "total"]].notna().all().all()
        assert frame.loc[~frame.status.eq("MEASURED"), "selection"].isna().all()
        maximum = check_identity(complete.selection+complete.replacement-complete.total)
        assets = pd.read_csv(path / f"asset-payoffs-{h}.csv.gz")
        assert not assets.duplicated(["date", "ticker"]).any()
        gross_cost_max = check_identity(assets.gross-assets.cost-assets.net)
        for config, key in (("all_pass", ("whole", "matched20")), (str(summary["seeds"][0]), ("k5", "paired"))):
            expected = summary["horizons"][str(h)][key[0]][key[1]]["selection"]
            result = complete.loc[complete.config.eq(config), "selection"]
            assert len(result) == expected["n"]
            assert abs(result.mean()-expected["mean"]) < 1e-10
        receipts[str(h)] = {"rows": len(frame), "matchedRows": len(complete), "decompositionMaxError": maximum,
                            "assetPayoffRows": len(assets), "grossCostNetMaxError": gross_cost_max}
    return receipts


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    status = prospective()
    save(OUT / "prospective-status.json", status)
    checks = {**source_verification(), "prospectiveFilesVerified": len(status["existingFilesSha256"])}
    checks["markets"] = {}
    for market, check in (("US", check_us), ("KR", check_kr)):
        summary_path = OUT / market / "summary.json"
        if summary_path.is_file():
            raw = json.loads(summary_path.read_text())
            assert set(raw["horizons"]) == {"126", "252"}
            checks["markets"][market] = {"summarySHA256": digest(summary_path), "checks": check(summary_path.parent, raw)}
        else:
            checks["markets"][market] = {"status": "UNAVAILABLE"}
    save(OUT / "verification.json", checks)
    files = [p for p in [*OUT.rglob("*"), *HERE.glob("*.py"), *HERE.glob("*.sh"), HERE / "DESIGN-ko.md"]
             if p.is_file() and p != OUT / "artifact-manifest.json"]
    save(OUT / "artifact-manifest.json", {str(p.relative_to(HERE)): {"sha256": digest(p), "bytes": p.stat().st_size}
                                         for p in sorted(files)})
    print(json.dumps(checks, ensure_ascii=False))


if __name__ == "__main__":
    main()
