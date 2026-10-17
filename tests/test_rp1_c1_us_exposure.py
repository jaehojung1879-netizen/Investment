"""rp1-c1-us-exposure-ladder-replication-v1: wrapper equivalence, economic reading, gates, frozen spec, outcome-free modes.

Synthetic data only, except the equivalence test, which reads the sealed KR study's own retained bytes and compares with its sealed result."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from pipeline import kr_market_risk_anatomy as M
from pipeline import kr_market_risk_model as K
from pipeline import kr_market_risk_model_execution as E
from pipeline import rp1_c1_us_exposure as U
from pipeline import rp1_c1_us_exposure_spec as SP
from pipeline import rp1_c1_us_sources as SRC

ROOT = Path(__file__).resolve().parents[1]


def walk(sessions, seed=0, drift=0.0003, vol=0.012):
    rng = np.random.default_rng(seed)
    return pd.Series(100.0 * np.exp(np.cumsum(drift + vol * rng.standard_normal(len(sessions)))), index=sessions)


def synthetic_world(market="US", start="1990-01-02", end="1999-12-31", seed=1):
    sessions = U.market_sessions(market, start, end)
    rng = np.random.default_rng(seed)
    close = walk(sessions, seed)
    days = pd.date_range(start, end, freq="B")
    spread = pd.Series(np.sin(np.arange(len(days)) / 180.0) * 1.5 + 0.2 * rng.standard_normal(len(days)), index=days)
    vix = pd.Series(np.abs(18 + 6 * np.sin(np.arange(len(days)) / 90.0) + 2 * rng.standard_normal(len(days))), index=days)
    cash = pd.Series(4.0 + 0.5 * np.sin(np.arange(len(days)) / 300.0), index=days)
    return sessions, {"reference": close, "spread": spread, "vix": vix, "asset": close * 1.0001, "cash": cash}


# ---- the wrapper changes only the calendar --------------------------------------------------------------------------------------------------
def test_calendar_functions_equal_the_sealed_kr_functions_on_the_kr_calendar():
    sessions = U.market_sessions("KR", "2001-01-02", "2012-12-28")
    for frequency in ("W", "M"):
        assert U.period_end_sessions(sessions, frequency, "KR").equals(K.period_end_sessions(sessions, frequency))
    assert U.decision_schedule(sessions, "2005-01-01", "2012-12-28", "KR").equals(K.decision_schedule(sessions, "2005-01-01", "2012-12-28"))


def test_layer_states_equal_the_sealed_states_on_the_kr_calendar():
    sessions, values = synthetic_world("KR", "1995-01-03", "2001-12-28")
    a = U.layer_states(values["reference"], values["spread"], values["vix"], sessions, "KR")
    b = K.layer_states(values["reference"], values["spread"], values["vix"], sessions)
    pd.testing.assert_frame_equal(a, b)


def test_us_calendar_samples_xnys_week_ends_and_trades_the_next_xnys_session():
    sessions = U.market_sessions("US", "2020-11-02", "2020-12-31")
    schedule = U.decision_schedule(sessions, "2020-11-01", "2020-12-31", "US")
    for d, x in zip(schedule["decisionDate"], schedule["executionDate"]):
        assert x == sessions[sessions.get_loc(d) + 1]
    assert pd.Timestamp("2020-11-27") in set(schedule["decisionDate"])        # Black Friday: the week-end session before Thanksgiving week ends
    assert pd.Timestamp("2020-11-26") not in set(sessions)                    # Thanksgiving is not an XNYS session


def test_states_are_end_date_invariant_on_the_us_calendar():
    sessions, values = synthetic_world("US", "1990-01-02", "1996-06-28")
    full = U.layer_states(values["reference"], values["spread"], values["vix"], sessions, "US")
    cut = sessions[sessions <= pd.Timestamp("1995-03-15")]                   # mid-week, mid-month
    part = U.layer_states(values["reference"].reindex(cut), values["spread"][:"1995-03-15"], values["vix"][:"1995-03-15"], cut, "US")
    pd.testing.assert_frame_equal(full.loc[cut], part)


# ---- the economic reading ----------------------------------------------------------------------------------------------------------------
def test_zero_cash_replay_is_the_sealed_replay():
    sessions, values = synthetic_world()
    states = U.layer_states(values["reference"], values["spread"], values["vix"], sessions, "US")
    schedule = U.decision_schedule(sessions, "1993-02-01", "1999-12-31", "US")
    window = sessions[sessions >= schedule["executionDate"].iloc[0]]
    bench = values["reference"].reindex(window)
    for cid in K.CANDIDATE_ORDER:
        t = K.candidate_targets(states, schedule, cid)["target"].tolist()
        for stress in (0.0, 1.0, 3.0):
            ours = U.replay_path_with_cash(bench, schedule, t, pd.Series(0.0, index=window), stress, U.US_BUY_COST, U.US_SELL_COST)
            pd.testing.assert_frame_equal(ours, K.replay_path(bench, schedule, t, stress, U.US_BUY_COST, U.US_SELL_COST))


def test_cash_accrues_the_previous_known_rate_over_calendar_days():
    sessions = U.market_sessions("US", "2021-01-04", "2021-01-15")
    rate = pd.Series(3.6, index=pd.date_range("2020-12-01", "2021-01-15"))
    r = U.cash_interval_returns(rate, sessions, lag_days=0)
    assert np.isnan(r.iloc[0])
    gap = (sessions[1:] - sessions[:-1]).days
    np.testing.assert_allclose(r.iloc[1:].to_numpy(), 0.036 * gap / 360.0)


def test_a_missing_cash_rate_refuses_rather_than_reading_as_zero():
    sessions, values = synthetic_world()
    schedule = U.decision_schedule(sessions, "1993-02-01", "1999-12-31", "US")
    window = sessions[sessions >= schedule["executionDate"].iloc[0]]
    cash = pd.Series(0.0001, index=window)
    cash.iloc[10] = np.nan
    with pytest.raises(ValueError, match="CASH_RATE_MISSING"):
        U.replay_path_with_cash(values["asset"].reindex(window), schedule, [1.0] * len(schedule), cash)


def test_all_cash_path_compounds_the_cash_rate_and_full_exposure_ignores_it():
    sessions, values = synthetic_world()
    schedule = U.decision_schedule(sessions, "1993-02-01", "1999-12-31", "US")
    window = sessions[sessions >= schedule["executionDate"].iloc[0]]
    cash = pd.Series(0.0001, index=window)
    all_cash = U.replay_path_with_cash(values["asset"].reindex(window), schedule, [0.0] * len(schedule), cash, stress=0.0)
    assert all_cash["nav"].iloc[-1] == pytest.approx(1.0001 ** (len(window) - 1))
    full = U.replay_path_with_cash(values["asset"].reindex(window), schedule, [1.0] * len(schedule), cash, stress=0.0)
    asset = values["asset"].reindex(window)
    assert full["nav"].iloc[-1] == pytest.approx(asset.iloc[-1] / asset.iloc[0])


# ---- diagnostics ------------------------------------------------------------------------------------------------------------------------
def test_false_alarm_list_agrees_with_the_sealed_profile():
    sessions, values = synthetic_world(seed=7)
    states = U.layer_states(values["reference"], values["spread"], values["vix"], sessions, "US")
    schedule = U.decision_schedule(sessions, "1993-02-01", "1999-12-31", "US")
    window = sessions[sessions >= schedule["executionDate"].iloc[0]]
    bench = values["reference"].reindex(window)
    forward = M.forward_targets(bench, K.FALSE_ALARM_HORIZON)["forwardWorstLoss"]
    for cid in K.CANDIDATE_ORDER:
        path = K.replay_path(bench, schedule, K.candidate_targets(states, schedule, cid)["target"].tolist())
        rows, profile = U.false_alarm_list(path, forward), K.false_alarm_profile(path, forward)
        assert len(rows) == profile["activations"]
        assert sum(r["status"] == "FALSE_ALARM" for r in rows) == profile["falseAlarms"]
        assert sum(r["status"] == "PENDING" for r in rows) == profile["pendingActivations"]


def test_up_down_gap_is_the_arithmetic_split_of_the_daily_gap():
    idx = pd.date_range("2020-01-01", periods=5)
    passive = pd.DataFrame({"dailyReturn": [np.nan, 0.02, -0.01, 0.03, -0.04]}, index=idx)
    path = pd.DataFrame({"dailyReturn": [np.nan, 0.01, -0.005, 0.03, -0.02], "target": 1.0}, index=idx)
    gap = U.up_down_market_gap(path, passive)
    years = 4 / K.ANNUALISATION
    assert gap["upMarketCostPerYear"] == pytest.approx(0.01 / years)
    assert gap["downMarketSavingPerYear"] == pytest.approx(0.025 / years)


def test_monthly_cvar_is_the_mean_of_the_worst_tail_months():
    idx = pd.bdate_range("2020-01-01", "2021-12-31")
    path = pd.DataFrame({"nav": np.linspace(1.0, 2.0, len(idx))}, index=idx)
    path.iloc[300:, 0] *= 0.8
    out = U.monthly_cvar(path)
    months = U.monthly_returns(path).sort_values().to_numpy()
    assert out["tailMonths"] == 2 and out["cvar"] == pytest.approx(months[:2].mean()) and out["worstMonth"] == pytest.approx(months[0])


def test_evaluate_on_a_synthetic_us_world_keeps_the_frozen_vocabulary():
    sessions, values = synthetic_world(end="2000-12-29")
    cfg = {**U.us_config(), "analysisEnd": "2000-12-29"}
    result = U.evaluate(values, cfg)
    assert set(result["candidates"]) == set(K.CANDIDATE_ORDER)
    assert result["decision"]["developmentNomination"] in (K.NOMINATION_NONE, K.NOMINATION_TRADEOFF, *K.CANDIDATE_ORDER[1:])
    assert set(result["economic"]["candidates"]) == set(K.CANDIDATE_ORDER)
    for cid in K.CANDIDATE_ORDER:
        assert set(result["candidates"][cid]["diagnostics"]) == {"monthlyCvar", "upDownMarketGap", "protectionByEpisode", "falseAlarmList", "subperiods"}
    K.assert_no_forbidden_keys(E.json_safe(result))


def test_us_costs_are_the_repository_us_cost_table():
    from pipeline.benchmark_alpha import REALISTIC_COSTS
    us = REALISTIC_COSTS["US"]
    assert U.US_BUY_COST == pytest.approx((us["commissionBps"] + us["spreadBps"] / 2) / 1e4)
    assert U.US_SELL_COST == pytest.approx((us["commissionBps"] + us["spreadBps"] / 2 + us["sellTaxBps"]) / 1e4)


# ---- sources and gates ----------------------------------------------------------------------------------------------------------------
def chart(stamps, closes, adj, dividends=None):
    return json.dumps({"chart": {"result": [{"meta": {"symbol": "SPY", "currency": "USD", "exchangeTimezoneName": "America/New_York", "gmtoffset": -14400},
                                             "timestamp": stamps, "events": {"dividends": dividends or {}},
                                             "indicators": {"quote": [{"close": closes}], "adjclose": [{"adjclose": adj}]}}]}}).encode()


def test_adjclose_parser_drops_and_counts_invalid_rows_and_reads_exchange_local_dates():
    stamps = [1609770600, 1609857000, 1609943400]                            # 2021-01-04..06 14:30 UTC (09:30 New York)
    rows, dropped = SRC.parse_yahoo_adjclose(chart(stamps, [1, 2, 3], [10.0, None, -1.0]))
    assert rows == [("2021-01-04", 10.0)] and dropped == 2
    divs = {"1": {"date": 1609857000, "amount": 1.5}}
    assert SRC.yahoo_dividend_dates(chart(stamps, [1, 2, 3], [1, 2, 3], divs)) == ["2021-01-05"]


def test_reference_gate_refuses_a_single_missing_session_in_the_window():
    days = U.market_sessions("US", "1990-01-02", U.ANALYSIS_END)
    audit = {"status": "ACQUIRED", "dates": days, "dropped": 0, "rows": len(days), "identityOk": True}
    ok, reasons, _ = SRC.reference_gate(audit, "1993-02-05", U.ANALYSIS_END)
    assert ok, reasons
    hole = {**audit, "dates": days.delete(days.get_loc(pd.Timestamp("2008-10-10")))}
    ok, reasons, info = SRC.reference_gate(hole, "1993-02-05", U.ANALYSIS_END)
    assert not ok and "REFERENCE_SESSION_MISSING_IN_THE_EVALUATION_WINDOW" in reasons and info["evaluationWindow"]["missing"] == ["2008-10-10"]


def test_cash_gate_reports_unknown_sessions_without_reading_a_value():
    days = pd.date_range("1993-01-01", "1993-12-31", freq="B")
    ok, _, info = SRC.cash_gate(days, "1993-02-08", "1993-12-31")
    assert ok and info["unknownCount"] == 0
    gap = days[(days < pd.Timestamp("1993-06-01")) | (days > pd.Timestamp("1993-06-30"))]
    ok, reasons, info = SRC.cash_gate(gap, "1993-02-08", "1993-12-31")
    assert not ok and info["unknownCount"] > 0 and reasons == ["CASH_RATE_UNKNOWN_ON_AN_EVALUATION_SESSION"]


def test_reused_kr_sources_are_exactly_the_sealed_kr_pins():
    sealed = json.loads((ROOT / SRC.KR_SPEC_PATH).read_text())["inputs"]["files"]
    for rel, sha in SP.kr_reused_files(ROOT).items():
        assert sealed[rel] == sha


# ---- the frozen spec ------------------------------------------------------------------------------------------------------------------
def test_spec_loads_and_rebuilds_byte_for_byte():
    import importlib.util
    spec, sha = SP.load_spec(ROOT)
    assert spec["studyId"] == SP.STUDY and SP.scientific_digest(spec) == (ROOT / SP.SCIENTIFIC_SIDECAR).read_text().strip()
    path = ROOT / "scripts" / "build_rp1_c1_us_exposure_spec.py"
    module_spec = importlib.util.spec_from_file_location("build_rp1_c1", path)
    builder = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(builder)
    assert builder.build(ROOT) == spec


def test_the_decision_rule_and_candidate_tables_are_the_sealed_kr_ones():
    spec, _ = SP.load_spec(ROOT)
    kr = json.loads((ROOT / "research_specs/kr-market-risk-model-v1.json").read_text())
    assert {k: v for k, v in spec["decision"].items() if k in kr["decision"]} == kr["decision"]
    assert spec["model"]["candidates"] == kr["model"]["candidates"]
    assert spec["model"]["levels"] == kr["model"]["levels"]


@pytest.mark.parametrize("section", list(SP.SCIENTIFIC_KEYS))
def test_a_changed_scientific_section_is_refused(section):
    spec = json.loads((ROOT / SP.SPEC_PATH).read_text())
    mutated = copy.deepcopy(spec)
    mutated[section] = {"changed": True}
    assert SP.scientific_digest(mutated) != SP.scientific_digest(spec)


def test_the_route_reuses_an_existing_workflow_and_no_workflow_file_is_added():
    # WP4d replaced the WORKFLOW_CENSUS_FROZEN blocker with a route inside an existing, unpinned workflow (see tests/test_rp1_c1_us_wp4d.py).
    spec, _ = SP.load_spec(ROOT)
    assert spec["lifecycle"]["route"]["workflow"] == ".github/workflows/seal-kr-factor-anatomy-v1.yml"
    assert not [p for p in (ROOT / ".github/workflows").iterdir() if "rp1" in p.name]
    assert spec["boundary"]["blocksStudyA"] is False and spec["boundary"]["blocksStudyB"] is False


# ---- outcome-free modes ----------------------------------------------------------------------------------------------------------------
def _poison(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("OUTCOME_FUNCTION_CALLED")
    for module, name in ((U, "evaluate"), (U, "economic_reading"), (K, "replay_path"), (U, "replay_path_with_cash"), (M, "forward_targets"),
                         (K, "candidate_targets"), (K, "path_summary")):
        monkeypatch.setattr(module, name, boom)


def test_readiness_without_a_snapshot_blocks_and_reads_no_value(monkeypatch):
    _poison(monkeypatch)
    out = SP.readiness_audit(ROOT)
    assert out["decision"] == SP.DECISION_BLOCKED and "US_SOURCE_SNAPSHOT_NOT_ACQUIRED" in out["blockers"]
    assert out["counters"] == {"usValueReads": 0, "stateComputationsOnValues": 0, "replayCallsOnValues": 0, "krSealedReproductionReads": 0}


def test_design_readiness_is_determinable_and_is_never_the_formal_gate(monkeypatch):
    _poison(monkeypatch)
    out = SP.readiness_audit(ROOT, assume_complete_reference=True)
    assert out["decision"] == SP.DESIGN_PASSED != SP.DECISION_READY
    assert out["decisionDates"] == 1754 and out["firstDecisionDate"] == "1993-02-05" and out["lastExecutionDate"] == "2026-09-14"
    assert all(v["share"] == 1.0 and v["firstDecisionDeterminable"] for v in out["determinable"].values())


def test_verify_is_outcome_free(monkeypatch):
    _poison(monkeypatch)
    out = SP.verify(ROOT)
    assert out["status"] == "VERIFIED" and out["outcomeFree"] and out["formalExecutionInThisChange"] is False


def test_kr_equivalence_is_exact_against_the_sealed_result():
    out = SP.equivalence_audit(ROOT)
    assert out["status"] == "EXACT", out["checks"]
    assert all(block["maxAbsoluteDifference"] == 0.0 for block in out["sealedBlocks"].values())
    assert out["usValuesRead"] == 0
    committed = json.loads((ROOT / SP.EQUIVALENCE_PATH).read_text())
    assert committed["status"] == "EXACT" and committed["sealedKrResultSha256"] == out["sealedKrResultSha256"]
