"""Invented inputs and approval refusal only; no historical market execution."""
import json
from pathlib import Path

import pandas as pd
import pytest

from research.kr_event_correction_v2 import cohort as C, evaluate as V, portfolio as P, run as R
from research.corporate_event_outcome_v1.shareholder_inputs_v2 import SourceBlocked


def test_default_packet_validation_opens_no_price_or_live_paths():
    result = R.validate()
    assert result['pricesOpened'] == result['historicalExecutions'] == result['liveWrites'] == 0
    assert result['status'] == 'SOURCE_BLOCKED' and result['protectedPinsMatch']
    assert len(R.read(R.CONTRACT)['cells']) == 4
    assert not R.CLAIM.exists() and not R.RESULT.exists() and not R.AUTHORIZATION.exists()


def test_missing_owner_approval_stops_before_claim_or_price_reader(monkeypatch, tmp_path):
    monkeypatch.setattr(R, 'AUTHORIZATION', tmp_path / 'absent-owner.json')
    monkeypatch.setattr(R, 'claim', lambda: pytest.fail('claim must not be consumed'))
    monkeypatch.setattr(R, 'load_inputs', lambda *_: pytest.fail('prices must not be opened'))
    with pytest.raises(SourceBlocked, match='NO_NEW_OWNER_AUTHORIZATION'):
        R.execute(tmp_path, tmp_path)
    assert not R.CLAIM.exists() and not R.RESULT.exists()


def test_an_old_or_wrong_scope_authorization_cannot_be_reused(monkeypatch, tmp_path):
    path = tmp_path / 'owner.json'
    path.write_text(json.dumps({'scope': 'LIVE', 'phrase': 'APPROVE OLD_STUDY'}))
    monkeypatch.setattr(R, 'AUTHORIZATION', path)
    monkeypatch.setattr(R, 'claim', lambda: pytest.fail('claim must not be consumed'))
    with pytest.raises(SourceBlocked, match='DOES_NOT_PIN_THIS_SCOPE'):
        R.execute(tmp_path, tmp_path)


def test_known_missing_files_do_not_consume_a_lock_even_after_approval(monkeypatch, tmp_path):
    monkeypatch.setattr(R, 'authorize', lambda: {'priceSha256': {'missing.gz': 'a' * 64}, 'universeGitBlobs': {}})
    monkeypatch.setattr(R, 'claim', lambda: pytest.fail('known missing sources must not consume a claim'))
    with pytest.raises(SourceBlocked, match='ABSENT_OR_CHANGED_BEFORE_CLAIM'):
        R.execute(tmp_path, tmp_path)


def cohort_input():
    sessions = list(pd.bdate_range('2023-01-02', '2025-02-07').strftime('%Y-%m-%d'))
    snapshots = {d: {'000001': {'listedShares': n}} for d, n in
                 [('2023-12-01', 100), ('2024-12-02', 100), ('2025-01-02', 100), ('2025-03-04', 999999)]}
    previous = {'rcept_no': '20240201000001', 'corp_code': 'I', 'stock_code': '000001',
                'report_nm': '현금ㆍ현물배당결정', 'recordDate': '2023-12-31',
                'dividendClass': '결산배당', 'dividendKind': '현금배당', 'dpsCommonKrw': '100'}
    current = {**previous, 'rcept_no': '20250203000001', 'recordDate': '2024-12-31', 'dpsCommonKrw': '125'}
    index = [{**current, 'family': 'EB', 'report_nm': '주요사항보고서(교환사채권발행결정)'}]
    admission = {'securityIdentities': {'000001.KS': {'corp_code': 'I', 'securityClass': 'COMMON',
                  'from': '2012-01-01', 'through': '2026-10-30', 'sourceSha256': 'a' * 64}},
                 'fiscalPeriods': {previous['rcept_no']: {'fiscalYear': 2023, 'knownOn': '2024-01-31', 'sourceSha256': 'b' * 64},
                                   current['rcept_no']: {'fiscalYear': 2024, 'knownOn': '2025-01-31', 'sourceSha256': 'c' * 64}},
                 'amendmentLinks': {}}
    return index, [previous, current], snapshots, admission, sessions


