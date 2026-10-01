"""Synthetic acquisition/snapshot fixtures only: no real historical outcomes."""
from copy import deepcopy
from dataclasses import asdict
import json
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from pipeline import kr_model_raw_snapshot as S
from pipeline import kr_model_portfolio_execution as X
from scripts import prepare_kr_model_raw_snapshot as CLI

DATE = '2020-01-03'


def payload():
    return {'OutBlock_1': [{'ISU_SRT_CD': '000001', 'BAS_DD': '20200103', 'TDD_CLSPRC': '100',
                           'MKTCAP': '100,000,000', 'LIST_SHRS': '1,000,000',
                           'ACC_TRDVOL': '1000', 'ACC_TRDVAL': '100000'}]}


def acquire(root):
    return S.collect_official(root, [DATE], ['000001.KS'], key='synthetic-key',
                              fetch=lambda *args: payload(), pace=0)


def seal(root, monkeypatch):
    acquire(root)
    monkeypatch.setattr(S, 'required_dates', lambda spec: [DATE])
    monkeypatch.setattr(X, 'load_sources', lambda *args: None)
    return S.freeze_snapshot(root, S.frozen_spec())


def test_deterministic_normalization_and_duplicate_rejection():
    data = payload()
    second = deepcopy(data['OutBlock_1'][0]); second['ISU_SRT_CD'] = '000002'
    data['OutBlock_1'].append(second)
    rows, provenance = S.normalize_official(data, DATE)
    data['OutBlock_1'].reverse()
    assert S.normalize_official(data, DATE) == (rows, provenance)
    data['OutBlock_1'].append(second)
    with pytest.raises(ValueError, match='DUPLICATE'):
        S.normalize_official(data, DATE)


@pytest.mark.parametrize('field,value', [('ACC_TRDVAL', None), ('ACC_TRDVOL', '-1'),
                                         ('LIST_SHRS', '0'), ('TDD_CLSPRC', 'NaN'),
                                         ('MKTCAP', '10'), ('BAS_DD', '20200106'),
                                         ('ISU_SRT_CD', 'bad')])
def test_required_fields_invalid_values_and_identity(field, value):
    data = payload(); data['OutBlock_1'][0][field] = value
    with pytest.raises(ValueError):
        S.normalize_official(data, DATE)


def test_cache_requires_verified_raw_lineage(tmp_path):
    report = acquire(tmp_path)
    assert report['complete'] and report['cache']['rows'] == 1
    S.verify_cached_day(tmp_path, DATE, ['000001.KS'])
    before = (tmp_path / 'market' / (DATE + '.json')).read_bytes()
    again = acquire(tmp_path)
    assert again['calls'] == 0
    assert (tmp_path / 'market' / (DATE + '.json')).read_bytes() == before
    (tmp_path / 'sources/krx' / (DATE + '.json.gz')).unlink()
    with pytest.raises(OSError):
        acquire(tmp_path)


def test_snapshot_identity_repeatable_and_component_tampering(tmp_path, monkeypatch):
    first = seal(tmp_path, monkeypatch)
    assert S.freeze_snapshot(tmp_path, S.frozen_spec()) == first
    assert S.verify_snapshot(tmp_path) == first
    component = tmp_path / 'sources/provenance' / (DATE + '.json')
    component.write_text(component.read_text() + ' ')
    with pytest.raises(ValueError, match='COMPONENT_CHANGED'):
        S.verify_snapshot(tmp_path)


def test_manifest_and_extra_file_tampering(tmp_path, monkeypatch):
    seal(tmp_path, monkeypatch)
    extra = tmp_path / 'labels.json'; extra.write_text('{}')
    with pytest.raises(ValueError, match='NON_ALLOWLIST'):
        S.verify_snapshot(tmp_path)
    extra.unlink()
    path = tmp_path / S.MANIFEST
    doc = json.loads(path.read_text()); doc['sha256'] = '0'*64
    path.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match='MANIFEST_CHANGED'):
        S.verify_snapshot(tmp_path)


def test_exact_component_hash_required(tmp_path, monkeypatch):
    doc = seal(tmp_path, monkeypatch)
    name = next(iter(doc['components']))
    doc['components'][name]['sha256'] = '0'*64
    doc['sha256'] = S.digest({k:v for k,v in doc.items() if k != 'sha256'})
    X.atomic_write(tmp_path / S.MANIFEST, doc)
    (tmp_path / 'snapshot-manifest.sha256').write_text(doc['sha256']+'\n')
    with pytest.raises(ValueError, match='COMPONENT_CHANGED'):
        S.verify_snapshot(tmp_path)


