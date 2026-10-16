"""Run the owner's fixed US_DECISION_PILOT_V1 on read-only original inputs.

No old research executor, result, forecast, execution budget or lock is used.
Only aggregate new analytical results may be published; caches stay outside git.
"""
from __future__ import annotations

import argparse
from bisect import bisect_left
from collections import Counter, defaultdict
import csv
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import us_decision_pilot as P  # noqa: E402
from pipeline import us_cash_profitability as CP  # noqa: E402
from pipeline import finnhub_derive as FD, finnhub_fundamentals as FF  # noqa: E402
from pipeline import accounting_quality as AQ, replay_calendar as RC  # noqa: E402
from pipeline import us_dual_benchmark_data as D, replay_inputs as RI  # noqa: E402
from pipeline import regional_alpha_features as RAF  # noqa: E402
from pipeline import us_capital_allocation_coverage as C  # noqa: E402

PROTOCOL = 'docs/us-decision-pilot-v1-protocol.json'
MEMBERSHIP = 'research_specs/alpha-opportunity-model-v1-us-membership.json.gz'
SECTORS = 'data/research/us-capital-allocation-alpha-v1/sp500-snapshot-sectors.json.gz'
IDENTITY = 'docs/results/alpha-opportunity-model-v3-survivorship-audit.json'
STRATEGIES = ('B0_SPY', 'B1_PRICE', 'B2_MULTIFACTOR', 'B3_GATED_PRICE', 'B3_GATED_MULTIFACTOR',
              'FORCED_5_PRICE_DIAGNOSTIC', 'FORCED_5_MULTIFACTOR_DIAGNOSTIC', 'B2_PLUS_VALUE')
METRICS = ('cagr', 'annualizedCagrDifferenceVsSPY', 'mdd', 'annualVolatility', 'sharpeZeroRiskFree',
           'twoWayTurnover', 'tradingCostInitialCapital', 'meanNames', 'meanCash')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_contract(root=ROOT):
    root = Path(root)
    protocol = json.loads((root / PROTOCOL).read_bytes())
    if protocol['id'] != P.STUDY or protocol['sourceScope']['status'] != 'READ_ONLY_INPUT_REUSE_AUTHORIZED':
        raise ValueError('PILOT_SCOPE_NOT_AUTHORIZED')
    pins = {**protocol['protectionSources'], **protocol['inputAndHelperHashes'],
            'pipeline/us_decision_pilot.py': protocol['coreCodeSha256'],
            'scripts/run_us_decision_pilot.py': protocol['orchestrationCodeSha256']}
    for path, expected in pins.items():
        if sha(root / path) != expected:
            raise ValueError('PINNED_SOURCE_CHANGED:' + path)
    return protocol


def load_prices(root=ROOT):
    """Only original price/benchmark components; validate manifest AND content."""
    reader = D.SealedReader(Path(root))
    manifest = reader.manifest()
    if RI.digest({k: v for k, v in manifest.items() if k != 'sha256'}) != manifest['sha256']:
        raise ValueError('MANIFEST_CONTENT_CHANGED')
    bucket, refs = defaultdict(dict), []
    for name in sorted(manifest['components']):
        if not name.startswith(('price/20', 'benchmark/20')):
            continue
        for ref in manifest['components'][name]:
            refs.append(ref)
            for row in reader.component(ref):
                ticker, day = row['ticker'], row['date']
                if ticker.endswith(('.KS', '.KQ')):
                    continue
                value = row.get('Close')
                if day in bucket[ticker] and bucket[ticker][day] != value:
                    raise ValueError('CONFLICTING_SOURCE_PRICE')
                bucket[ticker][day] = value
    frame = pd.DataFrame({t: pd.Series(v, dtype=float) for t, v in sorted(bucket.items())})
    frame.index = pd.to_datetime(frame.index)
    frame = frame.sort_index()
    sessions = RC.sessions(str(frame.index[0].date()), manifest['through'], 'US')
    frame = frame.reindex(sessions)  # NaN stays NaN, including whole missing sessions.
    return frame, {'commit': reader.commit, 'manifestSha256': manifest['sha256'],
                   'through': manifest['through'], 'componentRefs': sorted(set(refs)),
                   'pricePanels': len(frame.columns), 'priceRows': int(frame.notna().sum().sum())}


