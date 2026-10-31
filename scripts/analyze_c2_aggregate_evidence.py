"""Falsify claims from immutable published C2 aggregates; never replay a path.

Scope: scalar subtraction, existing splits/decomposition, and Bernoulli cost
bounds. No ledger, price, calibration, valuation or selection engine is read.
An upper bound is not a stressed replay; a positive bound proves no edge.
"""
from __future__ import annotations

import argparse
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, localcontext
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE_COMMIT = 'ee0dcca0ec9b4c43c7bc9760dc00939f3b6a6b7f'
SOURCES = {
    'corrected': ('docs/weekly-decision/weekly-passive-first-v1-replay-corrected-benchmark.json',
                  '901b3aee7d3bc06eed3fd2bd14b07a0d4ca4da23745b861a877203c48772b8d2'),
    'original': ('docs/weekly-decision/weekly-passive-first-v1-replay.json',
                 '03ed2d619f3040136f8f13744cb776142d5966f9278092d7b29b81d440e5a957'),
    'spec': ('docs/weekly-decision/weekly-passive-first-v1.json',
             'bfb25cf8799d29197ab50644a6f5d6cd9a06856db25f6a12c5de953af26b749a'),
    'basisProtocol': ('docs/weekly-decision/weekly-passive-first-v1-benchmark-basis-protocol.json',
                      'a08f92b06aab6de4959b52d0a5bc0fd2c6b21851c53deca114167898e97a8fe6'),
    'accountingCode': ('scripts/run_weekly_passive_first_replay.py',
                       '58bc5ca3f2e313baeb3b8ddbf31534f4fb0909efd69fb7460711ce0a51969592'),
}
D = Decimal


def number(row, key):
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'UNMEASURED_OR_INVALID: {key}')
    return D(str(value))


def outward(value, upper=True):
    return float(value.quantize(D('.000001'), rounding=ROUND_CEILING if upper else ROUND_FLOOR))


def cost_bounds(candidate, passive, multiplier):
    """Conditional bound for SAME fixed gross paths, weights and horizon.

    For original cost fractions 0<=ci<1, 1-k*ci <= (1-ci)**k. Thus candidate
    annual growth at k is <= (1+N)**k/(1+G)**(k-1). Passive retention is
    >= 1-k*sum(ci). Adverse endpoints allow three-decimal percent rounding and
    four-decimal year rounding. Aggregate retention also certifies k*ci<1.
    """
    if multiplier not in (2, 3):
        raise ValueError('ONLY_OWNER_REQUESTED_2X_3X_BOUNDS')
    with localcontext() as ctx:
        ctx.prec = 60
        k, eps, year_eps = D(multiplier), D('.0005'), D('.00005')
        n, g = number(candidate, 'cagrPct'), number(candidate, 'grossCagrPct')
        pg, cost = number(passive, 'grossCagrPct'), number(passive, 'totalCostPctOfNav')
        years, py = number(candidate, 'years'), number(passive, 'years')
        if (years != py or years <= year_eps or cost < 0 or n-eps <= -100
                or pg-eps <= -100 or g-eps <= -100 or g < n):
            raise ValueError('INVALID_COST_BOUND_DOMAIN')
        q_min = ((1+(n-eps)/100)/(1+(g+eps)/100)) ** (years+year_eps)
        max_cost = 1-q_min
        if k*max_cost >= 1 or k*(cost+eps)/100 >= 1:
            return {'multiplier': multiplier, 'status': 'DOMAIN_NOT_PROVEN', 'edgeUpperPp': None}
        upper = (1+(n+eps)/100)**k/(1+(g-eps)/100)**(k-1)-1
        lower = (1+(pg-eps)/100)*(1-k*(cost+eps)/100)**(1/(years-year_eps))-1
        return {'multiplier': multiplier, 'status': 'CONDITIONAL_BOUND_NOT_REPLAY',
                'candidateNetCagrUpperPct': outward(upper*100),
                'passiveNetCagrLowerPct': outward(lower*100, upper=False),
                'edgeUpperPp': outward((upper-lower)*100),
                'maxOriginalCostFractionUpper': outward(max_cost),
                'positiveEdgeRuledOutOnRecordedBasis': upper < lower}


