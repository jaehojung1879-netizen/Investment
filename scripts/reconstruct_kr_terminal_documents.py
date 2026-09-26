"""Reconstruct documented KR terminal terms from retained DART originals.

The review file selects subject and ratio orientation; every numeric term is
re-extracted from the cited real document. No return/price valuation runs.
A filed decision is not proof of execution. Missing subsequent corrections
block final economics, while their original terms remain inspectable.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import historical_store as HS  # noqa: E402
from pipeline import kr_terminal_action_document_parser as P  # noqa: E402
from pipeline import kr_terminal_corporate_actions as TCA  # noqa: E402


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def normalize_legal_name(value):
    # Legal-form/spacing normalization only, never abbreviations/transliteration.
    return re.sub(r'\s+|주식회사|\(주\)|㈜', '', value)


def resolve_successor(name, universe, explicit=None):
    matches = []
    for issuer in universe['issuers']:
        for security in issuer['securities']:
            names = [issuer['corpName'], *security.get('names', [])]
            exact = any(normalize_legal_name(n) == normalize_legal_name(name) for n in names)
            if (explicit and security['ticker'] == explicit) or (not explicit and exact):
                matches.append((security['ticker'], issuer['corpCode']))
    matches = sorted(set(matches))
    if len(matches) != 1:
        return None, None, 'AMBIGUOUS_EXACT_IDENTITY' if matches else 'NO_EXACT_IDENTITY_BRIDGE'
    return *matches[0], None


def term_row(structure, label, quote):
    rows = P.labeled_rows(structure, label)
    matched = [r for r in rows if ' | '.join(r['cells'][1:]) == quote
               or (len(r['cells']) > 1 and r['cells'][1] == quote)]
    if len(matched) != 1:
        raise ValueError(f'reviewed row missing/ambiguous: {label}: {quote}')
    return matched[0]


def ratio_from_row(value, mode):
    compact = re.sub(r'\s+', '', value)
    if mode == 'cash':
        return None
    if mode == 'cells':
        values = compact.split('|')
        if len(values) != 2 or values[0] != '1':
            raise ValueError('unsupported ratio table')
        return float(values[1])
    if mode == 'allocation':
        matches = re.findall(r'1주당.*?보통주식([0-9]+(?:\.[0-9]+)?)주', compact)
        if len(set(matches)) != 1:
            raise ValueError('ambiguous per-old-share allocation')
        return float(matches[0])
    # Orientation is explicitly reviewed, not guessed from which number is 1.
    # Common-share block is before (2) preferred-share terms in observed forms.
    common = compact.split('(2)')[0]
    pairs = re.findall(r'([0-9]+(?:\.[0-9]+)?):([0-9]+(?:\.[0-9]+)?)', common)
    if not pairs:
        raise ValueError('no ratio pair')
    # Multi-company transfer is permitted only by its reviewed exact first row;
    # the reviewed expected value and subject quote below are both mandatory.
    left, right = map(float, pairs[0])
    if mode == 'left' and right == 1:
        return left
    if mode == 'right' and left == 1:
        return right
    raise ValueError('unsupported ratio orientation')


def failure_classification(receipt, disclosure, review):
    # These exclusions were reviewed AFTER all successful documents were parsed.
    if receipt in {'20260429000294', '20260515100001'}:
        return 'REDUNDANT_SUPERSEDED_OR_UNNECESSARY', 'Later 20260519000237 restates the cash consideration and date after the correction order.'
    if receipt in {'20150721800301', '20150805800334'}:
        return 'REDUNDANT_SUPERSEDED_OR_UNNECESSARY', 'Subsidiary split, not the parent SK common-share merger; parent merger decision is retained.'
    if receipt == '20161103000360':
        return 'REDUNDANT_SUPERSEDED_OR_UNNECESSARY', 'Later merger absorbs KB Investment into the already wholly-owned Hyundai Securities; not its public-share exchange.'
    if disclosure['ticker'] == '117930.KS':
        return 'POTENTIALLY_MATERIAL', 'Business-transfer amendment may inform liquidation assets, but cannot by itself prove a shareholder payout; no zero recovery inferred.'
    if '첨부정정' in disclosure['reportName']:
        return 'POTENTIALLY_MATERIAL', 'Unavailable amended attachment; body terms retained but final attachment/supersession not established.'
    return 'MATERIALLY_BLOCKING', 'Later body correction to the selected terminal decision is unavailable; final consideration/effective date cannot be verified.'


def reconstruct(*, evidence_root, identity_path, review_path):
    store = evidence_root / 'ledger/kr-corporate-actions'
    docs = HS.read_jsonl(store / 'kr-terminal-action-documents.jsonl.gz')
    disclosures = HS.read_jsonl(store / 'kr-corporate-actions-disclosures.jsonl.gz')
    index = {r['receiptNo']: r for r in disclosures}
    raw = {d['receiptNo']: d for d in docs}
    state = json.loads((store / 'document-fetch-state.json').read_text())['receipts']
    identities = json.loads(identity_path.read_text())
    reviews = json.loads(review_path.read_text())['reviews']
    fetch = json.loads((store / 'fetch-state.json').read_text())['tickers']
    parsed, coverage = {}, []
    for doc in sorted(docs, key=lambda d: d['receiptNo']):
        if len(doc['members']) != 1:
            raise ValueError('new multi-member document pattern requires explicit review')
        member = doc['members'][0]
        if hashlib.sha256(member['text'].encode(member['encodingUsed'])).hexdigest() != member['sha256']:
            raise ValueError('original member hash mismatch')
        structure = P.document_structure(member['text'])
        parsed[doc['receiptNo']] = structure
        coverage.append({'receiptNo': doc['receiptNo'], 'ticker': doc['ticker'],
                         'documentSha256': member['sha256'], 'zipSha256': doc['zipSha256'],
                         'tableRowsParsed': len(structure['rows']), 'parseStatus': 'PARSED',
                         'use': 'CONTEXT_NOT_SELECTED_AS_TERMINAL_TERMS'})
    # Do not inspect/classify failures until the full successful corpus is parsed.
    by_review = {r['oldSecurity']: r for r in reviews}
    failures = []
    for receipt, entry in sorted(state.items()):
        if entry['status'] != 'FETCH_FAILED':
            continue
        category, reason = failure_classification(receipt, index[receipt], by_review[entry['ticker']])
        failures.append({'receiptNo': receipt, 'ticker': entry['ticker'], 'category': category,
                         'reason': reason, 'retainedError': entry.get('error') or entry.get('reason'),
                         'alternativeEvidence': 'All 92 retained documents examined; no later authoritative final terms substitute found.'
                         if category != 'REDUNDANT_SUPERSEDED_OR_UNNECESSARY' else 'See reason and selected successful decision.'})

    def cite(receipt, quote, field):
        doc = raw[receipt]
        return {'receiptNo': receipt, 'receiptDate': index[receipt]['receiptDate'],
                'documentSha256': doc['members'][0]['sha256'], 'zipSha256': doc['zipSha256'],
                'field': field, 'quote': quote,
                'url': f'https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt}'}

    actions = []
    for review in reviews:
        ticker, receipt = review['oldSecurity'], review['receiptNo']
        own_failures = [f for f in failures if f['ticker'] == ticker]
        materials = [f for f in own_failures if f['category'] == 'MATERIALLY_BLOCKING']
        blockers = []
        if not receipt:
            action = TCA.build_record(old_security=ticker, action_type=TCA.TERMINATION_TYPE_UNRESOLVED,
                                      old_issuer_corp_code=fetch[ticker]['corpCode'])
            blockers = [review['blocker']]
            action.update({'fieldEvidence': {}, 'documentedTerms': None,
                           'executionStatus': 'UNRESOLVED', 'identityBridge': None})
        else:
            source = parsed[receipt]
            normalized_text = ' '.join(source['text'].split())
            if normalize_legal_name(review['oldName']) not in normalize_legal_name(normalized_text):
                raise ValueError(f'old subject absent: {ticker}')
            all_row_text = [' | '.join(row['cells']) for row in source['rows']]
            if review['actionQuote'] not in all_row_text and review['actionQuote'] not in normalized_text:
                raise ValueError('action-type evidence missing')
            term_row(source, review['ratioLabel'], review['ratioQuote'])
            date_row = term_row(source, review['dateLabel'], review['dateQuote'])
            ratio = ratio_from_row(review['ratioQuote'], review['ratioMode'])
            if review['expectedRatio'] is not None and ratio != float(review['expectedRatio']):
                raise ValueError('reviewed ratio differs from extracted ratio')
            cash = P.cash_instead_of_stock(review['ratioQuote'])
            cash_only = review['actionType'] == TCA.CASH_SHARE_EXCHANGE
            if cash_only != (cash is not None):
                raise ValueError('cash/stock action-type mismatch')
            effective = P.korean_date(date_row['cells'][1])
            if not effective:
                raise ValueError('effective-date extraction failed')
            evidence = {
                'actionType': cite(receipt, review['actionQuote'], 'actionType'),
                'effectiveDate': cite(receipt, review['dateQuote'], 'effectiveDate'),
                'terminalConsideration': cite(receipt, review['ratioQuote'], 'terminalConsideration'),
            }
            if review['successorName'] not in normalize_legal_name(normalized_text):
                raise ValueError('successor legal name absent from original')
            explicit = review.get('explicitSuccessorCode')
            if explicit and explicit['quote'] not in parsed[explicit['receiptNo']]['text']:
                raise ValueError('explicit KRX code not in document')
            successor, successor_corp, identity_reason = resolve_successor(
                review['successorName'], identities, explicit['ticker'] if explicit else None)
            bridge = {'method': 'DOCUMENT_EXPLICIT_KRX_CODE' if explicit else 'UNIQUE_EXACT_LEGAL_OR_HISTORICAL_NAME',
                      'nameFromDocument': review['successorName'], 'identitySourcePath': 'ledger/dart-ownership-events/collection-universe.json',
                      'identitySourceSha256': digest(identity_path), 'reason': identity_reason}
            if explicit:
                bridge['documentEvidence'] = cite(explicit['receiptNo'], explicit['quote'], 'successorSecurity')
            if successor and not cash_only:
                evidence['successorSecurity'] = cite(receipt, review['successorName'], 'successorSecurity')
            if ratio is not None:
                evidence['successorSharesPerOldShare'] = cite(receipt, review['ratioQuote'], 'successorSharesPerOldShare')
            # Fractional payout must be an explicit rule, not a guessed close.
            fraction = None
            fraction_evidence = None
            candidates = [receipt] + [d['receiptNo'] for d in docs if d['ticker'] == ticker and d['receiptNo'] != receipt]
            for candidate in candidates:
                text = ' '.join(parsed[candidate]['text'].split())
                for match in re.finditer('단주', text):
                    snippet = text[max(0, match.start()-45):match.start()+320]
                    if '현금' in snippet and ('종가' in snippet or '매각' in snippet):
                        fraction, fraction_evidence = snippet, cite(candidate, snippet, 'fractionalShareTreatment')
                        break
                if fraction:
                    break
            # Do not import fractional terms from unrelated later actions.
            if fraction_evidence and fraction_evidence['receiptNo'] > receipt:
                fraction, fraction_evidence = None, None
            if fraction_evidence:
                evidence['fractionalShareTreatment'] = fraction_evidence
            # Original terms survive as candidates even when later amendments block them.
            documented = {'cashPerOldShare': cash, 'successorSharesPerOldShare': ratio,
                          'successorName': review['successorName'], 'effectiveDate': effective,
                          'receiptNo': receipt, 'receiptDate': index[receipt]['receiptDate'],
                          'scope': 'FILED_CONTRACTUAL_TERMS_NOT_PROOF_OF_EXECUTION'}
            if materials:
                blockers.append('FINAL_ECONOMIC_TERMS_AND_EFFECTIVE_DATE: later body corrections unavailable (' + ','.join(f['receiptNo'] for f in materials) + ')')
            if not cash_only and not successor:
                blockers.append('SUCCESSOR_SECURITY_IDENTITY: ' + str(identity_reason))
            if not cash_only and ratio != 1 and not fraction:
                blockers.append('FRACTIONAL_SHARE_CASH_IN_LIEU_RULE: not found in retained applicable decision')
            if any(f['category'] == 'POTENTIALLY_MATERIAL' for f in own_failures):
                blockers.append('AMENDMENT_ATTACHMENT_FINALITY: unavailable potentially material attachment')
            blockers.append('EXECUTION_CONFIRMATION: collected decisions state conditional/planned terms; no matching completion evidence establishes actual occurrence and final payment')
            action = TCA.build_record(
                old_security=ticker, action_type=review['actionType'],
                old_issuer_corp_code=fetch[ticker]['corpCode'],
                effective_date=None if materials else effective,
                cash_per_old_share=None if materials else cash,
                successor_security=None if cash_only else successor,
                successor_issuer_corp_code=None if cash_only else successor_corp,
                successor_shares_per_old_share=None if materials else ratio,
                fractional_share_treatment=fraction,
                cash_in_lieu_rule=fraction,
                source_receipt_number=receipt, source_receipt_date=index[receipt]['receiptDate'],
                sources=(f'DART:{receipt}',),
                unresolved_fields=('executionConfirmation',) + (('finalEconomicTerms',) if materials else ()))
            # build_record defaults final receipt to primary; overwrite explicitly
            # when later unavailable material prevents a claim of finality.
            action['finalTermsReceiptNumber'] = None
            action['latestReviewedTermsReceiptNumber'] = receipt
            action.update({'fieldEvidence': evidence, 'documentedTerms': documented,
                           'identityBridge': bridge, 'executionStatus': review['executionStatus']})
            # Use the normalized existing multi-component contract, not a new book.
            components = []
            if action['cashPerOldShare'] is not None:
                components.append(TCA.build_consideration_component(
                    component_type=TCA.COMPONENT_CASH, cash_amount=action['cashPerOldShare'],
                    source_receipt_number=receipt, source_receipt_date=index[receipt]['receiptDate']))
            if not cash_only and (successor or action['successorSharesPerOldShare'] is not None):
                components.append(TCA.build_consideration_component(
                    component_type=TCA.COMPONENT_SUCCESSOR_SHARES, successor_security=successor,
                    successor_issuer_corp_code=successor_corp,
                    shares_per_old_share=action['successorSharesPerOldShare'],
                    source_receipt_number=receipt, source_receipt_date=index[receipt]['receiptDate']))
            action['considerationComponents'] = components
            for row in coverage:
                if row['receiptNo'] == receipt:
                    row['use'] = 'REVIEWED_TERMINAL_CONTRACTUAL_TERMS'
        # Explicit same-event review selection. Every later version preserves its
        # own publication date and the original submission date stated in its body.
        history = []
        previous = None
        for r in review['terminalAmendmentReceipts']:
            correction_rows = [row for row in parsed[r]['rows'] if row['isCorrectionTable']]
            initial_rows = [row for row in parsed[r]['rows'] if row['cells']
                            and '최초제출일' in row['cells'][0].replace(' ', '')]
            history.append({**TCA.build_amendment_entry(
                receipt_number=r, receipt_date=index[r]['receiptDate'],
                report_name=index[r]['reportName'], supersedes_receipt_number=previous,
                fields_changed=tuple(row['cells'][0][:120] for row in correction_rows
                                     if row['cells'] and '정정전' not in ''.join(row['cells']).replace(' ', '')[:80])),
                'originalSubmissionDateEvidence': [row['cells'] for row in initial_rows],
                'correctionRows': [
                    {'cellsPreview': [cell[:400] for cell in row['cells']],
                     'fullCellsSha256': hashlib.sha256(json.dumps(row['cells'], ensure_ascii=False).encode()).hexdigest()}
                    for row in correction_rows],
                'scope': 'REVIEWED_SAME_TERMINAL_EVENT_PUBLICATION_SEQUENCE',
                'documentSha256': raw[r]['members'][0]['sha256']})
            previous = r
        action['amendmentHistory'] = history
        action['rawDocumentReceipts'] = sorted(d['receiptNo'] for d in docs if d['ticker'] == ticker)
        action['sources'] = [f'DART:{r}' for r in action['rawDocumentReceipts']]
        action['sourceReceiptNumbers'] = action['rawDocumentReceipts']
        action['blockingReasons'] = blockers
        action['failedReceipts'] = own_failures
        action['reconstructionStatus'] = 'PARTIALLY_RECONSTRUCTED' if receipt else 'BLOCKED'
        action['amendmentChainStatus'] = ('READY' if receipt and not any(
            f['category'] != 'REDUNDANT_SUPERSEDED_OR_UNNECESSARY' for f in own_failures) else 'BLOCKED')
        actions.append(action)
    TCA.validate_book(actions)
    chains = TCA.chain_all_successors(actions)
    if any(c['cyclesDetected'] for c in chains.values()):
        raise ValueError('cycle in reconstructed successor chain')
    book = {'schema': TCA.CONTRACT, 'version': 'kr-terminal-corporate-actions-v1',
            'actions': actions, 'successorChains': chains,
            'scope': 'DOCUMENTED_TERMS_WITH_EXPLICIT_FINALITY_AND_EXECUTION_BLOCKERS',
            'inputs': {'documentEvidenceCommit': '71c5128a01a7528536a8ff24c4e82d896363fec0',
                       'dividendEvidenceCommit': 'dfeb098e26ff71d3b8149199677417a78eda42d6',
                       'sourceHashes': {p.name: digest(p) for p in sorted(store.iterdir()) if p.is_file()},
                       'identityUniverseSha256': digest(identity_path), 'reviewSha256': digest(review_path)},
            'historicalOutcomesComputed': False}
    report = {'documentsParsed': coverage, 'failures': failures, 'documentsAttempted': len(state),
              'documentsSucceeded': len(docs), 'documentsFailed': len(failures),
              'parsedTableRows': sum(d['tableRowsParsed'] for d in coverage),
              'sourceHashes': book['inputs']['sourceHashes']}
    return book, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence-root', type=Path, required=True)
    parser.add_argument('--identity-universe', type=Path, required=True)
    parser.add_argument('--review', type=Path, default=ROOT/'data/kr-terminal-document-review.json')
    parser.add_argument('--output', type=Path, default=ROOT/'data/kr-terminal-corporate-actions.json')
    parser.add_argument('--report', type=Path, default=ROOT/'docs/results/kr-terminal-document-parsing.json')
    args = parser.parse_args()
    book, report = reconstruct(evidence_root=args.evidence_root, identity_path=args.identity_universe, review_path=args.review)
    for path, value in [(args.output, book), (args.report, report)]:
        path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)+'\n')
        path.with_suffix(path.suffix+'.sha256').write_text(digest(path)+'\n')
    print(json.dumps({'documentsParsed': len(report['documentsParsed']), 'actions': len(book['actions'])}))


if __name__ == '__main__':
    main()
