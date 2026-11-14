"""Daily input checks and fixed-horizon gross USD holding reconstruction.

No model, portfolio ranking, tuning, production writer, or old study executor.
Cash received at a documented terminal event stays unremunerated until H.
Successor exposure requires a separately identified, complete successor series.
"""
from __future__ import annotations

from dataclasses import dataclass
from bisect import bisect_left, bisect_right
import math

import numpy as np
import pandas as pd

from pipeline import price_adjustment as PA

BASIS_TOLERANCE = 1e-5  # Price representation/float precision; never fitted to a return.


class Unresolved(ValueError):
    pass


@dataclass
class Series:
    ticker: str
    tr: pd.Series
    raw_close: pd.Series
    good_days: set[str]
    source: str
    receipt: str
    identity_verified: bool = False
    actions_verified: bool = False


def positive(value):
    return isinstance(value, (int, float, np.number)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def whole_window_source(preferred, fallback, entry, end):
    """Select a complete publisher window; never splice levels or hide its gaps."""
    if preferred is not None and preferred.tr.index.min() <= pd.Timestamp(entry) and pd.Timestamp(end) <= preferred.tr.index.max():
        return preferred
    return fallback


def frame_series(ticker, frame, *, source, receipt, basis, adjusted=None):
    """Reuse the registered forward adjustment once, preserving missing sessions."""
    if basis != "SPLIT_ADJUSTED_DIVIDEND_UNADJUSTED":
        raise Unresolved("ALREADY_ADJUSTED_OR_UNKNOWN_BASIS")
    if frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
        raise Unresolved("DUPLICATE_OR_UNSORTED_DAILY_KEYS")
    if any(column not in frame for column in ("Open", "High", "Low", "Close", "Volume", PA.DIVIDEND, PA.SPLIT)):
        raise Unresolved("REQUIRED_PRICE_OR_ACTION_FIELD_ABSENT")
    good = frame.Close.map(positive) & frame.Volume.map(positive)
    good &= (frame.Low <= frame[["Open", "Close"]].min(axis=1) + 1e-7)
    good &= (frame.High >= frame[["Open", "Close"]].max(axis=1) - 1e-7)
    transformed, events = PA.to_total_return(frame)
    if any(not e.get("applied", True) for e in events):
        raise Unresolved("DISTRIBUTION_RECIPE_REFUSED")
    ratios = PA.future_split_factor(frame[PA.SPLIT].where(frame[PA.SPLIT] > 0, 1))
    raw_close = frame.Close * ratios
    check = None
    if adjusted is not None:
        ratio = (transformed.Close / adjusted).replace([np.inf, -np.inf], np.nan).dropna()
        if len(ratio) < 2:
            raise Unresolved("ADJUSTED_LEVEL_CHECK_UNAVAILABLE")
        check = float((ratio / ratio.median() - 1).abs().max())
        if check > BASIS_TOLERANCE:
            raise Unresolved("ADJUSTED_VS_REBUILT_LEVEL_MISMATCH")
    return Series(ticker, transformed.Close, raw_close,
                  set(frame.index[good].strftime("%Y-%m-%d")), source, receipt), check


def holding(series, entry, end, calendar, *, terminal=None, successors=None, cvr=None, require_admission=True):
    """One fixed gross-TR label; never fills an unknown exit or an absent quote."""
    if require_admission and not (series.identity_verified and series.actions_verified):
        raise Unresolved("SECURITY_OR_ACTION_ADMISSION_UNRESOLVED")
    start_pos, end_pos = bisect_left(calendar, entry), bisect_left(calendar, end)
    if start_pos >= len(calendar) or end_pos >= len(calendar) or calendar[start_pos] != entry or calendar[end_pos] != end or entry > end:
        raise Unresolved("INVALID_HOLDING_CALENDAR")
    if entry not in series.good_days or not positive(series.tr.get(entry)):
        raise Unresolved("ENTRY_PRICE_MISSING_OR_NOT_TRADABLE")
    window = calendar[start_pos:end_pos + 1]
    terminal = terminal if terminal and entry <= terminal["date"] <= end else None
    if not terminal:
        if any(d not in series.good_days for d in window):
            raise Unresolved("PRICE_PATH_GAP")
        if not positive(series.tr.get(end)):
            raise Unresolved("EXIT_PRICE_MISSING")
        return float(series.tr.at[end] / series.tr.at[entry] - 1)
    if not terminal.get("verified") or not terminal.get("citation"):
        raise Unresolved("TERMINAL_CONSIDERATION_UNVERIFIED")
    last = terminal["last_trading_date"]
    if last < entry or last >= terminal["date"] and terminal.get("effective_before_open", False):
        raise Unresolved("TERMINAL_ENTRY_OR_TIMING_UNRESOLVED")
    if any(d not in series.good_days for d in window if d <= last):
        raise Unresolved("PRE_TERMINAL_PRICE_PATH_GAP")
    if terminal.get("cvr") and (cvr is None or end not in cvr):
        raise Unresolved("CVR_MARK_OR_PAYOFF_MISSING")
    wealth = float(series.tr.at[last] / series.tr.at[entry])
    shares = wealth / float(series.raw_close.at[last])
    cash = terminal.get("cash")
    ratio = terminal.get("shares")
    if cash is None and ratio is None:
        if terminal.get("zero_confirmed") is True:
            return -1.0
        raise Unresolved("TERMINAL_CONSIDERATION_MISSING")
    value = shares * float(cash or 0)
    if ratio:
        if terminal.get("cash_in_lieu_required") and not terminal.get("fractional_reference_shares_authorized"):
            raise Unresolved("FRACTIONAL_SHARE_SETTLEMENT_UNRESOLVED")
        successor = (successors or {}).get(terminal.get("successor"))
        first = terminal["date"]
        if successor is None or not (successor.identity_verified and successor.actions_verified):
            raise Unresolved("SUCCESSOR_SECURITY_OR_ACTIONS_UNVERIFIED")
        days = calendar[bisect_left(calendar, first):bisect_right(calendar, end)]
        if any(d not in successor.good_days for d in days):
            raise Unresolved("SUCCESSOR_PRICE_PATH_GAP")
        value += shares * ratio * float(successor.raw_close.at[first]) * float(successor.tr.at[end] / successor.tr.at[first])
    if terminal.get("cvr"):
        value += shares * cvr[end]
    return value - 1


def ranges(days, calendar=None):
    """Calendar-date ranges for an explicit set of missing exchange sessions."""
    days = sorted(set(days))
    if not days:
        return []
    positions = {d: i for i, d in enumerate(calendar)} if calendar is not None else None
    out, start, previous = [], days[0], days[0]
    for day in days[1:]:
        separate = positions[day] != positions[previous] + 1 if positions is not None else (pd.Timestamp(day) - pd.Timestamp(previous)).days > 1
        if separate:
            out.append({"from": start, "through": previous})
            start = day
        previous = day
    return [*out, {"from": start, "through": previous}]
