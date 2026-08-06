"""Global market indices for the dashboard.

Yahoo Finance remains the primary source, but a single vendor is not reliable
enough for a scheduled dashboard.  Korean indices are therefore cross-checked
against FinanceDataReader and supported global symbols fall back to Stooq.
The freshest valid series wins.

Each row carries a dated one-year history and an explicit freshness status.
That lets the frontend draw a real detail chart and lets deployment validation
stop an obviously stale critical index instead of silently publishing it.
"""
from __future__ import annotations

import io
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from .datafeed import download_retry

# ``fdr`` and ``stooq`` are independent fallbacks.  FinanceDataReader's KS11
# and KQ11 routes are especially important because Yahoo intermittently leaves
# Korea index rows stale on shared CI runner IPs.
SPEC = [
    {"symbol": "^GSPC", "name": "S&P 500", "region": "US", "fdr": None, "stooq": "^spx", "digits": 2, "critical": True},
    {"symbol": "^IXIC", "name": "나스닥 종합", "region": "US", "fdr": None, "stooq": "^ndq", "digits": 2},
    {"symbol": "^DJI", "name": "다우존스", "region": "US", "fdr": None, "stooq": "^dji", "digits": 2},
    {"symbol": "^SOX", "name": "필라델피아 반도체", "region": "US", "fdr": None, "stooq": None, "digits": 2},
    {"symbol": "^KS11", "name": "코스피", "region": "KR", "fdr": "KS11", "stooq": None, "digits": 2, "critical": True},
    {"symbol": "^KQ11", "name": "코스닥", "region": "KR", "fdr": "KQ11", "stooq": None, "digits": 2, "critical": True},
    {"symbol": "KRW=X", "name": "원/달러", "region": "FX", "fdr": None, "stooq": "usdkrw", "digits": 1},
    {"symbol": "^VIX", "name": "VIX", "region": "US", "fdr": None, "stooq": None, "digits": 2},
    {"symbol": "BTC-USD", "name": "비트코인", "region": "CRYPTO", "fdr": None, "stooq": "btcusd", "digits": 0},
    {"symbol": "GC=F", "name": "금 (선물)", "region": "CMDTY", "fdr": None, "stooq": "xauusd", "digits": 1},
    {"symbol": "DX-Y.NYB", "name": "달러인덱스", "region": "FX", "fdr": None, "stooq": None, "digits": 2},
]

SPARK_POINTS = 63  # ~3 months of trading days
HISTORY_POINTS = 260  # one trading year for the clickable detail view
SPARK_PERIOD = "3M"


def _clean_close(series: pd.Series | None) -> pd.Series | None:
    if series is None:
        return None
    out = pd.to_numeric(series, errors="coerce").dropna().sort_index()
    if out.empty:
        return None
    out.index = pd.to_datetime(out.index).tz_localize(None).normalize()
    return out[~out.index.duplicated(keep="last")]


def _yahoo_close(frame: pd.DataFrame | None, symbol: str) -> pd.Series | None:
    if frame is None or frame.empty:
        return None
    try:
        if isinstance(frame.columns, pd.MultiIndex):
            level0 = frame.columns.get_level_values(0)
            if symbol in level0:
                return _clean_close(frame[symbol]["Close"])
            if "Close" in level0:
                return _clean_close(frame["Close"][symbol])
        if "Close" in frame.columns:
            return _clean_close(frame["Close"])
    except Exception:
        return None
    return None


def _finance_datareader_close(symbol: str, start: str) -> pd.Series | None:
    """Independent Korea-index route used when Yahoo is late or unavailable."""
    try:
        import FinanceDataReader as fdr

        df = fdr.DataReader(symbol, start)
        if df is None or df.empty or "Close" not in df:
            return None
        return _clean_close(df["Close"])
    except Exception as exc:
        print(f"  warning: FinanceDataReader {symbol} failed: {exc}")
        return None


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
        return _clean_close(df["Close"])
    except Exception as exc:
        print(f"  warning: stooq {stooq_symbol} failed: {exc}")
        return None


