"""Closed provenance verifies identities while every execution path stays closed."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from pipeline import closed_atlas_provenance as P
from pipeline import pages_operational_maintenance as M

ROOT = Path(__file__).resolve().parents[1]


class ReadOnly:
    def __init__(self):
        self.calls = []
        meta = json.loads((ROOT / P.EVIDENCE).read_text())
        self.locks = [{'ref': ref, 'object': {'type': 'commit', 'sha': P.CONSUMED}} for ref in meta['lockRefs']]
        self.main = M.MAIN

    def get(self, path):
        self.calls.append(path)
        if path == 'git/ref/heads/main':
            return {'object': {'sha': self.main}}
        assert path == 'git/matching-refs/tags/' + P.LOCK.removeprefix('refs/tags/')
        return deepcopy(self.locks)


def test_real_registered_bytes_and_consumed_lock_fixture_never_enable_execution():
    github = ReadOnly()
    out = P.inspect(ROOT, expected_main=M.MAIN, github=github)
    assert out['status'] == 'CLOSED_STUDY_HISTORICAL_PROVENANCE_VERIFIED'
    assert out['operationalMaintenanceVersion'] == 2
    assert out['operationalMaintenanceRecordSha256'] == M.sha((ROOT / M.RECORD).read_bytes())
    assert out['permanentlyConsumed'] and not out['authorizationUsableForNewExecution']
    assert out['registeredDependenciesVerified'] == 158 and out['protectedFilesVerified'] == 235
    assert out['historicalResult'] == 'ABSENT_IN_REFERENCE_GIT_NO_SUCCESS_CLAIM'
    assert out['externalOutcomeArtifacts'] == 'NOT_FETCHED_OR_EVALUATED'
    assert out['newExecutionPreflight'] == 'NOT_RUN' and not out['formalExecutionAuthorized']
    assert not any(out['counters'].values()) and len(github.calls) == 2


@pytest.mark.parametrize('mutation', [
    lambda api: api.locks.clear(),
    lambda api: api.locks.pop(),
    lambda api: api.locks.append(deepcopy(api.locks[0])),
    lambda api: api.locks[0]['object'].update(sha='0' * 40),
    lambda api: api.locks[0]['object'].update(type='tag'),
    lambda api: api.locks[0].update(ref=P.LOCK + '-unrelated'),
])
def test_missing_changed_duplicate_or_other_locks_are_not_unconsumed(mutation):
    api = ReadOnly()
    mutation(api)
    with pytest.raises(ValueError, match='CONSUMED_LOCK_MISSING_CHANGED_OR_UNEXPECTED'):
        P.inspect(ROOT, expected_main=M.MAIN, github=api)


def test_stale_expected_main_and_api_errors_fail_closed():
    api = ReadOnly()
    api.main = '0' * 40
    with pytest.raises(ValueError, match='PROVENANCE_MAIN_MOVED_OR_STALE_EXPECTATION'):
        P.inspect(ROOT, expected_main=M.MAIN, github=api)

    def refused(path):
        raise ValueError('PROVENANCE_GITHUB_READ_REFUSED')

    api.get = refused
    with pytest.raises(ValueError, match='PROVENANCE_GITHUB_READ_REFUSED'):
        P.inspect(ROOT, expected_main=M.MAIN, github=api)


@pytest.mark.parametrize('path', ['pipeline/kr_alpha_atlas_phase_c/models.py',
                                  'docs/results/kr-alpha-atlas-phase-b-readiness.json'])
def test_changed_science_or_protected_bytes_are_rejected_before_network(path, monkeypatch):
    actual = P.file_hash
    monkeypatch.setattr(P, 'file_hash', lambda root, name: '0' * 64 if name == path else actual(root, name))
    api = ReadOnly()
    with pytest.raises(ValueError, match='SCIENTIFIC_DEPENDENCY_CHANGED|PROTECTED_RESEARCH_BYTES_CHANGED'):
        P.inspect(ROOT, expected_main=M.MAIN, github=api)
    assert not api.calls


def test_read_client_cannot_access_writing_or_unrelated_endpoints(monkeypatch):
    monkeypatch.setattr(P.subprocess, 'run', lambda *a, **k: pytest.fail('No subprocess permitted'))
    for path in ('git/refs', 'actions/workflows/pages.yml/dispatches', 'actions/runs/1/rerun', 'git/ref/heads/signal-history'):
        with pytest.raises(ValueError, match='PROVENANCE_READ_ENDPOINT_REQUIRED'):
            P.ReadOnlyGitHub().get(path)


def test_module_has_no_numerical_or_scientific_imports_in_a_fresh_process():
    code = "from pipeline.closed_atlas_provenance import inspect; import sys; assert not any(k.split('.')[0] in {'numpy','pandas','sklearn'} for k in sys.modules)"
    subprocess.run([sys.executable, '-c', code], cwd=ROOT, check=True)


@pytest.mark.parametrize('expected', ['', 'main', '0' * 39, None])
def test_immutable_main_identity_required(expected):
    with pytest.raises(ValueError, match='IMMUTABLE_EXPECTED_MAIN_REQUIRED'):
        P.inspect(ROOT, expected_main=expected, github=ReadOnly())
