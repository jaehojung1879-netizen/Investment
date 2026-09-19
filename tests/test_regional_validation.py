from copy import deepcopy
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

from pipeline import regional_rotation as RR
from pipeline import regional_validation as V
from pipeline import portfolio_validation as PV

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_regional_rotation_replay as RUNNER


def make_rows(region, seed=1, n=8):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range('2020-01-02',periods=n*21+1).strftime('%Y-%m-%d').tolist()
    rows = []
    for i in range(n):
        daily = dates[i*21:(i+1)*21+1]
        p = np.r_[1.,np.cumprod(1+rng.normal(.0008,.01,21))]
        b = np.r_[1.,np.cumprod(1+rng.normal(.0002,.007,21))]
        rf = np.r_[1.,np.cumprod(np.full(21,1.00008))]
        ticker = f'{region}{i%2}'
        rows.append(dict(date=daily[0],endDate=daily[-1],dailyDates=daily,
            dailyGrossNav=p.tolist(),dailyBenchmarkNav=b.tolist(),dailyRiskFreeNav=rf.tolist(),
            grossReturn=p[-1]-1,benchmarkReturn=b[-1]-1,grossExcessReturn=p[-1]-b[-1],
            weights={ticker:.7},regionByTicker={ticker:region},terminalWeights={ticker:.72},
            terminalRegionByTicker={ticker:region},top1=.7,top3=.7,effectiveNames=1))
    return rows


@pytest.fixture
def inputs():
    return {'US':make_rows('US'), 'KR':make_rows('KR',2)}


CFG = {'transactionCosts':{'US':{'commissionBps':3,'spreadBps':10},
                          'KR':{'commissionBps':5,'spreadBps':12,'sellTaxBps':20}}}


def test_static_uses_exact_same_regional_paths_and_preserves_daily_cash(inputs):
    original = deepcopy(inputs)
    rows = RR.static_blend(inputs)
    assert inputs == original
    for i,row in enumerate(rows):
        assert row['regionalWeights'] == {'US':.5,'KR':.5}
        assert sum(row['regionalWeights'].values()) == 1
        assert row['dailyGrossNav'] == pytest.approx((np.array(inputs['US'][i]['dailyGrossNav'])+inputs['KR'][i]['dailyGrossNav'])/2)
        assert row['cashWeight'] == pytest.approx(.3)
        assert sum(row['weights'].values()) == pytest.approx(.7)
        for region in inputs:
            source = inputs[region][i]
            ticker = next(iter(source['weights']))
            assert row['terminalWeights'][ticker] == pytest.approx(
                .5*(1+source['grossReturn'])/(1+row['grossReturn'])*source['terminalWeights'][ticker])
    inputs['US'][-1]['grossReturn'] = 100
    assert RR.static_blend(inputs)[:-1] == rows[:-1]


def test_future_outcomes_cannot_change_past_schedule_and_anchors(inputs):
    dates = [r['date'] for r in inputs['US']]
    before = RR.regional_weight_schedule(inputs,evaluation_dates=dates)
    for region in inputs:
        inputs[region][-1]['grossExcessReturn'] = 500
        inputs[region][-1]['endDate'] = '2099-12-31'
    assert RR.regional_weight_schedule(inputs,evaluation_dates=dates) == before
    inputs['US'].pop(3)
    after = RR.regional_weight_schedule(inputs,evaluation_dates=dates)
    assert [r['date'] for r in before] == [r['date'] for r in after]


def test_maturity_is_strict_and_lookback_is_calendar_days():
    rows = [dict(endDate='2020-04-01',grossExcessReturn=99),
            dict(endDate='2020-03-31',grossExcessReturn=.02),
            dict(endDate='2019-07-23',grossExcessReturn=88)]
    assert RR.trailing_mean_excess(rows,'2020-04-01',lookback_days=252) == .02


@pytest.mark.parametrize('temperature,floor',[(.05,.15),(.03,.1),(.1,.25)])
def test_dynamic_floor_raw_weights_and_determinism(inputs,temperature,floor):
    a = RR.regional_weight_schedule(inputs,temperature=temperature,floor=floor)
    assert a == RR.regional_weight_schedule(deepcopy(inputs),temperature=temperature,floor=floor)
    for r in a:
        assert sum(r['weights'].values()) == pytest.approx(1)
        assert min(r['weights'].values()) >= floor
        assert sum(r['rawWeights'].values()) == pytest.approx(1)
    assert RR.softmax_weights({'US':1000.,'KR':-1000.},temperature=temperature,floor=floor)['KR'] == floor


