"""Korean adapter for the committed exposure study; frozen sources and costs.

python -m research.kr_us_exposure_preserving_v1.kr --scratch /workspace/s2-inputs
"""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import pickle
import re
import subprocess
import sys

import numpy as np
import pandas as pd

from pipeline.kr_industry_anatomy import industry_of
from pipeline.kr_industry_anatomy_execution import load_membership_inputs
from research.kr_us_strategy_batch_v1 import common
from research.kr_us_strategy_batch_v1 import kr as OLD

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = ROOT / 'research/kr_us_strategy_batch_v1/results/KR'
INPUTS = HERE / 'inputs/KR'
SELECTORS = ('S2', 'VALUE_ORIGINAL', 'VALUE_COMPLETE', 'CONFIRM_NEUTRAL', 'FOUR_FACTOR')
SEEDS = tuple(range(20261119, 20261127))
CONFIGS = {**{f'S2_K{k}': f'KR:S2:FIXED20:K{k}' for k in range(1, 5)},
           **{s: f'KR:{s}:FIXED20:K5' for s in SELECTORS}}
ETF = OLD.M.ETF
LEADERS = set(OLD.TWO)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def clean(value):
    return OLD.clean(value)


def dump(path, value):
    path.write_text(json.dumps(clean(value), ensure_ascii=False, indent=1, allow_nan=False) + '\n')


def dated_books(document):
    return {key: {pd.Timestamp(d): w for d, w in dates.items()}
            for key, dates in document.items()}


def write_books(path, books):
    with gzip.open(path, 'wt') as stream:
        json.dump({key: {str(d.date()): w for d, w in by.items()} for key, by in books.items()}, stream)


def source_identity():
    paths = [SOURCE / name for name in ('books.json.gz', 'matched-books.json.gz',
             'asset-payoffs.csv.gz', 'matching-audit.csv.gz', 'summary.json',
             'cohorts-126.csv.gz', 'cohorts-252.csv.gz', 'matched-126.csv', 'matched-252.csv')]
    paths += [Path(OLD.__file__), Path(common.__file__)]
    hashes = {str(p.relative_to(ROOT)): sha(p) for p in paths}
    for path in paths:
        original = subprocess.check_output(['git', 'cat-file', 'blob',
                   '36ac329261f8f9000935e524d8a28c2005524c10:' + str(path.relative_to(ROOT))], cwd=ROOT)
        if hashlib.sha256(original).hexdigest() != hashes[str(path.relative_to(ROOT))]:
            raise ValueError('SOURCE_350_CHANGED:' + str(path))
    return hashes


def support_audit(I, ctx, base, passive, out):
    """Boolean support only: no returns, NAV, units, costs or relative prices."""
    sessions, px = I['sessions'], ctx.px
    dates = pd.DatetimeIndex(base['dates'])
    start = OLD.M.next_session(sessions, dates[0])
    end = I['closes'][ETF].last_valid_index()
    terminal_events, target_events, summaries = [], [], {}
    for every in (26, 52):
        events, missing = [], []
        for account in range(every):
            schedule = OLD.A.books_to_schedule({d: passive[d] for d in dates[account::every]}, sessions)
            held = {ETF}
            for date in sessions[(sessions >= start) & (sessions <= end)]:
                i = px.pos[date]
                for ticker in list(held):
                    terminal = px.terminal.get(ticker)
                    if terminal is not None and i > terminal:
                        events.append({'L': every, 'account': account, 'date': str(date.date()), 'ticker': ticker,
                                       'lastQuote': str(sessions[terminal].date()),
                                       'state': 'UNRESOLVED_TERMINAL_WHILE_HELD'})
                        held.remove(ticker)
                if date not in schedule:
                    continue
                targets = {t for t, w in schedule[date].items() if w > 0}
                def tradable(t):
                    return t == ETF or (t in px.col and bool(px.tradable[i, px.col[t]]))
                locked = {t for t in held if not tradable(t)}
                free = {t for t in targets if tradable(t)}
                for ticker in sorted(targets - free):
                    missing.append({'L': every, 'account': account, 'date': str(date.date()), 'ticker': ticker,
                                    'state': 'TARGET_NOT_TRADABLE_AT_EXECUTION',
                                    'finiteRawQuote': bool(ticker in I['closes'] and pd.notna(I['closes'].at[date, ticker]))})
                held = locked | (free if free else {ETF})
        events.sort(key=lambda r: (r['date'], r['account'], r['ticker']))
        missing.sort(key=lambda r: (r['date'], r['account'], r['ticker']))
        summaries[str(every)] = {'terminalHeldEvents': len(events), 'lastTerminalEvent': events[-1] if events else None,
                                 'targetNontradableEvents': len(missing), 'lastTargetNontradable': missing[-1] if missing else None}
        terminal_events.extend(events)
        target_events.extend(missing)
    last = max((e['date'] for e in terminal_events), default=None)
    threshold = pd.Timestamp(f'{pd.Timestamp(last).year + 1}-01-01') if last else dates[0]
    suffix = next((str(d.date()) for d in dates if d >= threshold), None)
    frozen = json.loads((INPUTS / 'quote-hazards.json').read_text())
    assert last == frozen['lastQuoteHazardSession'] and suffix == frozen['NAV_COVERAGE_SUFFIX_DECISION']
    assert summaries == frozen['byL']
    result = {'performanceCalculated': False, 'start': start, 'end': end,
              'lastQuoteHazardSession': last, 'NAV_COVERAGE_SUFFIX_DECISION': suffix,
              'byL': summaries, 'terminalEvents': terminal_events, 'targetNontradableEvents': target_events,
              'rule': 'Support-only frozen locking/tradability; no terminal value reconstructed; suffix fixed before new outcomes'}
    dump(out / 'quote-only-support-audit.json', result)
    return result


