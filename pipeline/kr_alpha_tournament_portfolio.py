"""KR alpha discovery tournament v1 — the common translator: risk, the robust long-only fractional-Kelly allocator, the baselines and the
self-financing passive-core ledger.

A portfolio is   passive core (069500.KS)  +  long-only active overweights,   gross <= 1, no leverage, no short, no cash target.
An active name enters only by displacing passive capital: its shrunk expected incremental return must pay its covariance penalty and the cost of
buying it AND selling the passive leg. With nothing worth that, the allocator returns zero active weight and the book stays passive.

Valuing a path is an OUTCOME computation: the execution harness reaches `replay` only behind its permit and durable lock.
"""
from __future__ import annotations

import math

import numpy as np
from sklearn.covariance import LedoitWolf

from . import kr_alpha_tournament as T

UNRESOLVED = "PORTFOLIO_MARK_OR_TERMINAL_ECONOMICS_UNRESOLVED"


# --------------------------------------------------------------------------- #
# Risk inputs (past-only)
# --------------------------------------------------------------------------- #
def risk_inputs(closes, bench_close, horizon=T.PRIMARY_HORIZON, lookback=T.COVARIANCE_LOOKBACK):
    """`closes`: {ticker: array of the `lookback + 1` closes ENDING AT the signal session}; `bench_close` the same for 069500.KS.
    Returns tickers with a complete window (sorted), the Ledoit-Wolf covariance of daily ACTIVE returns and each active return's covariance with
    the benchmark, both scaled to the horizon. A name without a complete window is absent (never filled)."""
    b = np.asarray(bench_close, float)
    if len(b) != lookback + 1 or not np.isfinite(b).all() or (b <= 0).any():
        return {"tickers": [], "cov": np.zeros((0, 0)), "ceb": np.zeros(0)}
    rb = np.diff(b) / b[:-1]
    names, cols = [], []
    for t in sorted(closes):
        c = np.asarray(closes[t], float)
        if len(c) == lookback + 1 and np.isfinite(c).all() and (c > 0).all():
            names.append(t)
            cols.append(np.diff(c) / c[:-1] - rb)
    if not names:
        return {"tickers": [], "cov": np.zeros((0, 0)), "ceb": np.zeros(0)}
    E = np.column_stack(cols)
    cov = LedoitWolf().fit(E).covariance_ * horizon
    ceb = np.array([np.cov(E[:, j], rb, ddof=1)[0, 1] for j in range(E.shape[1])]) * horizon
    return {"tickers": names, "cov": cov, "ceb": ceb}


def unit_costs(stress=1.0, cfg=T.PORTFOLIO, passive=T.PASSIVE_LEG):
    """Linear cost of moving one unit of NAV from the passive leg into a stock (buy) and back (sell)."""
    return (stress * (cfg["buyFixedCost"] + passive["costEachWay"]), stress * (cfg["sellFixedCost"] + passive["costEachWay"]))


def trade_box(w0, adv, nav_krw, cfg=T.PORTFOLIO, adv_multiplier=1.0):
    """[lower, upper] per name: the holding cap min(singleNameCap, f x ADV60 / NAV) and the per-trade participation limit f x ADV60 / NAV."""
    lim = np.array([cfg["maximumAdvFraction"] * adv_multiplier * a / nav_krw if a is not None and np.isfinite(a) and a > 0 else 0.0 for a in adv])
    cap = np.minimum(cfg["singleNameCap"], lim)
    lower = np.maximum(0.0, w0 - lim)
    upper = np.maximum(np.minimum(cap, w0 + lim), lower)
    return lower, upper


# --------------------------------------------------------------------------- #
# The allocator
# --------------------------------------------------------------------------- #
def _prox(v, eta, w0, cb, cs, lower, upper):
    w = np.where(v - eta * cb > w0, v - eta * cb, np.where(v + eta * cs < w0, v + eta * cs, w0))
    return np.clip(w, lower, upper)


