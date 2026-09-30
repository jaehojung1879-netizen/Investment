"""The formal alpha-opportunity-model-v5 result is committed byte-for-byte and closes the one-shot guard.

Outcome-neutral: this reads the archived result file and its recorded digests; it computes no statistic.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import alpha_opportunity_v5_execution as X  # noqa: E402
from scripts import execute_alpha_opportunity_model_v5 as CLI  # noqa: E402

RESULTS = ROOT / "docs/results"
RESULT = RESULTS / "alpha-opportunity-model-v5-result.json"
SIDECAR = RESULTS / "alpha-opportunity-model-v5-result.sha256"
FILE_SHA = "e06aa3fe17fb5986dd7e6a36272cc1bda59f78f97bfa4e6efaa68d1359d020d4"
SUBSTANTIVE_SHA = "9f5f84f4632847a74d21e29d22b46de9695490c2e4ad55ca1b75a0673e90c135"
ARCHIVED = {
    "alpha-opportunity-model-v5-diagnostic-models.json": "b43d7d42e95375619c0cd0c1fa2ee28e95273ad485a54fb9d46803ae3831db98",
    "alpha-opportunity-model-v5-diagnostic-summary.json": "37c6d8996f5a2696c7bd34863f96a9f74fc4a4a50bf694b5a772b1a4cafc304d",
    "alpha-opportunity-model-v5-diagnostic-references.json": "cf580b0c47b4023dfda707b4f9906796e8aabe88f4aa347b62ac8e23d3d67d2e",
}
LEDGER_SHA = "863827c0ad8de265e7d1f170265ece8927e649c6494f384eaef19f7957d61e6c"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def result():
    return json.loads(RESULT.read_text())


def test_committed_result_matches_its_sidecar_and_the_formal_artifact_digest():
    assert RESULT.is_file() and CLI.COMMITTED_RESULT == RESULT
    assert SIDECAR.read_text().strip() == FILE_SHA
    assert sha(RESULT) == FILE_SHA


def test_internal_substantive_digest_matches(result):
    assert result["resultDigests"]["substantiveResultSha256"] == SUBSTANTIVE_SHA
    assert X.substantive_digest(result) == SUBSTANTIVE_SHA


def test_sealed_verdict_is_inconclusive_and_closes_the_preregistration(result):
    assert result["overallStatus"] == "INCONCLUSIVE"
    assert result["substantiveResult"] is True and result["closesPreregistration"] is True
    assert result["promotionEligible"] is False
    assert result["executionMode"] == "FORMAL_EXECUTION" and result["phaseReached"] == "COMPLETE"
    assert result["cells"]["21"]["status"] == "INCONCLUSIVE"
    assert result["cells"]["126"]["status"] == "INCONCLUSIVE"
    assert result["blockedRegions"]["US"] == "BLOCKED_BY_DATA_INTEGRITY"
    assert result["studyId"] == "alpha-opportunity-model-v5"
    assert result["specSha256"] == (ROOT / "research_specs/alpha-opportunity-model-v5.sha256").read_text().strip()


def test_archived_diagnostics_match_recorded_hashes_and_reference_the_primary():
    for name, digest in ARCHIVED.items():
        assert sha(RESULTS / name) == digest
    refs = json.loads((RESULTS / "alpha-opportunity-model-v5-diagnostic-references.json").read_text())
    assert refs["status"] == "DIAGNOSTICS_COMPLETE"
    assert refs["changesPrimary"] is False and refs["authorizesRetry"] is False
    assert refs["primaryResultFileSha256"] == FILE_SHA and refs["primaryResultSha256"] == SUBSTANTIVE_SHA
    ledger = refs["artifacts"]["alpha-opportunity-model-v5-diagnostic-ledger.jsonl.gz"]
    assert (ledger["sha256"], ledger["bytes"], ledger["rowCount"]) == (LEDGER_SHA, 40563496, 125074)
    for name, digest in ARCHIVED.items():
        if name.endswith("references.json"):
            continue
        assert refs["artifacts"][name]["sha256"] == digest
    assert not list(ROOT.glob("**/alpha-opportunity-model-v5-diagnostic-ledger*"))  # ledger is not committed


def test_the_committed_result_permanently_refuses_any_further_formal_run():
    auth = ROOT / "research_specs/alpha-opportunity-model-v5-execution-authorization.json"
    spec_sha = (ROOT / "research_specs/alpha-opportunity-model-v5.sha256").read_text().strip()
    diag_sha = (ROOT / "research_specs/alpha-opportunity-model-v5-diagnostics-v1.sha256").read_text().strip()
    with pytest.raises(CLI.Refusal, match="A_COMMITTED_V5_RESULT_ALREADY_EXISTS"):
        CLI.verify_authorization(auth, spec_sha256=spec_sha, harness_files=X.harness_file_hashes(ROOT),
                                 diagnostic_spec_sha256=diag_sha)
