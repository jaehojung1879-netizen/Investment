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
    enabled = study(automation={"enabled": True, "pinnedCodeCommit": CODE, "pinnedTreeSha": "d" * 40, "singleWriterAttestation": "a"})
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
    enabled = study(automation={"enabled": True, "pinnedCodeCommit": CODE, "pinnedTreeSha": "d" * 40, "singleWriterAttestation": "a"})
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
    assert fresh["operatingState"] == "PENDING" and fresh["scheduledRecords"] is None  # recent is not complete: never HEALTHY
    assert fresh["freshness"]["state"] == "FRESH" and fresh["completeness"] == {"state": "NOT_ASSESSABLE", "basis": "NO_REGISTERED_CADENCE"}
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


def facts(**over):
    base = {"attestation": {
                "schema": ops.CUTOVER_SCHEMA, "studyId": "s1", "attestedAtUtc": "2026-11-26T00:00:00Z",
                "successor": ops.SUCCESSOR, "pinnedCodeCommit": CODE, "authorizationSha256": AUTH,
                "legacyRunsDrained": True, "retiredPermanently": True, "readbacks": [
                    {"id": "trig_x", "enabled": False, "readbackUtc": "2026-11-26T00:00:00Z",
                     "source": "CLAUDE_GET_TRIGGER_READBACK"},
                ],
            },
            "ownerApprovalAt": at("2026-11-26T01:00:00Z"),
            "authorization": {"studyId": "s1", "specSha256": SPEC}, "authorizationBytesSha256": AUTH, "specBytesSha256": SPEC,
            "pinnedCommitPresent": True, "pinnedTreeSha": "d" * 40, "durablyReferenced": True,
            "ledger": [row(DAYS[0])], "integrityErrors": [], "asOf": at("2026-11-27T00:00:00Z")}
    base.update(over)
    return base


def enabled_study(**over):
    automation = {"enabled": True, "pinnedCodeCommit": CODE, "pinnedTreeSha": "d" * 40, "singleWriterAttestation": "a"}
    return study(automation=automation, **over)


def reasons(f=None, s=None):
    return ops.guard_decision(s or enabled_study(), f or facts())["reasons"]


def test_guard_allows_only_with_every_condition():
    assert ops.guard_decision(enabled_study(), facts())["decision"] == "ALLOW_WRITE"
    assert "AUTOMATION_NOT_ENABLED_BY_OWNER" in reasons(s=study())


def test_guard_checks_the_authorization_bytes_hash_not_just_its_fields():
    # fields agree, but the file's bytes hash is not the registered one: refused (a re-written authorization cannot pass on its fields)
    assert "AUTHORIZATION_BYTES_HASH_MISMATCH" in reasons(facts(authorizationBytesSha256="e" * 64))
    assert "AUTHORIZATION_BYTES_HASH_MISMATCH" in reasons(facts(authorizationBytesSha256=None))
    assert "SPEC_BYTES_HASH_MISMATCH" in reasons(facts(specBytesSha256="e" * 64))
    # bytes hashes agree but the parsed fields do not
    assert "AUTHORIZATION_FIELDS_MISMATCH" in reasons(facts(authorization={"studyId": "s1", "specSha256": "e" * 64}))
    assert "AUTHORIZATION_FIELDS_MISMATCH" in reasons(facts(authorization=None))


def test_guard_pinned_code_must_exist_match_its_tree_and_be_durably_referenced():
    assert "PINNED_CODE_COMMIT_UNAVAILABLE" in reasons(facts(pinnedCommitPresent=False))
    assert "PINNED_TREE_HASH_MISMATCH" in reasons(facts(pinnedTreeSha="e" * 40))
    assert "PINNED_CODE_NOT_DURABLY_REFERENCED" in reasons(facts(durablyReferenced=False))


