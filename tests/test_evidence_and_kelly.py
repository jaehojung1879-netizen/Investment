"""Walk-forward discipline, historical calibration, and the Kelly posterior.

The behaviour under test is the central change of this work: an empty
prospective ledger no longer forces the expected excess return to zero, because
zero is itself a strong claim ("no edge") that the historical ledger can test.
What must NOT change is that evidence can only move the estimate toward what was
measured — uncertainty always shrinks toward zero, and a live shortfall always
cuts risk rather than raising it.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from pipeline import evidence as EV
from pipeline import historical_calibration as HC
from pipeline import kelly_portfolio as KP
from pipeline.kelly_portfolio import build_model_portfolio
from pipeline import walkforward as WF


# --------------------------------------------------------------------------- #
# Walk-forward
# --------------------------------------------------------------------------- #
def test_folds_are_strictly_time_ordered_with_no_random_split():
    folds = WF.make_folds(pd.bdate_range("2013-01-01", "2024-12-31"),
                          train_years=3, validation_years=1, test_years=1,
                          horizon_days=126, embargo_days=21)
    assert folds
    for fold in folds:
        assert fold.train_start <= fold.train_end < fold.validation_start
        assert fold.validation_end < fold.test_start <= fold.test_end
        WF.assert_ordered(fold, 126)
    # Test blocks march forward and never revisit an earlier period.
    starts = [f.test_start for f in folds]
    assert starts == sorted(starts)
    assert WF.split_summary(folds)["randomSplitUsed"] is False


def test_purge_and_embargo_gap_is_at_least_the_forecast_horizon():
    horizon, embargo = 126, 21
    folds = WF.make_folds(pd.bdate_range("2013-01-01", "2024-12-31"),
                          horizon_days=horizon, embargo_days=embargo)
    required = pd.Timedelta(days=horizon + embargo)
    for fold in folds:
        assert fold.validation_start - fold.train_end >= required
        assert fold.test_start - fold.validation_end >= required


def test_a_fold_with_overlapping_blocks_is_rejected():
    bad = WF.Fold(index=0, train_start=pd.Timestamp("2013-01-01"),
                  train_end=pd.Timestamp("2016-01-01"),
                  validation_start=pd.Timestamp("2016-01-02"),
                  validation_end=pd.Timestamp("2017-01-01"),
                  test_start=pd.Timestamp("2017-01-02"),
                  test_end=pd.Timestamp("2018-01-01"),
                  embargo_days=21, mode="expanding")
    with pytest.raises(ValueError):
        WF.assert_ordered(bad, horizon_days=126)


def test_test_rows_never_appear_in_training_or_validation_slices():
    dates = pd.bdate_range("2013-01-01", "2024-12-31")
    frame = pd.DataFrame({"date": dates, "value": range(len(dates))})
    for fold in WF.make_folds(dates, horizon_days=126, embargo_days=21):
        train = set(fold.slice(frame, "train")["date"])
        validation = set(fold.slice(frame, "validation")["date"])
        test = set(fold.slice(frame, "test")["date"])
        assert not train & test
        assert not validation & test
        assert not train & validation


def test_final_holdout_is_sealed_until_explicitly_unsealed():
    dates = pd.bdate_range("2013-01-01", "2025-12-31")
    frame = pd.DataFrame({"date": dates})
    guard = WF.HoldoutGuard.from_config({"finalHoldoutStart": "2023-01-01"})
    development = guard.development(frame)
    assert development["date"].max() < pd.Timestamp("2023-01-01")
    with pytest.raises(WF.HoldoutViolation):
        guard.holdout(frame)
    guard.unseal("model_frozen")
    holdout = guard.holdout(frame, reason="final_evaluation")
    assert holdout["date"].min() >= pd.Timestamp("2023-01-01")
    assert "unsealed:model_frozen" in guard.to_dict()["accessLog"]


def test_rolling_mode_drops_old_data_and_expanding_keeps_it():
    dates = pd.bdate_range("2013-01-01", "2024-12-31")
    expanding = WF.make_folds(dates, mode="expanding", horizon_days=126)
    rolling = WF.make_folds(dates, mode="rolling", horizon_days=126)
    assert all(f.train_start == expanding[0].train_start for f in expanding)
    assert rolling[-1].train_start > rolling[0].train_start


# --------------------------------------------------------------------------- #
# Historical calibration
# --------------------------------------------------------------------------- #
def _outcome(date, *, percentile, excess, region="US", pit=0.8, sector="Tech",
             regime="Goldilocks", ticker="AAA", cost=0.005):
    return {
        "id": f"{date}|{region}|{ticker}", "date": date, "asOf": date,
        "ticker": ticker, "region": region, "sector": sector,
        "macroRegime": regime, "alphaPercentile": percentile,
        "evidenceClass": "HISTORICAL_OOS",
        "pit": {"pitCoverage": pit, "lookAheadCheckPassed": True,
                "usableForCalibration": pit >= 0.6},
        "horizons": {"126": {"excessReturn": excess,
                             "costAdjustedExcessReturn": excess - cost,
                             "absoluteReturn": excess}},
    }


def _ledger(n_dates=90, seed=3):
    """A ledger where higher alpha buckets genuinely paid more."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2015-01-02", periods=n_dates, freq="5B")
    rows = []
    for date in dates:
        stamp = date.strftime("%Y-%m-%d")
        for percentile, mean in ((50, 0.005), (70, 0.015), (85, 0.030),
                                 (92, 0.045), (97, 0.070)):
            for k in range(3):
                rows.append(_outcome(stamp, percentile=percentile,
                                     excess=float(rng.normal(mean, 0.05)),
                                     ticker=f"T{percentile}{k}"))
    return rows


