"""weekly-passive-first-v1: 0-5 stocks per region, benchmark fallback, receipts."""
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from pipeline import weekly_decision as W

ROOT = Path(__file__).resolve().parent.parent


def _calibration(region="KR", expected=3.0, usable=True, established=True):
    buckets = []
    for lo, hi in ((0, 60), (60, 80), (80, 90), (90, 95), (95, 100)):
        buckets.append({"bucket": f"{lo}-{hi}", "usable": usable,
                        "unusableReason": None if usable else "ORDERING_NOT_ESTABLISHED",
                        "calibratedExpectedExcessReturnPct": expected,
                        "confidenceIntervalPct": [expected - 2, expected + 2],
                        "standardErrorPct": 1.0, "conservativeBasis": "ALPHA_SPREAD_VS_REPLAY_UNIVERSE",
                        "effectiveDates": 40})
    return {"available": True, "horizonDays": 126, "buckets": [0, 60, 80, 90, 95, 100],
            "regions": {region: {"buckets": buckets, "ordering": {"established": established}}}}


def _candidate(ticker, sector="Tech", region="KR", alpha=97, view="POSITIVE", state="ACCUMULATE_GRADUALLY",
               downside=20.0):
    return {"ticker": ticker, "region": region, "sector": sector, "alphaPercentile": alpha,
            "longTermResearchView": view, "evidenceCoverage": 1.0,
            "risk": {"downsideVolPct": downside}, "entry": {"entryState": state}}


def _sum(weights):
    return sum(weights.values())


def test_zero_stocks_is_one_hundred_percent_benchmark():
    cands = [_candidate(f"A{i}") for i in range(6)]
    out = W.decide("KR", cands, _calibration(usable=False, established=False), "2026-10-08")
    assert out["stockCount"] == 0 and out["holdings"] == []
    assert out["weights"] == {"069500.KS": 1.0}
    assert out["benchmarkWeightPct"] == 100.0
    assert out["status"] == "PASSIVE_NO_DEFENSIBLE_EDGE"
    assert out["noTradeReason"] == "ORDERING_NOT_ESTABLISHED"
    us = W.decide("US", [_candidate("X", region="US")], None, "2026-10-09")
    assert us["weights"] == {"SPY": 1.0}


@pytest.mark.parametrize("n", [1, 2, 3, 4])
def test_one_to_four_stocks_leave_residual_in_the_benchmark(n):
    cands = [_candidate(f"A{i}", sector=f"S{i}") for i in range(n)]
    out = W.decide("KR", cands, _calibration(), "2026-10-08")
    assert out["stockCount"] == n
    assert out["weights"]["069500.KS"] == pytest.approx(1 - 0.15 * n)
    assert _sum(out["weights"]) == pytest.approx(1.0)


def test_five_stocks_cap_and_sector_cap():
    cands = [_candidate(f"A{i}", sector="Tech") for i in range(4)] + \
            [_candidate(f"B{i}", sector=f"S{i}") for i in range(6)]
    out = W.decide("KR", cands, _calibration(), "2026-10-08")
    assert out["stockCount"] == 5
    assert sum(1 for h in out["holdings"] if h["sector"] == "Tech") <= 2
    assert all(h["weightPct"] == 15.0 for h in out["holdings"])
    assert out["benchmarkWeightPct"] == pytest.approx(25.0)
    assert _sum(out["weights"]) == pytest.approx(1.0)


def test_edge_below_switch_cost_is_not_selected():
    cost = W.cost_breakdown("KR", "2026-10-08")["switchCostPct"]
    out = W.decide("KR", [_candidate("A")], _calibration(expected=cost - 0.01), "2026-10-08")
    assert out["stockCount"] == 0
    assert "EXPECTED_NET_ADVANTAGE_NOT_POSITIVE" in out["excluded"][0]["codes"]


def test_missing_edge_is_absent_not_zero():
    out = W.decide("KR", [_candidate("A")], None, "2026-10-08")
    row = out["candidates"][0]
    assert row["expectedNetAdvantagePct"] is None and row["edgeAvailable"] is False
    assert row["edgePointEstimatePct"] is None