def test_guard_single_writer_requires_exact_readbacks_and_fresh_evidence_at_cutover():
    assert "SINGLE_WRITER_ATTESTATION_MISSING" in reasons(facts(attestation=None))
    a = facts()["attestation"]
    readback = a["readbacks"][0]
    for value in (True, 0, "false", None):
        changed = a | {"readbacks": [readback | {"enabled": value}]}
        assert "LEGACY_WRITER_NOT_VERIFIED_DISABLED:trig_x" in reasons(facts(attestation=changed))
    for entries in ([], [readback, readback], [readback | {"id": "wrong"}]):
        assert "LEGACY_WRITER_READBACK_IDS_MISMATCH" in reasons(facts(attestation=a | {"readbacks": entries}))
    for date in ("2026-11-18T00:00:00Z", "2026-11-26T00:00:01Z"):
        changed = a | {"readbacks": [readback | {"readbackUtc": date}]}
        assert "LEGACY_WRITER_READBACK_OUTSIDE_CUTOVER_WINDOW:trig_x" in reasons(facts(attestation=changed))
    assert "SINGLE_WRITER_APPROVAL_TIME_INVALID" in reasons(facts(asOf=at("2026-11-25T00:00:00Z")))
    assert "SINGLE_WRITER_APPROVAL_TIME_INVALID" in reasons(facts(ownerApprovalAt=None))
    assert "SINGLE_WRITER_APPROVAL_TIME_INVALID" in reasons(facts(attestation=a | {"attestedAtUtc": "garbage"}))
    assert "SINGLE_WRITER_CUTOVER_SCOPE_MISMATCH" in reasons(facts(attestation=a | {"legacyRunsDrained": False}))
    assert reasons(facts(asOf=at("2027-04-20T00:00:00Z"))) == []


def test_owner_approval_is_a_live_exact_byte_endorsement_on_the_control_issue():
    import hashlib
    raw = b'{"retiredPermanently": true}\n'
    comment = {
        "issue_url": "https://api.github.com/repos/jaehojung1879-netizen/Investment/issues/292",
        "user": {"id": 238918679}, "author_association": "OWNER",
        "body": f"{ops.CUTOVER_SCHEMA} sha256={hashlib.sha256(raw).hexdigest()}",
        "updated_at": "2026-11-26T01:00:00Z",
    }
    assert cli.owner_approval_time(comment, raw) == at("2026-11-26T01:00:00Z")
    assert cli.owner_approval_time(comment, raw + b" ") is None
    assert cli.owner_approval_time(comment | {"user": {"id": 1}}, raw) is None
    assert cli.owner_approval_time(comment | {"issue_url": comment["issue_url"] + "0"}, raw) is None
    assert cli.owner_approval_time(comment | {"body": "revoked"}, raw) is None


def test_guard_distinguishes_read_failure_absent_file_and_valid_empty_ledger():
    must = enabled_study(ledgerMustExist=True)
    failed = {"state": ops.LEDGER_READ_FAILED, "rows": [], "detail": "REF_UNREACHABLE"}
    absent = {"state": ops.LEDGER_ABSENT, "rows": [], "detail": None}
    empty = {"state": ops.LEDGER_EMPTY_VALID, "rows": [], "detail": None}
    assert "LEDGER_READ_FAILED" in reasons(facts(ledger=failed), must)
    assert "LEDGER_FILE_ABSENT_FOR_STUDY_WITH_EXISTING_RECEIPTS" in reasons(facts(ledger=absent), must)
    assert "LEDGER_EMPTY_FOR_STUDY_WITH_EXISTING_RECEIPTS" in reasons(facts(ledger=empty), must)
    # a first-ever study (ledgerMustExist false) may start from a missing or empty ledger, but never from a failed read
    first = enabled_study()
    assert ops.guard_decision(first, facts(ledger=absent))["decision"] == "ALLOW_WRITE"
    assert ops.guard_decision(first, facts(ledger=empty))["decision"] == "ALLOW_WRITE"
    assert "LEDGER_READ_FAILED" in reasons(facts(ledger=failed), first)


