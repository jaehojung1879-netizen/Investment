"""Synthetic tests for the outcome-free corporate-event cohort (no network, no prices)."""
from __future__ import annotations

import gzip
import json

import pytest

from research.corporate_event_readiness_v1.cohort import events as E
from research.corporate_event_readiness_v1.cohort.bodies import amendment_reference
from research.corporate_event_readiness_v1.cohort.dart_client import DartClient, DartRefusal, request_id
from research.corporate_event_readiness_v1.cohort.families import classify_title, is_subsidiary_report
from research.corporate_event_readiness_v1.cohort.identity import PitTop300, load_snapshots
from research.corporate_event_readiness_v1.cohort.power import gate, mde, power_table

SESSIONS = [f'2020-01-{d:02d}' for d in range(2, 32)] + [f'2020-02-{d:02d}' for d in range(1, 29)]


def pit():
    return PitTop300({'2020-01-01': {'000001': 'A', '000002': 'B'}, '2020-02-01': {'000001': 'A'}})


def row(no, day, fam, title, code='000001', corp='C1', rm=''):
    return {'rcept_no': no, 'rcept_dt': day.replace('-', ''), 'corp_code': corp, 'stock_code': code,
            'family': fam, 'report_nm': title, 'rm': rm}


def body(**terms):
    return {'parsed': {'quarantine_reasons': [], **terms}, 'amendmentRef': None, 'error': None}


def test_title_families_prefer_longest_keyword():
    assert classify_title('주요사항보고서(자기주식취득결정)') == 'BUYBACK'
    assert classify_title('주요사항보고서(자기주식취득신탁계약체결결정)') == 'TRUST'
    assert classify_title('주요사항보고서(자기주식취득신탁계약해지결정)') == 'TRUST_TERMINATION'
    assert classify_title('단일판매ㆍ공급계약체결(자율공시)') == 'SUPPLY'
    assert classify_title('단일판매ㆍ공급계약해지') == 'TERMINATION'
    assert classify_title('주식소각결정') == 'CANCELLATION'
    assert classify_title('최대주주변경') is None
    assert is_subsidiary_report('단일판매ㆍ공급계약체결(자회사의 주요경영사항)')


def test_identity_uses_snapshot_strictly_before_receipt():
    p = pit()
    assert p.membership('000002', '2020-02-01')['snapshot'] == '2020-01-01'
    assert p.membership('000002', '2020-02-01')['status'] == 'PIT_TOP300_MEMBER'
    assert p.membership('000002', '2020-02-02')['status'] == 'NOT_IN_PIT_TOP300'
    assert p.membership('000001', '2019-12-31')['status'] == 'NO_PRIOR_SNAPSHOT'
    assert p.membership('', '2020-01-15')['status'] == 'STOCK_CODE_ABSENT_IN_INDEX'


def test_load_snapshots_reads_only_identity(tmp_path):
    rows = [{'date': '2020-01-01', 'code': '000001', 'name': 'A', 'marketCap': 1.0}]
    (tmp_path / 'krx-universe-2020.jsonl.gz').write_bytes(
        gzip.compress('\n'.join(json.dumps(r) for r in rows).encode()))
    assert load_snapshots(tmp_path) == {'2020-01-01': {'000001': 'A'}}


@pytest.mark.parametrize('purpose,expected', [
    ('이익소각', 'CANCELLATION_STATED'), ('주가안정 및 주주가치 제고', 'SHAREHOLDER_VALUE'),
    ('임직원 성과보상', 'EMPLOYEE'), ('합병 대가 지급', 'CORPORATE_ACTION'), (None, 'NOT_STATED')])
def test_purpose_classes(purpose, expected):
    assert E.purpose_class(purpose) == expected


