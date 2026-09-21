"""Exactly one axis moves: whether `lowvol` is inside the alpha.

The design document names three ways this study could fool itself, and each
is tested directly here: fitting the challenger's weights instead of deriving
them from production's, letting the sleeve's removal be charged as missing
data (which would cost ~14 points of evidenceCoverage for reasons unrelated
to the hypothesis), and letting the research pool or any downstream mechanism
move along with the blend.
"""
from __future__ import annotations

import pytest

from pipeline import longterm as LT
from pipeline import lowvol_alpha_separation as L


# --------------------------------------------------------------------------- #
# Weights are DERIVED from production, never chosen
# --------------------------------------------------------------------------- #
def test_control_weights_are_productions_own_object_values():
    assert L.FOUR_FACTOR == dict(LT.FACTOR_WEIGHTS)


def test_challenger_weights_are_the_renormalized_production_ratio():
    assert L.THREE_FACTOR == pytest.approx(
        {"momentum": 0.375, "value": 0.3125, "quality": 0.3125})
    assert sum(L.THREE_FACTOR.values()) == pytest.approx(1.0)
    assert "lowvol" not in L.THREE_FACTOR


def test_the_30_25_25_ratio_survives_renormalization():
    for a, b in (("momentum", "value"), ("momentum", "quality"), ("value", "quality")):
        assert (L.THREE_FACTOR[a] / L.THREE_FACTOR[b]
                == pytest.approx(L.FOUR_FACTOR[a] / L.FOUR_FACTOR[b]))


def test_an_unknown_rung_is_refused_rather_than_defaulted():
    with pytest.raises(ValueError):
        L.sleeve_weights("SOMETHING_ELSE")


# --------------------------------------------------------------------------- #
# The section-5 trap: removal must not be charged as missing data
# --------------------------------------------------------------------------- #
def test_removing_the_sleeve_is_not_treated_as_a_missing_sleeve():
    """A name with all four sleeves present must blend to the three-factor
    mean under the challenger — not to a four-factor mean with a hole in it."""
    percentiles = {"momentum": 80, "value": 60, "quality": 40, "lowvol": 0}
    challenger = L.blended_percentile(percentiles, L.THREE_FACTOR)
    # 0.375*80 + 0.3125*60 + 0.3125*40 = 61.25 — lowvol's 0 contributes nothing
    # and, critically, does not drag the mean down as a present-but-zero sleeve.
    assert challenger == pytest.approx(61.25)


def test_a_sleeve_outside_the_strategy_never_enters_the_denominator():
    with_lowvol = L.blended_percentile(
        {"momentum": 80, "value": 60, "quality": 40, "lowvol": 99}, L.THREE_FACTOR)
    without_lowvol = L.blended_percentile(
        {"momentum": 80, "value": 60, "quality": 40}, L.THREE_FACTOR)
    assert with_lowvol == without_lowvol


def test_a_genuinely_absent_sleeve_renormalizes_over_what_is_present():
    # Only momentum present: the blend is momentum, not momentum scaled down.
    assert L.blended_percentile({"momentum": 80}, L.THREE_FACTOR) == pytest.approx(80.0)
    assert L.blended_percentile({"momentum": 80}, L.FOUR_FACTOR) == pytest.approx(80.0)


def test_no_usable_sleeve_is_none_rather_than_a_neutral_number():
    assert L.blended_percentile({"lowvol": 20}, L.THREE_FACTOR) is None
    assert L.blended_percentile({}, L.FOUR_FACTOR) is None
    assert L.blended_percentile(None, L.FOUR_FACTOR) is None


def test_coverage_is_read_from_the_row_and_never_recomputed():
    row = {"factorPercentiles": {"momentum": 90}, "features": {"evidenceCoverage": 0.5}}
    # (90 - 50) * 0.5 = 20.0 — the stored coverage, applied to a CENTRED blend.
    assert L._rung_alpha(row, L.THREE_FACTOR) == pytest.approx(20.0)
    manifest = L.freeze_manifest()
    assert manifest["coverageRecomputed"] is False
    assert manifest["coverageIdenticalAcrossRungs"] is True