def test_guard_refuses_altered_baseline_receipts_and_integrity_errors():
    base = enabled_study(baselineReceipts=[{"session": DAYS[0], "receiptSha256": row(DAYS[0])["receiptSha256"]}])
    assert ops.guard_decision(base, facts())["decision"] == "ALLOW_WRITE"
    altered = row(DAYS[0])
    altered["eventCount"] = 9
    assert "BASELINE_RECEIPTS_ALTERED_OR_MISSING" in reasons(facts(ledger=[altered]), base)
    assert "BASELINE_RECEIPTS_ALTERED_OR_MISSING" in reasons(facts(ledger=[]), base)
    assert "REMOTE_LEDGER_INTEGRITY_ERRORS" in reasons(facts(integrityErrors=[{"line": 1}]))


def test_status_distinguishes_read_failure_absent_and_empty_ledgers():
    must = study(ledgerMustExist=True)
    now = "2026-11-10T01:00:00Z"
    failed = status({"state": ops.LEDGER_READ_FAILED, "rows": [], "detail": "X"}, now, study=must)
    assert failed["operatingState"] == "SOURCE_BLOCKED" and failed["failureReason"] == "LEDGER_READ_FAILED"
    absent = status({"state": ops.LEDGER_ABSENT, "rows": []}, now, study=must)
    assert absent["failureReason"] == "LEDGER_FILE_ABSENT_ON_REACHABLE_REF"
    assert status(None, now)["failureReason"] == "LEDGER_NOT_YET_CREATED"
    empty = status({"state": ops.LEDGER_EMPTY_VALID, "rows": []}, now)
    assert empty["ledgerRead"] == "EMPTY_VALID" and empty["missedRecords"] == 1 and empty["operatingState"] == "MISSED"


def test_unreadable_or_absent_ledger_of_an_approved_existing_study_alerts_even_when_disabled():
    registry = {"schema": ops.REGISTRY_SCHEMA, "studies": [study(ledgerMustExist=True)]}
    for state in (ops.LEDGER_READ_FAILED, ops.LEDGER_ABSENT):
        out = ops.build_status(registry, {"s1": {"state": state, "rows": []}}, SESSIONS, at("2026-11-12T12:00:00Z"))
        assert out["alerts"] == ["s1"]


def test_altered_baseline_is_an_incident_even_when_no_writer_is_enabled():
    base = study(baselineReceipts=[{"session": DAYS[0], "receiptSha256": row(DAYS[0])["receiptSha256"]}])
    tampered = row(DAYS[0], events=[{"corp_code": "x"}])
    out = ops.build_status({"schema": ops.REGISTRY_SCHEMA, "studies": [base]}, {"s1": [tampered]}, SESSIONS, at("2026-11-10T01:00:00Z"))
    assert out["alerts"] == ["s1"] and out["studies"][0]["operatingState"] == "EXECUTION_FAILED"


def test_freshness_and_completeness_are_separate_states():
    # fresh but incomplete: the newest record is recent while an earlier window is missing
    partial = status([row(DAYS[0]), row(DAYS[2])], "2026-11-12T12:00:00Z")
    assert partial["freshness"]["state"] == "FRESH" and partial["completeness"]["state"] == "INCOMPLETE"
    # stale and empty
    assert status([], "2026-11-30T12:00:00Z")["freshness"]["state"] == "UNKNOWN"
    old = status([row(DAYS[0])], "2026-12-30T12:00:00Z")
    assert old["freshness"]["state"] == "STALE"
    # complete and fresh, but disabled: completeness is verified without being called healthy
    ok = status([row(DAYS[0]), row(DAYS[1])], "2026-11-11T01:00:00Z")
    assert ok["completeness"]["state"] == "VERIFIED_COMPLETE" and ok["operatingState"] == "DISABLED"
    live = status([row(DAYS[0]), row(DAYS[1])], "2026-11-11T01:00:00Z", study=enabled_study())
    assert live["operatingState"] == "HEALTHY"


