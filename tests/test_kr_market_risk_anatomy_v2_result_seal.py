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


# The frozen anatomy machinery is an EXACT file set, never a name prefix: a prefix such as "pipeline/kr_market_risk" also matches every later,
# legitimate kr_market_risk_* study. The set is derived from what the sealed v1 / v2 specs themselves hash (import closure plus sealed data inputs),
# plus the few anatomy-owned files that sit outside those closures, listed exactly.
ANATOMY_OWNED_OUTSIDE_THE_CLOSURES = (
    "research_specs/kr-market-risk-anatomy-v2.json", "research_specs/kr-market-risk-anatomy-v2.sha256",
    ".github/workflows/kr-market-risk-anatomy-v1-sources.yml",
    "scripts/acquire_kr_market_risk_sources.py", "scripts/write_kr_market_risk_readiness.py", "scripts/write_kr_market_risk_v2_readiness.py",
    "docs/kr-market-risk-anatomy-v1-design.md", "docs/kr-market-risk-anatomy-v2-source-readiness.md",
    "docs/results/kr-market-risk-anatomy-v2-readiness.json", "docs/results/kr-market-risk-anatomy-v2-provenance.json")
# The result, manifest, marker, provenance and final-result document are CREATED by the seal commit, so they are legitimately absent from the seal base
# and present in every later diff against it; their bytes are pinned by test_committed_result_files_are_pinned_byte_for_byte and the provenance tests.
SEAL_CREATED = ("docs/kr-market-risk-anatomy-v2-final-result.md", "docs/results/kr-market-risk-anatomy-v2-result.json", "docs/results/kr-market-risk-anatomy-v2-manifest.json",
                "docs/results/kr-market-risk-anatomy-v2-execution-started.json", "docs/results/kr-market-risk-anatomy-v2-seal-provenance.json")


def frozen_anatomy_paths(root=ROOT):
    """Exact protected set: every file the sealed v1 and v2 specs hash, plus the anatomy-owned files listed above."""
    paths = set(ANATOMY_OWNED_OUTSIDE_THE_CLOSURES)
    for name in ("kr-market-risk-anatomy-v1", "kr-market-risk-anatomy-v2"):
        paths |= set(json.loads((Path(root) / "research_specs" / (name + ".json")).read_text())["dependencyHashes"])
    return frozenset(paths)


def frozen_changes(changed, protected):
    return sorted(p for p in changed if p in protected)


def git_changed(base, root=ROOT):
    return subprocess.check_output(["git", "diff", "--name-only", base, "HEAD"], cwd=str(root), text=True).split()


def test_seal_change_touches_no_frozen_machinery():
    """Against the seal base, no frozen v2 / v1 machinery, spec, workflow or retained source byte changed. Later commits on main may add unrelated
    files, including later kr_market_risk_* studies; only the exact frozen set matters."""
    try:
        changed = git_changed(MAIN_SHA)
    except (subprocess.CalledProcessError, OSError):
        pytest.skip("seal base commit not available in this checkout")
    assert frozen_changes(changed, frozen_anatomy_paths()) == []


def test_the_protected_set_is_exact_derived_from_the_sealed_specs_and_never_a_name_prefix():
    protected = frozen_anatomy_paths()
    v2 = json.loads((ROOT / "research_specs/kr-market-risk-anatomy-v2.json").read_text())["dependencyHashes"]
    v1 = json.loads((ROOT / "research_specs/kr-market-risk-anatomy-v1.json").read_text())["dependencyHashes"]
    assert set(v2) | set(v1) <= protected and len(protected) >= len(set(v2) | set(v1))
    for path in ("pipeline/kr_market_risk_anatomy.py", "pipeline/kr_market_risk_anatomy_analysis.py", "pipeline/kr_market_risk_anatomy_execution.py",
                 "pipeline/kr_market_risk_anatomy_v2_execution.py", "pipeline/kr_market_risk_sources.py", "pipeline/kr_market_risk_sources_v2.py",
                 "pipeline/kr_market_risk_source_parse.py", "pipeline/kr_market_risk_overlay.py", "scripts/run_kr_market_risk_anatomy_v1.py",
                 "scripts/run_kr_market_risk_anatomy_v2.py", ".github/workflows/kr-market-risk-anatomy-v2.yml", "research_specs/kr-market-risk-anatomy-v2.json",
                 "data/kr-market-risk-anatomy-v1/sources/FDR_KS200/normalized.csv", "docs/results/kr-market-risk-anatomy-v2-readiness.json"):
        assert path in protected, path
    assert not [p for p in protected if "kr_market_risk_model" in p or "kr-market-risk-model" in p]
    assert not set(SEAL_CREATED) & protected and all((ROOT / p).exists() for p in SEAL_CREATED)


