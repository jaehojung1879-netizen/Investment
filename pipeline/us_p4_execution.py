"""Dormant P4 orchestration; all real panel loading is strictly after remote lock."""
from __future__ import annotations

import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess

from .kr_alpha_tournament_execution import github_api

ROOT = Path(__file__).resolve().parents[1]
LOCK = 'refs/tags/us-cash-profitability-signal-v1-exploratory-lock'
AUTH = 'docs/us-readiness/us-cash-profitability-exploratory-authorization-v1.json'
ACCEPTANCE = 'docs/us-readiness/us-h63-supplemental-calibration-acceptance-v1.json'
WORKFLOW = '.github/workflows/kr-corporate-action-collection.yml'
ACKNOWLEDGMENTS = ('outcomeExposedExploratoryHistory','survivorConditioned212MissingDeparted',
                  'membershipAndIdentityLimitations','oneShotFailureConsumesBudget','noLivePromotion',
                  'abandonOrProspectiveReviewOnly','uncalibratedUpperGeometry331To371')


class Blocked(RuntimeError):
    pass


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def git(args, root=ROOT):
    return subprocess.check_output(['git',*args],cwd=root)


def committed(root, relative):
    path=(root/relative).resolve()
    if not path.is_relative_to(root.resolve()) or path.read_bytes()!=git(['show','HEAD:'+relative],root):
        raise Blocked('UNCOMMITTED_OR_UNSAFE_PIN:'+relative)
    return path.read_bytes()


SUPPLEMENT_RESULT = 'docs/us-readiness/us-h63-inference-calibration-v1-supplement-result.json'
SUPPLEMENT_PROTOCOL = 'docs/us-readiness/us-h63-inference-calibration-v1-supplement-protocol.json'
READINESS_V2 = 'docs/us-readiness/us-cash-profitability-exploratory-readiness-v2.json'
PRODUCER_FILES = ('pipeline/us_h63_inference_calibration.py',
                  'pipeline/us_h63_supplemental_calibration.py',
                  'scripts/run_us_h63_supplemental_calibration.py')