def seed_books(ctx, dates, out):
    books, peers, audits, pools = {}, {}, [], []
    for seed in SEEDS:
        key = f'CONFIRM_SEED{seed}'
        books[key], peers[key] = {}, {}
        for date in dates:
            g = ctx.by[date].sort_values('ticker')
            eligible = g['_q'] & ~g.ticker.isin(OLD.C.WITHHELD)
            complete = eligible & g[OLD.VALUE].notna() & g[OLD.BUSINESS].notna().all(axis=1)
            positive = set(g.loc[complete & g[OLD.BUSINESS].gt(0).all(axis=1), 'ticker'])
            candidates = g.loc[complete, 'ticker'].astype(str)
            day = date.strftime('%Y-%m-%d')
            order = sorted(candidates, key=lambda t: (hashlib.sha256(f'{seed}|KR|{day}|{t}'.encode()).hexdigest(), t))
            selected = [t for t in order if t in positive][:5]
            book = OLD.make_book(selected, 'FIXED20')
            pool = g.set_index('ticker').loc[eligible.to_numpy()]
            peer, audit = common.match_book(pool, book, ETF, order=selected)
            books[key][date], peers[key][date] = book, peer
            audits.extend({'date': date, 'config': key, 'selector': 'CONFIRM_NEUTRAL', 'seed': seed, **row} for row in audit)
            pools.append({'date': date, 'seed': seed, 'completePool': len(candidates), 'positivePool': len(positive),
                          'actualNames': len(selected), 'selectedRankOrder': '|'.join(selected), 'matchComplete': peer is not None})
        print('KR confirmation seed prepared', seed, flush=True)
    write_books(out / 'seed-books.json.gz', books)
    write_books(out / 'seed-peer-books.json.gz', peers)
    pd.DataFrame(audits).to_csv(out / 'seed-matching-audit.csv.gz', index=False)
    pd.DataFrame(pools).to_csv(out / 'seed-pool-audit.csv.gz', index=False)
    return books, peers, audits


def weighted(book, values):
    if not book:
        return np.nan
    active = {t: w for t, w in book.items() if w > 0}
    prices = values.reindex(list(active)).to_numpy()
    return float(prices @ np.array(list(active.values()))) if np.isfinite(prices).all() else np.nan


