"""Market Research / C1c pure design tools. No data loader, execution permit or production call.

The sealed C1 state map, calendars, cash accrual, self-financing trades and
diagnostics are imported without modification. Only invented fixture economics
can be run by the accompanying CLI. Historical execution is not implemented.
"""
from __future__ import annotations

from functools import lru_cache
import hashlib
import importlib.metadata
import itertools
import json
import math
from pathlib import Path
import re
import subprocess
import sys

import numpy as np
import pandas as pd

from . import kr_market_risk_anatomy as M
from . import kr_market_risk_model as K
from . import prospective_receipt_core as P
from . import replay_calendar as RC
from . import rp1_c1_us_exposure as U

STUDY = "rp1-c1c-asymmetric-exit-reentry-v1"
PROGRAM = "rp1-market-research-v1"
ARMS = {"S0": (False, False), "S1": (True, False), "S2": (False, True), "S3": (True, True)}
LOOKBACK = 20
ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = "docs/research-program/proposals/market-research-c1c-v1.json"
SYNTHETIC = "SYNTHETIC_FIXTURE"


def digest(value):
    return hashlib.sha256(P.canonical(value)).hexdigest()


def domain(value, allowed):
    if value is None or pd.isna(value):
        return tuple(allowed)
    if not isinstance(value, (int, float, np.number)) or value not in allowed:
        raise ValueError("STATE_OUTSIDE_FROZEN_DOMAIN")
    return (int(value),)


def target(arm, slow, transition, fast, breakout):
    """Memoryless 2x2 rule; missing inputs are completed, never treated as benign.

    Breakout overrides a FAST=1 warning only. FAST=2 always vetoes re-entry.
    No latch is added: a later week without the trigger returns to C1's map.
    """
    hard, quick = ARMS[arm]
    if breakout is not None and not isinstance(breakout, (bool, np.bool_)):
        raise ValueError("BREAKOUT_MUST_BE_BOOLEAN_OR_MISSING")
    answers = set()
    for s, t, f, b in itertools.product(domain(slow, (0, 1)), domain(transition, (0, 1)),
                                       domain(fast, (0, 1, 2)), (False, True) if breakout is None else (bool(breakout),)):
        value = K.rule("C1", s, t, f)
        if hard and f == 2:
            value = 0.0
        elif quick and f == 1 and b:
            value = 1.0
        answers.add(value)
    return answers.pop() if len(answers) == 1 else None


@lru_cache(maxsize=2048)
def session_close(day, market):
    import exchange_calendars as xc
    name = {"KR": "XKRX", "US": "XNYS"}[market]
    if pd.Timestamp(day) not in RC.sessions(day, day, market):
        raise ValueError("SIGNAL_NOT_AN_EXCHANGE_SESSION")
    return xc.get_calendar(name, start="1990-01-01", end="2035-12-31").session_close(pd.Timestamp(day))


def final_at(day, market):
    close = session_close(day, market)
    ready = close + pd.Timedelta(hours=1)
    return max(ready, pd.Timestamp(day + "T18:00:00+09:00")) if market == "KR" else ready


def validate_series(series, market, *, complete=False):
    index = pd.DatetimeIndex(series.index)
    if not len(index) or index.tz is not None or not index.is_unique or not index.is_monotonic_increasing or not (index == index.normalize()).all():
        raise ValueError("INVALID_OR_DUPLICATE_SESSION_LABELS")
    expected = RC.sessions(str(index[0].date()), str(index[-1].date()), market)
    if not index.isin(expected).all() or complete and not index.equals(expected):
        raise ValueError("EXCHANGE_CALENDAR_GAP_OR_OFF_SESSION")
    if complete and (not np.isfinite(series.to_numpy(float)).all() or (series <= 0).any()):
        raise ValueError("INCOMPLETE_EXECUTABLE_PRICE_PATH")


def prior_high_breakout(close, day, market):
    validate_series(close, market)
    end = pd.Timestamp(day)
    days = RC.sessions(str((end - pd.Timedelta(days=90)).date()), day, market)[-(LOOKBACK + 1):]
    values = close.reindex(days)
    if len(values) != LOOKBACK + 1 or not np.isfinite(values.to_numpy(float)).all() or (values <= 0).any():
        return None
    return bool(values.iloc[-1] > values.iloc[:-1].max())


