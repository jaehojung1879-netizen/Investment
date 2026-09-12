"""Regression tests for fixed calendars, frozen inputs and measured KRW paths."""
import copy
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from pipeline import replay_calendar as RC
from pipeline import benchmark_source as BS
from pipeline import replay_inputs as RI
from pipeline import replay_recovery as RR
from pipeline import replay_valuation as RV
from pipeline import replay_determinism as RD
from pipeline import portfolio_validation as PV
from pipeline import pit_data
from pipeline import price_adjustment as PA


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


def test_snapshot_reuses_objects_and_refuses_a_revised_value(tmp_path):
    """A sealed NUMBER may never move; which names a vendor served may.

    This used to refuse any prefix difference at all, including a name the
    vendor simply failed to serve on the second run. replay-v14 run #55 showed
    what that costs: Yahoo drops delisted tickers intermittently (measured
    286 -> 282 missing across two acquisitions an hour apart, no code change),
    and every flip refused the run. See
    tests/test_input_prefix_reconciliation.py for the availability cases; what
    is pinned HERE is that the teeth are still in.
    """
    store = RI.InputStore(tmp_path, "r", "d")
    data = {"price/2020-01":[{"date":"2020-01-02", "ticker":"A", "Close":100.0}],
            "macro":[], "universe":[{"names":["A","B"]}]}
    m1 = store.commit(data, through="2020-01-31", policy={"fixed":True})
    before = {p.name:p.read_bytes() for p in (tmp_path / "replay-inputs/objects").iterdir()}
    assert store.commit(data, through="2020-01-31", policy={"fixed":True}) == m1
    assert before == {p.name:p.read_bytes() for p in (tmp_path / "replay-inputs/objects").iterdir()}
    for changed in [
        # A sealed name coming back with a different close.
        {**data,"price/2020-01":[{"date":"2020-01-02", "ticker":"A", "Close":101.0}]},
        # A sealed name growing an extra session inside a published month.
        {**data,"price/2020-01":data["price/2020-01"]
                                + [{"date":"2020-01-03","ticker":"A","Close":50}]},
        # An undated input is frozen whole: a change there is policy drift.
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


def test_generation_benchmark_lineage_is_loaded_without_full_snapshot(tmp_path):
    store=RI.InputStore(tmp_path,"r","d")
    lineage=[{"region":"KR","ticker":"^KS200","source":"fdr",
              "symbol":"KS200","policy":"PINNED_FOR_GENERATION"}]
    manifest=store.commit({"benchmark/source":lineage,
                           "price/2020-01":[{"date":"2020-01-02","ticker":"A","Close":1.0}]},
                          through="2020-01-02",policy={})

    assert store.load_component("benchmark/source",manifest)==lineage

    # The audit loads the valuation slice, which projects every dated panel down
    # to (date, ticker, Close). The lineage rows share the "benchmark/" prefix
    # and have none of those keys, so a prefix test alone walks into them: this
    # is the KeyError that killed the first replay-v10 audit before it could
    # write a report, leaving replay-v9's report to be quoted as the reason.
    slice_=store.load(manifest,valuation_only=True)
    assert slice_["price/2020-01"]==[{"date":"2020-01-02","ticker":"A","Close":1.0}]
    assert slice_[RI.BENCHMARK_SOURCE]==lineage


def test_snapshot_corruption_is_not_a_new_valid_baseline(tmp_path):
    store=RI.InputStore(tmp_path,"r","d")
    manifest=store.commit({"x":[{"date":"2020-01-01","value":1}]},through="2020-01-01",policy={})
    ref=manifest["components"]["x"][0]
    import gzip
    (tmp_path/"replay-inputs/objects"/(ref+".json.gz")).write_bytes(gzip.compress(b"[]"))
    with pytest.raises(RI.InputVersionConflict, match="hash mismatch"):
        store.load()


def test_official_fx_resolution_uses_only_latest_prior_fixing_and_records_age():
    observations=pd.Series([1300.,1310.],index=pd.to_datetime(["2024-03-28","2024-04-01"]))
    dates=pd.to_datetime(["2024-03-28","2024-03-29","2024-04-01"])
    resolved,mapping=RR.resolve_fx_fixings(observations,dates)
    assert resolved.tolist()==[1300.,1300.,1310.]
    assert [row["observationDate"] for row in mapping]==[
        "2024-03-28","2024-03-28","2024-04-01"]
    assert mapping[1]["ageCalendarDays"]==1
    with pytest.raises(RR.RecoveryError,match="timely prior"):
        RR.resolve_fx_fixings(observations,pd.to_datetime(["2024-04-08"]),max_staleness_days=3)


def test_kr_gap_recovery_requires_market_wide_hole_and_validated_return_bridge():
    sessions=RC.sessions("2020-01-02","2020-01-10","KR")
    gap=sessions[2]
    fallback=pd.DataFrame({"Open":np.arange(len(sessions))+100.,
        "High":np.arange(len(sessions))+101.,"Low":np.arange(len(sessions))+99.,
        "Close":np.arange(len(sessions))+100.,"Volume":1000.},index=sessions)
    tickers=[f"{i:06d}.KS" for i in range(20)]
    prices={ticker:(fallback*pd.Series({"Open":2,"High":2,"Low":2,"Close":2,"Volume":1})).drop(gap)
            for ticker in tickers}
    late="999999.KS"
    prices[late]=fallback.loc[fallback.index > gap].copy()
    prices["^KS200"]=pd.DataFrame({"Close":200.},index=sessions)
    report=RR.recover_systemic_kr_gaps(prices,tickers+[late],"^KS200",
        start="2020-01-02",through="2020-01-10",fetcher=lambda *args:fallback)
    assert len(report["systemicDates"])==1
    assert len(report["accepted"])==20 and not report["rejected"]
    assert all(prices[ticker].at[gap,"Close"]==pytest.approx(fallback.at[gap,"Close"]*2)
               for ticker in tickers)
    assert gap not in prices[late].index  # no pre-listing backfill

    # A lone missing name is consistent with a suspension, not a failed market
    # data session, and must remain missing.
    lone={ticker:fallback.mul(2) for ticker in tickers}
    lone[tickers[0]]=lone[tickers[0]].drop(gap)
    lone["^KS200"]=pd.DataFrame({"Close":200.},index=sessions)
    report=RR.recover_systemic_kr_gaps(lone,tickers,"^KS200",
        start="2020-01-02",through="2020-01-10",fetcher=lambda *args:fallback)
    assert not report["systemicDates"] and gap not in lone[tickers[0]].index


def test_kr_gap_recovery_rejects_adjustment_bridge_mismatch():
    sessions=RC.sessions("2020-01-02","2020-01-10","KR")
    gap=sessions[2]
    tickers=[f"{i:06d}.KS" for i in range(20)]
    base=pd.DataFrame({"Close":np.arange(len(sessions))+100.},index=sessions)
    prices={ticker:base.mul(2).drop(gap) for ticker in tickers}
    prices["^KS200"]=pd.DataFrame({"Close":200.},index=sessions)
    broken=base.copy()
    broken.loc[sessions[3]:,"Close"]*=1.1
    report=RR.recover_systemic_kr_gaps(prices,tickers,"^KS200",
        start="2020-01-02",through="2020-01-10",fetcher=lambda *args:broken)
    assert not report["accepted"]
    assert {row["reason"] for row in report["rejected"]}=={"NO_UNADJUSTED_PRIMARY_BRIDGE"}
    assert all(gap not in prices[ticker].index for ticker in tickers)


def test_kr_gap_recovery_compares_raw_returns_then_uses_lower_adjusted_bound():
    """Replay #42 confused Yahoo total return with FDR raw price return.

    The two raw series agree exactly.  A 2.04% adjustment-factor transition is
    therefore not vendor disagreement; the unavailable adjusted close is
    bounded by the two observed factors and the lower long-only NAV is used.
    """
    sessions=RC.sessions("2020-01-02","2020-01-10","KR")
    gap=sessions[2]
    right=sessions[3]
    tickers=[f"{i:06d}.KS" for i in range(20)]
    raw=pd.DataFrame({"Close":np.arange(len(sessions))+100.},index=sessions)
    adjusted=raw.mul(.98)
    adjusted.loc[right:,"Close"]=raw.loc[right:,"Close"]
    prices={ticker:adjusted.drop(gap).copy() for ticker in tickers}
    prices["^KS200"]=pd.DataFrame({"Close":200.},index=sessions)
    raw_frames={ticker:raw.copy() for ticker in tickers}

    report=RR.recover_systemic_kr_gaps(
        prices,tickers,"^KS200",start="2020-01-02",through="2020-01-10",
        fetcher=lambda *args:raw,
        targeted_primary_fetcher=lambda *args:{},
        raw_primary_fetcher=lambda *args:raw_frames)

    assert len(report["accepted"])==20 and not report["rejected"]
    assert {row["method"] for row in report["accepted"]}=={
        "FDR_RAW_RETURN_WITH_OBSERVED_ADJUSTMENT_BOUNDS_LOWER_NAV"}
    assert all(prices[ticker].at[gap,"Close"]==pytest.approx(raw.at[gap,"Close"]*.98)
               for ticker in tickers)
    assert all(row["rawBridgeDifferenceBps"]==pytest.approx(0)
               for row in report["accepted"])
    assert all(200 < row["pathUncertaintyBps"] < 205
               for row in report["accepted"])


def test_kr_gap_recovery_prefers_exact_targeted_yahoo_retry():
    sessions=RC.sessions("2020-01-02","2020-01-10","KR")
    gap=sessions[2]
    tickers=[f"{i:06d}.KS" for i in range(20)]
    full=pd.DataFrame({"Close":np.arange(len(sessions))+100.},index=sessions)
    prices={ticker:full.drop(gap).copy() for ticker in tickers}
    prices["^KS200"]=pd.DataFrame({"Close":200.},index=sessions)
    targeted={ticker:full.copy() for ticker in tickers}

    report=RR.recover_systemic_kr_gaps(
        prices,tickers,"^KS200",start="2020-01-02",through="2020-01-10",
        fetcher=lambda *args:None,
        targeted_primary_fetcher=lambda *args:targeted,
        raw_primary_fetcher=lambda *args:{})

    assert len(report["accepted"])==20 and not report["rejected"]
    assert {row["fallbackVendor"] for row in report["accepted"]}=={
        "YAHOO_TARGETED_RETRY"}
    assert all(prices[ticker].at[gap,"Close"]==full.at[gap,"Close"] for ticker in tickers)


def test_kr_gap_recovery_still_rejects_disagreeing_raw_vendor_returns():
    sessions=RC.sessions("2020-01-02","2020-01-10","KR")
    gap=sessions[2]
    tickers=[f"{i:06d}.KS" for i in range(20)]
    raw=pd.DataFrame({"Close":np.arange(len(sessions))+100.},index=sessions)
    adjusted=raw.mul(.98)
    adjusted.loc[sessions[3]:,"Close"]=raw.loc[sessions[3]:,"Close"]
    prices={ticker:adjusted.drop(gap).copy() for ticker in tickers}
    prices["^KS200"]=pd.DataFrame({"Close":200.},index=sessions)
    disagreeing=raw.copy()
    disagreeing.loc[sessions[3]:,"Close"]*=1.05

    report=RR.recover_systemic_kr_gaps(
        prices,tickers,"^KS200",start="2020-01-02",through="2020-01-10",
        fetcher=lambda *args:disagreeing,
        targeted_primary_fetcher=lambda *args:{},
        raw_primary_fetcher=lambda *args:{ticker:raw for ticker in tickers})

    assert not report["accepted"]
    assert {row["reason"] for row in report["rejected"]}=={
        "RAW_RETURN_BRIDGE_MISMATCH"}


def test_observed_v8_batch_holes_meet_systemic_not_individual_threshold():
    fixture=json.loads((Path(__file__).parent/"fixtures/replay-v8-kr-batch-gaps.observed.json").read_text())
    for row in fixture["dates"]:
        threshold=max(RR.KR_MIN_MISSING_NAMES,
                      int(np.ceil(row["activeNames"]*RR.KR_SYSTEMIC_MISSING_SHARE)))
        assert row["missingNames"] >= threshold
        assert .09 <= row["missingNames"]/row["activeNames"] <= .11


@pytest.mark.parametrize("held_ticker", ["024110.KS", "271560.KS"])
def test_observed_v9_held_gap_is_not_rejected_for_adjusted_vs_raw_basis(held_ticker):
    fixture=json.loads((Path(__file__).parent/"fixtures/replay-v9-actions-42-43.observed.json").read_text())
    observed=fixture["run42"]["systemicGap"]
    bridge_bps=observed["heldRejectedNames"][held_ticker]
    assert bridge_bps > RR.KR_BRIDGE_TOLERANCE_BPS
    assert bridge_bps < RR.KR_MAX_UNVOUCHED_ADJUSTMENT_BPS

    sessions=RC.sessions("2020-01-02","2020-01-10","KR")
    gap=sessions[2]
    tickers=[held_ticker]+[f"{i:06d}.KS" for i in range(19)]
    raw=pd.DataFrame({"Close":np.arange(len(sessions))+100.},index=sessions)
    adjusted=raw.copy()
    adjusted.loc[sessions[3]:,"Close"]*=1+bridge_bps/10000
    prices={ticker:adjusted.drop(gap).copy() for ticker in tickers}
    prices["^KS200"]=pd.DataFrame({"Close":200.},index=sessions)

    report=RR.recover_systemic_kr_gaps(
        prices,tickers,"^KS200",start="2020-01-02",through="2020-01-10",
        fetcher=lambda *args:raw,
        targeted_primary_fetcher=lambda *args:{},
        raw_primary_fetcher=lambda *args:{ticker:raw for ticker in tickers})

    target=next(row for row in report["accepted"] if row["ticker"]==held_ticker)
    assert target["method"]=="FDR_RAW_RETURN_WITH_OBSERVED_ADJUSTMENT_BOUNDS_LOWER_NAV"
    assert target["rawBridgeDifferenceBps"]==pytest.approx(0)
    assert target["pathUncertaintyBps"]==pytest.approx(bridge_bps)


def test_observed_run43_lineage_incident_requires_fdr_even_when_yahoo_is_newer(tmp_path):
    fixture=json.loads((Path(__file__).parent/"fixtures/replay-v9-actions-42-43.observed.json").read_text())
    incident=fixture["run43"]
    assert incident["selectedBenchmark"]["lastSession"] > incident["priorBenchmark"]["lastSession"]
    dates=pd.bdate_range("2020-01-01", periods=40)
    fdr=pd.Series(np.linspace(100,110,len(dates)-1),index=dates[:-1])
    yahoo=pd.Series(np.linspace(90,120,len(dates)),index=dates)

    chosen=BS.resolve_one(
        "^KS200", [{"kind":"fdr","symbol":"KS200"},
                    {"kind":"yahoo","symbol":"^KS200"}],
        start="2020-01-01", snapshot=None,
        pinned_source={"source":"fdr","symbol":"KS200"},
        fetchers={"fdr":lambda *_:fdr,"yahoo":lambda *_:yahoo})

    assert chosen["source"]==incident["priorBenchmark"]["source"]
    assert chosen["symbol"]==incident["priorBenchmark"]["symbol"]


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


def test_block_evidence_floor_does_not_authorize_a_gapped_nav_path():
    statuses=[{"status":"COMPLETE","reasons":[],"measured":True} for _ in range(9)]
    statuses.append({"status":"INCOMPLETE","reasons":["MISSING_PRICE_SESSION:A"]})
    cov=RV.coverage(statuses,90)
    assert cov["completenessPct"]==90
    assert cov["sufficientForBlockEvidence"]
    assert not cov["sufficientForContinuousPath"]
    assert not cov["sufficientForPath"]
    assert cov["continuousPathRequiredPct"]==100


def test_cash_and_stock_merger_values_held_position_without_buying_delisted_name():
    start,end="2018-12-17","2019-01-04"
    union=RC.sessions(start,end,"UNION")
    us=RC.sessions(start,end,"US")
    pre=us[us < pd.Timestamp("2018-12-20")]
    prices={
        "ESRX":pd.DataFrame({"Close":90.},index=pre),
        "CI":pd.DataFrame({"Close":180.},index=us),
        "SPY":pd.DataFrame({"Close":100.},index=us),
    }
    actions=RR.load_corporate_actions()
    view=RV.ValuationData(prices,{"US":"SPY"},pd.Series(1000.,index=union),
        [{"date":"2018-01-01","annualRatePct":0}],through=end,
        corporate_actions=actions)
    block={"date":start,"endDate":end,"signalDate":"2018-12-14"}
    decision={"weights":{"ESRX":1.0},"regionByTicker":{"ESRX":"US"}}
    row,status=view.window(decision,block)
    consideration=48.75+.2434*180
    assert status["status"]=="COMPLETE"
    assert row["grossReturn"]==pytest.approx(consideration/90-1)
    assert row["corporateActionsApplied"][0]["successorTicker"]=="CI"
    assert row["terminalRegionByTicker"]=={"CI":"US"}
    assert row["terminalWeights"]["CI"]==pytest.approx((.2434*180)/consideration)
    dead,dead_status=view.window(decision,{**block,"date":"2018-12-20"})
    assert dead is None and dead_status["status"]=="INCOMPLETE"


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
        through=view.through,calendar_rows=[],corporate_actions=RR.load_corporate_actions(),
        benchmark_lineage=[{"region":"KR","ticker":"^KS200","source":"fdr",
                            "symbol":"KS200","policy":"PINNED_FOR_GENERATION"}])
    store=RI.InputStore(tmp_path,"r","d")
    store.commit(data,through=view.through,policy={})
    frozen=RI.unpack(store.load())
    assert set(frozen["prices"])==set(view.prices)
    pd.testing.assert_series_equal(frozen["fx"],view.fx.rename("value"),check_freq=False,check_names=False)
    assert pd.isna(frozen["macro"].iloc[1,0])
    assert frozen["corporate_actions"]["version"]=="corporate-actions-v1"
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


