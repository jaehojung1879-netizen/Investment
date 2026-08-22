"""Maturity-aware up/down probability calibration for portfolio Kelly.

The portfolio optimizer uses a vector of expected excess returns and a
covariance matrix.  That is the multivariate form of Kelly and does not require
pretending every investment is a two-outcome bet.  A useful safety check is
still missing if we publish only the mean, however: *how often was the excess
return positive, how large were wins and losses, and did a probability forecast
made with information available at the time match the observed frequency?*

This module supplies that check without leaking labels backwards:

* the target is cost-adjusted regional excess return > 0 at ``horizon``;
* a label enters the expanding training state only on its stored ``endDate``;
* hundreds of names on one date are scored as one date cluster;
* region/alpha-bucket is the production base probability;
* macro regime and entry state are challengers and are used only when an early
  selection window improves Brier score and a later audit window passes the
  reliability gate;
* Beta shrinkage and payoff shrinkage pull thin cells to their parent instead
  of manufacturing extreme probabilities or payout ratios.

The result is a probability *audit and gate*, not a promise that the next price
move is known.  If the gate fails, constrained Kelly is withheld and the
existing conviction-tilted risk allocation remains in force.
"""
from __future__ import annotations

import math
from collections import defaultdict

import numpy as np
import pandas as pd

from .historical_outcomes import horizon_frame

DEFAULTS = {
    "priorStrength": 20.0,
    "payoffPriorStrength": 20.0,
    "minTrainingDates": 30,
    "minAuditDates": 63,
    "minIndependentAuditDates": 8,
    "minConditionDates": 20,
    "selectionFraction": 0.65,
    "minConditionBrierImprovement": 0.0025,
    "maxBrier": 0.255,
    "maxEce": 0.10,
    "maxLogLoss": 0.72,
    # Skill has to mean skill. A negative floor was letting through a
    # distribution WORSE than simply predicting the regional base rate, and the
    # other three checks cannot catch that: a constant predictor at the base
    # rate has Brier <= 0.25 by construction, near-zero ECE, and log-loss ~0.69,
    # so it clears maxBrier, maxEce and maxLogLoss every time. This is the only
    # check standing between a zero-information distribution and a Kelly weight.
    #
    # The floor is not a noise allowance. Simulating the null directly — a
    # constant predictor at the base rate, baseline estimated on the same audit
    # sample — gives a skill distribution far tighter than the old tolerance:
    #
    #     audit dates    null sd     false-pass at -0.01   at 0.0
    #             63     0.00113                    100%     1.9%
    #            200     0.00035                    100%     0.9%
    #            400     0.00017                    100%     1.0%
    #
    # -0.01 is roughly nine standard deviations of slack and admits every
    # uninformative model. 0.0 is the honest bar and costs ~1-2% false rejection.
    "minBrierSkill": 0.0,
}

VARIANTS = ("BASE", "MACRO", "ENTRY")


def _bucket(value: float | None, edges: list[float]) -> tuple[float, float] | None:
    if value is None or not np.isfinite(value):
        return None
    for lo, hi in zip(edges[:-1], edges[1:]):
        if lo <= float(value) < hi or (float(value) == edges[-1] and hi == edges[-1]):
            return float(lo), float(hi)
    return None


def _label(bounds: tuple[float, float] | None) -> str | None:
    return f"{bounds[0]:g}-{bounds[1]:g}" if bounds else None


def _posterior(success: float, trials: float, parent_probability: float,
               prior_strength: float) -> tuple[float, list[float]]:
    trials = max(0.0, float(trials))
    prior_strength = max(0.0, float(prior_strength))
    total = trials + prior_strength
    probability = ((float(success) + parent_probability * prior_strength) / total
                   if total else float(parent_probability))
    probability = float(np.clip(probability, 0.001, 0.999))
    variance = probability * (1.0 - probability) / max(total + 1.0, 1.0)
    half = 1.96 * math.sqrt(max(variance, 0.0))
    return probability, [max(0.0, probability - half), min(1.0, probability + half)]


