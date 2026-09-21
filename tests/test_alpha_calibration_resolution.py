"""The rescue must never cross calibration levels, and a no-op must be provably a no-op.

Three ways this study could fool itself: reordering candidate ROWS and
trusting `select_portfolio_by_scores` to respect that order (it always
re-sorts by score and would silently erase the reordering), letting a swap
cross from one calibrated expected-alpha level into another, or mutating the
caller's rows the way `select_portfolio_by_scores` itself is documented to.
All three are tested directly.
"""
from __future__ import annotations

import pytest

from pipeline import alpha_calibration_resolution as C
from pipeline import kelly_portfolio as KP


def _row(ticker, *, score, region="US", sector="Tech", bucket, percentile,
        alpha=0.5, eligible=True, exclusion=None):
    return {
        "ticker": ticker, "region": region, "sector": sector, "score": score,
        "convictionScore": score, "alphaPercentile": percentile,
        "calibrationBucket": bucket, "expectedGrossBenchmarkExcessPct": alpha,
        "eligible": eligible, "exclusionCodes": list(exclusion or []),
        "eligibilityCodes": tuple(exclusion or ()),
    }


def _cfg(target=2, per_sector=2, per_region=2):
    return {"selection": {"targetNames": target, "minNames": 1,
                          "maxNamesPerSector": per_sector, "maxNamesPerRegion": per_region}}


# --------------------------------------------------------------------------- #
# rescue_scores: the core mechanism
# --------------------------------------------------------------------------- #
def test_rescue_reassigns_score_values_not_row_identity():
    # A (bucket X, score 1.0, percentile 90) and B (bucket X, score 0.5,
    # percentile 99): same calibration level, B has the higher percentile.
    a = _row("A", score=1.0, bucket="90-95", percentile=90)
    b = _row("B", score=0.5, bucket="90-95", percentile=99)
    rescued, swaps = C.rescue_scores([a, b])
    by_ticker = {r["ticker"]: r for r in rescued}
    # B now carries the score that was at position 0 (1.0); A carries what
    # was at position 1 (0.5) -- the SCORE VALUES at each position are
    # unchanged, only which ticker holds them.
    assert by_ticker["B"]["score"] == 1.0
    assert by_ticker["A"]["score"] == 0.5
    # Both positions change occupant in a full 2-way swap.
    assert len(swaps) == 2
    by_position = {s["position"]: s for s in swaps}
    assert by_position[0]["controlTicker"] == "A" and by_position[0]["rescueTicker"] == "B"
    assert by_position[1]["controlTicker"] == "B" and by_position[1]["rescueTicker"] == "A"


def test_rescue_never_crosses_calibration_levels():
    # A: bucket Y, expected alpha 0.60, percentile 96 (Control's #1 by score).
    # B: bucket Z, expected alpha 0.30, percentile 99 (Control's #2 by score,
    # lower calibration level). B must NEVER outrank A despite the higher
    # percentile, because they are in different groups.
    a = _row("A", score=2.0, bucket="95-100", percentile=96, alpha=0.60)
    b = _row("B", score=1.0, bucket="90-95", percentile=99, alpha=0.30)
    rescued, swaps = C.rescue_scores([a, b])
    assert swaps == []
    ordered = sorted(rescued, key=lambda r: -r["score"])
    assert [r["ticker"] for r in ordered] == ["A", "B"]


def test_a_singleton_group_is_never_touched():
    a = _row("A", score=1.0, bucket="95-100", percentile=97)
    b = _row("B", score=0.5, bucket="90-95", percentile=99)
    rescued, swaps = C.rescue_scores([a, b])
    assert swaps == []
    by_ticker = {r["ticker"]: r for r in rescued}
    assert by_ticker["A"]["score"] == 1.0
    assert by_ticker["B"]["score"] == 0.5


def test_ties_on_percentile_fall_back_to_original_stable_order():
    a = _row("A", score=1.0, bucket="X", percentile=95)
    b = _row("B", score=0.9, bucket="X", percentile=95)
    c = _row("C", score=0.8, bucket="X", percentile=99)
    rescued, swaps = C.rescue_scores([a, b, c])
    ordered = sorted(rescued, key=lambda r: -r["score"])
    # C (percentile 99) takes the top slot; A and B (tied at 95) keep their
    # ORIGINAL relative order (A before B) in the remaining two slots.
    assert [r["ticker"] for r in ordered] == ["C", "A", "B"]


