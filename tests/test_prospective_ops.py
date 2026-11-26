"""prospective-ops-v1: status ledger, writer guard, post-write verification, workflow safety. Synthetic receipts only; no real ledger read."""
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from pipeline import prospective_ops as ops
from scripts import prospective_ops as cli

ROOT = Path(__file__).resolve().parents[1]
SPEC, AUTH, CODE = "a" * 64, "b" * 64, "c" * 40
DAYS = ["2026-11-09", "2026-11-10", "2026-11-11", "2026-11-12", "2026-11-13", "2026-11-16", "2026-11-17"]
SESSIONS = DAYS + ["2026-11-18", "2026-11-19", "2026-11-20", "2026-11-23", "2026-11-24"]


def study(**over):
    base = {"studyId": "s1", "kind": "SESSION_DAILY_KR", "firstEligibleSession": DAYS[0], "horizons": [2], "ledgerPath": "l.jsonl",
            "approval": {"status": ops.APPROVED, "authorizationSha256": AUTH, "specSha256": SPEC},
            "writer": {"legacyWriters": [{"id": "trig_x"}]},
            "automation": {"enabled": False, "pinnedCodeCommit": CODE, "singleWriterAttestation": "att.json"},
            "monitoring": {"continuityBaselineSession": None}}
    base.update(over)
    return base


def row(day, events=None, stamp=None):
    events = [] if events is None else events
    value = {"studyId": "s1", "signalDate": day, "createdAtUtc": stamp or day + "T10:40:00Z", "mode": "LIVE", "evidenceClass": "PROSPECTIVE_PAPER",
             "specSha256": SPEC, "authorizationSha256": AUTH, "events": events, "eventCount": len(events)}
    value["receiptSha256"] = ops.receipt_digest(value)
    return value


def at(text):
    return ops.parse_utc(text)


def status(rows, as_of="2026-11-12T12:00:00Z", **kwargs):
    return ops.study_status(kwargs.pop("study", study()), rows, SESSIONS, at(as_of), **kwargs)


def test_missing_closed_window_is_missed_not_zero_events_and_pending_is_not_missed():
    result = status([row(DAYS[0]), row(DAYS[2])], as_of="2026-11-12T12:00:00Z")
    assert result["operatingState"] == "MISSED" and result["missedSessions"] == [DAYS[1]]
    assert result["pendingSessions"] == [DAYS[3]] and result["scheduledRecords"] == 3 and result["validRecords"] == 2


def test_zero_event_receipt_is_a_valid_record():
    assert status([row(DAYS[0])], as_of="2026-11-10T01:00:00Z")["validRecords"] == 1


def test_enabled_study_with_every_window_recorded_is_healthy_and_disabled_one_is_not():
    rows = [row(d) for d in DAYS[:3]]
    enabled = study(automation={"enabled": True, "pinnedCodeCommit": CODE, "singleWriterAttestation": "a"})
    assert status(rows, "2026-11-12T01:00:00Z", study=enabled)["operatingState"] == "HEALTHY"
    assert status(rows, "2026-11-12T01:00:00Z")["operatingState"] == "DISABLED"


def test_baseline_marks_old_holes_but_does_not_hide_new_ones():
    s = study(monitoring={"continuityBaselineSession": DAYS[2]})
    result = status([row(DAYS[0])], "2026-11-12T01:00:00Z", study=s)
    assert result["missedNotObservedBeforeBaseline"] == [DAYS[1], DAYS[2]] and result["operatingState"] != "MISSED"
    assert status([row(DAYS[0])], "2026-11-13T01:00:00Z", study=s)["operatingState"] == "MISSED"


def test_baseline_never_reduces_the_missed_count():
    s = study(monitoring={"continuityBaselineSession": DAYS[2]})
    assert status([row(DAYS[0])], "2026-11-12T01:00:00Z", study=s)["missedRecords"] == 2


