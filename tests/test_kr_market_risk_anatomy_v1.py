"""Synthetic fixtures only. No real price, rate or outcome is read anywhere in this file."""
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from pipeline import kr_market_risk_anatomy as M
from pipeline import kr_market_risk_overlay as OV
from pipeline import kr_market_risk_sources as S
from pipeline.kr_model_portfolio_execution import digest

ROOT = Path(__file__).resolve().parents[1]
FROZEN_DESIGN_SHA256 = "3c398b6e87e6634443ffe25273f95ed100889515a71ddb66eb2ecd7035788aaa"


def sessions(start="2004-01-02", end="2012-12-28"):
    return M.kr_sessions(start, end)


def walk(n, seed=0, drift=0.0003, vol=0.01, start=100.0):
    rng = np.random.default_rng(seed)
    return start * np.cumprod(1 + rng.normal(drift, vol, n))


# --------------------------------------------------------------------------- #
# The frozen design
# --------------------------------------------------------------------------- #
def test_design_file_is_the_frozen_pre_source_design():
    path = ROOT / "research_specs/kr-market-risk-anatomy-v1-design.json"
    design = json.loads(path.read_text())
    assert digest(design) == FROZEN_DESIGN_SHA256 == path.with_suffix(".sha256").read_text().strip()
    assert design["scientificStatus"] == "EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY" == M.SCIENTIFIC_STATUS
    assert design["boundary"]["outcomeExecutionInThisChange"] is False and design["boundary"]["passFailSemantics"] == "NONE"
    assert any("not prospective confirmation" in line for line in design["scientificStatusMeaning"])
    assert design["architectureRole"]["layer"] == "MARKET" and "rank stocks" in design["architectureRole"]["mustNot"]


def test_design_is_exactly_what_the_builder_writes_from_the_module_registries():
    import importlib.util
    spec = importlib.util.spec_from_file_location("build_design", ROOT / "scripts/build_kr_market_risk_anatomy_design.py")
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    assert digest(builder.build()) == FROZEN_DESIGN_SHA256  # the code registries cannot drift from the frozen document


def test_every_registered_feature_has_family_tier_and_a_risk_orientation():
    assert set(M.FEATURES) == set(json.loads((ROOT / "research_specs/kr-market-risk-anatomy-v1-design.json").read_text())["features"])
    assert {v[0] for v in M.FEATURES.values()} == set(M.FAMILIES)
    assert {v[1] for v in M.FEATURES.values()} == set(M.TIERS)
    assert all(v[1] == ("EXTENDED_KR_INTERNALS" if n.startswith("int_") else "CORE_LONG_HISTORY") for n, v in M.FEATURES.items())
    assert M.HORIZONS["FAST_MARKET_BREAK"] == (21, 63) and M.HORIZONS["TRANSITION_FINANCIAL_STRESS"] == (63, 126) and M.HORIZONS["SLOW_VULNERABILITY"] == (126, 252)
    assert M.LOSS_CUTS == (-0.10, -0.15, -0.20) and M.PRIMARY_EPISODE_THRESHOLD == 0.15
    assert M.CADENCE["SLOW_VULNERABILITY"] == "M" and M.CADENCE["TRANSITION_FINANCIAL_STRESS"] == "W"


# --------------------------------------------------------------------------- #
# Point-in-time knowledge
# --------------------------------------------------------------------------- #
def test_no_future_observation_reaches_a_session():
    days = sessions("2010-01-04", "2010-03-31")
    obs = pd.Series(np.arange(1.0, 120.0), index=pd.date_range("2009-12-01", periods=119, freq="D"))
    base, dates = M.known_on_sessions(obs, days, lag_days=4)
    for day in days[::7]:
        assert pd.Timestamp(dates[day]) + pd.Timedelta(days=4) <= day  # only observations already available
    future = obs.copy()
    future.loc["2010-02-15":] = 1e9  # observations after t cannot move any value known at t
    moved, _ = M.known_on_sessions(future, days, lag_days=4)
    cut = pd.Timestamp("2010-02-15") + pd.Timedelta(days=4)
    assert base[days < cut].equals(moved[days < cut])


def test_lag_and_staleness_are_exact():
    days = pd.DatetimeIndex(["2020-01-06", "2020-01-07", "2020-01-08", "2020-01-31"])
    obs = pd.Series([1.0, 2.0], index=pd.to_datetime(["2020-01-03", "2020-01-06"]))
    value, obs_date = M.known_on_sessions(obs, days, lag_days=4, stale_days=14)
    assert np.isnan(value.iloc[0])  # 2020-01-03 + 4 days = 01-07: not yet known on 01-06
    assert value.iloc[1] == 1.0 and obs_date.iloc[1] == pd.Timestamp("2020-01-03")
    assert value.iloc[2] == 1.0 and value.iloc[3] != value.iloc[3]  # the carried value expires after 14 days: missing, not extended
    zero, _ = M.known_on_sessions(obs, days, lag_days=0)
    assert zero.iloc[0] == 2.0 and zero.iloc[3] == 2.0  # a KR index close with lag 0 is known the same day (the 01-06 observation on 01-06)


