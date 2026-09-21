"""Does using a RISK characteristic as 20% of ALPHA weaken stock selection?

THE QUESTION, AND ONLY THE QUESTION
------------------------------------
Production's four-factor alpha is 0.30 momentum + 0.25 value + 0.25 quality +
0.20 `lowvol`. `alpha-risk-separation-v1` removed downside volatility from the
SELECTION SCORE's denominator and found nothing: -0.902pp, 95% CI
[-5.068, +3.210], contains zero — and its diagnostic extension then measured
WHY. On the name-dates the two rungs disagreed about, momentum separated them
by +0.687 and quality by +0.626 (well under a percentile point) while `lowvol`
moved -9.725 and realised downside volatility +5.157pp. The denominator was
not suppressing high-momentum or high-quality names; it was holding back the
SAME alpha at higher volatility.

That localised the surviving defensive tilt in the one risk channel neither
study touched: the `lowvol` sleeve INSIDE the alpha. This study removes that
sleeve, and nothing else.

    CONTROL     0.30 momentum + 0.25 value + 0.25 quality + 0.20 lowvol
    CHALLENGER  0.375 momentum + 0.3125 value + 0.3125 quality

The challenger's weights are not fitted. They are production's own 30:25:25
renormalized to sum to one — `THREE_FACTOR` is DERIVED from
`longterm.FACTOR_WEIGHTS` at import, so it cannot drift from the production
ratio it inherits.

A HARNESS DIFFERENCE, MEASURED AND PUBLISHED RATHER THAN HIDDEN
----------------------------------------------------------------
Production blends sleeve Z-SCORES. The sealed replay-v16 ledger does not
store them: it stores each sleeve's PERCENTILE within its region
(`factorPercentiles`), the blended `rawAlpha` as a single scalar, and
`evidenceCoverage`. The z-scores cannot be recovered from integer
percentiles, so production's exact blend arithmetic is unreachable from
sealed inputs — verified, not assumed.

So BOTH rungs blend the stored sleeve percentiles, and the axis between them
stays exactly one thing. What that costs is disclosed: this harness's own
four-factor CONTROL reproduces the published `alphaPercentile` at a rank
correlation of about 0.92, not 1.0. Per `switch-hurdle-v1`'s rule — a ladder
carries its own control, and the control's own gap to the published path is
published beside it — `harness_fidelity` measures that gap on every block and
the report leads with it.

HOW COVERAGE IS APPLIED, AND WHY IT IS CENTRED
-----------------------------------------------
Production computes `alpha = rawAlpha x evidenceCoverage`, where `rawAlpha`
is a signed z-blend centred near zero, so coverage SHRINKS a name toward
neutral — it pushes a negative alpha further down and a positive one further
up. A percentile blend is strictly positive, so multiplying it by coverage
would push every weakly-covered name DOWN regardless of sign, which is a
different operation wearing the same name.

`_rung_alpha` therefore centres the blend at 50 before applying coverage.
That choice was made against the CONTROL's fidelity to the published path,
BEFORE any rung was valued: measured rank correlation to the stored
`alphaPercentile` is 0.929 centred against 0.746 uncentred. It was not
selected by which gave the challenger a better result.

WHAT MAKES THIS A ONE-AXIS TEST (and the trap in section 5 of the design)
--------------------------------------------------------------------------
`longterm` computes `factorCoverage = sleevesPresent / len(FACTOR_WEIGHTS)`
and a source-quality term averaged over the sleeves a name has. Deleting
`lowvol` naively would drop factor coverage from 4/4 to 3/4 and shift source
quality (momentum and `lowvol` are 1.0; value and quality 0.6), costing about
14 points of `evidenceCoverage` — a mechanical penalty with nothing to do
with the hypothesis, which would make the challenger look worse for the wrong
reason.

This study does not recompute coverage at all. `evidenceCoverage` is taken
from the sealed row and is IDENTICAL on both rungs, so the penalty cannot
arise. `dataInsufficient`, `longTermResearchView`, `valueTrap`, the risk
block, `entryState`, sector, region and the research POOL itself are likewise
production's own, unchanged and shared. Only which sleeves enter the blend
moves.

Measured on the sealed ledger: ZERO of 399,547 name-dates have no
three-factor sleeve at all, so the challenger can rank every name the control
can. No eligibility diverges between the rungs.

WHAT THIS IS NOT. Not a promotion, not a production change, not a weight
sweep, and not a claim about whether low volatility is a good property. The
question is narrower: whether spending 20% of the ALPHA on a RISK
characteristic weakens the benchmark-relative selection signal, when the risk
denominator and inverse-volatility sizing are both left exactly as they are.
"""
from __future__ import annotations