def test_missing_region_never_becomes_other_region(inputs):
    inputs['KR'].pop(2)
    rows = RR.static_blend(inputs)
    assert len(rows) == 7
    assert inputs['US'][2]['date'] not in [r['date'] for r in rows]


def test_exact_matching_no_imputation_or_shift(inputs):
    control = RR.static_blend(inputs)
    calendar = [dict(date=r['date'],endDate=r['endDate']) for r in control]
    challenger = deepcopy(control)
    challenger.pop(3)
    paths, report = V.matched_blocks({'a':control,'b':challenger},calendar)
    assert report['pairedBlocks'] == 7 and not report['complete']
    assert len(paths['a']) == len(paths['b']) == 7
    assert report['missingByPortfolio']['b'] == [calendar[3]]
    assert not V.metrics(paths['a'],CFG)['available']  # unknown interval cannot become flat cash
    challenger[0]['endDate'] = '2020-02-02'
    with pytest.raises(ValueError):
        V.matched_blocks({'a':control,'b':challenger},calendar)


@pytest.mark.parametrize('defect',['duplicate','missing','nan','reordered','endpoint'])
def test_invalid_daily_series_fail_closed(inputs,defect):
    rows = RR.static_blend(inputs)
    if defect=='duplicate':
        rows[0]['dailyDates'][1] = rows[0]['dailyDates'][0]
    elif defect=='missing':
        rows[0].pop('dailyRiskFreeNav')
    elif defect=='nan':
        rows[0]['dailyGrossNav'][1] = float('nan')
    elif defect=='reordered':
        rows[0]['dailyDates'][1:3] = reversed(rows[0]['dailyDates'][1:3])
    else:
        rows[0]['grossReturn'] = .8
    with pytest.raises(ValueError):
        V.metrics(rows,CFG)


def test_abc_use_shared_calculator_and_normal_sharpe_is_measured(inputs,monkeypatch):
    original = PV._path_metrics
    calls = []
    def spy(rows,*args,**kwargs):
        calls.append(len(rows))
        return original(rows,*args,**kwargs)
    monkeypatch.setattr(PV,'_path_metrics',spy)
    paths = [inputs['US'], RR.static_blend(inputs),RR.apply_schedule(inputs,RR.regional_weight_schedule(inputs))]
    for rows in paths:
        before = deepcopy(rows)
        result = V.metrics(rows,CFG)
        assert result['available'] and result['sharpe'] is not None
        assert result['metricVersion'] == 'calendar-span-daily-krw-rf-v1'
        assert rows == before
    assert calls == [8,8,8]


def test_undefined_sharpe_has_reason_and_never_zero(inputs):
    rows = inputs['US']
    for row in rows:
        row['dailyGrossNav'] = row['dailyRiskFreeNav'] = [1.]*22
        row['grossReturn'] = 0.
    m = V.metrics(rows,{})
    assert m['sharpe'] is None
    assert 'sharpe' in m['metricUnavailableReasons']


def test_bootstrap_numeric_calculator_matches_existing_daily_path_and_cost_events(inputs):
    rows = RR.static_blend(inputs)
    actual = V.metrics(rows,CFG)
    numeric = V._resampled_statistics(V._net_blocks(rows,CFG),np.arange(len(rows)))
    for key in V.METRICS:
        assert numeric[key] == pytest.approx(actual[key],abs=1e-5)


def test_paired_bootstrap_identity_seed_and_common_permutation(inputs):
    control = RR.static_blend(inputs)
    identical = V.paired_bootstrap(control,deepcopy(control),CFG,draws=40)
    for ci in identical['pathDifferenceCI'].values():
        assert ci['pointEstimate'] == 0
        assert ci['ci95'] == [0,0]
    dynamic = RR.apply_schedule(inputs,RR.regional_weight_schedule(inputs))
    a = V.paired_bootstrap(dynamic,control,CFG,draws=40,seed=11)
    assert a == V.paired_bootstrap(dynamic,control,CFG,draws=40,seed=11)
    assert a != V.paired_bootstrap(dynamic,control,CFG,draws=40,seed=12)
    assert a['pathDifferenceCI']['cagrPct']['pairedBlocks'] == len(control)
    with pytest.raises(ValueError,match='exact paired'):
        V.paired_bootstrap(dynamic[:-1],control,CFG,draws=40)