def test_slower_series_use_only_the_latest_known_observation_and_are_not_independent_rows():
    days = sessions("2010-01-04", "2011-12-30")
    monthly = pd.Series(np.arange(24.0), index=pd.date_range("2010-01-29", periods=24, freq="ME"))
    daily, _ = M.known_on_sessions(monthly, days, lag_days=4)
    assert daily.nunique() <= 24  # 500 carried daily rows carry at most 24 distinct values
    grid = M.period_end_dates(days, "M")
    assert M.assert_cadence(grid, "M", days) is True
    with pytest.raises(ValueError, match="ROWS_OFF_THE_REGISTERED_CADENCE"):
        M.assert_cadence(days[:30], "M", days)  # daily carried rows are not slow-family evidence


def test_expanding_percentile_is_end_date_invariant_and_past_only():
    x = pd.Series(walk(400, seed=3))
    full = M.expanding_percentile(x, 36)
    for cut in (60, 150, 399):
        part = M.expanding_percentile(x.iloc[:cut], 36)
        assert np.allclose(part.to_numpy(), full.iloc[:cut].to_numpy(), equal_nan=True)  # the state at t does not depend on later data
    assert full.iloc[:35].isna().all() and full.iloc[35:].notna().all()
    assert M.expanding_percentile(pd.Series([1, 2, 2, 3.0] * 20), 4).iloc[3] == pytest.approx((3 + 0.5 * 1) / 4)  # mid-rank of a new maximum among 4
    nan_x = x.copy()
    nan_x.iloc[50] = np.nan
    assert np.isnan(M.expanding_percentile(nan_x, 36).iloc[50])  # missing stays missing


def test_revised_history_cannot_masquerade_as_pit_exact():
    for sid, entry in S.SOURCES.items():
        eligible = M.classify_source(entry)
        assert eligible == (entry["vintageClass"] in M.PREDICTOR_ELIGIBLE_CLASSES)
        assert not (entry["vintageClass"] == "PIT_EXACT")  # no source in this registry has release evidence
        assert not (eligible and entry.get("vendor", "").startswith(("ECOS", "FRED_OECD")))
    with pytest.raises(ValueError, match="PIT_EXACT_REQUIRES_RELEASE_EVIDENCE"):
        M.classify_source({"vintageClass": "PIT_EXACT", "vendor": "FRED"})
    with pytest.raises(ValueError, match="ECOS_IS_REVISED_HISTORY"):
        M.classify_source({"vintageClass": "MARKET_OBSERVED_UNREVISED_APPROXIMATE_AVAILABILITY", "vendor": "ECOS"})
    for sid in ("ECOS_LEADING_INDEX", "ECOS_BASE_RATE", "ECOS_KTB_3Y", "FRED_NFCI", "FRED_ANFCI", "FRED_OECD_KR_10Y", "FRED_OECD_KR_3M"):
        assert S.SOURCES[sid]["vintageClass"] == "REVISED_HISTORY" and S.SOURCES[sid]["fetch"] is None and sid in S.EXCLUDED_IDS
    for sid in ("EXCESS_BOND_PREMIUM", "NEAR_TERM_FORWARD_SPREAD", "KR_TERM_SPREAD"):
        assert S.SOURCES[sid]["vintageClass"] == "NOT_AVAILABLE" and S.SOURCES[sid]["fetch"] is None
    assert S.validate_registry() and all(S.SOURCES[s]["vintageClass"] in M.PREDICTOR_ELIGIBLE_CLASSES for s in S.ACQUIRED_IDS)


def test_slow_and_transition_features_use_only_data_known_at_t():
    days = sessions("2005-01-03", "2011-12-30")
    idx = pd.date_range("2004-06-01", "2011-12-30", freq="B")
    rng = np.random.default_rng(1)
    s3 = pd.Series(np.cumsum(rng.normal(0, 0.05, len(idx))), index=idx)
    dff = pd.Series(2 + np.cumsum(rng.normal(0, 0.02, len(idx))), index=idx)

    def build(s3_obs, dff_obs):
        known = {"spread_10y3m": M.known_on_sessions(s3_obs, days, 4, 14)[0], "dff": M.known_on_sessions(dff_obs, days, 4, 14)[0]}
        weekly = M.period_end_dates(days, "W")
        return M.slow_features(known, days), M.transition_features(known, days, weekly)
    slow, trans = build(s3, dff)
    cut = pd.Timestamp("2008-06-30")
    s3b, dffb = s3.copy(), dff.copy()
    s3b[s3b.index > cut - pd.Timedelta(days=4)] += 50
    dffb[dffb.index > cut - pd.Timedelta(days=4)] -= 50
    slow2, trans2 = build(s3b, dffb)
    before = days[days <= cut]
    assert slow.loc[before].equals(slow2.loc[before]) or np.allclose(slow.loc[before].to_numpy(), slow2.loc[before].to_numpy(), equal_nan=True)
    assert np.allclose(trans.loc[before].to_numpy(), trans2.loc[before].to_numpy(), equal_nan=True)
    assert not np.allclose(slow.loc[days > cut + pd.Timedelta(days=30)].to_numpy(), slow2.loc[days > cut + pd.Timedelta(days=30)].to_numpy(), equal_nan=True)


