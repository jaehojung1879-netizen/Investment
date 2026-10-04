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
    if 'class="errorpage"' in text or '<title>페이지 오류' in text:
        return {'status': 'SOURCE_ERROR_PAGE', 'reason': 'KIND_PAGE_ERROR', 'rows': []}
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


NOTICE_PARSER_VERSION = 'kr-industry-v3-notice-parser-2'
_STRIP_STYLE = re.compile(r'(?is)<style.*?</style>')
_DATE = re.compile(r'(\d{4})[-.](\d{2})[-.](\d{2})')


def viewer_identity(viewer_html):
    """KIND's own viewer header for a receipt: '<company> (<6-digit stock code>)'."""
    m = re.search(r'<h1 class="ttl[^"]*">\s*([^<]*?)\s*\((\d{6})\)\s*</h1>', viewer_html or '')
    return {'company': m[1], 'stock_code': m[2]} if m else None


def _norm(label):
    return ''.join((label or '').split())


def parse_notice(document_html, viewer_html):
    """Only explicitly labelled facts. Returns status PARSED or an UNRESOLVED reason; nothing is inferred."""
    identity = viewer_identity(viewer_html)
    out = {'status': 'UNRESOLVED', 'reason': None, 'identity': identity, 'parserVersion': NOTICE_PARSER_VERSION,
           'before_label': None, 'before_code': None, 'after_label': None, 'after_code': None,
           'effective_date': None, 'reason_text': None, 'format': None}
    if identity is None:
        out['reason'] = 'VIEWER_IDENTITY_NOT_STATED'
        return out
    body = _STRIP_STYLE.sub('', document_html or '')
    table = _Table()
    table.feed(body)
    rows = [r for r in table.rows if any(r)]
    flat = {r[0]: r[1:] for r in rows if r}
    changed = next((r for r in rows if r and r[0].startswith('2.업종 및 업종코드')), None)
    if changed is not None:
        out['format'] = 'STRUCTURED_FORM'
        phase, labels, codes = None, {}, {}
        started = False
        for r in rows:
            if r and r[0].startswith('2.업종 및 업종코드'):
                started = True
                cells = r[1:]
            elif started:
                cells = r
            else:
                continue
            if cells and cells[0] in ('변경 전', '변경전', '변경 후', '변경후'):
                phase = 'before' if '전' in cells[0] else 'after'
                cells = cells[1:]
            if cells and cells[0] == '업종' and len(cells) > 1 and phase:
                labels[phase] = cells[1]
            elif cells and cells[0] == '업종코드' and len(cells) > 1 and phase:
                codes[phase] = cells[1]
            elif cells and r and r[0].startswith('3.'):
                break
        out.update(before_label=labels.get('before'), before_code=codes.get('before'),
                   after_label=labels.get('after'), after_code=codes.get('after'))
        date_cell = next((v for k, v in flat.items() if k.startswith('3.변경일')), None)
        reason = next((v for k, v in flat.items() if k.startswith('4.변경사유')), None)
        out['reason_text'] = ' '.join(reason or []) or None
        m = _DATE.search(' '.join(date_cell or []))
    else:
        text = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', body))
        before = re.search(r'변경\s*전\s*업종\s*및\s*코드(.*?)변경\s*후\s*업종', text)
        after = re.search(r'변경\s*후\s*업종\s*및\s*코드(.*?)4\.\s*변경일', text)
        m = re.search(r'변경일\s*:\s*(\d{4}[-.]\d{2}[-.]\d{2})', text)
        small = re.compile(r'\(소분류\)\s*([^()]+?)\s*\((\d+)\)')
        if before and after and small.search(before[1]) and small.search(after[1]):
            out['format'] = 'FREE_TEXT_SMALL_CLASS'
            b, a = small.search(before[1]), small.search(after[1])
            out.update(before_label=b[1].strip(), before_code=b[2], after_label=a[1].strip(), after_code=a[2])
        reason = re.search(r'5\.\s*변경사유\s*:\s*(.*?)\s*6\.', text)
        out['reason_text'] = reason[1] if reason else None
    if not m:
        out['reason'] = 'EFFECTIVE_DATE_NOT_STATED'
        return out
    out['effective_date'] = '-'.join(_DATE.search(m[0]).groups())
    if not out['before_label'] or not out['after_label']:
        out['reason'] = 'BEFORE_OR_AFTER_NOT_STATED'
        return out
    out['status'] = 'PARSED'
    return out


