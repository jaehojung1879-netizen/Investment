"""kr-market-risk-model-v1: the pure model. Synthetic series only; no test reads a historical market value or computes a historical outcome."""
import ast
import inspect
import itertools
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from pipeline import kr_market_risk_anatomy as M
from pipeline import kr_market_risk_model as K
from pipeline import kr_market_risk_overlay as O

ROOT = Path(__file__).resolve().parents[1]
CELLS = list(itertools.product((0, 1), (0, 1), (0, 1, 2)))


def synthetic(start="2004-01-02", end="2012-12-28", seed=7, crash=("2008-06-02", "2008-12-01")):
    """A random-walk reference with one violent segment (so every FAST count occurs), a VIX-like series and a 10y-3m spread that inverts and
    re-steepens (so every SLOW and TRANSITION state occurs)."""
    rng = np.random.default_rng(seed)
    sessions = M.kr_sessions(start, end)
    r = rng.normal(0.0004, 0.01, len(sessions))
    hit = (sessions >= pd.Timestamp(crash[0])) & (sessions <= pd.Timestamp(crash[1]))
    r[hit] = rng.normal(-0.004, 0.035, hit.sum())
    close = pd.Series(100 * np.exp(np.cumsum(r)), index=sessions)
    cal = pd.bdate_range(pd.Timestamp(start) - pd.Timedelta(days=4000), end)
    vix = pd.Series(18 + 6 * np.sin(np.arange(len(cal)) / 90.0) + rng.normal(0, 1, len(cal)), index=cal)
    vix[(cal >= pd.Timestamp(crash[0])) & (cal <= pd.Timestamp(crash[1]))] += 30
    spread = pd.Series(1.5 * np.sin(np.arange(len(cal)) / 400.0), index=cal)
    return sessions, close, spread, vix


@pytest.fixture(scope="module")
def world():
    sessions, close, spread, vix = synthetic()
    return sessions, close, spread, vix, K.layer_states(close, spread, vix, sessions)


# ---------------------------------------------------------------------------------------------------------------------------------------
# Frozen rules
# ---------------------------------------------------------------------------------------------------------------------------------------
def test_slow_alone_and_transition_alone_never_reduce_exposure_in_any_candidate():
    for cid in K.CANDIDATE_ORDER:
        assert K.rule(cid, 1, 0, 0) == 1.0 and K.rule(cid, 0, 1, 0) == 1.0 and K.rule(cid, 0, 0, 0) == 1.0


def test_fast_states_map_exactly_as_preregistered():
    assert [K.rule("C0", s, t, f) for s, t in ((0, 0), (1, 1)) for f in (0, 1, 2)] == [1.0, 0.7, 0.4, 1.0, 0.7, 0.4]
    assert [K.rule("C1", 0, 0, f) for f in (0, 1, 2)] == [1.0, 1.0, 0.4]            # an unconfirmed mild warning does nothing
    assert K.rule("C1", 1, 0, 1) == K.rule("C1", 0, 1, 1) == K.rule("C1", 1, 1, 1) == 0.7
    assert K.rule("C2", 1, 1, 0) == 0.7 and K.rule("C2", 1, 1, 1) == 0.4 and K.rule("C2", 0, 0, 1) == 0.7
    assert K.rule("C3", 1, 1, 0) == 0.7 and K.rule("C3", 0, 0, 1) == 1.0 and K.rule("C3", 1, 1, 1) == 0.4
    for cid in K.CANDIDATE_ORDER:                                                  # a severe break is never diluted
        assert all(K.rule(cid, s, t, 2) == 0.4 for s in (0, 1) for t in (0, 1))


def test_c3_is_exactly_the_multi_layer_consensus_count_and_the_ladder_is_a_2x2():
    assert all(K.rule("C3", *cell) == K.consensus_rule(*cell) for cell in CELLS)
    flags = {cid: (K.CANDIDATES[cid]["gating"], K.CANDIDATES[cid]["preemption"]) for cid in K.CANDIDATE_ORDER}
    assert flags == {"C0": (False, False), "C1": (True, False), "C2": (False, True), "C3": (True, True)}
    tables = {cid: [c["equityRiskMultiplier"] for c in K.mapping_table(cid)] for cid in K.CANDIDATE_ORDER}
    assert len({tuple(v) for v in tables.values()}) == 4                           # four distinct architectures


