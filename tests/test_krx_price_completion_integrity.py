"""Completion is a persisted source fact, never an empty-response assumption."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import collect_krx_daily_prices as C  # noqa: E402
from pipeline import historical_store as H  # noqa: E402

DAY = '2026-09-15'


def response(day=DAY, close='1000', volume='10'):
    return {'OutBlock_1': [{'ISU_CD': '005930', 'BAS_DD': day.replace('-', ''),
                           'TDD_CLSPRC': close, 'ACC_TRDVOL': volume}]}


def collect(path, payload, monkeypatch):
    monkeypatch.setattr(C, 'call', lambda *a, **k: payload)
    return C.collect(path, [DAY], auth_key='synthetic', base='unused', keep={'005930.KS'},
                     max_calls=1, max_minutes=1, pace=0, log=lambda *a: None)


def test_open_session_empty_response_never_becomes_closed_or_done(tmp_path, monkeypatch):
    result = collect(tmp_path, {'OutBlock_1': []}, monkeypatch)
    assert result['closed'] == [] and result['remaining'] == 1
    assert 'EXPECTED_SESSION' in result['stopped']
    assert C.load_done(tmp_path) == set()


def test_false_legacy_done_is_retried_and_actual_rows_are_required(tmp_path, monkeypatch):
    (tmp_path / C.DONE_NAME).write_text(json.dumps([DAY]))
    result = collect(tmp_path, response(), monkeypatch)
    assert result['calls'] == 1 and result['legacyDoneWithoutBars'] == [DAY]
    assert result['remaining'] == 0 and result['bars'] == 1
    rows = H.read_jsonl(tmp_path / 'krx-prices-2026.jsonl.gz')
    assert rows[0]['date'] == DAY and rows[0]['close'] == 1000
    receipt = json.loads((tmp_path / C.RECEIPTS_NAME).read_text())[DAY]
    assert receipt['keptRows'] == 1 and receipt['servedDate'] == DAY
    assert receipt['responseDigestBasis'] == 'CANONICAL_PARSED_JSON_NOT_ORIGINAL_HTTP_BYTES'


def test_failed_recovery_preserves_original_marker_but_reports_unresolved(tmp_path, monkeypatch):
    marker = tmp_path / C.DONE_NAME
    marker.write_text(json.dumps([DAY], indent=0) + '\n')
    before = marker.read_bytes()
    result = collect(tmp_path, {'OutBlock_1': []}, monkeypatch)
    assert marker.read_bytes() == before
    assert result['remaining'] == 1 and result['written'] == []


@pytest.mark.parametrize('day', ['2026-09-14', '2026-09-16'])
def test_stale_and_future_served_dates_are_both_rejected(tmp_path, monkeypatch, day):
    result = collect(tmp_path, response(day), monkeypatch)
    assert 'SESSION_MISMATCH' in result['stopped'] and result['written'] == []
    assert not C.load_done(tmp_path)


def test_missing_explicit_source_date_cannot_fall_back_to_request(tmp_path, monkeypatch):
    payload = response()
    del payload['OutBlock_1'][0]['BAS_DD']
    assert 'DATE_ABSENT' in collect(tmp_path, payload, monkeypatch)['stopped']
    assert not C.load_done(tmp_path)


@pytest.mark.parametrize('close', ['NaN', 'Infinity', '-1', '0'])
def test_invalid_prices_do_not_create_completion(tmp_path, monkeypatch, close):
    result = collect(tmp_path, response(close=close), monkeypatch)
    assert result['stopped'] and result['written'] == []
    assert not C.load_done(tmp_path)


def test_zero_volume_is_retained_as_halt_evidence_not_a_fake_trade(tmp_path, monkeypatch):
    result = collect(tmp_path, response(volume='0'), monkeypatch)
    assert result['bars'] == 1
    row = H.read_jsonl(tmp_path / 'krx-prices-2026.jsonl.gz')[0]
    assert row['volume'] == 0 and row['close'] == 1000


def test_universe_filter_cannot_turn_valid_source_into_false_completion(tmp_path, monkeypatch):
    payload = response()
    payload['OutBlock_1'][0]['ISU_CD'] = '999999'
    result = collect(tmp_path, payload, monkeypatch)
    assert 'EMPTY_FILTER' in result['stopped'] and result['remaining'] == 1


def test_atomic_replace_failure_preserves_prior_shard_and_marker(tmp_path, monkeypatch):
    prior = {'id': 'krx-price:2026-09-14:005930', 'date': '2026-09-14', 'region': 'KR',
             'ticker': '005930.KS', 'close': 900, 'volume': 10}
    shard = tmp_path / 'krx-prices-2026.jsonl.gz'
    H.write_shard(shard, [prior])
    C.save_done(tmp_path, {'2026-09-14'})
    before, marker = shard.read_bytes(), (tmp_path / C.DONE_NAME).read_bytes()
    monkeypatch.setattr(C.os, 'replace', lambda *a: (_ for _ in ()).throw(OSError('SYN_DISK_FULL')))
    with pytest.raises(OSError, match='DISK_FULL'):
        collect(tmp_path, response(), monkeypatch)
    assert shard.read_bytes() == before and (tmp_path / C.DONE_NAME).read_bytes() == marker


def test_existing_record_revision_is_refused_and_identical_retry_deduplicates():
    old = {'id': 'same', 'date': DAY, 'region': 'KR', 'ticker': '005930.KS', 'close': 1000}
    assert C._merged_rows([old], [dict(old)]) == [old]
    with pytest.raises(ValueError, match='EXISTING_PRICE_REVISION'):
        C._merged_rows([old], [{**old, 'close': 999}])


@pytest.mark.parametrize('bad', [
    {'ISU_CD': '000660', 'BAS_DD': '20260915', 'TDD_CLSPRC': '-', 'ACC_TRDVOL': '10'},
    {'ISU_CD': '005930', 'BAS_DD': '20260915', 'TDD_CLSPRC': '1001', 'ACC_TRDVOL': '10'},
])
def test_partially_invalid_or_duplicate_source_cannot_certify_completion(tmp_path, monkeypatch, bad):
    payload = response()
    payload['OutBlock_1'].append(bad)
    monkeypatch.setattr(C, 'call', lambda *a, **k: payload)
    result = C.collect(tmp_path, [DAY], auth_key='synthetic', base='unused',
                       keep={'005930.KS', '000660.KS'}, max_calls=1, max_minutes=1,
                       pace=0, log=lambda *a: None)
    assert 'DROPPED_OR_DUPLICATED' in result['stopped'] and not C.load_done(tmp_path)


def test_partial_success_does_not_hide_later_source_failure_from_scheduler(tmp_path, monkeypatch):
    monkeypatch.setenv('KRX_API_KEY', 'SYNTHETIC')
    monkeypatch.setattr(C, 'call', lambda base, endpoint, params, key:
                        response('2026-09-14') if params['basDd'] == '20260914' else {'OutBlock_1': []})
    assert C.main([str(tmp_path), '--all-issues', '--start', '2026-09-14',
                   '--end', '2026-09-15', '--pace', '0']) == 1
    assert C.load_done(tmp_path) == {'2026-09-14'}


def test_budgeted_partial_collection_remains_successfully_resumable(tmp_path, monkeypatch):
    monkeypatch.setenv('KRX_API_KEY', 'SYNTHETIC')
    monkeypatch.setattr(C, 'call', lambda *a, **k: response('2026-09-14'))
    assert C.main([str(tmp_path), '--all-issues', '--start', '2026-09-14',
                   '--end', '2026-09-15', '--max-calls', '1', '--pace', '0']) == 0
