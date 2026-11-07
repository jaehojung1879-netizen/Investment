"""Small, outcome-free DART HTML viewer adapter; unknown forms fail closed.

The existing corporate-action discovery receipt and amendment controls are reused.
Raw table cells stay available: extracted fields never substitute a later vintage.
"""
from __future__ import annotations

import hashlib
import gzip
import io
import json
from copy import deepcopy
import html
import re
import zlib
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from pipeline.kr_corporate_action_events import is_amendment, receipt_date

FAMILIES = {
    'BUYBACK': '자기주식취득결정',
    'TRUST': '자기주식취득신탁계약체결결정',
    'CANCELLATION': '주식소각결정',
    'DISPOSAL': '자기주식처분결정',
    'RIGHTS': '유상증자결정',
    'CB': '전환사채권발행결정',
    'EB': '교환사채권발행결정',
    'SUPPLY': '공급계약체결',
    'TERMINATION': '공급계약해지',
}


def load_filing(evidence: Path, metadata: dict) -> bytes:
    """Load one exact retained DART body, preserving its original encoding.

    The gzip container is storage only. Both stored and uncompressed identities
    must match; no text conversion, replacement decoding or implicit network.
    """
    receipt = metadata.get('rcept_no', '')
    if not isinstance(receipt, str) or not re.fullmatch(r'\d{14}', receipt):
        raise ValueError('FIXED_DART_BODY_PATH_REQUIRED')
    compressed = metadata.get('storage') == 'gzip'
    name = metadata.get('file')
    expected_name = receipt + ('.html.gz' if compressed else '.html')
    if name != expected_name:
        raise ValueError('FIXED_DART_BODY_PATH_REQUIRED')
    if metadata.get('storage') not in (None, 'identity', 'gzip'):
        raise ValueError('UNSUPPORTED_BODY_STORAGE')
    target = evidence / name
    if target.is_symlink() or not target.resolve().is_relative_to(evidence.resolve()):
        raise ValueError('BODY_PATH_ESCAPE')
    size = metadata.get('bytes')
    if type(size) is not int or not 0 < size <= 1_000_000:
        raise ValueError('BOUNDED_ORIGINAL_BODY_SIZE_REQUIRED')
    if target.stat().st_size > 1_000_000:
        raise ValueError('STORED_BODY_SIZE_LIMIT')
    stored = target.read_bytes()
    if compressed:
        if (metadata.get('storedBytes') != len(stored)
                or metadata.get('storedSha256') != hashlib.sha256(stored).hexdigest()):
            raise ValueError('STORED_BODY_IDENTITY_MISMATCH')
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(stored)) as stream:
                raw = stream.read(size + 1)
        except (OSError, EOFError, zlib.error) as exc:
            raise ValueError('INVALID_BODY_GZIP') from exc
    else:
        raw = stored
    if len(raw) != size or hashlib.sha256(raw).hexdigest() != metadata.get('sha256'):
        raise ValueError('ORIGINAL_BODY_IDENTITY_MISMATCH')
    return raw


def decode(raw: bytes) -> str:
    try:
        return raw.decode('utf-8')
    except UnicodeDecodeError:
        return raw.decode('cp949')


def clean(text: str) -> str:
    return re.sub(r'\s+', ' ', html.unescape(re.sub('<[^>]+>', ' ', text))).strip()


def table_rows(raw: bytes) -> list[list[str]]:
    text = decode(raw)
    return [[clean(c) for c in re.findall(r'<t[dh]\b[^>]*>(.*?)</t[dh]>', row, re.I | re.S)]
            for row in re.findall(r'<tr\b[^>]*>(.*?)</tr>', text, re.I | re.S)]


def number(text: str | None) -> str | None:
    if text is None or text.strip() in ('', '-', '해당사항없음'):
        return None
    value = text.replace(',', '').strip()
    if not re.fullmatch(r'[+-]?\d+(?:\.\d+)?', value):
        return None
    try:
        return str(Decimal(value))
    except InvalidOperation:
        return None


