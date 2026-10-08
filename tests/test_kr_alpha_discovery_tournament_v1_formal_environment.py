"""kr-alpha-discovery-tournament-v1 post-outcome audit: the formal execution environment manifest, the cheap parity preflight that runs before any expensive work,
the diagnostics of a refused reproduction, and proof that none of it touches a scientific rule or a sealed file. Synthetic observations only: no test depends on
the machine it runs on."""
from __future__ import annotations

import ast
import copy
import hashlib
import json
from pathlib import Path
import re

import pytest

from pipeline import kr_alpha_tournament_execution as E
from pipeline import kr_alpha_tournament_formal_environment as FE
from pipeline import kr_alpha_tournament_postoutcome_integrity_audit as A
from scripts import check_kr_alpha_tournament_formal_environment as CLI

ROOT = Path(__file__).resolve().parents[1]
AUDIT_WORKFLOW = ROOT / ".github/workflows/kr-alpha-discovery-tournament-v1-postoutcome-integrity-audit.yml"
FORMAL_WORKFLOW = ROOT / ".github/workflows/kr-alpha-discovery-tournament-v1.yml"
RESULT = ROOT / A.FORMAL["resultPath"]

# The 47 packages pip reported installing in the execute job of formal run 37535814142 (job 112519474120), typed here independently of the manifest.
FORMAL_PACKAGES = {
    "beautifulsoup4": "4.15.0", "certifi": "2026.7.22", "cffi": "2.1.1", "charset-normalizer": "3.5.2", "cloudpickle": "3.1.2", "curl-cffi": "0.16.3",
    "exchange-calendars": "4.11.1", "finance-datareader": "0.9.110", "fredapi": "0.5.2", "frozendict": "2.4.7", "idna": "3.20", "iniconfig": "2.3.0",
    "joblib": "1.6.0", "korean-lunar-calendar": "0.4.0", "lightgbm": "4.6.0", "lxml": "6.1.3", "multitasking": "0.0.13", "narwhals": "2.26.0", "numpy": "2.3.1",
    "packaging": "26.3", "pandas": "2.3.0", "peewee": "4.5.2", "platformdirs": "4.12.3", "plotly": "7.1.0", "pluggy": "1.6.0", "protobuf": "7.36.2",
    "pycparser": "3.0", "pygments": "2.21.0", "pyluach": "2.3.0", "pytest": "8.4.1", "python-dateutil": "2.9.0.post0", "pytz": "2026.5", "requests": "2.34.2",
    "requests-file": "3.0.1", "ruff": "0.15.8", "scikit-learn": "1.7.0", "scipy": "1.16.0", "six": "1.17.0", "soupsieve": "2.10", "threadpoolctl": "3.7.0",
    "toolz": "1.1.0", "tqdm": "4.70.1", "typing-extensions": "4.16.0", "tzdata": "2026.5", "urllib3": "2.8.0", "websockets": "17.2", "yfinance": "0.2.65"}


def _exact(manifest, **host):
    """What a perfectly matching interpreter would look like."""
    return {"python": {"version": manifest["python"]["version"], "implementation": "CPython", "executable": "/usr/bin/python"},
            "packages": dict(manifest["packages"]), "threadEnvironment": dict(manifest["threadEnvironment"]),
            "host": {"imageVersion": host.get("imageVersion", "20261004.327.1"), "cpuModel": host.get("cpuModel", "Fake CPU"), "cpuFlags": ["avx2"]},
            "blas": {"numpyShowConfig": None, "threadpool": [{"architecture": "Haswell", "internal_api": "openblas"}]}}


