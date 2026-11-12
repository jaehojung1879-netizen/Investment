"""Source-only evidence and independent accounting identities on synthetic inputs."""
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from pipeline import price_adjustment
from research.a1b1_economic_inputs_v1.dividends import parse_ex_dates, reconcile_decisions
from research.a1b1_economic_inputs_v1.economic_check import prepare_event, synthetic_pair, synthetic_payoff
from research.a1b1_economic_inputs_v1.references import load
from research.a1b1_economic_inputs_v1.repair import DATES, URL, recover


def fixture():
    source = b'SYNTHETIC_ACCOUNTING_SOURCE'
    charges = {k: 0 for k in ('commissionBps', 'spreadBps', 'slippageBps', 'taxBps')}
    return {'evidenceClass': 'SYNTHETIC', 'security': 'SYN_STOCK', 'benchmark': 'SYN_069500',
            'priceBasis': 'AS_TRADED_UNADJUSTED',
            'distributionPolicy': 'CASH_ON_PAYMENT_CLAIM_AT_PAR_NO_REINVESTMENT',
            'coverage': {'prices': 'COMPLETE', 'dividends': 'COMPLETE', 'actions': 'COMPLETE', 'identity': 'VERIFIED'},
            'sourceBytes': {'SYN': source}, 'sourceSha256': {'SYN': hashlib.sha256(source).hexdigest()},
            'bars': [{'date': d, 'close': 100.0, 'traded': True, 'sourceId': 'SYN'}
                     for d in ('2026-01-05', '2026-01-06', '2026-01-07')],
            'cashGrowth': {d: {'periodStart': p, 'periodEnd': d, 'growth': 1.0,
                              'basis': 'NET_INVESTABLE_PAYOFF', 'sourceId': 'SYN'}
                           for p, d in [('2026-01-05', '2026-01-06'), ('2026-01-06', '2026-01-07')]},
            'actions': [], 'costModel': {'basis': 'SELF_FINANCING_ENTRY_AND_TERMINAL_LIQUIDATION',
                                        'returnInputBasis': 'GROSS_BEFORE_TRANSACTION_COSTS',
                                        'interimTrades': False,
                                        'switchCostRule': 'FOUR_ACTUAL_LEGS_SHARED_TARIFF_NO_EXTRA_SURCHARGE',
                                        'validFrom': '2026-01-05', 'validThrough': '2026-01-07',
                                        'tariff': {kind: {side: deepcopy(charges) for side in ('BUY', 'SELL')}
                                                   for kind in ('STOCK', 'ETF')}}}


def dividend(**changes):
    return {'actionId': 'SYN_DIV', 'kind': 'CASH_DIVIDEND', 'security': 'SYN_STOCK',
            'date': '2026-01-06', 'paymentDate': '2026-01-07', 'dateSource': 'DIRECT',
            'amountPerShare': 10, 'withholdingFraction': 0, 'sourceId': 'SYN',
            'taxSourceId': 'SYN', **changes}


def test_direct_official_ex_date_keeps_issuer_and_security_identity_separate():
    raw = gzip.decompress((Path(__file__).parent / 'fixtures/a1b1_economic_inputs_v1/seibro-samsung-202503.xml.gz').read_bytes())
    row = parse_ex_dates(raw)['rows'][0]
    assert row['exDate'] == '2025-03-28' and row['recordDate'] == '2025-03-31'
    assert row['exDateSource'] == 'DIRECT' and row['securityId'] is None
    assert row['issuerShortCode'] == '00593'
    decision = {'rcept_no': 'SYN_RECEIPT', 'corp_code': 'SYN_CORP', 'stock_code': '005930',
                'recordDate': '2025-03-31', 'parseStatus': 'PARSED', 'amendment': False}
    joined = reconcile_decisions([decision], [row])[0]
    assert joined['priorCandidate'] is None and 'SHARE_CLASS' in joined['status']


