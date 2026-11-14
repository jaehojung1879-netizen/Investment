"""us-macro-cocktail-v1 — US ETF / macro / multi-asset research library (Track A).

Research-only and self-contained: it reads the frozen raw snapshot under
``data/raw`` (see ``fetch_data.py`` and ``data/manifest.json``) and imports no
repository pipeline module, so no sealed closure or common module is touched.
Every rule implemented here is the one written in ``protocol.json`` before any
return was computed; ``protocol_digest`` is checked by the runner and tests.
"""
from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
RAW = HERE / "data" / "raw"
MANIFEST = HERE / "data" / "manifest.json"
PROTOCOL = HERE / "protocol.json"
PROTOCOL_SHA256 = "0df428212f761b6e3fe4609dabe218df564105f820ead0babdbaf2533c948e43"

ASSETS = ["SPY", "QQQ", "IEF", "TLT", "SHY", "BIL", "GLD", "UUP"]
FRED_STATE = ["DGS10", "DGS2", "DGS3MO", "DTB3", "T10YIE", "DFII10", "VIXCLS", "DEXKOUS", "DTWEXBGS"]
BUY_BPS, SELL_BPS = 10.0, 13.0
S4 = {"SPY": 0.50, "IEF": 0.30, "GLD": 0.10, "BIL": 0.10}
STATE_COLS = ["spyEx12", "spyEx1", "iefEx12", "gldEx12", "uup6", "logVolSpy63", "vix",
              "corrSpyIef126", "corrSpyGld126", "corrSpyUup126", "y10", "dY10_63",
              "curve10y3m", "dBreakeven63", "realYield10"]
STRATEGIES = ["S1_SPY", "S2_QQQ", "S3_6040", "S4_BALANCED", "S5_EQUAL4", "S6_RISK_BUDGET_IV",
              "S7_VOLTARGET_SPY", "D1_TREND_SIGN", "D2_ERC_COV", "D3_STATE_RULES",
              "D4_RIDGE_SIGN", "D5_TREE_SIGN", "D6_FORECAST_VOL_SLEEVE"]
MIN_TRAIN = 60


# ----------------------------------------------------------------------------- identity
def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_inputs() -> dict:
    """Protocol digest and every raw file's uncompressed SHA-256 against the manifest."""
    if sha256_file(PROTOCOL) != PROTOCOL_SHA256:
        raise RuntimeError("PROTOCOL_CHANGED")
    manifest = json.loads(MANIFEST.read_text())
    for name, meta in manifest["files"].items():
        body = gzip.decompress((RAW / name).read_bytes())
        if hashlib.sha256(body).hexdigest() != meta["sha256"]:
            raise RuntimeError(f"RAW_INPUT_CHANGED {name}")
    return {"protocolSha256": PROTOCOL_SHA256, "manifestSha256": sha256_file(MANIFEST),
            "files": len(manifest["files"])}


# ----------------------------------------------------------------------------- loading
def load_yahoo(symbol: str) -> pd.DataFrame:
    name = RAW / f"yahoo_{symbol.replace('=', '_')}.json.gz"
    res = json.loads(gzip.decompress(name.read_bytes()))["chart"]["result"][0]
    tz = res["meta"].get("exchangeTimezoneName", "America/New_York")
    idx = pd.to_datetime(res["timestamp"], unit="s", utc=True).tz_convert(tz).normalize().tz_localize(None)
    q = res["indicators"]["quote"][0]
    df = pd.DataFrame({"close": q["close"], "volume": q.get("volume")}, index=idx)
    df["adjclose"] = res["indicators"].get("adjclose", [{}])[0].get("adjclose")
    df["dividend"] = 0.0
    df["splitRatio"] = 1.0
    events = res.get("events", {})
    for item in events.get("dividends", {}).values():
        day = pd.Timestamp(item["date"], unit="s", tz="UTC").tz_convert(tz).normalize().tz_localize(None)
        if day in df.index:
            df.loc[day, "dividend"] += float(item["amount"])
        else:
            df.loc[day, "dividend"] = float(item["amount"])  # surfaces as an extra row in the audit
    for item in events.get("splits", {}).values():
        day = pd.Timestamp(item["date"], unit="s", tz="UTC").tz_convert(tz).normalize().tz_localize(None)
        df.loc[day, "splitRatio"] = float(item["numerator"]) / float(item["denominator"])
    df.index.name = "date"
    return df.sort_index()


