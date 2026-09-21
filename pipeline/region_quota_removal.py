"""Should regional diversification be a name quota, or should the ranking decide?

WHERE THIS CAME FROM
--------------------
`alpha-reliability-v1` measured that the diversification guard produces more
turnover than the ranking's own opinion does: `maxNamesPerRegion = 3` stopped
a name on 93.10% of control rebalances, and on 134 of 145 the stopped name
outscored one the book took (median decision-alpha gap 0.856pp). Held
name-dates split KR 421 / US 301 where the same count with the caps lifted
wanted KR 640 / US 82 — the ranking, left alone, wants a very different mix
than the quota lets it hold. Neither `alpha-risk-separation-v1` nor
`dynamic-breadth-v1` touched that cap; `dynamic-breadth-v1` in fact measured
that it is the binding constraint on 17.42% of rebalances even in a study that
was not asking about regions at all. This study is.

THE PREREQUISITE, ANSWERED BY MEASUREMENT BEFORE THE LADDER IS READ
----------------------------------------------------------------------
`alpha-reliability-v1`'s own pre-registration named a prerequisite: alpha
percentiles are a WITHIN-REGION rank, so a Korean 90th and an American 90th
are not the same claim, and removing the quota needs a common scale first, or
it is just replaced by an artefact of the percentile's construction.

That scale already exists and this module does not invent a second one.
`ExpandingBucketCalibration.expected(region, percentile)` converts a
within-region percentile into a REGION-SPECIFIC calibrated expected
BENCHMARK EXCESS, in percentage points, against that region's OWN matched
benchmark — the same quantity `alpha_reliability.CONTROL`'s score already
ranks on. Two names in different regions with the same calibrated alpha are
making the SAME quantitative claim: "this many percentage points of excess
over my own region's benchmark, on a shrinkage-adjusted estimate of the
bucket's own historical excess." Percentiles are not compared across regions
anywhere in this ladder; calibrated excess returns are, and they already were
before this module existed.

WHAT IS ACTUALLY MEASURED, THEN, IS WHETHER THAT SCALE IS COMPARABLE IN
PRACTICE — not whether one exists. `calibration_comparability` reads the same
candidate stream `alpha_reliability.CONTROL` already scores, splits it by
region, and reports the calibrated alpha level, its standard error, its
shrinkage factor and its effective independent date count side by side. A
region with materially thinner history gets MORE shrinkage (`shrink =
eff / (eff + priorStrength)`), which pulls its calibrated alpha toward zero
regardless of the region's true opportunity — that is the artefact the
prerequisite warned about, and it is reported explicitly rather than assumed
away.

THE AXIS, AND ONLY THE AXIS
----------------------------
    CONTROL           `alpha_reliability.CONTROL`, called directly.
                       `maxNamesPerRegion = 3`.
    NO_REGION_QUOTA    the SAME score, the SAME candidate stream, the SAME
                       `targetNames = 5`. `maxNamesPerRegion` is opened to
                       `targetNames` — the same "cap set equal to the count it
                       could never usefully exceed" pattern
                       `selection_value.broad_config` already established for
                       a different cap — so a region can hold every slot the
                       ranking gives it. `maxNamesPerSector` (2) is UNCHANGED:
                       sector diversification is not this study's axis.

Breadth stays fixed at the production `targetNames = 5` on both rungs.
Stacking this with `dynamic-breadth-v1`'s adaptive count would move two axes
at once and is explicitly left for a stacked reference path, never the ladder
itself.

WHAT THIS IS NOT. Not a promotion, not a production change, and not the
"portfolio-level risk / covariance / concentration budget" the pre-
registration named as the eventual destination — building a covariance-based
concentration budget is substantially more machinery than a single-axis
ablation should introduce at once, and every study in this line has moved
exactly one thing. This rung answers the narrower, prior question: does the
ranking, left alone, want a different regional mix than the quota allows, and
does letting it have one help. What a risk-budget replacement should look
like is next, not now.
"""
from __future__ import annotations

import numpy as np

from . import alpha_reliability as AR
from . import kelly_portfolio as KP
from . import portfolio_validation as PV
from . import switch_hurdle as SH

VERSION = "region-quota-removal-v1"

CONTROL = AR.CONTROL
NO_REGION_QUOTA = "NO_REGION_QUOTA_SAME_SCORE"
LADDER = (CONTROL, NO_REGION_QUOTA)


