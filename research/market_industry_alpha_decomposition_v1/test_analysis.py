"""Synthetic regressions and read-only committed-output checks, no replay."""
from copy import deepcopy
from datetime import date, timedelta
import importlib.util
import json
from pathlib import Path
import subprocess

import numpy as np
import pytest

SPEC=importlib.util.spec_from_file_location('market_industry_decomposition',Path(__file__).with_name('analyze.py'))
A=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(A)


def test_hac_zero_matches_independent_hc1_closed_form():
    x=np.linspace(-.1,.1,100)
    y=.002+.7*x+.01*np.sin(np.arange(100))
    fit=A.ols_hac(y,x,0)
    xc=x-x.mean();sxx=np.sum(xc**2)
    beta=np.sum(xc*(y-y.mean()))/sxx;alpha=y.mean()-beta*x.mean()
    u=y-alpha-beta*x
    var_beta=np.sum(xc**2*u**2)/sxx**2*100/98
    alpha_weights=1/100-x.mean()*xc/sxx
    var_alpha=np.sum(alpha_weights**2*u**2)*100/98
    assert fit['beta']==pytest.approx(beta)
    assert fit['betaSe']==pytest.approx(np.sqrt(var_beta))
    assert fit['rawWeeklyInterceptSeFraction']==pytest.approx(np.sqrt(var_alpha))


def test_serial_dependence_changes_interval_not_point_estimate():
    rng=np.random.default_rng(123)
    x=rng.normal(0,.03,500)
    u=np.zeros(500)
    for i in range(1,500):
        u[i]=.9*u[i-1]+rng.normal(0,.003)
    y=.001+.6*x+u
    hc=A.ols_hac(y,x,0);hac=A.ols_hac(y,x,26)
    assert hac['beta']==pytest.approx(hc['beta'])
    assert hac['rawWeeklyInterceptSeFraction']>2*hc['rawWeeklyInterceptSeFraction']
    assert 'NOT_SELECTION_ADJUSTED' in hac['inference']


@pytest.mark.parametrize('beta',[-.5,2.0])
def test_regression_beta_not_clipped_into_a_portfolio(beta):
    x=np.linspace(-.02,.03,100)
    fit=A.ols_hac(.001+beta*x,x,26)
    assert fit['beta']==pytest.approx(beta)
    assert fit['rawWeeklyInterceptFraction']==pytest.approx(.001)
    assert 'weights' not in fit and 'nav' not in fit


def test_invalid_missing_or_insufficient_returns_not_silently_deleted():
    assert A.ols_hac(np.ones(20),np.arange(20),26)['status']=='BLOCKED'
    assert A.ols_hac(np.ones(52),np.arange(52),52)['status']=='BLOCKED'
    assert A.ols_hac(np.arange(100),np.ones(100),26)['reason']=='BENCHMARK_VARIATION_UNAVAILABLE'
    x=np.arange(100,dtype=float);x[3]=np.nan
    with pytest.raises(ValueError,match='NO_ROW_DROPPING'):
        A.ols_hac(np.ones(100),x,26)


def test_capture_flat_and_unsupported_conditions_distinct_from_measured_zero():
    rows=[{'days':7,'rc':0,'re':.01,'logExcess':-.01},
          {'days':7,'rc':0,'re':0,'logExcess':0}]
    c=A.capture(rows)
    assert c['up']['capturePct']==0 and c['up']['n']==1
    assert c['down']['capturePct'] is None and c['down']['n']==0
    assert c['flat']['capturePct'] is None and c['flat']['n']==1
    assert c['down']['reason'] is not None


def test_statistical_mean_bridge_reconciles_without_claiming_a_funded_alpha():
    x=np.linspace(-.02,.03,104)
    y=.001+.6*x+.004*np.sin(np.arange(104))
    rows=[{'from':'2024-01-01','through':'2025-12-31','days':7,'rc':float(a),'re':float(b)} for a,b in zip(y,x)]
    fit=A.regression_summary(rows,26)
    b=fit['statisticalArithmeticActiveBridge']
    assert b['observedActiveAnnualPp']==pytest.approx(b['betaSlopeTermAnnualPp']+b['rawInterceptTermAnnualPp'])
    assert abs(b['meanResidualAnnualPp'])<1e-12
    assert 'NOT_CAUSAL_SELECTION' in b['identity']
    assert 'nav' not in fit and 'fundedReturn' not in fit


def synthetic_targets():
    rows=[]
    for i in range(155):
        y,m=2014+i//12,i%12+1
        start=date(y,m,15)
        end=date(y+int(m==12),m%12+1,15)
        rows.append({'signalDate':(start-timedelta(days=1)).isoformat(),'date':start.isoformat(),
            'endDate':end.isoformat(),'weights':{'SYN':.6},'sectorByTicker':{},
            'dailyGrossNav':'MUST_NOT_USE_LEGACY_C1_PATH','dailyBenchmarkNav':'MUST_NOT_READ'})
    return {'sha256':'synthetic','regional':{'KR':rows}}


