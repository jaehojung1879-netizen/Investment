"""Batch exploratory economics for every screened KR event hypothesis, behind one exact-hash approval.

Nothing new is engineered for the economics: the calendar-time funded beta-matched book, its control, dated
costs, the moving-block bootstrap and the two-way clustered event mean are #322's ``engine`` / ``inference``;
stock total-return levels, the audited 069500 total-return series and the three cash scenarios are #322's
``b1_inputs`` functions under the Owner's 2026-11-08 input decisions. This module only loops them over the
hypothesis sets of ``hypotheses.py`` and applies one verdict rule fixed before any outcome.

Evidence class of everything this can produce: EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY.
It can never return VERIFIED / DEVELOPMENT_SUPPORT and promotes nothing.

Unresolved terminal economics are never filled. Two paths are reported side by side:
- EXCLUDE_UNRESOLVED: events whose whole holding window is priced (conditioning on survival, disclosed);
- DOWNSIDE_STRESS: the remaining events kept with a -100% terminal (a bound, not a consideration).
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import numpy as np

from research.corporate_event_outcome_v1 import contract as C
from research.corporate_event_outcome_v1 import engine as E
from research.corporate_event_outcome_v1 import inference as INF

from . import hypotheses as HY

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
CONTRACT = HERE / 'contract-v1.json'
EVENTS = HERE / 'events-v1.jsonl.gz'
AUTHORIZATION = HERE / 'AUTHORIZATION.json'
CLAIM = HERE / 'execution-claim.json'
RESULT = HERE / 'result-v1.json'
PHRASE = 'APPROVE BROAD_ALPHA_SCREEN_V1 EXPLORATORY_ONE_SHOT {sha}'
PRIMARY, HORIZONS = 'H126', ('H126', 'H252')
MEE = {'H126': 0.03, 'H252': 0.04}                 # inherited from the registered A1/B1 contract
FWER = 0.05
PRIMARY_CASH, CASH_SENSITIVITY = 'BOK_POLICY_RATE', ('ZERO', 'BOK_POLICY_RATE_PLUS_100BP')
MIN_EFFECTIVE_BLOCKS = 4.0                         # below this a block bootstrap is not an inference
MAX_NAMES = 5
PINNED_CODE = ('research/broad_alpha_screen_v1/hypotheses.py', 'research/broad_alpha_screen_v1/screen.py',
               'research/corporate_event_outcome_v1/engine.py', 'research/corporate_event_outcome_v1/inference.py',
               'research/corporate_event_outcome_v1/contract.py', 'research/corporate_event_outcome_v1/b1_inputs.py',
               'pipeline/benchmark_alpha.py', 'pipeline/kr_alpha_atlas_bars.py', 'pipeline/krx_prices.py',
               'pipeline/kr_alpha_atlas_benchmark_audit.py')


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_events() -> dict[str, list[dict]]:
    out = defaultdict(list)
    with gzip.open(EVENTS, 'rt', encoding='utf-8') as fh:
        for e in map(json.loads, fh):
            out[e['hypothesis']].append(e)
    return out


# ------------------------------------------------------------------ inputs
def assemble(price_dir: Path, events: dict[str, list[dict]]) -> dict:
    """Levels, tradability, benchmark and cash from the pinned sources via #322's own functions."""
    from research.corporate_event_outcome_v1 import b1_inputs as B
    tickers = {e['ticker'] for rows in events.values() for e in rows}
    sessions = [d.strftime('%Y-%m-%d') for d in B.RC.sessions('2012-01-02', B.LEDGER_END, 'KR')]
    rows = defaultdict(list)
    for name in sorted(os.listdir(price_dir)):
        if name.startswith('krx-prices-20') and name.endswith('.jsonl.gz'):
            with gzip.open(Path(price_dir) / name, 'rt') as fh:
                for line in fh:
                    r = json.loads(line)
                    if r['ticker'] in tickers:
                        rows[r['ticker']].append(r)
    divs, flags = B.dividends_by_ticker(tickers, sessions)
    levels, tradable, exceptions = {}, {}, {}
    for t in sorted(tickers):
        levels[t], tr, exceptions[t] = B.stock_levels(rows.get(t, []), divs.get(t, {}))
        tradable[t] = set(tr)
    bench, _ = B.benchmark_levels()
    cash, cash_meta = B.cash_returns(sessions)
    return {'sessions': sessions, 'levels': levels, 'tradable': tradable, 'etf': bench, 'cash': cash,
            'exceptions': exceptions, 'dividendFlags': dict(flags), 'cashMeta': cash_meta}