def test_hac_bandwidth_is_measured_in_observations_not_trading_days():
    """A 126-session overlap spans ~26 weekly observations, not 126.

    The lag has to be read off the series being estimated. Passing horizon-1
    directly meant a weekly series was given 125 lags for an overlap that spans
    25, and the extra lags are noise that can only shrink the estimated long-run
    variance — inflating t and the effective sample size.
    """
    weekly = pd.Series(np.zeros(300), index=pd.bdate_range("2015-01-02", periods=300, freq="5B"))
    daily = pd.Series(np.zeros(800), index=pd.bdate_range("2015-01-02", periods=800))

    weekly_stats = KP._newey_west_stats(weekly + 0.01, 126)
    daily_stats = KP._newey_west_stats(daily + 0.01, 126)

    assert weekly_stats["samplingStepDays"] == 5
    assert daily_stats["samplingStepDays"] == 1
    # 126 sessions / 5 sessions per observation -> 26 overlapping observations.
    assert weekly_stats["hacLag"] == 25
    assert daily_stats["hacLag"] == 125


def test_hac_does_not_invent_precision_on_independent_observations():
    """Independent weekly draws must not report a near-full effective sample.

    Under the old bandwidth this returned ~354 effective dates out of 374 and
    rejected a true null four times as often as it should have.
    """
    rng = np.random.default_rng(20240718)
    index = pd.bdate_range("2015-01-02", periods=374, freq="5B")
    rejections = 0
    trials = 200
    for _ in range(trials):
        series = pd.Series(rng.normal(0, 0.05, len(index)), index=index)
        stats = KP._newey_west_stats(series, 126)
        if abs(stats["mean"] / stats["se"]) >= 1.96:
            rejections += 1
    # Nominal 5%. The old convention sat above 13% here.
    assert rejections / trials < 0.10, rejections / trials


def test_bandwidth_limited_estimates_are_flagged():
    """A series too short to carry its own overlap gets a floor, and says so."""
    short = pd.Series(np.linspace(0, 0.02, 40),
                      index=pd.bdate_range("2015-01-02", periods=40))
    stats = KP._newey_west_stats(short, 126)
    assert stats["bandwidthLimited"] is True
    assert stats["hacLag"] == 10   # capped at n // 4


def _carry_ledger(n_dates=90, seed=11, carry=0.08, spread_per_bucket=0.0,
                  noise=0.05, region="US"):
    """A ledger where the whole universe beat the benchmark by ``carry``.

    ``spread_per_bucket`` is the only genuine ranking effect: 0.0 means the
    ranking ordered nothing and every point of measured "excess" is carry.
    """
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2015-01-02", periods=n_dates, freq="5B")
    rows = []
    for date in dates:
        stamp = date.strftime("%Y-%m-%d")
        # One shared shock per date: the universe moves together, which is what
        # makes the level look precise while saying nothing about the ranking.
        shared = float(rng.normal(carry, 0.04))
        for rank, percentile in enumerate((50, 70, 85, 92, 97)):
            for k in range(3):
                rows.append(_outcome(
                    stamp, percentile=percentile, region=region,
                    excess=shared + rank * spread_per_bucket + float(rng.normal(0, noise)),
                    ticker=f"T{percentile}{k}"))
    return rows