def test_incomplete_audit_is_not_reported_as_a_blocked_report(monkeypatch, capsys):
    """A crashed audit and a blocked report must not share an exit code.

    The workflow can only read the exit code, and it decides from that whether
    to quote `ledger/historical-portfolio-validation.json` as this run's
    verdict. On the first replay-v10 run the audit died in `InputStore.load`
    and the workflow named replay-v9's `continuous_nav_has_unknown_intervals`
    as the reason — an entirely different generation's evidence.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "audit_portfolio", Path(__file__).resolve().parent.parent / "scripts" / "audit_portfolio.py")
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)

    monkeypatch.setattr(audit, "main", lambda argv=None: (_ for _ in ()).throw(KeyError("date")))
    assert audit.run([]) == audit.INCOMPLETE != audit.BLOCKED
    assert "wrote no validation report" in capsys.readouterr().err

    monkeypatch.setattr(audit, "main", lambda argv=None: audit.BLOCKED)
    assert audit.run([]) == audit.BLOCKED


def _yahoo_panel(closes, dividends=None, splits=None, volumes=None,
                 start="2020-01-01"):
    """A Yahoo `auto_adjust=False, actions=True` panel: split-adjusted bars.

    Split-adjusted in both directions — a 2:1 halves every earlier close AND
    doubles every earlier volume — which is why the caller states the volumes
    when it is modelling a split.
    """
    index = pd.bdate_range(start, periods=len(closes))
    return pd.DataFrame({"Open": closes, "High": closes, "Low": closes,
                         "Close": closes,
                         "Volume": volumes or [100.0] * len(closes),
                         "Dividends": dividends or [0.0] * len(closes),
                         "Stock Splits": splits or [0.0] * len(closes)}, index=index)


def test_forward_total_return_is_proportional_to_yahoos_backward_adjustment():
    """The basis change must move the level and nothing that is measured."""
    closes = [100.0, 101.0, 99.0, 102.0, 103.0]
    dividends = [0.0, 0.0, 1.0, 0.0, 0.0]
    frame = _yahoo_panel(closes, dividends)
    forward, events = PA.to_total_return(frame)

    # Yahoo's own back-anchored adjustment of the same rows.
    factor = 1 - dividends[2] / closes[1]
    backward = np.array([c * (factor if i < 2 else 1.0) for i, c in enumerate(closes)])

    ratio = forward["Close"].to_numpy() / backward
    assert np.allclose(ratio, ratio[0])          # one constant factor, no more
    assert [row["date"] for row in events] == ["2020-01-03"]
    assert events[0]["applied"] and events[0]["dividend"] == 1.0


def test_a_split_leaves_the_as_traded_close_and_the_index_continuous():
    """A 2:1 split halves every earlier close in Yahoo's panel, which is the
    other half of why the sealed prefix moves. Undoing it recovers the prices
    that printed — 100, 101, 102 before the split — and the index steps only by
    the day's real return."""
    frame = _yahoo_panel([50.0, 50.5, 51.0, 51.5, 52.0],
                         splits=[0.0, 0.0, 0.0, 2.0, 0.0],
                         volumes=[200.0, 200.0, 200.0, 100.0, 100.0])
    forward, events = PA.to_total_return(frame)
    close = forward["Close"].to_numpy()
    assert close == pytest.approx([100.0, 101.0, 102.0, 103.0, 104.0], rel=1e-12)
    assert close[3] / close[2] == pytest.approx(103.0 / 102.0, rel=1e-12)
    assert any(row.get("split") == 2.0 for row in events)


