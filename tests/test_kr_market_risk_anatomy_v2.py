"""kr-market-risk-anatomy-v2: corrected SOURCE ADMISSIBILITY rules, frozen identity, label-free readiness and the one-shot lifecycle.
Synthetic dates, synthetic repositories and a fake GitHub API only. No test computes a historical market outcome."""
import inspect
import json
from pathlib import Path
import shutil

import pandas as pd
import pytest
from pipeline import kr_market_risk_anatomy as M
from pipeline import kr_market_risk_anatomy_analysis as AN
from pipeline import kr_market_risk_anatomy_execution as V1
from pipeline import kr_market_risk_anatomy_v2_execution as E
from pipeline import kr_market_risk_source_parse as P
from pipeline import kr_market_risk_sources as S
from pipeline import kr_market_risk_sources_v2 as R

ROOT = Path(__file__).resolve().parents[1]
SPEC, SHA = E.load_spec(ROOT)
GOOD_ENV = {"GITHUB_ACTIONS": "true", "GITHUB_REF": "refs/heads/main", "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_SHA": "a" * 40,
            "MARKET_INPUT_ARTIFACT": SPEC["input"]["artifactName"], "MARKET_INPUT_RUN_ID": str(SPEC["input"]["producingRunId"]), "GH_TOKEN": "t", "GITHUB_REPOSITORY": "o/r"}
SESSIONS = M.kr_sessions("2004-01-02", "2021-06-30")
ACQUIRED = "2021-06-30"


def view(dates, identity=True):
    return {"status": "ACQUIRED", "dates": pd.DatetimeIndex(dates), "rows": len(dates), "dropped": 0, "identityOk": identity}


def weekend_and_holiday_rows(first="2004-01-01", last="2021-06-30"):
    sessions = set(SESSIONS)
    return [d.strftime("%Y-%m-%d") for d in pd.date_range(first, last) if d not in sessions]


def fdr_like(drop=(), end="2021-06-30"):
    """A vendor FDR-shaped retention: every session valid except `drop`; raw rows include every non-session calendar date (placeholders)."""
    keep = [d for d in SESSIONS if d <= pd.Timestamp(end) and d not in set(pd.DatetimeIndex(drop))]
    raw = [d.strftime("%Y-%m-%d") for d in keep] + weekend_and_holiday_rows(last=end)
    return keep, raw


def fake_git(head="a" * 40, committed=True):
    def git(args, root):
        if args[0] == "rev-parse":
            return (head + "\n").encode()
        return (Path(root) / args[1][len("HEAD:"):]).read_bytes() if committed else b"different"
    return git


class FakeApi:
    def __init__(self, existing=()):
        self.refs, self.calls = {r: "x" for r in existing}, []

    def __call__(self, method, path, payload=None):
        self.calls.append(method)
        if method == "GET" and path.startswith("/git/matching-refs/"):
            prefix = "refs/" + path[len("/git/matching-refs/"):]
            return 200, [{"ref": r} for r in self.refs if r.startswith(prefix)]
        if method == "POST":
            if payload["ref"] in self.refs:
                return 422, {}
            self.refs[payload["ref"]] = payload["sha"]
            return 201, {}
        if method == "GET" and path.startswith("/git/ref/"):
            ref = "refs/" + path[len("/git/ref/"):]
            return (200, {"object": {"sha": self.refs[ref]}}) if ref in self.refs else (404, {})
        return 405, {}


@pytest.fixture(autouse=True)
def synthetic_lifecycle_paths(monkeypatch):
    monkeypatch.setattr(E, "RESULT_PATH", "docs/results/synthetic-absent-result.json")
    monkeypatch.setattr(E, "MARKER_PATH", "docs/results/synthetic-absent-marker.json")


