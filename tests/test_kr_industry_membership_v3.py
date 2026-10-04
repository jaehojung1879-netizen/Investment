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


def test_listing_parser_requires_one_receipt_per_row_and_assigns_no_labels():
    html = ('<script>alert("x");</script><table><tr><td>1</td><td>2024-01-02 10:00</td><td>가</td>'
            "<td><a onclick=\"openDisclsViewer('20240102000123','')\">업종변경 안내</a></td><td>가</td></tr></table>")
    out = V.parse_kind_listing(html.encode())
    assert out['status'] == 'PARSED' and out['rows'][0]['receipt_no'] == '20240102000123'
    assert out['rows'][0]['families'] == ['INDUSTRY_CHANGE'] and 'before_label' not in out['rows'][0]
    assert V.parse_kind_listing(html.replace("openDisclsViewer('20240102000123','')", 'x').encode())['status'] == 'RECEIPT_ROW_MISMATCH'
    assert V.parse_kind_listing(b'<HTML><TITLE>Access Denied</TITLE>')['status'] == 'ACCESS_DENIED'
    real = (ROOT / 'data/kr-industry-membership-foundation-v3/events/42c2976acb7df0c9718b465c8c50d6c453875b6d2b82c0edc5f4388985caab33.bin').read_bytes()
    assert V.parse_kind_listing(real)['status'] == 'SOURCE_ERROR_PAGE'


def test_event_listing_protocol_is_frozen_windowed_within_the_source_span_limit():
    from datetime import date
    from scripts import collect_kr_industry_v3_events as E
    plan = E.load_frozen()
    for a, b in plan['windows']:
        assert (date.fromisoformat(b) - date.fromisoformat(a)).days < 3 * 366
    assert plan['windows'][0][0] == '2013-01-01' and plan['maxRequests'] <= 150 and plan['query']['currentPageSize'] == '15' and plan['retries'] == 0