def test_features_keep_their_own_coverage_and_are_not_truncated_to_a_common_period():
    days = sessions("2005-01-03", "2011-12-30")
    long_idx = pd.date_range("2004-06-01", "2011-12-30", freq="B")
    late_idx = pd.date_range("2010-06-01", "2011-12-30", freq="B")
    known = {"spread_10y3m": M.known_on_sessions(pd.Series(1.0, index=long_idx), days, 4, 14)[0],
             "hy": M.known_on_sessions(pd.Series(5.0, index=late_idx), days, 4, 14)[0], "dff": M.known_on_sessions(pd.Series(1.0, index=long_idx), days, 4, 14)[0]}
    slow = M.slow_features(known, days)
    trans = M.transition_features(known, days, M.period_end_dates(days, "W"))
    assert slow.dropna(how="all").index[0] < pd.Timestamp("2005-02-01")  # the slow family starts with its own data
    assert trans["trans_hy_oas_level"].dropna().index[0] >= pd.Timestamp("2010-06-01")  # a late feature stays late and truncates nothing else
    assert slow.loc[days < pd.Timestamp("2010-06-01"), "slow_us_10y3m_flatness"].notna().sum() > 1000


def test_inversion_duration_and_resteepening():
    s = pd.Series([0.5, -0.1, -0.2, np.nan, -0.1, 0.3, -0.2])
    assert M.inversion_duration(s).tolist()[:3] == [0.0, 1.0, 2.0] and np.isnan(M.inversion_duration(s).iloc[3])
    assert M.inversion_duration(s).iloc[4] == 1.0 and M.inversion_duration(s).iloc[5] == 0.0
    days = sessions("2006-01-02", "2009-12-30")
    spread = pd.Series(np.where(np.arange(len(days)) < 700, -0.4, 0.4), index=days)
    out = M.slow_features({"spread_10y3m": spread}, days)
    assert out["slow_resteepening_flag_10y3m"].iloc[800] == 1.0 and out["slow_resteepening_flag_10y3m"].iloc[600] == 0.0
    assert out["slow_us_10y3m_flatness"].iloc[10] == pytest.approx(0.4)  # orientation: inverted = more risk


def test_easing_after_vulnerability_is_distinct_from_benign_easing():
    days = sessions("2004-01-02", "2012-12-28")
    n = len(days)
    dff = pd.Series(np.concatenate([np.full(1500, 5.0), np.linspace(5.0, 1.0, 300), np.full(n - 1800, 1.0)]), index=days)
    inverted = pd.Series(np.where(np.arange(n) < 1400, -0.3, 0.8), index=days)
    never = pd.Series(0.8, index=days)
    stress = pd.Series(np.concatenate([np.full(1500, 4.0), np.linspace(4, 20, n - 1500)]), index=days)
    calm = pd.Series(4.0, index=days)
    weekly = M.period_end_dates(days, "W")
    after = M.transition_features({"dff": dff, "spread_10y3m": inverted, "hy": stress, "vix": stress}, days, weekly)
    benign = M.transition_features({"dff": dff, "spread_10y3m": never, "hy": calm, "vix": calm}, days, weekly)
    probe = 1700
    assert after["trans_easing_flag"].iloc[probe] == 1.0 and after["trans_easing_after_inversion_flag"].iloc[probe] == 1.0
    assert after["trans_post_vulnerability_stress_easing_hy_flag"].iloc[probe] == 1.0 and after["trans_benign_easing_flag"].iloc[probe] == 0.0
    assert benign["trans_benign_easing_flag"].iloc[probe] == 1.0 and benign["trans_post_vulnerability_stress_easing_hy_flag"].iloc[probe] == 0.0
    assert benign["trans_easing_after_inversion_flag"].iloc[probe] == 0.0


# --------------------------------------------------------------------------- #
# Future-path targets, episodes and early damage (exact arithmetic on hand-made paths)
# --------------------------------------------------------------------------- #
def test_forward_worst_loss_and_max_drawdown_on_a_synthetic_path():
    c = np.array([100, 110, 99, 105, 80, 90, 95.0])
    t = M.forward_targets(c, 4)
    assert t.status.tolist() == ["MATURED", "MATURED", "MATURED", "PENDING", "PENDING", "PENDING", "PENDING"]
    assert t.forwardReturn.iloc[0] == pytest.approx(80 / 100 - 1) and t.forwardWorstLoss.iloc[0] == pytest.approx(80 / 100 - 1)
    assert t.futureMaxDrawdown.iloc[0] == pytest.approx(80 / 110 - 1)  # peak 110 to trough 80
    assert t.forwardWorstLoss.iloc[1] == pytest.approx(80 / 110 - 1) and t.futureMaxDrawdown.iloc[1] == pytest.approx(80 / 110 - 1)
    rets = np.array([110 / 100 - 1, 99 / 110 - 1, 105 / 99 - 1, 80 / 105 - 1])
    assert t.futureRealizedVol.iloc[0] == pytest.approx(np.std(rets, ddof=1) * math.sqrt(252))
    rising = M.forward_targets(np.array([100, 101, 102, 103, 104.0]), 3)
    assert rising.forwardWorstLoss.iloc[0] == pytest.approx(101 / 100 - 1) and rising.forwardWorstLoss.iloc[0] > 0 and rising.futureMaxDrawdown.iloc[0] == 0.0  # worst "loss" may be positive


