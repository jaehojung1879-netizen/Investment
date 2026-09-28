import ast
import builtins
import copy
import hashlib
import io
import json
import math
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest
from scipy.stats import norm

from pipeline import alpha_inference_calibration_v4 as v4
from pipeline import alpha_inference_calibration_v5 as v5
from pipeline import alpha_inference_mc_decision as mc

V4_SPEC_PATH = Path("research_specs/alpha-inference-calibration-v4.json")
V5_SPEC_PATH = Path("research_specs/alpha-inference-calibration-v5.json")
WORKFLOW = Path(".github/workflows/alpha-inference-calibration-v5.yml")
DIAGNOSTICS = Path("docs/results/alpha-inference-calibration-v5-precision-diagnostics.json")
V4_SHA = "012e43177b8e8ec7143eff30d7280c4cf8015b32b464bcddd87c09f75c984a5d"


def _v4():
    return json.loads(V4_SPEC_PATH.read_text())


def _v5():
    return json.loads(V5_SPEC_PATH.read_text())


def _validate(spec, *, formal=True, sha=V4_SHA, predecessor=None):
    v5.validate_spec(
        spec,
        predecessor_spec=_v4() if predecessor is None else predecessor,
        predecessor_spec_sha256=sha,
        formal=formal,
    )


def _tiny_spec(weeks=12, horizon=21, dgp_index=5, replicates=3):
    spec = _v5()
    spec["dgps"] = [spec["dgps"][dgp_index]]
    spec["horizons"] = {str(horizon): {"forwardSessions": horizon, "calendarWeeks": [weeks]}}
    spec["minimumConfirmatoryDepth"] = {str(horizon): {"calendarWeeks": weeks}}
    spec["simulationReplicates"] = replicates
    return spec


# ---------------------------------------------------------------- predecessor is frozen and untouched
def test_v4_protocol_is_the_frozen_closed_predecessor():
    assert hashlib.sha256(V4_SPEC_PATH.read_bytes()).hexdigest() == V4_SHA
    spec = _v5()
    assert spec["predecessorSpecSha256"] == V4_SHA == v5.FORMAL_PINS["predecessorSpecSha256"]
    result = spec["v4FormalResult"]
    assert result["primaryStatus"] == "INCONCLUSIVE" and result["closed"] is True
    assert result["statusCounts"] == {"PASS": 22, "INCONCLUSIVE": 2, "FAIL": 0, "DATA_INSUFFICIENT": 0}
    assert result["workflowRun"] == 36493207997 and result["artifactId"] == 11002423544
    assert result["artifactZipSha256"] == "0013579e661e026a592a658dfbaf3337ff5f6741d7432d1a7557332ba9dc08a8"
    assert len(result["inconclusiveCells"]) == 2
    assert all("H21 / 78" in cell for cell in result["inconclusiveCells"])


def test_engine_files_match_their_frozen_bytes():
    from scripts.run_alpha_inference_calibration_v5 import verify_engine_identity

    verify_engine_identity()
    assert _v5()["engineIdentity"]["files"] == v5.FORMAL_PINS["engineFiles"]
    for relative, expected in v5.FORMAL_PINS["engineFiles"].items():
        assert hashlib.sha256(Path(relative).read_bytes()).hexdigest() == expected
    tampered = dict(v5.FORMAL_PINS["engineFiles"])
    tampered["pipeline/alpha_inference_calibration_v4.py"] = "0" * 64
    with pytest.raises(ValueError, match="ENGINE_FILE_CHANGED"):
        verify_engine_identity(tampered)


