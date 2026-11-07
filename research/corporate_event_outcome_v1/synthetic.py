"""Invented markets for tests and the outcome-free dry run. Never real data.

``world(alpha_daily=...)`` plants a known selection edge: event names earn
``beta*R_m + (1-beta)*R_c + alpha`` per session while held, so a correct engine
must recover delta_H ~= H * alpha * (average invested share q).
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np

LABEL = 'SYNTHETIC_FIXTURE_NOT_MARKET_DATA'


def sessions(n: int, start: str = '2013-01-02') -> list[str]:
    d, out = date.fromisoformat(start), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def world(*, n_sessions=1400, n_names=40, n_events=60, horizon=126, alpha_daily=0.0,
          beta_range=(0.6, 1.4), seed=7, hypothesis='A1', vol=0.015):
    rng = np.random.default_rng(seed)
    days = sessions(n_sessions)
    rm = rng.normal(0.0003, 0.01, n_sessions)
    rc = np.full(n_sessions, 0.0001)
    etf = dict(zip(days, np.cumprod(1 + rm)))
    cash = {d: float(r) for d, r in zip(days, rc)}
    betas = rng.uniform(*beta_range, n_names)
    tickers = [f'S{i:03d}' for i in range(n_names)]
    rets = {t: betas[i] * rm + (1 - betas[i]) * rc + rng.normal(0, vol, n_sessions)
            for i, t in enumerate(tickers)}
    events, last_exit = [], {}
    starts = sorted(rng.integers(300, n_sessions - horizon - 2, n_events))
    for k, s in enumerate(starts):
        t = tickers[k % n_names]
        if last_exit.get(t, -1) >= s:
            continue
        entry = int(s) + 1
        rets[t][entry + 1:entry + 1 + horizon] += alpha_daily
        last_exit[t] = entry + horizon
        events.append({'rcept_no': f'R{k:05d}', 'ticker': t, 'corp_code': f'C{t}',
                       'signalSession': days[s], 'entrySession': days[entry],
                       'independent': {'H126': True, 'H252': entry + 252 < n_sessions and k % 2 == 0},
                       'hypothesis': hypothesis, 'industry': 'IND_A' if k % 3 else 'IND_B'})
    levels = {t: dict(zip(days, np.cumprod(1 + r))) for t, r in rets.items()}
    tradable = {t: set(days) for t in tickers}
    market = {'sessions': days, 'levels': levels, 'etf': etf, 'cash': cash,
              'tradable': tradable, 'terminal': {}}
    return market, events