# --------------------------------------------------------------------------- #
# Historical admissibility is independent of the wall clock; live freshness is separate
# --------------------------------------------------------------------------- #
def test_historical_admissibility_ignores_wall_clock_freshness_and_live_freshness_is_a_separate_record():
    keep, raw = fdr_like(end="2021-06-10")                   # ends 20 days before the acquisition day: v1 called this STALE_LAST_DATE
    ok, reasons, metrics = R.historical_eligibility("FDR_KS200", view(keep), raw, SESSIONS, ACQUIRED)
    assert ok and reasons == [] and "STALE_LAST_DATE" not in json.dumps(reasons)
    live = metrics["liveOperationalFreshness"]
    assert live["staleDays"] == 20 and live["meetsLiveFreshness"] is False and live["liveReady"] is False
    assert live["role"] == "FUTURE_LIVE_DEPLOYMENT_QUESTION_NOT_A_HISTORICAL_GATE"
    v1_ok, v1_reasons = S.reference_eligibility("FDR_KS200", {"status": "ACQUIRED", "dates": keep, "dropped": 0, "rows": len(keep), "identityOk": True}, SESSIONS, ACQUIRED)
    assert not v1_ok and v1_reasons == ["STALE_LAST_DATE"]      # the one v1 reason that v2 removes from the historical gate
    sessions_later = M.kr_sessions("2004-01-02", "2022-08-31")
    later = R.historical_eligibility("FDR_KS200", view(keep), raw, sessions_later, "2022-08-31")
    assert later[0] and later[2]["analysisEnd"] == metrics["analysisEnd"] and later[2]["liveOperationalFreshness"]["staleDays"] > 400
    assert "REFERENCE_FRESHNESS_DAYS" not in inspect.getsource(R.historical_eligibility) and "STALE" not in inspect.getsource(R.historical_eligibility)


def test_a_source_that_simply_stopped_early_cannot_pass_through_the_missing_freshness_gate():
    keep, raw = fdr_like(end="2019-12-31")                   # ends before the 2019H2-2020 window: never admissible, whatever the wall clock says
    ok, reasons, _ = R.historical_eligibility("FDR_KS200", view(keep), raw, SESSIONS, ACQUIRED)
    assert not ok and any("COVID_2019H2_2020" in r for r in reasons)


# --------------------------------------------------------------------------- #
# Session-based quality
# --------------------------------------------------------------------------- #
def test_denominator_is_expected_xkrx_sessions_and_non_session_rows_never_count():
    keep, raw = fdr_like()
    q = R.classify_rows(raw, keep, SESSIONS, R.QUALITY_WINDOW_START, "2021-06-30")
    window = SESSIONS[(SESSIONS >= "2006-01-01") & (SESSIONS <= "2021-06-30")]
    assert q["expectedSessions"] == len(window) == q["validSessions"] and q["badSessions"] == 0 and q["badSessionShare"] == 0.0
    assert q["nonSessionRows"] > 1000                          # weekend / holiday / placeholder rows are reported, not charged
    raw_share_v1 = (len(raw) - len(keep)) / len(raw)           # the v1-style raw-row invalid share would have charged them
    assert raw_share_v1 > R.MAX_BAD_SESSION_SHARE and R.historical_eligibility("FDR_KS200", view(keep), raw, SESSIONS, ACQUIRED)[0]


def test_weekend_and_holiday_null_rows_do_not_fail_and_a_genuine_session_hole_does():
    keep, raw = fdr_like()
    holiday = next(d for d in pd.date_range("2012-01-01", "2012-12-31") if d not in set(SESSIONS) and d.weekday() < 5)
    assert str(holiday.date()) in raw
    assert R.historical_eligibility("FDR_KS200", view(keep), raw, SESSIONS, ACQUIRED)[0]
    scattered = [SESSIONS[i] for i in range(1500, 4000, 100)]   # 25 isolated expected sessions missing
    keep2, raw2 = fdr_like(drop=scattered)
    ok, reasons, m = R.historical_eligibility("FDR_KS200", view(keep2), raw2, SESSIONS, ACQUIRED)
    assert not ok and "TOO_MANY_BAD_EXPECTED_SESSIONS" in reasons and m["quality"]["badSessions"] == 25 and m["quality"]["missingSessions"] == 25
    run = list(SESSIONS[2000:2006])                             # 6 consecutive sessions, share well under the limit
    ok, reasons, _ = R.historical_eligibility("FDR_KS200", view(fdr_like(drop=run)[0]), fdr_like(drop=run)[1], SESSIONS, ACQUIRED)
    assert not ok and reasons == ["MISSING_RUN_TOO_LONG"]


