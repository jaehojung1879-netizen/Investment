"""Current stance and tracked-path sections of the daily brief. Invented sources only; nothing is fetched or recomputed."""
from copy import deepcopy
from datetime import datetime, timezone
import json

import pytest

from pipeline import daily_decision_delta as D
from pipeline import daily_decision_report as R
from pipeline import entry_state_shadow_ledger as SH
from pipeline import weekly_decision as W
from tests.test_daily_decision_report import MemorySnapshot, build
from tests.test_entry_state_excess_rebase import _ledger

NOW = "2026-10-31T03:00:00+00:00"           # Saturday: both regions' last completed session is Friday 2026-10-30


def decision(region, **over):
    row = {"region": region, "status": "PASSIVE_NO_DEFENSIBLE_EDGE", "weekStatus": "FINAL_WEEKLY",
           "generatedAt": "2026-10-31T01:00:00+00:00", "asOfDate": "2026-10-30", "stockCount": 0, "holdings": [],
           "benchmark": W.BENCHMARKS[region], "benchmarkWeightPct": 100.0, "statusKo": "지수 100%",
           "freshness": {"status": "FRESH", "sourceDate": "2026-10-30"}, "watchlist": []}
    row.update(over)
    return row


def final_receipt(region, **over):
    row = decision(region, policyVersion=W.POLICY_VERSION, **over)
    row["digest"] = W.receipt_digest(row)
    return row


def docs(blocked=False, **region_over):
    d = {R.WEEKLY + "latest.json": {"blocked": blocked, "regions": {r: decision(r, **region_over) for r in ("KR", "US")}}}
    d[R.WEEKLY + "receipts.jsonl"] = [final_receipt(r) for r in ("KR", "US")]
    return d


def test_final_passive_decision_shows_zero_stocks_and_full_etf():
    r = build(docs())
    for region, etf in (("KR", "069500.KS"), ("US", "SPY")):
        c = r["regions"][region]["currentStance"]
        assert c == {"displayed": True, "stockCount": 0, "benchmarkWeightPct": 100.0, "holdings": [],
                     "statusKo": "지수 100%", "reason": "STORED_FINAL_DECISION_IS_THE_ETF_DEFAULT"}
    out = R.render(r)
    assert "|KR|0개|069500.KS 100%|없음|" in out
    assert "|US|0개|SPY 100% (QQQ는 보조 비교만)|없음|" in out


def test_without_a_digest_valid_final_receipt_the_stance_is_unknown_not_zero():
    d = docs()
    del d[R.WEEKLY + "receipts.jsonl"]
    c = build(d)["regions"]["KR"]["currentStance"]
    assert c["displayed"] is False and c["stockCount"] is None and c["benchmarkWeightPct"] is None
    assert c["reason"] == "NO_DIGEST_VALID_FINAL_RECEIPT_FOR_THIS_DECISION"
    assert "|KR|UNKNOWN|UNKNOWN|UNKNOWN|NO_DIGEST_VALID_FINAL_RECEIPT_FOR_THIS_DECISION|" in R.render(build(d))


def test_tampered_receipt_digest_does_not_back_the_decision():
    d = docs()
    d[R.WEEKLY + "receipts.jsonl"][0]["digest"] = "0" * 64
    assert build(d)["regions"]["KR"]["currentStance"]["reason"] == "NO_DIGEST_VALID_FINAL_RECEIPT_FOR_THIS_DECISION"
    assert build(d)["regions"]["US"]["currentStance"]["displayed"] is True


def test_a_decision_goes_unknown_once_a_newer_week_end_has_completed_without_a_new_decision():
    c = build(docs(), now="2026-11-09T03:00:00+00:00")["regions"]["KR"]["currentStance"]
    assert c["displayed"] is False and c["reason"] == "NOT_THE_LATEST_COMPLETED_WEEK_END_DECISION"


