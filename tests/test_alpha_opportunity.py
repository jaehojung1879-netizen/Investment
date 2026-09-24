"""Synthetic contracts only. Never read a real replay price/outcome or fit it."""
from __future__ import annotations

import ast
from copy import deepcopy
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from pipeline import alpha_opportunity_spec as S
from pipeline import alpha_opportunity_features as F
from pipeline import alpha_opportunity_model as M
from pipeline import alpha_opportunity_evaluation as E
from pipeline.alpha_opportunity_overlay import calendar_gate
from pipeline import replay_calendar as RC
from scripts import run_alpha_opportunity_model as CLI

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def spec():
    return S.read_json(S.DEFAULT_SPEC)


def synthetic(n_dates=220, names=12):
    rng = np.random.default_rng(42)
    dates = pd.date_range('2013-01-04', periods=n_dates, freq='W-FRI')
    x = rng.normal(size=n_dates*names)
    return pd.DataFrame({'date': np.repeat(dates.strftime('%Y-%m-%d'), names),
        'outcomeEndDate': np.repeat((dates+pd.Timedelta(days=31)).strftime('%Y-%m-%d'), names),
        'ticker': [f'SYNTHETIC_{i}' for _ in dates for i in range(names)],
        'region': 'US', 'x': x, 'forwardRelativeReturn': .01*x,
        'beatBenchmark': (x>0).astype(int), 'labelStatus': 'MATURED'})


def fixture_seal(tmp_path, spec):
    registry = S.read_json(ROOT/spec['featureRegistry'])
    (tmp_path/'features.json').write_bytes(S.canonical(registry))
    value = deepcopy(spec)
    value['featureRegistry'] = 'features.json'
    value['dependencyHashes'] = {'features.json': S.file_hash(tmp_path/'features.json')}
    p = tmp_path/'spec.json'
    p.write_bytes(S.canonical(value))
    h = S.digest(value)
    p.with_suffix('.sha256').write_text(h)
    return p, h


def test_canonical_unicode_order_and_hash():
    a, b = {'한글': [1, 2], 'b': 3}, {'b': 3, '한글': [1, 2]}
    assert S.canonical(a) == S.canonical(b)
    assert S.digest(a) == S.digest(b)
    assert not S.canonical(a).endswith(b'\n')
    assert '한글'.encode() in S.canonical(a)
    with pytest.raises(ValueError):
        S.canonical({'x': float('nan')})


def test_json_rejects_duplicates_and_nonfinite(tmp_path):
    p = tmp_path/'bad.json'
    for text in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}'):
        p.write_text(text)
        with pytest.raises(ValueError):
            S.read_json(p)


def test_real_seal_and_readiness(spec):
    seal = S.DEFAULT_SPEC.with_suffix('.sha256').read_text().strip()
    loaded, _ = S.load_sealed(expected_hash=seal)
    assert loaded == spec and seal == S.digest(spec)
    report = S.readiness(spec, seal)
    assert report['verdict'] == 'BLOCKED_PREREGISTRATION'
    assert not report['historicalModelsTrained'] and not report['historicalOutcomesComputed']
    assert S.read_json(ROOT/'docs/results/alpha-opportunity-model-v1-readiness.json') == report


def test_mutated_spec_external_hash_and_sidecar(tmp_path, spec):
    p, h = fixture_seal(tmp_path, spec)
    S.load_sealed(p, expected_hash=h, root=tmp_path)
    value = S.read_json(p); value['models']['ridge']['alpha'] = 11
    p.write_bytes(S.canonical(value))
    with pytest.raises(ValueError, match='SEALED_SPEC_CHANGED'):
        S.load_sealed(p, expected_hash=h, root=tmp_path)
    p.with_suffix('.sha256').write_text(S.digest(value))
    with pytest.raises(ValueError, match='SEALED_SPEC_CHANGED'):
        S.load_sealed(p, expected_hash=h, root=tmp_path)
    p.with_suffix('.sha256').unlink()
    with pytest.raises(ValueError, match='UNSEALED'):
        S.load_sealed(p, expected_hash=h, root=tmp_path)


