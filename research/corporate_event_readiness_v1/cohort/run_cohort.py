"""Fetch bodies for the outcome-free gates and write the cohort funnel artifacts.

Network use is limited to OpenDART ``document.xml`` for filings that already
passed the identity gate (PIT KOSPI Top300) in a body family, plus every
amendment of those families (to read their stated original-filing day).
Run with ``--offline`` to rebuild from the content-addressed cache only.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

from pipeline import replay_calendar
from pipeline.kr_corporate_action_events import is_amendment

from .bodies import amendment_reference, document_body, parse_body
from .dart_client import DartClient
from .events import HORIZONS, HYPOTHESES, PERIOD, Calendar, build, describe, iso
from .families import is_subsidiary_report
from .identity import PitTop300, load_snapshots, snapshot_digest
from .power import power_table


PRIORITY = {'CANCELLATION': 0, 'BUYBACK': 1, 'TRUST': 2, 'SUPPLY': 3}
AMENDMENT_WINDOW_DAYS = 10


def wanted_bodies(rows: list[dict], pit: PitTop300) -> list[dict]:
    """Originals that passed the identity gate in a hypothesis family, plus only those
    amendments that could precede entry (filed <= 10 calendar days after a same-issuer,
    same-family original). Later amendments are post-entry states under intention to
    treat and cannot change admission, so their bodies are not needed."""
    originals, amendments = [], []
    for row in rows:
        if row['family'] not in PRIORITY:
            continue
        day = iso(row['rcept_dt'])
        if not PERIOD[0] <= day <= PERIOD[1]:
            continue
        if pit.membership(row.get('stock_code'), day)['status'] != 'PIT_TOP300_MEMBER':
            continue
        if is_amendment(row['report_nm']):
            amendments.append(row)
        elif not is_subsidiary_report(row['report_nm']):
            originals.append(row)
    starts = {}
    for row in originals:
        starts.setdefault((row['corp_code'], row['family']), []).append(date.fromisoformat(iso(row['rcept_dt'])))
    keep = list(originals)
    for row in amendments:
        day = date.fromisoformat(iso(row['rcept_dt']))
        if any(0 <= (day - s).days <= AMENDMENT_WINDOW_DAYS for s in starts.get((row['corp_code'], row['family']), [])):
            keep.append(row)
    return sorted(keep, key=lambda r: (PRIORITY[r['family']], r['rcept_no']))


def fetch_bodies(client: DartClient, rows: list[dict], workers: int) -> tuple[dict, dict]:
    bodies, receipts = {}, {}

    def one(row):
        try:
            raw, info = document_body(client, row['rcept_no'])
        except Exception as exc:  # recorded per filing; never silently dropped
            return row, None, None, f'{type(exc).__name__}:{exc}'[:200]
        return row, raw, info, None

    with ThreadPoolExecutor(workers) as pool:
        for fut in as_completed([pool.submit(one, r) for r in rows]):
            row, raw, info, error = fut.result()
            if error:
                bodies[row['rcept_no']] = {'parsed': None, 'amendmentRef': None, 'error': error}
                continue
            receipts[row['rcept_no']] = info
            if is_amendment(row['report_nm']):
                bodies[row['rcept_no']] = {'parsed': None, 'amendmentRef': amendment_reference(raw), 'error': None}
            else:
                bodies[row['rcept_no']] = {'parsed': parse_body(raw, row), 'amendmentRef': None, 'error': None}
    return bodies, receipts


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--cache', type=Path, required=True)
    p.add_argument('--universe', type=Path, required=True)
    p.add_argument('--index', type=Path, required=True, help='issuer-index-rows-v1.jsonl.gz')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--data-cutoff', default='2026-10-30')
    p.add_argument('--as-of', default='2026-11-06')
    p.add_argument('--workers', type=int, default=3)
    p.add_argument('--offline', action='store_true')
    args = p.parse_args(argv)
    client = DartClient(args.cache, offline=args.offline)
    pit = PitTop300(load_snapshots(args.universe))
    rows = [json.loads(line) for line in gzip.open(args.index, 'rt', encoding='utf-8')]
    wanted = wanted_bodies(rows, pit)
    bodies, receipts = fetch_bodies(client, wanted, args.workers)
    sessions = [d.strftime('%Y-%m-%d') for d in replay_calendar.sessions('2013-01-01', '2027-12-31', 'KR')]
    result = build(rows, pit, bodies, Calendar(sessions), data_cutoff=args.data_cutoff, as_of=args.as_of)
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    funnel = {
        'population': 'Issuers ever in a monthly PIT KOSPI Top300 snapshot; every B/I001 filing 2013-01-01..2026-10-31',
        'calendarVersion': replay_calendar.CALENDAR_VERSION,
        'dataCutoff': args.data_cutoff, 'asOf': args.as_of,
        'filingVersionsByFamily': dict(sorted(_count(rows, 'family').items())),
        'stoppedAtGate': result['stageCounts'],
        'firstFailingReasonDetail': _detail(result['versions']),
        'pitExact': {'count': 0, 'reason': 'RECEIPT_CLOCK_NOT_SERVED_BY_LIST_JSON_DOCUMENT_XML_OR_DS005'},
        'dateOnlyConservativeCandidates': dict(sorted(_count(result['candidates'], 'hypothesis').items())),
        'independent': {f'{h}_H{n}': describe(result['independent'][(h, n)], n, sessions)
                        for h in HYPOTHESES for n in HORIZONS},
        'bodies': {'requested': len(wanted), 'retrieved': len(receipts),
                   'errors': sum(1 for b in bodies.values() if b['error'])},
        'apiCalls': client.calls, 'cacheHits': client.cache_hits,
    }
    funnel['power'] = power_table(funnel['independent'])
    (out / 'cohort-funnel-v1.json').write_text(json.dumps(funnel, ensure_ascii=False, indent=1) + '\n',
                                               encoding='utf-8')
    events = [v for v in result['versions'] if v.get('pitGrade') or v.get('stoppedAt') in
              ('HYPOTHESIS_CLASS', 'TERMS_PARSED', 'NO_PRE_ENTRY_AMENDMENT', 'ENTRY_WITHIN_CALENDAR')]
    for v in events:
        if v.get('pitGrade'):
            v['independent'] = {f'H{n}': not v.get('followOnOf', {}).get(f'H{n}') for n in HORIZONS}
    payload = ''.join(json.dumps(v, ensure_ascii=False, sort_keys=True) + '\n' for v in
                      sorted(events, key=lambda v: v['rcept_no']))
    (out / 'cohort-events-v1.jsonl.gz').write_bytes(gzip.compress(payload.encode(), 9, mtime=0))
    receipt_payload = json.dumps({k: receipts[k] for k in sorted(receipts)}, ensure_ascii=False, sort_keys=True)
    (out / 'body-receipts-v1.json.gz').write_bytes(gzip.compress(receipt_payload.encode(), 9, mtime=0))
    (out / 'inputs-v1.json').write_text(json.dumps({
        'indexRowsSha256': hashlib.sha256(args.index.read_bytes()).hexdigest(),
        'universeSnapshots': snapshot_digest(args.universe),
        'universeSourceCommit': 'signal-history@73b3907a663ebe300a435d0d57db4b2eee9e5ea4',
        'bodyReceiptCount': len(receipts),
    }, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps({k: funnel[k] for k in ('stoppedAtGate', 'dateOnlyConservativeCandidates', 'bodies')},
                     ensure_ascii=False))
    return 0


def _count(rows, key):
    out = {}
    for r in rows:
        out[r.get(key)] = out.get(r.get(key), 0) + 1
    return out


def _detail(versions):
    detail = {}
    for v in versions:
        gate = v.get('stoppedAt')
        if gate is None:
            continue
        reason = v.get('eventType') or (v.get('identity') or {}).get('status') or v.get('bodyError') or gate
        if gate == 'NO_PRE_ENTRY_AMENDMENT':
            reason = '+'.join(sorted({a['link'] for a in v['preEntryAmendments']}))
        if gate == 'ORIGINAL_VERSION':
            reason = 'AMENDMENT_REF_' + ((v.get('amendmentRef') or {}).get('status') or 'NOT_FETCHED')
        key = f'{gate}:{v["family"]}:{reason}'.split(':SHAREHOLDER')[0]
        detail[key] = detail.get(key, 0) + 1
    return dict(sorted(detail.items()))


if __name__ == '__main__':
    raise SystemExit(main())
