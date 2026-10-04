"""KR market risk anatomy v1 — pure descriptive instruments (MARKET layer: how much equity risk, never which stock or industry).

EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY. The KR market history is already known to the researchers, so a new
preregistration does not make it an independent sample: rules frozen before this study's formal execution protect against
post-outcome tuning INSIDE this study only. Nothing here validates, predicts, selects a market-timing rule or sizes a portfolio.

No I/O, no network, no model fit, no portfolio. Functions receive series and return tables.

Rules that run through every function and are tested on synthetic data:

* NOTHING FUTURE REACHES A FEATURE. Every external observation carries an availability date (observation date plus a frozen conservative
  lag) and a feature at KR session t sees only the latest observation available at t. Rolling windows look backwards over values that
  were already known on each earlier session.
* REVISED HISTORY IS NEVER BACKDATED. A source whose vintage class is REVISED_HISTORY (or has no release evidence at all) is not a
  predictor; PIT_EXACT needs release evidence; an approximate lag never upgrades a class.
* MISSING IS MISSING. No back-fill, no future interpolation, no current value stamped on history. A stale carry-forward expires.
* SLOWER DATA IS SAMPLED AT ITS OWN CADENCE. Statistics use monthly (slow), weekly (transition) or weekly-snapshot (fast) rows; carried
  daily rows are never counted as independent evidence.
* A HISTORICAL STATE IS END-DATE INVARIANT. Percentiles are expanding and past-only; the state at t is identical whether the data end at t
  or in 2026.
* TARGETS ARE FUTURE PATHS, NOT ONLY ENDPOINTS. Worst loss, maximum drawdown and realised volatility are computed on the future benchmark
  path; an unresolved window (a missing session) is unresolved, never filled.
* NOTHING IS TUNED. Every threshold is a module constant frozen before any outcome-containing history was inspected.
"""
from __future__ import annotations

import bisect
import math

import numpy as np
import pandas as pd

from . import kr_factor_anatomy as A
from . import kr_industry_anatomy as I
from . import replay_calendar as RC

STUDY = "kr-market-risk-anatomy-v1"
SCIENTIFIC_STATUS = "EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY"
SCIENTIFIC_STATUS_MEANING = (
    "exploratory historical development on a market history that is already known",
    "rules frozen before this study's formal outcome execution",
    "not prospective confirmation, not validated, not predictive, not production-ready",
    "preregistration and one-shot execution protect against post-outcome tuning inside this study; they do not make the sample independent",
)
TIERS = ("CORE_LONG_HISTORY", "EXTENDED_KR_INTERNALS")
FAMILIES = ("SLOW_VULNERABILITY", "TRANSITION_FINANCIAL_STRESS", "FAST_MARKET_BREAK", "KR_MARKET_INTERNALS")
ANNUALISATION = 252

# ---- cadence and horizons ---------------------------------------------------------------------------------------------------------
CADENCE = {"SLOW_VULNERABILITY": "M", "TRANSITION_FINANCIAL_STRESS": "W", "FAST_MARKET_BREAK": "W", "KR_MARKET_INTERNALS": "W"}
CADENCE_STEP_SESSIONS = {"M": 21, "W": 5, "D": 1}
HORIZONS = {"FAST_MARKET_BREAK": (21, 63), "TRANSITION_FINANCIAL_STRESS": (63, 126), "SLOW_VULNERABILITY": (126, 252),
            "KR_MARKET_INTERNALS": (21, 63)}
COMMON_HORIZONS = (63, 126)
ALL_HORIZONS = (21, 63, 126, 252)
LOSS_CUTS = (-0.10, -0.15, -0.20)           # forward worst-loss event labels, frozen
EPISODE_THRESHOLDS = (0.10, 0.15, 0.20)
PRIMARY_EPISODE_THRESHOLD = 0.15
LANDMARK_OFFSETS = (-252, -126, -63, -21)
LANDMARK_DRAWDOWNS = (0.05, 0.10, 0.15)
DAMAGE_CUTS = (0.20, 0.50)

# ---- availability (observation date -> first KR signal date that may use it) ---------------------------------------------------------
LAG_CALENDAR_DAYS = {"KR_INDEX_CLOSE": 0, "FRED_DAILY_MARKET": 4, "FRED_H10_WEEKLY": 8, "YAHOO_US_DAILY": 1}
STALE_CALENDAR_DAYS = {"D": 14}
FRED_DAILY_STALE_DAYS = 14

# ---- normalisation and states ------------------------------------------------------------------------------------------------------------
MIN_NORMALISATION_OBS = {"M": 36, "W": 156, "D": 756}
HIGH_STATE_PERCENTILE = 0.80
STRESS_WORSENING_PERCENTILE = 0.75
EASING_THRESHOLD_PP = -0.25
EASING_LOOKBACK_SESSIONS = 126
INVERSION_LOOKBACK_SESSIONS = 504
OVERLAY_VOL_THRESHOLD = 0.25
OVERLAY_MULTIPLIERS = (1.0, 0.7, 0.4)
DRAWDOWN_TRIGGER_CUT = -0.10

# ---- statistics --------------------------------------------------------------------------------------------------------------------------
MIN_TS_OBS = 36
MIN_YEAR_OBS = {"M": 8, "W": 20, "D": 100}
MIN_EVENTS_FOR_AUROC = 10
MIN_NONEVENTS_FOR_AUROC = 10

FORBIDDEN_OUTPUT_KEY_FRAGMENTS = I.FORBIDDEN_OUTPUT_KEY_FRAGMENTS + ("winner", "optimal", "besttrigger", "timingrule")

