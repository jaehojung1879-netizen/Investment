"""Three-date recovery into a NEW directory; never a production ledger writer.

Capture official bytes first, then replay through the ordinary collector. This
does not authorize a calendar exception, revise old prices, or calculate returns.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
from unittest.mock import patch

import requests

from pipeline import historical_store as store

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import collect_krx_daily_prices as collector  # noqa: E402

DATES = ('2026-09-15', '2026-09-16', '2026-10-01')
URL = 'https://data-dbg.krx.co.kr/svc/apis/sto/stk_bydd_trd'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def capture(destination):
    key = os.environ.get('KRX_API_KEY')
    if not key:
        raise ValueError('KRX_API_KEY_BINDING_REQUIRED')
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    records = []
    for day in DATES:
        response = requests.get(URL, params={'basDd': day.replace('-', '')},
                                headers={'AUTH_KEY': key}, timeout=30,
                                allow_redirects=False)
        raw = response.content
        if len(raw) > 8 * 1024 * 1024:
            raise ValueError('RESPONSE_SIZE_LIMIT')
        filename = day + '.json'
        (destination / filename).write_bytes(raw)
        records.append({'date': day, 'url': URL, 'basDd': day.replace('-', ''),
                        'file': filename, 'httpStatus': response.status_code,
                        'sha256': sha(raw), 'bytes': len(raw),
                        'capturedAtUtc': datetime.now(timezone.utc).isoformat()})
        # Save evidence even when a source refuses; never turn refusal into bars.
        (destination / 'manifest.json').write_text(json.dumps(records, indent=2) + '\n')
        response.raise_for_status()
    return records


def recover(original, responses, output):
    original, responses, output = map(Path, (original, responses, output))
    if output.exists() or original.resolve() == output.resolve():
        raise ValueError('NEW_ISOLATED_OUTPUT_REQUIRED')
    manifest = json.loads((responses / 'manifest.json').read_text())
    if (len(manifest) != len(DATES) or {r['date'] for r in manifest} != set(DATES)):
        raise ValueError('EXACT_THREE_DATE_SOURCE_MANIFEST_REQUIRED')
    payloads, source_receipts = {}, []
    for row in manifest:
        if (row['url'] != URL or row['httpStatus'] != 200
                or row['basDd'] != row['date'].replace('-', '')
                or row['file'] != row['date'] + '.json'):
            raise ValueError('OFFICIAL_SOURCE_REQUEST_MISMATCH')
        raw = (responses / row['file']).read_bytes()
        if sha(raw) != row['sha256'] or len(raw) != row['bytes']:
            raise ValueError('ORIGINAL_HTTP_BYTES_CHANGED')
        payloads[row['basDd']] = json.loads(raw)
        source_receipts.append(row)
    files = sorted(original.glob('krx-prices-*.jsonl.gz')) + [original / collector.DONE_NAME]
    before = {p.name: sha(p.read_bytes()) for p in files}
    old = [r for p in files if p.name.endswith('.gz') for r in store.read_jsonl(p)]
    if len({r['id'] for r in old}) != len(old):
        raise ValueError('ORIGINAL_DUPLICATE_RECORD_ID')
    # Preserve the original keep universe: do not introduce surviving replacements.
    keep = {r['ticker'] for r in old}
    output.mkdir(parents=True)
    for path in files:
        shutil.copyfile(path, output / path.name)
    with patch.object(collector, 'call', lambda base, endpoint, params, key: payloads[params['basDd']]):
        result = collector.collect(output, list(DATES), auth_key='OFFLINE_ORIGINAL_BYTES',
                                   base=URL, keep=keep, max_calls=3, max_minutes=2, pace=0)
    current = {r['id']: r for p in output.glob('krx-prices-*.jsonl.gz') for r in store.read_jsonl(p)}
    if any(current.get(r['id']) != r for r in old):
        raise ValueError('EXISTING_PRICE_RECORD_CHANGED')
    prior_ids = {r['id'] for r in old}
    added = [r for key, r in current.items() if key not in prior_ids]
    if any(r['date'] not in DATES for r in added):
        raise ValueError('RECOVERY_SCOPE_EXCEEDED')
    if before != {p.name: sha(p.read_bytes()) for p in files}:
        raise ValueError('ORIGINAL_INPUT_CHANGED')
    report = {'status': 'RECOVERED_ISOLATED' if result['remaining'] == 0 else 'SOURCE_BLOCKED',
              'originalPreservedSha256': before, 'sourceReceipts': source_receipts,
              'collector': result, 'addedRows': len(added),
              'byDate': {d: {'addedRows': sum(r['date'] == d for r in added),
                             'zeroVolumeRows': sum(r['date'] == d and r['volume'] == 0 for r in added)}
                         for d in DATES},
              'absentSecurityMeaning': 'UNKNOWN_NOT_AUTOMATIC_DELISTING_OR_ZERO',
              'productionWrite': False, 'outcomeExecutionAuthorized': False}
    (output / 'recovery-audit.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    cap = sub.add_parser('capture')
    cap.add_argument('destination', type=Path)
    rec = sub.add_parser('recover')
    for arg in ('original', 'responses', 'output'):
        rec.add_argument(arg, type=Path)
    args = parser.parse_args()
    result = capture(args.destination) if args.command == 'capture' else recover(args.original, args.responses, args.output)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