def window_state(slot: E.Slot, market: dict) -> tuple[str, str | None]:
    """Structural only: is every session of the holding window priced, and is a gap terminal?"""
    ses, lv = market['sessions'], market['levels'].get(slot.ticker, {})
    hold = ses[slot.entry:slot.exit + 1]
    if any(hold[0] < x['date'] <= hold[-1] for x in market['exceptions'].get(slot.ticker, ())):
        return 'UNCONFIRMED_CORPORATE_ACTION_IN_WINDOW', None
    missing = [d for d in hold if d not in lv]
    if not missing:
        return 'PRICED', None
    if all(d not in lv for d in ses[ses.index(missing[0]):]):
        return 'TERMINAL_UNRESOLVED', missing[0]
    return 'MID_SERIES_GAP', None


def partition(events: list[dict], horizon: str, market: dict) -> dict:
    slots, excluded = E.build_slots(events, horizon, market['sessions'], market['levels'], market['etf'],
                                    market['tradable'])
    priced, stress, terminal, state = [], [], {}, Counter(excluded.values())
    for s in slots:
        kind, first_missing = window_state(s, market)
        state[kind] += 1
        if kind == 'PRICED':
            priced.append(s)
            stress.append(s)
        elif kind == 'TERMINAL_UNRESOLVED':
            stress.append(s)
            terminal[s.ticker] = {'date': first_missing, 'multiple': 0.0}
    return {'priced': priced, 'stress': stress, 'terminal': terminal, 'states': dict(sorted(state.items()))}


def preflight(events: dict[str, list[dict]], market: dict) -> dict:
    """Counts only. No return, mean or book is computed."""
    return {f'{h}_{hz}': {'independent': sum(e['independent'][hz] for e in rows),
                          **partition(rows, hz, market)['states']}
            for h, rows in sorted(events.items()) for hz in HORIZONS}


# ------------------------------------------------------------------ economics
def _sim(slots, market, cash, terminal, mult):
    return E.simulate(slots, market['sessions'], market['levels'], market['etf'], market['cash'][cash],
                      market['tradable'], terminal, mult=mult)


def _delta(path, horizon) -> float | None:
    if not path['complete'] or not path['D']:
        return None
    return C.HORIZONS[horizon] * float(np.mean(path['D']))


def cap_names(slots: list[E.Slot], cap: int = MAX_NAMES) -> list[E.Slot]:
    """At most ``cap`` names at once, first come first held: the 0-5 name book this signal would feed."""
    kept: list[E.Slot] = []
    for s in sorted(slots, key=lambda x: (x.entry, x.key)):
        if sum(1 for k in kept if k.entry <= s.entry < k.exit) < cap:
            kept.append(s)
    return kept


def _interval(mean, boot, level, H):
    lo, hi = INF.basic_interval(mean, boot, level)
    return [H * lo, H * hi]