@pytest.mark.parametrize('raw', [b'<html>Access Denied</html>', b'<vector result="10"/>',
                                 b'<!DOCTYPE xml><vector result="0"/>'])
def test_source_refusal_or_count_mismatch_never_means_no_dividend(raw):
    with pytest.raises(ValueError):
        parse_ex_dates(raw)


def test_real_inputs_refused_before_numeric_fields_are_accessed():
    with pytest.raises(ValueError, match='SYNTHETIC_ONLY'):
        synthetic_payoff({'evidenceClass': 'HISTORICAL'})
    data = fixture()
    data['security'] = '005930.KS'
    with pytest.raises(ValueError, match='SYNTHETIC_ONLY'):
        synthetic_payoff(data)


def test_exact_shareholder_cashflow_differs_from_existing_adjustment_index():
    data = fixture()
    data['bars'][1]['close'] = data['bars'][2]['close'] = 95
    data['actions'] = [dividend()]
    result = synthetic_payoff(data)
    assert result['netReturn'] == pytest.approx(0.05)  # (95+10)/100-1
    frame = pd.DataFrame({'Close': [100, 95], 'Dividends': [0, 10]},
                         index=pd.to_datetime(['2026-01-05', '2026-01-06']))
    adjusted, _ = price_adjustment.to_total_return(frame)
    assert adjusted['Close'].iloc[-1] / adjusted['Close'].iloc[0] - 1 == pytest.approx(1 / 18)
    # Protect the old research bytes: demonstrate, never silently change the index.


@pytest.mark.parametrize('ratio,end', [(2, 50), (0.5, 200)])
def test_forward_and_reverse_split_preserve_actual_share_value_once(ratio, end):
    data = fixture()
    data['actions'] = [{'actionId': 'SYN_SPLIT', 'kind': 'SPLIT', 'security': 'SYN_STOCK',
                        'date': '2026-01-06', 'ratio': ratio, 'sourceId': 'SYN'}]
    data['bars'][1]['close'] = data['bars'][2]['close'] = end
    assert synthetic_payoff(data)['wealth'] == pytest.approx(1)


def test_cash_is_not_reinvested_or_interest_accrued_before_payment():
    data = fixture()
    data['bars'][1]['close'] = data['bars'][2]['close'] = 90
    data['cashGrowth']['2026-01-06']['growth'] = 2.0
    data['actions'] = [dividend(withholdingFraction=0.2)]
    result = synthetic_payoff(data)
    assert result['wealth'] == pytest.approx(0.98)
    data['actions'][0]['paymentDate'] = '2026-01-08'
    result = synthetic_payoff(data)
    assert result['liquidCash'] == pytest.approx(0.9)
    assert result['unpaidReceivable'] == pytest.approx(0.08)


def test_costs_are_self_financing_and_exit_notional_is_actual_value():
    data = fixture()
    data['costModel']['tariff']['STOCK']['BUY']['commissionBps'] = 100
    data['costModel']['tariff']['STOCK']['SELL']['taxBps'] = 200
    data['bars'][-1]['close'] = 110
    assert synthetic_payoff(data)['wealth'] == pytest.approx(1.1 * 0.98 / 1.01)
    etf = deepcopy(data)
    etf['security'] = etf['benchmark']
    etf['bars'][-1]['close'] = 100
    result = synthetic_pair(data, etf)
    assert result['netActiveReturn'] == pytest.approx(1.1 * 0.98 / 1.01 - 1)
    etf['bars'].pop()
    with pytest.raises(ValueError, match='GRID_MISMATCH'):
        synthetic_pair(data, etf)


@pytest.mark.parametrize('defect,code', [('dividends', 'INCOMPLETE'), ('raw', 'SOURCE_BYTES_CHANGED'),
                                      ('cash', 'CASH_INTERVAL'), ('gap', 'PRICE_SESSION_GAP'),
                                      ('halt', 'TRADABILITY'), ('terminal', 'INVALID_ECONOMIC_NUMBER'),
                                      ('rights', 'UNSUPPORTED_CORPORATE'), ('duplicate', 'DUPLICATE')])
