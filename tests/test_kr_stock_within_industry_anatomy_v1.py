"""Synthetic fixtures only. No historical price, return or outcome is read anywhere in this file."""
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from pipeline import kr_factor_anatomy as A
from pipeline import kr_industry_anatomy as I
from pipeline import kr_stock_within_industry_anatomy as S

ROOT = Path(__file__).resolve().parents[1]
CROSSWALK = json.loads((ROOT / 'research_specs/kr-industry-membership-foundation-v4/crosswalk.json').read_text())
SEMI = '반도체 제조업'
BANK = '은행 및 저축기관'
DATE = '2020-01-03'


def iv(label, status='RECONSTRUCTED_STABLE_NO_CHANGE_EVENT', start=None, end=None):
    return {'start': start, 'end': end, 'label': label, 'status': status, 'reconstruction_status': status}


def membership(n=6, label=SEMI, date=DATE):
    tickers = [f'T{i}.KS' for i in range(n)]
    return tickers, I.membership_table({date: tickers}, {t: [iv(label)] for t in tickers}, CROSSWALK)


def features(tickers, date=DATE, caps=None, **columns):
    frame = pd.DataFrame({'date': date, 'ticker': tickers, 'marketCap': caps if caps is not None else [100.0 * (i + 1) for i in range(len(tickers))]})
    for name in S.FEATURES:
        frame[name] = columns.get(name, [float(i) for i in range(len(tickers))])
    return frame


def forward_for(tickers, returns, bench=0.02, status='MATURED'):
    return {t: (r, bench, status) for t, r in zip(tickers, returns)}


def all_horizons(date, fw):
    return {(date, h): fw for h in S.HORIZONS}


def windows(date=DATE):
    return {(date, h): ('2020-01-06', '2021-01-06') for h in S.HORIZONS}


# --------------------------------------------------------------------------- #
# The leave-one-out benchmark
# --------------------------------------------------------------------------- #
def test_evaluated_stock_is_excluded_from_its_own_industry_benchmark():
    tickers, m = membership()
    cohort = S.build_cohorts(m)[(DATE, 'ELECTRONICS_ELECTRICAL')]
    for ticker in tickers:
        peers = S.peers_of(cohort, ticker)
        assert ticker not in peers and len(peers) == 5 and peers == sorted(set(tickers) - {ticker})
    # Changing the evaluated stock's own return or own cap cannot move its own benchmark.
    base = forward_for(tickers, [0.01 * (i + 1) for i in range(6)])
    caps = dict(zip(tickers, [100.0 * (i + 1) for i in range(6)]))
    t0 = S.stock_targets('T0.KS', cohort, base, caps)['CAP_WEIGHTED']
    moved = dict(base, **{'T0.KS': (9.0, 0.02, 'MATURED')})
    assert S.stock_targets('T0.KS', cohort, moved, dict(caps, **{'T0.KS': 1e12}))['CAP_WEIGHTED']['loo'] == t0['loo']
    assert S.stock_targets('T0.KS', cohort, moved, caps)['EQUAL_WEIGHT']['loo'] == S.stock_targets('T0.KS', cohort, base, caps)['EQUAL_WEIGHT']['loo']
    # ... while a PEER's return does move it.
    peer_moved = dict(base, **{'T1.KS': (9.0, 0.02, 'MATURED')})
    assert S.stock_targets('T0.KS', cohort, peer_moved, caps)['CAP_WEIGHTED']['loo'] != t0['loo']


def test_cap_and_equal_weight_arithmetic_with_peer_only_weights():
    tickers, m = membership()
    cohort = S.build_cohorts(m)[(DATE, 'ELECTRONICS_ELECTRICAL')]
    returns = [0.01 * (i + 1) for i in range(6)]
    caps = {t: 100.0 * (i + 1) for i, t in enumerate(tickers)}
    out = S.stock_targets('T5.KS', cohort, forward_for(tickers, returns, bench=0.02), caps)
    peers_cap = sum(caps[f'T{i}.KS'] for i in range(5))
    expected_cap = sum(caps[f'T{i}.KS'] / peers_cap * returns[i] for i in range(5))
    expected_eq = sum(returns[:5]) / 5
    cap, eq = out['CAP_WEIGHTED'], out['EQUAL_WEIGHT']
    assert cap['status'] == eq['status'] == 'MATURED'
    assert math.isclose(cap['loo'], expected_cap) and math.isclose(eq['loo'], expected_eq)
    assert math.isclose(cap['components']['STOCK_MINUS_LOO_INDUSTRY'], returns[5] - expected_cap)
    assert math.isclose(cap['components']['LOO_INDUSTRY_MINUS_MARKET'], expected_cap - 0.02)
    assert math.isclose(cap['components']['STOCK_MINUS_MARKET'], returns[5] - 0.02)
    assert math.isclose(eq['components']['STOCK_MINUS_LOO_INDUSTRY'], returns[5] - expected_eq)
    weights = S.peer_cap_weights([f'T{i}.KS' for i in range(5)], caps)
    assert math.isclose(sum(weights.values()), 1.0) and 'T5.KS' not in weights and math.isclose(weights['T4.KS'], 500 / 1500)


