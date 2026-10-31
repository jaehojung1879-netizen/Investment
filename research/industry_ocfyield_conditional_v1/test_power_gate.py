import json

import numpy as np
import pandas as pd
import pytest

from research.industry_ocfyield_conditional_v1 import power_gate as G


def _protocol(**over):
    p = G.load_protocol()
    p = json.loads(json.dumps(p))
    p.update(over)
    return p


def _frame(n_dates=60, n_ind=10, seed=0, missing=0.0):
    rng = np.random.default_rng(seed)
    dates = [f"2020-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(n_dates)]
    rows = []
    for d in dates:
        for i in range(n_ind):
            rows.append({"date": d, "industry": f"I{i:02d}",
                         "MEDIAN_ocfYieldProxy": rng.normal() if rng.random() >= missing else np.nan,
                         "REL_MOM_126": rng.normal(), "TOP1_CAP_SHARE": rng.random()})
    return pd.DataFrame(rows)


def test_protocol_reads_no_outcome_column():
    p = G.load_protocol()
    assert not any(c.startswith(G.FORBIDDEN_COLUMN_PREFIXES) for c in p["inputColumns"])
    bad = _protocol(inputColumns=p["inputColumns"] + ["rel_CAP_WEIGHTED_126"])
    with pytest.raises(ValueError, match="OUTCOME_COLUMN_REQUESTED"):
        G.load_inputs(bad)


def test_real_panel_input_columns_only():
    p = G.load_protocol()
    frame = G.load_inputs(p)
    assert sorted(frame.columns) == sorted(p["inputColumns"])


def test_support_inherits_min_cross_section_and_never_fills():
    p = G.load_protocol()
    frame = _frame(n_ind=9, missing=0.3)
    sup = G.support(frame, p)
    assert (sup["usable"] == (sup["counts"] >= 8)).all()
    assert sup["finite"].sum() == frame.dropna().shape[0]


def test_duplicate_industry_date_refused():
    p = G.load_protocol()
    frame = _frame(n_dates=3)
    with pytest.raises(ValueError, match="DUPLICATE"):
        G.support(pd.concat([frame, frame.iloc[:1]]), p)


def test_partial_statistic_removes_control_and_recovers_rho():
    """Label driven by a control only -> partial statistic ~0; driven by the residual feature -> ~rho."""
    p = G.load_protocol()
    sup = G.support(_frame(n_dates=80, n_ind=14, seed=3), p)
    designs = G.date_designs(sup, p)
    rng = np.random.default_rng(1)
    n_dates, n_ind = sup["finite"].shape
    sums = np.zeros((400, n_dates, n_ind))
    sums[:] = rng.standard_normal((400, n_dates, n_ind)) * np.sqrt(25)
    big = G.partial_series(designs, sums, 0.5, 25).mean()
    zero = G.partial_series(designs, sums, 0.0, 25).mean()
    assert abs(zero) < 0.02
    assert 0.40 < big < 0.60
    # pure control-driven label: rank-perfect on momentum, nothing left after residualising
    mom = sup["wide"]["REL_MOM_126"].to_numpy(float)
    control_only = np.broadcast_to(mom * 1e3, (1, n_dates, n_ind)).copy()
    assert abs(G.partial_series(designs, control_only, 0.0, 25).mean()) < 0.15


def test_sn_statistic_matches_definition_and_critical_value_is_sane():
    x = np.array([1.0, 2.0, 0.5, 1.5])
    m = x.mean()
    s = np.cumsum(x - m)
    assert G.sn_statistic(x) == pytest.approx(np.sqrt(4) * m / np.sqrt((s ** 2).sum() / 16))
    crit = G.sn_critical_value(0.025, paths=20_000, length=500)
    assert 6.0 < crit < 7.5  # fixed-b SN one-sided 2.5% is about 6.7


def test_window_sums_are_strictly_forward():
    """The synthetic label at t contains shocks t+1..t+hw only, never the shock dated t."""
    u = np.zeros((1, 10, 1))
    u[0, 4, 0] = 1.0
    sums = G.forward_window_sums(u, 3)[0, :, 0]
    assert sums.tolist() == [0, 1, 1, 1, 0, 0, 0, 0, 0, 0]
    assert G.forward_window_sums(np.ones((1, 10, 1)), 3)[0, :7, 0].tolist() == [3.0] * 7


def test_decision_rule_is_frozen_and_fails_closed():
    p = G.load_protocol()
    cells = [{"horizon": "H126", "design": "K2", "noise": "IID_NORMAL",
              "byRho": {"0": {"registeredSnRejection": 0.02}, "0.1": {"registeredSnRejection": 0.81}}}]
    assert G.decide(cells, p)["verdict"] == "GO"
    cells[0]["byRho"]["0"]["registeredSnRejection"] = 0.05
    assert G.decide(cells, p)["verdict"] == "NO_GO"
    cells[0]["byRho"]["0"]["registeredSnRejection"] = 0.02
    cells[0]["byRho"]["0.1"]["registeredSnRejection"] = 0.79
    assert G.decide(cells, p)["verdict"] == "NO_GO"


def test_committed_result_matches_protocol_and_panel_hashes():
    r = json.loads(G.RESULT_PATH.read_text())
    assert r["protocolSha256"] == G.sha256(G.PROTOCOL_PATH)
    assert r["panelSha256"] == G.sha256(G.ROOT / G.load_protocol()["panel"])
    assert r["decision"]["verdict"] == "NO_GO"
    assert r["fullCoverageCeiling"]["status"] == "POST_GATE_DIAGNOSTIC_CEILING_NOT_A_DECISION_INPUT"
