"""KR alpha discovery tournament v1 — assembling one run: labels, the four translators, the configuration universe, the evidence and the verdict.

The same functions serve the synthetic readiness world and the single real execution; only the data adapters differ. `build_labels`, `run_paths`,
`configuration_universe` and `assemble` read OUTCOMES and are reached in the real run only behind the permit and the durable lock.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy.stats import rankdata

from . import kr_alpha_tournament as T
from . import kr_alpha_tournament_evaluation as E
from . import kr_alpha_tournament_features as F
from . import kr_alpha_tournament_portfolio as P
from . import kr_alpha_tournament_walkforward as W
from . import kr_stock_within_industry_anatomy as S

TRANSLATORS = ("PRIMARY_ROBUST_KELLY", "BASELINE_1_EQUAL_WEIGHT_SLEEVE", "DECISION_FOCUSED_CHALLENGER", "BASELINE_0_PASSIVE")


# --------------------------------------------------------------------------- #
# Labels (OUTCOME)
# --------------------------------------------------------------------------- #
def forward_return(close_at, calendar, ticker, signal, horizon, through):
    """(entry, exit, return or None, status) with target_from_sessions semantics: entry = next session close, exit = horizon sessions later."""
    pos = calendar.pos_on_or_before(signal)
    if pos + 1 + horizon >= len(calendar.days):
        return None, None, None, "PENDING"
    entry, exit_ = calendar.days[pos + 1], calendar.days[pos + 1 + horizon]
    if exit_ > through:
        return entry, exit_, None, "PENDING"
    a, z = close_at(ticker, entry), close_at(ticker, exit_)
    if a is None or z is None or not np.isfinite([a, z]).all() or min(a, z) <= 0:
        return entry, exit_, None, "UNRESOLVED"
    return entry, exit_, float(z / a - 1.0), "MATURED"


def build_labels(rows, calendar, close_at, through, ineligible=frozenset(), counters=None):
    """`rows`: signal-time frame (date, ticker, industry, industryEligible, marketCap). Returns one label row per input row.
    eligible = MATURED stock AND benchmark H126 endpoints and (date, ticker) not in `ineligible` (the terminal-discipline exclusions)."""
    out = []
    for date, group in rows.groupby("date", sort=True):
        rb_entry, rb_exit, rb, rb_status = forward_return(close_at, calendar, T.BENCHMARK, date, T.PRIMARY_HORIZON, through)
        _, _, rb21, _ = forward_return(close_at, calendar, T.BENCHMARK, date, T.INNER_BLOCK_HORIZON, through)
        _, _, rb252, _ = forward_return(close_at, calendar, T.BENCHMARK, date, T.SECONDARY_HORIZON, through)
        recs = []
        for row in group.sort_values("ticker").itertuples(index=False):
            entry, exit_, r, status = forward_return(close_at, calendar, row.ticker, date, T.PRIMARY_HORIZON, through)
            _, _, r21, _ = forward_return(close_at, calendar, row.ticker, date, T.INNER_BLOCK_HORIZON, through)
            _, _, r252, _ = forward_return(close_at, calendar, row.ticker, date, T.SECONDARY_HORIZON, through)
            if counters is not None:
                counters["labelBuilds"] = counters.get("labelBuilds", 0) + 1
            ok = status == "MATURED" and rb_status == "MATURED" and (date, row.ticker) not in ineligible
            recs.append({"date": date, "ticker": row.ticker, "entryDate": entry, "exitDate": exit_ if status != "PENDING" else None,
                         "status": status, "eligible": ok, "stock": r if ok else np.nan, "yEcon": r - rb if ok else np.nan,
                         "r21Stock": r21 if r21 is not None else np.nan, "r21Bench": rb21 if rb21 is not None else np.nan,
                         "stock252": r252 if r252 is not None else np.nan, "bench252": rb252 if rb252 is not None else np.nan,
                         "industry": row.industry, "industryEligible": bool(row.industryEligible), "marketCap": row.marketCap})
        frame = pd.DataFrame(recs)
        el = frame["eligible"].to_numpy(bool)
        stock = frame["stock"].to_numpy(float)
        rank = np.full(len(frame), np.nan)
        if el.sum() >= T.MIN_NAMES_PER_LABEL_DATE:
            rank[el] = (rankdata(stock[el]) - 0.5) / el.sum()
        frame["C_CROSS_SECTIONAL_RANK"] = rank - 0.5
        frame["D_TOP_QUINTILE_EVENT"] = np.where(np.isfinite(rank), (rank > 0.8).astype(float), np.nan)
        caps = frame["marketCap"].to_numpy(float)
        a = np.full(len(frame), np.nan)
        for i in np.flatnonzero(el):
            others = el.copy()
            others[i] = False
            others &= np.isfinite(caps) & (caps > 0)
            if others.sum() >= T.TARGETS["A_MAGNITUDE_VS_SAME_DATA_UNIVERSE"]["minimumOtherNames"]:
                a[i] = stock[i] - float(np.dot(caps[others], stock[others]) / caps[others].sum())
        frame["A_MAGNITUDE_VS_SAME_DATA_UNIVERSE"] = a
        frame["B_RESIDUAL_VS_LOO_INDUSTRY"] = _loo_industry(frame)
        s252 = frame["stock252"].to_numpy(float)
        ok252 = np.isfinite(s252) & el
        r252 = np.full(len(frame), np.nan)
        if ok252.sum() >= T.MIN_NAMES_PER_LABEL_DATE:
            r252[ok252] = (rankdata(s252[ok252]) - 0.5) / ok252.sum() - 0.5
        frame["C252"] = r252
        out.append(frame)
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame(columns=["date", "ticker", *W.LABEL_COLUMNS])


def _loo_industry(frame):
    """The sealed leave-one-out industry residual (cap-weighted lens); cohorts are the date's eligible-industry members."""
    out = np.full(len(frame), np.nan)
    members = frame[frame.industryEligible & frame.industry.notna()]
    for industry, group in members.groupby("industry"):
        names = sorted(group.ticker)
        cohort = {"members": names, "n": len(names), "status": "ELIGIBLE" if len(names) >= S.MIN_INDUSTRY_MEMBERS else "INELIGIBLE"}
        forward = {r.ticker: (r.stock if r.eligible else np.nan, 0.0, "MATURED" if r.eligible else "UNRESOLVED") for r in group.itertuples()}
        caps = dict(zip(group.ticker, group.marketCap))
        for r in group.itertuples():
            t = S.stock_targets(r.ticker, cohort, forward, caps)["CAP_WEIGHTED"]
            if t["status"] == "MATURED":
                out[r.Index] = t["components"]["STOCK_MINUS_LOO_INDUSTRY"]
    return out


