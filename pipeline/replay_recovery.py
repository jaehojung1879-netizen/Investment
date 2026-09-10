"""Versioned, source-backed recovery for replay valuation inputs.

Recovery is deliberately narrower than generic missing-value filling:

* USD/KRW is one official FRED/H.10 series for the whole generation.  A
  valuation session uses the latest fixing published on or before that date;
  it never reads a future observation and it refuses a stale fixing.
* Korean equity rows are recovered only for a market-wide hole in the primary
  Yahoo panel.  A targeted Yahoo adjusted-price retry is preferred.  Otherwise
  the independent FDR raw return is checked against Yahoo raw anchors before it
  is mapped into the adjusted-price basis.  An individual suspension/delisting
  is therefore never filled by this path.
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

RECOVERY_VERSION = "fred-h10-fx-v1+fdr-systemic-gap-clustered-retry-v3+corporate-actions-v1"
FX_SERIES_ID = "DEXKOUS"  # Korean won per US dollar, Federal Reserve H.10
FX_MAX_STALENESS_DAYS = 7
KR_MIN_MISSING_NAMES = 20
KR_SYSTEMIC_MISSING_SHARE = 0.05
KR_MAX_GAP_SESSIONS = 3
KR_BRIDGE_TOLERANCE_BPS = 25.0
# A larger adjusted/raw basis move is no longer an ordinary cash-distribution
# adjustment.  It needs a reviewed corporate-action row, not a generic gap
# bridge.  The production incident peaked at 227.11 bps.
KR_MAX_UNVOUCHED_ADJUSTMENT_BPS = 500.0
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
        raise RecoveryError("FRED_API_KEY is required for source-backed replay USD/KRW inputs")
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


def _yahoo_targeted_frames(tickers: list[str], start: str, end: str, *,
                           adjusted: bool) -> dict[str, pd.DataFrame]:
    """Small-window retry used only after a market-wide batch hole is proven."""
    from .datafeed import UNADJUSTED_WITH_ACTIONS, fetch_prices

    if adjusted:
        # Same basis as the panel it will be spliced into: as-traded closes
        # carried forward on their own dividends, never Yahoo's back-anchored
        # adjusted close.
        return fetch_prices(tickers, start, end=end, batch=20, total_return=True)
    return fetch_prices(
        tickers, start, end=end, batch=20, auto_adjust=False, actions=True,
        columns=UNADJUSTED_WITH_ACTIONS,
    )


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
                             fetcher=None, targeted_primary_fetcher=None,
                             raw_primary_fetcher=None) -> dict:
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
    live_sources = fetcher is None
    fetcher = fetcher or _fdr_frame
    kr_sessions = RC.sessions(start, through, "KR")
    # A focused same-vendor retry is the highest-fidelity recovery: when it
    # succeeds it restores the exact observation that the large batch dropped.
    # The unadjusted retry is not substituted into valuation; it validates FDR
    # raw returns without confusing dividends with vendor disagreement.
    #
    # "Focused" has to mean it. One window spanning min(systemic)..max(systemic)
    # covered 2017-09-22 to 2025-09-19 on the first replay-v10 run — an
    # eight-year bulk download of the whole affected list, twice, which is the
    # same shape of request that dropped the rows in the first place. It
    # reported targetedYahooRetries: 0, so the designed first choice never once
    # succeeded. Each contiguous run of market-wide gap dates gets its own
    # window over only the names that are missing in it.
    clusters = _groups(kr_sessions, set(systemic))
    cluster_of = {date: index for index, dates in enumerate(clusters) for date in dates}
    targeted_by_cluster: list[dict] = []
    raw_by_cluster: list[dict] = []
    for dates in clusters:
        names = sorted(set().union(*(systemic[date] for date in dates)))
        window_start = str((dates[0] - pd.Timedelta(days=14)).date())
        window_end = str((dates[-1] + pd.Timedelta(days=14)).date())
        if targeted_primary_fetcher is None:
            targeted_by_cluster.append(_yahoo_targeted_frames(
                names, window_start, window_end, adjusted=True) if live_sources else {})
        else:
            targeted_by_cluster.append(
                targeted_primary_fetcher(names, window_start, window_end) or {})
        if raw_primary_fetcher is None:
            raw_by_cluster.append(_yahoo_targeted_frames(
                names, window_start, window_end, adjusted=False) if live_sources else {})
        else:
            raw_by_cluster.append(
                raw_primary_fetcher(names, window_start, window_end) or {})

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
        fallback = None
        fallback_fetched = False
        for group in _groups(kr_sessions, missing):
            # A contiguous run of this ticker's missing dates lies inside one
            # market-wide cluster, so it reads that cluster's narrow retry.
            index = cluster_of[group[0]]
            targeted = normalize_daily_frame(targeted_by_cluster[index][ticker]) \
                if ticker in targeted_by_cluster[index] else None
            raw = normalize_daily_frame(raw_by_cluster[index][ticker]) \
                if ticker in raw_by_cluster[index] else None
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
            if left not in primary.index or right not in primary.index:
                result["rejected"].append({"ticker":ticker,
                    "dates":[str(d.date()) for d in group], "reason":"NO_PRIMARY_BRIDGE"})
                continue
            p_left, p_right = float(primary.at[left,"Close"]), float(primary.at[right,"Close"])
            if not all(np.isfinite(value) and value > 0 for value in (p_left, p_right)):
                result["rejected"].append({"ticker":ticker,
                    "dates":[str(d.date()) for d in group], "reason":"NON_POSITIVE_BRIDGE"})
                continue

            # First choice: exact adjusted observations from a narrow retry of
            # the same source.  The anchors prove it is the same adjustment
            # vintage before it is joined to the primary panel.
            if (targeted is not None and "Close" in targeted
                    and all(date in targeted.index for date in needed)
                    and all(pd.notna(targeted.at[date, "Close"])
                            and np.isfinite(float(targeted.at[date, "Close"]))
                            and float(targeted.at[date, "Close"]) > 0 for date in needed)
                    and min(float(targeted.at[left, "Close"]),
                            float(targeted.at[right, "Close"])) > 0):
                t_left = float(targeted.at[left, "Close"])
                t_right = float(targeted.at[right, "Close"])
                retry_bridge_bps = abs((p_right/p_left)/(t_right/t_left)-1) * 10000
                if retry_bridge_bps <= KR_BRIDGE_TOLERANCE_BPS:
                    scale = p_left / t_left
                    columns = [column for column in ("Open","High","Low","Close","Volume")
                               if column in targeted.columns]
                    for date in group:
                        for column in columns:
                            value = targeted.at[date, column]
                            if pd.isna(value):
                                continue
                            primary.loc[date, column] = (float(value) if column == "Volume"
                                                        else float(value) * scale)
                    primary.sort_index(inplace=True)
                    result["accepted"].append({"ticker":ticker,
                        "date":str(group[0].date()),
                        "dates":[str(d.date()) for d in group],
                        "primaryVendor":"YAHOO_AS_TRADED_FORWARD_TOTAL_RETURN",
                        "fallbackVendor":"YAHOO_TARGETED_RETRY",
                        "method":"SAME_VENDOR_ADJUSTED_RETURN_BRIDGE",
                        "leftAnchor":str(left.date()), "rightAnchor":str(right.date()),
                        "bridgeDifferenceBps":float(retry_bridge_bps),
                        "scale":float(scale), "pathUncertaintyBps":0.0})
                    continue

            if not fallback_fetched:
                candidate = fetcher(
                    ticker, str((min(missing) - pd.Timedelta(days=14)).date()),
                    str((max(missing) + pd.Timedelta(days=14)).date()))
                fallback = (normalize_daily_frame(candidate)
                            if candidate is not None and "Close" in candidate else None)
                fallback_fetched = True
            if fallback is None:
                result["rejected"].append({"ticker":ticker,
                    "dates":[str(d.date()) for d in group], "reason":"FDR_NO_DATA"})
                continue
            if (any(date not in fallback.index for date in needed)
                    or any(pd.isna(fallback.at[date, "Close"])
                           or not np.isfinite(float(fallback.at[date, "Close"]))
                           or float(fallback.at[date, "Close"]) <= 0 for date in needed)):
                result["rejected"].append({"ticker":ticker,
                    "dates":[str(d.date()) for d in group],
                    "reason":"NO_PRIMARY_OR_FDR_BRIDGE"})
                continue
            f_left, f_right = float(fallback.at[left,"Close"]), float(fallback.at[right,"Close"])
            if not all(np.isfinite(value) and value > 0 for value in (f_left, f_right)):
                result["rejected"].append({"ticker":ticker,
                    "dates":[str(d.date()) for d in group], "reason":"NON_POSITIVE_BRIDGE"})
                continue
            adjusted_bridge_bps = abs((p_right/p_left)/(f_right/f_left)-1) * 10000

            if adjusted_bridge_bps <= KR_BRIDGE_TOLERANCE_BPS:
                scale = p_left / f_left
                columns = [column for column in ("Open","High","Low","Close","Volume")
                           if column in fallback.columns]
                for date in group:
                    for column in columns:
                        value = fallback.at[date,column]
                        if pd.isna(value):
                            continue
                        primary.loc[date,column] = (float(value) if column == "Volume"
                                                    else float(value) * scale)
                method = "FDR_RETURN_ANCHORED_TO_PREVIOUS_PRIMARY_CLOSE"
                raw_bridge_bps = None
                basis_shift_bps = 0.0
                path_uncertainty_bps = float(adjusted_bridge_bps)
            else:
                if (raw is None or "Close" not in raw
                        or left not in raw.index or right not in raw.index):
                    result["rejected"].append({"ticker":ticker,
                        "dates":[str(d.date()) for d in group],
                        "reason":"NO_UNADJUSTED_PRIMARY_BRIDGE",
                        "adjustedBridgeDifferenceBps":float(adjusted_bridge_bps)})
                    continue
                y_left, y_right = float(raw.at[left,"Close"]), float(raw.at[right,"Close"])
                if not all(np.isfinite(value) and value > 0 for value in (y_left, y_right)):
                    result["rejected"].append({"ticker":ticker,
                        "dates":[str(d.date()) for d in group],
                        "reason":"NON_POSITIVE_UNADJUSTED_BRIDGE"})
                    continue
                raw_bridge_bps = abs((y_right/y_left)/(f_right/f_left)-1) * 10000
                if raw_bridge_bps > KR_BRIDGE_TOLERANCE_BPS:
                    result["rejected"].append({"ticker":ticker,
                        "dates":[str(d.date()) for d in group],
                        "reason":"RAW_RETURN_BRIDGE_MISMATCH",
                        "adjustedBridgeDifferenceBps":float(adjusted_bridge_bps),
                        "rawBridgeDifferenceBps":float(raw_bridge_bps)})
                    continue
                left_factor, right_factor = p_left/y_left, p_right/y_right
                basis_shift_bps = abs(right_factor/left_factor-1) * 10000
                if basis_shift_bps > KR_MAX_UNVOUCHED_ADJUSTMENT_BPS:
                    result["rejected"].append({"ticker":ticker,
                        "dates":[str(d.date()) for d in group],
                        "reason":"UNVOUCHED_ADJUSTMENT_TOO_LARGE",
                        "adjustedBridgeDifferenceBps":float(adjusted_bridge_bps),
                        "rawBridgeDifferenceBps":float(raw_bridge_bps),
                        "adjustmentBasisShiftBps":float(basis_shift_bps)})
                    continue
                raw_scale = y_left/f_left
                # The two observed adjustment factors bound the unavailable
                # session's adjusted close.  For this long-only audit, retain
                # the lower bound rather than choose the value that flatters
                # the daily NAV.  Both bounds and their width are snapshotted.
                for date in group:
                    raw_value = float(fallback.at[date,"Close"])
                    left_bound = raw_value * raw_scale * left_factor
                    right_bound = raw_value * raw_scale * right_factor
                    primary.loc[date,"Close"] = min(left_bound, right_bound)
                scale = p_left/f_left
                method = "FDR_RAW_RETURN_WITH_OBSERVED_ADJUSTMENT_BOUNDS_LOWER_NAV"
                path_uncertainty_bps = float(basis_shift_bps)
            primary.sort_index(inplace=True)
            result["accepted"].append({"ticker":ticker,
                "date":str(group[0].date()), "dates":[str(d.date()) for d in group],
                "primaryVendor":"YAHOO_AS_TRADED_FORWARD_TOTAL_RETURN", "fallbackVendor":"FINANCE_DATA_READER",
                "method":method,
                "leftAnchor":str(left.date()), "rightAnchor":str(right.date()),
                "bridgeDifferenceBps":float(adjusted_bridge_bps),
                "rawBridgeDifferenceBps":(float(raw_bridge_bps)
                                           if raw_bridge_bps is not None else None),
                "adjustmentBasisShiftBps":float(basis_shift_bps),
                "pathUncertaintyBps":path_uncertainty_bps,
                "scale":float(scale)})
        prices[ticker] = primary
    return result
