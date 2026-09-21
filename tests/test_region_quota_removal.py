"""The region cap must be the ONLY thing that moves, and the scale claim must be measured.

Three ways this study could fool itself: widening `maxNamesPerSector` along
with the region cap (which would blur two different diversification
questions into one number), letting the config edit leak into `targetNames`
or the cost schedule (which would stack an unrelated axis), or asserting the
prerequisite about calibration comparability in prose instead of measuring it
from the control's own candidates. All three are tested directly.
"""
from __future__ import annotations

import pytest

from pipeline import region_quota_removal as RQ


# --------------------------------------------------------------------------- #
# local_cfg
# --------------------------------------------------------------------------- #
def test_local_cfg_opens_only_the_region_cap():
    base = {"selection": {"targetNames": 5, "minNames": 3, "maxNamesPerSector": 2,
                          "maxNamesPerRegion": 3, "convictionTiltRange": 1.0},
            "maxPositionWeight": 0.25, "minCashPct": 10}
    out = RQ.local_cfg(base)
    assert out["selection"]["maxNamesPerRegion"] == 5
    assert out["selection"]["maxNamesPerSector"] == 2
    assert out["selection"]["targetNames"] == 5
    assert out["selection"]["minNames"] == 3
    assert out["maxPositionWeight"] == 0.25
    assert out["minCashPct"] == 10


def test_local_cfg_opens_the_cap_to_target_names_not_to_infinity():
    base = {"selection": {"targetNames": 7, "maxNamesPerRegion": 3}}
    out = RQ.local_cfg(base)
    assert out["selection"]["maxNamesPerRegion"] == 7


def test_local_cfg_does_not_mutate_the_original():
    base = {"selection": {"targetNames": 5, "maxNamesPerRegion": 3}}
    RQ.local_cfg(base)
    assert base["selection"]["maxNamesPerRegion"] == 3


def test_local_cfg_falls_back_to_max_names_when_target_names_is_absent():
    base = {"selection": {"maxNamesPerRegion": 3}, "maxNames": 8}
    out = RQ.local_cfg(base)
    assert out["selection"]["maxNamesPerRegion"] == 8


# --------------------------------------------------------------------------- #
# calibration_comparability
# --------------------------------------------------------------------------- #
def _decision(date, rows):
    return {"date": date, "scored": rows}


def _row(ticker, region, *, alpha, se, shrink, eff, unique):
    return {"ticker": ticker, "region": region,
            "calibration": {"expectedExcessReturnPct": alpha, "standardErrorPct": se,
                            "shrinkageFactor": shrink, "effectiveIndependentDates": eff,
                            "uniqueDates": unique}}


def test_comparability_splits_by_region_and_reads_every_calibration_field():
    decisions = [_decision("2020-01-01", [
        _row("A", "US", alpha=3.0, se=0.5, shrink=0.9, eff=40, unique=45),
        _row("K", "KR", alpha=1.5, se=0.9, shrink=0.4, eff=12, unique=15),
    ])]
    blob = RQ.calibration_comparability(decisions)
    assert blob["available"] is True
    assert blob["byRegion"]["US"]["alpha"]["mean"] == pytest.approx(3.0)
    assert blob["byRegion"]["KR"]["shrink"]["mean"] == pytest.approx(0.4)
    assert blob["byRegion"]["KR"]["effectiveDates"]["mean"] == pytest.approx(12)


def test_comparability_counts_each_name_date_once_even_if_scored_twice():
    """A rung that scored a name twice for the same date must not double count."""
    row = _row("A", "US", alpha=3.0, se=0.5, shrink=0.9, eff=40, unique=45)
    decisions = [_decision("2020-01-01", [row, dict(row)])]
    blob = RQ.calibration_comparability(decisions)
    assert blob["byRegion"]["US"]["alpha"]["observations"] == 1


def test_a_name_with_no_calibration_is_skipped_not_zeroed():
    decisions = [_decision("2020-01-01", [
        {"ticker": "A", "region": "US", "calibration": None},
        _row("K", "KR", alpha=1.0, se=0.5, shrink=0.5, eff=20, unique=20),
    ])]
    blob = RQ.calibration_comparability(decisions)
    assert "US" not in blob["byRegion"]
    assert blob["byRegion"]["KR"]["alpha"]["observations"] == 1


def test_no_decisions_reports_absence():
    assert RQ.calibration_comparability([])["available"] is False


# --------------------------------------------------------------------------- #
# region_mix
# --------------------------------------------------------------------------- #
def test_region_mix_tallies_held_name_dates_and_shapes():
    decisions = [
        {"retained": [], "added": ["A", "B", "K"],
         "regionByTicker": {"A": "US", "B": "US", "K": "KR"}},
        {"retained": ["A"], "added": ["C"],
         "regionByTicker": {"A": "US", "C": "KR"}},
    ]
    blob = RQ.region_mix(decisions)
    assert blob["heldNameDatesByRegion"] == {"KR": 2, "US": 3}
    assert sum(blob["regionShapeCounts"].values()) == 2


def test_region_mix_on_no_decisions_returns_empty_tallies():
    blob = RQ.region_mix([])
    assert blob["heldNameDatesByRegion"] == {}
    assert blob["regionShapeCounts"] == {}


# --------------------------------------------------------------------------- #
# Freeze manifest
# --------------------------------------------------------------------------- #
def test_the_ladder_carries_alpha_reliability_s_own_control():
    from pipeline import alpha_reliability as AR
    assert RQ.LADDER[0] == RQ.CONTROL == AR.CONTROL


def test_the_sector_cap_and_target_names_are_declared_unchanged():
    manifest = RQ.freeze_manifest()
    assert manifest["sectorCapUnchangedFromProduction"] is True
    assert manifest["targetNamesUnchangedFromProduction"] is True
    assert manifest["regionCapControl"] == 3


def test_the_prerequisite_is_recorded_as_measured_not_asserted():
    manifest = RQ.freeze_manifest()
    assert "prerequisiteMeasuredBy" in manifest
    assert manifest["prerequisiteMeasuredBy"]


def test_this_study_does_not_claim_to_be_the_full_pre_registered_destination():
    manifest = RQ.freeze_manifest()
    assert "risk/covariance" in manifest["notTheFullPreRegisteredDestination"]


def test_no_new_parameter_and_nothing_promoted():
    manifest = RQ.freeze_manifest()
    assert manifest["parametersIntroduced"] == []
    assert manifest["permutationNullRun"] is False
    assert manifest["promotionEligible"] is False
    assert manifest["liveValidated"] is False
    assert manifest["productionChanged"] is False