# --------------------------------------------------------------------------- #
# Translators (decision callbacks for the ledger)
# --------------------------------------------------------------------------- #
def make_decider(kind, forecasts, data, risk, stress=1.0, adv_multiplier=1.0, cfg=T.PORTFOLIO, counters=None):
    rep = data["rep"]

    def decide(day, weights, nav_krw):
        f = forecasts.get(day)
        if f is None or kind == "BASELINE_0_PASSIVE":
            return None
        if not f.get("available"):
            return None                                     # no valid signal-time cross-section: hold the book (no trade)
        if "muPost" not in f and kind != "DECISION_FOCUSED_CHALLENGER":
            return {}                                       # passive default: no stable candidate this outer year
        rows = rep.iloc[f["rows"]]
        r = risk(f["signal"])
        pos = {t: i for i, t in enumerate(r["tickers"])}
        signal = f["muPost"] if "muPost" in f else np.zeros(len(rows))
        ok = (rows["tradable"].astype(bool).to_numpy() & (rows["adv60"].to_numpy(float) >= cfg["minimumAdvKrw"])
              & np.isfinite(signal) & rows["ticker"].isin(pos).to_numpy())
        tick = rows["ticker"].to_numpy()[ok]
        w0 = np.array([weights.get(t, 0.0) for t in tick])
        lower, upper = P.trade_box(w0, rows["adv60"].to_numpy(float)[ok], nav_krw, cfg, adv_multiplier)
        cb, cs = P.unit_costs(stress)
        if kind == "PRIMARY_ROBUST_KELLY":
            idx = [pos[t] for t in tick]
            w, _ = P.allocate(signal[ok], r["cov"][np.ix_(idx, idx)], r["ceb"][idx], w0, cb, cs, lower, upper)
        elif kind == "BASELINE_1_EQUAL_WEIGHT_SLEEVE":
            w = P.baseline_equal_weight(signal[ok], cb, cs, lower, upper)
        else:
            w = np.clip(f["dflWeights"][ok], lower, upper)
            if w.sum() > 1:
                w = w / w.sum()
        if counters is not None:
            counters["allocatorSolves"] = counters.get("allocatorSolves", 0) + 1
        return {t: float(v) for t, v in zip(tick, w) if v > 0}
    return decide