def _calibrate(rows, **cfg):
    settings = {"minEffectiveDates": 5, "shrinkagePriorStrength": 5}
    settings.update(cfg)
    return HC.calibrate(rows, horizon=126, cfg=settings,
                        diagnostics={"survivorshipRisk": "HIGH",
                                     "macroPitStatus": "REVISED_HISTORY",
                                     "fundamentalsPit": False})


def test_universe_carry_is_never_reported_as_model_alpha():
    """A universe that beat its benchmark is not a selection edge.

    Every bucket earns the same +8%: the ranking did nothing. The level must
    still show +8% (it happened), the spread must be ~0, and nothing may reach
    Kelly as an expected return.
    """
    calibration = _calibrate(_carry_ledger(spread_per_bucket=0.0))
    region = calibration["regions"]["US"]

    assert region["universeBaseline"]["meanExcessPct"] > 6.0
    for row in region["buckets"]:
        assert row["levelExpectedExcessReturnPct"] > 6.0, "the level really was earned"
        assert abs(row["spreadVsUniversePct"]) < 1.5, "but none of it is attributable"
        assert abs(row["calibratedExpectedExcessReturnPct"]) < 1.5

    assert region["ordering"]["established"] is False
    assert region["ordering"]["reason"] == "ORDERING_NOT_DISTINGUISHABLE_FROM_NOISE"
    assert region["usableBuckets"] == 0
    assert calibration["orderingEstablishedRegions"] == []

    # And the whole way down to the number that would size a position.
    assert EV.candidate_prior(calibration, "US", 97.0) is None
    summary = EV.summarize_region(calibration, {}, min_effective_dates=5,
                                  prior_scale_pct=3.0)
    assert summary["US"]["posterior"]["expectedExcessReturnPct"] == 0.0
    assert summary["US"]["alphaAttribution"]["orderingEstablished"] is False
    assert summary["US"]["alphaAttribution"]["universeBaselineExcessPct"] > 6.0


def test_isotonic_repair_never_manufactures_a_ladder_from_noise():
    """Isotonic regression always returns a monotone fit — that is the danger."""
    calibration = _calibrate(_carry_ledger(spread_per_bucket=0.0, seed=17))
    rows = calibration["regions"]["US"]["buckets"]
    assert all(r["monotonicityWarning"] == "ORDERING_NOT_ESTABLISHED_NO_LADDER_PUBLISHED"
               for r in rows)
    # No repair happened, so the published values are the measured ones.
    for row in rows:
        assert (row["calibratedExpectedExcessReturnPct"]
                == row["preIsotonicExpectedExcessReturnPct"])
    published = [r["calibratedExpectedExcessReturnPct"] for r in rows]
    assert published != sorted(published), "noise was laundered into a rising ladder"


def test_expected_return_is_the_spread_and_the_level_stays_visible():
    """Real ordering on top of a large carry: only the spread may be capitalised."""
    calibration = _calibrate(_carry_ledger(spread_per_bucket=0.02, seed=5))
    region = calibration["regions"]["US"]
    assert region["ordering"]["established"] is True
    carry = region["universeBaseline"]["meanExcessPct"]
    assert carry > 6.0

    top = [r for r in region["buckets"] if r["bucket"] == "95-100"][0]
    level = top["levelExpectedExcessReturnPct"]
    spread = top["spreadVsUniversePct"]
    assert level > spread + 4.0, "the level is inflated by the carry"
    assert spread > 2.0, "the ranking genuinely paid"
    # The published expectation tracks the spread, never the level.
    assert top["expectedReturnBasis"] == "ALPHA_SPREAD_VS_REPLAY_UNIVERSE"
    assert top["calibratedExpectedExcessReturnPct"] <= spread + 1e-9
    assert top["calibratedExpectedExcessReturnPct"] < level

    prior = EV.candidate_prior(calibration, "US", 97.0)
    assert prior is not None
    assert prior["expectedExcessReturnPct"] < prior["levelExcessReturnPct"]
    assert prior["universeBaselineExcessPct"] == carry


