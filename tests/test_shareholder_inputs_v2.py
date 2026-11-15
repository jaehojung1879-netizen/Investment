"""Invented shareholder markets plus saved filing identity regression (no returns)."""
import gzip
import json
from pathlib import Path

import pytest

from research.corporate_event_outcome_v1 import engine as E, engine_v2 as V
from research.corporate_event_outcome_v1 import shareholder_inputs_v2 as S


def dividend(no='20250101000001', **kw):
    return {'rcept_no': no, 'corp_code': 'ISSUER', 'stock_code': '000001',
            'report_nm': '현금ㆍ현물배당결정', 'dividendKind': '현금배당',
            'recordDate': '2024-12-31', 'dpsCommonKrw': '100',
            'exDateOfficial': '2024-12-27', **kw}


def test_parent_common_cash_is_not_overwritten_by_subsidiary_or_other_class():
    rows = [dividend(), dividend('20250102000001', report_nm='현금ㆍ현물배당결정(자회사의 주요경영사항)',
                                 dpsCommonKrw='40820465'),
            dividend('20250103000001', securityClass='PREFERRED', dpsCommonKrw='999')]
    out, flags, blocked = S.issuer_cash_dividends(rows, {'000001.KS': 'COMMON'})
    assert not blocked and out['000001.KS']['2024-12-27']['dps'] == 100
    assert flags == {'SUBSIDIARY_EXCLUDED': 1, 'OTHER_SECURITY_CLASS_EXCLUDED': 1}
    assert S.issuer_cash_dividends([dividend()], {'000001.KS': 'PREFERRED'})[2]


def test_duplicate_and_correction_require_unambiguous_lineage_and_publication_cut():
    row = dividend()
    assert not S.issuer_cash_dividends([row, row], {'000001.KS': 'COMMON'})[2]
    conflict = dividend('20250102000001', dpsCommonKrw='200')
    assert S.issuer_cash_dividends([row, conflict], {'000001.KS': 'COMMON'})[2]
    correction = {**conflict, 'amendment': True, 'amendsReceipt': row['rcept_no']}
    old = S.issuer_cash_dividends([row, correction], {'000001.KS': 'COMMON'}, known_before='2025-01-02')
    new = S.issuer_cash_dividends([row, correction], {'000001.KS': 'COMMON'}, known_before='2025-01-03')
    assert old[0]['000001.KS']['2024-12-27']['dps'] == 100
    assert new[0]['000001.KS']['2024-12-27']['dps'] == 200
    correction.pop('amendsReceipt')
    assert S.issuer_cash_dividends([row, correction], {'000001.KS': 'COMMON'})[2]


def test_unknown_dividend_is_blocked_while_explicit_zero_is_known():
    assert S.issuer_cash_dividends([dividend(dpsCommonKrw=None)], {'000001.KS': 'COMMON'})[2]
    assert S.issuer_cash_dividends([dividend(dpsCommonKrw='0')], {'000001.KS': 'COMMON'})[0]
    stock = dividend(kind='STOCK', dividendKind='주식배당')
    assert S.issuer_cash_dividends([stock], {'000001.KS': 'COMMON'})[2]
    assert not S.issuer_cash_dividends([stock], {'000001.KS': 'COMMON'},
                                     cited_stock_receipts=[stock['rcept_no']])[2]


def test_fiscal_year_is_not_inferred_from_a_shifted_record_date():
    prev, now = {'recordDate': '2023-12-31'}, {'recordDate': '2024-12-31'}
    assert S.annual_comparison(now, prev)['fiscalYear'] is None
    with pytest.raises(S.SourceBlocked, match='RECORD_DATE_SHIFT'):
        S.annual_comparison({'recordDate': '2025-03-14'}, prev)
    assert S.annual_comparison({'fiscalYearVerified': True, 'fiscalYear': 2024},
                               {'fiscalYearVerified': True, 'fiscalYear': 2023})['fiscalYear'] == 2024


def action(**kw):
    return {'date': '2025-01-03', 'confirmedOn': '2025-01-02', 'state': 'VERIFIED',
            'sourceSha256': 'a' * 64, 'kind': 'SPLIT', **kw}


def test_cited_split_stock_dividend_and_terminal_consideration_conserve_value():
    rows = [{'date': '2025-01-02', 'close': 100, 'volume': 10},
            {'date': '2025-01-03', 'close': 50, 'volume': 10}]
    assert S.cited_levels(rows, {}, [action(shareMultiplier=2)])[0]['2025-01-03'] == 1
    rows[-1]['close'] = 100 / 1.1
    assert S.cited_levels(rows, {}, [action(kind='STOCK_DIVIDEND', shareMultiplier=1.1)])[0]['2025-01-03'] == pytest.approx(1)
    rows[-1]['close'] = None
    lv, _, terminal = S.cited_levels(rows, {}, [action(kind='TERMINAL_CASH', terminalCashPerOldShare=60)])
    assert lv['2025-01-03'] == 0.6 and terminal['2025-01-03']['multiple'] == 0.6
    with pytest.raises(S.SourceBlocked, match='ECONOMIC_PACKAGE'):
        S.cited_levels(rows, {}, [action(kind='RIGHTS', shareMultiplier=2)])


