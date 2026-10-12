"""Invented multi-day fixtures are not operational real-source evidence."""
from dataclasses import replace
from datetime import timedelta
import hashlib
import json
from pathlib import Path

import pytest

from pipeline import us_persistent_daily_collection as C
from tests.test_us_real_source_preflight import membership, fetch, NOW

D = C.D


def response(at=NOW):
    return replace(membership(),observed_at=at)


def provider(ticker,start,through,at=NOW):
    return replace(fetch(ticker,start,through),observed_at=at)


def collect(root,source=None,fetcher=provider,now=NOW,**kwargs):
    clock=[0.]
    def sleep(seconds):
        clock[0]+=seconds
    return C.run(root,source or response(now),fetcher,now=now,monotonic=lambda:clock[0],sleep=sleep,**kwargs)


def test_persistent_idempotent_resume_and_partial_completion(tmp_path):
    first=collect(tmp_path,budget=C.Budget(max_calls=2))
    assert first['collectionComplete'] is False and first['actualAdapterAttempts']==2
    stored=D.ObservationStore(tmp_path,D.SYNTHETIC)
    before={p:p.read_bytes() for p in stored.prices.glob('*/observations-*.jsonl.gz')}
    calls=[]
    def tracked(ticker,*args):
        calls.append(ticker)
        return provider(ticker,*args)
    second=collect(tmp_path,fetcher=tracked)
    assert second['collectionComplete'] and calls==['AAPL','BRK-B','JPM']
    assert all(p.read_bytes()==b for p,b in before.items())
    calls.clear()
    third=collect(tmp_path,fetcher=tracked)
    assert third['collectionComplete'] and not calls and third['actualAdapterAttempts']==0
    assert len(stored.observations())==5
    assert len(list(C.Control(stored).path.glob('completions/*.json')))==1
    C.Control(stored).verify()


def test_two_synthetic_days_retain_sources_actions_and_membership_vintages(tmp_path):
    collect(tmp_path)
    later='2026-10-13T06:00:00Z'
    def next_day(ticker,start,through):
        r=provider(ticker,start,through,at=later)
        if ticker=='AAPL':
            r.frame['Dividends']=1.
        return r
    result=collect(tmp_path,now=later,fetcher=next_day)
    store=D.ObservationStore(tmp_path,D.SYNTHETIC)
    assert result['collectionComplete']
    assert len(store.snapshots())==2 and len(store.observations())==10
    assert store.snapshot_at(NOW)['observedAt']==D.stamp(NOW)
    assert all(not m['pitCompleteHistoricalUniverse'] for m in store.manifests())
    assert any(r['core']['cashDividendAsTraded']==1 for r in store.observations().values())


def test_changed_provider_observation_is_quarantined_without_hindsight(tmp_path):
    collect(tmp_path)
    store=D.ObservationStore(tmp_path,D.SYNTHETIC)
    first=store.prices_at(NOW)
    before={p:p.read_bytes() for p in store.prices.glob('*/observations-*.jsonl.gz')}
    later='2026-10-12T06:10:00Z'
    def revised(ticker,start,through):
        r=provider(ticker,start,through,at=later)
        if ticker=='AAPL':
            r.frame['Close']=100.5
        return r
    result=collect(tmp_path,now=later,fetcher=revised,recheck=True)
    assert not result['collectionComplete'] and result['status']=='REVISION_CONFLICT'
    assert all(p.read_bytes()==b for p,b in before.items())
    assert store.prices_at(NOW)==first
    assert any(r['status']=='REVISION_CONFLICT' for r in store.prices_at(later).values())
    assert len(list(C.Control(store).path.glob('completions/*.json')))==1


def test_bounded_transient_retry_and_no_retry_on_rate_limit(tmp_path):
    counts={}
    def transient(ticker,start,through):
        counts[ticker]=counts.get(ticker,0)+1
        if ticker=='AAPL' and counts[ticker]==1:
            raise D.Refused('TRANSPORT','timed out',C.CO.NETWORK_ERROR)
        return provider(ticker,start,through)
    result=collect(tmp_path,fetcher=transient)
    assert result['collectionComplete'] and result['actualAdapterAttempts']==6 and result['retryAttempts']==1
    limited=tmp_path/'limited'
    calls=[]
    def rate(ticker,*args):
        calls.append(ticker)
        if ticker=='AAPL':
            raise C.F.TransportStop('PROVIDER_RATE_LIMIT','HTTP 429')
        return provider(ticker,*args)
    partial=collect(limited,fetcher=rate)
    assert calls==['QQQ','SPY','AAPL'] and partial['stopReason']=='PROVIDER_RATE_LIMIT'
    assert partial['verifiedRecordCount']==2 and partial['retryAttempts']==0


