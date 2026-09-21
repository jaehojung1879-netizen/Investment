"""Confidence must only ever shrink a claim, and every input must be backward-only.

Two ways this study could fool itself and both are structural rather than
statistical. A confidence weight that could RAISE a name's expected alpha would
be a fifth factor wearing a reliability label — the ladder would then be
testing a new signal while claiming to test the old one spent better. And any
component of confidence that reached forward, or that re-used a quantity the
level had already been shrunk by, would make the rung look informative for a
reason that has nothing to do with the hypothesis. Both are tested here rather
than argued for in the module docstring.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from pipeline import alpha_reliability as AR
from pipeline import signal_persistence as SP

ROOT = Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))["kellyPortfolio"]


class _Calibration:
    """A stand-in bucket calibration with the production's coarse edges."""

    def __init__(self, table=None, se=None, shrink=1.0):
        self.table = table or {}
        self.se = se
        self.shrink = shrink

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
        return {"bucket": label, "expectedExcessReturnPct": value,
                "standardErrorPct": self.se, "shrinkageFactor": self.shrink}


def _candidate(ticker, *, region="US", percentile=97, vol=20.0, sleeves=(90, 90, 90, 90),
               sector="Tech"):
    keys = ("momentum", "value", "quality", "lowvol")
    return {"ticker": ticker, "region": region, "sector": sector,
            "alphaPercentile": percentile,
            "factorPercentiles": dict(zip(keys, sleeves)),
            "risk": {"downsideVolPct": vol},
            "longTermResearchView": "POSITIVE", "entryState": "BUY",
            "dataInsufficient": False, "valueTrap": False,
            "evidenceCoverage": 0.9}


# --------------------------------------------------------------------------- #
# sleeve_agreement
# --------------------------------------------------------------------------- #
def test_sleeves_that_agree_score_one_and_sleeves_at_the_extremes_score_zero():
    assert AR.sleeve_agreement({"a": 90, "b": 90, "c": 90, "d": 90}) == pytest.approx(1.0)
    assert AR.sleeve_agreement({"a": 0, "b": 0, "c": 100, "d": 100}) == pytest.approx(0.0)


def test_the_normalizer_is_the_arithmetic_maximum_not_a_fitted_scale():
    """50 is the largest sd values bounded in [0, 100] can have: half at each end."""
    assert AR.MAX_PERCENTILE_DISPERSION == 50.0
    extreme = np.std([0.0, 0.0, 100.0, 100.0], ddof=0)
    assert extreme == pytest.approx(AR.MAX_PERCENTILE_DISPERSION)


def test_one_sleeve_has_no_agreement_to_measure_and_abstains():
    """Answering 1.0 would hand the thinnest evidence the strongest reading."""
    assert AR.sleeve_agreement({"a": 90, "b": None, "c": None, "d": None}) is None
    assert AR.sleeve_agreement({}) is None
    assert AR.sleeve_agreement(None) is None


def test_partial_sleeves_are_measured_on_what_is_present():
    assert AR.sleeve_agreement({"a": 40, "b": 60, "c": None}) == pytest.approx(0.8)


# --------------------------------------------------------------------------- #
# history_reliability
# --------------------------------------------------------------------------- #
def test_a_name_that_never_moves_is_fully_reliable():
    assert AR.history_reliability(0.0, 6, 2.0) == pytest.approx(1.0)


def test_a_name_that_wobbles_more_than_the_cross_section_loses_reliability():
    steady = AR.history_reliability(0.5, 6, 2.0)
    noisy = AR.history_reliability(8.0, 6, 2.0)
    assert 0.0 < noisy < steady < 1.0


def test_more_blocks_of_the_same_wobble_are_more_reliable():
    assert AR.history_reliability(2.0, 6, 2.0) > AR.history_reliability(2.0, 2, 2.0)


def test_an_unmeasurable_dispersion_abstains_rather_than_scoring_one():
    assert AR.history_reliability(None, 6, 2.0) is None
    assert AR.history_reliability(1.0, 6, None) is None
    assert AR.history_reliability(0.0, 6, 0.0) is None


# --------------------------------------------------------------------------- #
# The persistence window is inherited, not re-opened
# --------------------------------------------------------------------------- #
def test_the_window_is_the_one_signal_persistence_already_fixed():
    assert AR.WINDOW_BLOCKS == SP.HORIZON_BLOCKS == 6
    assert AR.freeze_manifest()["parametersIntroduced"] == []


