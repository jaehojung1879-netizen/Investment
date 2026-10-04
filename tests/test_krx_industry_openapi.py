import copy
import hashlib
import json
from pathlib import Path
import re
import urllib.error

import pytest

from pipeline import krx_industry_openapi as K
from scripts import probe_krx_industry_openapi as P

ROOT = Path(__file__).resolve().parents[1]
KEY = 'SYNTHETIC_SECRET_NEVER_PERSIST_12345'


def service(index=0):
    return P.frozen_plan()[0]['services'][index]


def body(s, **values):
    row = {f['name']: 'SYNTHETIC_VALUE' for f in s['outputFields']}
    row.update(values)
    return json.dumps({'OutBlock_1': [row]}).encode()


def summarize(raw, s=None, date='2015-01-02', status=200):
    return K.summarize_response(raw, status, 'application/json', s or service(), date, KEY)


def test_header_auth_never_in_url_and_redirects_forbidden():
    request = K.request_for(K.SERVICES[0], K.DATES[0], KEY)
    assert request.get_header('Auth_key') == KEY
    assert KEY not in request.full_url
    assert request.full_url.endswith('?basDd=20150102')
    assert K.NoRedirect().redirect_request(request, None, 302, '', {}, 'https://other.invalid') is None


@pytest.mark.parametrize('raw', [KEY.encode(), json.dumps({'OutBlock_1': [{'ISU_NM': KEY}]}).encode(),
                                __import__('base64').b64encode(KEY.encode())])
def test_credential_rejected_before_hashing_or_persisting(raw, monkeypatch):
    s = service()
    monkeypatch.setattr(K.hashlib, 'sha256', lambda *_: pytest.fail('credential was hashed'))
    with pytest.raises(K.CredentialSafetyError) as error:
        summarize(raw, s)
    assert KEY not in str(error.value)


def test_sensitive_account_or_auth_response_is_not_retained():
    for field in ('AUTH_KEY', 'account_number', 'password'):
        with pytest.raises(K.CredentialSafetyError):
            summarize(json.dumps({field: 'SYNTHETIC'}).encode())


def test_success_and_service_start_date_are_not_pit_or_industry():
    s = service()
    assert s['serviceStartDate'] == '2010-01-04'
    assert next(f['label'] for f in s['outputFields'] if f['name'] == 'SECT_TP_NM') == '소속부'
    result = summarize(body(s), s)
    assert result['classification'] == 'SOURCE_SEMANTICS_UNRESOLVED'
    assert result['effectiveHistoricalDate'] is None
    assert not result['historicalDateAccepted']
    assert not result['historicalAsOfMembershipProven']
    assert result['industryFields'] == []
    assert result['membershipRowsAdmitted'] == 0


def test_dated_trading_schema_projects_no_values_or_outcomes():
    s = service(3)
    raw = body(s, BAS_DD='20150102', TDD_CLSPRC='DO_NOT_INSPECT', FLUC_RT='NO_OUTCOME_ACCESS')
    result = summarize(raw, s)
    assert result['classification'] == 'HISTORICAL_ROWS_WITHOUT_INDUSTRY'
    assert result['effectiveHistoricalDate'] == K.DATES[0]
    assert not result['historicalAsOfMembershipProven']
    assert 'DO_NOT_INSPECT' not in json.dumps(result)
    assert 'NO_OUTCOME_ACCESS' not in json.dumps(result)
    assert 'SYNTHETIC_VALUE' not in json.dumps(result)
    assert result['responseSha256'] == hashlib.sha256(raw).hexdigest()


def test_current_rows_cannot_backfill_and_unsupported_date_fails_closed():
    s = service(3)
    result = summarize(body(s, BAS_DD='20260901'), s)
    assert result['reason'] == 'REQUESTED_HISTORICAL_DATE_NOT_RETURNED'
    assert result['membershipRowsAdmitted'] == 0
    with pytest.raises(ValueError, match='OUTSIDE_FROZEN_PROBE'):
        K.request_for(K.SERVICES[0], '2010-01-04', KEY)


def test_schema_changes_fail_closed_even_if_industry_field_appears():
    s = service()
    result = summarize(body(s, INDUSTRY_NM='SYNTHETIC_INDUSTRY'), s)
    assert result['reason'] == 'DOCUMENTED_SCHEMA_CHANGED'
    assert result['membershipRowsAdmitted'] == 0
    assert not result['historicalAsOfMembershipProven']