# ---------------------------------------------------------------- v4 -> v5 semantic equivalence
def test_v5_is_semantically_identical_to_v4_except_the_permitted_differences():
    differences = v5.semantic_differences(_v4(), _v5())
    assert differences == {"scientificMismatches": [], "unclassifiedKeys": []}
    v4_spec, v5_spec = _v4(), _v5()
    for key in v5.SCIENTIFIC_KEYS:
        assert json.dumps(v4_spec[key], sort_keys=True) == json.dumps(v5_spec[key], sort_keys=True), key
    # the science keys named by the task, spelled out
    assert v5_spec["dgps"] == v4_spec["dgps"] and len(v5_spec["dgps"]) == 6
    assert v5_spec["horizons"] == v4_spec["horizons"]
    assert v5_spec["statistics"] == v4_spec["statistics"]
    assert v5_spec["intervalConstruction"] == v4_spec["intervalConstruction"]
    assert v5_spec["intervalConstruction"]["U1CriticalValue"] == 66.57
    assert v5_spec["acceptance"] == v4_spec["acceptance"]
    assert v5_spec["monteCarloDecision"] == v4_spec["monteCarloDecision"]
    assert v5_spec["monteCarloDecision"]["failSideDecisionCount"] == 360
    assert v5_spec["minimumConfirmatoryDepth"] == v4_spec["minimumConfirmatoryDepth"]
    for key in ("namesPerDate", "signalStepSessions", "selectionFraction", "syntheticForecastScale", "nullConstruction"):
        assert v5_spec[key] == v4_spec[key]


def test_only_identity_seed_budget_and_documentation_differ():
    changed = {
        key for key in set(_v4()) | set(_v5())
        if json.dumps(_v4().get(key), sort_keys=True) != json.dumps(_v5().get(key), sort_keys=True)
    }
    assert changed <= set(v5.PERMITTED_DIFFERENCE_KEYS)
    assert {"contract", "seed", "simulationReplicates"} <= changed
    assert not changed & set(v5.SCIENTIFIC_KEYS)


def test_equivalence_check_detects_any_scientific_change_and_any_unclassified_key():
    base = _v5()
    for key in v5.SCIENTIFIC_KEYS:
        broken = copy.deepcopy(base)
        broken[key] = "TAMPERED"
        assert key in v5.semantic_differences(_v4(), broken)["scientificMismatches"], key
    smuggled = copy.deepcopy(base)
    smuggled["easierDgp"] = {"name": "EASY"}
    assert v5.semantic_differences(_v4(), smuggled)["unclassifiedKeys"] == ["easierDgp"]
    dgp_tamper = copy.deepcopy(base)
    dgp_tamper["dgps"] = dgp_tamper["dgps"][:-1]
    assert v5.semantic_differences(_v4(), dgp_tamper)["scientificMismatches"] == ["dgps"]


def test_v5_engine_gives_identical_results_to_v4_engine_for_the_same_protocol():
    tiny = _tiny_spec(replicates=4)
    direct = v4.run_calibration(v5.engine_spec(tiny), formal=False)
    wrapped = v5.run_calibration(tiny, formal=False)
    assert wrapped["cells"] == direct["cells"]
    assert wrapped["primaryStatus"] == direct["primaryStatus"]
    assert wrapped["statusCounts"] == direct["statusCounts"]
    assert wrapped["contract"] == "ALPHA_INFERENCE_CALIBRATION_V5"
    assert direct["contract"] == "ALPHA_INFERENCE_CALIBRATION_V4"
    assert wrapped["engine"]["contract"] == "ALPHA_INFERENCE_CALIBRATION_V4"


def test_v5_module_contains_no_simulation_or_decision_logic_of_its_own():
    tree = ast.parse(Path("pipeline/alpha_inference_calibration_v5.py").read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module)
    assert imported <= {"__future__", "math", "typing", "scipy.stats", "pipeline"}
    text = Path("pipeline/alpha_inference_calibration_v5.py").read_text()
    for banned in ("open(", "numpy", "default_rng", "lfilter", "_self_normalized_interval"):
        assert banned not in text


# ---------------------------------------------------------------- frozen budget, seed and precision rule
def test_seed_is_new_and_differs_from_every_closed_protocol():
    seed = _v5()["seed"]
    assert seed == v5.FORMAL_PINS["seed"] == 20261002
    assert seed != _v4()["seed"]
    for name, prior in v5.PRIOR_SEEDS.items():
        assert seed != prior, name
    for version in (1, 2, 3):
        prior = json.loads(Path(f"research_specs/alpha-inference-calibration-v{version}.json").read_text())["seed"]
        assert prior == v5.PRIOR_SEEDS[f"v{version}"] and seed != prior
    assert _v4()["seed"] == v5.PRIOR_SEEDS["v4"]


