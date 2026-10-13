"""Synthetic orchestration and bare Git locks only; no real P4 inputs/outcomes."""
from concurrent.futures import ThreadPoolExecutor
import json
import subprocess

import pytest

from pipeline import us_p4_execution as E


def command(root,*args):
    return subprocess.check_output(['git',*args],cwd=root,stderr=subprocess.DEVNULL).decode().strip()


def fixture(tmp_path):
    repo=tmp_path/'repo';repo.mkdir()
    command(repo,'init','-b','main')
    command(repo,'config','user.email','fixture@example.invalid')
    command(repo,'config','user.name','Fixture')
    current={'pinnedIdentities':{'synthetic':'FIXTURE_NO_REAL_INPUT'},'executionPins':{'calibration':'FIXTURE_ACCEPTED'}}
    auth={'contract':'US_CASH_PROFITABILITY_EXPLORATORY_V1','authorizes':'ONE_EXPLORATORY_EXECUTION',
          'ownerLogin':'fixture-owner','acknowledgments':dict.fromkeys(E.ACKNOWLEDGMENTS,True),**current}
    path=repo/E.AUTH;path.parent.mkdir(parents=True);path.write_text(json.dumps(auth))
    command(repo,'add','.');command(repo,'commit','-m','Invented approval fixture')
    head=command(repo,'rev-parse','HEAD')
    bare=tmp_path/'remote.git';command(tmp_path,'clone','--bare',str(repo),str(bare))
    events=[]
    def api(method,path,payload):
        events.append((method,path))
        if path=='/git/ref/heads/main':
            return 200,{'object':{'sha':command(bare,'rev-parse','refs/heads/main')}}
        if path.startswith('/git/matching-refs/'):
            refs=command(bare,'for-each-ref','--format=%(refname)')
            return 200,[{'ref':r} for r in refs.splitlines() if r.startswith(E.LOCK)]
        if method=='POST':
            # update-ref create uses compare-and-swap, not concurrency alone.
            p=subprocess.run(['git','update-ref','--stdin'],cwd=bare,input=f"create {payload['ref']} {payload['sha']}\n",text=True,capture_output=True)
            return (201 if p.returncode==0 else 422),{}
        try:
            return 200,{'object':{'sha':command(bare,'rev-parse',E.LOCK)}}
        except subprocess.CalledProcessError:
            return 404,{}
    env={'GITHUB_ACTIONS':'true','GITHUB_EVENT_NAME':'workflow_dispatch','GITHUB_REF':'refs/heads/main',
         'GITHUB_RUN_ATTEMPT':'1','GITHUB_REPOSITORY':'fixture-owner/repo','GITHUB_ACTOR':'fixture-owner','GITHUB_SHA':head}
    return repo,bare,env,api,current,E.sha(path.read_bytes()),events


def run(tmp_path,fix,**changes):
    repo,bare,env,api,current,auth_sha,events=fix
    def mock_execute(work,reader):
        events.append(('MOCK_PANEL_LOAD_AFTER_LOCK',None))
        assert command(bare,'rev-parse',E.LOCK)==env['GITHUB_SHA']
        reader(lambda:events.append(('MOCK_OUTCOME_READ',None)))
        return {'interpretation':'CONTINUE_TO_PROSPECTIVE_REGISTRATION_REVIEW','promotionAuthorized':False}
    values={'mode':'execute','env':env,'expected_auth_sha':auth_sha,'api':api,'pins':lambda:current,'execute':mock_execute}
    values.update(changes)
    return E.orchestrate(repo,tmp_path/'output',**values)


def test_correct_order_no_automatic_publication(tmp_path):
    fix=fixture(tmp_path)
    result=run(tmp_path,fix)
    events=fix[-1]
    post=next(i for i,e in enumerate(events) if e[0]=='POST')
    load=next(i for i,e in enumerate(events) if e[0]=='MOCK_PANEL_LOAD_AFTER_LOCK')
    read=next(i for i,e in enumerate(events) if e[0]=='MOCK_OUTCOME_READ')
    assert post<load<read
    assert result['actualForwardReaderCalls']==1 and result['productionPromotion'] is False
    assert json.loads((tmp_path/'output/attempt.json').read_text())==result


@pytest.mark.parametrize('change',[{'GITHUB_REF':'refs/heads/feature'},{'GITHUB_EVENT_NAME':'pull_request'},
                                   {'GITHUB_RUN_ATTEMPT':'2'},{'GITHUB_ACTOR':'not-owner'}])
