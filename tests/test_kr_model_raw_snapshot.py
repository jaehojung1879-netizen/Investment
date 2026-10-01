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


# --- post-acquisition: KeyError('date') on the static lineage components (run 36844599518) ---------------------
from pipeline import replay_inputs as RI  # noqa: E402


def real_shaped_world(tmp_path):
    """The shape the pinned replay-v16 manifest really has: dated panels PLUS one-row `price/source`/`benchmark/source`."""
    objects = {'p1': [{'ticker': '000001.KS', 'date': '2020-01-03', 'Close': 1., 'High': 1., 'Low': 1., 'Open': 1., 'Volume': 1}],
               'b1': [{'ticker': '069500.KS', 'date': '2020-01-03', 'Close': 1.}],
               'ps': [{'coverageShortfall': {}, 'crossCheck': {}, 'distributions': {}, 'region': 'KR', 'routes': [], 'source': 'S',
                       'vendor': 'V'}],
               'bs': [{'policy': 'P', 'region': 'KR', 'source': 'S', 'symbol': '^KS200', 'ticker': '069500.KS'}]}
    comps = {'price/2020-01': ['p1'], 'benchmark/2020-01': ['b1'], 'price/source': ['ps'], 'benchmark/source': ['bs']}
    manifest = {'dataVersion': 'd', 'components': comps}
    manifest['sha256'] = RI.digest({k: v for k, v in manifest.items() if k != 'sha256'})
    path = tmp_path / 'ledger/historical/replay-v16/inputs.json'
    path.parent.mkdir(parents=True); path.write_text(json.dumps(manifest))
    spec = {'inputs': {'accounting': {'gitBlobSha1': {}, 'contentSha256': X.K.content_sha256({})}, 'universeBlobs': {},
                       'replayManifestSha256': manifest['sha256']}}
    (tmp_path / 'market').mkdir()
    return spec, objects


def run_loader(tmp_path, spec, objects):
    with patch.object(RI.InputStore, '_read', lambda self, ref: objects[ref]), \
         patch.object(X.MV.MarketValueStore, 'load', lambda path: object()), patch.object(X.K, 'shard_files', lambda path: []):
        return X.load_sources(tmp_path, spec)


def test_the_sealed_loader_reads_the_static_lineage_as_price_rows_and_dies_with_the_observed_keyerror(tmp_path):
    spec, objects = real_shaped_world(tmp_path)
    # Not a hypothetical: this is the unchanged sealed loader on the manifest shape the real replay-v16 inputs have.
    # The static component is a single row with `ticker` ending .KS and no `date`; the dedup loop indexes row["date"].
    with pytest.raises(KeyError, match='date'):
        run_loader(tmp_path, spec, objects)


def test_dated_panels_only_applies_the_repository_predicate_and_loads_every_dated_panel(tmp_path):
    spec, objects = real_shaped_world(tmp_path)
    S.SKIPPED_STATIC_SOURCES.clear()
    with S.dated_panels_only():
        *_, prices = run_loader(tmp_path, spec, objects)
    assert sorted(prices) == ['000001.KS', '069500.KS']
    assert len(prices['000001.KS']) == 1 and len(prices['069500.KS']) == 1
    assert sorted(S.SKIPPED_STATIC_SOURCES) == sorted(RI.STATIC_SOURCES)
    assert RI.is_price_panel('price/2020-01') and not RI.is_price_panel('price/source') and not RI.is_price_panel('benchmark/source')


def test_the_adaptation_never_dates_defaults_or_drops_a_dated_row_and_still_rejects_conflicts(tmp_path):
    spec, objects = real_shaped_world(tmp_path)
    objects['p1'].append({'ticker': '000001.KS', 'date': '2020-01-03', 'Close': 2., 'High': 1., 'Low': 1., 'Open': 1., 'Volume': 1})
    with S.dated_panels_only(), pytest.raises(ValueError, match='CONFLICTING_REPLAY_PRICE_RECORD'):
        run_loader(tmp_path, spec, objects)
    objects['p1'].pop()
    del objects['p1'][0]['date']  # a DATED panel row without a date is still malformed evidence, not skipped
    with S.dated_panels_only(), pytest.raises(KeyError, match='date'):
        run_loader(tmp_path, spec, objects)


