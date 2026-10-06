"""kr-alpha-discovery-tournament-v1: frozen identity, authorization, lock ordering (gates -> lock -> marker -> first label), the seal step as a real
subprocess, the workflow's structure and the outcome-free state of this preregistration. No market data, no network, no real lock."""
from __future__ import annotations

import ast
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

from pipeline import kr_alpha_tournament as T
from pipeline import kr_alpha_tournament_execution as E
from pipeline import kr_alpha_tournament_seal as SEAL
from pipeline import kr_alpha_tournament_study as ST

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/kr-alpha-discovery-tournament-v1.yml"


# --------------------------------------------------------------------------- #
# Frozen identity
# --------------------------------------------------------------------------- #
def test_spec_loads_and_its_hash_is_the_sidecar():
    spec, sha = E.load_spec(ROOT)
    assert sha == (ROOT / E.SPEC_SIDECAR).read_text().strip() == E.digest(spec)
    assert spec["trialLedger"]["totalEffectiveTrials"] == 123 and spec["scientificStatus"] == T.SCIENTIFIC_STATUS


def test_a_module_rule_change_or_a_dependency_edit_refuses(monkeypatch):
    real = E.frozen_sections
    monkeypatch.setattr(E, "frozen_sections", lambda: {**real(), "verdict": {**real()["verdict"], "meaningfulGPp": 0.5}})
    with pytest.raises(ValueError, match="MODULE_RULE_DIFFERS_FROM_FROZEN_SPEC: verdict"):
        E.load_spec(ROOT)
    monkeypatch.undo()
    real_hash = E.file_hash
    monkeypatch.setattr(E, "file_hash", lambda p: "0" * 64 if str(p).endswith("kr_alpha_tournament_portfolio.py") else real_hash(p))
    with pytest.raises(ValueError, match="HARNESS_OR_DEPENDENCY_CHANGED"):
        E.load_spec(ROOT)


def test_spec_inherits_the_integrated_studys_exact_input_and_membership_pins():
    spec, _ = E.load_spec(ROOT)
    integrated = json.loads((ROOT / E.INTEGRATED_SPEC).read_text())
    assert spec["input"] == integrated["input"] and spec["membership"] == integrated["membership"]
    assert spec["input"]["artifactName"] == "kr-model-raw-inputs-36844599518"


