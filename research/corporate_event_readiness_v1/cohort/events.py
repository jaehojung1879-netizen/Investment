"""Outcome-free event funnel: filing versions -> economic events -> independent N.

Nothing here reads a price, return, label or NAV. Every filing version gets
exactly one terminal stage and, if it stops, the FIRST gate it failed.

Timing rule (Owner draft, #292 comment 6671600416, C0): DART serves the
receipt DAY only, so the signal is the close of the first KR session strictly
after the receipt day and entry is the close of the session after that. This
is DATE_ONLY_CONSERVATIVE; PIT_EXACT needs a publication clock that no
available source serves, so PIT_EXACT is 0 by construction, not by omission.
"""
from __future__ import annotations

import bisect
import re
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal

from pipeline.kr_corporate_action_events import is_amendment

from .families import is_subsidiary_report

PERIOD = ('2013-01-01', '2026-10-31')
VALUE_UP_BOUNDARY = '2024-02-26'
RECENT_CONCENTRATION = ('2025-01-01', '2026-12-31')
HORIZONS = (126, 252)
B1_RATIO_PCT = Decimal('10')
BODY_FAMILIES = ('CANCELLATION', 'BUYBACK', 'TRUST', 'SUPPLY')
LIST_LEVEL_FAMILIES = ('TERMINATION', 'DISPOSAL', 'RIGHTS', 'CB', 'EB', 'BW', 'CAPITAL_REDUCTION', 'TRUST_TERMINATION')
HYPOTHESES = ('A1', 'A2', 'B1')

GATES = ('IN_PERIOD', 'ORIGINAL_VERSION', 'NOT_SUBSIDIARY_REPORT', 'PIT_TOP300_IDENTITY',
         'BODY_FAMILY', 'BODY_RETRIEVED', 'TERMS_PARSED', 'HYPOTHESIS_CLASS',
         'NO_PRE_ENTRY_AMENDMENT', 'ENTRY_WITHIN_CALENDAR')


def iso(yyyymmdd: str) -> str:
    return date(int(yyyymmdd[:4]), int(yyyymmdd[4:6]), int(yyyymmdd[6:8])).isoformat()


def purpose_class(text) -> str:
    if not text or not isinstance(text, str):
        return 'NOT_STATED'
    t = re.sub(r'\s+', '', text)
    if '소각' in t:
        return 'CANCELLATION_STATED'
    if any(k in t for k in ('합병', '주식교환', '분할', '교환사채', '공개매수')):
        return 'CORPORATE_ACTION'
    if any(k in t for k in ('임직원', '우리사주', '보상', '성과급', '스톡옵션', '주식매수선택권', '상여')):
        return 'EMPLOYEE'
    if any(k in t for k in ('주가안정', '주주가치', '기업가치', '주주환원', '주가부양', '책임경영')):
        return 'SHAREHOLDER_VALUE'
    return 'OTHER'


def _positive(value) -> bool:
    try:
        return value is not None and Decimal(value) > 0
    except Exception:
        return False


def classify(row: dict, parsed: dict | None) -> tuple[str | None, str]:
    """Return (hypothesis or None, economic event type). Uses filed terms only."""
    fam = row['family']
    if parsed is None:
        return None, 'BODY_NOT_PARSED'
    if fam == 'CANCELLATION':
        if _positive(parsed.get('quantity_common')) and _positive(parsed.get('issued_shares_common_at_decision')):
            return 'A1', 'CANCELLATION_DECISION_COMMON'
        if _positive(parsed.get('quantity_other')) and not _positive(parsed.get('quantity_common')):
            return None, 'CANCELLATION_OTHER_CLASS_ONLY'
        return None, 'CANCELLATION_TERMS_INCOMPLETE'
    if fam in ('BUYBACK', 'TRUST'):
        pclass = purpose_class(parsed.get('purpose'))
        if fam == 'BUYBACK' and not _positive(parsed.get('quantity_common')):
            return None, 'BUYBACK_COMMON_QUANTITY_MISSING'
        if fam == 'TRUST' and not _positive(parsed.get('amount_krw')):
            return None, 'TRUST_AMOUNT_MISSING'
        if pclass == 'CANCELLATION_STATED':
            return 'A1', fam + '_FOR_CANCELLATION'
        if pclass in ('SHAREHOLDER_VALUE', 'OTHER', 'NOT_STATED'):
            return 'A2', fam + '_NO_CANCELLATION_STATED:' + pclass
        return None, fam + '_EXCLUDED:' + pclass
    if fam == 'SUPPLY':
        flags = parsed.get('cohort_flags') or []
        if 'PROGRESS_UPDATE_OF_EARLIER_CONTRACT' in flags:
            return None, 'SUPPLY_PROGRESS_UPDATE_LATER_STATE'
        ratio = parsed.get('reported_contract_ratio_pct')
        if ratio is None and 'TERMS_WITHHELD_UNTIL_LATER_DISCLOSURE' in flags:
            return None, 'SUPPLY_TERMS_WITHHELD_AT_SIGNAL'
        if not (_positive(parsed.get('contract_amount_krw')) and _positive(parsed.get('recent_revenue_krw'))
                and ratio is not None):
            return None, 'SUPPLY_TERMS_INCOMPLETE'
        if 'CONTRACT_RATIO_MISMATCH' in parsed.get('quarantine_reasons', []):
            return None, 'SUPPLY_RATIO_MISMATCH'
        if Decimal(ratio) >= B1_RATIO_PCT:
            return 'B1', 'SUPPLY_LARGE_GE_10PCT_REVENUE'
        return None, 'SUPPLY_BELOW_10PCT_REVENUE'
    if fam == 'TERMINATION':
        return None, 'SUPPLY_TERMINATION_LATER_STATE'
    return None, 'LIST_LEVEL_ONLY'