def test_the_dispersion_comes_from_the_same_backward_window_as_the_mean():
    smoother = SP.PercentileSmoother(3)
    assert smoother.dispersion("A") is None
    smoother.observe("A", 90.0, "d1")
    assert smoother.dispersion("A") is None          # one observation has no spread
    smoother.observe("A", 94.0, "d2")
    assert smoother.dispersion("A") == pytest.approx(np.std([90.0, 94.0], ddof=1))


# --------------------------------------------------------------------------- #
# confidence_rows
# --------------------------------------------------------------------------- #
def test_the_shared_candidate_rows_are_never_mutated():
    """Contexts are shared across rungs; an in-place edit contaminates them all."""
    state = AR.ReliabilityState()
    original = [_candidate("A"), _candidate("B", percentile=93)]
    AR.confidence_rows(original, state, "d1", persistence=True, confidence=True)
    assert original[0]["alphaPercentile"] == 97
    assert "signalConfidence" not in original[0]


def test_switching_confidence_off_is_absence_not_a_fitted_neutral():
    state = AR.ReliabilityState()
    rows = AR.confidence_rows([_candidate("A"), _candidate("B", percentile=93)],
                              state, "d1", persistence=False, confidence=False)
    assert all(row["signalConfidence"] == 1.0 for row in rows)


def test_persistence_off_reproduces_the_production_percentile():
    state = AR.ReliabilityState()
    AR.confidence_rows([_candidate("A", percentile=100)], state, "d1",
                       persistence=False, confidence=False)
    rows = AR.confidence_rows([_candidate("A", percentile=91)], state, "d2",
                              persistence=False, confidence=False)
    assert rows[0]["alphaPercentile"] == 91


def test_persistence_on_averages_the_name_s_own_backward_window():
    state = AR.ReliabilityState()
    AR.confidence_rows([_candidate("A", percentile=100)], state, "d1",
                       persistence=True, confidence=False)
    rows = AR.confidence_rows([_candidate("A", percentile=90)], state, "d2",
                              persistence=True, confidence=False)
    assert rows[0]["alphaPercentile"] == pytest.approx(95.0)


def test_the_pooled_dispersion_prior_is_built_only_from_earlier_blocks():
    """A name too new for its own dispersion borrows the pool's, and the pool is
    whatever has already been seen — never the whole history."""
    state = AR.ReliabilityState()
    assert state.pooled_sd() is None
    for index, value in enumerate((90, 94, 98)):
        AR.confidence_rows([_candidate("A", percentile=value)], state, f"d{index}",
                           persistence=True, confidence=True)
    assert state.pooled_sd() is not None


def test_a_name_with_no_measurable_confidence_abstains_from_the_rung():
    """Nothing behind the weight is not the same as full confidence."""
    state = AR.ReliabilityState()
    lonely = _candidate("A", sleeves=(90, None, None, None))
    rows = AR.confidence_rows([lonely], state, "d1", persistence=True, confidence=True)
    assert rows[0]["signalConfidence"] is None
    assert rows[0]["confidenceUnmeasuredComponents"] == list(AR.CONFIDENCE_COMPONENTS)

    scored = AR.reliability_scores(rows, _Calibration({("US", "95-100"): 3.0}), CFG,
                                   as_of="2020-01-01")
    assert scored[0]["eligible"] is False
    assert "SIGNAL_CONFIDENCE_UNMEASURABLE" in scored[0]["exclusionCodes"]


def test_the_cross_section_dispersion_is_measured_within_a_region():
    """The percentile is a within-region rank; pooling regions would compare a
    Korean name's position against an American cross-section."""
    state = AR.ReliabilityState()
    rows = AR.confidence_rows(
        [_candidate("A", region="US", percentile=100), _candidate("B", region="US", percentile=92),
         _candidate("K", region="KR", percentile=97), _candidate("L", region="KR", percentile=96)],
        state, "d1", persistence=True, confidence=True)
    by_ticker = {row["ticker"]: row for row in rows}
    assert by_ticker["A"]["crossSectionPercentileSd"] == pytest.approx(
        np.std([100.0, 92.0], ddof=1))
    assert by_ticker["K"]["crossSectionPercentileSd"] == pytest.approx(
        np.std([97.0, 96.0], ddof=1))


