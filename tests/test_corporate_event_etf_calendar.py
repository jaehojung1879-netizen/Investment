"""Synthetic close/volume checks and fixed date reconciliation, no real returns."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from research.corporate_event_readiness_v1.etf.source import (
    inspect_source, project_price_quality, reconcile_price_sessions,
)

ROOT = Path(__file__).resolve().parents[1] / 'research/corporate_event_readiness_v1/etf'


def projection(dates):
    return json.dumps({'dates': dates, 'originalSha256': 'a' * 64}).encode()


def test_matching_calendar_remains_only_input_label_verification():
    r = reconcile_price_sessions(projection(['2026-01-06', '2026-01-05']),
                                 expected_sessions=['2026-01-05', '2026-01-06'],
                                 requested_through='2026-01-06', calendar_id='SYN_CALENDAR')
    assert r['status'] == 'REPOSITORY_CALENDAR_LABELS_MATCH'
    assert not r['officialSessionCalendarCertified'] and not r['priceValuesValidated']
    assert not r['economicEmpiricismReady'] and not r['outcomeExecutionAuthorized']


def test_mutable_dated_endpoint_cannot_leak_later_observations():
    r = reconcile_price_sessions(projection(['2026-01-07', '2026-01-06']),
                                 expected_sessions=['2026-01-05', '2026-01-06'],
                                 requested_through='2026-01-06', calendar_id='SYN_CALENDAR')
    assert r['status'] == 'BLOCKED'
    assert r['observationsAfterRequestedCutoff'] == ['2026-01-07']
    assert r['missingSessions'] == ['2026-01-05']
    assert 'OBSERVATIONS_AFTER_REQUESTED_CUTOFF' in r['blockers']


def test_calendar_requires_unique_ordered_independent_labels():
    with pytest.raises(ValueError, match='INDEPENDENT_ORDERED_CALENDAR'):
        reconcile_price_sessions(projection(['2026-01-06']), expected_sessions=['2026-01-06'] * 2,
                                 requested_through='2026-01-06', calendar_id='SYN')


class Sheet:
    nrows = 6

    def __init__(self, close='100', volume='1'):
        self.close, self.volume = close, volume

    def cell_value(self, row, col):
        headers = {(0, 0): 'KODEX 단기채권 기준가격', (2, 0): '일자', (2, 1): '거래가격(원)',
                   (3, 1): '종가', (3, 4): '거래량', (2, 5): '펀드기준가격(원)', (2, 8): '과표기준가(원)'}
        if (row, col) in headers:
            return headers[row, col]
        if row >= 4:
            # Price change, NAV and return cells must never be selected.
            assert col in (0, 1, 4), 'OUTCOME_OR_NAV_CELL_SELECTED'
            return {0: ['20260106', '20260105'][row - 4], 1: self.close, 4: self.volume}[col]
        raise AssertionError((row, col))


@pytest.mark.parametrize('close,volume,expected', [
    ('100', '0', 'zeroReportedVolumeDates'), ('NaN', '1', 'invalidCloseDates'),
    ('0', '1', 'invalidCloseDates'), ('100', 'Infinity', 'invalidVolumeDates'),
    ('100', '1.5', 'invalidVolumeDates'), ('100', '-1', 'invalidVolumeDates'),
])
def test_price_quality_uses_no_nav_or_returns(monkeypatch, close, volume, expected):
    sheet = Sheet(close, volume)
    monkeypatch.setitem(sys.modules, 'xlrd', SimpleNamespace(
        open_workbook=lambda **kwargs: SimpleNamespace(sheet_by_index=lambda index: sheet)))
    r = project_price_quality(b'SYNTHETIC_XLS_ONLY')
    assert r[expected] == ['2026-01-06', '2026-01-05']
    assert r['returnsComputed'] == 0 and not r['numericPriceValuesRetained']
    assert not r['navSelected'] and not r['tradabilityCertified']


def test_taxable_distribution_cannot_exceed_gross_cash():
    payload = json.loads((ROOT / 'issuer-projection.json').read_text())
    payload['info']['divideList'][0]['TAX_DIVID_A'] = '999999'
    r = inspect_source(json.dumps(payload).encode())
    assert r['quarantine'][0]['reason'] == 'TAXABLE_AMOUNT_EXCEEDS_GROSS'
    assert not r['economicEmpiricismReady']


def test_retained_date_delta_reproduces_cutoff_failure_without_prices():
    from hashlib import sha256
    p = json.loads((ROOT / 'source-verification-v2.json').read_text())
    delta = p['dateProjectionDelta']
    original = json.loads((ROOT / delta['basePath']).read_bytes())
    original['dates'] = sorted(set(original['dates']) - set(delta['removedDates'])
                               | set(delta['addedDates']), reverse=True)
    original['originalSha256'] = delta['replacementOriginalSha256']
    raw = (json.dumps(original, ensure_ascii=False, sort_keys=True) + '\n').encode()
    assert sha256(raw).hexdigest() == delta['replacementProjectionSha256']
    r = reconcile_price_sessions(raw, expected_sessions=sorted(
        json.loads((ROOT / delta['basePath']).read_bytes())['dates']),
        requested_through='2026-11-04', calendar_id='SYN_REPLAY_LABEL_ORACLE_NOT_OFFICIAL_CALENDAR')
    assert r['observationsAfterRequestedCutoff'] == ['2026-11-05', '2026-11-06']
    assert r['status'] == 'BLOCKED'
