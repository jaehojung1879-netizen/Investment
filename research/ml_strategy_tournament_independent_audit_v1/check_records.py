"""Independent structural checks on immutable submitted records, without fitting."""
from collections import defaultdict
from itertools import combinations
import gzip
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
SUB = HERE.parent / 'ml_strategy_tournament_v1'


def main():
    h = json.loads(gzip.decompress((SUB / 'results/holdings-all.json.gz').read_bytes()))
    pred = np.load(SUB / 'results/predictions-rebalance-pctile.npz', allow_pickle=False)
    pairs = pd.MultiIndex.from_arrays([pred['dates'], pred['tickers']])
    folds = json.loads((SUB / 'results/fold-records.json').read_text())
    fit = [(s, r) for s, rr in folds.items() for r in rr if r.get('trainRows')]
    violations = [{'sid': s, **r} for s, r in fit if r['trainLastExit'] >= r['testFirst']]
    weight_issues, dates, all_sums, negative = [], [], [], []
    for view, paths in h.items():
        for sid, pp in paths.items():
            dates.append(len(pp))
            for r in pp:
                sm = sum(r['weights'].values()) + r['etf']
                all_sums.append(sm)
                if abs(sm - 1) > 3e-6:
                    weight_issues.append([view, sid, r['date'], sm])
                if min([r['etf'], *r['weights'].values()]) < 0:
                    negative.append([view, sid, r['date']])
    evidence = {'predictionRows': len(pairs), 'duplicatePredictionKeys': int(pairs.duplicated().sum()),
                'uniqueRebalanceSignalDates': len(set(pred['dates'])), 'submittedFittedFoldsH126': len(fit),
                'recordedMaturityViolationsH126': violations, 'h252FoldRecords': 'NOT_SAVED',
                'weightSumMinMax': [min(all_sums), max(all_sums)], 'weightSumViolations': weight_issues,
                'negativeWeights': negative, 'allPathsRebalanceRange': [min(dates), max(dates)]}
    for view in h:
        ranking = json.loads((SUB / f'results/rankings-{view}.json').read_text())
        board = json.loads((SUB / f'results/leaderboard-{view}.json').read_text())['leaderboard']
        top = sorted(board, key=lambda s: (-board[s]['cagr'], s))[:20]
        pairs_hold = {s: {(r['date'], t) for r in h[view][s] for t in r['weights']} for s in top}
        jaccard = [len(pairs_hold[a] & pairs_hold[b]) / max(1, len(pairs_hold[a] | pairs_hold[b])) for a, b in combinations(top, 2)]
        dates_sorted = sorted(set(pred['dates']))
        selected = [s for s in top if s != 'RULE_ETF_ONLY']
        corr_by_pair = defaultdict(list)
        for d in dates_sorted:
            mask = pred['dates'] == d
            frame = pd.DataFrame({s: np.where(pred[s][mask] >= 0, pred[s][mask], np.nan)
                                  for s in selected})
            corr = frame.corr(method='spearman')
            for a, b in combinations(selected, 2):
                v = corr.at[a, b]
                if np.isfinite(v):
                    corr_by_pair[a, b].append(v)
        corrs = [np.mean(v) for v in corr_by_pair.values()]
        coverage = sorted({r['strategy'] for key in ('absoluteTop10', 'riskAdjustedTop10') for r in ranking[key]})
        evidence[view] = {'top10Union': coverage, 'top20HoldJaccard': float(np.mean(jaccard)),
                          'top20PredictionRankCorrRebalanceOnly': float(np.mean(corrs)),
                          'predictionCorrelationScope': '140 recorded rebalances; quantized percentiles; not all weekly predictions',
                          'nonEtfMlBeatEtf': sum(v['cagr'] > board['RULE_ETF_ONLY']['cagr'] + 1e-10 for s, v in board.items() if not s.startswith('RULE_'))}
    # Future-coverage counterexample tied to actual saved coverage tables.
    elig = json.loads((SUB / 'results/data-eligibility.json').read_text())
    evidence['featuresWithFullCoveragePassButNo2015Coverage'] = {
        c: {'fullCoverage': v, '2015Coverage': elig['coverageByYear'].get(c, {}).get('2015')}
        for c, v in elig['featureCoverageOverall'].items()
        if v >= .2 and elig['coverageByYear'].get(c, {}).get('2015') == 0
    }
    (HERE / 'record-checks.json').write_text(json.dumps(evidence, indent=1, allow_nan=False) + '\n')
    print(json.dumps({k: v for k, v in evidence.items() if k not in ('gated', 'forced')}, indent=1))


if __name__ == '__main__':
    main()
