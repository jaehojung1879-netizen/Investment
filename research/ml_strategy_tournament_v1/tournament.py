"""ml-strategy-tournament-v1 — dataset, model grid, walk-forward fitting, portfolio NAV engine and metrics.

Everything here reads the frozen `config.json`. The feature matrix comes from the existing Phase B builder (see build_features.py); this module
adds only (a) date-level market state from the benchmark close and the dated BOK policy rate, (b) forward labels, (c) models and (d) the
portfolio ledger. Evidence class: EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
CONFIG = json.loads((HERE / "config.json").read_text())
BENCH = CONFIG["benchmark"]

MARKET_FROM_MATRIX = ["H05_crossIndustryDispersion", "H07_leadershipPersistence", "H09_marketBreadth", "H10_marketConcentrationTop2",
                      "I01_kospiTrendVolState", "J05_shortSellingRegime"]
MARKET_DERIVED = ["MKT_trend126", "MKT_trend252", "MKT_vol63", "MKT_drawdown252", "MKT_ma200", "MKT_bokRate", "MKT_bokRateChange252",
                  "MKT_xsDispersion63", "MKT_xsMedianMom252"]
INDUSTRY = ["A09_industryRelativeMomentum126", "B05_industryRelativeValue", "H01_industryRelMom126", "H02_industryRelMom63",
            "H03_industryBreadthAboveMA126", "H04_withinIndustryDispersion126", "H06_industryConcentrationTop1", "H08_equalVsCapWeightIndustry",
            "H11_industryEarningsContext", "H12_industryValuationContext"]
DROP = {"C08_netIncomeMinusOcf"}        # documented alias (sign flip) of C07: one information item, kept once
FAMILIES = {
    "MARKET": lambda c: c in MARKET_FROM_MATRIX or c.startswith("MKT_"),
    "INDUSTRY": lambda c: c in INDUSTRY,
    "ACCOUNTING": lambda c: c[:1] in ("B", "C") or c == "J01_periodicFilingEvent",
    "PRICE_MOMENTUM": lambda c: c[:1] == "A" and c not in INDUSTRY,
    "LIQUIDITY_RISK": lambda c: c[:1] in ("D", "E", "F"),
}


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# --------------------------------------------------------------------------- #
# Dataset
# --------------------------------------------------------------------------- #
def closes_on(prices, ticker, sessions):
    frame = prices.get(ticker)
    if frame is None or not len(frame):
        return pd.Series(np.nan, index=sessions)
    close = frame["Close"].astype(float)
    close.index = pd.DatetimeIndex(close.index).tz_localize(None).normalize()
    return close[~close.index.duplicated(keep="last")].reindex(sessions)


def volumes_on(prices, ticker, sessions):
    frame = prices.get(ticker)
    if frame is None or not len(frame) or "Volume" not in frame:
        return pd.Series(np.nan, index=sessions)
    v = frame["Volume"].astype(float)
    v.index = pd.DatetimeIndex(v.index).tz_localize(None).normalize()
    return v[~v.index.duplicated(keep="last")].reindex(sessions)


def bok_rate_series(sessions, events):
    """Policy rate in effect at each session: the latest announced event dated on or before the session (event date = announcement)."""
    ev = pd.Series({pd.Timestamp(e["date"]): float(e["annualRatePct"]) for e in events}).sort_index()
    return ev.reindex(ev.index.union(sessions)).ffill().reindex(sessions)


def market_state(bench_close, sessions, bok_events):
    c = bench_close.ffill()
    r = c.pct_change()
    out = pd.DataFrame(index=sessions)
    out["MKT_trend126"] = c / c.shift(126) - 1
    out["MKT_trend252"] = c / c.shift(252) - 1
    out["MKT_vol63"] = r.rolling(63).std() * math.sqrt(252)
    out["MKT_drawdown252"] = c / c.rolling(252).max() - 1
    out["MKT_ma200"] = c / c.rolling(200).mean() - 1
    rate = bok_rate_series(sessions, bok_events)
    out["MKT_bokRate"] = rate
    out["MKT_bokRateChange252"] = rate - rate.shift(252)
    return out


def forward_excess(close, bench, sessions, horizon):
    """Excess of stock over benchmark from the close of the first session after the signal date to `horizon` sessions later.
    Returns (excess, exit_session) aligned on the signal sessions."""
    pos = np.arange(len(sessions))
    entry = pos + 1
    exit_ = entry + horizon
    valid = exit_ < len(sessions)
    ex_dates = pd.Series(pd.NaT, index=sessions)
    ex_dates[valid] = sessions[exit_[valid]]
    c = close.to_numpy()
    b = bench.to_numpy()
    out = np.full(len(sessions), np.nan)
    e, x = entry[valid], exit_[valid]
    with np.errstate(invalid="ignore", divide="ignore"):
        out[valid] = (c[x] / c[e]) - (b[x] / b[e])
    return pd.Series(out, index=sessions), ex_dates


def assemble(matrix, prices, sessions, bok_events, horizons=(126, 252)):
    """Long table: one row per (date, ticker) with transformed-ready raw features, market state, labels and exit dates."""
    rows = matrix.rows.reset_index(drop=True).copy()
    rows["date"] = pd.to_datetime(rows["date"])
    values = matrix.values.reset_index(drop=True)
    values = values[[c for c in values.columns if c not in DROP]]
    df = pd.concat([rows[["date", "ticker", "industry", "isPreferredShare", "tradableAtSignal"]], values], axis=1)
    bench = closes_on(prices, BENCH, sessions)
    mkt = market_state(bench, sessions, bok_events)
    df = df.merge(mkt, left_on="date", right_index=True, how="left")
    g = df.groupby("date")
    df["MKT_xsDispersion63"] = g["A04_return63d"].transform("std")
    df["MKT_xsMedianMom252"] = g["A06_return252d"].transform("median")
    for h in horizons:
        df[f"y{h}"] = np.nan
        df[f"exit{h}"] = pd.NaT
    for t, idx in df.groupby("ticker").groups.items():
        close = closes_on(prices, t, sessions)
        for h in horizons:
            ex, exd = forward_excess(close, bench, sessions, h)
            d = df.loc[idx, "date"]
            df.loc[idx, f"y{h}"] = ex.reindex(d).to_numpy()
            df.loc[idx, f"exit{h}"] = exd.reindex(d).to_numpy()
    for h in horizons:
        # Exit date is a property of the calendar; it exists even when the label is withheld.
        df[f"exit{h}"] = pd.to_datetime(df[f"exit{h}"])
    return df.sort_values(["date", "ticker"]).reset_index(drop=True), bench


def feature_layers(df):
    feats = [c for c in df.columns if c[:1] in "ABCDEFHIJ" and c[1:3].isdigit() or c.startswith("MKT_")]
    coverage = df[feats].notna().mean()
    feats = [c for c in feats if coverage[c] >= CONFIG["features"]["minimumCoverageToEnter"]]
    market = [c for c in feats if c in MARKET_FROM_MATRIX or c.startswith("MKT_")]
    industry = [c for c in feats if c in INDUSTRY]
    company = [c for c in feats if c not in market and c not in industry]
    return {"company": company, "industry": industry, "market": market}, coverage


def feature_set(layers, fs):
    if fs == "C":
        return list(layers["company"])
    if fs == "CI":
        return layers["company"] + layers["industry"]
    return layers["company"] + layers["industry"] + layers["market"]


def rank_transform(df, cols):
    """Within-date percentile ranks (same-date information only); NaN stays NaN."""
    return df.groupby("date")[cols].rank(pct=True)


# --------------------------------------------------------------------------- #
# Model grid
# --------------------------------------------------------------------------- #
def grid():
    out = []
    g = CONFIG["modelGrid"]
    for fam in ("LGBM", "XGB", "RF", "ET", "RIDGE", "ENET"):
        spec = g[fam]
        for fs, obj, hp in itertools.product(spec["featureSets"], spec["objectives"], spec["hyperparameters"]):
            out.append({"id": f"{fam}_{fs}_{obj}_{hp['id']}", "family": fam, "fs": fs, "objective": obj, "hp": hp, "horizon": 126})
    for name in g["RULE"]["strategies"]:
        out.append({"id": f"RULE_{name}", "family": "RULE", "fs": None, "objective": None, "hp": {}, "horizon": 126})
    return out


def grid_h252():
    out = []
    g = CONFIG["modelGrid"]
    for fam, fss in (("LGBM", ["CIM"]), ("RIDGE", g["RIDGE"]["featureSets"])):
        spec = g[fam]
        for fs, obj, hp in itertools.product(fss, spec["objectives"], spec["hyperparameters"]):
            out.append({"id": f"H252_{fam}_{fs}_{obj}_{hp['id']}", "family": fam, "fs": fs, "objective": obj, "hp": hp, "horizon": 252})
    return out


def _targets(train, h):
    y = train[f"y{h}"].to_numpy()
    lo, hi = np.nanpercentile(y, [1, 99])
    reg = np.clip(y, lo, hi)
    pct = train.groupby("date")[f"y{h}"].rank(pct=True).to_numpy()
    quint = np.minimum((pct * 5).astype(int), 4)
    clf = (y > CONFIG["labels"]["economicThresholdPct"] / 100).astype(int)
    return reg, pct, quint, clf


def _linear_matrix(frame, ranked, cols, layers, stats=None, interactions=False):
    market = [c for c in cols if c in layers["market"]]
    cross = [c for c in cols if c not in market]
    parts = [(ranked[cross] - 0.5).fillna(0.0)]
    m = frame[market].astype(float)
    if stats is None:
        stats = (m.mean(), m.std().replace(0, 1.0))
    parts.append(((m - stats[0]) / stats[1]).fillna(0.0).clip(-5, 5))
    for name in ("company", "industry"):
        lc = [c for c in cross if c in layers[name]]
        if lc:
            parts.append(ranked[lc].isna().mean(axis=1).rename(f"MISS_{name}").to_frame())
    X = pd.concat(parts, axis=1)
    if interactions:
        for a, b in CONFIG["features"]["declaredInteractions"]:
            if a in X and b in X:
                X[f"X_{a}__{b}"] = X[a] * X[b]
    return X.to_numpy(dtype=np.float32), stats


def _tree_matrix(frame, ranked, cols, layers, impute=False, medians=None):
    market = [c for c in cols if c in layers["market"]]
    cross = [c for c in cols if c not in market]
    X = pd.concat([ranked[cross], frame[market].astype(float)], axis=1)
    if impute:
        if medians is None:
            medians = frame[market].median()
        X[cross] = X[cross].fillna(0.5)
        X[market] = X[market].fillna(medians)
    return X.to_numpy(dtype=np.float32), medians


def fit_predict(cfg, train, test, train_ranked, test_ranked, layers, want_train_pred=False):
    """Fit one configuration on `train` and score `test`. Returns (test scores, train scores or None, fitted model, feature names)."""
    fam, obj, hp, h = cfg["family"], cfg["objective"], cfg["hp"], cfg["horizon"]
    cols = feature_set(layers, "CIM" if cfg["fs"] == "CIMX" else cfg["fs"])
    reg, pct, quint, clf = _targets(train, h)
    if fam in ("RIDGE", "ENET"):
        from sklearn.linear_model import ElasticNet, Ridge
        Xtr, stats = _linear_matrix(train, train_ranked, cols, layers, interactions=cfg["fs"] == "CIMX")
        Xte, _ = _linear_matrix(test, test_ranked, cols, layers, stats, interactions=cfg["fs"] == "CIMX")
        target = reg if obj == "REG" else pct - 0.5
        model = Ridge(alpha=hp["alpha"]) if fam == "RIDGE" else ElasticNet(alpha=hp["alpha"], l1_ratio=hp["l1_ratio"], max_iter=5000)
        model.fit(Xtr, target)
        pred = model.predict(Xte)
        return pred, (model.predict(Xtr) if want_train_pred else None), model, cols
    if fam in ("RF", "ET"):
        from sklearn.ensemble import ExtraTreesClassifier, ExtraTreesRegressor, RandomForestClassifier, RandomForestRegressor
        Xtr, med = _tree_matrix(train, train_ranked, cols, layers, impute=True)
        Xte, _ = _tree_matrix(test, test_ranked, cols, layers, impute=True, medians=med)
        kw = dict(n_estimators=hp["n_estimators"], min_samples_leaf=hp["min_samples_leaf"], max_features=hp["max_features"],
                  max_samples=hp["max_samples"], bootstrap=True, n_jobs=1, random_state=7)
        if obj == "CLF":
            model = (RandomForestClassifier if fam == "RF" else ExtraTreesClassifier)(**kw).fit(Xtr, clf)
            return model.predict_proba(Xte)[:, 1], (model.predict_proba(Xtr)[:, 1] if want_train_pred else None), model, cols
        model = (RandomForestRegressor if fam == "RF" else ExtraTreesRegressor)(**kw).fit(Xtr, pct)
        return model.predict(Xte), (model.predict(Xtr) if want_train_pred else None), model, cols
    Xtr, _ = _tree_matrix(train, train_ranked, cols, layers)
    Xte, _ = _tree_matrix(test, test_ranked, cols, layers)
    if fam == "LGBM":
        import lightgbm as lgb
        p = {k: v for k, v in hp.items() if k != "id"} | CONFIG["modelGrid"]["LGBM"]["fixed"]
        if obj == "REG":
            model = lgb.LGBMRegressor(**p).fit(Xtr, reg)
        elif obj == "CLF":
            model = lgb.LGBMClassifier(**p).fit(Xtr, clf)
        else:
            groups = train.groupby("date", sort=False).size().to_numpy()
            model = lgb.LGBMRanker(objective="lambdarank", label_gain=list(range(5)), **p).fit(Xtr, quint, group=groups)
        if obj == "CLF":
            return model.predict_proba(Xte)[:, 1], (model.predict_proba(Xtr)[:, 1] if want_train_pred else None), model, cols
        return model.predict(Xte), (model.predict(Xtr) if want_train_pred else None), model, cols
    import xgboost as xgb
    p = {k: v for k, v in hp.items() if k != "id"} | CONFIG["modelGrid"]["XGB"]["fixed"]
    if obj == "REG":
        model = xgb.XGBRegressor(objective="reg:squarederror", **p).fit(Xtr, reg)
    elif obj == "CLF":
        model = xgb.XGBClassifier(objective="binary:logistic", **p).fit(Xtr, clf)
    else:
        qid = train["date"].rank(method="dense").astype(np.int64).to_numpy()   # small ordinal ids: xgboost narrows qid
        model = xgb.XGBRanker(objective="rank:pairwise", **p).fit(Xtr, quint, qid=qid)
    if obj == "CLF":
        return model.predict_proba(Xte)[:, 1], (model.predict_proba(Xtr)[:, 1] if want_train_pred else None), model, cols
    return model.predict(Xte), (model.predict(Xtr) if want_train_pred else None), model, cols


def rule_score(name, ranked):
    if name == "FOUR_FACTOR":
        parts = [ranked["A07_momentum12_1"], ranked["B01_bookToMarket"], ranked["C02_returnOnEquity"], 1 - ranked["F02_downsideVol126"]]
        return pd.concat(parts, axis=1).mean(axis=1, skipna=True)
    if name == "MOMENTUM":
        return ranked["A07_momentum12_1"]
    if name == "LOW_VOL":
        return 1 - ranked["F02_downsideVol126"]
    if name == "VALUE":
        return ranked["B01_bookToMarket"]
    if name == "QUALITY":
        return ranked["C02_returnOnEquity"]
    if name == "INDUSTRY_MOMENTUM":
        return ranked["H01_industryRelMom126"] + 0.01 * ranked["A09_industryRelativeMomentum126"].fillna(0)
    if name == "ETF_ONLY":
        return pd.Series(np.nan, index=ranked.index)
    raise KeyError(name)


def fold_split(df, year, h):
    first = df.loc[df["date"].dt.year == year, "date"].min()
    train = df[(df["date"] < first) & df[f"y{h}"].notna() & (df[f"exit{h}"] < first)]
    test = df[df["date"].dt.year == year]
    return train, test


def spearman_by_date(frame, score_col, y_col):
    """Per-date Spearman correlation (Pearson on within-date average ranks), vectorised; dates with < 20 pairs are NaN."""
    f = frame[["date", score_col, y_col]].dropna()
    g = f.groupby("date")
    x = g[score_col].rank()
    y = g[y_col].rank()
    t = pd.DataFrame({"date": f["date"], "x": x, "y": y, "xy": x * y, "xx": x * x, "yy": y * y})
    s = t.groupby("date").agg(n=("x", "size"), sx=("x", "sum"), sy=("y", "sum"), sxy=("xy", "sum"), sxx=("xx", "sum"), syy=("yy", "sum"))
    cov = s["sxy"] - s["sx"] * s["sy"] / s["n"]
    vx = s["sxx"] - s["sx"] ** 2 / s["n"]
    vy = s["syy"] - s["sy"] ** 2 / s["n"]
    with np.errstate(invalid="ignore", divide="ignore"):
        rho = cov / np.sqrt(vx * vy)
    return rho.where((s["n"] >= 20) & (vx > 0) & (vy > 0))


# --------------------------------------------------------------------------- #
# Portfolio
# --------------------------------------------------------------------------- #
def sell_tax_bps(date):
    sched = CONFIG["portfolio"]["costs"]["stock"]["sellTaxSchedule"]
    eff = [r for r in sched if r["effectiveDate"] <= str(pd.Timestamp(date).date())]
    return max(eff, key=lambda r: r["effectiveDate"])["sellTaxBps"]


def stock_cost_bps(date, side, mult=1.0):
    c = CONFIG["portfolio"]["costs"]["stock"]
    bps = c["commissionBps"] + c["spreadBps"] / 2 + (sell_tax_bps(date) if side == "sell" else 0.0)
    return bps * mult


def etf_cost_bps(mult=1.0):
    c = CONFIG["portfolio"]["costs"]["etf"]
    return (c["commissionBps"] + c["spreadBps"] / 2) * mult


def round_trip_hurdle(date, mult=1.0):
    return (stock_cost_bps(date, "buy", mult) + stock_cost_bps(date, "sell", mult) + 2 * etf_cost_bps(mult)) / 1e4


def quality_mask(df):
    q = CONFIG["portfolio"]["quality"]
    return (df["tradableAtSignal"].astype(bool) & (df["isPreferredShare"] != True) &  # noqa: E712
            (df["E04_tradabilityGuard20"] >= q["E04_tradabilityGuard20"]) & (df["E07_suspensionStaleRisk"].fillna(1) <= q["E07_suspensionStaleRisk"]) &
            (df["E03_capacityMedianTradedValue60"] >= q["E03_minMedianTradedValueKrw"]))


def bucket_of(pct):
    edges = CONFIG["portfolio"]["calibrationBuckets"]
    out = np.full(len(pct), len(edges) - 1)
    for i, (lo, hi) in enumerate(edges):
        out[(pct >= lo) & (pct < hi)] = i
    return out


def calibration_table(frame, score_col, h):
    """Per signal date: mean realised excess per score bucket among quality-eligible names, and that date's label exit session."""
    f = frame[frame["_q"] & frame[score_col].notna()][["date", score_col, f"y{h}", f"exit{h}"]].copy()
    f["pct"] = f.groupby("date")[score_col].rank(pct=True)
    f["b"] = bucket_of(f["pct"].to_numpy())
    f = f[f[f"y{h}"].notna()]
    tab = f.pivot_table(index="date", columns="b", values=f"y{h}", aggfunc="mean")
    ex = frame.groupby("date")[f"exit{h}"].first()
    return tab, ex