# --------------------------------------------------------------------------- #
# The contraction guarantee
# --------------------------------------------------------------------------- #
def test_confidence_can_only_shrink_an_alpha_claim_never_raise_it():
    """The design's one hard guarantee: a reliability weight is not a factor."""
    state = AR.ReliabilityState()
    candidates = [_candidate("A", percentile=100, sleeves=(99, 20, 99, 20)),
                  _candidate("B", percentile=93, sleeves=(92, 94, 93, 93))]
    rows = AR.confidence_rows(candidates, state, "d1", persistence=True, confidence=True)
    calibration = _Calibration({("US", "95-100"): 4.0, ("US", "90-95"): 1.0})
    scored = AR.reliability_scores(rows, calibration, CFG, as_of="2020-01-01")
    assert AR.contraction_holds(scored)
    for row in scored:
        assert abs(row["reliableAlphaPct"]) <= abs(row["expectedGrossBenchmarkExcessPct"])


def test_the_contraction_check_catches_an_amplified_claim():
    assert AR.contraction_holds([
        {"expectedGrossBenchmarkExcessPct": 2.0, "reliableAlphaPct": 3.0}]) is False
    assert AR.contraction_holds([
        {"expectedGrossBenchmarkExcessPct": 2.0, "reliableAlphaPct": -1.0}]) is False
    assert AR.contraction_holds([
        {"expectedGrossBenchmarkExcessPct": None, "reliableAlphaPct": None}]) is True


def test_a_negative_alpha_is_contracted_toward_zero_and_keeps_its_sign():
    state = AR.ReliabilityState()
    rows = AR.confidence_rows([_candidate("A", percentile=93, sleeves=(99, 20, 99, 20))],
                              state, "d1", persistence=True, confidence=True)
    scored = AR.reliability_scores(rows, _Calibration({("US", "90-95"): -2.0}), CFG,
                                   as_of="2020-01-01")
    assert -2.0 < scored[0]["reliableAlphaPct"] < 0.0


# --------------------------------------------------------------------------- #
# The hysteresis, and how it differs from the switch hurdle
# --------------------------------------------------------------------------- #
def _two_names_one_bucket(hysteresis):
    # Sleeves that disagree, so confidence is below one and there is a margin to
    # spend. Two names that agree perfectly carry no doubt and no hysteresis —
    # which is the rule behaving correctly, not an exception to it.
    state = AR.ReliabilityState()
    candidates = [_candidate("HELD", percentile=97, vol=20.0, sleeves=(99, 40, 99, 40)),
                  _candidate("NEW", percentile=97, vol=19.0, sleeves=(99, 40, 99, 40))]
    rows = AR.confidence_rows(candidates, state, "d1", persistence=True, confidence=True)
    return AR.reliability_scores(rows, _Calibration({("US", "95-100"): 3.0}), CFG,
                                 as_of="2020-01-01", incumbents={"HELD"},
                                 hysteresis=hysteresis)


def test_without_hysteresis_a_tie_on_alpha_is_broken_by_downside_volatility():
    """The control's behaviour, and the reason this study exists: the two names
    carry the SAME expected alpha and the book still swaps them."""
    scored = {row["ticker"]: row for row in _two_names_one_bucket(False)}
    assert (scored["NEW"]["expectedGrossBenchmarkExcessPct"]
            == scored["HELD"]["expectedGrossBenchmarkExcessPct"])
    assert scored["NEW"]["score"] > scored["HELD"]["score"]


def test_with_hysteresis_a_tie_on_alpha_cannot_displace_an_incumbent():
    scored = {row["ticker"]: row for row in _two_names_one_bucket(True)}
    assert scored["HELD"]["score"] > scored["NEW"]["score"]


def test_the_margin_is_exactly_what_the_contraction_discarded():
    """The shrinkage and the hurdle are one quantity read twice, not two choices."""
    scored = _two_names_one_bucket(True)
    for row in scored:
        alpha = row["expectedGrossBenchmarkExcessPct"]
        assert row["uncertaintyMarginPct"] == pytest.approx(
            abs(alpha) - abs(row["reliableAlphaPct"]))


def test_a_fully_confident_name_receives_no_margin_at_all():
    state = AR.ReliabilityState()
    for index in range(3):
        AR.confidence_rows([_candidate("A", percentile=97, sleeves=(97, 97, 97, 97)),
                            _candidate("B", percentile=93, sleeves=(93, 93, 93, 93))],
                           state, f"d{index}", persistence=True, confidence=True)
    rows = AR.confidence_rows([_candidate("A", percentile=97, sleeves=(97, 97, 97, 97)),
                               _candidate("B", percentile=93, sleeves=(93, 93, 93, 93))],
                              state, "d3", persistence=True, confidence=True)
    steady = next(row for row in rows if row["ticker"] == "A")
    assert steady["signalConfidence"] == pytest.approx(1.0)
    scored = AR.reliability_scores([steady], _Calibration({("US", "95-100"): 3.0}), CFG,
                                   as_of="2020-01-01", incumbents={"A"}, hysteresis=True)
    assert scored[0]["uncertaintyMarginPct"] == pytest.approx(0.0)