@pytest.mark.parametrize("now", ["2026-11-02T10:00:00+00:00",    # Monday, after KR's close
                                 "2026-11-04T03:00:00+00:00",    # Wednesday
                                 "2026-11-05T13:00:00+00:00"])   # Thursday, after KR's close
def test_the_friday_decision_holds_for_the_whole_following_week(now):
    r = build(docs(), now=now)
    assert r["regions"]["KR"]["freshnessAtReport"]["status"] == "STALE"        # the session freshness view is unchanged
    for region in ("KR", "US"):
        c = r["regions"][region]["currentStance"]
        assert c["displayed"] is True and c["stockCount"] == 0 and c["benchmarkWeightPct"] == 100.0


def test_each_region_goes_unknown_when_its_own_week_end_closes_without_a_new_decision():
    # Friday 2026-11-06 21:00 KST: KR's week-end has closed, US's (21:00 UTC close) has not.
    r = build(docs(), now="2026-11-06T12:00:00+00:00")
    assert r["regions"]["KR"]["currentStance"]["displayed"] is False
    assert r["regions"]["KR"]["currentStance"]["reason"] == "NOT_THE_LATEST_COMPLETED_WEEK_END_DECISION"
    assert r["regions"]["US"]["currentStance"]["displayed"] is True


@pytest.mark.parametrize("over,reason", [
    ({"stockCount": 2}, "PASSIVE_STATUS_FIELDS_INCONSISTENT"),
    ({"benchmarkWeightPct": 60.0}, "PASSIVE_STATUS_FIELDS_INCONSISTENT"),
    ({"holdings": [{"ticker": "AAA"}]}, "PASSIVE_STATUS_FIELDS_INCONSISTENT"),
    ({"stockCount": True}, "PASSIVE_STATUS_FIELDS_INCONSISTENT"),
    ({"benchmark": "SPY"}, "PASSIVE_STATUS_FIELDS_INCONSISTENT"),
    ({"status": "SOMETHING_ELSE"}, "POLICY_STATUS_UNRECOGNIZED"),
    ({"weekStatus": "INTRA_WEEK_PREVIEW"}, "NOT_A_FINAL_WEEKLY_DECISION"),
    ({"generatedAt": "2026-11-05T00:00:00+00:00"}, "POLICY_TIMESTAMP_MISSING_OR_AFTER_REPORT"),
])
def test_stored_fields_that_disagree_never_become_a_displayed_position(over, reason):
    region = {"KR": decision("KR", **over)}
    d = docs()
    d[R.WEEKLY + "latest.json"] = {"regions": region}
    c = build(d)["regions"]["KR"]["currentStance"]
    assert c["displayed"] is False and c["reason"] == reason and c["stockCount"] is None


def test_a_blocked_weekly_publication_displays_nothing():
    assert build(docs(blocked=True))["regions"]["KR"]["currentStance"]["reason"] == "WEEKLY_PUBLICATION_BLOCKED"


def test_a_stock_selection_is_never_displayed_without_an_admission_registry():
    held = [{"ticker": "AAA", "weightPct": 30.0}, {"ticker": "BBB", "weightPct": 20.0}]
    d = docs(status="STOCKS_SELECTED", stockCount=2, holdings=held, benchmarkWeightPct=50.0)
    d[R.WEEKLY + "receipts.jsonl"] = [final_receipt(r, status="STOCKS_SELECTED", stockCount=2, holdings=held,
                                                    benchmarkWeightPct=50.0) for r in ("KR", "US")]
    r = build(d)
    c = r["regions"]["KR"]["currentStance"]
    assert c["displayed"] is False and c["reason"].startswith("STOCK_SELECTION_NOT_DISPLAYED")
    assert c["stockCount"] is None and c["holdings"] is None
    out = R.render(r)
    assert "AAA" not in out and "BBB" not in out and "AAA" not in json.dumps(r)