class Calendar:
    def __init__(self, sessions: list[str]):
        self.sessions = sessions

    def first_after(self, day: str) -> int | None:
        i = bisect.bisect_right(self.sessions, day)
        return i if i < len(self.sessions) else None

    def at(self, i: int) -> str | None:
        return self.sessions[i] if 0 <= i < len(self.sessions) else None


def build(index_rows: list[dict], pit, bodies: dict[str, dict], calendar: Calendar,
          *, data_cutoff: str, as_of: str, period: tuple[str, str] = PERIOD) -> dict:
    """``bodies``: rcept_no -> {'parsed': dict|None, 'amendmentRef': dict|None, 'error': str|None}."""
    versions, stage_counts = [], Counter()
    amendments_by_key: dict[tuple, list[dict]] = defaultdict(list)
    for row in index_rows:
        if is_amendment(row['report_nm']):
            amendments_by_key[(row['corp_code'], row['family'])].append(row)

    def stop(rec, gate):
        rec['stoppedAt'] = gate
        stage_counts[gate] += 1
        versions.append(rec)

    for row in sorted(index_rows, key=lambda r: (r['rcept_dt'], r['rcept_no'])):
        day = iso(row['rcept_dt'])
        rec = {'rcept_no': row['rcept_no'], 'corp_code': row['corp_code'], 'stock_code': row['stock_code'],
               'family': row['family'], 'receiptDay': day, 'rm': row.get('rm', '')}
        if not period[0] <= day <= period[1]:
            stop(rec, 'IN_PERIOD')
            continue
        if is_amendment(row['report_nm']):
            ref = (bodies.get(row['rcept_no']) or {}).get('amendmentRef')
            rec['amendmentRef'] = ref
            stop(rec, 'ORIGINAL_VERSION')
            continue
        if is_subsidiary_report(row['report_nm']):
            stop(rec, 'NOT_SUBSIDIARY_REPORT')
            continue
        member = pit.membership(row.get('stock_code'), day)
        rec['identity'] = member
        if member['status'] != 'PIT_TOP300_MEMBER':
            stop(rec, 'PIT_TOP300_IDENTITY')
            continue
        if row['family'] not in BODY_FAMILIES:
            stop(rec, 'BODY_FAMILY')
            continue
        body = bodies.get(row['rcept_no'])
        if not body or body.get('error') or body.get('parsed') is None:
            rec['bodyError'] = (body or {}).get('error', 'NOT_FETCHED')
            stop(rec, 'BODY_RETRIEVED')
            continue
        parsed = body['parsed']
        hypothesis, etype = classify(row, parsed)
        rec['eventType'] = etype
        rec['terms'] = {k: parsed.get(k) for k in (
            'decision_date', 'quantity_common', 'issued_shares_common_at_decision', 'share_ratio_pct',
            'amount_krw', 'purpose', 'contract_amount_krw', 'recent_revenue_krw',
            'reported_contract_ratio_pct', 'revenue_fiscal_year', 'contract_start', 'contract_end')}
        if hypothesis is None:
            stop(rec, 'TERMS_PARSED' if 'INCOMPLETE' in etype or 'MISSING' in etype or etype == 'BODY_NOT_PARSED'
                 else 'HYPOTHESIS_CLASS')
            continue
        rec['hypothesis'] = hypothesis
        sig = calendar.first_after(day)
        entry = sig + 1 if sig is not None else None
        entry_day = calendar.at(entry) if entry is not None else None
        rec['signalSession'], rec['entrySession'] = calendar.at(sig) if sig is not None else None, entry_day
        # Pre-entry amendment: explicit body link (KRX form) or, when the amendment's
        # body states no reference, ANY same-issuer same-family amendment filed in
        # [receipt day, entry day] -- a conservative exclusion on pre-entry information
        # that never copies values across an unproven link.
        pre_entry = []
        for am in amendments_by_key.get((row['corp_code'], row['family']), []):
            am_day = iso(am['rcept_dt'])
            if entry_day is None or not day <= am_day <= entry_day:
                continue
            ref = (bodies.get(am['rcept_no']) or {}).get('amendmentRef') or {}
            if ref.get('status') == 'STATED':
                if ref.get('referencedFirstFilingDay') == day:
                    pre_entry.append({'rcept_no': am['rcept_no'], 'link': 'BODY_STATED'})
            else:
                pre_entry.append({'rcept_no': am['rcept_no'], 'link': 'UNLINKED_SAME_ISSUER_FAMILY_WINDOW'})
        if pre_entry:
            rec['preEntryAmendments'] = pre_entry
            stop(rec, 'NO_PRE_ENTRY_AMENDMENT')
            continue
        if entry_day is None or entry_day > data_cutoff:
            stop(rec, 'ENTRY_WITHIN_CALENDAR')
            continue
        rec['pitGrade'] = 'DATE_ONLY_CONSERVATIVE'
        rec['_entryIndex'] = entry
        for h in HORIZONS:
            end = calendar.at(entry + h)
            rec[f'H{h}End'] = end
            rec[f'H{h}Matured'] = bool(end and end <= as_of)
        stage_counts['DATE_ONLY_CONSERVATIVE_CANDIDATE'] += 1
        rec['stoppedAt'] = None
        versions.append(rec)

    candidates = [v for v in versions if v.get('pitGrade')]
    independent = {}
    for hyp in HYPOTHESES:
        for h in HORIZONS:
            last: dict[str, int] = {}
            kept = []
            for v in sorted((c for c in candidates if c['hypothesis'] == hyp),
                            key=lambda c: (c['_entryIndex'], c['rcept_no'])):
                prev = last.get(v['corp_code'])
                if prev is not None and v['_entryIndex'] < prev + h:
                    v.setdefault('followOnOf', {})[f'H{h}'] = True
                    continue
                last[v['corp_code']] = v['_entryIndex']
                kept.append(v)
            independent[(hyp, h)] = kept
    for v in versions:
        v.pop('_entryIndex', None)
    return {'versions': versions, 'stageCounts': dict(stage_counts), 'candidates': candidates,
            'independent': independent}