def completed(root, cache='c' * 64):
    X.atomic_write(root / 'acquisition.json', {'status': 'SERVED', 'complete': True, 'missingDates': [], 'requiredDates': 1,
                                               'cache': {'sha256': cache}})


def test_replay_never_contacts_the_source_and_only_accepts_the_completed_acquisition(tmp_path, monkeypatch):
    monkeypatch.setattr(CLI, 'boundary', lambda root: {'permanentLockExists': False})
    monkeypatch.setattr(S, 'materialize_universe', lambda *args: ['000001.KS'])
    monkeypatch.setattr(S, 'materialize_inherited', lambda *args: None)
    monkeypatch.setattr(S, 'required_dates', lambda spec: [DATE])
    monkeypatch.setattr(S, 'collect_official', lambda *a, **k: (_ for _ in ()).throw(AssertionError('must not collect')))
    monkeypatch.setattr('urllib.request.urlopen', lambda *a, **k: (_ for _ in ()).throw(AssertionError('network')))
    completed(tmp_path)
    frozen = {}
    def freeze(directory, spec):
        frozen['hit'] = True
        return {'sha256': 'a' * 64, 'inputIdentity': {'sha256': 'b' * 64}, 'components': {}}
    monkeypatch.setattr(S, 'freeze_snapshot', freeze)
    monkeypatch.setattr(S, 'gates_only', lambda directory, root=None: {'status': 'DATA_INSUFFICIENT', 'counters': asdict(X.Counters()),
                                                                       'gates': {'reasons': ['X']}})
    with S.outcome_firewall():
        report = CLI.collect_and_gate(tmp_path, key=None, fetch=CLI.no_network, replay=True, expected_cache_sha256='c' * 64)
    assert frozen['hit'] and report['acquisitionSource'].startswith('REPLAY_OF_PRESERVED_ARTIFACT')
    assert report['counters'] == asdict(X.Counters()) == {k: 0 for k in report['counters']}
    assert not report.get('executionAuthorizationCreated') and not report.get('executionPermitIssued')
    wrong = CLI.collect_and_gate(tmp_path, key=None, fetch=CLI.no_network, replay=True, expected_cache_sha256='d' * 64)
    assert wrong['status'] == 'INFRASTRUCTURE_ERROR' and 'NOT_THE_COMPLETED_ACQUISITION' in wrong['error']
    with pytest.raises(RuntimeError, match='FORBIDDEN_IN_REPLAY'):
        CLI.no_network()


def test_a_post_acquisition_crash_is_reported_as_infrastructure_error_not_an_uncaught_traceback(tmp_path, monkeypatch):
    monkeypatch.setattr(CLI, 'boundary', lambda root: {'permanentLockExists': False})
    monkeypatch.setattr(S, 'materialize_universe', lambda *args: ['000001.KS'])
    monkeypatch.setattr(S, 'materialize_inherited', lambda *args: None)
    monkeypatch.setattr(S, 'required_dates', lambda spec: [DATE])
    completed(tmp_path)
    monkeypatch.setattr(S, 'freeze_snapshot', lambda *a: {}['date'])
    report = CLI.collect_and_gate(tmp_path, key=None, fetch=CLI.no_network, replay=True)
    assert report['status'] == 'INFRASTRUCTURE_ERROR' and report['errorType'] == 'KeyError'
    assert report['counters'] == asdict(X.Counters()) and report['rawSnapshotSha256'] is None


def test_the_workflow_cannot_start_another_krx_acquisition():
    text = (S.X.ROOT / '.github/workflows/probes.yml').read_text()
    job = text[text.index('  kr-model-raw-replay:'):]
    assert 'kr-model-raw-readiness' not in text and 'KRX_API_KEY' not in job and '--mode replay' in job
    assert '--mode collect' not in text and 'run-id: 36844599518' in job and 'kr-model-raw-inputs-36844599518' in job
    assert '3419d9d201f942b3c89be146b8f696679c8105a5f00d8adb0dd2c5a655a80037' in job
