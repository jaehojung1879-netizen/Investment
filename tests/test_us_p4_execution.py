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


@pytest.mark.parametrize('verdict',['FAIL','INCONCLUSIVE','UNKNOWN'])
def test_supplemental_failed_or_inconclusive_blocked(tmp_path,verdict):
    fix=fixture(tmp_path);repo=fix[0]
    result=repo/'synthetic-result.json';result.write_text(json.dumps({'verdict':verdict}))
    protocol=repo/'synthetic-protocol.json';protocol.write_text('{}')
    pre=repo/'docs/us-readiness/us-cash-profitability-exploratory-preflight-v1.json';pre.write_text('{}')
    acceptance={'contract':'US_H63_SUPPLEMENTAL_ACCEPTANCE_V1','accepted':True,'authorizes':'NOTHING','reviewedBy':'fixture',
                'preflightSha256':E.sha(pre.read_bytes()),'resultPath':'synthetic-result.json','resultSha256':E.sha(result.read_bytes()),
                'protocolPath':'synthetic-protocol.json','protocolSha256':E.sha(protocol.read_bytes()),'overallVerdictPointer':'/verdict'}
    (repo/E.ACCEPTANCE).write_text(json.dumps(acceptance));command(repo,'add','.');command(repo,'commit','-m','synthetic failing evidence')
    with pytest.raises(E.Blocked,match='FAILED_INCONCLUSIVE'):
        E.supplemental(repo,E.sha(pre.read_bytes()))


def test_supplemental_pass_requires_geometry_hash_and_zero_outcomes(tmp_path):
    fix=fixture(tmp_path);repo=fix[0]
    data={'verdict':'PASS','horizonSessions':63,'statistic':'CT_SN','criticalValue':28.31,'minimumNames':150,
          'maximumNames':244,'underCalibratedDates':163,'outcomeReads':0}
    result=repo/'synthetic-result.json';result.write_text(json.dumps(data))
    protocol=repo/'synthetic-protocol.json';protocol.write_text('{}')
    pre=repo/'docs/us-readiness/us-cash-profitability-exploratory-preflight-v1.json';pre.write_text('{}')
    code=repo/'pipeline/synthetic_calibration.py';code.parent.mkdir();code.write_text('# SYNTHETIC code identity only')
    data.update(protocolIdentity=E.sha(protocol.read_bytes()),producerSha=E.sha(code.read_bytes()))
    result.write_text(json.dumps(data))
    acceptance={'contract':'US_H63_SUPPLEMENTAL_ACCEPTANCE_V1','accepted':True,'authorizes':'NOTHING','reviewedBy':'fixture',
                'preflightSha256':E.sha(pre.read_bytes()),'resultPath':result.name,'resultSha256':E.sha(result.read_bytes()),
                'protocolPath':protocol.name,'protocolSha256':E.sha(protocol.read_bytes()),'overallVerdictPointer':'/verdict',
                'proofPointers':{k:'/'+k for k in data if k not in ('verdict','protocolIdentity','producerSha')},
                'protocolIdentityKind':'FILE_BYTES_SHA256','protocolIdentityPointer':'/protocolIdentity',
                'producerCodePointers':{'pipeline/synthetic_calibration.py':'/producerSha'}}
    path=repo/E.ACCEPTANCE;path.write_text(json.dumps(acceptance));command(repo,'add','.');command(repo,'commit','-m','synthetic accepted evidence')
    assert E.supplemental(repo,E.sha(pre.read_bytes()))['supplementalResultSha256']==E.sha(result.read_bytes())
    acceptance['resultSha256']='f'*64;path.write_text(json.dumps(acceptance));command(repo,'add','.');command(repo,'commit','-m','synthetic wrong hash')
    with pytest.raises(E.Blocked,match='HASH_MISMATCH'):E.supplemental(repo,E.sha(pre.read_bytes()))


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
