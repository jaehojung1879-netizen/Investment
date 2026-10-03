import json
import shutil
from pathlib import Path
import pytest
from pipeline import krx_industry_otp as K
from pipeline import kr_industry_membership as M
from scripts import probe_krx_industry_otp as P
from scripts import build_kr_industry_membership_foundation as B

ROOT = Path(__file__).resolve().parents[1]
CONTEXT = {'requestedDate': '2020-01-02', 'effectiveDate': '2020-01-02', 'market': 'STK',
           'substituted': False, 'substitutionReason': None}


@pytest.mark.parametrize('body,status', [(b'<html>LOGOUT</html>', 200), (b'LOGOUT', 200),
    (b'{"error":"denied"}', 200), (b'Forbidden', 403), (b'', 200),
    (b'<html>\xc0\xaf\xc8\xbf\xc7\xcf\xc1\xf6 \xbe\xca\xc0\xba \xbf\xe4\xc3\xbb</html>', 200)])
def test_errors_never_become_otp_or_classifications(body, status):
    assert K.valid_otp(body, status) is None
    parsed = K.parse_classification_csv(body, status, CONTEXT)
    assert parsed['status'] == 'REJECTED'
    assert parsed['classificationRows'] == []
    assert not parsed['historicalMembershipAdmitted']


def test_http_error_with_csv_header_is_still_not_data():
    raw = '종목코드,종목명,업종명\n000001,합성회사,합성업종\n'.encode('cp949')
    assert K.parse_classification_csv(raw, 403, CONTEXT)['classificationRows'] == []


def test_only_requested_fields_are_projected_and_missing_industry_is_unknown():
    raw = ('종목코드,종목명,업종명,시장구분,기준일자,등락률,종가\n'
           '000001,합성회사,,KOSPI,20200102,DO_NOT_INSPECT_PRICE_PERFORMANCE,SYNTHETIC_PRICE\n'
           '000002,합성회사2,합성업종,KOSPI,20200102,DO_NOT_INSPECT_PRICE_PERFORMANCE,SYNTHETIC_PRICE\n').encode('cp949')
    result = K.parse_classification_csv(raw, 200, CONTEXT)
    assert result['status'] == 'CLASSIFICATION_CSV_REVIEW_REQUIRED'
    assert result['classificationRows'][0]['classificationStatus'] == 'UNKNOWN'
    assert result['classificationRows'][1]['classificationStatus'] == 'REPORTED_CLASSIFICATION_REVIEW_REQUIRED'
    assert not result['historicalMembershipAdmitted']
    assert 'DO_NOT_INSPECT_PRICE_PERFORMANCE' not in json.dumps(result)
    assert 'SYNTHETIC_PRICE' not in json.dumps(result)
    assert result['dateEvidence'] == 'CSV_DATE_MATCHES_REQUEST'


def test_date_context_is_not_invented_or_current_backfilled():
    raw = '종목코드,종목명,업종명,기준일자\n000001,합성회사,합성업종,20260901\n'.encode()
    assert K.parse_classification_csv(raw, 200, CONTEXT)['reason'] == 'REQUESTED_DATE_CONFLICT'
    raw = '종목코드,종목명,업종명\n000001,합성회사,합성업종\n'.encode()
    parsed = K.parse_classification_csv(raw, 200, CONTEXT)
    assert parsed['dateEvidence'] == 'REQUEST_BOUND_QUERY_ONLY'
    assert not parsed['historicalMembershipAdmitted']
    assert M.admit_assignment({'source_kind': 'CURRENT_PROFILE'}, raw, {})[0] is None


def test_substitution_is_explicit_and_strictly_prior_if_closed():
    days = ['2019-12-30', '2020-01-02']
    assert K.probe_date('2020-01-01', days) == {'requestedDate': '2020-01-01', 'effectiveDate': '2019-12-30',
        'substituted': True, 'substitutionReason': 'IMMEDIATELY_PRIOR_KR_SESSION'}
    assert not K.probe_date('2020-01-02', days)['substituted']
    with pytest.raises(ValueError, match='PRIOR_KR_SESSION_MISSING'):
        K.probe_date('2019-12-29', days)


def test_missing_schema_ragged_and_duplicate_security_codes_fail_closed():
    for raw in ['종목코드,종목명\n000001,합성회사\n',
                '종목코드,종목명,업종명\n000001,합성회사\n',
                '종목코드,종목명,업종명\n000001,합성회사,합성업종\n000001,다른회사,다른업종\n']:
        assert K.parse_classification_csv(raw.encode(), 200, CONTEXT)['status'] == 'REJECTED'


def test_probe_is_offline_reproducible_and_hash_changes_are_refused(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Offline verification cannot contact a source')
    monkeypatch.setattr(P, 'build_opener', forbidden)
    result = P.verify(ROOT)
    assert result['requestCount'] <= 18
    assert {r['requestedDate'] for r in result['dateResults']} == {'2015-01-02', '2020-01-02', '2023-01-02', '2026-09-01'}
    assert not result['realClassificationCsvObtained']
    assert not result['historicalMembershipAdmitted']
    for rel in [P.PLAN, str(Path(P.PLAN).with_suffix('.sha256')), 'pipeline/replay_calendar.py']:
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, target)
    shutil.copytree(ROOT / P.DATA, tmp_path / P.DATA)
    req = result['requests'][0]
    (tmp_path / P.DATA / req['rawFile']).write_bytes(b'changed source')
    with pytest.raises(ValueError, match='KRX_RAW_RESPONSE_CHANGED'):
        P.verify(tmp_path)


def test_failed_probe_does_not_promote_or_shrink_universe():
    mapping, audit, signals = B.build()
    assert not mapping['memberships']
    assert audit['decision'] == 'DATA_FOUNDATION_INSUFFICIENT'
    assert audit['selectedTaxonomy'] is None
    assert audit['researchUniverseNameDates'] == 610 * 120
    for a in signals['candidateAudits']:
        for d in a['dates']:
            assert d['universeCount'] == 120 and len(d['missingSecurityIds']) == 120
    criteria = B.read(ROOT, B.CRITERIA)
    assert criteria['candidateTaxonomiesInPriorityOrder'] == ['KRX_NATIVE_INDUSTRY_AS_PUBLISHED', 'KSIC_DIVISION_2_DIGIT', 'KSIC_GROUP_3_DIGIT']
    assert M.select_taxonomy(signals['candidateAudits'], criteria) is None
