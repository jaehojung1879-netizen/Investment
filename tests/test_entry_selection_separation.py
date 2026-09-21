"""The throttle must move from the SELECTION score to the WEIGHT, and nowhere else.

Three ways this study could fool itself: leaving the throttle partially in the
score (so selection is not actually alpha-only), redistributing the capital a
throttled name gives up to other names (which would be a second, unregistered
axis), or letting a blocking state (multiplier 0) slip from an eligibility
exclusion into merely a very small weight. All three are tested directly.
"""
from __future__ import annotations

from pipeline import entry_selection_separation as ES
from pipeline import kelly_portfolio as KP


# --------------------------------------------------------------------------- #
# _alpha_only_score / entry_weighted_scores
# --------------------------------------------------------------------------- #
def _row(ticker, *, score, state, eligible=True, exclusion=None, entry_state="ACCUMULATE"):
    return {"ticker": ticker, "region": "US", "sector": "Tech", "score": score,
            "convictionScore": score, "eligible": eligible,
            "exclusionCodes": list(exclusion or []),
            "entryStateMultiplier": state, "entryState": entry_state}


def test_alpha_only_score_divides_out_the_throttle_exactly():
    row = _row("A", score=0.6, state=0.5, entry_state="WATCH")
    assert ES._alpha_only_score(row) == 1.2


def test_alpha_only_score_leaves_accumulate_unchanged():
    row = _row("A", score=0.8, state=1.0)
    assert ES._alpha_only_score(row) == 0.8


def test_alpha_only_score_untouched_when_state_blocks_the_row():
    row = _row("A", score=-1e12, state=0.0, eligible=False,
               exclusion=["ENTRY_OR_RESEARCH_STATE_BLOCKS_SIZING"], entry_state="EVENT_RISK")
    assert ES._alpha_only_score(row) == -1e12


def test_entry_weighted_scores_does_not_mutate_the_input_rows_exclusion_list():
    original = _row("A", score=0.6, state=0.5, entry_state="WATCH")
    out = ES.entry_weighted_scores([original])
    out[0]["exclusionCodes"].append("SOMETHING_SELECTION_ADDED")
    assert original["exclusionCodes"] == []


def test_entry_weighted_scores_returns_new_row_objects():
    original = _row("A", score=0.6, state=0.5, entry_state="WATCH")
    out = ES.entry_weighted_scores([original])
    assert out[0] is not original
    assert out[0]["score"] == 1.2
    assert original["score"] == 0.6


# --------------------------------------------------------------------------- #
# weight_throttle_summary
# --------------------------------------------------------------------------- #
def test_weight_throttle_summary_counts_only_names_below_full_multiplier():
    decisions = [{
        "retained": ["A"], "added": ["B", "C"],
        "entryStateMultiplierByTicker": {"A": 1.0, "B": 0.5, "C": 0.25},
    }]
    blob = ES.weight_throttle_summary(decisions)
    assert blob["heldNameDates"] == 3
    assert blob["throttledNameDates"] == 2
    assert blob["throttledNameDatesPct"] == 66.67
    assert blob["unapproachedWeightPctWhenThrottled"]["observations"] == 2


def test_weight_throttle_summary_on_no_decisions_reports_absence():
    blob = ES.weight_throttle_summary([])
    assert blob["heldNameDates"] == 0
    assert blob["throttledNameDatesPct"] is None
    assert blob["unapproachedWeightPctWhenThrottled"]["available"] is False


# --------------------------------------------------------------------------- #
# entry_state_incidence
# --------------------------------------------------------------------------- #
def _cfg():
    return {"selection": {"targetNames": 1, "minNames": 1, "maxNamesPerSector": 1,
                          "maxNamesPerRegion": 1}}


def test_incidence_reports_eligible_and_held_state_distribution():
    # A (ACCUMULATE, score 1.0, selected) and B (WATCH, discounted score 0.4,
    # not selected) under a target of 1 name.
    a = _row("A", score=1.0, state=1.0, entry_state="ACCUMULATE")
    b = _row("B", score=0.4, state=0.5, entry_state="WATCH")
    a["selected"], b["selected"] = True, False
    decisions = [{"scored": [a, b]}]
    blob = ES.entry_state_incidence(decisions, _cfg())
    assert blob["measuredRebalances"] == 1
    assert blob["eligibleByState"] == {"ACCUMULATE": 1, "WATCH": 1}
    assert blob["heldByState"] == {"ACCUMULATE": 1}


