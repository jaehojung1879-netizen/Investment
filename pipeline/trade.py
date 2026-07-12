"""Paper-only trade idea gate.

Actionable recommendations remain disabled unless a ticker/horizon passes OOS
quality gates and portfolio state is supplied locally. Public artifacts must not
include Kelly sizing or private holdings.
"""
from __future__ import annotations

import pandas as pd

COST_HURDLE = {"US": 0.004, "KR": 0.007}
CONVICTION_FLOOR = 0.55
PAPER_ONLY = True


def suggested_weight(prob_up: float, up_mean: float, down_mean: float, portfolio_state: dict | None = None,
                     quality_grade: str | None = None) -> float | None:
    """Kelly sizing is disabled by default; no local portfolio means no weight."""
    if not portfolio_state or quality_grade != "A":
        return None
    return None


def expected_value(prob_up: float, up_mean: float, down_mean: float) -> float:
    return prob_up * up_mean + (1 - prob_up) * down_mean


def _why(score: float, regime: str, diag: dict | None, quality: dict | None) -> str:
    parts = ["모의 신호", "상승국면" if regime == "Bull" else "전환국면"]
    if diag:
        mom = diag.get("mom63")
        if mom is not None: parts.append(f"60일 모멘텀 {mom * 100:+.0f}%")
        rel = diag.get("relMomentum")
        if rel is not None and rel > 0: parts.append("벤치마크 우위")
    if quality:
        parts.append(f"OOS lift {quality.get('lift')}%p")
        parts.append(f"BSS {quality.get('brierSkillScore')}")
    parts.append(f"모델 점수 {score * 100:.0f}%")
    return " · ".join(parts)


def build_idea(ticker: str, region: str, prob_up: float, stats: dict, horizon: int, last_date: str,
               regime: str, diag: dict | None = None, quality: dict | None = None,
               portfolio_state: dict | None = None) -> dict | None:
    quality = quality or {"eligible": False, "eligibilityReasons": ["quality_not_evaluated"], "qualityGrade": "REJECT"}
    ev = expected_value(prob_up, stats["upMean"], stats["downMean"])
    hurdle = COST_HURDLE.get(region, 0.004)
    ev_net = ev - hurdle
    edge_ci_lower = ev_net - 0.05  # conservative placeholder until robust payoff CI is implemented
    qualifies = (not PAPER_ONLY) and quality.get("eligible") and prob_up >= CONVICTION_FLOOR and ev_net > 0 and edge_ci_lower > 0 and regime != "Bear"
    if not qualifies:
        return None
    hold_until = (pd.Timestamp(last_date) + pd.tseries.offsets.BDay(horizon)).strftime("%Y-%m-%d")
    weight = suggested_weight(prob_up, stats["upMean"], stats["downMean"], portfolio_state, quality.get("qualityGrade"))
    return {"ticker": ticker, "region": region, "modelScore": round(prob_up, 4), "probUp": None,
            "suggestedWeightPct": round(weight * 100, 1) if weight is not None else None,
            "estimatedNetEdgePct": round(ev_net * 100, 2), "confidenceInterval": [round(edge_ci_lower * 100, 2), None],
            "sampleSize": stats.get("sampleSize"), "estimationMethod": "historical prior only; paper gated",
            "horizon": horizon, "entry": last_date, "holdUntil": hold_until, "regime": regime,
            "why": _why(prob_up, regime, diag, quality), "quality": quality,
            "invalidation": "모의 신호 전용 — 실제 매매 금지"}


def rank_ideas(ideas: list[dict], per_region: int = 5) -> dict:
    out: dict[str, list[dict]] = {}
    for region in ("KR", "US"):
        regional = sorted((i for i in ideas if i["region"] == region), key=lambda x: x.get("estimatedNetEdgePct") or -999, reverse=True)
        out[region] = regional[:per_region]
    return out
