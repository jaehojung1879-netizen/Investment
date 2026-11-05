"""Actual byte fixtures plus synthetic safety mutations; never an alpha test."""
import json
from pathlib import Path

import pytest

from research.corporate_event_readiness_v1.filings import as_of_chain, number, parse_filing

EVIDENCE = Path(__file__).resolve().parents[1] / 'research/corporate_event_readiness_v1/evidence'
SAMPLES = json.loads((EVIDENCE / 'filing-samples.json').read_text())['samples']


def parsed(no):
    meta = next(m for m in SAMPLES if m['rcept_no'] == no)
    return parse_filing((EVIDENCE / meta['file']).read_bytes(), meta)


@pytest.mark.parametrize('meta', SAMPLES, ids=lambda m: m['rcept_no'])
def test_real_bytes_hash_and_fail_closed_admission(meta):
    raw = (EVIDENCE / meta['file']).read_bytes()
    result = parse_filing(raw, meta)
    assert 'INPUT_HASH_MISMATCH' not in result['quarantine_reasons']
    assert result['family'] and result['raw_table_rows']
    assert result['receipt_at'] is None and result['pit_available_at'] is None
    assert result['data_eligibility'] == 'BLOCKED' and not result['economic_study_ready']
    assert result['completion_status'] == 'NOT_OBSERVED'
    assert result['tradable_security_at_event'] is None
    assert result['source_version_verified'] is False


def test_buyback_quantity_decision_period_and_denominator_not_holdings_ratio():
    r = parsed('20121112800006')
    assert r['quantity_common'] == '481277'
    assert r['amount_krw'] == '125132020000'
    assert r['decision_date'] == '2012-11-09'
    assert r['receipt_date'] == '2012-11-12'
    assert r['expected_execution_start'] == '2012-11-13'
    assert r['expected_execution_end'] == '2013-02-12'
    assert r['share_ratio_pct'] is None  # 8.57% is EXISTING treasury holdings.


def test_supply_uses_contemporaneous_revenue_not_latest():
    r = parsed('20200302800563')
    assert r['contract_amount_krw'] == '67100000000'
    assert r['recent_revenue_krw'] == '1547803760412'
    assert r['revenue_fiscal_year'] == 2018  # not receipt year minus one
    assert r['revenue_basis'] == '연결'
    assert r['reported_contract_ratio_pct'] == '4.34'
    assert r['contract_start'] == '2020-04-01'
    assert r['contract_end'] == '2022-12-31'
    assert r['counterparty'] == '메리츠화재해상보험(주)'
    assert r['counterparty_country'] is None


def test_unknown_revenue_year_abstains():
    r = parsed('20130424800010')
    assert r['revenue_fiscal_year'] is None
    assert 'REVENUE_FISCAL_YEAR_NOT_EXPLICIT' in r['quarantine_reasons']


def test_subsidiary_cannot_be_parent_dilution():
    r = parsed('20170531800614')
    assert r['quantity_common'] == '5259600'
    assert r['issued_shares_common_at_decision'] == '400'
    assert 'SUBSIDIARY_EVENT_SECURITY_UNRESOLVED' in r['quarantine_reasons']


def test_cancellation_is_a_decision_not_completion():
    r = parsed('20241002800232')
    assert r['quantity_common'] == '3209009'
    assert r['issued_shares_common_at_decision'] == '20703283'
    assert r['expected_execution_start'] is None  # acquisition period is not cancellation execution
    assert r['completion_status'] == 'NOT_OBSERVED'
    assert 'INDEX_MARKS_AMENDMENTS_HISTORICAL_BODY_VERSION_UNVERIFIED' in r['quarantine_reasons']


def test_trust_and_debt_forms_have_no_invented_share_count():
    trust = parsed('20170427800211')
    assert trust['amount_krw'] == '5000000000'
    assert trust['quantity_common'] is None
    assert trust['expected_execution_start'] == '2017-04-27'
    assert parsed('20160217800701')['amount_krw'] == '7900000000'
    eb = parsed('20260911800557')
    assert eb['amount_krw'] == '500000000000'
    assert eb['quantity_common'] == '1851851'


def test_amendment_and_termination_do_not_overwrite_original():
    r = parsed('20261030800168')
    assert r['amendment'] and r['chain_status'] == 'UNRESOLVED'
    assert r['changes'] and r['chain_parent_receipt'] is None
    assert r['contract_amount_krw'] == '308560797394'
    assert r['revenue_fiscal_year'] == 2023
    termination = parsed('20191002800414')
    assert termination['family'] == 'TERMINATION'
    assert termination['chain_parent_receipt'] is None


def test_hash_tamper_and_bad_form_quarantine():
    m = SAMPLES[0]
    assert parse_filing(b'changed', m)['quarantine_reasons'] == ['INPUT_HASH_MISMATCH']
    r = parse_filing(b'<html>error</html>', {'report_nm': '자기주식취득결정'})
    assert r['parse_status'] == 'QUARANTINED'
    assert number('1,234') == '1234' and number('not a value') is None


def test_required_fields_and_negative_amount_are_not_complete_parse():
    raw = '<table><tr><td>2. 계약금액(원)</td><td>-20</td></tr></table>'.encode()
    r = parse_filing(raw, {'report_nm': '단일판매ㆍ공급계약체결'})
    assert r['parse_status'] != 'PARSED'
    assert 'NEGATIVE_VALUE:contract_amount_krw' in r['quarantine_reasons']


def test_asof_timestamp_offsets_future_version_and_nested_immutability():
    versions = [
        {'pit_available_at': '2020-01-01T09:00:00+09:00', 'changes': ['original']},
        {'pit_available_at': '2020-01-01T00:00:00.001Z', 'changes': ['later']},
        {'pit_available_at': None, 'changes': ['unknown']},
    ]
    out = as_of_chain(versions, '2020-01-01T00:00:00Z')
    assert len(out) == 1
    out[0]['changes'].append('mutation')
    assert versions[0]['changes'] == ['original']
    with pytest.raises(ValueError, match='AWARE_TIMESTAMP_REQUIRED'):
        as_of_chain(versions, '2020-01-01')


def test_same_issuer_and_date_does_not_link_distinct_contracts():
    original_candidate = parsed('20141224800064')
    termination = parsed('20191002800414')
    assert original_candidate['contract_name'] == '가좌주공 2단지 주택재건축 정비사업'
    assert termination['contract_name'] == '두산연구단지 설계 및 신축공사(T/K)'
    assert original_candidate['contract_name'] != termination['contract_name']
    assert termination['chain_parent_receipt'] is None
