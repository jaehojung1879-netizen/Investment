import json, subprocess, sys
import numpy as np
import pandas as pd

from pipeline.features import add_targets, build_features, feature_columns
from pipeline.model import current_signal, walk_forward
from pipeline.config import ModelConfig
from pipeline.quality import evaluate_oos, recommendations_blocked
from pipeline.backtest import long_flat_next_open
from pipeline.trade import suggested_weight


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
    assert 'signal_observations_below_30' in q['eligibilityReasons']
    q2=evaluate_oos(res, threshold=.5)
    assert not q2['eligible'] and q2['brierSkillScore'] < 0

def test_block_reasons_seed_stale_zero_models():
    blocked, reasons=recommendations_blocked({'seed':True,'stale':True,'meta':{'modelsTrained':0,'coveragePct':100,'eligibleSignals':0}})
    assert blocked and {'seed_data','stale_data','models_trained_zero','no_quality_gate_passed_signals'} <= set(reasons)

def test_backtest_next_open_and_costs_constant_price():
    idx=pd.bdate_range('2024-01-01', periods=4)
    df=pd.DataFrame({'Open':[100]*4,'Close':[100]*4,'pred_cal':[1,1,0,0]}, index=idx)
    bt=long_flat_next_open(df, costs={'US':{'buyCommissionBps':0,'sellCommissionBps':0,'sellTaxBps':0,'slippageBps':10}}, region='US')
    assert bt['totalReturn'] < 0 and bt['accountingOk']
    assert bt['trades'][0]['date'] == idx[1]

def test_no_sell_without_position():
    idx=pd.bdate_range('2024-01-01', periods=3)
    df=pd.DataFrame({'Open':[100,100,100],'Close':[100,100,100],'pred_cal':[0,0,0]}, index=idx)
    assert long_flat_next_open(df)['numTrades'] == 0

def test_no_portfolio_means_no_kelly_weight():
    assert suggested_weight(.9,.1,-.05) is None

def test_validate_exit_nonzero_on_seed(tmp_path):
    p=tmp_path/'site.json'; p.write_text(json.dumps({'seed':True,'stale':False,'generatedAt':'x','portfolioName':'x','core':[],'screened':[],'tradeIdeas':{'KR':[],'US':[]},'meta':{'modelsTrained':0,'coveragePct':100}}))
    r=subprocess.run([sys.executable,'-m','pipeline.validate',str(p)], cwd='.', capture_output=True, text=True)
    assert r.returncode != 0
