"""kr-market-risk-model-v1: frozen identity, outcome-free readiness, one-shot lifecycle, automatic Draft seal, prospective receipts and workflow.

The repository has exactly two valid lifecycle states and every test here is correct in both:

* PRE_SEAL  - the result, marker, manifest and seal provenance are all absent; readiness may report READY.
* POST_SEAL - all four exist together (the exact formal bytes, pinned byte-for-byte by test_kr_market_risk_model_v1_result_seal.py); readiness
  and authorization REFUSE any new formal execution, and that refusal is the correct, permanent behaviour of a sealed study - not a failure.

Synthetic lifecycle tests (readiness READY, the full gated execute path, a refused lock) run on `pre_seal_root`, an isolated copy of ONLY the frozen
preregistration inputs with no result files, so they exercise the real one-shot protections without depending on the state of the real repository.
Separate tests prove the real repository refuses re-execution. Synthetic values, synthetic repositories and fake GitHub APIs only; no test reads a
historical market value or computes a historical outcome."""
import ast
import hashlib
import io
import json
from pathlib import Path
import shutil
import zipfile

import numpy as np
import pandas as pd
import pytest
from pipeline import kr_market_risk_anatomy as M
from pipeline import kr_market_risk_model as K
from pipeline import kr_market_risk_model_execution as E
from pipeline import kr_market_risk_model_receipts as RCP
from pipeline import kr_market_risk_model_seal as SEAL

ROOT = Path(__file__).resolve().parents[1]
SPEC, SHA = E.load_spec(ROOT)
MAIN = "a" * 40
GOOD_ENV = {"GITHUB_ACTIONS": "true", "GITHUB_REF": "refs/heads/main", "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_SHA": MAIN,
            "GH_TOKEN": "t", "GITHUB_REPOSITORY": "o/r"}
WORKFLOW = (ROOT / ".github/workflows/kr-market-risk-model-v1.yml").read_text()
SEAL_FILES = (E.RESULT_PATH, E.MARKER_PATH, E.MANIFEST_PATH, SEAL.PROVENANCE_PATH)
ALREADY_COMMITTED = ["MARKET_RISK_MODEL_RESULT_ALREADY_COMMITTED", "MARKET_RISK_MODEL_MARKER_ALREADY_COMMITTED", "MARKET_RISK_MODEL_MANIFEST_ALREADY_COMMITTED"]


def repository_state(root=ROOT):
    """PRE_SEAL (no seal file) or POST_SEAL (all four). Any mixture is a broken repository and fails loudly instead of choosing a side."""
    present = {rel: (Path(root) / rel).exists() for rel in SEAL_FILES}
    if all(present.values()):
        return "POST_SEAL"
    if not any(present.values()):
        return "PRE_SEAL"
    raise AssertionError("PARTIAL_SEAL_STATE: " + json.dumps(present, sort_keys=True))


class FakeApi:
    def __init__(self, existing=()):
        self.refs, self.calls = {r: MAIN for r in existing}, []

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
        if method == "POST" and path == "/pulls":
            self.pr = payload
            return 201, {"number": 7, "draft": payload.get("draft")}
        return 405, {}


def fake_git(head=MAIN, committed=True):
    def git(args, root):
        if args[0] == "rev-parse":
            return (head + "\n").encode()
        return (Path(root) / args[1][len("HEAD:"):]).read_bytes() if committed else b"different"
    return git


def synthetic_values(seed=3):
    """Synthetic stand-ins with the real keys and calendar span. They are NOT market data."""
    rng = np.random.default_rng(seed)
    sessions = M.kr_sessions("2003-01-02", E.INHERITED["analysisEnd"])
    r = rng.normal(0.0003, 0.012, len(sessions))
    r[(sessions >= pd.Timestamp("2011-08-01")) & (sessions <= pd.Timestamp("2011-12-30"))] -= 0.004
    cal = pd.bdate_range("1995-01-02", E.INHERITED["analysisEnd"])
    us10y = pd.Series(3.0 + 0.3 * np.sin(np.arange(len(cal)) / 200.0), index=cal)
    us3m = pd.Series(2.0 + 1.6 * np.sin(np.arange(len(cal)) / 500.0), index=cal)
    vix = pd.Series(np.abs(19 + 7 * np.sin(np.arange(len(cal)) / 70.0) + rng.normal(0, 1.5, len(cal))) + 9, index=cal)
    return {"reference": pd.Series(100 * np.exp(np.cumsum(r)), index=sessions), "vix": vix, "us10y": us10y, "us3m": us3m}


