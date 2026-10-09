"""Outcome-blind quote/corporate-action correction, outside preserved Phase C v1.

The stock auditor compares same-session source quotation scales only. It never
computes a stock holding return, label, IC, prediction or portfolio performance.
The ETF audit alone may compute annual returns, as explicitly authorized.
"""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess

import pandas as pd

from pipeline import replay_calendar as RC
from pipeline.kr_alpha_atlas_phase_c import contract
from pipeline.kr_alpha_atlas_benchmark_audit import (
    adjusted_index, annual_comparison, benchmark_only, issuer_prices, vendor_prices, verified_sources,
)

BASE = 'docs/audits/kr-alpha-atlas-phase-c-integrity'
SAMPLE = BASE + '/stock-price-audit-sample.json'
CORRECTION = BASE + '/corrected-inputs.json'
BENCHMARK_REPORT = BASE + '/benchmark-reconciliation-corrected.json'
STOCK_REPORT = BASE + '/stock-price-integrity.json'


def checked_files(root, records, directory):
    for row in records:
        p = Path(root) / directory / row['path']
        if not p.resolve().is_relative_to((Path(root) / directory).resolve()):
            raise ValueError('SOURCE_PATH_ESCAPES_SNAPSHOT')
        if contract.file_hash(p) != row['sha256']:
            raise ValueError('PRICE_INTEGRITY_SOURCE_MUTATED')


def recovered_cash(root):
    """Read explicit payments, validating overlaps; never infer an absent payment."""
    root = Path(root)
    directory = root / BASE / 'benchmark-history'
    manifest = json.loads((directory / 'sources.json').read_text())
    checked_files(root, manifest['files'], BASE + '/benchmark-history')
    amounts, sources, tables = {}, {}, []
    for item in manifest['files']:
        if item['httpStatus'] != 200:
            continue  # refusal body is evidence, not a distribution table
        txt = directory / (Path(item['path']).stem + '.txt')
        if contract.file_hash(txt) != item['textSha256']:
            raise ValueError('ISSUER_TABLE_EXTRACTION_CHANGED')
        text = txt.read_text()
        if '069500' not in text or 'KR7069500007' not in text:
            raise ValueError('WRONG_OFFICIAL_ETF_REPORT')
        section = text[text.index('투자분배금 지급현황'):].split('※ 포트폴리오')[0]
        pairs = re.findall(r'(20\d{2}\.\d{2}\.\d{2})\s+(\d+)\s*(?:\n|$)', section)
        if len(pairs) != 6:
            raise ValueError('EXPECTED_SIX_PAYMENT_TABLE')
        table = {}
        for date, amount in pairs:
            date, amount = date.replace('.', '-'), float(amount)
            if date in amounts and amounts[date] != amount:
                raise ValueError('ISSUER_PAYMENT_CONFLICT')
            amounts[date] = table[date] = amount
            sources.setdefault(date, []).append(item['path'])
        if tables and not (set(table) & set(tables[-1])):
            raise ValueError('OFFICIAL_PAYMENT_HISTORY_GAP')
        tables.append(table)
    payload = json.loads((root / BASE / 'sources/issuer-dividends.json').read_text())
    latest = {str(pd.Timestamp(r['basicD']).date()): float(r['dividA']) for r in payload['dividList']}
    if not tables or not (set(latest) & set(tables[-1])):
        raise ValueError('ISSUER_CURRENT_HISTORY_NOT_BRIDGED')
    for date, amount in latest.items():
        if date in amounts and amounts[date] != amount:
            raise ValueError('ISSUER_PAYMENT_CONFLICT')
        amounts[date] = amount
        sources.setdefault(date, []).append('issuer-dividends.json')
    # Coverage follows linked most-recent-payment tables through March 2022 and
    # the complete 20-payment current API, not a calendar zero-dividend guess.
    days = RC.sessions('2011-01-01', '2026-12-31', 'KR')
    result = []
    for date, amount in sorted(amounts.items()):
        pos = int(days.searchsorted(pd.Timestamp(date), side='left')) - 1
        if pos < 0 or amount <= 0:
            raise ValueError('INVALID_OFFICIAL_PAYMENT')
        result.append({'ticker': '069500.KS', 'recordDate': date,
                       'exDate': str(days[pos].date()), 'cashKrwPerUnit': amount,
                       'sourceRefs': sources[date]})
    return result