from collections import defaultdict

import numpy as np

from . import alpha_reliability as AR
from . import kelly_portfolio as KP
from . import longterm as LT
from . import portfolio_validation as PV
from . import switch_hurdle as SH

VERSION = "lowvol-alpha-separation-v1"

CONTROL = "CONTROL_FOUR_FACTOR_ALPHA"
NO_LOWVOL = "NO_LOWVOL_IN_ALPHA"
LADDER = (CONTROL, NO_LOWVOL)

# Production's own weights, imported rather than re-declared.
FOUR_FACTOR: dict[str, float] = dict(LT.FACTOR_WEIGHTS)
# DERIVED from those, never chosen: drop `lowvol`, renormalize the rest so the
# 30:25:25 ratio production already uses is preserved exactly.
_REMAINING = {k: v for k, v in FOUR_FACTOR.items() if k != "lowvol"}
THREE_FACTOR: dict[str, float] = {k: v / sum(_REMAINING.values())
                                  for k, v in _REMAINING.items()}

# The percentile a blend is centred on before coverage is applied. This is the
# midpoint of a 0-100 percentile scale, not a tuned parameter.
NEUTRAL_PERCENTILE = 50.0


def sleeve_weights(rung: str) -> dict[str, float]:
    if rung == CONTROL:
        return dict(FOUR_FACTOR)
    if rung == NO_LOWVOL:
        return dict(THREE_FACTOR)
    raise ValueError(f"unknown rung: {rung}")


def blended_percentile(factor_percentiles: dict | None,
                       weights: dict[str, float]) -> float | None:
    """Weighted mean of the sleeve percentiles this strategy actually defines.

    Renormalized over the sleeves PRESENT among the rung's OWN sleeve set. A
    sleeve outside the set is not "missing" — it does not exist in this
    strategy — so its absence never enters a coverage count anywhere.
    """
    percentiles = factor_percentiles or {}
    total = weight = 0.0
    for sleeve, w in weights.items():
        value = PV._finite(percentiles.get(sleeve))
        if value is None:
            continue
        total += w * float(value)
        weight += w
    return total / weight if weight > 0 else None


def _rung_alpha(row: dict, weights: dict[str, float]) -> float | None:
    """The rung's alpha for one sealed row: centred blend x stored coverage.

    `evidenceCoverage` is production's own, read from the row and identical on
    both rungs — this study never recomputes it, so removing a sleeve cannot
    be mistaken for missing data.
    """
    blend = blended_percentile(row.get("factorPercentiles"), weights)
    if blend is None:
        return None
    coverage = PV._finite((row.get("features") or {}).get("evidenceCoverage"))
    if coverage is None:
        coverage = PV._finite(row.get("evidenceCoverage"))
    if coverage is None:
        return None
    return (blend - NEUTRAL_PERCENTILE) * float(coverage)


