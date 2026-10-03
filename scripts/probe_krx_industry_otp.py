"""Run only the preregistered four-date official KRX OTP -> CSV feasibility probe."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from http.cookiejar import CookieJar
import json
from pathlib import Path
import sys
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import build_opener, HTTPCookieProcessor, HTTPRedirectHandler, Request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import krx_industry_otp as K  # noqa: E402

PLAN = 'research_specs/kr-industry-membership-foundation-v1/krx-otp-feasibility-plan.json'
EXPECTED_PLAN_SHA256 = '1fd169376b2537c603eca2d18a4420addbc5a4ab5c90fb14c93ab8a684787373'
DATA = 'data/kr-industry-membership-foundation-v1/krx-otp-probe'
FREEZE_COMMIT = '6ab3555db4c4a0ae6d63654d9e608b22c0ca4f23'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def now():
    return datetime.now(timezone.utc).isoformat()


def run(plan_path, output):
    plan_raw = plan_path.read_bytes()
    if K.sha256(plan_raw) != EXPECTED_PLAN_SHA256:
        raise ValueError('FROZEN_OTP_PROBE_PLAN_CHANGED')
    plan = json.loads(plan_raw)
    output.mkdir(parents=True, exist_ok=False)
    (output / 'raw').mkdir()
    manifest = {'contract': 'KRX_INDUSTRY_OTP_FEASIBILITY_V1', 'planSha256': K.sha256(plan_raw),
                'preregistrationCommit': FREEZE_COMMIT, 'startedAt': now(), 'requests': [], 'dateResults': [],
                'historicalOutcomeComputed': False, 'outcomeFieldsInspected': False,
                'historicalMembershipAdmitted': False, 'expandedCollection': False}

    def checkpoint():
        # Raw objects are immutable; only an in-progress journal is rewritten until sealed.
        (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + '\n')

    def request(opener, url, params, headers, stage, profile, context):
        if len(manifest['requests']) >= plan['maxRequests']:
            raise ValueError('REQUEST_BUDGET_EXCEEDED')
        request_data = None if params is None else urlencode(params).encode('ascii')
        req = Request(url, data=request_data, headers=headers)
        entry = {'endpoint': url, 'method': req.get_method(), 'parameters': params or {},
                 'requestHeaders': headers, 'requestBodySha256': K.sha256(request_data) if request_data else None,
                 'requestTimestamp': now(), 'stage': stage, 'profile': profile, 'dateContext': context,
                 'responseHeaders': {}, 'status': None, 'transportError': None}
        manifest['requests'].append(entry)
        checkpoint()
        try:
            try:
                response = opener.open(req, timeout=plan['timeoutSeconds'])
            except HTTPError as error:
                response = error
            with response:
                entry['status'] = response.code
                entry['responseHeaders'] = {k: response.headers[k] for k in
                    ('Content-Type', 'Content-Disposition', 'Content-Length', 'Location', 'Server') if k in response.headers}
                raw = response.read(plan['maxBodyBytes'] + 1)
        except Exception as exc:
            entry['transportError'] = type(exc).__name__ + ': ' + str(exc)
            raw = b''
        entry['bodyBudgetExceeded'] = len(raw) > plan['maxBodyBytes']
        digest = K.sha256(raw)
        path = output / 'raw' / (digest + '.bin')
        if path.exists():
            if path.read_bytes() != raw:
                raise ValueError('RAW_HASH_COLLISION_OR_CHANGED_OBJECT')
        else:
            with path.open('xb') as stream:
                stream.write(raw)
        entry.update(responseTimestamp=now(), rawSha256=digest, rawBytes=len(raw), rawFile='raw/' + path.name)
        checkpoint()
        return raw, entry

    for profile in plan['profiles']:
        opener = build_opener(HTTPCookieProcessor(CookieJar()), NoRedirect())
        headers = {'User-Agent': plan['userAgent'], 'Referer': profile['referer'],
                   'Accept-Language': 'ko-KR,ko;q=0.9,en;q=0.5', 'Accept': '*/*'}
        request(opener, profile['bootstrapUrl'], None, headers, 'SESSION_BOOTSTRAP', profile['id'], None)
        post_headers = dict(headers, **{'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'})
        for date in plan['dates']:
            context = {k: date[k] for k in ('requestedDate', 'effectiveDate', 'substituted', 'substitutionReason')}
            context['market'] = date['otpParameters']['mktId']
            raw, otp_request = request(opener, plan['otpEndpoint'], date['otpParameters'], post_headers,
                                       'OTP', profile['id'], context)
            otp = None if otp_request['bodyBudgetExceeded'] else K.valid_otp(raw, otp_request['status'])
            otp_request['otpAccepted'] = otp is not None
            if otp is None:
                text, encoding = K.text_response(raw)
                otp_request.update(errorVerbatim=text, errorEncoding=encoding, otpFailureReason='NO_VALID_OTP')
            csv_raw, csv_request = request(opener, plan['csvEndpoint'], {'code': otp or ''}, post_headers,
                                           'CSV_EXCHANGE' if otp else 'CONTROL_NO_VALID_OTP', profile['id'], context)
            parsed = K.parse_classification_csv(csv_raw, csv_request['status'], context)
            if not otp or csv_request['bodyBudgetExceeded']:
                parsed.update(status='REJECTED', reason='NO_VALID_OTP' if not otp else 'BODY_BUDGET_EXCEEDED', classificationRows=[])
            csv_request['parsed'] = parsed
            manifest['dateResults'].append({'profile': profile['id'], **context, 'otpStatus': otp_request['status'],
                                           'otpAccepted': bool(otp), 'csvStatus': csv_request['status'],
                                           'csvStage': csv_request['stage'], 'status': parsed['status'], 'reason': parsed['reason'],
                                           'classificationRowsObtained': len(parsed['classificationRows']),
                                           'otpRawSha256': otp_request['rawSha256'], 'csvRawSha256': csv_request['rawSha256']})
            checkpoint()
    manifest.update(completedAt=now(), requestCount=len(manifest['requests']))
    manifest['realClassificationCsvObtained'] = any(r['classificationRowsObtained'] > 0 for r in manifest['dateResults'])
    manifest['feasibilityDecision'] = 'EXPANSION_PLAN_REQUIRED' if manifest['realClassificationCsvObtained'] else 'NO_USABLE_HISTORICAL_CSV_OBTAINED'
    checkpoint()
    return manifest


def verify(root=ROOT):
    root = Path(root)
    plan_raw = (root / PLAN).read_bytes()
    if K.sha256(plan_raw) != EXPECTED_PLAN_SHA256 or (root / PLAN).with_suffix('.sha256').read_text().strip() != EXPECTED_PLAN_SHA256:
        raise ValueError('FROZEN_OTP_PROBE_PLAN_CHANGED')
    plan = json.loads(plan_raw)
    manifest = json.loads((root / DATA / 'manifest.json').read_text())
    if manifest['planSha256'] != EXPECTED_PLAN_SHA256 or manifest.get('requestCount') != len(manifest['requests']) or manifest.get('requestCount') != 18:
        raise ValueError('INCOMPLETE_OR_CHANGED_PROBE')
    if manifest['preregistrationCommit'] != FREEZE_COMMIT or any(manifest[k] for k in
            ('historicalOutcomeComputed', 'outcomeFieldsInspected', 'historicalMembershipAdmitted', 'expandedCollection')):
        raise ValueError('PROBE_SCOPE_OR_FREEZE_CHANGED')
    for req in manifest['requests']:
        if Path(req['rawFile']) != Path('raw') / (req['rawSha256'] + '.bin'):
            raise ValueError('RAW_OBJECT_PATH_CHANGED')
        raw = (root / DATA / req['rawFile']).read_bytes()
        if K.sha256(raw) != req['rawSha256'] or len(raw) != req['rawBytes']:
            raise ValueError('KRX_RAW_RESPONSE_CHANGED')
        if req['bodyBudgetExceeded'] != (len(raw) > plan['maxBodyBytes']):
            raise ValueError('RAW_BODY_BUDGET_FLAG_CHANGED')
        data = None if req['method'] == 'GET' else urlencode(req['parameters']).encode('ascii')
        if req['requestBodySha256'] != (K.sha256(data) if data else None):
            raise ValueError('REQUEST_BODY_CHANGED')
    # Calendar dates are checked against the existing pinned session contract, not source availability.
    from pipeline.replay_calendar import sessions, CALENDAR_VERSION
    if plan['calendarVersion'] != CALENDAR_VERSION or K.sha256((root / 'pipeline/replay_calendar.py').read_bytes()) != plan['calendarSourceSha256']:
        raise ValueError('PINNED_KR_CALENDAR_CHANGED')
    trading_dates = [str(d.date()) for d in sessions('2014-12-01', '2026-09-01', 'KR')]
    wanted_results = []
    pos = 0
    for profile in plan['profiles']:
        bootstrap = manifest['requests'][pos]
        if bootstrap['stage'] != 'SESSION_BOOTSTRAP' or bootstrap['endpoint'] != profile['bootstrapUrl'] or bootstrap['parameters'] or bootstrap['method'] != 'GET':
            raise ValueError('BOOTSTRAP_CHANGED')
        pos += 1
        for date in plan['dates']:
            context = K.probe_date(date['requestedDate'], trading_dates)
            if any(date[k] != v for k, v in context.items()):
                raise ValueError('UNRECORDED_PROBE_DATE_SUBSTITUTION')
            context['market'] = date['otpParameters']['mktId']
            otp_req, csv_req = manifest['requests'][pos:pos+2]
            pos += 2
            if otp_req['endpoint'] != plan['otpEndpoint'] or otp_req['parameters'] != date['otpParameters'] or otp_req['stage'] != 'OTP':
                raise ValueError('OTP_REQUEST_CHANGED')
            otp_raw = (root / DATA / otp_req['rawFile']).read_bytes()
            otp = None if otp_req['bodyBudgetExceeded'] else K.valid_otp(otp_raw, otp_req['status'])
            stage = 'CSV_EXCHANGE' if otp else 'CONTROL_NO_VALID_OTP'
            if csv_req['endpoint'] != plan['csvEndpoint'] or csv_req['parameters'] != {'code': otp or ''} or csv_req['stage'] != stage:
                raise ValueError('CSV_EXCHANGE_CHANGED')
            csv_raw = (root / DATA / csv_req['rawFile']).read_bytes()
            parsed = K.parse_classification_csv(csv_raw, csv_req['status'], context)
            if not otp or csv_req['bodyBudgetExceeded']:
                parsed.update(status='REJECTED', reason='NO_VALID_OTP' if not otp else 'BODY_BUDGET_EXCEEDED', classificationRows=[])
            if otp_req['otpAccepted'] != (otp is not None):
                raise ValueError('OTP_ADMISSION_CHANGED')
            if csv_req['parsed'] != parsed:
                raise ValueError('CSV_PARSER_RESULT_CHANGED')
            wanted_results.append({'profile': profile['id'], **context, 'otpStatus': otp_req['status'], 'otpAccepted': bool(otp),
                                   'csvStatus': csv_req['status'], 'csvStage': stage, 'status': parsed['status'], 'reason': parsed['reason'],
                                   'classificationRowsObtained': len(parsed['classificationRows']),
                                   'otpRawSha256': otp_req['rawSha256'], 'csvRawSha256': csv_req['rawSha256']})
    for req in manifest['requests']:
        path = Path(req['rawFile'])
        if path != Path('raw') / (req['rawSha256'] + '.bin'):
            raise ValueError('RAW_OBJECT_PATH_CHANGED')
        raw = (root / DATA / path).read_bytes()
        if K.sha256(raw) != req['rawSha256'] or len(raw) != req['rawBytes']:
            raise ValueError('KRX_RAW_RESPONSE_CHANGED')
        profile = next(p for p in plan['profiles'] if p['id'] == req['profile'])
        if req['requestHeaders']['Referer'] != profile['referer'] or req['requestHeaders']['User-Agent'] != plan['userAgent']:
            raise ValueError('KRX_REQUEST_HEADERS_CHANGED')
        if req['stage'] != 'SESSION_BOOTSTRAP' and (req['method'] != 'POST' or req['dateContext'] not in [{k: r[k] for k in ('requestedDate', 'effectiveDate', 'substituted', 'substitutionReason', 'market')} for r in wanted_results]):
            raise ValueError('KRX_DATE_CONTEXT_CHANGED')
    if wanted_results != manifest['dateResults'] or manifest['realClassificationCsvObtained'] != any(r['classificationRowsObtained'] for r in wanted_results):
        raise ValueError('PROBE_RESULT_CHANGED')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    if args.verify:
        result = verify()
    else:
        if args.output is None:
            raise ValueError('FRESH_OUTPUT_REQUIRED')
        result = run(ROOT / PLAN, args.output)
    print(result['feasibilityDecision'])