def test_baseline_verification_detects_missing_altered_and_reordered_receipts():
    a, b = row(DAYS[0]), row(DAYS[1])
    s = study(baselineReceipts=[{"session": DAYS[0], "receiptSha256": a["receiptSha256"]}, {"session": DAYS[1], "receiptSha256": b["receiptSha256"]}])
    assert ops.verify_baseline([a, b, row(DAYS[2])], s)["state"] == "INTACT"
    assert ops.verify_baseline([b, a], s)["state"] == "VIOLATED"
    assert ops.verify_baseline([a], s)["problems"][0]["reason"] == "RECEIPT_MISSING"
    assert ops.verify_baseline([a, b], study())["state"] == "NOT_REGISTERED"


def test_writer_session_same_day_retries_delay_and_boundaries():
    sess = ["2026-11-12", "2026-11-13", "2026-11-16", "2026-11-17"]
    # every scheduled time of one KST day speaks for the same session
    assert {ops.writer_session(at(f"2026-11-12T{t}:00Z"), sess) for t in ("10:40", "11:40", "13:00", "14:20", "14:59")} == {"2026-11-12"}
    assert ops.writer_session(at("2026-11-12T09:00:00Z"), sess) == "2026-11-12"   # 18:00 KST final close is inclusive
    assert ops.writer_session(at("2026-11-12T08:59:59Z"), sess) is None          # not final yet
    assert ops.writer_session(at("2026-11-12T15:00:00Z"), sess) is None            # KST midnight: the date is now the 13th and its close (09:00 UTC) has not come
    assert ops.writer_session(at("2026-11-13T10:40:00Z"), sess) == "2026-11-13"
    # a run delayed past KST midnight on Friday, or on the weekend, writes nothing: the session stays missed
    assert ops.writer_session(at("2026-11-13T15:00:00Z"), sess) is None
    assert ops.writer_session(at("2026-11-13T23:30:00Z"), sess) is None
    assert ops.writer_session(at("2026-11-14T10:40:00Z"), sess) is None
    assert ops.writer_session(at("2026-11-15T10:40:00Z"), sess) is None


def test_receipt_window_outlives_the_writers_own_reach():
    sess = ["2026-11-12", "2026-11-13", "2026-11-16", "2026-11-17"]
    # Friday's receipt window stays open until Monday 00:00 UTC, but the registered writer cannot reach it after 15:00 UTC Friday
    assert ops.window_session(at("2026-11-14T10:40:00Z"), sess) == "2026-11-13"
    assert ops.window_session(at("2026-11-16T00:00:00Z"), sess) is None
    assert ops.window_session(at("2026-11-12T08:59:59Z"), sess) is None
    assert ops.window_session(at("2026-11-13T00:00:00Z"), sess) is None            # the next open ends Thursday's window (exclusive)


def test_a_weekday_holiday_has_no_writer_session():
    import pandas
    from pipeline import replay_calendar as calendar
    days = [d.strftime("%Y-%m-%d") for d in calendar.sessions("2026-12-01", "2027-01-15", "KR")]
    holidays = sorted({d.strftime("%Y-%m-%d") for d in pandas.bdate_range("2026-12-01", "2027-01-14")} - set(days))
    assert holidays, "expected at least one KR weekday closure in the window"
    for holiday in holidays:
        for t in ("10:40", "12:40", "14:20"):
            assert ops.writer_session(at(f"{holiday}T{t}:00Z"), days) is None


def test_template_schedule_times_are_inside_the_writers_reach():
    cron = re.findall(r'cron: "(\d+) (\d+) \* \* 1-5"', WORKFLOW)
    assert len(cron) >= 3
    for minute, hour in cron:
        utc = int(hour) * 60 + int(minute)
        assert 9 * 60 <= utc < 15 * 60  # after the 18:00 KST close and before KST midnight, or the writer speaks for nothing