# ---------------------------------------------------------------------------------------------------------------- tracked path
def stored_status(tmp_path, **over):
    readout = _ledger(tmp_path)
    full = SH.status_report(tmp_path, now=datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc))
    doc = {"schema": "ENTRY_STATE_SHADOW_STATUS_V1", "studyId": SH.STUDY, "productionEffect": "NONE",
           "atUtc": "2026-11-10T12:00:00Z", "status": "OK", "report": {"readout": full}}
    assert readout  # the ledger produced strategies
    doc.update(over)
    return doc


LATER = "2026-11-10T13:00:00+00:00"


def test_missing_ledger_status_is_unknown_and_never_a_zero_return():
    r = build(docs())
    t = r["trackedPath"]
    assert t["status"] == "NOT_STARTED_NO_STORED_STATUS" and t["rows"] == [] and t["realAccountPerformance"] is None
    out = R.render(r)
    assert "검증된 실제 계좌 성과: 없음" in out and "ETF 대비 성과는 **UNKNOWN**" in out
    assert "과거 탐색 백테스트" in out and "합산하지 않습니다" in out


def test_stored_paper_path_is_shown_against_the_etf_from_its_own_start(tmp_path):
    d = docs()
    d[R.SHADOW] = stored_status(tmp_path)
    r = build(d, now=LATER)
    rows = {x["strategyId"]: x for x in r["trackedPath"]["rows"]}
    assert r["trackedPath"]["status"] == "READ"
    assert rows["KR:ETF_ONLY"]["excessVsEtfPct"] == pytest.approx(0.0, abs=1e-9)
    assert rows["KR:CURRENT_POLICY"]["etfBaseDate"] == "2026-11-02"
    assert rows["US:ETF_ONLY"]["status"] == "NOT_IN_STORED_STATUS"
    assert r["trackedPath"]["researchScenarioCount"] >= 2
    assert not any(":N" in k for k in rows)                       # research scenarios are not in the performance table
    out = R.render(r)
    assert "KR:CURRENT_POLICY" in out and "PENDING_" in out and "2026-11-02" in out
    assert "KR:N1:IN_RANK" not in out


@pytest.mark.parametrize("over,expected", [
    ({"studyId": "other"}, "INVALID_STORED_STATUS"),
    ({"productionEffect": "ORDERS"}, "INVALID_STORED_STATUS"),
    ({"atUtc": "2027-01-01T00:00:00Z"}, "INVALID_STORED_STATUS"),
    ({"status": "TIMEOUT", "reason": "CHILD_PROCESS_EXCEEDED_600_SECONDS"}, "LAST_ATTEMPT_TIMEOUT"),
])
def test_unusable_ledger_status_is_reported_as_such(tmp_path, over, expected):
    d = docs()
    d[R.SHADOW] = stored_status(tmp_path, **over)
    t = build(d, now=LATER)["trackedPath"]
    assert t["status"] == expected and t["rows"] == []


def test_non_finite_or_wrong_class_values_are_unknown_not_numbers(tmp_path):
    doc = stored_status(tmp_path)
    doc["report"]["readout"]["strategies"]["KR:CURRENT_POLICY"]["excessVsEtfPct"] = float("nan")
    doc["report"]["readout"]["strategies"]["KR:CURRENT_POLICY"]["nav"] = 0
    d = docs()
    d[R.SHADOW] = doc
    row = next(x for x in build(d, now=LATER)["trackedPath"]["rows"] if x["strategyId"] == "KR:CURRENT_POLICY")
    assert row["excessVsEtfPct"] is None and row["nav"] is None and row["navDate"] is None and row["etfBaseDate"] is None
    doc2 = stored_status(tmp_path / "again")
    doc2["report"]["readout"]["evidenceClass"] = "HISTORICAL_DEVELOPMENT"
    d[R.SHADOW] = doc2
    assert build(d, now=LATER)["trackedPath"]["status"] == "INVALID_STORED_STATUS"


