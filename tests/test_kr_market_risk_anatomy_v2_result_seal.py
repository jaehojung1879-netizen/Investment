"""Result seal for kr-market-risk-anatomy-v2: exact artifact bytes, exact identities, no recomputation, no re-execution."""
import hashlib
import json
from pathlib import Path
import subprocess

import pytest
from pipeline import kr_market_risk_anatomy as M
from pipeline import kr_market_risk_anatomy_v2_execution as E

ROOT = Path(__file__).resolve().parents[1]
R = ROOT / "docs/results"
P = "kr-market-risk-anatomy-v2-"
RESULT, MANIFEST, MARKER, PROV = (R / (P + n) for n in ("result.json", "manifest.json", "execution-started.json", "seal-provenance.json"))
DOC = ROOT / "docs/kr-market-risk-anatomy-v2-final-result.md"
ARCHIVE = "f7f9f17a3a2aaa9bdb7b4ae488717d5cb1bbfc6228400664d4295557af37450f"
SPEC = "4be62167585bbacb7a7192768eb120d90e08fbfc6b518695e52929077d1d06f2"
DESIGN = "3c398b6e87e6634443ffe25273f95ed100889515a71ddb66eb2ecd7035788aaa"
AUDIT = "29e1b54b249f84be327d9c7a228d6e68a447d38511652414fc7ef2c9f0099345"
RESULT_SHA = "7be4f68f30cf57b01cde88f106b3c0c2ed88fc9942ca2a14007664ffbe4ca769"
MARKER_SHA = "391b6ff013d5a89d5e0342fdc767c4304bc6d7ad6bc8d63247a45a71794c73bc"
MANIFEST_SHA = "d32efef61916ef761a662723a4e18edcbf32ad737a22b9835cd81733204e0067"
MAIN_SHA = "5b73b20d676537c7ed3e613986b61fdade7c9b8d"
STATUS = "EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY"
COUNTERS = {"analysisCalls": 1, "episodeCalls": 1, "forwardTargetCalls": 1, "markerWrites": 1, "valueReads": 14}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def prov():
    return json.loads(PROV.read_text())


def test_committed_result_files_are_pinned_byte_for_byte(prov):
    assert (sha(RESULT), sha(MANIFEST), sha(MARKER)) == (RESULT_SHA, MANIFEST_SHA, MARKER_SHA)
    for path in (RESULT, MANIFEST, MARKER):
        entry = prov["committedFiles"]["docs/results/" + path.name]
        assert entry["sha256"] == sha(path) and entry["bytes"] == path.stat().st_size
    assert {v["sourceFile"] for v in prov["committedFiles"].values()} == {"market-risk-anatomy.json", "manifest.json", "execution-started.json"}
    assert E.RESULT_PATH == "docs/results/kr-market-risk-anatomy-v2-result.json" and E.MARKER_PATH == "docs/results/kr-market-risk-anatomy-v2-execution-started.json"


def test_manifest_and_marker_tie_the_result_to_the_frozen_identities():
    manifest, marker = json.loads(MANIFEST.read_text()), json.loads(MARKER.read_text())
    assert manifest["files"] == {"market-risk-anatomy.json": RESULT_SHA}
    assert (manifest["specSha256"], manifest["designSha256"], manifest["sourceAuditSha256"]) == (SPEC, DESIGN, AUDIT)
    assert manifest["scientificStatus"] == STATUS and manifest["studyId"] == "kr-market-risk-anatomy-v2" and manifest["counters"] == COUNTERS
    assert marker["lockedMainSha"] == MAIN_SHA and marker["lockRef"] == "refs/tags/kr-market-risk-anatomy-v2-execution-lock-" + SPEC
    assert marker["valuesReadBeforeThisMarker"] == 0 and marker["specSha256"] == SPEC and marker["designSha256"] == DESIGN and marker["sourceAuditSha256"] == AUDIT