def decide(frame_on_date, score_col, calib, exit_by_date, date, h, max_names=5, gate=True, cost_mult=1.0, exclude=()):
    """Target stock weights on one rebalance date. Returns (weights, diagnostic)."""
    g = frame_on_date[frame_on_date["_q"] & frame_on_date[score_col].notna() & ~frame_on_date["ticker"].isin(exclude)]
    if g.empty:
        return {}, {"reason": "NO_SCORED_ELIGIBLE"}
    g = g.assign(pct=g[score_col].rank(pct=True))
    g = g.assign(b=bucket_of(g["pct"].to_numpy())).sort_values([score_col, "ticker"], ascending=[False, True])
    if not gate:
        picks = g.head(max_names)
        return {t: 1.0 / max_names for t in picks["ticker"]}, {"reason": "FORCED"}
    matured = exit_by_date[(exit_by_date < date)].index
    tab = calib.reindex(matured).dropna(how="all")
    if len(tab) < CONFIG["portfolio"]["minimumCalibrationDates"]:
        return {}, {"reason": "CALIBRATION_NOT_READY", "datesMatured": int(len(tab))}
    expected = tab.mean(axis=0)
    hurdle = round_trip_hurdle(date, cost_mult)
    g = g.assign(expNet=g["b"].map(expected).astype(float) - hurdle)
    eligible = g["b"].isin(CONFIG["portfolio"]["eligibleBuckets"])
    picks = g[eligible & (g["expNet"] > 0)].head(max_names)
    w = CONFIG["portfolio"]["weightPerName"]
    return {t: w for t in picks["ticker"]}, {"reason": "GATED", "expectedByBucket": {int(k): float(v) for k, v in expected.items()},
                                             "hurdle": hurdle, "picked": len(picks)}