# ---------------------------------------------------------------------------------------------------------------------------------------
# Frozen identity
# ---------------------------------------------------------------------------------------------------------------------------------------
def test_the_frozen_spec_carries_the_module_rules_the_development_label_and_no_outcome():
    assert SHA == (ROOT / "research_specs/kr-market-risk-model-v1.sha256").read_text().strip() and len(SHA) == 64
    assert SPEC["scientificStatus"] == "EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY" and SPEC["developmentStatement"] == K.DEVELOPMENT_STATEMENT
    assert SPEC["phase"] == "PREREGISTRATION_AND_HARNESS_ONLY_NO_OUTCOME_COMPUTED" and SPEC["outcomeAccess"]["inThisChange"] == "NONE"
    assert SPEC["boundary"]["isValidation"] is False and SPEC["boundary"]["usesMachineLearning"] is False
    revision = SPEC["preOutcomeRevisions"][0]
    assert revision["id"] == "NOMINATION_RULE_REVISION_1" and revision["madeBeforeAnyOutcome"] is True and revision["outcomeCountersAtRevision"] == "ALL_ZERO"
    assert SPEC["decision"]["tieBreak"].startswith("NONE") and SPEC["decision"]["severalSurvivors"] == K.NOMINATION_TRADEOFF
    assert SPEC["decision"]["routes"] == ["EFFICIENCY_ROUTE", "PROTECTION_ROUTE"] and "simplicityOrder" not in SPEC["decision"]
    assert [c["equityRiskMultiplier"] for c in SPEC["model"]["candidates"]["C1"]["table"]] == [c["equityRiskMultiplier"] for c in K.mapping_table("C1")]
    assert SPEC["inherited"] == {"primaryReference": "FDR_KS200", "analysisEnd": "2026-09-17", "vixRoleSource": "FRED_VIXCLS"}
    for rel in (".github/workflows/kr-market-risk-model-v1.yml", "docs/kr-market-risk-model-v1-design.md", "pipeline/kr_market_risk_model_seal.py",
                "pipeline/kr_market_risk_overlay.py", E.RECEIPT_SCHEMA_PATH):
        assert rel in SPEC["dependencyHashes"]
    assert repository_state() in ("PRE_SEAL", "POST_SEAL")                         # all four seal files exist together, or none does


def _copy_closure(tmp_path):
    for rel in list(SPEC["dependencyHashes"]) + [E.SPEC_PATH, "research_specs/kr-market-risk-model-v1.sha256"]:
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, target)
    return tmp_path


@pytest.fixture(scope="module")
def pre_seal_root(tmp_path_factory):
    """An isolated repository root holding ONLY the frozen preregistration inputs (spec, sidecar and every pinned file) and no result, marker,
    manifest or provenance. The real one-shot protections run unmodified against it; the real repository is never touched."""
    root = _copy_closure(tmp_path_factory.mktemp("pre_seal_root"))
    assert repository_state(root) == "PRE_SEAL"
    assert E.load_spec(root)[1] == SHA
    return root


def test_any_change_to_a_rule_a_pin_a_closure_file_or_the_spec_refuses_to_load(tmp_path, monkeypatch):
    root = _copy_closure(tmp_path)
    assert E.load_spec(root)[1] == SHA
    for rel, code in ((E.SNAPSHOT_DIR + "/FDR_KS200/normalized.csv", "HARNESS_OR_DEPENDENCY_CHANGED"),
                      ("docs/results/kr-market-risk-anatomy-v2-result.json", "HARNESS_OR_DEPENDENCY_CHANGED"),
                      ("pipeline/kr_market_risk_model.py", "HARNESS_OR_DEPENDENCY_CHANGED")):
        original = (root / rel).read_bytes()
        (root / rel).write_bytes(original + b"\n")
        with pytest.raises(ValueError, match=code):
            E.load_spec(root)
        (root / rel).write_bytes(original)
    spec = json.loads((root / E.SPEC_PATH).read_text())
    spec["decision"]["meaningfulDrawdownImprovement"] = 0.05
    (root / E.SPEC_PATH).write_text(json.dumps(spec))
    with pytest.raises(ValueError, match="SPEC_IDENTITY_CHANGED"):
        E.load_spec(root)
    shutil.copy2(ROOT / E.SPEC_PATH, root / E.SPEC_PATH)
    monkeypatch.setattr(K, "MEANINGFUL_DRAWDOWN_IMPROVEMENT", 0.05)
    with pytest.raises(ValueError, match="MODULE_RULE_DIFFERS_FROM_FROZEN_SPEC: decision"):
        E.load_spec(root)


