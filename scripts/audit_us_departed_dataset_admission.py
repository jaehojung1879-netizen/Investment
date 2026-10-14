"""Read-only admission audit of explicitly supplied local recovery files.

Never fetches removed GitHub objects; only a fixed, already-present fundamentals
commit/path prefix may be read. Public output is aggregate metadata, no prices.
"""
from __future__ import annotations

import argparse
from bisect import bisect_left
from collections import Counter, defaultdict
import gzip
import json
from pathlib import Path
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import us_departed_dataset_admission as D  # noqa: E402
from pipeline import us_departed_price_recovery as R  # noqa: E402
from pipeline import replay_calendar as RC  # noqa: E402

APPROVED_SPEC_SHA256 = 'ebef3f0c359ea7f1791773e08b3a251ae183dd5941127513bc1dc3605fd3fa56'
FUNDAMENTALS_COMMIT = '704d7db6d5b00def771aba5d2665d0846d6bc776'
RECOVERY = 'docs/us-readiness/us-departed-public-price-recovery-v1.json'
STORE = 'candidate_data/us-departed-public-price-v1/manifest.json'
PROTOCOL = 'docs/us-readiness/us-multifactor-research-roadmap-v1.json'
IDENTITY = 'research_specs/alpha-opportunity-model-v3-us-identity-evidence.json.gz'
MEMBERSHIP = 'research_specs/alpha-opportunity-model-v1-us-membership.json.gz'
BASELINE = 'docs/results/alpha-opportunity-model-v3-survivorship-audit.json'
START, END = '2013-01-01', '2026-09-14'  # original audit denominator, not extended to today


def load_json(path):
    return json.loads(Path(path).read_bytes())


def verify_local_artifacts(directory, manifest):
    """Exact local-only bytes; DATA_UNAVAILABLE is distinct from checksum failure."""
    if directory is None:
        return None
    paths = {}
    for key in ('raw', 'panel'):
        item = manifest[key];name = item['externalFilename']
        if Path(name).name != name:
            raise ValueError('INVALID_EXTERNAL_FILENAME')
        path = Path(directory) / name
        if not path.is_file():
            return None
        data = path.read_bytes()
        if len(data) != item['bytes'] or D.digest(data) != item['sha256']:
            raise ValueError('LOCAL_ARTIFACT_CHECKSUM_MISMATCH')
        paths[key] = path
    expanded = gzip.decompress(paths['panel'].read_bytes())
    if D.digest(expanded) != manifest['panel']['decompressedSha256']:
        raise ValueError('LOCAL_PANEL_EXPANDED_CHECKSUM_MISMATCH')
    panel = json.loads(expanded)
    if len(panel['rows']) != manifest['panel']['perSourceObservations']:
        raise ValueError('LOCAL_PANEL_COUNT_MISMATCH')
    return paths, panel


def frozen_inputs(recovery):
    for path, expected_sha in recovery['inputSha256'].items():
        if D.digest((ROOT / path).read_bytes()) != expected_sha:
            raise ValueError('SEALED_INPUT_HASH_MISMATCH')
    if D.digest((ROOT / PROTOCOL).read_bytes()) != APPROVED_SPEC_SHA256:
        raise ValueError('APPROVED_ADMISSION_SPEC_HASH_MISMATCH')
    spec = load_json(ROOT / PROTOCOL)
    if spec['datasetAdmissionGate']['id'] != 'US_MF1_DATASET_ADMISSION_V1':
        raise ValueError('WRONG_ADMISSION_SPECIFICATION')
    member = json.loads(gzip.decompress((ROOT / MEMBERSHIP).read_bytes()))['snapshots']
    identity = json.loads(gzip.decompress((ROOT / IDENTITY).read_bytes()))
    baseline = load_json(ROOT / BASELINE)
    malformed = baseline['regions']['US']['identity']['malformed']
    fixes = {k: v['resolvedTo'] for k, v in malformed.items() if v['resolvedTo']}
    member = [{**s, 'members': sorted({fixes.get(t, t) for t in s['members']})} for s in member]
    return member, identity


