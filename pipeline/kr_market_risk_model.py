"""KR market risk model v1 — the pure model (MARKET layer only: HOW MUCH KR equity risk, never which industry or which stock).

EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY. The Market Risk Model v1 design is informed by outcome-exposed Market Anatomy v2 and
therefore all historical performance from this model remains DEVELOPMENT / EXPLORATORY evidence. Nothing here validates, predicts or promotes.

No I/O, no network, no fit. Functions receive series and return tables. The output of the model is ONE number per decision date,
`equityRiskMultiplier` in {1.0, 0.7, 0.4}: 1.0 = the normal equity risk budget, below 1.0 = partial de-risking, never leverage.

Rules that run through every function and are tested on synthetic data:

* THREE LAYERS, ALL INHERITED. SLOW = the sealed anatomy's post-inversion re-steepening flag (10y-3m > 0 now and < 0 somewhere in the last 504
  sessions), sampled at month-ends. TRANSITION = VIX level in the top fifth of its own past-only weekly history (the anatomy's HIGH state, 0.80,
  minimum 156 weekly observations). FAST = the existing overlay count: close < mean of the last 200 closes, plus annualised vol63 > 25%. No window,
  threshold or lag is new; every one is imported from `kr_market_risk_anatomy`.
* A 2 x 2 LADDER ON ONE VOCABULARY. C0 is the existing overlay (FAST only). Two structural switches are added: GATING (a single FAST warning needs
  SLOW or TRANSITION confirmation before it reduces anything) and PREEMPTION (SLOW and TRANSITION both adverse step the budget down one level, even
  with no FAST break). C1 = gating, C2 = preemption, C3 = both, which is exactly the multi-layer consensus count. Every rung moves one thing and every
  candidate uses only 1.0 / 0.7 / 0.4.
* MISSING IS NEITHER BENIGN NOR ADVERSE. A candidate's multiplier is defined only when every completion of the missing layers gives the same answer;
  otherwise the candidate holds its previous target (no information, no action) and the hold is counted.
* RE-ENTRY IS THE SAME STATE MACHINE. The multiplier is a memoryless function of today's observable states; normal exposure resumes at the first
  decision date whose state maps to 1.0. No trough, no rebound threshold, no minimum hold, no knowledge of the future.
* A STATE AT t IS END-DATE INVARIANT. Weekly and monthly sampling dates come from the exchange calendar (a session whose next session lies in a later
  week / month), never from where the data happen to stop, and every input is the value already known at t.
* SIGNAL AT CLOSE t, TRADE AT THE NEXT SESSION'S CLOSE. Holdings drift between trades; a trade happens only when the target changes; buys and sells
  pay the repository's KR costs from cash; cash earns zero.
"""
from __future__ import annotations

import itertools
import math

import numpy as np
import pandas as pd

from . import kr_market_risk_anatomy as M

STUDY = "kr-market-risk-model-v1"
MODEL_VERSION = "kr-market-risk-model-v1"
SCIENTIFIC_STATUS = M.SCIENTIFIC_STATUS
DEVELOPMENT_STATEMENT = ("The Market Risk Model v1 design is informed by outcome-exposed Market Anatomy v2 and therefore all historical performance from this "
                         "model remains DEVELOPMENT / EXPLORATORY evidence.")
ANNUALISATION = M.ANNUALISATION

# ---- the one multiplier vocabulary (the existing overlay's, unchanged) ---------------------------------------------------------------------------
LEVELS = tuple(float(x) for x in M.OVERLAY_MULTIPLIERS)          # (1.0, 0.7, 0.4)
FULL, REDUCED, MINIMUM = LEVELS

# ---- layers (every constant inherited from the sealed anatomy) -----------------------------------------------------------------------------------
LAYERS = ("SLOW", "TRANSITION", "FAST")
SLOW_FEATURE = "slow_resteepening_flag_10y3m"
SLOW_CADENCE = "M"
TRANSITION_FEATURE = "trans_vix_level"
TRANSITION_CADENCE = "W"
TRANSITION_HIGH_PERCENTILE = M.HIGH_STATE_PERCENTILE
TRANSITION_MIN_OBS = M.MIN_NORMALISATION_OBS["W"]
FAST_TREND_WINDOW = 200
FAST_VOL_WINDOW = 63
FAST_VOL_THRESHOLD = M.OVERLAY_VOL_THRESHOLD
INVERSION_LOOKBACK_SESSIONS = M.INVERSION_LOOKBACK_SESSIONS
FRED_LAG_DAYS = M.LAG_CALENDAR_DAYS["FRED_DAILY_MARKET"]
FRED_STALE_DAYS = M.FRED_DAILY_STALE_DAYS
DECISION_CADENCE = "W"
STATE_VALUES = {"SLOW": (0, 1), "TRANSITION": (0, 1), "FAST": (0, 1, 2)}