def test_replicate_count_is_exactly_frozen_and_follows_the_precision_rule():
    spec = _v5()
    assert spec["simulationReplicates"] == 8000 == v5.FORMAL_PINS["simulationReplicates"] == v5.chosen_replicates()
    assert spec["precisionCriterion"]["chosenReplicates"] == 8000
    assert v5.required_replicates_normal() == 7299 == spec["precisionCriterion"]["normalApproximationMinimumR"]
    assert v5.required_replicates_exact() == 7501 == spec["precisionCriterion"]["exactClopperPearsonMinimumR"]
    assert v5.round_up_to_unit(7501) == 8000 and v5.round_up_to_unit(7299) == 7500
    assert v5.chosen_replicates() % v5.ROUNDING_UNIT == 0
    # the smallest clean number that meets both criteria: one unit lower does not
    assert v5.chosen_replicates() - v5.ROUNDING_UNIT < v5.required_replicates_exact()


def test_precision_criterion_is_satisfied_by_both_the_normal_and_the_exact_interval():
    r = _v5()["simulationReplicates"]
    z = float(norm.ppf(0.975))  # 1.959963984..., not the rounded 1.96
    assert 1.96 < z + 1e-4 and z < 1.96  # the exact percentile is a hair below the rounded value
    assert z * math.sqrt(0.95 * 0.05 / r) <= 0.005
    assert v5.exact_cp_half_width(r) <= 0.005
    # 7,500 is the instructive near miss: fine by the normal formula, a hair over exactly
    assert z * math.sqrt(0.95 * 0.05 / 7500) <= 0.005 < v5.exact_cp_half_width(7500)
    assert v5.exact_cp_half_width(7501) <= 0.005
    assert v5.exact_cp_half_width(2000) > 0.009  # v4's budget was about twice as wide
    assert all(v5.exact_cp_half_width(x) <= 0.005 for x in range(r, r + 200, 7))


def test_normal_approximation_uses_the_exact_percentile_and_is_documented_that_way():
    z = float(norm.ppf(0.975))
    exact_real_minimum = (z / 0.005) ** 2 * 0.95 * 0.05
    rounded_real_minimum = (1.96 / 0.005) ** 2 * 0.95 * 0.05
    assert math.ceil(exact_real_minimum) == 7299 == v5.required_replicates_normal()
    assert math.ceil(rounded_real_minimum) == 7300  # the rounded literal would have said 7,300
    assert v5.chosen_replicates() == 8000  # immaterial to the budget: the exact criterion dominates
    formula = _v5()["precisionCriterion"]["normalApproximationFormula"]
    assert formula.startswith("z_0.975 * sqrt(") and "1.959963984" in formula
    doc = Path("docs/alpha-inference-calibration-v5-precision.md").read_text()
    assert "1.959963984" in doc and "7,298.77" in doc and "7,299.04" in doc  # 7,299.04 only as the literal-1.96 remark
    assert "1.96·√" not in doc  # the rounded literal is no longer the stated formula
    diag = json.loads(DIAGNOSTICS.read_text())
    assert math.isclose(diag["precisionRule"]["zValue"], z, abs_tol=1e-9)
    assert math.isclose(diag["precisionRule"]["normalApproximationRealMinimum"], exact_real_minimum, abs_tol=1e-6)
    half = diag["halfWidthByBudget"]["8000"]["normalApproximation"]
    assert math.isclose(half, z * math.sqrt(0.95 * 0.05 / 8000), abs_tol=1e-9)


def test_precision_helpers_reject_invalid_inputs():
    for bad in ((0.0, 0.95, 0.95), (0.005, 1.0, 0.95), (0.005, 0.95, 0.4)):
        with pytest.raises(ValueError):
            v5.required_replicates_normal(*bad)
    with pytest.raises(ValueError):
        v5.exact_cp_half_width(0)
    with pytest.raises(ValueError):
        v5.round_up_to_unit(0)


def test_the_rule_does_not_depend_on_any_v4_cell():
    criterion = _v5()["precisionCriterion"]
    assert "any v4 cell" in criterion["notDerivedFrom"]
    assert v5.required_replicates_normal(0.005, 0.95, 0.95) == 7299  # p = 0.95, not a v4 cell value
    # the rule's inputs are exactly these three constants
    assert (v5.PRECISION_TARGET_HALF_WIDTH, v5.PRECISION_AT_PROBABILITY, v5.PRECISION_LEVEL) == (0.005, 0.95, 0.95)


