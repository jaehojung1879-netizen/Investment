"""One registered historical evaluation of A1/B1 (A2 descriptive) over admitted inputs.

``evaluate`` is pure: it is handed the admitted market and the frozen cohort and
returns the result document. It is reachable from real data only through
``run.execute`` (authorization + admission). Tests call it on invented markets.
"""
from __future__ import annotations

from datetime import date

import numpy as np

from . import contract as C
from . import decision as DEC
from . import engine as E
from . import inference as INF

# Books actually simulated: the executed primaries, plus A2 only as A1's descriptive comparator.
HYPOTHESES = tuple(C.EXECUTED_PRIMARY) + (('A2',) if 'A1' in C.EXECUTED_PRIMARY else ())


def _union_calendar(paths: dict[str, dict]) -> list[str]:
    days = sorted({d for p in paths.values() if p.get('complete') for d in p['dates']})
    return days


def _aligned(path: dict, calendar: list[str], key: str = 'D') -> np.ndarray:
    """Series on the joint calendar; sessions outside this book's own span are ETF-vs-ETF (0)."""
    by = dict(zip(path['dates'], path[key]))
    return np.array([by.get(d, 0.0) for d in calendar], dtype=float)


def _point(slots, horizon, market, keep) -> float | None:
    sub = [s for s in slots if keep(s)]
    if not sub:
        return None
    p = E.simulate(sub, **market, mult=1.0)
    if not p['complete'] or not p['D']:
        return None
    return C.HORIZONS[horizon] * float(np.mean(p['D']))


