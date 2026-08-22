"""Combining historical OOS evidence with prospective paper evidence.

The old behaviour was: no prospective history, therefore expected excess return
is exactly 0, therefore Kelly never activates, therefore wait a year. That is
not conservatism — 0 is itself a point estimate, and it is a strong one. It
asserts the model has no edge, which the historical ledger can test.

The replacement is a posterior. Two sources speak, each with a mean, a standard
error and a credibility weight, and they are combined by precision:

    precision_i = w_i / se_i^2
    mu_post     = sum(precision_i * mu_i) / (sum(precision_i) + precision_prior)

``precision_prior`` is a zero-mean prior of scale ``priorScalePct``. It does two
jobs at once: it shrinks a thin, noisy estimate toward "no edge", and it means a
source with an enormous standard error contributes almost nothing rather than
dragging the posterior around.

The weighting is self-adjusting and needs no schedule. Historical evidence
enters with weight ~0.6 and a standard error set by its effective sample size.
Prospective evidence enters at weight 1.0. On day one the prospective precision
is zero and the posterior is the discounted historical prior. As live dates
accumulate, prospective precision rises and its share of the posterior rises
with it — automatically, with no crossover date to hardcode.

Two asymmetries are deliberate and are enforced by tests:

* Prospective evidence that comes in *worse* than history cuts the Kelly
  fraction (``drift_report``).
* Prospective evidence that comes in worse never raises the expected return, and
  a missing prospective ledger never raises it either. Evidence can only move
  the estimate toward what was measured, and uncertainty only ever shrinks it
  toward zero.
"""
from __future__ import annotations

import math

import numpy as np

from .historical_calibration import PROSPECTIVE_WEIGHT, lookup_bucket

# Kelly activation ladder. Codes are for the artifact; the Korean labels are
# what a person reads. They describe *which evidence is carrying the estimate*,
# not how good the estimate is.
ACTIVATION_LADDER = (
    "NO_EVIDENCE",
    "HISTORICAL_PRIOR_ONLY",
    "HISTORICAL_OOS_SUPPORTED",
    "PROSPECTIVE_EARLY",
    "PROSPECTIVE_CONFIRMED",
    "ACTIVE_PAPER",
    "ACTIVE_VALIDATED",
)

ACTIVATION_KO = {
    "NO_EVIDENCE": "검증 근거 없음",
    "HISTORICAL_PRIOR_ONLY": "과거 OOS 근거 준비 중",
    "HISTORICAL_OOS_SUPPORTED": "과거 OOS 검증 활용 중",
    "PROSPECTIVE_EARLY": "실시간 검증 축적 중",
    "PROSPECTIVE_CONFIRMED": "실시간 검증 우세",
    "ACTIVE_PAPER": "Paper 운용 중",
    "ACTIVE_VALIDATED": "검증 완료",
}

ACTIVATION_EXPLAIN_KO = {
    "NO_EVIDENCE": "과거·실시간 어느 쪽에서도 기대수익을 추정할 근거가 없습니다.",
    "HISTORICAL_PRIOR_ONLY": "과거 재현 결과는 있으나 표본이 얇아 아직 비중에 반영하지 않습니다.",
    "HISTORICAL_OOS_SUPPORTED": "미래를 보지 않고 과거를 재현한 결과가 기대수익의 근거입니다. 실시간 검증은 아직 없습니다.",
    "PROSPECTIVE_EARLY": "실제 미래 데이터가 쌓이기 시작했고, 아직은 과거 근거의 비중이 큽니다.",
    "PROSPECTIVE_CONFIRMED": "실시간 검증 표본이 과거 근거보다 더 큰 비중을 차지합니다.",
    "ACTIVE_PAPER": "Paper 포트폴리오에 실제로 적용 중입니다.",
    "ACTIVE_VALIDATED": "실시간 검증 기준을 모두 통과했습니다.",
}

