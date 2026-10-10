"""Explicit v4 numerical-runtime addendum; no scientific function duplicated.

v1/v2/v3 stay byte-identical. Reuses v3 preparation, executor and atomic lifecycle,
with an exactly bound CPU dispatch and diagnostics before the unchanged gate.
"""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
import time
from unittest.mock import patch

from pipeline import kr_alpha_atlas_mirae_repair as R
from pipeline import kr_alpha_atlas_matrix_diagnostics as D
from pipeline import kr_alpha_atlas_numeric_runtime as NR
from pipeline import kr_model_raw_snapshot as RAW
from pipeline.kr_alpha_atlas_integrity_audit import AuditCounters
from pipeline.kr_alpha_atlas_phase_c import contract

ADDENDUM = 'research_specs/kr-alpha-atlas-phase-c-v4-reproducibility.json'
SIDECAR = 'research_specs/kr-alpha-atlas-phase-c-v4-reproducibility.sha256'
AUTHORIZATION = 'research_specs/kr-alpha-atlas-phase-c-v4-execution-authorization.json'
PARENT_SHA = '64c742408331d7da91e8def6a6eba6fde52d5f19734b011e1287e8a7622c8198'
BASE = 'docs/audits/kr-alpha-atlas-phase-c-reproducibility'
ADDITIONAL_FILES = (
    'pipeline/kr_alpha_atlas_matrix_diagnostics.py',
    'pipeline/kr_alpha_atlas_numeric_runtime.py',
    'pipeline/kr_alpha_atlas_reproducibility.py',
    'scripts/diagnose_kr_alpha_atlas_matrix.py',
    'scripts/run_kr_alpha_atlas_phase_c_reproducible.py',
    'tests/test_kr_alpha_atlas_matrix_diagnostics.py',
    'tests/test_kr_alpha_atlas_reproducibility.py',
    '.github/workflows/pages.yml', BASE+'/root-cause.json',
)
_PARENT = {'ADDENDUM': R.ADDENDUM, 'SIDECAR': R.SIDECAR, 'AUTHORIZATION': R.AUTHORIZATION,
           'load': R.load, 'prepare': R.prepare}


def parent_load(root):
    # A scoped binding below never changes the parent's published hash checks.
    with ExitStack() as stack:
        for name, value in _PARENT.items():
            stack.enter_context(patch.object(R, name, value))
        return _PARENT['load'](root)


def expected_effective(parent, meta):
    out = deepcopy(parent)
    out['version'] = 4
    out['registrationAmendmentId'] = 'kr-alpha-atlas-phase-c-v4-numerical-reproducibility'
    out['phaseBIdentity']['matrixDigest'] = meta['correctedMatrixDigest']
    out['runtime']['environment'] = {**parent['runtime']['environment'], **NR.ENVIRONMENT}
    out['lifecycle']['authorizationPath'] = AUTHORIZATION
    out['dependencyHashes'] = {**parent['dependencyHashes'], **meta['additionalDependencyHashes']}
    out['numericalReproducibilityAddendum'] = {
        'parentV3FileSha256': PARENT_SHA,
        'publishedV3MatrixDigest': parent['phaseBIdentity']['matrixDigest'],
        'policy': 'PIN_AVX2_NUMPY_AND_HASWELL_BLAS_BEFORE_IMPORT_NO_GATE_TOLERANCE_CHANGE',
        'rootCauseEvidenceSha256': meta['additionalDependencyHashes'][BASE+'/root-cause.json'],
    }
    return out


