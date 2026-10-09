"""Versioned pre-outcome input amendment using the unchanged v1 research engine.

No duplicated scientific functions. Both versions claim the identical permanent
GitHub ref and artifact namespace. Audit/preflight never invokes formal().
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict
import json
import os
from pathlib import Path
import resource
import subprocess
import time
from unittest.mock import patch

import numpy as np
import pandas as pd

from pipeline import kr_alpha_atlas_inputs as AI
from pipeline import kr_alpha_atlas_readiness as RD, kr_alpha_atlas_registry as REG
from pipeline import kr_model_raw_snapshot as RAW
from pipeline.kr_alpha_atlas_integrity_audit import (
    AuditCounters, outcome_free_firewall, resource_facts, persistence_probe,
)
from pipeline.kr_alpha_atlas_price_integrity import (
    CORRECTION, BENCHMARK_REPORT, STOCK_REPORT,
)
from pipeline.kr_alpha_atlas_phase_c import contract, executor, labels, lifecycle, preflight, synthetic

AMENDMENT = 'research_specs/kr-alpha-atlas-phase-c-v2-amendment.json'
SIDECAR = 'research_specs/kr-alpha-atlas-phase-c-v2-amendment.sha256'
ORIGINAL_SHA = 'b57be30ce54abf1dd26388954053e99d4b1bf71fa06f3598787317e953988db0'
GLOBAL_LOCK = 'refs/tags/kr-alpha-atlas-phase-c-v1-execution-lock'
ADDITIONAL_FILES = [
    'pipeline/kr_alpha_atlas_phase_c_amendment.py',
    'pipeline/kr_alpha_atlas_price_integrity.py',
    'pipeline/kr_alpha_atlas_integrity_audit.py',
    'pipeline/kr_alpha_atlas_benchmark_audit.py',
    'scripts/run_kr_alpha_atlas_phase_c_amended.py',
    'scripts/audit_kr_alpha_atlas_price_integrity.py',
    '.github/workflows/kr-alpha-atlas-phase-c-amended.yml',
    'tests/test_kr_alpha_atlas_phase_c_amendment.py',
    'tests/test_workflow_inventory.py',
    'docs/workflow-inventory-phase-c-amendment.md',
    CORRECTION, BENCHMARK_REPORT, STOCK_REPORT,
]


def read_correction(root):
    root = Path(root)
    correction = json.loads((root/CORRECTION).read_text())
    if correction['originalSpecFileSha256'] != ORIGINAL_SHA:
        raise ValueError('WRONG_ORIGINAL_REGISTRATION')
    for path, expected in correction['sourceHashes'].items():
        p = (root/path).resolve()
        if not p.is_relative_to(root.resolve()) or contract.file_hash(p)!=expected:
            raise ValueError('CORRECTED_SOURCE_IDENTITY_CHANGED')
    if (correction['finalSourceSession']!='2026-09-14' or
            len(correction['finalSessionQuotes'])!=235 or
            correction['stockRules']!=[{'ticker':'006800.KS','policy':'WITHHOLD_FULL_SECURITY_PRICE_BASIS',
                'reason':'UNRESOLVED_CORPORATE_ACTION_SOURCE_BASIS_2018_AND_2026',
                'scope':'Every date and horizon; outcome-blind symmetric refusal. Universe identity and verified raw-KRX non-price/accounting information are retained. Selected unpriceable name blocks the paired economics.',
                'noZeroPayoffOrLastPriceExit':True}]):
        raise ValueError('UNREGISTERED_PRICE_CORRECTION_SCOPE')
    report = json.loads((root/BENCHMARK_REPORT).read_text())
    if contract.file_hash(root/BENCHMARK_REPORT)!=correction['benchmarkEvidenceSha256']:
        raise ValueError('BENCHMARK_EVIDENCE_CHANGED')
    if (contract.file_hash(root/STOCK_REPORT)!=correction['stockEvidenceSha256'] or
            contract.file_hash(root/'docs/audits/kr-alpha-atlas-phase-c-integrity/final-session-source-integrity.json')!=correction['finalSessionEvidenceSha256']):
        raise ValueError('STOCK_SOURCE_EVIDENCE_CHANGED')
    final=json.loads((root/'docs/audits/kr-alpha-atlas-phase-c-integrity/final-session-source-integrity.json').read_text())
    if (correction['benchmarkQuotes']!=report['correctedBenchmarkQuotes'] or
            correction['finalSessionQuotes']!=final['correctedFinalQuotes']):
        raise ValueError('CORRECTED_QUOTES_DISAGREE_WITH_SOURCE_EVIDENCE')
    required = contract.load(root)['chronology']['evaluationYears']
    cells = report['annualComparisons']
    if (report['ticker']!='069500.KS' or report['aggregateStatus']!='PASS' or
            report['threshold']!=0.005 or report['requiredYears']!=required or
            [r['year'] for r in cells]!=list(range(2013,2027)) or
            any(r['status']!='PASS' or not r['identicalSessionCoverage'] or
                r['matchingSessions']!=r['expectedSessions'] or
                abs(r['differencePercentagePoints'])>0.5 for r in cells)):
        raise ValueError('COMPLETE_FIXED_THRESHOLD_RECONCILIATION_REQUIRED')
    return correction


def corrected_identity(base, correction, sha):
    identity = deepcopy(base)
    identity.pop('sha256')
    identity['originalPhaseBInputsSha256'] = base['sha256']
    identity['preOutcomeInputCorrectionSha256'] = sha
    identity['correctionBasis'] = correction['basis']
    identity['sha256'] = contract.digest(identity)
    return identity


def overlay(inputs, correction, sha):
    """Same-session quotation adjustment only; no stock forward-return calculation."""
    original = contract.load()
    if inputs.identity!=original['phaseBIdentity']['inputs']:
        raise ValueError('ORIGINAL_INPUT_LINEAGE_CHANGED')
    benchmark = pd.DataFrame(correction['benchmarkQuotes'])
    if set(benchmark)!= {'date','Close'} or benchmark.date.duplicated().any():
        raise ValueError('CORRECTED_BENCHMARK_SCHEMA')
    benchmark.index = pd.to_datetime(benchmark.pop('date'))
    if (not benchmark.index.is_monotonic_increasing or
            not np.isfinite(benchmark.Close).all() or (benchmark.Close<=0).any()):
        raise ValueError('INVALID_CORRECTED_BENCHMARK_QUOTE')
    inputs.prices = dict(inputs.prices)
    inputs.prices['069500.KS'] = benchmark
    # Refuse every original last-session stock bar first. Only exactly identified
    # raw-KRX, basis-compatible replacements may enter the corrected view.
    for ticker, original_frame in list(inputs.prices.items()):
        if ticker=='069500.KS':
            continue
        frame=original_frame.copy()
        final=frame.index==pd.Timestamp(correction['finalSourceSession'])
        for column in ('Open','High','Low','Close','Volume'):
            if column in frame:
                frame.loc[final,column]=np.nan
        inputs.prices[ticker]=frame
    for quote in correction['finalSessionQuotes']:
        if quote['ticker'] not in inputs.prices:
            raise ValueError('CORRECTED_SOURCE_SECURITY_ABSENT')
        frame=inputs.prices[quote['ticker']]
        stamp=pd.Timestamp(quote['date'])
        if stamp not in frame.index:
            raise ValueError('CORRECTED_SOURCE_SESSION_ABSENT')
        for column in ('Open','High','Low','Close','Volume'):
            frame.loc[stamp,column]=quote[column]
    for rule in correction['stockRules']:
        frame = inputs.prices[rule['ticker']].copy()
        for column in ('Open','High','Low','Close'):
            if column in frame:
                frame.loc[:,column] = np.nan
        inputs.prices[rule['ticker']] = frame
    inputs.identity = corrected_identity(inputs.identity,correction,sha)
    return inputs


@contextmanager
def corrected_loader(root):
    """Scoped loader injection into the identical frozen prepare()/build_matrix().

    Fixed single-thread execution; no global replacement outside this context.
    The original loader verifies every legacy snapshot before the explicit overlay.
    """
    correction = read_correction(root)
    original_loader = AI.load_inputs
    sha = contract.file_hash(Path(root)/CORRECTION)
    def selected(commit, work, repo):
        inputs = original_loader(commit,work,repo)
        return overlay(inputs,correction,sha)
    with patch.object(AI,'load_inputs',selected):
        yield


def expected_effective(root, amendment):
    base = contract.load(root)
    if contract.file_hash(Path(root)/contract.SPEC)!=ORIGINAL_SHA:
        raise ValueError('ORIGINAL_V1_CHANGED')
    correction = read_correction(root)
    effective = deepcopy(base)
    effective['version'] = 2
    effective['registrationAmendmentId'] = 'kr-alpha-atlas-phase-c-v2-input-integrity'
    effective['phaseBIdentity']['inputs'] = corrected_identity(base['phaseBIdentity']['inputs'],correction,contract.file_hash(Path(root)/CORRECTION))
    effective['phaseBIdentity']['matrixDigest'] = amendment['correctedMatrixDigest']
    effective['primaryFrozenSnapshot'] = 'EXPLICIT_VERSIONED_OVERLAY_ON_ORIGINAL_GIT_PINNED_PROXY_INPUTS; original Phase B identities remain preserved'
    effective['benchmarkIntegrity'] = {
        'status':'RECONCILED_DEFINITION_COMPATIBLE', 'claimGate':'VERIFIED',
        'externalCheck':base['benchmarkIntegrity']['externalCheck'],
        'frozenDecision':'069500.KS gross shareholder total return uses official raw ETF market quotes and complete bridged gross distribution records exactly once. Independent price-source reconstruction passes every required year; no threshold relaxation.',
        'evidenceFileSha256':contract.file_hash(Path(root)/BENCHMARK_REPORT),
        'economicDefinition':correction['benchmarkDefinition'],
        'independenceLimit':'Independent price publisher; both reconstructions share authoritative issuer cash observations. This does not verify NAV returns, investor net-tax returns or actual payment-date cash execution.',
    }
    effective['targets']['basis']='PARTIAL_DISTRIBUTION_STOCK_ADJUSTED_INDEX_MINUS_VERIFIED_GROSS_ETF_SHAREHOLDER_TOTAL_RETURN'
    effective['targets']['benchmarkGross']='Official ETF market price with complete gross cash entitlements reinvested once at ex-date close; same entry/exit sessions; no KOSPI200 substitution.'
    effective['sourceLimitations']=[
        ('BENCHMARK: official 069500.KS gross ETF shareholder total return reconciled in the authorized outcome-blind amendment; independent price publisher shares the official cash observations. Stock distribution coverage remains partial, and gross total-return-index reinvestment is not payment-date cash execution or investor after-tax return.'
         if x.startswith('BENCHMARK 069500.KS') else x)
        for x in base['sourceLimitations']
    ]+['STOCK SOURCE AUDIT: six predeclared names in three fixed windows; no certification of every historical stock action. 006800.KS entire price basis is withheld because 2018 and 2026 action scales remain unresolved. Last-session raw-KRX replacements require verified same-session basis and positive trading volume; absent/suspended names stay invalid.']
    effective['lifecycle']['authorizationPath'] = 'research_specs/kr-alpha-atlas-phase-c-v2-execution-authorization.json'
    # Both old and amended formal paths atomically compete for this SAME ref.
    if effective['lifecycle']['lockPrefix']!=GLOBAL_LOCK:
        raise ValueError('SHARED_GLOBAL_ONE_SHOT_NAMESPACE_REQUIRED')
    effective['inputIntegrityAmendment'] = {
        'correctionFileSha256':contract.file_hash(Path(root)/CORRECTION),
        'stockRule':correction['stockRules'],
        'validity':'The one unresolved stock price basis is withheld for the complete security, across all hypotheses and portfolios. Original final-session bars are refused; only identified raw-KRX replacements are admitted. Unpriceable forecasts still participate in selection and block paired economics. Unknown payout is never zero or last-price exit.',
        'originalMatrixDigest':base['phaseBIdentity']['matrixDigest'],
        'noHypothesisThresholdModelHorizonOrPortfolioChange':True,
    }
    effective['dependencyHashes'] = {**base['dependencyHashes'], **amendment['additionalDependencyHashes']}
    return effective


def load(root=contract.ROOT):
    root = Path(root)
    if contract.file_hash(root/AMENDMENT)!=(root/SIDECAR).read_text().strip():
        raise ValueError('AMENDMENT_FILE_DIGEST_CHANGED')
    amendment = json.loads((root/AMENDMENT).read_text())
    if amendment['originalSpecFileSha256']!=ORIGINAL_SHA or amendment['globalOneShotLock']!=GLOBAL_LOCK:
        raise ValueError('AMENDMENT_BASE_OR_NAMESPACE_CHANGED')
    expected = {p:contract.file_hash(root/p) for p in ADDITIONAL_FILES}
    if amendment['additionalDependencyHashes']!=expected:
        raise ValueError('AMENDED_DEPENDENCY_CHANGED')
    effective = expected_effective(root,amendment)
    if amendment['effectiveContractSha256']!=contract.digest(effective):
        raise ValueError('AMENDED_CONTRACT_CHANGED')
    if (amendment['originalMatrixDigest']!=contract.load(root)['phaseBIdentity']['matrixDigest'] or
            not isinstance(amendment['correctedMatrixDigest'],str) or len(amendment['correctedMatrixDigest'])!=64):
        raise ValueError('MATRIX_REGISTRATION_INCOMPLETE')
    return effective


def prepare(root, spec, work):
    with corrected_loader(root):
        data, identity = preflight.prepare(root,spec,None,work)
    identity['formalInputBasis'] = 'PHASE_C_V2_EXPLICIT_PRICE_INTEGRITY_OVERLAY'
    identity['originalPhaseBMatrixDigest'] = contract.load(root)['phaseBIdentity']['matrixDigest']
    identity['amendmentFileSha256'] = contract.file_hash(Path(root)/AMENDMENT)
    identity['stockSourceIntegrityPolicy'] = spec['inputIntegrityAmendment']['validity']
    return data, identity


def source_readiness(data,spec,*,require_ready=True):
    """Reuse Phase B's outcome-free coverage/cell rules; never select new factors."""
    registry=REG.load()
    features=RD.build_features_report(data,registry,spec['developmentCutoff'])
    baselines=RD.baseline_readiness(registry,features,data)
    interactions=RD.interaction_readiness(data,registry,features)
    eligible={f['featureId']:features[f['featureId']] for f in spec['eligibleFeatures']}
    below=[f for f,r in eligible.items() if r['measuredStatus']!='MEASURED_READY']
    baseline_blocked=[k for k,b in baselines.items() if b['status']!='READY']
    if require_ready and (below or baseline_blocked):
        raise ValueError('CORRECTED_INPUT_READY_FLOOR_BLOCKER: '+','.join(sorted(below)))
    return {'eligibleFeatureCoverage':eligible,'baselines':baselines,'interactions':interactions,
            'registeredRulesUnchanged':RD.RULES,'newFactorsAdded':0,
            'status':'BLOCKED_PRE_OUTCOME' if below or baseline_blocked else 'READY',
            'featuresBelowOriginalFloor':sorted(below),'baselinesBlocked':baseline_blocked}


