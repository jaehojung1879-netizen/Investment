"""Quantify source-only coverage and missingness; no return/model inputs."""
from collections import Counter, defaultdict
import gzip
import json
from pathlib import Path

from . import features as F
from . import pit_filing_evidence as E

FIXED_PLAN_SHA256 = "2c73067ced7c59a2b23a693b5db6aca37f45d69c478c2f789df877126f738766"
ACQUISITION_STATUSES = frozenset({
    "NOT_ATTEMPTED_ENVIRONMENT_NETWORK_BLOCKED", "NOT_ATTEMPTED_AFTER_TRANSPORT_FAILURE",
    "TRANSPORT_ACCESS_FAILURE_NOT_SOURCE_ABSENCE", "SOURCE_ATTACHMENT_UNRESOLVED",
    "ACQUIRED_UNVERIFIED_ORIGINAL_XBRL_ZIP",
})


def _bound_acquisition(coverage, rows, directory, api_receipt=None):
    """Bind one measured input run to its exact fixed-68 acquisition and objects.

    Hashes identify the producer's retained evidence; they are not source
    signatures or financial-fact approval. The existing package reader still
    enforces the original public main/page/attachment provenance.
    """
    if api_receipt is not None:
        return _bound_api_acquisition(coverage, rows, directory, api_receipt)
    from . import portable_collection as P
    from . import xbrl_recovery as R

    manifest_path = directory / "manifest.json"
    raw = manifest_path.read_bytes()
    manifest_sha = E.sha(raw)
    if coverage.get("originalRecoveryManifestSha256") != manifest_sha:
        raise ValueError("MEASUREMENT_ACQUISITION_MANIFEST_MISMATCH")
    plan_path = P.HERE / "xbrl_recovery_v2/portable-plan.json.gz"
    if E.sha(plan_path.read_bytes()) != FIXED_PLAN_SHA256:
        raise ValueError("FIXED_68_PORTABLE_PLAN_CHANGED")
    targets = {t["receipt"]: {k: v for k, v in t.items() if k != "mainRaw"}
               for t in P.validate_plan(P.read_plan(plan_path))}
    manifest = json.loads(raw)
    if (not isinstance(manifest, dict)
            or manifest.get("status") != "ACQUISITION_MEASURED_NOT_SOURCE_APPROVAL"
            or type(manifest.get("fixedReceipts")) is not int or manifest["fixedReceipts"] != len(targets)
            or type(manifest.get("newHistoricalLabelsRead")) is not int or manifest["newHistoricalLabelsRead"] != 0
            or manifest.get("demandSha256") != E.sha(R.DEMAND.read_bytes())
            or manifest.get("apiKeyRequiredForThisPublicRoute") is not False):
        raise ValueError("FIXED_68_ACQUISITION_IDENTITY_MISMATCH")
    records = manifest.get("rows")
    if not isinstance(records, list) or len(records) != len(targets):
        raise ValueError("FIXED_68_ACQUISITION_PARTITION_INCOMPLETE")
    seen, counts = set(), Counter()
    for row in records:
        if not isinstance(row, dict) or row.get("receipt") not in targets:
            raise ValueError("ACQUISITION_RECEIPT_NOT_IN_FIXED_PLAN")
        receipt, status = row["receipt"], row.get("status")
        if receipt in seen:
            raise ValueError("DUPLICATE_ACQUISITION_RECEIPT")
        if status not in ACQUISITION_STATUSES:
            raise ValueError("UNKNOWN_ACQUISITION_STATUS")
        seen.add(receipt)
        counts[status] += 1
        expected = targets[receipt]
        # Successful collection replaces the main URL with the exact attachment
        # URL; the unchanged package reader verifies that receipt/dcm linkage.
        keys = set(expected) - ({"url"} if status == "ACQUIRED_UNVERIFIED_ORIGINAL_XBRL_ZIP" else set())
        if F.digest({k: row.get(k) for k in keys}) != F.digest({k: expected[k] for k in keys}):
            raise ValueError("ACQUISITION_TARGET_METADATA_MISMATCH")
    declared = manifest.get("statusCounts")
    calls = manifest.get("publicRequestsAttempted")
    if (not isinstance(declared, dict) or any(type(v) is not int or v < 0 for v in declared.values())
            or declared != dict(counts)):
        raise ValueError("ACQUISITION_STATUS_COUNTS_MISMATCH")
    if type(calls) is not int or not 0 <= calls <= 2 * len(targets):
        raise ValueError("INVALID_ACQUISITION_REQUEST_COUNT")
    try:
        packages = R.load_packages(directory)
    except (KeyError, TypeError, OSError) as exc:
        raise ValueError("ACQUIRED_PACKAGE_PROVENANCE_UNVERIFIED") from exc
    if manifest_path.read_bytes() != raw:
        raise ValueError("ACQUISITION_CHANGED_DURING_VERIFICATION")
    _verify_package_bindings(rows, packages)
    return manifest, manifest_sha



