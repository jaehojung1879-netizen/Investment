"""The score must divide by nothing except entry state, and eligibility must not move.

Two ways this study could fool itself. `separation_scores` could accidentally
keep a risk term in the formula (defeating the whole point of the ablation),
or it could relax `DOWNSIDE_RISK_UNAVAILABLE` along with the score change,
which would let this study claim a benefit that actually came from sizing
names the control could not size at all. Both are tested directly.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline import alpha_reliability as AR
from pipeline import alpha_risk_separation as ARS

ROOT = Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))["kellyPortfolio"]


class _Calibration:
    def __init__(self, table=None):
        self.table = table or {}

    def expected(self, region, percentile):
        if percentile is None:
            return None
        edges = (0, 60, 80, 90, 95, 100)
        label = None
        for low, high in zip(edges, edges[1:]):
            if low <= float(percentile) <= high:
                label = f"{low}-{high}"
                break
        if label is None:
            return None
        value = self.table.get((region, label))
        if value is None:
            return None
        return {"bucket": label, "expectedExcessReturnPct": value}


def _row(ticker, *, region="US", percentile=97, vol=20.0, sector="Tech",
         sleeves=None, state="ACCUMULATE_GRADUALLY"):
    return {"ticker": ticker, "region": region, "sector": sector,
            "alphaPercentile": percentile,
            "factorPercentiles": dict(sleeves or {"momentum": 90, "value": 90,
                                                   "quality": 90, "lowvol": 90}),
            "risk": {"downsideVolPct": vol}, "downsideVolPct": vol,
            "entryState": state, "entry": {"entryState": state},
            "longTermResearchView": "POSITIVE", "dataInsufficient": False,
            "valueTrap": False, "evidenceCoverage": 0.9}


# --------------------------------------------------------------------------- #
# The axis itself: no risk term anywhere in the challenger's score
# --------------------------------------------------------------------------- #
def test_the_challenger_score_is_alpha_times_state_and_nothing_else():
    calibration = _Calibration({("US", "95-100"): 4.0})
    scored = ARS.separation_scores([_row("A", vol=10.0)], calibration, CFG)
    assert scored[0]["score"] == pytest.approx(4.0 * 1.0)


def test_two_names_with_identical_alpha_and_different_risk_tie_on_the_challenger():
    """The whole point of the ablation: risk cannot break a tie it used to break."""
    calibration = _Calibration({("US", "95-100"): 4.0})
    scored = ARS.separation_scores(
        [_row("LOW_RISK", vol=5.0), _row("HIGH_RISK", vol=40.0)], calibration, CFG)
    scores = {row["ticker"]: row["score"] for row in scored}
    assert scores["LOW_RISK"] == pytest.approx(scores["HIGH_RISK"])


def test_the_control_score_still_divides_by_risk_and_breaks_that_same_tie():
    """Sanity check on the control this study borrows: the axis is real."""
    calibration = _Calibration({("US", "95-100"): 4.0})
    control_rows = AR.reliability_scores(
        [dict(_row("LOW_RISK", vol=5.0), signalConfidence=1.0),
         dict(_row("HIGH_RISK", vol=40.0), signalConfidence=1.0)],
        calibration, CFG, as_of="2020-01-01")
    scores = {row["ticker"]: row["score"] for row in control_rows}
    assert scores["LOW_RISK"] > scores["HIGH_RISK"]


def test_entry_state_multiplier_still_scales_the_challenger_score():
    calibration = _Calibration({("US", "95-100"): 4.0})
    scored = ARS.separation_scores([_row("A", state="WATCH")], calibration, CFG)
    assert scored[0]["score"] == pytest.approx(4.0 * float(CFG["watchWeightMultiplier"]))


# --------------------------------------------------------------------------- #
# Eligibility: sizing still needs a risk unit, whatever the ranking divides by
# --------------------------------------------------------------------------- #
def test_a_name_with_no_risk_unit_is_still_excluded_on_the_challenger():
    calibration = _Calibration({("US", "95-100"): 4.0})
    row = _row("NO_RISK")
    row["risk"] = {}
    row["downsideVolPct"] = None
    scored = ARS.separation_scores([row], calibration, CFG)
    assert scored[0]["eligible"] is False
    assert "DOWNSIDE_RISK_UNAVAILABLE" in scored[0]["exclusionCodes"]


def test_a_name_without_a_matured_calibration_is_excluded_not_scored_at_zero():
    scored = ARS.separation_scores([_row("A")], _Calibration({}), CFG)
    assert scored[0]["eligible"] is False
    assert "MATURED_CALIBRATION_NOT_READY" in scored[0]["exclusionCodes"]
    assert scored[0]["score"] == -1e12


def test_a_blocking_entry_state_excludes_on_both_rungs():
    calibration = _Calibration({("US", "95-100"): 4.0})
    row = _row("BLOCKED", state="AVOID")
    scored = ARS.separation_scores([row], calibration, CFG)
    assert scored[0]["eligible"] is False
    assert "ENTRY_OR_RESEARCH_STATE_BLOCKS_SIZING" in scored[0]["exclusionCodes"]


# --------------------------------------------------------------------------- #
# Field shape: every `alpha_reliability` diagnostic reads this rung unmodified
# --------------------------------------------------------------------------- #
def test_output_rows_carry_every_field_the_reused_diagnostics_read():
    calibration = _Calibration({("US", "95-100"): 4.0})
    row = ARS.separation_scores([_row("A")], calibration, CFG)[0]
    for key in ("ticker", "region", "sector", "score", "alphaPercentile",
                "rawAlphaPercentile", "downsideVolPct", "expectedGrossBenchmarkExcessPct",
                "factorPercentiles", "entryState", "entryStateMultiplier", "eligible",
                "exclusionCodes", "eligibilityCodes"):
        assert key in row


def test_confidence_and_uncertainty_are_neutral_placeholders_not_an_axis():
    """This study does not move confidence; the fields exist only so the reused
    `alpha_reliability` diagnostics do not need a special case."""
    calibration = _Calibration({("US", "95-100"): 4.0})
    row = ARS.separation_scores([_row("A")], calibration, CFG)[0]
    assert row["signalConfidence"] == 1.0
    assert row["uncertaintyMarginPct"] == 0.0
    assert row["reliableAlphaPct"] == row["expectedGrossBenchmarkExcessPct"]


# --------------------------------------------------------------------------- #
# tilt_survival
# --------------------------------------------------------------------------- #
def test_tilt_survival_reports_absence_when_either_side_is_unmeasured():
    assert ARS.tilt_survival({"available": False}, {"available": True})["available"] is False


def test_tilt_survival_computes_deltas_as_alpha_only_minus_control():
    control = {"available": True,
               "downsideVolPctSelected": {"mean": 24.45},
               "downsideVolPctRejected": {"mean": 27.17},
               "lowvolSleevePercentileSelected": {"mean": 74.37},
               "lowvolIsTheHighestSleevePct": 32.69,
               "lowvolIsInTheTopTwoSleevesPct": 58.86,
               "scoreVsDownsideVolSpearman": {"mean": 0.075}}
    alpha_only = {"available": True,
                  "downsideVolPctSelected": {"mean": 25.38},
                  "downsideVolPctRejected": {"mean": 26.88},
                  "lowvolSleevePercentileSelected": {"mean": 70.51},
                  "lowvolIsTheHighestSleevePct": 28.53,
                  "lowvolIsInTheTopTwoSleevesPct": 53.88,
                  "scoreVsDownsideVolSpearman": {"mean": 0.044}}
    blob = ARS.tilt_survival(control, alpha_only)
    assert blob["available"] is True
    assert blob["downsideVolPctSelectedDelta"] == pytest.approx(25.38 - 24.45, abs=1e-6)
    assert blob["lowvolIsTheHighestSleevePctDelta"] == pytest.approx(28.53 - 32.69, abs=1e-6)


# --------------------------------------------------------------------------- #
# Freeze manifest
# --------------------------------------------------------------------------- #
def test_the_ladder_carries_alpha_reliability_s_own_control():
    assert ARS.LADDER[0] == ARS.CONTROL == AR.CONTROL
    assert ARS.freeze_manifest()["controlSource"].startswith("alpha_reliability.run_rung")


def test_the_lowvol_sleeve_and_sizing_base_are_declared_unchanged():
    manifest = ARS.freeze_manifest()
    channels = manifest["riskChannelsInThisSystem"]
    assert "UNCHANGED" in channels["alphaLevel"]
    assert "REMOVED" in channels["selectionRanking"]
    assert "UNCHANGED" in channels["positionSizing"]
    assert manifest["downsideRiskUnavailableStillExcludesBothRungs"] is True


def test_no_new_parameter_and_nothing_promoted():
    manifest = ARS.freeze_manifest()
    assert manifest["parametersIntroduced"] == []
    assert manifest["permutationNullRun"] is False
    assert manifest["promotionEligible"] is False
    assert manifest["liveValidated"] is False
    assert manifest["productionChanged"] is False
