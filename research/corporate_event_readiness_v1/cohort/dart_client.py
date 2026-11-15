"""Minimal OpenDART client with a content-addressed raw-response cache.

* The API key is read from ``DART_API_KEY`` and is never written anywhere: the
  cache key and every receipt use the request parameters WITHOUT the key.
* Every raw response body is stored gzip-compressed under its SHA256 so a later
  rebuild can prove it read exactly the bytes the collection received.
* Status 020 (request limit) and transport errors are retried with backoff;
  any other non-000/013 status is returned to the caller unchanged, never
  converted into "no data".
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = 'https://opendart.fss.or.kr/api/'
RETRY_STATUSES = {'020'}
OK_STATUSES = {'000', '013'}
# document.xml answers an absent original with XML status 014; it is an explicit
# source answer (cached and counted), never a transport error and never a body.
XML_ANSWER_STATUSES = {'014'}


class DartRefusal(RuntimeError):
    """A DART status that is neither data nor an explicit no-data answer."""


def request_id(endpoint: str, params: dict) -> str:
    clean = {k: params[k] for k in sorted(params) if k != 'crtfc_key'}
    return endpoint + '?' + urllib.parse.urlencode(clean)


class DartClient:
    def __init__(self, cache: Path, *, key: str | None = None, pause: float = 0.0,
                 max_attempts: int = 6, offline: bool = False):
        self.cache = Path(cache)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.key = key if key is not None else os.environ.get('DART_API_KEY', '')
        self.pause = pause
        self.max_attempts = max_attempts
        self.offline = offline
        self.calls = 0
        self.cache_hits = 0

    def get(self, endpoint: str, params: dict) -> tuple[bytes, dict]:
        rid = request_id(endpoint, params)
        digest = hashlib.sha256(rid.encode()).hexdigest()
        meta_path = self.cache / 'req' / (digest + '.json')
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding='utf-8'))
            body = gzip.decompress((self.cache / 'raw' / (meta['sha256'] + '.gz')).read_bytes())
            if hashlib.sha256(body).hexdigest() != meta['sha256']:
                raise DartRefusal('CACHE_BODY_HASH_MISMATCH:' + rid)
            self.cache_hits += 1
            return body, meta
        if self.offline:
            raise DartRefusal('OFFLINE_CACHE_MISS:' + rid)
        if not self.key:
            raise DartRefusal('DART_API_KEY_ABSENT')
        url = BASE + endpoint + '?' + urllib.parse.urlencode({**params, 'crtfc_key': self.key})
        delay = 2.0
        for attempt in range(1, self.max_attempts + 1):
            try:
                with urllib.request.urlopen(url, timeout=60) as response:
                    body = response.read()
                    ctype = response.headers.get('Content-Type', '')
                self.calls += 1
            except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
                if attempt == self.max_attempts:
                    raise DartRefusal(f'TRANSPORT:{type(exc).__name__}:{rid}') from exc
                time.sleep(delay)
                delay *= 2
                continue
            status = None
            xml_status = re.search(rb'<status>(\d{3})</status>', body[:400]) if body[:5] == b'<?xml' else None
            if xml_status:
                status = xml_status.group(1).decode()
            elif body[:1] == b'{':
                try:
                    status = str(json.loads(body).get('status'))
                except ValueError:
                    status = 'UNPARSEABLE_JSON'
            if status in RETRY_STATUSES and attempt < self.max_attempts:
                time.sleep(delay)
                delay *= 2
                continue
            break
        sha = hashlib.sha256(body).hexdigest()
        (self.cache / 'raw').mkdir(exist_ok=True)
        (self.cache / 'req').mkdir(exist_ok=True)
        raw_path = self.cache / 'raw' / (sha + '.gz')
        if not raw_path.exists():
            raw_path.write_bytes(gzip.compress(body, mtime=0))
        meta = {'request': rid, 'sha256': sha, 'bytes': len(body), 'contentType': ctype,
                'status': status, 'fetchedAt': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
        # Only answers that are data or an explicit no-data are cached; a refusal is
        # never remembered as if it were the source's answer.
        if status in OK_STATUSES | XML_ANSWER_STATUSES or (status is None and body[:2] == b'PK'):
            meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding='utf-8')
        if self.pause:
            time.sleep(self.pause)
        return body, meta

    def get_json(self, endpoint: str, params: dict) -> tuple[dict, dict]:
        body, meta = self.get(endpoint, params)
        payload = json.loads(body)
        status = str(payload.get('status'))
        if status not in OK_STATUSES:
            raise DartRefusal(f'STATUS_{status}:{payload.get("message")}:{meta["request"]}')
        return payload, meta
