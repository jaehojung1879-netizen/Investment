"""Invented paths only: no data files, vendor calls, historical labels or writer."""
import copy

import numpy as np
import pandas as pd
import pytest

from pipeline import market_research_c1c as C
from pipeline import market_research_c1c_diagnostics as D
from pipeline import replay_calendar as RC


def fixture(market="US", end="2020-05-29"):
    days = RC.sessions("2020-01-02", end, market)
    close = pd.Series(100 * np.exp(np.arange(len(days)) * 0.002 + 0.04 * np.sin(np.arange(len(days)) / 5)), index=days)
    plan = C.schedule(close, market, "2020-01-02", end)
    close = close.loc[plan.executionDate.iloc[0]:]
    cash = pd.Series(0.0, index=close.index)
    return close, plan, cash


def report(close, plan, cash, targets, **kw):
    return D.synthetic_diagnostics(close, plan, targets, cash, kw.pop("market", "US"),
                                   kw.pop("basis", "ETF_CASH_ECONOMIC"), kw.pop("stress", 1),
                                   evidence_class=kw.pop("evidence_class", C.SYNTHETIC), **kw)


@pytest.mark.parametrize("market", ["KR", "US"])
@pytest.mark.parametrize("level", [0.0, 0.4, 0.7, 1.0])
def test_constant_policy_equals_its_mean_exposure_matched_comparator(market, level):
    close, plan, cash = fixture(market)
    if market == "US":
        cash[:] = .0001
    r = report(close, plan, cash, [level] * len(plan), market=market)
    assert r["exposureMatch"]["matched"]
    assert abs(r["exposureMatch"]["residual"]) <= D.MATCH_TOLERANCE
    assert r["exposureMatch"]["staticInitialTarget"] == pytest.approx(level, abs=1e-11)
    assert r["candidateMinusMatchedStaticNetAnnualLogGrowth"] == pytest.approx(0, abs=1e-11)
    assert not r["timingAlphaEstablished"] and not r["productionAllowed"]