def supplemental(root, preflight_sha):
    """Verify the actual merged supplement schema; never infer full geometry coverage."""
    from .us_h63_supplemental_calibration import verdict
    try:
        raw=committed(root,ACCEPTANCE)
        acceptance=json.loads(raw)
        if (acceptance.get('contract')!='US_H63_SUPPLEMENTAL_ACCEPTANCE_V1' or acceptance.get('accepted') is not True or
                acceptance.get('authorizes')!='NOTHING' or not acceptance.get('reviewedBy') or
                acceptance.get('preflightSha256')!=preflight_sha):
            raise Blocked('SUPPLEMENTAL_NOT_ACCEPTED_OR_PREFLIGHT_MISMATCH')
        result_raw=committed(root,SUPPLEMENT_RESULT)
        protocol_raw=committed(root,SUPPLEMENT_PROTOCOL)
        readiness_raw=committed(root,READINESS_V2)
        for key,blob in (('resultSha256',result_raw),('protocolSha256',protocol_raw),('readinessV2Sha256',readiness_raw)):
            if acceptance.get(key)!=sha(blob):
                raise Blocked('SUPPLEMENTAL_HASH_MISMATCH:'+key)
        result,protocol,readiness=map(json.loads,(result_raw,protocol_raw,readiness_raw))
        if (result['contract']!='US_H63_INFERENCE_CALIBRATION_V1_SUPPLEMENT' or
                result['developmentOnly'] is not False or result['readsRealData'] is not False or
                result['primaryMethod']!='CT_SN' or result['replicates']!=2000 or
                result['verdict']['supplementStatus']!='SUPPLEMENT_PASS'):
            raise Blocked('SUPPLEMENTAL_FAILED_INCONCLUSIVE_OR_DEVELOPMENT')
        if result['protocolSha256']!=sha(protocol_raw) or result['parent']!=protocol['parent']:
            raise Blocked('SUPPLEMENTAL_RESULT_PROTOCOL_LINK_MISMATCH')
        if set(result['codeSha256'])!=set(PRODUCER_FILES):
            raise Blocked('SUPPLEMENTAL_PRODUCER_CODE_PROOF_MISSING')
        for relative,digest in result['codeSha256'].items():
            if digest!=sha(committed(root,relative)):
                raise Blocked('SUPPLEMENTAL_PRODUCER_CODE_MISMATCH')
        for kind in ('code','protocol','result'):
            parent=protocol['parent']
            if sha(committed(root,parent[kind]))!=parent[kind+'Sha256']:
                raise Blocked('SUPPLEMENTAL_PARENT_HASH_MISMATCH')
        expected={(d['name'],w) for d in protocol['dgps'] for w in protocol['sampleLengths']['weeks']}
        cells=result['cells']
        actual={(c['dgp'],c['weeks']) for c in cells}
        if (len(expected)!=30 or len(cells)!=30 or actual!=expected or
                result['verdict']!=verdict(cells,30) or result['verdict']['primaryStateCounts']!={'PASS':30} or
                result['verdict']['allCellsGeometryAsDesigned'] is not True or
                any(c['methods']['CT_SN']['state']!='PASS' or
                    any(m['state']!='PASS' for m in c['methods']['CT_SN']['metrics'].values()) for c in cells)):
            raise Blocked('SUPPLEMENTAL_CELL_PROOF_MISMATCH')
        geometry=protocol['historicalGeometry']
        preflight=json.loads(committed(root,geometry['source']))
        if (geometry['sourceSha256']!=preflight_sha or geometry['definedDatesBelowParentMinimum']!=163 or
                protocol['outcomeFree'] is not True or
                protocol['sizeGrid']['targetAvailableNamesPerDate']!=[150,200,244] or
                protocol['sampleLengths']['weeks']!=[260,700] or
                preflight['counters']['outcomeReads']!=0 or preflight['counters']['intervalComputations']!=0 or
                readiness['counters']!=preflight['counters'] or readiness['executed'] is not False or
                readiness['outcomeFree'] is not True or
                readiness['inputs']['supplementResult']['sha256']!=sha(result_raw) or
                readiness['inputs']['preflight']['sha256']!=preflight_sha or
                readiness['groups']['calibrationReadiness']['state']!='PASS'):
            raise Blocked('SUPPLEMENTAL_READINESS_OR_OUTCOME_FREE_PROOF_MISMATCH')
        # PASS covers only the specified synthetic geometries, NOT 331-371.
        # An explicit, separately reviewed owner disposition is mandatory; no default waiver.
        if acceptance.get('upperGeometryDisposition')!='EXPLICIT_OWNER_ACCEPTED_EXPLORATORY_EXTRAPOLATION':
            raise Blocked('UNCALIBRATED_UPPER_GEOMETRY_331_TO_371_REQUIRES_OWNER_REVIEW')
        return {'acceptanceSha256':sha(raw),'supplementalResultSha256':sha(result_raw),
                'supplementalProtocolSha256':sha(protocol_raw),'readinessV2Sha256':sha(readiness_raw),
                'uncalibratedUpperGeometry':'331-371:EXPLICIT_OWNER_ACCEPTED_EXPLORATORY_EXTRAPOLATION'}
    except (OSError,KeyError,TypeError,ValueError,subprocess.CalledProcessError) as exc:
        raise Blocked('SUPPLEMENTAL_ABSENT_OR_INVALID') from exc


def input_pins(root):
    """Hashes only before lock: never parse price values or load the panel."""
    from scripts import run_us_cash_profitability_exploratory as H
    if root.resolve()!=ROOT.resolve():
        raise Blocked('REAL_INPUT_ROOT_MISMATCH')
    identities=H.identities()
    reader=H.D.SealedReader(root)
    manifest=reader.manifest()
    component_hashes={}
    for refs in manifest['components'].values():
        for ref in refs:
            raw=gzip.decompress(reader.blob(H.D.OBJECTS+ref+'.json.gz'))
            if sha(raw)!=ref:
                raise Blocked('REPLAY_COMPONENT_HASH_MISMATCH')
            component_hashes[ref]=sha(raw)  # no JSON price parsing, no return calculation
    listing=git(['ls-tree','-r',H.A.FUNDAMENTALS_COMMIT,'ledger/fundamentals/us/'],root).decode().splitlines()
    fundamentals={}
    for line in listing:
        meta,path=line.split('\t')
        oid=meta.split()[2]
        fundamentals[path]=sha(git(['cat-file','blob',oid],root))
    if not fundamentals or not component_hashes:
        raise Blocked('EMPTY_PINNED_INPUT_STORE')
    code={}
    for line in git(['ls-tree','-r','--name-only','HEAD','pipeline','scripts','requirements.txt'],root).decode().splitlines():
        if line.endswith('.py') or line=='requirements.txt':
            code[line]=sha(committed(root,line))
    metadata={p:sha(committed(root,p)) for p in (WORKFLOW,
        'docs/us-readiness/us-cash-profitability-exploratory-preflight-v1.json',
        'docs/us-readiness/us-cash-profitability-exploratory-readiness-v1.json')}
    excluded={AUTH,ACCEPTANCE,'docs/us-readiness/us-cash-profitability-exploratory-result-v1.json'}
    for relative in git(['ls-tree','-r','--name-only','HEAD','data/research','research_specs','docs/us-readiness','docs/results'],root).decode().splitlines():
        if relative not in excluded and (relative.endswith('.json') or relative.endswith('.json.gz')):
            metadata[relative]=sha(committed(root,relative))
    calibration=supplemental(root,metadata['docs/us-readiness/us-cash-profitability-exploratory-preflight-v1.json'])
    return {'pinnedIdentities':identities,'executionPins':{'codeTreeSha256':sha(canonical(code)),
            'replayManifestBytesSha256':sha(reader.blob(H.D.REPLAY_MANIFEST)),
            'replayObjectsSha256':sha(canonical(component_hashes)),'fundamentalsBlobsSha256':sha(canonical(fundamentals)),
            'metadataSha256':sha(canonical(metadata)),**calibration}}