def test_an_invalid_row_on_an_expected_session_is_counted_as_invalid_not_as_missing():
    keep, raw = fdr_like()
    bad = SESSIONS[3000]
    keep = [d for d in keep if d != bad]                        # the vendor row exists (still in raw) but was not valid
    q = R.classify_rows(raw, keep, SESSIONS, R.QUALITY_WINDOW_START, "2021-06-30")
    assert q["invalidExpectedSessions"] == 1 and q["missingSessions"] == 0 and q["badSessions"] == 1


def test_duplicate_vendor_rows_are_reported_separately_and_a_duplicate_in_the_used_series_fails_closed():
    keep, raw = fdr_like()
    raw2 = raw + [raw[10], raw[500], raw[900]]                  # surplus raw duplicates
    q = R.classify_rows(raw2, keep, SESSIONS, "2004-01-01", "2021-06-30")
    assert q["duplicateRawRows"] == 3 and q["badSessions"] == 0
    assert R.historical_eligibility("FDR_KS200", view(keep), raw2, SESSIONS, ACQUIRED)[0]
    dup = keep + [keep[3000]]
    ok, reasons, _ = R.historical_eligibility("FDR_KS200", view(sorted(dup)), raw2, SESSIONS, ACQUIRED)
    assert not ok and "DUPLICATE_DATES_IN_USED_SERIES" in reasons


# --------------------------------------------------------------------------- #
# Priority, family fallback, no splice, deterministic analysis end
# --------------------------------------------------------------------------- #
def test_kospi200_is_preferred_and_the_composite_is_only_a_distinct_fallback_with_no_splice():
    k200, raw200 = fdr_like()
    comp, rawc = fdr_like()
    both = R.select_primary_reference({"FDR_KS200": view(k200), "YAHOO_KS11": view(comp)}, {"FDR_KS200": raw200, "YAHOO_KS11": rawc}, SESSIONS, ACQUIRED)
    assert both["primary"] == "FDR_KS200" and both["composite"] is False and both["spliced"] is False and "YAHOO_KS11" not in both["evaluated"]
    scattered = [SESSIONS[i] for i in range(1500, 4000, 100)]
    hole, rawh = fdr_like(drop=scattered)
    fallback = R.select_primary_reference({"FDR_KS200": view(hole), "YAHOO_KS11": view(comp)}, {"FDR_KS200": rawh, "YAHOO_KS11": rawc}, SESSIONS, ACQUIRED)
    assert fallback["primary"] == "YAHOO_KS11" and fallback["composite"] is True and fallback["spliced"] is False
    none = R.select_primary_reference({"FDR_KS200": view(hole)}, {"FDR_KS200": rawh}, SESSIONS, ACQUIRED)
    assert none["decision"] == "NO_ELIGIBLE_PRIMARY_REFERENCE" and none["primary"] is None
    text = inspect.getsource(R)
    for splice in ("concat(", "combine_first", ".fillna(", "ffill", "interpolate"):
        assert splice not in text
    assert R.PRIMARY_FAMILY_ORDER == ("KOSPI200", "KOSPI_COMPOSITE") and R.REFERENCE_PRIORITY.index("FDR_KS200") < R.REFERENCE_PRIORITY.index("YAHOO_KS11")


def test_the_official_krx_route_with_a_documented_blocker_is_never_selected():
    ok, reasons, _ = R.historical_eligibility("KRX_OPENAPI_KOSPI200", None, None, SESSIONS, ACQUIRED)
    assert not ok and reasons[0].startswith("DOCUMENTED_BLOCKER")


def test_analysis_end_is_deterministic_never_extended_and_ignores_non_sessions_and_the_acquisition_day():
    keep, _ = fdr_like(end="2021-06-10")
    first = R.analysis_end(keep, SESSIONS, ACQUIRED)
    assert first == R.analysis_end(list(reversed(keep)), SESSIONS, ACQUIRED) == pd.Timestamp("2021-06-10")
    extra = keep + [pd.Timestamp("2021-06-12"), pd.Timestamp("2021-06-30")]            # a Saturday and the acquisition day itself
    assert R.analysis_end(extra, SESSIONS, ACQUIRED) == pd.Timestamp("2021-06-10") and R.analysis_end([], SESSIONS, ACQUIRED) is None
    assert R.analysis_end(keep, M.kr_sessions("2004-01-02", "2022-08-31"), "2022-08-31") == first       # a later wall clock never moves it


