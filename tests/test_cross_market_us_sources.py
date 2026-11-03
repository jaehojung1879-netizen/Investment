"""US source infrastructure regressions; genuine metadata, synthetic prices only."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from research.cross_market_foundation_v1 import us_sources as us

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "research/cross_market_foundation_v1/evidence"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def record(**updates):
    return {"id": "synthetic-A|filing-1", "ticker": "SYNTH_A", "cik": "123", "fiscalYear": 2020,
            "accession": "synthetic-filing", "availableFrom": "2020-01-02",
            "acceptedDate": "2020-01-02T20:00:00-05:00", **updates}


def adapt(records, *, signal="2020-01-03", cik="123"):
    raw = b"\n".join(us.canonical(r) for r in records)
    return us.build_filing_metadata_inputs(raw, digest(raw), signal_day=signal, member_cik=cik,
                                           sessions=["2020-01-02", "2020-01-03", "2020-01-06"])


def test_checksum_is_a_payload_gate():
    raw = b"metadata"
    assert us.verify_payload(raw, digest(raw), 8)["payloadVerified"]
    with pytest.raises(ValueError, match="HASH_MISMATCH"):
        us.verify_payload(b"changed", digest(raw))
    with pytest.raises(ValueError, match="SIZE_MISMATCH"):
        us.verify_payload(raw, digest(raw), 0)


def test_real_212_audit_reconciles_grain_and_preserves_all_failures():
    recovery = json.loads((ROOT / "docs/us-readiness/us-departed-public-price-recovery-v1.json").read_text())
    admission = json.loads((ROOT / "docs/us-readiness/us-departed-dataset-admission-audit-v1.json").read_text())
    report = us.classify_departed(recovery, admission)
    summary = report["summary"]
    assert summary["identifiers"] == 212
    assert summary["historicalCandidateCoverage"] == {"FULL": 5, "NONE": 37, "PARTIAL": 170}
    assert summary["originalMissingSessions"] == 256402
    assert summary["candidateSessionsPreviouslyMeasured"] == 186910
    assert summary["remainingCandidateMissingPreviouslyMeasured"] == 69492
    assert summary["identityHolds"] == 8
    assert summary["admittedSessions"] == 0
    assert all(len(r["blockingCodes"]) == 6 for r in report["rows"])
    assert all(r["priceIssuerAndShareClass"] == "SOURCE_BLOCKED" for r in report["rows"])
    assert len({r["securityAuditId"] for r in report["rows"]}) == 212


@pytest.mark.parametrize("mutation,error", [
    ("duplicate", "DUPLICATE_AUDIT_IDENTIFIER"), ("cohort", "DEPARTED_COHORT_MISMATCH"),
    ("security", "SECURITY_ID_JOIN_MISMATCH"), ("count", "MEMBERSHIP_SESSION_COUNT_MISMATCH")])
def test_departed_identity_join_and_counts_fail_closed(mutation, error):
    a = json.loads((ROOT / "docs/us-readiness/us-departed-public-price-recovery-v1.json").read_text())
    b = json.loads((ROOT / "docs/us-readiness/us-departed-dataset-admission-audit-v1.json").read_text())
    if mutation == "duplicate":
        a["inventory"].append(deepcopy(a["inventory"][0]))
    elif mutation == "cohort":
        b["identifiers"].pop()
    elif mutation == "security":
        b["identifiers"][0]["securityId"] = "different"
    else:
        a["inventory"][0]["missingSessions"] += 1
    with pytest.raises(ValueError, match=error):
        us.classify_departed(a, b)


def test_both_dates_same_day_withheld_then_next_session():
    assert adapt([record()], signal="2020-01-02")["records"][0]["status"] == "WITHHELD"
    row = adapt([record()])["records"][0]
    assert row["status"] == "PIT_METADATA_ONLY"
    assert not row["priceSecurityLinkVerified"]


def test_new_york_or_source_day_whichever_later_is_withheld():
    # Thursday source date but Friday NY date: Friday remains unavailable.
    delayed = record(acceptedDate="2020-01-02T23:30:00-10:00")
    assert adapt([delayed])["records"][0]["status"] == "WITHHELD"
    assert adapt([delayed], signal="2020-01-06")["records"][0]["status"] == "PIT_METADATA_ONLY"


@pytest.mark.parametrize("updates", [
    {"acceptedDate": "2020-01-02 99:99:99"}, {"acceptedDate": None},
    {"availableFrom": "2020-01-02junk"}, {"cik": None}, {"cik": "0000000000"},
    {"cik": "4343243243432434"}, {"cik": "456"}, {"fiscalYear": 1215}, {"fiscalYear": True}])
def test_malformed_or_wrong_issuer_metadata_is_retained_withheld(updates):
    row = adapt([record(**updates)])["records"][0]
    assert row["status"] == "WITHHELD" and row["reasons"]


def test_duplicate_filing_calendar_and_invalid_dated_cik_rejected():
    with pytest.raises(ValueError, match="DUPLICATE_FILING_ID"):
        adapt([record(), record()])
    with pytest.raises(ValueError, match="SIGNAL_NOT_A_SESSION"):
        adapt([record()], signal="2020-01-04")
    with pytest.raises(ValueError, match="INVALID_DATED_MEMBER_CIK"):
        adapt([record()], cik="000")


def test_genuine_pinned_filing_metadata_sample_is_pit_without_outcome_claim():
    sample = json.loads((EVIDENCE / "us-filing-metadata-sample.json").read_text())
    raw = sample["metadataJsonl"].encode()
    result = us.build_filing_metadata_inputs(raw, digest(raw), signal_day="2013-03-07",
                member_cik="1090872", sessions=["2013-03-05", "2013-03-06", "2013-03-07"])
    assert result["records"][0]["ticker"] == "A"
    assert result["records"][0]["status"] == "PIT_METADATA_ONLY"
    assert not result["researchOutcomeAdmission"]
    assert not sample["financialValuesIncluded"]
    assert sample["source"]["sourceCommit"] == "704d7db6d5b00def771aba5d2665d0846d6bc776"


def test_existing_price_parser_does_not_emit_prices_or_invent_payoff():
    raw = b"date,close,volume\n2020-01-02,10,\n2020-01-03,12,20\n"
    result = us.candidate_price_dates(raw, digest(raw), ["2020-01-02", "2020-01-03"])
    assert result["observedSessions"] == ["2020-01-02", "2020-01-03"]
    assert result["quality"]["volumeMissingRows"] == 1
    assert result["terminalPayoff"] is None
    assert not result["researchOutcomeAdmission"]
    assert "close" not in result and "prices" not in result


def test_git_real_bytes_checked_without_granting_rights(tmp_path):
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    raw = b"small retained metadata\n"
    blob = subprocess.check_output(["git", "hash-object", "-w", "--stdin"], input=raw, cwd=tmp_path).decode().strip()
    receipt = us.git_object_receipt(tmp_path, blob, expected_sha256=digest(raw))
    assert receipt["payloadState"] == "EXACT_LOCAL_BYTES_VERIFIED"
    assert receipt["reuseRights"] == "UNVERIFIED" and not receipt["researchAdmission"]
    assert us.git_object_receipt(tmp_path, "0" * 40)["payloadState"] == "LOCAL_OBJECT_UNAVAILABLE"
    with pytest.raises(ValueError, match="HASH_MISMATCH"):
        us.git_object_receipt(tmp_path, blob, expected_sha256="0" * 64)


def test_readiness_does_not_confuse_metadata_existence_with_execution_permission():
    result = us.research_readiness({"benchmarkBytesVerified": True, "filingBytesVerified": True,
                                  "singleSecHeaderRecovered": True})
    rows = {r["track"]: r for r in result["tracks"]}
    assert rows["direct_stock_selection"]["status"] == "SOURCE_BLOCKED"
    assert rows["earnings_fundamental_changes"]["status"] == "RIGHTS_BLOCKED"
    assert rows["industry_selection"]["status"] == "PARTIAL"
    assert not any(r["empiricalReady"] or r["newOutcomeExecutionAuthorized"] for r in rows.values())
    assert all(r["status"] in us.STATES for r in rows.values())


def test_us_equity_economic_basis_rejects_krw_benchmark_and_implicit_fx():
    args = {"stock_currency": "USD", "benchmark_currency": "USD", "investor_currency": "USD", "signal_day": "2020-01-03"}
    assert not us.validate_us_currency_basis(**args)["fxEmbedded"]
    with pytest.raises(ValueError, match="NATIVE_CURRENCY_MISMATCH"):
        us.validate_us_currency_basis(**{**args, "benchmark_currency": "KRW"})
    with pytest.raises(ValueError, match="MUST_NOT_EMBED_FX"):
        us.validate_us_currency_basis(**args, fx_observation={"quote": "KRW_PER_USD"})
    with pytest.raises(ValueError, match="FX_REQUIRED"):
        us.validate_us_currency_basis(**{**args, "investor_currency": "KRW"})


def test_krw_investor_fx_has_separate_receipt_and_no_future_or_same_day_release():
    args = {"stock_currency": "USD", "benchmark_currency": "USD", "investor_currency": "KRW", "signal_day": "2020-01-03"}
    observation = {"quote": "KRW_PER_USD", "observationDate": "2020-01-02", "availableFrom": "2020-01-02",
                   "source": "SYNTHETIC_FX_SOURCE", "sha256": "a" * 64}
    assert us.validate_us_currency_basis(**args, fx_observation=observation)["usdAndKrwResultsMustRemainSeparate"]
    with pytest.raises(ValueError, match="NOT_AVAILABLE_AT_SIGNAL"):
        us.validate_us_currency_basis(**args, fx_observation={**observation, "availableFrom": "2020-01-03"})
    with pytest.raises(ValueError, match="NOT_AVAILABLE_AT_SIGNAL"):
        us.validate_us_currency_basis(**args, fx_observation={**observation, "observationDate": "2020-01-06"})
    with pytest.raises(ValueError, match="SOURCE_RECEIPT_REQUIRED"):
        us.validate_us_currency_basis(**args, fx_observation={**observation, "sha256": ""})
