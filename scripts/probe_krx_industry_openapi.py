"""Isolated manual KRX header-auth probe; sanitized metadata only, never raw rows."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import krx_industry_openapi as K  # noqa: E402

PLAN = 'research_specs/kr-industry-membership-foundation-v1/krx-openapi-feasibility-plan.json'
DOCS = 'data/kr-industry-membership-foundation-v1/krx-openapi-docs'
EXPECTED_PLAN_SHA256 = '7d011f12dddf226d85b31ab65f3dac5db91f29e03309e87d3ec0d38ea9e548f3'
OUTPUT = 'krx-openapi-source-metadata.json'
EVIDENCE = 'data/kr-industry-membership-foundation-v1/krx-openapi-probe'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def frozen_plan(root=ROOT):
    root = Path(root)
    raw = (root / PLAN).read_bytes()
    if sha(raw) != EXPECTED_PLAN_SHA256 or sha(raw) != (root / PLAN).with_suffix('.sha256').read_text().strip():
        raise ValueError('FEASIBILITY_PLAN_HASH_CHANGED')
    plan = K.validate_plan(json.loads(raw))
    manifest_raw = (root / DOCS / 'manifest.json').read_bytes()
    if sha(manifest_raw) != plan['officialDocumentationManifestSha256']:
        raise ValueError('OFFICIAL_DOCUMENTATION_CHANGED')
    manifest = json.loads(manifest_raw)
    if plan['services'] != manifest['services']:
        raise ValueError('DOCUMENTED_SERVICE_CONTRACT_CHANGED')
    for item in manifest['services'] + manifest['references']:
        path = item.get('sourceFile', item.get('path'))
        if Path(path).name != path or sha((root / DOCS / path).read_bytes()) != item['sha256']:
            raise ValueError('OFFICIAL_SOURCE_HASH_CHANGED')
    return plan, sha(raw)


def verify_evidence(root=ROOT):
    """Reproduce retained metadata identity; never invent a source result if not run."""
    root = Path(root)
    plan, digest = frozen_plan(root)
    path = root / EVIDENCE / OUTPUT
    if not path.exists():
        return {'status': 'NOT_EXECUTED', 'planSha256': digest, 'requestCount': 0,
                'historicalMembershipProven': False, 'admittedMembershipRows': 0,
                'reason': 'MANUAL_DISPATCH_REQUIRED; not a KRX access or source-absence finding'}
    raw = path.read_bytes()
    if sha(raw) != path.with_name(OUTPUT + '.sha256').read_text().strip():
        raise ValueError('SANITIZED_SOURCE_METADATA_CHANGED')
    value = json.loads(raw)
    if (value['planSha256'] != digest or value['requestCount'] != plan['maxRequests']
            or value['rawResponsesRetained'] or value['historicalMembershipProven']
            or value['admittedMembershipRows'] != 0):
        raise ValueError('UNPROVEN_MEMBERSHIP_OR_PLAN_CHANGED')
    expected = [(s['serviceId'], d) for s in plan['services'] for d in plan['dates']]
    if [(r['serviceId'], r['requestedHistoricalDate']) for r in value['records']] != expected:
        raise ValueError('FIXED_SERVICE_DATE_MATRIX_CHANGED')
    if any(r['historicalAsOfMembershipProven'] or r['membershipRowsAdmitted'] != 0 for r in value['records']):
        raise ValueError('REFERENCE_FEASIBILITY_CANNOT_PROMOTE_MEMBERSHIP')
    return {'status': 'SANITIZED_EVIDENCE_RETAINED', 'planSha256': digest,
            'metadataSha256': sha(raw), 'requestCount': value['requestCount'],
            'historicalMembershipProven': False, 'admittedMembershipRows': 0,
            'producerCommit': value['producerCommit'], 'runId': value['runId'], 'records': value['records']}


def execute(root=ROOT):
    plan, plan_hash = frozen_plan(root)
    if os.environ.get('GITHUB_EVENT_NAME') != 'workflow_dispatch' or os.environ.get('KRX_INDUSTRY_MANUAL_PROBE') != '1':
        raise ValueError('ISOLATED_MANUAL_WORKFLOW_REQUIRED')
    commit, run = os.environ.get('GITHUB_SHA', ''), os.environ.get('GITHUB_RUN_ID', '')
    if not re.fullmatch(r'[0-9a-f]{40}', commit) or not re.fullmatch(r'[0-9]+', run):
        raise ValueError('MANUAL_PRODUCER_IDENTITY_REQUIRED')
    key = os.environ.get('AUTH_KEY', '')
    K.ensure_safe_bytes(b'', key)
    opener = urllib.request.build_opener(K.NoRedirect())
    records = []
    for service in plan['services']:
        for date in plan['dates']:
            request = K.request_for(service['serviceId'], date, key)
            timestamp = datetime.now(timezone.utc).isoformat()
            try:
                with opener.open(request, timeout=plan['timeoutSeconds']) as response:
                    raw = response.read(plan['maximumResponseBytes'] + 1)
                    status = response.status
                    content_type = response.headers.get('Content-Type', '')
            except urllib.error.HTTPError as error:
                raw = error.read(plan['maximumResponseBytes'] + 1)
                status, content_type = error.code, error.headers.get('Content-Type', '')
            except Exception:
                # No exception repr: transport exceptions can contain request details.
                records.append({'serviceId': service['serviceId'], 'requestedHistoricalDate': date,
                                'parameters': {'basDd': date.replace('-', '')}, 'acquiredAt': timestamp,
                                'classification': 'NO_USABLE_RESPONSE', 'reason': 'TRANSPORT_FAILURE',
                                'historicalAsOfMembershipProven': False, 'membershipRowsAdmitted': 0})
                time.sleep(plan['minimumIntervalSeconds'])
                continue
            if len(raw) > plan['maximumResponseBytes']:
                # Do not hash a truncated response as if it were the exact full bytes.
                raise ValueError('RESPONSE_LIMIT_EXCEEDED_NO_EVIDENCE_PERSISTED')
            record = K.summarize_response(raw, status, content_type, service, date, key)
            record.update(serviceId=service['serviceId'], endpoint=service['endpoint'], acquiredAt=timestamp)
            records.append(record)
            time.sleep(plan['minimumIntervalSeconds'])
    result = {'contract': 'krx-industry-openapi-feasibility-v1', 'producerCommit': commit, 'runId': run,
              'planSha256': plan_hash, 'officialDocumentationManifestSha256': plan['officialDocumentationManifestSha256'],
              'requestCount': len(records), 'records': records, 'rawResponsesRetained': False,
              'historicalMembershipProven': False, 'admittedMembershipRows': 0,
              'decision': 'DATA_FOUNDATION_INSUFFICIENT'}
    raw_output = (json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()
    K.ensure_safe_bytes(raw_output, key)
    # Fixed filenames and exclusive creation prevent accidental overwrites or broad uploads.
    with Path(OUTPUT).open('xb') as stream:
        stream.write(raw_output)
    with Path(OUTPUT + '.sha256').open('x') as stream:
        stream.write(sha(raw_output) + '\n')
    print('Sanitized KRX reference-source metadata retained; no membership admitted.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-plan', action='store_true')
    args = parser.parse_args()
    if args.verify_plan:
        frozen_plan()
        print('Official documentation and frozen feasibility plan hashes reproduce offline.')
        return 0
    try:
        execute()
    except Exception:
        # Even unexpected exceptions must not print credential-bearing locals or bodies.
        print('Probe stopped safely; no source membership promoted.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
