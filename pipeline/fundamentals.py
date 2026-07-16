"""Fundamental data feed (valuation / quality) via Yahoo Finance.

Pulls a compact set of fundamentals per ticker for the long-horizon factor
engine: valuation (trailing/forward P/E, P/B, FCF yield), quality (ROE,
margins, leverage) and growth (revenue/earnings). Fetches are threaded and
individually fault-tolerant — a missing ticker or field degrades that name's
factor coverage, never the build.

HONESTY NOTE: Yahoo serves CURRENT-snapshot fundamentals only. There is no
point-in-time history, so value/quality factor performance cannot be
backtested from this feed without look-ahead bias. The long-term engine
therefore leans on published academic factor evidence (Fama-French value,
Novy-Marx profitability, Jegadeesh-Titman momentum) rather than claiming an
in-house backtest for these sleeves. This is disclosed in the payload.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# Fields harvested from yfinance's info dict -> our compact names.
_FIELDS = {
    "trailingPE": "trailingPE",
    "forwardPE": "forwardPE",
    "priceToBook": "priceToBook",
    "returnOnEquity": "roe",
    "profitMargins": "profitMargin",
    "operatingMargins": "operatingMargin",
    "debtToEquity": "debtToEquity",
    "revenueGrowth": "revenueGrowth",
    "earningsGrowth": "earningsGrowth",
    "freeCashflow": "freeCashflow",
    "marketCap": "marketCap",
    "dividendYield": "dividendYield",
}

FETCH_BUDGET_SEC = 300  # hard wall-clock budget so fundamentals can never stall the build
_MAX_WORKERS = 6


def _clean(v):
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


def _fetch_one(ticker: str) -> dict | None:
    import yfinance as yf

    info = yf.Ticker(ticker).info or {}
    out = {ours: _clean(info.get(theirs)) for theirs, ours in _FIELDS.items()}
    if all(v is None for v in out.values()):
        return None
    # Derived: FCF yield = free cash flow / market cap (both same currency).
    fcf, mcap = out.get("freeCashflow"), out.get("marketCap")
    out["fcfYield"] = round(fcf / mcap, 4) if fcf and mcap and mcap > 0 else None
    # Derived: earnings yield = 1 / trailing P/E (guard nonsense P/Es).
    pe = out.get("trailingPE")
    out["earningsYield"] = round(1.0 / pe, 4) if pe and 0 < pe < 1000 else None
    out["bookYield"] = round(1.0 / out["priceToBook"], 4) if out.get("priceToBook") and out["priceToBook"] > 0 else None
    return out


def fetch_fundamentals(tickers: list[str]) -> dict[str, dict]:
    """Threaded snapshot fetch. Returns {ticker: fields} for whatever succeeded."""
    results: dict[str, dict] = {}
    deadline = time.time() + FETCH_BUDGET_SEC
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        futures = {pool.submit(_fetch_one, t): t for t in tickers}
        for fut in as_completed(futures, timeout=FETCH_BUDGET_SEC + 30):
            t = futures[fut]
            if time.time() > deadline:
                break
            try:
                row = fut.result(timeout=30)
                if row:
                    results[t] = row
            except Exception:
                continue
    return results
