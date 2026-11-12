"""Read-only identities of a permanently consumed study; no numerical imports.

This is neither an execution preflight nor a result evaluation. Stored result
bytes, when required by a registration, are hashed opaquely and never decoded.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess

from pipeline import pages_operational_maintenance as M

REPOSITORY = 'jaehojung1879-netizen/Investment'
EVIDENCE = 'docs/operations/closed-atlas-provenance-1.json'
CONSUMED = '09ba076f9fcd7ca9957b12933dd51bd69e6506d0'
STUDY = 'kr-alpha-atlas-phase-c-v1'
LOCK = 'refs/tags/' + STUDY + '-execution-lock'
SPEC_NAMES = ('kr-alpha-atlas-phase-c-v1', 'kr-alpha-atlas-phase-c-v2-amendment',
              'kr-alpha-atlas-phase-c-v3-price-repair', 'kr-alpha-atlas-phase-c-v4-reproducibility')
POLICY = 'docs/ci/historical-workflow-provenance-v1.json'
AUTH = 'research_specs/kr-alpha-atlas-phase-c-v4-execution-authorization.json'
METADATA = {f'research_specs/{name}.{suffix}' for name in SPEC_NAMES for suffix in ('json', 'sha256')} | {
    AUTH, POLICY, 'docs/audits/kr-alpha-atlas-phase-c-reproducibility/root-cause.json',
    'docs/audits/kr-alpha-atlas-phase-c-reproducibility/validation.json',
}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return M.sha(canonical(value))


def require(condition, error):
    if not condition:
        raise ValueError(error)


class ReadOnlyGitHub:
    """No method for writes, dispatch, lock acquisition or artifact downloads."""
    def get(self, path):
        require(path in ('git/ref/heads/main', 'git/matching-refs/tags/' + LOCK.removeprefix('refs/tags/')),
                'PROVENANCE_READ_ENDPOINT_REQUIRED')
        result = subprocess.run(['gh', 'api', 'repos/' + REPOSITORY + '/' + path, '--method', 'GET'],
                                check=False, capture_output=True, timeout=60)
        require(result.returncode == 0, 'PROVENANCE_GITHUB_READ_REFUSED')
        return json.loads(result.stdout)


def file_hash(root, path):
    target = Path(root) / path
    require(not target.is_symlink() and target.resolve().is_relative_to(Path(root).resolve()),
            'PROVENANCE_SOURCE_PATH_ESCAPE')
    # Do not parse any historical prices, labels or result values.
    with target.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def inspect(root, *, expected_main, github=None):
    root = Path(root)
    require(isinstance(expected_main, str) and re.fullmatch('[0-9a-f]{40}', expected_main),
            'IMMUTABLE_EXPECTED_MAIN_REQUIRED')
    M.validate(root)
    raw = M.read(root, EVIDENCE)
    require(M.sha(raw) == M.read(root, EVIDENCE.replace('.json', '.sha256')).decode().strip(),
            'CLOSED_PROVENANCE_EVIDENCE_CHANGED')
    evidence = json.loads(raw)
    require(set(evidence) == {'schema', 'referenceMain', 'studyId', 'consumedCommit', 'lockPrefix',
                             'lockRefs', 'metadataSha256', 'resultPath', 'resultPresent'},
            'EXACT_CLOSED_PROVENANCE_SCHEMA_REQUIRED')
    require(evidence['schema'] == 'CLOSED_ATLAS_PROVENANCE_V1' and evidence['referenceMain'] == M.MAIN
            and evidence['studyId'] == STUDY and evidence['consumedCommit'] == CONSUMED
            and evidence['lockPrefix'] == LOCK and evidence['resultPresent'] is False
            and evidence['resultPath'] == 'docs/results/kr-alpha-atlas-phase-c-v1-result.json'
            and set(evidence['metadataSha256']) == METADATA, 'EXACT_CONSUMED_STUDY_REQUIRED')
    for path, expected in evidence['metadataSha256'].items():
        historical = M.historical(root, path)
        require(M.sha(historical) == file_hash(root, path) == expected, 'FROZEN_PROVENANCE_METADATA_CHANGED')
    specs = []
    for name in SPEC_NAMES:
        path = f'research_specs/{name}.json'
        require(file_hash(root, path) == M.read(root, path.replace('.json', '.sha256')).decode().strip(),
                'FROZEN_REGISTRATION_SIDECAR_CHANGED')
        specs.append(json.loads(M.read(root, path)))
    v1, _, _, v4 = specs
    require(v1['studyId'] == STUDY and v1['lifecycle']['lockPrefix'] == LOCK
            and v1['lifecycle']['resultPath'] == evidence['resultPath']
            and v4['globalOneShotLock'] == LOCK and v4['sameStudyId'] == STUDY
            and v4['formalExecutionAuthorized'] is False, 'ORIGINAL_LIFECYCLE_CHANGED')
    manifest = dict(v1['dependencyHashes'])
    for spec in specs[1:]:
        manifest.update(spec['additionalDependencyHashes'])
    authorization = json.loads(M.read(root, AUTH))
    require(digest(manifest) == v4['dependencyManifestSha256'] == authorization['dependencyManifestSha256']
            and v4['effectiveContractSha256'] == authorization['effectiveContractSha256'],
            'HISTORICAL_DEPENDENCY_IDENTITY_CHANGED')
    # Preserve the historical execution authorization; do not reuse it.
    for path in (f'research_specs/{SPEC_NAMES[-1]}.json', AUTH):
        require(M.sha(M.historical(root, path, CONSUMED)) == file_hash(root, path),
                'CONSUMED_REGISTRATION_OR_AUTHORIZATION_CHANGED')
    lock_refs = [LOCK, LOCK + '-spec-' + file_hash(root, f'research_specs/{SPEC_NAMES[-1]}.json')]
    require(evidence['lockRefs'] == lock_refs, 'EXACT_CONSUMED_LOCK_SET_REQUIRED')
    policy = json.loads(M.read(root, POLICY))
    require(set(policy['historicalDependencies']) == {M.TESTS, 'pipeline/kr_alpha_atlas_phase_c/contract.py'},
            'HISTORICAL_ADAPTER_SCOPE_CHANGED')
    operational = {M.PAGES, M.VERIFIER, M.WORKFLOW_TEST}
    for path, expected in manifest.items():
        if file_hash(root, path) == expected:
            continue
        if path in operational:
            require(M.sha(M.historical(root, path)) == expected, 'HISTORICAL_OPERATIONAL_DEPENDENCY_CHANGED')
        elif path in policy['historicalDependencies']:
            require(policy['historicalDependencies'][path] == expected
                    and M.sha(M.historical(root, path, policy['registrationCommit'])) == expected,
                    'HISTORICAL_CI_DEPENDENCY_CHANGED')
            if path != M.TESTS:
                require(file_hash(root, path) == policy['currentValidatorSha256'], 'HISTORICAL_ADAPTER_CHANGED')
        else:
            raise ValueError('REGISTERED_SCIENTIFIC_DEPENDENCY_CHANGED: ' + path)
    for path, expected in v1['protectedHashes'].items():
        require(file_hash(root, path) == expected, 'PROTECTED_RESEARCH_BYTES_CHANGED: ' + path)
    # A consumed failure has no formal result. Absence is not a successful study.
    for commit in (M.MAIN, CONSUMED):
        require(M.git(root, 'cat-file', '-t', commit).strip() == b'commit', 'HISTORICAL_COMMIT_REQUIRED')
        require(not M.git(root, 'ls-tree', '-z', commit, '--', evidence['resultPath']),
                'HISTORICAL_RESULT_PRESENCE_CHANGED')
    result_path = root / evidence['resultPath']
    require(not result_path.exists() and not result_path.is_symlink(), 'UNEXPECTED_FORMAL_RESULT_PRESENT')
    github = github or ReadOnlyGitHub()
    require(github.get('git/ref/heads/main')['object']['sha'] == expected_main,
            'PROVENANCE_MAIN_MOVED_OR_STALE_EXPECTATION')
    locks = github.get('git/matching-refs/tags/' + LOCK.removeprefix('refs/tags/'))
    observed = sorted((r['ref'], r['object']['type'], r['object']['sha']) for r in locks)
    require(observed == sorted((ref, 'commit', CONSUMED) for ref in lock_refs),
            'CONSUMED_LOCK_MISSING_CHANGED_OR_UNEXPECTED')
    return {'status': 'CLOSED_STUDY_HISTORICAL_PROVENANCE_VERIFIED',
            'scope': 'READ_ONLY_CLOSED_STUDY_PROVENANCE', 'studyId': STUDY,
            'operationalMaintenanceVersion': 2,
            'operationalMaintenanceRecordSha256': M.sha(M.read(root, M.RECORD)),
            'referenceMain': M.MAIN, 'observedMain': expected_main, 'consumedCommit': CONSUMED,
            'lockRefs': lock_refs, 'permanentlyConsumed': True,
            'historicalAuthorizationPreserved': True, 'authorizationUsableForNewExecution': False,
            'historicalResult': 'ABSENT_IN_REFERENCE_GIT_NO_SUCCESS_CLAIM',
            'externalOutcomeArtifacts': 'NOT_FETCHED_OR_EVALUATED',
            'registeredDependencyManifestSha256': digest(manifest),
            'registeredDependenciesVerified': len(manifest), 'protectedFilesVerified': len(v1['protectedHashes']),
            'inputEvidence': 'REGISTERED_IDENTITIES_ONLY_NOT_REPREPARED',
            'newExecutionPreflight': 'NOT_RUN', 'formalExecutionAuthorized': False,
            'counters': {'outcomeReads': 0, 'labelBuilds': 0, 'modelFits': 0, 'backtests': 0,
                         'dispatches': 0, 'lockWrites': 0, 'refWrites': 0}}
