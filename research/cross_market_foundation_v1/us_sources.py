"""Outcome-free US source inventory and dated metadata adapters.

Reuses the existing candidate parser/admission rules. No HTTP client, research
runner, price-return calculation, source revision or sealed-result writer lives
here. Git reads disable lazy fetch: absent local bytes remain explicitly absent.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
from zoneinfo import ZoneInfo

from pipeline.replay_calendar import sessions as exchange_sessions
from pipeline.us_departed_dataset_admission import filing_visible
from pipeline.us_departed_price_recovery import canonical, parse_csv

MAIN = "37f8cbf6b1c066f6b3c65235953648d17ebf2f69"
PR316 = "86c5983ffba643a58d9eba84a05dc60f4d8e9e6a"
PR287 = "9a10baef600078c132b6942e83f72b587cf0c581"
REPLAY = "1bf68f59cffa20239977e2cfaa0f35a07d0ec884"
STATES = {"READY", "PARTIAL", "SOURCE_BLOCKED", "RIGHTS_BLOCKED", "UNDERPOWERED"}
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
MAX_PAYLOAD_BYTES = 16 * 1024 * 1024
MAX_INFLATED_BYTES = 64 * 1024 * 1024


def verify_payload(raw: bytes, expected_sha256: str, expected_bytes: int | None = None) -> dict:
    """Verify retained bytes; a digest appearing in metadata alone is insufficient."""
    if not isinstance(raw, bytes) or not HEX64.fullmatch(expected_sha256):
        raise ValueError("INVALID_PAYLOAD_OR_HASH")
    if len(raw) > MAX_PAYLOAD_BYTES:
        raise ValueError("PAYLOAD_BYTE_BUDGET")
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("PAYLOAD_HASH_MISMATCH")
    if expected_bytes is not None and len(raw) != expected_bytes:
        raise ValueError("PAYLOAD_SIZE_MISMATCH")
    return {"sha256": expected_sha256, "bytes": len(raw), "payloadVerified": True}


def _inflate(raw: bytes) -> bytes:
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
        value = stream.read(MAX_INFLATED_BYTES + 1)
    if len(value) > MAX_INFLATED_BYTES:
        raise ValueError("INFLATED_BYTE_BUDGET")
    return value


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "--no-replace-objects", "-c", "remote.origin.promisor=false", *args],
        cwd=repo, env={**os.environ, "GIT_NO_LAZY_FETCH": "1"},
        capture_output=True, timeout=30, check=False,
    )


def git_object_receipt(repo: Path, blob: str, *, expected_sha256: str | None = None,
                       logical_sha256: str | None = None) -> dict:
    """Inspect already-local bytes only. This never fetches a dangling object."""
    if not HEX40.fullmatch(blob):
        raise ValueError("INVALID_GIT_BLOB")
    result = {"gitBlob": blob, "payloadState": "LOCAL_OBJECT_UNAVAILABLE",
              "reuseRights": "UNVERIFIED", "researchAdmission": False}
    size = _git(repo, "cat-file", "-s", blob)
    if size.returncode:
        return result
    if int(size.stdout) > MAX_PAYLOAD_BYTES:
        return {**result, "payloadState": "PAYLOAD_BYTE_BUDGET"}
    fetched = _git(repo, "cat-file", "blob", blob)
    if fetched.returncode:
        return result
    raw = fetched.stdout
    observed = hashlib.sha256(raw).hexdigest()
    verify_payload(raw, expected_sha256 or observed)
    git_hash = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    if git_hash != blob:
        raise ValueError("GIT_BLOB_HASH_MISMATCH")
    result.update(payloadState="EXACT_LOCAL_BYTES_VERIFIED", bytes=len(raw), sha256=observed)
    if logical_sha256 is not None:
        logical = _inflate(raw)
        if hashlib.sha256(logical).hexdigest() != logical_sha256:
            raise ValueError("LOGICAL_PAYLOAD_HASH_MISMATCH")
        result.update(logicalSha256=logical_sha256, logicalBytes=len(logical))
    return result


def _pinned(repo: Path, commit: str, path: str) -> tuple[bytes, dict]:
    if not HEX40.fullmatch(commit) or path.startswith("/") or ".." in Path(path).parts:
        raise ValueError("UNPINNED_GIT_SOURCE")
    obj = _git(repo, "rev-parse", f"{commit}:{path}")
    blob = obj.stdout.decode().strip()
    if obj.returncode or not HEX40.fullmatch(blob):
        raise ValueError("PINNED_GIT_PATH_UNAVAILABLE:" + path)
    receipt = git_object_receipt(repo, blob)
    if receipt["payloadState"] != "EXACT_LOCAL_BYTES_VERIFIED":
        raise ValueError("PINNED_PAYLOAD_UNAVAILABLE:" + path)
    receipt.update(sourceCommit=commit, path=path, gitTreePathVerified=True)
    return _git(repo, "cat-file", "blob", blob).stdout, receipt


def classify_departed(recovery: dict, admission: dict, *, expected_count: int = 212) -> dict:
    """Join audit identifier grain, preserving all independent failures per row."""
    left, right = recovery["inventory"], admission["identifiers"]
    def indexed(rows, key):
        result = {x[key]: x for x in rows}
        if len(result) != len(rows):
            raise ValueError("DUPLICATE_AUDIT_IDENTIFIER")
        return result
    a, b = indexed(left, "auditIdentifier"), indexed(right, "ticker")
    if set(a) != set(b) or len(a) != expected_count:
        raise ValueError("DEPARTED_COHORT_MISMATCH")
    if len({x["securityId"] for x in left}) != len(left):
        raise ValueError("DUPLICATE_SECURITY_AUDIT_ID")
    rows = []
    for ticker in sorted(a):
        x, y = a[ticker], b[ticker]
        if x["securityId"] != y["securityId"]:
            raise ValueError("SECURITY_ID_JOIN_MISMATCH")
        expected = x["expectedPricingWindow"]["sessions"]
        if x["coveredSessions"] + x["missingSessions"] != expected:
            raise ValueError("MEMBERSHIP_SESSION_COUNT_MISMATCH")
        rows.append({
            "auditIdentifier": ticker, "securityAuditId": x["securityId"],
            "idKind": x["securityIdKind"], "sealedIdentityCategory": x["sealedIdentityCategory"],
            "historicalIssuerNames": x["historicalIssuerNames"],
            "historicalCiksReportedNotBackfilled": y["historicalCiksReportedNotBackfilled"],
            "symbolReuseFlag": x["symbolReuseFlagFromSealedAudit"], "identityHold": x["identityHold"],
            "priceIssuerAndShareClass": "SOURCE_BLOCKED",
            "datedIssuerCikEvidenceRows": len(y["datedMemberCikEvidence"]),
            "membershipIntervals": x["membershipIntervals"],
            "expectedPricingWindow": x["expectedPricingWindow"],
            "historicalCandidateCoverage": x["qualifiedPriceCoverage"],
            "candidateSessionsPreviouslyMeasured": x["coveredSessions"],
            "missingCandidateSessionsPreviouslyMeasured": x["missingSessions"],
            "selectedPublisher": y["selectedPublisher"],
            "candidateSources": sorted({r["source"] for r in x["candidateSources"]}),
            "candidateRawPayloadInCurrentCheckout": False,
            "originalShareBasisAndCorporateActions": x["corporateActionState"],
            "terminalConsideration": x["terminalConsideration"],
            "sourceUseRights": "UNVERIFIED", "durablePrivateStorage": "NOT_CONFIRMED",
            "filingToPriceIssuerLink": y["filingToPriceIssuerLinkStatus"],
            "filingRecordsPreviouslyMeasured": y["filingRecords"],
            "endpointExistencePreviouslyMeasured": y["endpointCounts"],
            "researchReadiness": "SOURCE_BLOCKED", "admittedSessions": 0,
            "blockingCodes": ["PRICE_SECURITY_IDENTITY_UNPROVEN", "AS_TRADED_BASIS_UNPROVEN",
                              "CORPORATE_ACTION_LINEAGE_UNRESOLVED", "TERMINAL_CONSIDERATION_UNRESOLVED",
                              "RAW_CANDIDATE_PAYLOAD_NOT_RETAINED_HERE", "REUSE_RIGHTS_UNVERIFIED"],
        })
    return {
        "schema": "CROSS_MARKET_US_DEPARTED_AUDIT_V1", "grain": "SEALED_AUDIT_IDENTIFIER_NOT_PERMANENT_SECURITY_ID",
        "rows": rows,
        "summary": {"identifiers": len(rows),
                    "identityCategories": dict(sorted(Counter(r["sealedIdentityCategory"] for r in rows).items())),
                    "historicalCandidateCoverage": dict(sorted(Counter(r["historicalCandidateCoverage"] for r in rows).items())),
                    "originalMissingSessions": sum(r["expectedPricingWindow"]["sessions"] for r in rows),
                    "candidateSessionsPreviouslyMeasured": sum(r["candidateSessionsPreviouslyMeasured"] for r in rows),
                    "remainingCandidateMissingPreviouslyMeasured": sum(r["missingCandidateSessionsPreviouslyMeasured"] for r in rows),
                    "corporateActionUnresolvedIdentifiers": len(rows), "terminalTriageUnresolvedIdentifiers": len(rows),
                    "identityHolds": sum(r["identityHold"] for r in rows), "admittedSessions": 0},
        "interpretation": "212 audit identifiers are not 212 confirmed delistings. Candidate counts are historical metadata, not newly reproduced raw prices.",
        "outcomeReads": 0, "outcomeExecutionAuthorized": False,
    }


def _visible_day(value: str) -> str:
    text = str(value)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?)?", text):
        raise ValueError("INVALID_PUBLICATION_TIMESTAMP")
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    days = [parsed.date().isoformat()]
    if parsed.tzinfo:
        days.append(parsed.astimezone(ZoneInfo("America/New_York")).date().isoformat())
    return max(days)


def build_filing_metadata_inputs(raw: bytes, expected_sha256: str, *, signal_day: str,
                                 member_cik: str, sessions: list[str], compressed: bool = False) -> dict:
    """Checksum-verified metadata-only adapter; cannot certify price/share-class linkage.

    Both dates are validated fully, source and NY dates conservatively withheld.
    No same-day publication, weekend evaluation, future CIK backfill or feature
    values are emitted. Caller supplies the *dated* membership CIK, never today's.
    """
    receipt = verify_payload(raw, expected_sha256)
    if sessions != sorted(set(sessions)) or any(date.fromisoformat(d).isoformat() != d for d in sessions):
        raise ValueError("INVALID_SESSION_CALENDAR")
    if signal_day not in sessions:
        raise ValueError("SIGNAL_NOT_A_SESSION")
    actual_sessions = set(exchange_sessions(sessions[0], sessions[-1], "US").strftime("%Y-%m-%d"))
    if not set(sessions).issubset(actual_sessions):
        raise ValueError("NON_US_TRADING_SESSION")
    if not re.fullmatch(r"\d{1,10}", str(member_cik)) or int(member_cik) == 0:
        raise ValueError("INVALID_DATED_MEMBER_CIK")
    records = [json.loads(line) for line in (_inflate(raw) if compressed else raw).splitlines() if line.strip()]
    rows, seen = [], set()
    for record in records:
        identity = record.get("id") or (str(record.get("ticker")) + "|" + str(record.get("accession")))
        if identity in seen:
            raise ValueError("DUPLICATE_FILING_ID")
        seen.add(identity)
        status = "WITHHELD"
        reasons = []
        try:
            available = _visible_day(record.get("availableFrom", ""))
            accepted = _visible_day(record.get("acceptedDate", ""))
            observed_cik = str(record.get("cik", ""))
            if not re.fullmatch(r"\d{1,10}", observed_cik) or int(observed_cik) == 0:
                raise ValueError("INVALID_FILING_CIK")
            fiscal = record.get("fiscalYear")
            if isinstance(fiscal, bool) or not isinstance(fiscal, int) or not 1990 <= fiscal <= 2100:
                raise ValueError("FISCAL_YEAR_UNPROVEN")
            conservative = {**record, "availableFrom": available, "acceptedDate": accepted}
            if filing_visible(conservative, signal_day, member_cik):
                status = "PIT_METADATA_ONLY"
            else:
                reasons.append("NOT_YET_VISIBLE_OR_DATED_CIK_MISMATCH")
        except (ValueError, TypeError) as exc:
            reasons.append(str(exc))
        rows.append({"id": identity, "ticker": record.get("ticker"), "cik": record.get("cik"),
                     "availableFrom": record.get("availableFrom"), "acceptedDate": record.get("acceptedDate"),
                     "fiscalYear": record.get("fiscalYear"), "status": status, "reasons": reasons,
                     "priceSecurityLinkVerified": False})
    return {"schema": "US_DATED_FILING_METADATA_INPUT_V1", "source": receipt, "signalDay": signal_day,
            "datedMemberCik": str(member_cik), "records": sorted(rows, key=lambda r: r["id"]),
            "researchOutcomeAdmission": False, "readsForwardPrices": False}


def candidate_price_dates(raw: bytes, expected_sha256: str, sessions: list[str]) -> dict:
    """Existing parser, without emitting prices or upgrading observations to admission."""
    receipt = verify_payload(raw, expected_sha256)
    rows, quality = parse_csv(raw, set(sessions))
    return {"source": receipt, "observedSessions": sorted(rows), "quality": quality,
            "researchOutcomeAdmission": False, "terminalPayoff": None}


def validate_us_currency_basis(*, stock_currency: str, benchmark_currency: str,
                               investor_currency: str, signal_day: str,
                               fx_observation: dict | None = None) -> dict:
    """Admission contract only: never turn a USD economic return into a KRW one.

    FX is a separately dated source, not a risk-free return or equity payoff.
    Terminal settlements/dividends must separately pass their native USD basis.
    """
    if stock_currency != "USD" or benchmark_currency != "USD":
        raise ValueError("US_STOCK_ETF_NATIVE_CURRENCY_MISMATCH")
    if date.fromisoformat(signal_day).isoformat() != signal_day:
        raise ValueError("INVALID_SIGNAL_DATE")
    if investor_currency == "USD":
        if fx_observation is not None:
            raise ValueError("USD_ECONOMIC_COMPARISON_MUST_NOT_EMBED_FX")
        return {"nativeCurrency": "USD", "investorCurrency": "USD", "fxEmbedded": False}
    if investor_currency != "KRW":
        raise ValueError("UNSUPPORTED_INVESTOR_CURRENCY")
    if not isinstance(fx_observation, dict) or fx_observation.get("quote") != "KRW_PER_USD":
        raise ValueError("DATED_KRW_PER_USD_FX_REQUIRED")
    available = _visible_day(fx_observation.get("availableFrom", ""))
    observed = date.fromisoformat(str(fx_observation.get("observationDate", ""))).isoformat()
    if observed > signal_day or available >= signal_day:
        raise ValueError("FX_NOT_AVAILABLE_AT_SIGNAL")
    if observed > available:
        raise ValueError("FX_AVAILABILITY_PRECEDES_OBSERVATION")
    source = fx_observation.get("source")
    sha = fx_observation.get("sha256", "")
    if not source or not isinstance(sha, str) or not HEX64.fullmatch(sha):
        raise ValueError("FX_SOURCE_RECEIPT_REQUIRED")
    return {"nativeCurrency": "USD", "investorCurrency": "KRW", "fxEmbedded": True,
            "fxQuote": "KRW_PER_USD", "fxObservationDate": observed,
            "fxAvailabilityDay": available, "fxSource": source, "fxSourceSha256": sha,
            "usdAndKrwResultsMustRemainSeparate": True}


def research_readiness(facts: dict) -> dict:
    """Explicit construction readiness, separate from empirical execution approval."""
    benchmark = facts.get("benchmarkBytesVerified") is True
    filings = facts.get("filingBytesVerified") is True
    header = facts.get("singleSecHeaderRecovered") is True
    rows = [
        ("market_risk_exposure", "PARTIAL" if benchmark else "SOURCE_BLOCKED",
         ["BENCHMARK_COMMON_RETURN_BASIS_REVIEW", "BENCHMARK_REUSE_RIGHTS_UNVERIFIED", "NO_NEW_EXECUTION_APPROVAL"]),
        ("industry_selection", "PARTIAL" if header else "SOURCE_BLOCKED",
         ["DATED_SIC_PANEL_INCOMPLETE", "HISTORICAL_SECURITY_CLASS_LINK_MISSING", "NO_INDUSTRY_OUTCOMES_AUTHORIZED"]),
        ("direct_stock_selection", "SOURCE_BLOCKED",
         ["DEPARTED_212_NOT_ADMITTED", "PRICE_SECURITY_IDENTITY_UNPROVEN", "CORPORATE_ACTIONS_TERMINAL_UNRESOLVED", "REUSE_RIGHTS_UNVERIFIED"]),
        ("earnings_fundamental_changes", "RIGHTS_BLOCKED" if filings else "SOURCE_BLOCKED",
         ["FINNHUB_RETENTION_REUSE_GRANT_UNPROVEN", "PIT_METADATA_NOT_PRICE_SHARE_CLASS_PROOF", "COMMON_TOTAL_RETURN_BASIS_UNRESOLVED"]),
        ("ownership_insider_form4", "SOURCE_BLOCKED",
         ["FULL_FORM4_TRANSACTION_PANEL_NOT_RETAINED", "FILING_DAY_NOT_TRANSACTION_DAY", "POWER_NOT_ASSESSED"]),
        ("portfolio_d_comparison", "PARTIAL" if benchmark else "SOURCE_BLOCKED",
         ["PROSPECTIVE_OPERATIONS_SEPARATE_OWNER", "COMMON_STOCK_ETF_TOTAL_RETURN_AND_COSTS", "NO_MATURE_H126_H252_COHORT_CERTIFIED"]),
    ]
    return {"schema": "US_RESEARCH_READINESS_V1", "facts": facts,
            "tracks": [{"track": key, "status": status, "blockingCodes": blocks,
                        "empiricalReady": False, "newOutcomeExecutionAuthorized": False}
                       for key, status, blocks in rows],
            "statusMeaning": "PARTIAL means bounded metadata/input work is possible, never permission or full historical research readiness.",
            "usdVsKrw": {"localInvestmentReturn": "USD_TOTAL_RETURN",
                         "krwInvestorReturn": "(1+USD_TOTAL_RETURN)*(USD_KRW_END/USD_KRW_START)-1",
                         "fxQuote": "KRW_PER_USD", "mixingAllowed": False},
            "samplePower": "NOT_ASSESSED_NO_ADMITTED_COHORT"}


def generate(repo: Path, output: Path) -> dict:
    """Reproduce inventory locally; only source metadata and byte hashes are inspected."""
    evidence = output / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    receipts = []
    def load(commit, path):
        raw, receipt = _pinned(repo, commit, path)
        receipts.append(receipt)
        return json.loads(raw)
    recovery = load(MAIN, "docs/us-readiness/us-departed-public-price-recovery-v1.json")
    admission = load(MAIN, "docs/us-readiness/us-departed-dataset-admission-audit-v1.json")
    departed = classify_departed(recovery, admission)
    source_audit = load(PR316, "research/alpha_evidence_sprint_v2/evidence/c2-source-inventory.json")
    wid = load(PR287, "docs/winner-inflection-discovery/blocker-review-v3/metadata.json")
    funnel = load(PR287, "docs/winner-inflection-discovery/blocker-review-v3/source-funnel-20261029.json")
    manifest = load(REPLAY, "ledger/historical/replay-v16/inputs.json")
    replay_objects = []
    for record in source_audit["objectsRead"]:
        ref, component, blob = record["ref"], record["component"], record["blob"]
        if not component.startswith(("price/", "benchmark/", "corporate-events/")):
            raise ValueError("UNEXPECTED_SOURCE_OBJECT_SCOPE")
        if ref not in manifest["components"].get(component, []):
            raise ValueError("SOURCE_MANIFEST_REF_MISMATCH")
        path = "ledger/replay-inputs/objects/" + ref + ".json.gz"
        found = _git(repo, "rev-parse", f"{REPLAY}:{path}")
        if found.returncode or found.stdout.decode().strip() != blob:
            raise ValueError("SOURCE_TREE_BLOB_MISMATCH")
        receipt = git_object_receipt(repo, blob, logical_sha256=ref)
        replay_objects.append({**receipt, "sourceCommit": REPLAY, "path": path,
                               "component": component, "gitTreePathVerified": True})
    fundamentals = []
    for item in admission["inputManifest"]["fundamentalsFiles"]:
        raw, receipt = _pinned(repo, admission["inputManifest"]["fundamentalsCommit"], item["path"])
        verify_payload(raw, item["sha256"])
        if receipt["gitBlob"] != item["gitBlob"]:
            raise ValueError("FUNDAMENTALS_TREE_BLOB_MISMATCH")
        fundamentals.append(receipt)
    benchmark_path = "data/research/us-dual-benchmark-v1/spy-qqq-total-return.csv.gz"
    benchmark, benchmark_receipt = _pinned(repo, MAIN, benchmark_path)
    verify_payload(benchmark, source_audit["items"]["9_US_analog"]["benchmark"]["usDualBenchmark"]["sha256"])
    receipts.append(benchmark_receipt)
    for path in ["research_specs/alpha-opportunity-model-v1-us-membership.json.gz",
                 "research_specs/alpha-opportunity-model-v3-us-identity-evidence.json.gz",
                 "docs/us-readiness/us-departed-price-redistribution-audit-v1.json",
                 "candidate_data/us-departed-public-price-v1/manifest.json"]:
        _, receipt = _pinned(repo, MAIN, path)
        receipts.append(receipt)
    header_path = Path(__file__).parent / "evidence/industry-sec-aapl-2023-header.sgml"
    header_verified = False
    if header_path.is_file():
        verify_payload(header_path.read_bytes(), "e4254ad253c7910000c0887662c49540cc78d7403df93e0fb3b968eefee7ed9a", 952)
        header_verified = True
    sample_ref = next(r for r in fundamentals if r["path"].endswith("finnhub-2013.jsonl.gz"))
    first_line = _inflate(_git(repo, "cat-file", "blob", sample_ref["gitBlob"]).stdout).splitlines()[0]
    first_record = json.loads(first_line)
    keys = ("id", "ticker", "accession", "cik", "form", "fiscalYear", "periodEnd", "availableFrom", "acceptedDate")
    projection = {k: first_record[k] for k in keys}
    sample = {"schema": "GENUINE_FILING_METADATA_PROJECTION_V1", "source": sample_ref,
              "originalJsonlLineSha256": hashlib.sha256(first_line).hexdigest(),
              "retainedFields": list(keys), "financialValuesIncluded": False,
              "metadataJsonl": canonical(projection).decode() + "\n"}
    facts = {"benchmarkBytesVerified": True, "filingBytesVerified": bool(fundamentals),
             "singleSecHeaderRecovered": header_verified,
             "secHeaderEvidence": "research/cross_market_foundation_v1/evidence/industry-sec-aapl-2023-header.sgml",
             "departedRawArchivesPresentHere": False, "departedDatasetAdmittedSessions": 0}
    readiness = research_readiness(facts)
    inventory = {
        "schema": "CROSS_MARKET_US_SOURCE_INVENTORY_V1", "sourcePins": {"main": MAIN, "pr316": PR316, "pr287": PR287},
        "publicMetadataAndBenchmark": receipts, "fundamentalsShards": fundamentals,
        "replayObjects": replay_objects,
        "summary": {"replayObjects": len(replay_objects),
                    "replayObjectCompressedBytes": sum(r.get("bytes", 0) for r in replay_objects),
                    "logicalHashesVerified": sum("logicalSha256" in r for r in replay_objects),
                    "fundamentalsShards": len(fundamentals), "outcomeReads": 0, "returnCalculations": 0,
                    "priceSeriesParsedForOutcomes": 0},
        "departedExternalArtifacts": {"raw": recovery["rawCandidateArtifact"], "panel": recovery["candidatePanelRevision"],
                                     "presentInCurrentCheckout": False, "durableOwnerStorageConfirmed": False,
                                     "danglingPriceObjectsRecovered": False},
        "rights": {"vendorInternalResearchReuse": "UNVERIFIED", "rawPublicRedistribution": "NOT_AUTHORIZED_BY_THIS_SPRINT",
                   "codeLicenseDoesNotGrantVendorDataRights": True},
        "existingWidGates": {"rights": wid["rights"]["status"], "identity": wid["identity"]["status"],
                            "returnBasis": wid["returnBasis"]["status"],
                            "spyActionRows": wid["returnBasis"]["spyActionRows"],
                            "fiscalShardReview": funnel["fiscalShardReview"]},
        "limitation": "Hashes prove byte availability, not historical information availability, security identity, vendor reuse rights, or empirical approval.",
    }
    for name, data in [("us-departed-212.json", departed), ("us-source-inventory.json", inventory), ("us-readiness.json", readiness), ("us-filing-metadata-sample.json", sample)]:
        (evidence / name).write_bytes(canonical(data) + b"\n")
    return inventory["summary"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(generate(args.repo.resolve(), args.output.resolve()), sort_keys=True))


if __name__ == "__main__":
    main()
