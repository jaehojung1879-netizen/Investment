"""Synthetic arithmetic/absence regressions; no strategy engine or real outcome run."""
from copy import deepcopy
import hashlib
import importlib.util
import math
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location('portfolio_edge_forensics', Path(__file__).with_name('run.py'))
F = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(F)


def paired(a, b):
    dates = ['2018-12-28','2019-12-27','2020-12-25','2021-12-31'][:len(a)]
    return [[d, v] for d, v in zip(dates, a)], [[d, v] for d, v in zip(dates, b)]


def test_exact_arithmetic_jensen_identity_does_not_invent_alpha():
    a, b = paired([1, 1.1, 1], [1, 1, 1])
    rows = F.interval_data(a, b)
    d = F.decomposition(rows)
    assert d['arithmeticIntervalActiveAnnualizedPp'] > 0
    assert d['exactJensenDifferenceAnnualizedLogPoints'] < 0
    assert d['logGrowthGapAnnualizedLogPoints'] == pytest.approx(0, abs=1e-12)
    assert d['geometricGapPpFromLogIdentity'] == pytest.approx(0, abs=1e-12)
    assert d['jensenShareOfLogGapPct'] is None
    assert abs(d['identityResidualLogPoints']) < 1e-12


def test_scale_invariance_common_initial_capital_and_no_double_cost():
    a, b = paired([100, 110, 99], [50, 60, 55])
    before = deepcopy((a, b))
    x = F.summarize_intervals(F.interval_data(a, b))
    a1 = [[d, v/100] for d, v in a]
    b1 = [[d, v/50] for d, v in b]
    assert F.summarize_intervals(F.interval_data(a1, b1)) == pytest.approx(x)
    assert (a, b) == before
    assert x['candidateWealthFromOne'] == pytest.approx(.99)
    assert x['benchmarkWealthFromOne'] == pytest.approx(1.1)
    assert x['excessReturnPp'] == pytest.approx(-11)  # Percent, not fraction / 100x.


@pytest.mark.parametrize('bad', [None, 0, -1, True, float('nan'), float('inf'), '1'])
def test_missing_bad_nav_never_zero(bad):
    a, b = paired([1, 1.1], [1, 1])
    a[1][1] = bad
    with pytest.raises(ValueError, match='NAV'):
        F.interval_data(a, b)


def test_missing_duplicate_and_unordered_dates_fail_without_inner_join():
    a, b = paired([1, 1.1, 1.2], [1, 1.05, 1.1])
    with pytest.raises(ValueError, match='CALENDAR_MISMATCH'):
        F.interval_data(a, b[:2])
    for series in [a[:1]+a[:1]+a[2:], a[::-1]]:
        with pytest.raises(ValueError, match='DUPLICATE_OR_UNORDERED'):
            F.interval_data(series, b)
    a[1][0] = '2019-02-30'
    with pytest.raises(ValueError):
        F.interval_data(a, b)


def test_return_log_contribution_and_full_clock_identity():
    a, b = paired([1, 1.2, 1.32, 1.1], [1, 1.1, 1.21, 1.3])
    rows = F.interval_data(a, b)
    annual = [{'year': r['through'][:4], **F.summarize_intervals([r])} for r in rows]
    full = F.summarize_intervals(rows)
    assert math.fsum(y['logExcess'] for y in annual) == pytest.approx(full['logExcess'])
    assert full['candidateReturnPct'] == pytest.approx(10)
    assert full['benchmarkReturnPct'] == pytest.approx(30)
    assert full['relativeWealthReturnPct'] == pytest.approx((1.1/1.3-1)*100)
    assert full['cagrGapPp'] == pytest.approx(F.decomposition(rows)['geometricGapPpFromLogIdentity'])


def test_relative_gain_and_arithmetic_excess_can_have_opposite_signs():
    rows = [
        {'status':'MEASURED','start':'2020-01-01','observedEndDate':'2020-07-01',
         'candidateReturnPct':80,'benchmarkReturnPct':100,'excessReturnPp':-20,'relativeWealthReturnPct':-10},
        {'status':'MEASURED','start':'2021-01-01','observedEndDate':'2021-07-01',
         'candidateReturnPct':-40,'benchmarkReturnPct':-50,'excessReturnPp':10,'relativeWealthReturnPct':20},
    ]
    x = F.window_summary(rows)
    assert x['meanRelativeWealthReturnPct'] == pytest.approx(5)
    assert x['benchmarkInteractionPp'] == pytest.approx(-10)
    assert x['excess']['meanPp'] == pytest.approx(-5)
    assert abs(x['meanExcessIdentityResidualPp']) < 1e-12


