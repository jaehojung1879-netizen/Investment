"""Regression tests for fixed calendars, frozen inputs and measured KRW paths."""
import copy
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from pipeline import replay_calendar as RC
from pipeline import replay_inputs as RI
from pipeline import replay_valuation as RV
from pipeline import replay_determinism as RD
from pipeline import portfolio_validation as PV
from pipeline import pit_data


def test_schedule_is_a_prefix_across_cutoffs_and_does_not_read_prices():
    short = RC.schedule("2013-01-01", "2013-03-01")
    long = RC.schedule("2013-01-01", "2013-07-01")
    assert short == long[:len(short)]
    days = RC.sessions("2013-01-01", "2014-01-01")
    for left, right in zip(long, long[1:]):
        assert left["endDate"] == right["date"]
        assert days.get_loc(right["date"]) - days.get_loc(left["date"]) == 21
        assert left["signalDate"] < left["date"]
    assert any(row["endDate"] > "2013-03-01" for row in short)
    assert RD.compare_schedule(short, long)["verdict"] == RD.EXTENDED


def test_weekly_grid_waits_for_the_scheduled_end_of_week():
    thursday = RC.signal_grid("2020-01-01", "2020-01-09")
    friday = RC.signal_grid("2020-01-01", "2020-01-10")
    assert "2020-01-09" not in thursday
    assert friday == thursday + ["2020-01-10"]


def test_common_calendar_excludes_both_countries_holidays():
    common = RC.sessions("2024-07-01", "2024-08-31")
    assert pd.Timestamp("2024-07-04") not in common
    assert pd.Timestamp("2024-08-15") not in common


def test_snapshot_reuses_objects_and_refuses_revision_recovery_and_removal(tmp_path):
    store = RI.InputStore(tmp_path, "r", "d")
    data = {"price/2020-01":[{"date":"2020-01-02", "ticker":"A", "Close":100.0}],
            "macro":[], "universe":[{"names":["A","B"]}]}
    m1 = store.commit(data, through="2020-01-31", policy={"fixed":True})
    before = {p.name:p.read_bytes() for p in (tmp_path / "replay-inputs/objects").iterdir()}
    assert store.commit(data, through="2020-01-31", policy={"fixed":True}) == m1
    assert before == {p.name:p.read_bytes() for p in (tmp_path / "replay-inputs/objects").iterdir()}
    for changed in [
        {**data,"price/2020-01":[{"date":"2020-01-02", "ticker":"A", "Close":101.0}]},
        {**data,"price/2020-01":data["price/2020-01"]+[{"date":"2020-01-03","ticker":"B","Close":50}]},
        {**data,"price/2020-01":[]},
        {**data,"macro":[{"date":"2020-01-15","value":2}]},
    ]:
        with pytest.raises(RI.InputVersionConflict):
            store.commit(changed, through="2020-02-01", policy={"fixed":True})
        assert store.manifest() == m1
    extended = {**data,"price/2020-02":[{"date":"2020-02-03","ticker":"A","Close":103.0}]}
    m2 = store.commit(extended, through="2020-02-03", policy={"fixed":True})
    assert m2["components"]["price/2020-01"] == m1["components"]["price/2020-01"]
    assert store.load(m1) == data
    assert store.load() == extended


def test_snapshot_data_version_cannot_change_inside_same_replay_directory(tmp_path):
    RI.InputStore(tmp_path,"r","d").commit({},through="2020-01-01",policy={})
    with pytest.raises(RI.InputVersionConflict):
        RI.InputStore(tmp_path,"r","new-d").manifest()
    assert RI.InputStore(tmp_path,"new-r","new-d").manifest() is None


def test_snapshot_corruption_is_not_a_new_valid_baseline(tmp_path):
    store=RI.InputStore(tmp_path,"r","d")
    manifest=store.commit({"x":[{"date":"2020-01-01","value":1}]},through="2020-01-01",policy={})
    ref=manifest["components"]["x"][0]
    import gzip
    (tmp_path/"replay-inputs/objects"/(ref+".json.gz")).write_bytes(gzip.compress(b"[]"))
    with pytest.raises(RI.InputVersionConflict, match="hash mismatch"):
        store.load()


