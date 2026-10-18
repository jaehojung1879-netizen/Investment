"""Synthetic KR signals; frozen US input-report integrity, no real outcomes."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import types

import pandas as pd
import pytest

from pipeline import rp1_a0 as A, rp1_kr_a0 as K, prospective_receipt_core as CORE
from pipeline import experiment_workbench as W
from scripts import rp1_inspect_kr_a0 as S


def annual(year,op,*,cash=10,public=None,basis='CFS'):
    public=public or f'{year+1}-02-01'
    return {'id':f'SYN-{year}-{public}','ticker':'SYN.KS','fiscalYear':year,'reportCode':'11011',
        'availableFrom':public,'receiptNos':[public.replace('-','')+'000001'],'fsDiv':basis,
        'accounts':{a:{'statement':'CF' if a=='영업활동현금흐름' else 'IS',
                       'amounts':{'thstrm_amount':v}} for a,v in [('영업이익',op),('영업활동현금흐름',cash),('매출액',100)]}}


def history(rows):
    return A.FilingHistory('SYN.KS',rows,adapter=K.Filings())


def test_kr_growth_cross_public_next_day_not_level_cross():
    rows=[annual(2017,100),annual(2018,90),annual(2019,110)]
    assert history(rows).at('2020-02-01')['flag'] is None
    out=history(rows).at('2020-02-02')
    assert out['flag'] is True and out['eventDate']=='2020-02-02'
    assert out['growth']==pytest.approx(110/90-1)
    assert history(rows).at('2019-02-02')['flag'] is False


def test_corrections_and_future_filings_do_not_rewrite_original_event():
    rows=[annual(2017,100),annual(2018,90),annual(2019,110)]
    amendment=annual(2019,-999,public='2020-03-01')
    original=history(rows).at('2020-02-02')
    assert history(rows+[annual(2020,-999)]).at('2020-02-02')==original
    amended=history(rows+[amendment]).at('2020-03-02')
    assert amended['eventDate']==original['eventDate']  # known 26-week event retained
    assert amended['growth']==pytest.approx(-999/90-1)  # correction visible only on its own next day
    assert history(rows+[amendment]).at('2020-02-02')==original
    rows[-1]['receiptNos']=['20990101000001']
    assert history(rows).at('2020-02-02')['flag'] is None


@pytest.mark.parametrize('case,reason',[('missingop','OPERATING_INCOME_NOT_STATED'),('missingcash','OPERATING_CASH_FLOW_NOT_STATED'),
    ('mixed','STATEMENT_BASIS_CONFLICT'),('chain','INCOMPLETE_TTM_CHAIN'),('negativebase','NON_POSITIVE_YOY_BASE')])
def test_missing_causes_are_not_fabricated_zeroes(case,reason):
    rows=[annual(2017,100),annual(2018,90),annual(2019,110)]
    if case=='missingop':del rows[-1]['accounts']['영업이익']
    elif case=='missingcash':del rows[-1]['accounts']['영업활동현금흐름']
    elif case=='mixed':rows[-1]['fsDiv']='OFS'
    elif case=='chain':rows=rows[::2]
    elif case=='negativebase':rows[1]['accounts']['영업이익']['amounts']['thstrm_amount']=-1
    state=history(rows).at('2020-02-02')
    assert state['flag'] is None and state['reason']==reason


def test_retention_and_staleness_still_use_shared_engine():
    h=history([annual(2017,100),annual(2018,90),annual(2019,110)])
    state=h.at('2020-02-02');h.cache[len(h.days)]={**state,'periodEnd':'2020-06-30'}
    assert h.at('2020-08-02')['flag'] is True
    assert h.at('2020-08-03')['flag'] is False
    assert history([annual(2017,100),annual(2018,90),annual(2019,110)]).at('2020-07-01')['reason']=='REPORT_STALE_OVER_180_DAYS'


def kr_row(ticker='SYN.KS',day='2020-01-03',flag=1):
    source=W.Source('synthetic:KR','a'*64,'SYNTHETIC',None,'NOT_RETAINED');at=day+'T15:30:00+09:00'
    vals={'financial.A_H1':flag,'financial.A_H2':flag,'financial.A_H3':flag,'risk.marketCap':100.,
          'price.relative126':.1,'financial.C13_fundamentalAcceleration':.2}
    cells=tuple(W.Cell(k,float(v) if v is not None else None,'ratio',at if v is not None else None,source,
                      None if v is not None else 'INCOMPLETE_CHAIN') for k,v in vals.items())
    return W.Observation(W.Key('KR',day,'KRX:'+ticker),ticker,'DART:SYN','PROVISIONAL',at,'PUBLIC_RECONSTRUCTION',source,
                         '2019-12-31T00:00:00+09:00',True,None,'Sector','RECONSTRUCTED',cells)


def test_kr_original_five_names_gate_and_h2_stratum_exception():
    rows=[kr_row(f'S{i}.KS',flag=int(i<5)) for i in range(20)]
    d=A.measure(rows,market='KR',comparators=K.COMPARATORS,size_field='risk.marketCap')
    assert d['hypotheses']['A-H1']['gates']['namesPerDate'] is True
    assert d['hypotheses']['A-H1']['gates']['mde'] is None
    assert d['a1Admission']=='NO_GO'
    assert all(len(k.split(':S')[0].split('|'))==2 for k in d['hypotheses']['A-H2']['strata'])
    assert all(len(k.split(':S')[0].split('|'))==3 for k in d['hypotheses']['A-H1']['strata'])
    assert d['hypotheses']['A-H1']['gates']['distinctness'] is None
    # Diagnostic latest-52 counts never replace full-period formal gates.
    d['byDate']=d['byDate']*53
    out=K.diagnostics(d)
    assert out['LATEST_52_WEEKS']['dates']==52 and out['FULL_PERIOD']['dates']==53


def test_h3_kr_ranks_market_cap_not_us_liquidity_and_abstains_all_peer_gaps():
    rows=[{'ticker':f'S{s}-{t}','sector':str(s),'marketCap':100-t,'size63':t,'relative126':s+t/10}
          for s in range(3) for t in range(5)]
    assert A.h3(rows,size_field='marketCap')['S2-0'][0] is True
    rows[0]['relative126']=None
    assert all(v[0] is None for v in A.h3(rows,size_field='marketCap').values())
    rows[0]['relative126']=0;rows[0]['marketCap']=None
    assert all(v[0] is None for v in A.h3(rows,size_field='marketCap').values())


def test_kr_uses_kodex_benchmark_and_future_price_poison_does_not_change_inputs():
    from pipeline import replay_calendar as RC
    days=RC.sessions('2018-01-01','2020-12-31','KR')
    frames={'SYN.KS':pd.DataFrame({'Close':range(1,len(days)+1),'Volume':100.},index=days),
            '069500.KS':pd.DataFrame({'Close':100.,'Volume':100.},index=days)}
    day=str(days[200].date())
    expected=A.PastPrices(frames,days,benchmark='069500.KS').features('SYN.KS',day)
    assert expected['relative126']==pytest.approx(201/75-1)
    frames['SYN.KS'].loc[frames['SYN.KS'].index>day,'Close']=9999999
    frames['069500.KS'].loc[frames['069500.KS'].index>day,'Close']=1
    assert A.PastPrices(frames,days,benchmark='069500.KS').features('SYN.KS',day)==expected


def eligible_row(ticker,**kw):
    return {'ticker':ticker,'issuerId':'DART:SYN','sector':'AUTOS','industry':'AUTOS','isPreferredShare':False,
            'priceAsOf':'2020-01-03','positiveVolumeSessions20':20,'medianTradedValue60Krw':1e9,**kw}


def test_original_h2_eligibility_identity_finance_and_industry_floor():
    rows=[eligible_row(f'S{i}') for i in range(5)]
    assert all(not r for r in K.eligibility(rows,'2020-01-03').values())
    rows[0]['sector']='FINANCIALS'
    out=K.eligibility(rows,'2020-01-03')
    assert out['S0'][0]=='DEFINITIONALLY_EXCLUDED_FINANCIAL'
    assert out['S1']==['INDUSTRY_BELOW_MIN_MEMBERS']
    rows[0]['sector']='AUTOS';rows[0]['issuerId']=None
    assert K.eligibility(rows,'2020-01-03')['S0'][0]=='IDENTITY_UNRESOLVED'


def test_wp6_preview_has_original_unknowns_mapping_and_no_backdating_or_writer(monkeypatch):
    monkeypatch.setattr(CORE,'system_utc_now',lambda:pd.Timestamp('2020-01-03T10:00:00Z'))
    row=kr_row(flag=None)
    args={'merged_at_utc':'2020-01-01T00:00:00Z','spec_sha256':'a'*64,'code_hashes':{'synthetic.py':'b'*64},
          'input_sha256':'c'*64,'reasons':dict.fromkeys(A.HYPOTHESES,'NO_VISIBLE_FILING'),
          'strata':K.stratum_identities([row])[row.key.sample_id]}
    preview=K.receipt_preview(row,**args)
    assert preview['states']['A-H1']=={'value':None,'unknownReason':'NO_VISIBLE_FILING'}
    assert preview['sampleId']==row.key.sample_id and preview['ledgerWrites']==0
    assert preview['mode']=='PREVIEW_ONLY_NOT_A_RECEIPT' and 'A2_NOT_AUTHORIZED' in preview['blockers']
    assert CORE.receipt_digest({k:v for k,v in preview.items() if k!='previewSha256'})==preview['previewSha256']
    monkeypatch.setattr(CORE,'system_utc_now',lambda:pd.Timestamp('2020-01-06T01:00:00Z'))
    assert 'RECEIPT_CREATED_AFTER_EXECUTION_OPEN_BACKDATED' in K.receipt_preview(row,**args)['blockers']
    monkeypatch.setattr(CORE,'append',lambda *a,**k:pytest.fail('LEDGER_WRITE'))
    K.receipt_preview(row,**args)


def test_no_outcomes_in_observation_and_no_input_access_before_admission(monkeypatch):
    monkeypatch.setattr(S,'load_inputs',lambda *a:pytest.fail('INPUT_OPENED'))
    result=S.guarded_inspect(Path('.'),main_admission={'status':'BLOCKED_PRECONDITIONS'})
    assert result['sourceInputsOpened']==0 and result['resultAccessSpies']['forbiddenAccessCalls']==0
    with pytest.raises(ValueError,match='DUPLICATE'):
        A.measure([kr_row(),kr_row()],market='KR')


def test_us_original_engine_golden_default_behavior_is_byte_equal():
    # Frozen CODE, not a new US study/result. Synthetic independent panels go
    # through the entire old and generalized default measurement functions.
    from tests.test_rp1_a0 import observation, annual as us_annual
    raw=subprocess.check_output(['git','show','a3021f361d339ef53d3109049b47607db3293d3e:pipeline/rp1_a0.py'])
    old=types.ModuleType('pipeline._rp1_us_golden');old.__package__='pipeline';exec(compile(raw,'frozen-us-a0','exec'),old.__dict__)
    rows=[observation(ticker=f'S{i}',flags=(int(i<10),None if i%4==0 else int(i<10),int(i<3))) for i in range(30)]
    assert CORE.canonical(A.measure(rows))==CORE.canonical(old.measure(rows))
    records=[us_annual(2017,100),us_annual(2018,90),us_annual(2019,110)]
    for day in ('2019-02-02','2020-02-01','2020-02-02','2020-07-01'):
        assert A.FilingHistory('SYN',deepcopy(records)).at(day)==old.FilingHistory('SYN',deepcopy(records)).at(day)
    assert A.h3([])==old.h3([])
    assert hashlib.sha256((S.ROOT/S.US_RESULT).read_bytes()).hexdigest()==S.US_SHA


def test_preview_default_opens_no_real_data(capsys,monkeypatch):
    monkeypatch.setattr(S,'guarded_inspect',lambda *a,**k:pytest.fail('REAL_DATA'))
    assert S.main([])==0
    assert json.loads(capsys.readouterr().out)['sourceInputsOpened']==0


def test_kr_adapter_end_to_end_synthetic_population_and_strata(monkeypatch):
    from types import SimpleNamespace
    from pipeline import replay_calendar as RC, regional_alpha_features as RAF
    calendar=RC.sessions('2018-01-01','2020-06-30','KR');day='2020-06-12'
    tickers=[f'S{s}{i}.KS' for s in range(3) for i in range(5)]
    members=RAF.MembershipSnapshots([{'date':'2020-06-01','members':tickers,
        'rows':{t:{'name':'합성기업'} for t in tickers}}])
    frames={t:pd.DataFrame({'Close':100.+pd.Series(range(len(calendar)),index=calendar)*(i+1)/100,
                          'Volume':1000.},index=calendar) for i,t in enumerate(tickers)}
    frames['069500.KS']=pd.DataFrame({'Close':100.,'Volume':1000.},index=calendar)
    class Bars:
        def __init__(self,i):self.i=i
        def quote(self,d):return {'marketCap':1e12-self.i*1e9}
        def features_at(self,d):return {'E04_tradabilityGuard20':20,'E03_capacityMedianTradedValue60':1e10},{}
        def basis_cause(self,d,n):return None
    monkeypatch.setattr(S.S.KI,'industry_of',lambda iv,cw,t,d:('I'+t[1],'RECONSTRUCTED_STABLE_NO_CHANGE_EVENT'))
    filings={t:[{**annual(y,o),'ticker':t} for y,o in [(2017,100),(2018,90),(2019,110)]] for t in tickers}
    inputs=(SimpleNamespace(receipts={}),{},members,frames,{t:Bars(i) for i,t in enumerate(tickers)},filings,
            {t:('DART:'+t,'KRX:'+t) for t in tickers},{},{},{},calendar,[day],0)
    rows,details,reasons=S.observations(inputs)
    assert len(rows)==15 and all(o.investable for o in rows) and not reasons
    assert all(o.key.market=='KR' and CORE.utc(o.signal_at).tz_convert('Asia/Seoul').hour==18 for o in rows)
    report=A.measure(rows,market='KR',comparators=K.COMPARATORS,size_field='risk.marketCap',missing_details=details)
    for h in A.HYPOTHESES:
        assert report['hypotheses'][h]['measured']==15
    assert report['hypotheses']['A-H1']['events']==15
    original=CORE.canonical(report)
    for f in frames.values():f.loc[f.index>day,'Close']=999999
    poisoned,details,_=S.observations(inputs)
    assert CORE.canonical(A.measure(poisoned,market='KR',comparators=K.COMPARATORS,size_field='risk.marketCap',missing_details=details))==original
    identity=K.stratum_identities(rows)
    assert all(identity[o.key.sample_id]['A-H2'].count('|')==1 for o in rows)
    assert all(identity[o.key.sample_id]['A-H1'].count('|')==2 for o in rows)


def test_kr_c13_uses_latest_visible_correction_and_exact_previous_period():
    def q3(year,op):
        row=annual(year,op,public=f'{year}-11-01');row['reportCode']='11014'
        for name,v in [('영업이익',op),('매출액',75)]:row['accounts'][name]['amounts']['thstrm_add_amount']=v
        return row
    rows=[annual(2017,100),q3(2018,60),annual(2018,90),q3(2019,70),annual(2019,110)]
    before=history(rows).at('2020-02-02')
    assert before['deltas']['operatingMargin']==pytest.approx(.1)
    correction=annual(2019,140,public='2020-03-01')
    after=history(rows+[correction]).at('2020-03-02')
    assert after['deltas']['operatingMargin']==pytest.approx(.4)
    assert history(rows+[correction]).at('2020-02-02')==before


def test_raw_allowlist_and_unmeasured_denominators_remain_explicit():
    reader=S.S.Sources(S.ROOT)
    with pytest.raises(ValueError,match='OUTSIDE_RAW_INPUT_ALLOWLIST'):
        reader.blob(S.S.SOURCE_COMMIT,'ledger/outcomes.jsonl')
    row=kr_row(flag=None)
    report=A.measure([row],market='KR',comparators=K.COMPARATORS,size_field='risk.marketCap')
    h=report['hypotheses']['A-H1']
    assert h['measured']==0 and h['missing']=={'INCOMPLETE_CHAIN':1}
    assert h['prevalence'] is None and report['byDate'][0]['hypotheses']['A-H1']['events'] is None
    assert K.diagnostics(report)['LATEST_52_WEEKS']['hypotheses']['A-H1']['events'] is None


def test_whole_kr_report_reconciles_and_scans_without_real_sources(monkeypatch):
    from types import SimpleNamespace
    row=kr_row(flag=None)
    fake=(SimpleNamespace(receipts={}),None,None,None,None,{'SYN.KS':[annual(2019,10,basis=None)]},
          None,None,None,{'terminalSecurities':['SYN.KS']},None,None,0)
    monkeypatch.setattr(S,'validate_contracts',lambda root:json.loads((S.ROOT/S.SPEC).read_bytes()))
    monkeypatch.setattr(S,'load_inputs',lambda repo:fake)
    monkeypatch.setattr(S,'observations',lambda data:([row],{row.key.sample_id:dict.fromkeys(A.HYPOTHESES,'NO_VISIBLE_FILING')},{}))
    result=S.guarded_inspect(S.ROOT,main_admission={'status':'ADMITTED'})
    S.US.U.scan_output(result)
    assert result['historicalInferenceEligibility']=='GOVERNANCE_CLOSED'
    assert result['sourceAvailability']['filingObservedRange'] is None
    assert result['sourceAvailability']['filingObservedAtMissing']==1
    assert result['sourceAvailability']['statementBasisRecords']=={'UNKNOWN':1}
    assert result['populationAudit']['groups']['terminal:KNOWN_TERMINAL']['population']==1
    assert result['resultAccessSpies']['forbiddenAccessCalls']==0
    assert len(result['resultAccessSpies']['calls'])==11
    h=result['hypotheses']['A-H1']
    assert h['measured']+sum(h['missing'].values())==h['eligible']
    assert result['latest52IsFormalGate'] is False


def test_registered_holdings_industry_is_not_a_portfolio_guard_bypass():
    from dataclasses import replace
    row=replace(kr_row(),industry_id='HOLDINGS_BUSINESS_SERVICES')
    report=A.measure([row],market='KR',comparators=K.COMPARATORS,size_field='risk.marketCap')
    before=CORE.canonical(report)
    S.CORE_SCAN(report)
    assert CORE.canonical(report)==before  # retain exact taxonomy, no renaming in result
    bad=deepcopy(report);bad['holdings']={'SYN':1}
    with pytest.raises(ValueError,match='FORBIDDEN_OUTPUT_KEY'):
        S.CORE_SCAN(bad)
    bad=deepcopy(report);bad['hypotheses']['A-H1']['strata']={'HOLDINGS_BUSINESS_SERVICES|0|0:S1':{'nav':1}}
    with pytest.raises(ValueError,match='INVALID_REGISTERED_KR_STRATUM'):
        S.CORE_SCAN(bad)


def test_committed_kr_measurement_receipt_is_exact_and_reconciles():
    path=S.ROOT/'docs/research-program/results/rp1-kr-a0-measurability-v1.json'
    raw=path.read_bytes()
    assert hashlib.sha256(raw).hexdigest()=='5f20f8d9ba4278282fea9537e47e79b8af9228e31cd7e4b2e225634d9a2f39b3'
    report=json.loads(raw)
    S.CORE_SCAN(report)
    assert len(report['byDate'])==714
    assert sum(d['population'] for d in report['byDate'])==85680
    assert sum(d['eligible'] for d in report['byDate'])==50462
    assert sum(report['eligibilityReasons'].values())+50462==85680
    for h,r in report['hypotheses'].items():
        assert r['measured']+sum(r['missing'].values())==r['eligible']
        assert sum(r['strata'].values())==r['measured']
        assert sum(d['hypotheses'][h]['measured'] for d in report['byDate'])==r['measured']
        assert r['verdict']=='PROSPECTIVE_ONLY' and r['gates']['measurability'] is False
        assert r['mde']['status']=='MDE_UNRESOLVED'
    assert report['diagnostics']['LATEST_52_WEEKS']['dates']==52
    assert report['latest52IsFormalGate'] is False and report['a1Admission']=='GOVERNANCE_CLOSED'
    assert report['resultAccessSpies']['forbiddenAccessCalls']==0
    assert all(x==0 for x in report['accessCounters'].values())
    assert hashlib.sha256((S.ROOT/S.US_RESULT).read_bytes()).hexdigest()==S.US_SHA
