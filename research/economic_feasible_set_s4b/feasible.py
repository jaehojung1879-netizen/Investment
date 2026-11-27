"""Synthetic market/E scenarios. No prices, tickers, or forecasts of security returns."""

from dataclasses import dataclass
from math import isfinite

import numpy as np
from scipy.optimize import linprog


@dataclass(frozen=True)
class Bounds:
    lo: float
    hi: float

    def __post_init__(self):
        if not isfinite(self.lo) or not isfinite(self.hi) or self.lo > self.hi:
            raise ValueError(f"Invalid bounds: {self}")

    @property
    def mid(self):
        return (self.lo + self.hi) / 2

    def product(self, other):
        corners = [a * b for a in (self.lo, self.hi) for b in (other.lo, other.hi)]
        return Bounds(min(corners), max(corners))


@dataclass(frozen=True)
class Product:
    hours_per_unit: float
    starting_backlog: float
    live_orders: tuple[float, ...]  # new non-cancellable order units in the period
    cancellations: tuple[float, ...]
    demand_floor: tuple[float, ...]  # committed delivery floor, optional through zero
    price: Bounds
    variable_cost: Bounds


@dataclass(frozen=True)
class Scenario:
    products: tuple[Product, ...]
    shared_hours: tuple[float, ...]
    tax: float
    fixed_opex: Bounds  # per period
    depreciation: Bounds  # per period
    maintenance_capex: Bounds  # per period
    growth_capex: Bounds  # per period
    incremental_nwc: Bounds  # per period, negative means release
    discount: Bounds  # annual
    terminal_growth: Bounds
    terminal_roic: Bounds
    terminal_nopat: Bounds  # annual cash basis before terminal reinvestment


def capacity_rows(scenario):
    """A made-to-order model. No inventory, subcontracting or spot sales in this fixture."""
    periods = len(scenario.shared_hours)
    products = scenario.products
    if periods != 4 or not products or not 0 <= scenario.tax < 1:
        raise ValueError("Four quarterly periods, at least one product and a valid tax rate are required")
    if (
        any(v < 0 or not isfinite(v) for v in scenario.shared_hours)
        or not 0 <= scenario.terminal_growth.lo <= scenario.terminal_growth.hi < scenario.discount.lo
        or scenario.terminal_growth.hi >= scenario.terminal_roic.lo
        or scenario.terminal_nopat.lo < 0
    ):
        raise ValueError("Unresolved capacity or terminal assumptions")
    n = periods * len(products)
    rows, limits, floors = [], [], []
    for t, hours in enumerate(scenario.shared_hours):
        row = [0.0] * n
        for j, product in enumerate(products):
            if not isfinite(product.hours_per_unit) or product.hours_per_unit <= 0:
                raise ValueError("Each product must use positive shared resource time")
            row[j * periods + t] = product.hours_per_unit
        rows.append(row)
        limits.append(hours)
    for j, product in enumerate(products):
        contractual_series = (product.live_orders, product.cancellations, product.demand_floor)
        if product.starting_backlog < 0 or not isfinite(product.starting_backlog) or any(
            len(series) != periods or any(v < 0 or not isfinite(v) for v in series)
            for series in contractual_series
        ):
            raise ValueError("Backlog, live orders, cancellations and floors must be present and nonnegative")
        available = product.starting_backlog
        for t, (orders, cancelled) in enumerate(zip(product.live_orders, product.cancellations, strict=True)):
            available += orders - cancelled
            row = [0.0] * n
            row[j * periods:j * periods + t + 1] = [1.0] * (t + 1)
            rows.append(row)
            limits.append(available)
        floors.extend((floor, None) for floor in product.demand_floor)
    return rows, limits, floors


def optimize(objective, matrices, maximum=False):
    rows, limits, floors = matrices
    weights = np.array(objective)
    result = linprog(-weights if maximum else weights, A_ub=rows, b_ub=limits, bounds=floors, method="highs")
    if result.status == 2:
        return None
    if not result.success:
        raise RuntimeError(result.message)
    return float(weights @ result.x), result.x


