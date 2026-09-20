"""Replace an incumbent only when the improvement pays for the swap.

WHY, AND WHY PER REGION
-----------------------
The published calibrated challenger rebalances every 21 sessions and replaces
about three of its five names each time. That is 4.56x annual one-way turnover
against an arithmetic stock-selection edge of +0.040pp/yr, and the bill comes
to 1.386pp — the deficit to the matched benchmark is an implementation cost,
not an ordering failure (`selection_value`). `benchmark-relative-alpha-v1`
named the remedy and then tested it bundled with two other changes, so nothing
learned which one cost what.

WHAT THIS ISOLATES. One thing: the replacement decision. Cadence stays at every
block, the cash floor and caps stay production, and there is NO positive-alpha
cash gate — v1's gate drove average cash to 46% and emptied eight quarters
outright, which is a separate lever and belongs in its own rung.

THE HURDLE IS THE TAX CODE, NOT A TUNED KNOB. A swap costs the sell leg of the
name leaving and the buy leg of the name arriving, and `_turnover_cost` already
prices those differently: a buy pays commission plus half the spread, a sell
pays that plus the statutory sell tax. In Korea that tax has run 30bp down to
15bp over the replay and it dominates — measured off the dated schedule, a
Korean round trip costs 1.6x to 2.5x an American one, by year:

    2013  US 0.163%  KR 0.410%  (2.52x)      2023  US 0.163%  KR 0.310%  (1.90x)
    2019  US 0.163%  KR 0.360%  (2.21x)      2026  US 0.163%  KR 0.310%  (1.90x)

So an incumbent is credited the sell cost of ITS OWN region and a challenger is
charged the buy cost of ITS OWN region, with nobody choosing the ratio between
them:

    sell_cost = commission + spread/2 + sellTax        (what staying avoids)
    buy_cost  = commission + spread/2                  (what arriving costs)

THE OBVIOUS PREDICTION FROM THAT IS WRONG, AND MEASURING IT IS HOW WE KNOW.
Korea's credit is three times America's, so Korean positions should have become
the stickier ones. Measured against the no-hurdle control they did the opposite:
US retention went 41.2% -> 88.0% (+46.8pp) and Korean retention only
53.2% -> 62.9% (+9.7pp). A credit is spent against the GAP between the names
competing for the slot, not against zero, so what decides whether it flips an
ordering is the dispersion of expected alpha inside that region rather than the
size of the credit. Korea also runs at its `maxNamesPerRegion` cap with roughly
three of twelve pool names held against America's one or two, so a Korean
incumbent faces more internal competition per rebalance. Pooling the regions
would still be wrong — the costs really do differ by 1.6x to 2.5x — but "the
expensive market gets protected more" was an assumption, and it did not survive.

TWO RUNGS, FIXED BEFORE THE RESULT. `selection_value` established that a rung
moving several things at once cannot be read, so:

    COST        an incumbent must be beaten by more than the friction of the
                swap. Nothing estimated enters the hurdle.
    COST_PLUS_SE  additionally by one standard error of the bucket estimate
                behind the challenger's alpha. `k = 1` is fixed a priori; it is
                the natural unit of "the gap is bigger than the noise", not a
                value chosen because it scored well.

AND THE GAIN IS NOT THE ONE THE RULE WAS DESIGNED TO COLLECT. Against its
control the cost rung saves 0.27pp of cost drag (1.404 -> 1.133) and gains
2.16pp of ARITHMETIC STOCK SELECTION (+0.315 -> +2.471). Eight times more of it
comes from the book holding names longer than from the fees it avoids: chasing
each month's top-ranked name was destroying gross return, and the hurdle stopped
that as a side effect of being designed for something else. A rule that works
for a reason its author did not predict is weaker evidence than one that works
for the stated reason, and that is why this stays a CHALLENGER with prospective
evidence still to collect, not a result to act on.

WHAT THIS IS NOT. It is not a promotion, not a production change, and not a
claim that either rung beats the benchmark going forward. On 155 blocks the
paired interval on the cost rung clears zero by 0.122pp at its lower bound —
thin, on one historical sample, after several rungs have been looked at, and
with no correction for that. A rung ending higher is a point estimate and is
reported as one.
"""
from __future__ import annotations

from copy import deepcopy

import pandas as pd

from . import benchmark_alpha as BA
from . import kelly_portfolio as KP
from . import portfolio_validation as PV

