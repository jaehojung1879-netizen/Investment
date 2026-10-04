from pathlib import Path

import pytest
from pipeline import kr_industry_membership_v3 as V
from scripts import probe_kr_industry_v3_sources as P

ROOT = Path(__file__).resolve().parents[1]


def ev(date, before, after, **kw):
    return dict({'notice_date': date, 'before_label': before, 'after_label': after, 'source_sha256': 'a' * 64,
                 'identity_status': 'EXACT_ISSUER_SECURITY'}, **kw)


def test_protocol_is_frozen_and_bounded():
    plan = P.load_frozen()
    assert plan['maxRequests'] == len(plan['requests']) == 4 and plan['retries'] == 0 and not plan['outcomesAllowed']


def test_current_table_is_current_only_never_historical():
    html = '<table><tr><th>회사명</th><th>종목코드</th><th>업종</th></tr><tr><td>가</td><td>5930</td><td>통신업</td></tr></table>'.encode()
    out = V.parse_current_state(html, '2026-10-04')
    assert out['tier'] == V.CURRENT_TIER and not out['historicalAdmitted']
    assert out['rows'][0]['ticker'] == '005930' and out['rows'][0]['industry_label'] == '통신업'
    assert V.parse_current_state(b'<html>LOGOUT</html>', 'x')['reason'] == 'NO_TABLE'
    assert V.parse_current_state('<table><tr><th>회사명</th></tr></table>'.encode(), 'x')['reason'] == 'REQUIRED_COLUMNS_ABSENT'


def test_reconstruction_oldest_interval_is_not_pit():
    r = V.reconstruct('C', [ev('2020-01-01', 'A', 'B'), ev('2022-01-01', 'B', 'C')])
    assert r['status'] == 'RECONSTRUCTED'
    assert [(i['label'], i['status']) for i in r['intervals']] == [
        ('C', 'PIT_ADMISSIBLE_INTERVAL'), ('B', 'PIT_ADMISSIBLE_INTERVAL'), ('A', 'UNVERIFIED_START_NOT_PIT')]


def test_broken_chain_stops_instead_of_guessing():
    r = V.reconstruct('C', [ev('2020-01-01', 'A', 'B'), ev('2022-01-01', 'X', 'Z')])
    assert r['status'] == 'CHAIN_BREAK' and r['intervals'][-1]['label'] is None


@pytest.mark.parametrize('bad', [dict(before_label=None), dict(after_label=''), dict(notice_date='n/a'),
                                 dict(identity_status='NAME_MATCH'), dict(source_sha256=None)])
def test_event_without_stated_labels_date_or_identity_is_refused(bad):
    event = ev('2020-01-01', 'A', 'B')
    event.update(bad)
    assert V.valid_event(event)
    assert V.reconstruct('B', [event])['intervals'][0]['status'] == 'UNVERIFIED_START_NOT_PIT'


def test_title_match_is_reading_list_not_assignment():
    assert V.classify_disclosure_title('업종변경 안내') == ['INDUSTRY_CHANGE']
    assert 'before_label' not in V.classify_disclosure_title('합병 결정')
