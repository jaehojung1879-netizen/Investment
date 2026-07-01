"""Market + macro data acquisition.

Prices come from Yahoo Finance via yfinance (no key required).
Macro series come from FRED via fredapi (requires FRED_API_KEY).

All network access happens here so the rest of the pipeline can be unit
tested with synthetic frames.
"""
from __future__ import annotations

import time

import pandas as pd

from .config import Config


OHLCV = ["Open", "High", "Low", "Close", "Volume"]


def download_retry(tickers, start: str, retries: int = 3, **kwargs) -> pd.DataFrame | None:
    """yf.download with exponential-backoff retries.

    Yahoo intermittently throttles CI runner IPs; an empty frame on a batch
    that should have data is treated as a transient failure and retried.
    """
    import yfinance as yf

    delay = 2.0
    for attempt in range(retries):
        try:
            df = yf.download(
                tickers, start=start, progress=False, auto_adjust=True,
                threads=True, **kwargs,
            )
            if df is not None and len(df):
                return df
        except Exception as exc:
            label = tickers if isinstance(tickers, str) else f"{len(tickers)} tickers"
            print(f"  warning: download {label} attempt {attempt + 1} failed: {exc}")
        if attempt < retries - 1:
            time.sleep(delay)
            delay *= 2
    return None


def _extract(df: pd.DataFrame, chunk: list[str], out: dict[str, pd.DataFrame]) -> None:
    """Split a (possibly multi-ticker) download frame into per-ticker OHLCV."""
    if len(chunk) == 1:
        tk = chunk[0]
        if isinstance(df.columns, pd.MultiIndex):
            df = df.copy()
            df.columns = df.columns.get_level_values(-1)
        keep = [c for c in OHLCV if c in df.columns]
        if keep:
            sub = df[keep].dropna(how="all")
            if len(sub):
                out[tk] = sub.copy()
        return
    for tk in chunk:
        if tk not in df.columns.get_level_values(0):
            continue
        sub = df[tk]
        keep = [c for c in OHLCV if c in sub.columns]
        sub = sub[keep].dropna(how="all")
        if len(sub):
            out[tk] = sub.copy()


def fetch_prices(tickers: list[str], start: str, batch: int = 40) -> dict[str, pd.DataFrame]:
    """Return {ticker: DataFrame[Open, High, Low, Close, Volume]} indexed by date.

    Downloads in threaded batches (much faster for a large universe), retries
    transient batch failures, then makes one smaller-batch second pass over
    anything still missing so a single throttled batch can't silently drop 40
    names from the universe.
    """
    out: dict[str, pd.DataFrame] = {}
    for i in range(0, len(tickers), batch):
        chunk = tickers[i : i + batch]
        df = download_retry(chunk, start=start, group_by="ticker")
        if df is None or len(df) == 0:
            continue
        _extract(df, chunk, out)

    missing = [t for t in tickers if t not in out]
    if missing:
        print(f"  retrying {len(missing)} missing tickers in small batches ...")
        small = 10
        for i in range(0, len(missing), small):
            chunk = missing[i : i + small]
            df = download_retry(chunk, start=start, retries=2, group_by="ticker")
            if df is not None and len(df):
                _extract(df, chunk, out)
        missing = [t for t in tickers if t not in out]
    if missing:
        print(f"  warning: no data for {len(missing)} tickers (e.g. {missing[:5]})")
    return out


def fetch_vix(start: str) -> pd.Series | None:
    df = download_retry("^VIX", start=start)
    if df is None or len(df) == 0:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df["Close"].rename("VIX")


def fetch_macro(cfg: Config, start: str) -> pd.DataFrame | None:
    """Fetch FRED macro series. Returns None if no API key is configured."""
    if not cfg.has_fred or not cfg.fred_series:
        return None
    from fredapi import Fred

    fred = Fred(api_key=cfg.fred_api_key)
    frame: dict[str, pd.Series] = {}
    for name, series_id in cfg.fred_series.items():
        try:
            frame[name] = fred.get_series(series_id, observation_start=start)
        except Exception as exc:  # pragma: no cover - network dependent
            print(f"  warning: FRED {series_id} failed: {exc}")
    if not frame:
        return None
    macro = pd.DataFrame(frame)
    if "Treasury_10Y" in macro and "Treasury_2Y" in macro:
        macro["Yield_Curve"] = macro["Treasury_10Y"] - macro["Treasury_2Y"]
    return macro