# ---------------------------------------------------------------------------------------------------------------------------------------
# Feature registry: orientation is ALWAYS "higher value = more downside risk"; the sign flip is part of the definition.
# ---------------------------------------------------------------------------------------------------------------------------------------
FEATURES = {
    # SLOW_VULNERABILITY
    "slow_us_10y3m_flatness": ("SLOW_VULNERABILITY", "CORE_LONG_HISTORY", "minus (DGS10 - DGS3MO), percentage points"),
    "slow_us_10y2y_flatness": ("SLOW_VULNERABILITY", "CORE_LONG_HISTORY", "minus (DGS10 - DGS2), percentage points"),
    "slow_inversion_duration_10y3m": ("SLOW_VULNERABILITY", "CORE_LONG_HISTORY", "consecutive month-end observations with 10y-3m < 0 including t"),
    "slow_resteepening_flag_10y3m": ("SLOW_VULNERABILITY", "CORE_LONG_HISTORY", "1 if 10y-3m > 0 now and its minimum over the trailing 504 sessions was < 0, else 0"),
    "slow_fed_funds_level": ("SLOW_VULNERABILITY", "CORE_LONG_HISTORY", "DFF level, percent"),
    "slow_fed_funds_change_126": ("SLOW_VULNERABILITY", "CORE_LONG_HISTORY", "DFF(t) - DFF(t-126 sessions), percentage points (tightening = risk)"),
    # TRANSITION_FINANCIAL_STRESS
    "trans_hy_oas_level": ("TRANSITION_FINANCIAL_STRESS", "CORE_LONG_HISTORY", "BAMLH0A0HYM2 level"),
    "trans_hy_oas_change_21": ("TRANSITION_FINANCIAL_STRESS", "CORE_LONG_HISTORY", "HY OAS(t) - HY OAS(t-21 sessions)"),
    "trans_hy_oas_change_63": ("TRANSITION_FINANCIAL_STRESS", "CORE_LONG_HISTORY", "HY OAS(t) - HY OAS(t-63 sessions)"),
    "trans_ig_oas_level": ("TRANSITION_FINANCIAL_STRESS", "CORE_LONG_HISTORY", "BAMLC0A0CM level"),
    "trans_ig_oas_change_63": ("TRANSITION_FINANCIAL_STRESS", "CORE_LONG_HISTORY", "IG OAS(t) - IG OAS(t-63 sessions)"),
    "trans_vix_level": ("TRANSITION_FINANCIAL_STRESS", "CORE_LONG_HISTORY", "VIX level"),
    "trans_vix_change_21": ("TRANSITION_FINANCIAL_STRESS", "CORE_LONG_HISTORY", "VIX(t) - VIX(t-21 sessions)"),
    "trans_vix_change_63": ("TRANSITION_FINANCIAL_STRESS", "CORE_LONG_HISTORY", "VIX(t) - VIX(t-63 sessions)"),
    "trans_usdkrw_change_63": ("TRANSITION_FINANCIAL_STRESS", "CORE_LONG_HISTORY", "log(USDKRW(t)/USDKRW(t-63 sessions)) (KRW weakening = risk)"),
    "trans_usdkrw_realized_vol_21": ("TRANSITION_FINANCIAL_STRESS", "CORE_LONG_HISTORY", "annualised std of the last 21 known log changes"),
    "trans_easing_flag": ("TRANSITION_FINANCIAL_STRESS", "CORE_LONG_HISTORY", "1 if DFF(t) - DFF(t-126 sessions) <= -0.25 pp"),
    "trans_benign_easing_flag": ("TRANSITION_FINANCIAL_STRESS", "CORE_LONG_HISTORY", "easing, no 10y-3m inversion in the trailing 504 sessions, HY stress not worsening"),
    "trans_easing_after_inversion_flag": ("TRANSITION_FINANCIAL_STRESS", "CORE_LONG_HISTORY", "easing with a 10y-3m inversion in the trailing 504 sessions"),
    "trans_post_vulnerability_stress_easing_hy_flag": ("TRANSITION_FINANCIAL_STRESS", "CORE_LONG_HISTORY", "easing after inversion AND HY stress worsening (expanding percentile of HY level or 63-session change >= 0.75)"),
    "trans_post_vulnerability_stress_easing_vix_flag": ("TRANSITION_FINANCIAL_STRESS", "CORE_LONG_HISTORY", "easing after inversion AND VIX stress worsening (expanding percentile of VIX level or 63-session change >= 0.75)"),
    # FAST_MARKET_BREAK
    "fast_trend_distance_sma200": ("FAST_MARKET_BREAK", "CORE_LONG_HISTORY", "minus (close / mean of last 200 closes - 1)"),
    "fast_sma200_slope_21": ("FAST_MARKET_BREAK", "CORE_LONG_HISTORY", "minus (SMA200(t) / SMA200(t-21) - 1)"),
    "fast_ret_63": ("FAST_MARKET_BREAK", "CORE_LONG_HISTORY", "minus trailing 63-session return"),
    "fast_ret_126": ("FAST_MARKET_BREAK", "CORE_LONG_HISTORY", "minus trailing 126-session return"),
    "fast_drawdown_252": ("FAST_MARKET_BREAK", "CORE_LONG_HISTORY", "minus (close / max of last 252 closes - 1), a depth >= 0"),
    "fast_realized_vol_21": ("FAST_MARKET_BREAK", "CORE_LONG_HISTORY", "std (ddof 1) of the last 21 daily returns x sqrt(252)"),
    "fast_realized_vol_63": ("FAST_MARKET_BREAK", "CORE_LONG_HISTORY", "std (ddof 1) of the last 63 daily returns x sqrt(252)"),
    "fast_downside_vol_63": ("FAST_MARKET_BREAK", "CORE_LONG_HISTORY", "sqrt(mean(min(r,0)^2)) over the last 63 returns x sqrt(252)"),
    "fast_vol_acceleration": ("FAST_MARKET_BREAK", "CORE_LONG_HISTORY", "vol21 / vol63 - 1"),
    "fast_overlay_count": ("FAST_MARKET_BREAK", "CORE_LONG_HISTORY", "existing overlay: trend adverse (close < mean of last 200) + vol adverse (vol63 > 25%)"),
    # KR_MARKET_INTERNALS (EXTENDED tier only; needs a PIT universe)
    "int_breadth_above_sma200": ("KR_MARKET_INTERNALS", "EXTENDED_KR_INTERNALS", "minus fraction of PIT members above their SMA200"),
    "int_positive_breadth_63": ("KR_MARKET_INTERNALS", "EXTENDED_KR_INTERNALS", "minus fraction of PIT members with a positive 63-session return"),
    "int_breadth_deterioration_63": ("KR_MARKET_INTERNALS", "EXTENDED_KR_INTERNALS", "minus (breadth above SMA200 (t) - breadth (t-63 sessions))"),
    "int_capweight_minus_equalweight_63": ("KR_MARKET_INTERNALS", "EXTENDED_KR_INTERNALS", "cap-weighted minus equal-weighted 63-session return of PIT members (narrow leadership = risk)"),
    "int_dispersion_63": ("KR_MARKET_INTERNALS", "EXTENDED_KR_INTERNALS", "cross-sectional std of 63-session returns of PIT members"),
    "int_concentration_top5_share": ("KR_MARKET_INTERNALS", "EXTENDED_KR_INTERNALS", "top five signal-date market-cap share among PIT members"),
}
BINARY_FLAG_FEATURES = tuple(n for n in FEATURES if n.endswith("_flag"))
BASELINE_TRIGGERS = {
    "B1_TREND_ADVERSE": "close < mean of the last 200 closes (the existing overlay trend leg)",
    "B2_VOL_ADVERSE": "annualised vol63 > 25% (the existing overlay vol leg)",
    "B3_OVERLAY_ANY": "existing overlay count >= 1 (risk multiplier <= 0.7)",
    "B4_OVERLAY_BOTH": "existing overlay count == 2 (risk multiplier 0.4)",
    "D10_TRAILING_DRAWDOWN": "close / max of the last 252 closes - 1 <= -10%",
}
SLOW_WARNINGS = {"W1_INVERSION_10Y3M": "10y-3m < 0", "W2_INVERSION_10Y2Y": "10y-2y < 0"}


