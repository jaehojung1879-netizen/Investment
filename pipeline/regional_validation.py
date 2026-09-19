"""Read-only attribution of a frozen regional challenger; no selection/promotion.

Two uncertainty estimands are explicitly separate: mean paired block-metric
contrasts and paired resampling of the full net daily path. Costs in resampled
blocks remain the costs actually incurred on the chronological original path.
"""
from __future__ import annotations

from copy import deepcopy
import math
from types import MappingProxyType

import numpy as np

from . import portfolio_validation as PV
from . import regional_rotation as RR
from . import replay_valuation as RV

VERSION = 'regional-rotation-v1'
BASELINE = MappingProxyType(dict(lookback_days=252, temperature=0.05, floor=0.15))
BOOTSTRAP_SEED = 11
BOOTSTRAP_DRAWS = 2000
METRICS = ('cagrPct', 'annualizedExcessPct', 'sharpe', 'sortino', 'mddPct', 'calmar', 'cvar95Pct')
SENSITIVITIES = (('lookback-126', 'lookback_days', 126), ('lookback-504', 'lookback_days', 504),
                 ('floor-0.10', 'floor', .10), ('floor-0.25', 'floor', .25),
                 ('temperature-0.03', 'temperature', .03), ('temperature-0.10', 'temperature', .10))
PORTFOLIOS = ('Combined CHAMPION', 'Static 50/50', 'Dynamic Regional Rotation v1')
COMPARISONS = (('diversificationRegionalReranking', PORTFOLIOS[1], PORTFOLIOS[0]),
               ('dynamicTiming', PORTFOLIOS[2], PORTFOLIOS[1]),
               ('totalArchitecture', PORTFOLIOS[2], PORTFOLIOS[0]))


def freeze_manifest():
    if dict(BASELINE) != dict(lookback_days=RR.DEFAULT_LOOKBACK_DAYS,
                              temperature=RR.DEFAULT_TEMPERATURE, floor=RR.DEFAULT_FLOOR):
        raise ValueError('regional defaults drifted from frozen v1; do not silently redefine v1')
    return dict(id=VERSION, status='CHALLENGER', parameters=dict(BASELINE),
                lookbackUnit='CALENDAR_DAYS', score='MEAN_GROSS_EXCESS_OF_MATURED_21_COMMON_SESSION_BLOCKS',
                maturityRule='windowStart <= endDate < decisionDate',
                decisionRule='FIRST_FIXED_EVALUATION_ANCHOR_IN_EACH_CALENDAR_QUARTER',
                effectiveRule='DECISION_DATE_INCLUSIVE', coldStart='EQUAL_WEIGHT_IF_ANY_SCORE_MISSING',
                weightRule='SOFTMAX_THEN_FLOOR_WITH_SIX_DECIMAL_TARGETS',
                prospectiveStatus='NOT_YET_COLLECTED', promotionEligible=False, liveValidated=False)


def validate_rows(rows):
    seen = set()
    for row in rows:
        date, end = row['date'], row['endDate']
        if date in seen:
            raise ValueError('duplicate block date: ' + date)
        seen.add(date)
        dates = row.get('dailyDates', [])
        if len(dates) < 2 or dates[0] != date or dates[-1] != end or dates != sorted(set(dates)):
            raise ValueError('missing, duplicate, unsorted or misaligned daily dates: ' + date)
        for key in ('dailyGrossNav', 'dailyBenchmarkNav', 'dailyRiskFreeNav'):
            nav = np.asarray(row.get(key, []), dtype=float)
            if len(nav) != len(dates) or not np.isfinite(nav).all() or np.any(nav <= 0):
                raise ValueError('invalid or missing daily NAV: ' + key)
            if not math.isclose(nav[0], 1.0, abs_tol=1e-10):
                raise ValueError('daily NAV must start at one')
        for field, key in (('grossReturn', 'dailyGrossNav'), ('benchmarkReturn', 'dailyBenchmarkNav')):
            if not math.isclose(row[field], row[key][-1] - 1, abs_tol=1e-9):
                raise ValueError('endpoint/daily path mismatch: ' + field)


