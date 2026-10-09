"""Input amendment: invented quotes only; real corpus checks are hashes/metadata."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import subprocess

import numpy as np
import pandas as pd
import pytest

from pipeline import kr_alpha_atlas_phase_c_amendment as A
from pipeline import kr_alpha_atlas_price_integrity as P
from pipeline.kr_alpha_atlas_benchmark_audit import adjusted_index
from pipeline.kr_alpha_atlas_phase_c import contract, economics, labels, lifecycle, synthetic

ROOT=Path(__file__).resolve().parents[1]


def test_preserved_v1_and_exact_versioned_amendment():
    base=contract.load()
    effective=A.load()
    assert contract.file_hash(ROOT/contract.SPEC)==A.ORIGINAL_SHA
    assert base['benchmarkIntegrity']['claimGate']=='BLOCKED_UNVERIFIED'
    assert effective['benchmarkIntegrity']['claimGate']=='VERIFIED'
    allowed={'version','registrationAmendmentId','phaseBIdentity','primaryFrozenSnapshot',
             'benchmarkIntegrity','targets','lifecycle','inputIntegrityAmendment','dependencyHashes','sourceLimitations'}
    assert {k for k in effective if effective.get(k)!=base.get(k)}<=allowed
    for k in set(base)-allowed:
        assert effective[k]==base[k]
    assert effective['studyId']==base['studyId']
    assert effective['targets']['modelTarget']==base['targets']['modelTarget']
    assert effective['targets']['gross']==base['targets']['gross']
    assert effective['targets']['industryRelative']==base['targets']['industryRelative']
    assert effective['phaseBIdentity']['inputs']['originalPhaseBInputsSha256']==base['phaseBIdentity']['inputs']['sha256']
    assert effective['phaseBIdentity']['matrixDigest']!=base['phaseBIdentity']['matrixDigest']
    assert len(effective['eligibleFeatures'])==38
    assert sum(len(f['registeredHorizons']) for f in effective['eligibleFeatures'])==73
    assert contract.model_groups(effective)==contract.model_groups(base)
    assert effective['lifecycle']['lockPrefix']==base['lifecycle']['lockPrefix']==A.GLOBAL_LOCK
    assert effective['lifecycle']['artifactPrefix']==base['lifecycle']['artifactPrefix']
    assert effective['lifecycle']['resultPath']==base['lifecycle']['resultPath']


def test_real_reconciliation_evidence_metadata_only():
    # Does not calculate any real return in CI. The authorized benchmark-only
    # audit's already frozen evidence is validated as metadata and exact bytes.
    c=A.read_correction(ROOT)
    r=json.loads((ROOT/P.BENCHMARK_REPORT).read_text())
    assert [x['year'] for x in r['annualComparisons']]==list(range(2013,2027))
    assert len(r['distributions'])==46
    assert r['threshold']==0.005
    assert r['aggregateStatus']=='PASS'
    assert all(x['status']=='PASS' for x in r['annualComparisons'])
    assert c['benchmarkQuotes']==r['correctedBenchmarkQuotes']
    assert r['independentEndpoint']['vendorOwnQuote']==r['independentEndpoint']['officialRawQuote']
    assert all('stock' not in x['definition'].lower() for x in r['annualComparisons'])


def test_benchmark_reverse_cash_basis_then_shareholder_reinvestment_once():
    dates=['2020-01-02','2020-01-03','2020-01-06']
    raw=pd.Series([100.,99.,110.],index=dates)
    cash=[{'exDate':dates[1],'cashKrwPerUnit':10.}]
    vendor=adjusted_index(raw,cash)
    vendor=vendor*(raw.iloc[-1]/vendor.iloc[-1])
    reconstructed=P.raw_from_adjusted_benchmark(vendor,cash)
    assert reconstructed.to_numpy()==pytest.approx(raw.to_numpy())
    true=adjusted_index(reconstructed,cash,shareholder=True)
    assert true.iloc[1]==pytest.approx(1.09)
    assert true.iloc[1]!=pytest.approx(adjusted_index(raw,cash).iloc[1])
    with pytest.raises(ValueError,match='ONLY_REGISTERED'):
        P.raw_from_adjusted_benchmark(vendor,cash,ticker='006800.KS')
    vendor.iloc[1]=np.nan
    with pytest.raises(ValueError,match='INVALID_ADJUSTED'):
        P.raw_from_adjusted_benchmark(vendor,cash)


def test_same_session_source_scale_exposes_double_adjustment_without_stock_return():
    days=['2020-01-02','2020-01-03']
    raw={days[0]:{'close':100.},days[1]:{'close':90.}}
    vendor={days[0]:90.,days[1]:90.}
    internal={days[0]:{'Close':100.},days[1]:{'Close':100./.9}}
    r=P.quote_scale_reading(vendor,raw,internal,[{'date':days[1],'dividend':10.,'split':1.}],
                            {'start':days[0],'end':days[1]})
    action=r['corporateActionObservations'][0]
    assert action['cashAlreadyAdjusted']
    assert action['internalToKrxQuoteScaleChange']==pytest.approx(action['singleCashFactor']**2)
    assert r['stockHoldingReturnsCalculated']==0


def test_overlay_does_not_fabricate_last_price_or_zero_and_retains_population():
    base=contract.load()
    index=pd.to_datetime(['2026-09-10','2026-09-11','2026-09-14'])
    frame=pd.DataFrame({k:[10.,11.,12.] for k in ['Open','High','Low','Close','Volume']},index=index)
    inputs=SimpleNamespace(identity=deepcopy(base['phaseBIdentity']['inputs']),
                           prices={'006800.KS':frame.copy(),'SUSPENDED.KS':frame.copy(),'VERIFIED.KS':frame.copy()})
    correction={'basis':'INVENTED','benchmarkQuotes':[{'date':str(d.date()),'Close':1.} for d in index],
                'finalSourceSession':'2026-09-14','stockRules':[{'ticker':'006800.KS'}],
                'finalSessionQuotes':[{'ticker':'VERIFIED.KS','date':'2026-09-14',
                                      **{k:13. for k in ['Open','High','Low','Close','Volume']}}]}
    result=A.overlay(inputs,correction,'invented-correction')
    assert set(result.prices)=={'006800.KS','SUSPENDED.KS','VERIFIED.KS','069500.KS'}
    assert result.prices['006800.KS'].Close.isna().all()
    assert result.prices['006800.KS'].Volume.iloc[:2].notna().all()
    assert np.isnan(result.prices['006800.KS'].Volume.iloc[-1])
    assert np.isnan(result.prices['SUSPENDED.KS'].loc[index[-1],'Close'])
    assert result.prices['SUSPENDED.KS'].loc[index[0],'Close']==10.
    assert result.prices['VERIFIED.KS'].loc[index[-1],'Close']==13.
    assert result.identity['originalPhaseBInputsSha256']==base['phaseBIdentity']['inputs']['sha256']
    assert base['phaseBIdentity']['inputs']['sha256']!=result.identity['sha256']


def test_full_security_source_refusal_uses_same_synthetic_label_and_portfolio_engine():
    s=A.load()
    data=synthetic.market(end='2013-06-28',names=32)
    ticker='SYN000'
    data.closes[ticker][:]=np.nan
    counters=labels.Counters()
    book=labels.build_labels(data,21,s['developmentCutoff'],labels.synthetic_permit(data),counters)
    ids=book.table.index[book.table.ticker.eq(ticker)]
    assert book.table.loc[ids,'state'].eq('INVALID').all()
    assert book.table.loc[ids,'gross'].isna().all()
    first=ids[0]
    b=economics.block(data,book,data.rows.loc[first,'date'],{first:0.2},'CASH',s)
    assert b['status']=='BLOCKED'
    assert 'UNPRICEABLE' in b['reason']
    assert counters.realOutcomeReads==counters.realLabels==counters.realModelFits==0


def test_production_equivalent_preparation_injects_only_original_loader(monkeypatch):
    calls=[]
    result=SimpleNamespace(identity=contract.load()['phaseBIdentity']['inputs'])
    monkeypatch.setattr(A,'read_correction',lambda *_:{'basis':'INVENTED'})
    original=lambda *args:(calls.append(args) or result)
    monkeypatch.setattr(A.AI,'load_inputs',original)
    monkeypatch.setattr(A,'overlay',lambda inputs,*_:(calls.append('explicit-overlay') or inputs))
    with A.corrected_loader(ROOT):
        assert A.AI.load_inputs('exact-pin','fresh-work',ROOT) is result
    assert A.AI.load_inputs is original
    assert calls==[('exact-pin','fresh-work',ROOT),'explicit-overlay']


@pytest.mark.parametrize('failure',['source','checksum','matrix','runtime','dependency','memory','wall-time','synthetic','persistence'])
def test_amended_preparation_failure_never_claims_global_lock(failure):
    events=[]
    def prepare():
        events.append('prepare')
        raise RuntimeError(failure)
    with pytest.raises(RuntimeError,match=failure):
        lifecycle.ordered_once(checks=lambda:events.append('checks'),prepare=prepare,
                               claim=lambda:events.append(A.GLOBAL_LOCK),run=lambda *_:events.append('outcomes'),
                               on_failure=lambda *_:events.append('post-lock'))
    assert events==['checks','prepare']


@pytest.mark.parametrize('fail_after_claim',[False,True])
def test_two_versions_share_atomic_global_namespace_even_partial_claim(fail_after_claim):
    refs=set()
    claims=[]
    def claim():
        claims.append(A.GLOBAL_LOCK)
        if A.GLOBAL_LOCK in refs:
            raise RuntimeError('CONSUMED')
        refs.add(A.GLOBAL_LOCK)
        if fail_after_claim:
            raise RuntimeError('AMBIGUOUS_PARTIAL_CLAIM')
        return object()
    def run(*_):
        raise RuntimeError('PERSISTENCE_FAILURE')
    for _version in [1,2]:
        with pytest.raises(RuntimeError):
            lifecycle.ordered_once(checks=lambda:None,prepare=lambda:None,claim=claim,run=run,on_failure=lambda *_:None)
    assert refs=={A.GLOBAL_LOCK}
    assert claims==[A.GLOBAL_LOCK,A.GLOBAL_LOCK]


def test_exact_dependency_mutation_refused():
    original=contract.file_hash
    def changed(p):
        return '0'*64 if str(p).endswith('kr_alpha_atlas_price_integrity.py') else original(p)
    with patch.object(contract,'file_hash',changed):
        with pytest.raises(ValueError,match='AMENDED_DEPENDENCY_CHANGED'):
            A.load()


def test_correction_corpus_mutation_refused():
    original=contract.file_hash
    c=json.loads((ROOT/P.CORRECTION).read_text())
    target=next(iter(c['sourceHashes']))
    def changed(p):
        return '0'*64 if str(p).endswith(target) else original(p)
    with patch.object(contract,'file_hash',changed):
        with pytest.raises(ValueError,match='CORRECTED_SOURCE_IDENTITY_CHANGED'):
            A.read_correction(ROOT)


def test_new_manual_workflow_and_cli_do_not_enable_auto_execution():
    text=(ROOT/'.github/workflows/kr-alpha-atlas-phase-c-amended.yml').read_text()
    old=(ROOT/'.github/workflows/kr-alpha-atlas-phase-c.yml').read_text()
    assert 'workflow_dispatch:' in text
    assert 'pull_request:' not in text and 'schedule:' not in text and '\n  push:' not in text
    assert 'default: validate' in text
    group='group: kr-alpha-atlas-phase-c-v1-single-attempt'
    assert group in text and group in old
    assert 'kr-alpha-atlas-phase-c-v1-results-${{ github.run_id }}' in text
    assert 'kr-alpha-atlas-phase-c-v2-preflight-${{ github.run_id }}' in text
    s=A.load()
    assert not (ROOT/s['lifecycle']['authorizationPath']).exists()
    assert not (ROOT/contract.load()['lifecycle']['authorizationPath']).exists()


def test_amended_formal_refuses_missing_owner_authorization_before_prepare_or_claim(tmp_path,monkeypatch):
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip()
    events=[]
    github=SimpleNamespace(main=lambda:head,claim=lambda *_:events.append('lock'),
                           locks=lambda *_:[],previous_results=lambda *_:False)
    original=subprocess.check_output
    def clean(command,**kwargs):
        return b'' if command[:3]==['git','status','--porcelain'] else original(command,**kwargs)
    monkeypatch.setattr(subprocess,'check_output',clean)
    monkeypatch.setattr(A,'prepare',lambda *_:events.append('prepare'))
    with pytest.raises(ValueError,match='EXPLICIT_HUMAN_AMENDED_EXECUTION_AUTHORIZATION_ABSENT'):
        A.formal(work=tmp_path,github=github)
    assert events==[]


@pytest.mark.parametrize('report_only',[False,True])
def test_missing_source_coverage_cannot_be_turned_into_formal_readiness(monkeypatch,report_only):
    s=A.load()
    target='H08_equalVsCapWeightIndustry'
    features={f['featureId']:{'measuredStatus':'MEASURED_READY','coverageWithinUsableRangePct':90.} for f in s['eligibleFeatures']}
    features[target]={'measuredStatus':'MEASURED_BELOW_COVERAGE_FLOOR','coverageWithinUsableRangePct':59.}
    monkeypatch.setattr(A.RD,'build_features_report',lambda *_:features)
    monkeypatch.setattr(A.RD,'baseline_readiness',lambda *_:{'B4':{'status':'READY'}})
    monkeypatch.setattr(A.RD,'interaction_readiness',lambda *_:{'X4':{'status':'SOURCE_BLOCKED'}})
    if report_only:
        report=A.source_readiness(object(),s,require_ready=False)
        assert report['status']=='BLOCKED_PRE_OUTCOME'
        assert report['featuresBelowOriginalFloor']==[target]
        assert report['registeredRulesUnchanged']['minFeatureCoverage']==0.6
    else:
        with pytest.raises(ValueError,match='CORRECTED_INPUT_READY_FLOOR_BLOCKER: '+target):
            A.source_readiness(object(),s)