def feature_family(name):
    return FEATURES[name][0]


# =======================================================================================================================================
# Sessions, cadence and as-of knowledge
# =======================================================================================================================================
def kr_sessions(start, end):
    return RC.sessions(start, end, "KR")


def period_end_dates(sessions, frequency):
    """Last KR session of each calendar period (M month, W week, D every session). Only sessions at or before the last given session."""
    days = pd.DatetimeIndex(sessions)
    if frequency == "D":
        return days
    return pd.DatetimeIndex(pd.Series(days, index=days).groupby(days.to_period(frequency)).max().to_list())


def known_on_sessions(observations, sessions, lag_days, stale_days=None):
    """Latest observation AVAILABLE on each KR session. availableFrom(obs d) = d + lag_days (calendar); the value used on session t is
    the observation with the greatest date whose availableFrom <= t. Returns (values, obsDates) aligned to `sessions`.

    A carried observation older than `stale_days` (calendar, relative to t) is missing, never extended. Nothing after t can matter:
    availability is monotone in the observation date, so the lookup is a left-closed search on the availability axis."""
    obs = pd.Series(observations).dropna()
    obs = obs[np.isfinite(obs.to_numpy(float))]
    obs.index = pd.DatetimeIndex(obs.index)
    obs = obs[~obs.index.duplicated(keep="last")].sort_index()
    days = pd.DatetimeIndex(sessions)
    avail = (obs.index + pd.Timedelta(days=int(lag_days))).to_numpy()
    pos = np.searchsorted(avail, days.to_numpy(), side="right") - 1
    values = np.full(len(days), np.nan)
    obs_dates = np.full(len(days), np.datetime64("NaT"), dtype="datetime64[ns]")
    ok = pos >= 0
    values[ok] = obs.to_numpy(float)[pos[ok]]
    obs_dates[ok] = obs.index.to_numpy()[pos[ok]]
    if stale_days is not None:
        age = (days.to_numpy() - obs_dates) / np.timedelta64(1, "D")
        expired = ok & (age > stale_days)
        values[expired] = np.nan
        obs_dates[expired] = np.datetime64("NaT")
    return pd.Series(values, index=days), pd.Series(obs_dates, index=days)


def expanding_percentile(values, min_obs):
    """Past-only percentile of x_t among the finite values observed up to and including t: (#less + 0.5 #equal) / n. NaN where fewer than
    `min_obs` finite values exist yet, and NaN where x_t is NaN. The value at t never depends on any later observation."""
    x = pd.Series(values, dtype=float)
    out = np.full(len(x), np.nan)
    history = []
    for i, v in enumerate(x.to_numpy()):
        if not np.isfinite(v):
            continue
        bisect.insort(history, v)
        if len(history) >= min_obs:
            lo, hi = bisect.bisect_left(history, v), bisect.bisect_right(history, v)
            out[i] = (lo + 0.5 * (hi - lo)) / len(history)
    return pd.Series(out, index=x.index)


# =======================================================================================================================================
# Vulnerability, transition and fast features (computed on the KR session grid from values already known on each session)
# =======================================================================================================================================
def _diff_over(series, sessions_back):
    return series - series.shift(sessions_back)


def fast_features(close):
    """Benchmark-derived features on the session grid. `close` is indexed by KR sessions (NaN for a missing session); every value at t uses
    closes at or before t. Oriented so that higher = more downside risk."""
    c = pd.Series(close, dtype=float)
    ret = c.pct_change(fill_method=None)
    sma200 = c.rolling(200).mean()
    vol21 = ret.rolling(21).std(ddof=1) * math.sqrt(ANNUALISATION)
    vol63 = ret.rolling(63).std(ddof=1) * math.sqrt(ANNUALISATION)
    down = np.sqrt((np.minimum(ret, 0.0) ** 2).where(ret.notna()).rolling(63).mean()) * math.sqrt(ANNUALISATION)
    out = pd.DataFrame(index=c.index)
    out["fast_trend_distance_sma200"] = -(c / sma200 - 1.0)
    out["fast_sma200_slope_21"] = -(sma200 / sma200.shift(21) - 1.0)
    out["fast_ret_63"] = -(c / c.shift(63) - 1.0)
    out["fast_ret_126"] = -(c / c.shift(126) - 1.0)
    out["fast_drawdown_252"] = -(c / c.rolling(252).max() - 1.0)
    out["fast_realized_vol_21"], out["fast_realized_vol_63"] = vol21, vol63
    out["fast_downside_vol_63"] = down
    out["fast_vol_acceleration"] = vol21 / vol63 - 1.0
    out["fast_overlay_count"] = overlay_count_series(c)
    return out