def day(text: str | None) -> str | None:
    if not text:
        return None
    m = re.fullmatch(r'(\d{4})(?:-|\s*년\s*)(\d{1,2})(?:-|\s*월\s*)(\d{1,2})(?:\s*일)?', text.strip())
    try:
        return date(*map(int, m.groups())).isoformat() if m else None
    except ValueError:
        return None


def _label(text: str) -> str:
    return re.sub(r'\s+', '', re.sub(r'^\d+(?:-\d+)?\.\s*', '', text))


def _value(rows: list[list[str]], labels: tuple[str, ...]) -> str | None:
    """Require one exact observed label; repeated labels are ambiguous, not first wins."""
    found = [row[i + 1:] for row in rows for i, cell in enumerate(row[:-1]) if _label(cell) in labels]
    if len(found) != 1:
        return None
    values = found[0]
    return values[-1] if values else None


def _period(rows: list[list[str]], label: str) -> tuple[str | None, str | None]:
    hits = [i for i, row in enumerate(rows) if row and _label(row[0]) == label]
    if len(hits) != 1:
        return None, None
    i = hits[0]
    start = day(rows[i][-1]) if '시작일' in rows[i] else None
    end = day(rows[i + 1][-1]) if i + 1 < len(rows) and rows[i + 1][0] == '종료일' else None
    return start, end