def evaluate_one(hyp: str, rows: list[dict], horizon: str, market: dict, family: int, industry: dict,
                 draws: int | None = None) -> dict:
    H, sign = C.HORIZONS[horizon], HY.HYPOTHESES[hyp][0]
    part = partition(rows, horizon, market)
    slots = part['priced']
    out = {'expectedSign': sign, 'states': part['states'], 'slots': len(slots), 'issuers': len({s.issuer for s in slots})}
    if not slots:
        return {**out, 'blocked': 'NO_PRICED_SLOT'}
    paths = {m: _sim(slots, market, PRIMARY_CASH, {}, m) for m in (0.0, 1.0, 2.0, 3.0)}
    p = paths[1.0]
    if not p['complete']:
        return {**out, 'blocked': p['failure']}
    D = np.array(p['D'])
    book, ctrl, etf = np.array(p['book']), np.array(p['control']), np.array(p['etf'])
    block = C.BOOTSTRAP['block'][horizon]
    boot = INF.synchronized_bootstrap({'D': D}, block, draws=draws)['D']
    sens = {b: INF.synchronized_bootstrap({'D': D}, b, draws=draws)['D'] for b in C.BOOTSTRAP['sensitivityBlocks'][horizon]}
    m = float(D.mean())
    level = 1 - FWER / family
    se = INF.hac_se(D, C.HAC_LAG[horizon])
    years = defaultdict(float)
    for d, x in zip(p['dates'], p['D']):
        years[d[:4]] += x
    ars = [(E.slot_holding_return(s, market['sessions'], market['levels'], market['etf'], market['cash'][PRIMARY_CASH], {}), s)
           for s in slots]
    ars = [(a, s) for a, s in ars if a is not None]

    def group_mean(key):
        g = defaultdict(list)
        for a, s in ars:
            g[key(s)].append(a)
        return {str(k): {'n': len(v), 'mean': float(np.mean(v))} for k, v in sorted(g.items(), key=lambda kv: str(kv[0]))}
    regime = {
        'preValueUp': [s for s in slots if s.entry_date < C.VALUE_UP],
        'postValueUp': [s for s in slots if s.entry_date >= C.VALUE_UP],
        'excluding2025_2026': [s for s in slots if not C.RECENT_CONCENTRATION[0] <= s.entry_date <= C.RECENT_CONCENTRATION[1]],
    }
    top_industry = Counter(industry.get(s.ticker) for s in slots if industry.get(s.ticker)).most_common(1)
    if top_industry:
        regime[f'excludingLargestIndustry:{top_industry[0][0]}'] = [s for s in slots if industry.get(s.ticker) != top_industry[0][0]]
    stress = _sim(part['stress'], market, PRIMARY_CASH, part['terminal'], 1.0) if part['terminal'] else p
    capped = cap_names(slots)
    cp = _sim(capped, market, PRIMARY_CASH, {}, 1.0)
    out.update({
        'calendar': [p['dates'][0], p['dates'][-1]], 'sessions': len(D), 'effectiveBlocks': len(D) / block,
        'selectionDelta': {f'cost{k:g}x': _delta(v, horizon) for k, v in paths.items()},
        'simpleEtfExcess': H * float(np.mean(book - etf)), 'exposureTerm': H * float(np.mean(ctrl - etf)),
        'bookTotalReturnAnnualized': float(np.prod(1 + book) ** (252 / len(book)) - 1),
        'etfTotalReturnAnnualized': float(np.prod(1 + etf) ** (252 / len(etf)) - 1),
        'controlTotalReturnAnnualized': float(np.prod(1 + ctrl) ** (252 / len(ctrl)) - 1),
        'turnoverOneWay': p['turnover'],
        'ci95': _interval(m, boot, 0.95, H), 'ciSimultaneous': _interval(m, boot, level, H), 'simultaneousLevel': level,
        'pBootstrapTwoSided': INF.bootstrap_p(m, boot),
        'hacSe': H * se if se else None,
        'blockSensitivityCi95': {str(b): _interval(m, v, 0.95, H) for b, v in sens.items()},
        'cashSensitivity': {c: _delta(_sim(slots, market, c, {}, 1.0), horizon) for c in CASH_SENSITIVITY},
        'downsideStressDelta': _delta(stress, horizon), 'downsideStressEvents': len(part['terminal']),
        'checks': {k: (_delta(_sim(v, market, PRIMARY_CASH, {}, 1.0), horizon) if v else None) for k, v in regime.items()},
        'selectionByCalendarYear': {y: float(v) for y, v in sorted(years.items())},
        'eventLevel': {**E.two_way_cluster_mean([a for a, _ in ars], [s.issuer for _, s in ars],
                                                [date.fromisoformat(s.entry_date).isocalendar()[:2] for _, s in ars]),
                       'unresolved': len(slots) - len(ars), 'hitRate': float(np.mean([a > 0 for a, _ in ars])) if ars else None,
                       'median': float(np.median([a for a, _ in ars])) if ars else None},
        'eventByEntryYear': group_mean(lambda s: s.entry_date[:4]),
        'eventByIndustryNotPit': group_mean(lambda s: industry.get(s.ticker) or 'UNLABELLED'),
        'maxFiveNames': {'slots': len(capped), 'selectionDelta': _delta(cp, horizon),
                         'simpleEtfExcess': (H * float(np.mean(np.array(cp['book']) - np.array(cp['etf']))) if cp['complete'] else None),
                         'shareOfSessionsWithAName': float(np.mean([any(s.entry <= i < s.exit for s in capped)
                                                                   for i in range(capped[0].entry, capped[-1].exit)]))},
    })
    return out


