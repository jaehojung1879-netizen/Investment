"""Invented prices/states only; no source, sealed return, one-shot runner or live writer."""
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from pipeline import market_research_c1c as C
from pipeline import kr_market_risk_anatomy as M
from pipeline import kr_market_risk_model as K
from pipeline import replay_calendar as RC
from pipeline import rp1_c1_us_exposure as U
from scripts import check_market_research as CLI

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("slow,transition,fast,breakout", itertools.product((0, 1), (0, 1), (0, 1, 2), (False, True)))
def test_factorial_moves_only_one_component_at_a_time(slow, transition, fast, breakout):
    base = K.rule("C1", slow, transition, fast)
    actual = {arm: C.target(arm, slow, transition, fast, breakout) for arm in C.ARMS}
    assert actual["S0"] == base
    assert actual["S1"] == (0 if fast == 2 else base)
    assert actual["S2"] == (1 if fast == 1 and breakout else base)
    assert actual["S3"] == (0 if fast == 2 else 1 if fast == 1 and breakout else base)


@pytest.mark.parametrize("arm", C.ARMS)
def test_missing_is_completed_not_a_benign_label(arm):
    assert C.target(arm, None, None, 0, None) == 1
    assert C.target(arm, None, None, None, None) is None
    assert C.target(arm, None, None, 2, None) == (0 if arm in ("S1", "S3") else 0.4)
    assert C.target(arm, 1, 0, 1, None) == (None if arm in ("S2", "S3") else 0.7)


@pytest.mark.parametrize("value", [0.5, -1, 3, "1"])
def test_invalid_severity_is_not_truncated_into_a_valid_state(value):
    with pytest.raises(ValueError, match="DOMAIN"):
        C.target("S0", 0, 0, value, False)


def closes(market="US", start="2019-01-02", end="2020-04-30"):
    days = RC.sessions(start, end, market)
    return pd.Series(np.linspace(100, 130, len(days)), index=days)


def states_for(plan, market="US", fast=1):
    out = pd.DataFrame({"slow": 1, "transition": 0, "fast": fast}, index=pd.DatetimeIndex(plan.decisionDate))
    for layer in ("slow", "transition", "fast"):
        out[layer + "KnownAt"] = [C.final_at(str(d.date()), market).isoformat() for d in out.index]
    return out


def test_breakout_excludes_signal_close_and_requires_all_exchange_sessions():
    close = closes()
    day = str(close.index[-1].date())
    assert C.prior_high_breakout(close, day, "US") is True
    equal = close.copy(); equal.iloc[-1] = equal.iloc[-2]
    assert C.prior_high_breakout(equal, day, "US") is False
    hole = close.drop(close.index[-10])
    assert len(hole) > 300 and C.prior_high_breakout(hole, day, "US") is None
    invalid = close.copy(); invalid.iloc[-10] = np.nan
    assert C.prior_high_breakout(invalid, day, "US") is None
    assert C.prior_high_breakout(close.iloc[-20:], day, "US") is None


def test_future_price_poison_does_not_change_previous_signal_or_decision_grid():
    close = closes()
    day = str(close.index[-40].date())
    before = C.prior_high_breakout(close, day, "US")
    changed = close.copy(); changed.loc[changed.index > day] *= 1000
    assert C.prior_high_breakout(changed, day, "US") == before
    full = C.schedule(close, "US", "2020-01-01", "2020-04-30")
    cut = C.schedule(close.loc[:"2020-02-12"], "US", "2020-01-01", "2020-02-12")
    pd.testing.assert_frame_equal(cut, full[full.executionDate <= "2020-02-12"].reset_index(drop=True))


