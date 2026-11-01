"""Owner-scoped post-outcome arithmetic on immutable saved NAVs; no replay."""
import argparse
from collections import Counter
import csv
from datetime import date
import gzip
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import statistics
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MAIN = '37f8cbf6b1c066f6b3c65235953648d17ebf2f69'
READOUT = 'e46024ca92be16b5ded9c459797a7027c1d81d23'
NAV_PATH = 'docs/weekly-decision/weekly-passive-first-v1-replay-corrected-benchmark.json'
YEAR_DAYS = 365.2425
CLASS = 'POST_OUTCOME_EXPOSED_DESCRIPTIVE_SAVED_NAV_FORENSICS_NOT_ALPHA'


def canonical(value):
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)+'\n'


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def read_sources(repo, pins):
    """No lazy fetch, price source, model, strategy engine or mutable ref reads."""
    output = {}
    for s in pins['sources']:
        if not re.fullmatch('[0-9a-f]{40}', s['commit']) or Path(s['path']).is_absolute() or '..' in Path(s['path']).parts:
            raise ValueError('INVALID_SOURCE_REF')
        raw = subprocess.check_output(['git', 'show', s['commit']+':'+s['path']], cwd=repo,
            env=dict(os.environ, GIT_NO_LAZY_FETCH='1'), stderr=subprocess.PIPE)
        if hashlib.sha256(raw).hexdigest() != s['sha256']:
            raise ValueError('SOURCE_HASH_MISMATCH: '+s['path'])
        output[s['path']] = raw
    return output


def validate_nav(candidate, benchmark):
    for series in [candidate, benchmark]:
        if not isinstance(series, list) or len(series) < 2:
            raise ValueError('INSUFFICIENT_NAV')
        previous = None
        for row in series:
            if not isinstance(row, list) or len(row) != 2:
                raise ValueError('INVALID_NAV_ROW')
            stamp, value = row
            if not isinstance(stamp, str) or date.fromisoformat(stamp).isoformat() != stamp:
                raise ValueError('INVALID_DATE')
            if previous is not None and stamp <= previous:
                raise ValueError('DUPLICATE_OR_UNORDERED_DATE')
            if not finite(value) or value <= 0:
                raise ValueError('MISSING_OR_INVALID_NAV_NOT_ZERO')
            previous = stamp
    if [x[0] for x in candidate] != [x[0] for x in benchmark]:
        raise ValueError('CALENDAR_MISMATCH_NO_INNER_JOIN')


def drawdown(dates, nav):
    peak = 0
    worst = (0.0, 0, 0)
    episodes = []
    underwater = None
    for i, value in enumerate(nav):
        if value >= nav[peak]:
            if underwater is not None:
                episodes.append((peak, i, True))
                underwater = None
            peak = i
        else:
            underwater = peak
        dd = value / nav[peak]-1
        if dd < worst[0]:
            worst = (dd, peak, i)
    if underwater is not None:
        episodes.append((underwater, len(nav)-1, False))
    depth, p, trough = worst
    recovery = next((i for i in range(trough+1, len(nav)) if nav[i] >= nav[p]), None) if depth < 0 else None
    days = lambda a, b: (date.fromisoformat(dates[b])-date.fromisoformat(dates[a])).days
    longest = max(episodes, key=lambda x: days(x[0], x[1]), default=None)
    return {'mddPct': depth*100, 'peakDate': dates[p] if depth < 0 else None,
        'troughDate': dates[trough] if depth < 0 else None,
        'recoveryDate': dates[recovery] if recovery is not None else None,
        'status': 'NO_DRAWDOWN' if depth == 0 else 'RECOVERED' if recovery is not None else 'UNRECOVERED_THROUGH_LAST_OBSERVATION',
        'peakToRecoveryDays': days(p, recovery) if recovery is not None else None,
        'peakToLastObservationDays': days(p, len(nav)-1) if depth < 0 else None,
        'longestUnderwaterEpisode': None if longest is None else {
            'peakDate': dates[longest[0]], 'endDate': dates[longest[1]],
            'calendarDays': days(longest[0], longest[1]), 'recovered': longest[2]}}


def quantile(values, p):
    ordered = sorted(values)
    if not ordered:
        return None
    point = (len(ordered)-1)*p
    lo, hi = math.floor(point), math.ceil(point)
    return ordered[lo]+(ordered[hi]-ordered[lo])*(point-lo)


def distribution(values):
    if not values:
        return {'n': 0, 'meanPp': None, 'winRatePct': None, 'lossCount': 0, 'tieCount': 0,
            'p05Pp': None, 'worst5PctMeanPp': None, 'status': 'NO_MEASUREMENTS'}
    tail = sorted(values)[:math.ceil(len(values)*.05)]
    return {'n': len(values), 'meanPp': statistics.mean(values),
        'winRatePct': 100*sum(v > 1e-10 for v in values)/len(values),
        'lossCount': sum(v < -1e-10 for v in values), 'tieCount': sum(abs(v) <= 1e-10 for v in values),
        'p05Pp': quantile(values, .05), 'worst5PctMeanPp': statistics.mean(tail),
        'tailCount': len(tail), 'status': 'MEASURED_DESCRIPTIVE_NO_INFERENTIAL_CI'}


