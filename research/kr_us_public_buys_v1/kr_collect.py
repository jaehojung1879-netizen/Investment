"""Collect reproducible public DART D002 search receipts and transaction sections."""
from __future__ import annotations

import argparse
from calendar import monthrange
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import re
from threading import Event, Lock
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from scripts.collect_kr_industry_membership_sources import nodes

HOST = 'https://dart.fss.or.kr'
D002 = '임원주요주주특정증권등소유상황보고서'
LIST_FIELDS = {'maxResults': 100, 'sort': 'date', 'series': 'desc', 'pageGubun': 'corp', 'publicType': 'D002'}


def squeeze(value):
    return re.sub(r'[\s·ㆍ・]', '', value)


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=1) + '\n')
    temp.replace(path)


class PublicDart:
    def __init__(self, root, pace, max_calls):
        self.root = root
        self.pace = pace
        self.max_calls = max_calls
        self.calls = 0
        self.next_request = 0.
        self.rate_stop = Event()
        self.consecutive_unavailable = 0
        self.lock = Lock()

    def get(self, route, query, rel):
        destination = self.root / rel
        receipt = destination.with_suffix('.json')
        url = HOST + route + '?' + urlencode(query)
        if receipt.is_file():
            cached = json.loads(receipt.read_text())
            if cached['url'] != url:
                raise ValueError(f'cached URL differs for {rel}')
            if cached['status'] == 200:
                raw = gzip.decompress(destination.read_bytes())
                assert hashlib.sha256(raw).hexdigest() == cached['sha256']
                return raw, cached
        with self.lock:
            if self.rate_stop.is_set() or self.calls >= self.max_calls:
                return None, {'url': url, 'status': None, 'error': 'RATE_OR_CALL_BUDGET_STOP'}
            time.sleep(max(0., self.next_request - time.monotonic()))
            self.next_request = time.monotonic() + self.pace
            self.calls += 1
        status, content = None, None
        try:
            req = Request(url, headers={'User-Agent': 'Mozilla/5.0 (historical public DART research)'})
            with urlopen(req, timeout=12) as response:
                status = response.status
                content = response.read(3_000_000)
            error = None
        except HTTPError as exc:
            status, error = exc.code, 'HTTP_ERROR'
            if status in (403, 429):
                self.rate_stop.set()
        except (URLError, OSError) as exc:
            error = type(exc).__name__
        with self.lock:
            self.consecutive_unavailable = self.consecutive_unavailable + 1 if status == 503 else 0
            if self.consecutive_unavailable >= 4:
                self.rate_stop.set()
        result = {'url': url, 'status': status, 'error': error, 'retrievedAtUTC': utcnow()}
        if content:
            result.update(sha256=hashlib.sha256(content).hexdigest(), bytes=len(content))
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(gzip.compress(content, mtime=0))
        if not (status is None and self.rate_stop.is_set()):
            save(receipt, result)
        return content, result


def search_rows(raw):
    soup = BeautifulSoup(raw.decode('utf-8', 'strict'), 'html.parser')
    info = soup.select_one('div.pageInfo')
    body = soup.select_one('table.tbList > tbody')
    if not body:
        raise ValueError('DART table missing')
    if not info:
        if body.select_one('td.no_data') and '조회 결과가 없습니다' in body.get_text(' ', strip=True):
            return 1, 1, 0, []
        raise ValueError('DART pagination missing')
    m = re.fullmatch(r'\[(\d+)/(\d+)\]\s*\[총 ([\d,]+)건\]', info.get_text(strip=True))
    if m is None:
        raise ValueError('DART pagination mismatched')
    page, pages, total = (int(v.replace(',', '')) for v in m.groups())
    rows = []
    for row in body.find_all('tr', recursive=False):
        cells = row.find_all('td', recursive=False)
        company, form = cells[1].select_one('a'), cells[2].select_one('a[id^=r_]')
        receipt = form['id'].removeprefix('r_')
        filing = form.get_text(' ', strip=True)
        corp_code = re.search(r"openCorpInfoNew\('([\d]{8})'", company.get('onclick', '')).group(1)
        date = cells[4].get_text(strip=True).replace('.', '-')
        assert re.fullmatch(r'\d{14}', receipt) and receipt[:8] <= date.replace('-', '') and D002 in squeeze(filing)
        rows.append({'receipt': receipt, 'corpCode': corp_code, 'publicDate': date,
                     'receiptPrefixDate': f'{receipt[:4]}-{receipt[4:6]}-{receipt[6:8]}',
                     'issuerName': company.get_text(' ', strip=True), 'reporter': cells[3].get_text(' ', strip=True),
                     'form': filing})
    return page, pages, total, rows


