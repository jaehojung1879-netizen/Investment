"""Frozen identity, label-free readiness, one-shot lifecycle and the analysis assembly. Synthetic repositories, synthetic series and a fake GitHub API only."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil

import numpy as np
import pandas as pd
import pytest
from pipeline import kr_factor_anatomy_execution as AE
from pipeline import kr_industry_anatomy_execution as IE
from pipeline import kr_market_risk_anatomy as M
from pipeline import kr_market_risk_anatomy_analysis as AN
from pipeline import kr_market_risk_anatomy_execution as E
from pipeline import kr_market_risk_source_parse as P
from pipeline import kr_market_risk_sources as S
from pipeline import kr_stock_within_industry_anatomy_execution as SE
from pipeline import kr_top120_regime_review_execution as RE

ROOT = Path(__file__).resolve().parents[1]
SPEC, SHA = E.load_spec(ROOT)
GOOD_ENV = {"GITHUB_ACTIONS": "true", "GITHUB_REF": "refs/heads/main", "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_SHA": "a" * 40,
            "MARKET_INPUT_ARTIFACT": SPEC["input"]["artifactName"], "MARKET_INPUT_RUN_ID": str(SPEC["input"]["producingRunId"]), "GH_TOKEN": "t", "GITHUB_REPOSITORY": "o/r"}


@pytest.fixture(autouse=True)
def synthetic_lifecycle_paths(monkeypatch):
    """Authorization and lifecycle tests exercise the rules, not the repository state."""
    monkeypatch.setattr(E, "RESULT_PATH", "docs/results/synthetic-absent-result.json")
    monkeypatch.setattr(E, "MARKER_PATH", "docs/results/synthetic-absent-marker.json")


def fake_git(head="a" * 40, committed=True):
    def git(args, root):
        if args[0] == "rev-parse":
            return (head + "\n").encode()
        return (Path(root) / args[1][len("HEAD:"):]).read_bytes() if committed else b"different"
    return git


def authorize(env=None, git=None, probe=lambda: False, root=ROOT, spec=SPEC, sha=SHA):
    return E.authorize_execution(spec, sha, root, dict(GOOD_ENV, **(env or {})), git or fake_git(), probe)


class FakeApi:
    def __init__(self, existing=(), refuse_create=None):
        self.refs, self.calls, self.refuse_create = {r: "x" for r in existing}, [], refuse_create

    def __call__(self, method, path, payload=None):
        self.calls.append(method)
        if method == "GET" and path.startswith("/git/matching-refs/"):
            prefix = "refs/" + path[len("/git/matching-refs/"):]
            return 200, [{"ref": r} for r in self.refs if r.startswith(prefix)]
        if method == "POST":
            if payload["ref"] in self.refs:
                return 422, {}
            if self.refuse_create:
                return 500, {}
            self.refs[payload["ref"]] = payload["sha"]
            return 201, {}
        if method == "GET" and path.startswith("/git/ref/"):
            ref = "refs/" + path[len("/git/ref/"):]
            return (200, {"object": {"sha": self.refs[ref]}}) if ref in self.refs else (404, {})
        return 405, {}


# --------------------------------------------------------------------------- #
# Frozen identity
# --------------------------------------------------------------------------- #
def test_frozen_spec_design_and_scientific_label():
    assert SPEC["scientificStatus"] == "EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY" == M.SCIENTIFIC_STATUS
    assert SPEC["boundary"]["passFailSemantics"] == "NONE" and SPEC["boundary"]["outcomeExecutionInThisChange"] is False and SPEC["phase"].startswith("ANATOMY_SOURCE_FOUNDATION")
    design = json.loads((ROOT / E.DESIGN_PATH).read_text())
    assert E.digest(design) == SPEC["designSha256"] == (ROOT / "research_specs/kr-market-risk-anatomy-v1-design.sha256").read_text().strip()
    assert SPEC["preSourceFreezeCommit"] == "8091944a2dea3a7fc91c6135b364222bdc997fd0"
    assert design["architectureRole"]["layer"] == "MARKET"
    for path in ("research_specs/kr-market-risk-anatomy-v1-design.json", "docs/kr-market-risk-anatomy-v1-design.md", "research_specs/kr-market-risk-anatomy-v1-design.sha256"):
        assert path in SPEC["dependencyHashes"]


def test_pins_detect_every_change_to_the_design_and_the_snapshot(tmp_path):
    assert E.verify_pins(SPEC, ROOT)
    root = tmp_path / "repo"
    (root / "research_specs").mkdir(parents=True)
    for rel in ("research_specs/kr-market-risk-anatomy-v1-design.json", "research_specs/kr-market-risk-anatomy-v1-design.sha256"):
        shutil.copy(ROOT / rel, root / rel)
    shutil.copytree(ROOT / E.SNAPSHOT_DIR, root / E.SNAPSHOT_DIR)
    assert E.verify_pins(SPEC, root)
    one = next(iter(SPEC["sourcePins"]["files"]))
    target = root / E.SNAPSHOT_DIR / one
    target.write_bytes(target.read_bytes() + b"x")
    with pytest.raises(ValueError, match="SOURCE_SNAPSHOT_FILE_CHANGED"):
        E.verify_pins(SPEC, root)
    shutil.copy(ROOT / E.SNAPSHOT_DIR / one, target)
    (root / E.SNAPSHOT_DIR / "audit.json").write_text((root / E.SNAPSHOT_DIR / "audit.json").read_text() + " ")
    with pytest.raises(ValueError, match="SOURCE_AUDIT_CHANGED"):
        E.verify_pins(SPEC, root)
    shutil.copy(ROOT / E.SNAPSHOT_DIR / "audit.json", root / E.SNAPSHOT_DIR / "audit.json")
    (root / E.SNAPSHOT_DIR / "EXTRA").write_text("x")
    with pytest.raises(ValueError, match="FILE_SET_CHANGED"):
        E.verify_pins(SPEC, root)
    (root / E.SNAPSHOT_DIR / "EXTRA").unlink()
    design = root / "research_specs/kr-market-risk-anatomy-v1-design.json"
    design.write_text(design.read_text().replace('"MARKET"', '"STOCK"', 1))
    with pytest.raises(ValueError, match="FROZEN_DESIGN_CHANGED"):
        E.verify_pins(SPEC, root)


def test_source_snapshot_audit_is_metadata_only_and_the_registry_is_complete():
    audit = json.loads((ROOT / E.SNAPSHOT_DIR / "audit.json").read_text())
    assert set(audit["sources"]) == set(S.ACQUIRED_IDS) and audit["kind"] == "SOURCE_SNAPSHOT_IDENTITY_AUDIT_NO_OUTCOMES"
    assert any("No return, drawdown" in line for line in audit["statements"])
    for sid, record in audit["sources"].items():
        assert record["vintageClass"] in M.PREDICTOR_ELIGIBLE_CLASSES
        for name, h in record["files"].items():
            assert P.sha256((ROOT / E.SNAPSHOT_DIR / sid / name).read_bytes()) == h == SPEC["sourcePins"]["files"][f"{sid}/{name}"]
        assert not any(k in record for k in ("mean", "median", "min", "max", "std", "lastValue"))  # dates and counts only


def test_recorded_identity_defect_is_kept_and_the_registered_function_is_used():
    audit = json.loads((ROOT / E.SNAPSHOT_DIR / "audit.json").read_text())
    recorded = {sid: r["identityOk"] for sid, r in audit["sources"].items()}
    assert recorded["YAHOO_VIX"] is False and recorded["YAHOO_KRWX"] is False  # the acquisition-time check compared an undeclared currency; the flag is kept as recorded
    views, _ = E.snapshot_views(ROOT)
    assert views["YAHOO_VIX"]["identityOk"] is True and views["YAHOO_KRWX"]["identityOk"] is True and all(v["identityOk"] for v in views.values() if v["status"] == "ACQUIRED")
    assert S.identity_ok(S.SOURCES["YAHOO_KS200"], {"symbol": "^KS200", "currency": "USD"}) is False
    assert S.identity_ok(S.SOURCES["YAHOO_VIX"], {"symbol": "^OTHER"}) is False and S.identity_ok(S.SOURCES["FRED_DGS10"], {"id": "DGS2"}) is False


# --------------------------------------------------------------------------- #
# Label-free readiness on the committed snapshot
# --------------------------------------------------------------------------- #
def test_committed_readiness_is_data_blocked_with_exact_blockers_and_zero_outcome_access():
    r = E.readiness_audit(ROOT)
    assert r["decision"] == "DATA_BLOCKED_BEFORE_MARKET_RISK_ANATOMY" in ("READY_FOR_MARKET_RISK_ANATOMY_EXECUTION", "DATA_BLOCKED_BEFORE_MARKET_RISK_ANATOMY")
    assert r["blockers"] == ["PRIMARY_REFERENCE_NOT_SELECTED"] and r["covers2008"] is False and r["earliestDefensibleCoreHistoryDate"] is None
    assert r["counters"] == E.Counters().__dict__ and r["basedOnAnyReturnResult"] is False and r["historicalExecutionPerformed"] is False
    ev = r["primaryReference"]["evaluated"]
    assert ev["FDR_KS200"]["reasons"] == ["STALE_LAST_DATE"] and ev["YAHOO_KS11"]["reasons"] == ["TOO_MANY_INVALID_ROWS"]
    assert "HISTORY_STARTS_AFTER_2005-12-31" in ev["YAHOO_KS200"]["reasons"] and ev["KRX_OPENAPI_KOSPI200"]["reasons"][0].startswith("DOCUMENTED_BLOCKER")
    d = r["referenceDiagnostics"]
    assert d["FDR_KS200"]["staleDaysAtAcquisition"] == 17 and d["FDR_KS200"]["sessionCoverage"]["GFC_2007_2009"] == 1.0 and d["FDR_KS200"]["firstDate"] == "1990-01-03"
    assert d["YAHOO_KS11"]["droppedRowShare"] == pytest.approx(149 / 7486, abs=1e-6) and d["YAHOO_KS11"]["droppedRowShare"] > d["YAHOO_KS11"]["droppedRowShareLimit"]
    assert d["YAHOO_KS200"]["sessionCoverage"]["GFC_2007_2009"] == 0.0 and d["YAHOO_069500"]["eligibleAsPrimary"] is False
    assert r["roleSources"] == {"VIX": "FRED_VIXCLS", "USDKRW": "FRED_DEXKOUS"} and r["acquiredOn"] == "2026-10-04"


def test_the_blocked_decision_is_not_unblocked_by_the_frozen_rules_or_a_changed_threshold():
    views, audit = E.snapshot_views(ROOT)
    sessions = M.kr_sessions("1990-01-02", audit["acquiredOn"])
    assert S.select_primary_reference(views, sessions, audit["acquiredOn"])["primary"] is None
    # the transition and slow families have their own coverage (VIX and USD/KRW reach 2007-2009 and 2020); HY and IG start in 2023 and keep their own tables
    cov = S.core_gates(views, {"primary": "FDR_KS200", "decision": "TEST_ONLY"}, {"VIX": "FRED_VIXCLS", "USDKRW": "FRED_DEXKOUS"}, sessions, audit["acquiredOn"])
    assert cov["coverage"]["TRANSITION_GFC_2007_2009"]["trans_vix_level"] >= 0.95 and cov["coverage"]["TRANSITION_GFC_2007_2009"]["trans_hy_oas_level"] < 0.05
    assert cov["coverage"]["SLOW_GFC_2007_2009"]["slow_us_10y3m_flatness"] >= 0.95
    assert S.REFERENCE_FRESHNESS_DAYS == 10 and S.REFERENCE_MAX_DROPPED_SHARE == 0.005  # the frozen limits that block FDR_KS200 and YAHOO_KS11


def test_extended_tier_audit_is_structural_and_not_part_of_the_decision():
    t = E.readiness_audit(ROOT)["extendedTier"]
    assert t["requiredForDecision"] is False and t["firstPitSignalDate"] == "2015-01-02" and t["pitSignalDates"] == 610 and t["startsMateriallyLaterThanCore"] is True
    assert t["rawInputArtifact"]["artifactId"] == 11157875265 and t["neverReconstructedFromTodaysConstituents"] is True


def test_readiness_and_verify_never_read_a_value_or_call_an_outcome_function(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("OUTCOME_OR_VALUE_ACCESS_ON_PULL_REQUEST")
    for module, names in ((M, ("forward_targets", "underwater_episodes", "first_trigger_damage", "trigger_profile", "fast_features", "baseline_trigger_states", "feature_statistics")),
                          (AN, ("build_core_panel", "analyze", "feature_tables", "episode_tables", "obs_series")), (P, ("read_normalized", "parse_fred_observations", "parse_yahoo_chart")),
                          (E, ("load_series", "execute", "extended_internals", "claim_execution_lock"))):
        for name in names:
            monkeypatch.setattr(module, name, boom)
    assert E.verify(ROOT)["counters"] == E.Counters().__dict__ and E.verify(ROOT)["stoppedBeforeOutcomes"] is True
    r = E.readiness_audit(ROOT)
    assert r["counters"] == E.Counters().__dict__ and r["decision"] == "DATA_BLOCKED_BEFORE_MARKET_RISK_ANATOMY"
    assert E.snapshot_views(ROOT)[0]["FDR_KS200"]["dates"].is_monotonic_increasing


def test_readiness_flips_when_the_frozen_identity_fails(monkeypatch):
    monkeypatch.setattr(E, "verify_pins", lambda *a, **k: (_ for _ in ()).throw(ValueError("PIN")))
    r = E.readiness_audit(ROOT)
    assert r["decision"] == "DATA_BLOCKED_BEFORE_MARKET_RISK_ANATOMY" and r["blockers"] == ["FROZEN_IDENTITY_NOT_VERIFIED"]


def test_blocked_and_revised_inputs_are_published_with_reasons():
    r = E.readiness_audit(ROOT)
    ex = r["excludedRevisedOrUnbuiltInputs"]
    for sid in ("ECOS_LEADING_INDEX", "FRED_NFCI", "FRED_ANFCI", "FRED_OECD_KR_10Y", "ECOS_BASE_RATE", "ECOS_KTB_3Y"):
        assert ex[sid]["vintageClass"] == "REVISED_HISTORY" and ex[sid]["reason"]
    for sid in ("EXCESS_BOND_PREMIUM", "NEAR_TERM_FORWARD_SPREAD", "KR_TERM_SPREAD"):
        assert ex[sid]["vintageClass"] == "NOT_AVAILABLE"
    assert r["sourceInventory"]["FRED_BAMLH0A0HYM2"]["firstDate"] == "2023-10-03"  # the licence window: a late candidate keeps its own coverage table


# --------------------------------------------------------------------------- #
# Authorization, lock and ordering
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("env,reason", [({"GITHUB_ACTIONS": "false"}, "REQUIRES_ACTIONS"), ({"GITHUB_REF": "refs/heads/x"}, "REQUIRES_MAIN"),
                                        ({"GITHUB_EVENT_NAME": "pull_request"}, "WORKFLOW_DISPATCH"), ({"MARKET_INPUT_ARTIFACT": "wrong"}, "INPUT_ARTIFACT_IDENTITY_MISMATCH"),
                                        ({"MARKET_INPUT_RUN_ID": "1"}, "INPUT_ARTIFACT_IDENTITY_MISMATCH")])
def test_execute_is_main_only_and_workflow_dispatch_only(env, reason):
    with pytest.raises(ValueError, match=reason):
        authorize(env)


def test_authorization_checks_input_hashes_before_any_lock_and_refuses_existing_state(monkeypatch):
    permit = authorize()
    assert E.require_permit(permit) is permit
    calls = []
    original = E.verify_pins
    monkeypatch.setattr(E, "verify_pins", lambda *a, **k: calls.append("pins") or original(*a, **k))
    probe_calls = []
    authorize(probe=lambda: probe_calls.append("lock") or False)
    assert calls == ["pins"] and probe_calls == ["lock"]  # the pins were checked, and only then the lock state
    tampered = copy.deepcopy(SPEC)
    tampered["sourcePins"]["auditSha256"] = "0" * 64
    monkeypatch.setattr(E, "verify_pins", original)
    probe_calls.clear()
    with pytest.raises(ValueError, match="SOURCE_AUDIT_CHANGED"):
        authorize(spec=tampered, probe=lambda: probe_calls.append("lock") or False)
    assert probe_calls == []  # a failed input hash never reaches the lock probe
    with pytest.raises(ValueError, match="CHECKOUT_IS_NOT_THE_DISPATCHED_COMMIT"):
        authorize(git=fake_git(head="b" * 40))
    with pytest.raises(ValueError, match="SPEC_NOT_COMMITTED_AT_HEAD"):
        authorize(git=fake_git(committed=False))
    with pytest.raises(ValueError, match="EXECUTION_LOCK_ALREADY_EXISTS"):
        authorize(probe=lambda: True)
    monkeypatch.setattr(E, "RESULT_PATH", "README.md")
    with pytest.raises(ValueError, match="RESULT_ALREADY_COMMITTED"):
        authorize()
    monkeypatch.setattr(E, "RESULT_PATH", "docs/results/absent.json")
    monkeypatch.setattr(E, "MARKER_PATH", "README.md")
    with pytest.raises(ValueError, match="MARKER_ALREADY_COMMITTED"):
        authorize()


def test_pull_request_environment_is_never_authorized_and_the_runner_refuses():
    assert E.verify(ROOT, {"GITHUB_EVENT_NAME": "pull_request"})["executeAuthorizedInThisEnvironment"] is False
    spec = importlib.util.spec_from_file_location("run_market", ROOT / "scripts/run_kr_market_risk_anatomy_v1.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    with pytest.raises(ValueError, match="FORMAL_EXECUTION_REQUIRES_ACTIONS"):
        runner.run("execute", output="x", env={"GITHUB_EVENT_NAME": "pull_request"})
    with pytest.raises(ValueError, match="UNREGISTERED_EXECUTION_MODE"):
        runner.run("anything")
    assert not (ROOT / "docs/results" / (E.STUDY + "-result.json")).exists() and not (ROOT / "docs/results" / (E.STUDY + "-execution-started.json")).exists()


def test_lock_is_study_level_exclusive_and_refuses_any_existing_prefix_ref():
    api = FakeApi()
    lock = E.claim_execution_lock(SHA, GOOD_ENV, api)
    assert E.require_lock(lock, SHA) is lock and set(api.calls) <= {"GET", "POST"}
    assert E.STUDY_LOCK_REF in api.refs and E.lock_ref(SHA) in api.refs and E.LOCK_PREFIX == "refs/tags/kr-market-risk-anatomy-v1-execution-lock"
    with pytest.raises(ValueError, match="EXECUTION_LOCK_ALREADY_EXISTS"):
        E.claim_execution_lock("f" * 64, GOOD_ENV, api)  # a different spec sha is refused by the study-level ref
    for existing in (E.LOCK_PREFIX, E.LOCK_PREFIX + "-" + "9" * 64, E.LOCK_PREFIX + "-anything"):
        assert E.lock_exists(None, GOOD_ENV, FakeApi(existing=[existing])) is True
        with pytest.raises(ValueError, match="EXECUTION_LOCK_ALREADY_EXISTS"):
            authorize(probe=lambda e=existing: E.lock_exists(SHA, GOOD_ENV, FakeApi(existing=[e])))
    with pytest.raises(ValueError, match="NOT_CREATED"):
        E.claim_execution_lock(SHA, GOOD_ENV, FakeApi(refuse_create=True))
    with pytest.raises(ValueError, match="UNVERIFIABLE"):
        E.lock_exists(None, {}, api)
    with pytest.raises(ValueError, match="REQUIRES_ACTIONS_MAIN"):
        E.claim_execution_lock(SHA, dict(GOOD_ENV, GITHUB_REF="refs/heads/x"), FakeApi())
    with pytest.raises(ValueError, match="LOCK_REQUIRED"):
        E.require_lock(object(), SHA)


def test_values_need_both_permit_and_lock_and_leave_counters_zero_on_refusal():
    counters = E.Counters()
    with pytest.raises(ValueError, match="WITHOUT_PERMIT"):
        E.load_series(ROOT, counters, object(), None, SHA)
    with pytest.raises(ValueError, match="DURABLE_EXECUTION_LOCK_REQUIRED"):
        E.load_series(ROOT, counters, authorize(), None, SHA)
    assert counters.zero()


# --------------------------------------------------------------------------- #
# A synthetic READY repository: ordering of gates -> lock -> marker -> values -> outcomes
# --------------------------------------------------------------------------- #
def planted_close(sessions):
    n = len(sessions)
    rng = np.random.default_rng(7)
    path = 100 * np.cumprod(1 + rng.normal(0.0004, 0.008, n))
    peak = int(n * 0.35)
    path[peak:peak + 120] *= np.linspace(1.0, 0.62, 120)
    path[peak + 120:] *= 0.62
    path[peak + 120:] *= np.cumprod(np.full(n - peak - 120, 1.0006))
    return pd.Series(path, index=sessions)


def synthetic_root(tmp_path, with_hy=True, reference_start="2003-01-02", acquired_on="2021-03-01"):
    root = tmp_path / "repo"
    (root / "research_specs").mkdir(parents=True)
    for rel in ("research_specs/kr-market-risk-anatomy-v1-design.json", "research_specs/kr-market-risk-anatomy-v1-design.sha256"):
        shutil.copy(ROOT / rel, root / rel)
    snap = root / E.SNAPSHOT_DIR
    snap.mkdir(parents=True)
    sessions = M.kr_sessions(reference_start, "2021-02-26")
    bdays = pd.bdate_range("2002-06-03", "2021-02-26")
    rng = np.random.default_rng(3)
    audit = {"studyId": E.STUDY, "kind": "SOURCE_SNAPSHOT_IDENTITY_AUDIT_NO_OUTCOMES", "acquiredOn": acquired_on, "sources": {}, "statements": ["synthetic"]}
    files = {}

    def add(sid, rows, identity):
        directory = snap / sid
        directory.mkdir()
        data = P.normalized_csv(rows)
        (directory / "normalized.csv").write_bytes(data)
        files[sid + "/normalized.csv"] = P.sha256(data)
        audit["sources"][sid] = {"status": "ACQUIRED", "validRows": len(rows), "droppedRows": 0, "identity": identity, "identityOk": True,
                                 "firstDate": rows[0][0], "lastDate": rows[-1][0], "vintageClass": S.SOURCES[sid]["vintageClass"], "files": {"normalized.csv": files[sid + "/normalized.csv"]}}
    ref = planted_close(sessions)
    add("YAHOO_KS200", [(d.strftime("%Y-%m-%d"), float(v)) for d, v in ref.items()], {"symbol": "^KS200", "currency": "KRW"})
    levels = {"FRED_DGS10": (3.0, 0.03), "FRED_DGS3MO": (2.5, 0.05), "FRED_DGS2": (2.8, 0.04), "FRED_DFF": (2.4, 0.03), "FRED_VIXCLS": (20.0, 0.5), "FRED_DEXKOUS": (1100.0, 3.0)}
    for sid, (base, step) in levels.items():
        values = base + np.cumsum(rng.normal(0, step, len(bdays)))
        values = np.abs(values) + (1.0 if sid in ("FRED_VIXCLS", "FRED_DEXKOUS") else 0.0)
        add(sid, [(d.strftime("%Y-%m-%d"), float(v)) for d, v in zip(bdays, values)], {"id": S.SOURCES[sid]["symbol"]})
    if with_hy:
        late = bdays[bdays >= "2018-01-01"]
        add("FRED_BAMLH0A0HYM2", [(d.strftime("%Y-%m-%d"), float(4 + abs(rng.normal(0, 1)))) for d in late], {"id": "BAMLH0A0HYM2"})
    (snap / "audit.json").write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n")
    design = json.loads((root / E.DESIGN_PATH).read_text())
    spec = {"studyId": E.STUDY, "scientificStatus": E.SCIENTIFIC_STATUS, "designSha256": E.digest(design),
            "sourcePins": {"snapshotDir": E.SNAPSHOT_DIR, "auditSha256": E.file_hash(snap / "audit.json"), "files": {k: E.file_hash(snap / k) for k in sorted(files)}}}
    return root, spec, "b" * 64


def test_a_ready_synthetic_snapshot_yields_ready_and_the_lock_precedes_every_value_read(tmp_path, monkeypatch):
    root, spec, sha = synthetic_root(tmp_path)
    views, audit = E.snapshot_views(root)
    decided = E.decide(root)
    assert decided["gates"]["decision"] == E.DECISION_READY and decided["reference"]["primary"] == "YAHOO_KS200" and decided["reference"]["composite"] is False
    order = []
    original = {name: getattr(E, name) for name in ("decide", "claim_execution_lock", "write_execution_marker", "load_series")}
    for name, fn in original.items():
        monkeypatch.setattr(E, name, (lambda n, f: lambda *a, **k: order.append(n) or f(*a, **k))(name, fn))
    monkeypatch.setattr(AN, "build_core_panel", (lambda f: lambda *a, **k: order.append("build_core_panel") or f(*a, **k))(AN.build_core_panel))
    monkeypatch.setattr(AN, "analyze", (lambda f: lambda *a, **k: order.append("analyze") or f(*a, **k))(AN.analyze))
    out = tmp_path / "out"
    permit = E.ExecutionPermit(sha, E._PERMIT_TOKEN)
    manifest = E.execute(out, spec, sha, permit, root, GOOD_ENV, FakeApi())
    assert order == ["decide", "claim_execution_lock", "write_execution_marker", "load_series", "build_core_panel", "analyze"]
    marker = json.loads((out / "execution-started.json").read_text())
    assert marker["valuesReadBeforeThisMarker"] == 0 and marker["lockRef"] == E.lock_ref(sha) and manifest["counters"]["valueReads"] >= 7
    result = json.loads((out / "market-risk-anatomy.json").read_text())
    assert result["primaryReference"]["primary"] == "YAHOO_KS200" and result["extendedStatus"] == "NOT_RUN_NO_INPUT"
    assert result["episodes"]["counts"]["depth_ge_15pct"] >= 1 and "statements" in result


def test_a_failed_readiness_gate_writes_gates_failed_and_creates_no_lock(tmp_path):
    root, spec, sha = synthetic_root(tmp_path, reference_start="2012-01-02")  # a reference that starts after 2005 can never be selected
    api = FakeApi()
    with pytest.raises(ValueError, match="READINESS_GATE_FAILED"):
        E.execute(tmp_path / "out", spec, sha, E.ExecutionPermit(sha, E._PERMIT_TOKEN), root, GOOD_ENV, api)
    assert api.refs == {} and api.calls == []  # not even a GET: the gates precede the lock entirely
    failed = json.loads((tmp_path / "out" / "gates-failed.json").read_text())
    assert failed["blockers"] == ["PRIMARY_REFERENCE_NOT_SELECTED"] and failed["counters"] == E.Counters().__dict__
    assert not (tmp_path / "out" / "execution-started.json").exists()


def test_a_synthetic_pit_change_after_the_pins_is_refused_before_the_lock(tmp_path):
    root, spec, sha = synthetic_root(tmp_path)
    target = root / E.SNAPSHOT_DIR / "FRED_DFF" / "normalized.csv"
    target.write_bytes(target.read_bytes() + b"2021-02-27,1.0\n")
    api = FakeApi()
    with pytest.raises(ValueError, match="SOURCE_SNAPSHOT_FILE_CHANGED"):
        E.execute(tmp_path / "out", spec, sha, E.ExecutionPermit(sha, E._PERMIT_TOKEN), root, GOOD_ENV, api)
    assert api.calls == []


# --------------------------------------------------------------------------- #
# The analysis assembly on a planted drawdown
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def planted(tmp_path_factory):
    root, spec, sha = synthetic_root(tmp_path_factory.mktemp("planted"))
    views, audit = E.snapshot_views(root)
    counters = E.Counters()
    lock = E.ExecutionLock(sha, "a" * 40, "ref", E._LOCK_TOKEN)
    series = E.load_series(root, counters, E.ExecutionPermit(sha, E._PERMIT_TOKEN), lock, sha)
    decided = E.decide(root)
    panel = AN.build_core_panel(series["YAHOO_KS200"], {k: v for k, v in series.items() if k != "YAHOO_KS200"}, decided["roles"], S.lag_days)
    return panel, AN.analyze(panel), decided


def test_the_panel_keeps_each_feature_on_its_own_coverage_and_never_fills_the_reference(planted):
    panel, result, decided = planted
    sample = result["sample"]
    assert sample["reference"]["missingSessions"] == 0 and sample["reference"]["datesOffCalendar"] == 0
    assert sample["features"]["trans_hy_oas_level"]["start"] >= "2018-01-01"  # a late candidate stays late
    assert sample["features"]["trans_vix_level"]["start"] < "2003-06-01" and sample["features"]["fast_realized_vol_63"]["start"] < "2004-01-01"
    assert sample["features"]["slow_us_10y3m_flatness"]["cadence"] == "M" and sample["features"]["trans_vix_level"]["cadence"] == "W"
    assert all(v["tier"] == "CORE_LONG_HISTORY" for v in sample["features"].values())


def test_every_feature_is_tabulated_at_its_horizons_on_its_cadence(planted):
    panel, result, decided = planted
    feats = result["features"]
    assert set(feats["slow_us_10y3m_flatness"]) == {"H63", "H126", "H252"} and set(feats["fast_realized_vol_63"]) == {"H21", "H63", "H126"}
    assert set(feats["trans_vix_level"]) == {"H63", "H126"}
    cell = feats["fast_realized_vol_63"]["H63"]
    assert cell["validDates"] > 100 and cell["spearmanVersusLossSeverity"]["hacSe"] > 0 and set(cell["events"]) == {"loss_le_10", "loss_le_15", "loss_le_20"}
    assert cell["events"]["loss_le_20"]["rates"]["events"] >= 1  # the planted ~38% decline produces -20% events
    M.assert_no_forbidden_keys(result)


def test_planted_episode_is_found_algorithmically_with_landmarks_and_latest_known_states(planted):
    panel, result, decided = planted
    major = result["episodes"]["episodes"]
    assert result["episodes"]["counts"]["depth_ge_15pct"] == len(major) >= 1
    ep = max(major, key=lambda e: e["depth"] * -1)
    assert ep["depth"] < -0.30 and ep["peak"] < ep["trough"] and "landmarks" in ep
    lm = ep["landmarks"]
    assert lm["peak"]["date"] == ep["peak"] and lm["trough"]["date"] == ep["trough"] and lm["peak-252"]["date"] < lm["peak-126"]["date"] < lm["peak-63"]["date"] < lm["peak-21"]["date"] < lm["peak"]["date"]
    assert lm["first_drawdown_5"]["date"] <= lm["first_drawdown_10"]["date"] <= lm["first_drawdown_15"]["date"] <= ep["trough"]
    state = lm["peak"]
    assert "fast_trend_distance_sma200" in state["features"] and "known_spread_10y3m" in state["knownInputs"]
    assert set(ep["slowWarnings"]) == {"W1_INVERSION_10Y3M", "W2_INVERSION_10Y2Y"}
    assert ep["slowWarnings"]["W1_INVERSION_10Y3M"]["status"] in ("ACTIVE_AT_PEAK", "ON_THEN_OFF", "NEVER_ON_BEFORE_PEAK")


def test_every_frozen_trigger_gets_damage_false_alarm_and_recovery_tables(planted):
    panel, result, decided = planted
    by = result["episodes"]["byTrigger"]
    assert set(by) == set(M.BASELINE_TRIGGERS)
    for name, block in by.items():
        assert set(block["damage"]) == {"threshold_10", "threshold_15", "threshold_20"}
        d = block["damage"]["threshold_15"]
        assert d["episodes"] == result["episodes"]["counts"]["depth_ge_15pct"] and d["triggered"] + d["missed"] + d["stateUnavailable"] == d["episodes"]
        assert block["profile"]["activations"] >= 0 and set(block["profile"]["followed"]) == {f"H{h}|loss_le_{c}" for h in (63, 126) for c in (10, 15, 20)}
        assert len(block["profile"]["normalisation"]) == d["episodes"]
    triggered = [r for r in by["B1_TREND_ADVERSE"]["perEpisode"] if r["status"] == "TRIGGERED"]
    assert triggered and all(0.0 <= r["damageFraction"] <= 1.0 and r["triggerDelaySessions"] >= 0 for r in triggered)


def test_extended_internals_are_tabulated_on_their_own_period_without_touching_the_core(planted):
    panel, core, decided = planted
    sessions = panel["sessions"]
    frame = pd.DataFrame(np.nan, index=sessions, columns=[n for n in M.FEATURES if n.startswith("int_")])
    weekly = M.period_end_dates(sessions, "W")
    weekly = weekly[weekly >= "2015-01-02"]
    frame.loc[weekly, "int_breadth_above_sma200"] = np.linspace(-0.7, -0.3, len(weekly))
    result = AN.analyze(panel, frame)
    assert result["features"] == core["features"]  # the core tables are unchanged by the extended tier
    ext = result["extendedInternals"]
    assert ext["tier"] == "EXTENDED_KR_INTERNALS" and ext["sample"]["int_breadth_above_sma200"]["start"] >= "2015-01-02" and ext["sample"]["int_dispersion_63"]["start"] is None
    assert ext["features"]["int_breadth_above_sma200"]["H21"]["validDates"] > 100


def test_extended_builder_uses_pit_members_and_missing_inputs_stay_missing(tmp_path, monkeypatch):
    sessions = M.kr_sessions("2014-01-02", "2016-12-30")
    rng = np.random.default_rng(1)
    names = [f"T{i}.KS" for i in range(6)]
    prices = {t: pd.DataFrame({"Close": 100 * np.cumprod(1 + rng.normal(0.0004, 0.01, len(sessions)))}, index=sessions) for t in names[:-1]}
    schedule_dates = [str(d.date()) for d in M.period_end_dates(sessions, "W") if d >= pd.Timestamp("2015-06-01")][:30]

    class Members:
        def on(self, date):
            return {"members": names}

    class Market:
        def at(self, ticker, date):
            return {"marketCap": 1e9 * (names.index(ticker) + 1)}
    monkeypatch.setattr(E.X, "load_spec", lambda root: ({}, "x"))
    monkeypatch.setattr(E.X, "load_sources", lambda input_root, spec: (None, Members(), Market(), prices))
    import pipeline.kr_industry_membership as KM
    monkeypatch.setattr(KM, "top120_schedule", lambda inputs: ({d: names for d in schedule_dates}, {}))
    panel = {"sessions": sessions}
    frame = E.extended_internals(tmp_path, panel, SPEC, ROOT)
    assert frame["int_breadth_above_sma200"].notna().sum() == 0  # one member (T5) has no prices at all: every statistic that needs ALL members is missing, never renormalised
    prices[names[-1]] = pd.DataFrame({"Close": 100 * np.cumprod(1 + rng.normal(0.0004, 0.01, len(sessions)))}, index=sessions)
    full = E.extended_internals(tmp_path, panel, SPEC, ROOT)
    assert full["int_breadth_above_sma200"].notna().sum() == len(schedule_dates) and full["int_concentration_top5_share"].dropna().iloc[0] == pytest.approx(20 / 21)
    assert full["int_breadth_deterioration_63"].notna().sum() > 0 and full.index.equals(sessions)


# --------------------------------------------------------------------------- #
# Isolation from sealed studies and the workflow
# --------------------------------------------------------------------------- #
def test_sealed_studies_cannot_be_rerun_and_this_study_never_calls_them():
    env = dict(GOOD_ENV, ANATOMY_INPUT_ARTIFACT=SPEC["input"]["artifactName"], ANATOMY_INPUT_RUN_ID=str(SPEC["input"]["producingRunId"]),
               REGIME_INPUT_ARTIFACT=SPEC["input"]["artifactName"], REGIME_INPUT_RUN_ID=str(SPEC["input"]["producingRunId"]))
    for module, expect in ((IE, "RESULT_ALREADY_COMMITTED"), (SE, "RESULT_ALREADY_COMMITTED"), (AE, "RESULT_ALREADY_COMMITTED")):
        spec, sha = module.load_spec(ROOT)
        with pytest.raises(ValueError, match=expect):
            if module is AE:
                module.authorize_execution(spec, sha, ROOT, env, fake_git())
            else:
                module.authorize_execution(spec, sha, ROOT, env, fake_git(), lambda: False)
    spec_r, sha_r = RE.load_spec(ROOT)
    with pytest.raises(ValueError, match="EXECUTION_LOCK_ALREADY_EXISTS"):
        RE.authorize_execution(spec_r, sha_r, ROOT, env, fake_git(), lambda: True)
    for sealed_result in ("kr-factor-anatomy-v1", "kr-industry-opportunity-anatomy-v1", "kr-stock-within-industry-anatomy-v1"):
        assert (ROOT / "docs/results" / (sealed_result + "-result.json")).exists()
    for module in ("pipeline/kr_market_risk_anatomy.py", "pipeline/kr_market_risk_sources.py", "pipeline/kr_market_risk_anatomy_analysis.py", "pipeline/kr_market_risk_anatomy_execution.py",
                   "scripts/run_kr_market_risk_anatomy_v1.py"):
        text = (ROOT / module).read_text()
        for forbidden in ("run_kr_factor_anatomy", "run_kr_top120_regime_review", "run_kr_model_overlay", "run_kr_industry_anatomy", "run_kr_stock_within_industry", "IE.execute(", "SE.execute(",
                          "AE.execute(", "RE.execute(", "X.execute(", "collect_dart", "KRX_API"):
            assert forbidden not in text


def test_prior_sealed_study_files_are_unchanged():
    assert (ROOT / "research_specs/kr-model-overlay-portfolio-v1.sha256").read_text().strip() == "563b64ee6f4709a263719669f795ad55e7828e340f082358af1599453253b6fd"
    assert (ROOT / "research_specs/kr-industry-opportunity-anatomy-v1.sha256").read_text().strip() == "98278ce5724b27dd19d253eab6cb1e7854ea432a62098441cdad46d067609f55"
    assert (ROOT / "research_specs/kr-stock-within-industry-anatomy-v1.sha256").read_text().strip() == "cfcec648194e25a8914056266443e241528a68352054a10d75cb6889225e5073"


def test_workflow_never_executes_on_pull_requests_and_has_one_write_permission():
    workflow = (ROOT / ".github/workflows/kr-market-risk-anatomy-v1.yml").read_text()
    for other in ("run_kr_factor_anatomy", "run_kr_top120_regime_review", "run_kr_industry_anatomy", "run_kr_stock_within_industry", "kr-model-overlay-portfolio-v1 execute",
                  "collect_dart", "KRX_API", "FRED_API_KEY", "schedule:", "cron"):
        assert other not in workflow
    execute = workflow[workflow.index("  execute:"):]
    assert "github.event_name == 'workflow_dispatch' && inputs.mode == 'execute'" in execute and "refs/heads/main" in execute
    assert "contents: write" in execute and workflow.count("contents: write") == 1
    assert "--mode execute" in execute and "--mode execute" not in workflow.split("  execute:")[0]
    assert "listMatchingRefs" in execute and "sourcePins" in execute and "designSha256" in execute and "pull_request" in workflow
