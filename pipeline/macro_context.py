"""Level / change / acceleration per macro regime axis — a research context
dataset, not a scoring change.

WHY THIS EXISTS. `pipeline/regime.py` already computes, for a single as-of
date, a `[-1, +1]` axis VALUE per axis (`AXES = growth, inflation, liquidity,
financialConditions, riskAppetite, earningsCredit`, `regime.py:75`) — but it
is called once per build, for "today," and nothing in this repository turns
that single level into a TIME SERIES a future study could read a change or
an acceleration off of. `alpha-information-inventory-v1`'s research map
found this explicitly: a stock-level feature x regime interaction (momentum
acceleration x financial conditions, volume shock x quality x liquidity
regime) has never been coded anywhere, and one reason is that only the
level was ever computed, never its own trend.

WHY THIS CALLS `regime.py` RATHER THAN RE-DERIVING THE AXIS VALUE.
`regime.indicator_read`/`regime._axis_summary` already implement the exact
z-score/direction/confidence aggregation this module needs — reusing them
is `switch-hurdle-v1`'s own discipline ("a ladder carries its own control,"
here: a context dataset carries its own definition of "level" from the one
place that definition already exists), and re-deriving the aggregation a
second time would be a second place for the two to silently disagree on
what an axis position actually is. `_axis_summary` is nominally private
(leading underscore) but is a pure, already-tested function with no
production side effect; importing it is a deliberate reuse choice, not an
accident.

WHAT THIS DOES NOT DO. It computes no interaction with any stock-level
feature, tests no relationship to any outcome, and is not called by
`build.py`, `regime.py`'s own axis decision, or any challenger study. It is
a context dataset a FUTURE study (not this one) would join against
stock-level features to test an interaction — that join and that test are
explicitly out of scope here, per this task's own "no interaction/outcome
testing" instruction.

KR STATUS. Every entry in `regime.INDICATORS` is FRED- or CBOE-sourced —
there is no KR axis to restructure this way, confirmed by
`alpha-information-inventory-v1`'s data map (§16-17): the ECOS fetch layer
that would need to exist for one is still 100% unbuilt (see
`pipeline/kr_investor_flow.py`'s sibling KR-macro workstream in this same
PR for what would be needed before a KR axis history could exist at all).
This module is US/global only, by construction of what `regime.py` itself
can compute today.
"""
from __future__ import annotations

import pandas as pd

from . import regime as REGIME

CONTRACT = "MACRO_CONTEXT_V1"


def axis_indicators(axis: str) -> list[str]:
    """Every indicator name `regime.INDICATORS` assigns to this axis."""
    return [name for name, (a, *_rest) in REGIME.INDICATORS.items() if a == axis]


def axis_value_at(macro: pd.DataFrame, axis: str,
                  asof: pd.Timestamp) -> dict:
    """One axis's `regime._axis_summary` reading as of one date.

    Calls `regime.indicator_read` per indicator in the axis, exactly as
    `regime.build` does for "today" — the only difference here is that
    `asof` is a parameter instead of always being the latest date, which is
    what turns a single snapshot into something a caller can request at
    many dates to build a history.
    """
    reads = []
    for name in axis_indicators(axis):
        if macro is None or name not in macro.columns:
            continue
        read = REGIME.indicator_read(name, macro[name], asof=asof)
        if read is not None:
            reads.append(read)
    summary = REGIME._axis_summary(reads)  # noqa: SLF001 - deliberate reuse, see module docstring
    summary["axis"] = axis
    summary["asof"] = asof
    return summary


def axis_history(macro: pd.DataFrame, axis: str,
                 dates: list[pd.Timestamp]) -> pd.DataFrame:
    """The axis's `value`/`confidence`/`coverage` at each requested date.

    `dates` should be a caller-chosen, PRE-SPECIFIED grid (e.g. the same
    weekly replay grid `historical_replay.py` already uses) — this function
    does not choose dates for the caller, so it cannot silently pick a
    favorable sampling.
    """
    rows = []
    for asof in dates:
        summary = axis_value_at(macro, axis, pd.Timestamp(asof))
        rows.append({"date": pd.Timestamp(asof), "level": summary["value"],
                    "confidence": summary["confidence"],
                    "coverage": summary["coverage"], "nIndicators": summary["nIndicators"]})
    frame = pd.DataFrame(rows).set_index("date").sort_index()
    # `summary["value"]` is `None`, not `NaN`, when an axis has no readable
    # indicators on a date. Coercing to float here (not at the caller) keeps
    # every numeric column a real float Series, so `.diff()` downstream never
    # hits pandas' object-dtype `None - None` failure on a sparse history.
    for col in ("level", "confidence", "coverage"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    return frame


def level_change_acceleration(levels: pd.Series, window: int = 21) -> pd.DataFrame:
    """Level, backward change over `window`, and change-of-change.

    Every column is BACKWARD-looking only: `change` at date T compares T's
    level to the level `window` observations earlier in the same series,
    never a future one, and `acceleration` is the same differencing applied
    to `change` itself. A `NaN` where fewer than `window` prior observations
    exist, never a value invented from a partial window.
    """
    change = levels.diff(window)
    acceleration = change.diff(window)
    return pd.DataFrame({"level": levels, "change": change, "acceleration": acceleration})


def build_context_table(macro: pd.DataFrame, dates: list[pd.Timestamp],
                        window: int = 21) -> dict[str, pd.DataFrame]:
    """Level/change/acceleration for every axis in `regime.AXES`.

    One DataFrame per axis, keyed by axis name — never pooled into a single
    wide table implying the axes should be compared on one scale, since
    `regime._axis_summary`'s `[-1, +1]` range is already comparable across
    axes by construction (each is a mean of signed +/-1 contributions), but
    the CONFIDENCE/COVERAGE columns are axis-specific and would be
    meaningless averaged together.
    """
    out: dict[str, pd.DataFrame] = {}
    for axis in REGIME.AXES:
        history = axis_history(macro, axis, dates)
        out[axis] = level_change_acceleration(history["level"], window).join(
            history[["confidence", "coverage", "nIndicators"]])
    return out
