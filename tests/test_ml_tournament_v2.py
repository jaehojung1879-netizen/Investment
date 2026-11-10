"""Economic invariants, source boundaries, train-only features and cache identity."""
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from research.ml_strategy_tournament_v2 import accounting as A, refit as R
from research.ml_strategy_tournament_v2.identity import cache_read, cache_write, digest


def market(n=7):
    days = [str(d.date()) for d in pd.bdate_range('2020-01-02', periods=n)]
    return {'sessions': days, 'quotes': {d: {t: {'close': 100., 'volume': 1., 'basis': 'RAW_UNADJUSTED'}
             for t in (A.ETF, 'AAA.KS', 'BBB.KS')} for d in days}, 'events': {},
            'admission': {t: {'status': 'COMPLETE', 'from': days[0], 'through': days[-1]} for t in (A.ETF, 'AAA.KS', 'BBB.KS')}}


def decision(d, weights):
    return {'date': d, 'weights': weights}


def event(d, kind, **kw):
    return {'date': d, 'ticker': 'AAA.KS', 'kind': kind, 'confirmedOn': '2019-12-30',
            'state': 'VERIFIED', 'sourceSha256': 'a' * 64, **kw}


def test_fee_charged_on_actual_filled_notionals_and_cash_conserved():
    m = market()
    b = A.run(m, [decision(m['sessions'][0], {'AAA.KS': 1.})], capital=100.)
    expected = (100 - 100 * .00025) / (1 + .00055)
    assert b['account'][0]['nav'] == pytest.approx(expected)
    assert b['maxAbsFundingResidualKrw'] < 1e-10
    assert sum(t['totalFeeIncludingTax'] for t in b['trades']) == pytest.approx(100 - expected)
    assert b['account'][0]['cash'] >= 0


def test_halted_quantity_is_not_reduced_to_pay_other_trades_fees():
    m = market()
    a, b = m['sessions'][:2]
    m['quotes'][b]['AAA.KS']['volume'] = 0.
    out = A.run(m, [decision(a, {'AAA.KS': .5, A.ETF: .5}), decision(b, {'BBB.KS': 1.})], capital=100.)
    rows = {(r['date'], r['ticker']): r for r in out['assets']}
    assert out['status'] == 'COMPLETE'
    assert rows[a, 'AAA.KS']['quantity'] == rows[b, 'AAA.KS']['quantity']
    assert not any(t['ticker'] == 'AAA.KS' and t['date'] == b for t in out['trades'])
    assert any(o['status'] == 'HALTED_DEFERRED_OR_SKIPPED' for o in out['orders'])
    assert min(r['cash'] for r in out['account']) >= 0


def test_dividend_receivable_is_not_spendable_before_payment_or_double_counted():
    m = market()
    d = m['sessions']
    for date in d[1:]:
        m['quotes'][date]['AAA.KS']['close'] = 90.
    m['events'][d[1]] = [event(d[1], 'CASH_DIVIDEND', dps=10., amountBasis='PRE_ACTION_SHARE', paymentDate=d[3])]
    out = A.run(m, [decision(d[0], {'AAA.KS': 1.}), decision(d[1], {'AAA.KS': 1.}), decision(d[3], {'AAA.KS': 1.})], capital=100.)
    accounts = {r['date']: r for r in out['account']}
    assert accounts[d[1]]['nav'] == pytest.approx(accounts[d[0]]['nav'])
    assert accounts[d[1]]['cashReceivable'] > 0
    assert accounts[d[1]]['cash'] == 0
    assert not any(t['date'] == d[1] for t in out['trades'])
    assert accounts[d[3]]['cashReceivable'] == 0
    assert any(t['date'] == d[3] and t['ticker'] == 'AAA.KS' and t['quantityDelta'] > 0 for t in out['trades'])


def test_stock_entitlement_is_valued_but_not_tradable_until_delivery():
    m = market()
    d = m['sessions']
    for date in d[1:]:
        m['quotes'][date]['AAA.KS']['close'] = 100 / 1.1
    m['events'][d[1]] = [event(d[1], 'STOCK_DIVIDEND', sharesPerOldShare=.1, deliveryDate=d[4])]
    out = A.run(m, [decision(d[0], {'AAA.KS': 1.}), decision(d[1], {A.ETF: 1.})], capital=100.)
    accounts = {r['date']: r for r in out['account']}
    assert accounts[d[1]]['stockReceivableValue'] > 0
    assert accounts[d[3]]['stockReceivableValue'] > 0
    assert accounts[d[4]]['stockReceivableValue'] == 0
    assert not any(t['date'] == d[1] and t['quantityDelta'] < -1 for t in out['trades'] if t['ticker'] == 'AAA.KS')