def overlay_state_from_window(close201):
    """The existing `kr_market_risk_overlay.state_at` rule applied to the 201 sessions ending at t (a literal replica of its arithmetic so a
    test can prove equality). NaN anywhere in the window, or a non-positive close, is DATA_INSUFFICIENT."""
    close = pd.to_numeric(pd.Series(close201), errors="coerce")
    if len(close) < 201 or not np.isfinite(close.to_numpy()).all() or (close <= 0).any():
        return {"status": "DATA_INSUFFICIENT", "riskMultiplier": None}
    trend_adverse = bool(close.iloc[-1] < close.iloc[-200:].mean())
    vol = float(close.pct_change(fill_method=None).tail(63).std(ddof=1) * np.sqrt(252))
    vol_adverse = vol > OVERLAY_VOL_THRESHOLD
    count = int(trend_adverse) + int(vol_adverse)
    return {"status": "READY", "trendAdverse": trend_adverse, "benchmarkVol63": vol, "volAdverse": bool(vol_adverse),
            "riskMultiplier": OVERLAY_MULTIPLIERS[count], "count": count}


def overlay_count_series(close):
    """overlay count (0/1/2) at every session, NaN where the existing rule is DATA_INSUFFICIENT. Uses the literal window replica."""
    c = pd.Series(close, dtype=float)
    values = c.to_numpy()
    out = np.full(len(c), np.nan)
    for i in range(200, len(c)):
        state = overlay_state_from_window(values[i - 200:i + 1])
        if state["status"] == "READY":
            out[i] = state["count"]
    return pd.Series(out, index=c.index)


def baseline_trigger_states(close):
    """Frozen binary triggers on the session grid as float arrays (1 on, 0 off, NaN unavailable)."""
    c = pd.Series(close, dtype=float)
    count = overlay_count_series(c)
    values = c.to_numpy()
    trend = np.full(len(c), np.nan)
    vol = np.full(len(c), np.nan)
    for i in range(200, len(c)):
        state = overlay_state_from_window(values[i - 200:i + 1])
        if state["status"] == "READY":
            trend[i], vol[i] = float(state["trendAdverse"]), float(state["volAdverse"])
    dd = c / c.rolling(252).max() - 1.0
    d10 = (dd <= DRAWDOWN_TRIGGER_CUT).astype(float).where(dd.notna())
    return pd.DataFrame({"B1_TREND_ADVERSE": trend, "B2_VOL_ADVERSE": vol, "B3_OVERLAY_ANY": (count >= 1).astype(float).where(count.notna()),
                         "B4_OVERLAY_BOTH": (count >= 2).astype(float).where(count.notna()), "D10_TRAILING_DRAWDOWN": d10}, index=c.index)


def slow_features(known, sessions):
    """known: dict name -> daily-known Series on `sessions` (see known_on_sessions): 'spread_10y3m', 'spread_10y2y', 'dff'.
    Returns the daily-grid table (to be SAMPLED at month-ends, never read daily)."""
    out = pd.DataFrame(index=pd.DatetimeIndex(sessions))
    s3, s2, dff = known.get("spread_10y3m"), known.get("spread_10y2y"), known.get("dff")
    if s3 is not None:
        out["slow_us_10y3m_flatness"] = -s3
        out["slow_resteepening_flag_10y3m"] = ((s3 > 0) & (s3.rolling(INVERSION_LOOKBACK_SESSIONS, min_periods=INVERSION_LOOKBACK_SESSIONS).min() < 0)).astype(float).where(
            s3.notna() & s3.rolling(INVERSION_LOOKBACK_SESSIONS, min_periods=INVERSION_LOOKBACK_SESSIONS).min().notna())
    if s2 is not None:
        out["slow_us_10y2y_flatness"] = -s2
    if dff is not None:
        out["slow_fed_funds_level"] = dff
        out["slow_fed_funds_change_126"] = _diff_over(dff, EASING_LOOKBACK_SESSIONS)
    return out


def inversion_duration(month_end_spread):
    """Consecutive month-end observations with spread < 0 up to and including each month (0 when not inverted, NaN when unknown)."""
    s = pd.Series(month_end_spread, dtype=float)
    out, run = np.full(len(s), np.nan), 0
    for i, v in enumerate(s.to_numpy()):
        if not np.isfinite(v):
            run = 0
            continue
        run = run + 1 if v < 0 else 0
        out[i] = run
    return pd.Series(out, index=s.index)


def transition_features(known, sessions, weekly_dates):
    """known: daily-known Series ('hy','ig','vix','usdkrw','dff','spread_10y3m', optional 'usdkrw_obs_logchg' handled by the caller).
    The expanding percentile states used by the stress-worsening flags are computed on the WEEKLY grid (their own cadence)."""
    idx = pd.DatetimeIndex(sessions)
    out = pd.DataFrame(index=idx)
    hy, ig, vix, krw = known.get("hy"), known.get("ig"), known.get("vix"), known.get("usdkrw")
    if hy is not None:
        out["trans_hy_oas_level"], out["trans_hy_oas_change_21"], out["trans_hy_oas_change_63"] = hy, _diff_over(hy, 21), _diff_over(hy, 63)
    if ig is not None:
        out["trans_ig_oas_level"], out["trans_ig_oas_change_63"] = ig, _diff_over(ig, 63)
    if vix is not None:
        out["trans_vix_level"], out["trans_vix_change_21"], out["trans_vix_change_63"] = vix, _diff_over(vix, 21), _diff_over(vix, 63)
    if krw is not None:
        out["trans_usdkrw_change_63"] = np.log(krw / krw.shift(63))
    dff, s3 = known.get("dff"), known.get("spread_10y3m")
    if dff is not None:
        easing = (_diff_over(dff, EASING_LOOKBACK_SESSIONS) <= EASING_THRESHOLD_PP).astype(float).where(_diff_over(dff, EASING_LOOKBACK_SESSIONS).notna())
        out["trans_easing_flag"] = easing
        inverted = None
        if s3 is not None:
            lowest = s3.rolling(INVERSION_LOOKBACK_SESSIONS, min_periods=INVERSION_LOOKBACK_SESSIONS).min()
            inverted = (lowest < 0).astype(float).where(lowest.notna())
            out["trans_easing_after_inversion_flag"] = ((easing == 1) & (inverted == 1)).astype(float).where(easing.notna() & inverted.notna())
        for label, base, flag in (("hy", hy, "trans_post_vulnerability_stress_easing_hy_flag"), ("vix", vix, "trans_post_vulnerability_stress_easing_vix_flag")):
            if base is None or inverted is None:
                continue
            level_pct = _weekly_percentile(base, weekly_dates)
            change_pct = _weekly_percentile(_diff_over(base, 63), weekly_dates)
            worsening = ((level_pct >= STRESS_WORSENING_PERCENTILE) | (change_pct >= STRESS_WORSENING_PERCENTILE)).astype(float).where(level_pct.notna() | change_pct.notna())
            out[flag] = ((easing == 1) & (inverted == 1) & (worsening == 1)).astype(float).where(easing.notna() & inverted.notna() & worsening.notna())
            if label == "hy":
                out["trans_benign_easing_flag"] = ((easing == 1) & (inverted == 0) & (worsening == 0)).astype(float).where(easing.notna() & inverted.notna() & worsening.notna())
    return out


