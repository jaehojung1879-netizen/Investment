"""Direct raw-source checks and fixed-path final-quote diagnostic. No refitting."""
import ast
from bisect import bisect_left
from collections import defaultdict
import gzip
import hashlib
import json

import numpy as np
import pandas as pd
import xlrd

from recompute import HERE, ROOT, SUB, BENCH, blob, replay, metrics


def rows(raw):
    return [json.loads(r) for r in gzip.decompress(raw).splitlines() if r]


def main():
    spec = json.loads((ROOT / 'research_specs/kr-model-overlay-portfolio-v1.json').read_text())
    c = pd.read_pickle('/workspace/audit-cache/closes.pkl')
    v = pd.read_pickle('/workspace/audit-cache/volumes.pkl')
    h = json.loads(gzip.decompress((SUB / 'results/holdings-all.json.gz').read_bytes()))
    pred = np.load(SUB / 'results/predictions-rebalance-pctile.npz')
    bydate, identity = defaultdict(list), {}
    for path, expected in spec['inputs']['universeBlobs'].items():
        raw = blob(path)
        digest = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        assert digest == expected
        identity[path] = digest
        for r in rows(raw):
            bydate[r['date']].append(r)
    snapshot_dates = sorted(bydate)
    snapshot_sets = {d: {r['ticker'] for r in sorted(rr, key=lambda z: (z['rank'], z['ticker']))[:120]} for d, rr in bydate.items()}
    bad = []
    for d, t in zip(pred['dates'], pred['tickers']):
        sd = snapshot_dates[bisect_left(snapshot_dates, str(d)) - 1]
        if not sd < d or t not in snapshot_sets[sd]:
            bad.append([str(d), str(t), sd])
    changes = sum(snapshot_sets[a] != snapshot_sets[b] for a, b in zip(snapshot_dates, snapshot_dates[1:]))
    acct = spec['inputs']['accounting']
    filing_count, mismatched_receipts, collected_later = 0, [], 0
    for name, expected in acct['gitBlobSha1'].items():
        raw = blob('ledger/fundamentals/kr-candidate-merged/' + name, acct['sourceCommit'])
        digest = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        assert digest == expected
        identity['accounting/' + name] = digest
        for r in rows(raw):
            filing_count += 1
            if {s[:8] for s in r.get('receiptNos', [])} != {r['availableFrom'].replace('-', '')}:
                mismatched_receipts.append({'id': r['id'], 'availableFrom': r['availableFrom']})
            collected_later += r.get('collectedAt', '')[:10] > r['availableFrom']
    raw_2026 = rows(blob('ledger/prices/kr/krx-prices-2026.jsonl.gz'))
    raw_map = {(r['date'], r['ticker']): r for r in raw_2026}
    # Independently derive final index scale using the prior source session.
    final = '2026-09-14'
    prior = '2026-09-11'
    corrections = []
    corrected = c.copy()
    for t in c.columns:
        old = raw_map.get((prior, t))
        new = raw_map.get((final, t))
        if t == BENCH or not old or not new or not old['volume'] > 0 or not new['volume'] > 0:
            continue
        if not np.isfinite(c.at[pd.Timestamp(prior), t]) or not np.isfinite(c.at[pd.Timestamp(final), t]):
            continue
        scale = c.at[pd.Timestamp(prior), t] / old['close']
        replacement = scale * new['close']
        ratio = c.at[pd.Timestamp(final), t] / replacement - 1
        corrections.append({'ticker': t, 'priorRawKrx': old['close'], 'finalRawKrx': new['close'],
                            'storedFinalIndex': c.at[pd.Timestamp(final), t], 'priorScaleFinalIndex': replacement,
                            'scaleGap': ratio})
        corrected.at[pd.Timestamp(final), t] = replacement
    official = json.loads((ROOT / 'docs/audits/kr-alpha-atlas-phase-c-integrity/final-session-source-integrity.json').read_text())
    match = {r['ticker']: r['Close'] for r in official['correctedFinalQuotes']}
    reproduction = max(abs(r['priorScaleFinalIndex'] / match[r['ticker']] - 1) for r in corrections if r['ticker'] in match)
    # ETF recomposition: raw issuer price spreadsheet + stated distribution rows,
    # not the corrected Close column. Historical entitlement completeness remains a limit.
    p = ROOT / 'docs/audits/kr-alpha-atlas-phase-c-integrity'
    sheet = xlrd.open_workbook(p / 'sources/issuer-standard.xls').sheet_by_index(0)
    quotes = {pd.to_datetime(str(sheet.cell_value(i, 0)), format='%Y%m%d'): float(sheet.cell_value(i, 1))
              for i in range(4, sheet.nrows) if str(sheet.cell_value(i, 0)).isdigit()}
    raw_etf = pd.Series(quotes).sort_index().loc['2012-01-02':'2026-09-14']
    bdoc = json.loads((p / 'benchmark-reconciliation-corrected.json').read_text())
    dividends = pd.Series({pd.Timestamp(r['exDate']): r['cashKrwPerUnit'] for r in bdoc['distributions']})
    tr = ((raw_etf + dividends.reindex(raw_etf.index).fillna(0)) / raw_etf.shift(1)).fillna(1).cumprod()
    submitted = pd.Series({pd.Timestamp(r['date']): r['Close'] for r in bdoc['correctedBenchmarkQuotes']})
    etf_gap = float((tr / submitted.reindex(tr.index) - 1).abs().max())
    events = json.loads((ROOT / 'data/bok-policy-rates.json').read_text())['events']
    rf = pd.Series({pd.Timestamp(r['date']): r['annualRatePct'] for r in events}).sort_index()
    rf = rf.reindex(rf.index.union(c.index)).ffill().reindex(c.index) / 100 / 252
    sensitivity = {}
    for view, sid in [('gated', 'RULE_INDUSTRY_MOMENTUM'), ('forced', 'XGB_CI_RANK_h1')]:
        n, _, turn, *_ = replay(corrected, v, h[view][sid])
        before, _, _, *_ = replay(c, v, h[view][sid])
        sensitivity[view + '-' + sid] = {'finalSourceOnlyFixedPath': metrics(n, rf, turn),
                                         'originalFinalNav': float(before.iloc[-1]),
                                         'navRelativeChange': float(n.iloc[-1] / before.iloc[-1] - 1),
                                         'scope': 'Final marks only, no re-selection; not a corrected tournament or certified action history'}
    mirae_holds = {view: {sid: [r['date'] for r in pp if '006800.KS' in r['weights']] for sid, pp in paths.items()
                          if any('006800.KS' in r['weights'] for r in pp)} for view, paths in h.items()}
    vendor_rows = ast.literal_eval((p / 'stock-sources/naver-006800.json').read_text().strip())
    vendor = {pd.to_datetime(r[0], format='%Y%m%d').strftime('%Y-%m-%d'): float(r[4]) for r in vendor_rows[1:]}
    before_date, action_date, ticker = '2026-03-13', '2026-03-16', '006800.KS'
    vendor_scale_change = (vendor[action_date] / raw_map[action_date, ticker]['close']) / (vendor[before_date] / raw_map[before_date, ticker]['close'])
    replay_scale_change = (c.at[pd.Timestamp(action_date), ticker] / raw_map[action_date, ticker]['close']) / (c.at[pd.Timestamp(before_date), ticker] / raw_map[before_date, ticker]['close'])
    cash_factor = 1 + 300 / vendor[before_date]
    mirae_event = {'ticker': ticker, 'date': action_date, 'cashKrw': 300.,
                   'vendorToKrxScaleChange': vendor_scale_change,
                   'replayToKrxScaleChange': replay_scale_change, 'singleCashFactor': cash_factor,
                   'replayScaleDivVendorScale': replay_scale_change / vendor_scale_change,
                   'primaryDeclarationShareEntitlement': .0073206,
                   'limit': 'No whole-security correction inferred from this single event'}
    # Rebuild label eligibility and fold counts directly from source closes/calendar.
    from pipeline.replay_calendar import sessions
    extended_days = sessions('2013-01-01', '2026-09-24', 'KR')
    weekly = pd.Series(extended_days, index=extended_days).groupby(extended_days.to_period('W')).max()
    weekly = [d for d in weekly if d <= pd.Timestamp('2026-09-14')]
    labrows = []
    price_array = c.to_numpy()
    ticker_col = {t: j for j, t in enumerate(c.columns)}
    for date in weekly:
        ds = str(date.date())
        member_date = snapshot_dates[bisect_left(snapshot_dates, ds) - 1]
        entry = c.index.get_loc(date) + 1
        for ticker in snapshot_sets[member_date]:
            item = {'date': ds, 'ticker': ticker}
            for horizon in [126, 252]:
                ex = entry + horizon
                item['exit' + str(horizon)] = str(c.index[ex].date()) if ex < len(c) else None
                item['valid' + str(horizon)] = bool(ex < len(c) and entry < len(c) and
                    np.isfinite(price_array[entry, ticker_col[ticker]]) and np.isfinite(price_array[ex, ticker_col[ticker]]))
            labrows.append(item)
    labels = pd.DataFrame(labrows)
    folds = json.loads((SUB / 'results/fold-records.json').read_text())
    fold_mismatches = []
    by_first = {}
    for rr in folds.values():
        for r in rr:
            if r.get('trainRows') and r['testFirst'] not in by_first:
                train = labels[(labels.date < r['testFirst']) & labels.valid126 & (labels.exit126 < r['testFirst'])]
                by_first[r['testFirst']] = [len(train), train.date.nunique(), train.exit126.max()]
    for sid, rr in folds.items():
        for r in rr:
            if r.get('trainRows'):
                counts = by_first[r['testFirst']]
                if counts != [r['trainRows'], r['trainDates'], r['trainLastExit']]:
                    fold_mismatches.append({'sid': sid, 'year': r['year'], 'independentCounts': counts})
    label_evidence = {'rows': len(labels), 'weeklyDates': len(weekly),
                       'H126Valid': int(labels.valid126.sum()), 'H252Valid': int(labels.valid252.sum()),
                       'H126LastSignal': labels.loc[labels.valid126, 'date'].max(),
                       'H252LastSignal': labels.loc[labels.valid252, 'date'].max(),
                       'H126FoldCountMismatches': fold_mismatches,
                       'limit': 'Eligibility/maturity only, not proof of correct terminal/corporate-action economics'}
    evidence = {'pinnedBlobIdentities': identity, 'membershipSnapshotCount': len(snapshot_dates),
                'membershipSetChanges': changes, 'uniqueTop120Ever': len(set.union(*snapshot_sets.values())),
                'predictionMembershipRowsChecked': len(pred['dates']), 'membershipViolations': bad,
                'filingsChecked': filing_count, 'independentLabels': label_evidence, 'miraeDividendCounterexample': mirae_event, 'receiptDateMismatches': mismatched_receipts,
                'filingsCollectedAfterReceipt': collected_later,
                'filingVintageLimit': 'Receipt-date gating verified in code; historical API values/revisions were not independently archived at release',
                'finalQuoteComparisons': corrections, 'gapAbove0p1pct': sum(abs(r['scaleGap']) > .001 for r in corrections),
                'priorScaleRepairMaxGapVsExistingAudit': reproduction,
                'etfRawIssuerPricePlusStatedCashMaxRelativeGap': etf_gap,
                'etfLimit': 'Stated historical cash rows reused; archived PDF entitlement completeness not independently re-parsed',
                'fixedPathFinalSourceDiagnostic': sensitivity, 'pathsHoldingWithheld006800': mirae_holds}
    (HERE / 'source-checks.json').write_text(json.dumps(evidence, indent=1, allow_nan=False, default=lambda x: x.item()) + '\n')
    print(json.dumps({k: v for k, v in evidence.items() if k not in ['pinnedBlobIdentities', 'finalQuoteComparisons', 'pathsHoldingWithheld006800']}, indent=1, default=lambda x: x.item()))


if __name__ == '__main__':
    main()
