import pandas as pd
import pytest

from research.kr_us_public_buys_v1 import kr
from research.kr_us_public_buys_v1.kr_collect import search_rows


@pytest.mark.parametrize(('reason', 'security', 'price', 'expected'), [
    ('장내매수(+)', '보통주', '12,300', 'VERIFIED_MARKET_BUY'),
    ('장내매수(+)', '보통주', '-', 'UNKNOWN_BUY_ECONOMICS'),
    ('장내매수(+)', '우선주', '12,300', 'EXCLUDED_NONCOMMON'),
    ('장외매수(+)', '보통주', '12,300', 'EXCLUDED_OFF_EXCHANGE'),
    ('주식매수선택권행사(+)', '보통주', '12,300', 'EXCLUDED_NONMARKET_ACQUISITION'),
    ('기타(+)', '보통주', '12,300', 'UNKNOWN_TRANSACTION_TYPE'),
])
def test_dart_requires_cash_documented_market_acquisition(reason, security, price, expected):
    row = {'reason': reason, 'security': security, 'delta': '400', 'price': price, 'eventReported': '2023년 1월 4일'}
    actual, reported, _, _ = kr.classify(row, '2023-01-05')
    assert actual == expected
    assert reported == '2023-01-04'


def test_dart_list_uses_observed_public_date_even_when_receipt_prefix_differs():
    raw = '''<table class="tbList"><tbody><tr><td>1</td>
        <td><a onclick="openCorpInfoNew('00126380', 'winCorpInfo', '')">삼성전자</a></td>
        <td><a id="r_20230126000597">임원ㆍ주요주주특정증권등소유상황보고서</a></td>
        <td>reporter</td><td>2023.01.27</td><td></td></tr></tbody></table>
        <div class="pageInfo">[1/1] [총 1건]</div>'''.encode()
    _, _, _, records = search_rows(raw)
    row = records[0]
    assert row['publicDate'] == '2023-01-27' and row['receiptPrefixDate'] == '2023-01-26'
    dates = pd.DatetimeIndex(['2023-01-27', '2023-02-03'])
    sessions = pd.bdate_range('2023-01-26', '2023-02-03')
    assert kr.public_end(dates, row['publicDate'], sessions) == (pd.Timestamp('2023-01-30'), dates[1])


def test_amended_buy_keeps_first_date_and_later_removal_is_effective_only_when_public():
    raw = {'reason': '장내매수(+)', 'security': '보통주', 'before': '10', 'delta': '2', 'after': '12',
           'price': '100', 'eventReported': '2023.01.03'}
    base = {'receipt': '20230104000001', 'reporter': 'reporter', 'corpCode': '00000001', 'form': 'D002',
            'publicDate': '2023-01-04', 'eligibleDate': '2023-01-05', 'status': 'PARSED', 'transactions': [raw]}
    correction = dict(base, receipt='20230105000001', form='[기재정정] D002', publicDate='2023-01-05', eligibleDate='2023-01-06',
                      amendmentFamily=[base['receipt']], transactions=[dict(raw, price='99')])
    removal = dict(correction, receipt='20230106000001', publicDate='2023-01-06', eligibleDate='2023-01-09',
                   amendmentFamily=[base['receipt'], correction['receipt']], transactions=[dict(raw, reason='증여(+)')])
    docs = {record['receipt']: record for record in (base, correction, removal)}
    _, rows = kr.process_documents([base, correction, removal], docs, docs)
    assert [r['eventStatus'] for r in rows] == [
        'CLEAN_FIRST_DISCLOSURE', 'AMENDED_PREVIOUSLY_IDENTIFIED_BUY', 'EXCLUDED_NONMARKET_ACQUISITION']
    assert rows[0]['publicDate'] == '2023-01-04'
    assert rows[0]['withdrawnEligibleDate'] == '2023-01-09'
