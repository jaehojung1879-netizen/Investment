"""Operational CI evolution must preserve historical and scientific identities."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from pipeline.kr_alpha_atlas_phase_c import contract as C

ROOT = Path(__file__).resolve().parents[1]
POLICY = "docs/ci/historical-workflow-provenance-v1.json"
WORKFLOW = ".github/workflows/tests.yml"
VALIDATOR = "pipeline/kr_alpha_atlas_phase_c/contract.py"
REGISTRATION = "8c3611116c5103a1e860173b180d0094e45b3074"


@pytest.fixture(scope="module")
def identities():
    return C.load(), C.build()


@pytest.fixture
def scratch(tmp_path, identities):
    # Read-only Git queries use the real object store; mutations affect only
    # these temporary copies, never sealed repository files.
    (tmp_path / ".git").symlink_to(ROOT / ".git", target_is_directory=True)
    for rel in (C.SPEC, C.SIDECAR, POLICY, VALIDATOR):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / rel).read_bytes())
    return tmp_path, deepcopy(identities[0]), deepcopy(identities[1])


def write_policy(root, change):
    policy = json.loads((root / POLICY).read_text())
    change(policy)
    (root / POLICY).write_text(json.dumps(policy))


def test_all_original_registered_dependencies_remain_verifiable(identities):
    spec, _ = identities
    raw = subprocess.check_output(["git", "show", REGISTRATION + ":" + C.SPEC], cwd=ROOT)
    assert raw == (ROOT / C.SPEC).read_bytes()
    for path, sha in spec["dependencyHashes"].items():
        blob = subprocess.check_output(["git", "show", REGISTRATION + ":" + path], cwd=ROOT)
        assert hashlib.sha256(blob).hexdigest() == sha, path
        if path not in (WORKFLOW, VALIDATOR):
            assert C.file_hash(ROOT / path) == sha, path


def test_operational_budget_is_60_and_all_existing_gates_are_identical():
    old = subprocess.check_output(["git", "show", REGISTRATION + ":" + WORKFLOW], cwd=ROOT)
    assert old.count(b"timeout-minutes: 30") == 1
    assert (ROOT / WORKFLOW).read_bytes() == old.replace(b"timeout-minutes: 30", b"timeout-minutes: 60", 1)
    assert b"run: python -m pytest -q\n" in old
    assert b"fetch-depth: 0" in old


def test_comparison_changes_only_two_identities_and_never_the_spec(identities):
    spec, current = map(deepcopy, identities)
    before = C.canonical(spec)
    changed = {p for p in spec["dependencyHashes"] if spec["dependencyHashes"][p] != current["dependencyHashes"][p]}
    assert changed == {WORKFLOW, VALIDATOR}
    assert C.historical_ci_dependencies(spec, current, ROOT) == spec
    assert C.canonical(spec) == before
    assert C.digest(spec["dependencyHashes"]) == "5e71455a3f01c1796ac99d5e7b66b30baa7c2982c62cb5ea1013201892f91820"


def test_future_operational_workflow_hash_does_not_reseal_research(scratch):
    root, spec, current = scratch
    current["dependencyHashes"][WORKFLOW] = "a" * 64
    assert C.historical_ci_dependencies(spec, current, root) == spec


@pytest.mark.parametrize("mutation", [
    lambda p: p.update(version=2),
    lambda p: p.update(version=True),
    lambda p: p.update(schema="UNSUPPORTED"),
    lambda p: p.update(registrationCommit="0" * 40),
    lambda p: p.update(specSha256="0" * 64),
    lambda p: p.update(unregisteredOverride=True),
    lambda p: p["historicalDependencies"].update({"pipeline/kr_alpha_atlas_phase_c/models.py": "0" * 64}),
])
def test_policy_cannot_expand_scope_or_change_registration(scratch, mutation):
    root, spec, current = scratch
    write_policy(root, mutation)
    with pytest.raises(ValueError, match="UNSUPPORTED_CI_PROVENANCE"):
        C.historical_ci_dependencies(spec, current, root)


def test_historical_workflow_hash_is_verified_against_git(scratch):
    root, spec, current = scratch
    write_policy(root, lambda p: p["historicalDependencies"].update({WORKFLOW: "0" * 64}))
    with pytest.raises(ValueError, match="HISTORICAL_CI_DEPENDENCY_CHANGED"):
        C.historical_ci_dependencies(spec, current, root)


@pytest.mark.parametrize("path", [C.SPEC, C.SIDECAR, VALIDATOR])
def test_current_registration_sidecar_and_adapter_mutation_refused(scratch, path):
    root, spec, current = scratch
    with (root / path).open("ab") as stream:
        stream.write(b"\n# changed\n")
    with pytest.raises(ValueError, match="MUTATED|VALIDATOR_CHANGED"):
        C.historical_ci_dependencies(spec, current, root)


@pytest.mark.parametrize("failure", ["missing", "corrupt", "unrelated"])
def test_unavailable_corrupt_or_unrelated_git_history_fails_closed(scratch, monkeypatch, failure):
    root, spec, current = scratch
    show, run = subprocess.check_output, subprocess.run

    def git_show(args, **kwargs):
        if args[-1] == REGISTRATION + ":" + WORKFLOW:
            if failure == "missing":
                raise subprocess.CalledProcessError(128, args)
            if failure == "corrupt":
                return b"wrong historical workflow"
        return show(args, **kwargs)

    def git_run(args, **kwargs):
        if failure == "unrelated" and args[:2] == ["git", "merge-base"]:
            raise subprocess.CalledProcessError(1, args)
        return run(args, **kwargs)

    monkeypatch.setattr(subprocess, "check_output", git_show)
    monkeypatch.setattr(subprocess, "run", git_run)
    with pytest.raises(ValueError, match="GIT_OBJECT_UNAVAILABLE|DEPENDENCY_CHANGED|NOT_ANCESTOR"):
        C.historical_ci_dependencies(spec, current, root)


@pytest.mark.parametrize("area", ["scientific-code", "formal-workflow", "protected-result", "formula", "closure"])
def test_compatibility_never_accepts_scientific_or_protected_changes(scratch, monkeypatch, area):
    root, spec, current = scratch
    if area == "scientific-code":
        current["dependencyHashes"]["pipeline/kr_alpha_atlas_phase_c/models.py"] = "0" * 64
    elif area == "formal-workflow":
        current["dependencyHashes"][C.WORKFLOW] = "0" * 64
    elif area == "protected-result":
        current["protectedHashes"][next(iter(current["protectedHashes"]))] = "0" * 64
    elif area == "formula":
        current["linearModel"]["penalty"] = 0.5
    else:
        current["dependencyHashes"]["pipeline/unregistered_scientific_code.py"] = "0" * 64
    monkeypatch.setattr(C, "build", lambda _: current)
    with pytest.raises(ValueError, match="INCOMPLETE_MUTATED"):
        C.validate(spec, root)


def test_missing_compatibility_record_fails_closed(scratch):
    root, spec, current = scratch
    (root / POLICY).unlink()
    with pytest.raises(FileNotFoundError):
        C.historical_ci_dependencies(spec, current, root)