@pytest.mark.parametrize("market,signal,execution", [("US", "2020-01-17", "2020-01-21"), ("KR", "2026-07-16", "2026-07-20")])
def test_holiday_week_ends_trade_next_real_session(market, signal, execution):
    close = closes(market, "2020-01-01" if market == "US" else "2026-06-01", "2020-02-01" if market == "US" else "2026-08-01")
    plan = C.schedule(close, market, signal, execution)
    assert str(plan.decisionDate.iloc[0].date()) == signal
    assert str(plan.executionDate.iloc[0].date()) == execution
    C.validate_plan(plan, market)


def test_known_at_after_finality_and_intraday_timestamp_refuse():
    close = closes(); plan = C.schedule(close, "US", "2020-01-01", "2020-04-30")
    states = states_for(plan)
    states.iloc[0, states.columns.get_loc("fastKnownAt")] = "2021-01-01T00:00:00Z"
    with pytest.raises(ValueError, match="NOT_KNOWN"):
        C.targets(close, states, plan, "US", "S3")
    assert C.final_at("2020-11-27", "US").isoformat() == "2020-11-27T19:00:00+00:00"
    assert C.final_at("2026-10-30", "KR") == pd.Timestamp("2026-10-30T18:00:00+09:00")
    states = states_for(plan)
    states.iloc[0, states.columns.get_loc("fastKnownAt")] = "2020-01-03T12:00:00"  # no timezone
    with pytest.raises(ValueError, match="WITHOUT_TIMEZONE"):
        C.targets(close, states, plan, "US", "S0")
    states = states_for(plan)
    states.iloc[0, states.columns.get_loc("fastKnownAt")] = (C.session_close(str(plan.decisionDate.iloc[0].date()), "US") - pd.Timedelta(minutes=1)).isoformat()
    with pytest.raises(ValueError, match="INTRADAY_FAST"):
        C.targets(close, states, plan, "US", "S0")


def test_missing_hold_and_first_undefined_refusal_are_per_arm():
    close = closes(); plan = C.schedule(close, "US", "2020-01-01", "2020-04-30")
    states = states_for(plan)
    states.iloc[1, states.columns.get_loc("fast")] = np.nan
    result = C.targets(close, states, plan, "US", "S1")
    assert result.heldForMissing.iloc[1] and result.target.iloc[1] == result.target.iloc[0]
    states.iloc[0, states.columns.get_loc("fast")] = np.nan
    with pytest.raises(ValueError, match="FIRST_TARGET_UNDETERMINED"):
        C.targets(close, states, plan, "US", "S1")


def test_reentry_is_not_latched_and_fast2_always_vetoes():
    assert C.target("S3", 1, 0, 1, True) == 1
    assert C.target("S3", 1, 0, 1, False) == 0.7
    assert C.target("S3", 1, 1, 2, True) == 0


def replay_fixture():
    close = closes(end="2019-03-29")
    plan = C.schedule(close, "US", "2019-02-01", "2019-03-29")
    return close.loc[plan.executionDate.iloc[0]:], plan


def test_gap_until_next_close_is_borne_by_old_holdings():
    close, plan = replay_fixture()
    close[:] = 100
    second = plan.executionDate.iloc[1]
    close.loc[second:] = 70  # a gap at the sell execution is not avoided
    cash = pd.Series(0., index=close.index)
    selected = [1., 0.] + [0.] * (len(plan) - 2)
    path = C.replay(close, plan, selected, cash, "US", "C1_PRIMARY_REPLICA", 0, evidence_class=C.SYNTHETIC)
    assert path.nav.loc[second] == pytest.approx(0.7)
    assert path.target.loc[second] == 0
    # A rise through the buy close is missed by the old zero position.
    close.loc[second:] = 130
    path = C.replay(close, plan, [0., 1.] + [1.] * (len(plan) - 2), cash, "US", "C1_PRIMARY_REPLICA", 0, evidence_class=C.SYNTHETIC)
    assert path.nav.loc[second] == 1