def test_unauthorized_and_absent_ledger_and_failed_run():
    assert ops.study_status(study(approval={"status": "REGISTERED_NOT_AUTHORIZED"}), None, SESSIONS, at("2026-11-12T00:00:00Z"))["operatingState"] == "UNAUTHORIZED"
    assert status(None)["operatingState"] == "SOURCE_BLOCKED"
    assert status([row(DAYS[0])], "2026-11-10T01:00:00Z", writer_outcome="failure")["operatingState"] == "EXECUTION_FAILED"


def test_a_successful_run_without_a_receipt_is_not_healthy():
    enabled = study(automation={"enabled": True, "pinnedCodeCommit": CODE, "singleWriterAttestation": "a"})
    result = status([], "2026-11-11T01:00:00Z", study=enabled, writer_outcome="success")
    assert result["operatingState"] == "MISSED"


@pytest.mark.parametrize("mutate,reason", [
    (lambda r: r.update(mode="DRY_RUN"), "REGISTRATION_OR_MODE_MISMATCH"),
    (lambda r: r.update(eventCount=3), "EVENT_COUNT_MISMATCH"),
    (lambda r: r.update(createdAtUtc="2026-11-10T00:00:00Z"), "OUTSIDE_AUTHORIZED_WINDOW"),
    (lambda r: r.update(createdAtUtc="2026-11-09T08:59:00Z"), "OUTSIDE_AUTHORIZED_WINDOW"),
])
def test_invalid_receipts_are_flagged_and_not_counted(mutate, reason):
    bad = row(DAYS[0])
    mutate(bad)
    if reason != "REGISTRATION_OR_MODE_MISMATCH" and reason != "EVENT_COUNT_MISMATCH" and reason != "OUTSIDE_AUTHORIZED_WINDOW":
        bad["receiptSha256"] = ops.receipt_digest(bad)
    result = status([bad], "2026-11-10T01:00:00Z")
    assert result["operatingState"] == "EXECUTION_FAILED" and reason in result["receiptErrors"][0]["reasons"] and result["validRecords"] == 0


def test_duplicate_session_invalidates_it():
    result = status([row(DAYS[0]), row(DAYS[0])], "2026-11-10T01:00:00Z")
    assert "DUPLICATE_SESSION" in result["receiptErrors"][0]["reasons"] and result["validRecords"] == 0


def test_independence_is_per_issuer_and_hypothesis_within_the_horizon():
    def event(corp, hyp, entry):
        return {"corp_code": corp, "hypothesis": hyp, "entrySession": entry, "rcept_no": corp + entry}
    rows = [row(DAYS[0], [event("1", "A1", DAYS[1]), event("2", "A1", DAYS[1])]), row(DAYS[1], [event("1", "A1", DAYS[2]), event("1", "B1", DAYS[2])])]
    kept = ops.independent_observations(rows, {DAYS[0], DAYS[1]}, SESSIONS, horizon=2)
    assert {k["key"] for k in kept} == {("1", "A1"), ("2", "A1"), ("1", "B1")} and len(kept) == 3  # raw events 4, independent 3
    assert ops.independent_observations(rows, {DAYS[0]}, SESSIONS, 2) != ops.independent_observations(rows, {DAYS[0], DAYS[1]}, SESSIONS, 2)
    summary = ops.maturity_summary(kept, DAYS[3])
    assert summary["independentObservations"] == 3 and summary["evaluable"] == 2 and summary["nextMaturity"] == DAYS[4]


def test_events_of_invalid_receipts_never_count():
    assert ops.independent_observations([row(DAYS[0], [{"corp_code": "1", "hypothesis": "A1", "entrySession": DAYS[1]}])], set(), SESSIONS, 2) == []


def test_weekly_kind_excludes_the_unfinished_week():
    assert ops.weekly_last_sessions(SESSIONS, DAYS[0]) == ["2026-11-13", "2026-11-20"]


def test_observed_only_makes_no_completeness_claim():
    s = study(kind="OBSERVED_ONLY", monitoring={"maxStaleCalendarDays": 5})
    fresh = ops.study_status(s, [{"signalDate": "2026-11-20"}], SESSIONS, at("2026-11-23T00:00:00Z"))
    assert fresh["operatingState"] == "HEALTHY" and fresh["scheduledRecords"] is None and fresh["completenessClaim"].startswith("NONE")
    assert ops.study_status(s, [{"signalDate": "2026-11-01"}], SESSIONS, at("2026-11-23T00:00:00Z"))["operatingState"] == "MISSED"