def schedule(close, market, start, end):
    """Calendar-derived weekly dates with next-session-close executions."""
    validate_series(close, market, complete=True)
    days = RC.sessions(str(close.index[0].date()), end, market)
    return U.decision_schedule(days, start, end, market)


def targets(close, states, plan, market, arm):
    """states carries slow/transition/fast and each layer's timezone-aware knownAt.

    The caller's states must come from the unchanged delayed/staleness-aware
    layer adapter. A future publication timestamp cannot be used at the close.
    """
    if not states.index.is_unique or not states.index.is_monotonic_increasing:
        raise ValueError("INVALID_STATE_PANEL_INDEX")
    validate_plan(plan, market)
    prior, rows = None, []
    for row in plan.itertuples(index=False):
        day, execution = pd.Timestamp(row.decisionDate), pd.Timestamp(row.executionDate)
        label = str(day.date())
        calendar = RC.sessions(label, str((day + pd.Timedelta(days=15)).date()), market)
        if len(calendar) < 2 or calendar[0] != day or execution != calendar[1] or tuple(day.isocalendar())[:2] == tuple(calendar[1].isocalendar())[:2]:
            raise ValueError("NOT_WEEKLY_NEXT_SESSION_EXECUTION")
        values = states.loc[day] if day in states.index else pd.Series(dtype=object)
        layers = []
        for name in ("slow", "transition", "fast"):
            value = values.get(name)
            if value is not None and not pd.isna(value):
                known = values.get(name + "KnownAt")
                if known is None or pd.isna(known) or P.utc(known) > final_at(label, market):
                    raise ValueError("STATE_NOT_KNOWN_AT_DECISION:" + name)
                if name == "fast" and P.utc(known) < session_close(label, market):
                    raise ValueError("INTRADAY_FAST_CANNOT_CERTIFY_FINAL_CLOSE")
            layers.append(value)
        breakout = prior_high_breakout(close.loc[:day], label, market)
        value = target(arm, *layers, breakout)
        held = value is None
        if held:
            if prior is None:
                raise ValueError("FIRST_TARGET_UNDETERMINED")
            value = prior
        rows.append({"decisionDate": day, "executionDate": execution, "target": value,
                     "heldForMissing": held, "breakout": breakout})
        prior = value
    if not rows:
        raise ValueError("NO_SCHEDULED_DECISIONS")
    return pd.DataFrame(rows)


def validate_plan(plan, market):
    if plan.empty or not pd.DatetimeIndex(plan.decisionDate).is_monotonic_increasing or not pd.DatetimeIndex(plan.decisionDate).is_unique:
        raise ValueError("INVALID_DECISION_SCHEDULE")
    if not pd.DatetimeIndex(plan.executionDate).is_unique or not pd.DatetimeIndex(plan.executionDate).is_monotonic_increasing:
        raise ValueError("INVALID_EXECUTION_SCHEDULE")
    for d, e in zip(plan.decisionDate, plan.executionDate):
        d, e = pd.Timestamp(d), pd.Timestamp(e)
        days = RC.sessions(str(d.date()), str((d + pd.Timedelta(days=15)).date()), market)
        if len(days) < 2 or days[0] != d or days[1] != e or tuple(d.isocalendar())[:2] == tuple(e.isocalendar())[:2]:
            raise ValueError("NOT_WEEKLY_NEXT_SESSION_EXECUTION")


def sealed_states(close, spread, vix, market):
    """Reuse original FAST/SLOW/TRANSITION, including four-day lag and 14-day staleness.

    No source read occurs. Observation-date inputs retain the sealed adapter's
    date-resolution/publication assumptions; this is not a new vintage claim.
    """
    validate_series(close, market, complete=True)
    result = U.layer_states(close, spread, vix, close.index, market)
    for layer in ("slow", "transition", "fast"):
        result[layer + "KnownAt"] = [final_at(str(day.date()), market).isoformat() for day in result.index]
    return result


