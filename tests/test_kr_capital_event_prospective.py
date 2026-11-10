"""The separate P2/K7 prospective study: definitions, refusal without authorization, and receipt rules."""
import json

import pytest

from pipeline import prospective_receipt_core as core
from research.kr_capital_event_prospective_v1 import recorder as R


def _row(no, code, fy, dps, title='현금ㆍ현물배당결정', **kw):
    return {'rcept_no': no, 'stock_code': code, 'dividendClass': '결산배당', 'dividendKind': '현금배당',
            'dpsCommonKrw': str(dps), 'recordDate': f'{fy}-12-31', 'report_nm': title, **kw}


def test_prior_year_base_is_the_issuers_own_original_decision():
    rows = [_row('1', 'A', 2024, 1000, title='현금ㆍ현물배당결정(자회사의 주요경영사항)'), _row('2', 'A', 2024, 500),
            _row('3', 'A', 2024, 700, amendment=True), _row('4', 'B', 2024, '-')]
    assert R.prior_year_end_dps(rows, '2026-01-01') == {('A', 2024): {'dps': 500.0, 'recordDate': '2024-12-31'}}


def test_prior_base_never_reads_a_decision_received_on_or_after_the_run():
    rows = [_row('20250210000001', 'A', 2024, 500), _row('20260305000001', 'A', 2025, 900)]
    assert set(R.prior_year_end_dps(rows, '2026-03-05')) == {('A', 2024)}          # same-day filing is not a base
    assert set(R.prior_year_end_dps(rows, '2026-03-06')) == {('A', 2024), ('A', 2025)}


def test_missed_sessions_are_listed_and_never_backfilled(tmp_path, monkeypatch):
    import pandas as pd
    monkeypatch.setattr(R, 'verify', lambda: {'firstEligibleSignalSession': '2026-11-11'})
    ledger = tmp_path / 'receipts.jsonl'
    ledger.write_text(json.dumps({'signalDate': '2026-11-11'}) + '\n' + json.dumps({'signalDate': '2026-11-13'}) + '\n')
    now = pd.Timestamp('2026-11-17T10:00:00Z')            # the 11-17 window is still open; 11-12 and 11-16 closed empty
    assert R.missed_sessions(ledger, now) == ['2026-11-12', '2026-11-16']
    assert R.missed_sessions(tmp_path / 'absent.jsonl', pd.Timestamp('2026-11-11T12:00:00Z')) == []


def test_no_authorization_means_no_live_recording():
    assert not R.AUTHORIZATION.exists() or R.verify()['specSha256']
    if not R.AUTHORIZATION.exists():
        with pytest.raises(ValueError, match='NO_REGISTERED_AUTHORIZATION'):
            R.verify()


def test_pinned_code_matches_the_spec_and_ledger_is_separate():
    spec = json.loads(R.SPEC.read_text(encoding='utf-8'))
    assert set(spec['codeSha256']) == set(R.PINNED_CODE)
    assert all(R.hashlib.sha256((R.REPO / p).read_bytes()).hexdigest() == h for p, h in spec['codeSha256'].items())
    assert spec['ledger'] == R.LEDGER_RELATIVE and 'kr-corporate-information-events-v1' not in R.LEDGER_RELATIVE


def _receipt(mode='DRY_RUN', **kw):
    return R.session_receipt('2026-11-11', [], [], [], spec_sha256='a' * 64, created_at_utc='2026-11-11T10:00:00+00:00',
                             mode=mode, **kw)


def test_receipt_holds_no_names_and_a_dry_run_is_never_prospective_evidence():
    r = _receipt()
    assert r['evidenceClass'] == R.DRY_RUN_CLASS and r['book']['signalNames'] == 0 and r['book']['etfWeight'] == 1.0
    live = _receipt('LIVE', authorization={'authorizationSha256': 'b' * 64}, code_commit='c' * 40)
    assert live['evidenceClass'] == core.EVIDENCE_CLASS
    bad = {**r, 'book': {**r['book'], 'signalNames': 1}}
    bad.pop('receiptSha256')
    with pytest.raises(ValueError, match='UNVERIFIED_CANDIDATES_CANNOT_HOLD_NAMES'):
        R.validate(bad)
    with pytest.raises(ValueError, match='LIVE_REQUIRES_AUTHORIZATION'):
        _receipt('LIVE')


def test_a_receipt_cannot_be_backdated_or_written_before_the_close():
    kw = dict(signal_date='2026-11-11', merged_at_utc='2026-11-10T06:00:00+00:00')
    with pytest.raises(ValueError, match='BEFORE_SIGNAL_CLOSE'):
        core.check_timing(created_at_utc='2026-11-11T08:59:00+00:00', now_utc='2026-11-11T08:59:00+00:00', **kw)
    with pytest.raises(ValueError, match='BACKDATED'):
        core.check_timing(created_at_utc='2026-11-12T00:00:00+00:00', now_utc='2026-11-12T00:00:00+00:00', **kw)
    with pytest.raises(ValueError, match='BEFORE_PROSPECTIVE_ELIGIBILITY'):
        core.check_timing(signal_date='2026-11-10', merged_at_utc='2026-11-10T06:00:00+00:00',
                          created_at_utc='2026-11-10T10:00:00+00:00', now_utc='2026-11-10T10:00:00+00:00')
    assert core.check_timing(created_at_utc='2026-11-11T10:00:00+00:00', now_utc='2026-11-11T10:00:00+00:00',
                             **kw).strftime('%Y-%m-%d') == '2026-11-12'


def test_push_survives_a_moved_branch_and_is_verified_on_the_remote(tmp_path):
    import subprocess

    def g(*a, cwd):
        return subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@t', *a], cwd=cwd, check=True,
                              capture_output=True, text=True).stdout.strip()
    remote, seed, work, other = (tmp_path / n for n in ('remote.git', 'seed', 'work', 'other'))
    subprocess.run(['git', 'init', '-q', '--bare', str(remote)], check=True)
    subprocess.run(['git', 'init', '-q', str(seed)], check=True)
    (seed / 'x').write_text('x')
    g('add', '.', cwd=seed)
    g('commit', '-qm', 'seed', cwd=seed)
    g('push', '-q', str(remote), 'HEAD:signal-history', cwd=seed)
    for clone in (work, other):
        subprocess.run(['git', 'clone', '-q', '-b', 'signal-history', str(remote), str(clone)], check=True)
    (other / 'y').write_text('y')                       # another writer moves the branch first
    g('add', '.', cwd=other)
    g('commit', '-qm', 'other writer', cwd=other)
    g('push', '-q', 'origin', 'HEAD:signal-history', cwd=other)
    receipt = _receipt('LIVE', authorization={'authorizationSha256': 'b' * 64}, code_commit='c' * 40)
    ledger = work / R.LEDGER_RELATIVE
    ledger.parent.mkdir(parents=True)
    ledger.write_bytes(core.canonical(receipt) + b'\n')
    g('add', '.', cwd=work)
    g('commit', '-qm', 'receipt', cwd=work)
    commit = R.push_and_verify(work, receipt)
    assert g('rev-parse', 'signal-history', cwd=remote) == commit
    assert g('show', 'signal-history:y', cwd=remote) == 'y'            # the other writer's commit is kept
    with pytest.raises(SystemExit, match='REMOTE_LEDGER_DOES_NOT_CARRY_THIS_RECEIPT'):
        R.push_and_verify(work, {**receipt, 'receiptSha256': 'd' * 64})
