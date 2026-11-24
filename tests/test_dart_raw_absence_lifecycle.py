"""Outcome-free regression tests for the raw collector's active absence state."""
from __future__ import annotations

import pytest

from pipeline import dart_raw_statements as RS
from scripts import collect_dart_raw_statements as collect

KEY = RS.record_id("000001.KS", 2026, "11014")
ATTEMPTS = [{"fsDiv": "CFS", "status": "013"}, {"fsDiv": "OFS", "status": "013"}]


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