def test_decomposition_identity_holds_on_every_matured_row():
    tickers, m = membership(8)
    fw = forward_for(tickers, [0.03 * i - 0.05 for i in range(8)], bench=0.011)
    panel = S.build_stock_panel(m, features(tickers), all_horizons(DATE, fw), windows())
    assert S.assert_identity(panel) is True
    matured = panel['status_CAP_WEIGHTED_126'].eq('MATURED')
    assert matured.all()
    lhs = panel['t_STOCK_MINUS_MARKET_CAP_WEIGHTED_126']
    rhs = panel['t_LOO_INDUSTRY_MINUS_MARKET_CAP_WEIGHTED_126'] + panel['t_STOCK_MINUS_LOO_INDUSTRY_CAP_WEIGHTED_126']
    assert np.allclose(lhs, rhs, atol=1e-15)
    broken = panel.copy()
    broken.loc[0, 't_STOCK_MINUS_MARKET_CAP_WEIGHTED_126'] += 1e-6
    with pytest.raises(ValueError, match='DECOMPOSITION_IDENTITY_VIOLATED'):
        S.assert_identity(broken)


def test_cohort_is_frozen_at_the_signal_date():
    tickers, m = membership()
    later = membership(date='2020-06-05')[1]
    cohorts = S.build_cohorts(pd.concat([m, later]))
    assert cohorts[(DATE, 'ELECTRONICS_ELECTRICAL')]['members'] == tickers
    assert cohorts[('2020-06-05', 'ELECTRONICS_ELECTRICAL')]['members'] == tickers
    # A name that joins the industry later is not a peer of an earlier date, and a later weight never reaches an earlier target.
    intervals = {t: [iv(SEMI)] for t in tickers}
    intervals['T5.KS'] = [iv(BANK, end='2020-01-04'), iv(SEMI, start='2020-01-04')]
    early = I.membership_table({DATE: tickers}, intervals, CROSSWALK)
    assert early[early.ticker == 'T5.KS'].iloc[0].industry == 'FINANCIALS'
    assert S.build_cohorts(early)[(DATE, 'ELECTRONICS_ELECTRICAL')]['members'] == tickers[:5]


def test_weights_are_signal_date_caps_only():
    tickers, m = membership()
    cohort = S.build_cohorts(m)[(DATE, 'ELECTRONICS_ELECTRICAL')]
    fw = forward_for(tickers, [0.05] * 6)
    caps = {t: 100.0 * (i + 1) for i, t in enumerate(tickers)}
    first = S.stock_targets('T0.KS', cohort, fw, caps)['CAP_WEIGHTED']['loo']
    # The loo return of identical peer returns is that return whatever the weights are, so vary the returns with the caps held fixed
    # and then the caps with the returns held fixed: only the supplied (signal-date) caps determine the weights.
    skew = forward_for(tickers, [0.0, 0.01, 0.02, 0.03, 0.04, 0.05])
    a = S.stock_targets('T0.KS', cohort, skew, caps)['CAP_WEIGHTED']['loo']
    reversed_caps = dict(zip(tickers, [600.0, 500.0, 400.0, 300.0, 200.0, 100.0]))
    b = S.stock_targets('T0.KS', cohort, skew, reversed_caps)['CAP_WEIGHTED']['loo']
    assert first == pytest.approx(0.05) and a != b
    w = S.peer_cap_weights(cohort['members'][1:], reversed_caps)
    assert b == pytest.approx(sum(w[t] * skew[t][0] for t in w))


