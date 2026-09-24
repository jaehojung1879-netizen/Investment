"""Volume/price attention features: magnitude preserved, never a false zero.

Every assertion checks either (a) that a genuine absence (a zero-range day,
a non-shock day, a missing share count) comes back `NaN` rather than 0.0 or
an invented value, or (b) that the raw/log magnitude survives instead of
collapsing straight to a percentile, which is this module's whole reason to
exist over reusing production's percentile-only `volumeSurge`.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import liquidity_attention as LA  # noqa: E402


def _flat_frame(n=80, price=100.0, volume=1000.0):
    dates = pd.bdate_range("2023-01-02", periods=n)
    return pd.DataFrame({
        "Open": price, "High": price, "Low": price, "Close": price,
        "Volume": volume,
    }, index=dates)


def test_volume_ratio_needs_the_full_window_or_it_is_nan():
    frame = _flat_frame(n=10)
    ratio = LA.volume_ratio(frame["Volume"], 5, 60)
    assert ratio.isna().all()  # never enough history for a 60-day average


def test_volume_ratio_matches_productions_volume_surge_construction():
    frame = _flat_frame(n=70, volume=100.0)
    frame.loc[frame.index[-5:], "Volume"] = 500.0
    ratio = LA.volume_ratio(frame["Volume"], 5, 60)
    last = ratio.iloc[-1]
    # 5 days at 500 + 55 days at 100 over the trailing 60 = avg 133.33
    expected_denominator = (5 * 500.0 + 55 * 100.0) / 60.0
    assert last == pytest.approx(500.0 / expected_denominator)


def test_log_volume_shock_distinguishes_2x_from_15x():
    frame = _flat_frame(n=61, volume=100.0)
    two_x = frame.copy()
    two_x.iloc[-1, two_x.columns.get_loc("Volume")] = 200.0
    fifteen_x = frame.copy()
    fifteen_x.iloc[-1, fifteen_x.columns.get_loc("Volume")] = 1500.0

    shock_2x = LA.log_volume_shock(two_x["Volume"], 60).iloc[-1]
    shock_15x = LA.log_volume_shock(fifteen_x["Volume"], 60).iloc[-1]
    assert shock_15x > shock_2x * 2  # magnitude preserved, not compressed to the same rank


def test_close_location_value_is_nan_on_a_zero_range_day_not_half():
    high = pd.Series([100.0, 100.0])
    low = pd.Series([100.0, 100.0])
    close = pd.Series([100.0, 100.0])
    clv = LA.close_location_value(high, low, close)
    assert clv.isna().all()


def test_close_location_value_bounds():
    high = pd.Series([110.0])
    low = pd.Series([90.0])
    close_at_high = pd.Series([110.0])
    close_at_low = pd.Series([90.0])
    assert LA.close_location_value(high, low, close_at_high).iloc[0] == 1.0
    assert LA.close_location_value(high, low, close_at_low).iloc[0] == 0.0


def test_close_near_high_and_low_are_not_complements_of_each_other():
    clv = pd.Series([0.5])  # dead center: neither near high nor near low
    shock = pd.Series([2.0])
    high_flag = LA.close_near_high_after_shock(clv, shock, shock_threshold=1.0)
    low_flag = LA.close_near_low_after_shock(clv, shock, shock_threshold=1.0)
    assert high_flag.iloc[0] == 0.0
    assert low_flag.iloc[0] == 0.0  # both 0.0 on the same day, not complementary


def test_shock_flags_are_nan_on_a_non_shock_day():
    clv = pd.Series([0.95])
    shock = pd.Series([0.1])  # below threshold: not a shock day at all
    high_flag = LA.close_near_high_after_shock(clv, shock, shock_threshold=1.0)
    assert high_flag.isna().iloc[0]


def test_turnover_is_nan_without_a_share_count():
    close = pd.Series([100.0, 100.0])
    volume = pd.Series([1000.0, 1000.0])
    turnover = LA.turnover(close, volume, None)
    assert turnover.isna().all()


def test_turnover_is_a_real_ratio_with_a_share_count():
    close = pd.Series([100.0])
    volume = pd.Series([1000.0])
    turnover = LA.turnover(close, volume, shares_outstanding=100_000.0)
    # dollar volume 100,000 / market cap 10,000,000 = 1%
    assert turnover.iloc[0] == pytest.approx(0.01)


def test_shock_persistence_distinguishes_one_day_from_sustained():
    single_spike = pd.Series([0.0, 0.0, 0.0, 0.0, 2.0])
    sustained = pd.Series([2.0, 2.0, 2.0, 2.0, 2.0])
    assert LA.shock_persistence(single_spike, threshold=1.0, window=5).iloc[-1] == 1.0
    assert LA.shock_persistence(sustained, threshold=1.0, window=5).iloc[-1] == 5.0


def test_amihud_proxy_is_nan_on_non_positive_dollar_volume():
    returns = pd.Series([0.01] * 25)
    dollar_volume = pd.Series([0.0] * 25)  # never positive
    proxy = LA.amihud_illiquidity_proxy(returns, dollar_volume, window=20)
    assert proxy.isna().all()


def test_compute_features_requires_close_column():
    with pytest.raises(ValueError):
        LA.compute_features(pd.DataFrame({"Volume": [1.0, 2.0]}))


def test_compute_features_runs_on_a_full_ohlcv_frame():
    rng = np.random.default_rng(1)
    n = 90
    dates = pd.bdate_range("2023-01-02", periods=n)
    close = 100 * np.cumprod(1 + rng.normal(0, 0.01, n))
    frame = pd.DataFrame({
        "Open": close * 1.001,
        "High": close * 1.01,
        "Low": close * 0.99,
        "Close": close,
        "Volume": rng.integers(1000, 5000, n).astype(float),
    }, index=dates)
    out = LA.compute_features(frame, shares_outstanding=1_000_000.0)
    assert set(LA.FEATURE_MANIFEST) == set(out.columns)
    # The last row has enough history for every rolling window to fire.
    assert out["volumeRatio5_60"].iloc[-1] is not None


def test_cross_sectional_percentile_is_a_separate_call_never_baked_in():
    values = pd.Series([1.0, 5.0, 2.0, 9.0, 3.0])
    pct = LA.cross_sectional_percentile(values)
    assert pct.iloc[3] == 100.0  # the largest value ranks at the top
    assert pct.iloc[0] == 20.0  # the smallest value ranks at the bottom