def analyze(corrected, original):
    region, old = corrected['regions']['KR'], original['regions']['KR']
    if (region['benchmark'] != '069500.KS' or region['baseCurrency'] != 'KRW'
            or region['benchmarkDefinition'] != 'PHASE_C_RECONCILED_GROSS_ETF_TOTAL_RETURN'):
        raise ValueError('WRONG_BENCHMARK_BASIS')
    paths = region['paths']
    c2, c1, p0 = (paths[tag] for tag in ('C2', 'C1', 'P0'))
    for row in (c2, c1, p0):
        if row['available'] is not True:
            raise ValueError('INCOMPLETE_PUBLISHED_PATH')
        for key in ('startDate', 'endDate', 'sessions', 'blocks', 'years', 'initialCapitalKrw'):
            if row[key] != p0[key]:
                raise ValueError(f'NONCOMMON_CALENDAR_OR_CAPITAL: {key}')
        if row['halves']['splitDate'] != p0['halves']['splitDate']:
            raise ValueError('NONCOMMON_SPLIT')
    fields = ('cagrPct', 'maxDrawdownPct', 'annualizedVolatilityPct',
              'annualizedDownsideVolatilityPct', 'oneWayTurnoverPerYear', 'annualizedCostDragPct')
    contrasts = {tag: {key: float(number(c2, key)-number(control, key)) for key in fields}
                 for tag, control in [('C2_MINUS_PASSIVE', p0), ('C2_MINUS_C1', c1)]}
    halves = {key: float(number(c2['halves'], key)-number(p0['halves'], key))
              for key in ('firstHalfCagrPct', 'secondHalfCagrPct')}
    arithmetic = number(c2, 'arithmeticActiveReturnPpPerYear')
    residual = number(c2, 'geometricMinusArithmeticPp')
    excess = number(c2, 'excessCagrPp')
    return {
        'id': 'c2-aggregate-falsification-v1', 'evidenceClass': 'POST_OUTCOME_EXPOSED_AGGREGATE_DIAGNOSTIC',
        'verdict': 'INCONCLUSIVE', 'validatedAlpha': False, 'promotionEligible': False,
        'historicalLedgerReads': 0, 'valuationCalls': 0, 'modelFits': 0,
        'sourcePointer': '/regions/KR/paths',
        'calendar': {key: p0[key] for key in ('startDate', 'endDate', 'sessions', 'blocks', 'years')},
        'observed': {tag: {key: row[key] for key in (*fields, 'grossCagrPct', 'averageNamesHeld',
                     'averageBenchmarkWeightPct', 'nameTrades')} for tag, row in [('C2', c2), ('C1', c1), ('P0', p0)]},
        'contrastsFromRoundedPublishedScalars': contrasts,
        'contrastUnits': {key: 'one-way times/year' if key == 'oneWayTurnoverPerYear' else 'percentage points'
                          for key in fields},
        'roundingNote': 'Recorded excess uses unrounded paths; subtracting displayed three-decimal CAGR can differ by 0.001pp.',
        'recordedExcessCagrPp': float(excess),
        'decomposition': {'arithmeticActiveNetPpPerYear': float(arithmetic),
                          'geometricMinusArithmeticPp': float(residual),
                          'geometricResidualSharePct': float(residual/excess*100) if excess > 0 else None,
                          'causalStockSelectionAlpha': None,
                          'interpretation': 'Arithmetic active return includes allocation/beta/sector/timing and costs; residual is not an identified volatility contribution.'},
        'stability': {'splitDate': c2['halves']['splitDate'], 'c2MinusPassiveHalfCagrPp': halves,
                      'calendarYearExcessPp': c2['excessByCalendarYearPp'],
                      'independentEvaluation': False},
        'benchmarkSensitivity': {'originalRecordedExcessPp': old['paths']['C2']['excessCagrPp'],
                                'correctedRecordedExcessPp': float(excess),
                                'stockLegsFullyReconciled': False},
        'costBounds': [cost_bounds(c2, p0, k) for k in (2, 3)],
        'costBoundAssumptions': ['Fixed recorded decisions, gross legs and proportional cost accounting; no price impact change.',
                                'Original per-block costs nonnegative and below NAV; aggregate retention certifies scaled positivity.',
                                'Bounds include adverse source rounding; they are not exact stressed NAV, MDD, tax or investor-return results.'],
        'calibration': region_calibration(corrected),
        'concentration': {'averageNamesHeld': c2['averageNamesHeld'],
                          'decisionBlockMeanIndexTargetPct': c2['averageBenchmarkWeightPct'],
                          'topContributionsTruncated': c2['topContributions'],
                          'leaveOneOutSensitivity': None},
        'notAuthorizedByOriginalOneShotProtocol': ['new matched-beta or selection-null path',
                                                  'exact 2x/3x cost replay', 'stock deletion/concentration replay'],
        'nextExperiment': 'Separate fixed-C2 common-calendar passive-exposure attribution; source admission and new exact-version authorization required before paths/labels are used.',
    }