def test_incidence_detects_when_alpha_only_selection_would_flip():
    # A's discounted score (1.0) beats B's discounted score (0.6) today, so A
    # is selected. But B's OWN alpha (score / state = 0.6 / 0.5 = 1.2) exceeds
    # A's (1.0 / 1.0 = 1.0) once the throttle is removed -- alpha-only flips
    # the winner to B.
    a = _row("A", score=1.0, state=1.0, entry_state="ACCUMULATE")
    b = _row("B", score=0.6, state=0.5, entry_state="WATCH")
    a["selected"], b["selected"] = True, False
    decisions = [{"scored": [a, b]}]
    blob = ES.entry_state_incidence(decisions, _cfg())
    assert blob["rebalancesWhereSelectionWouldChange"] == 1
    assert blob["namesTheDiscountKeptOutOfTheBook"] == 1
    assert blob["namesTheDiscountLetIntoTheBook"] == 1


def test_incidence_does_not_mutate_the_control_decisions_it_reads():
    a = _row("A", score=1.0, state=1.0, entry_state="ACCUMULATE")
    b = _row("B", score=0.6, state=0.5, entry_state="WATCH")
    a["selected"], b["selected"] = True, False
    decisions = [{"scored": [a, b]}]
    ES.entry_state_incidence(decisions, _cfg())
    assert a["exclusionCodes"] == [] and b["exclusionCodes"] == []
    assert a["score"] == 1.0 and b["score"] == 0.6


def test_incidence_on_no_decisions_reports_zero_measured():
    blob = ES.entry_state_incidence([], _cfg())
    assert blob["measuredRebalances"] == 0
    assert blob["rebalancesWhereSelectionWouldChangePct"] is None


def test_incidence_ineligible_rows_are_excluded_from_the_distribution():
    a = _row("A", score=1.0, state=1.0, entry_state="ACCUMULATE")
    a["selected"] = True
    blocked = _row("Z", score=-1e12, state=0.0, eligible=False,
                   exclusion=["ENTRY_OR_RESEARCH_STATE_BLOCKS_SIZING"], entry_state="EVENT_RISK")
    blocked["selected"] = False
    decisions = [{"scored": [a, blocked]}]
    blob = ES.entry_state_incidence(decisions, _cfg())
    assert blob["eligibleByState"] == {"ACCUMULATE": 1}
    assert "EVENT_RISK" not in blob["eligibleByState"]


# --------------------------------------------------------------------------- #
# Freeze manifest
# --------------------------------------------------------------------------- #
def test_the_ladder_carries_alpha_reliability_s_own_control():
    from pipeline import alpha_reliability as AR
    assert ES.LADDER[0] == ES.CONTROL == AR.CONTROL


def test_eligibility_is_declared_unchanged_and_weight_is_never_redistributed():
    manifest = ES.freeze_manifest()
    assert "0" in manifest["eligibilityUnchanged"] or "eligibility" in manifest["eligibilityUnchanged"]
    assert "NEVER reallocated" in manifest["weightRedistribution"] or \
        "never reallocated" in manifest["weightRedistribution"]


def test_no_new_parameter_and_nothing_promoted():
    manifest = ES.freeze_manifest()
    assert manifest["parametersIntroduced"] == []
    assert manifest["permutationNullRun"] is False
    assert manifest["promotionEligible"] is False
    assert manifest["liveValidated"] is False
    assert manifest["productionChanged"] is False


def test_target_names_sector_region_caps_and_costs_declared_unchanged():
    manifest = ES.freeze_manifest()
    assert manifest["targetNamesSectorRegionCapsCostAssumptionsUnchanged"] is True


# --------------------------------------------------------------------------- #
# select_portfolio_by_scores reuse sanity: the throttle really does move rank
# --------------------------------------------------------------------------- #
def test_select_portfolio_by_scores_picks_by_the_handed_score_not_state():
    """Sanity check on production's own selector: it ranks by `score` alone,
    so handing it an alpha-only score is sufficient to remove the throttle
    from selection without touching `_select_scored` itself."""
    a = _row("A", score=1.0, state=1.0, entry_state="ACCUMULATE")
    b = _row("B", score=1.5, state=1.0, entry_state="ACCUMULATE")
    cfg = {"selection": {"targetNames": 1, "minNames": 1, "maxNamesPerSector": 1,
                         "maxNamesPerRegion": 1}}
    selected, _ = KP.select_portfolio_by_scores([a, b], [a, b], cfg, method="TEST")
    assert [c["ticker"] for c in selected] == ["B"]