def test_unknown_action_future_confirmation_and_ambiguous_cash_basis_block():
    rows = [{'date': '2025-01-02', 'close': 100, 'volume': 10},
            {'date': '2025-01-03', 'close': 50, 'volume': 10}]
    with pytest.raises(S.SourceBlocked, match='REQUIRES_CITED'):
        S.cited_levels(rows, {})
    with pytest.raises(S.SourceBlocked, match='NOT_KNOWN'):
        S.cited_levels(rows, {}, [action(shareMultiplier=2)], known_before='2025-01-02')
    with pytest.raises(S.SourceBlocked, match='CASH_BASIS_UNKNOWN'):
        S.cited_levels(rows, {'2025-01-03': {'dps': 5}}, [action(shareMultiplier=2)])
    lv = S.cited_levels(rows, {'2025-01-03': {'dps': 5, 'amountBasis': 'POST_ACTION_SHARE'}},
                        [action(shareMultiplier=2)])[0]
    assert lv['2025-01-03'] == 1.1


def test_saved_241560_parent_dps_regression_reads_filings_only():
    path = Path('research/corporate_event_readiness_v1/cohort/data/dividend-decisions-v1.jsonl.gz')
    with gzip.open(path, 'rt') as f:
        rows = [r for r in map(json.loads, f) if r.get('rcept_no') in
                {'20190724800532', '20190726800709', '20200210800791', '20200309800657'}]
    out, flags, blocked = S.issuer_cash_dividends(rows, {'241560.KS': 'COMMON'})
    assert len(rows) == 4 and flags['SUBSIDIARY_EXCLUDED'] == 2 and not blocked
    assert {d['dps'] for d in out['241560.KS'].values()} == {600}


def market():
    days = ['2025-01-02', '2025-01-03', '2025-01-06', '2025-01-07', '2025-01-08']
    levels = {'A': dict(zip(days, [100, 100, 100, 50, 50])), 'B': dict.fromkeys(days, 100)}
    etf, cash = dict.fromkeys(days, 100), dict.fromkeys(days, 0)
    slots = [E.Slot('a', 'A', 'A', 0, 1, 1, 1), E.Slot('b', 'B', 'B', 0, 4, 1, 1)]
    return days, levels, etf, cash, slots


def test_resumed_exit_is_sold_at_first_tradable_close_without_waiting_for_other_slots():
    days, levels, etf, cash, slots = market()
    tradable = {'A': {days[0], *days[2:]}, 'B': set(days)}
    old = E.simulate(slots, days, levels, etf, cash, tradable, {}, mult=0)
    new = V.simulate(slots, days, levels, etf, cash, tradable, {}, mult=0)
    assert old['book'][3] == -0.25 and new['book'][3] == 0
    assert new['resumedExits'] == [{'ticker': 'A', 'soldOn': days[2]}]
    assert V.simulate(slots, days, levels, etf, cash, {k: set(days) for k in levels}, {}, mult=1)['D'] == \
        E.simulate(slots, days, levels, etf, cash, {k: set(days) for k in levels}, {}, mult=1)['D']


def test_final_halt_extends_to_real_sale_and_unresolved_tail_is_never_filled():
    days, levels, etf, cash, slots = market()
    new = V.simulate(slots[:1], days, levels, etf, cash, {'A': {days[0], days[2]}}, {}, mult=0)
    assert new['complete'] and new['dates'][-1] == days[2] and new['extendedBeyondNominalExit']
    bad = V.simulate(slots[:1], days, levels, etf, cash, {'A': {days[0]}}, {}, mult=0)
    assert not bad['complete'] and bad['failure']['code'] == 'EXIT_STILL_UNTRADABLE_AT_SOURCE_CUTOFF'


def test_eb_title_does_not_assert_economic_or_realized_dilution():
    assert S.dilution_evidence('EB')['economicDilution'] == 'UNVERIFIED'
    own_shares = S.dilution_evidence('EB', {'economicDilution': 'NO_NEW_SHARES', 'sourceSha256': 'b' * 64})
    assert not own_shares['cohortMembershipChangedByTerms']


def test_cited_total_loss_reports_ruin_without_recreating_capital():
    days, levels, etf, cash, _ = market()
    slot = E.Slot('a', 'A', 'A', 0, 4, 1, 1)
    result = V.simulate([slot], days, levels, etf, cash, {'A': set(days)},
                         {'A': {'date': days[1], 'multiple': 0, 'sourceSha256': 'a' * 64}}, mult=0)
    assert result['complete'] and result['capitalExhausted']
    assert result['book'] == [0, -1, 0, 0, 0]


def test_halted_ex_date_never_reinvests_cash_or_guesses_a_post_action_price():
    rows = [{'date': '2025-01-02', 'close': 100, 'volume': 10},
            {'date': '2025-01-03', 'close': 100, 'volume': 0}]
    with pytest.raises(S.SourceBlocked, match='HALTED_ACTION_OR_DIVIDEND'):
        S.cited_levels(rows, {'2025-01-03': {'dps': 10}})
    with pytest.raises(S.SourceBlocked, match='HALTED_ACTION_OR_DIVIDEND'):
        S.cited_levels(rows, {}, [action(shareMultiplier=2)])
    lv, _, _ = S.cited_levels(rows, {}, [action(kind='TERMINAL_CASH', terminalCashPerOldShare=60)])
    assert lv['2025-01-03'] == .6  # actual cited cash consideration needs no market trade