def nonvolume_cashflow(s):
    after_tax = 1 - s.tax
    return Bounds(
        -s.fixed_opex.hi * after_tax + s.depreciation.lo - s.maintenance_capex.hi
        - s.growth_capex.hi - s.incremental_nwc.hi,
        -s.fixed_opex.lo * after_tax + s.depreciation.hi - s.maintenance_capex.lo
        - s.growth_capex.lo - s.incremental_nwc.lo,
    )


def terminal_enclosure(s):
    reinvestment_factor = Bounds(
        1 - s.terminal_growth.hi / s.terminal_roic.lo,
        1 - s.terminal_growth.lo / s.terminal_roic.hi,
    )
    discount_factor = Bounds(
        1 / ((s.discount.hi - s.terminal_growth.lo) * (1 + s.discount.hi)),
        1 / ((s.discount.lo - s.terminal_growth.hi) * (1 + s.discount.lo)),
    )
    return s.terminal_nopat.product(reinvestment_factor).product(discount_factor)


def value_enclosure(s, matrices):
    """A conservative outer projection. Ignoring dependencies can only widen it."""
    weights, fixed = [], []
    for t in range(1, 5):
        discount_factor = Bounds((1 + s.discount.hi) ** (-t / 4), (1 + s.discount.lo) ** (-t / 4))
        fixed.append(nonvolume_cashflow(s).product(discount_factor))
    for product in s.products:
        unit_after_tax = Bounds(
            (product.price.lo - product.variable_cost.hi) * (1 - s.tax),
            (product.price.hi - product.variable_cost.lo) * (1 - s.tax),
        )
        for t in range(1, 5):
            factor = Bounds((1 + s.discount.hi) ** (-t / 4), (1 + s.discount.lo) ** (-t / 4))
            weights.append(unit_after_tax.product(factor))
    low = optimize([x.lo for x in weights], matrices)
    if low is None:
        return None
    high = optimize([x.hi for x in weights], matrices, maximum=True)
    terminal = terminal_enclosure(s)
    return Bounds(low[0] + sum(x.lo for x in fixed) + terminal.lo,
                  high[0] + sum(x.hi for x in fixed) + terminal.hi)


def midpoint_projection(s, matrices):
    """A certified inner interval, under the joint midpoint nuisance scenario."""
    r, g, roic = s.discount.mid, s.terminal_growth.mid, s.terminal_roic.mid
    factors = [(1 + r) ** (-t / 4) for t in range(1, 5)]
    weights = [
        (p.price.mid - p.variable_cost.mid) * (1 - s.tax) * discount
        for p in s.products for discount in factors
    ]
    fixed = nonvolume_cashflow(s).mid * sum(factors)
    continuation = s.terminal_nopat.mid * (1 - g / roic) / ((r - g) * (1 + r))
    low, high = optimize(weights, matrices), optimize(weights, matrices, maximum=True)
    return Bounds(low[0] + fixed + continuation, high[0] + fixed + continuation), low[1], high[1]


def evaluate(s, market):
    matrices = capacity_rows(s)
    outer = value_enclosure(s, matrices)
    if outer is None:
        return {"classification": "MODEL_CONFLICT", "value_outer": None, "conditional_gap": None}
    inner, xlo, xhi = midpoint_projection(s, matrices)
    witness = None
    conditional_gap = None
    tolerance = 1e-7
    if market.lo > outer.hi + tolerance:
        classification = "MARKET_ABOVE_E_CONDITIONAL"
        conditional_gap = market.lo - outer.hi
    elif market.hi < outer.lo - tolerance:
        classification = "MARKET_BELOW_E_CONDITIONAL"
        conditional_gap = outer.lo - market.hi
    elif max(inner.lo, market.lo) <= min(inner.hi, market.hi):
        classification = "OVERLAP_WITNESS_ABSTAIN"
        matched_ev = max(inner.lo, market.lo)
        weight = (matched_ev - inner.lo) / (inner.hi - inner.lo) if inner.hi > inner.lo else 0.0
        witness = {
            "ev": matched_ev,
            "product_quarter_units": ((1 - weight) * xlo + weight * xhi).tolist(),
        }
    else:
        classification = "OUTER_OVERLAP_UNRESOLVED"
    return {
        "classification": classification,
        "value_outer": [outer.lo, outer.hi],
        "value_inner_at_midpoints": [inner.lo, inner.hi],
        "conditional_gap": conditional_gap,
        "witness": witness,
    }