def reconcile_benchmark(root):
    """Only the registered ETF; no stock-minus-benchmark or stock returns."""
    root = Path(root)
    spec = contract.load(root)
    directory = root / BASE / 'sources'
    sources = verified_sources(directory)
    market, _ = issuer_prices(directory / 'issuer-standard.xls')
    vendor = vendor_prices(directory / 'naver-benchmark.json')
    cash = recovered_cash(root)
    cutoff = spec['developmentCutoff']
    market = market[(market.index >= '2012-01-01') & (market.index <= cutoff)]
    cash = [r for r in cash if '2012-01-01'<=r['exDate'] <= cutoff]
    vendor=vendor[(vendor.index>=market.index[0]) & (vendor.index<=cutoff)]
    if vendor.index[-1]!=market.index[-1]:
        raise ValueError('INDEPENDENT_BENCHMARK_ENDPOINT_MISMATCH')
    # Economic choice fixed by shareholder accounting, not reconciliation size:
    # gross ex-date cash entitlement reinvested at that session's market close.
    official = adjusted_index(market, cash, shareholder=True)
    independent_raw = raw_from_adjusted_benchmark(vendor,cash)
    independent = adjusted_index(independent_raw,cash,shareholder=True)
    sessions = RC.sessions('2011-01-01', cutoff, 'KR')
    comparisons = annual_comparison(official, independent, sessions, list(range(2013, 2027)),
                                    coverage_from='2012-01-01', cutoff=cutoff)
    for row in comparisons:
        row.update(internalSourceSha256=sources['files']['issuerPrices']['sha256'],
                   independentPriceSha256=sources['files']['vendorPrices']['sha256'],
                   definition='GROSS_ETF_MARKET_PRICE_TOTAL_RETURN_EX_DATE_CLOSE_CASH_REINVESTMENT',
                   explanation='Official raw ETF market prices versus an independent Naver price-basis reconstruction; both apply the same authoritative gross payments once and the same ex-date close-reinvestment formula. Cash source is shared and disclosed.')
    vendor_recipe=adjusted_index(market,cash)
    holder_diagnostics = []
    for row in comparisons:
        a, b = row['anchorSession'], row['endSession']
        holder_diagnostics.append({'year': row['year'], 'status': 'NOT_COMPARABLE',
                                   'officialCashReinvestedReturn': float(official[b] / official[a] - 1),
                                   'differenceFromAdjustedIndexPp': float((official[b]/official[a] - vendor_recipe[b]/vendor_recipe[a])*100),
                                   'reason': 'Actual ex-date cash-reinvestment formula differs from vendor adjustment formula. Not used to select the definition or to relax the threshold.'})
    return {'auditClass': 'BENCHMARK_ONLY_INTEGRITY', 'ticker': '069500.KS',
            'threshold': 0.005, 'requiredYears': spec['chronology']['evaluationYears'],
            'sourceIdentities': sources, 'distributions': cash, 'coverageFrom': '2012-01-01',
            'correctedBenchmarkQuotes':[{'date':d,'Close':float(p)} for d,p in official.items()],
            'economicDefinition':'P_t/P_previous plus gross cash entitlement D_t/P_previous, equivalently (P_t+D_t)/P_previous, reinvested at ex-date close. Before investor distribution tax; ETF expenses already embedded in market prices; registered benchmark trade costs remain separate.',
            'independentDefinitionMapping':'Naver adjusted-close cash factor is reversed using only authoritative ETF distributions and its own latest unadjusted endpoint. Raw-source quote precision is approximate; distributions are shared official observations, not independently observed twice.',
            'independentEndpoint':{'session':vendor.index[-1],'vendorOwnQuote':float(vendor.iloc[-1]),'officialRawQuote':float(market.iloc[-1]),'nextScheduledRecordDate':'2026-10-31','sourceCaptureBeforeNextDistribution':True},
            'annualComparisons': comparisons, 'shareholderDefinitionDiagnostics': holder_diagnostics,
            'aggregateStatus': 'PASS' if all(r['status']=='PASS' for r in comparisons) else 'FAIL',
            'limits': ['Annual reconciliation verifies gross ETF market-price shareholder total return, not NAV or KOSPI200.',
                       'Ex-date close reinvestment recognizes the distribution receivable before the payment date; this is a total-return-index convention, not an investor cash-execution receipt or a financed trading strategy.',
                       'Issuer annual NAV performance tables are not used as market-price total returns.',
                       'Historical payment records are reconstructed from official archived six-payment tables; no missing payment becomes zero.'],
            'realHistoricalAlphaOutcomeReads': 0, 'realForwardLabels': 0,
            'realHistoricalModelFits': 0, 'realPortfolioBacktests': 0,
            'formalExecutionDispatches': 0, 'permanentExecutionLocksCreated': 0}


