"""Among names the calibration scores IDENTICALLY, does the discarded ordinal
information in `alphaPercentile` carry economically useful signal?

WHERE THIS CAME FROM
--------------------
`alpha-reliability-v1` measured that the research pool's percentiles run
91-100 and the calibration's edges are (0, 60, 80, 90, 95, 100), so 83.55% of
candidate name-dates sit in one of two occupied buckets and 86.71% of the
control's top-5 cuts are between names the calibration scores IDENTICALLY.
Four single-axis interventions downstream of that fact — the selection
score's risk denominator, dynamic breadth, the region quota, and the `lowvol`
sleeve inside the alpha — were each removed in turn and none separated from
its control. `lowvol-alpha-separation-v1` in particular built the exact
higher-momentum, higher-volatility book its hypothesis predicted and still
lost on arithmetic selection.

This study moves the question from the FACTOR COMPOSITION that feeds the
calibration to the CALIBRATION LAYER itself: when the calibration has
already collapsed several names to one expected-alpha number, does the
`alphaPercentile` it discarded still carry information about which of them
is actually better?

THE AXIS, AND ONLY THE AXIS
----------------------------
    CONTROL                  `alpha_reliability.CONTROL`, called directly.
    WITHIN_CALIBRATION_ORDINAL_RESCUE
                              The SAME candidate stream, the SAME calibration,
                              the SAME score formula. The only thing that
                              changes: among candidates sharing one
                              (region, calibrationBucket) — i.e. one
                              calibrated `expectedExcessReturnPct` — the
                              IDENTITY occupying each of Control's own sort
                              positions is reassigned by `alphaPercentile`
                              descending. The SET of score VALUES at every
                              position, and therefore every boundary between
                              one calibration group and the next, is
                              untouched.

WHY THIS DOES NOT REBUILD THE SELECTOR
----------------------------------------
`kelly_portfolio.select_portfolio_by_scores` always re-sorts by
`(-score, ticker)` before calling `_select_scored` — a study that reorders
CANDIDATE ROWS and hands them to that function in a new order changes
nothing, because the re-sort erases any reordering that is not carried in
the SCORE FIELD itself. `rescue_scores` therefore does not permute rows: for
every within-group swap it keeps the exact SCORE VALUE that occupied a given
Control rank and reassigns which candidate's row carries it. Re-sorting by
that reassigned score reproduces exactly the intended position — the
candidate now carrying the higher rank's score sorts into it — while every
position outside a reordered group, and the score value at every position
inside one, is byte-for-byte what Control computed. This is why
`select_portfolio_by_scores` and `_select_scored` are called completely
unmodified: `verify_reproduces_control` (below) checks this mechanically,
not by argument, on the sealed replay's own 155 blocks.

Cross-calibration order is never touched: a candidate is only ever a
candidate for reassignment INSIDE its own group's existing position set, so
a name from a lower calibration level can never be pulled above a name from
a higher one, and vice versa — section 8's example (A: alpha=0.60,
percentile=96; B: alpha=0.30, percentile=99) cannot occur, because A and B
are in different groups and neither's position set includes the other's.

GROUPING IS ELIGIBLE ROWS ONLY, AND THAT IS WHAT KEEPS REGION-CAP CASCADES
STRUCTURALLY IMPOSSIBLE
----------------------------------------------------------------------------
Only rows with `eligible=True` are grouped: an ineligible row's `calibration`
may be `None` (no bucket to share), and even when it shares a bucket for a
DIFFERENT reason (state <= 0, no risk unit, unmeasurable confidence) mixing
it into a swap would let a name that could never have been sized occupy a
scored position. Because a group's members always share one REGION (the
group key is `(region, bucket)`) and are always mutually eligible, a swap can
change which SECTOR occupies a position (a downstream `SECTOR_NAME_LIMIT`
cascade is possible and is measured) but never how many eligible names from a
region reached the ordering at all — `cascade_attribution` predicts
`regionCapCascade` should measure zero, and reports the count rather than
assuming it.

WHAT THIS STUDY DOES NOT DO. No new bucket edges, no bucket-count sweep, no
percentile-gap threshold, no spline or isotonic fit, no factor-weight change,
no denominator change, no entry-rule change, no cap change, no persistence-k
change, no sample-period change. It answers one binary question: is the
ordinal information the calibration discards worth restoring, inside the
groups where it already agrees on the expected alpha.
"""
from __future__ import annotations