VERSION = "regional-switch-hurdle-v1"

# The control rung. It runs the SAME loop with the hurdle switched off, so it
# must reproduce the published challenger path. Without it a difference between
# this module's books and the sealed one is attributable to the hurdle or to any
# other way this loop happens to differ from `portfolio_replay`, and there is no
# way to tell which — the confound `selection_value` was built to avoid and that
# `benchmark-relative-alpha-v1` fell into. A ladder whose control does not
# reproduce its baseline reports nothing about the rungs above it.
CONTROL = "NO_HURDLE_CONTROL_SAME_LOOP"
COST = "SWITCH_HURDLE_ROUND_TRIP_COST"
COST_PLUS_SE = "SWITCH_HURDLE_ROUND_TRIP_COST_PLUS_ONE_STANDARD_ERROR"
LADDER = (CONTROL, COST, COST_PLUS_SE)

# One standard error. The unit of "this gap is larger than the noise behind it",
# fixed before the result and never swept.
SE_MULTIPLE = 1.0


def leg_costs(region: str, as_of: str, cfg_pf: dict) -> tuple[float, float]:
    """`(buy, sell)` cost in percentage points, on the dated regional schedule.

    Same split `portfolio_validation._turnover_cost` charges the realised path,
    so the hurdle a decision clears is the cost that decision will actually pay
    rather than a second cost model invented for the ranking.
    """
    policy = PV._dated_cost_policy(
        ((cfg_pf.get("transactionCosts") or {}).get(region) or {}), as_of)
    commission = float(policy.get("commissionBps", 0))
    half_spread = float(policy.get("spreadBps", 0)) / 2
    buy = (commission + half_spread) / 100.0
    sell = (commission + half_spread + float(policy.get("sellTaxBps", 0))) / 100.0
    return buy, sell


def hurdle_scores(candidates: list[dict], calibration: PV.ExpandingBucketCalibration,
                  cfg_pf: dict, *, as_of: str, incumbents: set[str] | None = None,
                  se_multiple: float = 0.0, apply_cost: bool = True) -> list[dict]:
    """Rank on expected alpha adjusted for what acting on it costs.

    An incumbent carries `+ sell_cost`: the friction it avoids by staying. A
    challenger carries `- buy_cost`, and under `COST_PLUS_SE` also
    `- se_multiple x SE`, the precision of the bucket its alpha came from.

    ELIGIBILITY IS NOT THE HURDLE. The hurdle moves ORDER only. A name with no
    matured calibration, no downside-risk unit, or an entry state that blocks
    sizing is excluded on a fact about the name, exactly as the production
    challenger excludes it — an incumbent cannot survive on its retention credit
    once it stops being eligible to hold at all.
    """
    incumbents = incumbents or set()
    rows = []
    for candidate in candidates:
        region = candidate.get("region") or "UNKNOWN"
        estimate = calibration.expected(region, candidate.get("alphaPercentile"))
        alpha = (estimate or {}).get("expectedExcessReturnPct")
        risk = KP._risk_unit(candidate)
        state = KP._state_multiplier(candidate, cfg_pf)
        buy, sell = leg_costs(region, as_of, cfg_pf)
        if not apply_cost:
            buy = sell = 0.0
        incumbent = candidate["ticker"] in incumbents

        # The SE is published on the RAW bucket mean; the alpha carried here is
        # the shrunk one, so the margin is scaled the same way or it would be
        # denominated in a different quantity than the thing it gates.
        raw_se = (estimate or {}).get("standardErrorPct")
        shrink = float((estimate or {}).get("shrinkageFactor") or 0.0)
        margin = (float(raw_se) * shrink * float(se_multiple)
                  if raw_se is not None and se_multiple else 0.0)

        if alpha is None:
            decision_alpha = None
        elif incumbent:
            decision_alpha = float(alpha) + sell
        else:
            decision_alpha = float(alpha) - buy - margin

        excluded = []
        if estimate is None:
            excluded.append("MATURED_CALIBRATION_NOT_READY")
        if risk is None or risk <= 0:
            excluded.append("DOWNSIDE_RISK_UNAVAILABLE")
        if state <= 0:
            excluded.append("ENTRY_OR_RESEARCH_STATE_BLOCKS_SIZING")
        score = (decision_alpha / (risk * 100) * state
                 if decision_alpha is not None and risk and risk > 0 else -1e12)
        rows.append({
            "ticker": candidate["ticker"], "region": region,
            "sector": candidate.get("sector") or "Unclassified",
            "score": score, "convictionScore": score,
            "alphaPercentile": candidate.get("alphaPercentile"),
            "downsideVolPct": risk * 100 if risk else None,
            "evidenceCoverage": candidate.get("evidenceCoverage"),
            "expectedGrossBenchmarkExcessPct": alpha,
            "buyCostPct": round(buy, 5), "sellCostPct": round(sell, 5),
            "uncertaintyMarginPct": round(margin, 5),
            "incumbent": incumbent,
            "retentionCreditPct": round(sell, 5) if incumbent else 0.0,
            "decisionAlphaPct": decision_alpha,
            "eligible": not excluded, "exclusionCodes": excluded,
            "calibration": estimate,
        })
    return rows


