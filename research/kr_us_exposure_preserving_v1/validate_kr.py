"""Independent arithmetic checks for the preserved Korean output and funding design."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import pickle

import pandas as pd

from . import engine


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, default=Path(__file__).resolve().parent / 'results/KR')
    parser.add_argument('--prepared', type=Path, default=Path('/workspace/exposure-inputs/kr/adapter-input.pkl'))
    args = parser.parse_args(argv)
    checks = {}
    for h in (126, 252):
        frame = pd.read_csv(args.out / f'cohorts-{h}.csv.gz')
        valid = frame[['funded', 'passive', 'active']].notna().all(axis=1)
        error = (frame.loc[valid, 'funded'] - frame.loc[valid, 'passive'] - frame.loc[valid, 'active']).abs().max()
        assert error < 1e-9
        checks[str(h)] = {'decompositionRows': int(valid.sum()), 'maxAbsDecompositionError': float(error)}
    official = pd.read_csv(args.out / 'official-pcf-exposure-audit.csv.gz')
    expected_dates = json.loads((args.out / 'official-pcf-audit-summary.json').read_text())['eligibleDecisionDates']
    counts = official.groupby('config').size()
    assert counts.loc[~counts.index.str.endswith(':PEER')].eq(expected_dates).all()
    assert counts.le(expected_dates).all()
    checks['officialPCFAuditDecisionDates'] = expected_dates
    checks['officialPCFExposureRows'] = len(official)
    for name in ('Samsung', 'Hynix'):
        error = (official['direct' + name] + official['indirect' + name] - official['total' + name]).abs().max()
        assert error < 1e-12
        checks['pcf' + name + 'LookthroughMaxError'] = float(error)
    inputs = pickle.loads(args.prepared.read_bytes())
    maximum = 0.
    for bydate in inputs['books'].values():
        for date, book in bydate.items():
            base, groups = inputs['passive'][date], inputs['sectors'][date]
            stock = {t: w for t, w in book.items() if t != inputs['etf'] and w > 0}
            funded, _, gap = engine.redistribute(base, stock, groups, inputs['leaders'])
            keys = {(groups.get(t, 'UNCLASSIFIED'), t in inputs['leaders']) for t in set(base) | set(stock)}
            def cells(weights):
                return {cell: sum(w for t, w in weights.items()
                                  if (groups.get(t, 'UNCLASSIFIED'), t in inputs['leaders']) == cell) for cell in keys}
            original = {t: (1-sum(stock.values())) * base.get(t, 0) + stock.get(t, 0) for t in set(base) | set(stock)}
            b, f, o = cells(base), cells(funded), cells(original)
            previous, current = engine.distance(b, o), engine.distance(b, f)
            error = abs(current - 2 * gap)
            maximum = max(maximum, error)
            assert current <= previous + 1e-10
            assert error < 1e-10
    checks['fundingCellL1MinimalityCheckedBooks'] = sum(len(v) for v in inputs['books'].values())
    checks['fundingCellL1EqualsTwiceGapMaxError'] = maximum
    (args.out / 'adapter-validation.json').write_text(json.dumps(checks, indent=1) + '\n')
    print(json.dumps(checks, indent=1))


if __name__ == '__main__':
    main()
