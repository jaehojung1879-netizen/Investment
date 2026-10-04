"""Fetch only the frozen Top120-scoped KIND 업종변경 notice documents (resume-safe, no substitution)."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import kr_industry_membership_v3 as V  # noqa: E402

BASE = ROOT / 'research_specs/kr-industry-membership-foundation-v3'
VIEWER = 'https://kind.krx.co.kr/common/disclsviewer.do?method=search&acptno={r}&docno=&viewerhost=&viewerport='
DOC_URL = re.compile(r'https?://kind\.krx\.co\.kr/external/[^\'"\s<>)]+\.html?')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def frozen():
    out = {}
    for name in ('top120-notice-candidates.json', 'notice-document-protocol-rev5.json'):
        raw = (BASE / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != (BASE / (name + '.sha256')).read_text().strip():
            raise ValueError('UNFROZEN:' + name)
        out[name] = json.loads(raw)
    return out['top120-notice-candidates.json'], out['notice-document-protocol-rev5.json']


def fetch(opener, url, protocol):
    stamp = datetime.now(timezone.utc).isoformat()
    try:
        with opener.open(Request(url, headers={'User-Agent': 'Mozilla/5.0 (KR industry source feasibility)', 'Referer': 'https://kind.krx.co.kr/'}), timeout=protocol['timeoutSeconds']) as r:
            body, status = r.read(protocol['maxBodyBytes'] + 1), r.status
    except HTTPError as exc:
        body, status = exc.read(protocol['maxBodyBytes'] + 1), exc.code
    except Exception as exc:
        return {'url': url, 'requestedAt': stamp, 'status': None, 'error': type(exc).__name__}, None
    return {'url': url, 'requestedAt': stamp, 'status': status, 'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest(), 'error': None}, body


def run(output):
    cands, protocol = frozen()
    output.mkdir(parents=True, exist_ok=True)
    state_path = output / 'state.json'
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    opener, requests = build_opener(NoRedirect()), 0
    for cand in cands['candidates']:
        receipt = cand['receipt_no']
        if state.get(receipt, {}).get('status') == 'SERVED':
            continue
        record = {'receipt_no': receipt, 'company': cand['company'], 'candidate_securities': cand['candidate_securities'], 'responses': [], 'status': 'UNRESOLVED', 'reason': None}
        urls = [VIEWER.format(r=receipt)]
        seen = set()
        while urls and len(seen) < 4:
            url = urls.pop(0)
            if url in seen:
                continue
            seen.add(url)
            if requests >= protocol['maxRequests']:
                raise ValueError('CALL_BUDGET_EXCEEDED')
            requests += 1
            meta, body = fetch(opener, url, protocol)
            if body is not None:
                (output / (meta['sha256'] + '.bin')).write_bytes(body)
                if len(seen) == 1:
                    text, _ = V.decode(body)
                    urls.extend(sorted(set(DOC_URL.findall(text or '')))[:3])
                if meta['status'] == 200 and body[:400].find(b'Access Denied') < 0:
                    meta['isDocument'] = len(seen) > 1
            record['responses'].append(meta)
            time.sleep(1)
        docs = [m for m in record['responses'][1:] if m.get('status') == 200 and m.get('isDocument')]
        if docs:
            record.update(status='SERVED', reason=None)
        else:
            denied = any(m.get('status') == 403 for m in record['responses'])
            record['reason'] = 'EDGE_DENIAL' if denied else ('NO_DOCUMENT_URL_IN_VIEWER' if len(record['responses']) == 1 and record['responses'][0].get('status') == 200 else 'NOT_SERVED')
        state[receipt] = record
        state_path.write_text(json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2) + '\n')
        print(json.dumps({'receipt': receipt, 'status': record['status'], 'reason': record['reason'], 'n': len(record['responses'])}, ensure_ascii=False), flush=True)
    manifest = {'contract': 'KR_INDUSTRY_V3_NOTICE_DOCUMENT_RESULT', 'candidateSha256': (BASE / 'top120-notice-candidates.json.sha256').read_text().strip(),
                'protocolSha256': (BASE / 'notice-document-protocol-rev5.json.sha256').read_text().strip(), 'candidates': len(cands['candidates']),
                'served': sum(1 for v in state.values() if v['status'] == 'SERVED'), 'unresolved': sum(1 for v in state.values() if v['status'] != 'SERVED'),
                'requestsThisRun': requests, 'historicalOutcomeComputed': False}
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + '\n')
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    run(p.parse_args().output)
