"""alpha-mechanism-decomposition-v1 — why did the strategies in #329 make (or lose) money?

    python research/alpha_mechanism_decomposition_v1/analyze.py --scratch <dir>

<dir> must hold what the #329 pipeline produced from the pinned signal-history commit 4ea107ed (see README / REPORT §재현):
    matrix.pkl, dataset.pkl            research/ml_strategy_tournament_v1/{build_features,prepare_dataset}.py
    macro_panel.pkl, vix_fx.pkl        research/adaptive_cocktail_v1/load_sources.py
    raw/ledger/universe/kr/*.jsonl.gz  materialised by build_features (PIT market caps for industry baskets and matching)

Nothing is fitted, tuned or selected here. The frozen #329 code is CALLED from byte-identical vendored copies (vendor/PROVENANCE.json);
every decomposition is read only after the vendored code reproduces the published #329 numbers (verification.json "reproduction").
Every number is POST_HOC / EXPLORATORY on outcome-exposed KR history and is computed on the replay-v16 conditional total-return
index, never a certified shareholder return.
"""
from __future__ import annotations

import argparse
import glob
import gzip
import hashlib
import importlib.util
import itertools
import json
import math
import pickle
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
EVIDENCE = "POST_HOC_EXPLORATORY_DECOMPOSITION_ON_OUTCOME_EXPOSED_KR_HISTORY"
RETURN_BASIS = "CONDITIONAL_REPLAY_V16_TOTAL_RETURN_INDEX_NOT_CERTIFIED_SHAREHOLDER_RETURN"
POST_HOC_INDUSTRIES = ("CAPITAL_GOODS_DEFENSE", "ELECTRONICS_ELECTRICAL")
MEGA = ("005930.KS", "000660.KS")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


RUN = _load("amd_cocktail_run", HERE / "vendor/adaptive_cocktail_v1/run.py")
C = RUN.C
C.ROOT = ROOT                     # the only runtime patch: the vendored file sits two levels deeper than the original
T = _load("amd_tournament", HERE / "vendor/ml_strategy_tournament_v1/tournament.py")
M = _load("amd_mechanism", HERE / "mechanism.py")
SLEEVES = list(C.CHOICE)
RISKY = list(C.RISKY)
SMS = "SLEEVE_MOMENTUM_SWITCH"


def r6(x, n=6):
    if x is None:
        return None
    try:
        x = float(x)
    except (TypeError, ValueError):
        return x
    return round(x, n) if math.isfinite(x) else None


def clean(o):
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (float, np.floating)):
        return r6(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (pd.Timestamp,)):
        return str(o.date())
    return o


# =========================================================================== #
# Inputs
# =========================================================================== #
def load(scratch):
    s = Path(scratch)
    df, closes, vols, sessions, macro, vix, fx, rf, ident = RUN.load(s)
    blob = pickle.loads((s / "dataset.pkl").read_bytes())
    raw_closes = blob["closes"]                                  # before the #330 final-session correction (tournament v1 basis)
    rows = pickle.loads((s / "matrix.pkl").read_bytes())["matrix"].rows[["date", "ticker", "pitSnapshotDate"]].copy()
    rows["date"] = pd.to_datetime(rows["date"])
    df = df.merge(rows, on=["date", "ticker"], how="left", validate="one_to_one")
    caps = {}
    for p in sorted(glob.glob(str(s / "raw/ledger/universe/kr/*.jsonl.gz"))):
        with gzip.open(p, "rt") as fh:
            for line in fh:
                r = json.loads(line)
                caps[(r["date"], r["ticker"])] = r.get("marketCap")
    df["_mcap"] = [caps.get((str(d)[:10], t)) for d, t in zip(df["pitSnapshotDate"], df["ticker"])]
    df["_mcap"] = df["_mcap"].astype(float)
    ident = dict(ident, mcapCoverage=float(df["_mcap"].notna().mean()), universeShards=len(glob.glob(str(s / "raw/ledger/universe/kr/*.jsonl.gz"))))
    return dict(df=df, closes=closes, raw_closes=raw_closes, vols=vols, sessions=sessions, macro=macro, vix=vix, fx=fx, rf=rf, ident=ident)


def run_phase(I, phase, exclude=(), cost_mult=1.0):
    return RUN.run_all(I["df"], I["closes"], I["vols"], I["sessions"], I["macro"], I["vix"], I["fx"], I["rf"], exclude=exclude,
                       cost_mult=cost_mult, label=f"AMD{phase}", phase=phase)


# =========================================================================== #
# Shared attribution machinery
# =========================================================================== #
class Ctx:
    def __init__(self, I):
        self.I = I
        self.by = {d: g for d, g in I["df"].groupby("date")}
        px = C.Prices(I["closes"], I["vols"], I["sessions"], I["rf"])
        term = {t: I["sessions"][i] for t, i in px.terminal.items()}
        self.pp = M.PeriodPrices(I["closes"], I["sessions"], I["rf"], terminal=term)
        self.px = px
        self.cache = {}


def policy_book(R, name, d):
    w = R["weights"][name][d]
    return C.combine({k: R["books"][k][d] for k in w}, w)


def books_to_schedule(books, sessions):
    return {M.next_session(sessions, d): b for d, b in books.items() if M.next_session(sessions, d) is not None}


def attribute_books(ctx, books, end, tag, extra=None):
    """books: {signal date: {asset: weight}} -> leg DataFrame over the periods those decisions define."""
    sess = ctx.I["sessions"]
    per = M.periods(sorted(books), sess, end)
    legs = []
    for k, (d, e, x) in enumerate(per):
        for r in M.attribute_book(books[d], ctx.by[d], ctx.pp, e, x, cache=ctx.cache):
            r.update(period=k, date=d, execution=e, periodEnd=x, tag=tag, **(extra(d) if extra else {}))
            legs.append(r)
    return pd.DataFrame(legs)


def engine_paths(ctx, books, start, end, cost_mult=1.0):
    sched = books_to_schedule(books, ctx.I["sessions"])
    net = C.simulate(ctx.px, sched, start, end, cost_mult=cost_mult)
    gross = C.simulate(ctx.px, sched, start, end, cost_mult=0.0)
    return net, gross


def full_decomposition(ctx, books, start, end, bench, tag, cost_mult=1.0, extra=None):
    legs = attribute_books(ctx, books, end, tag, extra)
    years = (len(ctx.I["sessions"][(ctx.I["sessions"] >= start) & (ctx.I["sessions"] <= end)]) - 1) / 252
    s = M.summarise(legs, years, tag)
    net, gross = engine_paths(ctx, books, start, end, cost_mult)
    nn, gg = net["nav"], gross["nav"]
    per = legs.groupby("period").agg(e=("execution", "first"), x=("periodEnd", "first"))
    wr = (legs["weight"] * legs["R"]).groupby(legs["period"]).sum()
    g_t = gg.reindex(per["x"]).to_numpy() / gg.reindex(per["e"]).to_numpy() - 1
    n_t = nn.reindex(per["x"]).to_numpy() / nn.reindex(per["e"]).to_numpy() - 1
    mech = g_t - wr.to_numpy()
    cost = n_t - g_t
    m = C.metrics(nn, bench, ctx.I["rf"])
    s.update(netCagr=m["cagr"], netExcessCagr=m["excessCagr"], sharpe=m["sharpe"], mdd=m["mdd"], trackingError=m["trackingError"],
             informationRatio=m["informationRatio"], vol=m["vol"], costPerYearEngine=net["costs"] / years, turnoverPerYear=net["turnover"] / years,
             MECHANICS=float(np.nansum(mech) / years), COST=float(np.nansum(cost) / years), terminalHits=len(net["terminalHits"]),
             nanLegs=int(legs["R"].isna().sum()))
    s["compoundingNet"] = s["netExcessCagr"] - (s["arithmeticExcess"] + s["MECHANICS"] + s["COST"])
    per_rows = pd.DataFrame({"period": per.index, "execution": per["e"].to_numpy(), "periodEnd": per["x"].to_numpy(), "MECHANICS": mech, "COST": cost,
                             "grossEngine": g_t, "netEngine": n_t})
    return legs, s, per_rows, nn