def test_no_sealed_prior_study_file_changed_and_the_control_module_is_the_one_the_overlay_study_sealed():
    for rel, wanted in SPEC["predecessor"]["sealedArtifacts"].items():
        assert hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() == wanted
    overlay = json.loads((ROOT / "research_specs/kr-model-overlay-portfolio-v1.json").read_text())
    assert SPEC["dependencyHashes"]["pipeline/kr_market_risk_overlay.py"] == overlay["dependencyHashes"]["pipeline/kr_market_risk_overlay.py"]
    anatomy = json.loads((ROOT / "research_specs/kr-market-risk-anatomy-v2.json").read_text())
    for rel, wanted in anatomy["sourcePins"]["files"].items():
        key = E.SNAPSHOT_DIR + "/" + rel
        if key in SPEC["inputs"]["files"]:
            assert SPEC["inputs"]["files"][key] == wanted                          # the same immutable bytes the sealed anatomy read


# ---------------------------------------------------------------------------------------------------------------------------------------
# Outcome-free readiness and verify
# ---------------------------------------------------------------------------------------------------------------------------------------
def _spy_on_every_outcome_function(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("OUTCOME_FUNCTION_CALLED")
    for module, names in ((E, ("load_values", "evaluate", "claim_execution_lock", "write_execution_marker", "write_outputs")),
                          (K, ("replay_path", "development_nomination", "path_summary", "false_alarm_profile", "episode_capture", "rebound_cost")),
                          (M, ("forward_targets", "underwater_episodes")), (E.P, ("read_normalized",))):
        for name in names:
            monkeypatch.setattr(module, name, boom)


def test_readiness_and_verify_in_the_pre_seal_state_read_dates_only_and_report_ready(monkeypatch, pre_seal_root):
    _spy_on_every_outcome_function(monkeypatch)
    report = E.readiness_audit(pre_seal_root)
    assert report["decision"] == E.DECISION_READY and report["blockers"] == [] and all(v == 0 for v in report["counters"].values())
    assert report["firstDecisionDate"] == "2007-01-05" and report["referenceMissingSessionsFrom2006"] == []
    assert all(v["share"] >= E.MIN_DETERMINABLE_SHARE and v["firstDecisionDeterminable"] for v in report["determinable"].values())
    verified = E.verify(pre_seal_root, {})
    assert verified["status"] == "VERIFIED" and verified["stoppedBeforeOutcomes"] and verified["executeAuthorizedInThisEnvironment"] is False


def test_the_real_repository_is_ready_before_the_seal_and_recognised_as_sealed_after_it(monkeypatch):
    """Both states are valid. After the seal the ONLY reason readiness is not READY is that the study already ran: every date gate still passes."""
    _spy_on_every_outcome_function(monkeypatch)
    report, verified = E.readiness_audit(ROOT), E.verify(ROOT, {})
    assert all(v == 0 for v in report["counters"].values()) and report["checks"]["noOutcomeAccess"] is True
    assert verified["status"] == "VERIFIED" and verified["stoppedBeforeOutcomes"] and verified["executeAuthorizedInThisEnvironment"] is False
    if repository_state() == "PRE_SEAL":
        assert report["decision"] == E.DECISION_READY and report["blockers"] == []
        return
    assert report["decision"] != E.DECISION_READY and report["decision"] == E.DECISION_BLOCKED          # a sealed study is never READY again
    assert report["blockers"] == ALREADY_COMMITTED                                                       # ... and nothing else is wrong with it
    assert report["checks"]["frozenSpecPinsAndImportClosure"] is True and report["checks"]["referenceCompleteFrom2006"] is True
    assert all(v for k, v in report["checks"].items() if k.startswith("determinable_"))


def test_presence_proxy_gives_exactly_the_definedness_of_real_valued_inputs():
    values = synthetic_values()
    sessions = E.grid(values["reference"].index)
    spread = values["us10y"] - values["us3m"]
    real = K.layer_states(values["reference"].reindex(sessions), spread, values["vix"], sessions)
    proxy = K.layer_states(E.presence(values["reference"].index).reindex(sessions), E.presence(spread.index), E.presence(values["vix"].index), sessions)
    for col in ("slow", "transition", "fast"):
        assert (real[col].isna() == proxy[col].isna()).all()


# ---------------------------------------------------------------------------------------------------------------------------------------
# Authorization, lock, marker, values
# ---------------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("env, reason", [({"GITHUB_ACTIONS": ""}, "ACTIONS"), ({"GITHUB_REF": "refs/heads/x"}, "MAIN"),
                                         ({"GITHUB_EVENT_NAME": "pull_request"}, "WORKFLOW_DISPATCH"), ({"GITHUB_SHA": "b" * 40}, "DISPATCHED_COMMIT")])
def test_execute_is_actions_main_dispatch_only(env, reason):
    with pytest.raises(ValueError, match=reason):
        E.authorize_execution(SPEC, SHA, ROOT, dict(GOOD_ENV, **env), fake_git(), lambda: False)


