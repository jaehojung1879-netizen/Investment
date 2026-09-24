"""Pre-registered evidence for alpha-opportunity-model-v2. Research only.

Nothing here selects a portfolio, sizes a position or compounds a path. Every
function works on per-date summaries of name-level predictions against their
own regional benchmark, and every interval resamples WHOLE weekly dates in
moving blocks (never independent name rows), exactly as v1 sealed it.

What v2 adds to v1's instruments, and why:

* The probability head predicts the NET event, P(R_i - R_b - cost > 0),
  because the competitor for the capital is the benchmark net of switching.
* Absolute calibration (A) is measured on the pooled, NOT within-date
  demeaned, relationship between predicted and realised relative return:
  the v2 question is whether a predicted +X means something in absolute
  terms, which a purely cross-sectional statistic cannot answer.
* Opportunity evidence (D) must clear BOTH the outside option's level (0)
  and the spread over non-active names on the same date — the repository's
  "lesser of level and spread" rule, so universe carry cannot be credited as
  opportunity.
* Missing forward endpoints are no longer allowed to void every date. They
  are bounded: every gate must hold with unresolved names left out AND with
  them assigned the date's worst plausible observed outcome, and the active
  set's level is additionally stressed for PIT members the panel never
  priced (`portfolio_validation`'s survivorship-bound convention).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from .alpha_opportunity_model import block_sample_indices

MATURED = "MATURED"
PENDING = "PENDING"
UNRESOLVED = "MISSING_FORWARD_PRICE_OR_DELISTING"
TREATMENTS = ("OBSERVED_ONLY", "WORST_PLAUSIBLE")
QUALITY_METRICS = ("rankIC", "withinDateSlope", "brierImprovement",
                   "logLossImprovement", "mseImprovement")


# --------------------------------------------------------------------------- #
# Labels
# --------------------------------------------------------------------------- #
def target_from_sessions(sessions, prices, benchmark, ticker, date, horizon, through):
    """v1's `target_at` semantics against a precomputed regional calendar.

    Entry is the next regional session CLOSE after the information date; exit
    is `horizon` further sessions. Exact endpoints only: no nearest date, no
    forward fill, no last price, no zero. Pending is decided by the calendar
    alone, before any price is read.
    """
    days = pd.DatetimeIndex(sessions)
    pos = days.searchsorted(pd.Timestamp(date), side="right")
    if pos + horizon >= len(days):
        raise ValueError("CALENDAR_TOO_SHORT")
    entry, exit_ = days[pos], days[pos + horizon]
    out = {"entryDate": str(entry.date()), "outcomeEndDate": str(exit_.date()),
           "forwardRelativeReturn": None, "labelStatus": PENDING}
    if exit_ > pd.Timestamp(through):
        return out
    out["labelStatus"] = UNRESOLVED
    values = []
    for name in (ticker, benchmark):
        f = prices.get(name)
        if f is None or entry not in f.index or exit_ not in f.index:
            return out
        a, z = f.loc[entry, "Close"], f.loc[exit_, "Close"]
        if not np.isfinite([a, z]).all() or min(a, z) <= 0:
            return out
        values.append(z / a - 1.0)
    return {**out, "forwardRelativeReturn": float(values[0] - values[1]), "labelStatus": MATURED}


def net_label(relative, cost):
    """1 iff the stock beat its benchmark by more than the round trip it cost."""
    if relative is None or cost is None or not np.isfinite([relative, cost]).all():
        return None
    return int(relative - cost > 0)


def attach_labels(regional, labels):
    """Gross label columns plus the NET label, which exists only when MATURED."""
    data = pd.concat([regional.reset_index(drop=True), labels.reset_index(drop=True)], axis=1)
    if len(data) != len(regional) or len(labels) != len(regional):
        raise ValueError("LABEL_ROW_MISMATCH")
    data["beatBenchmarkNet"] = [net_label(y, c) if s == MATURED else None
                                for y, c, s in zip(data.forwardRelativeReturn, data.roundTripCost,
                                                   data.labelStatus)]
    return data


# --------------------------------------------------------------------------- #
# Survivorship treatment
# --------------------------------------------------------------------------- #
def worst_plausible(observed, *, quantile, minimum_names):
    """The date's own bad outcome: a return some tradable name genuinely earned.

    Same convention as `portfolio_validation.worst_case_excess` — a worst
    PLAUSIBLE outcome, not a worst possible one, and None below the minimum
    tail cross-section rather than a substitute.
    """
    values = pd.to_numeric(pd.Series(observed, dtype=float), errors="coerce").dropna().to_numpy()
    if len(values) < minimum_names:
        return None
    return float(np.quantile(values, quantile))


def apply_treatment(group, treatment, spec):
    """One evaluation date under one endpoint treatment.

    Returns (frame, status). OBSERVED_ONLY drops unresolved endpoints (the
    survivor-favourable reading); WORST_PLAUSIBLE assigns them the date's
    worst plausible observed relative return and a net label of 0. A date
    whose unresolved share exceeds the repository tolerance is INCOMPLETE
    under both, never repaired.
    """
    cfg = spec["survivorship"]
    matured = group.labelStatus.eq(MATURED)
    unresolved = group.labelStatus.eq(UNRESOLVED)
    if group.labelStatus.eq(PENDING).any():
        return None, "PENDING"
    if len(group) < spec["walkForward"]["minimumNamesPerDate"]:
        return None, "TOO_FEW_TRADABLE_NAMES"
    if 100.0 * unresolved.mean() > cfg["dateUnresolvedTolerancePct"]:
        return None, "INCOMPLETE_UNRESOLVED_ENDPOINTS"
    if treatment == "OBSERVED_ONLY":
        return group.loc[matured].copy(), "MEASURED"
    if treatment != "WORST_PLAUSIBLE":
        raise ValueError("UNREGISTERED_TREATMENT")
    out = group.copy()
    if unresolved.any():
        tail = worst_plausible(group.loc[matured, "forwardRelativeReturn"],
                               quantile=cfg["worstPlausibleQuantile"],
                               minimum_names=cfg["minimumTailCrossSection"])
        if tail is None:
            return None, "UNMEASURABLE_TAIL"
        out.loc[unresolved, "forwardRelativeReturn"] = tail
        out.loc[unresolved, "beatBenchmarkNet"] = 0
    return out, "MEASURED"


# --------------------------------------------------------------------------- #
# Per-date predictive statistics (A, B, C)
# --------------------------------------------------------------------------- #
def date_summary(group):
    """All A/B/C statistics for one date, names weighted equally within it."""
    y = group.forwardRelativeReturn.to_numpy(float)
    z = group.beatBenchmarkNet.to_numpy(float)
    p = group.probabilityNetOutperform.to_numpy(float)
    mu = group.grossExpectedAlpha.to_numpy(float)
    b = group.trainingBaseRate.to_numpy(float)
    m = group.trainingMeanReturn.to_numpy(float)
    if not np.isfinite(np.column_stack((y, z, p, mu, b, m))).all():
        raise ValueError("MODEL_UNSTABLE_NONFINITE")
    if ((p < 0) | (p > 1)).any():
        raise ValueError("INVALID_PROBABILITY")
    pc, bc = np.clip(p, 1e-12, 1 - 1e-12), np.clip(b, 1e-12, 1 - 1e-12)

    def loss(v):
        return -(z * np.log(v) + (1 - z) * np.log(1 - v))
    ic = float(spearmanr(mu, y).statistic) if np.ptp(mu) > 0 and np.ptp(y) > 0 else np.nan
    var = np.var(mu)
    slope = float(np.mean((mu - mu.mean()) * (y - y.mean())) / var) if var > 0 else np.nan
    bins = np.minimum((p * 10).astype(int), 9)
    ece = sum(np.mean(bins == j) * abs(p[bins == j].mean() - z[bins == j].mean())
              for j in range(10) if np.any(bins == j))
    # Per-bin date-weighted sums for the POOLED calibration error (gated).
    bin_p = [float(p[bins == j].sum() / len(p)) for j in range(10)]
    bin_z = [float(z[bins == j].sum() / len(p)) for j in range(10)]
    return {"names": len(group), "rankIC": ic, "withinDateSlope": slope,
            "brierImprovement": float(np.mean((b - z) ** 2 - (p - z) ** 2)),
            "logLossImprovement": float(np.mean(loss(bc) - loss(pc))),
            "mseImprovement": float(np.mean((m - y) ** 2 - (mu - y) ** 2)),
            "perDateEce": float(ece), "eceBinP": bin_p, "eceBinZ": bin_z,
            "probabilityBias": float(np.mean(p - z)),
            "expectedReturnBias": float(np.mean(mu - y)),
            # Sufficient statistics for the pooled ABSOLUTE calibration slope.
            "sMu": float(mu.mean()), "sY": float(y.mean()),
            "sMu2": float(np.mean(mu ** 2)), "sMuY": float(np.mean(mu * y))}


def absolute_slope(table):
    """Date-balanced pooled slope of realised on predicted relative return.

    Not demeaned within date, so it rewards a predicted LEVEL that moves with
    the realised level through time, not only a correct ordering.
    """
    if table.empty:
        return np.nan
    mu_bar, y_bar = table.sMu.mean(), table.sY.mean()
    var = table.sMu2.mean() - mu_bar ** 2
    cov = table.sMuY.mean() - mu_bar * y_bar
    return float(cov / var) if var > 1e-18 else np.nan


def pooled_ece(table):
    """Date-balanced ECE over 10 fixed equal-width bins, pooled across dates.

    v1 averaged a PER-DATE ECE, whose noise floor for a perfectly calibrated
    predictor is ~0.070 at 120 names and ~0.035 at 500 (the simulated null
    recorded in the spec): its 0.05 bound rejected a calibrated KR model with
    certainty. Pooling the same bins across dates keeps the same bound
    meaningful (null ~0.001-0.003).
    """
    if table.empty:
        return np.nan
    p = np.vstack(table.eceBinP.to_numpy()).sum(axis=0)
    z = np.vstack(table.eceBinZ.to_numpy()).sum(axis=0)
    return float(np.abs(p - z).sum() / len(table))


def block_interval(table, statistic, spec):
    """Moving-block bootstrap of complete weekly dates; None if too short."""
    cfg = spec["inference"]
    n, block = len(table), cfg["blockDates"]
    if n < cfg["minimumEvaluationBlocks"] * block:
        return None
    point = statistic(table)
    if not np.isfinite(point):
        return None
    rng = np.random.default_rng(cfg["seed"])
    draws = []
    for _ in range(cfg["replicates"]):
        value = statistic(table.iloc[block_sample_indices(n, block, rng)])
        if not np.isfinite(value):
            return None
        draws.append(value)
    tail = cfg["twoSidedTail"]
    return {"estimate": float(point), "lower": float(np.quantile(draws, tail)),
            "upper": float(np.quantile(draws, 1 - tail)), "dates": n,
            "nonoverlapBlockFloor": n // block, "blockDates": block}


def _mean_of(name):
    def statistic(table):
        values = table[name].to_numpy(float)
        return float(values.mean()) if np.isfinite(values).all() else np.nan
    return statistic


def predictive_evidence(daily, spec):
    """A (absolute usefulness), B (direction), C (probability calibration), E."""
    gates = spec["evidenceGates"]
    intervals = {name: block_interval(daily, _mean_of(name), spec) for name in QUALITY_METRICS}
    intervals["ece"] = block_interval(daily, pooled_ece, spec)
    intervals["absoluteSlope"] = block_interval(daily, absolute_slope, spec)
    disclosed = {name: block_interval(daily, _mean_of(name), spec)
                 for name in ("expectedReturnBias", "probabilityBias", "perDateEce")}
    if any(v is None for v in intervals.values()):
        return {"status": "DATA_INSUFFICIENT", "intervals": intervals}
    annual = daily.assign(year=pd.to_datetime(daily.date).dt.year).groupby("year")[
        ["rankIC", "brierImprovement", "mseImprovement"]].mean()
    if len(annual) < gates["minimumEvaluationFolds"]:
        return {"status": "DATA_INSUFFICIENT", "reason": "too few annual folds", "intervals": intervals}
    positive = float((annual > 0).all(axis=1).mean())
    quality = (all(intervals[k]["lower"] > 0 for k in QUALITY_METRICS + ("absoluteSlope",))
               and intervals["ece"]["upper"] <= gates["maxEce"])
    stable = positive >= gates["positiveFoldFraction"]
    return {"status": "MEASURED", "quality": bool(quality), "stable": bool(stable),
            "positiveFoldFraction": positive, "intervals": intervals,
            "disclosedBias": disclosed}


# --------------------------------------------------------------------------- #
# Opportunity evidence (D) — the benchmark outside option
# --------------------------------------------------------------------------- #
def opportunity_date(group, *, unvouched_share, spec):
    """Realised net alpha of the ACTIVE set against 0 and against non-active names.

    A candidate-date diagnostic: names are averaged equally only to summarise
    the date, which is not a weighting a portfolio would use and implies no
    position size. A date with no active name is a NO_ACTIVE_OPPORTUNITY date:
    the capital stayed in the benchmark, and that date contributes a count,
    not a fictitious return.
    """
    cfg = spec["survivorship"]
    net = group.forwardRelativeReturn - group.roundTripCost
    active = group.activeOpportunity.eq(True).to_numpy()
    row = {"activeCount": int(active.sum()), "tradableNames": len(group)}
    multiples = spec["costStress"]["multiples"]
    if not active.any():
        return {**row, "state": "NO_ACTIVE_OPPORTUNITY", "activeNet": np.nan,
                "spreadOverNonActive": np.nan, "stressedActiveNet": np.nan,
                **{f"activeNetCostX{m:g}": np.nan for m in multiples}}
    active_net = float(net[active].mean())
    # Disclosure only (never gated): the same active set charged m round trips.
    row.update({f"activeNetCostX{m:g}": float((group.forwardRelativeReturn - m * group.roundTripCost)[active].mean())
                for m in multiples})
    spread = float(active_net - net[~active].mean()) if (~active).any() else np.nan
    tail = worst_plausible(group.forwardRelativeReturn, quantile=cfg["worstPlausibleQuantile"],
                           minimum_names=cfg["minimumTailCrossSection"])
    stressed = np.nan
    if tail is not None and np.isfinite(unvouched_share):
        g = min(1.0, max(0.0, cfg["stressScale"] * unvouched_share))
        stressed = float((1 - g) * active_net + g * (tail - float(group.roundTripCost.mean())))
    return {**row, "state": "ACTIVE_OPPORTUNITIES", "activeNet": active_net,
            "spreadOverNonActive": spread, "stressedActiveNet": stressed}


def opportunity_evidence(table, spec):
    """Full-calendar block bootstrap; conditional means over active dates only.

    Zero-active dates stay in the resampled calendar (so how often the model
    finds anything is resampled with it) but contribute no return. Every
    lower bound must exceed the outside option's 0, the point estimate must
    be positive in both chronological halves, and at least
    `minimumActiveDates` dates must carry an active opportunity.
    """
    cfg, gates = spec["inference"], spec["evidenceGates"]
    table = table.sort_values("date").reset_index(drop=True)
    active = table.state.eq("ACTIVE_OPPORTUNITIES").to_numpy()
    summary = {"evaluationDates": len(table), "activeDates": int(active.sum()),
               "noActiveOpportunityDates": int((~active).sum())}
    if len(table) < cfg["blockDates"] * cfg["minimumEvaluationBlocks"]:
        return {**summary, "evidence": None, "reason": "TOO_FEW_DATE_BLOCKS"}
    if active.sum() < gates["minimumActiveDates"]:
        return {**summary, "evidence": False, "reason": "TOO_FEW_ACTIVE_OPPORTUNITY_DATES"}
    keys = ("activeNet", "spreadOverNonActive", "stressedActiveNet")
    for key in keys:
        if not np.isfinite(table.loc[active, key]).all():
            return {**summary, "evidence": None, "reason": "UNMEASURABLE_" + key}
    rng = np.random.default_rng(cfg["seed"])
    draws = {key: [] for key in keys}
    for _ in range(cfg["replicates"]):
        idx = block_sample_indices(len(table), cfg["blockDates"], rng)
        chosen = idx[active[idx]]
        if not len(chosen):
            return {**summary, "evidence": None, "reason": "EMPTY_RESAMPLED_ACTIVE_SET"}
        for key in keys:
            draws[key].append(float(table[key].iloc[chosen].mean()))
    tail = cfg["twoSidedTail"]
    intervals = {key: {"estimate": float(table.loc[active, key].mean()),
                       "lower": float(np.quantile(vals, tail)),
                       "upper": float(np.quantile(vals, 1 - tail))}
                 for key, vals in draws.items()}
    half = len(table) // 2
    halves = []
    for part in (table.iloc[:half], table.iloc[half:]):
        chosen = part.state.eq("ACTIVE_OPPORTUNITIES")
        halves.append(float(part.loc[chosen, "activeNet"].mean()) if chosen.any() else None)
    halves_ok = all(h is not None and h > 0 for h in halves)
    evidence = all(intervals[k]["lower"] > 0 for k in keys) and halves_ok
    disclosed = {key: float(table.loc[active, key].mean())
                 for key in table.columns if key.startswith("activeNetCostX")}
    return {**summary, "evidence": bool(evidence), "intervals": intervals,
            "halvesActiveNet": halves, "halvesPositive": bool(halves_ok),
            "costStressDisclosureNotGated": disclosed, "portfolioReturn": None}


# --------------------------------------------------------------------------- #
# Verdict
# --------------------------------------------------------------------------- #
PRIORITY = ("PIT_INVALID", "MODEL_UNSTABLE", "DATA_INSUFFICIENT", "OPPORTUNITY_EVIDENCE",
            "PREDICTIVE_EVIDENCE_BENCHMARK_PREFERRED", "NO_MODEL_EVIDENCE")


def verdict(per_treatment, *, pit_valid=True, numerically_stable=True):
    """Conjunctive across endpoint treatments; integrity outranks any metric.

    ``per_treatment`` maps each registered treatment to
    {"predictive": predictive_evidence(...), "opportunity": opportunity_evidence(...)}.
    """
    if not pit_valid:
        return {"verdict": "PIT_INVALID", "promotionEligible": False}
    if not numerically_stable:
        return {"verdict": "MODEL_UNSTABLE", "reason": "numerical", "promotionEligible": False}
    if set(per_treatment) != set(TREATMENTS):
        return {"verdict": "DATA_INSUFFICIENT", "reason": "treatment missing", "promotionEligible": False}
    predictive = [per_treatment[t]["predictive"] for t in TREATMENTS]
    opportunity = [per_treatment[t]["opportunity"] for t in TREATMENTS]
    if any(p.get("status") != "MEASURED" for p in predictive):
        return {"verdict": "DATA_INSUFFICIENT", "reason": "predictive intervals", "promotionEligible": False}
    quality = all(p["quality"] for p in predictive)
    stable = all(p["stable"] for p in predictive)
    if quality and not stable:
        return {"verdict": "MODEL_UNSTABLE", "reason": "chronological", "promotionEligible": False}
    if not quality:
        return {"verdict": "NO_MODEL_EVIDENCE", "promotionEligible": False}
    if any(o.get("evidence") is None for o in opportunity):
        return {"verdict": "DATA_INSUFFICIENT", "reason": "opportunity gate unevaluable",
                "promotionEligible": False}
    if all(o["evidence"] for o in opportunity):
        return {"verdict": "OPPORTUNITY_EVIDENCE", "promotionEligible": False}
    return {"verdict": "PREDICTIVE_EVIDENCE_BENCHMARK_PREFERRED", "promotionEligible": False}


def calendar_depth(eligible_dates_by_year, spec):
    """Outcome-free upper bound on evaluable dates/folds before labels exist."""
    wf, cfg, gates = spec["walkForward"], spec["inference"], spec["evidenceGates"]
    first = int(wf["featureStart"][:4]) + math.ceil(wf["minimumHistoryMonths"] / 12)
    counts = {str(y): int(n) for y, n in eligible_dates_by_year.items()}
    years = sorted(int(y) for y, n in counts.items() if n and int(y) >= first)
    dates = int(sum(counts[str(y)] for y in years))
    ok = len(years) >= gates["minimumEvaluationFolds"] and dates >= cfg["blockDates"] * cfg["minimumEvaluationBlocks"]
    return {"evaluationYearsUpperBound": len(years), "evaluationDatesUpperBound": dates,
            "status": "SUFFICIENT_UPPER_BOUND" if ok else "BLOCKED_BY_SAMPLE_DEPTH"}


def evaluate_cell(cell, folds, failures, unvouched_by_date, spec, *, region, horizon):
    """Verdict for one region x horizon LINEAR cell from its OOF predictions.

    ``cell`` holds LINEAR predictions only (the challenger never decides).
    Pending dates are removed by calendar; every remaining evaluation date must
    be MEASURED under both endpoint treatments or the cell is DATA_INSUFFICIENT.
    """
    base = {"region": region, "horizon": horizon, "family": "LINEAR", "promotionEligible": False}
    unstable = any(f.get("family") == "LINEAR" for f in failures)
    gap = [f for f in folds if f["evaluation"] and f["status"] != "READY"]
    if cell is None or cell.empty or gap or not any(f["evaluation"] for f in folds):
        return {**base, "verdict": "MODEL_UNSTABLE" if unstable else "DATA_INSUFFICIENT",
                "reason": "fold schedule"}
    cell = cell.loc[pd.to_datetime(cell.outcomeEndDate) <= pd.Timestamp(spec["dataCutoff"])]
    per_treatment, incomplete = {}, []
    for treatment in TREATMENTS:
        daily, opp = [], []
        for date, group in cell.groupby("date", sort=True):
            treated, status = apply_treatment(group, treatment, spec)
            if status != "MEASURED":
                incomplete.append({"date": date, "treatment": treatment, "status": status})
                continue
            daily.append({"date": date, **date_summary(treated)})
            opp.append({"date": date, **opportunity_date(
                treated, unvouched_share=unvouched_by_date.get((region, date), np.nan), spec=spec)})
        per_treatment[treatment] = {
            "predictive": predictive_evidence(pd.DataFrame(daily), spec) if daily else {"status": "DATA_INSUFFICIENT"},
            "opportunity": opportunity_evidence(pd.DataFrame(opp), spec) if opp else {"evidence": None}}
    decision = verdict(per_treatment, numerically_stable=not unstable)
    if incomplete and decision["verdict"] not in ("PIT_INVALID", "MODEL_UNSTABLE"):
        decision = {"verdict": "DATA_INSUFFICIENT", "reason": "incomplete evaluation dates",
                    "promotionEligible": False}
    return {**base, **decision, "incompleteDates": incomplete, "evidence": per_treatment,
            "classCounts": {str(k): int(v) for k, v in cell.opportunityClass.value_counts().items()}}
