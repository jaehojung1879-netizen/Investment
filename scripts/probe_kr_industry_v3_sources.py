"""Run only the frozen v3 request list (4 requests, no retry, no redirect) and retain raw bytes."""
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

SPEC = ROOT / 'research_specs/kr-industry-membership-foundation-v3/protocol.json'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def load_frozen():
    raw = SPEC.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SPEC.with_suffix('.json.sha256').read_text().strip():
        raise ValueError('UNFROZEN_V3_PROTOCOL')
    return json.loads(raw)['probe']


def run(output):
    plan = load_frozen()
    output.mkdir(parents=True, exist_ok=False)
    opener, results = build_opener(NoRedirect()), []
    for number, req in enumerate(plan['requests']):
        if number >= plan['maxRequests']:
            raise ValueError('CALL_BUDGET_EXCEEDED')
        data = urlencode(req['form']).encode() if req.get('form') else None
        headers = {'User-Agent': 'Mozilla/5.0 (KR industry source feasibility)', 'Referer': 'https://data.krx.co.kr/' if 'krx.co.kr' in req['url'] else 'https://kind.krx.co.kr/'}
        if data:
            headers['Content-Type'] = 'application/x-www-form-urlencoded; charset=UTF-8'
        entry = {'id': req['id'], 'method': req['method'], 'url': req['url'], 'form': req.get('form')}
        try:
            with opener.open(Request(req['url'], data=data, headers=headers, method=req['method']), timeout=plan['timeoutSeconds']) as r:
                body, status, ctype = r.read(plan['maxBodyBytes'] + 1), r.status, r.headers.get('Content-Type')
        except HTTPError as exc:
            body, status, ctype = exc.read(plan['maxBodyBytes'] + 1), exc.code, exc.headers.get('Content-Type')
        except Exception as exc:
            entry.update(status=None, error=type(exc).__name__)
            results.append(entry)
            continue
        entry.update(status=status, contentType=ctype, bytes=len(body), sha256=hashlib.sha256(body).hexdigest(), error=None)
        (output / (entry['sha256'] + '.bin')).write_bytes(body)
        if req['id'] == 'kind-corp-list-current' and status == 200:
            parsed = V.parse_current_state(body, time.strftime('%Y-%m-%d', time.gmtime()))
            entry['parse'] = {k: parsed[k] for k in ('status', 'reason', 'columns')}
            entry['parse']['rows'] = len(parsed['rows'])
            entry['parse']['rowsWithIndustry'] = sum(1 for r in parsed['rows'] if r['industry_label'])
        text, _ = V.decode(body)
        entry['head'] = (text or '')[:300]
        results.append(entry)
        print(json.dumps({k: entry.get(k) for k in ('id', 'status', 'bytes', 'parse')}, ensure_ascii=False), flush=True)
        time.sleep(1)
    manifest = {'contract': 'KR_INDUSTRY_V3_PROBE_RESULT', 'protocolSha256': SPEC.with_suffix('.json.sha256').read_text().strip(),
                'results': results, 'historicalOutcomeComputed': False, 'historicalAdmitted': False}
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + '\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    run(p.parse_args().output)