def cost_rates(market, basis):
    if market == "US" and basis in ("C1_PRIMARY_REPLICA", "ETF_CASH_ECONOMIC"):
        return U.US_BUY_COST, U.US_SELL_COST
    if market == "KR" and basis == "C1_PRIMARY_REPLICA":
        return K.BUY_COST, K.SELL_COST
    if market == "KR" and basis == "ETF_CASH_ECONOMIC":
        # Existing REALISTIC_COSTS commission 1.5 + half-spread 4bps; domestic equity ETF sell tax is zero.
        return 0.00055, 0.00055
    raise ValueError("MARKET_OR_ASSET_BASIS_NOT_REGISTERED")


def replay(close, plan, selected, cash_returns, market, basis, stress, *, evidence_class):
    """Synthetic only: reuse the sealed, drifting, self-financing replay.

    C1_PRIMARY_REPLICA retains the original uncharged initialization. Separate
    ETF_CASH_ECONOMIC funds entry and liquidation identically for every arm.
    No historical runner or file-based input route is provided by this PR.
    """
    if evidence_class != SYNTHETIC:
        raise ValueError("HISTORICAL_EXECUTION_NOT_IMPLEMENTED_OR_AUTHORIZED")
    if stress not in (0, 1, 2, 3):
        raise ValueError("UNREGISTERED_COST_STRESS")
    validate_series(close, market, complete=True)
    validate_plan(plan, market)
    if len(selected) != len(plan) or not pd.DatetimeIndex(plan.executionDate).is_unique:
        raise ValueError("TARGET_SCHEDULE_MISMATCH")
    if plan.executionDate.iloc[0] not in close.index or plan.executionDate.iloc[-1] not in close.index:
        raise ValueError("EXECUTION_OUTSIDE_OBSERVED_PATH")
    if any(t is None or not np.isfinite(t) or not 0 <= t <= 1 for t in selected):
        raise ValueError("UNDETERMINED_OR_LEVERAGED_TARGET")
    buy, sell = cost_rates(market, basis)
    cash_window = cash_returns.reindex(close.index[close.index >= plan.executionDate.iloc[0]]).iloc[1:]
    if not np.isfinite(cash_window.to_numpy(float)).all() or (cash_window <= -1).any():
        raise ValueError("CASH_INTERVAL_MISSING_OR_IMPOSSIBLE")
    if basis == "C1_PRIMARY_REPLICA" and not (cash_returns.reindex(close.index).fillna(0) == 0).all():
        raise ValueError("PRIMARY_REPLICA_REQUIRES_ZERO_CASH")
    effective_plan, effective_targets = plan, list(selected)
    if basis == "ETF_CASH_ECONOMIC":
        # The final valuation close liquidates the whole book. Do not buy a new
        # target at that same close only to sell it immediately as an artifact.
        keep = pd.DatetimeIndex(plan.executionDate) < close.index[-1]
        effective_plan = plan.loc[keep].reset_index(drop=True)
        effective_targets = [v for v, ok in zip(selected, keep) if ok]
        if not len(effective_targets):
            raise ValueError("NO_HOLDING_INTERVAL_BEFORE_LIQUIDATION")
    path = U.replay_path_with_cash(close, effective_plan, effective_targets, cash_returns, stress=stress, buy_cost=buy, sell_cost=sell)
    if len(path) < 2:
        raise ValueError("TOO_FEW_VALUATION_SESSIONS")
    path["entryFee"] = 0.0
    path["liquidationFee"] = 0.0
    path.attrs.update(entryNotionalFraction=0.0, exitNotionalFraction=0.0, exitCostFraction=0.0,
                      terminalTargetOmitted=len(plan) - len(effective_plan))
    if basis == "ETF_CASH_ECONOMIC":
        factor = 1 / (1 + selected[0] * buy * stress)
        path["nav"] *= factor
        path.iloc[0, path.columns.get_loc("entryFee")] = 1 - factor
        path.iloc[0, path.columns.get_loc("dailyReturn")] = factor - 1
        before = path.nav.iloc[-1]
        fee = before * path.weightEnd.iloc[-1] * sell * stress
        path.iloc[-1, path.columns.get_loc("nav")] = before - fee
        path.iloc[-1, path.columns.get_loc("liquidationFee")] = fee
        path.iloc[-1, path.columns.get_loc("dailyReturn")] = path.nav.iloc[-1] / path.nav.iloc[-2] - 1
        path.attrs.update(entryNotionalFraction=selected[0] * factor,
                          exitNotionalFraction=float(path.weightEnd.iloc[-1]), exitCostFraction=fee / before)
    return path