@pytest.mark.parametrize('kind', ['TERMINAL_CASH', 'TERMINAL_EXCHANGE'])
def test_uncited_or_incomplete_terminal_is_blocked_not_zero_or_last_quote(kind):
    m = market()
    d = m['sessions']
    m['events'][d[2]] = [{'date': d[2], 'ticker': 'AAA.KS', 'kind': kind}]
    out = A.run(m, [decision(d[0], {'AAA.KS': 1.})])
    assert out['status'] == 'SOURCE_BLOCKED'
    assert out['account'][2]['nav'] is None
    assert all(r['nav'] is None for r in out['account'][2:])


def test_cited_terminal_cash_preserves_claim_then_pays_real_cash():
    m = market()
    d = m['sessions']
    m['events'][d[2]] = [event(d[2], 'TERMINAL_CASH', cashPerOldShare=120., paymentDate=d[4])]
    out = A.run(m, [decision(d[0], {'AAA.KS': 1.})], capital=100.)
    assert out['status'] == 'COMPLETE'
    assert out['account'][2]['cashReceivable'] > 0
    assert out['account'][4]['cashReceivable'] == 0
    assert out['account'][4]['cash'] > 100


def test_missing_terminal_quote_never_becomes_last_price_exit():
    m = market()
    d = m['sessions']
    for date in d[2:]:
        m['quotes'][date].pop('AAA.KS')
    out = A.run(m, [decision(d[0], {'AAA.KS': 1.})])
    assert out['blocked']['date'] == d[2]
    assert 'TERMINAL_CONSIDERATION' in out['blocked']['reason']


def test_source_silence_does_not_admit_complete_shareholder_economics():
    m = market()
    m['admission'].pop('AAA.KS')
    out = A.run(m, [decision(m['sessions'][0], {'AAA.KS': 1.})])
    assert out['status'] == 'SOURCE_BLOCKED'
    assert out['trades'] == []


def test_adjusted_prices_cannot_double_count_explicit_dividends():
    m = market()
    m['quotes'][m['sessions'][0]]['AAA.KS']['basis'] = 'TOTAL_RETURN'
    with pytest.raises(ValueError, match='ADJUSTED_PRICE'):
        A.run(m, [])


def test_identical_etf_paths_have_exactly_zero_active_returns():
    m = market()
    d = [decision(m['sessions'][0], {A.ETF: 1.})]
    a, b = A.run(m, d), A.run(m, d)
    x = np.array([r['nav'] for r in a['account']], dtype=np.float64)
    y = np.array([r['nav'] for r in b['account']], dtype=np.float64)
    assert np.array_equal(x - y, np.zeros(len(x)))
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


@pytest.mark.parametrize('dimension', ['code', 'config', 'source', 'model', 'fold', 'environment'])
def test_cache_refuses_every_identity_change(tmp_path, dimension):
    key = {k: 'original' for k in ['code', 'config', 'source', 'model', 'fold', 'environment']}
    p = tmp_path / 'scores.json'
    cache_write(p, key, {'scores': [.1, .2]})
    assert cache_read(p, key)['scores'] == [.1, .2]
    changed = {**key, dimension: 'different'}
    with pytest.raises(ValueError, match='CACHE_IDENTITY'):
        cache_read(p, changed)


def test_corrupt_cache_payload_is_not_reused(tmp_path):
    p = tmp_path / 'scores.json'
    cache_write(p, {'code': 'fixed'}, {'score': .1})
    d = json.loads(p.read_text())
    d['payload']['score'] = 99.
    p.write_text(json.dumps(d))
    with pytest.raises(ValueError, match='CACHE_PAYLOAD'):
        cache_read(p, {'code': 'fixed'})


def frame():
    d = pd.to_datetime(['2019-01-04', '2019-02-01', '2019-03-01', '2020-01-03', '2020-02-07'])
    return pd.DataFrame({'date': d, 'ticker': ['AAA.KS'] * len(d), 'y126': [.1] * len(d),
                         'exit126': pd.to_datetime(['2019-09-01', '2019-10-01', '2019-11-01', '2020-08-01', '2020-09-01']),
                         'A07_momentum12_1': [.2] * len(d), 'A09_industryRelativeMomentum126': [.1] * len(d),
                         'H01_industryRelMom126': [.3] * len(d), 'B01_bookToMarket': [np.nan] * len(d),
                         'MKT_trend126': [1., 2., 3., 100., 200.]})