def run_paths(forecasts, data, risk, days, start, end, mark, executable, adv_of, counters=None):
    """Every translator at base costs, and the primary under each registered stress. Paths are valued daily by the same ledger."""
    out = {}
    for kind in TRANSLATORS:
        if counters is not None:
            counters["ledgerReplays"] = counters.get("ledgerReplays", 0) + 1
        out[(kind, "BASE")] = P.replay(days, start, end, mark, executable, adv_of, make_decider(kind, forecasts, data, risk, counters=counters))
    for name, stress in T.STRESSES.items():
        if name == "BASE":
            continue
        if counters is not None:
            counters["ledgerReplays"] = counters.get("ledgerReplays", 0) + 1
        decider = make_decider("PRIMARY_ROBUST_KELLY", forecasts, data, risk, stress["costMultiplier"], stress["advFractionMultiplier"], counters=counters)
        out[("PRIMARY_ROBUST_KELLY", name)] = P.replay(days, start, end, mark, executable, adv_of, decider, stress=stress["costMultiplier"],
                                                       delay=stress["executionDelaySessions"])
    return out


def configuration_universe(forecasts, labels):
    """(anchors x configurations) gross active block returns of the cheap translator: equal-weight top quintile of each configuration's native
    score, held 21 sessions from the signal's entry, minus 069500.KS. Gives PBO / DSR / SPA a universe; never selects anything."""
    days = sorted(d for d in forecasts if forecasts[d].get("universeScores"))
    ids = sorted({cid for d in days for cid in forecasts[d]["universeScores"]})
    matrix = np.full((len(days), len(ids)), np.nan)
    r21 = labels["r21Stock"].to_numpy(float)
    b21 = labels["r21Bench"].to_numpy(float)
    for i, d in enumerate(days):
        f = forecasts[d]
        rows = f["rows"]
        realised = np.isfinite(r21[rows])
        bench = b21[rows][np.isfinite(b21[rows])]
        if not realised.any() or not len(bench):
            continue
        for j, cid in enumerate(ids):
            score = f["universeScores"].get(cid)
            if score is None:
                continue
            pct = (rankdata(score) - 0.5) / len(score)
            top = (pct > 0.8) & realised
            if top.any():
                active = float(np.mean(r21[rows][top])) - float(bench[0])
                matrix[i, j] = math.log1p(float(bench[0]) + active) - math.log1p(float(bench[0]))
    return ids, matrix


