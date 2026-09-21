"""The floor is unconditional, the walk stops at the first failure, and the score never moves.

Three ways this study could fool itself: testing distinguishability on the
risk-adjusted SCORE instead of the alpha claim (which would quietly reopen the
risk-denominator axis `alpha-risk-separation-v1` already closed), letting a
later name pass after an earlier one failed (which would not be a boundary
any more), or widening `local_cfg` beyond `targetNames` (which would drag the
region/sector-cap axis into a study that is not supposed to touch it). All
three are tested directly.
"""
from __future__ import annotations

import pytest

from pipeline import dynamic_breadth as DB
from pipeline import switch_hurdle as SH


def _row(ticker, *, score, alpha, se=0.5, shrink=1.0, eligible=True):
    return {
        "ticker": ticker, "score": score, "eligible": eligible,
        "calibration": {"expectedExcessReturnPct": alpha, "standardErrorPct": se,
                        "shrinkageFactor": shrink},
    }


# --------------------------------------------------------------------------- #
# dynamic_target
# --------------------------------------------------------------------------- #
def test_the_floor_is_unconditional_even_when_the_third_name_is_not_distinguishable():
    rows = [_row("A", score=3, alpha=4.0), _row("B", score=2, alpha=3.0),
            _row("C", score=1, alpha=0.01, se=5.0)]
    count, reason = DB.dynamic_target(rows, floor=3, ceiling=10)
    assert count == 3
    assert reason == "FEWER_THAN_FLOOR_ELIGIBLE"


def test_fewer_than_floor_eligible_returns_what_is_available_not_the_floor():
    rows = [_row("A", score=3, alpha=4.0), _row("B", score=2, alpha=3.0)]
    count, reason = DB.dynamic_target(rows, floor=3, ceiling=10)
    assert count == 2
    assert reason == "FEWER_THAN_FLOOR_ELIGIBLE"


def test_the_walk_stops_at_the_first_name_that_fails_the_bar():
    rows = [_row(t, score=10 - i, alpha=4.0, se=0.1) for i, t in enumerate("ABCDE")]
    rows.append(_row("FAIL", score=4, alpha=0.05, se=1.0))       # fails: 0.05 < 1x1.0
    rows.append(_row("PASSES_BUT_LATER", score=3, alpha=9.0, se=0.1))  # would pass
    count, reason = DB.dynamic_target(rows, floor=3, ceiling=10)
    assert count == 5           # A-E admitted (floor 3 + 2 more), FAIL stops the walk
    assert reason == "ALPHA_NOT_DISTINGUISHABLE_FROM_ZERO"


def test_a_negative_alpha_never_clears_the_bar_however_small_its_standard_error():
    rows = [_row(t, score=10 - i, alpha=4.0, se=0.1) for i, t in enumerate("ABC")]
    rows.append(_row("NEG", score=1, alpha=-0.5, se=0.001))
    count, reason = DB.dynamic_target(rows, floor=3, ceiling=10)
    assert count == 3
    assert reason == "ALPHA_NOT_DISTINGUISHABLE_FROM_ZERO"


def test_the_effective_standard_error_is_scaled_by_shrinkage_like_switch_hurdle():
    """1.0 shrunk by 0.5 is an effective SE of 0.5; alpha of exactly 0.5 clears it."""
    rows = [_row(t, score=10 - i, alpha=4.0, se=0.1) for i, t in enumerate("ABC")]
    rows.append(_row("EDGE", score=1, alpha=0.5, se=1.0, shrink=0.5))
    count, _ = DB.dynamic_target(rows, floor=3, ceiling=10)
    assert count == 4


def test_the_walk_never_looks_past_the_ceiling():
    rows = [_row(t, score=20 - i, alpha=4.0, se=0.1) for i, t in enumerate(
        "ABCDEFGHIJKLMNO")]
    count, reason = DB.dynamic_target(rows, floor=3, ceiling=10)
    assert count == 10
    assert reason == "REACHED_CEILING"


