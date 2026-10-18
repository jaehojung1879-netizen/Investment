"""KR A0. Default preview opens nothing; --inspect reads fixed LOCAL inputs.

No network collection, historical outcomes, automatic repair or ledger writer.
A successful current-main Tests run and merged WP1/WP5 are checked first.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch
from contextlib import ExitStack

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import experiment_workbench as W  # noqa: E402
from pipeline import kr_alpha_atlas_bars as B  # noqa: E402
from pipeline import kr_continuing_dividend_sample as COMMON  # noqa: E402
from pipeline import krx_prices as KP  # noqa: E402
from pipeline import replay_inputs as RI  # noqa: E402
from pipeline import rp1_a0 as A  # noqa: E402
from pipeline import rp1_kr_a0 as K  # noqa: E402
from scripts import inspect_experiment_sources as S  # noqa: E402
from scripts import rp1_inspect_a0 as US  # noqa: E402

SPEC = 'docs/research-program/specs/rp1-kr-a0-measurability-v1.json'
US_RESULT = 'docs/research-program/results/rp1-a0-measurability-v1.json'
US_SHA = '2ae0314a4dc710d8f47afb149332678b34346f90e2fa4bc4e615f37bee063a04'
CODE = ('pipeline/rp1_a0.py', 'pipeline/rp1_kr_a0.py', 'scripts/rp1_inspect_kr_a0.py',
        'pipeline/experiment_workbench.py','pipeline/dart_derive.py','pipeline/dart_fundamentals.py',
        'pipeline/alpha_opportunity_features.py','pipeline/kr_value_quality_catalyst.py',
        'pipeline/fundamental_acceleration.py','pipeline/fundamental_acceleration_seal.py',
        'pipeline/kr_alpha_signal_v2.py','pipeline/kr_alpha_atlas_bars.py','pipeline/krx_prices.py',
        'pipeline/regional_alpha_features.py','pipeline/kr_industry_anatomy.py','pipeline/replay_calendar.py',
        'pipeline/prospective_receipt_core.py','scripts/inspect_experiment_sources.py')


def validate_contracts(root=ROOT):
    _,wp1,_=US.contracts(root)
    if wp1['result']['studyABranch']['KR']!='H252':
        raise ValueError('KR_H252_NOT_CALIBRATED')
    root = Path(root)
    if hashlib.sha256((root / US_RESULT).read_bytes()).hexdigest() != US_SHA:
        raise ValueError('US_A0_GOLDEN_CHANGED')
    spec = json.loads((root / SPEC).read_bytes())
    if spec['id']!='rp1-kr-a0-measurability-v1' or spec['gates']!={
        'prevalence':[.03,.50],'measurabilityMin':.60,'signalPositiveNamesPerKRDateMin':5,
        'H1CorrelationAbsMax':.70,'MDE80AnnualPercentagePointsMax':4}:
        raise ValueError('ORIGINAL_A0_GATES_CHANGED')
    for path, sha in spec['originalContractHashes'].items():
        if hashlib.sha256((root / path).read_bytes()).hexdigest() != sha:
            raise ValueError('ORIGINAL_KR_CONTRACT_CHANGED:' + path)
    if spec['sourceCommit'] != S.SOURCE_COMMIT or spec['manifestSha256'] != S.MANIFEST_SHA:
        raise ValueError('SOURCE_IDENTITY_CHANGED')
    return spec


def admission(root=ROOT, github=US.api):
    result = US.main_admission(root, github)
    if not github('pulls/260').get('merged'):
        result['blockers'].append('PR_260_NOT_MERGED')
    result['status'] = 'ADMITTED' if not result['blockers'] else 'BLOCKED_PRECONDITIONS'
    return result


def load_inputs(repo):
    source = S.Sources(repo)
    manifest = json.loads(source.blob(S.SOURCE_COMMIT, S.MANIFEST))
    if RI.digest({k:v for k,v in manifest.items() if k != 'sha256'}) != S.MANIFEST_SHA:
        raise ValueError('REPLAY_MANIFEST_CHANGED')
    roles = ('price/20', 'benchmark/20')
    source.allowed_objects = {r for n, refs in manifest['components'].items() if n.startswith(roles) for r in refs}
    frames = defaultdict(dict)
    for n, refs in sorted(manifest['components'].items()):
        if not n.startswith(roles):
            continue
        for ref in refs:
            for row in source.component(ref):
                ticker, day = row['ticker'], row['date']
                if not ticker.endswith('.KS') or (ticker == '069500.KS') != n.startswith('benchmark/20'):
                    continue
                value = (row.get('Close'), row.get('Volume'))
                if day in frames[ticker] and frames[ticker][day] != value:
                    raise ValueError('CONFLICTING_PRICE_KEY')
                frames[ticker][day] = value
    frames = {t:pd.DataFrame.from_dict(v, orient='index', columns=['Close','Volume']).sort_index() for t,v in frames.items()}
    for f in frames.values():
        f.index = pd.to_datetime(f.index)
    snapshots, raw, filings = defaultdict(list), defaultdict(list), defaultdict(list)
    for year in range(2013,2027):
        for row in source.rows(f'ledger/universe/kr/krx-universe-{year}.jsonl.gz'):
            snapshots[row['date']].append(row)
    members = S.RAF.MembershipSnapshots([{'date':d,'members':[r['ticker'] for r in sorted(rows,key=lambda r:(r['rank'],r['ticker']))[:120]],
            'rows':{r['ticker']:r for r in rows}} for d,rows in sorted(snapshots.items())])
    ever = {t for s in members.snapshots for t in s['members']}
    for year in range(2013,2027):
        for row in source.rows(f'ledger/prices/kr/krx-prices-{year}.jsonl.gz'):
            if row['ticker'] in ever:
                raw[row['ticker']].append(row)
    invalid_receipts = 0
    for year in range(2015,2027):
        for row in source.rows(f'ledger/fundamentals/kr-candidate-merged/dart-{year}.jsonl.gz'):
            filings[row['ticker']].append(row)
            invalid_receipts += K.Filings.visible_day(row) is None
    calendar = S.RC.sessions('2011-01-01','2026-10-31','KR')
    bars = {t:B.TickerBars(t,KP.frame_from_rows(rows,traded_only=False),calendar) for t,rows in raw.items()}
    inventory = source.json(S.IDENTITIES)
    identities = {r['ticker']:(i['issuerId'],r['securityId']) for i in inventory['issuers'] for r in i['securities']}
    intervals,crosswalk,provenance = source.json(S.INTERVALS),source.json(S.CROSSWALK),source.json(S.KR_PROVENANCE)
    dates = [str(d.date()) for d in calendar.to_series().groupby(calendar.to_period('W')).max()
             if '2013-01-01' <= str(d.date()) <= manifest['through']]
    return source,manifest,members,frames,bars,filings,identities,intervals,crosswalk,provenance,calendar,dates,invalid_receipts


def observations(inputs):
    source,manifest,members,frames,bars,filings,identities,intervals,crosswalk,_,calendar,dates,_ = inputs
    histories = {t:A.FilingHistory(t,rows,adapter=K.Filings()) for t,rows in filings.items()}
    observed_by_id={str(r['id']):r.get('collectedAt') for rows in filings.values() for r in rows}
    past = A.PastPrices(frames,calendar,benchmark='069500.KS')
    universe_hash = RI.digest({p:v for p,v in source.receipts.items() if 'universe/kr/' in p})
    filing_hash = RI.digest({p:v for p,v in source.receipts.items() if 'fundamentals/kr-' in p})
    input_context={'priceManifestSha256':S.MANIFEST_SHA,'universeSha256':universe_hash,
        'industrySourcesSha256':RI.digest({p:v for p,v in source.receipts.items() if p.endswith((S.INTERVALS,S.CROSSWALK))}),
        'rawBarSourcesSha256':RI.digest({p:v for p,v in source.receipts.items() if 'prices/kr/' in p})}
    src = W.Source(S.SOURCE_COMMIT+':'+S.MANIFEST,S.MANIFEST_SHA,'PUBLIC_RECONSTRUCTION',None,'NOT_RETAINED')
    usrc = W.Source(S.SOURCE_COMMIT+':KR-universe',universe_hash,'PUBLIC_RECONSTRUCTION',None,'NOT_RETAINED')
    result,details,eligibility_all = [],{},Counter()
    for day in dates:
        snap = members.on(day)
        rows=[]
        for ticker in sorted(snap['members']):
            b=bars.get(ticker);quote=b.quote(day) if b else None
            bv,br=b.features_at(day) if b else ({},{})
            industry,status=S.KI.industry_of(intervals,crosswalk,ticker,day)
            # Membership name is known at the strictly earlier snapshot; never
            # the company's final surviving name from the whole panel.
            name=snap.get('rows',{}).get(ticker,{}).get('name')
            relative = past.features(ticker,day)['relative126']
            price_reason = b.basis_cause(day,127) if b else 'NO_PRICE_PANEL'
            if price_reason:
                relative=None
            size=quote['marketCap'] if quote else None
            guard=bv.get('E04_tradabilityGuard20')
            row={'ticker':ticker,'sector':industry,'industry':industry,'industryStatus':status,
                 'issuerId':identities.get(ticker,(None,None))[0], 'marketCap':size,'relative126':relative,
                 'priceReason':price_reason or 'PAST_126_SESSION_WINDOW_UNRESOLVED',
                 'isPreferredShare':None if not name else not COMMON.is_likely_common_share(name),
                 'priceAsOf':day if quote else None,'positiveVolumeSessions20':int(guard) if A.finite(guard) else None,
                 'medianTradedValue60Krw':bv.get('E03_capacityMedianTradedValue60'),
                 'liquidityReason':br.get('E03_capacityMedianTradedValue60')}
            rows.append(row)
        eligibility=K.eligibility(rows,day)
        for row in rows:
            causes=eligibility[row['ticker']];eligibility_all.update(causes)
            if row['liquidityReason']:
                eligibility_all.update(['liquidityInput:'+row['liquidityReason']])
            row['eligibilityReason']=causes[0] if causes else None
            state=histories[row['ticker']].at(day) if row['ticker'] in histories else {
                'flag':None,'reason':'NO_FILING_STORE','deltas':{},'fields':{},'publicDay':None,'sourceIds':[]}
            row['state']=state
            row.update(deltaRoe=state['deltas'].get('roe'),deltaOperatingMargin=state['deltas'].get('operatingMargin'),
                       deltaProfitMargin=state['deltas'].get('profitMargin'),deltaEarningsGrowth=state['deltas'].get('earningsGrowth'))
        eligible=[r for r in rows if not r['eligibilityReason']]
        third=A.h3(eligible,size_field='marketCap');composite=A.acceleration_controls(eligible,market='KR')
        for row in rows:
            t,state=row['ticker'],row['state'];third_value,third_reason=third.get(t,(None,'INELIGIBLE'))
            flags={'A-H1':state['flag'],'A-H2':A.h2(state['flag'],row['relative126']),'A-H3':third_value}
            values={'financial.'+h.replace('-','_'):float(v) if v is not None else None for h,v in flags.items()}
            values.update({'risk.marketCap':row['marketCap'],'price.relative126':row['relative126'],
                           'financial.C13_fundamentalAcceleration':composite.get(t)})
            # KR final-close timestamp, including delayed-opening days; never
            # the US executor's XNYS clock.
            at=(pd.Timestamp(day)+K.CORE.KR_CLOSE_FINAL_UTC).tz_localize('UTC').isoformat()
            observed_stamps=[observed_by_id.get(i) for i in state['sourceIds']]
            observed_at=max(observed_stamps) if observed_stamps and all(observed_stamps) else None
            fsrc=W.Source(S.SOURCE_COMMIT+':KR-visible-filings:'+RI.digest(state['sourceIds']),
                RI.digest({**input_context,'filingReceipts':filing_hash,'sourceIds':state['sourceIds']}),'PUBLIC_RECONSTRUCTION',
                observed_at,None if observed_at else 'NOT_RETAINED')
            financial_at=(pd.Timestamp(state['publicDay'])+pd.Timedelta(days=1)).tz_localize('Asia/Seoul').isoformat() if state['publicDay'] else None
            cells=tuple(W.Cell(n,v,'KRW' if n=='risk.marketCap' else 'ratio',
                        (financial_at if n=='financial.A_H1' else at) if v is not None else None,
                        fsrc if n.startswith('financial.') else src,None if v is not None else 'INCOMPLETE_CHAIN') for n,v in values.items())
            key=W.Key('KR',day,identities.get(t,(None,'KRX:'+t))[1])
            details[key.sample_id]={'A-H1':state['reason'],'A-H2':state['reason'] if state['flag'] is None else row['priceReason'],'A-H3':third_reason}
            result.append(W.Observation(key,t,row['issuerId'],'PROVISIONAL' if row['issuerId'] else 'UNRESOLVED',at,
                'PUBLIC_RECONSTRUCTION',usrc,snap['date']+'T00:00:00+09:00',not row['eligibilityReason'],row['eligibilityReason'],
                row['industry'],'RECONSTRUCTED' if row['industry'] else 'UNRESOLVED',cells))
    return result,details,dict(sorted(eligibility_all.items()))


def inspect(repo, *, main_admission, root=ROOT):
    if main_admission['status']!='ADMITTED':
        return {**main_admission,'sourceInputsOpened':0}
    spec=validate_contracts(root); inputs=load_inputs(repo)
    rows,details,all_reasons=observations(inputs)
    report=A.measure(rows,missing_details=details,market='KR',comparators=K.COMPARATORS,size_field='risk.marketCap')
    report['diagnostics']=K.diagnostics(report)
    report['peerCompletenessByDate']=K.peer_diagnostics(rows)
    terminal_rows=inputs[9]['terminalSecurities']
    # Provenance may store richer terminal records; never infer an outcome.
    if not all(isinstance(t,str) for t in terminal_rows):
        raise ValueError('TERMINAL_IDENTITY_SCHEMA_UNRESOLVED')
    terminal=set(terminal_rows)
    audit=A.population_audit(rows,terminal)
    audit['definition']='Retrospective known terminal securities from pinned identity provenance; not a terminal-consideration or return audit'
    audit['groups']={k.replace('index:EXITED','terminal:KNOWN_TERMINAL').replace(
        'index:LAST_PRESERVED_SNAPSHOT_MEMBER','terminal:NOT_FLAGGED_AS_TERMINAL'):v for k,v in audit['groups'].items()}
    report.update(market='KR',formalA0Measurement=True,mainAdmission=main_admission,sourceCommit=S.SOURCE_COMMIT,
        manifestSha256=S.MANIFEST_SHA,sourceReceipts=inputs[0].receipts,specification=spec,
        specSha256=hashlib.sha256((Path(root)/SPEC).read_bytes()).hexdigest(),
        codeHashes={p:hashlib.sha256((Path(root)/p).read_bytes()).hexdigest() for p in CODE},
        measurementCodeCommit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
        usA0GoldenSha256=US_SHA,populationAudit=audit,eligibilityReasonsAll=all_reasons,
        invalidReceiptDateRecords=inputs[-1],rawInputPriceBasis='INHERITED_REPLAY_NOT_NEW_RETURN_BASIS_ADMISSION',
        historicalInferenceEligibility='GOVERNANCE_CLOSED',a1Admission='GOVERNANCE_CLOSED',
        latest52IsFormalGate=False,prospectiveActivation='NOT_AUTHORIZED',
        recordingPrerequisites=['KR_SOURCE_INTEGRITY_AND_STORAGE_RIGHTS','ORIGINAL_A2_REGISTRATION_AND_AUTHORIZATION',
                               'CURRENT_PIT_INPUTS_WITH_OBSERVED_AT','PREVIEW_ONLY_INTERFACE_NOT_A_LEDGER_WRITER'])
    filing_rows=[r for rs in inputs[5].values() for r in rs]
    observed=sorted(r['collectedAt'] for r in filing_rows if r.get('collectedAt'))
    report['sourceAvailability']={'filingRecords':len(filing_rows),'filingTickers':len(inputs[5]),
        'accountPresenceRecords':{name:sum(name in r.get('accounts',{}) for r in filing_rows)
                                  for name in ('영업이익','영업활동현금흐름','매출액')},
        'statementBasisRecords':dict(sorted(Counter(r.get('fsDiv','UNKNOWN') for r in filing_rows).items())),
        'filingPublicRange':[min(r['availableFrom'] for r in filing_rows),max(r['availableFrom'] for r in filing_rows)],
        'filingObservedRange':[observed[0],observed[-1]] if observed else None,
        'filingObservedAtMissing':len(filing_rows)-len(observed),
        'reconstructionIsProspective':False,'priceLinkedThrough':report['byDate'][-1]['date'],
        'industryEvidence':'PARTIALLY_RECONSTRUCTED_V4','identityEvidence':'RETROSPECTIVE_ISSUER_BRIDGE_NOT_SECURITY_VERIFICATION',
        'liquidityBasis':B.TRADING_VALUE_BASIS_PROXY}
    recent=report['diagnostics']['LATEST_52_WEEKS']['hypotheses']
    report['prospectiveRepresentation']={h:{'status':'REPRESENTABLE_PREVIEW_NOT_AUTHORIZED' if recent[h]['measured'] else 'BLOCKED_INPUTS',
        'isStatisticalAdmission':False,'latest52DiagnosticOnly':True} for h in A.HYPOTHESES}
    CORE_SCAN(report)
    return report


def CORE_SCAN(report):
    # The inherited measurement has diagnostic field names that the broad
    # receipt-only scanner disallows; the existing input census scanner applies.
    US.U.scan_output(report)


def guarded_inspect(repo, *, main_admission, root=ROOT):
    # These real execution/label/model entry points fail before returning any
    # value. No closed KR result/discovery module is loaded for this task.
    from pipeline import historical_outcomes as HO
    from pipeline import winner_inflection_execution as EX
    targets=((HO,'compute_outcomes'),(HO,'horizon_frame'),(EX,'outcome'),(EX,'label_cohorts'),(EX,'model_predictions'),
             (EX,'predictive_report'),(EX,'top5_diagnostics'),(EX,'economics'),(EX,'execute'),
             (A.WE,'fit_prepared'),(A.WE,'compare_synthetic'))
    calls={m.__name__+'.'+n:0 for m,n in targets}
    def denied(name):
        def deny(*args,**kwargs):
            calls[name]+=1
            raise AssertionError('KR_A0_FORBIDDEN_RESULT_ACCESS:'+name)
        return deny
    with ExitStack() as stack:
        for module,name in targets:
            stack.enter_context(patch.object(module,name,denied(module.__name__+'.'+name)))
        report=inspect(repo,main_admission=main_admission,root=root)
    report['resultAccessSpies']={'forbiddenAccessCalls':sum(calls.values()),
                               'calls':[{'entrypoint':n,'count':v} for n,v in sorted(calls.items())]}
    CORE_SCAN(report)
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inspect',action='store_true')
    parser.add_argument('--repo',type=Path,default=ROOT)
    args=parser.parse_args(argv)
    report=guarded_inspect(args.repo,main_admission=admission(args.repo)) if args.inspect else {
        'status':'PREVIEW_ONLY','sourceInputsOpened':0,'ledgerWrites':0}
    print(json.dumps(report,sort_keys=True,ensure_ascii=False,allow_nan=False,indent=2))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
