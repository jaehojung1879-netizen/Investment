"""rp1-inference-calibration-v1 (Track A / WP1): engine reuse, frozen protocol, depths, decision rules, host workflow. Synthetic only."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess

import numpy as np
import pytest

from pipeline import alpha_inference_calibration_v4 as v4
from pipeline import alpha_inference_calibration_v5 as v5
from pipeline import alpha_inference_mc_decision as mc
from pipeline import rp1_inference_calibration as W

ROOT = Path(__file__).resolve().parents[1]
REPRODUCED_IN_TESTS = ((0, 252, 78), (5, 252, 78))   # the cheapest H252 cells of the iid and the heavy-tailed persistent DGP


# ---- the frozen protocol ------------------------------------------------------------------------------------------------------------------
def test_the_committed_spec_is_the_module_definition_and_verifies():
    spec, sha = W.load_spec(ROOT)
    assert spec == W.build_spec(ROOT)
    assert sha == (ROOT / W.SPEC_PATH).with_suffix(".sha256").read_text().strip()


def test_every_scientific_section_is_v5s_verbatim_and_every_key_is_classified():
    spec, _ = W.load_spec(ROOT)
    base, base_sha = W.v5_spec(ROOT)
    assert base_sha == W.V5_SPEC_SHA256 == spec["predecessorSpecSha256"]
    assert W.semantic_differences(base, spec) == {"inheritedMismatches": [], "unclassifiedKeys": []}
    for key in W.INHERITED_KEYS:
        mutated = copy.deepcopy(spec)
        mutated[key] = {"changed": True}
        assert key in W.semantic_differences(base, mutated)["inheritedMismatches"]
    assert W.semantic_differences(base, {**spec, "newKnob": 1})["unclassifiedKeys"] == ["newKnob"]


def test_seed_is_new_and_the_budget_is_v5s_precision_rule():
    spec, _ = W.load_spec(ROOT)
    assert spec["seed"] == W.SEED == 20261018 and spec["seed"] not in W.PRIOR_SEEDS.values()
    assert spec["simulationReplicates"] == v5.chosen_replicates() == 8000
    assert spec["acceptance"]["materialCoverageFloor"] == 0.95 and spec["intervalConstruction"]["U1CriticalValue"] == 66.57


def test_engine_files_are_v5s_pins_and_unchanged():
    spec, _ = W.load_spec(ROOT)
    for rel, sha in v5.FORMAL_PINS["engineFiles"].items():
        assert spec["engineIdentity"]["files"][rel] == sha == hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()


def test_depths_come_from_calendars_and_the_fail_budget_counts_every_registered_decision():
    assert W.claim_depths() == {"KR_H252": 660, "US_H126": 688, "US_H252": 662}
    assert W.registered_cells() == {"126": [78, 312, 688], "252": [78, 312, 660, 662]}
    spec, _ = W.load_spec(ROOT)
    assert spec["cells"]["count"] == 42 and spec["monteCarloDecision"]["failSideDecisionCount"] == 630 == 42 * 5 * 3
    base = json.loads((ROOT / W.V5_SPEC_PATH).read_text())["monteCarloDecision"]
    for key in W.MONTE_CARLO_INHERITED:
        assert spec["monteCarloDecision"][key] == base[key]
    assert base["failSideDecisionCount"] != 630    # the count is recomputed for this grid by the frozen rule, never copied


def _copy_root(tmp_path):
    spec, _ = W.load_spec(ROOT)
    rels = [W.SPEC_PATH, str(Path(W.SPEC_PATH).with_suffix(".sha256")), W.V5_SPEC_PATH, *spec["engineIdentity"]["files"]]
    for rel in rels:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_bytes((ROOT / rel).read_bytes())
    W.load_spec(tmp_path)
    return spec


def _reseal(tmp_path, spec):
    text = json.dumps(spec, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    (tmp_path / W.SPEC_PATH).write_text(text)
    (tmp_path / W.SPEC_PATH).with_suffix(".sha256").write_text(hashlib.sha256(text.encode()).hexdigest() + "\n")


@pytest.mark.parametrize("change", ["sidecar", "seed", "replicates", "inherited", "engine", "v5"])
def test_load_spec_refuses_every_kind_of_change(tmp_path, change):
    spec = _copy_root(tmp_path)
    if change == "sidecar":
        (tmp_path / W.SPEC_PATH).with_suffix(".sha256").write_text("0" * 64 + "\n")
    elif change == "seed":
        _reseal(tmp_path, {**spec, "seed": 20261002})
    elif change == "replicates":
        _reseal(tmp_path, {**spec, "simulationReplicates": 2000})
    elif change == "inherited":
        _reseal(tmp_path, {**spec, "acceptance": {**spec["acceptance"], "materialCoverageFloor": 0.90}})
    elif change == "engine":
        path = tmp_path / "pipeline/alpha_inference_calibration_v4.py"
        path.write_bytes(path.read_bytes() + b"\n# edited\n")
    else:
        path = tmp_path / W.V5_SPEC_PATH
        path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError):
        W.load_spec(tmp_path)


# ---- the engine is called, and it is v4's ------------------------------------------------------------------------------------------------
def test_run_cell_returns_v4s_own_cell_bytes_on_a_v4_protocol():
    base = json.loads((ROOT / "research_specs/alpha-inference-calibration-v4.json").read_text())
    spec = {**base, "seed": 7, "simulationReplicates": 10, "dgps": base["dgps"][3:5],
            "horizons": {"126": {"forwardSessions": 126, "calendarWeeks": [312]}}}
    reference = v4.run_calibration(spec, formal=False)
    for index, theirs in enumerate(reference["cells"]):
        mine = W.run_cell(spec, index, 126, 312, power=False)
        assert {k: theirs[k] for k in theirs if k != "depthStatus"} == mine


def test_the_parallel_run_equals_the_serial_run_cell_for_cell():
    spec, _ = W.load_spec(ROOT)
    small = {**spec, "seed": 3, "dgps": spec["dgps"][:2], "cells": {**spec["cells"], "horizons": {"252": [78]}}}
    serial = W.run_calibration(small, workers=1, replicates=4)
    parallel = W.run_calibration(small, workers=2, replicates=4)
    assert json.dumps(serial, sort_keys=True) == json.dumps(parallel, sort_keys=True)


def test_power_readout_is_exact_for_a_uniform_accrual_location_shift():
    spec, _ = W.load_spec(ROOT)
    engine = W.engine_spec({**spec, "seed": 9})
    draw = v4.simulate_replicate(engine, spec["dgps"][4], horizon=252, weeks=78, replicate=0, dgp_index=4)
    design = v4.statistic_designs(engine, draw)["selectedMinusUniverse"]
    d, x = v4.calendar_time_series(draw["daily"], design["weights"], 252, 5, design["signalTerm"])
    base = v4.calendar_time_sn_interval(d, x, 66.57, 1e-12)
    shifted = v4.calendar_time_sn_interval(d + 0.37 * x, x, 66.57, 1e-12)
    assert shifted["estimate"] == pytest.approx(base["estimate"] + 0.37, abs=1e-12)
    assert shifted["width"] == pytest.approx(base["width"], rel=1e-12)
    readout = W.power_readout([{"estimate": e, "lower": e - 1.0, "upper": e + 1.0} for e in np.linspace(-0.5, 0.5, 11)])
    assert readout["mde80"] == pytest.approx(np.quantile(1.0 - np.linspace(-0.5, 0.5, 11), 0.8))
    assert readout["gaussianReferenceInEstimatorSd"] == pytest.approx(2.2414027 + 0.8416212, abs=1e-6)


# ---- decision rules -----------------------------------------------------------------------------------------------------------------------
def _cells(states):
    spec, _ = W.load_spec(ROOT)
    cells = []
    for (h, w), state in states.items():
        for dgp in spec["dgps"]:
            cells.append({"dgp": dgp["name"], "horizonSessions": h, "calendarWeeks": w, "status": state})
    return spec, cells


def test_a_claim_is_decided_only_at_its_actual_depth():
    spec, cells = _cells({(252, 78): mc.FAIL, (252, 312): mc.INCONCLUSIVE, (252, 660): mc.PASS, (252, 662): mc.FAIL,
                          (126, 78): mc.FAIL, (126, 312): mc.PASS, (126, 688): mc.INCONCLUSIVE})
    verdicts = W.claim_verdicts(spec, cells)
    assert verdicts["KR_H252"]["verdict"] == "CALIBRATED_FOR_PRIMARY_INFERENCE"
    assert verdicts["US_H252"]["verdict"] == "NOT_CALIBRATED_FAIL"
    assert verdicts["US_H126"]["verdict"] == "NOT_CERTIFIED_INCONCLUSIVE"
    assert verdicts["KR_H252"]["depthProfile"] == {"78": mc.FAIL, "312": mc.INCONCLUSIVE, "660": mc.PASS, "662": mc.FAIL}
    assert W.study_a_branch(verdicts) == {"KR": "H252", "US": "NONE_DESCRIPTIVE_OR_PROSPECTIVE_ONLY"}
    one_fail = [dict(c) for c in cells]
    next(c for c in one_fail if c["calendarWeeks"] == 660)["status"] = mc.FAIL
    assert W.claim_verdicts(spec, one_fail)["KR_H252"]["verdict"] == "NOT_CALIBRATED_FAIL"


def test_the_branch_falls_back_to_h126_only_when_h252_is_not_calibrated():
    ok = {"verdict": "CALIBRATED_FOR_PRIMARY_INFERENCE"}
    no = {"verdict": "NOT_CERTIFIED_INCONCLUSIVE"}
    assert W.study_a_branch({"KR_H252": no, "US_H252": no, "US_H126": ok}) == {"KR": "H126", "US": "H126"}
    assert W.study_a_branch({"KR_H252": ok, "US_H252": ok, "US_H126": no}) == {"KR": "H252", "US": "H252"}


def test_a_smoke_cannot_use_the_formal_or_a_closed_seed():
    import importlib.util
    module_spec = importlib.util.spec_from_file_location("run_rp1_wp1", ROOT / "scripts/run_rp1_inference_calibration.py")
    runner = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(runner)
    for seed in (W.SEED, 20261002, 20261001):
        with pytest.raises(SystemExit, match="REFUSED"):
            runner.main(["smoke", "--seed", str(seed), "--replicates", "2"])
    with pytest.raises(SystemExit, match="REFUSED"):
        runner.main(["smoke", "--seed", "5", "--replicates", "51"])


def test_the_module_reads_no_market_data():
    source = (ROOT / "pipeline/rp1_inference_calibration.py").read_text()
    imports = set(re.findall(r"^from pipeline(?:\.[\w.]+)? import (\w+)", source, re.M)) | set(re.findall(r"^import (\w+)", source, re.M))
    assert imports <= {"alpha_inference_calibration_v4", "alpha_inference_calibration_v5", "alpha_inference_mc_decision", "replay_calendar",
                       "_aggregate", "hashlib", "json", "numpy"}
    for forbidden in ("signal-history", "ledger/", "read_csv", "fetch_prices", "yfinance"):
        assert forbidden not in source


# ---- no workflow is touched ----------------------------------------------------------------------------------------------------------
def test_no_workflow_inventory_or_sealed_path_is_touched():
    try:
        diff = subprocess.run(["git", "diff", "--name-only", "origin/main...HEAD"], capture_output=True, text=True, cwd=ROOT, check=True).stdout.split()
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("no git history available")
    if any(p.startswith("pipeline/rp1_inference_calibration") for p in subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", "origin/main"], capture_output=True, text=True, cwd=ROOT).stdout.split()):
        pytest.skip("the protocol is already on main")
    assert not [p for p in diff if p.startswith((".github/", "research_specs/", "docs/results/", "ledger/", "data/")) or "workflow-inventory" in p]
    assert not [p for p in diff if p.startswith("pipeline/") and p != "pipeline/rp1_inference_calibration.py"]


# ---- the committed result, once it exists --------------------------------------------------------------------------------------------------
def test_a_committed_result_is_this_spec_and_complete():
    path = ROOT / W.RESULT_PATH
    if not path.exists():
        pytest.skip("the formal result is not committed yet")
    document = json.loads(path.read_text())
    spec, sha = W.load_spec(ROOT)
    assert document["specSha256"] == sha and document["runClass"] == "FORMAL" and document["seed"] == W.SEED
    result = document["result"]
    assert result["simulationReplicates"] == 8000 and len(result["cells"]) == spec["cells"]["count"]
    assert set(result["claims"]) == set(spec["claims"])
    assert {c["verdict"] for c in result["claims"].values()} <= {"CALIBRATED_FOR_PRIMARY_INFERENCE", "NOT_CALIBRATED_FAIL",
                                                                  "NOT_CERTIFIED_INCONCLUSIVE"}
    assert result["studyABranch"] == W.study_a_branch(result["claims"])


def _same(a, b, path="$"):
    """Integers, strings, flags and states exactly; floats to 1e-9 relative (the run is deterministic; a last-bit libm difference
    across interpreter builds is reported, never absorbed into a verdict -- every count and state must still match exactly)."""
    if isinstance(a, dict) and isinstance(b, dict):
        assert a.keys() == b.keys(), path
        for k in a:
            _same(a[k], b[k], f"{path}.{k}")
    elif isinstance(a, list) and isinstance(b, list):
        assert len(a) == len(b), path
        for i, (x, y) in enumerate(zip(a, b)):
            _same(x, y, f"{path}[{i}]")
    elif isinstance(a, float) or isinstance(b, float):
        assert a == pytest.approx(b, rel=1e-9, abs=1e-15), path
    else:
        assert a == b, path


@pytest.mark.parametrize("dgp_index,horizon,weeks", REPRODUCED_IN_TESTS)
def test_the_committed_result_reproduces_with_the_formal_seed(dgp_index, horizon, weeks):
    path = ROOT / W.RESULT_PATH
    if not path.exists():
        pytest.skip("the formal result is not committed yet")
    spec, _ = W.load_spec(ROOT)
    committed = {(c["dgp"], c["horizonSessions"], c["calendarWeeks"]): c for c in json.loads(path.read_text())["result"]["cells"]}
    cell = W.run_cell(spec, dgp_index, horizon, weeks)
    _same(json.loads(json.dumps(cell)), committed[(spec["dgps"][dgp_index]["name"], horizon, weeks)])
