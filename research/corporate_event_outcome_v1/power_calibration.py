"""Second-moment-only power for the registered calendar-time A1/B1 books.

Reads the KRX as-traded bars (signal-history ``ledger/prices/kr``) and emits ONLY:
per ticker-year residual SDs and market betas, per-year average residual correlation
within and across PIT/extended research industries, and the implied SE/MDE of
delta_H. No mean return of any stock, event, window or book is computed or written
(``test_power_calibration_emits_no_first_moment`` checks the output keys).

Daily D_t of an equal-slot funded beta-matched book is approximated by the slots'
idiosyncratic residuals: var(D_t) = (1/n_t^2) * sum_ij q_i q_j s_i s_j rho_ij, with
rho = 1 (i = j), the year's within-industry average (same research industry) or the
cross-industry average otherwise, plus a beta-estimation term (SE 0.08, market SD
1%/day). Days are treated as independent; serial dependence and factor-exposure
mismatch would only widen the SE, so the MDE here is a LOWER bound.

    SE(delta_H) = H * sqrt(sum_t var(D_t)) / T,   MDE = (z_{1-.05/6} + z_.80) * SE
Gate (Owner contract #292 c.6671600416): MDE <= MEE GO; <= 2*MEE MARGINAL; else NO_GO.
"""
from __future__ import annotations

import gzip
import itertools
import json
import os
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd

from pipeline import replay_calendar as RC

from . import contract as C

HERE = Path(__file__).resolve().parent
EVENTS = C.COHORT_DIR / 'data' / 'cohort-events-v1.jsonl.gz'
DAILY_LIMIT = 0.31          # a move beyond the KRX daily limit is a split/unexplained move, dropped
BETA_SE, MARKET_SD = 0.08, 0.01
CRIT = NormalDist().inv_cdf(1 - C.FWER / (2 * len(C.FAMILY_SLOTS))) + NormalDist().inv_cdf(0.80)


def residual_moments(price_dir: Path) -> tuple[dict, dict, pd.DataFrame]:
    rows = []
    for name in sorted(os.listdir(price_dir)):
        if name.startswith('krx-prices-20') and name.endswith('.jsonl.gz'):
            with gzip.open(Path(price_dir) / name, 'rt') as fh:
                for line in fh:
                    r = json.loads(line)
                    rows.append((r['ticker'], r['date'], r['close'], r['volume']))
    df = pd.DataFrame(rows, columns=['t', 'd', 'c', 'v'])
    px = df.pivot(index='d', columns='t', values='c').sort_index()
    vol = df.pivot(index='d', columns='t', values='v').reindex(px.index)
    ret = px.pct_change(fill_method=None)
    ret[(vol <= 0) | (vol.shift(1) <= 0)] = np.nan
    ret[ret.abs() > DAILY_LIMIT] = np.nan
    mkt = ret.mean(axis=1)
    year = pd.Series(ret.index.str[:4], index=ret.index)
    sig, beta = {}, {}
    resid = pd.DataFrame(index=ret.index, columns=ret.columns, dtype=float)
    for y, ix in ret.groupby(year).groups.items():
        R, m = ret.loc[ix], mkt.loc[ix]
        for t in R.columns:
            ok = R[t].notna() & m.notna()
            if ok.sum() < 120:
                continue
            x, z = m[ok].to_numpy(), R[t][ok].to_numpy()
            b = np.cov(x, z)[0, 1] / np.var(x, ddof=1)
            e = z - z.mean() - b * (x - x.mean())       # demeaned residual: a second moment only
            sig[(t, y)], beta[(t, y)] = float(np.std(e, ddof=1)), float(b)
            resid.loc[R[t][ok].index, t] = e
    return sig, beta, resid


def industry_correlations(resid: pd.DataFrame, industry: dict[str, str]) -> tuple[dict, dict]:
    year = resid.index.str[:4]
    within, cross = {}, {}
    for y in sorted(set(year)):
        R = resid[year == y]
        R = R.loc[:, R.notna().sum() >= 120]
        A = R.corr(min_periods=100).to_numpy()
        g = [industry.get(c) for c in R.columns]
        iu = np.triu_indices(len(g), 1)
        same = np.array([g[i] is not None and g[i] == g[j] for i, j in zip(*iu)], dtype=bool)
        vals = A[iu]
        ok = ~np.isnan(vals)
        within[y] = float(vals[same & ok].mean()) if (same & ok).any() else 0.0
        cross[y] = float(vals[~same & ok].mean()) if (~same & ok).any() else 0.0
    return within, cross


