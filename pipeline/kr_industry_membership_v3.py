"""KRX current-state anchor and official change-event reconstruction, outcome-free.

Three kinds of evidence are kept apart and never merged into one tier:
CURRENT_ONLY anchors (state as of an acquisition date, never historical),
dated official change events (KIND notices, primary) and secondary corroboration
(DART / retained v1-v2 bytes). Nothing here reads a price, return or model.
"""
from __future__ import annotations
from datetime import date
from html.parser import HTMLParser
import hashlib
import re

CONTRACT = 'KR_INDUSTRY_MEMBERSHIP_FOUNDATION_V3'
CURRENT_TIER = 'CURRENT_ONLY_CROSSCHECK'
EVENT_TIER = 'KIND_DATED_INDUSTRY_CHANGE_NOTICE'
SECONDARY_TIER = 'SECONDARY_CORROBORATION_ONLY'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def decode(raw):
    for encoding in ('utf-8-sig', 'cp949', 'euc-kr'):
        try:
            return raw.decode(encoding), encoding
        except UnicodeError:
            pass
    return None, None


class _Table(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self._row, self._cell = [], None, None

    def handle_starttag(self, tag, attrs):
        if tag == 'tr':
            self._row = []
        elif tag in ('td', 'th') and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self._cell is not None:
            self._row.append(' '.join(''.join(self._cell).split()))
            self._cell = None
        elif tag == 'tr' and self._row is not None:
            self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


FIELDS = {'name': ('회사명', '종목명'), 'ticker': ('종목코드', '단축코드'), 'industry': ('업종', '업종명'),
          'market': ('시장구분', '시장')}


def parse_current_state(raw, acquired_on):
    """Parse an official listed-company table as a CURRENT_ONLY anchor.

    HTTP success, a plausible table or the word 업종 prove nothing about any past date.
    """
    text, encoding = decode(raw)
    out = {'status': 'REJECTED', 'reason': None, 'encoding': encoding, 'rows': [], 'tier': CURRENT_TIER,
           'asOf': acquired_on, 'historicalAdmitted': False}
    if text is None:
        out['reason'] = 'UNSUPPORTED_ENCODING'
        return out
    parser = _Table()
    parser.feed(text)
    if not parser.rows:
        out['reason'] = 'NO_TABLE'
        return out
    header = parser.rows[0]
    index = {k: next((header.index(a) for a in names if a in header), None) for k, names in FIELDS.items()}
    if index['ticker'] is None or index['industry'] is None:
        out['reason'] = 'REQUIRED_COLUMNS_ABSENT'
        out['columns'] = header
        return out
    for row in parser.rows[1:]:
        if len(row) != len(header):
            continue
        ticker = row[index['ticker']].zfill(6) if row[index['ticker']].isdigit() else row[index['ticker']]
        label = row[index['industry']].strip()
        out['rows'].append({'ticker': ticker, 'name': row[index['name']] if index['name'] is not None else None,
                            'market': row[index['market']] if index['market'] is not None else None,
                            'industry_label': label or None})
    out['status'] = 'PARSED_CURRENT_ONLY' if out['rows'] else 'EMPTY'
    out['columns'] = header
    return out


def valid_event(event):
    """A change event is usable only if it states both labels and a real notice date itself."""
    try:
        date.fromisoformat(event['notice_date'])
    except (KeyError, ValueError, TypeError):
        return 'NOTICE_DATE_UNPROVEN'
    if not event.get('before_label') or not event.get('after_label'):
        return 'BEFORE_OR_AFTER_LABEL_NOT_STATED'
    if event['before_label'] == event['after_label']:
        return 'NOT_A_CHANGE'
    if not event.get('source_sha256') or event.get('identity_status') != 'EXACT_ISSUER_SECURITY':
        return 'SOURCE_OR_IDENTITY_UNPROVEN'
    return None


def reconstruct(anchor_label, events):
    """Walk backward from a current anchor over dated official events.

    An interval starts at a dated official event that states its label (PIT_ADMISSIBLE_INTERVAL).
    The oldest interval has no dated start; its label is known only in hindsight, so it is
    UNVERIFIED_START and is never admitted as a point-in-time state. A chain that does not
    connect (an event's after-label differs from the label it must explain) stops the walk:
    everything older is UNKNOWN, never guessed.
    """
    rejected, usable = [], []
    for event in events:
        reason = valid_event(event)
        (rejected if reason else usable).append((event, reason))
    usable = sorted((e for e, _ in usable), key=lambda e: e['notice_date'])
    if len({e['notice_date'] for e in usable}) != len(usable):
        return {'status': 'AMBIGUOUS_SAME_DATE_EVENTS', 'intervals': [], 'rejected': [r for _, r in rejected]}
    intervals, label, end = [], anchor_label, None
    for event in reversed(usable):
        if event['after_label'] != label:
            intervals.append({'label': None, 'end': event['notice_date'], 'start': None, 'status': 'CHAIN_BREAK_UNKNOWN_BEFORE'})
            return {'status': 'CHAIN_BREAK', 'intervals': intervals, 'rejected': [r for _, r in rejected]}
        intervals.append({'label': label, 'start': event['notice_date'], 'end': end, 'status': 'PIT_ADMISSIBLE_INTERVAL'})
        label, end = event['before_label'], event['notice_date']
    if anchor_label is None:
        return {'status': 'NO_ANCHOR', 'intervals': [], 'rejected': [r for _, r in rejected]}
    intervals.append({'label': label, 'start': None, 'end': end, 'status': 'UNVERIFIED_START_NOT_PIT'})
    return {'status': 'RECONSTRUCTED', 'intervals': intervals, 'rejected': [r for _, r in rejected]}


FAMILIES = (('INDUSTRY_CHANGE', r'업종\s*변경'), ('TRADE_NAME_CHANGE', r'상호\s*변경'), ('MERGER', r'합병'),
            ('SPLIT', r'분할'), ('DELISTING', r'상장\s*폐지'), ('CODE_CHANGE', r'종목\s*코드\s*변경'))


def classify_disclosure_title(title):
    """A title match is a reading list entry, never a before/after assignment."""
    return [name for name, pattern in FAMILIES if re.search(pattern, title or '')]


def parse_kind_listing(raw):
    """Rows of a KIND disclosure list: receipt number, date, company, title. A title is a reading list entry."""
    text, _ = decode(raw)
    if text is None:
        return {'status': 'REJECTED', 'reason': 'UNSUPPORTED_ENCODING', 'rows': []}
    if 'Access Denied' in text[:400]:
        return {'status': 'ACCESS_DENIED', 'reason': 'EDGE_DENIAL', 'rows': []}
    table = _Table()
    table.feed(text)
    rows = []
    for row in table.rows:
        if len(row) >= 4 and re.fullmatch(r'\d+', row[0] or ''):
            rows.append({'seq': row[0], 'time': row[1], 'company': row[2], 'title': row[3]})
    receipts = re.findall(r"openDisclsViewer\('(\d{14})'", text)
    if len(receipts) != len(rows):
        return {'status': 'RECEIPT_ROW_MISMATCH', 'reason': f'{len(receipts)} receipts vs {len(rows)} rows', 'rows': []}
    for row, receipt in zip(rows, receipts):
        row['receipt_no'] = receipt
        row['families'] = classify_disclosure_title(row['title'])
    return {'status': 'PARSED' if rows else 'EMPTY', 'reason': None, 'rows': rows, 'alert': re.findall(r'alert\("([^"]*)"', text)}