def _metrics(rows: list[dict], variant: str, *, horizon: int) -> dict:
    if not rows:
        return {"available": False, "predictions": 0, "dates": 0,
                "independentDates": 0, "brier": None, "baselineBrier": None,
                "brierSkill": None, "ece": None, "logLoss": None}
    frame = pd.DataFrame(rows)
    p = pd.to_numeric(frame[variant], errors="coerce").clip(0.001, 0.999)
    y = pd.to_numeric(frame["actual"], errors="coerce").clip(0.0, 1.0)
    base = pd.to_numeric(frame["REGION_BASELINE"], errors="coerce").clip(0.001, 0.999)
    valid = p.notna() & y.notna() & base.notna()
    frame, p, y, base = frame.loc[valid], p.loc[valid], y.loc[valid], base.loc[valid]
    if frame.empty:
        return {"available": False, "predictions": 0, "dates": 0,
                "independentDates": 0, "brier": None, "baselineBrier": None,
                "brierSkill": None, "ece": None, "logLoss": None}

    # Losses are averaged within date before being averaged through time.  A
    # broad cross-section therefore cannot masquerade as independent history.
    loss = pd.DataFrame({
        "date": pd.to_datetime(frame["date"]),
        "brier": (p - y) ** 2,
        "baseBrier": (base - y) ** 2,
        "logLoss": -(y * np.log(p) + (1.0 - y) * np.log(1.0 - p)),
    }).groupby("date", sort=True).mean()
    brier = float(loss["brier"].mean())
    base_brier = float(loss["baseBrier"].mean())

    # ECE uses one probability/frequency pair per date.  Using the individual
    # cells here would quietly give a day with more populated buckets more
    # influence even though every other audit loss is date-clustered.
    calibration = pd.DataFrame({
        "date": pd.to_datetime(frame["date"]),
        "probability": p,
        "actual": y,
    }).groupby("date", sort=True).mean()
    bins = np.linspace(0.0, 1.0, 6)
    calibration_p = calibration["probability"].to_numpy()
    calibration_y = calibration["actual"].to_numpy()
    labels = np.digitize(calibration_p, bins[1:-1], right=False)
    ece = 0.0
    calibration_bins = []
    for idx in range(5):
        mask = labels == idx
        if not mask.any():
            continue
        predicted = float(calibration_p[mask].mean())
        realized = float(calibration_y[mask].mean())
        ece += float(mask.mean()) * abs(predicted - realized)
        calibration_bins.append({
            "range": f"{int(bins[idx] * 100)}-{int(bins[idx + 1] * 100)}",
            "predictedPct": round(predicted * 100, 3),
            "realizedPct": round(realized * 100, 3),
            "dates": int(mask.sum()),
        })

    dates = sorted(pd.Timestamp(x).normalize() for x in loss.index)
    independent: list[pd.Timestamp] = []
    for stamp in dates:
        if not independent or stamp >= independent[-1] + pd.offsets.BDay(horizon):
            independent.append(stamp)
    return {
        "available": True,
        "predictions": int(len(frame)),
        "dates": int(len(loss)),
        "independentDates": int(len(independent)),
        "brier": round(brier, 5),
        "baselineBrier": round(base_brier, 5),
        "brierSkill": (round(1.0 - brier / base_brier, 4) if base_brier > 0 else None),
        "ece": round(float(ece), 5),
        "logLoss": round(float(loss["logLoss"].mean()), 5),
        "calibrationBins": calibration_bins,
    }


def _gate(metrics: dict, cfg: dict, *, selected_variant: str = "BASE") -> dict:
    checks = {
        "auditDates": int(metrics.get("dates") or 0) >= int(cfg["minAuditDates"]),
        "independentAuditDates": int(metrics.get("independentDates") or 0)
        >= int(cfg["minIndependentAuditDates"]),
        "brier": metrics.get("brier") is not None
        and float(metrics["brier"]) <= float(cfg["maxBrier"]),
        "ece": metrics.get("ece") is not None
        and float(metrics["ece"]) <= float(cfg["maxEce"]),
        "logLoss": metrics.get("logLoss") is not None
        and float(metrics["logLoss"]) <= float(cfg["maxLogLoss"]),
        "brierSkill": metrics.get("brierSkill") is not None
        and float(metrics["brierSkill"]) >= float(cfg["minBrierSkill"]),
        # A conditional challenger must still add value in the untouched audit
        # window. Beating only the unconditional regional baseline is not
        # enough if it is worse than the region×alpha BASE it would replace.
        "conditionalAuditImprovement": (
            selected_variant == "BASE"
            or (metrics.get("conditionalBrierImprovement") is not None
                and float(metrics["conditionalBrierImprovement"])
                >= float(cfg["minConditionBrierImprovement"]))),
    }
    return {
        "eligible": bool(all(checks.values())),
        "checks": checks,
        "failures": [key for key, passed in checks.items() if not passed],
        "thresholds": {key: cfg[key] for key in (
            "minAuditDates", "minIndependentAuditDates", "maxBrier", "maxEce",
            "maxLogLoss", "minBrierSkill", "minConditionBrierImprovement")},
        "method": "MATURITY_AWARE_EXPANDING_WALK_FORWARD",
    }


