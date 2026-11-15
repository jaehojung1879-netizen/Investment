"""Three requested long-only paths from saved targets/rankings, never rerun C2.

Next-eligible replacement inherits the removed capital slot, subject to the
SAVED security/sector/name caps; unused capital goes to the ETF. No feature,
score, ranking or risk estimate is reconstructed. Existing names are not forced
out merely because a filing arrives while held. This rule is fixed pre-run.
"""
from __future__ import annotations

import math

import numpy as np

from research.corporate_event_outcome_v1 import engine as E, inference as I
from research.corporate_event_outcome_v1.shareholder_inputs_v2 import SourceBlocked
from .evaluate import metrics


def asset(ticker):
    return E.ETF if ticker == '069500.KS' else ticker


def targets(decisions, events, sessions, mode, *, signal_calendar=None):
    if mode not in ('ORIGINAL', 'AVOID_NEXT', 'AVOID_ETF'):
        raise ValueError('UNKNOWN_PORTFOLIO_PATH')
    index, out, previous = {d: i for i, d in enumerate(signal_calendar or sessions)}, {}, set()
    for row in decisions:
        day = row['entrySession']
        if row['signalSession'] >= day or row['knownOn'] > row['signalSession']:
            raise SourceBlocked('SAVED_DECISION_NOT_PUBLIC_BEFORE_ENTRY')
        weights = {asset(k): float(v) for k, v in row['weights'].items()}
        if any(not math.isfinite(v) or v < 0 for v in weights.values()) or abs(sum(weights.values()) - 1) > 1e-9:
            raise SourceBlocked('SAVED_TARGET_NOT_LONG_ONLY_FULLY_FUNDED')
        if day in out or row['maxNames'] > 5:
            raise SourceBlocked('DECISION_SEQUENCE_OR_NAME_CAP_INVALID')
        if mode != 'ORIGINAL':
            candidates = row['rankedCandidates']
            if len({r['ticker'] for r in candidates}) != len(candidates):
                raise SourceBlocked('DUPLICATE_SAVED_CANDIDATE')
            sectors = {r['ticker']: r['sector'] for r in candidates}
            banned = {e['ticker'] for e in events if e['hypothesis'] == 'P2_DILUTION'
                      and e['entrySession'] in index and 0 <= index[day] - index[e['entrySession']] < 252}
            removed = [t for t, w in weights.items() if w > 0 and t not in (E.ETF, E.CASH)
                       and t not in previous and t in banned]
            for ticker in removed:
                capital = weights.pop(ticker)
                if mode == 'AVOID_NEXT':
                    for candidate in candidates:  # use saved order, no reranking
                        t = candidate['ticker']
                        if not candidate['eligible'] or t in banned or t in weights or asset(t) in (E.ETF, E.CASH):
                            continue
                        held = [k for k, w in weights.items() if w > 0 and k not in (E.ETF, E.CASH)]
                        if len(held) >= row['maxNames']:
                            break
                        sector = candidate['sector']
                        if any(k not in sectors for k in held):
                            raise SourceBlocked('SAVED_SECTOR_IDENTITY_MISSING')
                        sector_weight = sum(weights[k] for k in held if sectors[k] == sector)
                        room = min(capital, candidate['maxWeight'], row['maxSecurityWeight'],
                                   row['maxSectorWeight'] - sector_weight)
                        if room > 0:
                            weights[t] = room
                            capital -= room
                            break
                weights[E.ETF] = weights.get(E.ETF, 0) + capital
        previous = {t for t, w in weights.items() if w > 0 and t not in (E.ETF, E.CASH)}
        out[day] = weights
    return out


