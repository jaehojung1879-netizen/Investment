"""MVMA-v1 Phase 2 engine on synthetic markets only (no real outcome is read here)."""
from __future__ import annotations

import copy
import json
import math

import numpy as np
import pandas as pd
import pytest

from research.market_valuation_macro_overlay_v1 import bil_total_return as BT
from research.market_valuation_macro_overlay_v1 import phase2 as P2
from research.market_valuation_macro_overlay_v1 import protocol as PR


@pytest.fixture(scope="module")
def spec():
    return json.loads(PR.PROTOCOL_PATH.read_text())


@pytest.fixture(scope="module")
def world(spec):
    sessions = [d.date().isoformat() for d in pd.bdate_range("2011-12-01", "2026-09-14")]
    rng = np.random.default_rng(5)
    spy_r = rng.normal(0.0004, 0.01, len(sessions))
    spy = dict(zip(sessions, 100 * np.cumprod(1 + spy_r)))
    bil = dict(zip(sessions, np.cumprod(np.full(len(sessions), 1 + 0.00005))))
    window = spec["calendar"]["evaluationWindowUS"]
    decisions = P2.month_end_sessions(sessions, window["firstDecision"][:7], window["lastDecision"][:7])
    ledger = []
    for i, d in enumerate(decisions):
        cheap = bool(i % 3 == 0)
        stable = bool(i % 4 != 1)
        stress = bool(i % 11 == 5)
        ledger.append({"decisionDate": d, "cheap": cheap, "earningsStable": stable, "creditStress": stress,
                       "deepDrawdown": bool(i % 50 == 7), "pe": 15 + (i % 7),
                       "targetV1": 1.0 if cheap else 0.6,
                       "targetM1T": 0.6 if (not stable and stress) else 1.0 if (stable and not stress) else 0.8,
                       "targetVM1T": 0.6 if (not stable and stress) else 1.0 if (cheap and stable and not stress) else 0.8,
                       "targetD1": 1.0 if i % 50 == 7 else 0.8})
    return sessions, spy, bil, ledger


@pytest.fixture(scope="module")
def result(world, spec):
    sessions, spy, bil, ledger = world
    small = copy.deepcopy(spec)
    small["inference"]["bootstrap"]["replicates"] = 200
    return P2.analyze(ledger, sessions, spy, bil, small)


def test_b0_gross_nav_is_the_etf_and_static_timing_is_zero(result, world):
    sessions, spy, bil, _ = world
    execs = [result["firstExecution"], result["lastExecution"]]
    b0 = result["policies"]["B0"]["gross"]
    assert b0["terminalValue"] == pytest.approx(spy[execs[1]] / spy[execs[0]], rel=1e-12)
    assert result["policies"]["B0"]["costPaid"] == 0.0
    for static in ("B1", "B2"):
        assert result["policies"][static]["costPaid"] > 0     # drift resets are traded and charged


def test_decomposition_identity_and_static_control(result):
    for policy, d in result["decomposition"].items():
        assert d["annualActiveGross"] == pytest.approx(d["annualLevel"] + d["annualTiming"], abs=1e-12)
        assert d["annualTimingNetOfCost"] == pytest.approx(d["annualTiming"] - d["annualCost"], abs=1e-12)
        assert 0.6 <= d["averageExposure"] <= 1.0


def test_constant_exposure_has_zero_timing():
    r_e, r_f = np.array([0.01, -0.02, 0.03]), np.array([0.001] * 3)
    d = P2.MT.decompose([0.8, 0.8, 0.8], r_e, r_f, 0.0004, 0.0004)
    assert d["timing"] == pytest.approx(0.0, abs=1e-15) and d["meanCost"] == 0.0


def test_h1_and_h2_inference_and_holm(result):
    h12 = result["H1"]["H12M"]
    assert h12["nCheap"] + h12["nNotCheap"] == result["periods"] == 152
    assert h12["difference"] == pytest.approx(h12["meanCheap"] - h12["meanNotCheap"], abs=1e-12)
    assert 0 <= h12["hac"]["pTwoSided"] <= 1
    adj = result["holm"]["adjusted"]
    raw = [h12["hac"]["pTwoSided"], result["H2"]["pTwoSided"]]
    assert min(adj.values()) == pytest.approx(min(1.0, 2 * min(raw)))
    assert max(adj.values()) >= max(raw)


def test_holm_matches_definition():
    adj = P2.holm({"a": 0.01, "b": 0.04, "c": 0.03})
    assert adj == {"a": 0.03, "c": 0.06, "b": 0.06}


def test_hac_with_lag_zero_matches_classical_white_slope_se():
    rng = np.random.default_rng(1)
    d = rng.random(400) < 0.5
    y = 0.02 * d + rng.normal(0, 0.05, 400)
    out = P2.hac_ols(y, d, 0)
    assert out["slope"] == pytest.approx(y[d].mean() - y[~d].mean(), abs=1e-12)
    assert out["se"] == pytest.approx(math.sqrt(y[d].var() / d.sum() + y[~d].var() / (~d).sum()), rel=1e-9)


def test_bootstrap_is_deterministic():
    a = P2.block_bootstrap(50, 12, 30, 7, lambda idx: float(idx.mean()))
    b = P2.block_bootstrap(50, 12, 30, 7, lambda idx: float(idx.mean()))
    assert np.array_equal(a, b)