def _events(frame: pd.DataFrame, keys: list[str]) -> list[dict]:
    rows = []
    grouped = frame.groupby(["date", *keys], dropna=False, sort=True)
    for values, subset in grouped:
        values = values if isinstance(values, tuple) else (values,)
        key_values = values[1:]
        end_dates = pd.to_datetime(subset["outcomeEndDate"], errors="coerce").dropna()
        if end_dates.empty:
            continue
        rows.append({
            "date": pd.Timestamp(values[0]).normalize(),
            "endDate": pd.Timestamp(end_dates.max()).normalize(),
            "key": tuple("UNKNOWN" if pd.isna(v) else str(v) for v in key_values),
            "actual": float(subset["target"].mean()),
        })
    return rows


def _walk_forward_region(frame: pd.DataFrame, cfg: dict, horizon: int) -> dict:
    """Generate true prequential probabilities for one region."""
    parent_events = _events(frame, ["bucket"])
    macro_events = _events(frame, ["bucket", "macroRegime"])
    entry_events = _events(frame, ["bucket", "entryState"])
    region_events = _events(frame.assign(_region="REGION"), ["_region"])
    cells = _events(frame, ["bucket", "macroRegime", "entryState"])

    state = {
        "region": defaultdict(lambda: [0.0, 0.0]),
        "parent": defaultdict(lambda: [0.0, 0.0]),
        "macro": defaultdict(lambda: [0.0, 0.0]),
        "entry": defaultdict(lambda: [0.0, 0.0]),
    }
    streams = {
        "region": sorted(region_events, key=lambda x: (x["endDate"], x["date"])),
        "parent": sorted(parent_events, key=lambda x: (x["endDate"], x["date"])),
        "macro": sorted(macro_events, key=lambda x: (x["endDate"], x["date"])),
        "entry": sorted(entry_events, key=lambda x: (x["endDate"], x["date"])),
    }
    cursors = {key: 0 for key in streams}
    prior_strength = float(cfg["priorStrength"])
    condition_strength = float(cfg["priorStrength"])
    min_train = int(cfg["minTrainingDates"])
    min_condition = int(cfg["minConditionDates"])
    predictions: list[dict] = []

    def admit(cutoff: pd.Timestamp) -> None:
        for name, rows in streams.items():
            cursor = cursors[name]
            while cursor < len(rows) and rows[cursor]["endDate"] <= cutoff:
                event = rows[cursor]
                success, trials = state[name][event["key"]]
                state[name][event["key"]] = [success + event["actual"], trials + 1.0]
                cursor += 1
            cursors[name] = cursor

    for date in sorted({row["date"] for row in cells}):
        admit(pd.Timestamp(date).normalize())
        for cell in [row for row in cells if row["date"] == date]:
            bucket, macro, entry = cell["key"]
            region_success, region_trials = state["region"][("REGION",)]
            region_p, _ = _posterior(region_success, region_trials, 0.5, prior_strength)
            bucket_success, bucket_trials = state["parent"][(bucket,)]
            if region_trials < min_train or bucket_trials < min_train:
                continue
            base_p, _ = _posterior(bucket_success, bucket_trials, region_p, prior_strength)
            macro_success, macro_trials = state["macro"][(bucket, macro)]
            entry_success, entry_trials = state["entry"][(bucket, entry)]
            macro_p = (_posterior(macro_success, macro_trials, base_p, condition_strength)[0]
                       if macro_trials >= min_condition else base_p)
            entry_p = (_posterior(entry_success, entry_trials, base_p, condition_strength)[0]
                       if entry_trials >= min_condition else base_p)
            predictions.append({
                "date": date, "actual": cell["actual"], "REGION_BASELINE": region_p,
                "BASE": base_p, "MACRO": macro_p, "ENTRY": entry_p,
                "bucket": bucket, "macroRegime": macro, "entryState": entry,
            })

    dates = sorted({pd.Timestamp(row["date"]).normalize() for row in predictions})
    if len(dates) < 2:
        return {"available": False, "reason": "no_maturity_safe_predictions",
                "selectedVariant": "BASE", "variants": {},
                "audit": _metrics([], "BASE", horizon=horizon),
                "reliabilityGate": _gate({}, cfg)}
    split_idx = max(1, min(len(dates) - 1,
                           int(len(dates) * float(cfg["selectionFraction"]))))
    split_date = dates[split_idx]
    selection_rows = [row for row in predictions if pd.Timestamp(row["date"]) < split_date]
    audit_rows = [row for row in predictions if pd.Timestamp(row["date"]) >= split_date]
    selection = {variant: _metrics(selection_rows, variant, horizon=horizon)
                 for variant in VARIANTS}
    base_score = selection["BASE"].get("brier")
    selected = "BASE"
    if base_score is not None:
        candidates = []
        for variant in ("MACRO", "ENTRY"):
            score = selection[variant].get("brier")
            if score is not None and base_score - score >= float(cfg["minConditionBrierImprovement"]):
                candidates.append((score, variant))
        if candidates:
            selected = min(candidates, key=lambda item: (item[0], item[1]))[1]
    audit = _metrics(audit_rows, selected, horizon=horizon)
    base_audit = _metrics(audit_rows, "BASE", horizon=horizon)
    audit["baseVariantBrier"] = base_audit.get("brier")
    audit["conditionalBrierImprovement"] = (
        round(float(base_audit["brier"]) - float(audit["brier"]), 5)
        if base_audit.get("brier") is not None and audit.get("brier") is not None
        else None)
    gate = _gate(audit, cfg, selected_variant=selected)
    return {
        "available": True,
        "selectedVariant": selected,
        "variantsTried": list(VARIANTS),
        "selectionPeriod": [str(dates[0].date()), str((split_date - pd.Timedelta(days=1)).date())],
        "auditPeriod": [str(split_date.date()), str(dates[-1].date())],
        "selection": selection,
        "audit": audit,
        "reliabilityGate": gate,
        "predictions": len(predictions),
        "labelAvailabilityPolicy": "OUTCOME_END_DATE_LTE_PREDICTION_DATE",
    }