def load_fred(series: str) -> pd.Series:
    text = gzip.decompress((RAW / f"fred_{series}.csv.gz").read_bytes()).decode()
    rows = [line.split(",") for line in text.strip().splitlines()[1:]]
    s = pd.Series({pd.Timestamp(d): (float(v) if v not in ("", ".") else np.nan) for d, v in rows})
    return s.dropna().sort_index().rename(series)


def xnys_sessions(start: str, end: str) -> pd.DatetimeIndex:
    import exchange_calendars as xc
    cal = xc.get_calendar("XNYS", start="1990-01-01")
    return pd.DatetimeIndex(cal.sessions_in_range(start, end)).tz_localize(None)


def total_return_index(df: pd.DataFrame) -> pd.Series:
    """TR from split-adjusted close plus the dated cash distribution on its ex-date."""
    close = df["close"]
    gross = (close + df["dividend"]) / close.shift(1)
    tr = gross.fillna(1.0).cumprod()
    return tr / tr.iloc[0]


# ----------------------------------------------------------------------------- data audit
def audit_asset(symbol: str, sessions: pd.DatetimeIndex) -> dict:
    df = load_yahoo(symbol)
    first, last = df.index[0], df.index[-1]
    expected = sessions[(sessions >= first) & (sessions <= last)]
    have = df.index[df["close"].notna()]
    missing = expected.difference(have)
    extra = have.difference(expected)
    tr = total_return_index(df.loc[df["close"].notna()])
    r_ours = tr.pct_change().dropna()
    adj = df["adjclose"].dropna()
    r_adj = adj.pct_change().dropna()
    both = r_ours.index.intersection(r_adj.index)
    diff = (r_ours[both] - r_adj[both]).abs()
    price_r = df["close"].pct_change().abs()
    by_year = (df.loc[df["dividend"] > 0, "dividend"].groupby(df.index[df["dividend"] > 0].year).sum()
               / df["close"].groupby(df.index.year).last())
    return {
        "symbol": symbol, "firstSession": str(first.date()), "lastSession": str(last.date()),
        "sessions": int(len(have)), "missingXnysSessions": int(len(missing)),
        "missingSample": [str(d.date()) for d in missing[:10]],
        "extraNonSessionRows": int(len(extra)), "extraSample": [str(d.date()) for d in extra[:10]],
        "duplicateDates": int(df.index.duplicated().sum()),
        "nonPositiveCloses": int((df["close"] <= 0).sum()),
        "distributionEvents": int((df["dividend"] > 0).sum()),
        "splitEvents": [{"date": str(d.date()), "ratio": float(r)} for d, r in df.loc[df["splitRatio"] != 1.0, "splitRatio"].items()],
        "maxAbsDailyCloseMovePct": round(float(price_r.max() * 100), 3),
        "maxAbsDailyCloseMoveDate": str(price_r.idxmax().date()),
        "trVsVendorAdjclose": {
            "comparedSessions": int(len(both)),
            "medianAbsDailyDiffBp": round(float(diff.median() * 1e4), 4),
            "p99AbsDailyDiffBp": round(float(diff.quantile(0.99) * 1e4), 4),
            "maxAbsDailyDiffBp": round(float(diff.max() * 1e4), 3),
            "sessionsAbove1bp": int((diff > 1e-4).sum()),
            "cumulativeTrRatioOursOverVendor": round(float((1 + r_ours[both]).prod() / (1 + r_adj[both]).prod()), 6),
        },
        "trailingDistributionYieldByYearPct": {int(k): round(float(v * 100), 3) for k, v in by_year.dropna().items() if k >= 2008},
    }


