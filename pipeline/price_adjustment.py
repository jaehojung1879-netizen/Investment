"""As-traded prices and a forward-anchored total-return basis.

WHY THIS EXISTS
---------------
Yahoo's auto-adjusted close is a BACK-anchored total-return series: every value
in it is scaled by the dividends that fall AFTER it, so one new ex-dividend
rewrites that ticker's whole history. Measured between two consecutive
production acquisitions one day apart — the seals replay-v9 and replay-v10
committed — 17 of 567 names moved by 3 to 86 bps in JANUARY 2011 for exactly
that reason (SWK 86, 003550.KS 84, AEE 70, CI 55, BLK 51 bps), and 550 more
moved by a single float32 step.

An input store whose whole purpose is an immutable published prefix cannot hold
such a series. The prefix legitimately changes every day, `InputStore.commit`
compares it byte for byte, and so every acquisition run after a generation's
first one must fail with INPUT_VERSION_CONFLICT. That is not a bug in any one
generation: it is why replay v7, v8, v9 and v10 each lasted one or two runs
before the ledger had to start over.

WHAT THIS MODULE CHANGES
------------------------
The same information, rebased so that it is append-only:

* Splits are undone back to the price that printed. Yahoo's *unadjusted* close
  is still split-adjusted, so a later split divides every earlier close;
  multiplying by the ratio of the splits that come after each session cancels
  that exactly, and what is left is the as-traded price, which never moves.
* The total-return index is then accumulated FORWARD from the first session,
  with Yahoo's own factor ``1 / (1 - dividend / previous close)``. A dividend
  paid tomorrow multiplies tomorrow onward and leaves every published value
  alone.

Anchoring at the start instead of the end changes the level by ONE CONSTANT
FACTOR PER TICKER and nothing else, so the series stays exactly proportional to
Yahoo's adjusted close. Every ratio the pipeline takes of it — momentum,
volatility, drawdown, benchmark excess, NAV growth — is unchanged, which is why
this is an input-provenance change and not a change of what is measured.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .market_dates import normalize_daily_frame

ADJUSTMENT_VERSION = "as-traded-forward-total-return-v1"

DIVIDEND = "Dividends"
SPLIT = "Stock Splits"
SCALED_COLUMNS = ("Open", "High", "Low", "Close")
EVENT_COLUMNS = (DIVIDEND, SPLIT)


def _series(frame: pd.DataFrame, column: str, default: float) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(default, index=frame.index, dtype=float)
    values = pd.to_numeric(frame[column], errors="coerce").fillna(default)
    return values.astype(float)


def future_split_factor(splits: pd.Series) -> np.ndarray:
    """Product of the splits that happen STRICTLY AFTER each session.

    The close printed on a split date is already the post-split price, so a
    split must never scale its own session.
    """
    ratios = np.asarray(splits, dtype=float)
    if not len(ratios):
        return np.ones(0)
    inclusive = np.cumprod(ratios[::-1])[::-1]      # product over j >= i
    return np.concatenate([inclusive[1:], [1.0]])   # product over j >  i


def event_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """The dividend and split columns of a vendor actions panel, on its index.

    Kept separate from the prices so a second vendor's bars can carry them:
    FinanceDataReader serves the Korean sessions Yahoo is missing but publishes
    no distributions, while Yahoo publishes the distributions for the very names
    whose sessions it drops. Both vendors quote a split-adjusted,
    dividend-unadjusted close, so the events transfer between them unchanged.
    """
    if frame is None or not len(frame):
        return pd.DataFrame(columns=[DIVIDEND, SPLIT], index=pd.DatetimeIndex([]))
    clean = normalize_daily_frame(frame)
    return pd.DataFrame({DIVIDEND: _series(clean, DIVIDEND, 0.0),
                         SPLIT: _series(clean, SPLIT, 0.0)}, index=clean.index)


def _aligned_events(index: pd.DatetimeIndex, events) -> tuple[pd.Series, pd.Series]:
    """Place each event on the first session of ``index`` at or after its date.

    A vendor can date an event on a day the other vendor does not quote. Snapping
    forward keeps the event inside the series it is being applied to instead of
    dropping it.
    """
    dividends = pd.Series(0.0, index=index)
    ratios = pd.Series(1.0, index=index)
    if events is None or not len(events):
        return dividends, ratios
    for stamp, row in events.iterrows():
        position = index.searchsorted(stamp, side="left")
        if position >= len(index):
            continue
        amount = float(row.get(DIVIDEND) or 0.0)
        ratio = float(row.get(SPLIT) or 0.0)
        if amount > 0:
            dividends.iloc[position] += amount
        if ratio > 0 and ratio != 1.0:
            ratios.iloc[position] *= ratio
    return dividends, ratios


def to_total_return(frame: pd.DataFrame, events=None) -> tuple[pd.DataFrame, list[dict]]:
    """Rebase one vendor frame onto the as-traded, forward total-return basis.

    ``frame`` is a split-adjusted, dividend-unadjusted OHLCV — Yahoo fetched
    with ``auto_adjust=False, actions=True``, or FinanceDataReader's Korean
    bars. ``events`` supplies the dividends and splits when the frame does not
    carry them itself, which is how Korean sessions from one vendor are joined
    to distributions from the other.

    Returns the rebased frame — ``Dividends`` and ``Stock Splits`` carried on it
    in AS-TRADED terms so they can be sealed as their own evidence — and the
    event rows, including any the adjustment refused to apply.
    """
    if frame is None or "Close" not in frame:
        return frame, []
    clean = normalize_daily_frame(frame).copy()
    if not len(clean):
        return clean, []

    if events is None:
        raw_dividends = _series(clean, DIVIDEND, 0.0)
        # Yahoo writes 0.0 for "no split here"; a real ratio is strictly positive.
        raw_splits = _series(clean, SPLIT, 0.0)
        ratios = raw_splits.where(raw_splits > 0, 1.0)
    else:
        raw_dividends, ratios = _aligned_events(clean.index, events)
    after = future_split_factor(ratios)

    # As traded: the numbers that actually printed on the day.
    as_traded = clean.copy()
    for column in SCALED_COLUMNS:
        if column in as_traded.columns:
            as_traded[column] = _series(clean, column, np.nan) * after
    dividends = raw_dividends * after
    if "Volume" in as_traded.columns:
        # Share counts move inversely to price through a split.
        as_traded["Volume"] = _series(clean, "Volume", np.nan) / after

    close = as_traded["Close"].to_numpy(dtype=float)
    amounts = dividends.to_numpy(dtype=float)
    ratio_values = ratios.to_numpy(dtype=float)
    dates = as_traded.index

    events: list[dict] = []
    step = np.ones(len(close))
    for i in range(len(close)):
        if ratio_values[i] != 1.0:
            step[i] *= ratio_values[i]
            events.append({"date": dates[i].strftime("%Y-%m-%d"),
                           "split": float(ratio_values[i]), "applied": True})
        amount = amounts[i]
        if amount <= 0:
            continue
        previous = close[i - 1] if i else np.nan
        row = {"date": dates[i].strftime("%Y-%m-%d"), "dividend": float(amount)}
        # The first session has nothing to accrue against, and a payment that
        # swallows the previous close is a vendor error, not a distribution.
        # Both are recorded rather than silently folded into the index.
        if not np.isfinite(previous) or previous <= 0:
            events.append({**row, "applied": False, "reason": "NO_PREVIOUS_CLOSE"})
            continue
        if amount >= previous:
            events.append({**row, "applied": False,
                           "reason": "DIVIDEND_NOT_BELOW_PREVIOUS_CLOSE"})
            continue
        step[i] *= 1.0 / (1.0 - amount / previous)
        events.append({**row, "applied": True})

    cumulative = np.cumprod(step)
    result = as_traded.copy()
    for column in SCALED_COLUMNS:
        if column in result.columns:
            result[column] = result[column].to_numpy(dtype=float) * cumulative
    if "Volume" in result.columns:
        # Only the split half of the cumulative factor applies to share counts.
        split_only = np.cumprod(ratio_values)
        result["Volume"] = result["Volume"].to_numpy(dtype=float) / split_only
    result[DIVIDEND] = dividends.to_numpy(dtype=float)
    result[SPLIT] = ratio_values
    events.sort(key=lambda row: (row["date"], "split" not in row))
    return result, events


def rebase_frames(frames: dict[str, pd.DataFrame],
                  events: dict[str, pd.DataFrame] | None = None
                  ) -> tuple[dict[str, pd.DataFrame], dict[str, list[dict]]]:
    """``to_total_return`` over a whole panel, keeping each ticker's events."""
    prices: dict[str, pd.DataFrame] = {}
    out_events: dict[str, list[dict]] = {}
    for ticker, frame in (frames or {}).items():
        rebased, rows = to_total_return(
            frame, None if events is None else events.get(ticker))
        if rebased is None or not len(rebased):
            continue
        prices[ticker] = rebased
        if rows:
            out_events[ticker] = rows
    return prices, out_events