def evaluate(events: dict[str, list[dict]], market: dict, *, pinned_industry: dict[str, str | None],
             characteristics: dict | None = None, blocked: list[str] | None = None,
             draws: int | None = None) -> dict:
    """``events[h]`` = cohort rows (ticker, corp_code, rcept_no, signalSession, entrySession,
    independent, industry). ``market`` = kwargs for engine.simulate (sessions, levels, etf, cash,
    tradable, terminal). ``characteristics[rcept_no]`` = {'event': row, 'candidates': rows,
    'peerReturns': {peer id: H gross return}, 'eventReturn': H gross return} or absent."""
    blocked = list(blocked or [])
    out = {'studyId': C.STUDY_ID, 'evidenceClass': 'EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY',
           'promotionEligible': False, 'horizons': {}}
    sim_market = {k: market[k] for k in ('sessions', 'levels', 'etf', 'cash', 'tradable', 'terminal')}
    for horizon in C.HORIZONS:
        H = C.HORIZONS[horizon]
        slots, excluded, paths = {}, {}, {}
        for h in HYPOTHESES:
            slots[h], excluded[h] = E.build_slots(events.get(h, []), horizon, market['sessions'],
                                                  market['levels'], market['etf'], market['tradable'])
            for m in C.COST_MULTIPLIERS:
                paths[(h, m)] = E.simulate(slots[h], **sim_market, mult=m)
        primary_paths = {f'{h}x{m}': p for (h, m), p in paths.items()}
        calendar = _union_calendar(primary_paths)
        cols, incomplete = {}, {}
        for (h, m), p in paths.items():
            if p['complete'] and p['slots'] and calendar:
                cols[f'{h}x{m:g}'] = _aligned(p, calendar)
            elif not p['complete']:
                incomplete[f'{h}x{m:g}'] = p['failure']
        if 'A1x1' in cols and 'A2x1' in cols:
            cols['A1minusA2x1'] = cols['A1x1'] - cols['A2x1']
        blocks = {C.BOOTSTRAP['block'][horizon], *C.BOOTSTRAP['sensitivityBlocks'][horizon]}
        boot = {b: INF.synchronized_bootstrap(cols, b, draws=draws) for b in blocks} if cols else {}
        hz = {'calendarSessions': len(calendar), 'calendarStart': calendar[0] if calendar else None,
              'calendarEnd': calendar[-1] if calendar else None, 'books': {}, 'incomplete': incomplete}
        for name, series in cols.items():
            s = INF.summarize(series, horizon, {b: boot[b][name] for b in blocks})
            hz['books'][name] = s
        for h in HYPOTHESES:
            p = paths[(h, 1.0)]
            entry = {'slots': len(slots[h]), 'excluded': _count(excluded[h])}
            if p['complete'] and p['dates']:
                entry['turnoverOneWay'] = p['turnover']
                entry['simpleEtfExcess'] = H * float(np.mean(np.array(p['book']) - np.array(p['etf'])))
                entry['exposureTerm'] = H * float(np.mean(np.array(p['control']) - np.array(p['etf'])))
                entry['selectionTerm'] = H * float(np.mean(p['D']))
                ars = [E.slot_holding_return(s, market['sessions'], market['levels'], market['etf'],
                                             market['cash'], market['terminal']) for s in slots[h]]
                pairs = [(a, s) for a, s in zip(ars, slots[h]) if a is not None]
                entry['eventLevel'] = E.two_way_cluster_mean(
                    [a for a, _ in pairs], [s.issuer for _, s in pairs],
                    [date.fromisoformat(s.entry_date).isocalendar()[:2] for _, s in pairs])
                entry['eventLevel']['unresolved'] = len(ars) - len(pairs)
            hz['books'].setdefault(f'{h}x1', {}).update(entry)
        out['horizons'][horizon] = hz

    # ---- decisions: primary horizon only; H252, A2 and splits are descriptive
    hz = out['horizons'][C.PRIMARY_HORIZON]
    H = C.HORIZONS[C.PRIMARY_HORIZON]
    pvals = {'H3': 1.0, **{h: 1.0 for h in C.NOT_RUN}}
    for h in C.EXECUTED_PRIMARY:
        b = hz['books'].get(f'{h}x1')
        if b and 'pBootstrapTwoSided' in b:
            pvals[h] = b['pBootstrapTwoSided']
        else:
            pvals[h] = 1.0
    reject = INF.holm(pvals)
    out['holm'] = {'pValues': pvals, 'reject': reject}
    decisions = {h: {'verdict': v, 'reasons': ['MDE_GT_2X_MEE_BEFORE_ANY_OUTCOME'], 'pValueSlot': 1.0}
                 for h, v in C.NOT_RUN.items()}
    slots126 = {}
    for h in C.EXECUTED_PRIMARY:
        slots126[h], _ = E.build_slots(events.get(h, []), C.PRIMARY_HORIZON, market['sessions'],
                                       market['levels'], market['etf'], market['tradable'])
        b = hz['books'].get(f'{h}x1', {})
        why = list(blocked)
        if f'{h}x1' in hz['incomplete'] or 'delta' not in b:
            why.append(f'{h}_PATH_INCOMPLETE')
        two = hz['books'].get(f'{h}x2', {}).get('delta')
        sl = slots126[h]
        regime = {
            'preValueUp': _point(sl, C.PRIMARY_HORIZON, sim_market, lambda s: s.entry_date < C.VALUE_UP),
            'postValueUp': _point(sl, C.PRIMARY_HORIZON, sim_market, lambda s: s.entry_date >= C.VALUE_UP),
            'excluding2025_2026': _point(sl, C.PRIMARY_HORIZON, sim_market,
                                         lambda s: not (C.RECENT_CONCENTRATION[0] <= s.entry_date
                                                        <= C.RECENT_CONCENTRATION[1])),
        }
        ind = pinned_industry.get(h)
        industry = {'excludingLargestIndustry': (
            _point(sl, C.PRIMARY_HORIZON, sim_market, lambda s: s.meta.get('industry') != ind)
            if ind else None)}
        matched = _matched(h, sl, characteristics)
        decisions[h] = DEC.decide(
            h, blocked=why, primary=b if 'delta' in b else None, cost2x_delta=two,
            holm_reject=reject.get(h), dependence_uncertain=(INF.dependence_uncertain(b)
                                                             if 'delta' in b else None),
            regime=regime, industry=industry, matched=matched)
        decisions[h]['checks'] = {'regime': regime, 'industry': industry, 'matched': matched}
        decisions[h]['meeDelta'] = C.MEE[C.PRIMARY_HORIZON]
    out['decisions'] = decisions
    out['portfolioStep'] = ('NOT_REACHED' if not any(d['verdict'] == 'DEVELOPMENT_SUPPORT'
                                                       for d in decisions.values())
                            else 'SEPARATE_0_TO_5_NAME_PREREGISTRATION_REQUIRED')
    return out


def _matched(h: str, slots, characteristics) -> dict:
    keys = ['plain'] + (['industryMatched'] if h == 'B1' else [])
    if not characteristics:
        return {k: None for k in keys}
    res = {}
    for k in keys:
        vals, g1, g2 = [], [], []
        for s in slots:
            c = characteristics.get(s.key)
            if not c:
                continue
            peers = E.match_peers(c['event'], c['candidates'], exact_industry=(k == 'industryMatched'))
            if peers is None or c.get('eventReturn') is None:
                continue
            pr = [c['peerReturns'].get(p) for p in peers]
            if any(x is None for x in pr):
                continue
            vals.append(c['eventReturn'] - sum(pr) / len(pr))
            g1.append(s.issuer)
            g2.append(date.fromisoformat(s.entry_date).isocalendar()[:2])
        est = E.two_way_cluster_mean(vals, g1, g2) if vals else {'se': None}
        res[k] = est['mean'] if est.get('se') is not None else None
    return res


def _count(excluded: dict) -> dict:
    out: dict = {}
    for v in excluded.values():
        out[v] = out.get(v, 0) + 1
    return out