def test_dependency_tampering(tmp_path, spec):
    p, h = fixture_seal(tmp_path, spec)
    (tmp_path/'features.json').write_text('{}')
    with pytest.raises(ValueError, match='DEPENDENCY_CHANGED'):
        S.load_sealed(p, expected_hash=h, root=tmp_path)


def test_execution_blocked_before_inputs(monkeypatch, spec, tmp_path):
    monkeypatch.setenv('GITHUB_REF', 'refs/heads/main')
    monkeypatch.setattr(CLI, 'execute', lambda *a: pytest.fail('must not train'))
    monkeypatch.setattr(CLI, 'verify_inputs', lambda *a: pytest.fail('must not read inputs'))
    with pytest.raises(ValueError, match='BLOCKED_PREREGISTRATION'):
        CLI.main(['--sealed-sha256', S.digest(spec), '--execute', '--reviewed',
                  '--input-root', str(tmp_path), '--output', str(tmp_path/'out')])
    assert not (tmp_path/'out').exists()


def test_review_branch_and_prerequisites(spec):
    for reviewed, branch in ((False,'refs/heads/main'),(True,'refs/heads/research/x')):
        with pytest.raises(ValueError, match='MERGE_AND_REVIEW'):
            S.require_execution(spec, reviewed=reviewed, branch=branch, prerequisites={'ok':True})
    clean = deepcopy(spec); clean['designBlockers'] = []
    clean['validatedCoverageArtifact'] = 'synthetic-contract'
    clean['snapshots']['advSnapshotSha256'] = 'synthetic-hash'
    for key in ('minimumEdge','concentrationRiskMultiple','tradeNotional','maximumAdvFraction','minimumAdv','slippageBps'):
        clean['investability'][key] = .01
    with pytest.raises(ValueError, match='PREREQUISITE'):
        S.require_execution(clean, reviewed=True, branch='refs/heads/main', prerequisites={'ok':False})


def test_cli_validation_only_deterministic(spec, capsys):
    assert CLI.main(['--sealed-sha256', S.digest(spec)]) == 0
    a = capsys.readouterr().out
    CLI.main(['--sealed-sha256', S.digest(spec)])
    assert capsys.readouterr().out == a
    assert json.loads(a)['historicalModelsTrained'] is False


def test_chronological_expanding_maturity_no_overlap(spec):
    data = synthetic()
    fs = list(M.folds(data, sorted(data.date.unique()), spec))
    assert len(fs) == 2 and all(f['status']=='READY' for f in fs)
    previous_size = 0
    for fold in fs:
        train, valid = fold['train'], fold['validation']
        assert train.date.max() < fold['cutoff'] <= valid.date.min()
        assert train.outcomeEndDate.max() < fold['cutoff']
        assert set(train.date).isdisjoint(valid.date)
        assert len(train) > previous_size
        previous_size = len(train)


def test_exact_cutoff_label_is_purged(spec):
    data = synthetic(); cutoff = '2016-01-01'
    data.loc[data.date.eq('2013-01-04'), 'outcomeEndDate'] = cutoff
    f = next(M.folds(data, sorted(data.date.unique()), spec))
    assert not f['train'].date.eq('2013-01-04').any()


def test_fold_schedule_not_moved_by_missing_labels(spec):
    data = synthetic()
    data.loc[data.date.ge('2016-01-01'), 'labelStatus'] = 'MISSING_FORWARD_PRICE_OR_DELISTING'
    f = next(M.folds(data, sorted(data.date.unique()), spec))
    assert f['cutoff'] == '2016-01-01' and len(f['validation']) > 0


def test_equal_date_weights():
    dates = ['a']*2 + ['b']*10
    w = M.date_weights(dates)
    assert w[:2].sum() == pytest.approx(1)
    assert w[2:].sum() == pytest.approx(1)
    assert w[0] == pytest.approx(5*w[-1])