def test_future_rows_and_missingness_cannot_change_past_fold_inputs():
    f = frame()
    *_, before = R.fold_inputs(f, 2020)
    future = f.iloc[[-1]].copy()
    future['date'], future['exit126'], future['B01_bookToMarket'] = pd.Timestamp('2025-01-03'), pd.Timestamp('2025-09-01'), 100.
    expanded = pd.concat([f, future], ignore_index=True)
    *_, after = R.fold_inputs(expanded, 2020)
    assert before == after
    assert 'B01_bookToMarket' not in before['layers']['company']
    assert before['marketMean']['MKT_trend126'] == 2.


def test_refit_source_gate_precedes_any_real_fit(tmp_path):
    with patch.object(R.T, 'fit_predict', side_effect=AssertionError('FIT_FORBIDDEN')):
        with pytest.raises(ValueError, match='SOURCE_BLOCKED'):
            R.fit_fixed_fold(frame(), 2020, 'XGB_CI_RANK_h1', {'status': 'SOURCE_BLOCKED'}, tmp_path, packet={}, approval=None)
    assert not list(tmp_path.iterdir())


def test_v1_and_audit_pins_remain_exact():
    root = Path(__file__).resolve().parents[1]
    pins = json.loads((root / 'research/ml_strategy_tournament_independent_audit_v1/frozen-inputs.json').read_text())
    from research.ml_strategy_tournament_v2.identity import file_hash
    assert all(file_hash(root / p) == r['sha256'] for p, r in pins['files'].items())


