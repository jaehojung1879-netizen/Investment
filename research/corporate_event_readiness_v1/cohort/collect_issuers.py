"""Collect every B / I001 filing 2013-2026 for issuers ever in the PIT KOSPI Top300.

The population is defined BEFORE any filing is read: the union of every
security that appears in a monthly PIT KOSPI Top300 snapshot (signal-history
``ledger/universe/kr``; delisted names included because each snapshot lists
the members of its own date). Securities map to DART issuers with the
repository's existing resolver (``dart_ownership_universe._resolve_security``:
exact stock code, else a unique exact name); unresolved securities are kept
with their reason, never dropped silently.

Per-issuer ``list.json`` takes the full date range in one result set, walked by
the existing fail-closed ``fetch_all_pages``.
"""
from __future__ import annotations

import argparse
import gzip
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from pipeline.dart_ownership_universe import _resolve_security, _unique_index, parse_corp_code_zip
from pipeline.kr_corporate_action_events import fetch_all_pages

from .collect_index import FIELDS, QUERIES
from .dart_client import DartClient
from .families import classify_title
from .identity import load_snapshots


def securities_from_snapshots(snapshots: dict[str, dict[str, str]]) -> list[dict]:
    seen: dict[str, dict] = {}
    for day in sorted(snapshots):
        for code, name in snapshots[day].items():
            row = seen.setdefault(code, {'stockCode': code, 'names': set(), 'firstSnapshot': day})
            row['names'].add(name)
            row['lastSnapshot'] = day
    return [{**v, 'names': sorted(v['names'])} for _, v in sorted(seen.items())]


def resolve_issuers(securities: list[dict], directory: list[dict]) -> tuple[dict, list[dict]]:
    by_stock = _unique_index(directory, 'stockCode')
    by_name = _unique_index(directory, 'corpName')
    issuers, unresolved = {}, []
    for sec in securities:
        row, provenance = _resolve_security(sec, by_stock, by_name)
        if row is None:
            unresolved.append({**sec, 'mapping': provenance})
            continue
        entry = issuers.setdefault(row['corpCode'], {'corpCode': row['corpCode'], 'corpName': row['corpName'],
                                                      'securities': []})
        entry['securities'].append({'stockCode': sec['stockCode'], 'names': sec['names'],
                                    'firstSnapshot': sec['firstSnapshot'], 'lastSnapshot': sec['lastSnapshot'],
                                    'method': provenance['method']})
    return issuers, unresolved


def collect_issuer(client: DartClient, corp_code: str, query: str, bgn: str, end: str) -> tuple[list[dict], dict]:
    pages = []

    def fetch_page(page_no: int) -> dict:
        payload, meta = client.get_json('list.json', {**QUERIES[query], 'corp_code': corp_code, 'bgn_de': bgn,
                                                      'end_de': end, 'page_no': page_no, 'page_count': 100})
        pages.append({'pageNo': page_no, 'sha256': meta['sha256']})
        return payload

    rows, summary = fetch_all_pages(fetch_page)
    return rows, {'corpCode': corp_code, 'query': query, 'totalCount': summary.get('totalCount'),
                  'pages': sorted(pages, key=lambda p: p['pageNo'])}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--cache', type=Path, required=True)
    p.add_argument('--universe', type=Path, required=True, help='directory of krx-universe-YYYY.jsonl.gz')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--start', default='20130101')
    p.add_argument('--end', default='20261031')
    p.add_argument('--workers', type=int, default=3)
    p.add_argument('--offline', action='store_true')
    args = p.parse_args(argv)
    client = DartClient(args.cache, offline=args.offline)
    snapshots = load_snapshots(args.universe)
    securities = securities_from_snapshots(snapshots)
    blob, corp_meta = client.get('corpCode.xml', {})
    directory = parse_corp_code_zip(blob)
    issuers, unresolved = resolve_issuers(securities, directory)
    tasks = [(c, q) for c in sorted(issuers) for q in QUERIES]
    relevant, manifest, scanned = {}, [], {q: 0 for q in QUERIES}
    with ThreadPoolExecutor(args.workers) as pool:
        futures = [pool.submit(collect_issuer, client, c, q, args.start, args.end) for c, q in tasks]
        for fut in as_completed(futures):
            rows, info = fut.result()
            manifest.append(info)
            scanned[info['query']] += len(rows)
            for row in rows:
                family = classify_title(row.get('report_nm', ''))
                if family is None:
                    continue
                keep = {k: row.get(k) for k in FIELDS}
                keep['family'] = family
                prior = relevant.get(keep['rcept_no'])
                if prior and {k: prior[k] for k in FIELDS} != {k: keep[k] for k in FIELDS}:
                    raise RuntimeError('INDEX_ROW_DISAGREES_ACROSS_QUERIES:' + keep['rcept_no'])
                relevant[keep['rcept_no']] = keep
    args.out.mkdir(parents=True, exist_ok=True)
    rows = [relevant[k] for k in sorted(relevant)]
    payload = ''.join(json.dumps(r, ensure_ascii=False, sort_keys=True) + '\n' for r in rows)
    (args.out / 'issuer-index-rows-v1.jsonl.gz').write_bytes(gzip.compress(payload.encode(), 9, mtime=0))
    manifest.sort(key=lambda m: (m['corpCode'], m['query']))
    (args.out / 'issuer-universe-v1.json').write_text(json.dumps({
        'population': 'UNION_OF_PIT_KOSPI_TOP300_MONTHLY_SNAPSHOTS',
        'snapshotDates': [min(snapshots), max(snapshots)], 'snapshotCount': len(snapshots),
        'securities': len(securities), 'resolvedIssuers': len(issuers),
        'unresolvedSecurities': unresolved,
        'corpCodeDirectory': {'sha256': corp_meta['sha256'], 'fetchedAt': corp_meta['fetchedAt'],
                              'rows': len(directory)},
        'issuers': [issuers[k] for k in sorted(issuers)],
    }, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    (args.out / 'issuer-index-manifest-v1.json').write_text(json.dumps({
        'source': 'OpenDART list.json per corp_code', 'bgn_de': args.start, 'end_de': args.end,
        'queries': QUERIES, 'resultSets': manifest, 'rowsScannedByQuery': scanned,
        'relevantRows': len(rows), 'apiCalls': client.calls, 'cacheHits': client.cache_hits,
    }, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps({'issuers': len(issuers), 'unresolved': len(unresolved), 'relevantRows': len(rows),
                      'scanned': scanned, 'calls': client.calls}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