def test_collections_render_as_plain_text_not_escaped_json():
    d = docs()
    d[R.WEEKLY + "latest.json"]["regions"]["KR"]["watchlist"] = [
        {"ticker": "ONE.KS", "rank": 1, "priceMomentum": {"asOf": "2026-10-30"},
         "exclusionCodes": ["ORDERING_NOT_ESTABLISHED", "ENTRY_OR_RESEARCH_STATE_BLOCKS_SIZING"]}]
    out = R.render(build(d))
    assert "ORDERING_NOT_ESTABLISHED, ENTRY_OR_RESEARCH_STATE_BLOCKS_SIZING" in out
    assert "&#91;&quot;" not in out and "&quot;" not in out
    assert R.text([]) == "없음" and R.text(None) == "UNKNOWN" and R.text({"a": [1, None]}) == "a=(1, UNKNOWN)"
    assert "[x](http://evil)" not in R.text("[x](http://evil)")        # link syntax stays neutralised


def test_render_stays_pure_and_repeatable(tmp_path):
    d = docs()
    d[R.SHADOW] = stored_status(tmp_path)
    first = R.render(build(deepcopy(d), now=LATER))
    assert first == R.render(build(deepcopy(d), now=LATER))
    assert MemorySnapshot(d).read(R.SHADOW) is not None


def test_the_daily_delta_reports_a_stance_and_tracked_path_change_without_inventing_values(tmp_path):
    d = docs()
    d[R.SHADOW] = stored_status(tmp_path)
    before = build(deepcopy(d), now="2026-11-10T13:00:00+00:00")
    d2 = deepcopy(d)
    d2[R.SHADOW]["report"]["readout"]["strategies"]["KR:CURRENT_POLICY"]["fillState"] = "STOPPED_UNRESOLVED_MISSING_PRICE"
    after = build(d2, now="2026-11-11T13:00:00+00:00")
    changes = D.compare(json.loads(json.dumps(before)), json.loads(json.dumps(after)))["changes"]
    kinds = {(c["scope"], c["key"], c["kind"]) for c in changes}
    assert ("KR:CURRENT_POLICY", "trackedPath.fillState", "TRACKED_PATH") in kinds
    # both reports are long past the weekly decision: the stance is UNKNOWN in each, so no stance change is invented
    assert not any(c["kind"] == "REGION_STANCE" for c in changes)


def test_the_daily_delta_flags_a_stance_going_from_etf_default_to_unknown():
    before = build(docs())
    after = build(docs(), now="2026-11-09T03:00:00+00:00")
    changes = D.compare(json.loads(json.dumps(before)), json.loads(json.dumps(after)))["changes"]
    moved = {c["key"]: (c["before"], c["after"]) for c in changes if c["kind"] == "REGION_STANCE" and c["scope"] == "KR"}
    assert moved["currentStance.displayed"] == (True, False)
    assert moved["currentStance.stockCount"] == (0, None) and moved["currentStance.benchmarkWeightPct"] == (100.0, None)


# ---------------------------------------------------------------------------------------------------------- materialisation
def test_materialize_reads_only_allowed_paths_at_a_pinned_commit(tmp_path):
    import subprocess
    from scripts import materialize_daily_report_sources as M

    def git(*a):
        return subprocess.run(["git", *a], cwd=tmp_path, capture_output=True, text=True, check=True).stdout.strip()
    git("init", "-q")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "t")
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "latest.json").write_text("{}")
    (tmp_path / "secret.txt").write_text("not a report source")
    git("add", "-A")
    git("commit", "-qm", "c")
    sha = git("rev-parse", "HEAD")
    out = M.materialize(sha, root=tmp_path)
    assert out["present"] == 1 and out["failed"] == [] and out["absentInCommit"] == len(R.ALLOWED) - 1
    with pytest.raises(ValueError, match="FULL_IMMUTABLE_SOURCE_SHA_REQUIRED"):
        M.materialize("HEAD", root=tmp_path)
    with pytest.raises(ValueError, match="COMMIT_NOT_AVAILABLE_LOCALLY"):
        M.materialize("0" * 40, root=tmp_path)