def test_matches_realised_interval_exposure_not_average_requested_targets():
    close, plan, cash = fixture()
    close[:] = 100 * np.exp(np.arange(len(close)) * .015)
    targets = [0.0 if i < len(plan) // 2 else 1.0 for i in range(len(plan))]
    r = report(close, plan, cash, targets)
    m = r["exposureMatch"]
    assert m["candidateMeanIntervalExposure"] == pytest.approx(m["staticMeanIntervalExposure"], abs=1e-12)
    assert abs(m["staticInitialTarget"] - np.mean(targets)) > .01
    assert m["interpretation"].startswith("EX_POST")


def test_future_price_poison_cannot_change_candidate_past_but_static_is_explicitly_ex_post():
    close, plan, cash = fixture()
    targets = [0.4 if i % 2 else 1.0 for i in range(len(plan))]
    poisoned = close.copy(); cut = close.index[len(close) // 2]
    poisoned.loc[poisoned.index > cut] *= np.linspace(1, 2, (poisoned.index > cut).sum())
    a = C.replay(close, plan, targets, cash, "US", "ETF_CASH_ECONOMIC", 1, evidence_class=C.SYNTHETIC)
    b = C.replay(poisoned, plan, targets, cash, "US", "ETF_CASH_ECONOMIC", 1, evidence_class=C.SYNTHETIC)
    pd.testing.assert_frame_equal(a.loc[:cut], b.loc[:cut])
    x, y = report(close, plan, cash, targets), report(poisoned, plan, cash, targets)
    assert x["exposureMatch"]["staticInitialTarget"] != pytest.approx(y["exposureMatch"]["staticInitialTarget"])
    assert not x["timingAlphaEstablished"] and not y["timingAlphaEstablished"]


def test_zero_exposure_earns_only_declared_cash_and_pays_no_equity_lifecycle_cost():
    close, plan, cash = fixture(); cash[:] = .0002
    r = report(close, plan, cash, [0.0] * len(plan))
    s = r["summaries"]["candidate"]
    assert s["netCumulativeReturn"] == pytest.approx((1.0002 ** (len(close) - 1)) - 1)
    assert s["lifecycleOneWayTurnover"] == s["entryFeeInitialCapitalFraction"] == s["exitFeePreLiquidationNavFraction"] == 0
    with pytest.raises(ValueError, match="ZERO_CASH"):
        report(close, plan, cash, [0.0] * len(plan), basis="C1_PRIMARY_REPLICA")


def test_flat_price_switching_costs_and_lifecycle_turnover_are_visible():
    close, plan, cash = fixture(); close[:] = 100
    targets = [float(i % 2) for i in range(len(plan))]
    one = report(close, plan, cash, targets, stress=1)
    three = report(close, plan, cash, targets, stress=3)
    assert three["summaries"]["candidate"]["netCumulativeReturn"] < one["summaries"]["candidate"]["netCumulativeReturn"] < 0
    assert one["summaries"]["candidate"]["lifecycleOneWayTurnover"] > one["summaries"]["matchedStatic"]["lifecycleOneWayTurnover"]
    assert one["summaries"]["candidate"]["switches"] > 0


def test_fixed_episode_captures_execution_close_gap_and_rebound_delay():
    close, plan, cash = fixture(); close[:] = 100
    sell, buy = plan.executionDate.iloc[2], plan.executionDate.iloc[4]
    trough, end = close.index[close.index.get_loc(sell) + 1], plan.executionDate.iloc[7]
    close.loc[sell:] = 70; close.loc[trough:] = 60; close.loc[buy:] = 90; close.loc[end:] = 100
    targets = [1.0] * 2 + [0.0] * 2 + [1.0] * (len(plan) - 4)
    e = {"episodeId": "fixed-drop-rebound", "startDate": str(close.index[0].date()),
         "troughDate": str(trough.date()), "endDate": str(end.date())}
    r = report(close, plan, cash, targets, episodes=[e], stress=0)
    row = r["episodes"]["windows"][0]
    # The 30% fall through the sell close is still borne. Only the later fall is avoided.
    assert row["lossAvoidedNet"] == pytest.approx(.1)
    assert row["firstFullReentryExecutionDate"] == str(buy.date())
    assert row["firstFullReentryDelaySessions"] == close.index.get_loc(buy) - close.index.get_loc(trough)
    assert row["reboundOpportunityCostNet"] > 0


def test_pending_episode_and_whipsaw_never_become_successful_zero_or_dropped_rows():
    close, plan, cash = fixture()
    future = RC.sessions(str(close.index[-1].date()), "2020-07-31", "US")[-1]
    e = {"episodeId": "pending", "startDate": str(close.index[0].date()),
         "troughDate": str(close.index[-3].date()), "endDate": str(future.date())}
    targets = [0.0] * (len(plan) - 2) + [1.0, 0.0]
    r = report(close, plan, cash, targets, episodes=[e])
    assert r["episodes"]["intendedWindows"] == r["episodes"]["pendingWindows"] == 1
    assert r["episodes"]["completeCohortAggregate"] is None
    assert r["episodes"]["windows"][0]["lossAvoidedNet"] is None
    assert r["transitions"]["pendingReentries"] == 1
    event = r["transitions"]["reentries"][0]
    assert event["observedReversalSoFar"] is True and event["reversedWithin20Sessions"] is None
    assert r["transitions"]["wholeCohortWhipsawShare"] is None


def test_already_full_at_trough_is_not_fabricated_as_a_new_reentry_execution():
    close, plan, cash = fixture()
    episode = {"episodeId": "held-through", "startDate": str(close.index[0].date()),
               "troughDate": str(close.index[5].date()), "endDate": str(close.index[10].date())}
    row = report(close, plan, cash, [1.] * len(plan), episodes=[episode])["episodes"]["windows"][0]
    assert row["fullReentryStatus"] == "ALREADY_FULL_AT_TROUGH"
    assert row["firstFullReentryExecutionDate"] is None and row["firstFullReentryDelaySessions"] == 0


@pytest.mark.parametrize("fault", ["nan", "infinity", "negative", "bool", "string", "short", "missing_bar", "cash_gap", "cash_minus_one", "bool_stress", "basis", "real"])
def test_invalid_inputs_fail_closed_for_whole_comparison(fault):
    close, plan, cash = fixture(); targets = [.7] * len(plan); kw = {}
    if fault == "nan": targets[0] = np.nan
    if fault == "infinity": targets[0] = np.inf
    if fault == "negative": targets[0] = -.1
    if fault == "bool": targets[0] = True
    if fault == "string": targets[0] = "0.7"
    if fault == "short": targets[0] = 1.1
    if fault == "missing_bar": close = close.drop(close.index[3])
    if fault == "cash_gap": cash = cash.drop(cash.index[3])
    if fault == "cash_minus_one": cash.iloc[3] = -1
    if fault == "bool_stress": kw["stress"] = True
    if fault == "basis": kw["basis"] = "MIXED_SPY_PRICE_INDEX"
    if fault == "real": kw["evidence_class"] = "OWNER_APPROVED_HISTORICAL"
    with pytest.raises(ValueError): report(close, plan, cash, targets, **kw)


def test_episode_contract_rejects_duplicates_or_off_calendar_without_changing_inputs():
    close, plan, cash = fixture(); targets = [.7] * len(plan)
    episode = {"episodeId": "one", "startDate": str(close.index[0].date()),
               "troughDate": str(close.index[5].date()), "endDate": str(close.index[10].date())}
    original = copy.deepcopy(episode)
    with pytest.raises(ValueError, match="UNIQUE_EPISODE"):
        report(close, plan, cash, targets, episodes=[episode, episode])
    assert episode == original
    episode["troughDate"] = "2020-01-11"
    with pytest.raises(ValueError, match="OFF_EXCHANGE"):
        report(close, plan, cash, targets, episodes=[episode])


def test_finite_input_levels_cannot_publish_nonfinite_path_after_arithmetic_overflow():
    close, plan, cash = fixture()
    close.iloc[0], close.iloc[1] = 1e-300, 1e300
    with pytest.raises(ValueError, match="NONFINITE_OR_IMPOSSIBLE"):
        report(close, plan, cash, [1.0] * len(plan))


@pytest.mark.parametrize("fault", ["scalar_targets", "missing_plan", "none_episodes"])
def test_malformed_contract_types_raise_explicit_input_errors(fault):
    close, plan, cash = fixture(); targets = [.7] * len(plan); kw = {}
    if fault == "scalar_targets": targets = None
    if fault == "missing_plan": plan = None
    if fault == "none_episodes": kw["episodes"] = None
    with pytest.raises(ValueError): report(close, plan, cash, targets, **kw)
