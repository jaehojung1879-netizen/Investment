"""Korean replay prices: exchange-native sessions, vendor-checked.

WHY THE VENDOR CHANGED
----------------------
Yahoo was the primary price source for Korean equities, and its KRX history is
incomplete in a way no recovery inside it can repair. Measured on the
replay-v11 production run:

* Yahoo serves 3,782 sessions of KOSPI 200 against FinanceDataReader's 3,855 —
  73 KRX sessions, 1.9% of the record, that Yahoo does not have.
* Five of those are absent for the WHOLE Korean cross-section: 2017-09-22,
  2017-12-20, 2022-01-03, 2022-05-09 and 2025-09-19, each missing for all 61-68
  names active on the day.
* v11 narrowed the same-vendor retry to one window per gap cluster, and it still
  recovered nothing: `targetedYahooRetries: 0` across all five. Every one of the
  284 repairs came from FDR. Sessions a vendor does not have cannot be retried
  into existence.
* The 42 names the bridge check then refused on 2025-09-19 were refused against
  Yahoo's own anchors, which disagree with FDR's by a median 55 bps (max 227).
  That disagreement is uncorrelated with each name's daily volatility
  (r = -0.07) and is a third of a typical day's move, so it is not a shifted
  session label — it is the level itself.

So the replay reads Korean sessions from the exchange-native vendor and keeps
Yahoo for what Yahoo does have and FDR does not publish: the distributions.

WHAT EACH VENDOR CONTRIBUTES
----------------------------
* FinanceDataReader — every KRX session's bar, split-adjusted and
  dividend-unadjusted, exactly the shape Yahoo's unadjusted close has, so
  `price_adjustment.to_total_return` treats the two identically.
* Yahoo — the dividend and split events, which FDR does not serve. Both vendors
  quote to the same split basis, so an event carries across unchanged.
* Yahoo's closes are kept as a CROSS-CHECK. Every session both vendors quote is
  compared and the disagreement is summarised into the ledger rather than
  silently preferred away.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import price_adjustment as PA
from .market_dates import normalize_daily_frame

SOURCE_VERSION = "krx-native-sessions-with-yahoo-distributions-v2"

# How much later than the cross-check vendor the primary's history may start
# before the run refuses to seal it. replay-v12 sealed a Korean panel whose 56
# of 68 names began on 2014-06-23 instead of 2011-01-03, because
# FinanceDataReader's default Naver endpoint ignores `start` and returns a fixed
# trailing window. Nothing failed: the contract passed on 154/154 matured
# blocks while three and a half years of the Korean cross-section had quietly
# gone. A truncated primary is not allowed to be silent twice.
TRUNCATION_TOLERANCE_SESSIONS = 21

# How many names must share one late start date before it counts as a truncated
# download rather than a listing date.
#
# A capped download cuts every name to the SAME boundary, because the cap is a
# row count measured back from today: replay-v12 truncated 56 of 68 Korean names
# to 2014-06-23 exactly. A real listing date is idiosyncratic — replay-v13's
# first working fetch flagged two names, 175330.KS at 2013-07-18 and 018260.KS
# at 2014-11-14, two unrelated dates, each the day that stock actually began
# trading. Yahoo's earlier history for those is its own artifact: it back-fills
# a holding company with its predecessor's record and quotes some names before
# they listed. Treating "the cross-check has more history" as proof the primary
# is short gets that backwards, and would refuse a correct Korean panel forever.
TRUNCATION_CLUSTER_NAMES = 3


def _agreement(primary: pd.DataFrame, secondary: pd.DataFrame | None) -> dict | None:
    """How far apart the two vendors are on the sessions they both quote."""
    if secondary is None or "Close" not in secondary or not len(secondary):
        return None
    left = pd.to_numeric(primary["Close"], errors="coerce")
    right = pd.to_numeric(normalize_daily_frame(secondary)["Close"], errors="coerce")
    shared = left.index.intersection(right.index)
    if not len(shared):
        return None
    a, b = left.reindex(shared), right.reindex(shared)
    usable = a.notna() & b.notna() & (a > 0) & (b > 0)
    if not usable.any():
        return None
    difference = np.abs((b[usable] / a[usable] - 1).to_numpy(float)) * 10000
    # How much of the second vendor's history the primary is missing from the
    # FRONT. Sessions the primary lacks in the middle are a hole; sessions it
    # lacks at the start are a truncated download, and they look identical in a
    # row count.
    primary_start, secondary_start = left.dropna().index[0], right.dropna().index[0]
    starts_later = int((right.dropna().index < primary_start).sum())
    return {"sharedSessions": int(usable.sum()),
            "onlyPrimarySessions": int(len(left.dropna()) - usable.sum()),
            "onlySecondarySessions": int(len(right.dropna().index.difference(shared))),
            "primaryFirstSession": primary_start.strftime("%Y-%m-%d"),
            "secondaryFirstSession": secondary_start.strftime("%Y-%m-%d"),
            "primaryStartsLaterSessions": starts_later,
            "medianDifferenceBps": float(np.median(difference)),
            "p99DifferenceBps": float(np.percentile(difference, 99)),
            "maxDifferenceBps": float(difference.max())}


def acquire(tickers: list[str], start: str, *, end: str | None = None,
            session_fetcher=None, action_fetcher=None) -> dict:
    """Korean total-return bars, plus the evidence for how they were built."""
    from .datafeed import AS_TRADED_WITH_ACTIONS, fetch_krx_sessions, fetch_prices

    tickers = list(dict.fromkeys(tickers))
    if not tickers:
        return {"prices": {}, "events": {}, "agreement": [], "missing": [],
                "routes": {}, "source": SOURCE_VERSION}
    routes: dict[str, str] = {}
    session_fetcher = session_fetcher or (
        lambda names: fetch_krx_sessions(names, start, end=end, routes=routes))
    action_fetcher = action_fetcher or (
        lambda names: fetch_prices(names, start, end=end, auto_adjust=False,
                                   actions=True, columns=AS_TRADED_WITH_ACTIONS))

    sessions = session_fetcher(tickers) or {}
    actions = action_fetcher(tickers) or {}

    prices: dict[str, pd.DataFrame] = {}
    events: dict[str, list[dict]] = {}
    agreement: list[dict] = []
    for ticker in tickers:
        frame = sessions.get(ticker)
        if frame is None or "Close" not in frame or not len(frame):
            continue
        clean = normalize_daily_frame(frame)
        rebased, rows = PA.to_total_return(
            clean, PA.event_columns(actions.get(ticker)))
        if rebased is None or not len(rebased):
            continue
        prices[ticker] = rebased
        if rows:
            events[ticker] = rows
        row = _agreement(clean, actions.get(ticker))
        if row:
            agreement.append({"ticker": ticker, **row})
    return {"prices": prices, "events": events, "agreement": agreement,
            "missing": [t for t in tickers if t not in prices],
            "requested": len(tickers), "routes": routes,
            "source": SOURCE_VERSION}


# How much of the Korean universe the primary may fail to serve at all before
# the run stops. replay-v13's first attempt got `400 Bad Request` from KRX for
# every one of 119 names and carried on for fifteen more minutes, to die at the
# benchmark preflight with "KR 126D: None% (0/0)" — a message about the
# benchmark, for a failure in the price fetch.
MINIMUM_SERVED_SHARE = 0.90


def acquisition_failure(result: dict) -> str | None:
    """Why the Korean acquisition cannot be used, in one line, or None."""
    requested = int(result.get("requested") or 0)
    if not requested:
        return None
    served = requested - len(result.get("missing") or [])
    if served == 0:
        return (f"the Korean price vendor served no sessions at all for any of "
                f"{requested} tickers")
    if served < requested * MINIMUM_SERVED_SHARE:
        return (f"the Korean price vendor served only {served} of {requested} "
                f"tickers ({served / requested:.1%}, floor "
                f"{MINIMUM_SERVED_SHARE:.0%})")
    return None


def _late_row(row: dict) -> dict:
    return {"ticker": row["ticker"],
            "primaryFirstSession": row["primaryFirstSession"],
            "secondaryFirstSession": row["secondaryFirstSession"],
            "sessions": row["primaryStartsLaterSessions"]}


def coverage_shortfall(rows: list[dict]) -> dict:
    """Evidence that the primary's history was cut short by the download.

    This is the check replay-v12 did not have. A vendor that answers with a
    short window answers successfully, so nothing downstream can tell the
    difference between "this name listed in 2014" and "this download stopped at
    2014" — except the other vendor, which has the earlier sessions.

    But "the other vendor has more" is not the same claim. What separates the
    two is the SHAPE: a capped download cuts many names to one shared boundary,
    a listing date belongs to one name. So only a shared late start counts as a
    truncation; the idiosyncratic ones are reported and allowed through.
    """
    late = sorted((row for row in rows
                   if row.get("primaryStartsLaterSessions", 0)
                   > TRUNCATION_TOLERANCE_SESSIONS),
                  key=lambda row: -row["primaryStartsLaterSessions"])
    shared: dict[str, list[dict]] = {}
    for row in late:
        shared.setdefault(row["primaryFirstSession"], []).append(row)
    clustered = [group for group in shared.values()
                 if len(group) >= TRUNCATION_CLUSTER_NAMES]
    truncated = [row for group in clustered for row in group]
    idiosyncratic = [row for row in late if row not in truncated]
    return {
        "tickers": len(truncated),
        "toleranceSessions": TRUNCATION_TOLERANCE_SESSIONS,
        "clusterNames": TRUNCATION_CLUSTER_NAMES,
        "missingSessions": int(sum(row["primaryStartsLaterSessions"]
                                   for row in truncated)),
        "sharedStartDates": sorted(group[0]["primaryFirstSession"]
                                   for group in clustered),
        "worst": [_late_row(row) for row in truncated[:8]],
        # Not a failure: one name starting later than the cross-check is what a
        # listing date looks like from here.
        "lateStartsWithoutSharedBoundary": [_late_row(row)
                                            for row in idiosyncratic[:8]],
    }


def agreement_summary(rows: list[dict]) -> dict:
    """One line for the diagnostics: how much the two vendors disagree, and where."""
    if not rows:
        return {"tickers": 0}
    median = np.array([row["medianDifferenceBps"] for row in rows], dtype=float)
    worst = max(rows, key=lambda row: row["maxDifferenceBps"])
    return {
        "tickers": len(rows),
        "sharedSessions": int(sum(row["sharedSessions"] for row in rows)),
        # Sessions the exchange-native vendor has and Yahoo does not are the
        # whole reason for the change; sessions only Yahoo has would be a
        # warning that the primary is now the incomplete one.
        "sessionsOnlyInPrimary": int(sum(row["onlyPrimarySessions"] for row in rows)),
        "sessionsOnlyInSecondary": int(sum(row["onlySecondarySessions"] for row in rows)),
        "medianOfMedianDifferenceBps": float(np.median(median)),
        "worstTicker": worst["ticker"],
        "worstDifferenceBps": float(worst["maxDifferenceBps"]),
        "policy": "FDR_SESSIONS_ARE_AUTHORITATIVE; YAHOO_IS_A_RECORDED_CROSS_CHECK",
    }