def _pct(a: float, b: float) -> float | None:
    if b is None or b == 0:
        return None
    return round((a / b - 1) * 100, 2)


def _as_utc(now: datetime | pd.Timestamp | None = None) -> pd.Timestamp:
    ts = pd.Timestamp(now or datetime.now(timezone.utc))
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


def _expected_market_date(region: str, now: datetime | pd.Timestamp | None = None) -> pd.Timestamp:
    """Most recent session date that should be available at evaluation time.

    A short post-close buffer gives vendors time to publish final rows while
    still making the completed US session mandatory for the 07:10 KST build.
    Exchange holidays are intentionally tolerated by the status thresholds.
    """
    now_utc = _as_utc(now)
    if region == "KR":
        local = now_utc.tz_convert(ZoneInfo("Asia/Seoul"))
        after_close = (local.hour, local.minute) >= (17, 0)
    elif region == "US":
        local = now_utc.tz_convert(ZoneInfo("America/New_York"))
        # 07:10 KST is 17:10 ET in standard time and 18:10 ET in daylight
        # time.  Requiring the completed session from 16:45 ET prevents the
        # previous trading day from being presented as current at breakfast.
        after_close = (local.hour, local.minute) >= (16, 45)
    elif region == "CRYPTO":
        return now_utc.tz_convert(ZoneInfo("UTC")).tz_localize(None).normalize()
    else:
        local = now_utc.tz_convert(ZoneInfo("America/New_York"))
        after_close = (local.hour, local.minute) >= (16, 45)

    candidate = local.tz_localize(None).normalize()
    if not after_close:
        candidate -= pd.offsets.BDay(1)
    while candidate.weekday() >= 5:
        candidate -= pd.offsets.BDay(1)
    return candidate


def _freshness(observation_date, region: str, now=None) -> tuple[int, str, str]:
    obs = pd.Timestamp(observation_date).tz_localize(None).normalize()
    expected = _expected_market_date(region, now)
    if obs >= expected:
        lag = 0
    else:
        lag = len(pd.bdate_range(obs + pd.offsets.BDay(1), expected))
    if lag == 0:
        return lag, "CURRENT", "최신"
    if lag <= 2:
        return lag, "DELAYED", "업데이트 지연"
    return lag, "STALE", "오래됨"


def summarize_close(spec: dict, close: pd.Series, source: str, now=None) -> dict | None:
    """Stats, dated history, and freshness for one market series."""
    s = _clean_close(close)
    if s is None:
        return None
    if len(s) < 30:
        return None
    last = float(s.iloc[-1])
    prev = float(s.iloc[-2]) if len(s) >= 2 else None
    m1 = float(s.iloc[-22]) if len(s) >= 22 else None
    m3 = float(s.iloc[-SPARK_POINTS]) if len(s) >= SPARK_POINTS else None

    year = s.index[-1].year
    prior = s[s.index.year < year]
    ytd_base = float(prior.iloc[-1]) if len(prior) else float(s.iloc[0])

    hi52 = float(s.iloc[-252:].max())
    ma200 = float(s.iloc[-200:].mean()) if len(s) >= 200 else None

    spark = [round(float(v), 2) for v in s.iloc[-SPARK_POINTS:]]
    history = [
        {"date": pd.Timestamp(d).strftime("%Y-%m-%d"), "value": round(float(v), spec["digits"])}
        for d, v in s.iloc[-HISTORY_POINTS:].items()
    ]
    lag, freshness_status, freshness_label = _freshness(s.index[-1], spec["region"], now)
    return {
        "symbol": spec["symbol"],
        "name": spec["name"],
        "region": spec["region"],
        "digits": spec["digits"],
        "last": round(last, spec["digits"]),
        "chg1dPct": _pct(last, prev),
        "chg1mPct": _pct(last, m1),
        "chg3mPct": _pct(last, m3),
        "ytdPct": _pct(last, ytd_base),
        "from52wHighPct": _pct(last, hi52),
        "above200d": bool(last >= ma200) if ma200 is not None else None,
        "spark": spark,
        "sparkPeriod": SPARK_PERIOD,
        "sparkPoints": len(spark),
        "sparkStartDate": s.iloc[-SPARK_POINTS:].index[0].strftime("%Y-%m-%d"),
        "sparkEndDate": s.index[-1].strftime("%Y-%m-%d"),
        "history": history,
        "asOf": s.index[-1].strftime("%Y-%m-%d"),
        "source": source,
        "freshnessBdays": lag,
        "freshnessStatus": freshness_status,
        "freshnessLabelKo": freshness_label,
        "critical": bool(spec.get("critical")),
    }


