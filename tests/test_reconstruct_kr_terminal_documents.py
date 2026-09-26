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


def _reused_name_universe():
    # Two issuers share an exact legal name at different times -- the real
    # shape observed live for 우리금융지주 (corpCode 00375302, delisted into
    # 우리은행 2014-12-01, vs corpCode 01350869, first listed 2019-03-04) and
    # 제일모직 (corpCode 00148328, delisted 2014-08-01, vs the entity now
    # named 삼성물산 carrying 제일모직 as a historical alias).
    return {'issuers': [
        {'corpName': '재사용이름', 'corpCode': 'OLD',
         'securities': [{'ticker': 'OLD.KS', 'names': [], 'delisted': '2014-08-01'}]},
        {'corpName': '재사용이름', 'corpCode': 'NEW',
         'securities': [{'ticker': 'NEW.KS', 'names': [], 'delisted': None}]},
    ]}


def test_a_candidate_already_delisted_before_the_document_is_excluded():
    universe = _reused_name_universe()
    ticker, corp, reason, note = BUILD.resolve_successor(
        '재사용이름', universe, as_of_date='2015-05-26')
    assert (ticker, corp, reason) == ('NEW.KS', 'NEW', None)
    assert 'OLD.KS/OLD' in note and 'delisted 2014-08-01' in note


def test_temporal_exclusion_never_narrows_when_both_candidates_are_still_live():
    # Neither candidate is delisted before the document -- stays ambiguous.
    universe = _reused_name_universe()
    universe['issuers'][0]['securities'][0]['delisted'] = '2020-01-01'
    ticker, corp, reason, note = BUILD.resolve_successor(
        '재사용이름', universe, as_of_date='2015-05-26')
    assert ticker is None and reason == 'AMBIGUOUS_EXACT_IDENTITY' and note is None


def test_temporal_exclusion_requires_as_of_date_and_never_applies_to_explicit_code():
    universe = _reused_name_universe()
    # No as_of_date supplied: falls back to the old, unresolved behaviour.
    assert BUILD.resolve_successor('재사용이름', universe)[2] == 'AMBIGUOUS_EXACT_IDENTITY'
    # An explicit document-stated KRX code always wins outright and never
    # goes through the temporal exclusion path.
    ticker, corp, reason, note = BUILD.resolve_successor(
        '재사용이름', universe, explicit='OLD.KS', as_of_date='2015-05-26')
    assert (ticker, corp, reason, note) == ('OLD.KS', 'OLD', None, None)


def test_real_book_resolves_both_reused_name_successors_by_temporal_exclusion():
    # 000030.KS's document names "우리금융지주" and 000830.KS's names
    # "제일모직" -- both exact names that also belong to an OLDER, already-
    # terminated issuer in this repository's own 22-security book (053000.KS
    # and 001300.KS respectively). Both must resolve to the entity that was
    # still capable of being formed/receiving shares on the citing date.
    by = {r['oldSecurity']: r for r in book()['actions']}
    assert by['000030.KS']['successorSecurity'] == '316140.KS'
    assert by['000030.KS']['identityBridge']['method'] == \
        'UNIQUE_EXACT_LEGAL_OR_HISTORICAL_NAME_TEMPORALLY_DISAMBIGUATED'
    assert by['000830.KS']['successorSecurity'] == '028260.KS'
    assert by['000830.KS']['identityBridge']['method'] == \
        'UNIQUE_EXACT_LEGAL_OR_HISTORICAL_NAME_TEMPORALLY_DISAMBIGUATED'


def test_independent_completion_evidence_resolves_execution_never_final_terms():
    row = next(r for r in book()['actions'] if r['oldSecurity'] == '000030.KS')
    assert row['executionStatus'] == 'CONFIRMED_BY_INDEPENDENT_COMPLETION_EVIDENCE'
    assert row['completionEvidence'] and row['completionEvidence'][0]['receiptNo'] == '20190111000457'
    assert 'executionConfirmation' not in row['unresolvedFields']
    # The independent evidence never substitutes for the still-missing body
    # corrections: final consideration/ratio/date stay blocked.
    assert row['effectiveDate'] is None
    assert row['successorSharesPerOldShare'] is None
    assert row['finalTermsReceiptNumber'] is None
    matrix = INV.completeness_row(identity=None, action=row, dividends=None, last_trading_date=None)
    assert matrix['terminalConsiderationResolved'] == INV.BLOCKED
    assert matrix['terminalActionChainResolved'] == INV.BLOCKED


def test_completion_evidence_review_schema_requires_receipt_and_quote():
    # The reconstruction script never guards this with a schema validator of
    # its own (every review field is checked by USE, the same discipline the
    # rest of this reviewed file already follows) -- but every entry actually
    # in the committed review file must carry both keys, so a hand-edit
    # cannot add a dangling citation with no receipt or no quote to check.
    reviews = json.loads((ROOT/'data/kr-terminal-document-review.json').read_text())['reviews']
    for review in reviews:
        for item in review.get('completionEvidence') or ():
            assert item.get('receiptNo') and item.get('quote') and item.get('note')


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