def test_missing_session_is_unresolved_never_filled_and_pending_is_pending():
    c = np.array([100, 101, np.nan, 103, 104, 105.0])
    t = M.forward_targets(c, 3)
    assert t.status.tolist()[:3] == ["UNRESOLVED_MISSING_SESSION", "UNRESOLVED_MISSING_SESSION", "UNRESOLVED_MISSING_SESSION"]
    assert t.forwardReturn.iloc[:3].isna().all() and t.status.iloc[3:].eq("PENDING").all()
    assert M.forward_targets(np.array([100, 0.0, 101, 102]), 2).status.iloc[0] == "UNRESOLVED_MISSING_SESSION"


@pytest.mark.parametrize("worst,expected", [(-0.0999, (0, 0, 0)), (-0.10, (1, 0, 0)), (-0.1499, (1, 0, 0)), (-0.15, (1, 1, 0)), (-0.20, (1, 1, 1)), (-0.5, (1, 1, 1))])
def test_loss_label_boundaries_are_inclusive(worst, expected):
    labels = M.loss_labels(pd.Series([worst]))
    assert tuple(int(labels[k].iloc[0]) for k in ("loss_le_10", "loss_le_15", "loss_le_20")) == expected
    assert np.isnan(M.loss_labels(pd.Series([np.nan]))["loss_le_10"].iloc[0])


def test_underwater_episodes_peak_trough_recovery_and_censoring():
    c = np.array([100, 90, 80, 85, 100, 95, 70, 75, 100.0, 120, 108, 100, 104])
    eps = M.underwater_episodes(c)
    assert [(e["peakPos"], e["troughPos"], e["recoveryPos"], e["censored"]) for e in eps] == [(0, 2, 4, False), (4, 6, 8, False), (9, 11, None, True)]
    assert eps[0]["depth"] == pytest.approx(-0.20) and eps[1]["depth"] == pytest.approx(70 / 100 - 1) and eps[2]["depth"] == pytest.approx(100 / 120 - 1)
    tie = M.underwater_episodes(np.array([100, 90, 100, 90, 100.0]))  # an equal high RECOVERS and restarts the peak at that date
    assert [(e["peakPos"], e["recoveryPos"]) for e in tie] == [(0, 2), (2, 4)]
    first_low = M.underwater_episodes(np.array([100, 80, 90, 80, 100.0]))
    assert first_low[0]["troughPos"] == 1  # the FIRST lowest close is the trough
    assert M.underwater_episodes(np.array([100, np.nan, 90, 100.0]))[0]["peakPos"] == 0  # missing sessions are skipped, not filled


def test_episode_thresholds_are_inclusive_and_deterministic():
    c = np.array([100, 90, 100, 85, 100, 80, 100.0])
    eps = M.underwater_episodes(c)
    assert [round(e["depth"], 4) for e in eps] == [-0.10, -0.15, -0.20]
    assert len(M.episodes_at_least(eps, 0.10)) == 3 and len(M.episodes_at_least(eps, 0.15)) == 2 and len(M.episodes_at_least(eps, 0.20)) == 1
    assert M.underwater_episodes(c) == M.underwater_episodes(c.copy())
    rng = np.random.default_rng(9)
    path = 100 * np.cumprod(1 + rng.normal(0, 0.02, 3000))
    again = M.underwater_episodes(pd.Series(path, index=pd.RangeIndex(3000)))
    assert again == M.underwater_episodes(path) and all(e["depth"] < 0 and e["troughPos"] > e["peakPos"] for e in again)


def test_episode_landmarks_are_fixed_positions():
    c = np.concatenate([np.linspace(50, 100, 300), np.linspace(99, 70, 40), np.linspace(71, 120, 80)])
    ep = M.underwater_episodes(c)[0]
    lm = M.episode_landmarks(c, ep)
    assert lm["peak"] == ep["peakPos"] == 299 and lm["peak-252"] == 47 and lm["peak-21"] == 278 and lm["trough"] == ep["troughPos"]
    assert c[lm["first_drawdown_5"]] / 100 - 1 <= -0.05 and c[lm["first_drawdown_5"] - 1] / 100 - 1 > -0.05
    assert lm["first_drawdown_5"] < lm["first_drawdown_10"] < lm["first_drawdown_15"] <= lm["trough"]
    shallow = M.episode_landmarks(np.array([100, 97, 100.0]), M.underwater_episodes(np.array([100, 97, 100.0]))[0])
    assert shallow["first_drawdown_5"] is None and shallow["peak-252"] is None  # a landmark that does not exist is None