def test_ineligible_rows_are_never_grouped_even_with_a_shared_bucket():
    a = _row("A", score=1.0, bucket="95-100", percentile=91)
    blocked = _row("Z", score=-1e12, bucket="95-100", percentile=99,
                   eligible=False, exclusion=["ENTRY_OR_RESEARCH_STATE_BLOCKS_SIZING"])
    rescued, swaps = C.rescue_scores([a, blocked])
    assert swaps == []


def test_a_row_with_no_bucket_is_never_grouped():
    a = _row("A", score=1.0, bucket=None, percentile=91)
    b = _row("B", score=0.5, bucket=None, percentile=99)
    a["calibrationBucket"] = None
    b["calibrationBucket"] = None
    rescued, swaps = C.rescue_scores([a, b])
    assert swaps == []


def test_rescue_does_not_mutate_the_input_rows():
    a = _row("A", score=1.0, bucket="X", percentile=90)
    b = _row("B", score=0.5, bucket="X", percentile=99)
    before_a, before_b = dict(a), dict(b)
    C.rescue_scores([a, b])
    assert a == before_a and b == before_b
    assert a["exclusionCodes"] is not None  # untouched original list object


def test_rescue_output_rows_have_independent_exclusion_lists():
    a = _row("A", score=1.0, bucket="X", percentile=90)
    b = _row("B", score=0.5, bucket="X", percentile=99)
    rescued, _ = C.rescue_scores([a, b])
    rescued[0]["exclusionCodes"].append("SOMETHING")
    assert a["exclusionCodes"] == [] and b["exclusionCodes"] == []


def test_three_way_group_orders_fully_by_percentile_descending():
    rows = [
        _row("LOW", score=3.0, bucket="X", percentile=91),
        _row("MID", score=2.0, bucket="X", percentile=95),
        _row("HIGH", score=1.0, bucket="X", percentile=99),
    ]
    rescued, swaps = C.rescue_scores(rows)
    ordered = sorted(rescued, key=lambda r: -r["score"])
    assert [r["ticker"] for r in ordered] == ["HIGH", "MID", "LOW"]
    # Positions (scores 3.0/2.0/1.0) are exactly Control's own values.
    assert [r["score"] for r in ordered] == [3.0, 2.0, 1.0]
    # A full 3-way reversal only changes the identity at the two OUTER
    # positions -- the middle rank (MID) is already correctly placed.
    assert len(swaps) == 2


def test_a_group_split_across_non_adjacent_positions_still_only_swaps_within_it():
    # X-bucket members at Control positions 0 and 2; a Y-bucket singleton
    # sits at position 1 in between. The Y row must never move.
    rows = [
        _row("X_LOW", score=3.0, bucket="X", percentile=90),
        _row("Y_ONLY", score=2.0, bucket="Y", percentile=98),
        _row("X_HIGH", score=1.0, bucket="X", percentile=99),
    ]
    rescued, swaps = C.rescue_scores(rows)
    by_ticker = {r["ticker"]: r for r in rescued}
    assert by_ticker["Y_ONLY"]["score"] == 2.0  # untouched, still the middle value
    ordered = sorted(rescued, key=lambda r: -r["score"])
    assert [r["ticker"] for r in ordered] == ["X_HIGH", "Y_ONLY", "X_LOW"]


# --------------------------------------------------------------------------- #
# verify_reproduces_control: the mechanical proof, on a small fixture
# --------------------------------------------------------------------------- #
def test_degenerate_rescue_reproduces_control_selection():
    candidates = [{"ticker": "A", "region": "US"}, {"ticker": "B", "region": "US"},
                 {"ticker": "C", "region": "US"}]
    scored = [
        _row("A", score=3.0, bucket="X", percentile=90),
        _row("B", score=2.0, bucket="Y", percentile=95),
        _row("C", score=1.0, bucket="Z", percentile=99),
    ]
    cfg = _cfg(target=2, per_sector=3, per_region=3)
    selected, _ = KP.select_portfolio_by_scores(candidates, scored, cfg, method="TEST")
    control_tickers = {c["ticker"] for c in selected}
    # Must not raise.
    C.verify_reproduces_control(candidates, scored, cfg, control_tickers)


