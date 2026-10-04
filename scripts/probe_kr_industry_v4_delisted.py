"""One frozen request: the official KIND delisted-company register page (no retry, no redirect)."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import kr_industry_membership_v3 as V  # noqa: E402

SPEC = ROOT / 'research_specs/kr-industry-membership-foundation-v4/protocol.json'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def run(output):
    raw = SPEC.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SPEC.with_suffix('.json.sha256').read_text().strip():
        raise ValueError('UNFROZEN_V4_PROTOCOL')
    probe = json.loads(raw)['bounded_probe']
    url = probe['request'].split(' ', 1)[1]
    output.mkdir(parents=True, exist_ok=False)
    stamp = datetime.now(timezone.utc).isoformat()
    try:
        with build_opener(NoRedirect()).open(Request(url, headers={'User-Agent': 'Mozilla/5.0 (KR industry source feasibility)', 'Referer': 'https://kind.krx.co.kr/'}), timeout=20) as r:
            body, status, ctype = r.read(8000001), r.status, r.headers.get('Content-Type')
    except HTTPError as exc:
        body, status, ctype = exc.read(8000001), exc.code, exc.headers.get('Content-Type')
    sha = hashlib.sha256(body).hexdigest()
    (output / (sha + '.bin')).write_bytes(body)
    text, _ = V.decode(body)
    manifest = {'contract': 'KR_INDUSTRY_V4_DELISTED_REGISTER_PROBE', 'url': url, 'requestedAt': stamp, 'status': status, 'contentType': ctype,
                'bytes': len(body), 'sha256': sha, 'head': (text or '')[:300], 'protocolSha256': SPEC.with_suffix('.json.sha256').read_text().strip(),
                'historicalOutcomeComputed': False}
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + '\n')
    print(json.dumps({k: manifest[k] for k in ('status', 'bytes', 'contentType')}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    run(p.parse_args().output)
