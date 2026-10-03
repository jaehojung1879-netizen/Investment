"""Public dated DART classification evidence only, in immutable bounded slices."""
from __future__ import annotations
import argparse
import base64
import gzip
import hashlib
import json
from pathlib import Path
import re
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def nodes(raw, receipt):
    result = []
    for block in re.split(r'var node\d+ = \{\};', raw.decode('utf-8', 'strict'))[1:]:
        node = dict(re.findall(r'node\d+\[\'(text|rcpNo|dcmNo|eleId|offset|length|dtd)\'\]\s*=\s*"([^"]*)"', block))
        if len(node) == 7 and node['rcpNo'] == receipt:
            result.append(node)
    return result


def classification_markers(raw):
    plain = re.sub(r'<[^>]*>', ' ', raw.decode('utf-8', errors='replace'))
    markers = [{'offset': m.start(), 'text': plain[max(0, m.start()-100):m.start()+700]}
               for m in re.finditer(r'한국.{0,8}산업분류|업종.{0,6}코드|업종.{0,8}CODE|표준산업|산업분류코드', plain, re.I)]
    codes = sorted(set(re.findall(r'\b[A-U]\s?\d{2,5}\b', plain)))
    return markers, codes


class Collector:
    def __init__(self, plan, budget):
        self.plan, self.budget, self.calls = plan, budget, 0

    def request(self, url):
        if self.calls >= self.budget:
            raise ValueError('CALL_BUDGET_EXCEEDED')
        self.calls += 1
        try:
            with urlopen(Request(url, headers={'User-Agent': 'Mozilla/5.0 (KR industry source research)'}),
                         timeout=self.plan['timeoutSeconds']) as response:
                raw, status = response.read(self.plan['maxBodyBytes'] + 1), response.status
        except HTTPError as exc:
            raw, status = exc.read(self.plan['maxBodyBytes'] + 1), exc.code
        except Exception as exc:
            return {'url': url, 'status': None, 'error': type(exc).__name__, 'raw': None}
        if len(raw) > self.plan['maxBodyBytes']:
            return {'url': url, 'status': status, 'error': 'BODY_BUDGET_EXCEEDED', 'raw': None}
        return {'url': url, 'status': status, 'error': None, 'sha256': sha(raw), 'raw': raw}

    def receipt(self, target):
        receipt = target['receiptNos'][0]
        if not re.fullmatch(r'\d{14}', receipt):
            raise ValueError('EXACT_RECEIPT_REQUIRED')
        result = {'target': target, 'responses': [], 'sections': []}
        main = self.request('https://dart.fss.or.kr/dsaf001/main.do?rcpNo=' + receipt)
        result['responses'].append(main)
        if main['status'] != 200 or main['raw'] is None:
            return result
        try:
            available = nodes(main['raw'], receipt)
        except UnicodeError:
            return result
        for label, tokens in [('company_overview', ['1.회사의개요', 'I.회사의개요', 'Ⅰ.회사의개요']),
                              ('business_overview', ['1.사업의개요', 'II.사업의내용', 'Ⅱ.사업의내용'])]:
            choices = [n for n in available if ''.join(n['text'].split()) in tokens]
            if not choices:
                continue
            node = min(choices, key=lambda n: int(n['length']))
            response = self.request('https://dart.fss.or.kr/report/viewer.do?' + urlencode({k: node[k] for k in ['rcpNo', 'dcmNo', 'eleId', 'offset', 'length', 'dtd']}))
            response['section'] = label
            result['responses'].append(response)
            if response['status'] == 200 and response['raw']:
                markers, codes = classification_markers(response['raw'])
                result['sections'].append({'section': label, 'node': node, 'sha256': response['sha256'],
                                          'classificationMarkers': markers, 'explicitCodeCandidates': codes})
        return result


def collect(plan_path, output, batch):
    plan_raw = plan_path.read_bytes()
    plan = json.loads(plan_raw)
    if plan['contract'] != 'KR_INDUSTRY_SOURCE_ACQUISITION_PLAN_V1' or plan['historicalOutcomeComputed']:
        raise ValueError('OUTCOME_FREE_PLAN_REQUIRED')
    if not 0 <= batch <= 20:
        raise ValueError('INVALID_FIXED_BATCH')
    targets = plan['targets'][batch * 20:(batch + 1) * 20]
    output.mkdir(parents=True, exist_ok=False)
    collector, objects, records = Collector(plan, len(targets) * 3), {}, []
    # One worker per slice; Actions max-parallel=4 preserves the frozen global limit.
    for target in targets:
        record = collector.receipt(target)
        for response in record['responses']:
            raw = response.pop('raw')
            if raw is not None:
                objects.setdefault(sha(raw), base64.b64encode(raw).decode())
        records.append(record)
        print(f"batch {batch}: {len(records)}/{len(targets)}", flush=True)
    archive = output / f'batch-{batch:03d}.json.gz'
    archive.write_bytes(gzip.compress(json.dumps(objects, sort_keys=True, separators=(',', ':')).encode(), mtime=0))
    manifest = {'contract': 'KR_INDUSTRY_PUBLIC_DART_BATCH_V1', 'batch': batch,
                'acquisitionPlanSha256': sha(plan_raw), 'records': records, 'requests': collector.calls,
                'archive': archive.name, 'archiveSha256': sha(archive.read_bytes()),
                'historicalOutcomeComputed': False}
    (output / f'manifest-{batch:03d}.json').write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + '\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--batch', type=int, required=True)
    args = p.parse_args()
    collect(args.plan, args.output, args.batch)