def test_same_session_retry_after_success_is_a_duplicate_not_a_second_receipt():
    once, again = row(DAYS[0]), row(DAYS[0], stamp=DAYS[0] + "T12:40:00Z")
    result = status([once, again], "2026-11-10T01:00:00Z")
    assert result["validRecords"] == 0 and "DUPLICATE_SESSION" in result["receiptErrors"][0]["reasons"]
    windows = ops.session_windows(SESSIONS, DAYS[0])
    assert ops.verify_new_receipt([once, again], study(), DAYS[0], windows, at("2026-11-10T01:00:00Z"))["result"] == "NOT_RECORDED"


def test_delayed_receipt_outside_its_window_is_not_a_receipt():
    late = row(DAYS[0], stamp="2026-11-10T00:00:00Z")  # exactly the next open
    early = row(DAYS[0], stamp="2026-11-09T08:59:59Z")  # before the final close
    on_time = row(DAYS[1], stamp="2026-11-10T09:00:00Z")  # exactly the close: valid
    windows = ops.session_windows(SESSIONS, DAYS[0])
    valid, errors = ops.verify_rows([late, early, on_time], study(), windows, at("2026-11-11T01:00:00Z"))
    assert valid == {DAYS[1]} and {e["session"] for e in errors} == {DAYS[0]}


def test_verify_new_receipt_requires_exactly_one_valid_row():
    windows = ops.session_windows(SESSIONS, DAYS[0])
    now = at("2026-11-10T01:00:00Z")
    assert ops.verify_new_receipt([row(DAYS[0])], study(), DAYS[0], windows, now)["result"] == "RECORDED_AND_VERIFIED"
    assert ops.verify_new_receipt([], study(), DAYS[0], windows, now)["result"] == "NOT_RECORDED"
    assert ops.verify_new_receipt([row(DAYS[0]), row(DAYS[0])], study(), DAYS[0], windows, now)["result"] == "NOT_RECORDED"


def test_build_status_alerts_only_for_enabled_studies():
    enabled = study(studyId="e", automation={"enabled": True, "pinnedCodeCommit": CODE, "pinnedTreeSha": "d" * 40, "singleWriterAttestation": "a"})
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
    monkeypatch.setattr(cli, "git_bytes", lambda *a, cwd=repo: (lambda r: (r.returncode, r.stdout))(subprocess.run(["git", *a], cwd=cwd, capture_output=True)))
    assert len(cli.read_rows("led", "l.jsonl")) == 2 and cli.read_rows("led", "absent.jsonl") is None
    assert cli.read_ledger("led", "l.jsonl")["state"] == "ROWS" and cli.read_ledger("led", "absent.jsonl")["state"] == "ABSENT"
    assert cli.read_ledger("no-such-ref", "l.jsonl")["state"] == "READ_FAILED"   # unreachable ref is not "no rows"
    (repo / "empty.jsonl").write_text("")
    (repo / "bad.jsonl").write_text("{not json\n")
    run("add", "."), run("commit", "-qm", "y")
    assert cli.read_ledger("led", "empty.jsonl")["state"] == "EMPTY_VALID"
    assert cli.read_ledger("led", "bad.jsonl")["state"] == "READ_FAILED"
    with pytest.raises(RuntimeError):
        cli.read_rows("no-such-ref", "l.jsonl")
    before = (repo / "l.jsonl").read_bytes()
    code = cli.main(["--registry", str(registry), "status", "--ledger-ref", "led", "--as-of", "2026-11-12T12:00:00Z", "--out", str(tmp_path / "o.json")])
    assert code == 0  # not enabled: a known state, not an alert
    out = json.loads((tmp_path / "o.json").read_text())
    assert out["studies"][0]["missedRecords"] == 1 and (repo / "l.jsonl").read_bytes() == before


WORKFLOW_PATH = ROOT / ".github/workflows/prospective-ops.yml"
WORKFLOW = WORKFLOW_PATH.read_text()


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


def test_install_binds_exact_live_workflow_and_additive_inventory(tmp_path):
    from pipeline import prospective_workflow_maintenance as maintenance

    maintenance.verify_install(ROOT)
    for path in maintenance.INSTALL_BYTES:
        copy = tmp_path / path
        copy.parent.mkdir(parents=True, exist_ok=True)
        copy.write_bytes((ROOT / path).read_bytes())
    maintenance.verify_install(tmp_path)
    (tmp_path / maintenance.WORKFLOW).write_bytes(WORKFLOW_PATH.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="PROSPECTIVE_WORKFLOW_INSTALL_BYTES_CHANGED"):
        maintenance.verify_install(tmp_path)


