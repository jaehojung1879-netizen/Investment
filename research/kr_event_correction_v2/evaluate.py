"""Four fixed cells; called only behind run.py's exact-hash one-shot gate."""
from __future__ import annotations

from collections import Counter, defaultdict

import numpy as np

from research.corporate_event_outcome_v1 import contract as C, engine as E, engine_v2 as V, inference as I
from research.corporate_event_outcome_v1 import shareholder_inputs_v2 as S

CELLS = (('P2_DILUTION', 'H126'), ('P2_DILUTION', 'H252'),
         ('K7_DIVIDEND_INCREASE', 'H126'), ('K7_DIVIDEND_INCREASE', 'H252'))
CASH = ('ZERO', 'BOK_POLICY_RATE', 'BOK_POLICY_RATE_PLUS_100BP')


def metrics(returns):
    x = np.asarray(returns, float)
    nav = np.r_[1., np.cumprod(1 + x)]
    sd, down = x.std(ddof=1), np.sqrt(np.mean(np.minimum(x, 0) ** 2))
    return {'cagr': float(nav[-1] ** (252 / len(x)) - 1),
            'arithmeticAnnualized': float(252 * x.mean()),
            'sharpeZero': float(np.sqrt(252) * x.mean() / sd) if sd else None,
            'sortinoZero': float(np.sqrt(252) * x.mean() / down) if down else None,
            'mdd': float(np.min(nav / np.maximum.accumulate(nav) - 1)),
            'sessions': len(x)}


def assemble_stocks(price_rows, events, dividend_rows, admission, sessions, *, extra_tickers=()):
    """Caller already verified raw-file pins and source admission, after approval."""
    tickers = {e['ticker'] for e in events} | set(extra_tickers)
    rows = defaultdict(list)
    for row in price_rows:
        if row['ticker'] in tickers and sessions[0] <= row['date'] <= sessions[-1]:
            rows[row['ticker']].append(row)
    classes = {t: admission['securityIdentities'][t]['securityClass'] for t in tickers}
    decisions = [{**r, 'amendsReceipt': admission['amendmentLinks'].get(r['rcept_no'])}
                 for r in dividend_rows if r.get('stock_code', '') + '.KS' in tickers]
    stock_receipts = {r for t in tickers for a in admission['actionsByTicker'].get(t, [])
                      for r in a.get('stockDividendReceipts', []) if a.get('state') == 'VERIFIED'}
    divs, flags, blocked = S.issuer_cash_dividends(decisions, classes, cited_stock_receipts=stock_receipts)
    if blocked:
        raise S.SourceBlocked('DIVIDEND_INPUTS_BLOCKED:' + repr(blocked))
    levels, tradable, terminal, beta_levels = {}, {}, {}, {}
    for ticker in sorted(tickers):
        coverage = admission['coverageByTicker'].get(ticker, {})
        if not (coverage.get('dividendsComplete') and coverage.get('actionsComplete')
                and coverage.get('terminalEconomicsComplete') and coverage.get('sourceSha256')
                and coverage.get('through', '') >= sessions[-1]):
            raise S.SourceBlocked('SHAREHOLDER_COVERAGE_UNQUALIFIED:' + ticker)
        actions = [a for a in admission['actionsByTicker'].get(ticker, []) if a['date'] <= sessions[-1]]
        for action in actions:
            if action.get('terminalCashPerOldShare') is not None and not any(r['date'] == action['date'] for r in rows[ticker]):
                rows[ticker].append({'ticker': ticker, 'date': action['date'], 'close': None, 'volume': 0,
                                     'valuationBasis': 'CITED_CASH_SETTLEMENT_NOT_MARKET_PRICE'})
        lv, tr, settlements = S.cited_levels(rows[ticker], divs.get(ticker, {}), actions)
        levels[ticker], tradable[ticker] = lv, tr
        if len(settlements) > 1:
            raise S.SourceBlocked('MULTIPLE_TERMINAL_SETTLEMENTS:' + ticker)
        for day, record in settlements.items():
            terminal[ticker] = {**record, 'date': day}
        for event in (e for e in events if e['ticker'] == ticker):
            signal = event['signalSession']
            end = sessions.index(signal)
            window = sessions[max(0, end - 252):end + 1]
            relevant = {d: v for d, v in divs.get(ticker, {}).items() if window[0] < d <= signal}
            if any(v['knownOn'] >= signal for v in relevant.values()):
                raise S.SourceBlocked('BETA_DIVIDEND_NOT_PUBLIC_BEFORE_SIGNAL:' + event['rcept_no'])
            actions_then = [a for a in actions if window[0] < a['date'] <= signal]
            bars = [r for r in rows[ticker] if window[0] <= r['date'] <= signal]
            beta_levels[event['rcept_no']] = S.cited_levels(bars, relevant, actions_then, known_before=signal)[0]
    return {'levels': levels, 'tradable': tradable, 'terminal': terminal,
            'betaLevels': beta_levels, 'dividendFlags': flags}