# ---- the candidate ladder --------------------------------------------------------------------------------------------------------------------------
CANDIDATES = {
    "C0": {"name": "C0_EXISTING_BASELINE_CONTROL", "layers": ("FAST",), "gating": False, "preemption": False,
           "hypothesis": "the existing SMA200 + Vol63 overlay: 1.0 / 0.7 / 0.4 by the FAST count; the control, unchanged"},
    "C1": {"name": "C1_CONFIRMATION_GATED", "layers": LAYERS, "gating": True, "preemption": False,
           "hypothesis": "false alarms fall if a single FAST warning needs SLOW or TRANSITION confirmation; slow or transition stress alone never acts; "
                         "a severe FAST break (both legs) acts without waiting"},
    "C2": {"name": "C2_PREEMPTIVE_HIERARCHICAL", "layers": LAYERS, "gating": False, "preemption": True,
           "hypothesis": "lateness falls if SLOW and TRANSITION both adverse step the budget down one level before FAST breaks; slow alone is only an "
                         "observation; once FAST deteriorates the reduction is stronger"},
    "C3": {"name": "C3_MULTI_LAYER_CONSENSUS", "layers": LAYERS, "gating": True, "preemption": True,
           "hypothesis": "agreement across independent layers balances early warning against false alarms: one isolated adverse family does nothing, "
                         "two adverse families 0.7, three 0.4, and a severe FAST break is never diluted by benign slow data"},
}
CANDIDATE_ORDER = ("C0", "C1", "C2", "C3")
CONTROL = "C0"
PASSIVE = "PASSIVE_FULL_EXPOSURE"                # always 1.0; a dominance reference, never a candidate

# ---- portfolio and cost (repository KR conventions, unchanged) ----------------------------------------------------------------------------------
BUY_COST = 0.0015
SELL_COST = 0.0045
COST_STRESS = (1.0, 2.0, 3.0)
CASH_RATE = "ZERO_KRW_NOMINAL"

# ---- evaluation (frozen before any outcome) ------------------------------------------------------------------------------------------------------
EVALUATION_START = "2007-01-01"                  # first decision date on or after this; 2006 (the anatomy's quality-window start) is warm-up
FALSE_ALARM_HORIZON = 63
FALSE_ALARM_LOSS_CUT = M.LOSS_CUTS[0]            # -10%: an activation is a false alarm when the reference never falls 10% within H63 of it
ROLLING_LOSS_HORIZONS = (63, 126)
REBOUND_HORIZONS = (63, 126)
EPISODE_THRESHOLDS = M.EPISODE_THRESHOLDS
PRIMARY_EPISODE_THRESHOLD = M.PRIMARY_EPISODE_THRESHOLD

# ---- decision (frozen before any outcome; Pareto first, symmetric bands versus C0, no weighted utility) -----------------------------------------
DOMINANCE_AXES = (("netAnnualizedReturn", "HIGHER"), ("maxDrawdown", "HIGHER"), ("reducedSessionShare", "LOWER"))
# Two economically distinct routes to a nomination, one symmetric band each. Round development tolerances fixed before any candidate outcome.
RETURN_BAND = 0.005                              # 0.50 pp per year of net annualized return: the non-inferiority margin AND the meaningful-improvement margin
MEANINGFUL_DRAWDOWN_IMPROVEMENT = 0.10           # |MDD| at most 90% of C0's |MDD| (protection route) ...
NON_INFERIORITY_DRAWDOWN_BAND = 0.10             # ... and at most 110% of it for non-inferiority (efficiency route)
BAND_EPSILON = 1e-12                             # a value exactly on a band edge counts as inside it despite float representation
NOMINATION_NONE = "NO_CANDIDATE_NOMINATED_CONTROL_RETAINED"
NOMINATION_TRADEOFF = "NO_UNAMBIGUOUS_NOMINATION_PARETO_TRADEOFF"
ROUTES = ("EFFICIENCY_ROUTE", "PROTECTION_ROUTE")

