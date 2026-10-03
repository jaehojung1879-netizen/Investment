"""Collect only frozen public annual receipt sections; reuse all retained v1 bytes."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
import base64
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.collect_kr_industry_membership_sources import Collector  # noqa: E402


def collect(plan_path, output):
    raw = plan_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != plan_path.with_suffix('.json.sha256').read_text().strip():
        raise ValueError('UNFROZEN_REQUEST_LIST')
    plan = json.loads(raw)
    if plan['historicalOutcomeComputed'] or plan['maxWorkers'] != 4:
        raise ValueError('INVALID_OUTCOME_FREE_PLAN')
    output.mkdir(parents=True, exist_ok=True)
    def fetch(target):
        collector = Collector(plan, 3)
        record = collector.receipt(target)
        objects = {}
        for response in record['responses']:
            body = response.pop('raw')
            if body is not None:
                objects[hashlib.sha256(body).hexdigest()] = base64.b64encode(body).decode()
        return record, objects, collector.calls
    with ThreadPoolExecutor(max_workers=plan['maxWorkers']) as pool:
        for batch in range((len(plan['targets']) + 24) // 25):
            archive = output / f'batch-{batch:03d}.json.gz'
            manifest_path = output / f'manifest-{batch:03d}.json'
            targets = plan['targets'][batch*25:(batch+1)*25]
            if manifest_path.exists():
                manifest = json.loads(manifest_path.read_text())
                if manifest['planSha256'] != hashlib.sha256(raw).hexdigest() or manifest['archiveSha256'] != hashlib.sha256(archive.read_bytes()).hexdigest():
                    raise ValueError('RETAINED_SOURCE_CHANGED')
                continue
            records, objects, calls = [], {}, 0
            for record, bodies, count in pool.map(fetch, targets):
                records.append(record)
                objects.update(bodies)
                calls += count
            archive.write_bytes(gzip.compress(json.dumps(objects, sort_keys=True, separators=(',', ':')).encode(), mtime=0))
            manifest = {'contract': 'KR_INDUSTRY_PUBLIC_DART_BATCH_V2', 'planSha256': hashlib.sha256(raw).hexdigest(), 'records': records, 'requests': calls, 'archive': archive.name, 'archiveSha256': hashlib.sha256(archive.read_bytes()).hexdigest(), 'historicalOutcomeComputed': False}
            manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
            print(f'batch {batch}: {len(records)} receipts, {calls} requests',flush=True)


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    collect(a.plan,a.output)
