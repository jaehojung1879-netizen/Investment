"""Network-free regressions for the scheduled DART statement collector."""
from __future__ import annotations

import pytest

from scripts import collect_dart_fundamentals as collect

KEY = "sample"
NEG = {"status": "013"}
POS = {"status": "000", "list": [{"account_nm": "assets"}]}


@pytest.mark.parametrize(("responses", "expected", "basis", "calls"), [
    ([POS], "000", "CFS", 1),
    ([NEG, POS], "000", "OFS", 2),
    ([NEG, NEG], "013", "OFS", 2),
    ([NEG, {"status": "800"}], "800", "OFS", 2),
    ([{"status": "100"}], "100", "CFS", 1),
    ([{"status": "000", "list": []}], "INVALID_SUCCESS_PAYLOAD", "CFS", 1),
    ([{"status": "013", "list": [{}]}], "CONTRADICTORY_ABSENCE_PAYLOAD", "CFS", 1),
    ([{"status": "900"}], "900", "CFS", 1),
    ([{"status": "020"}], "020", "CFS", 1),
    ([{"status": "014"}], "014", "CFS", 1),
    ([{"status": "unexpected"}], "UNKNOWN_STATUS", "CFS", 1),
    ([None], "REQUEST_FAILED", "CFS", 1),
    ([[]], "REQUEST_FAILED", "CFS", 1),
])
def test_preserve_source_disposition(monkeypatch, responses, expected, basis, calls):
    iterator = iter(responses)
    seen = []

    def call(path, params):
        seen.append(params["fs_div"])
        return next(iterator), "never persist this diagnostic"

    monkeypatch.setattr(collect, "call", call)
    rows, fs_div, status, attempts = collect.fetch_statement_evidence("secret", "corp", 2026, "11014")
    assert (status, fs_div, len(seen)) == (expected, basis, calls)
    assert len(attempts) == calls
    assert "secret" not in repr(attempts)
    assert bool(rows) == (expected == "000")
    if expected == "013":
        assert attempts == [{"fsDiv": "CFS", "status": "013"}, {"fsDiv": "OFS", "status": "013"}]


def entry(checked):
    return {"fiscalYear": 2026, "reportCode": "11014", "status": "013",
            "attempts": [{"fsDiv": "CFS", "status": "013"}, {"fsDiv": "OFS", "status": "013"}],
            "checkedAt": checked}


@pytest.mark.parametrize(("checked", "today", "expected"), [
    ("2026-09-28T12:25:09Z", "2027-01-14", False),
    ("2027-01-13T23:59:59Z", "2027-01-14", False),
    ("2027-01-14T00:00:00Z", "2027-01-14", True),
    ("2027-01-15T00:00:00Z", "2027-01-14", False),
    ("2027-01-14T00:00:00", "2027-01-14", False),
    ("bad", "2027-01-14", False),
])
def test_negative_evidence_requires_post_grace_check(checked, today, expected):
    assert (KEY in collect.confirmed_absences({KEY: entry(checked)}, today)) is expected


def test_legacy_collapsed_013_is_unverified():
    legacy = entry("2027-01-14T00:00:00Z")
    legacy.pop("attempts")
    assert collect.confirmed_absences({KEY: legacy}, "2027-01-14") == set()


def test_current_due_filing_precedes_historical_and_future_rechecks():
    pending = [("A.KS", 2016, "11013"), ("A.KS", 2026, "11011"),
               ("B.KS", 2026, "11014"), ("A.KS", 2026, "11012")]
    assert collect.prioritize_due(pending, "2026-11-25") == [
        ("B.KS", 2026, "11014"), ("A.KS", 2026, "11012"),
        ("A.KS", 2016, "11013"), ("A.KS", 2026, "11011")]
