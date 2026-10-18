"""Invented A0 inputs only; no actual population/price/label execution."""
import json

import pandas as pd
import pytest

from pipeline import experiment_workbench as W
from pipeline import replay_calendar as RC
from pipeline import rp1_a0 as A
from scripts import rp1_inspect_a0 as S


def annual(year, operating, *, cash=10, public=None):
    public = public or f"{year+1}-02-01"
    return {"ticker": "SYN", "id": f"SYN-{year}", "fiscalYear": year, "form": "10-K", "periodDays": 365,
        "periodEnd": f"{year}-12-31", "availableFrom": public, "acceptedDate": public + " 17:00:00",
        "statements": {"bs": [], "ic": [{"concept": "OperatingIncomeLoss", "unit": "usd", "value": operating},
            {"concept": "Revenues", "unit": "usd", "value": 100},
            {"concept": "NetIncomeLoss", "unit": "usd", "value": operating}],
            "cf": [{"concept": "NetCashProvidedByUsedInOperatingActivities", "unit": "usd", "value": cash}]}}


def test_h1_is_yoy_growth_cross_and_not_operating_income_level_cross():
    # Every operating-income level is positive. Growth falls below zero and
    # then rises above it; that event is distinct from Pattern B's level cross.
    records = [annual(2017, 100), annual(2018, 90), annual(2019, 110)]
    h = A.FilingHistory("SYN", records)
    assert h.at("2019-02-02")["flag"] is False
    assert h.at("2020-02-01")["flag"] is None  # same-day filing invisible; old report stale
    assert h.at("2020-02-01")["growth"] == pytest.approx(-0.1)
    state = h.at("2020-02-02")
    assert state["growth"] == pytest.approx(110 / 90 - 1)
    assert state["flag"] is True
    assert state["eventDate"] == "2020-02-02"
    assert state["fields"]["operatingMargin"] == pytest.approx(1.1)


def test_event_26_weeks_and_report_staleness_are_separate_guards():
    records = [annual(2017, 100), annual(2018, 90), annual(2019, 110)]
    h = A.FilingHistory("SYN", records)
    original = h.at("2020-02-02")
    # Isolate exact state retention from a later report's 180-day age guard.
    n = len(h.days)
    h.cache[n] = {**original, "periodEnd": "2020-06-30"}
    event = pd.Timestamp("2020-02-02")
    assert h.at(str((event + pd.Timedelta(weeks=26)).date()))["flag"] is True
    assert h.at(str((event + pd.Timedelta(weeks=26, days=1)).date()))["flag"] is False
    assert A.FilingHistory("SYN", records).at("2020-07-01")["reason"] == "REPORT_STALE_OVER_180_DAYS"


@pytest.mark.parametrize("cash", [0, -10])
def test_growth_cross_without_positive_cash_never_emits_event(cash):
    rows = [annual(2017, 100), annual(2018, 90), annual(2019, 110, cash=cash)]
    assert A.FilingHistory("SYN", rows).at("2020-02-02")["flag"] is False


def test_original_filing_future_mutation_and_pretax_fallback_cannot_create_event():
    rows = [annual(2017, 100), annual(2018, 90), annual(2019, 110)]
    baseline = A.FilingHistory("SYN", rows).at("2020-02-02")
    future = annual(2020, 999999)
    amended = annual(2019, -999999, public="2020-02-03")
    assert A.FilingHistory("SYN", rows + [future, amended]).at("2020-02-02") == baseline
    assert A.FilingHistory("SYN", rows + [amended]).at("2020-02-04")["growth"] == baseline["growth"]
    rows[-1]["statements"]["ic"][0]["concept"] = "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"
    assert A.FilingHistory("SYN", rows).at("2020-02-02")["flag"] is None


def test_nonpositive_base_and_missing_ttm_are_missing_not_zero():
    rows = [annual(2017, -10), annual(2018, -20), annual(2019, 110)]
    out = A.FilingHistory("SYN", rows).at("2020-02-02")
    assert out["flag"] is None and out["reason"] == "NON_POSITIVE_YOY_BASE"
    assert A.FilingHistory("SYN", []).at("2020-02-02")["flag"] is None


def test_past_price_prefix_and_benchmark_relative_sign_are_exact():
    days = RC.sessions("2018-01-01", "2020-12-31", "US")
    frames = {"SYN": pd.DataFrame({"Close": range(1, len(days)+1), "Volume": 100.0}, index=days),
              "SPY": pd.DataFrame({"Close": 100.0, "Volume": 100.0}, index=days)}
    day = str(days[260].date())
    baseline = A.PastPrices(frames, days).features("SYN", day)
    frames["SYN"].loc[frames["SYN"].index > day, "Close"] = 9999999
    assert A.PastPrices(frames, days).features("SYN", day) == baseline
    assert baseline["relative126"] == pytest.approx(261 / 135 - 1)
    assert A.h2(True, baseline["relative126"]) is True
    assert A.h2(True, -0.01) is False
    assert A.h2(None, 1) is None and A.h2(True, None) is None
    frames["SYN"].loc[day, "Close"] = None
    assert A.PastPrices(frames, days).features("SYN", day)["relative126"] is None