def freeze_manifest() -> dict:
    return {
        "id": VERSION,
        "status": "CHALLENGER",
        "ladder": list(LADDER),
        "rankingSource": "CALIBRATED_EXPECTED_BENCHMARK_EXCESS_PER_DOWNSIDE_RISK",
        "decisionCadence": "EVERY_FIXED_21D_EVALUATION_BLOCK",
        "hurdle": "INCUMBENT_CREDITED_ITS_REGION_SELL_COST_CHALLENGER_CHARGED_ITS_REGION_BUY_COST",
        "costSource": "SAME_DATED_SCHEDULE_THE_REALISED_PATH_PAYS",
        "seMultiple": SE_MULTIPLE,
        "positiveAlphaCashGate": False,
        "heldFixedAgainstThePublishedChallenger": [
            "fixed 21-session evaluation blocks and their cadence",
            "PIT research candidate pool",
            "calibrated expected-benchmark-excess ranking",
            "entry-state and research-view exclusions",
            "name/sector/region caps, maxPositionWeight, cash floor",
            "conviction-tilted inverse-downside-volatility weights",
            "realistic dated transaction cost schedule",
        ],
        "varied": ["whether replacing an incumbent must clear the swap's own friction",
                   "whether it must additionally clear one standard error"],
        "promotionEligible": False,
        "liveValidated": False,
        "productionChanged": False,
    }


def run_rung(rung: str, *, contexts: dict, calibrator, calendar: list[dict],
             cfg_pf: dict, valuation) -> dict:
    """Value one rung on the fixed blocks, carrying incumbency across them."""
    if rung not in LADDER:
        raise ValueError(f"unknown rung: {rung}")
    se_multiple = SE_MULTIPLE if rung == COST_PLUS_SE else 0.0
    apply_cost = rung != CONTROL
    research_cfg = BA.cost_config(cfg_pf)
    rows, decisions, failures = [], [], []
    terminal_weights: dict[str, float] = {}
    terminal_regions: dict[str, str] = {}

    for block in calendar:
        signal_date = block["signalDate"]
        calibrator.advance(signal_date)
        candidates, macro = contexts.get(signal_date) or ([], {})
        incumbents = set(terminal_weights)
        scored = hurdle_scores(candidates, calibrator, research_cfg,
                               as_of=block["date"], incumbents=incumbents,
                               se_multiple=se_multiple, apply_cost=apply_cost)
        allocation = KP.selection_and_baseline(
            candidates, research_cfg, macro, scored=scored, method=rung)
        weights = allocation["weights"]
        selected = {c["ticker"]: c for c in allocation["selected"]}
        held = set(weights)
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
            "replaced": sorted(incumbents - held),
            "added": sorted(held - incumbents),
            "retainedByRegion": _count_by_region(held & incumbents, scored),
            "replacedByRegion": _count_by_region(incumbents - held, scored),
            "valuationStatus": diagnostic["status"],
        })
        if outcome is None:
            failures.append({**block, **diagnostic})
            continue
        rows.append(outcome)
        terminal_weights = dict(outcome.get("terminalWeights") or {})
        terminal_regions = dict(outcome.get("terminalRegionByTicker") or {})
    expected = [b for b in calendar if b["endDate"] <= valuation.through]
    return {"rung": rung, "rows": rows, "decisions": decisions, "failures": failures,
            "complete": len(rows) == len(expected),
            "expectedBlocks": len(expected), "measuredBlocks": len(rows),
            "seMultiple": se_multiple, "appliedCost": apply_cost,
            "terminalRegions": terminal_regions}


