"""Outcome-free preparation: event sets, structural window coverage, second-moment power, frozen contract.

Reads prices only for (a) presence of a level on each session and (b) #322's second-moment-only power
calibration. No return of any event, window or book is computed or written.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import NormalDist

from pipeline import replay_calendar as RC
from research.corporate_event_outcome_v1 import power_calibration as PC

from . import hypotheses as HY
from . import screen as S


def power(events: list[dict], price_dir: Path) -> dict:
    sig, beta, resid = PC.residual_moments(price_dir)
    industry = PC.ticker_industry()
    within, cross = PC.industry_correlations(resid, industry)
    sessions = [d.strftime('%Y-%m-%d') for d in RC.sessions('2013-01-01', '2027-12-31', 'KR')]
    n = NormalDist()
    zc = n.inv_cdf(1 - S.FWER / (2 * len(HY.PRIMARY_FAMILY)))
    crit = zc + n.inv_cdf(0.80)
    out = {}
    for hyp in HY.HYPOTHESES:
        for h in HY.HORIZONS:
            if not any(e['hypothesis'] == hyp and e['independent'][f'H{h}'] and e[f'H{h}Matured'] for e in events):
                continue
            b = PC.book_power(events, sessions, HY.DATA_CUTOFF, sig, beta, within, cross, industry, hyp, h)
            se, mee = b['seDeltaPp'], 100 * S.MEE[f'H{h}']
            mde = round(crit * se, 2)
            out[f'{hyp}_H{h}'] = {k: b[k] for k in ('maturedIndependent', 'calendarSessions', 'emptySessions',
                                                    'meanActiveSlots', 'maxActiveSlots', 'seDeltaPp')} | {
                'mdePp': mde, 'meePp': mee, 'gate': 'GO' if mde <= mee else 'MARGINAL' if mde <= 2 * mee else 'NO_GO',
                'powerAtMee': round(n.cdf(mee / se - zc), 3), 'timeBlocks252': round(b['calendarSessions'] / 252, 1)}
    return {'basis': 'SECOND_MOMENT_ONLY_LOWER_BOUND (power_calibration.book_power); family = %d' % len(HY.PRIMARY_FAMILY),
            'critical': round(crit, 4), 'sets': out}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--signal-history', type=Path, required=True, help='checkout of signal-history ledger/')
    ap.add_argument('--commit', required=True)
    args = ap.parse_args()
    prices = args.signal_history / 'prices' / 'kr'
    built = HY.build(args.signal_history / 'universe' / 'kr', args.signal_history / 'dart-ownership-events')
    HY.dump_events(built['events'], S.EVENTS)
    events = S.load_events()
    market = S.assemble(prices, events)
    doc = {'contract': 'BROAD_ALPHA_SCREEN_ELIGIBILITY_V1', 'returnsComputed': 0, 'dataCutoff': HY.DATA_CUTOFF,
           'signalHistoryCommit': args.commit, 'eventRows': len(built['events']),
           'independent': built['independent'], 'dropped': built['dropped'],
           'windowStates': S.preflight(events, market), 'dividendFlags': market['dividendFlags'],
           'cash': market['cashMeta'], 'power': power(built['events'], prices)}
    (S.HERE / 'eligibility-v1.json').write_text(json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=True) + '\n',
                                                encoding='utf-8')
    S.CONTRACT.write_text(json.dumps(S.build_contract(args.commit, prices), ensure_ascii=False, indent=1,
                                     sort_keys=True) + '\n', encoding='utf-8')
    print(S.PHRASE.format(sha=S.sha(S.CONTRACT)))


if __name__ == '__main__':
    main()