def test_damage_fraction_arithmetic_and_statuses():
    c = np.array([100, 95, 90, 80, 70, 75, 100.0])
    ep = M.underwater_episodes(c)[0]
    on = np.array([0, 0, 1, 1, 1, 0, 0.0])
    r = M.first_trigger_damage(c, ep, on)
    assert r["status"] == "TRIGGERED" and r["triggerPos"] == 2 and r["triggerDelaySessions"] == 2
    assert r["lossAtTrigger"] == pytest.approx(-0.10) and r["damageFraction"] == pytest.approx(0.10 / 0.30)
    assert r["remainingDrawdownAfterTrigger"] == pytest.approx(70 / 90 - 1) and r["alreadyOnAtPeak"] is False
    early = M.first_trigger_damage(c, ep, np.array([1, 1, 1, 1, 1, 0, 0.0]))
    assert early["alreadyOnAtPeak"] is True and early["lossAtTrigger"] == 0.0 and early["damageFraction"] == 0.0 and early["triggerDelaySessions"] == 0
    assert M.first_trigger_damage(c, ep, np.zeros(7))["status"] == "MISSED"
    assert M.first_trigger_damage(c, ep, np.array([0, 0, 0, 0, 0, 1, 1.0]))["status"] == "ACTIVATED_AFTER_TROUGH"
    assert M.first_trigger_damage(c, ep, np.full(7, np.nan))["status"] == "STATE_UNAVAILABLE"
    summary = M.damage_summary([r, early, {"status": "MISSED"}, {"status": "ACTIVATED_AFTER_TROUGH"}])
    assert summary["episodes"] == 4 and summary["triggered"] == 2 and summary["missed"] == 2
    assert summary["shareTriggeredBefore20pctOfDrawdown"] == pytest.approx(1 / 4) and summary["shareTriggeredBefore50pctOfDrawdown"] == pytest.approx(2 / 4)  # fractions 0.0 and 1/3 of 4 episodes
    assert summary["damageFractions"] == sorted(summary["damageFractions"])
    none_triggered = M.damage_summary([{"status": "MISSED"}, {"status": "MISSED"}])
    assert none_triggered["shareTriggeredBefore20pctOfDrawdown"] == 0.0 and none_triggered["shareTriggeredBefore50pctOfDrawdown"] == 0.0 and none_triggered["triggered"] == 0  # not NaN
    assert M.damage_summary([])["shareTriggeredBefore20pctOfDrawdown"] is None


def test_slow_pre_peak_warning_is_kept_separate_from_the_fast_trigger():
    c = np.concatenate([np.linspace(100, 200, 400), np.linspace(199, 120, 60), np.linspace(121, 250, 100)])
    ep = M.underwater_episodes(c)[0]
    slow_on = np.zeros(len(c))
    slow_on[100:380] = 1  # on for 280 sessions, then off BEFORE the peak
    r = M.slow_warning_lead(slow_on, ep)
    assert r["status"] == "ON_THEN_OFF" and r["sessionsSinceLastOn"] == ep["peakPos"] - 379
    slow_on[100:] = 1
    r = M.slow_warning_lead(slow_on, ep)
    assert r["status"] == "ACTIVE_AT_PEAK" and r["leadSessions"] == ep["peakPos"] - 100
    assert M.slow_warning_lead(np.zeros(len(c)), ep)["status"] == "NEVER_ON_BEFORE_PEAK"
    fast = M.first_trigger_damage(c, ep, np.concatenate([np.zeros(430), np.ones(len(c) - 430)]))
    assert fast["status"] == "TRIGGERED" and "leadSessions" not in fast and fast["triggerDelaySessions"] == 430 - ep["peakPos"]


def test_trigger_profile_counts_false_alarms_and_normalisation():
    c = np.concatenate([np.linspace(100, 100, 5) + np.arange(5) * 0.01, np.linspace(100, 70, 40), np.linspace(71, 110, 60)])
    eps = M.episodes_at_least(M.underwater_episodes(c), 0.15)
    on = np.zeros(len(c))
    on[10:60] = 1
    prof = M.trigger_profile(on, c, eps, horizons=(21,))
    assert prof["activations"] == 1 and prof["adverseSessions"] == 50 and prof["adverseShare"] == pytest.approx(50 / len(c))
    norm = prof["normalisation"][0]
    assert norm["status"] == "NORMALISED" and norm["delaySessions"] > 0 and norm["returnMissedBeforeNormalisation"] > 0
    cell = prof["followed"]["H21|loss_le_10"]
    assert cell["onSessions"] > 0 and cell["rateWhenOn"] is not None
    never_off = M.trigger_profile(np.ones(len(c)), c, eps, horizons=(21,))
    assert never_off["normalisation"][0]["status"] == "NEVER_NORMALISED_IN_SAMPLE" and never_off["activations"] == 1
    calm = np.linspace(100, 130, 200)
    flat = M.trigger_profile(np.concatenate([np.zeros(20), np.ones(30), np.zeros(150)]), calm, [], horizons=(63,))
    assert flat["activationStreaksH63"]["matured"] == 1 and flat["activationStreaksH63"]["share"] == 1.0  # a false alarm: no -10% drawdown follows