def rebuild_percentiles(signals: list[dict], rung: str) -> dict[str, dict[str, float]]:
    """`alphaPercentile` rebuilt under one rung, per date, within each region.

    Ranked across the FULL regional cross-section of that date — the same base
    production ranks on — not across the research pool, which would be a
    narrower and differently-shaped denominator. The rank-to-percentile
    transform is `longterm._percentile`'s: average ranks, scaled to 0-100 and
    rounded, so the calibration receives the granularity it was built for.
    """
    weights = sleeve_weights(rung)
    grouped: dict[tuple[str, str], list[tuple[str, float]]] = defaultdict(list)
    for row in signals:
        date, ticker = row.get("date"), row.get("ticker")
        if not date or not ticker:
            continue
        alpha = _rung_alpha(row, weights)
        if alpha is None:
            continue
        grouped[(date, row.get("region") or "UNKNOWN")].append((ticker, alpha))

    out: dict[str, dict[str, float]] = defaultdict(dict)
    for (date, _region), pairs in grouped.items():
        values = np.asarray([alpha for _, alpha in pairs], dtype=float)
        # `rank(method="average", pct=True) * 100`, rounded — matching
        # `longterm._percentile` rather than re-deriving a ranking rule.
        order = values.argsort()
        ranks = np.empty(len(values), dtype=float)
        ranks[order] = np.arange(1, len(values) + 1, dtype=float)
        # Average ranks over ties, exactly as pandas' "average" method does.
        for value in np.unique(values):
            tied = values == value
            if tied.sum() > 1:
                ranks[tied] = ranks[tied].mean()
        percentiles = np.round(ranks / len(values) * 100.0)
        for (ticker, _alpha), percentile in zip(pairs, percentiles, strict=True):
            out[date][ticker] = float(percentile)
    return dict(out)


def rung_candidates(raw_candidates: list[dict], rebuilt: dict[str, float]) -> list[dict]:
    """The production pool, with only `alphaPercentile` swapped for this rung's.

    COPIES. The contexts are shared across rungs, so editing a candidate in
    place would contaminate every rung after it — the defect
    `signal_persistence` already has a test for. The pool MEMBERSHIP is
    production's own and identical on both rungs; only the ranking quantity
    inside it moves.
    """
    out = []
    for candidate in raw_candidates:
        item = dict(candidate)
        percentile = rebuilt.get(candidate.get("ticker"))
        if percentile is not None:
            item["alphaPercentile"] = percentile
        out.append(item)
    return out


