"""Independent, read-only audit of frozen selections; never trains/searches models.

No imports from the submitted research or its NAV engine. Values are synthetic
TOTAL RETURN INDEX units, not executable security shares. A conditional replay
cannot certify dividend receipts, cash balances or missing terminal consideration.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SUB = ROOT / 'research/ml_strategy_tournament_v1'
PIN = '4ea107ed0cde289f0a049a65ff13d2441a786710'
BENCH = '069500.KS'
CFG = json.loads((SUB / 'config.json').read_text())


def blob(path, commit=PIN):
    return subprocess.check_output(['git', 'cat-file', 'blob', f'{commit}:{path}'], cwd=ROOT)


def sha(b):
    return hashlib.sha256(b).hexdigest()


def load_prices(cache):
    """Read exact manifest objects independently, verifying their decoded digests."""
    manifest_raw = blob('ledger/historical/replay-v16/inputs.json')
    m = json.loads(manifest_raw)
    canonical = json.dumps({k: v for k, v in m.items() if k != 'sha256'},
                           sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
    assert sha(canonical) == m['sha256'] == 'f0781292f508a123c234ded6d28aa8e84a0dc3cc29500e14989dc0b68f53b4d2'
    rows, seen, identical = [], {}, 0
    evidence = {'commit': PIN, 'manifestFileSha256': sha(manifest_raw), 'objects': {}}
    for name, refs in sorted(m['components'].items()):
        if not name.startswith(('price/', 'benchmark/')) or name in ('price/source', 'benchmark/source'):
            continue
        for ref in refs:
            data = gzip.decompress(blob('ledger/replay-inputs/objects/' + ref + '.json.gz'))
            assert sha(data) == ref
            evidence['objects'][ref] = {'component': name, 'bytesDecoded': len(data)}
            for row in json.loads(data):
                if not row.get('ticker', '').endswith('.KS'):
                    continue
                key = row['date'], row['ticker']
                if key in seen:
                    assert row == seen[key], ('conflicting_price', key)
                    identical += 1
                else:
                    seen[key] = row
                    rows.append(row)
    frame = pd.DataFrame(rows)
    frame['date'] = pd.to_datetime(frame['date'])
    closes = frame.pivot(index='date', columns='ticker', values='Close').sort_index()
    volumes = frame.pivot(index='date', columns='ticker', values='Volume').sort_index()
    from pipeline.replay_calendar import sessions  # only the pinned calendar, no outcome engine
    days = sessions('2013-01-01', '2026-09-14', 'KR')
    closes, volumes = closes.reindex(days), volumes.reindex(days)
    q = json.loads((ROOT / 'docs/audits/kr-alpha-atlas-phase-c-integrity/benchmark-reconciliation-corrected.json').read_text())
    closes[BENCH] = pd.Series({pd.Timestamp(r['date']): r['Close'] for r in q['correctedBenchmarkQuotes']}).reindex(days)
    assert closes[BENCH].notna().all()
    evidence.update(identicalDuplicateRowsCollapsed=identical, uniqueRows=len(rows), sessions=len(days))
    cache.mkdir(exist_ok=True, parents=True)
    closes.to_pickle(cache / 'closes.pkl')
    volumes.to_pickle(cache / 'volumes.pkl')
    (HERE / 'source-objects.json').write_text(json.dumps(evidence, indent=1) + '\n')
    return closes, volumes


def cost_rate(ticker, date, dw):
    spec = CFG['portfolio']['costs']['etf' if ticker == BENCH else 'stock']
    bps = spec['commissionBps'] + spec['spreadBps'] / 2
    if ticker != BENCH and dw < 0:
        bps += max((r for r in spec['sellTaxSchedule'] if r['effectiveDate'] <= date),
                   key=lambda r: r['effectiveDate'])['sellTaxBps']
    return bps / 10000


def replay(closes, volumes, holdings, cost_mult=1., remove=(), remove_industry=None):
    """Reconstruct a fixed recorded weight path using TR index units.

    Reproduce the disclosed pre-cost-weight fee convention. Also report the cash
    conservation residual against fees computed from the actual unit changes.
    Removal diagnostics replace the removed sleeve by ETF, never reselect/refit.
    """
    c = closes.loc['2016-01-11':'2026-09-14']
    carry = closes.ffill().loc[c.index]
    ix = {t: j for j, t in enumerate(c.columns)}
    pc = carry.to_numpy()
    raw = c.to_numpy()
    vol = volumes.reindex(c.index).to_numpy()
    last = {t: closes[t].last_valid_index() for t in c}
    terminal = {t: d for t, d in last.items() if d is not None and
                closes.index.get_loc(d) < len(closes) - 6 and t != BENCH}
    sched = {x['date']: x for x in holdings}
    units = {BENCH: 1. / pc[0, ix[BENCH]]}
    nav, turn, contributions, ledger, issues, fees = [], 0., defaultdict(lambda: np.zeros(len(c))), [], [], []
    pre_value_prev = {BENCH: 1.}
    cumulative_residual = 0.
    industries = json.loads(gzip.decompress((ROOT / 'data/kr-industry-membership-foundation-v4/state/intervals.json.gz').read_bytes()))
    for k, date in enumerate(c.index):
        ds = str(date.date())
        old = {t: u * pc[k, ix[t]] if t not in terminal or date <= terminal[t] else 0. for t, u in units.items()}
        gross = sum(old.values())
        assert np.isfinite(gross) and gross > 0
        if k:
            for t in set(old) | set(pre_value_prev):
                contributions[t][k] = (old.get(t, 0.) - pre_value_prev.get(t, 0.)) / nav[-1]
        fee = 0.
        if ds in sched:
            h = sched[ds]
            new = dict(h['weights'])
            for t in list(new):
                ind = next((r.get('research_industry_id') for r in industries.get(t, [])
                            if (r.get('start') is None or r['start'] <= ds) and
                            (r.get('end') is None or ds < r['end'])), None)
                if t in remove or (remove_industry is not None and ind == remove_industry):
                    new.pop(t)
            # Preserve submitted rounded ETF weight unless doing explicit removal.
            new[BENCH] = 1 - sum(new.values()) if remove or remove_industry else h['etf']
            oldw = {t: v / gross for t, v in old.items()}
            all_names = set(oldw) | set(new)
            for t in all_names:
                dw = new.get(t, 0.) - oldw.get(t, 0.)
                if abs(dw) > 1e-9:
                    fee += abs(dw) * cost_rate(t, ds, dw) * cost_mult
                if t != BENCH:
                    turn += abs(dw)
                if t != BENCH and abs(dw) > 2e-6 and not (
                    np.isfinite(raw[k, ix[t]]) and vol[k, ix[t]] > 0
                ):
                    issues.append({'date': ds, 'ticker': t, 'kind': 'NONTRADABLE_WEIGHT_CHANGE', 'dw': dw})
            net = gross * (1 - fee)
            new_units = {t: w * net / pc[k, ix[t]] for t, w in new.items() if w > 0}
            actual_fee = 0.
            for t in set(units) | set(new_units):
                change = (new_units.get(t, 0.) - units.get(t, 0.)) * pc[k, ix[t]]
                if t in terminal and date > terminal[t]:
                    continue
                actual_fee += abs(change) * cost_rate(t, ds, change) * cost_mult
                if t != BENCH and vol[k, ix[t]] <= 0 and abs(change) > 1e-10:
                    issues.append({'date': ds, 'ticker': t, 'kind': 'LOCKED_UNITS_CHANGED', 'notional': change})
            balance_error = gross - sum(new_units[t] * pc[k, ix[t]] for t in new_units) - actual_fee
            cumulative_residual += balance_error / gross
            fees.append({'date': ds, 'feeCharged': gross * fee, 'actualUnitTradeFee': actual_fee,
                         'cashConservationResidual': balance_error, 'weightSum': sum(new.values()),
                         'etfWeight': new[BENCH]})
            units = new_units
        net = sum(u * pc[k, ix[t]] if t not in terminal or date <= terminal[t] else 0. for t, u in units.items())
        nav.append(net)
        pre_value_prev = {t: u * pc[k, ix[t]] if t not in terminal or date <= terminal[t] else 0. for t, u in units.items()}
        for t, u in units.items():
            ledger.append({'date': ds, 'ticker': t, 'trIndexUnits': u, 'trIndexClose': pc[k, ix[t]],
                           'value': pre_value_prev[t], 'nav': net, 'cash': 0.})
    return pd.Series(nav, index=c.index), contributions, turn, fees, issues, ledger, cumulative_residual


def metrics(nav, rf, turnover):
    r = nav.pct_change().dropna()
    yrs = len(r) / 252
    return {'cagr': float(nav.iloc[-1] ** (1 / yrs) - 1),
            'calendarCagr': float(nav.iloc[-1] ** (365.2425 / (nav.index[-1] - nav.index[0]).days) - 1),
            'mdd': float((nav / nav.cummax() - 1).min()),
            'sharpe': float((r - rf.reindex(r.index)).mean() / r.std() * np.sqrt(252)),
            'annualStockTurnover': float(turnover / yrs), 'finalNav': float(nav.iloc[-1]),
            'sessions': len(nav)}


def block_ci(matrix, block, reps=2000):
    """SAME circular time blocks for all columns. Arithmetic annualized mean gaps."""
    x = np.asarray(matrix)
    rng = np.random.default_rng(11)
    n = len(x)
    stats = np.empty((reps, x.shape[1]))
    for j in range(reps):
        idx = ((rng.integers(n, size=int(np.ceil(n / block)))[:, None] + np.arange(block)) % n).ravel()[:n]
        stats[j] = x[idx].mean(axis=0) * 252
    return {'blockSessions': block, 'reps': reps, 'annualMean': (x.mean(axis=0) * 252).tolist(),
            'ci95': np.percentile(stats, [2.5, 97.5], axis=0).T.tolist(),
            'fractionAtOrBelowZero': (stats <= 0).mean(axis=0).tolist(),
            'status': 'DESCRIPTIVE_POST_SELECTION_NOT_FAMILYWISE_CORRECTED'}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cache', type=Path, default=Path('/workspace/audit-cache'))
    args = ap.parse_args()
    if (args.cache / 'closes.pkl').exists():
        closes = pd.read_pickle(args.cache / 'closes.pkl')
        volumes = pd.read_pickle(args.cache / 'volumes.pkl')
    else:
        closes, volumes = load_prices(args.cache)
    days = closes.index
    events = json.loads((ROOT / 'data/bok-policy-rates.json').read_text())['events']
    rates = pd.Series({pd.Timestamp(x['date']): x['annualRatePct'] for x in events}).sort_index()
    rf = rates.reindex(rates.index.union(days)).ffill().reindex(days) / 100 / 252
    holds = json.loads(gzip.decompress((SUB / 'results/holdings-all.json.gz').read_bytes()))
    out, navs, coverage, subjects = {}, {}, [], {}
    for view, paths in holds.items():
        board = json.loads((SUB / f'results/leaderboard-{view}.json').read_text())['leaderboard']
        rankings = json.loads((SUB / f'results/rankings-{view}.json').read_text())
        top = {x['strategy'] for key in ('absoluteTop10', 'riskAdjustedTop10') for x in rankings[key]}
        out[view], navs[view] = {}, {}
        for sid, path in paths.items():
            n, contrib, turn, fees, issues, ledger, residual = replay(closes, volumes, path)
            met = metrics(n, rf, turn)
            diff = {key: met[key] - board[sid][key] for key in ('cagr', 'mdd', 'sharpe', 'annualStockTurnover')}
            navs[view][sid] = n
            out[view][sid] = {'reported': {k: board[sid][k] for k in diff}, 'independentConditional': met,
                              'difference': diff, 'cashConservationRelativeResidualSum': residual,
                              'issues': issues[:20], 'issueCount': len(issues),
                              'status': 'CONDITIONAL_WEIGHT_PATH_REPLAY',
                              'executionStatus': 'NOT_INDEPENDENTLY_REPRODUCED'}
            if sid in top:
                coverage.append({'view': view, 'strategy': sid, 'rebalances': len(path),
                                 'absTop10': sid in {x['strategy'] for x in rankings['absoluteTop10']},
                                 'riskTop10': sid in {x['strategy'] for x in rankings['riskAdjustedTop10']},
                                 **met, **{'delta_' + k: v for k, v in diff.items()}})
            if (view, sid) in [('gated', 'RULE_INDUSTRY_MOMENTUM'), ('forced', 'XGB_CI_RANK_h1')]:
                tag = view + '-' + sid
                pd.DataFrame(ledger).to_csv(HERE / f'ledger-{tag}.csv.gz', index=False, compression={'method': 'gzip', 'mtime': 0})
                pd.DataFrame(fees).to_csv(HERE / f'fees-{tag}.csv', index=False)
                bn = navs[view].get('RULE_ETF_ONLY')
                if bn is None:
                    bn = closes[BENCH].reindex(n.index) / closes.at[n.index[0], BENCH]
                r, br = n.pct_change().iloc[1:], bn.pct_change().iloc[1:]
                byname = sorted(((t, float(a.sum())) for t, a in contrib.items() if t != BENCH), key=lambda z: -z[1])
                annual = {}
                for y in sorted(set(n.index.year)):
                    mask = r.index.year == y
                    annual[str(y)] = {'strategy': float((1 + r[mask]).prod() - 1), 'etf': float((1 + br[mask]).prod() - 1)}
                leaveyears = {str(y): {'strategy': float((1 + r[r.index.year != y]).prod() ** (252 / (r.index.year != y).sum()) - 1),
                                     'etf': float((1 + br[br.index.year != y]).prod() ** (252 / (br.index.year != y).sum()) - 1)}
                              for y in sorted(set(r.index.year))}
                sensitivity = {}
                for label, kwargs in [('costX2FixedPath', {'cost_mult': 2.}),
                                      ('removeTop1ToEtf', {'remove': [byname[0][0]]}),
                                      ('removeTop5ToEtf', {'remove': [t for t, _ in byname[:5]]}),
                                      ('removeDefenseToEtf', {'remove_industry': 'CAPITAL_GOODS_DEFENSE'}),
                                      ('removeElectronicsToEtf', {'remove_industry': 'ELECTRONICS_ELECTRICAL'})]:
                    nn, _, tt, *_ = replay(closes, volumes, path, **kwargs)
                    sensitivity[label] = metrics(nn, rf, tt)
                subjects[tag] = {'annual': annual, 'topContributions': byname[:20], 'leaveYearOut': leaveyears,
                                 'fixedSelectionSensitivities': sensitivity,
                                 'blockVsEtf': {str(b): block_ci((r - br).to_numpy()[:, None], b) for b in (126, 252)}}
        pd.DataFrame(navs[view]).to_csv(HERE / f'conditional-navs-{view}.csv.gz', compression={'method': 'gzip', 'mtime': 0})
        print(view, 'replayed', len(paths), flush=True)
    x = navs['forced']['XGB_CI_RANK_h1'].pct_change().iloc[1:]
    lin = navs['forced']['RIDGE_CI_RANK_a2'].pct_change().iloc[1:]
    subjects['forced-XGB_CI_RANK_h1']['vsLinear'] = {str(b): block_ci((x - lin).to_numpy()[:, None], b) for b in (126, 252)}
    (HERE / 'recalculation.json').write_text(json.dumps(out, indent=1, allow_nan=False) + '\n')
    (HERE / 'winner-evidence.json').write_text(json.dumps(subjects, indent=1, allow_nan=False) + '\n')
    pd.DataFrame(coverage).to_csv(HERE / 'top10-coverage.csv', index=False)


if __name__ == '__main__':
    main()