@pytest.mark.parametrize("basis", ["C1_PRIMARY_REPLICA", "ETF_CASH_ECONOMIC"])
def test_self_financing_cost_stress_cannot_create_profit_on_flat_prices(basis):
    close, plan = replay_fixture(); close[:] = 100
    cash = pd.Series(0., index=close.index)
    selected = [float(i % 2) for i in range(len(plan))]
    values = [C.replay(close, plan, selected, cash, "US", basis, x, evidence_class=C.SYNTHETIC).nav.iloc[-1] for x in (0, 1, 2, 3)]
    assert values[0] == 1 and all(a > b for a, b in zip(values[:-1], values[1:]))


def test_funded_entry_and_liquidation_are_counted_in_full_return_mdd_and_month_tail():
    close, plan = replay_fixture(); close[:] = 100
    cash = pd.Series(0., index=close.index)
    path = C.replay(close, plan, [1.] * len(plan), cash, "US", "ETF_CASH_ECONOMIC", 1, evidence_class=C.SYNTHETIC)
    expected = (1 - U.US_SELL_COST) / (1 + U.US_BUY_COST)
    assert path.nav.iloc[-1] == pytest.approx(expected)
    report = C.diagnostics(path, path, close, cash)
    assert report["summary"]["fundedCumulativeReturn"] == pytest.approx(expected - 1)
    assert report["summary"]["fundedMdd"] == pytest.approx(expected - 1)
    assert report["summary"]["drawdownPeakIsInitialCapital"] is True
    assert report["monthlyCvar"]["cvar"] < 0
    assert report["entryFee"] > 0 and report["liquidationFee"] > 0
    periods = C.lifecycle_periods(path, path)
    assert np.prod([1 + r for r in periods["calendarYears"].values()]) == pytest.approx(path.nav.iloc[-1])


def test_zero_cost_control_path_equals_unchanged_sealed_cash_replay():
    close, plan = replay_fixture(); cash = pd.Series(0., index=close.index)
    targets = [0.7] * len(plan)
    actual = C.replay(close, plan, targets, cash, "US", "C1_PRIMARY_REPLICA", 0, evidence_class=C.SYNTHETIC)
    expected = U.replay_path_with_cash(close, plan, targets, cash, 0, U.US_BUY_COST, U.US_SELL_COST)
    pd.testing.assert_frame_equal(actual[expected.columns], expected)


def test_final_close_does_not_buy_a_new_position_only_to_liquidate_it():
    close, plan = replay_fixture()
    plan = plan.iloc[:2].copy()
    close = close.loc[:plan.executionDate.iloc[-1]].copy(); close[:] = 100
    cash = pd.Series(0., index=close.index)
    path = C.replay(close, plan, [0., 1.], cash, "US", "ETF_CASH_ECONOMIC", 1, evidence_class=C.SYNTHETIC)
    assert path.nav.iloc[-1] == 1 and path.attrs["terminalTargetOmitted"] == 1
    assert path.notional.abs().sum() == 0


def test_cash_accrual_uses_previous_known_rate_and_real_weekend_days():
    days = RC.sessions("2020-01-02", "2020-01-13", "US")
    rates = pd.Series([3., 30.], index=pd.to_datetime(["2019-12-27", "2020-01-09"]))
    result = U.cash_interval_returns(rates, days)
    assert result.loc["2020-01-06"] == pytest.approx(.03 * 3 / 360)
    assert result.loc["2020-01-13"] == pytest.approx(.03 * 3 / 360)  # Jan 9 observation not known at Friday's close
    old = M.known_on_sessions(pd.Series([1.], index=pd.to_datetime(["2020-01-01"])), days, 4, 14)[0]
    assert np.isnan(old.iloc[0]) and np.isfinite(old.iloc[-1])