def interval_data(a, b):
    validate_nav(a, b)
    rows = []
    for i in range(1, len(a)):
        rc, re = a[i][1]/a[i-1][1]-1, b[i][1]/b[i-1][1]-1
        rows.append({'from': a[i-1][0], 'through': a[i][0], 'index': i,
            'days': (date.fromisoformat(a[i][0])-date.fromisoformat(a[i-1][0])).days,
            'rc': rc, 're': re, 'lc': math.log1p(rc), 'le': math.log1p(re),
            'logExcess': math.log1p(rc)-math.log1p(re)})
    return rows


def summarize_intervals(rows):
    if not rows:
        raise ValueError('NO_INTERVALS')
    years = sum(r['days'] for r in rows)/YEAR_DAYS
    lc, le = math.fsum(r['lc'] for r in rows), math.fsum(r['le'] for r in rows)
    return {'from': rows[0]['from'], 'through': rows[-1]['through'], 'intervals': len(rows),
        'elapsedObservedDays': sum(r['days'] for r in rows), 'years': years,
        'candidateReturnPct': math.expm1(lc)*100, 'benchmarkReturnPct': math.expm1(le)*100,
        'excessReturnPp': (math.expm1(lc)-math.expm1(le))*100,
        'candidateCagrPct': math.expm1(lc/years)*100, 'benchmarkCagrPct': math.expm1(le/years)*100,
        'cagrGapPp': (math.expm1(lc/years)-math.expm1(le/years))*100,
        'candidateLogWealth': lc, 'benchmarkLogWealth': le, 'logExcess': lc-le,
        'relativeWealthReturnPct': math.expm1(lc-le)*100,
        'candidateWealthFromOne': math.exp(lc), 'benchmarkWealthFromOne': math.exp(le)}


def decomposition(rows):
    full = summarize_intervals(rows)
    years, rate = full['years'], len(rows)/full['years']
    ar = math.fsum(r['rc']-r['re'] for r in rows)/years*100
    jensen = math.fsum((r['lc']-r['rc'])-(r['le']-r['re']) for r in rows)/years*100
    def risk(key):
        values = [r[key] for r in rows]
        return {'observedIntervalSdPct': statistics.stdev(values)*100,
            'annualizedObservedIntervalVolatilityPct': statistics.stdev(values)*math.sqrt(rate)*100,
            'annualizedObservedDownsideRmsPct': math.sqrt(statistics.mean(min(v, 0)**2 for v in values)*rate)*100,
            'observedIntervalWorst5PctMeanReturnPct': statistics.mean(sorted(values)[:math.ceil(.05*len(values))])*100}
    return {'arithmeticIntervalActiveAnnualizedPp': ar, 'exactJensenDifferenceAnnualizedLogPoints': jensen,
        'logGrowthGapAnnualizedLogPoints': full['logExcess']/years*100,
        'identityResidualLogPoints': full['logExcess']/years*100-ar-jensen,
        'jensenShareOfLogGapPct': jensen/(full['logExcess']/years*100)*100 if abs(full['logExcess']) > 1e-12 else None,
        'geometricGapPpFromLogIdentity': (1+full['benchmarkCagrPct']/100)*math.expm1(full['logExcess']/years)*100,
        'candidateRisk': risk('rc'), 'benchmarkRisk': risk('re'),
        'effectiveObservedIntervalsPerYear': rate,
        'interpretation': 'ARITHMETIC_ACTIVE_INCLUDES_ALLOCATION_BETA_SECTOR_TIMING_COSTS_NOT_SELECTION_ALPHA; JENSEN_IS_EXACT_ALL_MOMENTS_NOT_CAUSAL_VARIANCE_ATTRIBUTION'}


def window_summary(rows):
    measured = [r for r in rows if r['status'] == 'MEASURED']
    out = {'scheduledOrigins': len(rows), 'statusCounts': dict(Counter(r['status'] for r in rows)),
        'excess': distribution([r['excessReturnPp'] for r in measured])}
    if not measured:
        return out
    er = [r['benchmarkReturnPct']/100 for r in measured]
    w = [r['relativeWealthReturnPct']/100 for r in measured]
    cross = statistics.mean(e*z for e, z in zip(er, w))*100
    relative = statistics.mean(w)*100
    out.update({'candidateMeanAbsoluteReturnPct': statistics.mean(r['candidateReturnPct'] for r in measured),
        'benchmarkMeanAbsoluteReturnPct': statistics.mean(r['benchmarkReturnPct'] for r in measured),
        'meanRelativeWealthReturnPct': relative, 'benchmarkInteractionPp': cross,
        'benchmarkRelativeWealthCovariancePp': statistics.mean((e-statistics.mean(er))*(z-statistics.mean(w)) for e, z in zip(er, w))*100,
        'meanExcessIdentityResidualPp': out['excess']['meanPp']-relative-cross,
        'identity': 'MEAN(Rc-Re) = MEAN(W) + MEAN(Re*W), W=(1+Rc)/(1+Re)-1; fractions converted to pp once'})
    # Greedy disjoint count describes time support, never independent trials.
    last_end = None
    disjoint = 0
    for r in measured:
        if last_end is None or r['start'] >= last_end:
            disjoint += 1
            last_end = r['observedEndDate']
    out['disjointCalendarBlockCount_NOT_PROOF_OF_INDEPENDENCE'] = disjoint
    return out


