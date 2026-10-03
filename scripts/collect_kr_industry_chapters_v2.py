"""Collect only the frozen classification-chapter supplements (68 requests, frozen before acquisition)."""
from __future__ import annotations
import argparse
import base64
import gzip
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.collect_kr_industry_membership_sources import Collector  # noqa: E402

PLAN = ROOT / 'research_specs/kr-industry-membership-foundation-v2/classification-chapters.json'


def collect(output):
    raw = PLAN.read_bytes()
    if hashlib.sha256(raw).hexdigest() != PLAN.with_suffix('.json.sha256').read_text().strip():
        raise ValueError('UNFROZEN_CHAPTER_REQUEST_LIST')
    plan = json.loads(raw)
    if plan['historicalOutcomeComputed'] or plan['maxWorkers'] != 4 or len(plan['targets']) > plan['maxCalls']:
        raise ValueError('INVALID_OUTCOME_FREE_PLAN')
    output.mkdir(parents=True, exist_ok=False)
    collector, objects, records = Collector(plan, plan['maxCalls']), {}, []
    for target in plan['targets']:
        node = target['node']
        expected = 'https://dart.fss.or.kr/report/viewer.do?' + urlencode({k: node[k] for k in ['rcpNo', 'dcmNo', 'eleId', 'offset', 'length', 'dtd']})
        if target['url'] != expected or node['rcpNo'] != target['target']['receiptNos'][0]:
            raise ValueError('FROZEN_URL_DISAGREES_WITH_NODE')
        response = collector.request(target['url'])
        body = response.pop('raw')
        if body is not None:
            objects[hashlib.sha256(body).hexdigest()] = base64.b64encode(body).decode()
        records.append({'target': target['target'], 'node': node, 'mainResponse': target['mainResponse'], 'response': response})
        print(f'classification chapter {len(records)}/{len(plan["targets"])} status={response["status"]}', flush=True)
    archive = output / 'chapters.json.gz'
    archive.write_bytes(gzip.compress(json.dumps(objects, sort_keys=True, separators=(',', ':')).encode(), mtime=0))
    manifest = {'contract': 'KR_INDUSTRY_CLASSIFICATION_CHAPTERS_RESULT_V2', 'planSha256': hashlib.sha256(raw).hexdigest(),
                'records': records, 'requests': collector.calls, 'archive': archive.name,
                'archiveSha256': hashlib.sha256(archive.read_bytes()).hexdigest(), 'historicalOutcomeComputed': False}
    (output / 'manifest-chapters.json').write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + '\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    collect(p.parse_args().output)
