"""Long-horizon (6–12 month) cross-sectional multi-factor ranking — the
site's PRIMARY investment engine.

Instead of asking "will this stock be up in 10 days?" (a near coin flip), it
asks the question institutional quant equity actually answers: "within this
region's universe, which names look RELATIVELY best on factors with decades
of published evidence?" Ranking is cross-sectional, so it does not depend on
predicting market direction, is far less sensitive to multiple-testing and
regime drift than per-ticker ML, and the 6–12 month holding period amortizes
trading costs to noise.

Factor sleeves (region-relative, winsorized z-scores):
  momentum  12-1 month price momentum (Jegadeesh-Titman; skip the last month
            to avoid short-term reversal) blended with 6-month momentum
  value     earnings yield + book yield + FCF yield (Fama-French HML family)
  quality   ROE + operating/profit margins + low leverage + earnings growth
            (Novy-Marx profitability / QMJ family)
  lowvol    negative 252-day realized volatility (Ang et al. low-vol anomaly)

Composite = evidence-weighted blend, weights renormalized over the sleeves a
name actually has data for. Names below MA200 are flagged (trend filter) and
pushed down the pick list. Position weights within the pick list use inverse
volatility (risk-parity style), capped per name.

HONESTY: value/quality use CURRENT-snapshot fundamentals (no point-in-time
history exists on this feed), so those sleeves rest on published academic
evidence, not an in-house backtest. Momentum/low-vol are computed from our
own price history. The universe is today's constituents (survivorship bias:
affects backtests, not today's forward-looking ranks). All of this ships in
the payload's caveats.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

FACTOR_WEIGHTS = {"momentum": 0.30, "value": 0.25, "quality": 0.25, "lowvol": 0.20}
TOP_PICKS = 5          # published picks per region
TABLE_ROWS = 15        # extended ranking table per region
MAX_WEIGHT = 0.20      # per-name cap inside the long-term sleeve
MIN_HISTORY = 273      # 252d momentum + 21d skip

CAVEATS = [
    "value/quality는 현재 스냅샷 재무 데이터 기반 — 시점별(point-in-time) 이력이 없어 자체 백테스트 불가, 학술 팩터 근거(Fama-French, Novy-Marx 등)에 의존",
    "유니버스는 현재 상장 종목 기준(생존편향) — 과거 성과 재현 검증에는 영향, 오늘의 상대 순위 산출에는 영향 제한적",
    "팩터 프리미엄은 수년 단위로 부침 — 6~12개월 보유·분산·리밸런싱 전제",
    "투자 조언이 아닌 리서치 참고 자료",
]


def momentum_12_1(close: pd.Series) -> float | None:
    """12-month return excluding the most recent month (standard 12-1)."""
    s = close.dropna()
    if len(s) < MIN_HISTORY:
        return None
    return float(s.iloc[-21] / s.iloc[-252] - 1)


def momentum_6m(close: pd.Series) -> float | None:
    s = close.dropna()
    if len(s) < 126:
        return None
    return float(s.iloc[-1] / s.iloc[-126] - 1)


def realized_vol_252(close: pd.Series) -> float | None:
    r = close.dropna().pct_change().dropna()
    if len(r) < 60:
        return None
    return float(r.iloc[-252:].std() * np.sqrt(252))


def zscore(values: pd.Series, winsor: float = 2.5) -> pd.Series:
    """Cross-sectional z-score, winsorized so one outlier can't own a sleeve."""
    v = values.astype(float)
    mask = v.notna()
    if mask.sum() < 3:
        return pd.Series(np.nan, index=v.index)
    z = (v - v[mask].mean()) / (v[mask].std(ddof=0) or 1.0)
    return z.clip(-winsor, winsor)


def _sleeve(frames: list[pd.Series]) -> pd.Series:
    """Average the available z-scored inputs of one factor sleeve per name."""
    df = pd.concat(frames, axis=1)
    return df.mean(axis=1, skipna=True)


def _percentile(s: pd.Series) -> pd.Series:
    return s.rank(pct=True).mul(100).round(0)


