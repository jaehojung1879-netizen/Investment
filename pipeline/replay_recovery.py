"""Versioned, source-backed recovery for replay valuation inputs.

Recovery is deliberately narrower than generic missing-value filling:

* USD/KRW is one official FRED/H.10 series for the whole generation.  A
  valuation session uses the latest fixing published on or before that date;
  it never reads a future observation and it refuses a stale fixing.
* Korean equity rows are recovered only for a market-wide hole in the primary
  Yahoo panel.  The independent FDR return is applied to the preceding Yahoo
  adjusted close, and the bridge to the next Yahoo close must agree.  An
  individual suspension/delisting is therefore never filled by this path.
* Corporate actions are a reviewed static ledger, content-addressed with every
  other input.  They are not inferred from a missing terminal quote.
"""
from __future__ import annotations

import math
import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import replay_calendar as RC
from .market_dates import normalize_daily_frame, normalize_daily_series

RECOVERY_VERSION = "fred-h10-fx-v1+fdr-systemic-gap-v1+corporate-actions-v1"
FX_SERIES_ID = "DEXKOUS"  # Korean won per US dollar, Federal Reserve H.10
FX_MAX_STALENESS_DAYS = 7
KR_MIN_MISSING_NAMES = 20
KR_SYSTEMIC_MISSING_SHARE = 0.05
KR_MAX_GAP_SESSIONS = 3
KR_BRIDGE_TOLERANCE_BPS = 25.0
CORPORATE_ACTIONS_PATH = Path(__file__).resolve().parents[1] / "data" / "replay-corporate-actions.json"


class RecoveryError(RuntimeError):
    """A required source cannot produce a defensible replay input."""


def load_corporate_actions(path: str | Path = CORPORATE_ACTIONS_PATH) -> dict:
    import json

    book = json.loads(Path(path).read_text(encoding="utf-8"))
    if book.get("schema") != "REPLAY_CORPORATE_ACTIONS_V1" or not book.get("version"):
        raise RecoveryError("invalid replay corporate-action ledger")
    seen = set()
    for row in book.get("actions") or []:
        required = ("ticker", "region", "type", "effectiveDate")
        if any(not row.get(key) for key in required):
            raise RecoveryError("corporate-action row is missing an identity field")
        key = (row["ticker"], row["effectiveDate"])
        if key in seen:
            raise RecoveryError(f"duplicate corporate action: {key}")
        seen.add(key)
        if row["type"] != "CASH_AND_STOCK_MERGER":
            raise RecoveryError(f"unsupported corporate action: {row['type']}")
        if float(row.get("cashPerShare", -1)) < 0 or float(row.get("successorSharesPerShare", 0)) <= 0:
            raise RecoveryError(f"invalid merger consideration: {key}")
        if not row.get("successorTicker") or len(row.get("sources") or []) < 1:
            raise RecoveryError(f"unvouched merger action: {key}")
    return book


def successor_dependencies(book: dict) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for row in book.get("actions") or []:
        out.setdefault(row["region"], []).append(row["successorTicker"])
    return {region: list(dict.fromkeys(names)) for region, names in out.items()}


def fetch_fred_usdkrw(api_key: str | None, start: str, *, retries: int = 3,
                      fetcher=None) -> pd.Series:
    """Fetch the official H.10 DEXKOUS observations as one unspliced vintage."""
    if not api_key and fetcher is None:
        raise RecoveryError("FRED_API_KEY is required for replay-v9 USD/KRW inputs")
    if fetcher is None:
        from fredapi import Fred

        fred = Fred(api_key=api_key)
        fetcher = lambda: fred.get_series(FX_SERIES_ID, observation_start=start)
    delay = 2.0
    last_error = None
    for attempt in range(retries):
        try:
            raw = fetcher()
            values = pd.to_numeric(raw, errors="coerce").dropna()
            values = normalize_daily_series(values[values > 0]).sort_index()
            if len(values):
                return values.rename("USD_KRW")
            last_error = "empty series"
        except Exception as exc:  # pragma: no cover - network dependent
            last_error = str(exc)
        if attempt < retries - 1:
            time.sleep(delay)
            delay *= 2
    raise RecoveryError(f"FRED {FX_SERIES_ID} unavailable after {retries} attempts: {last_error}")