def load_filings(root=ROOT):
    """Read the original pinned Git blobs, never trust a mutable local manifest."""
    root = Path(root)
    listing = subprocess.check_output(['git', 'ls-tree', '-r', D.SOURCE_COMMIT,
                                      'ledger/fundamentals/us/'], cwd=root).decode().splitlines()
    grouped, shards = defaultdict(list), []
    for line in listing:
        meta, path = line.split('\t')
        if not path.endswith('.jsonl.gz'):
            continue
        oid = meta.split()[2]
        blob = subprocess.check_output(['git', 'cat-file', 'blob', oid], cwd=root)
        actual = hashlib.sha1(b'blob ' + str(len(blob)).encode() + b'\0' + blob).hexdigest()
        if actual != oid:
            raise ValueError('FUNDAMENTAL_BLOB_CHANGED')
        shards.append({'path': path, 'gitBlob': oid, 'sha256': hashlib.sha256(blob).hexdigest()})
        for line in gzip.decompress(blob).splitlines():
            if line.strip():
                row = json.loads(line)
                grouped[row['ticker']].append(row)
    if not shards:
        raise ValueError('MISSING_ORIGINAL_FUNDAMENTALS')
    return grouped, shards


class AccountingCache:
    """Cache by strictly visible source prefix; freshness is checked on EVERY date."""
    def __init__(self, records):
        dated = sorted(((CP.visible_day(r).isoformat(), r) for r in records if CP.visible_day(r)),
                       key=lambda pair: pair[0])
        self.days = [d for d, _ in dated]
        self.records = [r for _, r in dated]
        self.cache = {}

    def at(self, day):
        n = bisect_left(self.days, day)  # same-day filings unavailable
        if n not in self.cache:
            visible = self.records[:n]
            values = CP.features_as_of(visible, day)
            by_key = FD.index_filings(visible)
            key = CP.current_key(by_key)
            values.update(assetGrowthPct=None, debtToEquity=None)
            if key is not None and values['reportAgeDays'] is not None and 0 <= values['reportAgeDays'] <= 180:
                current = by_key[key]
                fields, _ = AQ.derive_us_fields(by_key, *key)
                values['assetGrowthPct'] = fields.get('assetGrowthPct')
                resolved = FF.resolve_units(current)
                equity = FD.amount(current, 'bs', FD.EQUITY, resolved)
                liabilities, _ = FD.total_liabilities(current, resolved)
                # Existing debtToEquity is TOTAL LIABILITIES/equity, not interest-bearing debt.
                if equity is not None and equity > 0 and liabilities is not None and liabilities >= 0:
                    values['debtToEquity'] = liabilities / equity
            self.cache[n] = values
        values = dict(self.cache[n])
        end = values.get('reportEnd')
        age = (pd.Timestamp(day) - pd.Timestamp(end)).days if end else None
        if age is None or not 0 <= age <= 180:
            values.update({f: None for f in P.ACCOUNTING})
        ciks = {str(int(r['cik'])) for r in self.records[:n] if str(r.get('cik', '')).isdigit()}
        return values, ciks


def price_matrix_features(close):
    valid = np.isfinite(close) & (close > 0)
    complete = valid.rolling(253, min_periods=253).sum() == 253
    momentum = (close / close.shift(252) - 1).where(complete)
    vol = (close.pct_change(fill_method=None).rolling(252, min_periods=252).std(ddof=1)
           * np.sqrt(252)).where(complete)
    return momentum, vol


