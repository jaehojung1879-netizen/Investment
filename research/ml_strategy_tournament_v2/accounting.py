"""Float64 cash/share/receivable ledger. No adjusted price can enter this engine.

Fractional research quantities; no assumption of real exchange lot fills.
Sources can block an outcome but can never replace a frozen stock selection.
"""
from __future__ import annotations
from copy import deepcopy
import math

from research.ml_strategy_tournament_v1.tournament import stock_cost_bps, etf_cost_bps
from .vendor.shareholder_inputs import SourceBlocked

ETF = '069500.KS'


def fee_rate(ticker, date, delta):
    return (etf_cost_bps() if ticker == ETF else stock_cost_bps(date, 'buy' if delta > 0 else 'sell')) / 1e4


def check_event(e):
    if e.get('kind') == 'BLOCKED':
        raise SourceBlocked(e.get('reason', 'CORPORATE_ACTION_UNRESOLVED') + ':' + e['ticker'])
    if not e.get('sourceSha256') or not e.get('confirmedOn') or e.get('state') != 'VERIFIED':
        raise SourceBlocked('UNCITED_OR_UNVERIFIED_ACTION')
    if e['confirmedOn'] > e['date']:
        raise SourceBlocked('ACTION_CONFIRMED_AFTER_EFFECTIVE_DATE')
    if e['kind'] not in ('CASH_DIVIDEND', 'SPLIT', 'STOCK_DIVIDEND', 'TERMINAL_CASH', 'TERMINAL_EXCHANGE', 'BLOCKED'):
        raise SourceBlocked('UNKNOWN_ACTION_KIND')
    if e.get('paymentDate', e['date']) < e['date']:
        raise SourceBlocked('PAYMENT_BEFORE_EX_DATE')
    if e['kind'] == 'BLOCKED':
        raise SourceBlocked(e.get('reason', 'CORPORATE_ACTION_UNRESOLVED'))


