"""What each layer of the construction is actually worth, measured separately.

WHY THIS EXISTS
---------------
`benchmark-relative-alpha-v1` established BENCHMARK_NOT_BEATEN and named a next
direction — keep the calibrated signal, add a replacement hurdle — on the
reading that the calibrated challenger has a real +0.340pp/yr gross edge worth
protecting from turnover. Two measurements on the same sealed ledger showed that
number is not what it looks like:

* That +0.340pp/yr is a GEOMETRIC gap, and it decomposes (`decompose_edge`)
  into +0.040pp of arithmetic stock selection and +0.300pp of compounding: the
  book carries 0.83x the matched benchmark's block volatility, so it loses less
  to variance drag. 88% of the only positive number in the report is a
  low-volatility tilt rather than picking, and a CAGR comparison cannot show it.
* 93% of turnover is names being REPLACED, not weights being retargeted (4.7
  names held, 39.8% surviving to the next block), so the ~1.4pp/yr bill is paid
  for the ranking's opinion about WHICH names and not for rebalancing drift.

The hypothesis that followed — the ranking is not worth its bill, so hold what
the screen approved and stop paying to choose within it — is what this ladder
was built to test. IT WAS REFUTED, and by its own test: on replay-v16 holding
the pool broadly lands at -2.729pp/yr net excess against the concentrated
book's -1.046pp, and the arithmetic selection edge RISES monotonically with how
much of the ranking is used (-1.771pp with none, -1.501pp as a weight tilt,
+0.040pp as concentration). The module is kept, and this paragraph with it,
because the ladder that refutes a hypothesis is the same instrument that would
have confirmed it — and because the decompositions above are measurements of
the published book that stand whatever the ladder says.

WHAT THE LADDER LEFT OPEN, and `selection_null` then answered: the published
null permutes the CHAMPION's conviction score, whose arithmetic selection edge
is -1.589pp/yr, so its INDISTINGUISHABLE_FROM_RANDOM verdict was never evidence
about the challenger. Run for the challenger it lands at the 87th/84th/94th
percentile of its own null (annualized excess p=0.134, information ratio
p=0.164, Sharpe p=0.065) against the champion's 61st/54th/91.5th — a
substantially stronger ranking that still does not clear the pre-registered 5%
bar on any statistic. Note also that beating the null and beating the benchmark
are different bars: choosing is worth about +2.9pp/yr against a permuted
ranking, and the book still trails its matched benchmark.

THE LADDER
----------
Three rungs against one matched benchmark, on the same fixed blocks, the same
PIT research pool, the same production selection and weighting functions, the
same realistic costs. Each rung uses the calibrated challenger ranking for one
more thing than the rung below it:

  SCREEN_ONLY         hold every eligible pool name, inverse-downside-volatility
                      weighted, conviction tilt switched OFF. The ranking is not
                      consulted at all. Turnover is whatever the screen's own
                      membership hysteresis produces.
  SCREEN_PLUS_TILT    the same held set, with the production conviction tilt
                      (0.5x-1.5x by rank) switched on. The ranking now sizes
                      positions but never excludes a name.
  SCREEN_PLUS_CONCENTRATION
                      the published concentrated book: the ranking now also
                      decides which ~5 of the ~24 names are held at all.

The rungs differ in ONE use of the ranking each, so the difference between two
adjacent rungs is what that use was worth. Cadence, retargeting, caps, cash
floor, entry-state exclusions and costs are identical across all three — a rung
that also changed the rebalance schedule would confound the ranking's value
with the holding period, which is the confound that made v1's three-changes-at-
once result unreadable.

WHAT THIS IS NOT. It is not a parameter search and no rung is a tuned variant:
each is a fixed point on "how much of the ranking do you use", specified before
the result was seen, and `TILT_OFF` is the ABSENCE of the tilt rather than a
fitted value for it. Nothing here promotes a selector, and a rung winning is not
a promotion trigger — `portfolio_validation.comparison_verdict` and the
promotion gate still own that decision.
"""
from __future__ import annotations

from copy import deepcopy

import numpy as np

from . import benchmark_alpha as BA
from . import kelly_portfolio as KP
from . import portfolio_validation as PV

VERSION = "selection-value-decomposition-v1"

SCREEN_ONLY = "SCREEN_ONLY_RISK_WEIGHTED_NO_RANKING"
SCREEN_PLUS_TILT = "SCREEN_PLUS_CONVICTION_TILT_NO_CONCENTRATION"
SCREEN_PLUS_CONCENTRATION = "SCREEN_PLUS_CONCENTRATION_PUBLISHED_BOOK"

