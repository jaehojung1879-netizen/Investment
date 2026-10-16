"""Invented inputs only; no strategy result or market download is needed."""
from copy import deepcopy
import ast
from datetime import datetime
from pathlib import Path
import subprocess

import pytest

from pipeline import weekly_decision as W
from pipeline import weekly_publish as P
from test_weekly_publish import _site


@pytest.fixture(autouse=True)
def no_history(monkeypatch):
    monkeypatch.setattr(P.H, "build_history", lambda: {"available": False})


@pytest.mark.parametrize("region,at,expected", [
    ("KR", "2026-10-16T04:44:48.202397Z", "2026-10-15"),
    ("KR", "2026-10-16T07:29:59Z", "2026-10-15"),
    ("KR", "2026-10-16T07:30:00Z", "2026-10-15"),
    ("KR", "2026-10-16T08:59:59Z", "2026-10-15"),
    ("KR", "2026-10-16T09:00:00Z", "2026-10-16"),
    ("KR", "2025-11-13T08:29:59Z", "2025-11-12"),  # CSAT delayed close
    ("KR", "2025-11-13T08:30:00Z", "2025-11-12"),
    ("KR", "2025-11-13T09:00:00Z", "2025-11-13"),
    ("KR", "2026-10-09T23:00:00Z", "2026-10-08"),  # Hangul Day
    ("KR", "2026-06-03T12:00:00Z", "2026-06-02"),  # pinned closure override
    ("US", "2026-10-16T20:59:59Z", "2026-10-15"),
    ("US", "2026-10-16T21:00:00Z", "2026-10-16"),
    ("US", "2026-11-02T21:59:59Z", "2026-10-30"),  # DST ended
    ("US", "2026-11-02T22:00:00Z", "2026-11-02"),
    ("US", "2026-11-27T18:59:59Z", "2026-11-25"),  # 13:00 NY early close + 60m
    ("US", "2026-11-27T19:00:00Z", "2026-11-27"),
    ("US", "2027-01-01T23:00:00Z", "2026-12-31"),
])
def test_actual_close_plus_buffer(region, at, expected):
    instant = datetime.fromisoformat(at.replace("Z", "+00:00"))
    assert W.last_completed_session(region, instant) == expected
    assert W.last_completed_session(region, instant.astimezone(W.ZoneInfo("Asia/Seoul"))) == expected


@pytest.mark.parametrize("region,at", [
    ("KR", "2026-10-16T04:44:48.202397Z"),
    ("US", "2026-10-16T20:30:00Z"),
])
def test_future_friday_cannot_become_a_final(region, at):
    now = datetime.fromisoformat(at.replace("Z", "+00:00"))
    result = W.freshness(region, "2026-10-16", now)
    assert result["status"] == "INVALID" and result["weekEnd"] is False
    assert result["reason"] == "OBSERVATION_AFTER_COMPLETED_SESSION"
    site = _site(generatedAt=at, indices=[{"symbol": W.SESSION_EVIDENCE[region], "asOf": "2026-10-16"}])
    a, b = P.build_from_site(site, "synthetic-sha", []), P.build_from_site(site, "synthetic-sha", [])
    assert a == b and P.validate(a) == []
    blob = a["regions"][region]
    assert blob["status"] == "SOURCE_INCOMPLETE"
    assert not blob["weights"] and not blob["holdings"] and not blob["watchlist"]
    assert "receiptId" not in blob


def test_future_holiday_label_is_checked_before_normalization():
    at = datetime.fromisoformat("2026-10-10T02:00:00+00:00")
    assert W.freshness("KR", "2026-10-09", at)["status"] == "INVALID"
    assert W.freshness("US", "2026-10-11", at)["status"] == "INVALID"


def test_naive_clock_is_refused():
    with pytest.raises(ValueError, match="timezone-aware"):
        W.last_completed_session("KR", datetime(2026, 10, 16, 13, 44))