def test_train_only_robust_transform_and_missing():
    train = pd.DataFrame({'x':[1.,2.,3.,np.nan], 'absent':[np.nan]*4})
    tr = M.TrainTransformer(['x','absent']).fit(train, np.ones(4))
    before = deepcopy((tr.center,tr.scale,tr.active))
    transformed = tr.transform(pd.DataFrame({'x':[1e9,np.nan], 'absent':[99,99]}))
    assert tr.omitted == ['absent'] and transformed.shape == (2,2)
    assert transformed[0,0] > 1e6 and transformed[1,0] == 0
    assert transformed[1,1] == 1
    assert tr.center == before[0] and tr.scale == before[1]


def test_signed_log_nonfinite_and_allmissing():
    t = M.TrainTransformer(['x'], ('x',))
    raw = t.raw(pd.DataFrame({'x':[-3,np.inf,None]}))
    assert raw[0,0] == pytest.approx(-np.log(4))
    assert np.isnan(raw[1:,0]).all()
    with pytest.raises(ValueError, match='ALL_FEATURES_MISSING'):
        t.fit(pd.DataFrame({'x':[None,np.inf]}), np.ones(2))


def test_registry_regions_horizons_and_coverage(spec):
    registry = S.read_json(ROOT/spec['featureRegistry'])
    assert len(spec['allowedFeatures']['US']['21']) == 6
    assert len(spec['allowedFeatures']['US']['126']) == 11
    assert len(spec['allowedFeatures']['KR']['126']) == 9
    assert 'shareCountChangePct' not in spec['allowedFeatures']['KR']['126']
    assert 'capexIntensityPct' not in spec['allowedFeatures']['KR']['126']
    for r in registry['features']:
        assert {'family','rawFields','transformation','pitAvailability','region','coverage','missingRule','allowedModels'} <= r.keys()
        assert 'ownership' not in r['name']
    frame = pd.DataFrame({'date':['2020-01-01']*2,'region':['US']*2,'relative126':[1,np.nan]})
    row = next(x for x in F.coverage(frame,registry) if x['feature']=='relative126')
    assert row['coverage']==.5 and row['universeRows']==2


def test_price_features_do_not_see_future_or_skip_sessions():
    days = RC.sessions('2020-01-01','2021-01-01','US')
    f = pd.DataFrame({'Close':100*np.exp(np.arange(len(days))*.001),'Volume':1000.},index=days)
    date = str(days[180].date())
    a = F.price_attention_at(f,f,date)
    f.loc[f.index>date,'Close'] = 1e9
    assert F.price_attention_at(f,f,date) == a
    f = f.drop(days[175])
    b = F.price_attention_at(f,f,date)
    assert np.isnan(b['vol63']) and np.isnan(b['logVolumeShock60'])


def test_targets_next_close_regional_holidays_missing_and_pending():
    days = RC.sessions('2020-07-01','2020-12-01','US')
    bench = pd.DataFrame({'Close':100.},index=days)
    stock = pd.DataFrame({'Close':100.+np.arange(len(days))},index=days)
    prices = {'SYNTHETIC':stock,'SPY':bench}
    label = F.target_at(prices,'US','SYNTHETIC','2020-07-02',21,'2020-12-01')
    assert label['entryDate']=='2020-07-06'  # July 3 holiday
    assert label['beatBenchmark']==1
    assert label['forwardRelativeReturn']==pytest.approx(stock.loc[label['outcomeEndDate'],'Close']/stock.loc['2020-07-06','Close']-1)
    assert F.target_at(prices,'US','SYNTHETIC','2020-07-02',126,'2020-08-01')['labelStatus']=='PENDING'
    prices['SYNTHETIC']=stock.drop(pd.Timestamp(label['outcomeEndDate']))
    missing = F.target_at(prices,'US','SYNTHETIC','2020-07-02',21,'2020-12-01')
    assert missing['forwardRelativeReturn'] is None and missing['labelStatus'].startswith('MISSING')