def test_every_candidate_is_monotone_in_risk_uses_only_the_three_levels_and_never_exceeds_one():
    for cid in K.CANDIDATE_ORDER:
        for s, t, f in CELLS:
            m = K.rule(cid, s, t, f)
            assert m in K.LEVELS and m <= 1.0
            if s == 0:
                assert K.rule(cid, 1, t, f) <= m
            if t == 0:
                assert K.rule(cid, s, 1, f) <= m
            if f < 2:
                assert K.rule(cid, s, t, f + 1) <= m
    assert K.LEVELS == tuple(M.OVERLAY_MULTIPLIERS) == (1.0, 0.7, 0.4)


def test_every_layer_constant_is_the_sealed_anatomy_constant():
    assert (K.TRANSITION_HIGH_PERCENTILE, K.TRANSITION_MIN_OBS, K.FAST_VOL_THRESHOLD) == (M.HIGH_STATE_PERCENTILE, M.MIN_NORMALISATION_OBS["W"], M.OVERLAY_VOL_THRESHOLD)
    assert (K.INVERSION_LOOKBACK_SESSIONS, K.FRED_LAG_DAYS, K.FRED_STALE_DAYS) == (504, M.LAG_CALENDAR_DAYS["FRED_DAILY_MARKET"], M.FRED_DAILY_STALE_DAYS)
    assert K.SLOW_FEATURE in M.FEATURES and K.TRANSITION_FEATURE in M.FEATURES
    assert (K.FALSE_ALARM_LOSS_CUT, K.EPISODE_THRESHOLDS, K.PRIMARY_EPISODE_THRESHOLD) == (M.LOSS_CUTS[0], M.EPISODE_THRESHOLDS, M.PRIMARY_EPISODE_THRESHOLD)
    assert (K.BUY_COST, K.SELL_COST, K.COST_STRESS[1:]) == (0.0015, 0.0045, (2.0, 3.0))


# ---------------------------------------------------------------------------------------------------------------------------------------
# Missing data
# ---------------------------------------------------------------------------------------------------------------------------------------
def test_missing_is_neither_benign_nor_adverse_but_a_determinable_answer_is_kept():
    assert K.multiplier("C1", None, 0, 1) is None                  # 1.0 if SLOW is benign, 0.7 if adverse: undefined, never guessed
    assert K.multiplier("C2", 1, None, 1) is None                  # 0.7 or 0.4
    assert K.multiplier("C0", None, None, None) is None
    assert K.multiplier("C1", None, None, 0) == 1.0 and K.multiplier("C1", None, float("nan"), 2) == 0.4
    assert K.multiplier("C3", 0, None, 0) == 1.0                   # one family at most whatever T is
    assert K.multiplier("C0", None, None, 1) == 0.7                # C0 does not read SLOW or TRANSITION
    with pytest.raises(ValueError, match="STATE_OUTSIDE_FROZEN_DOMAIN"):
        K.multiplier("C0", 0, 0, 3)


def test_an_undefined_state_holds_the_previous_target_and_is_counted_and_undefined_first_is_refused():
    days = M.kr_sessions("2020-01-06", "2020-03-31")
    schedule = K.decision_schedule(days, "2020-01-01", "2020-03-31")
    states = pd.DataFrame({"slow": 0.0, "transition": 0.0, "fast": 1.0}, index=days)
    d = schedule["decisionDate"]
    states.loc[d.iloc[0], "slow"] = 1.0
    states.loc[d.iloc[2], "slow"] = np.nan
    t = K.candidate_targets(states, schedule, "C1")
    assert t["target"].tolist()[:4] == [0.7, 1.0, 1.0, 1.0] and t["heldForMissingState"].tolist()[:4] == [False, False, True, False]
    states.loc[d.iloc[0], "slow"] = np.nan
    with pytest.raises(ValueError, match="STATE_UNAVAILABLE_AT_FIRST_DECISION"):
        K.candidate_targets(states, schedule, "C1")
    assert K.candidate_targets(states, schedule, "C0")["target"].iloc[0] == 0.7     # C0 never reads SLOW


# ---------------------------------------------------------------------------------------------------------------------------------------
# No look-ahead and end-date invariance
# ---------------------------------------------------------------------------------------------------------------------------------------
def _same(a, b):
    return np.array_equal(a.to_numpy(float), b.to_numpy(float), equal_nan=True)


