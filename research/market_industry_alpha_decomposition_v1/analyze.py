"""Fixed saved-result decomposition. No strategy engine, fit for trading or replay."""
import argparse
from collections import defaultdict
from datetime import date
import gzip
import hashlib
import json
import math
from pathlib import Path
import statistics
import types

import numpy as np
from scipy.stats import t as student_t

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
NAV = 'docs/weekly-decision/weekly-passive-first-v1-replay-corrected-benchmark.json'
REGIONAL = 'docs/results/regional-standalone-paths.json.gz'
HELPER = 'research/portfolio_edge_forensics_v1/run.py'
CLASS = 'POST_OUTCOME_EXPOSED_DESCRIPTIVE_NOT_IMPLEMENTABLE_ALPHA'
NAMED = ('005930.KS', '000660.KS')


def dump(value):
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)+'\n'


def fixed_helper(repo, sources):
    """Reuse exactly one hash-pinned #309 pure helper; its guarded main is never run."""
    module = types.ModuleType('fixed_saved_nav_forensics_helper')
    module.__file__ = str(repo/HELPER)
    exec(compile(sources[HELPER], module.__file__, 'exec'), vars(module))
    return module


def read_sources(repo, manifest):
    # Reuse #309's exact reader only after authenticating that one fixed code blob.
    import os
    import subprocess
    pin = next(s for s in manifest['sources'] if s['path'] == HELPER)
    if pin['commit'] != '84fe989f92d348e88243090bcad5d7a1fe891a02' or pin['sha256'] != '2b9419d92c8f0a26e387063e275afab69f1a71c0cbd3adecdb8452dca4fc04ef':
        raise ValueError('FIXED_HELPER_IDENTITY_MISMATCH')
    raw = subprocess.check_output(['git', 'show', pin['commit']+':'+HELPER], cwd=repo,
        env=dict(os.environ, GIT_NO_LAZY_FETCH='1'), stderr=subprocess.PIPE)
    if hashlib.sha256(raw).hexdigest() != pin['sha256']:
        raise ValueError('HELPER_BYTES_MISMATCH')
    f = fixed_helper(repo, {HELPER: raw})
    return f.read_sources(repo, manifest), f


def ols_hac(y, x, lag):
    """Raw-return OLS, Bartlett Newey-West sandwich, n/(n-k), pointwise t CI."""
    y, x = np.asarray(y, dtype=float), np.asarray(x, dtype=float)
    n, k = len(x), 2
    if y.shape != x.shape or y.ndim != 1 or n <= lag+k or lag < 0:
        return {'status': 'BLOCKED', 'reason': 'INSUFFICIENT_COMMON_SUPPORT_FOR_FIXED_HAC_LAG', 'n': n, 'lag': lag}
    if not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)):
        raise ValueError('NONFINITE_RETURN_NO_ROW_DROPPING')
    design = np.column_stack([np.ones(n), x])
    if np.linalg.matrix_rank(design) != 2:
        return {'status': 'BLOCKED', 'reason': 'BENCHMARK_VARIATION_UNAVAILABLE', 'n': n, 'lag': lag}
    bread = np.linalg.inv(design.T@design)
    coef = bread@design.T@y
    residual = y-design@coef
    z = design*residual[:, None]
    meat = z.T@z
    for h in range(1, lag+1):
        gamma = z[h:].T@z[:-h]
        meat += (1-h/(lag+1))*(gamma+gamma.T)
    covariance = bread@meat@bread*(n/(n-k))
    if np.min(np.diag(covariance)) < -1e-15:
        raise ValueError('NEGATIVE_HAC_VARIANCE')
    se = np.sqrt(np.maximum(np.diag(covariance), 0))  # Numerical PSD roundoff only; no beta clipping.
    critical = float(student_t.ppf(.975, n-k))
    return {'status': 'DESCRIPTIVE', 'n': n, 'lag': lag, 'lagFractionOfN': lag/n, 'beta': float(coef[1]),
        'betaSe': float(se[1]), 'betaCi95Pointwise': [float(coef[1]-critical*se[1]), float(coef[1]+critical*se[1])],
        'rawWeeklyInterceptFraction': float(coef[0]), 'rawWeeklyInterceptSeFraction': float(se[0]),
        'rawWeeklyInterceptCi95Fraction': [float(coef[0]-critical*se[0]), float(coef[0]+critical*se[0])],
        'rSquared': float(1-np.sum(residual**2)/np.sum((y-y.mean())**2)) if np.var(y) else None,
        'inference': 'POINTWISE_HAC_T_APPROXIMATION_NOT_SELECTION_ADJUSTED_NOT_CAPM_OR_OOS_ALPHA'}