def regime_split(legs, states, key="MKT_TREND_252"):
    st = {d: states.loc[:d].iloc[-1][key] for d in legs["date"].unique()}
    lab = legs["date"].map(lambda d: "BULL_252D_UP" if st[d] > 0 else "BEAR_252D_DOWN")
    out = {}
    for name, g in legs.groupby(lab):
        days = g.groupby("period").agg(e=("execution", "first"), x=("periodEnd", "first"))
        yrs = sum((x - e).days for e, x in zip(days["e"], days["x"])) / 365.25
        out[name] = {"periods": int(len(days)), "years": r6(yrs, 3), **{t: r6(g[t].sum() / yrs) for t in M.TERMS},
                     "arithmeticExcess": r6(g["excess"].sum() / yrs)}
    return out


def term_by(legs, years, col):
    g = legs.groupby(col)[list(M.TERMS) + ["excess"]].sum() / years
    return {k: {c: r6(v) for c, v in row.items()} for k, row in g.iterrows()}


# =========================================================================== #
# H1 — strategy momentum
# =========================================================================== #
def h1(ctx, R, phase):
    sess, end, start, bench = ctx.I["sessions"], R["end"], R["start"], R["bench"]
    years = (len(sess[(sess >= start) & (sess <= end)]) - 1) / 252
    out, legs_all, per_all, mech_events = {}, [], [], []
    chosen = {d: max(w, key=w.get) for d, w in R["weights"][SMS].items()}
    sleeve_legs = {}
    for name in [SMS, "STATIC_EW4"] + SLEEVES:
        books = {d: policy_book(R, name, d) for d in R["weights"][name]}
        legs, s, per_rows, nav = full_decomposition(ctx, books, start, end, bench, name,
                                                    extra=(lambda d: {"sleeve": chosen[d]}) if name == SMS else None)
        legs["policy"], legs["phase"] = name, phase
        per_rows["policy"], per_rows["phase"] = name, phase
        mech_events += mechanics_events(ctx, legs, per_rows, name, phase)
        legs_all.append(legs)
        per_all.append(per_rows)
        s["byYear"] = term_by(legs.assign(y=legs["execution"].dt.year), 1.0, "y")
        s["byIndustry"] = term_by(legs, years, "industry")
        s["regime"] = regime_split(legs, R["states"])
        keep = legs["execution"].dt.year != 2025
        y_wo = years - legs.loc[~keep].groupby("period").apply(lambda g: (g["periodEnd"].iloc[0] - g["execution"].iloc[0]).days / 365.25,
                                                                include_groups=False).sum()
        s["without2025"] = {t: r6(legs.loc[keep, t].sum() / y_wo) for t in M.TERMS + ("excess",)}
        mega = legs["asset"].isin(MEGA)
        s["megaCapLegs"] = {t: r6(legs.loc[mega, t].sum() / years) for t in M.TERMS + ("excess",)}
        two = legs["industry"].isin(POST_HOC_INDUSTRIES)
        s["defenseElectronicsLegs"] = {t: r6(legs.loc[two, t].sum() / years) for t in M.TERMS + ("excess",)}
        out[name] = s
        if name in SLEEVES:
            sleeve_legs[name] = legs
    # sleeve layer: choice value of the switch, decomposed by term
    pr = {k: sleeve_legs[k].groupby("period")[list(M.TERMS) + ["excess"]].sum() for k in SLEEVES}
    pid = sleeve_legs[SLEEVES[0]].groupby("period")["date"].first()
    ch = pd.Series([chosen[d] for d in pid], index=pid.index)
    cv = {}
    for t in list(M.TERMS) + ["excess"]:
        frame = pd.DataFrame({k: pr[k][t] for k in SLEEVES})
        v = M.choice_value(frame, ch)
        cv[t] = {"annualised": r6(v.sum() / years), "meanPerPeriod": r6(v.mean()),
                 "bootstrapPerPeriod": M.block_bootstrap_mean(v, 3, reps=4000, scale=len(v) / years)}
    gross = pd.DataFrame({k: (sleeve_legs[k]["weight"] * sleeve_legs[k]["R"]).groupby(sleeve_legs[k]["period"]).sum() for k in SLEEVES})
    nulls = M.permutation_null(gross, ch, years, draws=10000)
    freq = ch.value_counts(normalize=True).to_dict()
    twin = {d: {k: freq.get(k, 0.0) for k in SLEEVES} for d in R["weights"][SMS]}
    twin_books = {d: C.combine({k: R["books"][k][d] for k in SLEEVES}, twin[d]) for d in twin}
    _, tw, _, _ = full_decomposition(ctx, twin_books, start, end, bench, "SAME_AVERAGE_EXPOSURE_TWIN")
    sw = ch.ne(ch.shift()).iloc[1:]
    out["_sleeveLayer"] = {
        "choiceValue": cv, "permutationNull": nulls, "chosenFrequency": {k: r6(v, 4) for k, v in freq.items()},
        "switchShare": r6(sw.mean(), 4), "switches": int(sw.sum()),
        "sameAverageExposureTwin": {k: tw[k] for k in ("netCagr", "netExcessCagr", "sharpe", "mdd", "INDUSTRY_ALPHA", "SELECTION_ALPHA", "MARKET_BETA",
                                                     "COST", "compoundingNet")},
        "persistence": sleeve_persistence(gross, ch, R, sess),
        "byChosenSleeve": {k: {t: r6(sum(pr[k].at[p, t] for p in ch.index[ch == k]) / years) for t in list(M.TERMS) + ["excess"]} for k in SLEEVES}}
    out["_mechanicsEvents"] = mech_events
    return out, pd.concat(legs_all), pd.concat(per_all)


def mechanics_events(ctx, legs, per_rows, name, phase, threshold=0.002):
    """Name every period where the frozen engine's gross return departs from the buy-and-hold target book by more than `threshold`.
    The engine keeps a name it cannot trade at the execution close (zero volume / no close) and writes a terminated name off at ZERO;
    the target book does neither. The names responsible are the previous period's stock legs that were untradable at this execution
    session or whose terminal session falls inside this period."""
    out = []
    sess = ctx.I["sessions"]
    prev = {k: set(g["asset"]) - {M.ETF, M.CASH} for k, g in legs.groupby("period")}
    for _, r in per_rows.iterrows():
        if not np.isfinite(r["MECHANICS"]) or abs(r["MECHANICS"]) <= threshold:
            continue
        k, e, x = int(r["period"]), r["execution"], r["periodEnd"]
        i = ctx.px.pos[e]
        execs = per_rows.set_index("period")["execution"]
        carried = set()
        for j in range(k - 1, -1, -1):                     # a name stays in the engine's book while it is untradable at every later execution
            for t in prev.get(j, ()):
                if all(not ctx.px.tradable[ctx.px.pos[execs[m]], ctx.px.col[t]] for m in range(j + 1, k + 1)):
                    carried.add(t)
        locked = sorted(carried)
        term = sorted(t for t in carried | prev.get(k, set()) if t in ctx.pp.terminal and ctx.pp.terminal[t] < x)
        untradable_days = {t: int((~ctx.px.tradable[i:ctx.px.pos[x] + 1, ctx.px.col[t]]).sum()) for t in locked}
        kind = ("TERMINAL_WRITE_OFF_AT_ZERO_UNRESOLVED_CONSIDERATION" if term else
                "LOCKED_UNTRADABLE_AT_REBALANCE" if locked else "DRIFT_OR_NETTING")
        out.append({"policy": name, "phase": phase, "execution": str(e.date()), "periodEnd": str(x.date()), "mechanics": r6(r["MECHANICS"]),
                    "kind": kind, "lockedNames": locked, "terminalNames": term, "untradableSessionsInPeriod": untradable_days,
                    "sessionsInPeriod": int(len(sess[(sess > e) & (sess <= x)]))})
    return out


