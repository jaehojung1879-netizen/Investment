"""Price-side SOURCE admission for cohort events -- presence and tradability only.

Reads the KRX bar ledger (signal-history ``ledger/prices/kr``) but keeps, per
row, only ``(ticker, date, traded)`` where ``traded = volume > 0``. Open, high,
low, close and listed shares are discarded at parse time and never enter any
computation: this module answers "does a priceable, tradable session exist",
not "what was the return". A missing bar, a zero-volume (suspended) session or
a window that ends before maturity is a SOURCE fact, recorded, and never used
to drop an event (intention to treat, Owner draft C0).

It also inventories dividend-decision filings (``현금ㆍ현물배당결정`` /
``주식배당결정``) from the already-cached per-issuer I001 pages, because the
KRX bars carry no dividends; the ex-date rule is NOT derived here (AGENTS
v2.28: an ex-date is never computed from a record date by assumption).
"""
from __future__ import annotations

import argparse
import bisect
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from pipeline import replay_calendar

from .collect_issuers import collect_issuer
from .dart_client import DartClient
from .families import compact

DIVIDEND_WORDS = {'CASH_OR_IN_KIND_DIVIDEND': '현금현물배당결정', 'STOCK_DIVIDEND': '주식배당결정'}
PRICE_FIELDS_KEPT = ('ticker', 'date', 'traded')