def arithmetic_decomposition(path, asset_close, cash_returns):
    """Arithmetic identity only. Mean exposure uses the FULL path, is ex post,
    and is never an implementable counterfactual or evidence of timing skill.
    """
    days = path.index[1:]
    w = path.weightStart.reindex(days)
    spread = asset_close.pct_change(fill_method=None).reindex(days) - cash_returns.reindex(days)
    cash = cash_returns.reindex(days)
    implied = cash + w * spread
    mean_w = float(w.mean())
    terms = {"cash": float(cash.mean() * 252), "unconditionalExposure": float(mean_w * spread.mean() * 252),
             "timingCovariance": float(((w - mean_w) * (spread - spread.mean())).mean() * 252),
             "costImpact": float((implied - path.dailyReturn.reindex(days)).mean() * 252)}
    actual = float(path.dailyReturn.reindex(days).mean() * 252)
    return {**terms, "netArithmetic": actual, "identityResidual": actual - (terms["cash"] + terms["unconditionalExposure"] + terms["timingCovariance"] - terms["costImpact"]),
            "meanExposure": mean_w, "initialEntryFeeOutsideDailyIdentity": float(path.entryFee.sum()),
            "interpretation": "EX_POST_IDENTITY_NOT_TRADABLE_NOT_TIMING_SKILL"}


def diagnostics(path, passive, asset_close, cash_returns):
    bench = asset_close.reindex(path.index)
    market_reference = passive.copy()
    market_reference["dailyReturn"] = bench.pct_change(fill_method=None)
    summary = K.path_summary(path, market_reference)
    total = float(path.nav.iloc[-1] - 1)
    funded_cagr = K.annualized(path.nav.iloc[-1], len(path) - 1)
    # Include the initial unit of wealth when entry is funded; otherwise an entry fee disappears from MDD.
    lifecycle_dd = K.max_drawdown(np.r_[1.0, path.nav.to_numpy()])
    mdd = lifecycle_dd["maxDrawdown"]
    episodes = M.episodes_at_least(K.episodes_in_window(bench), K.PRIMARY_EPISODE_THRESHOLD)
    forward = M.forward_targets(bench, K.FALSE_ALARM_HORIZON)["forwardWorstLoss"]
    months = path.nav.groupby(path.index.to_period("M")).last()
    monthly = months.to_numpy() / np.r_[1.0, months.to_numpy()[:-1]] - 1
    tail = max(1, math.ceil(0.05 * len(monthly)))
    monthly_cvar = {"months": len(monthly), "tailMonths": tail, "cvar": float(np.sort(monthly)[:tail].mean()),
                    "worstMonth": float(monthly.min()), "partialMonthsIncluded": True}
    cash = cash_returns.reindex(path.index).copy()
    cash.iloc[0] = 0.0
    implementation = K.implementation_cost(path)
    lifecycle_notional = path.attrs.get("entryNotionalFraction", 0) + path.attrs.get("exitNotionalFraction", 0)
    implementation.update(allLifecycleOneWayTurnover=(implementation["tradedNotional"] + lifecycle_notional) / 2,
                          allLifecycleCostFractionSum=implementation["totalCostFractionOfNav"] + float(path.entryFee.sum()) + path.attrs.get("exitCostFraction", 0),
                          entryExitNotionalFractions=lifecycle_notional,
                          terminalTargetOmitted=path.attrs.get("terminalTargetOmitted", 0))
    return {"summary": {**summary, "cumulativeReturn": total, "annualizedReturn": funded_cagr, "maxDrawdown": mdd,
                         "maxDrawdownPeak": str(path.index[max(0, lifecycle_dd["peakPos"] - 1)].date()),
                         "maxDrawdownTrough": str(path.index[max(0, lifecycle_dd["troughPos"] - 1)].date()),
                         "maxDrawdownRecoverySessions": lifecycle_dd["recoverySessions"],
                         "drawdownPeakIsInitialCapital": lifecycle_dd["peakPos"] == 0,
                         "targetShare": {str(level): float((path.target == level).mean()) for level in (0.0, 0.4, 0.7, 1.0)},
                         "fundedCumulativeReturn": total, "fundedCagr": funded_cagr,
                         "fundedMdd": mdd, "sharpeOverCash": U.sharpe_over_cash(path, cash),
                         "calmar": funded_cagr / abs(mdd) if mdd < 0 and funded_cagr is not None else None},
            "monthlyCvar": monthly_cvar, "implementation": implementation,
            "entryFee": float(path.entryFee.sum()), "liquidationFee": float(path.liquidationFee.sum()),
            "upDownGap": U.up_down_market_gap(path, market_reference), "falseAlarm": K.false_alarm_profile(path, forward),
            "episodeCapture": K.episode_capture(path, bench, episodes), "rebound": K.rebound_cost(path, bench, episodes),
            "arithmetic": arithmetic_decomposition(path, asset_close, cash_returns)}