def test_non_main_non_manual_rerun_or_non_owner_blocked(tmp_path,change):
    fix=fixture(tmp_path);fix[2].update(change)
    with pytest.raises(E.Blocked):run(tmp_path,fix)
    assert not any(e[0] in ('POST','MOCK_OUTCOME_READ') for e in fix[-1])


def test_missing_authorization_and_hash_mismatch_are_outcome_free(tmp_path):
    fix=fixture(tmp_path)
    (fix[0]/E.AUTH).unlink()
    with pytest.raises(E.Blocked,match='NO_COMMITTED'):run(tmp_path,fix)
    assert not any(e[0]=='POST' for e in fix[-1])
    other=tmp_path/'other';other.mkdir();fix=fixture(other)
    with pytest.raises(E.Blocked,match='HASH_MISMATCH'):run(other,fix,expected_auth_sha='invalid')
    assert not any(e[0]=='POST' for e in fix[-1])


def test_missing_calibration_or_mismatched_pins_block_before_lock(tmp_path):
    fix=fixture(tmp_path)
    def missing():raise E.Blocked('SUPPLEMENTAL_ABSENT')
    with pytest.raises(E.Blocked,match='SUPPLEMENTAL'):run(tmp_path,fix,pins=missing)
    other=tmp_path/'other';other.mkdir();fix=fixture(other)
    with pytest.raises(E.Blocked,match='MISMATCH'):run(other,fix,pins=lambda:{'pinnedIdentities':{},'executionPins':{}})
    assert not any(e[0]=='POST' for e in fix[-1])


def test_existing_prefix_and_atomic_acquire_failure_zero_outcomes(tmp_path):
    fix=fixture(tmp_path)
    command(fix[1],'update-ref',E.LOCK+'-prior',fix[2]['GITHUB_SHA'])
    with pytest.raises(E.Blocked,match='ALREADY_SPENT'):run(tmp_path,fix)
    other=tmp_path/'other';other.mkdir();fix=fixture(other)
    api=fix[3]
    def denied(method,path,payload):
        return (403,{}) if method=='POST' else api(method,path,payload)
    with pytest.raises(E.Blocked,match='CREATION_FAILED'):run(other,fix,api=denied)
    audit=json.loads((other/'output/attempt.json').read_text())
    assert audit['actualForwardReaderCalls']==0


def test_concurrent_bare_git_attempts_exactly_one_lock(tmp_path):
    fix=fixture(tmp_path)
    def attempt(_):
        try:E.acquire(fix[3],fix[2]['GITHUB_SHA']);return True
        except E.Blocked:return False
    with ThreadPoolExecutor(2) as pool:
        winners=list(pool.map(attempt,range(2)))
    assert sum(winners)==1
    assert command(fix[1],'rev-parse',E.LOCK)==fix[2]['GITHUB_SHA']


def test_post_lock_failure_permanently_consumes_attempt(tmp_path):
    fix=fixture(tmp_path)
    def fail(work,reader):raise RuntimeError('synthetic failure after lock')
    with pytest.raises(RuntimeError):run(tmp_path,fix,execute=fail)
    assert command(fix[1],'rev-parse',E.LOCK)==fix[2]['GITHUB_SHA']
    again=tmp_path/'again';again.mkdir()
    with pytest.raises(E.Blocked,match='ALREADY_SPENT'):run(again,fix)
    assert json.loads((tmp_path/'output/attempt.json').read_text())['status']=='LOCK_SPENT_OR_UNKNOWN_NO_RETRY'


def test_main_moves_after_lock_zero_outcomes_and_lock_still_spent(tmp_path):
    fix=fixture(tmp_path);api=fix[3];created=[False]
    def changed(method,path,payload):
        reply=api(method,path,payload)
        if method=='POST':created[0]=True
        if created[0] and path=='/git/ref/heads/main':return 200,{'object':{'sha':'f'*40}}
        return reply
    with pytest.raises(E.Blocked,match='CURRENT_REMOTE_MAIN'):run(tmp_path,fix,api=changed)
    assert command(fix[1],'rev-parse',E.LOCK)==fix[2]['GITHUB_SHA']
    assert not any(e[0]=='MOCK_OUTCOME_READ' for e in fix[-1])


