"""Outcome-free execution readiness for the A1/B1 historical evaluation.

Reads ONLY committed metadata: the frozen cohort, its price PRESENCE admission
(no price value), the terminal/gap split, DART dividend-decision dates, and the
committed PIT industry intervals (kr-industry-membership-foundation-v4). No
price level, return, label or model output is read; a test replaces every
engine/study entry point with a spy that raises and runs this module.

It answers: how many events would enter the registered test, which outputs are
computable now (none economic), which are SOURCE_BLOCKED and by what, and pins
the largest PIT industry per hypothesis BEFORE any outcome (the registered
industry-removal check uses it).
"""
from __future__ import annotations

import bisect
import gzip
import json
from collections import Counter, defaultdict
from pathlib import Path

from pipeline import replay_calendar

from research.corporate_event_readiness_v1.cohort import power
from . import contract as C
from . import ex_date as X

ROOT = C.REPO
DATA = C.COHORT_DIR / 'data'
INDUSTRY = ROOT / 'data/kr-industry-membership-foundation-v4/state/intervals.json.gz'
EXTENSION = Path(__file__).parent / 'data' / 'industry-extension-v1.json'
LEDGER_END = '2026-10-30'
KNOWN_LEDGER_GAPS = ('2026-09-15', '2026-09-16', '2026-10-01')   # cohort README section 10


def load_events() -> list[dict]:
    with gzip.open(DATA / 'cohort-events-v1.jsonl.gz', 'rt', encoding='utf-8') as fh:
        return [json.loads(line) for line in fh]


def industry_lookup() -> dict[str, list[dict]]:
    return json.loads(gzip.open(INDUSTRY).read())


def industry_at(intervals: dict, stock_code: str, day: str) -> tuple[str | None, str]:
    rows = intervals.get(f'{stock_code}.KS')
    if rows is None:
        return None, 'OUTSIDE_TOP120_PIT_INDUSTRY_UNIVERSE'
    for iv in rows:
        if (iv['start'] is None or iv['start'] <= day) and (iv['end'] is None or day < iv['end']):
            if iv.get('research_industry_id'):
                return iv['research_industry_id'], iv['status']
            return None, 'PIT_INDUSTRY_UNKNOWN'
    return None, 'NO_INTERVAL_COVERS_DATE'


def extension_labels() -> dict[str, dict]:
    return json.loads(EXTENSION.read_text(encoding='utf-8'))['labels']


def label_with_extension(intervals: dict, ext: dict, e: dict) -> tuple[str | None, str]:
    """PIT v4 label first; else the NOT-PIT DART-KSIC extension (kept as a separate tier)."""
    label, status = industry_at(intervals, e['stock_code'], e['signalSession'])
    if label:
        return label, 'PIT_V4'
    row = ext.get(e['corp_code'])
    if row and row.get('group') and row['kind'] == 'EXTENDED':
        return row['group'], 'NOT_PIT_EXTENSION'
    return None, status


def _hhi(counter: Counter) -> float:
    n = sum(counter.values())
    return sum((v / n) ** 2 for v in counter.values()) if n else 0.0