def sector_rows():
    return [{"ticker": f"S{sector}T{t}", "sector": str(sector), "size63": 100-t,
             "relative126": sector + t / 10} for sector in range(3) for t in range(5)]


def test_h3_uses_top_three_liquidity_and_all_peers_without_survivor_replacement():
    rows = sector_rows()
    flags = A.h3(rows)
    assert flags["S2T0"][0] is True
    assert flags["S2T3"][0] is False  # above its industry median
    assert flags["S0T0"][0] is False
    rows[0]["relative126"] = None
    assert all(f[0] is None for f in A.h3(rows).values())
    rows = sector_rows()
    rows[3]["size63"] = rows[2]["size63"]
    assert A.h3(rows)["S0T0"][1] == "LEADER_BOUNDARY_TIE_UNRESOLVED"


def observation(day="2020-01-03", ticker="SYN", flags=(1, 1, 0), *, eligible=True):
    source = W.Source("synthetic:filing", "a"*64, "SYNTHETIC", None, "NOT_RETAINED")
    values = {"financial."+h.replace("-","_"): v for h,v in zip(A.HYPOTHESES, flags)}
    values.update({"risk.size63": 100.0, "price.relative126": 0.1,
        "financial.delta_operatingMargin": 0.2, "financial.earningsGrowth": .3,
        "financial.accelerationComposite": .1})
    at = day + "T21:00:00Z"
    cells = tuple(W.Cell(k, float(v) if v is not None else None, "ratio", at if v is not None else None,
        source, None if v is not None else "INCOMPLETE_CHAIN") for k,v in values.items())
    return W.Observation(W.Key("US", day, "replay-v16:US:"+ticker), ticker, None,
        "PROVISIONAL" if eligible else "UNRESOLVED", at, "PUBLIC_RECONSTRUCTION", source,
        "2019-12-31T00:00:00Z", eligible, None if eligible else "KNOWN_IDENTITY_CONFLICT", "Industry", "RECONSTRUCTED", cells)


def test_population_missing_and_strata_reconcile_without_outcomes():
    rows = [observation(ticker=f"S{i}", flags=(int(i<10), int(i<10), int(i<10))) for i in range(30)]
    rows += [observation(ticker="MISSING", flags=(None,None,None)), observation(ticker="PARA", eligible=False)]
    report = A.measure(rows)
    for h in A.HYPOTHESES:
        x=report["hypotheses"][h]
        assert x["population"] == 32 and x["eligible"] == 31 and x["measured"] == 30 and x["events"] == 10
        assert sum(x["missing"].values()) + x["measured"] == x["eligible"]
        assert sum(x["strata"].values()) == x["measured"]
        assert x["mde"]["status"] == "MDE_UNRESOLVED"
        assert x["verdict"] != "PROCEED_TO_A1"
    assert all(k.count('|')==1 for k in report["hypotheses"]["A-H2"]["strata"])
    assert all(k.count('|')==2 for k in report["hypotheses"]["A-H1"]["strata"])
    assert json.dumps(A.measure(list(reversed(rows))),sort_keys=True) == json.dumps(report,sort_keys=True)
    with pytest.raises(ValueError,match="DUPLICATE"):
        A.measure(rows+[rows[0]])


def test_rank_biserial_ties_and_unidentified_binary_groups():
    assert A.rank_biserial([0,0,1,1],[1,2,3,4]) == 1
    assert A.rank_biserial([1,1,0,0],[1,2,3,4]) == -1
    assert A.rank_biserial([1,1],[1,2]) is None
    assert A.rank_biserial([0,1],[1,1]) == 0


def test_state_cells_cannot_accept_continuous_scores():
    with pytest.raises(ValueError,match='BINARY_EVENT_REQUIRED'):
        A.measure([observation(flags=(0.5,1,0))])


def test_no_go_even_when_synthetic_measurement_gates_pass_without_variance():
    rows=[observation(ticker=f"S{i}", flags=(int(i<10), int(i<10), int(i<10))) for i in range(30)]
    report=A.measure(rows)
    x=report['hypotheses']['A-H2']
    assert all(x['gates'][k] is True for k in ('prevalence','measurability','namesPerDate'))
    assert x['verdict']=='BLOCKED/UNRESOLVED' and x['gates']['mde'] is None
    assert report['a1Admission']=='NO_GO'