def test_state_at_t_is_identical_whether_the_data_end_at_t_or_years_later(world):
    sessions, close, spread, vix, full = world
    every = [K.layer_states(close, spread, vix, sessions).index]
    assert len(every[0]) == len(full)
    for cut in ("2007-03-14", "2008-09-30", "2010-06-15"):                         # a mid-week, a mid-crash and a mid-month end
        t = pd.Timestamp(cut)
        short = K.layer_states(close[close.index <= t], spread[spread.index <= t], vix[vix.index <= t], sessions[sessions <= t])
        for col in ("slow", "transition", "fast", "vixPercentile", "trendAdverse", "volAdverse"):
            assert _same(short[col], full.loc[short.index, col]), (cut, col)
    assert {0.0, 1.0} <= set(full["slow"].dropna()) and {0.0, 1.0} <= set(full["transition"].dropna()) and {0.0, 1.0, 2.0} <= set(full["fast"].dropna())


def test_a_future_shock_cannot_move_an_earlier_state_or_target(world):
    sessions, close, spread, vix, full = world
    t = pd.Timestamp("2009-06-30")
    shocked_close = close.where(close.index <= t, close * 0.3)
    shocked_vix = vix.where(vix.index <= t, vix + 80)
    shocked_spread = spread.where(spread.index <= t, -5.0)
    shocked = K.layer_states(shocked_close, shocked_spread, shocked_vix, sessions)
    for col in ("slow", "transition", "fast"):
        assert _same(shocked.loc[:t, col], full.loc[:t, col])
    schedule = K.decision_schedule(sessions, "2007-01-01", "2012-12-28")
    early = schedule["decisionDate"] <= t
    for cid in K.CANDIDATE_ORDER:
        a, b = K.candidate_targets(full, schedule, cid), K.candidate_targets(shocked, schedule, cid)
        assert a["target"][early].tolist() == b["target"][early].tolist()


def test_sampling_dates_come_from_the_calendar_not_from_where_the_data_stop():
    days = M.kr_sessions("2021-01-04", "2021-03-17")                              # ends on a Wednesday, mid-month
    weekly, monthly = K.period_end_sessions(days, "W"), K.period_end_sessions(days, "M")
    assert pd.Timestamp("2021-03-17") not in weekly and pd.Timestamp("2021-03-17") not in monthly
    assert pd.Timestamp("2021-01-29") in monthly and pd.Timestamp("2021-02-26") in monthly and pd.Timestamp("2021-03-12") in weekly
    schedule = K.decision_schedule(days, "2021-01-01", "2021-03-17")
    calendar = M.kr_sessions("2021-01-01", "2021-04-30")
    assert all(calendar[calendar.get_loc(d) + 1] == e for d, e in zip(schedule["decisionDate"], schedule["executionDate"]))
    assert schedule["executionDate"].max() <= pd.Timestamp("2021-03-17")


def test_re_entry_is_memoryless_and_uses_no_trough_or_future_information():
    days = M.kr_sessions("2020-01-06", "2020-06-30")
    schedule = K.decision_schedule(days, "2020-01-01", "2020-06-30")
    fast = [2, 2, 1, 1, 0, 0, 1, 0] + [0] * (len(schedule) - 8)
    states = pd.DataFrame({"slow": 0.0, "transition": 0.0, "fast": np.nan}, index=days)
    states.loc[schedule["decisionDate"], "fast"] = fast
    for cid, expected in (("C0", [0.4, 0.4, 0.7, 0.7, 1.0, 1.0, 0.7, 1.0]), ("C1", [0.4, 0.4, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0])):
        assert K.candidate_targets(states, schedule, cid)["target"].tolist()[:8] == expected
    assert "trough" not in inspect.signature(K.candidate_targets).parameters and "close" not in inspect.signature(K.multiplier).parameters


# ---------------------------------------------------------------------------------------------------------------------------------------
# The control is the existing overlay, exactly
# ---------------------------------------------------------------------------------------------------------------------------------------
def test_control_reproduces_the_existing_overlay_exactly():
    sessions, close, spread, vix = synthetic(start="2013-01-02", end="2015-12-30", crash=("2014-03-03", "2014-07-31"))
    benchmark = pd.DataFrame({"Close": close})
    fast = K.fast_states(close)
    checked = set()
    for date in sessions[200::7]:
        live = O.state_at(benchmark, str(date.date()))
        assert live["status"] == "READY"
        assert K.multiplier("C0", None, None, int(fast.loc[date, "fast"])) == live["riskMultiplier"]
        assert bool(fast.loc[date, "trendAdverse"]) == live["trendAdverse"] and bool(fast.loc[date, "volAdverse"]) == live["volAdverse"]
        checked.add(live["riskMultiplier"])
    assert checked == {1.0, 0.7, 0.4}


