import json, subprocess, sys
import numpy as np
import pandas as pd

from pipeline.features import add_targets, build_features, feature_columns
from pipeline.model import PROB_CLIP, current_signal, shrink_probability, walk_forward
from pipeline.config import ModelConfig
from pipeline.quality import evaluate_oos, recommendations_blocked
from pipeline.backtest import long_flat_next_open
from pipeline.build import _dumps
from pipeline.trade import MAX_POSITION_WEIGHT, build_idea, rank_ideas, suggested_weight


def price(n=80):
    idx=pd.bdate_range('2024-01-01', periods=n)
    close=pd.Series(np.arange(1,n+1,dtype=float), index=idx)
    return pd.DataFrame({'Open':close,'High':close+1,'Low':close-1,'Close':close,'Volume':1000}, index=idx)

def test_targets_last_h_nan_and_forward_sign():
    df=add_targets(price(40), [5,10,21])
    for h in [5,10,21]:
        assert df[f'forward_return_{h}d'].tail(h).isna().all()
        assert df[f'target_{h}d'].tail(h).isna().all()
        assert df[f'target_{h}d'].iloc[-h-1] == 1.0

def test_current_signal_latest_targetless_row(monkeypatch):
    import pipeline.model as M
    class Dummy:
        def fit(self,*a,**k): return self
        def predict_proba(self,X): return np.column_stack([np.full(len(X),.4),np.full(len(X),.6)])
    monkeypatch.setattr(M, '_new_model', lambda: Dummy())
    monkeypatch.setattr(M, '_calibrated_proba', lambda model, cal_X, cal_y, target_X: np.full(len(target_X), .6))
    df=price(620); df['Close']=100+np.sin(np.arange(620)/5)*10+np.arange(620)*0.01; df['Open']=df['Close']; df['High']=df['Close']+1; df['Low']=df['Close']-1
    feat=add_targets(build_features(df), [21]); cols=feature_columns(feat)
    sig=current_signal(feat, cols, 'target_21d', ModelConfig(min_train_days=50, calibration_window=30))
    assert sig and sig['asOf'] == feat.dropna(subset=cols).index[-1].strftime('%Y-%m-%d')

def test_walk_forward_purged_boundaries(monkeypatch):
    import pipeline.model as M
    class Dummy:
        def fit(self,*a,**k): return self
        def predict_proba(self,X): return np.column_stack([np.full(len(X),.4),np.full(len(X),.6)])
    monkeypatch.setattr(M, '_new_model', lambda: Dummy())
    monkeypatch.setattr(M, '_calibrated_proba', lambda model, cal_X, cal_y, target_X: np.full(len(target_X), .6))
    feat=add_targets(build_features(price(700)), [21]); cols=feature_columns(feat)
    res=walk_forward(feat, cols, 'target_21d', ModelConfig(min_train_days=60, calibration_window=30, step_size=20, oos_start='2024-01-01'), '2024-01-01', 21)
    assert not res.empty
    r=res.iloc[0]
    assert pd.Timestamp(r.foldTrainEnd) < pd.Timestamp(r.foldCalibrationStart)
    assert pd.Timestamp(r.foldCalibrationEnd) < pd.Timestamp(r.foldTestStart)

def test_quality_rejects_negative_bss_and_low_signal_count():
    res=pd.DataFrame({'actual':[0,1]*130, 'prob_cal':[.9,.1]*130})
    q=evaluate_oos(res, threshold=.95)
    assert not q['eligible']
    assert 'signal_observations_below_20' in q['eligibilityReasons']
    q2=evaluate_oos(res, threshold=.5)
    assert not q2['eligible'] and q2['brierSkillScore'] < 0