def verdict(r: dict, reject: bool | None) -> dict:
    """Fixed before outcomes. Direction-aware; a gate that was not measured cannot pass."""
    if 'blocked' in r:
        return {'verdict': 'SOURCE_BLOCKED', 'reasons': [str(r['blocked'])]}
    if r['effectiveBlocks'] < MIN_EFFECTIVE_BLOCKS:
        return {'verdict': 'DESCRIPTIVE_ONLY_TOO_FEW_TIME_BLOCKS', 'reasons': [f"effectiveBlocks={r['effectiveBlocks']:.1f}"]}
    s, mee = r['expectedSign'], MEE[PRIMARY]
    d1, d2 = r['selectionDelta']['cost1x'], r['selectionDelta']['cost2x']
    lo, hi = r['ciSimultaneous']
    toward_hi = hi if s > 0 else -lo           # the simultaneous bound in the hypothesised direction
    toward_lo = lo if s > 0 else -hi
    if toward_hi < mee:
        return {'verdict': 'EXPLORATORY_REJECT_ECONOMIC_EFFECT', 'reasons': [f'SIMULTANEOUS_BOUND_IN_DIRECTION<{mee}']}
    checks = list(r['checks'].values())
    gates = {
        'holm': bool(reject), 'simultaneousExcludesZero': toward_lo > 0, 'pointAtLeastMee': s * d1 >= mee,
        # a long signal must survive doubled costs; an avoid signal is not traded, so costs cannot rescue or sink it
        'cost2xKeepsSign': s * d2 > 0 if s > 0 else True,
        'downsideStressKeepsSign': (r['downsideStressDelta'] is not None and r['downsideStressDelta'] > 0) if s > 0 else True,
        'everyCheckMeasuredAndSameSign': all(v is not None and s * v > 0 for v in checks),
        'cashScenariosSameSign': all(v is not None and s * v > 0 for v in r['cashSensitivity'].values()),
        'blockLengthsAgree': all((v[0] > 0) == (r['ci95'][0] > 0) and (v[1] < 0) == (r['ci95'][1] < 0)
                                 for v in r['blockSensitivityCi95'].values()),
    }
    failed = sorted(k for k, ok in gates.items() if not ok)
    return {'verdict': 'INCONCLUSIVE' if failed else 'EXPLORATORY_SUPPORT_NOT_VERIFIED', 'gates': gates, 'reasons': failed}


def secondary(r: dict) -> dict:
    """Components and thin samples are described, never judged: they carry no multiplicity-controlled claim."""
    if 'blocked' in r:
        return {'verdict': 'SOURCE_BLOCKED', 'reasons': [str(r['blocked'])]}
    if r['effectiveBlocks'] < MIN_EFFECTIVE_BLOCKS:
        return {'verdict': 'DESCRIPTIVE_ONLY_TOO_FEW_TIME_BLOCKS', 'reasons': [f"effectiveBlocks={r['effectiveBlocks']:.1f}"]}
    return {'verdict': 'SECONDARY_DESCRIPTIVE_NO_VERDICT', 'reasons': []}