def parse_filing(raw: bytes, metadata: dict) -> dict:
    """Parse fixed bytes only. PARSED is distinct from empirical admission.

    DART list rows contain receipt DAY, not a publication clock or historical
    security identity. Neither today's issuer name nor its stock code proves PIT.
    """
    sha = hashlib.sha256(raw).hexdigest()
    title = metadata.get('report_nm', '')
    compact_title = title.replace('ㆍ', '').replace('·', '').replace(' ', '')
    family = next((key for key, word in FAMILIES.items() if word in compact_title), None)
    result = {
        'receipt_no': metadata.get('rcept_no'), 'issuer_id': metadata.get('corp_code'),
        'issuer_name_in_index': metadata.get('corp_name'),
        'security_code_in_index': metadata.get('stock_code'),
        'tradable_security_at_event': None, 'historical_name_mapping': None,
        'receipt_date': receipt_date(metadata.get('rcept_dt')),
        'receipt_at': None, 'published_at': None, 'pit_available_at': None,
        'availability_precision': 'DATE_ONLY_NO_INTRADAY_CLAIM',
        'family': family, 'input_sha256': sha, 'parser_version': 'dart-html-v1',
        'amendment': is_amendment(title), 'chain_parent_receipt': None,
        'chain_status': 'UNRESOLVED' if is_amendment(title) or family == 'TERMINATION' else 'ORIGINAL',
        'completion_status': 'NOT_OBSERVED', 'completion_known_at': None,
        'decision_date': None, 'expected_execution_start': None, 'expected_execution_end': None,
        'quantity_common': None, 'quantity_other': None, 'issued_shares_common_at_decision': None,
        'share_ratio_pct': None, 'amount_krw': None, 'purpose': None,
        'contract_amount_krw': None, 'recent_revenue_krw': None,
        'revenue_fiscal_year': None, 'revenue_basis': None, 'reported_contract_ratio_pct': None,
        'recomputed_contract_ratio_pct': None, 'contract_start': None, 'contract_end': None,
        'contract_name': None, 'counterparty': None, 'counterparty_country': None, 'supply_region': None,
        'changes': [], 'source_version_verified': False,
        'quarantine_reasons': [], 'parse_status': 'QUARANTINED',
        'data_eligibility': 'BLOCKED', 'economic_study_ready': False,
    }
    reasons = result['quarantine_reasons']
    if metadata.get('sha256') and metadata['sha256'] != sha:
        reasons.append('INPUT_HASH_MISMATCH')
        return result
    try:
        rows = [r for r in table_rows(raw) if r]
    except UnicodeError:
        reasons.append('UNSUPPORTED_ENCODING')
        return result
    result['raw_table_rows'] = rows
    if not family or not rows:
        reasons.append('UNSUPPORTED_FORM_OR_NO_TABLE')
        return result
    # A parent-company report about a subsidiary is not a parent security event.
    if '정' in metadata.get('rm', ''):
        reasons.append('INDEX_MARKS_AMENDMENTS_HISTORICAL_BODY_VERSION_UNVERIFIED')
    if '자회사' in title or '종속회사' in title:
        reasons.append('SUBSIDIARY_EVENT_SECURITY_UNRESOLVED')
    if result['amendment']:
        result['changes'] = [r for r in rows if any('정정' in c for c in r)]
        reasons.append('AMENDMENT_CHAIN_REQUIRES_ORIGINAL_RECEIPT_PROOF')
    result['decision_date'] = day(_value(rows, ('이사회결의일(결정일)', '취득결정일')))
    if family in ('SUPPLY', 'TERMINATION'):
        result['contract_amount_krw'] = number(_value(rows, ('계약금액(원)', '해지금액(원)')))
        result['recent_revenue_krw'] = number(_value(rows, ('최근매출액(원)',)))
        result['reported_contract_ratio_pct'] = number(_value(rows, ('매출액대비(%)',)))
        result['contract_start'], result['contract_end'] = _period(rows, '계약기간')
        result['contract_name'] = _value(rows, ('-체결계약명', '-해지계약명'))
        result['counterparty'] = _value(rows, ('계약상대',))
        result['supply_region'] = _value(rows, ('판매ㆍ공급지역', '판매·공급지역'))
        result['decision_date'] = day(_value(rows, ('계약(수주)일자', '해지일자')))
        # Only a contemporaneous explicit fiscal-year statement may set this field.
        notes = ' '.join(' '.join(r) for r in rows)
        m = re.search(r'최근\s*매출액은\s*(\d{4})년(?:말)?\s*(연결|별도)?\s*(?:재무제표|기준)', notes)
        if m:
            result['revenue_fiscal_year'] = int(m[1])
            result['revenue_basis'] = m[2] or 'UNSPECIFIED'
        else:
            reasons.append('REVENUE_FISCAL_YEAR_NOT_EXPLICIT')
        amount, revenue = result['contract_amount_krw'], result['recent_revenue_krw']
        if amount and revenue and Decimal(revenue) > 0:
            ratio = Decimal(amount) / Decimal(revenue) * 100
            result['recomputed_contract_ratio_pct'] = str(ratio)
            reported = result['reported_contract_ratio_pct']
            if reported is not None and abs(ratio - Decimal(reported)) > Decimal('0.11'):
                reasons.append('CONTRACT_RATIO_MISMATCH')
        else:
            reasons.append('CONTRACT_AMOUNT_OR_REVENUE_MISSING')
        if family == 'TERMINATION':
            reasons.append('TERMINATION_ORIGINAL_CHAIN_UNRESOLVED')
    else:
        quantity_labels = {
            'BUYBACK': ('취득예정주식(주)',), 'DISPOSAL': ('처분예정주식(주)',),
            'CANCELLATION': ('소각할주식의종류와수',), 'RIGHTS': ('신주의종류와수',),
        }
        result['quantity_common'] = number(_value(rows, quantity_labels.get(family, ('주식수',))))
        result['issued_shares_common_at_decision'] = number(_value(rows, ('증자전발행주식총수(주)', '발행주식총수')))
        result['purpose'] = _value(rows, ('취득목적', '처분목적', '계약목적'))
        if family in ('RIGHTS', 'CB', 'EB'):
            result['purpose'] = [r for r in rows if r and any(k in r[0] for k in ('자금조달의 목적', '시설자금', '운영자금', '기타자금', '채무상환자금', '영업양수자금', '타법인 증권 취득자금'))]
        labels = quantity_labels.get(family, ())
        hits = [i for i, r in enumerate(rows) if r and _label(r[0]) in labels]
        if len(hits) == 1 and hits[0] + 1 < len(rows):
            other = rows[hits[0] + 1]
            if other and any(k in other[0] for k in ('종류주식', '기타주식')):
                result['quantity_other'] = number(other[-1])
        result['amount_krw'] = number(_value(rows, {
            'BUYBACK': ('취득예정금액(원)',), 'DISPOSAL': ('처분예정금액(원)',),
            'TRUST': ('계약금액(원)',), 'CANCELLATION': ('소각예정금액(원)',),
            'CB': ('사채의권면총액(원)', '사채의권면(전자등록)총액(원)'),
            'EB': ('사채의권면총액(원)', '사채의권면(전자등록)총액(원)'),
        }.get(family, ())))
        period = {'BUYBACK': '취득예상기간', 'DISPOSAL': '처분기간', 'TRUST': '계약기간'}.get(family)
        if period:
            result['expected_execution_start'], result['expected_execution_end'] = _period(rows, period)
            if family == 'BUYBACK' and result['expected_execution_start'] is None:
                result['expected_execution_start'], result['expected_execution_end'] = _period(rows, '취득기간')
        else:
            result['expected_execution_start'] = day(_value(rows, ('납입일', '소각예정일')))
        count, total = result['quantity_common'], result['issued_shares_common_at_decision']
        if count is not None and total is not None and Decimal(total) > 0:
            result['share_ratio_pct'] = str(Decimal(count) / Decimal(total) * 100)
        if result['decision_date'] is None:
            reasons.append('DECISION_DATE_NOT_PARSED')
    required = ('contract_amount_krw', 'recent_revenue_krw', 'reported_contract_ratio_pct', 'decision_date') if family in ('SUPPLY', 'TERMINATION') else ('decision_date', 'amount_krw')
    if family in ('BUYBACK', 'DISPOSAL', 'CANCELLATION', 'RIGHTS', 'EB'):
        required += ('quantity_common',)
    for field in required:
        if result[field] is None:
            reasons.append('REQUIRED_FIELD_MISSING:' + field)
    for field in ('quantity_common', 'quantity_other', 'amount_krw', 'contract_amount_krw', 'recent_revenue_krw', 'reported_contract_ratio_pct'):
        if result[field] is not None and Decimal(result[field]) < 0:
            reasons.append('NEGATIVE_VALUE:' + field)
    if family not in ('SUPPLY', 'TERMINATION', 'TRUST') and result['issued_shares_common_at_decision'] is None:
        reasons.append('ISSUED_SHARES_DENOMINATOR_NOT_OBSERVED')
    if family == 'CB' and result['quantity_common'] is None:
        reasons.append('CONVERSION_SHARE_EQUIVALENT_NOT_OBSERVED')
    if result['decision_date'] and result['receipt_date'] and result['decision_date'] > result['receipt_date']:
        reasons.append('DECISION_AFTER_RECEIPT')
    if result['revenue_fiscal_year'] and result['receipt_date'] and result['revenue_fiscal_year'] > int(result['receipt_date'][:4]):
        reasons.append('REVENUE_FISCAL_YEAR_AFTER_RECEIPT')
    if not result['amendment']:
        result['parse_status'] = 'PARSED_WITH_GAPS' if reasons else 'PARSED'
    # These eligibility gaps do not erase parsed values.
    result['eligibility_blockers'] = ['PIT_SECURITY_IDENTITY_UNVERIFIED', 'PUBLICATION_TIME_UNVERIFIED',
                                      'HISTORICAL_DOCUMENT_VERSION_NOT_VERIFIED',
                                      'HISTORICAL_PRICE_ACTIONS_TERMINAL_CONSIDERATION_NOT_ADMITTED']
    return result


