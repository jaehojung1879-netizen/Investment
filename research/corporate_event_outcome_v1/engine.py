"""Calendar-time funded beta-matched research book (Owner contract C0).

Pure functions over admitted inputs. Nothing here fetches data; ``run.execute``
is the only caller allowed to hand it real historical levels, and only after
authorization. Tests use invented markets.

Inputs (all keyed by ISO date):
- ``sessions``: ascending KR sessions covering beta windows and holding windows.
- ``levels[ticker][date]``: admitted TOTAL-RETURN index level for the stock.
- ``tradable[ticker]``: set of sessions with volume > 0.
- ``etf[date]``: 069500.KS total-return level. ``cash[date]``: investable KRW
  cash return earned ON that session (from the previous close).
- ``terminal[ticker]``: ``{'date': last session, 'multiple': consideration value /
  level on the previous session}``; after ``date`` the position is cash.

A held name with no level, no terminal record, on a session in its window makes
the path incomplete. Nothing is filled.
"""
from __future__ import annotations

import bisect
import math
from dataclasses import dataclass, field

from . import contract as C

ETF, CASH = 'ETF', 'CASH'


class Incomplete(Exception):
    def __init__(self, code: str, day: str, ticker: str | None = None):
        super().__init__(f'{code}:{day}:{ticker}')
        self.code, self.day, self.ticker = code, day, ticker


# ---------------------------------------------------------------- beta / slots
def estimate_beta(levels: dict[str, float], etf: dict[str, float], sessions: list[str],
                  signal: str) -> dict:
    """OLS beta on the 252 daily returns ending AT the signal session.

    Reads nothing after ``signal`` (tested by a future-poisoning test)."""
    i = bisect.bisect_right(sessions, signal) - 1
    if i < 0 or sessions[i] != signal:
        return {'beta': None, 'pairs': 0, 'reason': 'SIGNAL_NOT_A_SESSION'}
    window = sessions[max(0, i - C.BETA['windowReturns']):i + 1]
    xs, ys = [], []
    for prev, day in zip(window, window[1:]):
        a, b, m0, m1 = levels.get(prev), levels.get(day), etf.get(prev), etf.get(day)
        if None in (a, b, m0, m1) or a <= 0 or m0 <= 0:
            continue
        ys.append(b / a - 1)
        xs.append(m1 / m0 - 1)
    n = len(xs)
    if n < C.BETA['minPairs']:
        return {'beta': None, 'pairs': n, 'reason': 'INSUFFICIENT_PRE_SIGNAL_PAIRS'}
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 0:
        return {'beta': None, 'pairs': n, 'reason': 'ZERO_BENCHMARK_VARIANCE'}
    beta = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    if beta < 0:
        return {'beta': beta, 'pairs': n, 'reason': 'NEGATIVE_BETA_NOT_INVESTABLE'}
    return {'beta': beta, 'pairs': n, 'reason': None}


@dataclass
class Slot:
    key: str
    ticker: str
    issuer: str
    entry: int          # session index of the entry close
    exit: int           # entry + H
    beta: float
    q: float
    entry_date: str = ''
    meta: dict = field(default_factory=dict)


def build_slots(events: list[dict], horizon: str, sessions: list[str], levels: dict, etf: dict,
                tradable: dict) -> tuple[list[Slot], dict]:
    """Independent events of one hypothesis -> investable slots, with every exclusion counted."""
    h = C.HORIZONS[horizon]
    idx = {s: i for i, s in enumerate(sessions)}
    slots, excluded = [], {}
    for e in events:
        if not e.get('independent', {}).get(horizon):
            continue
        ticker = e['ticker']
        entry = idx.get(e['entrySession'])
        reason = None
        if entry is None:
            reason = 'ENTRY_NOT_A_SESSION'
        elif entry + h >= len(sessions):
            reason = 'NOT_MATURED'
        elif e['entrySession'] not in tradable.get(ticker, ()):
            reason = 'ENTRY_NOT_TRADABLE'
        if reason is None:
            b = estimate_beta(levels.get(ticker, {}), etf, sessions, e['signalSession'])
            reason = b['reason']
        if reason:
            excluded[e['rcept_no']] = reason
            continue
        beta = b['beta']
        slots.append(Slot(key=e['rcept_no'], ticker=ticker, issuer=e.get('corp_code', ticker),
                          entry=entry, exit=entry + h, beta=beta, q=1.0 / max(1.0, beta),
                          entry_date=e['entrySession'],
                          meta={'industry': e.get('industry'), 'pairs': b['pairs']}))
    return sorted(slots, key=lambda s: (s.entry, s.key)), excluded