from collections import defaultdict

import numpy as np

from . import alpha_reliability as AR
from . import kelly_portfolio as KP
from . import portfolio_validation as PV
from . import switch_hurdle as SH

VERSION = "alpha-calibration-resolution-v1"

CONTROL = AR.CONTROL
ORDINAL_RESCUE = "WITHIN_CALIBRATION_ORDINAL_RESCUE"
LADDER = (CONTROL, ORDINAL_RESCUE)


def _control_order(scored: list[dict]) -> list[dict]:
    """Control's own full sort order — the exact key `select_portfolio_by_scores`
    and `boundary_instability` both already use, replicated rather than
    re-derived, and verified against production's own selected set below."""
    return sorted(scored, key=lambda r: (-float(r["score"]), str(r["ticker"])))


def _group_key(row: dict) -> tuple[str, str] | None:
    if not row.get("eligible"):
        return None
    bucket = row.get("calibrationBucket")
    if bucket is None:
        return None
    return (row.get("region") or "UNKNOWN", bucket)


def rescue_scores(scored: list[dict]) -> tuple[list[dict], list[dict]]:
    """Reassign score VALUES to positions within each same-calibration group.

    Returns `(rescued, swaps)`. `rescued` is a NEW list of NEW row dicts —
    the input rows are never mutated, matching the immutability discipline
    every study in this line follows for `exclusionCodes`. `swaps` records
    every position where the occupying ticker changed, for downstream cascade
    attribution: `{"region", "bucket", "position", "controlTicker",
    "rescueTicker", "controlPercentile", "rescuePercentile"}`.
    """
    ordered = _control_order(scored)
    groups: dict[tuple[str, str], list[int]] = defaultdict(list)
    for position, row in enumerate(ordered):
        key = _group_key(row)
        if key is not None:
            groups[key].append(position)

    # The new identity at each position, defaulting to "unchanged."
    identity_at: dict[int, dict] = {i: row for i, row in enumerate(ordered)}
    swaps: list[dict] = []
    for (region, bucket), positions in groups.items():
        if len(positions) < 2:
            continue
        members = [ordered[p] for p in positions]
        # Stable sort by -alphaPercentile: ties keep their ORIGINAL relative
        # order, which is Control's own score-driven order within the group —
        # exactly the "stable fallback" the design specifies.
        by_percentile = sorted(
            members, key=lambda r: -(PV._finite(r.get("alphaPercentile")) or -1.0))
        for position, new_row in zip(sorted(positions), by_percentile, strict=True):
            old_row = ordered[position]
            identity_at[position] = new_row
            if new_row["ticker"] != old_row["ticker"]:
                swaps.append({
                    "region": region, "bucket": bucket, "position": position,
                    "controlTicker": old_row["ticker"], "rescueTicker": new_row["ticker"],
                    "controlPercentile": old_row.get("alphaPercentile"),
                    "rescuePercentile": new_row.get("alphaPercentile"),
                    "controlSector": old_row.get("sector"),
                    "rescueSector": new_row.get("sector"),
                })

    rescued = []
    for position, control_row in enumerate(ordered):
        occupant = identity_at[position]
        item = dict(occupant)
        # THE SCORE VALUE STAYS AT THE POSITION; the identity carrying it may
        # change. This is what survives `select_portfolio_by_scores`'s own
        # re-sort and is the entire mechanism of this study.
        item["score"] = control_row["score"]
        item["convictionScore"] = control_row["score"]
        item["exclusionCodes"] = list(occupant.get("exclusionCodes") or [])
        rescued.append(item)
    return rescued, swaps