def test_coverage_shrinks_toward_neutral_in_both_directions():
    """A percentile blend is strictly positive, so an UNCENTRED coverage
    multiply would push every weakly-covered name down regardless of sign.
    Centring makes coverage shrink toward neutral, as production's signed
    rawAlpha does."""
    strong = {"factorPercentiles": {"momentum": 90}, "features": {"evidenceCoverage": 0.5}}
    weak = {"factorPercentiles": {"momentum": 10}, "features": {"evidenceCoverage": 0.5}}
    assert L._rung_alpha(strong, L.THREE_FACTOR) == pytest.approx(20.0)
    assert L._rung_alpha(weak, L.THREE_FACTOR) == pytest.approx(-20.0)
    # Lower coverage moves BOTH toward zero, never both downward.
    faint_strong = dict(strong, features={"evidenceCoverage": 0.1})
    faint_weak = dict(weak, features={"evidenceCoverage": 0.1})
    assert abs(L._rung_alpha(faint_strong, L.THREE_FACTOR)) < abs(
        L._rung_alpha(strong, L.THREE_FACTOR))
    assert abs(L._rung_alpha(faint_weak, L.THREE_FACTOR)) < abs(
        L._rung_alpha(weak, L.THREE_FACTOR))


def test_a_row_without_coverage_is_unrankable_rather_than_assumed_full():
    assert L._rung_alpha({"factorPercentiles": {"momentum": 90}}, L.THREE_FACTOR) is None


# --------------------------------------------------------------------------- #
# rebuild_percentiles
# --------------------------------------------------------------------------- #
def _signal(ticker, date, region, percentiles, coverage=1.0, published=None):
    row = {"ticker": ticker, "date": date, "region": region,
           "factorPercentiles": percentiles, "features": {"evidenceCoverage": coverage}}
    if published is not None:
        row["alphaPercentile"] = published
    return row


def test_percentiles_are_ranked_within_region_not_across_regions():
    signals = [
        _signal("US1", "2020-01-01", "US", {"momentum": 90}),
        _signal("US2", "2020-01-01", "US", {"momentum": 10}),
        _signal("KR1", "2020-01-01", "KR", {"momentum": 80}),
        _signal("KR2", "2020-01-01", "KR", {"momentum": 20}),
    ]
    out = L.rebuild_percentiles(signals, L.NO_LOWVOL)
    # Top of each region is 100 even though the US top beats the KR top.
    assert out["2020-01-01"]["US1"] == 100.0
    assert out["2020-01-01"]["KR1"] == 100.0
    assert out["2020-01-01"]["US2"] == 50.0
    assert out["2020-01-01"]["KR2"] == 50.0


def test_ties_receive_the_average_rank():
    signals = [_signal(f"T{i}", "2020-01-01", "US", {"momentum": 50}) for i in range(4)]
    out = L.rebuild_percentiles(signals, L.NO_LOWVOL)
    # Four tied names: average rank 2.5 of 4 -> 62.5 -> rounds to 62.
    assert set(out["2020-01-01"].values()) == {62.0}


def test_the_lowvol_sleeve_changes_the_ranking_between_rungs():
    """A high-momentum / high-volatility name against a low-momentum /
    low-volatility one: the sleeve decides the order under the control and
    cannot under the challenger."""
    signals = [
        _signal("GROWTH", "2020-01-01", "US", {"momentum": 99, "lowvol": 1}),
        _signal("DEFENSIVE", "2020-01-01", "US", {"momentum": 60, "lowvol": 99}),
    ]
    control = L.rebuild_percentiles(signals, L.CONTROL)["2020-01-01"]
    challenger = L.rebuild_percentiles(signals, L.NO_LOWVOL)["2020-01-01"]
    # Control: growth 0.3*99+0.2*1 over 0.5 = 59.8; defensive 0.3*60+0.2*99 over 0.5 = 75.6
    assert control["DEFENSIVE"] > control["GROWTH"]
    # Challenger: momentum alone, so the growth name wins.
    assert challenger["GROWTH"] > challenger["DEFENSIVE"]