def test_ordering_gate_admits_a_ranking_that_actually_orders_returns():
    calibration = _calibrate(_ledger())
    assert calibration["orderingEstablishedRegions"] == ["US"]
    ordering = calibration["regions"]["US"]["ordering"]
    assert ordering["established"] is True
    assert ordering["topMinusBottomTStat"] >= ordering["minTStat"]
    assert ordering["meanRankIC"] > 0


def test_calibration_produces_an_increasing_bucket_ladder():
    calibration = HC.calibrate(_ledger(), horizon=126,
                               cfg={"minEffectiveDates": 5, "shrinkagePriorStrength": 5},
                               diagnostics={"survivorshipRisk": "HIGH",
                                            "macroPitStatus": "REVISED_HISTORY",
                                            "fundamentalsPit": False})
    assert calibration["available"]
    buckets = calibration["regions"]["US"]["buckets"]
    values = [b["calibratedExpectedExcessReturnPct"] for b in buckets if b["usable"]]
    assert values == sorted(values), "isotonic repair must leave a non-decreasing ladder"
    assert values[-1] > values[0]


def test_calibration_shrinks_thin_buckets_toward_zero():
    thin = [_outcome("2015-01-02", percentile=97, excess=0.5),
            _outcome("2015-03-02", percentile=97, excess=0.5),
            _outcome("2015-05-04", percentile=97, excess=0.5)]
    calibration = HC.calibrate(thin, horizon=126,
                               cfg={"minEffectiveDates": 30, "shrinkagePriorStrength": 30},
                               diagnostics={})
    row = calibration["regions"]["US"]["buckets"][0]
    # A 50% mean from three dates must not survive as a 50% expectation.
    assert row["meanExcessReturnPct"] > 40
    assert row["shrunkExpectedExcessReturnPct"] < 10
    assert row["usable"] is False


def test_low_pit_observations_never_reach_calibration():
    poor = [_outcome(d.strftime("%Y-%m-%d"), percentile=97, excess=0.30, pit=0.2)
            for d in pd.bdate_range("2015-01-02", periods=60, freq="5B")]
    calibration = HC.calibrate(poor, horizon=126, cfg={"minEffectiveDates": 5},
                               diagnostics={}, require_pit=True)
    assert calibration["available"] is False
    assert calibration["excludedLowPitObservations"] == len(poor)


def test_path_statistics_use_non_overlapping_dates_only():
    """Chaining overlapping 126-day returns would invent a drawdown."""
    index = pd.bdate_range("2015-01-02", periods=200)
    values = pd.Series(np.full(200, 0.02), index=index)
    summary = HC._summary_stats(values, horizon=126)
    assert summary["nonOverlappingDates"] <= 3
    # All-positive returns cannot produce a drawdown, however they are sampled.
    assert summary["mdd"] in (None, 0.0) or summary["mdd"] >= -1e-12


def test_evidence_weight_discounts_each_named_defect():
    clean = HC.evidence_weight(
        pit_coverage=0.95, survivorship_risk="LOW", macro_pit_status="PIT_EXACT",
        fundamentals_pit=True, regime_share=0.3, sector_share=0.2,
        fold_stable=True, effective_dates=100, min_effective_dates=30)
    dirty = HC.evidence_weight(
        pit_coverage=0.4, survivorship_risk="HIGH", macro_pit_status="REVISED_HISTORY",
        fundamentals_pit=False, regime_share=0.9, sector_share=0.8,
        fold_stable=False, effective_dates=5, min_effective_dates=30)
    assert clean["weight"] > dirty["weight"]
    assert clean["weight"] <= HC.HISTORICAL_BASE_WEIGHT
    assert dirty["weight"] >= HC.MIN_HISTORICAL_WEIGHT
    for defect in ("survivorship_unresolved", "macro_revised_history",
                   "fundamentals_not_point_in_time", "regime_concentration",
                   "sector_concentration", "fold_instability", "low_pit_coverage"):
        assert defect in dirty["penaltiesApplied"]


