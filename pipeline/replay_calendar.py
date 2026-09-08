"""Exchange-calendar schedules, independent of downloaded observations.

Session labels are valuation dates, not simultaneous KR/US execution timestamps.
The signal used at an anchor must be strictly older than the anchor.
"""
from functools import lru_cache
import hashlib
import json

import pandas as pd

CALENDAR_VERSION = "xkrx-xnys-4.11.1-v2-kr-2026-closures"
ORIGIN = "2013-01-01"
# Published exchange closures omitted by the pinned library. This is a
# source-backed calendar correction, never inferred from absent price rows.
# https://corp.tossinvest.com/en/post?category=52&id=21740&type=notice
KR_CLOSURES = ("2026-05-25", "2026-06-03", "2026-07-17")


@lru_cache(maxsize=64)
def sessions(start: str, end: str, region: str = "COMMON") -> pd.DatetimeIndex:
    import exchange_calendars as xc
    if pd.Timestamp(start) < pd.Timestamp("1990-01-01") or pd.Timestamp(end) > pd.Timestamp("2035-12-31"):
        raise ValueError("session request outside pinned calendar bounds; version the calendar before extending")
    names = {"KR": ("XKRX",), "US": ("XNYS",), "COMMON": ("XKRX", "XNYS"),
             "UNION": ("XKRX", "XNYS")}[region]
    calendars = [xc.get_calendar(n, start="1990-01-01", end="2035-12-31").sessions
                 .tz_localize(None).normalize() for n in names]
    calendars = [c.difference(pd.to_datetime(KR_CLOSURES)) if n == "XKRX" else c
                 for n, c in zip(names, calendars)]
    result = calendars[0]
    for other in calendars[1:]:
        result = result.union(other) if region == "UNION" else result.intersection(other)
    return result[(result >= pd.Timestamp(start)) & (result <= pd.Timestamp(end))]


def signal_grid(start: str, through: str, frequency: str = "W") -> list[str]:
    """Only completed calendar periods; Tuesday never becomes this week's Friday."""
    end = (pd.Timestamp(through) + pd.offsets.MonthEnd(1) + pd.Timedelta(days=7)).strftime("%Y-%m-%d")
    days = sessions(start, end, "UNION")
    freq = frequency.upper()
    if freq == "D":
        picked = days
    else:
        picked = pd.Series(days, index=days).groupby(days.to_period(freq)).max()
    return [pd.Timestamp(d).strftime("%Y-%m-%d") for d in picked
            if pd.Timestamp(d) <= pd.Timestamp(through)]


def schedule(start: str, through: str, horizon: int = 21,
             frequency: str = "W") -> list[dict]:
    """Every Nth common session from a fixed origin; incomplete blocks stay put."""
    if horizon <= 0:
        raise ValueError("horizon must be positive")
    end = (pd.Timestamp(through) + pd.Timedelta(days=horizon * 3 + 90)).strftime("%Y-%m-%d")
    days = sessions(start, end)
    grid = signal_grid(start, end, frequency)
    if grid:
        days = days[days > pd.Timestamp(grid[0])]
    out = []
    for i in range(0, len(days) - horizon, horizon):
        date = days[i].strftime("%Y-%m-%d")
        if date > through:
            break
        # This is the last SCHEDULED signal, never the last AVAILABLE signal.
        previous = [d for d in grid if d < date]
        out.append({"date": date, "endDate": days[i + horizon].strftime("%Y-%m-%d"),
                    "signalDate": previous[-1] if previous else None,
                    "anchorIndex": i // horizon})
    return out


def metadata(start: str, through: str, frequency: str = "W") -> dict:
    rows = schedule(start, through, frequency=frequency)
    return {"version": CALENDAR_VERSION, "origin": start, "through": through,
            "strideSessions": 21, "sessionRule": "XKRX_INTERSECTION_XNYS",
            "signalFrequency": frequency, "signalRule": "PREVIOUS_COMPLETED_PERIOD_STRICTLY_BEFORE_ANCHOR",
            "anchors": rows, "krClosureOverrides": list(KR_CLOSURES),
            "sha256": hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()}
