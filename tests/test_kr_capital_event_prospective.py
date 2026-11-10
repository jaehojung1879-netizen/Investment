"""The separate P2/K7 prospective study: definitions, refusal without authorization, and receipt rules."""
import json

import pytest

from pipeline import prospective_receipt_core as core
from research.kr_capital_event_prospective_v1 import recorder as R


def _row(no, code, fy, dps, title='현금ㆍ현물배당결정', **kw):
    return {'rcept_no': no, 'stock_code': code, 'dividendClass': '결산배당', 'dividendKind': '현금배당',
            'dpsCommonKrw': str(dps), 'recordDate': f'{fy}-12-31', 'report_nm': title, **kw}


def test_prior_year_base_is_the_issuers_own_original_decision():
    rows = [_row('1', 'A', 2024, 1000, title='현금ㆍ현물배당결정(자회사의 주요경영사항)'), _row('2', 'A', 2024, 500),
            _row('3', 'A', 2024, 700, amendment=True), _row('4', 'B', 2024, '-')]
    assert R.prior_year_end_dps(rows) == {('A', 2024): {'dps': 500.0, 'recordDate': '2024-12-31'}}


def test_no_authorization_means_no_live_recording():
    assert not R.AUTHORIZATION.exists() or R.verify()['specSha256']
    if not R.AUTHORIZATION.exists():
        with pytest.raises(ValueError, match='NO_REGISTERED_AUTHORIZATION'):
            R.verify()


def test_pinned_code_matches_the_spec_and_ledger_is_separate():
    spec = json.loads(R.SPEC.read_text(encoding='utf-8'))
    assert set(spec['codeSha256']) == set(R.PINNED_CODE)
    assert all(R.hashlib.sha256((R.REPO / p).read_bytes()).hexdigest() == h for p, h in spec['codeSha256'].items())
    assert spec['ledger'] == R.LEDGER_RELATIVE and 'kr-corporate-information-events-v1' not in R.LEDGER_RELATIVE


def _receipt(mode='DRY_RUN', **kw):
    return R.session_receipt('2026-11-11', [], [], [], spec_sha256='a' * 64, created_at_utc='2026-11-11T10:00:00+00:00',
                             mode=mode, **kw)


def test_receipt_holds_no_names_and_a_dry_run_is_never_prospective_evidence():
    r = _receipt()
    assert r['evidenceClass'] == R.DRY_RUN_CLASS and r['book']['signalNames'] == 0 and r['book']['etfWeight'] == 1.0
    live = _receipt('LIVE', authorization={'authorizationSha256': 'b' * 64}, code_commit='c' * 40)
    assert live['evidenceClass'] == core.EVIDENCE_CLASS
    bad = {**r, 'book': {**r['book'], 'signalNames': 1}}
    bad.pop('receiptSha256')
    with pytest.raises(ValueError, match='UNVERIFIED_CANDIDATES_CANNOT_HOLD_NAMES'):
        R.validate(bad)
    with pytest.raises(ValueError, match='LIVE_REQUIRES_AUTHORIZATION'):
        _receipt('LIVE')


def test_a_receipt_cannot_be_backdated_or_written_before_the_close():
    kw = dict(signal_date='2026-11-11', merged_at_utc='2026-11-10T06:00:00+00:00')
    with pytest.raises(ValueError, match='BEFORE_SIGNAL_CLOSE'):
        core.check_timing(created_at_utc='2026-11-11T08:59:00+00:00', now_utc='2026-11-11T08:59:00+00:00', **kw)
    with pytest.raises(ValueError, match='BACKDATED'):
        core.check_timing(created_at_utc='2026-11-12T00:00:00+00:00', now_utc='2026-11-12T00:00:00+00:00', **kw)
    with pytest.raises(ValueError, match='BEFORE_PROSPECTIVE_ELIGIBILITY'):
        core.check_timing(signal_date='2026-11-10', merged_at_utc='2026-11-10T06:00:00+00:00',
                          created_at_utc='2026-11-10T10:00:00+00:00', now_utc='2026-11-10T10:00:00+00:00')
    assert core.check_timing(created_at_utc='2026-11-11T10:00:00+00:00', now_utc='2026-11-11T10:00:00+00:00',
                             **kw).strftime('%Y-%m-%d') == '2026-11-12'