def test_historical_evidence_never_outweighs_prospective_evidence():
    assert HC.HISTORICAL_BASE_WEIGHT < HC.PROSPECTIVE_WEIGHT
    assert 0.5 <= HC.HISTORICAL_BASE_WEIGHT <= 0.8


# --------------------------------------------------------------------------- #
# Evidence combination
# --------------------------------------------------------------------------- #
HISTORICAL = {"expectedExcessReturnPct": 6.0, "standardErrorPct": 1.5,
              "effectiveDates": 84, "weight": 0.55}


def test_historical_prior_replaces_the_zero_fallback():
    """The core fix: no prospective history must not mean 'no edge'."""
    combined = EV.combine(HISTORICAL, None, prior_scale_pct=3.0)
    assert combined["posterior"]["expectedExcessReturnPct"] > 0
    assert combined["posterior"]["historicalWeightPct"] == 100.0
    assert combined["posterior"]["prospectiveWeightPct"] == 0.0
    # Still shrunk toward zero — a prior is not a promise.
    assert combined["posterior"]["expectedExcessReturnPct"] < 6.0


def test_no_evidence_at_all_still_yields_zero():
    combined = EV.combine(None, None, prior_scale_pct=3.0)
    assert combined["posterior"]["expectedExcessReturnPct"] == 0.0


def test_prospective_weight_rises_automatically_as_its_sample_grows():
    shares = []
    for dates, se in ((5, 5.0), (20, 3.0), (60, 1.5), (200, 0.8)):
        combined = EV.combine(
            HISTORICAL,
            {"expectedExcessReturnPct": 2.0, "standardErrorPct": se,
             "effectiveDates": dates},
            prior_scale_pct=3.0)
        shares.append(combined["posterior"]["prospectiveWeightPct"])
    assert shares == sorted(shares), shares
    assert shares[0] < 30 and shares[-1] > 70


def test_a_wider_confidence_interval_shrinks_the_posterior():
    tight = EV.combine({**HISTORICAL, "standardErrorPct": 0.5}, None, prior_scale_pct=3.0)
    wide = EV.combine({**HISTORICAL, "standardErrorPct": 6.0}, None, prior_scale_pct=3.0)
    assert (tight["posterior"]["expectedExcessReturnPct"]
            > wide["posterior"]["expectedExcessReturnPct"])


def test_drift_detection_only_ever_reduces_risk():
    worse = EV.drift_report(HISTORICAL, {"expectedExcessReturnPct": 1.0,
                                         "standardErrorPct": 1.0, "effectiveDates": 40})
    assert worse["detected"] is True
    assert worse["kellyMultiplier"] < 1.0

    better = EV.drift_report(HISTORICAL, {"expectedExcessReturnPct": 12.0,
                                          "standardErrorPct": 1.0, "effectiveDates": 40})
    assert better["detected"] is False
    assert better["kellyMultiplier"] == 1.0

    thin = EV.drift_report(HISTORICAL, {"expectedExcessReturnPct": 0.0,
                                        "standardErrorPct": 1.0, "effectiveDates": 3})
    assert thin["detected"] is False


def test_poor_prospective_results_never_raise_the_expected_return():
    baseline = EV.combine(HISTORICAL, None, prior_scale_pct=3.0)
    disappointing = EV.combine(
        HISTORICAL,
        {"expectedExcessReturnPct": -2.0, "standardErrorPct": 1.0, "effectiveDates": 60},
        prior_scale_pct=3.0)
    assert (disappointing["posterior"]["expectedExcessReturnPct"]
            < baseline["posterior"]["expectedExcessReturnPct"])


def test_activation_ladder_reports_which_evidence_is_carrying_the_estimate():
    assert EV.activation_status(historical=None, prospective=None,
                                min_effective_dates=30)["code"] == "NO_EVIDENCE"
    assert EV.activation_status(historical={"effectiveDates": 10}, prospective=None,
                                min_effective_dates=30)["code"] == "HISTORICAL_PRIOR_ONLY"
    assert EV.activation_status(historical=HISTORICAL, prospective=None,
                                min_effective_dates=30)["code"] == "HISTORICAL_OOS_SUPPORTED"
    early = EV.activation_status(historical=HISTORICAL,
                                 prospective={"effectiveDates": 5},
                                 min_effective_dates=30)
    assert early["code"] == "PROSPECTIVE_EARLY"
    confirmed = EV.activation_status(historical=HISTORICAL,
                                     prospective={"effectiveDates": 120},
                                     min_effective_dates=30)
    assert confirmed["code"] == "PROSPECTIVE_CONFIRMED"
    # Every rung has user-facing Korean copy, not just a code.
    for code in EV.ACTIVATION_LADDER:
        assert EV.ACTIVATION_KO[code] and EV.ACTIVATION_EXPLAIN_KO[code]


