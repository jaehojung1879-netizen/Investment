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
from urllib.parse import urlencode, urljoin
from urllib.request import HTTPRedirectHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import kr_industry_membership_v3 as V  # noqa: E402

BASE = ROOT / 'research_specs/kr-industry-membership-foundation-v3'
VIEWER = 'https://kind.krx.co.kr/common/disclsviewer.do?method=search&acptno={r}&docno=&viewerhost=&viewerport='
DOC_PATH = re.compile(r'(?:https?://kind\.krx\.co\.kr)?/[A-Za-z0-9_./-]+\.html?')
DOCNO = re.compile(r"<option value=['\"](\d{10,}\|[YN])['\"]")
POST_URL = 'https://kind.krx.co.kr/common/disclsviewer.do'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def frozen():
    out = {}
    for name in ('top120-notice-candidates.json', 'notice-document-protocol-rev6.json'):
        raw = (BASE / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != (BASE / (name + '.sha256')).read_text().strip():
            raise ValueError('UNFROZEN:' + name)
        out[name] = json.loads(raw)
    return out['top120-notice-candidates.json'], out['notice-document-protocol-rev6.json']


def fetch(opener, url, protocol, form=None):
    stamp = datetime.now(timezone.utc).isoformat()
    data = urlencode(form).encode() if form else None
    try:
        with opener.open(Request(url, data=data, method='POST' if form else 'GET', headers={'User-Agent': 'Mozilla/5.0 (KR industry source feasibility)', 'Referer': 'https://kind.krx.co.kr/'}), timeout=protocol['timeoutSeconds']) as r:
            body, status = r.read(protocol['maxBodyBytes'] + 1), r.status
    except HTTPError as exc:
        body, status = exc.read(protocol['maxBodyBytes'] + 1), exc.code
    except Exception as exc:
        return {'url': url, 'form': form, 'requestedAt': stamp, 'status': None, 'error': type(exc).__name__}, None
    return {'url': url, 'form': form, 'requestedAt': stamp, 'status': status, 'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest(), 'error': None}, body


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
        record['responses'] = []
        prior = state.get(receipt, {}).get('responses', [])
        viewer = next((m for m in prior if m.get('url') == VIEWER.format(r=receipt) and m.get('status') == 200 and (output / (m['sha256'] + '.bin')).exists()), None)
        if viewer is None:
            requests += 1
            viewer, body = fetch(opener, VIEWER.format(r=receipt), protocol)
            if body is not None:
                (output / (viewer['sha256'] + '.bin')).write_bytes(body)
            time.sleep(1)
        record['responses'].append(viewer)
        text = V.decode((output / (viewer['sha256'] + '.bin')).read_bytes())[0] if viewer.get('sha256') else None
        doc_nos = sorted(set(DOCNO.findall(text or '')))
        if not doc_nos:
            record['reason'] = 'NO_DOCNO_IN_VIEWER' if viewer.get('status') == 200 else 'EDGE_DENIAL_OR_ERROR'
        for doc_no in doc_nos[:2]:
            requests += 1
            meta, body = fetch(opener, POST_URL, protocol, {'method': 'searchContents', 'docNo': doc_no.split('|')[0]})
            meta['stage'] = 'searchContents'
            if body is not None:
                (output / (meta['sha256'] + '.bin')).write_bytes(body)
            record['responses'].append(meta)
            time.sleep(1)
            if body is None or meta['status'] != 200:
                continue
            paths = sorted(set(DOC_PATH.findall(V.decode(body)[0] or '')))[:3]
            meta['namedPaths'] = paths
            for path in paths:
                requests += 1
                doc_meta, doc_body = fetch(opener, urljoin('https://kind.krx.co.kr/', path), protocol)
                doc_meta['stage'] = 'document'
                if doc_body is not None:
                    (output / (doc_meta['sha256'] + '.bin')).write_bytes(doc_body)
                record['responses'].append(doc_meta)
                time.sleep(1)
        if any(m.get('stage') == 'document' and m.get('status') == 200 for m in record['responses']):
            record.update(status='SERVED', reason=None)
        elif record['reason'] is None:
            record['reason'] = 'NO_DOCUMENT_PATH_IN_SEARCHCONTENTS' if any(m.get('stage') == 'searchContents' for m in record['responses']) else 'NOT_SERVED'
        state[receipt] = record
        state_path.write_text(json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2) + '\n')
        print(json.dumps({'receipt': receipt, 'status': record['status'], 'reason': record['reason'], 'n': len(record['responses']), 'paths': [m.get('namedPaths') for m in record['responses'] if m.get('stage') == 'searchContents']}, ensure_ascii=False), flush=True)
    manifest = {'contract': 'KR_INDUSTRY_V3_NOTICE_DOCUMENT_RESULT', 'candidateSha256': (BASE / 'top120-notice-candidates.json.sha256').read_text().strip(),
                'protocolSha256': (BASE / 'notice-document-protocol-rev6.json.sha256').read_text().strip(), 'candidates': len(cands['candidates']),
                'served': sum(1 for v in state.values() if v['status'] == 'SERVED'), 'unresolved': sum(1 for v in state.values() if v['status'] != 'SERVED'),
                'requestsThisRun': requests, 'historicalOutcomeComputed': False}
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + '\n')
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    run(p.parse_args().output)
