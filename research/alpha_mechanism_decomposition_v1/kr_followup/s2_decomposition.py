"""Original S2 over 6 and 12 months: where its result came from, and whether it survives without the recent semiconductor lead.

    python research/alpha_mechanism_decomposition_v1/kr_followup/s2_decomposition.py --scratch <dir used by analyze.py> --stage fixed|ledgers

Reuses sg1_random_control.setup (S2 / SG1 books, OCI-corrected closes, frozen costs). SG1's threshold is unchanged.
Benchmark for every operating result: KODEX 200 (069500.KS) total return.

DEFINITIONS FIXED BEFORE ANY RESULT OF THIS FILE WAS COMPUTED
  Buckets.  SAMSUNG_HYNIX = 005930.KS + 000660.KS. OTHER_ELECTRONICS = every other name of PIT industry ELECTRONICS_ELECTRICAL
            (the industry that holds the semiconductor makers; no point-in-time semiconductor sub-classification exists in the
            inputs, so this bucket is labelled for what it is). REST = all other industries.
  Look-through of KODEX 200. A book's 069500 weight is spread over the PIT top-120 at their signal-date market-cap shares
            (the universe rows the decisions already read). KOSPI 200 has 200 names and its own cap rule; the difference between
            069500's return and this proxy over each holding window is reported as UNEXPLAINED, never assigned to a bucket.
            No later index weight is used for an earlier date.
  Leadership months. For every month-end session t: the cap-weighted PIT top-120 proxy return over the 126 sessions to t, split
            by bucket/industry (weight at t-126 x name return). SEMI_LED if that return > 0 and SAMSUNG_HYNIX supplies >= 50% of it.
            Otherwise LED_BY_<industry> if one industry (the two names counted inside ELECTRONICS_ELECTRICAL only when they are
            not SEMI_LED) supplies >= 50%. Otherwise BROAD (or DOWN when the return <= 0). Only market data enter this; no
            strategy result does.
  Samples.  FULL = every cohort. EX_SEMI_LED = cohorts whose holding window touches no SEMI_LED month. LED_BY_X = cohorts whose
            entry month is LED_BY_X (other-industry leadership episodes); the number of distinct episodes is reported.
  Controls. SIZE_CONTROL (same industry, nearest cap, same count: analyze.control_book(["_mcap"])); INDUSTRY_BASKETS
            (analyze.industry_book: each S2 pick spread over its own cap-weighted industry); RANDOM_A (#345's control: SG1's count drawn
            score-free from S2's own names, same 20% per name and same 069500 weight, sg1_random_control.random_books); KODEX 200.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections import defaultdict
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


RC = _load("kr_sg1_random_control", HERE / "sg1_random_control.py")
A, M, C = RC.A, RC.M, RC.C
TWO = ("005930.KS", "000660.KS")
EL = "ELECTRONICS_ELECTRICAL"
BUCKETS = ("SAMSUNG_HYNIX", "OTHER_ELECTRONICS", "REST")


def bucket(t, industry):
    return "SAMSUNG_HYNIX" if t in TWO else ("OTHER_ELECTRONICS" if industry == EL else "REST")


def proxy_weights(g):
    x = g[g["_mcap"].notna() & (g["_mcap"] > 0)]
    w = x.set_index("ticker")["_mcap"] / x["_mcap"].sum()
    return w, x.set_index("ticker")["industry"]


def leadership(I2, ctx2, base):
    """Month-end leadership labels from the PIT top-120 proxy (market data only)."""
    cl, sess = I2["closes"], I2["sessions"]
    dates = base["dates"]
    month_ends = sorted({sess[sess <= pd.Timestamp(p.end_time.date())][-1] for p in pd.period_range(dates[0], dates[-1], freq="M")})
    out = {}
    for t in month_ends:
        i = sess.get_loc(t)
        if i < 126:
            continue
        t0 = sess[i - 126]
        prior = [d for d in dates if d <= t0]
        if not prior:
            continue
        g = ctx2.by[prior[-1]]
        w, ind = proxy_weights(g)
        r = (cl.loc[t, w.index] / cl.loc[t0, w.index] - 1).fillna(0.0)
        contrib = w * r
        total = float(contrib.sum())
        two = float(contrib[contrib.index.isin(TWO)].sum())
        by_ind = contrib.groupby(ind.reindex(contrib.index)).sum()
        if total <= 0:
            lab = "DOWN"
        elif two >= 0.5 * total:
            lab = "SEMI_LED"
        else:
            top = by_ind.idxmax()
            lab = f"LED_BY_{top}" if by_ind.max() >= 0.5 * total else "BROAD"
        out[t] = {"label": lab, "proxyReturn126": total, "samsungHynixShare": two / total if total > 0 else None,
                  "topIndustry": str(by_ind.idxmax()), "topIndustryShare": float(by_ind.max() / total) if total > 0 else None}
    return out


def month_of(lead, day):
    keys = [k for k in lead if k <= day]
    return lead[keys[-1]]["label"] if keys else None


def cohort(I2, ctx2, base, book, d, H):
    """Net return of a book held H sessions from the next session, with bucket look-through of direct and 069500 weights."""
    cl, sess = I2["closes"], I2["sessions"]
    e = M.next_session(sess, d)
    i = sess.get_loc(e)
    if i + H >= len(sess) or sess[i + H] > cl[M.ETF].last_valid_index():
        return None
    x = sess[i + H]
    g = ctx2.by[d]
    ind = g.set_index("ticker")["industry"]
    w_px, ind_px = proxy_weights(g)
    rx = cl.loc[x] / cl.loc[e] - 1
    gross, buy, sell = 0.0, 0.0, 0.0
    expo, contr = defaultdict(float), defaultdict(float)
    for t, w in book.items():
        if t == M.CASH or w <= 0:
            continue
        r = rx.get(t, np.nan)
        if not np.isfinite(r):
            return {"unresolved": t}
        gross += w * r
        buy += w * C.cost_rate(t, "buy", e)
        sell += w * (1 + r) * C.cost_rate(t, "sell", x)
        if t == M.ETF:
            rp = rx.reindex(w_px.index).fillna(0.0)
            for tt, ww in w_px.items():
                b = bucket(tt, ind_px.get(tt))
                expo[b] += w * ww
                contr[b] += w * ww * rp[tt]
            contr["UNEXPLAINED_ETF_VS_PROXY"] += w * (r - float((w_px * rp).sum()))
        else:
            b = bucket(t, ind.get(t))
            expo[b] += w
            contr[b] += w * r
    return {"entry": e, "exit": x, "gross": gross, "net": gross - buy - sell, "cost": buy + sell, "expo": dict(expo), "contr": dict(contr)}


def block_ci(v, block):
    return RC.block_ci(v, block)


def stage_fixed(I2, ctx2, base, paths):
    lead = leadership(I2, ctx2, base)
    dates = base["dates"]
    books = {"S2": base["s2"], "SG1": base["sg1"], "ETF": {d: {M.ETF: 1.0} for d in dates}}
    books["SIZE_CONTROL"] = {d: A.control_book(ctx2.by[d], base["s2"][d], ["_mcap"])[0] for d in dates}
    books["INDUSTRY_BASKETS"] = {d: A.industry_book(ctx2.by[d], base["s2"][d]) for d in dates}
    rnd = [RC.random_books(base, "POOL_S2_PICKS", p) for p in range(paths)]
    out = {"leadership": {str(k.date()): v for k, v in lead.items()}, "fixed": {}}
    ep = defaultdict(int)
    prev = None
    for k, v in sorted(lead.items()):
        if v["label"] != prev and v["label"] not in ("BROAD", "DOWN"):
            ep[v["label"]] += 1
        prev = v["label"]
    out["leadershipEpisodes"] = dict(ep)
    out["leadershipMonths"] = dict(pd.Series([v["label"] for v in lead.values()]).value_counts())
    for H in (126, 252):
        rows = []
        for d in dates:
            cs = {k: cohort(I2, ctx2, base, b[d], d, H) for k, b in books.items()}
            if any(v is None for v in cs.values()):
                continue
            if any("unresolved" in v for v in cs.values()):
                rows.append({"date": d, "unresolved": {k: v["unresolved"] for k, v in cs.items() if "unresolved" in v}})
                continue
            rv = [cohort(I2, ctx2, base, r[d], d, H) for r in rnd]
            rv = [x["net"] for x in rv if x and "unresolved" not in x]
            months = pd.period_range(cs["S2"]["entry"], cs["S2"]["exit"], freq="M")
            labs = {month_of(lead, pd.Timestamp(p.end_time.date())) for p in months}
            rows.append({"date": d, "entry": cs["S2"]["entry"], "exit": cs["S2"]["exit"], "entryLabel": month_of(lead, cs["S2"]["entry"]),
                         "touchesSemiLed": "SEMI_LED" in labs, **{f"{k}_net": v["net"] for k, v in cs.items()},
                         **{f"{k}_gross": v["gross"] for k, v in cs.items()}, **{f"{k}_cost": v["cost"] for k, v in cs.items()},
                         "RANDOM_A_net": float(np.mean(rv)) if rv else np.nan,
                         **{f"S2_expo_{b}": cs["S2"]["expo"].get(b, 0.0) for b in BUCKETS}, **{f"ETF_expo_{b}": cs["ETF"]["expo"].get(b, 0.0) for b in BUCKETS},
                         **{f"S2_contr_{b}": cs["S2"]["contr"].get(b, 0.0) for b in BUCKETS + ("UNEXPLAINED_ETF_VS_PROXY",)},
                         **{f"ETF_contr_{b}": cs["ETF"]["contr"].get(b, 0.0) for b in BUCKETS + ("UNEXPLAINED_ETF_VS_PROXY",)}})
        df = pd.DataFrame([r for r in rows if "unresolved" not in r])
        unres = [{"date": str(r["date"].date()), **r["unresolved"]} for r in rows if "unresolved" in r]
        block = int(round(H / 5))
        samples = {"FULL": df, "EX_SEMI_LED": df[~df["touchesSemiLed"]], "FROM_2022": df[df["date"] >= pd.Timestamp("2022-01-01")],
                   "TO_2021": df[df["date"] < pd.Timestamp("2022-01-01")]}
        for lab in sorted(set(df["entryLabel"].dropna())):
            if lab.startswith("LED_BY_") or lab == "SEMI_LED":
                samples[f"ENTRY_{lab}"] = df[df["entryLabel"] == lab]
        cell = {"unresolvedCohorts": unres, "blockWeeks": block}
        for name, s in samples.items():
            if s.empty:
                continue
            e = s["ETF_net"]
            row = {"cohorts": int(len(s)), "first": str(s["date"].iloc[0].date()), "last": str(s["date"].iloc[-1].date()),
                   "independentBlocks": round(len(s) / block, 1)}
            for k in ("S2", "SG1", "RANDOM_A", "SIZE_CONTROL", "INDUSTRY_BASKETS"):
                x = s[f"{k}_net"] - e
                row[k] = {"meanNetExcess": float(x.mean()), "ci": block_ci(x.dropna().tolist(), block), "winRate": float((x > 0).mean())}
            row["ETF_meanNet"] = float(e.mean())
            row["selectionVsSizeControl"] = {"mean": float((s["S2_net"] - s["SIZE_CONTROL_net"]).mean()),
                                             "ci": block_ci((s["S2_net"] - s["SIZE_CONTROL_net"]).tolist(), block)}
            row["industryAllocation"] = {"mean": float((s["INDUSTRY_BASKETS_net"] - e).mean()),
                                         "ci": block_ci((s["INDUSTRY_BASKETS_net"] - e).tolist(), block)}
            row["selectionVsIndustryBaskets"] = {"mean": float((s["S2_net"] - s["INDUSTRY_BASKETS_net"]).mean()),
                                                 "ci": block_ci((s["S2_net"] - s["INDUSTRY_BASKETS_net"]).tolist(), block)}
            row["S2_costMean"] = float(s["S2_cost"].mean())
            row["exposure"] = {b: {"S2": float(s[f"S2_expo_{b}"].mean()), "ETF": float(s[f"ETF_expo_{b}"].mean())} for b in BUCKETS}
            row["contribution"] = {b: {"S2": float(s[f"S2_contr_{b}"].mean()), "ETF": float(s[f"ETF_contr_{b}"].mean()),
                                       "difference": float((s[f"S2_contr_{b}"] - s[f"ETF_contr_{b}"]).mean())}
                                   for b in BUCKETS + ("UNEXPLAINED_ETF_VS_PROXY",)}
            cell[name] = row
        out["fixed"][str(H)] = cell
        print(H, {n: round(c["S2"]["meanNetExcess"], 4) for n, c in cell.items() if isinstance(c, dict) and "S2" in c}, flush=True)
    return out


def ledgers(I2, ctx2, base, paths):
    """Staggered 6/12-month books evaluated from 2022-01-03: INHERITED (#345, decisions from 2020-12) vs FRESH (decisions from 2022)."""
    dates = base["dates"]
    sess = I2["sessions"]
    etf = pd.Series(ctx2.px.etf, index=sess)
    out = {}
    fresh_first = M.next_session(sess, [d for d in dates if d >= RC.TEST_START][0])
    eval_start = M.next_session(sess, fresh_first)          # both modes are read from the same session, after the fresh book's first fill
    out["evaluationStart"] = str(eval_start.date())
    for every in (26, 52):
        for mode, start_dec in (("INHERITED", RC.WARMUP_START), ("FRESH", RC.TEST_START)):
            use = [d for d in dates if d >= start_dec]
            for name, books in [("S2", base["s2"]), ("SG1", base["sg1"]), ("ETF", {d: {M.ETF: 1.0} for d in dates})] + \
                               [(f"RANDOM_A_{p}", RC.random_books(base, "POOL_S2_PICKS", p)) for p in range(paths)]:
                scheds = [A.books_to_schedule({d: books[d] for d in use[k::every]}, sess) for k in range(every)]
                start = M.next_session(sess, use[0])
                end = I2["closes"][M.ETF].last_valid_index()
                res = A.multi_account(ctx2.px, scheds, start, end, I2["rf"], etf, 1.0)
                w = RC.window(res["nav"], etf, start=eval_start)
                w.update(oneWayTurnoverPerYear=res["oneWayTurnoverPerYear"], costPerYear=res["costPerYear"])
                firsts = sorted(min(s) for s in scheds if s)
                w["fillUp"] = {"firstEntry": str(firsts[0].date()), "allAccountsInvestedBy": str(firsts[-1].date())} if mode == "FRESH" else None
                nav = res["nav"].loc[eval_start:]
                b = etf.loc[nav.index]
                yearly = {}
                for y, gidx in nav.groupby(nav.index.year).groups.items():
                    a0 = nav.loc[:gidx[0]].iloc[-2] if len(nav.loc[:gidx[0]]) > 1 else nav.iloc[0]
                    b0 = b.loc[:gidx[0]].iloc[-2] if len(b.loc[:gidx[0]]) > 1 else b.iloc[0]
                    yearly[int(y)] = {"book": float(nav.loc[gidx[-1]] / a0 - 1), "etf": float(b.loc[gidx[-1]] / b0 - 1)}
                w["calendarYears"] = yearly
                out[f"L{every}|{mode}|{name}"] = w
            rk = [out[f"L{every}|{mode}|RANDOM_A_{p}"]["excess"] for p in range(paths)]
            out[f"L{every}|{mode}|RANDOM_A_summary"] = {"paths": paths, "meanExcess": float(np.mean(rk)), "sdExcess": float(np.std(rk, ddof=1)) if paths > 1 else None}
            print(every, mode, {k.split("|")[2]: round(v["excess"], 4) for k, v in out.items() if k.startswith(f"L{every}|{mode}|") and "RANDOM_A_" not in k}, flush=True)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--scratch", required=True)
    ap.add_argument("--stage", choices=("fixed", "ledgers"), required=True)
    ap.add_argument("--paths", type=int, default=50)
    a = ap.parse_args(argv)
    I2, ctx2, base = RC.setup(a.scratch)
    res = stage_fixed(I2, ctx2, base, a.paths) if a.stage == "fixed" else ledgers(I2, ctx2, base, a.paths)
    res["paths"] = a.paths
    (HERE / f"s2-decomposition-{a.stage}.json").write_text(json.dumps(res, indent=1, ensure_ascii=False, default=str) + "\n")


if __name__ == "__main__":
    main()
