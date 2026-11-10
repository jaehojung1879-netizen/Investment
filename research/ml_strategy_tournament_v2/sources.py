"""Exact original KRX observations plus cited ETF cash; unknown events block.

Legacy adjusted prices are isolated in diagnostics and never used by accounting.
The 2018 Mirae subscription right is a boundary, not a fitted adjustment.
"""
from __future__ import annotations
from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

import pandas as pd

from pipeline import replay_calendar as RC
from pipeline.kr_alpha_atlas_benchmark_audit import issuer_prices
from pipeline import kr_alpha_atlas_mirae_repair as MIRAE
from .identity import HERE, ROOT, file_hash

CONFIG = json.loads((HERE / 'config.json').read_text())
PIN = CONFIG['rawSourceCommit']
ETF = '069500.KS'
BASE = ROOT / 'docs/audits/kr-alpha-atlas-phase-c-integrity'


def git_blob(path):
    return subprocess.check_output(['git', 'cat-file', 'blob', PIN + ':' + path], cwd=ROOT)


def selections():
    src = ROOT / 'research/ml_strategy_tournament_v1/results/holdings-all.json.gz'
    h = json.loads(gzip.decompress(src.read_bytes()))
    out = {}
    for candidate in CONFIG['candidates']:
        sid, view = candidate['id'], candidate['view']
        out[sid] = [{'date': r['date'], 'weights': {**r['weights'], ETF: r['etf']},
                     'sourceView': view} for r in h[view][sid]]
    return out