def test_portfolio_drift_takes_the_worst_region():
    region_evidence = {
        "KR": {"drift": {"detected": True, "kellyMultiplier": 0.4, "differencePct": -5.0}},
        "US": {"drift": {"detected": False, "kellyMultiplier": 1.0}},
    }
    result = EV.portfolio_drift(region_evidence)
    assert result["detected"] is True
    assert result["kellyMultiplier"] == 0.4
    assert result["regionsAffected"] == ["KR"]


# --------------------------------------------------------------------------- #
# Kelly wiring
# --------------------------------------------------------------------------- #
def _kelly_cfg():
    return {"horizonDays": 126, "minEffectiveDates": 5, "minUniqueDates": 5,
            "shrinkagePriorStrength": 5, "evidencePriorScalePct": 3.0,
            "activation": {"minPaperDays": 0, "minMaturedSignals": 0},
            "alphaPercentileBuckets": [0, 60, 80, 90, 95, 100],
            "transactionCosts": {"US": {"commissionBps": 5, "sellTaxBps": 3,
                                        "spreadBps": 10, "assumedTurnoverPct": 25,
                                        "rebalanceDays": 63}}}


def _calibration():
    return HC.calibrate(_ledger(), horizon=126,
                        cfg={"minEffectiveDates": 5, "shrinkagePriorStrength": 5},
                        diagnostics={"survivorshipRisk": "HIGH",
                                     "macroPitStatus": "REVISED_HISTORY",
                                     "fundamentalsPit": False})


def test_kelly_expected_return_is_zero_without_any_evidence():
    """The pre-existing safe behaviour must survive untouched."""
    got = KP.estimate_expected_returns(
        [{"ticker": "X", "region": "US", "alphaPercentile": 97}], [], _kelly_cfg(),
        as_of="2026-01-01")[0]
    assert got["expectedExcessReturnPct"] == 0.0
    assert got["status"] == "SHADOW_INSUFFICIENT_HISTORY"
    assert got.get("evidence") is None


def test_historical_prior_replaces_the_kelly_zero_fallback():
    got = KP.estimate_expected_returns(
        [{"ticker": "X", "region": "US", "alphaPercentile": 97}], [], _kelly_cfg(),
        as_of="2026-01-01", historical_calibration=_calibration())[0]
    assert got["prospectiveOnlyExpectedExcessReturnPct"] == 0.0
    assert got["expectedExcessReturnPct"] > 0.0
    assert got["status"] == "SHADOW"
    evidence = got["evidence"]
    assert evidence["posterior"]["historicalWeightPct"] == 100.0
    assert evidence["activation"]["code"] == "HISTORICAL_OOS_SUPPORTED"
    assert evidence["historicalBucket"] == "95-100"


def test_kelly_posterior_moves_toward_prospective_as_it_accumulates():
    calibration = _calibration()
    rng = np.random.default_rng(9)
    prospective = [
        {"id": f"p{i}", "date": d.strftime("%Y-%m-%d"), "ticker": "X", "region": "US",
         "alphaPercentile": 97, "sector": "Tech",
         "horizons": {"126": {"excessReturn": float(rng.normal(0.005, 0.02))}}}
        for i, d in enumerate(pd.bdate_range("2024-01-02", periods=120, freq="2B"))
    ]
    candidate = [{"ticker": "X", "region": "US", "alphaPercentile": 97}]
    prior_only = KP.estimate_expected_returns(candidate, [], _kelly_cfg(),
                                              as_of="2026-01-01",
                                              historical_calibration=calibration)[0]
    with_live = KP.estimate_expected_returns(candidate, prospective, _kelly_cfg(),
                                             as_of="2026-01-01",
                                             historical_calibration=calibration)[0]
    assert with_live["evidence"]["posterior"]["prospectiveWeightPct"] > 0
    # Live evidence of +0.5% must pull a +7% historical prior down, not up.
    assert (with_live["expectedExcessReturnPct"]
            < prior_only["expectedExcessReturnPct"])