def _date_values(subset: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.Series]:
    hit = subset.groupby("date", sort=True)["target"].mean()
    upside = subset[subset["netReturn"] > 0].groupby("date", sort=True)["netReturn"].mean()
    downside = (-subset[subset["netReturn"] <= 0]
                .groupby("date", sort=True)["netReturn"].mean())
    return hit, upside, downside


def _effective_count(series: pd.Series, horizon: int) -> int:
    """Conservative effective count for overlapping forward labels."""
    clean = pd.to_numeric(series, errors="coerce").dropna().sort_index()
    if clean.empty:
        return 0
    independent: list[pd.Timestamp] = []
    for stamp in (pd.Timestamp(x).normalize() for x in clean.index):
        if not independent or stamp >= independent[-1] + pd.offsets.BDay(horizon):
            independent.append(stamp)
    non_overlapping = max(1, len(independent))
    arr = clean.to_numpy(dtype=float)
    n = len(arr)
    centered = arr - float(arr.mean())
    gamma0 = float(centered @ centered / n)
    lag = min(max(0, int(horizon) - 1), n - 1)
    long_run = gamma0
    for k in range(1, lag + 1):
        gamma = float(centered[k:] @ centered[:-k] / n)
        long_run += 2.0 * (1.0 - k / (lag + 1.0)) * gamma
    long_run = max(long_run, 0.0)
    hac_effective = (n if long_run <= 1e-18
                     else int(max(1, min(n, math.floor(n * gamma0 / long_run)))))
    # A constant all-win cell has zero estimated autocovariance and would make
    # HAC report every overlapping label as independent.  The horizon-spaced
    # cap prevents that most seductive thin-cell failure.
    return min(hac_effective, non_overlapping)