def main_matches(api, head):
    status,body=api('GET','/git/ref/heads/main',None)
    if status!=200 or body.get('object',{}).get('sha')!=head:
        raise Blocked('NOT_CURRENT_REMOTE_MAIN')


def lock_absent(api):
    status,body=api('GET','/git/matching-refs/'+LOCK[len('refs/'):],None)
    if status!=200 or not isinstance(body,list):
        raise Blocked('LOCK_STATE_UNVERIFIABLE')
    if body:
        raise Blocked('ONE_SHOT_ALREADY_SPENT')


def authorize(root, env, expected_auth_sha, api, pins):
    if (env.get('GITHUB_ACTIONS')!='true' or env.get('GITHUB_EVENT_NAME')!='workflow_dispatch' or
            env.get('GITHUB_REF')!='refs/heads/main' or env.get('GITHUB_RUN_ATTEMPT')!='1'):
        raise Blocked('REQUIRES_FIRST_MANUAL_MAIN_ATTEMPT')
    if env.get('GITHUB_ACTOR')!=env.get('GITHUB_REPOSITORY','/').split('/')[0]:
        raise Blocked('OWNER_DISPATCH_REQUIRED')
    head=git(['rev-parse','HEAD'],root).decode().strip()
    if head!=env.get('GITHUB_SHA'):
        raise Blocked('CHECKOUT_MISMATCH')
    main_matches(api,head)
    try:
        raw=committed(root,AUTH)
        auth=json.loads(raw)
    except (OSError,ValueError,subprocess.CalledProcessError) as exc:
        raise Blocked('NO_COMMITTED_OWNER_AUTHORIZATION') from exc
    if not expected_auth_sha or sha(raw)!=expected_auth_sha:
        raise Blocked('OWNER_AUTHORIZATION_HASH_MISMATCH')
    if (auth.get('contract')!='US_CASH_PROFITABILITY_EXPLORATORY_V1' or
            auth.get('authorizes')!='ONE_EXPLORATORY_EXECUTION' or auth.get('ownerLogin')!=env['GITHUB_ACTOR'] or
            any(auth.get('acknowledgments',{}).get(k) is not True for k in ACKNOWLEDGMENTS)):
        raise Blocked('OWNER_SCOPE_OR_ACKNOWLEDGMENT_MISSING')
    # All expensive input byte checks follow explicit authorization, before lock.
    current=pins()
    if current['executionPins'].get('acceptanceSha256'):
        acceptance=json.loads(committed(root,ACCEPTANCE))
        if acceptance.get('reviewedBy')!=env['GITHUB_ACTOR']:
            raise Blocked('SUPPLEMENTAL_OWNER_REVIEW_REQUIRED')
    if auth.get('pinnedIdentities')!=current['pinnedIdentities'] or auth.get('executionPins')!=current['executionPins']:
        raise Blocked('PINNED_INPUT_CODE_OR_CALIBRATION_MISMATCH')
    if (root/'docs/us-readiness/us-cash-profitability-exploratory-result-v1.json').exists():
        raise Blocked('EXISTING_P4_RESULT_REFUSES_NEW_ATTEMPT')
    lock_absent(api)
    return head,current,sha(raw)


def acquire(api,head):
    main_matches(api,head)
    lock_absent(api)
    status,_=api('POST','/git/refs',{'ref':LOCK,'sha':head})
    if status!=201:
        raise Blocked('ATOMIC_LOCK_CREATION_FAILED_OR_ALREADY_SPENT')
    verify_lock(api,head)
    main_matches(api,head)
    return LOCK


