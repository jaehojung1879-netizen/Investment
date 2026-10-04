"""Frozen rev3: windowed KIND 업종변경 notice LISTING only (no document fetch, no labels)."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import kr_industry_membership_v3 as V  # noqa: E402

SPEC = ROOT / 'research_specs/kr-industry-membership-foundation-v3/event-listing-rev3.json'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def load_frozen():
    raw = SPEC.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SPEC.with_suffix('.json.sha256').read_text().strip():
        raise ValueError('UNFROZEN_V3_EVENT_LISTING')
    return json.loads(raw)


def run(output):
    plan = load_frozen()
    output.mkdir(parents=True, exist_ok=False)
    opener, requests, results, hits = build_opener(NoRedirect()), 0, [], []
    for start, end in plan['windows']:
        for page in range(1, plan['maxPagesPerWindow'] + 1):
            if requests >= plan['maxRequests']:
                raise ValueError('CALL_BUDGET_EXCEEDED')
            requests += 1
            form = dict(plan['query'], pageIndex=str(page), reportNm='업종변경', fromDate=start, toDate=end)
            req = Request(plan['url'], data=urlencode(form).encode(), method='POST', headers={
                'User-Agent': 'Mozilla/5.0 (KR industry source feasibility)', 'Referer': 'https://kind.krx.co.kr/',
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'})
            try:
                with opener.open(req, timeout=plan['timeoutSeconds']) as r:
                    body, status = r.read(plan['maxBodyBytes'] + 1), r.status
            except HTTPError as exc:
                body, status = exc.read(plan['maxBodyBytes'] + 1), exc.code
            except Exception as exc:
                results.append({'window': [start, end], 'page': page, 'status': None, 'error': type(exc).__name__})
                break
            sha = hashlib.sha256(body).hexdigest()
            (output / (sha + '.bin')).write_bytes(body)
            parsed = V.parse_kind_listing(body)
            results.append({'window': [start, end], 'page': page, 'status': status, 'bytes': len(body), 'sha256': sha,
                            'parse': parsed['status'], 'rows': len(parsed['rows']), 'alert': parsed.get('alert')})
            print(json.dumps(results[-1], ensure_ascii=False), flush=True)
            hits.extend(parsed['rows'])
            time.sleep(1)
            if parsed['status'] == 'ACCESS_DENIED' and plan['stopOnAccessDenied']:
                break
            if parsed['status'] != 'PARSED' or len(parsed['rows']) < int(plan['query']['currentPageSize']):
                break
    manifest = {'contract': 'KR_INDUSTRY_V3_EVENT_LISTING_RESULT', 'planSha256': SPEC.with_suffix('.json.sha256').read_text().strip(),
                'requests': requests, 'results': results, 'listedRows': len(hits), 'uniqueReceipts': len({h['receipt_no'] for h in hits}),
                'rows': hits, 'historicalOutcomeComputed': False, 'labelsAssigned': False}
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + '\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    run(p.parse_args().output)