def assemble(process, paths, labels, signal_coverage_percent, identity_unchanged=True):
    """Every registered statistic and the frozen verdict, from the finished process and valued paths."""
    passive = paths[("BASELINE_0_PASSIVE", "BASE")]
    result = {"paths": {}, "complete": {}}
    complete = all(p["complete"] for p in paths.values())
    for (kind, stress), p in sorted(paths.items()):
        result["complete"][kind + ":" + stress] = p["complete"]
        if p["complete"]:
            result["paths"][kind + ":" + stress] = E.path_metrics(p["path"])
    cb, cs = P.unit_costs()
    prediction = E.prediction_diagnostics(process["anchors"], labels, cb + cs, secondary_column="C252")
    evidence = {"integrity": {"pathsComplete": complete, "identityUnchanged": identity_unchanged, "signalCoveragePercent": signal_coverage_percent},
                "gPp": None, "bootstrapLower": None, "gCostX2Pp": None, "periodsPositive": None, "gLeaveLargestOutPp": None, "dsr": None,
                "spaP": None, "pbo": None, "icLower95": prediction["rankIc"]["lower95"]}
    comparisons = {}
    if complete:
        primary = paths[("PRIMARY_ROBUST_KELLY", "BASE")]
        days, diff = E.log_growth_difference(primary["path"], passive["path"])
        g = E.annualised_pp(diff)
        slices = E.period_slices(days, diff)
        for (kind, stress), p in sorted(paths.items()):
            if kind != "BASELINE_0_PASSIVE":
                comparisons[kind + ":" + stress] = E.annualised_pp(E.log_growth_difference(p["path"], passive["path"])[1])
        boot = E.moving_block_bootstrap(diff)
        llo = E.leave_largest_contributor_out(g, primary["contributions"], len(diff))
        ids, universe = configuration_universe(process["anchors"], labels)
        primary_blocks = E.blocks(diff)
        trial_sharpes = [float(np.nanmean(c) / np.nanstd(c, ddof=1)) for c in universe.T if np.isfinite(c).sum() > 2 and np.nanstd(c, ddof=1) > 0]
        ledger = T.trial_ledger(len(process["folds"]))
        dsr = E.deflated_sharpe(primary_blocks, trial_sharpes, ledger["totalEffectiveTrials"])
        n = min(len(primary_blocks), universe.shape[0])
        strategy_blocks = [E.blocks(E.log_growth_difference(paths[(k, "BASE")]["path"], passive["path"])[1])[:n]
                           for k in ("PRIMARY_ROBUST_KELLY", "BASELINE_1_EQUAL_WEIGHT_SLEEVE", "DECISION_FOCUSED_CHALLENGER")]
        spa_all = E.spa_test(np.column_stack(strategy_blocks + [universe[:n]]) if n else np.zeros((0, 0)))
        spa_primary = E.spa_test(strategy_blocks[0][:, None]) if n else {"status": "TOO_SHORT", "pValue": None}
        pbo = E.pbo_cscv(universe)
        evidence.update(gPp=g, bootstrapLower=boot["lower95"], gCostX2Pp=comparisons.get("PRIMARY_ROBUST_KELLY:COST_X2"),
                        periodsPositive=sum(1 for s in slices.values() if s["gPp"] is not None and s["gPp"] > 0), gLeaveLargestOutPp=llo["gPp"],
                        dsr=dsr.get("dsr"), spaP=spa_primary.get("pValue"), pbo=pbo.get("pbo"))
        result.update(gPp=g, periods=slices, bootstrap=boot, leaveLargestContributorOut=llo, deflatedSharpe=dsr, spaPrimary=spa_primary,
                      spaUniverse=spa_all, pbo=pbo, comparisonsVsPassivePp=comparisons, universeConfigurations=len(ids),
                      optimizerValueVsBaseline1Pp=(g - comparisons["BASELINE_1_EQUAL_WEIGHT_SLEEVE:BASE"]) if g is not None else None)
    result.update(prediction=prediction, evidence=evidence, verdict=E.verdict(evidence))
    return result