# --------------------------------------------------------------------------- #
# The manifest and the constraint file
# --------------------------------------------------------------------------- #
def test_manifest_parses_and_records_the_exact_formal_environment():
    m = FE.load_manifest(ROOT)
    assert m["python"]["version"] == "3.11.16" and m["python"]["implementation"] == "CPython"
    assert m["packages"] == FORMAL_PACKAGES and len(m["packages"]) == 47
    assert m["formalRun"]["runId"] == 37535814142 and m["formalRun"]["executionSha"] == A.FORMAL["executionSha"]
    assert m["formalRun"]["jobName"] == "execute"            # the job that computed the result, not the frozen-machine job
    assert m["threadEnvironment"] == {"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}
    assert m["host"]["imageVersion"] == "20260927.320.1" and m["host"]["cpuModel"] is None    # the formal log never recorded the CPU
    audit = m["firstPostOutcomeAudit"]
    assert audit["python"] == "3.11.17" and audit["numericalWheelFilesIdentical"] is True
    assert audit["packageDifferencesFromFormal"] == {"iniconfig": {"formal": "2.3.0", "firstAudit": "2.3.1"}, "peewee": {"formal": "4.5.2", "firstAudit": "4.5.3"},
                                                      "toolz": {"formal": "1.1.0", "firstAudit": "1.2.0"}}


def test_a_tampered_manifest_is_refused(tmp_path):
    for mutate, message in ((lambda m: m["packages"].__setitem__("numpy", "2.3.2"), "DIGEST_MISMATCH"),
                            (lambda m: m["python"].__setitem__("version", "3.11.17"), "DIGEST_MISMATCH")):
        copy_root = tmp_path / message
        (copy_root / "docs/results").mkdir(parents=True, exist_ok=True)
        m = json.loads((ROOT / FE.MANIFEST_PATH).read_text())
        mutate(m)
        (copy_root / FE.MANIFEST_PATH).write_text(json.dumps(m))
        with pytest.raises(ValueError, match=message):
            FE.load_manifest(copy_root)


def test_the_constraint_file_is_exactly_what_the_manifest_implies():
    m = FE.load_manifest(ROOT)
    text = (ROOT / FE.CONSTRAINTS_PATH).read_text()
    assert text == FE.constraints_text(m)
    pins = {line.split("==")[0]: line.split("==")[1] for line in text.splitlines() if line and not line.startswith("#")}
    assert pins == FORMAL_PACKAGES


def test_the_normal_requirements_agree_with_the_formal_environment_so_the_constraints_cannot_conflict():
    m = FE.load_manifest(ROOT)
    for line in (ROOT / "requirements.txt").read_text().splitlines() + (ROOT / "requirements-dev.txt").read_text().splitlines():
        if "==" in line and not line.startswith("#"):
            name, version = line.strip().split("==")
            assert m["packages"][FE.canonical_name(name)] == version, name


# --------------------------------------------------------------------------- #
# The preflight: pass, and fail BEFORE expensive work
# --------------------------------------------------------------------------- #
def test_a_matching_environment_passes_the_preflight():
    m = FE.load_manifest(ROOT)
    record = FE.parity_record(m, _exact(m), (ROOT / FE.CONSTRAINTS_PATH).read_text())
    assert record["ok"] is True and record["pythonEnvironment"]["classification"] == FE.PYTHON_EXACT and record["pythonEnvironment"]["failures"] == []


@pytest.mark.parametrize("mutate,fragment", [
    (lambda o: o["python"].__setitem__("version", "3.11.17"), "python: formal 3.11.16, observed 3.11.17"),
    (lambda o: o["python"].__setitem__("version", "3.12.0"), "python: formal 3.11.16, observed 3.12.0"),
    (lambda o: o["packages"].__setitem__("peewee", "4.5.3"), "package peewee: formal 4.5.2, observed 4.5.3"),
    (lambda o: o["packages"].__setitem__("numpy", "2.3.2"), "package numpy: formal 2.3.1, observed 2.3.2"),
    (lambda o: o["packages"].pop("scipy"), "package scipy: formal 1.16.0, observed NOT INSTALLED"),
    (lambda o: o["threadEnvironment"].__setitem__("OMP_NUM_THREADS", None), "OMP_NUM_THREADS: formal 1, observed None"),
    (lambda o: o["threadEnvironment"].__setitem__("OPENBLAS_NUM_THREADS", "4"), "OPENBLAS_NUM_THREADS: formal 1, observed 4"),
    (lambda o: o["threadEnvironment"].__setitem__("MKL_NUM_THREADS", ""), "MKL_NUM_THREADS: formal 1, observed "),
])
def test_any_python_environment_difference_fails_the_preflight_and_names_it(mutate, fragment):
    m = FE.load_manifest(ROOT)
    observed = _exact(m)
    mutate(observed)
    record = FE.parity_record(m, observed, (ROOT / FE.CONSTRAINTS_PATH).read_text())
    assert record["ok"] is False and record["pythonEnvironment"]["classification"] == FE.PYTHON_MISMATCH
    assert any(fragment in f for f in record["pythonEnvironment"]["failures"]), record["pythonEnvironment"]["failures"]


def test_a_constraint_file_that_drifted_from_the_manifest_fails_the_preflight():
    m = FE.load_manifest(ROOT)
    drifted = (ROOT / FE.CONSTRAINTS_PATH).read_text().replace("peewee==4.5.2", "peewee==4.5.3")
    record = FE.parity_record(m, _exact(m), drifted)
    assert record["ok"] is False and any("constraint file" in f for f in record["pythonEnvironment"]["failures"])


def test_the_cli_stops_with_a_nonzero_exit_and_writes_its_record_before_any_expensive_step(tmp_path, monkeypatch, capsys):
    m = FE.load_manifest(ROOT)
    bad = _exact(m)
    bad["python"]["version"] = "3.11.17"
    monkeypatch.setattr(FE, "observe_environment", lambda *a, **k: bad)
    out = tmp_path / "audit" / "environment-parity.json"
    assert CLI.main(["--output", str(out)]) == 1
    printed = capsys.readouterr().out
    assert "PYTHON_ENVIRONMENT_MISMATCH" in printed and FE.PARITY_FAILURE in printed
    record = json.loads(out.read_text())                       # the artifact says what this run actually looked like
    assert record["ok"] is False and record["observed"]["python"]["version"] == "3.11.17"
    assert not (tmp_path / "inputs").exists()                  # nothing was downloaded
    good = _exact(m)
    monkeypatch.setattr(FE, "observe_environment", lambda *a, **k: good)
    assert CLI.main(["--output", str(out)]) == 0
    assert json.loads(out.read_text())["pythonEnvironment"]["classification"] == FE.PYTHON_EXACT


# --------------------------------------------------------------------------- #
# The host is recorded and classified, and never gates
# --------------------------------------------------------------------------- #
def test_the_host_is_classified_honestly_and_never_blocks_the_audit():
    m = FE.load_manifest(ROOT)
    newer_image = FE.classify_host(m, _exact(m))                        # runner image 20261004 vs formal 20260927
    assert newer_image["classification"] == FE.HOST_DIFFERS and newer_image["blocksTheAudit"] is False
    same_image = FE.classify_host(m, _exact(m, imageVersion=m["host"]["imageVersion"]))
    assert same_image["classification"] == FE.HOST_UNVERIFIABLE        # equal image, but the formal CPU was never recorded
    assert any("CPU model was not recorded" in r for r in same_image["reasons"])
    assert FE.parity_record(m, _exact(m), (ROOT / FE.CONSTRAINTS_PATH).read_text())["ok"] is True      # a different host does not fail the Python gate
    known = copy.deepcopy(m)
    known["host"].update({"cpuModel": "Fake CPU", "openblasArchitecture": "Haswell"})
    assert FE.classify_host(known, _exact(known, imageVersion=known["host"]["imageVersion"]))["classification"] == FE.HOST_MATCH
    assert FE.classify_host(known, _exact(known, imageVersion=known["host"]["imageVersion"], cpuModel="Other CPU"))["classification"] == FE.HOST_DIFFERS


def test_observing_the_real_interpreter_never_raises_and_records_the_detail():
    observed = FE.observe_environment()
    assert observed["python"]["version"] and observed["packages"] and set(observed["threadEnvironment"]) == set(FE.THREAD_VARIABLES)
    record = FE.parity_record(FE.load_manifest(ROOT), observed)
    assert record["observed"]["pipFreeze"] and "blas" in record["observed"] and record["host"]["classification"] in (FE.HOST_MATCH, FE.HOST_DIFFERS, FE.HOST_UNVERIFIABLE)


# --------------------------------------------------------------------------- #
# Scientific rules, the sealed files and the formal workflow are untouched
# --------------------------------------------------------------------------- #
def test_the_reproduction_tolerance_is_still_exactly_1e_minus_9():
    assert A.FLOAT_TOLERANCE == 1e-9
    assert A._first_divergence({"v": 1.0}, {"v": 1.0 + 5e-10}, "v") is None
    assert A._first_divergence({"v": 1.0}, {"v": 1.0 + 2e-9}, "v") is not None
    assert A._first_divergence({"v": 0.10176568680470117}, {"v": 0.101765555609953}, "v") is not None      # the recovered 1.31e-7 gap still refuses


def test_the_sealed_formal_workflow_spec_and_result_are_byte_identical_to_the_seal():
    spec, sha = E.load_spec(ROOT)                                        # raises on ANY sealed dependency, workflow, receipt-schema or prior change
    assert sha == A.FORMAL["specSha256"] == "a8acb44c4b685e06ce7692e44461147110e2e2d32a119adef0dd216476f50e7f"
    workflow = ".github/workflows/kr-alpha-discovery-tournament-v1.yml"
    assert spec["dependencyHashes"][workflow] == hashlib.sha256(FORMAL_WORKFLOW.read_bytes()).hexdigest()
    assert hashlib.sha256(RESULT.read_bytes()).hexdigest() == A.FORMAL["resultSha256"] == "4a117ed23d30f9d716c87dbd987e1b80798484b0ab3558638379bf65cf9ccc5d"
    assert A.verify_sealed_result(ROOT)["verdict"]["verdict"] == "BLOCKED_BY_DATA_INTEGRITY"
    assert "constraints/" not in "".join(spec["dependencyHashes"]) and FE.MANIFEST_PATH not in spec["dependencyHashes"]     # the new files are audit-only


def test_the_new_modules_are_stdlib_only_and_cannot_reach_a_lock_the_network_or_a_subprocess():
    forbidden_imports = {"subprocess", "urllib", "requests", "socket", "http"}
    forbidden_words = ("execution-lock", "LockClaim", "authorize_execution", "write_marker", "load_market_values", "--mode execute")
    for path in (ROOT / "pipeline/kr_alpha_tournament_formal_environment.py", ROOT / "scripts/check_kr_alpha_tournament_formal_environment.py"):
        text = path.read_text()
        imported = set()
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.Import):
                imported |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert not (imported & forbidden_imports), (path.name, imported & forbidden_imports)
        assert not [w for w in forbidden_words if w in text], path.name