def capture(rows):
    if not rows:
        return {'status': 'UNAVAILABLE', 'n': 0}
    years = sum(r['days'] for r in rows)/365.2425
    out = {'n': len(rows), 'definition': 'CONDITIONAL_ARITHMETIC_MEAN_CANDIDATE_DIVIDED_BY_BENCHMARK; REALIZED_WEEKLY_EX_POST_NOT_A_SIGNAL'}
    for name, condition in [('up', lambda x: x > 0), ('down', lambda x: x < 0), ('flat', lambda x: x == 0)]:
        block = [r for r in rows if condition(r['re'])]
        mc = statistics.mean(r['rc'] for r in block) if block else None
        mb = statistics.mean(r['re'] for r in block) if block else None
        out[name] = {'n': len(block), 'meanCandidateReturnPct': mc*100 if mc is not None else None,
            'meanEtfReturnPct': mb*100 if mb is not None else None,
            'capturePct': mc/mb*100 if mb not in (None, 0) else None,
            'annualArithmeticActiveContributionPp': math.fsum(r['rc']-r['re'] for r in block)/years*100,
            'logExcessContribution': math.fsum(r['logExcess'] for r in block),
            'reason': 'NO_CONDITIONAL_SUPPORT_OR_ZERO_ETF_MEAN' if mb in (None, 0) else None}
    return out


def regression_summary(rows, lag):
    fit = ols_hac([r['rc'] for r in rows], [r['re'] for r in rows], lag)
    if fit['status'] == 'BLOCKED':
        return fit
    rate = len(rows)/(sum(r['days'] for r in rows)/365.2425)
    years = len(rows)/rate
    active = math.fsum(r['rc']-r['re'] for r in rows)/years*100
    slope_term = (fit['beta']-1)*math.fsum(r['re'] for r in rows)/years*100
    intercept_term = fit['rawWeeklyInterceptFraction']*rate*100
    fit.update({'from': rows[0]['from'], 'through': rows[-1]['through'], 'observedIntervalsPerYear': rate,
        'annualizedArithmeticRawInterceptPp': fit['rawWeeklyInterceptFraction']*rate*100,
        'annualizedArithmeticRawInterceptCi95Pp': [v*rate*100 for v in fit['rawWeeklyInterceptCi95Fraction']],
        'correlation': float(np.corrcoef([r['rc'] for r in rows], [r['re'] for r in rows])[0, 1]),
        'annualizedObservedTrackingErrorPct': statistics.stdev(r['rc']-r['re'] for r in rows)*math.sqrt(rate)*100,
        'statisticalArithmeticActiveBridge': {'observedActiveAnnualPp': active,
            'betaSlopeTermAnnualPp': slope_term, 'rawInterceptTermAnnualPp': intercept_term,
            'meanResidualAnnualPp': active-slope_term-intercept_term,
            'identity': 'mean(Rc-Re)=a+(beta-1)*mean(Re)+mean(error); OLS_INTERCEPT_FORCES_MEAN_ERROR_ZERO_NOT_CAUSAL_SELECTION_ATTRIBUTION'}})
    return fit


def target_inventory(records, packet_digest):
    if records['sha256'] != packet_digest or len(records['regional']['KR']) != 155:
        raise ValueError('REGIONAL_TARGET_LINEAGE_MISMATCH')
    blocks = records['regional']['KR']
    dates = []
    for r in blocks:
        if r['signalDate'] >= r['date'] or r['date'] >= r['endDate']:
            raise ValueError('TARGET_DATES_INVALID')
        weights = r['weights']
        if any(not isinstance(w, (float, int)) or isinstance(w, bool) or not math.isfinite(w) or w < 0 for w in weights.values()) or sum(weights.values()) > 1:
            raise ValueError('TARGET_WEIGHTS_INVALID_NO_CLIPPING')
        dates.append(r['date'])
    if dates != sorted(set(dates)) or any(a['endDate'] != b['date'] for a, b in zip(blocks, blocks[1:])):
        raise ValueError('TARGET_CALENDAR_GAPS_OR_DUPLICATES')
    output = {}
    for year in ['2024', '2025', '2026']:
        lo = date(int(year), 1, 1)
        hi = min(date(int(year)+1, 1, 1), date.fromisoformat(blocks[-1]['endDate']))
        rows, sectors = [], defaultdict(float)
        for r in blocks:
            start, end = max(lo, date.fromisoformat(r['date'])), min(hi, date.fromisoformat(r['endDate']))
            days = (end-start).days
            if days <= 0:
                continue
            direct = sum(r['weights'].get(t, 0) for t in NAMED)
            residual = 1-sum(r['weights'].values())
            for ticker, w in r['weights'].items():
                label = r['sectorByTicker'].get(ticker) or 'Unclassified'
                sectors[label] += w*days
            rows.append({'date': r['date'], 'endDate': r['endDate'], 'clippedFrom': start.isoformat(), 'clippedThrough': end.isoformat(),
                'calendarDays': days, 'namedDirectTargetWeight': direct, 'residualEtfTargetWeight': residual,
                'weights': r['weights'], 'recordedSectorLabels_NOT_PIT_CERTIFIED': r['sectorByTicker']})
        total_days = sum(r['calendarDays'] for r in rows)
        if total_days != (hi-lo).days:
            raise ValueError('TARGET_COVERAGE_MISSING_CARRY_IN')
        output[year] = {'status': 'DESCRIPTIVE_TARGETS_NOT_EXECUTED_MARKET_VALUE_EXPOSURE', 'calendarDays': total_days,
            'overlappingBlocksIncludingCarryIn': len(rows), 'blocksWithNamedDirectTarget': sum(r['namedDirectTargetWeight'] > 0 for r in rows),
            'calendarDayWeightedNamedDirectTargetPct': sum(r['namedDirectTargetWeight']*r['calendarDays'] for r in rows)/total_days*100,
            'calendarDayWeightedResidualEtfTargetPct': sum(r['residualEtfTargetWeight']*r['calendarDays'] for r in rows)/total_days*100,
            'directStockRecordedLabelWeightsPct_NOT_EFFECTIVE_SECTOR_EXPOSURE': {k:v/total_days*100 for k, v in sectors.items()},
            'rows': rows}
    return {'byYear': output, 'fullSourceBlocks': len(blocks),
        'requiredReturnObservationCoverage': {'from': '2023-12-29', 'through': blocks[-1]['endDate'],
            'officialEtfConstituentDatesVerified': None, 'executedC2PositionPnlDatesVerified': None,
            'reason': 'NO_ADMITTED_DATED_ETF_OR_MATCHING_EXECUTED_LEG_PNL_PANEL_IN_INSPECTED_SOURCES'},
        'recentUniqueBlocks': len({r['date'] for v in output.values() for r in v['rows']}),
        'namedPairIndirectWeight': None, 'semiconductorIndustryWeight': None, 'officialEtfDatedSectorWeights': None,
        'brinsonAttribution': {'status': 'BLOCKED', 'allocationPp': None, 'selectionPp': None, 'interactionPp': None, 'costPp': None,
            'reason': 'MISSING_OFFICIAL_DATED_ETF_CONSTITUENTS_SECTOR_RETURNS_AND_MATCHING_C2_EXECUTED_HOLDINGS_LEG_PNL_COSTS'},
        'conditionalNamedPairIdentity': 'If named direct target=0, modeled pair target exposure=wETF*wETF_pair and active pair weight=(wETF-1)*wETF_pair. wETF_pair unknown; no number or causal return inferred. Other semiconductor names are not excluded by this identity.',
        'notOfficialEtfProxy': 'PIT_TOP120_CAP_WEIGHTS_ARE_NOT_KODEX200_CONSTITUENTS; RECORDED_VENDOR_SECTOR_LABELS_ARE_NOT_PIT_CERTIFIED'}


