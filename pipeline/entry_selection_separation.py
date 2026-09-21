"""Does entry state decide WHO is held, or only HOW FAST its weight is approached?

WHERE THIS CAME FROM
--------------------
`alpha_reliability.reliability_scores` computes
`score = decision / (risk * 100) * state`, where `state` is
`kelly_portfolio._state_multiplier`: 0.0 for a state that blocks sizing
outright (EVENT_RISK, AVOID, a non-POSITIVE research view, dataInsufficient,
valueTrap), 0.25 for WAIT_FOR_PULLBACK, 0.5 for WATCH, 1.0 for ACCUMULATE
(the unconditional default). The 0.0 case is an ELIGIBILITY fact and already
excludes the name from every rung in this line of studies. The 0.25/0.5
cases are not eligibility facts — they are a CONTINUOUS discount baked
straight into the ranking score alpha and risk are also scored on, so a
WATCH name's score is cut in half before it is ever compared to an
ACCUMULATE name's, which can push it out of the top-N cut entirely and can
change its rank inside the conviction tilt for names that DO make the cut.

`alpha-reliability-v1`'s own pre-registration named this study's separation:
alpha decides the held set; entry state decides how fast the target weight
is APPROACHED — ACCUMULATE to full weight, WATCH to part, WAIT_FOR_PULLBACK
throttles new entry, EVENT_RISK holds new entry. Read literally, none of
that is a claim about WHICH names get ranked and chosen; it is a claim
about how much of a chosen name's weight is deployed. Today's mechanism
does the opposite: the throttle acts at selection and never touches the
weight of a name that already made the cut.

THE AXIS, AND ONLY THE AXIS
----------------------------
    CONTROL          `alpha_reliability.CONTROL`, called directly. State
                      multiplies the SELECTION score (today's production
                      shape).
    ENTRY_AT_WEIGHT   The SAME score with the CONTINUOUS throttle divided
                      back out before selection and the conviction tilt —
                      `_alpha_only_score` recovers `decision / (risk * 100)`
                      exactly, using `entryStateMultiplier` the row already
                      carries. Selection and the tilt rank are then decided
                      by alpha and risk alone. AFTER `baseline_weights`
                      computes the risk-parity, tilt-adjusted target weight
                      for each held name, that SAME name's own
                      `entryStateMultiplier` — 0.25, 0.5 or 1.0, the exact
                      values production already uses, never re-derived — is
                      applied ONCE to shrink the weight actually taken.
                      Capital the throttle withholds is left in cash, never
                      redistributed to other names: an under-approached
                      position is not fully funded yet, not a signal to
                      fund something else more.

WHAT THIS AXIS DOES NOT TOUCH
-------------------------------
A state whose multiplier is 0.0 remains a full eligibility exclusion on
BOTH rungs, for both new entries and incumbents, exactly as production
computes it today. Whether an INCUMBENT should be forced out at all when
its state degrades to a blocking one is explicitly a separate claim about
EXITS in the pre-registration, and gets its own test — this study changes
only the CONTINUOUS throttle's role, never eligibility, never an exit rule.
`targetNames`, `maxNamesPerSector`, `maxNamesPerRegion`, the cash floor and
every cost assumption are unchanged from `alpha_reliability.CONTROL`.
"""
from __future__ import annotations

from . import alpha_reliability as AR
from . import kelly_portfolio as KP
from . import switch_hurdle as SH

VERSION = "entry-selection-separation-v1"

CONTROL = AR.CONTROL
ENTRY_AT_WEIGHT = "ENTRY_STATE_THROTTLES_WEIGHT_NOT_SELECTION"
LADDER = (CONTROL, ENTRY_AT_WEIGHT)


def _alpha_only_score(row: dict) -> float | None:
    """`row["score"]` with the entry-state throttle divided back out.

    For an ELIGIBLE row `entryStateMultiplier` is always > 0 (a multiplier of
    0.0 is itself the eligibility exclusion), so the division is safe and
    exact: `score / state == decision / (risk * 100)`, the alpha/risk
    quantity with no state term. An ineligible row's score is returned
    unchanged — it plays no further role once excluded.
    """
    score = row.get("score")
    state = row.get("entryStateMultiplier")
    if score is None or state is None or state <= 0:
        return score
    return score / state


