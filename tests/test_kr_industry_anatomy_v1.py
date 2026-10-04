"""Synthetic fixtures only. No historical price, return or outcome is read anywhere in this file."""
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from pipeline import kr_factor_anatomy as A
from pipeline import kr_industry_anatomy as I

ROOT = Path(__file__).resolve().parents[1]
CROSSWALK = json.loads((ROOT / 'research_specs/kr-industry-membership-foundation-v4/crosswalk.json').read_text())
SEMI = '반도체 제조업'
BANK = '은행 및 저축기관'


def iv(label, status='RECONSTRUCTED_STABLE_NO_CHANGE_EVENT', start=None, end=None):
    return {'start': start, 'end': end, 'label': label, 'status': status, 'reconstruction_status': status}


def setup(n=6, label=SEMI):
    tickers = [f'T{i}.KS' for i in range(n)]
    schedule = {'2020-01-03': tickers}
    intervals = {t: [iv(label)] for t in tickers}
    return tickers, schedule, intervals


def caps(tickers, date='2020-01-03', base=100.0):
    return pd.DataFrame({'date': date, 'ticker': tickers, 'marketCap': [base * (i + 1) for i in range(len(tickers))]})


def test_cohort_is_frozen_with_signal_date_cap_weights_only():
    tickers, schedule, intervals = setup()
    membership = I.membership_table(schedule, intervals, CROSSWALK)
    cohort = I.build_cohorts(membership, caps(tickers))[('2020-01-03', 'ELECTRONICS_ELECTRICAL')]
    assert cohort['status'] == 'ELIGIBLE' and cohort['n'] == 6
    assert math.isclose(sum(cohort['capWeights'].values()), 1.0) and math.isclose(cohort['capWeights']['T5.KS'], 6 / 21)
    later = caps(tickers, base=100.0).assign(marketCap=lambda d: d.marketCap[::-1].to_numpy())
    changed = I.build_cohorts(membership, later)[('2020-01-03', 'ELECTRONICS_ELECTRICAL')]
    assert changed['capWeights'] != cohort['capWeights']  # weights are exactly the supplied signal-date caps, nothing else enters


def test_no_future_membership_leakage_and_interval_boundaries():
    tickers, schedule, _ = setup()
    intervals = {t: [iv(BANK, end='2020-01-03'), iv(SEMI, start='2020-01-03')] for t in tickers}
    got = I.membership_table(schedule, intervals, CROSSWALK)
    assert set(got.industry) == {'ELECTRONICS_ELECTRICAL'}  # the interval that starts at t applies at t, the older one ended
    early = I.membership_table({'2019-12-27': tickers}, intervals, CROSSWALK)
    assert set(early.industry) == {'FINANCIALS'}


def test_minimum_five_members_and_no_unknown_fill():
    tickers, schedule, intervals = setup(8)
    for t in tickers[4:]:
        intervals[t] = [iv(None, status='UNKNOWN')]
    membership = I.membership_table(schedule, intervals, CROSSWALK)
    cohort = I.build_cohorts(membership, caps(tickers))[('2020-01-03', 'ELECTRONICS_ELECTRICAL')]
    assert cohort['n'] == 4 and cohort['status'] == 'INELIGIBLE' and cohort['reason'] == 'BELOW_MINIMUM_CLASSIFIED_MEMBERS'
    assert membership.industry.isna().sum() == 4 and (membership.membershipStatus[membership.industry.isna()] == 'UNKNOWN').all()
    assert cohort['capWeights'] is None


def test_unmapped_conflict_and_terminated_names_stay_unknown():
    assert I.industry_of({'A': [iv('존재하지 않는 업종')]}, CROSSWALK, 'A', '2020-01-03') == (None, 'UNMAPPED_LABEL')
    assert I.industry_of({'A': [iv(SEMI, status='CONFLICT')]}, CROSSWALK, 'A', '2020-01-03')[0] is None
    tickers, schedule, intervals = setup()
    table = I.membership_table(schedule, intervals, CROSSWALK, terminated={'T0.KS': '2020-01-03'})
    assert table[table.ticker == 'T0.KS'].iloc[0].membershipStatus == 'IDENTITY_TERMINATED' and pd.isna(table[table.ticker == 'T0.KS'].iloc[0].industry)


