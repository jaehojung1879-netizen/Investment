"""Verify retained official source bytes and audit full PIT Top120 membership.

No source contact, price panel, target, model, portfolio or sealed study execution.
"""
from __future__ import annotations
import argparse
import base64
import gzip
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import kr_industry_membership as K  # noqa: E402
from scripts.collect_kr_industry_membership_sources import classification_markers  # noqa: E402

DATA = 'data/kr-industry-membership-foundation-v1'
CRITERIA = 'research_specs/kr-industry-membership-foundation-v1/criteria.json'
SPEC = 'research_specs/kr-industry-membership-foundation-v1.json'


def read(root, rel):
    return json.loads((Path(root) / rel).read_text())


def write_new(path, value, compressed=False):
    raw = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=None if compressed else 2) + '\n').encode()
    if compressed:
        raw = gzip.compress(raw, mtime=0)
    with path.open('xb') as stream:
        stream.write(raw)


def verify_sources(root):
    root = Path(root)
    plan_raw = (root / 'research_specs/kr-industry-membership-foundation-v1/acquisition-plan.json').read_bytes()
    plan = json.loads(plan_raw)
    provenance = read(root, DATA + '/artifact-provenance.json')
    if len(provenance['artifacts']) != 21 or {a['batch'] for a in provenance['artifacts']} != set(range(21)):
        raise ValueError('ALL_FIXED_SOURCE_BATCHES_REQUIRED')
    records, objects, calls = [], {}, 0
    for batch in range(21):
        manifest = read(root, DATA + f'/acquired-dart/manifest-{batch:03d}.json')
        if manifest['batch'] != batch or manifest['acquisitionPlanSha256'] != K.sha256(plan_raw):
            raise ValueError('ACQUISITION_PLAN_CHANGED')
        expected = plan['targets'][batch * 20:(batch + 1) * 20]
        if [r['target'] for r in manifest['records']] != expected or manifest['requests'] > len(expected) * 3:
            raise ValueError('SOURCE_INVENTORY_OR_REQUEST_BUDGET_CHANGED')
        archive = (root / DATA / 'acquired-dart' / manifest['archive']).read_bytes()
        if K.sha256(archive) != manifest['archiveSha256']:
            raise ValueError('PUBLIC_SOURCE_ARCHIVE_CHANGED')
        batch_objects = {key: base64.b64decode(value, validate=True) for key, value in json.loads(gzip.decompress(archive)).items()}
        if any(K.sha256(raw) != key for key, raw in batch_objects.items()):
            raise ValueError('PUBLIC_RAW_SOURCE_CHANGED')
        for record in manifest['records']:
            for response in record['responses']:
                if response.get('sha256') and response['sha256'] not in batch_objects:
                    raise ValueError('SOURCE_RESPONSE_NOT_RETAINED')
            for section in record['sections']:
                markers, codes = classification_markers(batch_objects[section['sha256']])
                if markers != section['classificationMarkers'] or codes != section['explicitCodeCandidates']:
                    raise ValueError('SOURCE_READING_LIST_CHANGED')
                if section['node']['rcpNo'] != record['target']['receiptNos'][0]:
                    raise ValueError('RECEIPT_IDENTITY_CHANGED')
        objects.update(batch_objects)
        records.extend(manifest['records'])
        calls += manifest['requests']
    if calls > plan['maxCalls'] or [r['target'] for r in records] != plan['targets']:
        raise ValueError('FULL_FIXED_ACQUISITION_PLAN_REQUIRED')
    terminal_raw = (root / DATA / 'retained-terminal-documents.jsonl.gz').read_bytes()
    if K.sha256(terminal_raw) != '98c1475f888cb07b5c8865b8902516e463bd934281d1f4744a7aba4b4d687071':
        raise ValueError('RETAINED_TERMINAL_SOURCE_CHANGED')
    terminal = [json.loads(line) for line in gzip.decompress(terminal_raw).splitlines()]
    for record in terminal:
        for member in record['members']:
            raw = member['text'].encode(member['encodingUsed'])
            if K.sha256(raw) != member['sha256']:
                raise ValueError('RETAINED_DART_MEMBER_CHANGED')
            objects.setdefault(member['sha256'], raw)
    for reference in read(root, DATA + '/reference-sources/manifest.json'):
        if reference.get('sourceFile'):
            raw = (root / reference['sourceFile']).read_bytes()
            if K.sha256(raw) != reference['sha256']:
                raise ValueError('REFERENCE_SOURCE_CHANGED')
            if reference['status'] == 200:
                objects.setdefault(K.sha256(raw), raw)
    return records, objects, terminal, calls