def test_registry_refuses_enabling_an_unapproved_or_unattested_study():
    registry = {"schema": ops.REGISTRY_SCHEMA, "studies": [study(approval={"status": "REGISTERED_NOT_AUTHORIZED"}, automation={"enabled": True})]}
    assert "s1: AUTOMATION_ENABLED_WITHOUT_APPROVAL" in ops.validate_registry(registry)
    registry["studies"] = [study(automation={"enabled": True, "pinnedCodeCommit": CODE})]
    assert "s1: AUTOMATION_WITHOUT_SINGLE_WRITER_ATTESTATION" in ops.validate_registry(registry)
    registry["studies"] = [study(), study()]
    assert "s1: DUPLICATE_STUDY_ID" in ops.validate_registry(registry)


def test_committed_registry_is_valid_and_nothing_is_enabled():
    registry = json.loads((ROOT / "research/prospective_ops/registry.json").read_text())
    assert ops.validate_registry(registry) == []
    assert not any(s.get("automation", {}).get("enabled") for s in registry["studies"])
    corporate = registry["studies"][0]
    assert corporate["approval"]["specSha256"] == "1692b5b3131a76ab6dd8a5198ef0fd262fffa4ec7cf0925444cf344aacbd61d4"
    assert corporate["automation"]["pinnedCodeCommit"] == "8aee189ff453d9bd624a67df5e1e5975bd7d211c"


def test_guard_allows_only_with_every_condition_and_refuses_each_missing_one():
    enabled = study(automation={"enabled": True, "pinnedCodeCommit": CODE, "singleWriterAttestation": "a"})
    attest = {"studyId": "s1", "legacyWriterStates": {"trig_x": "DISABLED"}}
    authz = {"studyId": "s1", "specSha256": SPEC}
    assert ops.guard_decision(enabled, attest, authz, True, [])["decision"] == "ALLOW_WRITE"
    assert "AUTOMATION_NOT_ENABLED_BY_OWNER" in ops.guard_decision(study(), attest, authz, True, [])["reasons"]
    assert "SINGLE_WRITER_ATTESTATION_MISSING" in ops.guard_decision(enabled, None, authz, True, [])["reasons"]
    still_on = {"studyId": "s1", "legacyWriterStates": {"trig_x": "ENABLED"}}
    assert "LEGACY_WRITER_NOT_ATTESTED_DISABLED:trig_x" in ops.guard_decision(enabled, still_on, authz, True, [])["reasons"]
    assert "PINNED_CODE_COMMIT_UNAVAILABLE" in ops.guard_decision(enabled, attest, authz, False, [])["reasons"]
    assert "AUTHORIZATION_OR_SPEC_MISMATCH" in ops.guard_decision(enabled, attest, {"studyId": "s1", "specSha256": "d" * 64}, True, [])["reasons"]
    assert "REMOTE_LEDGER_INTEGRITY_ERRORS" in ops.guard_decision(enabled, attest, authz, True, [{"line": 1}])["reasons"]
    assert ops.guard_decision(enabled, attest, None, True, [])["decision"] == "REFUSE"


def test_verify_new_receipt_requires_exactly_one_valid_row():
    windows = ops.session_windows(SESSIONS, DAYS[0])
    now = at("2026-11-10T01:00:00Z")
    assert ops.verify_new_receipt([row(DAYS[0])], study(), DAYS[0], windows, now)["result"] == "RECORDED_AND_VERIFIED"
    assert ops.verify_new_receipt([], study(), DAYS[0], windows, now)["result"] == "NOT_RECORDED"
    assert ops.verify_new_receipt([row(DAYS[0]), row(DAYS[0])], study(), DAYS[0], windows, now)["result"] == "NOT_RECORDED"