def _prox_budget(v, eta, w0, cb, cs, lower, upper):
    w = _prox(v, eta, w0, cb, cs, lower, upper)
    if w.sum() <= 1.0 + 1e-15:
        return w
    if eta <= 0.0:
        # the starting-point projection (eta = 0) of a held book that is fully invested up to rounding: bisect the budget shift directly,
        # since the multiplier parameterisation below divides by eta
        lo, hi = 0.0, float(np.max(v)) + 1.0
        for _ in range(200):
            mid = (lo + hi) / 2
            if _prox(v - mid, eta, w0, cb, cs, lower, upper).sum() > 1.0:
                lo = mid
            else:
                hi = mid
        return _prox(v - hi, eta, w0, cb, cs, lower, upper)
    lo, hi = 0.0, (float(np.max(v)) + 1.0) / eta + 1.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if _prox(v - eta * mid, eta, w0, cb, cs, lower, upper).sum() > 1.0:
            lo = mid
        else:
            hi = mid
    return _prox(v - eta * hi, eta, w0, cb, cs, lower, upper)


def objective(w, mu, cov, ceb, w0, cb, cs, kelly=T.ALLOCATOR["kellyFraction"]):
    return float(w @ (mu - ceb) - 0.5 / kelly * w @ cov @ w - cb @ np.maximum(w - w0, 0) - cs @ np.maximum(w0 - w, 0))


def allocate(mu, cov, ceb, w0, cb, cs, lower, upper, kelly=T.ALLOCATOR["kellyFraction"], max_iter=T.ALLOCATOR_MAX_ITER, tol=T.ALLOCATOR_TOL):
    """argmax  w'(mu - ceb) - 1/(2 kelly) w' cov w - cb'(w - w0)+ - cs'(w0 - w)+   s.t. lower <= w <= upper, sum w <= 1.
    FISTA with the exact prox; deterministic. Returns (weights, info)."""
    n = len(mu)
    if n == 0:
        return np.zeros(0), {"iterations": 0, "converged": True}
    mu, cov, ceb, w0 = (np.asarray(x, float) for x in (mu, cov, ceb, w0))
    cb, cs = np.broadcast_to(np.asarray(cb, float), (n,)), np.broadcast_to(np.asarray(cs, float), (n,))
    if not (np.isfinite(mu).all() and np.isfinite(cov).all() and np.isfinite(ceb).all()):
        raise ValueError("NON_FINITE_ALLOCATOR_INPUT")
    Q = (cov + cov.T) / 2 / kelly
    L = max(float(np.linalg.eigvalsh(Q)[-1]), 1e-12)
    eta = 1.0 / L
    g = mu - ceb
    x = _prox_budget(np.clip(w0, lower, upper), 0.0, w0, cb, cs, lower, upper)
    y, t, converged, k = x.copy(), 1.0, False, 0
    for k in range(1, max_iter + 1):
        x_new = _prox_budget(y - eta * (Q @ y - g), eta, w0, cb, cs, lower, upper)
        t_new = (1 + math.sqrt(1 + 4 * t * t)) / 2
        y = x_new + ((t - 1) / t_new) * (x_new - x)
        step = float(np.max(np.abs(x_new - x)))
        x, t = x_new, t_new
        if step < tol:
            converged = True
            break
    if (x < lower - 1e-12).any() or (x > upper + 1e-12).any() or x.sum() > 1 + 1e-9:
        raise ValueError("ALLOCATOR_CONSTRAINT_VIOLATION")
    x = np.where(x < 1e-12, 0.0, x)
    return x, {"iterations": k, "converged": converged, "objective": objective(x, mu, cov, ceb, w0, cb, cs, kelly)}