def test_source_328_economic_functions_are_exactly_reused():
    import ast
    root = Path(__file__).resolve().parents[1] / 'research/ml_strategy_tournament_v2/vendor'
    original = ast.parse((root / 'shareholder_inputs_328.py.txt').read_text())
    adapted = ast.parse((root / 'shareholder_inputs.py').read_text())
    functions = lambda tree: {n.name: ast.dump(n) for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    old, new = functions(original), functions(adapted)
    assert all(new[name] == body for name, body in old.items())
    assert digest(old) == digest({name: new[name] for name in old})


def test_terminal_cash_settles_on_cited_same_day():
    m = market()
    d = m['sessions']
    m['events'][d[2]] = [event(d[2], 'TERMINAL_CASH', cashPerOldShare=120., paymentDate=d[2])]
    out = A.run(m, [decision(d[0], {'AAA.KS': 1.}), decision(d[2], {A.ETF: 1.})], capital=100.)
    assert out['status'] == 'COMPLETE'
    assert out['account'][2]['cashReceivable'] == 0
    assert any(t['date'] == d[2] and t['ticker'] == A.ETF for t in out['trades'])


def test_cited_share_exchange_does_not_invent_cash_or_tradable_old_security():
    m = market()
    d = m['sessions']
    m['events'][d[2]] = [event(d[2], 'TERMINAL_EXCHANGE', successor='BBB.KS', sharesPerOldShare=1.2, paymentDate=d[4])]
    out = A.run(m, [decision(d[0], {'AAA.KS': 1.})], capital=100.)
    assert out['status'] == 'COMPLETE'
    assert out['account'][2]['stockReceivableValue'] > 100
    rows = {(r['date'], r['ticker']): r for r in out['assets']}
    assert rows[d[2], 'AAA.KS']['quantity'] == 0
    assert rows[d[2], 'BBB.KS']['quantity'] == 0
    assert rows[d[4], 'BBB.KS']['quantity'] > 1


def test_uncited_price_jump_is_not_a_synthetic_split_return():
    m = market()
    d = m['sessions']
    m['quotes'][d[2]]['AAA.KS']['close'] = 50.
    out = A.run(m, [decision(d[0], {'AAA.KS': 1.})])
    assert out['status'] == 'SOURCE_BLOCKED'
    assert 'RAW_PRICE_JUMP' in out['blocked']['reason']


def test_approved_packet_still_cannot_override_source_block():
    with pytest.raises(ValueError, match='SOURCE_BLOCKED'):
        R.authorization_gate({'candidates': R.CONFIG['candidates'], 'allowNewWinner': False},
                             {'authorized': True}, {'status': 'SOURCE_BLOCKED'})


def test_reported_v1_metadata_hash_is_distinct_from_actual_protected_bytes():
    from research.ml_strategy_tournament_v2.identity import ROOT, file_hash
    assert file_hash(ROOT / 'research/ml_strategy_tournament_v1/config.json') == R.CONFIG['v1ConfigSha256']
    assert R.CONFIG['v1PublishedMetadataConfigSha256'] != R.CONFIG['v1ConfigSha256']


def test_simultaneous_split_and_cash_uses_old_share_basis_in_any_order():
    from copy import deepcopy
    m = market()
    d = m['sessions']
    for date in d[1:]:
        m['quotes'][date]['AAA.KS']['close'] = 45.
    ev = [event(d[1], 'SPLIT', shareMultiplier=2.),
          event(d[1], 'CASH_DIVIDEND', dps=10., amountBasis='PRE_ACTION_SHARE', paymentDate=d[3])]
    m['events'][d[1]] = ev
    ds = [decision(d[0], {'AAA.KS': 1.})]
    a = A.run(m, ds, capital=100.)
    reversed_events = deepcopy(m)
    reversed_events['events'][d[1]] = list(reversed(ev))
    b = A.run(reversed_events, ds, capital=100.)
    assert a['account'][1]['nav'] == pytest.approx(a['account'][0]['nav'])
    assert [r['nav'] for r in a['account']] == [r['nav'] for r in b['account']]


def test_duplicate_distribution_cannot_be_credited_twice():
    m = market()
    d = m['sessions']
    e = event(d[1], 'CASH_DIVIDEND', dps=10., amountBasis='PRE_ACTION_SHARE', paymentDate=d[3])
    m['events'][d[1]] = [e, dict(e)]
    out = A.run(m, [decision(d[0], {'AAA.KS': 1.})])
    assert out['status'] == 'SOURCE_BLOCKED'
    assert 'DUPLICATE' in out['blocked']['reason']


def test_fixed_fit_and_cache_use_actual_input_identity(tmp_path):
    from research.ml_strategy_tournament_v2.identity import code_identity, environment
    f = frame()
    sources = {'status': 'COMPLETE_VERIFIED_SHAREHOLDER_INPUTS', 'correctedMatrixSha256': R.frame_sha(f)}
    packet = {'code': code_identity(), 'configSha256': digest(R.CONFIG), 'environment': environment(),
              'sourceAdmissionSha256': digest(sources), 'candidates': R.CONFIG['candidates'], 'allowNewWinner': False}
    approval = {'authorized': True, 'packetSha256': digest(packet)}
    calls = []
    def fake_fit(cfg, train, test, train_ranked, test_ranked, layers):
        calls.append(cfg)
        assert 'B01_bookToMarket' not in layers['company']
        return np.zeros(len(test)), None, None, layers['company'] + layers['industry']
    with patch.object(R, 'verify_public_owner_approval'), patch.object(R.T, 'fit_predict', side_effect=fake_fit):
        first = R.fit_fixed_fold(f, 2020, 'XGB_CI_RANK_h1', sources, tmp_path, packet=packet, approval=approval)
        second = R.fit_fixed_fold(f, 2020, 'XGB_CI_RANK_h1', sources, tmp_path, packet=packet, approval=approval)
        assert first == second and len(calls) == 1
        changed = f.copy()
        changed.loc[0, 'y126'] = 10.
        with pytest.raises(ValueError, match='CONTENT_IDENTITY'):
            R.fit_fixed_fold(changed, 2020, 'XGB_CI_RANK_h1', sources, tmp_path, packet=packet, approval=approval)


def test_blocked_day_does_not_publish_partial_fills_or_committed_entitlements():
    m = market()
    d = m['sessions']
    e = event(d[1], 'CASH_DIVIDEND', dps=10., amountBasis='PRE_ACTION_SHARE', paymentDate=d[1])
    m['events'][d[1]] = [e, dict(e)]
    out = A.run(m, [decision(d[0], {'AAA.KS': 1.}), decision(d[1], {A.ETF: 1.})])
    assert out['status'] == 'SOURCE_BLOCKED'
    assert not any(t['date'] == d[1] for t in out['trades'])
    assert any(e.get('status') == 'UNCOMMITTED_SOURCE_BLOCKED_DAY' for e in out['events'])
    assert out['account'][1]['nav'] is None


def test_result_manifest_does_not_include_its_own_previous_bytes(tmp_path):
    from research.ml_strategy_tournament_v2.run import manifest_payload
    from research.ml_strategy_tournament_v2.identity import write_once
    write_once(tmp_path / 'results.json', {'cagr': .1})
    first = manifest_payload(tmp_path, 'SYN_ID', {'ledger.jsonl.gz': 'a' * 64})
    write_once(tmp_path / 'result-manifest.json', first)
    second = manifest_payload(tmp_path, 'SYN_ID', {'ledger.jsonl.gz': 'a' * 64})
    assert first == second
    assert 'result-manifest.json' not in second['files']
    write_once(tmp_path / 'result-manifest.json', second)
