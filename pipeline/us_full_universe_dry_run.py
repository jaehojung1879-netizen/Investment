"""One-session, full observed universe source diagnostic; no production activation."""
from collections import Counter
from contextlib import contextmanager
from datetime import timedelta
import json
import os
from pathlib import Path
import time

from . import us_daily_market_data as D
from . import us_daily_market_sources as S
from . import us_real_source_preflight as P

VERSION = 'us-full-universe-real-dry-run-v1'
MAX_CALLS = 552  # Existing live membership guard: <=550 securities plus two ETFs.
MAX_SECONDS = 1200
PACE_SECONDS = 1.0


class ControlledStop(BaseException):
    """Collector's finally block commits progress before this controlled stop."""


def run(root, membership, fetch, *, now, monotonic=time.monotonic, sleep=time.sleep,
        pace=PACE_SECONDS, max_seconds=MAX_SECONDS, max_calls=MAX_CALLS, runtime=None):
    if pace < PACE_SECONDS or not 0 < max_seconds <= MAX_SECONDS or not 2 <= max_calls <= MAX_CALLS:
        raise ValueError('Refuse unpaced or expanded diagnostic budgets')
    store = D.ObservationStore(root, membership.source_kind)
    store.root.mkdir(parents=True, exist_ok=True)
    if list(store.root.iterdir()):
        raise D.Refused('STAGE_NOT_EMPTY', 'A fresh isolated stage is required')
    snapshot = D.membership_snapshot(membership, now)
    session = D.completed_sessions(now)[-1]
    started = monotonic()
    calls, failures = [], []
    stop_reason = None
    last_start = None

    def paced(ticker, start, through):
        nonlocal last_start, stop_reason
        if last_start is not None:
            sleep(max(0., pace - (monotonic() - last_start)))
        if monotonic() - started >= max_seconds or len(calls) >= max_calls:
            stop_reason = 'TIME_BUDGET' if monotonic() - started >= max_seconds else 'CALL_BUDGET'
            raise ControlledStop()
        last_start = monotonic()
        event = {'ticker': ticker, 'startedAt': S.now_utc(), 'start': start, 'through': through}
        calls.append(event)
        reply = None
        try:
            reply = fetch(ticker, start, through)
            member = next(m for m in D.target_members(snapshot, None)[0] if m['ticker'] == ticker)
            # Validate here to retain exact original refusal and frame context.
            D.price_records(reply, member, snapshot, [session], now)
            event['status'] = 'VALID'
            event['observedAt'] = D.stamp(reply.observed_at)
            return reply
        except D.Refused as exc:
            record = P.failure(ticker, 'PRICE', exc, reply)
            failures.append(record)
            event['status'] = record['failureClass']
            if record['failureClass'] == 'PROVIDER_RATE_LIMIT':
                stop_reason = 'PROVIDER_RATE_LIMIT'
                raise ControlledStop() from exc
            raise
        finally:
            event['elapsedSeconds'] = round(monotonic() - last_start, 3)
            # Persist each attempt before a following request, not just at completion.
            (store.root / 'attempts.json').write_text(json.dumps(calls, sort_keys=True, indent=2)+'\n')

    try:
        manifest = D.collect(store.root, membership, paced, now=now, target_dates=[session],
                             max_calls=max_calls, max_seconds=max_seconds, batch_size=1)
    except ControlledStop:
        manifest = store.manifests()[-1]
    rows = list(store.observations([session]).values())
    before = P.files(store.root)
    repeat = store.append_prices(rows)
    unchanged = before == P.files(store.root)
    first = min((D.utc(r['availableFrom']) for r in rows), default=None)
    integrity = {'appendOnlyBytesUnchanged': unchanged, 'repeatCount': repeat['repeated'],
                 'sameAcquisitionRepeatProviderCalls': 0,
                 'sourceReferencesVerified': len(rows),
                 'noPricesBeforeFirstAcquisition': first is None or not store.prices_at(first-timedelta(microseconds=1))}
    as_traded = []
    for row in rows:
        raw = next(p for p in row['sourcePanel'] if p['date'] == session)
        factor = row['splitFactorStrictlyAfterSession']
        as_traded.append(all(row['core'][k] == raw[k]*factor for k in ('Open', 'High', 'Low', 'Close')) and
                         row['core']['Volume'] == raw['Volume']/factor and
                         row['core']['cashDividendAsTraded'] == raw['Dividends']*factor)
    integrity['asTradedBasisVerified'] = all(as_traded)
    valid = {r['core']['ticker'] for r in rows}
    benchmark = {t: 'VALID' if t in valid else 'MISSING_OR_INVALID' for t in ('SPY', 'QQQ')}
    complete = manifest['collectionComplete'] and len(rows) == len(snapshot['members'])+2
    sound = unchanged and repeat['repeated'] == len(rows) and all(as_traded) and integrity['noPricesBeforeFirstAcquisition']
    result = {'schema': 'US_FULL_UNIVERSE_DRY_RUN_V1', 'version': VERSION,
              'sourceKind': membership.source_kind, 'runtime': runtime or {},
              'verdict': 'PASS' if complete and sound else 'PARTIAL' if rows else 'BLOCKED',
              'session': session, 'plannedAt': D.stamp(now), 'membershipSource': membership.source,
              'membershipSourceIdentity': membership.source_identity,
              'membershipObservedAt': snapshot['observedAt'], 'universeSnapshotDigest': snapshot['digest'],
              'sourceRawSha256': snapshot['sourceRawSha256'],
              'expectedConstituentSecurities': len(snapshot['members']), 'expectedSecuritiesIncludingBenchmarks': len(snapshot['members'])+2,
              'observedIssuerCikCount': len({m['issuerCik'] for m in snapshot['members']}),
              'collectedConstituents': len(valid-set(D.BENCHMARKS)), 'collectedSecurities': len(valid),
              'benchmarks': benchmark, 'completenessPercent': round(100*len(valid)/(len(snapshot['members'])+2), 6),
              'failureCountsByRootCause': dict(sorted(Counter(f['failureClass'] for f in failures).items())),
              'failures': failures, 'missing': manifest['missing'], 'stopReason': stop_reason or manifest['stopReason'],
              'actualProviderAdapterCalls': len(calls), 'membershipHttpCalls': 2,
              'underlyingYahooHttpCalls': None, 'underlyingYahooHttpCallsStatus': 'NOT_INSTRUMENTED_YFINANCE_INTERNAL_TRANSPORT',
              'elapsedSeconds': round(monotonic()-started, 3), 'maxProviderAdapterCalls': max_calls,
              'maxSeconds': max_seconds, 'minimumRequestStartIntervalSeconds': pace,
              'providerTimeoutSeconds': 20, 'diagnosticRetries': 0,
              'nonzeroDividendRecords': sum(r['core']['cashDividendAsTraded'] > 0 for r in rows),
              'nonidentitySplitRecords': sum(r['core']['splitRatio'] != 1 for r in rows),
              'actionColumnsVerifiedRecords': len(rows),
              'unresolvedActionIssues': [f for f in failures if f['failureClass'] == 'MISSING_CORPORATE_ACTIONS'],
              'corporateActionLimitation': 'Single session does not establish future revisions, special distributions, spinoffs or provider event completeness',
              'shareClassSymbols': [{'sourceSymbol': m['sourceSymbol'], 'ticker': m['ticker'], 'status': 'VALID' if m['ticker'] in valid else 'MISSING_OR_INVALID'}
                                    for m in snapshot['members'] if '.' in m['sourceSymbol'] or '-' in m['ticker']],
              'integrity': integrity, 'collectionManifest': manifest,
              'historicalPitMembershipVerified': False, 'permanentSecurityIdentityVerified': False,
              'sourceOfficialCompletenessVerified': False, 'qualityWarnings': snapshot['qualityWarnings'],
              'dailyOperationEnabled': False, 'productionWrites': False,
              'dailyOperationalFeasibility': 'ONE_SESSION_TECHNICALLY_FEASIBLE_NOT_RELIABILITY_PROVEN' if complete and sound else 'NOT_ESTABLISHED'}
    result = D.sealed(result)
    (store.root/'source-audit.json').write_text(json.dumps(result, sort_keys=True, indent=2)+'\n')
    (store.root/'evidence-hashes.json').write_text(json.dumps(P.files(store.root), sort_keys=True, indent=2)+'\n')
    return result



