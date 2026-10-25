"""Quantify source-only coverage and missingness; no return/model inputs."""
from collections import Counter, defaultdict
import gzip
import json
from pathlib import Path

from . import features as F
from . import pit_filing_evidence as E


def decompose(cohorts, rows, acquisition):
    by_date = {c["signal"]: c for c in cohorts}
    priority = {r["receipt"] for r in acquisition["rows"]}
    acquired = {r["receipt"] for r in acquisition["rows"] if r["status"] == "ACQUIRED_UNVERIFIED_ORIGINAL_XBRL_ZIP"}
    denominators = sum(c["expectedCount"] for c in cohorts)
    result = {}
    for signal in F.SIGNALS:
        bins, taxonomy_years = Counter(), defaultdict(Counter)
        verified = 0
        for row in rows:
            s = row["signals"][signal]
            verified += s["originalFinancialFactsMatched"]
            for reason in s["reasons"]:
                if reason.startswith("CONCEPT_BASIS_CHANGED:"):
                    taxonomy_years[row["signal"][:4]][reason] += 1
            c = by_date[row["signal"]]
            needed = {n for leg in row["filingReceipts"] if leg for n in leg}
            if c["reasons"]:
                reason = "MEMBERSHIP_SNAPSHOT_BLOCKED"
            elif row["endedBySignal"]:
                reason = "IDENTITY_ENDED_BY_SIGNAL"
            elif row["tradingStatus"] != "OBSERVED_TRADABLE_SIGNAL_BAR":
                reason = "SIGNAL_BAR_MISSING_OR_NONTRADABLE"
            elif not s["inputReadable"]:
                reason = "RAW_ANNUAL_INPUT_UNREADABLE_OR_INCOMPARABLE"
            elif not row["originalMainPairMatched"]:
                reason = "ORIGINAL_RECEIPT_OR_MAIN_PAIR_NOT_MATCHED"
            elif not row["datedIdentityMatched"]:
                reason = "DATED_ISSUER_OR_NAME_UNRESOLVED"
            elif not row["industryIssuerMatched"]:
                reason = "DATED_INDUSTRY_ISSUER_UNRESOLVED"
            elif not needed <= acquired:
                reason = ("PRIORITY_ORIGINAL_PACKAGES_NOT_ACQUIRED" if needed <= priority
                          else "OTHER_ORIGINAL_PACKAGES_NOT_ACQUIRED")
            elif not s["originalFinancialFactsMatched"]:
                reason = "ORIGINAL_FACT_CONTEXT_UNIT_VINTAGE_OR_VALUE_NOT_VERIFIED"
            elif not s["fiscalWindowsComparable"]:
                reason = "ORIGINAL_FISCAL_WINDOWS_NOT_COMPARABLE"
            elif not s["legacyFreshnessReferencePassed"]:
                reason = "OUTSIDE_LEGACY_550_DIAGNOSTIC_REFERENCE"
            elif row["fiscalAgePolicyStatus"] != "SYNTHETIC_TEST_POLICY_ONLY":
                reason = "SCIENTIFIC_FISCAL_AGE_POLICY_PENDING"
            else:
                reason = "SYNTHETIC_COMPLETE_NOT_REAL_EXECUTION_PERMISSION"
            bins[reason] += 1
        slots = sum(len(c["missingRankSlots"]) for c in cohorts)
        bins["UNIDENTIFIED_MEMBERSHIP_RANK_SLOTS"] += slots
        if sum(bins.values()) != denominators:
            raise ValueError("EXCLUSIVE_REASON_PARTITION_LOST_DENOMINATOR")
        result[signal] = {"denominator": denominators, "originalFinancialFactsVerifiedPairs": verified,
                          "originalFinancialFactsCoverage": verified / denominators if denominators else None,
                          "researchEligibleObservations": sum(r["signals"][signal]["inputAdmitted"] for r in rows),
                          "exclusiveFirstUnresolvedStage": dict(sorted(bins.items())),
                          "taxonomyChangeReasonsBySignalYearNonexclusive": {y: dict(sorted(v.items())) for y, v in sorted(taxonomy_years.items())}}
    return {"status": "SOURCE_QUALITY_ONLY_NOT_ALPHA_EVIDENCE", "fixedOriginalTargets": len(priority),
            "originalPackagesAcquiredUnverified": len(acquired), "acquisitionStatusCounts": acquisition["statusCounts"],
            "publicReceiptRequestsAttempted": acquisition["publicRequestsAttempted"],
            "originalFiscalYearsInTargetRegistry": dict(sorted(Counter(str(r["fiscalYear"]) for r in acquisition["rows"]).items())),
            "originalTargetIssuers": len({r["corpCode"] for r in acquisition["rows"]}),
            "signals": result, "historicalReturnLabelsRead": 0, "historicalModelFits": 0,
            "taxonomyVerdict": "UNRESOLVED_UNTIL_ORIGINAL_FACT_AND_TAXONOMY_EVIDENCE; no prefix-only economic equivalence assumed",
            "partitionMeaning": "Fixed diagnostic first-failure order, NOT sample exclusion. All nonexclusive reasons remain in measurement coverage."}


def write_report(measurement, acquisition, output):
    measurement, acquisition, output = Path(measurement), Path(acquisition), Path(output)
    if output.exists():
        raise ValueError("PRESERVE_PREVIOUS_SOURCE_QUALITY_REPORT")
    from .pit_join import verify_measurement
    verify_measurement(measurement)  # never bypass intended-cohort/byte receipt validation
    coverage = json.loads((measurement / "coverage.json").read_text())
    cohorts = [json.loads(x) for x in gzip.decompress((measurement / "cohorts.jsonl.gz").read_bytes()).splitlines()]
    rows = [json.loads(x) for x in gzip.decompress((measurement / "rows.jsonl.gz").read_bytes()).splitlines()]
    manifest = json.loads((acquisition / "manifest.json").read_text())
    report = decompose(cohorts, rows, manifest)
    report["sourceReceipts"] = {"measurementCoverageSha256": E.sha((measurement / "coverage.json").read_bytes()),
                                "acquisitionManifestSha256": E.sha((acquisition / "manifest.json").read_bytes()),
                                "codeSha256": E.sha(Path(__file__).read_bytes())}
    baseline_path = Path(__file__).parent / "pit_measurement_v1/coverage.json"
    baseline = json.loads(baseline_path.read_text())
    report["sourceReceipts"]["baselineCoverageSha256"] = E.sha(baseline_path.read_bytes())
    report["baselineOriginalFactsVerified"] = {s: baseline["coverage"]["signals"][s]["originalFinancialFactsMatched"] for s in F.SIGNALS}
    report["verifiedOriginalFactsImprovement"] = {s: report["signals"][s]["originalFinancialFactsVerifiedPairs"]
                                               - report["baselineOriginalFactsVerified"][s] for s in F.SIGNALS}
    if coverage["coverage"]["expectedMemberDates"] != report["signals"][F.SIGNALS[0]]["denominator"]:
        raise ValueError("SOURCE_QUALITY_AND_MEASUREMENT_DENOMINATORS_DIFFER")
    output.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    return report