def test_preview_no_io_and_blocked_main_opens_no_inputs(monkeypatch, capsys):
    def forbidden(*a,**kw): raise AssertionError('UNAPPROVED_INPUT_OR_OUTCOME_ACCESS')
    monkeypatch.setattr(S,'contracts',forbidden)
    monkeypatch.setattr(S,'load_inputs',forbidden)
    assert S.main([])==0
    assert json.loads(capsys.readouterr().out)['status']=='PREVIEW_ONLY'
    assert S.inspect('.',admission={'status':'BLOCKED_PRECONDITIONS','blockers':['PR_256_NOT_MERGED']})['sourceInputsOpened']==0


def test_main_admission_never_passes_open_pr_or_stale_success():
    def github(path):
        if path.startswith('pulls/'): return {'merged': False}
        if path.startswith('git/'): return {'object':{'sha':'a'*40}}
        return {'workflow_runs':[{'head_sha':'b'*40,'conclusion':'success','event':'push'}]}
    result=S.main_admission(github=github)
    assert result['status']=='BLOCKED_PRECONDITIONS'
    assert len(result['blockers'])==3


def test_existing_contracts_and_population_bytes_remain_pinned():
    _,wp1,wp2=S.contracts()
    assert wp1['result']['studyABranch']['US']=='H252'
    assert wp2['daily']['selection']['selectedRule']=='R-b'


def test_outcome_spies_do_not_fire_for_signal_measurement(monkeypatch):
    from pipeline import winner_inflection_execution as E, winner_inflection_exploration as X, us_decision_pilot as P
    calls=[]
    def forbidden(*a,**kw): calls.append(True); raise AssertionError('OUTCOME_ACCESS')
    for obj,names in ((E,('outcome','label_cohorts','model_predictions','execute','economics')),
                      (X,('training_plan',)),(P,('simulate','metrics','label_reading')),(W,('LabelReference','Fold'))):
        for name in names: monkeypatch.setattr(obj,name,forbidden)
    report=A.measure([observation()])
    assert calls==[] and all(v==0 for v in report['accessCounters'].values())


def test_actual_adapter_rebuilds_same_wp2_mask_using_only_synthetic_inputs():
    from collections import defaultdict
    from types import SimpleNamespace
    from pipeline import rp1_us_universe as U
    from scripts import inspect_experiment_sources as B
    from scripts import rp1_inspect_us_universe as D
    tickers=[f'S{i}' for i in range(15)]+['PARA']
    sectors=['Industrials','Health Care','Information Technology']
    members=[{'date':'2019-01-01','sourceCommit':'synthetic','members':tickers}]
    industry=[{**members[0],'rows':{t:{'sector':sectors[i%3],'cik':'123'} for i,t in enumerate(tickers)}}]
    evidence={'rows':[[t,t+' Corp','123'] for t in tickers],
              'snapshots':[{'date':'2019-01-01','sourceCommit':'synthetic','rows':list(range(len(tickers)))}]}
    calendar=RC.sessions('2018-01-01','2020-03-20','US')
    frames={t:pd.DataFrame({'Close':[100+i+j/10 for j in range(len(calendar))], 'Volume':1000+i},index=calendar) for i,t in enumerate(tickers+['SPY'])}
    prices={t:{str(d.date()) for d in calendar} for t in tickers}
    filings=defaultdict(list)
    for t in tickers:
        filings[t]=[{**annual(y,op),'ticker':t,'cik':'123'} for y,op in [(2017,100),(2018,90),(2019,110)]]
    dates=['2020-03-06','2020-03-13']
    spec=json.loads((S.ROOT/D.SPEC).read_bytes())
    check=U.measure(members,industry,evidence,prices,[r for group in filings.values() for r in group],dates,spec,through='2020-03-20')
    receipts={B.CODE_BASE+':'+B.MEMBERS:{'sha256':'a'*64}, B.CODE_BASE+':'+B.SECTORS:{'sha256':'b'*64}}
    inputs=(SimpleNamespace(receipts=receipts),{'through':'2020-03-20'},frames,prices,members,industry,evidence,filings,calendar,dates)
    rows,details=S.observations(inputs,spec,{'weeklyCompatibility':{'sampleIdentity':check['sampleIdentity']}})
    assert len(rows)==32
    assert sum(r.investable is True for r in rows)==30
    assert all(r.identity_status=='UNRESOLVED' for r in rows if r.ticker=='PARA')
    measured=A.measure(rows,missing_details=details)
    assert measured['hypotheses']['A-H1']['events']==30
    assert measured['hypotheses']['A-H1']['measured']==30
    assert measured['eligibilityReasons']=={'KNOWN_IDENTITY_CONFLICT':2}
    assert all(c.available_at<=r.signal_at for r in rows for c in r.cells if c.value is not None)
    # The full source-derived population and hold mask is mandatory, not just
    # the survivors' count. A changed expected mask refuses the adapter.
    bad={'weeklyCompatibility':{'sampleIdentity':{}}}
    with pytest.raises(ValueError,match='POPULATION_OR_HOLD_MASK_CHANGED'):
        S.observations(inputs,spec,bad)