def describe(events: list[dict], horizon: int, sessions: list[str]) -> dict:
    """Calendar-only description of an independent set; no return is read."""
    if not events:
        return {'N': 0}
    years = Counter(e['entrySession'][:4] for e in events)
    weeks = {date.fromisoformat(e['entrySession']).isocalendar()[:2] for e in events}
    months = Counter(e['entrySession'][:7] for e in events)
    issuers = {e['corp_code'] for e in events}
    pre = sum(e['entrySession'] < VALUE_UP_BOUNDARY for e in events)
    recent = sum(RECENT_CONCENTRATION[0] <= e['entrySession'] <= RECENT_CONCENTRATION[1] for e in events)
    # Concurrency: open positions per session if every independent event were held H sessions.
    index = {s: i for i, s in enumerate(sessions)}
    open_count = Counter()
    for e in events:
        i = index[e['entrySession']]
        for j in range(i, min(i + horizon, len(sessions))):
            open_count[j] += 1
    covered = [open_count[j] for j in open_count]
    span = range(index[min(e['entrySession'] for e in events)], index[max(e['entrySession'] for e in events)] + 1)
    empty = sum(1 for j in span if open_count.get(j, 0) == 0)
    max_issuer_share = max(Counter(e['corp_code'] for e in events).values()) / len(events)
    return {
        'N': len(events), 'issuers': len(issuers), 'entryWeeks': len(weeks), 'entryMonths': len(months),
        'byEntryYear': dict(sorted(years.items())),
        'preValueUp': pre, 'postValueUp': len(events) - pre, 'recent2025to2026': recent,
        'matured': sum(e[f'H{horizon}Matured'] for e in events),
        'meanConcurrentWhenActive': round(sum(covered) / len(covered), 2) if covered else 0,
        'maxConcurrent': max(covered) if covered else 0,
        'sessionsWithNoOpenPositionInSpan': empty, 'sessionsInSpan': len(span),
        'largestIssuerShare': round(max_issuer_share, 4),
    }