def test_quality_grade_ladder():
    rng=np.random.default_rng(0)
    # A skilled, calibrated signal: prob ~ true probability of the outcome.
    p=rng.uniform(.35,.75,600); y=(rng.uniform(0,1,600) < p).astype(int)
    q=evaluate_oos(pd.DataFrame({'actual':y,'prob_cal':p}), threshold=.55)
    assert q['eligible'] and q['qualityGrade'] in ('A','B')
    # A coin-flip signal must never be eligible.
    q2=evaluate_oos(pd.DataFrame({'actual':rng.integers(0,2,600),'prob_cal':rng.uniform(.4,.6,600)}), threshold=.55)
    assert q2['qualityGrade'] == 'REJECT' or q2['lift'] <= 5

def test_probability_shrinkage_and_clip():
    # A saturated calibrator output (1.0) must come back inside honest bounds.
    assert shrink_probability(1.0, .55, 25.2) <= PROB_CLIP[1]
    assert shrink_probability(0.0, .55, 25.2) >= PROB_CLIP[0]
    # Shrinkage pulls toward the base rate, harder with less evidence.
    weak=float(shrink_probability(.9, .5, 5)); strong=float(shrink_probability(.9, .5, 500))
    assert weak < strong <= .9
    # Published probabilities can never claim certainty.
    assert PROB_CLIP[1] < 1.0 and PROB_CLIP[0] > 0.0

def test_block_reasons_seed_stale_zero_models():
    blocked, reasons=recommendations_blocked({'seed':True,'stale':True,'meta':{'modelsTrained':0,'coveragePct':100,'eligibleSignals':0}})
    assert blocked and {'seed_data','stale_data','models_trained_zero'} <= set(reasons)
    # OOS quality is a per-idea badge now, never a global blocker.
    assert 'no_quality_gate_passed_signals' not in reasons

def test_healthy_build_not_blocked_despite_zero_eligible_and_few_errors():
    blocked, reasons=recommendations_blocked({'meta':{'modelsTrained':50,'coveragePct':99,'eligibleSignals':0,
                                                      'universeScreened':180,'pipelineErrors':['X: boom']}})
    assert not blocked and reasons == []

def test_excessive_pipeline_errors_block():
    blocked, reasons=recommendations_blocked({'meta':{'modelsTrained':50,'coveragePct':99,
                                                      'universeScreened':100,'pipelineErrors':['e']*11}})
    assert blocked and 'pipeline_errors_excessive' in reasons

def test_backtest_next_open_and_costs_constant_price():
    idx=pd.bdate_range('2024-01-01', periods=4)
    df=pd.DataFrame({'Open':[100]*4,'Close':[100]*4,'pred_cal':[1,1,0,0]}, index=idx)
    bt=long_flat_next_open(df, costs={'US':{'buyCommissionBps':0,'sellCommissionBps':0,'sellTaxBps':0,'slippageBps':10}}, region='US')
    assert bt['totalReturn'] < 0 and bt['accountingOk']
    # Trade dates must be JSON-safe ISO strings (a raw Timestamp here once broke
    # the Pages build at json.dumps time).
    assert bt['trades'][0]['date'] == idx[1].strftime('%Y-%m-%d')
    json.dumps(bt)

def test_dumps_sanitizes_nonfinite_floats():
    # NaN/Inf once aborted the artifact write (allow_nan=False) and blocked the
    # Pages deploy; they must serialize to null and leave ints/bools intact.
    payload = {"sharpe": float("nan"), "ratio": float("inf"), "np_nan": np.float64("nan"),
               "nested": [{"vol": float("-inf"), "ok": 1.5}], "n": 5, "flag": True}
    parsed = json.loads(_dumps(payload))
    assert parsed["sharpe"] is None and parsed["ratio"] is None and parsed["np_nan"] is None
    assert parsed["nested"][0]["vol"] is None and parsed["nested"][0]["ok"] == 1.5
    assert parsed["n"] == 5 and parsed["flag"] is True


def test_dumps_serializes_timestamps():
    # A stray pandas Timestamp must degrade to an ISO string, not raise.
    parsed = json.loads(_dumps({"asOf": pd.Timestamp("2026-07-14")}))
    assert parsed["asOf"].startswith("2026-07-14")


