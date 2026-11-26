"""Construction, missing-business state, and cost-path checks for the registered KR batch."""
import numpy as np
import pandas as pd
import pytest

from research.kr_us_strategy_batch_v1 import kr


def test_fixed_total_uses_actual_names_and_preserves_stock_budget():
    assert kr.make_book([], 'FIXED20') == {kr.M.ETF: 1.}
    assert kr.make_book(['A', 'B'], 'FIXED20') == {'A': .1, 'B': .1, kr.M.ETF: .8}
    assert kr.make_book(['A', 'B'], 'SLOT20') == {'A': .2, 'B': .2, kr.M.ETF: .6}
    assert kr.make_book(['A'], 'FIXED20') == kr.make_book(['A'], 'SLOT20')


def test_business_absence_is_not_failure_and_original_value_is_retained():
    frame = pd.DataFrame({'ticker': ['A', 'B', 'C', 'D'], '_q': True, 'industry': 'X',
                          kr.VALUE: [.9, .8, .7, .6], 'b08Confirmed': [1., 0., 0., 1.],
                          'C01_returnOnAssets': [1., 1., -1., 1.],
                          'C05_ocfToAssets': 1., 'C14_ocfImprovement': [1., np.nan, 1., 1.],
                          'H01_industryRelMom126': [.4, .3, .2, .1],
                          'A09_industryRelativeMomentum126': [.4, .3, .2, .1],
                          'A07_momentum12_1': [.4, .3, .2, .1], 'B01_bookToMarket': [.4, .3, .2, .1],
                          'C02_returnOnEquity': [.4, .3, .2, .1], 'F02_downsideVol126': [.4, .3, .2, .1]})
    names, _, audit = kr.selectors(frame, pd.Timestamp('2020-01-03'))
    assert names['S2'] == ['A', 'D']
    assert names['VALUE_ORIGINAL'] == ['A', 'B', 'C', 'D']
    assert names['VALUE_COMPLETE'] == ['A', 'C', 'D']
    assert set(names['QUALITY_NEUTRAL']) == {'A', 'C', 'D'}
    assert set(names['CONFIRM_NEUTRAL']) == {'A', 'D'}
    assert audit['businessUnmeasured'] == 1


def prices(values):
    dates = pd.bdate_range('2020-01-01', periods=len(values))
    frame = pd.DataFrame({'A': values, kr.M.ETF: 100.}, index=dates)
    volume = pd.DataFrame(1., index=dates, columns=frame.columns)
    px = kr.C.Prices(frame, volume, dates, pd.Series(0., index=dates))
    return dates, frame, px


def test_daily_wealth_charges_entry_and_final_exit_only_and_keeps_carry_marks():
    dates, frame, px = prices([100., 80., np.nan, 120.])
    payoff, reason = kr.asset_payoff(frame, px, 'A', dates[0], dates[-1])
    assert reason is None
    buy = kr.C.cost_rate('A', 'buy', dates[0])
    sell = kr.C.cost_rate('A', 'sell', dates[-1])
    assert payoff['wealth'][0] == pytest.approx(1-buy)
    assert payoff['wealth'][1] == payoff['wealth'][2] == pytest.approx(.8-buy)
    assert payoff['net'] == pytest.approx(.2-buy-1.2*sell)
    result = kr.portfolio_payoff({'A': 1.}, {'A': payoff})
    assert result['mdd'] == pytest.approx(-.2-buy)


def test_unresolved_entry_abstains_instead_of_becoming_etf():
    dates, frame, px = prices([np.nan, 100., 120.])
    payoff, reason = kr.asset_payoff(frame, px, 'A', dates[0], dates[-1])
    assert payoff is None
    assert reason == 'ENTRY_OR_EXIT_PRICE_MISSING'
    assert kr.portfolio_payoff({'A': .2, kr.M.ETF: .8}, {'A': None}) is None


def test_policy_warmup_ends_at_sufficient_fit_even_when_etf_is_selected():
    trace = pd.DataFrame({'date': pd.to_datetime(['2019-01-04', '2020-01-03']),
                          'sufficient': [False, True], 'chosen': ['ETF', 'ETF']})
    assert kr.policy_start({'trace': trace}) == pd.Timestamp('2020-01-03')