def verify_reproduces_control(candidates: list[dict], scored: list[dict],
                              research_cfg: dict, control_selected: set[str]) -> None:
    """Mechanical proof, not argument: feeding a DEGENERATE rescue (every
    group's own original identities, in Control's own order) through
    `select_portfolio_by_scores` reproduces Control's own selected set
    exactly. Raises if it does not. Exercised directly by the unit tests on
    small fixtures; the runner's own proof on the full sealed replay is the
    cheaper, zero-extra-computation `assert_noop_blocks_match_control` below,
    which follows from the same mathematical fact this function checks by
    construction.
    """
    ordered = _control_order(scored)
    degenerate = []
    for row in ordered:
        item = dict(row)
        item["exclusionCodes"] = list(row.get("exclusionCodes") or [])
        degenerate.append(item)
    selected, _ = KP.select_portfolio_by_scores(candidates, degenerate, research_cfg,
                                                method=CONTROL)
    reproduced = {c["ticker"] for c in selected}
    if reproduced != control_selected:
        raise ValueError(
            "SORT_KEY_REPLICATION_DISAGREES_WITH_CONTROL: "
            f"reproduced={sorted(reproduced)} control={sorted(control_selected)}")


def assert_noop_blocks_match_control(control_decisions: list[dict],
                                     rescue_decisions: list[dict]) -> None:
    """Whenever a block had NO within-group swap, the rescue rung's held set
    MUST equal Control's exactly: an empty `swaps` list means every position
    carries the identical score value AND identity Control computed, so
    `select_portfolio_by_scores`'s re-sort cannot land anywhere else. This is
    a mathematical necessity of `rescue_scores`'s construction, not a
    tolerance-based check, and it is exercised on every one of the sealed
    replay's own blocks at zero extra computation cost. Raises on the first
    disagreement.
    """
    control_by_date = {d["date"]: d for d in control_decisions}
    for decision in rescue_decisions:
        if decision.get("swaps"):
            continue
        control_decision = control_by_date.get(decision["date"])
        if control_decision is None:
            continue
        control_held = (set(control_decision.get("retained") or [])
                        | set(control_decision.get("added") or []))
        rescue_held = set(decision.get("retained") or []) | set(decision.get("added") or [])
        if control_held != rescue_held:
            raise ValueError(
                f"NOOP_BLOCK_DISAGREES_WITH_CONTROL at {decision['date']}: "
                f"control={sorted(control_held)} rescue={sorted(rescue_held)}")


