"""MCT-v1: estimators, point-in-time panel and the one-shot harness (synthetic outcomes only)."""
from __future__ import annotations

import json

import numpy as np
import pytest

from research.market_causal_transmission_v1 import execute as EX
from research.market_causal_transmission_v1 import models as M
from research.market_causal_transmission_v1 import panel as P
from research.market_causal_transmission_v1 import spf_reader as SR
from research.market_causal_transmission_v1 import transmission as T

SPEC = json.loads(EX.PROTOCOL.read_text())


@pytest.fixture(autouse=True)
def _stdlib_spf(monkeypatch):
    """CI does not install openpyxl. The signal tests read the same preserved SPF bytes through the stdlib reader,
    whose output test_stdlib_spf_reader_equals_the_executed_parse pins to the openpyxl parse the study used."""
    monkeypatch.setattr(P, "load_spf", SR.load_spf_stdlib)


def test_stdlib_spf_reader_equals_the_executed_parse():
    fixture = json.loads((P.HERE / "evidence" / "spf-level-parsed.json").read_text())
    assert SR.load_spf_stdlib() == fixture
    assert len(fixture) == 233 and fixture[0]["year"] == 1968


def _synthetic(n=420, seed=3):
    rng = np.random.default_rng(seed)
    months = P.months("1970-01", P.shift("1970-01", n - 1))
    rows = []
    for m in months:
        rows.append({"month": m, **{k: bool(rng.random() < 0.4) for k in
                                    ("highPe", "highCape", "earnDown", "creditStress", "trendDown", "volHigh")}})
    risk = np.array([0.05 + 0.35 * (r["highPe"] and r["creditStress"]) for r in rows])
    fwd = {h: [float(-0.2 if rng.random() < q else 0.05) for q in risk] for h in (6, 12)}
    return rows, fwd


def test_walk_forward_never_reads_an_unmatured_outcome():
    rows, fwd = _synthetic()
    loss = [v <= -0.1 for v in fwd[12]]
    mask = [i >= 240 for i in range(len(rows))]
    model = {"kind": "CELLS", "inputs": ["highPe", "earnDown", "creditStress"]}
    base = M.walk_forward(rows, loss, 12, mask, model, 24, 1.0)
    for t in (250, 300, 400):
        poisoned = loss[: t - 11] + [not v for v in loss[t - 11:]]
        again = M.walk_forward(rows, poisoned, 12, [i == t for i in range(len(rows))], model, 24, 1.0)
        assert again[t] == pytest.approx(base[t])


def test_cells_and_logit_find_a_planted_interaction():
    rows, fwd = _synthetic(n=900)
    loss = [v <= -0.1 for v in fwd[12]]
    mask = [i >= 600 for i in range(len(rows))]
    cells = M.walk_forward(rows, loss, 12, mask, {"kind": "CELLS", "inputs": ["highPe", "creditStress"]}, 24, 1.0)
    base = M.walk_forward(rows, loss, 12, mask, {"kind": "BASE"}, 24, 1.0)
    idx = [i for i in range(len(rows)) if mask[i]]
    y = [float(loss[i]) for i in idx]
    assert M.brier([cells[i] for i in idx], y).mean() < M.brier([base[i] for i in idx], y).mean()
    X = np.array([[float(r["highPe"]), float(r["creditStress"])] for r in rows])
    beta = M.logistic_fit(X, np.array(loss, dtype=float), 1.0)
    assert beta[1] > 0 and beta[2] > 0


def test_missing_input_falls_back_to_base_rate():
    rows, fwd = _synthetic()
    rows[300]["earnDown"] = None
    loss = [v <= -0.1 for v in fwd[12]]
    mask = [i == 300 for i in range(len(rows))]
    p = M.walk_forward(rows, loss, 12, mask, {"kind": "CELLS", "inputs": ["earnDown"]}, 24, 1.0)
    b = M.walk_forward(rows, loss, 12, mask, {"kind": "BASE"}, 24, 1.0)
    assert p[300] == b[300]


def test_ols_hac_recovers_slopes_and_contrast():
    rng = np.random.default_rng(1)
    X = rng.normal(size=(500, 2))
    y = 0.5 * X[:, 0] - 0.3 * X[:, 1] + rng.normal(scale=0.1, size=500)
    fit = M.ols_hac(y, X, 3, ["a", "b"])
    assert fit["coef"]["a"]["b"] == pytest.approx(0.5, abs=0.02)
    c = M.linear_contrast(fit, ["a", "b"], {"a": 1.0, "b": -1.0})
    assert c["estimate"] == pytest.approx(0.8, abs=0.03) and c["p"] < 1e-6