def baseline_equal_weight(mu_post, cb, cs, lower, upper):
    """Baseline 1: every name whose shrunk expected incremental return exceeds its round-trip active cost (the primary's own admission arithmetic, no
    new threshold), each at min(1/n, its box), passive residual."""
    mu_post = np.asarray(mu_post, float)
    admit = mu_post > (np.asarray(cb) + np.asarray(cs))
    n = int(admit.sum())
    w = np.clip(np.where(admit, 1.0 / n if n else 0.0, 0.0), lower, upper)
    if w.sum() > 1.0:
        w = lower + (w - lower) * max(0.0, 1.0 - lower.sum()) / max((w - lower).sum(), 1e-300)
    return w


# --------------------------------------------------------------------------- #
# Self-financing passive-core ledger (daily). An OUTCOME function.
# --------------------------------------------------------------------------- #
def trading_cost(before, after, adv, nav_krw, stress=1.0, cfg=T.PORTFOLIO, passive=T.PASSIVE_LEG):
    """Cost as a fraction of pre-trade NAV for moving `before` -> `after` (amounts in units of pre-trade NAV; key BENCHMARK is the passive leg).
    Stocks: fixed buy/sell cost plus square-root impact on actual executed KRW notional (the sealed schedule). Passive leg: costEachWay, no impact."""
    total = 0.0
    for t in sorted(set(before) | set(after)):
        delta = after.get(t, 0.0) - before.get(t, 0.0)
        if delta == 0:
            continue
        if t == T.BENCHMARK:
            total += abs(delta) * passive["costEachWay"]
            continue
        value = adv.get(t)
        if value is None or not np.isfinite(value) or value <= 0:
            raise ValueError("MISSING_EXECUTABLE_LIQUIDITY: " + t)
        participation = abs(delta) * nav_krw / value
        fixed = cfg["buyFixedCost"] if delta > 0 else cfg["sellFixedCost"]
        total += abs(delta) * (fixed + cfg["impactAtOnePercent"] * math.sqrt(participation / 0.01))
    return stress * total


def execute(before, target_stock, adv, nav_krw, stress=1.0, fixed=()):
    """Exact close ledger. `before`: {ticker or BENCHMARK: amount} in units of pre-trade NAV (cash is 1 - sum); `target_stock`: {ticker: weight of
    POST-cost NAV} for the tradable names; `fixed`: held names that cannot trade today and keep their exact amount; the passive leg takes the
    remainder. Solves the post-cost NAV factor k with k + cost(k) = pre-trade NAV by bisection, so every cost is paid from the book itself
    (self-financing: no external cash, no leverage, no negative leg)."""
    if any(w < 0 for w in target_stock.values()):
        raise ValueError("NEGATIVE_TARGET")
    pre = 1.0
    held_fixed = {t: before[t] for t in fixed if before.get(t, 0) > 0}
    stock_total = sum(target_stock.values())

    def after(k):
        scale = 1.0
        room = k - sum(held_fixed.values())
        if stock_total * k > room:
            scale = max(0.0, room) / (stock_total * k) if stock_total > 0 else 0.0
        out = {t: w * k * scale for t, w in target_stock.items() if w > 0}
        out.update(held_fixed)
        out[T.BENCHMARK] = max(0.0, k - sum(out.values()))
        return out

    lo, hi = 0.0, pre
    for _ in range(100):
        mid = (lo + hi) / 2
        if mid + trading_cost(before, after(mid), adv, nav_krw, stress) > pre:
            hi = mid
        else:
            lo = mid
    k = lo
    amounts = after(k)
    cost = trading_cost(before, amounts, adv, nav_krw, stress)
    if k <= 0 or k + cost > pre + 1e-9:
        raise ValueError("UNFUNDED_TRANSACTION_COSTS")
    turnover = sum(abs(amounts.get(t, 0.0) - before.get(t, 0.0)) for t in set(before) | set(amounts)) / 2
    # the passive leg stays a key even at weight 0 (a fully invested book, sum w = 1, is a registered state): the next session's benchmark return
    # is read from it, and dropping the key made that read raise KeyError
    return {"weights": {t: a / k for t, a in amounts.items() if a > 0 or t == T.BENCHMARK}, "navFactor": k, "costFraction": cost,
            "turnover": turnover}