# ---------------------------------------------------------------------------------------------------------------------------------------
# Path replay and costs
# ---------------------------------------------------------------------------------------------------------------------------------------
def _flat(n_weeks=6):
    days = M.kr_sessions("2021-01-04", "2021-03-31")
    schedule = K.decision_schedule(days, "2021-01-01", "2021-03-31").iloc[:n_weeks].reset_index(drop=True)
    close = pd.Series(100.0, index=days)
    return days, schedule, close


def test_costs_charge_exactly_the_exposure_change_and_nothing_else():
    days, schedule, close = _flat()
    path = K.replay_path(close, schedule, [1.0, 0.4, 0.4, 0.4, 1.0, 1.0])
    sell = 0.6 / (1 - 0.4 * K.SELL_COST)
    e1 = schedule["executionDate"].iloc[1]
    assert path.loc[e1, "cost"] == pytest.approx(K.SELL_COST * sell, abs=1e-15)
    assert path.loc[e1, "weightEnd"] == pytest.approx(0.4, abs=1e-15) and path.loc[e1, "nav"] == pytest.approx(1 - K.SELL_COST * sell, abs=1e-15)
    nav_before = path.loc[e1, "nav"]
    buy = (1.0 * nav_before - 0.4 * nav_before) / (1 + K.BUY_COST)
    e4 = schedule["executionDate"].iloc[4]
    assert path.loc[e4, "cost"] * nav_before == pytest.approx(K.BUY_COST * buy, abs=1e-15) and path.loc[e4, "weightEnd"] == pytest.approx(1.0)
    assert (path["notional"] != 0).sum() == 2 and K.implementation_cost(path)["multiplierSwitches"] == 2
    gross = K.replay_path(close, schedule, [1.0, 0.4, 0.4, 0.4, 1.0, 1.0], stress=0.0)
    assert gross["cost"].sum() == 0 and gross["nav"].iloc[-1] == pytest.approx(1.0)
    double = K.replay_path(close, schedule, [1.0, 0.4, 0.4, 0.4, 1.0, 1.0], stress=2.0)
    assert double.loc[e1, "cost"] == pytest.approx(2 * K.SELL_COST * 0.6 / (1 - 0.4 * 2 * K.SELL_COST))
    still = K.replay_path(close, schedule, [0.7] * 6)
    assert still["cost"].sum() == 0 and (still["notional"] == 0).all()


def test_drift_is_not_traded_and_the_trade_happens_at_the_next_session_close():
    days, schedule, close = _flat()
    e1 = schedule["executionDate"].iloc[1]
    close.loc[e1:] = 110.0                                                        # the execution session itself jumps 10%
    path = K.replay_path(close, schedule, [1.0, 0.4, 0.4, 0.4, 0.4, 0.4], stress=0.0)
    assert path.loc[e1, "dailyReturn"] == pytest.approx(0.10)                     # the old weight earned the jump; the trade is at that close
    path2 = K.replay_path(close.where(close.index < schedule["executionDate"].iloc[2], 150.0), schedule, [0.7] * 6, stress=0.0)
    assert path2["weightEnd"].iloc[-1] > 0.7 and (path2["notional"] == 0).all()   # drifted, never retargeted while the target is unchanged
    with pytest.raises(ValueError, match="NO_LEVERAGE"):
        K.replay_path(close, schedule, [1.0, 1.2, 1.0, 1.0, 1.0, 1.0])
    gap = close.copy()
    gap.iloc[30] = np.nan
    with pytest.raises(ValueError, match="MISSING_OR_INVALID"):
        K.replay_path(gap, schedule, [1.0] * 6)


def test_metrics_on_a_hand_checked_path():
    days, schedule, close = _flat(n_weeks=10)
    close[:] = np.linspace(100, 80, len(close))
    close.iloc[-20:] = np.linspace(80, 100, 20)
    path = K.replay_path(close, schedule, [1.0] * 10, stress=0.0)
    mdd = K.max_drawdown(path["nav"])
    assert mdd["maxDrawdown"] == pytest.approx(close[path.index].min() / close[path.index].iloc[0] - 1)
    profile = K.false_alarm_profile(K.replay_path(close, schedule, [1.0, 0.7] + [1.0] * 8), M.forward_targets(close[path.index], 63)["forwardWorstLoss"])
    assert profile["activations"] == 1
    assert K.participation(path["dailyReturn"], path["dailyReturn"]) == {"upside": pytest.approx(1.0), "downside": pytest.approx(1.0)}


