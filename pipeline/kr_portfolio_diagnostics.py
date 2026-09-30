"""Frozen descriptive instruments; only called AFTER the primary durable write.

These may never choose parameters or rescue the development state.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def portfolio_metrics(path):
    nav = np.asarray([1.0] + [r["nav"] for r in path])
    benchmark = np.asarray([1.0] + [r["benchmarkNav"] for r in path])
    returns = nav[1:] / nav[:-1] - 1
    annual_vol = float(np.std(returns, ddof=1) * np.sqrt(252))
    downside = float(np.sqrt(np.mean(np.minimum(returns, 0)**2)) * np.sqrt(252))
    years = (pd.Timestamp(path[-1]["date"]) - pd.Timestamp(path[0]["date"])).days / 365.2425
    midpoint = len(path) // 2
    half = (nav[midpoint] - benchmark[midpoint],
            nav[-1] / nav[midpoint] - benchmark[-1] / benchmark[midpoint])
    return {"netReturn": float(nav[-1] - 1), "grossReturn": float(path[-1]["grossNav"] - 1),
            "benchmarkReturn": float(benchmark[-1] - 1), "netExcess": float(nav[-1] - benchmark[-1]),
            "chronologicalHalfExcess": [float(x) for x in half],
            "cagr": float(nav[-1]**(1 / years) - 1) if years >= 1 else None,
            "annualVolatility": annual_vol, "downsideVolatility": downside,
            "sharpeZeroCashRate": float(np.mean(returns)*252 / annual_vol) if annual_vol else None,
            "sortinoZeroCashRate": float(np.mean(returns)*252 / downside) if downside else None,
            "maxDrawdown": float(np.min(nav / np.maximum.accumulate(nav) - 1)),
            "turnover": float(sum(r["turnover"] for r in path)),
            "costDrag": float(path[-1]["grossNav"] - nav[-1]),
            "dailyHitRate": float(np.mean(returns > benchmark[1:] / benchmark[:-1] - 1)),
            "averageCash": float(np.mean([r["cashWeight"] for r in path])),
            "averageHoldings": float(np.mean([r["holdings"] for r in path])),
            "maxSecurityWeight": float(max((max(r["weights"].values(), default=0) for r in path), default=0)),
            "cashRateAssumption": "ZERO_KRW_NOMINAL", "sessions": len(path)}


def valuation_convergence(entry, exit_):
    """Common accounting-proxy multiple movement; explicitly price-mechanical.

No perfect return attribution: log(cap change)=log(book change)+log(P/B change)
only when both book/cap values are positive and identity/class basis is unchanged.
"""
    values = [entry.get(k) for k in ("totalBookEquity", "marketCap")]
    values += [exit_.get(k) for k in ("totalBookEquity", "marketCap")]
    if (entry.get("basis") != exit_.get("basis") or entry.get("securityId") != exit_.get("securityId")
            or any(v is None or not np.isfinite(v) or v <= 0 for v in values)):
        return {"status": "NOT_INTERPRETABLE", "affectsPrimary": False}
    book0, cap0, book1, cap1 = values
    fundamental = float(np.log(book1 / book0))
    rerating = float(np.log((cap1 / book1) / (cap0 / book0)))
    return {"status": "DESCRIPTIVE", "logBookGrowth": fundamental, "logMultipleExpansion": rerating,
            "entryCheapness": book0/cap0, "exitCheapness": book1/cap1,
            "cheapnessChange": book1/cap1 - book0/cap0,
            "fundamentalImproved": fundamental > 0, "multipleExpanded": rerating > 0,
            "distributionContribution": None, "priceMechanical": True,
            "notACompleteShareholderReturnDecomposition": True, "affectsPrimary": False}


def supplementary(context, bundle, spec, permit, counters):
    from . import kr_model_portfolio_execution as X
    from . import kr_value_quality_catalyst as F
    from . import replay_calendar as RC
    X.require_permit(permit)
    output = {"studyId": X.STUDY, "status": "DESCRIPTIVE_ONLY", "affectsPrimary": False,
              "canRescuePrimary": False, "canAuthorizeRerun": False, "concordance": {}, "valuationConvergence": []}
    for horizon, predictions in context["predictions"].items():
        if predictions.empty:
            output["concordance"][horizon] = None
            continue
        correlation = pd.to_numeric(predictions.prediction, errors="coerce").corr(
            pd.to_numeric(predictions.challengerPrediction, errors="coerce"))
        output["concordance"][horizon] = float(correlation) if np.isfinite(correlation) else None
    output["predictionRecords"] = {}
    for horizon, predictions in context["predictions"].items():
        # Persist realized-label-free model output and decomposition for each stock/date.
        rows = predictions.to_dict("records")
        for row in rows:
            row["predictionH" + horizon] = row.pop("prediction")
        output["predictionRecords"][horizon] = rows
    days = RC.sessions("2013-01-01", "2028-12-31", "KR")
    for row in context["predictions"]["126"].to_dict("records"):
        exit_day = str(days[days.searchsorted(pd.Timestamp(row["date"]), side="right") + 126].date())
        if exit_day > spec["developmentCutoff"]:
            continue
        ticker = row["ticker"]
        entry_quote, exit_quote = bundle["market"].at(ticker, row["date"]), bundle["market"].at(ticker, exit_day)
        if entry_quote is None or exit_quote is None:
            continue
        entry, entry_basis = F.accounting_values(bundle["accounting"].get(ticker, []), row["date"])
        exit_, exit_basis = F.accounting_values(bundle["accounting"].get(ticker, []), exit_day)
        outcome = valuation_convergence({**entry, **entry_quote, "basis": entry_basis.get("basis")},
                                       {**exit_, **exit_quote, "basis": exit_basis.get("basis")})
        output["valuationConvergence"].append({"ticker": ticker, "signalDate": row["date"], **outcome})
    # Frozen stress/baseline variants are descriptive and run only after primary durability.
    output["portfolioBaselines"] = {}
    for variant in ("equal", "momentum"):
        try:
            value = X.replay_portfolio(permit, context["predictions"]["126"], bundle, spec, counters, variant=variant)
            output["portfolioBaselines"][variant] = {k: v for k, v in value.items() if k != "path"}
        except ValueError as exc:
            output["portfolioBaselines"][variant] = {"complete": False, "reason": str(exc)}
    output["costStress"] = {}
    for stress in spec["costStress"]:
        try:
            value = X.replay_portfolio(permit, context["predictions"]["126"], bundle, spec, counters, stress=stress)
            output["costStress"][str(stress)] = {k: v for k, v in value.items() if k != "path"}
        except ValueError as exc:
            output["costStress"][str(stress)] = {"complete": False, "reason": str(exc)}
    return output