def fetch(now=None) -> list[dict]:
    """Fetch all indices and choose the freshest independent source."""
    now_utc = _as_utc(now)
    start = (now_utc.tz_localize(None) - pd.Timedelta(days=560)).strftime("%Y-%m-%d")
    symbols = [x["symbol"] for x in SPEC]
    df = download_retry(symbols, start=start, group_by="ticker")

    out: list[dict] = []
    for spec in SPEC:
        candidates: list[tuple[str, pd.Series]] = []
        yahoo = _yahoo_close(df, spec["symbol"])
        if yahoo is not None:
            candidates.append(("Yahoo Finance", yahoo))

        # Always cross-check the two critical Korean indices.  For Stooq-backed
        # symbols, use the fallback only when Yahoo is absent or more than one
        # business day behind the expected session.
        if spec.get("fdr"):
            alt = _finance_datareader_close(spec["fdr"], start)
            if alt is not None:
                candidates.append(("FinanceDataReader", alt))
        yahoo_lag = _freshness(yahoo.index[-1], spec["region"], now_utc)[0] if yahoo is not None else 99
        if spec.get("stooq") and yahoo_lag > 0:
            alt = _stooq_close(spec["stooq"])
            if alt is not None:
                candidates.append(("Stooq", alt))

        if not candidates:
            print(f"  warning: index {spec['symbol']} unavailable from all sources")
            continue
        source, close = max(candidates, key=lambda item: (item[1].index[-1], len(item[1])))
        row = summarize_close(spec, close, source, now=now_utc)
        if row:
            row["sourcesChecked"] = [name for name, _ in candidates]
            row["fetchedAt"] = now_utc.isoformat()
            out.append(row)
    print(f"  indices: {len(out)}/{len(SPEC)} fetched")
    return out


def health(rows: list[dict]) -> dict:
    """Deployment/UI summary for the market tape."""
    by_symbol = {r.get("symbol"): r for r in rows}
    critical = [s["symbol"] for s in SPEC if s.get("critical")]
    missing_critical = [s for s in critical if s not in by_symbol]
    stale_critical = [
        s for s in critical
        if s in by_symbol and by_symbol[s].get("freshnessStatus") == "STALE"
    ]
    current = sum(r.get("freshnessStatus") == "CURRENT" for r in rows)
    delayed = sum(r.get("freshnessStatus") == "DELAYED" for r in rows)
    stale = sum(r.get("freshnessStatus") == "STALE" for r in rows)
    status = "STALE" if missing_critical or stale_critical else ("DELAYED" if delayed or stale else "CURRENT")
    return {
        "status": status,
        "requested": len(SPEC),
        "fetched": len(rows),
        "current": current,
        "delayed": delayed,
        "stale": stale,
        "criticalSymbols": critical,
        "missingCritical": missing_critical,
        "staleCritical": stale_critical,
        "asOf": max((r.get("asOf") for r in rows if r.get("asOf")), default=None),
    }