def test_a_dividend_paid_after_the_cutoff_cannot_rewrite_a_sealed_session(tmp_path):
    """The whole reason for the basis change, as the input store sees it.

    Yahoo's adjusted close rescales the published past on every ex-dividend, so
    `commit` refused every acquisition run after a generation's first one and
    replay v7..v10 each lasted one or two runs. On the as-traded forward basis
    the same event is an append.
    """
    closes = [100.0, 101.0, 102.0, 103.0]
    monday = _yahoo_panel(closes)
    # One day later the vendor reports the same sessions plus a fresh ex-date.
    tuesday = _yahoo_panel(closes + [104.0], dividends=[0.0] * 4 + [2.0])

    def pack(frame, through):
        rebased, _ = PA.to_total_return(frame)
        return RI.pack(prices={"A": rebased}, benchmarks={},
                       universe={"US": ["A"]},
                       universe_history=pit_data.UniverseHistory({}),
                       fundamentals=pit_data.FundamentalStore(), macro=None,
                       vix=None, vintages={}, fx=None,
                       rates={"events": [], "verifiedThrough": through},
                       through=through, calendar_rows=[])

    store = RI.InputStore(tmp_path, "r", "d")
    first = pack(monday, "2020-01-06")
    store.commit(first, through="2020-01-06", policy={})
    # Extending the cutoff over the new ex-date must be accepted, not refused.
    store.commit(pack(tuesday, "2020-01-07"), through="2020-01-07", policy={})

    sealed = store.load()
    assert [r["Close"] for r in sealed["price/2020-01"] if r["date"] <= "2020-01-06"] == \
           [r["Close"] for r in first["price/2020-01"]]
    assert sealed["corporate-events/2020-01"] == [
        {"date": "2020-01-07", "ticker": "A", "dividend": 2.0, "split": 1.0}]