def cross_vendor_checks() -> dict:
    out = {}
    for etf, idx_name in (("SPY", "SP500"), ("QQQ", "NASDAQ100")):
        df = load_yahoo(etf)
        ix = load_fred(idx_name)
        common = df.index.intersection(ix.index)
        common = common[common >= pd.Timestamp("2016-11-14")]
        etf_r = df.loc[common, "close"].pct_change()
        ix_r = ix[common].pct_change()
        exdiv = df.loc[common, "dividend"] > 0
        d = (etf_r - ix_r)[~exdiv].dropna().abs()
        out[f"{etf}_vs_FRED_{idx_name}"] = {
            "basis": "ETF price return vs index price return on common sessions, ex-dividend sessions excluded",
            "sessions": int(len(d)), "medianAbsDiffBp": round(float(d.median() * 1e4), 3),
            "p99AbsDiffBp": round(float(d.quantile(0.99) * 1e4), 3),
            "sessionsAbove50bp": int((d > 0.005).sum()),
            "returnCorrelation": round(float(np.corrcoef(etf_r[~exdiv].dropna(), ix_r[~exdiv].dropna().reindex(etf_r[~exdiv].dropna().index))[0, 1]), 6),
        }
    fx_y = load_yahoo("KRW=X")["close"].dropna()
    fx_f = load_fred("DEXKOUS")
    common = fx_y.index.intersection(fx_f.index)
    common = common[common >= pd.Timestamp("2008-01-01")]
    rel = (fx_y[common] / fx_f[common] - 1).abs()
    rel = rel[np.isfinite(rel)]
    out["USDKRW_Yahoo_vs_FRED_DEXKOUS"] = {
        "basis": "same calendar date; Yahoo KRW=X is a vendor composite whose snapshot time differs from the H.10 noon-New-York print",
        "dates": int(len(rel)), "medianAbsRelDiffPct": round(float(rel.median() * 100), 4),
        "p99AbsRelDiffPct": round(float(rel.quantile(0.99) * 100), 4),
        "datesAbove1pct": int((rel > 0.01).sum()),
    }
    return out


def compare_with_repo_snapshot(tr: pd.DataFrame) -> dict:
    """Cross-check SPY/QQQ TR against the repository's sealed dual-benchmark snapshot (same vendor, earlier fetch)."""
    path = HERE.parents[1] / "data" / "research" / "us-dual-benchmark-v1" / "spy-qqq-total-return.csv.gz"
    if not path.exists():
        return {"status": "SNAPSHOT_NOT_PRESENT"}
    snap = pd.read_csv(path)
    snap["date"] = pd.to_datetime(snap["date"], format="%Y-%m-%d")
    out = {"path": str(path.relative_to(HERE.parents[1])),
           "basis": "repository replay-v16 as-traded forward total return (same vendor, earlier fetch); daily return comparison"}
    for sym in ("SPY", "QQQ"):
        s = snap.loc[snap["ticker"] == sym].set_index("date")["totalReturnClose"].dropna()
        common = s.index.intersection(tr.index)
        a = s[common].pct_change().dropna()
        b = tr.loc[common, sym].pct_change().dropna()
        d = (a - b).abs()
        out[sym] = {"sessions": int(len(d)), "first": str(common[0].date()), "last": str(common[-1].date()),
                    "medianAbsDiffBp": round(float(d.median() * 1e4), 4), "p99AbsDiffBp": round(float(d.quantile(0.99) * 1e4), 3),
                    "maxAbsDiffBp": round(float(d.max() * 1e4), 3), "sessionsAbove1bp": int((d > 1e-4).sum()),
                    "cumulativeRatioOursOverRepo": round(float((1 + b).prod() / (1 + a).prod()), 6)}
    return out


# ----------------------------------------------------------------------------- panel
@dataclass
class Panel:
    sessions: pd.DatetimeIndex
    tr: pd.DataFrame          # TR index per asset on XNYS sessions
    ret: pd.DataFrame         # daily TR returns
    fred: pd.DataFrame        # FRED values usable at each session (strictly earlier observation)
    fx_next: pd.Series        # DEXKOUS first print dated strictly after each session
    fx_same: pd.Series        # DEXKOUS last print dated on or before each session


def build_panel(end: str = "2026-11-09") -> Panel:
    sessions = xnys_sessions("2007-05-30", end)
    tr = {}
    for a in ASSETS:
        df = load_yahoo(a)
        df = df.loc[df["close"].notna()]
        t = total_return_index(df)
        tr[a] = t.reindex(sessions)
    tr = pd.DataFrame(tr)
    if tr.isna().any().any():
        bad = tr.isna().sum()
        raise RuntimeError(f"PANEL_GAP {bad[bad > 0].to_dict()}")
    ret = tr.pct_change().fillna(0.0)
    fred = {}
    for s in FRED_STATE:
        series = load_fred(s)
        # strictly-earlier observation: shift by one day before as-of alignment
        shifted = series.copy()
        shifted.index = shifted.index + pd.Timedelta(days=1)
        fred[s] = shifted.reindex(shifted.index.union(sessions)).ffill().reindex(sessions)
    fred = pd.DataFrame(fred)
    fx = load_fred("DEXKOUS")
    nxt = pd.Series(index=sessions, dtype=float)
    pos = fx.index.searchsorted(sessions, side="right")
    nxt[:] = [fx.iloc[p] if p < len(fx) else np.nan for p in pos]
    same = fx.reindex(fx.index.union(sessions)).ffill().reindex(sessions)
    return Panel(sessions, tr, ret, fred, nxt, same)