def test_no_survivor_substitution_or_renormalisation():
    tickers, schedule, intervals = setup()
    cohort = I.build_cohorts(I.membership_table(schedule, intervals, CROSSWALK), caps(tickers))[('2020-01-03', 'ELECTRONICS_ELECTRICAL')]
    forward = {t: (0.10, 0.04, 'MATURED') for t in tickers}
    forward['T0.KS'] = (np.nan, 0.04, 'UNRESOLVED_TERMINAL_OR_DISTRIBUTION_EVIDENCE')
    out = I.industry_targets(cohort, forward, 126)
    assert all(v['status'] == 'UNRESOLVED_INCOMPLETE_COHORT_OR_WINDOW' and v['relative'] is None for v in out.values())


def test_equal_weight_cap_weight_and_market_relative_arithmetic():
    tickers, schedule, intervals = setup()
    cohort = I.build_cohorts(I.membership_table(schedule, intervals, CROSSWALK), caps(tickers))[('2020-01-03', 'ELECTRONICS_ELECTRICAL')]
    returns = {t: 0.01 * (i + 1) for i, t in enumerate(tickers)}
    forward = {t: (r, 0.02, 'MATURED') for t, r in returns.items()}
    out = I.industry_targets(cohort, forward, 126)
    expected_cap = sum((i + 1) / 21 * 0.01 * (i + 1) for i in range(6))
    assert math.isclose(out['CAP_WEIGHTED']['return'], expected_cap) and math.isclose(out['CAP_WEIGHTED']['relative'], expected_cap - 0.02)
    assert math.isclose(out['EQUAL_WEIGHT']['return'], np.mean(list(returns.values()))) and math.isclose(out['EQUAL_WEIGHT']['relative'], 0.035 - 0.02)


def test_cap_weight_unavailable_fails_closed_for_primary_lens_only():
    tickers, schedule, intervals = setup()
    c = caps(tickers)
    c.loc[0, 'marketCap'] = np.nan
    cohort = I.build_cohorts(I.membership_table(schedule, intervals, CROSSWALK), c)[('2020-01-03', 'ELECTRONICS_ELECTRICAL')]
    assert cohort['capWeights'] is None and cohort['missingCapShare'] == pytest.approx(1 / 6)
    out = I.industry_targets(cohort, {t: (0.1, 0.0, 'MATURED') for t in tickers}, 126)
    assert out['CAP_WEIGHTED']['status'] == 'INELIGIBLE_CAP_WEIGHT_UNAVAILABLE' and out['EQUAL_WEIGHT']['status'] == 'MATURED'


def test_concentration_and_leave_largest_out_and_mega_cap_exclusion():
    tickers, schedule, intervals = setup(7)
    tickers[0], tickers[1] = '005930.KS', '000660.KS'
    schedule = {'2020-01-03': tickers}
    intervals = {t: [iv(SEMI)] for t in tickers}
    c = pd.DataFrame({'date': '2020-01-03', 'ticker': tickers, 'marketCap': [500, 300, 100, 50, 30, 20, 10]})
    membership = I.membership_table(schedule, intervals, CROSSWALK)
    key = ('2020-01-03', 'ELECTRONICS_ELECTRICAL')
    full = I.build_cohorts(membership, c)[key]
    assert full['top1'] == pytest.approx(500 / 1010) and full['top2'] == pytest.approx(800 / 1010) and full['hhi'] > 0
    leave = I.build_cohorts(membership, c, leave_largest_out=True)[key]
    assert '005930.KS' not in leave['members'] and leave['n'] == 6 and leave['top1'] == pytest.approx(300 / 510)
    excl = I.build_cohorts(membership, c, exclude=I.EXCLUDED_MEGA_CAPS)[key]
    assert excl['n'] == 5 and excl['status'] == 'ELIGIBLE'
    assert I.build_cohorts(membership, c, exclude=I.EXCLUDED_MEGA_CAPS, leave_largest_out=True)[key]['status'] == 'INELIGIBLE'


