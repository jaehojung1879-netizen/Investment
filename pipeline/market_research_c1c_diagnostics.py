"""Invented-input economic diagnostics; no source loader, outcome runner or trade path.

The mandatory static comparator is matched to the candidate's realised mean
interval exposure, not its average requested target. Its initial mix is solved
using the whole invented path. It is therefore an EX POST diagnostic, not an
implementable forecast or proof of market-timing alpha. All paths use the same
asset, cash, calendar, costs and funded-entry/liquidation convention through the
existing replay. Source rights and genuine ETF total-return identity are separate
admission requirements; a synthetic basis label establishes neither.
"""
from __future__ import annotations

from numbers import Real
import re

import numpy as np
import pandas as pd

from . import market_research_c1c as C
from . import kr_market_risk_model as K
from . import replay_calendar as RC

MATCH_TOLERANCE = 1e-12
MATCH_ITERATIONS = 64
WHIPSAW_SESSIONS = C.LOOKBACK
BASES = ("C1_PRIMARY_REPLICA", "ETF_CASH_ECONOMIC")


def _numeric_series(series, name):
    if not isinstance(series, pd.Series) or not pd.api.types.is_numeric_dtype(series.dtype) or pd.api.types.is_bool_dtype(series.dtype):
        raise ValueError("NUMERIC_SERIES_REQUIRED:" + name)
    index = series.index
    if not isinstance(index, pd.DatetimeIndex) or index.tz is not None or not index.is_unique or not index.is_monotonic_increasing:
        raise ValueError("UNIQUE_ORDERED_SESSION_SERIES_REQUIRED:" + name)
    if not np.isfinite(series.to_numpy(dtype=float, na_value=np.nan)).all():
        raise ValueError("FINITE_SERIES_REQUIRED:" + name)


def _inputs(close, plan, selected, cash_returns, market, basis, stress, evidence_class):
    if evidence_class != C.SYNTHETIC:
        raise ValueError("SYNTHETIC_DIAGNOSTICS_ONLY")
    if market not in ("KR", "US") or basis not in BASES:
        raise ValueError("MARKET_OR_BASIS_NOT_REGISTERED")
    if isinstance(stress, (bool, np.bool_)) or not isinstance(stress, Real) or stress not in (0, 1, 2, 3):
        raise ValueError("UNREGISTERED_COST_STRESS")
    _numeric_series(close, "asset")
    _numeric_series(cash_returns, "cash")
    C.validate_series(close, market, complete=True)
    if not isinstance(plan, pd.DataFrame) or not {"decisionDate", "executionDate"} <= set(plan.columns):
        raise ValueError("DECISION_EXECUTION_PLAN_REQUIRED")
    C.validate_plan(plan, market)
    if isinstance(selected, (str, bytes, dict)):
        raise ValueError("BOUNDED_NUMERIC_TARGET_SEQUENCE_REQUIRED")
    try:
        selected = tuple(selected)
    except TypeError as exc:
        raise ValueError("BOUNDED_NUMERIC_TARGET_SEQUENCE_REQUIRED") from exc
    if len(selected) != len(plan) or any(isinstance(v, (bool, np.bool_)) or not isinstance(v, Real)
                                        or not np.isfinite(v) or not 0 <= v <= 1 for v in selected):
        raise ValueError("BOUNDED_NUMERIC_TARGET_SEQUENCE_REQUIRED")
    cash = cash_returns.reindex(close.index)
    if not np.isfinite(cash.to_numpy(dtype=float, na_value=np.nan)).all() or (cash <= -1).any():
        raise ValueError("COMPLETE_POSSIBLE_CASH_INTERVALS_REQUIRED")
    return selected, cash


def _mean_exposure(path):
    return float(path.weightStart.iloc[1:].mean())