def month_end_sessions(sessions: pd.DatetimeIndex) -> pd.DatetimeIndex:
    s = pd.Series(sessions, index=sessions)
    return pd.DatetimeIndex(s.groupby([sessions.year, sessions.month]).max().values)


# ----------------------------------------------------------------------------- state
def state_frame(p: Panel) -> pd.DataFrame:
    tr, r = p.tr, p.ret
    out = pd.DataFrame(index=p.sessions)

    def ex(a, n):
        return tr[a] / tr[a].shift(n) - tr["BIL"] / tr["BIL"].shift(n)
    out["spyEx12"] = ex("SPY", 252)
    out["spyEx1"] = ex("SPY", 21)
    out["iefEx12"] = ex("IEF", 252)
    out["gldEx12"] = ex("GLD", 252)
    out["uup6"] = tr["UUP"] / tr["UUP"].shift(126) - 1
    out["logVolSpy63"] = np.log(r["SPY"].rolling(63).std() * np.sqrt(252))
    out["vix"] = p.fred["VIXCLS"]
    out["corrSpyIef126"] = r["SPY"].rolling(126).corr(r["IEF"])
    out["corrSpyGld126"] = r["SPY"].rolling(126).corr(r["GLD"])
    out["corrSpyUup126"] = r["SPY"].rolling(126).corr(r["UUP"])
    out["y10"] = p.fred["DGS10"]
    out["dY10_63"] = p.fred["DGS10"] - p.fred["DGS10"].shift(63)
    out["curve10y3m"] = p.fred["DGS10"] - p.fred["DGS3MO"]
    out["dBreakeven63"] = p.fred["T10YIE"] - p.fred["T10YIE"].shift(63)
    out["realYield10"] = p.fred["DFII10"]
    return out[STATE_COLS]


# ----------------------------------------------------------------------------- schedule
@dataclass
class Schedule:
    decisions: pd.DatetimeIndex
    executions: pd.DatetimeIndex   # executions[i] follows decisions[i]


def schedule(p: Panel, first_decision: str, last: str) -> Schedule:
    me = month_end_sessions(p.sessions)
    me = me[(me >= pd.Timestamp(first_decision)) & (me <= pd.Timestamp(last))]
    pos = p.sessions.searchsorted(me, side="right")
    keep = pos < len(p.sessions)
    return Schedule(me[keep], p.sessions[pos[keep]])


# ----------------------------------------------------------------------------- allocation rules
def _norm(w: dict) -> dict:
    w = {k: float(v) for k, v in w.items() if v > 1e-12}
    s = sum(w.values())
    return {k: v / s for k, v in w.items()}


def erc_weights(cov: np.ndarray) -> np.ndarray:
    """Equal risk contribution, long-only: argmin 0.5 w'Cw - (1/n) sum log w, then normalise (Spinu 2013)."""
    from scipy.optimize import minimize
    n = cov.shape[0]
    x0 = 1 / np.sqrt(np.diag(cov))

    def f(y):
        return 0.5 * y @ cov @ y - np.log(y).sum() / n

    def g(y):
        return cov @ y - 1 / (n * y)
    res = minimize(f, x0, jac=g, method="L-BFGS-B", bounds=[(1e-10, None)] * n,
                   options={"ftol": 1e-15, "gtol": 1e-12, "maxiter": 10000})
    w = res.x / res.x.sum()
    return w


def sign_mapping(signs: dict) -> dict:
    """S4 sleeves SPY/IEF/GLD kept iff their signal is positive, else moved to BIL."""
    w = dict(S4)
    for a in ("SPY", "IEF", "GLD"):
        if not signs[a]:
            w["BIL"] += w[a]
            w[a] = 0.0
    return _norm(w)