def test_an_unrankable_row_is_absent_rather_than_ranked_at_zero():
    signals = [
        _signal("A", "2020-01-01", "US", {"momentum": 90}),
        _signal("B", "2020-01-01", "US", {"lowvol": 90}),  # nothing the challenger uses
    ]
    out = L.rebuild_percentiles(signals, L.NO_LOWVOL)["2020-01-01"]
    assert "B" not in out
    assert out["A"] == 100.0


# --------------------------------------------------------------------------- #
# rung_candidates: the pool is production's, only the ranking quantity moves
# --------------------------------------------------------------------------- #
def test_rung_candidates_copies_and_does_not_mutate_the_shared_context():
    original = [{"ticker": "A", "alphaPercentile": 95, "sector": "Tech"}]
    out = L.rung_candidates(original, {"A": 42.0})
    assert out[0] is not original[0]
    assert out[0]["alphaPercentile"] == 42.0
    assert original[0]["alphaPercentile"] == 95
    assert out[0]["sector"] == "Tech"


def test_pool_membership_is_never_changed_by_the_rebuild():
    original = [{"ticker": "A", "alphaPercentile": 95}, {"ticker": "B", "alphaPercentile": 93}]
    out = L.rung_candidates(original, {"A": 42.0})  # B has no rebuilt percentile
    assert [c["ticker"] for c in out] == ["A", "B"]
    assert out[1]["alphaPercentile"] == 93  # falls back, is not dropped


# --------------------------------------------------------------------------- #
# sector diagnostics
# --------------------------------------------------------------------------- #
def _decision(date, held, sectors):
    return {"date": date, "retained": [], "added": sorted(held),
            "scored": [{"ticker": t, "sector": s} for t, s in sectors.items()]}


def test_sector_exposure_counts_held_name_dates():
    decisions = [_decision("2020-01-01", {"A", "B"},
                           {"A": "Technology", "B": "Utilities", "C": "Technology"})]
    blob = L.sector_exposure(decisions)
    assert blob["heldNameDates"] == 2
    assert blob["bySector"] == {"Technology": 1, "Utilities": 1}
    assert blob["sharePct"]["Technology"] == 50.0


def test_sector_shift_is_challenger_minus_control_in_points():
    control = {"sharePct": {"Technology": 20.0, "Utilities": 30.0}}
    challenger = {"sharePct": {"Technology": 35.0, "Utilities": 10.0}}
    delta = L.sector_shift(control, challenger)["sharePctDelta"]
    assert delta["Technology"] == 15.0
    assert delta["Utilities"] == -20.0


def test_a_sector_only_one_rung_holds_is_still_reported():
    delta = L.sector_shift({"sharePct": {"Utilities": 40.0}},
                           {"sharePct": {"Technology": 40.0}})["sharePctDelta"]
    assert delta["Technology"] == 40.0
    assert delta["Utilities"] == -40.0


def test_sector_exposure_on_no_decisions_reports_absence():
    blob = L.sector_exposure([])
    assert blob["heldNameDates"] == 0
    assert blob["bySector"] == {}


# --------------------------------------------------------------------------- #
# Freeze manifest
# --------------------------------------------------------------------------- #
def test_every_downstream_mechanism_is_declared_unchanged():
    manifest = L.freeze_manifest()
    for key in ("eligibilityRecomputed", "coverageRecomputed", "weightSweepPerformed",
                "permutationNullRun", "promotionEligible", "liveValidated",
                "productionChanged"):
        assert manifest[key] is False
    for key in ("researchPoolIdenticalAcrossRungs", "riskDenominatorRetainedOnBothRungs",
                "inverseVolSizingRetainedOnBothRungs", "entryLogicUnchanged",
                "regionAndSectorCapsUnchanged"):
        assert manifest[key] is True
    assert manifest["targetNamesUnchanged"] == 5
    assert manifest["parametersIntroduced"] == []


def test_the_harness_difference_is_declared_not_hidden():
    manifest = L.freeze_manifest()
    assert "PERCENTILE" in manifest["harnessDifference"]
    assert "not the published path" in manifest["harnessDifference"]
