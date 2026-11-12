"""A1/B1 source-only plan and synthetic share/cash reconciliation.

No real outcome entry point exists. This is not the registered calendar-time
book, ex-ante beta comparator or inference engine. Their unsealed cash, tax,
execution and distribution policies remain Claude/Owner decisions.
"""
from datetime import date
import hashlib
import json
import math

from pipeline import prospective_receipt_core as core
from pipeline import replay_calendar as calendar

from .references import load


def require(condition, code):
    if not condition:
        raise ValueError(code)


def finite(value, *, positive=False):
    require(not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value) and (value > 0 if positive else value >= 0),
            'INVALID_ECONOMIC_NUMBER')
    return value


def prepare_event(spec_bytes, expected_spec_sha256, event, as_of_utc, policies):
    """No price values: retain incomplete observations and refuse missing policies."""
    require(hashlib.sha256(spec_bytes).hexdigest() == expected_spec_sha256, 'SPEC_BYTES_CHANGED')
    spec = json.loads(spec_bytes)
    require(spec.get('studyId') == 'kr-corporate-information-events-v1', 'WRONG_STUDY')
    require(event.get('hypothesis') in ('A1', 'B1') and event.get('rcept_no'), 'A1_B1_EVENT_REQUIRED')
    days = [d.strftime('%Y-%m-%d') for d in calendar.sessions(event['receiptDay'],
                                                              event['entrySession'], 'KR')]
    after = [d for d in days if d > event['receiptDay']]
    require(len(after) == 2 and after == [event['signalSession'], event['entrySession']],
            'REGISTERED_SIGNAL_ENTRY_TIMING_MISMATCH')
    require(core.utc(event['informationAvailableAtUtc']) <= core.utc(event['signalSession'] + 'T09:00:00Z'),
            'FUTURE_SIGNAL_INFORMATION')
    maturity = {f'H{h}': load('comparison').maturity_status('KR', event['entrySession'], h, as_of_utc)
                for h in (126, 252)}
    needed = ('cash', 'costTax', 'execution', 'distribution', 'terminal', 'shareClassIdentity')
    missing = [k for k in needed if not core.is_sha256(policies.get(k))]
    return {'scope': 'SOURCE_ONLY_NOT_EXECUTION_APPROVAL', 'eventId': event['rcept_no'],
            'maturity': maturity, 'missingPolicyHashes': missing,
            'status': 'BLOCKED' if missing else 'REFERENCES_PRESENT_NOT_SOURCE_ADMITTED',
            'historicalOutcomeAuthorized': False, 'performance': None}