def test_classification_uses_filed_terms_only():
    assert E.classify(row('1', '2020-01-10', 'CANCELLATION', '주식소각결정'),
                      {'quantity_common': '10', 'issued_shares_common_at_decision': '100'})[0] == 'A1'
    assert E.classify(row('1', '2020-01-10', 'CANCELLATION', '주식소각결정'),
                      {'quantity_other': '10'})[1] == 'CANCELLATION_OTHER_CLASS_ONLY'
    assert E.classify(row('1', '2020-01-10', 'BUYBACK', 'x'),
                      {'quantity_common': '5', 'purpose': '이익 소각'})[0] == 'A1'
    assert E.classify(row('1', '2020-01-10', 'BUYBACK', 'x'),
                      {'quantity_common': '5', 'purpose': '주가안정'})[0] == 'A2'
    assert E.classify(row('1', '2020-01-10', 'BUYBACK', 'x'),
                      {'quantity_common': '5', 'purpose': '임직원 보상'})[0] is None
    big = {'contract_amount_krw': '20', 'recent_revenue_krw': '100', 'reported_contract_ratio_pct': '20.0',
           'quarantine_reasons': []}
    assert E.classify(row('1', '2020-01-10', 'SUPPLY', 'x'), big)[0] == 'B1'
    small = {**big, 'reported_contract_ratio_pct': '9.99'}
    assert E.classify(row('1', '2020-01-10', 'SUPPLY', 'x'), small)[1] == 'SUPPLY_BELOW_10PCT_REVENUE'
    bad = {**big, 'quarantine_reasons': ['CONTRACT_RATIO_MISMATCH']}
    assert E.classify(row('1', '2020-01-10', 'SUPPLY', 'x'), bad)[1] == 'SUPPLY_RATIO_MISMATCH'


def run(rows, bodies, cutoff='2020-02-28', as_of='2020-02-28'):
    return E.build(rows, pit(), bodies, E.Calendar(SESSIONS), data_cutoff=cutoff, as_of=as_of)


def test_signal_is_first_session_after_receipt_and_entry_the_next():
    rows = [row('a', '2020-01-10', 'CANCELLATION', '주식소각결정')]
    out = run(rows, {'a': body(quantity_common='1', issued_shares_common_at_decision='10')})
    v = out['candidates'][0]
    assert (v['signalSession'], v['entrySession']) == ('2020-01-11', '2020-01-12')
    assert v['pitGrade'] == 'DATE_ONLY_CONSERVATIVE'


def test_every_version_stops_once_with_first_failing_gate():
    rows = [row('x1', '2012-12-31', 'BUYBACK', 'x'),
            row('x2', '2020-01-10', 'BUYBACK', '[기재정정]주요사항보고서(자기주식취득결정)', corp='C9'),
            row('x3', '2020-01-10', 'SUPPLY', '단일판매ㆍ공급계약체결(자회사의 주요경영사항)'),
            row('x4', '2020-01-10', 'BUYBACK', 'x', code='999999'),
            row('x5', '2020-01-10', 'RIGHTS', '유상증자결정'),
            row('x6', '2020-01-10', 'BUYBACK', 'x')]
    out = run(rows, {})
    stops = {v['rcept_no']: v['stoppedAt'] for v in out['versions']}
    assert stops == {'x1': 'IN_PERIOD', 'x2': 'ORIGINAL_VERSION', 'x3': 'NOT_SUBSIDIARY_REPORT',
                     'x4': 'PIT_TOP300_IDENTITY', 'x5': 'BODY_FAMILY', 'x6': 'BODY_RETRIEVED'}
    assert sum(out['stageCounts'].values()) == len(rows)


def test_pre_entry_amendment_excludes_only_with_pre_entry_information():
    original = row('o', '2020-01-10', 'SUPPLY', '단일판매ㆍ공급계약체결')
    terms = body(contract_amount_krw='20', recent_revenue_krw='100', reported_contract_ratio_pct='20')
    linked = row('m', '2020-01-11', 'SUPPLY', '[기재정정]단일판매ㆍ공급계약체결')
    stated = {'parsed': None, 'error': None,
              'amendmentRef': {'status': 'STATED', 'referencedFirstFilingDay': '2020-01-10'}}
    out = run([original, linked], {'o': terms, 'm': stated})
    stops = {v['rcept_no']: v['stoppedAt'] for v in out['versions']}
    assert stops == {'o': 'NO_PRE_ENTRY_AMENDMENT', 'm': 'ORIGINAL_VERSION'}
    assert out['candidates'] == []
    # An amendment that states a DIFFERENT original is not linked.
    other = {**stated, 'amendmentRef': {'status': 'STATED', 'referencedFirstFilingDay': '2019-05-01'}}
    out = run([original, linked], {'o': terms, 'm': other})
    assert [v['rcept_no'] for v in out['candidates']] == ['o']
    # A post-entry amendment never removes the event (intention to treat).
    late = row('m', '2020-01-20', 'SUPPLY', '[기재정정]단일판매ㆍ공급계약체결')
    out = run([original, late], {'o': terms, 'm': stated})
    assert [v['rcept_no'] for v in out['candidates']] == ['o']


