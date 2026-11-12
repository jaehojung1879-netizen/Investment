"""Recheck relevant #330 assertions from pinned source/code, preserve its bytes."""
from bisect import bisect_left
from collections import defaultdict
import gzip
import hashlib
import json

import numpy as np

from .identity import HERE, ROOT, file_hash, write_once
from .sources import git_blob, PIN


def review():
    pins = json.loads((ROOT / 'research/ml_strategy_tournament_independent_audit_v1/frozen-inputs.json').read_text())
    assert all(file_hash(ROOT / p) == r['sha256'] for p, r in pins['files'].items())
    spec = json.loads((ROOT / 'research_specs/kr-model-overlay-portfolio-v1.json').read_text())
    grouped = defaultdict(list)
    for path, expected in spec['inputs']['universeBlobs'].items():
        raw = git_blob(path)
        assert hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest() == expected
        for line in gzip.decompress(raw).splitlines():
            r = json.loads(line)
            grouped[r['date']].append(r)
    dates = sorted(grouped)
    members = {d: {r['ticker'] for r in sorted(rows, key=lambda r: (r['rank'], r['ticker']))[:120]} for d, rows in grouped.items()}
    z = np.load(ROOT / 'research/ml_strategy_tournament_v1/results/predictions-rebalance-pctile.npz', allow_pickle=False)
    violations, keys = [], set()
    for d, t in zip(z['dates'], z['tickers']):
        prior = dates[bisect_left(dates, str(d)) - 1]
        if not prior < d or t not in members[prior] or (d, t) in keys:
            violations.append([str(d), str(t), prior])
        keys.add((d, t))
    fold = json.loads((ROOT / 'research/ml_strategy_tournament_v1/results/fold-records.json').read_text())
    fitted = [r for records in fold.values() for r in records if r.get('trainRows')]
    bad_folds = [r for r in fitted if r['trainLastExit'] >= r['testFirst']]
    actual = file_hash(ROOT / 'research/ml_strategy_tournament_v1/config.json')
    published = json.loads((ROOT / 'research/ml_strategy_tournament_v1/results/data-eligibility.json').read_text())['inputs']['configSha256']
    return {'rawCommit': PIN, 'originalPinnedFilesUnchanged': True,
            'PITStoredRebalanceRows': {'status': 'PASS' if not violations else 'FAIL', 'keys': len(keys), 'violations': violations},
            'H126StoredFoldMaturity': {'status': 'PASS' if not bad_folds else 'FAIL', 'folds': len(fitted), 'violations': bad_folds},
            'H252FitPath': {'status': 'INCONCLUSIVE', 'reason': 'FOLD_AND_HOLDING_RECORDS_NOT_SAVED'},
            'filingAndMacroVintage': {'status': 'INCONCLUSIVE', 'reason': 'NO_NEW_RELEASE_VINTAGE_PROOF_IN_THIS_REPAIR'},
            'futureCoverageSelection': {'v1': 'FAIL_REPRODUCED_BY_REGRESSION', 'v2': 'TRAIN_ONLY_FIXED_AND_SYNTHETICALLY_TESTED'},
            'miraeBlanketRefusal': {'audit330': 'TOO_BROAD_FOR_EXISTING_RECOVERED_CONNECTED_SEGMENTS',
                                  'v2': 'VERIFIED_SEGMENTS_REUSED_UNVALUED_2018_RIGHT_STILL_BLOCKS_CROSSING_HOLDINGS'},
            'terminal': {'v1ZeroOrLastPrice': 'FAIL', 'v2': 'CITED_PACKAGE_ONLY_OR_SOURCE_BLOCKED'},
            'accounting': {'v1LockedQuantityAndFee': 'FAIL_REPRODUCED', 'v2': 'ACTUAL_NOTIONAL_CASH_EQUATION_AND_LOCKED_UNITS_TESTED'},
            'modelSelectionVsExternalEvaluation': {'status': 'FAIL_UNCHANGED_NO_NEW_VALIDATION_CLAIM'},
            'configMetadataIdentity': {'status': 'FAIL_IN_PUBLISHED_METADATA', 'actualConfigSha256': actual,
                                       'publishedMetadataConfigSha256': published, 'audit330ManifestPinnedActualBytes': True,
                                       'audit330NarrativeRepeatedStaleMetadata': True,
                                       'limit': 'Mismatch alone does not prove numerical hyperparameters changed'}}


if __name__ == '__main__':
    print(write_once(HERE / 'audit-reassessment.json', review()))
