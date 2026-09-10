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

SOURCE_VERSION = "krx-fdr-sessions-with-yahoo-distributions-v1"


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
    return {"sharedSessions": int(usable.sum()),
            "onlyPrimarySessions": int(len(left.dropna()) - usable.sum()),
            "onlySecondarySessions": int(len(right.dropna().index.difference(shared))),
            "medianDifferenceBps": float(np.median(difference)),
            "p99DifferenceBps": float(np.percentile(difference, 99)),
            "maxDifferenceBps": float(difference.max())}


def acquire(tickers: list[str], start: str, *, end: str | None = None,
            session_fetcher=None, action_fetcher=None) -> dict:
    """Korean total-return bars, plus the evidence for how they were built."""
    from .datafeed import AS_TRADED_WITH_ACTIONS, fetch_fdr_prices, fetch_prices

    tickers = list(dict.fromkeys(tickers))
    if not tickers:
        return {"prices": {}, "events": {}, "agreement": [], "missing": [],
                "source": SOURCE_VERSION}
    session_fetcher = session_fetcher or (
        lambda names: fetch_fdr_prices(names, start, end=end))
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
            "source": SOURCE_VERSION}


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