# The conviction tilt is a multiplicative rank adjustment of 1 +/- range/2, so a
# range of exactly zero is the tilt not being applied — the neutral point of the
# production formula, not a value chosen because it scored well.
TILT_OFF = 0.0

LADDER = (SCREEN_ONLY, SCREEN_PLUS_TILT)


def broad_config(cfg_pf: dict, *, pool_size: int, tilt_range: float) -> dict:
    """Production portfolio config with the NAME-COUNT caps opened to the pool.

    Only the counts move. `maxPositionWeight`, `maxSectorWeight`,
    `maxThemeWeight` and `minCashPct` are untouched, so sector and single-name
    RISK stays bounded exactly as production bounds it — what changes is that a
    name is no longer dropped for being the third in its region or the sixth
    overall. Costs come from `benchmark_alpha.cost_config`, so every rung is
    priced on the same realistic schedule the published table uses.
    """
    out = BA.cost_config(cfg_pf)
    selection = dict(out.get("selection") or {})
    selection.update({
        "targetNames": int(pool_size),
        "maxNamesPerSector": int(pool_size),
        "maxNamesPerRegion": int(pool_size),
        "convictionTiltRange": float(tilt_range),
    })
    out["selection"] = selection
    out["maxNames"] = int(pool_size)
    return out


def eligibility_rows(candidates: list[dict], cfg_pf: dict,
                     scored: list[dict] | None = None) -> list[dict]:
    """One row per candidate carrying eligibility FACTS and an optional ranking.

    Eligibility here is only what is true about the name regardless of any
    ordering — the entry state and research-view multiplier, and whether a
    downside-volatility unit exists to weight it by. This is the same split
    `selection_null` draws: the alpha floor is a score decision and is excluded
    from the null, every other exclusion is a fact and is kept. `SCREEN_ONLY`
    therefore holds what the screen approved, not what the screen approved and
    the ranking then liked.

    With `scored` absent every score is 0.0, so `_select_scored` falls through
    to its alphabetical tie-break and `baseline_weights` gives every name the
    same neutral tilt. With `scored` present the challenger's own score is
    carried through for the tilt.
    """
    by_ticker = {row["ticker"]: row for row in (scored or [])}
    rows = []
    for candidate in candidates:
        risk = KP._risk_unit(candidate)
        state = KP._state_multiplier(candidate, cfg_pf)
        excluded = []
        if risk is None or risk <= 0:
            excluded.append("DOWNSIDE_RISK_UNAVAILABLE")
        if state <= 0:
            excluded.append("ENTRY_OR_RESEARCH_STATE_BLOCKS_SIZING")
        ranked = by_ticker.get(candidate["ticker"]) or {}
        score = float(ranked.get("score") or 0.0) if ranked else 0.0
        rows.append({
            "ticker": candidate["ticker"],
            "region": candidate.get("region") or "UNKNOWN",
            "sector": candidate.get("sector") or "Unclassified",
            "score": score, "convictionScore": score,
            "alphaPercentile": candidate.get("alphaPercentile"),
            "downsideVolPct": risk * 100 if risk else None,
            "evidenceCoverage": candidate.get("evidenceCoverage"),
            "eligible": not excluded, "exclusionCodes": excluded,
        })
    return rows