def _instant(text: str) -> datetime:
    instant = datetime.fromisoformat(text.replace('Z', '+00:00'))
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError('AWARE_TIMESTAMP_REQUIRED')
    return instant


def as_of_chain(versions: list[dict], cutoff: str) -> list[dict]:
    """No date-only or later version can silently amend the original signal."""
    at = _instant(cutoff)
    return [deepcopy(v) for v in versions if v.get('pit_available_at') and _instant(v['pit_available_at']) <= at]


def parse_viewer_family(raw: bytes, *, receipt: str, sha256: str) -> dict:
    """Read the explicit family menu, not a same-issuer/title/date heuristic.

    A current menu links disclosure versions. It does not authenticate the
    historical body, first-publication clock, issuer security or economic N.
    """
    if hashlib.sha256(raw).hexdigest() != sha256:
        raise ValueError('VIEWER_INPUT_HASH_MISMATCH')
    text = decode(raw)
    menus = re.findall(r'<select\b[^>]*\bid=["\x27]family["\x27][^>]*>(.*?)</select>', text, re.I | re.S)
    if len(menus) != 1:
        raise ValueError('UNIQUE_VIEWER_FAMILY_MENU_REQUIRED')
    versions = []
    for attrs, content in re.findall(r'<option\b([^>]*)>(.*?)</option>', menus[0], re.I | re.S):
        match = re.search(r'\bvalue=["\x27]rcpNo=(\d{14})["\x27]', attrs)
        if not match:
            continue
        no = match[1]
        title = clean(content)
        shown = re.match(r'(\d{4})\.(\d{2})\.(\d{2})\s', title)
        if not shown or ''.join(shown.groups()) != no[:8]:
            raise ValueError('VIEWER_RECEIPT_DATE_MISMATCH')
        versions.append({'receipt': no, 'receiptDate': date(*map(int, shown.groups())).isoformat(),
                         'amendment': is_amendment(title), 'label': title,
                         'publishedAt': None, 'historicalBodyVersionVerified': False})
    ids = [v['receipt'] for v in versions]
    if receipt not in ids or len(ids) != len(set(ids)):
        raise ValueError('UNIQUE_SELECTED_RECEIPT_REQUIRED')
    originals = [v for v in versions if not v['amendment']]
    # Termination is a follow-up of a supply event; its own menu is not its origin.
    root = originals[0]['receipt'] if len(originals) == 1 and '해지' not in originals[0]['label'] else None
    if root and any(v['receipt'] < root for v in versions):
        raise ValueError('VIEWER_AMENDMENT_PRECEDES_ORIGINAL')
    return {'evidenceClass': 'CURRENT_VIEWER_DECLARED_FAMILY_ONLY',
            'selectedReceipt': receipt, 'originalReceiptCandidate': root,
            'versions': sorted(versions, key=lambda v: v['receipt']),
            'sourceSha256': sha256, 'sourceVersionAtReceiptVerified': False,
            'independentEconomicEvents': None, 'pitEligible': False,
            'researchAdmission': False, 'outcomeExecutionAuthorized': False}


