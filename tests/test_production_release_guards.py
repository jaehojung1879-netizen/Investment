"""Release regressions on invented inputs; no vendor or historical study."""
import json

import pytest

from pipeline import entry_state_shadow_ledger as L
from pipeline import daily_decision_report as R
from tests.test_entry_state_shadow_ledger import observation, SUNDAY
from tests.test_entry_state_shadow_restart import MONDAY
from tests.test_daily_decision_practical import docs, final_receipt
from tests.test_daily_decision_report import build


@pytest.mark.parametrize("field,value", [("digest", "0" * 64), ("executionSession", "2026-10-30")])
def test_bad_persisted_receipt_is_refused_before_any_accounting(tmp_path, field, value):
    receipts = L.decision_receipts(observation(), recorded_at=SUNDAY, code={}, observation_sha256="synthetic")
    L.append_decisions(tmp_path, receipts)
    receipts[0][field] = value
    path = tmp_path / "decisions.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in receipts))
    before = path.read_bytes()
    with pytest.raises(ValueError, match="INVALID_STORED_DECISION"):
        L.append_decisions(tmp_path, receipts)
    with pytest.raises(ValueError, match="INVALID_STORED_DECISION"):
        L.advance(tmp_path, now=MONDAY, close_of=lambda *_: 100.0)
    assert path.read_bytes() == before
    assert not (tmp_path / "fills.jsonl").exists()
    assert not (tmp_path / "nav-daily.jsonl").exists()


def test_valid_final_receipt_cannot_back_a_different_passive_summary():
    source = docs()
    source[R.WEEKLY + "receipts.jsonl"][0] = final_receipt(
        "KR", status="STOCKS_SELECTED", stockCount=1, holdings=[{"ticker": "SYN.KS"}], benchmarkWeightPct=70)
    stance = build(source)["regions"]["KR"]["currentStance"]
    assert not stance["displayed"] and stance["reason"] == "FINAL_RECEIPT_SUMMARY_MISMATCH"


def test_final_weekly_survives_a_daily_preview():
    source = docs()
    source[R.WEEKLY + "latest.json"]["regions"]["KR"].update(
        weekStatus="INTRA_WEEK_PREVIEW", asOfDate="2026-11-02", generatedAt="2026-11-02T10:00:00Z")
    stance = build(source, now="2026-11-02T12:00:00Z")["regions"]["KR"]["currentStance"]
    assert stance["displayed"] and stance["benchmarkWeightPct"] == 100


def test_future_nav_inside_an_old_status_stays_unknown():
    source = docs()
    source[R.SHADOW] = {"schema": "ENTRY_STATE_SHADOW_STATUS_V1", "studyId": L.STUDY,
        "productionEffect": "NONE", "atUtc": "2026-10-31T01:00:00Z", "status": "OK",
        "report": {"readout": {"evidenceClass": L.EVIDENCE_CLASS, "strategies": {
            "KR:CURRENT_POLICY": {"nav": 9, "navDate": "2099-01-02", "excessVsEtfPct": 800,
                                  "etfBaseDate": "2099-01-01"}}}}}
    row = next(x for x in build(source)["trackedPath"]["rows"] if x["strategyId"] == "KR:CURRENT_POLICY")
    assert row["status"] == "INVALID_STORED_DATES"
    assert row["nav"] is None and row["excessVsEtfPct"] is None


def test_missing_fill_cost_is_refused_without_appending_a_new_mark(tmp_path):
    receipts = L.decision_receipts(observation(), recorded_at=SUNDAY, code={}, observation_sha256="synthetic")
    L.append_decisions(tmp_path, receipts)
    L.advance(tmp_path, now=MONDAY, close_of=lambda *_: 100.0)
    fills = tmp_path / "fills.jsonl"
    stored = [json.loads(s) for s in fills.read_text().splitlines()]
    del stored[0]["costFraction"]
    fills.write_text("".join(json.dumps(r) + "\n" for r in stored))
    before = (tmp_path / "nav-daily.jsonl").read_bytes()
    with pytest.raises(ValueError, match="INVALID_STORED_FILL_COST"):
        L.advance(tmp_path, now=MONDAY.replace(day=3), close_of=lambda *_: 100.0)
    assert (tmp_path / "nav-daily.jsonl").read_bytes() == before