def test_receipt_date_not_transaction_reference_and_no_pre2024():
    days=RC.sessions('2024-01-01','2025-03-01','KR')
    event={'id':'synthetic','issuerId':'DART:SYNTHETIC','receiptNo':'20250203000001',
           'availableFrom':'2025-02-03','holdingPctChange':-2.,'transactionDate':'2020-01-01'}
    assert F.ownership_at([event],'DART:SYNTHETIC','2025-02-03',days)['ownershipCount21']==0
    after=F.ownership_at([event],'DART:SYNTHETIC','2025-02-04',days)
    assert after=={'ownershipCount21':1,'ownershipNetDirection21':-1}
    assert F.ownership_at([event],'DART:SYNTHETIC','2024-09-23',days)['ownershipCount21'] is None
    assert F.ownership_at([event],None,'2025-02-04',days)['ownershipCount21'] is None
    event['availableFrom']='2020-01-01'
    with pytest.raises(ValueError,match='PIT_INVALID'):
        F.ownership_at([event],'DART:SYNTHETIC','2025-02-04',days)


def test_ownership_missing_change_and_duplicate_receipts():
    days=RC.sessions('2024-01-01','2025-03-01','KR')
    event={'id':'synthetic','issuerId':'x','receiptNo':'20250203000001','availableFrom':'2025-02-03','holdingPctChange':None}
    result=F.ownership_at([event,event],'x','2025-02-04',days)
    assert result=={'ownershipCount21':1,'ownershipNetDirection21':None}


def test_filings_filtered_before_derive():
    rows=[{'id':'a','availableFrom':'2020-01-01','receiptNos':['20200101000001']},
          {'id':'b','availableFrom':'2020-01-02','receiptNos':['20200102000001']},
          {'id':'c','availableFrom':'2020-01-01','receiptNos':['20190101000001']}]
    assert [x['id'] for x in F.visible_filings(rows,'2020-01-02','KR')]==['a']
    assert F.visible_filings([{'id':'x'}],'2020-01-02','US')==[]


@pytest.mark.parametrize('family',['LINEAR','SHALLOW_CHALLENGER'])
def test_synthetic_heads_deterministic_and_region_separation(spec,family):
    data=synthetic(50)
    train=data.loc[data.date.lt('2013-09-01')]
    valid=data.loc[data.date.ge('2013-11-01')]
    a=M.fit_heads(train,valid,['x'],family,spec)
    b=M.fit_heads(train,valid,['x'],family,spec)
    assert np.isfinite(a['expectedRelativeReturn']).all()
    assert ((a['probability']>=0)&(a['probability']<=1)).all()
    np.testing.assert_array_equal(a['probability'],b['probability'])
    np.testing.assert_array_equal(a['expectedRelativeReturn'],b['expectedRelativeReturn'])
    bad=valid.copy();bad['region']='KR'
    with pytest.raises(ValueError,match='REGION_MISMATCH'):
        M.fit_heads(train,bad,['x'],family,spec)
    with pytest.raises(ValueError,match='LABEL_NOT_MATURE'):
        M.fit_heads(train,train,['x'],family,spec)


def test_fixed_challenger_params(spec):
    classifier, regressor=M.estimator_pair('SHALLOW_CHALLENGER',spec)
    for estimator in (classifier,regressor):
        for k,v in spec['models']['histGradientBoosting'].items():
            assert estimator.get_params()[k]==v
        assert estimator.max_leaf_nodes==7 and estimator.max_iter==100
        assert estimator.early_stopping is False
    with pytest.raises(ValueError):
        M.estimator_pair('SEARCH_WINNER',spec)


def test_block_sampling_deterministic():
    a=M.block_sample_indices(20,5,np.random.default_rng(42))
    b=M.block_sample_indices(20,5,np.random.default_rng(42))
    np.testing.assert_array_equal(a,b)
    assert (np.diff(a.reshape(-1,5),axis=1)==1).all()