def resolve_fx_fixings(observations: pd.Series, dates: pd.DatetimeIndex, *,
                       max_staleness_days: int = FX_MAX_STALENESS_DAYS) -> tuple[pd.Series, list[dict]]:
    """Resolve each valuation session to the latest non-future official fixing."""
    source = normalize_daily_series(pd.to_numeric(observations, errors="coerce").dropna())
    source = source[(source > 0) & np.isfinite(source)].sort_index()
    wanted = pd.DatetimeIndex(pd.to_datetime(dates)).normalize().unique().sort_values()
    if not len(source) or not len(wanted):
        raise RecoveryError("USD/KRW fixing observations or valuation sessions are empty")
    lookup = pd.Series(source.index, index=source.index)
    resolved = source.reindex(source.index.union(wanted)).sort_index().ffill().reindex(wanted)
    observed_at = lookup.reindex(lookup.index.union(wanted)).sort_index().ffill().reindex(wanted)
    age = pd.Series((wanted - pd.DatetimeIndex(observed_at)).days, index=wanted)
    bad = resolved.isna() | observed_at.isna() | (age < 0) | (age > int(max_staleness_days))
    if bad.any():
        sample = ", ".join(str(d.date()) for d in wanted[bad.to_numpy()][:8])
        raise RecoveryError(f"USD/KRW has no timely prior H.10 fixing for {sample}")
    mapping = [{"date":str(date.date()), "observationDate":str(pd.Timestamp(obs).date()),
                "ageCalendarDays":int(days), "seriesId":FX_SERIES_ID,
                "policy":"LATEST_PUBLISHED_FIXING_ON_OR_BEFORE_SESSION"}
               for date, obs, days in zip(wanted, observed_at, age)]
    return resolved.rename("USD_KRW"), mapping


def _fdr_frame(ticker: str, start: str, end: str, retries: int = 3) -> pd.DataFrame | None:
    import FinanceDataReader as fdr

    symbol = ticker.removesuffix(".KS").removesuffix(".KQ")
    delay = 1.0
    for attempt in range(retries):
        try:
            frame = fdr.DataReader(symbol, start, end)
            if frame is not None and not frame.empty:
                return frame
        except Exception as exc:  # pragma: no cover - network dependent
            print(f"    warning: FinanceDataReader {ticker} attempt {attempt + 1} failed: {exc}")
        if attempt < retries - 1:
            time.sleep(delay)
            delay *= 2
    return None


def _systemic_dates(prices: dict[str, pd.DataFrame], tickers: list[str],
                    benchmark: pd.Series, start: str, through: str) -> tuple[dict[pd.Timestamp, set[str]], list[dict]]:
    sessions = RC.sessions(start, through, "KR")
    benchmark_dates = set(normalize_daily_series(benchmark).dropna().index)
    rows = []
    systemic: dict[pd.Timestamp, set[str]] = {}
    series = {ticker: normalize_daily_series(frame["Close"]).dropna()
              for ticker in tickers for frame in [prices.get(ticker)]
              if frame is not None and "Close" in frame}
    for date in sessions:
        if date not in benchmark_dates:
            continue
        active, missing = [], []
        for ticker, values in series.items():
            # Requiring an observation on both sides excludes IPOs, delistings,
            # and terminal suspensions from the recovery population.
            if bool((values.index < date).any()) and bool((values.index > date).any()):
                active.append(ticker)
                value = values.get(date, np.nan)
                if not np.isfinite(value) or value <= 0:
                    missing.append(ticker)
        threshold = max(KR_MIN_MISSING_NAMES, math.ceil(len(active) * KR_SYSTEMIC_MISSING_SHARE))
        if active and len(missing) >= threshold:
            systemic[date] = set(missing)
            rows.append({"date":str(date.date()), "activeNames":len(active),
                         "missingNames":len(missing), "missingShare":len(missing)/len(active),
                         "thresholdNames":threshold})
    return systemic, rows


def _groups(index: pd.DatetimeIndex, selected: set[pd.Timestamp]) -> list[list[pd.Timestamp]]:
    positions = [i for i, date in enumerate(index) if date in selected]
    groups: list[list[pd.Timestamp]] = []
    for position in positions:
        if not groups or position != index.get_loc(groups[-1][-1]) + 1:
            groups.append([index[position]])
        else:
            groups[-1].append(index[position])
    return groups


