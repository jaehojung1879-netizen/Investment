import numpy as np
import pandas as pd
import pytest

from research.kr_us_replica_filter_v1 import kr


def test_matching_prioritizes_cardinality_filters_failures_and_respects_caliper():
    universe = pd.DataFrame({
        'industry': ['a', 'a', 'a', 'a', 'a', 'a', 'b'],
        '_mcap': [100., 200., 50., 150., 100., 49., 100.],
        'passFilter': [True, True, False, False, True, False, False],
    }, index=['a', 'b', 'lower', 'shared', 'pass', 'bad_caps', 'bad_industry'])
    matched, audit = kr.match(universe, ('a', 'b', 'pass'))
    assert len(matched.pairs) == 2
    assert set(dict(matched.pairs).values()) == {'lower', 'shared'}
    assert next(row for row in audit if row['passTicker'] == 'b')['withinCaliperFails'] == 1
    assert sum(row['reason'] == 'SCARCE_FAIL_PEER_ASSIGNED_TO_ANOTHER_PASS' for row in audit) == 1
    matched, _ = kr.match(universe, ('a', 'b'))
    assert matched.pairs == (('a', 'lower'), ('b', 'shared'))


def test_matching_minimizes_log_cap_loss_after_cardinality():
    universe = pd.DataFrame({
        'industry': ['a'] * 4, '_mcap': [100., 140., 110., 145.], 'passFilter': [True, True, False, False],
    }, index=['a', 'b', 'c', 'd'])
    matched, _ = kr.match(universe, ('b', 'a'))
    reversed_input, _ = kr.match(universe.iloc[::-1], ('b', 'a'))
    assert matched == reversed_input
    assert matched.pairs == (('b', 'd'), ('a', 'c'))


def test_etf_decomposition_and_stress_preserve_each_legs_weight():
    values = {kr.ETF: .10, 'a': .20, 'c': .15, 'd': .05}
    pairs = (('a', 'c'), ('b', 'd'))
    assert np.isnan(kr.from_pairs(pairs, values)['total'])
    stress = kr.stress_row(pd.Timestamp('2021-01-08'), 'all_pass', pairs, values,
                           {'b': {'hasEntryQuote': True}})
    assert stress['unknownPassWeight'] == .10
    assert stress['unknownFailWeight'] == 0.
    assert stress['bothZero_replacement'] == pytest.approx(0.)
    assert stress['bothZero_selection'] == pytest.approx(0.)
    assert stress['selectionHigh_selection'] == pytest.approx(.10)
    payoff = kr.from_pairs(pairs, dict(values, b=.30))
    assert payoff['passNet'] == pytest.approx(.13)
    assert payoff['failNet'] == pytest.approx(.10)
    assert payoff['total'] == pytest.approx(payoff['selection'] + payoff['replacement'])
    no_entry = kr.stress_row(pd.Timestamp('2021-01-08'), 'all_pass', pairs, values,
                             {'b': {'hasEntryQuote': False}})
    assert no_entry['hasUnquotedEntry']
    assert 'bothZero_selection' not in no_entry