# ---------------------------------------------------------------------------------------------------------------------------------------
# The preregistered decision: Pareto, symmetric non-inferiority / meaningful-improvement bands, no forced winner
# ---------------------------------------------------------------------------------------------------------------------------------------
def _s(r, mdd, share):
    return {"netAnnualizedReturn": r, "maxDrawdown": mdd, "reducedSessionShare": share}


BASE = {K.PASSIVE: _s(0.060, -0.55, 0.0), "C0": _s(0.050, -0.40, 0.50)}


def _decide(**candidates):
    filler = {c: _s(0.0, -0.99, 0.99) for c in ("C1", "C2", "C3")}                  # a hopeless candidate: dominated, never survives
    return K.development_nomination({**BASE, **filler, **{k.upper(): v for k, v in candidates.items()}})


def test_the_bands_are_symmetric_round_preregistered_numbers_and_the_old_rule_is_gone():
    assert (K.RETURN_BAND, K.MEANINGFUL_DRAWDOWN_IMPROVEMENT, K.NON_INFERIORITY_DRAWDOWN_BAND) == (0.005, 0.10, 0.10)
    assert not hasattr(K, "SIMPLICITY_ORDER") and not hasattr(K, "RETURN_INDISTINGUISHABLE_PP")
    assert K.ROUTES == ("EFFICIENCY_ROUTE", "PROTECTION_ROUTE") and K.NOMINATION_TRADEOFF == "NO_UNAMBIGUOUS_NOMINATION_PARETO_TRADEOFF"


def test_c1_can_be_nominated_by_the_efficiency_route_without_any_drawdown_gain():
    """C1 is never more de-risked than C0, so it cannot be required to improve drawdown: more return, fewer costly false alarms, drawdown within +10%."""
    out = _decide(c1=_s(0.0555, -0.42, 0.25))
    assert out["developmentNomination"] == "C1" and out["steps"]["C1"]["routes"] == ["EFFICIENCY_ROUTE"]
    assert out["steps"]["C1"]["drawdownNonInferiorVersusControl"] and not out["steps"]["C1"]["meaningfulDrawdownImprovementVersusControl"]


def test_the_protection_route_nominates_a_candidate_with_meaningfully_shallower_drawdown_and_non_inferior_return():
    out = _decide(c2=_s(0.0460, -0.34, 0.45))
    assert out["developmentNomination"] == "C2" and out["steps"]["C2"]["routes"] == ["PROTECTION_ROUTE"]
    assert out["steps"]["C2"]["returnNonInferiorVersusControl"] and not out["steps"]["C2"]["meaningfulReturnImprovementVersusControl"]


def test_non_inferiority_is_required_on_both_axes_before_any_improvement_counts():
    assert _decide(c1=_s(0.0600, -0.45, 0.20))["developmentNomination"] == K.NOMINATION_NONE        # +1.0pp return, but drawdown 12.5% deeper
    assert _decide(c2=_s(0.0440, -0.20, 0.40))["developmentNomination"] == K.NOMINATION_NONE        # drawdown halved, but return 0.6pp below the margin
    both = _decide(c3=_s(0.0520, -0.39, 0.45))                                                      # inside both bands, improving neither route
    assert both["developmentNomination"] == K.NOMINATION_NONE and both["steps"]["C3"]["routes"] == [] and not both["steps"]["C3"]["survives"]


def test_a_value_exactly_on_a_band_edge_counts_as_inside_it_and_a_missing_value_never_passes():
    assert _decide(c1=_s(0.055, -0.44, 0.30))["steps"]["C1"]["survives"]                            # +0.50pp return and 110% drawdown, both exactly on the edge
    assert _decide(c2=_s(0.045, -0.36, 0.30))["steps"]["C2"]["survives"]                            # -0.50pp return and 90% drawdown, both exactly on the edge
    assert not _decide(c1=_s(0.0549, -0.40, 0.30))["steps"]["C1"]["meaningfulReturnImprovementVersusControl"]
    assert not _decide(c1=_s(0.055, -0.4401, 0.30))["steps"]["C1"]["survives"]
    for hole in (_s(None, -0.30, 0.2), _s(0.06, None, 0.2)):
        step = _decide(c1=hole)["steps"]["C1"]
        assert not step["survives"] and not step["returnNonInferiorVersusControl"] and step["routes"] == []