def annual_sensitivity(rows, annual):
    total = summarize_intervals(rows)
    ordered = sorted(annual, key=lambda x: (-x['logExcess'], x['year']))
    cases = [('LEAVE_ONE_YEAR_OUT', [x['year']]) for x in annual]
    cases += [('REMOVE_LARGEST_POSITIVE_LOG_YEARS_1', [x['year'] for x in ordered if x['logExcess'] > 0][:1]),
        ('REMOVE_LARGEST_POSITIVE_LOG_YEARS_3', [x['year'] for x in ordered if x['logExcess'] > 0][:3]),
        ('REMOVE_MOST_NEGATIVE_LOG_YEARS_1', [min(annual, key=lambda x: x['logExcess'])['year']])]
    output = []
    for label, years in cases:
        kept = [r for r in rows if r['through'][:4] not in years]
        if not kept:
            output.append({'kind': label, 'removedYears': years, 'status': 'NO_RETAINED_SUPPORT'})
            continue
        stats = summarize_intervals(kept)
        output.append({'kind': label, 'removedYears': years, 'status': 'POST_HOC_COMPRESSED_TIME_SENSITIVITY_NOT_A_TRADABLE_STRATEGY',
            'retained': stats, 'retainedLogExcessAnnualizedOnOriginalClockLogPoints': stats['logExcess']/total['years']*100})
    return output


def analyze_pair(region, strategy, packet, old, windows):
    s = packet['regions'][region]
    a, b = s['weeklyNav'][strategy], s['weeklyNav']['P0']
    rows = interval_data(a, b)
    full = summarize_intervals(rows)
    if abs(full['cagrGapPp']-old['scopes']['FULL']['cagrGapPp']) > 1e-9:
        raise ValueError('READOUT_COMMON_ENDPOINT_OR_BASIS_MISMATCH')
    annual = []
    for year in sorted({r['through'][:4] for r in rows}):
        annual.append({'year': year, **summarize_intervals([r for r in rows if r['through'].startswith(year)])})
    dates = [x[0] for x in a]
    scopes = {}
    for name in ['FIRST_EQUAL_TIME_HALF', 'SECOND_EQUAL_TIME_HALF']:
        ref = old['scopes'][name]['candidate']
        block = [r for r in rows if r['from'] >= ref['from'] and r['through'] <= ref['through']]
        scopes[name] = summarize_intervals(block)
    recent_start = max(d for d in dates if d <= '2024-01-01')
    scopes['RECENT_2024_2026'] = summarize_intervals([r for r in rows if r['from'] >= recent_start])
    split_from = old['scopes']['FIRST_EQUAL_TIME_HALF']['candidate']['through']
    split_to = old['scopes']['SECOND_EQUAL_TIME_HALF']['candidate']['from']
    boundary = summarize_intervals([r for r in rows if r['from'] >= split_from and r['through'] <= split_to])
    own = [x[1]/a[0][1] for x in a]
    etf = [x[1]/b[0][1] for x in b]
    relative = [x/y for x, y in zip(own, etf)]
    rolling = {}
    for key in ['CALENDAR_6M', 'CALENDAR_12M']:
        stored = windows['FULL/'+key]
        summary = window_summary(stored)
        ref = old['scopes']['FULL']['windows'][key]
        if summary['statusCounts'] != ref['statusCounts'] or abs(summary['excess']['meanPp']-ref['meanExcessReturnPp']) > 1e-9:
            raise ValueError('STORED_WINDOWS_MISMATCH')
        # Validate every measured row against the original common NAV, not a new endpoint rule.
        for w in stored:
            if w['status'] == 'MEASURED':
                i, j = dates.index(w['start']), dates.index(w['observedEndDate'])
                if abs((a[j][1]/a[i][1]-1)*100-w['candidateReturnPct']) > 1e-8 or abs((b[j][1]/b[i][1]-1)*100-w['benchmarkReturnPct']) > 1e-8:
                    raise ValueError('STORED_WINDOW_NAV_MISMATCH')
        rolling[key] = {'full': summary, 'priorSourceSummaryReused': ref,
            'byOriginYear': {year: window_summary([r for r in stored if r['start'].startswith(year)]) for year in sorted({r['start'][:4] for r in stored})},
            'recentOrigins2024Onward': window_summary([r for r in stored if r['start'] >= '2024-01-01'])}
    ranked = sorted(rows, key=lambda r: r['logExcess'], reverse=True)
    top3 = sorted(annual, key=lambda r: r['logExcess'], reverse=True)[:3]
    return {'id': f'{region}/{strategy}-P0', 'region': region, 'strategyId': strategy, 'benchmark': s['benchmark'],
        'studyId': old['candidateInput']['studyId'], 'notMarketC1FormalStudy': True,
        'currency': s['baseCurrency'], 'fxReturnsIncluded': s['fxReturnsIncluded'], 'frequency': 'WEEKLY_OBSERVED_NOT_DAILY',
        'evidenceClass': CLASS, 'inheritedEvidenceClass': old['candidateInput']['evidenceClass'],
        'sourceRef': {'commit': MAIN, 'path': NAV_PATH, 'candidatePointer': f'/regions/{region}/weeklyNav/{strategy}', 'benchmarkPointer': f'/regions/{region}/weeklyNav/P0'},
        'returnBasis': old['candidateInput']['returnBasis'], 'benchmarkReturnBasis': old['benchmarkInput']['returnBasis'],
        'costBasis': old['candidateInput']['costBasis'], 'sourceStatus': s['status'], 'limitations': old['candidateInput']['limitations'],
        'observations': len(a), 'intervals': len(rows), 'dateMismatchCount': 0,
        'observedGapCalendarDays': dict(sorted(Counter(r['days'] for r in rows).items())),
        'missingness': {'sourceUnionRowsDropped': 0, 'navMissingRows': 0, 'independentWeeklyScheduleVerified': False,
            'reason': 'COMMON_STORED_GRID_ONLY_NO_DAILY_CALENDAR_OR_UNRECORDED_SESSION_CERTIFICATION'},
        'full': full, 'scopes': scopes, 'halfBoundaryNotIncludedInEitherHalf': boundary,
        'decomposition': decomposition(rows),
        'candidateDrawdown': drawdown(dates, own), 'benchmarkDrawdown': drawdown(dates, etf),
        'relativeWealthDrawdown': drawdown(dates, relative), 'annualPeriods': annual,
        'annualExcessDistribution': distribution([y['excessReturnPp'] for y in annual]),
        'largestPositiveObservedIntervals': ranked[:5], 'largestNegativeObservedIntervals': ranked[-5:][::-1],
        'topThreeYears': [x['year'] for x in top3], 'topThreeYearsLogExcess': math.fsum(x['logExcess'] for x in top3),
        'topThreeShareOfFullLogExcessPct': math.fsum(x['logExcess'] for x in top3)/full['logExcess']*100 if abs(full['logExcess']) > 1e-12 else None,
        'sensitivities': annual_sensitivity(rows, annual), 'rolling': rolling,
        'perSecurityPeriodAttribution': {'status': 'UNAVAILABLE', 'reason': 'NO_MATCHING_EXECUTED_POSITION_COST_AND_LEG_PNL_HISTORY_IN_CONSUMED_PACKET; P1_DECISIONS_AND_TRUNCATED_TOPCONTRIBUTIONS_ARE_NOT_C1_C2_PERIOD_ATTRIBUTION'},
        'causalStockSelectionAlpha': None, 'inference': 'NONE_NO_P_VALUES_OR_INDEPENDENT_OOS'}, rows


