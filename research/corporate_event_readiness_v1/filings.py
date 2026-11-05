"""Small, outcome-free DART HTML viewer adapter; unknown forms fail closed.

The existing corporate-action discovery receipt and amendment controls are reused.
Raw table cells stay available: extracted fields never substitute a later vintage.
"""
from __future__ import annotations

import hashlib
from copy import deepcopy
import html
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

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
