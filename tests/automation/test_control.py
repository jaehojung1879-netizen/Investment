from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
import subprocess

import pytest

from automation.control import GATES, Journal, apply, select, validate


def task(key, priority=1, deps=(), resources=None):
    return dict(id=key, issue=100 + priority, track='A', priority=priority,
                dependencies=list(deps), agent='codex', risk='LOW', kind='a2_preview',
                acceptance=['synthetic only'], resources=resources or [key],
                gates=dict.fromkeys(GATES, False), status='READY', claim=None, pr=None,
                head_sha=None, run_id=None, ci='UNRUN', repairs=0, history=[],
                scope_sha256=hashlib.sha256(key.encode()).hexdigest())


def queue(*tasks):
    return dict(version=1, tasks=list(tasks), events={})


def event(op, **kwargs):
    return dict(id=op + str(kwargs), task='a', op=op, **kwargs)


def claimed(q=None):
    q = q or queue(task('a'))
    e = event('claim')
    return apply(q, e), e['id']


def started(q, claim, head='a' * 40, run=1):
    return apply(q, event('ci_started', claim=claim, pr=1, head_sha=head, run_id=run))


def result(q, claim, outcome):
    t = q['tasks'][0]
    return apply(q, event('ci_result', claim=claim, head_sha=t['head_sha'], run_id=t['run_id'], outcome=outcome))


def test_duplicate_delivery_and_collision():
    q = queue(task('a'))
    e = event('claim')
    n = apply(q, e)
    assert apply(n, e) == n
    assert q['tasks'][0]['status'] == 'READY'
    with pytest.raises(ValueError, match='collision'):
        apply(n, {**e, 'task': 'b'})


def test_dependencies_blocked_owner_and_resource_conflicts():
    q = queue(task('a', deps=['b']), task('b', 2), task('c', 3))
    q['tasks'][1]['status'] = 'BLOCKED_OWNER'
    assert select(q)['candidate'] == 'c'
    q['tasks'][2]['dependencies'] = ['a']
    assert select(q)['stop']
    q['tasks'][1]['dependencies'] = ['a']
    with pytest.raises(ValueError, match='cycle'):
        select(q)
    q, _ = claimed(queue(task('a', resources=['shared']), task('b', 2, resources=['shared']), task('c', 3)))
    assert select(q)['candidate'] == 'c'


def test_two_slots_and_no_duplicate_pending_ci():
    q, claim = claimed(queue(task('a'), task('b', 2), task('c', 3)))
    q = started(q, claim)
    q = apply(q, dict(id='worker-b', task='b', op='claim'))
    assert select(q)['candidate'] is None
    assert select(q)['resume'][0]['action'] == 'MONITOR_EXISTING_CI'
    with pytest.raises(ValueError):
        apply(q, dict(id='duplicate-worker', task='a', op='claim'))
    with pytest.raises(ValueError):
        apply(q, dict(id='third-worker', task='c', op='claim'))


def test_failure_repair_budget_and_interruption_history():
    q, claim = claimed()
    for i in range(3):
        q = started(q, claim, str(i) * 40, i + 1)
        q = result(q, claim, 'FAILURE')
        q = json.loads(json.dumps(q))  # restart in a new process
    t = q['tasks'][0]
    assert t['status'] == 'FAILED' and t['repairs'] == 2
    assert len(t['history']) == 7
    assert [e['run_id'] for e in t['history'] if e['op'] == 'ci_started'] == [1, 2, 3]
    assert select(q)['stop']


def test_exact_head_review_and_no_merge():
    q, claim = claimed()
    q = started(q, claim)
    with pytest.raises(ValueError, match='stale'):
        apply(q, event('ci_result', claim=claim, head_sha='b' * 40, run_id=1, outcome='SUCCESS'))
    with pytest.raises(ValueError, match='not a pass'):
        result(q, claim, 'SKIPPED')
    q = result(q, claim, 'SUCCESS')
    assert select(q)['resume'][0]['action'] == 'REQUEST_INDEPENDENT_REVIEW'
    with pytest.raises(ValueError, match='independent'):
        apply(q, event('review', claim=claim, head_sha='a' * 40, reviewer='codex', verdict='APPROVED'))
    q = apply(q, event('review', claim=claim, head_sha='a' * 40, reviewer='claude', verdict='APPROVED'))
    assert q['tasks'][0]['status'] == 'DONE'
    with pytest.raises(ValueError, match='unknown event'):
        apply(q, event('merge', claim=claim))


