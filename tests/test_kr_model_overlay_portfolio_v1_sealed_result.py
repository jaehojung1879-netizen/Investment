"""The formal kr-model-overlay-portfolio-v1 DEVELOPMENT result is committed byte-for-byte and closes the one-shot.

Outcome-neutral: reads archived bytes and recorded digests. It computes no historical statistic; the only logic
applied is the frozen `development_state` rule to the archived numbers, to prove the archived state follows from them.
"""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

import pytest

from pipeline import kr_model_portfolio_execution as X
from scripts import run_kr_model_overlay_portfolio_v1 as CLI

ROOT = Path(__file__).resolve().parents[1]
R = ROOT / "docs/results"
P = "kr-model-overlay-portfolio-v1-"
RESULT = R / (P + "result.json")
RESULT_FILE_SHA = "2c16e4e121abdd771c103eadce8707484b4092eb501188823aa1ac0726ec272a"
SPEC_SHA = "563b64ee6f4709a263719669f795ad55e7828e340f082358af1599453253b6fd"
INPUT_SHA = "233df37ed205cc6b48828121e711417ccf961301dc58aa252430b343db9666a7"
RUN_ID = 36926769546
EXEC_SHA = "89decab393a09381b11cbd16db99e73cc32b2a64"
PRIMARY_ARCHIVE = "dcf27477fbf425023432f973c5607e41ca70a751ec99e33b89fa6c3878e21c48"
AUDIT_ARCHIVE = "03827ed6a554cb4a13c6abedeba5dad0d89be863b6de61e86883845053e98af2"
SUMMARY_SHA = "db9f2b7a7ab0aa7fda0e997187bbb84fd49e19fcbe83ae5ede535e23b6970be4"
FILES = {
    "result.json": RESULT_FILE_SHA,
    "result.sha256.json": "c1311e67bd88fff24c2701ba5dc03daf329415ba4be60b3510ef66b1c162722a",
    "execution-started.json": "ba0747b92d30409c5c310fd844413e9e1c95c3924517716ac358194943df83d4",
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def result():
    return json.loads(RESULT.read_text())


@pytest.fixture(scope="module")
def prov():
    return json.loads((R / (P + "seal-provenance.json")).read_text())


def test_archived_bytes_are_exactly_the_formal_artifact_files():
    assert RESULT == ROOT / X.RESULT_PATH
    for name, digest in FILES.items():
        assert sha(R / (P + name)) == digest
    assert json.loads((R / (P + "result.sha256.json")).read_text()) == {"fileSha256": RESULT_FILE_SHA}
    assert json.loads((R / (P + "execution-started.json")).read_text()) == {"inputSha256": INPUT_SHA, "specSha256": SPEC_SHA}
    raw = gzip.decompress((R / (P + "diagnostic-summary.json.gz")).read_bytes())
    assert hashlib.sha256(raw).hexdigest() == SUMMARY_SHA and len(raw) == 58463505


def test_provenance_records_run_artifacts_and_lock(prov):
    assert prov["formalRun"]["runId"] == RUN_ID and prov["formalRun"]["executionCommitSha"] == EXEC_SHA
    assert prov["specSha256"] == SPEC_SHA and prov["inputSnapshotSha256"] == INPUT_SHA
    assert prov["artifacts"]["primary"]["artifactId"] == 11194647226
    assert prov["artifacts"]["primary"]["archiveSha256"] == PRIMARY_ARCHIVE
    assert prov["artifacts"]["audit"]["artifactId"] == 11194283481
    assert prov["artifacts"]["audit"]["archiveSha256"] == AUDIT_ARCHIVE
    lock = prov["permanentExecutionLock"]
    assert lock["ref"] == "refs/tags/" + X.STUDY + "-execution-lock-" + SPEC_SHA
    assert lock["points_to"] == EXEC_SHA and lock["neverUpdatedOrDeleted"] is True
    assert prov["primaryResultFileSha256"] == RESULT_FILE_SHA and prov["canonicalState"] == "DEVELOPMENT_REJECT"
    for entry in prov["committedFiles"].values():
        assert sha(ROOT / entry["path"]) == entry["sha256"]


def test_result_identity_and_canonical_state(result):
    assert result["studyId"] == X.STUDY and result["specSha256"] == SPEC_SHA
    assert result["specSha256"] == (ROOT / X.SPEC_PATH).with_suffix(".sha256").read_text().strip()
    assert result["inputSnapshotSha256"] == INPUT_SHA
    assert result["state"] == "DEVELOPMENT_REJECT"
    assert result["scientificStatus"] == "DEVELOPMENT_ON_OUTCOME_EXPOSED_HISTORY"
    assert result["substantive"] is True and result["prospectiveEvidence"] is False
    assert result["executionAuthorizationConsumed"] is True
    assert result["counters"]["portfolioOutcomeCalls"] == 1 and result["counters"]["modelOutcomeCalls"] == 2


def test_archived_state_follows_from_archived_numbers_under_the_frozen_rule(result):
    m, p = result["model"]["126"], result["portfolio"]
    assert m["complete"] and p["complete"]
    assert m["mseImprovementVsMean"] < 0 and m["mseImprovementVsMomentum"] < 0 and m["rankWeightedSpread"] < 0
    assert p["netExcess"] < 0 and all(h < 0 for h in p["chronologicalHalfExcess"])
    assert X.development_state(m, p) == "DEVELOPMENT_REJECT"


def test_diagnostics_are_descriptive_and_cannot_rescue():
    summary = json.loads(gzip.decompress((R / (P + "diagnostic-summary.json.gz")).read_bytes()))
    assert summary["status"] == "DESCRIPTIVE_ONLY" and summary["studyId"] == X.STUDY
    assert summary["affectsPrimary"] is False and summary["canRescuePrimary"] is False and summary["canAuthorizeRerun"] is False


def test_committed_result_permanently_refuses_a_further_execution(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    with pytest.raises(ValueError, match="SUBSTANTIVE_RESULT_ALREADY_CLOSED_V1"):
        CLI.run("execute", input_root=tmp_path, output=tmp_path / "out", root=ROOT)
    assert not (tmp_path / "out").exists()
    assert "V1_ALREADY_CLOSED" in (ROOT / ".github/workflows/kr-model-overlay-portfolio-v1.yml").read_text()


def test_frozen_study_is_unchanged_and_lock_machinery_intact():
    frozen, sha_ = X.load_spec()  # verifies spec digest, import closure and every pinned dependency/harness hash
    assert sha_ == SPEC_SHA
    assert frozen["horizons"] == [126, 252] and frozen["portfolio"]["singleNameCap"] == 0.3
    assert frozen["sectorStatus"] == "DEFERRED_BY_PIT_SECTOR_HISTORY"
    assert frozen["oneShot"]["substantiveResultCloses"] is True
    auth = json.loads((ROOT / X.AUTH_PATH).read_text())
    assert auth["specSha256"] == SPEC_SHA and auth["authorizedExecutions"] == 1
    assert auth["inputSnapshotSha256"] == INPUT_SHA
    assert auth["harnessHashes"] == frozen["dependencyHashes"]
    assert hasattr(X, "claim_execution_lock") and "PERMANENT_ONE_SHOT_LOCK_ALREADY_EXISTS" in (ROOT / ".github/workflows/kr-model-overlay-portfolio-v1.yml").read_text()