def version_terms(raw: bytes, metadata: dict) -> dict:
    """Extract one version's main form, never the before/after correction table.

    A hidden amount stays unavailable even if a later version discloses it.
    Receipt-level terms neither authenticate historical availability nor prove
    actual execution/cancellation completion.
    """
    if metadata.get('sha256') != hashlib.sha256(raw).hexdigest():
        raise ValueError('INPUT_HASH_MISMATCH')
    parsed = parse_filing(raw, metadata)
    if 'INPUT_HASH_MISMATCH' in parsed['quarantine_reasons']:
        raise ValueError('INPUT_HASH_MISMATCH')
    family = parsed['family']
    if family not in ('SUPPLY', 'CANCELLATION'):
        raise ValueError('SUPPORTED_VERSIONED_FORM_REQUIRED')
    text, depth, tables, table_start = decode(raw), 0, [], 0
    for match in re.finditer(r'</?table\b[^>]*>', text, re.I):
        if match[0].lower().startswith('</'):
            depth -= 1
            if depth < 0:
                raise ValueError('UNBALANCED_FORM_TABLE')
            if depth == 0:
                tables.append(text[table_start:match.end()])
        else:
            if depth == 0:
                table_start = match.start()
            depth += 1
    if depth:
        raise ValueError('UNBALANCED_FORM_TABLE')
    date_label = '계약(수주)일자' if family == 'SUPPLY' else '이사회결의일(결정일)'
    candidates = []
    for table in tables:
        rows = table_rows(table.encode('utf-8'))
        labels = {_label(cell) for row in rows for cell in row}
        if {'정정항목', '정정전', '정정후'} <= labels:
            continue
        if date_label in labels:
            candidates.append(rows)
    if len(candidates) != 1:
        raise ValueError('UNIQUE_MAIN_VERSION_FORM_REQUIRED')
    rows = candidates[0]
    amount_label = '계약금액(원)' if family == 'SUPPLY' else '소각예정금액(원)'
    raw_amount = _value(rows, (amount_label,))
    withheld = (raw_amount in ('-', '') and '공시유보' in ' '.join(' '.join(r) for r in rows))
    result = {
        'receipt': parsed['receipt_no'], 'issuer': parsed['issuer_id'],
        'family': family, 'sourceSha256': parsed['input_sha256'],
        'reportedDecisionDate': day(_value(rows, (date_label,))),
        'commonShares': number(_value(rows, ('소각할주식의종류와수',))) if family == 'CANCELLATION' else None,
        'amountKrw': number(raw_amount),
        'amountStatus': 'WITHHELD_AT_THIS_VERSION' if withheld else
                        ('OBSERVED' if number(raw_amount) is not None else 'MISSING_OR_AMBIGUOUS'),
        'contractName': _value(rows, ('-체결계약명',)) if family == 'SUPPLY' else None,
        'contractPeriod': list(_period(rows, '계약기간')) if family == 'SUPPLY' else None,
        'amendment': parsed['amendment'], 'publishedAt': None,
        'historicalVersionAuthenticated': False, 'completionStatus': 'NOT_OBSERVED',
        'researchAdmission': False, 'outcomeExecutionAuthorized': False,
    }
    if any(value is not None and Decimal(value) < 0
           for value in (result['amountKrw'], result['commonShares'])):
        raise ValueError('INVALID_VERSION_TERM_NUMBER')
    if (result['reportedDecisionDate'] and parsed['receipt_date']
            and result['reportedDecisionDate'] > parsed['receipt_date']):
        raise ValueError('VERSION_DECISION_AFTER_RECEIPT')
    return result


