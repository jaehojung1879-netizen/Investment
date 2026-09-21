"""A diagnostic added after a ladder is scored may only READ it.

Four ways this extension could betray that rule: re-defining the frozen
ladder instead of importing it, letting the exploratory two-axis stack be
paired into the primary ladder, letting a realised return reach a score, or
mutating the decisions it reads. All four are tested directly, plus the
set-difference pairing itself.
"""
from __future__ import annotations

import pytest

from pipeline import alpha_reliability as AR
from pipeline import alpha_risk_separation as ARS
from pipeline import alpha_risk_separation_diagnostics as D


# --------------------------------------------------------------------------- #
# The frozen ladder is imported, never redefined
# --------------------------------------------------------------------------- #
def test_the_ladder_is_the_frozen_study_s_own_objects():
    assert D.PRIMARY_LADDER is ARS.LADDER
    assert D.CONTROL == ARS.CONTROL == AR.CONTROL
    assert D.ALPHA_ONLY == ARS.ALPHA_ONLY


def test_the_exploratory_stack_is_not_a_rung_of_the_primary_ladder():
    assert D.EXPLORATORY_STACK not in D.PRIMARY_LADDER
    manifest = D.freeze_manifest()
    assert manifest["primaryLadderRescored"] is False
    assert manifest["frozenReportRewritten"] is False
    caveat = manifest["exploratoryMovesTwoAxes"].lower()
    assert "attributable to neither" in caveat
    assert "never paired into the primary ladder" in caveat


def test_the_frozen_keys_cover_every_scored_block_of_the_study():
    # If a scored block of the frozen report is not asserted byte-identical,
    # a diagnostic here could move it without anything failing.
    for key in ("ladder", "pairedVsControl", "separation", "riskDominance",
                "boundaryInstability", "replacementAnatomy", "tiltSurvival"):
        assert key in D.FROZEN_KEYS


def test_realised_returns_are_declared_evaluation_only():
    manifest = D.freeze_manifest()
    assert manifest["realisedReturnsUsedFor"] == "EVALUATION_ONLY_NEVER_RULE_CONSTRUCTION"


def test_no_new_parameter_no_post_hoc_threshold_nothing_promoted():
    manifest = D.freeze_manifest()
    assert manifest["parametersIntroduced"] == []
    assert manifest["thresholdsAddedAfterSeeingAResult"] == []
    assert manifest["permutationNullRun"] is False
    assert manifest["promotionEligible"] is False
    assert manifest["liveValidated"] is False
    assert manifest["productionChanged"] is False


def test_region_and_entry_diagnostics_are_declared_observational():
    joined = " ".join(D.freeze_manifest()["observationalOnly"])
    assert "region" in joined and "entry" in joined


# --------------------------------------------------------------------------- #
# set_difference_profiles
# --------------------------------------------------------------------------- #
def _row(ticker, *, momentum, value, quality, lowvol, vol, percentile=95, alpha=1.0):
    return {"ticker": ticker, "region": "US", "sector": "Tech",
            "factorPercentiles": {"momentum": momentum, "value": value,
                                  "quality": quality, "lowvol": lowvol},
            "downsideVolPct": vol, "alphaPercentile": percentile,
            "expectedGrossBenchmarkExcessPct": alpha}


def _decisions(date, control_held, alpha_held, scored):
    control = {"date": date, "retained": [], "added": sorted(control_held),
               "scored": scored}
    alpha = {"date": date, "retained": [], "added": sorted(alpha_held), "scored": scored}
    return [control], [alpha]


def test_set_difference_splits_the_two_disagreement_groups():
    scored = [
        _row("HIVOL", momentum=99, value=50, quality=60, lowvol=10, vol=40.0),
        _row("LOVOL", momentum=40, value=55, quality=65, lowvol=95, vol=12.0),
        _row("BOTH", momentum=70, value=70, quality=70, lowvol=70, vol=20.0),
    ]
    control, alpha = _decisions("2020-01-01", {"LOVOL", "BOTH"}, {"HIVOL", "BOTH"}, scored)
    priced = {"2020-01-01": {"HIVOL": {"excessReturn": 0.05},
                             "LOVOL": {"excessReturn": -0.01}}}
    blob = D.set_difference_profiles(control, alpha, priced)

    assert blob["available"] is True
    assert blob["heldNameDatesAgreed"] == 1
    assert blob["heldNameDatesDisagreed"] == 1
    challenger = blob["selectedByChallengerNotControl"]
    only_control = blob["selectedByControlNotChallenger"]
    assert challenger["nameDates"] == 1 and only_control["nameDates"] == 1
    # The challenger took the high-momentum / high-vol name.
    assert challenger["momentum"]["mean"] == pytest.approx(99)
    assert challenger["downsideVolPct"]["mean"] == pytest.approx(40.0)
    assert only_control["lowvol"]["mean"] == pytest.approx(95)
    assert only_control["downsideVolPct"]["mean"] == pytest.approx(12.0)


