#!/usr/bin/env python3
"""Fetch public market data and build a static JSON artifact for GitHub Pages."""
from __future__ import annotations

import csv
import json
import math
import statistics
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

SYMBOLS = {
    "QQQ": "https://stooq.com/q/d/l/?s=qqq.us&i=d",
    "SPY": "https://stooq.com/q/d/l/?s=spy.us&i=d",
}
OUT = Path("data/market-data.json")
STALE_OK = True


def fetch_csv(url: str) -> list[dict[str, str]]:
    with urllib.request.urlopen(url, timeout=30) as response:
        text = response.read().decode("utf-8")
    rows = list(csv.DictReader(text.splitlines()))
    return [row for row in rows if row.get("Close") and row["Close"] != "0"]


def sma(values: list[float], window: int) -> float | None:
    if len(values) < window:
        return None
    return sum(values[-window:]) / window


def pct(now: float, then: float) -> float:
    return (now / then - 1) * 100


def rsi(values: list[float], window: int = 14) -> float | None:
    if len(values) <= window:
        return None
    gains: list[float] = []
    losses: list[float] = []
    for previous, current in zip(values[-window - 1 : -1], values[-window:]):
        change = current - previous
        gains.append(max(change, 0))
        losses.append(abs(min(change, 0)))
    average_gain = sum(gains) / window
    average_loss = sum(losses) / window
    if average_loss == 0:
        return 100.0
    rs = average_gain / average_loss
    return 100 - (100 / (1 + rs))


def realized_vol(values: list[float], window: int = 21) -> float | None:
    if len(values) <= window:
        return None
    returns = [math.log(values[i] / values[i - 1]) for i in range(len(values) - window, len(values))]
    return statistics.stdev(returns) * math.sqrt(252) * 100 if len(returns) > 1 else None


def max_drawdown(values: list[float], window: int = 252) -> float | None:
    sample = values[-window:]
    if not sample:
        return None
    peak = sample[0]
    worst = 0.0
    for value in sample:
        peak = max(peak, value)
        worst = min(worst, value / peak - 1)
    return worst * 100


def round_or_none(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(value, digits)


def build() -> dict:
    series: dict[str, list[dict[str, str]]] = {symbol: fetch_csv(url) for symbol, url in SYMBOLS.items()}
    qqq = series["QQQ"]
    spy = series["SPY"]
    qqq_close = [float(row["Close"]) for row in qqq]
    spy_close = [float(row["Close"]) for row in spy]

    latest = qqq[-1]
    close = qqq_close[-1]
    sma50 = sma(qqq_close, 50)
    sma200 = sma(qqq_close, 200)
    returns = {days: pct(close, qqq_close[-days - 1]) for days in (21, 63, 126) if len(qqq_close) > days}
    qqq_63 = pct(qqq_close[-1], qqq_close[-64]) if len(qqq_close) > 63 else None
    spy_63 = pct(spy_close[-1], spy_close[-64]) if len(spy_close) > 63 else None
    relative_strength = None if qqq_63 is None or spy_63 is None else qqq_63 - spy_63
    vol = realized_vol(qqq_close)
    drawdown = max_drawdown(qqq_close)
    rsi14 = rsi(qqq_close)

    score = 50
    score += 15 if sma50 and close > sma50 else -10
    score += 20 if sma200 and close > sma200 else -20
    score += 10 if relative_strength and relative_strength > 0 else -8
    score += 8 if returns.get(63, 0) > 0 else -8
    score += 5 if rsi14 and 45 <= rsi14 <= 70 else -5
    score += 5 if vol and vol < 28 else -8
    score = max(0, min(100, score))

    if score >= 70:
        stance = "Constructive"
        action = "핵심 비중 유지, 단기 과열만 점검"
    elif score >= 45:
        stance = "Neutral"
        action = "분할 접근, 추가 확인 전 과도한 확신 금지"
    else:
        stance = "Defensive"
        action = "현금/헤지/비중 축소 조건 점검"

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "source": "Stooq daily CSV via scripts/fetch_market_data.py",
        "symbol": "QQQ",
        "latestDate": latest["Date"],
        "latestClose": round(close, 2),
        "composite": {"score": score, "stance": stance, "action": action},
        "metrics": {
            "sma50": round_or_none(sma50),
            "sma200": round_or_none(sma200),
            "rsi14": round_or_none(rsi14),
            "realizedVol21d": round_or_none(vol),
            "maxDrawdown252d": round_or_none(drawdown),
            "relativeStrength63d": round_or_none(relative_strength),
        },
        "returns": {f"{days}d": round(value, 2) for days, value in returns.items()},
        "signals": [
            {"horizon": "21D", "return": round_or_none(returns.get(21)), "view": "단기 리스크/반등 확인"},
            {"horizon": "63D", "return": round_or_none(returns.get(63)), "view": "중기 추세 판단"},
            {"horizon": "126D", "return": round_or_none(returns.get(126)), "view": "반기 국면 판단"},
        ],
        "riskFlags": [
            {"name": "SMA200", "active": bool(sma200 and close < sma200), "message": "장기 추세 하회"},
            {"name": "Volatility", "active": bool(vol and vol > 30), "message": "실현 변동성 확대"},
            {"name": "Relative Strength", "active": bool(relative_strength and relative_strength < 0), "message": "QQQ가 SPY 대비 약세"},
            {"name": "Drawdown", "active": bool(drawdown and drawdown < -15), "message": "최근 1년 낙폭 확대"},
        ],
    }


if __name__ == "__main__":
    try:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(build(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {OUT}")
    except Exception as exc:
        if STALE_OK and OUT.exists():
            print(f"warning: failed to refresh market data, keeping existing {OUT}: {exc}", file=sys.stderr)
            sys.exit(0)
        print(f"failed to fetch market data: {exc}", file=sys.stderr)
        sys.exit(1)