# --------------------------------------------------------------------------- #
# The existing overlay is reproduced exactly
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("seed,vol", [(0, 0.008), (1, 0.02), (2, 0.03)])
def test_existing_overlay_is_reproduced_exactly(seed, vol):
    days = M.kr_sessions("2012-06-01", "2015-12-30")
    close = pd.Series(walk(len(days), seed=seed, vol=vol), index=days)
    frame = pd.DataFrame({"Close": close})
    counts = M.overlay_count_series(close)
    states = M.baseline_trigger_states(close)
    checked = 0
    for date in days[450::17]:
        ref = OV.state_at(frame, str(date.date()))
        mine = M.overlay_state_from_window(close.loc[:date].iloc[-201:])
        assert ref["status"] == mine["status"] == "READY"
        assert ref["riskMultiplier"] == mine["riskMultiplier"] and ref["trendAdverse"] == mine["trendAdverse"] and ref["volAdverse"] == mine["volAdverse"]
        assert ref["benchmarkVol63"] == mine["benchmarkVol63"]
        assert counts.loc[date] == (int(ref["trendAdverse"]) + int(ref["volAdverse"]))
        assert states.loc[date, "B1_TREND_ADVERSE"] == float(ref["trendAdverse"]) and states.loc[date, "B2_VOL_ADVERSE"] == float(ref["volAdverse"])
        assert states.loc[date, "B3_OVERLAY_ANY"] == float(counts.loc[date] >= 1) and states.loc[date, "B4_OVERLAY_BOTH"] == float(counts.loc[date] >= 2)
        checked += 1
    assert checked > 20
    hole = close.copy()
    hole.iloc[500] = np.nan
    date = days[520]
    assert OV.state_at(pd.DataFrame({"Close": hole}), str(date.date()))["status"] == M.overlay_state_from_window(hole.loc[:date].iloc[-201:])["status"] == "DATA_INSUFFICIENT"


def test_overlay_constants_and_multiplier_mapping():
    assert M.OVERLAY_MULTIPLIERS == (1.0, 0.7, 0.4) and M.OVERLAY_VOL_THRESHOLD == 0.25
    assert M.overlay_state_from_window(pd.Series(np.linspace(100, 200, 201)))["riskMultiplier"] == 1.0  # rising, calm
    assert M.overlay_state_from_window(pd.Series(np.linspace(200, 100, 201)))["riskMultiplier"] == 0.7  # falling below SMA200, calm
    assert M.overlay_state_from_window(pd.Series(np.linspace(100, 200, 50)))["status"] == "DATA_INSUFFICIENT"


def test_fast_features_are_past_only_and_oriented_as_risk():
    c = pd.Series(walk(600, seed=4), index=pd.RangeIndex(600))
    f = M.fast_features(c)
    bumped = c.copy()
    bumped.iloc[400:] *= 3.0
    g = M.fast_features(bumped)
    assert f.iloc[:400].equals(g.iloc[:400]) or np.allclose(f.iloc[:400].to_numpy(), g.iloc[:400].to_numpy(), equal_nan=True)
    steady = M.fast_features(pd.Series(np.linspace(100, 200, 300)))
    crashing = M.fast_features(pd.Series(np.linspace(200, 100, 300)))
    for name in ("fast_trend_distance_sma200", "fast_ret_63", "fast_drawdown_252", "fast_sma200_slope_21"):
        assert crashing[name].iloc[-1] > steady[name].iloc[-1]  # a falling market is MORE risky on every oriented feature
    assert steady["fast_drawdown_252"].iloc[-1] == pytest.approx(0.0)


# --------------------------------------------------------------------------- #
# Statistics
# --------------------------------------------------------------------------- #
def test_time_series_statistics_exact_small_cases():
    x = np.arange(60.0)
    assert M.ts_spearman(x, x)["rho"] == pytest.approx(1.0) and M.ts_spearman(x, -x)["rho"] == pytest.approx(-1.0)
    assert M.ts_spearman(x[:10], x[:10])["rho"] is None  # fewer than 36 observations
    h = M.rank_corr_hac(x, x + np.random.default_rng(0).normal(0, 3, 60), lag=3)
    assert 0.5 < h["rho"] <= 1 and h["hacSe"] > 0 and h["n"] == 60
    score = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20.0])
    label = np.array([0] * 10 + [1] * 10)
    assert M.auroc(score, label)["auroc"] == pytest.approx(1.0) and M.auroc(score, 1 - label)["auroc"] == pytest.approx(0.0)
    assert M.auroc(score[:15], label[:15])["auroc"] is None and M.auroc(np.ones(20), label)["auroc"] == pytest.approx(0.5)
    rates = M.event_rates(np.array([1, 0, 1, 0, 0, 0.0]), np.array([1, 1, 0, 0, np.nan, 0.0]))
    assert rates["n"] == 6 and rates["events"] == 2 and rates["nHigh"] == 2 and rates["eventsHigh"] == 1 and rates["rateNotHigh"] == pytest.approx(1 / 3)


def test_feature_statistics_use_cadence_rows_event_counts_and_period():
    days = sessions("2006-01-02", "2010-12-30")
    close = pd.Series(walk(len(days), seed=5, vol=0.012), index=days)
    grid = M.period_end_dates(days, "W")
    feature = M.fast_features(close)["fast_realized_vol_63"].reindex(grid)
    targets = M.forward_targets(close, 63).reindex(grid)
    out = M.feature_statistics(grid, feature, targets, "W", 63)
    M.assert_cadence(grid, "W", days)
    assert out["validDates"] == int(feature.notna().sum() - (targets.status != "MATURED").loc[feature.notna()].sum())
    assert out["start"] and out["end"] and out["events"]["loss_le_10"]["rates"]["n"] == int(targets.status.eq("MATURED").sum())
    assert out["spearmanVersusLossSeverity"]["rho"] is not None and set(out["byYear"]) >= {"2007", "2008"}
    M.assert_no_forbidden_keys(out)
    with pytest.raises(ValueError):
        M.assert_no_forbidden_keys({"bestTrigger": 1})


