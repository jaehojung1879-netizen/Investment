"""Read-only concentration diagnostic, ADDED AFTER main fixed results were seen.

No portfolio, sample, parameter, price or statistic in run.py is changed.
"""
import hashlib
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent


def main():
    out = HERE / 'results'
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in out.glob('cohorts-*.csv')}
    result = {'status': 'POST_RESULT_READ_ONLY_DIAGNOSTIC_NO_POLICY_CHANGE'}
    for h in (126, 252):
        df = pd.read_csv(out / f'cohorts-{h}.csv')
        rows = []
        for k in range(1, 6):
            g = df.groupby(f'rank{k}Ticker')[f'delta{k}'].agg(['count', 'mean', 'sum'])
            g['meanContributionOverAllCohorts'] = g['sum'] / df.mainValid.sum()
            g['rank'] = k
            g.index.name = 'ticker'
            rows.append(g.reset_index())
        pd.concat(rows).to_csv(out / f'rank-ticker-contributions-{h}.csv', index=False)
        two = df.rank5Ticker.isin(['005930.KS', '000660.KS'])
        total = float(df.delta5.mean())
        contrib = float(df.loc[two, 'delta5'].sum() / df.mainValid.sum())
        result[str(h)] = {'rank5MeanIncrement': total, 'rank5SamsungHynixContribution': contrib,
                          'shareOfNetRank5Increment': contrib / total if total else None,
                          'rank5MedianIncrement': float(df.delta5.median()),
                          'rank5PositiveShare': float((df.delta5 > 0).mean()),
                          'semiconductorHoldingCohorts': int(two.sum()), 'allCohorts': int(df.mainValid.sum()),
                          'leadershipUnknownCohorts': int(df.leadershipUnknown.sum()),
                          'semiLedCohorts': int(df.touchesSemiLed.sum()),
                          'exSemiLedKnownCohorts': int((~df.touchesSemiLed & ~df.leadershipUnknown).sum())}
    assert before == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in out.glob('cohorts-*.csv')}
    (out / 'concentration-diagnostic.json').write_text(json.dumps(result, indent=1) + '\n')
    root = HERE.parents[1]
    study = root / 'research/alpha_mechanism_decomposition_v1'
    paths = ['prospective/recorder.py', 'prospective/spec.json', 'kr_followup/preview-receipts.jsonl',
             'kr_followup/weekly_records.py', 'kr_followup/latest_inputs.py', 'kr_followup/latest-disclosure-check.json']
    rows = [json.loads(line) for line in (study / paths[2]).read_text().splitlines()]
    status = {'status': 'PREPARED_NOT_AUTHORIZED', 'liveReceiptWrittenByThisStudy': False, 'prospectiveObservationsAdded': 0,
              'existingPreviewRecords': len(rows),
              'existingPreviewDateRange': [min(r['signalDate'] for r in rows), max(r['signalDate'] for r in rows)],
              'previewIsProspectiveEvidence': False,
              'reason': 'recorder.REGISTERED_AUTHORIZATION=None; no backdating; latest extension is not verified current live input',
              'existingFilesSha256': {str((study / p).relative_to(root)): hashlib.sha256((study / p).read_bytes()).hexdigest() for p in paths}}
    (out / 'prospective-status.json').write_text(json.dumps(status, indent=1) + '\n')


if __name__ == '__main__':
    main()
