"""The switch hurdle: what a swap must clear, and that the control is real.

The rule is only as good as its control. `benchmark-relative-alpha-v1` moved
cadence, a cash gate and the weighting rule together and could not say which one
cost what; this ladder's whole claim rests on the no-hurdle rung running the same
loop, so the tests that matter most here are the ones that keep the rungs
differing in exactly one thing.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline import portfolio_validation as PV
from pipeline import switch_hurdle as SH

ROOT = Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))["kellyPortfolio"]

REALISTIC = {"transactionCosts": {
    "US": {"commissionBps": 5.0, "spreadBps": 6.0, "sellTaxBps": 0.30},
    "KR": {"commissionBps": 1.5, "spreadBps": 8.0, "sellTaxBps": 20.0,
           "sellTaxSchedule": [{"effectiveDate": "1900-01-01", "sellTaxBps": 30.0},
                               {"effectiveDate": "2023-01-01", "sellTaxBps": 20.0}]},
}}


class _Calibration:
    """Bucket estimates keyed by region, standing in for the expanding one."""

    def __init__(self, table):
        self.table = table

    def expected(self, region, alpha_percentile):
        return self.table.get(region)


def _candidate(ticker, region, *, vol=20.0, state="ACCUMULATE_GRADUALLY"):
    return {"ticker": ticker, "region": region, "sector": "S",
            "longTermResearchView": "POSITIVE", "entryState": state,
            "risk": {"downsideVolPct": vol}, "alphaPercentile": 90.0}


# --------------------------------------------------------------------------- #
# leg_costs
# --------------------------------------------------------------------------- #
def test_a_sell_carries_the_tax_and_a_buy_does_not():
    """`_turnover_cost` charges the realised path this way; the hurdle must match."""
    buy, sell = SH.leg_costs("KR", "2013-06-30", REALISTIC)
    assert buy == pytest.approx((1.5 + 4.0) / 100)
    assert sell == pytest.approx((1.5 + 4.0 + 30.0) / 100)     # 2013 statutory rate
    assert sell > buy


def test_the_korean_sell_leg_follows_the_dated_statutory_schedule():
    early = SH.leg_costs("KR", "2013-06-30", REALISTIC)[1]
    late = SH.leg_costs("KR", "2024-06-30", REALISTIC)[1]
    assert early > late                                        # 30bp fell to 20bp
    assert late == pytest.approx((1.5 + 4.0 + 20.0) / 100)


def test_korea_costs_more_to_turn_over_than_america():
    """The asymmetry the hurdle inherits is the tax code, not a chosen ratio."""
    for date in ("2013-06-30", "2026-06-30"):
        kr = sum(SH.leg_costs("KR", date, REALISTIC))
        us = sum(SH.leg_costs("US", date, REALISTIC))
        assert kr > us * 1.5, date


# --------------------------------------------------------------------------- #
# hurdle_scores
# --------------------------------------------------------------------------- #
def test_an_incumbent_is_credited_what_staying_avoids():
    calibration = _Calibration({"KR": {"expectedExcessReturnPct": 1.0,
                                       "shrinkageFactor": 1.0, "standardErrorPct": 0.5}})
    rows = SH.hurdle_scores([_candidate("A", "KR")], calibration, REALISTIC,
                            as_of="2024-06-30", incumbents={"A"})
    sell = SH.leg_costs("KR", "2024-06-30", REALISTIC)[1]
    assert rows[0]["decisionAlphaPct"] == pytest.approx(1.0 + sell)
    assert rows[0]["retentionCreditPct"] == pytest.approx(sell)


def test_a_challenger_pays_what_arriving_costs():
    calibration = _Calibration({"KR": {"expectedExcessReturnPct": 1.0,
                                       "shrinkageFactor": 1.0, "standardErrorPct": 0.5}})
    rows = SH.hurdle_scores([_candidate("B", "KR")], calibration, REALISTIC,
                            as_of="2024-06-30", incumbents=set())
    buy = SH.leg_costs("KR", "2024-06-30", REALISTIC)[0]
    assert rows[0]["decisionAlphaPct"] == pytest.approx(1.0 - buy)
    assert rows[0]["retentionCreditPct"] == 0.0


def test_an_equal_alpha_challenger_cannot_displace_an_incumbent():
    """The whole rule in one assertion: a tie is not a reason to trade."""
    calibration = _Calibration({"KR": {"expectedExcessReturnPct": 1.0,
                                       "shrinkageFactor": 1.0, "standardErrorPct": 0.5}})
    rows = SH.hurdle_scores([_candidate("HELD", "KR"), _candidate("NEW", "KR")],
                            calibration, REALISTIC, as_of="2024-06-30",
                            incumbents={"HELD"})
    by = {r["ticker"]: r for r in rows}
    assert by["HELD"]["score"] > by["NEW"]["score"]


def test_a_challenger_that_clears_the_whole_round_trip_does_displace_it():
    calibration = _Calibration({
        "KR": {"expectedExcessReturnPct": 1.0, "shrinkageFactor": 1.0,
               "standardErrorPct": 0.5}})
    buy, sell = SH.leg_costs("KR", "2024-06-30", REALISTIC)
    strong = _candidate("NEW", "KR")
    rows = SH.hurdle_scores([_candidate("HELD", "KR"), strong], calibration, REALISTIC,
                            as_of="2024-06-30", incumbents={"HELD"})
    # Same bucket, so lift the challenger's own alpha past the round trip instead.
    calibration.table["KR"] = {"expectedExcessReturnPct": 1.0 + buy + sell + 0.01,
                               "shrinkageFactor": 1.0, "standardErrorPct": 0.5}
    lifted = SH.hurdle_scores([_candidate("HELD", "KR"), strong], calibration, REALISTIC,
                              as_of="2024-06-30", incumbents=set())
    assert rows[0]["eligible"] and lifted[0]["eligible"]
    assert lifted[0]["decisionAlphaPct"] > rows[0]["decisionAlphaPct"]


def test_the_uncertainty_margin_is_scaled_the_same_way_the_alpha_is():
    """The alpha carried is shrunk; an unshrunk margin would gate the wrong quantity."""
    calibration = _Calibration({"US": {"expectedExcessReturnPct": 2.0,
                                       "shrinkageFactor": 0.5, "standardErrorPct": 1.0}})
    rows = SH.hurdle_scores([_candidate("N", "US")], calibration, REALISTIC,
                            as_of="2024-06-30", incumbents=set(), se_multiple=1.0)
    buy = SH.leg_costs("US", "2024-06-30", REALISTIC)[0]
    assert rows[0]["uncertaintyMarginPct"] == pytest.approx(1.0 * 0.5)
    assert rows[0]["decisionAlphaPct"] == pytest.approx(2.0 - buy - 0.5)


def test_the_margin_is_absent_when_the_rung_does_not_ask_for_one():
    calibration = _Calibration({"US": {"expectedExcessReturnPct": 2.0,
                                       "shrinkageFactor": 0.5, "standardErrorPct": 1.0}})
    rows = SH.hurdle_scores([_candidate("N", "US")], calibration, REALISTIC,
                            as_of="2024-06-30", incumbents=set(), se_multiple=0.0)
    assert rows[0]["uncertaintyMarginPct"] == 0.0


def test_the_control_switches_the_hurdle_off_entirely():
    """Without this the ladder has no baseline that differs in one thing only."""
    calibration = _Calibration({"KR": {"expectedExcessReturnPct": 1.0,
                                       "shrinkageFactor": 1.0, "standardErrorPct": 0.5}})
    rows = SH.hurdle_scores([_candidate("HELD", "KR"), _candidate("NEW", "KR")],
                            calibration, REALISTIC, as_of="2024-06-30",
                            incumbents={"HELD"}, apply_cost=False)
    by = {r["ticker"]: r for r in rows}
    assert by["HELD"]["decisionAlphaPct"] == pytest.approx(1.0)
    assert by["NEW"]["decisionAlphaPct"] == pytest.approx(1.0)
    assert by["HELD"]["retentionCreditPct"] == 0.0


def test_the_hurdle_never_rescues_an_ineligible_incumbent():
    """A retention credit orders names; it does not make one holdable."""
    calibration = _Calibration({"KR": {"expectedExcessReturnPct": 1.0,
                                       "shrinkageFactor": 1.0, "standardErrorPct": 0.5}})
    rows = SH.hurdle_scores([_candidate("HELD", "KR", state="AVOID")], calibration,
                            REALISTIC, as_of="2024-06-30", incumbents={"HELD"})
    assert rows[0]["eligible"] is False
    assert "ENTRY_OR_RESEARCH_STATE_BLOCKS_SIZING" in rows[0]["exclusionCodes"]


def test_a_name_without_a_matured_calibration_is_excluded_not_scored_at_zero():
    rows = SH.hurdle_scores([_candidate("X", "KR")], _Calibration({}), REALISTIC,
                            as_of="2024-06-30", incumbents=set())
    assert rows[0]["eligible"] is False
    assert rows[0]["decisionAlphaPct"] is None
    assert "MATURED_CALIBRATION_NOT_READY" in rows[0]["exclusionCodes"]


# --------------------------------------------------------------------------- #
# The calibration now publishes the precision the hurdle needs
# --------------------------------------------------------------------------- #
def test_bucket_estimates_carry_a_standard_error_on_independent_dates():
    """Dividing by every date would understate the error by about the overlap."""
    def month(i):
        return f"{2015 + i // 12:04d}-{1 + i % 12:02d}-15"

    outcomes = [
        {"id": f"d{i}", "date": month(i), "ticker": f"T{i}",
         "region": "US", "alphaPercentile": 92.0,
         "horizons": {"126": {"excessReturn": 0.01 * (1 if i % 2 else -1),
                              "costAdjustedExcessReturn": 0.01 * (1 if i % 2 else -1),
                              "endDate": month(i)}}}
        for i in range(60)]
    cal = PV.ExpandingBucketCalibration(outcomes, horizon=126, min_dates=5)
    cal.advance("2026-01-01")
    estimate = cal.expected("US", 92.0)
    assert estimate is not None
    assert estimate["standardErrorPct"] is not None
    assert estimate["standardErrorPct"] > 0
    # 60 monthly observations, but a 126-session window overlaps about six of
    # them, so the independent count is far smaller and the error far larger.
    assert estimate["uniqueDates"] == 60
    assert estimate["effectiveIndependentDates"] < estimate["uniqueDates"]


# --------------------------------------------------------------------------- #
# Freeze manifest
# --------------------------------------------------------------------------- #
def test_the_manifest_freezes_the_se_multiple_and_promotes_nothing():
    manifest = SH.freeze_manifest()
    assert manifest["seMultiple"] == 1.0 == SH.SE_MULTIPLE
    assert manifest["promotionEligible"] is False
    assert manifest["liveValidated"] is False
    assert manifest["productionChanged"] is False
    assert manifest["positiveAlphaCashGate"] is False       # v1's gate is a separate lever
    assert SH.CONTROL in manifest["ladder"]


def test_the_ladder_carries_its_own_control():
    assert SH.LADDER[0] == SH.CONTROL
    assert set(SH.LADDER) == {SH.CONTROL, SH.COST, SH.COST_PLUS_SE}


# --------------------------------------------------------------------------- #
# Regional attribution
# --------------------------------------------------------------------------- #
def test_regional_contributions_rebuild_the_headline():
    rows = [{"date": f"2020-{i + 1:02d}-01", "endDate": f"2020-{i + 2:02d}-01",
             "grossExcessReturn": 0.01 * i,
             "weightByRegion": {"US": 0.4, "KR": 0.3},
             "excessByRegion": {"US": 0.006 * i, "KR": 0.004 * i}} for i in range(1, 9)]
    blob = SH.regional_attribution(rows, years=2.0)
    assert blob["available"]
    total = sum(blob["byRegion"][r]["contributionPpPerYear"] for r in ("US", "KR"))
    import numpy as np
    headline = float(np.mean([r["grossExcessReturn"] for r in rows])) * (len(rows) / 2.0) * 100
    assert total == pytest.approx(headline, abs=1e-3)


def test_a_region_never_held_is_reported_as_such_not_as_zero_skill():
    rows = [{"date": "2020-01-01", "endDate": "2020-02-01", "grossExcessReturn": 0.01,
             "weightByRegion": {"US": 0.5, "KR": 0.0},
             "excessByRegion": {"US": 0.01, "KR": 0.0}}]
    blob = SH.regional_attribution(rows, years=1.0)
    assert blob["byRegion"]["KR"]["blocksHeld"] == 0
    assert blob["byRegion"]["KR"]["sleeveExcessPpPerYear"] is None
    assert blob["byRegion"]["KR"]["sleeveWinRatePct"] is None