def test_economic_gaps_are_rejected_without_zero_or_last_price_substitution(defect, code):
    data = fixture()
    if defect == 'dividends': data['coverage']['dividends'] = 'UNKNOWN'
    if defect == 'raw': data['sourceBytes']['SYN'] = b'changed'
    if defect == 'cash': data['cashGrowth'].pop('2026-01-06')
    if defect == 'gap': data['bars'].pop(1)
    if defect == 'halt': data['bars'][-1]['traded'] = False
    if defect == 'terminal': data['actions'] = [dividend(kind='TERMINAL_CASH', amountPerShare=None)]
    if defect == 'rights': data['actions'] = [dividend(kind='RIGHTS_ISSUE')]
    if defect == 'duplicate': data['actions'] = [dividend(), dividend()]
    with pytest.raises(ValueError, match=code): synthetic_payoff(data)


def test_pending_horizons_are_retained_and_missing_policies_remain_blocked():
    raw = json.dumps({'studyId': 'kr-corporate-information-events-v1'}).encode()
    event = {'hypothesis': 'A1', 'rcept_no': 'SYN', 'receiptDay': '2026-01-05',
             'signalSession': '2026-01-06', 'entrySession': '2026-01-07',
             'informationAvailableAtUtc': '2026-01-05T06:00:00Z'}
    result = prepare_event(raw, hashlib.sha256(raw).hexdigest(), event, '2026-01-08T12:00:00Z', {})
    assert result['status'] == 'BLOCKED' and result['performance'] is None
    assert all(r['status'] == 'OBSERVATION_INCOMPLETE' for r in result['maturity'].values())
    event['informationAvailableAtUtc'] = '2026-01-07T09:00:00Z'
    with pytest.raises(ValueError, match='FUTURE_SIGNAL'):
        prepare_event(raw, hashlib.sha256(raw).hexdigest(), event, '2026-01-08T12:00:00Z', {})


def test_exact_reference_is_existing_admission_engine():
    gate = load('admission').window_admission
    assert gate({'2026-01-05': True}, ['2026-01-05', '2026-01-06'], '2026-01-05', 1,
                '2026-01-05')['status'] == 'PENDING_MATURITY_OR_LEDGER_END'


def test_recovery_preserves_original_bytes_and_only_adds_three_date_rows(tmp_path):
    from pipeline import historical_store as H
    original, responses, output = [tmp_path / n for n in ('original', 'responses', 'output')]
    original.mkdir(); responses.mkdir()
    old = {'id': 'krx-price:2026-09-14:005930', 'date': '2026-09-14', 'region': 'KR',
           'ticker': '005930.KS', 'close': 100, 'volume': 1}
    (original / 'krx-prices-2026.jsonl.gz').write_bytes(H.encode([old]))
    (original / 'krx-prices-done.json').write_text(json.dumps(list(DATES)))
    before = {p.name: p.read_bytes() for p in original.iterdir()}
    manifest = []
    for day in DATES:
        raw = json.dumps({'OutBlock_1': [{'ISU_CD': '005930', 'BAS_DD': day.replace('-', ''),
                                         'TDD_CLSPRC': '100', 'ACC_TRDVOL': '1'}]}).encode()
        (responses / (day + '.json')).write_bytes(raw)
        manifest.append({'date': day, 'url': URL, 'basDd': day.replace('-', ''), 'httpStatus': 200,
                         'file': day + '.json', 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)})
    (responses / 'manifest.json').write_text(json.dumps(manifest))
    result = recover(original, responses, output)
    assert result['addedRows'] == 3 and result['status'] == 'RECOVERED_ISOLATED'
    assert before == {p.name: p.read_bytes() for p in original.iterdir()}
    with pytest.raises(ValueError, match='NEW_ISOLATED_OUTPUT'):
        recover(original, responses, output)