# --------------------------------------------------------------------------- #
# Process summary (fold logs without arrays)
# --------------------------------------------------------------------------- #
def process_summary(process):
    folds = []
    for f in process["folds"]:
        folds.append({k: f[k] for k in ("year", "cutoff", "trainingRows", "trainingDates", "innerBlocks", "ensemble", "state", "memberCalibration",
                                         "decisionFocusedChallenger")}
                     | {"candidates": [{k: c[k] for k in ("id", "positiveIcFolds", "requiredPositiveIcFolds", "calibration", "coverage",
                                                           "economicScore", "survives", "rejections")} for c in f["candidates"]]})
    families = {}
    for f in process["folds"]:
        for m in f["ensemble"]:
            fam = m.split("|")[0]
            families[fam] = families.get(fam, 0) + 1
    return {"folds": folds, "ensembleFamilyCounts": dict(sorted(families.items())),
            "passiveDefaultYears": [f["year"] for f in process["folds"] if not f["ensemble"]]}


# --------------------------------------------------------------------------- #
# The invented world (readiness and tests only; no market data)
# --------------------------------------------------------------------------- #
class SyntheticWorld:
    """Invented prices, caps, liquidity and signal-time features on the real KR calendar. A persistent characteristic carries a small, known
    forward drift so the machinery has something to find; it is NOT a claim about any market."""

    def __init__(self, start="2014-06-02", end="2020-12-30", names=40, industries=5, seed=11, signal=0.0006):
        from . import replay_calendar as RC
        from .regional_alpha_features import weekly_grid
        from . import kr_integrated_alpha_portfolio_replay as R
        rng = np.random.default_rng(seed)
        self.days = [str(d.date()) for d in RC.sessions(start, end, "KR")]
        self.calendar = W.Calendar(self.days)
        self.tickers = [f"{100000 + i:06d}.KS" for i in range(names)]
        self.industry = {t: f"IND{i % industries}" for i, t in enumerate(self.tickers)}
        n = len(self.days)
        market = rng.normal(0.0003, 0.011, n)
        self.char = {}
        closes = {T.BENCHMARK: 10000 * np.cumprod(1 + market)}
        for t in self.tickers:
            x = np.zeros(n)
            for i in range(1, n):
                x[i] = 0.995 * x[i - 1] + rng.normal(0, 0.1)
            beta = rng.uniform(0.6, 1.4)
            r = beta * market + rng.normal(0, 0.018, n) + signal * np.r_[0.0, x[:-1]]
            closes[t] = 1000 * np.cumprod(1 + r)
            self.char[t] = x
        self.closes = {t: dict(zip(self.days, v)) for t, v in closes.items()}
        self.cap = {t: float(rng.uniform(1e12, 2e13)) for t in self.tickers}
        self.adv = {t: float(rng.uniform(4e9, 5e10)) for t in self.tickers}
        weekly = weekly_grid(start, end, "KR")
        self.weekly = [w for w in weekly if self.calendar.pos_on_or_before(w) >= 260]
        self.anchors = R.anchor_schedule(self.days, self.weekly, "2017-01-01", T.STRIDE_KR_SESSIONS)
        self.through = end
        self.rng = rng

    def close_at(self, ticker, day):
        return self.closes.get(ticker, {}).get(day)

    def mark(self, ticker, day, previous):
        v = self.close_at(ticker, day)
        if v is None:
            raise ValueError(P.UNRESOLVED + ": " + ticker + ":" + day)
        return v

    def executable(self, ticker, day):
        return ticker in self.closes and day in self.closes[ticker]

    def adv_of(self, ticker, day):
        return self.adv.get(ticker)

    def signal_rows(self):
        rows = []
        for date in self.weekly:
            pos = self.calendar.index[date]
            for t in self.tickers:
                c = np.array([self.closes[t][d] for d in self.days[max(0, pos - 260):pos + 1]])
                b = np.array([self.closes[T.BENCHMARK][d] for d in self.days[max(0, pos - 260):pos + 1]])
                row = {"date": date, "ticker": t, "industry": self.industry[t], "industryEligible": True, "marketCap": self.cap[t],
                       "tradable": True, "adv60": self.adv[t]}
                row.update(F.derived_price_features(c, b))
                rel = float(c[-1] / c[-127] - b[-1] / b[-127]) if len(c) > 127 else None
                row.update(relative126=rel, momentum121=float(c[-22] / c[-253] - 1) if len(c) > 253 else None,
                           negativeDownsideVol126=-float(np.sqrt(np.mean(np.minimum(np.diff(c[-127:]) / c[-127:-1], 0) ** 2)) * np.sqrt(252)),
                           logAdv60=math.log1p(self.adv[t]), bookToMarketProxy=float(self.char[t][pos]),
                           earningsYieldProxy=float(self.rng.normal()), ocfYieldProxy=None if self.rng.random() < 0.2 else float(self.rng.normal()),
                           netIncomeToAssets=float(self.rng.normal()), ocfToAssets=float(self.rng.normal()),
                           negativeAccrualsToAssets=float(self.rng.normal()), ocfImprovementToAssets=None,
                           logVolumeShock5_60=float(self.rng.normal(0, 0.3)), logAmihud60=float(self.rng.normal(-20, 1)),
                           logMarketCap=math.log(self.cap[t]), stockMinusLooIndustry126=rel)
                rows.append(row)
        frame = pd.DataFrame(rows)
        for f in T.INDUSTRY_FEATURES:
            frame["ind_" + f] = frame.groupby(["date", "industry"])["relative126"].transform("mean") * (1 + T.INDUSTRY_FEATURES.index(f))
        frame["marketTrendAdverse"] = 0.0
        frame["marketVol63"] = 0.18
        return frame

    def risk(self):
        cache = {}

        def provider(date):
            if date not in cache:
                pos = self.calendar.index[date]
                window = self.days[pos - T.COVARIANCE_LOOKBACK:pos + 1]
                closes = {t: np.array([self.closes[t][d] for d in window]) for t in self.tickers}
                cache[date] = P.risk_inputs(closes, np.array([self.closes[T.BENCHMARK][d] for d in window]))
            return cache[date]
        return provider