def csv_output(comparisons, intervals, all_windows):
    fields = ['comparisonId','kind','status','year','from','through','calendarTargetDate','endpointLagCalendarDays','intervals',
        'candidateReturnPct','benchmarkReturnPct','excessReturnPp','relativeWealthReturnPct','logExcess',
        'candidateCagrPct','benchmarkCagrPct','cagrGapPp','currency','fxReturnsIncluded','costBasis','evidenceClass','sourceRef']
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
    writer.writeheader()
    for c in comparisons:
        base = {'comparisonId': c['id'], 'currency': c['currency'], 'fxReturnsIncluded': c['fxReturnsIncluded'],
            'costBasis': c['costBasis'], 'evidenceClass': CLASS}
        records = [('CALENDAR_YEAR_END_OBSERVATION_BIN', x) for x in c['annualPeriods']]
        records += [(k, v) for k, v in {'FULL': c['full'], **c['scopes']}.items()]
        for kind, row in records:
            writer.writerow({**base, **{k: row[k] for k in fields if k in row}, 'kind': kind, 'status': 'MEASURED',
                'sourceRef': MAIN+':'+NAV_PATH+'#'+c['sourceRef']['candidatePointer']})
        for r in intervals[c['id']]:
            writer.writerow({**base, 'kind': 'OBSERVED_WEEKLY_INTERVAL', 'status': 'MEASURED', 'from': r['from'],
                'through': r['through'], 'intervals': 1, 'candidateReturnPct': r['rc']*100, 'benchmarkReturnPct': r['re']*100,
                'excessReturnPp': (r['rc']-r['re'])*100, 'logExcess': r['logExcess'],
                'sourceRef': MAIN+':'+NAV_PATH+'#'+c['sourceRef']['candidatePointer']})
        key = 'A/'+c['id']
        for kind in ['CALENDAR_6M', 'CALENDAR_12M']:
            for w in all_windows[key]['FULL/'+kind]:
                writer.writerow({**base, 'kind': kind+'_REUSED_STORED_READOUT', 'status': w['status'],
                    'from': w['start'], 'through': w.get('observedEndDate'), 'calendarTargetDate': w.get('calendarTargetDate'),
                    **{k: w[k] for k in fields if k in w},
                    'sourceRef': READOUT+':research/economic_path_readout_v1/results.windows.json.gz#'+key+'/FULL/'+kind})
    return stream.getvalue()