def build_signals(close, raw, root=ROOT):
    root = Path(root)
    membership = RAF.MembershipSnapshots(json.loads(gzip.decompress((root / MEMBERSHIP).read_bytes()))['snapshots'])
    sectors = C.SectorBook(json.loads(gzip.decompress((root / SECTORS).read_bytes()))['snapshots'])
    # Read ONLY identity metadata, never any old strategy outcome or performance.
    identity = json.loads((root / IDENTITY).read_bytes())['regions']['US']['identity']
    categories = {t: c for c, ts in identity['categories'].items() for t in ts}
    ambiguous = {t for t, c in categories.items() if c == 'TICKER_REUSE_DIFFERENT_ISSUER'} | set(identity['panelPostdatesMembership'])
    malformed = {k.upper(): v['resolvedTo'] for k, v in identity['malformed'].items() if v.get('resolvedTo')}
    renames = {t: r['pricedBy'] for t, r in identity['renames'].items() if r.get('pricedBy')}
    caches = {t: AccountingCache(rows) for t, rows in raw.items()}
    momentum, vol = price_matrix_features(close)
    # Extend the calendar past cutoff so an incomplete final week is never a signal.
    cutoff = str(close.index[-1].date())
    calendar = RC.sessions('2013-01-01', str((close.index[-1] + pd.Timedelta(days=10)).date()), 'US')
    grid = pd.Series(calendar, index=calendar).groupby(calendar.to_period('W')).max()
    dates = [d for d in grid if str(d.date()) <= cutoff and d in close.index]
    frames, years, weekly = {}, defaultdict(Counter), []
    for day in dates:
        text = str(day.date())
        snap = membership.on(text)
        count = Counter()
        if snap is None:
            weekly.append({'date': text, 'status': 'NO_DATED_MEMBERSHIP', 'completeCases': 0})
            continue
        rows, seen_tickers = [], set()
        count['signalDates'] += 1
        for symbol in snap['members']:
            count['memberDates'] += 1
            normalized = malformed.get(symbol.upper(), symbol)
            ticker = renames.get(normalized, normalized)
            if normalized in ambiguous or ticker in seen_tickers:
                count['IDENTITY_HOLD'] += 1
                continue
            seen_tickers.add(ticker)
            sector, sector_basis = sectors.lookup(snap, symbol)
            if sector in ('Financials', 'Real Estate', C.UNCLASSIFIED):
                count['SECTOR_EXCLUDED'] += 1
                continue
            if ticker not in close:
                count['NO_PRICE_PANEL'] += 1
                continue
            if pd.isna(momentum.at[day, ticker]) or pd.isna(vol.at[day, ticker]):
                count['PRICE_HISTORY_INCOMPLETE'] += 1
                continue
            if ticker not in caches:
                count['NO_PIT_FILINGS'] += 1
                continue
            values, ciks = caches[ticker].at(text)
            member_cik = sectors.cik(snap, symbol)
            if not member_cik or str(int(member_cik)) not in ciks:
                count['CIK_UNVERIFIED_OR_MISMATCH'] += 1
                continue
            missing = [f for f in P.ACCOUNTING if values.get(f) is None or not np.isfinite(values[f])]
            if missing:
                count['ACCOUNTING_INCOMPLETE_OR_STALE'] += 1
                for f in missing:
                    count['missing_' + f] += 1
                continue
            rows.append({'ticker': ticker, 'sector': sector, 'sectorBasis': sector_basis,
                         'momentum252': momentum.at[day, ticker], 'vol252': vol.at[day, ticker],
                         **{f: values[f] for f in P.ACCOUNTING}})
            count['COMPLETE_CASE'] += 1
        frame = P.scores(pd.DataFrame(rows).set_index('ticker')) if rows else pd.DataFrame()
        if not frame.empty:
            frames[day] = frame
            count['usableSignalDates'] += 1
        years[str(day.year)].update(count)
        weekly.append({'date': text, 'snapshotDate': snap['date'],
                       'snapshotAgeDays': (day - pd.Timestamp(snap['date'])).days,
                       'completeCases': len(rows), 'scorableCases': len(frame),
                       'status': 'SCORED' if not frame.empty else 'INSUFFICIENT_COMPLETE_CASES'})
        if len(weekly) % 52 == 0:
            print(json.dumps({'phase': 'input_features', 'date': text, 'completeCases': len(rows)}), flush=True)
    return frames, dict(years), weekly


