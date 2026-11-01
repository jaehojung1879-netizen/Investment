"""Synthetic tests for entry-state-shadow-ledger-v1. No vendor, no real ledger."""
from __future__ import annotations

from datetime import datetime, timezone
import json

import pytest

from pipeline import entry_state_shadow_ledger as L


def observation(as_of="2026-10-30", stocks=None, residual=None):
    stocks = {"000001.KS": 0.3} if stocks is None else stocks
    residual = 0.7 if residual is None else residual
    scenario = {"stockCount": 1, "status": "SOURCE_PINNED_COUNTERFACTUAL",
                "rankStateInSelection": {"selected": list(stocks), "stocks": stocks, "residual": residual,
                                         "candidateAudit": [{"ticker": "000001.KS", "status": "SELECTED"}]},
                "stateAtPositionWeight": {"selected": list(stocks), "stocks": {k: v / 2 for k, v in stocks.items()},
                                          "residual": 1 - sum(stocks.values()) / 2, "candidateAudit": []}}
    blocked = {"stockCount": 10, "status": "INSUFFICIENT_ELIGIBLE_NAMES", "rankStateInSelection": None,
               "stateAtPositionWeight": None}
    return {"sourceCommit": "a" * 40, "regions": {"KR": {
        "status": "RESEARCH_SNAPSHOT_ONLY_NOT_LIVE_VALIDATED", "asOfDate": as_of,
        "currentPolicy": {"status": "PASSIVE_NO_DEFENSIBLE_EDGE"},
        "legacyControlOnly": {"selected": ["000001.KS"], "stocks": stocks, "residual": residual,
                              "sameAsPublished": True},
        "researchScenarios": [scenario, blocked]}}}


SUNDAY = datetime(2026, 11, 1, 3, 0, tzinfo=timezone.utc)      # Sunday 12:00 KST


def test_execution_session_is_after_recording_never_before():
    assert L.execution_session("KR", "2026-10-30", SUNDAY) == "2026-11-02"
    # recorded Monday 10:00 KST, after Monday's open: Monday is not usable, Tuesday is
    assert L.execution_session("KR", "2026-10-30", datetime(2026, 11, 2, 1, 0, tzinfo=timezone.utc)) == "2026-11-03"


def test_receipt_before_signal_session_final_is_refused():
    with pytest.raises(ValueError, match="RECORDED_BEFORE_SIGNAL_SESSION_FINAL"):
        L.decision_receipts(observation(), recorded_at=datetime(2026, 10, 30, 6, 0, tzinfo=timezone.utc),
                            code={}, observation_sha256="x")


def test_receipts_are_write_once_and_conflicts_refused(tmp_path):
    receipts = L.decision_receipts(observation(), recorded_at=SUNDAY, code={"commit": "c"}, observation_sha256="x")
    ids = {r["strategyId"] for r in receipts}
    assert {"KR:ETF_ONLY", "KR:CURRENT_POLICY", "KR:LEGACY_CONTROL_MAXREGION3", "KR:N1:IN_RANK",
            "KR:N1:AT_WEIGHT", "KR:N10:IN_RANK"} <= ids
    first = L.append_decisions(tmp_path, receipts)
    assert first["appended"] == len(receipts)
    before = (tmp_path / "decisions.jsonl").read_bytes()
    again = L.append_decisions(tmp_path, L.decision_receipts(observation(), recorded_at=SUNDAY.replace(hour=4),
                                                             code={"commit": "c"}, observation_sha256="x"))
    assert again["appended"] == 0 and again["alreadyPresent"] == len(receipts)
    changed = L.decision_receipts(observation(stocks={"000002.KS": 0.3}), recorded_at=SUNDAY, code={"commit": "c"},
                                  observation_sha256="x")
    report = L.append_decisions(tmp_path, changed)
    assert report["conflictsRefused"] and (tmp_path / "decisions.jsonl").read_bytes() == before
    blocked = next(r for r in receipts if r["strategyId"] == "KR:N10:IN_RANK")
    assert blocked["targetWeights"] is None and blocked["action"] == "HOLD_PREVIOUS_BOOK_NO_TRADE"


PRICES = {"2026-11-02": {"069500.KS": 100.0, "000001.KS": 50.0},
          "2026-11-03": {"069500.KS": 101.0, "000001.KS": 55.0},
          "2026-11-04": {"069500.KS": 102.0, "000001.KS": 50.0}}


def close_of(ticker, session):
    return PRICES.get(session, {}).get(ticker)