def verify_lock(api,head):
    status,body=api('GET','/git/ref/'+LOCK[len('refs/'):],None)
    if status!=200 or body.get('object',{}).get('sha')!=head:
        raise Blocked('LOCK_CONFIRMATION_FAILED_ATTEMPT_MAY_BE_SPENT')


def real_execute(work, guarded_reader):
    """Only called after lock: reuse the frozen CLI, not another research engine."""
    from scripts import run_us_cash_profitability_exploratory as H
    from types import SimpleNamespace
    H.A.extract(work/'fundamentals',H.A.FUNDAMENTALS_COMMIT)
    original=H.close_reader
    H.close_reader=lambda tickers,sessions:guarded_reader(lambda:original(tickers,sessions))
    try:
        H.execute(SimpleNamespace(workspace=work/'fundamentals',workers=4,output=work/'result.json'))
    finally:
        H.close_reader=original
    record=json.loads((work/'result.json').read_text())
    status=record['result']['status']
    return {'rawStatus':status,'interpretation':'ABANDON' if status==H.X.ABANDON else
            'CONTINUE_TO_PROSPECTIVE_REGISTRATION_REVIEW' if status==H.X.CONTINUE else 'NOT_EVALUABLE',
            'promotionAuthorized':False}


def orchestrate(root, work, *, mode, env, expected_auth_sha, api, pins=None, execute=None):
    root,work=Path(root).resolve(),Path(work).resolve()
    if work.is_relative_to(root) or any((p/'.git').is_file() or (p/'.git/HEAD').is_file() for p in (work,*work.parents)) or work.exists():
        raise Blocked('FRESH_OUTPUT_OUTSIDE_ALL_CHECKOUTS_REQUIRED')
    work.mkdir(parents=True)
    audit={'contract':'US_P4_EXECUTION_ATTEMPT_V1','mode':mode,'status':'BLOCKED','lockRef':LOCK,
           'lockCreateAttempted':False,'lockConfirmed':False,'actualForwardReaderCalls':0,'productionPromotion':False}
    try:
        head,current,auth_sha=authorize(root,env,expected_auth_sha,api,pins or (lambda:input_pins(root)))
        audit.update(headSha=head,authorizationSha256=auth_sha,pins=current)
        if mode=='validate':
            audit['status']='PRELOCK_GATES_PASSED_NO_EXECUTION'
        elif mode=='execute':
            audit['lockCreateAttempted']=True
            acquire(api,head)
            audit['lockConfirmed']=True
            def guarded_reader(reader):
                verify_lock(api,head)
                main_matches(api,head)
                if audit['actualForwardReaderCalls']!=0:
                    raise Blocked('SECOND_FORWARD_READER_CALL_REFUSED')
                audit['actualForwardReaderCalls']+=1
                return reader()
            audit['interpretation']=(execute or real_execute)(work,guarded_reader)
            audit['status']='EXECUTED_PENDING_SEPARATE_REVIEW_AND_SEAL'
        else:
            raise Blocked('INVALID_MODE')
    except BaseException as exc:
        audit['errorType']=type(exc).__name__
        audit['reason']=str(exc)[:1000]
        audit['status']='LOCK_SPENT_OR_UNKNOWN_NO_RETRY' if audit['lockCreateAttempted'] else 'BLOCKED'
        raise
    finally:
        (work/'attempt.json').write_bytes(canonical(audit)+b'\n')
    return audit


def cli(argv=None):
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['pins','validate','execute'])
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--authorization-sha256',default='')
    args=parser.parse_args(argv)
    env=dict(os.environ)
    api=lambda method,path,payload:github_api(method,path,payload,env=env)
    try:
        if args.mode=='pins':
            target=args.work.resolve()
            if target.exists() or target.is_relative_to(ROOT) or any((p/'.git').is_file() or (p/'.git/HEAD').is_file() for p in (target,*target.parents)):
                raise Blocked('FRESH_PIN_OUTPUT_OUTSIDE_CHECKOUTS_REQUIRED')
            current=input_pins(ROOT)
            args.work.mkdir(parents=True)
            (args.work/'candidate-pins.json').write_bytes(canonical({'authorizes':'NOTHING',**current})+b'\n')
            print(json.dumps({'status':'OUTCOME_FREE_CANDIDATE_PINS_NOT_AUTHORIZATION'}))
            return 0
        print(json.dumps(orchestrate(ROOT,args.work,mode=args.mode,env=env,
                         expected_auth_sha=args.authorization_sha256,api=api),sort_keys=True))
        return 0
    except (Blocked,OSError,ValueError,subprocess.CalledProcessError) as exc:
        print(json.dumps({'status':'BLOCKED_OR_SPENT','reason':str(exc)}))
        return 1
