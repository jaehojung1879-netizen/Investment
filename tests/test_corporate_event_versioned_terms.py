"""Actual amendment terms are versioned evidence, never backfilled signal data."""
import gzip
import hashlib
import json
from pathlib import Path

import pytest

from research.corporate_event_readiness_v1.filings import (
    as_of_chain, corroborate_family_index, load_filing, version_terms,
)

ROOT = Path(__file__).resolve().parents[1] / 'research/corporate_event_readiness_v1'
META = {}
for name in ('filing-samples.json', 'chain-body-samples-v1.json'):
    META.update({r['rcept_no']: r for r in json.loads((ROOT / 'evidence' / name).read_text())['samples']})


def terms(no):
    return version_terms(load_filing(ROOT / 'evidence', META[no]), META[no])


def test_every_version_of_the_two_explicit_families_has_a_retained_body():
    families = json.loads((ROOT / 'evidence/viewer-family-links.json').read_text())
    ids = {v['receipt'] for family in families if family['originalReceiptCandidate']
           for v in family['versions']}
    assert len(ids) == 9
    assert all(no in META for no in ids)
    for no in ids:
        r = terms(no)
        assert not r['historicalVersionAuthenticated'] and r['publishedAt'] is None
        assert r['completionStatus'] == 'NOT_OBSERVED' and not r['researchAdmission']


def test_withheld_contract_size_is_not_filled_from_later_disclosure():
    original, amendment, later = map(terms, ['20241226800099', '20250327801734', '20261030800168'])
    assert original['contractName'] == amendment['contractName'] == later['contractName']
    assert original['amountKrw'] is amendment['amountKrw'] is None
    assert original['amountStatus'] == amendment['amountStatus'] == 'WITHHELD_AT_THIS_VERSION'
    assert later['amountStatus'] == 'OBSERVED' and later['amountKrw'] is not None
    assert all(not x['researchAdmission'] for x in (original, amendment, later))
    # A receipt DAY or a current menu cannot create a historical publication clock.
    assert as_of_chain([dict(x, pit_available_at=x['publishedAt'])
                        for x in (original, amendment, later)], '2025-01-01T00:00:00Z') == []


def test_cancellation_revision_does_not_replace_original_share_count():
    original, revised, later = map(terms, ['20241002800232', '20241028800693', '20251215801442'])
    assert original['commonShares'] == '3209009'
    assert revised['commonShares'] == later['commonShares'] == '2040030'
    assert original['amountKrw'] != revised['amountKrw']
    assert original['reportedDecisionDate'] == '2024-10-02'
    assert later['reportedDecisionDate'] == '2025-05-08'
    assert all(x['completionStatus'] == 'NOT_OBSERVED' for x in (original, revised, later))


def test_original_and_correction_comparison_table_are_not_ambiguous_main_fields():
    revised = terms('20241028800693')
    assert revised['commonShares'] == '2040030'  # not comparison-table "before" 3209009
    raw = load_filing(ROOT / 'evidence', META['20241028800693'])
    with pytest.raises(ValueError, match='INPUT_HASH_MISMATCH'):
        version_terms(raw + b'changed', META['20241028800693'])


def test_duplicate_main_form_is_refused():
    raw = b'<table><tr><td>9. \xec\x9d\xb4\xec\x82\xac\xed\x9a\x8c\xea\xb2\xb0\xec\x9d\x98\xec\x9d\xbc(\xea\xb2\xb0\xec\xa0\x95\xec\x9d\xbc)</td><td>2026-01-01</td></tr></table>' * 2
    meta = {'report_nm': '주식소각결정', 'rcept_no': '20260102000001', 'rcept_dt': '20260102',
            'sha256': hashlib.sha256(raw).hexdigest()}
    with pytest.raises(ValueError, match='UNIQUE_MAIN_VERSION_FORM_REQUIRED'):
        version_terms(raw, meta)


def index_fixture(**change):
    row = dict(corp_code='SYN_ISSUER', rcept_no='20260102000001', rcept_dt='20260102',
               report_nm='주식소각결정')
    row.update(change)
    raw = gzip.compress(json.dumps(row).encode() + b'\n', mtime=0)
    blob = hashlib.sha1(f'blob {len(raw)}\0'.encode() + raw).hexdigest()
    family = {'versions': [{'receipt': '20260102000001', 'receiptDate': '2026-01-02',
                            'amendment': False, 'label': '2026.01.02 주식소각결정'}]}
    return raw, blob, family


def test_pinned_index_corroboration_does_not_authenticate_pit_security():
    raw, blob, family = index_fixture()
    r = corroborate_family_index(family, raw, issuer='SYN_ISSUER', expected_blob=blob)
    assert r['matchedVersionCount'] == 1
    assert not r['historicalSecurityIdentityVerified']
    assert not r['historicalPublicationClockVerified'] and not r['researchAdmission']


@pytest.mark.parametrize('change,reason', [
    ({'corp_code': 'OTHER'}, 'INDEX_ISSUER_MISMATCH'),
    ({'rcept_dt': '20260103'}, 'INDEX_MENU_DATE_MISMATCH'),
    ({'report_nm': '[정정]주식소각결정'}, 'INDEX_MENU_AMENDMENT_MISMATCH'),
    ({'rcept_no': '20260103000001'}, 'INDEX_FAMILY_RECEIPT_MISSING'),
    ({'report_nm': '단일판매ㆍ공급계약체결'}, 'INDEX_MENU_FAMILY_MISMATCH'),
])
def test_index_conflicts_are_not_silently_linked(change, reason):
    raw, blob, family = index_fixture(**change)
    with pytest.raises(ValueError, match=reason):
        corroborate_family_index(family, raw, issuer='SYN_ISSUER', expected_blob=blob)


def test_changed_index_bytes_are_refused_before_field_use():
    raw, blob, family = index_fixture()
    with pytest.raises(ValueError, match='PINNED_GIT_BLOB_MISMATCH'):
        corroborate_family_index(family, raw + b'changed', issuer='SYN_ISSUER', expected_blob=blob)


def test_duplicate_menu_rows_are_not_silently_collapsed():
    raw, blob, family = index_fixture()
    family['versions'] *= 2
    with pytest.raises(ValueError, match='UNIQUE_NONEMPTY_FAMILY_REQUIRED'):
        corroborate_family_index(family, raw, issuer='SYN_ISSUER', expected_blob=blob)