def test_no_ladder_rung_charges_a_transaction_cost():
    """The cost hurdle is a different hypothesis and is reported outside the ladder."""
    manifest = AR.freeze_manifest()
    assert manifest["transactionCostHurdleInLadder"] is False
    assert AR.STACKED not in AR.LADDER
    assert manifest["reportedSeparately"] == AR.STACKED


def test_the_cost_hurdle_is_the_stacked_path_and_moves_a_second_axis():
    state = AR.ReliabilityState()
    rows = AR.confidence_rows([_candidate("HELD", region="KR", percentile=97)],
                              state, "d1", persistence=True, confidence=True)
    calibration = _Calibration({("KR", "95-100"): 3.0})
    plain = AR.reliability_scores(rows, calibration, CFG, as_of="2020-01-01",
                                  incumbents={"HELD"}, hysteresis=True)
    stacked = AR.reliability_scores(rows, calibration, CFG, as_of="2020-01-01",
                                    incumbents={"HELD"}, hysteresis=True, cost_hurdle=True)
    assert stacked[0]["decisionAlphaPct"] > plain[0]["decisionAlphaPct"]


# --------------------------------------------------------------------------- #
# Eligibility is a fact about the name, not a thing the rule can rescue
# --------------------------------------------------------------------------- #
def test_the_hysteresis_never_rescues_an_ineligible_incumbent():
    state = AR.ReliabilityState()
    blocked = _candidate("HELD")
    blocked["entryState"] = "AVOID"
    rows = AR.confidence_rows([blocked], state, "d1", persistence=True, confidence=True)
    scored = AR.reliability_scores(rows, _Calibration({("US", "95-100"): 3.0}), CFG,
                                   as_of="2020-01-01", incumbents={"HELD"},
                                   hysteresis=True)
    assert scored[0]["eligible"] is False
    assert "ENTRY_OR_RESEARCH_STATE_BLOCKS_SIZING" in scored[0]["exclusionCodes"]


def test_a_name_without_a_matured_calibration_is_excluded_not_scored_at_zero():
    state = AR.ReliabilityState()
    rows = AR.confidence_rows([_candidate("A")], state, "d1",
                              persistence=True, confidence=True)
    scored = AR.reliability_scores(rows, _Calibration({}), CFG, as_of="2020-01-01")
    assert scored[0]["eligible"] is False
    assert "MATURED_CALIBRATION_NOT_READY" in scored[0]["exclusionCodes"]
    assert scored[0]["score"] == -1e12


# --------------------------------------------------------------------------- #
# Diagnostics
# --------------------------------------------------------------------------- #
def _decision(date, *, retained, added, replaced, scored):
    return {"date": date, "retained": retained, "added": added, "replaced": replaced,
            "scored": scored}


def _row(ticker, score, alpha, percentile=97.0, confidence=0.5, cut=None):
    return {"ticker": ticker, "score": score, "eligible": True,
            "expectedGrossBenchmarkExcessPct": alpha, "alphaPercentile": percentile,
            "rawAlphaPercentile": percentile, "signalConfidence": confidence,
            "selectionExclusionCodes": cut}


def test_a_cut_between_two_names_with_the_same_alpha_is_counted_as_a_tie():
    decisions = [_decision("2020-01-01", retained=[], added=["A", "B"], replaced=[],
                           scored=[_row("A", 2.0, 3.0), _row("B", 1.5, 3.0),
                                   _row("C", 1.0, 3.0, cut=["BELOW_TARGET_COUNT_CUTOFF"])])]
    blob = AR.boundary_instability(decisions)
    assert blob["rebalancesMeasured"] == 1
    assert blob["tiedOnExpectedAlphaPct"] == pytest.approx(100.0)


def test_a_cut_with_a_real_alpha_difference_is_not_a_tie():
    decisions = [_decision("2020-01-01", retained=[], added=["A"], replaced=[],
                           scored=[_row("A", 2.0, 4.0),
                                   _row("C", 1.0, 1.0, cut=["BELOW_TARGET_COUNT_CUTOFF"])])]
    assert AR.boundary_instability(decisions)["tiedOnExpectedAlphaPct"] == pytest.approx(0.0)


