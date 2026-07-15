"""Daily short-term trade-idea engine.

For each candidate it combines the calibrated UP-probability at the trade
horizon with the historical UP/DOWN move sizes to estimate an expected value,
then subtracts a round-trip cost hurdle. Only positive-edge, high-conviction,
non-bear ideas are proposed, each with an explicit hold-until date and an
invalidation rule. Ideas are ranked within each region (KR / US).

Why a cost hurdle and a conviction floor: short-horizon direction models sit
close to a coin flip, so a raw probability over 0.5 is not a tradeable edge.
The edge has to clear transaction costs (and, for short-term holds, tax) to be
worth acting on.

OOS quality metrics (lift, Brier skill, grade) ride along on every idea as a
badge — informational, not a hard gate — so the site can show how well the
model has actually predicted this ticker out-of-sample.
"""
from __future__ import annotations

import pandas as pd

# Round-trip cost hurdle as a fraction of price. Covers slippage on both legs
# plus a haircut for short-term tax/fees. KR short-term trading is taxed/fee'd
# more heavily, so its hurdle is higher.
COST_HURDLE = {"US": 0.004, "KR": 0.007}
CONVICTION_FLOOR = 0.55
MAX_POSITION_WEIGHT = 0.10  # cap any single idea at 10% of the book


def suggested_weight(prob_up: float, up_mean: float, down_mean: float) -> float | None:
    """Half-Kelly position size, capped.

    Full Kelly f* = p − (1−p)/b with b = avg win / avg loss maximizes log
    growth but assumes the probabilities are exact; since ours are model
    estimates, half-Kelly is the standard haircut. Returns a fraction of
    capital in [0, MAX_POSITION_WEIGHT], or None if move sizes are degenerate.
    """
    if up_mean <= 0 or down_mean >= 0:
        return None
    b = up_mean / abs(down_mean)
    kelly = prob_up - (1 - prob_up) / b
    half = kelly / 2
    return max(0.0, min(MAX_POSITION_WEIGHT, half))


def expected_value(prob_up: float, up_mean: float, down_mean: float) -> float:
    """Expected forward return (fraction) given UP probability and move sizes."""
    return prob_up * up_mean + (1 - prob_up) * down_mean


def _why(prob_up: float, regime: str, diag: dict | None, quality: dict | None) -> str:
    """A short, human rationale for proposing the idea."""
    parts = ["상승국면" if regime == "Bull" else "전환국면"]
    if diag:
        mom = diag.get("mom63")
        if mom is not None:
            parts.append(f"60일 모멘텀 {mom * 100:+.0f}%")
        rel = diag.get("relMomentum")
        if rel is not None and rel > 0:
            parts.append("벤치마크 우위")
        rsi = diag.get("rsi14")
        if rsi is not None and rsi > 70:
            parts.append(f"RSI {rsi:.0f} 과열주의")
    if quality and quality.get("eligible"):
        parts.append(f"OOS lift {quality.get('lift')}%p 검증")
    parts.append(f"상승확률 {prob_up * 100:.0f}%")
    return " · ".join(parts)


def build_idea(
    ticker: str,
    region: str,
    prob_up: float,
    stats: dict,
    horizon: int,
    last_date: str,
    regime: str,
    diag: dict | None = None,
    quality: dict | None = None,
) -> dict | None:
    quality = quality or {"eligible": False, "eligibilityReasons": ["quality_not_evaluated"], "qualityGrade": "REJECT"}
    ev = expected_value(prob_up, stats["upMean"], stats["downMean"])
    hurdle = COST_HURDLE.get(region, 0.004)
    ev_net = ev - hurdle

    qualifies = prob_up >= CONVICTION_FLOOR and ev_net > 0 and regime != "Bear"
    if not qualifies:
        return None

    hold_until = (pd.Timestamp(last_date) + pd.tseries.offsets.BDay(horizon)).strftime("%Y-%m-%d")
    weight = suggested_weight(prob_up, stats["upMean"], stats["downMean"])
    return {
        "ticker": ticker,
        "region": region,
        "modelScore": round(prob_up, 4),
        "probUp": round(prob_up, 4),
        "suggestedWeightPct": round(weight * 100, 1) if weight is not None else None,
        "expMovePct": round(ev * 100, 2),
        "estimatedNetEdgePct": round(ev_net * 100, 2),
        "sampleSize": stats.get("sampleSize"),
        "horizon": horizon,
        "entry": last_date,
        "holdUntil": hold_until,
        "regime": regime,
        "why": _why(prob_up, regime, diag, quality),
        "quality": quality,
        "invalidation": "종가가 MA20 하회하거나 다음 신호 확률이 0.5 미만이면 조기 청산",
    }


def rank_ideas(ideas: list[dict], per_region: int = 5) -> dict:
    """Group qualifying ideas by region: quality-validated first, then net edge."""
    out: dict[str, list[dict]] = {}
    for region in ("KR", "US"):
        regional = sorted(
            (i for i in ideas if i["region"] == region),
            key=lambda x: (bool((x.get("quality") or {}).get("eligible")), x.get("estimatedNetEdgePct") or -999),
            reverse=True,
        )
        out[region] = regional[:per_region]
    return out