def recover_systemic_kr_gaps(prices: dict[str, pd.DataFrame], tickers: list[str],
                             benchmark_ticker: str, *, start: str, through: str,
                             fetcher=None) -> dict:
    """Recover only validated, market-wide missing Korean primary-vendor bars.

    ``prices`` is updated in place.  The returned audit rows are snapshotted,
    including rejected attempts; a vendor recovery therefore cannot silently
    rewrite an already published generation.
    """
    benchmark_frame = prices.get(benchmark_ticker)
    if benchmark_frame is None or "Close" not in benchmark_frame:
        raise RecoveryError("KR benchmark is required before systemic-gap recovery")
    systemic, population = _systemic_dates(
        prices, tickers, benchmark_frame["Close"], start, through)
    result = {"version":RECOVERY_VERSION, "systemicDates":population,
              "accepted":[], "rejected":[]}
    if not systemic:
        return result
    fetcher = fetcher or _fdr_frame
    kr_sessions = RC.sessions(start, through, "KR")
    for ticker in tickers:
        frame = prices.get(ticker)
        if frame is None or "Close" not in frame:
            continue
        primary = normalize_daily_frame(frame).copy()
        # Only names counted as active (observed on both sides of this date)
        # may be repaired. A global batch hole must never backfill an IPO's
        # pre-listing dates or a delisted name's post-exit dates.
        missing = {date for date, affected in systemic.items() if ticker in affected}
        if not missing:
            continue
        fallback = fetcher(ticker,
                           str((min(missing) - pd.Timedelta(days=14)).date()),
                           str((max(missing) + pd.Timedelta(days=14)).date()))
        if fallback is None or "Close" not in fallback:
            result["rejected"].append({"ticker":ticker, "dates":sorted(str(d.date()) for d in missing),
                                       "reason":"FDR_NO_DATA"})
            continue
        fallback = normalize_daily_frame(fallback)
        for group in _groups(kr_sessions, missing):
            if len(group) > KR_MAX_GAP_SESSIONS:
                result["rejected"].append({"ticker":ticker,
                    "dates":[str(d.date()) for d in group], "reason":"GAP_TOO_LONG"})
                continue
            first_pos, last_pos = kr_sessions.get_loc(group[0]), kr_sessions.get_loc(group[-1])
            if first_pos == 0 or last_pos + 1 >= len(kr_sessions):
                reason = "NO_PRIMARY_BRIDGE"
                result["rejected"].append({"ticker":ticker,
                    "dates":[str(d.date()) for d in group], "reason":reason})
                continue
            left, right = kr_sessions[first_pos - 1], kr_sessions[last_pos + 1]
            needed = [left, *group, right]
            if (left not in primary.index or right not in primary.index
                    or any(date not in fallback.index for date in needed)):
                result["rejected"].append({"ticker":ticker,
                    "dates":[str(d.date()) for d in group], "reason":"NO_PRIMARY_OR_FDR_BRIDGE"})
                continue
            p_left, p_right = float(primary.at[left,"Close"]), float(primary.at[right,"Close"])
            f_left, f_right = float(fallback.at[left,"Close"]), float(fallback.at[right,"Close"])
            if min(p_left,p_right,f_left,f_right) <= 0:
                result["rejected"].append({"ticker":ticker,
                    "dates":[str(d.date()) for d in group], "reason":"NON_POSITIVE_BRIDGE"})
                continue
            bridge_bps = abs((p_right/p_left)/(f_right/f_left)-1) * 10000
            if bridge_bps > KR_BRIDGE_TOLERANCE_BPS:
                result["rejected"].append({"ticker":ticker,
                    "dates":[str(d.date()) for d in group], "reason":"ADJUSTED_RETURN_BRIDGE_MISMATCH",
                    "bridgeDifferenceBps":float(bridge_bps)})
                continue
            scale = p_left / f_left
            columns = [column for column in ("Open","High","Low","Close","Volume")
                       if column in fallback.columns]
            for date in group:
                for column in columns:
                    value = fallback.at[date,column]
                    if pd.isna(value):
                        continue
                    primary.loc[date,column] = float(value) if column == "Volume" else float(value) * scale
            primary.sort_index(inplace=True)
            result["accepted"].append({"ticker":ticker,
                "date":str(group[0].date()), "dates":[str(d.date()) for d in group],
                "primaryVendor":"YAHOO_AUTO_ADJUSTED", "fallbackVendor":"FINANCE_DATA_READER",
                "method":"FDR_RETURN_ANCHORED_TO_PREVIOUS_PRIMARY_CLOSE",
                "leftAnchor":str(left.date()), "rightAnchor":str(right.date()),
                "bridgeDifferenceBps":float(bridge_bps), "scale":float(scale)})
        prices[ticker] = primary
    return result
