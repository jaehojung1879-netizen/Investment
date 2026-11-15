"""List the cohort events whose holding window ends before maturity (presence only).

Uses ``admission.window_admission`` unchanged, then separates two different
facts that its ``ENDS_BEFORE_MATURITY`` label lumps together:
* ``TERMINAL_NO_BAR_AT_OR_AFTER_WINDOW_END``: the ticker has no bar on or after
  the window-end session anywhere in the ledger (delisting / merger / tender);
* ``LEDGER_SESSION_GAP_NOT_TERMINAL``: the ticker trades later, but the window
  end falls on a session the ledger lacks for (almost) every ticker.
Ledger-wide gap sessions are listed so the price-side source repair is named. Each listed event needs a cited
terminal consideration (merger, exchange, tender, delisting value) before any
outcome can be computed; none is inferred here and no event is dropped.
"""
from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path

from pipeline import replay_calendar

from .admission import load_presence, window_admission
from .identity import load_snapshots


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--events', type=Path, required=True)
    p.add_argument('--prices', type=Path, required=True)
    p.add_argument('--universe', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args(argv)
    sessions = [d.strftime('%Y-%m-%d') for d in replay_calendar.sessions('2013-01-01', '2027-12-31', 'KR')]
    presence, _ = load_presence(args.prices)
    ledger_end = max(max(v) for v in presence.values())
    names = {}
    for snap in load_snapshots(args.universe).values():
        names.update(snap)
    events = [json.loads(line) for line in gzip.open(args.events, 'rt', encoding='utf-8')]
    rows = []
    for e in events:
        if not e.get('pitGrade'):
            continue
        for h in (126, 252):
            if not e['independent'][f'H{h}']:
                continue
            res = window_admission(presence.get(e['stock_code'] + '.KS'), sessions, e['entrySession'], h, ledger_end)
            if res['status'] == 'ENDS_BEFORE_MATURITY_TERMINAL_ECONOMICS_REQUIRED':
                bars = presence[e['stock_code'] + '.KS']
                end = sessions[sessions.index(e['entrySession']) + h]
                kind = ('LEDGER_SESSION_GAP_NOT_TERMINAL' if any(d >= end for d in bars)
                        else 'TERMINAL_NO_BAR_AT_OR_AFTER_WINDOW_END')
                rows.append({'hypothesis': e['hypothesis'], 'horizon': f'H{h}', 'rcept_no': e['rcept_no'],
                             'classification': kind, 'windowEnd': end,
                             'stockCode': e['stock_code'], 'nameAtLastSnapshot': names.get(e['stock_code']),
                             'entrySession': e['entrySession'], 'lastBar': res['lastBar'],
                             'terminalConsideration': 'UNRESOLVED_NOT_INFERRED'})
    rows.sort(key=lambda r: (r['hypothesis'], r['horizon'], r['entrySession'], r['rcept_no']))
    counts = {}
    for day in sessions:
        if day > ledger_end:
            break
        counts[day] = 0
    for bars in presence.values():
        for day in bars:
            if day in counts:
                counts[day] += 1
    gaps = []
    ordered = sorted(counts)
    for i, day in enumerate(ordered):
        neighbours = [counts[d] for d in ordered[max(0, i - 10):i] + ordered[i + 1:i + 11]]
        typical = sorted(neighbours)[len(neighbours) // 2] if neighbours else 0
        if typical and counts[day] < 0.5 * typical:
            gaps.append({'session': day, 'tickersWithBar': counts[day], 'typicalNeighbourCount': typical})
    by_kind = {}
    for r in rows:
        key = f"{r['hypothesis']}_{r['horizon']}:{r['classification']}"
        by_kind[key] = by_kind.get(key, 0) + 1
    report = {'events': rows, 'count': len(rows), 'byClassification': dict(sorted(by_kind.items())),
              'ledgerWideGapSessions': gaps,
              'note': 'supersedes the ENDS_BEFORE_MATURITY split in price-admission-v1.json; no event is dropped'}
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps({'count': len(rows), 'byClassification': report['byClassification'],
                      'ledgerWideGapSessions': [g['session'] for g in gaps]}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
