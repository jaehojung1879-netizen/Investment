"""Outcome-free contract checks and invented OHLC kernel reproducibility."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import pytest

from pipeline import kr_alpha_atlas_reproducibility as V4
from pipeline import kr_alpha_atlas_mirae_repair as R
from pipeline import kr_alpha_atlas_numeric_runtime as NR
from pipeline.kr_alpha_atlas_phase_c import contract

ROOT = contract.ROOT


def test_preserved_versions_sources_and_scientific_choices():
    parent, child = R.load(), V4.load()
    allowed = {'version', 'registrationAmendmentId', 'runtime', 'lifecycle',
               'phaseBIdentity', 'dependencyHashes', 'numericalReproducibilityAddendum'}
    assert {k: v for k, v in parent.items() if k not in allowed} == {k: v for k, v in child.items() if k not in allowed}
    assert child['phaseBIdentity']['inputs'] == parent['phaseBIdentity']['inputs']
    assert child['phaseBIdentity']['matrixDigest'] != parent['phaseBIdentity']['matrixDigest']
    assert parent['phaseBIdentity']['matrixDigest'] == 'c3d66a99f1e1a1c525a9a659b0bee3cc1bf04109796234b310f0513b222187e7'
    assert child['lifecycle'] == {**parent['lifecycle'], 'authorizationPath': V4.AUTHORIZATION}
    assert child['runtime'] == {**parent['runtime'], 'environment': {**parent['runtime']['environment'], **NR.ENVIRONMENT}}
    assert child['benchmarkIntegrity'] == parent['benchmarkIntegrity']
    assert child['targets'] == parent['targets']
    paths = [V4.AUTHORIZATION, R.AUTHORIZATION, R.V2.load()['lifecycle']['authorizationPath'], contract.load()['lifecycle']['authorizationPath']]
    assert len(set(paths)) == 4  # Real absence is audited; CI must allow later owner approval.
    assert contract.file_hash(ROOT/R.ADDENDUM) == V4.PARENT_SHA


def test_scoped_reuse_restores_every_parent_binding():
    before = {k: getattr(R, k) for k in V4._PARENT}
    with V4.bindings():
        assert R.load is V4.load and R.prepare is V4.prepare
        assert V4.parent_load(ROOT)['version'] == 3
        assert R.load(ROOT)['version'] == 4
    assert {k: getattr(R, k) for k in before} == before


def test_unsupported_amendment_header_is_rejected():
    original = json.loads

    def mutated(raw, *args, **kwargs):
        doc = original(raw, *args, **kwargs)
        if isinstance(doc, dict) and doc.get('schema') == 'KR_ALPHA_ATLAS_PRE_OUTCOME_NUMERICAL_ADDENDUM_V1':
            doc['version'] = 5
        return doc

    with patch.object(V4.json, 'loads', mutated):
        with pytest.raises(ValueError, match='SUPPORTED_EXACT_V4_ADDENDUM_REQUIRED'):
            V4.load()


def test_no_approval_cannot_reach_prepare_or_global_lock(tmp_path):
    class FakeGitHub:
        def main(self):
            return 'SYN_HEAD'

        def claim(self, *args):
            raise AssertionError('LOCK_MUST_NOT_BE_REACHED')

    def git_output(args, **kwargs):
        if args == ['git', 'rev-parse', 'HEAD']:
            return b'SYN_HEAD\n'
        if args == ['git', 'status', '--porcelain', '--untracked-files=no']:
            return b''
        raise AssertionError(args)

    exists = Path.exists

    def no_approval(path):
        return False if str(path).endswith('-execution-authorization.json') else exists(path)

    with patch.object(Path, 'exists', no_approval), patch.object(R.subprocess, 'check_output', git_output), patch.object(V4, 'prepare', side_effect=AssertionError('PREPARE_MUST_NOT_BE_REACHED')):
        with pytest.raises(ValueError, match='EXPLICIT_HUMAN_SOURCE_REPAIR_AUTHORIZATION_ABSENT'):
            V4.formal(work=tmp_path/'SYN_ONLY', github=FakeGitHub())
    assert not list(tmp_path.iterdir())


def test_bootstrap_rejects_late_numpy_import():
    with pytest.raises(RuntimeError, match='BEFORE_NUMPY_IMPORT'):
        NR.bootstrap()


def test_synthetic_ohlc_kernel_is_exact_across_hash_seeds():
    code = """