def test_verify_raises_on_a_genuine_disagreement():
    candidates = [{"ticker": "A", "region": "US"}, {"ticker": "B", "region": "US"}]
    scored = [_row("A", score=1.0, bucket="X", percentile=90),
             _row("B", score=0.5, bucket="Y", percentile=95)]
    cfg = _cfg(target=2, per_sector=3, per_region=3)
    with pytest.raises(ValueError, match="SORT_KEY_REPLICATION_DISAGREES_WITH_CONTROL"):
        C.verify_reproduces_control(candidates, scored, cfg, {"WRONG_TICKER"})


# --------------------------------------------------------------------------- #
# assert_noop_blocks_match_control
# --------------------------------------------------------------------------- #
def test_noop_block_check_passes_when_no_swaps_and_sets_agree():
    control = [{"date": "2020-01-01", "retained": ["A"], "added": ["B"]}]
    rescue = [{"date": "2020-01-01", "retained": ["A"], "added": ["B"], "swaps": []}]
    C.assert_noop_blocks_match_control(control, rescue)  # must not raise


def test_noop_block_check_raises_on_disagreement_with_no_swaps():
    control = [{"date": "2020-01-01", "retained": ["A"], "added": ["B"]}]
    rescue = [{"date": "2020-01-01", "retained": ["A"], "added": ["C"], "swaps": []}]
    with pytest.raises(ValueError, match="NOOP_BLOCK_DISAGREES_WITH_CONTROL"):
        C.assert_noop_blocks_match_control(control, rescue)


def test_noop_block_check_skips_blocks_that_actually_swapped():
    control = [{"date": "2020-01-01", "retained": ["A"], "added": ["B"]}]
    rescue = [{"date": "2020-01-01", "retained": ["A"], "added": ["C"],
              "swaps": [{"controlTicker": "B", "rescueTicker": "C"}]}]
    C.assert_noop_blocks_match_control(control, rescue)  # skipped, must not raise


# --------------------------------------------------------------------------- #
# information_loss_diagnostic (Stage A)
# --------------------------------------------------------------------------- #
def test_information_loss_counts_eligible_name_dates_and_levels():
    decisions = [{
        "date": "2020-01-01",
        "scored": [
            _row("A", score=1.0, bucket="95-100", percentile=96),
            _row("B", score=0.9, bucket="95-100", percentile=99),
            _row("C", score=0.5, bucket="90-95", percentile=91),
        ],
    }]
    blob = C.information_loss_diagnostic(decisions)
    assert blob["totalEligibleNameDates"] == 3
    assert blob["distinctCalibrationLevels"] == 2
    assert blob["largestLevelShare"] == pytest.approx(2 / 3 * 100, abs=0.01)
    assert blob["withinLevelPercentileRange"]["observations"] == 1
    assert blob["withinLevelPercentileRange"]["mean"] == pytest.approx(3.0)


def test_information_loss_excludes_ineligible_rows():
    decisions = [{
        "date": "2020-01-01",
        "scored": [
            _row("A", score=1.0, bucket="95-100", percentile=96),
            _row("Z", score=-1e12, bucket="95-100", percentile=99, eligible=False),
        ],
    }]
    blob = C.information_loss_diagnostic(decisions)
    assert blob["totalEligibleNameDates"] == 1


def test_information_loss_on_no_decisions_reports_absence():
    blob = C.information_loss_diagnostic([])
    assert blob["totalEligibleNameDates"] == 0
    assert blob["distinctCalibrationLevels"] == 0
    assert blob["largestLevelShare"] is None


# --------------------------------------------------------------------------- #
# within_calibration_information (Stage B, evaluation only)
# --------------------------------------------------------------------------- #
def test_within_calibration_information_pairwise_concordance():
    decisions = [{
        "date": "2020-01-01",
        "scored": [
            _row("HIGH", score=1.0, bucket="X", percentile=99),
            _row("LOW", score=0.9, bucket="X", percentile=90),
        ],
    }]
    priced = {"2020-01-01": {"HIGH": {"excessReturn": 0.05}, "LOW": {"excessReturn": 0.01}}}
    blob = C.within_calibration_information(decisions, priced)
    assert blob["pairwiseConcordance"]["pairsCompared"] == 1
    assert blob["pairwiseConcordance"]["higherPercentileRealisedBetterPct"] == 100.0