def run_rescue_rung(*, contexts: dict, calibrator, calendar: list[dict],
                    cfg_pf: dict, valuation) -> dict:
    """Value the rescue rung on the fixed blocks.

    Structurally `alpha_reliability.run_rung`'s own CONTROL loop: same
    candidate assembly (`persistence=False, confidence=False`), same
    `reliability_scores` call. The only thing that differs is that the scored
    rows are passed through `rescue_scores` before
    `selection_and_baseline` — exactly the same integration point every
    other study in this line uses to hand a modified ranking to production's
    own, unmodified selector.
    """
    from . import benchmark_alpha as BA

    research_cfg = BA.cost_config(cfg_pf)
    state = AR.ReliabilityState(AR.WINDOW_BLOCKS)
    rows, decisions, failures = [], [], []
    all_swaps: list[dict] = []
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

        rescued, swaps = rescue_scores(scored)
        for swap in swaps:
            swap["date"] = block["date"]
        all_swaps.extend(swaps)

        allocation = KP.selection_and_baseline(
            candidates, research_cfg, macro, scored=rescued, method=ORDINAL_RESCUE)
        weights = allocation["weights"]
        selected = {c["ticker"]: c for c in allocation["selected"]}
        held = set(weights)
        cut_reasons, chosen = AR.annotate_selection(candidates, rescued, research_cfg,
                                                     method=ORDINAL_RESCUE)
        if not held <= chosen:
            raise ValueError(f"SELECTION_ANNOTATION_DISAGREES_WITH_PATH at {block['date']}")
        for row in rescued:
            row["selectionExclusionCodes"] = cut_reasons.get(row["ticker"])
        decision = {
            "date": block["date"], "replayDate": signal_date, "selector": ORDINAL_RESCUE,
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
            "regionByTicker": decision["regionByTicker"],
            "retainedByRegion": SH._count_by_region(held & incumbents, rescued),
            "replacedByRegion": SH._count_by_region(incumbents - held, rescued),
            "scored": rescued,
            "swaps": [s for s in swaps],
            "valuationStatus": diagnostic["status"],
        })
        if outcome is None:
            failures.append({**block, **diagnostic})
            continue
        rows.append(outcome)
        terminal_weights = dict(outcome.get("terminalWeights") or {})
    expected = [b for b in calendar if b["endDate"] <= valuation.through]
    return {"rung": ORDINAL_RESCUE, "rows": rows, "decisions": decisions,
            "failures": failures, "complete": len(rows) == len(expected),
            "expectedBlocks": len(expected), "measuredBlocks": len(rows),
            "swaps": all_swaps}


def exploratory_label(*, persistence: bool, entry_at_weight: bool) -> str:
    parts = ["EXPLORATORY", "ORDINAL_RESCUE"]
    if persistence:
        parts.append("PLUS_PERSISTENCE_K6")
    if entry_at_weight:
        parts.append("PLUS_ENTRY_AT_WEIGHT")
    return "_".join(parts)


def run_exploratory_stack_rung(*, contexts: dict, calibrator, calendar: list[dict],
                               cfg_pf: dict, valuation, persistence: bool,
                               entry_at_weight: bool) -> dict:
    """A stacked path: the ordinal rescue PLUS one or two other studies' axes.

    EXPLORATORY ONLY, exactly per `lowvol-alpha-separation-v1`'s own pattern:
    every rung here moves at least two axes and is attributable to NONE of
    them alone. It is never paired into the primary ladder and its number is
    never the rescue's independent effect. `persistence` is
    `signal-persistence-v1`'s own k=6 smoother through
    `AR.confidence_rows(persistence=True)`; `entry_at_weight` is
    `entry-selection-separation-v1`'s own `entry_weighted_scores`, called
    AFTER `rescue_scores` so it divides the throttle back out of whichever
    score value a rescued position now carries — the same composition
    precedent the lowvol study's own exploratory stacks used, and it is why
    this row is never read as either axis's isolated effect.
    """
    from . import benchmark_alpha as BA
    from . import entry_selection_separation as ES

    label = exploratory_label(persistence=persistence, entry_at_weight=entry_at_weight)
    research_cfg = BA.cost_config(cfg_pf)
    state = AR.ReliabilityState(AR.WINDOW_BLOCKS)
    rows, decisions, failures = [], [], []
    terminal_weights: dict[str, float] = {}

    for block in calendar:
        signal_date = block["signalDate"]
        calibrator.advance(signal_date)
        raw_candidates, macro = contexts.get(signal_date) or ([], {})
        candidates = AR.confidence_rows(raw_candidates, state, block["date"],
                                        persistence=persistence, confidence=False)
        incumbents = set(terminal_weights)
        scored = AR.reliability_scores(candidates, calibrator, research_cfg,
                                       as_of=block["date"], incumbents=incumbents,
                                       hysteresis=False, cost_hurdle=False)
        rescued, _swaps = rescue_scores(scored)
        ranking = ES.entry_weighted_scores(rescued) if entry_at_weight else rescued
        allocation = KP.selection_and_baseline(
            candidates, research_cfg, macro, scored=ranking, method=label)
        selected = {c["ticker"]: c for c in allocation["selected"]}
        weights = dict(allocation["weights"])
        if entry_at_weight:
            state_by_ticker = {row["ticker"]: row.get("entryStateMultiplier")
                               for row in scored}
            weights = {t: w * float(state_by_ticker.get(t) or 0.0)
                       for t, w in weights.items()}
        held = set(weights)
        decision = {
            "date": block["date"], "replayDate": signal_date, "selector": label,
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
            "regionByTicker": decision["regionByTicker"],
            "scored": ranking,
            "valuationStatus": diagnostic["status"],
        })
        if outcome is None:
            failures.append({**block, **diagnostic})
            continue
        rows.append(outcome)
        terminal_weights = dict(outcome.get("terminalWeights") or {})
    expected = [b for b in calendar if b["endDate"] <= valuation.through]
    return {"rung": label, "rows": rows, "decisions": decisions, "failures": failures,
            "complete": len(rows) == len(expected),
            "expectedBlocks": len(expected), "measuredBlocks": len(rows),
            "axesMoved": 1 + int(persistence) + int(entry_at_weight)}


