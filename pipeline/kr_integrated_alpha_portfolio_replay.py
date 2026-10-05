"""KR integrated alpha portfolio v1 — the daily path replay and the metrics of one architecture.

EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY. This module values portfolios, so every function here is an OUTCOME function: the
execution harness calls it only behind its permit and durable lock, and verify / readiness never reach it (a test replaces each one with a spy).

One code path serves all six architectures. The ONLY inputs that differ are the registered axes: which underlying decision is traded (S or I+S) and
which market multiplier table scales it (none, C0 or C1). Anchors, universe, sizing, costs, liquidity limits, partial fills and the unresolved
terminal rule are identical, and the sealed `kr_concentrated_portfolio.execute_rebalance` does every trade.

* STOCK ANCHORS. Every 21 KR sessions from the fixed 2015-01-01 origin (the overlay study's calendar), executing at that close on the underlying
  decision of the preceding completed weekly KR signal. Between anchors nothing is retargeted.
* MARKET EVENTS. The sealed Market Risk Model trades at the close of the session AFTER each weekly decision, and only when its multiplier changes.
  Here that is a PURE SCALE of the book already held: names keep their drifted proportions, are never added or swapped, and the held book is
  re-expressed at multiplier 1, renormalised to at most 1, then multiplied by the new target. Drift is never traded away while the target is unchanged.
* AN UNRESOLVED HELD MARK BLOCKS THE PATH. A held name with no observed close, no observed zero-volume quote to carry and no terminal economics makes
  that architecture's path `complete: False`; it never disappears and is never replaced by a survivor.
"""
from __future__ import annotations

from bisect import bisect_left
import math

import numpy as np
import pandas as pd

from . import kr_concentrated_portfolio as P
from . import kr_integrated_alpha_portfolio as M
from . import kr_market_risk_anatomy as MA
from . import kr_market_risk_model as K

UNRESOLVED = "PORTFOLIO_MARK_OR_TERMINAL_ECONOMICS_UNRESOLVED"
ANNUALISATION = 252
DAYS_PER_YEAR = 365.2425


class Context:
    """Everything a replay reads, as plain attributes: prices {ticker: frame with Close}, market (a store with at / trailing), days (KR sessions),
    benchmark ticker, an ADV cache shared by every architecture (the 60-session mean depends only on the ticker and the history date)."""

    def __init__(self, prices, market, days, benchmark=M.BENCHMARK):
        self.prices, self.market, self.days, self.benchmark = prices, market, pd.DatetimeIndex(days), benchmark
        self.adv_cache = {}


def anchor_schedule(days, weekly_signals, start=M.EVALUATION_START, stride=M.STRIDE_KR_SESSIONS):
    """[(anchor day, signal date)]: every `stride`-th session counted from the first session of `days` (the fixed origin), on or after `start`, with the
    signal being the last weekly KR signal STRICTLY before the anchor. Independent of where any data end."""
    signals = sorted(weekly_signals)
    out = []
    for index, stamp in enumerate(pd.DatetimeIndex(days)):
        if index % stride:
            continue
        day = str(stamp.date())
        if day < start:
            continue
        position = bisect_left(signals, day)
        if position:
            out.append((day, signals[position - 1]))
    return out


def mark_price(ctx, ticker, day, previous=None):
    """Observed close; an observed zero-volume quote may carry the previous mark; a missing or delisted economics may not."""
    frame = ctx.prices.get(ticker)
    stamp = pd.Timestamp(day)
    value = frame.loc[stamp, "Close"] if frame is not None and stamp in frame.index else None
    if value is not None and np.isfinite(value) and value > 0:
        return float(value)
    quote = ctx.market.at(ticker, day)
    if quote and quote["volume"] == 0 and previous is not None:
        return previous
    raise ValueError(UNRESOLVED + ": " + ticker + ":" + day)


def adv_map(ctx, tickers, history_date, trade_day):
    """ADV60 over the 60 sessions ending at `history_date`, only for names with an observed positive-volume quote at the execution close.
    A name without one is absent, so its order is deferred (no fictitious suspension fill)."""
    out = {}
    for ticker in sorted(tickers):
        quote = ctx.market.at(ticker, trade_day)
        if not quote or quote["volume"] <= 0:
            continue
        key = (ticker, history_date)
        if key not in ctx.adv_cache:
            history = ctx.market.trailing(ticker, history_date, M.PORTFOLIO["advLookback"])
            ok = len(history) == M.PORTFOLIO["advLookback"] and all(r is not None for r in history)
            ctx.adv_cache[key] = float(np.mean([r["tradingValue"] for r in history])) if ok else None
        if ctx.adv_cache[key] is not None:
            out[ticker] = ctx.adv_cache[key]
    return out