def local_cfg(cfg_pf: dict) -> dict:
    """Production config with ONLY `selection.maxNamesPerRegion` opened.

    Opened to `targetNames`, not to infinity: a region can never usefully
    hold more names than the book's own count, so this is the same "cap set
    equal to the count it cannot exceed" `selection_value.broad_config`
    already uses for a different cap. `maxNamesPerSector`, `maxPositionWeight`,
    the cash floor and every cost assumption are untouched.
    """
    out = dict(cfg_pf)
    selection = dict(out.get("selection") or {})
    target = int(selection.get("targetNames", out.get("maxNames", 5)))
    selection["maxNamesPerRegion"] = target
    out["selection"] = selection
    return out


def run_no_quota_rung(*, contexts: dict, calibrator, calendar: list[dict],
                      cfg_pf: dict, valuation) -> dict:
    """Value the no-region-quota rung on the fixed blocks.

    Candidate assembly and scoring are IDENTICAL to `alpha_reliability`'s own
    CONTROL — called, not reimplemented. The only thing that changes is the
    region cap in the config handed to `selection_and_baseline`.
    """
    from . import benchmark_alpha as BA

    research_cfg = BA.cost_config(cfg_pf)
    open_cfg = local_cfg(research_cfg)
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
        allocation = KP.selection_and_baseline(
            candidates, open_cfg, macro, scored=scored, method=NO_REGION_QUOTA)
        weights = allocation["weights"]
        selected = {c["ticker"]: c for c in allocation["selected"]}
        held = set(weights)
        cut_reasons, chosen = AR.annotate_selection(candidates, scored, open_cfg,
                                                     method=NO_REGION_QUOTA)
        if not held <= chosen:
            raise ValueError(f"SELECTION_ANNOTATION_DISAGREES_WITH_PATH at {block['date']}")
        for row in scored:
            row["selectionExclusionCodes"] = cut_reasons.get(row["ticker"])
        decision = {
            "date": block["date"], "replayDate": signal_date, "selector": NO_REGION_QUOTA,
            "weights": weights,
            "regionByTicker": {t: selected[t].get("region") for t in weights},
            "cashPct": (1 - sum(weights.values())) * 100,
            "rebalanceDecision": True, "selectedTickers": list(weights),
        }
        outcome, diagnostic = valuation.window(decision, block)
        decisions.append({
            "date": block["date"], "signalDate": signal_date,
            "heldNames": len(weights),
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
    return {"rung": NO_REGION_QUOTA, "rows": rows, "decisions": decisions,
            "failures": failures, "complete": len(rows) == len(expected),
            "expectedBlocks": len(expected), "measuredBlocks": len(rows)}


def calibration_comparability(control_decisions: list[dict]) -> dict:
    """Is the calibrated scale the ranking already uses comparable across regions?

    Read from the CONTROL path's own scored candidates — the exact stream
    every rung in this study ranks from — never re-derived. This is the axis
    measured BEFORE the ladder is read: if one region's calibration carries
    materially more shrinkage or a materially shorter effective history, that
    is reported here as a limitation on what removing the quota can honestly
    claim, not discovered after the fact from a result that looked good.
    """
    by_region: dict[str, dict[str, list]] = {}
    seen: set[tuple[str, str, str]] = set()
    for decision in control_decisions:
        for row in decision.get("scored") or []:
            estimate = row.get("calibration")
            if not estimate:
                continue
            region = row.get("region") or "UNKNOWN"
            key = (decision["date"], region, row["ticker"])
            if key in seen:
                continue
            seen.add(key)
            bucket = by_region.setdefault(region, {
                "alpha": [], "se": [], "shrink": [], "effectiveDates": [],
                "uniqueDates": [],
            })
            for field, target in (("expectedExcessReturnPct", "alpha"),
                                  ("standardErrorPct", "se"),
                                  ("shrinkageFactor", "shrink"),
                                  ("effectiveIndependentDates", "effectiveDates"),
                                  ("uniqueDates", "uniqueDates")):
                value = PV._finite(estimate.get(field))
                if value is not None:
                    bucket[target].append(value)

    out = {}
    for region, blob in sorted(by_region.items()):
        out[region] = {label: _spread(values) for label, values in blob.items()}
    return {
        "available": bool(out), "byRegion": out,
        "note": ("Read from the CONTROL path's own candidate stream, per name-date. "
                 "`shrink` closer to 1 means less of the bucket mean is discounted toward "
                 "zero; `effectiveDates` is the non-overlapping observation count behind "
                 "that shrinkage. A region with a systematically lower shrink or fewer "
                 "effective dates has its calibrated alpha pulled harder toward zero for "
                 "reasons of DATA HISTORY LENGTH, not of true opportunity — that is the "
                 "comparability artefact the pre-registration's prerequisite named."),
    }


def _spread(values) -> dict:
    array = np.asarray([v for v in values if v is not None], dtype=float)
    if not array.size:
        return {"available": False, "observations": 0}
    return {
        "available": True, "observations": int(array.size),
        "mean": round(float(array.mean()), 4),
        "sd": round(float(array.std(ddof=1)), 4) if array.size > 1 else None,
        "median": round(float(np.median(array)), 4),
        "p10": round(float(np.percentile(array, 10)), 4),
        "p90": round(float(np.percentile(array, 90)), 4),
    }


def region_mix(decisions: list[dict]) -> dict:
    """Held name-dates by region, and the rebalance-level region shape."""
    held_by_region: dict[str, int] = {}
    shapes: dict[str, int] = {}
    for decision in decisions:
        region_of = decision.get("regionByTicker") or {}
        held = set(decision.get("retained") or []) | set(decision.get("added") or [])
        for ticker in held:
            region = str(region_of.get(ticker) or "UNKNOWN")
            held_by_region[region] = held_by_region.get(region, 0) + 1
        shape = "/".join(f"{region}:{count}" for region, count in sorted(
            _tally(region_of.get(t) for t in held).items()))
        shapes[shape] = shapes.get(shape, 0) + 1
    return {
        "heldNameDatesByRegion": dict(sorted(held_by_region.items())),
        "regionShapeCounts": dict(sorted(shapes.items(), key=lambda kv: -kv[1])),
    }


def _tally(values) -> dict[str, int]:
    out: dict[str, int] = {}
    for value in values:
        key = str(value or "UNKNOWN")
        out[key] = out.get(key, 0) + 1
    return out


def freeze_manifest() -> dict:
    return {
        "id": VERSION,
        "status": "CHALLENGER",
        "ladder": list(LADDER),
        "controlSource": "alpha_reliability.run_rung(alpha_reliability.CONTROL, ...), unmodified",
        "axis": "WHETHER_MAX_NAMES_PER_REGION_BINDS_AT_ALL",
        "prerequisite": (
            "ALPHA_PERCENTILES_ARE_WITHIN_REGION_BUT_THE_EXISTING_CALIBRATED_SCORE_"
            "ALREADY_EXPRESSES_EACH_NAME_IN_THE_SAME_UNIT_REGION_SPECIFIC_EXPECTED_"
            "BENCHMARK_EXCESS_PP_NO_NEW_SCALE_IS_INTRODUCED"
        ),
        "prerequisiteMeasuredBy": "calibration_comparability_on_the_control_path_own_candidates",
        "regionCapControl": 3, "regionCapChallenger": "OPENED_TO_TARGET_NAMES",
        "sectorCapUnchangedFromProduction": True, "targetNamesUnchangedFromProduction": True,
        "breadthAxisNotStacked": "dynamic-breadth-v1's adaptive count is a separate study",
        "notTheFullPreRegisteredDestination": (
            "A portfolio-level risk/covariance/concentration budget is the eventual "
            "replacement named in the pre-registration; this rung tests only whether "
            "the COUNT quota binds, one axis at a time, per this line's discipline."
        ),
        "permutationNullRun": False,
        "parametersIntroduced": [],
        "heldFixedAcrossRungs": [
            "fixed 21-session evaluation blocks and their cadence",
            "PIT research candidate pool",
            "0.30/0.25/0.25/0.20 momentum/value/quality/low-vol sleeve weights",
            "expanding bucket calibration of percentile to expected excess",
            "entry-state and research-view exclusions",
            "score formula: calibrated alpha / downside volatility x entry multiplier",
            "targetNames = 5, maxNamesPerSector = 2, maxPositionWeight, cash floor",
            "inverse-downside-volatility conviction-tilted position sizing",
            "no backward-percentile smoothing, no confidence contraction, no signal "
            "hysteresis, no transaction-cost hurdle, no dynamic breadth",
        ],
        "promotionEligible": False,
        "liveValidated": False,
        "productionChanged": False,
    }