def _matched_static(replay, candidate, n_targets):
    """Bounded numerical inversion only; never a signal or a fitted strategy."""
    wanted = _mean_exposure(candidate)
    low, high = 0.0, 1.0
    lower, upper = replay([low] * n_targets), replay([high] * n_targets)
    if not _mean_exposure(lower) <= wanted <= _mean_exposure(upper):
        raise ValueError("MATCHED_EXPOSURE_NOT_BRACKETED")
    chosen, target, iterations = lower, low, 0
    for target, chosen in ((low, lower), (high, upper)):
        if abs(_mean_exposure(chosen) - wanted) <= MATCH_TOLERANCE:
            break
    else:
        for iterations in range(1, MATCH_ITERATIONS + 1):
            target = (low + high) / 2
            chosen = replay([target] * n_targets)
            actual = _mean_exposure(chosen)
            if abs(actual - wanted) <= MATCH_TOLERANCE:
                break
            if actual < wanted:
                low = target
            else:
                high = target
    residual = _mean_exposure(chosen) - wanted
    if abs(residual) > MATCH_TOLERANCE:
        raise ValueError("MATCHED_EXPOSURE_DID_NOT_CONVERGE")
    return chosen, {"matched": True, "candidateMeanIntervalExposure": wanted,
                    "staticMeanIntervalExposure": _mean_exposure(chosen), "staticInitialTarget": float(target),
                    "residual": residual, "tolerance": MATCH_TOLERANCE, "iterations": iterations,
                    "policy": "FIXED_INITIAL_MIX_DRIFTS_NO_TRADE_WHILE_TARGET_UNCHANGED",
                    "interpretation": "EX_POST_FULL_PATH_MATCH_NOT_A_FORECAST_OR_TIMING_ALPHA_TEST"}


def _summary(path):
    implementation = K.implementation_cost(path)
    initial = float(path.attrs.get("entryNotionalFraction", 0.0))
    final = float(path.attrs.get("exitNotionalFraction", 0.0))
    intervals = path.dailyReturn.iloc[1:].to_numpy(float)
    tail = np.sort(intervals)[:max(1, int(np.ceil(.05 * len(intervals))))]
    return {"valuationIntervals": len(path) - 1, "netCumulativeReturn": float(path.nav.iloc[-1] - 1),
            "netAnnualLogGrowth": float(np.log(path.nav.iloc[-1]) * 252 / (len(path) - 1)),
            "fundedMaxDrawdown": float(K.max_drawdown(np.r_[1.0, path.nav.to_numpy()])["maxDrawdown"]),
            "dailyCvar95Loss": max(0.0, float(-tail.mean())),
            "annualizedVolatility": float(np.std(intervals, ddof=1) * np.sqrt(252)) if len(intervals) > 1 else None,
            "meanIntervalExposure": _mean_exposure(path), "switches": implementation["multiplierSwitches"],
            "switchNotionalSumOfPreTradeNavFractions": implementation["tradedNotional"],
            "lifecycleOneWayTurnover": (implementation["tradedNotional"] + initial + final) / 2,
            "switchFeeFractionSum": implementation["totalCostFractionOfNav"],
            "entryFeeInitialCapitalFraction": float(path.entryFee.sum()),
            "exitFeePreLiquidationNavFraction": float(path.attrs.get("exitCostFraction", 0.0)),
            "terminalTargetOmitted": int(path.attrs.get("terminalTargetOmitted", 0))}


def _transitions(path):
    """Execution-close changes only. The initial build is not a re-entry."""
    previous = path.target.shift(1)
    rows = []
    for i in np.flatnonzero((path.target > previous).to_numpy()):
        complete = i + WHIPSAW_SESSIONS < len(path)
        observed = bool((path.target.iloc[i + 1:i + WHIPSAW_SESSIONS + 1] < path.target.iloc[i]).any())
        rows.append({"executionDate": str(path.index[i].date()), "fromTarget": float(previous.iloc[i]),
                     "toTarget": float(path.target.iloc[i]), "observedReversalSoFar": observed,
                     "reversedWithin20Sessions": observed if complete else None, "pending": not complete})
    pending = sum(r["pending"] for r in rows)
    count = sum(r["reversedWithin20Sessions"] is True for r in rows)
    return {"horizonSessions": WHIPSAW_SESSIONS, "reentries": rows, "reentryCount": len(rows),
            "pendingReentries": pending, "maturedWhipsaws": count,
            "wholeCohortWhipsawShare": count / len(rows) if rows and not pending else None,
            "riskReductionExecutions": int((path.target < previous).sum()),
            "initialBuildExcluded": True, "futureValuesUsedOnlyForDiagnostics": True}