def audit(root, work, expected_main):
    """Identical real-input preparation, with hard outcome/fit/lock firewall."""
    root, work = Path(root), Path(work)
    work.mkdir(parents=True,exist_ok=False)
    github = lifecycle.GitHub()
    if github.main()!=expected_main:
        raise ValueError('LATEST_MAIN_CHANGED')
    subprocess.run(['git','merge-base','--is-ancestor',expected_main,'HEAD'],cwd=root,check=True)
    spec = load(root)
    if github.locks(GLOBAL_LOCK) or github.previous_results(spec['lifecycle']['artifactPrefix']):
        raise ValueError('STUDY_ALREADY_CONSUMED')
    runtime = preflight.verify_runtime(spec)
    before = resource_facts(work)
    if before['memoryCapacityBytes']<spec['compute']['memoryBytes'] or before['diskFreeBytes']<1024**3:
        raise ValueError('PRE_OUTCOME_RESOURCE_CAPACITY_BLOCKER')
    started = time.monotonic()
    with outcome_free_firewall() as attempts:
        data,identity = prepare(root,spec,work/'inputs')
        readiness = data.validate_features(spec)
        # Persist a structured audit refusal instead of losing the already
        # verified matrix/PIT and exact coverage when a source gate is blocked.
        # Formal preparation keeps require_ready=True and cannot claim a lock.
        coverage=source_readiness(data,spec,require_ready=False)
        probe = persistence_probe(work)
    elapsed = time.monotonic()-started
    if elapsed>spec['compute']['wallSeconds']:
        raise ValueError('PRE_OUTCOME_PREPARATION_TIME_BUDGET_EXCEEDED')
    if github.main()!=expected_main or github.locks(GLOBAL_LOCK):
        raise ValueError('MAIN_OR_LOCK_CHANGED_DURING_SAFE_PREFLIGHT')
    load(root)
    common = (data.rows.date>='2016-04-01') & (data.rows.date<=spec['developmentCutoff'])
    b4 = data.values.loc[common,spec['baselines']['B4_COMBINED_SIMPLE']].notna().all(axis=1)
    withheld=data.rows.loc[data.rows.ticker.eq('006800.KS')]
    source_attrition={'security':'006800.KS','policy':'FULL_SECURITY_PRICE_BASIS_WITHHELD',
                      'referenceNameDateRows':len(data.rows),'affectedNameDateRows':len(withheld),
                      'referenceShare':len(withheld)/len(data.rows),
                      'affectedRowsByYear':withheld.groupby(withheld.date.str[:4]).size().to_dict(),
                      'affectedRowsByIndustry':withheld.groupby('industry').size().to_dict(),
                      'scope':'Source/calendar counts only, not constructed labels. Industry cohorts with an invalid peer remain subject to the original symmetric LOO refusal.'}
    report = {'status':('BLOCKED_PRE_OUTCOME_SOURCE_COVERAGE' if coverage['status']=='BLOCKED_PRE_OUTCOME'
                       else 'PASS_OUTCOME_FREE_CORRECTED_PREPARATION'),'expectedMain':expected_main,
              'reconstructionStatus':'PASS_EXACT_CORRECTED_MATRIX_AND_PIT',
              'registrationFileSha256':contract.file_hash(root/AMENDMENT),
              'effectiveContractSha256':contract.digest(spec),'identity':identity,
              'expectedMatrixDigest':spec['phaseBIdentity']['matrixDigest'],
              'actualMatrixDigest':identity['matrixDigest'],'readiness':readiness,
              'correctedSourceReadiness':coverage,
              'securities':int(data.rows.ticker.nunique()),'eligibleCandidates':len(spec['eligibleFeatures']),
              'b4CommonRows':int(common.sum()),'b4CommonCompleteCasePct':float(b4.mean()*100),
              'sourceIntegrityAttrition':source_attrition,
              'runtime':runtime,'resourcesBefore':before,'resourcesAfter':resource_facts(work),
              'elapsedSeconds':round(elapsed,3),'maxRssBytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
              'persistenceProbe':probe,'firewallBlockedCalls':attempts,'counters':asdict(AuditCounters()),
              'sourceSchemas':preflight.verify_source_schema_samples(root,spec),
              'benchmarkIntegrity':spec['benchmarkIntegrity'],
              'excludedLayers':['authorization','lock creation','targets','model fits','IC/spreads','portfolios','formal results']}
    RAW.immutable_bytes(work/'corrected-preflight.json',contract.canonical(report)+b'\n')
    return report