def _weekly_percentile(daily_known, weekly_dates):
    """Expanding percentile computed on the weekly sample, then carried to the daily grid by the latest weekly value (past-only)."""
    d = pd.Series(daily_known, dtype=float)
    weekly = d.reindex(pd.DatetimeIndex(weekly_dates))
    pct = expanding_percentile(weekly.to_numpy(), MIN_NORMALISATION_OBS["W"])
    pct.index = weekly.index
    return pct.reindex(d.index, method="ffill")


def realized_vol_of_known_changes(observations, sessions, lag_days, window=21):
    """Annualised std of the last `window` KNOWN log changes of an observation series, on each KR session. Uses observations only once
    available; the window is counted in observations, not sessions."""
    obs = pd.Series(observations).dropna().sort_index()
    logchg = np.log(obs / obs.shift(1)).dropna()
    days = pd.DatetimeIndex(sessions)
    avail = (logchg.index + pd.Timedelta(days=int(lag_days))).to_numpy()
    values = logchg.to_numpy(float)
    out = np.full(len(days), np.nan)
    for i, day in enumerate(days.to_numpy()):
        k = np.searchsorted(avail, day, side="right")
        if k >= window:
            out[i] = float(np.std(values[k - window:k], ddof=1) * math.sqrt(ANNUALISATION))
    return pd.Series(out, index=days)


def internals_features(returns63, above_sma200, caps, breadth_lag_sessions=63):
    """KR market internals from a PIT cross-section of ONE signal date (callers pass only that date's members). Returns the oriented
    higher=more-risk values; any missing member input leaves that statistic missing, never zero. Pure and label-free."""
    r = A.clean_numeric(returns63)
    ab = A.clean_numeric(above_sma200)
    w = A.clean_numeric(caps)
    out = {name: np.nan for name in FEATURES if name.startswith("int_")}
    if np.isfinite(ab).all() and len(ab):
        out["int_breadth_above_sma200"] = -float(np.mean(ab))
    if np.isfinite(r).all() and len(r):
        out["int_positive_breadth_63"] = -float(np.mean(r > 0))
        out["int_dispersion_63"] = float(np.std(r, ddof=0))
        if np.isfinite(w).all() and (w > 0).all():
            out["int_capweight_minus_equalweight_63"] = float(math.fsum(sorted(w / w.sum() * r)) - np.mean(r))
    if np.isfinite(w).all() and (w > 0).all() and len(w) >= 5:
        out["int_concentration_top5_share"] = float(np.sort(w)[-5:].sum() / w.sum())
    return out


# =======================================================================================================================================
# Future-path targets
# =======================================================================================================================================
def forward_targets(close, horizon):
    """Per session position p: ForwardReturn_H, ForwardWorstLossFromSignal_H, FutureMaxDrawdown_H, FutureRealizedVol_H and a status.

    close: array/Series on the KR session grid (NaN = missing session). The window is the path close[p..p+H].
      forwardReturn   = close[p+H]/close[p] - 1
      forwardWorstLoss = min(close[p+1..p+H])/close[p] - 1  (may be positive when the path never falls below the signal value)
      futureMaxDrawdown = min over the window of close[j]/running_max(close[p..j]) - 1   (<= 0; the signal-date value may be the peak)
      futureRealizedVol = std (ddof 1) of the H daily returns x sqrt(252)
    Status MATURED / PENDING (window runs past the last session) / UNRESOLVED_MISSING_SESSION (any NaN or non-positive close in the path).
    A missing session is never filled."""
    c = np.asarray(pd.Series(close, dtype=float).to_numpy(), float)
    n = len(c)
    cols = {k: np.full(n, np.nan) for k in ("forwardReturn", "forwardWorstLoss", "futureMaxDrawdown", "futureRealizedVol")}
    status = np.empty(n, dtype=object)
    for p in range(n):
        if p + horizon > n - 1:
            status[p] = "PENDING"
            continue
        path = c[p:p + horizon + 1]
        if not np.isfinite(path).all() or (path <= 0).any():
            status[p] = "UNRESOLVED_MISSING_SESSION"
            continue
        status[p] = "MATURED"
        cols["forwardReturn"][p] = path[-1] / path[0] - 1.0
        cols["forwardWorstLoss"][p] = path[1:].min() / path[0] - 1.0
        cols["futureMaxDrawdown"][p] = float((path / np.maximum.accumulate(path) - 1.0).min())
        cols["futureRealizedVol"][p] = float(np.std(path[1:] / path[:-1] - 1.0, ddof=1) * math.sqrt(ANNUALISATION)) if horizon >= 2 else np.nan
    out = pd.DataFrame(cols, index=pd.Series(close).index)
    out["status"] = status
    return out


def loss_labels(worst_loss):
    """Boolean event labels at the frozen cuts (<= -10/-15/-20%); NaN stays NaN."""
    w = pd.Series(worst_loss, dtype=float)
    return {f"loss_le_{int(abs(cut) * 100)}": (w <= cut + 1e-15).astype(float).where(w.notna()) for cut in LOSS_CUTS}


