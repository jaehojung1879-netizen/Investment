"""Prospective receipts for F1 (dividend increase, long candidate) and F2 (dilution decision, avoid rule).

A separate study with its own spec, authorization and ledger. It never reads or writes the registered
``kr-corporate-information-events-v1`` ledger, spec or code; it calls that study's public helpers
(``day`` listing conventions, PIT Top300 identity, body retrieval, dividend parsing) and the shared
``prospective_receipt_core`` (no-backdating window, append-only ledger, digest).

The event definitions are the ones #327 screened, unchanged (``broad_alpha_screen_v1.hypotheses``):
F2 = an original (non-amendment), issuer-own rights-issue / CB / EB / BW decision by a PIT KOSPI Top300 member,
     removed if the same issuer files a same-family amendment up to the signal session;
F1 = a year-end common cash DPS at least 25% above the same stock's previous year-end DPS, listed shares within
     +/-10% between the two record dates.
One correction to F1, made for correctness and before any prospective outcome exists: a dividend decision titled
"(자회사의 주요경영사항)" is a parent reporting its SUBSIDIARY's dividend. #327's historical K7 set did not remove
those (85 of its 460 H126 events touch one), so its +3.51pp reading is for a contaminated definition. Here both
the current decision and its prior-year base must be the issuer's own report.
Nothing here was fitted to a return. Terms of an F2 filing (size, allotment method, conversion price) are NOT
parsed: the body hash is recorded so they can be read later, and they never gate an event.

A receipt is evidence that a signal was recorded before its entry session. It is not performance.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import subprocess
import tempfile
from datetime import date
from pathlib import Path

from pipeline import prospective_receipt_core as core
from pipeline import replay_calendar
from pipeline.kr_corporate_action_events import fetch_all_pages, is_amendment
from research.broad_alpha_screen_v1 import hypotheses as HY
from research.corporate_event_readiness_v1.cohort.bodies import DocumentNotServed, document_body
from research.corporate_event_readiness_v1.cohort.dart_client import DartClient
from research.corporate_event_readiness_v1.cohort.dividends import parse_dividend
from research.corporate_event_readiness_v1.cohort.families import classify_title, compact, is_subsidiary_report
from research.corporate_event_readiness_v1.cohort.identity import PitTop300, load_snapshots
from research.corporate_event_readiness_v1.cohort.prospective import receipt_days_for
from research.corporate_event_readiness_v1.cohort.registration import verify as verify_registration

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STUDY_ID = 'kr-capital-event-prospective-v1'
SPEC = HERE / 'spec-v1.json'
AUTHORIZATION = HERE / 'AUTHORIZATION-prospective-recording.json'
LEDGER_RELATIVE = f'ledger/research-strategies/{STUDY_ID}/receipts.jsonl'
DILUTION = ('RIGHTS', 'CB', 'EB', 'BW')
DIVIDEND_TITLE = '현금현물배당결정'
DRY_RUN_CLASS = 'DRY_RUN_NOT_PROSPECTIVE_EVIDENCE'
STORE_MARKER = '.capital-event-dry-run-store'
PINNED_CODE = ('research/kr_capital_event_prospective_v1/recorder.py', 'research/broad_alpha_screen_v1/hypotheses.py',
               'pipeline/prospective_receipt_core.py', 'pipeline/replay_calendar.py',
               'research/corporate_event_readiness_v1/cohort/prospective.py',
               'research/corporate_event_readiness_v1/cohort/registration.py',
               'research/corporate_event_readiness_v1/cohort/identity.py',
               'research/corporate_event_readiness_v1/cohort/families.py',
               'research/corporate_event_readiness_v1/cohort/dividends.py',
               'research/corporate_event_readiness_v1/cohort/bodies.py',
               'research/corporate_event_readiness_v1/cohort/dart_client.py')
PRIOR_DIVIDENDS = HY.COHORT / 'dividend-decisions-v1.jsonl.gz'


def day_rows(client: DartClient, day: str) -> tuple[list[dict], list[dict]]:
    """Same two list.json queries as the registered recorder; keeps dilution and dividend-decision titles."""
    rows, sources, ymd = [], [], day.replace('-', '')
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
    kept, seen = [], set()
    for row in rows:
        title = row.get('report_nm', '')
        family = 'DIVIDEND' if DIVIDEND_TITLE in compact(title) else classify_title(title)
        if family in (*DILUTION, 'DIVIDEND') and row['rcept_no'] not in seen:
            seen.add(row['rcept_no'])
            kept.append({**{k: row.get(k) for k in ('rcept_no', 'rcept_dt', 'corp_code', 'corp_name', 'stock_code',
                                                    'report_nm')}, 'family': family})
    return kept, sources


def _identity(pit: PitTop300, code: str | None, day: str, signal_date: str) -> dict:
    member = dict(pit.membership(code, day))
    if member.get('snapshot'):
        member['snapshotAgeDays'] = (date.fromisoformat(signal_date) - date.fromisoformat(member['snapshot'])).days
    return member


def _body_hash(client: DartClient, rcept_no: str) -> tuple[bytes | None, str]:
    try:
        raw, info = document_body(client, rcept_no)
        return raw, info['bodySha256']
    except (DocumentNotServed, ValueError) as exc:
        return None, 'BODY_NOT_SERVED:' + str(exc)[:60]


def prior_year_end_dps(prior_rows: list[dict]) -> dict:
    """(stock_code, fiscal year) -> first ORIGINAL year-end common cash DPS and its record date."""
    out: dict = {}
    for r in sorted(prior_rows, key=lambda x: x['rcept_no']):
        if r.get('dividendClass') != '결산배당' or r.get('dividendKind') != '현금배당' or r.get('amendment'):
            continue
        if is_subsidiary_report(r.get('report_nm', '')):     # a parent reporting its subsidiary's dividend
            continue
        try:
            dps = float(str(r.get('dpsCommonKrw')).replace(',', ''))
        except ValueError:
            continue
        if r.get('recordDate'):
            out.setdefault((r['stock_code'], int(r['recordDate'][:4])), {'dps': dps, 'recordDate': r['recordDate']})
    return out


def collect(signal_date: str, *, client: DartClient, pit: PitTop300, prior_rows: list[dict],
            sessions: list[str]) -> tuple[list[dict], list[dict], list[dict]]:
    if signal_date not in sessions:
        raise ValueError('SIGNAL_DATE_IS_NOT_A_KR_SESSION')
    entry = sessions[sessions.index(signal_date) + 1]
    rows, sources = [], []
    for day in receipt_days_for(signal_date, sessions):
        got, src = day_rows(client, day)
        rows.extend(got)
        sources.extend(src)
    amended = {(r['corp_code'], r['family']) for r in rows if is_amendment(r['report_nm'])}
    prior = prior_year_end_dps(prior_rows)
    events, observations, seen = [], [], set()
    for r in sorted(rows, key=lambda x: x['rcept_no']):
        day = HY.iso(r['rcept_dt'])
        if is_amendment(r['report_nm']) or is_subsidiary_report(r['report_nm']):
            continue
        member = _identity(pit, r.get('stock_code'), day, signal_date)
        if member['status'] != 'PIT_TOP300_MEMBER':
            continue
        base = {'rcept_no': r['rcept_no'], 'corp_code': r['corp_code'], 'stock_code': r['stock_code'],
                'family': r['family'], 'receiptDay': day, 'entrySession': entry, 'identity': member,
                'pitGrade': 'DATE_ONLY_CONSERVATIVE', 'publicationClock': 'NOT_SERVED_BY_DART_LIST_DATE_ONLY'}
        if r['family'] in DILUTION:
            if (r['corp_code'], r['family']) in amended:
                continue
            _, body = _body_hash(client, r['rcept_no'])
            key = (r['corp_code'], 'F2')
            events.append({**base, 'candidate': 'F2_DILUTION_AVOID', 'sourceBodySha256': body,
                           'terms': 'NOT_PARSED_BODY_HASH_RETAINED', 'sameSessionFollowOn': key in seen})
            seen.add(key)
            continue
        raw, body = _body_hash(client, r['rcept_no'])
        parsed = parse_dividend(raw) if raw is not None else {}
        obs = {'rcept_no': r['rcept_no'], 'stock_code': r['stock_code'], 'sourceBodySha256': body,
               **{k: parsed.get(k) for k in ('dividendClass', 'dividendKind', 'dpsCommonKrw', 'recordDate')}}
        observations.append(obs)                 # every decision is kept: next year's comparison base
        if parsed.get('dividendClass') != '결산배당' or parsed.get('dividendKind') != '현금배당':
            continue
        try:
            dps = float(str(parsed.get('dpsCommonKrw')).replace(',', ''))
            fy = int(parsed['recordDate'][:4])
        except (TypeError, ValueError):
            continue
        before = prior.get((r['stock_code'], fy - 1))
        if not before or before['dps'] <= 0:
            continue
        a, b = HY._listed(pit, r['stock_code'], before['recordDate']), HY._listed(pit, r['stock_code'], parsed['recordDate'])
        if not a or not b or not 0.9 <= b / a <= 1.1:
            continue
        change = dps / before['dps'] - 1
        if change >= HY.DIVIDEND_CHANGE:
            events.append({**base, 'candidate': 'F1_DIVIDEND_INCREASE_LONG', 'sourceBodySha256': body,
                           'terms': {'dpsCommonKrw': dps, 'priorDpsCommonKrw': before['dps'],
                                     'dpsChangePct': round(100 * change, 2), 'fiscalYear': fy,
                                     'specialDividendSeparable': False},
                           'sameSessionFollowOn': False})
    return events, observations, sources


def session_receipt(signal_date: str, events, observations, sources, *, spec_sha256: str, created_at_utc: str,
                    mode: str, authorization: dict | None = None, code_commit: str | None = None) -> dict:
    ages = [e['identity'].get('snapshotAgeDays', 0) for e in events]
    receipt = {
        'studyId': STUDY_ID, 'specSha256': spec_sha256, 'mode': mode,
        'evidenceClass': core.EVIDENCE_CLASS if mode == 'LIVE' else DRY_RUN_CLASS,
        'signalDate': signal_date, 'createdAtUtc': created_at_utc,
        'events': sorted(events, key=lambda e: e['rcept_no']), 'eventCount': len(events),
        'dividendObservations': sorted(observations, key=lambda o: o['rcept_no']), 'sources': sources,
        'identitySnapshotStale': bool(ages and max(ages) > 62),
        # No candidate is VERIFIED, so the book these signals feed holds nothing: 0 of at most 5 names.
        'book': {'signalNames': 0, 'maxNames': 5, 'etf': '069500.KS', 'etfWeight': 1.0, 'cashWeight': 0.0,
                 'promotion': 'NONE_CANDIDATES_ARE_NOT_VERIFIED'},
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
    if (receipt.get('evidenceClass') == core.EVIDENCE_CLASS) != (mode == 'LIVE'):
        raise ValueError('EVIDENCE_CLASS_DOES_NOT_MATCH_MODE')
    if mode == 'LIVE' and not (core.is_sha256(receipt.get('authorizationSha256', ''))
                               and core.is_git_sha(receipt.get('codeCommit', ''))):
        raise ValueError('LIVE_RECEIPT_PROVENANCE_INVALID')
    if receipt['book']['signalNames'] != 0 or receipt['book']['etfWeight'] != 1.0:
        raise ValueError('UNVERIFIED_CANDIDATES_CANNOT_HOLD_NAMES')
    core.scan_for_outcome_keys(receipt)
    if 'receiptSha256' in receipt and receipt['receiptSha256'] != core.receipt_digest(receipt):
        raise ValueError('RECEIPT_DIGEST_MISMATCH')


def verify() -> dict:
    return verify_registration(SPEC, AUTHORIZATION, REPO)


def sessions_list() -> list[str]:
    return [d.strftime('%Y-%m-%d') for d in replay_calendar.sessions('2013-01-01', '2027-12-31', 'KR')]


def prior_rows(ledger: Path | None) -> list[dict]:
    with gzip.open(PRIOR_DIVIDENDS, 'rt', encoding='utf-8') as fh:
        rows = [json.loads(line) for line in fh]
    if ledger and Path(ledger).is_file():            # decisions this study itself recorded in earlier seasons
        for line in Path(ledger).read_text(encoding='utf-8').splitlines():
            rows += json.loads(line).get('dividendObservations', [])
    return rows


def record(signal_date: str, *, mode: str, client: DartClient, universe: Path, ledger: Path,
           code_commit: str | None = None) -> dict:
    pit = PitTop300(load_snapshots(universe))
    HY.load_listed_shares(universe)
    sessions = sessions_list()
    if mode == 'LIVE':
        authorization = verify()
        if not Path(ledger).resolve().as_posix().endswith('/' + LEDGER_RELATIVE):
            raise ValueError('LIVE_LEDGER_PATH_MUST_BE_' + LEDGER_RELATIVE)
        now = core.system_utc_now()
        core.check_timing(signal_date=signal_date, created_at_utc=now, now_utc=now,
                          merged_at_utc=authorization['authorizedAtUtc'])
    else:
        authorization = None
        if Path(ledger).resolve().is_relative_to(REPO) or not (Path(ledger).parent / STORE_MARKER).is_file():
            raise ValueError('DRY_RUN_STORE_MUST_BE_MARKED_AND_OUTSIDE_THE_REPOSITORY')
    events, observations, sources = collect(signal_date, client=client, pit=pit, prior_rows=prior_rows(ledger),
                                            sessions=sessions)
    created = core.system_utc_now()
    if mode == 'LIVE':                                # still before the entry open after the network work
        core.check_timing(signal_date=signal_date, created_at_utc=created, now_utc=created,
                          merged_at_utc=authorization['authorizedAtUtc'])
    receipt = session_receipt(signal_date, events, observations, sources,
                              spec_sha256=hashlib.sha256(SPEC.read_bytes()).hexdigest(),
                              created_at_utc=created.isoformat(), mode=mode, authorization=authorization,
                              code_commit=code_commit)
    core.append(Path(ledger), receipt, validate=validate, key_fields=('signalDate',))
    return receipt


def git(*args, cwd=REPO) -> str:
    return subprocess.run(['git', *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--mode', choices=('DRY_RUN', 'LIVE'), default='DRY_RUN')
    p.add_argument('--signal-date', help='DRY_RUN only; LIVE always uses the session that just closed')
    p.add_argument('--universe', type=Path, help='DRY_RUN: checkout of signal-history ledger/universe/kr')
    p.add_argument('--store', type=Path, help='DRY_RUN: marked directory outside the repository')
    args = p.parse_args(argv)
    work = Path(tempfile.mkdtemp(prefix='kr-capital-event-'))
    client = DartClient(work / 'dart-cache')
    if args.mode == 'DRY_RUN':
        r = record(args.signal_date, mode='DRY_RUN', client=client, universe=args.universe,
                   ledger=args.store / 'dry-run-receipts.jsonl')
        print(json.dumps({'mode': 'DRY_RUN', 'signalDate': r['signalDate'], 'events': r['eventCount'],
                          'dividendObservations': len(r['dividendObservations']), 'dartCalls': client.calls},
                         ensure_ascii=False))
        return 0
    verify()
    now = core.system_utc_now()
    kst_day = (now + core.KST).tz_localize(None).normalize()
    if not core.is_kr_session(kst_day) or now < (kst_day + core.KR_CLOSE_FINAL_UTC).tz_localize('UTC'):
        print(json.dumps({'status': 'NO_RECEIPT_DUE', 'nowUtc': now.isoformat()}))
        return 0
    signal_date = kst_day.strftime('%Y-%m-%d')
    worktree = work / 'signal-history'
    git('fetch', '--depth=1', 'origin', 'signal-history')
    git('worktree', 'add', '--force', '--detach', str(worktree), 'FETCH_HEAD')
    try:
        try:
            r = record(signal_date, mode='LIVE', client=client, universe=worktree / 'ledger' / 'universe' / 'kr',
                       ledger=worktree / LEDGER_RELATIVE, code_commit=git('rev-parse', 'HEAD'))
        except ValueError as exc:
            if str(exc) == 'RECEIPT_ALREADY_EXISTS':
                print(json.dumps({'status': 'ALREADY_RECORDED', 'signalDate': signal_date}))
                return 0
            raise
        git('add', LEDGER_RELATIVE, cwd=worktree)
        git('-c', 'user.name=capital-event-receipt-bot', '-c', 'user.email=actions@github.com', 'commit', '-m',
            f'ledger: kr capital event prospective receipt {signal_date}', cwd=worktree)
        pushed = subprocess.run(['git', 'push', 'origin', 'HEAD:signal-history'], cwd=worktree,
                                capture_output=True, text=True)
        if pushed.returncode != 0:          # an unpushed receipt is not a public record: fail loudly
            raise SystemExit('PUSH_FAILED_RECEIPT_NOT_PUBLIC: ' + pushed.stderr[-300:])
        print(json.dumps({'status': 'RECORDED', 'signalDate': signal_date, 'events': r['eventCount'],
                          'createdAtUtc': r['createdAtUtc'], 'receiptSha256': r['receiptSha256'],
                          'signalHistoryCommit': git('rev-parse', 'HEAD', cwd=worktree)}, ensure_ascii=False))
        return 0
    finally:
        subprocess.run(['git', 'worktree', 'remove', '--force', str(worktree)], cwd=REPO, capture_output=True)


if __name__ == '__main__':
    raise SystemExit(main())