@pytest.mark.parametrize('bad', [np.nan, 0.0, -5.0, None])
def test_peer_without_a_usable_cap_makes_only_the_cap_lens_ineligible(bad):
    tickers, m = membership()
    cohort = S.build_cohorts(m)[(DATE, 'ELECTRONICS_ELECTRICAL')]
    caps = {t: 100.0 * (i + 1) for i, t in enumerate(tickers)}
    caps['T3.KS'] = bad
    out = S.stock_targets('T0.KS', cohort, forward_for(tickers, [0.01] * 6), caps)
    assert out['CAP_WEIGHTED']['status'] == 'INELIGIBLE_CAP_WEIGHT_UNAVAILABLE' and out['CAP_WEIGHTED']['loo'] is None
    assert out['EQUAL_WEIGHT']['status'] == 'MATURED'
    # The stock whose OWN cap is missing is not a peer of itself: its cap lens is still defined.
    own = S.stock_targets('T3.KS', cohort, forward_for(tickers, [0.01] * 6), caps)
    assert own['CAP_WEIGHTED']['status'] == 'MATURED'


def test_minimum_four_other_peers():
    for n, eligible in ((4, False), (5, True), (6, True)):
        tickers, m = membership(n)
        cohort = S.build_cohorts(m)[(DATE, 'ELECTRONICS_ELECTRICAL')]
        assert (cohort['status'] == 'ELIGIBLE') is eligible
        peers = S.peers_of(cohort, 'T0.KS')
        assert (peers is not None) is eligible and (peers is None or len(peers) >= S.MIN_PEERS)
    tickers, m = membership(4)
    out = S.stock_targets('T0.KS', S.build_cohorts(m)[(DATE, 'ELECTRONICS_ELECTRICAL')], forward_for(tickers, [0.1] * 4), {})
    assert all(v['status'] == 'INELIGIBLE_INDUSTRY_DATE' and v['loo'] is None for v in out.values())
    assert S.peers_of(None, 'T0.KS') is None


def test_unknown_names_are_never_filled_in_and_stay_in_the_denominator():
    tickers, _ = membership(8)
    intervals = {t: [iv(SEMI)] for t in tickers}
    for t in tickers[4:]:
        intervals[t] = [iv(None, status='UNKNOWN')]
    m = I.membership_table({DATE: tickers}, intervals, CROSSWALK)
    assert S.build_cohorts(m)[(DATE, 'ELECTRONICS_ELECTRICAL')]['members'] == tickers[:4]  # the four UNKNOWN names are not used to fill it
    panel = S.build_stock_panel(m, features(tickers), all_horizons(DATE, forward_for(tickers, [0.1] * 8)), windows())
    assert len(panel) == 8 and panel.membershipStatus.eq('UNKNOWN').sum() == 4
    assert panel.status.value_counts().to_dict() == {'INELIGIBLE_UNCLASSIFIED': 4, 'INELIGIBLE_BELOW_MINIMUM_INDUSTRY_MEMBERS': 4}
    assert panel.filter(like='t_').isna().all().all()
    audit = S.membership_eligibility(m)
    assert audit['stockDates'] == 8 and audit['unknownRetainedInDenominator'] == 4 and audit['byStatus'].get('ELIGIBLE', 0) == 0


@pytest.mark.parametrize('status', ['UNRESOLVED_TERMINAL_OR_DISTRIBUTION_EVIDENCE', 'MISSING_FORWARD_PRICE_OR_DELISTING', 'MISSING'])
def test_terminal_or_unresolved_peer_refuses_the_target_without_survivor_substitution(status):
    tickers, m = membership()
    cohort = S.build_cohorts(m)[(DATE, 'ELECTRONICS_ELECTRICAL')]
    caps = {t: 100.0 * (i + 1) for i, t in enumerate(tickers)}
    fw = forward_for(tickers, [0.1] * 6)
    fw['T2.KS'] = (np.nan, 0.02, status)
    out = S.stock_targets('T0.KS', cohort, fw, caps)
    assert all(v['status'] == 'UNRESOLVED_PEER_RETURN' and v['loo'] is None and v['components']['STOCK_MINUS_LOO_INDUSTRY'] is None for v in out.values())
    own = S.stock_targets('T2.KS', cohort, fw, caps)  # the terminal stock itself has no target either
    assert all(v['status'] == 'UNRESOLVED_OWN_RETURN' for v in own.values())
    # A finite return behind a refused status is NEVER used: only MATURED peers contribute.
    fw['T2.KS'] = (0.9, 0.02, status)
    assert S.stock_targets('T0.KS', cohort, fw, caps)['CAP_WEIGHTED']['status'] == 'UNRESOLVED_PEER_RETURN'
    assert S.peer_returns(['A', 'B'], None, {'A': 0.1, 'B': np.nan}) == (None, None)


def test_pending_windows_are_pending_not_zero_or_unresolved():
    tickers, m = membership()
    cohort = S.build_cohorts(m)[(DATE, 'ELECTRONICS_ELECTRICAL')]
    out = S.stock_targets('T0.KS', cohort, forward_for(tickers, [np.nan] * 6, status='PENDING'), {})
    assert all(v['status'] == 'PENDING' and v['loo'] is None for v in out.values())


