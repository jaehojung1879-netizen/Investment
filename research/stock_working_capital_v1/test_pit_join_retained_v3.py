"""Invented retained-document joins. No financial originals, returns or model runs."""
import base64
from copy import deepcopy
import gzip
import json

import pytest

from . import pit_filing_evidence as E
from . import pit_join_retained_v3 as V3
from .test_pit_admission import main_body, meta, target, worker


class Sources:
    def __init__(self, files):
        self.files = files

    def blob(self, commit, path):
        assert commit == V3.J.EVIDENCE_COMMIT
        return self.files[path]


def retained(*, mutate=None):
    t = target(2024)
    raw = main_body(t) + b"<a onclick=\"openCorpInfoNew('12345678', 'winCorp');\">issuer</a>"
    receipt = t['receiptNos'][0]
    response = {'url': 'https://dart.fss.or.kr/dsaf001/main.do?rcpNo=' + receipt,
                'status': 200, 'sha256': E.sha(raw)}
    record = {'responses': [response]}
    bodies = {E.sha(raw): base64.b64encode(raw).decode()}
    if mutate:
        mutate(t, record, bodies)
    archive = gzip.compress(json.dumps(bodies).encode(), mtime=0)
    manifest = {'archive': 'batch-000.json.gz', 'archiveSha256': E.sha(archive), 'records': [record]}
    files = {V3.INVENTORY + '/batch-00/inventory.json': json.dumps([
        {'paginationComplete': True, 'selected': [t]}]).encode(),
        V3.V1 + '/manifest-000.json': json.dumps(manifest).encode(),
        V3.V1 + '/batch-000.json.gz': archive}
    return Sources(files), t, manifest


def load(source):
    return V3.supplement_originals(source, {}, inventory_batches=1, archive_batches=1)


def test_reused_v1_exact_selected_original_is_not_lost():
    source, t, _ = retained()
    originals, audit = load(source)
    key = (t['ticker'], t['fiscalYear'], t['receiptNos'][0])
    assert originals[key][0]['mainSha256']
    assert originals[key][0]['originalFinancialValuesVerified'] is False
    assert audit['addedExactSelectedOriginals'] == 1
    assert audit['newFinancialFactsCertified'] == 0


@pytest.mark.parametrize('field,value', [('corpCode', '87654321'), ('ticker', '654321.KS'),
                                        ('fiscalYear', 2023), ('availableFrom', '2025-03-01')])
def test_self_inconsistent_inventory_identity_never_joins(field, value):
    source, _, _ = retained(mutate=lambda t, r, b: t.update({field: value}))
    with pytest.raises(ValueError):
        load(source)


def test_listing_and_target_cannot_forge_the_issuer_in_original_bytes():
    def mutate(t, record, bodies):
        t['corpCode'] = t['listingMetadata']['corp_code'] = '87654321'
    source, _, _ = retained(mutate=mutate)
    with pytest.raises(ValueError, match='ORIGINAL_ISSUER_LINK_MISMATCH'):
        load(source)


def test_source_bodies_and_archive_hashes_are_enforced():
    source, _, _ = retained(mutate=lambda t, r, b: b.update({next(iter(b)): base64.b64encode(b'wrong').decode()}))
    with pytest.raises(ValueError, match='ORIGINAL_MAIN_BODY_DIGEST_MISMATCH'):
        load(source)
    source, _, manifest = retained()
    manifest['archiveSha256'] = '0' * 64
    source.files[V3.V1 + '/manifest-000.json'] = json.dumps(manifest).encode()
    with pytest.raises(ValueError, match='ORIGINAL_ARCHIVE_DIGEST_MISMATCH'):
        load(source)


def test_unselected_receipt_is_not_used_as_a_same_year_substitute():
    source, _, _ = retained(mutate=lambda t, r, b: r['responses'][0].update(
        {'url': 'https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20250321009999'}))
    originals, audit = load(source)
    assert originals == {} and audit['notSelectedReceipts'] == 1