def load_raw(*, cache=Path('/workspace/ml-v2-sources')):
    cache.mkdir(exist_ok=True, parents=True)
    decisions = selections()
    tickers = {t for ds in decisions.values() for d in ds for t, w in d['weights'].items() if w > 0}
    days = [str(d.date()) for d in RC.sessions(CONFIG['start'], CONFIG['end'], 'KR')]
    allowed_days = set(days)
    quotes, hashes = defaultdict(dict), {}
    probe_dates = {'2026-09-10', '2026-09-11', '2026-09-14'}
    raw_probe, legacy_probe = {}, {}
    # Never trust a previous pickle just because it exists. Each source blob is
    # pinned by Git identity; source cache is exact-byte and hash checked.
    for year in range(2016, 2027):
        path = f'ledger/prices/kr/krx-prices-{year}.jsonl.gz'
        raw = git_blob(path)
        hashes[PIN + ':' + path] = hashlib.sha256(raw).hexdigest()
        for line in gzip.decompress(raw).splitlines():
            r = json.loads(line)
            if r['date'] in probe_dates:
                raw_probe[r['date'], r['ticker']] = r
            if r['ticker'] not in tickers or r['date'] not in allowed_days:
                continue
            key = r['date'], r['ticker']
            if key[1] in quotes[key[0]]:
                raise ValueError('DUPLICATE_RAW_SECURITY_DATE')
            quotes[key[0]][key[1]] = {'close': float(r['close']), 'volume': float(r['volume']),
                                    'basis': 'RAW_UNADJUSTED'}
    issuer = BASE / 'sources/issuer-standard.xls'
    prices, _ = issuer_prices(issuer)
    # issuer_prices returns a raw official market-price Series.
    if isinstance(prices, pd.DataFrame):
        prices = prices['close'] if 'close' in prices else prices['Close']
    for day in days:
        price = float(prices.loc[day])
        existing = quotes[day].get(ETF)
        if existing and abs(existing['close'] - price) > 1e-6:
            raise ValueError('OFFICIAL_ETF_KRX_PRICE_DISAGREEMENT')
        quotes[day][ETF] = {'close': price, 'volume': (existing or {}).get('volume', 1.), 'basis': 'RAW_UNADJUSTED'}
    hashes[str(issuer.relative_to(ROOT))] = file_hash(issuer)
    distribution_path = HERE / 'vendor/069500-official-distributions-328.json'
    distribution_rows = json.loads(distribution_path.read_text())
    hashes[str(distribution_path.relative_to(ROOT))] = file_hash(distribution_path)
    events = defaultdict(list)
    full_calendar = RC.sessions('2002-01-01', '2026-12-31', 'KR')
    bdoc = json.loads((BASE / 'benchmark-reconciliation-corrected.json').read_text())
    known = {r['recordDate']: r for r in bdoc['distributions']}
    seen = set()
    for row in distribution_rows:
        record = pd.to_datetime(row['basicD'], format='%Y%m%d')
        payment = str(pd.to_datetime(row['payD'], format='%Y%m%d').date())
        ex = str(full_calendar[full_calendar.searchsorted(record, side='left') - 1].date())
        if ex < CONFIG['start'] or ex > CONFIG['end']:
            continue
        if str(record.date()) in seen:
            raise ValueError('DUPLICATE_OFFICIAL_ETF_DISTRIBUTION')
        seen.add(str(record.date()))
        check = known.get(str(record.date()))
        if not check or check['exDate'] != ex or check['cashKrwPerUnit'] != float(row['dividA']):
            raise ValueError('ETF_CASH_HISTORY_DOES_NOT_MATCH_PINNED_OFFICIAL_CROSSCHECK')
        events[ex].append({'ticker': ETF, 'date': ex, 'kind': 'CASH_DIVIDEND', 'dps': float(row['dividA']),
                           'amountBasis': 'PRE_ACTION_SHARE', 'paymentDate': payment,
                           'confirmedOn': ex, 'state': 'VERIFIED', 'sourceSha256': file_hash(distribution_path),
                           'availabilityLimit': 'Outcome entitlement record, not a prospective announcement-time feature'})
    expected_count = sum(CONFIG['start'] <= r['exDate'] <= CONFIG['end'] for r in bdoc['distributions'])
    assert len(seen) == expected_count
    # Observed vendor events are *red flags*, not independently qualified
    # cash or split entitlements. Do not round floating DPS into official cash.
    manifest_raw = git_blob('ledger/historical/replay-v16/inputs.json')
    manifest = json.loads(manifest_raw)
    from .identity import digest
    assert digest({k: v for k, v in manifest.items() if k != 'sha256'}) == manifest['sha256'] == 'f0781292f508a123c234ded6d28aa8e84a0dc3cc29500e14989dc0b68f53b4d2'
    hashes[PIN + ':ledger/historical/replay-v16/inputs.json'] = hashlib.sha256(manifest_raw).hexdigest()
    legacy_rows = []
    for component, refs in sorted(manifest['components'].items()):
        if not component.startswith(('price/', 'benchmark/')) or component in ('price/source', 'benchmark/source'):
            continue
        for ref in refs:
            data = gzip.decompress(git_blob('ledger/replay-inputs/objects/' + ref + '.json.gz'))
            assert hashlib.sha256(data).hexdigest() == ref
            decoded = json.loads(data)
            legacy_rows.extend(r for r in decoded if r.get('ticker') in tickers)
            for r in decoded:
                if r.get('ticker', '').endswith('.KS') and r.get('date') in probe_dates:
                    legacy_probe[r['date'], r['ticker']] = r
    legacy = pd.DataFrame(legacy_rows)
    legacy['date'] = pd.to_datetime(legacy['date'])
    if legacy.duplicated(['date', 'ticker']).any():
        raise ValueError('DUPLICATE_LEGACY_SECURITY_DATE')
    legacy_days = RC.sessions('2013-01-01', CONFIG['end'], 'KR')
    legacy_close = legacy.pivot(index='date', columns='ticker', values='Close').reindex(legacy_days)
    legacy_volume = legacy.pivot(index='date', columns='ticker', values='Volume').reindex(legacy_days)
    legacy_close[ETF] = pd.Series({pd.Timestamp(r['date']): r['Close'] for r in bdoc['correctedBenchmarkQuotes']}).reindex(legacy_days)
    final_scales = []
    for (date, ticker), row in raw_probe.items():
        if date != '2026-09-14' or ticker == ETF or row['volume'] <= 0:
            continue
        prev = raw_probe.get(('2026-09-11', ticker))
        old = legacy_probe.get(('2026-09-11', ticker))
        end = legacy_probe.get((date, ticker))
        if not prev or prev['volume'] <= 0 or not old or not end:
            continue
        expected = old['Close'] / prev['close'] * row['close']
        final_scales.append({'ticker': ticker, 'legacyFinal': end['Close'], 'rawBasisFinal': expected,
                             'relativeDifference': end['Close'] / expected - 1})
    final_probe = {'matchingSecurities': len(final_scales),
                   'scaleGapsAbove0p1pct': sum(abs(r['relativeDifference']) > .001 for r in final_scales),
                   'quotes': final_scales,
                   'cause': 'FINAL_VENDOR_QUOTE_BASIS_INCONSISTENT_WITH_PREVIOUS_KRX_SCALE',
                   'rootCause': 'ACQUISITION_TIMING_VS_VENDOR_REVISION_NOT_ESTABLISHED_ORIGINAL_RESPONSE_NOT_SAVED',
                   'repair': 'RAW_KRX_AND_OFFICIAL_ISSUER_QUOTES_USED_DIRECTLY_NO_UNKNOWN_ADJUSTMENT_FACTOR'}
    vendor_count = 0
    for component, refs in sorted(manifest['components'].items()):
        if not component.startswith('corporate-events/'):
            continue
        for ref in refs:
            data = gzip.decompress(git_blob('ledger/replay-inputs/objects/' + ref + '.json.gz'))
            assert hashlib.sha256(data).hexdigest() == ref
            for row in json.loads(data):
                if 'date' not in row:
                    continue
                t, d = row.get('ticker'), row['date']
                if t not in tickers or t == ETF or d not in allowed_days:
                    continue
                if not row.get('dividend') and float(row.get('split') or 1.) == 1:
                    continue
                vendor_count += 1
                events[d].append({'ticker': t, 'date': d, 'kind': 'BLOCKED',
                                   'reason': 'VENDOR_ACTION_WITHOUT_COMPLETE_CITED_CASH_SHARE_SETTLEMENT',
                                   'vendorDividend': row.get('dividend'), 'vendorSplit': row.get('split'),
                                   'confirmedOn': d, 'state': 'UNRESOLVED', 'sourceSha256': ref})
    q = MIRAE.read_correction()
    MIRAE.verify_raw_quotes(ROOT, q)
    hashes[str(Path(MIRAE.CORRECTION))] = file_hash(ROOT / MIRAE.CORRECTION)
    for boundary in q['quarantinedSessions']:
        if boundary in allowed_days:
            events[boundary].append({'ticker': MIRAE.TICKER, 'date': boundary, 'kind': 'BLOCKED',
                                     'state': 'UNRESOLVED', 'confirmedOn': q['rightsEvent']['announcementDate'],
                                     'sourceSha256': hashes[MIRAE.CORRECTION],
                                     'reason': 'UNVALUED_UNLISTED_PREFERRED_SUBSCRIPTION_RIGHT_2018'})
    # Complete official ETF cash/pay dates; stock completeness is not inferred
    # from silence in the Yahoo/DART collector or the 25-name sample.
    admission = {t: {'status': 'SOURCE_BLOCKED', 'reason': 'COMPLETE_FISCAL_CASH_ACTION_TERMINAL_COVERAGE_NOT_PROVEN'} for t in tickers}
    admission[ETF] = {'status': 'COMPLETE', 'from': CONFIG['start'], 'through': CONFIG['end'],
                      'basis': 'OFFICIAL_RAW_ISSUER_PRICES_AND_FULL_CITED_DISTRIBUTIONS_WITH_PAY_DATES'}
    return {'finalSourceProbe': final_probe, 'legacyClose': legacy_close, 'legacyVolume': legacy_volume, 'sessions': days, 'quotes': dict(quotes), 'events': dict(events), 'admission': admission,
            'sourceHashes': hashes, 'vendorActionRedFlags': vendor_count,
            'shareholderSourceStatus': 'SOURCE_BLOCKED_FOR_STOCKS', 'miraeSourceReassessment': {
                'connectedSegmentsVerified': True, 'unvaluedBoundary': q['quarantinedSessions'],
                'fullSecurityBlanketRefusalInAudit330': 'SUPERSEDED_BY_EXISTING_CITED_SEGMENT_REPAIR',
                'doesNotProveCompleteDistributionCoverage': True}}, decisions
