"""Outcome-free regression tests for the raw collector's active absence state."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from pipeline import dart_canonical_accounts as CA
from pipeline import dart_raw_statements as RS
from pipeline import historical_store as HS
from scripts import collect_dart_raw_statements as collect

KEY = RS.record_id("000001.KS", 2026, "11014")
ATTEMPTS = [{"fsDiv": "CFS", "status": "013", "rows": 0},
            {"fsDiv": "OFS", "status": "013", "rows": 0}]


def row(checked):
    return {
        "fiscalYear": 2026,
        "reportCode": "11014",
        "attempts": ATTEMPTS,
        "checkedAt": checked,
    }


@pytest.mark.parametrize(("checked", "today", "expected"), [
    ("2026-09-28T12:25:09Z", "2026-11-25", False),
    ("2026-09-28T12:25:09Z", "2027-01-14", False),
    ("2027-01-13T23:59:59Z", "2027-01-14", False),
    ("2027-01-14T00:00:00Z", "2027-01-14", True),
    ("2027-01-15T00:00:00Z", "2027-01-14", False),
    ("2027-01-14T00:00:00", "2027-01-14", False),
    ("2027-01-14T01:00:00+09:00", "2027-01-14", False),
    ("invalid", "2027-01-14", False),
    (None, "2027-01-14", False),
])
def test_confirmation_is_based_on_observation_not_elapsed_time(checked, today, expected):
    absent = {KEY: row(checked)}
    assert (KEY in collect.confirmed_absences(absent, today)) is expected


def test_old_frozen_gate_would_skip_a_premature_negative_but_new_work_list_retries():
    absent = {KEY: row("2026-09-28T12:25:09Z")}
    assert RS.settled(absent, "2027-01-14") == {KEY}
    pending = RS.work_list(
        ["000001.KS"], [2026], ["11014"], set(),
        collect.confirmed_absences(absent, "2027-01-14"),
    )
    assert pending == [("000001.KS", 2026, "11014")]


@pytest.mark.parametrize("attempts", [
    [{"fsDiv": "CFS", "status": "013"}],
    [{"fsDiv": "CFS", "status": "013"}, {"fsDiv": "OFS", "status": "800"}],
    [{"fsDiv": "CFS", "status": "013"}, {"fsDiv": "CFS", "status": "013"}],
    [None],
    None,
])
def test_only_both_verified_negative_responses_can_settle(attempts):
    entry = row("2027-01-14T00:00:00Z")
    entry["attempts"] = attempts
    assert collect.confirmed_absences({KEY: entry}, "2027-01-14") == set()


def test_served_and_unresolved_supersede_active_absence_without_double_counting():
    absent = {"recovered": {}, "failed": {}, "still_absent": {}}
    unresolved = {"recovered": {}, "failed": {}, "only_unresolved": {}}
    collect.reconcile_active_statuses(absent, unresolved, {"recovered"})
    assert set(absent) == {"still_absent"}
    assert set(unresolved) == {"failed", "only_unresolved"}
    assert not set(absent) & set(unresolved)


def test_recent_year_refresh_prioritizes_due_q3_before_future_annual():
    pending = [("A.KS", 2026, "11012"), ("A.KS", 2026, "11014"),
               ("A.KS", 2026, "11011"), ("B.KS", 2026, "11014"),
               ("B.KS", 2026, "11011")]
    absent = {RS.record_id("A.KS", 2026, "11014"): row("2026-11-24T00:00:00Z"),
              RS.record_id("B.KS", 2026, "11014"): row("2026-09-28T00:00:00Z")}
    ordered = collect.prioritize_refresh(pending, absent, {}, "2026-11-25")
    assert ordered[:3] == [("B.KS", 2026, "11014"), ("A.KS", 2026, "11014"),
                           ("A.KS", 2026, "11012")]
    assert [x[2] for x in ordered[3:]] == ["11011", "11011"]


def test_historical_backfill_order_stays_unchanged():
    pending = [("A.KS", 2016, "11013"), ("A.KS", 2016, "11011"),
               ("B.KS", 2016, "11014")]
    assert collect.prioritize_refresh(pending, {}, {}, "2026-11-25") == pending


def test_two_013_labels_with_nonzero_rows_do_not_settle():
    entry = row("2027-01-14T00:00:00Z")
    entry["attempts"] = [dict(ATTEMPTS[0], rows=1), ATTEMPTS[1]]
    assert collect.confirmed_absences({KEY: entry}, "2027-01-14") == set()


@pytest.mark.parametrize("payload", [
    {"status": "013", "list": [{"unexpected": "row"}]},
    {"status": "013", "list": "malformed"},
    {"status": "000", "list": []},
    {"status": "000", "list": [None]},
    {"status": "100"},
    [],
])
def test_cfs_failure_never_falls_through_to_ofs(monkeypatch, payload):
    seen = []

    def fake(path, params):
        seen.append(params["fs_div"])
        return payload

    monkeypatch.setattr(collect, "call_json", fake)
    rows, basis, attempts, stop = collect.fetch_statement("k", "c", 2026, "11014", collect.Budget(2, 10))
    assert rows == [] and basis is None and stop is None
    assert seen == ["CFS"]
    assert not collect.genuine_negative(attempts)


@pytest.fixture
def raw_q3(tmp_path, monkeypatch):
    class CollectionClock(datetime):
        current = datetime(2026, 11, 26, tzinfo=timezone.utc)

        @classmethod
        def now(cls, tz=None):
            return cls.current.astimezone(tz)

    monkeypatch.setattr(collect, "datetime", CollectionClock)
    monkeypatch.setattr(collect, "year_codes", lambda _: ("11014",))
    monkeypatch.setattr(collect, "PACE_SECONDS", 0)
    directory = [{"corpCode": f"{i:08}", "corpName": f"Issuer {i}", "stockCode": f"{i:06}"}
                 for i in range(1, 4)]

    def run(answer, max_calls, *, issuers=1):
        calls = []

        def fake(path, params):
            assert path == "fnlttSinglAcntAll.json"
            calls.append((params["corp_code"], params["fs_div"]))
            return answer(calls[-1])

        monkeypatch.setattr(collect, "call_json", fake)
        universe = {f"{x['stockCode']}.KS": x["corpName"] for x in directory[:issuers]}
        manifest = collect.collect(tmp_path, "mock-key", universe, [2026], collect.Budget(max_calls, 10),
                                   directory_fn=lambda _: directory)
        return manifest, calls

    return run, CollectionClock


def asset(receipt="20261113000001"):
    return {"rcept_no": receipt, "sj_div": "BS", "account_nm": "자산총계",
            "account_id": "ifrs-full_Assets", "thstrm_amount": "100"}


def test_collect_filters_bad_rows_from_both_ledgers_without_stopping(raw_q3, tmp_path):
    run, _ = raw_q3
    bad = RS.record_id("000002.KS", 2026, "11014")
    other_bad = RS.record_id("000003.KS", 2026, "11014")
    (tmp_path / "absent.json").write_text(json.dumps({KEY: None}), encoding="utf-8")
    (tmp_path / "unresolved.json").write_text(json.dumps({bad: None, other_bad: {
        "ticker": "000003.KS", "fiscalYear": 2026, "reportCode": "11014",
        "attempts": [{"fsDiv": ["CFS"], "status": "013"}], "checkedAt": {"bad": "timestamp"},
    }}), encoding="utf-8")

    manifest, calls = run(lambda _: {"status": "000", "list": [asset()]}, 3, issuers=3)

    assert calls == [("00000001", "CFS"), ("00000002", "CFS"), ("00000003", "CFS")]
    assert manifest["thisRun"]["invalidActiveRows"] == {"absent": 1, "unresolved": 2}
    assert manifest["thisRun"]["written"] == 3
    assert manifest["datasetComplete"]
    assert json.loads((tmp_path / "absent.json").read_text()) == {}
    assert json.loads((tmp_path / "unresolved.json").read_text()) == {}


@pytest.mark.parametrize("ofs_served", [False, True])
def test_collect_resumes_ofs_with_a_one_call_budget(raw_q3, tmp_path, ofs_served):
    run, _ = raw_q3
    first, calls = run(lambda _: {"status": "013"}, 1, issuers=2)
    assert calls == [("00000001", "CFS")]
    assert first["thisRun"]["stopReason"] == "CALL_BUDGET_SPENT"
    assert first["thisRun"]["attemptStatuses"] == {"CFS=013": 1}
    assert first["recordedAbsences"] == 0
    partial = json.loads((tmp_path / "unresolved.json").read_text())[KEY]
    assert partial["evidence"] == RS.NOT_ESTABLISHED

    answer = {"status": "000", "list": [asset()]} if ofs_served else {"status": "013"}
    second, calls = run(lambda _: answer, 1, issuers=2)
    assert calls == [("00000001", "OFS")]
    assert second["thisRun"]["calls"] == 1
    assert second["thisRun"]["attemptStatuses"] == {f"OFS={answer['status']}": 1}
    assert second["unresolvedFilings"] == 0
    assert second["thisRun"]["written"] == int(ofs_served)
    assert second["recordedAbsences"] == int(not ofs_served)
    if ofs_served:
        stored, = HS.read_jsonl(tmp_path / "raw-2026.jsonl.gz")
        assert stored["id"] == KEY and stored["fsDiv"] == "OFS"
        assert [a["status"] for a in stored["attempts"]] == ["013", "000"]


def test_collect_resumed_absence_cannot_settle_using_only_the_later_observation(raw_q3, tmp_path):
    run, clock = raw_q3
    clock.current = datetime(2027, 1, 13, 23, 59, 59, tzinfo=timezone.utc)
    run(lambda _: {"status": "013"}, 1)
    clock.current = datetime(2027, 1, 14, tzinfo=timezone.utc)
    manifest, calls = run(lambda _: {"status": "013"}, 1)
    assert calls == [("00000001", "OFS")]
    assert manifest["recordedAbsences"] == 1 and manifest["remaining"] == 1
    absent = json.loads((tmp_path / "absent.json").read_text())
    assert collect.confirmed_absences(absent, "2027-01-14") == set()


def test_collect_restarts_with_cfs_if_the_checkpoint_has_expired(raw_q3):
    run, clock = raw_q3
    run(lambda _: {"status": "013"}, 1)
    clock.current = datetime(2026, 12, 5, tzinfo=timezone.utc)
    manifest, calls = run(lambda _: {"status": "000", "list": [asset()]}, 1)
    assert calls == [("00000001", "CFS")]
    assert manifest["thisRun"]["written"] == 1 and manifest["unresolvedFilings"] == 0


@pytest.mark.parametrize("receipt,reason", [
    ("20261120000001", "MIXED_RECEIPT_NUMBERS"),
    ("20261113000002", "MIXED_RECEIPT_NUMBERS"),
    ("20261131000001", "INVALID_RECEIPT_NUMBER"),
    ("20261113", "INVALID_RECEIPT_NUMBER"),
    (None, "INVALID_RECEIPT_NUMBER"),
])
def test_collect_quarantines_mixed_or_incomplete_receipts_before_canonical_input(raw_q3, tmp_path,
                                                                                 receipt, reason):
    run, _ = raw_q3

    def answer(call):
        rows = [asset(), asset(receipt)] if call[0] == "00000001" else [asset()]
        return {"status": "000", "list": rows}

    manifest, calls = run(answer, 2, issuers=2)
    assert calls == [("00000001", "CFS"), ("00000002", "CFS")]
    assert manifest["thisRun"]["receiptRejections"] == {reason: 1}
    assert manifest["recordedAbsences"] == 0 and manifest["thisRun"]["written"] == 1
    unresolved = json.loads((tmp_path / "unresolved.json").read_text())
    assert unresolved[KEY]["reason"] == reason
    assert unresolved[KEY]["attempts"][0]["status"] == "000"
    stored, = HS.read_jsonl(tmp_path / "raw-2026.jsonl.gz")
    canonical, error = CA.canonical_record(stored)
    assert error == "" and canonical["availableFrom"] == "2026-11-13"
    assert stored["ticker"] == "000002.KS" and stored["rows"] == [asset()]
