"""Outcome-free, synthetic-only audit of two DISTINCT proposed re-entry structures.

The previously listed C1c 'one rung per week' hypothesis is NOT the newer
post-outcome 20-session breakout. Neither is an executable registration.
No historical prices, published outcomes, returns or live allocations are read.
"""
from __future__ import annotations

from itertools import product

from .kr_market_risk_model import rule
from .market_research_c1c import target

ORIGINAL_RUNG_GRID = (0.4, 0.7, 1.0)
STRUCTURAL_HYPOTHESIS = "C1c-REENTRY-SPEED-ORIGINAL-STRUCTURAL"
BREAKOUT_HYPOTHESIS = "POST_C1_RESULT_20_SESSION_BREAKOUT_SEPARATE"


def one_rung_reentry(previous, desired):
    """Immediately reduce risk; when increasing equity add at most one frozen rung."""
    if type(previous) not in (int, float) or type(desired) not in (int, float):
        raise ValueError("INVALID_EXPOSURE_DOMAIN")
    if previous not in ORIGINAL_RUNG_GRID or desired not in ORIGINAL_RUNG_GRID:
        raise ValueError("UNREGISTERED_EXPOSURE_RUNG")
    if desired <= previous:
        return desired
    return ORIGINAL_RUNG_GRID[min(ORIGINAL_RUNG_GRID.index(previous) + 1,
                                  ORIGINAL_RUNG_GRID.index(desired))]


def one_rung_path(desired_targets):
    """First decision has no prior position; later decisions cannot see future states."""
    desired_targets = tuple(desired_targets)
    if not desired_targets:
        raise ValueError("EMPTY_REENTRY_PATH")
    if desired_targets[0] not in ORIGINAL_RUNG_GRID or type(desired_targets[0]) not in (int, float):
        raise ValueError("INITIAL_POSITION_UNDEFINED")
    out = [desired_targets[0]]
    for desired in desired_targets[1:]:
        out.append(one_rung_reentry(out[-1], desired))
    return tuple(out)


def symbolic_breakout_cells():
    """Complete abstract C1 input-domain truth table, NOT historical state frequency."""
    result = []
    for slow, transition, fast, breakout in product((0, 1), (0, 1), (0, 1, 2), (False, True)):
        control = rule("C1", slow, transition, fast)
        arms = {name: target(name, slow, transition, fast, breakout)
                for name in ("S0", "S1", "S2", "S3")}
        if arms["S0"] != control:
            raise ValueError("SEALED_C1_CONTROL_CHANGED")
        result.append({"slow": slow, "transition": transition,
                       "fast": fast, "breakout": breakout,
                       "control": control,
                       "differences": tuple(k for k in ("S1", "S2", "S3")
                                            if arms[k] != control)})
    return tuple(result)
