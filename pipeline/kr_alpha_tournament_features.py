"""KR alpha discovery tournament v1 — signal-time features and their target-agnostic representations.

Everything here reads values at or before the signal date. Nothing reads a label, a forward price or an outcome. Representations are per-date
cross-sectional transforms (no cross-date fit), so they cannot leak a later date into an earlier one; the only fitted transform (standardisation of the
linear design) is fitted on training rows inside the model module.

The sealed instruments are REUSED, never copied: percentiles (`kr_factor_anatomy.pct_rank`), within-industry percentiles
(`kr_stock_within_industry_anatomy.within_industry_percentiles`).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import kr_alpha_tournament as T
from . import kr_factor_anatomy as A
from . import kr_stock_within_industry_anatomy as S


# --------------------------------------------------------------------------- #
# Raw derived features from past-only arrays (the execution harness feeds them; synthetic tests feed invented arrays)
# --------------------------------------------------------------------------- #
def _finite(a):
    return a is not None and len(a) and np.isfinite(a).all() and (a > 0).all()


def derived_price_features(close, bench):
    """`close` and `bench` are the replay Close values of the stock and 069500.KS for the sessions ENDING AT the signal session (last element = signal
    close), oldest first, aligned. Each feature needs its own full finite window; otherwise it is None (never filled)."""
    close = np.asarray(close, float)
    bench = np.asarray(bench, float)
    out = dict.fromkeys(("ret21", "ret63", "dist252High", "ma200Distance", "vol63", "beta252", "maxDrawdown252"))
    n = len(close)
    if n >= 22 and _finite(close[-22:]):
        out["ret21"] = float(close[-1] / close[-22] - 1.0)
    if n >= 64 and _finite(close[-64:]):
        out["ret63"] = float(close[-1] / close[-64] - 1.0)
        r = np.diff(close[-64:]) / close[-64:-1]
        out["vol63"] = float(np.std(r, ddof=1) * math.sqrt(252))
    if n >= 252 and _finite(close[-252:]):
        window = close[-252:]
        out["dist252High"] = float(close[-1] / window.max() - 1.0)
        out["maxDrawdown252"] = float(np.min(window / np.maximum.accumulate(window) - 1.0))
    if n >= 200 and _finite(close[-200:]):
        out["ma200Distance"] = float(close[-1] / close[-200:].mean() - 1.0)
    if n >= 253 and len(bench) >= 253 and _finite(close[-253:]) and _finite(bench[-253:]):
        r = np.diff(close[-253:]) / close[-253:-1]
        b = np.diff(bench[-253:]) / bench[-253:-1]
        var = float(np.var(b, ddof=1))
        if var > 0:
            out["beta252"] = float(np.cov(r, b, ddof=1)[0, 1] / var)
    return out


def liquidity_features(trailing, market_cap):
    """`trailing`: the 60 most recent KRX quotes (oldest first) ending at the signal date, each {volume, tradingValue} or None; `market_cap` at the
    signal date. Magnitude-preserving: a 2x and a 15x shock stay different."""
    out = {"logVolumeShock5_60": None, "logAmihud60": None, "logMarketCap": None}
    if market_cap is not None and np.isfinite(market_cap) and market_cap > 0:
        out["logMarketCap"] = float(math.log(market_cap))
    if len(trailing) == 60 and all(q is not None and q.get("tradingValue") is not None and q["tradingValue"] > 0 for q in trailing):
        tv = np.array([q["tradingValue"] for q in trailing], float)
        out["logVolumeShock5_60"] = float(math.log(tv[-5:].mean() / tv.mean()))
    return out


def amihud(close, trading_values):
    """log mean(|daily return| / KRW traded value) over the last 60 sessions, both aligned and ending at the signal date; None unless complete."""
    close = np.asarray(close, float)
    tv = np.asarray(trading_values, float)
    if len(close) < 61 or len(tv) < 60 or not _finite(close[-61:]) or not _finite(tv[-60:]):
        return None
    r = np.abs(np.diff(close[-61:]) / close[-61:-1])
    value = float(np.mean(r / tv[-60:]))
    return float(math.log(value)) if value > 0 else None


def loo_industry_momentum(ticker, peers, trail126, caps):
    """Stock trailing-126 return minus the cap-weighted trailing-126 return of its industry PEERS (the stock excluded). None unless every peer has a
    finite trailing return and a positive signal-date cap (the sealed stock-within-industry rule, applied to the past)."""
    if not peers or ticker not in trail126 or not np.isfinite(trail126[ticker]):
        return None
    values, weights = [], []
    for p in peers:
        r, c = trail126.get(p, np.nan), caps.get(p, np.nan)
        if r is None or c is None or not np.isfinite(r) or not np.isfinite(c) or c <= 0:
            return None
        values.append(r)
        weights.append(c)
    w = np.asarray(weights) / math.fsum(weights)
    return float(trail126[ticker] - float(np.dot(w, values)))


# --------------------------------------------------------------------------- #
# Representations
# --------------------------------------------------------------------------- #
def robust_z(values):
    x = A.clean_numeric(values)
    out = np.full(len(x), np.nan)
    ok = np.isfinite(x)
    if ok.sum() < T.ROBUST_Z_MIN_FINITE:
        return out
    med = float(np.median(x[ok]))
    mad = float(np.median(np.abs(x[ok] - med))) * 1.4826
    if not mad > 0:
        return out
    out[ok] = np.clip((x[ok] - med) / mad, -T.ROBUST_Z_CLIP, T.ROBUST_Z_CLIP)
    return out


def represent(frame):
    """Add every registered representation to a signal-time panel.

    `frame` columns: date, ticker, industry (NaN when unclassified), industryEligible (bool: member of an eligible v4 cohort), every STOCK_FEATURES
    raw value, `ind_<f>` (the raw value of industry feature f of the stock's industry on that date, NaN if none) and MARKET_FEATURES. Rows are
    processed per date; the output does not depend on row order (sorted by date, ticker)."""
    out = frame.sort_values(["date", "ticker"]).reset_index(drop=True).copy()
    cols = {}
    for f in T.STOCK_FEATURES:
        raw = A.clean_numeric(out[f]) if f in out else np.full(len(out), np.nan)
        cols["m_" + f] = (~np.isfinite(raw)).astype(float)
        z = np.full(len(out), np.nan)
        p = np.full(len(out), np.nan)
        for idx in out.groupby("date", sort=True).indices.values():
            z[idx] = robust_z(raw[idx])
            p[idx] = A.pct_rank(raw[idx])
        cols["z_" + f], cols["p_" + f] = z, p
    eligible = out[out.get("industryEligible", False).astype(bool)] if "industryEligible" in out else out.iloc[0:0]
    wi = {f: np.full(len(out), np.nan) for f in T.STOCK_FEATURES}
    if len(eligible):
        ranked = S.within_industry_percentiles(eligible[["date", "industry", "ticker", *T.STOCK_FEATURES]], columns=T.STOCK_FEATURES)
        position = {(d, t): i for i, (d, t) in enumerate(zip(out.date, out.ticker))}
        rows = np.array([position[(d, t)] for d, t in zip(ranked.date, ranked.ticker)], int)
        for f in T.STOCK_FEATURES:
            wi[f][rows] = ranked["wi_" + f].to_numpy(float)
    for f in T.STOCK_FEATURES:
        cols["w_" + f] = wi[f]
    for f in T.INDUSTRY_FEATURES:
        raw = A.clean_numeric(out["ind_" + f]) if "ind_" + f in out else np.full(len(out), np.nan)
        pct = np.full(len(out), np.nan)
        for idx in out.groupby("date", sort=True).indices.values():
            sub = out.iloc[idx]
            per_industry = {}
            for ind, value in zip(sub.industry, raw[idx]):
                if isinstance(ind, str) and np.isfinite(value):
                    per_industry[ind] = value
            if len(per_industry) >= T.INDUSTRY_MIN_RANKED:
                names = sorted(per_industry)
                ranks = dict(zip(names, A.pct_rank(np.array([per_industry[n] for n in names]))))
                pct[idx] = [ranks.get(ind, np.nan) if isinstance(ind, str) else np.nan for ind in sub.industry]
        cols["i_" + f] = pct
        cols["im_" + f] = (~np.isfinite(pct)).astype(float)
    for f in T.MARKET_FEATURES:
        cols["mkt_" + f] = A.clean_numeric(out[f]) if f in out else np.full(len(out), np.nan)
    return pd.concat([out, pd.DataFrame(cols, index=out.index)], axis=1)


def linear_columns():
    names = []
    for f in T.STOCK_FEATURES:
        names += ["z_" + f, "pc_" + f, "wc_" + f, "m_" + f]
    for f in T.INDUSTRY_FEATURES:
        names += ["ic_" + f, "im_" + f]
    names += ["mkt_" + f for f in T.MARKET_FEATURES]
    names += [a + "*" + b for a, b in T.INTERACTIONS]
    return names


def tree_columns():
    names = []
    for f in T.STOCK_FEATURES:
        names += ["z_" + f, "p_" + f, "w_" + f]
    names += ["i_" + f for f in T.INDUSTRY_FEATURES]
    names += ["mkt_" + f for f in T.MARKET_FEATURES]
    return names


def linear_design(rep):
    """Centred, zero-filled representations beside missingness indicators, plus the registered context interactions. No fitted quantity."""
    cols = {}
    for f in T.STOCK_FEATURES:
        cols["z_" + f] = np.nan_to_num(rep["z_" + f].to_numpy(float), nan=0.0)
        cols["pc_" + f] = np.nan_to_num(rep["p_" + f].to_numpy(float) - 0.5, nan=0.0)
        cols["wc_" + f] = np.nan_to_num(rep["w_" + f].to_numpy(float) - 0.5, nan=0.0)
        cols["m_" + f] = rep["m_" + f].to_numpy(float)
    for f in T.INDUSTRY_FEATURES:
        cols["ic_" + f] = np.nan_to_num(rep["i_" + f].to_numpy(float) - 0.5, nan=0.0)
        cols["im_" + f] = rep["im_" + f].to_numpy(float)
    for f in T.MARKET_FEATURES:
        cols["mkt_" + f] = np.nan_to_num(rep["mkt_" + f].to_numpy(float), nan=0.0)
    for a, b in T.INTERACTIONS:
        cols[a + "*" + b] = cols[a] * cols[b]
    names = linear_columns()
    return np.column_stack([cols[n] for n in names]).astype(float), names


def tree_design(rep):
    names = tree_columns()
    return np.column_stack([rep[n].to_numpy(float) for n in names]).astype(float), names