def region_calibration(report):
    ordering = report['finalAnchorCalibration']['regions']['KR']['ordering']
    return {'pointer': '/finalAnchorCalibration/regions/KR/ordering',
            'orderingEstablished': ordering['established'], 'rankICTStat': ordering['rankICTStat'],
            'topMinusBottomTStat': ordering['topMinusBottomTStat'],
            'directC2ConvictionRankingTest': False}


def calendar_context(candidate, passive):
    """Post-hoc signs of published annual aggregates, never a trading signal."""
    cy, py, excess = (candidate['calendarYearReturnPct'], passive['calendarYearReturnPct'],
                      candidate['excessByCalendarYearPp'])
    first, last = int(passive['startDate'][:4]), int(passive['endDate'][:4])
    if set(cy) != set(py) or set(py) != set(excess) or set(py) != {str(y) for y in range(first, last+1)}:
        raise ValueError('NONCOMMON_OR_MISSING_CALENDAR_YEARS')
    rows = []
    eps = D('.0005')  # Source annual returns are rounded to three decimal percentage points.
    for year in sorted(py):
        stock, bench, active = number(cy, year), number(py, year), number(excess, year)
        if abs(stock-bench-active) > 3*eps:
            raise ValueError('INCONSISTENT_PUBLISHED_ANNUAL_EXCESS')
        direction = 'UP' if bench > eps else 'DOWN' if bench < -eps else 'UNDETERMINED'
        rows.append({'year': year, 'passiveReturnPct': float(bench), 'c2ReturnPct': float(stock),
                     'recordedExcessPp': float(active), 'benchmarkDirection': direction,
                     # The source rounds the candidate's annual return BEFORE
                     # subtracting the raw passive return, then rounds again.
                     'outperformed': True if active > 2*eps else False if active < -2*eps else None,
                     'isWindowBookendYear': int(year) in {first, last}})

    def counts(selected):
        return {direction: {'years': len(group := [r for r in selected if r['benchmarkDirection'] == direction]),
                            'wins': sum(r['outperformed'] is True for r in group),
                            'losses': sum(r['outperformed'] is False for r in group),
                            'unresolvedByRounding': sum(r['outperformed'] is None for r in group)}
                for direction in ('UP', 'DOWN', 'UNDETERMINED')}
    return {'sourcePointers': ['/regions/KR/paths/P0/calendarYearReturnPct',
                               '/regions/KR/paths/C2/calendarYearReturnPct',
                               '/regions/KR/paths/C2/excessByCalendarYearPp'],
            'rows': rows, 'allYears': counts(rows),
            'interiorYearsExcludingWindowBookends': counts([r for r in rows if not r['isWindowBookendYear']]),
            'directionIsExPostOutcomeContext': True, 'betaMatchedSelectionAlpha': None,
            'costBasis': 'PUBLISHED_1X_MODELED_COSTS_ONLY',
            'interpretation': 'Post-hoc association only. Realized window direction is not known at selection time; these counts prove neither timing skill nor a causal beta explanation. Bookend windows are not full calendar years.'}