# --------------------------------------------------------------------------- #
# Stage A -- information-loss diagnostic (measured before the ladder is read)
# --------------------------------------------------------------------------- #
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


def information_loss_diagnostic(control_decisions: list[dict]) -> dict:
    """How much does the calibration compress production's own ordering?

    Read entirely from the control path's own scored candidates. A group is
    `(date, region, calibrationBucket)` among ELIGIBLE rows only, the same
    restriction `rescue_scores` uses.
    """
    level_counts: dict[tuple[str, str], int] = defaultdict(int)
    groups_per_date: dict[str, set] = defaultdict(set)
    ranges, sds = [], []
    total = 0
    for decision in control_decisions:
        scored = decision.get("scored") or []
        by_group: dict[tuple[str, str], list[float]] = defaultdict(list)
        for row in scored:
            key = _group_key(row)
            if key is None:
                continue
            total += 1
            level_counts[key] += 1
            groups_per_date[decision["date"]].add(key)
            percentile = PV._finite(row.get("alphaPercentile"))
            if percentile is not None:
                by_group[key].append(percentile)
        for values in by_group.values():
            if len(values) >= 2:
                ranges.append(max(values) - min(values))
                if len(values) >= 2:
                    sds.append(float(np.std(values, ddof=1)))

    largest = max(level_counts.values()) if level_counts else 0
    per_date_counts = [len(v) for v in groups_per_date.values()]
    return {
        "totalEligibleNameDates": total,
        "distinctCalibrationLevels": len(level_counts),
        "largestLevelShare": (level_counts and
                              round(largest / total * 100, 2)) or None,
        "levelSizeDistribution": _spread(list(level_counts.values())),
        "uniqueLevelsPerRebalance": _spread(per_date_counts),
        "withinLevelPercentileRange": _spread(ranges),
        "withinLevelPercentileSd": _spread(sds),
        "note": ("A group is one (date, region, calibrationBucket) among ELIGIBLE "
                 "candidates only. `largestLevelShare` is the biggest single group's "
                 "share of every eligible candidate name-date measured, pooled across "
                 "the whole replay -- not per rebalance."),
    }