def test_issuer_embargo_counts_one_independent_event_per_window():
    terms = body(quantity_common='1', issued_shares_common_at_decision='10')
    rows = [row('e1', '2020-01-02', 'CANCELLATION', '주식소각결정'),
            row('e2', '2020-01-06', 'CANCELLATION', '주식소각결정'),
            row('e3', '2020-01-06', 'CANCELLATION', '주식소각결정', code='000002', corp='C2')]
    out = E.build(rows, pit(), {r: terms for r in ('e1', 'e2', 'e3')}, E.Calendar(SESSIONS),
                  data_cutoff='2020-02-28', as_of='2020-02-28')
    kept = {v['rcept_no'] for v in out['independent'][('A1', 126)]}
    assert kept == {'e1', 'e3'}
    d = E.describe(out['independent'][('A1', 126)], 126, SESSIONS)
    assert d['N'] == 2 and d['issuers'] == 2 and d['matured'] == 0


def test_amendment_reference_reads_stated_fields_only():
    html = ('<table><tr><td>1. 정정관련 공시서류</td><td>단일판매ㆍ공급계약 체결</td></tr>'
            '<tr><td>2. 정정관련 공시서류제출일</td><td>2013.05.02</td></tr>'
            '<tr><td>3. 정정사유</td><td>계약금액 증액</td></tr></table>').encode('cp949')
    ref = amendment_reference(html)
    assert ref == {'referencedTitle': '단일판매ㆍ공급계약 체결', 'referencedFirstFilingDay': '2013-05-02',
                   'reason': '계약금액 증액', 'status': 'STATED'}
    assert amendment_reference(b'<table><tr><td>x</td></tr></table>')['status'] == 'NOT_STATED_IN_BODY'


def test_power_is_conditional_and_monotone():
    assert mde(20, 1, 1) is None and gate(None, 3) == 'NO_EVENTS'
    assert mde(20, 400, 2) < mde(20, 100, 2) < mde(20, 100, 4)
    table = power_table({'A1_H126': {'N': 100}, 'A1_H252': {'N': 0}})
    assert table['status'].startswith('CONDITIONAL')
    assert {r['gate'] for r in table['rows'] if r['set'] == 'A1_H252'} == {'NO_EVENTS'}


def test_client_never_records_key_and_refuses_offline_miss(tmp_path, monkeypatch):
    assert 'crtfc_key' not in request_id('list.json', {'crtfc_key': 'SECRET', 'page_no': 1})
    client = DartClient(tmp_path, key='SECRET', offline=True)
    with pytest.raises(DartRefusal, match='OFFLINE_CACHE_MISS'):
        client.get('list.json', {'page_no': 1})
    assert not any('SECRET' in p.read_text(errors='ignore') for p in tmp_path.rglob('*') if p.is_file())


def test_candidate_signal_cannot_be_promoted_without_external_evidence():
    from research.corporate_event_readiness_v1.cohort.candidate_signal import HypothesisEvidence, classify_signal
    event = {'rcept_no': '1', 'corp_code': 'C', 'stock_code': '000001', 'family': 'CANCELLATION',
             'eventType': 'CANCELLATION_DECISION_COMMON', 'hypothesis': 'A1', 'receiptDay': '2020-01-10',
             'entrySession': '2020-01-14', 'pitGrade': 'DATE_ONLY_CONSERVATIVE'}
    assert classify_signal(event)['state'] == 'EXPLORATORY'
    assert classify_signal({**event, 'hypothesis': 'A2'})['state'] == 'NOT_ADMITTED'
    assert classify_signal({**event, 'pitGrade': None})['state'] == 'NOT_ADMITTED'
    hist = HypothesisEvidence('ab' * 32, True, 'DEVELOPMENT_SUPPORT')
    assert classify_signal(event, hist)['state'] == 'PROSPECTIVE_CANDIDATE'
    done = HypothesisEvidence('ab' * 32, True, 'DEVELOPMENT_SUPPORT', 'SUPPORT', True)
    assert classify_signal(event, done)['state'] == 'VERIFIED'
    out = classify_signal(event, HypothesisEvidence('ab' * 32, True, 'UNCERTAIN', 'SUPPORT', True))
    assert out['state'] == 'EXPLORATORY'
    assert all(k not in out for k in ('weight', 'weights', 'position', 'targetWeight'))