def build(root=ROOT):
    root = Path(root)
    criteria_raw = (root / CRITERIA).read_bytes()
    criteria = json.loads(criteria_raw)
    records, objects, terminal, calls = verify_sources(root)
    inputs, identity = read(root, DATA + '/top120-inputs.json'), read(root, DATA + '/identity-provenance.json')
    if inputs['sourceCommit'] != criteria['researchUniverseSourceCommit']:
        raise ValueError('PINNED_PIT_UNIVERSE_CHANGED')
    if K.sha256((root / DATA / 'identity-inventory.json').read_bytes()) != identity['sourceSha256']:
        raise ValueError('REUSED_IDENTITY_SOURCE_CHANGED')
    if K.sha256((root / identity['terminalSourcePath']).read_bytes()) != identity['terminalSourceSha256']:
        raise ValueError('REUSED_TERMINAL_CONTRACT_CHANGED')
    reviewed = read(root, DATA + '/reviewed-assignments.json')
    rows, rejected, admitted_reviews = [], [], []
    for candidate in reviewed['assignments']:
        raw = objects.get(candidate['source_sha256'])
        if raw is None:
            raise ValueError('ASSIGNMENT_SOURCE_MISSING')
        row, reasons = K.admit_assignment(candidate, raw, objects)
        if row is None:
            rejected.append({'security_id': candidate.get('security_id'), 'reasons': reasons})
        else:
            if row.ticker not in inputs['securities']:
                raise ValueError('ASSIGNMENT_OUTSIDE_PINNED_UNIVERSE')
            rows.append(row)
            admitted_reviews.append(candidate)
    mapping = K.mapping_document(rows, K.sha256(criteria_raw))
    mapping.update(admissionReviews=admitted_reviews, rejectedAssignments=rejected)
    mapping['unknownSecurities'] = [
        {'security_id': info['security_id'], 'ticker': ticker,
         **{k: None for k in ('taxonomy_id', 'taxonomy_version', 'industry_id', 'valid_from', 'valid_to', 'release_date', 'known_to', 'source', 'source_sha256')},
         'identity_provenance': {'universeSourceCommit': inputs['sourceCommit'], 'krxStockCode': info['stock_code'],
                                'existingIssuerMappings': identity['issuerMappings'].get(ticker, [])},
         'status': 'UNKNOWN', 'reason': 'NO_ADMISSIBLE_DATED_CLASSIFICATION'}
        for ticker, info in sorted(inputs['securities'].items()) if not any(r.ticker == ticker for r in rows)]
    schedule, stamps = K.top120_schedule(inputs)
    extended, _ = K.top120_schedule(inputs, start='2013-01-01')
    audits = [K.coverage(rows, schedule, taxonomy, criteria) for taxonomy in criteria['candidateTaxonomiesInPriorityOrder']]
    annual_extended = [K.coverage(rows, extended, taxonomy, criteria) for taxonomy in criteria['candidateTaxonomiesInPriorityOrder']]
    chosen = K.select_taxonomy(audits, criteria)
    source = {'plannedReceipts': len(records), 'publicRequests': calls, 'retainedTerminalReceiptsScanned': len(terminal),
              'http200ReceiptPages': sum(r['responses'][0].get('status') == 200 for r in records),
              'http200SectionsParsed': sum(len(r['sections']) for r in records),
              'classificationMentionSections': sum(bool(s['classificationMarkers']) for r in records for s in r['sections']),
              'codeShapedCandidateSections': sum(bool(s['explicitCodeCandidates']) for r in records for s in r['sections']),
              'retainedTerminalCodeRelatedMentionSections': len(read(root, DATA + '/classification-observations.json')['terminalClassificationMentions']),
              'admittedAssignmentRows': len(rows), 'readingListIsNotMembership': True,
              'eraStatus': [{'fiscalYear': y, 'plannedReceipts': sum(r['target']['fiscalYear'] == y for r in records),
                             'http200SectionsParsed': sum(len(r['sections']) for r in records if r['target']['fiscalYear'] == y)}
                            for y in sorted({r['target']['fiscalYear'] for r in records})]}
    audit = {'contract': K.CONTRACT, 'decision': 'READY_FOR_INDUSTRY_ANATOMY' if chosen else 'DATA_FOUNDATION_INSUFFICIENT',
             'selectedTaxonomy': chosen, 'selectedGranularity': chosen, 'criteriaSha256': K.sha256(criteria_raw),
             'sourceAcquisition': source, 'universeSourceCommit': inputs['sourceCommit'], 'universeSnapshots': len(inputs['snapshots']),
             'everTop120Securities': len(inputs['securities']), 'issuerIdentityMappingsAvailable': len(identity['issuerMappings']),
             'researchSignalDates': len(schedule), 'researchUniverseNameDates': sum(map(len, schedule.values())),
             'firstSignalDate': min(schedule), 'lastSignalDate': max(schedule), 'membershipSha256': mapping['membershipSha256'],
             'candidateAudits': [{k: v for k, v in a.items() if k != 'dates'} for a in audits],
             'extendedAnnualHistory': [{'taxonomy_id': a['taxonomy_id'], 'annual': a['annual']} for a in annual_extended],
             'terminalSecurityAudit': [{'security_id': 'KRX:' + ticker,
                                        'universeNameDates': sum('KRX:' + ticker in names for names in schedule.values()),
                                        'classifiedNameDatesByCandidate': {a['taxonomy_id']: sum(
                                            'KRX:' + ticker in schedule[d['date']] and 'KRX:' + ticker not in d['missingSecurityIds'] for d in a['dates']) for a in audits}}
                                       for ticker in identity['terminalSecurities']],
             'historicalOutcomeComputed': False, 'factorPerformanceComputed': False, 'modelFitPerformed': False,
             'portfolioResultComputed': False, 'priorStudyRerun': False, 'productionWired': False}
    return mapping, audit, {'contract': K.CONTRACT, 'universeSourceSnapshotBySignalDate': stamps, 'candidateAudits': audits}