@pytest.mark.parametrize('horizon', [63, 126, 252])
def test_exact_horizon_endpoints_follow_the_repository_rule(horizon):
    days = pd.bdate_range('2019-06-03', periods=400)
    prices = {t: pd.DataFrame({'Close': np.linspace(100, 200, len(days))}, index=days) for t in ('X.KS', S.BENCHMARK)}
    signal = str(days[10].date())
    out = A.endpoint_returns(days, prices, S.BENCHMARK, 'X.KS', signal, horizon, '2021-12-31')
    assert out['entryDate'] == str(days[11].date()) and out['exitDate'] == str(days[11 + horizon].date())
    assert out['status'] == 'MATURED' and S.RETURN_BASIS == 'BENCHMARK_RELATIVE_ADJUSTED_INDEX_RETURN_PARTIAL_DISTRIBUTIONS'
    assert horizon in S.HORIZONS and S.PRIMARY_HORIZON == 126
    late = A.endpoint_returns(days, prices, S.BENCHMARK, 'X.KS', signal, horizon, str(days[10 + horizon].date()))
    assert late['status'] == 'PENDING' and late['stockReturn'] is None  # exit after the development cutoff: pending, not a number


def test_all_three_horizons_are_built_per_stock_date_with_their_own_windows():
    tickers, m = membership()
    fw = {h: forward_for(tickers, [0.01 * h * (i + 1) / 100 for i in range(6)]) for h in S.HORIZONS}
    windows_ = {(DATE, h): (f'e{h}', f'x{h}') for h in S.HORIZONS}
    panel = S.build_stock_panel(m, features(tickers), {(DATE, h): fw[h] for h in S.HORIZONS}, windows_)
    for h in S.HORIZONS:
        assert set(panel[f'entry{h}']) == {f'e{h}'} and set(panel[f'exit{h}']) == {f'x{h}'}
        assert panel[f'status_CAP_WEIGHTED_{h}'].eq('MATURED').all() and panel[f'status_EQUAL_WEIGHT_{h}'].eq('MATURED').all()
    assert panel['stock63'].iloc[0] != panel['stock252'].iloc[0]


# --------------------------------------------------------------------------- #
# Within-industry ranks
# --------------------------------------------------------------------------- #
def frame_for_ranks(values_by_industry, date=DATE):
    rows = []
    for industry, values in values_by_industry.items():
        for i, v in enumerate(values):
            rows.append({'date': date, 'industry': industry, 'ticker': f'{industry}{i}', 'f': v})
    return pd.DataFrame(rows)


def test_within_industry_rank_uses_only_same_date_same_industry_peers():
    frame = frame_for_ranks({'A': [1.0, 2.0, 3.0, 4.0, 5.0], 'B': [100.0, 200.0, 300.0, 400.0, 500.0]})
    out = S.within_industry_percentiles(frame, columns=('f',))
    for industry in 'AB':
        assert list(out[out.industry == industry].wi_f) == pytest.approx([0.1, 0.3, 0.5, 0.7, 0.9])
    perturbed = frame.copy()
    perturbed.loc[perturbed.industry == 'B', 'f'] = [5e9, -1.0, 7.0, 7.5, 1e-9]  # another industry's values cannot move A's ranks
    assert list(S.within_industry_percentiles(perturbed, columns=('f',)).query("industry == 'A'").wi_f) == pytest.approx([0.1, 0.3, 0.5, 0.7, 0.9])
    other_date = pd.concat([frame, frame_for_ranks({'A': [9e9, 8e9, -9e9, 3.0, 2.0]}, date='2021-01-08')])
    again = S.within_industry_percentiles(other_date, columns=('f',))
    assert list(again[(again.date == DATE) & (again.industry == 'A')].wi_f) == pytest.approx([0.1, 0.3, 0.5, 0.7, 0.9])  # a later date cannot


def test_within_industry_rank_ignores_the_forward_outcome_and_row_order():
    tickers, m = membership(7)
    feats = features(tickers, bookToMarketProxy=[3.0, 1.0, 2.0, 7.0, 5.0, 6.0, 4.0])
    one = S.build_stock_panel(m, feats, all_horizons(DATE, forward_for(tickers, [0.01 * i for i in range(7)])), windows())
    two = S.build_stock_panel(m, feats, all_horizons(DATE, forward_for(tickers, [(-1) ** i * 0.5 for i in range(7)], bench=0.3)), windows())
    shuffled = S.build_stock_panel(m.sample(frac=1.0, random_state=1).reset_index(drop=True), feats.sample(frac=1.0, random_state=2),
                                   all_horizons(DATE, forward_for(tickers, [0.2] * 7)), windows())
    for other in (two, shuffled):
        assert one.set_index('ticker').wi_bookToMarketProxy.sort_index().equals(other.set_index('ticker').wi_bookToMarketProxy.sort_index())
    assert one.set_index('ticker').wi_bookToMarketProxy['T3.KS'] == pytest.approx((7 - 0.5) / 7)