def test_bootstrap_train_only_synthetic(spec):
    data=synthetic(120,2);train=data.loc[data.date.lt('2015-01-01')];valid=data.loc[data.date.ge('2015-03-01')]
    # Tiny synthetic test contract; frozen production hyperparameters untouched.
    cfg=deepcopy(spec);cfg['uncertainty'].update(replicates=3,blockDates=5,minimumTrainingBlocks=2)
    a=M.prediction_uncertainty(train,valid,['x'],cfg)
    b=M.prediction_uncertainty(train,valid,['x'],cfg)
    assert a['status']=='MEASURED'
    np.testing.assert_array_equal(a['meanLower'],b['meanLower'])
    assert (a['meanLower']<=a['meanUpper']).all()


def test_residuals_only_past_matured_oof():
    data=synthetic(30);data['expectedRelativeReturn']=0.
    scale=M.matured_residual_scale(data,'2014-01-01')
    data.loc[data.outcomeEndDate.ge('2013-06-01'),'forwardRelativeReturn']=999
    earlier=M.matured_residual_scale(data,'2013-06-01',minimum_dates=2)
    assert scale is not None and earlier <1
    assert M.matured_residual_scale(data,'2013-01-01') is None


def test_gate_zero_candidates_and_unknown(spec):
    assert M.opportunity_gate(1.,0.,.01,.1,1e6,spec)['passes'] is None
    cfg=deepcopy(spec)
    cfg['investability'].update(minimumEdge=.01,concentrationRiskMultiple=.1,tradeNotional=100.,maximumAdvFraction=.01,minimumAdv=1000.,slippageBps=1.)
    assert M.opportunity_gate(.005,.001,.002,.1,1e6,cfg)['passes'] is False
    assert M.opportunity_gate(.1,.09,.002,.1,1e6,cfg)['passes'] is True
    assert M.opportunity_gate(.1,.09,.002,.1,100.,cfg)['passes'] is False
    assert M.opportunity_gate(.1,np.nan,.002,.1,1e6,cfg)['passes'] is None


def test_dated_cost_schedule(spec):
    assert M.dated_round_trip_cost('US','2013-01-01',spec)==pytest.approx(.00163)
    assert M.dated_round_trip_cost('KR','2013-01-01',spec)==pytest.approx(.0041)
    assert M.dated_round_trip_cost('KR','2025-01-01',spec)==pytest.approx(.0026)


def test_verdict_priority_and_no_missing_row_survivor_selection(spec):
    f=synthetic(2);f['probability']=.5;f['expectedRelativeReturn']=0.
    f['trainingBaseRate']=.5;f['trainingMeanReturn']=0.
    f.loc[0,'labelStatus']='MISSING_FORWARD_PRICE_OR_DELISTING'
    daily=E.daily_metrics(f)
    assert daily.status.iloc[0]=='INCOMPLETE_DATE'
    assert E.verdict(daily,spec,pit_valid=True)['verdict']=='DATA_INSUFFICIENT'
    assert E.verdict(daily,spec,pit_valid=False)['verdict']=='PIT_INVALID'
    assert E.verdict(daily,spec,pit_valid=True,convergence_ok=False)['verdict']=='MODEL_UNSTABLE'
    assert E.block_interval([1,2],spec) is None


def test_all_verdicts_synthetic(spec):
    dates=pd.date_range('2016-01-01',periods=300,freq='W-FRI')
    daily=pd.DataFrame({'date':dates.strftime('%Y-%m-%d'),'status':'MEASURED',
        'rankIC':.1,'brierImprovement':.1,'logLossImprovement':.1,'mseImprovement':.1,'returnSlope':.1,'ece':.01})
    cfg=deepcopy(spec);cfg['inference']['replicates']=20
    assert E.verdict(daily,cfg,pit_valid=True,opportunity_evidence=True)['verdict']=='MODEL_EVIDENCE'
    assert E.verdict(daily,cfg,pit_valid=True,opportunity_evidence=False)['verdict']=='NO_MODEL_EVIDENCE'
    assert E.verdict(daily,cfg,pit_valid=True)['verdict']=='DATA_INSUFFICIENT'
    daily['rankIC']=-.1
    assert E.verdict(daily,cfg,pit_valid=True,opportunity_evidence=True)['verdict']=='NO_MODEL_EVIDENCE'