def _verify_package_bindings(rows, packages):
    for row in rows:
        for detail in row["signals"].values():
            digests = detail["originalFinancialSourceDigests"]
            if len(digests) != 2 or len(row["filingReceipts"]) != 2:
                raise ValueError("VERIFIED_FINANCIAL_LEG_SCHEMA_MISMATCH")
            for receipts, sha in zip(row["filingReceipts"], digests):
                if sha is None:
                    continue
                if (not receipts or len(receipts) != 1 or receipts[0] not in packages
                        or sha != packages[receipts[0]]["sha256"]):
                    raise ValueError("VERIFIED_FINANCIAL_LEG_ACQUISITION_MISMATCH")
            if detail["originalFinancialFactsMatched"] and any(sha is None for sha in digests):
                raise ValueError("VERIFIED_FINANCIAL_PAIR_SOURCE_MISSING")


def _bound_api_acquisition(coverage, rows, directory, receipt):
    from . import opendart_recovery as O
    packages, audit = O.load_acquisition(directory, receipt)
    if (coverage.get('originalRecoveryManifestSha256') != audit['acquisitionManifestSha256']
            or coverage.get('originalRecoveryReceiptSha256') != audit['receiptSha256']
            or coverage.get('originalRecoveryRoute') != O.ROUTE):
        raise ValueError('MEASUREMENT_API_ACQUISITION_BINDING_MISMATCH')
    _verify_package_bindings(rows, packages)
    targets = O._targets(O.PLAN)
    # Normalize only verified retained packages for the same reason partition.
    # Route and API request records remain separate from public-popup requests.
    manifest = {'rows': [{**{k: v for k, v in t.items() if k != 'mainRaw'},
                          'status': 'ACQUIRED_UNVERIFIED_ORIGINAL_XBRL_ZIP'} for t in targets],
                'statusCounts': {'ACQUIRED_UNVERIFIED_ORIGINAL_XBRL_ZIP': len(packages)},
                'publicRequestsAttempted': 0, 'apiRequestsRecorded': len(packages),
                'route': O.ROUTE}
    return manifest, audit['acquisitionManifestSha256']


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


def write_report(measurement, acquisition, output, *, api_receipt=None):
    measurement, acquisition, output = Path(measurement), Path(acquisition), Path(output)
    if output.exists():
        raise ValueError("PRESERVE_PREVIOUS_SOURCE_QUALITY_REPORT")
    from .pit_join import verify_measurement
    verify_measurement(measurement)  # never bypass intended-cohort/byte receipt validation
    coverage = json.loads((measurement / "coverage.json").read_text())
    cohorts = [json.loads(x) for x in gzip.decompress((measurement / "cohorts.jsonl.gz").read_bytes()).splitlines()]
    rows = [json.loads(x) for x in gzip.decompress((measurement / "rows.jsonl.gz").read_bytes()).splitlines()]
    manifest, manifest_sha = _bound_acquisition(coverage, rows, acquisition, api_receipt)
    report = decompose(cohorts, rows, manifest)
    if api_receipt is not None:
        report["acquisitionRoute"] = manifest["route"]
        report["apiRequestsRecorded"] = manifest["apiRequestsRecorded"]
        report["independentAcquisitionReceiptSha256"] = coverage["originalRecoveryReceiptSha256"]
    report["sourceReceipts"] = {"measurementCoverageSha256": E.sha((measurement / "coverage.json").read_bytes()),
                                "acquisitionManifestSha256": manifest_sha,
                                "fixedPortablePlanSha256": FIXED_PLAN_SHA256,
                                "codeSha256": E.sha(Path(__file__).read_bytes())}
    baseline_path = Path(__file__).parent / "pit_measurement_v1/coverage.json"
    baseline = json.loads(baseline_path.read_text())
    report["sourceReceipts"]["baselineCoverageSha256"] = E.sha(baseline_path.read_bytes())
    report["baselineOriginalFactsVerified"] = {s: baseline["coverage"]["signals"][s]["originalFinancialFactsMatched"] for s in F.SIGNALS}
    report["verifiedOriginalFactsImprovement"] = {s: report["signals"][s]["originalFinancialFactsVerifiedPairs"]
                                               - report["baselineOriginalFactsVerified"][s] for s in F.SIGNALS}
    if coverage["coverage"]["expectedMemberDates"] != report["signals"][F.SIGNALS[0]]["denominator"]:
        raise ValueError("SOURCE_QUALITY_AND_MEASUREMENT_DENOMINATORS_DIFFER")
    with output.open("x") as stream:
        stream.write(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    return report
