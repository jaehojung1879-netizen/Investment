"""Does a fixed count of five cut an ordering that does not have five names in it?

WHERE THIS CAME FROM
--------------------
`alpha-reliability-v1` measured the ordering a fixed count of five is
currently cutting, and it is thin: a mean of 3.56 tied pairs sit inside the
top five, 2.03 names in ranks 6-10 are indistinguishable from the fifth, and
the decision-alpha gaps at 3-vs-4, 5-vs-6, 8-vs-9 and 10-vs-11 cluster near
zero. `alpha-risk-separation-v1` then showed what removing the score's
continuously-varying term does to that same boundary — ties explode further.
Neither study changed how many names the book holds. This one does, and
nothing else.

THE AXIS, FIXED BEFORE THE RESULT
----------------------------------
Breadth is bounded in [FLOOR, CEILING] = [3, 10] — the exact numbers
`alpha-reliability-v1` pre-registered, not re-derived here. `FLOOR = 3` is
also the existing `minNames` in `config.json`; it is not a new number. Beyond
the floor, a name is added only if its OWN calibrated alpha estimate clears
zero by at least one standard error of the bucket mean it came from — the
SAME `SE_MULTIPLE = 1.0` and the SAME `raw_se x shrinkageFactor` scaling
`switch_hurdle.hurdle_scores` already uses for its own margin, imported
rather than re-derived. No new parameter is introduced anywhere in this
module.

THE SCORE DOES NOT MOVE. Ranking is `alpha_reliability.CONTROL`'s own score —
calibrated alpha divided by downside volatility times the entry multiplier —
called via `alpha_reliability.confidence_rows` and `.reliability_scores`
exactly as the control assembles it. The only thing this axis changes is HOW
MANY of the ranked names are taken, never how they are ordered.

WHAT "DISTINGUISHABLE" MEANS, AND WHY IT IS TESTED ON THE ALPHA, NOT THE SCORE
-------------------------------------------------------------------------------
A name's SCORE mixes three things (alpha, risk, entry state) that answer
different questions — "is this a good name" is the first of them. The breadth
question is specifically about the ALPHA CLAIM's own precision, so the test
reads the calibration's `expectedExcessReturnPct` and `standardErrorPct`
directly, not the risk-adjusted score. A name clears the bar when

    expectedExcessReturnPct > 0
    AND expectedExcessReturnPct >= SE_MULTIPLE x (standardErrorPct x shrinkageFactor)

Both quantities come from `ExpandingBucketCalibration.expected`, already
computed for every rung in this line of studies; nothing here fits a new
statistic to produce them.

THE WALK IS MONOTONIC AND STOPS AT THE FIRST FAILURE. Names are examined in
score order, from rank `FLOOR + 1` to `CEILING`. The first one that fails the
bar ends the walk — a later name passing the bar after an earlier one failed
it would not be "distinguishable additional breadth", it would be the tail of
a ranking whose head already told the book to stop. Below `FLOOR` no test is
applied at all: the floor is unconditional, matching production's own
`minNames`.

WHAT THIS DOES NOT TOUCH. `maxNamesPerRegion` (3) and `maxNamesPerSector` (2)
are the CAPS `alpha-reliability-v1` measured as a bigger source of turnover
than the ranking's own opinion, and they are `region-quota-removal-v1`'s
axis, not this one's. They stay exactly as production sets them — which means
the two-region universe here can never actually reach the ceiling of 10 names
(2 regions x 3 = 6 is the hard maximum), and this module measures and reports
that interaction rather than silently absorbing it or widening a cap that is
out of scope.

WHAT THIS IS NOT. Not a promotion, not a production change, and not a search
over 3/5/7/10 for whichever scored best on this sample — that comparison is
exactly what the pre-registration forbade. `SE_MULTIPLE`, `FLOOR` and
`CEILING` are all inherited from prior work, and none is swept.
"""
from __future__ import annotations

import numpy as np

from . import alpha_reliability as AR
from . import kelly_portfolio as KP
from . import portfolio_validation as PV
from . import switch_hurdle as SH

VERSION = "dynamic-breadth-v1"

CONTROL = AR.CONTROL
DYNAMIC_BREADTH = "DYNAMIC_BREADTH_3_TO_10_SE_DISTINGUISHABLE"
LADDER = (CONTROL, DYNAMIC_BREADTH)

# Pre-registered by `alpha-reliability-v1`, not re-derived here. FLOOR is also
# production's existing `selection.minNames`.
FLOOR = 3
CEILING = 10

# `switch_hurdle.SE_MULTIPLE`, imported rather than re-declared, so a change to
# that a-priori unit cannot silently diverge between the two studies that use it.
SE_MULTIPLE = SH.SE_MULTIPLE


