"""Single-slot economics, fixed prefix and common-date denominators."""
import numpy as np
import pandas as pd
import pytest

from research.kr_s2_single_slot_matched_v1 import analyze as A


def test_every_rank_replaces_only_one_stock_and_keeps_original_prefix_and_etf():
    names = ['AAA', 'BBB', 'CCC', 'DDD', 'EEE']
    for k in range(1, 6):
        b, s, q = A.single_slot(names, 'PEER', k)
        assert b == A.L.book(names[:k-1])
        assert s == A.L.book(names[:k])
        assert set(q) - {A.L.M.ETF} == set(names[:k-1]) | {'PEER'}
        assert q.get(A.L.M.ETF, 0.) == pytest.approx(1-.2*k)
        assert s.get(A.L.M.ETF, 0.) == q.get(A.L.M.ETF, 0.)
    with pytest.raises(AssertionError):
        A.single_slot(names, 'AAA', 3)


def test_costed_single_replacement_equals_difference_of_prefix_increments():
    e, x = pd.to_datetime(['2024-01-02', '2024-07-02'])
    # Earlier S2 and peer positions have deliberately very different returns.
    cl = pd.DataFrame({'AAA': [100., 210.], 'BBB': [100., 50.], 'CCC': [100., 130.],
                       'X': [100., 70.], 'Y': [100., 170.], 'Z': [100., 115.], A.L.M.ETF: [100., 108.]}, index=[e, x])
    returns = {t: A.L.asset_return(cl, t, e, x) for t in cl}
    b, s, q = A.single_slot(['AAA', 'BBB', 'CCC'], 'Z', 3)
    B, S, Q = [A.portfolio_return(w, returns) for w in (b, s, q)]
    m3 = A.portfolio_return(A.L.book(['X', 'Y', 'Z']), returns)
    m2 = A.portfolio_return(A.L.book(['X', 'Y']), returns)
    assert S-Q == pytest.approx(.2*(returns['CCC'][1]-returns['Z'][1]))
    assert (S-B)-(m3-m2) == pytest.approx(S-Q)
    assert S-Q != pytest.approx(S-m3)  # replacing the WHOLE prefix would answer a different question
    assert S-B == pytest.approx((S-Q)+(Q-B))
    assert returns['CCC'][2] > returns[A.L.M.ETF][2]


def test_common_dates_exclude_absent_and_unpriceable_and_size_filter_is_separate():
    valid = np.ones((5, 5), dtype=bool)
    present = np.ones_like(valid)
    within = np.ones_like(valid)
    present[0, 4] = False
    valid[1, 2] = False
    within[2, 1] = False
    own, common, capped_common = A.select_masks(valid, present, within)
    assert own[:, 0].sum() == 5
    assert own[:, 4].sum() == 4
    assert common.tolist() == [False, False, True, True, True]
    assert capped_common.tolist() == [False, False, False, True, True]
