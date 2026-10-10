"""Invented cells only; observer cannot suppress the production digest gate."""
import json
from unittest.mock import patch
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from pipeline import kr_alpha_atlas_matrix as MX
from pipeline import kr_alpha_atlas_matrix_diagnostics as D
from pipeline.kr_alpha_atlas_phase_c import preflight


def invented():
    rows = pd.DataFrame({'date': ['2020-01-03']*2, 'pitSnapshotDate': ['2020-01-02']*2, 'ticker': ['SYN2', 'SYN1'],
                         'industry': ['SYN', 'SYN'], 'liquidityTier': ['LOW', 'HIGH']})
    values = pd.DataFrame({'A01_return1d': [np.nan, .1]})
    reasons = pd.DataFrame({'A01_return1d': ['NO_PRICE_PANEL', '']})
    return MX.Matrix(rows, values, reasons, pd.DataFrame(index=rows.index), pd.DataFrame(), {'scope': 'SYN'})


def test_observer_preserves_identical_object_and_failed_gate_artifact(tmp_path):
    matrix = invented()
    with patch.object(MX, 'build_matrix', return_value=matrix), D.observe('deliberate-mismatch', tmp_path):
        with pytest.raises(ValueError, match='PHASE_B_MATRIX_DIGEST_CHANGED'):
            actual = MX.build_matrix(None, [])
            assert actual is matrix
            if actual.digest() != 'deliberate-mismatch':
                raise ValueError('PHASE_B_MATRIX_DIGEST_CHANGED')
    doc = json.loads((tmp_path/'matrix-diagnostic.json').read_text())
    assert doc['actualMatrixDigest'] == matrix.digest()
    assert doc['expectedMatrixDigest'] == 'deliberate-mismatch'
    assert len(doc['features']['A01_return1d']['missingnessReasonsDigest']) == 64
    assert doc['pit']['pass'] and doc['missingness']['pass']
    assert all(v == 0 for v in doc['counters'].values())


def test_independent_value_reason_and_row_fingerprints():
    matrix = invented()
    a, _ = D.diagnostic(matrix, matrix.digest())
    matrix.values.loc[1, 'A01_return1d'] += .01
    b, _ = D.diagnostic(matrix, 'SYN')
    assert a['orderedRowIdentityDigest'] == b['orderedRowIdentityDigest']
    assert a['features']['A01_return1d']['valuesDigest'] != b['features']['A01_return1d']['valuesDigest']
    assert a['features']['A01_return1d']['missingnessReasonsDigest'] == b['features']['A01_return1d']['missingnessReasonsDigest']


def test_actual_frozen_preflight_still_refuses_and_leaves_diagnostics(tmp_path):
    inputs = SimpleNamespace(identity={'sourceCommit': 'SYN'}, trading_value_basis='SYN',
                             prices={}, calendar=pd.DatetimeIndex([]),
                             memberships=SimpleNamespace(snapshots=[]), accounting={})
    spec = {'phaseBIdentity': {'inputs': inputs.identity, 'matrixDigest': 'SYN_WRONG'},
            'tradingValueBasis': 'SYN', 'developmentCutoff': '2020-01-03'}
    with patch.object(preflight, 'verify_git_inputs', return_value={}), patch.object(D.AI, 'load_inputs', return_value=inputs), patch.object(MX, 'build_matrix', return_value=invented()), D.observe('SYN_WRONG', tmp_path/'diagnostics'):
        with pytest.raises(ValueError, match='PHASE_B_MATRIX_DIGEST_CHANGED'):
            preflight.prepare(D.contract.ROOT, spec, None, tmp_path/'SYN_inputs')
    report = json.loads((tmp_path/'diagnostics/matrix-diagnostic.json').read_text())
    assert report['actualMatrixDigest'] == invented().digest()
    assert all(v == 0 for v in report['counters'].values())


def test_pr_diagnostic_has_no_outcome_or_lock_permissions():
    text = (D.contract.ROOT/'.github/workflows/pages.yml').read_text()
    job = text.split('  matrix-diagnostic:', 1)[1].split('  matrix-formal-owner-only:', 1)[0]
    assert 'contents: read' in job and 'contents: write' not in job
    assert 'persist-credentials: false' in job
    assert ' execute ' not in job and 'execution-authorization' not in job
    assert "github.event_name != 'pull_request'" in text
