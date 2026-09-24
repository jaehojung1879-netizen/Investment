"""Predeclared dependence-aware model evidence, not a portfolio backtest."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from .alpha_opportunity_model import block_sample_indices


def daily_metrics(frame):
    rows = []
    for date, group in frame.groupby("date", sort=True):
        # Never silently drop unpriced members and report survivors as the universe.
        if not group.labelStatus.eq("MATURED").all() or len(group) < 10:
            rows.append({"date": date, "status": "INCOMPLETE_DATE"})
            continue
        y = group.forwardRelativeReturn.to_numpy(float)
        z = group.beatBenchmark.to_numpy(float)
        p = group.probability.to_numpy(float)
        mu = group.expectedRelativeReturn.to_numpy(float)
        b = group.trainingBaseRate.to_numpy(float)
        m = group.trainingMeanReturn.to_numpy(float)
        if not np.isfinite(np.column_stack((y, z, p, mu, b, m))).all():
            raise ValueError("MODEL_UNSTABLE_NONFINITE")
        if ((p < 0) | (p > 1)).any():
            raise ValueError("INVALID_PROBABILITY")
        p, b = np.clip(p, 1e-12, 1-1e-12), np.clip(b, 1e-12, 1-1e-12)
        loss = lambda v: -(z*np.log(v)+(1-z)*np.log(1-v))
        ic = float(spearmanr(mu, y).statistic) if np.ptp(mu) > 0 and np.ptp(y) > 0 else np.nan
        variance = np.var(mu)
        slope = float(np.mean((mu-mu.mean())*(y-y.mean())) / variance) if variance > 0 else np.nan
        bins = np.minimum((p*10).astype(int), 9)
        ece = sum(np.mean(bins == j) * abs(p[bins == j].mean()-z[bins == j].mean())
                  for j in range(10) if np.any(bins == j))
        rows.append({"date": date, "status": "MEASURED", "rankIC": ic,
                     "brierImprovement": float(np.mean((b-z)**2-(p-z)**2)),
                     "logLossImprovement": float(np.mean(loss(b)-loss(p))),
                     "mseImprovement": float(np.mean((m-y)**2-(mu-y)**2)),
                     "returnSlope": slope, "expectedReturnBias": float(np.mean(mu-y)),
                     "ece": float(ece), "probabilityBias": float(np.mean(p-z)),
                     "names": len(group)})
    return pd.DataFrame(rows)


def block_interval(values, spec):
    values = np.asarray(values, float)
    if not np.isfinite(values).all():
        return None
    cfg = spec["inference"]
    n, block = len(values), cfg["blockDates"]
    if n < cfg["minimumEvaluationBlocks"] * block:
        return None
    rng = np.random.default_rng(cfg["seed"])
    draws = [values[block_sample_indices(n, block, rng)].mean() for _ in range(cfg["replicates"])]
    tail = cfg["twoSidedTail"]
    return {"mean": float(values.mean()), "lower": float(np.quantile(draws, tail)),
            "upper": float(np.quantile(draws, 1-tail)), "dates": n,
            "nonoverlapBlockFloor": n//block, "blockDates": block}


def verdict(daily, spec, *, pit_valid, opportunity_evidence=None, convergence_ok=True):
    """Precedence prevents a lucky metric overriding an integrity failure."""
    if not pit_valid:
        return {"verdict": "PIT_INVALID"}
    if not convergence_ok:
        return {"verdict": "MODEL_UNSTABLE"}
    if daily.empty or not daily.status.eq("MEASURED").all():
        return {"verdict": "DATA_INSUFFICIENT", "reason": "incomplete scheduled cross-section"}
    metrics = ["rankIC", "brierImprovement", "logLossImprovement", "mseImprovement", "returnSlope", "ece"]
    intervals = {name: block_interval(daily[name], spec) for name in metrics}
    if any(v is None for v in intervals.values()):
        return {"verdict": "DATA_INSUFFICIENT", "intervals": intervals}
    years = pd.to_datetime(daily.date).dt.year
    annual = daily.assign(year=years).groupby("year")[metrics].mean()
    if len(annual) < spec["evidenceGates"]["minimumEvaluationFolds"]:
        return {"verdict": "DATA_INSUFFICIENT", "reason": "too few annual folds"}
    positive = (annual[["rankIC", "brierImprovement", "mseImprovement"]] > 0).all(axis=1)
    stable = float(positive.mean()) >= spec["evidenceGates"]["positiveFoldFraction"]
    quality = all(intervals[k]["lower"] > 0 for k in metrics if k != "ece")
    quality = quality and intervals["ece"]["upper"] <= spec["evidenceGates"]["maxEce"]
    if opportunity_evidence is None:
        status = "DATA_INSUFFICIENT"
    elif quality and not stable:
        status = "MODEL_UNSTABLE"
    elif quality and stable and opportunity_evidence is True:
        status = "MODEL_EVIDENCE"
    else:
        status = "NO_MODEL_EVIDENCE"
    return {"verdict": status, "predictiveEvidence": bool(quality and stable),
            "opportunityEvidence": opportunity_evidence, "intervals": intervals,
            "positiveFoldFraction": float(positive.mean()), "promotionEligible": False}


def overlay_sample_gate(*, training_dates, evaluation_dates, events, issuers, spec):
    cfg = spec["ownershipOverlay"]
    enough = (training_dates >= cfg["minimumTrainingDates"]
              and evaluation_dates >= cfg["minimumEvaluationDates"]
              and events >= cfg["minimumDistinctReceipts"] and issuers >= cfg["minimumIssuers"])
    return {"verdict": "ELIGIBLE_FOR_EXPERIMENTAL_TEST" if enough else "DATA_INSUFFICIENT",
            "promotionEligible": False, "trainingDates": training_dates,
            "evaluationDates": evaluation_dates, "events": events, "issuers": issuers}


def selected_opportunity_evidence(frame, spec):
    """Candidate-date diagnostics only. No position sizes, NAV or equity curve."""
    rows = []
    for date, group in frame.groupby("date", sort=True):
        if group.gateStatus.ne("EVALUATED").any():
            rows.append({"date": date, "status": "UNEVALUABLE"})
            continue
        selected = group.loc[group.passesOpportunity.eq(True)]
        if selected.empty:
            rows.append({"date": date, "status": "ZERO_OPPORTUNITIES", "count": 0})
            continue
        if not group.labelStatus.eq("MATURED").all():
            rows.append({"date": date, "status": "MISSING_LABEL", "count": len(selected)})
            continue
        net = selected.forwardRelativeReturn - selected.roundTripCost - spec["investability"]["slippageBps"]/10000
        rows.append({"date": date, "status": "MEASURED", "count": len(selected),
                     "netAdvantage": float(net.mean()),
                     "selectionBeyondUniverse": float(selected.forwardRelativeReturn.mean()-group.forwardRelativeReturn.mean())})
    if not rows:
        return {"evidence": None, "reason": "NO_DATES"}
    table = pd.DataFrame(rows)
    if table.status.eq("ZERO_OPPORTUNITIES").all():
        return {"evidence": False, "zeroOpportunityDates": len(table), "rows": rows}
    if table.status.isin(["UNEVALUABLE", "MISSING_LABEL"]).any():
        return {"evidence": None, "reason": "GATE_OR_LABEL_UNAVAILABLE", "rows": rows}
    # Bootstrap the FULL regular date grid. Numerator and denominator resample
    # together; empty selection dates remain zero count, not a false 0% return.
    cfg = spec["inference"]
    if len(table) < cfg["blockDates"]*cfg["minimumEvaluationBlocks"]:
        return {"evidence": None, "reason": "TOO_FEW_DATE_BLOCKS", "rows": rows}
    observed = table.status.eq("MEASURED").to_numpy()
    if observed.sum() < spec["evidenceGates"]["minimumSelectedDates"]:
        return {"evidence": None, "reason": "TOO_FEW_SELECTED_DATES", "rows": rows}
    rng = np.random.default_rng(cfg["seed"])
    estimates = {"netAdvantage": [], "selectionBeyondUniverse": []}
    for _ in range(cfg["replicates"]):
        idx = block_sample_indices(len(table), cfg["blockDates"], rng)
        valid = idx[observed[idx]]
        if not len(valid):
            return {"evidence": None, "reason": "EMPTY_RESAMPLED_SELECTION", "rows": rows}
        for key in estimates:
            estimates[key].append(float(table[key].iloc[valid].mean()))
    lower = {key: float(np.quantile(vals, cfg["twoSidedTail"])) for key, vals in estimates.items()}
    return {"evidence": bool(lower["netAdvantage"] > spec["investability"]["minimumEdge"]
                             and lower["selectionBeyondUniverse"] > 0),
            "lowerBounds": lower, "rows": rows, "portfolioReturn": None}


def candidate_churn(frame):
    """Membership changes, not traded turnover or an implied portfolio size."""
    rows, previous = [], None
    for date, group in frame.groupby("date", sort=True):
        if group.gateStatus.ne("EVALUATED").any():
            previous = None
            rows.append({"date": date, "status": "UNEVALUABLE"})
            continue
        current = set(group.loc[group.passesOpportunity.eq(True), "ticker"])
        rows.append({"date": date, "count": len(current),
                     "entrantFraction": len(current-previous)/len(current) if previous is not None and current else None,
                     "exitFraction": len(previous-current)/len(previous) if previous else None})
        previous = current
    return rows


def family_disagreement(frame):
    """Date-balanced diagnostic only. Does not crown a winner or use outcomes."""
    ids = ["region", "horizon", "date", "ticker"]
    left = frame.loc[frame.family.eq("LINEAR")]
    right = frame.loc[frame.family.eq("SHALLOW_CHALLENGER")]
    pairs = left.merge(right, on=ids, suffixes=("_linear", "_challenger"), validate="one_to_one")
    if pairs.empty:
        return None
    pairs["probabilityDifference"] = abs(pairs.probability_linear-pairs.probability_challenger)
    pairs["meanDifference"] = abs(pairs.expectedRelativeReturn_linear-pairs.expectedRelativeReturn_challenger)
    pairs["directionDisagreement"] = np.sign(pairs.expectedRelativeReturn_linear).ne(np.sign(pairs.expectedRelativeReturn_challenger)).astype(float)
    cols = ["probabilityDifference", "meanDifference", "directionDisagreement"]
    return {k: float(v) for k, v in pairs.groupby("date")[cols].mean().mean().items()}
