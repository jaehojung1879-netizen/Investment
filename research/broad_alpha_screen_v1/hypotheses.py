"""Outcome-free event sets for every screened hypothesis. No price, return or label is read here.

Reused, not rebuilt (#320/#322): the sealed A1/A2/B1 cohort, the Top300 issuer filing index, the parsed
dividend decisions, ``Calendar`` / ``PitTop300`` and the amendment / subsidiary-report rules. New here is
only the mapping from those existing records to hypothesis ids, under the cohort's own conventions:
signal = first session after the receipt day, entry = the session after it, a same-issuer same-family
amendment filed up to the entry day removes the event, and a later event of the same issuer inside an
open H-session window is a follow-on, not a new independent event.
"""
from __future__ import annotations

import gzip
import json
from collections import Counter, defaultdict
from pathlib import Path

from pipeline import replay_calendar as RC
from pipeline.kr_corporate_action_events import is_amendment
from research.corporate_event_readiness_v1.cohort.events import Calendar, describe, iso
from research.corporate_event_readiness_v1.cohort.families import is_subsidiary_report
from research.corporate_event_readiness_v1.cohort.identity import PitTop300, load_snapshots

REPO = Path(__file__).resolve().parents[2]
COHORT = REPO / 'research' / 'corporate_event_readiness_v1' / 'cohort' / 'data'
HERE = Path(__file__).resolve().parent
DATA_CUTOFF, AS_OF = '2026-10-30', '2026-10-30'
HORIZONS = (126, 252)
DIVIDEND_CHANGE = 0.25          # fixed before any outcome: +/-25% change of the year-end common cash DPS
OWNERSHIP_MIN_INCREASE_PP = 1.0  # the 5%-rule's own reporting step

# id -> (expected sign of the funded beta-matched selection term, mechanism, source grade)
HYPOTHESES = {
    'K1_CANCELLATION': (+1, '자사주 소각·소각 목적 취득 (cohort A1)', 'BODY_PARSED_DATE_ONLY_CONSERVATIVE'),
    'K2_BUYBACK_NO_CANCEL': (+1, '비소각 자사주 취득·신탁 (cohort A2)', 'BODY_PARSED_DATE_ONLY_CONSERVATIVE'),
    'K3_SUPPLY_GE_10PCT': (+1, '매출 10% 이상 단일판매·공급계약 (cohort B1)', 'BODY_PARSED_DATE_ONLY_CONSERVATIVE'),
    'K4_RIGHTS_ISSUE': (-1, '유상증자 결정 (주식수 희석)', 'TITLE_LEVEL_TERMS_UNPARSED'),
    'K5_EQUITY_LINKED_DEBT': (-1, 'CB·EB·BW 발행 결정 (잠재 희석)', 'TITLE_LEVEL_TERMS_UNPARSED'),
    'K6_SUPPLY_TERMINATION': (-1, '단일판매·공급계약 해지', 'TITLE_LEVEL_TERMS_UNPARSED'),
    'K7_DIVIDEND_INCREASE': (+1, '결산 현금배당 주당 25% 이상 증액', 'BODY_PARSED_DPS'),
    'K8_DIVIDEND_CUT': (-1, '결산 현금배당 주당 25% 이상 감액', 'BODY_PARSED_DPS'),
    'K9_BLOCK_HOLDER_INCREASE': (+1, '5% 대량보유 1%p 이상 증가 보고', 'DART_MAJORSTOCK_2024_09_ONWARD'),
}
# Pooled primaries, fixed before any outcome because no single component can detect 3pp (eligibility-v1.json):
# one mechanism each, events of the components merged and de-duplicated per issuer.
POOLED = {
    'P1_CAPITAL_RETURN': (+1, '주주환원 결정 통합: 소각 + 자사주 취득·신탁 + 배당 증액',
                          ('K1_CANCELLATION', 'K2_BUYBACK_NO_CANCEL', 'K7_DIVIDEND_INCREASE')),
    'P2_DILUTION': (-1, '희석 결정 통합: 유상증자 + CB·EB·BW', ('K4_RIGHTS_ISSUE', 'K5_EQUITY_LINKED_DEBT')),
}
for _k, (_s, _m, _parts) in POOLED.items():
    HYPOTHESES[_k] = (_s, _m, 'POOLED:' + '+'.join(_parts))