class WalkForward:
    """Monthly walk-forward models; labels admitted only after their window closed."""

    def __init__(self, p: Panel, state: pd.DataFrame, decisions: pd.DatetimeIndex, executions: pd.DatetimeIndex):
        from sklearn.linear_model import Ridge
        from sklearn.tree import DecisionTreeRegressor
        self.Ridge, self.Tree = Ridge, DecisionTreeRegressor
        self.p, self.state = p, state
        self.dec, self.exe = decisions, executions
        self.X = state.loc[decisions, STATE_COLS]
        sidx = p.sessions
        self.exe_pos = sidx.get_indexer(executions)
        self.dec_pos = sidx.get_indexer(decisions)
        tr = p.tr
        nxt = list(executions[1:]) + [None]
        y = {}
        self.label_end = {}
        for a in ("SPY", "IEF", "GLD"):
            vals = []
            for e, n in zip(executions, nxt):
                vals.append(np.nan if n is None else (tr.at[n, a] / tr.at[e, a]) - (tr.at[n, "BIL"] / tr.at[e, "BIL"]))
            y[a] = pd.Series(vals, index=decisions)
        self.y_month = pd.DataFrame(y)
        self.month_label_end = pd.Series([sidx.get_loc(n) if n is not None else 10**9 for n in nxt], index=decisions)
        r = p.ret["SPY"].values
        vol = []
        vol_end = []
        for ep in self.exe_pos:
            seg = r[ep + 1: ep + 64]
            vol.append(np.log(np.std(seg, ddof=1) * np.sqrt(252)) if len(seg) == 63 else np.nan)
            vol_end.append(ep + 63)
        self.y_vol = pd.Series(vol, index=decisions)
        self.vol_label_end = pd.Series(vol_end, index=decisions)
        self.records = []

    def _train(self, i: int, y: pd.Series, label_end: pd.Series):
        d = self.dec[i]
        cutoff = self.dec_pos[i]
        ok = (label_end <= cutoff) & y.notna() & self.X.notna().all(axis=1) & (self.dec < d)
        return self.X[ok], y[ok]

    @staticmethod
    def _std(Xtr, x):
        mu, sd = Xtr.mean(), Xtr.std(ddof=0).replace(0, 1.0)
        return (Xtr - mu) / sd, (x - mu) / sd

    def sign_forecast(self, i: int, kind: str):
        x = self.X.iloc[[i]]
        if x.isna().any(axis=1).iloc[0]:
            return None, {}
        preds = {}
        for a in ("SPY", "IEF", "GLD"):
            Xtr, ytr = self._train(i, self.y_month[a], self.month_label_end)
            if len(ytr) < MIN_TRAIN:
                return None, {"trainingSamples": int(len(ytr))}
            Z, z = self._std(Xtr, x)
            if kind == "ridge":
                m = self.Ridge(alpha=10.0).fit(Z.values, ytr.values)
            else:
                m = self.Tree(max_depth=2, min_samples_leaf=24, random_state=0).fit(Z.values, ytr.values)
            preds[a] = float(m.predict(z.values)[0])
        return preds, {"trainingSamples": int(len(ytr))}

    def vol_forecast(self, i: int):
        x = self.X.iloc[[i]]
        Xtr, ytr = self._train(i, self.y_vol, self.vol_label_end)
        if len(ytr) < MIN_TRAIN or x.isna().any(axis=1).iloc[0]:
            return None
        Z, z = self._std(Xtr, x)
        m = self.Ridge(alpha=1.0).fit(Z.values, ytr.values)
        return float(np.exp(m.predict(z.values)[0]))


