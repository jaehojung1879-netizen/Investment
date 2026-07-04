"""Global market indices for the dashboard tape (S&P 500, NASDAQ, KOSPI, ...).

Yahoo Finance is the primary source. Any symbol that still comes back empty
after retries is re-fetched from Stooq's public CSV endpoint, so the market
tape survives a Yahoo throttle on CI runners. Output is a compact list the
frontend renders directly: level, 1D/1M/YTD change, distance from the 52-week
high, trend position, and a 3-month sparkline.
"""
from __future__ import annotations

import io

import pandas as pd

from .datafeed import download_retry

# Stooq symbol is the fallback source id; None means Yahoo-only.
SPEC = [
    {"symbol": "^GSPC", "name": "S&P 500", "region": "US", "stooq": "^spx", "digits": 2},
    {"symbol": "^IXIC", "name": "나스닥 종합", "region": "US", "stooq": "^ndq", "digits": 2},
    {"symbol": "^DJI", "name": "다우존스", "region": "US", "stooq": "^dji", "digits": 2},
    {"symbol": "^SOX", "name": "필라델피아 반도체", "region": "US", "stooq": None, "digits": 2},
    {"symbol": "^KS11", "name": "코스피", "region": "KR", "stooq": None, "digits": 2},
    {"symbol": "^KQ11", "name": "코스닥", "region": "KR", "stooq": None, "digits": 2},
    {"symbol": "KRW=X", "name": "원/달러", "region": "FX", "stooq": "usdkrw", "digits": 1},
    {"symbol": "^VIX", "name": "VIX", "region": "US", "stooq": None, "digits": 2},
    {"symbol": "BTC-USD", "name": "비트코인", "region": "CRYPTO", "stooq": "btcusd", "digits": 0},
    {"symbol": "GC=F", "name": "금 (선물)", "region": "CMDTY", "stooq": "xauusd", "digits": 1},
    {"symbol": "DX-Y.NYB", "name": "달러인덱스", "region": "FX", "stooq": None, "digits": 2},
]

SPARK_POINTS = 63  # ~3 months of trading days


def _stooq_close(stooq_symbol: str) -> pd.Series | None:
    """Daily close history from Stooq's free CSV endpoint (no key needed)."""
    import requests

    try:
        r = requests.get(
            "https://stooq.com/q/d/l/",
            params={"s": stooq_symbol, "i": "d"},
            timeout=20,
        )
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text), parse_dates=["Date"], index_col="Date")
        s = df["Close"].dropna()
        return s if len(s) else None
    except Exception as exc:
        print(f"  warning: stooq {stooq_symbol} failed: {exc}")
        return None


def _pct(a: float, b: float) -> float | None:
    if b is None or b == 0:
        return None
    return round((a / b - 1) * 100, 2)


def summarize_close(spec: dict, close: pd.Series, source: str) -> dict | None:
    """Compact stats + sparkline for one index close series."""
    s = close.dropna().sort_index()
    if len(s) < 30:
        return None
    last = float(s.iloc[-1])
    prev = float(s.iloc[-2]) if len(s) >= 2 else None
    m1 = float(s.iloc[-22]) if len(s) >= 22 else None

    year = s.index[-1].year
    prior = s[s.index.year < year]
    ytd_base = float(prior.iloc[-1]) if len(prior) else float(s.iloc[0])

    hi52 = float(s.iloc[-252:].max())
    ma200 = float(s.iloc[-200:].mean()) if len(s) >= 200 else None

    spark = [round(float(v), 2) for v in s.iloc[-SPARK_POINTS:]]
    return {
        "symbol": spec["symbol"],
        "name": spec["name"],
        "region": spec["region"],
        "digits": spec["digits"],
        "last": round(last, spec["digits"]),
        "chg1dPct": _pct(last, prev),
        "chg1mPct": _pct(last, m1),
        "ytdPct": _pct(last, ytd_base),
        "from52wHighPct": _pct(last, hi52),
        "above200d": bool(last >= ma200) if ma200 is not None else None,
        "spark": spark,
        "asOf": s.index[-1].strftime("%Y-%m-%d"),
        "source": source,
    }


def fetch() -> list[dict]:
    """Fetch and summarize every index in SPEC. Never raises; failed symbols
    are simply omitted (the frontend hides what is missing)."""
    start = (pd.Timestamp.today() - pd.Timedelta(days=500)).strftime("%Y-%m-%d")
    symbols = [x["symbol"] for x in SPEC]
    df = download_retry(symbols, start=start, group_by="ticker")

    out: list[dict] = []
    for spec in SPEC:
        close = None
        if df is not None:
            try:
                if isinstance(df.columns, pd.MultiIndex):
                    if spec["symbol"] in df.columns.get_level_values(0):
                        close = df[spec["symbol"]]["Close"]
                elif "Close" in df.columns:
                    close = df["Close"]
            except Exception:
                close = None
        source = "Yahoo Finance"
        if (close is None or close.dropna().empty) and spec["stooq"]:
            close = _stooq_close(spec["stooq"])
            source = "Stooq"
        if close is None or close.dropna().empty:
            print(f"  warning: index {spec['symbol']} unavailable from all sources")
            continue
        row = summarize_close(spec, close, source)
        if row:
            out.append(row)
    print(f"  indices: {len(out)}/{len(SPEC)} fetched")
    return out