def load(root=contract.ROOT):
    root = Path(root)
    parent = parent_load(root)
    if contract.file_hash(root/_PARENT['ADDENDUM']) != PARENT_SHA:
        raise ValueError('PUBLISHED_V3_NOT_PRESERVED')
    if contract.file_hash(root/ADDENDUM) != (root/SIDECAR).read_text().strip():
        raise ValueError('REPRODUCIBILITY_ADDENDUM_CHANGED')
    meta = json.loads((root/ADDENDUM).read_text())
    keys = {'additionalDependencyHashes', 'amendmentId', 'correctedMatrixDigest',
            'dependencyManifestSha256', 'effectiveContractSha256', 'formalExecutionAuthorized',
            'freshExactHashOwnerApprovalRequired', 'globalOneShotLock', 'numericalEnvironment',
            'parentV3FileSha256', 'publishedV3MatrixDigest', 'reason', 'sameArtifactPrefix',
            'sameResultPath', 'sameStudyId', 'schema', 'unchangedInputIdentitySha256', 'version'}
    if (set(meta) != keys or meta['schema'] != 'KR_ALPHA_ATLAS_PRE_OUTCOME_NUMERICAL_ADDENDUM_V1' or
            type(meta['version']) is not int or meta['version'] != 4 or
            meta['amendmentId'] != 'kr-alpha-atlas-phase-c-v4-numerical-reproducibility'):
        raise ValueError('SUPPORTED_EXACT_V4_ADDENDUM_REQUIRED')
    if (meta['parentV3FileSha256'] != PARENT_SHA or meta['sameStudyId'] != contract.STUDY or
            meta['globalOneShotLock'] != parent['lifecycle']['lockPrefix'] or
            meta['sameResultPath'] != parent['lifecycle']['resultPath'] or
            meta['sameArtifactPrefix'] != parent['lifecycle']['artifactPrefix'] or
            meta['formalExecutionAuthorized'] is not False or
            meta['freshExactHashOwnerApprovalRequired'] is not True or
            meta['publishedV3MatrixDigest'] != parent['phaseBIdentity']['matrixDigest'] or
            meta['unchangedInputIdentitySha256'] != parent['phaseBIdentity']['inputs']['sha256'] or
            meta['numericalEnvironment'] != NR.ENVIRONMENT):
        raise ValueError('ONE_ORIGINAL_STUDY_AND_EXACT_RUNTIME_REQUIRED')
    if set(meta['additionalDependencyHashes']) != set(ADDITIONAL_FILES):
        raise ValueError('COMPLETE_REPRODUCIBILITY_CLOSURE_REQUIRED')
    for path, sha in meta['additionalDependencyHashes'].items():
        p = (root/path).resolve()
        if not p.is_relative_to(root.resolve()) or contract.file_hash(p) != sha:
            raise ValueError('REPRODUCIBILITY_DEPENDENCY_CHANGED: '+path)
    evidence = json.loads((root/BASE/'root-cause.json').read_text())
    full = evidence['fullMatrixReproduction']
    if (full['actualMatrixDigest'] != meta['correctedMatrixDigest'] or
            full['expectedMatrixDigest'] != parent['phaseBIdentity']['matrixDigest'] or
            full['reconstructedOriginalCanonicalDigest'] != parent['phaseBIdentity']['matrixDigest'] or
            full['rowCount'] != 85680 or len(full['featureColumns']) != 76 or
            full['inputIdentity'] != parent['phaseBIdentity']['inputs'] or
            not full['pit']['pass'] or not full['missingness']['pass']):
        raise ValueError('INDEPENDENT_SOURCE_ONLY_NUMERICAL_REPRODUCTION_REQUIRED')
    out = expected_effective(parent, meta)
    if (contract.digest(out) != meta['effectiveContractSha256'] or
            contract.digest(out['dependencyHashes']) != meta['dependencyManifestSha256'] or
            len(meta['correctedMatrixDigest']) != 64):
        raise ValueError('EXACT_EFFECTIVE_REPRODUCIBILITY_CONTRACT_REQUIRED')
    return out


def prepare(root, spec, work, *, capture=None):
    NR.verify(spec)  # Cheap, before inputs and long before lock.
    with D.observe(spec['phaseBIdentity']['matrixDigest'], Path(work)/'matrix-diagnostics'):
        data, identity = _PARENT['prepare'](root, spec, work, capture=capture)
    identity['numericalReproducibility'] = spec['numericalReproducibilityAddendum']
    return data, identity


@contextmanager
def bindings():
    """Single-threaded orchestration only; frozen scientific functions untouched."""
    with ExitStack() as stack:
        for name, value in {'ADDENDUM': ADDENDUM, 'SIDECAR': SIDECAR,
                            'AUTHORIZATION': AUTHORIZATION, 'load': load, 'prepare': prepare}.items():
            stack.enter_context(patch.object(R, name, value))
        yield


def _reject_parent_approvals(root):
    parent = parent_load(root)
    paths = (_PARENT['AUTHORIZATION'], R.V2.load(root)['lifecycle']['authorizationPath'],
             contract.load(root)['lifecycle']['authorizationPath'])
    if any((Path(root)/p).exists() for p in paths):
        raise ValueError('SUPERSEDED_VERSION_AUTHORIZATION_MUST_NOT_BE_USED')
    return parent


def audit(root, work, expected_main):
    work = Path(work)
    receipt = {'scope': 'V4_SOURCE_ONLY_PREFLIGHT', 'status': 'STARTED', 'counters': asdict(AuditCounters())}
    start = time.monotonic()
    try:
        _reject_parent_approvals(root)
        spec = load(root)
        NR.verify(spec)
        with bindings():
            report = R.audit(root, work, expected_main)
        receipt.update(status=report['status'], actualMatrixDigest=report['actualMatrixDigest'],
                       expectedMatrixDigest=spec['phaseBIdentity']['matrixDigest'])
        return report
    except Exception as error:
        receipt.update(status='FAIL_GATE_PRESERVED_NOT_CONSUMED', errorClass=type(error).__name__, error=str(error))
        raise
    finally:
        receipt['elapsedSeconds'] = round(time.monotonic()-start, 3)
        work.mkdir(parents=True, exist_ok=True)
        RAW.immutable_bytes(work/'reproducibility-preflight-receipt.json', contract.canonical(receipt)+b'\n')


def formal(root=contract.ROOT, *, work, github=None):
    _reject_parent_approvals(root)
    load(root)
    with bindings():
        # Exact owner approval, clean actual main, preflight, atomic global lock,
        # first outcome permit and consumed-failure rules are the frozen lifecycle.
        return R.formal(root, work=work, github=github)
