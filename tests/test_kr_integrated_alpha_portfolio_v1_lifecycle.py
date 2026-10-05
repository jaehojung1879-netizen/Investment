"""kr-integrated-alpha-portfolio-v1: frozen identity, outcome-free readiness, one-shot lifecycle, automatic Draft seal, prospective receipts and workflow.

The repository has exactly two valid lifecycle states and every test here is correct in both:

* PRE_SEAL  - the result, marker, manifest and seal provenance are all absent; readiness may report READY.
* POST_SEAL - all four exist together (pinned byte-for-byte by test_kr_integrated_alpha_portfolio_v1_result_seal.py); readiness and authorization
  REFUSE any new formal execution, and that refusal is the correct, permanent behaviour of a sealed study - not a failure.

Synthetic lifecycle tests run on `pre_seal_root`, an isolated copy of ONLY the frozen preregistration inputs with no result files, so they exercise the
real one-shot protections without depending on the state of the real repository. Separate tests prove the real repository refuses re-execution.
Invented values, synthetic repositories and fake GitHub APIs only; no test reads a historical market value or computes a historical outcome."""
import ast
import hashlib
import inspect
import io
import json
from pathlib import Path
import shutil
import zipfile

import numpy as np
import pandas as pd
import pytest
from pipeline import kr_integrated_alpha_portfolio as M
from pipeline import kr_integrated_alpha_portfolio_execution as E
from pipeline import kr_integrated_alpha_portfolio_receipts as RCP
from pipeline import kr_integrated_alpha_portfolio_replay as R
from pipeline import kr_integrated_alpha_portfolio_seal as SEAL
from pipeline import kr_market_risk_model as K

ROOT = Path(__file__).resolve().parents[1]
SPEC, SHA = E.load_spec(ROOT)
MAIN = "a" * 40
GOOD_ENV = {"GITHUB_ACTIONS": "true", "GITHUB_REF": "refs/heads/main", "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_SHA": MAIN, "GH_TOKEN": "t",
            "GITHUB_REPOSITORY": "o/r", E.INPUT_ARTIFACT_ENV: SPEC["input"]["artifactName"], E.INPUT_RUN_ENV: str(SPEC["input"]["producingRunId"])}
WORKFLOW = (ROOT / ".github/workflows/kr-integrated-alpha-portfolio-v1.yml").read_text()
SEAL_FILES = (E.RESULT_PATH, E.MARKER_PATH, E.MANIFEST_PATH, SEAL.PROVENANCE_PATH)
ALREADY_COMMITTED = ["INTEGRATED_PORTFOLIO_RESULT_ALREADY_COMMITTED", "INTEGRATED_PORTFOLIO_MARKER_ALREADY_COMMITTED", "INTEGRATED_PORTFOLIO_MANIFEST_ALREADY_COMMITTED"]


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
        self.refs, self.calls, self.pr = {r: MAIN for r in existing}, [], None

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


@pytest.fixture(scope="module")
def world():
    return E.synthetic_world()


# ---------------------------------------------------------------------------------------------------------------------------------------
# Frozen identity
# ---------------------------------------------------------------------------------------------------------------------------------------
def test_the_frozen_spec_carries_the_module_rules_the_development_label_and_no_outcome():
    assert SHA == (ROOT / "research_specs/kr-integrated-alpha-portfolio-v1.sha256").read_text().strip() and len(SHA) == 64
    assert SPEC["scientificStatus"] == "EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY" and SPEC["developmentStatement"] == M.DEVELOPMENT_STATEMENT
    assert SPEC["phase"] == "PREREGISTRATION_AND_HARNESS_ONLY_NO_OUTCOME_COMPUTED" and SPEC["outcomeAccess"]["inThisChange"] == "NONE"
    assert SPEC["boundary"]["isValidation"] is False and SPEC["boundary"]["usesMachineLearning"] is False and SPEC["boundary"]["mayRerunAnyPriorStudy"] is False
    assert SPEC["boundary"]["mayTuneAThresholdOrWeightFromOutcomes"] is False and SPEC["boundary"]["mayChangeC0OrC1"] is False
    assert SPEC["governance"]["lastLargeHistoricalArchitectureStudy"] is True and SPEC["preOutcomeRevisions"] == []
    assert list(SPEC["architectures"]["order"]) == list(M.ARCH_ORDER) and SPEC["architectures"]["matrix"]["F"] == {"name": "I+S+M1", "industry": True, "market": "C1"}
    assert SPEC["decision"]["finalArchitecture"]["noPostHocTieBreak"] is True and SPEC["decision"]["bands"]["source"].startswith("inherited unchanged")
    assert SPEC["portfolio"]["anchors"]["architectureSpecificTradingRules"] == "NONE" and SPEC["stockLayer"]["eligibility"]["noAbsoluteDoNotInvestThreshold"] is True
    assert SPEC["cashYield"]["changes"] == "ONLY the return earned by residual cash" and SPEC["marketLayer"]["c1Status"].startswith("SHADOW_CHALLENGER")
    for rel in (".github/workflows/kr-integrated-alpha-portfolio-v1.yml", "docs/kr-integrated-alpha-portfolio-v1-design.md", "pipeline/kr_integrated_alpha_portfolio_seal.py",
                E.RECEIPT_SCHEMA_PATH, M.CASH_YIELD["path"], "pipeline/kr_market_risk_model.py", "pipeline/kr_industry_anatomy.py", "pipeline/kr_stock_within_industry_anatomy.py"):
        assert rel in SPEC["dependencyHashes"]
    assert repository_state() in ("PRE_SEAL", "POST_SEAL")


def _copy_closure(tmp_path):
    for rel in list(SPEC["dependencyHashes"]) + [E.SPEC_PATH, E.SPEC_SIDECAR] + ["tests/" + name for name in SPEC["tests"]]:
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, target)
    return tmp_path


@pytest.fixture(scope="module")
def pre_seal_root(tmp_path_factory):
    """An isolated repository root holding ONLY the frozen preregistration inputs (spec, sidecar, every pinned file, the registered tests) and no result,
    marker, manifest or provenance. The real one-shot protections run unmodified against it; the real repository is never touched."""
    root = _copy_closure(tmp_path_factory.mktemp("pre_seal_root"))
    assert repository_state(root) == "PRE_SEAL"
    assert E.load_spec(root)[1] == SHA
    return root


