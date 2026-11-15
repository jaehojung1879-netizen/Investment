"""Annual total-equity facts (자본총계) for the cohort issuers, for the book-to-market match check.

OpenDART ``fnlttSinglAcnt`` (annual report, reprt_code 11011), one call per issuer-year, FY2012-2025.
Stores only what the match needs: statement basis (consolidated preferred), 자본총계 as stated, the
serving filing's receipt number (its date is the availability date -- an amendment served in place of
an original makes it LATER, i.e. conservative) and the response body hash. A status that is not
000/013 is kept as the source's own answer; 013 (no data) is recorded as absence, never as zero.
Total equity includes non-controlling interests; the parent-attributable figure is not in this endpoint,
and the match uses the same definition for the event firm and its peers. No price is read here.
"""
from __future__ import annotations

import argparse
import gzip
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from research.corporate_event_readiness_v1.cohort.dart_client import DartClient

UNIVERSE = Path(__file__).resolve().parents[1] / 'corporate_event_readiness_v1/cohort/data/issuer-universe-v1.json'
YEARS = range(2012, 2026)


def amount(text: str | None) -> int | None:
    if text is None:
        return None
    t = text.replace(',', '').strip()
    return int(t) if t.lstrip('-').isdigit() else None


def pick(rows: list[dict]) -> dict | None:
    for fs in ('CFS', 'OFS'):        # consolidated preferred; which one answered is recorded
        hit = [r for r in rows if r.get('fs_div') == fs and r.get('sj_div') == 'BS' and r.get('account_nm') == '자본총계']
        if len(hit) == 1:
            r = hit[0]
            return {'basis': fs, 'totalEquityKrw': amount(r.get('thstrm_amount')), 'rcept_no': r.get('rcept_no')}
        if len(hit) > 1:
            return {'basis': fs, 'totalEquityKrw': None, 'rcept_no': None, 'problem': 'AMBIGUOUS_ACCOUNT'}
    return None


def one(client: DartClient, corp: str, year: int) -> dict:
    body, info = client.get('fnlttSinglAcnt.json', {'corp_code': corp, 'bsns_year': str(year), 'reprt_code': '11011'})
    d = json.loads(body)
    row = {'corp_code': corp, 'fiscalYear': year, 'status': d.get('status'),
           'bodySha256': info.get('sha256') or info.get('bodySha256')}
    if d.get('status') == '000':
        got = pick(d.get('list', []))
        row.update(got or {'problem': 'NO_TOTAL_EQUITY_ROW'})
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--cache', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--workers', type=int, default=4)
    args = ap.parse_args()
    corps = [i['corpCode'] for i in json.loads(UNIVERSE.read_text(encoding='utf-8'))['issuers']]
    client = DartClient(args.cache)
    jobs = [(c, y) for c in corps for y in YEARS]
    with ThreadPoolExecutor(args.workers) as pool:
        rows = list(pool.map(lambda j: one(client, *j), jobs))
    rows.sort(key=lambda r: (r['corp_code'], r['fiscalYear']))
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / 'equity-facts-v1.jsonl.gz').write_bytes(gzip.compress(
        ''.join(json.dumps(r, ensure_ascii=False, sort_keys=True) + '\n' for r in rows).encode(), 9, mtime=0))
    summary = {'issuers': len(corps), 'issuerYears': len(rows), 'apiCalls': client.calls,
               'status': dict(Counter(r['status'] for r in rows)),
               'withEquity': sum(1 for r in rows if r.get('totalEquityKrw') is not None),
               'basis': dict(Counter(r.get('basis') for r in rows if r.get('totalEquityKrw') is not None)),
               'problems': dict(Counter(r.get('problem') for r in rows if r.get('problem')))}
    (args.out / 'equity-facts-summary-v1.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=1, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
