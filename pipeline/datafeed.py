"""Market + macro data acquisition.

Prices come from Yahoo Finance via yfinance (no key required).
Macro series come from FRED via fredapi (requires FRED_API_KEY).

All network access happens here so the rest of the pipeline can be unit
tested with synthetic frames.
"""
from __future__ import annotations

import time

import pandas as pd

from . import pit_data
from .config import Config
from .market_dates import normalize_daily_frame, normalize_daily_series


OHLCV = ["Open", "High", "Low", "Close", "Volume"]


def download_retry(tickers, start: str, retries: int = 3, **kwargs) -> pd.DataFrame | None:
    """yf.download with exponential-backoff retries.

    Yahoo intermittently throttles CI runner IPs; an empty frame on a batch
    that should have data is treated as a transient failure and retried.
    """
    import yfinance as yf

    # A daily Yahoo bar is labelled with its exchange-local session date.  If
    # yfinance combines timezone-aware frames first, an Asian midnight can be
    # converted to the previous UTC date before our normalizer ever sees it.
    # Remove the timezone while each ticker still owns its local calendar.
    kwargs.setdefault("ignore_tz", True)
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
            sub = normalize_daily_frame(df[keep].dropna(how="all"))
            if len(sub):
                out[tk] = sub.copy()
        return
    for tk in chunk:
        if tk not in df.columns.get_level_values(0):
            continue
        sub = df[tk]
        keep = [c for c in OHLCV if c in sub.columns]
        sub = normalize_daily_frame(sub[keep].dropna(how="all"))
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


def fetch_regional_prices(universe: dict[str, list[str]],
                          start: str, batch: int = 40) -> dict[str, pd.DataFrame]:
    """Fetch the replay universe without mixing exchange calendars in one batch.

    A single multi-market ``yf.download`` frame has one shared index.  Once US
    and KR bars have been coerced onto that index, an exchange-local date can
    already be lost and later normalization cannot reconstruct it, so each
    region is downloaded independently.

    Benchmarks are deliberately NOT fetched here.  They need vendor redundancy,
    a plausibility check and a committed snapshot to fall back on — see
    ``pipeline.benchmark_source`` — and folding that into the universe fetch is
    what let a one-row vendor response pass for a decade of index history.
    """
    out: dict[str, pd.DataFrame] = {}
    for region, names in universe.items():
        tickers = list(dict.fromkeys(names))
        if not tickers:
            continue
        print(f"  fetching {region} universe: {len(tickers)} tickers ...")
        out.update(fetch_prices(tickers, start, batch=batch))
    return out


def fetch_vix(start: str) -> pd.Series | None:
    df = download_retry("^VIX", start=start)
    if df is None or len(df) == 0:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return normalize_daily_series(df["Close"].rename("VIX"))


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
    # Derived columns come from pit_data so the replay, which rebuilds them
    # from vintaged inputs, cannot drift from the definition used here.
    return pit_data.derive_macro_columns(pd.DataFrame(frame))


def fetch_macro_vintages(cfg: Config, names) -> dict[str, pd.DataFrame]:
    """ALFRED release history for the named FRED series.

    Only the replay needs this: today's build wants today's number, while a
    replay standing on 2015-03-02 wants the number that had been printed by
    then. Series are opt-in because the full release history is far heavier
    than the revised series, and a series nobody asked for stays REVISED_HISTORY
    rather than quietly claiming a vintage it has no evidence for.
    """
    wanted = [name for name in (names or []) if name in cfg.fred_series]
    if not cfg.has_fred or not wanted:
        return {}
    from fredapi import Fred

    fred = Fred(api_key=cfg.fred_api_key)
    out: dict[str, pd.DataFrame] = {}
    for name in wanted:
        series_id = cfg.fred_series[name]
        try:
            releases = fred.get_series_all_releases(series_id)
        except Exception as exc:  # pragma: no cover - network dependent
            print(f"  warning: ALFRED {series_id} vintages failed: {exc}")
            continue
        if releases is not None and len(releases):
            out[name] = releases
    return out