def test_one_session_delay_moves_every_execution(world, spec):
    sessions, spy, bil, ledger = world
    a = P2.analyze(ledger, sessions, spy, bil, spec, delay=1, with_inference=False)
    b = P2.analyze(ledger, sessions, spy, bil, spec, delay=2, with_inference=False)
    assert a["firstExecution"] < b["firstExecution"]
    assert a["policies"]["B0"]["gross"]["terminalValue"] != b["policies"]["B0"]["gross"]["terminalValue"]


def test_cost_stress_scales_costs(world, spec):
    sessions, spy, bil, ledger = world
    one = P2.analyze(ledger, sessions, spy, bil, spec, with_inference=False)
    three = P2.analyze(ledger, sessions, spy, bil, spec, cost_stress=3.0, with_inference=False)
    assert three["decomposition"]["VM1T"]["annualCost"] == pytest.approx(3 * one["decomposition"]["VM1T"]["annualCost"])
    assert three["policies"]["VM1T"]["net"]["cagr"] < one["policies"]["VM1T"]["net"]["cagr"]


def test_window_mismatch_is_refused(world, spec):
    sessions, spy, bil, ledger = world
    with pytest.raises(AssertionError, match="WINDOW_ROW_COUNT"):
        P2.analyze(ledger[:-1], sessions, spy, bil, spec, with_inference=False)


def test_leverage_target_is_refused(world):
    sessions, spy, bil, _ = world
    with pytest.raises(AssertionError, match="LEVERAGE_OR_SHORT_TARGET"):
        P2.nav_path([1.2], sessions[:2], sessions, spy, bil, 0.0)


def test_dca_a_with_no_costs_equals_buying_each_month(world):
    sessions, spy, bil, _ = world
    execs = sessions[:: 21][:13]
    a = P2.run_dca("DCA-A", [False] * 12, execs, spy, bil, 0.0, 0.5)
    expected = sum(spy[execs[-1]] / spy[d] for d in execs[:-1])
    assert a["terminalValue"] == pytest.approx(expected, rel=1e-12)
    assert a["parkedAtEnd"] == 0.0 and a["contributed"] == 12
    b = P2.run_dca("DCA-B", [False] * 12, execs, spy, bil, 0.0, 0.5)
    assert b["parkedAtEnd"] > 0 and b["averageParkedShare"] > 0


def test_bil_total_return_restates_pre_split_distributions_and_rejects_jumps():
    closes = {"2017-11-28": 91.0, "2017-11-29": 91.0, "2017-11-30": 91.0, "2017-12-01": 91.0}
    sessions = sorted(closes)
    split = [{"date": "2017-11-30", "numerator": 1.0, "denominator": 2.0}]
    dist = BT.restate_per_current_share([{"exDate": "2017-11-29", "amount": 0.05}], split)
    assert dist == {"2017-11-29": 0.1}
    index = BT.total_return_index(closes, dist, sessions)
    assert index["2017-11-29"] == pytest.approx(1 + 0.1 / 91.0)
    with pytest.raises(BT.BilInputError, match="IMPLAUSIBLE_DAILY_RETURN"):
        BT.total_return_index({**closes, "2017-11-30": 45.5}, {}, sessions)
    with pytest.raises(BT.BilInputError, match="BIL_CLOSE_MISSING"):
        BT.total_return_index({k: v for k, v in closes.items() if k != "2017-11-29"}, {}, sessions)


def test_full_report_pipeline_runs_end_to_end_on_synthetic_data(world, spec):
    from research.market_valuation_macro_overlay_v1 import execute_phase2 as EX
    sessions, spy, bil, ledger = world
    small = copy.deepcopy(spec)
    small["inference"]["bootstrap"]["replicates"] = 50
    early = []
    for k in range(60):     # recorded PE history before the window, as the real ledger carries
        early.append({"decisionDate": f"2007-{k % 12 + 1:02d}-0{k // 12 + 1}", "pe": 14.0 + k % 5})
    full_ledger = early + ledger
    primary = P2.analyze(ledger, sessions, spy, bil, small)
    primary["_spy"], primary["_bil"] = spy, bil
    report = {"primary": EX.strip(primary), "verdicts": EX.verdicts(primary, small),
              "comparisons": EX.comparisons(primary, small), "tables": EX.state_and_regime_tables(primary, small),
              "robustness": EX.robustness(full_ledger, sessions, spy, bil, small, primary), "dca": EX.dca(primary, small)}
    text = json.dumps(report, sort_keys=True)
    assert "NaN" not in text and '"_' not in text
    assert report["verdicts"]["promotionEligible"] is False
    assert set(report["dca"]) >= {"DCA-A", "DCA-B", "DCA-C"}
    assert EX.monthly_csv(primary).count("\n") == 153


def test_execution_refuses_without_authorization_or_after_a_result(tmp_path, monkeypatch):
    from research.market_valuation_macro_overlay_v1 import execute_phase2 as EX
    monkeypatch.setattr(EX, "RESULT", tmp_path / "result.json")
    monkeypatch.setattr(EX, "AUTHORIZATION", tmp_path / "missing.json")
    with pytest.raises(EX.ExecutionRefused, match="NO_AUTHORIZATION_FILE"):
        EX.verify_authorization()
    (tmp_path / "result.json").write_text("{}")
    with pytest.raises(EX.ExecutionRefused, match="ONE_SHOT_ALREADY_SPENT"):
        EX.verify_authorization()
