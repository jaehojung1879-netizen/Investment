"""Accounting identities and original-engine refusal for the US batch study."""
import numpy as np
import pandas as pd
import pytest

from research.kr_us_strategy_batch_v1 import us


def test_stock_normalization_keeps_relative_weights_and_empty_fallback():
    native = {"A": .3, "B": .5, "SPY": .2}
    assert us.normalize_stock(native, .2) == pytest.approx({"A": .075, "B": .125, "SPY": .8})
    assert us.normalize_stock({"SPY": 1}, .5) == {"SPY": 1}


def test_postcutoff_split_supplement_is_idempotent_and_undoes_future_scale():
    import hashlib
    import json
    from research.kr_us_strategy_batch_v1 import us_prepare as P
    stamp = 1790861400
    event = {"date": stamp, "numerator": 6665, "denominator": 1000, "splitRatio": "6665:1000"}
    body = json.dumps({"chart": {"result": [{"meta": {"symbol": "CTVA"},
                                             "events": {"splits": {str(stamp): event}}}]}}).encode()
    sha = hashlib.sha256(body).hexdigest()
    assert P.verified_ctva_event(body, sha) == event
    with pytest.raises(ValueError, match="SHA256"):
        P.verified_ctva_event(body + b" ", sha)
    old = {"rows": [[1500000000, 29/6.665]], "splits": []}
    fixed = P.supplement_record(old, event, sha)
    assert old["splits"] == [] and fixed["rows"] == old["rows"]
    assert P.supplement_record(fixed, event, sha) == fixed
    assert P.split_factor_after(fixed, "2026-09-01") == pytest.approx(6.665)
    reader = object.__new__(P.F.AsTraded)
    reader.series = {"CTVA": pd.Series([29/6.665], index=pd.to_datetime(["2020-01-03"]))}
    reader.splits = {"CTVA": [(pd.Timestamp("2026-10-01"), 6.665)]}
    assert reader.close_on("CTVA", pd.Timestamp("2020-01-03")) == pytest.approx(29)


def test_daily_costed_path_endpoint_and_initial_cost_drawdown():
    prices = pd.DataFrame({"A": [100, 90, 120], "SPY": [100, 110, 110]})
    result = us.fixed_path(prices, {"A": .2, "SPY": .8})
    expected_gross = .2 * .2 + .8 * .1
    assert result["net"] == pytest.approx(us.EV.net(expected_gross), abs=1e-14)
    wealth = np.array([1, 1-us.EV.BUY, (1-us.EV.BUY)*1.06,
                       (1-us.EV.BUY)*1.12*(1-us.EV.SELL)])
    assert result["mdd"] == pytest.approx((wealth/np.maximum.accumulate(wealth)-1).min())


def test_internal_marks_can_carry_but_missing_terminal_is_unresolved():
    prices = pd.DataFrame({"A": [100, np.nan, 120]})
    result = us.fixed_path(prices, {"A": 1})
    assert result["internalMissingMarks"] == 1
    assert result["net"] == pytest.approx(us.EV.net(.2))
    prices.iloc[-1, 0] = np.nan
    assert us.fixed_path(prices, {"A": 1}) is None


def test_confirmation_neutral_is_hash_order_with_existing_sector_cap():
    frame = pd.DataFrame({"sector": ["S1"]*10 + ["S2"]*10 + ["S3"]*10,
                          "confirmed": [False]*5 + [True]*25}, index=[f"T{i:02}" for i in range(30)])
    names = us.neutral_names(frame, "2020-01-03", True)
    assert len(names) == 5
    assert frame.loc[names, "confirmed"].all()
    assert frame.loc[names, "sector"].value_counts().max() <= 2
    assert names == us.neutral_names(frame.sample(frac=1, random_state=9), "2020-01-03", True)


def test_nav_uses_same_costed_spy_baseline_and_refuses_missing_held_quote():
    days = pd.bdate_range("2020-01-01", periods=12)
    prices = pd.DataFrame({"SPY": np.linspace(100, 110, len(days)), "A": np.linspace(100, 120, len(days))}, index=days)
    decisions = days[[0, 4, 8]]
    spy = {d: {"SPY": 1} for d in decisions}
    _, _, result, _ = us.ledger_one((us.ETF, 2, prices, spy, decisions, None))
    assert result["full"]["cagrGap"] == pytest.approx(0, abs=1e-12)
    stocks = {d: {"A": 1} for d in decisions}
    prices.loc[days[3], "A"] = np.nan
    _, _, result, path = us.ledger_one(("TEST", 2, prices, stocks, decisions, None))
    assert result["status"] == "NOT_ESTIMABLE"
    assert "UNRESOLVED_HELD_OBSERVATION" in result["reason"]
    assert path is None