def industry_evidence(source):
    full = source['analysis']['FULL']
    features = ['REL_MOM_126', 'MEDIAN_ocfYieldProxy', 'BREADTH_ABOVE_MA_126', 'TOP1_CAP_SHARE']
    output = {}
    for f in features:
        key = f+'|CAP_WEIGHTED|H126'
        stat = full['ic'][key]
        periods = {}
        for name, years in [('SIGNAL_YEARS_2017_2024', range(2017, 2025)), ('SIGNAL_YEARS_2025_2026', range(2025, 2027))]:
            present = {str(y): stat['byYear'][str(y)] for y in years if str(y) in stat['byYear']}
            n = sum(x['dates'] for x in present.values())
            periods[name] = {'dates': n, 'meanIc': sum(x['dates']*x['mean'] for x in present.values())/n if n else None,
                'missingSignalYears': [y for y in years if str(y) not in present], 'hacSe': None,
                'reason': 'DATE_WEIGHTED_PUBLISHED_YEAR_MEANS_ONLY_NO_NEW_INFERENCE'}
        output[f] = {'sourcePointer': '/analysis/FULL/ic/'+key, 'full': stat, 'signalYearSummaries': periods,
            'originalOutcomeWindowSlices': {name: full['slices'][key+'|'+name] for name in ['PRE_2025_COMPLETE_WINDOW','TOUCHES_2025_OR_LATER']},
            'notice': 'Signal years and entry/exit outcome-window slices are distinct; no pooling with portfolio returns or independent OOS claim.'}
    return output


def industry_bridge(saved):
    output = {}
    for span, contrast in saved['dMinusA'].items():
        values = {}
        for book in ['A','D']:
            b = saved['books'][book]
            industries = b['industryContribution'][span]['byIndustry']
            gross = math.fsum(industries.values())
            expected = b['namedSecurities']['bySpan'][span]['grossContributionNavUnitsOfBook']
            cost = contrast['costNavUnits'+book]
            net = b['namedSecurities']['bySpan'][span]['netChangeNavUnitsOfBook']
            if abs(gross-expected) > 1e-9 or abs(gross-cost-net) > 1e-9:
                raise ValueError('SAVED_INDUSTRY_BRIDGE_DOES_NOT_RECONCILE')
            values[book] = {'grossNavUnits': gross, 'costNavUnits': cost, 'netChangeNavUnits': net,
                'grossMinusCostMinusNetResidual': gross-cost-net,
                'electronicsElectricalGrossNavUnits': industries.get('ELECTRONICS_ELECTRICAL')}
        dg = values['D']['grossNavUnits']-values['A']['grossNavUnits']
        dc = values['D']['costNavUnits']-values['A']['costNavUnits']
        dn = values['D']['netChangeNavUnits']-values['A']['netChangeNavUnits']
        electronics = values['D']['electronicsElectricalGrossNavUnits']-values['A']['electronicsElectricalGrossNavUnits']
        output[span] = {'books': values, 'deltaGrossNavUnits': dg, 'deltaCostNavUnits': dc, 'deltaNetNavUnits': dn,
            'electronicsElectricalDeltaGrossNavUnits': electronics,
            'electronicsShareOfGrossDifferencePct': electronics/dg*100 if dg else None,
            'unallocatedOtherIndustryGrossDifferenceNavUnits': dg-electronics, 'reconciliationResidualNavUnits': dg-dc-dn,
            'status': 'MEASURED_BRIDGE_FROM_SAVED_RECONSTRUCTED_AUDIT_NOT_BRINSON_ALLOCATION_SELECTION',
            'costByIndustry': None, 'semiconductorOnlyContribution': None}
    return output


