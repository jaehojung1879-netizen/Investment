"""Sector rotation (RRG-style) and factor/style momentum.

Sector rotation: for each sector ETF we compute a relative-strength ratio vs
the region benchmark (distance of the RS line from its own 63-day mean) and a
relative-strength momentum (21-day change of the RS line), then classify each
sector into the four Relative-Rotation-Graph quadrants:

    주도 (Leading)    ratio > 0, momentum > 0
    약화 (Weakening)  ratio > 0, momentum < 0
    개선 (Improving)  ratio < 0, momentum > 0
    부진 (Lagging)    ratio < 0, momentum < 0

This is the simplified public formulation, not JdK's proprietary one, but it
answers the same question: where is money rotating to / away from.

Factor momentum: excess 1/3/6-month returns of style ETFs (momentum, value,
quality, low-vol, small caps) over SPY — which style of stock the market is
currently paying for.
"""
from __future__ import annotations

import pandas as pd

from .datafeed import download_retry

US_BENCH = "SPY"
US_SECTORS = [
    ("XLK", "기술"), ("XLC", "커뮤니케이션"), ("XLY", "경기소비재"), ("XLP", "필수소비재"),
    ("XLV", "헬스케어"), ("XLF", "금융"), ("XLI", "산업재"), ("XLE", "에너지"),
    ("XLB", "소재"), ("XLU", "유틸리티"), ("XLRE", "리츠"),
]
KR_BENCH = "069500.KS"  # KODEX 200
KR_SECTORS = [
    ("091160.KS", "반도체"), ("091170.KS", "은행"), ("102970.KS", "증권"),
    ("117460.KS", "에너지화학"), ("117680.KS", "철강"), ("117700.KS", "건설"),
    ("140710.KS", "운송"), ("244580.KS", "바이오"),
]
FACTORS = [
    ("MTUM", "모멘텀"), ("VLUE", "가치"), ("QUAL", "퀄리티"),
    ("USMV", "저변동"), ("IWM", "소형주"),
]

RS_MEAN_WINDOW = 63   # RS ratio: distance from the RS line's 3-month mean
RS_MOM_WINDOW = 21    # RS momentum: 1-month change of the RS line


def _quadrant(ratio: float, mom: float) -> str:
    if ratio >= 0:
        return "주도" if mom >= 0 else "약화"
    return "개선" if mom >= 0 else "부진"


def fetch_closes() -> dict[str, pd.Series]:
    symbols = list(dict.fromkeys(
        [t for t, _ in US_SECTORS + KR_SECTORS + FACTORS] + [US_BENCH, KR_BENCH]
    ))
    start = (pd.Timestamp.today() - pd.Timedelta(days=420)).strftime("%Y-%m-%d")
    df = download_retry(symbols, start=start, group_by="ticker")
    out: dict[str, pd.Series] = {}
    if df is None:
        return out
    for sym in symbols:
        try:
            if isinstance(df.columns, pd.MultiIndex):
                if sym not in df.columns.get_level_values(0):
                    continue
                s = df[sym]["Close"].dropna()
            else:
                s = df["Close"].dropna()
            if len(s) >= RS_MEAN_WINDOW + RS_MOM_WINDOW:
                out[sym] = s
        except Exception:
            continue
    return out


def _ret(close: pd.Series | None, days: int) -> float | None:
    if close is None:
        return None
    s = close.dropna()
    if len(s) <= days or s.iloc[-days - 1] == 0:
        return None
    return float((s.iloc[-1] / s.iloc[-days - 1] - 1) * 100)


def _sector_row(ticker: str, name: str, close: pd.Series, bench: pd.Series) -> dict | None:
    rs = (close / bench.reindex(close.index).ffill()).dropna()
    if len(rs) <= RS_MEAN_WINDOW + RS_MOM_WINDOW:
        return None
    mean = rs.rolling(RS_MEAN_WINDOW).mean().iloc[-1]
    prev = rs.iloc[-RS_MOM_WINDOW - 1]
    if not mean or not prev:
        return None
    ratio = float((rs.iloc[-1] / mean - 1) * 100)
    mom = float((rs.iloc[-1] / prev - 1) * 100)
    r1, r3 = _ret(close, 21), _ret(close, 63)
    return {
        "ticker": ticker, "name": name,
        "rsRatio": round(ratio, 2), "rsMom": round(mom, 2),
        "quadrant": _quadrant(ratio, mom),
        "ret1mPct": round(r1, 1) if r1 is not None else None,
        "ret3mPct": round(r3, 1) if r3 is not None else None,
    }


def _region(sectors: list[tuple[str, str]], bench_sym: str, closes: dict[str, pd.Series]) -> dict | None:
    bench = closes.get(bench_sym)
    if bench is None:
        return None
    rows = []
    for ticker, name in sectors:
        c = closes.get(ticker)
        if c is None:
            continue
        row = _sector_row(ticker, name, c, bench)
        if row:
            rows.append(row)
    if not rows:
        return None
    rows.sort(key=lambda r: r["rsRatio"], reverse=True)
    return {"benchmark": bench_sym, "sectors": rows}


def _factors(closes: dict[str, pd.Series]) -> list[dict]:
    bench = closes.get(US_BENCH)
    if bench is None:
        return []
    out = []
    for ticker, name in FACTORS:
        c = closes.get(ticker)
        if c is None:
            continue
        row = {"ticker": ticker, "name": name}
        ok = False
        for label, days in (("ex1mPct", 21), ("ex3mPct", 63), ("ex6mPct", 126)):
            r, b = _ret(c, days), _ret(bench, days)
            row[label] = round(r - b, 1) if (r is not None and b is not None) else None
            ok = ok or row[label] is not None
        if ok:
            out.append(row)
    out.sort(key=lambda r: (r.get("ex3mPct") is None, -(r.get("ex3mPct") or 0)))
    return out


def build(closes: dict[str, pd.Series] | None = None) -> dict | None:
    """Assemble rotation data. `closes` is injectable for tests/seed data."""
    if closes is None:
        closes = fetch_closes()
    if not closes:
        return None
    us = _region(US_SECTORS, US_BENCH, closes)
    kr = _region(KR_SECTORS, KR_BENCH, closes)
    factors = _factors(closes)
    if us is None and kr is None and not factors:
        return None
    as_of = None
    for s in closes.values():
        d = s.dropna().index[-1]
        as_of = d if as_of is None or d > as_of else as_of
    return {
        "asOf": as_of.strftime("%Y-%m-%d") if as_of is not None else None,
        "US": us,
        "KR": kr,
        "factors": factors,
    }