def test_no_sell_without_position():
    idx=pd.bdate_range('2024-01-01', periods=3)
    df=pd.DataFrame({'Open':[100,100,100],'Close':[100,100,100],'pred_cal':[0,0,0]}, index=idx)
    assert long_flat_next_open(df)['numTrades'] == 0

def test_half_kelly_weight_math_grade_scale_and_caps():
    # Grade A = pure half-Kelly: b=0.1/0.05=2, kelly=0.9-0.1/2=0.85, half=0.425 -> 10% cap
    assert suggested_weight(.9,.1,-.05,'A') == MAX_POSITION_WEIGHT
    # b=1, kelly=0.2, half=0.1 -> exactly the cap for grade A
    assert abs(suggested_weight(.6,.05,-.05,'A') - 0.1) < 1e-9
    # Grade B gets half of half-Kelly
    assert abs(suggested_weight(.6,.05,-.05,'B') - 0.05) < 1e-9
    # Volatility budget caps a high-vol name: 1.5% budget / 60% vol = 2.5%
    assert abs(suggested_weight(.9,.1,-.05,'A',60.0) - 0.025) < 1e-9
    # negative-edge kelly clamps to 0, degenerate move sizes -> None
    assert suggested_weight(.4,.05,-.05,'A') == 0.0
    assert suggested_weight(.9,-.01,-.05,'A') is None
    assert suggested_weight(.9,.05,.01,'A') is None

def test_build_idea_requires_validated_edge():
    stats={'upMean':.05,'downMean':-.02,'baseRate':.55}
    q={'eligible':True,'qualityGrade':'A','lift':8.0,'brierSkillScore':.06,'eligibilityReasons':[]}
    idea=build_idea('QQQ','US',.62,stats,10,'2026-07-14','Bull',{'mom63':.1,'aboveMA50':True,'realizedVol':25.0},q)
    assert idea is not None
    assert idea['suggestedWeightPct'] is not None and idea['suggestedWeightPct'] > 0
    assert idea['quality']['qualityGrade'] == 'A'
    assert idea['estimatedNetEdgePct'] > 0
    # unvalidated (REJECT) models are screened, never recommended
    assert build_idea('SPY','US',.62,stats,10,'2026-07-14','Bull',{'mom63':.1},{'eligible':False,'qualityGrade':'REJECT'}) is None

def test_build_idea_trend_veto():
    stats={'upMean':.05,'downMean':-.02,'baseRate':.55}
    q={'eligible':True,'qualityGrade':'A','lift':8.0,'brierSkillScore':.06,'eligibilityReasons':[]}
    # below MA50 AND negative momentum -> model fighting the tape -> veto
    assert build_idea('X','US',.62,stats,10,'2026-07-14','Bull',{'mom63':-.34,'aboveMA50':False},q) is None
    # either trend signal agreeing lets it through
    assert build_idea('X','US',.62,stats,10,'2026-07-14','Bull',{'mom63':-.05,'aboveMA50':True},q) is not None

def test_build_idea_rejects_bear_low_conviction_negative_edge():
    stats={'upMean':.05,'downMean':-.02,'baseRate':.55}
    q={'eligible':True,'qualityGrade':'B','lift':4.0,'brierSkillScore':.03,'eligibilityReasons':[]}
    assert build_idea('QQQ','US',.62,stats,10,'2026-07-14','Bear',{'mom63':.1},q) is None
    assert build_idea('QQQ','US',.50,stats,10,'2026-07-14','Bull',{'mom63':.1},q) is None
    assert build_idea('QQQ','US',.56,{'upMean':.003,'downMean':-.003},10,'2026-07-14','Bull',{'mom63':.1},q) is None

def test_rank_ideas_grade_a_first():
    mk=lambda t,e,g: {'ticker':t,'region':'US','estimatedNetEdgePct':e,'quality':{'eligible':True,'qualityGrade':g}}
    ranked=rank_ideas([mk('B_HIGH',5.0,'B'), mk('A_LOW',1.0,'A')])
    assert [i['ticker'] for i in ranked['US']] == ['A_LOW','B_HIGH']