def _count_by_region(tickers, scored: list[dict]) -> dict[str, int]:
    region_of = {row["ticker"]: row["region"] for row in scored}
    out: dict[str, int] = {}
    for ticker in tickers:
        region = region_of.get(ticker, "UNKNOWN")
        out[region] = out.get(region, 0) + 1
    return out


def summarize(rows: list[dict], cfg_pf: dict) -> dict:
    """Path metrics plus the edge and turnover splits, on realistic costs."""
    from . import selection_value as SV
    return SV.summarize(rows, cfg_pf)


def regional_attribution(rows: list[dict], *, years: float) -> dict:
    """Split the book's gross excess into what each region's sleeve contributed.

    `excessByRegion` sums to `grossExcessReturn` by construction, so the two
    contributions reconstruct the headline rather than approximating it. The
    sleeve figure divides by the weight actually held, which answers "how good
    was the picking there" independently of how much was allocated to it — the
    champion's loss is mostly that it held 51.9% of the book in the sleeve with
    the weaker record and 25.6% in the stronger one.

    Both are point estimates. On 155 blocks split two ways the bootstrap
    intervals around them span zero, so they diagnose where to look and do not
    establish that one region's ranking works and the other's does not.
    """
    import numpy as np
    ordered = sorted(rows, key=lambda row: row["date"])
    if not ordered or years <= 0:
        return {"available": False, "reason": "no_blocks"}
    per_year = len(ordered) / years
    out: dict[str, dict] = {}
    for region in sorted({r for row in ordered
                          for r in (row.get("weightByRegion") or {})}):
        weight = np.array([(row.get("weightByRegion") or {}).get(region, 0.0)
                           for row in ordered], dtype=float)
        excess = np.array([(row.get("excessByRegion") or {}).get(region, 0.0)
                           for row in ordered], dtype=float)
        held = weight > 1e-9
        sleeve = excess[held] / weight[held] if held.any() else np.array([])
        contribution_ci = PV._bootstrap_ci(excess, draws=4000, seed=11)
        sleeve_ci = (PV._bootstrap_ci(sleeve, draws=4000, seed=11)
                     if sleeve.size >= 2 else [None, None])
        out[region] = {
            "blocksHeld": int(held.sum()), "blocks": len(ordered),
            "averageWeightPct": round(float(weight.mean()) * 100, 3),
            "contributionPpPerYear": round(float(excess.mean()) * per_year * 100, 4),
            "contributionCi95Pp": [None if v is None else round(v * per_year, 4)
                                   for v in contribution_ci],
            "sleeveExcessPpPerYear": (round(float(sleeve.mean()) * (held.sum() / years) * 100, 4)
                                      if sleeve.size else None),
            "sleeveExcessCi95Pp": [None if v is None else round(v * (held.sum() / years), 4)
                                   for v in sleeve_ci],
            "sleeveWinRatePct": (round(float((sleeve > 0).mean()) * 100, 2)
                                 if sleeve.size else None),
        }
    return {"available": True, "byRegion": out,
            "note": ("`excessByRegion` sums to `grossExcessReturn`, so the contributions "
                     "reconstruct the headline. Sleeve figures are weight-normalised and "
                     "their intervals are wide; they locate the question, not the answer.")}


def turnover_by_region(decisions: list[dict]) -> dict:
    """How many names each region retained against replaced, per rebalance.

    The hurdle is regional because the cost is, so whether it actually bit
    harder in the expensive market is checked here rather than assumed.
    """
    retained: dict[str, int] = {}
    replaced: dict[str, int] = {}
    for decision in decisions:
        for region, count in (decision.get("retainedByRegion") or {}).items():
            retained[region] = retained.get(region, 0) + count
        for region, count in (decision.get("replacedByRegion") or {}).items():
            replaced[region] = replaced.get(region, 0) + count
    out = {}
    for region in sorted(set(retained) | set(replaced)):
        kept, gone = retained.get(region, 0), replaced.get(region, 0)
        total = kept + gone
        out[region] = {"retained": kept, "replaced": gone,
                       "retentionRatePct": round(kept / total * 100, 2) if total else None}
    return out


def published_challenger_rows(sealed: dict) -> list[dict]:
    """The comparison path: the same ranking with no hurdle at all."""
    return deepcopy(sealed["portfolioReplay"]["headlineRows"][PV.CHALLENGER])


def block_quarter(date: str) -> tuple[int, int]:
    stamp = pd.Timestamp(date)
    return stamp.year, stamp.quarter