def build(repo):
    manifest = json.loads((HERE/'source-manifest.json').read_text())
    source, f = read_sources(repo, manifest)
    packet = json.loads(source[NAV])
    if packet['benchmarkBasis'] != 'phase-c-corrected':
        raise ValueError('WRONG_BENCHMARK_BASIS')
    s = packet['regions']['KR']
    rows = f.interval_data(s['weeklyNav']['C2'], s['weeklyNav']['P0'])
    targets = target_inventory(json.loads(gzip.decompress(source[REGIONAL])), packet['regionalPathsSha256'])
    scope_rows = {'FULL': rows, 'OBSERVED_2017_2024': [r for r in rows if '2017' <= r['through'][:4] <= '2024'],
        'OBSERVED_2025_2026': [r for r in rows if r['through'][:4] >= '2025']}
    scope_rows.update({y:[r for r in rows if r['through'].startswith(y)] for y in ['2024','2025','2026']})
    scopes = {name: {'performance': f.summarize_intervals(r), 'capture': capture(r), 'logArithmeticDecomposition': f.decomposition(r),
        'primaryHac26': regression_summary(r, 26), 'sensitivityHac52': regression_summary(r, 52)} for name, r in scope_rows.items()}
    ends = list(range(104, len(rows)+1, 13))
    if ends[-1] != len(rows):
        ends.append(len(rows))
    rolling = [regression_summary(rows[e-104:e], 26) for e in ends]
    fits = [r for r in rolling if r['status'] == 'DESCRIPTIVE']
    prior = json.loads(source['research/portfolio_edge_forensics_v1/results.json'])['comparisons'][0]
    if abs(f.summarize_intervals(rows)['cagrGapPp']-prior['full']['cagrGapPp']) > 1e-9:
        raise ValueError('PR309_CONTEXT_MISMATCH')
    integrated = json.loads(source['docs/results/kr-integrated-alpha-portfolio-v1-postoutcome-completed-audit.json'])
    within = json.loads(source['docs/results/kr-stock-within-industry-anatomy-v1-result.json'])
    wi = within['analysis']['FULL']['pooledIc']
    effect_keys = ['ocfYieldProxy|RAW|LOO_INDUSTRY_MINUS_MARKET|CAP_WEIGHTED|H126',
        'ocfYieldProxy|RAW|STOCK_MINUS_LOO_INDUSTRY|CAP_WEIGHTED|H126', 'ocfYieldProxy|RAW|STOCK_MINUS_MARKET|CAP_WEIGHTED|H126']
    reliability = json.loads(source['docs/results/alpha-reliability-report.json'])
    power = json.loads(source['research/industry_ocfyield_conditional_v1/power-gate-result.json'])
    cash_proxy = json.loads(source['research/independent_audit_c2_marketc_v1/c2-beta-audit.json'])['riskFreeProxy']
    return {'id': 'market-industry-alpha-decomposition-v1', 'evidenceClass': CLASS,
        'sourceManifest': manifest, 'codeSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'studyId': s and 'weekly-passive-first-v1-replay-corrected-benchmark', 'notFormalMarketC1C2': True,
        'currency': s['baseCurrency'], 'fxReturnsIncluded': s['fxReturnsIncluded'], 'costBasis': 'NET_ALREADY_CHARGED_NO_NEW_COST_DEDUCTION',
        'returnFrequency': 'OBSERVED_WEEKLY_NOT_DAILY', 'candidateReturnBasis': prior['returnBasis'],
        'benchmarkReturnBasis': prior['benchmarkReturnBasis'], 'sourceStatus': prior['sourceStatus'],
        'inheritedSourceLimitations': prior['limitations'], 'observedIntervalGapDays': prior['observedGapCalendarDays'],
        'E1': targets, 'E2': {'scopes': scopes, 'annualCapture': {y:capture([r for r in rows if r['through'].startswith(y)]) for y in sorted({r['through'][:4] for r in rows})},
            'rolling104ObservedReturnsStep13': rolling, 'rollingBetaMin': min(r['beta'] for r in fits), 'rollingBetaMax': max(r['beta'] for r in fits),
            'reusedPR309Decomposition': prior['decomposition'], 'reusedPR309ActiveDrawdown': prior['relativeWealthDrawdown'],
            'fundedFixedExposureComparison': {'status': 'BLOCKED', 'return': None, 'reason': 'ADMITTED_MATCHING_KRW_CASH_AND_EXECUTABLE_PAST_ONLY_BETA_COST_RETURN_INPUTS_UNAVAILABLE'},
            'retainedCashEvidence': {'priorPR300Proxy': cash_proxy, 'legacyRiskFreeNavFieldExists': True,
                'admission': 'BOK_POLICY_RATE_AND_MODELED_LEGACY_RISKFREE_NAV_ARE_NOT_A_VERIFIED_INVESTABLE_KRW_CASH_RETURN'},
            'interceptInterpretation': 'RAW_RETURN_REGRESSION_NOT_CAPM_ALPHA. Constant-beta cash-funded alpha would also need -(1-beta)*cash mean and trading/funding effects; these are UNKNOWN. Full-sample beta is EX_POST, never a tradable OOS comparator.'},
        'E3': {'industryIc': industry_evidence(json.loads(source['docs/results/kr-industry-opportunity-anatomy-v1-result.json'])),
            'savedPeriodMetrics': {span: {'A': integrated['books']['A']['periodMetrics'][span]['cumulativeNetReturn'],
                'D': integrated['books']['D']['periodMetrics'][span]['cumulativeNetReturn'],
                'passive': integrated['books']['D']['periodMetrics'][span]['cumulativePassiveReturn']}
                for span in integrated['books']['D']['periodMetrics']},
            'sameCompanyOcfComponentAssociations_NOT_ADDITIVE_IC': {k:wi[k] for k in effect_keys},
            'integratedDBridge': industry_bridge(integrated), 'savedIntegratedFormalDecision': integrated['formalReported'],
            'savedDConcentration': integrated['books']['D']['concentration'], 'savedDGainConcentration': integrated['books']['D']['gainConcentration'],
            'savedDNamedSecurities': integrated['books']['D']['namedSecurities'],
            'reconstructionProvenance': integrated['reconstruction'], 'integratedSourceProvenance': integrated['provenance'],
            'independentOcfPowerGate': {'decision': power['decision'], 'support': power['support'], 'outcomeAccess': power['outcomeAccess']},
            'oldRiskDominance_NOT_C2_SPECIFIC': reliability['structuralDiagnostics']['riskDominance']},
        'literature': json.loads((HERE/'literature.json').read_text()),
        'newStrategyPaths': 0, 'sealedReexecutions': 0, 'newForecastFits': 0,
        'exPostOlsDiagnosticsRequested': len(rolling)+len(scopes)*2,
        'exPostOlsDiagnosticsComputed': len(fits)+sum(s[k]['status']=='DESCRIPTIVE' for s in scopes.values() for k in ['primaryHac26','sensitivityHac52']),
        'promotionEligible': False, 'productionChanges': False, 'stockCountPolicyChanges': False}