def matched_blocks(paths, calendar):
    """Exact (anchor,end) intersection; disclose all omissions, never impute."""
    expected = {(r['date'], r['endDate']) for r in calendar}
    indexes = {}
    for name, rows in paths.items():
        validate_rows(rows)
        indexes[name] = {(r['date'], r['endDate']): r for r in rows}
        if set(indexes[name]) - expected:
            raise ValueError('path contains a non-calendar block: ' + name)
    keys = sorted(expected.intersection(*(set(i) for i in indexes.values())))
    for key in keys:
        aligned = [index[key] for index in indexes.values()]
        if any(r['dailyDates'] != aligned[0]['dailyDates'] or
               r['dailyRiskFreeNav'] != aligned[0]['dailyRiskFreeNav'] for r in aligned):
            raise ValueError('paired paths have different dates or risk-free series')
    return ({name: [index[k] for k in keys] for name, index in indexes.items()},
            dict(expectedBlocks=len(expected), pairedBlocks=len(keys),
                 matchedBlocks=[dict(date=a, endDate=b) for a, b in keys],
                 missingByPortfolio={name: [dict(date=a, endDate=b) for a,b in sorted(expected-set(index))]
                                     for name,index in indexes.items()},
                 complete=len(keys) == len(expected)))


def metrics(rows, cfg_pf):
    """All A/B/C and per-block metrics use the production path calculator.

    Deep copies prevent its cost annotation from mutating sealed rows or callers.
    No daily-data fallback to the obsolete endpoint lower bound is permitted.
    """
    validate_rows(rows)
    copied = deepcopy(rows)
    result = PV._path_metrics(copied, PV.HEADLINE_HORIZON, cfg_pf,
                              only_dates=[r['date'] for r in copied])
    if not result.get('available'):
        return result
    result['riskFreeStatus'] = 'AVAILABLE_POLICY_RATE_PROXY'
    result['calmar'] = (result['cagrPct'] / abs(result['mddPct']) if result['mddPct'] < 0 else None)
    result['metricUnavailableReasons'] = {}
    for key, reason in (('sharpe', 'INSUFFICIENT_OR_ZERO_VARIANCE_DAILY_RF_EXCESS'),
                        ('sortino', 'NO_NEGATIVE_DAILY_RF_EXCESS'), ('calmar', 'NO_DRAWDOWN')):
        if result[key] is None:
            result['metricUnavailableReasons'][key] = reason
    result['sumTransactionCostPct'] = sum(r['transactionCost'] for r in copied) * 100
    result['averageCashPct'] = np.mean([1-sum(r['weights'].values()) for r in copied]) * 100
    result['averageEquityPct'] = 100-result['averageCashPct']
    result['costAdjustedCagrPct'] = result['cagrPct']
    result['grossCagrPct'] = (np.prod([1+r['grossReturn'] for r in copied]) ** (1/result['calendarYears'])-1)*100
    result['costDragCagrPp'] = result['grossCagrPct'] - result['cagrPct']
    return result


def _net_blocks(rows, cfg_pf):
    copied = deepcopy(rows)
    # Costs are those from the original chronological strategy, not from
    # impossible transitions between randomly sampled historical dates.
    PV._path_metrics(copied, PV.HEADLINE_HORIZON, cfg_pf, only_dates=[r['date'] for r in copied])
    blocks = []
    for row in copied:
        values = []
        for key in ('dailyGrossNav', 'dailyBenchmarkNav', 'dailyRiskFreeNav'):
            nav = np.array(row[key], dtype=float)
            returns = nav[1:] / nav[:-1] - 1
            if key == 'dailyGrossNav':
                returns[0] = (1+returns[0]) * (1-row['transactionCost']) - 1
            values.append(returns)
        blocks.append((values, RV.span_years(row['date'], row['endDate']), row['transactionCost']))
    return blocks