def test_target_carry_in_coverage_and_unknown_etf_attribution():
    r=synthetic_targets();before=deepcopy(r)
    output=A.target_inventory(r,'synthetic')
    assert r==before
    for year,v in output['byYear'].items():
        assert v['overlappingBlocksIncludingCarryIn']==(12 if year=='2026' else 13)
        assert v['rows'][0]['clippedFrom']==year+'-01-01'
        assert v['rows'][0]['date']<year+'-01-01'  # The prior December holding is retained.
        assert v['calendarDayWeightedResidualEtfTargetPct']==pytest.approx(40)
        assert v['calendarDayWeightedNamedDirectTargetPct']==0
        assert v['directStockRecordedLabelWeightsPct_NOT_EFFECTIVE_SECTOR_EXPOSURE']['Unclassified']==pytest.approx(60)
    assert output['officialEtfDatedSectorWeights'] is None
    assert output['brinsonAttribution']['allocationPp'] is None
    assert 'NOT_KODEX200' in output['notOfficialEtfProxy']


def test_target_metadata_never_reads_legacy_valuation():
    class Poison(dict):
        def __getitem__(self,key):
            if key in {'dailyGrossNav','dailyBenchmarkNav','grossReturn','costAdjustedReturn'}:
                raise AssertionError('legacy path read')
            return super().__getitem__(key)
    r=synthetic_targets();r['regional']['KR']=[Poison(x) for x in r['regional']['KR']]
    assert A.target_inventory(r,'synthetic')['fullSourceBlocks']==155


def test_target_missing_identity_dates_weights_and_gaps_refused():
    for mutate in [lambda r:r.update(sha256='different'),
        lambda r:r['regional']['KR'][10].update(signalDate=r['regional']['KR'][10]['date']),
        lambda r:r['regional']['KR'][10].update(weights={'SYN':1.1}),
        lambda r:r['regional']['KR'][10].update(weights={'SYN':True}),
        lambda r:r['regional']['KR'][10].update(endDate='2014-11-14')]:
        r=synthetic_targets();mutate(r)
        with pytest.raises(ValueError):
            A.target_inventory(r,'synthetic')


def test_complete_saved_industry_bridge_reconciles_and_detects_missing_cost():
    saved={'books':{},'dMinusA':{'FULL':{'costNavUnitsA':.1,'costNavUnitsD':.2}}}
    for b,vec,gross,cost in [('A',{'ELECTRONICS_ELECTRICAL':.2,'OTHER':.3},.5,.1),
                            ('D',{'ELECTRONICS_ELECTRICAL':.8,'OTHER':.2},1,.2)]:
        saved['books'][b]={'industryContribution':{'FULL':{'byIndustry':vec}},
            'namedSecurities':{'bySpan':{'FULL':{'grossContributionNavUnitsOfBook':gross,'netChangeNavUnitsOfBook':gross-cost}}}}
    out=A.industry_bridge(saved)['FULL']
    assert out['deltaGrossNavUnits']==pytest.approx(.5)
    assert out['deltaCostNavUnits']==pytest.approx(.1)
    assert out['deltaNetNavUnits']==pytest.approx(.4)
    assert abs(out['reconciliationResidualNavUnits'])<1e-12
    assert out['electronicsShareOfGrossDifferencePct']==pytest.approx(120)
    assert out['costByIndustry'] is None and out['semiconductorOnlyContribution'] is None
    saved['dMinusA']['FULL']['costNavUnitsD']=.1
    with pytest.raises(ValueError,match='DOES_NOT_RECONCILE'):
        A.industry_bridge(saved)


def test_helper_identity_checked_before_execution(monkeypatch,tmp_path):
    def no_call(*args,**kwargs):
        raise AssertionError('unverified code read/executed')
    monkeypatch.setattr(subprocess,'check_output',no_call)
    with pytest.raises(ValueError,match='HELPER_IDENTITY'):
        A.read_sources(tmp_path,{'sources':[{'path':A.HELPER,'commit':'0'*40,'sha256':'0'*64}]})


def test_committed_actual_scope_and_evidence_classes():
    r=json.loads(Path(__file__).with_name('results.json').read_text())
    assert r['notFormalMarketC1C2'] and r['currency']=='KRW' and not r['fxReturnsIncluded']
    assert r['E2']['scopes']['FULL']['primaryHac26']['n']==714
    assert len(r['E2']['rolling104ObservedReturnsStep13'])==48
    assert r['E2']['fundedFixedExposureComparison']['status']=='BLOCKED'
    assert r['E1']['namedPairIndirectWeight'] is None
    assert r['E1']['recentUniqueBlocks']==31
    assert not r['promotionEligible'] and not r['productionChanges'] and r['sealedReexecutions']==0
    for v in r['E3']['integratedDBridge'].values():
        assert abs(v['reconciliationResidualNavUnits'])<1e-9
    assert len(r['literature']['papers'])==7
    assert all('w6493' not in p['readUrl'] for p in r['literature']['papers'])
