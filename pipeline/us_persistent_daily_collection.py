"""Owner-gated manual persistent staging; never production or scheduled activation."""
from dataclasses import asdict, dataclass
from datetime import date, timedelta
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import time

from . import collector_outcomes as CO
from . import us_daily_market_data as D
from . import us_daily_market_sources as S
from . import us_full_universe_dry_run as F
from . import us_real_source_preflight as P

VERSION = 'us-persistent-daily-collection-v1'
ROOT = Path(__file__).resolve().parents[1]
SCOPE = 'MANUAL_PROSPECTIVE_STAGING_ONLY'


@dataclass(frozen=True)
class Budget:
    max_calls: int = 600
    max_seconds: float = 1200
    pace_seconds: float = 1
    retries_per_symbol: int = 1
    retry_backoff_seconds: float = 5

    def validate(self):
        if (type(self.max_calls) is not int or not 2 <= self.max_calls <= 600 or
                not math.isfinite(self.max_seconds) or not 0 < self.max_seconds <= 1200 or
                not math.isfinite(self.pace_seconds) or not 1 <= self.pace_seconds <= 5 or
                type(self.retries_per_symbol) is not int or not 0 <= self.retries_per_symbol <= 1 or
                not math.isfinite(self.retry_backoff_seconds) or not 5 <= self.retry_backoff_seconds <= 30):
            raise D.Refused('INVALID_PERSISTENT_BUDGET', 'Conservative bounded request/retry budgets required')


def code_digest():
    paths = ['pipeline/us_persistent_daily_collection.py', 'scripts/collect_us_daily_persistent.py',
             'pipeline/us_daily_market_data.py', 'pipeline/us_daily_market_sources.py',
             'pipeline/us_full_universe_dry_run.py', 'pipeline/us_real_source_preflight.py',
             'pipeline/collector_outcomes.py', 'requirements.txt']
    return D.digest({p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths})


def plan(root, *, now, session=None, recheck=False, budget=Budget()):
    budget.validate()
    store = D.ObservationStore(root)
    recent = D.completed_sessions(now)
    session = session or recent[-1]
    if session not in recent:
        raise D.Refused('SESSION_OUTSIDE_PROSPECTIVE_WINDOW', 'Only one of the last seven completed sessions is allowed')
    return {'foundationVersion': VERSION, 'collectorVersion': D.VERSION, 'sourceKind': D.LIVE,
            'storageRoot': str(store.root), 'session': session, 'recheck': recheck,
            'budgets': asdict(budget), 'codeDigest': code_digest(), 'scope': SCOPE,
            'networkRequested': False, 'productionWrites': False, 'scheduleEnabled': False}


def authorize(approval, expected_sha256, request, *, now):
    """Exact owner-reviewed bytes, local ACL trust; not proof of a human signature."""
    raw = Path(approval).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise D.Refused('APPROVAL_HASH_MISMATCH', 'Approval must match the separately owner-reviewed exact hash')
    try:
        value = json.loads(raw)
        valid = (value['schema'] == 'US_DAILY_MANUAL_APPROVAL_V1' and value['approved'] is True and
                 bool(value['approvedBy'].strip()) and value['scope'] == SCOPE and
                 value['storageRoot'] == request['storageRoot'] and value['codeDigest'] == request['codeDigest'] and
                 value['budgets'] == request['budgets'] and value['sourceKind'] == D.LIVE and
                 value['allowRedistribution'] is False and value['allowSchedule'] is False and
                 (not request['recheck'] or value['allowRecheck'] is True) and
                 value['usageReview']['recurringAcquisitionPermitted'] is True and
                 value['usageReview']['persistentStoragePermitted'] is True and
                 bool(value['usageReview']['evidenceReferences']) and bool(value['usageReview']['reviewedBy'].strip()))
        granted, expires = D.utc(value['grantedAt']), D.utc(value['expiresAt'])
        at = D.utc(now)
        valid &= granted <= at < expires and 0 < (expires-granted).total_seconds() <= 30*86400
        # Date scope is explicit; approval cannot backfill pre-approval sessions.
        first, last = date.fromisoformat(value['firstSession']), date.fromisoformat(value['lastSession'])
        valid &= first <= date.fromisoformat(request['session']) <= last
        valid &= date.fromisoformat(D.completed_sessions(granted)[0]) <= first <= last <= expires.date()
        valid &= (expires-at).total_seconds() >= request['budgets']['max_seconds']+120
    except (KeyError, TypeError, ValueError, AttributeError):
        valid = False
    if not valid:
        raise D.Refused('OWNER_APPROVAL_OR_USAGE_REVIEW_MISSING', 'Unexpired exact-scope owner approval and source-use review required')
    return expected_sha256