def build() -> dict:
    events = load_events()
    terminal = json.loads((DATA / 'terminal-economics-required-v1.json').read_text(encoding='utf-8'))
    admission = json.loads((DATA / 'price-admission-v1.json').read_text(encoding='utf-8'))
    with gzip.open(DATA / 'dividend-decisions-v1.jsonl.gz', 'rt', encoding='utf-8') as fh:
        dividends = [json.loads(line) for line in fh]
    intervals = industry_lookup()
    ext = extension_labels()
    sessions = [d.date().isoformat() for d in replay_calendar.sessions('2012-01-01', '2027-12-31', 'KR')]

    div_by_code = defaultdict(list)
    for d in dividends:
        if not d.get('amendment') and d.get('recordDate') and d.get('parseStatus') == 'PARSED':
            div_by_code[d['stock_code']].append(d)
    term_by = defaultdict(dict)
    for row in terminal['events']:
        term_by[(row['hypothesis'], row['horizon'])][row['rcept_no']] = row['classification']

    sets, pinned = {}, {}
    for hyp in ('A1', 'B1', 'A2'):
        for horizon, H in C.HORIZONS.items():
            rows = [e for e in events if e.get('hypothesis') == hyp and e.get('independent', {}).get(horizon)]
            matured = [e for e in rows if e.get(f'{horizon}Matured') and e[f'{horizon}End'] <= LEDGER_END]
            gap_hit = [e for e in matured if any(e['entrySession'] < g <= e[f'{horizon}End']
                                                 for g in KNOWN_LEDGER_GAPS)]
            terms = term_by[(hyp, horizon)]
            ind, ind_status, ind_vu = Counter(), Counter(), defaultdict(Counter)
            pit_only = 0
            for e in rows:
                label, status = label_with_extension(intervals, ext, e)
                ind[label or 'UNLABELLED'] += 1
                ind_vu['post' if e['entrySession'] >= C.VALUE_UP else 'pre'][label or 'UNLABELLED'] += 1
                ind_status[status if label is None else 'LABELLED_' + status] += 1
                pit_only += status == 'PIT_V4'
            issuers = Counter(e['corp_code'] for e in rows)
            years = Counter(e['entrySession'][:4] for e in rows)
            div = Counter()
            for e in matured:
                end = e[f'{horizon}End']
                hits = [d for d in div_by_code.get(e['stock_code'], [])
                        if e['entrySession'] < d['recordDate'] <= end]
                if not hits:
                    div['NO_PARSED_RECORD_DATE_IN_WINDOW'] += 1
                elif all(d.get('exDateTier') == 'FILING_STATED_RELATIVE_RULE_PLUS_PINNED_CALENDAR'
                         for d in hits):
                    div['ALL_IN_WINDOW_FILING_STATED_RULE'] += 1
                else:
                    div['RECORD_DATE_ONLY_EX_DATE_RULE_REQUIRED'] += 1
            mkt = Counter()
            for e in matured:
                end = e[f'{horizon}End']
                inside = []
                for d in div_by_code.get(e['stock_code'], []):
                    ex = X.market_ex_date(d['recordDate'], sessions)['exDate']
                    if ex and e['entrySession'] < ex <= end:
                        inside.append(d)
                if not inside:
                    mkt['NO_EX_DATE_IN_WINDOW'] += 1
                elif all(d.get('dpsCommonKrw') for d in inside):
                    mkt['ALL_IN_WINDOW_DIVIDENDS_DATED_AND_SIZED'] += 1
                else:
                    mkt['IN_WINDOW_DIVIDEND_WITHOUT_COMMON_DPS'] += 1
            labelled = Counter({k: v for k, v in ind.items() if k != 'UNLABELLED'})
            top = labelled.most_common(1)[0] if labelled else (None, 0)
            if horizon == C.PRIMARY_HORIZON:
                pinned[hyp] = top[0]
            span = (min(e['entrySession'] for e in matured), max(e[f'{horizon}End'] for e in matured)) \
                if matured else (None, None)
            T = (bisect.bisect_right(sessions, span[1]) - bisect.bisect_left(sessions, span[0])) if matured else 0
            sets[f'{hyp}_{horizon}'] = {
                'independentEvents': len(rows), 'issuers': len(issuers),
                'maturedByLedgerEnd': len(matured),
                'maturedWindowCrossesKnownLedgerGap': len(gap_hit),
                'pendingMaturity': len(rows) - len(matured),
                'priceWindowAdmission': admission['windowAdmission'][f'{hyp}_{horizon}']['status'],
                'terminalSplit': dict(Counter(terms.values())),
                'valueUp': {'pre': sum(e['entrySession'] < C.VALUE_UP for e in rows),
                            'post': sum(e['entrySession'] >= C.VALUE_UP for e in rows)},
                'entries2025_2026': sum(C.RECENT_CONCENTRATION[0] <= e['entrySession'] <= C.RECENT_CONCENTRATION[1]
                                        for e in rows),
                'byEntryYear': dict(sorted(years.items())),
                'issuerConcentration': {'top10Share': round(sum(v for _, v in issuers.most_common(10)) / len(rows), 4)
                                        if rows else None,
                                        'hhi': round(_hhi(issuers), 4),
                                        'maxEventsOneIssuer': max(issuers.values()) if issuers else 0},
                'pitIndustry': {'labelled': sum(labelled.values()), 'coverage': round(sum(labelled.values()) / len(rows), 4)
                                if rows else None,
                                'pitV4Only': {'labelled': pit_only,
                                              'coverage': round(pit_only / len(rows), 4) if rows else None},
                                'labelTiers': 'PIT_V4 = sealed v4 intervals; NOT_PIT_EXTENSION = current DART KSIC '
                                              'learned map (leave-one-out agreement in industry-extension-v1.json)',
                                'status': dict(ind_status), 'distribution': dict(ind.most_common()),
                                'byValueUp': {k: dict(v.most_common()) for k, v in sorted(ind_vu.items())},
                                'largestIndustry': top[0], 'largestIndustryShareOfLabelled':
                                round(top[1] / sum(labelled.values()), 4) if labelled else None},
                'dividendWindowExposureMatured': dict(div),
                'dividendWindowIfMarketRuleSealed': dict(mkt),
                'calendarSpanMatured': {'start': span[0], 'end': span[1], 'sessions': T,
                                        'effectivePrimaryBlocks': round(T / C.BOOTSTRAP['block'][horizon], 2)},
            }

    power_rows = {k: {'N': v['maturedByLedgerEnd']} for k, v in sets.items() if k[:2] in ('A1', 'B1')}
    out = {
        'studyId': C.STUDY_ID, 'contract': 'OUTCOME_FREE_EXECUTION_READINESS_V1',
        'outcomesRead': 0, 'priceValuesRead': 0,
        'inherited': C.verify_registered(),
        'sets': sets,
        'pinnedLargestPitIndustryForRemovalCheck': pinned,
        'powerOnMaturedN': power.power_table(power_rows),
        'exDateRuleCheck': ex_date_check(dividends, sessions),
        'sourceStatus': SOURCE_STATUS,
        'computability': COMPUTABILITY,
    }
    return out


