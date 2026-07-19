"""Walk-forward validation for the PRICE-BASED long-term sleeves only.

Momentum and low-volatility are computed from our own price history, so they
CAN be walk-forward tested — with the survivorship caveat stated up front
(today's constituents only). Value and quality use current-snapshot
fundamentals with no point-in-time history, so this module deliberately does
NOT produce a value/quality backtest: claiming one would be look-ahead.

At each monthly rebalance it ranks the cross-section by a price factor, then
measures the rank information coefficient (Spearman) against the forward
``horizon``-day return — the standard factor-efficacy metric.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

SURVIVORSHIP_CAVEAT = (
    "현재 상장 종목만 포함(생존편향) — 상장폐지·편출 종목 미반영으로 과거 성과가 과대평가될 수 있음. "
    "value/quality는 시점별 데이터가 없어 백테스트 대상에서 제외."
)


def _price_panel(prices: dict[str, pd.DataFrame]) -> pd.DataFrame:
    closes = {t: df["Close"] for t, df in prices.items() if "Close" in df}
    if not closes:
        return pd.DataFrame()
    return pd.DataFrame(closes).sort_index()


def _mom_12_1(panel: pd.DataFrame, i: int) -> pd.Series:
    if i < 252:
        return pd.Series(dtype=float)
    return panel.iloc[i - 21] / panel.iloc[i - 252] - 1


def _lowvol(panel: pd.DataFrame, i: int) -> pd.Series:
    if i < 252:
        return pd.Series(dtype=float)
    window = panel.iloc[i - 252:i].pct_change()
    return -window.std()


_FACTORS = {"momentum": _mom_12_1, "lowvol": _lowvol}


def walk_forward(prices: dict[str, pd.DataFrame], horizon: int = 63, step: int = 21,
                 factor: str = "momentum") -> dict:
    """Return rank-IC series and summary for one price factor."""
    panel = _price_panel(prices)
    fn = _FACTORS.get(factor)
    if panel.empty or fn is None or len(panel) < 252 + horizon + step:
        return {"factor": factor, "horizon": horizon, "n": 0, "meanRankIC": None,
                "caveat": SURVIVORSHIP_CAVEAT}
    ics = []
    for i in range(252, len(panel) - horizon, step):
        score = fn(panel, i).dropna()
        if len(score) < 5:
            continue
        fwd = (panel.iloc[i + horizon] / panel.iloc[i] - 1).reindex(score.index).dropna()
        common = score.index.intersection(fwd.index)
        if len(common) < 5:
            continue
        ic = score.loc[common].rank().corr(fwd.loc[common].rank())
        if pd.notna(ic):
            ics.append({"date": panel.index[i].strftime("%Y-%m-%d"), "rankIC": round(float(ic), 3),
                        "n": int(len(common))})
    if not ics:
        return {"factor": factor, "horizon": horizon, "n": 0, "meanRankIC": None,
                "caveat": SURVIVORSHIP_CAVEAT}
    arr = np.array([x["rankIC"] for x in ics])
    return {
        "factor": factor, "horizon": horizon, "n": len(ics),
        "meanRankIC": round(float(arr.mean()), 3),
        "hitRate": round(float((arr > 0).mean()), 3),
        "tStat": round(float(arr.mean() / (arr.std(ddof=1) / np.sqrt(len(arr)))), 2) if len(arr) > 1 and arr.std() > 0 else None,
        "series": ics[-24:],
        "caveat": SURVIVORSHIP_CAVEAT,
    }


def build(prices_by_region: dict[str, dict], horizon: int = 63) -> dict:
    out = {"horizon": horizon, "priceFactorsOnly": True, "caveat": SURVIVORSHIP_CAVEAT, "regions": {}}
    for region, prices in prices_by_region.items():
        out["regions"][region] = {
            factor: walk_forward(prices, horizon=horizon, factor=factor)
            for factor in _FACTORS
        }
    return out