FORBIDDEN_OUTPUT_KEY_FRAGMENTS = ("winner", "optimal", "best", "promot", "validated", "verdict", "passfail", "recommend", "productionready",
                                  "timingrule", "proven", "alpha")


# =======================================================================================================================================
# Candidate rules
# =======================================================================================================================================
def rule(candidate, slow, transition, fast):
    """The frozen deterministic mapping for fully observed states (slow, transition in {0,1}; fast in {0,1,2})."""
    spec = CANDIDATES[candidate]
    if fast == 2:
        return MINIMUM
    index = 1 if fast == 1 else 0
    if fast == 1 and spec["gating"] and not (slow or transition):
        index = 0
    if spec["preemption"] and slow and transition:
        index += 1
    return LEVELS[min(index, 2)]


def consensus_rule(slow, transition, fast):
    """C3 written as the multi-layer consensus count it is: a severe FAST break is 0.4; otherwise count adverse families (SLOW, TRANSITION, FAST >= 1)
    and map 0 or 1 -> 1.0, 2 -> 0.7, 3 -> 0.4. A test proves it equals `rule('C3', ...)` on all twelve cells."""
    if fast == 2:
        return MINIMUM
    return (FULL, FULL, REDUCED, MINIMUM)[int(slow) + int(transition) + int(fast == 1)]


def _missing(value):
    return value is None or (isinstance(value, float) and not math.isfinite(value))


def multiplier(candidate, slow, transition, fast):
    """The candidate's multiplier, or None when the missing layers it reads could change the answer. A layer the candidate does not read never makes
    it undefined; a missing layer whose every completion gives the same answer is harmless. Missing is never read as benign or as adverse."""
    given = {"SLOW": slow, "TRANSITION": transition, "FAST": fast}
    for layer, value in given.items():
        if not _missing(value) and int(value) not in STATE_VALUES[layer]:
            raise ValueError("STATE_OUTSIDE_FROZEN_DOMAIN: " + layer)
    options = [STATE_VALUES[layer] if _missing(given[layer]) and layer in CANDIDATES[candidate]["layers"] else
               ((0,) if _missing(given[layer]) else (int(given[layer]),)) for layer in LAYERS]
    answers = {rule(candidate, s, t, f) for s, t, f in itertools.product(*options)}
    return answers.pop() if len(answers) == 1 else None


def mapping_table(candidate):
    """All twelve fully observed cells, in a fixed order (frozen into the spec and compared on every load)."""
    return [{"slow": s, "transition": t, "fast": f, "equityRiskMultiplier": rule(candidate, s, t, f)}
            for s, t, f in itertools.product(STATE_VALUES["SLOW"], STATE_VALUES["TRANSITION"], STATE_VALUES["FAST"])]


# =======================================================================================================================================
# Calendar-anchored sampling (end-date invariant)
# =======================================================================================================================================
def period_end_sessions(sessions, frequency):
    """Sessions whose NEXT KR session (from the exchange calendar, known in advance) lies in a later week ('W') or month ('M'). Unlike grouping the
    sessions that happen to be present, this never marks the last available session as a period end, so a sampling date does not move when the data
    end earlier or later."""
    days = pd.DatetimeIndex(sessions)
    if len(days) == 0:
        return days
    calendar = M.kr_sessions(str(days[0].date()), str((days[-1] + pd.Timedelta(days=45)).date()))
    position = calendar.get_indexer(days)
    if (position < 0).any():
        raise ValueError("SESSION_NOT_ON_THE_KR_CALENDAR")
    if position.max() + 1 >= len(calendar):
        raise ValueError("CALENDAR_TOO_SHORT")
    following = calendar[position + 1]
    is_end = days.to_period(frequency) != following.to_period(frequency)
    return days[np.asarray(is_end)]


def _carry(sampled, sessions):
    """Latest sampled value at or before each session (label-based: a NaN on the latest sampling date stays NaN, it is never skipped over)."""
    return pd.Series(sampled, dtype=float).reindex(pd.DatetimeIndex(sessions), method="ffill")