def test_corrected_cohort_detects_normal_k7_and_keeps_p2_as_title_evidence():
    args = cohort_input()
    events, _ = C.build(*args)
    assert {e['hypothesis'] for e in events} == {C.P2, C.K7}
    k7 = next(e for e in events if e['hypothesis'] == C.K7)
    assert k7['detail']['verifiedFiscalYear'] == 2024 and k7['detail']['dpsChangePct'] == 25
    assert k7['signalSession'] == '2025-02-04' and k7['entrySession'] == '2025-02-05'
    p2 = next(e for e in events if e['hypothesis'] == C.P2)
    assert p2['detail']['dilutionEvidence']['economicDilution'] == 'UNVERIFIED'


def test_subsidiary_and_unqualified_fiscal_year_do_not_become_a_new_cohort():
    args = list(cohort_input())
    args[1][-1]['report_nm'] += '(자회사의 주요경영사항)'
    events, _ = C.build(*args)
    assert not any(e['hypothesis'] == C.K7 for e in events)
    args = list(cohort_input())
    args[3]['fiscalPeriods'].clear()
    with pytest.raises(SourceBlocked, match='FISCAL_PERIOD_MISSING'):
        C.build(*args)


def test_ambiguous_known_correction_blocks_instead_of_silently_using_old_dps():
    args = list(cohort_input())
    args[1].append({**args[1][-1], 'rcept_no': '20250203000002', 'amendment': True, 'dpsCommonKrw': '200'})
    with pytest.raises(SourceBlocked, match='AMENDMENT_CHAIN_UNRESOLVED'):
        C.build(*args)


def portfolio_input():
    days = ['2025-01-02', '2025-01-03', '2025-01-06']
    market = {'sessions': days, 'etf': dict.fromkeys(days, 100), 'cash': {'ZERO': dict.fromkeys(days, 0)},
              'levels': {'A': dict(zip(days, [100, 90, 90])), 'B': dict(zip(days, [100, 105, 105]))},
              'tradable': {'A': set(days), 'B': set(days)}}
    history = list(pd.bdate_range(end=days[0], periods=253).strftime('%Y-%m-%d'))
    market['signalCalendar'] = [*history[:-1], *days]
    decision = {'signalSession': '2024-12-30', 'knownOn': '2024-12-30', 'entrySession': days[0],
                'weights': {'A': 1.0}, 'maxNames': 5, 'maxSecurityWeight': 1., 'maxSectorWeight': 1.,
                'rankedCandidates': [{'ticker': t, 'eligible': True, 'sector': t, 'maxWeight': 1.} for t in ('A', 'B')]}
    events = [{'hypothesis': C.P2, 'ticker': 'A', 'entrySession': days[0]}]
    expected = {f'{i}x': [-.0011 * i, -.1, 0.] for i in (1, 2, 3)}
    bundle = {'status': 'COMPLETE_FROZEN_C2_LEDGER', 'calendar': days, 'decisions': [decision],
              'expectedDailyByCost': expected, 'dilutionEventCoverageFrom': history[0]}
    return bundle, events, market


def test_three_paths_compare_same_capital_costs_and_saved_next_candidate():
    bundle, events, market = portfolio_input()
    result = P.compare(bundle, events, market, draws=9)
    paths = result['paths']
    assert set(paths) == {'ORIGINAL', 'AVOID_NEXT', 'AVOID_ETF'}
    assert paths['AVOID_ETF']['1x']['daily'] == [0, 0, 0]
    assert paths['AVOID_NEXT']['1x']['daily'][1] == pytest.approx(.05)
    assert paths['ORIGINAL']['1x']['daily'][1] == pytest.approx(-.1)
    assert not paths['AVOID_NEXT']['1x']['inferenceEligible']  # invented three-day example