@contextmanager
def provider_http_evidence():
    """Count pinned provider transport calls; refuse 429 before internal retry.

    No URL, cookies, authorization or response body is recorded. Standard
    curl transport, proxy configuration and TLS verification remain unchanged.
    """
    from curl_cffi.requests import Session
    original = Session.request
    evidence = []
    def counted(session, method, url, *args, **kwargs):
        event = {'method': method, 'startedAt': S.now_utc(), 'statusCode': None}
        evidence.append(event)
        try:
            response = original(session, method, url, *args, **kwargs)
            event['statusCode'] = response.status_code
            if response.status_code == 429:
                raise D.Refused('YAHOO_PROVIDER_REFUSAL', 'HTTP 429: rate limit; diagnostic refused internal retry')
            return response
        except Exception as exc:
            event['exceptionType'] = type(exc).__name__
            raise
    Session.request = counted
    try:
        yield evidence
    finally:
        Session.request = original


def main(output):
    root = Path(output).resolve()
    # Refuse checkout or occupied staging before any network request.
    store = D.ObservationStore(root)
    store.root.mkdir(parents=True, exist_ok=True)
    if list(store.root.iterdir()):
        raise D.Refused('STAGE_NOT_EMPTY', 'Fresh isolated stage required')
    runtime = P.runtime_identity()
    try:
        membership = S.current_sp500()
        with provider_http_evidence() as http:
            result = run(root, membership, S.yahoo_daily, now=S.now_utc(), runtime=runtime)
        result.pop('digest')
        result['underlyingYahooHttpCalls'] = len(http)
        result['underlyingYahooHttpCallsStatus'] = 'OBSERVED_PINNED_CURL_SESSION_REQUESTS'
        result['providerHttpStatusCounts'] = dict(sorted(Counter(str(e['statusCode']) for e in http).items()))
        result = D.sealed(result)
        (root/'provider-http-attempts.json').write_text(json.dumps(http, sort_keys=True, indent=2)+'\n')
        (root/'source-audit.json').write_text(json.dumps(result, sort_keys=True, indent=2)+'\n')
        (root/'evidence-hashes.json').unlink()
        (root/'evidence-hashes.json').write_text(json.dumps(P.files(root), sort_keys=True, indent=2)+'\n')
    except D.Refused as exc:
        result = D.sealed({'schema': 'US_FULL_UNIVERSE_DRY_RUN_V1', 'version': VERSION, 'verdict': 'BLOCKED',
                          'sourceKind': D.LIVE, 'runtime': runtime, 'failure': P.failure(None, 'MEMBERSHIP_OR_STAGE', exc),
                          'expectedSecuritiesIncludingBenchmarks': None, 'collectedSecurities': 0,
                          'actualProviderAdapterCalls': 0, 'completenessPercent': None})
        (root/'source-audit.json').write_text(json.dumps(result, sort_keys=True, indent=2)+'\n')
        (root/'evidence-hashes.json').write_text(json.dumps(P.files(root), sort_keys=True, indent=2)+'\n')
    summary = f"{result['verdict']} expected={result['expectedSecuritiesIncludingBenchmarks']} collected={result['collectedSecurities']} pct={result['completenessPercent']} calls={result['actualProviderAdapterCalls']} sec={result.get('elapsedSeconds')}"
    detail = f"SPY={result.get('benchmarks',{}).get('SPY')} QQQ={result.get('benchmarks',{}).get('QQQ')} dividends={result.get('nonzeroDividendRecords')} splits={result.get('nonidentitySplitRecords')} failures={result.get('failureCountsByRootCause',result.get('failure',{}).get('failureClass'))}"
    # Compact full audit is also retained as a notice for standard GitHub API retrieval.
    compact = {k:v for k,v in result.items() if k not in ('collectionManifest','missing','runtime')}
    print('::notice title=US full-universe source audit::'+json.dumps(compact, sort_keys=True).replace('%','%25').replace('\n','%0A').replace('\r','%0D'))
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as out:
            out.write(f"summary={summary}\ndetail={detail}\nverdict={result['verdict']}\n")
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as out:
            out.write('```json\n'+json.dumps(compact, indent=2, sort_keys=True)+'\n```\n')
    print(summary)
    return 0