def valuation_fixture(end="2020-03-31"):
    days=RC.sessions("2020-01-01",end,"UNION")
    prices={}
    for name,region in [("A","US"),("B","KR"),("SPY","US"),("KS200","KR")]:
        sessions=RC.sessions("2020-01-01",end,region)
        prices[name]=pd.DataFrame({"Close":100.0},index=sessions)
    fx=pd.Series(np.linspace(1000,1100,len(days)),index=days)
    rates=[{"date":"2019-12-01","annualRatePct":3.65}]
    view=RV.ValuationData(prices,{"US":"SPY","KR":"KS200"},fx,rates,through=end)
    block=RC.schedule("2020-01-01",end)[0]
    decision={"date":block["signalDate"],"weights":{"A":.5,"B":.4},
              "regionByTicker":{"A":"US","B":"KR"},"cashPct":10,"selector":PV.CHAMPION}
    return view,decision,block


def test_us_sleeve_and_benchmark_use_identical_krw_fx_and_cash():
    view,decision,block=valuation_fixture()
    row,status=view.window(decision,block)
    assert status["status"]=="COMPLETE"
    fx_return=view.fx.loc[block["endDate"]]/view.fx.loc[block["date"]]-1
    expected=.5*fx_return+.1*row["riskFreeReturn"]
    assert row["grossReturn"]==pytest.approx(expected)
    assert row["benchmarkReturn"]==pytest.approx(expected)
    assert row["grossExcessReturn"]==pytest.approx(0)


@pytest.mark.parametrize("kind",["price","benchmark","fx","risk-free"])
def test_missing_inputs_never_shift_or_impute_the_block(kind):
    view,decision,block=valuation_fixture()
    original=copy.deepcopy(block)
    day=RC.sessions(block["date"],block["endDate"])[3]
    if kind=="price": view.prices["A"]=view.prices["A"].drop(day)
    if kind=="benchmark": view.prices["SPY"]=view.prices["SPY"].drop(day)
    if kind=="fx": view.fx=view.fx.drop(day)
    if kind=="risk-free": view.rates=[]
    row,status=view.window(decision,block)
    assert row is None and status["status"]=="INCOMPLETE"
    assert block==original


def test_horizon_maturity_uses_calendar_cutoff_even_when_all_inputs_are_missing():
    view,decision,block=valuation_fixture()
    view.through=block["date"]
    view.prices={}
    row,status=view.window(decision,block)
    assert row is None and status["status"]=="HORIZON_NOT_MATURED"
    cov=RV.coverage([status],90)
    assert cov["eligibleDecisions"]==0 and cov["droppedDecisions"]==0
    assert cov["completenessPct"] is None
    assert not cov["droppedByReason"]


def test_official_market_closure_can_mark_last_close_but_open_gap_cannot():
    view,decision,_=valuation_fixture()
    block={"date":"2020-01-17","endDate":"2020-01-21","signalDate":"2020-01-10"}
    assert pd.Timestamp("2020-01-20") not in view.prices["A"].index  # MLK day
    row,status=view.window(decision,block)
    assert status["status"]=="COMPLETE"
    assert "2020-01-20" in row["dailyDates"]  # KR open, FX still moves


def test_empty_portfolio_remains_measured_cash_not_a_missing_or_deleted_period():
    view,decision,block=valuation_fixture()
    decision["weights"]={}
    row,status=view.window(decision,block)
    assert status["status"]=="EMPTY_PORTFOLIO"
    assert row["grossReturn"]==pytest.approx(row["riskFreeReturn"])
    cov=RV.coverage([status],90)
    assert cov["completeOutcomes"]==1 and cov["completenessPct"]==100


def test_daily_drawdown_detects_intrablock_crash_and_includes_initial_nav():
    view,decision,block=valuation_fixture()
    decision["weights"]={"A":1.0}
    view.fx[:]=1000
    mid=RC.sessions(block["date"],block["endDate"],"US")[5]
    view.prices["A"].loc[mid]=50
    row,_=view.window(decision,block)
    result=PV._path_metrics([row],21,{"transactionCosts":{"US":{}}},[block["date"]])
    assert result["nav"][-1]["nav"]==pytest.approx(1)
    assert result["mddPct"]==pytest.approx(-50)
    assert result["sharpe"] is not None
    assert result["fxReturnsIncluded"] is True