def test_unexpected_interruption_preserves_prices_manifest_and_receipt(tmp_path):
    def interrupted(ticker,*args):
        if ticker=='AAPL':
            raise KeyboardInterrupt()
        return provider(ticker,*args)
    with pytest.raises(KeyboardInterrupt):
        collect(tmp_path,fetcher=interrupted)
    store=D.ObservationStore(tmp_path,D.SYNTHETIC)
    controls=C.Control(store).verify()
    assert len(store.observations())==2
    assert any(r.get('status')=='INTERRUPTED' for r in controls)
    assert not list(C.Control(store).path.glob('completions/*.json'))
    assert collect(tmp_path)['collectionComplete']


def test_corrupt_manifest_and_deleted_attempt_prevent_more_fetches(tmp_path):
    collect(tmp_path)
    store=D.ObservationStore(tmp_path,D.SYNTHETIC)
    attempt=next(C.Control(store).path.glob('attempts/*.json'))
    attempt.unlink()
    def forbidden(*args):
        raise AssertionError('Corruption must stop before acquisition')
    with pytest.raises(D.Refused,match='attempt receipt is missing'):
        collect(tmp_path,fetcher=forbidden)
    other=tmp_path/'other'
    collect(other)
    m=next(D.ObservationStore(other,D.SYNTHETIC).prices.glob('manifests/*.jsonl.gz'))
    m.write_bytes(b'corrupt')
    with pytest.raises(D.Refused,match='Corrupt chunk'):
        collect(other,fetcher=forbidden)


def test_identity_change_remains_blocked_across_resume(tmp_path):
    collect(tmp_path)
    later='2026-10-12T06:10:00Z'
    changed=replace(response(later),raw=membership().raw.replace(b'AAPL,Fixture tech,100',b'AAPL,Fixture tech,999'))
    r=collect(tmp_path,source=changed,now=later,fetcher=lambda t,s,e:provider(t,s,e,at=later))
    assert not r['collectionComplete'] and r['status']=='IDENTITY_BLOCKED'
    assert any(x['code']=='TICKER_REUSED_DIFFERENT_CIK' for x in D.ObservationStore(tmp_path,D.SYNTHETIC).manifests()[-1]['identityIssues'])


def approval_file(tmp_path,request,**changes):
    value={'schema':'US_DAILY_MANUAL_APPROVAL_V1','approved':True,'approvedBy':'fixture-owner','scope':C.SCOPE,
           'storageRoot':request['storageRoot'],'codeDigest':request['codeDigest'],'budgets':request['budgets'],
           'sourceKind':D.LIVE,'allowRedistribution':False,'allowSchedule':False,'allowRecheck':True,
           'grantedAt':NOW,'expiresAt':'2026-10-20T06:00:00Z','firstSession':'2026-10-09','lastSession':'2026-10-19',
           'usageReview':{'recurringAcquisitionPermitted':True,'persistentStoragePermitted':True,
                          'reviewedBy':'fixture-reviewer','evidenceReferences':['SYNTHETIC_APPROVAL_ONLY']}}
    value.update(changes)
    path=tmp_path/'fixture-approval.json'
    path.write_text(json.dumps(value))
    return path,hashlib.sha256(path.read_bytes()).hexdigest()


def test_owner_gate_exact_hash_scope_expiry_and_unresolved_terms(tmp_path):
    request=C.plan(tmp_path/'store',now=NOW)
    file,sha=approval_file(tmp_path,request)
    assert C.authorize(file,sha,request,now=NOW)==sha
    for change in [{'approved':False},{'storageRoot':'/other'}, {'codeDigest':'wrong'},
                   {'allowSchedule':True}, {'expiresAt':NOW},
                   {'usageReview':{'recurringAcquisitionPermitted':False}}]:
        file,sha=approval_file(tmp_path,request,**change)
        with pytest.raises(D.Refused):
            C.authorize(file,sha,request,now=NOW)
    with pytest.raises(D.Refused,match='exact hash'):
        C.authorize(file,'bad',request,now=NOW)


def test_cli_default_and_missing_approval_have_no_network(monkeypatch,tmp_path):
    from scripts import collect_us_daily_persistent as CLI
    def forbidden(*args):
        raise AssertionError('Network not authorized')
    monkeypatch.setattr(C.S,'current_sp500',forbidden)
    assert CLI.main([str(tmp_path/'store')])==0
    assert not (tmp_path/'store').exists()
    with pytest.raises(D.Refused,match='No real request'):
        CLI.main([str(tmp_path/'store'),'--mode','collect'])
    with pytest.raises(D.Refused,match='owner-gated'):
        C.run(tmp_path,replace(response(),source_kind=D.LIVE),forbidden,now=NOW,approval_digest='fake')