def test_within_calibration_information_discordant_pair():
    decisions = [{
        "date": "2020-01-01",
        "scored": [
            _row("HIGH", score=1.0, bucket="X", percentile=99),
            _row("LOW", score=0.9, bucket="X", percentile=90),
        ],
    }]
    priced = {"2020-01-01": {"HIGH": {"excessReturn": 0.01}, "LOW": {"excessReturn": 0.05}}}
    blob = C.within_calibration_information(decisions, priced)
    assert blob["pairwiseConcordance"]["higherPercentileRealisedBetterPct"] == 0.0


def test_within_calibration_information_ignores_cross_group_pairs():
    decisions = [{
        "date": "2020-01-01",
        "scored": [
            _row("A", score=1.0, bucket="X", percentile=99),
            _row("B", score=0.5, bucket="Y", percentile=50),
        ],
    }]
    priced = {"2020-01-01": {"A": {"excessReturn": 0.01}, "B": {"excessReturn": 0.05}}}
    blob = C.within_calibration_information(decisions, priced)
    assert blob["pairwiseConcordance"]["pairsCompared"] == 0


def test_within_calibration_information_missing_price_excludes_the_name():
    decisions = [{
        "date": "2020-01-01",
        "scored": [
            _row("HIGH", score=1.0, bucket="X", percentile=99),
            _row("LOW", score=0.9, bucket="X", percentile=90),
        ],
    }]
    blob = C.within_calibration_information(decisions, {})  # nothing priced
    assert blob["available"] is False
    assert blob["pairwiseConcordance"]["pairsCompared"] == 0


def test_within_calibration_information_half_split_is_median_rank_not_a_threshold():
    decisions = [{
        "date": "2020-01-01",
        "scored": [
            _row("A", score=1.0, bucket="X", percentile=99),
            _row("B", score=0.9, bucket="X", percentile=95),
            _row("C", score=0.8, bucket="X", percentile=90),
            _row("D", score=0.7, bucket="X", percentile=85),
        ],
    }]
    priced = {"2020-01-01": {"A": {"excessReturn": 0.10}, "B": {"excessReturn": 0.08},
                             "C": {"excessReturn": 0.02}, "D": {"excessReturn": 0.00}}}
    blob = C.within_calibration_information(decisions, priced)
    assert blob["topHalfMeanForwardExcessPct"] == pytest.approx(9.0, abs=1e-6)
    assert blob["bottomHalfMeanForwardExcessPct"] == pytest.approx(1.0, abs=1e-6)
    assert blob["topMinusBottomPp"] == pytest.approx(8.0, abs=1e-6)


# --------------------------------------------------------------------------- #
# tied_swap_ordinal_detail
# --------------------------------------------------------------------------- #
def test_tied_swap_detail_only_includes_swaps_tied_on_calibrated_alpha():
    scored = {
        "ARRIVE": _row("ARRIVE", score=0.9, bucket="X", percentile=96, alpha=0.5),
        "DEPART": _row("DEPART", score=1.0, bucket="X", percentile=90, alpha=0.5),
    }
    decisions = [{"date": "2020-01-01", "scored": list(scored.values()),
                 "added": ["ARRIVE"], "replaced": ["DEPART"]}]
    priced = {"2020-01-01": {"ARRIVE": {"excessReturn": 0.03}, "DEPART": {"excessReturn": 0.01}}}
    blob = C.tied_swap_ordinal_detail(decisions, priced)
    assert blob["swapsMeasured"] == 1
    assert blob["percentileGap"]["mean"] == pytest.approx(6.0)