def membership_grid(snapshots, calendar, tickers):
    dates = [s['date'] for s in snapshots]
    expected, denominators, weekly_denominators = {t: set() for t in tickers}, Counter(), Counter()
    for day in calendar:
        if START <= day <= END:
            pos = bisect_left(dates, day) - 1
            if pos >= 0:
                members = set(snapshots[pos]['members'])
                denominators[day[:4]] += len(members)
                for ticker in members.intersection(tickers): expected[ticker].add(day)
    # Original weekly audit anchors: last US session in each W-FRI bin through END.
    import pandas as pd
    index = pd.to_datetime([d for d in calendar if START <= d <= '2027-12-31'])
    anchors = pd.Series(index, index=index).resample('W-FRI').max().dropna()
    anchors = [str(d.date()) for d in anchors if str(d.date()) <= END]
    for day in anchors:
        pos = bisect_left(dates, day) - 1
        if pos >= 0: weekly_denominators[day[:4]] += len(set(snapshots[pos]['members']))
    return expected, denominators, anchors, weekly_denominators


def read_filing_metadata():
    """No price/label/replay object reads. Verify Git blob hash and discard statements."""
    import hashlib
    try:
        tree = subprocess.check_output(['git', 'ls-tree', '-r', FUNDAMENTALS_COMMIT,
                                       'ledger/fundamentals/us/'], cwd=ROOT, stderr=subprocess.DEVNULL).decode()
    except subprocess.CalledProcessError:
        return {}, [], 'NOT_ACCESSIBLE_NO_FETCH_ATTEMPT'
    grouped, files = defaultdict(list), []
    for entry in tree.splitlines():
        meta, path = entry.split('\t');mode, kind, blob_id = meta.split()
        if path in {'ledger/fundamentals/us/inventory.json', 'ledger/fundamentals/us/period-semantics.json',
                    'ledger/fundamentals/us/windows.json'}: continue
        if kind != 'blob' or not path.startswith('ledger/fundamentals/us/finnhub-') or not path.endswith('.jsonl.gz'):
            raise ValueError('UNEXPECTED_FUNDAMENTALS_PATH')
        raw = subprocess.check_output(['git', 'show', FUNDAMENTALS_COMMIT + ':' + path], cwd=ROOT)
        actual = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        if actual != blob_id: raise ValueError('FUNDAMENTALS_BLOB_MISMATCH')
        files.append({'path': path, 'gitBlob': blob_id, 'sha256': D.digest(raw)})
        for line in gzip.decompress(raw).splitlines():
            if line:
                record = json.loads(line)
                grouped[record['ticker']].append({k: record.get(k) for k in
                                                 ('id', 'ticker', 'cik', 'availableFrom', 'acceptedDate', 'periodEnd', 'source')})
    return dict(grouped), files, 'VERIFIED_PINNED_METADATA_ONLY'


def local_candidates(paths, panel, recovery, sessions):
    """Validate each candidate against exact acquisition bytes; never mix quotes."""
    records = {(r['source'], r['ticker']): r for r in recovery['acquisition'] if r.get('status') == 200}
    allowed = {(s['source'], item['auditIdentifier']) for item in recovery['inventory']
               for s in item['candidateSources'] if s['countedInQualifiedCoverage']}
    security_ids = {i['auditIdentifier']: i['securityId'] for i in recovery['inventory']}
    candidates, parsed, keys = defaultdict(lambda: defaultdict(set)), {}, set()
    with tarfile.open(paths['raw'], 'r:gz') as archive:
        members = archive.getmembers()
        if len({m.name for m in members}) != len(members): raise ValueError('DUPLICATE_ARCHIVE_PATH')
        for source, ticker in sorted(allowed):
            record = records[source, ticker]
            member = archive.getmember('raw-' + source.lower() + '/' + ticker + '.csv')
            if not member.isfile() or member.size > 5 * 1024 * 1024: raise ValueError('UNSAFE_RAW_MEMBER')
            raw = archive.extractfile(member).read()
            if D.digest(raw) != record['sha256']: raise ValueError('SOURCE_PRICE_CHECKSUM_MISMATCH')
            parsed[source, ticker], _ = R.parse_csv(raw, sessions)
    for row in panel['rows']:
        if len(row) != 10: raise ValueError('INVALID_CANDIDATE_SCHEMA')
        security_id, ticker, source, day = row[:4]
        key = (ticker, source, day)
        if (source, ticker) not in allowed or security_id != security_ids[ticker] or key in keys:
            raise ValueError('INVALID_SECURITY_OR_DUPLICATE_SOURCE_DATE')
        keys.add(key)
        raw_row = parsed[source, ticker].get(day)
        if raw_row is None or row[4:] != [raw_row[k] for k in ('open', 'high', 'low', 'close', 'volume', 'adj_close')]:
            raise ValueError('PANEL_DOES_NOT_REPRODUCE_SOURCE_BYTES')
        candidates[ticker][day].add(source)
    provenance = {t: {s: {'citation': records[s, t]['url'], 'sha256': records[s, t]['sha256'],
                          'revision': records[s, t]['sourceRevision'], 'acquiredAt': records[s, t]['acquiredAt']}
                      for s, tick in allowed if tick == t} for t in security_ids}
    raw_dates = {t: {s: sorted(parsed[s, t]) for s, tick in parsed if tick == t} for t in security_ids}
    return candidates, provenance, raw_dates