def test_identity_mismatch_is_refused():
    keep, raw = fdr_like()
    ok, reasons, _ = R.historical_eligibility("FDR_KS200", view(keep, identity=False), raw, SESSIONS, ACQUIRED)
    assert not ok and "IDENTITY_CHECK_FAILED" in reasons


# --------------------------------------------------------------------------- #
# Frozen identity, v1 untouched, no new acquisition
# --------------------------------------------------------------------------- #
def test_frozen_spec_label_rules_and_scope():
    assert SPEC["scientificStatus"] == "EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY" == M.SCIENTIFIC_STATUS
    assert SPEC["studyId"] == "kr-market-risk-anatomy-v2" and SPEC["predecessor"]["studyId"] == "kr-market-risk-anatomy-v1"
    assert SPEC["newExternalAcquisition"] is False and SPEC["boundary"]["outcomeExecutionInThisChange"] is False and SPEC["boundary"]["passFailSemantics"] == "NONE"
    assert SPEC["sourceRules"]["liveFreshnessDaysInformationalOnly"] == 10 and SPEC["sourceRules"]["maxBadSessionShare"] == 0.005
    assert json.loads(json.dumps(SPEC["sourceRules"])) == json.loads(json.dumps(E.source_rules()))
    v1 = json.loads((ROOT / "research_specs/kr-market-risk-anatomy-v1.json").read_text())
    assert SPEC["designSha256"] == v1["designSha256"] and SPEC["sourcePins"] == v1["sourcePins"] and SPEC["input"] == v1["input"]
    for rel in ("pipeline/kr_market_risk_anatomy.py", "pipeline/kr_market_risk_sources.py", "pipeline/kr_market_risk_anatomy_execution.py"):
        assert rel in SPEC["dependencyHashes"]               # v1 code is byte-pinned by the v2 closure


def test_v1_remains_blocked_unchanged_and_its_sealed_bytes_are_pinned():
    assert V1.readiness_audit(ROOT)["decision"] == "DATA_BLOCKED_BEFORE_MARKET_RISK_ANATOMY"
    committed = json.loads((ROOT / "docs/results/kr-market-risk-anatomy-v1-readiness.json").read_text())
    assert committed["decision"] == "DATA_BLOCKED_BEFORE_MARKET_RISK_ANATOMY" and committed["blockers"] == ["PRIMARY_REFERENCE_NOT_SELECTED"]
    assert committed["primaryReference"]["evaluated"]["FDR_KS200"]["reasons"] == ["STALE_LAST_DATE"]
    assert S.REFERENCE_FRESHNESS_DAYS == 10 and S.REFERENCE_MAX_DROPPED_SHARE == 0.005     # v1's own rules are untouched
    for rel, wanted in SPEC["predecessor"]["sealedArtifacts"].items():
        assert E.file_hash(ROOT / rel) == wanted
    assert not (ROOT / "docs/results/kr-market-risk-anatomy-v1-result.json").exists()


def test_prior_sealed_study_files_are_unchanged():
    assert (ROOT / "research_specs/kr-model-overlay-portfolio-v1.sha256").read_text().strip() == "563b64ee6f4709a263719669f795ad55e7828e340f082358af1599453253b6fd"
    assert (ROOT / "research_specs/kr-industry-opportunity-anatomy-v1.sha256").read_text().strip() == "98278ce5724b27dd19d253eab6cb1e7854ea432a62098441cdad46d067609f55"
    assert (ROOT / "research_specs/kr-stock-within-industry-anatomy-v1.sha256").read_text().strip() == "cfcec648194e25a8914056266443e241528a68352054a10d75cb6889225e5073"


