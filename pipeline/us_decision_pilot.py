"""Fixed, descriptive US decision comparison; no source access or production writes.

Callers supply explicitly permitted inputs. This module does not open sealed
studies, recover absent prices, impute accounting fields, or issue forecasts.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import kelly_portfolio as KP
from .benchmark_alpha import REALISTIC_COSTS

STUDY = "US_DECISION_PILOT_V1"
EVIDENCE = "SURVIVOR_CONDITIONED_EXPLORATORY"
ACCOUNTING = ("cashOperatingProfitability", "operatingProfitabilityToAssets", "assetGrowthPct", "debtToEquity")
FAMILIES = ("price", "cash", "accrual", "investment", "leverage")
HORIZONS = (63, 126, 252)
MIN_NAMES = 30


def scores(rows: pd.DataFrame) -> pd.DataFrame:
    """One complete-case cross-section, formed before any label is consulted."""
    required = ["momentum252", "vol252", *ACCOUNTING]
    x = rows.replace([np.inf, -np.inf], np.nan).dropna(subset=required).copy()
    if x.index.has_duplicates:
        raise ValueError("DUPLICATE_SECURITY")
    if len(x) < MIN_NAMES:
        return x.iloc[:0]
    rank = lambda field, sign=1: (sign * x[field]).rank(method="average")
    # Half/quarter integer ranks sum exactly; normalize ONCE so algebraic
    # ties cannot become spurious orderings from floating-point cancellation.
    raw = pd.DataFrame({"price": (rank("momentum252") + rank("vol252", -1)) / 2,
        "cash": rank(ACCOUNTING[0]), "accrual": rank(ACCOUNTING[1]),
        "investment": rank(ACCOUNTING[2], -1), "leverage": rank(ACCOUNTING[3], -1)})
    for family in FAMILIES:
        x[family] = raw[family] / len(x)
    x["B1"] = x["price"]
    x["B2"] = raw[list(FAMILIES)].sum(axis=1) / (len(FAMILIES) * len(x))
    for family in FAMILIES:
        x["WITHOUT_" + family] = raw[[f for f in FAMILIES if f != family]].sum(axis=1) / (4 * len(x))
    return x


def price_features(close: pd.Series, as_of) -> dict:
    """252-session momentum and volatility; exact observations, no ffill."""
    history = close.loc[:as_of].tail(253)
    if (len(history) != 253 or pd.Timestamp(history.index[-1]).normalize() != pd.Timestamp(as_of).normalize()
            or not np.isfinite(history).all() or (history <= 0).any()):
        return {"momentum252": None, "vol252": None}
    returns = history.pct_change(fill_method=None).iloc[1:]
    return {"momentum252": float(history.iloc[-1] / history.iloc[0] - 1),
            "vol252": float(returns.std(ddof=1) * np.sqrt(252))}


def allocation(frame: pd.DataFrame, column: str, *, concentrated=False) -> dict:
    """Broad top quintile, or explicitly FORCED diagnostic <=5 / sector <=2."""
    if frame.empty:
        raise ValueError("SIGNAL_UNAVAILABLE_NOT_AN_EXPLICIT_CASH_DECISION")
    ordered = frame.assign(_ticker=frame.index).sort_values([column, "_ticker"], ascending=[False, True])
    if not concentrated:
        chosen = list(ordered.index[:max(1, math.ceil(len(frame) / 5))])
    else:
        if frame["sector"].isna().any() or frame["sector"].isin(("UNCLASSIFIED", "Unclassified")).any():
            raise ValueError("DATED_SECTOR_REQUIRED")
        candidates = [{"ticker": t, "region": "US", "sector": row.sector} for t, row in ordered.iterrows()]
        ranked = [{**r, "score": float(ordered.loc[r["ticker"], column]), "eligible": True,
                   "exclusionCodes": []} for r in candidates]
        selected, _ = KP.select_portfolio_by_scores(candidates, ranked,
            {"maxNames": 5, "selection": {"targetNames": 5, "minNames": 0,
             "maxNamesPerSector": 2, "maxNamesPerRegion": 5}}, method=STUDY + "_FORCED_DIAGNOSTIC")
        chosen = [r["ticker"] for r in selected]
    return {t: 1 / len(chosen) for t in chosen} if chosen else {}


def rebalance(weights: dict, target: dict, buy_rate: float, sell_rate: float):
    """Self-financing, no leverage: costs paid before assigning target weights."""
    if any(v < 0 or not np.isfinite(v) for v in target.values()) or sum(target.values()) > 1 + 1e-12:
        raise ValueError("INVALID_TARGET")
    names = set(weights) | set(target)
    cost = 0.0
    for _ in range(100):
        delta = {t: target.get(t, 0) * (1 - cost) - weights.get(t, 0) for t in names}
        buy = sum(max(v, 0) for v in delta.values())
        sell = sum(max(-v, 0) for v in delta.values())
        updated = buy_rate * buy + sell_rate * sell
        if abs(updated - cost) < 1e-13:
            return updated, buy + sell
        cost = updated
    raise ValueError("COST_SOLVER_DID_NOT_CONVERGE")


def simulate(close: pd.DataFrame, orders: dict, *, costed=True) -> pd.DataFrame:
    """Orders keyed by NEXT-session closing fill date, not signal close.

    A missing held quote refuses the path. No sale at last quote, restart,
    zero return, or survivor substitution is performed. Cash earns zero.
    """
    if not close.index.is_monotonic_increasing or close.index.has_duplicates:
        raise ValueError("INVALID_SESSION_INDEX")
    if not set(orders).issubset(set(close.index)):
        raise ValueError("ORDER_OUTSIDE_SESSION_GRID")
    if len(close) and close.index[0] in orders:
        raise ValueError("INITIAL_CASH_ANCHOR_REQUIRED")
    policy = REALISTIC_COSTS["US"]
    buy_rate = (policy["commissionBps"] + policy["spreadBps"] / 2) / 10000 if costed else 0
    sell_rate = buy_rate + (policy["sellTaxBps"] / 10000 if costed else 0)
    nav, weights, records = 1.0, {}, []
    for i, day in enumerate(close.index):
        if i and weights:
            names = list(weights)
            a, b = close.loc[close.index[i - 1], names], close.loc[day, names]
            if not np.isfinite(a).all() or not np.isfinite(b).all() or (a <= 0).any() or (b <= 0).any():
                raise ValueError("UNRESOLVED_HELD_OBSERVATION:" + str(day))
            ratios = b / a
            growth = 1 - sum(weights.values()) + sum(weights[t] * ratios[t] for t in names)
            nav *= growth
            weights = {t: weights[t] * ratios[t] / growth for t in names}
        cost_amount, traded = 0.0, 0.0
        if day in orders:
            target = orders[day]
            if target:
                quotes = close.loc[day, list(target)]
                if not np.isfinite(quotes).all() or (quotes <= 0).any():
                    raise ValueError("UNRESOLVED_ENTRY_OBSERVATION:" + str(day))
            cost, traded = rebalance(weights, target, buy_rate, sell_rate)
            cost_amount = nav * cost
            nav -= cost_amount
            weights = dict(target)
        records.append({"date": day, "nav": nav, "costInitialCapital": cost_amount,
                        "twoWayTurnover": traded, "names": len(weights), "cash": 1 - sum(weights.values())})
    return pd.DataFrame(records).set_index("date")


def metrics(path: pd.DataFrame) -> dict:
    if len(path) < 2:
        return {"status": "NOT_ESTIMABLE", "reason": "INSUFFICIENT_SESSIONS"}
    nav = path.nav
    r = nav.pct_change(fill_method=None).iloc[1:]
    sd = float(r.std(ddof=1)) if len(r) > 1 else float("nan")
    yearly = {}
    previous = float(nav.iloc[0])
    for year, group in path.groupby(path.index.year):
        last = float(group.nav.iloc[-1])
        yearly[str(year)] = last / previous - 1
        previous = last
    return {"status": "ESTIMATED_DESCRIPTIVE", "start": str(path.index[0].date()),
            "end": str(path.index[-1].date()), "sessions": len(r),
            "cagr": float((nav.iloc[-1] / nav.iloc[0]) ** (252 / len(r)) - 1),
            "mdd": float((nav / nav.cummax() - 1).min()),
            "annualVolatility": sd * np.sqrt(252) if np.isfinite(sd) else None,
            "sharpeZeroRiskFree": float(r.mean() / sd * np.sqrt(252)) if np.isfinite(sd) and sd > 0 else None,
            "cashRateAssumption": "ZERO_UNREMUNERATED_CASH", "yearlyReturns": yearly,
            "tradingCostInitialCapital": float(path.costInitialCapital.sum()),
            "twoWayTurnover": float(path.twoWayTurnover.sum()),
            "oneWayHalfTurnover": float(path.twoWayTurnover.sum() / 2),
            "meanNames": float(path.names.mean()), "meanCash": float(path.cash.mean())}


def label_reading(frame: pd.DataFrame, entry: pd.Series, exit_: pd.Series) -> dict:
    """Same full cohort for every score; endpoints absent -> date unresolved."""
    if len(frame) < MIN_NAMES:
        return {"status": "NOT_ESTIMABLE", "reason": "INSUFFICIENT_NAMES"}
    if not set(frame.index).issubset(entry.index) or not set(frame.index).issubset(exit_.index):
        return {"status": "UNRESOLVED", "reason": "MISSING_ENDPOINT_SECURITY"}
    a, b = entry.loc[frame.index], exit_.loc[frame.index]
    if not np.isfinite(a).all() or not np.isfinite(b).all() or (a <= 0).any() or (b <= 0).any():
        return {"status": "UNRESOLVED", "reason": "MISSING_ENDPOINT_NO_TERMINAL_PAYOFF"}
    result = b / a - 1
    out = {}
    for name in ("B1", "B2", *FAMILIES, *("WITHOUT_" + f for f in FAMILIES)):
        ordered = frame.assign(_ticker=frame.index).sort_values([name, "_ticker"], ascending=[False, True])
        n = max(1, math.ceil(len(frame) / 5))
        ic = (frame[name].rank().corr(result.rank())
              if frame[name].nunique() > 1 and result.nunique() > 1 else float("nan"))
        out[name] = {"rankIC": float(ic) if np.isfinite(ic) else None,
                     "topMinusBottom": float(result.loc[ordered.index[:n]].mean() - result.loc[ordered.index[-n:]].mean()),
                     "topMean": float(result.loc[ordered.index[:n]].mean())}
    return {"status": "RESOLVED", "names": len(frame), "scores": out}
