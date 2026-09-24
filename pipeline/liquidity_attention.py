"""Volume/price attention features, with magnitude kept alongside rank.

WHY THIS EXISTS. Production's only volume-derived feature is `volumeSurge`
(`build.py:123-138`, `historical_replay.py:290-299`) — the 5-day/60-day
average-volume ratio, always consumed either raw or as a cross-sectional
PERCENTILE, never as a magnitude the reader can tell a 2x day from a 15x
day by. `alpha-information-inventory-v1`'s data map (§4, §6) named this
explicitly: collapsing a volume shock to a percentile rank can make a
2x-average day and a 15x-average day look nearly identical, when they are
economically different events. This module computes the same family of
ratios but returns the RAW ratio, a LOG-scaled version, AND leaves
cross-sectional percentiling to a separate, explicit call
(`cross_sectional_percentile`) — so a caller can keep magnitude and rank
side by side rather than being forced to choose one at collection time.

WHY THIS IS A SEPARATE MODULE FROM `historical_replay.TickerHistory`.
`TickerHistory` (`historical_replay.py:99-107`) carries only
Close/Open/Volume — no High/Low — because that is all production's
`volumeSurge`/momentum features need. Several of the features below (range,
close-location value, gap, Amihud-style illiquidity) need High/Low, which
would mean widening a shared production data structure for a research-only
purpose. This module instead takes a plain OHLCV `DataFrame` directly, is
never imported by `historical_replay.py`, `build.py`, `longterm.py`, or any
challenger study, and computes nothing that reaches production.

PIT SAFETY. Every feature is a backward-looking rolling statistic ending at
each row's own date — nothing here reads a later row. A trading day's own
OHLCV is available to use once that day has closed (the same assumption
production's own `volumeSurge` already makes); no feature is shifted by an
extra day beyond what the rolling window itself implies.

NO FORWARD-RETURN RELATIONSHIP IS COMPUTED OR CONSUMED HERE. This module
produces features from already-visible price/volume history; nothing in it
reads an outcome, and nothing in `pipeline/` imports it for scoring.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

CONTRACT = "LIQUIDITY_ATTENTION_V1"

REQUIRED_COLUMN = "Close"
OPTIONAL_COLUMNS = ("Open", "High", "Low", "Volume")


def _safe_ratio(numer: pd.Series, denom: pd.Series) -> pd.Series:
    """Elementwise ratio, `NaN` (never inf or a fabricated value) on a
    non-positive or missing denominator."""
    out = numer / denom.replace(0.0, np.nan)
    return out.where(denom > 0)


def volume_ratio(volume: pd.Series, short: int, long: int) -> pd.Series:
    """Average volume over `short` days divided by average over `long` days.

    Generalizes production's `volumeSurge` (short=5, long=60) to any window
    pair, e.g. 1/20, 1/60, 5/20 — all requested by the parent task and none
    of them coded anywhere in the repository today.
    """
    short_avg = volume.rolling(short, min_periods=short).mean()
    long_avg = volume.rolling(long, min_periods=long).mean()
    return _safe_ratio(short_avg, long_avg)


def log_volume_shock(volume: pd.Series, window: int = 60) -> pd.Series:
    """`log(today's volume / trailing average)` — magnitude-preserving.

    A 2x day and a 15x day are 0.69 and 2.71 here, not both "near the top of
    the percentile range." This is the raw-magnitude sibling every ratio
    below also has a percentile-only version of somewhere else in this
    repository's Opportunity radar (`volumeSurge`), and is the reason this
    module exists rather than re-deriving that same percentile-only feature.
    """
    avg = volume.rolling(window, min_periods=window).mean()
    ratio = _safe_ratio(volume, avg)
    return np.log(ratio.where(ratio > 0))


def volume_zscore(volume: pd.Series, window: int = 60) -> pd.Series:
    """Standard score of today's volume against its own trailing window."""
    mean = volume.rolling(window, min_periods=window).mean()
    std = volume.rolling(window, min_periods=window).std(ddof=1)
    return _safe_ratio(volume - mean, std)