def test_a_name_a_cap_stopped_is_not_the_ranking_s_marginal_reject():
    """Comparing the last held name against a capped one measures the
    diversification rules, not the ranking."""
    decisions = [_decision("2020-01-01", retained=[], added=["A"], replaced=[],
                           scored=[_row("A", 2.0, 4.0),
                                   _row("C", 1.9, 1.0,
                                        cut=["REGION_NAME_LIMIT"])])]
    blob = AR.boundary_instability(decisions)
    assert blob["available"] is False
    assert blob["rebalancesWhereEveryNearMissWasCapped"] == 1


def test_a_rebalance_that_holds_everything_has_no_cut_to_measure():
    decisions = [_decision("2020-01-01", retained=["A"], added=["B"], replaced=[],
                           scored=[_row("A", 2.0, 3.0), _row("B", 1.0, 3.0)])]
    blob = AR.boundary_instability(decisions)
    assert blob["available"] is False
    assert blob["rebalancesWhereEveryNearMissWasCapped"] == 1


def test_the_swap_is_paired_at_its_margin_and_scored_against_what_happened():
    decisions = [
        _decision("2020-01-01", retained=[], added=["OLD"], replaced=[],
                  scored=[_row("OLD", 2.0, 3.0)]),
        _decision("2020-02-01", retained=[], added=["NEW"], replaced=["OLD"],
                  scored=[_row("NEW", 2.5, 3.0), _row("OLD", 2.0, 3.0)]),
    ]
    priced = {"2020-02-01": {"NEW": {"excessReturn": -0.02},
                             "OLD": {"excessReturn": 0.01}}}
    blob = AR.replacement_anatomy(decisions, priced)
    assert blob["replacementsMeasured"] == 1
    assert blob["tiedOnExpectedAlphaPct"] == pytest.approx(100.0)
    assert blob["arrivingMinusDepartingExcess"]["meanPct"] == pytest.approx(-3.0)
    assert blob["whenTiedOnExpectedAlpha"]["observations"] == 1
    assert blob["whenSeparatedOnExpectedAlpha"]["available"] is False


def test_a_swap_the_cross_section_cannot_price_is_dropped_not_zeroed():
    decisions = [
        _decision("2020-01-01", retained=[], added=["OLD"], replaced=[],
                  scored=[_row("OLD", 2.0, 3.0)]),
        _decision("2020-02-01", retained=[], added=["NEW"], replaced=["OLD"],
                  scored=[_row("NEW", 2.5, 4.0), _row("OLD", 2.0, 3.0)]),
    ]
    blob = AR.replacement_anatomy(decisions, {})
    assert blob["replacementsMeasured"] == 1
    assert blob["arrivingMinusDepartingExcess"]["available"] is False


def test_an_incumbent_whose_percentile_barely_moved_and_was_dropped_is_counted():
    decisions = [
        _decision("2020-01-01", retained=[], added=["OLD"], replaced=[],
                  scored=[_row("OLD", 2.0, 3.0, percentile=97.0)]),
        _decision("2020-02-01", retained=[], added=["NEW"], replaced=["OLD"],
                  scored=[_row("NEW", 2.5, 3.0, percentile=98.0),
                          _row("OLD", 2.0, 3.0, percentile=96.5)]),
    ]
    blob = AR.replacement_anatomy(decisions, {})
    assert blob["incumbentsWhosePercentileMovedOnePointOrLess"] == 1
    assert blob["ofThoseReplacedPct"] == pytest.approx(100.0)


def test_nothing_replaced_is_unavailable_rather_than_a_zero_rate():
    assert AR.replacement_anatomy([], {})["available"] is False
    assert AR.boundary_instability([])["available"] is False


def test_an_empty_spread_reports_absence_rather_than_zero():
    assert AR._spread([])["available"] is False
    assert AR._outcome_block([])["available"] is False


# --------------------------------------------------------------------------- #
# Freeze manifest
# --------------------------------------------------------------------------- #
def test_the_ladder_carries_its_own_control_and_moves_one_axis_per_rung():
    manifest = AR.freeze_manifest()
    assert AR.LADDER[0] == AR.CONTROL
    assert manifest["axisPerRung"][AR.CONTROL] == "NONE_THIS_IS_THE_BASELINE"
    assert len(manifest["axisPerRung"]) == len(AR.LADDER)