def test_within_industry_rank_ties_share_the_average_percentile():
    out = S.within_industry_percentiles(frame_for_ranks({'A': [1.0, 2.0, 2.0, 2.0, 9.0, 10.0]}), columns=('f',))
    assert out.wi_f.iloc[1] == out.wi_f.iloc[2] == out.wi_f.iloc[3] == pytest.approx((3 - 0.5) / 6)  # ranks 2,3,4 average to 3
    assert out.wi_f.iloc[0] == pytest.approx(0.5 / 6) and out.wi_f.iloc[5] == pytest.approx(5.5 / 6)
    reordered = S.within_industry_percentiles(frame_for_ranks({'A': [2.0, 10.0, 2.0, 1.0, 9.0, 2.0]}), columns=('f',))
    assert sorted(reordered.wi_f) == pytest.approx(sorted(out.wi_f))


def test_thin_peer_set_is_not_ranked_and_missing_is_never_zero():
    out = S.within_industry_percentiles(frame_for_ranks({'A': [1.0, np.nan, 3.0, 4.0, 5.0, 6.0]}), columns=('f',))
    assert out.wi_f.notna().sum() == 5 and out.wi_n_f.iloc[0] == 5 and out.wi_f.isna().sum() == 1 and (out.wi_f.dropna() > 0).all()
    thin = S.within_industry_percentiles(frame_for_ranks({'A': [1.0, 2.0, 3.0, 4.0, np.nan, np.nan]}), columns=('f',))
    assert thin.wi_f.isna().all() and (thin.wi_n_f == 4).all()
    missing_column = S.within_industry_percentiles(frame_for_ranks({'A': [1.0] * 5}), columns=('absent',))
    assert missing_column.wi_absent.isna().all()


def test_mega_cap_exclusion_is_applied_before_cohorts_ranks_and_weights():
    tickers = ['005930.KS', '000660.KS'] + [f'T{i}.KS' for i in range(4)]
    m = I.membership_table({DATE: tickers}, {t: [iv(SEMI)] for t in tickers}, CROSSWALK)
    feats = features(tickers, caps=[1e6, 5e5, 10.0, 20.0, 30.0, 40.0])
    fw = forward_for(tickers, [0.5, 0.4, 0.01, 0.02, 0.03, 0.04])
    full = S.build_stock_panel(m, feats, all_horizons(DATE, fw), windows())
    excluded = S.build_stock_panel(m, feats, all_horizons(DATE, fw), windows(), exclude=S.EXCLUDED_MEGA_CAPS)
    assert full.status.eq('ELIGIBLE').sum() == 6
    assert excluded.status.eq('ELIGIBLE').sum() == 0 and excluded.status.value_counts().to_dict() == {
        'EXCLUDED_BY_SENSITIVITY': 2, 'INELIGIBLE_BELOW_MINIMUM_INDUSTRY_MEMBERS': 4}  # four names left: below five, never refilled
    assert S.build_cohorts(m, S.EXCLUDED_MEGA_CAPS)[(DATE, 'ELECTRONICS_ELECTRICAL')]['members'] == [f'T{i}.KS' for i in range(4)]
    assert len(excluded) == 6  # the excluded rows stay, with a status, in the denominator


# --------------------------------------------------------------------------- #
# Statistics
# --------------------------------------------------------------------------- #
def synthetic_panel(dates=40, industries=6, per=6, seed=0, signal=0.0):
    rng = np.random.default_rng(seed)
    days = [str(d.date()) for d in pd.bdate_range('2018-01-05', periods=dates, freq='W-FRI')]
    rows_m, rows_f, forward = [], [], {}
    for d in days:
        tickers = []
        for k in range(industries):
            for i in range(per):
                tickers.append((f'I{k}S{i}.KS', k))
        names = [t for t, _ in tickers]
        label = {0: SEMI, 1: BANK, 2: '의료용기기 제조업', 3: '자동차 신품 부품 제조업', 4: '건물 건설업', 5: '기초 화학물질 제조업'}
        intervals = {t: [iv(label[k])] for t, k in tickers}
        rows_m.append(I.membership_table({d: names}, intervals, CROSSWALK))
        feat = features(names, date=d, caps=list(rng.uniform(1, 100, len(names))), **{c: list(rng.normal(size=len(names))) for c in S.FEATURES})
        rows_f.append(feat)
        x = feat.bookToMarketProxy.to_numpy()
        returns = signal * x + rng.normal(0, 0.05, len(names))
        for h in S.HORIZONS:
            forward[(d, h)] = {t: (float(r), 0.01, 'MATURED') for t, r in zip(names, returns)}
    return pd.concat(rows_m, ignore_index=True), pd.concat(rows_f, ignore_index=True), forward, {(d, h): (d, '2020-12-31') for d in days for h in S.HORIZONS}


