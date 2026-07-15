"""OOS quality gates and deployment safety checks."""
from __future__ import annotations

import math
import numpy as np
import pandas as pd

MIN_OOS_OBS = 252
MIN_SIGNAL_OBS = 30
MIN_LIFT = 0.05


def _wilson_lower(successes: int, n: int, z: float = 1.96) -> float:
    if n <= 0:
        return 0.0
    p = successes / n
    denom = 1 + z*z/n
    centre = p + z*z/(2*n)
    adj = z * math.sqrt((p*(1-p) + z*z/(4*n))/n)
    return (centre - adj) / denom


def calibration_error(y, p, bins: int = 10) -> float:
    y = np.asarray(y, dtype=float); p = np.asarray(p, dtype=float)
    if len(y) == 0:
        return float('nan')
    edges = np.linspace(0, 1, bins + 1)
    ece = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (p >= lo) & (p <= hi if hi == 1 else p < hi)
        if mask.any():
            ece += mask.mean() * abs(y[mask].mean() - p[mask].mean())
    return float(ece)


def evaluate_oos(res: pd.DataFrame, threshold: float = 0.5, min_oos: int = MIN_OOS_OBS,
                 min_signals: int = MIN_SIGNAL_OBS) -> dict:
    from sklearn.metrics import precision_score, recall_score, f1_score, brier_score_loss
    reasons = []
    if res is None or res.empty:
        return {"eligible": False, "eligibilityReasons": ["no_oos_results"], "qualityGrade": "REJECT"}
    y = res["actual"].astype(int)
    p = res["prob_cal"].astype(float).clip(0, 1)
    pred = (p >= threshold).astype(int)
    n = int(len(y)); signal_n = int(pred.sum()); baseline = float(y.mean())
    precision = float(precision_score(y, pred, zero_division=0))
    recall = float(recall_score(y, pred, zero_division=0))
    f1 = float(f1_score(y, pred, zero_division=0))
    brier = float(brier_score_loss(y, p))
    naive = float(brier_score_loss(y, np.repeat(baseline, n)))
    bss = 1 - (brier / naive) if naive > 0 else float("nan")
    lift = precision - baseline
    lower_lift = _wilson_lower(int(((pred == 1) & (y == 1)).sum()), signal_n) - baseline if signal_n else -baseline
    recent = res.tail(min(252, n))
    recent_y = recent["actual"].astype(int); recent_p = recent["prob_cal"].astype(float).clip(0, 1)
    recent_pred = (recent_p >= threshold).astype(int)
    recent_precision = float(precision_score(recent_y, recent_pred, zero_division=0)) if len(recent_y) else 0.0
    recent_lift = recent_precision - float(recent_y.mean()) if len(recent_y) else 0.0
    extreme_rate = float(((p <= 0.01) | (p >= 0.99)).mean())
    if n < min_oos: reasons.append(f"oos_observations_below_{min_oos}")
    if signal_n < min_signals: reasons.append(f"signal_observations_below_{min_signals}")
    if lift <= MIN_LIFT: reasons.append("precision_lift_not_above_5pp")
    if lower_lift <= 0: reasons.append("precision_lift_ci_lower_not_positive")
    if not (brier < naive): reasons.append("brier_not_better_than_base_rate")
    if not (bss > 0): reasons.append("brier_skill_score_not_positive")
    if recent_lift <= 0 or lift <= 0: reasons.append("recent_or_full_oos_direction_not_positive")
    if extreme_rate > 0.10: reasons.append("calibration_instability_extreme_probabilities")
    eligible = not reasons
    grade = "A" if eligible and lift >= 0.10 and bss >= 0.05 else ("B" if eligible else "REJECT")
    return {
        "days": n, "baseline": round(baseline, 4), "precision": round(precision, 4),
        "recall": round(recall, 4), "f1": round(f1, 4), "lift": round(lift * 100, 2),
        "liftCiLower": round(lower_lift * 100, 2), "brier": round(brier, 4),
        "naiveBrier": round(naive, 4), "brierSkillScore": round(bss, 4),
        "ece": round(calibration_error(y, p), 4), "signalCount": signal_n,
        "recentLift": round(recent_lift * 100, 2), "eligible": eligible,
        "eligibilityReasons": reasons, "qualityGrade": grade,
    }


def recommendations_blocked(payload: dict) -> tuple[bool, list[str]]:
    """Hard data-safety blockers only.

    OOS quality (eligible/grade) is a per-idea badge, not a global gate, so it
    never blocks here. Scattered per-ticker errors are tolerated; only a broad
    pipeline failure (>10% of the screened universe erroring) blocks.
    """
    m = payload.get("meta", {})
    reasons = []
    if payload.get("seed"): reasons.append("seed_data")
    if payload.get("stale"): reasons.append("stale_data")
    if m.get("modelsTrained", 0) == 0: reasons.append("models_trained_zero")
    if (m.get("coveragePct") or 0) < 95: reasons.append("coverage_below_95")
    if m.get("buildValidationFailed"): reasons.append("build_validation_failed")
    if m.get("syntheticData"): reasons.append("synthetic_data")
    n_errors = len(m.get("pipelineErrors") or [])
    universe = m.get("universeScreened") or 0
    if n_errors and n_errors > 0.10 * max(universe, 1):
        reasons.append("pipeline_errors_excessive")
    return bool(reasons), reasons