# =======================================================================================================================================
# Layer states
# =======================================================================================================================================
def fast_states(close):
    """FAST layer on every session: count (0/1/2), trend leg, vol leg and vol63, from the literal replica of `kr_market_risk_overlay.state_at`
    (`kr_market_risk_anatomy.overlay_state_from_window`). NaN where the existing rule is DATA_INSUFFICIENT."""
    c = pd.Series(close, dtype=float)
    values = c.to_numpy()
    out = {k: np.full(len(c), np.nan) for k in ("fast", "trendAdverse", "volAdverse", "vol63")}
    for i in range(FAST_TREND_WINDOW, len(c)):
        state = M.overlay_state_from_window(values[i - FAST_TREND_WINDOW:i + 1])
        if state["status"] == "READY":
            out["fast"][i], out["trendAdverse"][i] = state["count"], float(state["trendAdverse"])
            out["volAdverse"][i], out["vol63"][i] = float(state["volAdverse"]), state["benchmarkVol63"]
    return pd.DataFrame(out, index=c.index)


def slow_states(spread_obs, sessions, lag_days=FRED_LAG_DAYS):
    """SLOW layer: the anatomy's re-steepening flag on the known 10y-3m spread, sampled at calendar month-ends and carried to every session."""
    days = pd.DatetimeIndex(sessions)
    known = M.known_on_sessions(spread_obs, days, lag_days, FRED_STALE_DAYS)[0]
    daily = M.slow_features({"spread_10y3m": known}, days)[SLOW_FEATURE]
    ends = period_end_sessions(days, SLOW_CADENCE)
    return _carry(daily.reindex(ends), days), _carry(known.reindex(ends), days)


def transition_states(vix_obs, sessions, lag_days=FRED_LAG_DAYS):
    """TRANSITION layer: past-only expanding percentile of the known VIX level on calendar week-ends (>= 156 observations), adverse at >= 0.80."""
    days = pd.DatetimeIndex(sessions)
    known = M.known_on_sessions(vix_obs, days, lag_days, FRED_STALE_DAYS)[0]
    ends = period_end_sessions(days, TRANSITION_CADENCE)
    weekly = known.reindex(ends)
    pct = M.expanding_percentile(weekly.to_numpy(), TRANSITION_MIN_OBS)
    pct.index = ends
    adverse = (pct >= TRANSITION_HIGH_PERCENTILE).astype(float).where(pct.notna())
    return _carry(adverse, days), _carry(pct, days), _carry(weekly, days)


def layer_states(close, spread_obs, vix_obs, sessions, spread_lag=FRED_LAG_DAYS, vix_lag=FRED_LAG_DAYS):
    """Every layer on the KR session grid. `close` is the reference close indexed by session (NaN = missing session); `spread_obs` and `vix_obs` are
    observation-dated series. Nothing after a session can reach that session's row."""
    days = pd.DatetimeIndex(sessions)
    fast = fast_states(pd.Series(close, dtype=float).reindex(days))
    slow, spread = slow_states(spread_obs, days, spread_lag)
    transition, pct, vix = transition_states(vix_obs, days, vix_lag)
    out = fast.copy()
    out["slow"], out["spreadAtSample"] = slow.to_numpy(), spread.to_numpy()
    out["transition"], out["vixPercentile"], out["vixAtSample"] = transition.to_numpy(), pct.to_numpy(), vix.to_numpy()
    return out


# =======================================================================================================================================
# Decisions and targets
# =======================================================================================================================================
def decision_schedule(sessions, start, end):
    """Weekly decision dates (calendar week-end sessions) on or after `start` whose execution session (the NEXT KR session) is on or before `end`."""
    days = pd.DatetimeIndex(sessions)
    calendar = M.kr_sessions(str(days[0].date()), str((pd.Timestamp(end) + pd.Timedelta(days=45)).date()))
    ends = period_end_sessions(days[days <= pd.Timestamp(end)], DECISION_CADENCE)
    rows = []
    for d in ends[ends >= pd.Timestamp(start)]:
        execution = calendar[calendar.get_loc(d) + 1]
        if execution <= pd.Timestamp(end):
            rows.append({"decisionDate": d, "executionDate": execution})
    return pd.DataFrame(rows, columns=["decisionDate", "executionDate"])


def _cell(value):
    return None if _missing(value) else int(value)


def candidate_targets(states, schedule, candidate):
    """Targets on each decision date. Undefined -> hold the previous target (counted); undefined on the FIRST decision date is refused."""
    rows, previous = [], None
    for d in schedule["decisionDate"]:
        row = states.loc[d]
        m = multiplier(candidate, _cell(row["slow"]), _cell(row["transition"]), _cell(row["fast"]))
        held = m is None
        if held:
            if previous is None:
                raise ValueError("STATE_UNAVAILABLE_AT_FIRST_DECISION: " + candidate)
            m = previous
        rows.append({"decisionDate": d, "target": m, "heldForMissingState": held})
        previous = m
    return pd.DataFrame(rows)


