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


# --------------------------------------------------------------------------- #
# Delayed scheduled runs (#273): a build inside an unfinished session is
# deferred, never published, and the freshness gate itself is unchanged.
# --------------------------------------------------------------------------- #
import json  # noqa: E402


def _at(generated, kr=None, us="2026-10-20"):
    site = _site(generatedAt=generated, indices=[{"symbol": "^KS11", "asOf": kr},
                                                 {"symbol": "^GSPC", "asOf": us}])
    site["details"] = {"A": {"region": "KR", "asOf": kr}, "X": {"region": "US", "asOf": us}}
    return site


def _ledger(tmp_path, site):
    """A previous publication in the ledger layout, then the paths a run writes."""
    ledger = tmp_path / "prior"
    ledger.mkdir()
    path = tmp_path / "site.json"
    path.write_text(json.dumps(site))
    assert P.main([str(path), str(ledger / "receipts.jsonl"), str(ledger / "latest.json"),
                   str(ledger / "receipts.jsonl"), str(ledger / "publication-status.json")]) == 0
    out = tmp_path / "out"
    return ledger, [ledger / "receipts.jsonl", out / "latest.json", out / "receipts.jsonl",
                    out / "publication-status.json"]


def _run(tmp_path, site, paths):
    path = tmp_path / "site.json"
    path.write_text(json.dumps(site))
    return P.main([str(path)] + [str(p) for p in paths])


SATURDAY = "2026-10-17T04:35:17Z"   # previous publication: Friday 10-16 is final
EVENING = "2026-10-20T09:20:00Z"    # previous publication: the 18:20 KST weekday run


def _latest(path):
    return json.loads(Path(path).read_text())