# ---------------------------------------------------------------- exact Clopper-Pearson operating characteristic
def _levels():
    cfg = _v5()["monteCarloDecision"]
    return {
        "pass_alpha": cfg["passSideOneSidedAlpha"],
        "fail_alpha": mc.fail_side_alpha(cfg["failSideFamilywiseAlpha"], cfg["failSideDecisionCount"]),
    }


def test_decision_boundaries_at_the_frozen_budget_match_the_classifier():
    levels = _levels()
    bounds = v5.decision_boundaries(8000, kind=mc.FLOOR, threshold=0.95, **levels)
    assert bounds == {"minSuccessesForPass": 7639, "maxSuccessesForFail": 7526}
    kw = dict(kind=mc.FLOOR, threshold=0.95, pass_alpha=levels["pass_alpha"], fail_alpha=levels["fail_alpha"])
    assert mc.classify_metric(7639, 8000, **kw)["state"] == mc.PASS
    assert mc.classify_metric(7638, 8000, **kw)["state"] == mc.INCONCLUSIVE
    assert mc.classify_metric(7526, 8000, **kw)["state"] == mc.FAIL
    assert mc.classify_metric(7527, 8000, **kw)["state"] == mc.INCONCLUSIVE
    ceiling = v5.decision_boundaries(8000, kind=mc.CEILING, threshold=0.05, **levels)
    assert ceiling["maxEventsForPass"] < 400 < ceiling["minEventsForFail"]
    # more precision moves both boundaries toward the floor from each side
    old = v5.decision_boundaries(2000, kind=mc.FLOOR, threshold=0.95, **levels)
    assert old["minSuccessesForPass"] / 2000 > 7639 / 8000 > 7526 / 8000 > old["maxSuccessesForFail"] / 2000


def test_state_probabilities_are_a_distribution_monotone_in_true_coverage():
    levels = _levels()
    previous_pass, previous_fail = -1.0, 2.0
    for p in (0.93, 0.945, 0.95, 0.955, 0.96, 0.97):
        probs = v5.state_probabilities(600, p, kind=mc.FLOOR, threshold=0.95, **levels)
        assert math.isclose(sum(probs.values()), 1.0, abs_tol=1e-9)
        assert all(0.0 <= v <= 1.0 for v in probs.values())
        assert probs[mc.PASS] >= previous_pass and probs[mc.FAIL] <= previous_fail
        previous_pass, previous_fail = probs[mc.PASS], probs[mc.FAIL]
    with pytest.raises(ValueError):
        v5.state_probabilities(10, 1.5, kind=mc.FLOOR, threshold=0.95, **levels)


def test_published_diagnostics_match_a_fresh_computation_and_stay_development_only():
    diag = json.loads(DIAGNOSTICS.read_text())
    assert diag["label"] == "DEVELOPMENT_ONLY" and diag["outcomeFree"] is True
    rule = diag["precisionRule"]
    assert rule["chosenReplicates"] == _v5()["simulationReplicates"]
    assert rule["normalApproximationMinimumR"] == 7299 and rule["exactClopperPearsonMinimumR"] == 7501
    at = diag["operatingCharacteristicByBudget"]["8000"]
    assert at["coverageFloorBoundaries"] == v5.decision_boundaries(8000, kind=mc.FLOOR, threshold=0.95, **_levels())
    fresh = v5.state_probabilities(8000, 0.955, kind=mc.FLOOR, threshold=0.95, **_levels())
    for state in (mc.PASS, mc.INCONCLUSIVE, mc.FAIL):
        assert math.isclose(at["coverageByTrueValue"]["0.955"][state], fresh[state], abs_tol=1e-8)
    # the generic grid required by the task is present, and no registered cell is named
    for p in ("0.940", "0.945", "0.950", "0.955", "0.960", "0.965", "0.975"):
        assert p in at["coverageByTrueValue"]
    text = json.dumps(diag)
    for cell_marker in ("PERSISTENT_SHARED_HEAVY", "exactCoverageV4", "H21 / 78"):
        assert cell_marker not in text


# ---------------------------------------------------------------- formal protocol pinning
def test_frozen_v5_protocol_validates_in_formal_mode():
    _validate(_v5())