# Zero-mean prior scale, in return units (3% over the horizon). Chosen to be the
# same order as a plausible factor edge: large enough not to crush a real
# signal, small enough that a 12% estimate from four dates gets cut hard.
DEFAULT_PRIOR_SCALE = 0.03

# A prospective sample this much worse than history, with enough dates behind
# it, is treated as the model degrading rather than as noise.
DRIFT_TRIGGER_PCT = 3.0
DRIFT_MIN_EFFECTIVE_DATES = 12
DRIFT_MIN_KELLY_MULTIPLIER = 0.25


def _precision(weight: float, se: float | None, floor: float = 1e-6) -> float:
    """Credibility-scaled precision. No standard error means no vote."""
    if se is None or not math.isfinite(se) or se <= floor:
        return 0.0
    return float(weight) / float(se) ** 2


def combine(historical: dict | None, prospective: dict | None, *,
            prior_scale_pct: float = DEFAULT_PRIOR_SCALE * 100,
            historical_weight: float | None = None) -> dict:
    """Precision-weighted posterior over the two evidence classes.

    Both inputs use percent units and the shape
    ``{"expectedExcessReturnPct", "standardErrorPct", "effectiveDates", "weight"}``.
    Either may be ``None`` or empty.
    """
    prior_precision = 1.0 / max(float(prior_scale_pct), 1e-6) ** 2

    def unpack(source: dict | None, default_weight: float) -> tuple[float, float | None, int, float]:
        source = source or {}
        mean = source.get("expectedExcessReturnPct")
        se = source.get("standardErrorPct")
        dates = int(source.get("effectiveDates") or 0)
        weight = source.get("weight")
        weight = float(default_weight if weight is None else weight)
        if mean is None or dates <= 0:
            return 0.0, None, dates, weight
        return float(mean), (float(se) if se is not None else None), dates, weight

    h_mean, h_se, h_dates, h_weight = unpack(historical, 0.0)
    if historical_weight is not None:
        h_weight = float(historical_weight)
    p_mean, p_se, p_dates, p_weight = unpack(prospective, PROSPECTIVE_WEIGHT)

    h_precision = _precision(h_weight, h_se)
    p_precision = _precision(p_weight, p_se)
    total = h_precision + p_precision + prior_precision
    posterior = (h_precision * h_mean + p_precision * p_mean) / total if total else 0.0
    posterior_se = math.sqrt(1.0 / total) if total else None

    evidence_precision = h_precision + p_precision
    share_h = h_precision / evidence_precision if evidence_precision else 0.0
    share_p = p_precision / evidence_precision if evidence_precision else 0.0

    return {
        "historical": {
            "expectedExcessReturnPct": round(h_mean, 3) if h_dates else None,
            "standardErrorPct": round(h_se, 4) if h_se is not None else None,
            "effectiveDates": h_dates,
            "weight": round(h_weight, 4),
            "precision": round(h_precision, 6),
        },
        "prospective": {
            "expectedExcessReturnPct": round(p_mean, 3) if p_dates else None,
            "standardErrorPct": round(p_se, 4) if p_se is not None else None,
            "effectiveDates": p_dates,
            "weight": round(p_weight, 4),
            "precision": round(p_precision, 6),
        },
        "posterior": {
            "expectedExcessReturnPct": round(posterior, 3),
            "standardErrorPct": round(posterior_se, 4) if posterior_se is not None else None,
            "confidenceIntervalPct": ([round(posterior - 1.96 * posterior_se, 3),
                                       round(posterior + 1.96 * posterior_se, 3)]
                                      if posterior_se is not None else None),
            "historicalWeightPct": round(share_h * 100, 1),
            "prospectiveWeightPct": round(share_p * 100, 1),
            "shrinkToZeroPrecision": round(prior_precision, 6),
            "method": "INVERSE_VARIANCE_PRECISION_WEIGHTED_WITH_ZERO_MEAN_PRIOR",
        },
        "priorScalePct": round(float(prior_scale_pct), 3),
    }