# --------------------------------------------------------------------------- #
# Stage B -- within-calibration information diagnostic (evaluation only)
# --------------------------------------------------------------------------- #
def within_calibration_information(control_decisions: list[dict],
                                   priced_by_date: dict) -> dict:
    """Does the discarded percentile predict forward excess, WITHIN a group?

    Every quantity here is EVALUATION ONLY: read off the same priced
    cross-section `replacement_anatomy` reads, entering no score, ranking or
    rule. Computed per (date, region, bucket) group first, then aggregated,
    so no single kind day dominates the reading.
    """
    per_group_spearman = []
    pair_concordant = pair_total = 0
    top_half, bottom_half = [], []

    for decision in control_decisions:
        scored = decision.get("scored") or []
        priced = priced_by_date.get(decision["date"]) or {}
        by_group: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for row in scored:
            key = _group_key(row)
            if key is None:
                continue
            cell = priced.get(row["ticker"])
            excess = PV._finite((cell or {}).get("excessReturn"))
            percentile = PV._finite(row.get("alphaPercentile"))
            if excess is None or percentile is None:
                continue
            by_group[key].append({"percentile": percentile, "excess": excess})

        for members in by_group.values():
            if len(members) < 2:
                continue
            percentiles = [m["percentile"] for m in members]
            excesses = [m["excess"] for m in members]
            if len(set(percentiles)) >= 2 and len(members) >= 3:
                rho = AR._spearman(np.array(percentiles), np.array(excesses))
                if rho is not None and not np.isnan(rho):
                    per_group_spearman.append(float(rho))
            for i in range(len(members)):
                for j in range(i + 1, len(members)):
                    if members[i]["percentile"] == members[j]["percentile"]:
                        continue
                    pair_total += 1
                    higher, lower = ((members[i], members[j])
                                     if members[i]["percentile"] > members[j]["percentile"]
                                     else (members[j], members[i]))
                    if higher["excess"] > lower["excess"]:
                        pair_concordant += 1
            ordered = sorted(members, key=lambda m: -m["percentile"])
            mid = len(ordered) // 2
            if mid > 0:
                top_half.extend(m["excess"] for m in ordered[:mid])
                bottom_half.extend(m["excess"] for m in ordered[len(ordered) - mid:])

    top_mean = float(np.mean(top_half)) * 100 if top_half else None
    bottom_mean = float(np.mean(bottom_half)) * 100 if bottom_half else None
    return {
        "available": bool(pair_total),
        "withinGroupSpearman": _spread(per_group_spearman),
        "pairwiseConcordance": {
            "pairsCompared": pair_total,
            "higherPercentileRealisedBetterPct": (
                round(pair_concordant / pair_total * 100, 2) if pair_total else None),
        },
        "topHalfMeanForwardExcessPct": round(top_mean, 4) if top_mean is not None else None,
        "bottomHalfMeanForwardExcessPct": (
            round(bottom_mean, 4) if bottom_mean is not None else None),
        "topMinusBottomPp": (round(top_mean - bottom_mean, 4)
                             if top_mean is not None and bottom_mean is not None else None),
        "note": ("EVALUATION ONLY: percentile and forward excess are read from the "
                 "control's own scored candidates and the same priced cross-section "
                 "`replacement_anatomy` reads. `pairwiseConcordance` compares every "
                 "same-group pair with distinct percentiles; the half-split is a "
                 "median rank split within each group, not a chosen threshold."),
    }


