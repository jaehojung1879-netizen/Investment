"""Turning a rank into a number: alpha percentile -> expected excess return.

``alpha``, ``rawAlpha`` and ``alphaPercentile`` are cross-sectional *ranks*. They
have never been expected returns and this module does not change that. What it
does is ask the historical out-of-sample ledger an empirical question:

    When this model, run without seeing the future, put a name in the 90-95th
    alpha percentile in Korea, what did that name actually do against KOSPI 200
    over the next 126 sessions?

The answer is a measured distribution, not a transformation of the score. If the
ledger has no answer for a bucket, the bucket has no expected return — it is not
interpolated from the score.

FOUR THINGS THAT WOULD MAKE THAT NUMBER A LIE, AND WHAT IS DONE ABOUT THEM
--------------------------------------------------------------------------
*Hundreds of names on one day are not hundreds of independent facts.* Every
date's cross-section collapses to a single observation before anything is
averaged (``kelly_portfolio._clustered_date_returns``).

*Overlapping 126-day windows are autocorrelated.* Daily-sampled forward returns
behave like an MA(h-1) process, so the standard error uses a Bartlett-kernel
Newey-West estimator with lag = horizon-1, and the resulting effective sample
size — not the row count — drives shrinkage.

*A thin bucket will show a spectacular mean by luck.* Estimates shrink toward
zero as ``eff / (eff + prior_strength)``, so a 3-date bucket contributes almost
nothing regardless of how good it looks.

*Buckets can come out non-monotone by noise.* Weighted isotonic regression
repairs the ordering rather than shipping a calibration that says the 80-90th
percentile beats the 95-100th.

And the whole result is then discounted, because backtest evidence is not live
evidence — see ``evidence_weight``.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import kelly_portfolio as KP
from . import pit_data
from .historical_outcomes import horizon_frame

DEFAULT_BUCKETS = (0, 60, 80, 90, 95, 100)

# Why 0.6 and not 1.0, and not 0.
#
# A historical replay is genuinely out-of-sample in time: on 2019-05-15 the
# engine could not see 2019-05-16. That is worth a great deal and is why the
# weight is not near zero.
#
# But it is not worth as much as prospective paper evidence, for a reason no
# amount of care inside the replay can fix: the *model specification itself* was
# chosen by people who already lived through 2019. Factor choice, sleeve
# weights, the entry-state ladder and the risk metrics were all authored with
# hindsight about which decade happened. Prospective evidence is the only kind
# free of that, so it anchors at 1.0 and history anchors below it.
#
# 0.6 sits mid-range in the 0.5-0.8 band: high enough that a decade of clean OOS
# history dominates an empty prospective ledger (which is the entire point of
# this work), low enough that a year of real prospective evidence can overtake
# it. Every known defect then multiplies it further down.
HISTORICAL_BASE_WEIGHT = 0.6
PROSPECTIVE_WEIGHT = 1.0
MIN_HISTORICAL_WEIGHT = 0.15

# Discount factors applied multiplicatively. Each is a named, checkable defect.
PENALTY = {
    "survivorship_unresolved": 0.80,
    "macro_revised_history": 0.95,
    "fundamentals_not_point_in_time": 0.90,
    "regime_concentration": 0.85,
    "sector_concentration": 0.90,
    "fold_instability": 0.70,
    "low_pit_coverage": 0.75,
}


def _bucket_label(lo, hi) -> str:
    return f"{lo:g}-{hi:g}"


def _summary_stats(values: pd.Series, horizon: int) -> dict:
    """Median and hit ratio over all dates; drawdown and CVaR over a
    non-overlapping subsample.

    Daily- or weekly-sampled 126-day forward returns overlap heavily. Averaging
    them is fine — overlap inflates the variance of the estimate, not the
    estimate. Chaining them into an equity curve is not fine: the same market
    move gets compounded dozens of times and the resulting drawdown is an
    artifact of the sampling, not of the strategy.
    """
    if not len(values):
        return {"median": None, "hitRatio": None, "mdd": None, "cvar95": None,
                "nonOverlappingDates": 0}
    arr = values.to_numpy(dtype=float)
    thinned: list[float] = []
    chosen: list[pd.Timestamp] = []
    for stamp, value in values.items():
        if not chosen or stamp >= chosen[-1] + pd.offsets.BDay(horizon):
            chosen.append(stamp)
            thinned.append(float(value))
    mdd = cvar = None
    if len(thinned) >= 3:
        block = np.asarray(thinned, dtype=float)
        equity = np.cumprod(1.0 + block)
        drawdown = equity / np.maximum.accumulate(equity) - 1.0
        tail_n = max(1, int(math.ceil(len(block) * 0.05)))
        mdd = round(float(np.min(drawdown)), 6)
        cvar = round(float(np.mean(np.sort(block)[:tail_n])), 6)
    return {
        "median": round(float(np.median(arr)), 6),
        "hitRatio": round(float(np.mean(arr > 0)), 4),
        "mdd": mdd,
        "cvar95": cvar,
        "nonOverlappingDates": len(thinned),
    }


def _fold_stability(frame: pd.DataFrame, folds: int = 4) -> dict:
    """Does the bucket's edge survive being cut into time slices?

    An edge concentrated in one lucky window is a different animal from one that
    shows up in every slice, even if both have the same full-sample mean. Sign
    agreement across slices is the cheapest honest test of that.
    """
    dates = sorted(frame["date"].unique())
    if len(dates) < folds * 2:
        return {"folds": 0, "signAgreement": None, "stable": None, "sliceMeans": []}
    chunks = np.array_split(np.array(dates), folds)
    means = []
    for chunk in chunks:
        subset = frame[frame["date"].isin(set(chunk))]
        if subset.empty:
            continue
        means.append(float(subset.groupby("date")["value"].mean().mean()))
    if not means:
        return {"folds": 0, "signAgreement": None, "stable": None, "sliceMeans": []}
    overall = float(np.mean(means))
    agree = float(np.mean([np.sign(m) == np.sign(overall) for m in means])) if overall else 0.0
    return {
        "folds": len(means),
        "signAgreement": round(agree, 3),
        "stable": bool(agree >= 0.75),
        "sliceMeans": [round(m, 6) for m in means],
    }


def _concentration(frame: pd.DataFrame, column: str) -> float | None:
    if column not in frame or frame[column].isna().all():
        return None
    counts = frame[column].fillna("UNKNOWN").value_counts(normalize=True)
    return float(counts.iloc[0]) if len(counts) else None


def evidence_weight(*, pit_coverage: float | None, survivorship_risk: str,
                    macro_pit_status: str, fundamentals_pit: bool,
                    regime_share: float | None, sector_share: float | None,
                    fold_stable: bool | None, effective_dates: int,
                    min_effective_dates: int) -> dict:
    """How much a historical bucket's estimate is allowed to count.

    Starts at ``HISTORICAL_BASE_WEIGHT`` and multiplies down for each defect
    that is actually present. The applied penalties are returned alongside the
    number so the dashboard can show *why* history is being discounted rather
    than presenting a bare coefficient.
    """
    weight = HISTORICAL_BASE_WEIGHT
    applied: list[str] = []

    coverage = float(pit_coverage or 0.0)
    if coverage < pit_data.MIN_CALIBRATION_COVERAGE:
        weight *= PENALTY["low_pit_coverage"]
        applied.append("low_pit_coverage")
    else:
        # Partial credit between the floor and full coverage.
        weight *= min(1.0, 0.85 + 0.15 * coverage)

    if survivorship_risk not in {"LOW"}:
        weight *= PENALTY["survivorship_unresolved"]
        applied.append("survivorship_unresolved")
    if macro_pit_status == pit_data.REVISED_HISTORY:
        weight *= PENALTY["macro_revised_history"]
        applied.append("macro_revised_history")
    if not fundamentals_pit:
        weight *= PENALTY["fundamentals_not_point_in_time"]
        applied.append("fundamentals_not_point_in_time")
    if regime_share is not None and regime_share > 0.6:
        weight *= PENALTY["regime_concentration"]
        applied.append("regime_concentration")
    if sector_share is not None and sector_share > 0.5:
        weight *= PENALTY["sector_concentration"]
        applied.append("sector_concentration")
    if fold_stable is False:
        weight *= PENALTY["fold_instability"]
        applied.append("fold_instability")

    # Small samples are already shrunk toward zero in the estimate itself; the
    # weight penalty here is about how much the *estimate* should move Kelly.
    if effective_dates < min_effective_dates:
        weight *= max(0.3, effective_dates / max(min_effective_dates, 1))
        applied.append("small_effective_sample")

    return {
        "weight": round(max(MIN_HISTORICAL_WEIGHT, min(HISTORICAL_BASE_WEIGHT, weight)), 4),
        "baseWeight": HISTORICAL_BASE_WEIGHT,
        "penaltiesApplied": applied,
        "rationaleKo": ("과거 OOS는 시점상 진짜 out-of-sample이지만 모델 설계 자체가 그 시기를 "
                        "겪은 뒤에 만들어졌으므로 실시간 증거보다 낮은 가중치를 부여합니다."),
    }


def calibrate(outcomes: list[dict], *, horizon: int = 126,
              buckets=DEFAULT_BUCKETS, cfg: dict | None = None,
              diagnostics: dict | None = None,
              cost_adjusted: bool = True,
              require_pit: bool = True) -> dict:
    """Region x alpha-bucket calibration from historical OOS outcomes."""
    cfg = cfg or {}
    diagnostics = diagnostics or {}
    edges = [float(x) for x in buckets]
    min_eff = int(cfg.get("minEffectiveDates", 30))
    prior_strength = float(cfg.get("shrinkagePriorStrength", min_eff))

    frame = horizon_frame(outcomes, horizon, cost_adjusted=False)
    excluded_low_pit = 0
    if require_pit and len(frame):
        before = len(frame)
        frame = frame[frame["usableForCalibration"]]
        excluded_low_pit = before - len(frame)
    if not len(frame):
        return {
            "horizonDays": horizon, "available": False,
            "reason": "no_matured_historical_outcomes_with_sufficient_pit_quality",
            "excludedLowPitObservations": excluded_low_pit,
            "regions": {}, "buckets": list(edges),
        }

    frame = frame.copy()
    frame["bucket"] = [
        _bucket_label(*b) if (b := KP._bucket(v, edges)) else None
        for v in frame["alphaPercentile"]
    ]
    frame = frame.dropna(subset=["bucket"])

    survivorship = diagnostics.get("survivorshipRisk", "HIGH")
    macro_status = diagnostics.get("macroPitStatus", pit_data.REVISED_HISTORY)
    fundamentals_pit = bool(diagnostics.get("fundamentalsPit"))

    regions: dict[str, dict] = {}
    for region in sorted(frame["region"].unique()):
        region_frame = frame[frame["region"] == region]
        rows: list[dict] = []
        for bucket in sorted(region_frame["bucket"].unique(), key=lambda b: float(b.split("-")[0])):
            subset = region_frame[region_frame["bucket"] == bucket]
            if subset.empty:
                continue
            gross = subset.groupby("date")["excessReturn"].mean().dropna().sort_index()
            net = subset.groupby("date")["costAdjustedExcessReturn"].mean().dropna().sort_index()
            if not len(gross):
                continue
            stats = KP._newey_west_stats(gross, horizon)
            net_stats = KP._newey_west_stats(net, horizon) if len(net) else stats
            summary = _summary_stats(gross, horizon)
            eff = int(stats["effectiveDates"])
            shrink = eff / (eff + prior_strength) if eff else 0.0
            base_mean = float(net_stats["mean"] if cost_adjusted and len(net) else stats["mean"])
            shrunk = base_mean * shrink
            se = stats.get("se")
            stability = _fold_stability(subset.assign(value=subset["excessReturn"]))
            regime_share = _concentration(subset, "macroRegime")
            sector_share = _concentration(subset, "sector")
            coverage = float(subset["pitCoverage"].mean()) if len(subset) else 0.0
            weight = evidence_weight(
                pit_coverage=coverage, survivorship_risk=survivorship,
                macro_pit_status=macro_status, fundamentals_pit=fundamentals_pit,
                regime_share=regime_share, sector_share=sector_share,
                fold_stable=stability.get("stable"), effective_dates=eff,
                min_effective_dates=min_eff,
            )
            rows.append({
                "bucket": bucket,
                "observations": int(len(subset)),
                "uniqueSignalDates": int(stats["uniqueDates"]),
                "effectiveDates": eff,
                "hacLag": int(stats["hacLag"]),
                "meanExcessReturnPct": round(float(stats["mean"]) * 100, 3),
                "costAdjustedMeanExcessReturnPct": (round(float(net_stats["mean"]) * 100, 3)
                                                     if len(net) else None),
                "shrunkExpectedExcessReturnPct": round(shrunk * 100, 3),
                "shrinkageFactor": round(shrink, 4),
                "standardErrorPct": round(float(se) * 100, 4) if se is not None else None,
                "confidenceIntervalPct": ([round((base_mean - 1.96 * se) * shrink * 100, 3),
                                            round((base_mean + 1.96 * se) * shrink * 100, 3)]
                                           if se is not None else None),
                "positiveHitRatio": summary["hitRatio"],
                "medianExcessReturnPct": round((summary["median"] or 0) * 100, 3),
                "mddPct": round(summary["mdd"] * 100, 3) if summary["mdd"] is not None else None,
                "cvar95Pct": round(summary["cvar95"] * 100, 3) if summary["cvar95"] is not None else None,
                "nonOverlappingDates": summary["nonOverlappingDates"],
                "meanPitCoverage": round(coverage, 4),
                "topRegimeSharePct": round(regime_share * 100, 1) if regime_share is not None else None,
                "topSectorSharePct": round(sector_share * 100, 1) if sector_share is not None else None,
                "foldStability": stability,
                "evidenceWeight": weight["weight"],
                "evidenceWeightDetail": weight,
                "usable": bool(eff >= min_eff),
            })
        if not rows:
            continue
        rows = _repair_monotonicity(rows)
        regions[region] = {
            "buckets": rows,
            "observations": int(len(region_frame)),
            "uniqueDates": int(region_frame["date"].nunique()),
            "usableBuckets": sum(1 for r in rows if r["usable"]),
        }

    return {
        "horizonDays": horizon,
        "available": bool(regions),
        "method": "DATE_CLUSTERED_NEWEY_WEST_HAC_WITH_ISOTONIC_REPAIR",
        "evidenceClass": "HISTORICAL_OOS",
        "costAdjusted": bool(cost_adjusted),
        "buckets": list(edges),
        "excludedLowPitObservations": excluded_low_pit,
        "regions": regions,
        "notAForecastKo": ("알파 백분위는 순위이며, 여기 수치는 과거 같은 순위 구간에서 실제로 "
                            "관측된 초과수익 분포입니다. 미래 수익 보장이 아닙니다."),
    }


def _repair_monotonicity(rows: list[dict]) -> list[dict]:
    """Force a non-decreasing bucket ladder, and say when repair was needed."""
    usable = [r for r in rows if r["usable"]]
    if len(usable) < 2:
        for row in rows:
            row["monotonicityWarning"] = None
            row["calibratedExpectedExcessReturnPct"] = row["shrunkExpectedExcessReturnPct"]
        return rows
    values = [r["shrunkExpectedExcessReturnPct"] for r in usable]
    weights = [max(1, int(r["effectiveDates"])) for r in usable]
    repaired = KP._isotonic_non_decreasing(values, weights)
    violated = any(abs(a - b) > 1e-9 for a, b in zip(values, repaired))
    lookup = {r["bucket"]: v for r, v in zip(usable, repaired)}
    for row in rows:
        row["preIsotonicExpectedExcessReturnPct"] = row["shrunkExpectedExcessReturnPct"]
        row["calibratedExpectedExcessReturnPct"] = round(
            lookup.get(row["bucket"], row["shrunkExpectedExcessReturnPct"]), 3)
        row["monotonicityWarning"] = "BUCKET_MONOTONICITY_REPAIRED" if violated else None
    return rows


def lookup_bucket(calibration: dict, region: str, alpha_percentile: float | None) -> dict | None:
    """The calibrated row a live candidate falls into, or None."""
    if not calibration or not calibration.get("available") or alpha_percentile is None:
        return None
    region_blob = (calibration.get("regions") or {}).get(region)
    if not region_blob:
        return None
    edges = [float(x) for x in calibration.get("buckets") or DEFAULT_BUCKETS]
    target = KP._bucket(float(alpha_percentile), edges)
    if not target:
        return None
    label = _bucket_label(*target)
    for row in region_blob.get("buckets", []):
        if row["bucket"] == label:
            return row
    return None


# --------------------------------------------------------------------------- #
# Regime interaction — researched, not switched on by default
# --------------------------------------------------------------------------- #
REGIME_SIGNIFICANCE_Z = 1.96
REGIME_MIN_EFFECTIVE_DATES = 15


def regime_interaction(outcomes: list[dict], *, horizon: int = 126,
                       buckets=DEFAULT_BUCKETS, cfg: dict | None = None,
                       require_pit: bool = True) -> dict:
    """Does the alpha bucket's payoff depend on the macro regime?

    Region x bucket is the BASE calibration and stays the base. Splitting it
    again by regime is tempting and usually wrong: five buckets x two regions x
    five regimes is fifty cells carved out of one dataset, and most of them will
    show a large "effect" made entirely of noise.

    So this function is a diagnostic, not a second calibration. Each cell is
    shrunk toward its region x bucket parent by ``eff / (eff + parent_strength)``
    — hierarchical shrinkage, so a thin cell simply reports the parent — and the
    interaction is marked significant only when the gap clears roughly two
    standard errors AND the cell has enough effective dates to be worth reading.

    ``activate`` is the field a caller should gate on. It is true only when at
    least one cell in that region is genuinely significant; until then the base
    calibration is the whole story and this output is research.
    """
    cfg = cfg or {}
    min_eff = int(cfg.get("minEffectiveDates", 30))
    parent_strength = float(cfg.get("regimeShrinkageStrength", min_eff))
    edges = [float(x) for x in buckets]

    frame = horizon_frame(outcomes, horizon)
    if require_pit and len(frame):
        frame = frame[frame["usableForCalibration"]]
    if not len(frame) or "macroRegime" not in frame:
        return {"available": False, "reason": "no_usable_outcomes", "regions": {},
                "activate": False}
    frame = frame.copy()
    frame["bucket"] = [
        _bucket_label(*b) if (b := KP._bucket(v, edges)) else None
        for v in frame["alphaPercentile"]
    ]
    frame = frame.dropna(subset=["bucket", "macroRegime"])
    if not len(frame):
        return {"available": False, "reason": "no_macro_regime_labels_in_ledger",
                "regions": {}, "activate": False,
                "noteKo": "매크로 데이터 없이 재현한 구간은 국면 라벨이 없어 상호작용을 볼 수 없습니다."}

    regions: dict[str, dict] = {}
    any_significant = False
    for region in sorted(frame["region"].unique()):
        region_frame = frame[frame["region"] == region]
        cells: list[dict] = []
        for bucket in sorted(region_frame["bucket"].unique(),
                             key=lambda b: float(b.split("-")[0])):
            bucket_frame = region_frame[region_frame["bucket"] == bucket]
            parent_series = bucket_frame.groupby("date")["excessReturn"].mean().dropna()
            if not len(parent_series):
                continue
            parent = KP._newey_west_stats(parent_series, horizon)
            for regime in sorted(bucket_frame["macroRegime"].dropna().unique()):
                cell_frame = bucket_frame[bucket_frame["macroRegime"] == regime]
                series = cell_frame.groupby("date")["excessReturn"].mean().dropna()
                if len(series) < 3:
                    continue
                stats = KP._newey_west_stats(series, horizon)
                eff = int(stats["effectiveDates"])
                weight = eff / (eff + parent_strength) if eff else 0.0
                shrunk = weight * float(stats["mean"]) + (1 - weight) * float(parent["mean"])
                gap = float(stats["mean"]) - float(parent["mean"])
                se = stats.get("se")
                z = (gap / se) if se else None
                significant = bool(
                    z is not None and abs(z) >= REGIME_SIGNIFICANCE_Z
                    and eff >= REGIME_MIN_EFFECTIVE_DATES)
                any_significant = any_significant or significant
                cells.append({
                    "bucket": bucket, "regime": regime,
                    "observations": int(len(cell_frame)),
                    "effectiveDates": eff,
                    "rawMeanExcessPct": round(float(stats["mean"]) * 100, 3),
                    "parentMeanExcessPct": round(float(parent["mean"]) * 100, 3),
                    "shrunkMeanExcessPct": round(shrunk * 100, 3),
                    "shrinkageTowardParent": round(1 - weight, 4),
                    "gapVsParentPct": round(gap * 100, 3),
                    "zScore": round(z, 3) if z is not None else None,
                    "significant": significant,
                })
        if cells:
            regions[region] = {"cells": cells,
                               "significantCells": sum(1 for c in cells if c["significant"])}
    return {
        "available": bool(regions),
        "method": "HIERARCHICAL_SHRINKAGE_TOWARD_REGION_ALPHA_BUCKET",
        "regions": regions,
        # The gate. Base calibration stays authoritative until this is true.
        "activate": bool(any_significant),
        "minEffectiveDates": REGIME_MIN_EFFECTIVE_DATES,
        "significanceZ": REGIME_SIGNIFICANCE_Z,
        "policyKo": ("지역 x 알파버킷을 기본 calibration으로 유지하고, 국면 상호작용은 "
                      "OOS에서 유의미할 때만 추가합니다. 표본이 얇은 셀은 상위 버킷 값으로 "
                      "수축되어 사실상 기본값을 보고합니다."),
    }
