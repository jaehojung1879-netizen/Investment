"""Authorization, lock and label-free verification guards. Invented inputs only; no GitHub call is made."""
import json

import numpy as np
import pandas as pd
import pytest

from pipeline import kr_factor_anatomy as A
from pipeline import replay_calendar as RC
from research.industry_alpha_next_v1 import inputs as IN
from research.industry_alpha_next_v1 import panel as P
from research.industry_alpha_next_v1 import run_study as R
from research.industry_alpha_next_v1 import study as S

DECISIONS = {"krHistoryClosureException": True, "classifiedOnlyEstimand": True, "admissionRule": "BLOCK_SCOPED",
             "minimumCompleteBlocks": 100, "sequentialGate": True, "supportRule": "AS_REGISTERED"}
MAIN = {"GITHUB_ACTIONS": "true", "GITHUB_REF": "refs/heads/main"}


def test_design_keeps_execution_disabled_and_the_executor_refuses_first():
    design = json.loads((R.HERE / "design.json").read_text())
    assert design["executionEnabled"] is False and design["authorization"] is None
    with pytest.raises(PermissionError, match="EXECUTION_DISABLED_IN_DESIGN"):
        R.authorize("/nonexistent", env=MAIN)


def test_execute_refuses_before_any_input_is_read(monkeypatch):
    monkeypatch.setattr(R, "load_real", lambda *a, **k: pytest.fail("inputs read before authorization"))
    with pytest.raises(PermissionError):
        R.execute("/nonexistent", env=MAIN)


@pytest.mark.parametrize("change, error", [
    ({"specSha256": "0" * 64}, "SPEC_CHANGED"),
    ({"codeSha256": {}}, "CODE_CHANGED"),
    ({"inputIdentitySha256": "0" * 64}, "INPUT_IDENTITY_CHANGED"),
    ({"studyId": "other"}, "ANOTHER_STUDY"),
    ({"ownerLogin": ""}, "OWNER_IDENTITY"),
    ({"ownerDecisions": {**DECISIONS, "sequentialGate": None}}, "OWNER_DECISION_MISSING"),
    ({"ownerDecisions": {**DECISIONS, "krHistoryClosureException": False}}, "EXPLICITLY_ACCEPTED"),
    ({"ownerDecisions": {**DECISIONS, "supportRule": "LOWER_THE_BAR"}}, "INVALID_SUPPORT_RULE"),
    ({"ownerDecisions": {**DECISIONS, "minimumCompleteBlocks": True}}, "INVALID_MINIMUM"),
])
def test_every_authorization_field_is_checked(tmp_path, monkeypatch, change, error):
    monkeypatch.setattr(R.json, "loads", _design_enabled(R.json.loads))
    auth = {"studyId": S.STUDY_ID, "specSha256": S.spec_sha256(), "codeSha256": S.code_sha256(),
            "inputIdentitySha256": IN.identity()["sha256"], "ownerLogin": "owner", "ownerDecisions": DECISIONS} | change
    path = tmp_path / "auth.json"
    path.write_text(json.dumps(auth))
    with pytest.raises(PermissionError, match=error):
        R.authorize(path, env=MAIN)


def test_a_complete_authorization_yields_a_permit_only_in_actions_on_main(tmp_path, monkeypatch):
    monkeypatch.setattr(R.json, "loads", _design_enabled(R.json.loads))
    auth = {"studyId": S.STUDY_ID, "specSha256": S.spec_sha256(), "codeSha256": S.code_sha256(),
            "inputIdentitySha256": IN.identity()["sha256"], "ownerLogin": "owner", "ownerDecisions": DECISIONS}
    path = tmp_path / "auth.json"
    path.write_text(json.dumps(auth))
    permit, decisions = R.authorize(path, env=MAIN)
    assert permit.scope == "AUTHORIZED_HISTORICAL" and decisions == DECISIONS
    with pytest.raises(PermissionError, match="MERGED_MAIN"):
        R.authorize(path, env={"GITHUB_ACTIONS": "true", "GITHUB_REF": "refs/heads/feature"})


def _design_enabled(real):
    def loads(text, *a, **k):
        value = real(text, *a, **k)
        if isinstance(value, dict) and value.get("schema") == "INDUSTRY_ALPHA_NEXT_DESIGN_V1":
            value = {**value, "executionEnabled": True}
        return value
    return loads