def test_blocking_entry_state_and_missing_risk_exclude():
    cands = [_candidate("A", state="AVOID"), _candidate("B", view="NEUTRAL"),
             {**_candidate("C"), "risk": {}}]
    out = W.decide("KR", cands, _calibration(), "2026-10-08")
    assert out["stockCount"] == 0


def test_kr_and_us_costs_are_regional_and_dated():
    kr18 = W.cost_breakdown("KR", "2018-06-01")
    kr26 = W.cost_breakdown("KR", "2026-06-01")
    us = W.cost_breakdown("US", "2026-06-01")
    assert kr18["sellTaxBps"] == 30 and kr26["sellTaxBps"] == 20
    assert us["sellTaxBps"] == pytest.approx(0.30)
    # The KR ETF leg pays no securities transaction tax; the stock leg does.
    assert kr26["benchmarkRoundTripPct"] < kr26["stockRoundTripPct"]
    assert W.trade_cost_fraction("KR", "2026-06-01", is_benchmark=True, side="sell") < \
        W.trade_cost_fraction("KR", "2026-06-01", is_benchmark=False, side="sell")


def test_region_isolation_ignores_other_region_candidates():
    cands = [_candidate("A", region="US"), _candidate("B", region="KR")]
    cal = _calibration("KR")
    out = W.decide("KR", cands, cal, "2026-10-08")
    assert [c["ticker"] for c in out["candidates"]] == ["B"]


def test_retention_credit_orders_but_never_admits():
    cost = W.cost_breakdown("KR", "2026-10-08")["switchCostPct"]
    out = W.decide("KR", [_candidate("A")], _calibration(expected=cost - 0.05), "2026-10-08",
                   incumbents={"A"})
    assert out["stockCount"] == 0


def test_decision_is_deterministic():
    cands = [_candidate(f"A{i}", sector=f"S{i}", alpha=90 + i) for i in range(7)]
    a = W.decide("KR", cands, _calibration(), "2026-10-08")
    b = W.decide("KR", list(reversed(cands)), _calibration(), "2026-10-08")
    assert a["weights"] == b["weights"] and a["holdings"] == b["holdings"]


def test_freshness_uses_each_exchange_calendar_and_time_zone():
    # Friday 2026-10-09 is Hangul Day (KRX closed); the KR week ends Thursday.
    now = datetime(2026, 10, 10, 2, 0, tzinfo=timezone.utc)
    kr = W.freshness("KR", "2026-10-09", now)
    assert kr["observedSession"] == "2026-10-08" and kr["weekEnd"] is True and kr["status"] == "FRESH"
    # 16:30 New York on Friday is before close + buffer; 17:30 is after.
    assert W.last_completed_session("US", datetime(2026, 10, 9, 20, 30, tzinfo=timezone.utc)) == "2026-10-08"
    assert W.last_completed_session("US", datetime(2026, 10, 9, 21, 30, tzinfo=timezone.utc)) == "2026-10-09"
    stale = W.freshness("US", "2026-10-08", now)
    assert stale["status"] == "STALE" and stale["reason"] == "SOURCE_NOT_UPDATED"


def test_stale_data_issues_no_new_decision_and_keeps_last_receipt():
    now = datetime(2026, 10, 10, 2, 0, tzinfo=timezone.utc)
    prior = W.build_receipt(W.decide("US", [], None, "2026-10-02"), generated_at="x", inputs={},
                            evidence=W.EVIDENCE, week_status="FINAL_WEEKLY")
    out = W.build({"regions": {}}, None, {"KR": "2026-10-08", "US": "2026-10-08"}, now=now,
                  prior_receipts=[prior])
    us = out["regions"]["US"]
    assert us["status"] == "STALE_DATA_NO_NEW_DECISION" and us["holdings"] == [] and us["weights"] == {}
    assert us["lastValidReceipt"]["asOfDate"] == "2026-10-02"
    assert out["regions"]["KR"]["asOfDate"] == "2026-10-08"