def test_any_change_to_a_rule_a_pin_a_closure_file_or_the_spec_refuses_to_load(tmp_path, monkeypatch):
    root = _copy_closure(tmp_path)
    assert E.load_spec(root)[1] == SHA
    for rel in (M.CASH_YIELD["path"], "docs/results/kr-market-risk-model-v1-result.json", "pipeline/kr_market_risk_model.py", "pipeline/kr_integrated_alpha_portfolio_replay.py",
                "data/kr-industry-membership-foundation-v4/state/intervals.json.gz"):
        original = (root / rel).read_bytes()
        (root / rel).write_bytes(original + b"\n")
        with pytest.raises(ValueError, match="HARNESS_OR_DEPENDENCY_CHANGED"):
            E.load_spec(root)
        (root / rel).write_bytes(original)
    spec = json.loads((root / E.SPEC_PATH).read_text())
    spec["decision"]["bands"]["returnBandAnnual"] = 0.01
    (root / E.SPEC_PATH).write_text(json.dumps(spec))
    with pytest.raises(ValueError, match="SPEC_IDENTITY_CHANGED"):
        E.load_spec(root)
    shutil.copy2(ROOT / E.SPEC_PATH, root / E.SPEC_PATH)
    monkeypatch.setattr(M, "RETURN_BAND", 0.01)
    with pytest.raises(ValueError, match="BANDS_OR_LEVELS_DIFFER_FROM_THE_SEALED_MODEL"):          # the inherited bands are checked against the market model's own spec
        E.load_spec(root)
    monkeypatch.setattr(M, "RETURN_BAND", 0.005)
    monkeypatch.setattr(M, "MIN_ELIGIBLE_PER_DATE", 8)
    with pytest.raises(ValueError, match="MODULE_RULE_DIFFERS_FROM_FROZEN_SPEC: stockLayer"):
        E.load_spec(root)
    monkeypatch.setattr(M, "MIN_ELIGIBLE_PER_DATE", 10)
    monkeypatch.setitem(M.STOCK_WEIGHTS, "RISK_SCORE", 0.4)
    with pytest.raises(ValueError, match="MODULE_RULE_DIFFERS_FROM_FROZEN_SPEC: stockLayer"):
        E.load_spec(root)


def test_no_sealed_prior_study_file_changed_and_the_component_studies_are_byte_identical():
    """The market model, the industry anatomy, the stock within-industry anatomy and the overlay study are untouched: every pinned prior file, and every
    file each of those studies itself sealed, still hashes to what was sealed."""
    assert sorted(SPEC["priors"]["studies"]) == sorted(E.PRIOR_STUDIES) == sorted(SPEC["priors"]["neverRerun"])
    for rel, wanted in SPEC["priors"]["sealedArtifacts"].items():
        assert hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() == wanted
    for study in ("kr-market-risk-model-v1", "kr-industry-opportunity-anatomy-v1", "kr-stock-within-industry-anatomy-v1", "kr-model-overlay-portfolio-v1"):
        sealed = json.loads((ROOT / ("research_specs/" + study + ".json")).read_text())
        for rel, wanted in sealed["dependencyHashes"].items():
            if rel.startswith("tests/") or rel.endswith("workflow-inventory.md"):
                continue
            assert hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() == wanted, (study, rel)
        assert (ROOT / ("research_specs/" + study + ".sha256")).read_text().strip() == SPEC["priors"]["sealedArtifacts"]["research_specs/" + study + ".sha256"] \
            or ("research_specs/" + study + ".sha256") in SPEC["priors"]["sealedArtifacts"]
    for rel in ("docs/results/kr-market-risk-model-v1-result.json", "docs/results/kr-industry-opportunity-anatomy-v1-result.json",
                "docs/results/kr-stock-within-industry-anatomy-v1-result.json", "docs/results/kr-model-overlay-portfolio-v1-result.json"):
        assert rel in SPEC["priors"]["sealedArtifacts"]


def test_market_c0_and_c1_mappings_and_bytes_are_the_sealed_models_own():
    market = json.loads((ROOT / E.MARKET_SPEC).read_text())
    for cid in M.MARKET_CANDIDATES:
        assert SPEC["marketLayer"]["candidates"][cid]["table"] == market["model"]["candidates"][cid]["table"] == K.mapping_table(cid)
    assert SPEC["dependencyHashes"]["pipeline/kr_market_risk_model.py"] == market["dependencyHashes"]["pipeline/kr_market_risk_model.py"]
    assert hashlib.sha256((ROOT / "pipeline/kr_market_risk_model.py").read_bytes()).hexdigest() == market["dependencyHashes"]["pipeline/kr_market_risk_model.py"]
    assert tuple(market["model"]["levels"]) == K.LEVELS == (1.0, 0.7, 0.4)
    assert (M.RETURN_BAND, M.MEANINGFUL_DRAWDOWN_IMPROVEMENT, M.NON_INFERIORITY_DRAWDOWN_BAND) == (
        market["decision"]["returnBand"], market["decision"]["meaningfulDrawdownImprovement"], market["decision"]["nonInferiorityDrawdownBand"])
    # the market layer is the sealed model's own functions, not a copy
    assert M.K is K and E.K is K and R.K is K


def test_industry_and_stock_anatomy_bytes_and_the_membership_pins_are_unchanged():
    for study in ("kr-industry-opportunity-anatomy-v1", "kr-stock-within-industry-anatomy-v1"):
        sealed = json.loads((ROOT / ("research_specs/" + study + ".json")).read_text())
        for module in ("pipeline/kr_industry_anatomy.py", "pipeline/kr_stock_within_industry_anatomy.py"):
            if module in sealed["dependencyHashes"]:
                assert SPEC["dependencyHashes"][module] == sealed["dependencyHashes"][module]
    stock = json.loads((ROOT / E.STOCK_SPEC).read_text())
    assert stock["input"] == SPEC["input"] and stock["membership"] == SPEC["membership"]
    for rel, wanted in SPEC["membership"]["files"].items():
        assert SPEC["dependencyHashes"][rel] == wanted