def test_an_ineligible_name_is_never_counted_toward_breadth():
    rows = [_row("A", score=5, alpha=4.0), _row("B", score=4, alpha=4.0),
            _row("BLOCKED", score=4.5, alpha=4.0, eligible=False)]
    count, reason = DB.dynamic_target(rows, floor=3, ceiling=10)
    assert count == 2
    assert reason == "FEWER_THAN_FLOOR_ELIGIBLE"


def test_missing_calibration_precision_stops_the_walk_rather_than_guessing():
    rows = [_row(t, score=10 - i, alpha=4.0, se=0.1) for i, t in enumerate("ABC")]
    incomplete = _row("NOSE", score=1, alpha=4.0)
    del incomplete["calibration"]["standardErrorPct"]
    rows.append(incomplete)
    count, reason = DB.dynamic_target(rows, floor=3, ceiling=10)
    assert count == 3
    assert reason == "CALIBRATION_PRECISION_UNAVAILABLE"


def test_floor_and_ceiling_and_se_multiple_are_inherited_not_invented():
    assert DB.FLOOR == 3
    assert DB.CEILING == 10
    assert DB.SE_MULTIPLE == SH.SE_MULTIPLE == 1.0


# --------------------------------------------------------------------------- #
# local_cfg
# --------------------------------------------------------------------------- #
def test_local_cfg_moves_only_target_names():
    base = {"selection": {"targetNames": 5, "minNames": 3, "maxNamesPerSector": 2,
                          "maxNamesPerRegion": 3, "convictionTiltRange": 1.0},
            "maxPositionWeight": 0.25, "minCashPct": 10}
    out = DB.local_cfg(base, 7)
    assert out["selection"]["targetNames"] == 7
    assert out["selection"]["maxNamesPerSector"] == 2
    assert out["selection"]["maxNamesPerRegion"] == 3
    assert out["selection"]["minNames"] == 3
    assert out["maxPositionWeight"] == 0.25
    assert out["minCashPct"] == 10


def test_local_cfg_does_not_mutate_the_original():
    base = {"selection": {"targetNames": 5}}
    DB.local_cfg(base, 9)
    assert base["selection"]["targetNames"] == 5


# --------------------------------------------------------------------------- #
# breadth_distribution
# --------------------------------------------------------------------------- #
def test_breadth_distribution_reports_the_gap_between_computed_and_held():
    decisions = [
        {"heldNames": 5, "computedTarget": 8, "stopReason": "ALPHA_NOT_DISTINGUISHABLE_FROM_ZERO",
         "cappedByDiversification": True},
        {"heldNames": 3, "computedTarget": 3, "stopReason": "FEWER_THAN_FLOOR_ELIGIBLE",
         "cappedByDiversification": False},
    ]
    blob = DB.breadth_distribution(decisions)
    assert blob["available"] is True
    assert blob["namesHeld"]["mean"] == pytest.approx(4.0)
    assert blob["rebalancesCappedByDiversification"] == 1
    assert blob["rebalancesCappedByDiversificationPct"] == pytest.approx(50.0)


def test_breadth_distribution_reports_absence_on_no_decisions():
    assert DB.breadth_distribution([])["available"] is False


# --------------------------------------------------------------------------- #
# Freeze manifest
# --------------------------------------------------------------------------- #
def test_the_ladder_carries_alpha_reliability_s_own_control():
    from pipeline import alpha_reliability as AR
    assert DB.LADDER[0] == DB.CONTROL == AR.CONTROL


def test_no_new_parameter_and_caps_declared_unchanged():
    manifest = DB.freeze_manifest()
    assert manifest["parametersIntroduced"] == []
    assert manifest["regionAndSectorCapsUnchangedFromProduction"] is True
    assert manifest["scoreUnchangedFromControl"] is True
    assert manifest["permutationNullRun"] is False
    assert manifest["promotionEligible"] is False
    assert manifest["productionChanged"] is False


def test_the_floor_and_ceiling_sources_are_recorded_not_asserted_silently():
    manifest = DB.freeze_manifest()
    assert "PRE_REGISTERED" in manifest["floorSource"]
    assert "PRE_REGISTERED" in manifest["ceilingSource"]
    assert "SWITCH_HURDLE" in manifest["seMultipleSource"]