def _distribution(subset: pd.DataFrame, *, parent: dict | None, cfg: dict,
                  horizon: int) -> dict:
    hit, upside, downside = _date_values(subset)
    dates = int(len(hit))
    effective = _effective_count(hit, horizon)
    scale = effective / dates if dates else 0.0
    parent_p = float((parent or {}).get("upProbabilityPct", 50.0)) / 100.0
    probability, interval = _posterior(float(hit.sum()) * scale, effective,
                                       parent_p, float(cfg["priorStrength"]))

    parent_up = float((parent or {}).get("averageUpsidePct") or 0.0) / 100.0
    parent_down = float((parent or {}).get("averageDownsidePct") or 0.0) / 100.0
    if parent is None:
        parent_up = float(upside.mean()) if len(upside) else 0.0
        parent_down = float(downside.mean()) if len(downside) else 0.0
    payoff_prior = float(cfg["payoffPriorStrength"])
    up_eff = _effective_count(upside, horizon)
    down_eff = _effective_count(downside, horizon)
    observed_up = float(upside.mean()) if len(upside) else parent_up
    observed_down = float(downside.mean()) if len(downside) else parent_down
    avg_up = ((observed_up * up_eff + parent_up * payoff_prior)
              / (up_eff + payoff_prior) if up_eff + payoff_prior else 0.0)
    avg_down = ((observed_down * down_eff + parent_down * payoff_prior)
                / (down_eff + payoff_prior) if down_eff + payoff_prior else 0.0)
    expected = probability * avg_up - (1.0 - probability) * avg_down
    payoff_ratio = avg_up / avg_down if avg_down > 1e-12 else None
    binary_kelly = (probability - (1.0 - probability) / payoff_ratio
                    if payoff_ratio and payoff_ratio > 0 else None)
    return {
        "observations": int(len(subset)),
        "dates": dates,
        "effectiveDates": effective,
        "upProbabilityPct": round(probability * 100.0, 2),
        "downProbabilityPct": round((1.0 - probability) * 100.0, 2),
        "probabilityIntervalPct": [round(x * 100.0, 2) for x in interval],
        "averageUpsidePct": round(avg_up * 100.0, 3),
        "averageDownsidePct": round(avg_down * 100.0, 3),
        "payoffRatio": round(payoff_ratio, 4) if payoff_ratio is not None else None,
        "distributionExpectedExcessReturnPct": round(expected * 100.0, 3),
        "binaryKellyFraction": (round(float(np.clip(binary_kelly, -1.0, 1.0)), 4)
                                 if binary_kelly is not None else None),
        "target": "COST_ADJUSTED_REGIONAL_EXCESS_RETURN_GT_ZERO",
    }


def calibrate(outcomes: list[dict], *, horizon: int = 126,
              buckets=(0, 60, 80, 90, 95, 100), cfg: dict | None = None,
              require_pit: bool = True) -> dict:
    config = {**DEFAULTS, **(cfg or {})}
    edges = [float(x) for x in buckets]
    frame = horizon_frame(outcomes, horizon, cost_adjusted=False)
    if require_pit and len(frame):
        frame = frame[frame["usableForCalibration"]]
    required = {"date", "outcomeEndDate", "region", "alphaPercentile",
                "costAdjustedExcessReturn"}
    if frame.empty or not required <= set(frame.columns):
        return {"available": False, "reason": "no_matured_probability_outcomes",
                "regions": {}, "reliabilityGate": {"eligible": False,
                "failures": ["no_matured_probability_outcomes"]}}
    frame = frame.copy()
    frame["bucket"] = [_label(_bucket(value, edges)) for value in frame["alphaPercentile"]]
    frame["netReturn"] = pd.to_numeric(frame["costAdjustedExcessReturn"], errors="coerce")
    frame["outcomeEndDate"] = pd.to_datetime(frame["outcomeEndDate"], errors="coerce")
    frame = frame.dropna(subset=["bucket", "netReturn", "outcomeEndDate"])
    frame["target"] = (frame["netReturn"] > 0).astype(float)
    frame["macroRegime"] = frame["macroRegime"].fillna("UNKNOWN")
    frame["entryState"] = frame["entryState"].fillna("UNKNOWN")
    if frame.empty:
        return {"available": False, "reason": "probability_rows_invalid",
                "regions": {}, "reliabilityGate": {"eligible": False,
                "failures": ["probability_rows_invalid"]}}

    regions: dict[str, dict] = {}
    for region in sorted(frame["region"].unique()):
        regional = frame[frame["region"] == region]
        walk = _walk_forward_region(regional, config, horizon)
        regional_parent = _distribution(regional, parent=None, cfg=config, horizon=horizon)
        rows = []
        for bucket in sorted(regional["bucket"].unique(), key=lambda x: float(x.split("-")[0])):
            subset = regional[regional["bucket"] == bucket]
            base = _distribution(subset, parent=regional_parent, cfg=config, horizon=horizon)
            macro_cells = {}
            for macro in sorted(subset["macroRegime"].unique()):
                cell = _distribution(subset[subset["macroRegime"] == macro], parent=base,
                                     cfg=config, horizon=horizon)
                cell["eligible"] = bool(
                    walk.get("selectedVariant") == "MACRO"
                    and (walk.get("reliabilityGate") or {}).get("eligible")
                    and int(cell.get("effectiveDates") or 0) >= int(config["minConditionDates"]))
                macro_cells[macro] = cell
            entry_cells = {}
            for state in sorted(subset["entryState"].unique()):
                cell = _distribution(subset[subset["entryState"] == state], parent=base,
                                     cfg=config, horizon=horizon)
                cell["eligible"] = bool(
                    walk.get("selectedVariant") == "ENTRY"
                    and (walk.get("reliabilityGate") or {}).get("eligible")
                    and int(cell.get("effectiveDates") or 0) >= int(config["minConditionDates"]))
                entry_cells[state] = cell
            rows.append({"bucket": bucket, **base, "macroConditions": macro_cells,
                         "entryConditions": entry_cells})
        regions[region] = {**walk, "baseRate": regional_parent, "buckets": rows}

    by_region = {region: (blob.get("reliabilityGate") or {})
                 for region, blob in regions.items()}
    overall_eligible = bool(by_region) and all(gate.get("eligible") for gate in by_region.values())
    return {
        "available": bool(regions),
        "horizonDays": int(horizon),
        "method": "MATURITY_AWARE_EXPANDING_BETA_BINOMIAL",
        "target": "COST_ADJUSTED_REGIONAL_EXCESS_RETURN_GT_ZERO",
        "buckets": edges,
        "regions": regions,
        "reliabilityGate": {
            "eligible": overall_eligible,
            "byRegion": by_region,
            "failures": [region for region, gate in by_region.items() if not gate.get("eligible")],
            "requiredForKelly": True,
        },
        "configuration": {key: config[key] for key in DEFAULTS},
        "explainKo": ("상승확률은 126일 비용 차감 지역 초과수익이 0보다 클 빈도입니다. "
                      "각 결과가 실제 만기된 뒤에만 다음 예측에 사용하며, 거시·진입상태 조건은 "
                      "별도 시계열 감사 구간에서 Brier 점수를 개선할 때만 적용합니다."),
    }