def test_the_six_paths_differ_only_along_the_registered_axes(world, monkeypatch):
    """The same replay function, the same anchors, context, config and cost stress serve all six; only the underlying decisions (S or I+S) and the market
    table (none, C0, C1) differ."""
    seen = {}
    real = R.replay_architecture

    def spy(architecture, decisions, anchors, market_table, ctx, cfg=M.PORTFOLIO, **kwargs):
        seen[architecture] = {"decisions": id(decisions), "anchors": id(anchors), "table": None if market_table is None else id(market_table), "ctx": id(ctx), "cfg": id(cfg),
                              "kwargs": dict(kwargs)}
        return {"complete": False, "reason": "spy", "architecture": architecture}
    monkeypatch.setattr(R, "replay_architecture", spy)
    ctx = R.Context(world["prices"], world["market"], world["days"])
    permit, lock = E.ExecutionPermit(SHA, E._PERMIT_TOKEN), E.ExecutionLock(SHA, MAIN, "refs/tags/x", E._LOCK_TOKEN)
    E.run_architectures(world["decisions"], world["anchors"], world["tables"], ctx, E.Counters(), permit, lock, SHA, stresses=(1.0,))
    assert sorted(seen) == sorted(M.ARCH_ORDER)
    shared = {k: {s[k] for s in seen.values()} for k in ("anchors", "ctx", "cfg")}
    assert all(len(v) == 1 for v in shared.values())
    assert len({tuple(sorted(s["kwargs"].items())) for s in seen.values()}) == 1
    assert seen["A"]["decisions"] == seen["B"]["decisions"] == seen["C"]["decisions"] and seen["D"]["decisions"] == seen["E"]["decisions"] == seen["F"]["decisions"]
    assert seen["A"]["decisions"] != seen["D"]["decisions"]
    assert seen["A"]["table"] is None and seen["D"]["table"] is None and seen["B"]["table"] == seen["E"]["table"] and seen["C"]["table"] == seen["F"]["table"]
    assert seen["B"]["table"] != seen["C"]["table"]
    monkeypatch.setattr(R, "replay_architecture", real)
    # the architecture label is never read by the engine: swapping it changes nothing
    layer = {s: p["S"] for s, p in world["decisions"].items()}
    a = R.replay_architecture("A", layer, world["anchors"], None, ctx)
    f = R.replay_architecture("F", layer, world["anchors"], None, ctx)
    assert [r["nav"] for r in a["path"]] == [r["nav"] for r in f["path"]]
    parameters = list(inspect.signature(R.replay_architecture).parameters)
    assert parameters[:5] == ["architecture", "decisions", "anchors", "market_table", "ctx"]


# ---------------------------------------------------------------------------------------------------------------------------------------
# Outcome-free readiness and verify
# ---------------------------------------------------------------------------------------------------------------------------------------
def _spy_on_every_real_input_and_outcome_function(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("REAL_INPUT_OR_OUTCOME_FUNCTION_CALLED")
    for name in ("build_signal_bundle", "load_market_values", "market_tables", "assemble", "claim_execution_lock", "write_execution_marker", "write_outputs", "github_api"):
        monkeypatch.setattr(E, name, boom)
    for name in ("load_sources", "prepare", "build_labels", "input_identity"):
        monkeypatch.setattr(E.X, name, boom)


def test_readiness_and_verify_in_the_pre_seal_state_touch_no_real_input_and_report_ready(monkeypatch, pre_seal_root):
    seen_tickers = set()
    real = R.replay_architecture

    def record(architecture, decisions, anchors, market_table, ctx, *a, **k):
        seen_tickers.update(ctx.prices)
        return real(architecture, decisions, anchors, market_table, ctx, *a, **k)
    _spy_on_every_real_input_and_outcome_function(monkeypatch)
    monkeypatch.setattr(R, "replay_architecture", record)
    report = E.readiness_audit(pre_seal_root)
    assert report["decision"] == E.DECISION_READY and report["blockers"] == [] and all(v == 0 for v in report["counters"].values())
    assert report["checks"]["syntheticSixPathWorldCompleteAndDeterministic"] is True and report["checks"]["noOutcomeAccess"] is True
    assert seen_tickers and all(t.startswith("T") or t == M.BENCHMARK for t in seen_tickers)                # invented tickers only: no real price was read
    assert report["marketPresence"]["ok"] and report["marketPresence"]["firstDecisionDate"] == "2007-01-05"
    depth = report["membershipDepthUpperBounds"]
    assert depth["classifiedStocksInEligibleIndustriesPerDate"]["min"] >= M.MIN_ELIGIBLE_PER_DATE and depth["eligibleIndustriesPerDate"]["min"] >= M.MIN_INDUSTRIES_RANKED
    assert report["cashYieldSource"]["status"] == "FROZEN_PROXY" and report["cashYieldSource"]["coversFeatureStart"] is True
    assert report["basedOnAnyReturnResult"] is False and report["historicalExecutionPerformed"] is False and report["anchors"] == depth["anchors"]
    verified = E.verify(pre_seal_root, {})
    assert verified["status"] == "VERIFIED" and verified["stoppedBeforeOutcomes"] and verified["executeAuthorizedInThisEnvironment"] is False
    assert all(v == 0 for v in verified["counters"].values())


def test_the_real_repository_is_ready_before_the_seal_and_recognised_as_sealed_after_it(monkeypatch):
    """Both states are valid. After the seal the ONLY reason readiness is not READY is that the study already ran: every other gate still passes."""
    _spy_on_every_real_input_and_outcome_function(monkeypatch)
    report, verified = E.readiness_audit(ROOT), E.verify(ROOT, {})
    assert all(v == 0 for v in report["counters"].values()) and report["checks"]["noOutcomeAccess"] is True
    assert verified["status"] == "VERIFIED" and verified["stoppedBeforeOutcomes"] and verified["executeAuthorizedInThisEnvironment"] is False
    if repository_state() == "PRE_SEAL":
        assert report["decision"] == E.DECISION_READY and report["blockers"] == []
        return
    assert report["decision"] == E.DECISION_BLOCKED and report["blockers"] == ALREADY_COMMITTED
    assert report["checks"]["frozenSpecPinsAndImportClosure"] is True and report["checks"]["syntheticSixPathWorldCompleteAndDeterministic"] is True


def test_verify_and_readiness_never_issue_a_github_call_so_no_lock_or_dispatch_can_exist(monkeypatch, pre_seal_root):
    api = FakeApi()
    monkeypatch.setattr(E, "github_api", api)
    E.verify(pre_seal_root, {})
    assert api.calls == [] and api.refs == {}
    assert "workflow_dispatch" in WORKFLOW and "gh workflow run" not in WORKFLOW and "actions_run_trigger" not in WORKFLOW


# ---------------------------------------------------------------------------------------------------------------------------------------
# Authorization, lock, marker
# ---------------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("env, reason", [({"GITHUB_ACTIONS": ""}, "ACTIONS"), ({"GITHUB_REF": "refs/heads/x"}, "MAIN"),
                                         ({"GITHUB_EVENT_NAME": "pull_request"}, "WORKFLOW_DISPATCH"), ({"GITHUB_SHA": "b" * 40}, "DISPATCHED_COMMIT"),
                                         ({E.INPUT_ARTIFACT_ENV: "other"}, "INPUT_ARTIFACT_IDENTITY_MISMATCH"), ({E.INPUT_RUN_ENV: "1"}, "INPUT_ARTIFACT_IDENTITY_MISMATCH")])