def evaluate(close, frames):
    """New comparison only. Same pre-outcome cohorts, dates, costs and basis."""
    available = sorted(d for d in frames if close.index.get_loc(d) + 1 < len(close))
    if not available:
        raise ValueError('NO_COMMON_COMPLETE_CASE_DATES')
    start = available[0]
    prices = close.loc[start:]
    first_fill = close.index[close.index.get_loc(start) + 1]
    mapping = {'B1_PRICE': ('B1', False), 'B2_MULTIFACTOR': ('B2', False),
               'FORCED_5_PRICE_DIAGNOSTIC': ('B1', True), 'FORCED_5_MULTIFACTOR_DIAGNOSTIC': ('B2', True),
               **{'WITHOUT_' + f: ('WITHOUT_' + f, False) for f in P.FAMILIES}}
    orders = {'B0_SPY': {first_fill: {'SPY': 1.0}}}
    for name, (column, concentrated) in mapping.items():
        orders[name] = {close.index[close.index.get_loc(d) + 1]: P.allocation(frames[d], column, concentrated=concentrated)
                        for d in available}
    strategies, private_paths = {}, {}
    for name, trades in orders.items():
        print(json.dumps({'phase': 'portfolio', 'strategy': name}), flush=True)
        try:
            net = P.simulate(prices, trades)
            gross = P.simulate(prices, trades, costed=False)
            metrics = P.metrics(net)
            metrics.update(grossCagr=P.metrics(gross)['cagr'],
                           annualizedTurnover=metrics['twoWayTurnover'] * 252 / metrics['sessions'],
                           rebalanceDates=len(trades))
            strategies[name] = metrics
            private_paths[name] = net
        except ValueError as error:
            if not str(error).startswith(('UNRESOLVED_HELD', 'UNRESOLVED_ENTRY')):
                raise
            # Do not publish a stitched NAV. Other unaffected strategies still run.
            strategies[name] = {'status': 'NOT_ESTIMABLE', 'reason': str(error),
                                'start': str(start.date()), 'end': str(prices.index[-1].date())}
    baseline = strategies['B0_SPY'].get('cagr')
    for row in strategies.values():
        if 'cagr' in row and baseline is not None:
            row['annualizedCagrDifferenceVsSPY'] = row['cagr'] - baseline
            row['annualizedCostDrag'] = row['grossCagr'] - row['cagr']
    for name in ('B3_GATED_PRICE', 'B3_GATED_MULTIFACTOR', 'B2_PLUS_VALUE'):
        strategies[name] = {'status': 'NOT_ESTIMABLE', 'reason': 'NO_SCORE_SPECIFIC_PIT_EXPECTED_NET_EXCESS' if 'GATED' in name else 'HISTORICAL_PRICE_SHARE_BASIS_NOT_INDEPENDENTLY_VERIFIED'}
    diagnostics = {}
    for horizon in P.HORIZONS:
        records, states = [], Counter()
        for day in available:
            pos = close.index.get_loc(day) + 1
            if pos + horizon >= len(close):
                states['NOT_MATURED'] += 1
                continue
            reading = P.label_reading(frames[day], close.iloc[pos], close.iloc[pos + horizon])
            states[reading['status']] += 1
            if reading['status'] == 'RESOLVED':
                spy_a, spy_b = close.SPY.iloc[pos], close.SPY.iloc[pos + horizon]
                spy = float(spy_b / spy_a - 1) if np.isfinite(spy_a) and np.isfinite(spy_b) and spy_a > 0 and spy_b > 0 else None
                records.append({'date': str(day.date()), 'names': reading['names'], 'spy': spy, 'scores': reading['scores']})
        scores = {}
        for column in ('B1', 'B2', *P.FAMILIES, *('WITHOUT_' + f for f in P.FAMILIES)):
            values = [r['scores'][column] for r in records]
            def mean(key):
                a = [v[key] for v in values if v[key] is not None]
                return float(np.mean(a)) if a else None
            excess = [r['scores'][column]['topMean'] - r['spy'] for r in records if r['spy'] is not None]
            scores[column] = {'meanRankIC': mean('rankIC'), 'definedICDates': sum(v['rankIC'] is not None for v in values),
                              'meanTopMinusBottom': mean('topMinusBottom'), 'meanTopMinusSPY': float(np.mean(excess)) if excess else None}
        paired = [r['scores']['B2']['rankIC'] - r['scores']['B1']['rankIC'] for r in records
                  if r['scores']['B2']['rankIC'] is not None and r['scores']['B1']['rankIC'] is not None]
        diagnostics[str(horizon)] = {'statusCounts': dict(states), 'resolvedCohorts': len(records),
            'memberLabels': sum(r['names'] for r in records), 'firstSignal': records[0]['date'] if records else None,
            'lastSignal': records[-1]['date'] if records else None, 'scores': scores,
            'pairedMeanICIncrementB2VsB1': float(np.mean(paired)) if paired else None,
            'inference': 'DESCRIPTIVE_OVERLAPPING_COHORTS_NO_P_VALUES_OR_OOS_CLAIM'}
    return strategies, diagnostics, private_paths


