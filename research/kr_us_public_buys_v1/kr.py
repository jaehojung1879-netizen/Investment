"""DART transaction support and Korean public-buy study on the frozen weekly axis."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date as day
from decimal import Decimal, InvalidOperation
import gzip
import hashlib
import json
from pathlib import Path
import re

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

from research.kr_us_public_buys_v1.kr_collect import save, squeeze
from research.kr_us_replica_filter_v1 import kr as PRIOR
from research.kr_us_strategy_batch_v1 import common
from research.kr_us_strategy_batch_v1 import kr as OLD

HERE = Path(__file__).resolve().parent
INPUTS = HERE / 'inputs/KR'
OUT = HERE / 'results/KR'
ETF = PRIOR.ETF
CROSSWALK = INPUTS / 'pit-dart-crosswalk.json.gz'
SOURCE = 'DART_D002_PUBLIC_SEARCH_AND_VIEWER'
COVERAGE_FILE = 'dart-panel.json.gz'
VALUE = OLD.VALUE
TREND = 'A07_momentum12_1'


def gzip_json(path):
    with gzip.open(path, 'rt') as stream:
        return json.load(stream)


def pack_json(path, payload):
    path.write_bytes(gzip.compress((json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
                                    + '\n').encode(), mtime=0))


def eligible_universe(context, dates):
    stocks = {}
    features = ['industry', '_mcap', VALUE, TREND, 'b08Confirmed', *OLD.BUSINESS]
    for date in dates:
        row = context.by[date].set_index('ticker').sort_index()
        mask = row['_q'] & row.tradableAtSignal & ~row.isPreferredShare & ~row.index.isin(OLD.C.WITHHELD)
        mask &= row._mcap.gt(0) & np.isfinite(row._mcap) & row.industry.notna()
        stocks[date] = row.loc[mask, features].copy()
        pool = stocks[date]
        for feature in (VALUE, TREND):
            pool[feature + '_pct'] = pool.groupby('industry')[feature].rank(method='average', pct=True)
        known = np.isfinite(pool[OLD.BUSINESS]).all(axis=1) & np.isfinite(pool[VALUE])
        pool['confirmedKnown'] = pool['b08Confirmed'].where(known)
    return stocks


def crosswalk():
    source = gzip_json(CROSSWALK)
    by_ticker = defaultdict(list)
    for issuer in source['issuers']:
        for security in issuer['securities']:
            by_ticker[security['ticker']].append((issuer['corpCode'], security['listed'], security['delisted']))
    return by_ticker


def corp_at(by_ticker, ticker, date):
    d = f'{date:%Y-%m-%d}'
    candidates = {corp for corp, start, end in by_ticker[ticker] if (not start or start <= d) and (not end or d < end)}
    return next(iter(candidates)) if len(candidates) == 1 else None


def public_end(dates, publication, sessions):
    day = pd.Timestamp(publication)
    eligible = sessions.searchsorted(day, side='right')
    if eligible >= len(sessions):
        return None
    effective = sessions[eligible]
    weekly = dates.searchsorted(effective)
    return (effective, dates[weekly]) if weekly < len(dates) else None


def read_listings(raw):
    listings = {}
    months = {}
    for path in sorted((raw / 'parsed-lists').glob('*.json')):
        result = json.loads(path.read_text())
        scope = result['month']
        months[scope] = {k: v for k, v in result.items() if k != 'rows'}
        for row in result['rows']:
            receipt = row['receipt']
            if receipt in listings and row != listings[receipt]:
                raise ValueError(f'Inconsistent DART list result for {receipt}')
            listings[receipt] = row
    return listings, months


def plan_documents(raw, prices, context, dates, start, end):
    stocks = eligible_universe(context, dates)
    by_ticker = crosswalk()
    codes = {d: {corp_at(by_ticker, t, d) for t in s.index} for d, s in stocks.items()}
    listings, months = read_listings(raw)
    todo = []
    for row in sorted(listings.values(), key=lambda r: (r['publicDate'], r['receipt'])):
        public_month = row['publicDate'][:7]
        if not start <= public_month <= end or not months[public_month]['complete']:
            continue
        mapped = public_end(dates, row['publicDate'], prices['sessions'])
        if mapped is None or row['corpCode'] not in codes[mapped[1]]:
            continue
        todo.append({**row, 'eligibleDate': f'{mapped[0]:%Y-%m-%d}', 'decisionDate': f'{mapped[1]:%Y-%m-%d}'})
    save(raw / 'collection-plan.json', {'source': SOURCE, 'startMonth': start, 'endMonth': end, 'rows': todo})
    print('DART plan', len(todo), dict(Counter(row['publicDate'][:4] for row in todo)), flush=True)


def normalized_reporter(value):
    return hashlib.sha256(squeeze(value).casefold().encode()).hexdigest()[:20]


def amount(value):
    try:
        text = re.sub(r'[,\s+]', '', value)
        n = Decimal(text)
        return n if n.is_finite() else None
    except InvalidOperation:
        return None


def reported_date(value):
    parts = re.findall(r'\d+', value)
    if len(parts) != 3 or len(parts[0]) != 4:
        return None
    try:
        return day(*(int(x) for x in parts)).isoformat()
    except ValueError:
        return None


def classify(record, public_date):
    reason = squeeze(record['reason'])
    dtype = squeeze(record['security'])
    documented = reported_date(record['eventReported'])
    changed, price = amount(record['delta']), amount(record['price'])
    if reason in ('-', '해당사항없음', '해당없음') and documented is None and changed is None:
        return 'EXCLUDED_EMPTY_DETAIL', documented, changed, price
    if dtype not in ('보통주', '보통주식'):
        return ('EXCLUDED_NONCOMMON' if dtype and dtype != '-' else 'UNKNOWN_SECURITY'), documented, changed, price
    exclusions = ('주식매수선택권', '주식선택권', '스톡옵션', '옵션', '증여', '상속', '무상', '전환', '교환',
                  '합병', '분할', '감자', '유상증자', '배정', '배당', '보상', '임직원지급', '자기주식지급', '장외')
    if any(word in reason for word in exclusions):
        return 'EXCLUDED_' + ('OFF_EXCHANGE' if '장외' in reason else 'NONMARKET_ACQUISITION'), documented, changed, price
    if reason in ('장내매수(+)', '장내매수'):
        verdict = ('VERIFIED_MARKET_BUY' if documented is not None and documented <= public_date
                   and changed is not None and changed > 0 and price is not None and price > 0 else 'UNKNOWN_BUY_ECONOMICS')
    elif changed is not None and changed <= 0 or reason.startswith(('장내매도', '장외매도', '임원퇴임')):
        verdict = 'EXCLUDED_NONBUY'
    else:
        verdict = 'UNKNOWN_TRANSACTION_TYPE'
    return verdict, documented, changed, price


def parse_receipt(doc):
    if doc.get('status') != 'PARSED':
        return [], doc.get('status', 'DOC_NOT_COLLECTED')
    rows = []
    for raw in doc['transactions']:
        reason, reported, qty, price = classify(raw, doc['publicDate'])
        qty_text = str(qty.normalize()) if qty is not None else None
        price_text = str(price.normalize()) if price is not None else None
        rows.append({'status': reason, 'reportedSettlementDate': reported, 'transactionDate': None,
                     'transactionDateStatus': 'D002_CHANGE_DATE_IS_SETTLEMENT_FOR_EXCHANGE_TRADE',
                     'rawReason': raw['reason'], 'security': raw['security'], 'change': qty_text,
                     'unitPrice': price_text, 'sharesBefore': raw['before'], 'sharesAfter': raw['after'],
                     'cashConsiderationKRW': str(qty * price) if reason == 'VERIFIED_MARKET_BUY' else None,
                     'advancePlanReportDate': reported_date(raw.get('planDate') or '')})
    return rows, 'PARSED'


def event_key(doc, row):
    numbers = (amount(str(row[k])) for k in ('sharesBefore', 'change', 'sharesAfter', 'unitPrice'))
    return (doc['corpCode'], row['reportedSettlementDate'], 'COMMON',
            *(str(n.normalize()) if n is not None else None for n in numbers))


def process_documents(plan, docs, known_listings):
    """Apply receipt versions in publication order. Later versions never edit earlier decisions."""
    states, family_order, active, source_rows = {}, {}, {}, []
    by_weak = {}
    evidence = {}
    by_receipt = defaultdict(list)
    for item in plan:
        receipt = item['receipt']
        doc = docs.get(receipt, item)
        tx, status = parse_receipt(doc)
        amendment = '정정' in doc['form'] or '철회' in doc['form']
        linked = [r for r in doc.get('amendmentFamily', []) if r != receipt and r in evidence]
        anchor = family_order[min(linked, key=lambda r: family_order[r])] if linked else receipt
        prior = states.get(anchor)
        if status == 'PARSED' and amendment and prior is None:
            status = 'AMENDMENT_PRIOR_UNAVAILABLE'
        if status != 'PARSED':
            evidence[receipt] = status
            family_order[receipt] = anchor
            for row in tx:
                uncertain = {**row, 'receipt': receipt, 'corpCode': doc['corpCode'], 'publicDate': doc['publicDate'],
                             'familyAnchor': anchor, 'eventStatus': status}
                source_rows.append(uncertain)
                by_receipt[receipt].append(uncertain)
            continue
        value_by_key = {}
        for row in tx:
            key = event_key(doc, row)
            weak = (doc['corpCode'], normalized_reporter(doc['reporter']), row['reportedSettlementDate'], row['security'])
            event_status = row['status']
            result = {**row, 'receipt': receipt, 'corpCode': doc['corpCode'], 'publicDate': doc['publicDate'],
                      'eligibleDate': item['eligibleDate'], 'familyAnchor': anchor, 'eventStatus': event_status,
                      'officialPublicationClock': None, 'receiptPrefixDate': doc.get('receiptPrefixDate')}
            if event_status == 'VERIFIED_MARKET_BUY':
                old_key = by_weak.get(weak)
                if key in active:
                    result['eventStatus'] = 'DUPLICATE_ECONOMIC_TRANSACTION'
                elif amendment and prior is not None and old_key in prior:
                    result['eventStatus'] = 'AMENDED_PREVIOUSLY_IDENTIFIED_BUY'
                else:
                    active[key] = result
                    by_weak[weak] = key
                    result.update(eventStatus='CLEAN_FIRST_DISCLOSURE', withdrawnEligibleDate=None)
                basis_key = old_key if result['eventStatus'] == 'AMENDED_PREVIOUSLY_IDENTIFIED_BUY' else key
                value_by_key[basis_key] = active.get(basis_key, result)
            source_rows.append(result)
            by_receipt[receipt].append(result)
        if amendment and prior:
            for key in prior.keys() - value_by_key.keys():
                if key in active:
                    active[key]['withdrawnEligibleDate'] = item['eligibleDate']
        states[anchor] = value_by_key
        family_order[receipt] = anchor
        evidence[receipt] = status
    records = []
    for item in plan:
        r = item['receipt']
        doc = docs.get(r, {})
        related = [rel for rel in doc.get('amendmentFamily', []) if rel != r and rel in known_listings
                   and (known_listings[rel]['publicDate'], rel) < (item['publicDate'], r)]
        matching = by_receipt[r]
        records.append({k: v for k, v in item.items() if k not in ('reporter', 'issuerName')} |
                       {'reporterKey': normalized_reporter(item['reporter']), 'verdict': evidence[r],
                        'documentSource': doc.get('detail'), 'receiptSource': doc.get('main'),
                        'linkedPriorReceipts': related, 'transactionStatuses': dict(Counter(t['eventStatus'] for t in matching))})
    return records, source_rows


def freeze_panel(raw, path):
    plan = json.loads((raw / 'collection-plan.json').read_text())
    all_listings, months = read_listings(raw)
    docs = {item['receipt']: json.loads(file.read_text()) for item in plan['rows']
            if (file := raw / f'parsed-docs/{item["receipt"]}.json').is_file()}
    results, transactions = process_documents(plan['rows'], docs, all_listings)
    panel = {'source': SOURCE, 'months': months, 'planRange': [plan['startMonth'], plan['endMonth']],
             'planReceipts': len(plan['rows']), 'officialListRows': len(all_listings),
             'crosswalkSHA256': hashlib.sha256(gzip.decompress(CROSSWALK.read_bytes())).hexdigest(),
             'receiptRecords': results, 'transactionRows': transactions,
             'officialDataLimits': ['DATE_ONLY', 'EXCHANGE_D002_CHANGE_DATE_IS_SETTLEMENT',
                                    'REPORTING_RELATION_FROM_OFFICIAL_FORM_SCOPE',
                                    'NOT_FINAL_REPORT_ONLY', 'DELETED_FILINGS_NOT_INDEPENDENTLY_INVENTORIED']}
    pack_json(path, panel)
    print('DART panel frozen', len(docs), 'documents read', Counter(r['verdict'] for r in results), flush=True)
    return panel


def day_range_covered(months, previous, date):
    return all(months.get(str(m), {}).get('complete', False)
               for m in pd.period_range(previous, date - pd.Timedelta(days=1), freq='M'))


def event_audit(stocks, dates, panel):
    by_ticker = crosswalk()
    file_by_week = defaultdict(list)
    for record in panel['receiptRecords']:
        file_by_week[pd.Timestamp(record['decisionDate'])].append(record)
    clean = defaultdict(list)
    for row in panel['transactionRows']:
        if row['eventStatus'] == 'CLEAN_FIRST_DISCLOSURE':
            clean[row['receipt']].append(row)
    coverage, available, candidates = [], {}, []
    no_receipt_statuses = ('NO_D002_RECEIPT_ON_COMPLETE_LIST', 'NO_D002_RECEIPT_IN_ACQUIRED_DATE_SLICE')
    for i, date in enumerate(dates):
        source_complete = i > 0 and day_range_covered(panel['months'], dates[i - 1], date)
        source_slice = bool(file_by_week[date])
        if not source_complete and not source_slice:
            coverage.append({'date': date, 'sourceListComplete': False, 'sourceSliceObserved': False, 'strictCovered': False,
                             'candidateNames': len(stocks[date]), 'documentUnknownCandidates': None,
                             'classifiedUnknownCandidates': None, 'noReceiptNames': None, 'verifiedNames': None})
            available[date] = None
            candidates.extend({'date': date, 'ticker': t, 'sourceStatus': 'D002_LIST_NOT_ACQUIRED'} for t in stocks[date].index)
            continue
        scope = defaultdict(list)
        for f in file_by_week[date]:
            scope[f['corpCode']].append(f)
        statuses, signals, doc_missing = {}, {}, 0
        for ticker in stocks[date].index:
            code = corp_at(by_ticker, ticker, date)
            rows = scope[code]
            if code is None or any(r['verdict'] != 'PARSED' for r in rows):
                statuses[ticker] = 'DOCUMENT_UNOBTAINED_OR_LINKAGE_UNKNOWN'
                doc_missing += 1
                continue
            news = [t for r in rows for t in clean[r['receipt']]
                    if t['withdrawnEligibleDate'] is None or pd.Timestamp(t['withdrawnEligibleDate']) > date]
            if news:
                statuses[ticker] = 'VERIFIED_PUBLIC_BUY'
                signals[ticker] = max(t['publicDate'] for t in news)
            elif any(any(s.startswith('UNKNOWN') for s in r['transactionStatuses']) for r in rows):
                statuses[ticker] = 'TRANSACTION_TYPE_UNKNOWN'
            else:
                statuses[ticker] = 'PARSED_NO_CONFIRMED_BUY' if rows else no_receipt_statuses[not source_complete]
        # The panel's confirmed-name rule may be measured conditionally on successfully read issuers.
        enough_conditional = doc_missing < len(statuses) and (len(signals) > 0 or doc_missing == 0)
        strict = source_complete and doc_missing == 0
        scope_counts = Counter(statuses.values())
        ranking = sorted(signals, key=lambda t: (-pd.Timestamp(signals[t]).value, t))[:5]
        controls = [t for t, status in statuses.items() if status in ('PARSED_NO_CONFIRMED_BUY', *no_receipt_statuses)]
        coverage.append({'date': date, 'sourceListComplete': source_complete, 'sourceSliceObserved': source_slice,
                         'strictCovered': strict,
                         'candidateNames': len(statuses), 'documentUnknownCandidates': doc_missing,
                         'classifiedUnknownCandidates': scope_counts['TRANSACTION_TYPE_UNKNOWN'],
                         'noReceiptNames': sum(scope_counts[s] for s in no_receipt_statuses),
                         'verifiedNames': len(signals), 'selectedNames': len(ranking), 'conditionalPossible': enough_conditional,
                         'controlNames': len(controls), 'scopedReceiptCount': sum(map(len, scope.values()))})
        available[date] = (ranking, controls, strict) if enough_conditional else None
        for ticker, status in statuses.items():
            candidate_corp = corp_at(by_ticker, ticker, date)
            candidates.append({'date': date, 'ticker': ticker, 'corpCode': candidate_corp,
                               'sourceStatus': status, 'listCoversFullWeek': source_complete,
                               'controlEligibleInObservedWindow': ticker in controls,
                               'selectedRank': ranking.index(ticker) + 1 if ticker in ranking else None,
                               'lastVerifiedPublicDate': signals.get(ticker),
                               'officialReceipts': '|'.join(r['receipt'] for r in scope[candidate_corp])})
    return available, coverage, candidates


def build_pairs(stocks, ranking, peers, adjust=False):
    if not ranking:
        return [], []
    scope = stocks.loc[[*ranking, *peers], ['industry', '_mcap']].assign(passFilter=lambda x: x.index.isin(ranking))
    if not adjust:
        matches, rows = PRIOR.match(scope, ranking)
        return list(matches.pairs), rows
    rows, matched = [], {}
    vcol, tcol = VALUE + '_pct', TREND + '_pct'
    valid_stocks = stocks.dropna(subset=[vcol, tcol, 'confirmedKnown'])
    for sector, group in scope.loc[ranking].groupby('industry', sort=True):
        left = sorted(group.index)
        right = sorted(t for t in peers if t in valid_stocks.index and stocks.at[t, 'industry'] == sector)
        pair_details = {}
        n, m = len(left), len(right)
        cardinality_penalty = 4 * (n + 1)
        cost = np.full((n, m + n), float(cardinality_penalty))
        cost[:, :m] = 2 * cardinality_penalty
        for i, p in enumerate(left):
            if p not in valid_stocks.index:
                continue
            for j, f in enumerate(right):
                ratio = stocks.at[f, '_mcap'] / stocks.at[p, '_mcap']
                vd = abs(stocks.at[p, vcol] - stocks.at[f, vcol])
                td = abs(stocks.at[p, tcol] - stocks.at[f, tcol])
                if .5 <= ratio <= 2 and vd <= .25 and td <= .25 and stocks.at[p, 'confirmedKnown'] == stocks.at[f, 'confirmedKnown']:
                    cost[i, j] = abs(np.log(ratio)) + vd + td
                    pair_details[(i, j)] = ratio, vd, td
        ai, aj = linear_sum_assignment(cost)
        for i, j in zip(ai, aj, strict=True):
            p = left[i]
            row = {'passTicker': p, 'rank': ranking.index(p) + 1, 'industry': sector,
                   'heldValuePct': stocks.at[p, vcol], 'heldTrendPct': stocks.at[p, tcol],
                   'businessConfirmed': stocks.at[p, 'confirmedKnown'], 'passCap': stocks.at[p, '_mcap'],
                   'withinAdjustedCaliper': sum((i, k) in pair_details for k in range(m)),
                   'reason': 'UNMATCHED_ADJUSTED' if p in valid_stocks.index else 'MISSING_HELD_ADJUSTMENT_FIELDS'}
            if j < m:
                ratio, vd, td = pair_details[(i, j)]
                matched[p] = right[j]
                row.update(failTicker=right[j], reason='MATCHED', capRatio=ratio, valuePctDiff=vd, trendPctDiff=td,
                           failCap=stocks.at[right[j], '_mcap'])
            rows.append(row)
    return [(p, matched[p]) for p in ranking if p in matched], rows


def average(names, assets, field):
    if names and all(assets.get(t) is not None for t in names):
        return float(np.mean([assets[t][field] for t in names]))
    return np.nan


def calculate(prices, context, dates, available, stocks, out):
    horizons, audited_matches = {}, []
    matching = {}
    for date, observed in available.items():
        if observed is None:
            continue
        names, controls, strict = observed
        baseline, base_audit = build_pairs(stocks[date], names, controls)
        adjusted, adj_audit = build_pairs(stocks[date], names, controls, adjust=True)
        matching[date] = (names, baseline, adjusted, strict)
        for label, rows in (('base', base_audit), ('adjusted', adj_audit)):
            audited_matches.extend({'date': date, 'test': label, **row} for row in rows)
    PRIOR.write_csv(out / 'matching-audit.csv', audited_matches)
    checks = {}
    for h in (126, 252):
        records, missing, parts = [], [], []
        max_error, reproduction = 0., 0.
        old = pd.read_csv(PRIOR.SOURCE / f'cohorts-{h}.csv.gz', parse_dates=['date', 'entry', 'exit']).set_index('date')
        assert old.index.equals(dates)
        for date in dates:
            row = {'date': date, 'status': 'NO_CLASSIFIED_SIGNAL_OR_SOURCE_GAP', 'strict': False,
                   'picks': '', 'controls': '', 'adjustedControls': '', 'n': 0, 'fullMatch': False, 'adjustedMatch': False,
                   **dict.fromkeys(('total', 'selection', 'replacement', 'adjustedSelection', 'adjustedReplacement',
                                   'totalGross', 'selectionGross', 'replacementGross', 'adjustedSelectionGross',
                                   'adjustedReplacementGross', 'partialAdjustedSelection', 'etfNet', 'strategyNet', 'peerNet', 'adjustedPeerNet'), np.nan)}
            records.append(row)
            src = old.loc[date]
            row.update(entry=src.entry, exit=src.exit, mature=bool(src.mature), entryYear=src.entry.year)
            if date not in matching:
                continue
            names, baseline, adjusted, strict = matching[date]
            own, base, adj = tuple(names), tuple(f for _, f in baseline), tuple(f for _, f in adjusted)
            row.update(picks='|'.join(own), controls='|'.join(base), adjustedControls='|'.join(adj), n=len(own),
                       status='NOT_MATURED' if not src.mature else 'OBSERVED', strict=strict,
                       fullMatch=bool(own and len(base) == len(own)), adjustedMatch=bool(own and len(adj) == len(own)))
            if not src.mature:
                continue
            assets = {}
            for ticker in sorted({ETF, *own, *base, *adj}):
                payoff, issue = OLD.asset_payoff(prices['closes'], context.px, ticker, src.entry, src.exit)
                assets[ticker] = payoff
                if issue:
                    missing.append({'date': date, 'entry': src.entry, 'exit': src.exit, 'ticker': ticker, 'reason': issue})
            etf = assets[ETF]
            assert etf is not None
            reproduction = max(reproduction, abs(etf['net'] - src['KR:ETF_net']))
            for metric, suffix in (('net', ''), ('gross', 'Gross')):
                benchmark = etf[metric]
                vol = .2 * (average(own, assets, metric) - benchmark) if own else 0.
                row['total' + suffix] = vol
                if suffix == '':
                    row.update(etfNet=benchmark, strategyNet=benchmark + vol)
                    if adjusted and not row['adjustedMatch'] and all(assets[p] and assets[f] for p, f in adjusted):
                        row['partialAdjustedSelection'] = .2 / len(own) * sum(assets[p]['net'] - assets[f]['net']
                                                                             for p, f in adjusted)
                for matched, peers, selection, replacement, value in (
                    (row['fullMatch'], base, 'selection', 'replacement', 'peerNet'),
                    (row['adjustedMatch'], adj, 'adjustedSelection', 'adjustedReplacement', 'adjustedPeerNet')):
                    if not matched or not np.isfinite(vol):
                        continue
                    rep = .2 * (average(peers, assets, metric) - benchmark)
                    row[selection + suffix], row[replacement + suffix] = vol - rep, rep
                    if suffix == '':
                        row[value] = benchmark + rep
                    if np.isfinite(rep):
                        max_error = max(max_error, abs(row[selection + suffix] + rep - vol))
            if not np.isfinite(row['total']):
                row['status'] = 'UNRESOLVED_SELECTED_PAYOFF'
                continue
            for i, t in enumerate(own):
                selection = (.2 / len(own)) * (assets[t]['net'] - assets[base[i]]['net']) if np.isfinite(row['selection']) else np.nan
                contribution = (.2 / len(own)) * (assets[t]['net'] - etf['net'])
                parts.append({'date': date, 'entryYear': src.entry.year, 'ticker': t,
                              'strict': strict, 'total': contribution, 'selection': selection})
        frame = pd.DataFrame(records).set_index('date')
        measured = frame.total.notna()
        active = frame.n.gt(0)
        strict = measured & frame.strict
        matched = np.isfinite(frame.selection)
        adjmatched = np.isfinite(frame.adjustedSelection)
        masks = {'own': strict, 'active': strict & active, 'paired': strict & matched,
                 'adjusted': strict & adjmatched, 'bothMatches': strict & matched & adjmatched,
                 'conditionalOwn': measured, 'conditionalActive': measured & active, 'conditionalPaired': matched,
                 'conditionalAdjusted': adjmatched, 'conditionalBothMatches': matched & adjmatched}
        fields = ('total', 'selection', 'replacement', 'adjustedSelection', 'adjustedReplacement', 'totalGross', 'selectionGross',
                  'replacementGross', 'adjustedSelectionGross', 'adjustedReplacementGross', 'partialAdjustedSelection',
                  'etfNet', 'strategyNet', 'peerNet', 'adjustedPeerNet')
        data = {key: {f: common.stats(frame[f], h, mask) for f in fields} for key, mask in masks.items()}
        data['coverage'] = {'matureWeeks': int(frame.mature.sum()), 'strictMatureWeeks': int(strict.sum()),
                            'completeWeekPriceUnresolved': int((frame.strict & frame.mature & frame.total.isna()).sum()),
                            'strictActiveWeeks': int((strict & active).sum()), 'strictActiveMatchedWeeks': int((strict & matched).sum()),
                            'conditionalActiveWeeks': int((measured & active).sum()),
                            'conditionalActiveMatchedWeeks': int(matched.sum()), 'conditionalActiveAdjustedWeeks': int(adjmatched.sum()),
                            'tradeStatus': frame.status.value_counts().to_dict(),
                            'entryExitPriceFailures': len(missing)}
        data['sensitivity'] = {}
        at = pd.DataFrame(parts, columns=['date', 'entryYear', 'ticker', 'strict', 'total', 'selection'])
        for name, mask in (('strictTotal', strict), ('strictSelection', strict & matched),
                           ('conditionalTotal', active & measured), ('conditionalSelection', matched)):
            metric = 'selection' if name.endswith('Selection') else 'total'
            scope = at.loc[at.date.isin(frame.index[mask]) & at[metric].notna()]
            if scope.empty:
                data['sensitivity'][name] = {'topName': None, 'topYear': None}
                continue
            name_sum = scope.groupby('ticker')[metric].sum().sort_values(ascending=False, kind='stable')
            yr_sum = scope.groupby('entryYear')[metric].sum().sort_values(ascending=False, kind='stable')
            top_name, top_year = name_sum.index[0], int(yr_sum.index[0])
            name_dates = set(scope.loc[scope.ticker.eq(top_name), 'date'])
            data['sensitivity'][name] = {'topName': top_name, 'topYear': top_year,
                                        'entryYearContribution': yr_sum.to_dict(),
                                        'excludeTopNameDates': common.stats(frame[metric], h, mask & ~frame.index.isin(name_dates)),
                                        'excludeTopEntryYear': common.stats(frame[metric], h, mask & frame.entryYear.ne(top_year))}
        PRIOR.write_csv(out / f'cohorts-{h}.csv.gz', frame.reset_index())
        PRIOR.write_csv(out / f'price-failures-{h}.csv', pd.DataFrame(missing, columns=['date', 'entry', 'exit', 'ticker', 'reason']))
        PRIOR.write_csv(out / f'contributions-{h}.csv.gz', at)
        assert max_error < 1e-11 and reproduction < 1e-9
        horizons[str(h)] = data
        checks[str(h)] = {'threePartMaxError': max_error, 'oldEtfNetMaxError': reproduction}
    return horizons, matching, checks


def longest(dates, valid):
    best, current = [], []
    for d in dates:
        if d in valid:
            current.append(d)
            if len(current) > len(best):
                best = current[:]
        else:
            current = []
    return best


def nav(prices, ctx, dates, matches, out):
    session_axis = prices['sessions']
    bench = pd.Series(ctx.px.etf, index=session_axis)
    strategy_weeks = {d for d, (_, _, _, strict) in matches.items() if strict}
    control_weeks = {d for d, (n, m, _, strict) in matches.items() if strict and len(n) == len(m)}
    results = {}
    for sample, candidates in (('strategyOnly', strategy_weeks), ('paired', control_weeks)):
        period = longest(dates, candidates)
        results[sample] = {'continuousObservedWeeks': len(period)}
        for L in (26, 52):
            if len(period) < L:
                results[sample][str(L)] = {'status': 'INSUFFICIENT_CONTIGUOUS_DISCLOSURE_WEEKS', 'required': L}
                continue
            start, end = (OLD.M.next_session(session_axis, d) for d in (period[0], period[-1]))
            books = {'etf': {d: {ETF: 1.} for d in period},
                     'strategy': {d: OLD.make_book(matches[d][0], 'FIXED20') for d in period}}
            if sample == 'paired':
                books['peer'] = {d: OLD.make_book([f for _, f in matches[d][1]], 'FIXED20') for d in period}
            ledgers, navs = {}, {}
            for name, weekly in books.items():
                schedules = [OLD.A.books_to_schedule({d: weekly[d] for d in period[i::L]}, session_axis) for i in range(L)]
                issues = OLD.nav_diagnostic(ctx.px, schedules, start, end)
                if any(not ctx.px.tradable[ctx.px.pos[t], ctx.px.col[ticker]] or
                       (ticker in ctx.px.terminal and ctx.px.terminal[ticker] < ctx.px.pos[end])
                       for schedule in schedules for t, weights in schedule.items() for ticker in weights if ticker != ETF):
                    ledgers[name] = {'status': 'UNRESOLVED_EXECUTION_OR_TERMINAL', 'turnoverDiagnostic': issues}
                    continue
                result = OLD.A.multi_account(ctx.px, schedules, start, end, prices['rf'], bench)
                navs[name] = result.pop('nav')
                ledgers[name] = result
            PRIOR.write_csv(out / f'nav-{sample}-L{L}.csv.gz', pd.DataFrame(navs).rename_axis('date').reset_index())
            results[sample][str(L)] = {'status': 'MEASURED', 'books': ledgers}
    return results


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--stage', choices=('plan', 'freeze', 'run'), default='run')
    cli.add_argument('--scratch', type=Path, default=Path('/workspace/s2-inputs'))
    cli.add_argument('--raw', type=Path, default=Path('/workspace/public-buys-inputs/kr'))
    cli.add_argument('--panel', type=Path, default=INPUTS / COVERAGE_FILE)
    cli.add_argument('--out', type=Path, default=OUT)
    cli.add_argument('--start-month', default='2023-01')
    cli.add_argument('--end-month', default='2025-08')
    args = cli.parse_args(argv)
    if args.stage == 'freeze':
        freeze_panel(args.raw, args.panel)
        return
    prices, context, dates = PRIOR.load_inputs(args.scratch)
    if args.stage == 'plan':
        plan_documents(args.raw, prices, context, dates, args.start_month, args.end_month)
        return
    args.out.mkdir(parents=True, exist_ok=True)
    panel = gzip_json(args.panel)
    stocks = eligible_universe(context, dates)
    available, coverage, candidates = event_audit(stocks, dates, panel)
    PRIOR.write_csv(args.out / 'coverage-by-week.csv', coverage)
    PRIOR.write_csv(args.out / 'candidate-audit.csv.gz', candidates)
    PRIOR.write_csv(args.out / 'receipt-audit.csv.gz', panel['receiptRecords'])
    PRIOR.write_csv(args.out / 'transaction-audit.csv.gz', panel['transactionRows'])
    if available.get(pd.Timestamp('2023-01-06')) is not None:
        unresolved = {row['corpCode']: row['ticker'] for row in candidates
                      if row['date'] == pd.Timestamp('2023-01-06')
                      and row['sourceStatus'] == 'DOCUMENT_UNOBTAINED_OR_LINKAGE_UNKNOWN'}
        minimum = [{'kind': 'UNCOVERED_LIST_BOUNDARY', 'publicFrom': '2022-12-29', 'publicThrough': '2022-12-31',
                    'required': 'Official complete D002 search pages, then eligible document sections if listed'}]
        minimum.extend({'kind': 'MISSING_TRANSACTION_DOCUMENT', 'publicFrom': row['publicDate'],
                        'publicThrough': row['publicDate'], 'ticker': unresolved[row['corpCode']],
                        'corpCode': row['corpCode'], 'receipt': row['receipt'], 'required': row['verdict'],
                        'officialUrl': 'https://dart.fss.or.kr/dsaf001/main.do?rcpNo=' + row['receipt']}
                       for row in panel['receiptRecords'] if row['decisionDate'] == '2023-01-06'
                       and row['corpCode'] in unresolved and row['verdict'] != 'PARSED')
        PRIOR.write_csv(args.out / 'minimum-missing-2023-01-06.csv', minimum)
    horizons, matching, checks = calculate(prices, context, dates, available, stocks, args.out)
    summary = {'market': 'KR', 'source': SOURCE, 'decisionWeeks': len(dates),
               'coveredStudyWeeks': sum(r['strictCovered'] for r in coverage),
               'officialListCoveredWeeks': sum(r['sourceListComplete'] for r in coverage),
               'weights': {k: sum(len(m[0]) == k and m[3] for m in matching.values()) for k in range(6)},
               'conditionalWeights': {k: sum(len(m[0]) == k for m in matching.values()) for k in range(6)},
               'coverage': {'sourceRange': panel['planRange'], 'completeListMonths': sum(m['complete'] for m in panel['months'].values()),
                            'officialListReceipts': panel['officialListRows'], 'scopedReceipts': panel['planReceipts'],
                            'scopedReceiptStatuses': dict(Counter(r['verdict'] for r in panel['receiptRecords'])),
                            'sourceRows': dict(Counter(r['eventStatus'] for r in panel['transactionRows'])),
                            'listedPublicDateDiffersFromReceiptPrefix': sum(r['publicDate'] != r['receiptPrefixDate'] for r in panel['receiptRecords'])},
               'horizons': horizons, 'ledgers': nav(prices, context, dates, matching, args.out),
               'priceVerification': checks}
    OLD.dump(args.out / 'summary.json', summary)
    print('KR public disclosure results', summary['coverage'], 'complete weeks', summary['coveredStudyWeeks'], flush=True)


if __name__ == '__main__':
    main()