PRIMARY_FAMILY = ('P1_CAPITAL_RETURN', 'P2_DILUTION', 'K3_SUPPLY_GE_10PCT')
COHORT_MAP = {'A1': 'K1_CANCELLATION', 'A2': 'K2_BUYBACK_NO_CANCEL', 'B1': 'K3_SUPPLY_GE_10PCT'}
TITLE_MAP = {'RIGHTS': 'K4_RIGHTS_ISSUE', 'CB': 'K5_EQUITY_LINKED_DEBT', 'EB': 'K5_EQUITY_LINKED_DEBT',
             'BW': 'K5_EQUITY_LINKED_DEBT', 'TERMINATION': 'K6_SUPPLY_TERMINATION'}


def _jsonl(path: Path) -> list[dict]:
    with gzip.open(path, 'rt', encoding='utf-8') as fh:
        return [json.loads(line) for line in fh]


def sessions() -> list[str]:
    return [d.strftime('%Y-%m-%d') for d in RC.sessions('2013-01-01', '2027-12-31', 'KR')]


def _timed(rec: dict, day: str, cal: Calendar) -> dict | None:
    sig = cal.first_after(day)
    if sig is None or cal.at(sig + 1) is None or cal.at(sig + 1) > DATA_CUTOFF:
        return None
    rec.update(receiptDay=day, signalSession=cal.at(sig), entrySession=cal.at(sig + 1), _entry=sig + 1,
               pitGrade='DATE_ONLY_CONSERVATIVE')
    return rec


def cohort_events() -> tuple[list[dict], Counter]:
    out, drop = [], Counter()
    for e in _jsonl(COHORT / 'cohort-events-v1.jsonl.gz'):
        if e.get('pitGrade') and e.get('hypothesis') in COHORT_MAP:
            out.append({'hypothesis': COHORT_MAP[e['hypothesis']], 'rcept_no': e['rcept_no'],
                        'corp_code': e['corp_code'], 'stock_code': e['stock_code'], 'receiptDay': e['receiptDay'],
                        'signalSession': e['signalSession'], 'entrySession': e['entrySession'],
                        'pitGrade': e['pitGrade'], 'independent': e['independent'],
                        'detail': {'family': e['family'],
                                   'contractRatioPct': (e.get('terms') or {}).get('reported_contract_ratio_pct')}})
        else:
            drop['COHORT_NOT_ADMITTED'] += 1
    return out, drop


def title_events(pit: PitTop300, cal: Calendar) -> tuple[list[dict], Counter]:
    rows = _jsonl(COHORT / 'issuer-index-rows-v1.jsonl.gz')
    amendments = defaultdict(list)
    for r in rows:
        if is_amendment(r['report_nm']):
            amendments[(r['corp_code'], r['family'])].append(iso(r['rcept_dt']))
    out, drop = [], Counter()
    for r in sorted(rows, key=lambda x: (x['rcept_dt'], x['rcept_no'])):
        hyp = TITLE_MAP.get(r['family'])
        if hyp is None:
            continue
        day = iso(r['rcept_dt'])
        if is_amendment(r['report_nm']):
            drop[f'{hyp}:AMENDMENT_VERSION'] += 1
        elif is_subsidiary_report(r['report_nm']):
            drop[f'{hyp}:SUBSIDIARY_REPORT'] += 1
        elif pit.membership(r.get('stock_code'), day)['status'] != 'PIT_TOP300_MEMBER':
            drop[f'{hyp}:NOT_PIT_TOP300'] += 1
        else:
            rec = _timed({'hypothesis': hyp, 'rcept_no': r['rcept_no'], 'corp_code': r['corp_code'],
                          'stock_code': r['stock_code'], 'detail': {'family': r['family']}}, day, cal)
            if rec is None:
                drop[f'{hyp}:ENTRY_AFTER_CUTOFF'] += 1
            elif any(day <= a <= rec['entrySession'] for a in amendments[(r['corp_code'], r['family'])]):
                drop[f'{hyp}:PRE_ENTRY_AMENDMENT'] += 1
            else:
                out.append(rec)
    return out, drop