# --------------------------------------------------------------------------- #
# The audit workflow
# --------------------------------------------------------------------------- #
def _step_index(text, marker):
    assert text.count(marker) == 1, marker
    return text.index(marker)


def test_the_audit_workflow_pins_python_installs_the_constraints_and_runs_the_preflight_before_any_expensive_step():
    text = AUDIT_WORKFLOW.read_text()
    assert "python-version: '3.11.16'" in text and "python-version: '3.11'" not in text
    assert "cache: pip" not in text                                         # no stale wheel cache between the pins and the install
    assert "runs-on: ubuntu-24.04" in text and "ubuntu-latest" not in text
    assert "pip install -r requirements.txt -r requirements-dev.txt -c constraints/kr-alpha-discovery-tournament-v1-formal-env-37535814142.txt" in text
    install = _step_index(text, "- name: Install the normal requirements PLUS the audit-only constraints")
    preflight = _step_index(text, "- name: Environment parity preflight")
    download = _step_index(text, "- name: Download the exact preserved raw snapshot")
    reconstruct = _step_index(text, "- name: Model-free scan and read-only reconstruction")
    assert install < preflight < download < reconstruct
    body = text[preflight:download]
    assert "check_kr_alpha_tournament_formal_environment.py --output audit/environment-parity.json" in body and "set -euo pipefail" in body
    assert "continue-on-error" not in body and not re.search(r"^\s+if:", body, re.M)     # a failed preflight cannot be skipped over
    assert "audit/environment-parity.json" in text[text.index("Print the audit files"):]                   # and the record is printed and uploaded either way
    for var in ("OMP_NUM_THREADS: '1'", "OPENBLAS_NUM_THREADS: '1'", "MKL_NUM_THREADS: '1'"):
        assert var in text