@pytest.mark.parametrize("fault", ["gap", "nan", "zero", "duplicate", "late_execution", "missing_cash"])
def test_invalid_path_is_blocked_for_all_arms(fault):
    close, plan = replay_fixture(); cash = pd.Series(0., index=close.index)
    if fault == "gap": close = close.drop(close.index[3])
    if fault == "nan": close.iloc[3] = np.nan
    if fault == "zero": close.iloc[3] = 0
    if fault == "duplicate": close = pd.concat([close.iloc[:1], close])
    if fault == "late_execution": plan.loc[1, "executionDate"] = plan.executionDate.iloc[1] + pd.Timedelta(days=1)
    if fault == "missing_cash": cash.iloc[3] = np.nan
    with pytest.raises(ValueError):
        C.replay(close, plan, [0.7] * len(plan), cash, "US", "C1_PRIMARY_REPLICA", 1, evidence_class=C.SYNTHETIC)


def test_arithmetic_identity_distinguishes_exposure_covariance_and_cost():
    close, plan = replay_fixture(); cash = pd.Series(0., index=close.index)
    path = C.replay(close, plan, [0.7] * len(plan), cash, "US", "ETF_CASH_ECONOMIC", 1, evidence_class=C.SYNTHETIC)
    result = C.arithmetic_decomposition(path, close, cash)
    assert abs(result["identityResidual"]) < 1e-12
    assert result["interpretation"] == "EX_POST_IDENTITY_NOT_TRADABLE_NOT_TIMING_SKILL"


def test_factorial_rejects_missing_cell_and_does_not_turn_it_into_zero():
    assert C.factorial({"S0": 0., "S1": .01, "S2": .02, "S3": .05})["interaction"] == pytest.approx(.02)
    assert C.factorial({"S0": 0., "S1": None, "S2": .02, "S3": .05})["status"] == "INCOMPLETE_CELL"


def test_false_alarm_and_whipsaw_endpoints_are_pending_not_silent_zero():
    close, plan = replay_fixture(); cash = pd.Series(0., index=close.index)
    path = C.replay(close, plan, [0., 1.] + [0.7] * (len(plan) - 2), cash, "US", "C1_PRIMARY_REPLICA", 1, evidence_class=C.SYNTHETIC)
    path.loc[path.index[-2]:, "target"] = 1
    result = C.transition_diagnostics(path, path)
    assert result["fullReentries"][-1]["pending"] and result["fullReentries"][-1]["reversedWithin20"] is None
    assert C.diagnostics(path, path, close, cash)["falseAlarm"]["pendingActivations"] > 0


def test_interface_applies_market_risk_once_and_never_blocks_selection_research():
    evidence = {"known_at": C.final_at("2020-01-17", "US").isoformat(), "source_sha256": "1" * 64,
                "code_sha256": "2" * 64}
    msg = C.market_interface("US", "2020-01-17", "2020-01-21", .7, applied_scopes=("INDUSTRY_SELECTION",), **evidence)
    assert not msg["productionAllowed"] and not msg["BConditionalSignalAppliedAsRiskMultiplier"]
    with pytest.raises(ValueError, match="ALREADY_APPLIED"):
        C.market_interface("US", "2020-01-17", "2020-01-21", .7, applied_scopes=("MARKET_RISK_ONCE",), **evidence)
    assert C.program_readiness()["members"]["B-H2"].startswith("BLOCKED")
    assert not C.program_readiness()["industryAndStockResearchDependsOnMarketAlpha"]
    with pytest.raises(ValueError, match="INTERFACE_EXECUTION_BOUNDARY"):
        C.market_interface("US", "2020-01-15", "2020-01-16", .7,
            known_at=C.final_at("2020-01-15", "US").isoformat(), source_sha256="1" * 64, code_sha256="2" * 64)


def test_real_execution_is_not_available_even_with_existing_approval_text(capsys):
    close, plan = replay_fixture()
    with pytest.raises(ValueError, match="NOT_IMPLEMENTED_OR_AUTHORIZED"):
        C.replay(close, plan, [1.] * len(plan), pd.Series(0., index=close.index), "US", "C1_PRIMARY_REPLICA", 1,
                 evidence_class="OWNER_APPROVED_HISTORICAL")
    with pytest.raises(SystemExit):
        CLI.main(["execute"])


