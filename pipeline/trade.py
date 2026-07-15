"""Daily short-term trade-idea engine — institutional gate stack.

An idea must clear EVERY layer before it is published:

1. Validated edge   — the (ticker, horizon) model passed OOS quality gates
                      (grade A or B from pipeline.quality). Unvalidated
                      models appear in the screening table, never as picks.
2. Conviction       — calibrated & shrunk UP-probability ≥ 0.55. Probabilities
                      arrive from pipeline.model already Platt-calibrated,
                      shrunk toward the base rate, and clipped to [5%, 95%],
                      so a 100% reading is impossible by construction.
3. Positive net EV  — expected move (prob-weighted historical UP/DOWN moves)
                      must clear a region-specific round-trip cost hurdle.
4. Regime           — no fresh longs in a Bear regime.
5. Trend agreement  — price above its 50-day MA or positive 60-day momentum;
                      a directional model fighting the tape is a fade, not a
                      trade (trend-following overlay, AQR/two-sigma style).

Position sizing: half-Kelly scaled by validation grade (A full, B half),
then capped by a per-position volatility budget and a hard 10% ceiling —
fractional Kelly + vol targeting, the standard institutional combination.
"""
from __future__ import annotations

import pandas as pd

# Round-trip cost hurdle as a fraction of price. Covers slippage on both legs
# plus a haircut for short-term tax/fees. KR short-term trading is taxed/fee'd
# more heavily, so its hurdle is higher.
COST_HURDLE = {"US": 0.004, "KR": 0.007}
CONVICTION_FLOOR = 0.55
MAX_POSITION_WEIGHT = 0.10   # hard cap on any single idea
POSITION_RISK_BUDGET = 0.015  # per-position annualized-vol contribution cap
GRADE_KELLY_SCALE = {"A": 1.0, "B": 0.5}


def suggested_weight(prob_up: float, up_mean: float, down_mean: float,
                     quality_grade: str | None = None,
                     realized_vol_pct: float | None = None) -> float | None:
    """Grade-scaled half-Kelly with a volatility-budget cap.

    Full Kelly f* = p − (1−p)/b with b = avg win / avg loss maximizes log
    growth but assumes exact probabilities; half-Kelly is the standard
    haircut, and a grade-B (thinner evidence) edge gets half of that again.
    The final weight is additionally capped so the position contributes at
    most POSITION_RISK_BUDGET of annualized volatility to the book, and never
    exceeds MAX_POSITION_WEIGHT. Returns None if move sizes are degenerate.
    """
    if up_mean <= 0 or down_mean >= 0:
        return None
    b = up_mean / abs(down_mean)
    kelly = prob_up - (1 - prob_up) / b
    weight = (kelly / 2) * GRADE_KELLY_SCALE.get(quality_grade or "", 0.5)
    if realized_vol_pct and realized_vol_pct > 0:
        weight = min(weight, POSITION_RISK_BUDGET / (realized_vol_pct / 100.0))
    return max(0.0, min(MAX_POSITION_WEIGHT, weight))


def expected_value(prob_up: float, up_mean: float, down_mean: float) -> float:
    """Expected forward return (fraction) given UP probability and move sizes."""
    return prob_up * up_mean + (1 - prob_up) * down_mean


def _trend_confirms(diag: dict | None) -> bool:
    """Trend overlay: above the 50-day MA or positive 60-day momentum."""
    if not diag:
        return True  # no diagnostics — don't silently veto
    above_ma50 = diag.get("aboveMA50")
    mom = diag.get("mom63")
    checks = [c for c in (above_ma50, (mom > 0) if mom is not None else None) if c is not None]
    return any(checks) if checks else True


def _why(prob_up: float, regime: str, diag: dict | None, quality: dict | None) -> str:
    """A short, human rationale for proposing the idea."""
    parts = ["상승국면" if regime == "Bull" else "전환국면"]
    if quality:
        grade = quality.get("qualityGrade")
        if grade in ("A", "B"):
            parts.append(f"OOS 검증 {grade} (lift {quality.get('lift')}%p)")
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

    qualifies = (
        quality.get("eligible", False)
        and prob_up >= CONVICTION_FLOOR
        and ev_net > 0
        and regime != "Bear"
        and _trend_confirms(diag)
    )
    if not qualifies:
        return None

    hold_until = (pd.Timestamp(last_date) + pd.tseries.offsets.BDay(horizon)).strftime("%Y-%m-%d")
    weight = suggested_weight(prob_up, stats["upMean"], stats["downMean"],
                              quality.get("qualityGrade"), (diag or {}).get("realizedVol"))
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
    """Group qualifying ideas by region: grade A first, then net edge."""
    grade_rank = {"A": 2, "B": 1}
    out: dict[str, list[dict]] = {}
    for region in ("KR", "US"):
        regional = sorted(
            (i for i in ideas if i["region"] == region),
            key=lambda x: (grade_rank.get((x.get("quality") or {}).get("qualityGrade"), 0),
                           x.get("estimatedNetEdgePct") or -999),
            reverse=True,
        )
        out[region] = regional[:per_region]
    return out