def supplemental_fixture(tmp_path, mutate=None):
    repo=fixture(tmp_path)[0]
    def write(path,value):
        target=repo/path;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(value));return E.sha(target.read_bytes())
    codes={}
    for path in E.PRODUCER_FILES:
        target=repo/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text('# synthetic producer')
        codes[path]=E.sha(target.read_bytes())
    parent={'code':E.PRODUCER_FILES[0],'codeSha256':codes[E.PRODUCER_FILES[0]],
            'protocol':'parent-protocol.json','protocolSha256':write('parent-protocol.json',{}),
            'result':'parent-result.json','resultSha256':write('parent-result.json',{})}
    prepath='docs/us-readiness/us-cash-profitability-exploratory-preflight-v1.json'
    pre={'counters':{'outcomeReads':0,'intervalComputations':0,'featureBuilds':715}}
    pre_sha=write(prepath,pre)
    protocol={'parent':parent,'dgps':[{'name':f'SYNTHETIC_{n}'} for n in range(15)],
              'sampleLengths':{'weeks':[260,700]},'historicalGeometry':{'source':prepath,'sourceSha256':pre_sha,
              'definedDatesBelowParentMinimum':163},'outcomeFree':True,
              'sizeGrid':{'targetAvailableNamesPerDate':[150,200,244]}}
    protocol_sha=write(E.SUPPLEMENT_PROTOCOL,protocol)
    cells=[{'dgp':d['name'],'weeks':w,'primaryState':'PASS','geometry':{'holds':True},
            'methods':{'CT_SN':{'state':'PASS','metrics':{'coverage90':{'state':'PASS'}}}}}
           for d in protocol['dgps'] for w in [260,700]]
    from pipeline.us_h63_supplemental_calibration import verdict
    result={'contract':'US_H63_INFERENCE_CALIBRATION_V1_SUPPLEMENT','developmentOnly':False,'readsRealData':False,
            'primaryMethod':'CT_SN','replicates':2000,'protocolSha256':protocol_sha,'parent':parent,
            'codeSha256':codes,'cells':cells,'verdict':verdict(cells,30)}
    if mutate:mutate(result)
    result_sha=write(E.SUPPLEMENT_RESULT,result)
    readiness={'counters':pre['counters'],'executed':False,'outcomeFree':True,
               'inputs':{'supplementResult':{'sha256':result_sha},'preflight':{'sha256':pre_sha}},
               'groups':{'calibrationReadiness':{'state':'PASS'}}}
    readiness_sha=write(E.READINESS_V2,readiness)
    acceptance={'contract':'US_H63_SUPPLEMENTAL_ACCEPTANCE_V1','accepted':True,'authorizes':'NOTHING',
                'reviewedBy':'fixture-owner','preflightSha256':pre_sha,'resultSha256':result_sha,
                'protocolSha256':protocol_sha,'readinessV2Sha256':readiness_sha,
                'upperGeometryDisposition':'EXPLICIT_OWNER_ACCEPTED_EXPLORATORY_EXTRAPOLATION'}
    write(E.ACCEPTANCE,acceptance);command(repo,'add','.');command(repo,'commit','-m','Synthetic actual-schema evidence')
    return repo,pre_sha,acceptance


@pytest.mark.parametrize('status',['SUPPLEMENT_BLOCKED','INCONCLUSIVE','UNKNOWN','PASS'])
def test_supplemental_failed_or_invented_verdict_blocked(tmp_path,status):
    repo,pre_sha,_=supplemental_fixture(tmp_path,lambda r:r['verdict'].update(supplementStatus=status))
    with pytest.raises(E.Blocked,match='FAILED_INCONCLUSIVE'):E.supplemental(repo,pre_sha)


@pytest.mark.parametrize('mutation',[
    lambda r:r.update(developmentOnly=True),lambda r:r.update(readsRealData=True),
    lambda r:r['cells'].pop(),lambda r:r['cells'].__setitem__(0,r['cells'][1]),
    lambda r:r['cells'][0]['geometry'].update(holds=False),
    lambda r:r['cells'][0]['methods']['CT_SN']['metrics']['coverage90'].update(state='INCONCLUSIVE'),
    lambda r:r.update(protocolSha256='f'*64),lambda r:r['codeSha256'].update({E.PRODUCER_FILES[0]:'f'*64}),
])
def test_actual_schema_negative_proofs(tmp_path,mutation):
    repo,pre_sha,_=supplemental_fixture(tmp_path,mutation)
    with pytest.raises(E.Blocked):E.supplemental(repo,pre_sha)