def test_failed_acquisition_is_missing_evidence_not_a_success():
    source, _, _ = retained(mutate=lambda t, r, b: r['responses'][0].update({'status': 503}))
    originals, audit = load(source)
    assert originals == {} and audit['selectedOriginalsNotServed'] == 1


def test_duplicate_retained_copy_does_not_create_ambiguity_or_double_count():
    source, t, manifest = retained()
    manifest['records'].append(deepcopy(manifest['records'][0]))
    source.files[V3.V1 + '/manifest-000.json'] = json.dumps(manifest).encode()
    originals, audit = load(source)
    assert len(originals[(t['ticker'], t['fiscalYear'], t['receiptNos'][0])]) == 1
    assert audit['addedExactSelectedOriginals'] == 1


def test_conflicting_copy_never_overwrites_a_retained_original():
    source, t, _ = retained()
    key = (t['ticker'], t['fiscalYear'], t['receiptNos'][0])
    old = {key: [{'mainSha256': 'f' * 64}]}
    with pytest.raises(ValueError, match='CONFLICTING_RETAINED_ORIGINAL'):
        V3.supplement_originals(source, old, inventory_batches=1, archive_batches=1)
    assert old[key] == [{'mainSha256': 'f' * 64}]


def test_future_supplement_does_not_satisfy_earlier_filing_visibility():
    source, t, _ = retained()
    originals, _ = load(source)
    record = {'ticker': t['ticker'], 'corpCode': t['corpCode'], 'fiscalYear': t['fiscalYear'],
              'receiptNos': t['receiptNos'], 'availableFrom': t['availableFrom']}
    assert V3.A.filing_metadata(record, originals, '2025-03-01')[0] is None
    assert V3.A.filing_metadata(record, originals, '2025-04-01')[0] is not None


def test_real_join_reuses_original_but_does_not_admit_missing_financials_or_lose_terminated_member():
    source, _, _ = retained()
    prior = meta(2023)
    originals = {(prior['ticker'], prior['fiscalYear'], prior['receipt']): [prior]}
    c0, rows0 = worker(originals=originals, real_packages=False,
                       terminal={'345678.KS': '2025-03-20'}).on('2025-03-21')
    combined, _ = V3.supplement_originals(source, originals, inventory_batches=1, archive_batches=1)
    c1, rows1 = worker(originals=combined, real_packages=False,
                       terminal={'345678.KS': '2025-03-20'}).on('2025-03-21')
    assert c0 == c1 and len(rows0) == len(rows1) == 3
    assert rows0[0]['originalMainPairMatched'] is False
    assert rows1[0]['originalMainPairMatched'] is True and rows1[0]['datedIdentityMatched'] is True
    assert originals == {(prior['ticker'], prior['fiscalYear'], prior['receipt']): [prior]}
    for row in rows1:
        assert all(s['inputAdmitted'] is False and s['value'] is None for s in row['signals'].values())
    assert rows1[-1]['ticker'] == '345678.KS' and rows1[-1]['endedBySignal'] is True


def test_reused_filing_cannot_bridge_an_industry_notice_from_before_its_publication():
    source, _, _ = retained()
    originals, _ = load(source)
    event = {'ticker': '123456.KS', 'notice_date': '2025-03-01', 'identity': {'company': '테스트기업'}}
    assert V3.J.bridge_event_issuer(event, originals)['issuerCorpCode'] is None


@pytest.mark.parametrize('path', ['ledger/historical/replay-v16/outcomes.jsonl.gz',
                                 V3.V1 + '/../secret', V3.V1 + '/manifest-021.json',
                                 V3.V1 + '/arbitrary-original.zip'])
def test_supplement_reader_refuses_non_allowlisted_paths_before_io(tmp_path, monkeypatch, path):
    def fail(*args, **kwargs):
        raise AssertionError('No subprocess is allowed')
    monkeypatch.setattr(V3.J.subprocess, 'run', fail)
    with pytest.raises(ValueError, match='REFUSED'):
        V3.RetainedInputs(tmp_path).blob(V3.J.EVIDENCE_COMMIT, path)