def report(r):
    e2 = r['E2']; full = e2['scopes']['FULL']['primaryHac26']; recent = e2['scopes']['OBSERVED_2025_2026']['performance']
    d = r['E3']['integratedDBridge']['D_full_window']; gain = r['E3']['savedDGainConcentration']; ci = full['betaCi95Pointwise']
    ocf = r['E3']['industryIc']['MEDIAN_ocfYieldProxy']['full']
    lines = ['# Market & Industry Alpha Decomposition v1', '', '## 네 질문의 답', '',
        f"1. **BLOCKED — 반도체 귀속.** KR C2의2025~2026 저장 관측 구간({recent['from']}~{recent['through']}) 수익 차이는 {recent['excessReturnPp']:+.4f}pp, 연환산 {recent['cagrGapPp']:+.4f}pp다. 최근 {r['E1']['recentUniqueBlocks']}개 고유 목표 블록에서 삼성전자·SK하이닉스 직접 목표는0이지만, 공식ETF 구성·실현 보유·기여 장부가 없어 이 열세 중 반도체에 귀속할 수 있는 pp는 **UNKNOWN(null)**이다. 검증 불가를0pp 또는0%기여로 보고하지 않는다. ELECTRONICS_ELECTRICAL도 반도체만의 분류가 아니다.", '',
        f"2. **INCONCLUSIVE — 베타·복리.** 실제 주간 수익 {full['n']}개에서 DESCRIPTIVE β={full['beta']:.4f}, HAC26 95%구간 [{ci[0]:.4f},{ci[1]:.4f}], 상관 {full['correlation']:.4f}. raw 회귀 절편은 연 산술 {full['annualizedArithmeticRawInterceptPp']:+.4f}pp, 구간 [{full['annualizedArithmeticRawInterceptCi95Pp'][0]:+.4f},{full['annualizedArithmeticRawInterceptCi95Pp'][1]:+.4f}]; 한 요인 회귀만으로 전체기간 우위가 사라지지는 않았지만 현금·누락 요인·비용·주주수익·사후 선택을 통제한 투자 알파는 아니다. #309의 Jensen 비중 {e2['reusedPR309Decomposition']['jensenShareOfLogGapPct']:.2f}%는 기존 결과로 재사용하며 새 발견으로 주장하지 않는다.", '',
        f"3. **DESCRIPTIVE — 가장 큰 양의 H126 산업 연관 후보와 한계.** 기존 산업 중앙 OCF-yield IC {ocf['mean']:+.4f}, HAC SE {ocf['hacSe']:.4f}, 유효날짜 {ocf['validDates']}/유효지지 대용 {ocf['effectiveDates']:.2f}. 다중검정·독립 OOS를 통과한 투자 알파가 아니다. 통합D의 전자·전기 보유종목은 D−A gross 기여 차이의 {d['electronicsShareOfGrossDifferencePct']:.2f}%를 설명하지만 이는 Brinson 업종배분 효과가 아니다. D 자체 gross의 {gain['shareFrom2025And2026Spans']*100:.2f}%가2025~26에 집중됐고, D는 다른 원천 기준의 passive를 전체기간 앞서지 못했다.", '',
        '4. **BLOCKED — 가장 큰 단일 증거 공백.** 동일 날짜·주주수익·비용 기준의 `C2 실현 보유/종목별 P&L + KODEX200 공식 구성·업종별 가중/수익` 결합 패널이 없다. 이 한 결합 원천이 있어야 반도체 미보유의 기회비용, 업종배분, 업종 내 선택, 상호작용을 구분할 수 있다. 목표 비중31개나 PIT Top120 proxy는 이를 대신하지 못한다. 현금 수익도 미승인이므로 실제 beta-matched 비교를 실행하지 않았다.', '',
        '## E1 — 기록된 목표와 실제 귀속의 경계', '',
        '| 연도 | carry-in 포함 블록 | 커버 일수 | 직접 삼성/SK 목표% | ETF 잔여 목표% · 일수 가중 |', '|---|---:|---:|---:|---:|']
    for y, v in r['E1']['byYear'].items():
        lines.append(f"|{y}|{v['overlappingBlocksIncludingCarryIn']}|{v['calendarDays']}|{v['calendarDayWeightedNamedDirectTargetPct']:.4f}|{v['calendarDayWeightedResidualEtfTargetPct']:.4f}|")
    lines.extend(['', f"C2 Study ID: `{r['studyId']}`. 저장 CHAMPION+잔여ETF 경로이며 정식 Market-risk C1/C2와 다른 연구다.", '',
        '이는 원래155개 원장의 재조정 목표다. 새 목표/상한을 만들지 않았으며 실제 시가 비중 평균이나 체결 확정이 아니다. carry-in을 포함하고 연도별 겹치는 블록을 독립 관측으로 더하지 않았다. 내부 sectorByTicker는 Unclassified를 보존한 원 기록 라벨이지 PIT 인증 업종이 아니다.', '',
        r['E1']['conditionalNamedPairIdentity'], '',
        'Brinson allocation / selection / interaction / cost: 모두 **UNAVAILABLE**. 공식 ETF 구성·sector return·동일 시점 실행 보유/비용이 없으므로 정합 검사를 통과한 실제 Brinson 수치는 없다. 대신 E3의 완전한 저장 산업 기여 합을 총 gross−cost=net과 대조했다. 그 부분 진단을 Brinson으로 부르지 않는다.', '',
        '## E2 — 사후 시장 민감도와 포착률', '',
        '회귀식 Rc=a+βRe는 **같은 주의 raw 저장 net수익**에 대한 사후 통계다. C2 목표의 잔여는 현금이 아니라 ETF로, 명목상 개별주+ETF 합계100%다. β0.63을 주식 보유비중63%나 현금37%로 해석하지 않는다. cash excess-return CAPM이 아니고 현금0을 채택하지 않는다. 절편을 기하 CAGR로 지수변환하지 않는다. CI는 Bartlett Newey–West, 고정26관측주 지연/52관측주 민감도, n/(n−2) 보정, pointwise t 근사다. H126/H252 거래 세션과 동일하다고 부르지 않는다. 다수 구간의 CI는 동시구간·사후 선택 보정이 아니다.', '',
        '| 구간 | n | β [HAC26 CI] | raw 절편 연산술pp [CI] | 상관 | TE 연환산% |', '|---|---:|---|---|---:|---:|'])
    for name, s in e2['scopes'].items():
        v=s['primaryHac26']
        if v['status']=='DESCRIPTIVE':
            lines.append(f"|{name}|{v['n']}|{v['beta']:.4f} [{v['betaCi95Pointwise'][0]:.4f},{v['betaCi95Pointwise'][1]:.4f}]|{v['annualizedArithmeticRawInterceptPp']:+.4f} [{v['annualizedArithmeticRawInterceptCi95Pp'][0]:+.4f},{v['annualizedArithmeticRawInterceptCi95Pp'][1]:+.4f}]|{v['correlation']:.4f}|{v['annualizedObservedTrackingErrorPct']:.4f}|")
    lines.extend(['', '| 同一期 사후 회귀 mean bridge | 산술 active pp/년 | (β−1) ETF항 pp/년 | raw 절편 pp/년 | Jensen log-points/년 | 평균 잔차 pp/년 |',
        '|---|---:|---:|---:|---:|---:|'])
    for name,s in e2['scopes'].items():
        b=s['primaryHac26']['statisticalArithmeticActiveBridge']
        lines.append(f"|{name}|{b['observedActiveAnnualPp']:+.4f}|{b['betaSlopeTermAnnualPp']:+.4f}|{b['rawInterceptTermAnnualPp']:+.4f}|{s['logArithmeticDecomposition']['exactJensenDifferenceAnnualizedLogPoints']:+.4f}|{b['meanResidualAnnualPp']:.2e}|")
    lines.extend(['', 'mean(Rc−Re)=a+(β−1)mean(Re)+mean(error). 절편이 있는 OLS는 평균 잔차를0으로 강제하므로 이 정합은 인과 설명의 완결이나 선택 알파 식별이 아니다. ETF항은 같은 표본에서 맞춘 노출 연관이며 반도체 기여로 재명명하지 않는다. 산술 pp, 연 로그 차이, 기하 CAGR은 서로 다른 단위다.', ''])
    lines.extend(['', f"104개 관측 수익/13개 간격 rolling β: {e2['rollingBetaMin']:.4f}~{e2['rollingBetaMax']:.4f}. 창은 서로 중첩되며 독립 시행이 아니다. 각 시점 CI·지원 분모·HAC52 결과는 results.json에 있다. full-sample β를 과거에 알았던 거래 비중으로 사용하지 않는다. 연간 구간 n=38~52에서 지연26의 비중이 크므로 유한표본95%포함률을 인증하지 않는 근사다. 부족한 HAC52 지원은 지연을 줄이지 않고 BLOCKED로 보존한다.", '',
        '| 종료 관측 연도 | up n / capture% | down n / capture% | up/down 연 산술 기여pp |', '|---|---|---|---|'])
    for y,c in e2['annualCapture'].items():
        show=lambda x: 'UNKNOWN' if x is None else f'{x:.2f}'
        lines.append(f"|{y}|{c['up']['n']} / {show(c['up']['capturePct'])}|{c['down']['n']} / {show(c['down']['capturePct'])}|{c['up']['annualArithmeticActiveContributionPp']:+.4f} / {c['down']['annualArithmeticActiveContributionPp']:+.4f}|")
    lines.extend(['', 'Capture=같은 조건(ETF 주간 수익>0 또는<0)의 후보 평균/ETF 평균×100. 사후 up/down이며 예측 가능한 상태가 아니다. 연도 경계를 넘는 주는 종료 관측 연도로 배정하고 실제 구간을 JSON에 보존했다. 관측 주간 TE/상대 drawdown은 일별 수치가 아니다.', '',
        f"기존 #309 상대 drawdown: {json.dumps(e2['reusedPR309ActiveDrawdown'],ensure_ascii=False)}", '',
        '실제 funded fixed-exposure 비교: **BLOCKED**. 보존 현금 자료가 아예 없는 것은 아니다. #300이 사용한 BOK 기준금리와 원장 dailyRiskFreeNav는 정책금리/모델 경로이며, 실제 투자 가능한 KRW 현금 계정의 순수익 승인이 아니다. cash·과거에 정한 실행 beta·비용 입력이 승인되지 않았다. 가격/현금 보간, fitted comparator NAV, 레버리지 clipping, 원천 교정 및 새 전략을 만들지 않았다.', '',
        '## E3 — 산업 효과와 개발 성과를 분리', '',
        '| 기존 H126 CAP IC | mean | HAC SE | 유효날짜 / 지지 대용 | PRE_2025 완료창 | 2025 이후 닿는창 |', '|---|---:|---:|---:|---|---|'])
    for name,v in r['E3']['industryIc'].items():
        a=v['full'];p=v['originalOutcomeWindowSlices']['PRE_2025_COMPLETE_WINDOW'];q=v['originalOutcomeWindowSlices']['TOUCHES_2025_OR_LATER']
        lines.append(f"|{name}|{a['mean']:+.4f}|{a['hacSe']:.4f}|{a['validDates']} / {a['effectiveDates']:.2f}|{p['mean']:+.4f} ({p['validDates']})|{q['mean']:+.4f} ({q['validDates']})|")
    lines.extend(['', '이 표는 기존 결과를 읽었고 새 산업 IC/회귀/검정을 돌리지 않았다. PRE_2025는2015~24까지 포함할 수 있어2017~24로 재명명하지 않는다. 별도의2017~24/2025~26 signal-year 날짜 가중 평균과 빠진 연도를 JSON에 명시했다. momentum·breadth의 최근 창은15~16개뿐이며2026 지원이 없다. 최근 OCF와 momentum의 요약 방향은 엇갈리지만 유효날짜가 달라 동일 표본에서의 신호 불일치로 단정할 수 없다. concentration과 momentum도 서로 다른 변수다.', '',
        '기업 OCF-yield의 같은 표본472날짜에서, 산업−시장 연관은+0.0721(SE0.0247), 기업−산업은−0.0023(SE0.0233), 기업−시장은+0.0425(SE0.0250)였다. 이는 다른 산업 중앙값337날짜 통계와 다르며, Rank IC는 가법적이지 않아 세 값을 더해 기여도로 만들지 않는다.', '',
        '| 통합D−A 저장 기여 bridge | Δgross NAV단위 | 전자·전기 Δgross | 비중% | Δcost | Δnet | 정합 잔차 |', '|---|---:|---:|---:|---:|---:|---:|'])
    for name,v in r['E3']['integratedDBridge'].items():
        lines.append(f"|{name}|{v['deltaGrossNavUnits']:+.6f}|{v['electronicsElectricalDeltaGrossNavUnits']:+.6f}|{v['electronicsShareOfGrossDifferencePct']:.2f}|{v['deltaCostNavUnits']:+.6f}|{v['deltaNetNavUnits']:+.6f}|{v['reconciliationResidualNavUnits']:.2e}|")
    lines.extend(['', '이는 같은 원금 NAV 단위의 보유종목 산업별 총기여다. Δgross−Δcost=Δnet을 정합 확인했으나 업종배분/선택/상호작용의 인과 분해는 아니다. 기간별 NAV단위 기여는 복리로 커진 후반 자본의 영향을 받으므로 기간 자체 수익률과 구분한다. 단순 sector label을 반도체 테마로 재분류하지 않았다.', '',
        '| 통합D 고정 원 구간 | D 수익% | A 수익% | 저장 passive 수익% | D 최상위업종 평균 비중% |', '|---|---:|---:|---:|---:|'])
    for name,v in r['E3']['integratedDBridge'].items():
        # Original percentage returns have a different denominator from NAV-unit contributions.
        s=r['E3']['savedPeriodMetrics'][name]
        lines.append(f"|{name}|{s['D']*100:.2f}|{s['A']*100:.2f}|{s['passive']*100:.2f}|{r['E3']['savedDConcentration'][name]['meanTopIndustryShareOfInvested']*100:.2f}|")
    lines.extend(['', '통합D 전자·전기 gross 비중59.51%, 상위5종목87.08%, 삼성+SK 직접 gross9.16%(삼성+0.531238, SK−0.235633 NAV단위)는 기존 발견이다. 두 종목을 빼도 좋아졌던 원 등록 민감도를 재실행하지 않았다. D는 두 종목보다 넓은 전자·전기 업종의 특정 시기에 집중됐다.', '',
        '통합D는2017-01-16 시작/구형 미해결 ETF 구성이고, 이번 C2는2013-01-11 저장 시작/교정 ETF다. 통합D passive20.24% vs D15.01%와 C2의14.43%를 직접 순위 비교하지 않는다. Phase D는73평가·574fit 중 다중검정 통과0, prospective 지명0, Level4 NOT_TRIGGERED였다. 누락·생존편향·요인 중복이 이 실패의 입증된 원인이라고 단정하지 않는다.', '',
        '기존 alpha-reliability/risk-dominance는 점수 분모인 downside risk와 무차별 캘리브레이션의 영향, 교체불안정을 기록했다. 해당 다른 selector/표본의 결과를 C2 주간 경로에 대한 인과 판정으로 옮기지 않았다. OCF의 conditional study는 #300 원 power gate NO_GO로 남아 있으며 재실행하지 않았다.', '',
        f"#300의 기존 **합성** power gate: 의미있는 rho에서 검출률 {r['E3']['independentOcfPowerGate']['decision']['primaryPowerAtMeaningfulRho']*100:.2f}%, 등록 floor {r['E3']['independentOcfPowerGate']['decision']['powerFloor']*100:.0f}%, size gate도 미충족. 이는 실제 OCF 성과나 이번 회귀의 검정력이 아니다. 독립 표본에서 Market+Stock 대비 Industry의 추가 순경제성은 여전히 미검증이다.", '',
        '## 문헌의 적용과 한계', ''])
    for p in r['literature']['papers']:
        lines.extend([f"- **{p['citation']}** — {p['title']}. 읽은 범위: {p['readScope']}. {p['applicationKo']} 원문/초록: {p['readUrl']} · DOI {p['doi']} · 조회 바이트 SHA256 `{p['sha256']}`"])
    lines.extend(['', '문헌은 통제·반례의 동기이며 이 개발 backtest의 검증이 아니다. 새 산업/요인/규칙 grid나 factor 재학습은 하지 않았다. 논문 전문 미확보 항목은 초록을 읽었다고 명시했고 전문을 읽었다고 주장하지 않는다. 논문 PDF/출판사 payload는 공개 저장소에 재배포하지 않았다.', '',
        '## 재현과 경계', '', '```sh', 'python research/market_industry_alpha_decomposition_v1/analyze.py --repo .',
        'python research/market_industry_alpha_decomposition_v1/analyze.py --repo . --check',
        'python -m pytest -q research/market_industry_alpha_decomposition_v1/test_analysis.py', '```', '',
        'numpy/scipy는 기존 requirements를 사용한다. 필요한 고정 Git 객체가 없으면 source-manifest.json의 exact SHA를 정상 fetch한다. CLI는 네트워크나 fetch를 수행하지 않는다. #309의 해시 검증된 순수함수만 재사용하며 그 연구 CLI/build/전략을 호출하지 않는다. 원본·워크플로·원장·보호 해시·생산 배분은 수정하지 않았다. 종목 수의 새로운3/5 상한이나 선택목표는 없다. 승인된 알파·독립 OOS·승격은 없다.', '',
        '단일 다음 증거: 위의 시점별 C2/공식ETF 결합 패널. 이번 bounded 분석은 여기서 끝내며, 새 전략/연구 실행을 승인하지 않는다.', '', '고정 원본:', ''])
    for s in r['sourceManifest']['sources']:
        lines.append(f"- [{s['path']}](https://github.com/jaehojung1879-netizen/Investment/blob/{s['commit']}/{s['path']}) · `{s['sha256']}`")
    return '\n'.join(lines)+'\n'


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo',type=Path,default=ROOT)
    p.add_argument('--check',action='store_true')
    args=p.parse_args(argv)
    r=build(args.repo)
    outputs={'results.json':dump(r),'REPORT.md':report(r)}
    for name,text in outputs.items():
        path=HERE/name
        if args.check:
            if path.read_text()!=text:
                raise ValueError('REPRODUCTION_MISMATCH:'+name)
        else:
            path.write_text(text)
    print(dump({'operation':r['id'],'sealedReexecutions':0,'newStrategyPaths':0,'check':args.check}).strip())


if __name__=='__main__':
    main()