def formal(root=contract.ROOT, *, work, github=None):
    """One original study, corrected registration; owner approval is mandatory."""
    root,work = Path(root),Path(work)
    github = github or lifecycle.GitHub()
    # Parse only. Actual main and the owner approval precede exact validation.
    meta=json.loads((root/AMENDMENT).read_text())
    spec=json.loads((root/contract.SPEC).read_text())
    spec['lifecycle']['authorizationPath']='research_specs/kr-alpha-atlas-phase-c-v2-execution-authorization.json'
    counters = labels.Counters()
    budget = executor.Budget(spec)
    audit_doc = {}
    head = None
    output = work/'results'
    def checks():
        nonlocal head,spec
        head = subprocess.check_output(['git','rev-parse','HEAD'],cwd=root).decode().strip()
        if github.main()!=head or subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=root).strip():
            raise ValueError('ACTUAL_CLEAN_MERGED_MAIN_REQUIRED')
        path = root/spec['lifecycle']['authorizationPath']
        if not path.exists():
            raise ValueError('EXPLICIT_HUMAN_AMENDED_EXECUTION_AUTHORIZATION_ABSENT')
        wanted = {'studyId':contract.STUDY,'action':'ONE_FORMAL_EXECUTION','authorizedBy':lifecycle.HUMAN,
                  'originalSpecFileSha256':ORIGINAL_SHA,'amendmentFileSha256':contract.file_hash(root/AMENDMENT),
                  'effectiveContractSha256':meta['effectiveContractSha256'],
                  'dependencyManifestSha256':contract.digest({**spec['dependencyHashes'],**meta['additionalDependencyHashes']})}
        if json.loads(path.read_text())!=wanted:
            raise ValueError('AUTHORIZATION_NOT_EXACT_AMENDED_CONTRACT')
        committed = subprocess.check_output(['git','log','-1','--format=%H','--',spec['lifecycle']['authorizationPath']],cwd=root).decode().strip()
        if (not committed or github.human_author(committed)!=lifecycle.HUMAN or
                os.environ.get('GITHUB_EVENT_NAME')!='workflow_dispatch' or
                os.environ.get('GITHUB_ACTOR')!=lifecycle.HUMAN or os.environ.get('GITHUB_REF')!='refs/heads/main'):
            raise ValueError('OWNER_COMMITTED_APPROVAL_AND_MAIN_MANUAL_DISPATCH_REQUIRED')
        audit_doc['authorization']={**wanted,'authorizationCommit':committed}
        spec=load(root)
        if (root/spec['lifecycle']['resultPath']).exists() or github.previous_results(spec['lifecycle']['artifactPrefix']) or github.locks(GLOBAL_LOCK):
            raise ValueError('ORIGINAL_STUDY_ALREADY_CONSUMED')
    def pre():
        preflight.verify_runtime(spec)
        resources = resource_facts(work.parent)
        if resources['memoryCapacityBytes']<spec['compute']['memoryBytes'] or resources['diskFreeBytes']<1024**3:
            raise ValueError('PRE_OUTCOME_RESOURCE_CAPACITY_BLOCKER')
        data,identity = prepare(root,spec,work/'inputs')
        audit_doc['inputs']=identity
        synthetic.smoke(spec)
        data.validate_features(spec)
        source_readiness(data,spec)
        budget.check()
        output.mkdir(parents=True,exist_ok=True)
        persistence_probe(work)
        RAW.immutable_bytes(work/'preflight.json',contract.canonical(audit_doc)+b'\n')
        if github.main()!=head or github.locks(GLOBAL_LOCK):
            raise ValueError('MAIN_OR_LOCK_CHANGED_DURING_PREFLIGHT')
        load(root)
        return data
    def run(data,receipt):
        RAW.immutable_bytes(output/'lock-receipt.json',contract.canonical(receipt.document)+b'\n')
        permit = labels.formal_permit(data.source_identity,receipt)
        result = executor.execute(data,spec,permit,counters=counters,budget=budget)
        load(root)
        audit_doc.update(head=head,amendmentFileSha256=contract.file_hash(root/AMENDMENT),lock=receipt.document,counters=asdict(counters),runtime=preflight.verify_runtime(spec))
        return executor.persist(result,output,audit_doc)
    def failed(error,receipt):
        try:
            consumed = receipt is not None or bool(github.locks(GLOBAL_LOCK))
        except RuntimeError:
            RAW.immutable_bytes(work/'lock-status-unknown.json',contract.canonical({'status':'VERIFY_LOCK_BEFORE_ANY_RECOVERY','errorClass':type(error).__name__})+b'\n')
            return
        where = output/'consumed-failure.json' if consumed else work/'pre-outcome-failure.json'
        RAW.immutable_bytes(where,contract.canonical({'status':'CONSUMED_NO_RETRY' if consumed else 'NOT_CONSUMED',
            'errorClass':type(error).__name__,'counters':asdict(counters),'exactByteRecoveryOnly':consumed})+b'\n')
    return lifecycle.ordered_once(checks=checks,prepare=pre,
        claim=lambda:github.claim(GLOBAL_LOCK,head,contract.file_hash(root/AMENDMENT)),run=run,on_failure=failed)