def sleeve_persistence(gross, ch, R, sess):
    """Does the trailing-126 leader keep leading over the next holding period? Rank IC of trailing vs next-period sleeve return,
    and the rate at which the chosen sleeve is the period's best (chance = 1/4)."""
    navs = R["navs"]
    dates = sorted(R["weights"][SMS])
    ic, best = [], []
    for k, d in enumerate(dates[: len(gross)]):
        tr = {s: navs[s].loc[:d].iloc[-1] / navs[s].loc[:d].iloc[-127] - 1 for s in SLEEVES if len(navs[s].loc[:d]) > 127}
        if len(tr) < 4:
            continue
        nxt = gross.iloc[k]
        ic.append(M.spearman(pd.Series(tr), nxt[list(tr)]))
        best.append(nxt.idxmax() == ch.iloc[k])
    return {"meanRankIcTrailing126VsNextPeriod": r6(np.nanmean(ic), 4), "icHac": M.hac_mean(ic, 2),
            "chosenIsBestShare": r6(np.mean(best), 4), "chance": 0.25, "n": len(ic)}


# =========================================================================== #
# Industry-momentum diagnostics (H1 industry choice, H3)
# =========================================================================== #
def industry_forward(ctx, horizons=(20, 63)):
    sess = ctx.I["sessions"]
    pos = {d: i for i, d in enumerate(sess)}
    rows = []
    for d, g in ctx.by.items():
        if d.year < 2014:
            continue
        e = M.next_session(sess, d)
        if e is None:
            continue
        q = g[g["_q"]]
        for ind, gi in q.groupby("industry"):
            h01 = g.loc[g["industry"] == ind, "H01_industryRelMom126"].dropna()
            rec = {"table": "INDUSTRY_FORWARD", "date": d, "industry": ind, "H01": float(h01.iloc[0]) if len(h01) else np.nan, "members": len(gi)}
            bw = M.industry_basket(g, ind)
            for h in horizons:
                ix = pos[e] + h
                if ix >= len(sess):
                    rec[f"fwd{h}"] = np.nan
                    continue
                x = sess[ix]
                rets = {t: ctx.pp.ret(t, e, x) for t in bw}
                ok = {t: w for t, w in bw.items() if np.isfinite(rets[t])}
                s = sum(ok.values())
                rec[f"fwd{h}"] = sum(w / s * rets[t] for t, w in ok.items()) if s > 0 else np.nan
                rec[f"etf{h}"] = ctx.pp.ret(M.ETF, e, x)
            rows.append(rec)
    return pd.DataFrame(rows)