def synthetic_registry(full=False):
    """The frozen registry, or (fast tests) one configuration per family with the NO_DECAY scheme on target C (B for nothing)."""
    reg = T.candidate_registry()
    if full:
        return reg
    seen, out = set(), []
    for c in reg:
        if c["recency"] == "NO_DECAY" and c["family"] not in seen and c["target"] in ("C_CROSS_SECTIONAL_RANK",):
            out.append(c)
            seen.add(c["family"])
    return out


def run_synthetic(world=None, full=False, counters=None):
    """The whole pipeline on the invented world: representations -> labels -> nested process -> four translators -> evidence -> verdict."""
    world = world or SyntheticWorld()
    counters = {} if counters is None else counters
    rows = world.signal_rows()
    rep = F.represent(rows)
    data = W.prepare_data(rep)
    labels = W.align_labels(data, build_labels(rows, world.calendar, world.close_at, world.through, counters=counters))
    risk = world.risk()
    process = W.run_process(data, labels, world.anchors, synthetic_registry(full), risk, world.calendar, counters)
    first = W.outer_folds(world.anchors)[0]["anchors"][0][0]
    paths = run_paths(process["anchors"], data, risk, world.days, first, world.through, world.mark, world.executable, world.adv_of, counters)
    outer = [d for f in W.outer_folds(world.anchors) for d, _ in f["anchors"]]
    coverage = 100.0 * sum(1 for d in outer if process["anchors"].get(d, {}).get("available")) / max(1, len(outer))
    return {"process": process, "paths": paths, "labels": labels, "result": assemble(process, paths, labels, coverage), "counters": counters}