@pytest.mark.parametrize("bad_date", ["2026-10-15T00:00:00Z", "2026-02-30", 20261015])
def test_source_date_requires_an_exchange_date_label(bad_date):
    at = datetime.fromisoformat("2026-10-16T04:44:48+00:00")
    assert W.freshness("KR", bad_date, at)["reason"] == "OBSERVATION_DATE_INVALID"


def _premature():
    return W.build_receipt(W.decide("KR", [], None, "2026-10-16"),
                           generated_at="2026-10-16T04:44:48.202397Z", inputs={},
                           evidence=W.EVIDENCE, week_status="FINAL_WEEKLY")


def test_old_premature_receipt_is_never_repaired_by_a_later_clock():
    bad = _premature()
    before = deepcopy(bad)
    assert W.receipt_session_error(bad) == "OBSERVATION_AFTER_COMPLETED_SESSION"
    assert W.latest_final([bad], "KR") is None
    assert P.receipt_history([bad])["KR"] == []
    later = _site(generatedAt="2026-10-16T10:00:00Z", indices=[{"symbol": "^KS11", "asOf": "2026-10-16"}])
    later["longTerm"]["regions"]["KR"]["picks"] = []
    block = P.build_from_site(later, "synthetic-sha", [bad])
    kr = block["regions"]["KR"]
    assert kr["status"] == "SOURCE_INCOMPLETE" and not kr["weights"]
    assert kr["invalidRecordedReceipt"]["digest"] == bad["digest"]
    assert block["receiptIntegrity"][0]["status"] == "INVALID_SESSION"
    assert P.validate(block) == [] and bad == before
    merged, _ = W.append_receipts([bad], [])
    assert merged == [before]
    with pytest.raises(ValueError, match="receipt session invalid"):
        W.append_receipts([], [bad])


@pytest.mark.parametrize("region", ["KR", "US"])
def test_publisher_checks_sessions_independently_of_digest_and_freshness(region):
    block = P.build_from_site(_site(), "synthetic-sha", [])
    blob = block["regions"][region]
    blob["asOfDate"] = "2026-10-16"
    blob["digest"] = W.receipt_digest(blob)
    assert any(e.startswith(f"receipt_session_invalid:{region}") for e in P.validate(block))


def test_current_thursday_is_only_a_preview_while_friday_is_open():
    site = _site(generatedAt="2026-10-16T04:44:48Z",
                 indices=[{"symbol": "^KS11", "asOf": "2026-10-15"}])
    site["longTerm"]["regions"]["KR"]["picks"] = []
    blob = P.build_from_site(site, "synthetic-sha", [])["regions"]["KR"]
    assert blob["asOfDate"] == "2026-10-15" and blob["weekStatus"] == "INTRA_WEEK_PREVIEW"
    assert W.append_receipts([], [blob])[0] == []


def test_future_candidate_quote_cannot_enter_an_otherwise_completed_final():
    site = _site()
    site["details"]["A"]["asOf"] = "2026-10-12"
    blob = P.build_from_site(site, "synthetic-sha", [])["regions"]["KR"]
    assert blob["status"] == "SOURCE_INCOMPLETE" and not blob["weights"]
    assert "receiptId" not in blob


def test_safety_fix_preserves_all_investment_policy_and_digest_functions():
    root = Path(__file__).resolve().parents[1]
    original = subprocess.check_output(["git", "show", "002b56434e3aa3e845798ec2ea7ca6d9267e3f7a:pipeline/weekly_decision.py"], cwd=root).decode()
    current = (root / "pipeline/weekly_decision.py").read_text()
    names = {"cost_breakdown", "trade_cost_fraction", "edge_estimate", "score_candidates", "decide", "canonical",
             "receipt_digest", "calibration_digest", "receipt_id", "previous_change", "build_receipt"}
    def policies(source):
        return {n.name: ast.dump(n) for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name in names}
    assert policies(original) == policies(current) and len(policies(current)) == len(names)
