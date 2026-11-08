"""Assemble the B1 economic inputs from EXISTING sources and functions; compute no outcome.

Owner methodology decisions of 2026-11-08 (Issue #292 / #322), applied exactly:
1. Ex-date: an officially stated ex-date first; otherwise the KRX T+2 market rule on the record date and the
   pinned calendar (``cohort.dividends.market_ex_date``). Every dividend keeps its tier; a computed date is
   never promoted to "officially verified". Corrections, exceptions and unclear cases are flagged.
2. Cash: three SENSITIVITY scenarios (0%, BOK base rate, base rate + 100bp). Not an investable payoff.
3. Terminal (two B1 events): -100% is a downside stress only. No best-case recovery is invented.
4. Costs: pre-investor-tax, after trading costs (already in ``contract.COSTS``).
5. Industry: PIT v4 labels only; the non-PIT DART-KSIC extension is diagnostic and never used here.

Reused, not rebuilt: KRX bars (signal-history), ``krx_prices.frame_from_rows``, ``kr_alpha_atlas_bars.split_events``
(share-count-confirmed splits), DART dividend decisions (#320, ex-dates re-derived in #322), the audited
069500 recipe ``kr_alpha_atlas_benchmark_audit.issuer_prices / adjusted_index`` with official issuer files,
``kr_integrated_alpha_portfolio.policy_rate_in_force`` on ``data/bok-policy-rates.json``.

Price-derived level files are written to an output directory OUTSIDE the repository and only their SHA-256
is committed: anyone can regenerate them from the pinned sources, and the repository does not carry a
ready-made outcome table before execution is authorized. Integrity checks are structural (coverage, gaps,
flags); no return, mean, volatility of a holding window or book is computed here.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

from pipeline import krx_prices as KP
from pipeline import kr_alpha_atlas_bars as KB
from pipeline import kr_alpha_atlas_benchmark_audit as BA
from pipeline import kr_integrated_alpha_portfolio as IP
from pipeline import replay_calendar as RC

from . import contract as C

HERE = Path(__file__).resolve().parent
EVENTS = C.COHORT_DIR / 'data' / 'cohort-events-v1.jsonl.gz'
DIVIDENDS = C.COHORT_DIR / 'data' / 'dividend-decisions-v1.jsonl.gz'
BENCH_DIR = HERE / 'economic-readiness-v2' / 'benchmark'
BOK = C.REPO / 'data' / 'bok-policy-rates.json'
LEDGER_END = '2026-10-30'
LIMIT_CHANGE = '2015-06-15'            # KRX daily price limit 15% -> 30%
CASH_SCENARIOS = ('ZERO', 'BOK_POLICY_RATE', 'BOK_POLICY_RATE_PLUS_100BP')
TERMINAL_STRESS_MULTIPLE = 0.0         # downside stress only (Owner decision 3)


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _dump(path: Path, obj) -> str:
    raw = gzip.compress(json.dumps(obj, sort_keys=True, separators=(',', ':')).encode(), 9, mtime=0)
    Path(path).write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def b1_events() -> list[dict]:
    with gzip.open(EVENTS, 'rt', encoding='utf-8') as fh:
        return [e for e in map(json.loads, fh) if e.get('pitGrade') and e.get('hypothesis') == 'B1']


def dividends_by_ticker(tickers: set[str], sessions: list[str]) -> tuple[dict, Counter]:
    """Common cash DPS by ex-date with tier and flags; a later correction's amount replaces the original's."""
    with gzip.open(DIVIDENDS, 'rt', encoding='utf-8') as fh:
        rows = [json.loads(line) for line in fh]
    flags = Counter()
    by_key: dict = {}
    for r in sorted(rows, key=lambda x: x['rcept_no']):
        t = (r.get('stock_code') or '') + '.KS'
        if t not in tickers or not r.get('recordDate'):
            continue
        if r['kind'] == 'STOCK':
            flags['STOCK_DIVIDEND_NOT_MODELLED'] += 1
            by_key.setdefault((t, r['recordDate'], 'STOCK'), {'stock': True, 'rcept_no': r['rcept_no']})
            continue
        key = (t, r['recordDate'], 'CASH')
        prior = by_key.get(key)
        if r.get('amendment') and prior is None:
            flags['CORRECTION_WITHOUT_ORIGINAL'] += 1
        if prior is not None and r.get('amendment'):
            flags['AMOUNT_FROM_CORRECTION'] += 1
        dps = r.get('dpsCommonKrw')
        if dps in (None, '', '0', '-'):
            flags['COMMON_DPS_NOT_PARSED'] += 1
        # official ex-date: none of the retained official sources covers these windows (SEIBro raw not
        # retained by #324). The issuer's own stated relative rule and the market rule give the same date.
        ex = r.get('exDateMarketRuleCandidate')
        tier = ('FILING_STATED_RULE_EQUALS_MARKET_RULE' if r.get('exDateTier', '').startswith('FILING_STATED')
                else 'MARKET_RULE_COMPUTED_NOT_OFFICIALLY_VERIFIED')
        by_key[key] = {'exDate': ex, 'dps': float(str(dps).replace(',', '')) if dps not in (None, '', '0', '-') else None,
                       'tier': tier, 'corrected': bool(r.get('amendment')), 'rcept_no': r['rcept_no']}
    out: dict = defaultdict(dict)
    for (t, _record, kind), v in by_key.items():
        if kind == 'CASH' and v.get('exDate'):
            out[t][v['exDate']] = v
        elif kind == 'STOCK':
            out[t].setdefault('_stock', []).append(_record)
    return out, flags


def limit_for(day: str) -> float:
    return 0.15 if day < LIMIT_CHANGE else 0.30


def stock_levels(rows: list[dict], dividends: dict) -> tuple[dict, set, list]:
    """Shareholder total-return level on every session with a KRX row (suspended rows carry the close)."""
    rows = sorted(rows, key=lambda r: r['date'])
    traded = KP.frame_from_rows(rows)
    events, _unconfirmed, _stale = KB.split_events(traded)
    ratio = {str(e['date'].date()): float(e['ratio']) for e in events}
    levels, exceptions = {}, []
    prev = None
    for r in rows:
        day, close = r['date'], float(r['close'])
        if prev is None:
            levels[day] = 1.0
        else:
            f = ratio.get(day, 1.0)
            d = (dividends.get(day) or {}).get('dps') or 0.0
            gross = (close * f + d) / prev['close']
            move = close * f / prev['close'] - 1
            if day not in ratio and abs(move) > limit_for(day) + 1e-3:
                exceptions.append({'date': day, 'move': 'BEYOND_DAILY_LIMIT_UNCONFIRMED_ACTION',
                                   'sharesChanged': r.get('listedShares') != prev.get('listedShares')})
            levels[day] = levels[prev['date']] * gross
        prev = r
    tradable = {r['date'] for r in rows if (r.get('volume') or 0) > 0}
    return levels, tradable, exceptions


def benchmark_levels() -> tuple[dict, dict]:
    market, _nav = BA.issuer_prices(BENCH_DIR / 'issuer-standard-20261107.xls')
    raw = json.loads((BENCH_DIR / '069500-official-distributions.json').read_text(encoding='utf-8'))
    tmp = BENCH_DIR.parent / '.dividList.tmp.json'
    tmp.write_text(json.dumps({'dividList': raw}), encoding='utf-8')
    try:
        days = RC.sessions('2002-10-01', '2027-12-31', 'KR')
        dist = BA.issuer_distributions(tmp, days)
    finally:
        tmp.unlink(missing_ok=True)
    market = market[(market.index >= '2012-01-02') & (market.index <= LEDGER_END)]
    dist = [d for d in dist if '2012-01-02' < d['exDate'] <= LEDGER_END]
    idx = BA.adjusted_index(market, dist, shareholder=True)
    return {d: float(v) for d, v in idx.items()}, {'distributionsApplied': len(dist),
                                                   'exDateRule': 'issuer_distributions: session before record date'}


def cash_returns(sessions: list[str]) -> dict:
    doc = json.loads(BOK.read_text(encoding='utf-8'))
    events = doc['events']
    out = {s: {} for s in CASH_SCENARIOS}
    for prev, day in zip(sessions, sessions[1:]):
        gap = (pd.Timestamp(day) - pd.Timestamp(prev)).days
        rate = IP.policy_rate_in_force(events, prev)
        for name in CASH_SCENARIOS:
            pct = 0.0 if name == 'ZERO' else max(rate, 0.0) + (1.0 if name.endswith('100BP') else 0.0)
            out[name][day] = (1 + pct / 100) ** (gap / 365) - 1
    return out, {'verifiedThrough': doc.get('verifiedThrough'),
                 'sessionsAfterVerified': sum(1 for s in sessions if s > doc.get('verifiedThrough', '')),
                 'basis': 'BOK_POLICY_RATE_PROXY_SENSITIVITY_NOT_INVESTABLE'}


def build(price_dir: Path, out_dir: Path) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    events = b1_events()
    tickers = {e['stock_code'] + '.KS' for e in events}
    sessions = [d.strftime('%Y-%m-%d') for d in RC.sessions('2012-01-02', LEDGER_END, 'KR')]
    rows = defaultdict(list)
    for name in sorted(os.listdir(price_dir)):
        if name.startswith('krx-prices-20') and name.endswith('.jsonl.gz'):
            with gzip.open(Path(price_dir) / name, 'rt') as fh:
                for line in fh:
                    r = json.loads(line)
                    if r['ticker'] in tickers:
                        rows[r['ticker']].append(r)
    divs, div_flags = dividends_by_ticker(tickers, sessions)
    levels, tradable, exceptions = {}, {}, {}
    for t in sorted(tickers):
        lv, tr, ex = stock_levels(rows.get(t, []), divs.get(t, {}))
        levels[t], tradable[t], exceptions[t] = lv, sorted(tr), ex
    bench, bench_meta = benchmark_levels()
    cash, cash_meta = cash_returns(sessions)
    terminal_stress = {}
    with open(C.COHORT_DIR / 'data' / 'terminal-economics-required-v1.json', encoding='utf-8') as fh:
        term = json.load(fh)['events']
    for t in term:
        if t['hypothesis'] == 'B1' and t['classification'].startswith('TERMINAL'):
            i = sessions.index(t['lastBar'])
            terminal_stress[t['stockCode'] + '.KS'] = {'date': sessions[i + 1], 'multiple': TERMINAL_STRESS_MULTIPLE,
                                                       'basis': 'DOWNSIDE_STRESS_ONLY_NOT_A_CONSIDERATION'}
    hashes = {
        'stockTotalReturn': _dump(out_dir / 'b1-stock-total-return.json.gz', levels),
        'tradability': _dump(out_dir / 'b1-tradability.json.gz', {'sessions': sessions, 'tradable': tradable}),
        'benchmarkTotalReturn069500': _dump(out_dir / 'b1-benchmark-069500.json.gz', bench),
        'cashScenarios': _dump(out_dir / 'b1-cash-scenarios.json.gz', cash),
        'terminalStress': _dump(out_dir / 'b1-terminal-stress.json.gz', terminal_stress),
    }
    return {'events': events, 'sessions': sessions, 'levels': levels, 'tradable': tradable, 'bench': bench,
            'cash': cash, 'terminal': terminal_stress, 'divs': divs, 'divFlags': div_flags,
            'exceptions': exceptions, 'hashes': hashes, 'benchMeta': bench_meta, 'cashMeta': cash_meta}


def window_report(built: dict) -> dict:
    """Structural coverage of every matured B1 window (beta window + holding window); no return statistic."""
    sessions = built['sessions']
    idx = {s: i for i, s in enumerate(sessions)}
    out = {}
    for H in (126, 252):
        c, tiers = Counter(), Counter()
        for e in built['events']:
            if not e['independent'][f'H{H}']:
                continue
            c['independent'] += 1
            entry = idx.get(e['entrySession'])
            if entry is None or entry + H >= len(sessions):
                c['notMaturedByLedgerEnd'] += 1
                continue
            c['matured'] += 1
            t = e['stock_code'] + '.KS'
            hold = sessions[entry:entry + H + 1]
            lv = built['levels'][t]
            if not all(d in lv for d in hold):
                c['holdingWindowLevelGap_TERMINAL_OR_MISSING'] += 1
                c['terminalStressApplies'] += t in built['terminal']
            sig = idx[e['signalSession']]
            beta_days = sessions[max(0, sig - 252):sig + 1]
            if sum(d in lv for d in beta_days) < C.BETA['minPairs'] + 1:
                c['betaWindowShort'] += 1
            exc = [x for x in built['exceptions'][t] if hold[0] < x['date'] <= hold[-1]]
            if exc:
                c['holdingWindowUnconfirmedCorporateAction'] += 1
            if any(hold[0] < x['date'] <= hold[-1] for x in built['exceptions'][t]):
                pass
            stock_div = [d for d in built['divs'].get(t, {}).get('_stock', []) if hold[0] < d <= hold[-1]]
            if stock_div:
                c['holdingWindowStockDividendNotModelled'] += 1
            for d, v in built['divs'].get(t, {}).items():
                if d != '_stock' and hold[0] < d <= hold[-1]:
                    tiers[v['tier']] += 1
                    tiers['corrected'] += v['corrected']
                    tiers['dpsMissing'] += v['dps'] is None
            if not any(d in built['bench'] for d in hold[-1:]) or not all(d in built['bench'] for d in hold):
                c['benchmarkGap'] += 1
        out[f'B1_H{H}'] = {**c, 'inWindowCashDividendTiers': dict(tiers)}
    return out


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--prices', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True, help='directory OUTSIDE the repository for level files')
    ap.add_argument('--report', type=Path, default=HERE / 'economic-readiness-v2' / 'b1-input-assembly.json')
    args = ap.parse_args()
    if Path(args.out).resolve().is_relative_to(C.REPO):
        raise SystemExit('LEVEL_FILES_MUST_STAY_OUTSIDE_THE_REPOSITORY')
    built = build(args.prices, args.out)
    report = {
        'contract': 'B1_INPUT_ASSEMBLY_V1', 'returnsComputed': 0, 'ledgerEnd': LEDGER_END,
        'priceLedger': {'signalHistory': 'bad42157bf6dc3c82f2b5e10c7427f677fda0be6',
                        'shardSha256': {n: _sha(Path(args.prices) / n) for n in sorted(os.listdir(args.prices))
                                        if n.startswith('krx-prices-20')}},
        'generatedFileSha256': built['hashes'], 'tickers': len(built['levels']),
        'windows': window_report(built), 'dividendFlags': dict(built['divFlags']),
        'unconfirmedCorporateActions': {t: v for t, v in built['exceptions'].items() if v},
        'benchmark': built['benchMeta'], 'cash': built['cashMeta'],
        'terminalStress': built['terminal'],
        'ownerDecisions': '2026-11-08 Issue #292 / PR #322: ex-date rule (conditional), cash scenarios (sensitivity), '
                          'terminal partial identification (downside only), pre-tax after costs, non-PIT industry diagnostic only',
    }
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=1, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('generatedFileSha256', 'windows', 'dividendFlags', 'cash')},
                     ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