def lookup_distribution(surface: dict | None, region: str,
                        alpha_percentile: float | None, *, macro_regime: str | None,
                        entry_state: str | None) -> dict | None:
    """Return the audited distribution applicable to one live candidate."""
    if not surface or not surface.get("available") or alpha_percentile is None:
        return None
    region_blob = (surface.get("regions") or {}).get(region)
    if not region_blob:
        return None
    bounds = _bucket(float(alpha_percentile), [float(x) for x in surface.get("buckets") or []])
    label = _label(bounds)
    base = next((row for row in region_blob.get("buckets", []) if row.get("bucket") == label), None)
    if not base:
        return None
    variant = region_blob.get("selectedVariant") or "BASE"
    chosen = base
    context = "REGION_ALPHA_BUCKET"
    fallback = None
    if variant == "MACRO":
        cell = (base.get("macroConditions") or {}).get(macro_regime or "UNKNOWN")
        if cell and cell.get("eligible"):
            chosen, context = cell, "REGION_ALPHA_BUCKET_MACRO"
        else:
            fallback = "macro_cell_not_reliable"
    elif variant == "ENTRY":
        cell = (base.get("entryConditions") or {}).get(entry_state or "UNKNOWN")
        if cell and cell.get("eligible"):
            chosen, context = cell, "REGION_ALPHA_BUCKET_ENTRY"
        else:
            fallback = "entry_cell_not_reliable"
    keys = ("observations", "dates", "effectiveDates", "upProbabilityPct",
            "downProbabilityPct", "probabilityIntervalPct", "averageUpsidePct",
            "averageDownsidePct", "payoffRatio", "distributionExpectedExcessReturnPct",
            "binaryKellyFraction", "target")
    return {
        **{key: chosen.get(key) for key in keys},
        "bucket": label,
        "selectedVariant": variant,
        "contextUsed": context,
        "macroRegime": macro_regime,
        "entryState": entry_state,
        "fallbackReason": fallback,
        "reliabilityEligible": bool(
            (region_blob.get("reliabilityGate") or {}).get("eligible")
            and (surface.get("integrityGate") or {}).get("eligible", True)),
        "audit": region_blob.get("audit"),
        "reliabilityGate": region_blob.get("reliabilityGate"),
        "integrityGate": surface.get("integrityGate"),
        "evidenceClass": "HISTORICAL_OOS",
    }