# =======================================================================================================================================
# Underwater episodes, landmarks and early-damage metrics
# =======================================================================================================================================
def underwater_episodes(close):
    """Deterministic underwater episodes of a close series.

    running peak P (the latest close >= every earlier close); a close >= P is a (new or equal) high: it ends any open episode as a
    RECOVERY and restarts the peak at that date. A close < P opens an episode (peak = the date P was last set) and the trough is the
    FIRST lowest close of the episode (strict improvement only). depth = trough/peak - 1. An episode still open at the last observation is
    right-censored (recoveryPos None). Missing sessions are skipped (episodes are computed over observed closes only; positions refer to
    the original grid). Every episode is returned; thresholds are applied by `episodes_at_least`."""
    c = np.asarray(pd.Series(close, dtype=float).to_numpy(), float)
    episodes, peak_pos, peak_val, trough_pos, trough_val, under = [], None, None, None, None, False
    for i, v in enumerate(c):
        if not np.isfinite(v) or v <= 0:
            continue
        if peak_val is None or v >= peak_val:
            if under:
                episodes.append({"peakPos": peak_pos, "troughPos": trough_pos, "recoveryPos": i, "depth": trough_val / peak_val - 1.0, "censored": False})
                under = False
            peak_pos, peak_val = i, v
        else:
            if not under:
                under, trough_pos, trough_val = True, i, v
            elif v < trough_val:
                trough_pos, trough_val = i, v
    if under:
        episodes.append({"peakPos": peak_pos, "troughPos": trough_pos, "recoveryPos": None, "depth": trough_val / peak_val - 1.0, "censored": True})
    return episodes


def episodes_at_least(episodes, threshold):
    """Episodes whose depth reaches -threshold (e.g. 0.15 for -15%)."""
    return [e for e in episodes if e["depth"] <= -threshold + 1e-15]


def episode_landmarks(close, episode):
    """Fixed landmark positions of one episode (None when a landmark does not exist): peak-252/126/63/21, peak, first -5/-10/-15% close
    inside the episode, trough."""
    c = np.asarray(pd.Series(close, dtype=float).to_numpy(), float)
    peak, trough = episode["peakPos"], episode["troughPos"]
    out = {f"peak{off:+d}": (peak + off if peak + off >= 0 else None) for off in LANDMARK_OFFSETS}
    out["peak"] = peak
    for cut in LANDMARK_DRAWDOWNS:
        key = f"first_drawdown_{int(cut * 100)}"
        out[key] = None
        for i in range(peak + 1, trough + 1):
            if np.isfinite(c[i]) and c[i] / c[peak] - 1.0 <= -cut + 1e-15:
                out[key] = i
                break
    out["trough"] = trough
    return out


def first_trigger_damage(close, episode, on):
    """Early-damage metrics of one binary trigger over one episode.

    The trigger window is [peak, trough]. TriggerPos = first session in it with on == 1 (a state already on at the peak gives delay 0, loss 0
    and alreadyOnAtPeak). Metrics (all from closes at or before the trigger session, except the remaining drawdown, which is the outcome):
      lossAtTrigger        = close[trigger]/close[peak] - 1
      damageFraction       = |lossAtTrigger| / |depth|
      remainingDrawdown    = close[trough]/close[trigger] - 1
      triggerDelaySessions = trigger - peak
    Status: TRIGGERED / MISSED (never on in the window) / ACTIVATED_AFTER_TROUGH (first on after the trough: it could not reduce the drawdown)
    / STATE_UNAVAILABLE (no valid state in the window)."""
    c = np.asarray(pd.Series(close, dtype=float).to_numpy(), float)
    s = np.asarray(pd.Series(on, dtype=float).to_numpy(), float)
    peak, trough = episode["peakPos"], episode["troughPos"]
    window = s[peak:trough + 1]
    if not np.isfinite(window).any():
        return {"status": "STATE_UNAVAILABLE"}
    hits = np.flatnonzero(window == 1)
    if len(hits) == 0:
        after = np.flatnonzero(s[trough + 1:] == 1)
        return {"status": "ACTIVATED_AFTER_TROUGH" if len(after) else "MISSED", "depth": episode["depth"]}
    trig = peak + int(hits[0])
    loss = c[trig] / c[peak] - 1.0
    return {"status": "TRIGGERED", "triggerPos": trig, "triggerDelaySessions": trig - peak, "alreadyOnAtPeak": bool(s[peak] == 1),
            "lossAtTrigger": float(loss), "damageFraction": float(abs(loss) / abs(episode["depth"])), "depth": episode["depth"],
            "remainingDrawdownAfterTrigger": float(c[trough] / c[trig] - 1.0)}


def damage_summary(results):
    """Distribution of the continuous damage fraction over episodes plus the fixed cut shares (before 20% and before 50% of the eventual
    drawdown was suffered) and the missed count. Nothing is selected."""
    fractions = np.array([r["damageFraction"] for r in results if r["status"] == "TRIGGERED"], float)
    n = len(results)
    out = {"episodes": n, "triggered": int(len(fractions)), "missed": int(sum(r["status"] in ("MISSED", "ACTIVATED_AFTER_TROUGH") for r in results)),
           "stateUnavailable": int(sum(r["status"] == "STATE_UNAVAILABLE" for r in results)), "damageFractions": [float(x) for x in np.sort(fractions)]}
    for cut in DAMAGE_CUTS:
        out[f"shareTriggeredBefore{int(cut * 100)}pctOfDrawdown"] = (int((fractions < cut).sum()) / n if n else None)
    if len(fractions):
        out.update(median=float(np.median(fractions)), mean=float(np.mean(fractions)), min=float(fractions.min()), max=float(fractions.max()))
    return out


def slow_warning_lead(on, episode):
    """Pre-peak lead of a slow warning, kept separate from any fast trigger: whether it is on at the peak, the onset of the streak that is on at
    the peak (sessions before the peak), and otherwise sessions since it was last on (None when never on before the peak)."""
    s = np.asarray(pd.Series(on, dtype=float).to_numpy(), float)
    peak = episode["peakPos"]
    if not np.isfinite(s[:peak + 1]).any():
        return {"status": "STATE_UNAVAILABLE"}
    if s[peak] == 1:
        start = peak
        while start - 1 >= 0 and s[start - 1] == 1:
            start -= 1
        return {"status": "ACTIVE_AT_PEAK", "streakOnsetPos": start, "leadSessions": peak - start}
    prior = np.flatnonzero(s[:peak] == 1)
    if len(prior):
        return {"status": "ON_THEN_OFF", "lastOnPos": int(prior[-1]), "sessionsSinceLastOn": int(peak - prior[-1])}
    return {"status": "NEVER_ON_BEFORE_PEAK"}


