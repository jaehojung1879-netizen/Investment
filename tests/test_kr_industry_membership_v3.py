import hashlib
import json
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


def test_retained_listing_and_current_anchor_support_only_the_documented_scope():
    m = json.loads((ROOT / 'data/kr-industry-membership-foundation-v3/events-rev4/manifest.json').read_text())
    assert (m['requests'], m['listedRows'], m['uniqueReceipts']) == (67, 968, 968) and not m['labelsAssigned']
    assert all(r['families'] == ['INDUSTRY_CHANGE'] and 'before_label' not in r for r in m['rows'])
    assert m['listedRows'] > 400  # frozen rule: the document stage stops and reports above 400 hits
    probe = ROOT / 'data/kr-industry-membership-foundation-v3/probe/run-37170219625'
    raw = (probe / 'e67bc8d33c47c0013d6e31bfc62897d049ad6fadac9013261c8bc100a4380d58.bin').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == 'e67bc8d33c47c0013d6e31bfc62897d049ad6fadac9013261c8bc100a4380d58'
    anchor = V.parse_current_state(raw, '2026-10-04')
    assert len(anchor['rows']) == 2802 and anchor['tier'] == V.CURRENT_TIER and not anchor['historicalAdmitted']


def test_notice_candidates_are_frozen_name_candidates_only():
    from scripts import collect_kr_industry_v3_notices as N
    cands, protocol = N.frozen()
    assert cands['candidateCount'] == len(cands['candidates']) == 81 and cands['listedNotices'] == 968
    assert all(c['identity_status'].startswith('NAME_CANDIDATE_ONLY') for c in cands['candidates'])
    assert protocol['retries'] == 0 and protocol['maxRequests'] >= 81 and not protocol['outcomesAllowed']


def evt(eff, before, after, notice=None):
    return {'effective_date': eff, 'before_label': before, 'after_label': after, 'notice_date': notice or eff}


def at(intervals, stamp):
    return V.label_at(intervals, stamp)


def test_one_event_reconstructs_exact_boundary():
    iv = V.reconstruct_intervals('B', [evt('2020-03-01', 'A', 'B')])
    assert at(iv, '2020-02-29')['label'] == 'A' and at(iv, '2020-03-01')['label'] == 'B'
    assert at(iv, '2020-03-01')['status'] == 'CURRENT_KRX_KIND_ANCHOR' and at(iv, '2019-01-01')['status'] == 'VERIFIED_KRX_KIND_CHANGE_EVENT'


def test_multiple_events_and_unsorted_input():
    iv = V.reconstruct_intervals('C', [evt('2022-01-01', 'B', 'C'), evt('2018-06-01', 'A', 'B')])
    assert [at(iv, d)['label'] for d in ('2017-01-01', '2018-06-01', '2021-12-31', '2022-01-01')] == ['A', 'B', 'B', 'C']


def test_no_event_is_stable_reconstruction_never_pit():
    iv = V.reconstruct_intervals('X', [])
    assert at(iv, '2015-01-02')['status'] == 'RECONSTRUCTED_STABLE_NO_CHANGE_EVENT'
    assert V.reconstruct_intervals(None, [])[0]['label'] is None


def test_conflicting_events_leave_the_interval_unknown():
    iv = V.reconstruct_intervals('C', [evt('2018-06-01', 'A', 'B'), evt('2022-01-01', 'Z', 'C')])
    assert at(iv, '2020-01-01')['status'] == 'CONFLICT' and at(iv, '2020-01-01')['label'] is None and at(iv, '2023-01-01')['label'] == 'C'
    iv = V.reconstruct_intervals('B', [evt('2018-06-01', 'A', 'B')])
    assert V.reconstruct_intervals('Q', [evt('2018-06-01', 'A', 'B')])[-1]['status'] == 'CONFLICT' and iv[-1]['label'] == 'B'
    assert V.reconstruct_intervals('C', [evt('2018-06-01', 'A', 'B'), evt('2018-06-01', 'B', 'C')])[0]['status'] == 'CONFLICT'