@pytest.mark.parametrize('horizon', [63, 126, 252])
def test_exact_horizon_endpoints_follow_the_repository_rule(horizon):
    days = pd.bdate_range('2019-06-03', periods=400)
    prices = {t: pd.DataFrame({'Close': np.linspace(100, 200, len(days))}, index=days) for t in ('X.KS', I.BENCHMARK)}
    signal = str(days[10].date())
    out = A.endpoint_returns(days, prices, I.BENCHMARK, 'X.KS', signal, horizon, '2021-12-31')
    assert out['entryDate'] == str(days[11].date()) and out['exitDate'] == str(days[11 + horizon].date())
    assert out['status'] == 'MATURED' and I.RETURN_BASIS == 'BENCHMARK_RELATIVE_ADJUSTED_INDEX_RETURN_PARTIAL_DISTRIBUTIONS'


def test_features_use_only_past_windows():
    close = np.arange(1.0, 301.0)
    assert I.trailing_return(close, 199, 126) == pytest.approx(close[199] / close[73] - 1)
    bumped = close.copy()
    bumped[250:] = 1e6  # the future must not move any value computed at 199
    assert I.trailing_return(bumped, 199, 126) == I.trailing_return(close, 199, 126)
    assert I.above_moving_average(bumped, 199, 126) == I.above_moving_average(close, 199, 126) == 1.0
    assert np.isnan(I.trailing_return(close, 50, 126)) and np.isnan(I.above_moving_average(close, 50, 126))
    assert np.array_equal(I.daily_returns_window(bumped, 199, 126), I.daily_returns_window(close, 199, 126))


def test_industry_features_missing_stays_missing_never_zero():
    tickers, schedule, intervals = setup()
    cohort = I.build_cohorts(I.membership_table(schedule, intervals, CROSSWALK), caps(tickers))[('2020-01-03', 'ELECTRONICS_ELECTRICAL')]
    past = {t: {'trail63': 0.1, 'trail126': 0.2, 'aboveMA126': 1.0, 'bench63': 0.05, 'bench126': 0.1, 'daily': np.full(126, 0.001)} for t in tickers}
    panel = {t: {'logAdv60': 20.0, 'bookToMarketProxy': float(i)} for i, t in enumerate(tickers)}
    f = I.industry_features(cohort, past, panel)
    assert f['REL_MOM_126'] == pytest.approx(0.1) and f['BREADTH_POSITIVE_126'] == 1.0 and f['DOWNSIDE_VOL_126'] == 0.0
    assert f['MEDIAN_bookToMarketProxy'] == pytest.approx(2.5) and np.isnan(f['MEDIAN_ocfYieldProxy'])  # absent column is NaN
    past['T0.KS']['trail126'] = np.nan
    g = I.industry_features(cohort, past, panel)
    assert np.isnan(g['REL_MOM_126']) and np.isnan(g['BREADTH_POSITIVE_126'])  # one missing member: missing, not neutral
    sparse = {t: {'bookToMarketProxy': v} for t, v in zip(tickers, [1.0, 2.0, np.nan, np.nan, np.nan, np.nan])}
    assert np.isnan(I.industry_features(cohort, past, sparse)['MEDIAN_bookToMarketProxy'])  # 2 finite of 6 is below the frozen coverage


def test_accounting_is_visible_only_after_its_receipt_date():
    from pipeline.alpha_opportunity_features import visible_filings
    row = {'availableFrom': '2020-03-31', 'receiptNos': ['20200331000001'], 'id': 'a'}
    assert visible_filings([row], '2020-03-31', 'KR') == [] and visible_filings([row], '2020-04-01', 'KR') == [row]


