"""Run the alpha-reliability ladder and its boundary diagnostics, read-only.

Three studies on this ledger point at the conversion from a continuous signal
to a discrete five-name book and none has looked at it directly. This does:
it measures what separates the last name held from the first name excluded,
what separates the two sides of every swap, and whether the arriving name went
on to beat the one it displaced — and then asks whether spending the existing
signal more carefully (persistence, then confidence, then an uncertainty-aware
replacement rule) changes the path.

Nothing here writes inside the sealed ledger, nothing here adds a factor, and
nothing here promotes a selector.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import alpha_reliability as AR                 # noqa: E402
from pipeline import benchmark_alpha as BA                   # noqa: E402
from pipeline import historical_store as HS                  # noqa: E402
from pipeline import portfolio_validation as PV              # noqa: E402
from pipeline import provenance                              # noqa: E402
from pipeline import regional_validation as RVL              # noqa: E402
from pipeline import replay_calendar as RC                   # noqa: E402
from pipeline import replay_inputs as RI                     # noqa: E402
from pipeline import replay_valuation as RV                  # noqa: E402
from pipeline import selection_value as SV                   # noqa: E402
from pipeline import switch_hurdle as SH                     # noqa: E402
from pipeline.config import load_config                      # noqa: E402


def _guard(path: str, ledger: Path) -> Path:
    target = Path(path).resolve()
    if target == ledger.resolve() or ledger.resolve() in target.parents:
        raise ValueError("research output must remain outside the sealed ledger")
    if target.exists():
        raise FileExistsError("refusing to overwrite existing artifact: " + str(target))
    return target


def _digest_tree(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file():
            digest.update(str(path.relative_to(root)).encode())
            with path.open("rb") as stream:
                digest.update(hashlib.file_digest(stream, "sha256").digest())
    return digest.hexdigest()


SUMMARY_KEYS = ("cagrPct", "benchmarkCagrPct", "annualizedExcessPct", "sharpe",
                "sortino", "mddPct", "informationRatio", "averageTurnoverPct",
                "turnoverRebalances", "calendarYears", "annualOneWayTurnoverX",
                "grossCagrPct", "costDragCagrPp", "averageCashPct",
                "grossBenchmarkGapPp", "annualizedRealizedVolPct", "cvar95Pct",
                "annualizedDownsideVolPct", "trackingErrorPct", "hitRatePct",
                "edgeDecomposition", "turnoverDecomposition")


def _fields(row: dict) -> dict:
    return {key: row.get(key) for key in SUMMARY_KEYS if key in row}


def _fmt(value, suffix=""):
    return "n/a" if value is None else f"{value:.3f}{suffix}"


def _pair(blob, key="annualizedExcessPct"):
    delta = blob["pathDifferenceCI"][key]
    lo, hi = delta["ci95"]
    return delta["pointEstimate"], lo, hi


def _separation(blob, key="annualizedExcessPct"):
    """Does this interval exclude zero, and on WHICH side?

    Reading separation as "the lower bound cleared zero" makes an interval that
    excludes zero from BELOW invisible, and an axis that separates in the wrong
    direction is the most informative result a ladder can produce. Both sides
    are the same fact about the same interval and both are reported.
    """
    point, low, high = _pair(blob, key)
    if low is None or high is None:
        return None
    if low > 0:
        return {"direction": "BETTER", "pointEstimatePp": point, "ci95Pp": [low, high]}
    if high < 0:
        return {"direction": "WORSE", "pointEstimatePp": point, "ci95Pp": [low, high]}
    return None


def selection_behaviour(decisions: list[dict]) -> dict:
    """How many names each rebalance kept, added and dropped."""
    retained = [len(d.get("retained") or []) for d in decisions]
    added = [len(d.get("added") or []) for d in decisions]
    replaced = [len(d.get("replaced") or []) for d in decisions]
    held = [d.get("heldNames") or 0 for d in decisions]
    # The initial build has no incumbents; counting it would load the arrival
    # side with names nobody chose to churn into.
    offered = [len(d.get("retained") or []) + len(d.get("replaced") or [])
               for d in decisions]
    incumbent_blocks = [i for i, count in enumerate(offered) if count]
    kept = sum(retained[i] for i in incumbent_blocks)
    lost = sum(replaced[i] for i in incumbent_blocks)
    n = len(decisions) or 1
    return {
        "rebalances": len(decisions),
        "rebalancesWithIncumbents": len(incumbent_blocks),
        "averageNamesHeld": round(sum(held) / n, 3),
        "averageRetained": round(sum(retained) / n, 3),
        "averageAdded": round(sum(added) / n, 3),
        "averageReplaced": round(sum(replaced) / n, 3),
        "incumbentRetentionRatePct": (round(kept / (kept + lost) * 100, 2)
                                      if kept + lost else None),
        "incumbentReplacementRatePct": (round(lost / (kept + lost) * 100, 2)
                                        if kept + lost else None),
    }


NEXT_STUDIES = (
    {
        "order": 1,
        "id": "alpha-risk-separation-v1",
        "question": ("Is downside risk being spent twice — once deciding a name's "
                     "expected alpha and again deciding its capital?"),
        "firstAxis": ("Remove ONLY the downside-volatility denominator from the "
                      "selection ranking. The lowvol sleeve keeps its 0.20 weight "
                      "inside the four-factor alpha, and inverse-downside-volatility "
                      "sizing and every portfolio constraint stay exactly as they are, "
                      "so risk is still managed — it just stops deciding WHICH name."),
        "notInTheFirstLadder": ("Moving the lowvol sleeve out of the alpha layer. If a "
                                "defensive tilt survives the denominator's removal, that "
                                "is the NEXT study's axis, not this one's — two risk "
                                "channels moved together would be attributable to "
                                "neither."),
    },
    {
        "order": 2,
        "id": "dynamic-breadth-v1",
        "question": ("Does a fixed count of five cut an ordering that does not have "
                     "five distinguishable names in it?"),
        "firstAxis": ("Breadth follows signal strength between a floor of 3 and a "
                      "ceiling of 10, with no fixed target: hold the names whose edge "
                      "is distinguishable and hold cash when it is not."),
        "notInTheFirstLadder": ("Choosing whichever of 3/5/7/10 scored best on this "
                                "sample. The hypothesis is that a strength-dependent "
                                "breadth loses less information and churns less at the "
                                "boundary than ANY fixed count, and a fitted count "
                                "would answer a different question."),
    },
    {
        "order": 3,
        "id": "region-quota-removal-v1",
        "question": ("Should regional diversification be a name quota at all, or a "
                     "risk budget?"),
        "firstAxis": ("Replace `maxNamesPerRegion` with a portfolio-level risk / "
                      "covariance / concentration budget, so US 8 / KR 0 or KR 7 / "
                      "US 1 becomes expressible when that is what the ordering says."),
        "prerequisite": ("Alpha percentiles are computed WITHIN a region, so a Korean "
                         "90th and an American 90th are not the same claim. A common "
                         "cross-region scale has to exist before the quota comes off, "
                         "or the quota is simply replaced by an artefact of the "
                         "percentile's construction."),
    },
    {
        "order": 4,
        "id": "entry-selection-separation-v1",
        "question": ("Should the entry state decide WHAT is owned, or only how fast a "
                     "target weight is approached?"),
        "firstAxis": ("Separate the roles: alpha decides the held set, entry state "
                      "decides the path to the target weight — ACCUMULATE to full "
                      "weight, WATCH to part of it, WAIT_FOR_PULLBACK throttles new "
                      "entry, EVENT_RISK holds new entry."),
        "notInTheFirstLadder": ("Whether an INCUMBENT should be sold on a technical "
                                "overheat trigger at all. That is a separate claim "
                                "about exits and gets its own test."),
    },
)


def closing_answers(report: dict, summaries: dict) -> dict:
    """The five interpretation questions, answered from measured rows only."""
    risk_c = report["structuralDiagnostics"]["riskDominance"]["control"]
    risk_h = report["structuralDiagnostics"]["riskDominance"]["hysteresis"]
    entry_c = report["structuralDiagnostics"]["entryStateDynamics"]["control"]
    region_c = report["structuralDiagnostics"]["regionCapBinding"]["control"]
    breadth_c = report["structuralDiagnostics"]["breadthReadiness"]["control"]
    causes_c = report["structuralDiagnostics"]["departureCauses"]["control"]
    boundary_c = report["boundaryInstability"]["control"]

    def mean(blob, key):
        return ((blob.get(key) or {}).get("mean"))

    return {
        "whatExplainsTheFinalOrdering": (
            "BOTH, at different places, and only one of them is where the decision "
            f"happens. Across the whole cross-section the score's rank correlation with "
            f"the calibrated alpha averages "
            f"{_fmt(mean(risk_c, 'scoreVsCalibratedAlphaSpearman'))} against "
            f"{_fmt(mean(risk_c, 'scoreVsDownsideVolSpearman'))} with downside volatility, "
            "so the alpha term orders most PAIRS. But a five-name book is decided at its "
            f"margin, and there {_fmt(boundary_c.get('tiedOnExpectedAlphaPct'), '%')} of "
            "cuts are between two names the calibration scores identically — the alpha "
            "term has two levels and both sides of the cut are almost always on the same "
            "one. What settles those is the risk-and-entry product in the denominator. "
            f"The held set matches an alpha-only top-N only "
            f"{_fmt(risk_c.get('heldMatchingAlphaOnlyTopNPct'), '%')} of the time and "
            f"{_fmt(mean(risk_c, 'pairwiseOrderingInversionsPct'), '%')} of held against "
            "not-held pairs are ordered the other way by the alpha percentile."),
        "doesLowVolatilityDominanceSurviveTheStudy": (
            "The tilt is visible in what is HELD rather than in a large rank correlation, "
            "and it narrows without going away. Names held carry downside volatility of "
            f"{_fmt(mean(risk_c, 'downsideVolPctSelected'), '%')} against "
            f"{_fmt(mean(risk_c, 'downsideVolPctRejected'), '%')} rejected on the control, "
            f"and {_fmt(mean(risk_h, 'downsideVolPctSelected'), '%')} against "
            f"{_fmt(mean(risk_h, 'downsideVolPctRejected'), '%')} on the "
            "confidence-plus-hysteresis rung; the `lowvol` sleeve percentile of held names "
            f"goes {_fmt(mean(risk_c, 'lowvolSleevePercentileSelected'))} to "
            f"{_fmt(mean(risk_h, 'lowvolSleevePercentileSelected'))} against "
            f"{_fmt(mean(risk_h, 'lowvolSleevePercentileRejected'))} for the rejected. "
            f"`lowvol` is among a held name's top two sleeves "
            f"{_fmt(risk_c.get('lowvolIsInTheTopTwoSleevesPct'), '%')} of the time, so part "
            "of the tilt arrives through the ALPHA itself and would survive removing the "
            "denominator — which is why the pre-registered first study moves the "
            "denominator alone and leaves the sleeve for the one after it."),
        "whatDroveTheReplacements": (
            f"Of {causes_c.get('departuresMeasured')} departures on the control path: "
            + ", ".join(f"{cause} {_fmt(share, '%')}"
                        for cause, share in (causes_c.get("bySharePct") or {}).items())
            + ". The diversification guard alone — sector and region caps — accounts for "
            f"{_fmt((causes_c.get('bySharePct') or {}).get('REGION_CAP', 0) + (causes_c.get('bySharePct') or {}).get('SECTOR_CAP', 0), '%')} "
            "of every name this book replaced, and the entry-state step for "
            f"{_fmt((causes_c.get('bySharePct') or {}).get('ENTRY_OR_RESEARCH_STATE_TURNED_BLOCKING', 0), '%')}; "
            f"{entry_c.get('departuresWhereTheStepFellAndAlphaMovedOnePointOrLess')} of "
            "those had the multiplier fall while the name's own percentile moved a point "
            "or less. Where the ranking did outrank a name, its own percentile had moved "
            f"{_fmt(mean(causes_c, 'outrankedOwnPercentileMove'))} points and its reliable "
            f"alpha {_fmt(mean(causes_c, 'outrankedOwnReliableAlphaMovePp'), 'pp')}."),
        "doFixedFiveAndTheRegionQuotaOverrideTheSignal": (
            f"Yes, and the region quota is the larger of the two. It stopped a name on "
            f"{_fmt(region_c.get('regionCapBindingPct'), '%')} of rebalances and on "
            f"{region_c.get('rebalancesWhereACappedNameOutscoredOneTaken')} of "
            f"{region_c.get('rebalancesMeasured')} the capped name outscored one the book "
            f"took, by a median decision-alpha gap of "
            f"{_fmt((region_c.get('decisionAlphaGapAtTheOverridePp') or {}).get('median'), 'pp')}. "
            f"Held name-dates split {region_c.get('heldNameDatesByRegion')}; at the same "
            f"count with the caps lifted the ordering wanted "
            f"{region_c.get('topNByScoreWithCapsLiftedByRegion')}. On breadth, "
            f"{_fmt(mean(breadth_c, 'tiedPairsInsideTheTopFive'))} tied pairs sit inside the "
            f"top five and {_fmt(mean(breadth_c, 'ranksSixToTenTiedWithTheFifthName'))} of "
            "ranks 6-10 cannot be separated from the fifth name, so a fixed five is "
            "cutting an ordering that does not have five distinguishable names in it."),
        "whatToSeparateFirst": (
            "Two structural problems are now measured and they are not the same one. The "
            "BIGGEST override is the region quota, which binds on almost every rebalance "
            "and turns an ordering that wants one region into a near-fixed 3:2 — but it "
            "cannot be lifted yet, because alpha percentiles are computed WITHIN a region "
            "and there is no common scale to compare them across one. The problem that "
            "can be worked NOW is the double use of downside risk: it sets part of the "
            "alpha through the 0.20 lowvol sleeve, divides that alpha to make the score, "
            "and then sizes the position. `alpha-risk-separation-v1` removes only the "
            "middle use and is the pre-registered first study; the cross-region scale is "
            "the prerequisite the quota study has to build before it can run."),
    }


def structural_markdown(report: dict) -> list[str]:
    """The observational diagnostics: what actually decides this book.

    None of these added a rung or changed a number above. They read the paths
    the ladder produced, to interpret this study and pre-register the next one.
    """
    diag = report["structuralDiagnostics"]
    lines = ["", "## What actually decides the book (observational)", "",
             "None of this section added a rung, changed a score or moved a constraint.",
             "The `lowvol` sleeve weight, the downside-volatility denominator, the",
             "inverse-downside-volatility sizing, the entry multipliers, the region and",
             "sector caps and `targetNames = 5` are all exactly as the ladder ran them.", ""]

    lines += ["### A. Alpha or low volatility?", "",
              "| Reading | Control | + confidence + hysteresis |", "|---|---:|---:|"]
    a_c, a_h = diag["riskDominance"]["control"], diag["riskDominance"]["hysteresis"]
    for label, key, sub in (
            ("Spearman(score, alpha percentile)", "scoreVsAlphaPercentileSpearman", "mean"),
            ("Spearman(score, calibrated alpha)", "scoreVsCalibratedAlphaSpearman", "mean"),
            ("Spearman(score, downside vol)", "scoreVsDownsideVolSpearman", "mean"),
            ("Downside vol of names held", "downsideVolPctSelected", "mean"),
            ("Downside vol of names rejected", "downsideVolPctRejected", "mean"),
            ("`lowvol` sleeve percentile, held", "lowvolSleevePercentileSelected", "mean"),
            ("`lowvol` sleeve percentile, rejected", "lowvolSleevePercentileRejected", "mean")):
        lines.append(f"| {label} | {_fmt((a_c.get(key) or {}).get(sub))} | "
                     f"{_fmt((a_h.get(key) or {}).get(sub))} |")
    for label, key in (("`lowvol` is the name's highest sleeve", "lowvolIsTheHighestSleevePct"),
                       ("`lowvol` is in its top two sleeves", "lowvolIsInTheTopTwoSleevesPct"),
                       ("Held set matching an alpha-only top-N", "heldMatchingAlphaOnlyTopNPct")):
        lines.append(f"| {label} | {_fmt(a_c.get(key), '%')} | {_fmt(a_h.get(key), '%')} |")
    lines.append(f"| Held below the alpha top-N with below-median risk | "
                 f"{a_c.get('heldDespiteLowerAlphaAndBelowMedianRisk')} | "
                 f"{a_h.get('heldDespiteLowerAlphaAndBelowMedianRisk')} |")
    lines.append(f"| In the alpha top-N but dropped with above-median risk | "
                 f"{a_c.get('droppedDespiteTopAlphaAndAboveMedianRisk')} | "
                 f"{a_h.get('droppedDespiteTopAlphaAndAboveMedianRisk')} |")
    lines.append(f"| Held/not-held pairs the alpha term orders the other way | "
                 f"{_fmt((a_c.get('pairwiseOrderingInversionsPct') or {}).get('mean'), '%')} | "
                 f"{_fmt((a_h.get('pairwiseOrderingInversionsPct') or {}).get('mean'), '%')} |")

    b_c = diag["entryStateDynamics"]["control"]
    lines += ["", "### B. The entry state's step function", "",
              f"- States observed: `{b_c.get('observedStates')}`.",
              f"- {b_c.get('transitionsObserved')} state transitions, "
              f"**{_fmt(b_c.get('transitionsCoincidingWithASwapPct'), '%')}** of them on a "
              "name this rebalance moved in or out.",
              f"- {b_c.get('transitionsIntoABlockingState')} transitions into a state that "
              "blocks sizing outright; "
              f"{b_c.get('departuresWhoseStateHadTurnedBlocking')} departures had one.",
              f"- **{b_c.get('departuresWhereTheStepFellAndAlphaMovedOnePointOrLess')}** "
              "departures where the multiplier fell while the name's own alpha percentile "
              "moved a point or less — the step function, not the signal, deciding.", ""]
    if b_c.get("byTransition"):
        lines += ["| Transition | Count | Of those, on a name moved in or out |",
                  "|---|---:|---:|"]
        swaps = b_c.get("byTransitionCoincidingWithASwap") or {}
        for label, count in list(b_c["byTransition"].items())[:8]:
            lines.append(f"| `{label}` | {count} | {swaps.get(label, 0)} |")

    c_c = diag["regionCapBinding"]["control"]
    lines += ["", "### C. Does the diversification guard override the ranking?", "",
              f"- `maxNamesPerRegion = {c_c.get('maxNamesPerRegion')}`, "
              f"`maxNamesPerSector = {c_c.get('maxNamesPerSector')}`, on "
              f"{c_c.get('rebalancesMeasured')} rebalances.",
              f"- The region cap stopped a name on **{_fmt(c_c.get('regionCapBindingPct'), '%')}** "
              f"of them; the sector cap on {_fmt(c_c.get('sectorCapBindingPct'), '%')}.",
              f"- On **{c_c.get('rebalancesWhereACappedNameOutscoredOneTaken')}** rebalances a "
              "capped name outscored the lowest-scoring name the book took, by a median "
              f"decision-alpha gap of "
              f"{_fmt((c_c.get('decisionAlphaGapAtTheOverridePp') or {}).get('median'), 'pp')}.",
              f"- Name-dates held by region: `{c_c.get('heldNameDatesByRegion')}`.",
              f"- Same count, caps lifted, by region: "
              f"`{c_c.get('topNByScoreWithCapsLiftedByRegion')}`.",
              f"- Most common held shapes: "
              f"`{dict(list((c_c.get('heldRegionShapeCounts') or {}).items())[:4])}`."]

    d_c = diag["breadthReadiness"]["control"]
    lines += ["", "### D. What a breadth rule would have to work with", "",
              "`targetNames` stays at five and no breadth rule is implemented or scored.", "",
              "The near-neutral count is meaningful only where confidence is ON: the",
              "control discards no uncertainty, so its margin is zero by construction",
              "and the count is zero for that reason rather than as a reading.", "",
              "| Reading | Control | + confidence + hysteresis |", "|---|---:|---:|"]
    d_h = diag["breadthReadiness"]["hysteresis"]
    for label, key in (("Eligible candidates per rebalance", "eligibleCandidates"),
                       ("Top-ten names whose doubt exceeds their claim",
                        "namesInTopTenWhoseDoubtExceedsTheirClaim"),
                       ("Tied pairs inside the top five", "tiedPairsInsideTheTopFive"),
                       ("Ranks 6-10 tied with the fifth name", "ranksSixToTenTiedWithTheFifthName"),
                       ("Decision-alpha dispersion, top five", "decisionAlphaDispersionTopFivePp"),
                       ("Decision-alpha dispersion, top ten", "decisionAlphaDispersionTopTenPp")):
        lines.append(f"| {label} (mean) | {_fmt((d_c.get(key) or {}).get('mean'))} | "
                     f"{_fmt((d_h.get(key) or {}).get('mean'))} |")
    lines += ["", "| Gap in decision alpha | Control mean | Control median |",
              "|---|---:|---:|"]
    for label, blob in (d_c.get("decisionAlphaGapsPp") or {}).items():
        lines.append(f"| {label} | {_fmt(blob.get('mean'), 'pp')} | "
                     f"{_fmt(blob.get('median'), 'pp')} |")

    e_c = diag["departureCauses"]["control"]
    lines += ["", "### Why each departure happened", "",
              f"{e_c.get('departuresMeasured')} departures on the control path, attributed "
              "once each in the order the machinery applies them.", "",
              "| Cause | Count | Share |", "|---|---:|---:|"]
    for cause, count in (e_c.get("byCause") or {}).items():
        lines.append(f"| {cause} | {count} | "
                     f"{_fmt((e_c.get('bySharePct') or {}).get(cause), '%')} |")
    if e_c.get("ineligibilityByCode"):
        lines += ["", "The ineligible ones, split by the fact that disqualified them "
                  "(a calibration that has not matured yet is an early-history artefact, "
                  "not a selection decision):", ""]
        for code, count in (e_c["ineligibilityByCode"]).items():
            lines.append(f"- `{code}`: {count}")
    lines += ["", "For the ones the ranking outranked, the departing name's own move since "
              "its previous appearance: percentile "
              f"{_fmt((e_c.get('outrankedOwnPercentileMove') or {}).get('mean'))}, reliable "
              f"alpha {_fmt((e_c.get('outrankedOwnReliableAlphaMovePp') or {}).get('mean'), 'pp')}, "
              f"confidence {_fmt((e_c.get('outrankedOwnConfidenceMove') or {}).get('mean'))} "
              "(means, signed)."]
    return lines


def markdown(report: dict) -> str:
    axes = report["axisDiagnostics"]
    lines = [
        "# Alpha reliability v1", "",
        "> Read-only research CHALLENGER on sealed replay-v16 inputs. No factor is",
        "> added, no factor weight moves, no selector is promoted and production is",
        "> unchanged.", "",
        "## The question", "",
        "`selection_value` found 92-93% of turnover is names being REPLACED.",
        "`regional-switch-hurdle-v1` saved 0.270pp of cost drag and gained 2.157pp of",
        "arithmetic stock selection, which no cost argument predicts.",
        "`signal-persistence-v1` found ADDED names realise less than RETAINED ones on a",
        "paired interval that contains zero. All three point at the same place: the",
        "conversion from a continuous signal into a discrete five-name book. This",
        "measures that conversion and then tries to spend the SAME signal more",
        "carefully — level, then persistence, then confidence.", "",
        "## The axis, measured before the ladder was read", "",
        f"The pool's alpha percentiles run {_fmt(axes['alphaPercentile'].get('min'))} to "
        f"{_fmt(axes['alphaPercentile'].get('max'))} "
        f"(mean {_fmt(axes['alphaPercentile'].get('mean'))}, sd "
        f"{_fmt(axes['alphaPercentile'].get('sd'))}) over "
        f"{axes.get('poolNameDates')} pool name-dates. The calibration's bucket edges are",
        f"`{axes.get('bucketEdges')}`, so only **{axes.get('distinctBucketsOccupied')} "
        f"buckets** are ever occupied and "
        f"**{_fmt(axes.get('largestBucketSharePct'), '%')}** of name-dates fall in the",
        "largest one. Names inside a bucket are handed the SAME expected excess, so for",
        "most of the pool the ranking's alpha term is a constant and the ordering is",
        "decided by realised downside volatility alone.", "",
        "| Bucket | Name-dates |", "|---|---:|"]
    for bucket, count in (axes.get("bucketCounts") or {}).items():
        lines.append(f"| {bucket} | {count} |")
    lines += ["", "| Input | mean | sd | p10 | median | p90 |", "|---|---:|---:|---:|---:|---:|"]
    for label, key in (("own percentile sd over k=6", "ownPercentileSdOverWindow"),
                       ("cross-section percentile sd", "crossSectionPercentileSdWithinRegionDate"),
                       ("sleeve agreement", "sleeveAgreement"),
                       ("evidence coverage (already in the level)",
                        "evidenceCoverageAlreadyInTheLevel")):
        blob = axes.get(key) or {}
        lines.append(f"| {label} | {_fmt(blob.get('mean'))} | {_fmt(blob.get('sd'))} | "
                     f"{_fmt(blob.get('p10'))} | {_fmt(blob.get('median'))} | "
                     f"{_fmt(blob.get('p90'))} |")
    lines += ["",
              "`evidenceCoverage` is listed because `longterm` computes",
              "`alpha = rawAlpha x evidenceCoverage` BEFORE the percentile is taken. It has",
              "already shrunk the level, so it is not available as a confidence weight —",
              "using it again would charge the same doubt twice.", "",
              "## How unstable is the top-5 boundary?", ""]

    for label, key in (("control", "control"), ("confidence + hysteresis rung", "hysteresis")):
        blob = report["boundaryInstability"][key]
        lines += [f"### At the cut, {label}", "",
                  f"- Measured on {blob.get('rebalancesMeasured')} rebalances; "
                  f"{blob.get('rebalancesWhereEveryNearMissWasCapped')} more had every "
                  "near miss stopped by a sector or region cap, so the cut there was made "
                  "by the diversification rules and is not read as a ranking boundary.",
                  f"- Expected-alpha gap between the last name held and the first excluded: "
                  f"mean {_fmt((blob['expectedAlphaGapAtCutPp']).get('mean'), 'pp')}, "
                  f"median {_fmt((blob['expectedAlphaGapAtCutPp']).get('median'), 'pp')}.",
                  f"- **{_fmt(blob.get('tiedOnExpectedAlphaPct'), '%')}** of those cuts are a "
                  "TIE on expected alpha — the calibration cannot tell the two names apart and "
                  "the cut is made by downside volatility.",
                  f"- Alpha percentile gap at the cut: mean "
                  f"{_fmt((blob['alphaPercentileGapAtCut']).get('mean'))} points.", ""]

    anat = report["replacementAnatomy"]["control"]
    lines += ["### At the swap, control", "",
              f"- {anat.get('replacementsMeasured')} rebalances replaced at least one name.",
              f"- Expected-alpha gap between the arriving and the departing name: mean "
              f"{_fmt((anat['expectedAlphaGapAtReplacementPp']).get('mean'), 'pp')}, "
              f"median {_fmt((anat['expectedAlphaGapAtReplacementPp']).get('median'), 'pp')}.",
              f"- **{_fmt(anat.get('tiedOnExpectedAlphaPct'), '%')}** of swaps are between two "
              "names the calibration scores IDENTICALLY.",
              f"- Of {anat.get('incumbentsWhosePercentileMovedOnePointOrLess')} held names whose "
              "raw percentile moved one point or less since the previous block, "
              f"**{_fmt(anat.get('ofThoseReplacedPct'), '%')}** were replaced anyway.", "",
              "| Swap population | Arriving minus departing, next block | Win rate | 95% CI | n |",
              "|---|---:|---:|---:|---:|"]
    for label, key in (("all swaps", "arrivingMinusDepartingExcess"),
                       ("tied on expected alpha", "whenTiedOnExpectedAlpha"),
                       ("separated on expected alpha", "whenSeparatedOnExpectedAlpha")):
        blob = anat.get(key) or {}
        ci = blob.get("ci95Pct") or [None, None]
        lines.append(f"| {label} | {_fmt(blob.get('meanPct'), '%')} | "
                     f"{_fmt(blob.get('winRatePct'), '%')} | "
                     f"[{_fmt(ci[0], '%')}, {_fmt(ci[1], '%')}] | "
                     f"{blob.get('observations')} |")

    lines += structural_markdown(report)
    lines += ["", "## The ladder", "",
              "One axis per rung. No transaction-cost hurdle anywhere in the ladder.", "",
              "| Rung | Gross CAGR | Cost drag | Net CAGR | Matched benchmark | Net excess | "
              "Vol | Sharpe | MDD | Turnover |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for rung in AR.LADDER:
        row = report["ladder"][rung]
        lines.append(
            f"| {rung} | {_fmt(row.get('grossCagrPct'), '%')} | "
            f"{_fmt(row.get('costDragCagrPp'), 'pp')} | {_fmt(row.get('cagrPct'), '%')} | "
            f"{_fmt(row.get('benchmarkCagrPct'), '%')} | "
            f"{_fmt(row.get('annualizedExcessPct'), 'pp')} | "
            f"{_fmt(row.get('annualizedRealizedVolPct'), '%')} | "
            f"{_fmt(row.get('sharpe'))} | {_fmt(row.get('mddPct'), '%')} | "
            f"{_fmt(row.get('annualOneWayTurnoverX'), 'x')} |")

    lines += ["", "### Where the gross gap comes from", "",
              "| Rung | Arithmetic selection | Compounding | Geometric gross edge | Block sd ratio |",
              "|---|---:|---:|---:|---:|"]
    for rung in AR.LADDER:
        edge = (report["ladder"][rung].get("edgeDecomposition") or {})
        lines.append(f"| {rung} | {_fmt(edge.get('arithmeticSelectionEdgePp'), 'pp')} | "
                     f"{_fmt(edge.get('compoundingEdgePp'), 'pp')} | "
                     f"{_fmt(edge.get('geometricGrossEdgePp'), 'pp')} | "
                     f"{_fmt(edge.get('blockSdRatio'), 'x')} |")

    lines += ["", "### Turnover: names replaced against weights retargeted", "",
              "| Rung | One-way turnover | From name replacement | From weight retarget | "
              "Name share | US retention | KR retention |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for rung in AR.LADDER:
        blob = (report["ladder"][rung].get("turnoverDecomposition") or {})
        regional = report["retentionByRegion"][rung]
        lines.append(f"| {rung} | {_fmt(blob.get('averageOneWayTurnoverPct'), '%')} | "
                     f"{_fmt(blob.get('fromNameReplacementPct'), '%')} | "
                     f"{_fmt(blob.get('fromWeightRetargetPct'), '%')} | "
                     f"{_fmt(blob.get('nameReplacementSharePct'), '%')} | "
                     f"{_fmt((regional.get('US') or {}).get('retentionRatePct'), '%')} | "
                     f"{_fmt((regional.get('KR') or {}).get('retentionRatePct'), '%')} |")

    lines += ["", "### Selection behaviour", "",
              "| Rung | Names held | Retained | Added | Incumbent retention | Replacement rate |",
              "|---|---:|---:|---:|---:|---:|"]
    for rung in AR.LADDER:
        blob = report["selectionBehaviour"][rung]
        lines.append(f"| {rung} | {_fmt(blob.get('averageNamesHeld'))} | "
                     f"{_fmt(blob.get('averageRetained'))} | {_fmt(blob.get('averageAdded'))} | "
                     f"{_fmt(blob.get('incumbentRetentionRatePct'), '%')} | "
                     f"{_fmt(blob.get('incumbentReplacementRatePct'), '%')} |")

    lines += ["", "### Regional contribution to gross excess", "",
              "| Rung | US contribution | US 95% CI | KR contribution | KR 95% CI |",
              "|---|---:|---:|---:|---:|"]
    for rung in AR.LADDER:
        blob = (report["regionalAttribution"][rung].get("byRegion") or {})
        cells = []
        for region in ("US", "KR"):
            entry = blob.get(region) or {}
            ci = entry.get("contributionCi95Pp") or [None, None]
            cells.append(f"{_fmt(entry.get('contributionPpPerYear'), 'pp')}")
            cells.append(f"[{_fmt(ci[0], 'pp')}, {_fmt(ci[1], 'pp')}]")
        lines.append(f"| {rung} | " + " | ".join(cells) + " |")

    lines += ["", "### Paired differences, one axis at a time", "",
              "Each rung against the rung BELOW it, which differs from it in exactly one",
              "thing. The cumulative column is the same rung against the ladder control.", "",
              "| Rung | Δ vs rung below | 95% CI | Δ vs control | 95% CI | Blocks |",
              "|---|---:|---:|---:|---:|---:|"]
    for rung in AR.LADDER[1:]:
        adjacent = report["pairedAdjacent"][rung]
        cumulative = report["pairedVsControl"][rung]
        a_point, a_lo, a_hi = _pair(adjacent)
        c_point, c_lo, c_hi = _pair(cumulative)
        lines.append(
            f"| {rung} | {_fmt(a_point, 'pp')} | [{_fmt(a_lo, 'pp')}, {_fmt(a_hi, 'pp')}] | "
            f"{_fmt(c_point, 'pp')} | [{_fmt(c_lo, 'pp')}, {_fmt(c_hi, 'pp')}] | "
            f"{report['pairedBlocks']} |")

    stacked = report["stacked"]
    s_point, s_lo, s_hi = _pair(stacked["vsHysteresisRung"])
    row = stacked["summary"]
    lines += ["", "## Stacked with the transaction-cost hurdle, reported separately", "",
              "This adds the `regional-switch-hurdle-v1` cost credit on top of the last",
              "ladder rung, so it moves TWO axes and its number is attributable to",
              "neither. It is here because a production rule would carry both, not",
              "because it is evidence for either.", "",
              f"- Net excess **{_fmt(row.get('annualizedExcessPct'), 'pp')}**, Sharpe "
              f"{_fmt(row.get('sharpe'))}, MDD {_fmt(row.get('mddPct'), '%')}, turnover "
              f"{_fmt(row.get('annualOneWayTurnoverX'), 'x')}.",
              f"- Against the last ladder rung: Δ {_fmt(s_point, 'pp')}, 95% CI "
              f"[{_fmt(s_lo, 'pp')}, {_fmt(s_hi, 'pp')}].", ""]

    finding = report["finding"]
    lines += ["## Reading", "", f"**{finding['verdict']}** — {finding['verdictNote']}",
              "", finding["summary"], "",
              "### What separated, and in which direction", "",
              "An interval that excludes zero from BELOW is as much a separation as one",
              "that excludes it from above, and it is the more informative of the two:",
              "it means a pre-specified axis made the path measurably worse.", ""]
    for label, key in (("against the rung below", "separatedFromRungBelow"),
                       ("against the ladder control", "separatedFromControl")):
        blob = finding[key]
        if not blob:
            lines.append(f"- Nothing separated {label}.")
            continue
        for rung, entry in blob.items():
            lines.append(
                f"- {rung} separated {label}, **{entry['direction']}**: "
                f"{_fmt(entry['pointEstimatePp'], 'pp')}, 95% CI "
                f"[{_fmt(entry['ci95Pp'][0], 'pp')}, {_fmt(entry['ci95Pp'][1], 'pp')}].")
    lines += ["", "### Refuted", ""]
    for item in finding["refuted"]:
        lines.append(f"- {item}")
    answers = finding["closingAnswers"]
    lines += ["", "### Five questions this study was asked to answer", ""]
    for number, (label, key) in enumerate((
            ("What explains the final ordering — alpha or downside risk?",
             "whatExplainsTheFinalOrdering"),
            ("Does low-volatility dominance survive persistence and confidence?",
             "doesLowVolatilityDominanceSurviveTheStudy"),
            ("What drove the actual replacements?", "whatDroveTheReplacements"),
            ("Do a fixed five and the region quota override the signal?",
             "doFixedFiveAndTheRegionQuotaOverrideTheSignal"),
            ("What should the next study separate first?", "whatToSeparateFirst")), start=1):
        lines += [f"**{number}. {label}**", "", answers[key], ""]

    lines += ["### Pre-registered next studies", "",
              "Specified here, before any of them is run, and in this order. None is",
              "implemented, scored or parameterised by this PR.", ""]
    for study in report["nextStudies"]:
        lines += [f"**Study {study['order']} — `{study['id']}`**", "",
                  f"- Question: {study['question']}",
                  f"- First axis: {study['firstAxis']}"]
        if study.get("prerequisite"):
            lines.append(f"- Prerequisite: {study['prerequisite']}")
        if study.get("notInTheFirstLadder"):
            lines.append(f"- Deliberately NOT in the first ladder: {study['notInTheFirstLadder']}")
        lines.append("")

    lines += ["### Frozen candidate for prospective validation", "",
              f"**{finding['frozenCandidate'] or 'NONE — see below'}**", "",
              finding["frozenCandidateNote"], "",
              "A rung ending higher than another is a point estimate on sealed history,",
              "after several rungs across four studies, with no multiplicity correction.",
              "It is not evidence to promote a selector.", ""]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger_dir")
    parser.add_argument("--output", default="alpha-reliability-report.json")
    parser.add_argument("--markdown", default="alpha-reliability-report.md")
    args = parser.parse_args(argv)
    ledger = Path(args.ledger_dir)
    output, md = _guard(args.output, ledger), _guard(args.markdown, ledger)
    before = _digest_tree(ledger)

    cfg, _ = load_config()
    store = RI.InputStore(ledger, provenance.REPLAY_VERSION, provenance.DATA_VERSION)
    manifest = store.manifest()
    if not manifest or provenance.REPLAY_VERSION != "replay-v16":
        raise ValueError("alpha-reliability-v1 requires sealed replay-v16 inputs")
    frozen = RI.unpack(store.load(manifest, valuation_only=True))
    valuation = RV.ValuationData(
        frozen["prices"], cfg.benchmarks, frozen["fx"], frozen["risk_free"],
        through=manifest["through"],
        risk_free_through=frozen["risk_free_source"]["verifiedThrough"],
        corporate_actions=frozen.get("corporate_actions"))
    print("loading projected frozen signals and outcomes", flush=True)
    signals = HS.load(ledger, HS.SIGNALS, provenance.REPLAY_VERSION,
                      project=HS.audit_projection)
    outcomes = HS.load(ledger, HS.OUTCOMES, provenance.REPLAY_VERSION)
    sealed = json.loads((ledger / "historical-portfolio-validation.json").read_text())
    if sealed.get("inputSnapshot", {}).get("sha256") != manifest["sha256"]:
        raise ValueError("sealed report and frozen inputs have different lineage")

    replay_cfg = cfg.historical_replay or {}
    calendar = [b for b in RC.schedule(
        replay_cfg.get("start", RC.ORIGIN), manifest["through"], PV.HEADLINE_HORIZON,
        replay_cfg.get("frequency", "W")) if b["endDate"] <= manifest["through"]]
    contexts = SV.contexts_from_signals(signals, cfg.longterm)
    research_cfg = BA.cost_config(cfg.kelly_portfolio)

    def calibrator():
        return PV.ExpandingBucketCalibration(
            outcomes, horizon=int(cfg.kelly_portfolio.get("horizonDays", 126)),
            prior_strength=float(cfg.kelly_portfolio.get("shrinkagePriorStrength", 30)),
            min_dates=20, cost_adjusted=False)

    paths = {}
    for rung in AR.LADDER:
        print(f"running {rung} on {len(calendar)} blocks", flush=True)
        result = AR.run_rung(rung, contexts=contexts, calibrator=calibrator(),
                             calendar=calendar, cfg_pf=cfg.kelly_portfolio,
                             valuation=valuation)
        if not result["complete"]:
            raise ValueError(f"{rung} path incomplete: {result['failures'][:3]}")
        paths[rung] = result

    print(f"running {AR.STACKED} (two axes, reported separately)", flush=True)
    stacked = AR.run_rung(AR.STACKED, contexts=contexts, calibrator=calibrator(),
                          calendar=calendar, cfg_pf=cfg.kelly_portfolio,
                          valuation=valuation)
    if not stacked["complete"]:
        raise ValueError("stacked path incomplete")

    print("pricing the fixed cross-section for the replacement diagnostics", flush=True)
    by_date: dict[str, list[dict]] = {}
    for row in signals:
        if row.get("date"):
            by_date.setdefault(row["date"], []).append(row)
    shared = [row["date"] for row in paths[AR.CONTROL]["rows"]]
    _, priced_by_date, _ = PV.priced_cross_section(
        contexts, by_date, calendar, shared, valuation)

    summaries = {rung: SV.summarize(paths[rung]["rows"], research_cfg)
                 for rung in AR.LADDER}
    stacked_summary = SV.summarize(stacked["rows"], research_cfg)
    control_rows = paths[AR.CONTROL]["rows"]
    hysteresis_rung = AR.PERSISTENCE_CONFIDENCE_HYSTERESIS

    report = {
        "version": AR.VERSION, "status": "CHALLENGER",
        "freezeManifest": AR.freeze_manifest(),
        "inputSnapshot": {"sha256": manifest["sha256"], "through": manifest["through"]},
        "harnessNote": (
            "The ladder control is the same loop `signal_persistence` runs as "
            "RANK_ON_LATEST_ALPHA_PERCENTILE and `switch_hurdle` runs as "
            "NO_HURDLE_CONTROL_SAME_LOOP. Its published gap to the sealed challenger "
            "path is -0.684pp against -1.046pp of annualized net excess; that "
            "difference is the research harness, not a rung, and every comparison here "
            "is paired against this control rather than against the sealed path."),
        "axisDiagnostics": AR.axis_diagnostics(contexts, calendar),
        "boundaryInstability": {
            "control": AR.boundary_instability(paths[AR.CONTROL]["decisions"]),
            "hysteresis": AR.boundary_instability(paths[hysteresis_rung]["decisions"]),
        },
        "replacementAnatomy": {
            "control": AR.replacement_anatomy(paths[AR.CONTROL]["decisions"], priced_by_date),
            "hysteresis": AR.replacement_anatomy(paths[hysteresis_rung]["decisions"],
                                                 priced_by_date),
        },
        # Observational only, added after the ladder was scored. Each one READS
        # the paths above; none adds a rung, changes a score or moves a
        # constraint, and the ladder's numbers are identical with and without
        # them. They exist to interpret this study and pre-register the next.
        "structuralDiagnostics": {
            "riskDominance": {
                "control": AR.risk_dominance(paths[AR.CONTROL]["decisions"]),
                "hysteresis": AR.risk_dominance(paths[hysteresis_rung]["decisions"]),
            },
            "entryStateDynamics": {
                "control": AR.entry_state_dynamics(paths[AR.CONTROL]["decisions"]),
                "hysteresis": AR.entry_state_dynamics(paths[hysteresis_rung]["decisions"]),
            },
            "regionCapBinding": {
                "control": AR.region_cap_binding(paths[AR.CONTROL]["decisions"], research_cfg),
                "hysteresis": AR.region_cap_binding(paths[hysteresis_rung]["decisions"],
                                                    research_cfg),
            },
            "breadthReadiness": {
                "control": AR.breadth_readiness(paths[AR.CONTROL]["decisions"]),
                "hysteresis": AR.breadth_readiness(paths[hysteresis_rung]["decisions"]),
            },
            "departureCauses": {
                "control": AR.departure_causes(paths[AR.CONTROL]["decisions"]),
                "hysteresis": AR.departure_causes(paths[hysteresis_rung]["decisions"]),
            },
        },
        "ladder": {rung: _fields(summaries[rung]) for rung in AR.LADDER},
        "selectionBehaviour": {rung: selection_behaviour(paths[rung]["decisions"])
                               for rung in AR.LADDER},
        "retentionByRegion": {rung: AR.retention_rates(paths[rung]["decisions"])
                              for rung in AR.LADDER},
        "regionalAttribution": {
            rung: SH.regional_attribution(
                paths[rung]["rows"], years=summaries[rung].get("calendarYears") or 0)
            for rung in AR.LADDER},
        "pairedVsControl": {
            rung: RVL.paired_bootstrap(paths[rung]["rows"], control_rows, research_cfg)
            for rung in AR.LADDER[1:]},
        "pairedAdjacent": {
            rung: RVL.paired_bootstrap(paths[rung]["rows"],
                                       paths[AR.LADDER[index]]["rows"], research_cfg)
            for index, rung in enumerate(AR.LADDER[1:])},
        "pairedBlocks": len(control_rows),
        "stacked": {
            "summary": _fields(stacked_summary),
            "vsHysteresisRung": RVL.paired_bootstrap(
                stacked["rows"], paths[hysteresis_rung]["rows"], research_cfg),
            "vsControl": RVL.paired_bootstrap(stacked["rows"], control_rows, research_cfg),
            "selectionBehaviour": selection_behaviour(stacked["decisions"]),
            "note": ("Adds the transaction-cost switch hurdle on top of the last ladder "
                     "rung, so it moves two axes and is attributable to neither. Not a "
                     "ladder rung and not promotion evidence."),
        },
        "nextStudies": [dict(study) for study in NEXT_STUDIES],
        "sealedInvariant": {"before": before, "after": _digest_tree(ledger)},
        "productionChanged": False,
    }
    report["sealedInvariant"]["unchanged"] = (
        report["sealedInvariant"]["before"] == report["sealedInvariant"]["after"])
    if not report["sealedInvariant"]["unchanged"]:
        raise ValueError("SEALED_LEDGER_CHANGED")

    separated_adjacent = {rung: blob for rung in AR.LADDER[1:]
                          if (blob := _separation(report["pairedAdjacent"][rung]))}
    separated_control = {rung: blob for rung in AR.LADDER[1:]
                         if (blob := _separation(report["pairedVsControl"][rung]))}
    control_excess = summaries[AR.CONTROL].get("annualizedExcessPct")
    best = max(AR.LADDER, key=lambda r: summaries[r].get("annualizedExcessPct") or -1e9)
    anat = report["replacementAnatomy"]["control"]
    axes = report["axisDiagnostics"]

    # A CANDIDATE IS FROZEN ONLY IF ITS OWN PRE-SPECIFIED TEST DID NOT REFUTE IT.
    # PROVENANCE OF THIS RULE, because it matters more than the rule. The design
    # named the last rung as the candidate unconditionally. The first full run
    # returned that rung's confidence axis separated from the rung below it in
    # the WRONG direction, and freezing a candidate its own paired test had just
    # refuted would have made the test decorative. So the freeze was made
    # conditional AFTER that run. No rung, parameter, window or scoring rule
    # changed, and the condition can only ever REMOVE a candidate — it cannot
    # promote one, and it cannot make a refuted axis look better. That asymmetry
    # is what separates it from re-specifying a ladder until the hypothesis
    # survives, which is the failure this repository's discipline exists to
    # prevent.
    refuted_axes = [rung for rung, blob in separated_adjacent.items()
                    if blob["direction"] == "WORSE"]
    hysteresis_rung_refuted = [rung for rung in refuted_axes
                               if AR.LADDER.index(rung) <= AR.LADDER.index(hysteresis_rung)]
    frozen = None if hysteresis_rung_refuted else hysteresis_rung
    refuted_notes = []
    for rung in refuted_axes:
        blob = separated_adjacent[rung]
        refuted_notes.append(
            f"{rung}: the axis this rung adds made the path WORSE than the rung below "
            f"it by {_fmt(blob['pointEstimatePp'], 'pp')} of annualized net excess, 95% "
            f"CI [{_fmt(blob['ci95Pp'][0], 'pp')}, {_fmt(blob['ci95Pp'][1], 'pp')}], which "
            "EXCLUDES zero. The hypothesis behind it is refuted by its own "
            "pre-specified test and the rule is kept, not deleted, so the instrument "
            "that produced the answer survives.")
    if frozen is None:
        frozen_note = (
            "NOTHING IS FROZEN. The freeze rule is that a candidate is carried into "
            "prospective validation only if no axis it contains was refuted by its own "
            "paired test. "
            + " ".join(refuted_notes)
            + " That condition was NOT in the original design, which named the last "
            "rung unconditionally; it was added after the first full run returned this "
            "refutation, and the record says so rather than pretending otherwise. What "
            "makes it a tightening rather than a re-specification: no rung, parameter, "
            "window or scoring rule changed, every number here is what that run "
            "produced, and the condition can only ever REMOVE a candidate — it cannot "
            "promote one and it cannot make a refuted axis look better. So this study "
            "freezes no new candidate, the `signal-persistence-v1` k=6 rung stands as "
            "the one already frozen, and the refuted rule is kept rather than deleted. "
            "What the boundary diagnostic established is independent of the ladder and "
            "stands whatever the rungs did.")
    else:
        frozen_note = (
            f"`{frozen}` is the candidate this study freezes: k=6 backward persistence "
            "inherited from `signal-persistence-v1`, a confidence weight built only "
            "from a name's own percentile stability and its cross-sleeve agreement, and "
            "an incumbent/challenger comparison that requires the two "
            "uncertainty-adjusted readings not to overlap. It introduces no new "
            "parameter, adds no factor, and carries no transaction-cost term. What "
            "prospective data must check: benchmark excess, turnover, retained-versus-"
            "added realised excess, replacement success rate, ranking stability and "
            "whether the confidence weight is calibrated — that names it scores as "
            "low-confidence really do realise noisier outcomes.")

    best_interval = (_separation(report["pairedVsControl"][best])
                     if best != AR.CONTROL else None)
    report["finding"] = {
        "verdict": ("BENCHMARK_BEATEN" if (summaries[best].get("annualizedExcessPct") or 0) > 0
                    else "BENCHMARK_NOT_BEATEN"),
        "verdictNote": (
            "The verdict reads the best rung's POINT ESTIMATE against its matched "
            "benchmark and says nothing about whether that rung is distinguishable "
            "from the control. "
            + ("It is not: its paired interval against the control contains zero."
               if best_interval is None else
               f"Its paired interval against the control excludes zero, "
               f"{best_interval['direction']}.")),
        "bestRung": best,
        "bestNetExcessPp": summaries[best].get("annualizedExcessPct"),
        "controlNetExcessPp": control_excess,
        "separatedFromRungBelow": separated_adjacent,
        "separatedFromControl": separated_control,
        "refutedAxes": refuted_axes,
        "frozenCandidate": frozen,
        "closingAnswers": closing_answers(report, summaries),
        "promotionEligible": False,
        "summary": (
            f"The pool occupies {axes.get('distinctBucketsOccupied')} calibration buckets "
            f"and {_fmt(axes.get('largestBucketSharePct'), '%')} of its name-dates sit in "
            f"one of them, so "
            f"{_fmt(report['boundaryInstability']['control'].get('tiedOnExpectedAlphaPct'), '%')} "
            "of the control's top-5 cuts and "
            f"{_fmt(anat.get('tiedOnExpectedAlphaPct'), '%')} of its swaps are between names "
            "the calibration scores IDENTICALLY — ordered by realised downside volatility, "
            "not by alpha. Net excess moves from "
            f"{_fmt(control_excess, 'pp')} at the control to "
            + ", ".join(f"{_fmt(summaries[r].get('annualizedExcessPct'), 'pp')} ({r})"
                        for r in AR.LADDER[1:]) + "."),
        "refuted": refuted_notes + [
            ("Shrinking the alpha PERCENTILE toward a neutral percentile: the pool sits "
             "at 91-100, so shrinking toward the pool mean moves weak names UP into the "
             "top bucket and shrinking toward 50 collapses every name into one bucket. "
             "The confidence weight is applied in alpha space instead."),
            ("Evidence coverage and factor coverage as confidence weights: `longterm` "
             "already computes alpha = rawAlpha x evidenceCoverage before the percentile "
             "is taken, so both are inside the level and reusing them charges the same "
             "doubt twice."),
            ("'A one-point percentile change flips a holding' as the mechanism: the "
             "percentile only reaches the decision through a five-edge bucket map, so "
             "most one-point moves change nothing and most swaps happen between names "
             "with no alpha difference at all."),
        ],
        "frozenCandidateNote": frozen_note,
        "nextDirection": (
            "The binding constraint measured here is RESOLUTION, not information: the "
            "calibration maps an already alpha-filtered pool onto two buckets, so the "
            "ranking cannot express a difference between most of the names it is asked "
            "to choose between. Before any new factor is collected, the question is "
            "whether a finer or pool-relative calibration of the SAME percentile "
            "recovers orderings the current bucket map discards."),
    }

    output.write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                 allow_nan=False, sort_keys=True) + "\n")
    md.write_text(markdown(report))
    print(markdown(report), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