def test_cash_to_equity_rebalance_cost_and_daily_terminal_return_agree():
    view,decision,block=valuation_fixture()
    row,_=view.window(decision,block)
    result=PV._path_metrics([row],21,{"transactionCosts":{"US":{"commissionBps":10},"KR":{"commissionBps":10}}},[block["date"]])
    assert result["nav"][-1]["nav"]-1==pytest.approx(row["costAdjustedReturn"])


def test_unknown_interval_prevents_full_nav_path():
    view,decision,block=valuation_fixture()
    row,_=view.window(decision,block)
    later=copy.deepcopy(row)
    later["date"]="2020-03-01"
    assert RV.daily_statistics([row,later])["available"] is False


def test_policy_rate_never_backfills_and_counts_calendar_days():
    view,_,_=valuation_fixture()
    dates=pd.to_datetime(["2020-01-03","2020-01-06"])
    assert view.risk_free_path(dates)[-1]==pytest.approx((1+.0365/365)**3)
    view.rates=[{"date":"2020-01-05","annualRatePct":3.65}]
    view._rf_cache.clear()
    assert view.risk_free_path(dates) is None


def test_long_empty_interval_reports_champion_and_exclusion_bias():
    dates=pd.date_range("2020-01-03",periods=9,freq="W-FRI").strftime("%Y-%m-%d")
    decisions={PV.CHAMPION:[{"date":d,"weights":{"A":1}} for d in dates],
               PV.CHALLENGER:[{"date":d,"weights":{},"emptyReasons":["CALIBRATION_NOT_MATURED"]} for d in dates]}
    report=PV.empty_portfolio_diagnostics(decisions,"2020-03-06")
    row=report["longIntervals"][0]
    assert row["durationCalendarDays"]==63
    assert row["championPortfolioDates"]==9
    assert row["exclusionCouldFavorChallenger"] and row["includedAsKrwCash"]


def test_real_published_nav_uses_actual_calendar_span_not_block_count():
    data=json.loads((Path(__file__).parent/"fixtures/replay-v6-headline.observed.json").read_text())
    for record in data["selectors"].values():
        years=RV.span_years(record["firstDate"],record["lastEndDate"])
        assert years > 12
        corrected=(record["nav"][-1]["nav"] ** (1/years)-1)*100
        original=(record["nav"][-1]["nav"] ** (12/record["periods"])-1)*100
        assert original==pytest.approx(record["cagrPct"],abs=.002)
        assert corrected < original


def test_pack_roundtrip_preserves_inputs_and_bounds_asof(tmp_path):
    view,_,_=valuation_fixture()
    data=RI.pack(prices={k:v.to_frame("Close") for k,v in view.prices.items()},
        benchmarks=view.benchmarks,universe={"US":["A"],"KR":["B"]},
        universe_history=pit_data.UniverseHistory({}), fundamentals=pit_data.FundamentalStore(),
        macro=pd.DataFrame({"x":[1.,np.nan]},index=pd.to_datetime(["2020-01-01","2020-01-02"])),
        vix=None,vintages={},fx=view.fx,rates={"events":view.rates,"source":"observed fixture","verifiedThrough":view.through},
        through=view.through,calendar_rows=[])
    store=RI.InputStore(tmp_path,"r","d")
    store.commit(data,through=view.through,policy={})
    frozen=RI.unpack(store.load())
    assert set(frozen["prices"])==set(view.prices)
    pd.testing.assert_series_equal(frozen["fx"],view.fx.rename("value"),check_freq=False,check_names=False)
    assert pd.isna(frozen["macro"].iloc[1,0])
    audit=RI.unpack(store.load(valuation_only=True))
    assert set(audit["prices"])==set(view.prices)


