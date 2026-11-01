"""Focused synthetic accounting regressions; not source investment certification."""
import copy
import datetime as dt
import json
from pathlib import Path

import pytest

from .core import add_months, compare, summary, validate, window_readout


def path(nav=None, **kw):
    p={'region':'KR','strategyId':'S','studyId':'synthetic-test-not-research','currency':'KRW',
       'frequency':'WEEKLY','returnBasis':'SYNTHETIC','costBasis':'NET_ALREADY_CHARGED',
       'evidenceClass':'SYNTHETIC_FIXTURE','sourceCommit':'0'*40,'hashes':{'fixture':'0'*64},
       'nav':nav or [['2020-01-03',1.],['2020-01-10',1.01]]}
    return {**p,**kw}


def weekly(years=2):
    d=dt.date(2020,1,3)
    return [[(d+dt.timedelta(days=7*i)).isoformat(), 1.001**i] for i in range(52*years+1)]


def test_percent_units_and_net_path_is_not_charged_again():
    r,_=compare(path(),path(strategyId='ETF'), '2020-12-31')
    assert r['scopes']['FULL']['candidate']['cumulativeReturnPct']==pytest.approx(1.)
    assert r['scopes']['FULL']['cagrGapPp']==0
    assert r['exactAdditionalCostStress'] is None


def test_weekly_not_daily_sessions_or_daily_drawdown():
    p=path(weekly());r,_=compare(p,p,'2023-01-01')
    assert r['dailyMdd']=='UNAVAILABLE'
    assert r['scopes']['FULL']['windows']['H126']['status']=='UNAVAILABLE'
    assert r['scopes']['FULL']['windows']['CALENDAR_6M']['measuredWindows']>0


def test_calendar_months_are_not_26_rows_and_endpoint_is_explicit():
    points=weekly();ds=[r[0] for r in points];v=dict(points)
    s,rs=window_readout(ds,v,v,6,dt.date(2023,1,1))
    assert rs[0]['calendarTargetDate']=='2020-07-03'
    assert rs[0]['observedEndDate']=='2020-07-03'
    assert sum(s['statusCounts'].values())==len(points)
    # Different origins have a calendar-dependent number of observations.
    assert add_months(dt.date(2020,8,31),6)==dt.date(2021,2,28)


@pytest.mark.parametrize('changes',[{'currency':'USD'},{'region':'US'},{'frequency':'DAILY'}])
def test_pair_cannot_mix_currency_region_or_frequency(changes):
    with pytest.raises(ValueError,match='INCOMPARABLE'):compare(path(),path(**changes),'2021-01-01')


def test_missing_date_not_inner_joined_and_no_funded_gap_chaining():
    rows=weekly();a=path(rows);b=path(rows[:20]+rows[21:])
    r,_=compare(a,b,'2023-01-01')
    assert r['schedule']['origins']==len(rows)
    assert r['schedule']['missingBenchmarkDates']==[rows[20][0]]
    assert r['scopes']['FULL']['candidate'] is None
    assert r['scopes']['FULL']['windows']['CALENDAR_6M']['statusCounts']['MISSING_OR_GAPPED_PAIRED_PATH']>0


def test_common_missing_week_not_hidden_by_union():
    rows=weekly();rows=rows[:20]+rows[21:];r,_=compare(path(rows),path(rows),'2023-01-01')
    assert r['schedule']['gapDates']
    assert r['scopes']['FULL']['candidate'] is None


def test_missing_is_not_zero_return():
    rows=weekly();rows[10][1]=None;r,_=compare(path(rows),path(weekly()),'2023-01-01')
    assert r['scopes']['FULL']['candidate'] is None
    assert r['investmentConclusion']=='INSUFFICIENT_SOURCE_EVIDENCE_NO_PROMOTION'


@pytest.mark.parametrize('nav',[[['2020-01-03',1],['2020-01-03',2]],
                                [['2020-01-10',1],['2020-01-03',2]],
                                [['2020-01-03',1],['2020-01-10',float('nan')]],
                                [['2020-01-03',1],['2020-01-10',0]]])
def test_duplicate_unsorted_nonfinite_zero_not_silently_coerced(nav):
    with pytest.raises(ValueError):validate(path(nav))


def test_missing_contract_rejected():
    p=path();del p['studyId']
    with pytest.raises(ValueError):validate(p)


def test_maturity_versus_mature_unobserved_endpoint():
    rows=weekly(1);ds=[x[0] for x in rows];v=dict(rows)
    s,_=window_readout(ds,v,v,12,dt.date(2020,12,31))
    assert s['statusCounts']['IMMATURE_AT_AS_OF']>0
    s,_=window_readout(ds,v,v,12,dt.date(2022,12,31))
    assert s['statusCounts']['MATURE_TARGET_NO_STORED_ENDPOINT']>0
    assert s['meanExcessReturnPp'] is None


def test_unrecovered_drawdown_not_zero_recovery_time():
    s=summary(['2020-01-01','2020-01-02','2020-01-03'],[1,.5,.75])
    assert s['observedMddPct']==-50
    assert s['recovery']['recoveryDate'] is None
    assert s['recovery']['peakToRecoveryCalendarDays'] is None


def test_recovered_drawdown_peak_to_recovery():
    s=summary(['2020-01-01','2020-01-02','2020-01-03'],[1,.5,1])
    assert s['recovery']['peakToRecoveryCalendarDays']==2


def test_unknown_cost_basis_never_net_certified():
    r,_=compare(path(costBasis='UNKNOWN'),path(),'2021-01-01')
    assert 'NET_STATUS_UNPROVEN' in r['excessLabel']
    assert r['investmentConclusion']=='INSUFFICIENT_SOURCE_EVIDENCE_NO_PROMOTION'


