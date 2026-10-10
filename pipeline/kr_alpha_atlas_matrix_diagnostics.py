"""Bounded source-only diagnostics around the unchanged frozen matrix gate.

No labels, fits, portfolio statistics, authorization or lock entry point.
The observer returns the same Matrix; the original exact-digest gate still runs.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
import gzip
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import time
from unittest.mock import patch

import numpy as np
from threadpoolctl import threadpool_info

from pipeline import kr_alpha_atlas_inputs as AI, kr_alpha_atlas_matrix as MX
from pipeline import kr_alpha_atlas_mirae_repair as R
from pipeline import kr_alpha_atlas_readiness as RD
from pipeline import kr_model_raw_snapshot as RAW
from pipeline.kr_alpha_atlas_integrity_audit import AuditCounters, outcome_free_firewall
from pipeline.kr_alpha_atlas_phase_c import contract

SAMPLE_DATES = ('2014-01-10', '2016-04-01', '2018-03-30', '2018-08-03',
                '2020-03-20', '2022-07-01', '2026-03-20', '2026-09-11')


def runtime():
    from numpy._core import _multiarray_umath
    return {'python': platform.python_version(), 'platform': platform.platform(),
            'packages': {p: importlib.metadata.version(p) for p in
                         ('numpy', 'pandas', 'scipy', 'scikit-learn', 'threadpoolctl')},
            'environment': {k: os.environ.get(k) for k in
                            ('PYTHONHASHSEED', 'OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS',
                             'MKL_NUM_THREADS', 'OPENBLAS_CORETYPE', 'NPY_DISABLE_CPU_FEATURES',
                             'LC_ALL', 'LANG', 'TZ')},
            'numpyCpuFeatures': _multiarray_umath.__cpu_features__,
            'threadpools': [{k: v for k, v in x.items() if k != 'filepath'} for x in threadpool_info()]}


def _json_digest(obj):
    # Deliberately the SAME JSON conventions as Matrix.digest(), including spaces.
    return hashlib.sha256(json.dumps(obj).encode()).hexdigest()


def diagnostic(matrix, expected):
    order = matrix.rows.sort_values(['date', 'ticker']).index
    rows = matrix.rows.loc[order, ['date', 'ticker', 'industry', 'liquidityTier']].astype(str).values.tolist()
    values, reasons, features = {}, {}, {}
    for col in sorted(matrix.values.columns):
        values[col] = [None if not np.isfinite(v) else float(f'{v:.12g}')
                       for v in matrix.values.loc[order, col].to_numpy(float)]
        reasons[col] = matrix.reasons.loc[order, col].fillna('').tolist()
        features[col] = {'valuesDigest': _json_digest(values[col]),
                         'missingnessReasonsDigest': _json_digest(reasons[col]),
                         'finiteCells': sum(v is not None for v in values[col])}
    return {'schema': 'KR_ATLAS_MATRIX_DIAGNOSTIC_V1', 'scope': 'PIT_FEATURES_ONLY',
            'expectedMatrixDigest': expected, 'actualMatrixDigest': matrix.digest(),
            'rowCount': len(rows), 'featureColumns': sorted(values),
            'orderedRowIdentityDigest': _json_digest(rows), 'features': features,
            'inputIdentity': matrix.identity, 'runtime': runtime(),
            'pit': RD.pit_checks(matrix), 'missingness': RD.reason_checks(matrix),
            'counters': asdict(AuditCounters())}, {'rows': rows, 'values': values, 'reasons': reasons}


def write_diagnostic(matrix, expected, work):
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    report, payload = diagnostic(matrix, expected)
    RAW.immutable_bytes(work/'matrix-diagnostic.json', contract.canonical(report)+b'\n')
    # Bounded source-feature cells, not return targets; useful for exact cell comparison.
    RAW.immutable_bytes(work/'matrix-cells.json.gz', gzip.compress(contract.canonical(payload), mtime=0))
    print(json.dumps({k: report[k] for k in ('expectedMatrixDigest', 'actualMatrixDigest',
                                           'rowCount', 'orderedRowIdentityDigest')}), flush=True)
    return report


@contextmanager
def observe(expected, work):
    original = MX.build_matrix

    def measured(*args, **kwargs):
        matrix = original(*args, **kwargs)
        write_diagnostic(matrix, expected, work)
        return matrix  # Original gate receives identical object and digest.

    with patch.object(MX, 'build_matrix', measured):
        yield


def run(root, work, mode, expected_main=None):
    root, work = Path(root), Path(work)
    if work.exists():
        raise ValueError('FRESH_DIAGNOSTIC_DIRECTORY_REQUIRED')
    work.mkdir(parents=True)
    spec = R.load(root)
    start = time.monotonic()
    receipt = {'mode': mode, 'runtime': runtime(), 'status': 'STARTED',
               'expectedMatrixDigest': spec['phaseBIdentity']['matrixDigest'],
               'counters': asdict(AuditCounters())}
    try:
        with outcome_free_firewall() as attempts:
            if mode == 'sample':
                with R.corrected_loader(root):
                    inputs = AI.load_inputs(spec['phaseBIdentity']['inputs']['sourceCommit'], work/'inputs', root)
                    if inputs.identity != spec['phaseBIdentity']['inputs']:
                        raise ValueError('PINNED_INPUT_IDENTITY_CHANGED')
                    matrix = MX.build_matrix(inputs, list(SAMPLE_DATES))
                write_diagnostic(matrix, 'SAMPLE_NOT_FULL_REGISTERED_DIGEST', work)
            elif mode == 'preflight':
                with observe(spec['phaseBIdentity']['matrixDigest'], work):
                    R.audit(root, work/'preflight', expected_main)
            else:
                raise ValueError('SAFE_SAMPLE_OR_PREFLIGHT_ONLY')
            receipt.update(status='PASS', firewallBlockedCalls=attempts)
    except Exception as error:
        receipt.update(status='FAIL_GATE_PRESERVED', errorClass=type(error).__name__, error=str(error))
        raise
    finally:
        receipt['elapsedSeconds'] = round(time.monotonic()-start, 3)
        RAW.immutable_bytes(work/'diagnostic-receipt.json', contract.canonical(receipt)+b'\n')
    return receipt
