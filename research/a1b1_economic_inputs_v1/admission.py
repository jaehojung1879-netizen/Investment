"""Compare presence-only admission using the exact existing #320 gate.

Read compressed Git objects one at a time; never check out signal-history or
retain numerical prices. Repair files, when supplied, replace only that shard
in this isolated comparison. No event is dropped and no outcome is evaluated.
"""
import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess

from pipeline import replay_calendar as calendar

from .references import load

LEDGER_SHA = '73b3907a663ebe300a435d0d57db4b2eee9e5ea4'
COHORT_SHA = '9a47f478a407fae5324e8ae04e75199c16b56023'
COHORT_PATH = 'research/corporate_event_readiness_v1/cohort/data/cohort-events-v1.jsonl.gz'


def git(repo, *args):
    return subprocess.run(['git', '--no-replace-objects', *args], cwd=repo, check=True,
                          capture_output=True, timeout=60,
                          env={**os.environ, 'GIT_NO_LAZY_FETCH': '1'}).stdout


def project(raw, target):
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
        for line in stream:
            row = json.loads(line)
            ticker, day, volume = row['ticker'], row['date'], row.get('volume')
            del row
            target[ticker][day] = volume is not None and float(volume) > 0


def audit(repo, repaired=None):
    names = git(repo, 'ls-tree', '-r', '--name-only', LEDGER_SHA, 'ledger/prices/kr').decode().splitlines()
    names = [n for n in names if Path(n).name.startswith('krx-prices-') and n.endswith('.jsonl.gz')]
    before, after = defaultdict(dict), defaultdict(dict)
    sources = []
    for name in names:
        raw = git(repo, 'show', LEDGER_SHA + ':' + name)
        if len(raw) > 16 * 1024 * 1024:
            raise ValueError('SOURCE_SHARD_SIZE_LIMIT')
        project(raw, before)
        candidate = Path(repaired) / Path(name).name if repaired else None
        replacement = candidate.read_bytes() if candidate and candidate.is_file() else raw
        project(replacement, after)
        sources.append({'path': name, 'beforeSha256': hashlib.sha256(raw).hexdigest(),
                        'afterSha256': hashlib.sha256(replacement).hexdigest()})
    events_raw = git(repo, 'show', COHORT_SHA + ':' + COHORT_PATH)
    events = [json.loads(line) for line in gzip.decompress(events_raw).splitlines()]
    sessions = [d.strftime('%Y-%m-%d') for d in calendar.sessions('2013-01-01', '2027-12-31', 'KR')]
    gate = load('admission', repo).window_admission
    ledger_end = max(day for bars in before.values() for day in bars)
    tables = {}
    for hyp in ('A1', 'B1'):
        for h in (126, 252):
            subset = [e for e in events if e.get('pitGrade') and e['hypothesis'] == hyp
                      and e['independent'][f'H{h}']]
            a, b, changes = Counter(), Counter(), []
            for event in subset:
                ticker = event['stock_code'] + '.KS'
                old = gate(before.get(ticker), sessions, event['entrySession'], h, ledger_end)
                new = gate(after.get(ticker), sessions, event['entrySession'], h, ledger_end)
                a[old['status']] += 1
                b[new['status']] += 1
                if old != new:
                    changes.append({'receipt': event['rcept_no'], 'ticker': ticker,
                                    'before': old, 'after': new})
            tables[f'{hyp}_H{h}'] = {'N': len(subset), 'before': dict(a), 'after': dict(b),
                                     'newFullWindows': b['FULL_WINDOW_TRADED'] - a['FULL_WINDOW_TRADED'],
                                     'changes': changes}
    return {'scope': 'SOURCE_PRESENCE_ONLY_NO_RETURN_NAV_LABEL', 'ledgerSha': LEDGER_SHA,
            'cohortSha': COHORT_SHA, 'cohortBytesSha256': hashlib.sha256(events_raw).hexdigest(),
            'ledgerEnd': ledger_end, 'sources': sources, 'windowAdmission': tables,
            'fullyQualifiedEconomicEventIncrease': 0,
            'qualificationNote': 'Presence alone cannot establish dividends/actions/cash/tax eligibility',
            'repairedSourceProvided': repaired is not None, 'outcomeExecutionAuthorized': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path.cwd())
    parser.add_argument('--repaired', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.repo, args.repaired)
    args.out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'ledgerEnd': report['ledgerEnd'], 'windowAdmission': report['windowAdmission']}, indent=2))


if __name__ == '__main__':
    main()