def build_region(tickers: list[str], prices: dict, fundamentals: dict, diags: dict) -> pd.DataFrame | None:
    rows = {}
    for t in tickers:
        if t not in prices:
            continue
        close = prices[t]["Close"]
        f = fundamentals.get(t, {})
        rows[t] = {
            "mom121": momentum_12_1(close),
            "mom6": momentum_6m(close),
            "vol252": realized_vol_252(close),
            "earningsYield": f.get("earningsYield"),
            "bookYield": f.get("bookYield"),
            "fcfYield": f.get("fcfYield"),
            "roe": f.get("roe"),
            "opMargin": f.get("operatingMargin"),
            "profitMargin": f.get("profitMargin"),
            "debtToEquity": f.get("debtToEquity"),
            "earningsGrowth": f.get("earningsGrowth"),
        }
    if len(rows) < 5:
        return None
    # None -> NaN and force numeric dtype (all-missing columns stay object otherwise).
    df = pd.DataFrame.from_dict(rows, orient="index").astype(float)

    factors = pd.DataFrame(index=df.index)
    factors["momentum"] = _sleeve([zscore(df["mom121"]), zscore(df["mom6"])])
    factors["value"] = _sleeve([zscore(df["earningsYield"]), zscore(df["bookYield"]), zscore(df["fcfYield"])])
    factors["quality"] = _sleeve([
        zscore(df["roe"]), zscore(df["opMargin"]), zscore(df["profitMargin"]),
        zscore(-df["debtToEquity"]), zscore(df["earningsGrowth"]),
    ])
    factors["lowvol"] = zscore(-df["vol252"])

    # Composite: weights renormalized over the sleeves each name actually has.
    w = pd.Series(FACTOR_WEIGHTS)
    avail = factors.notna().astype(float)
    weight_sum = avail.mul(w, axis=1).sum(axis=1)
    composite = factors.fillna(0).mul(w, axis=1).sum(axis=1) / weight_sum.replace(0, np.nan)

    out = factors.copy()
    out["composite"] = composite
    out["vol252"] = df["vol252"]
    out["mom121"] = df["mom121"]
    out["aboveMA200"] = [bool((diags.get(t) or {}).get("aboveMA200")) for t in out.index]
    out["regime"] = [(diags.get(t) or {}).get("regime") for t in out.index]
    out["valueCoverage"] = factors["value"].notna()
    out = out.dropna(subset=["composite"])
    return out if len(out) >= 5 else None


def _weights(picks: pd.DataFrame) -> pd.Series:
    """Inverse-volatility weights inside the pick list, capped and normalized.

    Excess above the per-name cap is redistributed to uncapped names
    (iteratively), so the cap holds and weights still sum to 100%.
    """
    inv = 1.0 / picks["vol252"].clip(lower=0.05)
    inv = inv.fillna(inv.mean() if inv.notna().any() else 1.0)
    w = inv / inv.sum()
    for _ in range(6):
        over = w > MAX_WEIGHT
        if not over.any():
            break
        excess = float((w[over] - MAX_WEIGHT).sum())
        w[over] = MAX_WEIGHT
        under = ~over
        under_sum = float(w[under].sum())
        if not under.any() or under_sum <= 0:
            break
        w[under] += excess * w[under] / under_sum
    return w.round(3)


def build(universe: dict[str, list[str]], prices: dict, fundamentals: dict, diags: dict) -> dict | None:
    regions = {}
    for region, tickers in universe.items():
        table = build_region(tickers, prices, fundamentals, diags)
        if table is None:
            continue
        pct = table[["momentum", "value", "quality", "lowvol", "composite"]].apply(_percentile)

        # Trend-confirmed names first, then composite. Below-MA200 names can
        # still rank (value often lives there) but never above confirmed ones.
        order = table.sort_values(["aboveMA200", "composite"], ascending=[False, False])
        picks = order.head(TOP_PICKS)
        weights = _weights(picks)

        def _row(t):
            return {
                "ticker": t,
                "region": region,
                "composite": round(float(table.loc[t, "composite"]), 2),
                "percentile": int(pct.loc[t, "composite"]) if pd.notna(pct.loc[t, "composite"]) else None,
                "factors": {
                    k: (int(pct.loc[t, k]) if pd.notna(pct.loc[t, k]) else None)
                    for k in ("momentum", "value", "quality", "lowvol")
                },
                "mom12_1Pct": round(float(table.loc[t, "mom121"]) * 100, 1) if pd.notna(table.loc[t, "mom121"]) else None,
                "vol252Pct": round(float(table.loc[t, "vol252"]) * 100, 1) if pd.notna(table.loc[t, "vol252"]) else None,
                "aboveMA200": bool(table.loc[t, "aboveMA200"]),
                "regime": table.loc[t, "regime"],
                "valueDataAvailable": bool(table.loc[t, "valueCoverage"]),
            }

        regions[region] = {
            "picks": [dict(_row(t), weightPct=round(float(weights[t]) * 100, 1)) for t in picks.index],
            "table": [_row(t) for t in order.head(TABLE_ROWS).index],
            "universeRanked": int(len(table)),
        }
    if not regions:
        return None
    covered = sum(1 for t in fundamentals if fundamentals[t])
    requested = sum(len(v) for v in universe.values())
    return {
        "horizonMonths": [6, 12],
        "rebalance": "분기(3개월) 리밸런싱 권장",
        "factorWeights": FACTOR_WEIGHTS,
        "fundamentalsCoverage": round(100 * covered / requested, 1) if requested else 0.0,
        "regions": regions,
        "caveats": CAVEATS,
    }
