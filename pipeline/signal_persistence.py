"""Is last month's ranking noisier than the position it displaces?

WHERE THIS CAME FROM
--------------------
`regional-switch-hurdle-v1` was built to save the fees a swap costs and it did
save them — 0.270pp of cost drag. But against its own control it also gained
2.157pp of ARITHMETIC STOCK SELECTION, eight times more, and nothing in the cost
argument predicts that. Holding a name longer cannot make the name better; what
it can do is stop the book acting on a ranking that was wrong to move.

So the finding that rule actually produced is about the SIGNAL, not about costs:
chasing each block's top-ranked name was destroying gross return. This module
tests that directly instead of collecting it as a side effect.

TWO MEASUREMENTS, AND THEY ANSWER DIFFERENT THINGS
--------------------------------------------------
THE DIAGNOSTIC is parameter-free and asks the hypothesis in its own words. At
every rebalance the book's names divide into those it just ADDED and those it
RETAINED from the previous block. Both were chosen by the same ranking on the
same date; the only difference is whether the ranking had already been holding
them. If a fresh pick realises less forward benchmark excess than a standing
one, the ranking's newest opinions are its worst ones — which is the claim.

Nothing is fitted here and no rule changes: it reads the control path's own
decisions against the realised cross-section the book was priced on.

THE LADDER asks whether fixing the signal does what the hurdle did indirectly.
It ranks on a name's alpha percentile averaged over its last `k` appearances in
the research pool rather than on the latest one, and nothing else moves — no
hurdle, same cadence, same caps, same cash floor, same costs. One axis:

    LATEST (k=1)    the control. What production ranks on today.
    SMOOTHED_3      the midpoint.
    SMOOTHED_6      horizon-matched: the calibrated alpha forecasts 126
                    sessions, which is exactly six 21-session blocks, so this
                    averages the signal over the span it is predicting.

`k = 6` is chosen from the forecast horizon and `k = 3` is the midpoint between
it and the control. Neither is swept and neither was picked from a result.

SMOOTHING LOOKS BACKWARD ONLY. A name's window is its own last `k` observations
in the pool, including the current one and nothing after it. A name that left
the pool and returned resumes from its earlier history rather than restarting,
because the question is how noisy the ranking is about a given company, not how
recently the screen happened to surface it. Early blocks average over fewer
than `k` observations; they never reach forward for a missing one.

WHAT THIS IS NOT. Not a promotion, not a production change, and not a claim that
any rung beats the benchmark going forward. The combination of smoothing and the
switch hurdle is a TWO-axis change and is reported separately from the ladder,
because a number produced by moving two things at once cannot be attributed to
either.
"""
from __future__ import annotations

from collections import defaultdict, deque

import numpy as np

from . import benchmark_alpha as BA
from . import kelly_portfolio as KP
from . import portfolio_validation as PV
from . import switch_hurdle as SH

VERSION = "signal-persistence-v1"

LATEST = "RANK_ON_LATEST_ALPHA_PERCENTILE"
SMOOTHED_3 = "RANK_ON_MEAN_ALPHA_PERCENTILE_OVER_3_BLOCKS"
SMOOTHED_6 = "RANK_ON_MEAN_ALPHA_PERCENTILE_OVER_6_BLOCKS"
LADDER = (LATEST, SMOOTHED_3, SMOOTHED_6)

# The calibrated alpha forecasts `horizonDays` sessions and a block is 21, so
# six blocks is the forecast's own span. Not swept.
HORIZON_BLOCKS = 6
WINDOW = {LATEST: 1, SMOOTHED_3: 3, SMOOTHED_6: HORIZON_BLOCKS}

# Reported beside the ladder, never inside it: it moves two axes at once.
COMBINED = "SMOOTHED_6_PLUS_COST_HURDLE"


class PercentileSmoother:
    """A name's own last `k` alpha percentiles, in pool order, never forward.

    Keyed by ticker rather than by slot, so a name that leaves the pool and
    comes back continues its own history. The window advances only when the
    caller presents a block, so replaying the same block twice cannot
    double-count it.
    """

    def __init__(self, window: int):
        if window < 1:
            raise ValueError("window must be at least one block")
        self.window = int(window)
        self.history: dict[str, deque] = defaultdict(lambda: deque(maxlen=self.window))
        self.seen: set[tuple[str, str]] = set()

    def observe(self, ticker: str, percentile, date: str) -> None:
        value = PV._finite(percentile)
        key = (ticker, date)
        if value is None or key in self.seen:
            return
        self.seen.add(key)
        self.history[ticker].append(value)

    def smoothed(self, ticker: str, percentile):
        """The mean of what has been observed, or the raw value when nothing has.

        A name appearing for the first time has only its current percentile, so
        `k = 1` and every rung agree on it. That is the honest degradation: the
        smoother never invents history it does not have.
        """
        values = self.history.get(ticker)
        if not values:
            return percentile
        return float(np.mean(values))

    def depth(self, ticker: str) -> int:
        return len(self.history.get(ticker) or ())

    def dispersion(self, ticker: str):
        """Sample sd of what the window holds, or `None` below two observations.

        The same backward-only window the mean is taken over, so a consumer that
        needs to know how noisy a name's own signal has been reads it from here
        rather than rebuilding a second history beside this one. One observation
        has no dispersion to report, and reporting 0.0 for it would read as the
        most stable name in the cross-section.
        """
        values = self.history.get(ticker)
        if not values or len(values) < 2:
            return None
        return float(np.std(list(values), ddof=1))


