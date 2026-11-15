"""Only the v1 simulation loop is versioned: retry an expired frozen inventory.

All beta, slot, targeting, cost and rebalancing arithmetic is inherited from
the unchanged sealed engine. No historical invocation happens at import.
"""
from . import engine as E


def simulate(slots, sessions, levels, etf, cash, tradable, terminal, mult=1.0):
    if not slots:
        return E.simulate([], sessions, levels, etf, cash, tradable, terminal, mult)
    start, nominal_end = min(s.entry for s in slots), max(s.exit for s in slots)
    wb, wc = {E.ETF: 1.0}, {E.ETF: 1.0}
    out = {'dates': [], 'book': [], 'control': [], 'etf': [], 'D': []}
    turn, converted, current = {'book': 0.0, 'control': 0.0}, set(), []
    deferred, resumed = set(), []
    ruined = False
    try:
        for i in range(start, len(sessions)):
            day, rb, rc = sessions[i], 0.0, 0.0
            if i > start:
                prev = sessions[i - 1]
                for book, w in (('book', wb), ('control', wc)):
                    if book == 'book' and ruined:
                        continue
                    gross, grown = 0.0, {}
                    for k, v in w.items():
                        t = terminal.get(k)
                        r = (t['multiple'] - 1 if t and t['date'] == day else
                             E._ret(k, day, prev, levels, etf, cash, terminal))
                        if r is None:
                            raise E.Incomplete('MISSING_RETURN_NO_CITED_ECONOMICS', day, k)
                        gross += v * r
                        grown[k] = v * (1 + r)
                    total = sum(grown.values())
                    if total <= 0:
                        if total == 0 and book == 'book':
                            ruined, rb = True, -1.0
                            w.clear()
                            continue
                        raise E.Incomplete('INVALID_NEGATIVE_CAPITAL_OR_CONTROL_RUIN', day)
                    w.clear()
                    w.update({k: v / total for k, v in grown.items() if v > 0})
                    if book == 'book':
                        rb = gross
                    else:
                        rc = gross
                for k in list(wb):
                    t = terminal.get(k)
                    if k not in (E.ETF, E.CASH) and t and t['date'] == day:
                        wb[E.CASH] = wb.get(E.CASH, 0.0) + wb.pop(k)
                        converted.add(k)
            active = [s for s in slots if s.entry <= i < s.exit]
            keys, active_tickers = [s.key for s in active], {s.ticker for s in active}
            expired = {k for k in wb if k not in (E.ETF, E.CASH) and k not in active_tickers}
            ready = {k for k in expired if day in tradable.get(k, ())}
            cb = cc = 0.0
            if keys != current or ready:
                frozen = {k for k in wb if k not in (E.ETF, E.CASH) and day not in tradable.get(k, ())}
                deferred.update(expired & frozen)
                resumed.extend({'ticker': k, 'soldOn': day} for k in sorted(ready & deferred))
                tb = E._target(active, control=False, converted=frozenset(converted))
                if ruined:
                    wb, cb, tob = {}, 0.0, 0.0
                else:
                    wb, cb, tob = E._rebalance(wb, tb, frozen, day, mult)
                wc, cc, toc = E._rebalance(wc, E._target(active, control=True), set(), day, mult)
                turn['book'] += tob
                turn['control'] += toc
                current = keys
            nb, nc = (1 + rb) * (1 - cb) - 1, (1 + rc) * (1 - cc) - 1
            re = 0.0 if i == start else etf[day] / etf[sessions[i - 1]] - 1
            for key, value in (('dates', day), ('book', nb), ('control', nc), ('etf', re), ('D', nb - nc)):
                out[key].append(value)
            residual = [k for k in wb if k not in (E.ETF, E.CASH)]
            if i >= nominal_end and not residual:
                out.update(complete=True, failure=None, turnover=turn, slots=len(slots),
                           resumedExits=resumed, extendedBeyondNominalExit=i > nominal_end, capitalExhausted=ruined)
                return out
        raise E.Incomplete('EXIT_STILL_UNTRADABLE_AT_SOURCE_CUTOFF', sessions[-1])
    except E.Incomplete as exc:
        return {'complete': False, 'failure': {'code': exc.code, 'date': exc.day, 'ticker': exc.ticker},
                'slots': len(slots), 'resumedExits': resumed}