def test_tercile_rules_ties_and_small_cross_section():
    labels = [f'I{i}' for i in range(9)]
    x, y = np.arange(9.0), np.array([0, 0, 0, 1, 1, 1, 5, 5, 5.0])
    assert I.tercile_spread_for_date(x, y, labels) == pytest.approx(5.0)
    tied = x.copy()
    tied[2] = tied[3] = 2.5  # tie straddling the lower boundary: invalid, never resolved arbitrarily
    assert I.tercile_spread_for_date(tied, y, labels) is None
    assert I.tercile_spread_for_date(x[:8], y[:8], labels[:8]) is None
    ties_inside = np.array([0, 0, 0, 1, 2, 3, 4, 4, 4.0])
    assert I.tercile_spread_for_date(ties_inside, y, labels) == pytest.approx(5.0)


def test_small_cross_section_is_refused_per_date():
    rows = [{'date': '2020-01-03', 'industry': f'I{i}', 'f': float(i), 'y': float(i)} for i in range(7)]
    assert I.per_date_ic(pd.DataFrame(rows), 'f', 'y') == {}
    rows = [{'date': '2020-01-03', 'industry': f'I{i}', 'f': float(i), 'y': float(i)} for i in range(8)]
    assert I.per_date_ic(pd.DataFrame(rows), 'f', 'y') == {'2020-01-03': pytest.approx(1.0)}


def test_summary_statistics_and_descriptive_inference_are_labelled_series_only():
    s = pd.Series({'2020-01-03': 0.2, '2020-01-10': -0.1, '2021-01-08': 0.3, '2021-01-15': 0.0})
    out = I.summarize(s, 126)
    assert out['validDates'] == 4 and out['mean'] == pytest.approx(0.1) and out['positiveFraction'] == pytest.approx(2 / 3)
    assert set(out['byYear']) == {'2020', '2021'} and out['effectiveDates'] == pytest.approx(4 / 25.2)
    assert I.summarize({}, 126)['validDates'] == 0


def test_forbidden_output_semantics_are_refused():
    with pytest.raises(ValueError):
        I.assert_no_forbidden_keys({'a': {'bestFeature': 1}})
    I.assert_no_forbidden_keys({'meanRankCorrelation': 0.1})


def test_full_synthetic_analysis_runs_without_choosing_anything():
    dates = [str(d.date()) for d in pd.bdate_range('2020-01-03', periods=12, freq='W-FRI')]
    rows = []
    rng = np.random.default_rng(0)
    for d in dates:
        for k in range(10):
            row = {'date': d, 'industry': f'I{k}', 'status': 'ELIGIBLE', 'reason': None, 'n': 6, 'classifiedCoverage': 0.9, 'hhi': 0.2, 'missingCapShare': 0.0}
            row.update({name: float(rng.normal()) for name in I.FEATURES})
            row['TOP1_CAP_SHARE'] = float(rng.uniform(0.1, 0.6))
            for h in I.HORIZONS:
                row['entry' + str(h)], row['exit' + str(h)] = '2020-02-01', '2020-12-01'
                for lens in I.LENSES:
                    row[f'rel_{lens}_{h}'] = float(rng.normal())
                    row[f'status_{lens}_{h}'] = 'MATURED'
            rows.append(row)
    panel = pd.DataFrame(rows)
    result = I.analyze_panel(panel, {'developmentCutoff': '2026-09-14'})
    key = 'REL_MOM_126|CAP_WEIGHTED|H126'
    assert result['ic'][key]['validDates'] == 12 and result['tercile'][key]['validDates'] == 12
    assert result['coverage'][key]['eligibleIndustryDates'] == 120 and result['strata'][key + '|TOP1_CAP_SHARE_LOW']['validDates'] >= 0
    I.assert_no_forbidden_keys(result)
    assert I.eligibility_summary(panel)['eligible'] == 120 and I.lens_comparison(panel, 126)['validDates'] == 12
