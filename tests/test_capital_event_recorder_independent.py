"""Independent positive and adversarial probes of the inherited recorder."""
import json

import pytest

from research.kr_capital_event_prospective_v1 import recorder as R
from research.corporate_event_readiness_v1.cohort.identity import PitTop300


def current(title='현금ㆍ현물배당결정', **kw):
    return {'rcept_no': '20250203000001', 'rcept_dt': '20250203', 'corp_code': 'ISSUER',
            'stock_code': '000001', 'report_nm': title, 'family': 'DIVIDEND', **kw}


def prior(title='현금ㆍ현물배당결정', **kw):
    return {'rcept_no': '20240201000001', 'stock_code': '000001', 'report_nm': title,
            'dividendClass': '결산배당', 'dividendKind': '현금배당', 'recordDate': '2023-12-31',
            'dpsCommonKrw': '100', **kw}


def collect(monkeypatch, rows=None, previous=None, parsed=None):
    rows = [current()] if rows is None else rows
    parsed = {'dividendClass': '결산배당', 'dividendKind': '현금배당',
              'dpsCommonKrw': '125', 'recordDate': '2024-12-31', **(parsed or {})}
    monkeypatch.setattr(R, 'receipt_days_for', lambda *_: ['2025-02-03'])
    monkeypatch.setattr(R, 'day_rows', lambda *_: (rows, []))
    monkeypatch.setattr(R, '_body_hash', lambda *_: (b'invented filing', 'a' * 64))
    monkeypatch.setattr(R, 'parse_dividend', lambda _: parsed)
    pit = PitTop300({'2023-12-01': {'000001': 'A'}, '2024-12-02': {'000001': 'A'},
                     '2025-01-02': {'000001': 'A'}, '2025-03-04': {'000001': 'A'}})
    dates_read = []

    def shares(pit, code, day):
        dates_read.append(day)
        assert day <= '2025-02-03'
        return 100

    monkeypatch.setattr(R.HY, '_listed', shares)
    events, observations, sources = R.collect('2025-02-04', client=None, pit=pit,
                                             prior_rows=[prior()] if previous is None else previous,
                                             sessions=['2025-02-03', '2025-02-04', '2025-02-05'])
    return events, observations, dates_read


def test_normal_common_cash_increase_is_detected_and_future_dps_cannot_change_it(monkeypatch):
    events, _, reads = collect(monkeypatch)
    assert len(events) == 1 and events[0]['candidate'] == 'F1_DIVIDEND_INCREASE_LONG'
    assert events[0]['terms']['dpsChangePct'] == 25
    assert events[0]['terms']['annualComparison']['fiscalYear'] is None
    assert reads and max(reads) <= '2025-02-03'
    poisoned, _, _ = collect(monkeypatch, previous=[prior(), prior(rcept_no='20260203000001', dpsCommonKrw='999999')])
    assert poisoned == events


def test_subsidiaries_are_excluded_from_current_and_comparison_base(monkeypatch):
    title = '현금ㆍ현물배당결정(자회사의 주요경영사항)'
    assert collect(monkeypatch, rows=[current(title)])[0] == []
    assert collect(monkeypatch, previous=[prior(title)])[0] == []


def test_record_date_shift_is_explicitly_blocked_and_never_called_a_fiscal_year(monkeypatch):
    events, observations, reads = collect(monkeypatch, parsed={'recordDate': '2025-03-14'},
                                         previous=[prior(rcept_no='20250120000001', recordDate='2024-12-31')])
    assert events == [] and reads == []
    assert observations[0]['comparisonBlocked'] == 'FISCAL_YEAR_OR_RECORD_DATE_SHIFT_UNRESOLVED'


def test_same_day_and_future_receipt_payload_is_refused(monkeypatch):
    with pytest.raises(ValueError, match='NOT_PUBLIC_BEFORE_SIGNAL'):
        collect(monkeypatch, rows=[current(rcept_no='20250204000001', rcept_dt='20250204')])


def test_f2_preserves_title_decision_and_does_not_claim_actual_dilution(monkeypatch):
    events, _, _ = collect(monkeypatch, rows=[current('주요사항보고서(교환사채권발행결정)', family='EB')])
    assert events[0]['candidate'] == 'F2_DILUTION_AVOID'
    assert events[0]['dilutionEvidence']['economicDilution'] == 'UNVERIFIED'


def test_forged_receipt_evidence_and_nonzero_cash_cannot_pass_validation():
    from pipeline import prospective_receipt_core as C
    receipt = R.session_receipt('2025-02-04', [], [], [], spec_sha256='a' * 64,
                                 created_at_utc='2025-02-04T10:00:00Z', mode='DRY_RUN')
    for changes, reason in [({'evidenceClass': 'VERIFIED'}, 'EVIDENCE_CLASS'),
                            ({'book': {**receipt['book'], 'cashWeight': 0.5}}, 'CANNOT_HOLD')]:
        bad = {**receipt, **changes}
        bad.pop('receiptSha256')
        with pytest.raises(ValueError, match=reason):
            R.validate(bad)
    assert receipt['receiptSha256'] == C.receipt_digest(receipt)


def test_v2_cannot_reuse_v1_authorization_and_default_remains_dry_run():
    assert R.AUTHORIZATION.name == 'AUTHORIZATION-v2-prospective-recording.json'
    assert not R.AUTHORIZATION.exists()
    with pytest.raises(ValueError, match='NO_REGISTERED_AUTHORIZATION'):
        R.verify()
    spec = json.loads(R.SPEC.read_text())
    assert spec['specVersion'] == 2 and spec['operationalStatus'] == 'NOT_AUTHORIZED_INSTALLATION_NOT_VERIFIED'


def test_late_publication_refuses_before_any_git_push(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(R.subprocess, 'run', lambda *a, **k: calls.append(a))

    def closed():
        raise ValueError('PUBLICATION_WINDOW_CLOSED')

    with pytest.raises(ValueError, match='WINDOW_CLOSED'):
        R.push_and_verify(tmp_path, {}, before_publish=closed)
    assert not calls


def test_direct_real_remote_push_helper_cannot_bypass_owner_approval(monkeypatch, tmp_path):
    receipt = R.session_receipt('2025-02-04', [], [], [], spec_sha256='a' * 64,
                                 created_at_utc='2025-02-04T10:00:00Z', mode='LIVE',
                                 authorization={'authorizationSha256': 'b' * 64}, code_commit='c' * 40)
    monkeypatch.setattr(R, 'git', lambda *a, **k: 'https://github.com/jaehojung1879-netizen/Investment.git')
    with pytest.raises(ValueError, match='NO_REGISTERED_AUTHORIZATION'):
        R.publication_guard(tmp_path, receipt)


def test_local_test_remote_refuses_live_receipts_even_with_synthetic_provenance(monkeypatch, tmp_path):
    receipt = R.session_receipt('2025-02-04', [], [], [], spec_sha256='a' * 64,
                                 created_at_utc='2025-02-04T10:00:00Z', mode='LIVE',
                                 authorization={'authorizationSha256': 'b' * 64}, code_commit='c' * 40)
    monkeypatch.setattr(R, 'git', lambda *a, **k: str(tmp_path))
    with pytest.raises(ValueError, match='PUBLICATION_REMOTE_OR_RECEIPT_MODE_REFUSED'):
        R.publication_guard(tmp_path, receipt)