@pytest.mark.parametrize('raw,status,classification', [
    (b'Unauthorized API Call', 401, 'AUTHENTICATED_SERVICE_NOT_APPROVED'),
    (b'{"respMsg":"Unauthorized API Call"}', 200, 'AUTHENTICATED_SERVICE_NOT_APPROVED'),
    (b'Unauthorized Key', 401, 'NO_USABLE_RESPONSE'),
    (b'<html>error</html>', 200, 'NO_USABLE_RESPONSE'),
    (b'{"OutBlock_1":[]}', 200, 'NO_USABLE_RESPONSE'),
    (b'{}', 403, 'NO_USABLE_RESPONSE')])
def test_errors_do_not_promote_or_conflate_key_and_service_approval(raw, status, classification):
    result = summarize(raw, status=status)
    assert result['classification'] == classification
    assert not result['historicalAsOfMembershipProven']
    assert result['membershipRowsAdmitted'] == 0


def test_frozen_plan_and_document_sources_reproduce_offline():
    plan, digest = P.frozen_plan()
    assert digest == hashlib.sha256((ROOT / P.PLAN).read_bytes()).hexdigest()
    assert plan['preservedResearchNameDates'] == 610 * 120
    assert plan['frozenCriteriaSha256'] == hashlib.sha256(
        (ROOT / 'research_specs/kr-industry-membership-foundation-v1/criteria.json').read_bytes()).hexdigest()
    for name, value in [('maxRequests', 17), ('maxConcurrency', 2), ('fullHistoryExpansionAuthorized', True)]:
        changed = copy.deepcopy(plan)
        changed[name] = value
        with pytest.raises(ValueError):
            K.validate_plan(changed)


def test_full_history_expansion_requires_preexisting_plan_and_proof():
    with pytest.raises(ValueError, match='PREEXISTING_FULL_ACQUISITION_PLAN'):
        K.require_expansion_plan(None, {'historicalAsOfMembershipProven': False})
    plan, _ = P.frozen_plan()
    with pytest.raises(ValueError):
        K.require_expansion_plan(plan, {'historicalAsOfMembershipProven': True})


def test_unauthenticated_pr_cannot_execute(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('GITHUB_EVENT_NAME', 'pull_request')
    monkeypatch.setenv('AUTH_KEY', KEY)
    with pytest.raises(ValueError, match='ISOLATED_MANUAL_WORKFLOW_REQUIRED'):
        P.execute()
    assert list(tmp_path.iterdir()) == []


def test_manual_transport_errors_never_log_secret_or_exception(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('GITHUB_EVENT_NAME', 'workflow_dispatch')
    monkeypatch.setenv('KRX_INDUSTRY_MANUAL_PROBE', '1')
    monkeypatch.setenv('GITHUB_SHA', 'a' * 40)
    monkeypatch.setenv('GITHUB_RUN_ID', '123')
    monkeypatch.setenv('AUTH_KEY', KEY)
    class FakeOpener:
        def open(self, request, timeout):
            raise urllib.error.URLError(KEY)
    monkeypatch.setattr(P.urllib.request, 'build_opener', lambda *_: FakeOpener())
    monkeypatch.setattr(P.time, 'sleep', lambda *_: None)
    P.execute()
    captured = capsys.readouterr()
    assert KEY not in captured.out + captured.err
    raw = (tmp_path / P.OUTPUT).read_bytes()
    assert KEY.encode() not in raw
    result = json.loads(raw)
    assert result['requestCount'] == 16
    assert result['admittedMembershipRows'] == 0
    assert (tmp_path / (P.OUTPUT + '.sha256')).read_text().strip() == hashlib.sha256(raw).hexdigest()


def test_workflow_secret_is_exact_manual_step_only_and_upload_is_sanitized():
    text = (ROOT / '.github/workflows/probes.yml').read_text()
    job = re.split(r'\n  [a-zA-Z0-9_-]+:\n', text.split('\n  krx-industry-openapi:\n', 1)[1], maxsplit=1)[0]
    assert "if: github.event_name == 'workflow_dispatch' && inputs.probe == 'krx-industry-openapi'" in job
    assert "inputs.probe != 'krx-industry-openapi'" in text.split('\n  krx-industry-openapi:')[0]
    assert 'persist-credentials: false' in job
    assert job.count('${{ secrets.KRX_API_KEY }}') == 1
    assert 'AUTH_KEY: ${{ secrets.KRX_API_KEY }}' in job
    assert job.index('      - name: Read-only') < job.index('AUTH_KEY:') < job.index('      - name: Retain')
    assert 'args' not in job and 'tee' not in job and 'probe.log' not in job
    assert 'krx-openapi-source-metadata.json.sha256' in job
    assert 'contents: write' not in job
