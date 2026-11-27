"""Regression tests for conditional bounds and observation abstention."""

from dataclasses import replace

import pytest

from feasible import Bounds, Product, Scenario, evaluate


def scenario():
    return Scenario(
        products=(Product(1, 50, (0,) * 4, (0, 10, 0, 0), (0,) * 4, Bounds(3, 4), Bounds(1, 2)),),
        shared_hours=(15,) * 4,
        tax=0.25,
        fixed_opex=Bounds(6, 8),
        depreciation=Bounds(0, 2),
        maintenance_capex=Bounds(5, 6),
        growth_capex=Bounds(0, 5),
        incremental_nwc=Bounds(-1, 2),
        discount=Bounds(0.07, 0.13),
        terminal_growth=Bounds(0.01, 0.04),
        terminal_roic=Bounds(0.06, 0.15),
        terminal_nopat=Bounds(10, 20),
    )


def test_direction_and_gap_are_conservative():
    physical = scenario()
    high = evaluate(physical, Bounds(1000, 1100))
    low = evaluate(physical, Bounds(-1000, -900))
    assert high["classification"] == "MARKET_ABOVE_E_CONDITIONAL"
    assert high["conditional_gap"] == pytest.approx(1000 - high["value_outer"][1])
    assert low["classification"] == "MARKET_BELOW_E_CONDITIONAL"
    assert low["conditional_gap"] == pytest.approx(low["value_outer"][0] + 900)
    fixed_rate = evaluate(replace(physical, discount=Bounds(0.1, 0.1)), Bounds(0, 1000))
    broad_min, broad_max = high["value_outer"]
    fixed_min, fixed_max = fixed_rate["value_outer"]
    assert broad_min <= fixed_min <= fixed_max <= broad_max


def test_overlap_witness_respects_cumulative_backlog_and_hours():
    physical = scenario()
    result = evaluate(physical, Bounds(0, 500))
    assert result["classification"] == "OVERLAP_WITNESS_ABSTAIN"
    witness = result["witness"]
    assert 0 <= witness["ev"] <= 500
    q = witness["product_quarter_units"]
    assert len(q) == 4 and all(0 <= v <= 15 + 1e-7 for v in q)
    assert sum(q[:2]) <= 40 + 1e-7 and sum(q) <= 40 + 1e-7


def test_outer_overlap_alone_does_not_prove_feasibility():
    result = evaluate(scenario(), Bounds(300, 320))
    assert result["classification"] == "OUTER_OVERLAP_UNRESOLVED"
    assert result["witness"] is None
    assert result["conditional_gap"] is None


def test_contradictory_deliveries_do_not_create_a_valuation_signal():
    physical = scenario()
    invalid = replace(physical.products[0], demand_floor=(0, 0, 0, 16))
    result = evaluate(replace(physical, products=(invalid,)), Bounds(1000, 2000))
    assert result == {"classification": "MODEL_CONFLICT", "value_outer": None, "conditional_gap": None}


def test_equal_discount_and_terminal_growth_is_invalid():
    physical = scenario()
    with pytest.raises(ValueError, match="terminal"):
        evaluate(replace(physical, terminal_growth=Bounds(0.03, 0.07)), Bounds(100, 200))