def test_set_difference_reports_the_realised_gap_in_percentage_points():
    scored = [_row("A", momentum=90, value=50, quality=50, lowvol=20, vol=30.0),
              _row("B", momentum=30, value=50, quality=50, lowvol=90, vol=15.0)]
    control, alpha = _decisions("2020-01-01", {"B"}, {"A"}, scored)
    priced = {"2020-01-01": {"A": {"excessReturn": 0.04}, "B": {"excessReturn": 0.01}}}
    blob = D.set_difference_profiles(control, alpha, priced)
    # 4% - 1% = +3.00pp, and `_outcome_block` already scales to percent.
    assert blob["realisedForwardExcessDifferencePp"] == pytest.approx(3.0, abs=1e-6)


def test_set_difference_is_paired_within_a_date_not_pooled_across_them():
    """The two rungs swap their disagreement between two dates.

    Pooled across dates both names are held by both rungs and the difference
    would be EMPTY. Paired within each date, each name lands in a different
    group on each date — two name-dates a side.
    """
    scored = [_row("X", momentum=80, value=50, quality=50, lowvol=50, vol=25.0),
              _row("Y", momentum=20, value=50, quality=50, lowvol=80, vol=15.0)]
    control = [{"date": "2020-01-01", "retained": [], "added": ["Y"], "scored": scored},
               {"date": "2020-02-01", "retained": [], "added": ["X"], "scored": scored}]
    alpha = [{"date": "2020-01-01", "retained": [], "added": ["X"], "scored": scored},
             {"date": "2020-02-01", "retained": [], "added": ["Y"], "scored": scored}]
    blob = D.set_difference_profiles(control, alpha, {})
    assert blob["rebalancesMeasured"] == 2
    assert blob["selectedByChallengerNotControl"]["nameDates"] == 2
    assert blob["selectedByControlNotChallenger"]["nameDates"] == 2
    # Each group saw X once and Y once, so the momentum means coincide at the
    # midpoint — the signature of a within-date pairing rather than a pooled one.
    assert blob["selectedByChallengerNotControl"]["momentum"]["mean"] == pytest.approx(50)
    assert blob["selectedByControlNotChallenger"]["momentum"]["mean"] == pytest.approx(50)


def test_a_date_only_one_rung_scored_is_skipped_not_half_counted():
    scored = [_row("A", momentum=90, value=50, quality=50, lowvol=20, vol=30.0)]
    control = [{"date": "2020-01-01", "retained": [], "added": ["A"], "scored": scored}]
    alpha = [{"date": "2020-02-01", "retained": [], "added": ["A"], "scored": scored}]
    blob = D.set_difference_profiles(control, alpha, {})
    assert blob["rebalancesMeasured"] == 0
    assert blob["available"] is False


def test_an_empty_book_on_either_side_is_not_measured():
    scored = [_row("A", momentum=90, value=50, quality=50, lowvol=20, vol=30.0)]
    control = [{"date": "2020-01-01", "retained": [], "added": [], "scored": scored}]
    alpha = [{"date": "2020-01-01", "retained": [], "added": ["A"], "scored": scored}]
    blob = D.set_difference_profiles(control, alpha, {})
    assert blob["rebalancesMeasured"] == 0


def test_a_missing_price_is_absent_from_the_return_not_a_zero():
    scored = [_row("A", momentum=90, value=50, quality=50, lowvol=20, vol=30.0),
              _row("B", momentum=30, value=50, quality=50, lowvol=90, vol=15.0)]
    control, alpha = _decisions("2020-01-01", {"B"}, {"A"}, scored)
    blob = D.set_difference_profiles(control, alpha, {})  # nothing priced
    challenger = blob["selectedByChallengerNotControl"]
    assert challenger["nameDates"] == 1
    assert challenger["realisedForwardBenchmarkExcessPct"]["available"] is False
    assert blob["realisedForwardExcessDifferencePp"] is None


def test_set_difference_does_not_mutate_the_decisions_it_reads():
    scored = [_row("A", momentum=90, value=50, quality=50, lowvol=20, vol=30.0),
              _row("B", momentum=30, value=50, quality=50, lowvol=90, vol=15.0)]
    control, alpha = _decisions("2020-01-01", {"B"}, {"A"}, scored)
    before = [dict(row) for row in scored]
    D.set_difference_profiles(control, alpha, {"2020-01-01": {"A": {"excessReturn": 0.04}}})
    assert [dict(row) for row in scored] == before
    assert control[0]["added"] == ["B"] and alpha[0]["added"] == ["A"]


def test_no_decisions_reports_absence_rather_than_a_zero_profile():
    blob = D.set_difference_profiles([], [], {})
    assert blob["available"] is False
    assert blob["selectedByChallengerNotControl"]["nameDates"] == 0
    assert blob["realisedForwardExcessDifferencePp"] is None