def dynamic_target(scored: list[dict], *, floor: int = FLOOR, ceiling: int = CEILING,
                   se_multiple: float = SE_MULTIPLE) -> tuple[int, str]:
    """How many names this block's ordering can defend, and why it stopped.

    Returns `(count, stopReason)`. `count` is unconditionally `min(floor,
    eligible)` below the floor; beyond it, one more name is admitted for each
    consecutive rank whose own alpha estimate clears zero by `se_multiple`
    standard errors, stopping at the first rank that does not.
    """
    ordered = sorted((row for row in scored if row.get("eligible")),
                     key=lambda r: (-float(r["score"]), str(r["ticker"])))
    if len(ordered) <= floor:
        return len(ordered), "FEWER_THAN_FLOOR_ELIGIBLE"
    count = floor
    for row in ordered[floor:ceiling]:
        estimate = row.get("calibration") or {}
        alpha = PV._finite(estimate.get("expectedExcessReturnPct"))
        raw_se = PV._finite(estimate.get("standardErrorPct"))
        shrink = PV._finite(estimate.get("shrinkageFactor"))
        if alpha is None or raw_se is None or shrink is None:
            return count, "CALIBRATION_PRECISION_UNAVAILABLE"
        effective_se = raw_se * shrink
        if alpha > 0 and alpha >= se_multiple * effective_se:
            count += 1
        else:
            return count, "ALPHA_NOT_DISTINGUISHABLE_FROM_ZERO"
    return count, "REACHED_CEILING"


def local_cfg(cfg_pf: dict, target: int) -> dict:
    """Production config with ONLY `selection.targetNames` moved to `target`.

    `maxNamesPerSector`, `maxNamesPerRegion`, `maxPositionWeight`, the cash
    floor and every cost assumption are untouched — the same discipline
    `selection_value.broad_config` uses when it moves a different count.
    """
    out = dict(cfg_pf)
    selection = dict(out.get("selection") or {})
    selection["targetNames"] = int(target)
    out["selection"] = selection
    return out


def run_dynamic_breadth_rung(*, contexts: dict, calibrator, calendar: list[dict],
                             cfg_pf: dict, valuation) -> dict:
    """Value the dynamic-breadth rung on the fixed blocks.

    Candidate assembly and scoring are IDENTICAL to `alpha_reliability`'s own
    CONTROL — `confidence_rows(persistence=False, confidence=False)` then
    `reliability_scores(hysteresis=False, cost_hurdle=False)`, called rather
    than reimplemented. The only new step is choosing `targetNames` for this
    block before `selection_and_baseline` is called.
    """
    from . import benchmark_alpha as BA

    research_cfg = BA.cost_config(cfg_pf)
    state = AR.ReliabilityState(AR.WINDOW_BLOCKS)
    rows, decisions, failures = [], [], []
    terminal_weights: dict[str, float] = {}

    for block in calendar:
        signal_date = block["signalDate"]
        calibrator.advance(signal_date)
        raw_candidates, macro = contexts.get(signal_date) or ([], {})
        candidates = AR.confidence_rows(raw_candidates, state, block["date"],
                                        persistence=False, confidence=False)
        incumbents = set(terminal_weights)
        scored = AR.reliability_scores(candidates, calibrator, research_cfg,
                                       as_of=block["date"], incumbents=incumbents,
                                       hysteresis=False, cost_hurdle=False)
        target, stop_reason = dynamic_target(scored)
        block_cfg = local_cfg(research_cfg, target)
        allocation = KP.selection_and_baseline(
            candidates, block_cfg, macro, scored=scored, method=DYNAMIC_BREADTH)
        weights = allocation["weights"]
        selected = {c["ticker"]: c for c in allocation["selected"]}
        held = set(weights)
        cut_reasons, chosen = AR.annotate_selection(candidates, scored, block_cfg,
                                                     method=DYNAMIC_BREADTH)
        if not held <= chosen:
            raise ValueError(f"SELECTION_ANNOTATION_DISAGREES_WITH_PATH at {block['date']}")
        for row in scored:
            row["selectionExclusionCodes"] = cut_reasons.get(row["ticker"])
        decision = {
            "date": block["date"], "replayDate": signal_date, "selector": DYNAMIC_BREADTH,
            "weights": weights,
            "regionByTicker": {t: selected[t].get("region") for t in weights},
            "cashPct": (1 - sum(weights.values())) * 100,
            "rebalanceDecision": True, "selectedTickers": list(weights),
        }
        outcome, diagnostic = valuation.window(decision, block)
        # A cap trimmed the computed target if the region/sector caps stopped
        # the book before it reached the count `dynamic_target` defended.
        capped_by_diversification = len(held) < target
        decisions.append({
            "date": block["date"], "signalDate": signal_date,
            "heldNames": len(weights),
            "computedTarget": target, "stopReason": stop_reason,
            "cappedByDiversification": capped_by_diversification,
            "retained": sorted(held & incumbents),
            "added": sorted(held - incumbents),
            "replaced": sorted(incumbents - held),
            "regionByTicker": {t: selected[t].get("region") for t in weights},
            "retainedByRegion": SH._count_by_region(held & incumbents, scored),
            "replacedByRegion": SH._count_by_region(incumbents - held, scored),
            "scored": scored,
            "valuationStatus": diagnostic["status"],
        })
        if outcome is None:
            failures.append({**block, **diagnostic})
            continue
        rows.append(outcome)
        terminal_weights = dict(outcome.get("terminalWeights") or {})
    expected = [b for b in calendar if b["endDate"] <= valuation.through]
    return {"rung": DYNAMIC_BREADTH, "rows": rows, "decisions": decisions,
            "failures": failures, "complete": len(rows) == len(expected),
            "expectedBlocks": len(expected), "measuredBlocks": len(rows)}