def test_actual_schema_pass_hash_and_upper_geometry_gate(tmp_path):
    repo,pre_sha,acceptance=supplemental_fixture(tmp_path)
    assert E.supplemental(repo,pre_sha)['readinessV2Sha256']==acceptance['readinessV2Sha256']
    acceptance['upperGeometryDisposition']='OWNER_REVIEW_REQUIRED'
    path=repo/E.ACCEPTANCE;path.write_text(json.dumps(acceptance));command(repo,'add','.');command(repo,'commit','-m','No upper acceptance')
    with pytest.raises(E.Blocked,match='UNCALIBRATED_UPPER'):E.supplemental(repo,pre_sha)
    acceptance['resultSha256']='f'*64;path.write_text(json.dumps(acceptance));command(repo,'add','.');command(repo,'commit','-m','Wrong hash')
    with pytest.raises(E.Blocked,match='HASH_MISMATCH'):E.supplemental(repo,pre_sha)


def test_owner_must_acknowledge_uncalibrated_upper_geometry(tmp_path):
    fix=fixture(tmp_path);repo=fix[0];auth=json.loads((repo/E.AUTH).read_text())
    auth['acknowledgments'].pop('uncalibratedUpperGeometry331To371')
    (repo/E.AUTH).write_text(json.dumps(auth));command(repo,'add','.');command(repo,'commit','-m','Missing risk acknowledgment')
    fix[2]['GITHUB_SHA']=command(repo,'rev-parse','HEAD')
    command(fix[1],'fetch',str(repo),'main:main')
    with pytest.raises(E.Blocked,match='ACKNOWLEDGMENT'):
        run(tmp_path,fix,expected_auth_sha=E.sha((repo/E.AUTH).read_bytes()))
    assert not any(e[0]=='POST' for e in fix[-1])


def test_workflow_manual_route_excludes_all_original_jobs_and_preserves_steps():
    import re
    root=E.ROOT
    text=(root/E.WORKFLOW).read_text()
    base=command(root,'merge-base','HEAD','refs/remotes/origin/main')
    old=command(root,'show',base+':'+E.WORKFLOW)
    def jobs(source):
        return {m.group(1):m.group(2) for m in re.finditer(r'^  ([a-z0-9-]+):\n(.*?)(?=^  [a-z0-9-]+:|\Z)',source.split('jobs:\n',1)[1],re.M|re.S)}
    before,after=jobs(old),jobs(text)
    before.pop('us-p4',None)
    assert set(after)==set(before)|{'us-p4'}
    for name,body in before.items():
        assert body.split('    runs-on:',1)[1].strip()==after[name].split('    runs-on:',1)[1].strip()
        assert "!(inputs.us_p4_action == 'validate' || inputs.us_p4_action == 'execute')" in after[name]
        # Compare the original expression itself, including always()/needs semantics.
        def condition(block):
            value=block.split('    if:',1)[1].split('    runs-on:',1)[0].strip()
            return value.removeprefix('>-').removeprefix('|').strip()
        legacy=condition(body)
        guarded=condition(after[name]).split('&&',1)[1].strip()
        assert re.sub(r'\s+','',guarded[1:-1])==re.sub(r'\s+','',legacy)
    trigger=text.split('on:\n',1)[1].split('permissions:',1)[0]
    assert re.findall(r'^  ([a-z_]+):',trigger,re.M)==['workflow_dispatch']
    assert "default: none" in trigger and "cancel-in-progress: false" in text
    new=after['us-p4']
    assert "github.ref == 'refs/heads/main'" in new and "github.event_name == 'workflow_dispatch'" in new
    assert 'signal-history' not in new and 'secrets.DART' not in new
    assert 'actions/upload-artifact@v4' in new and 'if: always()' in new


def test_templates_never_authorize_and_original_p4_files_unchanged():
    root=E.ROOT
    base=command(root,'merge-base','HEAD','refs/remotes/origin/main')
    for p in ('docs/us-readiness/us-p4-owner-authorization-template-v1.json',
              'docs/us-readiness/us-h63-supplemental-acceptance-template-v1.json'):
        assert json.loads((root/p).read_text())['authorizes']=='NOTHING'
    for p in ('pipeline/us_cash_profitability_exploratory.py','scripts/run_us_cash_profitability_exploratory.py',
              'pipeline/us_h63_inference_calibration.py','pipeline/us_cash_profitability.py',
              'docs/us-readiness/us-cash-profitability-exploratory-preflight-v1.json',
              'docs/us-readiness/us-cash-profitability-exploratory-readiness-v1.json',
              'tests/test_workflow_inventory.py','tests/test_kr_alpha_atlas_price_repair_workflow_inventory.py'):
        assert (root/p).read_bytes()==E.git(['show',base+':'+p],root)