def replay(days, start, end, mark, executable, adv_of, decide, stress=1.0, delay=0, nav0_krw=T.PORTFOLIO["referenceNavKrw"]):
    """Value one path daily from `start` (the first outer anchor, already 100% passive) through `end`.

    `mark(ticker, day, previous)` -> close or raises UNRESOLVED; `executable(ticker, day)` -> bool; `adv_of(ticker, day)` -> ADV60 or None;
    `decide(day, pre_trade_weights, nav_krw)` -> {ticker: target weight} or None (no trade; the caller answers only on its anchor days); the
    trade executes `delay` sessions later at that session's close. Returns the daily record or an incomplete marker."""
    days = [d for d in days if start <= d <= end]
    if not days:
        raise ValueError("EMPTY_REPLAY_WINDOW")
    weights = {T.BENCHMARK: 1.0}
    prices = {T.BENCHMARK: mark(T.BENCHMARK, days[0], None)}
    nav, record, pending = 1.0, [], {}
    contributions = {}
    for i, day in enumerate(days):
        if i:
            gross, new_values, prev_bench = 0.0, {}, prices[T.BENCHMARK]
            try:
                current = {t: mark(t, day, prices[t]) for t in sorted(weights)}
            except ValueError as error:
                if UNRESOLVED in str(error):
                    return {"complete": False, "reason": str(error), "path": record}
                raise
            rb = current[T.BENCHMARK] / prev_bench - 1.0
            for t, w in weights.items():
                r = current[t] / prices[t] - 1.0
                new_values[t] = w * (1 + r)
                gross += w * r
                if t != T.BENCHMARK:
                    contributions[t] = contributions.get(t, 0.0) + w * (r - rb)
            cash = 1.0 - sum(weights.values())
            total = sum(new_values.values()) + cash
            weights = {t: v / total for t, v in new_values.items()}
            prices = current
            nav *= 1 + gross
        else:
            rb = 0.0
        if decide is not None:
            target = decide(day, dict(weights), nav * nav0_krw)
            if target is not None:
                exec_index = i + delay
                if exec_index < len(days):
                    pending[days[exec_index]] = (day, target)
        trade = None
        due = pending.pop(day, None)
        if due is not None:
            decision_day, target = due
            def can_trade(name):
                value = adv_of(name, day) if executable(name, day) else None
                return value is not None and np.isfinite(value) and value > 0

            tradable = {}
            for t, w in sorted(target.items()):
                if w > 0 and can_trade(t):
                    try:
                        price = prices[t] if t in prices else mark(t, day, None)
                    except ValueError:
                        continue
                    prices[t] = price
                    tradable[t] = w
            fixed = [t for t in weights if t != T.BENCHMARK and not can_trade(t)]      # deferred: no quote or no liquidity measure today
            moving = [t for t in set(tradable) | set(weights) if t != T.BENCHMARK and t not in fixed]
            adv = {t: adv_of(t, day) for t in moving}
            executed = execute(dict(weights), tradable, adv, nav * nav0_krw, stress, fixed=fixed)
            nav *= executed["navFactor"]
            weights = dict(executed["weights"])
            for t in list(prices):
                if t not in weights and t != T.BENCHMARK:
                    prices.pop(t)
            trade = {"decisionDay": decision_day, "costFraction": executed["costFraction"], "turnover": executed["turnover"],
                     "deferred": sorted(fixed)}
        active = {t: w for t, w in weights.items() if t != T.BENCHMARK}
        record.append({"date": day, "nav": nav, "benchmarkReturn": rb, "activeWeight": sum(active.values()), "activeNames": len(active),
                       "maxActiveWeight": max(active.values()) if active else 0.0,
                       "activeHhi": sum(w * w for w in active.values()), "trade": trade})
    return {"complete": True, "path": record, "contributions": contributions}