def prepare(scratch, out):
    """Adapt frozen #350 books; extend only missing per-asset payoffs with its exact helper."""
    out.mkdir(parents=True, exist_ok=True)
    sources = source_identity()
    prepared = scratch / 'kr-us-batch-v1-prepared.pkl'
    if prepared.exists():
        I, ctx, base, *_ = pickle.loads(prepared.read_bytes())
    else:
        I, ctx, base = OLD.RC.setup(str(scratch))
    source_summary = json.loads((SOURCE / 'summary.json').read_text())
    assert I['ident'] == source_summary['inputs']['identity']
    dates = pd.DatetimeIndex(base['dates'])
    nav_path = Path('/workspace/exposure-inputs/kr/nav-input.pkl')
    nav_path.parent.mkdir(parents=True, exist_ok=True)
    nav_temp = nav_path.with_suffix('.tmp')
    nav_temp.write_bytes(pickle.dumps({'prices': I['closes'], 'volumes': I['vols'], 'sessions': I['sessions'],
                                      'rf': I['rf'], 'ctx': ctx, 'etf': ETF, 'sourceIdentity': I['ident'],
                                      'coverageSuffixDecision': json.loads((INPUTS / 'quote-hazards.json').read_text())['NAV_COVERAGE_SUFFIX_DECISION']}))
    nav_temp.replace(nav_path)
    print('KR frozen I/ctx/base verified; NAV inputs ready', flush=True)
    with gzip.open(SOURCE / 'books.json.gz', 'rt') as stream:
        old_books = dated_books({k: v for k, v in json.load(stream).items() if k != 'MATCHED'})
    with gzip.open(SOURCE / 'matched-books.json.gz', 'rt') as stream:
        old_peers = dated_books(json.load(stream))
    books = {k: old_books[v] for k, v in CONFIGS.items()}
    peers = {s: old_peers[s] for s in SELECTORS}
    passive, sectors, pool_audit, new_audit = {}, {}, [], []
    for date in dates:
        g = ctx.by[date].sort_values('ticker')
        w, industry = OLD.KD.proxy_weights(g)
        passive[date] = w.to_dict()
        sectors[date] = {t: str(v) if pd.notna(v) else 'UNCLASSIFIED' for t, v in industry.items()}
        names, original, counts = OLD.selectors(g, date)
        assert original == base['s2'][date]
        for key, source_key in CONFIGS.items():
            selector = 'S2' if key.startswith('S2_K') else key
            k = int(key[-1]) if key.startswith('S2_K') else 5
            assert books[key][date] == OLD.make_book(names[selector][:k], 'FIXED20'), (date, source_key)
        pool = g.set_index('ticker').loc[(g['_q'] & ~g.ticker.isin(OLD.C.WITHHELD)).to_numpy()]
        for k in range(1, 5):
            key = f'S2_K{k}'
            peer, audit = common.match_book(pool, books[key][date], ETF, order=names['S2'][:k])
            peers.setdefault(key, {})[date] = peer
            new_audit.extend({'date': date, 'config': key, 'selector': 'S2', **row} for row in audit)
        pool_audit.append({'date': date, 'passiveNames': len(w), 'passiveCapWeightSum': sum(w),
                           'industryUnknownWeight': sum(w[t] for t in w.index if sectors[date][t] == 'UNCLASSIFIED'), **counts})
    pd.DataFrame(pool_audit).to_csv(out / 'signal-and-proxy-pool-audit.csv', index=False)
    old_audit = pd.read_csv(SOURCE / 'matching-audit.csv.gz', parse_dates=['date'])
    old_audit = old_audit[old_audit.selector.isin(SELECTORS)].copy()
    old_audit['config'] = old_audit.selector
    audits = [*old_audit.to_dict('records'), *new_audit]
    seeds, seed_peers, seed_audit = seed_books(ctx, dates, out)
    audits.extend(seed_audit)
    pd.DataFrame(audits).to_csv(out / 'matching-audit.csv.gz', index=False)
    write_books(out / 'original-book-schedules.json.gz', books)
    write_books(out / 'peer-book-schedules.json.gz', peers)
    frames = {h: pd.read_csv(SOURCE / f'cohorts-{h}.csv.gz', parse_dates=['date', 'entry', 'exit']).set_index('date') for h in (126, 252)}
    prior_peers = {h: pd.read_csv(SOURCE / f'matched-{h}.csv', parse_dates=['date']).set_index('date') for h in (126, 252)}
    asset_source = pd.read_csv(SOURCE / 'asset-payoffs.csv.gz', parse_dates=['date', 'entry', 'exit'])
    net_asset, entries, selection, legacy, periods = {}, {}, {}, {}, {}
    asset_audits, checks, status_rows, matching_coverage = [], {}, [], []
    all_books, all_peers = dict(books, **seeds), dict(peers, **seed_peers)
    audit_map = {}
    for row in audits:
        audit_map.setdefault((row['config'], pd.Timestamp(row['date'])), []).append(row)
    for horizon in (126, 252):
        frame = frames[horizon].reindex(dates)
        source_rows = asset_source[asset_source.horizon == horizon]
        assets = source_rows.pivot(index='date', columns='ticker', values='net').reindex(index=dates, columns=I['closes'].columns)
        present = set(zip(source_rows.date, source_rows.ticker))
        entries[horizon] = frame.entry.copy()
        additional = 0
        for date in dates:
            if not bool(frame.at[date, 'mature']):
                continue
            needed = set(passive[date]) | {ETF}
            for bookset in all_books.values():
                needed.update(bookset[date])
            for bookset in all_peers.values():
                needed.update((bookset.get(date) or {}).keys())
            for ticker in sorted(needed):
                if (date, ticker) in present:
                    continue
                additional += 1
                payoff, reason = OLD.asset_payoff(I['closes'], ctx.px, ticker, frame.at[date, 'entry'], frame.at[date, 'exit'])
                assets.at[date, ticker] = payoff['net'] if payoff else np.nan
                asset_audits.append({'date': date, 'entry': frame.at[date, 'entry'], 'exit': frame.at[date, 'exit'],
                                     'horizon': horizon, 'ticker': ticker, 'status': reason or 'MEASURED',
                                     **({k: payoff[k] for k in ('gross', 'net', 'cost')} if payoff else {})})
        assets.to_csv(out / f'asset-net-{horizon}.csv.gz', index_label='date', float_format='%.15g')
        net_asset[horizon] = assets
        legacy[horizon] = pd.DataFrame({key: frame[source_key + '_excess'] for key, source_key in CONFIGS.items()}, index=dates)
        selection[horizon] = pd.DataFrame(index=dates)
        reproduction = {}
        for config, bydate in all_books.items():
            values = []
            paired_records = []
            for date in dates:
                target, peer = weighted(bydate[date], assets.loc[date]), weighted(all_peers[config].get(date), assets.loc[date])
                n = sum(t != ETF and w > 0 for t, w in bydate[date].items())
                complete = all_peers[config].get(date) is not None
                paired = bool(n and np.isfinite(target) and np.isfinite(peer))
                value = target - peer if paired else np.nan
                values.append(value)
                reasons = sorted({r['reason'] for r in audit_map.get((config, date), []) if r['reason'] != 'MATCHED'})
                reason = ('NOT_MATURED' if not bool(frame.at[date, 'mature']) else 'EMPTY_SELECTION' if not n else
                          'MATCHING_FAILED:' + '|'.join(reasons) if not complete else
                          'TARGET_ASSET_PRICE_UNRESOLVED' if not np.isfinite(target) else
                          'PEER_ASSET_PRICE_UNRESOLVED' if not np.isfinite(peer) else 'PAIRED_MEASURED')
                row = {'date': date, 'horizon': horizon, 'config': config, 'mature': bool(frame.at[date, 'mature']),
                       'actualNames': n, 'matchComplete': complete, 'targetMeasured': bool(np.isfinite(target)),
                       'peerMeasured': bool(np.isfinite(peer)), 'paired': paired, 'reason': reason}
                status_rows.append(row)
                paired_records.append(row)
                if config in CONFIGS:
                    expected = frame.at[date, CONFIGS[config] + '_net']
                    assert np.isfinite(target) == np.isfinite(expected), (horizon, config, date, 'targetMask')
                    if np.isfinite(expected):
                        error = abs(target - expected)
                        assert error < 1e-9, (horizon, config, date, error)
                        reproduction[config] = max(reproduction.get(config, 0), error)
            selection[horizon][config] = values
            states = pd.DataFrame(paired_records)
            mature_nonempty = states.mature & states.actualNames.gt(0)
            denominator = int(mature_nonempty.sum())
            matching_coverage.append({'horizon': horizon, 'config': config, 'matureNonemptyDates': denominator,
                                      'matchedMatureDates': int((mature_nonempty & states.matchComplete).sum()),
                                      'matchRate': float(states.loc[mature_nonempty, 'matchComplete'].mean()) if denominator else None,
                                      'pairedDates': int(states.paired.sum()), 'blockWeeks': horizon // 5,
                                      'independentBlocksApprox': float(states.paired.sum() / (horizon // 5)),
                                      'excludedReasons': json.dumps(dict(Counter(states.loc[~states.paired, 'reason'])), sort_keys=True)})
            if config in SELECTORS:
                expected = prior_peers[horizon][config + '_selection'].reindex(dates)
                actual = selection[horizon][config]
                assert actual.notna().equals(expected.notna()), (horizon, config, 'selectionMask')
                error = float((actual - expected).abs().max())
                assert error < 1e-9, (horizon, config, error)
                reproduction[config + '_selection'] = error
                # Preserve original emitted decimal result after the independent reproduction check.
                selection[horizon][config] = expected
        seed_cols = list(seeds)
        complete_seeds = selection[horizon][seed_cols].notna().all(axis=1)
        selection[horizon]['CONFIRM_SEED_MEAN'] = selection[horizon][seed_cols].mean(axis=1).where(complete_seeds)
        pd.DataFrame({**{s: selection[horizon][s] for s in seed_cols},
                      'allEightMeasured': complete_seeds,
                      'meanAllEightOnly': selection[horizon]['CONFIRM_SEED_MEAN'],
                      'originalSeed20261118': selection[horizon]['CONFIRM_NEUTRAL']}).to_csv(out / f'seed-selection-{horizon}.csv.gz', index_label='date')
        semi = frame.touchesSemiLed.astype('boolean').fillna(False).astype(bool)
        known = ~frame.leadershipUnknown.astype('boolean').fillna(True).astype(bool)
        periods[horizon] = {'SEMI_LED': semi, 'NO_SEMI_LED': ~semi & known,
                            'PRE_2022': frame.entry.dt.year.lt(2022), 'FROM_2022': frame.entry.dt.year.ge(2022)}
        checks[str(horizon)] = {'additionalAssetDateRowsComputed': additional, 'legacyMaxError': reproduction,
                                'passiveAllNamesFiniteDates': int(pd.Series({d: np.isfinite(weighted(passive[d], assets.loc[d])) for d in dates}).sum())}
        print('KR adapter assets', horizon, additional, 'new rows', flush=True)
    pd.DataFrame(asset_audits).to_csv(out / 'additional-asset-payoffs.csv.gz', index=False, float_format='%.15g')
    pd.DataFrame(status_rows).to_csv(out / 'matching-date-status.csv.gz', index=False)
    pd.DataFrame(matching_coverage).to_csv(out / 'matching-coverage.csv', index=False)
    seed_summary = {str(h): {'paths': {key: common.stats(selection[h][key], h) for key in seeds},
                             'allEightSameDateMean': common.stats(selection[h]['CONFIRM_SEED_MEAN'], h),
                             'originalOnAllEightDates': common.stats(selection[h]['CONFIRM_NEUTRAL'], h,
                                                                      selection[h]['CONFIRM_SEED_MEAN'].notna()),
                             'seedMeanMinusOriginalSameDates': common.stats(selection[h]['CONFIRM_SEED_MEAN'] - selection[h]['CONFIRM_NEUTRAL'], h)}
                    for h in (126, 252)}
    dump(out / 'seed-summary.json', seed_summary)
    support_audit(I, ctx, base, passive, out)
    audit = {'sourceCommit': '36ac329261f8f9000935e524d8a28c2005524c10', 'designCommit': 'e3e572f',
             'designSHA256': sha(HERE / 'DESIGN-ko.md'), 'adapterSHA256': sha(Path(__file__)),
             'sourceFilesSHA256': sources, 'sourceIdentity': I['ident'], 'decisions': len(dates),
             'configs': CONFIGS, 'confirmationSeeds': list(SEEDS), 'reproduction': checks,
             'runtime': {'python': sys.version, 'numpy': np.__version__, 'pandas': pd.__version__},
             'navInputPath': str(nav_path), 'proxyBasis': 'POSITIVE_CAP_ALL_PIT_TOP120_NO_Q_FILTER',
             'releaseVisibility': 'Inherited reconstructed industry and fundamental visibility limits; history already exposed',
             'actualFundHoldingsVerified': False}
    dump(out / 'adapter-input-audit.json', audit)
    args = {'market': 'KR', 'etf': ETF, 'dates': dates, 'books': books, 'passive': passive, 'sectors': sectors,
            'leaders': LEADERS, 'net_asset': net_asset, 'entries': entries, 'legacy': legacy,
            'peers': peers, 'selection': selection, 'out': out, 'periods': periods}
    cache = Path('/workspace/exposure-inputs/kr/adapter-input.pkl')
    temporary = cache.with_suffix('.tmp')
    temporary.write_bytes(pickle.dumps(args))
    temporary.replace(cache)
    return args


def official_audit(dates, books, passive, out):
    """Official PCF-only exposure audit; never claims invested portfolio equivalence."""
    folder = INPUTS / 'kodex-pcf'
    manifest = json.loads((folder / 'manifest.json').read_text())
    snapshots = {}
    normalized = []
    intervals, crosswalk, ends = load_membership_inputs(ROOT)
    for receipt in manifest['records']:
        raw = gzip.decompress((folder / receipt['rawFile']).read_bytes())
        if hashlib.sha256(raw).hexdigest() != receipt['sha256']:
            raise ValueError('PCF_RAW_SHA_CHANGED')
        pdf = json.loads(raw)['pdf']
        assert str(pdf['gijunYMD']) == receipt['requestedGijunYMD'] == receipt['returnedGijunYMD']
        assert len(pdf['list']) == int(pdf['totalCnt']) == int(pdf['nowCnt'])
        total = sum(float(row['evalA'].replace(',', '')) for row in pdf['list'])
        weights, names = {}, {}
        for row in pdf['list']:
            code = row['itmNo']
            ticker = code + '.KS' if re.fullmatch('[0-9A-Z]{6}', code) else code
            category = 'KRX_EQUITY_CODE_SHAPE' if ticker.endswith('.KS') else (
                'KRW_DEPOSIT' if code == 'KRD010010001' and row['secNm'] == '원화예금' else 'UNCLASSIFIED_ASSET')
            weight = float(row['evalA'].replace(',', '')) / total
            weights[ticker], names[ticker] = weight, category
            normalized.append({'snapshot': str(pd.Timestamp(receipt['returnedGijunYMD']).date()), 'ticker': ticker,
                               'code': code, 'name': row['secNm'], 'category': category, 'pcfEvalWeight': weight,
                               'issuerNoncashRatioPct': row['ratio'], 'evalA': row['evalA'], 'quantity': row['applyQ'],
                               'sourceSHA256': receipt['sha256'], 'actualFundHoldingsVerified': False})
        snapshots[pd.Timestamp(receipt['returnedGijunYMD'])] = weights, names
    pd.DataFrame(normalized).to_csv(out / 'official-pcf-normalized.csv.gz', index=False)
    exposure_rows, availability = [], []
    names = dict(books, PASSIVE=passive, ETF={d: {ETF: 1.} for d in dates})
    for date in dates:
        prior = [d for d in snapshots if d < date]
        snapshot = max(prior) if prior else None
        age = (date - snapshot).days if snapshot is not None else None
        valid = age is not None and age <= 120
        availability.append({'date': date, 'snapshot': snapshot, 'ageCalendarDays': age,
                             'status': 'DATED_PCF_AUDIT_ONLY' if valid else 'STALE_OR_UNAVAILABLE',
                             'actualFundHoldingsVerified': False, 'originalReleaseVintageVerified': False})
        if not valid:
            continue
        base, categories = snapshots[snapshot]
        def group(t):
            if categories.get(t) == 'KRW_DEPOSIT':
                return 'CASH_AND_DEPOSITS'
            if not t.endswith('.KS'):
                return 'UNCLASSIFIED_ASSET'
            industry, _ = industry_of(intervals, crosswalk, t, date.strftime('%Y-%m-%d'))
            if ends.get(t) and date.strftime('%Y-%m-%d') >= ends[t]:
                industry = None
            return industry or 'UNCLASSIFIED'
        baseline_sector = Counter()
        for t, w in base.items():
            baseline_sector[group(t)] += w
        for key, bydate in names.items():
            book = bydate.get(date)
            if not book:
                continue
            etf_weight = book.get(ETF, 0.)
            direct = {t: w for t, w in book.items() if t != ETF}
            lookthrough = {t: direct.get(t, 0.) + etf_weight * base.get(t, 0.) for t in set(base) | set(direct)}
            sectors = Counter()
            for t, w in lookthrough.items():
                sectors[group(t)] += w
            row = {'date': date, 'config': key, 'snapshot': snapshot, 'ageCalendarDays': age,
                   'listedETFWeight': etf_weight, 'directStockWeight': sum(direct.values()),
                   'officialPCFSectorL1': sum(abs(sectors.get(s, 0)-baseline_sector.get(s, 0)) for s in set(sectors) | set(baseline_sector)),
                   'industryUnknownWeight': sectors.get('UNCLASSIFIED', 0.),
                   'cashDepositWeight': sectors.get('CASH_AND_DEPOSITS', 0.),
                   'unclassifiedAssetWeight': sectors.get('UNCLASSIFIED_ASSET', 0.),
                   'sectorWeights': json.dumps(dict(sectors), sort_keys=True),
                   'pcfBaselineSectorWeights': json.dumps(dict(baseline_sector), sort_keys=True),
                   'actualFundHoldingsVerified': False, 'originalReleaseVintageVerified': False,
                   'cashSubstitutionDiagnosticSnapshot': snapshot == pd.Timestamp('2018-05-03')}
            for ticker, label in [('005930.KS', 'Samsung'), ('000660.KS', 'Hynix')]:
                row['direct' + label] = direct.get(ticker, 0.)
                row['indirect' + label] = etf_weight * base.get(ticker, 0.)
                row['total' + label] = lookthrough.get(ticker, 0.)
                row['pcfBaseline' + label] = base.get(ticker, 0.)
            row['totalLeaders'] = row['totalSamsung'] + row['totalHynix']
            row['pcfBaselineLeaders'] = row['pcfBaselineSamsung'] + row['pcfBaselineHynix']
            row['leaderAbsoluteGap'] = abs(row['totalLeaders'] - row['pcfBaselineLeaders'])
            exposure_rows.append(row)
    pd.DataFrame(availability).to_csv(out / 'official-pcf-availability.csv', index=False)
    pd.DataFrame(exposure_rows).to_csv(out / 'official-pcf-exposure-audit.csv.gz', index=False)
    result = {'snapshots': len(snapshots), 'eligibleDecisionDates': sum(r['status'] == 'DATED_PCF_AUDIT_ONLY' for r in availability),
              'totalDecisionDates': len(dates), 'maximumAgeCalendarDays': 120, 'exposureRows': len(exposure_rows),
              'status': 'OFFICIAL_PORTFOLIO_DEPOSIT_FILE_NOT_VERIFIED_FUND_HOLDINGS',
              'actualFundHoldingsVerified': False, 'originalReleaseVintageVerified': False,
              'sourceManifestSHA256': sha(folder / 'manifest.json'),
              'limitations': ['PCF can omit suspended Samsung and substitute cash, observed2018-05-03',
                              'Some stock codes lack original total-return and/or reconstructed industry lineage',
                              'Later-retrieved issuer history does not establish its original release timestamp or vintage']}
    dump(out / 'official-pcf-audit-summary.json', result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--scratch', type=Path, required=True)
    parser.add_argument('--out', type=Path, default=HERE / 'results/KR')
    parser.add_argument('--stage', choices=('all', 'prepare', 'run'), default='all')
    args = parser.parse_args(argv)
    if args.stage == 'run':
        inputs = pickle.loads(Path('/workspace/exposure-inputs/kr/adapter-input.pkl').read_bytes())
        inputs['out'] = args.out
        audit = json.loads((args.out / 'adapter-input-audit.json').read_text())
        if audit['adapterSHA256'] != sha(Path(__file__)) or audit['designSHA256'] != sha(HERE / 'DESIGN-ko.md'):
            raise ValueError('PREPARED_ADAPTER_CODE_OR_DESIGN_CHANGED')
    else:
        inputs = prepare(args.scratch, args.out)
    if args.stage in ('all', 'run'):
        from . import engine
        engine.run(**inputs)
        with gzip.open(args.out / 'funding-book-schedules.json.gz', 'rt') as stream:
            funding = dated_books(json.load(stream))
        audit_books = {**{'ORIGINAL:' + k: v for k, v in inputs['books'].items()}, **{'FUNDED:' + k: v for k, v in funding.items()}}
        official_audit(inputs['dates'], audit_books, inputs['passive'], args.out)
    else:
        official_audit(inputs['dates'], {'ORIGINAL:' + k: v for k, v in inputs['books'].items()}, inputs['passive'], args.out)


if __name__ == '__main__':
    main()