def test_holm_and_exposure_map():
    assert M.holm({"a": 0.01, "b": 0.04, "c": None}) == {"a": 0.02, "b": 0.04, "c": None}
    assert M.exposure_from_probability(0.05, 0.1, 0.8) == 1.0
    assert M.exposure_from_probability(0.15, 0.1, 0.8) == 0.8
    assert M.exposure_from_probability(0.25, 0.1, 0.8) == 0.6
    assert M.exposure_from_probability(None, 0.1, 0.6) == 0.6


def test_auc_bounds():
    assert M.auc([0.9, 0.8, 0.1], [1, 1, 0]) == 1.0
    assert M.auc([0.1, 0.2, 0.9], [1, 1, 0]) == 0.0


def test_forecast_block_and_allocation_run_on_synthetic_data():
    rows, fwd = _synthetic(n=660)
    spec = json.loads(json.dumps(SPEC))
    spec["H2"]["sample"]["evaluation"] = [rows[300]["month"], rows[-13]["month"]]
    block = EX.forecast_block(spec, rows, fwd, 12, -0.10, 24)
    assert block["n"] > 300 and set(block["scores"]) == set(SPEC["H2"]["models"])
    rng = np.random.default_rng(9)
    ff = {P.shift(r["month"], 1): (float(rng.normal(0.005, 0.04)), 0.002) for r in rows}
    alloc = EX.allocation(spec, rows, block, ff)
    for name in ("HIST_MEAN", "VULN", "TV", "PE"):
        pol = alloc["policies"][name]
        assert pol["annualTimingNetOfCost"] == pytest.approx(pol["annualTiming"] - pol["annualCost"], abs=1e-12)
    assert alloc["policies"]["HIST_MEAN"]["averageExposure"] == pytest.approx(0.8)
    assert alloc["policies"]["HIST_MEAN"]["exposureChanges"] == 0


def test_signals_are_invariant_to_where_the_data_end():
    full = {r["month"]: r for r in P.signals()}
    short = P.signals(last="2005-12")
    for r in short:
        f = full[r["month"]]
        for k in ("pe", "highPe", "highCape", "earnDown", "creditStress", "trendDown", "volHigh", "spfSurvey"):
            assert r[k] == f[k], (r["month"], k)


def test_spf_survey_is_used_only_after_its_quarter_ends():
    for r in P.signals(first="1990-01", last="2000-12"):
        if r["spfSurvey"]:
            year, q = int(r["spfSurvey"][:4]), int(r["spfSurvey"][-1])
            assert r["month"] >= f"{year:04d}-{q * 3:02d}"


def test_credit_spread_uses_alfred_from_2007():
    rows = {r["month"]: r for r in P.signals(first="2016-01", last="2017-06")}
    assert rows["2016-12"]["spread"] is None          # BAA stalled in ALFRED: no look-ahead fill
    assert rows["2016-06"]["spread"] is not None


def test_local_projection_recovers_a_planted_shock_response():
    rows = [{"month": P.shift("1990-01", i), "MP": float(np.sin(i)), "CBI": float(np.cos(3 * i)), "ctlRet1": float(np.sin(i / 3 + 1)),
             "ctlRet12": float(np.sin(i / 7)), "ctlDgs10": float(np.cos(i / 5))} for i in range(300)]
    y = [-2.0 * r["MP"] + 1.0 * r["CBI"] for r in rows]
    out = T.local_projection(rows, y, ["MP", "CBI"], 3, {"MP": 1.0, "CBI": 1.0})
    assert out["coef"]["MP"]["b"] == pytest.approx(-2.0, abs=1e-9)
    assert out["mpMinusCbi"]["estimate"] == pytest.approx(-3.0, abs=1e-9)


def test_execution_refuses_twice_and_without_authorization(tmp_path, monkeypatch):
    monkeypatch.setattr(EX, "MARKER", tmp_path / "EXECUTION-STARTED.json")
    monkeypatch.setattr(EX, "RESULT", tmp_path / "result.json")
    monkeypatch.setattr(EX, "AUTHORIZATION", tmp_path / "none.json")
    with pytest.raises(EX.ExecutionRefused, match="NO_AUTHORIZATION_FILE"):
        EX.verify()
    (tmp_path / "EXECUTION-STARTED.json").write_text("{}")
    with pytest.raises(EX.ExecutionRefused, match="ONE_SHOT_ALREADY_SPENT"):
        EX.verify()


def test_package_signal_code_reads_no_outcome_column():
    import ast
    for module in ("panel", "readiness"):
        tree = ast.parse((P.HERE / f"{module}.py").read_text())
        funcs = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        if module == "panel":
            body = ast.dump(funcs["signals"])
            assert "outcomes" not in body