class PriceBook:
    def __init__(self, prices, tickers, sessions, bench):
        self.sessions = sessions
        self.pos = {d: i for i, d in enumerate(sessions)}
        self.tickers = list(tickers)
        self.col = {t: j for j, t in enumerate(self.tickers)}
        close = pd.DataFrame({t: closes_on(prices, t, sessions) for t in self.tickers})
        volume = pd.DataFrame({t: volumes_on(prices, t, sessions) for t in self.tickers})
        self.carry = close.ffill()
        self.ret = (self.carry / self.carry.shift(1) - 1).fillna(0.0).to_numpy()
        self.tradable = (close.notna() & (volume.fillna(0) > 0)).to_numpy()
        self.carry_np = self.carry.to_numpy()
        b = bench.ffill()
        self.bench = b
        self.bench_ret = (b / b.shift(1) - 1).fillna(0.0).to_numpy()
        end = bench.last_valid_index()
        last = close.apply(lambda s: s.last_valid_index())
        # Terminated: a name whose last finite close is more than 5 sessions before the benchmark's last close.
        self.terminal = {t: self.pos[d] for t, d in last.items() if d is not None and self.pos[d] < self.pos[end] - 5}


def simulate(book, schedule, start, end, terminal_mode="ZERO", cost_mult=1.0, record=False):
    """Daily NAV. `schedule`: {execution_session: target stock weights}. ETF holds the rest. Trades at the execution session's close.
    terminal_mode ZERO: a held name with no close after its last priced session is written off (lower bound);
    LAST: it is converted into the ETF at its last close (upper bound). Neither is a measured consideration."""
    idx = [i for i, d in enumerate(book.sessions) if start <= d <= end]
    sched = {book.pos[d]: w for d, w in schedule.items() if d in book.pos}
    hold, etf, nav = {}, 1.0, 1.0
    navs = np.empty(len(idx))
    stock_turn = total_turn = costs = 0.0
    contrib = {} if record else None
    trades, holdings, terminal_hits = [], [], []
    R, BR, TR = book.ret, book.bench_ret, book.tradable
    for k, i in enumerate(idx):
        d = book.sessions[i]
        if k > 0:
            new_hold = {}
            for t, v in hold.items():
                term = book.terminal.get(t)
                if term is not None and i > term:
                    terminal_hits.append((str(d.date()), t, v / nav))
                    if terminal_mode == "ZERO":
                        if record:
                            contrib.setdefault(t, np.zeros(len(idx)))[k] -= v / nav
                        continue
                    etf += v
                    continue
                r = R[i, book.col[t]]
                if record:
                    contrib.setdefault(t, np.zeros(len(idx)))[k] += v * r / nav
                new_hold[t] = v * (1 + r)
            if record:
                contrib.setdefault(BENCH, np.zeros(len(idx)))[k] += etf * BR[i] / nav
            etf *= 1 + BR[i]
            hold = new_hold
            nav = etf + sum(hold.values())
        if i in sched:
            target = sched[i]
            cur = {t: v / nav for t, v in hold.items()}
            new, cost = {}, 0.0
            for t in sorted(set(cur) | set(target)):
                c, w = cur.get(t, 0.0), target.get(t, 0.0)
                tradable = t in book.col and bool(TR[i, book.col[t]]) and not (t in book.terminal and i > book.terminal[t])
                if not tradable or abs(w - c) < 1e-12:
                    if c > 0:
                        new[t] = c
                    continue
                side = "buy" if w > c else "sell"
                cost += abs(w - c) * stock_cost_bps(d, side, cost_mult) / 1e4
                stock_turn += abs(w - c)
                if record:
                    trades.append({"date": str(d.date()), "ticker": t, "side": side, "fromWeight": round(c, 6), "toWeight": round(w, 6),
                                   "close": float(book.carry_np[i, book.col[t]])})
                if w > 0:
                    new[t] = w
            etf_w_old = etf / nav
            etf_w_new = 1.0 - sum(new.values())
            cost += abs(etf_w_new - etf_w_old) * etf_cost_bps(cost_mult) / 1e4
            total_turn += abs(etf_w_new - etf_w_old) + sum(abs(new.get(t, 0) - cur.get(t, 0)) for t in set(new) | set(cur))
            nav *= 1 - cost
            costs += cost
            hold = {t: w * nav for t, w in new.items()}
            etf = etf_w_new * nav
            if record:
                holdings.append({"date": str(d.date()), "weights": {t: round(w, 6) for t, w in new.items()}, "etf": round(etf_w_new, 6)})
        navs[k] = nav
    days = book.sessions[idx]
    out = {"nav": pd.Series(navs, index=days), "stockTurnover": stock_turn, "totalTurnover": total_turn / 2, "costs": costs,
           "terminalHits": terminal_hits}
    if record:
        out.update(contrib=contrib, trades=trades, holdings=holdings)
    return out