def test_zero_opportunities_valid_failure(spec):
    f=synthetic(2);f['gateStatus']='EVALUATED';f['passesOpportunity']=False
    result=E.selected_opportunity_evidence(f,spec)
    assert result['evidence'] is False and result['zeroOpportunityDates']==2
    assert all('netAdvantage' not in row for row in result['rows'])


def test_overlay_cannot_borrow_core_history(spec):
    result=calendar_gate(spec)
    assert result['verdict']=='DATA_INSUFFICIENT'
    assert result['weeklyDateUpperBound']==98 and result['evaluationDateUpperBound']==46
    assert result['promotionEligible'] is False and not result['historicalLabelsComputed']
    assert spec['ownershipOverlay']['horizon']==21


def test_no_production_imports_or_real_outcome_artifact():
    for path in (ROOT/'pipeline').glob('*.py'):
        if path.stem.startswith('alpha_opportunity_'):
            continue
        tree=ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node,(ast.Import,ast.ImportFrom)):
                names=[a.name for a in node.names]+[getattr(node,'module','') or '']
                assert not any('alpha_opportunity' in name for name in names), str(path)
    artifacts=list((ROOT/'docs/results').glob('alpha-opportunity-model-v1-*'))
    assert {p.name for p in artifacts}=={'alpha-opportunity-model-v1-input-audit.json','alpha-opportunity-model-v1-readiness.json'}
    for path in artifacts:
        artifact=S.read_json(path)
        assert artifact['historicalOutcomesComputed'] is False
        assert artifact['historicalModelsTrained'] is False
    workflow=(ROOT/'.github/workflows/alpha-opportunity-model-v1.yml').read_text()
    assert 'workflow_dispatch:' in workflow
    assert 'pull_request:' not in workflow and 'schedule:' not in workflow
    assert 'push:' not in workflow and 'contents: write' not in workflow


def test_result_schema_rejects_production_and_incomplete_outputs(spec):
    report={k:None for k in spec['expectedOutputSchema']['resultRequired']}
    report.update(specSha256=S.digest(spec),promotionEligible=False)
    S.validate_result(report,None,spec)
    report['positions']=[]
    with pytest.raises(ValueError,match='PORTFOLIO_OUTPUT'):
        S.validate_result(report,None,spec)
    with pytest.raises(ValueError,match='INCOMPLETE_RESULT'):
        S.validate_result({},None,spec)


def test_disagreement_and_candidate_churn_are_not_portfolio_returns():
    f=synthetic(2,2);f['probability']=.6;f['expectedRelativeReturn']=.01
    f['horizon']=21;f['family']='LINEAR';f['gateStatus']='EVALUATED'
    f['passesOpportunity']=[False,False,True,False]
    g=f.copy();g['family']='SHALLOW_CHALLENGER';g['expectedRelativeReturn']=-.01
    result=E.family_disagreement(pd.concat([f,g]))
    assert result['directionDisagreement']==1 and result['meanDifference']==pytest.approx(.02)
    churn=E.candidate_churn(f)
    assert churn[0]['count']==0 and churn[0]['exitFraction'] is None
    assert churn[1]['count']==1 and churn[1]['entrantFraction']==1


def test_raw_snapshot_hash_guard_rejects_mutation(tmp_path):
    (tmp_path/'raw.json').write_text('synthetic changed')
    with pytest.raises(ValueError,match='INPUT_SNAPSHOT_CHANGED'):
        CLI.verify_inputs({'inputFiles':{'raw.json':'0'*40}},tmp_path)