def test_internals_features_missing_stays_missing_and_orientation():
    r = np.array([0.1, -0.1, 0.2, 0.3, -0.2, 0.05])
    above = np.array([1, 0, 1, 1, 0, 1.0])
    caps = np.array([100, 90, 80, 70, 60, 50.0])
    f = M.internals_features(r, above, caps)
    assert f["int_breadth_above_sma200"] == pytest.approx(-4 / 6) and f["int_positive_breadth_63"] == pytest.approx(-4 / 6)
    assert f["int_concentration_top5_share"] == pytest.approx(400 / 450) and f["int_dispersion_63"] == pytest.approx(np.std(r))
    assert f["int_capweight_minus_equalweight_63"] == pytest.approx(float((caps / caps.sum() * r).sum() - r.mean()))
    g = M.internals_features(np.array([0.1, np.nan, 0.2]), above[:3], caps[:3])
    assert np.isnan(g["int_positive_breadth_63"]) and np.isnan(g["int_dispersion_63"]) and not np.isnan(g["int_breadth_above_sma200"])
    assert set(M.internals_features(r, above, caps)) == {n for n in M.FEATURES if n.startswith("int_")}


# --------------------------------------------------------------------------- #
# Source selection and readiness gates (dates only)
# --------------------------------------------------------------------------- #
def audit_for(days, start, end=None, **extra):
    d = days[(days >= pd.Timestamp(start)) & (days <= pd.Timestamp(end or days[-1]))]
    return {"status": "ACQUIRED", "dates": list(d), "rows": len(d), "dropped": 0, "identityOk": True, **extra}


def test_primary_reference_rule_never_substitutes_silently():
    days = M.kr_sessions("1999-01-04", "2026-09-30")
    acquired_on = "2026-10-02"
    good = audit_for(days, "1999-01-04")
    late = audit_for(days, "2010-01-04")
    # the preferred KOSPI 200 route passes -> chosen, composite not considered
    d = S.select_primary_reference({"YAHOO_KS200": good, "FDR_KS200": good, "YAHOO_KS11": good}, days, acquired_on)
    assert d["primary"] == "YAHOO_KS200" and d["composite"] is False and d["basis"] == "PRICE_INDEX_LEVEL" and "YAHOO_KS11" not in d["evaluated"]
    # the first fails coverage -> the SECOND KOSPI 200 route, not the composite
    d = S.select_primary_reference({"YAHOO_KS200": late, "FDR_KS200": good, "YAHOO_KS11": good}, days, acquired_on)
    assert d["primary"] == "FDR_KS200" and d["evaluated"]["YAHOO_KS200"]["eligible"] is False
    assert any(r.startswith("HISTORY_STARTS_AFTER") for r in d["evaluated"]["YAHOO_KS200"]["reasons"])
    # no KOSPI 200 route -> the composite only, and the decision says so
    d = S.select_primary_reference({"YAHOO_KS200": late, "FDR_KS200": None, "YAHOO_KS11": good}, days, acquired_on)
    assert d["primary"] == "YAHOO_KS11" and d["composite"] is True and d["family"] == "KOSPI_COMPOSITE"
    # the ETF robustness reference and the documented-blocker official route are never primary
    d = S.select_primary_reference({"YAHOO_069500": good, "KRX_OPENAPI_KOSPI200": good}, days, acquired_on)
    assert d["decision"] == "NO_ELIGIBLE_PRIMARY_REFERENCE" and d["primary"] is None
    assert "DOCUMENTED_BLOCKER" in d["evaluated"]["KRX_OPENAPI_KOSPI200"]["reasons"][0] and "YAHOO_069500" not in d["evaluated"]


def test_reference_tests_cover_staleness_gaps_identity_and_conflicts():
    days = M.kr_sessions("1999-01-04", "2026-09-30")
    acquired_on = "2026-10-02"
    ok = lambda audit: S.reference_eligibility("YAHOO_KS200", audit, days, acquired_on)  # noqa: E731
    base = audit_for(days, "1999-01-04")
    assert ok(base) == (True, [])
    stale = audit_for(days, "1999-01-04", "2026-06-30")
    assert "STALE_LAST_DATE" in ok(stale)[1]
    gap = dict(base, dates=[d for d in base["dates"] if not (pd.Timestamp("2008-09-01") <= d <= pd.Timestamp("2008-09-12"))])
    reasons = ok(gap)[1]
    assert "MISSING_RUN_TOO_LONG" in reasons and any(r.startswith("COVERAGE_BELOW") for r in reasons)
    assert "IDENTITY_CHECK_FAILED" in ok(dict(base, identityOk=False))[1]
    assert "TOO_MANY_INVALID_ROWS" in ok(dict(base, dropped=len(base["dates"])))[1]
    assert ok({"status": "FAILED"}) == (False, ["NOT_ACQUIRED"])
    a = pd.Series(np.linspace(100, 200, 400), index=days[:400])
    assert S.vendor_cross_check(a, a * 1.0001)["status"] == "CONSISTENT"
    assert S.vendor_cross_check(a, a * 1.02)["status"] == "CONFLICT" and S.vendor_cross_check(a[:50], a[:50])["status"] == "INSUFFICIENT_OVERLAP"
    d = S.select_primary_reference({"YAHOO_KS200": base, "FDR_KS200": base}, days, acquired_on, {"YAHOO_KS200|FDR_KS200": {"status": "CONFLICT"}})
    assert d["primary"] is None  # a vendor conflict blocks the choice