def decompose_edge(rows: list[dict], *, years: float) -> dict:
    """Split a path's GEOMETRIC gross gap into stock selection and compounding.

    A CAGR difference answers "which ended richer" and hides which of two very
    different things produced it. The arithmetic mean difference is what stock
    selection earned per block. The rest is compounding: a book whose block
    returns are less dispersed than its benchmark's keeps more of its own
    arithmetic mean, and that shows up in a CAGR comparison as though it were
    selection. On the published calibrated challenger the split is +0.040pp of
    selection and +0.301pp of compounding, so reporting only the +0.340pp total
    credits a low-volatility tilt to stock picking.

    Both terms are computed before transaction costs, because costs are already
    reported separately and mixing them in would make the selection term depend
    on the turnover policy.
    """
    book = np.asarray([row["grossReturn"] for row in rows], dtype=float)
    bench = np.asarray([row["benchmarkReturn"] for row in rows], dtype=float)
    if not len(book) or years <= 0:
        return {"available": False, "reason": "no_blocks"}
    per_year = len(book) / years

    def annualized(values):
        growth = float(np.prod(1.0 + values))
        return (float(values.mean()) * per_year,
                (growth ** (1.0 / years) - 1.0) if growth > 0 else None,
                float(values.std(ddof=1)) if len(values) > 1 else None)

    book_arith, book_geo, book_sd = annualized(book)
    bench_arith, bench_geo, bench_sd = annualized(bench)
    if book_geo is None or bench_geo is None:
        return {"available": False, "reason": "non_positive_growth"}
    selection = (book_arith - bench_arith) * 100
    compounding = (((book_geo - bench_geo) - (book_arith - bench_arith))) * 100
    return {
        "available": True, "blocks": len(book),
        "arithmeticSelectionEdgePp": round(selection, 4),
        "compoundingEdgePp": round(compounding, 4),
        "geometricGrossEdgePp": round(selection + compounding, 4),
        # A standard deviation of exactly 0.0 is a MEASURED constant series, not
        # a missing measurement, and `if sd` reads the two as the same thing. The
        # ratio is the only one of the three that genuinely cannot be formed,
        # and only because the denominator is zero.
        "bookBlockSdPct": round(book_sd * 100, 4) if book_sd is not None else None,
        "benchmarkBlockSdPct": round(bench_sd * 100, 4) if bench_sd is not None else None,
        "blockSdRatio": (round(book_sd / bench_sd, 4)
                         if book_sd is not None and bench_sd else None),
        "note": ("GEOMETRIC = ARITHMETIC + COMPOUNDING. A book less volatile than its "
                 "matched benchmark earns a positive compounding term without picking "
                 "a single better name."),
    }


def decompose_turnover(rows: list[dict]) -> dict:
    """Split one-way turnover into names replaced and weights retargeted.

    The two have completely different remedies. Weight retargeting is
    discretionary — carrying the drifted book costs nothing — so if it were the
    bulk of the bill, a no-retarget band would remove it at almost no change in
    what is held. Name replacement is the ranking acting on its opinion, and
    removing it means holding different names. Measured on the published books
    it is 92-93% the second, which is why v1's quarterly freeze had to change
    what was held in order to save anything.
    """
    ordered = sorted(rows, key=lambda row: row["date"])
    prior: dict[str, float] = {}
    name_l1 = weight_l1 = 0.0
    rebalances = 0
    carried = []
    for row in ordered:
        weights = row["weights"]
        if prior:
            common = set(weights) & set(prior)
            name_l1 += (sum(weights[t] for t in set(weights) - set(prior))
                        + sum(prior[t] for t in set(prior) - set(weights)))
            weight_l1 += sum(abs(weights[t] - prior[t]) for t in common)
            carried.append(len(common) / len(prior))
            rebalances += 1
        prior = dict(row.get("terminalWeights") or weights)
    if not rebalances:
        return {"available": False, "reason": "single_block"}
    name_rate = 0.5 * name_l1 / rebalances
    weight_rate = 0.5 * weight_l1 / rebalances
    total = name_rate + weight_rate
    return {
        "available": True, "rebalances": rebalances,
        "averageOneWayTurnoverPct": round(total * 100, 4),
        "fromNameReplacementPct": round(name_rate * 100, 4),
        "fromWeightRetargetPct": round(weight_rate * 100, 4),
        "nameReplacementSharePct": round(name_rate / total * 100, 2) if total else None,
        "namesCarriedToNextBlockPct": round(float(np.mean(carried)) * 100, 2),
        "averageNamesHeld": round(float(np.mean([len(r["weights"]) for r in ordered])), 2),
    }