def test_dsd_value_elements_become_cells_without_touching_other_bytes():
    from research.corporate_event_readiness_v1.cohort.bodies import as_table_cells, parse_body
    raw = ('<TABLE><TR><TD>1. 취득예정주식(주)</TD><TD>보통주식</TD>'
           '<TE ACODE="ACQ_OSTK">698,293</TE></TR><TR><TD>5. 취득목적</TD>'
           '<TE ACODE="ACQ_PP">이익소각</TE></TR><TR><TD>9. 취득결정일</TD>'
           '<TU AUNIT="ACQ_DD" AUNITVALUE="20211228">2021년 12월 28일</TU></TR></TABLE>').encode('cp949')
    cells, converted = as_table_cells(raw)
    assert converted and b'<TE' not in cells and b'<TU' not in cells and cells.count(b'<TD') == 7
    parsed = parse_body(raw, {'rcept_no': '20211228000464', 'report_nm': '주요사항보고서(자기주식취득결정)',
                              'rcept_dt': '20211228'})
    assert parsed['quantity_common'] == '698293' and parsed['purpose'] == '이익소각'
    assert parsed['parser_variant'].endswith('+dsd-te-tu-as-cells-v1')
    assert E.classify({'family': 'BUYBACK'}, parsed)[0] == 'A1'
    assert as_table_cells(b'<td>x</td>')[1] is False


def test_body_flags_are_self_statements_only():
    from research.corporate_event_readiness_v1.cohort.bodies import body_flags
    progress = '<table><tr><td>1. 제목</td><td>단일판매·공급계약 체결 건의 진행사항 공시</td></tr></table>'.encode('cp949')
    assert body_flags(progress) == ['PROGRESS_UPDATE_OF_EARLIER_CONTRACT']
    withheld = '<table><tr><td>유보사유</td><td>영업비밀</td></tr></table>'.encode('cp949')
    assert body_flags(withheld) == ['TERMS_WITHHELD_UNTIL_LATER_DISCLOSURE']
    none = '<table><tr><td>유보사유</td><td>-</td></tr></table>'.encode('cp949')
    assert body_flags(none) == []
    assert E.classify({'family': 'SUPPLY'}, {'cohort_flags': ['PROGRESS_UPDATE_OF_EARLIER_CONTRACT']})[1] == \
        'SUPPLY_PROGRESS_UPDATE_LATER_STATE'
    assert E.classify({'family': 'SUPPLY'}, {'cohort_flags': ['TERMS_WITHHELD_UNTIL_LATER_DISCLOSURE']})[1] == \
        'SUPPLY_TERMS_WITHHELD_AT_SIGNAL'


def test_document_status_014_is_an_explicit_cached_answer(tmp_path, monkeypatch):
    import io
    from research.corporate_event_readiness_v1.cohort import dart_client
    from research.corporate_event_readiness_v1.cohort.bodies import DocumentNotServed, document_body
    payload = ('<?xml version="1.0" encoding="UTF-8"?><result><status>014</status>'
               '<message>파일이 존재하지 않습니다.</message></result>').encode()

    class Response(io.BytesIO):
        headers = {'Content-Type': 'application/xml'}

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    calls = []
    monkeypatch.setattr(dart_client.urllib.request, 'urlopen',
                        lambda url, timeout: calls.append(url) or Response(payload))
    client = DartClient(tmp_path, key='K')
    with pytest.raises(DocumentNotServed):
        document_body(client, '20140203000264')
    offline = DartClient(tmp_path, key='K', offline=True)
    with pytest.raises(DocumentNotServed):
        document_body(offline, '20140203000264')
    assert len(calls) == 1


def test_price_presence_keeps_only_ticker_date_traded(tmp_path):
    from research.corporate_event_readiness_v1.cohort.admission import load_presence
    rows = [{'ticker': '000001.KS', 'date': '2020-01-02', 'close': 1.0, 'open': 1.0, 'volume': 10},
            {'ticker': '000001.KS', 'date': '2020-01-03', 'close': 9.0, 'volume': 0}]
    (tmp_path / 'krx-prices-2020.jsonl.gz').write_bytes(
        gzip.compress('\n'.join(json.dumps(r) for r in rows).encode()))
    presence, meta = load_presence(tmp_path)
    assert presence == {'000001.KS': {'2020-01-02': True, '2020-01-03': False}}
    assert 'close' in meta['fieldsDiscardedAtParse'] and meta['fieldsKept'] == ['ticker', 'date', 'traded']