def dollar_volume(close: pd.Series, volume: pd.Series) -> pd.Series:
    return close * volume


def turnover(close: pd.Series, volume: pd.Series,
            shares_outstanding: pd.Series | float | None) -> pd.Series:
    """Dollar volume divided by market capitalization.

    `shares_outstanding` may be a per-date Series (from a PIT-aware source)
    or a single float; either way this is None wherever a share count is
    unavailable, never a value computed against a wrong-date count. This is
    explicitly NOT the same quantity as `kelly_portfolio`'s `turnoverPct`
    (portfolio rebalancing turnover) — do not conflate the two, per the data
    map's own warning.
    """
    dv = dollar_volume(close, volume)
    if shares_outstanding is None:
        return pd.Series(np.nan, index=close.index)
    market_cap = close * shares_outstanding
    return _safe_ratio(dv, market_cap)


def dollar_volume_shock(close: pd.Series, volume: pd.Series,
                        window: int = 60) -> pd.Series:
    dv = dollar_volume(close, volume)
    avg = dv.rolling(window, min_periods=window).mean()
    return _safe_ratio(dv, avg)


def shock_persistence(shock: pd.Series, threshold: float, window: int = 5) -> pd.Series:
    """How many of the trailing `window` days cleared `shock > threshold`.

    Distinguishes a single-day spike (persistence 1) from sustained
    multi-day accumulation (persistence `window`) on the SAME peak shock
    value — the "1-day vs multi-day accumulation" distinction the parent
    task named explicitly.
    """
    cleared = (shock > threshold).astype(float)
    return cleared.rolling(window, min_periods=1).sum()


def price_direction(close: pd.Series) -> pd.Series:
    """`+1` up, `-1` down, `0` flat — the day's own close-to-close direction."""
    change = close.diff()
    return np.sign(change)


def volume_price_alignment(volume_shock: pd.Series, direction: pd.Series) -> pd.Series:
    """Signed shock: positive on an up day, negative on a down day, 0 flat.

    Lets a caller separate "volume-up + price-up" from "volume-up +
    price-down" from "volume-up + price-flat" by the sign and magnitude of
    one column, rather than three separate boolean features.
    """
    return volume_shock * direction


def volume_price_divergence(volume_zscore_series: pd.Series,
                            price_return: pd.Series, window: int = 20) -> pd.Series:
    """Rolling correlation between volume z-score and same-day return.

    A strongly negative rolling correlation is the textbook "volume up,
    price down" divergence pattern; strongly positive is confirmation. `NaN`
    wherever either series lacks enough trailing history, never a fabricated
    0.
    """
    return volume_zscore_series.rolling(window, min_periods=window).corr(price_return)


