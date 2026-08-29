"""What a per-region turnover number has to mean.

`estimate_transaction_cost` multiplies its turnover by ONE candidate's position
and subtracts the result from that candidate's expected return. So the quantity
it needs is a share of the SLEEVE — "of the weight held in this region, what
fraction is traded per rebalance" — not the region's share of portfolio
turnover. The two disagree by more than bookkeeping, and the wrong one is
quietly plausible, so the boundaries are pinned here.
"""
from __future__ import annotations

import pytest

from pipeline import portfolio_validation as PV


CFG = {"transactionCosts": {
    "US": {"commissionBps": 5, "sellTaxBps": 3, "spreadBps": 10},
    "KR": {"commissionBps": 5, "sellTaxBps": 20, "spreadBps": 12}}}


def _rates(weights, prior, regions):
    candidates = [{"ticker": t, "region": r} for t, r in regions.items()]
    return _PVcost(weights, prior, candidates)["turnoverByRegion"]


def _PVcost(weights, prior, candidates):
    return PV._turnover_cost(weights, prior, candidates, CFG)


def test_a_sleeve_replaced_whole_reads_one_hundred_percent():
    """Not 5% because it was 10% of the book — the position pays the full trip."""
    rates = _rates({"A": 0.10}, {"B": 0.10}, {"A": "KR", "B": "KR"})
    assert rates["KR"] == pytest.approx(1.0)


def test_a_sleeve_sold_out_reads_one_hundred_percent():
    rates = _rates({}, {"B": 0.20}, {"B": "KR"})
    assert rates["KR"] == pytest.approx(1.0)


def test_a_sleeve_opened_from_nothing_reads_one_hundred_percent():
    """Averaging the two ends is what keeps both boundaries finite."""
    rates = _rates({"A": 0.20}, {}, {"A": "KR"})
    assert rates["KR"] == pytest.approx(1.0)


def test_an_untouched_sleeve_reads_zero():
    rates = _rates({"A": 0.20}, {"A": 0.20}, {"A": "US"})
    assert rates["US"] == pytest.approx(0.0)


def test_a_region_held_at_neither_end_is_absent_not_zero():
    """A rebalance that did not touch a region is not a 0% observation for it.

    Counting it as one would drag the region's hurdle down in exactly the
    periods the strategy was avoiding that region.
    """
    rates = _rates({"A": 0.20}, {"A": 0.20}, {"A": "US"})
    assert "KR" not in rates


def test_one_region_churning_does_not_move_the_other():
    rates = _rates({"U1": 0.20, "K1": 0.10}, {"U2": 0.20, "K1": 0.10},
                   {"U1": "US", "U2": "US", "K1": "KR"})
    assert rates["US"] == pytest.approx(1.0)
    assert rates["KR"] == pytest.approx(0.0)


def test_the_sleeve_rate_exceeds_the_portfolio_rate_when_cash_is_held():
    """Why one number understated both sleeves.

    The portfolio measure divides by the whole book including cash; the sleeve
    measure divides by the sleeve. With a cash floor the second is always the
    larger, so a portfolio figure applied to a position is a discount.
    """
    candidates = [{"ticker": t, "region": "US"} for t in ("A", "B")]
    # Half the book in cash; the equity half is replaced entirely.
    cost = _PVcost({"A": 0.50}, {"B": 0.50}, candidates)

    assert cost["turnoverByRegion"]["US"] == pytest.approx(1.0)
    assert cost["turnover"] == pytest.approx(0.5)
    assert cost["turnoverByRegion"]["US"] > cost["turnover"]


def test_regional_rates_do_not_sum_to_the_portfolio_rate():
    """A property of the question, not a rounding gap — cash has no region."""
    candidates = [{"ticker": t, "region": r}
                  for t, r in {"A": "US", "B": "US", "K": "KR"}.items()]
    cost = _PVcost({"A": 0.30, "K": 0.20}, {"B": 0.30, "K": 0.20}, candidates)

    assert sum(cost["turnoverByRegion"].values()) != pytest.approx(cost["turnover"])


# --------------------------------------------------------------------------- #
# Aggregation across a path
# --------------------------------------------------------------------------- #
def _row(date, end, weights, regions):
    return {"date": date, "endDate": end, "weights": weights,
            "regionByTicker": regions, "grossReturn": 0.0, "grossExcessReturn": 0.0,
            "benchmarkReturn": 0.0, "top1": max(weights.values(), default=0),
            "top3": sum(weights.values()), "effectiveNames": 1.0}


def test_the_initial_build_is_not_counted_as_a_rebalance():
    """It is paid once; the rate it feeds is multiplied by every cycle."""
    rows = [_row("2020-01-01", "2020-04-01", {"A": 0.5}, {"A": "US"}),
            _row("2020-04-01", "2020-07-01", {"A": 0.5}, {"A": "US"}),
            _row("2020-07-01", "2020-10-01", {"A": 0.5}, {"A": "US"})]
    out = PV._path_metrics(rows, 63, CFG)

    # Two rebalances, both no-ops. Counting the opening buy would report 33%.
    assert out["turnoverRebalances"] == 2
    assert out["averageTurnoverPct"] == pytest.approx(0.0)
    assert out["averageTurnoverPctByRegion"]["US"] == pytest.approx(0.0)


def test_the_path_reports_each_region_and_how_often_it_measured_it():
    rows = [_row("2020-01-01", "2020-04-01", {"A": 0.4, "K": 0.2},
                 {"A": "US", "K": "KR"}),
            _row("2020-04-01", "2020-07-01", {"B": 0.4, "K": 0.2},
                 {"B": "US", "K": "KR"}),
            _row("2020-07-01", "2020-10-01", {"C": 0.4, "K": 0.2},
                 {"C": "US", "K": "KR"})]
    out = PV._path_metrics(rows, 63, CFG)

    # US replaced whole at both rebalances; KR untouched at both.
    assert out["averageTurnoverPctByRegion"] == {"US": 100.0, "KR": 0.0}
    assert out["turnoverRebalancesByRegion"] == {"US": 2, "KR": 2}
