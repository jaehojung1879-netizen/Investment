"""Verify saved single-slot economics and paired intervals without source pickle inputs."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from research.kr_s2_rank_ladder_v1 import run as L

HERE = Path(__file__).resolve().parent
OLD = HERE.parent/'kr_s2_rank_ladder_v1'


def main():
    out = HERE/'results'
    r = json.loads((out/'summary.json').read_text())
    p = json.loads((out/'provenance.json').read_text())
    assert all(hashlib.sha256((OLD/n).read_bytes()).hexdigest() == h for n, h in p['oldArtifactSha256'].items())
    assert hashlib.sha256((HERE/'analyze.py').read_bytes()).hexdigest() == p['analysisCodeSha256']
    old_fixed = json.loads((OLD/'results/fixed.json').read_text())
    audit = pd.read_csv(out/'matching-audit.csv', parse_dates=['date'])
    assert not audit.duplicated(['date','rank']).any()
    pairs = audit[audit.matchingSuccess]
    assert (pd.to_datetime(pairs.sourceSnapshot) < pairs.date).all()
    assert (pd.to_datetime(pairs.peerSnapshot) < pairs.date).all()
    assert pairs.apply(lambda a: a.peer in a.candidateTickers.split('|'), axis=1).all()
    assert ((pairs.capRatioPeerOverS2 >= .5) & (pairs.capRatioPeerOverS2 <= 2)).equals(pairs.within2x)
    checks = {'originalV1ArtifactsByteUnchanged': True, 'snapshotStrictlyBeforeSignal': True}
    max_identity = max_single = max_raw = max_ci = 0.
    for h in (126,252):
        fr = pd.read_csv(out/f'single-slot-{h}.csv', parse_dates=['date','entry','exit'])
        old = pd.read_csv(OLD/f'results/cohorts-{h}.csv', parse_dates=['date']).set_index('date')
        masks = pd.read_csv(out/f'common-dates-{h}.csv', parse_dates=['date'])
        assert len(fr) == len(old)*5 and not fr.duplicated(['date','rank']).any()
        for _,v in fr[fr.valid].iterrows():
            b,s,q = [json.loads(v[n]) for n in ('B_weights','S_weights','Q_weights')]
            changed = {t for t in set(s)|set(q) if abs(s.get(t,0)-q.get(t,0)) > 1e-12}
            assert changed == {v.ticker,v.peer}
            assert s.get(L.M.ETF,0) == q.get(L.M.ETF,0)
            assert all(abs(sum(w.values())-1) < 1e-12 for w in (b,s,q))
            max_identity = max(max_identity, abs(v.total-v.selection-v.replacement))
            max_single = max(max_single, abs(v.selection-.2*(v.stockNet-v.peerNet)))
            max_raw = max(max_raw, *(abs(v[a]-v[z]) for a,z in [('B_net','B_raw'),('S_net','S_raw'),('Q_net','Q_raw')]))
        for k in range(6):
            assert r['bookPerformance'][str(h)][str(k)]['FULL_REUSED'] == old_fixed[str(h)]['FULL'][str(k)]['vsETF']
        for k in range(1,6):
            sub = fr[fr['rank']==k].reset_index(drop=True)
            assert list(sub.date) == list(masks.date)
            own = sub.valid & sub.present
            coverage = r['coverage'][str(h)][str(k)]
            assert int(own.sum()) == coverage['validWeeks']
            assert int((own & sub.within2x).sum()) == coverage['within2xWeeks']
            for field in ('total','selection','replacement'):
                actual = L.stats(sub[field], masks.commonAllRanksWithin2x, round(h/5))
                cached = r['decomposition'][str(h)][str(k)]['COMMON_ALL_RANKS_WITHIN_2X'][field]
                assert actual['n'] == cached['n'] and abs(actual['mean']-cached['mean']) < 1e-12
                max_ci = max(max_ci, float(np.max(np.abs(np.array(actual['ci'])-cached['ci']))))
        fifth = fr[fr['rank']==5].reset_index(drop=True)
        two = fifth.ticker.isin(['005930.KS','000660.KS'])
        exact_share = old.loc[old.rank5Ticker.isin(['005930.KS','000660.KS']), 'delta5'].sum()/old.delta5.sum()
        assert abs(exact_share-r['old79PercentDenominator'][str(h)]['share']) < 1e-12
        sensitivity = r['rank5Sensitivity'][str(h)]
        assert sensitivity['EX_TWO_AT_RANK5']['total']['n'] == int((fifth.valid & ~two).sum())
        assert sensitivity['LEGACY_FULL_EX_TWO']['total']['n'] == int((~two).sum())
        checks[str(h)] = {'matureWeeks':len(old), 'validSlotComparisons':int(fr.valid.sum()),
                          'commonSizeWeeks':int(masks.commonAllRanksWithin2x.sum()), 'old79Share':float(exact_share)}
    assert max_identity < 1e-12 and max_single < 1e-10 and max_raw < 1e-10 and max_ci < 1e-12
    checks.update(maxSavedRowIdentityError=max_identity, maxDirectStockPeerDifferenceError=max_single,
                  maxRawBookReconstructionError=max_raw, maxReplayedPrimaryCIError=max_ci,
                  resultSha256={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(out.iterdir()) if f.name!='verification.json'})
    (out/'verification.json').write_text(json.dumps(checks,indent=1)+'\n')
    print(json.dumps({k:v for k,v in checks.items() if k!='resultSha256'},indent=1))


if __name__=='__main__':
    main()
