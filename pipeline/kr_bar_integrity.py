"""Read-side integrity of KR daily bars for FORWARD records: an unexplained value is missing, never repaired.

The 2026-10-21 read-only audit of the KRX price store (signal-history ``80611460``, PR #263 comment 6327469997) found two defects that
silently move a forward-looking number if a reader trusts the stored row:

* eight TRADED rows (volume > 0, positive close) whose open, high and low are 0 — a range that runs to zero is not a price the market printed,
  and its cause is unverified;
* open sessions marked done with no rows (2026-09-15, 2026-09-16, 2026-10-01) — a reader that walks rows instead of the exchange calendar
  silently stretches a "20-session" window over 22 sessions.

The sealed readers (``krx_prices.frame_from_rows``, ``kr_alpha_atlas_bars.TickerBars``) are pinned by closed studies and are not edited; this
module is the reader for forward records (``kr_selection_challenger``). It works on any OHLCV frame (KRX store rows or the vendor frames of
``datafeed.fetch_prices``), aligns it to the pinned exchange calendar, and returns per-session codes:

    VALID                        a traded session whose fields are consistent;
    SUSPENDED                    zero volume: not a session the name traded (KRX carries the last close forward, Yahoo repeats it);
    VOLUME_INVALID               the volume is missing, non-finite or negative: whether the name traded is unknown, so the session is
                                 missing (never read as traded, and never as a suspension either, which is a fact the vendor stated);
    RANGE_UNRESOLVED             traded, close valid, but open/high/low zero, non-finite or inconsistent with the close: the range is set
                                 missing and the close is kept;
    CLOSE_INVALID                the close is missing, non-finite or not positive: the whole session is missing;
    SESSION_MISSING              an exchange session inside the span with no row at all.

Nothing is filled, carried, interpolated or replaced with 0, and no stored byte is changed.
"""
from __future__ import annotations

import math

import pandas as pd

from . import replay_calendar as RC

STATES = ("VALID", "SUSPENDED", "RANGE_UNRESOLVED", "CLOSE_INVALID", "VOLUME_INVALID", "SESSION_MISSING")
NO_CLOSE_STATES = ("SUSPENDED", "CLOSE_INVALID", "VOLUME_INVALID", "SESSION_MISSING")
PRICE_FIELDS = ("Open", "High", "Low")
REL_TOLERANCE = 1e-9


def _number(value):
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def classify_row(open_, high, low, close, volume):
    """The state of one stored row and which price fields survive."""
    close, volume = _number(close), _number(volume)
    if close is None or close <= 0:
        return "CLOSE_INVALID"
    if volume is None or volume < 0:      # None covers a missing field, NaN and +/-inf (_number maps non-finite to None)
        return "VOLUME_INVALID"
    if volume == 0:
        return "SUSPENDED"
    prices = [_number(v) for v in (open_, high, low)]
    if any(p is None or p <= 0 for p in prices):
        return "RANGE_UNRESOLVED"
    o, h, lo = prices
    slack = REL_TOLERANCE * max(h, 1.0)
    if lo > h + slack or not (lo - slack <= o <= h + slack) or not (lo - slack <= close <= h + slack):
        return "RANGE_UNRESOLVED"
    return "VALID"


def sessions_between(start, end, calendar="KR"):
    return RC.sessions(str(pd.Timestamp(start).date()), str(pd.Timestamp(end).date()), calendar)


def calendar_frame(frame: pd.DataFrame, *, start=None, end=None, calendar="KR") -> pd.DataFrame:
    """Align one ticker's OHLCV frame to the exchange calendar and attach a ``state`` per session.

    Rows dated on a closed day are dropped and counted in ``frame.attrs['offCalendarRows']`` (a vendor row on a holiday is not a session);
    duplicate dates keep the first row. Unusable fields become NaN; a suspended or invalid session keeps no close."""
    if frame is None or not len(frame):
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume", "state"])
    raw = frame.copy()
    index = pd.DatetimeIndex(pd.to_datetime(raw.index))
    raw.index = (index.tz_localize(None) if index.tz is not None else index).normalize()
    raw = raw[~raw.index.duplicated(keep="first")].sort_index()
    first = pd.Timestamp(start) if start is not None else raw.index.min()
    last = pd.Timestamp(end) if end is not None else raw.index.max()
    days = pd.DatetimeIndex(sessions_between(first, last, calendar))
    off = int((~raw.index.isin(days) & (raw.index >= first) & (raw.index <= last)).sum())
    aligned = raw.reindex(days)
    out = pd.DataFrame(index=days)
    states = []
    for _, row in aligned.iterrows():
        if row.isna().all():
            states.append("SESSION_MISSING")
            continue
        states.append(classify_row(row.get("Open"), row.get("High"), row.get("Low"), row.get("Close"), row.get("Volume")))
    out["state"] = states
    for col in ("Open", "High", "Low", "Close", "Volume"):
        values = pd.to_numeric(aligned[col], errors="coerce") if col in aligned else pd.Series(float("nan"), index=days)
        out[col] = values.where(values.map(lambda v: math.isfinite(v)))
    bad_range = out["state"].isin(["RANGE_UNRESOLVED", *NO_CLOSE_STATES])
    for col in PRICE_FIELDS:
        out.loc[bad_range, col] = float("nan")
    no_close = out["state"].isin(list(NO_CLOSE_STATES))
    out.loc[no_close, "Close"] = float("nan")
    out.attrs["offCalendarRows"] = off
    return out


def traded_close(frame: pd.DataFrame, session) -> float | None:
    """The close of exactly ``session`` if the name TRADED that session, else None. Never an earlier close."""
    session = pd.Timestamp(session).normalize()
    if frame is None or session not in frame.index or frame.loc[session, "state"] not in ("VALID", "RANGE_UNRESOLVED"):
        return None
    value = frame.loc[session, "Close"]
    return float(value) if pd.notna(value) else None


def window_complete(frame: pd.DataFrame, end, sessions: int) -> bool:
    """True only if the ``sessions`` exchange sessions ending at ``end`` all carry a traded close."""
    end = pd.Timestamp(end).normalize()
    if frame is None or end not in frame.index:
        return False
    position = frame.index.get_loc(end)
    if position + 1 < sessions:
        return False
    window = frame.iloc[position + 1 - sessions: position + 1]
    return bool(window["state"].isin(["VALID", "RANGE_UNRESOLVED"]).all())


def summary(frame: pd.DataFrame) -> dict:
    counts = {state: 0 for state in STATES}
    if frame is not None and len(frame):
        for state, n in frame["state"].value_counts().items():
            counts[str(state)] = int(n)
    return {"sessions": int(len(frame)) if frame is not None else 0, "states": counts,
            "offCalendarRows": int((frame.attrs.get("offCalendarRows") if frame is not None else 0) or 0)}


def store_session_gaps(done_dates, stored_dates, calendar="KR") -> list[str]:
    """Open exchange sessions a collector marked done but holds no row for (the audit's B2). Reported, never repaired."""
    stored = {str(pd.Timestamp(d).date()) for d in stored_dates}
    out = []
    for day in sorted({str(pd.Timestamp(d).date()) for d in done_dates}):
        found = sessions_between(day, day, calendar)
        if len(found) == 1 and str(found[0].date()) == day and day not in stored:
            out.append(day)
    return out