def test_unmeasured_and_immature_are_not_losses_or_zero_returns():
    r = [{'status':'IMMATURE_AT_AS_OF','start':'2026-10-30','candidateReturnPct':None},
        {'status':'MATURE_TARGET_NO_STORED_ENDPOINT','start':'2025-10-30'}]
    s = F.window_summary(r)
    assert s['scheduledOrigins'] == 2 and s['excess']['n'] == 0
    assert s['excess']['meanPp'] is None and s['excess']['winRatePct'] is None
    r.append({'status':'MEASURED','start':'2024-01-01','observedEndDate':'2024-07-01',
        'candidateReturnPct':0,'benchmarkReturnPct':0,'relativeWealthReturnPct':0,'excessReturnPp':0})
    s = F.window_summary(r)
    assert s['excess']['meanPp'] == 0 and s['excess']['n'] == 1 and s['excess']['tieCount'] == 1
    assert s['excess']['lossCount'] == 0 and s['excess']['winRatePct'] == 0
    assert s['statusCounts']['IMMATURE_AT_AS_OF'] == 1


def test_overlapping_windows_never_become_independent_trials():
    rows = [{'status':'MEASURED','start':start,'observedEndDate':end,'candidateReturnPct':0,
        'benchmarkReturnPct':0,'relativeWealthReturnPct':0,'excessReturnPp':0}
        for start, end in [('2020-01-01','2020-07-01'),('2020-02-01','2020-08-01'),('2020-07-01','2021-01-01')]]
    s = F.window_summary(rows)
    assert s['excess']['n'] == 3
    assert s['disjointCalendarBlockCount_NOT_PROOF_OF_INDEPENDENCE'] == 2


def test_relative_drawdown_recovery_and_right_censoring():
    dates = ['2020-01-01','2020-02-01','2020-03-01','2020-04-01','2020-05-01']
    nav = [1, 1.2, .9, .95, 1.21]
    full = F.drawdown(dates, nav)
    assert full['mddPct'] == pytest.approx(-25)
    assert full['peakDate'] == '2020-02-01' and full['troughDate'] == '2020-03-01'
    assert full['recoveryDate'] == '2020-05-01' and full['peakToRecoveryDays'] == 90
    censored = F.drawdown(dates[:4], nav[:4])
    assert censored['recoveryDate'] is None and censored['peakToRecoveryDays'] is None
    assert censored['status'] == 'UNRECOVERED_THROUGH_LAST_OBSERVATION'
    assert F.drawdown(dates, [1]*5)['mddPct'] == 0


def test_leave_period_out_removes_both_legs_and_elapsed_days_without_making_nav():
    a, b = paired([1, 1.2, 1.56, 1.404], [1, 1.1, 1.21, 1.1495])
    rows = F.interval_data(a, b)
    annual = [{'year': r['through'][:4], **F.summarize_intervals([r])} for r in rows]
    result = F.annual_sensitivity(rows, annual)
    top = next(s for s in result if s['kind'] == 'REMOVE_LARGEST_POSITIVE_LOG_YEARS_1')
    assert top['removedYears'] == ['2020']
    kept = [r for r in rows if r['through'][:4] != '2020']
    assert top['retained'] == F.summarize_intervals(kept)
    assert top['retained']['elapsedObservedDays'] == sum(r['days'] for r in kept)
    assert 'nav' not in top and 'POST_HOC' in top['status']


def test_source_hash_identity_fail_closed_and_no_fetch_or_engine(monkeypatch, tmp_path):
    calls = []
    def reader(args, **kwargs):
        calls.append(args)
        assert args == ['git','show','a'*40+':saved.json']
        assert kwargs['env']['GIT_NO_LAZY_FETCH'] == '1'
        return b'{"saved":true}'
    monkeypatch.setattr(F.subprocess, 'check_output', reader)
    pins = {'sources':[{'commit':'a'*40,'path':'saved.json','sha256':hashlib.sha256(b'{"saved":true}').hexdigest()}]}
    assert F.read_sources(tmp_path, pins) == {'saved.json':b'{"saved":true}'}
    pins['sources'][0]['sha256'] = '0'*64
    with pytest.raises(ValueError, match='HASH_MISMATCH'):
        F.read_sources(tmp_path, pins)
    pins['sources'][0]['path'] = '../outside'
    with pytest.raises(ValueError, match='INVALID_SOURCE_REF'):
        F.read_sources(tmp_path, pins)
    assert len(calls) == 2


def test_no_strategy_valuation_training_authorization_or_network_imports():
    import ast
    tree = ast.parse(Path(F.__file__).read_text())
    imports = {n.module.split('.')[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    imports.update(alias.name.split('.')[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for alias in n.names)
    assert not imports & {'pipeline','requests','urllib','http','yfinance','numpy','pandas','sklearn'}
    assert F.CLASS.startswith('POST_OUTCOME_EXPOSED_DESCRIPTIVE')