def test_run_artifact_and_lock_identity_are_recorded(prov):
    assert (prov["executionRunId"], prov["artifactId"], prov["artifactName"]) == (37244866236, 11318254649, "kr-market-risk-anatomy-v2-results-37244866236")
    assert prov["artifactGithubDigest"] == "sha256:" + ARCHIVE == "sha256:" + prov["artifactArchiveSha256"]
    assert prov["executionSha"] == prov["sealBranchBaseSha"] == MAIN_SHA and prov["runConclusion"] == "success" and prov["runEvent"] == "workflow_dispatch"
    assert prov["artifactFileList"] == ["execution-started.json", "manifest.json", "market-risk-anatomy.json"]
    assert (prov["specSha256"], prov["designSha256"], prov["sourceAuditSha256"]) == (SPEC, DESIGN, AUDIT) and prov["executionCounters"] == COUNTERS
    assert prov["statisticsRecomputed"] is False and prov["workflowRerun"] is False and prov["scientificStatus"] == STATUS
    refs = {r["ref"]: r["sha"] for r in prov["executionLock"]["observedRefs"]}
    assert refs == {"refs/tags/kr-market-risk-anatomy-v2-execution-lock": MAIN_SHA, "refs/tags/kr-market-risk-anatomy-v2-execution-lock-" + SPEC: MAIN_SHA}
    assert prov["executionLock"]["lockedMainSha"] == MAIN_SHA


def test_frozen_spec_and_design_remain_exact():
    spec, sha_ = E.load_spec(ROOT)          # re-verifies the import closure, harness hashes, v1 sealed bytes and every source pin
    assert sha_ == SPEC == (ROOT / "research_specs/kr-market-risk-anatomy-v2.sha256").read_text().strip()
    assert spec["designSha256"] == DESIGN and spec["sourcePins"]["auditSha256"] == AUDIT and spec["scientificStatus"] == STATUS


def test_result_status_reference_and_forbidden_semantics_are_unchanged():
    result = json.loads(RESULT.read_text())
    assert result["scientificStatus"] == STATUS and result["studyId"] == "kr-market-risk-anatomy-v2" and result["predecessor"] == "kr-market-risk-anatomy-v1"
    assert result["primaryReference"]["primary"] == "FDR_KS200" and result["primaryReference"]["spliced"] is False and result["analysisEnd"] == "2026-09-17"
    assert result["episodes"]["counts"] == {"depth_ge_10pct": 13, "depth_ge_15pct": 12, "depth_ge_20pct": 9}
    M.assert_no_forbidden_keys(result)


def test_final_result_document_keeps_the_three_sections_and_the_boundary():
    text = DOC.read_text()
    for heading in ("## A. Formal observed result", "## B. Interpretation / development implication", "## C. What is not claimed"):
        assert heading in text
    assert STATUS in text and "not** prospective validation" in text and RESULT_SHA in text and "37244866236" in text
    assert not any(t in text for t in ("recommended portfolio", "PROMOTION", "is production-ready"))


def test_a_sealed_result_refuses_every_future_execution():
    spec, sha_ = E.load_spec(ROOT)
    env = {"GITHUB_ACTIONS": "true", "GITHUB_REF": "refs/heads/main", "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_SHA": "a" * 40, "GH_TOKEN": "t",
           "GITHUB_REPOSITORY": "o/r", "MARKET_INPUT_ARTIFACT": spec["input"]["artifactName"], "MARKET_INPUT_RUN_ID": str(spec["input"]["producingRunId"])}

    def git(args, root):
        return (b"a" * 40 + b"\n") if args[0] == "rev-parse" else (Path(root) / args[1][len("HEAD:"):]).read_bytes()
    assert (ROOT / E.RESULT_PATH).exists() and (ROOT / E.MARKER_PATH).exists()
    with pytest.raises(ValueError, match="MARKET_RISK_V2_RESULT_ALREADY_COMMITTED"):
        E.authorize_execution(spec, sha_, ROOT, env, git, lambda: False)
    assert E.lock_exists(sha_, env, lambda *a, **k: (200, [{"ref": E.LOCK_PREFIX}, {"ref": E.lock_ref(sha_)}]))


def test_seal_change_touches_no_frozen_machinery():
    """Against the seal base, no frozen v2 / v1 machinery, spec, workflow or retained source byte changed."""
    try:
        changed = subprocess.check_output(["git", "diff", "--name-only", MAIN_SHA, "HEAD"], cwd=str(ROOT), text=True).split()
    except (subprocess.CalledProcessError, OSError):
        pytest.skip("seal base commit not available in this checkout")
    # later commits on main may add unrelated files; the frozen v2 machinery must never be among the changes
    frozen = [p for p in changed if p.startswith(("pipeline/kr_market_risk", "research_specs/kr-market-risk-anatomy", ".github/workflows/kr-market-risk-anatomy", "scripts/run_kr_market_risk",
                                                 "scripts/build_kr_market_risk", "data/kr-market-risk-anatomy-v1/"))]
    assert frozen == []
