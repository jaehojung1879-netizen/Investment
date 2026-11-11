"""When did an observation become public? Release rules used by the v2 evidence packet.

An observation DATE is not an availability TIME. Each source gets an explicit rule, and
an observation may enter a cohort's evidence only if its release time is at or before
that region's information cutoff (the regional close of the receipt's asOfDate).

Rules verified 2026-11-11 against the publisher's own pages (see SOURCE_EVIDENCE):
  H10   Fed H.10 daily FX (DEXKOUS): released Monday 16:15 ET for the previous business
        week; next business day if Monday is a federal holiday. Weekly publication was
        suspended 2006-05-22..2009-01: availability there is UNVERIFIED.
  H15   Fed H.15 (DGS10, DGS3MO): posted Monday-Friday 16:15 ET; the 2026-11-10 release
        carries data through 2026-11-09, so observation d is public the next federal
        business day at 16:15 ET. T10YIE is computed by FRED from H.15 inputs and is
        given the same rule.
  VIX   VIXCLS via FRED. CBOE prints the close on d, but the FRED posting time is not
        verifiable; the CONSERVATIVE rule is the H.15 rule (next business day 16:15 ET).
  EXCH  An exchange close (KRX, NYSE) is public at that session's close.
  FX_VENDOR  Yahoo FX daily bars have no verifiable close time and are EXCLUDED.
"""
from __future__ import annotations

from functools import lru_cache

import pandas as pd

ET = "America/New_York"
SOURCE_EVIDENCE = {
    "H10": {"url": "https://www.federalreserve.gov/releases/h10/", "retrievedUtc": "2026-11-11T22:23Z",
            "quote": "On Mondays at 4:15 p.m. the Federal Reserve Board releases daily bilateral exchange rates and U.S. dollar indexes for the previous business week. If Monday falls on a Federal Holiday, the data will be released on the following business day."},
    "H15": {"url": "https://www.federalreserve.gov/releases/h15/", "retrievedUtc": "2026-11-11T22:23Z",
            "quote": "The release is posted daily Monday through Friday at 4:15pm. ... Release date: November 10, 2026 ... 2026 Nov 3 ... 2026 Nov 9"},
}
RULES = {"DEXKOUS": "H10", "DGS10": "H15", "DGS3MO": "H15", "T10YIE": "H15", "VIXCLS": "VIX"}
H10_SUSPENDED = (pd.Timestamp("2006-05-22"), pd.Timestamp("2009-01-31"))


@lru_cache(maxsize=1)
def _holidays() -> frozenset:
    from pandas.tseries.holiday import USFederalHolidayCalendar
    return frozenset(USFederalHolidayCalendar().holidays(start="1990-01-01", end="2035-12-31"))


def _business(d: pd.Timestamp) -> bool:
    return d.weekday() < 5 and d not in _holidays()


def _next_business(d: pd.Timestamp) -> pd.Timestamp:
    d = d + pd.Timedelta(days=1)
    while not _business(d):
        d += pd.Timedelta(days=1)
    return d


def release_utc(series: str, obs_date) -> pd.Timestamp | None:
    """UTC release time of a FRED observation, or None if the rule cannot vouch for it."""
    d = pd.Timestamp(obs_date).normalize()
    rule = RULES[series]
    if rule == "H10":
        if H10_SUSPENDED[0] <= d <= H10_SUSPENDED[1]:
            return None
        day = d + pd.Timedelta(days=7 - d.weekday())
        while not _business(day):
            day += pd.Timedelta(days=1)
    else:  # H15 and the conservative VIX rule
        day = _next_business(d)
    return (day + pd.Timedelta(hours=16, minutes=15)).tz_localize(ET).tz_convert("UTC")


@lru_cache(maxsize=4)
def calendar(region: str):
    import exchange_calendars as xc
    end = (pd.Timestamp.now(tz="UTC").tz_localize(None).normalize() + pd.Timedelta(days=730)).strftime("%Y-%m-%d")
    return xc.get_calendar({"KR": "XKRX", "US": "XNYS"}[region], start="2000-01-01", end=end)


def exchange_close_utc(region: str, session) -> pd.Timestamp:
    return pd.Timestamp(calendar(region).session_close(pd.Timestamp(session).strftime("%Y-%m-%d")))


def cutoff_utc(region: str, as_of: str) -> pd.Timestamp:
    """Information cutoff of a cohort: the regional close of the receipt's asOfDate."""
    return exchange_close_utc(region, as_of)


def available_fred(series: str, values: pd.Series, cutoff: pd.Timestamp) -> pd.Series:
    """Observations of a FRED series whose release time is at or before the cutoff."""
    keep = [d for d in values.index if (r := release_utc(series, d)) is not None and r <= cutoff]
    return values.loc[keep]


def available_closes(region: str, closes: pd.Series, cutoff: pd.Timestamp) -> pd.Series:
    keep = [d for d in closes.index if exchange_close_utc(region, d) <= cutoff]
    return closes.loc[keep]
