"""Earnings-surprise tests for KR and US (PREREGISTRATION.md sections 2-4).

    python -m research.kr_us_earnings_expectations_v1.analysis --market us|kr --private <scratch> --out research/kr_us_earnings_expectations_v1/results [--stage events|books|all]

Stage "events": E-A (surprise persistence), E-B (post-filing drift, sector x size adjusted), E-H3 (SUE vs announcement reaction), coverage.
Stage "books":  E-H1, E-H2 and E-IND on weekly decision dates with the existing execution and cost engines, fixed 6/12-month holding and
L26/L52 staggered ledgers, regimes. Returns are read only here; event dates, signals and controls are fixed by the code above them.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.alpha_search_round6_v1 import common as CM  # noqa: E402
from research.kr_us_earnings_expectations_v1 import events as EVN  # noqa: E402

AI_LED = pd.Timestamp("2023-01-01")
FRESH_DAYS, SUE_MIN = 120, 1.0
HORIZONS = (21, 63, 126, 252)
US_MEGA = ("AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "GOOG", "META", "AVGO", "TSLA")
KR_SEMI_INDUSTRY = "ELECTRONICS_ELECTRICAL"
KR_TWO = ("005930.KS", "000660.KS")


# --------------------------------------------------------------------------- market adapters
class US:
    name, etf, alt = "US", "SPY", "QQQ"

    def __init__(self, private: Path):
        from research.us_selection_value_v1 import evaluate as EV
        from research.us_selection_value_v1 import restored_compare as RCMP
        self.EV = EV
        self.close, feats, self.qqq, _ = EV.load(private / "us")
        self.secs = RCMP.sections_of(feats)
        self.dates = sorted(self.secs)
        self.sess = self.close.index

    def universe(self, d):
        x = self.secs[d]
        return pd.DataFrame({"group": x["sector"], "size": x["marketCap"].astype(float), "cell": x["sector"].astype(str) + "|" + x["capTercile"].astype(str),
                             "mom": x["momentum252"], "val": x["earningsYield"], "prof": x["CASH_PROFITABILITY"]}, index=x.index)

    def semi_ai(self, t, group):
        return t in US_MEGA or group == "Information Technology"


class KR:
    name, etf, alt = "KR", "069500.KS", None

    def __init__(self, private: Path):
        from research.alpha_search_round6_v1 import kr as K6
        self.K6, self.KD, self.A, self.M, self.RC = K6, K6.KD, K6.A, K6.M, K6.RC
        self.I2, self.ctx2, self.base = self.RC.setup(str(private / "data"))
        self.close = self.I2["closes"]
        self.sess = self.I2["sessions"]
        self.dates = sorted(self.ctx2.by)

    def universe(self, d):
        g = self.ctx2.by[d]
        g = g[(g["_mcap"] > 0) & ~g["isPreferredShare"].astype(bool)].set_index("ticker")
        size = g["_mcap"].astype(float)
        terc = size.groupby(g["industry"]).transform(lambda v: pd.qcut(v.rank(method="first"), 3, labels=False) if len(v) >= 3 else 0)
        return pd.DataFrame({"group": g["industry"], "size": size, "cell": g["industry"].astype(str) + "|" + terc.astype(str),
                             "mom": g.get("A07_momentum12_1"), "val": g.get("B02_earningsYield"), "prof": g.get("C01_returnOnAssets")}, index=g.index)

    def semi_ai(self, t, group):
        return group == KR_SEMI_INDUSTRY


# --------------------------------------------------------------------------- helpers
def session_after(sess, day, strict=True):
    i = sess.searchsorted(day, side="right" if strict else "left")
    return i if i < len(sess) else None


def last_key(keys, day):
    i = int(np.searchsorted(np.array(keys, dtype="datetime64[ns]"), np.datetime64(day), side="right")) - 1
    return keys[i] if i >= 0 else None


def boot_q(values, block, two_sided=False):
    r = CM.boot(values, block)
    if two_sided and r.get("pOneSided") is not None:
        p = r["pOneSided"]
        r["pTwoSided"] = min(1.0, 2 * min(p, 1 - p + 1 / (CM.B + 1)))
    return r


# --------------------------------------------------------------------------- events stage
def build_events(mk, private: Path):
    ee = private / "ee"
    if mk.name == "US":
        ev = EVN.attach_us_announcements(EVN.us_events(private), ee / "us-8k-202.json")
    else:
        ev = EVN.attach_kr_announcements(EVN.kr_events(private), ee / "kr-prelim-list.json")
    return ev


def event_returns(mk, ev):
    """Sector x size-cell adjusted returns for each event in the market universe on its reaction day."""
    C = mk.close
    arr = C.values
    col = {t: i for i, t in enumerate(C.columns)}
    keys = mk.dates
    cache = {}
    rows = []
    for r in ev.itertuples():
        if not pd.notna(r.sue):
            continue
        rec = {"ticker": r.ticker, "fyear": r.fyear, "stage": r.stage, "periodEnd": r.periodEnd, "sue": float(r.sue), "filingDate": r.filingDate,
               "announce": r.announceEffective}
        k = last_key(keys, r.filingDate)
        if k is None:
            continue
        if k not in cache:
            cache[k] = mk.universe(k)
        u = cache[k]
        if r.ticker not in u.index or r.ticker not in col:
            continue
        rec.update(group=u.at[r.ticker, "group"], cell=u.at[r.ticker, "cell"], size=float(u.at[r.ticker, "size"]),
                   mom=u.at[r.ticker, "mom"], val=u.at[r.ticker, "val"], prof=u.at[r.ticker, "prof"], uniDate=k)
        peers = [col[t] for t in u.index[(u["cell"] == rec["cell"]) & (u.index != r.ticker)] if t in col]
        j = col[r.ticker]
        i0 = session_after(mk.sess, r.filingDate, strict=True)          # STRICT: entry at the close after the filing day
        if i0 is not None:
            for h in HORIZONS:
                if i0 + h < len(mk.sess):
                    own = arr[i0 + h, j] / arr[i0, j] - 1
                    pr = arr[i0 + h, peers] / arr[i0, peers] - 1 if peers else np.array([])
                    pr = pr[np.isfinite(pr)]
                    rec[f"strict{h}"] = own - pr.mean() if np.isfinite(own) and len(pr) else np.nan
        if pd.notna(r.announceEffective):
            t0 = session_after(mk.sess, r.announceEffective, strict=False)
            if t0 is not None and t0 >= 22 and t0 + 1 < len(mk.sess):
                def adj(a, b):
                    own = arr[b, j] / arr[a, j] - 1
                    pr = arr[b, peers] / arr[a, peers] - 1 if peers else np.array([])
                    pr = pr[np.isfinite(pr)]
                    return own - pr.mean() if np.isfinite(own) and len(pr) else np.nan
                rec["pre"] = adj(t0 - 22, t0 - 2)
                rec["ear"] = adj(t0 - 2, t0 + 1)
                for h in HORIZONS:
                    if t0 + 1 + h < len(mk.sess):
                        rec[f"post{h}"] = adj(t0 + 1, t0 + 1 + h)
        rows.append(rec)
    df = pd.DataFrame(rows)
    df["q"] = df["periodEnd"].dt.to_period("Q")
    return df


def persistence(ev):
    e = ev[ev["sue"].notna()].copy()
    nxt = e.set_index(["ticker", "fyear", "stage"])["sue"]
    def next_key(y, s):
        return (y + 1, 1) if s == 4 else (y, s + 1)
    e["sueNext"] = [nxt.get((t, *next_key(y, s)), np.nan) for t, y, s in zip(e["ticker"], e["fyear"], e["stage"])]
    e = e.dropna(subset=["sueNext"])
    e["q"] = e["periodEnd"].dt.to_period("Q")
    per = e.groupby("q").apply(lambda g: g["sue"].rank().corr(g["sueNext"].rank()) if len(g) >= 20 else np.nan).dropna()
    out = {"quarters": int(len(per)), "pairs": int(len(e)), "all": boot_q(per.tolist(), 2)}
    for lab, m in (("BEFORE_2023", per.index.to_timestamp() < AI_LED), ("FROM_2023", per.index.to_timestamp() >= AI_LED)):
        out[lab] = boot_q(per[m].tolist(), 2)
    return out, e


def spread(df, col, lo=0.2, hi=0.8, by="q", min_n=10):
    rows = []
    for q, g in df.dropna(subset=[col]).groupby(by):
        if len(g) < min_n:
            continue
        r = g["sue"].rank(pct=True)
        rows.append({"q": q, "top": g.loc[r > hi, col].mean(), "bot": g.loc[r <= lo, col].mean(), "all": g[col].mean()})
    s = pd.DataFrame(rows).sort_values("q")
    return s


def drift_tests(er, mk):
    out = {}
    for h in HORIZONS:
        for pre in ("strict", "post"):
            col = f"{pre}{h}"
            if col not in er:
                continue
            s = spread(er, col)
            block = max(1, int(round(h / 63)))
            cell = {"quarters": int(len(s)), "events": int(er[col].notna().sum()), "topMinusBottom": boot_q((s["top"] - s["bot"]).tolist(), block),
                    "topAdjusted": boot_q(s["top"].tolist(), block)}
            for lab, m in (("BEFORE_2023", s["q"].dt.to_timestamp() < AI_LED), ("FROM_2023", s["q"].dt.to_timestamp() >= AI_LED)):
                cell[lab] = boot_q((s.loc[m, "top"] - s.loc[m, "bot"]).tolist(), block)
            ex = er[~er.apply(lambda r: mk.semi_ai(r["ticker"], r["group"]), axis=1)]
            s2 = spread(ex, col)
            cell["EX_SEMI_AI"] = boot_q((s2["top"] - s2["bot"]).tolist(), block)
            out[col] = cell
    # announcement-window anatomy (ANNOUNCE timing)
    an = er.dropna(subset=["ear"])
    anat = {}
    for col in ("pre", "ear", "post21", "post63", "post126", "post252"):
        if col in an:
            s = spread(an, col)
            anat[col] = boot_q((s["top"] - s["bot"]).tolist(), 1 if col in ("pre", "ear", "post21", "post63") else 2)
    out["announceAnatomy"] = anat
    # residual: per-quarter OLS of strict126 on ranks of SUE, momentum, value, profitability (Fama-MacBeth)
    coefs = []
    for q, g in er.dropna(subset=["strict126", "mom", "val", "prof"]).groupby("q"):
        if len(g) < 30:
            continue
        X = np.column_stack([np.ones(len(g))] + [g[c].rank(pct=True).values - 0.5 for c in ("sue", "mom", "val", "prof")])
        b, *_ = np.linalg.lstsq(X, g["strict126"].values, rcond=None)
        coefs.append(b[1])
    out["residualSueCoef126"] = boot_q(coefs, 2)
    return out


def divergence(er):
    an = er.dropna(subset=["ear", "post126"])
    rows = []
    for q, g in an.groupby("q"):
        top = g[g["sue"].rank(pct=True) > 2 / 3]
        if len(top) < 9:
            continue
        er_r = top["ear"].rank(pct=True)
        lo, hi = top.loc[er_r <= 1 / 3, "post126"].mean(), top.loc[er_r > 2 / 3, "post126"].mean()
        rows.append({"q": q, "diff": lo - hi, "lowEar": lo, "highEar": hi})
    s = pd.DataFrame(rows)
    out = {"quarters": int(len(s)), "lowEarMinusHighEar": boot_q(s["diff"].tolist(), 2, two_sided=True)}
    for lab, m in (("BEFORE_2023", s["q"].dt.to_timestamp() < AI_LED), ("FROM_2023", s["q"].dt.to_timestamp() >= AI_LED)):
        out[lab] = boot_q(s.loc[m, "diff"].tolist(), 2, two_sided=True)
    # does the price reaction predict the NEXT surprise (market information about future earnings)
    return out


def regimes_drift(er):
    """Market-wide vs narrow earnings breadth (share of SUE>0 per quarter vs its trailing 8-quarter median) for strict126."""
    b = er.groupby("q")["sue"].apply(lambda v: float((v > 0).mean()))
    med = b.rolling(8, min_periods=4).median().shift(1)
    lab = pd.Series(np.where(b > med, "BROAD_UPGRADE", "NARROW_UPGRADE"), index=b.index).where(med.notna())
    s = spread(er, "strict126")
    s["regime"] = s["q"].map(lab)
    return {k: boot_q((g["top"] - g["bot"]).tolist(), 2) for k, g in s.dropna(subset=["regime"]).groupby("regime")}


def coverage(mk, ev):
    e = ev.copy()
    out = {"events": int(len(e)), "tickers": int(e["ticker"].nunique()), "sueDefined": int(e["sue"].notna().sum()),
           "periodEnd": [str(e["periodEnd"].min().date()), str(e["periodEnd"].max().date())],
           "filingLagDaysMedian": float((e["filingDate"] - e["periodEnd"]).dt.days.median())}
    s = e[e["sue"].notna()]
    m = s["announceEffective"].notna()
    out["announceMatchShareOfSueEvents"] = float(m.mean())
    out["announceMatchByYear"] = s.groupby(s["periodEnd"].dt.year)["announceEffective"].apply(lambda v: round(float(v.notna().mean()), 3)).to_dict()
    lag = (s.loc[m, "announceEffective"] - s.loc[m, "periodEnd"]).dt.days
    lead = (s.loc[m, "filingDate"] - s.loc[m, "announceEffective"]).dt.days
    out["announceLagDaysMedian"] = float(lag.median()) if len(lag) else None
    out["filingAfterAnnounceDaysMedian"] = float(lead.median()) if len(lead) else None
    cov = []
    for d in mk.dates[::4]:
        u = mk.universe(d)
        f = s[(s["filingDate"] < d) & (s["filingDate"] >= d - pd.Timedelta(days=FRESH_DAYS))]
        cov.append(float(u.index.isin(f["ticker"]).mean()))
    out["universeFreshSueShare"] = {"median": float(np.median(cov)), "min": float(np.min(cov)), "max": float(np.max(cov)),
                                    "fromFirstSue": float(np.median([c for c in cov if c > 0])) if any(c > 0 for c in cov) else None}
    return out


# --------------------------------------------------------------------------- books stage
def fresh_sue(ev, d):
    f = ev[(ev["sue"].notna()) & (ev["filingDate"] < d) & (ev["filingDate"] >= d - pd.Timedelta(days=FRESH_DAYS))]
    return f.sort_values("filingDate").groupby("ticker")["sue"].last()


def pick_top(scores, groups, n=5, per=2):
    out, cnt = [], defaultdict(int)
    for t in sorted(scores.index, key=lambda t: (-scores[t], t)):
        g = groups.get(t)
        if cnt[g] >= per:
            continue
        out.append(t)
        cnt[g] += 1
        if len(out) == n:
            break
    return out


def books_kr(mk, ev):
    M, A = mk.M, mk.A
    dates = mk.base["dates"]
    books = {k: {} for k in ("ETF", "S2", "SUE_TOP", "SUE_CTRL", "S2_SUE")}
    nsel = []
    for d in dates:
        g = mk.ctx2.by[d]
        ok = g[(g["_mcap"] > 0) & ~g["isPreferredShare"].astype(bool) & g["tradableAtSignal"].astype(bool) & ~g["ticker"].isin(mk.KD.C.WITHHELD if hasattr(mk.KD, "C") else [])]
        s = fresh_sue(ev, d)
        s = s[s.index.isin(ok["ticker"])]
        grp = ok.set_index("ticker")["industry"].to_dict()
        top = pick_top(s[s >= SUE_MIN], grp)
        b = {t: 0.2 for t in top}
        b[M.ETF] = 1 - 0.2 * len(top)
        books["SUE_TOP"][d] = b
        books["SUE_CTRL"][d] = A.control_book(g, b, ["_mcap"])[0] if top else {M.ETF: 1.0}
        s2 = mk.base["s2"][d]
        keep = {t: w for t, w in s2.items() if t not in (M.ETF, M.CASH) and s.get(t, -np.inf) > 0}
        b2 = dict(keep)
        b2[M.ETF] = 1 - sum(keep.values())
        books["S2_SUE"][d] = b2
        books["S2"][d] = s2
        books["ETF"][d] = {M.ETF: 1.0}
        nsel.append({"date": d, "sueTop": len(top), "s2Sue": len(keep), "freshUniverse": int(len(s))})
    return books, pd.DataFrame(nsel)


def books_us(mk, ev):
    from research.active_fund_disclosure_v1 import evaluate_us as EUS
    from research.alpha_search_round6_v1 import us as R6
    EV = mk.EV
    books = {k: {} for k in ("SUE_TOP", "SUE_CTRL", "BASE", "PC_SUE", "COCKTAIL", "U1")}
    nsel = []

    def w20(names):
        b = {t: 0.2 for t in names}
        if len(names) < 5:
            b["SPY"] = b.get("SPY", 0) + 1 - 0.2 * len(names)
        return b
    for d in mk.dates:
        x = mk.secs[d]
        s = fresh_sue(ev, d)
        s = s[s.index.isin(x.index)]
        top = pick_top(s[s >= SUE_MIN], x["sector"].to_dict())
        ctrl = EUS.matched(x, top) if top else []
        books["SUE_TOP"][d] = w20(top)
        if ctrl is not None:
            books["SUE_CTRL"][d] = w20(ctrl)
        books["BASE"][d] = w20(EV.book(x, "PRICE_CONFIRMED", "TOP5"))
        y = x.copy()
        y["PRICE_CONFIRMED"] = y["PRICE_CONFIRMED"].where(y.index.isin(s[s > 0].index))
        books["PC_SUE"][d] = w20(EV.book(y, "PRICE_CONFIRMED", "TOP5"))
        coc = R6.sleeve_book(x, R6.EQUAL)
        books["COCKTAIL"][d], books["U1"][d] = coc, R6.top5_neutral(x, coc)[0]
        nsel.append({"date": d, "sueTop": len(top), "freshUniverse": int(len(s)), "ctrlMatched": ctrl is not None})
    return books, pd.DataFrame(nsel)


def fixed_kr(mk, books, nsel):
    KD = mk.KD
    lead = KD.leadership(mk.I2, mk.ctx2, mk.base)
    out = {}
    for H in (126, 252):
        rows = []
        for d in mk.base["dates"]:
            cs = {k: KD.cohort(mk.I2, mk.ctx2, mk.base, b[d], d, H) for k, b in books.items() if d in b}
            if any(v is None or "unresolved" in v for v in cs.values()):
                continue
            months = pd.period_range(cs["ETF"]["entry"], cs["ETF"]["exit"], freq="M")
            labs = {KD.month_of(lead, pd.Timestamp(p.end_time.date())) for p in months}
            gate = mk.K6.cap_over_equal(mk.I2, mk.ctx2, mk.base["dates"], d)
            rows.append({"date": d, "semiLed": "SEMI_LED" in labs, "gateOn": gate is not None and gate > 0,
                         **{f"{k}_net": v["net"] for k, v in cs.items()},
                         **{f"{k}_twoContr": v["contr"].get("SAMSUNG_HYNIX", 0.0) - cs["ETF"]["contr"].get("SAMSUNG_HYNIX", 0.0) for k, v in cs.items()}})
        out[str(H)] = summarise_fixed(pd.DataFrame(rows), H, ("S2", "SUE_TOP", "SUE_CTRL", "S2_SUE"), "ETF",
                                      {"E_H1": ("SUE_TOP", "SUE_CTRL"), "E_H2": ("S2_SUE", "S2")},
                                      extra={"SEMI_LED_TOUCH": "semiLed", "CONCENTRATION_GATE_ON": "gateOn"}, contr="twoContr")
    return out


def fixed_us(mk, books):
    from research.alpha_search_round6_v1 import us as R6
    out = {}
    for H in (126, 252):
        rows = []
        for d in mk.dates:
            cs = {k: R6.cohort_w(mk.close, mk.qqq, b[d], d, H) for k, b in books.items() if d in b}
            if "SUE_TOP" not in cs or any(v is None or "unresolved" in v for v in cs.values()):
                continue
            row = {"date": d, "spy": cs["SUE_TOP"]["spy"], "qqq": cs["SUE_TOP"]["qqq"], **{f"{k}_net": v["net"] for k, v in cs.items()}}
            gate = R6.cap_over_equal(mk.close, mk.secs, mk.dates, d)
            row["gateOn"] = gate is not None and gate > 0
            pos = mk.close.index.get_loc(d)
            e, z = mk.close.index[pos + 1], mk.close.index[pos + 1 + H]
            for k in ("SUE_TOP", "BASE", "PC_SUE"):
                w = pd.Series(books[k][d])
                m = [t for t in w.index if t in US_MEGA]
                row[f"{k}_megaContr"] = float((w[m] * (mk.close.loc[z, m] / mk.close.loc[e, m] - 1)).sum()) if m else 0.0
            rows.append(row)
        df = pd.DataFrame(rows)
        df["ETF_net"] = df["spy"]
        out[str(H)] = summarise_fixed(df, H, ("BASE", "SUE_TOP", "SUE_CTRL", "PC_SUE", "COCKTAIL", "U1"), "ETF",
                                      {"E_H1": ("SUE_TOP", "SUE_CTRL"), "E_H2": ("PC_SUE", "BASE")},
                                      extra={"CONCENTRATION_GATE_ON": "gateOn"}, contr="megaContr", alt="qqq")
    return out


def summarise_fixed(df, H, names, etf, pairs, extra=None, contr=None, alt=None):
    block = int(round(H / 5))
    samples = {"FULL": df, "BEFORE_2023": df[df["date"] < AI_LED], "FROM_2023": df[df["date"] >= AI_LED]}
    for lab, colname in (extra or {}).items():
        samples[lab] = df[df[colname]]
        samples["NOT_" + lab] = df[~df[colname]]
    out = {}
    for nm, s in samples.items():
        if s.empty:
            continue
        c = {"cohorts": int(len(s)), "first": str(s["date"].iloc[0].date()), "last": str(s["date"].iloc[-1].date())}
        c["vsETF"] = {k: boot_q((s[f"{k}_net"] - s[f"{etf}_net"]).dropna().tolist(), block) for k in names if f"{k}_net" in s}
        if alt:
            c["vsALT"] = {k: float((s[f"{k}_net"] - s[alt]).mean()) for k in names if f"{k}_net" in s}
        c["pairs"] = {p: boot_q((s[f"{a}_net"] - s[f"{b}_net"]).dropna().tolist(), block) for p, (a, b) in pairs.items()}
        if contr:
            c["concentrationContribution"] = {k: float(s[f"{k}_{contr}"].mean()) for k in names if f"{k}_{contr}" in s}
        out[nm] = c
    # sensitivity: drop the calendar year with the largest E_H1 contribution
    yr = df.assign(y=df["date"].dt.year, v=df[f"{pairs['E_H1'][0]}_net"] - df[f"{pairs['E_H1'][1]}_net"])
    top_year = int(yr.groupby("y")["v"].sum().idxmax())
    out["sensitivityDropBestYearE_H1"] = {"year": top_year, **boot_q(yr.loc[yr["y"] != top_year, "v"].dropna().tolist(), block)}
    return out


def ledgers_kr(mk, books):
    A, M, RC = mk.A, mk.M, mk.RC
    dates, sess = mk.base["dates"], mk.sess
    etf = pd.Series(mk.ctx2.px.etf, index=sess)
    start = M.next_session(sess, dates[0])
    end = mk.close[M.ETF].last_valid_index()
    out = {}
    for every in (26, 52):
        for k, b in books.items():
            scheds = [A.books_to_schedule({d: b[d] for d in dates[i::every]}, sess) for i in range(every)]
            res = A.multi_account(mk.ctx2.px, scheds, start, end, mk.I2["rf"], etf, 1.0)
            w = RC.window(res["nav"], etf, start=start)
            r = res["nav"].pct_change().dropna()
            w.update(oneWayTurnoverPerYear=res["oneWayTurnoverPerYear"], costPerYear=res["costPerYear"],
                     sharpeNoRf=float(r.mean() / r.std() * np.sqrt(252)), volatility=float(r.std() * np.sqrt(252)))
            out[f"L{every}|{k}"] = w
            print("ledger", every, k, round(w["excess"] * 100, 2), round(w["mdd"] * 100, 1), flush=True)
    return out


def ledgers_us(mk, books):
    from research.alpha_search_round6_v1 import us as R6
    out = {}
    for every in (26, 52):
        for k, b in books.items():
            start = min(b)
            out[f"L{every}|{k}"] = R6.ledger_w(mk.close, b, every, start, mk.close.index[-1])
            v = out[f"L{every}|{k}"]
            print("ledger", every, k, round(v.get("excess", np.nan) * 100, 2), round(v.get("mdd", np.nan) * 100, 1), flush=True)
    return out


def industry_test(mk, ev):
    """E-IND: equal-weight 126-session return of top-tercile minus bottom-tercile industries by mean fresh SUE (>= 3 firms)."""
    arr, col = mk.close.values, {t: i for i, t in enumerate(mk.close.columns)}
    dates = mk.base["dates"] if mk.name == "KR" else mk.dates
    rows = []
    for d in dates:
        u = mk.universe(last_key(mk.dates, d))
        s = fresh_sue(ev, d)
        s = s[s.index.isin(u.index)]
        g = s.groupby(u.loc[s.index, "group"]).agg(["mean", "size"])
        g = g[g["size"] >= 3]
        if len(g) < 6:
            continue
        i0 = session_after(mk.sess, d, strict=True)
        if i0 is None or i0 + 126 >= len(mk.sess):
            continue
        r = g["mean"].rank(pct=True)
        def ew(groups):
            names = [col[t] for t in u.index[u["group"].isin(groups)] if t in col]
            v = arr[i0 + 126, names] / arr[i0, names] - 1
            return float(np.nanmean(v))
        etf_r = float(arr[i0 + 126, col[mk.etf]] / arr[i0, col[mk.etf]] - 1)
        top, bot = ew(r.index[r > 2 / 3]), ew(r.index[r <= 1 / 3])
        rows.append({"date": d, "diff": top - bot, "topVsEtf": top - etf_r})
    s = pd.DataFrame(rows)
    out = {"dates": int(len(s)), "topMinusBottom": boot_q(s["diff"].tolist(), 25), "topIndustriesVsEtf": boot_q(s["topVsEtf"].tolist(), 25)}
    for lab, m in (("BEFORE_2023", s["date"] < AI_LED), ("FROM_2023", s["date"] >= AI_LED)):
        out[lab] = boot_q(s.loc[m, "diff"].tolist(), 25)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=("us", "kr"), required=True)
    ap.add_argument("--private", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--stage", choices=("events", "books", "all"), default="all")
    a = ap.parse_args(argv)
    P, OUT = Path(a.private), Path(a.out)
    mk = US(P) if a.market == "us" else KR(P)
    ev = build_events(mk, P)
    ev.to_pickle(P / "ee" / f"{a.market}-events.pkl")
    res = {"studyId": "kr-us-earnings-expectations-v1", "market": mk.name, "label": "EXPLORATORY_ON_OUTCOME_EXPOSED_HISTORY"}
    if a.stage in ("events", "all"):
        res["coverage"] = coverage(mk, ev)
        print("coverage", json.dumps(res["coverage"], default=str)[:600], flush=True)
        res["E_A_persistence"], _ = persistence(ev)
        er = event_returns(mk, ev)
        er.to_pickle(P / "ee" / f"{a.market}-event-returns.pkl")
        res["E_B_drift"] = drift_tests(er, mk)
        res["E_B_breadthRegimes"] = regimes_drift(er)
        cov = res["coverage"]["announceMatchShareOfSueEvents"]
        res["E_H3_divergence"] = divergence(er) if cov >= 0.6 else {"status": "NOT_EVALUABLE", "announceMatchShare": cov}
        (OUT / f"{a.market}-events.json").write_text(json.dumps(res, indent=1, sort_keys=True, default=str) + "\n")
        print("events done", flush=True)
    if a.stage in ("books", "all"):
        books, nsel = books_kr(mk, ev) if mk.name == "KR" else books_us(mk, ev)
        b = {"selection": {"meanSueTopNames": float(nsel["sueTop"].mean()), "shareZeroSueTop": float((nsel["sueTop"] == 0).mean()),
                           "meanFreshUniverse": float(nsel["freshUniverse"].mean())}}
        b["fixed"] = fixed_kr(mk, books, nsel) if mk.name == "KR" else fixed_us(mk, books)
        (OUT / f"{a.market}-books.json").write_text(json.dumps(b, indent=1, sort_keys=True, default=str) + "\n")
        b["E_IND"] = industry_test(mk, ev)
        (OUT / f"{a.market}-books.json").write_text(json.dumps(b, indent=1, sort_keys=True, default=str) + "\n")
        b["ledgers"] = ledgers_kr(mk, books) if mk.name == "KR" else ledgers_us(mk, books)
        (OUT / f"{a.market}-books.json").write_text(json.dumps(b, indent=1, sort_keys=True, default=str) + "\n")
        print("books done", flush=True)


if __name__ == "__main__":
    main()