@pytest.mark.parametrize('gate', sorted(GATES))
def test_owner_gates(gate):
    q = queue(task('a'))
    q['tasks'][0]['gates'][gate] = True
    with pytest.raises(ValueError, match='owner-only'):
        select(q)


def test_unknown_scope_fields_and_claim_theft():
    q, claim = claimed()
    with pytest.raises(ValueError, match='claim mismatch'):
        started(q, claim + 'stolen')
    with pytest.raises(ValueError, match='unknown event'):
        apply(q, {**event('block', claim=claim), 'secret': 'do-not-store'})
    bad = deepcopy(q)
    bad['tasks'][0]['kind'] = 'c1_execute'
    with pytest.raises(ValueError, match='unsupported'):
        validate(bad)


def git(path, *args):
    return subprocess.run(['git', '-C', str(path), *args], check=True, text=True, capture_output=True).stdout.strip()


def test_remote_cas_concurrent_workers_and_restart(tmp_path):
    remote = tmp_path / 'remote.git'
    remote.mkdir()
    git(remote, 'init', '--bare')
    workers = []
    for name in ('one', 'two'):
        repo = tmp_path / name
        repo.mkdir()
        git(repo, 'init')
        git(repo, 'config', 'user.name', 'Synthetic Worker')
        git(repo, 'config', 'user.email', 'synthetic@example.invalid')
        git(repo, 'remote', 'add', 'origin', str(remote))
        workers.append(Journal(repo))
    workers[0].save(None, queue(task('a'), task('b', 2), task('c', 3)))
    snapshots = [w.load() for w in workers]
    def race(pair):
        w, (base, q) = pair
        try:
            w.save(base, apply(q, event('claim')))
            return 'claimed'
        except subprocess.CalledProcessError:
            return 'conflict'
    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(race, zip(workers, snapshots))) == ['claimed', 'conflict']
    _, resumed = workers[1].load()
    assert select(resumed)['resume'] == [{'task': 'a', 'action': 'RESUME_EXISTING_CLAIM'}]
    assert select(resumed)['candidate'] == 'b'
    # No read of research files: queue-only tree and no checkout required.
    head, _ = workers[0].load()
    assert git(workers[0].repo, 'ls-tree', '--name-only', head) == 'queue.json'


def test_same_event_sequential_stale_writers_cannot_both_claim(tmp_path):
    remote, repo = tmp_path / 'remote.git', tmp_path / 'worker'
    remote.mkdir(); repo.mkdir()
    git(remote, 'init', '--bare'); git(repo, 'init')
    git(repo, 'config', 'user.name', 'Synthetic Worker')
    git(repo, 'config', 'user.email', 'synthetic@example.invalid')
    git(repo, 'remote', 'add', 'origin', str(remote))
    journal = Journal(repo)
    journal.save(None, queue(task('a')))
    base, q = journal.load()
    n = apply(q, event('claim'))
    journal.save(base, n)
    # Without a unique writer commit this can be an up-to-date push, giving
    # two workers a success receipt for the same claim even without overlap.
    with pytest.raises(subprocess.CalledProcessError):
        journal.save(base, n)
    _, resumed = journal.load()
    assert apply(resumed, event('claim')) == resumed


def test_controller_has_no_research_or_merge_execution_paths():
    import ast
    from pathlib import Path
    source = Path('automation/control.py').read_text()
    tree = ast.parse(source)
    imports = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    imports |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not any(i and i.startswith(('pipeline', 'scripts')) for i in imports)
    assert 'workflow_dispatch' not in source
    assert "'merge'" not in source
    assert "'--force'" not in source


def test_unchanged_head_and_stale_review_cannot_rerun_ci():
    q, claim = claimed()
    q = result(started(q, claim), claim, 'SUCCESS')
    q = apply(q, event('review', claim=claim, head_sha='a' * 40, reviewer='claude', verdict='CHANGES'))
    with pytest.raises(ValueError, match='change the head'):
        apply(q, {**event('ci_started', claim=claim, pr=1, head_sha='a' * 40, run_id=2), 'id': 'new-ci-same-head'})
    q = started(q, claim, 'b' * 40, 2)
    with pytest.raises(ValueError):
        apply(q, event('review', claim=claim, head_sha='a' * 40, reviewer='claude', verdict='APPROVED'))