def transition_diagnostics(path, control):
    """Earlier return to 100%, and reversal within 20 sessions. Future values
    are diagnostics ONLY; immature windows remain pending, never zero.
    """
    prior = path.target.shift(1).fillna(1.0)
    horizon = LOOKBACK
    exits = (path.target < prior)
    entries = (path.target == 1) & (prior < 1)
    rows = []
    for i in np.flatnonzero(entries.to_numpy()):
        complete = i + horizon < len(path)
        rows.append({"date": str(path.index[i].date()), "earlierThanControl": bool(control.target.iloc[i] < 1),
                     "reversedWithin20": bool((path.target.iloc[i + 1:i + horizon + 1] < 1).any()) if complete else None,
                     "pending": not complete})
    return {"riskReductions": int(exits.sum()), "fullReentries": rows}


def lifecycle_periods(path, passive):
    """First-year/first-half economic results start at unit wealth, not after entry fees."""
    years, previous = {}, 1.0
    for year, group in path.groupby(path.index.year):
        years[str(year)] = float(group.nav.iloc[-1] / previous - 1)
        previous = group.nav.iloc[-1]
    halves = K.halves(path, passive)
    mid = (len(path) - 1) // 2
    halves["firstHalf"]["annualizedReturn"] = K.annualized(path.nav.iloc[mid], mid)
    halves["firstHalf"]["passiveAnnualizedReturn"] = K.annualized(passive.nav.iloc[mid], mid)
    halves["firstHalf"]["maxDrawdown"] = K.max_drawdown(np.r_[1.0, path.nav.iloc[:mid + 1].to_numpy()])["maxDrawdown"]
    halves["firstHalf"]["passiveMaxDrawdown"] = K.max_drawdown(np.r_[1.0, passive.nav.iloc[:mid + 1].to_numpy()])["maxDrawdown"]
    return {"calendarYears": years, "halves": halves}


def factorial(values):
    """Three predeclared contrasts for ONE metric/basis/market/cost cell.
    Missing cells block the whole comparison, not a better-looking subset.
    """
    if set(values) != set(ARMS) or any(v is None or not np.isfinite(v) for v in values.values()):
        return {"status": "INCOMPLETE_CELL", "exit": None, "reentry": None, "interaction": None}
    a, b, c, d = (values[k] for k in ARMS)
    return {"status": "DESCRIPTIVE_ONLY", "exit": b - a, "reentry": c - a, "interaction": d - b - c + a,
            "averageExit": ((b - a) + (d - c)) / 2, "averageReentry": ((c - a) + (d - b)) / 2}