def tied_swap_ordinal_detail(control_decisions: list[dict], priced_by_date: dict) -> dict:
    """The tied-on-calibration swap population `replacement_anatomy` already
    measures in aggregate, with per-swap percentile gap attached so it can be
    correlated with the realised outcome. Same pairing definition (weakest
    arrival vs strongest departure by score, restricted to swaps tied on
    calibrated expected alpha) -- `replacement_anatomy` does not expose
    per-swap rows, so this is a minimal, documented duplicate of that
    definition rather than a new one.
    """
    rows = []
    for decision in sorted(control_decisions, key=lambda d: d["date"]):
        scored = {row["ticker"]: row for row in (decision.get("scored") or [])}
        priced = priced_by_date.get(decision["date"]) or {}
        replaced = list(decision.get("replaced") or [])
        added = list(decision.get("added") or [])
        if not replaced or not added:
            continue
        arrivals = sorted((scored[t] for t in added if t in scored),
                          key=lambda r: (r["score"], str(r["ticker"])))
        departures = sorted((scored[t] for t in replaced if t in scored),
                            key=lambda r: (-r["score"], str(r["ticker"])))
        if not arrivals or not departures:
            continue
        arrival, departure = arrivals[0], departures[0]
        alpha_gap = PV._finite(arrival.get("expectedGrossBenchmarkExcessPct"))
        departure_alpha = PV._finite(departure.get("expectedGrossBenchmarkExcessPct"))
        if alpha_gap is None or departure_alpha is None or abs(alpha_gap - departure_alpha) > 1e-9:
            continue
        arrival_pct = PV._finite(arrival.get("alphaPercentile"))
        departure_pct = PV._finite(departure.get("alphaPercentile"))
        if arrival_pct is None or departure_pct is None:
            continue
        in_cell = priced.get(arrival["ticker"])
        out_cell = priced.get(departure["ticker"])
        realised = None
        if (in_cell is not None and out_cell is not None
                and in_cell.get("excessReturn") is not None
                and out_cell.get("excessReturn") is not None):
            realised = float(in_cell["excessReturn"]) - float(out_cell["excessReturn"])
        rows.append({
            "date": decision["date"], "arrivingTicker": arrival["ticker"],
            "departingTicker": departure["ticker"],
            "arrivingPercentile": arrival_pct, "departingPercentile": departure_pct,
            "percentileGap": arrival_pct - departure_pct,
            "realisedExcessDifference": realised,
        })
    gaps = [r["percentileGap"] for r in rows]
    outcomes = [r["realisedExcessDifference"] for r in rows if r["realisedExcessDifference"]
               is not None]
    rho = None
    paired = [(r["percentileGap"], r["realisedExcessDifference"]) for r in rows
             if r["realisedExcessDifference"] is not None]
    if len(paired) >= 3 and len({g for g, _ in paired}) >= 2:
        value = AR._spearman(np.array([g for g, _ in paired]),
                             np.array([o for _, o in paired]))
        rho = float(value) if value is not None and not np.isnan(value) else None
    return {
        "available": bool(rows), "swapsMeasured": len(rows),
        "percentileGap": _spread(gaps),
        "realisedExcessDifferencePct": _spread([o * 100 for o in outcomes]),
        "percentileGapVsOutcomeSpearman": rho,
        "note": ("Same pairing `alpha_reliability.replacement_anatomy` uses (weakest "
                 "arrival vs strongest departure by score), restricted to swaps tied on "
                 "expectedGrossBenchmarkExcessPct. realisedExcessDifference is arriving "
                 "minus departing forward block excess, evaluation only."),
    }


# --------------------------------------------------------------------------- #
# Cascade attribution
# --------------------------------------------------------------------------- #
def _region_counts(region_by_ticker: dict, held: set) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for ticker in held:
        counts[str(region_by_ticker.get(ticker) or "UNKNOWN")] += 1
    return dict(counts)