def determinable_share(states, schedule, candidate):
    """Share of decision dates on which the candidate's multiplier is defined (presence only; the readiness gate)."""
    flags = [multiplier(candidate, _cell(states.loc[d, "slow"]), _cell(states.loc[d, "transition"]), _cell(states.loc[d, "fast"])) is not None
             for d in schedule["decisionDate"]]
    return {"decisionDates": len(flags), "determinable": int(sum(flags)), "share": (sum(flags) / len(flags)) if flags else None,
            "firstDecisionDeterminable": bool(flags[0]) if flags else False}


# =======================================================================================================================================
# Path replay (one asset: the reference, scaled by the multiplier; the rest in zero-rate cash)
# =======================================================================================================================================
def trade_to_target(equity, cash, target, buy_cost, sell_cost):
    """Exact post-cost rebalance at one close: afterwards equity / NAV == target, with costs paid from cash. Returns (equity, cash, signed notional,
    cost), notional and cost in currency."""
    nav = equity + cash
    if target * nav > equity:
        buy = (target * nav - equity) / (1.0 + target * buy_cost)
        return equity + buy, cash - buy - buy_cost * buy, buy, buy_cost * buy
    if target * nav < equity:
        sell = (equity - target * nav) / (1.0 - target * sell_cost)
        return equity - sell, cash + sell - sell_cost * sell, -sell, sell_cost * sell
    return equity, cash, 0.0, 0.0


def replay_path(close, schedule, targets, stress=1.0, buy_cost=BUY_COST, sell_cost=SELL_COST):
    """Start at NAV 1 on the close of the first execution session holding the first target (the initial build is not a rebalance and is not charged).
    On every later session the carried holding earns the reference return; on an execution session whose target differs from the current target the
    book trades at that close to exactly the target share of post-cost NAV. Drift is never traded away while the target is unchanged."""
    if not math.isfinite(stress) or stress < 0:
        raise ValueError("INVALID_COST_STRESS")
    targets = list(targets)
    if any(not (0.0 <= t <= 1.0) for t in targets):
        raise ValueError("NO_LEVERAGE_MULTIPLIER_REQUIRED")
    executions = dict(zip(pd.DatetimeIndex(schedule["executionDate"]), targets))
    first = pd.Timestamp(schedule["executionDate"].iloc[0])
    c = pd.Series(close, dtype=float)
    c = c[c.index >= first]
    if not np.isfinite(c.to_numpy()).all() or (c <= 0).any():
        raise ValueError("REFERENCE_PATH_HAS_A_MISSING_OR_INVALID_SESSION")
    current = targets[0]
    equity, cash = current, 1.0 - current
    rows = [{"date": first, "nav": 1.0, "weightStart": current, "weightEnd": current, "target": current, "notional": 0.0, "cost": 0.0, "dailyReturn": np.nan}]
    for prev, day in zip(c.index[:-1], c.index[1:]):
        nav_before = equity + cash
        weight_start = equity / nav_before
        equity *= c.loc[day] / c.loc[prev]
        notional = cost = 0.0
        pre_trade_nav = equity + cash
        if day in executions and executions[day] != current:
            current = executions[day]
            equity, cash, notional, cost = trade_to_target(equity, cash, current, buy_cost * stress, sell_cost * stress)
        nav = equity + cash
        rows.append({"date": day, "nav": nav, "weightStart": weight_start, "weightEnd": equity / nav, "target": current,
                     "notional": notional / pre_trade_nav, "cost": cost / pre_trade_nav, "dailyReturn": nav / nav_before - 1.0})
    return pd.DataFrame(rows).set_index("date")


# =======================================================================================================================================
# Metrics (every one frozen before outcomes; overlapping windows are descriptive)
# =======================================================================================================================================
def annualized(growth, sessions):
    return float(growth ** (ANNUALISATION / sessions) - 1.0) if sessions > 0 and growth > 0 else None


def max_drawdown(nav):
    v = pd.Series(nav, dtype=float).to_numpy()
    running = np.maximum.accumulate(v)
    dd = v / running - 1.0
    trough = int(np.argmin(dd))
    peak = int(np.argmax(v[:trough + 1])) if trough > 0 else 0
    later = np.flatnonzero(v[trough:] >= v[peak])
    recovery = trough + int(later[0]) if len(later) and dd[trough] < 0 else None
    return {"maxDrawdown": float(dd[trough]), "peakPos": peak, "troughPos": trough, "recoveryPos": recovery,
            "recoverySessions": (recovery - trough) if recovery is not None else None}