def test_unchanged_seals_and_deterministic_manifest_and_no_authorization():
    one, two = C.verify_design(), C.verify_design()
    assert one == two and one["preservedFiles"] >= 94
    assert one["historicalOutcomeExecutions"] == one["realNumericValueReads"] == 0
    assert not one["ownerAuthorization"] and not one["historicalExecutionEnabled"]


def test_inherited_four_day_lag_and_fourteen_day_staleness_do_not_read_future():
    days = RC.sessions("2020-01-02", "2020-02-10", "US")
    records = pd.Series([2., 999.], index=pd.to_datetime(["2020-01-01", "2020-02-06"]))
    values, _ = M.known_on_sessions(records, days, K.FRED_LAG_DAYS, K.FRED_STALE_DAYS)
    assert np.isnan(values.loc["2020-01-03"]) and values.loc["2020-01-06"] == 2
    assert np.isnan(values.loc["2020-01-16"]) and values.loc["2020-02-10"] == 999
    changed = records.copy(); changed.iloc[-1] = -999
    earlier, _ = M.known_on_sessions(changed, days, K.FRED_LAG_DAYS, K.FRED_STALE_DAYS)
    pd.testing.assert_series_equal(values.loc[:"2020-02-07"], earlier.loc[:"2020-02-07"])


def test_full_three_layer_adapter_keeps_earlier_state_prefix_under_future_poison():
    close = closes(start="2010-01-04", end="2017-12-29")
    dates = pd.date_range("2009-12-01", "2017-12-29", freq="D")
    spread = pd.Series(np.sin(np.arange(len(dates)) / 180), index=dates)
    vix = pd.Series(20 + 5 * np.sin(np.arange(len(dates)) / 30), index=dates)
    cutoff = "2016-02-12"
    before = C.sealed_states(close, spread, vix, "US")
    changed, s2, v2 = close.copy(), spread.copy(), vix.copy()
    changed.loc[changed.index > cutoff] *= 1000
    s2.loc[s2.index > cutoff] = 1000
    v2.loc[v2.index > cutoff] = 1000
    after = C.sealed_states(changed, s2, v2, "US")
    pd.testing.assert_frame_equal(before.loc[:cutoff], after.loc[:cutoff])


def test_impossible_cash_interval_cannot_generate_borrowing_or_negative_wealth():
    close, plan = replay_fixture(); cash = pd.Series(0., index=close.index)
    cash.iloc[3] = -1
    with pytest.raises(ValueError, match="CASH_INTERVAL_MISSING_OR_IMPOSSIBLE"):
        C.replay(close, plan, [0.4] * len(plan), cash, "US", "ETF_CASH_ECONOMIC", 1, evidence_class=C.SYNTHETIC)


def test_modified_numeric_protocol_cannot_pass_as_same_design(tmp_path):
    value = json.loads((ROOT / C.PROTOCOL).read_bytes())
    value["breakoutWindow"] = 19
    path = tmp_path / C.PROTOCOL; path.parent.mkdir(parents=True); path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="PROTOCOL_IMPLEMENTATION_MISMATCH"):
        C.verify_design(tmp_path)


def test_protected_file_modification_is_refused(tmp_path):
    protocol = tmp_path / C.PROTOCOL; protocol.parent.mkdir(parents=True)
    protocol.write_bytes((ROOT / C.PROTOCOL).read_bytes())
    name = "pipeline/sealed_synthetic.py"; file = tmp_path / name; file.parent.mkdir(); file.write_text("TAMPER")
    pin = {"files": {name: "0" * 64}}
    (protocol.parent / "market-research-preserved-sha256.json").write_text(json.dumps(pin))
    with pytest.raises(ValueError, match="EXISTING_STUDY_CHANGED"):
        C.verify_design(tmp_path)