def test_fill_is_carried_cost_once_and_marked(tmp_path):
    L.append_decisions(tmp_path, L.decision_receipts(observation(), recorded_at=SUNDAY, code={},
                                                     observation_sha256="x"))
    now = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)
    report = L.advance(tmp_path, now=now, close_of=close_of, through="2026-11-04")
    fills = [json.loads(s) for s in (tmp_path / "fills.jsonl").read_text().splitlines()]
    navs = [json.loads(s) for s in (tmp_path / "nav-daily.jsonl").read_text().splitlines()]
    rank = next(f for f in fills if f["strategyId"] == "KR:N1:IN_RANK")
    assert rank["session"] == "2026-11-02" and rank["firstEntry"] == ["000001.KS"]
    assert {(leg["ticker"], leg["instrument"]) for leg in rank["legs"]} == {("069500.KS", "ETF"), ("000001.KS", "STOCK")}
    assert rank["postTradeNav"] == pytest.approx(1 - rank["costFraction"])
    series = [n for n in navs if n["strategyId"] == "KR:N1:IN_RANK"]
    assert [n["date"] for n in series] == ["2026-11-02", "2026-11-03", "2026-11-04"]
    expected = rank["postTradeNav"] * (0.3 * 55 / 50 + 0.7 * 101 / 100)
    assert series[1]["nav"] == pytest.approx(expected)          # NAV carried, never reset, cost not charged again
    etf = [n for n in navs if n["strategyId"] == "KR:ETF_ONLY"]
    assert etf[0]["nav"] == pytest.approx(1.0) and etf[1]["nav"] == pytest.approx(1.01)
    assert not [f for f in fills if f["strategyId"] == "KR:N10:IN_RANK"]
    # a second run on the same clock appends nothing
    assert L.advance(tmp_path, now=now, close_of=close_of, through="2026-11-04")["navRowsAppended"] == 0
    assert report["fillsAppended"] >= 4


def test_second_decision_separates_retained_and_replaced(tmp_path):
    L.append_decisions(tmp_path, L.decision_receipts(observation(), recorded_at=SUNDAY, code={},
                                                     observation_sha256="x"))
    L.advance(tmp_path, now=datetime(2026, 11, 2, 12, tzinfo=timezone.utc), close_of=close_of, through="2026-11-02")
    second = observation(as_of="2026-11-02", stocks={"000001.KS": 0.2, "000002.KS": 0.2}, residual=0.6)
    PRICES["2026-11-03"]["000002.KS"] = 20.0
    PRICES["2026-11-04"]["000002.KS"] = 21.0
    L.append_decisions(tmp_path, L.decision_receipts(second, recorded_at=datetime(2026, 11, 2, 12, tzinfo=timezone.utc),
                                                     code={}, observation_sha256="y"))
    L.advance(tmp_path, now=datetime(2026, 11, 4, 12, tzinfo=timezone.utc), close_of=close_of, through="2026-11-04")
    fills = [json.loads(s) for s in (tmp_path / "fills.jsonl").read_text().splitlines()]
    later = [f for f in fills if f["strategyId"] == "KR:N1:IN_RANK"][1]
    assert later["session"] == "2026-11-03"
    assert later["retained"] == ["000001.KS"] and later["firstEntry"] == ["000002.KS"]
    assert later["retargeted"] == ["000001.KS"]


def test_missing_price_stops_the_path_instead_of_filling(tmp_path):
    L.append_decisions(tmp_path, L.decision_receipts(observation(), recorded_at=SUNDAY, code={},
                                                     observation_sha256="x"))
    gap = {"2026-11-02": {"069500.KS": 100.0, "000001.KS": 50.0}, "2026-11-03": {"069500.KS": 101.0}}
    L.advance(tmp_path, now=datetime(2026, 11, 4, 12, tzinfo=timezone.utc),
              close_of=lambda t, s: gap.get(s, {}).get(t), through="2026-11-04")
    navs = [json.loads(s) for s in (tmp_path / "nav-daily.jsonl").read_text().splitlines()]
    rank = [n for n in navs if n["strategyId"] == "KR:N1:IN_RANK"]
    assert rank[-1]["status"] == "UNRESOLVED_MISSING_PRICE" and rank[-1]["nav"] is None
    assert rank[-1]["missing"] == ["000001.KS"]
    again = L.advance(tmp_path, now=datetime(2026, 11, 5, 12, tzinfo=timezone.utc), close_of=close_of)
    assert again["strategies"]["KR:N1:IN_RANK"] == "STOPPED_UNRESOLVED"


def test_unfinal_session_is_not_marked_and_maturity_is_pending(tmp_path):
    L.append_decisions(tmp_path, L.decision_receipts(observation(), recorded_at=SUNDAY, code={},
                                                     observation_sha256="x"))
    # Monday 15:00 KST: market closed but the session is not final until 18:00 KST
    report = L.advance(tmp_path, now=datetime(2026, 11, 2, 6, 0, tzinfo=timezone.utc), close_of=close_of)
    assert report["navRowsAppended"] == 0 and report["fillsAppended"] == 0
    L.advance(tmp_path, now=datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc), close_of=close_of)
    state = L.maturity(tmp_path, now=datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc))["strategies"]
    assert state["KR:N1:AT_WEIGHT"]["H126"] == "PENDING_126_SESSIONS"
