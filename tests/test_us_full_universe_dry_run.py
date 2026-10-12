"""Invented fixtures only; source connectivity is established separately on Actions."""
import json
import pytest

from pipeline import us_daily_market_data as D
from pipeline import us_full_universe_dry_run as F
from tests.test_us_real_source_preflight import membership, fetch, NOW


def execute(tmp_path, provider=fetch, **kwargs):
    clock = [0.]
    def sleep(seconds):
        clock[0] += seconds
    return F.run(tmp_path, membership(), provider, now=NOW, monotonic=lambda: clock[0], sleep=sleep, **kwargs)


def test_full_observed_security_list_one_session_gate_and_pacing(tmp_path):
    calls = []
    def provider(ticker, start, through):
        calls.append((ticker,start,through))
        return fetch(ticker,start,through)
    result = execute(tmp_path, provider)
    assert [c[0] for c in calls] == ['QQQ','SPY','AAPL','BRK-B','JPM']
    assert all(c[1:] == ('2026-10-09','2026-10-09') for c in calls)
    assert result['verdict'] == 'PASS'
    assert result['expectedSecuritiesIncludingBenchmarks'] == result['collectedSecurities'] == 5
    assert result['elapsedSeconds'] == 4
    assert result['integrity']['repeatCount'] == 5
    assert result['integrity']['appendOnlyBytesUnchanged']
    assert result['shareClassSymbols'][0]['ticker'] == 'BRK-B'
    assert json.loads((tmp_path/'source-audit.json').read_text()) == result
    assert result['underlyingYahooHttpCalls'] is None


def test_rate_limit_stops_immediately_and_preserves_partial_manifest(tmp_path):
    calls = []
    def provider(ticker,start,through):
        calls.append(ticker)
        if ticker == 'BRK-B':
            raise D.Refused('YAHOO_PROVIDER_REFUSAL','HTTP 429 Too Many Requests')
        return fetch(ticker,start,through)
    result = execute(tmp_path, provider)
    assert calls == ['QQQ','SPY','AAPL','BRK-B']
    assert result['collectedSecurities'] == 3 and result['verdict'] == 'PARTIAL'
    assert result['stopReason'] == 'PROVIDER_RATE_LIMIT'
    assert result['failureCountsByRootCause'] == {'PROVIDER_RATE_LIMIT':1}
    assert result['collectionManifest']['status'] == 'INTERRUPTED'
    assert len(D.ObservationStore(tmp_path,D.SYNTHETIC).observations()) == 3


def test_benchmark_failure_blocks_all_members(tmp_path):
    calls = []
    def provider(ticker,*args):
        calls.append(ticker)
        raise D.Refused('YAHOO_PROVIDER_REFUSAL','CONNECT response 403')
    result = execute(tmp_path,provider)
    assert calls == ['QQQ','SPY']
    assert result['verdict'] == 'BLOCKED'
    assert result['failureCountsByRootCause'] == {'PROXY_CONNECT_403':2}


def test_incomplete_actions_and_currency_remain_missing_not_zero(tmp_path):
    def provider(ticker,start,through):
        reply = fetch(ticker,start,through)
        if ticker == 'AAPL':
            reply.frame.drop(columns=['Dividends'], inplace=True)
        if ticker == 'JPM':
            reply.metadata['currency'] = 'EUR'
        return reply
    result = execute(tmp_path,provider)
    assert result['verdict'] == 'PARTIAL'
    assert result['failureCountsByRootCause'] == {'INVALID_CURRENCY_UNIT':1,'MISSING_CORPORATE_ACTIONS':1}
    assert result['collectedSecurities'] == 3
    assert len(result['unresolvedActionIssues']) == 1


def test_call_and_time_budget_preserve_completed_rows(tmp_path):
    result = execute(tmp_path,max_calls=2)
    assert result['actualProviderAdapterCalls'] == 2
    assert result['collectedSecurities'] == 2
    assert result['verdict'] == 'PARTIAL'


def test_refuse_unpaced_expanded_or_occupied_stage_before_provider(tmp_path):
    with pytest.raises(ValueError):
        execute(tmp_path,pace=0)
    with pytest.raises(ValueError):
        execute(tmp_path,pace=float("nan"))
    with pytest.raises(ValueError):
        execute(tmp_path,max_calls=2.5)
    with pytest.raises(ValueError):
        execute(tmp_path,max_calls=1000)
    (tmp_path/'existing').write_text('untouched')
    with pytest.raises(D.Refused,match='fresh isolated'):
        execute(tmp_path)


def test_transport_counts_actual_requests_stops_429_and_restores(monkeypatch):
    from curl_cffi.requests import Session
    from types import SimpleNamespace
    def response(*args, **kwargs):
        return SimpleNamespace(status_code=429)
    monkeypatch.setattr(Session,'request',response)
    with F.provider_http_evidence() as events:
        with pytest.raises(F.TransportStop):
            Session.request(None,'GET','https://fixture.invalid')
    assert Session.request is response
    assert len(events) == 1 and events[0]['statusCode'] == 429
    assert 'url' not in events[0]


def test_manual_cli_import_has_no_provider_or_label_access(monkeypatch):
    import runpy
    def forbidden(*args,**kwargs):
        raise AssertionError('No source request on import')
    monkeypatch.setattr(F.S,'current_sp500',forbidden)
    monkeypatch.setattr(F.S,'yahoo_daily',forbidden)
    runpy.run_path('scripts/dry_run_us_full_universe.py',run_name='import_only')


def test_transport_stop_cannot_be_swallowed_by_vendor_exception_handler(tmp_path):
    calls = []
    def provider(ticker,start,through):
        calls.append(ticker)
        try:
            if ticker == 'AAPL':
                raise F.TransportStop('PROVIDER_RATE_LIMIT', 'HTTP 429')
            return fetch(ticker,start,through)
        except Exception:
            raise AssertionError('Vendor must not swallow controlled stop') from None
    result = execute(tmp_path,provider)
    assert calls == ['QQQ','SPY','AAPL']
    assert result['verdict'] == 'PARTIAL'
    assert result['stopReason'] == 'PROVIDER_RATE_LIMIT'
    assert result['collectedSecurities'] == 2


def test_final_workflow_has_no_diagnostic_hook_and_producer_evidence_is_pinned():
    from pathlib import Path
    import hashlib
    import subprocess
    root = Path(__file__).resolve().parents[1]
    workflow = (root/'.github/workflows/tests.yml').read_text()
    assert 'dry_run_us_full_universe.py' not in workflow
    assert 'us-full-universe-dry-run:' not in workflow
    evidence = json.loads((root/'docs/us-readiness/us-full-universe-real-dry-run-actions-evidence-v1.json').read_text())
    assert evidence['sourceAuditProjection']['collectedSecurities'] == 505
    assert evidence['sourceAuditProjection']['verdict'] == 'PASS'
    for path, sha in evidence['producerFileSha256'].items():
        original = subprocess.check_output(['git','show',evidence['producerHeadSha']+':'+path],cwd=root)
        assert hashlib.sha256(original).hexdigest() == sha
