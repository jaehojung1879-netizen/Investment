"""adaptive-cocktail-v1 — state panel, sleeve books, self-financing engine, fixed and learned cocktails, metrics.

Everything reads the frozen config.json. Evidence class EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY.
No function here reads a value dated after the decision date it serves, except `forward_relative` (labels), whose rows are only
handed to a model once their exit session is strictly before the decision date (`matured`).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CONFIG = json.loads((HERE / "config.json").read_text())
ETF = "069500.KS"
CASH = "CASH"
LAGS = CONFIG["timing"]["lagCalendarDays"]
WITHHELD = tuple(CONFIG["inputs"]["withheldSecurities"])
CHOICE = CONFIG["sleeves"]["choiceSet"]
RISKY = [s for s in CHOICE if s != "S0_ETF"]
SELL_TAX = [{"effectiveDate": "1900-01-01", "sellTaxBps": 30.0}, {"effectiveDate": "2019-06-03", "sellTaxBps": 25.0},
            {"effectiveDate": "2021-01-01", "sellTaxBps": 23.0}, {"effectiveDate": "2023-01-01", "sellTaxBps": 20.0},
            {"effectiveDate": "2024-01-01", "sellTaxBps": 18.0}, {"effectiveDate": "2025-01-01", "sellTaxBps": 15.0},
            {"effectiveDate": "2026-01-01", "sellTaxBps": 20.0}]
KR_STATES = ["MKT_TREND_63", "MKT_TREND_252", "MKT_VOL_63", "MKT_DD_252", "BREADTH_200", "IND_DISPERSION", "CONCENTRATION_TOP2", "LEADERSHIP_PERSIST"]
US_STATES = ["UST10_LEVEL", "UST10_CHG_63", "CURVE_10Y2Y", "CURVE_CHG_63", "BROAD_DOLLAR_CHG_63", "USDKRW_CHG_63", "USDKRW_VOL_63",
             "VIX_LEVEL", "VIX_CHG_63", "CORR_KR_USDKRW_126", "CORR_KR_UST10_126"]
ALL_STATES = KR_STATES + US_STATES


# --------------------------------------------------------------------------- #
# Point-in-time visibility
# --------------------------------------------------------------------------- #
def visible(series, kr_sessions, lag_days):
    """Value visible on each KR session D: the latest observation with observation date <= D - lag_days (calendar days)."""
    s = series.dropna().sort_index()
    s = s[~s.index.duplicated(keep="last")]
    q = pd.DataFrame({"t": kr_sessions - pd.Timedelta(days=lag_days)})
    obs = pd.DataFrame({"t": s.index, "v": s.to_numpy()})
    out = pd.merge_asof(q.sort_values("t"), obs, on="t", direction="backward")
    return pd.Series(out["v"].to_numpy(), index=kr_sessions)


def lagged_rolling_corr(a, b, window, lag_days, kr_sessions):
    """Rolling correlation of two daily series on their COMMON observation dates, then made visible with the lag.
    The value computed from observations ending on date t becomes visible on KR date D only if t <= D - lag_days."""
    j = pd.concat([a.rename("a"), b.rename("b")], axis=1, join="inner").dropna()
    c = j["a"].rolling(window, min_periods=window).corr(j["b"])
    return visible(c, kr_sessions, lag_days)


def state_panel(sessions, bench, macro, vix, fx, matrix_dates_frame):
    """Daily KR-session panel of every frozen state variable (values visible at that session's KR close)."""
    b = bench.reindex(sessions).ffill()
    r = b.pct_change()
    out = pd.DataFrame(index=sessions)
    out["MKT_TREND_63"] = b / b.shift(63) - 1
    out["MKT_TREND_252"] = b / b.shift(252) - 1
    out["MKT_VOL_63"] = r.rolling(63).std() * math.sqrt(252)
    out["MKT_DD_252"] = b / b.rolling(252).max() - 1
    md = matrix_dates_frame.set_index("date")
    for col, src in (("BREADTH_200", "H09_marketBreadth"), ("IND_DISPERSION", "H05_crossIndustryDispersion"),
                     ("CONCENTRATION_TOP2", "H10_marketConcentrationTop2"), ("LEADERSHIP_PERSIST", "H07_leadershipPersistence")):
        out[col] = md[src].reindex(sessions).ffill(limit=6)          # weekly same-date value carried within its week only
    lag_f = LAGS["FRED_DAILY_MARKET"]
    lag_h10 = LAGS["FRED_H10_WEEKLY"]
    t10 = visible(macro["Treasury_10Y"], sessions, lag_f)
    t2 = visible(macro["Treasury_2Y"], sessions, lag_f)
    out["UST10_LEVEL"] = t10
    out["UST10_CHG_63"] = t10 - t10.shift(63)
    curve = t10 - t2
    out["CURVE_10Y2Y"] = curve
    out["CURVE_CHG_63"] = curve - curve.shift(63)
    bd = visible(np.log(macro["Broad_Dollar"]), sessions, lag_h10)
    out["BROAD_DOLLAR_CHG_63"] = bd - bd.shift(63)
    fxs = fx.set_index(pd.to_datetime(fx["date"]))["value"].astype(float)
    fxl = np.log(fxs)
    fv = visible(fxl, sessions, lag_h10)
    out["USDKRW_CHG_63"] = fv - fv.shift(63)
    out["USDKRW_VOL_63"] = visible(fxl.diff().rolling(63, min_periods=63).std() * math.sqrt(252), sessions, lag_h10)
    vx = vix.set_index(pd.to_datetime(vix["date"]))["value"].astype(float)
    vv = visible(vx, sessions, lag_f)
    out["VIX_LEVEL"] = vv
    out["VIX_CHG_63"] = vv - vv.shift(63)
    kr_ret = r.dropna()
    out["CORR_KR_USDKRW_126"] = lagged_rolling_corr(kr_ret, fxl.diff(), 126, lag_h10, sessions)
    out["CORR_KR_UST10_126"] = lagged_rolling_corr(kr_ret, macro["Treasury_10Y"].diff(), 126, lag_f, sessions)
    out["MA200_ABOVE"] = (b > b.rolling(200).mean()).astype(float).where(b.rolling(200).count() == 200)
    out["VOL63_PCTL_EXPANDING"] = out["MKT_VOL_63"].expanding(252).apply(lambda v: (v[:-1] < v[-1]).mean(), raw=True)
    return out


# --------------------------------------------------------------------------- #
# Sleeve books
# --------------------------------------------------------------------------- #
def quality_mask(df):
    return (df["tradableAtSignal"].astype(bool) & (df["isPreferredShare"] != True) &  # noqa: E712
            (df["E04_tradabilityGuard20"] >= 20) & (df["E07_suspensionStaleRisk"].fillna(1) <= 0) &
            (df["E03_capacityMedianTradedValue60"] >= 5e9))


def sleeve_score(name, g):
    rk = lambda c: g[c].rank(pct=True)  # noqa: E731
    if name == "S1_INDUSTRY_MOMENTUM":
        return rk("H01_industryRelMom126") + 0.01 * rk("A09_industryRelativeMomentum126").fillna(0)
    if name == "S2_VALUE_CONFIRMED":
        return g["B08_valueBusinessConfirmation"].where(g["b08Confirmed"] == 1)
    if name == "S3_FOUR_FACTOR":
        return pd.concat([rk("A07_momentum12_1"), rk("B01_bookToMarket"), rk("C02_returnOnEquity"), 1 - rk("F02_downsideVol126")],
                         axis=1).mean(axis=1, skipna=True)
    raise KeyError(name)


def sleeve_book(name, g, exclude_industries=(), score=None, withheld=WITHHELD):
    """Target weights for one sleeve on one signal date. Returns (weights incl. ETF residual, picked list, would-have-picked withheld names)."""
    if name == "S0_ETF":
        return {ETF: 1.0}, [], []
    s = score if score is not None else sleeve_score(name, g)
    elig = g["_q"] & s.notna() & ~g["industry"].isin(exclude_industries)
    cand = g.assign(_s=s)[elig].sort_values(["_s", "ticker"], ascending=[False, True])
    would = [t for t in cand.head(5)["ticker"] if t in withheld]
    picks = list(cand[~cand["ticker"].isin(withheld)].head(5)["ticker"])
    w = {t: 0.2 for t in picks}
    if len(picks) < 5:
        w[ETF] = 0.2 * (5 - len(picks))
    return w, picks, would


def combine(books, weights):
    """Cocktail book = sum_k w_k * book_k; overlapping names net."""
    out = {}
    for k, wk in weights.items():
        if wk <= 0:
            continue
        for a, x in books[k].items():
            out[a] = out.get(a, 0.0) + wk * x
    return out


# --------------------------------------------------------------------------- #
# Self-financing engine
# --------------------------------------------------------------------------- #
def sell_tax_bps(date):
    eff = [r for r in SELL_TAX if r["effectiveDate"] <= str(pd.Timestamp(date).date())]
    return max(eff, key=lambda r: r["effectiveDate"])["sellTaxBps"]


def cost_rate(asset, side, date, mult=1.0):
    if asset == CASH:
        return 0.0
    if asset == ETF:
        return (1.5 + 2.0 / 2) / 1e4 * mult
    return (1.5 + 8.0 / 2 + (sell_tax_bps(date) if side == "sell" else 0.0)) / 1e4 * mult


class Prices:
    def __init__(self, closes, volumes, sessions, rf_daily):
        self.sessions = sessions
        self.pos = {d: i for i, d in enumerate(sessions)}
        self.col = {t: j for j, t in enumerate(closes.columns)}
        c = closes.reindex(sessions)
        self.carry = c.ffill().to_numpy()
        self.tradable = (c.notna() & (volumes.reindex(sessions).fillna(0) > 0)).to_numpy()
        self.etf = closes[ETF].reindex(sessions).ffill().to_numpy()
        self.rf = rf_daily.reindex(sessions).fillna(0).to_numpy()
        end = closes[ETF].last_valid_index()
        last = c.apply(lambda s: s.last_valid_index())
        self.terminal = {t: self.pos[d] for t, d in last.items() if d is not None and t != ETF and self.pos[d] < self.pos[end] - 5}

    def price(self, asset, i):
        return self.etf[i] if asset == ETF else self.carry[i, self.col[asset]]


def simulate(px, schedule, start, end, terminal_mode="ZERO", cost_mult=1.0, record=False):
    """schedule: {execution session (Timestamp): {asset: weight}} (weights sum to 1; ETF and CASH are assets).
    Units change only by a trade. A name that cannot trade keeps its units; the tradable targets share what is left.
    Cost is charged on traded value; NAV_post solves NAV_post = NAV_pre - cost(NAV_post)."""
    idx = [i for i, d in enumerate(px.sessions) if start <= d <= end]
    sched = {px.pos[d]: w for d, w in schedule.items() if d in px.pos}
    units = {ETF: 1.0 / px.etf[idx[0]]}
    cash = 0.0
    navs = np.empty(len(idx))
    costs = turnover = 0.0
    holdings, hits = [], []
    contrib = {} if record else None
    prev_val = {ETF: 1.0}
    for k, i in enumerate(idx):
        d = px.sessions[i]
        if k > 0:
            cash *= 1 + px.rf[i]
        for t in list(units):
            term = px.terminal.get(t)
            if term is not None and i > term:
                v = units.pop(t) * px.price(t, term)
                hits.append((str(d.date()), t, v))
                if terminal_mode == "LAST":
                    units[ETF] = units.get(ETF, 0.0) + v / px.etf[i]
        val = {t: u * px.price(t, i) for t, u in units.items()}
        nav = sum(val.values()) + cash
        if record and k > 0:
            nav_prev = sum(prev_val.values())
            for t, v in val.items():
                contrib.setdefault(t, np.zeros(len(idx)))[k] += (v - prev_val.get(t, v)) / nav_prev
        if i in sched:
            target = dict(sched[i])
            locked = {t: v for t, v in val.items() if t not in (ETF,) and not px.tradable[i, px.col[t]]}
            L = sum(locked.values())
            free = {a: w for a, w in target.items() if a not in locked and (a in (ETF, CASH) or px.tradable[i, px.col[a]])}
            tot = sum(free.values())
            free = {a: w / tot for a, w in free.items()} if tot > 1e-12 else {ETF: 1.0}
            cur = {a: v for a, v in val.items() if a not in locked}
            cur[CASH] = cash
            post = nav
            for _ in range(8):
                room = post - L                                   # what the tradable targets can hold after the locked names
                c = sum(abs(free.get(a, 0) * room - cur.get(a, 0)) * cost_rate(a, "buy" if free.get(a, 0) * room > cur.get(a, 0) else "sell", d, cost_mult)
                        for a in set(free) | set(cur))
                post = nav - c
            room = post - L
            traded = sum(abs(free.get(a, 0) * room - cur.get(a, 0)) for a in set(free) | set(cur) if a != CASH)
            turnover += traded / nav / 2
            costs += c / nav
            units = {t: locked[t] / px.price(t, i) for t in locked}
            for a, w in free.items():
                if a == CASH or w <= 0:
                    continue
                units[a] = units.get(a, 0.0) + w * room / px.price(a, i)
            cash = free.get(CASH, 0.0) * room
            nav = post
            val = {t: u * px.price(t, i) for t, u in units.items()}
            if record:
                holdings.append({"date": str(d.date()), "weights": {a: round(v / nav, 6) for a, v in val.items()} | ({CASH: round(cash / nav, 6)} if cash else {})})
        prev_val = dict(val)
        if cash and record:
            prev_val[CASH] = cash
        navs[k] = nav
    out = {"nav": pd.Series(navs, index=px.sessions[idx]), "costs": costs, "turnover": turnover, "terminalHits": hits}
    if record:
        out.update(contrib=contrib, holdings=holdings)
    return out


# --------------------------------------------------------------------------- #
# Learned allocation
# --------------------------------------------------------------------------- #
def ridge_fit_predict(X, y, x_new, alpha=10.0):
    """Ridge on standardised X with an unpenalised intercept; returns (prediction, conditional-mean standard error)."""
    n, p = X.shape
    xm, ym = X.mean(axis=0), y.mean()
    Xc = X - xm
    A = Xc.T @ Xc + alpha * np.eye(p)
    Ai = np.linalg.inv(A)
    beta = Ai @ Xc.T @ (y - ym)
    resid = y - ym - Xc @ beta
    dof = max(n - p - 1, 5)
    s2 = float(resid @ resid) / dof
    xn = x_new - xm
    var = s2 * (1.0 / n + float(xn @ Ai @ (Xc.T @ Xc) @ Ai @ xn))
    return float(ym + xn @ beta), math.sqrt(max(var, 0.0))


def learned_weights(mu, se, hurdle, full_edge=0.05, overlap=math.sqrt(63 / 20)):
    edges = {}
    for k in mu:
        s = se[k] * overlap
        kappa = mu[k] ** 2 / (mu[k] ** 2 + s ** 2) if (mu[k] ** 2 + s ** 2) > 0 else 0.0
        e = kappa * mu[k] - hurdle
        if e > 0:
            edges[k] = e
    total = sum(edges.values())
    if total <= 0:
        return {"S0_ETF": 1.0}, edges
    risky = min(1.0, total / full_edge)
    w = {k: risky * e / total for k, e in edges.items()}
    w["S0_ETF"] = 1.0 - sum(w.values())
    return w, edges


def round_trip_hurdle(date):
    return (2 * 5.5 + sell_tax_bps(date) + 2 * 2.5) / 1e4


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #
def metrics(nav, bench_nav, rf):
    r = nav.pct_change().dropna()
    b = bench_nav.reindex(nav.index).pct_change().dropna()
    yrs = (len(nav) - 1) / 252
    cagr = (nav.iloc[-1] / nav.iloc[0]) ** (1 / yrs) - 1
    bn = bench_nav.reindex(nav.index)
    bc = (bn.iloc[-1] / bn.iloc[0]) ** (1 / yrs) - 1
    act = r - b
    te = act.std() * math.sqrt(252)
    ex = r - rf.reindex(r.index).fillna(0)
    q = r.quantile(0.05)
    roll6 = (nav / nav.shift(126) - bn / bn.shift(126)).dropna()
    roll12 = (nav / nav.shift(252) - bn / bn.shift(252)).dropna()
    return {"cagr": cagr, "etfCagr": bc, "excessCagr": cagr - bc, "vol": r.std() * math.sqrt(252), "sharpe": ex.mean() / r.std() * math.sqrt(252),
            "mdd": float((nav / nav.cummax() - 1).min()), "cvar5Daily": float(r[r <= q].mean()), "trackingError": te,
            "informationRatio": act.mean() * 252 / te if te > 0 else None,
            "rolling126ExcessPositiveShare": float((roll6 > 0).mean()), "rolling126ExcessWorst": float(roll6.min()),
            "rolling252ExcessPositiveShare": float((roll12 > 0).mean()), "rolling252ExcessWorst": float(roll12.min()), "years": yrs}


def yearly(nav, bench_nav):
    out = {}
    bn = bench_nav.reindex(nav.index)
    for y, g in nav.groupby(nav.index.year):
        i0 = nav.index.get_loc(g.index[0])
        a0 = nav.iloc[i0 - 1] if i0 else nav.iloc[0]
        b0 = bn.iloc[i0 - 1] if i0 else bn.iloc[0]
        out[int(y)] = {"ret": float(g.iloc[-1] / a0 - 1), "etf": float(bn.loc[g.index[-1]] / b0 - 1)}
        out[int(y)]["excess"] = out[int(y)]["ret"] - out[int(y)]["etf"]
    return out


def block_bootstrap(diff, block=126, reps=2000, seed=11):
    x = diff.dropna().to_numpy()
    n = len(x)
    rng = np.random.default_rng(seed)
    k = int(math.ceil(n / block))
    st = np.empty(reps)
    for i in range(reps):
        idx = (rng.integers(0, n, k)[:, None] + np.arange(block)[None, :]).ravel()[:n] % n
        st[i] = x[idx].mean() * 252
    p = float(min(1.0, 2 * min((st <= 0).mean(), (st >= 0).mean())))
    return {"annualisedMeanDiff": float(x.mean() * 252), "ci95": [float(np.percentile(st, 2.5)), float(np.percentile(st, 97.5))], "twoSidedP": p}


def newey_west_slope(x, y, lags):
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    n = len(x)
    if n < 20 or np.std(x) == 0:
        return None
    X = np.column_stack([np.ones(n), x])
    b = np.linalg.lstsq(X, y, rcond=None)[0]
    e = y - X @ b
    XtXi = np.linalg.inv(X.T @ X)
    S = (X * e[:, None]).T @ (X * e[:, None])
    for L in range(1, lags + 1):
        w = 1 - L / (lags + 1)
        G = (X[L:] * e[L:, None]).T @ (X[:-L] * e[:-L, None])
        S += w * (G + G.T)
    V = XtXi @ S @ XtXi
    se = math.sqrt(V[1, 1])
    from scipy.stats import t as tdist
    tt = b[1] / se
    return {"slope": float(b[1]), "t": float(tt), "p": float(2 * tdist.sf(abs(tt), n - 2)), "n": int(n)}


def by_adjust(p):
    """Benjamini-Yekutieli adjusted p-values."""
    p = np.asarray(p, float)
    m = len(p)
    c = np.sum(1.0 / np.arange(1, m + 1))
    order = np.argsort(p)
    adj = np.empty(m)
    prev = 1.0
    for rank, i in reversed(list(enumerate(order, start=1))):
        prev = min(prev, p[i] * m * c / rank)
        adj[i] = prev
    return np.minimum(adj, 1.0)