# =======================================================================================================================================
# False alarms and recovery cost of a binary trigger
# =======================================================================================================================================
def trigger_profile(on, close, episodes, horizons=COMMON_HORIZONS):
    """Counts and rates for one pre-registered binary trigger: activations (0/NaN -> 1 transitions), share of valid sessions adverse, for every
    horizon and loss cut the share of ON sessions (and of OFF sessions) followed by that downside, the share of activation streaks followed by NO
    drawdown of at least 10% within H63 (the false alarms), and per supplied episode the normalisation delay after the trough with the return
    missed before the trigger's own off-state. Overlapping ON sessions are descriptive; nothing is optimised."""
    s = np.asarray(pd.Series(on, dtype=float).to_numpy(), float)
    valid = np.isfinite(s)
    onset = np.array([s[i] == 1 and not (i > 0 and s[i - 1] == 1) for i in range(len(s))])
    out = {"validSessions": int(valid.sum()), "adverseSessions": int((s == 1).sum()), "adverseShare": float((s == 1).sum() / valid.sum()) if valid.any() else None,
           "activations": int(onset.sum()), "followed": {}}
    for h in horizons:
        targets = forward_targets(close, h)
        matured = targets.status.eq("MATURED").to_numpy() & valid
        labels = loss_labels(targets.forwardWorstLoss)
        for name, label in labels.items():
            lab = label.to_numpy(float)
            on_m, off_m = matured & (s == 1), matured & (s == 0)
            out["followed"][f"H{h}|{name}"] = {"onSessions": int(on_m.sum()), "offSessions": int(off_m.sum()),
                                               "rateWhenOn": float(np.mean(lab[on_m])) if on_m.any() else None,
                                               "rateWhenOff": float(np.mean(lab[off_m])) if off_m.any() else None}
        unrewarded = total = 0
        w = targets.forwardWorstLoss.to_numpy(float)
        for i in np.flatnonzero(onset & matured):
            total += 1
            unrewarded += int(w[i] > LOSS_CUTS[0])
        out[f"activationStreaksH{h}"] = {"matured": total, "noTenPercentDrawdownWithin": unrewarded, "share": (unrewarded / total if total else None)}
    c = np.asarray(pd.Series(close, dtype=float).to_numpy(), float)
    out["normalisation"] = []
    for e in episodes:
        later = np.flatnonzero(s[e["troughPos"] + 1:] == 0)
        if len(later) == 0:
            out["normalisation"].append({"troughPos": e["troughPos"], "status": "NEVER_NORMALISED_IN_SAMPLE"})
            continue
        pos = e["troughPos"] + 1 + int(later[0])
        out["normalisation"].append({"troughPos": e["troughPos"], "status": "NORMALISED", "normalisedPos": pos, "delaySessions": pos - e["troughPos"],
                                     "returnMissedBeforeNormalisation": float(c[pos] / c[e["troughPos"]] - 1.0)})
    return out


# =======================================================================================================================================
# Time-series statistics (one market series, overlapping horizons; NOT a cross-sectional IC)
# =======================================================================================================================================
def ts_spearman(x, y, minimum=MIN_TS_OBS):
    fx, fy = A.clean_numeric(x), A.clean_numeric(y)
    ok = np.isfinite(fx) & np.isfinite(fy)
    if ok.sum() < minimum:
        return {"n": int(ok.sum()), "rho": None}
    rho = A.spearman(fx[ok], fy[ok])
    return {"n": int(ok.sum()), "rho": float(rho) if np.isfinite(rho) else None}


def rank_corr_hac(x, y, lag, minimum=MIN_TS_OBS):
    """Descriptive Newey-West standard error of the Spearman rank correlation of overlapping observations: the correlation is the mean of the
    product of the standardised average ranks, and the Bartlett-weighted long-run variance of that product series (lag = ceil(H / step)) gives
    the standard error. Descriptive: no multiplicity correction and no decision role."""
    from scipy.stats import rankdata
    fx, fy = A.clean_numeric(x), A.clean_numeric(y)
    ok = np.isfinite(fx) & np.isfinite(fy)
    if ok.sum() < minimum:
        return {"n": int(ok.sum()), "rho": None, "hacSe": None}
    rx, ry = rankdata(fx[ok]), rankdata(fy[ok])
    if np.std(rx) == 0 or np.std(ry) == 0:
        return {"n": int(ok.sum()), "rho": None, "hacSe": None}
    zx, zy = (rx - rx.mean()) / rx.std(), (ry - ry.mean()) / ry.std()
    product = zx * zy
    stats = I.newey_west_mean(product, lag)
    return {"n": int(ok.sum()), "rho": float(product.mean()), "hacSe": stats["se"]}