def run(market, decisions, *, capital=100000000., require_complete=True):
    """Fixed dated target records -> raw-price, actually funded research account.

    No missing payoff is zero, no last-price terminal exit, no dividend reinvested
    before its payment, no halted share can be bought/sold/rescaled by fees.
    Unknown paths keep full dated NOT_EXECUTED records, with null outcome NAV.
    """
    days = market['sessions']
    if len(set(days)) != len(days) or days != sorted(days):
        raise ValueError('DUPLICATE_OR_UNSORTED_SESSIONS')
    if len({r['date'] for r in decisions}) != len(decisions):
        raise ValueError('DUPLICATE_DECISION_DATE')
    schedule = {r['date']: r for r in decisions}
    quotes, events = market['quotes'], market.get('events', {})
    for daily in quotes.values():
        for q in daily.values():
            if q.get('basis') != 'RAW_UNADJUSTED':
                raise SourceBlocked('ADJUSTED_PRICE_WITH_EXPLICIT_DISTRIBUTIONS_FORBIDDEN')
    first = quotes.get(days[0], {}).get(ETF)
    if not first or not first['close'] > 0:
        raise SourceBlocked('INITIAL_ETF_RAW_PRICE_MISSING')
    quantities = {ETF: capital / first['close']}
    cash, claims = 0., []
    account, assets, trades, orders, event_ledger, residuals = [], [], [], [], [], []
    blocked = None
    previous_nav, known = capital, {ETF}
    for day_index, day in enumerate(days):
        start_qty, start_cash = dict(quantities), cash
        start_claims = deepcopy(claims)
        start_trades, start_orders, start_events = len(trades), len(orders), len(event_ledger)
        current_event = None
        fees, taxes, dividend_recognized, cash_paid = 0., 0., 0., 0.
        target = schedule.get(day)
        selected = set(target.get('weights', {})) if target else set()
        known |= selected | set(quantities)
        try:
            if blocked:
                raise SourceBlocked('PREVIOUS_SOURCE_BLOCK:' + blocked['date'])
            if require_complete:
                for t in sorted(set(quantities) | selected):
                    coverage = market.get('admission', {}).get(t, {})
                    if coverage.get('status') != 'COMPLETE' or not coverage.get('from', '9999') <= day <= coverage.get('through', ''):
                        raise SourceBlocked('SHAREHOLDER_COMPLETENESS_NOT_ESTABLISHED:' + t)
            # Payments/stock deliveries can occur on non-trading days; the first
            # subsequent session is the first modeled spending opportunity.
            retained = []
            for claim in claims:
                if claim.get('paymentDate') and claim['paymentDate'] <= day:
                    if claim['kind'] == 'CASH':
                        cash += claim['amount']
                        cash_paid += claim['amount']
                    else:
                        t = claim['ticker']
                        quantities[t] = quantities.get(t, 0.) + claim['quantity']
                    event_ledger.append({'date': day, **claim, 'kind': 'RECEIVABLE_SETTLED'})
                else:
                    retained.append(claim)
            claims = retained
            opening_quantities = dict(quantities)
            kinds_seen = set()
            # Entitlements use holdings immediately before the ex-date session.
            for e in events.get(day, []):
                t = e['ticker']
                q = quantities.get(t, 0.)
                if q <= 0:
                    continue
                current_event = e
                check_event(e)
                kind = e['kind']
                if (t, kind) in kinds_seen:
                    raise SourceBlocked('DUPLICATE_SAME_KIND_CORPORATE_ACTION:' + t)
                kinds_seen.add((t, kind))
                if kind in ('CASH_DIVIDEND', 'STOCK_DIVIDEND'):
                    q = opening_quantities.get(t, 0.)
                if kind == 'CASH_DIVIDEND':
                    if e.get('amountBasis') != 'PRE_ACTION_SHARE':
                        raise SourceBlocked('DIVIDEND_SHARE_BASIS_UNRESOLVED:' + t)
                    if not e.get('paymentDate'):
                        raise SourceBlocked('DIVIDEND_PAYMENT_DATE_UNRESOLVED:' + t)
                    amount = q * float(e['dps'])
                    if not math.isfinite(amount) or amount < 0:
                        raise SourceBlocked('INVALID_DIVIDEND_AMOUNT:' + t)
                    claim = {'kind': 'CASH', 'ticker': t, 'amount': amount, 'quantity': 0.,
                             'paymentDate': e['paymentDate'], 'sourceSha256': e['sourceSha256']}
                    if e['paymentDate'] <= day:
                        cash += amount
                        cash_paid += amount
                    else:
                        claims.append(claim)
                    dividend_recognized += amount
                elif kind == 'SPLIT':
                    multiplier = float(e['shareMultiplier'])
                    if not math.isfinite(multiplier) or multiplier <= 0:
                        raise SourceBlocked('INVALID_SPLIT_RATIO')
                    quantities[t] *= multiplier
                elif kind == 'STOCK_DIVIDEND':
                    if not e.get('deliveryDate'):
                        raise SourceBlocked('STOCK_DIVIDEND_DELIVERY_UNRESOLVED:' + t)
                    new_q = q * float(e['sharesPerOldShare'])
                    if new_q < 0 or not math.isfinite(new_q):
                        raise SourceBlocked('INVALID_STOCK_DIVIDEND_RATIO')
                    claim = {'kind': 'SHARES', 'ticker': t, 'quantity': new_q, 'amount': 0.,
                             'paymentDate': e['deliveryDate'], 'sourceSha256': e['sourceSha256']}
                    if e['deliveryDate'] <= day:
                        quantities[t] += new_q
                    else:
                        claims.append(claim)
                elif kind in ('TERMINAL_CASH', 'TERMINAL_EXCHANGE'):
                    if not e.get('paymentDate'):
                        raise SourceBlocked('TERMINAL_SETTLEMENT_DATE_UNKNOWN:' + t)
                    if kind == 'TERMINAL_CASH' and (not math.isfinite(float(e['cashPerOldShare'])) or float(e['cashPerOldShare']) < 0):
                        raise SourceBlocked('TERMINAL_CASH_INVALID')
                    quantities.pop(t)
                    if kind == 'TERMINAL_CASH':
                        claims.append({'kind': 'CASH', 'ticker': t, 'amount': q * float(e['cashPerOldShare']),
                                       'quantity': 0., 'paymentDate': e['paymentDate'], 'sourceSha256': e['sourceSha256']})
                    else:
                        if not e.get('successor') or float(e['sharesPerOldShare']) <= 0:
                            raise SourceBlocked('TERMINAL_EXCHANGE_PACKAGE_UNKNOWN:' + t)
                        claims.append({'kind': 'SHARES', 'ticker': e['successor'],
                                       'quantity': q * float(e['sharesPerOldShare']), 'amount': 0.,
                                       'paymentDate': e['paymentDate'], 'sourceSha256': e['sourceSha256']})
                event_ledger.append({'date': day, 'heldQuantityBefore': q, **e})
            current_event = None
            still_pending = []
            for claim in claims:
                if claim.get('paymentDate') and claim['paymentDate'] <= day:
                    if claim['kind'] == 'CASH':
                        cash += claim['amount']
                        cash_paid += claim['amount']
                    else:
                        quantities[claim['ticker']] = quantities.get(claim['ticker'], 0.) + claim['quantity']
                    event_ledger.append({'date': day, **claim, 'kind': 'RECEIVABLE_SETTLED'})
                else:
                    still_pending.append(claim)
            claims = still_pending
            needed = set(quantities) | {x['ticker'] for x in claims if x['kind'] == 'SHARES'} | selected | {ETF}
            if require_complete:
                for t in sorted(needed):
                    coverage = market.get('admission', {}).get(t, {})
                    if coverage.get('status') != 'COMPLETE' or not coverage.get('from', '9999') <= day <= coverage.get('through', ''):
                        raise SourceBlocked('SUCCESSOR_OR_CLAIM_SOURCE_NOT_ADMITTED:' + t)
            marks = {}
            for t in sorted(needed):
                q = quotes.get(day, {}).get(t)
                if not q or not math.isfinite(q['close']) or q['close'] <= 0:
                    raise SourceBlocked('MISSING_RAW_PRICE_OR_TERMINAL_CONSIDERATION:' + t)
                marks[t] = q['close']
            if day_index:
                for t in sorted(quantities):
                    prior = quotes.get(days[day_index - 1], {}).get(t)
                    explained = any(e['ticker'] == t and e.get('state') == 'VERIFIED' for e in events.get(day, []))
                    if prior and prior['close'] > 0 and not explained:
                        jump = marks[t] / prior['close'] - 1
                        limit = .15 if day < '2015-06-15' else .30
                        if abs(jump) > limit + .001:
                            raise SourceBlocked('RAW_PRICE_JUMP_REQUIRES_CITED_ACTION:' + t)
            cash_claims = sum(x['amount'] for x in claims if x['kind'] == 'CASH')
            share_claims = {}
            for x in claims:
                if x['kind'] == 'SHARES':
                    share_claims[x['ticker']] = share_claims.get(x['ticker'], 0.) + x['quantity'] * marks[x['ticker']]
            current = {t: q * marks[t] for t, q in quantities.items()}
            gross = cash + sum(current.values()) + cash_claims + sum(share_claims.values())
            if target:
                weights = {t: float(w) for t, w in target['weights'].items()}
                if any(w < 0 or not math.isfinite(w) for w in weights.values()) or abs(sum(weights.values()) - 1) > 3e-6:
                    raise ValueError('SAVED_WEIGHTS_INVALID')
                total = sum(weights.values())
                weights = {t: w / total for t, w in weights.items()}
                def tradable(t):
                    return quotes[day][t].get('volume', 0) > 0
                locked = {t: value for t, value in current.items() if not tradable(t)}
                def allocate(net):
                    budget = max(0., net - cash_claims - sum(share_claims.values()) - sum(locked.values()))
                    want = {t: max(0., net * w - share_claims.get(t, 0.)) for t, w in weights.items()
                            if t != ETF and t not in locked and tradable(t)}
                    scale = min(1., budget / sum(want.values())) if sum(want.values()) > 0 else 1.
                    new = {**locked, **{t: v * scale for t, v in want.items()}}
                    if not tradable(ETF):
                        raise SourceBlocked('BENCHMARK_CANNOT_EXECUTE')
                    new[ETF] = max(0., budget - sum(want.values()) * scale)
                    return new
                net = gross
                for _ in range(50):
                    new = allocate(net)
                    charge = sum(abs(new.get(t, 0.) - current.get(t, 0.)) * fee_rate(t, day, new.get(t, 0.) - current.get(t, 0.))
                                 for t in sorted(set(new) | set(current)))
                    nxt = gross - charge
                    if abs(nxt - net) <= max(1e-9, gross * 1e-15):
                        net = nxt
                        break
                    net = nxt
                new = allocate(net)
                for t in sorted(set(current) | set(new) | selected):
                    delta = new.get(t, 0.) - current.get(t, 0.)
                    charge = abs(delta) * fee_rate(t, day, delta)
                    tax = abs(delta) * max(0., fee_rate(t, day, delta) - fee_rate(t, day, abs(delta))) if delta < 0 else 0.
                    fees += charge
                    taxes += tax
                    fill = delta / marks[t]
                    if abs(fill) > 1e-10:
                        assert tradable(t), 'HALTED_SHARE_CHANGED'
                        trades.append({'date': day, 'ticker': t, 'quantityDelta': fill, 'rawPrice': marks[t],
                                       'notional': delta, 'totalFeeIncludingTax': charge, 'sellTax': tax})
                    requested = weights.get(t, 0.) * net - current.get(t, 0.)
                    orders.append({'date': day, 'ticker': t, 'targetWeight': weights.get(t, 0.),
                                   'requestedNotional': requested, 'filledNotional': delta,
                                   'status': 'HALTED_DEFERRED_OR_SKIPPED' if not tradable(t) and abs(requested) > 1e-6 else
                                   ('PARTIAL_LOCKED_CAPITAL' if abs(requested - delta) > .01 and t != ETF else 'PROCESSED')})
                before = dict(quantities)
                quantities = {t: val / marks[t] for t, val in new.items() if val > 1e-9}
                for t in locked:
                    assert abs(quantities[t] - before[t]) < max(1e-10, abs(before[t]) * 1e-14)
                cash = gross - fees - sum(new.values()) - cash_claims - sum(share_claims.values())
                if abs(cash) < max(1e-6, gross * 1e-13):
                    cash = 0.
                if cash < -1e-6:
                    raise AssertionError('NEGATIVE_CASH')
            nav = cash + sum(q * marks[t] for t, q in quantities.items()) + cash_claims + sum(share_claims.values())
            residual = nav - (gross - fees)
            assert abs(residual) <= max(1e-6, capital * 1e-12), ('FUNDING_NOT_CONSERVED', day, residual)
            residuals.append(residual)
            account.append({'date': day, 'nav': nav, 'cash': cash, 'cashReceivable': cash_claims,
                            'stockReceivableValue': sum(share_claims.values()), 'dividendRecognized': dividend_recognized,
                            'cashPaid': cash_paid, 'totalCosts': fees, 'sellTax': taxes,
                            'preTradeValue': gross, 'markAndActionPnl': gross - previous_nav,
                            'fundingResidual': residual, 'status': 'VALUED'})
            for t in sorted(known | needed):
                p = marks.get(t) or quotes.get(day, {}).get(t, {}).get('close')
                q = quantities.get(t, 0.)
                assets.append({'date': day, 'ticker': t, 'quantityBeforeEvents': start_qty.get(t, 0.),
                               'quantity': q, 'rawClose': p, 'marketValue': q * p if p is not None else (0. if q == 0 else None),
                               'shareReceivableValue': share_claims.get(t, 0.),
                               'shareReceivableQuantity': sum(x['quantity'] for x in claims if x['kind'] == 'SHARES' and x['ticker'] == t),
                               'cashReceivableKrw': sum(x['amount'] for x in claims if x['kind'] == 'CASH' and x['ticker'] == t), 'status': 'VALUED',
                               'tradable': bool(quotes.get(day, {}).get(t, {}).get('volume', 0) > 0)})
            previous_nav = nav
        except SourceBlocked as exc:
            # No partly processed day is published as a funded execution.
            quantities, cash, claims = start_qty, start_cash, start_claims
            del trades[start_trades:]
            del orders[start_orders:]
            for partial in event_ledger[start_events:]:
                partial['status'] = 'UNCOMMITTED_SOURCE_BLOCKED_DAY'
            if blocked is None:
                event_ledger.append({'date': day, 'kind': 'SOURCE_BLOCKED', 'reason': str(exc),
                                     'unresolvedEvent': current_event})

                blocked = {'date': day, 'reason': str(exc), 'knownQuantityBefore': start_qty, 'knownCashBefore': start_cash}
            account.append({'date': day, 'nav': None, 'cash': None, 'cashReceivable': None,
                            'totalCosts': None, 'status': 'SOURCE_BLOCKED', 'reason': blocked['reason']})
            for t in sorted(known | selected):
                assets.append({'date': day, 'ticker': t, 'quantity': None, 'rawClose': quotes.get(day, {}).get(t, {}).get('close'),
                               'marketValue': None, 'status': 'SOURCE_BLOCKED', 'lastVerifiedQuantity': start_qty.get(t, 0.) if day == blocked['date'] else None})
            if target:
                for t, w in target['weights'].items():
                    orders.append({'date': day, 'ticker': t, 'recordedWeight': w, 'status': 'NOT_EXECUTED_SOURCE_BLOCKED'})
    return {'status': 'SOURCE_BLOCKED' if blocked else 'COMPLETE', 'blocked': blocked,
            'account': account, 'assets': assets, 'trades': trades, 'orders': orders,
            'events': event_ledger, 'maxAbsFundingResidualKrw': max(map(abs, residuals), default=0.),
            'completeSourceAdmissionRequired': require_complete, 'finalClaims': deepcopy(claims)}