def test_identity_break_blocks_carry_and_missing_anchor_stays_unknown():
    iv = V.reconstruct_intervals('B', [evt('2020-03-01', 'A', 'B')], break_dates=['2019-01-01'])
    assert at(iv, '2018-01-01')['label'] is None and at(iv, '2021-01-01')['label'] == 'B'
    iv = V.reconstruct_intervals(None, [evt('2020-03-01', 'A', 'B')])
    assert at(iv, '2021-01-01')['label'] is None and at(iv, '2019-01-01')['label'] == 'A'


def test_notice_without_explicit_old_new_or_effective_date_is_unresolved():
    viewer = '<h1 class="ttl type-99 fleft">가 (000001)</h1>'
    assert V.parse_notice('<table><tr><td>1.회사명</td><td>가</td></tr></table>', viewer)['reason'] == 'EFFECTIVE_DATE_NOT_STATED'
    doc = '<table><tr><td>2.업종 및 업종코드 변경내역</td><td>변경 후</td><td>업종</td><td>B업</td></tr><tr><td>3.변경일</td><td>2020-01-02</td></tr></table>'
    assert V.parse_notice(doc, viewer)['reason'] == 'BEFORE_OR_AFTER_NOT_STATED'
    assert V.parse_notice(doc, '<h1>no code</h1>')['reason'] == 'VIEWER_IDENTITY_NOT_STATED'


def test_structured_notice_with_explicit_facts_and_identity_from_viewer():
    viewer = '<h1 class="ttl type-99 fleft">가 (000001)</h1>'
    doc = ('<table><tr><td>2.업종 및 업종코드 변경내역</td><td>변경 전</td><td>업종</td><td>A업</td></tr><tr><td>업종코드</td><td>01</td></tr>'
           '<tr><td>변경 후</td><td>업종</td><td>B업</td></tr><tr><td>업종코드</td><td>02</td></tr><tr><td>3.변경일</td><td>2020-01-02</td></tr>'
           '<tr><td>4.변경사유</td><td>합병</td></tr></table>')
    p = V.parse_notice(doc, viewer)
    assert (p['status'], p['before_label'], p['after_label'], p['effective_date'], p['identity']['stock_code']) == ('PARSED', 'A업', 'B업', '2020-01-02', '000001')
    assert p['reason_text'] == '합병'


def test_anchor_duplicates_and_conflicts():
    rows = [{'ticker': '1', 'industry_label': 'A'}, {'ticker': '1', 'industry_label': 'A'}, {'ticker': '2', 'industry_label': 'A'}, {'ticker': '2', 'industry_label': 'B'}]
    assert V.anchor_map(rows) == ({'1': 'A'}, ['2'])


def test_v3_builder_has_no_outcome_module_access_and_reproduces_committed_state(monkeypatch):
    import builtins
    import gzip
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        assert not any(x in name for x in ('portfolio_validation', 'factor_anatomy', 'model_overlay', 'price_adjustment', 'yfinance'))
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', guarded)
    from scripts import build_kr_industry_membership_v3 as B
    events, intervals, dates, audit = B.build()
    state = ROOT / 'data/kr-industry-membership-foundation-v3/state'
    for name, value in (('events.json.gz', events), ('intervals.json.gz', intervals), ('audit.json.gz', audit)):
        raw = gzip.compress((json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n').encode(), mtime=0)
        assert (state / name).read_bytes() == raw
    assert audit['decision'] == 'DATA_FOUNDATION_INSUFFICIENT_V3' and not audit['historicalOutcomeComputed']
    assert (audit['candidateNotices'], audit['noticeDocumentsFetched'], audit['verifiedChangeEvents']) == (81, 81, 80)
    assert audit['securitiesByChangeCount'] == {'0': 198, '1': 47, '2+': 15} and audit['nameDates'] == 73200
    assert audit['classifiedNameDates'] + audit['unknownNameDates'] == 73200 and audit['terminal'] == {'denominator': 2345, 'classified': 0}
    assert audit['gates']['terminalCoverage'] is False and audit['gates']['fractionInSufficientGroups'] is False


def test_notice_documents_are_the_retained_frozen_set():
    from scripts import collect_kr_industry_v3_notices as N
    cands, _ = N.frozen()
    state = json.loads((ROOT / 'data/kr-industry-membership-foundation-v3/notices/state.json').read_text())
    assert set(state) == {c['receipt_no'] for c in cands['candidates']} and all(v['status'] == 'SERVED' for v in state.values())
