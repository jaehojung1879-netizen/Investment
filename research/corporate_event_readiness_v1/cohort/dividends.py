"""Dividend-decision source build for the cohort issuers (outcome-free).

KRX bars carry no dividends, so a total-return basis needs, per issuer, every
dividend the holder was entitled to and the session on which the stock went
ex. This module reads the issuers' own ``현금ㆍ현물배당결정`` / ``주식배당결정``
filings (receipt-dated, OpenDART ``document.xml``) and extracts what they state:
kind, per-share amount (common / other class), market yield, total amount,
record date, scheduled payment date and the board-decision date.

Ex-date tier, kept separate from "resolved":
* many filings state that the yield's reference window starts at the close
  "배당기준일 전전거래일(배당부 종가일)" or "배당기준일 2매매거래일 전" -- the
  issuer's own statement that the last cum-dividend session is the second KR
  session before the record date. Phrasings anchored on 주주명부폐쇄일 or
  폐쇄기간 초일 are NOT accepted (they can name a different day);
* where that clause is present, ``exDateCandidate`` is the session after that
  cum day on the pinned XKRX calendar, with tier
  ``FILING_STATED_RELATIVE_RULE_PLUS_PINNED_CALENDAR``. It is NOT the
  ``DIRECT`` tier AGENTS v2.28 requires for READY (an ex-date stated outright),
  so ``exDateSemanticsResolved`` stays BLOCKED until the Owner accepts or
  rejects this tier. Where the clause is absent, no candidate is produced.
No price, return or adjustment factor is computed here.
"""
from __future__ import annotations

import argparse
import bisect
import gzip
import json
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from pipeline import replay_calendar

from ..filings import _label, day, number, table_rows
from .bodies import DocumentNotServed, as_table_cells, document_body
from .collect_issuers import collect_issuer
from .dart_client import DartClient
from .families import compact

KINDS = {'현금현물배당결정': 'CASH_OR_IN_KIND', '주식배당결정': 'STOCK'}
# Anchored on 배당기준일 only. "주주명부폐쇄일" / "폐쇄기간 초일" can name a different
# day than the record date (book-closure regime), so those phrasings never qualify.
CUM_RULE = re.compile(r'배당기준일\s*(?:의)?\s*(?:전전\s*거래일|제?\s*2\s*(?:매매)?\s*(?:거래|영업)일\s*'
                      r'(?:\(\s*배당부\s*종가일\s*\))?\s*전)')


def _row_value(rows: list[list[str]], label: str, sub: str | None = None) -> str | None:
    hits = [i for i, r in enumerate(rows) if r and _label(r[0]) == label]
    if len(hits) != 1:
        return None
    i = hits[0]
    if sub is None:
        return rows[i][-1] if len(rows[i]) > 1 else None
    if len(rows[i]) >= 3 and rows[i][1].replace(' ', '') == sub:
        return rows[i][-1]
    if i + 1 < len(rows) and rows[i + 1] and rows[i + 1][0].replace(' ', '') == sub:
        return rows[i + 1][-1]
    return None


def parse_dividend(raw: bytes) -> dict:
    cells, _ = as_table_cells(raw)
    rows = [r for r in table_rows(cells) if r]
    text = ' '.join(' '.join(r) for r in rows)
    out = {
        'dividendClass': _row_value(rows, '배당구분'),
        'dividendKind': _row_value(rows, '배당종류'),
        'dpsCommonKrw': number(_row_value(rows, '1주당배당금(원)', '보통주식')),
        'dpsOtherKrw': number(_row_value(rows, '1주당배당금(원)', '종류주식')),
        'yieldCommonPct': number(_row_value(rows, '시가배당률(%)', '보통주식')
                                 or _row_value(rows, '시가배당율(%)', '보통주식')),
        'totalKrw': number(_row_value(rows, '배당금총액(원)')),
        'recordDate': day(_row_value(rows, '배당기준일')),
        'paymentDate': day(_row_value(rows, '배당금지급예정일자')),
        'decisionDate': day(_row_value(rows, '이사회결의일(결정일)')),
        'cumDayRuleStated': bool(CUM_RULE.search(text)),
    }
    out['parseStatus'] = 'PARSED' if out['recordDate'] and (out['dpsCommonKrw'] or out['dpsOtherKrw']) else 'GAPS'
    return out


