"""Collect the market-wide DART filing index for 2013-2026 (outcome-free).

Queries every quarterly window for:
  * pblntf_ty=B        (major-matters reports: buybacks, disposals, trusts, rights, CB/EB/BW)
  * pblntf_detail_ty=I001 (KRX timely disclosures: share cancellation, supply contracts)
WITHOUT a corp_cls filter: DART reports today's market class, so filtering by
it would drop companies that were listed then and are delisted now.

Pagination is walked by the repository's existing fail-closed
``pipeline.kr_corporate_action_events.fetch_all_pages``.
"""
from __future__ import annotations

import argparse
import gzip
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path

from pipeline.kr_corporate_action_events import fetch_all_pages

from .dart_client import DartClient
from .families import classify_title

QUERIES = {'B': {'pblntf_ty': 'B'}, 'I001': {'pblntf_detail_ty': 'I001'}}
FIELDS = ('rcept_no', 'rcept_dt', 'corp_code', 'corp_name', 'stock_code', 'corp_cls',
          'report_nm', 'rm', 'flr_nm')


def windows(start: date, end: date) -> list[tuple[str, str]]:
    out, cur = [], start
    while cur <= end:
        q_end_month = ((cur.month - 1) // 3 + 1) * 3
        nxt = date(cur.year + (q_end_month == 12), 1 if q_end_month == 12 else q_end_month + 1, 1)
        last = min(nxt - timedelta(days=1), end)
        out.append((cur.strftime('%Y%m%d'), last.strftime('%Y%m%d')))
        cur = nxt
    return out


def collect_window(client: DartClient, query: str, bgn: str, end: str) -> tuple[list[dict], dict]:
    pages = []

    def fetch_page(page_no: int) -> dict:
        payload, meta = client.get_json('list.json', {**QUERIES[query], 'bgn_de': bgn, 'end_de': end,
                                                      'page_no': page_no, 'page_count': 100})
        pages.append({'pageNo': page_no, 'sha256': meta['sha256'], 'bytes': meta['bytes']})
        return payload

    rows, summary = fetch_all_pages(fetch_page)
    return rows, {'query': query, 'bgn_de': bgn, 'end_de': end, 'totalCount': summary.get('totalCount'),
                  'rowsFetched': summary.get('rowsFetched'), 'pages': sorted(pages, key=lambda p: p['pageNo'])}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--cache', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--start', default='2013-01-01')
    p.add_argument('--end', default='2026-10-31')
    p.add_argument('--workers', type=int, default=4)
    p.add_argument('--offline', action='store_true')
    args = p.parse_args(argv)
    client = DartClient(args.cache, offline=args.offline)
    tasks = [(q, b, e) for q in QUERIES for b, e in windows(date.fromisoformat(args.start),
                                                              date.fromisoformat(args.end))]
    relevant, manifest, counts = {}, [], {}
    with ThreadPoolExecutor(args.workers) as pool:
        futures = {pool.submit(collect_window, client, *t): t for t in tasks}
        for fut in as_completed(futures):
            rows, window = fut.result()
            manifest.append(window)
            for row in rows:
                counts[window['query']] = counts.get(window['query'], 0) + 1
                family = classify_title(row.get('report_nm', ''))
                if family is None:
                    continue
                keep = {k: row.get(k) for k in FIELDS}
                keep['family'] = family
                keep['indexQuery'] = window['query']
                prior = relevant.get(keep['rcept_no'])
                if prior and {k: prior[k] for k in FIELDS} != {k: keep[k] for k in FIELDS}:
                    raise RuntimeError('INDEX_ROW_DISAGREES_ACROSS_QUERIES:' + keep['rcept_no'])
                relevant[keep['rcept_no']] = keep
    args.out.mkdir(parents=True, exist_ok=True)
    manifest.sort(key=lambda w: (w['query'], w['bgn_de']))
    rows = [relevant[k] for k in sorted(relevant)]
    payload = ''.join(json.dumps(r, ensure_ascii=False, sort_keys=True) + '\n' for r in rows)
    # mtime=0 keeps the container byte-deterministic across rebuilds.
    (args.out / 'index-rows-v1.jsonl.gz').write_bytes(gzip.compress(payload.encode(), 9, mtime=0))
    (args.out / 'index-manifest-v1.json').write_text(json.dumps({
        'source': 'OpenDART list.json', 'start': args.start, 'end': args.end,
        'queries': QUERIES, 'corpClsFilter': None,
        'windows': manifest, 'rowsScannedByQuery': counts, 'relevantRows': len(rows),
        'apiCalls': client.calls, 'cacheHits': client.cache_hits,
    }, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps({'relevantRows': len(rows), 'scanned': counts, 'calls': client.calls,
                      'cacheHits': client.cache_hits}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