def auroc(score, label, min_events=MIN_EVENTS_FOR_AUROC, min_nonevents=MIN_NONEVENTS_FOR_AUROC):
    """Area under the ROC curve (Mann-Whitney with tie mid-ranks) of `score` against a binary label; None when the classes are too small."""
    from scipy.stats import rankdata
    s, l = A.clean_numeric(score), A.clean_numeric(label)
    ok = np.isfinite(s) & np.isfinite(l)
    s, l = s[ok], l[ok].astype(int)
    n1, n0 = int((l == 1).sum()), int((l == 0).sum())
    if n1 < min_events or n0 < min_nonevents:
        return {"events": n1, "nonEvents": n0, "auroc": None}
    ranks = rankdata(s)
    return {"events": n1, "nonEvents": n0, "auroc": float((ranks[l == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))}


def event_rates(label, high_state):
    """Unconditional event rate and the rate when the feature's past-only percentile state is HIGH (>= 0.80) versus not."""
    lab, hi = A.clean_numeric(label), A.clean_numeric(high_state)
    ok = np.isfinite(lab)
    both = ok & np.isfinite(hi)
    return {"n": int(ok.sum()), "events": int(np.nansum(lab[ok])), "rate": float(np.mean(lab[ok])) if ok.any() else None,
            "nHigh": int((both & (hi == 1)).sum()), "eventsHigh": int(np.nansum(lab[both & (hi == 1)])),
            "rateHigh": float(np.mean(lab[both & (hi == 1)])) if (both & (hi == 1)).any() else None,
            "nNotHigh": int((both & (hi == 0)).sum()), "eventsNotHigh": int(np.nansum(lab[both & (hi == 0)])),
            "rateNotHigh": float(np.mean(lab[both & (hi == 0)])) if (both & (hi == 0)).any() else None}


def year_table(dates, x, y, frequency, minimum=None):
    """Spearman per calendar year (years with at least MIN_YEAR_OBS finite pairs) plus the exact pair counts."""
    minimum = minimum or MIN_YEAR_OBS[frequency]
    frame = pd.DataFrame({"x": A.clean_numeric(x), "y": A.clean_numeric(y)}, index=pd.DatetimeIndex(dates))
    out = {}
    for year, g in frame.groupby(frame.index.year):
        ok = g.dropna()
        out[str(year)] = {"n": int(len(ok)), "rho": (ts_spearman(ok.x, ok.y, minimum)["rho"] if len(ok) >= minimum else None)}
    return out


def feature_statistics(dates, feature, targets, frequency, horizon):
    """Everything registered for ONE oriented feature at ONE horizon on its own cadence rows: Spearman versus loss severity (-worst loss), versus
    max-drawdown severity (-max drawdown) and versus realised volatility; event rates and AUROC at -10/-15/-20; descriptive HAC; year table;
    exact valid-date counts and period. `targets` is the forward_targets table sampled on the same dates."""
    x = pd.Series(feature, dtype=float)
    matured = targets.status.eq("MATURED").to_numpy()
    severity = -targets.forwardWorstLoss.to_numpy(float)
    mdd = -targets.futureMaxDrawdown.to_numpy(float)
    vol = targets.futureRealizedVol.to_numpy(float)
    lag = math.ceil(horizon / CADENCE_STEP_SESSIONS[frequency])
    xv = np.where(matured, x.to_numpy(float), np.nan)
    valid = np.isfinite(xv)
    pct = expanding_percentile(x, MIN_NORMALISATION_OBS[frequency])
    high = (pct >= HIGH_STATE_PERCENTILE).astype(float).where(pct.notna()).to_numpy(float)
    labels = loss_labels(targets.forwardWorstLoss)
    out = {"validDates": int(valid.sum()), "start": str(pd.DatetimeIndex(dates)[valid][0].date()) if valid.any() else None,
           "end": str(pd.DatetimeIndex(dates)[valid][-1].date()) if valid.any() else None,
           "spearmanVersusLossSeverity": rank_corr_hac(xv, severity, lag), "spearmanVersusMaxDrawdownSeverity": ts_spearman(xv, mdd),
           "spearmanVersusRealizedVol": ts_spearman(xv, vol), "byYear": year_table(dates, xv, severity, frequency), "events": {}}
    for name, label in labels.items():
        lab = np.where(matured, label.to_numpy(float), np.nan)
        out["events"][name] = {"rates": event_rates(lab, high), "auroc": auroc(xv, lab)}
    return out


def assert_cadence(dates, frequency, sessions):
    """The rows of a statistic must be exactly a subset of the family's cadence grid: carried daily rows are never independent evidence."""
    grid = set(period_end_dates(sessions, frequency))
    extra = [d for d in pd.DatetimeIndex(dates) if d not in grid]
    if extra:
        raise ValueError("ROWS_OFF_THE_REGISTERED_CADENCE: " + str(extra[0].date()))
    return True


def assert_no_forbidden_keys(value, path=""):
    """Outputs may not carry validation, winner, optimisation or best-trigger semantics anywhere in their key space."""
    if isinstance(value, dict):
        for key, inner in value.items():
            if any(f in str(key).lower().replace("_", "") for f in FORBIDDEN_OUTPUT_KEY_FRAGMENTS):
                raise ValueError("FORBIDDEN_OUTPUT_KEY: " + path + "/" + str(key))
            assert_no_forbidden_keys(inner, path + "/" + str(key))
    elif isinstance(value, (list, tuple)):
        for inner in value:
            assert_no_forbidden_keys(inner, path)
    return True


# =======================================================================================================================================
# Source/vintage classification and the label-free coverage gates
# =======================================================================================================================================
VINTAGE_CLASSES = ("PIT_EXACT", "MARKET_OBSERVED_UNREVISED_APPROXIMATE_AVAILABILITY", "REVISED_HISTORY", "NOT_AVAILABLE")
PREDICTOR_ELIGIBLE_CLASSES = ("PIT_EXACT", "MARKET_OBSERVED_UNREVISED_APPROXIMATE_AVAILABILITY")


def classify_source(entry):
    """Eligibility of a registered source as a historical predictor. A revised history, or anything without release evidence that is not a
    market-observed unrevised quote, is never eligible; PIT_EXACT demands retained release evidence; an approximate lag never upgrades."""
    cls = entry["vintageClass"]
    if cls not in VINTAGE_CLASSES:
        raise ValueError("UNKNOWN_VINTAGE_CLASS")
    if cls == "PIT_EXACT" and not entry.get("releaseEvidence"):
        raise ValueError("PIT_EXACT_REQUIRES_RELEASE_EVIDENCE")
    if str(entry.get("vendor", "")).startswith("ECOS") and cls != "REVISED_HISTORY":
        raise ValueError("ECOS_IS_REVISED_HISTORY")
    return cls in PREDICTOR_ELIGIBLE_CLASSES


def session_coverage(dates, sessions, start, end):
    """Share of KR sessions in [start, end] that have an observation (dates only; no value is read)."""
    window = pd.DatetimeIndex(sessions)
    window = window[(window >= pd.Timestamp(start)) & (window <= pd.Timestamp(end))]
    have = set(pd.DatetimeIndex(dates))
    return (sum(d in have for d in window) / len(window)) if len(window) else None