# ---------------------------------------------------------------- simulation
def _bps(instrument: str, side: str, day: str, mult: float) -> float:
    if instrument == CASH:
        return 0.0
    if instrument == ETF:
        base = C.COSTS['etfCommissionBps'] + C.COSTS['etfHalfSpreadBps']
        tax = C.COSTS['etfSellTaxBps'] if side == 'sell' else 0.0
    else:
        base = C.COSTS['stockCommissionBps'] + C.COSTS['stockHalfSpreadBps']
        tax = C.sell_tax_bps(day) if side == 'sell' else 0.0
    return mult * (base + tax)


def _target(active: list[Slot], control: bool, converted: frozenset = frozenset()) -> dict[str, float]:
    if not active:
        return {ETF: 1.0}
    n = len(active)
    out: dict[str, float] = {}
    for s in active:
        if control:
            risky, other = s.q * s.beta, ETF
        elif s.ticker in converted:      # terminal consideration already paid: slot is cash to exit
            risky, other = 0.0, CASH
        else:
            risky, other = s.q, s.ticker
        out[other] = out.get(other, 0.0) + risky / n
        out[CASH] = out.get(CASH, 0.0) + (1 - risky) / n
    return out


def _rebalance(w: dict[str, float], target: dict[str, float], frozen: set[str], day: str,
               mult: float) -> tuple[dict[str, float], float, float]:
    """Move to ``target``; frozen (untradable) names keep their weight. Returns (new w, cost, turnover)."""
    keep = {k: v for k, v in w.items() if k in frozen and v > 1e-15}
    free = 1.0 - sum(keep.values())
    tgt = {k: v for k, v in target.items() if k not in keep}
    tot = sum(tgt.values())
    new = dict(keep)
    if tot > 0:
        for k, v in tgt.items():
            new[k] = new.get(k, 0.0) + v * free / tot
    else:
        new[CASH] = new.get(CASH, 0.0) + free
    cost = turnover = 0.0
    for k in set(w) | set(new):
        delta = new.get(k, 0.0) - w.get(k, 0.0)
        if abs(delta) < 1e-15:
            continue
        turnover += abs(delta)
        cost += abs(delta) * _bps(k, 'buy' if delta > 0 else 'sell', day, mult) / 1e4
    return {k: v for k, v in new.items() if v > 1e-15}, cost, turnover / 2


def _ret(instrument: str, day: str, prev: str, levels: dict, etf: dict, cash: dict,
         terminal: dict) -> float | None:
    if instrument == CASH:
        return cash.get(day)
    src = etf if instrument == ETF else levels.get(instrument, {})
    a, b = src.get(prev), src.get(day)
    if a is not None and b is not None and a > 0:
        return b / a - 1
    if instrument != ETF:
        t = terminal.get(instrument)
        if t and t['date'] == day:
            return t['multiple'] - 1
    return None


def simulate(slots: list[Slot], sessions: list[str], levels: dict, etf: dict, cash: dict,
             tradable: dict, terminal: dict, mult: float = 1.0) -> dict:
    """Daily net returns of the research book and its funded beta-matched control.

    Returns ``{'dates', 'book', 'control', 'etf', 'D', 'turnover', 'complete', 'failure'}``.
    """
    if not slots:
        return {'complete': True, 'dates': [], 'book': [], 'control': [], 'etf': [], 'D': [],
                'turnover': {'book': 0.0, 'control': 0.0}, 'failure': None, 'slots': 0}
    start, end = min(s.entry for s in slots), max(s.exit for s in slots)
    wb, wc = {ETF: 1.0}, {ETF: 1.0}
    out = {'dates': [], 'book': [], 'control': [], 'etf': [], 'D': []}
    turn = {'book': 0.0, 'control': 0.0}
    converted: set[str] = set()          # terminated names now held as cash
    current: list[str] = []
    try:
        for i in range(start, end + 1):
            day = sessions[i]
            rb = rc = 0.0
            if i > start:
                prev = sessions[i - 1]
                for book, w in (('book', wb), ('control', wc)):
                    gross, grown = 0.0, {}
                    for k, v in w.items():
                        r = _ret(k, day, prev, levels, etf, cash, terminal)
                        if r is None:
                            raise Incomplete('MISSING_RETURN_NO_TERMINAL_CONSIDERATION'
                                             if k not in (ETF, CASH) else f'MISSING_{k}_RETURN', day, k)
                        gross += v * r
                        grown[k] = v * (1 + r)
                    tot = sum(grown.values())
                    w.clear()
                    w.update({k: v / tot for k, v in grown.items()})
                    if book == 'book':
                        rb = gross
                    else:
                        rc = gross
                # a name whose terminal consideration was paid today becomes cash
                for k in list(wb):
                    t = terminal.get(k)
                    if k not in (ETF, CASH) and t and t['date'] == day:
                        wb[CASH] = wb.get(CASH, 0.0) + wb.pop(k)
                        converted.add(k)
            active = [s for s in slots if s.entry <= i < s.exit]
            keys = [s.key for s in active]
            cb = cc = 0.0
            if keys != current:
                frozen = {k for k in wb if k not in (ETF, CASH) and day not in tradable.get(k, ())}
                tb = _target(active, control=False, converted=frozenset(converted))
                wb, cb, tob = _rebalance(wb, tb, frozen, day, mult)
                wc, cc, toc = _rebalance(wc, _target(active, control=True), set(), day, mult)
                turn['book'] += tob
                turn['control'] += toc
                current = keys
            nb, nc = (1 + rb) * (1 - cb) - 1, (1 + rc) * (1 - cc) - 1
            re = 0.0 if i == start else etf[day] / etf[sessions[i - 1]] - 1
            out['dates'].append(day)
            out['book'].append(nb)
            out['control'].append(nc)
            out['etf'].append(re)
            out['D'].append(nb - nc)
    except Incomplete as exc:
        return {'complete': False, 'failure': {'code': exc.code, 'date': exc.day, 'ticker': exc.ticker},
                'slots': len(slots)}
    out.update(complete=True, failure=None, turnover=turn, slots=len(slots))
    return out


