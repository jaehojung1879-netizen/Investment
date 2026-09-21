"""Is downside risk spent twice: once on the alpha, once on the ranking?

WHERE THIS CAME FROM
--------------------
`alpha-reliability-v1` measured, on the production path, that the score's rank
correlation with the calibrated alpha is 0.758 against 0.075 with downside
volatility — alpha orders most PAIRS — but a five-name book is decided at its
MARGIN, where 86.71% of cuts are between names the calibration scores
IDENTICALLY. There, what remains ordering the cut is the risk-and-entry
product in the score's denominator. And the tilt that denominator produces is
visible in what is HELD: 24.45% downside volatility against 27.17% rejected,
`lowvol` sleeve percentile 74.37 against 63.81, `lowvol` among a held name's
top two sleeves 58.86% of the time.

Downside risk enters this system through THREE separate channels: it is 0.20
of the four-factor alpha (the `lowvol` sleeve), it is the DENOMINATOR of the
selection score (`expected excess / downside volatility`), and it is the base
of the position size (`1 / downside volatility`, inverse-vol weighting). The
first and third are decisions this study does not touch. The second is the
one channel that decides WHICH FIVE NAMES are held at all, and it is the one
this study removes.

THE AXIS, AND ONLY THE AXIS
----------------------------
    CONTROL     `alpha-reliability-v1`'s own CONTROL rung, run unmodified via
                `alpha_reliability.run_rung`. Score = calibrated alpha /
                (downside volatility x 100) x entry multiplier. This is not a
                reproduction — it IS that path, called directly, so there is
                no second implementation of it to drift from the first.
    ALPHA_ONLY  the SAME candidate stream, the SAME calibration, the SAME
                entry multiplier, the SAME eligibility facts. The one thing
                that changes: the score's denominator. Score = calibrated
                alpha x entry multiplier — no division by risk anywhere in
                the ranking or the rank-based conviction tilt.

`DOWNSIDE_RISK_UNAVAILABLE` stays an exclusion on BOTH rungs. A name with no
risk unit cannot be SIZED regardless of how it is ranked — inverse-downside-
volatility sizing is a fact about the name, not a ranking decision, and this
study does not touch it. Removing the denominator from the SCORE is not the
same thing as pretending the risk does not exist.

WHAT ELSE THE SCORE'S DOUBLE DUTY MEANS
----------------------------------------
`selection_and_baseline` hands the same `scored` list to two consumers:
`select_portfolio_by_scores` (which five names) and `baseline_weights` (the
0.5x-1.5x conviction TILT among the five, ranked by the same score). Removing
the denominator therefore changes the tilt's rank order along with the
selection — which is correct, because both are downstream of the SAME
"selection ranking" the pre-registration named. What does NOT change is the
tilt's BASE: `1 / max(risk_unit, 0.05)`, computed identically on both rungs.
Inverse-volatility sizing is exactly as it was; only the ranking that decides
who receives it, and how much extra tilt on top of it, no longer divides by
risk.

WHAT THIS IS NOT. Not a promotion, not a production change, and not a claim
that either rung beats the benchmark going forward. It does not move the
`lowvol` sleeve's 0.20 weight inside the four-factor alpha — `alpha-
reliability-v1` measured that part of the tilt arrives through the alpha
itself and would therefore SURVIVE this rung's change; whether it does is
measured here, not assumed, and if it survives that is the next study's axis,
not a reason to widen this one. No persistence, no confidence contraction, no
signal hysteresis and no transaction-cost hurdle enter either rung — this
ladder moves exactly the one axis it was pre-registered to move.
"""
from __future__ import annotations

from . import alpha_reliability as AR
from . import kelly_portfolio as KP
from . import portfolio_validation as PV
from . import switch_hurdle as SH

VERSION = "alpha-risk-separation-v1"

# `alpha_reliability.CONTROL` run unmodified, not reproduced. See module
# docstring: calling the existing function is how this ladder avoids a second
# implementation of the control path to drift from the first.
CONTROL = AR.CONTROL
ALPHA_ONLY = "RANK_ON_CALIBRATED_ALPHA_ONLY_NO_RISK_DENOMINATOR"
LADDER = (CONTROL, ALPHA_ONLY)