def test_yahoos_adjusted_close_would_have_been_refused_by_the_same_store(tmp_path):
    """The control: the basis v10 sealed fails where the new one passes."""
    closes = [100.0, 101.0, 102.0, 103.0]
    factor = 1 - 2.0 / 103.0
    store = RI.InputStore(tmp_path, "r", "d")
    store.commit({"price/2020-01": [
        {"date": d, "ticker": "A", "Close": c}
        for d, c in zip(pd.bdate_range("2020-01-01", periods=4).strftime("%Y-%m-%d"), closes)]},
        through="2020-01-06", policy={})
    with pytest.raises(RI.InputVersionConflict, match="contradicts the sealed prefix"):
        store.commit({"price/2020-01": [
            {"date": d, "ticker": "A", "Close": c * factor}
            for d, c in zip(pd.bdate_range("2020-01-01", periods=4).strftime("%Y-%m-%d"), closes)]
            + [{"date": "2020-01-07", "ticker": "A", "Close": 104.0}]},
            through="2020-01-07", policy={})


def test_targeted_retry_window_is_per_gap_cluster_not_the_whole_span():
    """The retry that is meant to be focused must not span the generation.

    replay-v10 built one window from min(systemic) to max(systemic). On its
    first production run those were 2017-09-22 and 2025-09-19, so the "small
    window" became an eight-year bulk download of every affected name, twice —
    the same shape of request that dropped the rows. It reported
    targetedYahooRetries: 0.
    """
    sessions = RC.sessions("2020-01-02", "2020-06-30", "KR")
    early, late = sessions[3], sessions[80]
    tickers = [f"{i:06d}.KS" for i in range(20)]
    full = pd.DataFrame({"Close": np.arange(len(sessions)) + 100.}, index=sessions)
    prices = {ticker: full.drop([early, late]).copy() for ticker in tickers}
    prices["^KS200"] = pd.DataFrame({"Close": 200.}, index=sessions)

    windows = []

    def targeted(names, start, end):
        windows.append((start, end))
        return {ticker: full.copy() for ticker in names}

    report = RR.recover_systemic_kr_gaps(
        prices, tickers, "^KS200", start="2020-01-02", through="2020-06-30",
        fetcher=lambda *args: None, targeted_primary_fetcher=targeted,
        raw_primary_fetcher=lambda *args: {})

    assert len(windows) == 2, "one narrow window per market-wide gap cluster"
    for (start, end), day in zip(sorted(windows), (early, late)):
        assert pd.Timestamp(end) - pd.Timestamp(start) <= pd.Timedelta(days=29)
        assert pd.Timestamp(start) <= day <= pd.Timestamp(end)
    assert len(report["accepted"]) == 40 and not report["rejected"]
    assert all(prices[ticker].at[day, "Close"] == pytest.approx(full.at[day, "Close"])
               for ticker in tickers for day in (early, late))


