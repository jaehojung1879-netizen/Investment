"""Transparent (non-ML) regime + risk diagnosis per ticker.

These read the most recent engineered features so the site can show *why*
a name is risky, alongside the model's probability.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _last(series: pd.Series):
    s = series.dropna()
    return float(s.iloc[-1]) if len(s) else None


def _max_drawdown(close: pd.Series, window: int = 252) -> float | None:
    sample = close.dropna().iloc[-window:]
    if sample.empty:
        return None
    peak = sample.cummax()
    return float(((sample - peak) / peak).min() * 100)


def diagnose(ticker: str, data: pd.DataFrame) -> dict:
    """`data` is the feature frame for one ticker."""
    close = data["Close"]
    last_close = _last(close)
    ma50 = _last(data["ma50"]) if "ma50" in data else None
    ma200 = _last(data["ma200"]) if "ma200" in data else None
    vol_raw = _last(data["volatility_20d"]) if "volatility_20d" in data else None
    vol = vol_raw * 100 if vol_raw is not None else None  # fraction -> percent
    rsi = _last(data["rsi_14"]) if "rsi_14" in data else None
    rel_mom = _last(data["rel_momentum"]) if "rel_momentum" in data else None
    dd = _max_drawdown(close)
    pos_52w = _last(data["price_52w_high"]) if "price_52w_high" in data else None

    above_200 = last_close is not None and ma200 is not None and last_close > ma200
    golden = ma50 is not None and ma200 is not None and ma50 > ma200
    if above_200 and golden:
        regime = "Bull"
    elif (last_close is not None and ma200 is not None and last_close < ma200) and not golden:
        regime = "Bear"
    else:
        regime = "Transition"

    flags = []
    if last_close is not None and ma200 is not None and last_close < ma200:
        flags.append({"name": "SMA200", "active": True, "message": "장기 추세선(200일) 하회"})
    if vol is not None and vol > 30:
        flags.append({"name": "Volatility", "active": True, "message": f"실현 변동성 {vol:.0f}% (확대)"})
    if dd is not None and dd < -15:
        flags.append({"name": "Drawdown", "active": True, "message": f"최근 1년 낙폭 {dd:.0f}%"})
    if rel_mom is not None and rel_mom < 0:
        flags.append({"name": "Relative Strength", "active": True, "message": "벤치마크 대비 약세"})
    if rsi is not None and rsi > 75:
        flags.append({"name": "RSI", "active": True, "message": f"RSI {rsi:.0f} (단기 과열)"})

    return {
        "ticker": ticker,
        "regime": regime,
        "lastClose": round(last_close, 2) if last_close is not None else None,
        "ma50": round(ma50, 2) if ma50 is not None else None,
        "ma200": round(ma200, 2) if ma200 is not None else None,
        "realizedVol": round(vol, 1) if vol is not None else None,
        "rsi14": round(rsi, 1) if rsi is not None else None,
        "maxDrawdown252d": round(dd, 1) if dd is not None else None,
        "relMomentum": round(rel_mom * 100, 1) if rel_mom is not None else None,
        "pct52wHigh": round(pos_52w * 100, 1) if pos_52w is not None else None,
        "riskFlags": flags,
    }