def test_authorization_refuses_an_uncommitted_spec_any_committed_result_file_or_any_lock(pre_seal_root):
    """The real protections, run against the isolated pre-seal root: each committed file refuses on its own, then the lock."""
    with pytest.raises(ValueError, match="SPEC_NOT_COMMITTED_AT_HEAD"):
        E.authorize_execution(SPEC, SHA, pre_seal_root, GOOD_ENV, fake_git(committed=False), lambda: False)
    assert isinstance(E.authorize_execution(SPEC, SHA, pre_seal_root, GOOD_ENV, fake_git(), lambda: False), E.ExecutionPermit)
    with pytest.raises(ValueError, match="EXECUTION_LOCK_ALREADY_EXISTS"):
        E.authorize_execution(SPEC, SHA, pre_seal_root, GOOD_ENV, fake_git(), lambda: True)
    for rel, code in zip((E.RESULT_PATH, E.MARKER_PATH, E.MANIFEST_PATH), ALREADY_COMMITTED):
        target = pre_seal_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{}\n")
        try:
            with pytest.raises(ValueError, match=code):
                E.authorize_execution(SPEC, SHA, pre_seal_root, GOOD_ENV, fake_git(), lambda: False)
        finally:
            target.unlink()
    assert repository_state(pre_seal_root) == "PRE_SEAL"                           # the shared fixture root is left exactly as it was