def dividend_events(pit: PitTop300, cal: Calendar) -> tuple[list[dict], Counter]:
    """Year-end common cash DPS against the same stock's previous year-end DPS, at the decision's receipt day."""
    by_stock = defaultdict(dict)
    drop = Counter()
    for r in sorted(_jsonl(COHORT / 'dividend-decisions-v1.jsonl.gz'), key=lambda x: x['rcept_no']):
        if r.get('dividendClass') != '결산배당' or r.get('dividendKind') != '현금배당' or not r.get('recordDate'):
            continue
        if r.get('amendment'):
            drop['DIVIDEND:AMENDMENT_VERSION'] += 1
            continue
        try:
            dps = float(str(r.get('dpsCommonKrw')).replace(',', ''))
        except ValueError:
            drop['DIVIDEND:COMMON_DPS_NOT_PARSED'] += 1
            continue
        by_stock[r['stock_code']].setdefault(int(r['recordDate'][:4]), {**r, '_dps': dps})   # first original wins
    out = []
    for code, years in by_stock.items():
        for fy, r in sorted(years.items()):
            prev = years.get(fy - 1)
            if prev is None or prev['_dps'] <= 0:
                drop['DIVIDEND:NO_PRIOR_YEAR_DPS_IN_SOURCE'] += 1
                continue
            a, b = _listed(pit, code, prev['recordDate']), _listed(pit, code, r['recordDate'])
            if not a or not b or not 0.9 <= b / a <= 1.1:
                drop['DIVIDEND:SHARE_COUNT_CHANGED_OR_UNKNOWN_DPS_NOT_COMPARABLE'] += 1
                continue
            change = r['_dps'] / prev['_dps'] - 1
            hyp = ('K7_DIVIDEND_INCREASE' if change >= DIVIDEND_CHANGE else
                   'K8_DIVIDEND_CUT' if change <= -DIVIDEND_CHANGE else None)
            if hyp is None:
                drop['DIVIDEND:CHANGE_INSIDE_25PCT_BAND'] += 1
                continue
            day = iso(r['rcept_dt'])
            if pit.membership(code, day)['status'] != 'PIT_TOP300_MEMBER':
                drop[f'{hyp}:NOT_PIT_TOP300'] += 1
                continue
            rec = _timed({'hypothesis': hyp, 'rcept_no': r['rcept_no'], 'corp_code': r['corp_code'],
                          'stock_code': code, 'detail': {'dpsChangePct': round(100 * change, 2), 'fiscalYear': fy}},
                         day, cal)
            if rec is None:
                drop[f'{hyp}:ENTRY_AFTER_CUTOFF'] += 1
            else:
                out.append(rec)
    return out, drop


_SHARES: dict = {}


def _listed(pit: PitTop300, code: str, day: str) -> float | None:
    snap = pit.prior_snapshot(day)
    return _SHARES.get((snap, code)) if snap else None


def load_listed_shares(universe_dir: Path) -> None:
    for path in sorted(Path(universe_dir).glob('krx-universe-*.jsonl.gz')):
        for row in _jsonl(path):
            _SHARES[(row['date'], row['code'])] = row.get('listedShares')


