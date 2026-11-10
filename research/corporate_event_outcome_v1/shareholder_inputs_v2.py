"""Versioned, fail-closed shareholder inputs. The sealed v1 recipe is untouched.

These pure helpers do not fetch data or execute a historical study. A common
DPS belongs to the reporting issuer's COMMON security only. Unknown corporate
actions are blocked rather than repaired by a price-ratio guess.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict

from research.corporate_event_readiness_v1.cohort.families import is_subsidiary_report


class SourceBlocked(ValueError):
    """A shareholder payoff or a signal cannot be established from its sources."""


def number(value):
    try:
        n = float(str(value).replace(',', ''))
    except (TypeError, ValueError):
        raise SourceBlocked('AMOUNT_UNKNOWN') from None
    if not math.isfinite(n) or n < 0:
        raise SourceBlocked('AMOUNT_INVALID')
    return n


def receipt_day(row):
    s = str(row.get('rcept_dt') or str(row.get('rcept_no', ''))[:8])
    if len(s) == 8 and s.isdigit():
        return f'{s[:4]}-{s[4:6]}-{s[6:]}'
    raise SourceBlocked('RECEIPT_DAY_UNKNOWN')


def issuer_cash_dividends(rows, security_classes, *, known_before=None, cited_stock_receipts=()):
    """DART decisions -> own-issuer common cash DPS; no silent last-row wins.

    `security_classes` is an admitted security-identity map, not an inference
    from ticker suffixes. A correction needs an explicit original receipt link.
    Zero is a known zero; absent DPS is blocked. STOCK is never treated as cash.
    `known_before` is exclusive, as DART supplies a day but no publication clock.
    Returns (dividends_by_ticker_and_exdate, diagnostics, blocked_tickers).
    """
    counts, blocked, groups, seen = Counter(), defaultdict(list), defaultdict(list), {}
    for row in sorted(rows, key=lambda x: str(x['rcept_no'])):
        ticker = row.get('ticker') or (row.get('stock_code', '') + '.KS')
        if is_subsidiary_report(row.get('report_nm', '')):
            counts['SUBSIDIARY_EXCLUDED'] += 1
            continue
        if known_before and receipt_day(row) >= known_before:
            counts['NOT_PUBLIC_BEFORE_SIGNAL'] += 1
            continue
        if security_classes.get(ticker) != 'COMMON':
            blocked[ticker].append('SECURITY_CLASS_NOT_CONFIRMED_COMMON')
            continue
        if row.get('securityClass', 'COMMON') != 'COMMON':
            counts['OTHER_SECURITY_CLASS_EXCLUDED'] += 1
            continue
        if row.get('kind') == 'STOCK' or row.get('dividendKind') == '주식배당':
            if row['rcept_no'] in cited_stock_receipts:
                counts['STOCK_DIVIDEND_HANDLED_BY_CITED_SHARE_ACTION'] += 1
            else:
                blocked[ticker].append('STOCK_DIVIDEND_REQUIRES_CITED_SHARE_ACTION')
            continue
        if row.get('dividendKind') != '현금배당':
            blocked[ticker].append('DIVIDEND_KIND_NOT_CONFIRMED_CASH')
            continue
        if not row.get('corp_code') or not row.get('recordDate'):
            blocked[ticker].append('ISSUER_OR_RECORD_DATE_MISSING')
            continue
        ident = (ticker, str(row['rcept_no']))
        if ident in seen:
            if seen[ident] != row:
                blocked[ticker].append('CONFLICTING_SAME_RECEIPT')
            else:
                counts['EXACT_DUPLICATE_IGNORED'] += 1
            continue
        seen[ident] = row
        groups[(ticker, row['corp_code'], row['recordDate'])].append(row)
    out = defaultdict(dict)
    for (ticker, issuer, record), versions in groups.items():
        originals = [r for r in versions if not r.get('amendment')]
        if len(originals) != 1:
            blocked[ticker].append('DIVIDEND_ORIGINAL_NOT_UNIQUE')
            continue
        original, chosen = originals[0], originals[0]
        for row in versions:
            if not row.get('amendment'):
                continue
            if row.get('amendsReceipt') not in (original['rcept_no'], chosen['rcept_no']):
                blocked[ticker].append('CORRECTION_CHAIN_UNRESOLVED')
                continue
            chosen = row
        try:
            dps = number(chosen.get('dpsCommonKrw'))
        except SourceBlocked as exc:
            blocked[ticker].append(str(exc))
            continue
        ex = chosen.get('exDateOfficial') or chosen.get('exDateMarketRuleCandidate')
        if not ex:
            blocked[ticker].append('EX_DATE_UNKNOWN')
            continue
        if ex in out[ticker]:
            blocked[ticker].append('MULTIPLE_DISTRIBUTIONS_SAME_EX_DATE_UNRESOLVED')
            continue
        out[ticker][ex] = {'dps': dps, 'rcept_no': chosen['rcept_no'], 'corp_code': issuer,
                           'recordDate': record, 'securityClass': 'COMMON',
                           'amountBasis': chosen.get('amountBasis', 'UNSPECIFIED'),
                           'exDateTier': ('OFFICIAL' if chosen.get('exDateOfficial') else
                                          'MARKET_RULE_PROXY_NOT_OFFICIALLY_VERIFIED'),
                           'knownOn': receipt_day(chosen), 'source': chosen.get('source', {})}
    # Never expose a partially trusted ticker as a complete total-return input.
    for ticker in blocked:
        out.pop(ticker, None)
    return dict(out), dict(counts), {t: sorted(set(v)) for t, v in blocked.items()}


def annual_comparison(current, previous):
    """Keep verified fiscal years separate from calendar record-year proxies.

    Without verified fiscal periods, only a stable Dec-31 year-end sequence is
    comparable as a disclosed proxy. A changed/post-year-end record date is
    blocked; no fiscal year is inferred by subtracting one from receipt year.
    """
    if current.get('fiscalYearVerified') and previous.get('fiscalYearVerified'):
        fy, py = int(current['fiscalYear']), int(previous['fiscalYear'])
        if fy != py + 1:
            raise SourceBlocked('FISCAL_PERIODS_NOT_CONSECUTIVE')
        return {'basis': 'VERIFIED_FISCAL_YEAR', 'fiscalYear': fy}
    a, b = current.get('recordDate', ''), previous.get('recordDate', '')
    if not (a.endswith('-12-31') and b.endswith('-12-31') and int(a[:4]) == int(b[:4]) + 1):
        raise SourceBlocked('FISCAL_YEAR_OR_RECORD_DATE_SHIFT_UNRESOLVED')
    return {'basis': 'STABLE_DEC31_RECORD_YEAR_PROXY_NOT_VERIFIED_FISCAL_YEAR',
            'fiscalYear': None, 'comparisonRecordYear': int(a[:4])}


def cited_levels(rows, dividends, actions=(), *, known_before=None):
    """One security's shareholder index using cited actions, never guessed ratios.

    Action `shareMultiplier` is shares after / shares before (split, reverse
    split, stock dividend). Terminal cash is per old share and needs a cited
    source. Simultaneous cash/share actions require the dividend's share basis.
    Historical outcome use still requires the caller's completeness admission;
    this function alone cannot certify the absence of unreported actions.
    """
    bars = sorted(rows, key=lambda r: r['date'])
    by_day = {}
    for action in actions:
        if not action.get('sourceSha256') or not action.get('confirmedOn'):
            raise SourceBlocked('UNCITED_OR_UNDATED_ACTION')
        if known_before and action['confirmedOn'] >= known_before:
            raise SourceBlocked('ACTION_NOT_KNOWN_BEFORE_SIGNAL')
        if action.get('state') != 'VERIFIED':
            raise SourceBlocked('CORPORATE_ACTION_UNRESOLVED')
        if action.get('kind') not in ('SPLIT', 'REVERSE_SPLIT', 'STOCK_DIVIDEND', 'TERMINAL_CASH'):
            raise SourceBlocked('RIGHTS_MERGER_OR_OTHER_ACTION_REQUIRES_CITED_ECONOMIC_PACKAGE')
        if action.get('terminalCashPerOldShare') is not None and action['kind'] != 'TERMINAL_CASH':
            raise SourceBlocked('TERMINAL_CASH_KIND_MISMATCH')
        if action['date'] in by_day:
            raise SourceBlocked('MULTIPLE_ACTIONS_SAME_DAY_UNRESOLVED')
        by_day[action['date']] = action
    if len({r['date'] for r in bars}) != len(bars):
        raise SourceBlocked('DUPLICATE_PRICE_DATE')
    levels, tradable, terminal = {}, set(), {}
    prev = None
    for row in bars:
        day = row['date']
        action = by_day.get(day, {})
        # This is a cited cash settlement, never an invented tradable close.
        close = (prev['close'] if prev and action.get('terminalCashPerOldShare') is not None
                 else number(row.get('close')))
        if close <= 0:
            raise SourceBlocked('NONPOSITIVE_PRICE')
        if row.get('volume', 0) > 0:
            tradable.add(day)
        if prev is None:
            levels[day] = 1.0
        else:
            factor = number(action.get('shareMultiplier', 1))
            if factor <= 0:
                raise SourceBlocked('NONPOSITIVE_SHARE_MULTIPLIER')
            distribution = dividends.get(day, {})
            dps = number(distribution.get('dps', 0))
            if (row.get('volume') or 0) <= 0 and action.get('terminalCashPerOldShare') is None and (action or dps):
                raise SourceBlocked('HALTED_ACTION_OR_DIVIDEND_VALUATION_UNRESOLVED')
            if factor != 1 and dps:
                basis = distribution.get('amountBasis')
                if basis == 'POST_ACTION_SHARE':
                    dps *= factor
                elif basis != 'PRE_ACTION_SHARE':
                    raise SourceBlocked('SIMULTANEOUS_ACTION_CASH_BASIS_UNKNOWN')
            move = close * factor / prev['close'] - 1
            if not action and abs(move) > (0.15 if day < '2015-06-15' else 0.30) + 0.001:
                raise SourceBlocked('PRICE_MOVE_REQUIRES_CITED_CORPORATE_ACTION')
            if action.get('terminalCashPerOldShare') is not None:
                multiple = number(action['terminalCashPerOldShare']) / prev['close']
                terminal[day] = {'multiple': multiple, 'sourceSha256': action['sourceSha256']}
                gross = multiple
            else:
                gross = (close * factor + dps) / prev['close']
            levels[day] = levels[prev['date']] * gross
        prev = {'date': day, 'close': close}
        if action.get('terminalCashPerOldShare') is not None:
            break
    return levels, tradable, terminal


def dilution_evidence(family, terms=None):
    """Label evidence without turning a title match into realized dilution.

    The registered P2 cohort is not silently filtered to a new hypothesis.
    Parsed terms, when available, remain descriptive fields for that cohort.
    """
    if family not in ('RIGHTS', 'CB', 'EB', 'BW'):
        raise SourceBlocked('NOT_A_REGISTERED_P2_FAMILY')
    return {'family': family, 'definition': 'REGISTERED_TITLE_DECISION_NOT_REALIZED_DILUTION',
            'economicDilution': (terms or {}).get('economicDilution', 'UNVERIFIED'),
            'termsSourceSha256': (terms or {}).get('sourceSha256'),
            'cohortMembershipChangedByTerms': False}