def test_core_gates_ready_only_when_every_family_covers_2007_2009_and_2020():
    days = M.kr_sessions("1999-01-04", "2026-09-30")
    acquired_on = "2026-10-02"
    audits = {sid: audit_for(days, "1999-01-04") for sid in ("YAHOO_KS200", "FRED_DGS10", "FRED_DGS3MO", "FRED_DGS2", "FRED_DFF", "FRED_VIXCLS", "FRED_DEXKOUS")}
    audits["FRED_BAMLH0A0HYM2"] = audit_for(days, "2023-10-02")  # a late candidate: its own coverage table, NOT a gate failure
    ref = S.select_primary_reference(audits, days, acquired_on)
    roles = {"VIX": "FRED_VIXCLS", "USDKRW": "FRED_DEXKOUS"}
    out = S.core_gates(audits, ref, roles, days, acquired_on)
    assert out["decision"] == "READY_FOR_MARKET_RISK_ANATOMY_EXECUTION" and out["blockers"] == []
    assert out["coverage"]["TRANSITION_GFC_2007_2009"]["trans_hy_oas_level"] in (0.0, None) or out["coverage"]["TRANSITION_GFC_2007_2009"]["trans_hy_oas_level"] < 0.5
    assert out["coverage"]["TRANSITION_GFC_2007_2009"]["trans_vix_level"] >= 0.95
    # remove every transition source in the GFC window -> blocked with the exact gate named
    broken = {k: v for k, v in audits.items() if k not in ("FRED_VIXCLS", "FRED_DEXKOUS", "FRED_BAMLH0A0HYM2")}
    out = S.core_gates(broken, ref, roles, days, acquired_on)
    assert out["decision"] == "DATA_BLOCKED_BEFORE_MARKET_RISK_ANATOMY" and "TRANSITION_GFC_2007_2009" in out["blockers"]
    # a reference that starts in 2013 can never be selected, so the study is blocked rather than redefined as 2015+
    short = {"YAHOO_KS200": audit_for(days, "2013-01-02")}
    ref2 = S.select_primary_reference(short, days, acquired_on)
    out = S.core_gates(short, ref2, roles, days, acquired_on)
    assert out["decision"] == "DATA_BLOCKED_BEFORE_MARKET_RISK_ANATOMY" and out["blockers"] == ["PRIMARY_REFERENCE_NOT_SELECTED"]


def test_core_decision_does_not_depend_on_the_extended_tier():
    days = M.kr_sessions("1999-01-04", "2026-09-30")
    audits = {sid: audit_for(days, "1999-01-04") for sid in ("YAHOO_KS200", "FRED_DGS10", "FRED_DGS3MO", "FRED_DFF", "FRED_VIXCLS")}
    ref = S.select_primary_reference(audits, days, "2026-10-02")
    out = S.core_gates(audits, ref, {"VIX": "FRED_VIXCLS", "USDKRW": None}, days, "2026-10-02")
    assert out["decision"] == "READY_FOR_MARKET_RISK_ANATOMY_EXECUTION"
    assert not any(k.startswith("int_") for table in out["coverage"].values() for k in table)  # the internals tier is never a core gate
    assert all(M.FEATURES[f][1] == "CORE_LONG_HISTORY" for table in out["coverage"].values() for f in table)


def test_role_secondary_is_used_only_when_the_primary_fails_and_never_spliced():
    days = M.kr_sessions("1999-01-04", "2026-09-30")
    weekly = M.period_end_dates(days, "W")
    good, late = audit_for(days, "1999-01-04"), audit_for(days, "2015-01-02")
    assert S.select_role_source("VIX", {"FRED_VIXCLS": good, "YAHOO_VIX": good}, days, weekly)[0] == "FRED_VIXCLS"
    assert S.select_role_source("VIX", {"FRED_VIXCLS": late, "YAHOO_VIX": good}, days, weekly)[0] == "YAHOO_VIX"
    assert S.select_role_source("VIX", {"FRED_VIXCLS": late, "YAHOO_VIX": late}, days, weekly)[0] is None
    assert S.select_role_source("USDKRW", {"FRED_DEXKOUS": {"status": "FAILED"}, "YAHOO_KRWX": good}, days, weekly)[0] == "YAHOO_KRWX"


def test_lags_are_the_frozen_conservative_values():
    assert S.lag_days("YAHOO_KS200") == 0 and S.lag_days("FRED_DGS10") == 4 and S.lag_days("FRED_DEXKOUS") == 8 and S.lag_days("YAHOO_VIX") == 1
    assert S.SOURCES["FRED_DEXKOUS"]["instrument"].startswith("KRW per USD, H.10")