def exposure_bound(candidate, passive):
    """Cauchy-Schwarz bound, not a fitted beta or a risk-free excess-return beta."""
    sigma, benchmark = number(candidate, 'annualizedVolatilityPct'), number(passive, 'annualizedVolatilityPct')
    eps = D('.0005')
    if sigma < 0 or benchmark < 0:
        raise ValueError('INVALID_VOLATILITY')
    bound = (sigma+eps)/(benchmark-eps) if benchmark > eps else None
    return {'definition': 'ABS_SAMPLE_RAW_DAILY_NET_RETURN_BETA_LE_SIGMA_RATIO',
            'absoluteBetaUpperBound': outward(bound) if bound is not None else None,
            'unitBetaFeasibleOnRecordedBasis': bound >= 1 if bound is not None else None,
            'estimatedBeta': None, 'selectionAlpha': None,
            'sourcePointer': '/regions/KR/paths/{C2,P0}/annualizedVolatilityPct',
            'interpretation': 'Common daily net-return calendar and identical sample-volatility convention. Includes adverse volatility rounding. A bound is not an estimated beta, cash-adjusted beta, timing skill or causal selection attribution.'}


def extended_analysis(corrected, original):
    result = analyze(corrected, original)
    result['id'] = 'c2-aggregate-falsification-v2'
    paths = corrected['regions']['KR']['paths']
    c2, c1 = paths['C2'], paths['C1']
    result['publishedCalendarContext'] = calendar_context(c2, paths['P0'])
    result['exposureBound'] = exposure_bound(c2, paths['P0'])
    result['fallbackReplacement'] = {
        'arithmeticActiveNetDifferencePpPerYear': float(number(c2, 'arithmeticActiveReturnPpPerYear')-number(c1, 'arithmeticActiveReturnPpPerYear')),
        'geometricMinusArithmeticDifferencePp': float(number(c2, 'geometricMinusArithmeticPp')-number(c1, 'geometricMinusArithmeticPp')),
        'isolatedGrossResidualAssetEffect': None, 'causalSelectionEffect': None,
        'interpretation': 'Same recorded starting stock targets; replacement of residual cash with ETF includes cost/drift/compounding interactions. It is not new stock selection.'}
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='new JSON file only; defaults to stdout')
    parser.add_argument('--calendar-context', action='store_true', help='opt-in aggregate diagnostic v2; v1/default remains unchanged')
    args = parser.parse_args(argv)
    docs, provenance = {}, {}
    for key, (path, digest) in SOURCES.items():
        data = subprocess.check_output(['git', 'show', f'{SOURCE_COMMIT}:{path}'], cwd=ROOT,
                                       env={**os.environ, 'GIT_NO_LAZY_FETCH': '1'})
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError(f'SOURCE_HASH_MISMATCH: {key}')
        provenance[key] = {'commit': SOURCE_COMMIT, 'path': path, 'sha256': digest}
        if key != 'accountingCode':
            docs[key] = json.loads(data)
    if (docs['corrected']['specSha256'] != SOURCES['spec'][1]
            or docs['corrected']['benchmarkBasisProtocolSha256'] != SOURCES['basisProtocol'][1]):
        raise ValueError('SOURCE_CONTRACT_MISMATCH')
    result = (extended_analysis if args.calendar_context else analyze)(docs['corrected'], docs['original'])
    result['sources'] = provenance
    text = json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False)+'\n'
    if args.output:
        with args.output.open('x', encoding='utf-8') as stream:
            stream.write(text)
    else:
        print(text, end='')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