def test_the_audit_workflow_is_still_manual_read_only_and_never_executes_or_writes():
    text = AUDIT_WORKFLOW.read_text()
    header = "\n".join(line for line in text[:text.index("\njobs:")].splitlines() if not line.lstrip().startswith("#"))      # prose comments name the forbidden triggers
    assert "workflow_dispatch:" in header and "schedule:" not in header and "pull_request" not in header and "\n  push:" not in header
    assert "contents: read" in header and "actions: read" in header and "write" not in header.split("permissions:")[1].split("concurrency:")[0]
    assert "--mode execute" not in text and "git push" not in text and "git tag" not in text and "refs/tags" in text            # lock refs are only read
    assert "'.github/workflows/kr-alpha-discovery-tournament-v1.yml'" in text      # an audit_ref with an edited formal workflow is refused


def test_the_formal_workflow_is_unchanged_and_still_has_one_execute_and_the_same_python_request():
    text = FORMAL_WORKFLOW.read_text()
    assert text.count("--mode execute") == 1 and "python-version: '3.11'" in text and "constraints/" not in text and "environment-parity" not in text


# --------------------------------------------------------------------------- #
# A mismatch still blocks attribution; an exact reproduction still allows it
# --------------------------------------------------------------------------- #
def test_only_the_exact_registered_success_status_allows_attribution():
    assert A.reproduction_allows_attribution({"status": "RECONSTRUCTION_REPRODUCES_THE_SEALED_RESULT", "firstDivergence": None}) is True
    assert A.reproduction_allows_attribution({"status": "RECONSTRUCTION_MISMATCH", "firstDivergence": "x"}) is False
    assert A.reproduction_allows_attribution({"status": "RECONSTRUCTION_MISMATCH", "firstDivergence": None}) is False
    assert A.reproduction_allows_attribution({"status": "RECONSTRUCTION_REPRODUCES_THE_SEALED_RESULT", "firstDivergence": "x"}) is False
    assert A.reproduction_allows_attribution({}) is False and A.reproduction_allows_attribution(None) is False
    sealed = json.loads(RESULT.read_text())
    same = copy.deepcopy(sealed)
    same["counters"]["markerWrites"] = 0
    assert A.reproduction_allows_attribution(A.reproduction_check(same, sealed)) is True
    moved = copy.deepcopy(sealed)
    moved["paths"]["PRIMARY_ROBUST_KELLY:COST_X2"]["annualLogGrowth"] += 1.3e-7
    assert A.reproduction_allows_attribution(A.reproduction_check(moved, sealed)) is False