def test_gates_use_exact_snapshot_and_forbid_outcomes(tmp_path, monkeypatch):
    seal(tmp_path, monkeypatch)
    from scripts import run_kr_model_overlay_portfolio_v1 as formal
    def run(mode, *, input_root, root):
        assert mode == 'gates-only' and input_root == tmp_path
        for name in ('build_labels', 'model_predictions', 'evaluate_model', 'replay_portfolio',
                     'run_historical', 'issue_permit', 'claim_execution_lock', 'require_authorization'):
            with pytest.raises(RuntimeError, match='FORBIDDEN'):
                getattr(X, name)()
        for model in (X.M.Ridge(), X.M.HistGradientBoostingRegressor()):
            with pytest.raises(RuntimeError, match='FORBIDDEN'):
                model.fit([[0]], [0])
        return {'status': 'DATA_INSUFFICIENT', 'counters': asdict(X.Counters())}
    monkeypatch.setattr(formal, 'run', run)
    report = S.gates_only(tmp_path)
    assert report['counters'] == asdict(X.Counters())
    assert not report['executionPermitIssued']


def test_raw_observability_and_frozen_twenty_percent_floor():
    spec = S.frozen_spec()
    assert spec['gates']['coreFamilyFloor'] == .2
    frame = pd.DataFrame([{n: np.nan for n in S.F.RAW_FEATURES} for _ in range(10)])
    for family in ('VALUE', 'QUALITY', 'CATALYST'):
        frame.loc[0, S.F.FAMILIES[family][0]] = 1.
    frame['date'] = DATE; frame['ticker'] = [f'{i:06d}.KS' for i in range(10)]
    frame['accountingProvenance'] = [{} for _ in range(10)]
    frame['marketValuePresent'] = True; frame['tradable'] = True
    coverage = S.annual_coverage({'features': frame}, spec)['2020']
    assert coverage['pitUniverseDenominator'] == 10
    assert coverage['families']['coreFamilyObserved'] == {'count': 1, 'share': .1}
    bundle = {'features': frame, 'schedule': [DATE], 'overlay': {DATE: {'status': 'READY'}}}
    with patch.object(X.P, 'eligible', return_value=True):
        gates = X.pre_label_gates(bundle, spec, X.Counters())
    assert 'CORE_FAMILY_COVERAGE:2020' in gates['reasons']
    assert gates['counters'] == asdict(X.Counters())


def test_acquisition_failure_never_freezes_or_exchanges_permit(tmp_path, monkeypatch):
    monkeypatch.setattr(CLI, 'boundary', lambda root: {'permanentLockExists': False})
    monkeypatch.setattr(S, 'materialize_universe', lambda *args: ['000001.KS'])
    monkeypatch.setattr(S, 'required_dates', lambda spec: [DATE])
    def refusal(*args):
        raise S.Refused('HTTP 401 unauthorized synthetic-key')
    with patch.object(S, 'freeze_snapshot', side_effect=AssertionError('must not freeze')), S.outcome_firewall():
        report = CLI.collect_and_gate(tmp_path, key='synthetic-key', fetch=refusal, pace=0)
    assert report['status'] == 'DATA_INSUFFICIENT'
    assert report['acquisition']['status'] == 'AUTH_REQUIRED'
    assert 'synthetic-key' not in json.dumps(report)
    assert report['rawSnapshotSha256'] is None
    assert report['counters'] == asdict(X.Counters())
    assert not (tmp_path / S.MANIFEST).exists()


# --- transient network failure: SSL handshake timeout on the 596th request of the first real attempt -------------
SSL = 'URLError: <urlopen error _ssl.c:999: The handshake operation timed out>'
DATES = ['2020-01-03', '2020-01-06', '2020-01-07']


def dated(date):
    data = payload(); data['OutBlock_1'][0]['BAS_DD'] = date.replace('-', '')
    return data


def flaky(failures, seen):
    """Fail the SECOND date `failures` times with the exact observed SSL error, then serve."""
    def fetch(base, endpoint, params, key):
        day = params['basDd']; seen.append(day)
        if day == '20200106' and seen.count(day) <= failures:
            raise S.Refused(SSL)
        return dated(day[:4] + '-' + day[4:6] + '-' + day[6:])
    return fetch