def test_build_status_alerts_only_for_enabled_studies():
    enabled = study(studyId="e", automation={"enabled": True, "pinnedCodeCommit": CODE, "singleWriterAttestation": "a"})
    registry = {"schema": ops.REGISTRY_SCHEMA, "studies": [study(), enabled]}
    out = ops.build_status(registry, {"s1": [], "e": []}, SESSIONS, at("2026-11-12T12:00:00Z"))
    assert [s["operatingState"] for s in out["studies"]] == ["MISSED", "MISSED"] and out["alerts"] == ["e"]


def test_registry_row_cannot_carry_result_fields():
    registry = {"schema": ops.REGISTRY_SCHEMA, "studies": [study(realizedReturn=1.0)]}
    assert any("RESULT_FIELD" in p for p in ops.validate_registry(registry))


def test_cli_reads_exact_git_objects_and_never_writes(tmp_path, monkeypatch):
    repo = tmp_path / "r"
    repo.mkdir()
    run = lambda *a: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=repo, check=True, capture_output=True, text=True)
    run("init", "-q", "-b", "led")
    (repo / "l.jsonl").write_text("\n".join(json.dumps(row(d)) for d in DAYS[:2]) + "\n")
    run("add", "."), run("commit", "-qm", "x")
    reg = {"schema": ops.REGISTRY_SCHEMA, "studies": [study()]}
    registry = tmp_path / "reg.json"
    registry.write_text(json.dumps(reg))
    monkeypatch.setattr(cli, "git", lambda *a, cwd=repo, check=True: subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, check=check))
    assert len(cli.read_rows("led", "l.jsonl")) == 2 and cli.read_rows("led", "absent.jsonl") is None
    before = (repo / "l.jsonl").read_bytes()
    code = cli.main(["--registry", str(registry), "status", "--ledger-ref", "led", "--as-of", "2026-11-12T12:00:00Z", "--out", str(tmp_path / "o.json")])
    assert code == 0  # not enabled: a known state, not an alert
    out = json.loads((tmp_path / "o.json").read_text())
    assert out["studies"][0]["missedRecords"] == 1 and (repo / "l.jsonl").read_bytes() == before


TEMPLATE_PATH = ROOT / "research/prospective_ops/install/prospective-ops.yml"
WORKFLOW = TEMPLATE_PATH.read_text()


def test_workflow_has_no_ai_and_guards_before_writing():
    code = re.sub(r"#.*", "", WORKFLOW)
    assert "ANTHROPIC" not in code and "OPENAI" not in code
    assert code.index("Guard (fail closed)") < code.index("live_run")
    assert "steps.guard.outputs.allowed == 'true'" in code
    assert "cancel-in-progress: false" in code and "group: prospective-ops" in code
    assert "github.ref == 'refs/heads/main'" in code


def test_workflow_never_force_pushes_or_edits_a_receipt():
    code = re.sub(r"#.*", "", WORKFLOW)
    assert "--force" not in code and "push -f" not in code
    assert "receipts.jsonl" not in code
    for forbidden in ("sed -i", "truncate", "> ledger"):
        assert forbidden not in code


def test_every_scheduled_time_is_after_the_kr_final_close_and_before_the_next_open():
    for minute, hour in re.findall(r'cron: "(\d+) (\d+) \* \* 1-5"', WORKFLOW):
        utc = int(hour) * 60 + int(minute)
        assert 9 * 60 < utc < 24 * 60  # 18:00 KST = 09:00 UTC final close; 00:00 UTC next open


def test_status_clock_uses_utc_aware_timestamps():
    assert ops.parse_utc("2026-11-25T01:00:00Z").tzinfo == timezone.utc and isinstance(datetime.now(timezone.utc), datetime)
    with pytest.raises(ValueError):
        ops.parse_utc("2026-11-25T01:00:00")


def test_workflow_is_a_template_outside_the_sealed_workflow_tree():
    # Sealed studies pin the workflow census and the .github/workflows tree digest; installing is a separate owner-approved amendment.
    assert not (ROOT / ".github/workflows/prospective-ops.yml").exists()
    assert TEMPLATE_PATH.is_file() and "workflow_dispatch" in WORKFLOW