import hashlib,json
import numpy as np,pandas as pd
from pipeline.kr_alpha_atlas_bars import corwin_schultz
n=np.arange(20000,dtype=np.int64)
low=pd.Series(100.+(n*17%1000)*.125)
high=low+pd.Series(1.+(n*23%97)*.125)
s=corwin_schultz(high,low)
a=[None if not np.isfinite(v) else float(f'{v:.12g}') for v in s]
print(hashlib.sha256(json.dumps(a).encode()).hexdigest())
"""
    out = []
    for seed in ('1', '42', '314159'):
        env = {**os.environ, **NR.ENVIRONMENT, 'PYTHONHASHSEED': seed,
               'OPENBLAS_NUM_THREADS': '1', 'OMP_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1'}
        out.append(subprocess.check_output([sys.executable, '-c', code], cwd=ROOT, env=env, timeout=30).decode().strip())
    assert out == ['87ac737d35d8b31072e70e20407b108242fc43206bd99e66d363dfbfe2fd717e']*3


def test_runtime_restriction_and_cli_bootstrap_order():
    text = (ROOT/'scripts/run_kr_alpha_atlas_phase_c_reproducible.py').read_text()
    assert text.index('bootstrap()') < text.index('import kr_alpha_atlas_reproducibility')
    spec = V4.load()
    assert spec['runtime']['environment']['OPENBLAS_CORETYPE'] == 'Haswell'
    fake = deepcopy(spec)
    fake['runtime']['environment']['OPENBLAS_CORETYPE'] = 'Unsupported'
    with pytest.raises(ValueError, match='SINGLE_THREAD_ENVIRONMENT_REQUIRED'):
        NR.verify(fake)


def test_wrong_cpu_is_refused_before_the_parent_input_path(tmp_path):
    from pipeline.kr_alpha_atlas_phase_c import preflight
    from numpy._core import _multiarray_umath
    cpu = {**_multiarray_umath.__cpu_features__, 'AVX2': False}
    with patch.object(preflight, 'verify_runtime', return_value={'scope': 'SYN'}), patch.object(_multiarray_umath, '__cpu_features__', cpu), patch.dict(V4._PARENT, {'prepare': lambda *a, **k: pytest.fail('input acquisition must not run')}):
        with pytest.raises(ValueError, match='REGISTERED_AVX2_WITHOUT_AVX512_DISPATCH_REQUIRED'):
            V4.prepare(ROOT, {}, tmp_path/'SYN')
    assert not list(tmp_path.iterdir())


def test_workflow_separates_pr_preflight_owner_execution_and_pages():
    text = (ROOT/'.github/workflows/pages.yml').read_text()
    safe = text.split('  matrix-diagnostic:', 1)[1].split('  matrix-formal-owner-only:', 1)[0]
    formal = text.split('  matrix-formal-owner-only:', 1)[1].split('  build-and-deploy:', 1)[0]
    assert 'contents: read' in safe and 'contents: write' not in safe
    assert ' preflight ' in safe and ' execute ' not in safe
    assert "github.event_name == 'workflow_dispatch'" in formal
    assert "github.ref == 'refs/heads/main'" in formal
    assert "github.actor == 'jaehojung1879-netizen'" in formal
    assert 'kr-alpha-atlas-phase-c-v1-single-attempt' in text
    assert 'kr-alpha-atlas-phase-c-v1-results-' in formal
    assert 'execute' not in safe


def test_captured_failure_was_not_silenced():
    evidence = json.loads((ROOT/V4.BASE/'root-cause.json').read_text())
    assert evidence['originalFailure']['actualMatrixDigest'] is None
    assert evidence['originalFailure']['uploadedArtifacts'] == 0
    assert evidence['barIsolation']['changedCanonicalCells'] == 37
    assert evidence['barIsolation']['onlyChangedFeature'] == 'E05_highLowSpreadProxy'
    assert evidence['barIsolation']['sourceBitsIdentical'] is True
    assert all(v == 0 for v in evidence['counters'].values())
    assert hashlib.sha256((ROOT/V4.ADDENDUM).read_bytes()).hexdigest() == (ROOT/V4.SIDECAR).read_text().strip()