def _resampled_statistics(blocks, indices):
    """Numeric counterpart of RV.daily_statistics, parity-tested against it.

    Real block durations/RF/entry-cost events travel with each paired block.
    No fake calendar dates, daily IID sampling, or recalibrated weights.
    """
    chosen = [blocks[i] for i in indices]
    returns, benchmark, risk_free = [np.concatenate([b[0][j] for b in chosen]) for j in range(3)]
    years = sum(b[1] for b in chosen)
    periods = len(returns)/years
    growth = np.concatenate(([1.0], np.cumprod(1+returns)))
    peak = np.maximum.accumulate(growth)
    mdd = float(np.min(growth/peak-1))*100
    pos = 0
    for values, _, cost in chosen:
        mdd = min(mdd, (growth[pos]*(1-cost)/peak[pos]-1)*100)
        pos += len(values[0])
    cagr = (growth[-1] ** (1/years)-1)*100
    bench_cagr = (np.prod(1+benchmark) ** (1/years)-1)*100
    over_rf = returns-risk_free
    sd = np.std(over_rf, ddof=1) if len(over_rf)>1 else 0
    downside = np.sqrt(np.mean(np.minimum(over_rf, 0)**2))
    return dict(cagrPct=cagr, annualizedExcessPct=cagr-bench_cagr,
                sharpe=float(over_rf.mean()/sd*np.sqrt(periods)) if sd>0 else None,
                sortino=float(over_rf.mean()/downside*np.sqrt(periods)) if downside>0 else None,
                mddPct=mdd, calmar=cagr/abs(mdd) if mdd<0 else None,
                cvar95Pct=float(np.sort(returns)[:max(1,math.ceil(len(returns)*.05))].mean()*100))


def _interval(point, values, n, seed, draws):
    valid = [x for x in values if x is not None and math.isfinite(x)]
    # Do not silently condition on only the replicates with a defined ratio.
    available = n >= 2 and len(valid) == draws and point is not None
    ci = [float(x) for x in np.percentile(valid, [2.5,97.5])] if available else [None,None]
    return dict(pointEstimate=point, bootstrapMean=float(np.mean(valid)) if available else None,
                ci95=ci, pairedBlocks=n, seed=seed, samples=draws, validSamples=len(valid),
                reason=None if available else 'INSUFFICIENT_PAIRS_OR_UNDEFINED_METRIC_IN_RESAMPLES',
                evidence=('historical evidence is inconclusive' if not available or ci[0]<=0<=ci[1]
                          else 'historical interval excludes zero; prospective evidence still required'))


def paired_bootstrap(challenger, control, cfg_pf, *, draws=BOOTSTRAP_DRAWS, seed=BOOTSTRAP_SEED):
    if draws < 2:
        raise ValueError('bootstrap requires at least two draws')
    if [(r['date'],r['endDate']) for r in challenger] != [(r['date'],r['endDate']) for r in control]:
        raise ValueError('bootstrap requires exact paired blocks')
    n = len(control)
    if not n:
        return dict(available=False, reason='NO_PAIRED_BLOCKS')
    left, right = metrics(challenger, cfg_pf), metrics(control, cfg_pf)
    lb, rb = _net_blocks(challenger,cfg_pf), _net_blocks(control,cfg_pf)
    # The same index vector samples both portfolios and every metric.
    idx = np.random.default_rng(seed).integers(0,n,size=(draws,n))
    full = {k: [] for k in METRICS}
    for sample in idx:
        a,b = _resampled_statistics(lb,sample), _resampled_statistics(rb,sample)
        for key in METRICS:
            full[key].append(a[key]-b[key] if a[key] is not None and b[key] is not None else None)
    delta = {k: left.get(k)-right.get(k) if left.get(k) is not None and right.get(k) is not None else None
             for k in METRICS}
    # User-requested literal block-metric differences. Charge original costs,
    # not a new initial purchase every time a block is inspected in isolation.
    per_block = {k: [] for k in METRICS}
    for i in range(n):
        a,b = _resampled_statistics(lb,[i]),_resampled_statistics(rb,[i])
        for key in METRICS:
            per_block[key].append(a[key]-b[key] if a[key] is not None and b[key] is not None else None)
    block_ci = {}
    for key, values in per_block.items():
        if any(v is None for v in values):
            block_ci[key] = _interval(None,[],n,seed,draws)
        else:
            array = np.array(values)
            block_ci[key] = _interval(float(array.mean()),array[idx].mean(axis=1).tolist(),n,seed,draws)
    interactions = {key:left.get(key)-right.get(key)
                    if left.get(key) is not None and right.get(key) is not None else None
                    for key in ('averageCashPct','averageEquityPct','benchmarkCagrPct',
                                'averageTurnoverPct','sumTransactionCostPct','costDragCagrPp')}
    return dict(available=True, delta=delta, cashAndCostDeltas=interactions,
                mddDescription=(f'{delta["mddPct"]:+.3f}pp '+ ('shallower drawdown' if delta['mddPct']>0 else 'deeper drawdown')
                                if delta['mddPct'] is not None else 'full path unavailable'),
                pathDifferenceCI={k:_interval(delta[k],full[k],n,seed,draws) for k in METRICS},
                meanPairedBlockMetricDifferenceCI=block_ci,
                method='PAIRED_WHOLE_EVALUATION_BLOCK_PERCENTILE_BOOTSTRAP',
                estimandNote='Path deltas recompute nonlinear statistics on jointly resampled net daily blocks. '
                'Mean block-metric deltas are a separate estimand, not the full-path delta. '
                'Costs and allocations are fixed at their original chronological values. '
                'Blocks are treated as exchangeable; serial regime dependence is not removed.')