ATTRIBUTION_CALLS = {"gap_events", "terminal_window", "terminal_foundation", "failure_report", "exposure_table", "cost_x2_explanation"}


def test_every_attribution_call_in_reconstruct_sits_behind_the_gate_and_the_success_path_still_has_them():
    tree = ast.parse((ROOT / "pipeline/kr_alpha_tournament_postoutcome_integrity_audit.py").read_text())
    reconstruct = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "reconstruct")
    guard = next(i for i, stmt in enumerate(reconstruct.body) if isinstance(stmt, ast.If) and "reproduction_allows_attribution" in ast.dump(stmt.test)
                 and isinstance(stmt.body[-1], ast.Return))
    before = {n.func.id for stmt in reconstruct.body[:guard + 1] for n in ast.walk(stmt) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    after = {n.func.id for stmt in reconstruct.body[guard + 1:] for n in ast.walk(stmt) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert not (before & ATTRIBUTION_CALLS)                                  # no attribution can run before the gate has returned
    assert ATTRIBUTION_CALLS <= after                                        # an exact reproduction still reaches the registered forensic sections
    assert "reproduction_diagnostics" in ast.dump(reconstruct.body[guard])   # and the refusal branch records HOW it failed


FORBIDDEN_ATTRIBUTION_KEYS = {"firstFailures", "pathsWithoutFailure", "modelFreeScan", "terminalExposure", "costX2", "tradeCounts", "ticker", "heldWeight", "terminalWindows"}


def _walk_keys(x):
    if isinstance(x, dict):
        for k, v in x.items():
            yield k
            yield from _walk_keys(v)
    elif isinstance(x, list):
        for v in x:
            yield from _walk_keys(v)


def test_diagnostics_describe_how_a_reproduction_failed_without_attributing_anything():
    sealed = json.loads(RESULT.read_text())
    rec = copy.deepcopy(sealed)
    rec["counters"]["markerWrites"] = 1
    rec["paths"]["PRIMARY_ROBUST_KELLY:COST_X2"]["annualLogGrowth"] = 0.10176568680470117       # the recovered divergence
    gate = A.reproduction_check(rec, sealed)
    assert set(gate) == {"status", "firstDivergence"} and gate["status"] == "RECONSTRUCTION_MISMATCH"       # the gate itself is unchanged
    d = A.reproduction_diagnostics(rec, sealed, {"stub": True})
    assert d["diagnosticOnly"] and d["noFailureAttribution"] and d["tolerance"] == {"relTol": 1e-9, "absTol": 1e-9}
    assert d["firstDivergence"] == gate["firstDivergence"]
    pair = d["firstDivergentNumericPair"]
    assert pair["reconstructed"] == 0.10176568680470117 and pair["sealed"] == 0.101765555609953
    assert pair["absoluteDifference"] == pytest.approx(1.3119474817635535e-07) and pair["relativeDifference"] == pytest.approx(1.289186182790556e-06)
    for key in ("completePathFlags", "outerFoldStates", "selectedEnsembleIdsByYear", "counters", "processStructure"):
        assert d[key]["matched"] is True, key
    before, everywhere = d["maxNumericalDifference"]["beforeTheRefusalPoint"], d["maxNumericalDifference"]["acrossAllRegisteredFields"]
    assert before["maxAbsoluteDifference"] == 0.0 and before["fieldsBeyondTolerance"] == 0 and before["numericFieldsCompared"] > 0
    assert everywhere["fieldsBeyondTolerance"] == 1 and everywhere["maxAbsoluteDifference"] == pytest.approx(1.3119474817635535e-07)
    assert d["perRegisteredKey"]["paths"]["matched"] is False and d["perRegisteredKey"]["process"]["matched"] is True
    assert d["environment"] == {"stub": True}
    assert not (set(_walk_keys(d)) & FORBIDDEN_ATTRIBUTION_KEYS)
    json.dumps(d)                                                              # and it serialises


def test_diagnostics_report_each_kind_of_difference_separately():
    sealed = json.loads(RESULT.read_text())
    base = copy.deepcopy(sealed)
    base["counters"]["markerWrites"] = 1
    flags = copy.deepcopy(base)
    flags["complete"]["PRIMARY_ROBUST_KELLY:BASE"] = True
    d = A.reproduction_diagnostics(flags, sealed)
    assert d["completePathFlags"] == {"matched": False, "differingPathKeys": ["PRIMARY_ROBUST_KELLY:BASE"]} and d["firstDivergence"].startswith("complete/")
    states = copy.deepcopy(base)
    states["process"]["folds"][1]["state"] = "PASSIVE_DEFAULT_NO_STABLE_CANDIDATE"
    d = A.reproduction_diagnostics(states, sealed)
    assert d["outerFoldStates"] == {"matched": False, "differingYears": [2019]} and d["completePathFlags"]["matched"] is True
    ensemble = copy.deepcopy(base)
    ensemble["process"]["folds"][2]["ensemble"] = ensemble["process"]["folds"][2]["ensemble"][:-1]
    d = A.reproduction_diagnostics(ensemble, sealed)
    assert d["selectedEnsembleIdsByYear"] == {"matched": False, "differingYears": [2020]} and d["processStructure"]["matched"] is False
    counters = copy.deepcopy(base)
    counters["counters"]["modelFits"] += 1
    d = A.reproduction_diagnostics(counters, sealed)
    assert d["counters"]["matched"] is False and d["counters"]["differing"] == ["modelFits"]
    exact = A.reproduction_diagnostics(base, sealed)
    assert exact["firstDivergence"] is None and exact["maxNumericalDifference"]["acrossAllRegisteredFields"]["fieldsBeyondTolerance"] == 0