def run_targets(target_by_day, market, multiplier):
    """Same capital, dated fee function and daily marks for all three paths.

    Unavailable execution/economics blocks comparison; it is never assumed
    filled or reconstructed from an unexecuted target.
    """
    w, returns, costs = {E.ETF: 1.0}, [], []
    days = market['sessions']
    for i, day in enumerate(days):
        gross = 0.0
        if i:
            grown = {}
            for t, weight in w.items():
                terminal = market.get('terminal', {}).get(t)
                paid = terminal and terminal['date'] == day
                r = (terminal['multiple'] - 1 if paid else
                     E._ret(t, day, days[i - 1], market['levels'], market['etf'], market['cash']['ZERO'], {}))
                if r is None:
                    raise SourceBlocked('PORTFOLIO_PAYOFF_OR_TERMINAL_UNRESOLVED:' + t + ':' + day)
                gross += weight * r
                instrument = E.CASH if paid else t
                grown[instrument] = grown.get(instrument, 0) + weight * (1 + r)
            total = sum(grown.values())
            if total <= 0:
                raise SourceBlocked('PORTFOLIO_CAPITAL_EXHAUSTED_REQUIRES_SAVED_LIQUIDATION_RECORD')
            w = {t: v / total for t, v in grown.items()}
        cost = 0.0
        if day in target_by_day:
            target = target_by_day[day]
            for t in set(w) | set(target):
                if t not in (E.ETF, E.CASH) and abs(target.get(t, 0) - w.get(t, 0)) > 1e-12:
                    if day not in market['tradable'].get(t, ()):
                        raise SourceBlocked('PORTFOLIO_EXECUTION_NOT_AVAILABLE:' + t + ':' + day)
            w, cost, _ = E._rebalance(w, target, set(), day, multiplier)
        returns.append((1 + gross) * (1 - cost) - 1)
        costs.append(cost)
    return returns, costs


def compare(bundle, events, market, *, draws=None):
    """A mismatch to the stored original blocks B/C; no C2 regeneration fallback."""
    if bundle.get('status') != 'COMPLETE_FROZEN_C2_LEDGER' or bundle['calendar'] != market['sessions']:
        raise SourceBlocked('COMPLETE_ALIGNED_C2_LEDGER_MISSING')
    signal_calendar = market.get('signalCalendar', market['sessions'])
    first = signal_calendar.index(market['sessions'][0])
    if first < 252 or bundle.get('dilutionEventCoverageFrom', '9999') > signal_calendar[first - 252]:
        raise SourceBlocked('P2_LOOKBACK_BEFORE_PORTFOLIO_START_UNQUALIFIED')
    events = [*events, *bundle.get('priorP2Events', [])]
    if any(not e.get('sourceSha256') for e in bundle.get('priorP2Events', [])):
        raise SourceBlocked('PRIOR_P2_LOOKBACK_SOURCE_UNQUALIFIED')
    decisions = bundle['decisions']
    original_targets = targets(decisions, events, market['sessions'], 'ORIGINAL', signal_calendar=signal_calendar)
    original = {}
    for multiplier in (1, 2, 3):
        key = f'{multiplier}x'
        path, costs = run_targets(original_targets, market, multiplier)
        expected = bundle['expectedDailyByCost'][key]
        if len(path) != len(expected) or not np.allclose(path, expected, rtol=0, atol=1e-9):
            raise SourceBlocked('SAVED_C2_BASELINE_NOT_REPRODUCED:' + key)
        original[key] = {'daily': path, 'costs': costs, 'metrics': metrics(path)}
    result = {'ORIGINAL': original}
    for mode in ('AVOID_NEXT', 'AVOID_ETF'):
        result[mode] = {}
        ts = targets(decisions, events, market['sessions'], mode, signal_calendar=signal_calendar)
        for multiplier in (1, 2, 3):
            key = f'{multiplier}x'
            path, costs = run_targets(ts, market, multiplier)
            difference = np.array(path) - original[key]['daily']
            bootstrap = I.synchronized_bootstrap({'difference': difference}, 252, draws=draws)['difference']
            ci = I.basic_interval(float(difference.mean()), bootstrap, .95)
            result[mode][key] = {'daily': path, 'costs': costs, 'metrics': metrics(path),
                                 'annualArithmeticIncrement': float(252 * difference.mean()),
                                 'incrementCi95': [252 * float(v) for v in ci],
                                 'inferenceEligible': len(difference) / 252 >= 4}
    return {'status': 'EXPLORATORY_POST_OUTCOME_NOT_CONFIRMATION', 'paths': result,
            'replacementSizing': 'SAVED_CAPS_SLOT_CAPITAL_INHERITANCE_ETF_REMAINDER',
            'promotionEligible': False}