def test_the_study_adds_no_factor_and_moves_no_factor_weight():
    manifest = AR.freeze_manifest()
    assert manifest["factorsAdded"] == []
    assert manifest["factorWeightsChanged"] is False


def test_evidence_coverage_is_refused_as_a_confidence_weight_with_its_reason():
    """It is already multiplied into alpha before the percentile is taken."""
    manifest = AR.freeze_manifest()
    assert "evidenceCoverage" in manifest["confidenceExclusions"]
    assert "evidenceCoverage" not in manifest["confidenceComponents"]


def test_no_rung_claims_to_have_beaten_random():
    """No permutation null is run here, so nothing may be described as beating one."""
    assert AR.freeze_manifest()["permutationNullRun"] is False


def test_the_manifest_promotes_nothing():
    manifest = AR.freeze_manifest()
    assert manifest["promotionEligible"] is False
    assert manifest["liveValidated"] is False
    assert manifest["productionChanged"] is False


def test_run_rung_refuses_a_name_it_does_not_know():
    with pytest.raises(ValueError):
        AR.run_rung("NOT_A_RUNG", contexts={}, calibrator=None, calendar=[],
                    cfg_pf={}, valuation=None)


# --------------------------------------------------------------------------- #
# Structural diagnostics: observational only, and they must stay that way
# --------------------------------------------------------------------------- #
def _scored(ticker, score, *, alpha=3.0, percentile=97.0, vol=20.0, confidence=0.5,
            sleeves=None, region="US", sector="Tech", state="ACCUMULATE_GRADUALLY",
            multiplier=1.0, cut=None, codes=None, decision=None, reliable=None,
            margin=None):
    return {
        "ticker": ticker, "region": region, "sector": sector, "score": score,
        "eligible": not codes, "exclusionCodes": list(codes or []),
        "selectionExclusionCodes": cut,
        "expectedGrossBenchmarkExcessPct": alpha,
        "decisionAlphaPct": alpha if decision is None else decision,
        "reliableAlphaPct": alpha * confidence if reliable is None else reliable,
        "uncertaintyMarginPct": (abs(alpha) * (1 - confidence) if margin is None else margin),
        "alphaPercentile": percentile, "rawAlphaPercentile": percentile,
        "downsideVolPct": vol, "signalConfidence": confidence,
        "factorPercentiles": dict(sleeves or {"momentum": 80, "value": 70,
                                              "quality": 75, "lowvol": 60}),
        "entryState": state, "entryStateMultiplier": multiplier,
        "eligibilityCodes": tuple(codes or ()),
    }


def test_spearman_averages_ties_and_abstains_without_spread():
    """The calibration hands most of this pool one alpha, so ties are the norm."""
    assert AR._spearman([1, 2, 3, 4], [1, 2, 3, 4]) == pytest.approx(1.0)
    assert AR._spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)
    assert AR._spearman([5, 5, 5, 5], [1, 2, 3, 4]) is None
    assert AR._spearman([1, 2], [1, 2]) is None
    tied = AR._average_ranks(np.array([10.0, 10.0, 20.0, 30.0]))
    assert list(tied) == [0.5, 0.5, 2.0, 3.0]


def test_risk_dominance_sees_the_denominator_when_alpha_is_a_constant():
    """Every name shares one bucket, so only downside volatility can order them."""
    rows = [_scored("A", 0.20, alpha=3.0, vol=15.0), _scored("B", 0.15, alpha=3.0, vol=20.0),
            _scored("C", 0.12, alpha=3.0, vol=25.0), _scored("D", 0.10, alpha=3.0, vol=30.0)]
    blob = AR.risk_dominance([_decision("2020-01-01", retained=[], added=["A", "B"],
                                        replaced=[], scored=rows)])
    assert blob["available"]
    assert blob["scoreVsCalibratedAlphaSpearman"]["available"] is False
    assert blob["scoreVsDownsideVolSpearman"]["mean"] == pytest.approx(-1.0)
    assert blob["downsideVolPctSelected"]["mean"] < blob["downsideVolPctRejected"]["mean"]