def test_blocked_build_carries_no_holdings_or_weights():
    out = W.build({"regions": {"KR": {"picks": [_candidate("A")]}}}, _calibration(),
                  {"KR": "2026-10-08", "US": "2026-10-09"}, blocked=True)
    for blob in out["regions"].values():
        assert blob["status"] == "BLOCKED" and not blob["holdings"] and not blob["weights"]


def test_receipts_are_append_only_and_never_overwritten():
    d = W.decide("KR", [], None, "2026-10-08")
    first = W.build_receipt(d, generated_at="t1", inputs={}, evidence=W.EVIDENCE, week_status="FINAL_WEEKLY")
    same = W.build_receipt(d, generated_at="t2", inputs={}, evidence=W.EVIDENCE, week_status="FINAL_WEEKLY")
    assert first["digest"] == same["digest"]  # generatedAt is not content
    changed = W.build_receipt({**d, "statusKo": "edited"}, generated_at="t3", inputs={},
                              evidence=W.EVIDENCE, week_status="FINAL_WEEKLY")
    ledger, report = W.append_receipts([], [first])
    assert report["appended"] == [first["receiptId"]]
    ledger, report = W.append_receipts(ledger, [same, changed])
    assert len(ledger) == 1 and ledger[0]["digest"] == first["digest"]
    assert report["unchanged"] == [first["receiptId"]] and report["conflicts"][0]["kept"] == first["digest"]
    preview = W.build_receipt(W.decide("KR", [], None, "2026-10-07"), generated_at="t", inputs={},
                              evidence=W.EVIDENCE, week_status="INTRA_WEEK_PREVIEW")
    assert W.append_receipts(ledger, [preview])[1]["appended"] == []
    tampered = dict(first, stockCount=3)
    with pytest.raises(ValueError):
        W.append_receipts([], [tampered])


def test_previous_week_change_is_reported():
    cal = _calibration()
    before = W.build_receipt(W.decide("KR", [_candidate("A", sector="X")], cal, "2026-10-02"),
                             generated_at="t", inputs={}, evidence=W.EVIDENCE, week_status="FINAL_WEEKLY")
    now = W.decide("KR", [_candidate("B", sector="Y")], cal, "2026-10-08")
    receipt = W.build_receipt(now, generated_at="t", inputs={}, evidence=W.EVIDENCE,
                              week_status="FINAL_WEEKLY", prior=before)
    change = receipt["previousWeekChange"]
    assert change["added"] == ["B"] and change["removed"] == ["A"] and change["changed"]


def test_no_receipt_claims_validation():
    out = W.build({"regions": {}}, None, {"KR": "2026-10-08", "US": "2026-10-09"},
                  now=datetime(2026, 10, 10, 2, 0, tzinfo=timezone.utc))
    assert out["liveValidated"] is False
    assert out["evidence"]["verifiedLive"] == "NOT_VERIFIED"
    for blob in out["regions"].values():
        assert blob.get("liveValidated") is False
        assert blob["policyStatus"] == "EXPLORATORY_WEEKLY_DECISION"


def test_module_matches_frozen_spec():
    spec = json.loads((ROOT / W.SPEC_PATH).read_text())
    rule = spec["rule"]
    assert spec["policyVersion"] == W.POLICY_VERSION
    assert rule["nameWeight"] == W.NAME_WEIGHT and rule["maxNames"] == W.MAX_NAMES
    assert rule["minNames"] == W.MIN_NAMES and rule["edgeHorizonSessions"] == W.EDGE_HORIZON_SESSIONS
    assert {r: b["benchmark"] for r, b in spec["regions"].items()} == W.BENCHMARKS
    cfg = json.loads((ROOT / "config.json").read_text())
    assert cfg["longterm"]["maxNameWeight"] == W.NAME_WEIGHT
    assert cfg["kellyPortfolio"]["selection"]["maxNamesPerSector"] == W.MAX_NAMES_PER_SECTOR
    assert spec["promotionEligible"] is False and spec["liveValidated"] is False