def industry_ic(F, h, mask=None, label=""):
    f = F if mask is None else F[mask]
    f = f.dropna(subset=["H01", f"fwd{h}"])
    ic = f.groupby("date").apply(lambda g: M.spearman(g["H01"], g[f"fwd{h}"]) if len(g) >= 5 else np.nan, include_groups=False).dropna()
    top = f.loc[f.groupby("date")["H01"].idxmax()].set_index("date")[f"fwd{h}"]
    mean = f.groupby("date")[f"fwd{h}"].mean()
    spread = (top - mean.reindex(top.index)).dropna()
    lags = max(1, h // 5)
    return {"label": label, "horizon": h, "dates": int(len(ic)), "meanRankIc": r6(ic.mean(), 4), "icHac": M.hac_mean(ic, lags),
            "topIndustryMinusIndustryMean": r6(spread.mean(), 5), "spreadHac": M.hac_mean(spread, lags),
            "topIndustryHitRate": r6((spread > 0).mean(), 4)}


def within_industry_ic(ctx, h=20):
    """A09 (stock vs cap-weighted peers, trailing 126) against the next-h-session stock-minus-industry-basket return."""
    sess = ctx.I["sessions"]
    pos = {d: i for i, d in enumerate(sess)}
    ics, dates = [], []
    for d, g in ctx.by.items():
        if d.year < 2014:
            continue
        e = M.next_session(sess, d)
        if e is None or pos[e] + h >= len(sess):
            continue
        x = sess[pos[e] + h]
        q = g[g["_q"]].dropna(subset=["A09_industryRelativeMomentum126"])
        vals = []
        for ind, gi in q.groupby("industry"):
            if len(gi) < 3:
                continue
            bw = M.industry_basket(g, ind)
            rets = {t: ctx.pp.ret(t, e, x) for t in set(bw) | set(gi["ticker"])}
            rind = sum(w * rets[t] for t, w in bw.items() if np.isfinite(rets[t])) / max(1e-12, sum(w for t, w in bw.items() if np.isfinite(rets[t])))
            y = pd.Series({t: rets[t] - rind for t in gi["ticker"]})
            vals.append(M.spearman(gi.set_index("ticker")["A09_industryRelativeMomentum126"], y))
        v = np.nanmean(vals) if vals else np.nan
        if np.isfinite(v):
            ics.append(v)
            dates.append(d)
    s = pd.Series(ics, index=dates).sort_index()
    return {"horizon": h, "dates": int(len(s)), "meanWithinIndustryRankIc": r6(s.mean(), 4), "hac": M.hac_mean(s, 4),
            "byYear": {int(y): r6(v.mean(), 4) for y, v in s.groupby(s.index.year)}}


def entry_timing(R1legs):
    """For S1's defense / electronics legs: the industry's H01 rank among industries at the decision date and the year of first entry."""
    out = {}
    for ind in POST_HOC_INDUSTRIES:
        g = R1legs[(R1legs["industry"] == ind)]
        if g.empty:
            continue
        out[ind] = {"periodsHeld": int(g["period"].nunique()), "firstExecution": str(g["execution"].min().date()),
                    "heldByYear": {int(y): int(v) for y, v in g.groupby(g["execution"].dt.year)["period"].nunique().items()},
                    "industryAlphaByYear": {int(y): r6(v) for y, v in g.groupby(g["execution"].dt.year)["INDUSTRY_ALPHA"].sum().items()},
                    "selectionAlphaByYear": {int(y): r6(v) for y, v in g.groupby(g["execution"].dt.year)["SELECTION_ALPHA"].sum().items()}}
    return out


# =========================================================================== #
# H3 — 23.27% vs 7.56% bridge (full factorial + Shapley)
# =========================================================================== #
def rule_scores(df):
    s = df.groupby("date")["H01_industryRelMom126"].rank(pct=True) + 0.01 * df.groupby("date")["A09_industryRelativeMomentum126"].rank(pct=True).fillna(0)
    return s.where(df["date"].dt.year >= 2015)


def bridge(ctx, I):
    df = I["df"].copy()
    df["_rule"] = rule_scores(df)
    calib, exits = T.calibration_table(df, "_rule", 126)
    by = {d: g for d, g in df.groupby("date")}
    sess = I["sessions"]
    weekly = sorted(d for d in by if d.year >= 2014)
    t_dates = sorted(d for d in by if d >= pd.Timestamp("2016-01-01"))[::4]
    t_phase = [p for p in range(4) if set(t_dates) <= set(weekly[p::4])]
    t_phase = t_phase[0] if t_phase else None
    bench_end = I["closes"][M.ETF].last_valid_index()

    def prices(corrected):
        return I["closes"] if corrected else I["raw_closes"]

    books_t = {}
    for corrected in (False, True):
        cl = prices(corrected)
        books_t[corrected] = T.PriceBook({t: pd.DataFrame({"Close": cl[t], "Volume": I["vols"][t]}) for t in cl.columns}, list(cl.columns), sess, cl[M.ETF])
    px_c = {cor: C.Prices(prices(cor), I["vols"], sess, I["rf"]) for cor in (False, True)}
    results = {}
    decide_cache = {}
    for gate, start16, phase0, cengine, corrected, withheld in itertools.product((1, 0), (1, 0), (0, 1), (0, 1), (0, 1), (0, 1)):
        dates = weekly[0::4] if phase0 else weekly[t_phase::4]
        dates = [d for d in dates if d >= pd.Timestamp("2016-01-01" if start16 else "2018-01-01")]
        excl = tuple(C.WITHHELD) if withheld else ()
        sched = {}
        for d in dates:
            key = (d, gate, excl)
            if key not in decide_cache:
                decide_cache[key] = T.decide(by[d], "_rule", calib, exits, d, 126, gate=bool(gate), exclude=excl)[0]
            e = M.next_session(sess, d)
            if e is not None:
                sched[e] = decide_cache[key]
        start = min(sched)
        if cengine:
            cs = {e: (dict(w, **{M.ETF: 1.0 - sum(w.values())}) if sum(w.values()) < 1 - 1e-12 else dict(w)) for e, w in sched.items()}
            nav = C.simulate(px_c[bool(corrected)], cs, start, bench_end)["nav"]
        else:
            nav = T.simulate(books_t[bool(corrected)], sched, start, bench_end)["nav"]
        bn = prices(corrected)[M.ETF].reindex(nav.index).ffill()
        yrs = (len(nav) - 1) / 252
        cg = (nav.iloc[-1] / nav.iloc[0]) ** (1 / yrs) - 1
        bc = (bn.iloc[-1] / bn.iloc[0]) ** (1 / yrs) - 1
        yearly = {}
        for y, gg in nav.groupby(nav.index.year):
            i0 = nav.index.get_loc(gg.index[0])
            yearly[int(y)] = r6(gg.iloc[-1] / (nav.iloc[i0 - 1] if i0 else nav.iloc[0]) - 1)
        results[(gate, start16, phase0, cengine, corrected, withheld)] = {"cagr": cg, "etfCagr": bc, "excess": cg - bc, "start": str(start.date()),
                                                                         "yearly": yearly}
        if not cengine:
            # the tournament's own metric annualises nav_end / 1.0 (the pre-trade NAV), i.e. it includes the first purchase cost
            results[(gate, start16, phase0, cengine, corrected, withheld)]["cagrTournamentConvention"] = float(nav.iloc[-1]) ** (252 / (len(nav) - 1)) - 1
    factors = ["gate", "start2016", "phase0", "cocktailEngine", "correctedFinalQuotes", "withhold006800"]
    origin = (1, 1, 0, 0, 0, 0)
    target = (0, 0, 1, 1, 1, 1)

    def val(sub, metric):
        key = tuple(target[i] if i in sub else origin[i] for i in range(6))
        return results[key][metric]

    shap = {}
    for metric in ("cagr", "excess"):
        sv = {}
        for i, f in enumerate(factors):
            others = [j for j in range(6) if j != i]
            tot = 0.0
            for r in range(6):
                for S in itertools.combinations(others, r):
                    wgt = math.factorial(r) * math.factorial(6 - r - 1) / math.factorial(6)
                    tot += wgt * (val(set(S) | {i}, metric) - val(set(S), metric))
            sv[f] = r6(tot)
        shap[metric] = sv
    path, cur = [], set()
    for i, f in enumerate(factors):
        before = val(cur, "cagr")
        cur = cur | {i}
        path.append({"step": f, "cagrBefore": r6(before), "cagrAfter": r6(val(cur, "cagr")), "delta": r6(val(cur, "cagr") - before)})
    return {"tournamentPhase": t_phase, "origin": dict(zip(factors, origin)), "target": dict(zip(factors, target)),
            "originReproduction": {"publishedGated": 0.232735, "publishedForced": 0.230184,
                                   "reproducedGatedTournamentConvention": r6(results[origin]["cagrTournamentConvention"]),
                                   "reproducedForcedTournamentConvention": r6(results[(0,) + origin[1:]]["cagrTournamentConvention"])},
            "originCagr": r6(results[origin]["cagr"]), "targetCagr": r6(results[target]["cagr"]),
            "originExcess": r6(results[origin]["excess"]), "targetExcess": r6(results[target]["excess"]),
            "shapley": shap, "sequentialPath": path,
            "grid": [{**dict(zip(factors, k)), **{m: (r6(v) if not isinstance(v, (dict, str)) else v) for m, v in res.items()}} for k, res in results.items()]}


# =========================================================================== #
# Variant books (H2 ablation, H3 industry baskets and matched controls)
# =========================================================================== #
def topn_book(g, score, n=5, exclude=()):
    w, _, _ = C.sleeve_book("S2_VALUE_CONFIRMED", g, exclude, score=score)
    return w


def ew_book(g, mask):
    names = [t for t in g.loc[mask & g["_q"], "ticker"] if t not in C.WITHHELD]
    return {t: 1.0 / len(names) for t in names} if names else {M.ETF: 1.0}


def industry_book(g, base):
    """Same weights as `base`, each stock leg spread over its PIT cap-weighted industry basket."""
    out = {}
    for a, w in base.items():
        if a in (M.ETF, M.CASH):
            out[a] = out.get(a, 0.0) + w
            continue
        ind = g.loc[g["ticker"] == a, "industry"].iloc[0]
        bw = {t: v for t, v in M.industry_basket(g, ind).items() if t not in C.WITHHELD} or {a: 1.0}
        s = sum(bw.values())
        for t, v in bw.items():
            out[t] = out.get(t, 0.0) + w * v / s
    return out


def control_book(g, base, cols):
    picks = [a for a in base if a not in (M.ETF, M.CASH)]
    g2 = g[~g["ticker"].isin(C.WITHHELD)]
    ctrl = M.matched_controls(g2, picks, cols)
    out = {}
    for a, w in base.items():
        b = ctrl.get(a, a) if a not in (M.ETF, M.CASH) else a
        b = M.ETF if b is None else b
        out[b] = out.get(b, 0.0) + w
    return out, sum(1 for v in ctrl.values() if v is None)


def variant_table(ctx, R, phase, variants, bench_books_key):
    start, end, bench = R["start"], R["end"], R["bench"]
    rows, legs_out, daily = [], [], {}
    for vname, books in variants.items():
        legs, s, _, nav = full_decomposition(ctx, books, start, end, bench, vname)
        legs["policy"], legs["phase"] = vname, phase
        legs_out.append(legs)
        daily[vname] = nav.pct_change()
        rows.append({"phase": phase, "variant": vname, **{k: s[k] for k in ("netCagr", "netExcessCagr", "sharpe", "mdd", "trackingError", "informationRatio",
                                                                            "vol", "costPerYearEngine", "turnoverPerYear", "MARKET_BETA", "INDUSTRY_ALPHA",
                                                                            "SELECTION_ALPHA", "arithmeticExcess", "compounding", "COST", "MECHANICS",
                                                                            "meanEtfWeight", "meanBookBeta")},
                     "megaCapExcess": r6(legs.loc[legs["asset"].isin(MEGA), "excess"].sum() / s["years"]),
                     "defenseElectronicsExcess": r6(legs.loc[legs["industry"].isin(POST_HOC_INDUSTRIES), "excess"].sum() / s["years"])})
    return rows, pd.concat(legs_out), daily


def paired(daily, a, b):
    d = (daily[a] - daily[b]).dropna()
    return C.block_bootstrap(d)


def h2(ctx, R, phase):
    dates = sorted(R["weights"]["S2_VALUE_CONFIRMED"])
    base = {d: R["books"]["S2_VALUE_CONFIRMED"][d] for d in dates}
    V = {"C_VALUE_AND_CONFIRMATION_ORIGINAL": base, "A_VALUE_ONLY": {}, "A_VALUE_UNCONFIRMED_ONLY": {}, "B_CONFIRMATION_ONLY_EW": {},
         "D_MATCHED_CONTROL_SAME_INDUSTRY": {}, "C_INDUSTRY_BASKETS_OF_PICKS": {}, "VALUE_ONLY_EW_TOP_TERCILE": {}}
    unmatched = 0
    pick_h01 = []
    for d in dates:
        g = ctx.by[d]
        v = g["B08_valueBusinessConfirmation"]
        V["A_VALUE_ONLY"][d] = topn_book(g, v)
        V["A_VALUE_UNCONFIRMED_ONLY"][d] = topn_book(g, v.where(g["b08Confirmed"] == 0))
        V["B_CONFIRMATION_ONLY_EW"][d] = ew_book(g, (g["b08Confirmed"] == 1) & v.notna())
        V["VALUE_ONLY_EW_TOP_TERCILE"][d] = ew_book(g, v >= 2 / 3)
        V["C_INDUSTRY_BASKETS_OF_PICKS"][d] = industry_book(g, base[d])
        V["D_MATCHED_CONTROL_SAME_INDUSTRY"][d], u = control_book(g, base[d], ["_mcap", "E02_logAdv60", "A07_momentum12_1"])
        unmatched += u
        h = g.set_index("ticker")["H01_industryRelMom126"].rank(pct=True)
        pick_h01 += [float(h.get(t)) for t in base[d] if t in h.index and np.isfinite(h.get(t))]
    rows, legs, daily = variant_table(ctx, R, phase, V, None)
    C_ = "C_VALUE_AND_CONFIRMATION_ORIGINAL"
    pairs = {f"{C_}-{k}": paired(daily, C_, k) for k in V if k != C_}
    pairs["C-ETF"] = C.block_bootstrap((daily[C_] - R["bench"].pct_change()).dropna())
    s1x = (R["navs"]["S1_INDUSTRY_MOMENTUM"].pct_change() - R["navs"]["S0_ETF"].pct_change()).reindex(daily[C_].index)
    s2x = daily[C_] - R["bench"].pct_change().reindex(daily[C_].index)
    j = pd.concat([s2x.rename("s2"), s1x.rename("s1")], axis=1).dropna()
    b = np.polyfit(j["s1"], j["s2"], 1)
    extra = {"unmatchedPicks": unmatched, "meanIndustryMomentumPercentileOfPicks": r6(np.mean(pick_h01), 4),
             "s2ExcessOnS1ExcessDailySlope": r6(b[0], 4), "s2S1ExcessCorrelation": r6(j.corr().iloc[0, 1], 4)}
    return rows, legs, pairs, extra


def h3_variants(ctx, R, phase):
    dates = sorted(R["weights"]["S1_INDUSTRY_MOMENTUM"])
    base = {d: R["books"]["S1_INDUSTRY_MOMENTUM"][d] for d in dates}
    V = {"S1_ORIGINAL": base, "S1_INDUSTRY_BASKETS_CAP": {}, "S1_INDUSTRY_BASKETS_EW": {}, "S1_MATCHED_CONTROL_SIZE_LIQUIDITY": {}}
    for d in dates:
        g = ctx.by[d]
        V["S1_INDUSTRY_BASKETS_CAP"][d] = industry_book(g, base[d])
        eb = {}
        for a, w in base[d].items():
            if a in (M.ETF, M.CASH):
                eb[a] = eb.get(a, 0) + w
                continue
            ind = g.loc[g["ticker"] == a, "industry"].iloc[0]
            bw = [t for t in M.industry_basket(g, ind, equal=True) if t not in C.WITHHELD] or [a]
            for t in bw:
                eb[t] = eb.get(t, 0) + w / len(bw)
        V["S1_INDUSTRY_BASKETS_EW"][d] = eb
        V["S1_MATCHED_CONTROL_SIZE_LIQUIDITY"][d], _ = control_book(g, base[d], ["_mcap", "E02_logAdv60"])
    rows, legs, daily = variant_table(ctx, R, phase, V, None)
    pairs = {f"S1_ORIGINAL-{k}": paired(daily, "S1_ORIGINAL", k) for k in V if k != "S1_ORIGINAL"}
    pairs["S1_INDUSTRY_BASKETS_CAP-ETF"] = C.block_bootstrap((daily["S1_INDUSTRY_BASKETS_CAP"] - R["bench"].pct_change()).dropna())
    return rows, legs, pairs


# =========================================================================== #
# H4 — reading the learned cocktail's own forecasts (no new fit)
# =========================================================================== #
def h4(ctx, R):
    lab63 = R["labels"][63]
    sess = ctx.I["sessions"]
    navs = R["navs"]
    out = {}
    for kind, dg in R["diags"].items():
        rows = []
        for d, g in dg.items():
            if "mu" not in g or lab63.get(d, {}).get("exit") is None:
                continue
            real = {k: lab63[d].get(k) for k in RISKY}
            e = M.next_session(sess, d)
            i = sess.get_loc(e)
            x = sess[min(i + 20, len(sess) - 1)]
            r20 = {k: navs[k].loc[x] / navs[k].loc[e] - navs["S0_ETF"].loc[x] / navs["S0_ETF"].loc[e] for k in RISKY}
            tr126 = {k: (navs[k].loc[:d].iloc[-1] / navs[k].loc[:d].iloc[-127] - navs["S0_ETF"].loc[:d].iloc[-1] / navs["S0_ETF"].loc[:d].iloc[-127])
                     for k in RISKY}
            rows.append({"date": d, "n": g["n"], **{f"mu_{k}": g["mu"][k] for k in RISKY}, **{f"se_{k}": g["se"][k] for k in RISKY},
                         **{f"y63_{k}": real[k] for k in RISKY}, **{f"y20_{k}": r20[k] for k in RISKY}, **{f"tr126_{k}": tr126[k] for k in RISKY}})
        f = pd.DataFrame(rows)
        if f.empty:
            continue

        def rank_skill(pred_prefix, real_prefix):
            ic = [M.spearman(pd.Series([r[f"{pred_prefix}_{k}"] for k in RISKY]), pd.Series([r[f"{real_prefix}_{k}"] for k in RISKY])) for _, r in f.iterrows()]
            hit = [max(RISKY, key=lambda k: r[f"{pred_prefix}_{k}"]) == max(RISKY, key=lambda k: r[f"{real_prefix}_{k}"]) for _, r in f.iterrows()]
            return {"meanCrossSleeveRankIc": r6(np.nanmean(ic), 4), "icHac": M.hac_mean(ic, 3), "topPickIsBestShare": r6(np.mean(hit), 4), "chance": r6(1 / 3, 4)}

        oos = {}
        for k in RISKY:
            pred, real = f[f"mu_{k}"].to_numpy(), f[f"y63_{k}"].to_numpy()
            hist = []
            for d in f["date"]:
                tr = [x for x in R["dates"] if x < d and lab63[x].get("exit") is not None and lab63[x]["exit"] < d and k in lab63[x]]
                hist.append(np.mean([lab63[x][k] for x in tr]))
            hist = np.array(hist)
            oos[k] = {"n": int(len(real)), "oosR2VsExpandingMean": r6(1 - ((real - pred) ** 2).sum() / ((real - hist) ** 2).sum(), 4),
                      "oosR2OfTrailing126AsForecast": r6(1 - ((real - f[f"tr126_{k}"].to_numpy()) ** 2).sum() / ((real - hist) ** 2).sum(), 4),
                      "corrPredRealised": r6(np.corrcoef(pred, real)[0, 1], 4), "predSd": r6(pred.std(), 5), "realisedSd": r6(real.std(), 5),
                      "meanSe": r6(f[f"se_{k}"].mean(), 5)}
        n = f["n"].to_numpy()
        out[kind] = {"decisions": int(len(f)), "oos": oos,
                     "rankSkill63dLabel": rank_skill("mu", "y63"), "rankSkillHoldingPeriod20d": rank_skill("mu", "y20"),
                     "trailing126AsForecastRankSkill63d": rank_skill("tr126", "y63"), "trailing126AsForecastRankSkill20d": rank_skill("tr126", "y20"),
                     "trainingLabels": {"first": int(n.min()), "last": int(n.max()), "effectiveFirst": r6(n.min() * 20 / 63, 1),
                                        "effectiveLast": r6(n.max() * 20 / 63, 1),
                                        "features": len(C.ALL_STATES if "ALL" in kind else C.KR_STATES) + 2}}
    # counterfactual allocation rules applied to the SAME stored B1 forecasts (no refit): which part of the pipeline lost money
    dg = R["diags"]["B1_RIDGE_ALL_STATES"]
    cf = {"RAW_ARGMAX_IF_POSITIVE": {}, "NO_SHRINK_WITH_HURDLE": {}, "SHRINK_NO_HURDLE": {}, "AS_PUBLISHED_NO_BAND": {}}
    for d, g in dg.items():
        if "mu" not in g:
            for k in cf:
                cf[k][d] = {"S0_ETF": 1.0}
            continue
        best = max(g["mu"], key=g["mu"].get)
        cf["RAW_ARGMAX_IF_POSITIVE"][d] = {best: 1.0} if g["mu"][best] > 0 else {"S0_ETF": 1.0}
        cf["NO_SHRINK_WITH_HURDLE"][d] = C.learned_weights(g["mu"], {k: 0.0 for k in g["mu"]}, C.round_trip_hurdle(d))[0]
        cf["SHRINK_NO_HURDLE"][d] = C.learned_weights(g["mu"], g["se"], 0.0)[0]
        cf["AS_PUBLISHED_NO_BAND"][d] = C.learned_weights(g["mu"], g["se"], C.round_trip_hurdle(d))[0]
    res = {}
    for k, ws in cf.items():
        books = {d: C.combine({s: R["books"][s][d] for s in w}, w) for d, w in ws.items()}
        nav = C.simulate(ctx.px, books_to_schedule(books, sess), R["start"], R["end"])["nav"]
        m = C.metrics(nav, R["bench"], ctx.I["rf"])
        res[k] = {"cagr": r6(m["cagr"]), "excessCagr": r6(m["excessCagr"]), "sharpe": r6(m["sharpe"], 4), "mdd": r6(m["mdd"], 4),
                  "meanRiskyWeight": r6(np.mean([1 - w.get("S0_ETF", 0.0) for w in ws.values()]), 4)}
    out["allocationCounterfactualsOnStoredB1Forecasts"] = res
    n_dec = len(R["evalDates"])
    for h in (21, 63, 126):
        neff = n_dec * min(1.0, 20 / h)
        tcrit_raw, tcrit_by = 1.96, 3.97
        out.setdefault("power", {})[f"H{h}"] = {"decisions": n_dec, "overlapAdjustedEffectiveN": r6(neff, 1),
                                                "minDetectableAbsCorrRaw05": r6(tcrit_raw / math.sqrt(neff), 3),
                                                "minDetectableAbsCorrBY228q10": r6(tcrit_by / math.sqrt(neff), 3)}
    return out


# =========================================================================== #
# Source readiness (what would have to be certified to turn the conditional numbers into shareholder returns)
# =========================================================================== #
def vendor_events(scratch):
    """Vendor dividend / split flags from the same replay-v16 price objects the closes came from (flags, not certified events)."""
    sys.path.insert(0, str(ROOT))
    from pipeline import kr_model_portfolio_execution as X
    from pipeline import kr_model_raw_snapshot as K
    _, _, _, prices = X.load_sources(Path(scratch) / "raw", K.frozen_spec())
    ev = []
    for t, f in prices.items():
        cols = {c.lower().replace(" ", ""): c for c in f.columns}
        dcol, scol = cols.get("dividends"), cols.get("stocksplits")
        if dcol is None and scol is None:
            continue
        g = f.copy()
        g.index = pd.to_datetime(g.index)
        m = pd.Series(False, index=g.index)
        if dcol:
            m |= g[dcol].fillna(0) != 0
        if scol:
            m |= (g[scol].fillna(0) != 0) & (g[scol].fillna(0) != 1)
        for d, r in g[m].iterrows():
            ev.append({"ticker": t, "date": d, "dividend": float(r[dcol]) if dcol else 0.0, "split": float(r[scol]) if scol else 0.0})
    return pd.DataFrame(ev)


def source_readiness(legs, events):
    out = {}
    for pol, g in legs.groupby("policy"):
        stock = g[~g["asset"].isin([M.ETF, M.CASH])].reset_index(drop=True)
        stock["alpha"] = stock["INDUSTRY_ALPHA"] + stock["SELECTION_ALPHA"]
        hits = []
        if not events.empty:
            ev = events.set_index("ticker")
            for _, r in stock.iterrows():
                if r["asset"] in ev.index:
                    e = ev.loc[[r["asset"]]]
                    inside = e[(e["date"] > r["execution"]) & (e["date"] <= r["periodEnd"])]
                    for _, z in inside.iterrows():
                        hits.append({"ticker": r["asset"], "eventDate": str(z["date"].date()), "dividend": z["dividend"], "split": z["split"],
                                     "phase": int(r["phase"]), "execution": str(r["execution"].date()), "weight": r6(r["weight"], 4),
                                     "legExcess": r6(r["excess"]), "legAlpha": r6(r["alpha"])})
        tot = stock["alpha"].abs().sum()
        ranked = stock.reindex(stock["alpha"].abs().sort_values(ascending=False).index)
        cum = ranked["alpha"].abs().cumsum() / tot if tot > 0 else ranked["alpha"] * 0
        k50 = int((cum < 0.5).sum() + 1)
        out[pol] = {"stockLegs": int(len(stock)), "distinctTickers": int(stock["asset"].nunique()),
                    "legsCarrying50pctOfAbsAlpha": k50,
                    "top10Legs": [{"ticker": r["asset"], "phase": int(r["phase"]), "execution": str(r["execution"].date()), "industry": r["industry"],
                                   "alpha": r6(r["alpha"]), "weight": r6(r["weight"], 4)} for _, r in ranked.head(10).iterrows()],
                    "vendorFlaggedEventsInsideHeldWindows": len(hits),
                    "distinctTickersWithFlaggedEvents": len({h["ticker"] for h in hits}),
                    "flaggedEvents": sorted(hits, key=lambda h: -abs(h["legAlpha"] or 0))[:60]}
    return out


# =========================================================================== #
# Main
# =========================================================================== #
def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--scratch", required=True)
    ap.add_argument("--skip-bridge", action="store_true")
    ap.add_argument("--from-state", action="store_true", help="re-write outputs from the checkpoint of a completed computation")
    a = ap.parse_args(argv)
    t0 = time.time()
    state = Path(a.scratch) / "amd-state.pkl"
    if a.from_state:
        write_outputs(**pd.read_pickle(state))
        return
    I = load(a.scratch)
    ctx = Ctx(I)
    ref = json.loads((HERE / "results/reference-329-extract.json").read_text())

    phases = {p: run_phase(I, p) for p in range(4)}
    R0 = phases[0]
    # ---- reproduction gate ----------------------------------------------------------------------------------------------- #
    repro = {}
    for name, ref_perf in ref["performance"].items():
        if name not in R0["sims"]:
            continue
        m = C.metrics(R0["sims"][name]["nav"], R0["bench"], I["rf"])
        repro[name] = {"published": ref_perf["cagr"], "reproduced": r6(m["cagr"]), "absDiff": r6(abs(m["cagr"] - ref_perf["cagr"]), 9)}
    phase_repro = {}
    for p in range(4):
        pub = ref["postHoc"]["rebalancePhase"]["byPhase"][str(p)]
        for name in (SMS, "S1_INDUSTRY_MOMENTUM", "S2_VALUE_CONFIRMED", "STATIC_EW4"):
            m = C.metrics(phases[p]["sims"][name]["nav"], phases[p]["bench"], I["rf"])
            phase_repro[f"{p}:{name}"] = {"published": pub[name]["cagr"], "reproduced": r6(m["cagr"]), "absDiff": r6(abs(m["cagr"] - pub[name]["cagr"]), 9)}
    worst = max(v["absDiff"] for v in list(repro.values()) + list(phase_repro.values()))
    status = "REPRODUCED" if worst <= 1e-6 else ("REPRODUCED_WITHIN_TOLERANCE" if worst <= 1e-4 else "NOT_REPRODUCED")
    print(json.dumps({"reproduction": status, "worstAbsDiff": worst}), flush=True)
    if status == "NOT_REPRODUCED":
        (HERE / "results").mkdir(exist_ok=True)
        (HERE / "results/verification.json").write_text(json.dumps(clean({"evidenceClass": EVIDENCE, "reproduction": {"status": status, "cagr": repro,
                                                                                                                      "byPhase": phase_repro}}), indent=1))
        raise SystemExit("REPRODUCTION_FAILED: no decomposition is read on a path that does not reproduce #329")

    # ---- H1 ---------------------------------------------------------------------------------------------------------- #
    H1, legs_all, per_all = {}, [], []
    for p, R in phases.items():
        out, legs, per = h1(ctx, R, p)
        H1[p] = out
        legs_all.append(legs)
        per_all.append(per)
        print(f"H1 phase {p}: SMS net {out[SMS]['netCagr']:.4f} ind {out[SMS]['INDUSTRY_ALPHA']:.4f} sel {out[SMS]['SELECTION_ALPHA']:.4f} "
              f"beta {out[SMS]['MARKET_BETA']:.4f}", flush=True)
    sens = {}
    E = run_phase(I, 0, exclude=POST_HOC_INDUSTRIES)
    out_e, legs_e, _ = h1(ctx, E, 0)
    sens["excludeDefenseElectronicsPhase0"] = {k: {m: out_e[k][m] for m in ("netCagr", "netExcessCagr", "MARKET_BETA", "INDUSTRY_ALPHA", "SELECTION_ALPHA",
                                                                           "compoundingNet", "COST")} for k in (SMS, "STATIC_EW4") + tuple(SLEEVES)}
    sens["excludeDefenseElectronicsPhase0"]["_sleeveLayer"] = {"choiceValueExcess": out_e["_sleeveLayer"]["choiceValue"]["excess"],
                                                               "permutationNull": out_e["_sleeveLayer"]["permutationNull"]}
    K2 = run_phase(I, 0, cost_mult=2.0)
    sens["costX2Phase0"] = {k: r6(C.metrics(K2["sims"][k]["nav"], K2["bench"], I["rf"])["cagr"]) for k in (SMS, "STATIC_EW4", "S0_ETF") + tuple(SLEEVES)}
    tranche = pd.concat([phases[p]["sims"][SMS]["nav"].pct_change() for p in range(4)], axis=1).dropna().mean(axis=1)
    tranche_ew = pd.concat([phases[p]["sims"]["STATIC_EW4"]["nav"].pct_change() for p in range(4)], axis=1).dropna().mean(axis=1)
    tn = (1 + tranche).cumprod()
    m_t = C.metrics(tn / tn.iloc[0], R0["bench"].reindex(tn.index) / R0["bench"].reindex(tn.index).iloc[0], I["rf"])
    sens["fourTrancheStaggeredSMS"] = {"note": "daily average of the four phase books (each 25%, independently rebalanced) — the phase-free version of the "
                                               "same rule, POST_HOC", "cagr": r6(m_t["cagr"]), "excessCagr": r6(m_t["excessCagr"]), "sharpe": r6(m_t["sharpe"], 4),
                                       "mdd": r6(m_t["mdd"], 4), "vsFourTrancheEW4": C.block_bootstrap(tranche - tranche_ew),
                                       "vsETF": C.block_bootstrap(tranche - R0["bench"].pct_change().reindex(tranche.index))}
    print("sensitivities done", flush=True)

    # ---- industry momentum diagnostics ---------------------------------------------------------------------------------- #
    F = industry_forward(ctx)
    two = F["industry"].isin(POST_HOC_INDUSTRIES)
    y25 = F["date"].dt.year == 2025
    ind_stats = []
    for h in (20, 63):
        ind_stats.append(industry_ic(F, h, None, "ALL"))
        ind_stats.append(industry_ic(F, h, ~two, "EXCL_DEFENSE_ELECTRONICS"))
        ind_stats.append(industry_ic(F, h, ~y25, "EXCL_2025_SIGNALS"))
        ind_stats.append(industry_ic(F, h, ~two & ~y25, "EXCL_BOTH"))
        ind_stats.append(industry_ic(F, h, F["date"] < pd.Timestamp("2018-01-01"), "2014_2017"))
        ind_stats.append(industry_ic(F, h, F["date"] >= pd.Timestamp("2018-01-01"), "2018_2026"))
        for y in sorted(F["date"].dt.year.unique()):
            ind_stats.append(industry_ic(F, h, F["date"].dt.year == y, f"YEAR_{y}"))
    within = within_industry_ic(ctx, 20)
    s1legs = pd.concat(legs_all)
    entry = {p: entry_timing(s1legs[(s1legs["policy"] == "S1_INDUSTRY_MOMENTUM") & (s1legs["phase"] == p)]) for p in range(4)}
    print("industry diagnostics done", flush=True)

    # ---- H2 / H3 variants -------------------------------------------------------------------------------------------------- #
    s2_rows, s2_pairs, s2_extra, var_legs, s1_rows, s1_pairs = [], {}, {}, [], [], {}
    for p, R in phases.items():
        rows, legs, pairs, extra = h2(ctx, R, p)
        s2_rows += rows
        s2_pairs[p] = pairs
        s2_extra[p] = extra
        var_legs.append(legs)
        rows, legs, pairs = h3_variants(ctx, R, p)
        s1_rows += rows
        s1_pairs[p] = pairs
        var_legs.append(legs)
    print("variants done", flush=True)
    br = None if a.skip_bridge else bridge(ctx, I)
    print("bridge done", flush=True)
    H4 = h4(ctx, R0)
    print("h4 done", flush=True)

    # ---- outputs ---------------------------------------------------------------------------------------------------------- #
    legs = pd.concat(legs_all + [legs_e.assign(policy=lambda x: x["policy"] + "@EXCL_DEFENSE_ELECTRONICS")])
    per = pd.concat(per_all)
    try:
        events = vendor_events(a.scratch)
    except Exception as exc:  # noqa: BLE001 — the readiness file says the flags could not be read; nothing else depends on them
        events = pd.DataFrame()
        print("vendor events unavailable:", exc)
    I["terminalHits"] = sorted(set(map(tuple, ctx.pp.hits)))
    pd.to_pickle(dict(H1=H1, sens=sens, legs=legs, per=per, F=F, ind_stats=ind_stats, within=within, entry=entry, s2_rows=s2_rows, s2_pairs=s2_pairs,
                      s2_extra=s2_extra, s1_rows=s1_rows, s1_pairs=s1_pairs, br=br, H4=H4, events=events), Path(a.scratch) / "amd-partial.pkl")
    ready = source_readiness(legs[legs["policy"].isin([SMS, "S1_INDUSTRY_MOMENTUM", "S2_VALUE_CONFIRMED"])], events)
    kw = dict(I={k: v for k, v in I.items() if k in ("ident", "terminalHits")}, H1=H1, sens=sens, legs=legs, per=per, F=F, ind_stats=ind_stats,
              within=within, entry=entry, s2_rows=s2_rows, s2_pairs=s2_pairs, s2_extra=s2_extra, s1_rows=s1_rows, s1_pairs=s1_pairs, br=br, H4=H4,
              var_legs=pd.concat(var_legs), ready=ready, events=events, status=status, repro=repro, phase_repro=phase_repro, worst=worst, ref=ref, secs=time.time() - t0)
    pd.to_pickle(kw, state)
    write_outputs(**kw)


def write_outputs(I, H1, sens, legs, per, F, ind_stats, within, entry, s2_rows, s2_pairs, s2_extra, s1_rows, s1_pairs, br, H4, var_legs, ready, events,
                  status, repro, phase_repro, worst, ref, secs):
    res = HERE / "results"
    res.mkdir(exist_ok=True)
    V = var_legs.reindex(columns=["policy", "phase", "date", "execution", "periodEnd", "asset", "industry", "weight", "beta", "beta_ind", "R", "R_ind",
                                  "R_m", "R_f", "MARKET_BETA", "INDUSTRY_ALPHA", "SELECTION_ALPHA", "excess"]).copy()
    for c in ("date", "execution", "periodEnd"):
        V[c] = pd.to_datetime(V[c]).dt.strftime("%Y-%m-%d")
    V[V.select_dtypes("number").columns] = V.select_dtypes("number").round(8)
    with open(res / "variant-legs.csv.gz", "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=9, mtime=0) as fh:
        fh.write(V.sort_values(["policy", "phase", "execution", "asset"]).to_csv(index=False).encode())
    cols = ["policy", "phase", "date", "execution", "periodEnd", "sleeve", "asset", "industry", "weight", "beta", "beta_ind", "R", "R_ind", "R_m", "R_f",
            "MARKET_BETA", "INDUSTRY_ALPHA", "SELECTION_ALPHA", "excess", "industryMembers"]
    L = legs.reindex(columns=cols).copy()
    for c in ("date", "execution", "periodEnd"):
        L[c] = pd.to_datetime(L[c]).dt.strftime("%Y-%m-%d")
    P = per.copy()
    P["execution"] = pd.to_datetime(P["execution"]).dt.strftime("%Y-%m-%d")
    P["periodEnd"] = pd.to_datetime(P["periodEnd"]).dt.strftime("%Y-%m-%d")
    pr = P.melt(id_vars=["policy", "phase", "execution", "periodEnd"], value_vars=["MECHANICS", "COST"], var_name="asset", value_name="excess")
    pr["asset"] = "__" + pr["asset"] + "__"
    L = pd.concat([L, pr.reindex(columns=cols)], ignore_index=True)
    L["evidenceClass"], L["returnBasis"] = EVIDENCE, RETURN_BASIS
    num = L.select_dtypes("number").columns
    L[num] = L[num].round(8)
    L.sort_values(["policy", "phase", "execution", "asset"]).to_csv(HERE / "mechanism-attribution.csv", index=False)

    S2 = pd.DataFrame(s2_rows)
    S2["evidenceClass"], S2["returnBasis"] = EVIDENCE, RETURN_BASIS
    S2.round(6).to_csv(HERE / "s2-ablation.csv", index=False)

    Fi = F.copy()
    Fi["date"] = Fi["date"].dt.strftime("%Y-%m-%d")
    S1 = pd.DataFrame(s1_rows).assign(table="S1_VARIANT")
    stats = pd.DataFrame([{"table": "INDUSTRY_IC", "label": s["label"], "horizon": s["horizon"], "dates": s["dates"], "meanRankIc": s["meanRankIc"],
                           "icT": s["icHac"].get("t"), "topIndustryMinusIndustryMean": s["topIndustryMinusIndustryMean"], "spreadT": s["spreadHac"].get("t"),
                           "topIndustryHitRate": s["topIndustryHitRate"]} for s in ind_stats])
    phase_year = []
    for p in range(4):
        for y, row in H1[p]["S1_INDUSTRY_MOMENTUM"]["byYear"].items():
            phase_year.append({"table": "S1_PHASE_YEAR", "phase": p, "year": y, **row})
    bridge_rows = [{"table": "BRIDGE_GRID", **{k: v for k, v in g.items() if k != "yearly"}} for g in (br["grid"] if br else [])]
    D = pd.concat([stats, pd.DataFrame(phase_year), S1, pd.DataFrame(bridge_rows), Fi], ignore_index=True)
    D["evidenceClass"], D["returnBasis"] = EVIDENCE, RETURN_BASIS
    num = D.select_dtypes("number").columns
    D[num] = D[num].round(6)
    D.to_csv(HERE / "industry-momentum-diagnostics.csv", index=False)

    summary = {"studyId": "alpha-mechanism-decomposition-v1", "evidenceClass": EVIDENCE, "returnBasis": RETURN_BASIS,
               "h1": {str(p): H1[p] for p in H1}, "h1Sensitivities": sens, "industryMomentum": {"stats": ind_stats, "withinIndustryA09": within,
                                                                                            "defenseElectronicsEntry": entry},
               "s2": {"pairs": {str(p): v for p, v in s2_pairs.items()}, "extra": {str(p): v for p, v in s2_extra.items()}},
               "s1Variants": {"pairs": {str(p): v for p, v in s1_pairs.items()}}, "bridge": br, "h4": H4}
    (res / "summary.json").write_text(json.dumps(clean(summary), indent=1, ensure_ascii=False) + "\n")
    readiness = {"studyId": "alpha-mechanism-decomposition-v1", "evidenceClass": EVIDENCE,
                 "returnBasis": RETURN_BASIS,
                 "status": {"KR_ETF_069500_CASH_ACCOUNT": "VERIFIED_IN_#332_FOR_2016-01-11..2026-09-14 (not recomputed here)",
                            "KR_STOCK_STRATEGY_PATHS": "CONDITIONAL — replay-v16 total-return index; #332 strict admission SOURCE_BLOCKED from the first unresolved "
                                                       "event; every stock number in this study is a conditional decomposition",
                            "KR_STATE_MACRO_INPUTS": "CONDITIONAL — repository lag rules, FRED values not vintage-certified",
                            "TERMINAL_CONSIDERATION": "NOT_EXERCISED — zero terminal hits on every decomposed 2018-2026 path"},
                 "vendorEventFlagsRead": int(len(events)),
                 "engineResidualEvents": [e for p in H1 for e in H1[p]["_mechanicsEvents"]],
                 "minimumRecoveryTargets": ready,
                 "note": "A vendor dividend/split flag inside a held window is the minimum set of (ticker, date) events whose official cash/share package must be "
                         "verified to certify that leg; the flag list is not a completeness certificate (unflagged actions may exist)."}
    (HERE / "source-readiness.json").write_text(json.dumps(clean(readiness), indent=1, ensure_ascii=False) + "\n")
    closure = []
    for p in H1:
        for name, s in H1[p].items():
            if name.startswith("_"):
                continue
            closure.append(abs(s["netExcessCagr"] - (s["MARKET_BETA"] + s["INDUSTRY_ALPHA"] + s["SELECTION_ALPHA"] + s["MECHANICS"] + s["COST"] + s["compoundingNet"])))
    files = {n: hashlib.sha256((HERE / n).read_bytes()).hexdigest() for n in ("mechanism-attribution.csv", "s2-ablation.csv",
                                                                              "industry-momentum-diagnostics.csv", "source-readiness.json")}
    files["results/summary.json"] = hashlib.sha256((res / "summary.json").read_bytes()).hexdigest()
    ver = {"studyId": "alpha-mechanism-decomposition-v1", "evidenceClass": EVIDENCE, "returnBasis": RETURN_BASIS,
           "inputs": I["ident"], "reproduction": {"status": status, "worstAbsCagrDiff": worst, "cagrPhase0": repro, "cagrByPhase": phase_repro,
                                                  "reference": ref["source"]},
           "accounting": {"attributionIdentityMaxResidual": float(legs["residual"].abs().max()), "identityTolerance": M.IDENTITY_TOL,
                          "netGapClosureMaxResidual": max(closure), "nanReturnLegs": int(legs["R"].isna().sum()),
                          "mechanicsResidualAbsMaxPerPeriod": float(per["MECHANICS"].abs().max()),
                          "periodTerminalWriteOffs": I.get("terminalHits")},
           "pit": {"featureSource": "Phase B matrix digest " + I["ident"].get("matrixDigest", ""), "beta": "F03_beta252 at the signal date (trailing 252 sessions, ends at signal date)",
                   "industry": "PIT industry label on the signal date; basket = cap-weighted quality-eligible members on the signal date, market cap from the PIT universe snapshot the membership used (pitSnapshotDate < signal date)",
                   "forwardReturns": "read only for attribution after the decision; never fed back into a choice"},
           "tests": "tests/test_alpha_mechanism_decomposition_v1.py", "runtimeSeconds": round(secs, 1), "outputSha256": files}
    (res / "verification.json").write_text(json.dumps(clean(ver), indent=1, ensure_ascii=False) + "\n")
    print(json.dumps({"written": list(files), "seconds": round(secs, 1)}))


if __name__ == "__main__":
    main()