# ------------------------------------------------------------------------ push conflicts (real git, local bare remotes)
@pytest.fixture(autouse=True)
def git_identity(monkeypatch):
    """Give literal registered Git functions a committer identity, even on hosted runners."""
    for key, value in (("GIT_AUTHOR_NAME", "t"), ("GIT_AUTHOR_EMAIL", "t@t"), ("GIT_COMMITTER_NAME", "t"), ("GIT_COMMITTER_EMAIL", "t@t")):
        monkeypatch.setenv(key, value)


def test_workflow_sets_a_git_identity_before_the_registered_writer_runs():
    live_step = WORKFLOW.split("name: Registered LIVE run", 1)[1].split("  monitor:", 1)[0]
    invocation = live_step.index("-m research.corporate_event_readiness_v1.cohort.live_run")
    assert live_step.index("GIT_COMMITTER_NAME:") < invocation
    assert live_step.index("GIT_COMMITTER_EMAIL:") < invocation

import ast  # noqa: E402
import os  # noqa: E402
import stat  # noqa: E402

PINNED = "8aee189ff453d9bd624a67df5e1e5975bd7d211c"
RECEIPTS = "ledger/research-strategies/kr-corporate-information-events-v1/receipts.jsonl"


def _g(cwd, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def _remote_with_ledger(tmp_path):
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "signal-history", str(origin)], check=True)
    seed = tmp_path / "seed"
    subprocess.run(["git", "clone", "-q", str(origin), str(seed)], check=True, capture_output=True)
    _g(seed, "checkout", "-q", "-b", "signal-history")
    (seed / RECEIPTS).parent.mkdir(parents=True)
    (seed / RECEIPTS).write_text(json.dumps(row(DAYS[0])) + "\n")
    _g(seed, "add", "."), _g(seed, "commit", "-qm", "seed"), _g(seed, "push", "-q", "origin", "signal-history")
    return origin


def _clone(origin, path):
    subprocess.run(["git", "clone", "-q", str(origin), str(path)], check=True, capture_output=True)
    _g(path, "checkout", "-q", "signal-history")
    return path


def _pinned_push_with_retry(worktree):
    """The registered writer's own push loop, taken byte-for-byte from the pinned commit (its module needs the whole repo to import)."""
    shown = subprocess.run(["git", "show", f"{PINNED}:research/corporate_event_readiness_v1/cohort/live_run.py"], cwd=ROOT, capture_output=True, text=True)
    if shown.returncode != 0:
        pytest.skip("pinned commit 8aee189 not available in this checkout")
    wanted = [n for n in ast.parse(shown.stdout).body if isinstance(n, ast.FunctionDef) and n.name in ("git", "push_with_retry")]
    from pathlib import Path
    namespace = {"Path": Path, "subprocess": subprocess, "time": type("T", (), {"sleep": staticmethod(lambda _s: None)}), "REPO": worktree, "LEDGER_RELATIVE": RECEIPTS}
    exec(compile(ast.Module(body=wanted, type_ignores=[]), "pinned_live_run", "exec"), namespace)  # noqa: S102 - bytes of the registered commit
    return namespace["push_with_retry"]


def test_pinned_writer_push_survives_an_unrelated_remote_advance(tmp_path):
    origin = _remote_with_ledger(tmp_path)
    mine, other = _clone(origin, tmp_path / "mine"), _clone(origin, tmp_path / "other")
    (other / "unrelated.txt").write_text("x")
    _g(other, "add", "."), _g(other, "commit", "-qm", "other"), _g(other, "push", "-q", "origin", "signal-history")
    with (mine / RECEIPTS).open("a") as handle:
        handle.write(json.dumps(row(DAYS[1])) + "\n")
    sha = _pinned_push_with_retry(mine)(mine, "receipt")
    assert sha == _g(mine, "rev-parse", "HEAD")
    remote = subprocess.run(["git", "show", f"signal-history:{RECEIPTS}"], cwd=origin, capture_output=True, text=True).stdout.splitlines()
    assert [json.loads(line)["signalDate"] for line in remote] == [DAYS[0], DAYS[1]]