def separation_scores(rows: list[dict], calibration: PV.ExpandingBucketCalibration,
                      cfg_pf: dict) -> list[dict]:
    """Score on calibrated alpha alone: no downside-volatility denominator.

    Same eligibility facts as `alpha_reliability.reliability_scores`, same
    field shape (so every diagnostic built for that module reads this one's
    output without a special case), and the SAME risk-unavailability
    exclusion — a name still cannot be SIZED without a downside-vol unit,
    whatever the ranking divides by. The only formula that changes is the
    score itself.
    """
    out = []
    for row in rows:
        ticker, region = row["ticker"], row.get("region") or "UNKNOWN"
        estimate = calibration.expected(region, row.get("alphaPercentile"))
        alpha = (estimate or {}).get("expectedExcessReturnPct")
        risk = KP._risk_unit(row)
        state = KP._state_multiplier(row, cfg_pf)

        excluded = []
        if estimate is None:
            excluded.append("MATURED_CALIBRATION_NOT_READY")
        if risk is None or risk <= 0:
            excluded.append("DOWNSIDE_RISK_UNAVAILABLE")
        if state <= 0:
            excluded.append("ENTRY_OR_RESEARCH_STATE_BLOCKS_SIZING")

        # THE ONE LINE THAT DIFFERS FROM THE CONTROL: no `/ (risk * 100)`.
        score = float(alpha) * state if alpha is not None else -1e12

        out.append({
            "ticker": ticker, "region": region,
            "sector": row.get("sector") or "Unclassified",
            "score": score, "convictionScore": score,
            "alphaPercentile": row.get("alphaPercentile"),
            "rawAlphaPercentile": row.get("alphaPercentile"),
            "downsideVolPct": risk * 100 if risk else None,
            "evidenceCoverage": row.get("evidenceCoverage"),
            "expectedGrossBenchmarkExcessPct": alpha,
            # Carried at their neutral values so every `alpha_reliability`
            # diagnostic (which reads these keys) runs unmodified on this
            # rung's rows: confidence is not an axis this study moves.
            "reliableAlphaPct": alpha,
            "signalConfidence": 1.0,
            "uncertaintyMarginPct": 0.0,
            "factorPercentiles": dict(row.get("factorPercentiles") or {}),
            "entryState": ((row.get("entry") or {}).get("entryState")
                           or row.get("entryState")),
            "entryStateMultiplier": state,
            "decisionAlphaPct": alpha,
            "eligible": not excluded, "exclusionCodes": excluded,
            "eligibilityCodes": tuple(excluded),
            "calibration": estimate,
        })
    return out