def test_pooled_ic_uses_the_common_sample_and_a_minimum_cross_section():
    m, f, fw, w = synthetic_panel()
    panel = S.build_stock_panel(m, f, fw, w)
    series = S.pooled_ic_series(panel, 'bookToMarketProxy', 'WITHIN_INDUSTRY_RANK', S.PRIMARY_COMPONENT, 'CAP_WEIGHTED', 126)
    assert len(series) == 40
    sparse = panel.copy()
    sparse.loc[sparse.index[:-20], 'status_CAP_WEIGHTED_126'] = 'UNRESOLVED_PEER_RETURN'  # 20 matured stocks per date at most: below 30
    assert S.pooled_ic_series(sparse, 'bookToMarketProxy', 'RAW', S.PRIMARY_COMPONENT, 'CAP_WEIGHTED', 126) == {}
    assert panel.shape[0] == 40 * 36


def test_planted_within_industry_signal_is_recovered_and_industry_effect_is_separated():
    m, f, fw, w = synthetic_panel(signal=0.05, seed=3)
    panel = S.build_stock_panel(m, f, fw, w)
    key = ('bookToMarketProxy', 'WITHIN_INDUSTRY_RANK', S.PRIMARY_COMPONENT, 'CAP_WEIGHTED', 126)
    assert S.summarize(S.pooled_ic_series(panel, *key), 126)['mean'] > 0.3
    # Planting an INDUSTRY-wide effect instead (every stock of an industry moves together) leaves nothing stock-specific: the
    # leave-one-out target removes it, the stock-minus-market target keeps it.
    rng = np.random.default_rng(5)
    industry_shift = {k: s for k, s in enumerate([-0.2, -0.1, 0.0, 0.1, 0.2, 0.3])}
    fw2 = {}
    for (d, h), table in fw.items():
        fw2[(d, h)] = {t: (rng.normal(0, 0.01) + industry_shift[int(t[1])], b, s) for t, (r, b, s) in table.items()}
    f2 = f.copy()
    f2['bookToMarketProxy'] = [float(industry_shift[int(t[1])]) + rng.normal(0, 0.01) for t in f2.ticker]
    p2 = S.build_stock_panel(m, f2, fw2, w)
    vs_market = S.summarize(S.pooled_ic_series(p2, 'bookToMarketProxy', 'RAW', 'STOCK_MINUS_MARKET', 'CAP_WEIGHTED', 126), 126)['mean']
    vs_loo = S.summarize(S.pooled_ic_series(p2, 'bookToMarketProxy', 'RAW', S.PRIMARY_COMPONENT, 'CAP_WEIGHTED', 126), 126)['mean']
    assert vs_market > 0.5 and abs(vs_loo) < 0.2


def test_industry_date_group_spread_rules_ties_and_minimums():
    labels = [f'S{i}' for i in range(6)]
    x, y = np.arange(6.0), np.array([0.0, 0.0, 1.0, 1.0, 5.0, 5.0])
    assert S.industry_date_group_spread(x, y, labels) == pytest.approx(5.0)  # k = 2 per outer group
    assert S.industry_date_group_spread(x[:5], y[:5], labels[:5]) is None  # n < 6: groups of one stock are refused
    assert S.MIN_GROUP_INDUSTRY_N == 3 * S.MIN_GROUP_SIZE == 6
    boundary_tie = x.copy()
    boundary_tie[1] = boundary_tie[2] = 1.5  # tie straddling the lower boundary
    assert S.industry_date_group_spread(boundary_tie, y, labels) is None
    inside = np.array([0.0, 0.0, 2.0, 3.0, 5.0, 5.0])  # ties inside a group are harmless
    assert S.industry_date_group_spread(inside, y, labels) == pytest.approx(5.0)
    nine_x, nine_y = np.arange(9.0), np.array([0, 0, 0, 1, 1, 1, 4, 4, 4.0])
    assert S.industry_date_group_spread(nine_x, nine_y, [f'S{i}' for i in range(9)]) == pytest.approx(4.0)  # k = 3
    with_nan = np.array([0.0, np.nan, 2.0, 3.0, 4.0, 5.0])
    assert S.industry_date_group_spread(with_nan, y, labels) is None  # five finite
    # ordering is by (feature, ticker): ticker order breaks equal feature values deterministically inside a group
    assert S.industry_date_group_spread(np.array([1.0, 1.0, 5.0, 6.0, 9.0, 9.0]), y, ['b', 'a', 'c', 'd', 'e', 'f']) == pytest.approx(5.0)


