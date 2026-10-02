"""Result seal for kr-factor-anatomy-v1: exact artifact bytes, exact identities, no recomputation, no re-execution."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from pipeline import kr_factor_anatomy as A
from pipeline import kr_factor_anatomy_execution as E
from pipeline.alpha_opportunity_spec import digest

ROOT = Path(__file__).resolve().parents[1]
R = ROOT / "docs" / "results"
P = "kr-factor-anatomy-v1-"
RESULT, REPORT, MANIFEST, PROV = (R / (P + n) for n in ("result.json", "report.md", "manifest.json", "seal-provenance.json"))
ARCHIVE = "f8020bdac9878f523091881d129e3c414234012c17e1fd61e1e49b6d6538b80f"
SPEC = "ceb97f481ae7261e89da4467fba03465f0c78cc3654cd799c26e5088ee3bc3d2"
INPUT = "233df37ed205cc6b48828121e711417ccf961301dc58aa252430b343db9666a7"
STATUS = "EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY"
V1_SPEC_SHA = "563b64ee6f4709a263719669f795ad55e7828e340f082358af1599453253b6fd"
V1_RESULT_FILE_SHA = "2c16e4e121abdd771c103eadce8707484b4092eb501188823aa1ac0726ec272a"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def prov():
    return json.loads(PROV.read_text())


def test_committed_files_match_provenance_hashes(prov):
    files = prov["committedFiles"]
    for path in (RESULT, REPORT, MANIFEST):
        entry = files["docs/results/" + path.name]
        assert sha(path) == entry["sha256"] and path.stat().st_size == entry["bytes"]
    assert {v["sourceFile"] for v in files.values()} == {"anatomy.json", "report.md", "manifest.json"}


def test_artifact_identity_is_recorded_exactly(prov):
    assert (prov["executionRunId"], prov["artifactId"], prov["artifactName"]) == (
        36960496371, 11207962601, "kr-factor-anatomy-v1-results-36960496371")
    assert prov["artifactArchiveSha256"] == ARCHIVE
    assert prov["executionSha"] == "cd82a5b7edb08f18ccdaa3f231415354aef9a41c"
    assert prov["specSha256"] == SPEC and prov["inputIdentitySha256"] == INPUT
    assert prov["sealedAtUtc"].endswith("Z")


def test_spec_and_input_identity_remain_exact(prov):
    spec_path = ROOT / "research_specs" / "kr-factor-anatomy-v1.json"
    spec = json.loads(spec_path.read_text())
    assert digest(spec) == SPEC == spec_path.with_suffix(".sha256").read_text().strip()
    assert spec["input"]["identitySha256"] == INPUT
    manifest = json.loads(MANIFEST.read_text())
    assert (manifest["studyId"], manifest["specSha256"], manifest["inputIdentitySha256"]) == (
        "kr-factor-anatomy-v1", SPEC, INPUT)
    assert manifest["files"]["anatomy.json"] == sha(RESULT) and manifest["files"]["report.md"] == sha(REPORT)


def test_scientific_status_remains_exploratory_and_has_no_pass_fail_or_promotion_semantics(prov):
    manifest = json.loads(MANIFEST.read_text())
    result = json.loads(RESULT.read_text())
    assert manifest["scientificStatus"] == prov["scientificStatus"] == STATUS == E.SCIENTIFIC_STATUS
    assert A.assert_no_forbidden_keys(result) and A.assert_no_forbidden_keys(manifest)
    for obj in (result, manifest):
        for key in ("passed", "pass", "fail", "promotionEligible", "promoted", "bestFactor", "productionWeights"):
            assert key not in obj
    assert not any(token in REPORT.read_text() for token in ("PASS ", "FAIL ", "PROMOTION_ELIGIBLE", "production-ready"))


def test_sealed_v1_study_is_unchanged():
    assert (ROOT / "research_specs" / "kr-model-overlay-portfolio-v1.sha256").read_text().strip() == V1_SPEC_SHA
    assert sha(R / "kr-model-overlay-portfolio-v1-result.json") == V1_RESULT_FILE_SHA


def test_the_seal_recomputes_nothing_and_blocks_re_execution(prov):
    assert prov["statisticsRecomputed"] is False
    assert E.RESULT_PATH == "docs/results/kr-factor-anatomy-v1-result.json" and RESULT.exists()
    assert not (ROOT / ".github" / "seal").exists()
    spec = json.loads((ROOT / "research_specs" / "kr-factor-anatomy-v1.json").read_text())
    env = {"GITHUB_ACTIONS": "true", "GITHUB_REF": "refs/heads/main", "GITHUB_EVENT_NAME": "workflow_dispatch",
           "GITHUB_SHA": "x", "ANATOMY_INPUT_ARTIFACT": spec["input"]["artifactName"],
           "ANATOMY_INPUT_RUN_ID": str(spec["input"]["producingRunId"])}
    committed = lambda args, root: b"x" if args[:1] == ["rev-parse"] else (Path(root) / args[1].split(":", 1)[1]).read_bytes()  # noqa: E731
    with pytest.raises(ValueError, match="ANATOMY_RESULT_ALREADY_COMMITTED"):
        E.authorize_execution(spec, SPEC, root=ROOT, env=env, git=committed)
