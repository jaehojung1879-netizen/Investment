"""Real quoted decisions, finality barriers, and successor graph safety."""
import importlib.util
import json
from pathlib import Path

import pytest

from pipeline import kr_terminal_corporate_actions as TCA
from pipeline import kr_termination_inventory as INV
from pipeline import kr_terminal_action_document_parser as P

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('reconstruct', ROOT/'scripts/reconstruct_kr_terminal_documents.py')
BUILD = importlib.util.module_from_spec(spec)
spec.loader.exec_module(BUILD)


def book():
    return TCA.load_book(ROOT/'data/kr-terminal-corporate-actions.json')


def test_all_twenty_reviewed_real_term_patterns_reextract_exactly():
    reviews = json.loads((ROOT/'data/kr-terminal-document-review.json').read_text())['reviews']
    expected = {
        '000030.KS': 1.0, '000060.KS': 1.2657378, '000830.KS': 0.3500885,
        '001300.KS': 0.4425482, '002550.KS': 0.57287, '003450.KS': 0.1907312,
        '003600.KS': 0.7367839, '004940.KS': 0.1894302, '008560.KS': 0.1607327,
        '010520.KS': 0.8577607, '010620.KS': 0.4059146, '011160.KS': 0.2480895,
        '037620.KS': 2.9716317, '042670.KS': 0.1621707, '053000.KS': 1.0,
        '057050.KS': 6.357104, '079440.KS': 0.6601483,
    }
    cash_expected = {'003410.KS': 7000, '012510.KS': 120000, '115390.KS': 8750}
    for review in reviews:
        if not review['receiptNo']:
            continue
        ticker = review['oldSecurity']
        if ticker in cash_expected:
            assert P.cash_instead_of_stock(review['ratioQuote']) == cash_expected[ticker]
        else:
            assert BUILD.ratio_from_row(review['ratioQuote'], review['ratioMode']) == expected[ticker]
        assert P.korean_date(review['dateQuote']) is not None


def test_missing_later_body_corrections_preserve_candidates_but_block_final_terms():
    for action in book()['actions']:
        material = any(f['category'] == 'MATERIALLY_BLOCKING' for f in action['failedReceipts'])
        if material:
            assert action['documentedTerms'] is not None
            assert action['effectiveDate'] is None
            assert action['cashPerOldShare'] is None
            assert action['successorSharesPerOldShare'] is None
            assert action['finalTermsReceiptNumber'] is None
            matrix = INV.completeness_row(identity=None, action=action, dividends=None, last_trading_date=None)
            assert matrix['terminalConsiderationResolved'] == INV.BLOCKED
            assert matrix['terminalActionChainResolved'] == INV.BLOCKED


def test_cash_share_exchange_never_pays_the_valuation_ratio_or_parent_stock():
    cash = [r for r in book()['actions'] if r['actionType'] == TCA.CASH_SHARE_EXCHANGE]
    assert len(cash) == 3
    for row in cash:
        assert row['cashPerOldShare'] > 0
        assert row['successorSecurity'] is None
        assert row['successorSharesPerOldShare'] is None
        assert [c['type'] for c in row['considerationComponents']] == ['CASH']
        matrix = INV.completeness_row(identity=None, action=row, dividends=None, last_trading_date=None)
        assert matrix['exchangeRatioResolved'] == INV.NOT_APPLICABLE
        assert matrix['terminalConsiderationResolved'] == INV.READY


def test_subsidiary_merger_and_asset_sale_do_not_become_parent_share_termination():
    by = {r['oldSecurity']: r for r in book()['actions']}
    for ticker in ('067250.KS', '117930.KS'):
        assert by[ticker]['actionType'] == TCA.TERMINATION_TYPE_UNRESOLVED
        assert by[ticker]['cashPerOldShare'] is None
        assert by[ticker]['documentedTerms'] is None


def test_no_collected_decision_is_silently_promoted_to_proof_of_execution():
    for row in book()['actions']:
        assert row['finalTermsReceiptNumber'] is None
        assert row['reconstructionStatus'] != 'FULLY_RECONSTRUCTED'


def test_later_amendment_has_own_availability_not_original_effective_date():
    row = next(r for r in book()['actions'] if r['oldSecurity'] == '012510.KS')
    history = row['amendmentHistory']
    assert [r['receiptDate'] for r in history] == ['2026-04-27', '2026-05-11', '2026-05-19']
    assert history[-1]['supersedesReceiptNumber'] == '20260511000724'
    assert row['sourceReceiptDate'] == '2026-05-19'
    assert row['effectiveDate'] == '2026-06-30'


def test_missing_or_ambiguous_identity_never_uses_similar_name():
    universe = {'issuers': [{'corpName': 'KB금융', 'corpCode': '1',
                            'securities': [{'ticker': 'A.KS', 'names': ['KB금융']}]}]}
    assert BUILD.resolve_successor('KB금융지주', universe)[0] is None
    universe['issuers'].append({'corpName': 'KB금융', 'corpCode': '2',
                               'securities': [{'ticker': 'B.KS', 'names': []}]})
    assert BUILD.resolve_successor('KB금융', universe)[2] == 'AMBIGUOUS_EXACT_IDENTITY'


def edge(old, successors):
    components = tuple(TCA.build_consideration_component(
        component_type=TCA.COMPONENT_SUCCESSOR_SHARES, successor_security=successor,
        shares_per_old_share=1, source_receipt_number='r1', source_receipt_date='2020-01-01')
        for successor in successors)
    return TCA.build_record(old_security=old, action_type=TCA.MERGER_STOCK,
                            consideration_components=components)


def test_true_cycle_is_rejected_but_shared_successor_diamond_is_not():
    with pytest.raises(ValueError, match='cycle'):
        TCA.validate_book([edge('A', ['B']), edge('B', ['A'])])
    diamond = [edge('A', ['B', 'C']), edge('B', ['D']), edge('C', ['D'])]
    TCA.validate_book(diamond)
    assert TCA.chain_all_successors(diamond)['A']['cyclesDetected'] == []
    assert TCA.chain_all_successors(diamond)['A']['reachableSuccessors'] == ['B', 'C', 'D']


def test_real_coverage_and_failure_accounting():
    report = json.loads((ROOT/'docs/results/kr-terminal-document-parsing.json').read_text())
    assert (report['documentsAttempted'], report['documentsSucceeded'], report['documentsFailed']) == (130, 92, 38)
    assert len({r['receiptNo'] for r in report['documentsParsed']}) == 92
    assert all(r['documentSha256'] and r['tableRowsParsed'] for r in report['documentsParsed'])