def run_alpha_only_rung(*, contexts: dict, calibrator, calendar: list[dict],
                        cfg_pf: dict, valuation) -> dict:
    """Value the ALPHA_ONLY rung on the fixed blocks.

    Structurally the same loop `alpha_reliability.run_rung` runs for its
    CONTROL — same candidate assembly (`persistence=False, confidence=False`,
    so `confidence_rows` is a pass-through and contributes nothing this study
    does not already hold fixed), same research cost config, same incumbency
    bookkeeping, same selection-annotation reconciliation. The only thing
    that differs is which scoring function is called.
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
        scored = separation_scores(candidates, calibrator, research_cfg)
        allocation = KP.selection_and_baseline(
            candidates, research_cfg, macro, scored=scored, method=ALPHA_ONLY)
        weights = allocation["weights"]
        selected = {c["ticker"]: c for c in allocation["selected"]}
        held = set(weights)
        cut_reasons, chosen = AR.annotate_selection(candidates, scored, research_cfg,
                                                     method=ALPHA_ONLY)
        if not held <= chosen:
            raise ValueError(f"SELECTION_ANNOTATION_DISAGREES_WITH_PATH at {block['date']}")
        for row in scored:
            row["selectionExclusionCodes"] = cut_reasons.get(row["ticker"])
        decision = {
            "date": block["date"], "replayDate": signal_date, "selector": ALPHA_ONLY,
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
    return {"rung": ALPHA_ONLY, "rows": rows, "decisions": decisions, "failures": failures,
            "complete": len(rows) == len(expected),
            "expectedBlocks": len(expected), "measuredBlocks": len(rows)}


# --------------------------------------------------------------------------- #
# Did the tilt survive?
# --------------------------------------------------------------------------- #
def tilt_survival(control_diag: dict, alpha_only_diag: dict) -> dict:
    """Compares the two rungs' `risk_dominance` readings directly.

    `alpha-reliability-v1` named the question this answers: if a defensive
    tilt survives the denominator's removal, that is the NEXT study's axis
    (moving the `lowvol` sleeve itself), not this one's. This does not decide
    that question — it reports the comparison the decision is made from.
    """
    def delta(key, sub="mean"):
        a = (control_diag.get(key) or {}).get(sub)
        b = (alpha_only_diag.get(key) or {}).get(sub)
        if a is None or b is None:
            return None
        return round(float(b) - float(a), 4)

    return {
        "available": bool(control_diag.get("available") and alpha_only_diag.get("available")),
        "downsideVolPctSelectedDelta": delta("downsideVolPctSelected"),
        "downsideVolPctRejectedDelta": delta("downsideVolPctRejected"),
        "lowvolSleevePercentileSelectedDelta": delta("lowvolSleevePercentileSelected"),
        "lowvolIsTheHighestSleevePctDelta": (
            None if control_diag.get("lowvolIsTheHighestSleevePct") is None
            or alpha_only_diag.get("lowvolIsTheHighestSleevePct") is None else
            round(alpha_only_diag["lowvolIsTheHighestSleevePct"]
                  - control_diag["lowvolIsTheHighestSleevePct"], 2)),
        "lowvolIsInTheTopTwoSleevesPctDelta": (
            None if control_diag.get("lowvolIsInTheTopTwoSleevesPct") is None
            or alpha_only_diag.get("lowvolIsInTheTopTwoSleevesPct") is None else
            round(alpha_only_diag["lowvolIsInTheTopTwoSleevesPct"]
                  - control_diag["lowvolIsInTheTopTwoSleevesPct"], 2)),
        "scoreVsDownsideVolSpearmanControl": (control_diag.get(
            "scoreVsDownsideVolSpearman") or {}).get("mean"),
        "scoreVsDownsideVolSpearmanAlphaOnly": (alpha_only_diag.get(
            "scoreVsDownsideVolSpearman") or {}).get("mean"),
        "note": ("A negative vol/lowvol-percentile delta and a near-zero "
                 "score/downside-vol correlation on ALPHA_ONLY together would mean the "
                 "denominator was the channel. Values that stay close to the control's "
                 "mean the tilt survives — it must be arriving through the alpha term "
                 "itself, which is the sleeve this study does not touch, and is the "
                 "next study's axis rather than a reason to reopen this one."),
    }


def freeze_manifest() -> dict:
    return {
        "id": VERSION,
        "status": "CHALLENGER",
        "ladder": list(LADDER),
        "controlSource": "alpha_reliability.run_rung(alpha_reliability.CONTROL, ...), unmodified",
        "axis": "WHETHER_THE_SELECTION_SCORE_DIVIDES_BY_DOWNSIDE_VOLATILITY",
        "scoreFormulaControl": "calibratedAlpha / (downsideVolPct x 100) x entryMultiplier",
        "scoreFormulaChallenger": "calibratedAlpha x entryMultiplier",
        "riskChannelsInThisSystem": {
            "alphaLevel": "lowvol sleeve, 0.20 weight — UNCHANGED, out of scope for this study",
            "selectionRanking": "downside-vol denominator in the score — REMOVED on ALPHA_ONLY",
            "positionSizing": "inverse-downside-vol base weight — UNCHANGED on both rungs",
        },
        "downsideRiskUnavailableStillExcludesBothRungs": True,
        "permutationNullRun": False,
        "parametersIntroduced": [],
        "heldFixedAcrossRungs": [
            "fixed 21-session evaluation blocks and their cadence",
            "PIT research candidate pool",
            "0.30/0.25/0.25/0.20 momentum/value/quality/low-vol sleeve weights",
            "expanding bucket calibration of percentile to expected excess",
            "entry-state and research-view exclusions",
            "name/sector/region caps, maxPositionWeight, cash floor",
            "inverse-downside-volatility BASE weight",
            "no backward-percentile smoothing, no confidence contraction, no signal "
            "hysteresis, no transaction-cost hurdle",
        ],
        "promotionEligible": False,
        "liveValidated": False,
        "productionChanged": False,
    }