def scaled_targets(positions, current, new):
    """Market event: the held book's drifted proportions, re-expressed at multiplier 1, renormalised so the book never exceeds 1, times the new target."""
    underlying = {t: w / current for t, w in positions.items() if w > 0}
    scale = max(1.0, math.fsum(sorted(underlying.values())))
    return {t: v / scale * new for t, v in sorted(underlying.items())}


def replay_architecture(architecture, decisions, anchors, market_table, ctx, cfg=M.PORTFOLIO, *, stress=1.0, cutoff=M.DEVELOPMENT_CUTOFF):
    """Daily path of one architecture. `decisions` = {signalDate: underlying decision of the architecture's layer (S or I+S)};
    `market_table` is the sealed candidate's decision table (None = market OFF, multiplier 1.0 throughout). Returns {'complete': True, 'path': [...]}
    or {'complete': False, 'reason': ...} when a held mark is unresolved."""
    anchor_by_day = dict(anchors)
    if not anchor_by_day:
        return {"complete": False, "reason": "NO_ANCHORS"}
    first = min(anchor_by_day)
    positions, previous_prices = {}, {}
    nav = benchmark_nav = gross_nav = 1.0
    previous_benchmark = None
    current_multiplier = None
    started = False
    records = []
    try:
        for stamp in ctx.days:
            day = str(stamp.date())
            if day < first or day > cutoff:
                continue
            if started:
                growth_by = {}
                for ticker in positions:
                    mark = mark_price(ctx, ticker, day, previous_prices.get(ticker))
                    growth_by[ticker] = mark / previous_prices[ticker]
                    previous_prices[ticker] = mark
                growth = 1 - sum(positions.values()) + sum(w * growth_by[t] for t, w in positions.items())
                positions = {t: w * growth_by[t] / growth for t, w in positions.items()}
                gross_nav += nav * (growth - 1)           # identical executed stock notionals; saved fees stay in zero-rate cash
                nav *= growth
                benchmark_price = mark_price(ctx, ctx.benchmark, day)
                benchmark_nav *= benchmark_price / previous_benchmark
                previous_benchmark = benchmark_price
            target = 1.0 if market_table is None else M.target_in_force(market_table, day)
            if target is None:
                raise ValueError("MARKET_TARGET_UNAVAILABLE: " + day)
            cost = turnover = 0.0
            kind, replaced, added, execution, unavailable = None, 0, 0, None, False
            signal = anchor_by_day.get(day)
            if signal is not None and signal not in decisions:
                raise ValueError("MISSING_UNDERLYING_DECISION: " + signal)
            if signal is not None and not decisions[signal].get("available", True):
                # REGISTERED MISSING-SIGNAL RULE: no new decision exists for this book at this anchor, so NO STOCK TRADE is generated. The held book (if any)
                # continues unchanged and drifts; before the first valid decision the book is 100% cash. Nothing is imputed, substituted or liquidated.
                kind, unavailable = "NO_TRADE_SIGNAL_UNAVAILABLE", True
                if not started:
                    started = True
                    previous_benchmark = mark_price(ctx, ctx.benchmark, day)
                signal = None
            if signal is not None:
                decision = decisions[signal]
                desired = {t: w * target for t, w in decision["baseWeights"].items()}
                adv = adv_map(ctx, set(positions) | set(desired), signal, day)
                before = set(positions)
                execution = P.execute_rebalance(positions, desired, adv, decision["selected"], target, cfg, nav_krw=nav * cfg["referenceNavKrw"], stress=stress)
                kind = "ANCHOR"
                if started:
                    after = set(execution["weights"])
                    replaced, added = len(before - after), len(after - before)
            elif started and target != current_multiplier and positions:
                desired = scaled_targets(positions, current_multiplier, target)
                previous_session = str(ctx.days[ctx.days.searchsorted(stamp) - 1].date())
                adv = adv_map(ctx, set(positions), previous_session, day)
                execution = P.execute_rebalance(positions, desired, adv, [], target, cfg, nav_krw=nav * cfg["referenceNavKrw"], stress=stress)
                kind = "MARKET"
            if execution is not None:
                cost, turnover = execution["costFraction"], execution["oneWayTurnover"]
                nav *= execution["postCostNavFactor"]
                positions = execution["weights"]
                for ticker in positions:
                    previous_prices[ticker] = mark_price(ctx, ticker, day, previous_prices.get(ticker))
                if not started:
                    started = True
                    previous_benchmark = mark_price(ctx, ctx.benchmark, day)
                if len(positions) > cfg["maximumHoldings"]:
                    raise ValueError("REPLAY_HOLDING_CAP")
                if sum(positions.values()) > 1 + 1e-10:
                    raise ValueError("REPLAY_LEVERAGE")
            if started:
                current_multiplier = target
                records.append({"date": day, "nav": nav, "grossNav": gross_nav, "benchmarkNav": benchmark_nav, "cost": cost, "turnover": turnover,
                                "holdings": len(positions), "cashWeight": 1 - sum(positions.values()), "weights": dict(positions), "kind": kind,
                                "signalUnavailable": unavailable, "marketMultiplier": current_multiplier, "replaced": replaced, "added": added,
                                "overlayConstraintBinding": execution["overlayConstraintBinding"] if execution else None,
                                "overlayExcessDueToDeferredExit": execution["overlayExcessDueToDeferredExit"] if execution else None})
    except ValueError as error:
        if str(error).startswith(UNRESOLVED):
            return {"complete": False, "reason": str(error), "architecture": architecture}
        raise
    if len(records) < 252:
        return {"complete": False, "reason": "PORTFOLIO_DEPTH", "architecture": architecture}
    return {"complete": True, "architecture": architecture, "path": records}


