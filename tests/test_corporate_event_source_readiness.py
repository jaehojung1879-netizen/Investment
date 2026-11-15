"""Source-only regression: menus/versions are not economic N or PIT approval."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from research.corporate_event_readiness_v1.audit import verify_viewer_families
from research.corporate_event_readiness_v1.filings import parse_viewer_family
from research.corporate_event_readiness_v1.inventory import fixed_sample_readiness

ROOT = Path(__file__).resolve().parents[1] / 'research/corporate_event_readiness_v1'


def test_actual_menus_preserve_ten_versions_and_only_two_origin_candidates():
    rows = verify_viewer_families()
    assert len(rows) == 3
    assert sum(len(r['versions']) for r in rows) == 10
    assert sum(v['amendment'] for r in rows for v in r['versions']) == 7
    roots = {r['selectedReceipt']: r['originalReceiptCandidate'] for r in rows}
    assert roots == {'20261030800168': '20241226800099', '20191002800414': None,
                     '20241002800232': '20241002800232'}
    assert all(not r['pitEligible'] and r['independentEconomicEvents'] is None for r in rows)
    cancellation = next(r for r in rows if r['selectedReceipt'] == '20241002800232')
    assert cancellation['versions'][-1]['receiptDate'] == '2025-12-15'
    assert all(v['publishedAt'] is None for v in cancellation['versions'])


def menu(*options):
    return ('<select id="family">' + ''.join(
        '<option value="rcpNo=' + no + '">' + title + '</option>'
        for no, title in options) + '</select>').encode()


def parse(raw, receipt='20260102000001'):
    return parse_viewer_family(raw, receipt=receipt, sha256=hashlib.sha256(raw).hexdigest())


def test_duplicate_receipt_cannot_inflate_event_count():
    raw = menu(('20260102000001', '2026.01.02 소각결정'),
               ('20260102000001', '2026.01.02 소각결정'))
    with pytest.raises(ValueError, match='UNIQUE_SELECTED_RECEIPT'):
        parse(raw)


def test_navigation_does_not_guess_between_multiple_originals():
    raw = menu(('20260102000001', '2026.01.02 소각결정'),
               ('20260103000002', '2026.01.03 소각결정'))
    assert parse(raw)['originalReceiptCandidate'] is None


@pytest.mark.parametrize('raw,reason', [
    (b'<select></select>', 'UNIQUE_VIEWER_FAMILY_MENU'),
    (menu(('20260102000001', '2025.01.02 소각결정')), 'VIEWER_RECEIPT_DATE'),
    (menu(('20260103000001', '2026.01.03 소각결정')), 'UNIQUE_SELECTED_RECEIPT'),
    (menu(('20260102000001', '2026.01.02 [정정] 소각결정'),
          ('20260103000002', '2026.01.03 소각결정')), 'AMENDMENT_PRECEDES_ORIGINAL'),
])
def test_bad_menus_fail_closed(raw, reason):
    with pytest.raises(ValueError, match=reason):
        parse(raw)


def test_menu_hash_tamper_is_refused():
    with pytest.raises(ValueError, match='VIEWER_INPUT_HASH'):
        parse_viewer_family(b'changed', receipt='20260102000001', sha256='0' * 64)


def test_actual_fixture_cohort_is_source_blocked_not_thirteen_events():
    rows = json.loads((ROOT / 'evidence/parsed-filing-samples.json').read_text())
    result = fixed_sample_readiness(rows + [deepcopy(rows[0])])
    assert result['retainedVersions'] == 13
    assert result['duplicateReceiptRowsRemoved'] == 1
    assert result['issuerCandidates'] == 7
    assert result['sourceQualifiedReceiptCandidates'] == 0
    assert result['sourceBlockedReceipts'] == 13
    assert result['byPitIndustry'] == {'UNRESOLVED': {'retainedVersions': 13, 'sourceQualified': 0}}
    assert result['independentN'] is result['uniqueEconomicEvents'] is result['mde'] is None
    assert result['returnsRead'] == 0
    original_cancellation = next(r for r in rows if r['family'] == 'CANCELLATION')
    assert original_cancellation['completion_status'] == 'NOT_OBSERVED'


def test_receipt_revision_and_cross_issuer_collision_are_refused():
    row = json.loads((ROOT / 'evidence/parsed-filing-samples.json').read_text())[0]
    changed = {**row, 'input_sha256': '0' * 64}
    with pytest.raises(ValueError, match='CONFLICTING_FIXED_RECEIPT'):
        fixed_sample_readiness([row, changed])
    with pytest.raises(ValueError, match='RECEIPT_ISSUER_CONFLICT'):
        fixed_sample_readiness([row, {**row, 'issuer_id': 'SYN_OTHER_ISSUER'}])


def test_forged_ready_label_cannot_erase_evidence_blockers():
    row = json.loads((ROOT / 'evidence/parsed-filing-samples.json').read_text())[0]
    row.update(economic_study_ready=True, data_eligibility='READY')
    assert fixed_sample_readiness([row])['sourceQualifiedReceiptCandidates'] == 0