def test_alpha_score_itself_never_becomes_an_expected_return():
    """Alpha selects a calibration bucket. It is never multiplied into a return."""
    calibration = _calibration()
    absurd = KP.estimate_expected_returns(
        [{"ticker": "X", "region": "US", "alpha": 9_999_999, "alphaPercentile": 97}],
        [], _kelly_cfg(), as_of="2026-01-01", historical_calibration=calibration)[0]
    normal = KP.estimate_expected_returns(
        [{"ticker": "Y", "region": "US", "alpha": 0.01, "alphaPercentile": 97}],
        [], _kelly_cfg(), as_of="2026-01-01", historical_calibration=calibration)[0]
    assert absurd["expectedExcessReturnPct"] == normal["expectedExcessReturnPct"]


def test_an_unknown_region_gets_no_historical_prior():
    got = KP.estimate_expected_returns(
        [{"ticker": "X", "region": "JP", "alphaPercentile": 97}], [], _kelly_cfg(),
        as_of="2026-01-01", historical_calibration=_calibration())[0]
    assert got["expectedExcessReturnPct"] == 0.0
    assert got.get("evidence") is None


def test_candidate_prior_is_absent_rather_than_zero_for_a_thin_bucket():
    thin = HC.calibrate([_outcome("2015-01-02", percentile=97, excess=0.2)],
                        horizon=126, cfg={"minEffectiveDates": 30}, diagnostics={})
    assert EV.candidate_prior(thin, "US", 97) is None


# --------------------------------------------------------------------------- #
# Partial-region fallback must publish no Kelly weights
# --------------------------------------------------------------------------- #
def _two_region_candidates() -> list[dict]:
    """Eight names across KR and US, all portfolio-eligible.

    Regions are optimized in sorted order, so KR runs first. The calibration
    fixture below covers KR only — that is what makes KR solve and US fail,
    which is the ordering required to leave a partial solution in the
    accumulator.
    """
    rows = []
    for i in range(8):
        region = "KR" if i % 2 == 0 else "US"
        rows.append({
            "ticker": f"{region}{i}", "region": region, "sector": f"S{i % 3}",
            "alpha": 1.0 - i * 0.01,
            "alphaPercentile": 92,
            "longTermResearchView": "POSITIVE", "valueTrap": False,
            "evidenceCoverage": 0.9, "dataCompleteness": 0.9,
            "risk": {"vol252Pct": 20 + i, "downsideVolPct": 15 + i},
            "entry": {"entryState": "ACCUMULATE_GRADUALLY"},
        })
    return rows


def _kr_only_calibration():
    """Calibration covering KR but not US — the ordinary asymmetric case."""
    rng = np.random.default_rng(3)
    rows = []
    for date in pd.bdate_range("2015-01-02", periods=90, freq="5B"):
        stamp = date.strftime("%Y-%m-%d")
        for percentile, mean in ((50, 0.005), (70, 0.015), (85, 0.030),
                                 (92, 0.045), (97, 0.070)):
            for k in range(3):
                rows.append(_outcome(stamp, percentile=percentile,
                                     excess=float(rng.normal(mean, 0.05)),
                                     region="KR", ticker=f"T{percentile}{k}"))
    return HC.calibrate(rows, horizon=126,
                        cfg={"minEffectiveDates": 5, "shrinkagePriorStrength": 5},
                        diagnostics={"survivorshipRisk": "HIGH",
                                     "macroPitStatus": "REVISED_HISTORY",
                                     "fundamentalsPit": False})


def _price_frames(tickers, periods=900) -> dict:
    rng = np.random.default_rng(4)
    index = pd.bdate_range("2021-01-04", periods=periods)
    out = {}
    for i, ticker in enumerate(tickers):
        close = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.012, periods)))
        out[ticker] = pd.DataFrame({"Close": close}, index=index)
    return out