def smoothed_candidates(candidates: list[dict], smoother: PercentileSmoother,
                        date: str) -> list[dict]:
    """Copies carrying the smoothed percentile, for scoring AND selection.

    Both have to see the same number. Scoring on a smoothed percentile while
    selecting on the raw one would rank names by one quantity and cap them by
    another, and the difference would be invisible in the output.
    """
    for candidate in candidates:
        smoother.observe(candidate["ticker"], candidate.get("alphaPercentile"), date)
    out = []
    for candidate in candidates:
        copied = dict(candidate)
        copied["rawAlphaPercentile"] = candidate.get("alphaPercentile")
        copied["alphaPercentile"] = smoother.smoothed(
            candidate["ticker"], candidate.get("alphaPercentile"))
        copied["smoothingDepth"] = smoother.depth(candidate["ticker"])
        out.append(copied)
    return out


def incumbency_outcomes(decisions: list[dict], priced_by_date: dict) -> dict:
    """Realised forward excess of the names a rebalance ADDED against those it KEPT.

    Both groups were selected by the same ranking on the same date under the
    same constraints. The only thing separating them is whether the book was
    already holding them, so a gap between their realised outcomes is a
    statement about the ranking's newest opinions and not about the market,
    the sector mix or the cost model.

    The first block has no prior book and contributes nothing: every name in it
    is an arrival by construction, and counting them would load the ADDED side
    with an initial build nobody chose to churn into.
    """
    added_rows, retained_rows = [], []
    paired = []
    by_region: dict[str, dict[str, list]] = defaultdict(lambda: {"added": [], "retained": []})
    for decision in sorted(decisions, key=lambda d: d["date"]):
        added = list(decision.get("added") or [])
        retained = list(decision.get("retained") or [])
        if not retained and not added:
            continue
        priced = priced_by_date.get(decision["date"]) or {}
        region_of = decision.get("regionByTicker") or {}

        def excess(tickers):
            out = []
            for ticker in tickers:
                cell = priced.get(ticker)
                if cell is not None and cell.get("excessReturn") is not None:
                    out.append((ticker, float(cell["excessReturn"])))
            return out

        added_pairs, retained_pairs = excess(added), excess(retained)
        for ticker, value in added_pairs:
            added_rows.append(value)
            by_region[region_of.get(ticker, "UNKNOWN")]["added"].append(value)
        for ticker, value in retained_pairs:
            retained_rows.append(value)
            by_region[region_of.get(ticker, "UNKNOWN")]["retained"].append(value)
        # Paired only where the same rebalance produced both sides, so the
        # difference is within one date and carries no market-timing term.
        if added_pairs and retained_pairs:
            paired.append(float(np.mean([v for _, v in added_pairs]))
                          - float(np.mean([v for _, v in retained_pairs])))
    return {
        "available": bool(paired),
        "addedObservations": len(added_rows),
        "retainedObservations": len(retained_rows),
        "pairedRebalances": len(paired),
        "addedMeanExcessPct": _mean_pct(added_rows),
        "retainedMeanExcessPct": _mean_pct(retained_rows),
        "addedMinusRetainedPct": _mean_pct(paired),
        "addedMinusRetainedCi95Pct": (PV._bootstrap_ci(np.asarray(paired, dtype=float),
                                                       draws=4000, seed=11)
                                      if len(paired) >= 2 else [None, None]),
        "byRegion": {region: {
            "addedObservations": len(blob["added"]),
            "retainedObservations": len(blob["retained"]),
            "addedMeanExcessPct": _mean_pct(blob["added"]),
            "retainedMeanExcessPct": _mean_pct(blob["retained"]),
            "differencePct": (_mean_pct(blob["added"]) - _mean_pct(blob["retained"])
                              if blob["added"] and blob["retained"] else None),
        } for region, blob in sorted(by_region.items())},
        "note": ("Per-block realised 21-session benchmark excess. The paired figure is "
                 "the within-rebalance difference, so it carries no market-timing term. "
                 "Unpaired group means are reported for context and are not the test."),
    }


def _mean_pct(values) -> float | None:
    return round(float(np.mean(values)) * 100, 4) if len(values) else None