def test_nonoverlap_count_not_inflated_by_rolling_windows():
    r,_=compare(path(weekly(3)),path(weekly(3)),'2024-01-01')
    s=r['scopes']['FULL']['windows']['CALENDAR_6M']
    assert s['measuredWindows']>10*s['disjointTimeWindowCount']


def test_daily_verified_h126_uses_transitions():
    import exchange_calendars as xc
    dates=[x.strftime('%Y-%m-%d') for x in xc.get_calendar('XKRX',start='2020-01-01',end='2022-12-31').sessions]
    p=path([[d,1.001**i] for i,d in enumerate(dates)], frequency='DAILY',calendarPolicy='XKRX')
    r,w=compare(p,p,'2023-01-01')
    assert r['pairedCalendar']['verified']
    assert w['FULL/H126'][0]['observedEndDate']==dates[126]
    assert r['scopes']['FULL']['windows']['H126']['measuredWindows']==len(dates)-126


def test_daily_missing_session_cannot_be_relabelled_h126():
    import exchange_calendars as xc
    dates=[x.strftime('%Y-%m-%d') for x in xc.get_calendar('XKRX',start='2020-01-01',end='2021-12-31').sessions]
    dates.pop(20);p=path([[d,1] for d in dates],frequency='DAILY',calendarPolicy='XKRX')
    r,_=compare(p,p,'2023-01-01')
    assert not r['pairedCalendar']['verified']
    assert r['scopes']['FULL']['windows']['H126']['status']=='UNAVAILABLE'
    assert r['schedule']['missingCandidateDates']


def test_fixed_split_crossing_not_claimed_source_missing():
    r,_=compare(path(weekly(3)),path(weekly(3)),'2024-01-01')
    assert r['scopes']['FIRST_EQUAL_TIME_HALF']['windows']['CALENDAR_6M']['statusCounts']['CROSSES_FIXED_TIME_SPLIT']>0


def test_equal_source_paths_equal_returns_with_scaled_capital():
    a=path(weekly());b=copy.deepcopy(a);b['nav']=[[d,v*50_000_000] for d,v in b['nav']]
    r,_=compare(a,b,'2023-01-01')
    assert r['scopes']['FULL']['cagrGapPp']==pytest.approx(0,abs=1e-10)


def test_saved_real_results_retain_all_sources_and_weekly_limits():
    p=Path(__file__).with_name('results.json')
    if not p.exists():pytest.skip('Derived real outputs not built')
    r=json.loads(p.read_text())
    assert len(r['comparisons'])==12 and len(r['blockedComparisons'])==90
    for x in r['comparisons']:
        assert x['candidateInput']['costBasis']=='NET_ALREADY_CHARGED'
        if x['id'].startswith('A/'):
            assert x['candidateInput']['currency']=='KRW'
            assert x['scopes']['FULL']['windows']['H126']['status']=='UNAVAILABLE'
        for scope in x['scopes'].values():
            if 'windows' in scope:
                for w in scope['windows'].values():
                    if 'scheduledOrigins' in w:assert sum(w['statusCounts'].values())==w['scheduledOrigins']


def test_percent_return_input_not_mistaken_for_nav_levels():
    with pytest.raises(ValueError,match='NAV_LEVELS_REQUIRED'):
        validate(path(valueType='RETURNS_PCT'))


def test_hash_is_not_an_empty_metadata_placeholder():
    with pytest.raises(ValueError,match='INVALID_SOURCE_HASH'):
        validate(path(hashes={'file':'not-a-hash'}))


def test_no_measured_windows_are_none_not_zero():
    ds=['2020-01-03','2020-01-10'];v={x:1 for x in ds}
    s,_=window_readout(ds,v,v,6,dt.date(2020,1,11))
    assert s['measuredWindows']==0
    assert s['meanExcessReturnPp'] is None and s['winRatePct'] is None


def test_output_cannot_overwrite_original_or_producer_files(tmp_path):
    from .cli import guard_output
    from .adapters import HERE
    for p in [HERE.parents[1]/'docs/weekly-decision/weekly-passive-first-v1-replay-corrected-benchmark.json',
              HERE/'source-pins.json', HERE/'readout-plan.json', HERE/'core.py']:
        with pytest.raises(ValueError):guard_output(p)
    guard_output(tmp_path/'derived.json')
    with pytest.raises(ValueError):guard_output(tmp_path/'input.json',tmp_path/'input.json')


def test_currency_unit_scaling_does_not_invent_winning_windows():
    a=path(weekly());b=copy.deepcopy(a);b['nav']=[[d,v*50_000_000] for d,v in b['nav']]
    r,_=compare(a,b,'2023-01-01')
    w=r['scopes']['FULL']['windows']['CALENDAR_6M']
    assert w['winRatePct']==0 and w['lossWindowCount']==0
    assert w['tieWindowCount']==w['measuredWindows']


def test_explicit_qqq_is_separate_pair_not_a_spy_substitute(tmp_path,monkeypatch):
    import sys
    from .cli import main
    a=path(region='US',currency='USD');b=path(region='US',currency='USD',instrument='QQQ',strategyId='QQQ')
    source=tmp_path/'input.json';source.write_text(json.dumps({'asOfDate':'2021-01-01','candidate':a,'benchmark':b}))
    out=tmp_path/'out.json';monkeypatch.setattr(sys,'argv',['readout','--input',str(source),'--out',str(out)])
    main();result=json.loads(out.read_text())
    assert result['QQQ']['status']=='PROVIDED_AS_SEPARATE_PAIR'
    assert result['comparisons'][0]['benchmarkInput']['instrument']=='QQQ'