def test_a_baseline_mismatch_never_triggers_a_c2_reconstruction():
    bundle, events, market = portfolio_input()
    bundle['expectedDailyByCost']['1x'][1] = 123
    with pytest.raises(SourceBlocked, match='BASELINE_NOT_REPRODUCED'):
        P.compare(bundle, events, market, draws=9)


def test_pre_sample_filing_still_blocks_entry_and_unknown_lookback_is_not_empty():
    bundle, events, market = portfolio_input()
    events[0]['entrySession'] = market['signalCalendar'][-4]
    result = P.compare(bundle, events, market, draws=9)
    assert result['paths']['AVOID_ETF']['1x']['daily'] == [0, 0, 0]
    bundle.pop('dilutionEventCoverageFrom')
    with pytest.raises(SourceBlocked, match='LOOKBACK_BEFORE_PORTFOLIO_START'):
        P.compare(bundle, events, market, draws=9)


def test_missing_candidate_caps_or_liquidity_is_not_fabricated():
    bundle, events, market = portfolio_input()
    market['tradable']['B'].clear()
    with pytest.raises(SourceBlocked, match='EXECUTION_NOT_AVAILABLE'):
        P.compare(bundle, events, market, draws=9)
    bundle, events, market = portfolio_input()
    bundle['decisions'][0].pop('rankedCandidates')
    with pytest.raises(KeyError):
        P.compare(bundle, events, market, draws=9)


def test_preserved_v1_result_hashes_are_part_of_the_new_packet():
    packet = R.read(R.CONTRACT)
    for path in ('result-v1.json', 'result-postoutcome-v1.json', 'execution-claim.json', 'AUTHORIZATION.json'):
        assert 'research/broad_alpha_screen_v1/' + path in packet['protectedSha256']
    assert packet['promotionEligible'] is False
    assert Path('research/kr_capital_event_prospective_v1/spec-v1.json').is_file()


def test_all_four_cells_execute_on_invented_prices_and_reconcile_net_attribution(monkeypatch):
    import numpy as np
    from research.corporate_event_outcome_v1 import inference as I

    days = list(pd.bdate_range('2018-01-01', periods=800).strftime('%Y-%m-%d'))
    changes = .0002 + .005 * np.sin(np.arange(len(days)))
    index = dict(zip(days, np.cumprod(1 + changes)))
    events = [{'hypothesis': hyp, 'rcept_no': str(j), 'corp_code': ticker,
               'ticker': ticker, 'signalSession': days[299], 'entrySession': days[300],
               'independent': {'H126': True, 'H252': True}}
              for j, (hyp, ticker) in enumerate([(C.P2, 'A'), (C.K7, 'B')])]
    market = {'sessions': days, 'etf': index, 'levels': {'A': index, 'B': index},
              'tradable': {'A': set(days), 'B': set(days)}, 'terminal': {},
              'betaLevels': {'0': index, '1': index},
              'cash': {name: dict.fromkeys(days, 0.) for name in V.CASH}}
    original = I.synchronized_bootstrap
    monkeypatch.setattr(I, 'synchronized_bootstrap', lambda columns, block:
                        original(columns, block, draws=9, seed=319320))
    result = V.evaluate_four_cells(events, market)
    assert set(result) == {f'{h}:{z}' for h, z in V.CELLS}
    for key, cell in result.items():
        assert cell['slots'] == 1 and not cell['promotionEligible']
        summary = cell['summary']['BOK_POLICY_RATE:1x']
        assert summary['selectionDelta'] < 0  # identical gross assets, stock round-trip friction
        daily = cell['daily']['BOK_POLICY_RATE:1x']['D']
        assert summary['selectionDelta'] == pytest.approx(int(key.split(':H')[1]) * np.mean(daily))
        assert summary['simpleEtfExcess'] - summary['exposureTerm'] == pytest.approx(summary['selectionDelta'])
        assert summary['ci95'][0] <= summary['ci95'][1]
