"""S2's stock-selection effect linked to its run result, and one pre-registered score gate (train front / test back).

    python research/alpha_mechanism_decomposition_v1/kr_followup/s2_control_and_gate.py --scratch <dir used by analyze.py>

BOOKS (same decision dates, execution at the next session close, frozen costs, OCI-corrected closes, four accounts summed):
  S2                 recorder.decide B1_S2_ORIGINAL (0 names -> 069500, at most 5 x 20%, empty slots 069500)
  SIZE_CONTROL       every S2 pick replaced by the unpicked, quality-eligible name of the SAME industry nearest in within-date
                     market-cap percentile (mechanism.matched_controls(["_mcap"]), each control used once per date): same industries,
                     same count, same weights. A pick with no candidate keeps its slot in 069500 and is counted.
  MATCHED_3VAR       the existing control of the H2 study (cap, 60-day liquidity, 12-1 momentum), reported beside it
  INDUSTRY_BASKETS   every S2 pick spread over its own PIT cap-weighted industry basket (analyze.industry_book)
  ZG1                the earlier trailing-252 gate (zero_gate.gate_books), unchanged
  SG1                the pre-registered score gate below
  ETF                069500 total return
Decomposition (CAGR differences of these paths, and paired daily block bootstraps):
  (1) industry allocation  INDUSTRY_BASKETS - ETF
  (2) within-industry selection  S2 - INDUSTRY_BASKETS, and S2 - SIZE_CONTROL (same industry, similar size, same count)
  (3) net result  S2 - ETF

SG1 — written before any test-period number was computed. Signal: an S2 pick's own score, the within-industry value percentile
(B08_valueBusinessConfirmation) it was ranked on, known at the signal close. Two steps, both fixed in advance:
  TRAIN (signal dates 2018-01-01 .. 2021-12-31): for every S2 pick, the 21-session net-of-nothing return from its execution close
    minus its own cap-weighted industry basket over the same sessions. Evidence is read ONLY from this window: the mean of the
    top score tercile of picks minus the bottom tercile, with a pick-level bootstrap interval clustered by signal date.
    T = the 2/3 quantile of training-period pick scores (the tercile boundary, a distribution statistic, not an optimised value).
  RULE: if the training top-minus-bottom difference is > 0, SG1 holds only picks with score >= T (20% each, other slots 069500;
    no pick passing -> 0 names, 069500). If it is <= 0 the rule has no front-period support and is reported UNSUPPORTED_IN_TRAINING
    (still evaluated, labelled).
  TEST (signal dates 2022-01-01 ..): metrics on the four-account NAV restricted to the test window. No second threshold, window or
    signal is tried. If the paired SG1 - S2 interval contains 0, the verdict is "판단 유보", not a win.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
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
ZG = _load("kr_zero_gate", HERE / "zero_gate.py")
A, REC = OC.A, OC.REC
M, C = A.M, A.C
TRAIN = ("2018-01-01", "2021-12-31")
TEST_START = "2022-01-01"
FWD = 21
SCORE = "B08_valueBusinessConfirmation"


def stock_names(book):
    return [t for t, w in book.items() if t not in (M.ETF, M.CASH) and w > 1e-12]


def s2_books(ctx, phases):
    return {p: {d: REC.decide(ctx.by[d])["B1_S2_ORIGINAL"]["weights"] for d in phases[p]["weights"][A.SMS]} for p in phases}


def derived(ctx, s2, fn):
    out, unmatched = {}, 0
    for p, sched in s2.items():
        out[p] = {}
        for d, b in sched.items():
            r = fn(ctx.by[d], b)
            if isinstance(r, tuple):
                r, u = r
                unmatched += u
            out[p][d] = r
    return out, unmatched


def pick_forward(ctx, closes, sess, s2):
    """Training/test evidence rows: pick score and its 21-session return minus its own industry basket (execution close to +21)."""
    rows = []
    for p, sched in s2.items():
        for d, b in sched.items():
            e = M.next_session(sess, d)
            if e is None:
                continue
            i = sess.get_loc(e)
            if i + FWD >= len(sess):
                continue
            x = sess[i + FWD]
            g = ctx.by[d]
            for t in stock_names(b):
                row = g[g["ticker"] == t]
                if row.empty:
                    continue
                ind = row["industry"].iloc[0]
                bw = {k: v for k, v in M.industry_basket(g, ind).items() if k not in C.WITHHELD} or {t: 1.0}
                rr = closes.loc[x, list(bw)] / closes.loc[e, list(bw)] - 1
                ok = rr.notna()
                if not ok.any() or pd.isna(closes.at[x, t]) or pd.isna(closes.at[e, t]):
                    continue
                wsum = sum(bw[k] for k in rr.index[ok])
                basket = float(sum(bw[k] * rr[k] for k in rr.index[ok]) / wsum)
                rows.append({"phase": p, "signal": d, "ticker": t, "score": float(row[SCORE].iloc[0]),
                             "excessVsIndustry": float(closes.at[x, t] / closes.at[e, t] - 1 - basket)})
    return pd.DataFrame(rows)


def cluster_boot(df, col, groups, draws=2000, seed=20261115):
    rng = np.random.default_rng(seed)
    keys = df[groups].unique()
    by = {k: g for k, g in df.groupby(groups)}
    vals = []
    for _ in range(draws):
        pick = rng.choice(keys, len(keys), replace=True)
        s = pd.concat([by[k] for k in pick])
        vals.append(s[col].mean())
    return [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))]


def window_metrics(nav, etf, start):
    n, b = nav.loc[start:], etf.loc[start:]
    n, b = n / n.iloc[0], b / b.iloc[0]
    yrs = (len(n) - 1) / 252
    r, rb = n.pct_change().dropna(), b.pct_change().dropna()
    act = r - rb.reindex(r.index)
    return {"start": str(n.index[0].date()), "end": str(n.index[-1].date()), "cagr": float(n.iloc[-1] ** (1 / yrs) - 1),
            "etfCagr": float(b.iloc[-1] ** (1 / yrs) - 1), "excessCagr": float(n.iloc[-1] ** (1 / yrs) - b.iloc[-1] ** (1 / yrs)),
            "mdd": float((n / n.cummax() - 1).min()), "etfMdd": float((b / b.cummax() - 1).min()), "vol": float(r.std() * np.sqrt(252)),
            "trackingError": float(act.std() * np.sqrt(252)), "infoRatio": float(act.mean() * 252 / (act.std() * np.sqrt(252))) if act.std() > 0 else None}


def names_distribution(books, start=None):
    counts = [len(stock_names(b)) for sched in books.values() for d, b in sched.items() if start is None or str(d.date()) >= start]
    return {str(k): int(v) for k, v in sorted(pd.Series(counts).value_counts().items())}, float(np.mean(counts))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--scratch", required=True)
    a = ap.parse_args(argv)
    rec = json.loads((HERE / "010060-corporate-action-reconciliation.json").read_text())
    I = A.load(a.scratch)
    ctx = A.Ctx(I)
    phases = {p: A.run_phase(I, p) for p in range(4)}
    fixed, _ = OC.corrected_closes(I["closes"], rec)
    I2 = dict(I, closes=fixed)
    ctx2 = A.Ctx(I2)
    sess = I["sessions"]
    s2 = s2_books(ctx, phases)
    size_ctrl, um_size = derived(ctx, s2, lambda g, b: A.control_book(g, b, ["_mcap"]))
    ctrl3, um_3 = derived(ctx, s2, lambda g, b: A.control_book(g, b, ["_mcap", "E02_logAdv60", "A07_momentum12_1"]))
    ind, _ = derived(ctx, s2, A.industry_book)
    etf = {p: {d: {M.ETF: 1.0} for d in sched} for p, sched in s2.items()}
    zg1, _ = ZG.gate_books(I, ctx, phases)
    # ---- SG1: training evidence and threshold (training window only) ------------------------------------------------- #
    ev = pick_forward(ctx, fixed, sess, s2)
    ev["sig"] = ev["signal"].dt.strftime("%Y-%m-%d")
    tr = ev[(ev["sig"] >= TRAIN[0]) & (ev["sig"] <= TRAIN[1])].copy()
    lo_q, hi_q = tr["score"].quantile([1 / 3, 2 / 3])
    T = float(hi_q)
    top, bot = tr[tr["score"] >= hi_q], tr[tr["score"] <= lo_q]
    diff = float(top["excessVsIndustry"].mean() - bot["excessVsIndustry"].mean())
    tb = pd.concat([top.assign(_g=1), bot.assign(_g=0)])
    boots = []
    rng = np.random.default_rng(20261115)
    keys = tb["sig"].unique()
    by = {k: g for k, g in tb.groupby("sig")}
    for _ in range(2000):
        s = pd.concat([by[k] for k in rng.choice(keys, len(keys), replace=True)])
        boots.append(s.loc[s._g == 1, "excessVsIndustry"].mean() - s.loc[s._g == 0, "excessVsIndustry"].mean())
    supported = diff > 0
    training = {"window": TRAIN, "picks": int(len(tr)), "signalDates": int(tr["sig"].nunique()), "threshold": T,
                "topTercileMean": float(top["excessVsIndustry"].mean()), "bottomTercileMean": float(bot["excessVsIndustry"].mean()),
                "topMinusBottom": diff, "ci95": [float(np.nanpercentile(boots, 2.5)), float(np.nanpercentile(boots, 97.5))],
                "spearman": float(tr["score"].corr(tr["excessVsIndustry"], method="spearman")),
                "status": "SUPPORTED_POINT_ESTIMATE_IN_TRAINING" if supported else "UNSUPPORTED_IN_TRAINING"}
    te = ev[ev["sig"] >= TEST_START]
    test_ev = {"picks": int(len(te)), "aboveT": int((te["score"] >= T).sum()),
               "meanExcessAboveT": float(te.loc[te["score"] >= T, "excessVsIndustry"].mean()) if (te["score"] >= T).any() else None,
               "meanExcessBelowT": float(te.loc[te["score"] < T, "excessVsIndustry"].mean()) if (te["score"] < T).any() else None}
    sg1 = {}
    for p, sched in s2.items():
        sg1[p] = {}
        for d, b in sched.items():
            g = ctx.by[d].set_index("ticker")
            keep = [t for t in stock_names(b) if float(g.at[t, SCORE]) >= T]
            sg1[p][d] = {**{t: 0.2 for t in keep}, M.ETF: 1.0 - 0.2 * len(keep)} if keep else {M.ETF: 1.0}
    books = {"S2": s2, "SIZE_CONTROL": size_ctrl, "MATCHED_3VAR": ctrl3, "INDUSTRY_BASKETS": ind, "ZG1": zg1, "SG1": sg1, "ETF": etf}
    res = {k: A.four_account(I2, ctx2, phases, b) for k, b in books.items()}
    etf_nav = res["ETF"]["nav"]
    out = {"label": "CONDITIONAL_EXPOSED_HISTORY_OCI_CORRECTED", "books": {}, "paired": {}, "decomposition": {}, "sg1Training": training,
           "sg1TestEvidence": test_ev, "unmatchedPicks": {"SIZE_CONTROL": um_size, "MATCHED_3VAR": um_3}}
    for k, r in res.items():
        dist, mean_n = names_distribution(books[k])
        dist_t, mean_t = names_distribution(books[k], TEST_START)
        out["books"][k] = {"full": {**window_metrics(r["nav"], etf_nav, r["nav"].index[0]),
                                    "oneWayTurnoverPerYear": r["oneWayTurnoverPerYear"], "costPerYear": r["costPerYear"]},
                           "test": window_metrics(r["nav"], etf_nav, pd.Timestamp(TEST_START)),
                           "stockNamesDistribution": dist, "meanStockNames": mean_n,
                           "stockNamesDistributionTest": dist_t, "meanStockNamesTest": mean_t}
    daily = {k: r["nav"].pct_change().dropna() for k, r in res.items()}
    for a_, b_ in (("S2", "ETF"), ("INDUSTRY_BASKETS", "ETF"), ("S2", "INDUSTRY_BASKETS"), ("S2", "SIZE_CONTROL"), ("S2", "MATCHED_3VAR"),
                   ("SIZE_CONTROL", "INDUSTRY_BASKETS"), ("SG1", "S2"), ("SG1", "ETF"), ("ZG1", "S2"), ("ZG1", "ETF")):
        d_ = daily[a_] - daily[b_].reindex(daily[a_].index)
        out["paired"][f"{a_}-{b_}"] = {"full": C.block_bootstrap(d_.dropna()), "test": C.block_bootstrap(d_.loc[TEST_START:].dropna())}
    f = {k: v["full"]["cagr"] for k, v in out["books"].items()}
    out["decomposition"] = {"(1)industryAllocation=INDUSTRY_BASKETS-ETF": f["INDUSTRY_BASKETS"] - f["ETF"],
                            "(2a)selectionVsIndustryBaskets=S2-INDUSTRY_BASKETS": f["S2"] - f["INDUSTRY_BASKETS"],
                            "(2b)selectionVsSizeControl=S2-SIZE_CONTROL": f["S2"] - f["SIZE_CONTROL"],
                            "(3)netVsEtf=S2-ETF": f["S2"] - f["ETF"]}
    # ---- unresolved corporate-action windows inside held legs, and the paired result without them ----------------------- #
    flags, flagged_days = {}, set()
    for k in ("S2", "SIZE_CONTROL"):
        legs = []
        for p in phases:
            lg = A.attribute_books(ctx2, books[k][p], phases[p]["end"], k)
            lg["policy"], lg["phase"] = k, p
            legs.append(lg)
        fl = A.held_window_flags(ctx2, pd.concat(legs))
        flags[k] = [{**x, "execution": str(x["execution"].date()), "periodEnd": str(x["periodEnd"].date())} for x in fl]
        for x in fl:
            flagged_days |= set(sess[(sess > x["execution"]) & (sess <= x["periodEnd"])])
    out["unresolvedWindows"] = {"S2": flags["S2"], "SIZE_CONTROL": flags["SIZE_CONTROL"], "flaggedSessions": len(flagged_days)}
    keep = [d for d in daily["S2"].index if d not in flagged_days]
    for a_, b_ in (("S2", "SIZE_CONTROL"), ("S2", "INDUSTRY_BASKETS"), ("S2", "ETF")):
        d_ = (daily[a_] - daily[b_].reindex(daily[a_].index)).reindex(keep).dropna()
        out["paired"][f"{a_}-{b_}"]["excludingFlaggedSessions"] = C.block_bootstrap(d_)
    (HERE / "s2-control-and-gate.json").write_text(json.dumps(out, indent=1, ensure_ascii=False, default=str) + "\n")
    ev.drop(columns=["signal"]).to_csv(Path(a.scratch) / "s2-pick-forward-private.csv", index=False)
    print(json.dumps({k: {m: round(v["full"][m], 4) for m in ("cagr", "excessCagr", "mdd")} for k, v in out["books"].items()}))
    print(json.dumps(training))


if __name__ == "__main__":
    main()
