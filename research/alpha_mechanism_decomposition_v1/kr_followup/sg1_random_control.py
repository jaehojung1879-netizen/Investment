"""Did SG1 improve S2 by CHOOSING well, or by holding fewer stocks? A score-free random control, then 6/12-month holding.

    python research/alpha_mechanism_decomposition_v1/kr_followup/sg1_random_control.py --scratch <dir used by analyze.py> --stage l4|fixed|staggered

SG1 is unchanged: threshold T = 0.8958333333333333 read from s2-control-and-gate.json (fixed on 2018-2021 signals); a pick of the
S2 book is held at 20% when its within-industry value percentile is >= T, other slots in 069500, no pick -> 069500 100%.

RANDOM CONTROL (score-free). On every weekly signal date d, k = the number of names SG1 holds on d. The control draws k names
uniformly WITHOUT using the score from a candidate pool and holds them at the same 20% each, the rest in 069500 (k = 0 -> 069500 100%
for both). Same dates, execution (next session close), per-name weight, ETF weight, costs and OCI-corrected closes.
  POOL_S2_PICKS     (primary) the names of the S2 book on d — SG1 is a filter on exactly these
  POOL_S2_ELIGIBLE  (sensitivity) every name S2 could have ranked on d (quality-eligible, confirmed, scored, not withheld)
Draws are reproducible: numpy default_rng([20261115, pool, path, date ordinal]) over the pool sorted by ticker, so a path is the same
whatever order dates are processed in. Random books are drawn for every date from WARMUP_START so staggered accounts are invested at
the evaluation start; metrics are read from TEST_START (2022-01-03) only.

LEDGERS (frozen engine analyze.multi_account: equal capital per account, each trades only on its own dates, NAVs summed):
  L4    four accounts, account k trades on weekly dates k, k+4, ...   (the existing 4-week book, for comparison)
  L26   26 accounts, every 26 weeks  (each account holds ~6 months; buy dates staggered weekly)
  L52   52 accounts, every 52 weeks  (~12 months)
FIXED  each weekly cohort held exactly 126 / 252 sessions from its execution close, entry and exit costs at the frozen dated rates,
       compared with 069500 bought and sold on the same sessions; moving-block bootstrap over cohorts, block H/5 weeks.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
sys.path.insert(0, str(STUDY.parents[1]))


def _load(name, path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


OC = _load("kr_oci_corrected_nav", HERE / "oci_corrected_nav.py")
A, REC = OC.A, OC.REC
M, C = A.M, A.C
SCORE = "B08_valueBusinessConfirmation"
TEST_START = pd.Timestamp("2022-01-01")
WARMUP_START = pd.Timestamp("2020-12-01")       # 52 weeks + a margin before the test start
POOLS = ("POOL_S2_PICKS", "POOL_S2_ELIGIBLE")


def threshold():
    return float(json.loads((HERE / "s2-control-and-gate.json").read_text())["sg1Training"]["threshold"])


def stocks(b):
    return sorted(t for t, w in b.items() if t not in (M.ETF, M.CASH) and w > 1e-12)


def book_of(names):
    return {**{t: 0.2 for t in names}, M.ETF: 1.0 - 0.2 * len(names)} if names else {M.ETF: 1.0}


def setup(scratch):
    cache = Path(scratch) / "sg1-random-setup.pkl"
    rec = json.loads((HERE / "010060-corporate-action-reconciliation.json").read_text())
    I = A.load(scratch)
    ctx = A.Ctx(I)
    fixed, _ = OC.corrected_closes(I["closes"], rec)
    I2 = dict(I, closes=fixed)
    ctx2 = A.Ctx(I2)
    if cache.exists():
        base = pickle.loads(cache.read_bytes())
    else:
        phases = {p: A.run_phase(I, p) for p in range(4)}
        dates = sorted({d for p in phases for d in phases[p]["weights"][A.SMS]})
        T = threshold()
        base = {"dates": dates, "s2": {}, "sg1": {}, "eligible": {}, "T": T}
        for d in dates:
            g = ctx.by[d]
            s2 = REC.decide(g)["B1_S2_ORIGINAL"]["weights"]
            gi = g.set_index("ticker")
            picks = stocks(s2)
            base["s2"][d] = s2
            base["sg1"][d] = book_of([t for t in picks if float(gi.at[t, SCORE]) >= T])
            score = g[SCORE].where(g["b08Confirmed"] == 1)
            ok = g["_q"].astype(bool) & score.notna() & ~g["ticker"].isin(C.WITHHELD)
            base["eligible"][d] = sorted(g.loc[ok, "ticker"])
        cache.write_bytes(pickle.dumps(base))
    return I2, ctx2, base


def random_books(base, pool, path):
    out = {}
    pid = POOLS.index(pool)
    for d in base["dates"]:
        if d < WARMUP_START:
            out[d] = base["sg1"][d]
            continue
        k = len(stocks(base["sg1"][d]))
        cand = stocks(base["s2"][d]) if pool == "POOL_S2_PICKS" else base["eligible"][d]
        rng = np.random.default_rng([20261115, pid, path, int(d.toordinal())])
        names = sorted(rng.choice(cand, size=k, replace=False).tolist()) if k else []
        out[d] = book_of(names)
    return out


def schedules(books, dates, sess, every):
    use = [d for d in dates if d >= WARMUP_START]
    return [A.books_to_schedule({d: books[d] for d in use[k::every]}, sess) for k in range(every)]


def ledger(I2, ctx2, books, dates, every, cost_mult=1.0):
    sess = I2["sessions"]
    scheds = schedules(books, dates, sess, every)
    start = A.M.next_session(sess, [d for d in dates if d >= WARMUP_START][0])
    end = I2["closes"][M.ETF].last_valid_index()
    bench = pd.Series(ctx2.px.etf, index=sess)
    return A.multi_account(ctx2.px, scheds, start, end, I2["rf"], bench, cost_mult)


def window(nav, etf, turnover=None, cost=None):
    n, b = nav.loc[TEST_START:], etf.loc[TEST_START:]
    n, b = n / n.iloc[0], b / b.iloc[0]
    yrs = (len(n) - 1) / 252
    r, rb = n.pct_change().dropna(), b.pct_change().dropna()
    act = r - rb.reindex(r.index)
    out = {"start": str(n.index[0].date()), "end": str(n.index[-1].date()), "cagr": float(n.iloc[-1] ** (1 / yrs) - 1),
           "etfCagr": float(b.iloc[-1] ** (1 / yrs) - 1), "excess": float(n.iloc[-1] ** (1 / yrs) - b.iloc[-1] ** (1 / yrs)),
           "mdd": float((n / n.cummax() - 1).min()), "etfMdd": float((b / b.cummax() - 1).min()),
           "trackingError": float(act.std() * np.sqrt(252)), "infoRatio": float(act.mean() * 252 / (act.std() * np.sqrt(252))) if act.std() > 0 else None}
    return out


def ledger_metrics(I2, ctx2, books, dates, every):
    net = ledger(I2, ctx2, books, dates, every, 1.0)
    gross = ledger(I2, ctx2, books, dates, every, 0.0)
    etf = pd.Series(ctx2.px.etf, index=I2["sessions"])
    w = window(net["nav"], etf)
    wg = window(gross["nav"], etf)
    w.update(grossCagr=wg["cagr"], grossExcess=wg["excess"], oneWayTurnoverPerYear=net["oneWayTurnoverPerYear"], costPerYear=net["costPerYear"])
    return w, net["nav"]


def summarise_paths(vals, sg1_val):
    v = np.array(vals, float)
    return {"paths": int(len(v)), "mean": float(v.mean()), "sd": float(v.std(ddof=1)), "p05": float(np.percentile(v, 5)),
            "p95": float(np.percentile(v, 95)), "min": float(v.min()), "max": float(v.max()),
            "sg1": sg1_val, "shareOfPathsBelowSG1": float((v < sg1_val).mean()),
            "permutationP": float(((v >= sg1_val).sum() + 1) / (len(v) + 1))}


def stage_ledger(I2, ctx2, base, every, paths):
    dates = base["dates"]
    res = {}
    for name, books in (("ETF", {d: {M.ETF: 1.0} for d in dates}), ("S2", base["s2"]), ("SG1", base["sg1"])):
        res[name], _ = ledger_metrics(I2, ctx2, books, dates, every)
        print(every, name, round(res[name]["cagr"], 4), flush=True)
    for pool in POOLS:
        rows = []
        for p in range(paths):
            m, _ = ledger_metrics(I2, ctx2, random_books(base, pool, p), dates, every)
            rows.append(m)
            if p % 10 == 0:
                print(every, pool, p, round(m["cagr"], 4), flush=True)
        res[pool] = {k: summarise_paths([r[k] for r in rows], res["SG1"][k]) for k in
                     ("cagr", "grossCagr", "excess", "grossExcess", "mdd", "trackingError", "infoRatio", "oneWayTurnoverPerYear", "costPerYear")}
    names = [len(stocks(base["sg1"][d])) for d in dates if d >= TEST_START]
    res["sg1NamesDistributionTest"] = {str(k): int(v) for k, v in sorted(pd.Series(names).value_counts().items())}
    res["s2NamesDistributionTest"] = {str(k): int(v) for k, v in sorted(pd.Series([len(stocks(base["s2"][d])) for d in dates if d >= TEST_START]).value_counts().items())}
    return res


def cohort_returns(I2, base, books, H):
    """{signal date: (net book return, net 069500 return, unresolved)} for cohorts entering on/after TEST_START."""
    cl = I2["closes"]
    sess = I2["sessions"]
    out = {}
    for d in base["dates"]:
        if d < TEST_START:
            continue
        e = M.next_session(sess, d)
        i = sess.get_loc(e)
        if i + H >= len(sess) or sess[i + H] > cl[M.ETF].last_valid_index():
            continue
        x = sess[i + H]
        b = books[d]
        gross, buy, sell, bad = 0.0, 0.0, 0.0, False
        for t, w in b.items():
            pe, px_ = cl.at[e, t], cl.at[x, t]
            if not (np.isfinite(pe) and np.isfinite(px_)) or pe <= 0:
                bad = True
                break
            r = px_ / pe - 1
            gross += w * r
            buy += w * C.cost_rate(t, "buy", e)
            sell += w * (1 + r) * C.cost_rate(t, "sell", x)
        re_ = cl.at[x, M.ETF] / cl.at[e, M.ETF] - 1
        etf_net = re_ - C.cost_rate(M.ETF, "buy", e) - (1 + re_) * C.cost_rate(M.ETF, "sell", x)
        out[d] = (None if bad else gross - buy - sell, etf_net, bad, None if bad else gross)
    return out


def block_ci(v, block, draws=2000, seed=20261115):
    v = np.asarray(v, float)
    n = len(v)
    if n < 2 * block:
        return None
    rng = np.random.default_rng(seed)
    means = []
    for _ in range(draws):
        idx = []
        while len(idx) < n:
            s = rng.integers(0, n - block + 1)
            idx.extend(range(s, s + block))
        means.append(v[idx[:n]].mean())
    return [float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))]


def stage_fixed(I2, base, paths):
    res = {}
    for H in (126, 252):
        block = int(round(H / 5))
        own = {k: cohort_returns(I2, base, b, H) for k, b in (("S2", base["s2"]), ("SG1", base["sg1"]))}
        dates = sorted(d for d in own["SG1"] if not own["SG1"][d][2] and not own["S2"][d][2])
        unresolved = sorted(str(d.date()) for d in own["SG1"] if own["SG1"][d][2] or own["S2"][d][2])
        cell = {"cohorts": len(dates), "first": str(dates[0].date()) if dates else None, "last": str(dates[-1].date()) if dates else None,
                "blockWeeks": block, "independentBlocks": round(len(dates) / block, 1), "unresolvedCohorts": unresolved}
        etf = np.array([own["SG1"][d][1] for d in dates])
        for k in ("S2", "SG1"):
            v = np.array([own[k][d][0] for d in dates])
            g = np.array([own[k][d][3] for d in dates])
            cell[k] = {"meanNet": float(v.mean()), "meanGross": float(g.mean()), "meanNetExcessEtf": float((v - etf).mean()),
                       "ci": block_ci(v - etf, block), "winRate": float((v > etf).mean())}
        cell["ETF"] = {"meanNet": float(etf.mean())}
        sg1x = np.array([own["SG1"][d][0] for d in dates]) - etf
        for pool in POOLS:
            means, diffs = [], []
            for p in range(paths):
                rb = cohort_returns(I2, base, random_books(base, pool, p), H)
                v = np.array([rb[d][0] if (d in rb and not rb[d][2]) else np.nan for d in dates])
                means.append(float(np.nanmean(v - etf)))
                diffs.append(sg1x - (v - etf))
            dm = np.nanmean(np.vstack(diffs), axis=0)       # SG1 minus the path-average control, per cohort
            cell[pool] = {**summarise_paths(means, float(sg1x.mean())), "sg1MinusControlMeanPerCohort": float(np.nanmean(dm)),
                          "ci": block_ci(dm[np.isfinite(dm)], block)}
        res[str(H)] = cell
        print(H, {k: round(cell[k]["meanNetExcessEtf"], 4) for k in ("S2", "SG1")}, flush=True)
    return res


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--scratch", required=True)
    ap.add_argument("--stage", choices=("l4", "fixed", "staggered"), required=True)
    ap.add_argument("--paths", type=int, default=100)
    a = ap.parse_args(argv)
    I2, ctx2, base = setup(a.scratch)
    target = HERE / f"sg1-random-control-{a.stage}.json"      # one file per stage, so stages can run side by side
    out = {
        "label": "CONDITIONAL_EXPOSED_HISTORY_OCI_CORRECTED", "threshold": base["T"], "testStart": str(TEST_START.date()),
        "pools": {"POOL_S2_PICKS": "the S2 book's own names (primary)", "POOL_S2_ELIGIBLE": "every name S2 could rank (sensitivity)"}}
    if a.stage == "l4":
        out["L4"] = stage_ledger(I2, ctx2, base, 4, a.paths)
    elif a.stage == "fixed":
        out["FIXED"] = stage_fixed(I2, base, a.paths)
    else:
        out["L26"] = stage_ledger(I2, ctx2, base, 26, a.paths)
        out["L52"] = stage_ledger(I2, ctx2, base, 52, a.paths)
    out["paths"] = a.paths
    target.write_text(json.dumps(out, indent=1, ensure_ascii=False, default=str) + "\n")


if __name__ == "__main__":
    main()
