"""Share counts are source facts; unclassified totals cannot become common denominators."""
import hashlib
import json
from pathlib import Path

import pytest

from research.corporate_event_readiness_v1.filings import capital_share_terms, load_filing

ROOT = Path(__file__).resolve().parents[1] / 'research/corporate_event_readiness_v1/evidence'
META = {}
for filename in ('filing-samples.json', 'chain-body-samples-v1.json'):
    META.update({row['rcept_no']: row for row in json.loads((ROOT / filename).read_text())['samples']})


def actual(receipt):
    return capital_share_terms(load_filing(ROOT, META[receipt]), META[receipt])


def synthetic(quantity='200', denominator='1000', share_class='보통주식 (주)', notes=''):
    raw = (f'<table><tr><td>1. 소각할 주식의 종류와 수</td><td>보통주식 (주)</td><td>{quantity}</td></tr>'
           f'<tr><td>2. 발행주식 총수</td><td>{share_class}</td><td>{denominator}</td></tr>'
           '<tr><td>9. 이사회결의일(결정일)</td><td>2026-01-02</td></tr>'
           f'<tr><td>11. 기타 투자판단에 참고할 사항</td><td>{notes}</td></tr></table>').encode()
    meta = {'rcept_no': '20260103000001', 'rcept_dt': '20260103',
            'corp_code': 'SYN_ISSUER', 'report_nm': '주식소각결정',
            'sha256': hashlib.sha256(raw).hexdigest()}
    return raw, meta


def test_all_six_cancellation_versions_preserve_common_share_evidence():
    rows = [actual(no) for no in META if META[no]['corp_code'] == '00102858']
    assert len(rows) == 6
    assert {r['reportedIssuedCommonShares']['value'] for r in rows} == {'20703283'}
    assert actual('20241002800232')['plannedCommonShares']['value'] == '3209009'
    assert actual('20241028800693')['plannedCommonShares']['value'] == '2040030'
    for row in rows:
        assert not row['denominatorAtDecisionVerified'] and not row['historicalVersionAuthenticated']
        assert not row['researchAdmission'] and not row['outcomeExecutionAuthorized']
        assert row['completionStatus'] == 'NOT_OBSERVED' and not row['shareRatioComputed']


def test_explicit_old_note_total_is_retained_without_inverting_holdings_ratio():
    row = actual('20121112800006')
    note = row['reportedUnclassifiedIssuedShares']
    assert note['value'] == '48127704' and note['shareClass'] == 'UNSPECIFIED'
    assert not note['commonDenominatorEligible']
    assert row['reportedIssuedCommonShares']['value'] is None
    assert '8.57' not in note['sourceQuote']
    assert row['plannedCommonShares']['value'] == '481277'
    assert not row['shareRatioComputed']


def test_subsidiary_quantity_never_authenticates_parent_security():
    row = actual('20260804800356')
    assert row['plannedCommonShares']['value'] == '294447'
    assert row['subsidiaryEvent'] and row['tradableSecurityAtEvent'] is None
    assert not row['issuerSecurityVerified'] and not row['researchAdmission']
    assert row['reportedIssuedCommonShares']['value'] is None


@pytest.mark.parametrize('share_class', ['종류주식 (주)', '우선주식 (주)', '합계', '보통주식 (천주)'])
def test_preferred_total_or_other_unit_cannot_become_common_denominator(share_class):
    raw, meta = synthetic(share_class=share_class)
    row = capital_share_terms(raw, meta)
    assert row['reportedIssuedCommonShares']['value'] is None
    assert row['reportedIssuedCommonShares']['sourceRow'][1] == share_class
    assert row['reportedIssuedCommonShares']['shareClass'] == 'UNVERIFIED'


@pytest.mark.parametrize('quantity,denominator,reason', [
    ('-1', '1000', 'WHOLE_NONNEGATIVE_SHARES_REQUIRED'),
    ('1.5', '1000', 'WHOLE_NONNEGATIVE_SHARES_REQUIRED'),
    ('1,23', '1000', 'WHOLE_NONNEGATIVE_SHARES_REQUIRED'),
    ('200', '0', 'POSITIVE_COMMON_SHARE_DENOMINATOR_REQUIRED'),
    ('1001', '1000', 'PLANNED_SHARES_EXCEED_REPORTED_COMMON_TOTAL'),
])
def test_invalid_or_inconsistent_share_counts_are_refused(quantity, denominator, reason):
    raw, meta = synthetic(quantity=quantity, denominator=denominator)
    with pytest.raises(ValueError, match=reason):
        capital_share_terms(raw, meta)


def test_rounded_existing_treasury_ratio_is_never_a_denominator_source():
    raw, meta = synthetic(denominator='-', notes='직접소유주식 4,126,169주 비율 8.57%')
    row = capital_share_terms(raw, meta)
    assert row['reportedIssuedCommonShares']['value'] is None
    assert row['reportedUnclassifiedIssuedShares'] is None


@pytest.mark.parametrize('note,reason', [
    ('발행주식총수 * 1% : 10주 : 999주 * 1% = 10주', 'INCONSISTENT_ORDER_LIMIT_SHARE_NOTE'),
    ('발행주식총수 * 1% : 10주 : 1000주 * 1% = 10주 ' * 2, 'AMBIGUOUS_EXPLICIT_SHARE_TOTAL_NOTE'),
])
def test_inconsistent_or_ambiguous_note_is_not_selected(note, reason):
    raw, meta = synthetic(notes=note)
    with pytest.raises(ValueError, match=reason):
        capital_share_terms(raw, meta)


def test_duplicate_class_field_and_changed_original_bytes_are_refused():
    raw, meta = synthetic()
    duplicate = raw.replace(b'</table>', '<tr><td>2. 발행주식 총수</td><td>보통주식 (주)</td><td>1000</td></tr></table>'.encode())
    with pytest.raises(ValueError, match='INPUT_HASH_MISMATCH'):
        capital_share_terms(duplicate, meta)
    meta['sha256'] = hashlib.sha256(duplicate).hexdigest()
    with pytest.raises(ValueError, match='AMBIGUOUS_SHARE_CLASS_FIELD'):
        capital_share_terms(duplicate, meta)