def load_presence(price_dir: Path) -> tuple[dict[str, dict[str, bool]], dict]:
    presence: dict[str, dict[str, bool]] = defaultdict(dict)
    digests, dropped_keys = {}, set()
    for path in sorted(Path(price_dir).glob('krx-prices-*.jsonl.gz')):
        digests[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        with gzip.open(path, 'rt', encoding='utf-8') as fh:
            for line in fh:
                row = json.loads(line)
                ticker, day = row['ticker'], row['date']
                volume = row.get('volume')
                traded = bool(volume) and float(volume) > 0
                dropped_keys.update(k for k in row if k not in ('ticker', 'date', 'volume'))
                del row  # nothing but the three projected facts survives this loop
                presence[ticker][day] = traded
    return dict(presence), {'shardSha256': digests, 'fieldsKept': list(PRICE_FIELDS_KEPT),
                            'fieldsDiscardedAtParse': sorted(dropped_keys)}


def window_admission(bars: dict[str, bool] | None, sessions: list[str], entry: str, horizon: int,
                     ledger_end: str) -> dict:
    if not bars:
        return {'status': 'NO_PRICE_SOURCE'}
    i = bisect.bisect_left(sessions, entry)
    if i >= len(sessions) or sessions[i] != entry:
        return {'status': 'ENTRY_NOT_A_SESSION'}
    if i + horizon >= len(sessions) or sessions[i + horizon] > ledger_end:
        return {'status': 'PENDING_MATURITY_OR_LEDGER_END'}
    if not bars.get(entry):
        return {'status': 'ENTRY_NOT_TRADED' if entry in bars else 'NO_BAR_AT_ENTRY'}
    window = sessions[i:i + horizon + 1]
    present = [d for d in window if d in bars]
    last = max(present)
    untraded = sum(1 for d in window if d in bars and not bars[d])
    missing = sum(1 for d in window if d <= last and d not in bars)
    if last < window[-1]:
        status = 'ENDS_BEFORE_MATURITY_TERMINAL_ECONOMICS_REQUIRED'
    elif untraded or missing:
        status = 'SUSPENSION_OR_GAP_IN_WINDOW'
    else:
        status = 'FULL_WINDOW_TRADED'
    return {'status': status, 'lastBar': last, 'untradedSessions': untraded, 'missingSessions': missing}


def dividend_inventory(client: DartClient, corp_codes: list[str], bgn: str, end: str) -> dict:
    by_corp = {}
    for corp in corp_codes:
        rows, _ = collect_issuer(client, corp, 'I001', bgn, end)
        years = Counter()
        kinds = Counter()
        for row in rows:
            title = compact(row.get('report_nm', ''))
            for kind, word in DIVIDEND_WORDS.items():
                if word in title and '정정' not in title:
                    years[row['rcept_dt'][:4]] += 1
                    kinds[kind] += 1
        by_corp[corp] = {'filingsByYear': dict(sorted(years.items())), 'byKind': dict(kinds)}
    return by_corp


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--events', type=Path, required=True, help='cohort-events-v1.jsonl.gz')
    p.add_argument('--prices', type=Path, required=True, help='directory of krx-prices-YYYY.jsonl.gz')
    p.add_argument('--cache', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--start', default='20130101')
    p.add_argument('--end', default='20261031')
    args = p.parse_args(argv)
    sessions = [d.strftime('%Y-%m-%d') for d in replay_calendar.sessions('2013-01-01', '2027-12-31', 'KR')]
    presence, price_meta = load_presence(args.prices)
    ledger_end = max(max(v) for v in presence.values())
    events = [json.loads(line) for line in gzip.open(args.events, 'rt', encoding='utf-8')]
    independent = [e for e in events if e.get('pitGrade')]
    table = {}
    for horizon in (126, 252):
        for hyp in ('A1', 'A2', 'B1'):
            subset = [e for e in independent if e['hypothesis'] == hyp and e['independent'][f'H{horizon}']]
            statuses = Counter(window_admission(presence.get(e['stock_code'] + '.KS'), sessions,
                                                e['entrySession'], horizon, ledger_end)['status'] for e in subset)
            table[f'{hyp}_H{horizon}'] = {'N': len(subset), 'status': dict(sorted(statuses.items()))}
    client = DartClient(args.cache, offline=True)
    corps = sorted({e['corp_code'] for e in independent})
    dividends = dividend_inventory(client, corps, args.start, args.end)
    with_any = sum(1 for v in dividends.values() if v['filingsByYear'])
    report = {
        'scope': 'SOURCE_ADMISSION_PRESENCE_ONLY_NO_PRICE_VALUE_READ',
        'priceLedger': {'source': 'signal-history@73b3907a ledger/prices/kr (KRX sto/stk_bydd_trd, delisted incl.)',
                        'ledgerEnd': ledger_end, 'tickers': len(presence), **price_meta,
                        'dividendsCarried': False},
        'windowAdmission': table,
        'interpretation': {
            'FULL_WINDOW_TRADED': 'bars and positive volume on every session entry..entry+H',
            'SUSPENSION_OR_GAP_IN_WINDOW': 'zero-volume or missing sessions inside the window; still priceable',
            'ENDS_BEFORE_MATURITY_TERMINAL_ECONOMICS_REQUIRED': 'last bar before maturity: needs cited terminal '
                                                                'consideration; never last price or zero',
            'NO_BAR_AT_ENTRY / ENTRY_NOT_TRADED': 'pre-registered tradability failure at entry',
        },
        'dividendSourceInventory': {
            'source': 'cached OpenDART list.json I001 per issuer (no new calls)',
            'issuers': len(corps), 'issuersWithAnyDividendDecisionFiling': with_any,
            'filingsTotal': sum(sum(v['filingsByYear'].values()) for v in dividends.values()),
            'exDateRule': 'NOT_DERIVED (record-date to ex-date rule unsealed; AGENTS v2.28)',
            'totalReturnBasis': 'BLOCKED until dividend amounts, ex-dates and reinvestment policy are admitted',
            'byIssuer': dividends,
        },
        'viewerFallbackFor014': 'NOT_ATTEMPTED: #320 public-viewer plan records no bulk licence and zero further '
                                'requests without a new plan; 424 document.xml 014 answers stay a source gap',
    }
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=1, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps({'windowAdmission': table, 'dividendIssuers': [len(corps), with_any]}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
