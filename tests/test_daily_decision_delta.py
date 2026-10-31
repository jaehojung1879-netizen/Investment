"""Daily delta contracts: never make evidence from absent or stale data."""
from copy import deepcopy

import pytest

from pipeline.daily_decision_delta import compare


def report(day, source, date):
    studies = {
        "kr-selection-challenger-v1": {
            "recordedReceipts": None, "maturedRecordedOutcomes": None,
            "eligibleCounts": None, "aggregateStatus": None,
            "errors": [], "latestRecordAttempt": None, "latestReceipt": None,
        },
    }
    return {
        "schema": "READ_ONLY_DAILY_DECISION_REPORT_V1",
        "reportAsOfUtc": day,
        "sourceCommitSha": source,
        "sourceCommitTimestamp": date,
        "regions": {
            region: {
                "observedSession": "2026-10-23", "lastValidFinalSession": "2026-10-23",
                "persistedWeekStatus": "FINAL_WEEKLY", "persistedPolicyStatus": "PASSIVE_NO_DEFENSIBLE_EDGE",
                "freshnessAtReport": {
                    "status": "STALE", "expectedSession": "2026-10-30", "sourceDate": "2026-10-23"},
                "newNominationsInThisReport": 0, "evidenceCertifiedCandidateCount": None,
                "certificationReason": "NO_INVESTMENT_ADMISSION_REGISTRY_IN_THESE_SOURCES",
            } for region in ("KR", "US")
        },
        "paperStudies": studies,
        "sources": {"a.json": {"status": "READ"}, "missing.json": {"status": "MISSING"}},
        "safety": {"readOnly": True, "historicalOutcomesExecuted": False, "productionEffect": "NONE"},
    }


EARLIER = "2026-10-31T00:00:00+00:00"
LATER = "2026-11-01T00:00:00+00:00"
COMMIT = "a" * 40


def pair():
    return report(EARLIER, COMMIT, "2026-10-30T12:00:00+00:00"), report(
        LATER, "b" * 40, "2026-10-31T12:00:00+00:00")


def test_no_field_changes_are_not_fabricated_signals():
    a, b = pair()
    b["sourceCommitSha"] = COMMIT
    result = compare(a, b)
    assert result["status"] == "NO_TRACKED_FIELD_CHANGE"
    assert not result["changes"]
    assert not result["safety"]["investmentRecommendation"]


def test_freshness_rollover_does_not_invent_new_market_observation():
    a, b = pair()
    b["sourceCommitSha"] = COMMIT
    b["regions"]["KR"]["freshnessAtReport"]["expectedSession"] = "2026-10-31"
    delta = compare(a, b)
    assert delta["changes"] == [{
        "scope": "KR", "key": "freshnessAtReport.expectedSession", "kind": "REGION_FRESHNESS",
        "before": "2026-10-30", "after": "2026-10-31",
    }]
    assert not delta["safety"]["signalsGenerated"]


def test_unknown_to_zero_is_not_new_signal_or_alpha():
    a, b = pair()
    b["paperStudies"]["kr-selection-challenger-v1"]["recordedReceipts"] = 0
    b["paperStudies"]["kr-selection-challenger-v1"]["maturedRecordedOutcomes"] = 0
    b["paperStudies"]["kr-selection-challenger-v1"]["latestRecordAttempt"] = {
        "status": "SKIPPED", "reason": "ARTIFACT_NOT_BUILT_ON_A_FINAL_SESSION", "runId": "123"}
    changes = compare(a, b)["changes"]
    count = next(v for v in changes if v["key"] == "recordedReceipts")
    assert count["before"] is None and count["after"] == 0
    assert any(v["key"] == "latestRecordAttempt.reason" and v["after"].startswith("ARTIFACT") for v in changes)
    assert not any(v["kind"] == "VALIDATED_ALPHA" for v in changes)


def test_real_record_count_change_reports_only_recorded_field_change():
    a, b = pair()
    a["paperStudies"]["kr-selection-challenger-v1"]["recordedReceipts"] = 0
    b["paperStudies"]["kr-selection-challenger-v1"]["recordedReceipts"] = 1
    b["paperStudies"]["kr-selection-challenger-v1"]["latestReceipt"] = {"receiptSha256": "f" * 64}
    delta = compare(a, b)
    assert any(c["key"] == "recordedReceipts" and c["before"] == 0 and c["after"] == 1 for c in delta["changes"])
    assert any(c["kind"] == "PAPER_RECEIPT_ID" for c in delta["changes"])
    assert delta["comparisonAuthority"] == "UNVERIFIED_INPUT_REPORTS_NOT_SOURCE_REATTESTATION"
    assert not delta["safety"]["researchEvidenceAdmitted"]


def test_source_path_counts_and_commit_independently_change():
    a, b = pair()
    b["sources"]["missing.json"]["status"] = "READ"
    changes = compare(a, b)["changes"]
    assert any(c["kind"] == "SOURCE_READ_STATUS" and c["after"]["MISSING"] == 0 for c in changes)
    assert any(c["kind"] == "SOURCE_COMMIT_ID" for c in changes)


@pytest.mark.parametrize("fault", ["old_time", "same_time", "new_time", "naive", "future_commit",
                                  "source_sha", "admission", "not_read_only", "outcome", "negative_receipts"])
def test_invalid_or_unapproved_report_pair_rejected(fault):
    a, b = pair()
    if fault == "old_time":
        b["reportAsOfUtc"] = "2026-10-30T00:00:00+00:00"
    elif fault == "same_time":
        b["reportAsOfUtc"] = a["reportAsOfUtc"]
    elif fault == "new_time":
        b["reportAsOfUtc"] = None
    elif fault == "naive":
        b["reportAsOfUtc"] = "2026-11-01T00:00:00"
    elif fault == "future_commit":
        b["sourceCommitTimestamp"] = "2027-11-01T00:00:00+00:00"
    elif fault == "source_sha":
        b["sourceCommitSha"] = "relative-head"
    elif fault == "admission":
        b["regions"]["KR"]["evidenceCertifiedCandidateCount"] = 1
    elif fault == "not_read_only":
        b["safety"]["readOnly"] = False
    elif fault == "outcome":
        b["safety"]["historicalOutcomesExecuted"] = True
    elif fault == "negative_receipts":
        b["paperStudies"]["kr-selection-challenger-v1"]["recordedReceipts"] = -1
    with pytest.raises(ValueError):
        compare(a, b)


def test_reports_not_mutated():
    a, b = pair()
    old_a, old_b = deepcopy(a), deepcopy(b)
    compare(a, b)
    assert a == old_a and b == old_b


def test_cli_from_an_unrelated_directory_without_pythonpath(tmp_path):
    import json
    from pathlib import Path
    import subprocess
    import sys

    a, b = pair()
    before, after = tmp_path / "previous.json", tmp_path / "current.json"
    before.write_text(json.dumps(a), encoding="utf-8")
    after.write_text(json.dumps(b), encoding="utf-8")
    script = Path(__file__).resolve().parents[1] / "scripts" / "compare_daily_decision_reports.py"
    run = subprocess.run([sys.executable, str(script), "--before", str(before), "--after", str(after)],
                         cwd=tmp_path, capture_output=True, text=True, check=True)
    result = json.loads(run.stdout)
    assert result["schema"] == "READ_ONLY_DAILY_DECISION_DELTA_V1"
    assert result["status"] == "REPORTED_FIELDS_CHANGED"
    assert a == json.loads(before.read_text(encoding="utf-8"))
    assert b == json.loads(after.read_text(encoding="utf-8"))
