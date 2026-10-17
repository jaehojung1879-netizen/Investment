"""rp1-c1-us-exposure-ladder-replication-v1 — independent validation of a result before it is published.

The evaluation (`rp1_c1_us_exposure.evaluate`) assembles sealed KR functions. This module checks what it published WITHOUT those functions: it
re-derives the trading rule from the frozen text ("trade exactly to target x post-cost NAV at the execution close, costs paid from cash, drift
otherwise, cash earns the known rate"), replays every path with its own loop, and recomputes each economic quantity with its own arithmetic:

  CAGR, maximum drawdown, monthly CVaR (5%) and the worst month, summed transaction cost and cost drag (gross minus net CAGR), the share of
  sessions de-risked and the average equity weight, the up-market cost and down-market saving per year (upside non-participation), and, per
  >= 15% reference episode, the rebound missed over H63/H126 after the trough, the sessions until full exposure and the recovery opportunity cost
  (re-entry loss).

What it shares with the evaluation are the frozen STATE rules (layer states, decision schedule, candidate targets, the cash-rate lag), which the
KR equivalence audit proves equal to the sealed study. Every comparison is relative at 1e-9; any mismatch makes the validation INCONSISTENT and the
harness refuses to publish the result as validated. Pure: no I/O.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import kr_market_risk_model as K
from . import rp1_c1_us_exposure as U

TOLERANCE = 1e-9
YEAR = 252
CVAR_LEVEL = U.CVAR_LEVEL
EPISODE_DEPTH = K.PRIMARY_EPISODE_THRESHOLD
REBOUND = (63, 126)


# =======================================================================================================================================
# Independent replay and metrics
# =======================================================================================================================================
def replay(close, schedule, targets, buy, sell, cash_returns=None):
    """Own loop. Returns a frame with nav, target, weightStart, cost (share of pre-trade NAV) and dailyReturn, indexed like `close` from the first
    execution session."""
    first = pd.Timestamp(schedule["executionDate"].iloc[0])
    c = pd.Series(close, dtype=float)
    c = c[c.index >= first]
    price = c.to_numpy()
    rc = np.zeros(len(c)) if cash_returns is None else pd.Series(cash_returns, dtype=float).reindex(c.index).fillna(0.0).to_numpy()
    orders = {c.index.get_loc(pd.Timestamp(d)): float(t) for d, t in zip(schedule["executionDate"], targets) if pd.Timestamp(d) in c.index}
    held = float(targets[0])
    equity, cash = held, 1.0 - held
    nav, tgt, wstart, cost = [1.0], [held], [held], [0.0]
    for i in range(1, len(price)):
        before = equity + cash
        wstart.append(equity / before)
        equity *= price[i] / price[i - 1]
        cash *= 1.0 + rc[i]
        paid = 0.0
        if i in orders and orders[i] != held:
            held = orders[i]
            value = equity + cash
            if held * value > equity:                       # buy b: equity + b == held x (value - buy x b)
                b = (held * value - equity) / (1.0 + held * buy)
                equity, cash, paid = equity + b, cash - b - buy * b, buy * b
            elif held * value < equity:                     # sell s: equity - s == held x (value - sell x s)
                s = (equity - held * value) / (1.0 - held * sell)
                equity, cash, paid = equity - s, cash + s - sell * s, sell * s
            paid /= value
        nav.append(equity + cash)
        tgt.append(held)
        cost.append(paid)
    nav = np.asarray(nav)
    daily = np.r_[np.nan, nav[1:] / nav[:-1] - 1.0]
    return pd.DataFrame({"nav": nav, "target": tgt, "weightStart": wstart, "cost": cost, "dailyReturn": daily}, index=c.index)


def cagr(nav):
    n = len(nav) - 1
    growth = nav[-1] / nav[0]
    return growth ** (YEAR / n) - 1.0 if n > 0 and growth > 0 else None


def max_drawdown(nav):
    nav = np.asarray(nav, float)
    return float(np.min(nav / np.maximum.accumulate(nav) - 1.0))


def monthly_tail(path):
    nav = path["nav"]
    month_end = nav.groupby(nav.index.to_period("M")).last().to_numpy()
    start = np.r_[nav.iloc[0], month_end[:-1]]
    r = np.sort(month_end / start - 1.0)
    k = max(1, math.ceil(CVAR_LEVEL * len(r)))
    return {"cvar": float(r[:k].mean()), "worstMonth": float(r[0]), "months": int(len(r))}


def gap(path, passive):
    r, b = path["dailyReturn"].to_numpy()[1:], passive["dailyReturn"].to_numpy()[1:]
    years = len(r) / YEAR
    return {"upMarketCostPerYear": float(np.sum((b - r)[b > 0]) / years), "downMarketSavingPerYear": float(np.sum((r - b)[b < 0]) / years)}


def episodes(close):
    """Underwater episodes of the reference over the window, by the frozen definition: a close below the running peak opens one, its trough is the
    first lowest close, a close at or above the peak ends it, an open one at the end is censored."""
    c = np.asarray(close, float)
    out, peak, under, trough = [], 0, False, 0
    for i in range(len(c)):
        if c[i] >= c[peak]:
            if under:
                out.append({"peak": peak, "trough": trough, "recovery": i, "depth": c[trough] / c[peak] - 1.0})
                under = False
            peak = i
        elif not under:
            under, trough = True, i
        elif c[i] < c[trough]:
            trough = i
    if under:
        out.append({"peak": peak, "trough": trough, "recovery": None, "depth": c[trough] / c[peak] - 1.0})
    return out


def reentry(path, close, chosen):
    nav, ref, tgt = path["nav"].to_numpy(), np.asarray(close, float), path["target"].to_numpy()
    rows = []
    for e in chosen:
        t = e["trough"]
        row = {f"reboundMissedH{h}": (float((ref[t + h] / ref[t] - 1.0) - (nav[t + h] / nav[t] - 1.0)) if t + h < len(nav) else None) for h in REBOUND}
        full = np.flatnonzero(tgt[t:] >= 1.0)
        row["sessionsUntilFullExposure"] = int(full[0]) if len(full) else None
        end = e["recovery"] if e["recovery"] is not None else len(nav) - 1
        row["recoveryOpportunityCost"] = float((ref[end] / ref[t] - 1.0) - (nav[end] / nav[t] - 1.0))
        rows.append(row)
    return rows


def path_metrics(net, gross, passive):
    return {"cagr": cagr(net["nav"].to_numpy()), "maxDrawdown": max_drawdown(net["nav"]), **monthly_tail(net),
            "totalCost": float(net["cost"].sum()), "costDrag": cagr(gross["nav"].to_numpy()) - cagr(net["nav"].to_numpy()),
            "reducedSessionShare": float((net["target"] < 1.0).mean()), "averageEquityWeight": float(net["weightStart"].iloc[1:].mean()),
            **gap(net, passive)}


# =======================================================================================================================================
# Comparison against a published result
# =======================================================================================================================================
class _Checker:
    def __init__(self):
        self.checks, self.mismatches, self.worst = 0, [], 0.0

    def __call__(self, name, independent, published):
        self.checks += 1
        if independent is None or published is None:
            if independent is not published:
                self.mismatches.append({"quantity": name, "independent": independent, "published": published})
            return
        d = abs(float(independent) - float(published))
        self.worst = max(self.worst, d)
        if d > TOLERANCE * max(1.0, abs(float(published))):
            self.mismatches.append({"quantity": name, "independent": float(independent), "published": float(published), "absoluteDifference": d})


def validate(values, config, result):
    """Recompute and compare. Returns {status, checks, mismatches, maxAbsoluteDifference, independent: per-strategy table}."""
    market = config["market"]
    reference = values["reference"]
    reference = reference[(reference.index >= pd.Timestamp(config["gridStart"])) & (reference.index <= pd.Timestamp(config["analysisEnd"]))]
    sessions = U.market_sessions(market, str(reference.index.min().date()), config["analysisEnd"])
    close = reference.reindex(sessions)
    states = U.layer_states(close, values["spread"], values["vix"], sessions, market, config["spreadLag"], config["vixLag"])
    schedule = U.decision_schedule(sessions, config["evaluationStart"], config["analysisEnd"], market)
    window = sessions[sessions >= schedule["executionDate"].iloc[0]]
    bench = close.reindex(window)
    buy, sell = config["buyCost"], config["sellCost"]
    check = _Checker()
    targets = {cid: K.candidate_targets(states, schedule, cid)["target"].tolist() for cid in K.CANDIDATE_ORDER}
    passive = replay(bench, schedule, [1.0] * len(schedule), 0.0, 0.0)
    chosen = [e for e in episodes(bench.to_numpy()) if e["depth"] <= -EPISODE_DEPTH + 1e-15]
    table = {"primary": {K.PASSIVE: {"cagr": cagr(passive["nav"].to_numpy()), "maxDrawdown": max_drawdown(passive["nav"]), **monthly_tail(passive)}}}
    p = result["passive"]
    check("primary/PASSIVE/cagr", table["primary"][K.PASSIVE]["cagr"], p["summary"]["annualizedReturn"])
    check("primary/PASSIVE/maxDrawdown", table["primary"][K.PASSIVE]["maxDrawdown"], p["summary"]["maxDrawdown"])
    if "monthlyCvar" in p:
        check("primary/PASSIVE/cvar", table["primary"][K.PASSIVE]["cvar"], p["monthlyCvar"]["cvar"])
    check("primary/episodeCount", len(chosen), result["window"]["episodeCounts"][f"depth_ge_{int(EPISODE_DEPTH * 100)}pct"])
    for cid in K.CANDIDATE_ORDER:
        net = replay(bench, schedule, targets[cid], buy, sell)
        gross = replay(bench, schedule, targets[cid], 0.0, 0.0)
        m = path_metrics(net, gross, passive)
        rows = reentry(net, bench.to_numpy(), chosen)
        table["primary"][cid] = {**m, "reentry": _mean_rows(rows)}
        c = result["candidates"][cid]
        check(f"primary/{cid}/cagr", m["cagr"], c["net"]["annualizedReturn"])
        check(f"primary/{cid}/maxDrawdown", m["maxDrawdown"], c["net"]["maxDrawdown"])
        check(f"primary/{cid}/reducedSessionShare", m["reducedSessionShare"], c["net"]["reducedSessionShare"])
        check(f"primary/{cid}/averageEquityWeight", m["averageEquityWeight"], c["net"]["averageEquityWeight"])
        check(f"primary/{cid}/totalCost", m["totalCost"], c["implementation"]["totalCostFractionOfNav"])
        check(f"primary/{cid}/costDrag", m["costDrag"], c["implementation"]["costDrag"])
        if "diagnostics" in c:
            d = c["diagnostics"]
            check(f"primary/{cid}/cvar", m["cvar"], d["monthlyCvar"]["cvar"])
            check(f"primary/{cid}/worstMonth", m["worstMonth"], d["monthlyCvar"]["worstMonth"])
            check(f"primary/{cid}/upMarketCostPerYear", m["upMarketCostPerYear"], d["upDownMarketGap"]["upMarketCostPerYear"])
            check(f"primary/{cid}/downMarketSavingPerYear", m["downMarketSavingPerYear"], d["upDownMarketGap"]["downMarketSavingPerYear"])
        published = c["episodes"][f"depth_ge_{int(EPISODE_DEPTH * 100)}pct"]["rebound"]
        check(f"primary/{cid}/reentryEpisodes", len(rows), len(published))
        for i, (mine, theirs) in enumerate(zip(rows, published)):
            for key in ("reboundMissedH63", "reboundMissedH126", "sessionsUntilFullExposure", "recoveryOpportunityCost"):
                check(f"primary/{cid}/episode{i}/{key}", mine[key], theirs[key])
    if result.get("economic"):
        asset = values["asset"].reindex(window)
        cash = U.cash_interval_returns(values["cash"], window, config["cashLag"])
        e_passive = replay(asset, schedule, [1.0] * len(schedule), 0.0, 0.0)
        cash_only = replay(asset, schedule, [0.0] * len(schedule), 0.0, 0.0, cash)
        table["economic"] = {K.PASSIVE: {"cagr": cagr(e_passive["nav"].to_numpy()), "maxDrawdown": max_drawdown(e_passive["nav"]), **monthly_tail(e_passive)},
                             "CASH_ONLY": {"cagr": cagr(cash_only["nav"].to_numpy())}}
        ep = result["economic"]
        check("economic/PASSIVE/cagr", table["economic"][K.PASSIVE]["cagr"], ep["passive"]["summary"]["annualizedReturn"])
        check("economic/PASSIVE/maxDrawdown", table["economic"][K.PASSIVE]["maxDrawdown"], ep["passive"]["summary"]["maxDrawdown"])
        check("economic/PASSIVE/cvar", table["economic"][K.PASSIVE]["cvar"], ep["passive"]["monthlyCvar"]["cvar"])
        check("economic/CASH_ONLY/cagr", table["economic"]["CASH_ONLY"]["cagr"], ep["cashOnly"]["annualizedReturn"])
        for cid in K.CANDIDATE_ORDER:
            net = replay(asset, schedule, targets[cid], buy, sell, cash)
            gross = replay(asset, schedule, targets[cid], 0.0, 0.0, cash)
            m = path_metrics(net, gross, e_passive)
            table["economic"][cid] = m
            c = ep["candidates"][cid]
            check(f"economic/{cid}/cagr", m["cagr"], c["net"]["annualizedReturn"])
            check(f"economic/{cid}/maxDrawdown", m["maxDrawdown"], c["net"]["maxDrawdown"])
            check(f"economic/{cid}/costDrag", m["costDrag"], c["costDrag"])
            check(f"economic/{cid}/cvar", m["cvar"], c["monthlyCvar"]["cvar"])
            check(f"economic/{cid}/upMarketCostPerYear", m["upMarketCostPerYear"], c["upDownMarketGap"]["upMarketCostPerYear"])
            check(f"economic/{cid}/downMarketSavingPerYear", m["downMarketSavingPerYear"], c["upDownMarketGap"]["downMarketSavingPerYear"])
    return {"status": "CONSISTENT" if not check.mismatches else "INCONSISTENT", "checks": check.checks, "mismatches": check.mismatches[:50],
            "mismatchCount": len(check.mismatches), "maxAbsoluteDifference": check.worst, "tolerance": TOLERANCE, "independent": table,
            "independentOf": ["replay loop", "every metric"], "sharedWithTheEvaluation": ["layer states", "decision schedule", "candidate targets",
                                                                                        "cash-rate lag and staleness"]}


def _mean_rows(rows):
    out = {}
    for key in ("reboundMissedH63", "reboundMissedH126", "sessionsUntilFullExposure", "recoveryOpportunityCost"):
        v = [r[key] for r in rows if r[key] is not None]
        out[key] = {"episodes": len(rows), "measured": len(v), "mean": float(np.mean(v)) if v else None, "median": float(np.median(v)) if v else None}
    return out