def test_execute_is_actions_main_dispatch_on_the_exact_preserved_artifact_only(env, reason):
    with pytest.raises(ValueError, match=reason):
        E.authorize_execution(SPEC, SHA, ROOT, dict(GOOD_ENV, **env), fake_git(), lambda: False)


def test_authorization_refuses_an_uncommitted_spec_any_committed_result_file_or_any_lock(pre_seal_root):
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
    assert repository_state(pre_seal_root) == "PRE_SEAL"


def _load_runner():
    import importlib.util
    spec = importlib.util.spec_from_file_location("run_kr_integrated_alpha_portfolio_v1", ROOT / "scripts/run_kr_integrated_alpha_portfolio_v1.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_real_repository_refuses_every_new_formal_execution_once_sealed(tmp_path, monkeypatch):
    """A sealed study is permanently non-re-executable. Before the seal the real repository is simply authorizable; after it, every path to a new execution
    refuses BEFORE a lock is claimed or a value is read."""
    if repository_state() == "PRE_SEAL":
        assert isinstance(E.authorize_execution(SPEC, SHA, ROOT, GOOD_ENV, fake_git(), lambda: False), E.ExecutionPermit)
        return
    for probe in (lambda: False, lambda: True):
        with pytest.raises(ValueError, match="INTEGRATED_PORTFOLIO_RESULT_ALREADY_COMMITTED"):
            E.authorize_execution(SPEC, SHA, ROOT, GOOD_ENV, fake_git(), probe)
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
    provenance = json.loads((ROOT / SEAL.PROVENANCE_PATH).read_text())
    assert provenance["lockRefs"] == [E.STUDY_LOCK_REF, E.lock_ref(SHA)] and provenance["specSha256"] == SHA
    api = FakeApi(existing=provenance["lockRefs"])
    assert E.lock_exists(SHA, GOOD_ENV, api) is True
    with pytest.raises(ValueError, match="EXECUTION_LOCK_ALREADY_EXISTS"):
        E.claim_execution_lock(SHA, GOOD_ENV, api)
    assert {m for m, _ in api.calls} == {"GET"}
    monkeypatch.setattr(E, "_git", fake_git())
    for name in ("build_signal_bundle", "claim_execution_lock", "write_execution_marker", "load_market_values", "github_api"):
        monkeypatch.setattr(E, name, lambda *a, **k: (_ for _ in ()).throw(AssertionError("REACHED_AFTER_THE_SEAL")))
    out = tmp_path / "runner-output"
    with pytest.raises(ValueError, match="INTEGRATED_PORTFOLIO_RESULT_ALREADY_COMMITTED"):
        _load_runner().run("execute", input_root=str(tmp_path), output=str(out), root=ROOT, env=dict(GOOD_ENV))
    assert not out.exists()
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
    assert E.STUDY_LOCK_REF == "refs/tags/kr-integrated-alpha-portfolio-v1-execution-lock"


def test_market_values_and_portfolio_valuation_need_both_the_permit_and_the_lock(world):
    counters = E.Counters()
    permit = E.ExecutionPermit(SHA, E._PERMIT_TOKEN)
    with pytest.raises(ValueError, match="WITHOUT_PERMIT"):
        E.load_market_values(ROOT, counters, None, None, SHA)
    with pytest.raises(ValueError, match="LOCK_REQUIRED"):
        E.load_market_values(ROOT, counters, permit, None, SHA)
    ctx = R.Context(world["prices"], world["market"], world["days"])
    with pytest.raises(ValueError, match="LOCK_REQUIRED"):
        E.run_architectures(world["decisions"], world["anchors"], world["tables"], ctx, counters, permit, object(), SHA)
    with pytest.raises(ValueError, match="WITHOUT_PERMIT"):
        E.assemble({}, {}, [], {}, counters, ROOT, SPEC, None, None, SHA)
    assert counters.zero()


# ---------------------------------------------------------------------------------------------------------------------------------------
# The registered gates
# ---------------------------------------------------------------------------------------------------------------------------------------
def gate_bundle(world, **overrides):
    signals = sorted({s for _, s in world["anchors"]})
    rows = [{"date": s, "ticker": t, "marketCap": 1e12, "accountingProvenance": {"availableFrom": "2000-01-01"}} for s in signals for t in world["tickers"]]
    depth = {s: {"eligibleS": 12, "eligibleIS": 12, "industriesRanked": 6, "eligibleIndustries": 6, "members": 12, "classifiedInEligibleIndustry": 12} for s in signals}
    bundle = {"features": pd.DataFrame(rows), "schedule": {s: sorted(world["tickers"]) for s in signals}, "anchors": world["anchors"], "depth": depth}
    bundle.update(overrides)
    return bundle


def test_pre_lock_gates_stop_a_short_book_an_unrankable_industry_layer_and_bad_signal_inputs(world, monkeypatch):
    bundle = gate_bundle(world)
    monkeypatch.setattr(E, "v4_schedule", lambda root: dict(bundle["schedule"]))
    assert E.pre_lock_gates(bundle, SPEC, ROOT) == []
    signal = world["anchors"][3][1]
    short = gate_bundle(world)
    short["depth"][signal] = dict(short["depth"][signal], eligibleS=M.MIN_ELIGIBLE_PER_DATE - 1, eligibleIS=M.MIN_ELIGIBLE_PER_DATE - 1, industriesRanked=M.MIN_INDUSTRIES_RANKED - 1)
    assert set(E.pre_lock_gates(short, SPEC, ROOT)) == {"STOCK_DEPTH_BELOW_MINIMUM:S:" + signal, "STOCK_DEPTH_BELOW_MINIMUM:I+S:" + signal, "INDUSTRY_LAYER_UNRANKABLE:" + signal}
    duplicated = gate_bundle(world)
    duplicated["features"] = pd.concat([duplicated["features"], duplicated["features"].iloc[:1]], ignore_index=True)
    assert "DUPLICATE_PIT_NAME_DATE" in E.pre_lock_gates(duplicated, SPEC, ROOT)
    lookahead = gate_bundle(world)
    provenance = list(lookahead["features"]["accountingProvenance"])
    provenance[0] = {"availableFrom": "2999-01-01"}
    lookahead["features"]["accountingProvenance"] = provenance
    assert "ACCOUNTING_PUBLICATION_NOT_STRICTLY_PRIOR" in E.pre_lock_gates(lookahead, SPEC, ROOT)
    nocap = gate_bundle(world)
    nocap["features"]["marketCap"] = np.nan
    assert "MARKET_CAP_UNAVAILABLE" in E.pre_lock_gates(nocap, SPEC, ROOT)
    monkeypatch.setattr(E, "v4_schedule", lambda root: {s: ["OTHER.KS"] for s in bundle["schedule"]})
    assert any(r.startswith("PIT_TOP120_DIFFERS_FROM_V4_MEMBERSHIP_UNIVERSE") for r in E.pre_lock_gates(bundle, SPEC, ROOT))
    assert E.pre_lock_gates(dict(bundle, anchors=[]), SPEC, ROOT) == ["NO_PIT_NAME_DATES_OR_ANCHORS"]


# ---------------------------------------------------------------------------------------------------------------------------------------
# The full gated execute path on INVENTED inputs
# ---------------------------------------------------------------------------------------------------------------------------------------
def synthetic_bundle(world):
    depth = {s: {"eligibleS": p["S"]["eligibleCount"], "eligibleIS": p["I+S"]["eligibleCount"], "industriesRanked": 6, "eligibleIndustries": 6, "members": 12,
                 "classifiedInEligibleIndustry": 12} for s, p in world["decisions"].items()}
    return {"features": pd.DataFrame(), "schedule": {}, "decisions": world["decisions"], "depth": depth, "anchors": world["anchors"], "days": world["days"],
            "prices": world["prices"], "market": world["market"]}


@pytest.fixture(scope="module")
def executed(tmp_path_factory, pre_seal_root, world):
    """The full execute path on invented inputs (the raw artifact, the market values and the signal assembly are replaced): records the order of every step."""
    order, api = [], FakeApi()
    real = {n: getattr(E, n) for n in ("claim_execution_lock", "write_execution_marker", "run_architectures", "assemble", "write_outputs")}

    def load(root, counters, permit, lock, sha):
        E.require_permit(permit)
        E.require_lock(lock, sha)
        order.append("values")
        counters.marketValueReads += 4
        return {}

    def tables(values, counters, cutoff):
        order.append("tables")
        counters.marketStateComputations += 1
        return world["tables"]
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(E.X, "input_identity", lambda root: {"sha256": SPEC["input"]["identitySha256"]})
        mp.setattr(E, "build_signal_bundle", lambda input_root, spec, root, counters: order.append("bundle") or setattr(counters, "featureBuilds", counters.featureBuilds + 1)
                   or synthetic_bundle(world))
        mp.setattr(E, "readiness_audit", lambda root=pre_seal_root: order.append("readiness") or {"decision": E.DECISION_READY, "blockers": []})
        mp.setattr(E, "pre_lock_gates", lambda bundle, spec, root: order.append("gates") or [])
        mp.setattr(E, "claim_execution_lock", lambda *a, **k: order.append("lock") or real["claim_execution_lock"](*a, **k))
        mp.setattr(E, "write_execution_marker", lambda *a, **k: order.append("marker") or real["write_execution_marker"](*a, **k))
        mp.setattr(E, "load_market_values", load)
        mp.setattr(E, "market_tables", tables)
        mp.setattr(E, "run_architectures", lambda *a, **k: order.append("run") or real["run_architectures"](*a, **k))
        mp.setattr(E, "assemble", lambda *a, **k: order.append("assemble") or real["assemble"](*a, **k))
        out = tmp_path_factory.mktemp("synthetic") / "run"
        manifest = E.execute(str(out.parent), out, SPEC, SHA, E.ExecutionPermit(SHA, E._PERMIT_TOKEN), pre_seal_root, GOOD_ENV, api)
    return out, manifest, order, api


def test_gates_precede_the_lock_the_marker_follows_it_and_values_and_portfolios_follow_both(executed):
    out, manifest, order, api = executed
    assert order == ["bundle", "readiness", "gates", "lock", "marker", "values", "tables", "run", "assemble"]
    marker = json.loads((out / "execution-started.json").read_text())
    assert marker["valuesReadBeforeThisMarker"] == 0 and marker["featureBuildsBeforeThisMarker"] == 1
    assert marker["lockRef"] == E.lock_ref(SHA) and marker["lockedMainSha"] == MAIN and marker["studyLockRef"] == E.STUDY_LOCK_REF
    assert sorted(p.name for p in out.iterdir()) == sorted(E.ARTIFACT_FILES)
    counters = manifest["counters"]
    assert counters["markerWrites"] == 1 and counters["marketValueReads"] == 4 and counters["replayCalls"] == 18 and counters["featureBuilds"] == 1
    assert manifest["specSha256"] == SHA and manifest["files"]["execution-started.json"] == hashlib.sha256((out / "execution-started.json").read_bytes()).hexdigest()
    assert {m for m, _ in api.calls} <= {"GET", "POST"} and set(api.refs) == {E.STUDY_LOCK_REF, E.lock_ref(SHA)}


def test_the_result_carries_six_paths_the_registered_comparisons_and_a_mechanical_layer_decision(executed):
    out, _, _, _ = executed
    result = json.loads((out / E.RESULT_FILE).read_text())
    assert result["scientificStatus"] == "EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY" and result["developmentStatement"] == M.DEVELOPMENT_STATEMENT
    assert result["returnBasis"] == M.RETURN_BASIS and result["benchmark"] == "069500.KS" and M.assert_no_forbidden_keys(result) is None
    assert sorted(result["summaries"]) == list(M.ARCH_ORDER) and all(s["complete"] for s in result["summaries"].values())
    assert sorted(result["costStress"]["A"]) == ["x2", "x3"] and sorted(result["monthEndNav"]) == list(M.ARCH_ORDER) and result["passive"]["id"] == M.PASSIVE
    assert [(r["candidate"], r["base"]) for r in result["comparisons"]] == [(c, b) for _, _, c, b in M.COMPARISONS]
    assert set(result["attribution"]) == {"industryOnVsOff", "c0VsOff", "c1VsOff", "c1VsC0"} and set(result["interaction"]) == {"C0", "C1"}
    decision = result["layerDecisions"]
    assert set(decision) >= {"industry", "market", "finalArchitecture"} and decision["finalArchitecture"] in set(M.ARCH_ORDER) | {M.NO_UNAMBIGUOUS, M.NO_FINAL_BLOCKED}
    for a, s in result["summaries"].items():
        assert s["cashYield"]["status"] == "COMPUTED" and set(s["cashYield"]["variants"]) == {"ZERO", "PROXY", "PROXY_MINUS_HAIRCUT"}
        assert s["cashYield"]["variants"]["ZERO"]["netAnnualizedReturn"] == pytest.approx(s["netAnnualizedReturn"])
        assert s["cashYield"]["variants"]["PROXY"]["netAnnualizedReturn"] >= s["netAnnualizedReturn"] - 1e-12
        assert s["annualizedCostDrag"] >= 0 and s["netAnnualizedReturn"] > -1
    assert result["cashYieldSource"]["status"] == "FROZEN_PROXY" and result["stockLayerDepth"]["minimumEligiblePerDate"] == M.MIN_ELIGIBLE_PER_DATE
    assert result["underlyingAudit"]["identicalUnderlyingPerAxis"] is True and any("not validation" in s for s in result["statements"])


def test_a_blocked_gate_creates_no_lock_no_marker_and_reads_no_value(tmp_path, monkeypatch, pre_seal_root, world):
    api = FakeApi()
    monkeypatch.setattr(E.X, "input_identity", lambda root: {"sha256": SPEC["input"]["identitySha256"]})
    monkeypatch.setattr(E, "build_signal_bundle", lambda input_root, spec, root, counters: synthetic_bundle(world))
    monkeypatch.setattr(E, "readiness_audit", lambda root=pre_seal_root: {"decision": E.DECISION_READY, "blockers": []})
    monkeypatch.setattr(E, "pre_lock_gates", lambda bundle, spec, root: ["STOCK_DEPTH_BELOW_MINIMUM:S:2017-01-06"])
    monkeypatch.setattr(E, "load_market_values", lambda *a, **k: (_ for _ in ()).throw(AssertionError("VALUE_READ")))
    with pytest.raises(ValueError, match="READINESS_GATE_FAILED"):
        E.execute(str(tmp_path), tmp_path / "o", SPEC, SHA, E.ExecutionPermit(SHA, E._PERMIT_TOKEN), pre_seal_root, GOOD_ENV, api)
    assert api.refs == {} and api.calls == [] and not (tmp_path / "o" / "execution-started.json").exists() and not (tmp_path / "o" / E.RESULT_FILE).exists()
    failed = json.loads((tmp_path / "o" / "gates-failed.json").read_text())
    assert failed["reasons"] == ["STOCK_DEPTH_BELOW_MINIMUM:S:2017-01-06"] and failed["depth"]["anchors"] == len(world["anchors"]) and failed["counters"]["marketValueReads"] == 0


def test_a_wrong_input_identity_stops_before_anything_is_read(tmp_path, monkeypatch, pre_seal_root):
    monkeypatch.setattr(E.X, "input_identity", lambda root: {"sha256": "0" * 64})
    monkeypatch.setattr(E, "build_signal_bundle", lambda *a, **k: (_ for _ in ()).throw(AssertionError("BUNDLE_BUILT")))
    with pytest.raises(ValueError, match="INPUT_IDENTITY_MISMATCH"):
        E.execute(str(tmp_path), tmp_path / "o", SPEC, SHA, E.ExecutionPermit(SHA, E._PERMIT_TOKEN), pre_seal_root, GOOD_ENV, FakeApi())


def test_a_refused_lock_reads_no_value_and_writes_no_artifact(tmp_path, monkeypatch, pre_seal_root, world):
    api = FakeApi(existing=[E.STUDY_LOCK_REF])
    monkeypatch.setattr(E.X, "input_identity", lambda root: {"sha256": SPEC["input"]["identitySha256"]})
    monkeypatch.setattr(E, "build_signal_bundle", lambda input_root, spec, root, counters: synthetic_bundle(world))
    monkeypatch.setattr(E, "readiness_audit", lambda root=pre_seal_root: {"decision": E.DECISION_READY, "blockers": []})
    monkeypatch.setattr(E, "pre_lock_gates", lambda bundle, spec, root: [])
    monkeypatch.setattr(E, "load_market_values", lambda *a, **k: (_ for _ in ()).throw(AssertionError("VALUE_READ")))
    with pytest.raises(ValueError, match="EXECUTION_LOCK_ALREADY_EXISTS"):
        E.execute(str(tmp_path), tmp_path / "o", SPEC, SHA, E.ExecutionPermit(SHA, E._PERMIT_TOKEN), pre_seal_root, GOOD_ENV, api)
    assert not (tmp_path / "o").exists() or not any((tmp_path / "o").iterdir())


def test_a_blocked_path_is_reported_and_makes_the_dependent_layers_unevaluable(world):
    ctx = R.Context(world["prices"], world["market"], world["days"])
    permit, lock = E.ExecutionPermit(SHA, E._PERMIT_TOKEN), E.ExecutionLock(SHA, MAIN, "refs/tags/x", E._LOCK_TOKEN)
    results = E.run_architectures(world["decisions"], world["anchors"], world["tables"], ctx, E.Counters(), permit, lock, SHA, stresses=(1.0,))
    results[("E", 1.0)] = {"complete": False, "reason": R.UNRESOLVED + ": T01.KS:2017-03-01", "architecture": "E"}
    for arch in M.ARCH_ORDER:
        for stress in (2.0, 3.0):
            results[(arch, stress)] = results[(arch, 1.0)]
    assembled = E.assemble(results, world["decisions"], world["anchors"], {s: {"eligibleS": 12, "eligibleIS": 12, "industriesRanked": 6} for s in world["decisions"]},
                           E.Counters(), ROOT, SPEC, E.ExecutionPermit(SHA, E._PERMIT_TOKEN), E.ExecutionLock(SHA, MAIN, "refs/tags/x", E._LOCK_TOKEN), SHA)
    assert assembled["blockedPaths"] == {"E": results[("E", 1.0)]["reason"]} and assembled["summaries"]["E"]["complete"] is False
    assert assembled["layerDecisions"]["industry"]["layerDecision"] == "INDUSTRY_LAYER_NOT_EVALUABLE_BLOCKED_PATH"
    assert assembled["layerDecisions"]["finalArchitecture"] == M.NO_FINAL_BLOCKED


# ---------------------------------------------------------------------------------------------------------------------------------------
# The market layer through the sealed model, on committed source files only
# ---------------------------------------------------------------------------------------------------------------------------------------
def test_market_tables_are_the_sealed_models_own_targets(monkeypatch):
    counters, permit = E.Counters(), E.ExecutionPermit(SHA, E._PERMIT_TOKEN)
    lock = E.ExecutionLock(SHA, MAIN, "refs/tags/x", E._LOCK_TOKEN)
    values = E.load_market_values(ROOT, counters, permit, lock, SHA)
    assert counters.marketValueReads == len(E.MX.SOURCES)
    tables = E.market_tables(values, counters, SPEC["developmentCutoff"])
    assert counters.marketStateComputations == 1 and sorted(tables) == ["C0", "C1"]
    for cid, table in tables.items():
        assert set(table.target) <= set(K.LEVELS) and str(table.decisionDate.iloc[0].date()) == "2007-01-05" and table.executionDate.iloc[-1] <= pd.Timestamp(SPEC["developmentCutoff"])
        assert (table.executionDate > table.decisionDate).all() and table.executionDate.is_monotonic_increasing
    sessions = E.MX.grid(values["reference"].index)
    spread = E.AN.derived_spread(values["us10y"], values["us3m"])
    states = K.layer_states(values["reference"].reindex(sessions), spread, values["vix"], sessions, E.MS.lag_days(E.MX.SOURCES["us10y"]), E.MS.lag_days(E.MX.SOURCES["vix"]))
    schedule = K.decision_schedule(sessions, K.EVALUATION_START, SPEC["developmentCutoff"])
    direct = K.candidate_targets(states, schedule, "C1")
    assert tables["C1"].target.tolist() == direct.target.tolist() and tables["C1"].heldForMissingState.tolist() == direct.heldForMissingState.tolist()
    # the mapping used at each decision is the frozen C0 / C1 table
    probe = states.loc[tables["C0"].decisionDate.iloc[500]]
    assert tables["C0"].target.iloc[500] in (K.multiplier("C0", probe["slow"], probe["transition"], probe["fast"]), tables["C0"].target.iloc[499])
    assert counters.replayCalls == 0 and counters.metricCalls == 0


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
    for name in ("run_architectures", "load_market_values", "execute", "readiness_audit", "assemble"):                # the seal path can never reach the harness
        monkeypatch.setattr(E, name, lambda *a, **k: (_ for _ in ()).throw(AssertionError("RERUN")))
    data, digest = _archive(out)
    files = SEAL.read_archive(data, digest)
    SEAL.verify_bundle(files, SHA, MAIN)
    api = FakeApi(existing=[SEAL.LOCK_PREFIX, SEAL.LOCK_PREFIX + "-" + SHA])
    SEAL.verify_locks(api, SHA, MAIN)
    root = tmp_path / "repo"
    (root / "research_specs").mkdir(parents=True)
    for rel in (E.SPEC_PATH, E.SPEC_SIDECAR):
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
    (root / SEAL.COMMITTED["integrated-alpha-portfolio.json"]).write_bytes(b"{}")
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
    tampered = dict(files, **{"integrated-alpha-portfolio.json": files["integrated-alpha-portfolio.json"].replace(b"EXPLORATORY", b"EXPLORATOR9", 1)})
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
    assert _imports(ROOT / "pipeline/kr_integrated_alpha_portfolio_seal.py") <= {"__future__", "annotations", "hashlib", "io", "json", "pathlib", "Path", "zipfile"}
    script = _imports(ROOT / "scripts/seal_kr_integrated_alpha_portfolio_v1.py")
    assert {n for n in script if n.startswith("pipeline")} == {"pipeline", "pipeline.kr_integrated_alpha_portfolio_seal"}
    seal_job = WORKFLOW[WORKFLOW.index("\n  seal:"):]
    for text in ((ROOT / "pipeline/kr_integrated_alpha_portfolio_seal.py").read_text(), (ROOT / "scripts/seal_kr_integrated_alpha_portfolio_v1.py").read_text(), seal_job):
        for forbidden in ("/merge", "gh pr merge", "gh pr ready", "ready_for_review", "markPullRequestReadyForReview", "auto-merge", "--force", "push -f",
                          "run_kr_integrated_alpha_portfolio_v1", "--mode execute"):
            assert forbidden not in text, forbidden


# ---------------------------------------------------------------------------------------------------------------------------------------
# The workflow
# ---------------------------------------------------------------------------------------------------------------------------------------
def test_the_workflow_never_executes_or_seals_on_pull_requests_and_holds_minimal_permissions():
    execute = WORKFLOW[WORKFLOW.index("\n  execute:"):WORKFLOW.index("\n  seal:")]
    seal = WORKFLOW[WORKFLOW.index("\n  seal:"):]
    import yaml
    triggers = yaml.safe_load(WORKFLOW)[True]
    assert set(triggers) == {"pull_request", "workflow_dispatch"} and "gh workflow run" not in WORKFLOW
    assert "github.event_name == 'workflow_dispatch' && inputs.mode == 'execute'" in execute and "contents: write" in execute
    assert "pull-requests" not in execute and "listMatchingRefs" in execute and "RESULTS_ARTIFACT_ALREADY_EXISTS" in execute
    assert "PRESERVED_ARTIFACT_IDENTITY_MISMATCH" in execute and "INPUT_ARTIFACT_IDENTITY_MISMATCH" in execute and "PRIOR_SEALED_ARTIFACT_CHANGED" in execute
    assert "kr-integrated-alpha-portfolio-v1-results-${{ github.run_id }}" in execute and "kr-integrated-alpha-portfolio-v1-attempt-${{ github.run_id }}" in execute
    assert "DO NOT RETRY" in execute and "MAIN_ONLY" in execute and "EXECUTION_LOCK_ALREADY_EXISTS" in execute
    assert "needs.execute.result == 'success'" in seal and "github.event_name == 'workflow_dispatch'" in seal and "pull-requests: write" in seal
    assert "kr-integrated-alpha-portfolio-v1-results-" in seal and "MAIN_ONLY" in seal and "open-pr" in seal
    frozen = WORKFLOW[WORKFLOW.index("\n  frozen-machine:"):WORKFLOW.index("\n  execute:")]
    assert "--mode execute" not in frozen and "--mode verify" in frozen and "--mode readiness" in frozen and "pytest -q" in frozen
    for study in E.PRIOR_STUDIES:
        assert "run_" + study.replace("-", "_") not in WORKFLOW and study + "-execution-lock" not in WORKFLOW


def test_the_workflow_inventory_addendum_documents_the_workflow():
    addendum = (ROOT / "docs/workflow-inventory-addendum.md").read_text()
    assert "kr-integrated-alpha-portfolio-v1.yml" in addendum


# ---------------------------------------------------------------------------------------------------------------------------------------
# Prospective receipts (designed here; nothing is written or scheduled)
# ---------------------------------------------------------------------------------------------------------------------------------------
def _receipt(day="2026-10-06", c0=0.7, c1=1.0):
    rows = [{"ticker": f"T{i:02d}.KS", "industry": "X" if i < 6 else "Y", "STOCK_SCORE": i / 12, "VALUE_SCORE": i / 12, "RISK_SCORE": i / 12,
             "INDUSTRY_SCORE": 0.7 if i < 6 else 0.3, "COMBINED_SCORE": 0.5 * i / 12 + 0.5 * (0.7 if i < 6 else 0.3), "tradable": True, "adv60": 6e9,
             "downsideVol126": 0.18 + 0.01 * i} for i in range(12)]
    pair = M.underlying_pair(rows)
    return RCP.build_receipt(
        signal_date=day, input_identities={"prices": "0" * 64, "accounting": "1" * 64, "membership": "2" * 64, "FDR_KS200": "3" * 64},
        industry_membership={f"T{i:02d}.KS": "X" if i < 6 else "Y" for i in range(12)},
        stock_features={f"T{i:02d}.KS": {"bookToMarketProxy": 0.5, "earningsYieldProxy": 0.05, "negativeDownsideVol126": -0.2} for i in range(12)},
        industry_features={"X": {"REL_MOM_126": 0.1, "BREADTH_ABOVE_MA_126": 0.6}, "Y": {"REL_MOM_126": -0.1, "BREADTH_ABOVE_MA_126": 0.4}},
        scores={f"T{i:02d}.KS": {"STOCK_SCORE": i / 12, "INDUSTRY_SCORE": 0.7 if i < 6 else 0.3, "COMBINED_SCORE": 0.5} for i in range(12)},
        eligible={"S": [f"T{i:02d}.KS" for i in range(12)], "I+S": [f"T{i:02d}.KS" for i in range(12)]}, underlying=pair,
        market={"C0": {"states": {"slow": 1, "transition": 0, "fast": 1}, "multiplier": c0, "heldForMissingState": False},
                "C1": {"states": {"slow": 1, "transition": 0, "fast": 1}, "multiplier": c1, "heldForMissingState": False}},
        spec_sha256=SHA, code_identity={"commit": MAIN}, created_at_utc="2026-10-05T07:00:00Z", development_decision="NO_DEVELOPMENT_DECISION_YET")


def test_a_receipt_records_all_six_targets_derived_from_the_two_books_and_its_own_digest():
    r = _receipt()
    assert sorted(r["targets"]) == list(M.ARCH_ORDER) and r["executionDate"] == "2026-10-07" and r["receiptSha256"] == RCP.receipt_digest(r)
    assert r["evidenceClass"] == "PROSPECTIVE_PAPER" and r["evaluationHorizons"] == [21, 63, 126]
    a, b, c, d, e, f = (r["targets"][x] for x in M.ARCH_ORDER)
    assert a["selected"] == b["selected"] == c["selected"] and d["selected"] == e["selected"] == f["selected"]
    for t, w in r["underlying"]["S"]["baseWeights"].items():
        assert a["weights"][t] == w and b["weights"][t] == pytest.approx(w * 0.7) and c["weights"][t] == pytest.approx(w * 1.0)
    for t, w in r["underlying"]["I+S"]["baseWeights"].items():
        assert d["weights"][t] == w and e["weights"][t] == pytest.approx(w * 0.7)
    assert b["cashWeight"] == pytest.approx(1 - 0.7 * sum(r["underlying"]["S"]["baseWeights"].values())) and all(len(t["weights"]) <= 5 for t in r["targets"].values())
    schema = json.loads((ROOT / E.RECEIPT_SCHEMA_PATH).read_text())
    assert set(schema["required"]) == set(RCP.REQUIRED) | {"receiptSha256"} == set(r)
    with pytest.raises(ValueError, match="NOT_A_KR_SESSION"):
        _receipt(day="2026-10-05")                                                # a KR substitute holiday
    with pytest.raises(ValueError, match="OUTSIDE_FROZEN_VOCABULARY"):
        _receipt(c0=0.5)


def test_a_receipt_refuses_a_tampered_target_a_broken_shared_underlying_and_any_outcome_field():
    r = _receipt()
    for mutate, message in ((lambda x: x["targets"]["B"]["weights"].update({"T11.KS": 0.9}), "TARGET"),
                            (lambda x: x["targets"]["C"].update(selected=["T00.KS"]), "TARGET"),
                            (lambda x: x["underlying"]["S"].update(selected=["T00.KS"]), "TARGET"),
                            (lambda x: x.update(forwardReturn=0.1), "OUTCOME_FIELD_IN_RECEIPT"),
                            (lambda x: x["stockFeatures"]["T00.KS"].update(realizedExcess=0.1), "OUTCOME_FIELD_IN_RECEIPT"),
                            (lambda x: x["targets"].pop("F"), "ALL_SIX_TARGETS_REQUIRED")):
        broken = json.loads(json.dumps(r))
        mutate(broken)
        broken["receiptSha256"] = RCP.receipt_digest(broken)
        with pytest.raises(ValueError, match=message):
            RCP.validate_receipt(broken)
    stale = json.loads(json.dumps(r))
    stale["targets"]["D"]["weights"] = {}
    with pytest.raises(ValueError, match="DIGEST_MISMATCH"):
        RCP.validate_receipt(stale)
    empty = dict(signal_date="2026-10-06", input_identities={}, industry_membership={}, stock_features={}, industry_features={}, scores={}, eligible={}, underlying={},
                 market={}, spec_sha256=SHA, code_identity={"c": "d"}, created_at_utc="x", development_decision="x")
    with pytest.raises(ValueError, match="INPUT_IDENTITY_REQUIRED"):
        RCP.build_receipt(**empty)


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
    other = _receipt("2026-10-19")
    other["specSha256"] = "9" * 64
    other["receiptSha256"] = RCP.receipt_digest(other)
    with pytest.raises(ValueError, match="SPEC_CHANGED_WITHIN_A_LEDGER"):
        RCP.append_receipt(ledger, other)
    lines = ledger.read_text().splitlines()
    row = json.loads(lines[0])
    row["market"]["C0"]["multiplier"] = 1.0
    ledger.write_text(json.dumps(row) + "\n" + lines[1] + "\n")
    with pytest.raises(ValueError, match="DIGEST_MISMATCH"):
        RCP.read_ledger(ledger)
    r = _receipt("2026-10-06")
    assert not RCP.matured(r, "2026-11-02", 21) and RCP.matured(r, "2026-12-31", 21)
    with pytest.raises(ValueError, match="UNREGISTERED_HORIZON"):
        RCP.matured(r, "2027-12-31", 252)
    assert not (ROOT / "ledger" / "kr-integrated-alpha-portfolio").exists()      # nothing is written or scheduled by this change