def test_a_name_a_cap_stopped_is_not_counted_as_dropped_by_its_volatility():
    """A cap is not a risk estimate and must not be attributed to one."""
    rows = [_scored("TOP", 0.05, percentile=100.0, vol=40.0,
                    cut=["REGION_NAME_LIMIT"]),
            _scored("MID", 0.08, percentile=95.0, vol=25.0,
                    cut=["BELOW_TARGET_COUNT_CUTOFF"]),
            _scored("HELD", 0.20, percentile=91.0, vol=10.0)]
    blob = AR.risk_dominance([_decision("2020-01-01", retained=[], added=["HELD"],
                                        replaced=[], scored=rows)])
    assert blob["droppedDespiteTopAlphaAndAboveMedianRisk"] == 0
    assert blob["heldDespiteLowerAlphaAndBelowMedianRisk"] == 1


def test_entry_state_transitions_are_counted_per_name_across_blocks():
    first = [_scored("A", 0.2, state="ACCUMULATE_GRADUALLY", multiplier=1.0, percentile=97.0)]
    second = [_scored("A", 0.1, state="WATCH", multiplier=0.5, percentile=96.5)]
    blob = AR.entry_state_dynamics([
        _decision("2020-01-01", retained=[], added=["A"], replaced=[], scored=first),
        _decision("2020-02-01", retained=[], added=["B"], replaced=["A"], scored=second)])
    assert blob["transitionsObserved"] == 1
    assert blob["byTransition"]["ACCUMULATE_GRADUALLY -> WATCH"] == 1
    # The step halved while the name's own percentile moved half a point.
    assert blob["departuresWhereTheStepFellAndAlphaMovedOnePointOrLess"] == 1


def test_a_state_that_moves_on_an_untouched_name_changed_nothing():
    first = [_scored("A", 0.2, state="WATCH", multiplier=0.5)]
    second = [_scored("A", 0.2, state="ACCUMULATE_GRADUALLY", multiplier=1.0)]
    blob = AR.entry_state_dynamics([
        _decision("2020-01-01", retained=[], added=["A"], replaced=[], scored=first),
        _decision("2020-02-01", retained=["A"], added=[], replaced=[], scored=second)])
    assert blob["transitionsObserved"] == 1
    assert blob["transitionsCoincidingWithASwapPct"] == pytest.approx(0.0)


def test_region_cap_binding_measures_the_override_against_the_marginal_holding():
    rows = [_scored("KR1", 0.30, region="KR", decision=4.0),
            _scored("KR2", 0.25, region="KR", decision=3.5),
            _scored("KR3", 0.20, region="KR", decision=3.0),
            _scored("KR4", 0.18, region="KR", decision=2.8, cut=["REGION_NAME_LIMIT"]),
            _scored("US1", 0.10, region="US", decision=1.0)]
    decision = _decision("2020-01-01", retained=[], added=["KR1", "KR2", "KR3", "US1"],
                         replaced=[], scored=rows)
    decision["regionByTicker"] = {"KR1": "KR", "KR2": "KR", "KR3": "KR", "US1": "US"}
    blob = AR.region_cap_binding([decision], CFG)
    assert blob["rebalancesWhereTheRegionCapStoppedAName"] == 1
    assert blob["rebalancesWhereACappedNameOutscoredOneTaken"] == 1
    assert blob["decisionAlphaGapAtTheOverridePp"]["mean"] == pytest.approx(1.8)
    # A region absent from the top-N is absent from the tally, not a zero
    # reading: it was never in the ordering this figure describes.
    assert blob["topNByScoreWithCapsLiftedByRegion"] == {"KR": 4}
    assert blob["heldNameDatesByRegion"] == {"KR": 3, "US": 1}


def test_breadth_readiness_counts_names_whose_doubt_exceeds_their_claim():
    rows = [_scored("A", 0.30, alpha=4.0, confidence=0.9),
            _scored("B", 0.20, alpha=4.0, confidence=0.4),
            _scored("C", 0.10, alpha=4.0, confidence=0.4)]
    blob = AR.breadth_readiness([_decision("2020-01-01", retained=[], added=["A"],
                                           replaced=[], scored=rows)])
    # 0.4 x 4.0 = 1.6 against a discarded 2.4, so B and C are near neutral.
    assert blob["namesInTopTenWhoseDoubtExceedsTheirClaim"]["mean"] == pytest.approx(2.0)
    assert blob["targetNamesUnchanged"] == 5


def test_breadth_readiness_counts_ties_inside_and_just_below_the_top_five():
    rows = [_scored(name, 1.0 - index / 100, alpha=3.0)
            for index, name in enumerate("ABCDEFG")]
    blob = AR.breadth_readiness([_decision("2020-01-01", retained=[],
                                           added=list("ABCDE"), replaced=[], scored=rows)])
    assert blob["tiedPairsInsideTheTopFive"]["mean"] == pytest.approx(4.0)
    assert blob["ranksSixToTenTiedWithTheFifthName"]["mean"] == pytest.approx(2.0)