def identity_evidence(item, identity):
    """No future snapshot CIK backfill, no guessed ticker/price issuer binding."""
    grouped = defaultdict(list)
    for snapshot in identity['snapshots']:
        rows = [identity['rows'][idx] for idx in snapshot['rows'] if identity['rows'][idx][0] == item['auditIdentifier']]
        for row in rows:
            grouped[snapshot['date']].append({'kind': 'MEMBERSHIP_CIK_NOT_VERIFIED_PRICE_ISSUER_LINK',
                'date': snapshot['date'], 'cik': row[2], 'name': row[1], 'issuerVerified': False,
                'shareClassVerified': False, 'citation': IDENTITY + '#' + snapshot['date'],
                'sha256': snapshot['rawCsvSha256']})
    dates, records = [], []
    for day, group in sorted(grouped.items()):
        record = dict(group[0])
        record['coincidentSourceSha256s'] = sorted({r['sha256'] for r in group})
        if len({(r['cik'], r['name']) for r in group}) != 1:
            record.update({'kind': 'AMBIGUOUS_SAME_DAY_MEMBER_IDENTITY', 'cik': None, 'name': None})
        dates.append(day);records.append(record)
    return dates, records


def build(directory=None):
    manifest = load_json(ROOT / STORE);recovery = load_json(ROOT / RECOVERY)
    input_manifest = {'version': D.VERSION, 'admissionSpecification': 'US_MF1_DATASET_ADMISSION_V1',
                      'publicInputSha256': {p: D.digest((ROOT / p).read_bytes()) for p in
                                           (STORE, RECOVERY, PROTOCOL, IDENTITY, MEMBERSHIP, BASELINE)},
                      'codeSha256': {p: D.digest((ROOT / p).read_bytes()) for p in
                                     ('pipeline/us_departed_dataset_admission.py', 'scripts/audit_us_departed_dataset_admission.py',
                                      'pipeline/us_departed_price_recovery.py', 'pipeline/replay_calendar.py')},
                      'localArtifacts': {key: {k: manifest[key][k] for k in ('externalFilename', 'sha256', 'bytes')}
                                         for key in ('raw', 'panel')},
                      'fundamentalsCommit': FUNDAMENTALS_COMMIT, 'publisherRule': list(D.SOURCE_PRIORITY),
                      'historicalDenominatorEnds': END, 'calendarVersion': RC.CALENDAR_VERSION}
    local = verify_local_artifacts(directory, manifest)
    baseline = {'identities': 212, 'candidateIdentities': 175, 'coverage': {'FULL': 5, 'PARTIAL': 170, 'NONE': 37},
                'originalMissingSessions': 256402, 'candidateRecoveredSessions': 186910}
    if local is None:
        report = {'version': D.VERSION, 'dataState': 'DATA_UNAVAILABLE', 'verdict': 'BLOCKED',
                  'datasetGateVerdict': 'NOT_ADMITTED', 'historicalDevelopmentMayProceed': False,
                  'historicalReportedBaselineNotRemeasured': baseline, 'finalAdmittedSessions': None,
                  'measuredGateCounts': None, 'inputManifest': input_manifest,
                  'ownerRestoreRequired': [manifest[k]['externalFilename'] for k in ('raw', 'panel')],
                  'accessCounters': {'forwardOutcomes': 0, 'labels': 0, 'models': 0, 'portfolios': 0}}
        report['inputManifestSha256'] = D.digest(D.canonical(input_manifest))
        return report, None
    paths, panel = local
    snapshots, identity = frozen_inputs(recovery)
    calendar = [str(d.date()) for d in RC.sessions('2013-01-01', '2027-12-31', 'US')]
    quality_calendar = {str(d.date()) for d in RC.sessions('1990-01-01', '2027-12-31', 'US')}
    expected, denominators, anchors, weekly_denominators = membership_grid(snapshots, calendar, set(i['auditIdentifier'] for i in recovery['inventory']))
    candidates, provenance, raw_dates = local_candidates(paths, panel, recovery, quality_calendar)
    counts = Counter('FULL' if set(candidates.get(t, {})) == days and days else
                     'PARTIAL' if set(candidates.get(t, {})) & days else 'NONE' for t, days in expected.items())
    covered = sum(len(set(candidates.get(t, {})) & days) for t, days in expected.items())
    if (len(expected), sum(map(len, expected.values())), covered, dict(counts)) != (212, 256402, 186910, baseline['coverage']):
        raise ValueError('ORIGINAL_RECOVERY_NOT_REPRODUCED')
    filings, files, filing_state = read_filing_metadata()
    evidence, visibility, basis_identifiers = {}, Counter(), Counter()
    for item in recovery['inventory']:
        ticker = item['auditIdentifier'];dates, records = identity_evidence(item, identity)
        fs = filings.get(ticker) or filings.get(ticker.replace('-', '.')) or []
        days = expected[ticker]
        window = item['expectedPricingWindow']
        visibility['NO_FILINGS' if not fs else 'VISIBLE_DURING_MEMBERSHIP' if any(
            window['first'] <= str(f.get('availableFrom') or '')[:10] <= window['last'] for f in fs) else 'ONLY_OUTSIDE_MEMBERSHIP'] += 1
        sources = {s for q in candidates.get(ticker, {}).values() for s in q}
        if sources:
            basis_identifiers['HAS_D_OR_F' if sources & {'D', 'F'} else 'A_ONLY' if 'A' in sources else 'E_ONLY'] += 1
        evidence[ticker] = {'securityId': item['securityId'], 'identityHold': item['identityHold'],
                            'identityDates': dates, 'identityRecords': records, 'filings': fs,
                            'rawObservedDays': raw_dates[ticker], 'provenance': provenance[ticker],
                            'basisEvidence': {}, 'lineage': {}, 'terminal': {}, 'memberDays': days}
    if dict(basis_identifiers) != {'HAS_D_OR_F': 59, 'A_ONLY': 113, 'E_ONLY': 3}:
        raise ValueError('REGISTERED_BASIS_COUNTS_NOT_REPRODUCED')
    report, table = D.audit_sessions(expected, candidates, evidence, calendar)
    input_manifest['fundamentalsFiles'] = files
    input_manifest['calendarSha256'] = D.digest(D.canonical(calendar))
    report.update({'dataState': 'EXACT_LOCAL_BYTES_VERIFIED', 'verdict': 'BLOCKED', 'datasetGateVerdict': 'NOT_ADMITTED',
                   'historicalDevelopmentMayProceed': False, 'originalRecoveryReproduced': baseline,
                   'basisIdentifierCounts': dict(basis_identifiers), 'filingMetadataState': filing_state,
                   'filingPresenceByIdentifier': dict(visibility), 'ownerControlledDurableStorage': 'NOT_CONFIRMED',
                   'sourceUseAndRedistributionRights': 'UNVERIFIED; no price payload published',
                   'corporateActionUnresolvedIdentities': 212, 'terminalConsiderationUnresolvedIdentities': 212,
                   'factorFamilyUse': {name: {'admittedSessions': report['finalAdmittedSessions'],
                       'usableForMultifactorOutcomeTest': False, 'reason': 'AD2-AD6 not jointly passed; filing presence is not feature readiness'}
                       for name in ('price_momentum_risk', 'profitability', 'cash_flow', 'investment', 'leverage', 'valuation', 'share_count')},
                   'inputManifest': input_manifest, 'inputManifestSha256': D.digest(D.canonical(input_manifest)),
                   'newReplayGenerationCreated': False, 'scientificDefinitionsModified': False,
                   'privateTableContainsPriceLevels': False, 'admittedDatasetCreated': False,
                   'note': 'Diagnostic admission audit only. Exact local evidence is not durable owner-controlled storage or permission to reuse vendor data.'})
    report['membershipLimitation'] = recovery['membershipLimitation']
    report['sameDaySnapshotMultiplicity'] = {day: count for day, count in sorted(Counter(
        snapshot['date'] for snapshot in identity['snapshots']).items()) if count > 1}
    report['sameDaySnapshotPolicy'] = 'Original stable ordering preserved for baseline membership; conflicting same-day issuer evidence never establishes an issuer link'
    report['fundamentalsVisibilityMeaning'] = '160/41/11 reproduces legacy availableFrom window counts; not CIK linkage or feature readiness'
    report['gateResults'] = {
        'AD1_FROZEN_SNAPSHOT': 'CANDIDATE_HASHES_VERIFIED; NO_ADMITTED_GENERATION; DURABLE_STORAGE_NOT_CONFIRMED',
        'AD2_IDENTITY': 'BLOCKED_PRICE_ISSUER_SHARE_CLASS_LINK',
        'AD3_SINGLE_BASIS': 'ONE_FIXED_PUBLISHER; AS_TRADED_VERIFICATION_UNRESOLVED',
        'AD4_LINEAGE': 'BLOCKED_DATED_SPLIT_AND_DISTRIBUTION_LINEAGE',
        'AD5_TERMINAL': 'EXISTENCE_ONLY_WINDOWS_MEASURED; TERMINAL_CONSIDERATION_UNRESOLVED',
        'AD6_FUNDAMENTALS_LINK': 'BLOCKED_DATED_ISSUER_CIK_LINK',
        'AD7_RESIDUAL_SURVIVORSHIP': 'MEASURED_2013_2026; NO_ADMITTED_IMPROVEMENT',
        'AD8_NO_OUTCOME_ACCESS': 'ZERO_OUTCOME_LABEL_MODEL_PORTFOLIO_READS'}
    original_by_ticker = {item['auditIdentifier']: item for item in recovery['inventory']}
    for item in report['identifiers']:
        old = original_by_ticker[item['ticker']]
        item.update({'historicalIssuerNames': old['historicalIssuerNames'],
                     'historicalCiksReportedNotBackfilled': old['historicalCiksWhereReported'],
                     'sourceCatalogNames': old['sourceCatalogNames'], 'membershipIntervals': old['membershipIntervals'],
                     'sourceProvenance': provenance[item['ticker']],
                     'datedMemberCikEvidence': [{k: record.get(k) for k in ('date', 'cik', 'name', 'citation', 'sha256')}
                                               for record in evidence[item['ticker']]['identityRecords'] if record.get('cik')],
                     'filingToPriceIssuerLinkStatus': 'NO_FILINGS' if not item['filingRecords'] else 'UNVERIFIED_PRICE_ISSUER_LINK',
                     'terminalConsiderationStatus': 'UNRESOLVED', 'corporateActionLineageStatus': 'UNRESOLVED'})
    table_by_day = {(row['ticker'], row['date']): row['status'] for row in table}
    for year, item in report['annual'].items():
        original = recovery['annualMissingness'][year]
        weekly_missing = sum(1 for t, days in expected.items() for day in anchors
                             if day[:4] == year and day in days and table_by_day[t, day] != 'ADMITTED')
        candidate_unresolved = sum(v for k, v in item.items() if k.startswith('UNRESOLVED_'))
        item.update({'allUniverseDailyMemberDates': denominators[year],
                     'residualMissingDailySessions': item.get('originalMissing', 0) - item.get('ADMITTED', 0),
                     'residualMissingDailyPct': round(100 * (item.get('originalMissing', 0) - item.get('ADMITTED', 0)) / denominators[year], 4),
                     'beforeWeeklyPct': original['beforeMissingPricePanelsPct'], 'candidateAfterWeeklyPct': original['afterCandidateMissingObservationsPct'],
                     'residualNoAdmittedWeeklyMemberDates': weekly_missing,
                     'residualNoAdmittedWeeklyPct': round(100 * weekly_missing / weekly_denominators[year], 4),
                     'candidateWindowUnresolvedSessions': candidate_unresolved,
                     'candidateWindowUnresolvedPct': round(100 * candidate_unresolved / item['candidateRecovered'], 4) if item.get('candidateRecovered') else None})
    if report['finalAdmittedSessions'] == 0 and any(
            item['residualNoAdmittedWeeklyPct'] != item['beforeWeeklyPct'] for item in report['annual'].values()):
        raise ValueError('ORIGINAL_WEEKLY_DENOMINATOR_NOT_REPRODUCED')
    return report, table


def write_private_table(path, table):
    path = Path(path).resolve()
    if any((p / '.git').is_file() or (p / '.git/HEAD').is_file() for p in path.parents):
        raise ValueError('SESSION_TABLE_MUST_BE_OUTSIDE_GIT_CHECKOUT')
    with path.open('xb') as handle:
        handle.write(gzip.compress(D.canonical(table), mtime=0))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--private-artifacts', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--private-session-table', type=Path)
    args = parser.parse_args(argv)
    if args.report.exists(): raise ValueError('REFUSE_REPORT_OVERWRITE')
    report, table = build(args.private_artifacts)
    if args.private_session_table and table is not None: write_private_table(args.private_session_table, table)
    with args.report.open('xb') as handle: handle.write(D.canonical(report) + b'\n')
    print(json.dumps({k: report[k] for k in ('dataState', 'verdict', 'finalAdmittedSessions')}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
