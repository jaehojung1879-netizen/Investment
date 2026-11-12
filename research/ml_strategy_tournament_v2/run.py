"""Four fixed paths: actual cash outcomes, source blocks, isolated TR diagnostics.

This command cannot fit a model, select a winner or write a v1/audit result.
"""
from __future__ import annotations
import argparse
import gzip
import json
import os
from pathlib import Path
import sys

import pandas as pd

from . import accounting as A, sources as S
from .identity import HERE, ROOT, canonical, code_identity, digest, environment, file_hash, git_commit, write_once
from .metrics import metrics


def records(path, rows):
    # Fixed gzip mtime makes byte identities reproducible.
    raw = b''.join(canonical(r) + b'\n' for r in rows)
    data = gzip.compress(raw, mtime=0)
    if path.exists() and path.read_bytes() != data:
        raise ValueError('LEDGER_BYTES_CHANGED')
    path.write_bytes(data)
    return file_hash(path)


def manifest_payload(target, runid, ledger_hashes):
    files = dict(ledger_hashes)
    files.update({p.name: file_hash(p) for p in target.glob('*.json') if p.name != 'result-manifest.json'})
    return {'executionIdentitySha256': runid, 'files': files}


def diagnostic_tr(market, decisions, rf):
    """Controlled error deltas, not verified shareholder-account outcomes."""
    audit = ROOT / 'research/ml_strategy_tournament_independent_audit_v1'
    sys.path.insert(0, str(audit))
    from check_cash import exact_replay
    legacy = market['legacyClose']
    corrected = legacy.copy()
    prior, end = pd.Timestamp('2026-09-11'), pd.Timestamp('2026-09-14')
    repaired = []
    for t in corrected:
        if t == A.ETF:
            continue
        p, e = market['quotes'].get(str(prior.date()), {}).get(t), market['quotes'].get(str(end.date()), {}).get(t)
        if p and e and p['volume'] > 0 and e['volume'] > 0 and pd.notna(corrected.at[prior, t]):
            value = corrected.at[prior, t] * e['close'] / p['close']
            repaired.append({'ticker': t, 'date': str(end.date()), 'old': float(corrected.at[end, t]), 'new': float(value)})
            corrected.at[end, t] = value
    event_corrected = corrected.copy()
    q = S.MIRAE.read_correction()
    tq = {r['date']: r for r in q['rawQuotes']}
    pre, day = '2026-03-13', '2026-03-16'
    old_gross = legacy.at[pd.Timestamp(day), '006800.KS'] / legacy.at[pd.Timestamp(pre), '006800.KS']
    raw_gross = (tq[day]['close'] * (1 + q['stockDividendEvent']['commonSharesPerCommonShare']) + 300) / tq[pre]['close']
    from .vendor.shareholder_inputs import cited_levels
    levels, _, _ = cited_levels([tq[pre], tq[day]],
        {day: {'dps': 300., 'amountBasis': 'PRE_ACTION_SHARE'}},
        [{'kind': 'STOCK_DIVIDEND', 'date': day, 'shareMultiplier': 1 + q['stockDividendEvent']['commonSharesPerCommonShare'],
          'state': 'VERIFIED', 'confirmedOn': q['stockDividendEvent']['ratioConfirmedBeforeExDate'],
          'sourceSha256': file_hash(ROOT / S.MIRAE.CORRECTION)}])
    if abs(levels[day] - raw_gross) > 1e-12:
        raise AssertionError('REUSED_328_PACKAGE_CONTRADICTS_RAW_CASH_SHARE_FORMULA')
    pulse = raw_gross / old_gross
    event_corrected.loc[event_corrected.index >= day, '006800.KS'] *= pulse
    out = {'status': 'TR_INDEX_CONTROLLED_DIAGNOSTICS_NOT_VERIFIED_CASH_RESULTS', 'finalQuoteRepairs': repaired,
           'mirae2026Event': {'oldGross': old_gross, 'officialPackageGross': raw_gross, 'independentReused328PackageGross': levels[day], 'correctionPulse': pulse,
                             'scope': '2026_EVENT_ONLY_DOES_NOT_BRIDGE_2018_RIGHT_OR_CERTIFY_OTHER_ACTIONS'}, 'paths': {}}
    for sid, ds in decisions.items():
        board = json.loads((ROOT / ('research/ml_strategy_tournament_v1/results/leaderboard-' + next(x['view'] for x in S.CONFIG['candidates'] if x['id'] == sid) + '.json')).read_text())['leaderboard'][sid]
        if board['terminalHitCount'] != 0:
            raise ValueError('UNRESOLVED_TERMINAL_NOT_ALLOWED_IN_TR_DIAGNOSTIC')
        h = [{'date': d['date'], 'weights': {t: w for t, w in d['weights'].items() if t != A.ETF},
              'etf': d['weights'].get(A.ETF, 0.)} for d in ds]
        for i, d in enumerate(ds):
            interval_end = pd.Timestamp(ds[i + 1]['date'] if i + 1 < len(ds) else S.CONFIG['end'])
            for ticker, weight in d['weights'].items():
                if ticker != A.ETF and weight > 0:
                    last = legacy[ticker].last_valid_index()
                    if last is None or last < interval_end:
                        raise ValueError('INDEPENDENT_TERMINAL_CROSSING_GUARD:' + sid + ':' + ticker)
        out['paths'][sid] = {}
        for name, prices in [('CASH_EQUATION_ONLY', legacy), ('PLUS_FINAL_QUOTES', corrected),
                             ('PLUS_2026_MIRAE_PACKAGE', event_corrected)]:
            nav, residual = exact_replay(prices, market['legacyVolume'], h)
            m = metrics(list(nav.index), list(nav), 1., rf)
            m['maxAbsCashResidual'] = residual
            m['certifiedEconomicOutcome'] = False
            out['paths'][sid][name] = m
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--output-root', type=Path, default=HERE / 'results')
    args = ap.parse_args(argv)
    if not args.output_root.resolve().is_relative_to(HERE.resolve()):
        raise ValueError('OUTPUT_MUST_BE_V2_DIRECTORY')
    if any(os.environ.get(k) != '1' for k in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'PYTHONHASHSEED')):
        raise ValueError('REPRODUCIBLE_SINGLE_THREAD_HASH_SEED_ENVIRONMENT_REQUIRED')
    config = json.loads((HERE / 'config.json').read_text())
    original_config = ROOT / 'research/ml_strategy_tournament_v1/config.json'
    assert file_hash(original_config) == config['v1ConfigSha256']
    market, ds = S.load_raw()
    # No code path to fit_fixed_fold; B is a separate source/authorization gate.
    key = {'gitCommit': git_commit(), 'code': code_identity(), 'config': config,
           'sources': market['sourceHashes'], 'environment': environment(),
           'selectionsSha256': file_hash(ROOT / 'research/ml_strategy_tournament_v1/results/holdings-all.json.gz')}
    runid = digest(key)
    target = args.output_root / runid
    target.mkdir(parents=True, exist_ok=True)
    write_once(target / 'execution-identity.json', key)
    events = json.loads((ROOT / 'data/bok-policy-rates.json').read_text())['events']
    rate = pd.Series({pd.Timestamp(r['date']): r['annualRatePct'] for r in events}).sort_index()
    days = pd.to_datetime(market['sessions'])
    rf = rate.reindex(rate.index.union(days)).ffill().reindex(days) / 100 / 252
    results, hashes = {}, {}
    for candidate in config['candidates']:
        sid, view = candidate['id'], candidate['view']
        v1 = json.loads((ROOT / f'research/ml_strategy_tournament_v1/results/leaderboard-{view}.json').read_text())['leaderboard'][sid]
        paths = {}
        for label, strict in [('A_VERIFIED_CASH', True), ('A_OBSERVED_PREFIX_INCOMPLETE_EVENT_COVERAGE', False)]:
            book = A.run(market, ds[sid], capital=config['initialCapitalKrw'], require_complete=strict)
            if book['status'] == 'COMPLETE' and not strict and sid != 'RULE_ETF_ONLY':
                raise AssertionError('INCOMPLETE_STOCK_COVERAGE_CANNOT_BECOME_VERIFIED')
            met = metrics(market['sessions'], [r['nav'] for r in book['account']], config['initialCapitalKrw'], rf)
            valued = [r for r in book['account'] if r['nav'] is not None]
            prefix = metrics([r['date'] for r in valued], [r['nav'] for r in valued], config['initialCapitalKrw'], rf)
            prefix['scope'] = 'OBSERVED_SOURCE_PREFIX_NOT_VERIFIED_FULL_PERIOD'
            prefix['shortWindowAnnualizationWarning'] = len(valued) < 252
            files = {}
            for key_name in ('account', 'assets', 'trades', 'orders', 'events'):
                file = target / f'{sid}-{label}-{key_name}.jsonl.gz'
                files[file.name] = records(file, book[key_name])
            paths[label] = {'status': book['status'], 'metrics': met, 'firstBlock': book['blocked'],
                            'valuedSessions': len(valued), 'observedPrefixMetricsNotCertifiedFullPeriod': prefix,
                            'maxAbsFundingResidualKrw': book['maxAbsFundingResidualKrw'], 'ledgers': files,
                            'sourceCompletenessRequired': strict}
            hashes.update(files)
        results[sid] = {'v1': {k: v1[k] for k in ('cagr', 'excessCagr', 'mdd', 'sharpe', 'yearly')},
                        'v2A': paths,
                        'v2B': {'status': 'SOURCE_BLOCKED_NOT_RUN', 'metrics': {'cagr': None, 'excessCagr': None, 'mdd': None, 'sharpe': None, 'yearly': None},
                                'reason': 'COMPLETE_CORRECTED_STOCK_INPUTS_AND_EXACT_EXECUTION_PACKET_REQUIRED',
                                'newWinnerSelected': False}}
    results['RULE_ETF_ONLY']['v2B'] = {'status': 'NO_REFIT_ETF_COMMON_CONTROL', 'newWinnerSelected': False,
        'metrics': results['RULE_ETF_ONLY']['v2A']['A_VERIFIED_CASH']['metrics']}
    etf_cagr = results['RULE_ETF_ONLY']['v2A']['A_VERIFIED_CASH']['metrics']['cagr']
    for r in results.values():
        for path in r['v2A'].values():
            path['metrics']['excessCagr'] = path['metrics']['cagr'] - etf_cagr if path['metrics']['cagr'] is not None else None
    diagnostic = diagnostic_tr(market, ds, rf)
    write_once(target / 'controlled-diagnostics.json', diagnostic)
    write_once(target / 'results.json', results)
    source_review = {k: market[k] for k in ('admission', 'sourceHashes', 'miraeSourceReassessment', 'vendorActionRedFlags', 'shareholderSourceStatus', 'finalSourceProbe')}
    write_once(target / 'source-admission.json', source_review)
    write_once(target / 'decisions.json', ds)
    write_once(target / 'result-manifest.json', manifest_payload(target, runid, hashes))
    print(json.dumps({'runId': runid, 'output': str(target), 'results': results}, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