def market_interface(market, signal, execution, multiplier, *, known_at, source_sha256, code_sha256, applied_scopes=()):
    if "MARKET_RISK_ONCE" in applied_scopes:
        raise ValueError("MARKET_MULTIPLIER_ALREADY_APPLIED")
    if multiplier is None or not np.isfinite(multiplier) or not 0 <= multiplier <= 1:
        raise ValueError("NO_DETERMINED_BOUNDED_MULTIPLIER")
    if P.utc(known_at) != final_at(signal, market) or not all(isinstance(s, str) and re.fullmatch(r"[0-9a-f]{64}", s) for s in (source_sha256, code_sha256)):
        raise ValueError("INTERFACE_TIME_OR_IDENTITY_MISSING")
    days = RC.sessions(signal, str((pd.Timestamp(signal) + pd.Timedelta(days=15)).date()), market)
    if len(days) < 2 or pd.Timestamp(execution) != days[1] or tuple(days[0].isocalendar())[:2] == tuple(days[1].isocalendar())[:2]:
        raise ValueError("INTERFACE_EXECUTION_BOUNDARY_MISMATCH")
    return {"studyId": STUDY, "market": market, "signalDate": signal, "executionDate": execution,
            "equityRiskMultiplier": float(multiplier), "appliedScope": "MARKET_RISK_ONCE",
            "knownAt": known_at, "sourceSha256": source_sha256, "codeSha256": code_sha256,
            "contractSha256": digest(json.loads((ROOT / PROTOCOL).read_bytes())),
            "evidenceClass": SYNTHETIC, "productionAllowed": False,
            "selectionOrIndustryForecastChanged": False, "BConditionalSignalAppliedAsRiskMultiplier": False}


def program_readiness():
    return {"programId": PROGRAM, "members": {"B-H1": "REGISTERED_STATE_ONLY_FIRST_FLOOR_2026_10_30",
            "B-H1-outcomes": "BLOCKED_OUTCOME_CONTRACT_NOT_REGISTERED",
            "B-H2": "BLOCKED_NO_SUPPORTED_STUDY_A_P_EQUALS_1_SLOT_RETAINED",
            "C1c-2x2": "DESIGN_PENDING_INDEPENDENT_AUDIT_AND_OWNER_APPROVAL",
            "C-continuous-vol": "FUTURE_SEPARATE_PREREGISTRATION_NOT_IMPLEMENTED",
            "C-cash-short-bill": "FUTURE_SEPARATE_PREREGISTRATION_NOT_IMPLEMENTED"},
            "hypothesisFamiliesPooled": False, "historicalExecutionEnabled": False, "empiricalSupport": "NOT_TESTED",
            "industryAndStockResearchDependsOnMarketAlpha": False, "productionEffect": "NONE"}


def verify_design(root=ROOT):
    root = Path(root)
    protocol = json.loads((root / PROTOCOL).read_bytes())
    expected = {"studyId": STUDY, "control": "C1_CONFIRMATION_GATED", "armCount": 4,
                "breakoutWindow": LOOKBACK, "severeFast": 2, "hardExitTarget": 0.0,
                "reentryFast": 1, "reentryTarget": 1.0, "costStress": [1, 2, 3],
                "historicalExecutionEnabled": False, "productionEffect": "NONE"}
    if any(protocol.get(k) != v for k, v in expected.items()):
        raise ValueError("PROTOCOL_IMPLEMENTATION_MISMATCH_OR_EXECUTION_ENABLED")
    pins = json.loads((root / "docs/research-program/proposals/market-research-preserved-sha256.json").read_bytes())
    for name, sha in pins["files"].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != sha:
            raise ValueError("EXISTING_STUDY_CHANGED:" + name)
    closure = ["pipeline/market_research_c1c.py", "scripts/check_market_research.py", PROTOCOL,
               "docs/research-program/proposals/market-research-preserved-sha256.json",
               "tests/test_market_research_c1c.py"]
    return {**program_readiness(), "status": "BLOCKED_PENDING_INDEPENDENT_AUDIT_AND_OWNER_APPROVAL",
            "designStructure": "VERIFIED", "protocolSha256": digest(protocol), "preservedFiles": len(pins["files"]),
            "codeHashes": {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in closure},
            "codeCommit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
            "worktreeClean": not subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True).strip(),
            "runtime": {"python": sys.version.split()[0], **{p: importlib.metadata.version(p) for p in ("numpy", "pandas", "exchange-calendars")}},
            "realNumericValueReads": 0, "historicalOutcomeExecutions": 0, "ownerAuthorization": False}
