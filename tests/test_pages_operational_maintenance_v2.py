"""Approved maintenance cannot become an arbitrary hash override."""
from copy import deepcopy
import importlib.metadata
import json
from pathlib import Path

import pytest

from pipeline import pages_operational_maintenance as M

ROOT = Path(__file__).resolve().parents[1]
RECORD_SHA256 = 'e849e42235e6e38cf2dd141504daecc4e118392af0bccc855e56f1a304d7a082'


@pytest.fixture
def scratch(tmp_path):
    (tmp_path / '.git').symlink_to(ROOT / '.git')
    paths = {M.RECORD, M.SIDECAR, M.PREVIOUS, M.PREVIOUS.replace('.json', '.sha256'),
             M.PAGES, M.TESTS, M.VERIFIER, M.WORKFLOW_TEST,
             'research_specs/kr-alpha-atlas-phase-c-v4-reproducibility.json',
             'research_specs/kr-alpha-atlas-phase-c-v4-reproducibility.sha256'} | M.AUXILIARY
    for path in paths:
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / path).read_bytes())
    return tmp_path


def resign(root, mutate):
    doc = json.loads((root / M.RECORD).read_text())
    mutate(doc)
    raw = json.dumps(doc).encode()
    (root / M.RECORD).write_bytes(raw)
    (root / M.SIDECAR).write_text(M.sha(raw) + '\n')


def test_record_is_exact_and_original_state_only_record_is_preserved():
    assert M.sha((ROOT / M.RECORD).read_bytes()) == RECORD_SHA256
    assert M.sha((ROOT / M.PREVIOUS).read_bytes()) == M.PREVIOUS_SHA
    assert M.validate(ROOT)


@pytest.mark.parametrize('field,value', [
    ('version', True), ('version', 3), ('scope', 'ANY_WORKFLOW'),
    ('formalExecutionAuthorized', True), ('referenceMain', '0' * 40),
    ('parentMaintenanceCommit', '0' * 40), ('unexpected', True),
])
def test_resigned_record_cannot_expand_authorization(scratch, field, value):
    resign(scratch, lambda r: r.update({field: value}))
    with pytest.raises(ValueError, match='PAGES_MAINTENANCE_CONTRACT_CHANGED'):
        M.validate(scratch)


@pytest.mark.parametrize('path', sorted(M.AUXILIARY | {M.VERIFIER, M.PAGES, M.TESTS, M.WORKFLOW_TEST, M.PREVIOUS}))
def test_every_current_dependency_is_pinned(scratch, path):
    with (scratch / path).open('ab') as stream:
        stream.write(b'\n# corrupted\n')
    with pytest.raises((ValueError, json.JSONDecodeError)):
        M.validate(scratch)


@pytest.mark.parametrize('old,new', [
    (b'contents: read', b'contents: write'),
    (b'python-version: \'3.11.16\'', b'python-version: \'3.11.17\''),
    (b' execute --work ', b' validate --work '),
    (b'branches: [main]', b'branches: [main, unsafe]'),
])
def test_resigning_pages_cannot_change_permissions_runtime_formal_or_triggers(scratch, old, new):
    path = scratch / M.PAGES
    raw = path.read_bytes()
    assert old in raw
    raw = raw.replace(old, new, 1)
    path.write_bytes(raw)
    resign(scratch, lambda r: r.update(replacementPagesSha256=M.sha(raw)))
    with pytest.raises(ValueError, match='PAGES_MAINTENANCE_CONTRACT_CHANGED'):
        M.validate(scratch)


def test_resigning_tests_cannot_skip_the_suite(scratch):
    path = scratch / M.TESTS
    raw = path.read_bytes().replace(b'python -m pytest -q\n', b'python -m pytest -q -k safe\n')
    path.write_bytes(raw)
    resign(scratch, lambda r: r.update(replacementTestsSha256=M.sha(raw)))
    with pytest.raises(ValueError, match='PAGES_MAINTENANCE_CONTRACT_CHANGED'):
        M.validate(scratch)


def test_resigning_verifier_cannot_change_scientific_prepare(scratch):
    path = scratch / M.VERIFIER
    raw = path.read_bytes().replace(b'NR.verify(spec)  # Cheap', b'pass  # Cheap')
    path.write_bytes(raw)
    resign(scratch, lambda r: r.update(replacementVerifierSha256=M.sha(raw)))
    with pytest.raises(ValueError, match='PAGES_MAINTENANCE_CONTRACT_CHANGED'):
        M.validate(scratch)


def test_resigning_workflow_assertion_cannot_change_numeric_error_expectations(scratch):
    path = scratch / M.WORKFLOW_TEST
    raw = path.read_bytes().replace(b'SINGLE_THREAD_ENVIRONMENT_REQUIRED', b'IGNORED_DEPENDENCY_ERROR')
    path.write_bytes(raw)
    resign(scratch, lambda r: r.update(replacementWorkflowTestSha256=M.sha(raw)))
    with pytest.raises(ValueError, match='PAGES_MAINTENANCE_CONTRACT_CHANGED'):
        M.validate(scratch)


def test_constraints_match_original_registration_and_installed_numeric_extras():
    spec = json.loads((ROOT / 'research_specs/kr-alpha-atlas-phase-c-v1.json').read_text())
    expected = spec['runtime']['numericalExtras']
    assert expected == {'threadpoolctl': '3.7.0', 'joblib': '1.6.0'}
    pins = dict(line.split('==') for line in (ROOT / M.CONSTRAINTS).read_text().splitlines()
                if line and not line.startswith('#'))
    assert pins == expected
    assert {name: importlib.metadata.version(name) for name in pins} == pins


def test_local_git_helper_has_no_write_or_fetch_operation():
    for operation in ('push', 'fetch', 'update-ref', 'commit', 'reset'):
        with pytest.raises(ValueError, match='PAGES_MAINTENANCE_CONTRACT_CHANGED'):
            M.git(ROOT, operation)


def test_auxiliary_scope_cannot_expand_even_with_resigned_record(scratch):
    def expand(record):
        record['auxiliaryHashes'] = deepcopy(record['auxiliaryHashes'])
        record['auxiliaryHashes']['pipeline/kr_alpha_atlas_phase_c/models.py'] = '0' * 64
    resign(scratch, expand)
    with pytest.raises(ValueError, match='PAGES_MAINTENANCE_CONTRACT_CHANGED'):
        M.validate(scratch)