def test_pareto_elimination_comes_first_and_the_passive_path_can_eliminate_but_is_never_nominated():
    # inside both bands and on the efficiency route, yet the passive path is better on return AND drawdown at zero time de-risked.
    out = K.development_nomination({K.PASSIVE: _s(0.070, -0.30, 0.0), "C0": _s(0.050, -0.40, 0.50), "C1": _s(0.0556, -0.41, 0.30),
                                    "C2": _s(0.0, -0.99, 0.99), "C3": _s(0.0, -0.99, 0.99)})
    assert out["steps"]["C1"]["dominatedBy"] == [K.PASSIVE] and out["steps"]["C1"]["returnNonInferiorVersusControl"]
    assert not out["steps"]["C1"]["survives"] and out["developmentNomination"] == K.NOMINATION_NONE
    # a candidate dominated by ANOTHER CANDIDATE is eliminated even though it clears every band against C0
    out = _decide(c1=_s(0.0540, -0.41, 0.30), c3=_s(0.0556, -0.40, 0.20))
    assert out["steps"]["C1"]["dominatedBy"] == ["C3"] and out["steps"]["C1"]["returnNonInferiorVersusControl"] and not out["steps"]["C1"]["survives"]
    assert out["developmentNomination"] == "C3"
    assert out["controlDominatedBy"] == ["C3"]                                                   # better return, equal drawdown, less time de-risked


def test_several_mutually_non_dominated_survivors_are_a_reported_trade_off_and_nothing_is_forced():
    out = _decide(c1=_s(0.0560, -0.42, 0.25), c2=_s(0.0480, -0.34, 0.45))                       # C1 keeps return, C2 buys protection: a genuine trade-off
    assert out["survivors"] == ["C1", "C2"] and out["steps"]["C1"]["dominatedBy"] == [] and out["steps"]["C2"]["dominatedBy"] == []
    assert out["developmentNomination"] == K.NOMINATION_TRADEOFF and out["mutuallyNonDominatedSurvivors"] == ["C1", "C2"]
    three = _decide(c1=_s(0.0560, -0.42, 0.25), c2=_s(0.0480, -0.34, 0.45), c3=_s(0.0520, -0.35, 0.40))
    assert three["developmentNomination"] == K.NOMINATION_TRADEOFF
    # no tie-break: neither the simplest, nor the highest return, nor the shallowest drawdown is chosen
    assert all(three["developmentNomination"] != c for c in K.CANDIDATE_ORDER)


def test_identical_survivors_are_also_not_forced_and_no_survivor_keeps_the_control():
    same = _decide(c1=_s(0.0560, -0.42, 0.25), c2=_s(0.0560, -0.42, 0.25))
    assert same["survivors"] == ["C1", "C2"] and same["developmentNomination"] == K.NOMINATION_TRADEOFF
    assert _decide()["developmentNomination"] == K.NOMINATION_NONE and _decide()["survivors"] == []


def test_the_decision_output_carries_no_forbidden_semantics_and_no_utility_score():
    out = _decide(c1=_s(0.0560, -0.42, 0.25), c2=_s(0.0480, -0.34, 0.45))
    assert K.assert_no_forbidden_keys(out)
    assert not any("score" in key.lower() or "utility" in key.lower() for step in out["steps"].values() for key in step)
    with pytest.raises(ValueError, match="FORBIDDEN_OUTPUT_KEY"):
        K.assert_no_forbidden_keys({"bestCandidate": 1})


# ---------------------------------------------------------------------------------------------------------------------------------------
# Scope
# ---------------------------------------------------------------------------------------------------------------------------------------
def _imports(path):
    tree = ast.parse(Path(path).read_text())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names.update([node.module or ""] + [a.name for a in node.names])
        elif isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
    return names


def test_no_industry_or_stock_selection_enters_the_model():
    for module in ("kr_market_risk_model", "kr_market_risk_model_execution", "kr_market_risk_model_receipts"):
        names = _imports(ROOT / "pipeline" / (module + ".py"))
        assert not {n for n in names if any(x in n for x in ("industry", "concentrated", "overlay_portfolio", "value_quality", "alpha_opportunity_model",
                                                                "kelly", "stock", "longterm", "selection"))}, module
    for name, fn in inspect.getmembers(K, inspect.isfunction):
        assert not {p for p in inspect.signature(fn).parameters if any(x in p.lower() for x in ("ticker", "industry", "stock", "sector"))}, name