def test_departure_causes_attribute_each_name_once_and_sum_to_the_departures():
    rows = [_scored("BLOCKED", 0.1, codes=["ENTRY_OR_RESEARCH_STATE_BLOCKS_SIZING"]),
            _scored("CAPPED", 0.2, cut=["REGION_NAME_LIMIT"]),
            _scored("OUTRANKED", 0.05, cut=["BELOW_TARGET_COUNT_CUTOFF"])]
    blob = AR.departure_causes([_decision(
        "2020-01-01", retained=[], added=[],
        replaced=["BLOCKED", "CAPPED", "OUTRANKED", "GONE"], scored=rows)])
    assert blob["departuresMeasured"] == 4
    assert sum(blob["byCause"].values()) == 4
    assert blob["byCause"]["LEFT_THE_RESEARCH_POOL"] == 1
    assert blob["byCause"]["ENTRY_OR_RESEARCH_STATE_TURNED_BLOCKING"] == 1
    assert blob["byCause"]["REGION_CAP"] == 1
    assert blob["byCause"]["OUTRANKED_AT_THE_CUT"] == 1


def test_production_selection_cannot_contaminate_the_eligibility_facts():
    """`select_portfolio_by_scores` shallow copies each row, so its cut codes
    land in the CALLER's `exclusionCodes` list. Without a copy that cannot be
    appended to, a name the book was simply too full to reach comes back
    looking like a name that was ineligible on its own facts."""
    from pipeline import kelly_portfolio as KP

    state = AR.ReliabilityState()
    candidates = [_candidate(name, percentile=97, vol=10.0 + index)
                  for index, name in enumerate("ABCDEFGH")]
    rows = AR.confidence_rows(candidates, state, "d1", persistence=True, confidence=True)
    scored = AR.reliability_scores(rows, _Calibration({("US", "95-100"): 3.0}), CFG,
                                   as_of="2020-01-01")
    KP.selection_and_baseline(rows, CFG, None, scored=scored, method="TEST")

    contaminated = {code for row in scored for code in row["exclusionCodes"]}
    pristine = {code for row in scored for code in row["eligibilityCodes"]}
    selection_codes = {"BELOW_TARGET_COUNT_CUTOFF", "SECTOR_NAME_LIMIT", "REGION_NAME_LIMIT"}
    assert contaminated & selection_codes                    # production appended into ours
    assert pristine == set()                                 # the facts stayed facts
    assert all(isinstance(row["eligibilityCodes"], tuple) for row in scored)


def test_a_name_the_book_was_too_full_to_reach_is_not_called_ineligible():
    rows = [dict(_scored("FULL", 0.05, cut=["BELOW_TARGET_COUNT_CUTOFF"]),
                 exclusionCodes=["BELOW_TARGET_COUNT_CUTOFF"], eligibilityCodes=())]
    blob = AR.departure_causes([_decision("2020-01-01", retained=[], added=[],
                                          replaced=["FULL"], scored=rows)])
    assert blob["byCause"] == {"OUTRANKED_AT_THE_CUT": 1}


def test_the_diagnostics_never_touch_the_constraints_they_measure():
    """They read the paths the ladder produced; they do not relax anything."""
    manifest = AR.freeze_manifest()
    assert manifest["structuralDiagnosticsAreObservationalOnly"] is True
    assert set(manifest["structuralDiagnostics"]) == {
        "risk_dominance", "entry_state_dynamics", "region_cap_binding",
        "breadth_readiness", "departure_causes"}
    held = " ".join(manifest["constraintsHeldFixedByTheseDiagnostics"])
    for token in ("lowvol", "downside-volatility denominator", "maxNamesPerRegion",
                  "targetNames", "entry-state"):
        assert token in held


def test_adding_the_diagnostics_did_not_add_a_rung_or_a_parameter():
    manifest = AR.freeze_manifest()
    assert list(manifest["ladder"]) == list(AR.LADDER)
    assert manifest["parametersIntroduced"] == []
    assert manifest["promotionEligible"] is False


def test_every_diagnostic_reports_absence_rather_than_a_zero_reading():
    for blob in (AR.risk_dominance([]), AR.entry_state_dynamics([]),
                 AR.region_cap_binding([], CFG), AR.breadth_readiness([]),
                 AR.departure_causes([])):
        assert blob["available"] is False