def test_two_writers_for_the_same_session_cannot_both_land(tmp_path):
    origin = _remote_with_ledger(tmp_path)
    first, second = _clone(origin, tmp_path / "w1"), _clone(origin, tmp_path / "w2")
    for clone, stamp in ((first, "10:40:00Z"), (second, "10:41:00Z")):
        with (clone / RECEIPTS).open("a") as handle:
            handle.write(json.dumps(row(DAYS[1], stamp=f"{DAYS[1]}T{stamp}")) + "\n")
    push = _pinned_push_with_retry
    assert push(first)(first, "w1")
    with pytest.raises(RuntimeError, match="REBASE_ONTO_SIGNAL_HISTORY_FAILED"):
        push(second)(second, "w2")
    remote = subprocess.run(["git", "show", f"signal-history:{RECEIPTS}"], cwd=origin, capture_output=True, text=True).stdout.splitlines()
    assert [json.loads(line)["signalDate"] for line in remote] == [DAYS[0], DAYS[1]]  # exactly one receipt per session on the remote


def test_pinned_writer_gives_up_after_five_rejected_pushes_without_overwriting(tmp_path):
    origin = _remote_with_ledger(tmp_path)
    mine = _clone(origin, tmp_path / "mine")
    hook = origin / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(hook.stat().st_mode | stat.S_IEXEC)
    with (mine / RECEIPTS).open("a") as handle:
        handle.write(json.dumps(row(DAYS[1])) + "\n")
    with pytest.raises(RuntimeError, match="PUSH_FAILED_AFTER_5_ATTEMPTS"):
        _pinned_push_with_retry(mine)(mine, "receipt")
    assert len(subprocess.run(["git", "show", f"signal-history:{RECEIPTS}"], cwd=origin, capture_output=True, text=True).stdout.splitlines()) == 1


def _template_publish_loop():
    match = re.search(r"( *)for attempt in 1 2 3 4 5; do\n.*?\n\1done\n", WORKFLOW, re.S)
    assert match, "publish retry loop not found in the template"
    return "\n".join(line[len(match.group(1)):] for line in match.group(0).splitlines()) + "\n"


