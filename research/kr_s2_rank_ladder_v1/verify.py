"""Reconcile the new ladder's own endpoints with the pinned published S2."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    out = HERE / 'results'
    fixed = json.loads((out / 'fixed.json').read_text())
    reference = json.loads((ROOT / 'research/alpha_search_round6_v1/results/kr-fixed.json').read_text())
    checks = {}
    for h in (126, 252):
        own = fixed[str(h)]['FULL']['5']['vsETF']
        ref = reference['fixed'][str(h)]['FULL']
        checks[f'H{h}_S2_mean'] = {'actual': own['mean'], 'reference': ref['S2']['vsETF']['mean'],
                                  'gap': own['mean'] - ref['S2']['vsETF']['mean']}
        assert abs(checks[f'H{h}_S2_mean']['gap']) < 1e-8
        assert own['n'] == ref['cohorts']
        df = pd.read_csv(out / f'cohorts-{h}.csv')
        v = df.mainValid
        sums = sum(df[f'delta{k}'] for k in range(1, 6))
        gap = (sums - (df.N5_net - df.N0_net))[v].abs().max()
        assert gap < 1e-10
        checks[f'H{h}_telescopeMaxAbs'] = float(gap)
        decomposition = (df.selection5 + df.exposure5 - (df.N5_net - df.N0_net)).abs().max()
        assert decomposition < 1e-10
        checks[f'H{h}_controlDecompositionMaxAbs'] = float(decomposition)
    audit = pd.read_csv(out / 'decisions.csv')
    assert np.allclose(audit.etfWeight + .2*audit.actual, 1.)
    checks['shortfallDates'] = audit.loc[(audit.requested == 5) & audit.shortfall, 'date'].tolist()
    checks['actualCountDistribution'] = {str(k): int(n) for k, n in audit[audit.requested == 5].actual.value_counts().sort_index().items()}
    log = pd.read_csv(out / 'past-only-decisions.csv', parse_dates=['date', 'lastTrainExit'])
    assert (log.lastTrainExit.dropna() < log.loc[log.lastTrainExit.notna(), 'date']).all()
    checks['pastOnlyDecisionCounts'] = {str(k): int(n) for k, n in log.k.value_counts().sort_index().items()}
    checks['sourceMatrixDigestMatchesPublished'] = json.loads((out / 'inputs.json').read_text())['identity']['matrixDigest'] == '32e49b57a7541eea66f76373baef50c6302a394247b313f6099f718d46d54b0c'
    assert checks['sourceMatrixDigestMatchesPublished']
    if (out / 'ledgers.json').exists():
        led = json.loads((out / 'ledgers.json').read_text())
        ref = json.loads((ROOT / 'research/followup_round8_v1/results/kr-switch-ledgers.json').read_text())
        for every in (26, 52):
            for k, name in [(0, 'ETF'), (5, 'S2')]:
                own = led['metrics'][f'L{every}|N{k}']
                prior = ref['ledgers'][f'L{every}|ORIGINAL|{name}']
                for field in ['cagr', 'excess', 'mdd', 'oneWayTurnoverPerYear', 'costPerYear']:
                    gap = own[field] - prior[field]
                    checks[f'L{every}_N{k}_{field}_gap'] = gap
                    assert abs(gap) < 1e-8, (every, k, field, gap)
            nav = pd.read_csv(out / f'daily-nav-L{every}.csv', index_col='date')
            daily = nav.pct_change().iloc[1:]
            telescope = sum(daily[f'N{k}'] - daily[f'N{k-1}'] for k in range(1, 6))
            assert np.max(np.abs(telescope - (daily.N5 - daily.N0))) < 1e-12
    checks['resultSha256'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir()) if p.is_file() and p.name != 'verification.json'}
    (out / 'verification.json').write_text(json.dumps(checks, indent=1, ensure_ascii=False) + '\n')
    print(json.dumps({k: v for k, v in checks.items() if k != 'resultSha256'}, indent=1))


if __name__ == '__main__':
    main()