def worst_rolling_return(nav, horizon):
    v = pd.Series(nav, dtype=float).to_numpy()
    if len(v) <= horizon:
        return None
    return float((v[horizon:] / v[:-horizon] - 1.0).min())


def downside_volatility(returns):
    r = pd.Series(returns, dtype=float).dropna().to_numpy()
    return float(math.sqrt(np.mean(np.minimum(r, 0.0) ** 2)) * math.sqrt(ANNUALISATION)) if len(r) else None


def participation(returns, bench_returns):
    r, b = pd.Series(returns, dtype=float), pd.Series(bench_returns, dtype=float)
    ok = r.notna() & b.notna()
    up, down = ok & (b > 0), ok & (b < 0)
    return {"upside": float(r[up].mean() / b[up].mean()) if up.any() else None,
            "downside": float(r[down].mean() / b[down].mean()) if down.any() else None}


def episodes_in_window(bench_close):
    return M.underwater_episodes(pd.Series(bench_close, dtype=float))


def episode_capture(path, bench_close, episodes):
    """Per algorithmic reference episode: candidate return from the reference peak to the reference trough against the reference depth, the avoided
    loss, and the candidate's own sessions from the reference trough until its NAV regains its value at the reference peak (None if censored)."""
    nav = path["nav"].to_numpy()
    dates = path.index
    out = []
    for e in episodes:
        p, t = e["peakPos"], e["troughPos"]
        candidate = nav[t] / nav[p] - 1.0
        later = np.flatnonzero(nav[t:] >= nav[p])
        out.append({"peakDate": str(dates[p].date()), "troughDate": str(dates[t].date()), "referenceDepth": float(e["depth"]),
                    "referenceRecoveryDate": None if e["recoveryPos"] is None else str(dates[e["recoveryPos"]].date()), "censored": bool(e["censored"]),
                    "candidatePeakToTrough": float(candidate), "lossCaptureRatio": float(candidate / e["depth"]),
                    "avoidedLoss": float(candidate - e["depth"]), "sessionsToRegainPeakValue": int(later[0]) if len(later) else None})
    return out


def rebound_cost(path, bench_close, episodes):
    """Per episode trough: reference minus candidate return over H63/H126 after the trough (PENDING past the end), sessions until the target is back at
    1.0 (0 if already 1.0 at the trough, None if never in the sample), and reference minus candidate return from the trough to the reference recovery
    (to the end of the sample when censored)."""
    nav, close, target = path["nav"].to_numpy(), pd.Series(bench_close, dtype=float).to_numpy(), path["target"].to_numpy()
    out = []
    for e in episodes:
        t = e["troughPos"]
        row = {"troughDate": str(path.index[t].date())}
        for h in REBOUND_HORIZONS:
            row[f"reboundMissedH{h}"] = (float((close[t + h] / close[t] - 1.0) - (nav[t + h] / nav[t] - 1.0)) if t + h < len(nav) else None)
        full = np.flatnonzero(target[t:] >= FULL)
        row["sessionsUntilFullExposure"] = int(full[0]) if len(full) else None
        end = e["recoveryPos"] if e["recoveryPos"] is not None else len(nav) - 1
        row["recoveryOpportunityCost"] = float((close[end] / close[t] - 1.0) - (nav[end] / nav[t] - 1.0))
        row["recoveryWindowCensored"] = e["recoveryPos"] is None
        out.append(row)
    return out


def false_alarm_profile(path, forward_worst_loss):
    """Activations = sessions where the target falls from 1.0 to below 1.0 (plus a start below 1.0). An activation is a false alarm when the reference's
    forward worst loss over H63 from that session stays above -10%; activations whose window has not matured are PENDING and excluded. Also the share of
    reduced-target sessions not followed by a -10% loss within H63 (matured sessions only)."""
    target = path["target"].to_numpy()
    worst = pd.Series(forward_worst_loss, dtype=float).reindex(path.index).to_numpy()
    reduced = target < FULL
    onset = reduced & np.concatenate(([True], ~reduced[:-1]))
    matured = np.isfinite(worst)
    false = onset & matured & (worst > FALSE_ALARM_LOSS_CUT)
    quiet = reduced & matured & (worst > FALSE_ALARM_LOSS_CUT)
    return {"activations": int(onset.sum()), "maturedActivations": int((onset & matured).sum()), "pendingActivations": int((onset & ~matured).sum()),
            "falseAlarms": int(false.sum()), "falseAlarmShare": (float(false.sum() / (onset & matured).sum()) if (onset & matured).any() else None),
            "reducedSessions": int(reduced.sum()), "reducedSessionsWithoutSubsequentLargeLoss": int(quiet.sum()),
            "shareOfMaturedSessionsReducedWithoutSubsequentLargeLoss": (float(quiet.sum() / matured.sum()) if matured.any() else None)}