def activation_status(*, historical: dict | None, prospective: dict | None,
                      min_effective_dates: int, gate_passed: bool = False,
                      live_validated: bool = False, mode: str = "shadow") -> dict:
    """Where on the ladder this estimate stands, and what it is waiting for."""
    h_dates = int((historical or {}).get("effectiveDates") or 0)
    p_dates = int((prospective or {}).get("effectiveDates") or 0)
    h_usable = h_dates >= min_effective_dates
    p_usable = p_dates >= min_effective_dates

    if live_validated:
        code = "ACTIVE_VALIDATED"
    elif gate_passed and mode == "active":
        code = "ACTIVE_PAPER"
    elif p_usable and p_dates >= h_dates:
        code = "PROSPECTIVE_CONFIRMED"
    elif p_dates > 0 and (p_usable or h_usable):
        code = "PROSPECTIVE_EARLY"
    elif h_usable:
        code = "HISTORICAL_OOS_SUPPORTED"
    elif h_dates > 0:
        code = "HISTORICAL_PRIOR_ONLY"
    else:
        code = "NO_EVIDENCE"

    waiting = []
    if not h_usable and h_dates > 0:
        waiting.append(f"historical_effective_dates_{h_dates}/{min_effective_dates}")
    if not p_usable:
        waiting.append(f"prospective_effective_dates_{p_dates}/{min_effective_dates}")
    if not gate_passed:
        waiting.append("prospective_activation_gate")
    return {
        "code": code,
        "labelKo": ACTIVATION_KO[code],
        "explainKo": ACTIVATION_EXPLAIN_KO[code],
        "ladder": list(ACTIVATION_LADDER),
        "ladderIndex": ACTIVATION_LADDER.index(code),
        "historicalEffectiveDates": h_dates,
        "prospectiveEffectiveDates": p_dates,
        "minEffectiveDates": int(min_effective_dates),
        "waitingOn": waiting,
    }


def drift_report(historical: dict | None, prospective: dict | None, *,
                 trigger_pct: float = DRIFT_TRIGGER_PCT,
                 min_effective_dates: int = DRIFT_MIN_EFFECTIVE_DATES) -> dict:
    """Is the live world reproducing the backtest?

    Only one direction acts. Prospective results *below* history shrink the
    Kelly fraction; prospective results above history change nothing. A backtest
    that outperforms live is the expected failure mode, and rewarding the
    reverse would turn a lucky quarter into leverage.
    """
    h_mean = (historical or {}).get("expectedExcessReturnPct")
    p_mean = (prospective or {}).get("expectedExcessReturnPct")
    p_dates = int((prospective or {}).get("effectiveDates") or 0)
    if h_mean is None or p_mean is None or p_dates <= 0:
        return {"status": "INSUFFICIENT_PROSPECTIVE_SAMPLE", "detected": False,
                "kellyMultiplier": 1.0,
                "historicalExcessPct": h_mean, "prospectiveExcessPct": p_mean,
                "differencePct": None, "prospectiveEffectiveDates": p_dates}

    difference = float(p_mean) - float(h_mean)
    detected = bool(difference <= -abs(trigger_pct) and p_dates >= min_effective_dates)
    multiplier = 1.0
    if detected:
        # Scale down in proportion to the size of the shortfall, floored so the
        # portfolio degrades rather than snapping to zero on one bad quarter.
        severity = min(1.0, abs(difference) / max(abs(float(h_mean)), abs(trigger_pct)))
        multiplier = round(max(DRIFT_MIN_KELLY_MULTIPLIER, 1.0 - severity), 4)
    return {
        "status": "DRIFT_DETECTED" if detected else "WITHIN_TOLERANCE",
        "detected": detected,
        "historicalExcessPct": round(float(h_mean), 3),
        "prospectiveExcessPct": round(float(p_mean), 3),
        "differencePct": round(difference, 3),
        "prospectiveEffectiveDates": p_dates,
        "triggerPct": float(trigger_pct),
        "kellyMultiplier": multiplier,
        "policyKo": ("실시간 성과가 과거 대비 크게 낮으면 Kelly 비중을 축소합니다. "
                      "반대로 실시간 성과가 나쁘다고 기대수익을 올리는 일은 없습니다."),
    }


