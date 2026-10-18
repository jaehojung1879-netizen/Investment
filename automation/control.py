"""Fail-closed queue decisions. JSON metadata in a single Git CAS journal.

Does not launch commands, dispatch workflows, read research, or merge PRs.
Only a successful non-forced fast-forward push grants a claim.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
import re
import subprocess
import uuid
from pathlib import Path

REF = 'refs/heads/automation/queue-v1'
ACTIVE = {'RUNNING', 'CI_WAIT', 'REVIEW'}
STATES = ACTIVE | {'READY', 'DONE', 'BLOCKED_OWNER', 'FAILED'}
KINDS = {'collector_integrity', 'a2_preview', 'market_risk_preview', 'b_state_preview',
         'd_shadow_adapter', 'us_h1_rights_review'}
# All must be explicitly false, including on blocked tasks. Owner approval never
# turns this controller into a research executor; use a separate owner process.
GATES = {'formal_execute', 'outcome_access', 'sealed_write', 'spec_change', 'live_promotion',
         'production_change', 'spending', 'permission_change', 'secret_change',
         'licensed_persistence', 'merge_main', 'live_receipts', 'external_acquisition'}
SHA = re.compile(r'[0-9a-f]{40}')


def validate(q):
    if set(q) != {'version', 'tasks', 'events'} or q['version'] != 1:
        raise ValueError('unknown queue schema')
    if not isinstance(q['events'], dict) or not isinstance(q['tasks'], list):
        raise ValueError('invalid journal')
    ids = [t['id'] for t in q['tasks']]
    if len(ids) != len(set(ids)):
        raise ValueError('duplicate task')
    active = []
    for t in q['tasks']:
        if set(t) != {'id', 'issue', 'track', 'priority', 'dependencies', 'agent', 'risk', 'kind',
                      'acceptance', 'resources', 'gates', 'status', 'claim', 'pr', 'head_sha',
                      'run_id', 'ci', 'repairs', 'history', 'scope_sha256'}:
            raise ValueError('unknown task fields')
        if t['status'] not in STATES or t['track'] not in 'ABCD' or len(t['track']) != 1:
            raise ValueError('unknown status/track')
        if t['kind'] not in KINDS or t['risk'] != 'LOW' or t['agent'] != 'codex':
            raise ValueError('unsupported scope, risk, or implementer')
        if set(t['gates']) != GATES or any(v is not False for v in t['gates'].values()):
            raise ValueError('owner-only gate')
        if not isinstance(t['issue'], int) or t['issue'] < 1:
            raise ValueError('real issue number required')
        if not re.fullmatch(r'[0-9a-f]{64}', t['scope_sha256']):
            raise ValueError('pin issue specification digest')
        if not isinstance(t['priority'], int) or not t['acceptance'] or not t['resources']:
            raise ValueError('missing acceptance/resources')
        if any(d not in ids or d == t['id'] for d in t['dependencies']):
            raise ValueError('unknown/self dependency')
        if t['repairs'] not in (0, 1, 2) or t['ci'] not in {'UNRUN', 'PENDING', 'SUCCESS', 'FAILURE'}:
            raise ValueError('invalid CI/repair state')
        if t['head_sha'] is not None and not SHA.fullmatch(t['head_sha']):
            raise ValueError('invalid head SHA')
        if t['status'] in ACTIVE:
            if not t['claim']:
                raise ValueError('active task needs durable claim')
            if any(set(t['resources']) & set(a['resources']) for a in active):
                raise ValueError('overlapping active work')
            active.append(t)
        if t['status'] in {'CI_WAIT', 'REVIEW', 'DONE'}:
            if not all(t[k] for k in ('pr', 'head_sha', 'run_id')):
                raise ValueError('missing PR/head/run evidence')
        if t['status'] in {'REVIEW', 'DONE'} and t['ci'] != 'SUCCESS':
            raise ValueError('review requires successful exact-head CI')
    if len(active) > 2:
        raise ValueError('two-slot limit')
    # Cycles are errors, never silently treated as an empty queue.
    def visit(key, stack):
        if key in stack:
            raise ValueError('dependency cycle')
        for dep in next(t for t in q['tasks'] if t['id'] == key)['dependencies']:
            visit(dep, stack | {key})
    for key in ids:
        visit(key, set())


def select(q):
    validate(q)
    active = [t for t in q['tasks'] if t['status'] in ACTIVE]
    resume = [{'task': t['id'], 'action': {'CI_WAIT': 'MONITOR_EXISTING_CI',
               'REVIEW': 'REQUEST_INDEPENDENT_REVIEW', 'RUNNING': 'RESUME_EXISTING_CLAIM'}[t['status']]}
              for t in active]
    done = {t['id'] for t in q['tasks'] if t['status'] == 'DONE'}
    busy = {r for t in active for r in t['resources']}
    ready = sorted((t for t in q['tasks'] if t['status'] == 'READY'
                    and set(t['dependencies']) <= done and not busy.intersection(t['resources'])),
                   key=lambda t: (t['priority'], t['id']))
    # Return only one candidate. Another selection must reload committed state.
    return {'resume': resume, 'candidate': ready[0]['id'] if ready and len(active) < 2 else None,
            'stop': not active and not ready}


def apply(q, event):
    """Pure atomic transition; journal event ID makes redelivery a no-op.

    Remote callers must CAS-commit this result before acting on it. Input events
    are observations of the exact head/run, never instructions from PR text.
    """
    validate(q)
    fields = {'claim': {'id', 'task', 'op'},
              'ci_started': {'id', 'task', 'op', 'claim', 'pr', 'head_sha', 'run_id'},
              'ci_result': {'id', 'task', 'op', 'claim', 'head_sha', 'run_id', 'outcome'},
              'review': {'id', 'task', 'op', 'claim', 'head_sha', 'reviewer', 'verdict'},
              'block': {'id', 'task', 'op', 'claim'}}
    if event.get('op') not in fields or set(event) != fields[event['op']]:
        raise ValueError('unknown event fields; metadata only')
    if not event.get('id') or len(event['id']) > 160:
        raise ValueError('bounded event ID required')
    if event['id'] in q['events']:
        if q['events'][event['id']] != event:
            raise ValueError('event ID collision')
        return deepcopy(q)
    n = deepcopy(q)
    t = next(t for t in n['tasks'] if t['id'] == event['task'])
    op = event['op']
    before = t['status']
    if op == 'claim':
        if select(n)['candidate'] != t['id']:
            raise ValueError('not selectable')
        t.update(status='RUNNING', claim=event['id'])
    else:
        if not t['claim'] or event.get('claim') != t['claim']:
            raise ValueError('claim mismatch; no automatic lease expiry')
        if op == 'ci_started' and before == 'RUNNING':
            if not isinstance(event['pr'], int) or event['pr'] < 1 or not isinstance(event['run_id'], int) or event['run_id'] < 1:
                raise ValueError('positive PR and run IDs required')
            if t['pr'] is not None and t['pr'] != event['pr']:
                raise ValueError('one PR per task')
            if t['head_sha'] == event['head_sha']:
                raise ValueError('repair must change the head; no blind CI retry')
            if any(e.get('run_id') == event['run_id'] for e in t['history']):
                raise ValueError('CI run ID already recorded')
            t.update(status='CI_WAIT', pr=event['pr'], head_sha=event['head_sha'],
                     run_id=event['run_id'], ci='PENDING')
        elif op == 'ci_result' and before == 'CI_WAIT':
            if event['head_sha'] != t['head_sha'] or event['run_id'] != t['run_id']:
                raise ValueError('stale head/run observation')
            if event['outcome'] not in {'SUCCESS', 'FAILURE'}:
                raise ValueError('pending/cancelled/skipped/unknown is not a pass')
            t['ci'] = event['outcome']
            if t['ci'] == 'SUCCESS':
                t['status'] = 'REVIEW'
            elif t['repairs'] < 2:
                t.update(status='RUNNING', repairs=t['repairs'] + 1)
            else:
                t['status'] = 'FAILED'
        elif op == 'review' and before == 'REVIEW':
            if event['head_sha'] != t['head_sha'] or event['reviewer'] == t['agent'] or event['reviewer'] != 'claude':
                raise ValueError('independent exact-head Claude review required')
            if event['verdict'] == 'APPROVED':
                t['status'] = 'DONE'  # reviewed work, NOT a merge or scientific approval
            elif event['verdict'] == 'CHANGES' and t['repairs'] < 2:
                t.update(status='RUNNING', repairs=t['repairs'] + 1)
            else:
                t['status'] = 'FAILED'
        elif op == 'block' and before in ACTIVE:
            t['status'] = 'BLOCKED_OWNER'
        else:
            raise ValueError('forbidden transition')
    t['history'].append(event)
    n['events'][event['id']] = event
    validate(n)
    return n


class Journal:
    """Single native Git ref: non-forced fast-forward is compare-and-swap.

    The queue ref is never checked out. Rejected writers must reload and decide
    again; never retry a push with force or run work from uncommitted state.
    """
    def __init__(self, repo, remote='origin'):
        self.repo, self.remote = str(repo), remote

    def git(self, *args, input=None):
        return subprocess.run(['git', '-C', self.repo, *args], input=input, text=True,
                              capture_output=True, check=True).stdout.strip()

    def load(self):
        self.git('fetch', '--no-tags', self.remote, REF)
        head = self.git('rev-parse', 'FETCH_HEAD')
        q = json.loads(self.git('show', f'{head}:queue.json'))
        validate(q)
        return head, q

    def save(self, base, q):
        validate(q)
        blob = self.git('hash-object', '-w', '--stdin', input=json.dumps(q, sort_keys=True) + '\n')
        tree = self.git('mktree', input=f'100644 blob {blob}\tqueue.json\n')
        # Different writers of the same event must not produce the same commit.
        args = ['commit-tree', tree, '-m', 'autopilot: atomic metadata transition ' + uuid.uuid4().hex]
        if base:
            args += ['-p', base]
        commit = self.git(*args)
        self.git('push', self.remote, f'{commit}:{REF}')
        return commit


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo', default='.')
    p.add_argument('--file', type=Path, help='offline read-only JSON fixture')
    p.add_argument('--event', type=Path, help='commit one metadata event; never launches work')
    a = p.parse_args()
    committed = False
    if a.file:
        if a.event:
            p.error('--file is read-only')
        q = json.loads(a.file.read_text())
    else:
        journal = Journal(a.repo)
        base, q = journal.load()
        if a.event:
            updated = apply(q, json.loads(a.event.read_text()))
            if updated != q:
                journal.save(base, updated)
                committed = True
            q = updated
    print(json.dumps({'event_committed': committed, **select(q)}, indent=2))


if __name__ == '__main__':
    main()