def raw_from_adjusted_benchmark(adjusted,cash,*,ticker='069500.KS'):
    """Reverse a documented ETF vendor cash factor; ETF only, no stock returns.

    The captured terminal quote is before the next scheduled distribution and is
    the vendor's own raw endpoint. Earlier raw quotes solve the vendor factor
    identity backwards. Both the anchor and shared cash source are disclosed.
    """
    benchmark_only(ticker)
    if not adjusted.index.is_unique or not adjusted.index.is_monotonic_increasing or adjusted.isna().any() or (adjusted<=0).any():
        raise ValueError('INVALID_ADJUSTED_BENCHMARK_SOURCE')
    amounts={r['exDate']:r['cashKrwPerUnit'] for r in cash}
    raw=adjusted.copy()
    for i in range(len(raw)-1,0,-1):
        raw.iloc[i-1]=raw.iloc[i]*adjusted.iloc[i-1]/adjusted.iloc[i]+amounts.get(raw.index[i],0.0)
    return raw


def pinned_sample(root, sample):
    """Select source rows only for the already committed audit sample/windows."""
    root = Path(root)
    spec = contract.load(root)
    pin = sample['sourceCommit']
    if pin != spec['phaseBIdentity']['inputs']['sourceCommit']:
        raise ValueError('STOCK_SAMPLE_SOURCE_CHANGED')
    ids = {r['ticker'] for r in sample['securities']}
    def inside(date):
        return any(w['start'] <= date <= w['end'] for w in sample['sourceWindows'])
    raws, prices, events, hashes = {t: {} for t in ids}, {t: {} for t in ids}, {t: [] for t in ids}, {}
    for year in sorted({int(w[x][:4]) for w in sample['sourceWindows'] for x in ('start', 'end')}):
        path = f'ledger/prices/kr/krx-prices-{year}.jsonl.gz'
        blob = subprocess.check_output(['git', 'cat-file', 'blob', pin+':'+path], cwd=root)
        sha = hashlib.sha1(b'blob '+str(len(blob)).encode()+b'\0'+blob).hexdigest()
        if sha != spec['phaseBIdentity']['inputs']['barLedgerBlobSha1'][path]:
            raise ValueError('PINNED_KRX_QUOTE_IDENTITY_CHANGED')
        hashes[path] = sha
        for line in gzip.decompress(blob).splitlines():
            row = json.loads(line)
            if row['ticker'] in ids and inside(row['date']):
                raws[row['ticker']][row['date']] = row
    manifest = json.loads(subprocess.check_output(['git','cat-file','blob',pin+':ledger/historical/replay-v16/inputs.json'],cwd=root))
    if manifest['sha256'] != spec['phaseBIdentity']['inputs']['replayManifestSha256']:
        raise ValueError('PINNED_REPLAY_MANIFEST_CHANGED')
    for name, refs in sorted(manifest['components'].items()):
        if not (name.startswith('price/20') or name.startswith('corporate-events/20')):
            continue
        month = name.split('/')[1]
        if not any(w['start'][:7] <= month <= w['end'][:7] for w in sample['sourceWindows']):
            continue
        for ref in refs:
            blob = subprocess.check_output(['git','cat-file','blob',pin+':ledger/replay-inputs/objects/'+ref+'.json.gz'],cwd=root)
            content = gzip.decompress(blob)
            if hashlib.sha256(content).hexdigest() != ref:
                raise ValueError('PINNED_PRICE_OR_EVENT_CHANGED')
            hashes[name] = ref
            for row in json.loads(content):
                if row.get('ticker') in ids and inside(row['date']):
                    if name.startswith('price/'):
                        prices[row['ticker']][row['date']] = row
                    else:
                        events[row['ticker']].append(row)
    return raws, prices, events, hashes


