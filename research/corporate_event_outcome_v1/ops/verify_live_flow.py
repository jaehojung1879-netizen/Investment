"""Isolated verification of the registered LIVE writer's git flow + the pushed-only cleanup rule.
Runs the REGISTERED live_run.main (commit 8aee189) against a local bare 'origin'; only the receipt
content (live_append), clock and DART/universe readers are stubbed. No GitHub, no DART, no real ledger."""
import json, subprocess, sys, tempfile
from pathlib import Path
CODE, CLEAN = sys.argv[1], sys.argv[2]
sys.path.insert(0, CODE)
from research.corporate_event_readiness_v1.cohort import live_run as L
from research.corporate_event_readiness_v1.cohort.registration import LEDGER_RELATIVE

T = Path(tempfile.mkdtemp()); origin, main = T / 'origin.git', T / 'main'
def sh(*a, cwd=None, check=True): return subprocess.run(a, cwd=cwd, capture_output=True, text=True, check=check)
sh('git', 'init', '-q', '--bare', str(origin)); sh('git', 'init', '-q', str(main))
sh('git', '-c', 'user.name=a', '-c', 'user.email=a@b', 'commit', '-q', '--allow-empty', '-m', 'init', cwd=main)
sh('git', 'remote', 'add', 'origin', str(origin), cwd=main); sh('git', 'push', '-q', 'origin', 'HEAD:refs/heads/signal-history', cwd=main)
real_git = L.git
L.git = lambda *a, cwd=main, check=True: real_git(*a, cwd=cwd, check=check)
L.PitTop300 = lambda snaps: None; L.load_snapshots = lambda p: []; L.DartClient = lambda p: None
def fake_append(signal_date, *, client, pit, ledger, code_commit):
    ledger = Path(ledger); ledger.parent.mkdir(parents=True, exist_ok=True)
    rows = [json.loads(x) for x in ledger.read_text().splitlines()] if ledger.exists() else []
    if any(r['signalDate'] == signal_date for r in rows): raise ValueError('RECEIPT_ALREADY_EXISTS')
    r = {'signalDate': signal_date, 'eventCount': 0, 'receiptSha256': 'x' * 64}
    with ledger.open('a') as fh: fh.write(json.dumps(r) + '\n')
    return r
L.live_append = fake_append
def run(day):
    L.todays_signal_session = lambda now: day
    work = T / f'kr-event-live-work-{day}'
    try:
        L.main(['--workdir', str(work)]); status = 'OK'
    except Exception as e:
        status = f'RAISED {type(e).__name__}: {e}'
    clean = sh(CLEAN, str(main), str(T / 'kr-event-live-work-*/signal-history'), check=False).stdout.strip()
    ledger = sh('git', 'show', f'signal-history:{LEDGER_RELATIVE}', cwd=origin, check=False).stdout.splitlines()
    print(json.dumps({'day': day, 'run': status, 'cleanup': clean, 'originReceipts': [json.loads(x)['signalDate'] for x in ledger],
                      'worktrees': len(sh('git', 'worktree', 'list', cwd=main).stdout.splitlines()) - 1}, ensure_ascii=False))
L.time.sleep = lambda s: None
run('2026-11-09')                        # first run
run('2026-11-10')                        # second run (previous worktree must already be gone)
run('2026-11-10')                        # duplicate run on the same day
hook = origin / 'hooks' / 'pre-receive'; hook.write_text('#!/bin/sh\nexit 1\n'); hook.chmod(0o755)
run('2026-11-11')                        # push rejected: receipt must stay in a kept worktree
hook.unlink()
run('2026-11-12')                        # next day after the failure