def synthetic_payoff(fixture):
    """Self-financing shares + paid cash + unpaid claims; synthetic proofs only.

No automatic reinvestment, tax rate, zero cash yield, terminal price or fill
is assumed. A real strategy needs an approved policy and separate runner.
"""
    require(fixture.get('evidenceClass') == 'SYNTHETIC'
            and fixture.get('security', '').startswith('SYN_')
            and fixture.get('benchmark', '').startswith('SYN_'), 'SYNTHETIC_ONLY_NO_HISTORICAL_RUNNER')
    require(fixture.get('priceBasis') == 'AS_TRADED_UNADJUSTED'
            and fixture.get('distributionPolicy') == 'CASH_ON_PAYMENT_CLAIM_AT_PAR_NO_REINVESTMENT',
            'EXPLICIT_SYNTHETIC_BASIS_REQUIRED')
    require(fixture.get('coverage') == {'prices': 'COMPLETE', 'dividends': 'COMPLETE',
                                     'actions': 'COMPLETE', 'identity': 'VERIFIED'},
            'INCOMPLETE_TOTAL_RETURN_SOURCE')
    sources = fixture.get('sourceBytes', {})
    require(sources and all(isinstance(raw, bytes) for raw in sources.values()), 'RAW_SOURCE_BYTES_REQUIRED')
    proofs = fixture.get('sourceSha256', {})
    require(set(proofs) == set(sources) and all(hashlib.sha256(raw).hexdigest() == proofs[k]
                                             for k, raw in sources.items()), 'SOURCE_BYTES_CHANGED')
    bars = fixture['bars']
    dates = [r['date'] for r in bars]
    require(len(dates) >= 2 and dates == sorted(set(dates)), 'UNIQUE_ORDERED_SESSIONS_REQUIRED')
    expected = [d.strftime('%Y-%m-%d') for d in calendar.sessions(dates[0], dates[-1], 'KR')]
    require(dates == expected, 'PRICE_SESSION_GAP')
    for bar in bars:
        finite(bar['close'], positive=True)
        require(bar['sourceId'] in proofs, 'PRICE_SOURCE_PROVENANCE_MISSING')
    require(bars[0].get('traded') is True and bars[-1].get('traded') is True,
            'ACTUAL_ENTRY_EXIT_TRADABILITY_REQUIRED')
    cash = fixture['cashGrowth']
    require(set(cash) == set(dates[1:]), 'INVESTABLE_CASH_INTERVAL_MISSING')
    for i, day in enumerate(dates[1:], 1):
        row = cash[day]
        require(row.get('periodStart') == dates[i - 1] and row.get('periodEnd') == day
                and row.get('sourceId') in proofs and row.get('basis') == 'NET_INVESTABLE_PAYOFF',
                'INVESTABLE_CASH_NOT_REFERENCE_RATE')
        finite(row['growth'], positive=True)
    actions = fixture['actions']
    require(len({a['actionId'] for a in actions}) == len(actions), 'DUPLICATE_ECONOMIC_ACTION')
    for action in actions:
        require(action.get('sourceId') in proofs and action.get('security') == fixture['security'],
                'ACTION_IDENTITY_OR_SOURCE_MISMATCH')
        require(action['date'] in dates, 'ACTION_OUTSIDE_SESSION_GRID_NO_SNAPPING')
        require(action['kind'] in ('CASH_DIVIDEND', 'SPLIT', 'TERMINAL_CASH'), 'UNSUPPORTED_CORPORATE_ACTION_BLOCKED')
        if action['kind'] == 'SPLIT':
            finite(action['ratio'], positive=True)
        else:
            finite(action['amountPerShare'])
            finite(action['withholdingFraction'])
            require(action['withholdingFraction'] <= 1 and action.get('taxSourceId') in proofs,
                    'DIVIDEND_TERMINAL_TAX_POLICY_REQUIRED')
            require(action.get('dateSource') == 'DIRECT', 'DIRECT_EX_OR_TERMINAL_DATE_REQUIRED')
            require(date.fromisoformat(action['paymentDate']) >= date.fromisoformat(action['date']),
                    'PAYMENT_PRECEDES_ENTITLEMENT')
            require(action['paymentDate'] in dates or action['paymentDate'] > dates[-1],
                    'NON_SESSION_PAYMENT_NEEDS_CALENDAR_CASH_GRID')
    by_day = {d: [a for a in actions if a['date'] == d] for d in dates}
    require(all(len(rows) <= 1 for rows in by_day.values()), 'SAME_DAY_ACTION_ORDER_NOT_SEALED')
    require(not by_day[dates[0]], 'ENTRY_SESSION_ACTION_ENTITLEMENT_NOT_SEALED')
    reference = load('comparison')
    common = {'universe': [fixture['security']], 'benchmarkTicker': fixture['benchmark'],
              'costModel': fixture['costModel']}

    def cost(side, day, notional):
        leg = {'legId': side + ':' + day, 'security': fixture['security'], 'side': side,
               'session': day, 'notionalFractionOfInitialNav': notional}
        return reference.price_execution_legs(common, [leg])['totalCostFractionOfInitialNav']

    entry_rate = cost('BUY', dates[0], 1)
    shares = 1 / ((1 + entry_rate) * bars[0]['close'])
    paid_cash, claims = 0.0, []
    costs = entry_rate / (1 + entry_rate)
    for bar in bars[1:]:
        day = bar['date']
        paid_cash *= cash[day]['growth']
        for action in by_day[day]:
            if action['kind'] == 'SPLIT':
                shares *= action['ratio']
            else:
                amount = shares * action['amountPerShare'] * (1 - action['withholdingFraction'])
                claims.append({'amount': amount, 'paymentDate': action['paymentDate'],
                               'actionId': action['actionId'], 'sourceId': action['sourceId']})
                if action['kind'] == 'TERMINAL_CASH':
                    shares = 0.0
        for claim in claims:
            if claim['paymentDate'] == day:
                paid_cash += claim['amount']
        claims = [c for c in claims if c['paymentDate'] > day]
    sell_notional = shares * bars[-1]['close']
    sell_cost = cost('SELL', dates[-1], sell_notional)
    costs += sell_cost
    liquid = sell_notional - sell_cost + paid_cash
    receivable = math.fsum(c['amount'] for c in claims)
    return {'evidenceClass': 'SYNTHETIC', 'liquidCash': liquid, 'unpaidReceivable': receivable,
            'wealth': liquid + receivable, 'netReturn': liquid + receivable - 1,
            'transactionCosts': costs, 'sourceSha256': proofs,
            'historicalOutcomeAuthorized': False, 'notRegisteredEstimand': True}


def synthetic_pair(stock, etf):
    """Paired arithmetic only, never a beta-matched funded alpha estimate."""
    require([r['date'] for r in stock['bars']] == [r['date'] for r in etf['bars']],
            'ETF_ENTRY_MATURITY_GRID_MISMATCH')
    require(etf['security'] == stock['benchmark'] == etf['benchmark']
            and stock['costModel'] == etf['costModel']
            and stock['cashGrowth'] == etf['cashGrowth']
            and stock['distributionPolicy'] == etf['distributionPolicy'],
            'PAIRED_ECONOMIC_POLICY_MISMATCH')
    a, b = synthetic_payoff(stock), synthetic_payoff(etf)
    return {'evidenceClass': 'SYNTHETIC', 'stock': a, 'etf': b,
            'netActiveReturn': a['netReturn'] - b['netReturn'],
            'fundedAlphaStatus': 'NOT_EVALUATED_EX_ANTE_BETA_BOOK_REQUIRED',
            'historicalOutcomeAuthorized': False}