def target_weights(name: str, i: int, p: Panel, state: pd.DataFrame, wf: WalkForward) -> tuple[dict, dict]:
    d = wf.dec[i]
    pos = wf.dec_pos[i]
    st = state.loc[d]
    r = p.ret
    info: dict = {}
    if name == "S1_SPY":
        return {"SPY": 1.0}, info
    if name == "S2_QQQ":
        return {"QQQ": 1.0}, info
    if name == "S3_6040":
        return {"SPY": 0.6, "IEF": 0.4}, info
    if name == "S4_BALANCED":
        return dict(S4), info
    if name == "S5_EQUAL4":
        return {"SPY": .25, "IEF": .25, "GLD": .25, "BIL": .25}, info
    if name == "S6_RISK_BUDGET_IV":
        vols = r[["SPY", "IEF", "GLD"]].iloc[pos - 251: pos + 1].std()
        inv = 1 / vols
        return _norm((inv / inv.sum()).to_dict()), info
    if name == "S7_VOLTARGET_SPY":
        vol = r["SPY"].iloc[pos - 62: pos + 1].std() * np.sqrt(252)
        w = min(1.0, 0.15 / vol)
        return _norm({"SPY": w, "BIL": 1 - w}), {"spyVol63": float(vol)}
    if name == "D1_TREND_SIGN":
        signs = {"SPY": st["spyEx12"] > 0, "IEF": st["iefEx12"] > 0, "GLD": st["gldEx12"] > 0}
        return sign_mapping(signs), {k: bool(v) for k, v in signs.items()}
    if name == "D2_ERC_COV":
        from sklearn.covariance import LedoitWolf
        window = r[["SPY", "IEF", "GLD"]].iloc[pos - 125: pos + 1].values
        cov = LedoitWolf().fit(window).covariance_
        w = erc_weights(cov)
        return _norm(dict(zip(["SPY", "IEF", "GLD"], w))), info
    if name == "D3_STATE_RULES":
        w = dict(S4)
        w["SHY"] = 0.0
        w["UUP"] = 0.0
        fired = []
        if st["spyEx12"] < 0:
            w["BIL"] += w["SPY"] / 2
            w["SPY"] /= 2
            fired.append("a_equityTrendOff")
        if st["corrSpyIef126"] > 0 and st["dY10_63"] > 0:
            w["SHY"] += w["IEF"]
            w["IEF"] = 0.0
            fired.append("b_bondsNotHedgingRatesRising")
        if st["spyEx12"] < 0 and st["uup6"] > 0:
            w["UUP"] += 0.10
            w["BIL"] -= 0.10
            fired.append("c_dollarStrongInEquityDowntrend")
        return _norm(w), {"fired": fired}
    if name in ("D4_RIDGE_SIGN", "D5_TREE_SIGN"):
        preds, meta = wf.sign_forecast(i, "ridge" if name.startswith("D4") else "tree")
        if preds is None:
            return dict(S4), {"fallback": "STATIC_DEFAULT_INSUFFICIENT_TRAINING", **meta}
        return sign_mapping({a: preds[a] > 0 for a in preds}), {"predictedExcess": preds, **meta}
    if name == "D6_FORECAST_VOL_SLEEVE":
        fv = wf.vol_forecast(i)
        used = "RIDGE_FORECAST"
        if fv is None:
            fv = float(r["SPY"].iloc[pos - 62: pos + 1].std() * np.sqrt(252))
            used = "TRAILING_63_FALLBACK"
        scale = min(1.0, 0.15 / fv)
        w = dict(S4)
        w["BIL"] += w["SPY"] * (1 - scale)
        w["SPY"] *= scale
        return _norm(w), {"forecastVol": fv, "volSource": used}
    raise KeyError(name)


# ----------------------------------------------------------------------------- backtest
def rebalance(values: dict, target: dict, nav_pre: float, buy: float, sell: float) -> tuple[dict, float, float]:
    """Trade drifted values to target weights; costs leave the NAV. Returns (new values, cost, traded)."""
    names = set(values) | set(target)
    nav = nav_pre
    for _ in range(50):
        cost = 0.0
        for a in names:
            delta = target.get(a, 0.0) * nav - values.get(a, 0.0)
            cost += delta * buy if delta > 0 else -delta * sell
        new_nav = nav_pre - cost
        if abs(new_nav - nav) < 1e-15:
            break
        nav = new_nav
    traded = sum(abs(target.get(a, 0.0) * nav - values.get(a, 0.0)) for a in names)
    return {a: target[a] * nav for a in target if target[a] > 0}, nav_pre - nav, traded