def test_breakdown_inside_zero_to_point_one_is_refined(monkeypatch):
    def step(rows, dates, gaps, worst, scale):
        good=scale < .037
        return {"stressScale":scale,"separated":good,
                "verdict":"CHAMPION_BETTER" if good else "INDISTINGUISHABLE"}
    monkeypatch.setattr(PV,"_bound_step",step)
    monkeypatch.setattr(PV,"worst_case_excess",lambda *a,**k:{("2020-01-01","US"):-.2})
    report=PV.survivorship_bound({PV.CHAMPION:[{"date":"2020-01-01"}],
                                 PV.CHALLENGER:[{"date":"2020-01-01"}]},
        ["2020-01-01"],[],{"universeCoverageByRegion":{"US":{"affectedObservationsPct":20}}},horizon=21)
    lo,hi=report["breakdownInterval"]
    assert lo <= .037 <= hi and hi-lo <= .001
    assert report["breakdownAbsoluteError"] <= .0005
    assert report["breakdownRefinementSteps"] <= 12
    assert len(report["sweep"])==6


def test_actual_benchmark_artifact_produces_reproducible_daily_nav(tmp_path):
    fixture=json.loads((Path(__file__).parent/"fixtures/benchmark-prices.observed.json").read_text())
    series=pd.DataFrame(fixture["prices"]["KS200"]).set_index("date")["close"]
    series.index=pd.to_datetime(series.index)
    rates=json.loads((Path(__file__).parents[1]/"data/bok-policy-rates.json").read_text())["events"]
    view=RV.ValuationData({"KS200":series.to_frame("Close")},{"KR":"KS200"},None,rates,through="2020-12-31")
    blocks=RC.schedule("2019-01-01","2020-12-31")
    rows=[]
    for block in blocks:
        row,status=view.window({"weights":{"KS200":1.0},"regionByTicker":{"KS200":"KR"}},block)
        if block["endDate"] <= view.through:
            assert status["status"]=="COMPLETE"
            rows.append(row)
    result=PV._path_metrics(rows,21,{"transactionCosts":{"KR":{}}},[r["date"] for r in rows])
    expected=series.loc[rows[-1]["endDate"]]/series.loc[rows[0]["date"]]
    assert result["nav"][-1]["nav"]==pytest.approx(expected)
    assert result["annualizedExcessPct"]==pytest.approx(0)
    store=RI.InputStore(tmp_path,"test-observed","observed-source-v1")
    data={"price/observed":[{"ticker":"KS200",**r} for r in RI.frame_rows(series.to_frame("Close"),"2020-12-31")]}
    manifest=store.commit(data,through="2020-12-31",policy={"basis":"observed benchmark test only"})
    assert store.load()==data
    mutated=copy.deepcopy(data)
    mutated["price/observed"][50]["Close"] *= .9
    with pytest.raises(RI.InputVersionConflict):
        store.commit(mutated,through="2020-12-31",policy=manifest["policy"])


def test_full_report_keeps_schedule_when_a_price_recovers(monkeypatch):
    view,_,_=valuation_fixture()
    signals=[]
    for date in RC.signal_grid("2020-01-01",view.through):
        for ticker,region in [("A","US"),("B","KR")]:
            signals.append({"id":date+ticker,"date":date,"ticker":ticker,"region":region,
                "alphaPercentile":95,"alpha":1,"entryState":"ACCUMULATE_GRADUALLY",
                "risk":{"downsideVolPct":20}, "factorPercentiles":{"momentum":95,"lowvol":95},
                "pit":{"pitCoverage":.8},"modelVersion":"m","replayVersion":"r"})
    monkeypatch.setattr(PV,"_research_candidates",lambda rows,*a,**kw:[PV._candidate(r,price_proxy=True) for r in rows])
    cfg={"minCashPct":15,"maxPositionWeight":.5,"maxSectorWeight":1,"maxThemeWeight":1,
         "regionCaps":{"KR":1,"US":1},"selection":{"targetNames":2,"minNames":1,"maxNamesPerSector":2,
         "maxNamesPerRegion":2,"minAlphaPercentile":66},"selectionNullDraws":2,"transactionCosts":{}}
    diagnostics={"requestedStart":"2020-01-01","lastDate":view.through,
                 "evaluationCalendar":RC.metadata("2020-01-01",view.through),"benchmarkCoverageGate":{"eligible":True}}
    good=PV.build_report(signals,[],cfg_lt={},cfg_pf=cfg,diagnostics=diagnostics,
                         replay_version="r",model_version="m",valuation=view)
    assert good["portfolioReplay"]["selectors"][PV.CHAMPION]["summary"]["available"]
    assert good["portfolioReplay"]["selectors"][PV.CHALLENGER]["horizons"]["21"]["outcomeCoverage"]["statusCounts"]["EMPTY_PORTFOLIO"] > 0
    view.prices["A"]=view.prices["A"].drop(pd.Timestamp("2020-01-15"))
    bad=PV.build_report(signals,[],cfg_lt={},cfg_pf=cfg,diagnostics=diagnostics,
                        replay_version="r",model_version="m",valuation=view,previous_report=good)
    assert not bad["contractValidation"]["eligible"]
    assert bad["portfolioReplay"]["blockSchedule"]==good["portfolioReplay"]["blockSchedule"]
    assert bad["replayDeterminism"]["reproducible"]  # input gate, not shifting anchors, explains failure
    assert not bad["portfolioReplay"]["selectors"][PV.CHAMPION]["summary"]["available"]


