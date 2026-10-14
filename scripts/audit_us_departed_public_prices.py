"""Audit an isolated real acquisition, or replay its bounded candidate archive.

No research harness, labels, forward returns, or production publication path.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import gzip
import io
import json
from pathlib import Path
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import us_departed_price_recovery as R  # noqa: E402
from pipeline import alpha_opportunity_v3_identity as ID  # noqa: E402
from pipeline import alpha_opportunity_v3_survivorship as S  # noqa: E402
from pipeline import replay_calendar as RC  # noqa: E402

AUDIT = 'docs/results/alpha-opportunity-model-v3-survivorship-audit.json'
MEMBERSHIP = 'research_specs/alpha-opportunity-model-v1-us-membership.json.gz'
IDENTITY = 'research_specs/alpha-opportunity-model-v3-us-identity-evidence.json.gz'
START, END = '2013-01-01', '2026-09-14'
CONTROLS = ['AAPL', 'MSFT', 'AMZN', 'JNJ', 'XOM']


def inputs():
    audit = json.loads((ROOT / AUDIT).read_bytes())
    for key, path in [('usMembership', MEMBERSHIP), ('usIdentityEvidence', IDENTITY)]:
        if audit['inputs'][key]['sha256'] != R.digest((ROOT / path).read_bytes()):
            raise ValueError('SEALED_INPUT_HASH_MISMATCH')
    membership = json.loads(gzip.decompress((ROOT / MEMBERSHIP).read_bytes()))['snapshots']
    evidence = json.loads(gzip.decompress((ROOT / IDENTITY).read_bytes()))
    membership = ID.normalized_snapshots(membership, {k: v['resolvedTo'] for k, v in audit['regions']['US']['identity']['malformed'].items() if v['resolvedTo']})
    missing = audit['regions']['US']['_sets']['noPanel']
    if len(missing) != 212 or len(set(missing)) != 212:
        raise ValueError('NOT_THE_REGISTERED_212_IDENTIFIERS')
    return audit, membership, evidence, missing


def names_from_catalog(raw):
    out = {}
    for row in csv.reader(io.StringIO(raw.decode())):
        if len(row) >= 2 and row[0].startswith('WIKI/'):
            name = row[1].split(' Prices, Dividends')[0]
            out[row[0].split('/')[-1].replace('_', '-')] = name
    return out


def expected_members(snapshots, sessions, missing):
    expected = {t: set() for t in missing}
    denominators = Counter()
    for day in sessions:
        if START <= day <= END:
            snap = S.snapshot_on(snapshots, day)
            if snap:
                denominators[day[:4]] += len(snap['members'])
                for ticker in set(snap['members']) & set(missing):
                    expected[ticker].add(day)
    return expected, denominators


def intervals(days):
    # Contiguous membership episodes in the given session calendar are recorded separately.
    return {'first': min(days) if days else None, 'last': max(days) if days else None, 'sessions': len(days)}


def audit(raw_root):
    raw_root = Path(raw_root)
    registered, snapshots, identity, missing = inputs()
    import exchange_calendars as xc
    # Quality checks outside the frozen replay window use a separate XNYS calendar.
    # The scientific daily/weekly membership denominators still use the pinned calendar.
    calendar = xc.get_calendar('XNYS', start='1900-01-01', end='2027-12-31')
    sessions = {str(d.date()) for d in calendar.sessions}
    study_sessions = [str(d.date()) for d in RC.sessions(START, END, 'US')]
    daily_expected, daily_denominator = expected_members(snapshots, study_sessions, missing)
    weekly = S.weekly_grid(RC.sessions('2013-01-01', '2027-12-31', 'US'), END)
    weekly_expected, weekly_denominator = expected_members(snapshots, weekly, missing)
    wiki = names_from_catalog((raw_root / 'wiki-catalog.csv').read_bytes())
    catalogs = {'A': wiki, 'F': wiki, 'G': wiki}
    catalogs['D'] = {r[0]: r[1] for r in csv.reader(io.StringIO((raw_root / 'd-symbols.csv').read_text())) if len(r) >= 2}
    catalogs['E'] = {r['Symbol']: r['Name'] for r in csv.DictReader(io.StringIO((raw_root / 'e-symbols.csv').read_text()))}
    all_records = [{**r, 'source': 'A'} for r in json.loads((raw_root / 'source-a-acquisition.json').read_text())['records']]
    all_records += json.loads((raw_root / 'additional-acquisition.json').read_text())['records']
    parsed, acquisition = {}, []
    for record in all_records:
        if record.get('status') != 200:
            acquisition.append(record);continue
        source, ticker = record['source'], record['ticker']
        path = raw_root / ('raw-' + source.lower()) / (ticker + '.csv')
        raw = path.read_bytes()
        if R.digest(raw) != record['sha256']:
            raise ValueError('ACQUIRED_OBJECT_HASH_MISMATCH')
        try:
            rows, quality = R.parse_csv(raw, sessions)
        except (ValueError, UnicodeDecodeError) as exc:
            rows, quality = {}, {'error': str(exc), 'rawRows': 0, 'validRows': 0}
        parsed[source, ticker] = rows
        acquisition.append({**record, 'adjustmentBasis': R.BASIS[source], 'quality': quality})
    summary_by_symbol = {}
    for record in acquisition:
        summary_by_symbol.setdefault(record['ticker'], []).append(record)
    rows, covered_weekly, covered_daily, upper_daily, ohlcv_daily = [], Counter(), Counter(), Counter(), Counter()
    no_panel_weekly = Counter()
    for ticker in missing:
        names = sorted({r[1] for r in identity['rows'] if r[0].replace('.', '-') == ticker})
        ciks = sorted({str(r[2]) for r in identity['rows'] if r[0].replace('.', '-') == ticker and r[2]})
        catalog_names = {source: cat[ticker] for source, cat in catalogs.items() if ticker in cat}
        issuer_matches = {source for source, name in catalog_names.items() if any(
            R.normalized_name(name) == R.normalized_name(n) or
            (R.normalized_name(n), R.normalized_name(name)) in R.NAME_ALIASES.get(ticker, set()) for n in names)}
        expected = daily_expected[ticker]
        qualified, plausible, ohlcv = set(), set(), set()
        source_states = []
        for record in summary_by_symbol.get(ticker, []):
            source = record['source']; observations = parsed.get((source, ticker), {})
            state, overlap = R.coverage_state(expected, observations)
            plausible.update(overlap)
            postdates = bool(observations and expected and min(observations) > max(expected))
            accepted = source in issuer_matches and ticker not in R.IDENTITY_HOLDS and source != 'G' and not postdates
            if accepted:
                qualified.update(overlap)
                ohlcv.update(d for d in overlap if all(observations[d][k] is not None and observations[d][k] > 0 for k in ('open', 'high', 'low', 'close', 'volume')))
            source_states.append({'source': source, 'tickerWindowCoverage': state, 'overlapSessions': len(overlap),
                                  'issuerNameCorroborated': source in issuer_matches,
                                  'countedInQualifiedCoverage': accepted and bool(overlap),
                                  'identityState': 'HISTORY_POSTDATES_MEMBERSHIP_NOT_THIS_EPISODE' if postdates else
                                                   'ENTITY_OR_SECURITY_CLASS_CHANGE_UNRESOLVED' if ticker in R.IDENTITY_HOLDS else
                                                   'UPSTREAM_UNVERIFIED' if source == 'G' else
                                                   'NAME_AND_DATED_MEMBERSHIP_CORROBORATED_NOT_PERMANENT_ID' if accepted else 'ISSUER_NAME_NOT_CORROBORATED'})
        state, _ = R.coverage_state(expected, qualified)
        for d in qualified: covered_daily[d[:4]] += 1
        for d in plausible: upper_daily[d[:4]] += 1
        for d in ohlcv: ohlcv_daily[d[:4]] += 1
        for d in weekly_expected[ticker]:
            no_panel_weekly[d[:4]] += 1
            if d in qualified: covered_weekly[d[:4]] += 1
        category = next((k for k, vals in registered['regions']['US']['identity']['categories'].items() if ticker in vals), None)
        # A security key preserves this exact audited identifier + issuer evidence. Not a claimed CUSIP.
        security_id = R.digest(R.canonical([R.digest((ROOT / AUDIT).read_bytes()), ticker, names, ciks]))[:20]
        member_intervals = []
        active = None
        for s in snapshots:
            present = ticker in s['members']
            if present and active is None: active = s['date']
            if not present and active is not None:
                member_intervals.append({'observedFrom': active, 'observedAbsentFrom': s['date'], 'boundary': 'STRICTLY_AFTER_SNAPSHOT_NOT_AUTHORITATIVE_EFFECTIVE_DATE'});active = None
        if active is not None: member_intervals.append({'observedFrom': active, 'observedAbsentFrom': None, 'boundary': 'RIGHT_CENSORED'})
        rows.append({'auditIdentifier': ticker, 'securityId': security_id, 'securityIdKind': 'AUDIT_IDENTIFIER_WITH_ISSUER_EVIDENCE_NOT_PERMANENT_ID',
                     'historicalIssuerNames': names, 'historicalCiksWhereReported': ciks,
                     'sourceCatalogNames': catalog_names, 'sealedIdentityCategory': category,
                     'symbolReuseFlagFromSealedAudit': category == 'TICKER_REUSE_DIFFERENT_ISSUER',
                     'membershipIntervals': member_intervals, 'expectedPricingWindow': intervals(expected),
                     'candidateSources': source_states, 'sourceAWikiCatalogMatch': ticker in wiki, 'reviewedNameAliases': sorted(R.NAME_ALIASES.get(ticker, set())),
                     'qualifiedPriceCoverage': state, 'coveredSessions': len(qualified), 'missingSessions': len(expected - qualified),
                     'ohlcvCoveredSessions': len(ohlcv), 'tickerDateOnlyUpperBoundSessions': len(plausible),
                     'identityHold': ticker in R.IDENTITY_HOLDS,
                     'corporateActionState': 'EVENT_LINEAGE_AND_ORIGINAL_SHARE_BASIS_UNRESOLVED',
                     'terminalConsideration': 'UNRESOLVED_NO_ZERO_OR_LAST_PRICE_FILL', 'studyReady': False})
    years = {}
    for year in sorted(weekly_denominator):
        expected_base = registered['regions']['US']['memberDatesByYear'][year]
        before = round(100 * no_panel_weekly[year] / weekly_denominator[year], 4)
        if weekly_denominator[year] != expected_base['memberDates'] or abs(before - expected_base['NO_PANEL']) > .00011:
            raise ValueError('SEALED_WEEKLY_MISSINGNESS_DENOMINATOR_DOES_NOT_REPRODUCE:' + year)
        years[year] = {'weeklyMemberDates': weekly_denominator[year], 'beforeMissingPricePanelsPct': before,
                       'afterCandidateMissingObservationsPct': round(100 * (no_panel_weekly[year] - covered_weekly[year]) / weekly_denominator[year], 4),
                       'recoveredWeeklyMemberDates': covered_weekly[year],
                       'dailyMemberDates': daily_denominator[year],
                       'departedMissingDailySessionsBefore': sum(d[:4] == year for dates in daily_expected.values() for d in dates),
                       'qualifiedCoveredDailySessions': covered_daily[year], 'ohlcvCoveredDailySessions': ohlcv_daily[year],
                       'tickerDateOnlyUpperBoundDailySessions': upper_daily[year]}
    missing_records = [r for r in acquisition if r['ticker'] in missing]
    valid_dates = [d for (s, t), obs in parsed.items() if t in missing for d in obs]
    qualified_rows = sum(r['coveredSessions'] for r in rows)
    source_counts = {}
    for source in R.BASIS:
        recs = [r for r in missing_records if r['source'] == source]
        source_counts[source] = {'historiesDownloaded': len(recs), 'rawRows': sum(r['quality']['rawRows'] for r in recs),
                                 'validRows': sum(r['quality']['validRows'] for r in recs)}
    comparisons = []
    from pipeline.us_dual_benchmark_data import SealedReader
    reader = SealedReader(ROOT)
    manifest = reader.manifest()
    reference = {t: {} for t in CONTROLS}
    # Read only daily price levels for overlapping control windows; never labels/outcomes.
    for component, refs in manifest['components'].items():
        if not component.startswith('price/') or not ('2013-01' <= component[6:] <= '2020-12'):
            continue
        for ref in refs:
            for row in reader.component(ref):
                if row['ticker'] in reference and isinstance(row.get('Close'), (int, float)) and row['Close'] > 0:
                    reference[row['ticker']][row['date']] = row['Close']
    for t in CONTROLS:
        a = {d: v['close'] for d, v in parsed.get(('A', t), {}).items()}
        f = {d: v['adj_close'] for d, v in parsed.get(('F', t), {}).items() if v['adj_close'] is not None}
        comparisons.append({'ticker': t, 'pair': 'SOURCE_A_VS_ARCHIVED_YAHOO_ADJCLOSE', **R.compare_levels(a, f)})
        comparisons.append({'ticker': t, 'pair': 'SOURCE_A_VS_EXISTING_SEALED_YAHOO_TOTAL_RETURN_LEVEL', **R.compare_levels(a, reference[t])})
    result = {'version': R.VERSION, 'baseMainSha': '0a9fb1d96219f4402d9eb341cabbb616f786e52d',
              'returnsComputed': False, 'labelsConstructed': False, 'outcomesReadForResearch': False,
              'p4InputsModified': False, 'studyReady': False,
              'inputSha256': {p: R.digest((ROOT / p).read_bytes()) for p in (AUDIT, MEMBERSHIP, IDENTITY)},
              'totalMissingAuditIdentifiers': len(missing), 'sourceAWikiCatalogEntriesActuallyRead': len(wiki),
              'sourceAWikiCatalogMatches': len(set(missing) & set(wiki)),
              'priceHistoriesDownloaded': len(missing_records), 'distinctAuditIdentifiersWithDownloadedHistory': len({r['ticker'] for r in missing_records}),
              'rawRowsAcquired': sum(r['quality']['rawRows'] for r in missing_records),
              'firstObservedDate': min(valid_dates), 'lastObservedDate': max(valid_dates),
              'qualifiedPriceCoverageCounts': dict(Counter(r['qualifiedPriceCoverage'] for r in rows)),
              'qualifiedCoveredMembershipSessions': qualified_rows,
              'remainingNoQualifiedCoverageIdentifiers': [r['auditIdentifier'] for r in rows if r['qualifiedPriceCoverage'] == 'NONE'],
              'identityHoldIdentifiers': sorted(R.IDENTITY_HOLDS),
              'corporateActionUnresolvedIdentifiers': len(missing), 'terminalConsiderationUnresolvedIdentifiers': len(missing),
              'sourceCounts': source_counts,
              'recycledSymbolIdentitiesStillWithoutQualifiedCoverage': [r['auditIdentifier'] for r in rows if r['symbolReuseFlagFromSealedAudit'] and r['qualifiedPriceCoverage'] == 'NONE'],
              'remainingBlockersByIdentifier': {r['auditIdentifier']: ('IDENTITY_OR_SHARE_CLASS' if r['identityHold'] else 'NO_PUBLIC_HISTORY_DOWNLOADED' if not r['candidateSources'] else 'SOURCE_OR_IDENTITY_OR_OBSERVATION_WINDOW') for r in rows if r['qualifiedPriceCoverage'] == 'NONE'},
              'annualMissingness': years, 'inventory': rows, 'acquisition': acquisition,
              'providerAccessProbes': json.loads((raw_root / 'other-source-probes.json').read_text()),
              'coverageMeaning': 'Qualified positive-close existence under historical issuer-name and strictly-earlier snapshot corroboration. Not total-return readiness. Sources/bases not concatenated. G unknown provider excluded. Partial includes any missing expected session. Weekly before exactly reproduces sealed NO_PANEL; after measures absent candidate observations, not a rewritten sealed audit.',
              'membershipLimitation': registered['regions']['US']['membershipSnapshots'],
              'overlapCrossValidation': comparisons,
              'crossValidationLimitation': 'Different publishers and intended WIKI-vs-Yahoo route, but Source A has Yahoo fallback and no per-file upstream attestation. Independent-provider verification is NOT complete. Shape ratios do not authorize concatenation or event adjustment.'}
    return result, parsed


def archive(raw_root, path):
    require_nonpublic_output(path)
    """Deterministic, bounded raw artifact (no checkout/frozen-store writes)."""
    with Path(path).open('xb') as handle:
        with gzip.GzipFile(fileobj=handle, mode='wb', mtime=0, filename='') as gz:
            with tarfile.open(fileobj=gz, mode='w') as tar:
                uncompressed = 0
                for p in sorted(Path(raw_root).rglob('*')):
                    if p.is_symlink(): raise ValueError('SYMLINK_IN_RAW_STAGING')
                    if not p.is_file(): continue
                    uncompressed += p.stat().st_size
                    if uncompressed > 128 * 1024 * 1024: raise ValueError('UNCOMPRESSED_ARTIFACT_BYTE_BUDGET')
                    raw = p.read_bytes();info = tarfile.TarInfo(str(p.relative_to(raw_root)))
                    info.size = len(raw);info.mtime = 0;info.mode = 0o644
                    tar.addfile(info, io.BytesIO(raw))
    if Path(path).stat().st_size > 32 * 1024 * 1024:
        Path(path).unlink();raise ValueError('RAW_ARTIFACT_EXCEEDS_32_MIB')


def candidate_panel(result, parsed, path):
    require_nonpublic_output(path)
    """Long-form per-source observations; no adjusted-close stitching or selection."""
    _, snapshots, _, missing = inputs()
    study_sessions = [str(d.date()) for d in RC.sessions(START, END, 'US')]
    expected, _ = expected_members(snapshots, study_sessions, missing)
    observations = []
    for item in result['inventory']:
        ticker = item['auditIdentifier']
        for source in item['candidateSources']:
            if not source['countedInQualifiedCoverage']: continue
            for day, row in sorted(parsed[source['source'], ticker].items()):
                if day in expected[ticker]:
                    observations.append([item['securityId'], ticker, source['source'], day,
                                         *[row[k] for k in ('open', 'high', 'low', 'close', 'volume', 'adj_close')]])
    payload = {'version': R.VERSION, 'purpose': 'CANDIDATE_PRICE_OBSERVATIONS_NOT_RESEARCH_READY',
               'rowFields': ['securityId', 'auditIdentifier', 'source', 'date', 'open', 'high', 'low', 'close', 'volume', 'adjClose'],
               'sourceBases': R.BASIS, 'terminalConsiderationResolved': False,
               'issuerIdentity': 'NAME_CORROBORATED_NOT_PERMANENT_SECURITY_ID_VERIFIED', 'rows': observations}
    raw = R.canonical(payload)
    compressed = gzip.compress(raw, mtime=0)
    if len(compressed) > 16 * 1024 * 1024: raise ValueError('CANDIDATE_PANEL_BYTE_BUDGET')
    with Path(path).open('xb') as handle: handle.write(compressed)
    result['candidatePanelRevision'] = {'version': R.VERSION, 'sha256': R.digest(compressed),
                                      'decompressedSha256': R.digest(raw), 'bytes': len(compressed),
                                      'perSourceObservations': len(observations), 'sourcesNotConcatenated': True,
                                      'uniqueMembershipSessions': result['qualifiedCoveredMembershipSessions']}
    dates = [r[3] for r in observations]
    result['qualifiedMembershipFirstDate'] = min(dates) if dates else None
    result['qualifiedMembershipLastDate'] = max(dates) if dates else None


def require_nonpublic_output(path):
    """Reject payload output inside any Git checkout before reading inputs."""
    resolved = Path(path).resolve()
    if any((parent / '.git').is_file() or ((parent / '.git' / 'HEAD').is_file())
           for parent in resolved.parents):
        raise ValueError('PRICE_PAYLOAD_MUST_BE_OUTSIDE_GIT_CHECKOUT')


def verify_candidate_artifacts(manifest, directory):
    """Verify explicitly supplied non-public artifacts; never fetch or publish."""
    directory = Path(directory)
    for key in ('raw', 'panel'):
        item = manifest[key]
        name = item['externalFilename']
        if Path(name).name != name:
            raise ValueError('INVALID_EXTERNAL_FILENAME')
        data = (directory / name).read_bytes()
        if len(data) != item['bytes'] or R.digest(data) != item['sha256']:
            raise ValueError('ARTIFACT_CHECKSUM_MISMATCH')
    expanded = gzip.decompress((directory / manifest['panel']['externalFilename']).read_bytes())
    if R.digest(expanded) != manifest['panel']['decompressedSha256']:
        raise ValueError('EXPANDED_CHECKSUM_MISMATCH')
    panel = json.loads(expanded)
    rows = panel['rows']
    if (panel['terminalConsiderationResolved'] is not False
            or len(rows) != manifest['panel']['perSourceObservations']
            or any(len(row) != 10 for row in rows)
            or len({(row[0], row[2], row[3]) for row in rows}) != len(rows)
            or any(row[2] not in {'A', 'D', 'E', 'F'} or not isinstance(row[7], (int, float))
                   or not 0 < row[7] < float('inf') for row in rows)
            or any(row[8] is not None for row in rows if row[2] == 'E')):
        raise ValueError('CANDIDATE_OBSERVATION_INTEGRITY')
    return {'rawSha256': manifest['raw']['sha256'], 'panelSha256': manifest['panel']['sha256'],
            'perSourceObservations': len(rows)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw-root', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--archive', type=Path)
    parser.add_argument('--candidate-panel', type=Path)
    args = parser.parse_args(argv)
    if args.raw_root.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError('RAW_STAGING_MUST_BE_OUTSIDE_CHECKOUT')
    if args.report.exists(): raise ValueError('REFUSE_REPORT_OVERWRITE')
    for output in (args.archive, args.candidate_panel):
        if output is not None: require_nonpublic_output(output)
    result, parsed = audit(args.raw_root)
    if args.candidate_panel: candidate_panel(result, parsed, args.candidate_panel)
    if args.archive:
        archive(args.raw_root, args.archive)
        result['rawCandidateArtifact'] = {'sha256': R.digest(args.archive.read_bytes()), 'bytes': args.archive.stat().st_size,
                                         'retention': 'BOUNDED_VERSIONED_CANDIDATE_ARTIFACT_NOT_FROZEN_INPUT'}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_bytes(R.canonical(result) + b'\n')
    print(json.dumps({k: result[k] for k in ('priceHistoriesDownloaded', 'distinctAuditIdentifiersWithDownloadedHistory', 'rawRowsAcquired', 'qualifiedPriceCoverageCounts', 'qualifiedCoveredMembershipSessions')}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