def close_location_value(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    """Where today's close sits inside today's own range, in [0, 1].

    1.0 = closed at the high, 0.0 = closed at the low. `NaN` on a zero-range
    day (high == low) rather than an arbitrary 0.5 — a halted or
    single-print day is not the same as a day that traded through its own
    midpoint.
    """
    rng = high - low
    return _safe_ratio(close - low, rng)


def abnormal_range(high: pd.Series, low: pd.Series, close_prev: pd.Series,
                   window: int = 20) -> pd.Series:
    """Today's high-low range against its own trailing average, as a ratio.

    `close_prev` (yesterday's close) is the normalizer, matching a standard
    true-range convention, so the ratio is comparable across price levels.
    """
    true_range = pd.concat([
        high - low,
        (high - close_prev).abs(),
        (low - close_prev).abs(),
    ], axis=1).max(axis=1)
    avg = true_range.rolling(window, min_periods=window).mean()
    return _safe_ratio(true_range, avg)


def gap_pct(open_: pd.Series, close_prev: pd.Series) -> pd.Series:
    """Overnight gap: today's open against yesterday's close, in percent."""
    return _safe_ratio(open_ - close_prev, close_prev) * 100.0


def gap_times_volume(gap: pd.Series, volume_ratio_series: pd.Series) -> pd.Series:
    return gap * volume_ratio_series


def range_times_volume(range_ratio: pd.Series, volume_ratio_series: pd.Series) -> pd.Series:
    return range_ratio * volume_ratio_series


def close_near_high_after_shock(clv: pd.Series, volume_shock: pd.Series,
                                shock_threshold: float,
                                clv_threshold: float = 0.8) -> pd.Series:
    """1.0 if a volume-shock day ALSO closed near its own high, else 0.0.

    `NaN` on a day that was not a volume-shock day at all — the question is
    only meaningful conditional on a shock having happened, so a non-shock
    day is an absent observation, never a false 0.
    """
    on_shock_day = volume_shock > shock_threshold
    return (clv >= clv_threshold).astype(float).where(on_shock_day)


def close_near_low_after_shock(clv: pd.Series, volume_shock: pd.Series,
                               shock_threshold: float,
                               clv_threshold: float = 0.2) -> pd.Series:
    """1.0 if a volume-shock day ALSO closed near its own low, else 0.0.

    Deliberately a DIFFERENT indicator from `close_near_high_after_shock`,
    not its complement read backwards — a shock day can close in the middle
    of its range and be near neither extreme, so both can read 0.0 on the
    same day.
    """
    on_shock_day = volume_shock > shock_threshold
    return (clv <= clv_threshold).astype(float).where(on_shock_day)


def amihud_illiquidity_proxy(returns: pd.Series, dollar_volume_series: pd.Series,
                             window: int = 20) -> pd.Series:
    """Mean(|return| / dollar volume) over the trailing window — a standard,
    off-the-shelf illiquidity proxy, not one invented for this module.

    Larger values mean a given dollar volume moves the price more — i.e.
    less liquid. `NaN` wherever dollar volume is non-positive for a day
    inside the window rather than an infinite spike.
    """
    per_day = _safe_ratio(returns.abs(), dollar_volume_series)
    return per_day.rolling(window, min_periods=window).mean()


def market_adjusted_shock(shock: pd.Series, market_shock: pd.Series) -> pd.Series:
    """A name's own volume shock minus the market's same-day shock.

    `market_shock` is the caller's own cross-sectional average/median
    `log_volume_shock` across the universe on the same date — this function
    only does the subtraction, so it carries no assumption about how the
    market aggregate was built.
    """
    return shock - market_shock


def compute_features(frame: pd.DataFrame, *,
                     shares_outstanding: pd.Series | float | None = None,
                     shock_threshold: float = 1.0) -> pd.DataFrame:
    """All per-ticker features this module defines, from one OHLCV frame.

    `frame` must have a `Close` column and a `DatetimeIndex`; `Open`,
    `High`, `Low`, `Volume` are used where present and the features that
    need a missing one come back all-`NaN` for that column, never silently
    omitted (so a caller always sees which features could not be computed
    for this name, rather than a shorter, unexplained column list).
    """
    if REQUIRED_COLUMN not in frame.columns:
        raise ValueError(f"frame must have a '{REQUIRED_COLUMN}' column")
    close = frame["Close"].astype(float)
    idx = frame.index
    nan_series = pd.Series(np.nan, index=idx)

    volume = frame["Volume"].astype(float) if "Volume" in frame else nan_series
    open_ = frame["Open"].astype(float) if "Open" in frame else nan_series
    high = frame["High"].astype(float) if "High" in frame else nan_series
    low = frame["Low"].astype(float) if "Low" in frame else nan_series
    close_prev = close.shift(1)
    returns = close.pct_change()

    out = pd.DataFrame(index=idx)
    out["volumeRatio1_20"] = volume_ratio(volume, 1, 20)
    out["volumeRatio1_60"] = volume_ratio(volume, 1, 60)
    out["volumeRatio5_20"] = volume_ratio(volume, 5, 20)
    out["volumeRatio5_60"] = volume_ratio(volume, 5, 60)
    out["logVolumeShock60"] = log_volume_shock(volume, 60)
    out["volumeZScore60"] = volume_zscore(volume, 60)
    out["dollarVolume"] = dollar_volume(close, volume)
    out["turnoverPct"] = turnover(close, volume, shares_outstanding) * 100.0
    out["dollarVolumeShock60"] = dollar_volume_shock(close, volume, 60)
    out["shockPersistence5d"] = shock_persistence(out["logVolumeShock60"], shock_threshold, 5)
    direction = price_direction(close)
    out["volumePriceAlignment"] = volume_price_alignment(out["logVolumeShock60"], direction)
    out["volumePriceDivergence20"] = volume_price_divergence(out["volumeZScore60"], returns, 20)
    out["closeLocationValue"] = close_location_value(high, low, close)
    out["abnormalRange20"] = abnormal_range(high, low, close_prev, 20)
    out["gapPct"] = gap_pct(open_, close_prev)
    out["gapTimesVolume"] = gap_times_volume(out["gapPct"], out["volumeRatio5_60"])
    out["rangeTimesVolume"] = range_times_volume(out["abnormalRange20"], out["volumeRatio5_60"])
    out["closeNearHighAfterShock"] = close_near_high_after_shock(
        out["closeLocationValue"], out["logVolumeShock60"], shock_threshold)
    out["closeNearLowAfterShock"] = close_near_low_after_shock(
        out["closeLocationValue"], out["logVolumeShock60"], shock_threshold)
    out["amihudIlliquidity20"] = amihud_illiquidity_proxy(returns, out["dollarVolume"], 20)
    return out


def cross_sectional_percentile(values: pd.Series) -> pd.Series:
    """Rank-percentile of `values` ON ONE DATE, across whatever names are
    passed in (a caller's own cross-section).

    Deliberately separate from `compute_features`: percentiling is a
    cross-sectional operation (needs every name on a date at once), while
    everything above is a per-ticker, backward-looking-in-time operation. A
    caller who wants BOTH magnitude and rank calls this on top of
    `compute_features`'s output, keeping the two representations distinct
    rather than collapsing straight to one, per this module's whole reason
    for existing.
    """
    return values.rank(pct=True) * 100.0


FEATURE_MANIFEST: dict[str, str] = {
    "volumeRatio1_20": "1-day volume / 20-day average volume (raw ratio)",
    "volumeRatio1_60": "1-day volume / 60-day average volume (raw ratio)",
    "volumeRatio5_20": "5-day avg volume / 20-day average volume (raw ratio)",
    "volumeRatio5_60": "5-day avg volume / 60-day average volume — same construction as production volumeSurge",
    "logVolumeShock60": "log(today's volume / 60-day average) — magnitude-preserving",
    "volumeZScore60": "standard score of today's volume vs its own 60-day window",
    "dollarVolume": "Close x Volume",
    "turnoverPct": "dollar volume / market cap, in percent (needs a shares-outstanding series)",
    "dollarVolumeShock60": "dollar volume / 60-day average dollar volume",
    "shockPersistence5d": "count of the trailing 5 days whose logVolumeShock60 cleared the threshold",
    "volumePriceAlignment": "logVolumeShock60 signed by the day's own price direction",
    "volumePriceDivergence20": "20-day rolling correlation of volume z-score and same-day return",
    "closeLocationValue": "(close - low) / (high - low), in [0, 1]",
    "abnormalRange20": "true range / 20-day average true range",
    "gapPct": "overnight gap: (open - prior close) / prior close, in percent",
    "gapTimesVolume": "gapPct x volumeRatio5_60",
    "rangeTimesVolume": "abnormalRange20 x volumeRatio5_60",
    "closeNearHighAfterShock": "1.0 if closeLocationValue >= 0.8 on a logVolumeShock60 > threshold day, else 0.0; NaN on a non-shock day",
    "closeNearLowAfterShock": "1.0 if closeLocationValue <= 0.2 on a logVolumeShock60 > threshold day, else 0.0; NaN on a non-shock day (not the complement of closeNearHighAfterShock — both can read 0.0 the same day)",
    "amihudIlliquidity20": "mean(|return| / dollar volume) over the trailing 20 days — a standard illiquidity proxy",
}
