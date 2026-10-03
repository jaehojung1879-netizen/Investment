"""Outcome-free, header-only KRX reference API feasibility evidence.

No response values are exported, no membership is admitted by this probe.
The documented section/board field (소속부) is not an economic industry.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import urllib.parse
import urllib.request

DATES = ('2015-01-02', '2020-01-02', '2023-01-02', '2026-09-01')
SERVICES = ('sto/stk_isu_base_info', 'sto/ksq_isu_base_info',
            'sto/knx_isu_base_info', 'sto/stk_bydd_trd')
BASE = 'https://data-dbg.krx.co.kr/svc/apis/'
SENSITIVE_FIELDS = {'auth_key', 'authkey', 'api_key', 'apikey', 'token', 'password',
                    'account', 'account_number', 'acnt_no', 'authorization', 'cookie'}


class CredentialSafetyError(ValueError):
    """Fixed-message exception: never interpolate credential or response bytes."""


def ensure_safe_bytes(raw, key):
    if not key or len(key) < 8:
        raise CredentialSafetyError('CREDENTIAL_UNAVAILABLE_OR_INVALID')
    # Check before hashing, decoding metadata, writing or logging ANY response.
    forms = (key.encode(), urllib.parse.quote(key, safe='').encode(),
             base64.b64encode(key.encode()), json.dumps(key)[1:-1].encode())
    if any(secret in raw for secret in forms):
        raise CredentialSafetyError('RESPONSE_REJECTED_CREDENTIAL_PRESENT')


def validate_plan(plan):
    if (plan['mode'] != 'BOUNDED_FEASIBILITY_ONLY' or tuple(plan['dates']) != DATES
            or tuple(s['serviceId'] for s in plan['services']) != SERVICES
            or plan['maxRequests'] != 16 or plan['maxConcurrency'] != 1
            or plan['minimumIntervalSeconds'] < 1 or plan['retainRawResponses']
            or plan['fullHistoryExpansionAuthorized']):
        raise ValueError('FROZEN_FEASIBILITY_PLAN_REQUIRED')
    for service in plan['services']:
        if (service['endpoint'] != BASE + service['serviceId']
                or service['dateParameter'] != 'basDd'
                or service['industryFields'] != []):
            raise ValueError('OFFICIAL_REFERENCE_CONTRACT_CHANGED')
    return plan


def request_for(service, date, key):
    if service not in SERVICES or date not in DATES:
        raise ValueError('REQUEST_OUTSIDE_FROZEN_PROBE')
    ensure_safe_bytes(b'', key)
    url = BASE + service + '?' + urllib.parse.urlencode({'basDd': date.replace('-', '')})
    return urllib.request.Request(url, headers={'AUTH_KEY': key, 'Accept': 'application/json'}, method='GET')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # A credential-bearing request must never follow a redirect.
        return None


def _has_sensitive_field(value):
    if isinstance(value, dict):
        return any(str(k).lower() in SENSITIVE_FIELDS or _has_sensitive_field(v) for k, v in value.items())
    if isinstance(value, list):
        return any(_has_sensitive_field(v) for v in value)
    return False


def summarize_response(raw, status, content_type, service, date, key):
    ensure_safe_bytes(raw, key)
    try:
        parsed = json.loads(raw)
    except (ValueError, UnicodeError):
        parsed = None
    if _has_sensitive_field(parsed):
        raise CredentialSafetyError('RESPONSE_REJECTED_SENSITIVE_FIELD')
    # Never retain arbitrary server strings, header values, identifiers or rows.
    result = {'requestedHistoricalDate': date, 'effectiveHistoricalDate': None,
              'parameters': {'basDd': date.replace('-', '')}, 'httpStatus': status,
              'responseContentType': 'application/json' if 'application/json' in content_type.lower()
                  else 'text/html' if 'text/html' in content_type.lower() else 'OTHER',
              'responseSha256': hashlib.sha256(raw).hexdigest(), 'responseBytes': len(raw),
              'columns': [], 'rowCount': 0, 'securityIdentifierFields': [],
              'marketFields': [], 'industryFields': [], 'membershipRowsAdmitted': 0,
              'historicalAsOfMembershipProven': False, 'historicalDateAccepted': False,
              'serviceApprovalObserved': 'UNRESOLVED', 'classification': 'NO_USABLE_RESPONSE',
              'reason': 'NO_NONEMPTY_DOCUMENTED_ROWS'}
    if (raw.strip() in (b'Unauthorized API Call', b'"Unauthorized API Call"')
            or isinstance(parsed, dict) and parsed.get('respMsg') == 'Unauthorized API Call'):
        result.update(classification='AUTHENTICATED_SERVICE_NOT_APPROVED',
                      serviceApprovalObserved='NOT_APPROVED', reason='UNAUTHORIZED_API_CALL')
        return result
    if status != 200 or not isinstance(parsed, dict) or set(parsed) != {'OutBlock_1'}:
        return result
    rows = parsed['OutBlock_1']
    if not isinstance(rows, list) or not rows or any(not isinstance(row, dict) for row in rows):
        return result
    expected = {field['name'] for field in service['outputFields']}
    actual = set().union(*(set(row) for row in rows))
    if any(not re.fullmatch(r'[A-Z][A-Z0-9_]{0,63}', col) for col in actual):
        result['reason'] = 'UNSAFE_OR_UNDOCUMENTED_COLUMN_NAMES'
        return result
    result.update(columns=sorted(actual), rowCount=len(rows), serviceApprovalObserved='APPROVED_RESPONSE_OBSERVED')
    if any(set(row) != expected for row in rows):
        result.update(classification='SOURCE_SEMANTICS_UNRESOLVED', reason='DOCUMENTED_SCHEMA_CHANGED')
        return result
    identifiers = [f for f in ('ISU_CD', 'ISU_SRT_CD') if f in expected]
    result.update(securityIdentifierFields=identifiers,
                  marketFields=[f for f in ('MKT_TP_NM', 'MKT_NM') if f in expected])
    if any(any(not isinstance(row[f], str) or not row[f] for f in identifiers) for row in rows):
        result.update(classification='SOURCE_SEMANTICS_UNRESOLVED', reason='MISSING_SECURITY_IDENTIFIER')
        return result
    if 'BAS_DD' in expected:
        if any(row['BAS_DD'] != date.replace('-', '') for row in rows):
            result.update(classification='SOURCE_SEMANTICS_UNRESOLVED', reason='REQUESTED_HISTORICAL_DATE_NOT_RETURNED')
            return result
        result.update(effectiveHistoricalDate=date, historicalDateAccepted=True,
                      classification='HISTORICAL_ROWS_WITHOUT_INDUSTRY', reason='DATED_ROWS_NO_ECONOMIC_INDUSTRY_FIELD')
    else:
        # basDd and a service start date alone cannot establish historical semantics.
        result.update(classification='SOURCE_SEMANTICS_UNRESOLVED',
                      reason='REQUEST_BOUND_ROWS_WITHOUT_ASOF_DATE_OR_INDUSTRY')
    return result


def require_expansion_plan(plan, proof):
    if (not plan or plan.get('mode') != 'FROZEN_FULL_ACQUISITION'
            or not plan.get('frozenBeforeFirstRequest') or not plan.get('dates')
            or not plan.get('sourceCommit') or not plan.get('parserSchema')
            or not proof.get('historicalAsOfMembershipProven')):
        raise ValueError('PREEXISTING_FULL_ACQUISITION_PLAN_AND_MEMBERSHIP_PROOF_REQUIRED')
    # This reference-only feasibility implementation intentionally has no expansion path.
    raise ValueError('FULL_ACQUISITION_REQUIRES_SEPARATELY_REVIEWED_IMPLEMENTATION')