def test_formal_mode_refuses_every_altered_scientific_or_identity_choice():
    base = _v5()
    mutations = {
        "contract": lambda s: s.update(contract="ALPHA_INFERENCE_CALIBRATION_V4"),
        "seed to v4 seed": lambda s: s.update(seed=20261001),
        "seed": lambda s: s.update(seed=12345),
        "replicates": lambda s: s.update(simulationReplicates=8001),
        "replicates to v4": lambda s: s.update(simulationReplicates=2000),
        "chosenReplicates": lambda s: s["precisionCriterion"].update(chosenReplicates=7500),
        "targetHalfWidth": lambda s: s["precisionCriterion"].update(targetHalfWidth=0.01),
        "atProbability": lambda s: s["precisionCriterion"].update(atProbability=0.9),
        "predecessor hash": lambda s: s.update(predecessorSpecSha256="0" * 64),
        "engine identity": lambda s: s["engineIdentity"]["files"].update({"pipeline/alpha_inference_calibration_v4.py": "1" * 64}),
        "dgp parameter": lambda s: s["dgps"][0].update(sigmaShared=0.6),
        "dgp removed": lambda s: s["dgps"].pop(),
        "dgp added": lambda s: s["dgps"].append({**s["dgps"][0], "name": "EASY"}),
        "horizon depths": lambda s: s["horizons"]["126"].update(calendarWeeks=[100, 624]),
        "minimum depth": lambda s: s["minimumConfirmatoryDepth"]["126"].update(calendarWeeks=100),
        "statistics": lambda s: s["statistics"].update(confirmatory=["dateMean"]),
        "rankIC promoted": lambda s: s["statistics"].update(
            confirmatory=s["statistics"]["confirmatory"] + ["rankIC"], descriptive=[]),
        "coverage floor": lambda s: s["acceptance"].update(materialCoverageFloor=0.9),
        "false-positive ceiling": lambda s: s["acceptance"].update(directionalFalsePositiveCeiling=0.1),
        "undefined ceiling": lambda s: s["acceptance"].update(undefinedFrequencyCeiling=0.2),
        "half-width guard": lambda s: s["acceptance"].update(maximumMonteCarlo95HalfWidth=0.5),
        "u1": lambda s: s["intervalConstruction"].update(U1CriticalValue=60.0),
        "interval method": lambda s: s["intervalConstruction"].update(method="V3_SIGNAL_DATE"),
        "mc method": lambda s: s["monteCarloDecision"].update(intervalMethod="WALD"),
        "mc pass alpha": lambda s: s["monteCarloDecision"].update(passSideOneSidedAlpha=0.05),
        "mc fail alpha": lambda s: s["monteCarloDecision"].update(failSideFamilywiseAlpha=0.2),
        "mc decision count": lambda s: s["monteCarloDecision"].update(failSideDecisionCount=1),
        "selection fraction": lambda s: s.update(selectionFraction=0.5),
        "names per date": lambda s: s.update(namesPerDate=10),
        "null construction": lambda s: s["nullConstruction"].update(selection="changed"),
        "unclassified key": lambda s: s.update(extraEasyCase=True),
    }
    for name, mutate in mutations.items():
        broken = copy.deepcopy(base)
        mutate(broken)
        with pytest.raises(ValueError, match="INVALID_V5_PROTOCOL"):
            _validate(broken)
            raise AssertionError(f"not refused in formal mode: {name}")


def test_formal_mode_refuses_a_wrong_or_missing_predecessor():
    with pytest.raises(ValueError, match="INVALID_V5_PROTOCOL"):
        _validate(_v5(), sha="f" * 64)
    with pytest.raises(ValueError, match="INVALID_V5_PROTOCOL"):
        v5.validate_spec(_v5(), predecessor_spec=None, predecessor_spec_sha256=V4_SHA, formal=True)
    changed = _v4()
    changed["seed"] = 1
    changed["dgps"] = changed["dgps"][:2]
    with pytest.raises(ValueError, match="INVALID_V5_PROTOCOL"):
        _validate(_v5(), predecessor=changed)