@pytest.mark.parametrize('bars,expected', [
    (None, 'NO_PRICE_SOURCE'),
    ({d: True for d in SESSIONS[:6]}, 'FULL_WINDOW_TRADED'),
    ({**{d: True for d in SESSIONS[:6]}, SESSIONS[3]: False}, 'SUSPENSION_OR_GAP_IN_WINDOW'),
    ({d: True for d in SESSIONS[:4]}, 'ENDS_BEFORE_MATURITY_TERMINAL_ECONOMICS_REQUIRED'),
    ({SESSIONS[1]: False, **{d: True for d in SESSIONS[2:6]}}, 'ENTRY_NOT_TRADED'),
])
def test_window_admission_is_a_source_fact_not_a_return(bars, expected):
    from research.corporate_event_readiness_v1.cohort.admission import window_admission
    assert window_admission(bars, SESSIONS, SESSIONS[1], 4, SESSIONS[-1])['status'] == expected
    assert window_admission({SESSIONS[1]: True}, SESSIONS, SESSIONS[1], 4, SESSIONS[2])['status'] == \
        'PENDING_MATURITY_OR_LEDGER_END'


def test_build_period_parameter_leaves_historical_default_unchanged():
    terms = body(quantity_common='1', issued_shares_common_at_decision='10')
    rows = [row('p', '2020-01-10', 'CANCELLATION', '주식소각결정')]
    assert run(rows, {'p': terms})['candidates']
    out = E.build(rows, pit(), {'p': terms}, E.Calendar(SESSIONS), data_cutoff='2020-02-28',
                  as_of='2020-02-28', period=('2020-01-11', '2099-12-31'))
    assert out['stageCounts'] == {'IN_PERIOD': 1}


def test_prospective_receipt_is_dry_run_only_and_digest_bound(tmp_path):
    from pipeline import prospective_receipt_core as core
    from research.corporate_event_readiness_v1.cohort import prospective as P
    receipt = P.session_receipt('2020-01-10', [], spec_sha256='ab' * 32, created_at_utc='2020-01-10T10:00:00+00:00',
                                sources=[], mode='DRY_RUN')
    assert receipt['evidenceClass'] == P.DRY_RUN_CLASS != core.EVIDENCE_CLASS
    assert receipt['receiptSha256'] == core.receipt_digest(receipt)
    with pytest.raises(ValueError, match='ONLY_DRY_RUN'):
        P.session_receipt('2020-01-10', [], spec_sha256='ab' * 32, created_at_utc='x', sources=[], mode='LIVE')
    with pytest.raises(ValueError, match='DRY_RUN_CANNOT_CLAIM'):
        P.validate({**receipt, 'evidenceClass': core.EVIDENCE_CLASS})
    with pytest.raises(ValueError, match='OUTCOME_FIELD'):
        P.validate({**{k: v for k, v in receipt.items() if k != 'receiptSha256'}, 'forwardReturn': 1})
    assert P.REGISTERED_AUTHORIZATION is None


def test_prospective_store_guard(tmp_path):
    from pathlib import Path
    from research.corporate_event_readiness_v1.cohort import prospective as P
    repo = Path(P.__file__).resolve().parents[3]
    with pytest.raises(ValueError, match='OUTSIDE_REPOSITORY'):
        P.checked_store(repo / 'research', repo)
    with pytest.raises(ValueError, match='MARKER_REQUIRED'):
        P.checked_store(tmp_path, repo)
    (tmp_path / P.STORE_MARKER).write_text('')
    assert P.checked_store(tmp_path, repo) == tmp_path.resolve()


def test_receipt_days_map_each_day_to_exactly_one_signal_session():
    from research.corporate_event_readiness_v1.cohort import prospective as P
    sessions = ['2020-01-02', '2020-01-03', '2020-01-06']
    assert P.receipt_days_for('2020-01-06', sessions) == ['2020-01-03', '2020-01-04', '2020-01-05']
    assert P.receipt_days_for('2020-01-03', sessions) == ['2020-01-02']
