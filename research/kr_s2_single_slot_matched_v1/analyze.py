"""Read-only single-slot decomposition on afb3ea3; no selector/portfolio tuning.

See DESIGN-ko.md (committed before these new calculations).
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from research.kr_s2_rank_ladder_v1 import run as L

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / 'kr_s2_rank_ladder_v1'
BASE_COMMIT = 'afb3ea39ef2033e696c4e26485b7e4ebb74134d8'
TWO = {'005930.KS', '000660.KS'}
TOL = 1e-10  # old CSV has 12 significant digits


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, indent=1, ensure_ascii=False, default=str, allow_nan=False) + '\n')


def single_slot(picks, peer, rank):
    """B: k-1 S2 names. S: k S2 names. Q: SAME prefix + one peer, SAME ETF as S."""
    prefix = picks[:rank-1]
    b, s, q = L.book(prefix), L.book(picks[:rank]), L.book(prefix + [peer])
    assert all(s[t] == q[t] == .2 for t in prefix)
    assert s.get(L.M.ETF, 0.) == q.get(L.M.ETF, 0.)
    assert peer not in picks and peer not in (L.M.ETF, L.M.CASH)
    assert all(abs(sum(v.values()) - 1) < 1e-12 for v in (b, s, q))
    return b, s, q


def portfolio_return(weights, returns):
    if any(returns[t] is None for t, w in weights.items() if w > 0):
        return None
    return sum(w * returns[t][1] for t, w in weights.items() if w > 0)


def summarize(rows, mask, block):
    return {field: L.stats(rows[field], mask, block) for field in ('total', 'selection', 'replacement')}


def select_masks(valid, present, within2x):
    """All arrays share the original mature-week axis; no subset concatenation."""
    own = valid & present
    common = own.all(axis=1)
    common2 = (own & within2x).all(axis=1)
    return own, common, common2


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--scratch', required=True)
    ap.add_argument('--out', type=Path, default=HERE / 'results')
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    old_files = sorted((BASE / 'results').glob('*')) + [BASE / f for f in ('run.py', 'REPORT-ko.md', 'TABLES-ko.md', 'reproduce.sh')]
    before = {str(p.relative_to(BASE)): sha(p) for p in old_files if p.is_file()}
    old_meta = json.loads((BASE / 'results/inputs.json').read_text())
    I, ctx, base = L.RC.setup(args.scratch)
    # Pickle bytes vary by interpreter/serialization. Verify semantic identities and
    # all real cached slot payoffs below, while retaining both byte receipts.
    assert I['ident']['identity'] == old_meta['identity']['identity']
    assert I['ident']['matrixDigest'] == old_meta['identity']['matrixDigest']
    decisions = pd.read_csv(BASE / 'results/decisions.csv', parse_dates=['date'])
    original = decisions[decisions.requested == 5].set_index('date')
    assert sorted(base['dates']) == sorted(original.index)
    fixed = json.loads((BASE / 'results/fixed.json').read_text())
    old_concentration = json.loads((BASE / 'results/concentration-diagnostic.json').read_text())
    bydate, audit = {}, []
    for d in base['dates']:
        g = ctx.by[d].sort_values('ticker').copy()
        gi = g.set_index('ticker')
        weights, picks, _ = L.C.sleeve_book('S2_VALUE_CONFIRMED', g)
        assert weights == base['s2'][d]
        assert '|'.join(picks) == original.at[d, 'tickersInRankOrder']
        source = g[~g.ticker.isin(L.C.WITHHELD)]
        peers = L.M.matched_controls(source, picks, ['_mcap'])
        saved = original.at[d, 'matchedTickers'].split('|') if picks else []
        assert [str(peers[t]) for t in picks] == saved
        quality = source[source['_q'].astype(bool)]
        pct = quality.set_index('ticker')['_mcap'].rank(pct=True)
        used = set(picks)
        bydate[d] = (picks, peers)
        for k in range(1, 6):
            r = {'date': d, 'rank': k, 'present': len(picks) >= k, 'status': 'RANK_UNAVAILABLE', 'within2x': False,
                 'qualityCandidates': len(quality), 'matchingSuccess': False}
            if len(picks) >= k:
                t, peer = picks[k-1], peers[picks[k-1]]
                pool = quality[(quality.industry == gi.at[t, 'industry']) & ~quality.ticker.isin(used)]
                r.update(ticker=t, peer=peer, industry=gi.at[t, 'industry'], remainingIndustryCandidates=len(pool),
                         candidateTickers='|'.join(sorted(pool.ticker)))
                if peer is None:
                    r['status'] = 'NO_SAME_INDUSTRY_CANDIDATE'
                else:
                    assert peer not in used and peer in pool.ticker.to_list()
                    assert gi.at[t, 'industry'] == gi.at[peer, 'industry']
                    assert bool(gi.at[peer, '_q'])
                    for name in (t, peer):
                        assert pd.Timestamp(gi.at[name, 'pitSnapshotDate']) < d
                    a, b = float(gi.at[t, '_mcap']), float(gi.at[peer, '_mcap'])
                    good_cap = np.isfinite(a) and np.isfinite(b) and min(a, b) > 0
                    r.update(s2MarketCap=a if np.isfinite(a) else None, peerMarketCap=b if np.isfinite(b) else None,
                             sourceSnapshot=str(gi.at[t, 'pitSnapshotDate']), peerSnapshot=str(gi.at[peer, 'pitSnapshotDate']))
                    if good_cap:
                        ratio = b/a
                        r.update(status='MATCHED', matchingSuccess=True, capRatioPeerOverS2=ratio,
                                 symmetricCapMultiple=max(ratio, 1/ratio), capPercentileDistance=float(abs(pct[t]-pct[peer])),
                                 within2x=.5 <= ratio <= 2)
                        r['sizeFilterStatus'] = 'WITHIN_2X' if r['within2x'] else 'OUTSIDE_2X_SIZE_RANGE'
                    else:
                        r['status'] = 'MCAP_UNAVAILABLE'
                    used.add(peer)
            audit.append(r)
    au = pd.DataFrame(audit)
    au.to_csv(args.out / 'matching-audit.csv', index=False, float_format='%.16g')
    audit_index = au.set_index(['date', 'rank'])
    result = {'label': 'FOLLOW_UP_ON_OUTCOME_EXPOSED_HISTORY_NOT_PROSPECTIVE', 'baseCommit': BASE_COMMIT,
              'designCommit': '48e7f23', 'bookPerformance': {}, 'decomposition': {}, 'coverage': {},
              'rank5Sensitivity': {}, 'old79PercentDenominator': {}, 'matchedWholeBookDecomposition': {}, 'validation': {}}
    max_reconstruction, max_identity, max_old = 0., 0., 0.
    for h in (126, 252):
        df = pd.read_csv(BASE / f'results/cohorts-{h}.csv', parse_dates=['date', 'entry', 'exit'])
        rows = []
        for c in df.to_dict('records'):
            d, e, x = c['date'], c['entry'], c['exit']
            picks, peers = bydate[d]
            need = set(picks) | {v for v in peers.values() if v} | {L.M.ETF}
            returns = {t: L.asset_return(I['closes'], t, e, x) for t in need}
            for k in range(1, 6):
                ar = audit_index.loc[(d, k)]
                row = {'date': d, 'entry': e, 'exit': x, 'rank': k, 'present': bool(ar.present),
                       'matched': bool(ar.matchingSuccess), 'valid': False, 'within2x': bool(ar.within2x),
                       'status': ar.status, 'touchesSemiLed': c['touchesSemiLed'], 'leadershipUnknown': c['leadershipUnknown'],
                       'total': np.nan, 'selection': np.nan, 'replacement': np.nan}
                if row['present'] and row['matched']:
                    t, peer = picks[k-1], peers[picks[k-1]]
                    b, s, q = single_slot(picks, peer, k)
                    vals = [portfolio_return(w, returns) for w in (b, s, q)]
                    row.update(ticker=t, peer=peer, prefix='|'.join(picks[:k-1]), etfWeightSAndQ=1-.2*k,
                               B_weights=json.dumps(b, sort_keys=True), S_weights=json.dumps(s, sort_keys=True), Q_weights=json.dumps(q, sort_keys=True))
                    if any(v is None for v in vals):
                        row['status'] = 'UNRESOLVED_PRICE'
                    else:
                        # Reuse cached costed payoffs. Q retains the S2 prefix, NOT the matched prefix.
                        B, S = c[f'N{k-1}_net'], c[f'N{k}_net']
                        replacement = c[f'M{k}_net'] - c[f'M{k-1}_net']
                        Q = B + replacement
                        total, selection = S-B, S-Q
                        row.update(valid=True, B_net=B, S_net=S, Q_net=Q, B_raw=vals[0], S_raw=vals[1], Q_raw=vals[2],
                                   total=total, selection=selection, replacement=replacement,
                                   legacyMatchedIncrement=c[f'delta{k}'] - replacement,
                                   stockNet=returns[t][1], peerNet=returns[peer][1], etfNet=returns[L.M.ETF][1])
                        max_reconstruction = max(max_reconstruction, max(abs(a-b0) for a, b0 in zip((B, S, Q), vals)))
                        max_identity = max(max_identity, abs(total-selection-replacement))
                        max_old = max(max_old, abs(selection-row['legacyMatchedIncrement']))
                        assert abs(selection - .2*(returns[t][1]-returns[peer][1])) < TOL
                rows.append(row)
        frame = pd.DataFrame(rows)
        frame.to_csv(args.out / f'single-slot-{h}.csv', index=False, float_format='%.16g')
        indexed = {k: frame[frame['rank'] == k].reset_index(drop=True) for k in range(1, 6)}
        val = np.column_stack([indexed[k].valid for k in range(1, 6)])
        present = np.column_stack([indexed[k].present for k in range(1, 6)])
        within2 = np.column_stack([indexed[k].within2x for k in range(1, 6)])
        own, common, common2 = select_masks(val, present, within2)
        masks_frame = df[['date', 'entry', 'exit']].copy()
        masks_frame['commonAllRanks'] = common
        masks_frame['commonAllRanksWithin2x'] = common2
        for k in range(1, 6):
            masks_frame[f'rank{k}Valid'] = own[:, k-1]
            masks_frame[f'rank{k}Within2x'] = own[:, k-1] & within2[:, k-1]
        masks_frame.to_csv(args.out/f'common-dates-{h}.csv', index=False)
        block = round(h/5)
        dec, cover = {}, {}
        for k, fr in indexed.items():
            masks = {'RANK_PRESENT': own[:, k-1], 'COMMON_ALL_RANKS': common,
                     'WITHIN_2X': own[:, k-1] & within2[:, k-1], 'COMMON_ALL_RANKS_WITHIN_2X': common2}
            dec[str(k)] = {lab: summarize(fr, m, block) for lab, m in masks.items()}
            m = own[:, k-1]
            co = {'matureWeeks': len(df), 'rankPresentWeeks': int(fr.present.sum()), 'matchedWeeks': int(fr.matched.sum()),
                  'validWeeks': int(m.sum()), 'successRateOfRankPresent': float(fr.matched.sum()/fr.present.sum()) if fr.present.any() else None,
                  'firstTarget': str(fr.loc[fr.present, 'date'].min().date()), 'lastTarget': str(fr.loc[fr.present, 'date'].max().date()),
                  'unmatchedReasons': {str(a): int(b) for a, b in fr.loc[~fr.valid, 'status'].value_counts().items()},
                  'within2xWeeks': int((m & fr.within2x).sum()), 'outside2xWeeks': int((m & ~fr.within2x).sum()),
                  'commonAllRanksWeeks': int(common.sum()), 'commonWithin2xWeeks': int(common2.sum())}
            distances = audit_index.loc[[(d, k) for d in df.date]].reset_index()
            gap = distances.loc[distances.matchingSuccess, 'symmetricCapMultiple']
            co['symmetricCapMultiple'] = {'median': float(gap.median()), 'p90': float(gap.quantile(.9)), 'max': float(gap.max())}
            cover[str(k)] = co
            # Old FULL statistic includes zero contributions on weeks with no such rank.
            legacy = fr[['total', 'selection', 'replacement']].copy()
            legacy.loc[~fr.present, :] = 0.
            legacy_summary = summarize(legacy, np.ones(len(df), bool), block)
            dec[str(k)]['LEGACY_ZERO_FILL'] = legacy_summary
            prior = fixed[str(h)]['FULL'][str(k)]
            for field, oldfield in [('total', 'increment'), ('selection', 'incrementNetOfMatched')]:
                assert abs(legacy_summary[field]['mean'] - prior[oldfield]['mean']) < TOL
                assert np.max(np.abs(np.array(legacy_summary[field]['ci']) - prior[oldfield]['ci'])) < TOL
        result['decomposition'][str(h)], result['coverage'][str(h)] = dec, cover
        result['bookPerformance'][str(h)] = {
            str(k): {'FULL_REUSED': fixed[str(h)]['FULL'][str(k)]['vsETF'],
                     'COMMON_ALL_RANKS': L.stats(df[f'N{k}_net']-df.N0_net, common, block),
                     'COMMON_ALL_RANKS_WITHIN_2X': L.stats(df[f'N{k}_net']-df.N0_net, common2, block)} for k in range(6)}
        whole = pd.DataFrame({'total': df.N5_net-df.N0_net, 'selection': df.N5_net-df.M5_net, 'replacement': df.M5_net-df.N0_net})
        result['matchedWholeBookDecomposition'][str(h)] = {
            'FULL': summarize(whole, np.ones(len(df), bool), block),
            'COMMON_ALL_RANKS': summarize(whole, common, block),
            'COMMON_ALL_RANKS_WITHIN_2X': summarize(whole, common2, block)}
        fifth = indexed[5]
        is_two = fifth.ticker.isin(TWO)
        valid5 = own[:, 4]
        # Each group keeps the full original timeline for paired block sampling.
        masks = {'BASE_PRESENT': valid5, 'EX_TWO_AT_RANK5': valid5 & ~is_two,
                 'SEMI_LED': valid5 & fifth.touchesSemiLed,
                 'NON_SEMI_KNOWN': valid5 & ~fifth.touchesSemiLed & ~fifth.leadershipUnknown,
                 'LABEL_UNKNOWN': valid5 & fifth.leadershipUnknown,
                 'SEMI_LED_EX_TWO': valid5 & fifth.touchesSemiLed & ~is_two,
                 'NON_SEMI_KNOWN_EX_TWO': valid5 & ~fifth.touchesSemiLed & ~fifth.leadershipUnknown & ~is_two,
                 'WITHIN_2X': valid5 & fifth.within2x,
                 'WITHIN_2X_EX_TWO': valid5 & fifth.within2x & ~is_two,
                 'COMMON_WITHIN_2X': common2,
                 'COMMON_WITHIN_2X_EX_TWO': common2 & ~is_two}
        sensitivity = {lab: summarize(fifth, mask, block) for lab, mask in masks.items()}
        legacy5 = fifth[['total', 'selection', 'replacement']].copy()
        legacy5.loc[~fifth.present, :] = 0.
        sensitivity['LEGACY_FULL_ZERO_FILL'] = summarize(legacy5, np.ones(len(df), bool), block)
        sensitivity['LEGACY_FULL_EX_TWO'] = summarize(legacy5, ~is_two, block)
        result['rank5Sensitivity'][str(h)] = sensitivity
        numerator = float(df.loc[is_two.to_numpy(), 'delta5'].sum())
        denominator = float(df.delta5.sum())
        contribution = numerator/len(df)
        concentration = {'firstSignal': str(df.date.min().date()), 'lastSignal': str(df.date.max().date()),
                         'fullCohorts': len(df), 'rank5Present': int(fifth.present.sum()), 'twoAtRank5': int(is_two.sum()),
                         'excludedFullCohorts': int((~is_two).sum()), 'excludedPresentCohorts': int((valid5 & ~is_two).sum()),
                         'numeratorSumRank5NetIncrement': numerator, 'denominatorSumRank5NetIncrement': denominator,
                         'share': numerator/denominator, 'contributionMeanAcrossFullCohorts': contribution,
                         'fullMeanRank5Increment': denominator/len(df)}
        old = old_concentration[str(h)]
        assert abs(concentration['share']-old['shareOfNetRank5Increment']) < 1e-9
        assert abs(contribution-old['rank5SamsungHynixContribution']) < TOL
        result['old79PercentDenominator'][str(h)] = concentration
        # The common-date mean decomposition also reconciles to the N5-M5 book contrast.
        sums = {field: sum(dec[str(k)]['COMMON_ALL_RANKS'][field]['mean'] for k in range(1, 6)) for field in ('total', 'selection', 'replacement')}
        assert abs(sums['total'] - result['bookPerformance'][str(h)]['5']['COMMON_ALL_RANKS']['mean']) < TOL
        assert abs(sums['selection']-float((df.N5_net-df.M5_net)[common].mean())) < TOL
        result['validation'][str(h)] = {'commonAllRankMeansSummed': sums, 'commonWeeks': int(common.sum()),
                                      'commonFirst': str(df.loc[common, 'date'].min().date()), 'commonLast': str(df.loc[common, 'date'].max().date()),
                                      'commonWithin2xWeeks': int(common2.sum()),
                                      'commonWithin2xFirst': str(df.loc[common2, 'date'].min().date()),
                                      'commonWithin2xLast': str(df.loc[common2, 'date'].max().date())}
        for sample in ('COMMON_ALL_RANKS', 'COMMON_ALL_RANKS_WITHIN_2X'):
            for field in ('total', 'selection', 'replacement'):
                summed = sum(dec[str(k)][sample][field]['mean'] for k in range(1, 6))
                assert abs(summed-result['matchedWholeBookDecomposition'][str(h)][sample][field]['mean']) < TOL
    assert max_reconstruction < TOL
    assert max_identity < TOL and max_old < TOL
    after = {str(p.relative_to(BASE)): sha(p) for p in old_files if p.is_file()}
    assert before == after
    result['validation'].update(maxDirectBookReconstructionError=max_reconstruction,
                                maxPerDateDecompositionError=max_identity, maxLegacyEquivalenceError=max_old,
                                originalArtifactsByteUnchanged=True)
    dump(args.out / 'summary.json', result)
    dump(args.out / 'provenance.json', {'baseCommit': BASE_COMMIT, 'oldArtifactSha256': before,
         'referenceScratchSha256': old_meta['scratchFiles'],
         'actualScratchSha256': {name: sha(Path(args.scratch)/name) for name in old_meta['scratchFiles']},
         'semanticInputIdentitiesVerified': True, 'designSha256': sha(HERE/'DESIGN-ko.md'),
         'analysisCodeSha256': sha(HERE/'analyze.py'), 'comparisonType': 'COSTED_FIXED_HOLDING_SINGLE_SLOT_REPLACEMENT',
         'horizons': [126, 252], 'blocksWeeks': [25, 50], 'bootstrapDraws': L.DRAWS, 'seed': L.SEED,
         'sourceIdentity': I['ident'], 'pythonNumpyPandas': [__import__('sys').version, np.__version__, pd.__version__]})
    print(json.dumps(result['validation'], indent=1))


if __name__ == '__main__':
    main()
