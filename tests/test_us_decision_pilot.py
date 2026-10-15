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


def test_refusal_opens_only_explicit_contracts_not_price_alias_or_results(monkeypatch):
    import json
    from pathlib import Path
    from scripts import run_us_decision_pilot as S
    protocol = json.loads((S.ROOT / S.PROTOCOL).read_bytes())
    allowed = {S.ROOT / p for p in protocol['protectionSources']}
    allowed.update(S.ROOT / p for p in (S.PROTOCOL, 'pipeline/us_decision_pilot.py',
        'scripts/run_us_decision_pilot.py', 'data/research/us-dual-benchmark-v1/manifest.json'))
    original = Path.read_bytes
    reads = []
    def tracked(path):
        assert path in allowed, 'unexpected protected payload access: ' + str(path)
        reads.append(path)
        return original(path)
    monkeypatch.setattr(Path, 'read_bytes', tracked)
    result = S.build()
    assert reads and result['realOutcomeReads'] == result['sealedResultReads'] == 0
    assert result['newComparisonBudgetConsumed'] is False
    assert result['currentCandidates']['candidates'] == []
    assert result['currentCandidates']['status'] == 'CURRENT_CANDIDATES_NOT_VERIFIED'
    assert all(v is None for s in result['strategies'].values() for v in s['metrics'].values())
    assert result['annualMissingness']['years'] is None


def test_refusal_reproduces_committed_output_and_never_fabricates_zero_returns():
    import csv
    import json
    from scripts import run_us_decision_pilot as S
    path = S.ROOT / 'docs/results/us-decision-pilot-v1'
    assert S.build() == json.loads((path / 'result.json').read_bytes())
    with (path / 'strategy-metrics.csv').open() as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == len(S.STRATEGIES)
    assert all(r['status'] == 'NOT_ESTIMABLE' for r in rows)
    assert all(r['cagr'] == '' and r['meanCash'] == '' for r in rows)
