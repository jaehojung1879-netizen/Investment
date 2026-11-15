"""Synthetic-only checks: chronology, class grouping, path gaps and fees."""
import numpy as np
import pytest

from pipeline import replay_calendar as RC
from research.us_topk_market_cap_v1.inputs import invert_forward
from research.us_topk_market_cap_v1.performance import net, run_nav, summarize, weights
from research.us_topk_market_cap_v1.rank import capitalize, latest_facts


def test_invert_split_and_cash_dividend_without_using_future_price():
    # Raw 100 -> 50 after a 2:1 split, then ex-dividend 49 with $1 paid.
    rows = {"2024-01-02": {"Close": 100.}, "2024-01-03": {"Close": 100.},
            "2024-01-04": {"Close": 100.}, "2024-01-05": {"Close": 9000.}}
    events = {"2024-01-03": {"split": 2.}, "2024-01-04": {"dividend": 1.}}
    actual = invert_forward(rows, events, "2024-01-04")
    assert list(actual.values()) == pytest.approx([100., 50., 49.])
    assert "2024-01-05" not in actual


def test_shares_are_strictly_visible_actual_levels_not_eps_averages():
    facts = {"1": {"facts": [
        {"filed": "2024-01-10", "end": "2023-12-31", "val": 100, "tag": "dei:EntityCommonStockSharesOutstanding", "accn": "A", "receipt": "a"},
        {"filed": "2024-01-19", "end": "2024-01-15", "val": 999, "tag": "dei:EntityCommonStockSharesOutstanding", "accn": "B", "receipt": "b"},
    ]}}
    assert latest_facts("1", "2024-01-19", facts, {})["parts"][0]["value"] == 100
    assert latest_facts("1", "2024-01-20", facts, {})["parts"][0]["value"] == 999


def test_alphabet_company_cap_uses_distinct_quotes_and_is_held_once():
    filings = {"1652044": [{"status": 200, "filed": "2024-01-10", "accn": "A", "sha256": "a",
        "facts": [{"tag": "dei:EntityCommonStockSharesOutstanding", "end": "2024-01-05", "value": n,
                   "dims": [{"axis": "us-gaap:StatementClassOfStockAxis", "member": m}]}
                  for n, m in [(5, "us-gaap:CommonClassAMember"), (1, "us-gaap:CommonClassBMember"),
                               (4, "goog:CapitalClassCMember")]]}]}
    prices = {"GOOG": {"2024-01-19": 110.}, "GOOGL": {"2024-01-19": 100.}}
    row = capitalize("1652044", "2024-01-19", ["GOOGL", "GOOG"], prices, {}, {}, filings)
    assert row["cap"] == 1040  # (5 A + 1 B) * 100 + 4 C * 110
    assert row["ticker"] == "GOOG"
    assert weights([row], "equal_company") == {"GOOG": 1.0}


def test_unresolved_up_c_units_cannot_be_assumed_one_for_one():
    filings = {"1973266": [{"status": 200, "filed": "2024-01-10", "accn": "A", "sha256": "a", "facts": [
        {"tag": "dei:EntityCommonStockSharesOutstanding", "end": "2024-01-05", "value": 100,
         "dims": [{"axis": "us-gaap:StatementClassOfStockAxis", "member": "us-gaap:CommonClassBMember"}]}]}]}
    with pytest.raises(ValueError, match="UP_C_ECONOMIC"):
        capitalize("1973266", "2024-01-19", ["TKO"], {"TKO": {"2024-01-19": 20}}, {}, {}, filings)


class FlatReturns:
    calendar = [str(d.date()) for d in RC.sessions("2024-01-01", "2025-12-31", "US")]

    def get(self, ticker, start, end):
        return {"status": "COMPLETE", "gross": 0.0}


def rank(entry, status="VERIFIED_TEST"):
    return {"entry": entry, "status": status, "selected": [{"ticker": "SYN", "cap": 100.}]}


def test_nav_cost_is_self_financing_and_flat_book_is_not_recharged_each_week():
    result = run_nav([rank("2024-01-08"), rank("2024-01-16"), rank("2024-01-22")], "equal_company", FlatReturns())
    assert len(result) == 1
    assert result[0]["nav"] == pytest.approx(1 / 1.0008)
    assert result[0]["spy_nav"] == pytest.approx(result[0]["nav"])
    assert result[0]["weekly"][1]["fee"] == pytest.approx(0.)
    assert net(0.) == pytest.approx(.99917 / 1.0008 - 1)
    assert net(0., cash_wealth=1.) == pytest.approx(1 / 1.0008 - 1)


def test_nav_never_bridges_unverified_rank_or_replaces_missing_security():
    ranks = [rank("2024-01-08"), rank("2024-01-16"), rank("2024-01-22", "MISSING_COMPANY_CAP"),
             rank("2024-01-29"), rank("2024-02-05")]
    result = run_nav(ranks, "equal_company", FlatReturns())
    assert [(r["first_entry"], r["last_mark"]) for r in result] == [
        ("2024-01-08", "2024-01-22"), ("2024-01-29", "2024-02-05")]


def test_empty_mature_measurement_is_missing_and_not_zero():
    result = summarize([{"horizon": 252, "end": "2027-01-01", "status": "HOLDING_NOT_MATURE"}], [])
    assert result["mature_denominator"] == 0
    assert result["mean_excess"] is None
    assert result["win_rate"] is None
    assert result["moving_block_mean_ci95"] is None


def test_overlapping_cohorts_are_not_counted_as_independent_observations():
    cal = FlatReturns.calendar
    entries = list(range(20, 280, 5))
    rows = [{"horizon": 126, "entry": cal[i], "end": cal[i + 126], "signal": cal[i - 1],
             "status": "COMPLETE", "excess": .01, "net_return": .02, "spy_net_return": .01}
            for i in entries]
    result = summarize(rows, cal)
    assert result["complete_cohorts"] == 52
    assert result["disjoint_holding_intervals"] == 2
    assert result["block_length_weeks"] == 26
    assert np.isclose(result["mean_excess"], .01)