class FakeApi:
    def __init__(self, existing=(), get_status=200, post_status=201):
        self.existing, self.get_status, self.post_status, self.calls = list(existing), get_status, post_status, []

    def __call__(self, method, path, payload, env):
        self.calls.append((method, path))
        return (self.get_status, self.existing) if method == "GET" else (self.post_status, {})


def test_one_shot_lock_refuses_any_existing_ref_and_unverifiable_state():
    assert R.claim_lock("abc", {}, FakeApi())["ref"] == R.LOCK_PREFIX
    with pytest.raises(PermissionError, match="CONSUMED"):
        R.claim_lock("abc", {}, FakeApi(existing=[{"ref": R.LOCK_PREFIX + "-x"}]))
    with pytest.raises(RuntimeError, match="UNVERIFIABLE"):
        R.claim_lock("abc", {}, FakeApi(get_status=403))
    with pytest.raises(PermissionError, match="NOT_ACQUIRED"):
        R.claim_lock("abc", {}, FakeApi(post_status=422))
    api = FakeApi()
    R.claim_lock("abc", {}, api)
    assert [m for m, _ in api.calls] == ["GET", "POST"]


def invented_inputs():
    days = RC.sessions("2013-01-01", S.DEVELOPMENT_CUTOFF, "KR")
    rng = np.random.default_rng(0)
    tickers = [f"{i:06d}.KS" for i in range(40)]
    prices = {t: pd.DataFrame({"Close": 100 * np.exp(np.cumsum(rng.normal(0, 0.01, len(days)))), "Volume": 1000.0},
                              index=days) for t in tickers + [S.BENCHMARK]}
    weekly = {str(d.date()): tickers for d in days[days >= "2015-01-01"][::5]}
    intervals = {t: [{"start": None, "end": None, "label": f"L{i % 8}", "status": "CURRENT_KRX_KIND_ANCHOR",
                      "reconstruction_status": "CURRENT_KRX_KIND_ANCHOR"}] for i, t in enumerate(tickers)}
    crosswalk = {"mapping": {f"L{i}": f"G{i}" for i in range(8)}}
    snaps = [{"date": str(d.date()), "ticker": t, "marketCap": 1e9 * (1 + i)} for d in days[::21] for i, t in enumerate(tickers)]
    caps = IN.SnapshotCaps(snaps)
    return {"membership": {"intervals": intervals, "crosswalk": crosswalk, "ends": {}, "weekly": weekly,
                           "terminal": {tickers[0]}},
            "caps": caps, "prices": prices, "accounting": {}, "marketAdapter": IN.GitMarket(caps, prices),
            "through": S.DEVELOPMENT_CUTOFF}


def test_verify_inputs_never_enters_an_outcome_function(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("outcome function entered during label-free verification")
    monkeypatch.setattr(A, "endpoint_returns", boom)
    monkeypatch.setattr(P, "industry_and_laggard_targets", boom)
    monkeypatch.setattr(R, "forward_table", boom)
    report = R.verify_inputs(invented_inputs())
    assert report["outcomeCalls"] == 0 and report["evidenceClass"] == "LABEL_FREE_INPUT_VERIFICATION"
    assert report["industryDates"]["eligible"] > 0 and set(report["calendarSupport"]) == {"H126", "H252"}
    text = json.dumps(report, default=str)
    assert "cwRelative" not in text and "Relative\": " not in text


def test_spec_hash_is_deterministic_and_slots_come_from_design():
    assert S.spec_sha256() == S.spec_sha256() and len(S.slots()) == 36
    assert set(S.code_sha256()) == set(S.CODE_FILES)
    assert S.spec()["STATUS"] == "PREPARED_NOT_AUTHORIZED"


def test_synthetic_mode_runs_the_whole_analysis_and_is_labelled_synthetic():
    out = R.synthetic(signal=0.0)
    assert out["evidenceClass"] == "SYNTHETIC_FIXTURE" and len(out["analysis"]["family"]) == 36


def test_authorization_draft_is_never_an_authorization(tmp_path, monkeypatch):
    draft = R.authorization_draft()
    assert draft["specSha256"] == S.spec_sha256() and all(v is None for v in draft["ownerDecisions"].values())
    monkeypatch.setattr(R.json, "loads", _design_enabled(R.json.loads))
    path = tmp_path / "draft.json"
    path.write_text(json.dumps(draft))
    with pytest.raises(PermissionError):
        R.authorize(path, env=MAIN)