def ownership_events(pit: PitTop300, cal: Calendar, ownership_dir: Path) -> tuple[list[dict], Counter]:
    issuers = json.loads((COHORT / 'issuer-universe-v1.json').read_text(encoding='utf-8'))['issuers']
    # an issuer with several securities (common + preferred) is ambiguous at this level: only single-security issuers
    code_of = {i['corpCode']: i['securities'][0]['stockCode'] for i in issuers if len(i['securities']) == 1}
    out, drop = [], Counter()
    for path in sorted(Path(ownership_dir).glob('dart-ownership-20*.jsonl.gz')):
        for r in _jsonl(path):
            hyp = 'K9_BLOCK_HOLDER_INCREASE'
            if r.get('changeDirection') != 'INCREASE' or (r.get('holdingPctChange') or 0) < OWNERSHIP_MIN_INCREASE_PP:
                drop[f'{hyp}:NOT_AN_INCREASE_OF_1PP'] += 1
                continue
            code = code_of.get(r['corpCode'])
            day = r['availableFrom']
            if not code:
                drop[f'{hyp}:NO_STOCK_CODE_FOR_ISSUER'] += 1
            elif pit.membership(code, day)['status'] != 'PIT_TOP300_MEMBER':
                drop[f'{hyp}:NOT_PIT_TOP300'] += 1
            else:
                rec = _timed({'hypothesis': hyp, 'rcept_no': r['receiptNo'], 'corp_code': r['corpCode'],
                              'stock_code': code, 'detail': {'reportTypeRaw': r.get('reportTypeRaw'),
                                                             'holdingPctChange': r.get('holdingPctChange')}}, day, cal)
                if rec is None:
                    drop[f'{hyp}:ENTRY_AFTER_CUTOFF'] += 1
                else:
                    out.append(rec)
    return out, drop


def mark_independent(events: list[dict]) -> None:
    for hyp in HYPOTHESES:
        for h in HORIZONS:
            last: dict[str, int] = {}
            for e in sorted((x for x in events if x['hypothesis'] == hyp and '_entry' in x),
                            key=lambda x: (x['_entry'], x['rcept_no'])):
                prev = last.get(e['corp_code'])
                keep = prev is None or e['_entry'] >= prev + h
                e.setdefault('independent', {})
                e['independent'][f'H{h}'] = keep
                if keep:
                    last[e['corp_code']] = e['_entry']


def build(universe_dir: Path, ownership_dir: Path) -> dict:
    ses = sessions()
    cal, pit = Calendar(ses), PitTop300(load_snapshots(universe_dir))
    load_listed_shares(universe_dir)
    events, drop = cohort_events()
    for part in (title_events(pit, cal), dividend_events(pit, cal), ownership_events(pit, cal, ownership_dir)):
        events += part[0]
        drop += part[1]
    for e in events:                      # cohort rows carry no session index; every row gets one here
        e['_entry'] = ses.index(e['entrySession'])
    for pooled, (_sign, _mech, parts) in POOLED.items():
        events += [{**e, 'hypothesis': pooled, 'detail': {**e.get('detail', {}), 'component': e['hypothesis']},
                    'independent': None} for e in events if e['hypothesis'] in parts]
    cohort_flags = {(e['hypothesis'], e['rcept_no']): e['independent'] for e in events
                    if e['hypothesis'] in COHORT_MAP.values()}
    for e in events:
        if e.get('independent') is None:
            e.pop('independent', None)
    mark_independent(events)
    for e in events:                      # the sealed cohort's own independence flags are kept byte-for-byte
        if (e['hypothesis'], e['rcept_no']) in cohort_flags:
            e['independent'] = cohort_flags[(e['hypothesis'], e['rcept_no'])]
    idx = {s: i for i, s in enumerate(ses)}
    end = idx[AS_OF]
    for e in events:
        e.pop('_entry', None)
        e['ticker'] = e['stock_code'] + '.KS'
        for h in HORIZONS:
            e[f'H{h}Matured'] = idx[e['entrySession']] + h <= end
    events.sort(key=lambda e: (e['hypothesis'], e['entrySession'], e['rcept_no']))
    summary = {}
    for hyp in HYPOTHESES:
        for h in HORIZONS:
            ind = [e for e in events if e['hypothesis'] == hyp and e['independent'][f'H{h}']]
            summary[f'{hyp}_H{h}'] = describe(ind, h, ses)
    return {'events': events, 'dropped': dict(sorted(drop.items())), 'independent': summary}


def dump_events(events: list[dict], path: Path) -> None:
    payload = ''.join(json.dumps(e, ensure_ascii=False, sort_keys=True) + '\n' for e in events)
    path.write_bytes(gzip.compress(payload.encode(), 9, mtime=0))
