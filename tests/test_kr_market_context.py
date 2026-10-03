from dataclasses import replace
import hashlib
import json
from pathlib import Path
import re

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
    # Check this workflow's explicit text contract, as other workflow tests do;
    # no YAML parser dependency is needed in the repository test environment.
    workflow=Path('.github/workflows/probes.yml').read_text()
    parts=re.split(r"(?m)^  ([\w-]+):\s*$",workflow.split('\njobs:\n',1)[1])
    jobs=dict(zip(parts[1::2],parts[2::2]))
    secret_jobs=[name for name,body in jobs.items() if 'secrets.ECOS' in body]
    assert secret_jobs==['ecos-market-context']
    assert workflow.count('secrets.ECOS')==1
    job=jobs['ecos-market-context']
    assert "    if: github.event_name == 'workflow_dispatch' && inputs.probe == 'ecos-market-context'\n" in job
    assert '          ECOS_API_KEY: ${{ secrets.ECOS }}\n' in job
    runs=re.findall(r"(?m)^        run: (.*)$",job)
    assert runs==['python scripts/probe_ecos_market_context.py --output "$RUNNER_TEMP/ecos/source-readiness.json"']
    assert 'tee' not in runs[0]
    assert job.count('      - uses: actions/upload-artifact@v4\n')==1
    upload=job.split('      - uses: actions/upload-artifact@v4\n',1)[1]
    assert re.findall(r"(?m)^          path: (.*)$",upload)==['${{ runner.temp }}/ecos/source-readiness.json']


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


def test_old_v1_seal_stays_immutable_and_refuses_new_ecos_closure(monkeypatch,tmp_path,capsys):
    from pipeline import alpha_opportunity_spec as S
    from scripts import run_alpha_opportunity_model as CLI
    spec=S.read_json(S.DEFAULT_SPEC)
    seal=S.DEFAULT_SPEC.with_suffix('.sha256').read_text().strip()
    assert seal==S.digest(spec)
    assert S.readiness(spec,seal)['verdict']=='BLOCKED_PREREGISTRATION'
    with pytest.raises(ValueError,match='SEALED_DEPENDENCY_CHANGED: pipeline/config.py'):
        S.load_sealed(expected_hash=seal)
    monkeypatch.setenv('GITHUB_REF','refs/heads/main')
    monkeypatch.setattr(CLI,'execute',lambda *a:pytest.fail('must never train'))
    monkeypatch.setattr(CLI,'verify_inputs',lambda *a:pytest.fail('must never load input'))
    for args in ([],['--execute','--reviewed','--input-root',str(tmp_path),'--output',str(tmp_path/'blocked')]):
        with pytest.raises(ValueError,match='SEALED_DEPENDENCY_CHANGED'):
            CLI.main(['--sealed-sha256',seal,*args])
    assert capsys.readouterr().out=='' and not (tmp_path/'blocked').exists()


def test_every_measurement_even_missing_spread_carries_information_contract():
    required={'value','change','acceleration','direction','source','observedThrough',
              'publishedAt','availableFrom','vintageStatus','coverage','status'}
    for axis in MC.state_at('2024-01-01')['axes'].values():
        for row in axis['measurements'].values():
            assert required <= row.keys()


def test_applied_ecos_artifact_matches_config_and_readiness_without_network(monkeypatch):
    from pipeline.config import load_config
    from scripts.audit_market_industry_stock_foundation import audit

    monkeypatch.setattr(P.EM, 'request', lambda *a, **k: pytest.fail('artifact application must be offline'))
    root = Path(__file__).resolve().parents[1]
    evidence = json.loads((root / 'research_specs/kr-market-context-ecos-evidence-37080934658.json').read_text())
    provenance = evidence['artifactProvenance']
    assert (provenance['runId'], provenance['artifactId']) == (37080934658, 11258377162)
    assert provenance['sourceHead'] == '6ebe13922e899b88e938f4f7aec7b8575ec47f34'
    assert provenance['artifactDigest'] == 'sha256:6a0f59e13737b55102cfd3bbdf31f812c19ce71e104a0fde9727d86dcbffb1b3'
    assert provenance['sourceReadinessJsonSha256'] == '8cfb15cdcbf88796831b2b2c7eb25d44ca411a8acf44a53512906dd7f32e6b07'
    cfg, _ = load_config(root / 'config.json')
    context = audit(root)['marketContextFoundation']
    readiness = {r['name']: r for r in context['ecosSeriesReadiness']}
    assert context['manualLiveValidation']['status'] == 'COMPLETED_SUCCESS'
    assert set(evidence['validatedConfig']) == {'KTB_3Y', 'LeadingIndex'}
    expected = {
        'KTB_3Y': ('817Y002', '010200000', 'D', '국고채(3년)', '연%', '19981113', '20261002', 6910),
        'LeadingIndex': ('901Y067', 'I16E', 'M', '선행지수순환변동치', '2020=100', '197001', '202608', 680),
    }
    assert len(evidence['series']) == len(readiness) == len(cfg.ecos_series) == 9
    for row in evidence['series']:
        name = row['name']
        matrix = readiness[name]
        applied = cfg.ecos_series[name]
        assert matrix['appliedConfig'] == applied
        assert applied['sourceStatus'] == matrix['sourceStatus'] == row['sourceStatus']
        assert applied['vintageStatus'] == matrix['vintageStatus'] == row['vintageStatus'] == 'REVISED_HISTORY'
        assert matrix['publishedAt'] is None and matrix['availableFrom'] is None
        assert not matrix['historicalConfirmatoryEligible']
        assert matrix['tableExists'] == row['tableExists'] and matrix['manualProbeExecuted']
        if name in expected:
            assert applied == evidence['validatedConfig'][name]
            assert tuple(applied[k] for k in ['seriesId', 'itemCode', 'cycle', 'itemName', 'unit']) + (
                matrix['earliestObservation'], matrix['latestObservation'], matrix['observationCount']) == expected[name]
            assert hashlib.sha256(json.dumps(row['selectedItems'], sort_keys=True, ensure_ascii=False).encode()).hexdigest() == applied['validationEvidenceSha256']
            assert matrix['semanticMatchVerified'] and row['smoke']['validObservationFound']
            P.EM.resolve_spec(name, applied, ecos_series=cfg.ecos_series)
        else:
            assert applied['itemCode'] is None and applied['cycle'] is None
            assert matrix['unit'] is None and matrix['earliestObservation'] is None
            assert not matrix['semanticMatchVerified'] and row['smoke'] is None
            with pytest.raises(P.EM.AmbiguousSeries):
                P.EM.resolve_spec(name, applied, ecos_series=cfg.ecos_series)
    assert readiness['Exports']['sourceStatus'] == 'NOT_AVAILABLE'
    assert not readiness['Exports']['tableExists']
    assert not evidence['historicalOutcomeComputed'] and not evidence['modelFitPerformed']


def test_retained_ecos_semantic_candidates_preserve_fail_closed_choices():
    root = Path(__file__).resolve().parents[1]
    evidence = json.loads((root / 'research_specs/kr-market-context-ecos-evidence-37080934658.json').read_text())
    for row in evidence['series']:
        selection, error = P.automatic_selection(row['name'], row['table'], row['semanticAndGroupCandidates'])
        if row['name'] in evidence['validatedConfig']:
            assert error is None
            selected, error = P.validate_selection(row['name'], selection, row['table'], row['semanticAndGroupCandidates'])
            assert error is None and selected == row['selectedItems']
        else:
            assert selection is None and error == row['sourceStatus']