# =======================================================================================================================================
# Metrics
# =======================================================================================================================================
def annualize(growth, years):
    return float(growth ** (1.0 / years) - 1.0) if years >= 1 and growth > 0 else None


def _drawdown(nav, dates):
    mdd = K.max_drawdown(pd.Series(nav, dtype=float))
    return {"maxDrawdown": mdd["maxDrawdown"], "peakDate": dates[mdd["peakPos"]], "troughDate": dates[mdd["troughPos"]],
            "recoveryDate": None if mdd["recoveryPos"] is None else dates[mdd["recoveryPos"]], "recoverySessions": mdd["recoverySessions"]}


def episodes_table(nav, dates):
    """Underwater episodes at the sealed depth thresholds (the market anatomy's algorithm), with dates; named dates are never used."""
    episodes = MA.underwater_episodes(pd.Series(nav, dtype=float))
    out = {}
    for threshold in K.EPISODE_THRESHOLDS:
        chosen = MA.episodes_at_least(episodes, threshold)
        out[f"depth_ge_{int(threshold * 100)}pct"] = [{"peakDate": dates[e["peakPos"]], "troughDate": dates[e["troughPos"]],
                                                       "recoveryDate": None if e["recoveryPos"] is None else dates[e["recoveryPos"]],
                                                       "depth": float(e["depth"]), "censored": bool(e["censored"])} for e in chosen]
    return out


def half_table(nav, bench, dates):
    """Chronological halves of the sessions, each rebased; descriptive."""
    mid = (len(nav) - 1) // 2
    out = {}
    for label, lo, hi in (("firstHalf", 0, mid + 1), ("secondHalf", mid, len(nav))):
        n, b = nav[lo:hi], bench[lo:hi]
        years = (pd.Timestamp(dates[hi - 1]) - pd.Timestamp(dates[lo])).days / DAYS_PER_YEAR
        net, passive = annualize(n[-1] / n[0], years), annualize(b[-1] / b[0], years)
        out[label] = {"start": dates[lo], "end": dates[hi - 1], "netAnnualizedReturn": net, "passiveAnnualizedReturn": passive,
                      "excessAnnualizedVsPassive": None if net is None or passive is None else net - passive,
                      "maxDrawdown": _drawdown(list(np.asarray(n) / n[0]), dates[lo:hi])["maxDrawdown"]}
    return out


def calendar_year_table(nav, bench, dates):
    out, previous_nav, previous_bench = {}, nav[0], bench[0]
    years = pd.Series(range(len(dates))).groupby(pd.DatetimeIndex(dates).year).max()
    for year, position in years.items():
        out[str(year)] = {"net": float(nav[position] / previous_nav - 1), "passive": float(bench[position] / previous_bench - 1)}
        out[str(year)]["excess"] = out[str(year)]["net"] - out[str(year)]["passive"]
        previous_nav, previous_bench = nav[position], bench[position]
    return out