def backtest(targets: dict, sched: Schedule, p: Panel, end: str, cost_mult: float = 1.0) -> dict:
    """targets: decision date -> weight dict. NAV is 1.0 (uninvested) at the first decision."""
    buy, sell = BUY_BPS * 1e-4 * cost_mult, SELL_BPS * 1e-4 * cost_mult
    sess = p.sessions
    start = sess.get_loc(sched.decisions[0])
    stop = sess.get_loc(pd.Timestamp(end))
    exe_map = {e: d for d, e in zip(sched.decisions, sched.executions)}
    values: dict = {}
    cash = 1.0  # only before the first execution
    navs, costs, turnover = [], 0.0, 0.0
    ret = p.ret
    for t in range(start, stop + 1):
        day = sess[t]
        if t > start:
            for a in values:
                values[a] *= 1.0 + ret.at[day, a]
        if day in exe_map:
            nav_pre = sum(values.values()) + cash
            values, c, traded = rebalance(values, targets[exe_map[day]], nav_pre, buy, sell)
            cash = 0.0
            costs += c
            turnover += traded / (nav_pre - c)
        navs.append(sum(values.values()) + cash)
    nav = pd.Series(navs, index=sess[start: stop + 1])
    years = (nav.index[-1] - nav.index[0]).days / 365.25
    return {"nav": nav, "costTotalFrac": costs, "turnoverPerYear": turnover / years}


# ----------------------------------------------------------------------------- metrics
def month_end_series(nav: pd.Series) -> pd.Series:
    return nav.groupby([nav.index.year, nav.index.month]).tail(1)


def metrics(nav: pd.Series, bil_nav: pd.Series, spy_nav: pd.Series) -> dict:
    m = month_end_series(nav)
    mr = m.pct_change().dropna()
    b = month_end_series(bil_nav).pct_change().dropna().reindex(mr.index)
    s = month_end_series(spy_nav).pct_change().dropna().reindex(mr.index)
    years = (nav.index[-1] - nav.index[0]).days / 365.25
    cagr = (nav.iloc[-1] / nav.iloc[0]) ** (1 / years) - 1
    ex = mr - b
    dd = nav / nav.cummax() - 1
    vol = mr.std(ddof=1) * np.sqrt(12)
    beta = float(np.cov(mr, s, ddof=1)[0, 1] / np.var(s, ddof=1))
    arith = float(mr.mean() * 12)
    return {
        "start": str(nav.index[0].date()), "end": str(nav.index[-1].date()), "months": int(len(mr)),
        "cagrPct": round(cagr * 100, 3), "arithAnnualPct": round(arith * 100, 3),
        "compoundingTermPct": round((cagr - arith) * 100, 3),
        "volPct": round(vol * 100, 3),
        "sharpeOverBil": round(float(ex.mean() / ex.std(ddof=1) * np.sqrt(12)), 3) if ex.std(ddof=1) > 1e-12 else None,
        "maxDrawdownPct": round(float(dd.min() * 100), 3),
        "maxDrawdownTrough": str(dd.idxmin().date()),
        "calmar": round(float(cagr / abs(dd.min())), 3) if dd.min() < 0 else None,
        "betaToSpy": round(beta, 3),
        "worstMonthPct": round(float(mr.min() * 100), 3),
    }


def block_bootstrap_mean(x: np.ndarray, block: int = 12, draws: int = 5000, seed: int = 20261110) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    n = len(x)
    nb = int(np.ceil(n / block))
    means = np.empty(draws)
    for k in range(draws):
        starts = rng.integers(0, n - block + 1, nb)
        idx = (starts[:, None] + np.arange(block)[None, :]).ravel()[:n]
        means[k] = x[idx].mean()
    lo, hi = np.percentile(means, [2.5, 97.5])
    return float(lo), float(hi)


def paired(nav_a: pd.Series, nav_b: pd.Series) -> dict:
    a = month_end_series(nav_a).pct_change().dropna()
    b = month_end_series(nav_b).pct_change().dropna().reindex(a.index)
    d = (a - b).values
    lo, hi = block_bootstrap_mean(d)
    return {"meanAnnualDiffPct": round(float(d.mean() * 1200), 3),
            "ci95AnnualPct": [round(lo * 1200, 3), round(hi * 1200, 3)],
            "intervalContainsZero": bool(lo <= 0 <= hi), "months": int(len(d))}


def newey_west_t(d: np.ndarray, lag: int) -> tuple[float, float]:
    d = d - 0.0
    n = len(d)
    mu = d.mean()
    e = d - mu
    s = e @ e / n
    for k in range(1, lag + 1):
        w = 1 - k / (lag + 1)
        s += 2 * w * (e[k:] @ e[:-k]) / n
    se = np.sqrt(s / n)
    return float(mu), float(mu / se) if se > 0 else float("nan")
