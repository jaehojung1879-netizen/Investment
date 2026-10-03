"""Fail-closed KRX OTP/CSV feasibility parsing; no membership or outcome admission."""
from __future__ import annotations
import csv
import hashlib
import io
import re


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def text_response(raw):
    for encoding in ('utf-8-sig', 'cp949', 'euc-kr'):
        try:
            return raw.decode(encoding), encoding
        except UnicodeError:
            pass
    return None, None


def valid_otp(raw, status):
    if status != 200:
        return None
    try:
        value = raw.decode('ascii').strip()
    except UnicodeError:
        return None
    if re.search(r'logout|login|error|denied|forbidden|unauthorized|failed', value, re.I):
        return None
    return value if re.fullmatch(r'[A-Za-z0-9+/=_-]{16,4096}', value) else None


ALIASES = {
    'securityCode': ('종목코드', '단축코드', 'stock_code', 'security_code'),
    'securityName': ('종목명', '한글종목명', 'security_name'),
    'industryCode': ('업종코드', '산업코드', 'industry_code'),
    'industryLabel': ('업종명', '산업명', 'industry_label'),
    'market': ('시장구분', '시장', 'market'),
    'date': ('기준일자', '기준일', '거래일자', '일자', 'trdDd', 'date'),
}


def parse_classification_csv(raw, status, context):
    """Only schema and code/name/industry/market/date fields are examined.

    HTTP success, a CSV extension, or an OTP token never prove a dated assignment.
    Unselected price/performance fields are never projected or used.
    """
    text, encoding = text_response(raw)
    result = {'status': 'REJECTED', 'reason': None, 'encoding': encoding, 'columns': [],
              'classificationRows': [], 'historicalMembershipAdmitted': False,
              'dateContext': dict(context), 'dateEvidence': 'REQUEST_BOUND_QUERY_ONLY',
              'outcomeFieldsInspected': False}
    if status != 200:
        result.update(reason='HTTP_ERROR_OR_TRANSPORT_FAILURE', errorVerbatim=text)
        return result
    if text is None:
        result['reason'] = 'UNSUPPORTED_ENCODING'
        return result
    stripped = text.lstrip()
    if not stripped:
        result['reason'] = 'EMPTY_BODY'
        return result
    if stripped.startswith(('<', '{', '[')) or re.match(r'^(LOGOUT|LOGIN|ERROR|FORBIDDEN|UNAUTHORIZED)\b', stripped, re.I):
        result.update(reason='ERROR_OR_NON_CSV_BODY', errorVerbatim=text)
        return result
    try:
        table = list(csv.reader(io.StringIO(text), strict=True))
    except csv.Error:
        result['reason'] = 'MALFORMED_CSV'
        return result
    columns = [c.strip() for c in table[0]]
    result['columns'] = columns
    if len(columns) != len(set(columns)):
        result['reason'] = 'DUPLICATE_SCHEMA_COLUMNS'
        return result
    selected = {field: next((columns.index(a) for a in aliases if a in columns), None)
                for field, aliases in ALIASES.items()}
    if selected['securityCode'] is None or selected['securityName'] is None or (
            selected['industryCode'] is None and selected['industryLabel'] is None):
        result['reason'] = 'REQUIRED_CLASSIFICATION_SCHEMA_MISSING'
        return result
    seen = set()
    rows = []
    for values in table[1:]:
        if not values:
            continue
        if len(values) != len(columns):
            result['reason'] = 'RAGGED_CSV'
            return result
        row = {field: values[index].strip() if index is not None else None for field, index in selected.items()}
        code = row['securityCode']
        if not re.fullmatch(r'\d{6}', code) or code in seen or not row['securityName']:
            result['reason'] = 'SECURITY_CODE_OR_SUBJECT_NOT_UNIQUE'
            return result
        seen.add(code)
        if row['date'] is not None and row['date'].replace('-', '') != context['effectiveDate'].replace('-', ''):
            result['reason'] = 'REQUESTED_DATE_CONFLICT'
            return result
        missing = not any(v and v.upper() not in {'UNKNOWN', 'N/A', 'NULL', '-', '미분류'}
                          for v in (row['industryCode'], row['industryLabel']))
        row['classificationStatus'] = 'UNKNOWN' if missing else 'REPORTED_CLASSIFICATION_REVIEW_REQUIRED'
        row['marketContext'] = 'CSV_COLUMN' if selected['market'] is not None else 'REQUEST_MARKET_ONLY'
        rows.append(row)
    if not rows:
        result['reason'] = 'EMPTY_CLASSIFICATION_CSV'
        return result
    result.update(status='CLASSIFICATION_CSV_REVIEW_REQUIRED', reason=None, classificationRows=rows,
                  dateEvidence='CSV_DATE_MATCHES_REQUEST' if selected['date'] is not None else 'REQUEST_BOUND_QUERY_ONLY')
    return result


def probe_date(requested, trading_dates):
    """Substitution uses the immediately prior KR session, never a future day."""
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', requested):
        raise ValueError('ISO_PROBE_DATE_REQUIRED')
    eligible = [d for d in trading_dates if d <= requested]
    if not eligible:
        raise ValueError('PRIOR_KR_SESSION_MISSING')
    effective = max(eligible)
    return {'requestedDate': requested, 'effectiveDate': effective, 'substituted': effective != requested,
            'substitutionReason': None if effective == requested else 'IMMEDIATELY_PRIOR_KR_SESSION'}