def build(repo):
    pins = json.loads((HERE/'source-pins.json').read_text())
    sources = read_sources(repo, pins)
    packet = json.loads(sources[NAV_PATH])
    old = json.loads(sources['research/economic_path_readout_v1/results.json'])
    windows = json.loads(gzip.decompress(sources['research/economic_path_readout_v1/results.windows.json.gz']))
    if packet['benchmarkBasis'] != 'phase-c-corrected' or old['productionChanges'] or old['strategyReexecution']:
        raise ValueError('INVALID_STORED_SOURCE_SCOPE')
    comparisons, intervals = [], {}
    for region, strategy in [('KR','C2'),('US','C1'),('US','C2')]:
        key = f'A/{region}/{strategy}-P0'
        ref = next(c for c in old['comparisons'] if c['id'] == key)
        c, rows = analyze_pair(region, strategy, packet, ref, windows[key])
        comparisons.append(c)
        intervals[c['id']] = rows
    prior = json.loads(sources['research/c2_aggregate_evidence_v1/result-v2.json'])
    connection = json.loads(sources['research/entry_state_shadow_v1/readout_connection_v2/connection.json'])
    result = {'id': 'portfolio-edge-forensics-v1', 'operation': 'OWNER_SCOPED_SAVED_PATH_POST_HOC_DIAGNOSTIC_NO_STRATEGY_REEXECUTION',
        'evidenceClass': CLASS, 'units': {'returnCagrMdd': 'PERCENT', 'difference': 'PERCENTAGE_POINTS',
            'logExcess': 'NATURAL_LOG_RELATIVE_GROSS_WEALTH', 'annualizedLogPoints': '100_TIMES_LOG_RATE_PER_CALENDAR_YEAR',
            'nav': 'EACH_PATH_REBASED_TO_ONE_AT_FIRST_STORED_OBSERVATION'},
        'sourcePins': pins, 'generatorSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'method': {'annualBins': 'Assign each observed interval to END-date year, including boundary-straddling weeks; actual endpoints in CSV. 2013/2026 partial.',
            'recent': 'All observed intervals ending in 2024-2026, from last stored observation on/before 2024-01-01; no Jan1 interpolation.',
            'sensitivity': 'Exactly all leave-one-year-out, largest-positive1/3 and most-negative1. Ex-post diagnostic. Remove BOTH legs and their elapsed days; remaining growth operators only, no missing-week NAV or tradable strategy created.',
            'rolling': 'Reuse pinned #305 period records, validate against original NAV, add new mean-relative-wealth/benchmark-interaction decomposition. Calendar6/12m are not H126/H252.',
            'risk': 'Weekly observed interval SD/downside RMS annualized by observed intervals/elapsed years; irregular spacing retained. Not daily volatility, daily CVaR, beta or selection alpha.',
            'materiality': 'No economic threshold, alpha test, model selection or multiplicity claim; 1e-10pp only arithmetic tie tolerance.'},
        'comparisons': comparisons,
        'knownPriorNotNew': {'source': '97aa2cfe:research/c2_aggregate_evidence_v1/result-v2.json',
            'dailyOriginalStartAndCostsNotCombinedWithWeekly': prior['calendar'], 'decomposition': prior['decomposition'],
            'concentration': prior['concentration'], 'costBounds': prior['costBounds'], 'costBoundAssumptions': prior['costBoundAssumptions'], 'fallbackReplacement': prior['fallbackReplacement'],
            'benchmarkSensitivity': prior['benchmarkSensitivity'], 'calibration': prior['calibration']},
        'pr306ComparisonBarrier': {'sourceCommit': '98028fe4c8e5ea0c4829d1b1c381dbf730eccf13',
            'historicalEvidenceClass': connection['historical']['evidenceClass'],
            'status': 'NOT_POOLED_WITH_FIXED_C2; DIFFERENT_STRATEGY_COST_CURRENCY_AND_BENCHMARK_BASIS; NO_NEW_PR306_PATH_CALCULATION'},
        'qqq': {'status': 'UNAVAILABLE_IN_FIXED_C2_PACKET_SEPARATE_COMPARATOR'},
        'newStockSelectionAlphaIdentified': False, 'newSourceAdmissions': 0, 'productionChanges': False,
        'sealedReexecutions': 0, 'newStrategyPaths': 0, 'modelFits': 0, 'promotionEligible': False}
    return result, csv_output(comparisons, intervals, windows)