def candidate_prior(calibration: dict | None, region: str,
                    alpha_percentile: float | None, *,
                    macro_regime: str | None = None,
                    entry_state: str | None = None) -> dict | None:
    """The historical prior for one live candidate, or None.

    Returns nothing rather than a zero when the bucket has no usable history —
    ``combine`` treats absence and "measured zero" differently, and so should
    every caller.
    """
    row = lookup_bucket(calibration, region, alpha_percentile)
    if not row or not row.get("usable"):
        return None
    # Imported lazily to keep the evidence-combination module independent from
    # the heavier replay calibration path during simple unit tests.
    from . import probability_calibration as probability_mod
    distribution = probability_mod.lookup_distribution(
        (calibration or {}).get("probabilityCalibration"), region,
        alpha_percentile, macro_regime=macro_regime, entry_state=entry_state)
    se = row.get("standardErrorPct")
    return {
        # The spread over the replay universe, not the level over the benchmark —
        # see historical_calibration. The level travels alongside it so the
        # decomposition stays visible instead of being silently discarded.
        "expectedExcessReturnPct": row.get("calibratedExpectedExcessReturnPct",
                                           row.get("shrunkExpectedExcessReturnPct")),
        "expectedReturnBasis": row.get("expectedReturnBasis",
                                       "ALPHA_SPREAD_VS_REPLAY_UNIVERSE"),
        "levelExcessReturnPct": row.get("levelExpectedExcessReturnPct"),
        "universeBaselineExcessPct": row.get("universeBaselineExcessPct"),
        "spreadVsUniversePct": row.get("spreadVsUniversePct"),
        "spreadTStat": row.get("spreadTStat"),
        "standardErrorPct": se,
        "effectiveDates": int(row.get("effectiveDates") or 0),
        "uniqueDates": int(row.get("uniqueSignalDates") or 0),
        "observations": int(row.get("observations") or 0),
        "weight": float(row.get("evidenceWeight") or 0.0),
        "weightDetail": row.get("evidenceWeightDetail"),
        "bucket": row.get("bucket"),
        "quality": ("HIGH" if (row.get("effectiveDates") or 0) >= 60
                     else "MEDIUM" if (row.get("effectiveDates") or 0) >= 30 else "LOW"),
        "positiveHitRatio": row.get("positiveHitRatio"),
        "mddPct": row.get("mddPct"),
        "cvar95Pct": row.get("cvar95Pct"),
        "probabilityDistribution": distribution,
        "evidenceClass": "HISTORICAL_OOS",
    }


