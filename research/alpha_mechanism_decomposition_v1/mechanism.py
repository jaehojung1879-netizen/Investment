"""alpha-mechanism-decomposition-v1 — pure attribution primitives (no I/O, no outcome-driven choice).

Every function here takes plain pandas / numpy inputs so the tests can hand it an invented market.

THE PERIOD IDENTITY. A book decided at signal date d is executed at the next KR close e_t and held (drifting, no trade) until the next
execution close e_{t+1}. Over that holding period the book's buy-and-hold return is exactly sum_i w_i R_i, where w_i are the
execution-close target weights. For every stock leg the excess over 069500.KS splits exactly into three terms:

    R_i - R_m = (b_i - 1)(R_m - R_f)                             MARKET_BETA     exposure to the ETF's own excess over cash
              + [R_I - R_f - b_I (R_m - R_f)]                    INDUSTRY_ALPHA  the held industry basket's beta-adjusted return
              + [R_i - R_I - (b_i - b_I)(R_m - R_f)]             SELECTION_ALPHA the name against its own industry basket

with b_i the name's PIT 252-session beta at the signal date (F03_beta252), I the name's PIT industry basket on that date (cap-weighted,
quality-eligible members, the name included) and b_I its cap-weighted beta. An ETF leg contributes zero to all three, a cash leg has
b = 0 and contributes only (0 - 1)(R_m - R_f). The identity is asserted on every row.

Summing the three over legs and periods gives the ARITHMETIC excess. The gap between that annualised sum and the CAGR gap is the
compounding term (geometric = arithmetic + compounding). Transaction costs and the engine's suspension/locking mechanics are measured
separately by running the frozen engine with and without costs.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

ETF = "069500.KS"
CASH = "CASH"
TERMS = ("MARKET_BETA", "INDUSTRY_ALPHA", "SELECTION_ALPHA")
IDENTITY_TOL = 1e-10


# --------------------------------------------------------------------------- #
# Calendar helpers
# --------------------------------------------------------------------------- #
def next_session(sessions, d):
    i = sessions.searchsorted(d, side="right")
    return sessions[i] if i < len(sessions) else None


def periods(decision_dates, sessions, end):
    """[(signal date d_t, execution e_t, period end e_{t+1} or the last session)] for every decision whose execution exists."""
    exe = [(d, next_session(sessions, d)) for d in decision_dates]
    exe = [(d, e) for d, e in exe if e is not None and e <= end]
    out = []
    for i, (d, e) in enumerate(exe):
        x = exe[i + 1][1] if i + 1 < len(exe) else end
        if x > e:
            out.append((d, e, x))
    return out


# --------------------------------------------------------------------------- #
# Period returns
# --------------------------------------------------------------------------- #
class PeriodPrices:
    """Buy-and-hold period returns on the forward-filled close panel, the same carry rule the frozen engine values with.

    A name whose last finite close precedes the period end and which the engine treats as terminated is valued at ZERO from the
    session after its last close (the engine's primary terminal rule); the hit is recorded, never hidden."""

    def __init__(self, closes, sessions, rf_daily, terminal=None):
        self.sessions = sessions
        self.carry = closes.reindex(sessions).ffill()
        self.rf = rf_daily.reindex(sessions).fillna(0.0)
        self.terminal = terminal or {}
        self.hits = []

    def ret(self, asset, e, x):
        if asset == CASH:
            seg = self.rf.loc[e:x].iloc[1:]
            return float(np.prod(1 + seg.to_numpy()) - 1)
        p0, p1 = self.carry.at[e, asset], self.carry.at[x, asset]
        term = self.terminal.get(asset)
        if term is not None and term < x:
            self.hits.append((str(e.date()), asset, str(term.date())))
            return -1.0
        if not (np.isfinite(p0) and np.isfinite(p1)) or p0 <= 0:
            return float("nan")
        return float(p1 / p0 - 1)

    def cash(self, e, x):
        return self.ret(CASH, e, x)


def industry_basket(cross_section, industry, mcap_col="_mcap", eligible_col="_q", equal=False):
    """{ticker: weight} of the PIT industry basket: quality-eligible members of `industry` on the signal date, cap-weighted (or equal)."""
    g = cross_section[(cross_section["industry"] == industry) & cross_section[eligible_col].astype(bool)]
    if g.empty:
        return {}
    if equal:
        return {t: 1.0 / len(g) for t in g["ticker"]}
    m = g[mcap_col].astype(float)
    if not np.isfinite(m).all() or m.sum() <= 0:
        return {t: 1.0 / len(g) for t in g["ticker"]}
    return {t: float(v / m.sum()) for t, v in zip(g["ticker"], m)}


def industry_beta(weights, betas):
    """Weight-averaged beta over the members whose beta is finite (weights renormalised); 1.0 if none is measured."""
    pairs = [(w, float(betas.get(t, np.nan))) for t, w in weights.items()]
    pairs = [(w, b) for w, b in pairs if np.isfinite(b)]
    s = sum(w for w, _ in pairs)
    return sum(w * b for w, b in pairs) / s if s > 0 else 1.0


def attribute_leg(w, r_i, r_ind, r_m, r_f, b_i, b_ind):
    """Three-term split of one leg's weighted excess over the ETF. Returns dict with the terms and the identity residual."""
    mx = r_m - r_f
    beta = w * (b_i - 1.0) * mx
    ind = w * (r_ind - r_f - b_ind * mx)
    sel = w * (r_i - r_ind - (b_i - b_ind) * mx)
    total = w * (r_i - r_m)
    return {"MARKET_BETA": beta, "INDUSTRY_ALPHA": ind, "SELECTION_ALPHA": sel, "excess": total, "residual": total - beta - ind - sel}


def attribute_book(book, cross_section, pp, e, x, beta_col="F03_beta252", equal_industry=False, cache=None):
    """Attribute one period of one book. `book` = {asset: weight} (weights sum to 1; ETF and CASH allowed).

    Returns a list of leg rows. A stock with no finite period return is reported with NaN terms and flagged; it never silently
    becomes a zero return."""
    cache = {} if cache is None else cache
    r_m = pp.ret(ETF, e, x)
    r_f = pp.cash(e, x)
    cs = cross_section.set_index("ticker", drop=False)
    rows = []
    for a, w in sorted(book.items()):
        if w == 0:
            continue
        if a == ETF:
            rows.append({"asset": a, "industry": "ETF", "weight": w, "R": r_m, "R_ind": r_m, "beta": 1.0, "beta_ind": 1.0,
                         **attribute_leg(w, r_m, r_m, r_m, r_f, 1.0, 1.0)})
            continue
        if a == CASH:
            rows.append({"asset": a, "industry": "CASH", "weight": w, "R": r_f, "R_ind": r_f, "beta": 0.0, "beta_ind": 0.0,
                         **attribute_leg(w, r_f, r_f, r_m, r_f, 0.0, 0.0)})
            continue
        ind = cs.at[a, "industry"] if a in cs.index else None
        key = (e, ind, equal_industry)
        if key not in cache:
            bw = industry_basket(cross_section, ind, equal=equal_industry) if ind is not None else {}
            if not bw:
                bw = {a: 1.0}
            rets = {t: pp.ret(t, e, x) for t in bw}
            ok = {t: v for t, v in bw.items() if np.isfinite(rets[t])}
            s = sum(ok.values())
            ok = {t: v / s for t, v in ok.items()} if s > 0 else {}
            fb = industry_beta(ok, cs[beta_col])
            cache[key] = {"R_ind": sum(ok[t] * rets[t] for t in ok) if ok else float("nan"), "beta_ind": fb, "members": len(bw)}
        info = cache[key]
        r_i = pp.ret(a, e, x)
        b_i = float(cs.at[a, beta_col]) if a in cs.index and np.isfinite(cs.at[a, beta_col]) else info["beta_ind"]
        r_ind = info["R_ind"] if np.isfinite(info["R_ind"]) else r_i
        rows.append({"asset": a, "industry": ind, "weight": w, "R": r_i, "R_ind": r_ind, "beta": b_i, "beta_ind": info["beta_ind"],
                     "industryMembers": info["members"], **attribute_leg(w, r_i, r_ind, r_m, r_f, b_i, info["beta_ind"])})
    for r in rows:
        if np.isfinite(r["residual"]) and abs(r["residual"]) > IDENTITY_TOL:
            raise AssertionError(f"ATTRIBUTION_IDENTITY_BROKEN {r['asset']} {e.date()} {r['residual']}")
        r.update(R_m=r_m, R_f=r_f)
    return rows


# --------------------------------------------------------------------------- #
# Aggregation
# --------------------------------------------------------------------------- #
def cagr(period_returns, years):
    g = float(np.prod(1 + np.asarray(period_returns, float)))
    return g ** (1 / years) - 1 if g > 0 else -1.0


def summarise(legs, years, label):
    """Annualised arithmetic contribution of each term, plus the geometric gap and the compounding term."""
    legs = legs.assign(_wr=legs["weight"] * legs["R"], _wb=legs["weight"] * legs["beta"],
                       _etf=legs["weight"].where(legs["asset"] == ETF, 0.0), _cash=legs["weight"].where(legs["asset"] == CASH, 0.0))
    per = legs.groupby("period")
    rp = per["_wr"].sum()
    rm = per["R_m"].first()
    out = {"label": label, "periods": int(len(rp)), "years": years,
           "grossCagr": cagr(rp, years), "etfCagr": cagr(rm, years)}
    out["geometricGap"] = out["grossCagr"] - out["etfCagr"]
    for t in TERMS:
        out[t] = float(legs[t].sum() / years)
    out["arithmeticExcess"] = float(legs["excess"].sum() / years)
    out["compounding"] = out["geometricGap"] - out["arithmeticExcess"]
    out["betaAdjustedAlpha"] = out["INDUSTRY_ALPHA"] + out["SELECTION_ALPHA"]
    out["meanEtfWeight"], out["meanCashWeight"], out["meanBookBeta"] = (float(per["_etf"].sum().mean()), float(per["_cash"].sum().mean()),
                                                                        float(per["_wb"].sum().mean()))
    return out


# --------------------------------------------------------------------------- #
# Inference
# --------------------------------------------------------------------------- #
def block_bootstrap_mean(x, block, reps=4000, seed=17, scale=1.0):
    """Circular block bootstrap of the mean of a (possibly overlapping) series. Returns mean, 95% CI and two-sided p (scaled)."""
    x = np.asarray(pd.Series(x).dropna(), float)
    n = len(x)
    if n < 3:
        return {"n": n, "mean": None, "ci95": [None, None], "p": None}
    rng = np.random.default_rng(seed)
    k = int(math.ceil(n / block))
    st = np.empty(reps)
    for i in range(reps):
        idx = (rng.integers(0, n, k)[:, None] + np.arange(block)[None, :]).ravel()[:n] % n
        st[i] = x[idx].mean()
    p = float(min(1.0, 2 * min((st <= 0).mean(), (st >= 0).mean())))
    return {"n": n, "block": block, "mean": float(x.mean() * scale), "ci95": [float(np.percentile(st, 2.5) * scale), float(np.percentile(st, 97.5) * scale)],
            "p": p}


def hac_mean(x, lags):
    """Newey-West t-statistic of a mean (Bartlett kernel)."""
    x = np.asarray(pd.Series(x).dropna(), float)
    n = len(x)
    if n < 5:
        return {"n": n, "mean": None, "t": None}
    e = x - x.mean()
    s = e @ e / n
    for L in range(1, min(lags, n - 1) + 1):
        s += 2 * (1 - L / (lags + 1)) * (e[L:] @ e[:-L]) / n
    se = math.sqrt(max(s, 0) / n)
    return {"n": n, "lags": lags, "mean": float(x.mean()), "se": se, "t": float(x.mean() / se) if se > 0 else None}


def holm(pvals):
    p = np.asarray(pvals, float)
    order = np.argsort(p)
    m = len(p)
    out = np.empty(m)
    running = 0.0
    for i, j in enumerate(order):
        running = max(running, min(1.0, p[j] * (m - i)))
        out[j] = running
    return out


def spearman(a, b):
    a, b = pd.Series(a), pd.Series(b)
    m = a.notna() & b.notna()
    if m.sum() < 3:
        return float("nan")
    return float(a[m].rank().corr(b[m].rank()))


# --------------------------------------------------------------------------- #
# Choice value and nulls (sleeve layer)
# --------------------------------------------------------------------------- #
def choice_value(sleeve_period_returns, chosen):
    """v_t = R_chosen,t - mean_k R_k,t. `sleeve_period_returns`: DataFrame periods x sleeves; `chosen`: Series period -> sleeve."""
    m = sleeve_period_returns.mean(axis=1)
    picked = pd.Series([sleeve_period_returns.at[p, k] for p, k in chosen.items()], index=chosen.index)
    return picked - m


def permutation_null(sleeve_period_returns, chosen, years, draws=10000, seed=23):
    """Two nulls for the chained gross CAGR of a sleeve-switching policy:
    UNIFORM — every period picks a sleeve uniformly at random (no information);
    SHUFFLE — the realised choice sequence permuted across periods (same sleeve frequencies, timing destroyed)."""
    R = sleeve_period_returns.to_numpy()
    cols = list(sleeve_period_returns.columns)
    idx = np.array([cols.index(k) for k in chosen])
    n, k = R.shape
    actual = cagr(R[np.arange(n), idx], years)
    rng = np.random.default_rng(seed)
    uni = np.array([cagr(R[np.arange(n), rng.integers(0, k, n)], years) for _ in range(draws)])
    shf = np.array([cagr(R[np.arange(n), rng.permutation(idx)], years) for _ in range(draws)])
    return {"actualGrossCagr": actual,
            "uniform": {"median": float(np.median(uni)), "p95": float(np.percentile(uni, 95)), "pValue": float((1 + (uni >= actual).sum()) / (draws + 1))},
            "shuffle": {"median": float(np.median(shf)), "p95": float(np.percentile(shf, 95)), "pValue": float((1 + (shf >= actual).sum()) / (draws + 1))},
            "draws": draws}


# --------------------------------------------------------------------------- #
# Matched controls (S2 ablation D)
# --------------------------------------------------------------------------- #
def matched_controls(cross_section, picks, match_cols, eligible_col="_q"):
    """For every pick: the unpicked, eligible, same-industry name nearest in within-date percentile space of `match_cols`.
    Each control is used at most once per date (greedy in pick order). A pick with no candidate gets None and is reported."""
    g = cross_section[cross_section[eligible_col].astype(bool)].copy()
    pct = g[match_cols].rank(pct=True)
    used = set(picks)
    out = {}
    for t in picks:
        row = g[g["ticker"] == t]
        if row.empty:
            out[t] = None
            continue
        ind = row["industry"].iloc[0]
        cand = g[(g["industry"] == ind) & ~g["ticker"].isin(used)]
        if cand.empty:
            out[t] = None
            continue
        a = pct.loc[row.index[0]].to_numpy(float)
        b = pct.loc[cand.index].to_numpy(float)
        d = np.nansum((b - a) ** 2, axis=1) + np.isnan(b - a).sum(axis=1) * 0.25
        j = cand.index[int(np.argmin(d))]
        out[t] = cand.at[j, "ticker"]
        used.add(out[t])
    return out