def verify_closure(root=ROOT):
    root = Path(root)
    raw = (root / SPEC).read_bytes()
    if K.sha256(raw) != (root / SPEC).with_suffix('.sha256').read_text().strip():
        raise ValueError('INDUSTRY_SPEC_CHANGED')
    for path, wanted in json.loads(raw)['dependencyHashes'].items():
        if '..' in Path(path).parts or not path.startswith(('pipeline/', 'scripts/', 'tests/', 'research_specs/', DATA + '/', 'docs/kr-industry-membership-foundation-v1')):
            raise ValueError('UNSUPPORTED_AUDIT_INPUT')
        if K.sha256((root / path).read_bytes()) != wanted:
            raise ValueError('INDUSTRY_DEPENDENCY_CHANGED:' + path)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify', action='store_true')
    parser.add_argument('--output-root', type=Path)
    args = parser.parse_args()
    mapping, audit, signals = build()
    if args.verify:
        verify_closure()
        assert mapping == read(ROOT, DATA + '/membership.json')
        assert audit == read(ROOT, 'docs/kr-industry-membership-foundation-v1-audit.json')
        assert signals == json.loads(gzip.decompress((ROOT / DATA / 'signal-date-audits.json.gz').read_bytes()))
    else:
        if args.output_root is None:
            raise ValueError('FRESH_OUTPUT_ROOT_REQUIRED')
        args.output_root.mkdir(parents=True, exist_ok=False)
        write_new(args.output_root / 'membership.json', mapping)
        write_new(args.output_root / 'audit.json', audit)
        write_new(args.output_root / 'signal-date-audits.json.gz', signals, compressed=True)
    print(audit['decision'] + '; source and membership coverage only')