def evaluate(events: dict[str, list[dict]], market: dict, industry: dict | None = None,
             draws: int | None = None) -> dict:
    industry = industry or {}
    family = len(HY.PRIMARY_FAMILY)
    out = {'studyId': 'broad-alpha-screen-v1', 'evidenceClass': 'EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY',
           'promotionEligible': False, 'benchmark': C.BENCHMARK, 'primaryHorizon': PRIMARY, 'familySize': family,
           'costs': dict(C.COSTS) | {'sellTaxSchedule': list(C.COSTS['sellTaxSchedule'])}, 'hypotheses': {}}
    for hyp in HY.HYPOTHESES:
        out['hypotheses'][hyp] = {hz: evaluate_one(hyp, events.get(hyp, []), hz, market, family, industry, draws)
                                  for hz in HORIZONS}
    pvals = {h: (v[PRIMARY].get('pBootstrapTwoSided', 1.0)
                 if v[PRIMARY].get('effectiveBlocks', 0) >= MIN_EFFECTIVE_BLOCKS else 1.0)
             for h, v in out['hypotheses'].items() if h in HY.PRIMARY_FAMILY}
    reject = INF.holm(pvals, FWER)
    out['holm'] = {'pValues': pvals, 'reject': reject}
    out['verdicts'] = {h: (verdict(v[PRIMARY], reject[h]) if h in HY.PRIMARY_FAMILY else secondary(v[PRIMARY]))
                       for h, v in out['hypotheses'].items()}
    return out


# ------------------------------------------------------------------ contract / gate
def build_contract(signal_history_commit: str, price_dir: Path) -> dict:
    return {
        'studyId': 'broad-alpha-screen-v1', 'status': 'PREPARED_NOT_EXECUTED',
        'evidenceClass': 'EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY', 'promotionEligible': False,
        'question': 'KR 기업 공시 사건 메커니즘(1차 3개, 구성요소 9개)이 069500.KS 대비 자금 일치 베타조정 6~12개월 선택 수익을 내는가',
        'hypotheses': {k: {'expectedSign': v[0], 'mechanism': v[1], 'sourceGrade': v[2]} for k, v in HY.HYPOTHESES.items()},
        'fixedBeforeOutcome': {
            'primaryHorizon': PRIMARY, 'horizons': list(HORIZONS), 'meeDelta': MEE, 'fwer': FWER,
            'primaryFamily': list(HY.PRIMARY_FAMILY),
            'multiplicity': 'Holm over the 3 primary hypotheses at H126; components, H252 and every split are descriptive',
            'estimand': 'delta_H = H x mean daily (book - funded beta-matched control), net of dated costs (engine.simulate)',
            'costMultipliers': [1, 2, 3], 'primaryCash': PRIMARY_CASH, 'cashSensitivity': list(CASH_SENSITIVITY),
            'bootstrap': {'draws': C.BOOTSTRAP['draws'], 'seed': C.BOOTSTRAP['seed'], 'block': dict(C.BOOTSTRAP['block']),
                          'sensitivityBlocks': {k: list(v) for k, v in C.BOOTSTRAP['sensitivityBlocks'].items()}},
            'minEffectiveBlocks': MIN_EFFECTIVE_BLOCKS, 'dividendChangeThreshold': HY.DIVIDEND_CHANGE,
            'ownershipMinIncreasePp': HY.OWNERSHIP_MIN_INCREASE_PP, 'maxNames': MAX_NAMES,
            'terminal': 'EXCLUDE_UNRESOLVED primary + DOWNSIDE_STRESS(-100%) bound; never filled',
            'verdicts': ['SECONDARY_DESCRIPTIVE_NO_VERDICT', 'SOURCE_BLOCKED', 'DESCRIPTIVE_ONLY_TOO_FEW_TIME_BLOCKS', 'EXPLORATORY_REJECT_ECONOMIC_EFFECT',
                         'INCONCLUSIVE', 'EXPLORATORY_SUPPORT_NOT_VERIFIED'],
            'oneShot': 'one execution; no hypothesis, threshold, horizon or definition changes afterwards',
        },
        'knownLimits': [
            'KR history is outcome-exposed: nothing here is out-of-sample or VERIFIED',
            'DATE_ONLY_CONSERVATIVE timing; K4-K6 are title-level (terms unparsed)',
            'stock total return uses the conditional ex-date market rule (not officially sealed)',
            'cash is a BOK policy-rate proxy, not an investable payoff',
            'universe is PIT KOSPI Top300 only; industry labels outside Top120 are not PIT (diagnostic)',
            'events with unresolved terminal economics are excluded from the primary path and bounded at -100%',
            'model costs, no real fills; pre-investor-tax',
        ],
        'inputs': {'eventsSha256': sha(EVENTS), 'signalHistoryCommit': signal_history_commit,
                   'priceShardSha256': {n: sha(Path(price_dir) / n) for n in sorted(os.listdir(price_dir))
                                        if n.startswith('krx-prices-20')}},
        'codeSha256': {p: sha(REPO / p) for p in PINNED_CODE},
    }