def _receipts(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def test_2026_10_21_delayed_run_is_reproduced_and_only_kr_is_deferred(tmp_path, capsys):
    site = _at("2026-10-21T04:54:14.404960+00:00", kr="2026-10-21")  # 13:54 KST
    fresh = W.freshness("KR", "2026-10-21", datetime.fromisoformat(site["generatedAt"]))
    assert (fresh["status"], fresh["reason"]) == ("INVALID", "OBSERVATION_AFTER_COMPLETED_SESSION")
    assert (fresh["expectedSession"], fresh["observedSession"]) == ("2026-10-20", "2026-10-21")
    assert P.build_from_site(site, "sha", [])["regions"]["KR"]["status"] == "SOURCE_INCOMPLETE"
    assert P.unfinished_sessions(site) == {"KR": "2026-10-21"}
    ledger, paths = _ledger(tmp_path, _at(EVENING, kr="2026-10-20", us="2026-10-19"))
    prior = _latest(ledger / "latest.json")
    capsys.readouterr()
    assert _run(tmp_path, site, paths) == 0
    latest = _latest(paths[1])
    # KR keeps exactly what was published; NYSE 10-20 is final and publishes.
    assert latest["regions"]["KR"] == prior["regions"]["KR"]
    us = latest["regions"]["US"]
    assert us["asOfDate"] == us["freshness"]["expectedSession"] == "2026-10-20"
    assert latest["deferredRegions"] == {"KR": {"unfinishedSession": "2026-10-21",
                                                "carriedFromGeneratedAt": prior["generatedAt"]}}
    assert P.validate(latest) == []
    assert not [r for r in _receipts(paths[2]) if r["region"] == "KR" and r["asOfDate"] > "2026-10-20"]
    status = _latest(paths[3])
    assert status["status"] == "PUBLISHED" and status["deferredRegions"] == latest["deferredRegions"]
    assert '"deferred": "SESSION_NOT_FINAL"' in capsys.readouterr().out


def test_every_region_unfinished_re_emits_the_publication_byte_for_byte(tmp_path, monkeypatch):
    ledger, paths = _ledger(tmp_path, _at(SATURDAY, kr="2026-10-16", us="2026-10-16"))
    monkeypatch.setattr(P, "unfinished_sessions", lambda site: {"KR": "2026-10-21", "US": "2026-10-21"})
    assert _run(tmp_path, _at("2026-10-21T04:54:14Z", kr="2026-10-21", us="2026-10-21"), paths) == 0
    for name, written in (("latest.json", paths[1]), ("receipts.jsonl", paths[2]),
                          ("publication-status.json", paths[3])):
        assert written.read_bytes() == (ledger / name).read_bytes()


def test_evening_run_publishes_both_regions_from_finished_sessions(tmp_path):
    ledger, paths = _ledger(tmp_path, _at(SATURDAY, kr="2026-10-16", us="2026-10-16"))
    site = _at("2026-10-21T09:20:00Z", kr="2026-10-21", us="2026-10-20")  # 18:20 KST, after finality
    assert P.unfinished_sessions(site) == {}
    assert _run(tmp_path, site, paths) == 0
    latest = _latest(paths[1])
    assert "deferredRegions" not in latest
    assert {r: b["asOfDate"] for r, b in latest["regions"].items()} == {"KR": "2026-10-21", "US": "2026-10-20"}


def test_evening_run_delayed_into_the_nyse_session_still_publishes_kr(tmp_path):
    ledger, paths = _ledger(tmp_path, _at(EVENING, kr="2026-10-20", us="2026-10-19"))
    prior = _latest(ledger / "latest.json")
    site = _at("2026-10-21T15:00:00Z", kr="2026-10-21", us="2026-10-21")  # 11:00 New York
    assert _run(tmp_path, site, paths) == 0
    latest = _latest(paths[1])
    kr = latest["regions"]["KR"]
    assert kr["asOfDate"] == kr["freshness"]["observedSession"] == "2026-10-21"
    assert latest["regions"]["US"] == prior["regions"]["US"]
    assert set(latest["deferredRegions"]) == {"US"}
    assert not [r for r in _receipts(paths[2]) if r["region"] == "US" and r["asOfDate"] > "2026-10-19"]


def test_a_weekend_final_is_carried_through_the_week_and_never_beyond_a_cycle(tmp_path):
    ledger, paths = _ledger(tmp_path, _at(SATURDAY, kr="2026-10-16", us="2026-10-16"))
    chain = paths[:1] + [ledger / "latest.json", ledger / "receipts.jsonl", ledger / "publication-status.json"]
    final = _latest(ledger / "latest.json")
    # Every weekday run lands inside the KRX session: KR keeps Friday's FINAL, US publishes.
    for day, us in (("19", "16"), ("20", "19"), ("21", "20"), ("22", "21"), ("23", "22")):
        assert _run(tmp_path, _at(f"2026-10-{day}T04:40:00Z", kr=f"2026-10-{day}", us=f"2026-10-{us}"), chain) == 0
        latest = _latest(ledger / "latest.json")
        assert latest["regions"]["KR"] == final["regions"]["KR"]
        assert latest["deferredRegions"]["KR"]["carriedFromGeneratedAt"] == final["generatedAt"]
        assert latest["regions"]["US"]["asOfDate"] == f"2026-10-{us}"
    # If the weekend publication then fails, the block is refused once it is older than a cycle.
    assert _run(tmp_path, _at("2026-10-26T04:40:00Z", kr="2026-10-26", us="2026-10-23"), paths) == 0
    latest = _latest(paths[1])
    assert latest["regions"]["KR"]["status"] == "SOURCE_INCOMPLETE"
    assert "deferredRegions" not in latest and P.validate(latest) == []


def test_research_namespace_waits_for_a_build_with_no_session_in_progress(tmp_path, monkeypatch):
    from pipeline import current_champion_decisions as C
    calls = []
    monkeypatch.setattr(C, "publish", lambda *a, **k: calls.append(a))
    weekly = tmp_path / "ledger" / "weekly-decisions"
    weekly.mkdir(parents=True)
    paths = [weekly / "receipts.jsonl", weekly / "latest.json", weekly / "receipts.jsonl",
             weekly / "publication-status.json"]
    assert _run(tmp_path, _at(SATURDAY, kr="2026-10-16", us="2026-10-16"), paths) == 0
    assert len(calls) == 1
    assert _run(tmp_path, _at("2026-10-21T04:54:14Z", kr="2026-10-21"), paths) == 0
    assert len(calls) == 1
    assert _run(tmp_path, _at("2026-10-21T09:20:00Z", kr="2026-10-21"), paths) == 0
    assert len(calls) == 2


@pytest.mark.parametrize("generated,kr,status,week", [
    ("2026-10-21T09:00:00Z", "2026-10-21", "FRESH", "INTRA_WEEK_PREVIEW"),  # 18:00 KST finality
    ("2026-10-21T11:30:00Z", "2026-10-21", "FRESH", "INTRA_WEEK_PREVIEW"),  # delayed past finality
    ("2026-10-21T00:10:00Z", "2026-10-20", "FRESH", "INTRA_WEEK_PREVIEW"),  # on time, no new row yet
])
def test_completed_session_runs_publish_normally(tmp_path, generated, kr, status, week):
    site = _at(generated, kr=kr)
    assert P.unfinished_sessions(site) == {}
    ledger, paths = _ledger(tmp_path, _at(SATURDAY, kr="2026-10-16", us="2026-10-16"))
    assert _run(tmp_path, site, paths) == 0
    blob = json.loads(paths[1].read_text())["regions"]["KR"]
    assert blob["freshness"]["status"] == status and blob["weekStatus"] == week
    assert blob["asOfDate"] == blob["freshness"]["expectedSession"] == kr
    assert json.loads(paths[3].read_text())["siteGeneratedAt"] == generated


@pytest.mark.parametrize("generated", ["2026-10-21T00:10:00Z", "2026-10-21T08:59:59Z"])
def test_any_build_between_open_and_finality_waits(generated):
    assert P.unfinished_sessions(_at(generated, kr="2026-10-21")) == {"KR": "2026-10-21"}


def test_friday_intraday_build_cannot_write_a_premature_final(tmp_path):
    ledger, paths = _ledger(tmp_path, _at(SATURDAY, kr="2026-10-16", us="2026-10-16"))
    chain = paths[:1] + [ledger / "latest.json", ledger / "receipts.jsonl", ledger / "publication-status.json"]
    assert _run(tmp_path, _at("2026-10-23T04:44:48Z", kr="2026-10-23", us="2026-10-22"), chain) == 0
    assert not [r for r in _receipts(ledger / "receipts.jsonl")
                if r["region"] == "KR" and r["asOfDate"] == "2026-10-23"]
    # A run after 18:00 KST (manual dispatch or a delayed start) records the KR FINAL; Saturday's does not duplicate it.
    assert _run(tmp_path, _at("2026-10-23T09:20:00Z", kr="2026-10-23", us="2026-10-22"), chain) == 0
    saturday = _at("2026-10-24T04:35:00Z", kr="2026-10-23", us="2026-10-23")
    assert _run(tmp_path, saturday, paths) == 0
    finals = _receipts(paths[2])
    for region in ("KR", "US"):
        rows = [r for r in finals if r["region"] == region and r["asOfDate"] == "2026-10-23"]
        assert len(rows) == 1 and rows[0]["weekStatus"] == "FINAL_WEEKLY"
        assert W.receipt_session_error(rows[0]) is None


def test_holiday_run_publishes_and_holiday_dated_row_is_not_a_session(tmp_path):
    # Hangul Day (Friday 2026-10-09): Thursday is the week-end session.
    site = _at("2026-10-09T04:54:00Z", kr="2026-10-08", us="2026-10-08")
    assert P.unfinished_sessions(site) == {}
    blob = P.build_from_site(site, "sha", [])["regions"]["KR"]
    assert blob["asOfDate"] == "2026-10-08" and blob["weekStatus"] == "FINAL_WEEKLY"
    labelled = _at("2026-10-09T04:54:00Z", kr="2026-10-09", us="2026-10-08")
    assert P.unfinished_sessions(labelled) == {}
    assert P.build_from_site(labelled, "sha", [])["regions"]["KR"]["status"] == "SOURCE_INCOMPLETE"


@pytest.mark.parametrize("generated,kr", [
    ("2026-10-21T04:54:14Z", "2026-10-22"),   # future-dated row
    ("2026-10-20T23:30:00Z", "2026-10-21"),   # 08:30 KST: today's row before the open
])
def test_rows_that_are_not_a_session_in_progress_still_refuse(tmp_path, generated, kr):
    site = _at(generated, kr=kr)
    assert P.unfinished_sessions(site) == {}
    ledger, paths = _ledger(tmp_path, _at(SATURDAY, kr="2026-10-16", us="2026-10-16"))
    assert _run(tmp_path, site, paths) == 0
    blob = json.loads(paths[1].read_text())["regions"]["KR"]
    assert blob["status"] == "SOURCE_INCOMPLETE" and blob["freshness"]["status"] == "INVALID"
    assert not blob["weights"] and "receiptId" not in blob


def test_without_a_previous_publication_the_refusal_path_is_unchanged(tmp_path):
    site = tmp_path / "site.json"
    site.write_text(json.dumps(_at("2026-10-21T04:54:14Z", kr="2026-10-21")))
    out = tmp_path / "out"
    assert P.main([str(site), str(out / "r.jsonl"), str(out / "latest.json"), str(out / "r.jsonl"),
                   str(out / "status.json")]) == 0
    assert json.loads((out / "latest.json").read_text())["regions"]["KR"]["status"] == "SOURCE_INCOMPLETE"


def test_us_session_in_progress_is_deferred_too():
    site = _at("2026-10-21T15:00:00Z", kr="2026-10-21", us="2026-10-21")  # 11:00 New York
    assert P.unfinished_sessions(site) == {"US": "2026-10-21"}
