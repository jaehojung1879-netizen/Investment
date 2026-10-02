from dataclasses import replace
import json
from pathlib import Path

import pytest

from pipeline import kr_market_context as MC
from scripts import probe_ecos_market_context as P


def record(name="CPI",value=100,observed="2024-01-31",available="2024-02-10",fetched="2024-02-10",vintage="REVISED_HISTORY",source="ECOS:TEST"):
    return MC.Observation(name,value,observed,available,fetched,source,vintage,
                          source_status="LIVE_VALIDATED_SOURCE",unit="index",vintage_evidence="synthetic" if vintage=="PIT_EXACT" else None)


def measurement(state,name="CPI",axis="inflation"):
    return state["axes"][axis]["measurements"][name]


def test_six_axes_no_label_or_score():
    state=MC.state_at("2024-01-01")
    assert list(state["axes"]) == list(MC.AXES)
    assert len(state["axes"])==6 and state["region"]=="KR"
    assert not {"regime","score","weights","riskMultiplier","alpha","futureReturns"} & set(state)
    assert all(a["coverage"]["observed"]==0 for a in state["axes"].values())


def test_future_observation_publication_and_revised_fetch_excluded():
    rows=[record(),record(value=999,observed="2025-01-01",available="2025-01-02",fetched="2025-01-02")]
    assert measurement(MC.state_at("2024-02-09",rows))["value"] is None
    assert measurement(MC.state_at("2024-02-10",rows))["value"] ==100
    lagged=record(available="2024-02-10",fetched="2026-01-01")
    assert measurement(MC.state_at("2024-03-01",[lagged]))["value"] is None
    latest=measurement(MC.state_at("2026-01-01",[lagged]))
    assert latest["vintageStatus"]=="REVISED_HISTORY" and not latest["confirmatoryHistoricalEligible"]
    assert latest["knownFrom"]=="2026-01-01"


def test_backward_native_change_acceleration_and_missing():
    rows=[record(value=v,observed=f"2024-0{i}-01",available=f"2024-0{i}-02",fetched=f"2024-0{i}-02") for i,v in enumerate([100,102,105],1)]
    m=measurement(MC.state_at("2024-04-01",rows))
    assert (m["value"],m["change"],m["acceleration"],m["direction"]) ==(105,3,1,"UP")
    assert measurement(MC.state_at("2024-04-01",[record(value=None)]))["value"] is None


def test_revision_and_conflicting_identity():
    rows=[record(value=100),record(value=110,available="2024-03-01",fetched="2024-03-01")]
    assert measurement(MC.state_at("2024-02-15",rows))["value"]==100
    assert measurement(MC.state_at("2024-03-01",rows))["value"]==110
    with pytest.raises(ValueError,match="AMBIGUOUS"):
        MC.state_at("2024-03-01",[record(),record(value=101)])


def test_no_ecos_vintage_upgrade_or_outcome_name():
    with pytest.raises(ValueError,match="ECOS_IS_REVISED"):
        record(vintage="PIT_EXACT")
    with pytest.raises(ValueError,match="UNKNOWN_CONTEXT"):
        record(name="FutureIndustryReturn")
    with pytest.raises(ValueError,match="VINTAGE_EVIDENCE"):
        replace(record(source="FRED:T"),vintage_status="PIT_EXACT")


def test_spreads_require_aligned_observation_and_unit():
    rows=[replace(record(name="Korea_10Y",source="FRED:L",value=3),unit="percent"),
          replace(record(name="Korea_3M",source="FRED:S",value=2),unit="percent")]
    m=measurement(MC.state_at("2024-03-01",rows),"KR_TermSpread","domesticRates")
    assert m["value"]==1 and m["vintageStatus"]=="REVISED_HISTORY"
    rows[1]=replace(rows[1],observed_through="2024-01-30")
    assert measurement(MC.state_at("2024-03-01",rows),"KR_TermSpread","domesticRates")["value"] is None


def test_benchmark_reuses_existing_engine_and_requires_availability(monkeypatch):
    seen=[]
    def risk(frame,date):
        seen.append(date)
        return dict(status="READY",trendAdverse=True,benchmarkVol63=.3,availableThrough=date,riskMultiplier=.4)
    monkeypatch.setattr(MC,"equity_risk_state",risk)
    assert measurement(MC.state_at("2024-03-01",benchmark=object()),"KODEX200_Vol63","equityMarketState")["value"] is None
    state=MC.state_at("2024-03-01",benchmark=object(),benchmark_available_from="2024-02-29")
    assert seen==["2024-03-01"]
    assert "riskMultiplier" not in json.dumps(state)


def test_workflow_secret_is_manual_job_only_and_no_raw_upload():
    import yaml
    workflow=yaml.safe_load(Path('.github/workflows/probes.yml').read_text())
    jobs=workflow['jobs']
    secret_jobs=[]
    for name,job in jobs.items():
        if 'secrets.ECOS' in json.dumps(job):
            secret_jobs.append(name)
            assert "github.event_name == 'workflow_dispatch'" in job['if']
            env=job['steps'][2]['env']
            assert env['ECOS_API_KEY']=='${{ secrets.ECOS }}'
            assert 'tee' not in job['steps'][2]['run']
            assert job['steps'][3]['with']['path']=='${{ runner.temp }}/ecos/source-readiness.json'
    assert secret_jobs==['ecos-market-context']