def _load_runner():
    import importlib.util
    spec = importlib.util.spec_from_file_location("run_kr_market_risk_model_v1", ROOT / "scripts/run_kr_market_risk_model_v1.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_real_repository_refuses_every_new_formal_execution_once_sealed(tmp_path, monkeypatch):
    """A sealed study is permanently non-re-executable. Before the seal the same real repository is simply authorizable (the pre-seal protections are
    exercised on `pre_seal_root`); after it, every path to a new execution refuses BEFORE a lock is claimed or a value is read."""
    if repository_state() == "PRE_SEAL":
        assert isinstance(E.authorize_execution(SPEC, SHA, ROOT, GOOD_ENV, fake_git(), lambda: False), E.ExecutionPermit)
        return
    # 1. authorization: the committed result refuses first, whether or not a lock probe finds one (the lock is a second, independent barrier)
    for probe in (lambda: False, lambda: True):
        with pytest.raises(ValueError, match="MARKET_RISK_MODEL_RESULT_ALREADY_COMMITTED"):
            E.authorize_execution(SPEC, SHA, ROOT, GOOD_ENV, fake_git(), probe)
    # 2. each sealed file independently blocks authorization: remove nothing - prove it on copies of the real root with a single file missing
    for missing in (E.MARKER_PATH, E.MANIFEST_PATH):
        partial = tmp_path / ("without-" + Path(missing).name)
        _copy_closure(partial)
        for rel in SEAL_FILES:
            if rel != missing:
                (partial / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / rel, partial / rel)
        with pytest.raises(AssertionError, match="PARTIAL_SEAL_STATE"):
            repository_state(partial)
        with pytest.raises(ValueError, match="ALREADY_COMMITTED"):
            E.authorize_execution(SPEC, SHA, partial, GOOD_ENV, fake_git(), lambda: False)
    # 3. the durable lock tags recorded by the seal still refuse a second claim, using only GET
    provenance = json.loads((ROOT / SEAL.PROVENANCE_PATH).read_text())
    assert provenance["lockRefs"] == [E.STUDY_LOCK_REF, E.lock_ref(SHA)] and provenance["specSha256"] == SHA
    api = FakeApi(existing=provenance["lockRefs"])
    assert E.lock_exists(SHA, GOOD_ENV, api) is True
    with pytest.raises(ValueError, match="EXECUTION_LOCK_ALREADY_EXISTS"):
        E.claim_execution_lock(SHA, GOOD_ENV, api)
    assert {m for m, _ in api.calls} == {"GET"}
    # 4. the runner, which is what the workflow invokes: refuses before any lock, marker or value read (only git plumbing is faked, as above)
    monkeypatch.setattr(E, "_git", fake_git())
    for name in ("load_values", "claim_execution_lock", "write_execution_marker", "evaluate", "github_api"):
        monkeypatch.setattr(E, name, lambda *a, **k: (_ for _ in ()).throw(AssertionError("REACHED_AFTER_THE_SEAL")))
    out = tmp_path / "runner-output"
    with pytest.raises(ValueError, match="MARKET_RISK_MODEL_RESULT_ALREADY_COMMITTED"):
        _load_runner().run("execute", output=str(out), root=ROOT, env=dict(GOOD_ENV))
    assert not out.exists()
    # 5. the seal cannot be written a second time
    with pytest.raises(ValueError, match="RESULT_ALREADY_SEALED"):
        SEAL.check_main(ROOT)


def test_the_lock_is_study_level_exclusive_and_only_post_and_get_are_issued():
    api = FakeApi()
    lock = E.claim_execution_lock(SHA, GOOD_ENV, api)
    assert lock.ref == E.lock_ref(SHA) and set(api.refs) == {E.STUDY_LOCK_REF, E.lock_ref(SHA)}
    assert {m for m, _ in api.calls} <= {"GET", "POST"}
    with pytest.raises(ValueError, match="EXECUTION_LOCK_ALREADY_EXISTS"):
        E.claim_execution_lock(SHA, GOOD_ENV, api)
    with pytest.raises(ValueError, match="EXECUTION_LOCK_ALREADY_EXISTS"):
        E.claim_execution_lock("f" * 64, GOOD_ENV, api)                           # a revised spec cannot reopen the study
    with pytest.raises(ValueError, match="UNVERIFIABLE"):
        E.lock_exists(None, dict(GOOD_ENV, GH_TOKEN=""), FakeApi())


def test_values_and_outcomes_need_both_the_permit_and_the_lock():
    counters = E.Counters()
    with pytest.raises(ValueError, match="WITHOUT_PERMIT"):
        E.load_values(ROOT, counters, None, None, SHA)
    with pytest.raises(ValueError, match="LOCK_REQUIRED"):
        E.load_values(ROOT, counters, E.ExecutionPermit(SHA, E._PERMIT_TOKEN), None, SHA)
    with pytest.raises(ValueError, match="LOCK_REQUIRED"):
        E.evaluate({}, counters, E.ExecutionPermit(SHA, E._PERMIT_TOKEN), object(), SHA)
    assert counters.zero()


@pytest.fixture(scope="module")
def executed(tmp_path_factory, pre_seal_root):
    """The full execute path on SYNTHETIC values (load_values is replaced): records the order of every step."""
    order, api = [], FakeApi()
    real_readiness, real_claim, real_marker, real_evaluate = E.readiness_audit, E.claim_execution_lock, E.write_execution_marker, E.evaluate

    def load(root, counters, permit, lock, sha):
        E.require_permit(permit)
        E.require_lock(lock, sha)
        order.append("load_values")
        counters.valueReads += 4
        return synthetic_values()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(E, "readiness_audit", lambda root=pre_seal_root: order.append("readiness") or real_readiness(root))
        mp.setattr(E, "claim_execution_lock", lambda *a, **k: order.append("lock") or real_claim(*a, **k))
        mp.setattr(E, "write_execution_marker", lambda *a, **k: order.append("marker") or real_marker(*a, **k))
        mp.setattr(E, "load_values", load)
        mp.setattr(E, "evaluate", lambda *a, **k: order.append("evaluate") or real_evaluate(*a, **k))
        out = tmp_path_factory.mktemp("synthetic") / "run"
        manifest = E.execute(out, SPEC, SHA, E.ExecutionPermit(SHA, E._PERMIT_TOKEN), pre_seal_root, GOOD_ENV, api)
    return out, manifest, order, api


def test_lock_follows_every_gate_the_marker_follows_the_lock_and_values_and_artifacts_follow_both(executed):
    out, manifest, order, api = executed
    assert order == ["readiness", "lock", "marker", "load_values", "evaluate"]
    marker = json.loads((out / "execution-started.json").read_text())
    assert marker["valuesReadBeforeThisMarker"] == 0 and marker["lockRef"] == E.lock_ref(SHA) and marker["lockedMainSha"] == MAIN
    assert sorted(p.name for p in out.iterdir()) == sorted(E.ARTIFACT_FILES)
    assert manifest["counters"]["markerWrites"] == 1 and manifest["counters"]["valueReads"] == 4 and manifest["specSha256"] == SHA
    result = json.loads((out / "market-risk-model.json").read_text())
    assert result["decision"]["developmentNomination"] in K.CANDIDATE_ORDER[1:] + (K.NOMINATION_NONE, K.NOMINATION_TRADEOFF) and set(result["candidates"]) == set(K.CANDIDATE_ORDER)
    assert result["window"]["firstDecisionDate"] == "2007-01-05" and K.assert_no_forbidden_keys(result)
    for cid in K.CANDIDATE_ORDER:
        c = result["candidates"][cid]
        assert c["gross"]["annualizedReturn"] >= c["net"]["annualizedReturn"] and c["implementation"]["costDrag"] >= 0
        assert {"falseAlarm", "episodes", "halves", "calendarYears", "stress"} <= set(c)


def test_a_blocked_gate_creates_no_lock_no_marker_and_reads_no_value(tmp_path, monkeypatch, pre_seal_root):
    api = FakeApi()
    monkeypatch.setattr(E, "readiness_audit", lambda root=pre_seal_root: {"decision": E.DECISION_BLOCKED, "blockers": ["X"]})
    monkeypatch.setattr(E, "load_values", lambda *a, **k: (_ for _ in ()).throw(AssertionError("VALUE_READ")))
    with pytest.raises(ValueError, match="READINESS_GATE_BLOCKED"):
        E.execute(tmp_path / "o", SPEC, SHA, E.ExecutionPermit(SHA, E._PERMIT_TOKEN), pre_seal_root, GOOD_ENV, api)
    assert api.refs == {} and api.calls == [] and not (tmp_path / "o" / "execution-started.json").exists()
    assert not (tmp_path / "o" / "market-risk-model.json").exists()


def test_a_refused_lock_reads_no_value_and_writes_no_artifact(tmp_path, monkeypatch, pre_seal_root):
    api = FakeApi(existing=[E.STUDY_LOCK_REF])
    monkeypatch.setattr(E, "load_values", lambda *a, **k: (_ for _ in ()).throw(AssertionError("VALUE_READ")))
    with pytest.raises(ValueError, match="EXECUTION_LOCK_ALREADY_EXISTS"):
        E.execute(tmp_path / "o", SPEC, SHA, E.ExecutionPermit(SHA, E._PERMIT_TOKEN), pre_seal_root, GOOD_ENV, api)
    assert not (tmp_path / "o").exists() or not any((tmp_path / "o").iterdir())


# ---------------------------------------------------------------------------------------------------------------------------------------
# The automatic Draft seal
# ---------------------------------------------------------------------------------------------------------------------------------------
def _archive(out, extra=None):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        for name in E.ARTIFACT_FILES:
            z.writestr(name, (out / name).read_bytes())
        for name, data in (extra or {}).items():
            z.writestr(name, data)
    data = buffer.getvalue()
    return data, hashlib.sha256(data).hexdigest()


def test_the_seal_copies_the_exact_formal_bytes_and_opens_only_a_draft(executed, tmp_path, monkeypatch):
    out, _, _, _ = executed
    for name in ("evaluate", "load_values", "execute", "readiness_audit"):                # the seal path can never reach the harness
        monkeypatch.setattr(E, name, lambda *a, **k: (_ for _ in ()).throw(AssertionError("RERUN")))
    data, digest = _archive(out)
    files = SEAL.read_archive(data, digest)
    SEAL.verify_bundle(files, SHA, MAIN)
    api = FakeApi(existing=[SEAL.LOCK_PREFIX, SEAL.LOCK_PREFIX + "-" + SHA])
    SEAL.verify_locks(api, SHA, MAIN)
    root = tmp_path / "repo"
    (root / "research_specs").mkdir(parents=True)
    for rel in (E.SPEC_PATH, "research_specs/kr-market-risk-model-v1.sha256"):
        shutil.copy2(ROOT / rel, root / rel)
    assert SEAL.check_main(root) == SHA
    record = SEAL.write_seal(files, root, {"executionRunId": 1, "executionSha": MAIN, "artifactName": SEAL.RESULTS_ARTIFACT_PREFIX + "1", "artifactId": 2,
                                           "artifactArchiveSha256": digest, "specSha256": SHA})
    for name, rel in SEAL.COMMITTED.items():
        assert (root / rel).read_bytes() == (out / name).read_bytes()                 # byte-identical, never re-serialised
    assert SEAL.verify_written(root) == json.loads((root / SEAL.PROVENANCE_PATH).read_text())
    with pytest.raises(ValueError, match="ALREADY_SEALED"):
        SEAL.check_main(root)
    with pytest.raises(ValueError, match="ALREADY_SEALED"):
        SEAL.write_seal(files, root, {})
    number = SEAL.open_draft_pr(api, SEAL.SEAL_BRANCH_PREFIX + "1", "main", record)
    assert number == 7 and api.pr["draft"] is True and api.pr["base"] == "main"
    assert {m for m, _ in api.calls} <= {"GET", "POST"} and not any("merge" in p for _, p in api.calls)
    with pytest.raises(ValueError, match="NOT_REGISTERED"):
        SEAL.open_draft_pr(api, "feature/x", "main", record)
    with pytest.raises(ValueError, match="DRAFT_PULL_REQUEST_NOT_CREATED"):
        SEAL.open_draft_pr(lambda *a: (201, {"number": 8, "draft": False}), SEAL.SEAL_BRANCH_PREFIX + "1", "main", record)
    (root / SEAL.COMMITTED["market-risk-model.json"]).write_bytes(b"{}")
    with pytest.raises(ValueError, match="SEALED_FILE_CHANGED_BEFORE_PR"):
        SEAL.verify_written(root)


def test_the_seal_refuses_anything_but_the_exact_formal_artifact(executed):
    out, _, _, _ = executed
    data, digest = _archive(out)
    with pytest.raises(ValueError, match="ARCHIVE_SHA256_MISMATCH"):
        SEAL.read_archive(data + b"x", digest)
    extra, extra_digest = _archive(out, {"notes.txt": b"x"})
    with pytest.raises(ValueError, match="UNEXPECTED_ARTIFACT_FILE_LIST"):
        SEAL.read_archive(extra, extra_digest)
    files = SEAL.read_archive(data, digest)
    with pytest.raises(ValueError, match="SPEC_SHA_MISMATCH"):
        SEAL.verify_bundle(files, "f" * 64, MAIN)
    with pytest.raises(ValueError, match="LOCKED_COMMIT_MISMATCH"):
        SEAL.verify_bundle(files, SHA, "b" * 40)
    tampered = dict(files, **{"market-risk-model.json": files["market-risk-model.json"].replace(b"C0", b"C9", 1)})
    with pytest.raises(ValueError, match="MANIFEST_FILE_HASH_MISMATCH"):
        SEAL.verify_bundle(tampered, SHA, MAIN)
    meta = {"name": SEAL.RESULTS_ARTIFACT_PREFIX + "5", "expired": False, "workflow_run": {"id": 5}, "digest": "sha256:" + digest}
    assert SEAL.check_artifact_metadata(meta, 5) == digest
    for bad in ({"name": SEAL.ATTEMPT_ARTIFACT_PREFIX + "5"}, {"workflow_run": {"id": 6}}, {"expired": True}, {"digest": ""}):
        with pytest.raises(ValueError):
            SEAL.check_artifact_metadata(dict(meta, **bad), 5)
    with pytest.raises(ValueError, match="LOCK_REF_MISSING_OR_MOVED"):
        SEAL.verify_locks(FakeApi(existing=[SEAL.LOCK_PREFIX]), SHA, MAIN)
    good_run, good_jobs = {"event": "workflow_dispatch", "head_branch": "main", "head_sha": MAIN}, [{"name": "execute", "conclusion": "success"}]
    assert SEAL.verify_run(good_run, good_jobs, MAIN)
    for run, jobs in ((dict(good_run, event="push"), good_jobs), (dict(good_run, head_branch="x"), good_jobs), (dict(good_run, head_sha="b" * 40), good_jobs),
                      (good_run, [{"name": "execute", "conclusion": "failure"}])):
        with pytest.raises(ValueError):
            SEAL.verify_run(run, jobs, MAIN)


def _imports(path):
    names = set()
    for node in ast.walk(ast.parse(Path(path).read_text())):
        if isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
            names.update(node.module + "." + a.name if node.module == "pipeline" else a.name for a in node.names)
        elif isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
    return names


def test_the_seal_code_cannot_rerun_an_outcome_and_never_merges():
    assert _imports(ROOT / "pipeline/kr_market_risk_model_seal.py") <= {"__future__", "annotations", "hashlib", "io", "json", "pathlib", "Path", "zipfile"}
    script = _imports(ROOT / "scripts/seal_kr_market_risk_model_v1.py")
    assert {n for n in script if n.startswith("pipeline")} == {"pipeline", "pipeline.kr_market_risk_model_seal"}
    seal_job = WORKFLOW[WORKFLOW.index("\n  seal:"):]
    for text in ((ROOT / "pipeline/kr_market_risk_model_seal.py").read_text(), (ROOT / "scripts/seal_kr_market_risk_model_v1.py").read_text(), seal_job):
        for forbidden in ("/merge", "gh pr merge", "gh pr ready", "ready_for_review", "markPullRequestReadyForReview", "auto-merge", "--force", "push -f",
                          "run_kr_market_risk_model_v1", "--mode execute"):
            assert forbidden not in text, forbidden


# ---------------------------------------------------------------------------------------------------------------------------------------
# The workflow
# ---------------------------------------------------------------------------------------------------------------------------------------
def test_the_workflow_never_executes_or_seals_on_pull_requests_and_holds_minimal_permissions():
    execute = WORKFLOW[WORKFLOW.index("\n  execute:"):WORKFLOW.index("\n  seal:")]
    seal = WORKFLOW[WORKFLOW.index("\n  seal:"):]
    assert "pull_request:" in WORKFLOW and "schedule" not in WORKFLOW and "workflow_run" not in WORKFLOW and "gh workflow run" not in WORKFLOW
    assert "github.event_name == 'workflow_dispatch' && inputs.mode == 'execute'" in execute and "contents: write" in execute
    assert "pull-requests" not in execute and "listMatchingRefs" in execute and "RESULTS_ARTIFACT_ALREADY_EXISTS" in execute
    assert "kr-market-risk-model-v1-results-${{ github.run_id }}" in execute and "kr-market-risk-model-v1-attempt-${{ github.run_id }}" in execute
    assert "DO NOT RETRY" in execute
    assert "needs.execute.result == 'success'" in seal and "github.event_name == 'workflow_dispatch'" in seal and "pull-requests: write" in seal
    assert "kr-market-risk-model-v1-results-" in seal and "MAIN_ONLY" in seal and "open-pr" in seal
    assert "kr-market-risk-anatomy-v2-execution-lock" not in WORKFLOW and "run_kr_market_risk_anatomy" not in WORKFLOW


# ---------------------------------------------------------------------------------------------------------------------------------------
# Prospective receipts (designed here; nothing is written or scheduled)
# ---------------------------------------------------------------------------------------------------------------------------------------
def _receipt(day="2026-10-06", states=None, previous=None, arch="C1"):
    return RCP.build_receipt(signal_date=day, input_identities={"FDR_KS200": "0" * 64, "FRED_VIXCLS": "1" * 64},
                             layer_inputs={"vixPercentile": 0.9}, states=states or {"slow": 1, "transition": 0, "fast": 1}, spec_sha256=SHA,
                             code_identity={"commit": MAIN}, created_at_utc="2026-10-05T07:00:00Z", final_architecture=arch,
                             nomination_source="2" * 64, previous_multipliers=previous)


def test_a_receipt_records_every_candidate_the_final_multiplier_and_its_own_digest():
    r = _receipt()
    assert r["candidateMultipliers"] == {"C0": 0.7, "C1": 0.7, "C2": 0.7, "C3": 0.7} and r["finalEquityRiskMultiplier"] == 0.7
    assert r["executionDate"] == "2026-10-07" and r["receiptSha256"] == RCP.receipt_digest(r) and r["evidenceClass"] == "PROSPECTIVE_PAPER"
    schema = json.loads((ROOT / E.RECEIPT_SCHEMA_PATH).read_text())
    assert set(schema["required"]) == set(RCP.REQUIRED) | {"receiptSha256"} == set(r)
    held = _receipt(states={"slow": None, "transition": 0, "fast": 1}, previous={"C0": 1.0, "C1": 1.0, "C2": 0.7, "C3": 1.0})
    assert held["heldForMissingState"] == {"C0": False, "C1": True, "C2": False, "C3": True} and held["candidateMultipliers"]["C1"] == 1.0
    with pytest.raises(ValueError, match="WITHOUT_A_PREVIOUS_TARGET"):
        _receipt(states={"slow": None, "transition": 0, "fast": 1})
    with pytest.raises(ValueError, match="NOT_A_KR_SESSION"):
        _receipt(day="2026-10-05")                                                # a KR substitute holiday


def test_the_receipt_ledger_is_append_only_and_matures_only_on_the_calendar(tmp_path):
    ledger = tmp_path / "receipts.jsonl"
    RCP.append_receipt(ledger, _receipt("2026-10-06"))
    first = ledger.read_bytes()
    RCP.append_receipt(ledger, _receipt("2026-10-12"))
    assert ledger.read_bytes().startswith(first)                                  # earlier bytes are never rewritten
    with pytest.raises(ValueError, match="ALREADY_EXISTS"):
        RCP.append_receipt(ledger, _receipt("2026-10-12"))
    with pytest.raises(ValueError, match="OUT_OF_ORDER"):
        RCP.append_receipt(ledger, _receipt("2026-10-08"))
    tampered = dict(_receipt("2026-10-19"), finalEquityRiskMultiplier=1.0)
    with pytest.raises(ValueError):
        RCP.append_receipt(ledger, tampered)
    lines = ledger.read_text().splitlines()
    row = json.loads(lines[0])
    row["candidateMultipliers"]["C0"] = 1.0
    ledger.write_text(json.dumps(row) + "\n" + lines[1] + "\n")
    with pytest.raises(ValueError, match="DIGEST_MISMATCH"):
        RCP.read_ledger(ledger)
    r = _receipt("2026-10-06")
    assert not RCP.matured(r, "2026-11-02", 21) and RCP.matured(r, "2026-12-31", 21)
    with pytest.raises(ValueError, match="UNREGISTERED_HORIZON"):
        RCP.matured(r, "2027-12-31", 252)