def implementation_cost(path):
    """Trades caused by multiplier changes only: switch count, traded notional (sum of |trade| as a share of pre-trade NAV), one-way turnover
    ((buys + sells) / 2, the repository convention), its annual rate, and the summed cost share."""
    switches = int((path["notional"] != 0).sum())
    traded = float(path["notional"].abs().sum())
    years = (len(path) - 1) / ANNUALISATION
    return {"multiplierSwitches": switches, "tradedNotional": traded, "oneWayTurnover": traded / 2.0,
            "annualizedOneWayTurnover": (traded / 2.0 / years) if years > 0 else None, "totalCostFractionOfNav": float(path["cost"].sum())}


def path_summary(path, passive):
    n = len(path) - 1
    nav, ret = path["nav"], path["dailyReturn"]
    mdd = max_drawdown(nav)
    target = path["target"]
    return {"sessions": n, "cumulativeReturn": float(nav.iloc[-1] / nav.iloc[0] - 1.0), "annualizedReturn": annualized(nav.iloc[-1] / nav.iloc[0], n),
            "annualizedVolatility": float(ret.std(ddof=1) * math.sqrt(ANNUALISATION)), "downsideVolatility": downside_volatility(ret),
            "maxDrawdown": mdd["maxDrawdown"], "maxDrawdownPeak": str(nav.index[mdd["peakPos"]].date()), "maxDrawdownTrough": str(nav.index[mdd["troughPos"]].date()),
            "maxDrawdownRecoverySessions": mdd["recoverySessions"],
            **{f"worstRollingReturnH{h}": worst_rolling_return(nav, h) for h in ROLLING_LOSS_HORIZONS},
            "participation": participation(ret, passive["dailyReturn"]), "averageEquityWeight": float(path["weightStart"].iloc[1:].mean()),
            "targetShare": {str(level): float((target == level).mean()) for level in LEVELS}, "reducedSessionShare": float((target < FULL).mean())}


def halves(path, passive):
    """Chronological halves of the evaluation sessions (split at the middle session); each half rebased, descriptive only."""
    mid = (len(path) - 1) // 2
    out = {}
    for label, sl in (("firstHalf", slice(0, mid + 1)), ("secondHalf", slice(mid, len(path)))):
        sub, ref = path.iloc[sl], passive.iloc[sl]
        out[label] = {"start": str(sub.index[0].date()), "end": str(sub.index[-1].date()),
                      "annualizedReturn": annualized(sub["nav"].iloc[-1] / sub["nav"].iloc[0], len(sub) - 1), "maxDrawdown": max_drawdown(sub["nav"])["maxDrawdown"],
                      "reducedSessionShare": float((sub["target"] < FULL).mean()),
                      "passiveAnnualizedReturn": annualized(ref["nav"].iloc[-1] / ref["nav"].iloc[0], len(ref) - 1),
                      "passiveMaxDrawdown": max_drawdown(ref["nav"])["maxDrawdown"]}
    return out


def calendar_years(path):
    """Descriptive calendar-year returns (the first and last years are partial). Never redefines a rule."""
    nav = path["nav"]
    out, previous = {}, nav.iloc[0]
    for year, g in nav.groupby(nav.index.year):
        out[str(year)] = float(g.iloc[-1] / previous - 1.0)
        previous = g.iloc[-1]
    return out


def summarise_episodes(rows, key):
    values = [r[key] for r in rows if r.get(key) is not None]
    return {"episodes": len(rows), "measured": len(values), "mean": float(np.mean(values)) if values else None,
            "median": float(np.median(values)) if values else None}


# =======================================================================================================================================
# The preregistered decision (Pareto first; symmetric non-inferiority / meaningful-improvement bands versus C0; no forced winner)
# =======================================================================================================================================
def dominates(a, b):
    """a dominates b: at least as good on every axis and strictly better on one."""
    better = equal = 0
    for axis, direction in DOMINANCE_AXES:
        x, y = a[axis], b[axis]
        if x is None or y is None:
            return False
        if x == y:
            equal += 1
        elif (x > y) == (direction == "HIGHER"):
            better += 1
        else:
            return False
    return better > 0