def test_secret_guard_blocks_server_echo():
    with pytest.raises(ValueError,match="REDACTION"):
        P.safe_json({'candidateItems':[{'ITEM_NAME':'KEY_SECRET'}]},'KEY_SECRET')
    assert 'KEY_SECRET' not in P.safe_json({'sourceStatus':'REVISED_HISTORY'},'KEY_SECRET')


def test_semantic_native_metadata_validation_is_exact():
    table={'STAT_NAME':'시장금리','SRCH_YN':'Y'}
    items=[{'GRP_CODE':'Group1','ITEM_CODE':'G','ITEM_NAME':'국고채(3년)','CYCLE':'D','UNIT_NAME':'연%'}]
    chosen={'seriesId':'T','itemCode':'G','cycle':'D','semanticName':'KTB_3Y',
            'expectedItemNames':['국고채(3년)'],'expectedTableName':'시장금리','expectedUnit':'연%'}
    assert P.validate_selection('KTB_3Y',chosen,table,items)[1] is None
    assert P.validate_selection('KTB_3Y',{**chosen,'itemCode':'GUESS'},table,items)[1]=='AMBIGUOUS_SOURCE'
    assert P.validate_selection('KTB_3Y',{**chosen,'cycle':'M'},table,items)[1]=='DATA_LINEAGE_UNRESOLVED'
    assert P.validate_selection('KTB_3Y',{**chosen,'expectedUnit':'wrong'},table,items)[1]=='DATA_LINEAGE_UNRESOLVED'


def test_manual_guard_rejects_pr_before_network(monkeypatch,tmp_path):
    monkeypatch.setenv('GITHUB_EVENT_NAME','pull_request')
    monkeypatch.setenv('ECOS_MANUAL_PROBE','1')
    monkeypatch.setattr('sys.argv',['probe','--output',str(tmp_path/'out.json')])
    with pytest.raises(ValueError,match='MANUAL_WORKFLOW_REQUIRED'):
        P.main()
    assert not (tmp_path/'out.json').exists()


def test_auto_resolution_requires_unique_exact_semantics():
    table={'STAT_CODE':'T','STAT_NAME':'시장금리','SRCH_YN':'Y'}
    items=[{'GRP_CODE':'Group1','ITEM_CODE':'G','ITEM_NAME':'국고채(3년)','CYCLE':'D','UNIT_NAME':'연%'}]
    chosen,error=P.automatic_selection('KTB_3Y',table,items)
    assert error is None and chosen['itemCode']=='G' and chosen['cycle']=='D'
    assert P.automatic_selection('CorpBond_3Y',table,[{**items[0],'ITEM_NAME':'회사채(3년, AA-)'},
                                                  {**items[0],'ITEM_CODE':'B','ITEM_NAME':'회사채(3년, BBB-)'}])[1]=='AMBIGUOUS_SOURCE'
    assert P.automatic_selection('KTB_3Y',table,[{**items[0],'ITEM_NAME':'국고채(10년)'}])[0] is None


def test_native_ecos_frame_adapter_cannot_backdate_revised_history():
    import pandas as pd
    frame=pd.DataFrame({'CPI':{'202401':100.,'202403':999.}})
    config={'CPI':{'seriesId':'T','itemCode':'I','cycle':'M','unit':'index','sourceStatus':'LIVE_VALIDATED_SOURCE'}}
    rows=MC.ecos_records(frame,config,fetched_at='2024-03-10')
    assert len(rows)==1 and rows[0].observed_through=='2024-01-31'
    assert measurement(MC.state_at('2024-02-15',rows))['value'] is None
    assert measurement(MC.state_at('2024-03-10',rows))['value']==100


def test_probe_reports_metadata_and_smoke_without_values(monkeypatch):
    table={'STAT_CODE':'T','STAT_NAME':'시장금리','SRCH_YN':'Y','CYCLE':'D'}
    item={'STAT_CODE':'T','STAT_NAME':'시장금리','GRP_CODE':'Group1','ITEM_CODE':'G',
          'ITEM_NAME':'국고채(3년)','CYCLE':'D','UNIT_NAME':'연%','START_TIME':'20000101','END_TIME':'20240101','DATA_CNT':1}
    def meta(key,service,code=None):
        return ([table] if service=='StatisticTableList' else [item]),None
    def request(key,service,*parts):
        return {'StatisticSearch':{'row':[{'STAT_CODE':'T','ITEM_CODE1':'G','TIME':'20240101','DATA_VALUE':'12345.6789'}]}},None
    monkeypatch.setattr(P,'metadata',meta)
    monkeypatch.setattr(P.EM,'request',request)
    result=P.probe('SYNTHETIC_CREDENTIAL',{'KTB_3Y':{'seriesId':'T','itemCode':None,'cycle':None}})
    encoded=P.safe_json(result,'SYNTHETIC_CREDENTIAL')
    assert '12345.6789' not in encoded and 'DATA_VALUE' not in encoded
    assert result['series'][0]['sourceStatus']=='LIVE_VALIDATED_SOURCE'
    assert result['series'][0]['vintageStatus']=='REVISED_HISTORY'
    assert not result['series'][0]['historicalConfirmatoryEligible']
    assert result['validatedConfig']['KTB_3Y']['cycle']=='D'
    assert result['validatedConfig']['KTB_3Y']['unit']=='연%'