def build_validation(regional, combined, calendar, cfg_pf, *, draws=BOOTSTRAP_DRAWS, seed=BOOTSTRAP_SEED):
    freeze = freeze_manifest()
    dates = [r['date'] for r in calendar]
    schedule = RR.regional_weight_schedule(regional, **BASELINE, evaluation_dates=dates)
    static = RR.static_blend(regional)
    dynamic = RR.apply_schedule(regional, schedule)
    paths, matching = matched_blocks(dict(zip(PORTFOLIOS, (combined,static,dynamic))),calendar)
    summaries = {name:metrics(rows,cfg_pf) for name,rows in paths.items()}
    # Missing intervals are not compressed into an investable historical NAV.
    if not matching['complete']:
        summaries = {name:dict(available=False, reason='MISSING_SCHEDULED_BLOCKS',
                               matchedBlockMetrics=m) for name,m in summaries.items()}
    comparisons = {key:paired_bootstrap(paths[a],paths[b],cfg_pf,draws=draws,seed=seed)
                   for key,a,b in COMPARISONS}
    robustness = []
    for label, field, value in (('baseline',None,None),)+SENSITIVITIES:
        params = dict(BASELINE)
        if field:
            params[field] = value
        variant_schedule = RR.regional_weight_schedule(regional,**params,evaluation_dates=dates)
        variant = RR.apply_schedule(regional,variant_schedule)
        lookup = {(r['date'],r['endDate']):r for r in variant}
        selected = [lookup[(r['date'],r['endDate'])] for r in paths[PORTFOLIOS[1]]]
        m = metrics(selected,cfg_pf)
        reference = metrics(paths[PORTFOLIOS[1]],cfg_pf)
        weights = [r['weights']['US'] for r in variant_schedule]
        robustness.append(dict(id=label,parameters=params,metrics=m,
                               dynamicMinusStatic={k:m.get(k)-reference[k] if m.get(k) is not None and reference.get(k) is not None else None
                                                   for k in METRICS},
                               minUsWeight=min(weights),maxUsWeight=max(weights),
                               maxQuarterlyWeightChange=max((abs(a-b) for a,b in zip(weights,weights[1:])),default=0),
                               role='STABILITY_DIAGNOSTIC_NOT_MODEL_SELECTION'))
    changes = [r['dynamicMinusStatic'] for r in robustness]
    stability = {key:dict(positive=sum(bool(r[key] is not None and r[key]>0) for r in changes),
                         negative=sum(bool(r[key] is not None and r[key]<0) for r in changes),
                         zero=sum(bool(r[key]==0) for r in changes), variants=len(changes),
                         minDelta=min((r[key] for r in changes if r[key] is not None), default=None),
                         maxDelta=max((r[key] for r in changes if r[key] is not None), default=None))
                 for key in ('cagrPct','mddPct','sharpe')}
    # Scalar/diagnostic report; daily evidence remains in the hashed standalone
    # checkpoint and sealed CHAMPION. Do not duplicate eight full NAV arrays.
    for summary in summaries.values():
        for key in ('nav','rolling3YAnnualizedExcess','rolling5YAnnualizedExcess'):
            summary.pop(key,None)
    for row in robustness:
        for key in ('nav','rolling3YAnnualizedExcess','rolling5YAnnualizedExcess'):
            row['metrics'].pop(key,None)
    return dict(reportVersion='regional-validation-v1', robustnessStability=stability, freeze=freeze, matching=matching,
                baselineComparison=summaries, comparisons=comparisons, robustness=robustness,
                rotationSchedule=schedule, historicalStatus='HISTORICAL_ONLY_NO_PROMOTION',
                interpretation='Dynamic minus static isolates allocation-rule changes on identical sleeves, '
                'including induced cash, benchmark and trading-cost changes. Static minus combined bundles '
                'independent reranking, regional diversification, concentration and cash/risk-budget effects; '
                'these components are not separately identified by three portfolios.',
                sharpeRepair='The old blend discarded dailyDates/dailyGrossNav/dailyBenchmarkNav/dailyRiskFreeNav '
                'and terminal holdings, falling back to legacy endpoint metrics with Sharpe/Sortino=None. '
                'Daily NAV and drifted terminal holdings now survive blending; all portfolios use PV._path_metrics.',
                limitations=['Historical post-design replay, not prospective evidence.',
                             'No parameter optimization or automatic promotion.',
                             'Individual portfolio benchmarks vary with regional equity and cash weights.',
                             'IID block bootstrap may understate persistent-regime uncertainty.',
                             'OFAT results include previously observed history and are stability diagnostics only.'])