def quote_scale_reading(vendor, raw, internal, events, window):
    days = sorted(d for d in raw if window['start'] <= d <= window['end'] and
                  d in vendor and raw[d]['close'] > 0)
    if not days:
        return {'status': 'NO_MATCHING_SOURCE_SESSIONS', 'matchingSessions': 0}
    scale = [float(vendor[d]/raw[d]['close']) for d in days]
    actions = []
    known_factor = 1.0
    anchor = internal[days[0]]['Close']/raw[days[0]]['close'] if days[0] in internal else None
    residuals = []
    event_map = {r['date']:r for r in events}
    for pos, date in enumerate(days):
        if pos:
            event = event_map.get(date,{})
            dividend = float(event.get('dividend') or 0)
            known_factor *= float(event.get('split') or 1)/(1-dividend/raw[days[pos-1]]['close'])
        if anchor is not None and date in internal:
            residuals.append((abs((internal[date]['Close']/raw[date]['close'])/anchor/known_factor-1),date))
    for event in sorted(events, key=lambda r:r['date']):
        d = event['date']
        if d not in days or days.index(d)==0 or d not in internal:
            continue
        previous = days[days.index(d)-1]
        if previous not in internal:
            continue
        vendor_step = (vendor[d]/raw[d]['close'])/(vendor[previous]/raw[previous]['close'])
        internal_step = (internal[d]['Close']/raw[d]['close'])/(internal[previous]['Close']/raw[previous]['close'])
        cash = float(event.get('dividend') or 0)
        factor = 1/(1-cash/raw[previous]['close']) if cash else 1.0
        actions.append({'date':d, 'previousSession':previous, 'cashKrw':cash,
                        'registeredSplit':event.get('split'), 'vendorToKrxQuoteScaleChange':float(vendor_step),
                        'internalToKrxQuoteScaleChange':float(internal_step), 'singleCashFactor':float(factor),
                        'cashAlreadyAdjusted': bool(cash>0 and abs(vendor_step-factor)<1e-5),
                        'ordinaryDividendUnadjusted':bool(cash>0 and abs(vendor_step-1)<1e-4)})
    return {'status':'SOURCE_LEVEL_OBSERVATIONS_ONLY','matchingSessions':len(days),
            'vendorToKrxScaleMin':min(scale),'vendorToKrxScaleMax':max(scale),
            'corporateActionObservations':actions,
            'knownActionQuoteScaleResidualMax':max(residuals)[0] if residuals else None,
            'largestQuoteScaleResidualDate':max(residuals)[1] if residuals else None,
            'stockHoldingReturnsCalculated':0}


