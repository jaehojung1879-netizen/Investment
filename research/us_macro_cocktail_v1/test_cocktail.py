"""Tests for us-macro-cocktail-v1 (run: pytest -q research/us_macro_cocktail_v1)."""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cocktail as C  # noqa: E402
import track_b_reaudit as TB  # noqa: E402

ROOT = HERE.parents[1]


@pytest.fixture(scope="module")
def panel():
    return C.build_panel()


@pytest.fixture(scope="module")
def state(panel):
    return C.state_frame(panel)


def test_protocol_and_raw_inputs_are_frozen():
    ident = C.verify_inputs()
    assert ident["protocolSha256"] == C.PROTOCOL_SHA256
    assert ident["files"] == 20


def test_costs_match_repository_us_table():
    us = _find_us_costs(json.loads((ROOT / "config.json").read_text()))
    assert C.BUY_BPS == us["commissionBps"] + us["spreadBps"] / 2
    assert C.SELL_BPS == us["commissionBps"] + us["sellTaxBps"] + us["spreadBps"] / 2
    proto = json.loads(C.PROTOCOL.read_text())["trackA"]["costs"]
    assert (proto["buyBps"], proto["sellBps"]) == (C.BUY_BPS, C.SELL_BPS)


def _find_us_costs(obj):
    if isinstance(obj, dict):
        if "transactionCosts" in obj and "US" in obj["transactionCosts"]:
            return obj["transactionCosts"]["US"]
        for v in obj.values():
            found = _find_us_costs(v)
            if found:
                return found
    return None


def test_total_return_adds_distribution_on_ex_date_once():
    idx = pd.date_range("2020-01-01", periods=4)
    df = pd.DataFrame({"close": [100.0, 101.0, 99.0, 99.0], "dividend": [0.0, 0.0, 2.0, 0.0]}, index=idx)
    tr = C.total_return_index(df)
    assert tr.iloc[1] == pytest.approx(1.01)
    assert tr.iloc[2] == pytest.approx(1.01 * (99 + 2) / 101)
    assert tr.iloc[3] == pytest.approx(tr.iloc[2])


def test_rebalance_charges_buy_and_sell_rates_and_conserves_value():
    vals, cost, traded = C.rebalance({}, {"SPY": 1.0}, 1.0, 10e-4, 13e-4)
    assert vals["SPY"] + cost == pytest.approx(1.0)
    assert cost == pytest.approx(vals["SPY"] * 10e-4)
    vals, cost, _ = C.rebalance({"SPY": 1.0}, {"BIL": 1.0}, 1.0, 10e-4, 13e-4)
    assert cost == pytest.approx(1.0 * 13e-4 + vals["BIL"] * 10e-4)
    assert sum(vals.values()) + cost == pytest.approx(1.0)


def test_erc_equalises_risk_contributions():
    cov = np.array([[0.04, -0.002, 0.003], [-0.002, 0.004, 0.001], [0.003, 0.001, 0.025]])
    w = C.erc_weights(cov)
    rc = w * (cov @ w)
    assert w.min() > 0 and w.sum() == pytest.approx(1)
    assert np.ptp(rc / rc.sum()) < 1e-6


def test_fred_values_are_strictly_earlier_and_fx_is_next_print(panel):
    raw = C.load_fred("DGS10")
    for day in panel.sessions[[300, 1500, 4000]]:
        expect = raw[raw.index < day].iloc[-1]
        assert panel.fred.at[day, "DGS10"] == expect
    fx = C.load_fred("DEXKOUS")
    for day in panel.sessions[[300, 1500, 4000]]:
        assert panel.fx_next[day] == fx[fx.index > day].iloc[0]
        assert panel.fx_same[day] == fx[fx.index <= day].iloc[-1]


def test_state_uses_no_future_prices(panel, state):
    cut = pd.Timestamp("2019-06-28")
    p2 = C.Panel(panel.sessions[panel.sessions <= cut], panel.tr.loc[:cut], panel.ret.loc[:cut],
                 panel.fred.loc[:cut], panel.fx_next.loc[:cut], panel.fx_same.loc[:cut])
    s2 = C.state_frame(p2)
    pd.testing.assert_series_equal(s2.loc[cut], state.loc[cut], check_names=False)


def test_walk_forward_ignores_labels_not_yet_closed(panel, state):
    sched = C.schedule(panel, "2008-05-30", "2026-10-30")
    wf = C.WalkForward(panel, state, sched.decisions, sched.executions)
    i = list(sched.decisions).index(pd.Timestamp("2018-12-31"))
    base, _ = wf.sign_forecast(i, "ridge")
    vol = wf.vol_forecast(i)
    cutoff = wf.dec_pos[i]
    future = wf.month_label_end > cutoff
    wf.y_month.loc[future] = 1e6
    wf.y_vol.loc[wf.vol_label_end > cutoff] = 50.0
    poisoned, _ = wf.sign_forecast(i, "ridge")
    assert poisoned == base
    assert wf.vol_forecast(i) == vol
    # and the label of the month being decided is itself never visible
    assert wf.month_label_end.iloc[i] > cutoff


def test_execution_follows_decision_by_one_session(panel):
    sched = C.schedule(panel, "2015-12-31", "2026-10-30")
    pos_d = panel.sessions.get_indexer(sched.decisions)
    pos_e = panel.sessions.get_indexer(sched.executions)
    assert (pos_e - pos_d == 1).all()
    assert all(d.month != e.month for d, e in zip(sched.decisions, sched.executions))


def test_bootstrap_is_deterministic():
    x = np.random.default_rng(1).normal(size=120)
    assert C.block_bootstrap_mean(x) == C.block_bootstrap_mean(x)


def test_track_b_identities_hold():
    out = TB.reaudit()
    assert out["usUniverse"]["departed"] == 324 and out["usUniverse"]["departedNoPanel"] == 212
    assert out["independentHistoricalPerformanceComputed"] is False


def test_research_code_imports_no_repository_pipeline_module():
    for name in ("cocktail.py", "relations.py", "run_study.py", "fetch_data.py", "track_b_reaudit.py"):
        tree = ast.parse((HERE / name).read_text())
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                mods = [node.module or ""]
            assert not any(m.startswith("pipeline") for m in mods), (name, mods)


def test_published_results_match_a_fresh_strategy_run(panel, state):
    """The committed headline numbers are what the frozen code computes."""
    res = json.loads((HERE / "results" / "result.json").read_text())
    sched = C.schedule(panel, "2015-12-31", "2026-10-30")
    full = C.schedule(panel, "2008-05-30", "2026-10-30")
    wf = C.WalkForward(panel, state, full.decisions, full.executions)
    pos = {d: i for i, d in enumerate(wf.dec)}
    nav = {}
    for name in ("S4_BALANCED", "D1_TREND_SIGN", "D5_TREE_SIGN"):
        t = {d: C.target_weights(name, pos[d], panel, state, wf)[0] for d in sched.decisions}
        nav[name] = C.backtest(t, sched, panel, "2026-10-30")["nav"]
    spy = C.backtest({d: {"SPY": 1.0} for d in sched.decisions}, sched, panel, "2026-10-30")["nav"]
    bil = C.backtest({d: {"BIL": 1.0} for d in sched.decisions}, sched, panel, "2026-10-30")["nav"]
    for name, n in nav.items():
        assert C.metrics(n, bil, spy)["cagrPct"] == pytest.approx(res["windows"]["primary"]["strategies"][name]["USD"]["cagrPct"], abs=1e-6)