def _lt_prices(n_tickers=8, days=400, seed=1):
    rng=np.random.default_rng(seed); out={}
    idx=pd.bdate_range('2024-01-01', periods=days)
    for i in range(n_tickers):
        drift=0.0002*(i - n_tickers/2)  # spread of trends so momentum ranks differ
        close=pd.Series(100*np.exp(np.cumsum(rng.normal(drift, .015, days))), index=idx)
        out[f'T{i}']=pd.DataFrame({'Close':close,'Open':close,'High':close,'Low':close,'Volume':1e6}, index=idx)
    return out

def test_longterm_ranks_without_fundamentals():
    from pipeline.longterm import build
    prices=_lt_prices()
    universe={'US':list(prices)}
    diags={t:{'aboveMA200':True,'regime':'Bull'} for t in prices}
    lt=build(universe, prices, {}, diags)
    assert lt is not None and lt['regions']['US']['picks']
    p=lt['regions']['US']['picks'][0]
    assert p['factors']['momentum'] is not None
    assert p['factors']['value'] is None and not p['valueDataAvailable']
    weights=[x['weightPct'] for x in lt['regions']['US']['picks']]
    assert abs(sum(weights) - 100) < 1.0  # inverse-vol weights normalized

def test_longterm_fundamentals_lift_value_rank():
    from pipeline.longterm import build_region
    prices=_lt_prices()
    cheap={'earningsYield':.12,'bookYield':.9,'fcfYield':.08,'roe':.3,'operatingMargin':.3,'profitMargin':.2,'debtToEquity':20,'earningsGrowth':.2}
    rich={'earningsYield':.01,'bookYield':.1,'fcfYield':.005,'roe':.02,'operatingMargin':.02,'profitMargin':.01,'debtToEquity':300,'earningsGrowth':-.1}
    mid={'earningsYield':.05,'bookYield':.4,'fcfYield':.03,'roe':.12,'operatingMargin':.12,'profitMargin':.08,'debtToEquity':100,'earningsGrowth':.05}
    fundamentals={'T0':cheap,'T1':rich,'T2':mid,'T3':mid}
    diags={t:{'aboveMA200':True,'regime':'Bull'} for t in prices}
    tbl=build_region(list(prices), prices, fundamentals, diags)
    assert tbl is not None
    assert tbl.loc['T0','value'] > tbl.loc['T1','value']
    assert tbl.loc['T0','quality'] > tbl.loc['T1','quality']

def test_longterm_trend_filter_orders_picks():
    from pipeline.longterm import build
    prices=_lt_prices()
    universe={'US':list(prices)}
    # best momentum name is BELOW its MA200 -> must not outrank confirmed names
    diags={t:{'aboveMA200':t!='T7','regime':'Bull'} for t in prices}
    lt=build(universe, prices, {}, diags)
    picks=[p['ticker'] for p in lt['regions']['US']['picks']]
    confirmed=[p for p in lt['regions']['US']['picks'] if p['aboveMA200']]
    assert confirmed and picks.index(confirmed[0]['ticker']) == 0

def test_zscore_winsorized_and_small_sample():
    from pipeline.longterm import zscore
    s=pd.Series([1,2,3,4,1000.0])
    z=zscore(s)
    assert z.abs().max() <= 2.5  # outlier clipped
    tiny=zscore(pd.Series([1.0,2.0]))
    assert tiny.isna().all()  # too few names -> no score, not garbage

def test_validate_exit_nonzero_on_seed(tmp_path):
    p=tmp_path/'site.json'; p.write_text(json.dumps({'seed':True,'stale':False,'generatedAt':'x','portfolioName':'x','core':[],'screened':[],'tradeIdeas':{'KR':[],'US':[]},'meta':{'modelsTrained':0,'coveragePct':100}}))
    r=subprocess.run([sys.executable,'-m','pipeline.validate',str(p)], cwd='.', capture_output=True, text=True)
    assert r.returncode != 0