def verify_contract(price_dir: Path) -> tuple[dict, list[str]]:
    doc = json.loads(CONTRACT.read_text(encoding='utf-8'))
    problems = [f'CODE_CHANGED:{p}' for p, h in doc['codeSha256'].items() if sha(REPO / p) != h]
    if sha(EVENTS) != doc['inputs']['eventsSha256']:
        problems.append('EVENTS_CHANGED')
    problems += [f'PRICE_SHARD_CHANGED:{n}' for n, h in doc['inputs']['priceShardSha256'].items()
                 if not (Path(price_dir) / n).is_file() or sha(Path(price_dir) / n) != h]
    return doc, problems


class Refused(SystemExit):
    pass


def gate(price_dir: Path) -> str:
    """Every refusal happens before any market file is opened."""
    _, problems = verify_contract(price_dir)
    if problems:
        raise Refused(f'REFUSED: CONTRACT_VERIFICATION_FAILED {problems}')
    if RESULT.exists():
        raise Refused('REFUSED: RESULT_ALREADY_EXISTS_ONE_SHOT_SPENT')
    if not AUTHORIZATION.is_file():
        raise Refused('REFUSED: NO_OWNER_AUTHORIZATION')
    want = PHRASE.format(sha=sha(CONTRACT))
    if json.loads(AUTHORIZATION.read_text(encoding='utf-8')).get('phrase') != want:
        raise Refused(f'REFUSED: AUTHORIZATION_DOES_NOT_PIN_THIS_CONTRACT (expected "{want}")')
    git = lambda *a: subprocess.run(('git', *a), cwd=REPO, capture_output=True, text=True).stdout.strip()   # noqa: E731
    if not CLAIM.is_file() or git('status', '--porcelain', '--', str(CLAIM), str(AUTHORIZATION)):
        raise Refused('REFUSED: EXECUTION_CLAIM_NOT_COMMITTED (run --claim, commit and push it first)')
    return want


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--prices', type=Path, required=True, help='signal-history ledger/prices/kr')
    ap.add_argument('--mode', choices=('preflight', 'claim', 'execute'), default='preflight')
    args = ap.parse_args(argv)
    if args.mode == 'claim':
        try:
            gate(args.prices)
        except Refused as exc:
            if 'EXECUTION_CLAIM_NOT_COMMITTED' not in str(exc):
                raise
        CLAIM.write_text(json.dumps({'studyId': 'broad-alpha-screen-v1', 'contractSha256': sha(CONTRACT),
                                     'nonce': os.urandom(16).hex()}, indent=1) + '\n', encoding='utf-8')
        print('claim written; commit and push it before --mode execute')
        return 0
    if args.mode == 'execute':
        gate(args.prices)
    events = load_events()
    market = assemble(args.prices, events)
    if args.mode == 'preflight':
        print(json.dumps(preflight(events, market), ensure_ascii=False, indent=1))
        return 0
    from research.corporate_event_outcome_v1 import power_calibration as PC
    result = evaluate(events, market, PC.ticker_industry())
    result['contractSha256'] = sha(CONTRACT)
    tmp = RESULT.with_suffix('.tmp')
    tmp.write_text(json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True, default=float) + '\n', encoding='utf-8')
    os.replace(tmp, RESULT)
    print(json.dumps(result['verdicts'], ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