def test_development_mode_moves_only_seed_and_budget_never_the_method_or_thresholds():
    dev = _v5()
    dev["seed"], dev["simulationReplicates"] = 7, 5
    _validate(dev, formal=False)
    for mutate in (
        lambda s: s["acceptance"].update(materialCoverageFloor=0.9),
        lambda s: s["intervalConstruction"].update(U1CriticalValue=60.0),
        lambda s: s["monteCarloDecision"].update(passSideOneSidedAlpha=0.05),
        lambda s: s["statistics"].update(descriptive=[]),
        lambda s: s.update(contract="ALPHA_INFERENCE_CALIBRATION_V4"),
    ):
        broken = copy.deepcopy(dev)
        mutate(broken)
        with pytest.raises(ValueError, match="INVALID_V5_PROTOCOL"):
            _validate(broken, formal=False)


def test_run_calibration_defaults_to_formal_and_refuses_a_modified_protocol():
    with pytest.raises(ValueError, match="INVALID_V5_PROTOCOL"):
        v5.run_calibration(_tiny_spec(), predecessor_spec=_v4(), predecessor_spec_sha256=V4_SHA)


def test_a_small_complete_run_reports_a_valid_three_state_status_and_never_reads_files(monkeypatch):
    tiny = _tiny_spec(replicates=3)  # read the protocol BEFORE file access is blocked

    def refuse(*args, **kwargs):
        raise AssertionError(f"file access attempted: {args}")

    monkeypatch.setattr(builtins, "open", refuse)
    monkeypatch.setattr(Path, "open", refuse)
    monkeypatch.setattr(Path, "read_text", refuse)
    monkeypatch.setattr(Path, "read_bytes", refuse)
    result = v5.run_calibration(tiny, formal=False)
    assert result["primaryStatus"] == mc.INCONCLUSIVE
    assert result["replicationOf"]["contract"] == "ALPHA_INFERENCE_CALIBRATION_V4"
    assert result["precisionCriterion"]["chosenReplicates"] == 8000
    json.dumps(result, allow_nan=False)


# ---------------------------------------------------------------- runner
def _run(argv):
    from scripts.run_alpha_inference_calibration_v5 import main

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = main(argv)
    return code, buffer.getvalue()


