"""Market + macro data acquisition.

Prices come from Yahoo Finance via yfinance (no key required).
Macro series come from FRED via fredapi (requires FRED_API_KEY).

All network access happens here so the rest of the pipeline can be unit
tested with synthetic frames.
"""
from __future__ import annotations

import pandas as pd

from .config import Config


def fetch_prices(tickers: list[str], start: str) -> dict[str, pd.DataFrame]:
    """Return {ticker: DataFrame[Open, High, Low, Close, Volume]} indexed by date."""
    import yfinance as yf

    out: dict[str, pd.DataFrame] = {}
    for ticker in tickers:
        df = yf.download(ticker, start=start, progress=False, auto_adjust=True)
        if df is None or len(df) == 0:
            print(f"  warning: no data for {ticker}")
            continue
        # Flatten possible MultiIndex columns (yfinance batch behaviour).
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        keep = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
        out[ticker] = df[keep].copy()
    return out


def fetch_vix(start: str) -> pd.Series | None:
    import yfinance as yf

    df = yf.download("^VIX", start=start, progress=False, auto_adjust=True)
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