def run_rung(rung: str, *, contexts: dict, calibrator, calendar: list[dict],
             cfg_pf: dict, valuation, hurdle: bool = False) -> dict:
    """Value one rung, carrying incumbency and the smoothing window across blocks."""
    if rung not in WINDOW and rung != COMBINED:
        raise ValueError(f"unknown rung: {rung}")
    window = WINDOW.get(rung, HORIZON_BLOCKS)
    smoother = PercentileSmoother(window)
    research_cfg = BA.cost_config(cfg_pf)
    rows, decisions, failures = [], [], []
    terminal_weights: dict[str, float] = {}

    for block in calendar:
        signal_date = block["signalDate"]
        calibrator.advance(signal_date)
        raw_candidates, macro = contexts.get(signal_date) or ([], {})
        candidates = smoothed_candidates(raw_candidates, smoother, block["date"])
        incumbents = set(terminal_weights)
        scored = SH.hurdle_scores(candidates, calibrator, research_cfg,
                                  as_of=block["date"], incumbents=incumbents,
                                  se_multiple=0.0, apply_cost=bool(hurdle))
        allocation = KP.selection_and_baseline(
            candidates, research_cfg, macro, scored=scored, method=rung)
        weights = allocation["weights"]
        selected = {c["ticker"]: c for c in allocation["selected"]}
        held = set(weights)
        region_by_ticker = {t: selected[t].get("region") for t in weights}
        decision = {
            "date": block["date"], "replayDate": signal_date, "selector": rung,
            "weights": weights, "regionByTicker": region_by_ticker,
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
            "regionByTicker": dict(region_by_ticker),
            "meanSmoothingDepth": round(float(np.mean(
                [c["smoothingDepth"] for c in candidates])), 3) if candidates else None,
            "valuationStatus": diagnostic["status"],
        })
        if outcome is None:
            failures.append({**block, **diagnostic})
            continue
        rows.append(outcome)
        terminal_weights = dict(outcome.get("terminalWeights") or {})
    expected = [b for b in calendar if b["endDate"] <= valuation.through]
    return {"rung": rung, "rows": rows, "decisions": decisions, "failures": failures,
            "complete": len(rows) == len(expected), "window": window,
            "hurdleApplied": bool(hurdle),
            "expectedBlocks": len(expected), "measuredBlocks": len(rows)}


def percentile_movement(contexts: dict, calendar: list[dict]) -> dict:
    """How far a name's alpha percentile travels between consecutive blocks.

    Context for the ladder rather than a test of it: a signal that barely moves
    cannot be smoothed into something different, so this says whether the axis
    the ladder varies has any room to vary in.
    """
    previous: dict[str, float] = {}
    moves: list[float] = []
    for block in sorted(calendar, key=lambda b: b["date"]):
        candidates, _ = contexts.get(block["signalDate"]) or ([], {})
        for candidate in candidates:
            value = PV._finite(candidate.get("alphaPercentile"))
            if value is None:
                continue
            ticker = candidate["ticker"]
            if ticker in previous:
                moves.append(abs(value - previous[ticker]))
            previous[ticker] = value
    if not moves:
        return {"available": False}
    arr = np.asarray(moves, dtype=float)
    return {"available": True, "observations": int(arr.size),
            "meanAbsoluteMove": round(float(arr.mean()), 3),
            "medianAbsoluteMove": round(float(np.median(arr)), 3),
            "p90AbsoluteMove": round(float(np.percentile(arr, 90)), 3),
            "note": ("Percentile points moved by one name between consecutive blocks it "
                     "appeared in. A ranking that is stable leaves smoothing nothing to do.")}


def freeze_manifest() -> dict:
    return {
        "id": VERSION,
        "status": "CHALLENGER",
        "ladder": list(LADDER),
        "reportedSeparately": COMBINED,
        "axis": "HOW_MANY_BLOCKS_OF_ALPHA_PERCENTILE_THE_RANKING_AVERAGES",
        "windows": dict(WINDOW),
        "windowJustification": (
            "k=6 is the forecast horizon in blocks (126 sessions / 21); k=3 is the "
            "midpoint to the control. Neither is swept and neither was picked from a "
            "result."),
        "smoothingDirection": "BACKWARD_ONLY_OWN_POOL_APPEARANCES",
        "hurdleApplied": False,
        "heldFixedAcrossRungs": [
            "fixed 21-session evaluation blocks and their cadence",
            "PIT research candidate pool",
            "calibrated expected-benchmark-excess ranking function",
            "entry-state and research-view exclusions",
            "name/sector/region caps, maxPositionWeight, cash floor",
            "conviction-tilted inverse-downside-volatility weights",
            "realistic dated transaction cost schedule",
            "no switch hurdle",
        ],
        "promotionEligible": False,
        "liveValidated": False,
        "productionChanged": False,
    }