def ex_date_check(dividends: list[dict], sessions: list[str]) -> dict:
    """Outcome-free: the corrected stored candidate must equal the market rule on every stated row."""
    stated = [d for d in dividends if not d.get('amendment') and d.get('exDateCandidate')]
    disagree = [d['rcept_no'] for d in stated
                if X.market_ex_date(d['recordDate'], sessions)['exDate'] != d['exDateCandidate']]
    ev = [{**e, 'marketRule': X.market_ex_date(e['recordDate'], sessions)['exDate']} for e in X.EVIDENCE]
    return {'tier': X.TIER, 'sealed': False, 'filingStatedCandidates': len(stated),
            'disagreeWithMarketRule': len(disagree), 'publicEvidence': ev,
            'evidenceReproduced': all(e['marketRule'] == e['reportedExDate'] for e in ev),
            'priorBuildRecordedFact': 'the first build was one session late on 397 of 593 stated-rule '
                                      'candidates (non-session record dates); corrected in this change'}


SOURCE_STATUS = {
    'cohortAndCalendar': 'ADMITTED (frozen cohort-events-v1 sha pinned by the registered spec; pinned XKRX calendar)',
    'stockTotalReturn': 'SOURCE_BLOCKED: KRX bars carry no dividends; DART record dates parsed for 4,732 '
                        'decisions but the ex-date rule is an unsealed Owner decision (AGENTS v2.28)',
    'benchmarkTotalReturn069500': 'SOURCE_BLOCKED for an investability claim: replay-v16 series is reproducible but '
                                  'BENCHMARK_EXTERNAL_RECONCILIATION_UNRESOLVED (AGENTS v2.47)',
    'investableKrwCash': 'SOURCE_BLOCKED: BOK policy rate is a quote, not a payoff; 153130 is a bond-ETF twin '
                         'candidate, not risk-free cash (#292 Owner review B)',
    'terminalConsideration': 'SOURCE_BLOCKED for the held terminations listed in terminalSplit',
    'ledgerSessionGaps': 'SOURCE_DEFECT: 2026-09-15/16 and 2026-10-01 missing for every ticker while '
                         'krx-prices-done.json marks them complete',
    'pitIndustryOutsideTop120': 'SOURCE_BLOCKED: v4 PIT labels cover the Top120 universe only; B1 final '
                                'support needs an industry-matched check',
    'matchingCharacteristics': 'SOURCE_BLOCKED: PIT book-to-market for Top300 issuers not admitted',
    'investorCostTaxContract': 'MODEL_COST_ONLY: dated KR tariff from pipeline/benchmark_alpha.py; '
                               'investor account/tax contract (#317) not fixed',
}

COMPUTABILITY = {
    'eligibleEventCountsMaturityIndustryDistribution': 'COMPUTED_OUTCOME_FREE',
    'mdeOnMaturedN': 'COMPUTED_CONDITIONAL_ON_UNMEASURED_SIGMA',
    'etfExcessReturn': 'NOT_EXECUTED (needs authorization) / SOURCE_BLOCKED (total-return basis)',
    'netOfCostExcess1x2x3x': 'NOT_EXECUTED / SOURCE_BLOCKED',
    'betaMatchedSelection': 'NOT_EXECUTED / SOURCE_BLOCKED (cash leg, total return)',
    'industryAdjusted': 'NOT_EXECUTED / SOURCE_BLOCKED outside Top120',
    'matchedPeerControl': 'NOT_EXECUTED / SOURCE_BLOCKED (PIT B/M)',
    'h126AndH252': 'NOT_EXECUTED',
    'intervalsEffectiveNPower': 'NOT_EXECUTED (sigma, design effect need a price read)',
    'portfolio0to5': 'NOT_REACHED (requires DEVELOPMENT_SUPPORT first)',
}


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, default=Path(__file__).with_name('execution-readiness-v1.json'))
    args = ap.parse_args()
    doc = build()
    args.out.write_text(json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=True) + '\n', encoding='utf-8')
    print(args.out)


if __name__ == '__main__':
    main()