def test_symlink_escape_and_checkout_destinations_rejected_before_provider(tmp_path):
    path=tmp_path/'collection-control'/(C.VERSION+'-fixtures')
    path.parent.mkdir()
    outside=tmp_path.parent/(tmp_path.name+'-outside')
    outside.mkdir()
    path.symlink_to(outside,target_is_directory=True)
    with pytest.raises(D.Refused,match='symlink escape'):
        collect(tmp_path)
    with pytest.raises(D.Refused):
        C.plan(Path(__file__).resolve().parents[1]/'stage',now=NOW)


def test_limits_prospective_window_and_closed_workflow_scope(tmp_path):
    for b in [C.Budget(max_calls=10000),C.Budget(pace_seconds=0),C.Budget(retries_per_symbol=2)]:
        with pytest.raises(D.Refused):
            collect(tmp_path,budget=b)
    with pytest.raises(D.Refused):
        C.plan(tmp_path,now=NOW,session=(D.utc(NOW)-timedelta(days=30)).date().isoformat())
    root=Path(__file__).resolve().parents[1]
    for workflow in (root/'.github/workflows').glob('*.*'):
        assert 'collect_us_daily_persistent.py' not in workflow.read_text()


def test_rate_cooldown_survives_process_resume(tmp_path):
    def rate(*args):
        raise C.F.TransportStop('PROVIDER_RATE_LIMIT','HTTP 429')
    partial=collect(tmp_path,fetcher=rate)
    assert partial['cooldownUntil']
    with pytest.raises(D.Refused,match='15 minutes'):
        collect(tmp_path)
    later='2026-10-12T06:20:00Z'
    assert collect(tmp_path,now=later,fetcher=lambda t,s,e:provider(t,s,e,at=later))['collectionComplete']


def test_membership_failure_and_provider_transport_audits_are_immutable(tmp_path):
    request=C.plan(tmp_path,now=NOW)
    error=D.Refused('MEMBERSHIP_HTTP_REFUSAL','HTTP 429')
    failure=C.record_source_failure(tmp_path,error,request,'SYNTHETIC_APPROVAL_HASH',now=NOW,source_kind=D.SYNTHETIC)
    assert not failure['collectionComplete'] and failure['expectedRecordCount'] is None
    with pytest.raises(D.Refused,match='15 minutes'):
        C.inspect(tmp_path,now=NOW,source_kind=D.SYNTHETIC)
    transport=C.record_transport(tmp_path,[{'method':'GET','statusCode':429}],request,'SYNTHETIC_APPROVAL_HASH',source_kind=D.SYNTHETIC)
    assert transport['providerHttpCalls']==1
    assert len(C.Control(D.ObservationStore(tmp_path,D.SYNTHETIC)).verify())==2


def test_malformed_control_json_blocks_resume(tmp_path):
    collect(tmp_path)
    store=D.ObservationStore(tmp_path,D.SYNTHETIC)
    attempt=next(C.Control(store).path.glob('attempts/*.json'))
    attempt.write_text('{broken')
    with pytest.raises(D.Refused,match='Receipt hash'):
        collect(tmp_path)


def test_retry_attempts_share_the_global_call_budget(tmp_path):
    calls=[]
    def timeout(ticker,*args):
        calls.append(ticker)
        raise D.Refused('TRANSPORT','timed out',C.CO.NETWORK_ERROR)
    result=collect(tmp_path,fetcher=timeout,budget=C.Budget(max_calls=2))
    assert calls==['QQQ','QQQ']
    assert result['actualAdapterAttempts']==2 and result['stopReason']=='CALL_BUDGET'
    assert not result['collectionComplete']


def test_concurrent_store_owner_blocks_before_acquisition(tmp_path):
    store=D.ObservationStore(tmp_path,D.SYNTHETIC)
    def forbidden(*args):
        raise AssertionError('Another writer owns the store')
    with store.locked(),pytest.raises(D.Refused,match='Another collection'):
        collect(tmp_path,fetcher=forbidden)


def test_manifest_write_failure_resumes_without_refetch_or_false_completion(monkeypatch,tmp_path):
    with monkeypatch.context() as scoped:
        def failed(*args):
            raise OSError('SYNTHETIC manifest publication failure')
        scoped.setattr(D.ObservationStore,'save_manifest',failed)
        with pytest.raises(OSError,match='publication failure'):
            collect(tmp_path)
    store=D.ObservationStore(tmp_path,D.SYNTHETIC)
    assert len(store.observations())==5 and not store.manifests()
    assert not list(C.Control(store).path.glob('completions/*.json'))
    def forbidden(*args):
        raise AssertionError('Existing immutable price should be reused')
    recovered=collect(tmp_path,fetcher=forbidden)
    assert recovered['collectionComplete'] and recovered['actualAdapterAttempts']==0
    assert len(store.observations())==5