def audit_stocks(root):
    root = Path(root)
    sample = json.loads((root/SAMPLE).read_text())
    source = json.loads((root/BASE/'stock-sources/sources.json').read_text())
    if source['sampleSha256'] != contract.file_hash(root/SAMPLE):
        raise ValueError('PREDECLARED_SAMPLE_CHANGED')
    checked_files(root, source['files'], BASE+'/stock-sources')
    raw, internal, events, hashes = pinned_sample(root,sample)
    final=final_session_sources(root)
    corrected={t:dict(v) for t,v in internal.items()}
    for quote in final['correctedFinalQuotes']:
        if quote['ticker'] in corrected:
            corrected[quote['ticker']][quote['date']]=quote
    readings = []
    for record in sample['securities']:
        ticker = record['ticker']
        vendor = vendor_prices(root/BASE/'stock-sources'/f'naver-{ticker[:6]}.json')
        readings.append({'ticker':ticker, 'windows':[dict(w, **quote_scale_reading(
            vendor,raw[ticker],internal[ticker],events[ticker],w)) for w in sample['sourceWindows']],
            'correctedFinalSessionSourceReadings':[dict(w,**quote_scale_reading(
                vendor,raw[ticker],corrected[ticker],events[ticker],w)) for w in sample['sourceWindows']],
            'amendedSecurityPriceStatus':'WITHHELD_FULL_SECURITY' if ticker=='006800.KS' else 'SOURCE_SAMPLE_ASSESSED_ONLY'})
    return {'auditClass':'PREDECLARED_STOCK_SOURCE_QUOTE_AND_ACTION_ONLY',
            'sampleSha256':contract.file_hash(root/SAMPLE),'sampleFrozenCommit':'60a5692',
            'securities':readings,'pinnedSourceObjects':hashes,'freshVendorSources':source,
            'corporateActionSources':json.loads((root/BASE/'stock-sources/corporate-action-sources.json').read_text()),
            'ordinaryCashDoubleAdjustmentConclusion':'NOT_DETECTED_ON_ORDINARY_CASH_EVENTS_IN_THIS_SAMPLE',
            'exception':{'ticker':'006800.KS','date':'2026-03-16',
                         'finding':'Vendor quote scale change equals the cash-distribution factor; replay applies that cash factor again. Separately declared stock entitlement is 0.0073206 common shares per original common share.',
                         'policy':'Full-security price-basis withholding: an additional unexplained 2018 adjustment means a single-event patch cannot certify this security. Preserve its universe membership and non-price features; exclude its invalid price outcomes symmetrically and block paired economics when selected.'},
            'scopeLimit':'Six fixed names and three fixed windows, not proof of complete corporate-action economics for all 260 securities. Current vendor quotes are diagnostics, never relabelled as original snapshots.',
            'realHistoricalAlphaOutcomeReads':0,'realForwardLabels':0,'realHistoricalModelFits':0,
            'realPortfolioBacktests':0,'formalExecutionDispatches':0,'permanentExecutionLocksCreated':0}