def test_a_genuinely_frozen_anatomy_file_is_still_detected_and_a_later_market_risk_model_file_is_not_a_false_mutation():
    protected = frozen_anatomy_paths()
    dependency = sorted(json.loads((ROOT / "research_specs/kr-market-risk-anatomy-v2.json").read_text())["dependencyHashes"])[0]
    for frozen in ("pipeline/kr_market_risk_anatomy.py", "pipeline/kr_market_risk_sources_v2.py", ".github/workflows/kr-market-risk-anatomy-v2.yml",
                   "research_specs/kr-market-risk-anatomy-v2.sha256", "docs/results/kr-market-risk-anatomy-v2-provenance.json", dependency):
        assert frozen_changes([frozen, "README.md"], protected) == [frozen]
    later = ["pipeline/kr_market_risk_model.py", "pipeline/kr_market_risk_model_execution.py", "pipeline/kr_market_risk_model_receipts.py",
             "pipeline/kr_market_risk_model_seal.py", "scripts/build_kr_market_risk_model_v1_spec.py", "scripts/run_kr_market_risk_model_v1.py",
             "scripts/seal_kr_market_risk_model_v1.py", ".github/workflows/kr-market-risk-model-v1.yml", "research_specs/kr-market-risk-model-v1.json",
             "docs/results/kr-market-risk-model-v1-result.json",
             # a hypothetical future study sharing the family name must never be caught either
             "pipeline/kr_market_risk_model_v2.py", "pipeline/kr_market_risk_regime.py", "scripts/run_kr_market_risk_model_v2.py",
             "scripts/build_kr_market_risk_regime_spec.py", "research_specs/kr-market-risk-regime-v1.json"]
    assert frozen_changes(later, protected) == []


def test_the_real_git_diff_path_flags_a_frozen_edit_and_ignores_a_new_model_file(tmp_path):
    """The same diff plumbing the real test uses, on a throwaway repository seeded with the real sealed specs."""
    def git(*args):
        return subprocess.check_output(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=str(tmp_path), text=True)
    (tmp_path / "research_specs").mkdir()
    for name in ("kr-market-risk-anatomy-v1.json", "kr-market-risk-anatomy-v2.json"):
        (tmp_path / "research_specs" / name).write_bytes((ROOT / "research_specs" / name).read_bytes())
    (tmp_path / "pipeline").mkdir()
    (tmp_path / "pipeline/kr_market_risk_anatomy.py").write_text("x = 1\n")
    git("init", "-q")
    git("add", "-A")
    git("commit", "-q", "-m", "base")
    base = git("rev-parse", "HEAD").strip()
    (tmp_path / "pipeline/kr_market_risk_model.py").write_text("y = 1\n")
    git("add", "-A")
    git("commit", "-q", "-m", "new model file")
    protected = frozen_anatomy_paths(tmp_path)
    assert git_changed(base, tmp_path) == ["pipeline/kr_market_risk_model.py"] and frozen_changes(git_changed(base, tmp_path), protected) == []
    (tmp_path / "pipeline/kr_market_risk_anatomy.py").write_text("x = 2\n")
    git("add", "-A")
    git("commit", "-q", "-m", "frozen edit")
    assert frozen_changes(git_changed(base, tmp_path), protected) == ["pipeline/kr_market_risk_anatomy.py"]