def test_nothing_has_been_executed_sealed_or_locked_in_this_checkout():
    for rel in (E.RESULT_PATH, E.MARKER_PATH, E.MANIFEST_PATH, SEAL.PROVENANCE_PATH):
        assert not (ROOT / rel).exists(), rel
    tags = subprocess.run(["git", "tag", "--list", T.STUDY + "*"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    assert tags == ""


def test_committed_readiness_is_outcome_free_and_matches_the_spec():
    readiness = json.loads((ROOT / E.READINESS_PATH).read_text())
    _, sha = E.load_spec(ROOT)
    assert readiness["specSha256"] == sha and readiness["decision"] == E.DECISION_READY
    assert all(v == 0 for v in readiness["counters"].values())
    assert readiness["realOutcomesRead"] is False and readiness["rawArtifactTouched"] is False and readiness["synthetic"]["deterministic"]
    assert readiness["calendarFoldPlan"] == E.calendar_fold_plan()


def test_verify_and_readiness_never_touch_real_data(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("REAL_DATA_TOUCHED")
    for name in ("build_signal_bundle", "terminal_ineligible", "cross_check_endpoints", "RealContext"):
        monkeypatch.setattr(E, name, refuse)
    monkeypatch.setattr(E.X, "load_sources", refuse)
    monkeypatch.setattr(E, "synthetic_determinism", lambda full=False: {"deterministic": True})
    assert E.verify(ROOT)["verified"]
    assert E.readiness_audit(ROOT)["realOutcomesRead"] is False


# --------------------------------------------------------------------------- #
# Authorization
# --------------------------------------------------------------------------- #
def _env(**kw):
    spec, sha = E.load_spec(ROOT)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    env = {"GITHUB_ACTIONS": "true", "GITHUB_REF": "refs/heads/main", "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_SHA": head,
           E.INPUT_ARTIFACT_ENV: spec["input"]["artifactName"], E.INPUT_RUN_ENV: str(spec["input"]["producingRunId"])}
    env.update(kw)
    return spec, sha, env


def _git_committed(args, root):
    if args[0] == "rev-parse":
        return subprocess.check_output(["git", *args], cwd=root)
    return (Path(root) / args[1].split(":", 1)[1]).read_bytes()


@pytest.mark.parametrize("override,code", [({"GITHUB_ACTIONS": "false"}, "REQUIRES_ACTIONS"), ({"GITHUB_REF": "refs/heads/x"}, "REQUIRES_MAIN"),
                                           ({"GITHUB_EVENT_NAME": "pull_request"}, "WORKFLOW_DISPATCH"), ({"GITHUB_SHA": "0" * 40}, "NOT_THE_DISPATCHED"),
                                           ({E.INPUT_ARTIFACT_ENV: "other"}, "INPUT_ARTIFACT_IDENTITY_MISMATCH")])
def test_authorization_refuses_anything_but_the_registered_dispatch(override, code):
    spec, sha, env = _env(**override)
    with pytest.raises(ValueError, match=code):
        E.authorize_execution(spec, sha, ROOT, env, git=_git_committed, lock_probe=lambda: False)


def test_authorization_refuses_when_any_lock_exists_or_its_state_is_unknown():
    spec, sha, env = _env()
    with pytest.raises(ValueError, match="EXECUTION_LOCK_ALREADY_EXISTS"):
        E.authorize_execution(spec, sha, ROOT, env, git=_git_committed, lock_probe=lambda: True)
    with pytest.raises(ValueError, match="UNVERIFIABLE"):
        E.lock_exists({}, api=lambda *a: (200, []))
    with pytest.raises(ValueError, match="UNVERIFIABLE"):
        E.lock_exists({"GH_TOKEN": "x", "GITHUB_REPOSITORY": "o/r"}, api=lambda *a: (500, {}))
    permit = E.authorize_execution(spec, sha, ROOT, env, git=_git_committed, lock_probe=lambda: False)
    assert E.require_permit(permit) is permit


# --------------------------------------------------------------------------- #
# The lock and its order
# --------------------------------------------------------------------------- #
class FakeApi:
    def __init__(self, existing=()):
        self.refs, self.calls = {r: "sha" for r in existing}, []

    def __call__(self, method, path, payload=None):
        self.calls.append((method, path))
        if method == "GET" and path.startswith("/git/matching-refs/"):
            prefix = "refs/" + path[len("/git/matching-refs/"):]
            return 200, [{"ref": r} for r in self.refs if r.startswith(prefix)]
        if method == "POST" and path == "/git/refs":
            if payload["ref"] in self.refs:
                return 422, {}
            self.refs[payload["ref"]] = payload["sha"]
            return 201, {}
        if method == "GET" and path.startswith("/git/ref/"):
            ref = "refs/" + path[len("/git/ref/"):]
            return (200, {"object": {"sha": self.refs[ref]}}) if ref in self.refs else (404, {})
        raise AssertionError("UNEXPECTED_API_CALL " + method + " " + path)


LOCK_ENV = {"GITHUB_ACTIONS": "true", "GITHUB_REF": "refs/heads/main", "GITHUB_SHA": "a" * 40, "GH_TOKEN": "t", "GITHUB_REPOSITORY": "o/r"}


def test_lock_is_exclusive_for_any_spec_sha_and_only_post_and_get_are_issued():
    api = FakeApi()
    lock = E.claim_execution_lock("b" * 64, LOCK_ENV, api)
    assert lock.ref == E.LOCK_PREFIX + "-" + "b" * 64 and set(api.refs) == {E.STUDY_LOCK_REF, lock.ref}
    with pytest.raises(ValueError, match="EXECUTION_LOCK_ALREADY_EXISTS"):
        E.claim_execution_lock("c" * 64, LOCK_ENV, api)
    assert {m for m, _ in api.calls} <= {"GET", "POST"}
    with pytest.raises(ValueError, match="DURABLE_EXECUTION_LOCK_REQUIRED"):
        E.require_lock(lock, "c" * 64)


def _execute_with(monkeypatch, tmp_path, gates):
    spec, sha = E.load_spec(ROOT)
    order = []
    monkeypatch.setattr(E.X, "input_identity", lambda root: {"sha256": spec["input"]["identitySha256"]})
    monkeypatch.setattr(E, "build_signal_bundle", lambda *a, **k: (order.append("features"), a[3].__setitem__("featureBuilds", 1), {"features": None})[2])
    monkeypatch.setattr(E, "pre_lock_gates", lambda *a: (order.append("gates"), gates)[1])
    api = FakeApi()

    def spy_api(method, path, payload=None):
        if method == "POST":
            order.append("lock")
        return api(method, path, payload)

    def first_outcome(*a, **k):
        order.append("outcome")
        raise RuntimeError("SPY_FIRST_OUTCOME")
    for name in ("RealContext", "terminal_ineligible"):
        monkeypatch.setattr(E, name, first_outcome)
    monkeypatch.setattr(E.F, "represent", first_outcome)
    monkeypatch.setattr(E.ST, "build_labels", first_outcome)
    permit = E.ExecutionPermit(sha, E._PERMIT_TOKEN)
    return spec, sha, permit, api, spy_api, order


def test_a_failed_label_free_gate_stops_before_the_lock_and_spends_nothing(monkeypatch, tmp_path):
    spec, sha, permit, api, spy_api, order = _execute_with(monkeypatch, tmp_path, ["SIGNAL_COVERAGE_BELOW_80_PERCENT"])
    with pytest.raises(ValueError, match="PRE_LOCK_GATES_FAILED"):
        E.execute(tmp_path / "in", tmp_path / "out", spec, sha, permit, ROOT, LOCK_ENV, spy_api)
    assert order == ["features", "gates"] and api.refs == {}
    failed = json.loads((tmp_path / "out/gates-failed.json").read_text())
    assert failed["spent"] is False and E.outcomes_zero(failed["counters"])
    assert not (tmp_path / "out" / E.MARKER_FILE).exists()


def test_lock_then_marker_then_the_first_outcome(monkeypatch, tmp_path):
    spec, sha, permit, api, spy_api, order = _execute_with(monkeypatch, tmp_path, [])
    with pytest.raises(RuntimeError, match="SPY_FIRST_OUTCOME"):
        E.execute(tmp_path / "in", tmp_path / "out", spec, sha, permit, ROOT, LOCK_ENV, spy_api)
    assert order == ["features", "gates", "lock", "lock", "outcome"]
    marker = json.loads((tmp_path / "out" / E.MARKER_FILE).read_text())
    assert marker["valuesReadBeforeThisMarker"] == 0 and marker["lockRef"] == E.lock_ref(sha) and marker["counters"]["markerWrites"] == 1
    assert E.outcomes_zero(marker["counters"]) and set(api.refs) == {E.STUDY_LOCK_REF, E.lock_ref(sha)}


def test_execute_source_reads_no_outcome_before_the_lock():
    tree = ast.parse((ROOT / "pipeline/kr_alpha_tournament_execution.py").read_text())
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "execute")
    names = [(n.lineno, ast.unparse(n.func)) for n in ast.walk(fn) if isinstance(n, ast.Call)]
    lock_line = min(line for line, name in names if name == "claim_execution_lock")
    outcome = ("ST.build_labels", "W.run_process", "ST.run_paths", "ST.assemble", "RealContext", "terminal_ineligible", "F.represent")
    assert all(line > lock_line for line, name in names if name in outcome)


def test_the_marker_refuses_after_outcome_access(tmp_path):
    lock = E.ExecutionLock("s", "m", "r", E._LOCK_TOKEN)
    counters = E.new_counters()
    counters["labelBuilds"] = 1
    with pytest.raises(ValueError, match="MARKER_AFTER_OUTCOME_ACCESS"):
        E.write_marker(tmp_path, {}, "s", counters, lock)


# --------------------------------------------------------------------------- #
# Seal (stdlib only; exercised as a real subprocess)
# --------------------------------------------------------------------------- #
def test_seal_module_imports_only_the_standard_library():
    tree = ast.parse((ROOT / "pipeline/kr_alpha_tournament_seal.py").read_text())
    imported = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imported |= {(n.module or "").split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert imported <= {"__future__", "hashlib", "io", "json", "pathlib", "zipfile"}


def test_seal_script_actually_runs_its_subcommands(tmp_path):
    """The integrated study's seal script had no main() guard, so every subcommand was a silent no-op (run 37374530672). Run this one for real."""
    script = ROOT / "scripts/seal_kr_alpha_discovery_tournament_v1.py"
    assert 'if __name__ == "__main__":' in script.read_text()
    out = subprocess.run([sys.executable, str(script), "check-main", "--root", str(ROOT)], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == (ROOT / E.SPEC_SIDECAR).read_text().strip()
    (tmp_path / "research_specs").mkdir()
    (tmp_path / "research_specs" / (T.STUDY + ".json")).write_text("{}")
    (tmp_path / "research_specs" / (T.STUDY + ".sha256")).write_text("x\n")
    (tmp_path / "docs/results").mkdir(parents=True)
    (tmp_path / SEAL.COMMITTED["tournament-result.json"]).write_text("{}")
    bad = subprocess.run([sys.executable, str(script), "check-main", "--root", str(tmp_path)], capture_output=True, text=True)
    assert bad.returncode != 0 and "RESULT_ALREADY_SEALED" in bad.stderr


def _bundle(spec_sha, main_sha):
    lock = SEAL.LOCK_PREFIX + "-" + spec_sha
    result = json.dumps({"studyId": T.STUDY, "specSha256": spec_sha, "lockRef": lock, "lockedMainSha": main_sha, "scientificStatus": T.SCIENTIFIC_STATUS}).encode()
    marker = json.dumps({"studyId": T.STUDY, "specSha256": spec_sha, "lockRef": lock, "studyLockRef": SEAL.LOCK_PREFIX, "lockedMainSha": main_sha,
                         "valuesReadBeforeThisMarker": 0}).encode()
    manifest = json.dumps({"studyId": T.STUDY, "specSha256": spec_sha, "scientificStatus": T.SCIENTIFIC_STATUS, "counters": {"markerWrites": 1},
                           "files": {"tournament-result.json": hashlib.sha256(result).hexdigest(), "execution-started.json": hashlib.sha256(marker).hexdigest()}}).encode()
    return {"tournament-result.json": result, "execution-started.json": marker, "manifest.json": manifest}


def test_seal_copies_exact_bytes_and_refuses_any_mismatch(tmp_path):
    files = _bundle("s" * 64, "m" * 40)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for k, v in files.items():
            z.writestr(k, v)
    raw = buf.getvalue()
    assert SEAL.read_archive(raw, hashlib.sha256(raw).hexdigest()) == files
    with pytest.raises(ValueError, match="ARCHIVE_SHA256_MISMATCH"):
        SEAL.read_archive(raw, "0" * 64)
    SEAL.verify_bundle(files, "s" * 64, "m" * 40)
    with pytest.raises(ValueError, match="SPEC_SHA_MISMATCH"):
        SEAL.verify_bundle(files, "t" * 64, "m" * 40)
    record = SEAL.write_seal(files, tmp_path, {"executionRunId": 1})
    for name, rel in SEAL.COMMITTED.items():
        assert (tmp_path / rel).read_bytes() == files[name]
    assert SEAL.verify_written(tmp_path) == json.loads((tmp_path / SEAL.PROVENANCE_PATH).read_text()) and record["studyId"] == T.STUDY
    with pytest.raises(ValueError, match="NOT_THE_FORMAL_RESULTS_ARTIFACT"):
        SEAL.check_artifact_metadata({"name": SEAL.ATTEMPT_ARTIFACT_PREFIX + "1"}, 1)


# --------------------------------------------------------------------------- #
# Workflow
# --------------------------------------------------------------------------- #
def _job(text, name):
    start = text.index("\n  " + name + ":\n")
    rest = text[start + 1:]
    nxt = [rest.find("\n  " + j + ":\n") for j in ("frozen-machine", "execute", "seal") if j != name]
    nxt = [n for n in nxt if n > 0]
    return rest[:min(nxt)] if nxt else rest


def test_workflow_executes_only_by_manual_dispatch_and_seals_safely():
    text = WORKFLOW.read_text()
    header = text[:text.index("\njobs:")]
    assert "pull_request:" in header and "workflow_dispatch:" in header and "schedule:" not in header and "push:" not in header
    assert "permissions:\n  contents: read\n  actions: read" in header and "OMP_NUM_THREADS: '1'" in header
    frozen, execute, seal = _job(text, "frozen-machine"), _job(text, "execute"), _job(text, "seal")
    assert "if: github.event_name == 'workflow_dispatch' && inputs.mode == 'execute'" in execute
    assert "timeout-minutes: 340" in execute and "contents: write" in execute
    assert "--mode verify" in frozen and "--mode readiness" in frozen and "--mode execute" not in frozen and "contents: write" not in frozen
    assert execute.count("--mode execute") == 1
    commit = seal[seal.index("Commit and push"):]
    assert "SEAL_FILE_MISSING" in commit and commit.index("SEAL_FILE_MISSING") < commit.index("git add")
    for reserved in ("exec", "core", "github", "context", "glob", "io", "require"):
        assert f"const {reserved} " not in text and f"let {reserved} " not in text
    assert "a.expired" in execute and "EXECUTION_LOCK_ALREADY_EXISTS" in execute


def test_workflow_inventory_addendum_documents_the_workflow():
    assert "kr-alpha-discovery-tournament-v1.yml" in (ROOT / "docs/workflow-inventory-addendum.md").read_text()


def test_synthetic_world_and_real_adapters_share_one_translator_list():
    assert ST.TRANSLATORS[-1] == "BASELINE_0_PASSIVE" and set(T.PORTFOLIO_TRANSLATORS) | {"DECISION_FOCUSED_CHALLENGER"} == set(ST.TRANSLATORS)
