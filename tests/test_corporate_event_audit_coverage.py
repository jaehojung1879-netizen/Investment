"""Source completeness must come from retained menus, never the saved output list."""
import json
import shutil

import pytest

from research.corporate_event_readiness_v1.audit import ROOT, verify_extended_sources


@pytest.fixture
def packet(tmp_path):
    root = tmp_path / 'packet'
    shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns('__pycache__'))
    return root


def change(root, filename, mutation):
    path = root / 'evidence' / filename
    rows = json.loads(path.read_text())
    mutation(rows)
    path.write_text(json.dumps(rows))


@pytest.mark.parametrize('mutation', [
    lambda rows: rows.pop(),
    lambda rows: rows.clear(),
    lambda rows: rows.append(rows[0]),
    lambda rows: rows[0].update(receipt='20121112800006'),
])
def test_omitted_duplicate_or_unrelated_saved_body_is_not_a_complete_replay(packet, mutation):
    change(packet, 'version-terms-v1.json', mutation)
    with pytest.raises(ValueError, match='EXACT_VIEWER_VERSION_COVERAGE_REQUIRED'):
        verify_extended_sources(packet)


@pytest.mark.parametrize('mutation', [
    lambda rows: rows.clear(),
    lambda rows: rows.pop(),
    lambda rows: rows.append(rows[0]),
    lambda rows: rows[0]['matchedReceipts'].pop(),
])
def test_incomplete_index_proof_is_refused_before_any_git_read(packet, mutation, monkeypatch):
    change(packet, 'index-family-crosscheck-v1.json', mutation)

    def no_git(*args, **kwargs):
        pytest.fail('Incomplete proof must fail before a Git subprocess is reached')

    monkeypatch.setattr('subprocess.check_output', no_git)
    with pytest.raises(ValueError, match='EXACT_FIXED_INDEX_COVERAGE_REQUIRED'):
        verify_extended_sources(packet, verify_source_git=True)


@pytest.mark.parametrize('field,value,reason', [
    ('sourceCommit', '0' * 40, 'EXACT_FIXED_INDEX_SCOPE_REQUIRED'),
    ('sourcePath', 'unrelated.jsonl.gz', 'EXACT_FIXED_INDEX_SCOPE_REQUIRED'),
    ('issuer', 'OTHER', 'EXACT_FIXED_INDEX_SCOPE_REQUIRED'),
    ('indexBlob', '0' * 40, 'EXACT_FIXED_INDEX_SCOPE_REQUIRED'),
    ('matchedVersionCount', 0, 'EXACT_FIXED_INDEX_COUNT_REQUIRED'),
    ('matchedVersionCount', True, 'EXACT_FIXED_INDEX_COUNT_REQUIRED'),
    ('researchAdmission', True, 'INDEX_CORROBORATION_CANNOT_AUTHORIZE_RESEARCH'),
    ('historicalPublicationClockVerified', True, 'INDEX_CORROBORATION_CANNOT_AUTHORIZE_RESEARCH'),
    ('historicalSecurityIdentityVerified', True, 'INDEX_CORROBORATION_CANNOT_AUTHORIZE_RESEARCH'),
])
def test_default_audit_also_checks_index_scope_counts_and_no_pit_escalation(packet, field, value, reason):
    change(packet, 'index-family-crosscheck-v1.json', lambda rows: rows[0].update({field: value}))
    with pytest.raises(ValueError, match=reason):
        verify_extended_sources(packet)


def test_body_manifest_cannot_silently_overwrite_an_existing_receipt(packet):
    first = json.loads((packet / 'evidence/filing-samples.json').read_text())['samples'][0]
    change(packet, 'chain-body-samples-v1.json', lambda data: data['samples'].append(first))
    with pytest.raises(ValueError, match='DUPLICATE_FIXED_BODY_RECEIPT'):
        verify_extended_sources(packet)


@pytest.mark.parametrize('mutation', [lambda rows: rows.pop(), lambda rows: rows.append(rows[0])])
def test_capital_share_projection_must_cover_every_applicable_fixed_body(packet, mutation):
    change(packet, 'capital-share-evidence-v1.json', mutation)
    with pytest.raises(ValueError, match='EXACT_CAPITAL_SHARE_EVIDENCE_REQUIRED'):
        verify_extended_sources(packet)


def test_current_complete_packet_remains_source_only():
    result = verify_extended_sources(ROOT)
    assert result['versionedBodiesReproduced'] == 9
    assert result['indexVersionLinks'] == 10
    assert result['capitalShareBodiesReproduced'] == 9
    assert result['commonDenominatorCellsObserved'] == 6
    assert result['unclassifiedShareTotalsObserved'] == 1
    assert not result['indexBytesReverifiedFromLocalGit']
    assert not result['historicalPublicationVerified'] and not result['researchAdmission']
