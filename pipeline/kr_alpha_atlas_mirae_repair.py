"""Additive source-segment repair. The frozen v1/v2 engines stay byte-identical.

An unvalued cross-class subscription right is a boundary, never a fitted factor.
Only the source validity of 006800 is extended; no research function is replaced.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict
import gzip
import hashlib
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
from pipeline import kr_alpha_atlas_bars as B
from pipeline import kr_alpha_atlas_phase_c_amendment as V2
from pipeline import kr_industry_anatomy_execution as IE
from pipeline import kr_value_quality_catalyst as VQ
from pipeline import kr_model_raw_snapshot as RAW
from pipeline.kr_alpha_atlas_integrity_audit import (
    AuditCounters, outcome_free_firewall, persistence_probe, resource_facts,
)
from pipeline.kr_alpha_atlas_phase_c import contract, executor, labels, lifecycle, preflight, synthetic

BASE = 'docs/audits/kr-alpha-atlas-phase-c-integrity/mirae-source-recovery'
CORRECTION = BASE + '/006800-source-correction.json'
ADDENDUM = 'research_specs/kr-alpha-atlas-phase-c-v3-price-repair.json'
SIDECAR = 'research_specs/kr-alpha-atlas-phase-c-v3-price-repair.sha256'
PARENT_SHA = 'ca2564703dc018474a3d041f95d86bf16aa053a91ca4453cb975801c17a577bb'
TICKER = '006800.KS'
QUARANTINE = ('2018-01-23',)
AUTHORIZATION = 'research_specs/kr-alpha-atlas-phase-c-v3-execution-authorization.json'
ADDITIONAL_FILES = (
    'pipeline/kr_alpha_atlas_mirae_repair.py',
    'pipeline/kr_alpha_atlas_mirae_source_audit.py',
    'scripts/run_kr_alpha_atlas_phase_c_price_repair.py',
    '.github/workflows/kr-alpha-atlas-phase-c-price-repair.yaml',
    'tests/test_kr_alpha_atlas_mirae_repair.py',
    'tests/test_kr_alpha_atlas_price_repair_workflow_inventory.py',
    'docs/workflow-inventory-phase-c-price-repair.md',
    CORRECTION, BASE+'/sources.json', BASE+'/source-validity-policy.json',
    BASE+'/source-diagnostic.json',
    # Preserve the first authoring closure and receipt. Raw source bytes are
    # gzip-packed for the existing UTF-8 invariant; numeric inputs do not change.
    *(BASE+'/authoring-before-capture-packaging/'+p for p in (
        'registration.json','registration.sha256','sources.json',
        'source-diagnostic.json','full-input-preflight.json',
        'packaging-erratum.json','repair-module.py.txt')),
)


def read_correction(root=contract.ROOT):
    root = Path(root)
    q = json.loads((root / CORRECTION).read_text())
    if (q['ticker'] != TICKER or tuple(q['quarantinedSessions']) != QUARANTINE or
            q['sourceCommit'] != contract.load(root)['phaseBIdentity']['inputs']['sourceCommit'] or
            q['stockDividendEvent']['commonSharesPerCommonShare'] != 0.0073206 or
            q['stockDividendEvent']['cashKrwPerCommonShare'] != 300.0 or
            q['stockDividendEvent']['exDate'] != '2026-03-16' or
            q['rightsEvent']['valueOrAdjustmentFactor'] is not None):
        raise ValueError('UNREGISTERED_SOURCE_REPAIR_SCOPE')
    manifest = json.loads((root / q['newSourceManifest']).read_text())
    for record in manifest:
        if 'path' not in record:
            continue  # Explicit source refusal, not an observation.
        stored = (root / BASE / record['path']).read_bytes()
        if hashlib.sha256(stored).hexdigest() != record['storedSha256']:
            raise ValueError('CORPORATE_ACTION_SOURCE_BYTES_CHANGED')
        raw = gzip.decompress(stored) if record.get('compression') == 'gzip' else stored
        if len(raw) != record['bytes'] or hashlib.sha256(raw).hexdigest() != record['sha256']:
            raise ValueError('CORPORATE_ACTION_RAW_IDENTITY_CHANGED')
    policy = json.loads((root/BASE/'source-validity-policy.json').read_text())
    if (policy['correctionFileSha256'] != contract.file_hash(root/CORRECTION) or
            tuple(policy['quarantinedSessions']) != QUARANTINE or
            not policy['specifiedBeforeCorrectedCoverageAccess'] or
            not policy['everyCrossingWindowInvalid']):
        raise ValueError('OUTCOME_BLIND_SOURCE_POLICY_CHANGED')
    return q


def verify_raw_quotes(root, q):
    """Compare every correction quote with exact original KRX rows, no returns."""
    rows = []
    for path, identity in sorted(q['rawQuoteIdentity'].items()):
        if not path.startswith('ledger/prices/kr/'):
            continue
        blob = AI.git_blob(root, q['sourceCommit'], path)
        git_sha = hashlib.sha1(b'blob ' + str(len(blob)).encode() + b'\0' + blob).hexdigest()
        if (git_sha != identity['gitBlobSha1'] or
                hashlib.sha256(blob).hexdigest() != identity['rawSha256']):
            raise ValueError('ORIGINAL_KRX_SOURCE_CHANGED')
        for line in gzip.decompress(blob).splitlines():
            row = json.loads(line)
            if row['ticker'] == TICKER:
                rows.append(row)
    if sorted(rows, key=lambda r: r['date']) != q['rawQuotes']:
        raise ValueError('SOURCE_REPAIR_NOT_EXACT_ORIGINAL_KRX_QUOTES')


def reconstruct(q):
    """OHLC quotation factors only. Never divide two stock holding prices."""
    rows = q['rawQuotes']
    if not rows or len({r['date'] for r in rows}) != len(rows) or rows != sorted(rows, key=lambda r: r['date']):
        raise ValueError('NON_CANONICAL_RAW_SOURCE')
    events = {r['date']: r for r in q['registeredPartialEvents']}
    quarantined = set(q['quarantinedSessions'])
    factor, units, previous = 1.0, 1.0, None
    output = []
    for row in rows:
        d = row['date']
        values = [row[k] for k in ('open', 'high', 'low', 'close', 'volume')]
        if (not np.isfinite(values).all() or row['volume'] <= 0 or
                not 0 < row['low'] <= min(row['open'], row['close']) <= max(row['open'], row['close']) <= row['high']):
            raise ValueError('INVALID_RAW_KRX_OHLCV')
        if d in quarantined:
            # Independent segment normalization carries no right valuation.
            factor, units = 1.0, 1.0
        else:
            event = events.get(d, {})
            cash = float(event.get('dividend') or 0.0)
            share = float(event.get('split') or 1.0)
            if d == q['stockDividendEvent']['exDate']:
                cash = q['stockDividendEvent']['cashKrwPerCommonShare']
                share = 1.0 + q['stockDividendEvent']['commonSharesPerCommonShare']
            if cash:
                if previous is None or not 0 < cash < previous:
                    raise ValueError('CASH_FACTOR_WITHOUT_VALID_PREVIOUS_RAW_QUOTE')
                factor /= 1.0 - cash / previous  # Original partial-index definition.
            factor *= share
            units *= share
        output.append({'date': d, **{k.title(): (None if d in quarantined else row[k] * factor)
                                    for k in ('open', 'high', 'low', 'close')},
                       'Volume': row['volume'] / units})
        previous = row['close']
    frame = pd.DataFrame(output).set_index('date')
    frame.index = pd.to_datetime(frame.index)
    return frame.astype(float)


def repaired_identity(parent, correction_sha):
    out = deepcopy(parent)
    out.pop('sha256')
    out['parentV2InputsSha256'] = parent['sha256']
    out['sourceSegmentRepairSha256'] = correction_sha
    out['sourceSegmentPolicy'] = '006800_OFFICIAL_RAW_KRX_CONNECTED_SEGMENTS_NO_2018_RIGHTS_BRIDGE'
    out['sha256'] = contract.digest(out)
    return out


def window_valid(frame, days, pos, length):
    if pos - length + 1 < 0 or pos >= len(days):
        return False
    c = frame.Close.reindex(days[pos-length+1:pos+1]).to_numpy(float)
    return bool(len(c) == length and np.isfinite(c).all() and (c > 0).all())


class SourceBoundaryBars:
    """Retain verified non-price bars; refuse cross-session price diagnostics."""
    CROSS_SESSION_PRICE = ('D06_priceVolumeDivergence','D07_volumePriceAlignment',
                          'E01_amihudIlliquidity60','E05_highLowSpreadProxy')

    def __init__(self, inner):
        self.inner = inner

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def crosses(self, date, length):
        days = self.inner.calendar[self.inner.calendar<=pd.Timestamp(date)][-length:]
        return bool(len(days) and any(days[0]<=pd.Timestamp(d)<=days[-1] for d in QUARANTINE))

    def basis_cause(self, date, window):
        original = self.inner.basis_cause(date, window)
        return original or ('UNCONFIRMED_CORPORATE_ACTION_IN_WINDOW' if self.crosses(date,window) else None)

    def features_at(self, date):
        values, reasons = self.inner.features_at(date)
        for feature in self.CROSS_SESSION_PRICE:
            if self.crosses(date,B.BARS_FEATURES[feature]):
                values.pop(feature,None)
                reasons[feature] = 'UNCONFIRMED_CORPORATE_ACTION_IN_WINDOW'
        return values, reasons


@contextmanager
def source_window_guards():
    """Reject an intermediate source gap in legacy endpoint-only readers.

    Restricted to the repaired security. The original numeric calculation,
    all other securities and the all-member industry rule are unchanged.
    """
    arrays, feature = IE.past_arrays, VQ.feature_at

    def guarded_arrays(prices, ticker, days, pos, window):
        c = arrays(prices, ticker, days, pos, window)
        if ticker == TICKER and c is not None and (not np.isfinite(c).all() or (c <= 0).any()):
            return None
        return c

    def guarded_feature(ticker, date, records, market, frame, benchmark):
        out = feature(ticker, date, records, market, frame, benchmark)
        if ticker != TICKER or frame is None:
            return out
        days = AI.RC.sessions('2013-01-01', date, 'KR')
        if not window_valid(frame, days, len(days)-1, 127):
            out['relative126'] = None
        if not window_valid(frame, days, len(days)-22, 232):
            out['momentum121'] = None
        out.update(VQ.core_observability(pd.DataFrame([out])).iloc[0].to_dict())
        out['missingFeatures'] = [n for n in VQ.RAW_FEATURES if out[n] is None]
        return out

    with patch.object(IE, 'past_arrays', guarded_arrays), patch.object(VQ, 'feature_at', guarded_feature):
        yield


@contextmanager
def corrected_loader(root, *, capture=None):
    q = read_correction(root)
    verify_raw_quotes(root, q)
    parent = V2.read_correction(root)
    original = AI.load_inputs
    repair_sha = contract.file_hash(Path(root) / CORRECTION)

    def selected(commit, work, repo):
        inputs = original(commit, work, repo)
        legacy = inputs.prices[TICKER].copy()
        inputs = V2.overlay(inputs, parent, contract.file_hash(Path(root) / V2.CORRECTION))
        inputs.prices[TICKER] = reconstruct(q)
        inputs.bars[TICKER] = SourceBoundaryBars(inputs.bars[TICKER])
        inputs.identity = repaired_identity(inputs.identity, repair_sha)
        if capture is not None:
            capture.update(inputs=inputs, legacyMirae=legacy)
        return inputs

    with patch.object(AI, 'load_inputs', selected), source_window_guards():
        yield


def expected_effective(root, meta):
    parent = V2.load(root)
    out = deepcopy(parent)
    out['version'] = 3
    out['registrationAmendmentId'] = 'kr-alpha-atlas-phase-c-v3-006800-source-segments'
    out['phaseBIdentity']['inputs'] = repaired_identity(parent['phaseBIdentity']['inputs'], contract.file_hash(Path(root)/CORRECTION))
    out['phaseBIdentity']['matrixDigest'] = meta['correctedMatrixDigest']
    out['lifecycle']['authorizationPath'] = AUTHORIZATION
    out['sourceLimitations'][-1] = (
        'STOCK SOURCE AUDIT: prior fixed sample and 235 final-session repairs remain preserved. '
        '006800.KS is reconstructed from exact original raw KRX OHLCV with registered partial cash once and '
        'the separately verified 2026 stock entitlement. The official 2018-01-23 unlisted preferred '
        'subscription-right boundary has no verified valuation: all crossing feature/holding windows '
        'remain invalid; independently normalized connected segments must never be bridged. '
        'No certification of complete stock distributions or signal-date reproduction of every legacy action.'
    )
    out['inputIntegrityAmendment'] = {
        **parent['inputIntegrityAmendment'],
        'parentV2FileSha256': PARENT_SHA,
        'sourceSegmentRepairFileSha256': contract.file_hash(Path(root)/CORRECTION),
        'stockRule': {'ticker': TICKER, 'policy': 'VERIFIED_RAW_SOURCE_SEGMENTS_WITH_UNVALUED_RIGHTS_BOUNDARY',
                      'quarantinedSessions': list(QUARANTINE)},
        'validity': out['sourceLimitations'][-1] + ' Identical source/outcome validity for every model and portfolio; no zero payoff, last-price exit or survivor renormalization.',
    }
    out['dependencyHashes'] = {**parent['dependencyHashes'], **meta['additionalDependencyHashes']}
    return out


def load(root=contract.ROOT):
    root = Path(root)
    if contract.file_hash(root/V2.AMENDMENT) != PARENT_SHA:
        raise ValueError('PUBLISHED_V2_NOT_PRESERVED')
    if contract.file_hash(root/ADDENDUM) != (root/SIDECAR).read_text().strip():
        raise ValueError('SOURCE_REPAIR_ADDENDUM_CHANGED')
    meta = json.loads((root/ADDENDUM).read_text())
    if (meta['parentV2FileSha256'] != PARENT_SHA or meta['sameStudyId'] != contract.STUDY or
            meta['originalV1FileSha256'] != V2.ORIGINAL_SHA or
            meta['globalOneShotLock'] != V2.GLOBAL_LOCK or meta['formalExecutionAuthorized'] or
            meta['sameResultPath'] != contract.load(root)['lifecycle']['resultPath'] or
            meta['sameArtifactPrefix'] != contract.load(root)['lifecycle']['artifactPrefix'] or
            not meta['freshExactHashOwnerApprovalRequired']):
        raise ValueError('ONE_ORIGINAL_STUDY_AND_OWNER_APPROVAL_REQUIRED')
    sources = json.loads((root/BASE/'sources.json').read_text())
    expected_paths = set(ADDITIONAL_FILES) | {BASE+'/'+r['path'] for r in sources if 'path' in r}
    if set(meta['additionalDependencyHashes']) != expected_paths:
        raise ValueError('COMPLETE_SOURCE_REPAIR_DEPENDENCY_CLOSURE_REQUIRED')
    for path, sha in meta['additionalDependencyHashes'].items():
        p = (root/path).resolve()
        if not p.is_relative_to(root.resolve()) or contract.file_hash(p) != sha:
            raise ValueError('SOURCE_REPAIR_DEPENDENCY_CHANGED')
    read_correction(root)
    out = expected_effective(root, meta)
    if (contract.digest(out) != meta['effectiveContractSha256'] or
            contract.digest(out['dependencyHashes']) != meta['dependencyManifestSha256'] or
            len(meta['correctedMatrixDigest']) != 64):
        raise ValueError('EXACT_EFFECTIVE_SOURCE_REPAIR_CONTRACT_REQUIRED')
    return out


def prepare(root, spec, work, *, capture=None):
    with corrected_loader(root, capture=capture):
        data, identity = preflight.prepare(root, spec, None, work)
    identity.update(formalInputBasis='PHASE_C_V3_EXPLICIT_CONNECTED_SOURCE_SEGMENTS',
                    repairAddendumFileSha256=contract.file_hash(Path(root)/ADDENDUM),
                    parentV2FileSha256=PARENT_SHA,
                    stockSourceIntegrityPolicy=spec['inputIntegrityAmendment']['validity'])
    return data, identity


def audit(root, work, expected_main):
    root, work = Path(root), Path(work)
    work.mkdir(parents=True, exist_ok=False)
    github = lifecycle.GitHub()
    if github.main() != expected_main:
        raise ValueError('LATEST_MAIN_CHANGED')
    subprocess.run(['git','merge-base','--is-ancestor',expected_main,'HEAD'],cwd=root,check=True)
    spec = load(root)
    if (any((root/p).exists() for p in [AUTHORIZATION, contract.load(root)['lifecycle']['authorizationPath'], V2.load(root)['lifecycle']['authorizationPath']]) or
            (root/spec['lifecycle']['resultPath']).exists() or github.locks(V2.GLOBAL_LOCK) or github.previous_results(spec['lifecycle']['artifactPrefix'])):
        raise ValueError('AUDIT_REQUIRES_UNAUTHORIZED_UNCONSUMED_STUDY')
    runtime = preflight.verify_runtime(spec)
    before = resource_facts(work)
    if before['memoryCapacityBytes'] < spec['compute']['memoryBytes'] or before['diskFreeBytes'] < 1024**3:
        raise ValueError('PRE_OUTCOME_RESOURCE_CAPACITY_BLOCKER')
    start, capture = time.monotonic(), {}
    with outcome_free_firewall() as attempts:
        data, identity = prepare(root, spec, work/'inputs', capture=capture)
        readiness = V2.source_readiness(data, spec, require_ready=False)
        from pipeline.kr_alpha_atlas_mirae_source_audit import coverage_propagation
        propagation = coverage_propagation(data, capture)
        probe = persistence_probe(work)
    elapsed = time.monotonic()-start
    if elapsed > spec['compute']['wallSeconds']:
        raise ValueError('PRE_OUTCOME_PREPARATION_TIME_BUDGET_EXCEEDED')
    if github.main() != expected_main or github.locks(V2.GLOBAL_LOCK):
        raise ValueError('MAIN_OR_LOCK_CHANGED_DURING_SAFE_PREFLIGHT')
    load(root)
    common = data.rows.date.between('2016-04-01', spec['developmentCutoff'])
    report = {
        'status': 'PASS_OUTCOME_FREE_CORRECTED_PREPARATION' if readiness['status']=='READY' else 'BLOCKED_PRE_OUTCOME_SOURCE_COVERAGE',
        'expectedMain':expected_main,'repairAddendumFileSha256':contract.file_hash(root/ADDENDUM),
        'effectiveContractSha256':contract.digest(spec),'identity':identity,
        'actualMatrixDigest':identity['matrixDigest'],'expectedMatrixDigest':spec['phaseBIdentity']['matrixDigest'],
        'correctedSourceReadiness':readiness,'readiness':data.validate_features(spec),
        'coveragePropagation':propagation,'securities':int(data.rows.ticker.nunique()),
        'b4CommonRows':int(common.sum()),
        'b4CommonCompleteCasePct':float(data.values.loc[common,spec['baselines']['B4_COMBINED_SIMPLE']].notna().all(axis=1).mean()*100),
        'elapsedSeconds':round(elapsed,3),'maxRssBytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
        'runtime':runtime,'resourcesBefore':before,'resourcesAfter':resource_facts(work),
        'sourceSchemas':preflight.verify_source_schema_samples(root,spec),
        'persistenceProbe':probe,'firewallBlockedCalls':attempts,'counters':asdict(AuditCounters()),
        'benchmarkIntegrity':spec['benchmarkIntegrity'],
        'excludedLayers':['authorization','permanent lock','targets','fits','IC/spreads','portfolios','formal results'],
    }
    RAW.immutable_bytes(work/'source-repair-preflight.json',contract.canonical(report)+b'\n')
    return report


def formal(root=contract.ROOT, *, work, github=None):
    """Same frozen executor and atomic lifecycle, fresh exact-hash owner approval."""
    root, work = Path(root), Path(work)
    github = github or lifecycle.GitHub()
    meta = json.loads((root/ADDENDUM).read_text())  # Parse only before main/approval.
    spec = json.loads((root/contract.SPEC).read_text())
    counters, budget, audit_doc = labels.Counters(), executor.Budget(spec), {}
    output, head = work/'results', None

    def checks():
        nonlocal head, spec
        head = subprocess.check_output(['git','rev-parse','HEAD'],cwd=root).decode().strip()
        if github.main()!=head or subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=root).strip():
            raise ValueError('ACTUAL_CLEAN_MERGED_MAIN_REQUIRED')
        path = root/AUTHORIZATION
        if not path.exists():
            raise ValueError('EXPLICIT_HUMAN_SOURCE_REPAIR_AUTHORIZATION_ABSENT')
        wanted = {'studyId':contract.STUDY,'action':'ONE_FORMAL_EXECUTION','authorizedBy':lifecycle.HUMAN,
                  'originalSpecFileSha256':V2.ORIGINAL_SHA,'parentV2FileSha256':PARENT_SHA,
                  'repairAddendumFileSha256':contract.file_hash(root/ADDENDUM),
                  'effectiveContractSha256':meta['effectiveContractSha256'],
                  'dependencyManifestSha256':meta['dependencyManifestSha256']}
        if json.loads(path.read_text())!=wanted:
            raise ValueError('AUTHORIZATION_NOT_EXACT_SOURCE_REPAIR_CONTRACT')
        committed = subprocess.check_output(['git','log','-1','--format=%H','--',AUTHORIZATION],cwd=root).decode().strip()
        if (not committed or github.human_author(committed)!=lifecycle.HUMAN or
                os.environ.get('GITHUB_EVENT_NAME')!='workflow_dispatch' or
                os.environ.get('GITHUB_ACTOR')!=lifecycle.HUMAN or os.environ.get('GITHUB_REF')!='refs/heads/main'):
            raise ValueError('OWNER_COMMITTED_APPROVAL_AND_MAIN_MANUAL_DISPATCH_REQUIRED')
        audit_doc['authorization']={**wanted,'authorizationCommit':committed}
        spec = load(root)
        if (root/spec['lifecycle']['resultPath']).exists() or github.previous_results(spec['lifecycle']['artifactPrefix']) or github.locks(V2.GLOBAL_LOCK):
            raise ValueError('ORIGINAL_STUDY_ALREADY_CONSUMED')

    def pre():
        preflight.verify_runtime(spec)
        resources = resource_facts(work.parent)
        if resources['memoryCapacityBytes']<spec['compute']['memoryBytes'] or resources['diskFreeBytes']<1024**3:
            raise ValueError('PRE_OUTCOME_RESOURCE_CAPACITY_BLOCKER')
        data, identity = prepare(root,spec,work/'inputs')
        audit_doc['inputs'] = identity
        synthetic.smoke(spec)
        data.validate_features(spec)
        V2.source_readiness(data,spec)  # Original 60%/30 names/52 dates, strict.
        budget.check()
        output.mkdir(parents=True,exist_ok=True)
        persistence_probe(work)
        RAW.immutable_bytes(work/'preflight.json',contract.canonical(audit_doc)+b'\n')
        if github.main()!=head or github.locks(V2.GLOBAL_LOCK):
            raise ValueError('MAIN_OR_LOCK_CHANGED_DURING_PREFLIGHT')
        load(root)
        return data

    def run(data, receipt):
        RAW.immutable_bytes(output/'lock-receipt.json',contract.canonical(receipt.document)+b'\n')
        permit = labels.formal_permit(data.source_identity,receipt)
        result = executor.execute(data,spec,permit,counters=counters,budget=budget)
        load(root)
        audit_doc.update(head=head,repairAddendumFileSha256=contract.file_hash(root/ADDENDUM),
                         lock=receipt.document,counters=asdict(counters),runtime=preflight.verify_runtime(spec))
        return executor.persist(result,output,audit_doc)

    def failed(error, receipt):
        try:
            consumed = receipt is not None or bool(github.locks(V2.GLOBAL_LOCK))
        except RuntimeError:
            RAW.immutable_bytes(work/'lock-status-unknown.json',contract.canonical({'status':'VERIFY_LOCK_BEFORE_ANY_RECOVERY','errorClass':type(error).__name__})+b'\n')
            return
        where = output/'consumed-failure.json' if consumed else work/'pre-outcome-failure.json'
        RAW.immutable_bytes(where,contract.canonical({'status':'CONSUMED_NO_RETRY' if consumed else 'NOT_CONSUMED',
            'errorClass':type(error).__name__,'counters':asdict(counters),'exactByteRecoveryOnly':consumed})+b'\n')

    return lifecycle.ordered_once(checks=checks,prepare=pre,
        claim=lambda:github.claim(V2.GLOBAL_LOCK,head,contract.file_hash(root/ADDENDUM)),run=run,on_failure=failed)