def markdown_report(report):
    def fmt(x):
        return 'N/A' if x is None else f'{x:+.3f}'
    lines = ['# Regional Rotation v1 attribution', '',
             '**CHALLENGER — historical evidence only; no production promotion.**', '',
             f"Input: `{report['inputSnapshot']['sha256']}` through {report['inputSnapshot']['through']}.",
             'Frozen baseline: 252 **calendar** days; temperature 0.05; floor 0.15; quarterly fixed anchors.',
             'Only outcomes with windowStart ≤ endDate < decisionDate enter each trailing score.', '',
             '## Baseline comparison', '',
             '| Portfolio | CAGR % | Excess pp/yr | Sharpe | Sortino | MDD % | Calmar | CVaR daily % | Vol %/yr | Turnover % | Cash % | Sum cost % |',
             '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    fields = METRICS+('annualizedRealizedVolPct','averageTurnoverPct','averageCashPct','sumTransactionCostPct')
    for name,m in report['baselineComparison'].items():
        lines.append('| '+name+' | '+' | '.join(fmt(m.get(k)) for k in fields)+' |')
    for name,m in report['baselineComparison'].items():
        for key,reason in m.get('metricUnavailableReasons',{}).items():
            lines.append(f'{name} / {key}: {reason}')
    lines += ['', 'CAGR is cost-adjusted. Excess = portfolio CAGR minus its own equity/cash-matched benchmark CAGR. '
              'Sharpe and Sortino use daily BOK risk-free excess. CVaR is the mean worst 5% daily net returns. '
              'Turnover excludes the initial purchase; sum cost is the sum of entry cost fractions, not annualized drag.', '',
              f"Matching: {report['matching']['pairedBlocks']}/{report['matching']['expectedBlocks']} fixed matured blocks. "
              f"Complete: {report['matching']['complete']}. Missing blocks are never filled or renormalized.", '',
              '## Incremental attribution and paired bootstrap confidence intervals', '',
              'Raw deltas are challenger minus control. Positive MDD/CVaR deltas mean less-negative losses. '
              'Path CI jointly resamples whole net daily blocks (including original costs and RF). '
              'Its point estimate is the chronological full-path difference.', '']
    for key,a,b in COMPARISONS:
        c = report['comparisons'][key]
        lines += [f'### {key}: {a} minus {b}', '',
                  '| Metric | Path Δ | Bootstrap mean | 95% CI | Paired blocks | Seed | Draws |',
                  '|---|---:|---:|---|---:|---:|---:|']
        for metric,ci in c.get('pathDifferenceCI',{}).items():
            lines.append(f"| {metric} | {fmt(ci['pointEstimate'])} | {fmt(ci['bootstrapMean'])} | "
                         f"[{fmt(ci['ci95'][0])}, {fmt(ci['ci95'][1])}] | {ci['pairedBlocks']} | {ci['seed']} | {ci['samples']} |")
        lines += ['', c.get('mddDescription','Unavailable'), '',
                  'Cash/cost/benchmark deltas (pp, except turnover and summed cost in percentage points): ' +
                  ', '.join(f'{k} {fmt(v)}' for k,v in c.get('cashAndCostDeltas',{}).items()), '']
        for metric,ci in c.get('pathDifferenceCI',{}).items():
            lines.append(f"- {metric}: {ci['evidence']}" + (f" ({ci['reason']})" if ci['reason'] else ''))
        lines += ['', 'Literal mean paired **block-metric** differences (separate estimand; not the full-path difference):', '',
                  '| Metric | Mean block Δ | Bootstrap mean | 95% CI | Pairs | Seed | Draws |',
                  '|---|---:|---:|---|---:|---:|---:|']
        for metric,ci in c.get('meanPairedBlockMetricDifferenceCI',{}).items():
            lines.append(f"| {metric} | {fmt(ci['pointEstimate'])} | {fmt(ci['bootstrapMean'])} | "
                         f"[{fmt(ci['ci95'][0])}, {fmt(ci['ci95'][1])}] | {ci['pairedBlocks']} | {ci['seed']} | {ci['samples']} |")
        for metric,ci in c.get('meanPairedBlockMetricDifferenceCI',{}).items():
            if ci['reason']:
                lines.append(f"{metric}: {ci['reason']}")
        lines.append('')
    lines += ['## Robustness', '', 'Pre-specified OFAT; no winner or default selection.', '',
              '| Variant | Lookback calendar days | Temperature | Floor | ΔCAGR vs static pp | ΔMDD vs static pp | ΔSharpe | US weight min–max | Max quarterly change |',
              '|---|---:|---:|---:|---:|---:|---:|---|---:|']
    for row in report['robustness']:
        p,d = row['parameters'],row['dynamicMinusStatic']
        lines.append(f"| {row['id']} | {p['lookback_days']} | {p['temperature']} | {p['floor']} | {fmt(d['cagrPct'])} | "
                     f"{fmt(d['mddPct'])} | {fmt(d['sharpe'])} | {row['minUsWeight']:.3f}–{row['maxUsWeight']:.3f} | {row['maxQuarterlyWeightChange']:.3f} |")
    for key,st in report['robustnessStability'].items():
        lines += ['', f"{key}: positive {st['positive']}/{st['variants']}, negative {st['negative']}/{st['variants']}; "
                  f"range [{fmt(st['minDelta'])}, {fmt(st['maxDelta'])}]."]
    lines += ['', '## Interpretation', '', report['interpretation'], '',
              '## Sharpe repair', '', report['sharpeRepair'], '',
              '## Limitations', ''] + ['- '+s for s in report['limitations']]
    lines += ['', '## Regional allocation history', '',
              '| Decision date | US trailing score % | KR trailing score % | Raw US | Raw KR | Final US | Final KR |',
              '|---|---:|---:|---:|---:|---:|---:|']
    for row in report['rotationSchedule']:
        lines.append('| '+row['date']+' | '+' | '.join(fmt(row[field].get(region))
                     for field in ('trailingExcessPct','rawWeights','weights') for region in ('US','KR'))+' |')
    lines += ['', '## Invariants', '',
              f"Sealed ledger SHA-256 tree before/after: `{report['sealedInvariant']['before']}` / `{report['sealedInvariant']['after']}`.",
              'Sealed CHAMPION rows are read-only; production selector, Kelly, macro, runMode and liveValidated are unchanged.', '']
    return '\n'.join(lines)


def report_values(value):
    """Publish finite derived decimals at the existing daily metric precision.

    This avoids encoding insignificant cross-Python float summation noise in
    result artifacts. Calculations/bootstrap retain full precision throughout.
    """
    if isinstance(value, dict):
        return {k:report_values(v) for k,v in value.items()}
    if isinstance(value, (list,tuple)):
        return [report_values(v) for v in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError('non-finite report metric')
        return round(float(value),6)
    return value