def entry_weighted_scores(scored: list[dict]) -> list[dict]:
    """`AR.reliability_scores`'s own rows, ranking score with the throttle removed.

    Returns NEW row dicts with a NEW `exclusionCodes` list per row — never the
    input list's row objects or their list values. `select_portfolio_by_scores`
    appends cut codes into `exclusionCodes` in place; without this copy that
    mutation would leak into the CONTROL rows this function is handed, exactly
    the defect `eligibilityCodes` exists to keep separate from `exclusionCodes`
    elsewhere in this line of studies. `selected` is dropped rather than
    copied: `select_portfolio_by_scores` builds its OWN internal row copies
    and never mutates the list handed to it, so a `selected` flag carried over
    from the input would be the OLD selection's answer wearing the new score.
    """
    out = []
    for row in scored:
        item = dict(row)
        item["score"] = _alpha_only_score(row)
        item["convictionScore"] = item["score"]
        item["exclusionCodes"] = list(row.get("exclusionCodes") or [])
        item.pop("selected", None)
        out.append(item)
    return out


def run_entry_at_weight_rung(*, contexts: dict, calibrator, calendar: list[dict],
                             cfg_pf: dict, valuation) -> dict:
    """Value the entry-at-weight rung on the fixed blocks.

    Candidate assembly and the underlying alpha/risk score are IDENTICAL to
    `alpha_reliability`'s own CONTROL — `AR.confidence_rows` and
    `AR.reliability_scores` are called unmodified. Only the SCORE handed to
    selection and the tilt (`entry_weighted_scores`) and a post-hoc weight
    throttle (below) differ.
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
        if not AR.contraction_holds(scored):
            raise ValueError(f"CONFIDENCE_AMPLIFIED_AN_ALPHA_CLAIM at {block['date']}")
        alpha_only = entry_weighted_scores(scored)
        selected, selection = KP.select_portfolio_by_scores(
            alpha_only, alpha_only, research_cfg, method=ENTRY_AT_WEIGHT)
        raw_weights = KP.baseline_weights(selected, research_cfg, ranking_rows=alpha_only)
        state_by_ticker = {row["ticker"]: row.get("entryStateMultiplier") for row in scored}
        weights = {t: w * float(state_by_ticker.get(t) or 0.0) for t, w in raw_weights.items()}
        selected_by_ticker = {c["ticker"]: c for c in selected}
        held = set(weights)

        cut_reasons, chosen = AR.annotate_selection(candidates, alpha_only, research_cfg,
                                                     method=ENTRY_AT_WEIGHT)
        if not held <= chosen:
            raise ValueError(f"SELECTION_ANNOTATION_DISAGREES_WITH_PATH at {block['date']}")
        for row in alpha_only:
            row["selectionExclusionCodes"] = cut_reasons.get(row["ticker"])

        decision = {
            "date": block["date"], "replayDate": signal_date, "selector": ENTRY_AT_WEIGHT,
            "weights": weights,
            "regionByTicker": {t: selected_by_ticker[t].get("region") for t in weights},
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
            "retainedByRegion": SH._count_by_region(held & incumbents, alpha_only),
            "replacedByRegion": SH._count_by_region(incumbents - held, alpha_only),
            "scored": alpha_only,
            "entryStateMultiplierByTicker": state_by_ticker,
            "valuationStatus": diagnostic["status"],
        })
        if outcome is None:
            failures.append({**block, **diagnostic})
            continue
        rows.append(outcome)
        terminal_weights = dict(outcome.get("terminalWeights") or {})
    expected = [b for b in calendar if b["endDate"] <= valuation.through]
    return {"rung": ENTRY_AT_WEIGHT, "rows": rows, "decisions": decisions,
            "failures": failures, "complete": len(rows) == len(expected),
            "expectedBlocks": len(expected), "measuredBlocks": len(rows)}


def _state_label(row: dict) -> str:
    return row.get("entryState") or "WATCH"


def entry_state_incidence(control_decisions: list[dict], cfg_pf: dict) -> dict:
    """Before the ladder: how much would selection change if state didn't discount score?

    Reads the CONTROL path's own scored candidates — the exact stream this
    study's rung also ranks from — and recomputes the selected set with the
    SAME production cap machinery (`select_portfolio_by_scores`, never
    re-derived) on the alpha-only score. Reports the entry-state distribution
    among eligible and held names, and how often the two selected sets
    disagree, so a reader can see whether this axis has any bite BEFORE the
    ladder's performance numbers are read.
    """
    eligible_states: dict[str, int] = {}
    held_states: dict[str, int] = {}
    changed_rebalances = 0
    names_the_discount_kept_out = 0
    names_the_discount_let_in = 0
    measured = 0
    for decision in control_decisions:
        scored = decision.get("scored") or []
        if not scored:
            continue
        measured += 1
        for row in scored:
            if not row.get("eligible"):
                continue
            label = _state_label(row)
            eligible_states[label] = eligible_states.get(label, 0) + 1
            if row.get("selected"):
                held_states[label] = held_states.get(label, 0) + 1
        original_selected = {r["ticker"] for r in scored if r.get("selected")}
        alpha_only = entry_weighted_scores(scored)
        alpha_only_chosen, _ = KP.select_portfolio_by_scores(
            alpha_only, alpha_only, cfg_pf, method=ENTRY_AT_WEIGHT)
        alpha_only_selected = {c["ticker"] for c in alpha_only_chosen}
        if alpha_only_selected != original_selected:
            changed_rebalances += 1
            names_the_discount_kept_out += len(alpha_only_selected - original_selected)
            names_the_discount_let_in += len(original_selected - alpha_only_selected)
    return {
        "measuredRebalances": measured,
        "eligibleByState": dict(sorted(eligible_states.items())),
        "heldByState": dict(sorted(held_states.items())),
        "rebalancesWhereSelectionWouldChange": changed_rebalances,
        "rebalancesWhereSelectionWouldChangePct": (
            round(100.0 * changed_rebalances / measured, 2) if measured else None),
        "namesTheDiscountKeptOutOfTheBook": names_the_discount_kept_out,
        "namesTheDiscountLetIntoTheBook": names_the_discount_let_in,
    }


def _spread(values: list[float]) -> dict:
    if not values:
        return {"available": False, "observations": 0}
    ordered = sorted(values)
    n = len(ordered)
    mean = sum(ordered) / n

    def _pct(p: float) -> float:
        idx = min(n - 1, max(0, round(p / 100.0 * (n - 1))))
        return ordered[idx]
    return {
        "available": True, "observations": n, "mean": round(mean, 4),
        "median": round(_pct(50), 4), "p10": round(_pct(10), 4), "p90": round(_pct(90), 4),
    }


def weight_throttle_summary(entry_decisions: list[dict]) -> dict:
    """On the entry-at-weight rung: how much target weight sits unapproached in cash.

    Read from this rung's OWN decisions, never inferred from the control's.
    """
    throttled = 0
    total = 0
    unapproached_pct: list[float] = []
    for decision in entry_decisions:
        multipliers = decision.get("entryStateMultiplierByTicker") or {}
        held = set(decision.get("retained") or []) | set(decision.get("added") or [])
        for ticker in held:
            total += 1
            multiplier = multipliers.get(ticker)
            if multiplier is not None and multiplier < 0.999:
                throttled += 1
                unapproached_pct.append(round((1.0 - float(multiplier)) * 100, 3))
    return {
        "heldNameDates": total,
        "throttledNameDates": throttled,
        "throttledNameDatesPct": round(100.0 * throttled / total, 2) if total else None,
        "unapproachedWeightPctWhenThrottled": _spread(unapproached_pct),
    }


def freeze_manifest() -> dict:
    return {
        "id": VERSION,
        "status": "CHALLENGER",
        "ladder": list(LADDER),
        "controlSource": "alpha_reliability.run_rung(alpha_reliability.CONTROL, ...), unmodified",
        "axis": ("WHETHER_ENTRY_STATE_DISCOUNTS_THE_SELECTION_SCORE_OR_ONLY_"
                 "THROTTLES_THE_HELD_WEIGHT"),
        "eligibilityUnchanged": (
            "A state whose multiplier is 0 (EVENT_RISK, AVOID, dataInsufficient, "
            "valueTrap, non-POSITIVE research view) still excludes the name on BOTH "
            "rungs -- this axis is the CONTINUOUS throttle (0.25 WAIT_FOR_PULLBACK, "
            "0.5 WATCH), never eligibility. Whether an incumbent should be forced out "
            "on a blocking state at all is the next study's claim about exits, per the "
            "pre-registration, and is untouched here."
        ),
        "weightRedistribution": "NONE -- throttled capital is left in cash, never reallocated",
        "targetNamesSectorRegionCapsCostAssumptionsUnchanged": True,
        "permutationNullRun": False,
        "parametersIntroduced": [],
        "heldFixedAcrossRungs": [
            "fixed 21-session evaluation blocks and their cadence",
            "PIT research candidate pool",
            "0.30/0.25/0.25/0.20 momentum/value/quality/low-vol sleeve weights",
            "expanding bucket calibration of percentile to expected excess",
            "the entry-state multiplier's VALUES (0.25/0.5/1.0) -- only its ROLE moves",
            "targetNames = 5, maxNamesPerSector = 2, maxNamesPerRegion = 3, "
            "maxPositionWeight, cash floor",
            "inverse-downside-volatility conviction-tilted position sizing base",
            "no backward-percentile smoothing, no confidence contraction, no signal "
            "hysteresis, no transaction-cost hurdle, no dynamic breadth, no region "
            "quota removal",
        ],
        "promotionEligible": False,
        "liveValidated": False,
        "productionChanged": False,
    }