class Control:
    """Immutable content-addressed receipts alongside the existing price store."""
    def __init__(self, store):
        self.store = store
        self.path = store.root/'collection-control'/(VERSION+('-fixtures' if store.source_kind == D.SYNTHETIC else ''))
        self.safe(self.path)

    def safe(self, path):
        if not path.resolve().is_relative_to(self.path):
            raise D.Refused('UNSAFE_CONTROL_PATH', 'Control namespace symlink escape refused')
        return path

    def publish(self, family, record):
        record = D.sealed(record)
        payload = D.canonical(record)
        path = self.safe(self.path/family/(hashlib.sha256(payload).hexdigest()+'.json'))
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.read_bytes() != payload:
                raise D.Refused('CONTROL_BYTES_CONFLICT', 'Immutable receipt bytes differ')
            return record
        handle, temporary = tempfile.mkstemp(prefix='.pending-', dir=path.parent)
        try:
            with os.fdopen(handle, 'wb') as out:
                out.write(payload)
                out.flush()
                os.fsync(out.fileno())
            os.link(temporary, path)
            directory = os.open(path.parent, os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return record

    def verify(self):
        result = []
        for path in sorted(self.path.glob('*/*.json')):
            raw = self.safe(path).read_bytes()
            value = {}
            try:
                value = json.loads(raw)
                valid = (path.stem == hashlib.sha256(raw).hexdigest() and value['foundationVersion'] == VERSION and
                         value['sourceKind'] == self.store.source_kind and
                         value['digest'] == D.digest({k:v for k,v in value.items() if k != 'digest'}))
            except (ValueError, KeyError, TypeError):
                valid = False
            valid = valid and isinstance(value, dict) and value.get('schema') in {'US_DAILY_STAGING_ATTEMPT_V1','US_DAILY_STAGING_RECEIPT_V1','US_DAILY_STAGING_COMPLETION_V1','US_DAILY_MEMBERSHIP_FAILURE_V1','US_DAILY_PROVIDER_TRANSPORT_V1'}
            if not valid:
                raise D.Refused('CONTROL_INTEGRITY_FAILURE', 'Receipt hash, namespace or version mismatch')
            result.append(value)
        manifests = {r['digest']:r for r in self.store.manifests()}
        controls = {r['digest']:r for r in result}
        for row in result:
            if row['schema'] not in ('US_DAILY_STAGING_RECEIPT_V1','US_DAILY_STAGING_COMPLETION_V1'):
                continue
            try:
                if row.get('manifestDigest') not in manifests:
                    raise D.Refused('CONTROL_MANIFEST_REFERENCE_MISSING', 'Receipt references a missing collection manifest')
                manifest = manifests[row['manifestDigest']]
                if row['session'] not in manifest['targetSessions']:
                    raise D.Refused('CONTROL_SCOPE_MISMATCH', 'Receipt session differs from manifest')
                if row['schema'] == 'US_DAILY_STAGING_RECEIPT_V1':
                    if row['status'] != manifest['status'] or row['collectionComplete'] != manifest['collectionComplete']:
                        raise D.Refused('CONTROL_SCOPE_MISMATCH', 'Receipt status differs from manifest')
                    if any(d not in controls for d in row['attemptDigests']):
                        raise D.Refused('CONTROL_ATTEMPT_REFERENCE_MISSING', 'Committed attempt receipt is missing')
                    attempts = [controls[d] for d in row['attemptDigests']]
                    if (row['actualAdapterAttempts'] != len(attempts) or
                            any(a['schema'] != 'US_DAILY_STAGING_ATTEMPT_V1' or a['session'] != row['session'] for a in attempts)):
                        raise D.Refused('CONTROL_SCOPE_MISMATCH', 'Attempt scope or counts do not match receipt')
                else:
                    linked = controls.get(row['receiptDigest'], {})
                    if (not manifest['collectionComplete'] or row['universeSnapshotDigest'] != manifest['universeSnapshotDigest'] or
                            linked.get('schema') != 'US_DAILY_STAGING_RECEIPT_V1' or linked.get('manifestDigest') != row['manifestDigest'] or
                            linked.get('collectionComplete') is not True):
                        raise D.Refused('CONTROL_COMPLETION_REFERENCE_INVALID', 'Completion does not verify its receipt and complete manifest')
            except D.Refused:
                raise
            except (KeyError, TypeError, ValueError) as exc:
                raise D.Refused('CONTROL_CONTRACT_MISMATCH', 'Control record fields cannot be verified') from exc
        return result


def run(root, membership, fetch, *, now, session=None, recheck=False, budget=Budget(),
        approval_digest=None, approval=None, monotonic=time.monotonic, sleep=time.sleep):
    """Injected synthetic path; live requests must carry prior CLI authorization."""
    budget.validate()
    if membership.source_kind == D.LIVE:
        if not approval_digest or not approval:
            raise D.Refused('LIVE_APPROVAL_REQUIRED', 'Use the owner-gated manual entry point')
        authorize(approval, approval_digest, plan(root,now=now,session=session,recheck=recheck,budget=budget),now=now)
    store = D.ObservationStore(root, membership.source_kind)
    session = session or D.completed_sessions(now)[-1]
    if session not in D.completed_sessions(now):
        raise D.Refused('SESSION_OUTSIDE_PROSPECTIVE_WINDOW', 'Prospective window exceeded')
    control = Control(store)
    started = monotonic()
    attempts, last_start, stop = [], None, None
    manifest = None

    def paced(ticker, start, through):
        nonlocal last_start, stop
        for retry in range(budget.retries_per_symbol+1):
            if last_start is not None:
                sleep(max(0., budget.pace_seconds-(monotonic()-last_start)))
            if len(attempts) >= budget.max_calls or monotonic()-started >= budget.max_seconds:
                stop = 'CALL_BUDGET' if len(attempts) >= budget.max_calls else 'TIME_BUDGET'
                raise F.ControlledStop()
            last_start = monotonic()
            event = {'schema': 'US_DAILY_STAGING_ATTEMPT_V1', 'foundationVersion': VERSION,
                     'sourceKind': store.source_kind, 'ticker': ticker, 'session': session,
                     'startedAt': S.now_utc(), 'retryIndex': retry, 'status': 'INTERRUPTED'}
            attempts.append(event)
            try:
                reply = fetch(ticker, start, through)
                event.update(status='ACQUIRED_NOT_YET_VALIDATED', observedAt=D.stamp(reply.observed_at))
                return reply
            except F.TransportStop as exc:
                stop = exc.reason
                event.update(status=exc.reason, sourceMessage=exc.message)
                raise
            except D.Refused as exc:
                category = P.classify(exc)
                event.update(status=category, sourceCode=exc.code, sourceMessage=str(exc))
                if category in ('PROVIDER_RATE_LIMIT','PROVIDER_AUTHORIZATION','PROXY_CONNECT_403','PROVIDER_OR_GATEWAY_FORBIDDEN_UNRESOLVED'):
                    stop = category
                    raise F.ControlledStop() from exc
                transient = exc.outcome == CO.NETWORK_ERROR or 'timeout' in str(exc).lower() or 'timed out' in str(exc).lower()
                if not transient or retry == budget.retries_per_symbol:
                    raise
                sleep(budget.retry_backoff_seconds)
            finally:
                event['elapsedSeconds'] = round(monotonic()-last_start, 6)
                committed = control.publish('attempts', event)
                event['committedDigest'] = committed['digest']

    with store.locked():
        prior_controls = control.verify()
        check_cooldown(prior_controls, now)
        store.snapshots()
        store.observations([session])
        before_manifests = {r['digest'] for r in store.manifests()}
        try:
            # The existing engine under ONE store lock covers collection, validation
            # and completion publication; calling collect() here would double-lock.
            manifest = D._collect_locked(store, membership, paced, now=now, target_dates=[session],
                         max_calls=budget.max_calls, max_seconds=budget.max_seconds, batch_size=1, recheck=recheck)
        except F.ControlledStop:
            new = [r for r in store.manifests() if r['digest'] not in before_manifests]
            manifest = new[-1] if len(new) == 1 else None
        finally:
            manifests = store.manifests()
            if manifest is None:
                new = [r for r in manifests if r['digest'] not in before_manifests]
                manifest = new[-1] if len(new) == 1 else None
            if manifest is not None:
                sealed_manifest = D.sealed({k:v for k,v in manifest.items() if k != 'digest'})
                if sealed_manifest['digest'] not in {r['digest'] for r in manifests}:
                    raise D.Refused('MANIFEST_NOT_COMMITTED', 'No verified committed manifest')
                rows = store.observations([session])
                receipt = {'schema': 'US_DAILY_STAGING_RECEIPT_V1', 'foundationVersion': VERSION,
                           'sourceKind': store.source_kind, 'manifestDigest': sealed_manifest['digest'],
                           'session': session, 'sourceObservationAt': manifest['sourceObservationAt'],
                           'status': manifest['status'], 'collectionComplete': manifest['collectionComplete'],
                           'actualAdapterAttempts': len(attempts), 'retryAttempts': sum(a['retryIndex']>0 for a in attempts),
                           'stopReason': stop or manifest['stopReason'], 'verifiedRecordCount': len(rows),
                           'attemptDigests': [a['committedDigest'] for a in attempts],
                           'approvalDigest': approval_digest, 'codeDigest': code_digest(), 'budgets': asdict(budget),
                           'elapsedSeconds': round(monotonic()-started, 6),
                           'cooldownUntil': D.stamp(D.utc(now)+timedelta(seconds=monotonic()-started+900)) if stop == 'PROVIDER_RATE_LIMIT' else None,
                           'stagingOnly': True,
                           'historicalPitMembershipVerified': False, 'permanentSecurityIdentityVerified': False,
                           'productionWrites': False, 'scheduleEnabled': False}
                receipt = control.publish('receipts', receipt)
                if manifest['collectionComplete'] and not any(r.get('schema') == 'US_DAILY_STAGING_COMPLETION_V1' and r.get('manifestDigest') == sealed_manifest['digest'] for r in control.verify()):
                    control.publish('completions', {'schema':'US_DAILY_STAGING_COMPLETION_V1',
                        'foundationVersion':VERSION,'sourceKind':store.source_kind,'session':session,
                        'manifestDigest':sealed_manifest['digest'], 'receiptDigest':receipt['digest'], 'universeSnapshotDigest':manifest['universeSnapshotDigest'],
                        'historicalCompletionOnly':True, 'productionPublication':False})
    return receipt if manifest is not None else {'status':'INTERRUPTED_NO_MANIFEST','collectionComplete':False,'stopReason':stop}


def check_cooldown(controls, now):
    if any(r.get('cooldownUntil') and D.utc(now) < D.utc(r['cooldownUntil']) for r in controls):
        raise D.Refused('PERSISTENT_PROVIDER_COOLDOWN', 'Prior rate limit blocks collection for at least 15 minutes; no automatic retry')


def record_source_failure(root, exc, request, approval_digest, *, now, source_kind=D.LIVE):
    store = D.ObservationStore(root, source_kind)
    with store.locked():
        control = Control(store)
        control.verify()
        failure = P.failure(None, 'MEMBERSHIP', exc)
        return control.publish('source-failures', {'schema':'US_DAILY_MEMBERSHIP_FAILURE_V1',
            'foundationVersion':VERSION,'sourceKind':source_kind,'recordedAt':D.stamp(now),
            'approvalDigest':approval_digest,'requestDigest':D.digest(request), 'failure':failure,
            'cooldownUntil':D.stamp(D.utc(now)+timedelta(seconds=900)) if failure['failureClass']=='PROVIDER_RATE_LIMIT' else None,
            'collectionComplete':False,'expectedRecordCount':None,'priceAdapterAttempts':0})


def record_transport(root, events, request, approval_digest, *, source_kind=D.LIVE):
    store = D.ObservationStore(root, source_kind)
    with store.locked():
        control = Control(store)
        control.verify()
        return control.publish('transport', {'schema':'US_DAILY_PROVIDER_TRANSPORT_V1',
            'foundationVersion':VERSION,'sourceKind':source_kind,'approvalDigest':approval_digest,
            'requestDigest':D.digest(request),'providerHttpCalls':len(events),'events':events})


def inspect(root, *, now=None, source_kind=D.LIVE):
    store = D.ObservationStore(root, source_kind)
    with store.locked():
        controls = Control(store).verify()
        if now is not None:
            check_cooldown(controls, now)
        snapshots = store.snapshots()
        manifests = store.manifests()
        store.observations()
        return {'foundationVersion':VERSION,'verifiedReceipts':len(controls),'observedSnapshots':len(snapshots),
                'verifiedManifests':len(manifests),'stagingOnly':True,'scheduleEnabled':False,
                'warning':'Completion markers are historical evidence, not a current-ready view; use latest manifest and revision quarantine'}