def test_group_spread_aggregates_equal_weight_per_industry_not_per_stock():
    rows = []
    for k, (size, shift) in enumerate([(6, 1.0), (6, 3.0), (30, -100.0), (6, 5.0)]):
        for i in range(size):
            rows.append({'date': DATE, 'industry': f'I{k}', 'ticker': f'I{k}S{i:02d}', 'f': float(i), 'y': shift * (1 if i >= size - size // 3 else 0)})
    sub = pd.DataFrame(rows)
    series, used = S.per_date_group_spread(sub, 'f', 'y')
    expected = (1.0 + 3.0 + (-100.0) + 5.0) / 4  # the 30-stock industry counts once, like the 6-stock ones
    assert series[DATE] == pytest.approx(expected) and used[DATE] == 4
    assert S.per_date_group_spread(sub[sub.industry.isin(['I0', 'I1'])], 'f', 'y') == ({}, {})  # fewer than 3 industries


def test_equal_industry_ic_is_invariant_to_the_within_industry_transform():
    rng = np.random.default_rng(2)
    rows = []
    for k in range(4):
        for i in range(8):
            rows.append({'date': DATE, 'industry': f'I{k}', 'ticker': f'I{k}S{i}', 'raw': float(rng.normal() * 10 ** k), 'y': float(rng.normal())})
    sub = pd.DataFrame(rows)
    sub['wi'] = sub.groupby('industry').raw.rank(pct=True)
    a, _ = S.per_date_equal_industry_ic(sub, 'raw', 'y')
    b, _ = S.per_date_equal_industry_ic(sub, 'wi', 'y')
    assert a[DATE] == pytest.approx(b[DATE])


def test_size_control_reports_overlap_and_halves():
    m, f, fw, w = synthetic_panel(seed=7)
    panel = S.build_stock_panel(m, f, fw, w)
    out = S.size_control(panel, 126)
    assert set(out) == set(S.WEIGHT_LENSES)
    cap = out['CAP_WEIGHTED']
    assert cap['rankOverlapWithWithinIndustrySize']['validDates'] == 40
    assert set(cap['byWithinIndustrySizeHalf']) == {'LOWER_HALF_BY_WITHIN_INDUSTRY_SIZE', 'UPPER_HALF_BY_WITHIN_INDUSTRY_SIZE'}


def test_prior_comparison_classes_are_the_frozen_conventions():
    c = S.compare_to_prior
    assert c(0.09, 0.10, 100)['shiftClass'] == 'SURVIVES' and c(0.15, 0.10, 100)['shiftClass'] == 'SURVIVES'
    assert c(0.05, 0.10, 100)['shiftClass'] == 'WEAKENS_MATERIALLY'
    assert c(0.02, 0.10, 100)['shiftClass'] == 'LARGELY_ABSORBED'
    assert c(0.004, 0.10, 100)['shiftClass'] == 'ABSORBED_TO_NEAR_ZERO'
    assert c(-0.05, 0.10, 100)['shiftClass'] == 'CHANGES_SIGN'
    assert c(0.05, 0.004, 100)['shiftClass'] == 'REFERENCE_NEAR_ZERO'
    assert c(0.05, 0.10, 51)['shiftClass'] == 'DATA_INSUFFICIENT' and c(None, 0.1, 100)['shiftClass'] == 'DATA_INSUFFICIENT'


def test_sign_stability_is_descriptive_and_needs_enough_views():
    assert S.sign_stability({str(i): 0.1 for i in range(8)})['label'] == 'POSITIVE_IN_ALL_REGISTERED_VIEWS'
    assert S.sign_stability({str(i): -0.1 for i in range(8)})['label'] == 'NEGATIVE_IN_ALL_REGISTERED_VIEWS'
    mixed = S.sign_stability({**{str(i): 0.1 for i in range(7)}, 'x': -0.01})
    assert mixed['label'] == 'SIGN_DEPENDS_ON_VIEW' and mixed['positiveViews'] == 7 and mixed['negativeViews'] == 1
    assert S.sign_stability({'a': 0.1, 'b': 0.2, 'c': None})['label'] == 'DATA_INSUFFICIENT'


def test_forbidden_output_semantics_are_refused():
    for key in ('bestFeature', 'validated', 'recommendedPortfolio', 'verdict', 'alphaScore', 'passed'):
        with pytest.raises(ValueError):
            S.assert_no_forbidden_keys({'a': {key: 1}})
    S.assert_no_forbidden_keys({'meanRankCorrelation': 0.1, 'SIGN_DEPENDS_ON_VIEW': 1})


def test_full_synthetic_analysis_runs_without_choosing_anything():
    m, f, fw, w = synthetic_panel(dates=30, seed=11, signal=0.02)
    panels = {'FULL': S.build_stock_panel(m, f, fw, w), 'EXCLUDE_SAMSUNG_ELECTRONICS_AND_SK_HYNIX': S.build_stock_panel(m, f, fw, w, exclude=S.EXCLUDED_MEGA_CAPS)}
    prior = {'universes': {'PIT_TOP120_LARGE_CAP_ANALYSIS_UNIVERSE': {'standalone': {'V1_TERMINAL_DISCIPLINE': {
        name: {'126': {'meanRankCorrelation': 0.08}, '252': {'meanRankCorrelation': 0.05}} for name in S.FEATURES}}}}}
    result = S.analyze_all(panels, {'developmentCutoff': '2026-09-14'}, prior)
    key = 'bookToMarketProxy|WITHIN_INDUSTRY_RANK|STOCK_MINUS_LOO_INDUSTRY|CAP_WEIGHTED|H126'
    full = result['analysis']['FULL']
    assert full['pooledIc'][key]['validDates'] == 30 and key + '|FULL_SAMPLE' in full['slices']
    assert set(result['questions']) == set(S.QUESTIONS) and set(result['signViews']) == set(S.FEATURES)
    assert result['priorComparison']['bookToMarketProxy|H126']['sealedStockMinusMarket'] == 0.08
    assert result['eligibility']['FULL']['stockDates'] == 30 * 36 and result['eligibility']['FULL']['byStatus'] == {'ELIGIBLE': 1080}
    assert result['eligibility']['EXCLUDE_SAMSUNG_ELECTRONICS_AND_SK_HYNIX']['byStatus'] == {'ELIGIBLE': 1080}  # synthetic names are not the mega caps
    assert result['questions']['Q4_LIQUIDITY_AFTER_INDUSTRY_CONTROL']['sizeControl']
    assert result['questions']['Q5_DOWNSIDE_VOLATILITY_REGIME_AFTER_INDUSTRY_NEUTRALISATION']['byBenchmarkState']
    S.assert_no_forbidden_keys(result)


def test_eligibility_summary_counts_every_status_and_keeps_unknown():
    tickers, _ = membership(8)
    intervals = {t: [iv(SEMI)] for t in tickers}
    intervals['T7.KS'] = [iv(None, status='UNKNOWN')]
    m = I.membership_table({DATE: tickers}, intervals, CROSSWALK)
    panel = S.build_stock_panel(m, features(tickers), all_horizons(DATE, forward_for(tickers, [0.1] * 8)), windows())
    summary = S.eligibility_summary(panel)
    assert summary['stockDates'] == 8 and summary['byStatus'] == {'ELIGIBLE': 7, 'INELIGIBLE_UNCLASSIFIED': 1}
    assert summary['unknownRetainedInDenominator'] == 1 and summary['targetStatus']['CAP_WEIGHTED|H126']['MATURED'] == 7
    assert summary['targetStatus']['CAP_WEIGHTED|H126']['INELIGIBLE_STOCK_DATE'] == 1


def test_feature_registry_is_the_repository_raw_features_in_order():
    from pipeline import kr_value_quality_catalyst as F
    assert S.FEATURES == tuple(F.RAW_FEATURES) and len(S.FEATURES) == 11
    for name in ('bookToMarketProxy', 'earningsYieldProxy', 'ocfYieldProxy', 'netIncomeToAssets', 'ocfToAssets', 'negativeAccrualsToAssets',
                 'relative126', 'momentum121', 'ocfImprovementToAssets', 'negativeDownsideVol126', 'logAdv60'):
        assert name in S.FEATURES
    assert not any(any(x in name.lower() for x in ('ecos', 'fred', 'macro')) for name in S.FEATURES)
    assert S.SCIENTIFIC_STATUS == 'EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY'