def summarize_path(path, nav_override=None):
    """Every registered metric of one complete path. `nav_override` re-values the SAME path with another NAV series (cash-yield sensitivity): only
    the return metrics are recomputed from it; names, weights, trades and turnover are the primary path's."""
    dates = [path[0]["date"]] + [r["date"] for r in path]
    nav = np.asarray([1.0] + (nav_override if nav_override is not None else [r["nav"] for r in path]), float)
    gross = np.asarray([1.0] + [r["grossNav"] for r in path], float)
    bench = np.asarray([1.0] + [r["benchmarkNav"] for r in path], float)
    returns = nav[1:] / nav[:-1] - 1
    years = (pd.Timestamp(path[-1]["date"]) - pd.Timestamp(path[0]["date"])).days / DAYS_PER_YEAR
    net, grs, passive = annualize(nav[-1], years), annualize(gross[-1], years), annualize(bench[-1], years)
    drawdown = _drawdown(list(nav), dates)
    weights = [r["weights"] for r in path if r["weights"]]
    herfindahl = [sum((w / sum(v.values())) ** 2 for w in v.values()) for v in weights]
    max_weight = [max(v.values()) for v in weights]
    anchor_rows = [r for r in path if r["kind"] == "ANCHOR"]
    replaced = sum(r["replaced"] for r in anchor_rows)
    summary = {
        "complete": True, "sessions": len(path), "firstDate": path[0]["date"], "lastDate": path[-1]["date"], "years": float(years),
        "cumulativeNetReturn": float(nav[-1] - 1), "cumulativeGrossReturn": float(gross[-1] - 1), "cumulativePassiveReturn": float(bench[-1] - 1),
        "netAnnualizedReturn": net, "grossAnnualizedReturn": grs, "passiveAnnualizedReturn": passive,
        "excessAnnualizedVsPassive": None if net is None or passive is None else net - passive, "terminalExcessVsPassive": float(nav[-1] / bench[-1] - 1),
        "annualizedCostDrag": None if net is None or grs is None else grs - net, "terminalCostDrag": float(gross[-1] - nav[-1]),
        **drawdown, **{f"worstRollingReturnH{h}": K.worst_rolling_return(nav, h) for h in K.ROLLING_LOSS_HORIZONS},
        "annualizedVolatility": float(np.std(returns, ddof=1) * math.sqrt(ANNUALISATION)), "downsideVolatility": K.downside_volatility(returns),
        "totalOneWayTurnover": float(sum(r["turnover"] for r in path)), "annualizedOneWayTurnover": float(sum(r["turnover"] for r in path) / years),
        "totalCostFractionOfNav": float(sum(r["cost"] for r in path)), "replacements": int(replaced), "annualizedReplacements": float(replaced / years),
        "anchorRebalances": len(anchor_rows), "noTradeSignalUnavailableAnchors": sum(1 for r in path if r.get("signalUnavailable")),
        "sessionsFullyInCashBeforeFirstValidDecision": next((i for i, r in enumerate(path) if r["kind"] == "ANCHOR"), len(path)), "marketScaleTrades": sum(1 for r in path if r["kind"] == "MARKET"),
        "averageHoldings": float(np.mean([r["holdings"] for r in path])), "averageCashShare": float(np.mean([r["cashWeight"] for r in path])),
        "averageGrossEquityExposure": float(np.mean([1 - r["cashWeight"] for r in path])),
        "meanHerfindahl": float(np.mean(herfindahl)) if herfindahl else None, "meanMaxWeight": float(np.mean(max_weight)) if max_weight else None,
        "maxSecurityWeight": float(max(max_weight)) if max_weight else None,
        "reducedSessionShare": float(np.mean([r["marketMultiplier"] < 1.0 for r in path])),
        "halves": half_table(list(nav), list(bench), dates), "calendarYears": calendar_year_table(list(nav), list(bench), dates),
        "episodes": episodes_table(list(nav), dates)}
    return summary


def passive_summary(path):
    """The passive reference (069500.KS, the repository's accepted return basis) over the same sessions; never a candidate."""
    dates = [path[0]["date"]] + [r["date"] for r in path]
    bench = np.asarray([1.0] + [r["benchmarkNav"] for r in path], float)
    returns = bench[1:] / bench[:-1] - 1
    years = (pd.Timestamp(path[-1]["date"]) - pd.Timestamp(path[0]["date"])).days / DAYS_PER_YEAR
    return {"id": M.PASSIVE, "returnBasis": M.RETURN_BASIS, "cumulativeReturn": float(bench[-1] - 1), "annualizedReturn": annualize(bench[-1], years),
            "annualizedVolatility": float(np.std(returns, ddof=1) * math.sqrt(ANNUALISATION)), "downsideVolatility": K.downside_volatility(returns),
            "worstRollingReturnH63": K.worst_rolling_return(bench, 63), "worstRollingReturnH126": K.worst_rolling_return(bench, 126),
            **_drawdown(list(bench), dates), "episodes": episodes_table(list(bench), dates),
            "note": "adjusted-index return with partial distributions: neither a price return nor a complete shareholder total return; no entry cost is charged"}


def cash_sensitivity(path, events):
    """The primary path re-valued with residual cash earning the frozen Bank of Korea base-rate proxy. Reads the path; changes none of it."""
    out = {}
    for variant in M.CASH_YIELD["variants"]:
        nav = M.cash_overlay_nav(path, events, variant)
        summary = summarize_path(path, nav_override=nav)
        out[variant] = {k: summary[k] for k in ("netAnnualizedReturn", "excessAnnualizedVsPassive", "cumulativeNetReturn", "maxDrawdown", "annualizedVolatility")}
    return out
