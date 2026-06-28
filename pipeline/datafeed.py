"""Market + macro data acquisition.

Prices come from Yahoo Finance via yfinance (no key required).
Macro series come from FRED via fredapi (requires FRED_API_KEY).

All network access happens here so the rest of the pipeline can be unit
tested with synthetic frames.
"""
from __future__ import annotations

import pandas as pd

from .config import Config


OHLCV = ["Open", "High", "Low", "Close", "Volume"]


def fetch_prices(tickers: list[str], start: str, batch: int = 40) -> dict[str, pd.DataFrame]:
    """Return {ticker: DataFrame[Open, High, Low, Close, Volume]} indexed by date.

    Downloads in threaded batches (much faster for a large universe). Tickers
    with no data are skipped.
    """
    import yfinance as yf

    out: dict[str, pd.DataFrame] = {}
    for i in range(0, len(tickers), batch):
        chunk = tickers[i : i + batch]
        df = yf.download(
            chunk, start=start, progress=False, auto_adjust=True,
            group_by="ticker", threads=True,
        )
        if df is None or len(df) == 0:
            continue
        if len(chunk) == 1:
            tk = chunk[0]
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(-1)
            keep = [c for c in OHLCV if c in df.columns]
            if keep:
                out[tk] = df[keep].dropna(how="all").copy()
            continue
        for tk in chunk:
            if tk not in df.columns.get_level_values(0):
                continue
            sub = df[tk]
            keep = [c for c in OHLCV if c in sub.columns]
            sub = sub[keep].dropna(how="all")
            if len(sub):
                out[tk] = sub.copy()
    missing = [t for t in tickers if t not in out]
    if missing:
        print(f"  warning: no data for {len(missing)} tickers (e.g. {missing[:5]})")
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