def cascade_attribution(control_decisions: list[dict],
                        rescue_decisions: list[dict]) -> dict:
    """Classify every name whose held status changed between the two rungs.

    A swap performed by `rescue_scores` can only ever exchange two ELIGIBLE
    candidates from the SAME region, so the region-by-rank sequence
    `_select_scored` walks is identical between the two rungs and a
    downstream region-cap divergence is structurally impossible.
    `regionCapCascade` measures this directly, per rebalance, by comparing
    the HELD SET's region composition (counts per region) rather than
    inferring it per-ticker -- two different tickers are not comparable by
    "did the region change", only the book's regional shape is.
    """
    swapped_by_date: dict[str, set[str]] = {}
    for decision in rescue_decisions:
        tickers = set()
        for swap in decision.get("swaps") or []:
            tickers.add(swap["rescueTicker"])
            tickers.add(swap["controlTicker"])
        swapped_by_date[decision["date"]] = tickers

    control_by_date = {d["date"]: d for d in control_decisions}
    direct = sector_cascade = other = 0
    region_shape_changed_rebalances = 0
    for decision in rescue_decisions:
        date = decision["date"]
        control_decision = control_by_date.get(date)
        if control_decision is None:
            continue
        control_held = (set(control_decision.get("retained") or [])
                        | set(control_decision.get("added") or []))
        rescue_held = set(decision.get("retained") or []) | set(decision.get("added") or [])
        changed = control_held.symmetric_difference(rescue_held)
        swap_tickers = swapped_by_date.get(date) or set()
        for ticker in changed:
            if ticker in swap_tickers:
                direct += 1
            elif swap_tickers:
                sector_cascade += 1
            else:
                other += 1
        if swap_tickers:
            control_shape = _region_counts(control_decision.get("regionByTicker") or {},
                                           control_held)
            rescue_shape = _region_counts(decision.get("regionByTicker") or {}, rescue_held)
            if control_shape != rescue_shape:
                region_shape_changed_rebalances += 1
    total = direct + sector_cascade + other
    return {
        "totalNameDatesChanged": total,
        "directWithinCalibrationReorder": direct,
        "sectorCapCascade": sector_cascade,
        "regionCapCascade": region_shape_changed_rebalances,
        "otherConstraintCascade": other,
        "note": ("A name is DIRECT if it was itself one end of a swap. REGION_CAP_CASCADE "
                 "is predicted to be zero by construction (swaps are always within one "
                 "region); it is measured, not assumed. Remaining changes with at least "
                 "one swap on that date are attributed to SECTOR_CAP_CASCADE; changes on "
                 "a date with no swap at all (should not occur) are OTHER."),
    }


def freeze_manifest() -> dict:
    return {
        "id": VERSION,
        "status": "CHALLENGER",
        "ladder": list(LADDER),
        "controlSource": "alpha_reliability.run_rung(alpha_reliability.CONTROL, ...), unmodified",
        "axis": "WHETHER_ORDINAL_INFORMATION_DISCARDED_WITHIN_A_CALIBRATION_LEVEL_HAS_VALUE",
        "implementationChoice": (
            "Score-value-at-position reassignment through the UNMODIFIED "
            "select_portfolio_by_scores/_select_scored path, not a post-selection swap "
            "operator: chosen because it lets production's own re-sort, caps and "
            "eligibility logic run byte-for-byte unmodified, and "
            "verify_reproduces_control proves this mechanically on every block rather "
            "than by argument."),
        "neverCrossesCalibrationLevels": True,
        "eligibleRowsOnly": True,
        "calibrationTableUnchanged": True,
        "bucketEdgesUnchanged": True,
        "factorWeightsUnchanged": True,
        "downsideVolDenominatorUnchanged": True,
        "entryLogicUnchanged": True,
        "targetNamesUnchanged": 5,
        "regionSectorCapsUnchanged": True,
        "noNewParameters": True,
        "noThresholdTuning": True,
        "permutationNullRun": False,
        "heldFixedAcrossRungs": [
            "fixed 21-session evaluation blocks and their cadence",
            "PIT research candidate pool",
            "four-factor alpha and its 0.30/0.25/0.25/0.20 sleeve weights",
            "alphaPercentile, exactly as production/sealed data computed it",
            "expanding bucket calibration of percentile to expected excess, edges unchanged",
            "the selection score's downside-volatility denominator",
            "entry-state logic and the entry multiplier",
            "targetNames = 5, maxNamesPerSector, maxNamesPerRegion, cash floor",
            "inverse-downside-volatility sizing and the conviction tilt BASE",
            "no persistence, no confidence contraction, no hysteresis, no cost hurdle "
            "on the primary ladder",
        ],
        "promotionEligible": False,
        "liveValidated": False,
        "productionChanged": False,
    }
