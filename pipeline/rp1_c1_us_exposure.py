"""rp1-c1-us-exposure-ladder-replication-v1 — the sealed KR market-risk ladder applied, unchanged, to the US index.

FROZEN_RULE_REPLICATION. The rules were designed on outcome-exposed KR history (`kr-market-risk-anatomy-v2`, `kr-market-risk-model-v1`) and the US
index history they are applied to is publicly known. Whatever this study produces is a replication of a frozen rule in a second market, never
validation, never production. Only prospective records can become evidence.

Pure: no I/O, no network, no fit. This module adds exactly three things to the sealed `kr_market_risk_model` and changes nothing in it:

* AN EXCHANGE CALENDAR ARGUMENT. `kr_market_risk_model.period_end_sessions` and `decision_schedule` call the KRX calendar directly. The functions here
  are the same arithmetic with the calendar passed in; on the KR calendar they reproduce the sealed functions exactly (tested on every session of the
  sealed KR grid, and by reproducing the sealed KR decision from the retained KR bytes). Every rule, threshold, window, lag, multiplier, cost path,
  metric and the decision rule is imported from the sealed modules, never restated.
* AN ECONOMIC READING. The primary reading is the KR convention (price index, cash at zero). A second, pre-declared reading holds a total-return ETF
  and accrues a cash rate on the de-risked share. Both readings use the SAME targets, computed from the price-index states.
* DIAGNOSTICS THE KR STUDY DID NOT PUBLISH, frozen before any outcome: monthly CVaR, up-market cost against down-market saving, unprotected drawdown
  episodes, the false-alarm list, fixed sub-periods and, for the economic reading only, a Sharpe ratio over the cash rate. None of them enters the
  decision; the decision is the sealed KR rule.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import kr_market_risk_anatomy as M
from . import kr_market_risk_model as K
from . import replay_calendar as RC

STUDY = "rp1-c1-us-exposure-ladder-replication-v1"
SCIENTIFIC_STATUS = "FROZEN_RULE_REPLICATION_ON_PUBLICLY_KNOWN_US_HISTORY"
EVIDENCE_STATEMENT = ("The rules were designed on outcome-exposed KR history and are applied unchanged to publicly known US index history; every "
                      "number this study can produce is a frozen-rule replication, never validation and never a production signal.")
CALENDARS = ("KR", "US")

# ---- US conventions (everything else is imported from the sealed KR modules) ---------------------------------------------------------------
# One-way index exposure costs from the repository's US cost table (benchmark_alpha.REALISTIC_COSTS["US"], equality tested):
# buy = commission 5bp + half spread 3bp; sell = the same plus the 0.30bp sell-side fee. Conservative for an ETF whose spread is far narrower.
US_BUY_COST = 0.0008
US_SELL_COST = 0.00083
EVALUATION_START = "1993-02-01"   # first full month after SPY's 1993-01-29 listing, so both readings share one window
ANALYSIS_END = "2026-09-17"       # inherited unchanged from the sealed KR study; not chosen for the US
GRID_START = "1990-01-01"         # the KR acquisition START; the VIX expanding history and every state begin on the same footing
SUBPERIODS = (("PRE_KR_WINDOW", EVALUATION_START, "2006-12-31"), ("KR_WINDOW", "2007-01-01", ANALYSIS_END))
CVAR_LEVEL = 0.05
CASH_DAY_COUNT = 360              # DTB3 is a money-market (discount-basis) rate quoted on a 360-day year
CASH_RATE_DEFINITION = ("rate known at the previous session (FRED lag and staleness rules) / 100 x calendar days in the interval / 360; the discount "
                        "yield is used as a simple money-market rate, an approximation stated as one")


# =======================================================================================================================================
# Calendar-parameterised sampling (identical arithmetic to the sealed KR functions)
# =======================================================================================================================================
def market_sessions(market, start, end):
    if market not in CALENDARS:
        raise ValueError("UNKNOWN_CALENDAR: " + str(market))
    return RC.sessions(start, end, market)


def period_end_sessions(sessions, frequency, market):
    """`kr_market_risk_model.period_end_sessions` with the exchange calendar passed in: sessions whose NEXT session on that calendar lies in a later
    week ('W') or month ('M'). Never marks the last available session as a period end merely because the data stop there."""
    days = pd.DatetimeIndex(sessions)
    if len(days) == 0:
        return days
    calendar = market_sessions(market, str(days[0].date()), str((days[-1] + pd.Timedelta(days=45)).date()))
    position = calendar.get_indexer(days)
    if (position < 0).any():
        raise ValueError("SESSION_NOT_ON_THE_" + market + "_CALENDAR")
    if position.max() + 1 >= len(calendar):
        raise ValueError("CALENDAR_TOO_SHORT")
    following = calendar[position + 1]
    is_end = days.to_period(frequency) != following.to_period(frequency)
    return days[np.asarray(is_end)]


def slow_states(spread_obs, sessions, market, lag_days=K.FRED_LAG_DAYS):
    days = pd.DatetimeIndex(sessions)
    known = M.known_on_sessions(spread_obs, days, lag_days, K.FRED_STALE_DAYS)[0]
    daily = M.slow_features({"spread_10y3m": known}, days)[K.SLOW_FEATURE]
    ends = period_end_sessions(days, K.SLOW_CADENCE, market)
    return K._carry(daily.reindex(ends), days), K._carry(known.reindex(ends), days)


def transition_states(vix_obs, sessions, market, lag_days=K.FRED_LAG_DAYS):
    days = pd.DatetimeIndex(sessions)
    known = M.known_on_sessions(vix_obs, days, lag_days, K.FRED_STALE_DAYS)[0]
    ends = period_end_sessions(days, K.TRANSITION_CADENCE, market)
    weekly = known.reindex(ends)
    pct = M.expanding_percentile(weekly.to_numpy(), K.TRANSITION_MIN_OBS)
    pct.index = ends
    adverse = (pct >= K.TRANSITION_HIGH_PERCENTILE).astype(float).where(pct.notna())
    return K._carry(adverse, days), K._carry(pct, days), K._carry(weekly, days)


def layer_states(close, spread_obs, vix_obs, sessions, market, spread_lag=K.FRED_LAG_DAYS, vix_lag=K.FRED_LAG_DAYS):
    days = pd.DatetimeIndex(sessions)
    fast = K.fast_states(pd.Series(close, dtype=float).reindex(days))
    slow, spread = slow_states(spread_obs, days, market, spread_lag)
    transition, pct, vix = transition_states(vix_obs, days, market, vix_lag)
    out = fast.copy()
    out["slow"], out["spreadAtSample"] = slow.to_numpy(), spread.to_numpy()
    out["transition"], out["vixPercentile"], out["vixAtSample"] = transition.to_numpy(), pct.to_numpy(), vix.to_numpy()
    return out


def decision_schedule(sessions, start, end, market):
    days = pd.DatetimeIndex(sessions)
    calendar = market_sessions(market, str(days[0].date()), str((pd.Timestamp(end) + pd.Timedelta(days=45)).date()))
    ends = period_end_sessions(days[days <= pd.Timestamp(end)], K.DECISION_CADENCE, market)
    rows = []
    for d in ends[ends >= pd.Timestamp(start)]:
        execution = calendar[calendar.get_loc(d) + 1]
        if execution <= pd.Timestamp(end):
            rows.append({"decisionDate": d, "executionDate": execution})
    return pd.DataFrame(rows, columns=["decisionDate", "executionDate"])


# =======================================================================================================================================
# The economic reading: a total-return asset and an accruing cash leg, on the SAME targets
# =======================================================================================================================================
def cash_interval_returns(rate_obs, sessions, lag_days=K.FRED_LAG_DAYS, stale_days=K.FRED_STALE_DAYS):
    """Cash return earned from the previous session's close to each session's close: the rate known at the previous session (observation date +
    lag <= session, older than `stale_days` is missing), in percent per year, times calendar days / 360. NaN on the first session and wherever the
    rate is unknown; a missing rate is never filled with zero."""
    days = pd.DatetimeIndex(sessions)
    known = M.known_on_sessions(rate_obs, days, lag_days, stale_days)[0]
    gap = pd.Series(np.r_[np.nan, (days[1:] - days[:-1]).days], index=days, dtype=float)
    return known.shift(1) / 100.0 * gap / CASH_DAY_COUNT


def replay_path_with_cash(asset_close, schedule, targets, cash_returns, stress=1.0, buy_cost=K.BUY_COST, sell_cost=K.SELL_COST):
    """`kr_market_risk_model.replay_path` with one change: the cash share earns `cash_returns` (indexed by session) between closes. With a zero cash
    return it is the sealed function exactly (tested). Start, drift, trade-only-on-change and exact post-cost targeting are unchanged."""
    if not math.isfinite(stress) or stress < 0:
        raise ValueError("INVALID_COST_STRESS")
    targets = list(targets)
    if any(not (0.0 <= t <= 1.0) for t in targets):
        raise ValueError("NO_LEVERAGE_MULTIPLIER_REQUIRED")
    executions = dict(zip(pd.DatetimeIndex(schedule["executionDate"]), targets))
    first = pd.Timestamp(schedule["executionDate"].iloc[0])
    c = pd.Series(asset_close, dtype=float)
    c = c[c.index >= first]
    if not np.isfinite(c.to_numpy()).all() or (c <= 0).any():
        raise ValueError("REFERENCE_PATH_HAS_A_MISSING_OR_INVALID_SESSION")
    rc = pd.Series(cash_returns, dtype=float).reindex(c.index)
    if not np.isfinite(rc.iloc[1:].to_numpy()).all():
        raise ValueError("CASH_RATE_MISSING_ON_AN_EVALUATION_SESSION")
    current = targets[0]
    equity, cash = current, 1.0 - current
    rows = [{"date": first, "nav": 1.0, "weightStart": current, "weightEnd": current, "target": current, "notional": 0.0, "cost": 0.0, "dailyReturn": np.nan}]
    for prev, day in zip(c.index[:-1], c.index[1:]):
        nav_before = equity + cash
        weight_start = equity / nav_before
        equity *= c.loc[day] / c.loc[prev]
        cash *= 1.0 + rc.loc[day]
        notional = cost = 0.0
        pre_trade_nav = equity + cash
        if day in executions and executions[day] != current:
            current = executions[day]
            equity, cash, notional, cost = K.trade_to_target(equity, cash, current, buy_cost * stress, sell_cost * stress)
        nav = equity + cash
        rows.append({"date": day, "nav": nav, "weightStart": weight_start, "weightEnd": equity / nav, "target": current,
                     "notional": notional / pre_trade_nav, "cost": cost / pre_trade_nav, "dailyReturn": nav / nav_before - 1.0})
    return pd.DataFrame(rows).set_index("date")


# =======================================================================================================================================
# Diagnostics added before any outcome (descriptive; none of them enters the decision)
# =======================================================================================================================================
def monthly_returns(path):
    nav = path["nav"]
    month_end = nav.groupby(nav.index.to_period("M")).last()
    previous = pd.concat([pd.Series([nav.iloc[0]]), month_end.iloc[:-1]], ignore_index=True)
    return pd.Series(month_end.to_numpy() / previous.to_numpy() - 1.0, index=month_end.index.astype(str))


def monthly_cvar(path, level=CVAR_LEVEL):
    """Mean of the worst ceil(level x n) calendar-month returns (the first and last months are partial), and the worst month."""
    r = np.sort(monthly_returns(path).to_numpy())
    if len(r) == 0:
        return {"months": 0, "cvar": None, "worstMonth": None}
    k = max(1, int(math.ceil(level * len(r))))
    return {"months": int(len(r)), "tailMonths": k, "cvar": float(r[:k].mean()), "worstMonth": float(r[0])}


def up_down_market_gap(path, passive):
    """Arithmetic split of the daily return gap to the passive path: on passive up days the sum of (passive - candidate) is the up-market cost;
    on passive down days the sum of (candidate - passive) is the down-market saving. Per year, descriptive, not compounded."""
    r, b = path["dailyReturn"], passive["dailyReturn"].reindex(path.index)
    ok = r.notna() & b.notna()
    up, down = ok & (b > 0), ok & (b < 0)
    years = ok.sum() / K.ANNUALISATION
    return {"upMarketCostPerYear": float((b[up] - r[up]).sum() / years) if years else None,
            "downMarketSavingPerYear": float((r[down] - b[down]).sum() / years) if years else None,
            "upDays": int(up.sum()), "downDays": int(down.sum())}


def protection_by_episode(path, episodes):
    """Per reference episode: the share of sessions from peak to trough at a reduced target, and UNPROTECTED when the target was 1.0 throughout."""
    target = path["target"].to_numpy()
    out = []
    for e in episodes:
        window = target[e["peakPos"]:e["troughPos"] + 1]
        share = float((window < K.FULL).mean()) if len(window) else None
        out.append({"peakDate": str(path.index[e["peakPos"]].date()), "troughDate": str(path.index[e["troughPos"]].date()),
                    "referenceDepth": float(e["depth"]), "reducedShareOfDecline": share, "unprotected": bool(share == 0.0)})
    return out


def false_alarm_list(path, forward_worst_loss):
    """Every activation (target falls from 1.0) with its date, the target it fell to, and the reference's forward worst loss over H63; FALSE when the
    loss stayed above -10%, PENDING when the window has not matured. The counts equal `kr_market_risk_model.false_alarm_profile` (tested)."""
    target = path["target"].to_numpy()
    worst = pd.Series(forward_worst_loss, dtype=float).reindex(path.index).to_numpy()
    reduced = target < K.FULL
    onset = reduced & np.concatenate(([True], ~reduced[:-1]))
    rows = []
    for i in np.flatnonzero(onset):
        status = "PENDING" if not np.isfinite(worst[i]) else ("FALSE_ALARM" if worst[i] > K.FALSE_ALARM_LOSS_CUT else "FOLLOWED_BY_LARGE_LOSS")
        rows.append({"date": str(path.index[i].date()), "target": float(target[i]),
                     "forwardWorstLossH63": None if not np.isfinite(worst[i]) else float(worst[i]), "status": status})
    return rows


def subperiod_summary(path, passive, periods=SUBPERIODS):
    out = {}
    for name, start, end in periods:
        mask = (path.index >= pd.Timestamp(start)) & (path.index <= pd.Timestamp(end))
        sub, ref = path[mask], passive[mask]
        if len(sub) < 2:
            out[name] = {"start": start, "end": end, "sessions": int(max(len(sub) - 1, 0))}
            continue
        out[name] = {"start": str(sub.index[0].date()), "end": str(sub.index[-1].date()), "sessions": int(len(sub) - 1),
                     "annualizedReturn": K.annualized(sub["nav"].iloc[-1] / sub["nav"].iloc[0], len(sub) - 1),
                     "maxDrawdown": K.max_drawdown(sub["nav"])["maxDrawdown"], "reducedSessionShare": float((sub["target"] < K.FULL).mean()),
                     "passiveAnnualizedReturn": K.annualized(ref["nav"].iloc[-1] / ref["nav"].iloc[0], len(ref) - 1),
                     "passiveMaxDrawdown": K.max_drawdown(ref["nav"])["maxDrawdown"]}
    return out


def sharpe_over_cash(path, cash_returns):
    """Annualised mean of (daily path return - daily cash return) over its standard deviation (ddof 1) x sqrt(252)."""
    r = path["dailyReturn"]
    excess = (r - pd.Series(cash_returns, dtype=float).reindex(r.index)).dropna()
    sd = float(excess.std(ddof=1)) if len(excess) > 1 else 0.0
    return float(excess.mean() / sd * math.sqrt(K.ANNUALISATION)) if sd > 0 else None


def gross_minus(gross, net):
    n = len(net) - 1
    g, x = K.annualized(gross["nav"].iloc[-1] / gross["nav"].iloc[0], n), K.annualized(net["nav"].iloc[-1] / net["nav"].iloc[0], n)
    return None if g is None or x is None else g - x


# =======================================================================================================================================
# Assembly (pure; the formal harness calls it after its lock and never before)
# =======================================================================================================================================
def evaluate(values, config):
    """Every quantity of one market's replication from already-read values. `values`: reference (index close by date), spread (10y-3m by observation
    date), vix (by observation date) and, for the economic reading, asset (total-return close by date) and cash (rate in percent by observation date).
    `config`: market, gridStart, evaluationStart, analysisEnd, buyCost, sellCost, spreadLag, vixLag, cashLag, economic (bool), diagnostics (bool).

    On the KR configuration with diagnostics and the economic reading off this is the sealed KR evaluation step for step (the equivalence audit
    reproduces the sealed KR decision from the retained KR bytes)."""
    market = config["market"]
    reference = values["reference"]
    reference = reference[(reference.index >= pd.Timestamp(config["gridStart"])) & (reference.index <= pd.Timestamp(config["analysisEnd"]))]
    sessions = market_sessions(market, str(reference.index.min().date()), config["analysisEnd"])
    close = reference.reindex(sessions)
    states = layer_states(close, values["spread"], values["vix"], sessions, market, config["spreadLag"], config["vixLag"])
    schedule = decision_schedule(sessions, config["evaluationStart"], config["analysisEnd"], market)
    window = sessions[sessions >= schedule["executionDate"].iloc[0]]
    bench = close.reindex(window)
    forward = M.forward_targets(bench, K.FALSE_ALARM_HORIZON)["forwardWorstLoss"]
    episodes = K.episodes_in_window(bench)
    primary_episodes = M.episodes_at_least(episodes, K.PRIMARY_EPISODE_THRESHOLD)
    targets = {cid: K.candidate_targets(states, schedule, cid) for cid in K.CANDIDATE_ORDER}
    buy, sell = config["buyCost"], config["sellCost"]
    passive = K.replay_path(bench, schedule, [K.FULL] * len(schedule), stress=0.0, buy_cost=buy, sell_cost=sell)
    result = {"candidates": {}, "passive": {"summary": K.path_summary(passive, passive), "halves": K.halves(passive, passive),
                                            "calendarYears": K.calendar_years(passive),
                                            "episodeCapture": K.episode_capture(passive, bench, primary_episodes)}}
    if config.get("diagnostics"):
        result["passive"]["monthlyCvar"] = monthly_cvar(passive)
        result["passive"]["subperiods"] = subperiod_summary(passive, passive)
    nomination_input = {K.PASSIVE: {"netAnnualizedReturn": result["passive"]["summary"]["annualizedReturn"],
                                    "maxDrawdown": result["passive"]["summary"]["maxDrawdown"], "reducedSessionShare": 0.0}}
    for cid in K.CANDIDATE_ORDER:
        t = targets[cid]
        paths = {s: K.replay_path(bench, schedule, t["target"].tolist(), stress=s, buy_cost=buy, sell_cost=sell) for s in (0.0,) + K.COST_STRESS}
        net, gross = paths[1.0], paths[0.0]
        by_threshold = {}
        for threshold in K.EPISODE_THRESHOLDS:
            chosen = M.episodes_at_least(episodes, threshold)
            capture, rebound = K.episode_capture(net, bench, chosen), K.rebound_cost(net, bench, chosen)
            by_threshold[f"depth_ge_{int(threshold * 100)}pct"] = {
                "capture": capture, "rebound": rebound,
                "summary": {key: K.summarise_episodes(capture, key) for key in ("lossCaptureRatio", "avoidedLoss", "sessionsToRegainPeakValue")}
                | {key: K.summarise_episodes(rebound, key) for key in ("reboundMissedH63", "reboundMissedH126", "sessionsUntilFullExposure", "recoveryOpportunityCost")}}
        summary = K.path_summary(net, passive)
        entry = {"name": K.CANDIDATES[cid]["name"], "decisionDates": int(len(t)), "heldForMissingState": int(t["heldForMissingState"].sum()),
                 "net": summary, "gross": K.path_summary(gross, passive),
                 "stress": {f"x{int(s)}": {"annualizedReturn": K.path_summary(paths[s], passive)["annualizedReturn"], "costDrag": gross_minus(gross, paths[s])}
                            for s in K.COST_STRESS},
                 "implementation": {**K.implementation_cost(net), "costDrag": gross_minus(gross, net)},
                 "falseAlarm": K.false_alarm_profile(net, forward), "episodes": by_threshold,
                 "halves": K.halves(net, passive), "calendarYears": K.calendar_years(net)}
        if config.get("diagnostics"):
            entry["diagnostics"] = {"monthlyCvar": monthly_cvar(net), "upDownMarketGap": up_down_market_gap(net, passive),
                                    "protectionByEpisode": protection_by_episode(net, primary_episodes),
                                    "falseAlarmList": false_alarm_list(net, forward), "subperiods": subperiod_summary(net, passive)}
        result["candidates"][cid] = entry
        nomination_input[cid] = {"netAnnualizedReturn": summary["annualizedReturn"], "maxDrawdown": summary["maxDrawdown"],
                                 "reducedSessionShare": summary["reducedSessionShare"]}
    result["decision"] = {**K.development_nomination(nomination_input), "axes": nomination_input}
    result["window"] = {"firstDecisionDate": str(schedule["decisionDate"].iloc[0].date()), "firstExecutionDate": str(window[0].date()),
                        "lastExecutionDate": str(schedule["executionDate"].iloc[-1].date()), "end": str(window[-1].date()), "sessions": int(len(window) - 1),
                        "decisionDates": int(len(schedule)),
                        "episodeCounts": {f"depth_ge_{int(x * 100)}pct": len(M.episodes_at_least(episodes, x)) for x in K.EPISODE_THRESHOLDS}}
    if config.get("economic"):
        result["economic"] = economic_reading(values, config, schedule, targets, window)
    return result


def economic_reading(values, config, schedule, targets, window):
    """The pre-declared second reading: the same targets applied to the total-return asset with the de-risked share earning the cash rate. It is
    reported beside the primary reading and never enters the decision."""
    asset = values["asset"].reindex(window)
    cash = cash_interval_returns(values["cash"], window, config["cashLag"])
    zero = pd.Series(0.0, index=window)
    buy, sell = config["buyCost"], config["sellCost"]
    passive = replay_path_with_cash(asset, schedule, [K.FULL] * len(schedule), zero, stress=0.0, buy_cost=buy, sell_cost=sell)
    cash_only = replay_path_with_cash(asset, schedule, [0.0] * len(schedule), cash, stress=0.0, buy_cost=buy, sell_cost=sell)
    out = {"passive": {"summary": K.path_summary(passive, passive), "monthlyCvar": monthly_cvar(passive), "sharpeOverCash": sharpe_over_cash(passive, cash),
                       "subperiods": subperiod_summary(passive, passive)},
           "cashOnly": {"annualizedReturn": K.path_summary(cash_only, cash_only)["annualizedReturn"]}, "candidates": {}}
    for cid in K.CANDIDATE_ORDER:
        t = targets[cid]["target"].tolist()
        net = replay_path_with_cash(asset, schedule, t, cash, stress=1.0, buy_cost=buy, sell_cost=sell)
        gross = replay_path_with_cash(asset, schedule, t, cash, stress=0.0, buy_cost=buy, sell_cost=sell)
        out["candidates"][cid] = {"net": K.path_summary(net, passive), "costDrag": gross_minus(gross, net), "monthlyCvar": monthly_cvar(net),
                                  "sharpeOverCash": sharpe_over_cash(net, cash), "upDownMarketGap": up_down_market_gap(net, passive),
                                  "subperiods": subperiod_summary(net, passive)}
    return out


def us_config(economic=True, diagnostics=True):
    return {"market": "US", "gridStart": GRID_START, "evaluationStart": EVALUATION_START, "analysisEnd": ANALYSIS_END,
            "buyCost": US_BUY_COST, "sellCost": US_SELL_COST, "spreadLag": K.FRED_LAG_DAYS, "vixLag": K.FRED_LAG_DAYS, "cashLag": K.FRED_LAG_DAYS,
            "economic": economic, "diagnostics": diagnostics}


def kr_sealed_config():
    """The sealed KR study's configuration, for the equivalence audit only (KR costs, KR window, no added reading or diagnostic)."""
    return {"market": "KR", "gridStart": "1900-01-01", "evaluationStart": K.EVALUATION_START, "analysisEnd": "2026-09-17",
            "buyCost": K.BUY_COST, "sellCost": K.SELL_COST, "spreadLag": K.FRED_LAG_DAYS, "vixLag": K.FRED_LAG_DAYS, "cashLag": K.FRED_LAG_DAYS,
            "economic": False, "diagnostics": False}