def test_partial_region_kelly_solution_is_never_published_on_fallback():
    """A later region failing must not leave an earlier region's weights on show.

    Regions are optimized one at a time. Before expected returns could come
    from a historical prior this was unreachable, because an empty ledger made
    every region insufficient at once. With a prior, one region having a usable
    calibration bucket while the other does not is the ORDINARY case — and the
    accumulator would otherwise carry the solved region's weights into an
    artifact whose status says Kelly was not applied.
    """
    candidates = _two_region_candidates()
    tickers = [c["ticker"] for c in candidates]
    prices = _price_frames(tickers + ["SPY", "^KS200"])
    long_term = {"regions": {
        "KR": {"picks": [c for c in candidates if c["region"] == "KR"]},
        "US": {"picks": [c for c in candidates if c["region"] == "US"]},
    }}
    cfg = {**_kelly_cfg(), "enabled": True, "mode": "shadow",
           "minNames": 2, "maxNames": 8, "minNamesPerRegion": 2,
           "covarianceMinDays": 200, "covarianceLookbackDays": 400,
           "selection": {"targetNames": 8, "minNames": 2, "maxNamesPerSector": 8,
                         "maxNamesPerRegion": 8, "minAlphaPercentile": 50},
           "regionCaps": {"KR": 0.65, "US": 0.65}}

    portfolio = build_model_portfolio(
        long_term, prices, [], cfg,
        benchmarks={"KR": "^KS200", "US": "SPY"},
        bench_by_region={"KR": prices["^KS200"]["Close"], "US": prices["SPY"]["Close"]},
        as_of="2024-06-28", historical_calibration=_kr_only_calibration())

    if not portfolio.get("fallbackReason"):
        pytest.skip("this fixture did not reach the partial-region fallback path")
    # The invariant the validator enforces: a fallback exposes no Kelly weights.
    assert portfolio["constrainedKellyWeights"] == {}
    assert portfolio["kellyApplied"] is False
    assert portfolio["kellyAllocationImpactPct"] == 0.0
    for position in portfolio["positions"]:
        assert position["constrainedKellyWeightPct"] is None
        assert position["unconstrainedKellyWeightPct"] is None


def test_fallback_artifact_passes_the_kelly_weight_validator(tmp_path):
    """End-to-end: the same scenario must not trip `fallback_exposes_kelly_weights`."""
    from pipeline import validate as V

    candidates = _two_region_candidates()
    tickers = [c["ticker"] for c in candidates]
    prices = _price_frames(tickers + ["SPY", "^KS200"])
    long_term = {"regions": {
        "KR": {"picks": [c for c in candidates if c["region"] == "KR"]},
        "US": {"picks": [c for c in candidates if c["region"] == "US"]},
    }}
    cfg = {**_kelly_cfg(), "enabled": True, "mode": "shadow",
           "minNames": 2, "maxNames": 8, "minNamesPerRegion": 2,
           "covarianceMinDays": 200, "covarianceLookbackDays": 400,
           "selection": {"targetNames": 8, "minNames": 2, "maxNamesPerSector": 8,
                         "maxNamesPerRegion": 8, "minAlphaPercentile": 50},
           "regionCaps": {"KR": 0.65, "US": 0.65}}
    portfolio = build_model_portfolio(
        long_term, prices, [], cfg,
        benchmarks={"KR": "^KS200", "US": "SPY"},
        bench_by_region={"KR": prices["^KS200"]["Close"], "US": prices["SPY"]["Close"]},
        as_of="2024-06-28", historical_calibration=_kr_only_calibration())

    payload = {
        "portfolioName": "t", "meta": {"modelsTrained": 1, "coveragePct": 100},
        "generatedAt": "2024-06-28T00:00:00Z", "core": [], "screened": [],
        "tradeIdeas": {"KR": [], "US": []}, "runMode": "paperTrading",
        "schemaVersion": "2.4.0", "modelVersion": "test",
        "provenance": {"schemaVersion": "2.4.0", "modelVersion": "test",
                       "runMode": "paperTrading", "marketAsOf": "2024-06-28"},
        "modelPortfolio": portfolio, "recommendationsBlocked": False,
    }
    path = tmp_path / "artifact.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, default=str), encoding="utf-8")
    errors = V.validate(str(path), production=False)
    assert "fallback_exposes_kelly_weights" not in errors
    assert "fallback_exposes_position_kelly_weight" not in errors
    assert "fallback_has_nonzero_kelly_impact" not in errors
