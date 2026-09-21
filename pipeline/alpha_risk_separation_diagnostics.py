"""What the frozen alpha-risk-separation ladder did NOT yet answer.

WHY THIS IS A SEPARATE MODULE AND NOT AN EDIT
----------------------------------------------
`alpha-risk-separation-v1` is scored, published and merged. Its ladder is
CONTROL vs `RANK_ON_CALIBRATED_ALPHA_ONLY_NO_RISK_DENOMINATOR`, its paired
difference is -0.902pp with a 95% CI of [-5.068, +3.210] over 155 blocks,
and that interval CONTAINS ZERO. Nothing here re-scores any of it.

`alpha-reliability-v1` already wrote the rule this module obeys: A DIAGNOSTIC
ADDED AFTER A LADDER IS SCORED MAY ONLY READ IT. So the frozen rungs are
re-run by CALLING `alpha_reliability.run_rung` and
`alpha_risk_separation.run_alpha_only_rung` unmodified, and the runner
asserts that every scored block it reproduces is byte-identical to the
checked-in `docs/results/alpha-risk-separation-report.json`. If a diagnostic
in this module could move the ladder, that assertion fails and the report is
refused. The frozen result file is never rewritten.

WHAT THE FROZEN STUDY ALREADY ANSWERED, and is not repeated here:
`risk_dominance` (held-vs-rejected downside vol, `lowvol` sleeve percentile,
`lowvol` as highest / top-two sleeve, alpha-only-top-N overlap, names the
risk term promoted or dropped across the cut), `boundary_instability` (the
tie rate and the gaps at the cut), `replacement_anatomy` (swap anatomy and
realised arriving-minus-departing excess), `tilt_survival` (the cross-rung
deltas of all of the above).

THE THREE THINGS IT DID NOT
----------------------------
1. THE SET DIFFERENCE. `risk_dominance` compares held against rejected WITHIN
   each rung. It never looks at the names the two rungs DISAGREE about, which
   is the only population that can answer "did removing the denominator buy
   higher-momentum, higher-volatility names, and were those names actually
   better?". `set_difference_profiles` pairs the two rungs by date and
   profiles `selectedByChallengerNotControl` against
   `selectedByControlNotChallenger` on momentum, value, quality, lowvol,
   downside volatility, and the realised forward benchmark excess.

   The realised return is EVALUATION ONLY. It is read off the same priced
   cross-section `replacement_anatomy` already reads, it enters no score, no
   ranking and no rule, and it is reported as a description of what happened
   rather than as a fitted quantity.

   Factor facts are read from the CONTROL rung's own scored rows for BOTH
   groups. Both rungs score the same candidate cross-section and differ only
   in the score formula, so every name in either group is present in the
   control's rows — reading one source removes any doubt that a profile
   difference came from the source rather than from the group.

2. THE EXPLORATORY STACK. `signal-persistence-v1`'s k=6 smoother and this
   denominator removal are orthogonal, so their combination is worth SEEING —
   but it moves TWO axes and is attributable to neither, exactly as
   `signal-persistence-v1` said of its own stacked path. It is therefore run
   and reported OUTSIDE the primary ladder, never paired into it, and its
   number may not be read as the denominator's independent effect.

3. THE QUESTIONS IN PROSE. Q1-Q8 are answered from the numbers above in the
   markdown report rather than left for a reader to assemble.

WHAT THIS MODULE IS NOT. Not a promotion, not a production change, not a new
axis, and not a re-specification of anything in the frozen study. No
parameter is introduced, no threshold is added after seeing a result, and no
rung definition moves. `region_cap_binding` and `entry_state_dynamics` are
run on both rungs as OBSERVATIONAL diagnostics only: this study does not
touch the region quota or the entry logic, and its numbers are not grounds
to change either.
"""
from __future__ import annotations

import numpy as np

from . import alpha_reliability as AR
from . import alpha_risk_separation as ARS
from . import kelly_portfolio as KP
from . import portfolio_validation as PV
from . import switch_hurdle as SH

VERSION = "alpha-risk-separation-diagnostics-v1"

# The frozen ladder, read-only. Not redefined here — imported, so this module
# cannot disagree with the study it is reading about.
CONTROL = ARS.CONTROL
ALPHA_ONLY = ARS.ALPHA_ONLY
PRIMARY_LADDER = ARS.LADDER

