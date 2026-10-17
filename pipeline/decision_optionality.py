"""Synthetic-only decision adapter; production selection/costs are imported.

No loader, model, receipt writer, historical executor or promotion path. Forecasts
are supplied independently of discovery scores. Missing remaining alpha is never
manufactured from a purchase-date calibration or an elapsed holding period.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
import math

import pandas as pd

from . import experiment_workbench as EW
from . import industry_foundation as IF
from . import kelly_portfolio as KP
from . import prospective_receipt_core as CORE
from . import replay_calendar as RC
from . import weekly_decision as W

VERSION = "decision-optionality-v1"
POLICIES = ("ETF", "CURRENT", "FORCED_FIVE", "NO_CREDIT", "SYMMETRIC", "ASYMMETRIC", "EVENT_ONLY")
ACTIONS = ("WAIT_ETF", "BUY", "HOLD", "REDUCE", "EXIT", "REPLACE")
ECONOMIC_EXCLUSION = "EXPECTED_NET_ADVANTAGE_NOT_POSITIVE"


def _synthetic(scope):
    if scope != "SYNTHETIC":
        raise ValueError("HISTORICAL_DECISION_EXECUTION_NOT_AUTHORIZED")


@dataclass(frozen=True)
class RemainingForecast:
    key: EW.Key
    expected_excess_pct: float | None
    radius_pct: float | None
    available_at: str
    source: EW.Source
    thesis_valid: bool | None
    missing_reason: str | None = None
    horizon_sessions: int = W.EDGE_HORIZON_SESSIONS

    def __post_init__(self):
        if not isinstance(self.key, EW.Key) or not isinstance(self.source, EW.Source):
            raise ValueError("FORECAST_PROVENANCE_REQUIRED")
        CORE.utc(self.available_at)
        if self.horizon_sessions != W.EDGE_HORIZON_SESSIONS:
            raise ValueError("COMMON_FORWARD_HORIZON_REQUIRED")
        missing = self.expected_excess_pct is None or self.radius_pct is None
        if missing and not self.missing_reason:
            raise ValueError("FORECAST_ABSENCE_REASON_REQUIRED")
        if not missing and self.missing_reason is not None:
            raise ValueError("FORECAST_ABSENCE_CONFLICT")
        for value in (self.expected_excess_pct, self.radius_pct):
            if value is not None and not CORE.finite(value):
                raise ValueError("INVALID_FORECAST")
        if self.radius_pct is not None and self.radius_pct < 0:
            raise ValueError("NEGATIVE_UNCERTAINTY_RADIUS")
        if self.thesis_valid is not None and type(self.thesis_valid) is not bool:
            raise ValueError("INVALID_THESIS_STATE")

    @property
    def usable(self):
        return self.expected_excess_pct is not None and self.radius_pct is not None


@dataclass(frozen=True)
class Frame:
    market: str
    signal_date: str
    decision_at: str
    observations: tuple[EW.Observation, ...]
    candidates: tuple[dict, ...]
    calibration: dict | None
    before: dict[str, float]  # actual drifted weights; ETF included; {} = initial funding
    forecasts: tuple[RemainingForecast, ...] = ()


def _validate(frame):
    if frame.market not in W.BENCHMARKS:
        raise ValueError("UNKNOWN_MARKET")
    IF.day(frame.signal_date)
    at = CORE.utc(frame.decision_at)
    if (W.last_completed_session(frame.market, at.to_pydatetime()) != frame.signal_date
            or not W.is_week_end_session(frame.market, frame.signal_date)):
        raise ValueError("COMPLETED_OWN_MARKET_WEEK_REQUIRED")
    benchmark = W.BENCHMARKS[frame.market]
    names = [c["ticker"] for c in frame.candidates]
    observed = {o.ticker: o for o in frame.observations}
    required = set(names) | (set(frame.before) - {benchmark})
    if len(names) != len(set(names)) or len(observed) != len(frame.observations):
        raise ValueError("DUPLICATE_SECURITY")
    if set(observed) != required:
        raise ValueError("OBSERVATIONS_REQUIRED_FOR_ALL_CANDIDATES_AND_HOLDINGS")
    EW.sample_identity(frame.observations)
    for ticker, o in observed.items():
        if (o.key.market != frame.market or o.key.signal_date != frame.signal_date
                or o.key.security_identity != f"SYN:{ticker}" or not ticker.startswith("SYN")):
            raise ValueError("SYNTHETIC_SECURITY_KEY_REQUIRED")
        if CORE.utc(o.signal_at) > at:
            raise ValueError("INFORMATION_AFTER_DECISION")
    for c in frame.candidates:
        if c.get("region") != frame.market or c.get("sector") != observed[c["ticker"]].industry_id:
            raise ValueError("CANDIDATE_OBSERVATION_MISMATCH")
    if (any(not CORE.finite(v) or v <= 0 or v > 1 for v in frame.before.values())
            or (frame.before and not math.isclose(sum(frame.before.values()), 1, abs_tol=1e-10))
            or len(set(frame.before) - {benchmark}) > W.MAX_NAMES):
        raise ValueError("INVALID_ACTUAL_HOLDINGS")
    forecasts = {}
    for f in frame.forecasts:
        matches = [t for t, o in observed.items() if o.key == f.key]
        if len(matches) != 1 or matches[0] in forecasts:
            raise ValueError("FORECAST_KEY_MISMATCH")
        if CORE.utc(f.available_at) > at:
            raise ValueError("FORECAST_NOT_PUBLIC")
        if f.source.observed_at is None or CORE.utc(f.source.observed_at) > at:
            raise ValueError("SYNTHETIC_FORECAST_NOT_OBSERVED")
        forecasts[matches[0]] = f
    later = RC.sessions(str((pd.Timestamp(frame.signal_date) + pd.Timedelta(days=1)).date()),
                        str((pd.Timestamp(frame.signal_date) + pd.Timedelta(days=21)).date()), frame.market)
    import exchange_calendars as xc
    calendar = xc.get_calendar("XKRX" if frame.market == "KR" else "XNYS", start="1990-01-01", end="2035-12-31")
    if at >= calendar.session_open(later[0]):
        raise ValueError("DECISION_AFTER_NEXT_SESSION_OPEN")
    return benchmark, observed, forecasts, str(later[0].date())


def _select(candidates, scored, policy):
    # KP mutates nested exclusion lists: never give it the caller's audit rows.
    detached = deepcopy(scored)
    selected, meta = KP.select_portfolio_by_scores(
        deepcopy(candidates), detached, deepcopy(W.SELECTION_CFG), method=f"{VERSION}:{policy}")
    # Shared nested lists preserve ALL constraint reasons, outside the top-8 UI window.
    for row, audited in zip(scored, detached):
        row["exclusionCodes"] = list(audited["exclusionCodes"])
    return {c["ticker"]: W.NAME_WEIGHT for c in selected}, meta


def _remaining_audit(enter, leave, forecasts, market, execution, before, target):
    new, old = forecasts.get(enter), forecasts.get(leave)
    if not new or not old or not new.usable or not old.usable:
        return {"available": False, "reason": "REMAINING_ALPHA_OR_UNCERTAINTY_UNAVAILABLE"}
    if not math.isclose(before[leave], target[enter], abs_tol=1e-10):
        return {"available": False, "reason": "UNEQUAL_SWAP_WEIGHTS"}
    cost = 100 * (W.trade_cost_fraction(market, execution, is_benchmark=False, side="sell")
                  + W.trade_cost_fraction(market, execution, is_benchmark=False, side="buy"))
    gap = new.expected_excess_pct - old.expected_excess_pct
    radius = new.radius_pct + old.radius_pct
    return {"available": True, "entrantExpectedExcessPct": new.expected_excess_pct,
            "incumbentRemainingExpectedExcessPct": old.expected_excess_pct,
            "swapCostPct": cost, "uncertaintyRadiusSumPct": radius,
            "marginalNetPct": gap - cost, "conservativeMarginalNetPct": gap - cost - radius,
            "etfOpportunityCost": "ALREADY_IN_BOTH_EXCESS_FORECASTS",
            "capitalGainsTax": None, "capitalGainsTaxReason": "INVESTOR_SPECIFIC_NOT_MEASURED"}


def decide(frame: Frame, policy="CURRENT", *, scope):
    """Return synthetic decisions only. Actual dated fees belong to evaluate()."""
    _synthetic(scope)  # before examining the frame or calling any engine
    if policy not in POLICIES:
        raise ValueError("UNKNOWN_POLICY")
    frame = deepcopy(frame)
    benchmark, observed, forecasts, execution = _validate(frame)
    incumbent = set(frame.before) - {benchmark}
    candidates = list(frame.candidates)
    # Uninvestable / unresolved observations remain on the audit tape, never in the selector.
    barred = {t for t, o in observed.items() if o.investable is not True or o.identity_status != "VERIFIED_SECURITY"
              or o.industry_status == "UNRESOLVED"}
    scored = W.score_candidates(candidates, frame.calibration, frame.market, frame.signal_date, incumbent)
    for row in scored:
        if row["ticker"] in barred:
            row["eligible"] = False
            row["exclusionCodes"].append("OBSERVATION_NOT_INVESTABLE")
    info = {"observations": [asdict(o) for o in sorted(frame.observations, key=lambda o: o.ticker)],
            "candidates": sorted(candidates, key=lambda c: c["ticker"]), "calibration": frame.calibration,
            "forecasts": [asdict(f) for f in sorted(frame.forecasts, key=lambda f: f.key.sample_id)]}
    header = {"version": VERSION, "policy": policy, "dataMode": "synthetic", "recommendation": False,
              "historicalExecutionAuthorized": False, "market": frame.market, "signalDate": frame.signal_date,
              "decisionAt": frame.decision_at, "nextTradingSession": execution,
              "sampleSha256": EW.sample_identity(frame.observations), "informationSha256": IF.digest(info),
              "holdingsSha256": IF.digest(frame.before)}
    if policy in {"SYMMETRIC", "ASYMMETRIC"}:
        missing = [t for t in sorted(observed) if t not in forecasts or not forecasts[t].usable
                   or forecasts[t].thesis_valid is None]
        # Blocked artifacts carry no actionable output, holdings, targets or radar.
        if missing:
            return {**header, "status": "NOT_ESTIMABLE", "reason": "REMAINING_FORECAST_OR_THESIS_UNAVAILABLE",
                    "unmeasuredIdentities": [observed[t].key.sample_id for t in missing]}
    for row in scored:
        ticker = row["ticker"]
        if policy == "NO_CREDIT":
            # Use the exact original candidate risk, not the rounded display risk.
            source = next(c for c in candidates if c["ticker"] == ticker)
            risk = KP._risk_unit(source)
            if risk and risk > 0:
                row["score"] -= row["retentionCreditPct"] / (risk * 100) * KP._state_multiplier(source, {})
                row["convictionScore"] = row["score"]
            row["retentionCreditPct"] = 0.0
        if policy in {"FORCED_FIVE", "SYMMETRIC", "ASYMMETRIC"}:
            codes = [c for c in row["exclusionCodes"] if c != ECONOMIC_EXCLUSION]
            if policy != "FORCED_FIVE":
                f = forecasts[ticker]
                lower = f.expected_excess_pct - f.radius_pct
                exit_cost = 100 * (
                    W.trade_cost_fraction(frame.market, execution, is_benchmark=False, side="sell")
                    + W.trade_cost_fraction(frame.market, execution, is_benchmark=True, side="buy"))
                threshold = -exit_cost if ticker in incumbent and policy == "ASYMMETRIC" else row["switchCostPct"]
                if not f.thesis_valid:
                    codes.append("THESIS_INVALID")
                elif lower <= threshold:
                    codes.append("SIDE_SPECIFIC_ECONOMIC_BOUNDARY")
                row["sideBoundaryPct"] = threshold
                row["remainingLowerPct"] = lower
            row["exclusionCodes"] = codes
            row["eligible"] = not codes
    if policy == "ETF":
        target, meta = {}, {}
    elif policy in {"CURRENT", "EVENT_ONLY"} and not barred:
        # The control is CALLED, never a second reproduction of production.
        control = W.decide(frame.market, candidates, frame.calibration, frame.signal_date, incumbent)
        target, meta = {t: w for t, w in control["weights"].items() if t != benchmark}, {"controlCalled": W.POLICY_VERSION}
        by_ticker = {r["ticker"]: r for r in control["candidates"]}
        for row in scored:
            row["exclusionCodes"] = list(by_ticker[row["ticker"]]["exclusionCodes"])
    else:
        target, meta = _select(candidates, scored, policy)
    target[benchmark] = round(1 - sum(target.values()), 10)
    reason = "CURRENT_TARGET"
    if policy == "EVENT_ONLY" and frame.before and set(target) - {benchmark} == incumbent:
        if all(frame.before[t] <= W.NAME_WEIGHT + 1e-12 for t in incumbent):
            target, reason = dict(frame.before), "NO_NAME_EVENT_CARRY_ACTUAL_WEIGHTS"
        else:
            reason = "CAP_RESTORATION"
    target = {t: w for t, w in target.items() if w > 0}
    exits = sorted(incumbent - set(target))
    entries = sorted(set(target) - {benchmark} - incumbent)
    events = []
    for old, new in zip(exits, entries):
        old_row = next((r for r in scored if r["ticker"] == old), None)
        departure = "POOL_EXIT" if old_row is None else ",".join(old_row["exclusionCodes"]) or "RANK_OR_CONSTRAINT_EXIT"
        events.append({"action": "REPLACE", "from": old, "to": new, "reason": "EXIT_AND_ENTRY_ATTRIBUTION_PAIR",
                       "exitReason": departure, "entryReason": "NEW_ENTRY",
                       "marginalAudit": _remaining_audit(new, old, forecasts, frame.market, execution, frame.before, target)})
    paired = set(exits[:min(len(exits), len(entries))]) | set(entries[:min(len(exits), len(entries))])
    for t in sorted((incumbent | set(target)) - {benchmark} - paired):
        old, new = frame.before.get(t, 0), target.get(t, 0)
        action = "EXIT" if new == 0 else "BUY" if old == 0 or new > old + 1e-12 else "REDUCE" if new < old - 1e-12 else "HOLD"
        row = next((r for r in scored if r["ticker"] == t), None)
        why = ("POOL_EXIT" if row is None else ",".join(row["exclusionCodes"]) or "RANK_OR_CONSTRAINT_EXIT") if new == 0 else (
            "NEW_ENTRY" if old == 0 else reason if action == "HOLD" or reason == "CAP_RESTORATION" else "TARGET_RESTORATION")
        events.append({"action": action, "ticker": t, "reason": why})
    if not set(target) - {benchmark}:
        events.append({"action": "WAIT_ETF", "ticker": benchmark, "reason": "PASSIVE_OR_NO_ADMISSIBLE_EDGE"})
    evidence = {t: {"key": asdict(o.key), "signalAt": o.signal_at,
                    "purchaseBucketEdge": next((r["edge"] for r in scored if r["ticker"] == t), None),
                    "remainingForecast": asdict(forecasts[t]) if t in forecasts else None,
                    "judgmentUnavailableReason": None if t in forecasts and forecasts[t].usable else "REMAINING_ALPHA_OR_UNCERTAINTY_UNAVAILABLE"}
                for t, o in sorted(observed.items())}
    return {**header, "status": "SYNTHETIC_DECISION", "before": frame.before, "target": target,
            "actions": events, "evidence": evidence, "ranking": scored,
            "selection": meta, "stockCount": len(set(target) - {benchmark}),
            "forcedFiveShortfall": policy == "FORCED_FIVE" and len(set(target) - {benchmark}) < W.MAX_NAMES,
            "actualCosts": None, "actualEtfOpportunityReturn": None,
            "evaluationReason": "NOT_REAL_EXECUTION; SYNTHETIC_EVALUATOR_REQUIRED"}


def evaluate(decision, security_returns, *, execution_date, end_date, scope, cost_multiplier=1):
    """One invented holding interval using the existing weekly replay accountant.

    No historical input adapter. This is not a share-count backtester; dated NAV
    costs, ETF opportunity attribution and turnover validate synthetic mechanics.
    """
    _synthetic(scope)
    if decision.get("status") != "SYNTHETIC_DECISION" or decision.get("dataMode") != "synthetic":
        raise ValueError("SYNTHETIC_DECISION_REQUIRED")
    if cost_multiplier not in (1, 2, 3):
        raise ValueError("UNREGISTERED_COST_STRESS")
    if execution_date != decision["nextTradingSession"] or IF.day(end_date) <= execution_date:
        raise ValueError("NEXT_SESSION_EXECUTION_REQUIRED")
    region = decision["market"]
    if end_date not in {str(d.date()) for d in RC.sessions(end_date, end_date, region)}:
        raise ValueError("END_SESSION_REQUIRED")
    before, target = decision["before"], decision["target"]
    bench = W.BENCHMARKS[region]
    # Same full input tape even for ETF-only/zero-weight names; no arm-specific mask.
    required = set(decision["evidence"]) | set(before) | set(target) | {bench}
    if any(t != bench and not t.startswith("SYN") for t in required):
        raise ValueError("SYNTHETIC_SECURITY_REQUIRED")
    if any(t not in security_returns or not CORE.finite(security_returns[t]) or security_returns[t] < -1 for t in required):
        raise ValueError("COMMON_RETURN_MASK_UNRESOLVED")
    legs = []
    for t in sorted(set(before) | set(target)):
        delta = target.get(t, 0) - before.get(t, 0)
        if abs(delta) <= 1e-12:
            continue
        side = "buy" if delta > 0 else "sell"
        category = "ETF_LEG" if t == bench else "INITIAL_FUNDING" if not before else (
            "NAME_ENTRY_EXIT" if not before.get(t) or not target.get(t) else "WEIGHT_RETARGET")
        legs.append({"ticker": t, "side": side, "weightTraded": abs(delta), "date": execution_date,
                     "category": category, "costFraction": abs(delta) * cost_multiplier * W.trade_cost_fraction(
                         region, execution_date, is_benchmark=t == bench, side=side)})
    # Reuse the existing accountant for the base-cost NAV (including its exact cost timing).
    from scripts.run_weekly_passive_first_replay import _leg_cost
    base_cost, turnover, name_trades = _leg_cost(before, target, {t: region for t in required}, execution_date, {bench})
    cost = sum(r["costFraction"] for r in legs)
    if not math.isclose(cost, base_cost * cost_multiplier, abs_tol=1e-12):
        raise AssertionError("COST_LEDGER_DOES_NOT_RECONCILE")
    gross = sum(w * security_returns[t] for t, w in target.items())
    hold_gross = sum(w * security_returns[t] for t, w in before.items()) if before else None
    net = (1 - cost) * (1 + gross) - 1
    passive_cost = (cost_multiplier * W.trade_cost_fraction(region, execution_date, is_benchmark=True, side="buy")
                    if not before else 0.0)
    passive_net = (1 - passive_cost) * (1 + security_returns[bench]) - 1
    replacement_names = {t for a in decision["actions"] if a["action"] == "REPLACE" for t in (a["from"], a["to"])}
    return {"dataMode": "synthetic", "recommendation": False, "costMultiplier": cost_multiplier,
            "executionDate": execution_date, "endDate": end_date, "legs": legs,
            "costFraction": cost, "oneWayTurnover": turnover, "nameTrades": name_trades,
            "stockOrderLegs": sum(l["ticker"] != bench for l in legs),
            "replacementCostFraction": sum(l["costFraction"] for l in legs if l["ticker"] in replacement_names),
            "costByCategory": {k: sum(l["costFraction"] for l in legs if l["category"] == k)
                               for k in ("ETF_LEG", "INITIAL_FUNDING", "NAME_ENTRY_EXIT", "WEIGHT_RETARGET")},
            "initialFunding": not bool(before), "grossReturn": gross, "netReturn": net,
            "passiveNetReturn": passive_net, "netActiveReturn": net - passive_net,
            "grossPolicyEffectVsHold": gross - hold_gross if hold_gross is not None else None,
            "stockExcessContributions": {t: w * (security_returns[t] - security_returns[bench]) for t, w in target.items() if t != bench},
            "etfOpportunityReturn": sum(w for t, w in target.items() if t != bench) * security_returns[bench],
            "regret": None, "regretReason": "H126_FUTURE_DIAGNOSTIC_NOT_RUN"}