def ex_date_candidate(record_date: str | None, rule_stated: bool, sessions: list[str]) -> dict:
    if not record_date or not rule_stated:
        return {'exDateCandidate': None, 'exDateTier': 'NO_STATED_RULE' if record_date else 'NO_RECORD_DATE'}
    i = bisect.bisect_left(sessions, record_date)   # sessions strictly before the record date: sessions[:i]
    if i < 2:
        return {'exDateCandidate': None, 'exDateTier': 'CALENDAR_TOO_SHORT'}
    cum_last = sessions[i - 2]
    return {'cumDividendLastSession': cum_last, 'exDateCandidate': sessions[i - 1],
            'exDateTier': 'FILING_STATED_RELATIVE_RULE_PLUS_PINNED_CALENDAR'}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--events', type=Path, required=True)
    p.add_argument('--cache', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--workers', type=int, default=4)
    p.add_argument('--offline', action='store_true')
    args = p.parse_args(argv)
    sessions = [d.strftime('%Y-%m-%d') for d in replay_calendar.sessions('2012-01-01', '2027-12-31', 'KR')]
    events = [json.loads(line) for line in gzip.open(args.events, 'rt', encoding='utf-8')]
    corps = sorted({e['corp_code'] for e in events if e.get('pitGrade')})
    lists = DartClient(args.cache, offline=True)
    client = DartClient(args.cache, offline=args.offline)
    filings = []
    for corp in corps:
        rows, _ = collect_issuer(lists, corp, 'I001', '20130101', '20261031')
        for row in rows:
            kind = next((k for w, k in KINDS.items() if w in compact(row.get('report_nm', ''))), None)
            if kind:
                filings.append({'rcept_no': row['rcept_no'], 'rcept_dt': row['rcept_dt'], 'corp_code': corp,
                                'stock_code': row.get('stock_code'), 'report_nm': row['report_nm'], 'kind': kind,
                                'amendment': '정정' in row['report_nm']})

    def one(f):
        try:
            raw, info = document_body(client, f['rcept_no'])
        except DocumentNotServed as exc:
            return {**f, 'source': None, 'parseStatus': str(exc)}
        parsed = parse_dividend(raw)
        return {**f, **parsed, **ex_date_candidate(parsed['recordDate'], parsed['cumDayRuleStated'], sessions),
                'source': {'zipSha256': info['zipSha256'], 'bodySha256': info['bodySha256']}}

    out = []
    with ThreadPoolExecutor(args.workers) as pool:
        for fut in as_completed([pool.submit(one, f) for f in filings]):
            out.append(fut.result())
    out.sort(key=lambda r: r['rcept_no'])
    args.out.mkdir(parents=True, exist_ok=True)
    payload = ''.join(json.dumps(r, ensure_ascii=False, sort_keys=True) + '\n' for r in out)
    (args.out / 'dividend-decisions-v1.jsonl.gz').write_bytes(gzip.compress(payload.encode(), 9, mtime=0))
    originals = [r for r in out if not r['amendment']]
    summary = {
        'scope': 'OUTCOME_FREE_DIVIDEND_SOURCE_BUILD',
        'issuers': len(corps), 'filings': len(out), 'originals': len(originals),
        'amendments': len(out) - len(originals),
        'parseStatus': dict(Counter(r['parseStatus'] for r in originals)),
        'exDateTier': dict(Counter(r.get('exDateTier') for r in originals)),
        'issuersWithParsedOriginal': len({r['corp_code'] for r in originals if r['parseStatus'] == 'PARSED'}),
        'byRecordYear': dict(sorted(Counter((r.get('recordDate') or 'NONE')[:4] for r in originals).items())),
        'exDateSemanticsResolved': 'BLOCKED: FILING_STATED_RELATIVE_RULE tier is not DIRECT (AGENTS v2.28); '
                                   'Owner decision',
        'apiCalls': client.calls,
    }
    (args.out / 'dividend-decisions-summary-v1.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=1, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