def test_runner_can_be_invoked_directly_from_the_repo_root():
    completed = subprocess.run(
        [sys.executable, "scripts/run_alpha_inference_calibration_v5.py", "--help"],
        check=False, capture_output=True, text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "precision-only replication" in completed.stdout


def test_development_smoke_is_deterministic_labelled_and_without_verdict_authority(tmp_path):
    spec_file = tmp_path / "spec.json"
    spec_file.write_text(json.dumps(_tiny_spec()))
    outputs = [tmp_path / name for name in ("a.json", "b.json", "c.json")]
    for out, seed in zip(outputs, (11, 11, 12), strict=True):
        code, printed = _run(["--spec", str(spec_file), "--output", str(out),
                              "--development-smoke", "3", "--development-seed", str(seed)])
        assert code == 0
        assert "DEVELOPMENT_ONLY" in printed
    assert outputs[0].read_bytes() == outputs[1].read_bytes()
    a, c = (json.loads(p.read_text()) for p in (outputs[0], outputs[2]))
    assert a["runClass"] == "DEVELOPMENT_ONLY" and a["verdictAuthority"] == "NONE_DEVELOPMENT_ONLY"
    assert a["cells"] != c["cells"]
    keep = lambda d: {k: v for k, v in d.items() if k not in ("cells", "primaryFailures", "inconclusiveCells",  # noqa: E731
                                                            "statusCounts", "primaryStatus", "seedUsed")}
    assert keep(a) == keep(c)
    assert a["seedUsed"] == 11 and c["seedUsed"] == 12


def test_development_smoke_cannot_use_the_formal_seed_or_any_closed_protocols_seed(tmp_path):
    for seed in (20261002, 20261001, 20260930, 20260929, 20260928):
        with pytest.raises(SystemExit, match="REFUSED"):
            _run(["--output", str(tmp_path / "o.json"), "--development-smoke", "2", "--development-seed", str(seed)])


def test_a_complete_inconclusive_result_exits_zero_with_a_complete_artifact(tmp_path):
    spec_file = tmp_path / "spec.json"
    spec_file.write_text(json.dumps(_tiny_spec()))
    out = tmp_path / "o.json"
    code, printed = _run(["--spec", str(spec_file), "--output", str(out),
                          "--development-smoke", "3", "--development-seed", "5"])
    artifact = json.loads(out.read_text())
    assert code == 0 and artifact["primaryStatus"] == "INCONCLUSIVE" and "INCONCLUSIVE" in printed
    assert artifact["contract"] == "ALPHA_INFERENCE_CALIBRATION_V5"


def test_formal_runner_rejects_changed_dgps_horizons_thresholds_and_statistics(tmp_path):
    base = _v5()
    changes = {
        "dgps": lambda s: s["dgps"].pop(),
        "horizons": lambda s: s["horizons"]["126"].update(calendarWeeks=[100, 624]),
        "threshold": lambda s: s["acceptance"].update(materialCoverageFloor=0.9),
        "statistics": lambda s: s["statistics"].update(confirmatory=["dateMean"]),
        "replicates": lambda s: s.update(simulationReplicates=2000),
        "seed": lambda s: s.update(seed=1),
    }
    for name, mutate in changes.items():
        spec = copy.deepcopy(base)
        mutate(spec)
        spec_file = tmp_path / f"{name}.json"
        spec_file.write_text(json.dumps(spec))
        out = tmp_path / f"{name}-out.json"
        code, _ = _run(["--spec", str(spec_file), "--output", str(out)])
        artifact = json.loads(out.read_text())
        assert code == 1, name
        assert artifact["primaryStatus"] == "INFRASTRUCTURE_ERROR" and "INVALID_V5_PROTOCOL" in artifact["error"], name


def test_infrastructure_error_leaves_a_complete_error_artifact(tmp_path):
    spec = _v5()
    spec["contract"] = "NOT_V5"
    spec_file = tmp_path / "spec.json"
    spec_file.write_text(json.dumps(spec))
    out = tmp_path / "o.json"
    code, printed = _run(["--spec", str(spec_file), "--output", str(out)])
    artifact = json.loads(out.read_text())
    assert code == 1 and "INFRASTRUCTURE_ERROR" in printed
    assert artifact["primaryStatus"] == "INFRASTRUCTURE_ERROR"
    for key in ("contract", "runClass", "specSha256", "error", "traceback"):
        assert key in artifact


def test_runner_refuses_real_data_paths_for_spec_and_output(tmp_path):
    for bad in ("ledger/x.json", "data/site-data.json", "docs/results/x.json", "signal-history/x.json"):
        with pytest.raises(SystemExit, match="REFUSED"):
            _run(["--output", bad])
        with pytest.raises(SystemExit, match="REFUSED"):
            _run(["--spec", bad, "--output", str(tmp_path / "o.json")])


def test_runner_reuses_the_v4_path_guard_rather_than_a_second_copy():
    from scripts import run_alpha_inference_calibration_v4 as runner4
    from scripts import run_alpha_inference_calibration_v5 as runner5

    assert runner5.guard_path is runner4.guard_path
    assert {"ledger", "data", "results", "signal-history", "historical"} <= set(runner4.FORBIDDEN_COMPONENTS)


# ---------------------------------------------------------------- workflow
def test_workflow_is_manual_secret_free_main_only_and_always_uploads():
    text = "\n".join(line for line in WORKFLOW.read_text().splitlines() if not line.lstrip().startswith("#"))
    assert "workflow_dispatch" in text
    for forbidden in ("schedule:", "push:", "pull_request", "secrets.", "signal-history", "--development-smoke"):
        assert forbidden not in text
    assert "refs/heads/main" in text and "if: always()" in text and "contents: read" in text
    assert "alpha-inference-calibration-v5.json" in text
    assert "alpha-inference-calibration-v4.json" in text  # the predecessor protocol is also verified unchanged
    assert "alpha-inference-calibration-v4" not in text.replace("alpha-inference-calibration-v4.json", "")
    assert "name: Synthetic alpha inference calibration v5" in WORKFLOW.read_text()


def test_workflow_only_fails_the_job_for_infrastructure_errors():
    text = WORKFLOW.read_text()
    verdict_step = text.split("- name: Record methodological verdict")[1].split("- name: Upload")[0]
    assert "exit 1" not in verdict_step and "::warning::" in verdict_step and "INCONCLUSIVE" in verdict_step
    run_step = text.split("- name: Run synthetic-only calibration v5")[1].split("- name: Record")[0]
    assert "|| true" not in run_step
    runner = Path("scripts/run_alpha_inference_calibration_v5.py").read_text()
    assert runner.count("return 1") == 1