def final_session_sources(root):
    """Fixed three-session all-name quotation check, never stock holding returns."""
    root = Path(root)
    sample_path = root/BASE/'stock-source-final-session-sample.json'
    sample = json.loads(sample_path.read_text())
    if sample['dates']!=['2026-09-10','2026-09-11','2026-09-14']:
        raise ValueError('FINAL_SESSION_SAMPLE_CHANGED')
    spec = contract.load(root)
    pin = spec['phaseBIdentity']['inputs']['sourceCommit']
    if pin!=sample['sourceCommit']:
        raise ValueError('FINAL_SESSION_SOURCE_CHANGED')
    path = 'ledger/prices/kr/krx-prices-2026.jsonl.gz'
    blob = subprocess.check_output(['git','cat-file','blob',pin+':'+path],cwd=root)
    sha = hashlib.sha1(b'blob '+str(len(blob)).encode()+b'\0'+blob).hexdigest()
    if sha!=spec['phaseBIdentity']['inputs']['barLedgerBlobSha1'][path]:
        raise ValueError('FINAL_KRX_SOURCE_CHANGED')
    quotes={}
    for line in gzip.decompress(blob).splitlines():
        row=json.loads(line)
        if row['date'] in sample['dates']:
            quotes[(row['ticker'],row['date'])]=row
    manifest=json.loads(subprocess.check_output(['git','cat-file','blob',pin+':ledger/historical/replay-v16/inputs.json'],cwd=root))
    prices,events={},[]
    hashes={path:sha}
    for name in ['price/2026-09','corporate-events/2026-09']:
        for ref in manifest['components'][name]:
            blob=gzip.decompress(subprocess.check_output(['git','cat-file','blob',pin+':ledger/replay-inputs/objects/'+ref+'.json.gz'],cwd=root))
            if hashlib.sha256(blob).hexdigest()!=ref:
                raise ValueError('FINAL_SOURCE_OBJECT_CHANGED')
            hashes[name]=ref
            for row in json.loads(blob):
                if row.get('ticker','').endswith('.KS') and row['date'] in sample['dates']:
                    if name.startswith('price/'):
                        prices[(row['ticker'],row['date'])]=row
                    else:
                        events.append(row)
    if any(r['date']=='2026-09-14' and (r.get('dividend') or r.get('split',1)!=1) for r in events):
        raise ValueError('FINAL_SESSION_ACTION_REQUIRES_EXPLICIT_BASIS')
    readings, replacements=[],[]
    for ticker in sorted({k[0] for k in quotes}):
        dates=sample['dates']
        if not all((ticker,d) in prices and quotes.get((ticker,d),{}).get('close',0)>0 for d in dates):
            continue
        scales=[prices[(ticker,d)]['Close']/quotes[(ticker,d)]['close'] for d in dates]
        if abs(scales[1]/scales[0]-1)>1e-5:
            raise ValueError('PRECEDING_SOURCE_SCALES_NOT_COMPATIBLE')
        readings.append({'ticker':ticker,'middleToFirstQuoteScale':scales[1]/scales[0],
                         'finalToMiddleQuoteScale':scales[2]/scales[1]})
        # No market-price return is computed: convert the SAME final-session raw
        # quotation onto the previously verified index scale. No action on final
        # session is added, and absent/terminated names are never fabricated.
        raw=quotes[(ticker,dates[-1])]
        previous=quotes[(ticker,dates[-2])]
        frame=prices[(ticker,dates[-2])]
        volume_scale=frame['Volume']/previous['volume'] if previous['volume']>0 else None
        if volume_scale is None or raw['volume']<=0:
            continue
        replacements.append({'ticker':ticker,'date':dates[-1],
                             **{k:float(raw[k.lower()]*scales[1]) for k in ['Open','High','Low','Close']},
                             'Volume':float(raw['volume']*volume_scale),
                             'rawKrxClose':raw['close'],'verifiedPreviousIndexScale':scales[1]})
    return {'auditClass':'PREDECLARED_FIXED_DATE_SOURCE_ONLY','sampleSha256':contract.file_hash(sample_path),
            'sourceCommit':pin,'sourceHashes':hashes,'matchingSecurities':len(readings),
            'precedingSessionsUnexplainedScaleChanges':sum(abs(r['middleToFirstQuoteScale']-1)>1e-5 for r in readings),
            'finalSessionUnexplainedScaleChanges':sum(abs(r['finalToMiddleQuoteScale']-1)>1e-5 for r in readings),
            'quoteScaleReadings':readings,'correctedFinalQuotes':replacements,
            'replacementCount':len(replacements),
            'refusedFinalNames':[{'ticker':t,'reason':'NO_VERIFIED_POSITIVE_FINAL_TRADING_VOLUME'} for t in sorted({r['ticker'] for r in readings}-{r['ticker'] for r in replacements})],
            'noStockReturnsCalculated':True,'rootCauseLimit':'Final stored vendor session is not definition-compatible with final KRX quotations. Its acquisition timing versus vendor revision is not established because original raw vendor response was not preserved.'}
