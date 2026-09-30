"""Synthetic/adversarial machine tests. No historical price/return artifacts."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from pipeline import kr_market_value as MV
from pipeline import kr_value_quality_catalyst as F
from pipeline import kr_model_overlay_portfolio as M
from pipeline import kr_market_risk_overlay as O
from pipeline import kr_concentrated_portfolio as P
from pipeline import kr_model_portfolio_execution as X
from pipeline import kr_portfolio_diagnostics as D
from pipeline import replay_calendar as RC
from scripts import run_kr_model_overlay_portfolio_v1 as CLI
from scripts.collect_kr_model_market_values import collect

ROOT = Path(__file__).resolve().parents[1]


def spec():
    return json.loads((ROOT / X.SPEC_PATH).read_text())


def quote(date="2020-01-03", ticker="000001.KS", **changes):
    return {"date": date, "securityId": ticker, "close": 100, "marketCap": 100000000,
            "listedShares": 1000000, "volume": 1000, "tradingValue": 100000,
            "source": MV.SOURCE, **changes}


def filing(year, stage="11011", available=None, basis="CFS", ni=10, ocf=12, assets=100, liabilities=30):
    available = available or f"{year+1}-03-01"
    accounts = {}
    for name, value, statement in (("당기순이익", ni, "IS"), ("영업활동현금흐름", ocf, "CF"),
                                  ("자산총계", assets, "BS"), ("부채총계", liabilities, "BS")):
        accounts[name] = {"amounts": {"thstrm_amount": value, "thstrm_add_amount": value}, "statement": statement}
    return {"id": f"f:{year}:{stage}:{available}", "ticker": "000001.KS", "fiscalYear": year,
            "reportCode": stage, "availableFrom": available, "receiptNos": [available.replace("-", "")+"000001"],
            "fsDiv": basis, "accounts": accounts}


def price_frame(start="2013-01-01", end="2021-01-01", growth=.0001):
    days = RC.sessions(start, end, "KR")
    return pd.DataFrame({"Close": 100*np.exp(growth*np.arange(len(days)))}, index=days)


def candidate(ticker="000001.KS", alpha=.02, dv=.2, adv=1e10, **changes):
    return {"ticker": ticker, "predictionH126": alpha, "downsideVol126": dv, "adv60": adv, "tradable": True, **changes}


@pytest.mark.parametrize("field,value", [("marketCap",0), ("listedShares",-1), ("close",np.nan),
                                         ("volume",None), ("tradingValue",-1)])
def test_market_invalid(field,value):
    with pytest.raises(ValueError):
        MV.validate_record(quote(**{field:value}))


def test_market_date_security_and_reconciliation():
    for kwargs in ({"date":"2099-01-01"}, {"ticker":"999999.KS"}):
        with pytest.raises(ValueError):
            MV.validate_record(quote(), **kwargs)
    with pytest.raises(ValueError, match="INCOHERENT"):
        MV.validate_record(quote(marketCap=1e12))


def test_parse_exact_krx_units():
    payload = {"OutBlock_1":[{"ISU_SRT_CD":"000001", "BAS_DD":"20200103", "TDD_CLSPRC":"100",
                             "MKTCAP":"100,000,000", "LIST_SHRS":"1,000,000", "ACC_TRDVOL":"1000", "ACC_TRDVAL":"100000"}]}
    rows = MV.parse_market_values(payload,"2020-01-03")
    assert rows == [quote()]
    assert MV.validate_record(rows[0])
    with pytest.raises(ValueError, match="DATE_IDENTITY"):
        MV.parse_market_values(payload,"2020-01-06")


def test_cache_immutable_and_hash_checked(tmp_path):
    MV.write_day(tmp_path,"2020-01-03",[quote()])
    first = (tmp_path/"2020-01-03.json").read_bytes()
    MV.write_day(tmp_path,"2020-01-03",[quote()])
    assert (tmp_path/"2020-01-03.json").read_bytes() == first
    with pytest.raises(ValueError,match="REWRITE"):
        MV.write_day(tmp_path,"2020-01-03",[quote(volume=2000)])
    doc=json.loads(first); doc["sha256"]="0"*64
    (tmp_path/"2020-01-03.json").write_text(json.dumps(doc))
    with pytest.raises(ValueError,match="HASH"):
        MV.MarketValueStore.load(tmp_path)


def test_market_no_future_asof_and_shuffle():
    a,b=quote(),quote("2020-01-06",marketCap=200000000,close=200)
    assert MV.MarketValueStore([a,b]).at(a["securityId"],"2020-01-02") is None
    assert MV.MarketValueStore([a,b]).identity()==MV.MarketValueStore([b,a]).identity()
    with pytest.raises(ValueError,match="DUPLICATE"):
        MV.MarketValueStore([a,a])


def test_collector_bounded_exact_dates_no_holiday_forward(tmp_path):
    payload={"OutBlock_1":[{"ISU_SRT_CD":"000001","TDD_CLSPRC":"100","MKTCAP":"100000000",
                           "LIST_SHRS":"1000000","ACC_TRDVOL":"1000","ACC_TRDVAL":"100000"}]}
    calls=[]
    def fetch(base,path,params,key):
        calls.append(params); return payload
    assert collect(tmp_path,["2020-01-03","2020-01-06"],key="synthetic",max_calls=1,pace=0,fetch=fetch)==1
    assert calls == [{"basDd":"20200103"}]


def test_publication_lag_receipt_identity_and_no_restated_future():
    rows=[filing(2018),filing(2019,ni=20)]
    assert F.accounting_values(rows,"2020-03-01")[0]["netIncomeTtm"]==10
    assert F.accounting_values(rows,"2020-03-02")[0]["netIncomeTtm"]==20
    late=filing(2019,available="2021-06-01",ni=999)
    assert F.accounting_values(rows+[late],"2020-05-01")==F.accounting_values(rows,"2020-05-01")
    wrong=filing(2020,available="2021-03-01");wrong["receiptNos"]=["20220101000001"]
    assert F.accounting_values(rows+[wrong],"2021-05-01")[0]["netIncomeTtm"]==20


def test_ttm_quarter_ytd_rollforward_and_same_basis():
    rows=[filing(2018,ni=100),filing(2018,"11014",available="2018-11-01",ni=70),
          filing(2019,"11014",available="2019-11-01",ni=80)]
    values,_=F.accounting_values(rows,"2019-12-01")
    assert values["netIncomeTtm"]==110
    rows[0]["fsDiv"]="OFS"
    assert F.accounting_values(rows,"2019-12-01")[0]["netIncomeTtm"] is None


@pytest.mark.parametrize("denominator", [None,-10,0,1,np.inf,np.nan])
def test_ratio_sign_denominators(denominator):
    assert F.ratio(-100,denominator) is None


def test_negative_numerators_preserved_no_sector_or_dart_shares():
    assert F.ratio(-100,100)==-1
    values,_=F.accounting_values([filing(2019,liabilities=150)],"2020-04-01")
    assert values["totalBookEquity"] == -50
    text=(ROOT/"pipeline/kr_value_quality_catalyst.py").read_text()
    assert "sector_of" not in text and "sharesOutstanding" not in text


def test_downside_all_sessions_and_future_invariance():
    frame=price_frame(end="2020-04-01",growth=0)
    date=str(frame.index[-1].date())
    frame.iloc[-1,0]=90
    expected=np.sqrt(.1**2/126)*np.sqrt(252)
    assert F.downside_vol(frame,date)==pytest.approx(expected)
    future=pd.concat([frame,pd.DataFrame({"Close":[1e10]},index=[pd.Timestamp("2025-01-02")])])
    assert F.downside_vol(future,date)==F.downside_vol(frame,date)
    assert F.downside_vol(frame.iloc[:-1],date) is None


@pytest.mark.parametrize("n",range(8))
@pytest.mark.parametrize("multiplier",[0,.4,.7,1])
def test_0_to_5_cash_caps_and_overlay_selection(n,multiplier):
    cfg=spec()["portfolio"]
    rows=[candidate(f"{i:06d}.KS",dv=.1+i/100) for i in range(n)]
    result=P.construct(rows,multiplier,cfg)
    assert len(result["selected"])==min(n,5)
    assert len(result["weights"])<=5
    assert sum(result["weights"].values())<=1
    assert result["cashWeight"]==pytest.approx(1-sum(result["weights"].values()))
    assert all(w<=.3+1e-12 for w in result["weights"].values())
    assert result["selected"]==P.construct(rows,1,cfg)["selected"]


def test_positive_cost_adjusted_opportunity_and_liquidity():
    cfg=spec()["portfolio"]
    rows=[candidate(alpha=0),candidate("000002.KS",alpha=cfg["roundTripFixedCost"]),
          candidate("000003.KS",adv=1),candidate("000004.KS",tradable=False),candidate("000005.KS",dv=0)]
    assert P.construct(rows,1,cfg)["weights"]=={}
    with pytest.raises(ValueError,match="LEVERAGE"):
        P.construct([],1.01,cfg)


def test_inverse_risk_and_shuffled_determinism():
    cfg=spec()["portfolio"]
    rows=[candidate(f"{i:06d}.KS",dv=(i+1)*.1) for i in range(5)]
    a=P.construct(rows,.7,cfg); b=P.construct(list(reversed(rows)),.7,cfg)
    assert a==b
    assert a["weights"]["000004.KS"]<a["weights"]["000000.KS"]


def test_tax_buffer_and_cost_stress_only_charges_actual_trades():
    cfg=spec()["portfolio"]
    adv={"000001.KS":1e10}
    buy=P.trading_cost({}, {"000001.KS":.2},adv,cfg)
    sell=P.trading_cost({"000001.KS":.2},{},adv,cfg)
    assert sell["costFraction"]>buy["costFraction"]
    assert P.trading_cost({}, {"000001.KS":.2},adv,cfg,stress=2)["costFraction"]==2*buy["costFraction"]
    assert P.trading_cost({"000001.KS":.2},{"000001.KS":.2},{},cfg)["costFraction"]==0
    with pytest.raises(ValueError,match="ADV_TRADE"):
        P.trading_cost({}, {"000001.KS":.3},{"000001.KS":1},cfg)


def test_overlay_past_only_known_rule_and_missingness():
    frame=price_frame(end="2020-04-01")
    date=str(frame.index[-1].date())
    assert O.state_at(frame,date)["riskMultiplier"]==1
    frame.iloc[-1,0]=frame.iloc[-1,0]/2
    adverse=O.state_at(frame,date)
    assert adverse["riskMultiplier"]==.4
    future=pd.concat([frame,pd.DataFrame({"Close":[1e10]},index=[pd.Timestamp("2025-01-02")])])
    assert O.state_at(future,date)==adverse
    assert O.state_at(frame.iloc[:20],str(frame.index[19].date()))["status"]=="DATA_INSUFFICIENT"


def train_fixture():
    rng=np.random.default_rng(42)
    dates=np.repeat(["2015-01-02","2015-01-09","2015-01-16","2015-01-23"],12)
    frame=pd.DataFrame(rng.normal(size=(48,len(F.RAW_FEATURES))),columns=F.RAW_FEATURES)
    frame["date"]=dates;frame["ticker"]=[f"{i%12:06d}.KS" for i in range(48)]
    frame["region"]="KR";frame["outcomeEndDate"]="2016-01-01";frame["labelStatus"]="MATURED"
    frame["forwardRelativeReturn"]=rng.normal(size=48)/100
    valid=frame.iloc[:12].copy();valid["date"]="2019-01-04"
    return frame,valid


def test_training_only_scaling_missingness_and_interactions():
    train,valid=train_fixture()
    w=np.ones(len(train))/12
    transformer=M.FamilyTransformer().fit(train,w)
    before=deepcopy(transformer.center)
    x,scores=transformer.transform(valid)
    valid.loc[:,list(F.RAW_FEATURES)]=1e12
    transformer.transform(valid)
    assert np.array_equal(before,transformer.center)
    assert np.isfinite(x).all()
    low={name:np.array([-1.]) for name in F.FAMILIES}
    assert np.all(M.FamilyTransformer.interactions(low)==0)
    high={name:np.array([2.]) for name in F.FAMILIES}
    assert M.FamilyTransformer.interactions(high).tolist()==[[4,4,4,8]]
    assert all(v.shape==(12,) for v in scores.values())


def test_model_chronology_decomposition_and_input_order():
    train,valid=train_fixture()
    a=M.fit_predict(train,valid,spec())
    b=M.fit_predict(train.sample(frac=1,random_state=2),valid.sample(frac=1,random_state=3),spec())
    assert np.allclose(a["predictions"].prediction,b["predictions"].prediction,atol=1e-12)
    assert np.allclose(a["contributions"].sum(axis=1)+a["estimator"].intercept_,a["predictions"].prediction)
    train["outcomeEndDate"]="2020-01-01"
    with pytest.raises(ValueError,match="MATURED"):
        M.fit_predict(train,valid,spec())


def test_weekly_calendar_extension_invariance_and_maturity():
    a=M.weekly_dates("2020-01-01","2020-06-01")
    b=M.weekly_dates("2020-01-01","2020-12-31")
    assert a == [d for d in b if d<="2020-06-01"]
    from pipeline.alpha_opportunity_v2_evaluation import target_from_sessions
    days=RC.sessions("2020-01-01","2022-12-31","KR")
    class NoPrice(dict):
        def get(self,*args,**kwargs):
            raise AssertionError("pending maturity read prices")
    for h in (126,252):
        value=target_from_sessions(days,NoPrice(),"069500.KS","000001.KS","2020-01-03",h,"2020-02-01")
        assert value["labelStatus"]=="PENDING"
        assert value["entryDate"]>"2020-01-03"


def test_gates_never_call_outcome_paths(monkeypatch):
    hits=[]
    def bomb(*a,**k):
        hits.append(1);raise AssertionError("historical access")
    for name in ("build_labels","model_predictions","evaluate_model","replay_portfolio"):
        monkeypatch.setattr(X,name,bomb)
    counters=X.Counters()
    report=X.pre_label_gates({"features":pd.DataFrame()},spec(),counters)
    assert report["status"]=="DATA_INSUFFICIENT"
    assert counters.zero() and hits==[]
    report=CLI.run("gates-only")
    assert all(v==0 for v in report["counters"].values())


def test_execute_refuses_before_prepare_or_label(monkeypatch):
    def bomb(*a,**k):
        raise AssertionError("source read before authorization")
    monkeypatch.setattr(X,"prepare",bomb)
    with pytest.raises(ValueError,match="EXECUTE_UNAUTHORIZED"):
        CLI.run("execute")
    with pytest.raises(ValueError,match="WITHOUT_PERMIT"):
        X.build_labels(None,{},spec(),126,X.Counters())
    with pytest.raises(ValueError,match="WITHOUT_PERMIT"):
        X.replay_portfolio(None,pd.DataFrame(),{},spec(),X.Counters())


def test_frozen_closure_and_prior_identity():
    frozen,sha=X.load_spec()
    assert sha==(ROOT/X.SPEC_PATH).with_suffix(".sha256").read_text().strip()
    assert frozen["horizons"]==[126,252]
    assert not (ROOT/X.AUTH_PATH).exists()
    assert not (ROOT/X.RESULT_PATH).exists()
    assert frozen["portfolio"]["singleNameCap"]==.3
    assert frozen["sectorStatus"]=="DEFERRED_BY_PIT_SECTOR_HISTORY"


def test_one_shot_durable_write_and_receipt_immutability(tmp_path):
    data={"state":"DEVELOPMENT_INCONCLUSIVE"}
    first=X.atomic_write(tmp_path/"primary.json",data,immutable=True)
    with pytest.raises(FileExistsError):
        X.atomic_write(tmp_path/"primary.json",{"state":"DEVELOPMENT_CANDIDATE"},immutable=True)
    assert X.file_hash(tmp_path/"primary.json")==first
    kwargs={"signal_date":"2026-10-02","merge_date":"2026-09-30","spec_sha":"a"*64,
            "input_sha":"b"*64,"model_snapshot_sha":"c"*64,"predictions":[],"portfolio":{},"overlay":{}}
    X.prediction_receipt(tmp_path/"receipt.json",**kwargs)
    with pytest.raises(FileExistsError):
        X.prediction_receipt(tmp_path/"receipt.json",**kwargs)
    with pytest.raises(ValueError,match="STRICTLY_AFTER"):
        X.prediction_receipt(tmp_path/"bad.json",**{**kwargs,"signal_date":"2026-09-30"})
    with pytest.raises(ValueError,match="OUTCOME_IN"):
        X.prediction_receipt(tmp_path/"bad.json",**{**kwargs,"predictions":[{"forwardReturn":99}]})


def test_development_conjunction_no_head_rescue():
    model={"complete":True,"mseImprovementVsMean":1,"mseImprovementVsMomentum":1,"rankWeightedSpread":1}
    portfolio={"complete":True,"netExcess":1,"chronologicalHalfExcess":[1,1]}
    assert X.development_state(model,portfolio)=="DEVELOPMENT_CANDIDATE"
    assert X.development_state({**model,"complete":False},portfolio)=="DATA_INSUFFICIENT"
    assert X.development_state(model,{**portfolio,"netExcess":-1})=="DEVELOPMENT_REJECT"
    assert X.development_state({**model,"rankWeightedSpread":-1},portfolio)=="DEVELOPMENT_INCONCLUSIVE"


def test_valuation_auxiliary_discloses_mechanical_price_and_no_distribution():
    a={"securityId":"000001.KS","basis":"CFS","totalBookEquity":100,"marketCap":100}
    b={**a,"marketCap":200,"totalBookEquity":150}
    result=D.valuation_convergence(a,b)
    assert result["priceMechanical"] and not result["affectsPrimary"]
    assert result["distributionContribution"] is None
    assert result["logBookGrowth"]+result["logMultipleExpansion"]==pytest.approx(np.log(2))
    assert D.valuation_convergence(a,{**b,"basis":"OFS"})["status"]=="NOT_INTERPRETABLE"


def test_workflow_firewall_and_primary_always_upload():
    text=(ROOT/".github/workflows/kr-model-overlay-portfolio-v1.yml").read_text()
    assert "EXECUTE_UNAUTHORIZED" in text and "V1_ALREADY_CLOSED" in text
    assert "PRIMARY_ALREADY_EXISTS_DO_NOT_RERUN" in text
    assert text.count("--mode execute --inputs") == 1
    assert "if: always() && steps.primary.outputs.exists == 'true'" in text
    assert "schedule:" not in text


def gate_bundle():
    schedule=M.weekly_dates("2015-01-01","2026-09-14")
    rows=[]
    for date in schedule:
        for i in range(10):
            row={"date":date,"ticker":f"{i:06d}.KS","region":"KR",**dict.fromkeys(F.RAW_FEATURES,.1),
                 "accountingProvenance":{"availableFrom":"2014-12-31"},"marketValuePresent":True,"tradable":True,
                 "adv60":1e10,"downsideVol126":.2}
            rows.append(row)
    return {"features":pd.DataFrame(rows),"schedule":schedule,
            "overlay":{d:{"status":"READY","riskMultiplier":1} for d in schedule}}


def test_passed_gates_still_zero_access_and_future_publication_blocks(monkeypatch):
    for name in ("build_labels","model_predictions","evaluate_model","replay_portfolio"):
        monkeypatch.setattr(X,name,lambda *a,**k: pytest.fail("outcome function called"))
    bundle=gate_bundle(); counters=X.Counters()
    result=X.pre_label_gates(bundle,spec(),counters)
    assert result["status"]=="READY"
    assert result["stoppedBeforeOutcomes"] and counters.zero()
    assert result["coverage"]["2020"]["denominator"]>0
    assert result["annualTrainingDepthUpperBounds"]["252"]["2026"]>104
    bundle["features"].at[0,"accountingProvenance"]={"availableFrom":"2099-01-01"}
    with pytest.raises(ValueError,match="PUBLICATION"):
        X.pre_label_gates(bundle,spec(),counters)


def test_family_feature_fail_cannot_be_removed_to_pass():
    bundle=gate_bundle()
    bundle["features"]["bookToMarketProxy"]=None
    counters=X.Counters()
    result=X.pre_label_gates(bundle,spec(),counters)
    assert result["status"]=="DATA_INSUFFICIENT"
    assert any("bookToMarketProxy" in reason for reason in result["reasons"])
    assert counters.zero()


def test_input_allowlist_excludes_signal_and_outcome_files(tmp_path):
    (tmp_path/"ledger/historical/replay-v16").mkdir(parents=True)
    for name in ["signals-2020-01.jsonl.gz","outcomes-2020-01.jsonl.gz"]:
        (tmp_path/"ledger/historical/replay-v16"/name).write_bytes(b"must never be read")
    assert X.input_identity(tmp_path)["files"]=={}


def replay_fixture():
    cfg=deepcopy(spec())
    cfg["developmentCutoff"]="2020-05-01"
    cfg["walkForward"]["featureStart"]="2020-01-01"
    cfg["gates"]["minimumPortfolioSessions"]=10
    days=RC.sessions("2019-01-01","2020-05-01","KR")
    tickers=["000001.KS","000002.KS"]
    prices={t:pd.DataFrame({"Close":100*np.exp(.001*np.arange(len(days)))},index=days) for t in tickers}
    prices["069500.KS"]=pd.DataFrame({"Close":100*np.exp(.0003*np.arange(len(days)))},index=days)
    market=MV.MarketValueStore([quote(str(d.date()),t,tradingValue=1e10) for d in days for t in tickers])
    schedule=M.weekly_dates("2020-01-01","2020-05-01")
    features=[];predictions=[]
    for date in schedule:
        for t in tickers:
            features.append({"date":date,"ticker":t,"region":"KR","adv60":1e10,"downsideVol126":.2,"tradable":True})
            predictions.append({"date":date,"ticker":t,"region":"KR","prediction":.02,"momentumPrediction":.015})
    bundle={"features":pd.DataFrame(features),"market":market,"prices":prices,"schedule":schedule,
            "overlay":{d:{"status":"READY","riskMultiplier":.7} for d in schedule}}
    permit=X.OutcomePermit("synthetic-spec","synthetic-input",X._PERMIT_TOKEN)
    return permit,pd.DataFrame(predictions),bundle,cfg


def test_synthetic_continuous_replay_determinism_cost_cash_and_suspension():
    permit,predictions,bundle,cfg=replay_fixture()
    counters=X.Counters()
    a=X.replay_portfolio(permit,predictions,bundle,cfg,counters)
    b=X.replay_portfolio(permit,predictions.sample(frac=1,random_state=1),bundle,cfg,X.Counters())
    assert a==b and a["complete"]
    assert a["grossReturn"]>a["netReturn"]
    assert all(r["holdings"]<=5 and r["cashWeight"]>=0 for r in a["path"])
    assert counters.portfolioOutcomeCalls==1 and counters.targetCalls==0
    # No mark is invented for a missing held-security/termination session.
    day=a["path"][5]["date"]
    bundle["prices"]["000001.KS"]=bundle["prices"]["000001.KS"].drop(pd.Timestamp(day))
    bundle["market"].rows.pop((day,"000001.KS"))
    with pytest.raises(ValueError,match="TERMINAL_ECONOMICS_UNRESOLVED"):
        X.replay_portfolio(permit,predictions,bundle,cfg,X.Counters())


def test_prospective_recursive_label_rejection_and_sector_deferred_registry(tmp_path):
    with pytest.raises(ValueError,match="OUTCOME_IN"):
        X.prediction_receipt(tmp_path/"p.json",signal_date="2026-10-02",merge_date="2026-09-30",spec_sha="a"*64,
                             input_sha="b"*64,model_snapshot_sha="c"*64,predictions=[],
                             portfolio={"nested":{"label":3}},overlay={})
    cfg=spec()
    assert cfg["portfolio"]["sectorCap"] is None
    assert all(not any(token in name.lower() for token in ["ebitda","roic","netdebt","sector"])
               for names in cfg["featureFamilies"].values() for name in names)
    assert cfg["inputs"]["DartSharesStatus"]=="REJECTED_AS_PIT_VALUATION_SOURCE"


def test_research_imports_are_unreachable_from_production():
    from pipeline.alpha_opportunity_v3_spec import import_closure
    research = {"pipeline/" + module.__name__.split(".")[-1] + ".py" for module in (MV, F, M, O, P, X, D)}
    production = import_closure(["pipeline/build.py", "pipeline/longterm.py", "pipeline/opportunity.py",
                                 "pipeline/kelly_portfolio.py", "pipeline/validate.py"], ROOT)
    assert research.isdisjoint(production)
    for module in (MV, F, M, O, P, X, D):
        assert "pipeline/" + module.__name__.split(".")[-1] + ".py" in spec()["dependencyHashes"]


def test_empty_predictions_withhold_portfolio_path():
    permit = X.OutcomePermit("synthetic-spec", "synthetic-input", X._PERMIT_TOKEN)
    counters = X.Counters()
    result = X.replay_portfolio(permit, pd.DataFrame(), {"schedule": []}, spec(), counters)
    assert result == {"complete": False, "reason": "NO_PREDICTIONS"}


def test_permanent_formal_lock_survives_artifact_retention():
    workflow = (ROOT / ".github/workflows/kr-model-overlay-portfolio-v1.yml").read_text()
    assert "git.createRef" in workflow and "PERMANENT_ONE_SHOT_LOCK_ALREADY_EXISTS" in workflow
    assert "git.updateRef" not in workflow and "git.deleteRef" not in workflow
    assert "KR_V1_EXECUTION_LOCK" in workflow


def test_nonfinite_trailing_quotes_block_risk_inputs():
    frame = price_frame()
    frame.loc[frame.index[-1], "Close"] = np.inf
    date = str(frame.index[-1].date())
    assert F.downside_vol(frame, date) is None
    assert O.state_at(frame, date)["status"] == "DATA_INSUFFICIENT"


def test_authorization_pins_and_clean_gate_permit(tmp_path):
    frozen = spec()
    identity = {"sha256": "synthetic-input"}
    auth = {"studyId": X.STUDY, "specSha256": "synthetic-spec", "inputSnapshotSha256": identity["sha256"],
            "harnessHashes": frozen["dependencyHashes"], "diagnosticSpecSha256": frozen["diagnostics"]["sha256"],
            "authorizedExecutions": 1, "authorizedBy": "synthetic-operator", "mergeCommit": "synthetic-merge"}
    X.atomic_write(tmp_path / X.AUTH_PATH, auth)
    with pytest.raises(ValueError, match="IDENTITY_MISMATCH"):
        X.require_authorization(frozen, "different-spec", identity, tmp_path)
    with pytest.raises(ValueError, match="CLEAN_PASSED_GATES"):
        X.issue_permit({"status": "READY", "counters": {"targetCalls": 1}}, frozen, "synthetic-spec", identity, tmp_path)
    permit = X.issue_permit({"status": "READY", "counters": {"targetCalls": 0}}, frozen, "synthetic-spec", identity, tmp_path)
    X.require_permit(permit)


def test_diagnostic_crash_cannot_rewrite_or_retry_primary(tmp_path, monkeypatch):
    # Fake authorization/Actions only in a synthetic temporary checkout; never real execution.
    frozen, sha = spec(), "synthetic-spec"
    auth = b'{"synthetic":true}'
    path = tmp_path / X.AUTH_PATH
    path.parent.mkdir(parents=True)
    path.write_bytes(auth)
    monkeypatch.setattr(X, "load_spec", lambda *a: (frozen, sha))
    monkeypatch.setattr(CLI.subprocess, "check_output", lambda *a, **k: auth)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    monkeypatch.setenv("KR_V1_EXECUTION_LOCK", sha)
    monkeypatch.setattr(X, "input_identity", lambda *a: {"sha256": "synthetic-input"})
    monkeypatch.setattr(X, "require_authorization", lambda *a: {})
    monkeypatch.setattr(X, "prepare", lambda *a: {})
    monkeypatch.setattr(X, "pre_label_gates", lambda *a: {"status": "READY", "counters": {}})
    monkeypatch.setattr(X, "run_historical", lambda *a: ({"state": "DATA_INSUFFICIENT", "synthetic": True}, {}))
    def crash(*args):
        raise RuntimeError("synthetic diagnostic failure")
    monkeypatch.setattr(D, "supplementary", crash)
    output = tmp_path / "run"
    primary = CLI.run("execute", input_root=tmp_path, output=output, root=tmp_path)
    original = (output / "primary.json").read_bytes()
    assert primary["synthetic"] and (output / "diagnostics/error.json").exists()
    assert X.file_hash(output / "primary.json") == json.loads((output / "primary.sha256.json").read_text())["fileSha256"]
    with pytest.raises(ValueError, match="ONE_SHOT_ALREADY_SPENT"):
        CLI.run("execute", input_root=tmp_path, output=output, root=tmp_path)
    assert (output / "primary.json").read_bytes() == original


def test_suspended_and_partial_exits_still_occupy_holding_slots():
    occupied = {f"old{i}": .1 for i in range(5)}
    buys = {"new1": .2, "new2": .2, "old1": .03}
    assert P.limit_new_positions(occupied, buys, ["new2", "new1", "old1"]) == {"old1": .03}
    occupied["old0"] = 0.0
    allowed = P.limit_new_positions(occupied, buys, ["new2", "new1", "old1"])
    assert list(allowed) == ["old1", "new2"]
