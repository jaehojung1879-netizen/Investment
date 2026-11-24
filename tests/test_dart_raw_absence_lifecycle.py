"""Outcome-free regression tests for the raw collector's active absence state."""
from __future__ import annotations

import pytest

from pipeline import dart_raw_statements as RS
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
