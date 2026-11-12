"""Descriptive diagnostics on independently replayed fixed paths.

DSR uses the submission's iid approximation ONLY for reconciliation. It is not
a calibrated probability of luck. CSCV scores a tournament, not an individual
winner; adjacent blocks are not purged at H126/H252 boundaries. No new fit or
historical optimization is performed.
"""
from itertools import combinations
import json
import math

import numpy as np
import pandas as pd
from scipy.stats import norm

from recompute import HERE


def naive_dsr(x, scores, trials):
    sd = x.std(ddof=1)
    sr = x.mean() / sd
    skew = ((x - x.mean()) ** 3).mean() / sd ** 3
    kurt = ((x - x.mean()) ** 4).mean() / sd ** 4
    gamma = .5772156649
    expected = np.std(scores, ddof=1) * ((1 - gamma) * norm.ppf(1 - 1 / trials) + gamma * norm.ppf(1 - 1 / (trials * math.e)))
    z = (sr - expected) * np.sqrt(len(x) - 1) / np.sqrt(1 - skew * sr + (kurt - 1) / 4 * sr * sr)
    return {'naiveProbability': float(norm.cdf(z)), 'trials': trials, 'dailySharpe': float(sr),
            'status': 'DESCRIPTIVE_IID_APPROXIMATION_ONLY',
            'formalDsr': 'NOT_COMPUTABLE_WITH_VALIDATED_ASSUMPTIONS',
            'reasons': ['serial dependence not adjusted', 'full prior research trial count unknown',
                        'winner ranked by CAGR not daily active Sharpe', 'adaptive forced view added after outcomes']}


def pbo(matrix):
    n = len(matrix) // 16 * 16
    means = np.stack([x.mean(axis=0) for x in np.array_split(matrix[:n], 16)])
    bad, count = 0, 0
    for combo in combinations(range(16), 8):
        mask = np.zeros(16, dtype=bool)
        mask[list(combo)] = True
        train = means[mask].mean(axis=0)
        test = means[~mask].mean(axis=0)
        winner = np.argmax(train)
        percentile = ((test < test[winner]).sum() + .5 * (test == test[winner]).sum()) / len(test)
        bad += percentile <= .5
        count += 1
    return {'naivePbo': bad / count, 'combinations': count, 'blocks': 16,
            'blockLength': n // 16, 'droppedTailSessions': len(matrix) - n,
            'status': 'DESCRIPTIVE_SYSTEM_LEVEL_ONLY', 'formalPurgedPbo': 'NOT_VALIDATED_FOR_REPORTED_SELECTION_PROCEDURE',
            'reasons': ['no purge between adjacent CSCV blocks', 'performance criterion is mean active return, unlike reported CAGR/Sharpe ranking',
                        'block exchangeability under changing walk-forward training states not established']}


def regression(y, factors, lag):
    a = np.column_stack([np.ones(len(y)), factors])
    beta = np.linalg.lstsq(a, y, rcond=None)[0]
    residual = y - a @ beta
    score = a * residual[:, None]
    meat = score.T @ score
    for k in range(1, lag + 1):
        cov = score[k:].T @ score[:-k]
        meat += (1 - k / (lag + 1)) * (cov + cov.T)
    bread = np.linalg.pinv(a.T @ a)
    se = np.sqrt(np.maximum(np.diag(bread @ meat @ bread), 0))
    return {'annualAlpha': float(beta[0] * 252), 'alphaT': float(beta[0] / se[0]),
            'etfBeta': float(beta[1]), 'rSquared': float(1 - sum(residual ** 2) / sum((y - y.mean()) ** 2)),
            'conditionNumber': float(np.linalg.cond(a)), 'neweyWestLags': lag,
            'limit': 'ETF and strategy-return proxies only; not industry-neutral or size-factor alpha'}


def main():
    evidence = {}
    for view, sid in [('gated', 'RULE_INDUSTRY_MOMENTUM'), ('forced', 'XGB_CI_RANK_h1')]:
        nav = pd.read_csv(HERE / f'conditional-navs-{view}.csv.gz', index_col=0, parse_dates=True)
        r = nav.pct_change().iloc[1:]
        active = r.subtract(r['RULE_ETF_ONLY'], axis=0)
        nonzero = active.loc[:, active.std() > 1e-10]
        eig = np.linalg.eigvalsh(nonzero.corr())
        eff = float(eig.sum() ** 2 / sum(eig ** 2))
        scores = (nonzero.mean() / nonzero.std()).to_numpy()
        naive = naive_dsr(active[sid].to_numpy(), scores, len(nav.columns))
        rules = [s for s in r if s.startswith('RULE_') and s not in [sid, 'RULE_ETF_ONLY'] and active[s].std() > 1e-10]
        a = np.column_stack([r['RULE_ETF_ONLY'].to_numpy(), active[rules].to_numpy()])
        evidence[view] = {'subject': sid, 'strategies': len(nav.columns),
                          'activeNonzeroStrategies': len(nonzero.columns), 'activeEffectiveParticipationRatio': eff,
                          'dsr': naive, 'cscv': pbo(active.drop(columns='RULE_ETF_ONLY').to_numpy()),
                          'factorProxyRegressions': {str(lag): regression(r[sid].to_numpy(), a, lag) for lag in [10, 126]},
                          'factorProxyColumns': ['ETF', *rules]}
        # Isolate the float32 storage artefact using the SAME reconstructed paths.
        r32 = nav.astype(np.float32).astype(float).pct_change().iloc[1:]
        a32 = r32.subtract(r['RULE_ETF_ONLY'], axis=0)
        s32 = (a32.mean() / a32.std()).replace([np.inf, -np.inf], np.nan).dropna()
        evidence[view]['float32Reconciliation'] = {
            'dsr': naive_dsr(a32[sid].to_numpy(), s32.to_numpy(), len(s32)),
            'cscv': pbo(a32.drop(columns='RULE_ETF_ONLY').to_numpy()),
            'etfOnlyArtificialActiveVol': float(a32['RULE_ETF_ONLY'].std() * np.sqrt(252)),
            'limit': 'Float32 paths minus double-precision ETF create active returns for identical ETF books'}
        # Candidate selection here only reconstructs the submitted past-only diagnostic.
        sids = [s for s in nav if s != 'RULE_ETF_ONLY']
        selected, ret = [], []
        for year in sorted(set(nav.index.year))[1:]:
            past = nav.loc[nav.index.year < year, sids]
            winner = (past.iloc[-1] / past.iloc[0]).idxmax()
            selected.append([int(year), winner])
            ret.extend(r.loc[r.index.year == year, winner])
        years = len(ret) / 252
        evidence[view]['pastOnlyReturnSplice'] = {'cagr': float(np.prod(1 + np.array(ret)) ** (1 / years) - 1),
                                                  'selected': selected,
                                                  'status': 'RETURN_SPLICE_NOT_SELF_FINANCING_SWITCH_BACKTEST',
                                                  'limit': 'Boundary holdings and additional model-switch transaction costs absent'}
    (HERE / 'statistics.json').write_text(json.dumps(evidence, indent=1, allow_nan=False) + '\n')
    print(json.dumps(evidence, indent=1))


if __name__ == '__main__':
    main()