def test_calendar_bounds_fail_instead_of_silently_truncating():
    with pytest.raises(ValueError, match="calendar bounds"):
        RC.sessions("2035-12-01", "2036-01-01")


def test_rolling_annualization_uses_actual_leap_year_span():
    dates=pd.date_range("2016-01-01", "2022-01-01", freq="7D")
    years=np.array([(d-dates[0]).days/365.2425 for d in dates])
    row={"date":str(dates[0].date()), "endDate":str(dates[-1].date()),
         "transactionCost":0.0, "dailyDates":[str(d.date()) for d in dates],
         "dailyGrossNav":1.1**years, "dailyBenchmarkNav":1.04**years,
         "dailyRiskFreeNav":1.02**years}
    stats=RV.daily_statistics([row])
    assert stats["cagrPct"]==pytest.approx(10)
    for key in ("rolling3YAnnualizedExcess", "rolling5YAnnualizedExcess"):
        assert stats[key]
        for window in stats[key]:
            assert window["annualizedExcessPct"]==pytest.approx(6)
            assert window["calendarYears"]==pytest.approx(RV.span_years(window["firstDate"],window["date"]))


@pytest.mark.parametrize('day', ['2026-05-25', '2026-06-03', '2026-07-17'])
def test_confirmed_2026_kr_closures_are_not_required_prices(day):
    assert RC.sessions(day, day, 'KR').empty
    assert RC.sessions(day, day).empty
    if day != '2026-05-25':
        assert not RC.sessions(day, day, 'US').empty
        assert not RC.sessions(day, day, 'UNION').empty


def test_closure_carry_and_genuine_open_gap_are_distinguished():
    dates=RC.sessions('2026-06-02','2026-06-04','UNION')
    series=pd.Series([100.,102.],index=pd.to_datetime(['2026-06-02','2026-06-04']))
    view=RV.ValuationData({'KR':series.to_frame('Close')},{'KR':'KR'},None,[],through='2026-06-04')
    assert list(view.marks('KR','KR',dates))==[100.,100.,102.]
    assert view.missing_sessions('KR','KR',dates)==[]
    view.prices['KR']=view.prices['KR'].drop(pd.Timestamp('2026-06-04'))
    assert view.marks('KR','KR',dates) is None
    assert view.missing_sessions('KR','KR',dates)==['2026-06-04']


def test_missing_input_report_names_exact_observation_date():
    view,decision,block=valuation_fixture()
    missing=RC.sessions(block['date'],block['endDate'],'US')[4]
    view.prices['A']=view.prices['A'].drop(missing)
    row,status=view.window(decision,block)
    assert row is None
    assert {'input':'PRICE','ticker':'A','dates':[str(missing.date())]} in status['inputGaps']


def test_observed_v7_benchmark_gap_is_not_reclassified_as_a_holiday():
    data=json.loads((Path(__file__).parent/'fixtures/replay-v7-kr-benchmark-2013-02.observed.json').read_text())
    rows=[r for r in data['rows'] if r['ticker']=='^KS200']
    frame=pd.DataFrame(rows).set_index('date')
    frame.index=pd.to_datetime(frame.index)
    view=RV.ValuationData({'^KS200':frame},{'KR':'^KS200'},None,[],through='2013-02-28')
    dates=RC.sessions('2013-02-01','2013-02-28','UNION')
    assert view.missing_sessions('^KS200','KR',dates)==['2013-02-19']
    assert view.marks('^KS200','KR',dates) is None
