"""Canonical calendar labels for daily market data.

Daily Yahoo frames can arrive as timezone-naive dates or as timezone-aware
midnight stamps, depending on the ticker mix in a download batch.  Converting
the latter straight to ``datetime64[ns]`` first converts them to UTC and can
move an Asian session onto the previous calendar day.  That silently breaks
exact stock/benchmark joins.

The vendor's daily bar label is a market-calendar date, not an intraday instant.
We therefore preserve the displayed wall date, remove timezone metadata, and
normalize every row to midnight before any replay or outcome calculation.
"""
from __future__ import annotations

import pandas as pd


def normalize_daily_index(index) -> pd.DatetimeIndex:
    """Return timezone-naive midnight labels for daily bars.

    Duplicate labels are intentionally not removed here because callers need
    to apply the same keep rule to the associated values.  Invalid labels are
    returned as ``NaT`` so the frame helper can drop those rows explicitly.
    """
    stamps = pd.DatetimeIndex(pd.to_datetime(index, errors="coerce"))
    if stamps.tz is not None:
        stamps = stamps.tz_localize(None)
    return stamps.normalize()


def normalize_daily_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize a daily frame and deterministically keep the last duplicate."""
    out = frame.copy()
    out.index = normalize_daily_index(out.index)
    out = out[~out.index.isna()]
    return out[~out.index.duplicated(keep="last")].sort_index()


def normalize_daily_series(series: pd.Series) -> pd.Series:
    """Normalize a daily series and deterministically keep the last duplicate."""
    out = series.copy()
    out.index = normalize_daily_index(out.index)
    out = out[~out.index.isna()]
    return out[~out.index.duplicated(keep="last")].sort_index()