def collect(root, fetch, **kw):
    waits = []
    report = S.collect_official(root, DATES, ['000001.KS'], key='synthetic-key', fetch=fetch, pace=0,
                                sleep=waits.append, **kw)
    return report, waits


def test_transient_ssl_failure_recovers_within_the_bounded_retry_budget(tmp_path):
    seen = []
    report, waits = collect(tmp_path, flaky(3, seen))
    assert report['status'] == 'SERVED' and report['complete'] and report['cache']['dates'] == 3
    assert waits == [2, 5, 15] and report['requestAttempts'] == 6
    assert [e['attempt'] for e in report['retryEvents']] == [1, 2, 3]
    assert all(e['date'] == '20200106' and e['error'] == SSL for e in report['retryEvents'])
    assert report['retryPolicy'] == {'attempts': 5, 'backoffSeconds': [2, 5, 15, 45], 'retried': 'NETWORK_ERROR_ONLY'}
    for day in DATES:
        S.verify_cached_day(tmp_path, day, ['000001.KS'])


def test_exhausted_retries_fail_closed_and_keep_the_cache_and_provenance(tmp_path):
    seen = []
    root = tmp_path / 'partial'
    report, waits = collect(root, flaky(99, seen))
    assert report['status'] == 'NETWORK_ERROR' and not report['complete']
    assert report['failedDate'] == '2020-01-06' and 'handshake operation timed out' in report['failure']
    assert report['failure'].endswith('[attempts=5]') and waits == [2, 5, 15, 45] and report['requestAttempts'] == 6
    assert report['missingDates'] == ['2020-01-06', '2020-01-07']
    held = (root / 'market/2020-01-03.json').read_bytes()
    prov = (root / 'sources/provenance/2020-01-03.json').read_bytes()
    S.verify_cached_day(root, '2020-01-03', ['000001.KS'])
    assert not (root / 'market/2020-01-06.json').exists() and not (root / 'sources/krx/2020-01-06.json.gz').exists()
    with pytest.raises(ValueError, match='CANNOT_FREEZE_INCOMPLETE'):
        S.freeze_snapshot(root, S.frozen_spec())
    # A later run resumes from the byte-verified first writes and never rewrites them.
    resumed, _ = collect(root, flaky(0, []))
    assert resumed['complete'] and resumed['calls'] == 2
    assert (root / 'market/2020-01-03.json').read_bytes() == held
    assert (root / 'sources/provenance/2020-01-03.json').read_bytes() == prov


@pytest.mark.parametrize('message,status', [('HTTP 401 unauthorized', 'AUTH_REQUIRED'), ('response was not JSON: x', 'SCHEMA_CHANGED'),
                                            ('HTTP 403: forbidden', 'BLOCKED_SOURCE')])
def test_only_network_errors_are_retried(tmp_path, message, status):
    calls = []
    def refuse(*args):
        calls.append(args); raise S.Refused(message)
    report, waits = collect(tmp_path, refuse)
    assert report['status'] == status and len(calls) == 1 and waits == [] and report['retryEvents'] == []


def test_retry_never_alters_source_values_or_leaks_the_key(tmp_path):
    report, _ = collect(tmp_path, flaky(2, []))
    assert 'synthetic-key' not in json.dumps(report)
    doc = json.loads((tmp_path / 'market/2020-01-06.json').read_text())
    assert doc['records'][0]['close'] == 100 and doc['records'][0]['marketCap'] == 100000000


def test_network_failure_run_touches_no_outcome_and_keeps_all_six_counters_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(CLI, 'boundary', lambda root: {'permanentLockExists': False})
    monkeypatch.setattr(S, 'materialize_universe', lambda *args: ['000001.KS'])
    monkeypatch.setattr(S, 'required_dates', lambda spec: DATES)
    monkeypatch.setattr(S.time, 'sleep', lambda s: None)
    with patch.object(S, 'freeze_snapshot', side_effect=AssertionError('must not freeze')), S.outcome_firewall():
        report = CLI.collect_and_gate(tmp_path, key='synthetic-key', fetch=flaky(99, []), pace=0)
    assert report['acquisition']['status'] == 'NETWORK_ERROR' and report['status'] == 'DATA_INSUFFICIENT'
    assert report['counters'] == asdict(X.Counters()) == {k: 0 for k in report['counters']}
    assert report['rawSnapshotSha256'] is None and not (tmp_path / S.MANIFEST).exists()
    assert not report.get('executionAuthorizationCreated') and not report.get('executionPermitIssued')
