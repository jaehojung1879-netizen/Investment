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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='new JSON file only; defaults to stdout')
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
    result = analyze(docs['corrected'], docs['original'])
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
