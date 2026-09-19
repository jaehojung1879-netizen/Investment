"""Research-only benchmark-relative, turnover-aware stock-selection challenger.

The experiment changes neither the production selector nor the sealed replay.
It asks the narrower economic question the live strategy ultimately has to
answer: after realistic implementation costs, did selecting individual names
beat holding their regional total-return benchmarks?
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from types import MappingProxyType

import pandas as pd

from . import kelly_portfolio as KP
from . import portfolio_validation as PV


VERSION = "benchmark-relative-alpha-v1"
METHOD = "COST_AWARE_EXPECTED_BENCHMARK_EXCESS_QUARTERLY"

# A transparent retail-size base case, kept out of production config.  The
# Korean sell tax is date-aware because applying today's lower rate to 2013 is
# not a realistic historical replay.  Commissions and spreads are deliberately
# non-zero even where a broker advertises zero commission: spread and routing
# friction do not disappear.  Values are full-spread bps and per-side
# commission bps.  US regulatory fees are conservatively represented inside
# sellTaxBps; their small historical variation is immaterial next to turnover.
REALISTIC_COSTS = MappingProxyType({
    "US": MappingProxyType({
        "commissionBps": 5.0,
        "spreadBps": 6.0,
        "sellTaxBps": 0.30,
        "expectedTradeNotionalKrw": 10_000_000,
    }),
    "KR": MappingProxyType({
        "commissionBps": 1.5,
        "spreadBps": 8.0,
        "sellTaxBps": 20.0,
        "sellTaxSchedule": (
            MappingProxyType({"effectiveDate": "1900-01-01", "sellTaxBps": 30.0}),
            MappingProxyType({"effectiveDate": "2019-06-03", "sellTaxBps": 25.0}),
            MappingProxyType({"effectiveDate": "2021-01-01", "sellTaxBps": 23.0}),
            MappingProxyType({"effectiveDate": "2023-01-01", "sellTaxBps": 20.0}),
            MappingProxyType({"effectiveDate": "2024-01-01", "sellTaxBps": 18.0}),
            MappingProxyType({"effectiveDate": "2025-01-01", "sellTaxBps": 15.0}),
            MappingProxyType({"effectiveDate": "2026-01-01", "sellTaxBps": 20.0}),
        ),
        "expectedTradeNotionalKrw": 10_000_000,
    }),
})


def cost_config(cfg_pf: dict) -> dict:
    """Copy portfolio constraints and replace only research cost assumptions."""
    out = deepcopy(cfg_pf)
    out["transactionCosts"] = {
        region: {key: ([dict(item) for item in value] if key == "sellTaxSchedule" else value)
                 for key, value in dict(policy).items()}
        for region, policy in REALISTIC_COSTS.items()
    }
    return out


def freeze_manifest() -> dict:
    return {
        "id": VERSION,
        "status": "CHALLENGER",
        "selector": METHOD,
        "score": "POSITIVE_SHRUNK_MATURED_GROSS_REGIONAL_BENCHMARK_EXCESS_MINUS_ROUND_TRIP_COST_PER_DOWNSIDE_RISK",
        "decisionCadence": "FIRST_FIXED_21D_EVALUATION_ANCHOR_PER_CALENDAR_QUARTER",
        "betweenDecisions": "HOLD_DRIFTED_TERMINAL_WEIGHTS_NO_MONTHLY_REBALANCE",
        "incumbencyRule": "RETAINING_AN_INCUMBENT_RECEIVES_ONLY_THE_IMMEDIATE_SELL_PLUS_REPLACEMENT_BUY_COST_AVOIDED",
        "maturityRule": "OUTCOME_END_DATE_LTE_SIGNAL_DATE",
        "positiveAlphaGate": True,
        "costPolicy": {region: {
            key: ([dict(item) for item in value] if key == "sellTaxSchedule" else value)
            for key, value in dict(policy).items()}
            for region, policy in REALISTIC_COSTS.items()},
        "promotionEligible": False,
        "liveValidated": False,
        "prospectiveStatus": "NOT_YET_COLLECTED",
    }


def _round_trip_cost_pct(region: str, as_of: str, cfg_pf: dict) -> float:
    policy = PV._dated_cost_policy(
        ((cfg_pf.get("transactionCosts") or {}).get(region) or {}), as_of)
    # bps -> percentage points.  Full spread is crossed half on each leg.
    bps = (2 * float(policy.get("commissionBps", 0))
           + float(policy.get("spreadBps", 0))
           + float(policy.get("sellTaxBps", 0)))
    return bps / 100.0


def challenger_scores(candidates: list[dict], calibration: PV.ExpandingBucketCalibration,
                      cfg_pf: dict, *, as_of: str,
                      incumbents: set[str] | None = None) -> list[dict]:
    """Score only positive net benchmark alpha; reward holding, never churning.

    The retention credit is not an alpha forecast.  It is the immediate
    round-trip friction avoided by not selling an incumbent and buying its
    replacement.  It affects ordering only; the positive-alpha eligibility
    gate is applied before that credit, so a bad incumbent cannot survive by
    hiding behind transaction costs.
    """
    incumbents = incumbents or set()
    rows = []
    for candidate in candidates:
        region = candidate.get("region") or "UNKNOWN"
        estimate = calibration.expected(region, candidate.get("alphaPercentile"))
        gross_alpha = (estimate or {}).get("expectedExcessReturnPct")
        risk = KP._risk_unit(candidate)
        state = KP._state_multiplier(candidate, cfg_pf)
        trading_cost = _round_trip_cost_pct(region, as_of, cfg_pf)
        net_alpha = (float(gross_alpha) - trading_cost
                     if gross_alpha is not None else None)
        incumbent = candidate.get("ticker") in incumbents
        retention_credit = trading_cost if incumbent else 0.0
        decision_alpha = ((net_alpha + retention_credit)
                          if net_alpha is not None else None)
        excluded = []
        if estimate is None:
            excluded.append("MATURED_CALIBRATION_NOT_READY")
        if risk is None or risk <= 0:
            excluded.append("DOWNSIDE_RISK_UNAVAILABLE")
        if state <= 0:
            excluded.append("ENTRY_OR_RESEARCH_STATE_BLOCKS_SIZING")
        if net_alpha is not None and net_alpha <= 0:
            excluded.append("EXPECTED_NET_BENCHMARK_ALPHA_NOT_POSITIVE")
        score = (decision_alpha / (risk * 100) * state
                 if decision_alpha is not None and risk and risk > 0 else -1e12)
        rows.append({
            "ticker": candidate["ticker"], "region": region,
            "sector": candidate.get("sector") or "Unclassified",
            "score": score, "convictionScore": score,
            "alphaPercentile": candidate.get("alphaPercentile"),
            "downsideVolPct": risk * 100 if risk else None,
            "evidenceCoverage": candidate.get("evidenceCoverage"),
            "expectedGrossBenchmarkExcessPct": gross_alpha,
            "estimatedRoundTripCostPct": trading_cost,
            "expectedNetBenchmarkExcessPct": net_alpha,
            "incumbent": incumbent,
            "retentionCreditPct": retention_credit,
            "decisionAlphaPct": decision_alpha,
            "eligible": not excluded, "exclusionCodes": excluded,
            "calibration": estimate,
        })
    return rows


def _contexts(signals: list[dict], cfg_lt: dict) -> dict[str, tuple[list[dict], dict]]:
    by_date: dict[str, list[dict]] = defaultdict(list)
    for row in signals:
        if row.get("date"):
            by_date[row["date"]].append(row)
    prior_research: dict[str, set[str]] = {}
    contexts = {}
    for date in sorted(by_date):
        rows = by_date[date]
        candidates = PV._research_candidates(rows, cfg_lt, prior_research, price_proxy=True)
        label = next((r.get("macroRegime") for r in rows if r.get("macroRegime")), None)
        confidence = next((PV._finite(r.get("macroConfidence")) for r in rows
                           if PV._finite(r.get("macroConfidence")) is not None), None)
        contexts[date] = (candidates, {"regime": label, "confidence": confidence})
    return contexts


def run_challenger(signals: list[dict], outcomes: list[dict], *, cfg_lt: dict,
                   cfg_pf: dict, calendar: list[dict], valuation) -> dict:
    """Sequentially value the quarterly challenger on the fixed 21D calendar."""
    research_cfg = cost_config(cfg_pf)
    contexts = _contexts(signals, cfg_lt)
    calibrator = PV.ExpandingBucketCalibration(
        outcomes, horizon=int(cfg_pf.get("horizonDays", 126)),
        prior_strength=float(cfg_pf.get("shrinkagePriorStrength", 30)),
        min_dates=20, cost_adjusted=False)
    rows, decisions, failures = [], [], []
    terminal_weights: dict[str, float] = {}
    terminal_regions: dict[str, str] = {}
    last_quarter = None

    for block in calendar:
        signal_date = block["signalDate"]
        calibrator.advance(signal_date)
        context = contexts.get(signal_date)
        quarter = (pd.Timestamp(block["date"]).year, pd.Timestamp(block["date"]).quarter)
        rebalance = quarter != last_quarter
        if rebalance:
            last_quarter = quarter
            candidates, macro = context if context is not None else ([], {})
            scores = challenger_scores(
                candidates, calibrator, research_cfg, as_of=block["date"],
                incumbents=set(terminal_weights))
            allocation = KP.selection_and_baseline(
                candidates, research_cfg, macro, scored=scores, method=METHOD)
            weights = allocation["weights"]
            selected = {c["ticker"]: c for c in allocation["selected"]}
            regions = {ticker: selected[ticker].get("region") for ticker in weights}
            audit_scores = sorted(scores, key=lambda r: (-float(r["score"]), str(r["ticker"])))
        else:
            # Carry actual drifted weights.  Re-targeting yesterday's names to
            # fresh inverse-vol weights here would still be a monthly trade.
            weights = dict(terminal_weights)
            regions = dict(terminal_regions)
            audit_scores = []
        decision = {
            "date": block["date"], "replayDate": signal_date, "selector": METHOD,
            "weights": weights, "regionByTicker": regions,
            "cashPct": (1 - sum(weights.values())) * 100,
            "rebalanceDecision": rebalance,
            "selectedTickers": list(weights),
        }
        outcome, diagnostic = valuation.window(decision, block)
        decisions.append({
            "date": block["date"], "signalDate": signal_date,
            "rebalanceDecision": rebalance, "weights": weights,
            "selectedTickers": list(weights),
            "topScores": audit_scores[:12], "valuationStatus": diagnostic["status"],
        })
        if outcome is None:
            failures.append({**block, **diagnostic})
            continue
        rows.append(outcome)
        terminal_weights = dict(outcome.get("terminalWeights") or {})
        terminal_regions = dict(outcome.get("terminalRegionByTicker") or {})

    expected = [b for b in calendar if b["endDate"] <= valuation.through]
    complete = len(rows) == len(expected)
    summary = (PV._path_metrics(deepcopy(rows), PV.HEADLINE_HORIZON, research_cfg,
                                only_dates=[r["date"] for r in rows])
               if complete else {"available": False,
                                  "reason": "continuous_nav_has_unknown_intervals"})
    return {
        "method": METHOD, "rows": rows, "decisions": decisions,
        "summary": summary, "complete": complete,
        "expectedBlocks": len(expected), "measuredBlocks": len(rows),
        "failures": failures, "freezeManifest": freeze_manifest(),
    }


def reprice(rows: list[dict], cfg_pf: dict) -> dict:
    """Recalculate an existing path under the same realistic cost semantics."""
    copied = deepcopy(rows)
    return PV._path_metrics(copied, PV.HEADLINE_HORIZON, cost_config(cfg_pf),
                            only_dates=[row["date"] for row in copied])