def test_ofat_cannot_select_or_mutate_baseline(inputs):
    control = RR.static_blend(inputs)
    calendar = [dict(date=r['date'],endDate=r['endDate']) for r in control]
    before = dict(V.BASELINE)
    report = V.build_validation(inputs,inputs['US'],calendar,CFG,draws=10)
    assert dict(V.BASELINE) == before
    assert report['freeze']['status'] == 'CHALLENGER'
    assert not report['freeze']['promotionEligible']
    assert len(report['robustness']) == 7
    for row in report['robustness'][1:]:
        assert sum(row['parameters'][k]!=before[k] for k in before) == 1
    with pytest.raises(TypeError):
        V.BASELINE['floor'] = .25
    assert set(report['comparisons']) == {r[0] for r in V.COMPARISONS}


def test_output_guard_and_sealed_hash(tmp_path):
    ledger = tmp_path/'ledger'
    ledger.mkdir()
    source = ledger/'sealed.json'
    source.write_text('{"sealed":true}')
    before = RUNNER.ledger_digest(ledger)
    with pytest.raises(ValueError):
        RUNNER.guard_output(source,ledger)
    alias = tmp_path/'alias'
    alias.symlink_to(ledger,target_is_directory=True)
    with pytest.raises(ValueError):
        RUNNER.guard_output(alias/'new.json',ledger)
    assert RUNNER.ledger_digest(ledger) == before
    source.write_text('{}')
    assert RUNNER.ledger_digest(ledger) != before


def test_runner_refuses_parameter_optimization_before_any_replay(tmp_path):
    with pytest.raises(ValueError,match='v1 is frozen'):
        RUNNER.main([str(tmp_path),'--temperature','.03'])


def test_runner_end_to_end_immutable_seal_and_identical_repeat(tmp_path,inputs,monkeypatch):
    from pipeline import replay_inputs as RI, provenance
    from pipeline.config import load_config
    cfg,_ = load_config()
    combined = RR.static_blend(inputs)
    calendar = [dict(date=r['date'],endDate=r['endDate']) for r in combined]
    ledger = tmp_path/'ledger'
    ledger.mkdir()
    manifest = dict(sha256='fixture-input-hash',through=combined[-1]['endDate'])
    sealed = dict(replayVersion=provenance.REPLAY_VERSION,inputSnapshot=manifest,
                  portfolioReplay=dict(headlineRows={PV.CHAMPION:combined},
                    selectors={PV.CHAMPION:dict(summary=V.metrics(combined,cfg.kelly_portfolio))}))
    (ledger/'historical-portfolio-validation.json').write_text(json.dumps(sealed))
    monkeypatch.setattr(RI.InputStore,'manifest',lambda self:manifest)
    monkeypatch.setattr(RUNNER,'_load_frozen',lambda _: (manifest,dict(
        prices={},fx=None,risk_free=[],risk_free_source={'verifiedThrough':manifest['through']},
        universe={'US':['U'],'KR':['K']})))
    monkeypatch.setattr(RUNNER,'_region_champion_rows',lambda region,*args,**kwargs:(inputs[region],{}))
    monkeypatch.setattr(RUNNER.RC,'schedule',lambda *args:calendar)
    before = RUNNER.ledger_digest(ledger)
    checkpoint = tmp_path/'paths.json.gz'
    for i in range(2):
        assert RUNNER.main([str(ledger),'--output',str(tmp_path/f'{i}.json'),
                            '--markdown',str(tmp_path/f'{i}.md'),
                            '--paths-output' if i==0 else '--paths-input',str(checkpoint)]) == 0
    assert (tmp_path/'0.json').read_bytes() == (tmp_path/'1.json').read_bytes()
    assert (tmp_path/'0.md').read_bytes() == (tmp_path/'1.md').read_bytes()
    assert RUNNER.ledger_digest(ledger) == before
    cached = json.loads(__import__('gzip').decompress(checkpoint.read_bytes()))
    cached['regional']['US'][0]['grossReturn'] = 77
    checkpoint.write_bytes(__import__('gzip').compress(json.dumps(cached).encode()))
    with pytest.raises(ValueError,match='checkpoint hash'):
        RUNNER.main([str(ledger),'--output',str(tmp_path/'bad.json'),
                    '--markdown',str(tmp_path/'bad.md'),'--paths-input',str(checkpoint)])
