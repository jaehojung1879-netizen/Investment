"""Network-free regressions for the scheduled DART statement collector."""
from __future__ import annotations

import json
from types import SimpleNamespace

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


def test_main_recovers_legacy_absence_and_counts_only_verified_negative(tmp_path, monkeypatch):
    """Real main, local shard write and manifest, with DART responses stubbed."""
    monkeypatch.setenv("DART_API_KEY", "test-key")
    monkeypatch.setattr(collect, "load_config", lambda: (SimpleNamespace(longterm={}), None))
    monkeypatch.setattr(collect.universe_mod, "resolve", lambda _: ({"KR": ["000001.KS"]}, None))
    monkeypatch.setattr(collect, "corp_code_map", lambda _: {"000001": "00000001"})
    monkeypatch.setattr(collect.time, "sleep", lambda _: None)
    recovered = collect.DF.record_id("000001.KS", 2020, "11014")
    legacy = {"fiscalYear": 2020, "reportCode": "11014", "status": "013",
              "checkedAt": "2021-01-31T00:00:00Z"}
    (tmp_path / "absent.json").write_text(json.dumps({recovered: legacy}), encoding="utf-8")

    def call(path, params):
        code = params["reprt_code"]
        if code == "11014":
            return {"status": "000", "list": [
                {"account_nm": "자산총계", "sj_div": "BS",
                 "thstrm_amount": "100", "rcept_no": "20201114000001"}]}, ""
        if code == "11012":
            return {"status": "013"}, ""
        return {"status": "100"}, ""

    monkeypatch.setattr(collect, "call", call)
    assert collect.main([str(tmp_path), "--target", "statements",
                         "--from-year", "2020", "--to-year", "2020",
                         "--max-calls", "4"]) == 0
    absent = json.loads((tmp_path / "absent.json").read_text(encoding="utf-8"))
    half = collect.DF.record_id("000001.KS", 2020, "11012")
    assert set(absent) == {half}
    assert recovered not in absent
    assert absent[half]["attempts"] == [
        {"fsDiv": "CFS", "status": "013"}, {"fsDiv": "OFS", "status": "013"}]
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["progress"]["total"] == 4
    assert manifest["progress"]["collected"] == 1
    assert manifest["progress"]["absent"] == 1
    assert manifest["progress"]["pending"] == 2
    assert manifest["thisRun"]["statuses"] == {"000": 1, "013": 1, "100": 2}