def reconstruct_intervals(anchor_label, events, break_dates=()):
    """Intervals by disclosed effective date, anchored to a current official label.

    Older label = disclosed before-label; between events the disclosed after-label must equal
    the next event's before-label; after the last event it must equal the anchor. A mismatch
    leaves that interval UNKNOWN (CONFLICT). With no event at all the anchor is carried back
    as RECONSTRUCTED_STABLE_NO_CHANGE_EVENT. An identity break date stops any carrying across it.
    """
    usable = sorted((e for e in events if e.get('effective_date') and e.get('before_label') and e.get('after_label')
                     and _norm(e['before_label']) != _norm(e['after_label'])), key=lambda e: e['effective_date'])
    dates = [e['effective_date'] for e in usable]
    if len(set(dates)) != len(dates):
        return [{'start': None, 'end': None, 'label': None, 'status': 'CONFLICT', 'reason': 'SAME_EFFECTIVE_DATE_EVENTS'}]
    if not usable:
        if anchor_label is None:
            return [{'start': None, 'end': None, 'label': None, 'status': 'UNKNOWN', 'reason': 'NO_ANCHOR_NO_EVENT'}]
        return [{'start': None, 'end': None, 'label': anchor_label, 'status': 'RECONSTRUCTED_STABLE_NO_CHANGE_EVENT'}]
    out = [{'start': None, 'end': usable[0]['effective_date'], 'label': usable[0]['before_label'], 'status': 'VERIFIED_KRX_KIND_CHANGE_EVENT', 'notice_date': None}]
    for i, e in enumerate(usable):
        end = usable[i + 1]['effective_date'] if i + 1 < len(usable) else None
        nxt = usable[i + 1]['before_label'] if i + 1 < len(usable) else anchor_label
        if nxt is None:
            out.append({'start': e['effective_date'], 'end': end, 'label': None, 'status': 'UNKNOWN', 'reason': 'NO_ANCHOR_AFTER_LAST_EVENT'})
        elif _norm(e['after_label']) != _norm(nxt):
            out.append({'start': e['effective_date'], 'end': end, 'label': None, 'status': 'CONFLICT', 'reason': 'AFTER_LABEL_DISAGREES_WITH_NEXT_BEFORE_OR_ANCHOR'})
        else:
            out.append({'start': e['effective_date'], 'end': end, 'label': e['after_label'],
                        'status': 'VERIFIED_KRX_KIND_CHANGE_EVENT' if end else 'CURRENT_KRX_KIND_ANCHOR', 'notice_date': e.get('notice_date')})
    for stop in break_dates:
        for iv in out:
            if iv['label'] and (iv['start'] is None or iv['start'] < stop) and (iv['end'] is None or iv['end'] > stop):
                iv.update(label=None, status='UNKNOWN', reason='IDENTITY_BREAK_INSIDE_INTERVAL')
    return out


def label_at(intervals, stamp):
    for iv in intervals:
        if (iv['start'] is None or stamp >= iv['start']) and (iv['end'] is None or stamp < iv['end']):
            return iv
    return None


def anchor_map(rows):
    """Code -> raw current label. Identical duplicate rows collapse; differing labels drop the anchor (conflict)."""
    seen, conflicts = {}, set()
    for r in rows:
        label = r['industry_label']
        if r['ticker'] in seen and seen[r['ticker']] != label:
            conflicts.add(r['ticker'])
        seen.setdefault(r['ticker'], label)
    return {k: v for k, v in seen.items() if k not in conflicts and v}, sorted(conflicts)