def evaluate_cell(hypothesis, horizon, events, market):
    h, sessions, states = C.HORIZONS[horizon], market['sessions'], Counter()
    index = {d: i for i, d in enumerate(sessions)}
    slots = []
    for event in events:
        if event['hypothesis'] != hypothesis or not event['independent'][horizon]:
            continue
        entry, ticker = index[event['entrySession']], event['ticker']
        if entry + h >= len(sessions):
            states['NOT_MATURED'] += 1
            continue
        if event['entrySession'] not in market['tradable'].get(ticker, ()):
            states['ENTRY_NOT_TRADABLE'] += 1
            continue
        beta = E.estimate_beta(market['betaLevels'][event['rcept_no']], market['etf'], sessions, event['signalSession'])
        if beta['reason']:
            states[beta['reason']] += 1
            continue
        # Missing economics blocks the paired cell; never survivor-only deletion.
        for day in sessions[entry:entry + h + 1]:
            term = market['terminal'].get(ticker)
            if day not in market['levels'].get(ticker, {}) and not (term and term['date'] <= day):
                return {'status': 'SOURCE_BLOCKED', 'reason': 'HOLDING_ECONOMICS_UNRESOLVED',
                        'ticker': ticker, 'day': day, 'states': dict(states)}
        slots.append(E.Slot(event['rcept_no'], ticker, event['corp_code'], entry, entry + h,
                            beta['beta'], 1 / max(1, beta['beta']), event['entrySession']))
    if not slots:
        return {'status': 'SOURCE_BLOCKED', 'reason': 'NO_ADMITTED_SLOTS', 'states': dict(states)}
    paths, summary = {}, {}
    for cash in CASH:
        for cost in (0., 1., 2., 3.):
            path = V.simulate(slots, sessions, market['levels'], market['etf'], market['cash'][cash],
                              market['tradable'], market['terminal'], mult=cost)
            if not path['complete']:
                return {'status': 'SOURCE_BLOCKED', 'failure': path['failure'], 'states': dict(states)}
            paths[f'{cash}:{cost:g}x'] = path
    primary = paths['BOK_POLICY_RATE:1x']
    t, block = len(primary['D']), C.BOOTSTRAP['block'][horizon]
    if any(p['dates'] != primary['dates'] for p in paths.values()):
        raise S.SourceBlocked('COST_OR_CASH_CALENDARS_DIVERGED')
    columns = {k: np.array(p['D']) for k, p in paths.items()}
    bootstrap = I.synchronized_bootstrap(columns, block)
    for key, path in paths.items():
        x = columns[key]
        mean = float(x.mean())
        ci = I.basic_interval(mean, bootstrap[key], .95)
        simultaneous = I.basic_interval(mean, bootstrap[key], 1 - .05 / 3)
        hac = I.hac_se(x, h - 1)
        summary[key] = {'selectionDelta': h * mean, 'ci95': [h * v for v in ci],
                         'ciSimultaneous9833': [h * v for v in simultaneous],
                         'hacSe': h * hac if hac else None,
                         'pDescriptive': I.bootstrap_p(mean, bootstrap[key]),
                         'book': metrics(path['book']), 'etf': metrics(path['etf']),
                         'simpleEtfExcess': h * float(np.mean(np.array(path['book']) - path['etf'])),
                         'exposureTerm': h * float(np.mean(np.array(path['control']) - path['etf'])),
                         'turnover': path['turnover'], 'resumedExits': path['resumedExits']}
    years = defaultdict(float)
    for day, value in zip(primary['dates'], primary['D']):
        years[day[:4]] += value
    return {'status': 'EXPLORATORY_POST_OUTCOME_SOURCE_CORRECTION_NOT_CONFIRMATION',
            'hypothesis': hypothesis, 'horizon': horizon, 'slots': len(slots), 'states': dict(states),
            'effectiveBlocks': t / block, 'inferenceEligible': t / block >= 4,
            'summary': summary, 'selectionByCalendarYearSum': dict(years),
            'daily': {k: {'dates': p['dates'], 'book': p['book'], 'control': p['control'], 'D': p['D']}
                      for k, p in paths.items()},
            'promotionEligible': False,
            'limits': ['K7 and H252 remain descriptive; no new confirmatory family',
                       'P2 title decisions do not establish actual economic dilution',
                       'policy cash is a proxy; no real fills; pre-investor-tax']}


def evaluate_four_cells(events, market):
    return {f'{hypothesis}:{horizon}': evaluate_cell(hypothesis, horizon, events, market)
            for hypothesis, horizon in CELLS}


def compare_saved(four_cells, saved_postoutcome, saved_registered):
    out = {}
    for hypothesis, horizon in CELLS:
        key = f'{hypothesis}:{horizon}'
        old = saved_postoutcome['hypotheses'][hypothesis][horizon]
        new = four_cells[key]
        delta = new.get('summary', {}).get('BOK_POLICY_RATE:1x', {}).get('selectionDelta')
        previous = old['selectionDelta']['cost1x']
        out[key] = {'oldSavedDelta': previous, 'oldSavedCi95': old['ci95'], 'oldSlots': old['slots'],
                    'registeredOriginallyBlocked': saved_registered['hypotheses'][hypothesis][horizon].get('blocked'),
                    'correctedDelta': delta, 'correctedSlots': new.get('slots'),
                    'differenceOfResearchStatistics': delta - previous if delta is not None else None,
                    'portfolioBenefitMeasuredByThisDifference': False,
                    'evidenceClass': 'POST_OUTCOME_SOURCE_CORRECTION_NOT_CONFIRMATION'}
    return out