def breadth_distribution(decisions: list[dict]) -> dict:
    """How wide the book actually ran, and why it stopped where it did."""
    held = [d.get("heldNames") or 0 for d in decisions]
    computed = [d.get("computedTarget") for d in decisions if d.get("computedTarget") is not None]
    stop_reasons: dict[str, int] = {}
    for d in decisions:
        reason = d.get("stopReason") or "UNKNOWN"
        stop_reasons[reason] = stop_reasons.get(reason, 0) + 1
    capped = sum(1 for d in decisions if d.get("cappedByDiversification"))
    if not held:
        return {"available": False}
    arr = np.asarray(held, dtype=float)
    return {
        "available": True, "rebalances": len(decisions),
        "namesHeld": {
            "mean": round(float(arr.mean()), 3), "min": int(arr.min()),
            "max": int(arr.max()), "median": round(float(np.median(arr)), 3),
        },
        "computedTargetMean": (round(float(np.mean(computed)), 3) if computed else None),
        "stopReasonCounts": dict(sorted(stop_reasons.items(), key=lambda kv: -kv[1])),
        "rebalancesCappedByDiversification": capped,
        "rebalancesCappedByDiversificationPct": (round(capped / len(decisions) * 100, 2)
                                                 if decisions else None),
        "reachedCeilingPct": (round(stop_reasons.get("REACHED_CEILING", 0)
                                    / len(decisions) * 100, 2) if decisions else None),
        "note": ("`computedTarget` is what the SE-distinguishability walk defended before "
                 "any cap was applied; `heldNames` is what the book actually holds after "
                 "sector/region caps and cash-floor sizing. The gap between them is the "
                 "region-cap interaction this study does not resolve: with two regions "
                 "and maxNamesPerRegion=3 unchanged, ten names can never actually be held."),
    }


def freeze_manifest() -> dict:
    return {
        "id": VERSION,
        "status": "CHALLENGER",
        "ladder": list(LADDER),
        "controlSource": "alpha_reliability.run_rung(alpha_reliability.CONTROL, ...), unmodified",
        "axis": "HOW_MANY_NAMES_A_DISTINGUISHABLE_ORDERING_DEFENDS_BETWEEN_A_FLOOR_AND_A_CEILING",
        "floor": FLOOR, "ceiling": CEILING, "seMultiple": SE_MULTIPLE,
        "floorSource": "PRE_REGISTERED_BY_ALPHA_RELIABILITY_V1_AND_EQUAL_TO_PRODUCTION_MIN_NAMES",
        "ceilingSource": "PRE_REGISTERED_BY_ALPHA_RELIABILITY_V1",
        "seMultipleSource": "IMPORTED_FROM_SWITCH_HURDLE_SE_MULTIPLE_NOT_RE_DERIVED",
        "distinguishabilityTestedOn": "CALIBRATION_ALPHA_AND_ITS_OWN_STANDARD_ERROR_NOT_THE_RISK_ADJUSTED_SCORE",
        "scoreUnchangedFromControl": True,
        "regionAndSectorCapsUnchangedFromProduction": True,
        "permutationNullRun": False,
        "parametersIntroduced": [],
        "heldFixedAcrossRungs": [
            "fixed 21-session evaluation blocks and their cadence",
            "PIT research candidate pool",
            "0.30/0.25/0.25/0.20 momentum/value/quality/low-vol sleeve weights",
            "expanding bucket calibration of percentile to expected excess",
            "entry-state and research-view exclusions",
            "score formula: calibrated alpha / downside volatility x entry multiplier",
            "maxPositionWeight, maxNamesPerSector, maxNamesPerRegion, cash floor",
            "inverse-downside-volatility conviction-tilted position sizing",
            "no backward-percentile smoothing, no confidence contraction, no signal "
            "hysteresis, no transaction-cost hurdle",
        ],
        "promotionEligible": False,
        "liveValidated": False,
        "productionChanged": False,
    }
