"""Invented data only; never call a sealed study or load real Git prices in tests."""

from copy import deepcopy

import numpy as np
import pandas as pd
import pytest

from research.historical_alpha_discovery_v1 import run as R


def fixture(n=600):
    days = pd.bdate_range("2013-01-01", periods=n)
    close = pd.DataFrame({"TEST.KS": 100 * np.exp(np.arange(n) * 0.001)}, index=days)
    m = {
        "close": close,
        "open": close / 1.0005,
        "volume": close * 0 + 2e7,
        "listedShares": close * 0 + 1e8,
        "adjusted": close.copy(),
        "benchmark": pd.Series(np.exp(np.arange(n) * 0.0002), index=days),
    }
    members = [{"ticker": "TEST.KS", "name": "가상보통", "marketCap": 1e12, "rank": 10}]
    industries = {"TEST.KS": [{"start": None, "end": None, "research_industry_id": "SYN"}]}
    return m, members, industries


def test_feature_attribution_and_no_future_read():
    m, members, industries = fixture()
    a, reasons = R.features_at(m, 300, members, industries)
    assert not reasons and len(a) == 1
    assert a[0]["intraday"] == pytest.approx(126 * np.log(1.0005))
    assert a[0]["intraday"] + a[0]["overnight"] == pytest.approx(0.126)
    for k in ("close", "open", "volume", "listedShares"):
        m[k].iloc[301:] = np.nan
    assert R.features_at(m, 300, members, industries)[0] == a


@pytest.mark.parametrize("column", ["close", "open", "volume", "listedShares"])
def test_interior_required_session_cannot_be_counted_away(column):
    m, members, industries = fixture()
    m[column].iloc[200] = np.nan
    assert len(m[column]) > 300
    rows, reasons = R.features_at(m, 400, members, industries)
    assert not rows and reasons["MISSING_OR_UNTRADED_REQUIRED_KRX_SESSION"] == 1


def test_signal_time_corporate_action_ambiguity_is_missing():
    m, members, industries = fixture()
    m["listedShares"].iloc[290:] *= 2
    rows, reasons = R.features_at(m, 300, members, industries)
    assert not rows and reasons["CORPORATE_ACTION_AMBIGUITY_IN_PAST_WINDOW"] == 1


def test_missing_input_is_not_zero_factor_or_opposite_state():
    m, members, industries = fixture()
    m["volume"].iloc[250] = 0
    rows, reasons = R.features_at(m, 300, members, industries)
    assert not rows and reasons
    assert R.select(rows, "INTRADAY") == []


def test_industry_limit_and_five_slots_without_outcome_filter():
    rows = [
        {"ticker": str(i), "momentum": 1 - i / 100, "intraday": 1 - i / 100, "industry": str(i % 3)} for i in range(30)
    ]
    picks = R.select(rows, "INTRADAY")
    assert len(picks) == 5
    assert max(R.Counter(r["industry"] for r in picks).values()) <= 2
    assert R.select([{**r, "momentum": -1} for r in rows], "MOMENTUM") == []


def test_unknown_terminal_payoff_blocks_never_zero_last_or_replacement():
    m, _, _ = fixture()
    p, reason = R.path_for(m, "TEST.KS", 300, 426, {"TEST.KS": str(m["close"].index[400].date())})
    assert p is None and reason == "UNRESOLVED_TERMINAL_CONSIDERATION"
    row = {"ticker": "TEST.KS", "median60": 1e12}
    path, failures, _ = R.block_path(m, [row], "INTRADAY", 300, 426, {"TEST.KS": "2014-01-01"})
    assert path is None and len(failures) == 1


@pytest.mark.parametrize("kind", ["missing", "halt"])
def test_held_interior_gap_blocks_whole_path(kind):
    m, _, _ = fixture()
    if kind == "missing":
        m["adjusted"].iloc[330] = np.nan
    else:
        m["volume"].iloc[330] = 0
    p, reason = R.path_for(m, "TEST.KS", 300, 426, {})
    assert p is None and reason