def test_a_split_after_the_cutoff_cannot_rewrite_a_sealed_session(tmp_path):
    """The more violent half: a 2:1 split halves Yahoo's whole published past."""
    monday = _yahoo_panel([100.0, 101.0, 102.0, 103.0])
    tuesday = _yahoo_panel([50.0, 50.5, 51.0, 51.5, 26.0],
                           splits=[0.0, 0.0, 0.0, 0.0, 2.0],
                           volumes=[200.0, 200.0, 200.0, 200.0, 100.0])
    assert monday["Close"].tolist() != tuesday["Close"].tolist()[:4]
    assert monday["Volume"].tolist() != tuesday["Volume"].tolist()[:4]

    def sealed(frame):
        rebased, _ = PA.to_total_return(frame)
        return rebased["Close"].round(10).tolist()

    assert sealed(monday) == sealed(tuesday)[:4]

    store = RI.InputStore(tmp_path, "r", "d")
    for frame, through in ((monday, "2020-01-06"), (tuesday, "2020-01-07")):
        rebased, _ = PA.to_total_return(frame)
        store.commit(RI.pack(prices={"A": rebased}, benchmarks={},
                             universe={"US": ["A"]},
                             universe_history=pit_data.UniverseHistory({}),
                             fundamentals=pit_data.FundamentalStore(), macro=None,
                             vix=None, vintages={}, fx=None,
                             rates={"events": [], "verifiedThrough": through},
                             through=through, calendar_rows=[]),
                     through=through, policy={})
    assert store.load()["corporate-events/2020-01"] == [
        {"date": "2020-01-07", "ticker": "A", "dividend": 0.0, "split": 2.0}]