def corroborate_family_index(family: dict, raw_index: bytes, *, issuer: str,
                             expected_blob: str) -> dict:
    """Cross-check explicit menu links against pinned DART list bytes only."""
    from .build_inventory import _verify

    _verify(raw_index, expected_blob)
    with gzip.GzipFile(fileobj=io.BytesIO(raw_index)) as stream:
        body = stream.read(8_000_001)
    if len(body) > 8_000_000:
        raise ValueError('DART_INDEX_SIZE_LIMIT')
    wanted = {v['receipt']: v for v in family['versions']}
    if not wanted or len(wanted) != len(family['versions']):
        raise ValueError('UNIQUE_NONEMPTY_FAMILY_REQUIRED')
    found = {}
    for line in body.splitlines():
        row = json.loads(line)
        no = row.get('rcept_no')
        if no not in wanted:
            continue
        if no in found and found[no] != row:
            raise ValueError('CONFLICTING_INDEX_RECEIPT')
        if row.get('corp_code') != issuer:
            raise ValueError('INDEX_ISSUER_MISMATCH')
        if receipt_date(row.get('rcept_dt')) != wanted[no]['receiptDate']:
            raise ValueError('INDEX_MENU_DATE_MISMATCH')
        if is_amendment(row.get('report_nm')) != wanted[no]['amendment']:
            raise ValueError('INDEX_MENU_AMENDMENT_MISMATCH')
        def kinds(title):
            compact = str(title).replace('ㆍ', '').replace('·', '').replace(' ', '')
            return {name for name, term in FAMILIES.items() if term in compact}
        if not kinds(row.get('report_nm')) or kinds(row.get('report_nm')) != kinds(wanted[no].get('label')):
            raise ValueError('INDEX_MENU_FAMILY_MISMATCH')
        found[no] = row
    if set(found) != set(wanted):
        raise ValueError('INDEX_FAMILY_RECEIPT_MISSING')
    return {'issuer': issuer, 'indexBlob': expected_blob,
            'indexSha256': hashlib.sha256(raw_index).hexdigest(),
            'matchedReceipts': sorted(found), 'matchedVersionCount': len(found),
            'historicalSecurityIdentityVerified': False,
            'historicalPublicationClockVerified': False, 'researchAdmission': False}