def run_rung(rung: str, *, contexts: dict, calibrator, calendar: list[dict],
             cfg_pf: dict, valuation) -> dict:
    """Value one rung of the ladder on the fixed blocks.

    Every rung retargets on every block exactly as the published selectors do.
    Holding period is deliberately NOT a ladder axis: v1 moved cadence, the cash
    gate and the weighting rule together and its gross loss could not be
    attributed to any of them.
    """
    if rung not in LADDER:
        raise ValueError(f"unknown rung: {rung}")
    tilt = TILT_OFF if rung == SCREEN_ONLY else float(
        (cfg_pf.get("selection") or {}).get("convictionTiltRange", 1.0))
    rows, decisions, failures = [], [], []
    for block in calendar:
        signal_date = block["signalDate"]
        calibrator.advance(signal_date)
        candidates, macro = contexts.get(signal_date) or ([], {})
        ranked = (PV._challenger_scores(candidates, calibrator, cfg_pf)
                  if rung == SCREEN_PLUS_TILT else None)
        local = broad_config(cfg_pf, pool_size=max(len(candidates), 1), tilt_range=tilt)
        scored = eligibility_rows(candidates, local, ranked)
        allocation = KP.selection_and_baseline(
            candidates, local, macro, scored=scored, method=rung)
        weights = allocation["weights"]
        selected = {c["ticker"]: c for c in allocation["selected"]}
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
            "poolSize": len(candidates), "heldNames": len(weights),
            "eligibleCount": sum(1 for row in scored if row["eligible"]),
            "valuationStatus": diagnostic["status"],
        })
        if outcome is None:
            failures.append({**block, **diagnostic})
            continue
        rows.append(outcome)
    expected = [b for b in calendar if b["endDate"] <= valuation.through]
    return {"rung": rung, "rows": rows, "decisions": decisions,
            "failures": failures, "complete": len(rows) == len(expected),
            "expectedBlocks": len(expected), "measuredBlocks": len(rows),
            "convictionTiltRange": tilt}


def contexts_from_signals(signals: list[dict], cfg_lt: dict) -> dict:
    """The same PIT research pool the published replay walks, in date order."""
    return BA._contexts(signals, cfg_lt)


def summarize(rows: list[dict], cfg_pf: dict) -> dict:
    """Path metrics, the edge split and the turnover split for one rung."""
    copied = deepcopy(rows)
    metrics = PV._path_metrics(copied, PV.HEADLINE_HORIZON, cfg_pf,
                               only_dates=[row["date"] for row in copied])
    years = metrics.get("calendarYears") or 0
    gross = deepcopy(copied)
    growth = float(np.prod([1 + row["grossReturn"] for row in gross]))
    metrics["grossCagrPct"] = ((growth ** (1 / years) - 1) * 100
                               if years and growth > 0 else None)
    metrics["costDragCagrPp"] = (metrics["grossCagrPct"] - metrics["cagrPct"]
                                 if metrics.get("grossCagrPct") is not None
                                 and metrics.get("cagrPct") is not None else None)
    metrics["grossBenchmarkGapPp"] = (
        metrics["grossCagrPct"] - metrics["benchmarkCagrPct"]
        if metrics.get("grossCagrPct") is not None
        and metrics.get("benchmarkCagrPct") is not None else None)
    metrics["averageCashPct"] = float(np.mean([
        1 - sum(float(w) for w in row["weights"].values()) for row in copied])) * 100
    metrics["annualOneWayTurnoverX"] = (
        (metrics.get("averageTurnoverPct") or 0) / 100
        * (metrics.get("turnoverRebalances") or 0) / years if years else None)
    metrics["sumTransactionCostPct"] = sum(r["transactionCost"] for r in copied) * 100
    metrics["edgeDecomposition"] = decompose_edge(copied, years=years)
    metrics["turnoverDecomposition"] = decompose_turnover(copied)
    return metrics


def freeze_manifest(pool_sizes: list[int] | None = None) -> dict:
    return {
        "id": VERSION,
        "status": "DIAGNOSTIC",
        "ladder": list(LADDER) + [SCREEN_PLUS_CONCENTRATION],
        "rankingSource": "CALIBRATED_EXPECTED_RETURN_PER_DOWNSIDE_RISK",
        "heldFixedAcrossRungs": [
            "fixed 21-session evaluation blocks",
            "PIT research candidate pool and its own membership hysteresis",
            "retarget on every block",
            "entry-state and research-view exclusions",
            "maxPositionWeight / maxSectorWeight / maxThemeWeight",
            "regime cash floor and minCashPct",
            "realistic transaction cost schedule",
        ],
        "variedAcrossRungs": [
            "whether the ranking sizes positions (conviction tilt)",
            "whether the ranking excludes names (concentration)",
        ],
        "tiltOff": TILT_OFF,
        "poolSizeObserved": sorted(set(pool_sizes or [])) or None,
        "promotionEligible": False,
        "liveValidated": False,
        "productionChanged": False,
        "note": ("A ladder of ablations on sealed inputs. Each rung is a fixed point on "
                 "how much of the ranking is used, specified before the result was seen. "
                 "No rung is a tuned variant and no rung may promote a selector."),
    }