def test_pins_detect_a_changed_source_byte_a_changed_v1_artifact_and_any_new_acquisition(tmp_path):
    assert E.verify_pins(SPEC, ROOT)
    root = tmp_path / "repo"
    for rel in list(E.V1_SEALED_ARTIFACTS) + [V1.SPEC_PATH, V1.DESIGN_PATH]:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, root / rel)
    shutil.copytree(ROOT / V1.SNAPSHOT_DIR, root / V1.SNAPSHOT_DIR)
    assert E.verify_pins(SPEC, root)
    one = root / V1.SNAPSHOT_DIR / "FDR_KS200/raw_fdr.csv"
    original = one.read_bytes()
    one.write_bytes(original + b"x")
    with pytest.raises(ValueError, match="SOURCE_SNAPSHOT_FILE_CHANGED"):
        E.verify_pins(SPEC, root)
    one.write_bytes(original)
    (root / V1.SNAPSHOT_DIR / "NEW_SOURCE").mkdir()
    (root / V1.SNAPSHOT_DIR / "NEW_SOURCE" / "normalized.csv").write_text("date,value\n")
    with pytest.raises(ValueError, match="FILE_SET_CHANGED"):
        E.verify_pins(SPEC, root)
    shutil.rmtree(root / V1.SNAPSHOT_DIR / "NEW_SOURCE")
    readiness = root / "docs/results/kr-market-risk-anatomy-v1-readiness.json"
    readiness.write_text(readiness.read_text().replace("DATA_BLOCKED", "READY", 1))
    with pytest.raises(ValueError, match="V1_SEALED_ARTIFACT_CHANGED"):
        E.verify_pins(SPEC, root)
    with pytest.raises(ValueError, match="NEW_EXTERNAL_ACQUISITION_NOT_PERMITTED"):
        E.verify_pins(dict(SPEC, newExternalAcquisition=True), ROOT)


