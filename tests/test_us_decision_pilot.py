"""Synthetic comparisons only: no repository market panel or sealed result."""
import numpy as np
import pandas as pd
import pytest

from pipeline import us_decision_pilot as P


def cross_section():
    n = 40
    data = {field: np.arange(n, dtype=float) + 1 for field in (*P.ACCOUNTING, 'momentum252', 'vol252')}
    data['sector'] = ['S' + str(i // 4) for i in range(n)]
    return pd.DataFrame(data, index=['T' + str(i).zfill(2) for i in range(n)])


def test_family_weights_and_same_complete_case_not_zero_imputation():
    raw = cross_section()
    raw.loc['T00', P.ACCOUNTING[0]] = np.nan
    x = P.scores(raw)
    assert 'T00' not in x.index and len(x) == 39
    np.testing.assert_allclose(x.B2, x[list(P.FAMILIES)].mean(axis=1))
    np.testing.assert_allclose(x.B1, x.price)
    for family in P.FAMILIES:
        np.testing.assert_allclose(x['WITHOUT_' + family], x[[f for f in P.FAMILIES if f != family]].mean(axis=1))
    assert raw.loc['T00', P.ACCOUNTING[0]] is np.nan or pd.isna(raw.loc['T00', P.ACCOUNTING[0]])


def test_price_features_have_no_future_leak_or_gap_filling():
    series = pd.Series(np.arange(1, 301, dtype=float), index=pd.bdate_range('2000-01-01', periods=300))
    day = series.index[260]
    expected = P.price_features(series, day)
    series.loc[series.index > day] = 1e20
    assert P.price_features(series, day) == expected
    assert P.price_features(series.drop(day), day) == {'momentum252': None, 'vol252': None}
    series.iloc[250] = np.nan
    assert P.price_features(series, day) == {'momentum252': None, 'vol252': None}


def test_forced_diagnostic_reuses_selector_and_caps_no_leverage():
    frame = P.scores(cross_section())
    a = P.allocation(frame, 'B2', concentrated=True)
    b = P.allocation(frame.sample(frac=1, random_state=1), 'B2', concentrated=True)
    assert a == b and len(a) == 5 and sum(a.values()) == pytest.approx(1)
    assert frame.loc[list(a)].sector.value_counts().max() <= 2
    with pytest.raises(ValueError, match='SIGNAL_UNAVAILABLE'):
        P.allocation(frame.iloc[:0], 'B2')


def test_self_financing_costs_and_same_close_not_used():
    dates = pd.bdate_range('2000-01-03', periods=5)
    close = pd.DataFrame({'A': [1, 100, 100, 100, 100]}, index=dates)
    orders = {dates[1]: {'A': 1.0}, dates[3]: {}}
    path = P.simulate(close, orders)
    expected = 1 / (1 + .0008) * (1 - .00083)
    assert path.nav.iloc[-1] == pytest.approx(expected)
    assert path.costInitialCapital.sum() == pytest.approx(1 - expected)
    assert path.names.iloc[0] == 0
    assert P.metrics(path)['cagr'] < 0
    assert P.simulate(close, orders, costed=False).nav.iloc[-1] == 1
    with pytest.raises(ValueError, match='INITIAL_CASH_ANCHOR'):
        P.simulate(close, {dates[0]: {'A': 1}})


def test_missing_held_or_entry_quote_never_last_price_exit():
    dates = pd.bdate_range('2000-01-03', periods=5)
    close = pd.DataFrame({'A': [10, 10, np.nan, 10, 10]}, index=dates)
    with pytest.raises(ValueError, match='UNRESOLVED_HELD'):
        P.simulate(close, {dates[1]: {'A': 1.0}, dates[3]: {}})
    with pytest.raises(ValueError, match='UNRESOLVED_ENTRY'):
        P.simulate(close, {dates[2]: {'A': 1.0}})


def test_labels_do_not_drop_terminal_security_to_improve_sample():
    frame = P.scores(cross_section())
    entry = pd.Series(10.0, index=frame.index)
    exit_ = pd.Series(np.arange(40, dtype=float) + 10, index=frame.index)
    result = P.label_reading(frame, entry, exit_)
    assert result['status'] == 'RESOLVED'
    assert result['names'] == len(frame)
    assert result['scores']['B1']['rankIC'] is None  # constant score: undefined, never zero
    exit_.iloc[0] = np.nan
    assert P.label_reading(frame, entry, exit_)['status'] == 'UNRESOLVED'
    assert P.label_reading(frame.iloc[:0], entry, exit_)['status'] == 'NOT_ESTIMABLE'


def test_invalid_targets_and_unmeasurable_statistics():
    for weights in ({'A': 1.1}, {'A': -.1}, {'A': float('nan')}):
        with pytest.raises(ValueError, match='INVALID_TARGET'):
            P.rebalance({}, weights, .0008, .00083)
    index = pd.bdate_range('2000-01-03', periods=10)
    path = P.simulate(pd.DataFrame(index=index), {})
    m = P.metrics(path)
    assert m['cagr'] == m['mdd'] == 0 and m['sharpeZeroRiskFree'] is None


def test_no_source_or_sealed_study_access_in_core():
    from pathlib import Path
    code = Path(P.__file__).read_text()
    assert 'read_csv(' not in code and 'read_bytes(' not in code
    assert 'us_cash_profitability_exploratory' not in code
    assert 'SealedReader' not in code


def test_vectorized_features_equal_prefix_core_and_ignore_future():
    from scripts import run_us_decision_pilot as S
    index = pd.bdate_range('2000-01-03', periods=310)
    close = pd.DataFrame({'A': np.exp(np.sin(np.arange(310) / 20) / 10 + np.arange(310) / 1000)}, index=index)
    momentum, vol = S.price_matrix_features(close)
    day = index[270]
    expected = P.price_features(close.A, day)
    assert momentum.at[day, 'A'] == pytest.approx(expected['momentum252'])
    assert vol.at[day, 'A'] == pytest.approx(expected['vol252'])
    close.loc[index > day] *= 100
    assert S.price_matrix_features(close)[1].at[day, 'A'] == pytest.approx(vol.at[day, 'A'])
    close.iloc[265, 0] = np.nan
    assert pd.isna(S.price_matrix_features(close)[0].at[day, 'A'])


def test_accounting_cache_strict_visibility_freshness_and_future_insertion():
    from scripts import run_us_decision_pilot as S
    from test_us_alpha_phase3 import chain, filing, FF
    rows = chain()
    for row in rows:
        row['cik'] = '123'
        row['statements']['bs'].append({'concept': 'us-gaap_StockholdersEquity', 'unit': 'usd', 'value': 500})
    cache = S.AccountingCache(rows)
    actual, ciks = cache.at('2021-06-01')
    assert actual['cashOperatingProfitability'] == pytest.approx(170 / 1100)
    assert actual['debtToEquity'] == pytest.approx(600 / 500)
    assert ciks == {'123'}
    assert cache.at('2021-10-01')[0]['cashOperatingProfitability'] is None
    # Going backwards after a stale query cannot poison a cached earlier reading.
    assert cache.at('2021-06-01')[0] == actual
    future = filing(2021, FF.Q2, assets=1, ocf=1e9)
    assert S.AccountingCache(rows + [future]).at('2021-06-01')[0] == actual
    assert cache.at('2021-05-10')[0]['reportEnd'] == '2020-12-31'
    assert cache.at('2021-05-11')[0]['reportEnd'] == '2021-03-31'


def test_contract_is_verified_before_any_source_or_outcome_read(monkeypatch):
    from scripts import run_us_decision_pilot as S
    calls = []
    def refuse(root):
        raise ValueError('PINNED_SOURCE_CHANGED')
    monkeypatch.setattr(S, 'verify_contract', refuse)
    monkeypatch.setattr(S, 'load_prices', lambda root: calls.append('price'))
    monkeypatch.setattr(S, 'load_filings', lambda root: calls.append('filing'))
    with pytest.raises(ValueError, match='PINNED_SOURCE_CHANGED'):
        S.build()
    assert calls == []


def test_synthetic_real_runner_completes_even_when_economic_gate_unavailable():
    from scripts import run_us_decision_pilot as S
    dates = pd.bdate_range('2000-01-03', periods=280)
    frame = P.scores(cross_section())
    close = pd.DataFrame({t: np.exp(np.arange(280) * (i + 1) / 100000) for i, t in enumerate(frame.index)}, index=dates)
    close['SPY'] = np.exp(np.arange(280) / 10000)
    signals = {dates[i]: frame for i in range(0, 279, 20)}
    strategies, labels, paths = S.evaluate(close, signals)
    for name in ('B0_SPY', 'B1_PRICE', 'B2_MULTIFACTOR', 'FORCED_5_PRICE_DIAGNOSTIC', 'FORCED_5_MULTIFACTOR_DIAGNOSTIC'):
        assert strategies[name]['status'] == 'ESTIMATED_DESCRIPTIVE'
        assert paths[name].index[0] == dates[0]
        assert paths[name].names.iloc[0] == 0
    assert strategies['B3_GATED_PRICE']['status'] == 'NOT_ESTIMABLE'
    assert 'cagr' not in strategies['B3_GATED_PRICE']
    assert labels['252']['resolvedCohorts'] > 0
    assert labels['252']['statusCounts']['NOT_MATURED'] > 0
    assert labels['63']['scores']['B1']['meanRankIC'] is None  # truly constant signal
    assert len(paths) == 10


def test_pinned_contract_and_no_restricted_executor_imports():
    from scripts import run_us_decision_pilot as S
    protocol = S.verify_contract()
    assert protocol['sourceScope']['status'] == 'READ_ONLY_INPUT_REUSE_AUTHORIZED'
    code = S.Path(S.__file__).read_text()
    for forbidden in ('us_cash_profitability_exploratory', 'create_remote_lock', 'execute_study', 'signal-history/'):
        assert forbidden not in code