def _date(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("EXACT_EPISODE_SESSION_DATE_REQUIRED")
    return pd.Timestamp(value)


def _episode_rows(path, passive, episodes, market):
    """Fixed caller-supplied invented windows, never chosen by performance here."""
    if isinstance(episodes, (str, bytes, dict)):
        raise ValueError("FIXED_EPISODE_SEQUENCE_REQUIRED")
    try:
        episodes = tuple(episodes)
    except TypeError as exc:
        raise ValueError("FIXED_EPISODE_SEQUENCE_REQUIRED") from exc
    out, seen = [], set()
    for item in episodes:
        if not isinstance(item, dict) or set(item) != {"episodeId", "startDate", "troughDate", "endDate"}:
            raise ValueError("EXACT_EPISODE_CONTRACT_REQUIRED")
        identity = item["episodeId"]
        if not isinstance(identity, str) or not identity or identity in seen:
            raise ValueError("UNIQUE_EPISODE_ID_REQUIRED")
        seen.add(identity)
        start, trough, end = (_date(item[k]) for k in ("startDate", "troughDate", "endDate"))
        if not start < trough < end:
            raise ValueError("ORDERED_EPISODE_PHASES_REQUIRED")
        days = RC.sessions(item["startDate"], item["endDate"], market)
        if any(day not in days for day in (start, trough, end)):
            raise ValueError("EPISODE_OFF_EXCHANGE_SESSION")
        row = dict(item, status="MATURED", lossAvoidedNet=None, reboundOpportunityCostNet=None,
                   firstFullReentryExecutionDate=None, firstFullReentryDelaySessions=None)
        if start < path.index[0]:
            row["status"] = "BLOCKED_START_NOT_OBSERVED"
        elif end > path.index[-1]:
            row["status"] = "PENDING"
        else:
            def returns(nav, begin, finish):
                return float(nav.loc[finish] / nav.loc[begin] - 1)
            row["lossAvoidedNet"] = returns(path.nav, start, trough) - returns(passive.nav, start, trough)
            row["reboundOpportunityCostNet"] = returns(passive.nav, trough, end) - returns(path.nav, trough, end)
            recovery = path.loc[trough:end]
            full = recovery.index[recovery.target == 1.0]
            already_full = path.target.loc[trough] == 1.0
            row["fullReentryStatus"] = ("ALREADY_FULL_AT_TROUGH" if already_full else
                                        "REENTERED" if len(full) else "NOT_FULL_WITHIN_FIXED_WINDOW")
            if already_full:
                row["firstFullReentryDelaySessions"] = 0
            elif len(full):
                row["firstFullReentryExecutionDate"] = str(full[0].date())
                row["firstFullReentryDelaySessions"] = int(path.index.get_loc(full[0]) - path.index.get_loc(trough))
        out.append(row)
    incomplete = any(r["status"] != "MATURED" for r in out)
    aggregate = None if not out or incomplete else {
        "meanLossAvoidedNet": float(np.mean([r["lossAvoidedNet"] for r in out])),
        "meanReboundOpportunityCostNet": float(np.mean([r["reboundOpportunityCostNet"] for r in out]))}
    return {"windows": out, "intendedWindows": len(out), "maturedWindows": sum(r["status"] == "MATURED" for r in out),
            "pendingWindows": sum(r["status"] == "PENDING" for r in out),
            "blockedWindows": sum(r["status"].startswith("BLOCKED") for r in out), "completeCohortAggregate": aggregate,
            "windowOrigin": "CALLER_FIXED_SYNTHETIC_WINDOWS_NOT_A_REGISTRATION_OR_DATA_ADMISSION",
            "returnConvention": "CLOSE_TO_CLOSE_AFTER_PHASE_START; EXECUTION_CLOSE_RETURN_BELONGS_TO_PRIOR_HOLDING"}


def _cash_basis(cash, market, basis, declared):
    if basis == "C1_PRIMARY_REPLICA":
        expected = "ZERO_CASH_NONINVESTABLE_INDEX_DIAGNOSTIC"
    elif market == "KR":
        expected = "KR_ZERO_RATE_OPPORTUNITY_COST_SCENARIO"
    else:
        expected = "US_UNSPECIFIED_SYNTHETIC_CASH_SCENARIO"
    declared = expected if declared is None else declared
    if basis == "C1_PRIMARY_REPLICA" and not (cash == 0).all():
        raise ValueError("PRIMARY_REPLICA_REQUIRES_ZERO_CASH")
    allowed = {expected}
    if basis == "ETF_CASH_ECONOMIC":
        allowed.add("KR_UNVERIFIED_DAILY_RATE_SENSITIVITY_SCENARIO" if market == "KR" else
                    "US_SYNTHETIC_DTB3_PRIOR_KNOWN_ACT360")
    if declared not in allowed or ("ZERO" in declared and not (cash == 0).all()):
        raise ValueError("CASH_BASIS_OR_ZERO_RATE_SCENARIO_MISMATCH")
    return declared


def synthetic_diagnostics(close, plan, selected, cash_returns, market, basis, stress, *, evidence_class, episodes=(), cash_basis=None, cell_id=None):
    """Same-basis dynamic/static/passive paths and fixed-window diagnostics.

    No historical data option is exposed. An ETF basis here is invented ETF-TR
    arithmetic; only the separate source admission contract can establish real
    SPY/069500.KS identity, distributions, cash yields and rights.
    """
    selected, cash = _inputs(close, plan, selected, cash_returns, market, basis, stress, evidence_class)
    stress = int(stress)  # validated integer-valued grid; canonical report type
    cash_basis = _cash_basis(cash, market, basis, cash_basis)

    def replay(values):
        with np.errstate(over="ignore", divide="ignore", invalid="ignore"):
            path = C.replay(close, plan, values, cash, market, basis, stress, evidence_class=evidence_class)
        if (not np.isfinite(path[["nav", "weightStart", "weightEnd", "cost", "notional"]].to_numpy()).all()
                or not np.isfinite(path.dailyReturn.iloc[1:].to_numpy()).all() or (path.nav <= 0).any()):
            raise ValueError("NONFINITE_OR_IMPOSSIBLE_REPLAY_PATH")
        return path

    candidate = replay(selected)
    static, match = _matched_static(replay, candidate, len(selected))
    passive = replay([1.0] * len(selected))
    if not candidate.index.equals(static.index) or not candidate.index.equals(passive.index):
        raise ValueError("COMMON_VALUATION_CALENDAR_REQUIRED")
    summaries = {"candidate": _summary(candidate), "matchedStatic": _summary(static), "passive": _summary(passive)}
    buy, sell = C.cost_rates(market, basis)
    comparison = {"market": market, "basis": basis, "valuationIntervals": len(candidate) - 1,
                  "calendarSha256": C.digest([str(d.date()) for d in candidate.index]),
                  "planSha256": C.digest([
                      {"decisionDate": pd.Timestamp(d).isoformat(), "executionDate": pd.Timestamp(e).isoformat()}
                      for d, e in zip(plan.decisionDate, plan.executionDate)]),
                  "assetSha256": C.digest([float(v) for v in close.reindex(candidate.index)]),
                  "cashSha256": C.digest([float(v) for v in cash.reindex(candidate.index)]),
                  "startDate": str(candidate.index[0].date()), "endDate": str(candidate.index[-1].date()),
                  "costStress": stress, "buyCost": buy, "sellCost": sell, "cashBasis": cash_basis,
                  "returnConvention": ("FUNDED_NET_ETF_TR_SAME_CLOSE_WITH_LIQUIDATION" if basis == "ETF_CASH_ECONOMIC"
                                       else "NONINVESTABLE_PRICE_INDEX_UNFUNDED_START_NO_LIQUIDATION")}
    return {"market": market, "basis": basis, "costStress": stress, "evidenceClass": evidence_class,
            "cellId": cell_id,
            "basisMeaning": "NONINVESTABLE_PRICE_INDEX_ZERO_CASH_DIAGNOSTIC" if basis == "C1_PRIMARY_REPLICA"
            else "SYNTHETIC_ETF_TOTAL_RETURN_CASH_ECONOMICS_NOT_VENDOR_PROOF",
            "historicalExecutionEnabled": False, "productionAllowed": False, "timingAlphaEstablished": False,
            "comparisonBasis": comparison,
            "cashInterpretation": {"basis": cash_basis, "sourceAdmitted": False,
                "zeroCashIsActualShortRate": False, "cashManagementFeesAndTaxesAdmitted": False,
                "meaning": "KR_ZERO_IS_OPPORTUNITY_COST_SCENARIO_NOT_ACTUAL_DEPOSIT_OR_BILL_RETURN" if market == "KR"
                           else "SYNTHETIC_CASH_ARITHMETIC_NOT_PUBLICATION_OR_RIGHTS_PROOF"},
            "exposureMatch": match, "summaries": summaries,
            "candidateMinusMatchedStaticNetAnnualLogGrowth": summaries["candidate"]["netAnnualLogGrowth"] - summaries["matchedStatic"]["netAnnualLogGrowth"],
            "arithmeticAttribution": C.arithmetic_decomposition(candidate, close, cash),
            "transitions": _transitions(candidate), "episodes": _episode_rows(candidate, passive, episodes, market)}
