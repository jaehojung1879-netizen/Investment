"""One scheduled LIVE run: today's KR session receipt -> signal-history, or a clean no-op.

Steps, each failing closed:
1. today's KST date must be a KR session and the 18:00 KST final close must
   have passed (``prospective_receipt_core`` timing; checked again in
   ``prospective.live_append``);
2. a fresh worktree of ``signal-history`` provides the PIT universe snapshots
   and the append-only ledger;
3. ``prospective.live_append`` verifies the registration and writes one row;
   an existing row for the date is an idempotent no-op, never a rewrite;
4. commit and push with the same fetch-and-rebase retry ``ledger.yml`` uses.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
import time
from pathlib import Path

import pandas as pd

from pipeline import prospective_receipt_core as core

from .dart_client import DartClient
from .identity import PitTop300, load_snapshots
from .prospective import live_append
from .registration import LEDGER_RELATIVE

REPO = Path(__file__).resolve().parents[3]


def git(*args, cwd=REPO, check=True) -> str:
    return subprocess.run(['git', *args], cwd=cwd, capture_output=True, text=True, check=check).stdout.strip()


def todays_signal_session(now_utc: pd.Timestamp) -> str | None:
    kst_day = (now_utc + core.KST).tz_localize(None).normalize()
    if not core.is_kr_session(kst_day):
        return None
    if now_utc < (kst_day + core.KR_CLOSE_FINAL_UTC).tz_localize('UTC'):
        return None
    return kst_day.strftime('%Y-%m-%d')


def push_with_retry(worktree: Path, message: str) -> str:
    git('add', LEDGER_RELATIVE, cwd=worktree)
    if not git('diff', '--cached', '--name-only', cwd=worktree):
        return 'NO_CHANGE'
    git('-c', 'user.name=corporate-event-receipt-bot', '-c', 'user.email=actions@github.com',
        'commit', '-m', message, cwd=worktree)
    for attempt in range(1, 6):
        if subprocess.run(['git', 'push', 'origin', 'HEAD:signal-history'], cwd=worktree).returncode == 0:
            return git('rev-parse', 'HEAD', cwd=worktree)
        git('fetch', 'origin', 'signal-history', cwd=worktree)
        if subprocess.run(['git', 'rebase', 'origin/signal-history'], cwd=worktree).returncode != 0:
            subprocess.run(['git', 'rebase', '--abort'], cwd=worktree)
            raise RuntimeError('REBASE_ONTO_SIGNAL_HISTORY_FAILED')
        time.sleep(attempt * 3)
    raise RuntimeError('PUSH_FAILED_AFTER_5_ATTEMPTS')


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--workdir', type=Path, default=None)
    p.add_argument('--no-push', action='store_true', help='write locally only (verification runs)')
    args = p.parse_args(argv)
    now = core.system_utc_now()
    signal_date = todays_signal_session(now)
    if signal_date is None:
        print(json.dumps({'status': 'NO_RECEIPT_DUE', 'nowUtc': now.isoformat()}))
        return 0
    work = Path(args.workdir or tempfile.mkdtemp(prefix='kr-event-live-'))
    worktree = work / 'signal-history'
    git('fetch', '--depth=1', 'origin', 'signal-history')
    git('worktree', 'add', '--force', str(worktree), 'FETCH_HEAD')
    git('checkout', '-B', 'signal-history-receipts', cwd=worktree)
    ledger = worktree / LEDGER_RELATIVE
    pit = PitTop300(load_snapshots(worktree / 'ledger' / 'universe' / 'kr'))
    client = DartClient(work / 'dart-cache')
    commit = git('rev-parse', 'HEAD')
    try:
        receipt = live_append(signal_date, client=client, pit=pit, ledger=ledger, code_commit=commit)
    except ValueError as exc:
        if str(exc) == 'RECEIPT_ALREADY_EXISTS':
            print(json.dumps({'status': 'ALREADY_RECORDED', 'signalDate': signal_date}))
            return 0
        raise
    status = 'WRITTEN_NOT_PUSHED' if args.no_push else push_with_retry(
        worktree, f'ledger: kr corporate event receipt {signal_date}')
    print(json.dumps({'status': 'RECORDED', 'signalDate': signal_date, 'events': receipt['eventCount'],
                      'receiptSha256': receipt['receiptSha256'], 'signalHistoryCommit': status,
                      'codeCommit': commit}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