# --------------------------------------------------------------------------- #
# Readiness: label-free, deterministic, no outcome access
# --------------------------------------------------------------------------- #
def test_readiness_and_verify_never_read_a_value_or_call_an_outcome_function(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("OUTCOME_OR_VALUE_ACCESS_DURING_READINESS")
    for module, names in ((M, ("forward_targets", "underwater_episodes", "first_trigger_damage", "trigger_profile", "fast_features", "baseline_trigger_states", "feature_statistics")),
                          (AN, ("build_core_panel", "analyze", "feature_tables", "episode_tables", "obs_series")), (P, ("read_normalized", "parse_fred_observations", "parse_yahoo_chart", "parse_fdr_csv")),
                          (E, ("load_series", "execute", "extended_internals", "claim_execution_lock")), (V1, ("load_series", "execute"))):
        for name in names:
            monkeypatch.setattr(module, name, boom)
    assert E.verify(ROOT)["counters"] == E.Counters().__dict__ and E.verify(ROOT)["stoppedBeforeOutcomes"] is True
    r = E.readiness_audit(ROOT)
    assert r["counters"] == E.Counters().__dict__ and r["historicalExecutionPerformed"] is False and r["basedOnAnyReturnResult"] is False and r["newExternalAcquisition"] is False
    assert r["decision"] in (E.DECISION_READY, E.DECISION_BLOCKED) and r["checks"]["noOutcomeAccess"] is True


# --------------------------------------------------------------------------- #
# Lifecycle: authorization -> pins -> gates -> lock -> marker -> values
# --------------------------------------------------------------------------- #
def authorize(env=None, git=None, probe=lambda: False):
    return E.authorize_execution(SPEC, SHA, ROOT, dict(GOOD_ENV, **(env or {})), git or fake_git(), probe)


@pytest.mark.parametrize("env,reason", [({"GITHUB_ACTIONS": "false"}, "REQUIRES_ACTIONS"), ({"GITHUB_REF": "refs/pull/1/merge"}, "REQUIRES_MAIN"),
                                        ({"GITHUB_EVENT_NAME": "pull_request"}, "REQUIRES_WORKFLOW_DISPATCH"), ({"MARKET_INPUT_RUN_ID": "1"}, "INPUT_ARTIFACT_IDENTITY_MISMATCH")])
def test_execute_is_main_only_dispatch_only_and_input_pinned(env, reason):
    with pytest.raises(ValueError, match=reason):
        authorize(env)


def test_authorization_refuses_uncommitted_spec_existing_result_marker_or_lock(monkeypatch):
    assert authorize().specSha256 == SHA
    with pytest.raises(ValueError, match="SPEC_NOT_COMMITTED_AT_HEAD"):
        authorize(git=fake_git(committed=False))
    with pytest.raises(ValueError, match="EXECUTION_LOCK_ALREADY_EXISTS"):
        authorize(probe=lambda: True)
    monkeypatch.setattr(E, "RESULT_PATH", "docs/results/kr-market-risk-anatomy-v1-readiness.json")
    with pytest.raises(ValueError, match="RESULT_ALREADY_COMMITTED"):
        authorize()
    monkeypatch.setattr(E, "RESULT_PATH", "docs/results/synthetic-absent-result.json")
    monkeypatch.setattr(E, "MARKER_PATH", "docs/results/kr-market-risk-anatomy-v1-readiness.json")
    with pytest.raises(ValueError, match="MARKER_ALREADY_COMMITTED"):
        authorize()


def test_lock_is_study_level_exclusive_and_any_existing_prefix_ref_refuses_a_rerun():
    api = FakeApi()
    lock = E.claim_execution_lock(SHA, GOOD_ENV, api)
    assert lock.ref == E.lock_ref(SHA) and set(api.refs) == {E.STUDY_LOCK_REF, E.lock_ref(SHA)} and "PATCH" not in api.calls and "DELETE" not in api.calls
    with pytest.raises(ValueError, match="EXECUTION_LOCK_ALREADY_EXISTS"):
        E.claim_execution_lock(SHA, GOOD_ENV, api)
    with pytest.raises(ValueError, match="EXECUTION_LOCK_ALREADY_EXISTS"):
        E.claim_execution_lock("f" * 64, GOOD_ENV, api)         # a revised spec cannot reopen the study
    assert E.lock_exists(None, GOOD_ENV, FakeApi(existing=[E.LOCK_PREFIX + "-" + "9" * 64]))
    with pytest.raises(ValueError, match="UNVERIFIABLE"):
        E.lock_exists(None, dict(GOOD_ENV, GH_TOKEN=""), FakeApi())
    assert E.STUDY_LOCK_REF.startswith("refs/tags/kr-market-risk-anatomy-v2-") and "v1" not in E.LOCK_PREFIX


def test_values_need_both_permit_and_lock_and_leave_counters_zero_on_refusal():
    counters = E.Counters()
    with pytest.raises(ValueError, match="WITHOUT_PERMIT"):
        E.load_series(ROOT, counters, object(), None, SHA, "2026-09-17")
    with pytest.raises(ValueError, match="DURABLE_EXECUTION_LOCK_REQUIRED"):
        E.load_series(ROOT, counters, authorize(), None, SHA, "2026-09-17")
    assert counters.zero()


def ready_decision(root):
    return {"reference": {"primary": "FDR_KS200", "family": "KOSPI200", "basis": "PRICE_INDEX_LEVEL", "instrument": "x", "composite": False, "analysisEnd": "2026-09-17", "spliced": False},
            "roles": {"VIX": None, "USDKRW": None}, "gates": {"decision": E.DECISION_READY, "blockers": []}}


def test_lock_precedes_marker_precedes_every_value_read_and_a_failed_gate_creates_no_lock(tmp_path, monkeypatch):
    order = []

    class Stop(Exception):
        pass

    def load(*a, **k):
        order.append("load_series")
        raise Stop
    monkeypatch.setattr(E, "decide", lambda root=ROOT: order.append("decide") or ready_decision(root))
    original_claim, original_marker = E.claim_execution_lock, E.write_execution_marker
    monkeypatch.setattr(E, "claim_execution_lock", lambda *a, **k: order.append("claim_execution_lock") or original_claim(*a, **k))
    monkeypatch.setattr(E, "write_execution_marker", lambda *a, **k: order.append("write_execution_marker") or original_marker(*a, **k))
    monkeypatch.setattr(E, "load_series", load)
    api = FakeApi()
    with pytest.raises(Stop):
        E.execute(tmp_path / "out", SPEC, SHA, E.ExecutionPermit(SHA, E._PERMIT_TOKEN), ROOT, GOOD_ENV, api)
    assert order == ["decide", "claim_execution_lock", "write_execution_marker", "load_series"]
    marker = json.loads((tmp_path / "out" / "execution-started.json").read_text())
    assert marker["valuesReadBeforeThisMarker"] == 0 and marker["lockRef"] == E.lock_ref(SHA) and len(api.refs) == 2
    blocked, blocked_api = FakeApi(), FakeApi()
    monkeypatch.setattr(E, "decide", lambda root=ROOT: {"reference": {"primary": None}, "gates": {"decision": E.DECISION_BLOCKED, "blockers": ["PRIMARY_REFERENCE_NOT_SELECTED"]}})
    with pytest.raises(ValueError, match="READINESS_GATE_FAILED"):
        E.execute(tmp_path / "out2", SPEC, SHA, E.ExecutionPermit(SHA, E._PERMIT_TOKEN), ROOT, GOOD_ENV, blocked_api)
    assert blocked_api.refs == {} and blocked_api.calls == [] and blocked.refs == {} and not (tmp_path / "out2" / "execution-started.json").exists()
    assert json.loads((tmp_path / "out2" / "gates-failed.json").read_text())["counters"] == E.Counters().__dict__


def test_a_failed_pre_lock_pin_check_spends_nothing(tmp_path, monkeypatch):
    api = FakeApi()
    monkeypatch.setattr(E, "verify_pins", lambda spec, root=ROOT: (_ for _ in ()).throw(ValueError("SOURCE_SNAPSHOT_FILE_CHANGED: x")))
    with pytest.raises(ValueError, match="SOURCE_SNAPSHOT_FILE_CHANGED"):
        E.execute(tmp_path / "out", SPEC, SHA, E.ExecutionPermit(SHA, E._PERMIT_TOKEN), ROOT, GOOD_ENV, api)
    assert api.refs == {} and api.calls == [] and not (tmp_path / "out").exists()


def test_execute_without_a_permit_or_for_another_spec_is_refused():
    with pytest.raises(ValueError, match="WITHOUT_PERMIT"):
        E.execute("x", SPEC, SHA, object(), ROOT, GOOD_ENV, FakeApi())
    with pytest.raises(ValueError, match="PERMIT_FOR_A_DIFFERENT_SPEC"):
        E.execute("x", SPEC, SHA, E.ExecutionPermit("0" * 64, E._PERMIT_TOKEN), ROOT, GOOD_ENV, FakeApi())


def test_pull_request_environment_is_never_authorized_and_the_runner_refuses(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("run2", ROOT / "scripts/run_kr_market_risk_anatomy_v2.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    with pytest.raises(ValueError, match="REQUIRES_ACTIONS"):
        runner.run("execute", output=str(tmp_path), env={"GITHUB_ACTIONS": "false"})
    assert not any(tmp_path.iterdir())
    assert runner.run("verify", env={})["executeAuthorizedInThisEnvironment"] is False


def test_workflow_never_executes_on_pull_requests_has_one_write_permission_and_reads_the_v1_bytes():
    workflow = (ROOT / ".github/workflows/kr-market-risk-anatomy-v2.yml").read_text()
    for other in ("run_kr_factor_anatomy", "run_kr_top120_regime_review", "run_kr_industry_anatomy", "run_kr_stock_within_industry", "kr-model-overlay-portfolio-v1 execute",
                  "collect_dart", "KRX_API", "FRED_API_KEY", "schedule:", "cron", "acquire_kr_market_risk_sources"):
        assert other not in workflow
    execute = workflow[workflow.index("  execute:"):]
    assert "github.event_name == 'workflow_dispatch' && inputs.mode == 'execute'" in execute and "refs/heads/main" in execute
    assert workflow.count("contents: write") == 1 and "--mode execute" in execute and "--mode execute" not in workflow.split("  execute:")[0]
    assert "listMatchingRefs" in execute and "kr-market-risk-anatomy-v1/sources" in execute and "execution-lock'" in execute and "pull_request" in workflow
    assert "kr-market-risk-anatomy-v1-execution-lock" not in workflow


def test_v2_modules_contact_no_vendor_and_call_no_sealed_study():
    for rel in ("pipeline/kr_market_risk_sources_v2.py", "pipeline/kr_market_risk_anatomy_v2_execution.py", "scripts/run_kr_market_risk_anatomy_v2.py",
                "scripts/write_kr_market_risk_v2_readiness.py", "scripts/build_kr_market_risk_anatomy_v2_spec.py"):
        text = (ROOT / rel).read_text()
        for forbidden in ("requests.", "urllib.request", "http.client", "yfinance", "FinanceDataReader", "fdr.DataReader", "collect_dart", "KRX_API", "FRED_API_KEY", "run_kr_factor_anatomy",
                          "run_kr_top120_regime_review", "run_kr_model_overlay", "run_kr_industry_anatomy", "run_kr_stock_within_industry", "acquire_kr_market_risk_sources"):
            assert forbidden not in text, (rel, forbidden)