def metrics(nav, bench_nav, rf_daily, stock_turnover=None, years=None):
    r = nav.pct_change().dropna()
    b = bench_nav.reindex(nav.index).pct_change().dropna()
    n = len(r)
    yrs = years or n / 252
    cagr = nav.iloc[-1] ** (1 / yrs) - 1
    bcagr = bench_nav.reindex(nav.index).iloc[-1] / bench_nav.reindex(nav.index).iloc[0]
    bcagr = bcagr ** (1 / yrs) - 1
    ex = r - rf_daily.reindex(r.index).fillna(0)
    vol = r.std() * math.sqrt(252)
    sharpe = ex.mean() / r.std() * math.sqrt(252) if r.std() > 0 else np.nan
    act = r - b
    te = act.std() * math.sqrt(252)
    dd = (nav / nav.cummax() - 1).min()
    downside = r[r < 0].std() * math.sqrt(252)
    return {"cagr": cagr, "etfCagr": bcagr, "excessCagr": cagr - bcagr, "vol": vol, "sharpe": sharpe, "sortino": (ex.mean() * 252) / downside if downside else np.nan,
            "mdd": dd, "trackingError": te, "informationRatio": (act.mean() * 252) / te if te > 0 else np.nan,
            "annualStockTurnover": (stock_turnover / yrs) if stock_turnover is not None else None, "years": yrs}