# ---------------------------------------------------------------- event level
def slot_holding_return(s: Slot, sessions, levels, etf, cash, terminal) -> float | None:
    """Gross buy-and-hold H return of slot minus its funded control (event-level auxiliary)."""
    def growth(src_ret):
        g = 1.0
        for i in range(s.entry + 1, s.exit + 1):
            r = src_ret(sessions[i], sessions[i - 1])
            if r is None:
                return None
            g *= 1 + r
        return g
    cash_g = growth(lambda d, p: cash.get(d))
    etf_g = growth(lambda d, p: _ret(ETF, d, p, levels, etf, cash, terminal))
    t = terminal.get(s.ticker)

    def stock_r(d, p):
        if t and d > t['date']:
            return cash.get(d)
        return _ret(s.ticker, d, p, levels, etf, cash, terminal)
    stock_g = growth(stock_r)
    if None in (cash_g, etf_g, stock_g):
        return None
    book = s.q * stock_g + (1 - s.q) * cash_g
    ctrl = s.q * s.beta * etf_g + (1 - s.q * s.beta) * cash_g
    return book - ctrl


def two_way_cluster_mean(values: list[float], g1: list, g2: list) -> dict:
    """Mean and Cameron-Gelbach-Miller two-way clustered SE of the mean."""
    n = len(values)
    if n < 2 or len(set(g1)) < 2 or len(set(g2)) < 2:
        return {'n': n, 'mean': (sum(values) / n) if n else None, 'se': None,
                'reason': 'TOO_FEW_CLUSTERS'}
    m = sum(values) / n
    u = [v - m for v in values]

    def part(keys):
        acc: dict = {}
        for k, x in zip(keys, u):
            acc[k] = acc.get(k, 0.0) + x
        return sum(x * x for x in acc.values())
    var = (part(g1) + part(g2) - part(list(zip(g1, g2)))) / n ** 2
    if var <= 0:
        return {'n': n, 'mean': m, 'se': None, 'reason': 'NON_POSITIVE_VARIANCE'}
    return {'n': n, 'mean': m, 'se': math.sqrt(var), 'reason': None,
            'issuers': len(set(g1)), 'entryWeeks': len(set(g2))}


MATCH_FIELDS = ('logMcap', 'bookToMarket', 'mom12_1', 'ret21', 'beta')


def match_peers(event: dict, candidates: list[dict], *, exact_industry: bool, k: int = 3) -> list[str] | None:
    """Nearest-k non-event peers on standardized characteristics (signal-date cross-section).

    ``candidates`` rows carry ``id``, ``industry`` and every MATCH_FIELDS value as of the
    signal close. Returns None when fewer than k usable peers exist (measurement impossible).
    Ties break on peer id."""
    if any(event.get(f) is None for f in MATCH_FIELDS):
        return None
    pool = [c for c in candidates if c['id'] != event['id']
            and all(c.get(f) is not None for f in MATCH_FIELDS)]
    if exact_industry:
        if not event.get('industry'):
            return None
        pool = [c for c in pool if c.get('industry') == event['industry']]
    if len(pool) < k:
        return None
    scale = {}
    for f in MATCH_FIELDS:
        xs = [c[f] for c in pool] + [event[f]]
        mu = sum(xs) / len(xs)
        sd = math.sqrt(sum((x - mu) ** 2 for x in xs) / len(xs))
        scale[f] = sd if sd > 0 else 1.0
    dist = sorted((sum(((c[f] - event[f]) / scale[f]) ** 2 for f in MATCH_FIELDS), c['id']) for c in pool)
    return [cid for _, cid in dist[:k]]
