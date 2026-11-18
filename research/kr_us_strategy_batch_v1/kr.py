"""Registered Korean batch; source inputs/engines are frozen, outputs are research only.

python -m research.kr_us_strategy_batch_v1.kr --scratch /workspace/s2-inputs
"""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import pickle
import time

import numpy as np
import pandas as pd

from research.followup_round8_v1 import kr_switch as KS
from research.kr_s2_rank_ladder_v1 import run as L

A, C, M, RC, KD = L.A, L.C, L.M, L.RC, L.KD
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OLD = ROOT / 'research/kr_s2_rank_ladder_v1/results'
BUSINESS = ['C01_returnOnAssets', 'C05_ocfToAssets', 'C14_ocfImprovement']
VALUE = 'B08_valueBusinessConfirmation'
TWO = {'005930.KS', '000660.KS'}
ETF = 'KR:ETF'
REG = json.loads((HERE / 'registry.json').read_text())
GRID = {k: v for k, v in REG['grid'].items() if v['market'] == 'KR'}
SELECTORS = REG['krSelectors']


def common():
    from research.kr_us_strategy_batch_v1 import common as module
    return module


def clean(value):
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [clean(v) for v in value]
    if isinstance(value, (pd.Timestamp, Path)):
        return str(value)
    if isinstance(value, np.ndarray):
        return clean(value.tolist())
    if isinstance(value, np.generic):
        return clean(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def dump(path, value):
    path.write_text(json.dumps(clean(value), ensure_ascii=False, indent=1, allow_nan=False) + '\n')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def make_book(names, style):
    """FIXED20 uses actual names, including short books; no names means all ETF."""
    if not names:
        return {M.ETF: 1.0}
    w = .2 if style == 'SLOT20' else .2 / len(names)
    result = dict.fromkeys(names, w)
    residual = 1.0 - w * len(names)
    if residual > 1e-12:
        result[M.ETF] = residual
    return result


def selectors(g, date):
    """A complete factorial pool is measured before confirmation's sign is used."""
    eligible = g['_q'] & ~g.ticker.isin(C.WITHHELD)
    complete = eligible & g[VALUE].notna() & g[BUSINESS].notna().all(axis=1)
    neutral = common().neutral_order(g.loc[complete, 'ticker'], date, 'KR')
    positive = set(g.loc[complete & g[BUSINESS].gt(0).all(axis=1), 'ticker'])
    source_confirmed = set(g.loc[eligible & g[VALUE].notna() & g.b08Confirmed.eq(1), 'ticker'])
    if positive != source_confirmed:
        raise AssertionError(f'COMPLETE_POSITIVE_POOL_DIFFERS_FROM_ORIGINAL_CONFIRMED:{date}')
    original, s2, _ = C.sleeve_book('S2_VALUE_CONFIRMED', g)
    original_value = C.sleeve_book('S2_VALUE_CONFIRMED', g, score=g[VALUE])[1]
    complete_value = C.sleeve_book('S2_VALUE_CONFIRMED', g,
                                  score=g[VALUE].where(complete))[1]
    complete_s2 = C.sleeve_book('S2_VALUE_CONFIRMED', g,
                               score=g[VALUE].where(complete & g.ticker.isin(positive)))[1]
    if s2 != complete_s2:
        raise AssertionError(f'ORIGINAL_S2_NOT_COMPLETE_POSITIVE:{date}:{s2}:{complete_s2}')
    out = {'S2': s2, 'VALUE_ORIGINAL': original_value, 'VALUE_COMPLETE': complete_value,
           'QUALITY_NEUTRAL': neutral[:5],
           'CONFIRM_NEUTRAL': [t for t in neutral if t in positive][:5],
           'INDUSTRY_MOMENTUM': C.sleeve_book('S1_INDUSTRY_MOMENTUM', g)[1],
           'FOUR_FACTOR': C.sleeve_book('S3_FOUR_FACTOR', g)[1]}
    info = {'quality': int(eligible.sum()), 'valueMeasured': int((eligible & g[VALUE].notna()).sum()),
            'complete': int(complete.sum()), 'confirmedComplete': len(positive),
            'businessUnmeasured': int((eligible & g[VALUE].notna() & ~g[BUSINESS].notna().all(axis=1)).sum())}
    return out, original, info


def build(I, ctx, base, out):
    dates = base['dates']
    books = {k: {} for k in [ETF, *GRID]}
    matched = {selector: {} for selector in SELECTORS}
    audits, exposures, signal_audit = [], [], []
    counts = {}
    ordered = {}
    for date in dates:
        g = ctx.by[date].sort_values('ticker').copy()
        gi = g.set_index('ticker')
        names, original, info = selectors(g, date)
        assert original == base['s2'][date]
        ordered[date] = names
        signal_audit.append({'date': date, **info})
        books[ETF][date] = {M.ETF: 1.0}
        topcap = set(g.nlargest(5, '_mcap').ticker)
        for key, cfg in GRID.items():
            picked = names[cfg['selector']][:cfg['k']]
            weights = make_book(picked, cfg['style'])
            books[key][date] = weights
            counts[(key, date)] = len(picked)
            industry = Counter()
            for ticker, weight in weights.items():
                if ticker != M.ETF:
                    industry[str(gi.at[ticker, 'industry'])] += weight
            exposures.append({'date': date, 'id': key, 'requested': cfg['k'], 'actual': len(picked),
                              'shortfall': len(picked) < cfg['k'], 'etfWeight': weights.get(M.ETF, 0.),
                              'stockWeight': sum(w for t, w in weights.items() if t != M.ETF),
                              'namedTwoWeight': sum(weights.get(t, 0.) for t in TWO),
                              'capTop5DirectWeight': sum(weights.get(t, 0.) for t in topcap),
                              'industryWeights': json.dumps(industry, ensure_ascii=False),
                              'tickersRankOrder': '|'.join(picked)})
        pool = gi.loc[gi['_q'] & ~gi.index.isin(C.WITHHELD)]
        for selector in SELECTORS:
            key = f'KR:{selector}:FIXED20:K5'
            peer, audit = common().match_book(pool, books[key][date], M.ETF, order=names[selector])
            matched[selector][date] = peer
            audits.extend({'date': date, 'selector': selector, 'id': key, **leg} for leg in audit)
    anchors, state, anchor_meta = KS.build(I, ctx, base)
    for name in ('K2', 'MIX_PRE', 'MIX_EXP'):
        books[f'KR:{name}'] = anchors[name]
    pd.DataFrame(audits).to_csv(out / 'matching-audit.csv.gz', index=False)
    pd.DataFrame(exposures).to_csv(out / 'exposures.csv.gz', index=False)
    pd.DataFrame(signal_audit).to_csv(out / 'signal-pool-audit.csv', index=False)
    bookfile = {key: {str(d.date()): w for d, w in by.items()} for key, by in books.items()}
    bookfile['MATCHED'] = {s: {str(d.date()): w for d, w in by.items()} for s, by in matched.items()}
    with gzip.open(out / 'books.json.gz', 'wt') as f:
        json.dump(clean(bookfile), f, ensure_ascii=False, allow_nan=False)
    return books, matched, counts, ordered, anchor_meta, state


def asset_payoff(closes, px, ticker, entry, exit_):
    """Frozen fixed-cohort payoff; interior gaps carry, unresolved termination abstains.

    Include pre-entry wealth 1 in MDD. Purchase cost is a debit of entry capital;
    sale cost is charged only at the final mark, exactly as L.asset_return.
    """
    pe, pe_exit = closes.at[entry, ticker], closes.at[exit_, ticker]
    if not np.isfinite(pe) or not np.isfinite(pe_exit) or pe <= 0:
        return None, 'ENTRY_OR_EXIT_PRICE_MISSING'
    start, stop = px.pos[entry], px.pos[exit_]
    if ticker in px.terminal and px.terminal[ticker] < stop:
        return None, 'UNRESOLVED_TERMINAL_BASIS'
    marks = px.etf[start:stop+1] if ticker == M.ETF else px.carry[start:stop+1, px.col[ticker]]
    if not np.isfinite(marks).all():
        return None, 'INTERIOR_PRICE_UNRESOLVED'
    gross_path = marks / pe
    buy = C.cost_rate(ticker, 'buy', entry)
    sell = C.cost_rate(ticker, 'sell', exit_)
    cost = buy + gross_path[-1] * sell
    wealth = gross_path - buy
    wealth[-1] -= gross_path[-1] * sell
    gross = float(gross_path[-1] - 1)
    assert abs(float(wealth[-1] - 1) - (gross - cost)) < 1e-12
    return {'gross': gross, 'net': float(gross - cost), 'cost': float(cost), 'wealth': wealth}, None


def portfolio_payoff(weights, assets):
    if weights is None or any(assets.get(t) is None for t, w in weights.items() if w > 0):
        return None
    active = [(t, w) for t, w in weights.items() if w > 0]
    gross, net, cost = (sum(w * assets[t][field] for t, w in active)
                        for field in ('gross', 'net', 'cost'))
    path = np.r_[1., sum(w * assets[t]['wealth'] for t, w in active)]
    mdd = float(np.min(path / np.maximum.accumulate(path) - 1.))
    return {'gross': gross, 'net': net, 'cost': cost, 'mdd': mdd}


def compute_cohorts(I, ctx, base, books, matched, ordered, state, out):
    sessions, closes = I['sessions'], I['closes']
    end = closes[M.ETF].last_valid_index()
    leadership = KD.leadership(I, ctx, base)
    dump(out / 'leadership.json', leadership)
    frames, mdds, peerframes, attrframes = {}, {}, {}, {}
    failures, assetrows = [], []
    for horizon in (126, 252):
        rows, drawdowns, peers, attrs = [], [], [], []
        for date in base['dates']:
            entry = M.next_session(sessions, date)
            exit_pos = sessions.get_loc(entry) + horizon
            mature = exit_pos < len(sessions) and sessions[exit_pos] <= end
            exit_ = sessions[exit_pos] if exit_pos < len(sessions) else pd.NaT
            row = {'date': date, 'entry': entry, 'exit': exit_, 'mature': mature,
                   'gateDefined': state[date]['capMinusEqual126'] is not None}
            md = {'date': date, 'entry': entry, 'exit': exit_, 'mature': mature}
            pr = {'date': date, 'entry': entry, 'exit': exit_, 'mature': mature}
            if not mature:
                rows.append(row); drawdowns.append(md); peers.append(pr)
                failures.append({'date': date, 'horizon': horizon, 'id': '*', 'reason': 'NOT_MATURED'})
                continue
            labels = [KD.month_of(leadership, pd.Timestamp(p.end_time.date()))
                      for p in pd.period_range(entry, exit_, freq='M')]
            row.update(touchesSemiLed='SEMI_LED' in labels,
                       leadershipUnknown=any(label is None for label in labels))
            needed = {M.ETF}
            for by in books.values():
                needed.update(t for t, w in by[date].items() if w > 0)
            for by in matched.values():
                needed.update((by[date] or {}).keys())
            assets = {}
            for ticker in sorted(needed):
                payoff, reason = asset_payoff(closes, ctx.px, ticker, entry, exit_)
                assets[ticker] = payoff
                assetrows.append({'date': date, 'entry': entry, 'exit': exit_, 'horizon': horizon,
                                  'ticker': ticker, 'status': reason or 'MEASURED',
                                  **({field: payoff[field] for field in ('gross', 'net', 'cost')} if payoff else {})})
            gi = ctx.by[date].set_index('ticker')
            for key, by in books.items():
                weights = by[date]
                payoff = portfolio_payoff(weights, assets)
                if payoff is None:
                    bad = [t for t, w in weights.items() if w > 0 and assets[t] is None]
                    failures.append({'date': date, 'horizon': horizon, 'id': key,
                                     'reason': 'UNRESOLVED_HELD_PRICE', 'tickers': '|'.join(bad)})
                    continue
                for field in ('gross', 'net', 'cost'):
                    row[f'{key}_{field}'] = payoff[field]
                row[f'{key}_excess'] = payoff['net'] - assets[M.ETF]['net']
                md[key] = payoff['mdd']
                for ticker, weight in weights.items():
                    if ticker == M.ETF or weight <= 0:
                        continue
                    attrs.append({'date': date, 'entryYear': entry.year, 'id': key, 'ticker': ticker,
                                  'weight': weight, 'industry': str(gi.at[ticker, 'industry']),
                                  'grossContribution': weight * (assets[ticker]['gross'] - assets[M.ETF]['gross']),
                                  'netContribution': weight * (assets[ticker]['net'] - assets[M.ETF]['net']),
                                  'namedTwo': ticker in TWO})
                contribution = sum(weight * (assets[ticker]['net'] - assets[M.ETF]['net'])
                                   for ticker, weight in weights.items() if ticker != M.ETF)
                assert abs(contribution - row[f'{key}_excess']) < 1e-12
            for selector in SELECTORS:
                key = f'KR:{selector}:FIXED20:K5'
                payoff = portfolio_payoff(matched[selector][date], assets)
                n = len(ordered[date][selector])
                pr[f'{selector}_actual'] = n
                pr[f'{selector}_matchComplete'] = matched[selector][date] is not None
                if payoff is not None and n > 0 and f'{key}_net' in row:
                    pr[f'{selector}_peerNet'] = payoff['net']
                    pr[f'{selector}_selection'] = row[f'{key}_net'] - payoff['net']
                    pr[f'{selector}_replacement'] = payoff['net'] - assets[M.ETF]['net']
                    assert abs(pr[f'{selector}_selection'] + pr[f'{selector}_replacement'] - row[f'{key}_excess']) < 1e-12
            rows.append(row); drawdowns.append(md); peers.append(pr)
        frame, mdd, peer = (pd.DataFrame(values).set_index('date') for values in (rows, drawdowns, peers))
        for key in books:
            for field in ('net', 'excess', 'gross', 'cost'):
                if f'{key}_{field}' not in frame:
                    frame[f'{key}_{field}'] = np.nan
            if key not in mdd:
                mdd[key] = np.nan
        for selector in SELECTORS:
            for field in ('selection', 'replacement', 'peerNet'):
                if f'{selector}_{field}' not in peer:
                    peer[f'{selector}_{field}'] = np.nan
        frame.to_csv(out / f'cohorts-{horizon}.csv.gz', index_label='date', float_format='%.12g')
        mdd.to_csv(out / f'cohort-mdd-{horizon}.csv.gz', index_label='date', float_format='%.12g')
        peer.to_csv(out / f'matched-{horizon}.csv', index_label='date', float_format='%.12g')
        at = pd.DataFrame(attrs)
        at.to_csv(out / f'pername-cohort-{horizon}.csv.gz', index=False, float_format='%.12g')
        frames[horizon], mdds[horizon], peerframes[horizon], attrframes[horizon] = frame, mdd, peer, at
        print('KR fixed asset preparation', horizon, 'mature', int(frame.mature.sum()), flush=True)
    pd.DataFrame(failures).to_csv(out / 'failures.csv.gz', index=False)
    pd.DataFrame(assetrows).to_csv(out / 'asset-payoffs.csv.gz', index=False, float_format='%.12g')
    return frames, mdds, peerframes, attrframes


def source_checks(frames, out):
    checks = {}
    for horizon, frame in frames.items():
        old = pd.read_csv(OLD / f'cohorts-{horizon}.csv', parse_dates=['date']).set_index('date')
        errors = {}
        for k in range(6):
            key = f'KR:S2:SLOT20:K{k}' if k else ETF
            now = frame[f'{key}_net'].reindex(old.index)
            assert now.notna().equals(old[f'N{k}_net'].notna())
            delta = float((now - old[f'N{k}_net']).abs().max())
            assert delta < 1e-10, (horizon, k, delta)
            errors[str(k)] = delta
        frozen = json.loads((ROOT / 'research/followup_round8_v1/results/kr-switch-fixed.json').read_text())['fixed']
        anchor_errors = {}
        for anchor in ('K2', 'MIX_PRE', 'MIX_EXP'):
            key = f'KR:{anchor}'
            expected = frozen[str(horizon)]['ORIGINAL']['vsETF'][anchor]['mean']
            actual = float(frame[f'{key}_excess'].mean())
            assert abs(actual - expected) < 1e-10, (horizon, anchor, actual, expected)
            anchor_errors[anchor] = actual - expected
            expected_gate = frozen[str(horizon)]['GATE_DEFINED']['vsETF'][anchor]['mean']
            actual_gate = float(frame.loc[frame.gateDefined.astype(bool), f'{key}_excess'].mean())
            assert abs(actual_gate - expected_gate) < 1e-10, (horizon, anchor, actual_gate, expected_gate)
            anchor_errors[f'{anchor}_GATE_DEFINED'] = actual_gate - expected_gate
        checks[str(horizon)] = {'S2SlotMaxAbsoluteNetError': errors, 'anchorMeanError': anchor_errors}
    dump(out / 'source-reproduction-fixed.json', checks)
    return checks


def add_policies(base, frames, mdds, books, attrs, out):
    frame = frames[126]
    excess = pd.DataFrame({key: frame[f'{key}_excess'] for key in GRID})
    policies = {}
    for name, allowed in [('WF_S2_LCB', [k for k, v in GRID.items() if v['selector'] == 'S2']),
                          ('WF_ALL_LCB', list(GRID))]:
        key = f'KR:{name}'
        result = common().choose_policy(excess, mdds[126][list(GRID)], mdds[126][ETF],
                                        frame.exit, base['dates'], GRID, allowed)
        choice = result['choices'].reindex(base['dates'])
        books[key] = {date: books[ETF if choice.at[date] == 'ETF' else choice.at[date]][date]
                      for date in base['dates']}
        result['trace'].to_csv(out / f'policy-trace-{name}.csv', index=False)
        dump(out / f'policy-fits-{name}.json', result['fits'])
        policies[key] = result
        for horizon, df in frames.items():
            for field in ('net', 'excess', 'cost', 'gross'):
                df[f'{key}_{field}'] = [df.at[date, f'{ETF if choice.at[date] == "ETF" else choice.at[date]}_{field}'] for date in df.index]
            mdds[horizon][key] = [mdds[horizon].at[date, ETF if choice.at[date] == 'ETF' else choice.at[date]] for date in df.index]
            attribution = attrs[horizon]
            selected = attribution.loc[
                attribution.apply(lambda row: row['id'] == choice.at[row['date']], axis=1)].copy()
            selected['id'] = key
            attrs[horizon] = pd.concat([attribution, selected], ignore_index=True)
    for horizon, df in frames.items():
        df.to_csv(out / f'cohorts-{horizon}.csv.gz', index_label='date', float_format='%.12g')
        mdds[horizon].to_csv(out / f'cohort-mdd-{horizon}.csv.gz', index_label='date', float_format='%.12g')
        attrs[horizon].to_csv(out / f'pername-cohort-{horizon}.csv.gz', index=False, float_format='%.12g')
    with gzip.open(out / 'policy-books.json.gz', 'wt') as f:
        json.dump({k: {str(d.date()): w for d, w in books[k].items()} for k in policies}, f)
    return policies


def finish_book_artifacts(ctx, books, policies, out):
    """Preserve the complete executed list, including anchors and ETF warmup."""
    with gzip.open(out / 'books.json.gz', 'wt') as f:
        json.dump({k: {str(d.date()): w for d, w in by.items()} for k, by in books.items()}, f)
    audit = pd.read_csv(out / 'matching-audit.csv.gz', parse_dates=['date'])
    grouped = {(s, d): g for (s, d), g in audit.groupby(['selector', 'date'])}
    peers = {}
    for selector in SELECTORS:
        peers[selector] = {}
        for date, weights in books[f'KR:{selector}:FIXED20:K5'].items():
            legs = grouped.get((selector, date))
            if legs is not None and not legs.reason.eq('MATCHED').all():
                peers[selector][str(date.date())] = None
            else:
                matched = {M.ETF: weights[M.ETF]} if M.ETF in weights else {}
                if legs is not None:
                    matched.update(dict(zip(legs.peer, legs.weight, strict=True)))
                peers[selector][str(date.date())] = matched
    with gzip.open(out / 'matched-books.json.gz', 'wt') as f:
        json.dump(peers, f)
    original = pd.read_csv(out / 'exposures.csv.gz')
    original = original.loc[original.id.isin(GRID)]
    added = []
    for key, by in books.items():
        if key in GRID:
            continue
        for date, weights in by.items():
            gi = ctx.by[date].set_index('ticker')
            topcap = set(gi.nlargest(5, '_mcap').index)
            stocks = {t: w for t, w in weights.items() if t != M.ETF and w > 0}
            industry = Counter()
            for ticker, weight in stocks.items():
                industry[str(gi.at[ticker, 'industry'])] += weight
            added.append({'date': date, 'id': key, 'actual': len(stocks),
                          'etfWeight': weights.get(M.ETF, 0.), 'stockWeight': sum(stocks.values()),
                          'namedTwoWeight': sum(stocks.get(t, 0.) for t in TWO),
                          'capTop5DirectWeight': sum(stocks.get(t, 0.) for t in topcap),
                          'industryWeights': json.dumps(industry, ensure_ascii=False),
                          'tickersRankOrder': '|'.join(stocks),
                          'chosenConfig': policies[key]['choices'].at[date] if key in policies else None})
    pd.concat([original, pd.DataFrame(added)], ignore_index=True).to_csv(out / 'exposures.csv.gz', index=False)


def summarize(frames, peerframes, attrframes, books, policies, out):
    result = {'fixed': {}, 'selection': {}, 'sensitivity': {}, 'coreComparisons': {}, 'policies': {}}
    stat = common().stats
    starts = [policy_start(p) for p in policies.values()]
    post_start = max((d for d in starts if d is not None), default=None)
    matching_audit = pd.read_csv(out / 'matching-audit.csv.gz', parse_dates=['date'])
    for horizon, frame in frames.items():
        h = str(horizon)
        mask = frame[[f'{key}_net' for key in GRID]].notna().all(axis=1)
        matched = peerframes[horizon]
        matchedmask = matched[[f'{s}_selection' for s in SELECTORS]].notna().all(axis=1)
        result['fixed'][h], result['selection'][h], result['sensitivity'][h], result['coreComparisons'][h] = {}, {}, {}, {}
        for key in books:
            values = frame[f'{key}_excess']
            own_mask = frame.index >= post_start if key in policies and post_start is not None else None
            common_mask = mask & own_mask if own_mask is not None else mask
            if key in policies and post_start is None:
                own_mask = common_mask = np.zeros(len(frame), dtype=bool)
            result['fixed'][h][key] = {'own': stat(values, horizon, own_mask), 'common': stat(values, horizon, common_mask),
                                      'fullIncludingWarmup': stat(values, horizon) if key in policies else None,
                                      'matureMissingHeldPriceCount': int((frame.mature.astype(bool) & values.isna()).sum()),
                                      'commonDates': int(common_mask.sum())}
        for selector in SELECTORS:
            values = matched[f'{selector}_selection']
            complete = matched[f'{selector}_matchComplete'].astype('boolean').fillna(False).astype(bool)
            actual = matched[f'{selector}_actual'].fillna(0)
            mature = frame.mature.astype(bool)
            denom = mature & actual.gt(0)
            audit = matching_audit.loc[(matching_audit.selector == selector) & matching_audit.date.isin(frame.index[mature])]
            matched_legs = audit.reason.eq('MATCHED')
            weighted_coverage = float(audit.loc[matched_legs, 'weight'].sum() / audit.weight.sum()) if audit.weight.sum() > 0 else None
            result['selection'][h][selector] = {'own': stat(values, horizon),
                                                'common': stat(values, horizon, matchedmask),
                                                'replacementOwn': stat(matched[f'{selector}_replacement'], horizon),
                                                'replacementCommon': stat(matched[f'{selector}_replacement'], horizon, matchedmask),
                                                'coverage': {'matureNonempty': int(denom.sum()),
                                                             'matchingComplete': int((denom & complete).sum()),
                                                             'matchedPriceResolved': int(values.notna().sum()),
                                                             'legReasonCounts': audit.reason.value_counts().to_dict(),
                                                             'weightedLegCoverage': weighted_coverage,
                                                             'meanMatchedLogCapDistance': float(audit.loc[matched_legs, 'logCapDistance'].mean()),
                                                             'maxMatchedLogCapDistance': float(audit.loc[matched_legs, 'logCapDistance'].max()),
                                                             'matchSuccessRate': float((denom & complete).sum()/denom.sum()) if denom.any() else None}}
        at = attrframes[horizon]
        for key in books:
            values = frame[f'{key}_excess']
            selected = at[at.id == key] if not at.empty else at
            pername = selected.groupby('ticker').netContribution.sum().sort_values(ascending=False)
            peryear = selected.groupby('entryYear').netContribution.sum().sort_values(ascending=False)
            maximum_name = str(pername.index[0]) if len(pername) else None
            maximum_year = int(peryear.index[0]) if len(peryear) else None
            named = selected[selected.namedTwo].groupby('date').netContribution.sum().reindex(frame.index, fill_value=0.)
            maxname = selected[selected.ticker == maximum_name].groupby('date').netContribution.sum().reindex(frame.index, fill_value=0.)
            direct_dates = set(selected.loc[selected.namedTwo, 'date'])
            sens = {'exNamedTwoWeightToETF': stat(values - named, horizon),
                    'excludeNamedTwoCohorts': stat(values, horizon, ~frame.index.isin(direct_dates)),
                    'maxContributorTickerPostHoc': maximum_name,
                    'exMaxContributorWeightToETFPostHoc': stat(values - maxname, horizon),
                    'maxEntryYearPostHoc': maximum_year,
                    'excludeMaxEntryYearPostHoc': stat(values, horizon, frame.entry.dt.year.ne(maximum_year)),
                    'to2021': stat(values, horizon, frame.index < '2022-01-01'),
                    'from2022': stat(values, horizon, frame.index >= '2022-01-01'),
                    'touchesSemiLedPostHoc': stat(values, horizon, frame.touchesSemiLed.astype('boolean').fillna(False)),
                    'exSemiLedKnownPostHoc': stat(values, horizon, ~frame.touchesSemiLed.astype('boolean').fillna(False) & ~frame.leadershipUnknown.astype('boolean').fillna(True)),
                    'totalContributionSum': float(values.sum()), 'namedTwoContributionSum': float(named[values.notna()].sum()),
                    'namedTwoShareOfSignedTotal': float(named[values.notna()].sum()/values.sum()) if abs(values.sum()) > 1e-12 else None}
            sens['basis'] = 'OWN_PRICE_RESOLVED; post-hoc maximum ticker/year identified on own sample'
            sens['baseOwn'] = stat(values, horizon)
            sens['baseCommon'] = stat(values, horizon, mask)
            sens['common'] = {
                'exNamedTwoWeightToETF': stat(values - named, horizon, mask),
                'excludeNamedTwoCohorts': stat(values, horizon, mask & ~frame.index.isin(direct_dates)),
                'exMaxContributorWeightToETFPostHoc': stat(values - maxname, horizon, mask),
                'excludeMaxEntryYearPostHoc': stat(values, horizon, mask & frame.entry.dt.year.ne(maximum_year)),
                'to2021': stat(values, horizon, mask & (frame.index < '2022-01-01')),
                'from2022': stat(values, horizon, mask & (frame.index >= '2022-01-01'))}
            result['sensitivity'][h][key] = sens
        pername_rows = at.groupby(['id', 'ticker'], as_index=False).agg(netContributionSum=('netContribution', 'sum'),
                                                                    grossContributionSum=('grossContribution', 'sum'),
                                                                    heldCohorts=('date', 'nunique'))
        peryear_rows = at.groupby(['id', 'entryYear'], as_index=False).agg(netContributionSum=('netContribution', 'sum'),
                                                                       grossContributionSum=('grossContribution', 'sum'),
                                                                       heldCohorts=('date', 'nunique'))
        pername_rows.to_csv(out / f'pername-contribution-{horizon}.csv', index=False)
        peryear_rows.to_csv(out / f'entryyear-contribution-{horizon}.csv', index=False)
        for claim in REG['coreClaims']:
            if claim['market'] != 'KR':
                continue
            a, b = claim['a'], claim['b']
            if claim['kind'] == 'selection':
                cell = stat(matched[f"{claim['selector']}_selection"], horizon, matchedmask)
                cell['own'] = stat(matched[f"{claim['selector']}_selection"], horizon)
            else:
                values = frame[f'{a}_excess'] if b == 'ETF' else frame[f'{a}_net'] - frame[f'{b}_net']
                cmask = mask.copy()
                if claim['kind'] == 'factor':
                    for key in (a, b):
                        cmask &= pd.Series({date: len([t for t, w in book.items() if t != M.ETF and w > 0]) == 5
                                            for date, book in books[key].items()}).reindex(frame.index)
                if claim['kind'] == 'policy':
                    cmask &= frame.index >= post_start if post_start is not None else False
                cell = stat(values, horizon, cmask)
            result['coreComparisons'][h][claim['id']] = cell
        for key, policy in policies.items():
            first = post_start
            p_mask = mask & (frame.index >= first) if first is not None else mask & False
            result['policies'].setdefault(h, {})[key] = {
                'firstSufficientFit': first, 'vsETF': stat(frame[f'{key}_excess'], horizon, p_mask),
                'fixedSamePostFitDates': {k: stat(frame[f'{k}_excess'], horizon, p_mask) for k in GRID}}
    return result


def policy_start(policy):
    trace = policy['trace']
    # Shared API includes warmup; accept date as a column or the index.
    if 'sufficient' in trace:
        valid = trace.loc[trace.sufficient.astype(bool)]
        return pd.Timestamp(valid['date'].iloc[0] if 'date' in valid else valid.index[0]) if len(valid) else None
    fits = policy.get('fits', [])
    valid = [fit for fit in fits if fit.get('sufficient', False)]
    return min(pd.Timestamp(fit['fitDate']) for fit in valid) if valid else None


def book_signature(by):
    return hashlib.sha256(json.dumps({str(d): sorted(w.items()) for d, w in by.items()}, sort_keys=True).encode()).hexdigest()


def nav_diagnostic(px, schedules, start, end):
    """Use frozen recorded holdings for membership/reset and terminal receipts."""
    departed, held, resets, terminals = 0, 0, [], []
    for account, schedule in enumerate(schedules):
        record = C.simulate(px, schedule, start, end, record=True)
        terminals.extend({'account': account, 'date': d, 'ticker': t, 'valueLost': v}
                         for d, t, v in record['terminalHits'])
        previous_date, previous = start, {M.ETF: 1.}
        for row in record['holdings']:
            date, post = pd.Timestamp(row['date']), row['weights']
            oldnames = {t for t, w in previous.items() if t not in (M.ETF, M.CASH) and w > 1e-5}
            newnames = {t for t, w in post.items() if t not in (M.ETF, M.CASH) and w > 1e-5}
            held += len(oldnames)
            departed += len(oldnames - newnames)
            values = {t: w * px.price(t, px.pos[date]) / px.price(t, px.pos[previous_date])
                      for t, w in previous.items() if t != M.CASH}
            total = sum(values.values())
            resets.append(sum(abs(post[t] - values[t]/total) for t in set(values) & set(post)) if total else 0.)
            previous_date, previous = date, post
    return {'departedStockNames': departed, 'priorStockNameOccurrences': held,
            'nameReplacementShare': departed / held if held else None,
            'meanRetainedAssetL1ResetApprox': float(np.mean(resets)) if resets else None,
            'note': '6-decimal holdings; retained-asset resets are descriptive, not additive turnover attribution',
            'terminalEvents': terminals,
            'navBasisStatus': 'CONDITIONAL_UNRESOLVED_TERMINAL_ZERO' if terminals else 'NO_TERMINAL_ZERO_HIT_IN_FROZEN_ENGINE',
            'eligibleForRiskImprovementClaim': not terminals}


def ledgers(I, ctx, base, books, policies, out):
    sessions, dates = I['sessions'], base['dates']
    start = M.next_session(sessions, dates[0])
    end = I['closes'][M.ETF].last_valid_index()
    etf = pd.Series(ctx.px.etf, index=sessions)
    oldmetrics = json.loads((OLD / 'ledgers.json').read_text())['metrics']
    anchor_metrics = json.loads((ROOT / 'research/followup_round8_v1/results/kr-switch-ledgers.json').read_text())['ledgers']
    firstfits = [policy_start(p) for p in policies.values()]
    post_start = max((d for d in firstfits if d is not None), default=None)
    output, verification = {}, {}
    cache = out / 'ledger-cache'
    cache.mkdir(exist_ok=True)
    for every in (26, 52):
        navs, result = {}, {}
        oldnav = pd.read_csv(OLD / f'daily-nav-L{every}.csv', index_col='date', parse_dates=True)
        aliases = {}
        for key, by in books.items():
            stamp = book_signature(by)
            cachefile = cache / f'L{every}-{stamp}.pkl'
            if stamp in aliases:
                original = aliases[stamp]
                navs[key] = navs[original]
                result[key] = dict(result[original], identicalBookAliasOf=original)
                continue
            aliases[stamp] = key
            schedules = [A.books_to_schedule({d: by[d] for d in dates[i::every]}, sessions) for i in range(every)]
            before = time.time()
            if cachefile.exists():
                res = pickle.loads(cachefile.read_bytes())
            else:
                res = A.multi_account(ctx.px, schedules, start, end, I['rf'], etf, 1.)
                res['turnoverDiagnostic'] = nav_diagnostic(ctx.px, schedules, start, end)
                cachefile.write_bytes(pickle.dumps(res))
            nav = res['nav']
            full = common().nav_window(nav, etf)
            full.update(oneWayTurnoverPerYear=res['oneWayTurnoverPerYear'], costPerYear=res['costPerYear'],
                        turnoverDiagnostic=res['turnoverDiagnostic'])
            if key == ETF or (key.startswith('KR:S2:SLOT20:K')):
                k = int(key[-1]) if key != ETF else 0
                error = float((nav.reindex(oldnav.index) - oldnav[f'N{k}']).abs().max())
                assert error < 1e-9, (every, key, error)
                expected = oldmetrics[f'L{every}|N{k}']
                assert abs(full['cagr'] - expected['cagr']) < 1e-9
                verification[f'L{every}|{key}'] = {'dailyNavMaxError': error}
                nav = oldnav[f'N{k}']
            if key in ('KR:K2', 'KR:MIX_PRE', 'KR:MIX_EXP'):
                expected = anchor_metrics[f'L{every}|ORIGINAL|{key[3:]}']
                for field in ('cagr', 'mdd', 'oneWayTurnoverPerYear', 'costPerYear'):
                    assert abs(full[field] - expected[field]) < 1e-9, (every, key, field, full[field], expected[field])
                verification[f'L{every}|{key}'] = {'aggregateReproduced': True}
                gatedate = pd.Timestamp('2018-07-16')
                gate_window = common().nav_window(nav.loc[gatedate:], etf)
                gate_expected = anchor_metrics[f'L{every}|GATE_DEFINED|{key[3:]}']
                for field in ('cagr', 'mdd'):
                    assert abs(gate_window[field] - gate_expected[field]) < 1e-9
                verification[f'L{every}|{key}']['gateDefinedWindowReproduced'] = True
            navs[key] = nav
            post = common().nav_window(nav.loc[post_start:], etf) if post_start is not None else None
            if post is not None:
                post['windowNote'] = 'Existing accounts and holdings carried into common post-fit rebase; not fresh reset.'
            result[key] = {'full': full, 'postWarmup': post, 'postWarmupDate': post_start}
            print('KR ledger', every, key, f'{time.time()-before:.1f}s', flush=True)
            dump(out / f'ledgers-L{every}.json', result)
        pd.DataFrame(navs).to_csv(out / f'nav-L{every}.csv.gz', index_label='date', float_format='%.12g')
        output[f'L{every}'] = result
    dump(out / 'source-reproduction-ledgers.json', verification)
    return output


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--scratch', type=Path, required=True)
    ap.add_argument('--out', type=Path, default=HERE / 'results/KR')
    ap.add_argument('--stage', choices=('all', 'fixed', 'finalize-fixed', 'ledgers', 'summary'), default='all')
    args = ap.parse_args(argv)
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    work = args.scratch / 'kr-us-batch-v1-prepared.pkl'
    if args.stage in ('all', 'fixed', 'finalize-fixed'):
        I, ctx, base = RC.setup(str(args.scratch))
        prior = json.loads((OLD / 'inputs.json').read_text())
        assert I['ident']['identity'] == prior['identity']['identity']
        assert I['ident']['matrixDigest'] == prior['identity']['matrixDigest']
        if args.stage == 'finalize-fixed':
            with gzip.open(out / 'books.json.gz', 'rt') as f:
                saved = json.load(f)
            books = {key: {pd.Timestamp(d): w for d, w in by.items()}
                     for key, by in saved.items() if key != 'MATCHED' and key not in REG['policies']}
            counts = {(key, d): len([t for t, w in by.items() if t != M.ETF and w > 0])
                      for key, bydate in books.items() for d, by in bydate.items() if key in GRID}
            _, state, anchor_meta = KS.build(I, ctx, base)
            frames = {h: pd.read_csv(out / f'cohorts-{h}.csv.gz', parse_dates=['date', 'entry', 'exit']).set_index('date') for h in (126, 252)}
            mdds = {h: pd.read_csv(out / f'cohort-mdd-{h}.csv.gz', parse_dates=['date', 'entry', 'exit']).set_index('date') for h in (126, 252)}
            peers = {h: pd.read_csv(out / f'matched-{h}.csv', parse_dates=['date', 'entry', 'exit']).set_index('date') for h in (126, 252)}
            attrs = {h: pd.read_csv(out / f'pername-cohort-{h}.csv.gz', parse_dates=['date']) for h in (126, 252)}
            attrs = {h: values.loc[~values.id.isin(REG['policies'])].copy() for h, values in attrs.items()}
        else:
            books, matched, counts, ordered, anchor_meta, state = build(I, ctx, base, out)
            frames, mdds, peers, attrs = compute_cohorts(I, ctx, base, books, matched, ordered, state, out)
        reproduction = source_checks(frames, out)
        # Validate fixed-total versus slot algebra only on identical finite payoffs.
        max_scale_error = 0.
        for horizon, frame in frames.items():
            for selector in SELECTORS:
                for k in range(1, 6):
                    a, b = f'KR:{selector}:FIXED20:K{k}', f'KR:{selector}:SLOT20:K{k}'
                    actual = pd.Series({date: counts[(a, date)] for date in frame.index})
                    err = (frame[f'{a}_excess'] - frame[f'{b}_excess'] / actual.replace(0, 1)).abs().max()
                    max_scale_error = max(max_scale_error, float(err))
        assert max_scale_error < 1e-10
        policies = add_policies(base, frames, mdds, books, attrs, out)
        finish_book_artifacts(ctx, books, policies, out)
        work.write_bytes(pickle.dumps((I, ctx, base, books, frames, mdds, peers, attrs, policies, reproduction, anchor_meta)))
        summary = summarize(frames, peers, attrs, books, policies, out)
        summary.update(status='MEASURED_CONDITIONAL_CORPORATE_ACTION_BASIS', availability={'preparedSelectors': SELECTORS, 'missingInputs': []},
                       inputs={'identity': I['ident'], 'decisionCount': len(base['dates']),
                               'scratchFilesSha256': {p.name: sha(p) for p in args.scratch.glob('*.pkl') if not p.name.startswith('kr-us-batch')},
                               'sourceLimitations': ['Inherited Top120 proxy/PIT visibility limits',
                                                    'OCI successor valued and reinvested at relisting, not independently held thereafter',
                                                    'Frozen NAV engine terminal ZERO is conditional where unresolved terminal assets occur']},
                       sourceReproduction=reproduction, anchorMeta=anchor_meta, fixedTotalScaleMaxError=max_scale_error,
                       outputUnits='Returns/fractions (multiply by 100 for percent or percentage points).',
                       designCodeHashes={'DESIGN-ko.md': sha(HERE / 'DESIGN-ko.md'), 'registry.json': sha(HERE / 'registry.json'),
                                         'kr.py': sha(Path(__file__))})
        dump(out / 'summary.json', summary)
    else:
        I, ctx, base, books, frames, mdds, peers, attrs, policies, reproduction, anchor_meta = pickle.loads(work.read_bytes())
        summary = json.loads((out / 'summary.json').read_text())
        summary['sourceReproduction'] = source_checks(frames, out)
        finish_book_artifacts(ctx, books, policies, out)
    if args.stage in ('all', 'ledgers'):
        metrics = ledgers(I, ctx, base, books, policies, out)
        summary = json.loads((out / 'summary.json').read_text())
        summary['ledgers'] = metrics
        summary['designCodeHashes']['kr.py'] = sha(Path(__file__))
        dump(out / 'summary.json', summary)
    elif args.stage == 'summary':
        updated = summarize(frames, peers, attrs, books, policies, out)
        summary.update(updated)
        summary['designCodeHashes']['kr.py'] = sha(Path(__file__))
        dump(out / 'summary.json', summary)
    print('KR done', args.stage, flush=True)


if __name__ == '__main__':
    main()