def run_rung(rung: str, *, contexts: dict, percentiles: dict, calibrator,
             calendar: list[dict], cfg_pf: dict, valuation) -> dict:
    """Value one rung on the fixed blocks.

    Downstream of the rebuilt percentile this is `alpha_reliability.CONTROL`'s
    pipeline exactly: `confidence_rows(persistence=False, confidence=False)`
    (a pass-through), `reliability_scores(hysteresis=False, cost_hurdle=False)`
    — which keeps the downside-volatility DENOMINATOR and the entry multiplier
    — then production's own `selection_and_baseline`.
    """
    from . import benchmark_alpha as BA

    if rung not in LADDER:
        raise ValueError(f"unknown rung: {rung}")
    research_cfg = BA.cost_config(cfg_pf)
    state = AR.ReliabilityState(AR.WINDOW_BLOCKS)
    rows, decisions, failures = [], [], []
    terminal_weights: dict[str, float] = {}

    for block in calendar:
        signal_date = block["signalDate"]
        calibrator.advance(signal_date)
        raw_candidates, macro = contexts.get(signal_date) or ([], {})
        rebuilt = percentiles.get(signal_date) or {}
        candidates = AR.confidence_rows(
            rung_candidates(raw_candidates, rebuilt), state, block["date"],
            persistence=False, confidence=False)
        incumbents = set(terminal_weights)
        scored = AR.reliability_scores(candidates, calibrator, research_cfg,
                                       as_of=block["date"], incumbents=incumbents,
                                       hysteresis=False, cost_hurdle=False)
        allocation = KP.selection_and_baseline(
            candidates, research_cfg, macro, scored=scored, method=rung)
        weights = allocation["weights"]
        selected = {c["ticker"]: c for c in allocation["selected"]}
        held = set(weights)
        cut_reasons, chosen = AR.annotate_selection(candidates, scored, research_cfg,
                                                    method=rung)
        if not held <= chosen:
            raise ValueError(f"SELECTION_ANNOTATION_DISAGREES_WITH_PATH at {block['date']}")
        for row in scored:
            row["selectionExclusionCodes"] = cut_reasons.get(row["ticker"])
        decision = {
            "date": block["date"], "replayDate": signal_date, "selector": rung,
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
    return {"rung": rung, "rows": rows, "decisions": decisions, "failures": failures,
            "complete": len(rows) == len(expected),
            "expectedBlocks": len(expected), "measuredBlocks": len(rows)}


def exploratory_label(*, persistence: bool, entry_at_weight: bool) -> str:
    parts = ["EXPLORATORY", "NO_LOWVOL"]
    if persistence:
        parts.append("PLUS_PERSISTENCE_K6")
    if entry_at_weight:
        parts.append("PLUS_ENTRY_AT_WEIGHT")
    return "_".join(parts)


def run_exploratory_rung(*, contexts: dict, percentiles: dict, calibrator,
                         calendar: list[dict], cfg_pf: dict, valuation,
                         persistence: bool, entry_at_weight: bool) -> dict:
    """A stacked path: no-lowvol alpha PLUS one or two other studies' axes.

    EXPLORATORY ONLY. Every rung here moves at least two axes and is
    attributable to NONE of them alone. It is never paired into the primary
    ladder and its number is never the lowvol sleeve's independent effect.

    Nothing is re-implemented: `persistence` is `signal-persistence-v1`'s k=6
    smoother through `AR.confidence_rows(persistence=True)`, and
    `entry_at_weight` is `entry-selection-separation-v1`'s own
    `entry_weighted_scores` plus its post-selection weight throttle, both
    called rather than copied.
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
        rebuilt = percentiles.get(signal_date) or {}
        candidates = AR.confidence_rows(
            rung_candidates(raw_candidates, rebuilt), state, block["date"],
            persistence=persistence, confidence=False)
        incumbents = set(terminal_weights)
        scored = AR.reliability_scores(candidates, calibrator, research_cfg,
                                       as_of=block["date"], incumbents=incumbents,
                                       hysteresis=False, cost_hurdle=False)
        ranking = ES.entry_weighted_scores(scored) if entry_at_weight else scored
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


def harness_fidelity(signals: list[dict], percentiles: dict) -> dict:
    """How closely THIS harness's control reproduces the published ranking.

    The sealed ledger cannot supply the sleeve z-scores production blends, so
    this harness blends stored percentiles instead and its control is
    therefore NOT the published path. `switch-hurdle-v1`'s rule is that a
    ladder carries its own control and the control's own gap to the published
    path is published beside it — this is that gap, measured per date and
    region rather than asserted.
    """
    grouped: dict[tuple[str, str], list[tuple[float, float]]] = defaultdict(list)
    for row in signals:
        date, ticker = row.get("date"), row.get("ticker")
        published = PV._finite(row.get("alphaPercentile"))
        rebuilt = (percentiles.get(date) or {}).get(ticker) if date else None
        if published is None or rebuilt is None:
            continue
        grouped[(date, row.get("region") or "UNKNOWN")].append((float(rebuilt), published))

    correlations, exact = [], []
    for pairs in grouped.values():
        if len(pairs) < 10:
            continue
        rebuilt = np.asarray([p[0] for p in pairs], dtype=float)
        published = np.asarray([p[1] for p in pairs], dtype=float)
        correlations.append(float(AR._spearman(rebuilt, published) or np.nan))
        exact.append(float((rebuilt == published).mean() * 100))
    usable = [c for c in correlations if not np.isnan(c)]
    return {
        "available": bool(usable),
        "crossSectionsMeasured": len(usable),
        "rankCorrelationToPublishedAlphaPercentile": _spread(usable),
        "exactPercentileMatchPct": _spread(exact),
        "note": (
            "The sealed ledger stores each sleeve's PERCENTILE, never the z-score "
            "production blends, so production's exact alpha arithmetic is unreachable "
            "from sealed inputs. Both rungs therefore blend percentiles and the axis "
            "between them is still exactly one thing — but this control is not the "
            "published path, and this is how far apart they are. A correlation well "
            "below 1.0 does not invalidate the paired comparison; it bounds how much "
            "of production's own ranking this harness reproduces."),
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


def sector_exposure(decisions: list[dict]) -> dict:
    """Held name-dates by sector, from the path's own decisions.

    Uses the sector metadata already on the scored rows. No growth label is
    invented and no external classification is introduced.
    """
    held_counts: dict[str, int] = defaultdict(int)
    total = 0
    for decision in decisions:
        scored = {row["ticker"]: row for row in (decision.get("scored") or [])}
        held = set(decision.get("retained") or []) | set(decision.get("added") or [])
        for ticker in held:
            row = scored.get(ticker)
            sector = (row or {}).get("sector") or "Unclassified"
            held_counts[sector] += 1
            total += 1
    shares = {sector: round(count / total * 100, 2) for sector, count in held_counts.items()} \
        if total else {}
    return {
        "heldNameDates": total,
        "bySector": dict(sorted(held_counts.items(), key=lambda kv: -kv[1])),
        "sharePct": dict(sorted(shares.items(), key=lambda kv: -kv[1])),
    }


def sector_shift(control: dict, challenger: dict) -> dict:
    """Challenger-minus-control share, in percentage points, per sector."""
    sectors = sorted(set(control.get("sharePct") or {}) | set(challenger.get("sharePct") or {}))
    deltas = {}
    for sector in sectors:
        left = (control.get("sharePct") or {}).get(sector, 0.0)
        right = (challenger.get("sharePct") or {}).get(sector, 0.0)
        deltas[sector] = round(right - left, 2)
    return {
        "sharePctDelta": dict(sorted(deltas.items(), key=lambda kv: -kv[1])),
        "note": ("Percentage points of held name-dates, challenger minus control. A "
                 "larger technology share is a DESCRIPTION of what removing the sleeve "
                 "did, never evidence that holding more technology is better."),
    }


def freeze_manifest() -> dict:
    return {
        "id": VERSION,
        "status": "CHALLENGER",
        "ladder": list(LADDER),
        "axis": "WHETHER_THE_LOWVOL_SLEEVE_BELONGS_INSIDE_THE_ALPHA",
        "controlWeights": dict(FOUR_FACTOR),
        "challengerWeights": dict(THREE_FACTOR),
        "challengerWeightsDerivedNotFitted": (
            "production's own 30:25:25 renormalized to sum to one, computed from "
            "longterm.FACTOR_WEIGHTS at import"),
        "harnessDifference": (
            "The sealed ledger stores sleeve PERCENTILES, never the z-scores "
            "production blends, so this harness's control is not the published path. "
            "`harness_fidelity` measures and publishes that gap."),
        "coverageRecomputed": False,
        "coverageIdenticalAcrossRungs": True,
        "eligibilityRecomputed": False,
        "researchPoolIdenticalAcrossRungs": True,
        "riskDenominatorRetainedOnBothRungs": True,
        "inverseVolSizingRetainedOnBothRungs": True,
        "entryLogicUnchanged": True,
        "regionAndSectorCapsUnchanged": True,
        "targetNamesUnchanged": 5,
        "permutationNullRun": False,
        "parametersIntroduced": [],
        "weightSweepPerformed": False,
        "heldFixedAcrossRungs": [
            "fixed 21-session evaluation blocks and their cadence",
            "the production research POOL and its membership",
            "momentum/value/quality sleeve definitions and their 30:25:25 ratio",
            "evidenceCoverage, dataInsufficient, longTermResearchView, valueTrap",
            "expanding bucket calibration of percentile to expected excess",
            "the selection score's downside-volatility denominator",
            "entry-state logic and the entry multiplier",
            "targetNames = 5, maxNamesPerSector, maxNamesPerRegion, cash floor",
            "inverse-downside-volatility sizing and the conviction tilt",
            "transaction costs, rebalance schedule, benchmark construction",
            "no persistence, no confidence contraction, no hysteresis, no cost hurdle",
        ],
        "promotionEligible": False,
        "liveValidated": False,
        "productionChanged": False,
    }