def development_nomination(summaries):
    """`summaries`: {id: {netAnnualizedReturn, maxDrawdown, reducedSessionShare}} for C0..C3 and PASSIVE_FULL_EXPOSURE.

    1. PARETO ELIMINATION. A candidate dominated by any other candidate or by the passive reference is eliminated.
    2. NON-INFERIORITY versus C0, BOTH required: net annualized return >= C0's - 0.50 pp, and |maxDrawdown| <= 1.10 x |C0 maxDrawdown|.
    3. AT LEAST ONE MEANINGFUL IMPROVEMENT versus C0:
         EFFICIENCY_ROUTE  net annualized return >= C0's + 0.50 pp (drawdown being non-inferior), or
         PROTECTION_ROUTE  |maxDrawdown| <= 0.90 x |C0 maxDrawdown| (return being non-inferior).
    4. Exactly one survivor -> it is the development nomination. No survivor -> NO_CANDIDATE_NOMINATED_CONTROL_RETAINED. More than one survivor
       -> NO_UNAMBIGUOUS_NOMINATION_PARETO_TRADEOFF: survivors are mutually non-dominated (step 1 removed every dominated candidate), so choosing
       among them would need a preference between the hypotheses (fewer false alarms, less lateness, both) that this protocol does not own. No
       simplicity order, return ranking or utility is applied; every candidate stays in the prospective receipts either way.
    A nomination is DEVELOPMENT evidence for later integration, never validation."""
    pool = {k: v for k, v in summaries.items()}
    control = pool[CONTROL]
    dominated = {k: sorted(o for o in pool if o != k and dominates(pool[o], pool[k])) for k in CANDIDATE_ORDER}
    c_ret, c_dd = control["netAnnualizedReturn"], control["maxDrawdown"]
    steps = {}
    for k in CANDIDATE_ORDER[1:]:
        r, dd = pool[k]["netAnnualizedReturn"], pool[k]["maxDrawdown"]
        known = None not in (r, dd, c_ret, c_dd)
        return_ok = known and r >= c_ret - RETURN_BAND - BAND_EPSILON
        drawdown_ok = known and abs(dd) <= (1.0 + NON_INFERIORITY_DRAWDOWN_BAND) * abs(c_dd) + BAND_EPSILON
        return_better = known and r >= c_ret + RETURN_BAND - BAND_EPSILON
        drawdown_better = known and abs(dd) <= (1.0 - MEANINGFUL_DRAWDOWN_IMPROVEMENT) * abs(c_dd) + BAND_EPSILON
        non_inferior = bool(return_ok and drawdown_ok)
        routes = [name for name, hit in (("EFFICIENCY_ROUTE", return_better), ("PROTECTION_ROUTE", drawdown_better)) if hit]
        steps[k] = {"dominatedBy": dominated[k], "returnNonInferiorVersusControl": bool(return_ok), "drawdownNonInferiorVersusControl": bool(drawdown_ok),
                    "meaningfulReturnImprovementVersusControl": bool(return_better), "meaningfulDrawdownImprovementVersusControl": bool(drawdown_better),
                    "routes": routes if non_inferior else [], "survives": bool(not dominated[k] and non_inferior and routes)}
    survivors = [k for k in CANDIDATE_ORDER[1:] if steps[k]["survives"]]
    out = {"survivors": survivors, "steps": steps, "controlDominatedBy": dominated[CONTROL]}
    if not survivors:
        return {"developmentNomination": NOMINATION_NONE, **out}
    if len(survivors) > 1:
        return {"developmentNomination": NOMINATION_TRADEOFF, "mutuallyNonDominatedSurvivors": survivors, **out}
    return {"developmentNomination": survivors[0], **out}


def assert_no_forbidden_keys(value, path=""):
    if isinstance(value, dict):
        for key, inner in value.items():
            if any(f in str(key).lower().replace("_", "") for f in FORBIDDEN_OUTPUT_KEY_FRAGMENTS):
                raise ValueError("FORBIDDEN_OUTPUT_KEY: " + path + "/" + str(key))
            assert_no_forbidden_keys(inner, path + "/" + str(key))
    elif isinstance(value, (list, tuple)):
        for inner in value:
            assert_no_forbidden_keys(inner, path)
    return True