def search_month(client, yr_month):
    year, month = map(int, yr_month.split('-'))
    start = f'{year:04d}{month:02d}01'
    end = f'{year:04d}{month:02d}{monthrange(year, month)[1]:02d}'
    query = {**LIST_FIELDS, 'startDate': start, 'endDate': end, 'currentPage': 1}
    records, provenance = [], []
    result = {'month': yr_month, 'complete': False, 'pageReceipts': provenance, 'rows': records}
    while True:
        raw, receipt = client.get('/dsab001/searchCorp.ax', query,
                                  f'lists/{yr_month}-{query["currentPage"]:02d}.html.gz')
        provenance.append(receipt)
        if not raw:
            break
        try:
            page, pages, total, rows = search_rows(raw)
        except (ValueError, AttributeError, KeyError, IndexError, AssertionError) as exc:
            result['error'] = f'{type(exc).__name__}: {exc}'
            break
        if page != query['currentPage'] or ('declaredCount' in result and result['declaredCount'] != total):
            result['error'] = 'UNSTABLE_PAGE_TOTAL'
            break
        result.update(declaredCount=total, declaredPages=pages)
        records.extend(rows)
        if page >= pages:
            result['complete'] = len({r['receipt'] for r in records}) == len(records) == total
            break
        query['currentPage'] += 1
    save(client.root / f'parsed-lists/{yr_month}.json', result)
    print('DART list', yr_month, len(records), result['complete'], flush=True)
    return result


def label_key(value):
    return squeeze(value).replace('*', '')


def detail_table(raw):
    soup = BeautifulSoup(raw.decode('utf-8', 'strict'), 'html.parser')
    for table in soup.find_all('table'):
        headers = ''.join(label_key(h.get_text('', strip=True)) for h in table.find_all('th'))
        if not all(token in headers for token in ('보고사유', '변동일', '단가', '증감')):
            continue
        output = []
        for tr in table.find_all('tr'):
            cells = [td.get_text(' ', strip=True) for td in tr.find_all('td', recursive=False)]
            if not cells or label_key(cells[0]).startswith('합계'):
                continue
            if len(cells) not in (8, 9):
                return None
            reason, event, security, before, delta, after, price, note = cells[:8]
            output.append({'reason': reason, 'eventReported': event, 'security': security, 'before': before,
                           'delta': delta, 'after': after, 'price': price, 'note': note,
                           'planDate': cells[8] if len(cells) > 8 else None})
        return output
    return None


def disclosure(client, listed):
    receipt = listed['receipt']
    raw, main = client.get('/dsaf001/main.do', {'rcpNo': receipt}, f'docs/{receipt}-main.html.gz')
    value = {**listed, 'main': main, 'status': 'MAIN_UNAVAILABLE'}
    if not raw:
        return value
    sections = nodes(raw, receipt)
    soup = BeautifulSoup(raw.decode('utf-8', errors='strict'), 'html.parser')
    family = [option.get('value', '').removeprefix('rcpNo=')
              for option in soup.select('select#family option')]
    value['amendmentFamily'] = sorted({n for n in family if re.fullmatch(r'\d{14}', n)})
    candidates = [n for n in sections if '특정증권등의소유상황' in squeeze(n['text'])]
    if not candidates:
        value['status'] = 'DETAIL_NODE_UNAVAILABLE'
        return value
    node = candidates[0]
    detail, info = client.get('/report/viewer.do', {k: node[k] for k in ('rcpNo', 'dcmNo', 'eleId', 'offset', 'length', 'dtd')},
                              f'docs/{receipt}-detail.html.gz')
    value.update(status='DETAIL_UNAVAILABLE', detail=info)
    if detail:
        rows = detail_table(detail)
        value.update(status='PARSED' if rows is not None else 'UNRECOGNIZED_TABLE', transactions=rows)
    return value


def collect_docs(client, plan, workers):
    plan['root'] = str(client.root)
    print('DART scoped documents', len(plan['rows']), flush=True)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i, result in enumerate(pool.map(lambda row: disclosure(client, row), plan['rows']), 1):
            if result['main'].get('error') != 'RATE_OR_CALL_BUDGET_STOP':
                save(client.root / f'parsed-docs/{result["receipt"]}.json', result)
            if i % 50 == 0:
                print('DART document', i, 'of', len(plan['rows']), client.calls, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('lists', 'docs'))
    parser.add_argument('--raw', type=Path, default=Path('/workspace/public-buys-inputs/kr'))
    parser.add_argument('--start-month', default='2023-01')
    parser.add_argument('--end-month', default='2025-08')
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--pace', type=float, default=.22)
    parser.add_argument('--max-calls', type=int, default=6000)
    args = parser.parse_args()
    client = PublicDart(args.raw, args.pace, args.max_calls)
    if args.stage == 'lists':
        months = [f'{y:04d}-{m:02d}' for y in range(2017, 2027) for m in range(1, 13)
                  if args.start_month <= f'{y:04d}-{m:02d}' <= args.end_month]
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            results = list(pool.map(lambda month: search_month(client, month), months))
        print(Counter(r['complete'] for r in results), flush=True)
    else:
        collect_docs(client, json.loads((args.raw / 'collection-plan.json').read_text()), args.workers)


if __name__ == '__main__':
    main()
