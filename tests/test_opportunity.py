"""Opportunity and Warning radar behaviour, plus the anti-overfitting gates.

The behavioural rules being pinned here are the ones a plausible-looking
implementation gets wrong:

* A permanently excellent stock is not an opportunity. Nothing changed.
* Heavy volume into a falling price is distribution, not accumulation.
* A model that fails its acceptance gate does not ship with a caveat — it does
  not ship at all, and the transparent rule-based score stays in force.
* A "VALIDATED" tier is a claim about evidence, so it cannot be reached while
  the evidence layer is inactive.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pipeline import opportunity as OP
from pipeline import walkforward as WF


def _features(**overrides) -> dict:
    base = {column: 0.0 for column in OP.FEATURE_COLUMNS}
    base.update({"alphaPercentile": 60.0, "volumeSurge": 1.0, "volRegimeRatio": 1.0,
                 "aboveMA200": 1.0, "aboveMA50": 1.0, "rsi14": 50.0})
    base.update(overrides)
    return base


def _candidate(ticker="AAA", region="US", **overrides) -> dict:
    return {"ticker": ticker, "region": region, "sector": "Tech",
            "entryState": "ACCUMULATE_GRADUALLY", "isCoreHolding": False,
            "features": _features(**overrides)}


# --------------------------------------------------------------------------- #
# Tier logic
# --------------------------------------------------------------------------- #
def test_high_alpha_without_any_change_is_not_an_opportunity():
    """The single most important rule: opportunity is about CHANGE."""
    row = {**_candidate(alphaPercentile=99.0), "score": 95.0}
    tier, notes = OP.classify_tier(row, ml_active=True, high_score=70.0)
    assert tier == "WATCH"
    assert "NO_RECENT_CHANGE_DETECTED" in notes


def test_convergent_change_signals_produce_a_high_score():
    improving = _candidate(alphaPercentileDelta=14.0, momentum20Acceleration=9.0,
                           relMomentumDelta=0.05, volumeSurge=1.8,
                           entryStateImproved=1.0, sectorRotationImproved=1.0)
    flat = _candidate()
    assert (OP._rule_based_score(improving["features"])
            > OP._rule_based_score(flat["features"]) + 0.2)
    signals = OP._convergent_signals(improving["features"])
    for expected in ("ALPHA_PERCENTILE_RISING", "MOMENTUM_ACCELERATION",
                     "VOLUME_SURGE", "ENTRY_STATE_UPGRADE"):
        assert expected in signals


def test_volume_spike_on_a_falling_price_is_never_an_opportunity():
    distribution = _candidate(volumeSurge=2.2, mom20Pct=-9.0,
                              momentum20Acceleration=-6.0, relMomentumDelta=-0.04)
    row = {**distribution, "score": 95.0}
    tier, notes = OP.classify_tier(row, ml_active=True, high_score=70.0)
    assert tier == "WATCH"
    assert "VOLUME_SURGE_WITH_PRICE_DECLINE_NOT_AN_OPPORTUNITY" in notes


def test_validated_tier_is_unreachable_without_an_accepted_model():
    strong = {**_candidate(alphaPercentileDelta=20.0, momentum20Acceleration=12.0,
                           relMomentumDelta=0.06, volumeSurge=2.0,
                           entryStateImproved=1.0), "score": 96.0}
    with_model, _ = OP.classify_tier(strong, ml_active=True, high_score=70.0)
    without_model, notes = OP.classify_tier(strong, ml_active=False, high_score=70.0)
    assert with_model == "VALIDATED_OPPORTUNITY"
    assert without_model == "EMERGING_OPPORTUNITY"
    assert "HISTORICAL_MODEL_NOT_VALIDATED_RESEARCH_ONLY" in notes


def test_warning_score_is_not_the_opportunity_score_inverted():
    """A quiet stock must not be flagged as dangerous merely for being quiet."""
    quiet = _features()
    deteriorating = _features(alphaPercentileDelta=-12.0, momentum20Acceleration=-8.0,
                              relMomentumDelta=-0.04, entryStateImproved=-1.0,
                              ma200Crossed=-1.0, volRegimeRatio=1.9)
    assert OP._rule_based_warning_score(deteriorating) > OP._rule_based_warning_score(quiet)
    # Not a mirror image: the volatility-shock term has no opportunity twin.
    shock = _features(volRegimeRatio=1.9)
    assert OP._rule_based_warning_score(shock) > OP._rule_based_warning_score(quiet)
    assert OP._rule_based_score(shock) == pytest.approx(OP._rule_based_score(quiet))


def test_entry_downgrade_with_trend_breakdown_is_a_critical_warning():
    row = {**_candidate(entryStateImproved=-1.0, ma200Crossed=-1.0,
                        alphaPercentileDelta=-10.0), "score": 80.0}
    tier, notes = OP._warning_tier(row, ml_active=False, high_score=70.0)
    assert tier == "CRITICAL_WARNING"
    assert "ENTRY_DOWNGRADE_WITH_TREND_BREAKDOWN" in notes


def test_core_holdings_are_prioritised_in_the_warning_radar():
    held = {**_candidate("HELD"), "isCoreHolding": True}
    held["features"].update(alphaPercentileDelta=-6.0, entryStateImproved=-1.0)
    louder = _candidate("LOUD")
    louder["features"].update(alphaPercentileDelta=-20.0, momentum20Acceleration=-15.0,
                              entryStateImproved=-1.0, ma200Crossed=-1.0,
                              volRegimeRatio=2.0)
    radar = OP.build_radar([louder, held], kind="warning", cfg={})
    assert radar["regions"]["US"][0]["ticker"] == "HELD"


# --------------------------------------------------------------------------- #
# Radar assembly
# --------------------------------------------------------------------------- #
def test_radar_without_a_model_falls_back_transparently():
    radar = OP.build_radar([_candidate("AAA"), _candidate("BBB", region="KR")],
                           dataset=None, spec={}, cfg={}, kind="opportunity")
    assert radar["mlStatus"] == "NOT_TRAINED"
    assert radar["method"] == "RULE_BASED_CHANGE_SCORE"
    assert radar["evidenceClass"] == "NONE"
    assert set(radar["regions"]) == {"US", "KR"}
    for rows in radar["regions"].values():
        for row in rows:
            assert row["tier"] != "VALIDATED_OPPORTUNITY"


def test_a_rejected_model_is_not_used_and_says_so():
    rejected = {"status": "TRAINED", "accepted": False, "kind": "opportunity",
                "winner": {"family": "gradient_boosting", "target": "TARGET_A", "params": {}}}
    radar = OP.build_radar([_candidate()], dataset=None, spec=rejected, cfg={})
    assert radar["mlStatus"] == "REJECTED_BY_ACCEPTANCE_GATE"
    assert radar["method"] == "RULE_BASED_CHANGE_SCORE"


def test_an_opportunity_model_is_not_reused_for_the_warning_radar():
    spec = {"status": "TRAINED", "accepted": True, "kind": "opportunity",
            "winner": {"family": "logistic", "target": "TARGET_A", "params": {}}}
    radar = OP.build_radar([_candidate()], dataset=None, spec=spec, cfg={}, kind="warning")
    assert radar["mlStatus"] == "NO_MODEL_FOR_THIS_RADAR"


# --------------------------------------------------------------------------- #
# Targets and labels
# --------------------------------------------------------------------------- #
def _dataset(n_dates=60, seed=5) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for date in pd.bdate_range("2015-01-02", periods=n_dates, freq="5B"):
        for i in range(12):
            edge = 0.02 if i >= 9 else 0.0
            excess = float(rng.normal(edge, 0.06))
            row = {"id": f"{date}-{i}", "date": date.normalize(), "ticker": f"T{i}",
                   "region": "US", "sector": "Tech", "macroRegime": "Goldilocks",
                   "entryState": "WATCH", "sectorRotation": "STABLE",
                   "evidenceClass": "HISTORICAL_OOS", "pitCoverage": 0.8,
                   "usableForCalibration": True}
            for column in OP.FEATURE_COLUMNS:
                row[column] = float(rng.normal(0, 1))
            row["alphaPercentile"] = float(i * 8)
            for horizon in (21, 63, 126, 252):
                row[f"excess_{horizon}"] = excess
                row[f"netExcess_{horizon}"] = excess - 0.005
                row[f"mfe_{horizon}"] = abs(excess) + 0.05
                row[f"mae_{horizon}"] = -abs(excess) - 0.02
                row[f"mdd_{horizon}"] = -abs(excess) - 0.02
            rows.append(row)
    return pd.DataFrame(rows)


def test_every_target_produces_a_two_class_label():
    dataset = _dataset()
    for target in OP.TARGET_SPECS:
        labelled = OP.add_target(dataset, target)
        assert not labelled.empty, target
        assert labelled["target"].nunique() == 2, target
        assert set(labelled["target"].unique()) <= {0.0, 1.0}


def test_cross_sectional_target_ranks_inside_each_date_not_across_dates():
    dataset = _dataset()
    labelled = OP.add_target(dataset, "TARGET_C_TOP_QUINTILE_126D")
    shares = labelled.groupby("date")["target"].mean()
    # Roughly a fifth positive on EVERY date — never a whole date labelled 1.
    assert shares.max() <= 0.5
    assert shares.min() >= 0.0


def test_warning_targets_capture_the_opposite_direction():
    dataset = _dataset()
    for target in OP.WARNING_TARGET_SPECS:
        labelled = OP.add_target(dataset, target, OP.WARNING_TARGET_SPECS)
        assert not labelled.empty, target


# --------------------------------------------------------------------------- #
# Metrics and overfitting diagnostics
# --------------------------------------------------------------------------- #
def test_monotonicity_rewards_an_ordered_ladder_and_punishes_a_flat_one():
    ordered = [{"decile": i + 1, "meanExcessPct": i * 0.5} for i in range(10)]
    inverted = [{"decile": i + 1, "meanExcessPct": -i * 0.5} for i in range(10)]
    assert OP.monotonicity(ordered) == pytest.approx(1.0)
    assert OP.monotonicity(inverted) == pytest.approx(-1.0)


def test_top_bucket_path_statistics_use_non_overlapping_dates():
    index = pd.bdate_range("2015-01-02", periods=300)
    frame = pd.DataFrame({
        "date": index, "region": "US", "ticker": "T",
        "score": np.linspace(0, 1, 300), "scoreExcess": np.full(300, 0.02),
        "targetHorizon": 126,
    })
    result = OP.top_bucket_performance(frame, top_pct=0.5)
    assert result["dates"] > result["nonOverlappingDates"]
    assert result["nonOverlappingDates"] <= 4
    assert result["mddPct"] in (None, 0.0) or result["mddPct"] >= -1e-9


def test_acceptance_gate_rejects_a_model_that_fails_any_check():
    winner = OP.VariantResult(
        name="GBM", family="gradient_boosting", params={}, target="TARGET_A",
        test={"decileMonotonicity": 0.1,
              "topBucket": {"meanExcessPct": -1.0},
              "foldStability": {"stable": False}},
        folds=[{"fold": 0}])
    report = OP.acceptance_report(winner, None, cfg={}, pit_coverage=0.8)
    assert report["accepted"] is False
    for failure in ("decileMonotonicity", "netExcessSurvivesCost", "foldStability"):
        assert failure in report["failures"]


def test_acceptance_gate_requires_beating_the_simple_baseline():
    strong_test = {"decileMonotonicity": 0.9,
                   "topBucket": {"meanExcessPct": 2.0},
                   "foldStability": {"stable": True}}
    winner = OP.VariantResult(name="GBM", family="gradient_boosting", params={},
                              target="TARGET_A", test=strong_test, folds=[{"fold": 0}])
    better_baseline = OP.VariantResult(
        name="LOGISTIC_BASELINE", family="logistic", params={}, target="TARGET_A",
        test={**strong_test, "topBucket": {"meanExcessPct": 5.0}}, folds=[{"fold": 0}])
    report = OP.acceptance_report(winner, better_baseline, cfg={}, pit_coverage=0.8)
    assert report["accepted"] is False
    assert "beatsBaselineOutOfSample" in report["failures"]


def test_unlabelled_concentration_is_inconclusive_not_a_silent_pass_or_fail():
    predictions = pd.DataFrame({
        "date": pd.bdate_range("2015-01-02", periods=40), "region": "US",
        "score": np.linspace(0, 1, 40), "scoreExcess": np.full(40, 0.02),
        "macroRegime": [None] * 40, "sector": ["Unclassified"] * 40,
    })
    winner = OP.VariantResult(
        name="GBM", family="gradient_boosting", params={}, target="TARGET_A",
        test={"decileMonotonicity": 0.9, "topBucket": {"meanExcessPct": 2.0},
              "foldStability": {"stable": True}},
        folds=[{"fold": 0}])
    winner.predictions = predictions
    report = OP.acceptance_report(winner, None, cfg={}, pit_coverage=0.8)
    assert "regimeConcentrationNotAssessable" in report["inconclusive"]
    assert "notRegimeConcentrated" not in report["failures"]


def test_deflated_sharpe_punishes_a_wide_search():
    narrow = OP.deflated_sharpe(0.5, n_trials=2, n_obs=100)
    wide = OP.deflated_sharpe(0.5, n_trials=500, n_obs=100)
    assert narrow > wide


def test_search_log_records_how_many_variants_were_tried():
    dataset = _dataset(n_dates=120, seed=11)
    guard = WF.HoldoutGuard(start=pd.Timestamp(dataset["date"].max()) - pd.DateOffset(years=1))
    result = OP.train(dataset,
                      targets={"TARGET_A_POSITIVE_EXCESS_126D":
                               OP.TARGET_SPECS["TARGET_A_POSITIVE_EXCESS_126D"]},
                      cfg={"trainYears": 1.0, "validationYears": 0.6, "testYears": 0.6,
                           "embargoDays": 21, "includeLightGbm": False},
                      guard=guard,
                      zoo={"LOGISTIC_BASELINE": {"family": "logistic", "params": {"C": 1.0}},
                           "LOGISTIC_L2_STRONG": {"family": "logistic", "params": {"C": 0.05}}})
    if result["status"] == "TRAINED":
        assert result["diagnostics"]["searchLog"]["variantsTested"] >= 1
        assert "acceptance" in result
        assert isinstance(result["accepted"], bool)
    else:
        assert result["status"] in {"INSUFFICIENT_HISTORY", "NO_VIABLE_VARIANT", "NO_DATA"}


def test_training_never_scores_the_holdout_before_the_winner_is_chosen():
    dataset = _dataset(n_dates=120, seed=13)
    guard = WF.HoldoutGuard(start=pd.Timestamp(dataset["date"].max()) - pd.DateOffset(years=1))
    assert guard.sealed is True
    OP.train(dataset,
             targets={"TARGET_A_POSITIVE_EXCESS_126D":
                      OP.TARGET_SPECS["TARGET_A_POSITIVE_EXCESS_126D"]},
             cfg={"trainYears": 1.0, "validationYears": 0.6, "testYears": 0.6,
                  "includeLightGbm": False},
             guard=guard,
             zoo={"LOGISTIC_BASELINE": {"family": "logistic", "params": {"C": 1.0}}})
    log = guard.to_dict()["accessLog"]
    if log:
        # The unseal must be the FIRST holdout access, and must name the reason.
        assert log[0].startswith("unsealed:winner_selected")


# --------------------------------------------------------------------------- #
# Calibration and analogues
# --------------------------------------------------------------------------- #
def test_calibration_bands_hide_numbers_when_the_sample_is_thin():
    frame = pd.DataFrame({
        "date": pd.bdate_range("2015-01-02", periods=200),
        "score": np.linspace(0.01, 0.99, 200),
        "scoreExcess": np.linspace(-0.1, 0.2, 200),
        "grossExcess": np.linspace(-0.1, 0.2, 200),
    })
    bands = OP._calibration_bands(frame, bins=5)
    for band in bands:
        if not band["sampleSufficient"]:
            assert band["meanExcessPct"] is None
            assert band["positiveExcessHitRatio"] is None
        assert band["n"] is not None


def test_historical_analogues_are_explanatory_and_flag_thin_samples():
    dataset = _dataset(n_dates=80)
    candidate = _candidate()
    result = OP.historical_analogues(candidate, dataset, horizon=126, k=40)
    assert result is not None
    assert result["matches"] > 0
    assert "disclaimerKo" in result and "보장" in result["disclaimerKo"]
    assert result["worstDecileExcessPct"] <= result["meanExcessPct"]
    tiny = OP.historical_analogues(candidate, dataset.head(20), horizon=126, k=40)
    assert tiny is None or tiny["sampleSufficient"] is False