def test_funded_budget_and_tax_costs_and_stress_monotonicity():
    m, _, _ = fixture()
    row = {"ticker": "TEST.KS", "median60": 1e12}
    p, failures, costs = R.block_path(m, [row], "INTRADAY", 300, 426, {})
    assert not failures and p[0] == pytest.approx(1 / (1 + 0.00115))
    stock = 0.2 * np.exp(0.126) / (1 + 0.00115) * (1 - (11.5 + 30) / 10000)
    etf = 0.8 * np.exp(0.0252) / (1 + 0.00115) * (1 - 0.00115)
    assert p[-1] == pytest.approx(stock + etf)
    stress, _, _ = R.block_path(m, [row], "INTRADAY", 300, 426, {}, multiplier=2)
    assert stress[-1] < p[-1] and costs["entryFraction"] > 0 and costs["exitFraction"] > 0


def test_passive_etf_does_not_pay_rebalance_fees():
    m, _, _ = fixture()
    first, _, _ = R.block_path(m, [], "ETF", 200, 300, {}, charge_entry=True, charge_exit=False)
    last, _, _ = R.block_path(m, [], "ETF", 300, 400, {}, charge_entry=False, charge_exit=True)
    whole, _, _ = R.block_path(m, [], "ETF", 200, 400, {})
    assert first[-1] * last[-1] == pytest.approx(whole[-1])


def test_passive_etf_mid_block_has_no_trade_turnover():
    m, _, _ = fixture()
    p, failures, costs = R.block_path(m, [], "ETF", 200, 300, {}, charge_entry=False, charge_exit=False)
    assert not failures and p[-1] > 1
    assert costs == {"entryFraction": 0.0, "exitFraction": 0.0, "grossTurnover": 0.0}


def test_capacity_uses_actual_compounded_notional_and_raw_value():
    m, _, _ = fixture()
    row = {"ticker": "TEST.KS", "median60": 1e9}
    p, f, _ = R.block_path(m, [row], "INTRADAY", 300, 426, {}, nav_krw=1e9)
    assert p is None and f[0]["reason"] == "REALIZED_CAPACITY_EXCEEDED"


def test_only_two_valid_pairs_among_104_cannot_get_interval_or_support():
    rows = []
    for i in range(104):
        for book in R.BOOKS:
            rows.append(
                {
                    "analysisWindow": "FULL",
                    "sample": R.SPEC["samples"][0],
                    "horizon": 126,
                    "costMultiplier": 1,
                    "entry": f"{2000 + i // 10}-01-{1 + i % 10:02d}",
                    "book": book,
                    "netReturn": 0.2 if i < 2 else None,
                }
            )
    result = [
        r
        for r in R.paired_summary(rows)
        if r["book"] == "INTRADAY"
        and r["horizon"] == 126
        and r["costMultiplier"] == 1
        and r["analysisWindow"] == "FULL"
    ][0]
    assert result["validPairs"] == 2 and result["descriptiveYearBootstrap95"] is None
    assert result["evidence"] == "EXPLORATORY_DESCRIPTIVE"


def test_conditional_exclusion_explicit_and_not_hidden_in_strict_features():
    m, members, industries = fixture()
    assert len(R.features_at(m, 300, members, industries)[0]) == 1
    rows, reasons = R.features_at(m, 300, members, industries, conditional_exclusions={"TEST.KS"})
    assert not rows and reasons["EX_POST_CONDITIONAL_SAMPLE_EXCLUSION"] == 1


def test_metric_compounding_drawdown_and_missing_refusal():
    dates = pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-03"])
    stats = R.metrics([1, 1.2, 0.9], dates)
    assert stats["totalReturn"] == pytest.approx(-0.1)
    assert stats["mdd"] == pytest.approx(-0.25)
    with pytest.raises(ValueError):
        R.metrics([1, np.nan, 0.9], dates)


def test_frozen_data_commit_spec_has_no_live_or_historical_executor_imports():
    import ast

    tree = ast.parse(R.Path(R.__file__).read_text())
    imports = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    assert not any(x and (x.startswith("pipeline") or "c1" in x) for x in imports)
    assert len(R.SPEC["dataCommit"]) == 40
    assert R.SPEC["evidenceClass"].startswith("EXPLORATORY")
    assert deepcopy(R.SPEC)["production"].startswith("NONE")