# Reported OUTSIDE the primary ladder. Two axes at once, attributable to
# neither — the same status `signal-persistence-v1` gave its own stacked path.
EXPLORATORY_STACK = "EXPLORATORY_PERSISTENT_ALPHA_K6_PLUS_NO_RISK_DENOMINATOR"

# The keys of the frozen report this module must reproduce unchanged. If any
# of them moves, a diagnostic here has touched the ladder and the run is
# refused rather than published.
FROZEN_KEYS = ("ladder", "pairedVsControl", "pairedBlocks", "separation",
               "selectionBehaviour", "regionalAttribution", "riskDominance",
               "boundaryInstability", "replacementAnatomy", "tiltSurvival")

SLEEVES = ("momentum", "value", "quality", "lowvol")


def _held_of(decision: dict) -> set[str]:
    return set(decision.get("retained") or []) | set(decision.get("added") or [])


def _spread(values: list[float]) -> dict:
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


def _profile(rows: list[dict], returns: list[float]) -> dict:
    """Factor and risk profile of one side of the set difference."""
    out = {"nameDates": len(rows)}
    for sleeve in SLEEVES:
        out[sleeve] = _spread([PV._finite((r.get("factorPercentiles") or {}).get(sleeve))
                               for r in rows])
    out["downsideVolPct"] = _spread([PV._finite(r.get("downsideVolPct")) for r in rows])
    out["alphaPercentile"] = _spread([PV._finite(r.get("alphaPercentile")) for r in rows])
    out["expectedGrossBenchmarkExcessPct"] = _spread(
        [PV._finite(r.get("expectedGrossBenchmarkExcessPct")) for r in rows])
    # EVALUATION ONLY. Never read by any score, ranking or rule.
    out["realisedForwardBenchmarkExcessPct"] = AR._outcome_block(
        [r for r in returns if r is not None])
    return out


def set_difference_profiles(control_decisions: list[dict],
                            alpha_only_decisions: list[dict],
                            priced_by_date: dict) -> dict:
    """The names the two rungs DISAGREE about, profiled side by side.

    Paired WITHIN a rebalance date, so the comparison carries no
    market-timing term: both groups were chosen on the same date from the
    same cross-section under the same constraints, and the only thing that
    differs is whether the score divided by downside volatility.
    """
    control_by_date = {d["date"]: d for d in control_decisions}
    alpha_by_date = {d["date"]: d for d in alpha_only_decisions}
    shared = sorted(set(control_by_date) & set(alpha_by_date))

    challenger_rows, challenger_returns = [], []
    control_rows, control_returns = [], []
    agreed = disagreed = measured = 0
    per_date_overlap = []

    for date in shared:
        control_decision, alpha_decision = control_by_date[date], alpha_by_date[date]
        scored = {row["ticker"]: row for row in (control_decision.get("scored") or [])}
        if not scored:
            continue
        control_held = _held_of(control_decision)
        alpha_held = _held_of(alpha_decision)
        if not control_held or not alpha_held:
            continue
        measured += 1
        both = control_held & alpha_held
        agreed += len(both)
        only_challenger = alpha_held - control_held
        only_control = control_held - alpha_held
        disagreed += len(only_challenger)
        union = control_held | alpha_held
        if union:
            per_date_overlap.append(len(both) / len(union) * 100.0)

        priced = priced_by_date.get(date) or {}
        for ticker in sorted(only_challenger):
            row = scored.get(ticker)
            if row is None:
                continue
            challenger_rows.append(row)
            cell = priced.get(ticker) or {}
            challenger_returns.append(PV._finite(cell.get("excessReturn")))
        for ticker in sorted(only_control):
            row = scored.get(ticker)
            if row is None:
                continue
            control_rows.append(row)
            cell = priced.get(ticker) or {}
            control_returns.append(PV._finite(cell.get("excessReturn")))

    challenger = _profile(challenger_rows, challenger_returns)
    control = _profile(control_rows, control_returns)
    # `_outcome_block` reports its mean already scaled to percent (`meanPct`),
    # so the difference below is in percentage points of realised block excess.
    challenger_mean = challenger["realisedForwardBenchmarkExcessPct"].get("meanPct")
    control_mean = control["realisedForwardBenchmarkExcessPct"].get("meanPct")
    difference = (round(challenger_mean - control_mean, 4)
                  if challenger_mean is not None and control_mean is not None else None)

    return {
        "available": bool(measured),
        "rebalancesMeasured": measured,
        "heldNameDatesAgreed": agreed,
        "heldNameDatesDisagreed": disagreed,
        "heldSetOverlapPct": _spread(per_date_overlap),
        "selectedByChallengerNotControl": challenger,
        "selectedByControlNotChallenger": control,
        "realisedForwardExcessDifferencePp": difference,
        "note": (
            "Paired within a rebalance: both sides were chosen on the same date from "
            "the same cross-section under the same caps, so the within-date difference "
            "carries no market-timing term. Factor and risk facts are read from the "
            "CONTROL rung's own scored rows for BOTH groups — both rungs score the same "
            "cross-section and differ only in the score formula, so one source removes "
            "any doubt a profile gap came from the source rather than the group. The "
            "realised forward excess is EVALUATION ONLY: it is read off the same priced "
            "cross-section `replacement_anatomy` reads, and it enters no score, no "
            "ranking and no rule. `realisedForwardExcessDifferencePp` is a difference of "
            "two group means, not a paired test, and its sign is descriptive."),
    }