def build(root=ROOT):
    protocol = verify_contract(root)  # MUST precede every price/outcome read.
    close, identity = load_prices(root)
    raw, shards = load_filings(root)
    frames, annual, weekly = build_signals(close, raw, root)
    strategies, diagnostics, paths = evaluate(close, frames)
    comparison = strategies['B2_MULTIFACTOR'].get('annualizedCagrDifferenceVsSPY')
    return {'id': P.STUDY, 'evidenceClass': P.EVIDENCE,
        'verdict': 'INCONCLUSIVE' if comparison is None else ('BEAT' if comparison > 0 else 'NOT BEATEN'),
        'verdictScope': 'DESCRIPTIVE_PAIRED_NET_CAGR_ONLY; unconditional investment superiority remains INCONCLUSIVE',
        'executionState': 'EXECUTED_NEW_OWNER_REQUESTED_COMPARISON', 'newComparisonBudgetConsumed': True,
        'realOutcomeReads': {'portfolioValuationSessions': len(close), 'labelCohorts': {h: d['resolvedCohorts'] for h, d in diagnostics.items()}},
        'sealedStudyOutcomeReads': 0, 'remoteLockWrites': 0, 'sealedInputsModified': False,
        'protocolSha256': sha(Path(root) / PROTOCOL), 'inputs': {**identity, 'fundamentalShards': shards,
            'filingRecords': sum(map(len, raw.values())), 'filingTickers': len(raw)},
        'priceBasis': 'INTERNAL_VENDOR_FORWARD_TOTAL_RETURN_INDEX; dividends already applied, not applied again; external raw-close reconciliation unresolved',
        'strategies': strategies, 'selectionDiagnostics': diagnostics,
        'annualMissingness': annual, 'weeklyAvailability': weekly,
        'limitations': ['SURVIVOR_CONDITIONED; missing departed panels are not admitted or imputed',
            'Snapshot observation dates are not authoritative historical effective membership dates',
            'Verified rename mapping and identity exclusions inherited; no unverified recovered price used',
            'debtToEquity means total liabilities / positive equity, not interest-bearing debt / assets',
            'Earliest visible filing retained for each fiscal stage; later amendments not substituted',
            'Conditional on vendor price basis and unresolved terminal economics outside the priced cohort',
            'No calibrated expected-return gate, independent OOS evidence, model fit or promotion'],
        'currentCandidates': {'status': 'CURRENT_CANDIDATES_NOT_VERIFIED', 'candidates': [],
            'reason': 'Historical source cutoff is not current; current membership, action basis, PIT filings and score-specific economic gate not verified'},
        'promotionEligible': False, 'productionEffect': 'NONE', 'publicPricePayloads': False,
        'method': protocol['id']}, paths


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True, help='NEW directory for aggregate outputs')
    parser.add_argument('--private-path-dir', type=Path, required=True, help='outside checkout; never publish daily strategy paths')
    args = parser.parse_args(argv)
    private = args.private_path_dir.resolve()
    if private == ROOT or ROOT in private.parents:
        raise ValueError('PRIVATE_OUTPUT_MUST_BE_OUTSIDE_CHECKOUT')
    if args.output_dir.exists() or private.exists():
        raise ValueError('OUTPUT_EXISTS_NO_OVERWRITE')
    result, paths = build()
    args.output_dir.mkdir(parents=True)
    private.mkdir(parents=True)
    (args.output_dir / 'result.json').write_text(json.dumps(result, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2) + '\n')
    with (args.output_dir / 'strategy-metrics.csv').open('x', newline='') as out:
        writer = csv.DictWriter(out, fieldnames=['strategy', 'status', *METRICS, 'reason'], lineterminator='\n')
        writer.writeheader()
        for name, row in result['strategies'].items():
            writer.writerow({'strategy': name, 'status': row['status'], **{k: row.get(k) for k in METRICS}, 'reason': row.get('reason', '')})
    with (args.output_dir / 'yearly-performance.csv').open('x', newline='') as out:
        writer = csv.writer(out, lineterminator='\n')
        writer.writerow(['year', 'strategy', 'netReturn'])
        for name, row in result['strategies'].items():
            for year, value in row.get('yearlyReturns', {}).items():
                writer.writerow([year, name, value])
    for name, path in paths.items():
        path.to_csv(private / (name + '.csv'), lineterminator='\n')
    print(json.dumps({'verdict': result['verdict'], 'metrics': {n: r.get('cagr') for n, r in result['strategies'].items()}}), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