def summarize_region(calibration: dict | None, prospective_by_region: dict | None,
                     *, min_effective_dates: int, prior_scale_pct: float,
                     gate_passed: bool = False, mode: str = "shadow") -> dict:
    """Portfolio-level evidence summary, one row per region.

    Uses the highest alpha bucket present in each region, because that is the
    bucket the concentrated portfolio actually holds from.
    """
    prospective_by_region = prospective_by_region or {}
    out: dict[str, dict] = {}
    for region, blob in ((calibration or {}).get("regions") or {}).items():
        usable = [r for r in blob.get("buckets", []) if r.get("usable")]
        top = max(usable, key=lambda r: float(r["bucket"].split("-")[0])) if usable else None
        historical = None
        if top:
            historical = {
                "expectedExcessReturnPct": top.get("calibratedExpectedExcessReturnPct"),
                "standardErrorPct": top.get("standardErrorPct"),
                "effectiveDates": top.get("effectiveDates"),
                "weight": top.get("evidenceWeight"),
                "bucket": top.get("bucket"),
                "expectedReturnBasis": top.get("expectedReturnBasis",
                                               "ALPHA_SPREAD_VS_REPLAY_UNIVERSE"),
                "levelExcessReturnPct": top.get("levelExpectedExcessReturnPct"),
                "universeBaselineExcessPct": top.get("universeBaselineExcessPct"),
                "spreadVsUniversePct": top.get("spreadVsUniversePct"),
                "spreadTStat": top.get("spreadTStat"),
                "quality": ("HIGH" if (top.get("effectiveDates") or 0) >= 60
                             else "MEDIUM" if (top.get("effectiveDates") or 0) >= 30 else "LOW"),
            }
        prospective = prospective_by_region.get(region)
        combined = combine(historical, prospective, prior_scale_pct=prior_scale_pct)
        ordering = blob.get("ordering") or {}
        out[region] = {
            **combined,
            "activation": activation_status(
                historical=historical, prospective=prospective,
                min_effective_dates=min_effective_dates,
                gate_passed=gate_passed, mode=mode),
            "drift": drift_report(historical, prospective),
            # Why this region does or does not contribute a historical prior.
            # Without it a region with a decade of clean replay and no ordering
            # power is indistinguishable from a region with no replay at all.
            "alphaAttribution": {
                "orderingEstablished": bool(ordering.get("established")),
                "orderingReason": ordering.get("reason"),
                "topMinusBottomPct": ordering.get("topMinusBottomPct"),
                "topMinusBottomTStat": ordering.get("topMinusBottomTStat"),
                "meanRankIC": ordering.get("meanRankIC"),
                "rankICTStat": ordering.get("rankICTStat"),
                "minTStat": ordering.get("minTStat"),
                "universeBaselineExcessPct": ((blob.get("universeBaseline") or {})
                                              .get("meanExcessPct")),
                "levelExcessReturnPct": (historical or {}).get("levelExcessReturnPct"),
                "spreadVsUniversePct": (historical or {}).get("spreadVsUniversePct"),
                "explainKo": (
                    "순위가 수익을 정렬했다는 증거가 확인되어 알파 스프레드를 기대수익으로 씁니다."
                    if ordering.get("established")
                    else "이 지역에서는 알파 순위가 수익을 정렬했다는 증거가 없어 과거 근거를 "
                         "기대수익으로 쓰지 않습니다. 벤치마크 대비 초과수익은 대부분 유니버스 "
                         "전체의 캐리이며 선정 모델의 성과가 아닙니다."),
            },
        }
    for region, prospective in prospective_by_region.items():
        if region in out:
            continue
        combined = combine(None, prospective, prior_scale_pct=prior_scale_pct)
        out[region] = {
            **combined,
            "activation": activation_status(
                historical=None, prospective=prospective,
                min_effective_dates=min_effective_dates,
                gate_passed=gate_passed, mode=mode),
            "drift": drift_report(None, prospective),
        }
    return out


def portfolio_drift(region_evidence: dict | None) -> dict:
    """Worst-case drift across regions — what the Kelly fraction listens to."""
    rows = [blob.get("drift") or {} for blob in (region_evidence or {}).values()]
    detected = [r for r in rows if r.get("detected")]
    multiplier = min([float(r.get("kellyMultiplier", 1.0)) for r in rows], default=1.0)
    worst = min(detected, key=lambda r: r.get("differencePct", 0.0), default=None)
    return {
        "detected": bool(detected),
        "kellyMultiplier": round(float(np.clip(multiplier, DRIFT_MIN_KELLY_MULTIPLIER, 1.0)), 4),
        "regionsAffected": sorted(
            region for region, blob in (region_evidence or {}).items()
            if (blob.get("drift") or {}).get("detected")),
        "worst": worst,
        "summaryKo": ("과거 대비 실시간 성과 저하가 감지되어 Kelly 비중을 축소합니다."
                       if detected else "과거·실시간 성과 괴리는 허용 범위입니다."),
    }
