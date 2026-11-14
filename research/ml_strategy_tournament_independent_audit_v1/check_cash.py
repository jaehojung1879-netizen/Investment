"""Self-financing correction diagnostic on the SAME frozen selections.

Still TR index units: this does not replace missing executable-share ledgers.
Costs are charged on actual notionals and suspended units are immutable.
"""
import gzip
import json

import numpy as np
import pandas as pd

from recompute import BENCH, HERE, ROOT, SUB, cost_rate, metrics


def exact_replay(closes, volumes, holdings):
    c = closes.loc['2016-01-11':]
    carry = closes.ffill().reindex(c.index)
    volume = volumes.reindex(c.index)
    terminal = {t: closes[t].last_valid_index() for t in c if t != BENCH and
                closes[t].last_valid_index() is not None and
                closes.index.get_loc(closes[t].last_valid_index()) < len(closes) - 6}
    units = {BENCH: 1 / carry[BENCH].iloc[0]}
    schedule = {r['date']: r for r in holdings}
    values, residuals = [], []
    for d in c.index:
        ds = str(d.date())
        prices = carry.loc[d]
        old = {t: q * prices[t] for t, q in units.items() if t not in terminal or d <= terminal[t]}
        gross = sum(old.values())
        if ds in schedule:
            target = schedule[ds]['weights']
            all_names = set(old) | set(target)
            locked = {t: old.get(t, 0) for t in all_names if t != BENCH and
                      not (np.isfinite(c.at[d, t]) and volume.at[d, t] > 0) and old.get(t, 0) > 0}
            weights = {t: w for t, w in target.items() if t not in locked and
                       np.isfinite(c.at[d, t]) and volume.at[d, t] > 0}

            def allocate(net):
                available = max(0, net - sum(locked.values()))
                wanted = sum(weights.values()) * net
                scale = min(1, available / wanted) if wanted else 1
                final = {**locked, **{t: w * net * scale for t, w in weights.items()}}
                final[BENCH] = max(0., net - sum(final.values()))
                return final

            net = gross
            for _ in range(30):
                new = allocate(net)
                fee = sum(abs(new.get(t, 0) - old.get(t, 0)) * cost_rate(t, ds, new.get(t, 0) - old.get(t, 0))
                          for t in set(new) | set(old))
                nxt = gross - fee
                if abs(nxt - net) < 1e-14:
                    net = nxt
                    break
                net = nxt
            new = allocate(net)
            fee = sum(abs(new.get(t, 0) - old.get(t, 0)) * cost_rate(t, ds, new.get(t, 0) - old.get(t, 0))
                      for t in set(new) | set(old))
            residuals.append(gross - sum(new.values()) - fee)
            before_units = units
            units = {t: val / prices[t] for t, val in new.items() if val > 0}
            for t in locked:
                assert abs(units[t] - before_units[t]) < 1e-14
        values.append(sum(q * prices[t] for t, q in units.items() if t not in terminal or d <= terminal[t]))
    return pd.Series(values, index=c.index), max(map(abs, residuals))


def main():
    c = pd.read_pickle('/workspace/audit-cache/closes.pkl')
    v = pd.read_pickle('/workspace/audit-cache/volumes.pkl')
    hold = json.loads(gzip.decompress((SUB / 'results/holdings-all.json.gz').read_bytes()))
    events = json.loads((ROOT / 'data/bok-policy-rates.json').read_text())['events']
    rates = pd.Series({pd.Timestamp(x['date']): x['annualRatePct'] for x in events}).sort_index()
    rf = rates.reindex(rates.index.union(c.index)).ffill().reindex(c.index) / 100 / 252
    out = {}
    for view, sid in [('gated', 'RULE_INDUSTRY_MOMENTUM'), ('forced', 'XGB_CI_RANK_h1')]:
        n, residual = exact_replay(c, v, hold[view][sid])
        met = metrics(n, rf, 0)
        met['annualStockTurnover'] = None
        out[view + '-' + sid] = {'metrics': met, 'maxAbsCashResidual': residual,
                                  'status': 'FIXED_SELECTION_CASH_CONSERVATION_DIAGNOSTIC',
                                  'turnover': 'NOT_RECOMPUTED_IN_THIS_DIAGNOSTIC',
                                  'limit': 'TR units, missing original cash/share ledger; not certified investable NAV'}
    (HERE / 'cash-diagnostic.json').write_text(json.dumps(out, indent=1, allow_nan=False) + '\n')
    print(json.dumps(out, indent=1))


if __name__ == '__main__':
    main()