def _run_publish_loop(worktree, tmp_path):
    shim = tmp_path / "bin"
    shim.mkdir(exist_ok=True)
    (shim / "sleep").write_text("#!/bin/sh\nexit 0\n")
    (shim / "sleep").chmod(0o755)
    env = {**os.environ, "PATH": f"{shim}:{os.environ['PATH']}", "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    return subprocess.run(["bash", "-c", _template_publish_loop()], cwd=worktree, env=env, capture_output=True, text=True)


def test_template_status_publish_rebases_over_other_pushes_and_fails_closed_on_real_conflict(tmp_path):
    origin = _remote_with_ledger(tmp_path)
    mine, other = _clone(origin, tmp_path / "mine"), _clone(origin, tmp_path / "other")
    (other / "other.txt").write_text("x")
    _g(other, "add", "."), _g(other, "commit", "-qm", "o"), _g(other, "push", "-q", "origin", "signal-history")
    (mine / "ledger/research-ops").mkdir(parents=True)
    (mine / "ledger/research-ops/prospective-status.json").write_text("{}")
    _g(mine, "add", "."), _g(mine, "commit", "-qm", "status")
    assert _run_publish_loop(mine, tmp_path).returncode == 0
    # a genuine conflict (the other side edits the very same file) must fail, never overwrite
    (other / "ledger/research-ops").mkdir(parents=True, exist_ok=True)
    _g(other, "pull", "-q", "--rebase", "origin", "signal-history")
    (other / "ledger/research-ops/prospective-status.json").write_text('{"a": 1}')
    _g(other, "add", "."), _g(other, "commit", "-qm", "o2"), _g(other, "push", "-q", "origin", "signal-history")
    (mine / "ledger/research-ops/prospective-status.json").write_text('{"b": 2}')
    _g(mine, "add", "."), _g(mine, "commit", "-qm", "status2")
    failed = _run_publish_loop(mine, tmp_path)
    assert failed.returncode != 0
    shown = subprocess.run(["git", "show", "signal-history:ledger/research-ops/prospective-status.json"], cwd=origin, capture_output=True, text=True).stdout
    assert shown == '{"a": 1}'


def test_committed_registry_pins_the_three_existing_receipts_and_the_registered_writer():
    corporate = json.loads((ROOT / "research/prospective_ops/registry.json").read_text())["studies"][0]
    assert [b["session"] for b in corporate["baselineReceipts"]] == ["2026-11-09", "2026-11-11", "2026-11-12"]
    assert all(len(b["receiptSha256"]) == 64 for b in corporate["baselineReceipts"])
    assert corporate["ledgerMustExist"] is True and corporate["automation"]["enabled"] is False
    assert corporate["automation"]["pinnedTreeSha"] == "b1cd5b1852c401a1a9c3a13fce8b1466a4f5e61e"
    assert corporate["automation"]["preservation"]["status"] == "BRANCH_ONLY_NOT_DURABLE"


def test_this_change_touches_no_protected_path():
    registry = json.loads((ROOT / "research/prospective_ops/registry.json").read_text())
    prefixes = tuple(registry["protectedPathPrefixes"])
    diff = subprocess.run(["git", "diff", "--name-only", "origin/main...HEAD"], cwd=ROOT, capture_output=True, text=True)
    if diff.returncode != 0:
        pytest.skip("no origin/main history available")
    from pipeline.prospective_workflow_maintenance import WORKFLOW as installed_workflow, verify_install

    verify_install(ROOT)
    assert [p for p in diff.stdout.split() if p.startswith(prefixes) and p != installed_workflow] == []


def test_observed_receipts_keep_both_regions_and_dont_claim_validity():
    current = study(kind="OBSERVED_ONLY", dateField="asOfDate",
                    observationKey=["asOfDate", "region"], monitoring={"maxStaleCalendarDays": 5})
    rows = [{"asOfDate": DAYS[0], "region": region} for region in ("KR", "US", "US")]
    result = status(rows, "2026-11-10T00:00:00Z", study=current)
    assert result["observedRecords"] == 2
    assert result["validRecords"] is None


def test_metadata_only_evaluator_does_not_invent_a_result(monkeypatch):
    current = study(outcomeStatusPath="outcome-status.json")
    publication = {"studyId": "s1", "action": "outcomes", "status": "NOTHING_MATURED", "graded": 0, "value": 0.8}
    monkeypatch.setattr(cli, "git_bytes", lambda *_args: (0, json.dumps(publication).encode()))
    assert cli.outcome_publication("ledger", current) == {
        "state": "NOTHING_MATURED", "source": "outcome-status.json", "attemptedAt": None, "graded": 0,
    }
    publication["studyId"] = "wrong"
    assert cli.outcome_publication("ledger", current)["state"] == "EVALUATOR_STATUS_INVALID"


def test_baseline_prefix_rejects_byte_changes_and_accepts_only_suffix_appends(monkeypatch):
    import hashlib
    baseline = b'{"a": 1}\n'
    current = study(baselineLedger={"bytes": len(baseline), "sha256": hashlib.sha256(baseline).hexdigest()})
    monkeypatch.setattr(cli, "git_bytes", lambda *_args: (0, baseline + b'{"b": 2}\n'))
    assert cli.prefix_matches("ledger", current)
    monkeypatch.setattr(cli, "git_bytes", lambda *_args: (0, b'{"a":1}\n'))
    assert not cli.prefix_matches("ledger", current)