def report(result):
    # All displayed derived values come from build(); existing facts are labelled separately.
    kr = result['comparisons'][0]
    full, dec, recent = kr['full'], kr['decomposition'], kr['scopes']['RECENT_2024_2026']
    removed = next(x for x in kr['sensitivities'] if x['kind'].endswith('_3'))
    lines = ['# Portfolio Edge Forensics v1 — 투자위원회 독해', '',
        '**결론: INCONCLUSIVE — 저장 경로의 우위가 집중된 기간과 복리 구조는 측정했지만 종목선정 알파는 식별하지 못했다.**', '',
        '## 먼저 답할 네 질문', '',
        f"1. **어디서 앞섰나?** KR C2 전체 {full['candidateCagrPct']:.4f}% vs ETF {full['benchmarkCagrPct']:.4f}%, 차이 {full['cagrGapPp']:+.4f}pp는 기존 사실이다. 새 진단: 누적 로그 초과 {full['logExcess']:.6f} 중 상위3 연도 {', '.join(kr['topThreeYears'])}가 {kr['topThreeYearsLogExcess']:.6f} ({kr['topThreeShareOfFullLogExcessPct']:.1f}%)를 제공했다. 이 세 관측 연도 구간을 양쪽에서 제거하면 남은 로그 초과 {removed['retained']['logExcess']:.6f}, 남은 시간 기준 CAGR 차이 {removed['retained']['cagrGapPp']:+.4f}pp다. 음의 다른 기간 때문에 기여율은100%를 넘는다. 사후 민감도이지 거래 가능한 새 전략이나 OOS가 아니다.", '',
        f"2. **최근 왜 뒤졌나?** 2024~2026 관측 구간({recent['from']}~{recent['through']}) 후보 {recent['candidateReturnPct']:.4f}% vs ETF {recent['benchmarkReturnPct']:.4f}%, 차이 {recent['excessReturnPp']:+.4f}pp; 연환산 차이 {recent['cagrGapPp']:+.4f}pp. 어느 기간의 상대자산이 감소했는지는 아래 표로 입증된다. 종목·산업·베타·현금 대체·교체비용 각각이 이 감소를 얼마나 만들었는지는 matching executed leg P&L이 없어 UNKNOWN이다.", '',
        '3. **유지·개선·중단에 필요한 증거는?** 기존 C2는 연구 대조군으로 보존하며 운영 기본 ETF를 바꾸지 않는다. 유지/승격에는 권리·주주수익 적격성과 동일 노출·비용 대조, 독립 표본이 필요하다. 개선에는 먼저 비용/거래 장부나 고정 노출 통제에서 증분 원인이 식별돼야 한다. 중단은 등록된 경제적 기각 기준을 충족할 때 판단해야 하며, 이번 사후 특정 연도 제거만으로 규칙을 바꾸거나 중단하지 않는다.', '',
        '4. **다음 단 하나의 가설은?** 기존 제안 `c2-fixed-exposure-attribution-v1`만 재사용: 원래 선택·날짜·비중을 고정한 C2가 당시까지의 자료로 정한 거래 가능한 ETF+KRW 현금 노출 대조군을 넘는 비용 후 산술 기여를 남기는가? 새 arm·종목 수·최적 임계값을 만들지 않는다. 권리, 전체 주주수익, 253개 과거 종가, 교정 ETF warmup, 현금 기준을 먼저 증빙하고 독립 검토·정확한 소유자 실행 승인이 필요하다. 이번에는 실행하지 않았다.', '',
        '## 새로운 측정과 수학적 원인', '',
        f"동일 첫 관측 원금1 기준 최종자산: 후보 {full['candidateWealthFromOne']:.6f}, ETF {full['benchmarkWealthFromOne']:.6f}. 기간 {full['from']}~{full['through']}, {kr['observations']}관측/{kr['intervals']}수익 구간, KRW, NET_ALREADY_CHARGED. 초기2013-01-07 자본점은 덧붙이지 않았다.", '',
        f"정확한 항등식: 연 로그 성장률 차이 {dec['logGrowthGapAnnualizedLogPoints']:.6f} log-points = 관측 구간 산술 active {dec['arithmeticIntervalActiveAnnualizedPp']:.6f}pp + Jensen 차이 {dec['exactJensenDifferenceAnnualizedLogPoints']:.6f} log-points. Jensen 항은 로그 우위의 {dec['jensenShareOfLogGapPct']:.2f}%다. (Jensen=Σ[log(1+r)−r]; 모든 고차 모멘트 포함.) 이를 ETF 성장률 수준에서 지수변환하면 CAGR 차이 {dec['geometricGapPpFromLogIdentity']:+.4f}pp가 된다. **산술 active는 노출·산업·시점·비용을 포함하며 종목선정 알파가 아니다. Jensen도 낮은 분산의 인과 효과로 단정하지 않는다.** 기존 일별 요약의 +0.620/+1.131pp를 주간 분해의 새 결과로 재발표하지 않는다.", '',
        '| 달력 창 | 유효/예정 | 후보 평균 수익% | ETF 평균 수익% | 평균 차이pp | 평균 상대자산 증가% | ETF 결합항pp | 비중첩 시간 블록 |', '|---|---:|---:|---:|---:|---:|---:|---:|']
    for name, w in kr['rolling'].items():
        x = w['full']
        lines.append(f"|{name}|{x['excess']['n']}/{x['scheduledOrigins']}|{x['candidateMeanAbsoluteReturnPct']:.4f}|{x['benchmarkMeanAbsoluteReturnPct']:.4f}|{x['excess']['meanPp']:+.4f}|{x['meanRelativeWealthReturnPct']:+.4f}|{x['benchmarkInteractionPp']:+.4f}|{x['disjointCalendarBlockCount_NOT_PROOF_OF_INDEPENDENCE']}|")
    lines.extend(['', 'W=(1+Rc)/(1+Re)−1이면 Rc−Re=W+Re×W. 위 결합항은 mean(Re×W)다. ETF가 강한 구간의 미참여가 수익률 차이에 더 큰 금액 가중을 주므로 평균 상대자산 증가가 양수여도 평균 pp 차이는 음수일 수 있다. 전체기간 복리, 중첩 창의 동일가중 평균, 평균 상대자산 증가는 서로 다른 추정량이다. 겹친 창은 독립 시행이 아니고 비중첩 블록도 독립성을 보장하지 않는다.', '',
        '### 같은 방법의 KR/US 요약 — 모두 저장 KRW 경로', '',
        '| 경로 | 후보/ETF CAGR% | 차이pp | 연 산술 active pp | 연 Jensen log-points | 관측 연환산 SD 후보/ETF% | 관측 MDD 후보/ETF% |',
        '|---|---|---:|---:|---:|---|---|'])
    for c in result['comparisons']:
        d, f = c['decomposition'], c['full']
        lines.append(f"|{c['id']}|{f['candidateCagrPct']:.4f}/{f['benchmarkCagrPct']:.4f}|{f['cagrGapPp']:+.4f}|{d['arithmeticIntervalActiveAnnualizedPp']:+.4f}|{d['exactJensenDifferenceAnnualizedLogPoints']:+.4f}|{d['candidateRisk']['annualizedObservedIntervalVolatilityPct']:.4f}/{d['benchmarkRisk']['annualizedObservedIntervalVolatilityPct']:.4f}|{c['candidateDrawdown']['mddPct']:.4f}/{c['benchmarkDrawdown']['mddPct']:.4f}|")
    lines.extend(['', 'US는 KRW·환율 포함이며 USD 결과가 아니다. 이 표의 숫자는 source의 유효 주주수익/라이선스 승인을 뜻하지 않는다. 주식 부분 배당·교정ETF gross 분배 기준 차이와 미국 생존편향을 계승한다. NET_ALREADY_CHARGED는 원 거래비용이 이미 반영됐다는 뜻이며 배당세·누락된 기업행동까지 검증했다는 뜻이 아니다. 비용을 추가로 빼지 않았다. 종목 수는 새로 고정하지 않았고 역사3·5종목은 대조군일 뿐이다.', '',
        '## 국가별 기간·위험·열세와 민감도', '',
        '각 연도는 수익 구간의 종료 관측일로 배정한다. 연도 경계를 넘는 한 주 전체를 종료 연도에 귀속하며, 정확한12/31 가격을 만들지 않는다. 2013과2026은 부분 연도다. CSV에 실제 시작/종료와 원본 포인터를 남긴다. 기존 일별 연수익 요약과 경계가 달라 값이 같을 필요는 없다.', ''])
    for c in result['comparisons']:
        d = c['decomposition']
        lines.extend([f"### {c['id']} — {c['currency']} / FX 포함 {c['fxReturnsIncluded']}", '',
            f"Study ID: `{c['studyId']}`. C1/C2는 이 저장 CHAMPION 연구의 경로명이며 Market C1 정식 연구가 아니다.", '',
            f"{c['sourceStatus']} · {c['evidenceClass']} · {c['returnBasis']} vs {c['benchmarkReturnBasis']} · {c['costBasis']}", '',
            '| 종료 관측 연도 | 실제 시작 ~ 종료 | 후보% | ETF% | 차이pp | 로그 초과 |', '|---|---|---:|---:|---:|---:|'])
        for y in c['annualPeriods']:
            lines.append(f"|{y['year']}|{y['from']} ~ {y['through']}|{y['candidateReturnPct']:.4f}|{y['benchmarkReturnPct']:.4f}|{y['excessReturnPp']:+.4f}|{y['logExcess']:+.6f}|")
        lines.extend(['', f"연도 차이 분포: {canonical(c['annualExcessDistribution']).strip()}", '',
            '| 고정 구간 | 실제 시작 ~ 종료 | 후보 CAGR% | ETF CAGR% | 차이pp |', '|---|---|---:|---:|---:|'])
        for name, s in {'FULL': c['full'], **c['scopes']}.items():
            lines.append(f"|{name}|{s['from']} ~ {s['through']}|{s['candidateCagrPct']:.4f}|{s['benchmarkCagrPct']:.4f}|{s['cagrGapPp']:+.4f}|")
        lines.extend(['', f"반기 사이 따로 정산한1개 구간: {canonical(c['halfBoundaryNotIncludedInEitherHalf']).strip()}", '',
            f"관측 구간 위험: 후보/ETF 연환산 SD {d['candidateRisk']['annualizedObservedIntervalVolatilityPct']:.4f}/{d['benchmarkRisk']['annualizedObservedIntervalVolatilityPct']:.4f}%, downside RMS {d['candidateRisk']['annualizedObservedDownsideRmsPct']:.4f}/{d['benchmarkRisk']['annualizedObservedDownsideRmsPct']:.4f}%. 관측 빈도 연환산이며 일별 위험/CVaR로 부르지 않는다.", '',
            f"관측 MDD 후보 {c['candidateDrawdown']['mddPct']:.4f}% / ETF {c['benchmarkDrawdown']['mddPct']:.4f}%. 상대자산 최악 낙폭/회복: `{json.dumps(c['relativeWealthDrawdown'], ensure_ascii=False)}`.", '',
            '양·음 로그 기여 상위5개 관측 구간:', '', '| 방향 | 시작 ~ 종료 | 후보% | ETF% | 로그 초과 |', '|---|---|---:|---:|---:|'])
        for label, key in [('양','largestPositiveObservedIntervals'), ('음','largestNegativeObservedIntervals')]:
            for r in c[key]:
                lines.append(f"|{label}|{r['from']} ~ {r['through']}|{r['rc']*100:.4f}|{r['re']*100:.4f}|{r['logExcess']:+.6f}|")
        lines.extend(['', '사후 leave-period-out: 양쪽의 같은 관측 구간과 경과일을 제거한 성장연산자 진단. 원 시간에 현금·0수익을 삽입한 새 NAV가 아니다.', '',
            '| 제거 | 연도 | 남은 로그 초과 | 남은 시간 CAGR 차이pp |', '|---|---|---:|---:|'])
        for s in c['sensitivities']:
            if 'retained' in s:
                lines.append(f"|{s['kind']}|{','.join(s['removedYears'])}|{s['retained']['logExcess']:+.6f}|{s['retained']['cagrGapPp']:+.4f}|")
        lines.extend(['', '달력 창(기존 #305 값 재사용 + 새 결합항 귀속):', '',
            '| 창 | 예정/유효/비중첩 | 평균 차이pp | 승률% | 최하위5% 평균pp | 상태별 분모 |', '|---|---|---:|---:|---:|---|'])
        for name, w in c['rolling'].items():
            x = w['full']
            lines.append(f"|{name}|{x['scheduledOrigins']}/{x['excess']['n']}/{x['disjointCalendarBlockCount_NOT_PROOF_OF_INDEPENDENCE']}|{x['excess']['meanPp']:+.4f}|{x['excess']['winRatePct']:.4f}|{x['excess']['worst5PctMeanPp']:.4f}|{json.dumps(x['statusCounts'])}|")
        lines.extend(['', '원점 연도별/최근2024 이후 달력6/12개월 분포와 모든 누락·미성숙은 results.json/periods.csv에 보존한다. H126/H252, 일별 MDD, 일별 회복은 이 주간 경로에서 UNAVAILABLE이다.', ''])
    lines.extend(['## 가설별 증거 수준과 남은 원인', '',
        '| 원인 가설 | 수준 | 판단 |', '|---|---|---|',
        '| 몇 시기에 집중된 상대성과 | MEASURED | 연도 로그 합과 고정 제거 민감도로 정확히 확인. 사후 설명이며 재현될 국면 선택 규칙이 아님 |',
        '| 낮은 위험/복리만으로 모든 우위를 설명 | MEASURED / 인과 UNKNOWN | 정확한 Jensen 항과 산술 active를 구분; 둘 모두 존재해 전부 복리라고 단정할 수 없음. 실제 beta는 추정하지 않음 |',
        '| ETF 잔여 치환의 역할 | SUGGESTIVE / 기존 사실 | 원본 C1/C2는 같은 시작 종목 targets. 기존 #286의 C2−C1 gross/net/회전율 대비는 보존하지만 비용·drift·복리의 상호작용을 순수 ETF 기여로 오인하지 않음 |',
        '| 교체 비용 | SUGGESTIVE / 기간 귀속 UNKNOWN | 원 일별 요약에 비용drag·회전율은 있으나 같은 주간 구간의 거래별 비용 경로 없음. 2×/3× 기존 조건부 상한은 이미 계산됐으며 다시 실행하지 않음 |',
        '| 산업/개별 종목 집중 | UNKNOWN | truncated topContributions·평균 holdings 수는 기간 귀속 장부가 아님. P1의 decisions를 C2 보유로 바꾸지 않음 |',
        '| 배당/가격 정의 | SUGGESTIVE / 기존 한계 | 교정 ETF는 고정. 주식 완전 주주수익·역사 신원·권리는 승인되지 않았으며 원 sourceBasis 차이를 계승함 |', '',
        '## 재현·원본·제한', '',
        '```sh', 'python research/portfolio_edge_forensics_v1/run.py --repo .',
        'python research/portfolio_edge_forensics_v1/run.py --repo . --check',
        'python -m pytest -q research/portfolio_edge_forensics_v1/test_forensics.py', '```', '',
        '필요 Git 객체가 없으면 source-pins.json의 정확한 commit을 정상 fetch한 후 재현한다. 스크립트는 fetch하지 않는다. 산출물은 이 디렉터리의 세 파일에만 기록한다. 원본/봉인 결과/원장/가격/배분/파라미터/종목 수는 바꾸지 않는다. 공개 결과의 숫자만 읽고 새 가격·기업행동 원천은 수집하지 않는다.', '',
        '본 작업은 새 소유자 지시로 허용된 저장 결과의 사후 독해다. 기존 승인 잠금을 소비하거나 봉인 연구를 재실행하지 않았다. 주간 구간의 실제0과 미측정(null/미성숙)을 구분한다. 특정기간 제거는 source 부적격 종목을 빼거나 누락 NAV를 이어 붙이는 작업이 아니다.', '',
        '#306은 다른 strategy/currency 및 benchmark basis다. US fixed C2는 KRW/FX 포함, #306 USD/QQQ와 종합 순위를 만들지 않는다. QQQ는 이번 fixed C2 입력에서 UNAVAILABLE. 동결 연구의 기존 신호 구분력/저변동성/교체 분석은 source-pins의 이전 보고서이며 이번 발견으로 재명명하지 않는다.', '',
        '계산 원본(모든 SHA256은 source-pins.json 및 results.json에 있다):', ''])
    for s in result['sourcePins']['sources']:
        lines.append(f"- [{s['path']}](https://github.com/jaehojung1879-netizen/Investment/blob/{s['commit']}/{s['path']}) · `{s['sha256']}`")
    return '\n'.join(lines)+'\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=ROOT)
    parser.add_argument('--check', action='store_true', help='Compare outputs byte-for-byte without writing')
    args = parser.parse_args(argv)
    result, periods = build(args.repo)
    outputs = {'results.json': canonical(result), 'periods.csv': periods, 'REPORT.md': report(result)}
    for name, text in outputs.items():
        path = HERE/name
        if args.check:
            if path.read_text() != text:
                raise ValueError('REPRODUCTION_MISMATCH: '+name)
        else:
            path.write_text(text)
    print(canonical({'operation': result['operation'], 'comparisons': len(result['comparisons']),
        'newStrategyPaths': 0, 'sealedReexecutions': 0, 'output': str(HERE), 'check': args.check}).strip())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
