"""Pre-registered target equity weights for MVMA-v1. Pure: no I/O, no return, no NAV.

Each dynamic policy maps boolean states to one of three registered weights (0.6 / 0.8 / 1.0 of capital in the
equity ETF, the remainder in the registered cash asset). No leverage, no short: every target is in [0, 1].

Missing inputs follow the repository's "a determined answer is not missing" rule: a target is produced when EVERY
completion of the missing booleans gives the same weight (e.g. VM1 with earnings DETERIORATING and credit STRESSED is
0.6 whatever valuation says); otherwise the policy holds its previous target and the hold is counted. Before a
policy's first determinable target it holds `PRE_SIGNAL_WEIGHT`.
"""
from __future__ import annotations

from itertools import product

WEIGHTS = (0.6, 0.8, 1.0)
PRE_SIGNAL_WEIGHT = 0.8
STATIC_POLICIES = {"B0": 1.0, "B1": 0.8, "B2": 0.6}
DYNAMIC_POLICIES = ("V1", "M1", "VM1", "D1")


def v1(state: dict) -> float:
    """Trailing-5y-mean PER rule: cheap -> 1.0, otherwise 0.6."""
    return 1.0 if state["cheap"] else 0.6


def m1(state: dict) -> float:
    """Earnings / credit only: deteriorating AND stressed -> 0.6; stable AND not stressed -> 1.0; else 0.8."""
    if not state["earningsStable"] and state["creditStress"]:
        return 0.6
    if state["earningsStable"] and not state["creditStress"]:
        return 1.0
    return 0.8


def vm1(state: dict) -> float:
    """Priority 1: deteriorating AND stressed -> 0.6. Priority 2: cheap AND stable AND not stressed -> 1.0. Else 0.8."""
    if not state["earningsStable"] and state["creditStress"]:
        return 0.6
    if state["cheap"] and state["earningsStable"] and not state["creditStress"]:
        return 1.0
    return 0.8


def d1(state: dict) -> float:
    """Plain drawdown buying: >= 20% below the 252-session high -> 1.0, otherwise 0.8."""
    return 1.0 if state["deepDrawdown"] else 0.8


RULES = {"V1": (v1, ("cheap",)), "M1": (m1, ("earningsStable", "creditStress")),
         "VM1": (vm1, ("cheap", "earningsStable", "creditStress")), "D1": (d1, ("deepDrawdown",))}


def determined_target(policy: str, state: dict) -> float | None:
    """The policy's weight if every completion of the missing (None) inputs agrees, else None."""
    rule, inputs = RULES[policy]
    missing = [k for k in inputs if state.get(k) is None]
    outcomes = set()
    for completion in product((False, True), repeat=len(missing)):
        filled = {k: state.get(k) for k in inputs}
        filled.update(dict(zip(missing, completion)))
        outcomes.add(rule(filled))
    return outcomes.pop() if len(outcomes) == 1 else None


def target_path(policy: str, states: list[dict]) -> dict:
    """Target weight at every decision date, with the hold count and the first determinable decision index."""
    if policy in STATIC_POLICIES:
        return {"targets": [STATIC_POLICIES[policy]] * len(states), "holds": 0, "firstDetermined": 0 if states else None}
    previous = PRE_SIGNAL_WEIGHT
    targets, holds, first = [], 0, None
    for i, state in enumerate(states):
        value = determined_target(policy, state)
        if value is None:
            holds += 1
            value = previous
        elif first is None:
            first = i
        if not 0.0 <= value <= 1.0:
            raise AssertionError("LEVERAGE_OR_SHORT_TARGET")
        targets.append(value)
        previous = value
    return {"targets": targets, "holds": holds, "firstDetermined": first}
