"""Reproduce the Korean confirmation-filter contrasts on the #351 weekly axis."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import gzip
import hashlib
import json
from pathlib import Path
import pickle

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

from research.kr_us_exposure_preserving_v1 import kr as PRIOR
from research.kr_us_strategy_batch_v1 import common
from research.kr_us_strategy_batch_v1 import kr as OLD

HERE = Path(__file__).resolve().parent
SOURCE = PRIOR.SOURCE
PREVIOUS = Path(PRIOR.__file__).resolve().parent / 'results/KR'
ETF = PRIOR.ETF
LEADERS = frozenset(PRIOR.LEADERS)
SEEDS = (common.SEED, *PRIOR.SEEDS)
WHOLE = 'all_pass'
HORIZONS = (126, 252)
STOCK_WEIGHT = 0.20
ORIGINAL_KEY = 'KR:CONFIRM_NEUTRAL:FIXED20:K5'
METRICS = ('etfNet', 'passNet', 'failNet', 'selection', 'replacement', 'total')
SCENARIOS = {'bothMinus100': (-1., -1.), 'bothZero': (0., 0.), 'bothPlus100': (1., 1.),
             'selectionLow': (-1., 1.), 'selectionHigh': (1., -1.)}
PRICE_FAILURE_FIELDS = ('date', 'horizon', 'entry', 'exit', 'ticker', 'originalReason',
                        'detail', 'hasEntryQuote', 'hasExitQuote', 'lastQuote')
STRESS_FIELDS = ('date', 'config', 'pairs', 'missingPass', 'missingFail', 'unknownPassWeight', 'unknownFailWeight',
                 'hasUnquotedEntry', *(f'{name}_{field}' for name in SCENARIOS for field in ('selection', 'replacement', 'total')))


@dataclass(frozen=True)
class Match:
    pass_names: tuple[str, ...]
    pairs: tuple[tuple[str, str], ...]


def match(complete, pass_names):
    """Maximize cardinality before minimizing total |log(cap ratio)| in each industry."""
    fail = complete.loc[~complete['passFilter']]
    selected = complete.loc[list(pass_names)]
    audit = {
        ticker: {'passTicker': ticker, 'rank': i, 'industry': selected.at[ticker, 'industry'],
                 'passCap': float(selected.at[ticker, '_mcap']), 'failTicker': None,
                 'failCap': None, 'capRatio': None, 'logCapDistance': None,
                 'sameIndustryFails': 0, 'withinCaliperFails': 0, 'reason': None}
        for i, ticker in enumerate(pass_names, 1)
    }
    for row in audit.values():
        if pd.isna(row['industry']):
            row['reason'] = 'PASS_INDUSTRY_MISSING'
        elif not np.isfinite(row['passCap']) or row['passCap'] <= 0:
            row['reason'] = 'PASS_CAP_INVALID'
    for sector, pass_group in selected.groupby('industry', sort=True):
        pass_ids = sorted(t for t in pass_group.index if audit[t]['reason'] is None)
        if not pass_ids:
            continue
        same = fail.loc[fail.industry.eq(sector)]
        peers = same.loc[np.isfinite(same['_mcap']) & same['_mcap'].gt(0)].sort_index()
        if peers.empty:
            for ticker in pass_ids:
                audit[ticker].update(sameIndustryFails=len(same),
                                     reason='FAIL_CAP_INVALID_IN_INDUSTRY' if len(same) else 'NO_FAIL_IN_INDUSTRY')
            continue
        ratio = peers['_mcap'].to_numpy() / selected.loc[pass_ids, '_mcap'].to_numpy()[:, None]
        valid = (ratio >= .5) & (ratio <= 2)
        distance = np.abs(np.log(ratio))
        n, m = ratio.shape
        # A dummy assignment costs more than the feasible distance summed over all rows.
        penalty = n + 1
        assignment_cost = np.full((n, m + n), float(penalty))
        assignment_cost[:, :m] = np.where(valid, distance, 2 * penalty)
        indices, columns = linear_sum_assignment(assignment_cost)
        for i, j in zip(indices, columns, strict=True):
            row = audit[pass_ids[i]]
            row.update(sameIndustryFails=len(same), withinCaliperFails=int(valid[i].sum()))
            if j < m:
                assert valid[i, j]
                row.update(failTicker=peers.index[j], failCap=float(peers.iloc[j]['_mcap']),
                           capRatio=float(ratio[i, j]), logCapDistance=float(distance[i, j]), reason='MATCHED')
            else:
                row['reason'] = ('SCARCE_FAIL_PEER_ASSIGNED_TO_ANOTHER_PASS' if valid[i].any()
                                 else 'NO_FAIL_IN_CAP_CALIPER')
    rows = list(audit.values())
    assert all(row['reason'] for row in rows)
    pairs = tuple((row['passTicker'], row['failTicker']) for row in rows if row['failTicker'] is not None)
    return Match(tuple(pass_names), pairs), rows


def seed_top(positive, date, seed):
    return tuple(sorted(positive, key=lambda t: (
        hashlib.sha256(f'{seed}|KR|{date:%Y-%m-%d}|{t}'.encode()).hexdigest(), t))[:5])


def read_books(path):
    with gzip.open(path, 'rt') as stream:
        return json.load(stream)


def write_csv(path, values):
    compression = {'method': 'gzip', 'mtime': 0} if str(path).endswith('.gz') else None
    pd.DataFrame(values).to_csv(path, index=False, float_format='%.13g', compression=compression)


def load_inputs(scratch):
    prepared = scratch / 'kr-us-batch-v1-prepared.pkl'
    if prepared.exists():
        with prepared.open('rb') as stream:
            inputs, context, base, *_ = pickle.load(stream)
    else:
        inputs, context, base = OLD.RC.setup(str(scratch))
    identity = json.loads((SOURCE / 'summary.json').read_text())['inputs']['identity']
    if inputs['ident'] != identity:
        raise ValueError('Korean prepared inputs differ from #350 identity')
    return inputs, context, pd.DatetimeIndex(base['dates'])


def prepare_matches(context, dates, out):
    source_books = read_books(SOURCE / 'books.json.gz')[ORIGINAL_KEY]
    prior_books = read_books(PREVIOUS / 'seed-books.json.gz')
    matches, pair_rows, candidate_rows, pool_rows = {}, [], [], []
    fields = [OLD.VALUE, *OLD.BUSINESS]
    for date in dates:
        candidates = context.by[date].set_index('ticker').sort_index()
        assert candidates.index.is_unique
        eligible = candidates['_q'] & ~candidates.index.isin(OLD.C.WITHHELD)
        observed = np.isfinite(candidates[fields])
        complete = eligible & observed.all(axis=1)
        passed = complete & candidates[OLD.BUSINESS].gt(0).all(axis=1)
        source_pass = eligible & candidates[OLD.VALUE].notna() & candidates.b08Confirmed.eq(1)
        assert passed.equals(source_pass), date
        positive = tuple(candidates.index[passed])
        measured = candidates.loc[complete, ['industry', '_mcap']].assign(passFilter=passed[complete])
        for ticker in candidates.index[eligible]:
            candidate_rows.append({'date': date, 'ticker': ticker, 'industry': candidates.at[ticker, 'industry'],
                                   'mcap': candidates.at[ticker, '_mcap'],
                                   'status': ('PASS' if passed[ticker] else 'MEASURED_FAIL' if complete[ticker]
                                              else 'FIELD_UNOBSERVED'),
                                   'missingFields': '|'.join(observed.columns[~observed.loc[ticker]]),
                                   **candidates.loc[ticker, fields].to_dict()})
        day = f'{date:%Y-%m-%d}'
        scopes = {WHOLE: positive}
        for seed in SEEDS:
            names = seed_top(positive, date, seed)
            expected = source_books[day] if seed == SEEDS[0] else prior_books[f'CONFIRM_SEED{seed}'][day]
            assert OLD.make_book(names, 'FIXED20') == expected, (date, seed, names, expected)
            assert names == tuple(t for t in expected if t != ETF), (date, seed)
            scopes[str(seed)] = names
        matches[date] = {}
        for config, names in scopes.items():
            matches[date][config], audit = match(measured, names)
            pair_rows.extend({'date': date, 'config': config, **row} for row in audit)
        pool_rows.append({'date': date, 'originalCandidates': len(candidates), 'qualityEligible': int(eligible.sum()),
                          'qualityAndValueObserved': int((eligible & observed[OLD.VALUE]).sum()),
                          'qualityAnyUnobserved': int((eligible & ~complete).sum()), 'complete': int(complete.sum()),
                          'measuredFailures': int((complete & ~passed).sum()), 'passes': len(positive),
                          'allPassMatchedPairs': len(matches[date][WHOLE].pairs),
                          'maxFiveShortfall': len(positive) < 5})
    write_csv(out / 'candidate-audit.csv.gz', candidate_rows)
    write_csv(out / 'matching-audit.csv.gz', pair_rows)
    write_csv(out / 'pool-counts.csv', pool_rows)
    return matches, pd.DataFrame(pair_rows), pd.DataFrame(pool_rows).set_index('date')


def prices_on_date(inputs, context, needed, date, entry, exit_, horizon):
    values, missing, measured = {}, [], []
    closes, px = inputs['closes'], context.px
    for ticker in sorted(needed):
        payoff, reason = OLD.asset_payoff(closes, px, ticker, entry, exit_)
        if payoff is not None:
            values[ticker] = payoff['net']
            measured.append({'date': date, 'entry': entry, 'exit': exit_, 'ticker': ticker,
                             **{field: payoff[field] for field in ('gross', 'net', 'cost')}})
            continue
        raw_entry, raw_exit = closes.at[entry, ticker], closes.at[exit_, ticker]
        entry_quote = bool(np.isfinite(raw_entry) and raw_entry > 0)
        exit_quote = bool(np.isfinite(raw_exit) and raw_exit > 0)
        terminal = px.terminal.get(ticker)
        terminal_before_exit = terminal is not None and terminal < px.pos[exit_]
        detail = ('ENTRY_PRICE_MISSING' if not entry_quote else
                  'TERMINAL_PROCEEDS_UNRESOLVED' if terminal_before_exit else
                  'EXIT_PRICE_MISSING' if not exit_quote else reason)
        missing.append({'date': date, 'horizon': horizon, 'entry': entry, 'exit': exit_, 'ticker': ticker,
                        'originalReason': reason, 'detail': detail, 'hasEntryQuote': entry_quote,
                        'hasExitQuote': exit_quote, 'lastQuote': px.sessions[terminal] if terminal is not None else None})
    return values, missing, measured


def mean_names(names, values):
    if names and all(ticker in values for ticker in names):
        return float(np.mean([values[ticker] for ticker in names]))
    return np.nan


def payoff_metrics(etf, pass_sleeve, fail_sleeve, weight=STOCK_WEIGHT):
    pass_net = (1 - weight) * etf + weight * pass_sleeve
    fail_net = (1 - weight) * etf + weight * fail_sleeve
    return {'etfNet': etf, 'passNet': pass_net, 'failNet': fail_net, 'selection': pass_net - fail_net,
            'replacement': fail_net - etf, 'total': pass_net - etf}


def from_pairs(pairs, values, weight=STOCK_WEIGHT):
    passed = tuple(t for t, _ in pairs)
    failed = tuple(t for _, t in pairs)
    return payoff_metrics(values[ETF], mean_names(passed, values), mean_names(failed, values), weight=weight)


def stress_row(date, config, pairs, values, missing):
    """Stress unresolved exits after a quoted entry. Keep pair matching, weights and measured legs fixed."""
    pass_names, fail_names = zip(*pairs, strict=True)
    missing_pass = [t for t in pass_names if t not in values]
    missing_fail = [t for t in fail_names if t not in values]
    groups = [missing[t] for t in (*missing_pass, *missing_fail)]
    row = {'date': date, 'config': config, 'pairs': len(pairs), 'missingPass': '|'.join(missing_pass),
           'missingFail': '|'.join(missing_fail), 'unknownPassWeight': STOCK_WEIGHT * len(missing_pass) / len(pairs),
           'unknownFailWeight': STOCK_WEIGHT * len(missing_fail) / len(pairs),
           'hasUnquotedEntry': any(not group['hasEntryQuote'] for group in groups)}
    if row['hasUnquotedEntry']:
        return row
    for name, (p, f) in SCENARIOS.items():
        stressed = {**values, **dict.fromkeys(missing_pass, p), **dict.fromkeys(missing_fail, f)}
        for field, value in from_pairs(pairs, stressed).items():
            if field in ('selection', 'replacement', 'total'):
                row[f'{name}_{field}'] = value
    return row


def cohort_records(inputs, context, dates, matches, horizon, out):
    frame = pd.read_csv(SOURCE / f'cohorts-{horizon}.csv.gz', parse_dates=['date', 'entry', 'exit']).set_index('date')
    assert frame.index.equals(dates)
    prior_assets = pd.read_csv(PREVIOUS / f'asset-net-{horizon}.csv.gz', parse_dates=['date']).set_index('date')
    records, failures, stresses, attributions, payoffs = [], [], [], [], []
    checks = {'entryExitChecked': 0, 'etfMaxError': 0., 'legacyBookMaxError': 0.,
              'assetMaxError': 0., 'assetPayoffsChecked': 0, 'decompositionMaxError': 0.}
    sessions = inputs['sessions']
    end = inputs['closes'][ETF].last_valid_index()
    for date, baseline in frame.iterrows():
        entry = OLD.M.next_session(sessions, date)
        stop = sessions.get_loc(entry) + horizon
        exit_ = sessions[stop] if stop < len(sessions) else pd.NaT
        mature = bool(pd.notna(exit_) and exit_ <= end)
        assert baseline.entry == entry and (pd.isna(baseline.exit) if pd.isna(exit_) else baseline.exit == exit_)
        assert baseline.mature == mature
        checks['entryExitChecked'] += 1
        date_matches = matches[date]
        needed = {ETF, *date_matches[WHOLE].pass_names}
        for matched in date_matches.values():
            needed.update(fail for _, fail in matched.pairs)
        if mature:
            values, missing_rows, measured = prices_on_date(inputs, context, needed, date, entry, exit_, horizon)
            failures.extend(missing_rows)
            payoffs.extend(measured)
            missing = {r['ticker']: r for r in missing_rows}
            assert ETF in values
            checks['etfMaxError'] = max(checks['etfMaxError'], abs(values[ETF] - baseline['KR:ETF_net']))
            want = prior_assets.loc[date, sorted(needed)].dropna()
            got = pd.Series(values, dtype=float).reindex(want.index)
            assert got.notna().all(), (horizon, date)
            checks['assetMaxError'] = max(checks['assetMaxError'], float((want - got).abs().max()))
            checks['assetPayoffsChecked'] += len(want)
        for config, matched in date_matches.items():
            n, m = len(matched.pass_names), len(matched.pairs)
            support = bool(m and (config == WHOLE or n == m))
            semi = mature and bool(baseline.touchesSemiLed)
            leadership_known = mature and not bool(baseline.leadershipUnknown)
            row = {'date': date, 'entry': entry, 'exit': exit_, 'config': config, 'mature': mature,
                   'semiconductorPeriod': ('SEMI_LED' if semi else 'NON_SEMI_LED' if leadership_known else 'UNKNOWN'),
                   'names': n, 'pairs': m, 'matchedCandidateDate': support,
                   'passContainsLeader': bool(LEADERS.intersection(matched.pass_names)),
                   'pairedContainsLeader': any(p in LEADERS or f in LEADERS for p, f in matched.pairs)}
            records.append(row)
            if not mature:
                row['status'] = 'NOT_MATURED'
                continue
            etf = values[ETF]
            pass_sleeve = mean_names(matched.pass_names, values) if n else etf
            own = payoff_metrics(etf, pass_sleeve, np.nan)
            own_missing = [t for t in matched.pass_names if t in missing]
            row.update(ownEtfNet=etf, ownPassNet=own['passNet'], ownTotal=own['total'], ownStockOnlyTotal=pass_sleeve - etf,
                       ownStockWeight=STOCK_WEIGHT if n else 0., ownMissing='|'.join(own_missing))
            if own_missing:
                own_pairs = tuple((p, ETF) for p in matched.pass_names)
                stresses.append(stress_row(date, config + '_own', own_pairs, values, missing))
            if config == str(SEEDS[0]):
                expected = baseline[ORIGINAL_KEY + '_net']
                assert np.isfinite(own['passNet']) == np.isfinite(expected), (date, horizon, 'legacy book mask')
                if np.isfinite(expected):
                    checks['legacyBookMaxError'] = max(checks['legacyBookMaxError'], abs(expected - own['passNet']))
            if not support:
                row['status'] = 'NO_PASS' if not n else 'NO_PAIR' if config == WHOLE else 'INCOMPLETE_MATCH'
                continue
            unresolved = set(t for pair in matched.pairs for t in pair if t in missing)
            row['matchedMissing'] = '|'.join(sorted(unresolved))
            if unresolved:
                row['status'] = 'UNRESOLVED_PAYOFF'
                stresses.append(stress_row(date, config, matched.pairs, values, missing))
                continue
            row['status'] = 'MEASURED'
            paired = from_pairs(matched.pairs, values)
            row.update(paired)
            error = abs(paired['selection'] + paired['replacement'] - paired['total'])
            checks['decompositionMaxError'] = max(checks['decompositionMaxError'], error)
            if config == WHOLE:
                row.update({f'stockOnly_{k}': v for k, v in from_pairs(matched.pairs, values, weight=1.).items()})
            price_complete_pairs = [(p, f) for p, f in matched.pairs if p not in LEADERS and f not in LEADERS]
            row['pairsExLeaders'] = len(price_complete_pairs)
            row.update({f'exLeaders_{k}': v for k, v in from_pairs(price_complete_pairs, values).items()})
            if config in (WHOLE, str(SEEDS[0])):
                for p, f in matched.pairs:
                    weight = STOCK_WEIGHT / m
                    total, replacement = (weight * (values[t] - etf) for t in (p, f))
                    attributions.append({'date': date, 'entryYear': entry.year, 'config': config, 'passTicker': p,
                                         'failTicker': f, 'weight': weight, 'selection': total - replacement,
                                         'replacement': replacement, 'total': total})
    data = pd.DataFrame(records)
    assert all(checks[key] < 1e-9 for key in ('etfMaxError', 'legacyBookMaxError', 'assetMaxError'))
    assert checks['decompositionMaxError'] < 1e-12
    write_csv(out / f'cohorts-{horizon}.csv.gz', data)
    write_csv(out / f'asset-payoffs-{horizon}.csv.gz', payoffs)
    stress_frame = pd.DataFrame(stresses, columns=STRESS_FIELDS)
    write_csv(out / f'stress-{horizon}.csv.gz', stress_frame)
    write_csv(out / f'pair-attribution-{horizon}.csv.gz', attributions)
    return data, failures, stress_frame, pd.DataFrame(attributions), checks


def metrics(frame, horizon, mask=None, mapping=None, prefix=''):
    if mapping is None:
        mapping = {field: prefix + field for field in METRICS}
    return {name: common.stats(frame[column], horizon, mask) for name, column in mapping.items()}


def own_metrics(frame, horizon, mask=None):
    mapping = {'etfNet': 'ownEtfNet', 'passNet': 'ownPassNet', 'total': 'ownTotal',
               'stockOnlyTotal': 'ownStockOnlyTotal'}
    price_complete = frame.ownTotal.notna()
    return metrics(frame, horizon, price_complete if mask is None else price_complete & mask, mapping)


def summarize_coverage(frame, audit, pool):
    mature = frame.mature
    active = mature & frame.names.gt(0)
    support = mature & frame.matchedCandidateDate
    pairs = int(frame.loc[active, 'pairs'].sum())
    names = int(frame.loc[active, 'names'].sum())
    scoped = audit.loc[audit.date.isin(frame.index[mature])]
    measured = frame.status.eq('MEASURED')
    return {'matureDates': int(mature.sum()), 'nonemptyDates': int(active.sum()),
            'shortfallDates': int((mature & pool.maxFiveShortfall).sum()),
            'candidatePassNames': names, 'matchedNames': pairs, 'matchedNameRate': pairs / names if names else None,
            'matchedCandidateDates': int(support.sum()), 'matchedDateRate': float(support.sum()/active.sum()) if active.any() else None,
            'fullyMatchedDates': int((active & frame.pairs.eq(frame.names)).sum()),
            'pricedDates': int(measured.sum()), 'pricedMatchedNames': int(frame.loc[measured, 'pairs'].sum()),
            'pairedDateFirst': frame.index[measured].min() if measured.any() else None,
            'pairedDateLast': frame.index[measured].max() if measured.any() else None,
            'status': frame.status.value_counts().to_dict(), 'legReasons': scoped.reason.value_counts().to_dict(),
            'matchedCapRatioMedian': scoped.capRatio.median(),
            'matchedCapRatioRange': [scoped.capRatio.min(), scoped.capRatio.max()],
            'matchedAverageLogCapDistance': scoped.logCapDistance.mean()}


def summarize_stress(frame, stress, horizon, config, field, basis):
    relevant = stress.loc[stress.config.eq(config)].set_index('date') if len(stress) else pd.DataFrame()
    rows = basis.notna()
    if relevant.empty:
        return {'measuredDates': int(rows.sum()), 'affectedDates': 0, 'unquotedEntryDates': 0,
                'scenarios': {}, 'commonMissingNetBreakEven': None}
    add = relevant.loc[~relevant.hasUnquotedEntry]
    scenarios = {name: common.stats(basis.combine_first(add.get(f'{name}_{field}', pd.Series(dtype=float)))
                                    .reindex(frame.index), horizon) for name in SCENARIOS}
    # Both sides' unobserved names are assigned one identical unknown net value.
    # A zero coefficient means that this common value cannot move the signed difference.
    intercept = scenarios['bothZero']['mean']
    plus = scenarios['bothPlus100']['mean']
    slope = plus - intercept if intercept is not None and plus is not None else 0.
    return {'measuredDates': int(rows.sum()), 'affectedDates': len(relevant),
            'unquotedEntryDates': int(relevant.hasUnquotedEntry.sum()), 'eligibleStressDates': len(add),
            'sumUnresolvedPassWeight': relevant.unknownPassWeight.sum(),
            'sumUnresolvedFailWeight': relevant.unknownFailWeight.sum(),
            'scenarios': scenarios,
            'commonMissingNetBreakEven': -intercept / slope if abs(slope) > 1e-14 else None}


def annual_attribution(frame, horizon, config):
    combined = []
    for year in sorted(frame.entry.dt.year.unique()):
        mask = frame.entry.dt.year.eq(year)
        row = {'horizon': horizon, 'config': config, 'entryYear': int(year), 'dates': int((mask & frame.selection.notna()).sum())}
        for field in ('selection', 'replacement', 'total', 'ownTotal'):
            values = frame.loc[mask, field].dropna()
            row[f'{field}Sum'] = float(values.sum()) if len(values) else np.nan
            row[f'{field}Mean'] = float(values.mean()) if len(values) else np.nan
        combined.append(row)
    return combined


def top_year(annual, horizon, config, field):
    candidates = [row for row in annual if row['config'] == config and row['horizon'] == horizon
                  and np.isfinite(row[f'{field}Sum'])]
    return max(candidates, key=lambda row: (row[f'{field}Sum'], -row['entryYear']))['entryYear'] if candidates else None


def split_sensitivity(frame, horizon, annual, config):
    measured = frame.selection.notna()
    year = top_year(annual, horizon, config, 'selection')
    total_year = top_year(annual, horizon, config, 'total')
    own_year = top_year(annual, horizon, config, 'ownTotal')
    return {
        'exLeadersDates': metrics(frame, horizon, measured & ~frame.pairedContainsLeader),
        'leaderDatesOnly': metrics(frame, horizon, measured & frame.pairedContainsLeader),
        'exLeadersPairs': metrics(frame, horizon, prefix='exLeaders_'),
        'semiLed': metrics(frame, horizon, frame.semiconductorPeriod.eq('SEMI_LED')),
        'nonSemiLed': metrics(frame, horizon, frame.semiconductorPeriod.eq('NON_SEMI_LED')),
        'unknownSemi': metrics(frame, horizon, frame.semiconductorPeriod.eq('UNKNOWN')),
        'exTopEntryYear': metrics(frame, horizon, frame.entry.dt.year.ne(year)),
        'topSelectionEntryYear': year, 'topTotalEntryYear': total_year,
        'exTopTotalEntryYear': metrics(frame, horizon, frame.entry.dt.year.ne(total_year)),
        'ownExLeadersDates': own_metrics(frame, horizon, ~frame.passContainsLeader),
        'ownSemiLed': own_metrics(frame, horizon, frame.semiconductorPeriod.eq('SEMI_LED')),
        'ownNonSemiLed': own_metrics(frame, horizon, frame.semiconductorPeriod.eq('NON_SEMI_LED')),
        'ownUnknownSemi': own_metrics(frame, horizon, frame.semiconductorPeriod.eq('UNKNOWN')),
        'ownTopEntryYear': own_year,
        'ownExTopEntryYear': own_metrics(frame, horizon, frame.entry.dt.year.ne(own_year)),
    }


def summarize_horizon(data, audit, pool, stress, attribution, horizon, out):
    dates = pool.index
    frames = {key: frame.set_index('date').reindex(dates) for key, frame in data.groupby('config', sort=False)}
    whole, k5 = frames[WHOLE], frames[str(SEEDS[0])]
    measured_whole, measured_k5 = whole.selection.notna(), k5.selection.notna()
    common_pairs = measured_whole & measured_k5
    common_own = whole.ownTotal.notna() & k5.ownTotal.notna()
    seeds = tuple(str(s) for s in SEEDS)
    seed_selection = pd.DataFrame({seed: frames[seed].selection for seed in seeds})
    available = seed_selection.notna().sum(axis=1)
    all_nine = available.eq(len(SEEDS))
    all_own = pd.DataFrame({seed: frames[seed].ownTotal for seed in seeds}).notna().all(axis=1)
    seed_rows = []
    for seed in seeds:
        frame = frames[seed]
        row = {'seed': int(seed), 'paired': metrics(frame, horizon), 'pairedCommon': metrics(frame, horizon, all_nine),
               'own': own_metrics(frame, horizon), 'ownCommon': own_metrics(frame, horizon, all_own)}
        seed_rows.append(row)
    seed_daily = pd.DataFrame({'date': dates, 'availableSeeds': available, 'allNineMatched': all_nine,
                               'availableSeedMean': seed_selection.mean(axis=1),
                               'allNineMean': seed_selection.mean(axis=1).where(all_nine),
                               **{f'{seed}_{field}': frames[seed][field] for seed in seeds
                                  for field in ('selection', 'replacement', 'total', 'ownTotal')}})
    write_csv(out / f'seed-daily-{horizon}.csv.gz', seed_daily)
    seed_ranges, seed_common, seed_available = {}, {}, {}
    for field in ('selection', 'replacement', 'total', 'ownTotal'):
        paired = field != 'ownTotal'
        cols = [f'{seed}_{field}' for seed in seeds]
        means = [row['paired'][field]['mean'] if paired else row['own']['total']['mean'] for row in seed_rows]
        means = [m for m in means if m is not None]
        seed_ranges[field] = {'nSeeds': len(means), 'low': min(means) if means else None,
                              'high': max(means) if means else None, 'meanOfOwnMeans': np.mean(means) if means else None}
        daily = seed_daily[cols].mean(axis=1)
        seed_common[field] = common.stats(daily, horizon, all_nine if paired else all_own)
        seed_available[field] = common.stats(daily, horizon)
    coverage = {config: summarize_coverage(frame, audit.loc[audit.config.eq(config)], pool)
                for config, frame in frames.items()}
    annual = [row for config in (WHOLE, str(SEEDS[0]))
              for row in annual_attribution(frames[config], horizon, config)]
    named_two = {}
    for config in (WHOLE, str(SEEDS[0])):
        names = attribution.loc[attribution.config.eq(config)]
        n = coverage[config]['pricedDates']
        named_two[config] = {}
        for ticker in sorted(LEADERS):
            as_pass = names.loc[names.passTicker.eq(ticker)]
            as_fail = names.loc[names.failTicker.eq(ticker)]
            fail_net_minus_etf = as_fail.replacement.sum()
            named_two[config][ticker] = {'passDates': int(as_pass.date.nunique()), 'failDates': int(as_fail.date.nunique()),
                                         'passContributionMean': float(as_pass.total.sum() / n) if n else None,
                                         'failContributionMean': float(fail_net_minus_etf / n) if n else None,
                                         'netSelectionContributionMean': float((as_pass.total.sum() - fail_net_minus_etf)/n) if n else None}
    summary = {
        'whole': {'matched20': metrics(whole, horizon), 'matched100': metrics(whole, horizon, prefix='stockOnly_'),
                  'allPass20': own_metrics(whole, horizon),
                  'allPass20OnMatchedDates': own_metrics(whole, horizon, measured_whole),
                  'allPass20OnK5Dates': own_metrics(whole, horizon, measured_k5),
                  'matched20OnK5Dates': metrics(whole, horizon, common_pairs),
                  'matched20OnFullyMatchedDates': metrics(whole, horizon, whole.names.eq(whole.pairs)),
                  **split_sensitivity(whole, horizon, annual, WHOLE)},
        'k5': {'own': own_metrics(k5, horizon), 'paired': metrics(k5, horizon),
               'wholeCommon': metrics(k5, horizon, common_pairs),
               'deltaSelectionVsWholeOnCommonDates': common.stats(k5.selection - whole.selection, horizon, common_pairs),
               'deltaOwnTotalVsWholeOnCommonDates': common.stats(k5.ownTotal - whole.ownTotal, horizon, common_own),
               **split_sensitivity(k5, horizon, annual, str(SEEDS[0]))},
        'seedRange': seed_ranges, 'seedCommon': seed_common, 'seedAvailable': seed_available, 'seeds': seed_rows,
        'availableSeedCounts': available.loc[k5.mature].value_counts().sort_index().to_dict(),
        'namedTwoContributions': named_two,
        'coverage': coverage,
        'matureCandidateCounts': {k: int(v) for k, v in pool.loc[k5.mature].drop(columns='maxFiveShortfall').sum().items()},
        'priceStress': {
            'wholeSelection': summarize_stress(whole, stress, horizon, WHOLE, 'selection', whole.selection),
            'wholeOwnTotal': summarize_stress(whole, stress, horizon, WHOLE + '_own', 'total', whole.ownTotal),
            'k5Selection': summarize_stress(k5, stress, horizon, str(SEEDS[0]), 'selection', k5.selection),
            'k5Total': summarize_stress(k5, stress, horizon, str(SEEDS[0]), 'total', k5.total),
            'k5OwnTotal': summarize_stress(k5, stress, horizon, str(SEEDS[0]) + '_own', 'total', k5.ownTotal),
        },
    }
    return summary, annual


def flatten(path, horizons):
    rows = []

    def append(horizon, data, prefix):
        if isinstance(data, dict) and {'n', 'mean', 'ci', 'blockWeeks'}.issubset(data):
            lower, upper = data['ci'] or (None, None)
            fields = {key: data[key] for key in ('n', 'mean', 'pOneSidedApprox', 'blockWeeks', 'independentBlocksApprox')}
            rows.append({'horizon': horizon, 'comparison': '.'.join(prefix), **fields, 'ciLow': lower, 'ciHigh': upper})
        elif isinstance(data, dict):
            for key, value in data.items():
                append(horizon, value, (*prefix, str(key)))
        elif isinstance(data, list):
            for i, value in enumerate(data):
                key = str(value.get('seed', i)) if isinstance(value, dict) else str(i)
                append(horizon, value, (*prefix, key))

    for horizon, summary in horizons.items():
        append(horizon, summary, ())
    write_csv(path, rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scratch', type=Path, default=Path('/workspace/s2-inputs'))
    parser.add_argument('--out', type=Path, default=HERE / 'results/KR')
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    inputs, context, dates = load_inputs(args.scratch)
    matches, audit, pool = prepare_matches(context, dates, args.out)
    print(f'KR confirmation matching fixed for {len(dates)} decisions', flush=True)
    horizons, validation, failures, annual = {}, {}, [], []
    for horizon in HORIZONS:
        data, missing, stress, attr, checks = cohort_records(inputs, context, dates, matches, horizon, args.out)
        summary, years = summarize_horizon(data, audit, pool, stress, attr, horizon, args.out)
        horizons[str(horizon)] = summary
        validation[str(horizon)] = checks
        failures.extend(missing)
        annual.extend(years)
        print(f'KR confirmation payoffs completed ({horizon} sessions)', flush=True)
    main_six = horizons['126']
    primary = {'wholePassVsFail': main_six['whole']['matched100']['selection'],
               'originalK5PassVsFail': main_six['k5']['paired']['selection'],
               'originalK5PassVsETF': main_six['k5']['paired']['total']}
    holm = common.holm({key: value['pOneSidedApprox'] for key, value in primary.items()})
    coverage = [{'horizon': horizon, 'config': config, **row}
                for horizon, summary in horizons.items() for config, row in summary['coverage'].items()]
    flatten(args.out / 'metrics.csv', horizons)
    write_csv(args.out / 'coverage.csv', coverage)
    write_csv(args.out / 'entryyear.csv', annual)
    write_csv(args.out / 'missing-payoffs.csv', pd.DataFrame(failures, columns=PRICE_FAILURE_FIELDS))
    OLD.dump(args.out / 'summary.json', {'market': 'KR', 'dates': len(dates), 'seeds': SEEDS, 'horizons': horizons,
                                        'primary6': primary, 'holm6': holm})
    reused = [SOURCE / 'summary.json', SOURCE / 'books.json.gz', PREVIOUS / 'seed-books.json.gz',
              *(SOURCE / f'cohorts-{h}.csv.gz' for h in HORIZONS),
              *(PREVIOUS / f'asset-net-{h}.csv.gz' for h in HORIZONS)]
    OLD.dump(args.out / 'verification.json', {'sourceCommit': '0eceb6f135dd3bd08f35950997d36129bfe67f65',
                                             'sourceIdentity': inputs['ident'], 'seedBooksChecked': len(dates) * len(SEEDS),
                                             'checks': validation,
                                             'sourceFilesSHA256': {str(p.relative_to(HERE.parents[1])): OLD.sha(p) for p in reused}})
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
