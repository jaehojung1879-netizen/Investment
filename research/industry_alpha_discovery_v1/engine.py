"""Outcome engine: forward excess returns, HAC/block-bootstrap inference and fixed-exposure tilt strategies.

Nothing here chooses a threshold, horizon or definition; every one is a parameter fixed in protocol.json before the
first call on real data. Prices are total-return closes on the KODEX 200 (069500.KS) session calendar.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy import stats

# Sealed KR cost schedule inherited from research_specs/alpha-opportunity-model-v5.json (carriedFromV3.transactionCosts).
COMMISSION_BPS = 1.5
SPREAD_BPS = 8.0
SELL_TAX = [("1900-01-01", 30.0), ("2019-06-03", 25.0), ("2021-01-01", 23.0), ("2023-01-01", 20.0),
            ("2024-01-01", 18.0), ("2025-01-01", 15.0), ("2026-01-01", 20.0)]


def sell_tax_bps(day) -> float:
    d = str(pd.Timestamp(day).date())
    return max((r for r in SELL_TAX if r[0] <= d), key=lambda r: r[0])[1]


def stock_cost(delta: float, day) -> float:
    """Cost (fraction of NAV) of changing a stock weight by `delta`; buy: commission + half spread; sell adds tax."""
    half = SPREAD_BPS / 2
    bps = COMMISSION_BPS + half + (sell_tax_bps(day) if delta < 0 else 0.0)
    return abs(delta) * bps / 1e4


def etf_cost(delta: float) -> float:
    """KODEX 200 is exempt from the securities transaction tax."""
    return abs(delta) * (COMMISSION_BPS + SPREAD_BPS / 2) / 1e4


class Market:
    def __init__(self, closes: pd.DataFrame, bench: str = "069500.KS"):
        c = closes.dropna(subset=[bench]).sort_index()
        self.close = c.ffill()
        self.bench = bench
        self.sessions = c.index

    def entry_session(self, published, same_day: bool = False):
        """First session strictly after the publication date (default), or the publication day itself."""
        p = pd.Timestamp(published)
        idx = self.sessions.searchsorted(p, side="left" if same_day else "right")
        return None if idx >= len(self.sessions) else idx

    def basket_return(self, names, i0: int, i1: int) -> float | None:
        """Equal-weight buy-and-hold over sessions i0 -> i1 (weights set at i0 and left to drift)."""
        if i1 >= len(self.sessions):
            return None
        r = []
        for n in names:
            a, b = self.close[n].iloc[i0], self.close[n].iloc[i1]
            if not (np.isfinite(a) and np.isfinite(b)) or a <= 0:
                return None
            r.append(b / a - 1)
        return float(np.mean(r))

    def excess(self, names, i0: int, i1: int) -> float | None:
        a, b = self.basket_return(names, i0, i1), self.basket_return([self.bench], i0, i1)
        return None if a is None or b is None else a - b

    def absolute(self, names, i0: int, i1: int) -> float | None:
        return self.basket_return(names, i0, i1)


def ols_hac(y, X, lags: int) -> dict:
    """OLS with Newey-West (Bartlett) standard errors."""
    y = np.asarray(y, float)
    X = np.column_stack([np.ones(len(y)), np.asarray(X, float).reshape(len(y), -1)]) if np.size(X) else np.ones((len(y), 1))
    n, k = X.shape
    if n <= k + 2:
        return {"n": n, "status": "NOT_ESTIMABLE"}
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    e = y - X @ beta
    xe = X * e[:, None]
    S = xe.T @ xe
    for L in range(1, min(lags, n - 1) + 1):
        w = 1 - L / (lags + 1)
        G = xe[L:].T @ xe[:-L]
        S += w * (G + G.T)
    XtXi = np.linalg.inv(X.T @ X)
    V = XtXi @ S @ XtXi * n / (n - k)
    se = np.sqrt(np.maximum(np.diag(V), 0))
    t = beta / se
    df = max(n - k, 1)
    return {"n": n, "coef": beta.tolist(), "se": se.tolist(), "t": t.tolist(),
            "p": (2 * stats.t.sf(np.abs(t), df)).tolist(), "lags": lags,
            "ci95": [[b - stats.t.ppf(.975, df) * s, b + stats.t.ppf(.975, df) * s] for b, s in zip(beta, se)]}


def block_bootstrap_diff(y, flag, block: int, reps: int = 4000, seed: int = 20261122) -> dict:
    """Mean(y | flag) - mean(y | not flag) with a moving-block bootstrap over the event order (keeps overlap)."""
    y, flag = np.asarray(y, float), np.asarray(flag, bool)
    n = len(y)
    if flag.sum() < 3 or (~flag).sum() < 3:
        return {"status": "NOT_ESTIMABLE", "nOn": int(flag.sum()), "nOff": int((~flag).sum())}
    est = y[flag].mean() - y[~flag].mean()
    rng = np.random.default_rng(seed)
    b = max(1, min(block, n))
    starts = np.arange(n - b + 1)
    draws = []
    for _ in range(reps):
        idx = np.concatenate([np.arange(s, s + b) for s in rng.choice(starts, math.ceil(n / b))])[:n]
        yy, ff = y[idx], flag[idx]
        if ff.sum() and (~ff).sum():
            draws.append(yy[ff].mean() - yy[~ff].mean())
    d = np.asarray(draws)
    return {"estimate": float(est), "ci95": [float(np.quantile(d, .025)), float(np.quantile(d, .975))],
            "nOn": int(flag.sum()), "nOff": int((~flag).sum()), "block": b, "reps": len(d)}


def holm(pvals: dict[str, float]) -> dict[str, float]:
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m, run, out = len(items), 0.0, {}
    for i, (k, p) in enumerate(items):
        run = max(run, min(1.0, (m - i) * p))
        out[k] = run
    return out


def tilt_path(mkt: Market, names, decisions: pd.DataFrame, tilt: float, start=None, end=None) -> dict:
    """Daily NAV of KODEX 200 plus a `tilt` sleeve in the equal-weight basket while the signal is ON.

    `decisions` has columns `entryIdx` (session index the new state is executed at the close) and `on` (bool). Equity
    exposure is 100% in both states; the sleeve is rebalanced to target only when the state changes (it drifts
    otherwise) and costs are charged on every executed weight change. Returns NAV, the path's weights and turnover.
    """
    dec = decisions.dropna(subset=["entryIdx"]).sort_values("entryIdx")
    dec = dec.drop_duplicates("entryIdx", keep="last")
    i0 = int(dec["entryIdx"].iloc[0]) if start is None else start
    i1 = len(mkt.sessions) - 1 if end is None else end
    state = dict(zip(dec["entryIdx"].astype(int), dec["on"].astype(bool)))
    cols = [mkt.bench] + list(names)
    px = mkt.close[cols].iloc[i0:i1 + 1].to_numpy(float)
    rets = px[1:] / px[:-1] - 1
    w = np.zeros(len(cols))
    w[0] = 1.0
    nav, navs, turnover, on, days_on = 1.0, [1.0], 0.0, False, 0
    dates = mkt.sessions[i0:i1 + 1]
    for t in range(len(dates)):
        gi = i0 + t
        if gi in state and state[gi] != on:
            on = state[gi]
            target = np.zeros(len(cols))
            target[0] = 1 - tilt if on else 1.0
            if on:
                target[1:] = tilt / len(names)
            delta = target - w
            cost = etf_cost(delta[0]) + sum(stock_cost(d, dates[t]) for d in delta[1:])
            nav *= 1 - cost
            turnover += 0.5 * np.abs(delta).sum()
            w = target
            navs[-1] = nav
        if t < len(rets):
            g = w * (1 + rets[t])
            nav *= g.sum()
            w = g / g.sum()
            navs.append(nav)
            days_on += int(on)
    s = pd.Series(navs, index=dates)
    return {"nav": s, "turnover": turnover, "shareOn": days_on / max(len(rets), 1)}


def path_stats(nav: pd.Series) -> dict:
    years = (nav.index[-1] - nav.index[0]).days / 365.25
    cagr = nav.iloc[-1] ** (1 / years) - 1 if years > 0 else None
    dd = (nav / nav.cummax() - 1).min()
    r = nav.pct_change().dropna()
    return {"cagr": float(cagr), "mdd": float(dd), "annVol": float(r.std() * math.sqrt(252)),
            "start": str(nav.index[0].date()), "end": str(nav.index[-1].date())}
