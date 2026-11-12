"""Exact operational variants alongside immutable historical research bytes.

Only the two ordinary installs and the closed-study diagnostic route may differ
from the approved state-publication parent. No scientific or formal gate moves.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess

MAIN = '37f8cbf6b1c066f6b3c65235953648d17ebf2f69'
PARENT = '23522002dcd2d9e0e16dfb9d325a235aef664f0c'
RECORD = 'docs/operations/pages-yml-maintenance-2.json'
SIDECAR = 'docs/operations/pages-yml-maintenance-2.sha256'
PREVIOUS = 'docs/operations/pages-yml-maintenance-1.json'
PREVIOUS_SHA = '436ce3361d1183fe11db0c931de0cf688dfdd021ac70c7173b8b35a939e25ddf'
PAGES = '.github/workflows/pages.yml'
TESTS = '.github/workflows/tests.yml'
VERIFIER = 'pipeline/kr_alpha_atlas_reproducibility.py'
WORKFLOW_TEST = 'tests/test_kr_alpha_atlas_reproducibility.py'
CONSTRAINTS = 'constraints/ci-registered-numerics-v1.txt'
BOUNDARY = b'  build-and-deploy:\n'
OLD_PREFIX_SHA = '048356c7b43e499b32660ce40c0b1dde9db7e43b33a58fd36df8a4ea51e17b30'
AUXILIARY = {
    CONSTRAINTS, 'pipeline/pages_operational_maintenance.py',
    'pipeline/closed_atlas_provenance.py', 'scripts/audit_closed_atlas_provenance.py',
    'docs/operations/closed-atlas-provenance-1.json',
    'docs/operations/closed-atlas-provenance-1.sha256',
}
OLD_DIAGNOSTIC = b'''      - name: Real full-input preflight behind the outcome firewall
        if: github.event_name == 'pull_request' || inputs.atlas_action == 'matrix-preflight'
        run: |
          python scripts/run_kr_alpha_atlas_phase_c_reproducible.py preflight \\
            --expected-main "$(git rev-parse origin/main)" --work /tmp/atlas-matrix-v4-preflight
'''
NEW_DIAGNOSTIC = b'''      - name: Closed-study provenance behind the outcome firewall
        if: github.event_name == 'pull_request' || inputs.atlas_action == 'matrix-preflight'
        run: |
          python scripts/audit_closed_atlas_provenance.py \\
            --expected-main "$(git rev-parse origin/main)" --work /tmp/atlas-matrix-v4-preflight
'''


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def require(condition):
    if not condition:
        raise ValueError('PAGES_MAINTENANCE_CONTRACT_CHANGED')


def read(root, relative):
    path = PurePosixPath(relative)
    require(not path.is_absolute() and '..' not in path.parts and path.as_posix() == relative)
    target = Path(root) / relative
    require(not target.is_symlink() and target.resolve().is_relative_to(Path(root).resolve()))
    return target.read_bytes()


def git(root, *args):
    require(args and args[0] in ('show', 'cat-file', 'ls-tree'))
    env = {**os.environ, 'GIT_NO_LAZY_FETCH': '1', 'GIT_TERMINAL_PROMPT': '0'}
    try:
        return subprocess.run(['git', '--no-replace-objects', '-c', 'remote.origin.promisor=false', *args],
                              cwd=root, env=env, check=True, capture_output=True, timeout=30).stdout
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise ValueError('MAINTENANCE_HISTORICAL_GIT_OBJECT_REQUIRED') from error


def historical(root, path, commit=MAIN):
    return git(root, 'show', commit + ':' + path)


def replace_once(raw, old, new):
    require(raw.count(old) == 1)
    return raw.replace(old, new, 1)


def pages_variant(parent):
    candidate = replace_once(parent, OLD_DIAGNOSTIC, NEW_DIAGNOSTIC)
    return replace_once(candidate, b'run: pip install -r requirements.txt\n',
                        b'run: pip install -c constraints/ci-registered-numerics-v1.txt -r requirements.txt\n')


def tests_variant(parent):
    return replace_once(parent, b'run: pip install -r requirements.txt -r requirements-dev.txt\n',
                        b'run: pip install -c constraints/ci-registered-numerics-v1.txt -r requirements.txt -r requirements-dev.txt\n')


def verifier_variant(parent):
    """The numerical preparation, audit, bindings and formal functions are immutable."""
    old = parent.decode()
    old = replace_once(old, 'import hashlib\n', '')
    old = replace_once(old, '# exact-hash maintenance record admits only the reviewed Pages production job.',
                       '# exact-hash records admit the reviewed operational install/diagnostic variant.')
    old = replace_once(old, "MAINTENANCE_RECORD = 'docs/operations/pages-yml-maintenance-1.json'",
                       "MAINTENANCE_RECORD = 'docs/operations/pages-yml-maintenance-2.json'")
    old = replace_once(old, "MAINTENANCE_SIDECAR = 'docs/operations/pages-yml-maintenance-1.sha256'",
                       "MAINTENANCE_SIDECAR = 'docs/operations/pages-yml-maintenance-2.sha256'")
    start = old.index('def pages_maintenance_admitted(')
    end = old.index('\n\ndef parent_load(', start)
    replacement = '''def pages_maintenance_admitted(root=contract.ROOT):
    """Admit only the approved exact operational variant; historical hashes stay."""
    from pipeline.pages_operational_maintenance import validate
    validate(root)
    return True
'''
    old = old[:start] + replacement + old[end:]
    old = replace_once(old, 'if path not in (PAGES_WORKFLOW, VERIFIER_MODULE):',
                       "if path not in (PAGES_WORKFLOW, VERIFIER_MODULE, 'tests/test_kr_alpha_atlas_reproducibility.py'):")
    return old.encode()


def _workflow_assertion_only(old, new):
    start = b'def test_workflow_separates_pr_preflight_owner_execution_and_pages():\n'
    end = b'\ndef test_captured_failure_was_not_silenced():'
    require(old.count(start) == new.count(start) == 1 and old.count(end) == new.count(end) == 1)
    require(old.split(start)[0] == new.split(start)[0] and old.split(end)[1] == new.split(end)[1])


def validate(root):
    """Both historical bytes and this exact, structurally bounded variant are required."""
    raw = read(root, RECORD)
    require(sha(raw) == read(root, SIDECAR).decode().strip())
    record = json.loads(raw)
    require(set(record) == {
        'schema', 'version', 'state', 'scope', 'referenceMain', 'parentMaintenanceCommit',
        'parentMaintenanceRecordSha256', 'originalPagesSha256', 'replacementPagesSha256',
        'originalVerifierSha256', 'replacementVerifierSha256', 'originalTestsSha256',
        'replacementTestsSha256', 'originalWorkflowTestSha256', 'replacementWorkflowTestSha256',
        'sealedResearchPrefixSha256', 'sealedResearchPrefixBytes', 'approvedResearchPrefixSha256',
        'approvedResearchPrefixBytes', 'protectedContracts', 'formalExecutionAuthorized', 'auxiliaryHashes',
    })
    require(record['schema'] == 'PAGES_WORKFLOW_OPERATIONAL_MAINTENANCE_V2'
            and type(record['version']) is int and record['version'] == 2
            and type(record['sealedResearchPrefixBytes']) is int
            and type(record['approvedResearchPrefixBytes']) is int
            and record['state'] == 'IMPLEMENTATION_APPROVED_FINAL_MERGE_PENDING'
            and record['scope'] == 'REGISTERED_CI_INSTALL_AND_CLOSED_STUDY_PROVENANCE_ONLY'
            and record['referenceMain'] == MAIN and record['parentMaintenanceCommit'] == PARENT
            and record['parentMaintenanceRecordSha256'] == PREVIOUS_SHA
            and record['formalExecutionAuthorized'] is False
            and record['protectedContracts'] == ['KR_ALPHA_ATLAS_PHASE_C_V4', 'RESEARCH_TERMINAL_PY',
                 'RESEARCH_TERMINAL_NODE', 'RP1_C1_US_WP4D', 'RP1_US_UNIVERSE'])
    previous = read(root, PREVIOUS)
    require(sha(previous) == PREVIOUS_SHA and previous == historical(root, PREVIOUS, PARENT))
    require(read(root, PREVIOUS.replace('.json', '.sha256')).decode().strip() == PREVIOUS_SHA)
    spec_path = 'research_specs/kr-alpha-atlas-phase-c-v4-reproducibility.json'
    spec_raw = read(root, spec_path)
    require(spec_raw == historical(root, spec_path)
            and sha(spec_raw) == read(root, spec_path.replace('.json', '.sha256')).decode().strip())
    spec = json.loads(spec_raw)
    require(spec['formalExecutionAuthorized'] is False and spec['freshExactHashOwnerApprovalRequired'] is True)
    require(record['originalPagesSha256'] == spec['additionalDependencyHashes'][PAGES]
            and record['originalVerifierSha256'] == spec['additionalDependencyHashes'][VERIFIER]
            and record['originalWorkflowTestSha256'] == spec['additionalDependencyHashes'][WORKFLOW_TEST])
    old_pages = historical(root, PAGES)
    parent_pages = historical(root, PAGES, PARENT)
    parent_record = json.loads(previous)
    require(sha(old_pages) == record['originalPagesSha256'] == parent_record['originalPagesSha256'])
    require(sha(parent_pages) == parent_record['replacementPagesSha256'])
    require(old_pages.count(BOUNDARY) == parent_pages.count(BOUNDARY) == 1)
    old_prefix = old_pages.split(BOUNDARY)[0]
    require(old_prefix == parent_pages.split(BOUNDARY)[0] and len(old_prefix) == 5992)
    require(sha(old_prefix) == record['sealedResearchPrefixSha256'] == OLD_PREFIX_SHA
            and record['sealedResearchPrefixBytes'] == 5992)
    require(sha(historical(root, VERIFIER)) == record['originalVerifierSha256']
            == parent_record['originalVerifierSha256'])
    require(sha(historical(root, VERIFIER, PARENT)) == parent_record['replacementVerifierSha256'])
    pages = read(root, PAGES)
    require(pages == pages_variant(parent_pages) and sha(pages) == record['replacementPagesSha256'])
    prefix = pages.split(BOUNDARY)[0]
    require(len(prefix) == record['approvedResearchPrefixBytes']
            and sha(prefix) == record['approvedResearchPrefixSha256'])
    require(sha(read(root, VERIFIER)) == record['replacementVerifierSha256'])
    require(read(root, VERIFIER) == verifier_variant(historical(root, VERIFIER, PARENT)))
    old_tests = historical(root, TESTS)
    require(sha(old_tests) == record['originalTestsSha256'])
    require(read(root, TESTS) == tests_variant(old_tests)
            and sha(read(root, TESTS)) == record['replacementTestsSha256'])
    old_assertion = historical(root, WORKFLOW_TEST)
    new_assertion = read(root, WORKFLOW_TEST)
    require(sha(old_assertion) == record['originalWorkflowTestSha256'])
    require(sha(new_assertion) == record['replacementWorkflowTestSha256'])
    _workflow_assertion_only(old_assertion, new_assertion)
    require(set(record['auxiliaryHashes']) == AUXILIARY)
    for path, expected in record['auxiliaryHashes'].items():
        require(sha(read(root, path)) == expected)
    require(sha(read(root, CONSTRAINTS)) == 'e214198fc1437b12fffa0d601d5b77bb4b44e1b5f96493b553b15d24f9dbdc2d')
    return record
