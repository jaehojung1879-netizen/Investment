"""A1/B1 prospective event receipts on the existing ``prospective_receipt_core``.

One receipt per KR signal session lists every A1/B1 event whose signal is that
session's close (possibly none -> the operating default stays 069500.KS 100%).
The events come from the SAME frozen gates as the historical cohort
(``events.build`` on the day's filings), so the prospective sample and the
historical one share one definition.

Modes
* ``DRY_RUN``: written to an explicitly marked research store outside the
  repository and signal-history; evidence class
  ``DRY_RUN_NOT_PROSPECTIVE_EVIDENCE``; no timing claim, so a dry run can never
  be counted as a forward observation.
* ``LIVE``: runs only when ``registration.verify`` passes (registered spec,
  owner authorization pinning its SHA256, every pinned code file unchanged),
  only inside the core's no-backdating window (after the signal session's
  18:00 KST final close, before the next session opens), only on or after the
  first eligible session, and only into the canonical signal-history ledger
  path. Evidence class ``PROSPECTIVE_PAPER``. Outcomes are never written here.

Known difference to the historical gate, stated rather than hidden: a live
receipt is written after the signal close and before the next open, so it can
see amendments filed up to the signal session only; the historical gate looks
through the entry session. The outcome record must therefore re-apply the
amendment gate through the entry day before any H126/H252 result is read.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

from pipeline import prospective_receipt_core as core
from pipeline import replay_calendar
from pipeline.kr_corporate_action_events import fetch_all_pages

from .bodies import DocumentNotServed, amendment_reference, document_body, parse_body
from .dart_client import DartClient
from .events import Calendar, build
from .families import classify_title
from .identity import PitTop300, load_snapshots
from .registration import LEDGER_RELATIVE, verify

STUDY_ID = 'kr-corporate-information-events-v1'
STORE_MARKER = '.corporate-event-dry-run-store'
DRY_RUN_CLASS = 'DRY_RUN_NOT_PROSPECTIVE_EVIDENCE'
# Filings after the historical cohort's last receipt day; the historical PERIOD never overlaps it.
PROSPECTIVE_PERIOD = ('2026-11-01', '2099-12-31')
EVENT_FIELDS = ('rcept_no', 'corp_code', 'stock_code', 'family', 'hypothesis', 'eventType', 'receiptDay',
                'entrySession', 'pitGrade', 'terms', 'identity', 'sourceBodySha256', 'sameSessionFollowOn')
MAX_IDENTITY_SNAPSHOT_AGE_DAYS = 62


def receipt_days_for(signal_date: str, sessions: list[str]) -> list[str]:
    """Calendar days whose first KR session strictly after them is ``signal_date``."""
    i = sessions.index(signal_date)
    first = date.fromisoformat(sessions[i - 1]) if i else date.fromisoformat(signal_date) - timedelta(days=7)
    days, cur = [], first
    while cur < date.fromisoformat(signal_date):
        days.append(cur.isoformat())
        cur += timedelta(days=1)
    return days


def session_receipt(signal_date: str, events: list[dict], *, spec_sha256: str, created_at_utc: str,
                    sources: list[dict], mode: str, authorization: dict | None = None,
                    code_commit: str | None = None) -> dict:
    if mode not in ('DRY_RUN', 'LIVE'):
        raise ValueError('UNKNOWN_MODE')
    ages = [e['identity']['snapshotAgeDays'] for e in events if (e.get('identity') or {}).get('snapshotAgeDays')]
    receipt = {
        'studyId': STUDY_ID, 'specSha256': spec_sha256, 'mode': mode,
        'evidenceClass': core.EVIDENCE_CLASS if mode == 'LIVE' else DRY_RUN_CLASS,
        'signalDate': signal_date, 'createdAtUtc': created_at_utc,
        'events': [{k: e.get(k) for k in EVENT_FIELDS} for e in sorted(events, key=lambda e: e['rcept_no'])],
        'eventCount': len(events), 'sources': sources,
        'identitySnapshotStale': bool(ages and max(ages) > MAX_IDENTITY_SNAPSHOT_AGE_DAYS),
        'operatingDefault': 'KR 0 names / 069500.KS 100% (unchanged; no event is VERIFIED)',
    }
    if mode == 'LIVE':
        if not authorization or not code_commit:
            raise ValueError('LIVE_REQUIRES_AUTHORIZATION_AND_CODE_COMMIT')
        receipt['authorizationSha256'] = authorization['authorizationSha256']
        receipt['codeCommit'] = code_commit
    validate(receipt)
    receipt['receiptSha256'] = core.receipt_digest(receipt)
    return receipt


def validate(receipt: dict) -> None:
    mode = receipt.get('mode')
    if receipt.get('studyId') != STUDY_ID or mode not in ('DRY_RUN', 'LIVE'):
        raise ValueError('RECEIPT_IDENTITY_OR_MODE_INVALID')
    if mode == 'DRY_RUN' and receipt.get('evidenceClass') == core.EVIDENCE_CLASS:
        raise ValueError('DRY_RUN_CANNOT_CLAIM_PROSPECTIVE_PAPER')
    if mode == 'LIVE' and (receipt.get('evidenceClass') != core.EVIDENCE_CLASS
                           or not core.is_sha256(receipt.get('authorizationSha256', ''))
                           or not core.is_git_sha(receipt.get('codeCommit', ''))):
        raise ValueError('LIVE_RECEIPT_PROVENANCE_INVALID')
    if not core.is_sha256(receipt.get('specSha256', '')):
        raise ValueError('SPEC_SHA256_REQUIRED')
    core.scan_for_outcome_keys(receipt)
    if 'receiptSha256' in receipt and receipt['receiptSha256'] != core.receipt_digest(receipt):
        raise ValueError('RECEIPT_DIGEST_MISMATCH')


def checked_ledger(path: Path) -> Path:
    path = Path(path).resolve()
    if not path.as_posix().endswith('/' + LEDGER_RELATIVE):
        raise ValueError('LIVE_LEDGER_PATH_MUST_BE_' + LEDGER_RELATIVE)
    return path


def checked_store(path: Path, repo_root: Path) -> Path:
    path = Path(path).resolve()
    if path.is_relative_to(repo_root.resolve()) or 'signal-history' in path.parts or 'ledger' in path.parts:
        raise ValueError('DRY_RUN_STORE_MUST_BE_OUTSIDE_REPOSITORY_AND_LEDGERS')
    if not (path / STORE_MARKER).is_file():
        raise ValueError('DRY_RUN_STORE_MARKER_REQUIRED')
    return path


def day_rows(client: DartClient, day: str) -> tuple[list[dict], list[dict]]:
    rows, sources = [], []
    ymd = day.replace('-', '')
    for query in ({'pblntf_ty': 'B'}, {'pblntf_detail_ty': 'I001'}):
        pages = []

        def fetch_page(page_no, query=query, pages=pages):
            payload, meta = client.get_json('list.json', {**query, 'bgn_de': ymd, 'end_de': ymd,
                                                          'page_no': page_no, 'page_count': 100})
            pages.append(meta['sha256'])
            return payload

        got, _ = fetch_all_pages(fetch_page)
        rows.extend(got)
        sources.append({'day': day, 'query': query, 'pageSha256': sorted(pages)})
    relevant = []
    for row in rows:
        family = classify_title(row.get('report_nm', ''))
        if family:
            relevant.append({**{k: row.get(k) for k in ('rcept_no', 'rcept_dt', 'corp_code', 'corp_name',
                                                         'stock_code', 'corp_cls', 'report_nm', 'rm', 'flr_nm')},
                             'family': family})
    return relevant, sources


def collect_session(signal_date: str, *, client: DartClient, pit: PitTop300) -> tuple[list[dict], list[dict]]:
    sessions = [d.strftime('%Y-%m-%d') for d in replay_calendar.sessions('2013-01-01', '2027-12-31', 'KR')]
    if signal_date not in sessions:
        raise ValueError('SIGNAL_DATE_IS_NOT_A_KR_SESSION')
    rows, sources = [], []
    for day in receipt_days_for(signal_date, sessions):
        got, src = day_rows(client, day)
        rows.extend(got)
        sources.extend(src)
    bodies = {}
    for row in rows:
        if row['family'] not in ('CANCELLATION', 'BUYBACK', 'TRUST', 'SUPPLY'):
            continue
        try:
            raw, info = document_body(client, row['rcept_no'])
        except DocumentNotServed as exc:
            bodies[row['rcept_no']] = {'parsed': None, 'amendmentRef': None, 'error': str(exc)}
            continue
        amended = '정정' in row['report_nm']
        bodies[row['rcept_no']] = {'parsed': None if amended else parse_body(raw, row),
                                   'amendmentRef': amendment_reference(raw) if amended else None,
                                   'error': None, 'source': info}
    result = build(rows, pit, bodies, Calendar(sessions), data_cutoff='2099-12-31', as_of=signal_date,
                   period=PROSPECTIVE_PERIOD)
    events = [e for e in result['candidates'] if e['signalSession'] == signal_date and e['hypothesis'] in ('A1', 'B1')]
    seen = set()
    for e in sorted(events, key=lambda e: e['rcept_no']):
        e['sourceBodySha256'] = bodies[e['rcept_no']]['source']['bodySha256']
        # Issuer embargo inside one session; across sessions it is applied from the ledger
        # at outcome time with the same rule as the historical cohort (events.build).
        key = (e['corp_code'], e['hypothesis'])
        e['sameSessionFollowOn'] = key in seen
        seen.add(key)
        snap = (e.get('identity') or {}).get('snapshot')
        if snap:
            e['identity']['snapshotAgeDays'] = (date.fromisoformat(signal_date) - date.fromisoformat(snap)).days
    return events, sources


def dry_run(signal_date: str, *, client: DartClient, pit: PitTop300, spec_sha256: str, created_at_utc: str) -> dict:
    events, sources = collect_session(signal_date, client=client, pit=pit)
    return session_receipt(signal_date, events, spec_sha256=spec_sha256, created_at_utc=created_at_utc,
                           sources=sources, mode='DRY_RUN')


def live_append(signal_date: str, *, client: DartClient, pit: PitTop300, ledger: Path, code_commit: str,
                now_utc=None) -> dict:
    """Write ONE live receipt for ``signal_date`` or raise before anything is written."""
    authorization = verify()
    ledger = checked_ledger(ledger)
    created = core.system_utc_now() if now_utc is None else now_utc
    core.check_timing(signal_date=signal_date, created_at_utc=created, now_utc=created,
                      merged_at_utc=authorization['authorizedAtUtc'])
    events, sources = collect_session(signal_date, client=client, pit=pit)
    # Re-check the window after the network work: the receipt must still precede the next open.
    created = core.system_utc_now() if now_utc is None else now_utc
    core.check_timing(signal_date=signal_date, created_at_utc=created, now_utc=created,
                      merged_at_utc=authorization['authorizedAtUtc'])
    receipt = session_receipt(signal_date, events, spec_sha256=authorization['specSha256'],
                              created_at_utc=created.isoformat(), sources=sources, mode='LIVE',
                              authorization=authorization, code_commit=code_commit)
    core.append(ledger, receipt, validate=validate, key_fields=('signalDate',))
    return receipt


def main(argv: list[str] | None = None) -> int:
    import subprocess

    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--signal-date', action='append', required=True)
    p.add_argument('--cache', type=Path, required=True)
    p.add_argument('--universe', type=Path, required=True)
    p.add_argument('--store', type=Path, help='DRY_RUN store (marked, outside the repository)')
    p.add_argument('--ledger', type=Path, help='LIVE: <signal-history checkout>/' + LEDGER_RELATIVE)
    p.add_argument('--spec', type=Path, default=Path(__file__).with_name(
        'kr-corporate-information-events-v1-candidate.json'))
    p.add_argument('--mode', choices=('DRY_RUN', 'LIVE'), default='DRY_RUN')
    args = p.parse_args(argv)
    client = DartClient(args.cache)
    pit = PitTop300(load_snapshots(args.universe))
    repo_root = Path(__file__).resolve().parents[3]
    if args.mode == 'LIVE':
        if len(args.signal_date) != 1 or not args.ledger:
            raise SystemExit('LIVE takes exactly one --signal-date and --ledger')
        commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=repo_root, capture_output=True, text=True,
                                check=True).stdout.strip()
        receipt = live_append(args.signal_date[0], client=client, pit=pit, ledger=args.ledger, code_commit=commit)
        print(json.dumps({'mode': 'LIVE', 'signalDate': receipt['signalDate'], 'events': receipt['eventCount'],
                          'receiptSha256': receipt['receiptSha256']}, ensure_ascii=False))
        return 0
    store = checked_store(args.store, repo_root)
    spec_sha = hashlib.sha256(args.spec.read_bytes()).hexdigest()
    ledger = store / 'dry-run-receipts.jsonl'
    for signal_date in sorted(args.signal_date):
        receipt = dry_run(signal_date, client=client, pit=pit, spec_sha256=spec_sha,
                          created_at_utc=core.system_utc_now().isoformat())
        core.append(ledger, receipt, validate=validate, key_fields=('signalDate',))
        print(json.dumps({'signalDate': signal_date, 'events': receipt['eventCount'],
                          'receiptSha256': receipt['receiptSha256']}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