def test_tied_swap_detail_excludes_swaps_separated_on_calibrated_alpha():
    scored = {
        "ARRIVE": _row("ARRIVE", score=0.9, bucket="X", percentile=96, alpha=0.9),
        "DEPART": _row("DEPART", score=1.0, bucket="Y", percentile=90, alpha=0.3),
    }
    decisions = [{"date": "2020-01-01", "scored": list(scored.values()),
                 "added": ["ARRIVE"], "replaced": ["DEPART"]}]
    blob = C.tied_swap_ordinal_detail(decisions, {})
    assert blob["swapsMeasured"] == 0


# --------------------------------------------------------------------------- #
# cascade_attribution
# --------------------------------------------------------------------------- #
def test_cascade_attribution_classifies_a_direct_swap():
    control = [{"date": "2020-01-01", "retained": [], "added": ["A"]}]
    rescue = [{
        "date": "2020-01-01", "retained": [], "added": ["B"],
        "swaps": [{"controlTicker": "A", "rescueTicker": "B", "region": "US",
                  "bucket": "X", "position": 0}],
    }]
    blob = C.cascade_attribution(control, rescue)
    assert blob["directWithinCalibrationReorder"] == 2  # both A (removed) and B (added)
    assert blob["regionCapCascade"] == 0


def test_cascade_attribution_region_cascade_is_measured_not_assumed():
    # A same-region swap whose held-set region shape is preserved: no cascade.
    control_same = {"date": "2020-01-01", "retained": [], "added": ["A", "B"],
                    "regionByTicker": {"A": "US", "B": "KR"}}
    rescue_same = {
        "date": "2020-01-01", "retained": [], "added": ["A", "C"],
        "regionByTicker": {"A": "US", "C": "KR"},
        "swaps": [{"controlTicker": "B", "rescueTicker": "C", "region": "KR",
                  "bucket": "X", "position": 1}],
    }
    blob_same = C.cascade_attribution([control_same], [rescue_same])
    assert blob_same["regionCapCascade"] == 0
    assert blob_same["directWithinCalibrationReorder"] == 2

    # The same shape of swap, but the arriving name's own region differs from
    # what it replaced -- the held set's regional shape changes, and that is
    # what the field measures: not the swap itself, but its downstream effect
    # on the book's region composition.
    control_shift = {"date": "2020-02-01", "retained": [], "added": ["A", "B"],
                     "regionByTicker": {"A": "US", "B": "KR"}}
    rescue_shift = {
        "date": "2020-02-01", "retained": [], "added": ["A", "C"],
        "regionByTicker": {"A": "US", "C": "US"},
        "swaps": [{"controlTicker": "B", "rescueTicker": "C", "region": "KR",
                  "bucket": "X", "position": 1}],
    }
    blob_shift = C.cascade_attribution([control_shift], [rescue_shift])
    assert blob_shift["regionCapCascade"] == 1


def test_cascade_attribution_on_no_changes_reports_zero():
    control = [{"date": "2020-01-01", "retained": ["A"], "added": []}]
    rescue = [{"date": "2020-01-01", "retained": ["A"], "added": [], "swaps": []}]
    blob = C.cascade_attribution(control, rescue)
    assert blob["totalNameDatesChanged"] == 0


# --------------------------------------------------------------------------- #
# Freeze manifest
# --------------------------------------------------------------------------- #
def test_the_ladder_carries_alpha_reliability_s_own_control():
    from pipeline import alpha_reliability as AR
    assert C.LADDER[0] == C.CONTROL == AR.CONTROL


def test_manifest_declares_the_axis_and_no_new_parameters():
    manifest = C.freeze_manifest()
    assert manifest["noNewParameters"] is True
    assert manifest["noThresholdTuning"] is True
    assert manifest["neverCrossesCalibrationLevels"] is True
    assert manifest["eligibleRowsOnly"] is True
    assert manifest["permutationNullRun"] is False
    assert manifest["promotionEligible"] is False
    assert manifest["liveValidated"] is False
    assert manifest["productionChanged"] is False


def test_manifest_declares_downstream_mechanisms_unchanged():
    manifest = C.freeze_manifest()
    for key in ("calibrationTableUnchanged", "bucketEdgesUnchanged",
               "factorWeightsUnchanged", "downsideVolDenominatorUnchanged",
               "entryLogicUnchanged", "regionSectorCapsUnchanged"):
        assert manifest[key] is True
    assert manifest["targetNamesUnchanged"] == 5