def ticker_industry() -> dict[str, str]:
    ext = json.loads((HERE / 'data' / 'industry-extension-v1.json').read_text(encoding='utf-8'))['labels']
    with gzip.open(HERE / 'data' / 'company-facts-v1.jsonl.gz', 'rt', encoding='utf-8') as fh:
        stock = {r['corp_code']: r.get('stock_code') for r in map(json.loads, fh)}
    return {stock[c] + '.KS': lab['group'] for c, lab in ext.items() if stock.get(c) and lab.get('group')}


def book_power(events: list[dict], sessions: list[str], ledger_end: str, sig, beta, within, cross,
               industry, hypothesis: str, horizon: int) -> dict:
    idx = {s: i for i, s in enumerate(sessions)}
    end = idx[ledger_end]
    med = float(np.median(list(sig.values())))
    rows = [e for e in events if e.get('pitGrade') and e['hypothesis'] == hypothesis
            and e['independent'][f'H{horizon}'] and idx[e['entrySession']] + horizon <= end]
    info = []
    for e in rows:
        t, y = e['stock_code'] + '.KS', e['entrySession'][:4]
        s = sig.get((t, y)) or sig.get((t, str(int(y) - 1))) or med
        b = beta.get((t, y), 1.0)
        info.append((idx[e['entrySession']], s, 1 / max(1.0, b) if b > 0 else 1.0, industry.get(t)))
    span = range(min(i for i, *_ in info), max(i for i, *_ in info) + horizon + 1)
    var, n_active = [], []
    for t in span:
        act = [x for x in info if x[0] < t <= x[0] + horizon]
        n_active.append(len(act))
        if not act:
            var.append(0.0)
            continue
        yy = sessions[t][:4]
        v = sum((q * s) ** 2 + (q * BETA_SE * MARKET_SD) ** 2 for _, s, q, _ in act)
        for a, b in itertools.combinations(act, 2):
            rho = within.get(yy, 0.0) if a[3] and a[3] == b[3] else cross.get(yy, 0.0)
            v += 2 * rho * a[2] * a[1] * b[2] * b[1]
        var.append(v / len(act) ** 2)
    T = len(span)
    se = horizon * float(np.sqrt(sum(var))) / T
    mee = C.MEE[f'H{horizon}']
    mde = CRIT * se
    zc = NormalDist().inv_cdf(1 - C.FWER / (2 * len(C.FAMILY_SLOTS)))
    return {'maturedIndependent': len(rows), 'calendarSessions': T,
            'emptySessions': sum(1 for n in n_active if n == 0),
            'meanActiveSlots': round(float(np.mean(n_active)), 1), 'maxActiveSlots': max(n_active),
            'dailySdOfDPct': round(100 * float(np.sqrt(np.mean(var))), 3),
            'seDeltaPp': round(100 * se, 2), 'mdePp': round(100 * mde, 2), 'meePp': 100 * mee,
            'gate': 'GO' if mde <= mee else 'MARGINAL' if mde <= 2 * mee else 'NO_GO',
            'powerAtMee': round(NormalDist().cdf(mee / se - zc), 3),
            'probRejectEconomicIfTrueZero': round(NormalDist().cdf((mee - zc * se) / se), 3)}


def build(price_dir: Path, ledger_end: str = '2026-10-30') -> dict:
    sig, beta, resid = residual_moments(price_dir)
    industry = ticker_industry()
    within, cross = industry_correlations(resid, industry)
    sessions = [d.strftime('%Y-%m-%d') for d in RC.sessions('2013-01-01', '2027-12-31', 'KR')]
    with gzip.open(EVENTS, 'rt', encoding='utf-8') as fh:
        events = [json.loads(line) for line in fh]
    sets = {f'{h}_H{H}': book_power(events, sessions, ledger_end, sig, beta, within, cross, industry, h, H)
            for h in ('A1', 'B1') for H in (126, 252)}
    return {'contract': 'SECOND_MOMENT_ONLY_POWER_V1', 'firstMomentsComputed': 0,
            'ledgerEnd': ledger_end, 'critical': round(CRIT, 4),
            'tickerYears': len(sig), 'medianDailyResidualSd': round(float(np.median(list(sig.values()))), 4),
            'avgWithinIndustryResidualCorr': round(float(np.mean(list(within.values()))), 4),
            'avgCrossIndustryResidualCorr': round(float(np.mean(list(cross.values()))), 4),
            'mdeIsLowerBound': 'days independent; factor-exposure mismatch and serial dependence ignored',
            'sets': sets}


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--prices', type=Path, required=True, help='signal-history ledger/prices/kr directory')
    ap.add_argument('--out', type=Path, default=HERE / 'economic-readiness-v2' / 'power-second-moment.json')
    args = ap.parse_args()
    doc = build(args.prices)
    args.out.write_text(json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps(doc['sets'], ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