def run_exploratory_stack_rung(*, contexts: dict, calibrator, calendar: list[dict],
                               cfg_pf: dict, valuation) -> dict:
    """k=6 persistence AND the denominator removal, together. EXPLORATORY ONLY.

    Structurally `alpha_risk_separation.run_alpha_only_rung` with
    `persistence=True` — the k=6 smoother `signal-persistence-v1` already
    established, reused rather than re-derived, and the SAME
    `separation_scores` the frozen challenger ranks on. Nothing new is
    introduced; two existing pieces are combined.

    This path moves TWO axes. Its result is not the denominator's independent
    effect and may not be paired into the primary ladder or read as a rung of
    it. `signal-persistence-v1` reported its own stacked path under exactly
    this constraint.
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
        # THE ONE DIFFERENCE FROM THE FROZEN CHALLENGER: persistence=True.
        candidates = AR.confidence_rows(raw_candidates, state, block["date"],
                                        persistence=True, confidence=False)
        incumbents = set(terminal_weights)
        scored = ARS.separation_scores(candidates, calibrator, research_cfg)
        allocation = KP.selection_and_baseline(
            candidates, research_cfg, macro, scored=scored, method=EXPLORATORY_STACK)
        weights = allocation["weights"]
        selected = {c["ticker"]: c for c in allocation["selected"]}
        held = set(weights)
        cut_reasons, chosen = AR.annotate_selection(candidates, scored, research_cfg,
                                                     method=EXPLORATORY_STACK)
        if not held <= chosen:
            raise ValueError(f"SELECTION_ANNOTATION_DISAGREES_WITH_PATH at {block['date']}")
        for row in scored:
            row["selectionExclusionCodes"] = cut_reasons.get(row["ticker"])
        decision = {
            "date": block["date"], "replayDate": signal_date,
            "selector": EXPLORATORY_STACK, "weights": weights,
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
            "regionByTicker": decision["regionByTicker"],
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
    return {"rung": EXPLORATORY_STACK, "rows": rows, "decisions": decisions,
            "failures": failures, "complete": len(rows) == len(expected),
            "expectedBlocks": len(expected), "measuredBlocks": len(rows)}


def freeze_manifest() -> dict:
    return {
        "id": VERSION,
        "status": "DIAGNOSTIC_EXTENSION",
        "readsButDoesNotRescore": ARS.VERSION,
        "primaryLadder": list(PRIMARY_LADDER),
        "primaryLadderRescored": False,
        "frozenReportRewritten": False,
        "frozenKeysAssertedByteIdentical": list(FROZEN_KEYS),
        "exploratoryOutsideTheLadder": EXPLORATORY_STACK,
        "exploratoryMovesTwoAxes": (
            "k=6 percentile persistence AND the removal of the score's "
            "downside-volatility denominator. Attributable to neither; never to be "
            "read as the denominator's independent effect, and never paired into the "
            "primary ladder."),
        "realisedReturnsUsedFor": "EVALUATION_ONLY_NEVER_RULE_CONSTRUCTION",
        "observationalOnly": [
            "region_cap_binding — this study does not touch the region quota",
            "entry_state_dynamics — this study does not touch the entry logic",
        ],
        "permutationNullRun": False,
        "parametersIntroduced": [],
        "thresholdsAddedAfterSeeingAResult": [],
        "promotionEligible": False,
        "liveValidated": False,
        "productionChanged": False,
    }
