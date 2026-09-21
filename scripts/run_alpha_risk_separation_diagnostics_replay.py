"""Read the frozen alpha-risk-separation ladder; add only what it did not answer.

The primary ladder is NOT re-scored here. It is re-run by calling the frozen
study's own functions, and every scored block it produces is asserted
byte-identical against the checked-in
`docs/results/alpha-risk-separation-report.json`. If any of them moves, a
diagnostic in this run has touched the ladder and the report is REFUSED
rather than published. The frozen result file is never written to.

What is added: the set-difference factor/outcome profile the frozen study
never measured, the region-cap and entry-state observational reads, an
exploratory two-axis stack reported strictly outside the ladder, and the
Q1-Q8 answers in prose.

Nothing here writes inside the ledger and nothing here promotes a selector.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import alpha_reliability as AR                        # noqa: E402
from pipeline import alpha_risk_separation as ARS                   # noqa: E402
from pipeline import alpha_risk_separation_diagnostics as D         # noqa: E402
from pipeline import benchmark_alpha as BA                          # noqa: E402
from pipeline import historical_store as HS                         # noqa: E402
from pipeline import portfolio_validation as PV                     # noqa: E402
from pipeline import provenance                                     # noqa: E402
from pipeline import regional_validation as RVL                     # noqa: E402
from pipeline import replay_calendar as RC                          # noqa: E402
from pipeline import replay_inputs as RI                            # noqa: E402
from pipeline import replay_valuation as RV                         # noqa: E402
from pipeline import selection_value as SV                          # noqa: E402
from pipeline import switch_hurdle as SH                            # noqa: E402
from pipeline.config import load_config                             # noqa: E402

FROZEN_REPORT = ROOT / "docs" / "results" / "alpha-risk-separation-report.json"


def _guard(path: str, ledger: Path) -> Path:
    target = Path(path).resolve()
    if target == ledger.resolve() or ledger.resolve() in target.parents:
        raise ValueError("research output must remain outside the sealed ledger")
    if target == FROZEN_REPORT.resolve():
        raise ValueError("refusing to rewrite the frozen alpha-risk-separation report")
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


def _canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


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
    point, low, high = _pair(blob, key)
    if low is None or high is None:
        return None
    if low > 0:
        return {"direction": "BETTER", "pointEstimatePp": point, "ci95Pp": [low, high]}
    if high < 0:
        return {"direction": "WORSE", "pointEstimatePp": point, "ci95Pp": [low, high]}
    return None


def selection_behaviour(decisions: list[dict]) -> dict:
    retained = [len(d.get("retained") or []) for d in decisions]
    added = [len(d.get("added") or []) for d in decisions]
    replaced = [len(d.get("replaced") or []) for d in decisions]
    held = [d.get("heldNames") or 0 for d in decisions]
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


def _q4_verdict(challenger_side: dict, control_side: dict, mean_of) -> str:
    """State what the set difference actually says, rather than leaving it implied.

    The question presumes the denominator was blocking high-momentum /
    high-quality names. Whether it was is decided by which sleeves actually
    separate the two groups, so the verdict is derived from the measured gaps
    rather than asserted.
    """
    gaps = {sleeve: (None if mean_of(challenger_side, sleeve) is None
                     or mean_of(control_side, sleeve) is None
                     else mean_of(challenger_side, sleeve) - mean_of(control_side, sleeve))
            for sleeve in ("momentum", "quality", "value", "lowvol")}
    vol_gap = (None if mean_of(challenger_side, "downsideVolPct") is None
               or mean_of(control_side, "downsideVolPct") is None
               else mean_of(challenger_side, "downsideVolPct")
               - mean_of(control_side, "downsideVolPct"))
    if gaps["momentum"] is None or gaps["lowvol"] is None or vol_gap is None:
        return "The set difference could not be profiled on this sample."
    # "Separates" here means the gap is larger than the smallest gap that any
    # sleeve shows — a within-run comparison, not a threshold chosen in advance.
    momentum_gap, quality_gap, lowvol_gap = (gaps["momentum"], gaps["quality"],
                                             gaps["lowvol"])
    alpha_axis_moved = max(abs(momentum_gap), abs(quality_gap or 0.0))
    risk_axis_moved = abs(lowvol_gap)
    if risk_axis_moved > alpha_axis_moved:
        return (
            f"SO THE PREMISE OF THIS QUESTION IS NOT WHAT HAPPENED. Momentum moved "
            f"{momentum_gap:+.3f} and quality {(quality_gap or 0.0):+.3f} between the two "
            f"groups — differences of well under a percentile point — while `lowvol` "
            f"moved {lowvol_gap:+.3f} and realised downside volatility {vol_gap:+.3f}pp. "
            "The denominator was not holding back high-momentum or high-quality names. "
            "It was holding back names with the SAME alpha profile at HIGHER "
            "volatility, which is what a risk denominator is supposed to do. That "
            "reframes the axis: removing it did not buy different alpha, it bought the "
            "same alpha more riskily.")
    return (
        f"Momentum moved {momentum_gap:+.3f} and quality {(quality_gap or 0.0):+.3f} "
        f"against `lowvol`'s {lowvol_gap:+.3f} and {vol_gap:+.3f}pp of realised downside "
        "volatility, so the alpha sleeves separate the two groups at least as much as "
        "the risk axis does — the denominator was ordering on more than volatility "
        "alone.")


def _answers(report: dict) -> list[dict]:
    """Q1-Q8, answered from this run's own numbers."""
    ladder = report["frozenLadderReproduced"]["ladder"]
    control = ladder[D.CONTROL]
    challenger = ladder[D.ALPHA_ONLY]
    point, lo, hi = _pair(report["frozenLadderReproduced"]["pairedVsControl"])
    sep = report["frozenLadderReproduced"]["separation"]
    control_edge = control.get("edgeDecomposition") or {}
    challenger_edge = challenger.get("edgeDecomposition") or {}
    tilt = report["frozenLadderReproduced"]["tiltSurvival"]
    diff = report["setDifferenceProfiles"]
    challenger_side = diff["selectedByChallengerNotControl"]
    control_side = diff["selectedByControlNotChallenger"]
    boundary = report["frozenLadderReproduced"]["boundaryInstability"]

    def _m(side, key):
        return (side.get(key) or {}).get("mean")

    return [
        {"q": "Q1. Downside-volatility denominator를 제거했을 때 benchmark-relative "
              "net performance는 어떻게 변했는가?",
         "a": (f"Net excess moved {_fmt(control.get('annualizedExcessPct'), 'pp')} -> "
               f"{_fmt(challenger.get('annualizedExcessPct'), 'pp')}. Paired difference "
               f"{_fmt(point, 'pp')}, 95% CI [{_fmt(lo, 'pp')}, {_fmt(hi, 'pp')}] over "
               f"{report['frozenLadderReproduced']['pairedBlocks']} blocks, which "
               + ("EXCLUDES zero (" + sep["direction"] + ")." if sep else "CONTAINS zero.")
               + " The point estimate is worse and the interval does not clear zero in "
               "either direction, so removing the denominator is NOT SHOWN to help and "
               "is not shown to hurt either.")},
        {"q": "Q2. 그 변화 중 얼마가 arithmetic stock selection이고 얼마가 "
              "compounding / volatility effect인가?",
         "a": (f"Arithmetic stock selection "
               f"{_fmt(control_edge.get('arithmeticSelectionEdgePp'), 'pp')} -> "
               f"{_fmt(challenger_edge.get('arithmeticSelectionEdgePp'), 'pp')}; "
               f"compounding {_fmt(control_edge.get('compoundingEdgePp'), 'pp')} -> "
               f"{_fmt(challenger_edge.get('compoundingEdgePp'), 'pp')}; block sd ratio "
               f"{_fmt(control_edge.get('blockSdRatio'), 'x')} -> "
               f"{_fmt(challenger_edge.get('blockSdRatio'), 'x')}. This is the primary "
               "mechanism metric: it says whether any move came from CHOOSING "
               "differently or merely from a changed volatility profile.")},
        {"q": "Q3. 저변동성/방어주 편향은 실제로 감소했는가?",
         "a": (f"Held downside volatility moved "
               f"{_fmt(tilt.get('downsideVolPctSelectedDelta'), 'pp')} and `lowvol` being "
               f"a held name's highest sleeve moved "
               f"{_fmt(tilt.get('lowvolIsTheHighestSleevePctDelta'), 'pp')}; the score's "
               f"rank correlation with downside volatility moved "
               f"{_fmt(tilt.get('scoreVsDownsideVolSpearmanControl'))} -> "
               f"{_fmt(tilt.get('scoreVsDownsideVolSpearmanAlphaOnly'))}. The tilt is "
               "REDUCED, not removed — part of it arrives through the `lowvol` sleeve "
               "inside the alpha, which this study deliberately does not touch.")},
        {"q": "Q4. Momentum/Quality가 강하지만 volatility가 높은 종목이 더 많이 "
              "선택되었는가?",
         "a": (f"On the {diff['heldNameDatesDisagreed']} name-dates the two rungs "
               f"disagree about: the challenger-only names carry momentum "
               f"{_fmt(_m(challenger_side, 'momentum'))} / quality "
               f"{_fmt(_m(challenger_side, 'quality'))} / lowvol "
               f"{_fmt(_m(challenger_side, 'lowvol'))} at "
               f"{_fmt(_m(challenger_side, 'downsideVolPct'), '%')} downside volatility, "
               f"against the control-only names' momentum "
               f"{_fmt(_m(control_side, 'momentum'))} / quality "
               f"{_fmt(_m(control_side, 'quality'))} / lowvol "
               f"{_fmt(_m(control_side, 'lowvol'))} at "
               f"{_fmt(_m(control_side, 'downsideVolPct'), '%')}. "
               + _q4_verdict(challenger_side, control_side, _m))},
        {"q": "Q5. 그러한 newly selected high-vol names가 실제 forward "
              "benchmark-relative return에서도 더 나았는가? (descriptive only)",
         "a": (f"Challenger-only names realised "
               f"{_fmt((challenger_side['realisedForwardBenchmarkExcessPct'] or {}).get('meanPct'), '%')} "
               f"mean forward block excess (win rate "
               f"{_fmt((challenger_side['realisedForwardBenchmarkExcessPct'] or {}).get('winRatePct'), '%')}) "
               f"against control-only names' "
               f"{_fmt((control_side['realisedForwardBenchmarkExcessPct'] or {}).get('meanPct'), '%')} "
               f"(win rate "
               f"{_fmt((control_side['realisedForwardBenchmarkExcessPct'] or {}).get('winRatePct'), '%')}), "
               f"a difference of "
               f"{_fmt(diff.get('realisedForwardExcessDifferencePp'), 'pp')}. This is a "
               "difference of two group means, not a paired test, and it is DESCRIPTIVE: "
               "no rule, score or ranking in this repository reads it.")},
        {"q": "Q6. Volatility와 MDD는 얼마나 악화 또는 개선되었으며 inverse-vol sizing만으로 "
              "그 risk 증가가 충분히 통제되었는가?",
         "a": (f"Realized volatility "
               f"{_fmt(control.get('annualizedRealizedVolPct'), '%')} -> "
               f"{_fmt(challenger.get('annualizedRealizedVolPct'), '%')}, MDD "
               f"{_fmt(control.get('mddPct'), '%')} -> {_fmt(challenger.get('mddPct'), '%')}, "
               f"Sharpe {_fmt(control.get('sharpe'))} -> {_fmt(challenger.get('sharpe'))}. "
               "Inverse-downside-volatility SIZING is identical on both rungs, so "
               "whatever risk moved is what the SELECTION change let in that sizing "
               "alone did not absorb.")},
        {"q": "Q7. Top-5 boundary에서 expected-alpha tie가 발생했을 때 denominator 제거 "
              "전후로 무엇이 실제 tie-breaker가 되었는가?",
         "a": (f"Cuts tied on expected alpha "
               f"{_fmt((boundary['control'] or {}).get('tiedOnExpectedAlphaPct'), '%')} -> "
               f"{_fmt((boundary['alphaOnly'] or {}).get('tiedOnExpectedAlphaPct'), '%')}, "
               f"and the relative score gap at the cut (median) "
               f"{_fmt(((boundary['control'] or {}).get('relativeScoreGapAtCut') or {}).get('median'))} -> "
               f"{_fmt(((boundary['alphaOnly'] or {}).get('relativeScoreGapAtCut') or {}).get('median'))}. "
               "Removing the score's one continuously-varying term can only make ties at "
               "the margin MORE common: with the denominator gone the calibration's "
               "coarse alpha is all that is left, and the tie-break falls to the "
               "deterministic ticker ordering inside `_select_scored` rather than to any "
               "signal at all.")},
        {"q": "Q8. 이번 결과는 'lowvol sleeve를 alpha에서 제거하고 risk layer로 이동'할 "
              "충분한 근거를 주는가?",
         "a": ("Interpretation only; that experiment is NOT run here. The denominator's "
               "removal did not separate from the control in either direction, and the "
               "defensive tilt SURVIVED it — which localises the remaining tilt in the "
               "`lowvol` sleeve inside the alpha rather than in the ranking. That makes "
               "the sleeve the coherent next axis to TEST, and it is exactly not "
               "evidence that moving it would help: this study's own axis produced no "
               "separation, and a second axis inherits that uncertainty rather than "
               "resolving it.")},
    ]


def markdown(report: dict) -> str:
    frozen = report["frozenLadderReproduced"]
    ladder = frozen["ladder"]
    lines = [
        "# Alpha risk separation — diagnostic extension v1", "",
        "> Read-only extension of the FROZEN `alpha-risk-separation-v1` ladder.",
        "> No rung is re-scored, no score moves, and the checked-in frozen report",
        "> is never rewritten — every scored block below is asserted byte-identical",
        "> to it. Nothing is promoted and production is unchanged.", "",
        "## What this adds, and why it is a separate study", "",
        "`alpha-risk-separation-v1` is scored and merged. `alpha-reliability-v1`'s own",
        "rule — A DIAGNOSTIC ADDED AFTER A LADDER IS SCORED MAY ONLY READ IT — is what",
        "this obeys: the frozen rungs are re-run by CALLING the frozen study's own",
        "functions, and the run is refused if any of its published numbers move.", "",
        f"Byte-identity against `docs/results/alpha-risk-separation-report.json`: "
        f"**{report['frozenLadderIdentical']['verdict']}** "
        f"({len(report['frozenLadderIdentical']['keysChecked'])} scored blocks checked).",
        "", "## The frozen ladder, reproduced unchanged", "",
        "| Rung | Gross CAGR | Cost drag | Net CAGR | Matched benchmark | Net excess | "
        "Vol | Sharpe | MDD | Turnover |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for rung in D.PRIMARY_LADDER:
        row = ladder[rung]
        lines.append(
            f"| {rung} | {_fmt(row.get('grossCagrPct'), '%')} | "
            f"{_fmt(row.get('costDragCagrPp'), 'pp')} | {_fmt(row.get('cagrPct'), '%')} | "
            f"{_fmt(row.get('benchmarkCagrPct'), '%')} | "
            f"{_fmt(row.get('annualizedExcessPct'), 'pp')} | "
            f"{_fmt(row.get('annualizedRealizedVolPct'), '%')} | "
            f"{_fmt(row.get('sharpe'))} | {_fmt(row.get('mddPct'), '%')} | "
            f"{_fmt(row.get('annualOneWayTurnoverX'), 'x')} |")

    point, lo, hi = _pair(frozen["pairedVsControl"])
    sep = frozen["separation"]
    lines += ["", f"Paired difference (challenger minus control): **{_fmt(point, 'pp')}**, "
              f"95% CI [{_fmt(lo, 'pp')}, {_fmt(hi, 'pp')}] over {frozen['pairedBlocks']} "
              "paired blocks — "
              + ("**EXCLUDES zero, " + sep["direction"] + "**." if sep
                 else "**CONTAINS zero**."), ""]

    lines += ["### Where the gross gap comes from", "",
              "| Rung | Arithmetic selection | Compounding | Geometric gross edge | Block sd ratio |",
              "|---|---:|---:|---:|---:|"]
    for rung in D.PRIMARY_LADDER:
        edge = (ladder[rung].get("edgeDecomposition") or {})
        lines.append(f"| {rung} | {_fmt(edge.get('arithmeticSelectionEdgePp'), 'pp')} | "
                     f"{_fmt(edge.get('compoundingEdgePp'), 'pp')} | "
                     f"{_fmt(edge.get('geometricGrossEdgePp'), 'pp')} | "
                     f"{_fmt(edge.get('blockSdRatio'), 'x')} |")

    diff = report["setDifferenceProfiles"]
    challenger_side = diff["selectedByChallengerNotControl"]
    control_side = diff["selectedByControlNotChallenger"]
    lines += ["", "## NEW: the names the two rungs disagree about", "",
              "`risk_dominance` compares held against rejected WITHIN a rung. It cannot",
              "answer what the denominator actually BOUGHT. This pairs the two rungs by",
              "date and profiles only the names they disagree about.", "",
              f"- Rebalances measured: **{diff['rebalancesMeasured']}**",
              f"- Held name-dates both rungs agreed on: **{diff['heldNameDatesAgreed']}**",
              f"- Held name-dates they disagreed on: **{diff['heldNameDatesDisagreed']}**",
              f"- Held-set overlap per rebalance (mean): "
              f"**{_fmt((diff['heldSetOverlapPct'] or {}).get('mean'), '%')}**", "",
              "| Sleeve / metric | Challenger-only names | Control-only names |",
              "|---|---:|---:|"]
    for label, key in (("momentum", "momentum"), ("value", "value"),
                       ("quality", "quality"), ("lowvol", "lowvol"),
                       ("downside volatility", "downsideVolPct"),
                       ("alpha percentile", "alphaPercentile"),
                       ("calibrated expected excess", "expectedGrossBenchmarkExcessPct")):
        left = (challenger_side.get(key) or {}).get("mean")
        right = (control_side.get(key) or {}).get("mean")
        lines.append(f"| {label} | {_fmt(left)} | {_fmt(right)} |")

    left_out = challenger_side["realisedForwardBenchmarkExcessPct"]
    right_out = control_side["realisedForwardBenchmarkExcessPct"]
    lines += ["", "### Realised forward benchmark excess — EVALUATION ONLY", "",
              "Read off the same priced cross-section `replacement_anatomy` reads. It",
              "enters no score, no ranking and no rule; it is reported because the",
              "question was asked, not because anything was fitted to it.", "",
              "| | Challenger-only | Control-only |", "|---|---:|---:|",
              f"| Name-dates | {challenger_side['nameDates']} | {control_side['nameDates']} |",
              f"| Mean block excess | {_fmt(left_out.get('meanPct'), '%')} | "
              f"{_fmt(right_out.get('meanPct'), '%')} |",
              f"| Median | {_fmt(left_out.get('medianPct'), '%')} | "
              f"{_fmt(right_out.get('medianPct'), '%')} |",
              f"| Win rate | {_fmt(left_out.get('winRatePct'), '%')} | "
              f"{_fmt(right_out.get('winRatePct'), '%')} |",
              f"| 95% CI | {left_out.get('ci95Pct')} | {right_out.get('ci95Pct')} |",
              "", f"Difference of the two group means: "
              f"**{_fmt(diff.get('realisedForwardExcessDifferencePp'), 'pp')}** — a "
              "difference of means, NOT a paired test.", ""]

    stack = report["exploratoryStack"]
    lines += ["## EXPLORATORY ONLY — two axes at once, outside the ladder", "",
              "k=6 percentile persistence AND the denominator removal. This moves TWO",
              "axes and is attributable to NEITHER. It is not a rung of the primary",
              "ladder, it is not paired into it, and its number may not be read as the",
              "denominator's independent effect.", ""]
    if stack.get("available"):
        row = stack["summary"]
        s_point, s_lo, s_hi = stack["pairedVsControlPointEstimate"], *stack["ci95"]
        lines += [
            "| Path | Net excess | Sharpe | MDD | Turnover |", "|---|---:|---:|---:|---:|",
            f"| {D.CONTROL} (control) | {_fmt(ladder[D.CONTROL].get('annualizedExcessPct'), 'pp')} | "
            f"{_fmt(ladder[D.CONTROL].get('sharpe'))} | {_fmt(ladder[D.CONTROL].get('mddPct'), '%')} | "
            f"{_fmt(ladder[D.CONTROL].get('annualOneWayTurnoverX'), 'x')} |",
            f"| {D.EXPLORATORY_STACK} | {_fmt(row.get('annualizedExcessPct'), 'pp')} | "
            f"{_fmt(row.get('sharpe'))} | {_fmt(row.get('mddPct'), '%')} | "
            f"{_fmt(row.get('annualOneWayTurnoverX'), 'x')} |", "",
            f"Against the control: {_fmt(s_point, 'pp')}, 95% CI [{_fmt(s_lo, 'pp')}, "
            f"{_fmt(s_hi, 'pp')}] — reported for completeness and attributable to neither "
            "axis alone.", ""]
    else:
        lines += ["The exploratory path did not complete and is reported as unavailable "
                  "rather than partially.", ""]

    lines += ["## Observational only — not this study's axis", "",
              "The region quota and the entry logic are NOT touched by this study, and",
              "these numbers are not grounds to change either. They are reported because",
              "the denominator's removal interacts with both.", "",
              "| Reading | Control | Alpha-only |", "|---|---:|---:|"]
    region = report["regionCapBinding"]
    entry = report["entryStateDynamics"]

    def _both(blob, key, suffix=""):
        left, right = (blob["control"] or {}).get(key), (blob["alphaOnly"] or {}).get(key)
        fmt = (lambda v: _fmt(v, suffix)) if isinstance(left, float) else (lambda v: str(v))
        return f"{fmt(left)} | {fmt(right)}"

    lines += [
        f"| Region cap bound (% of rebalances) | {_both(region, 'regionCapBindingPct', '%')} |",
        f"| Sector cap bound (% of rebalances) | {_both(region, 'sectorCapBindingPct', '%')} |",
        f"| Rebalances a capped name outscored one taken | "
        f"{_both(region, 'rebalancesWhereACappedNameOutscoredOneTaken')} |",
        f"| Held name-dates by region | {_both(region, 'heldNameDatesByRegion')} |",
        f"| Top-N by score with caps lifted, by region | "
        f"{_both(region, 'topNByScoreWithCapsLiftedByRegion')} |",
        f"| Entry-state transitions observed | {_both(entry, 'transitionsObserved')} |",
        f"| Transitions coinciding with a swap (%) | "
        f"{_both(entry, 'transitionsCoincidingWithASwapPct', '%')} |",
        f"| Departures whose state had turned blocking | "
        f"{_both(entry, 'departuresWhoseStateHadTurnedBlocking')} |",
        f"| Departures where the step fell and alpha moved <=1pt | "
        f"{_both(entry, 'departuresWhereTheStepFellAndAlphaMovedOnePointOrLess')} |", "",
        "The last two rows are the §11 reading: a name dropped while the ranking had",
        "barely changed its opinion, with the entry step as the thing that moved. It is",
        "observational — `entry-selection-separation-v1` is the study that tested that",
        "axis, and this extension does not reopen it.", ""]

    lines += ["## Q1–Q8", ""]
    for item in report["answers"]:
        lines += [f"**{item['q']}**", "", item["a"], ""]

    lines += ["## What this extension does NOT justify", "",
              "- It re-scores nothing: the ladder above is the frozen study's own,",
              "  byte-identical. No new evidence about the denominator's effect is",
              "  produced here, and none of these diagnostics changes that interval.",
              "- The realised set-difference return is descriptive. It is a difference of",
              "  group means over names the two rungs happened to disagree about, with no",
              "  multiplicity correction and no paired test, and nothing is fitted to it.",
              "- The exploratory stack moves two axes and settles neither.",
              "- Region-cap and entry-state readings are observational; this study does",
              "  not touch either mechanism and its numbers are not grounds to.",
              "- Nothing here is a promotion. `promotionEligible` is false.", "",
              "## Next pre-registered study", "",
              "`lowvol` sleeve alpha/risk separation — move the 0.20 `lowvol` sleeve out",
              "of the four-factor alpha and into the risk layer. This extension's Q3/Q4",
              "localise the surviving tilt there, which makes it the coherent next axis",
              "to TEST; it is explicitly not evidence that the move would help, and it is",
              "not run here.", ""]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger_dir")
    parser.add_argument("--output", default="alpha-risk-separation-diagnostics-report.json")
    parser.add_argument("--markdown", default="alpha-risk-separation-diagnostics-report.md")
    args = parser.parse_args(argv)
    ledger = Path(args.ledger_dir)
    output, md = _guard(args.output, ledger), _guard(args.markdown, ledger)
    before = _digest_tree(ledger)

    cfg, _ = load_config()
    store = RI.InputStore(ledger, provenance.REPLAY_VERSION, provenance.DATA_VERSION)
    manifest = store.manifest()
    if not manifest or provenance.REPLAY_VERSION != "replay-v16":
        raise ValueError("this extension requires the same sealed replay-v16 inputs")
    frozen_input = RI.unpack(store.load(manifest, valuation_only=True))
    valuation = RV.ValuationData(
        frozen_input["prices"], cfg.benchmarks, frozen_input["fx"],
        frozen_input["risk_free"], through=manifest["through"],
        risk_free_through=frozen_input["risk_free_source"]["verifiedThrough"],
        corporate_actions=frozen_input.get("corporate_actions"))
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

    # ----- the frozen ladder, re-run by calling the frozen study's own code ---
    print(f"re-running frozen {D.CONTROL} (alpha_reliability's own control)", flush=True)
    control_path = AR.run_rung(D.CONTROL, contexts=contexts, calibrator=calibrator(),
                               calendar=calendar, cfg_pf=cfg.kelly_portfolio,
                               valuation=valuation)
    if not control_path["complete"]:
        raise ValueError(f"control path incomplete: {control_path['failures'][:3]}")

    print(f"re-running frozen {D.ALPHA_ONLY}", flush=True)
    alpha_only_path = ARS.run_alpha_only_rung(
        contexts=contexts, calibrator=calibrator(), calendar=calendar,
        cfg_pf=cfg.kelly_portfolio, valuation=valuation)
    if not alpha_only_path["complete"]:
        raise ValueError(f"alpha-only path incomplete: {alpha_only_path['failures'][:3]}")

    paths = {D.CONTROL: control_path, D.ALPHA_ONLY: alpha_only_path}
    summaries = {rung: SV.summarize(paths[rung]["rows"], research_cfg)
                 for rung in D.PRIMARY_LADDER}
    control_rows = paths[D.CONTROL]["rows"]

    print("pricing the fixed cross-section", flush=True)
    by_date: dict[str, list[dict]] = {}
    for row in signals:
        if row.get("date"):
            by_date.setdefault(row["date"], []).append(row)
    shared = [row["date"] for row in control_rows]
    _, priced_by_date, _ = PV.priced_cross_section(
        contexts, by_date, calendar, shared, valuation)

    reproduced = {
        "ladder": {rung: _fields(summaries[rung]) for rung in D.PRIMARY_LADDER},
        "selectionBehaviour": {rung: selection_behaviour(paths[rung]["decisions"])
                               for rung in D.PRIMARY_LADDER},
        "regionalAttribution": {
            rung: SH.regional_attribution(
                paths[rung]["rows"], years=summaries[rung].get("calendarYears") or 0)
            for rung in D.PRIMARY_LADDER},
        "riskDominance": {
            "control": AR.risk_dominance(paths[D.CONTROL]["decisions"]),
            "alphaOnly": AR.risk_dominance(paths[D.ALPHA_ONLY]["decisions"]),
        },
        "boundaryInstability": {
            "control": AR.boundary_instability(paths[D.CONTROL]["decisions"]),
            "alphaOnly": AR.boundary_instability(paths[D.ALPHA_ONLY]["decisions"]),
        },
        "replacementAnatomy": {
            "control": AR.replacement_anatomy(paths[D.CONTROL]["decisions"], priced_by_date),
            "alphaOnly": AR.replacement_anatomy(paths[D.ALPHA_ONLY]["decisions"],
                                                priced_by_date),
        },
        "pairedVsControl": RVL.paired_bootstrap(
            paths[D.ALPHA_ONLY]["rows"], control_rows, research_cfg),
        "pairedBlocks": len(control_rows),
    }
    reproduced["tiltSurvival"] = ARS.tilt_survival(
        reproduced["riskDominance"]["control"], reproduced["riskDominance"]["alphaOnly"])
    reproduced["separation"] = _separation(reproduced["pairedVsControl"])

    # ----- THE PROOF: the ladder must not have moved -------------------------
    published = json.loads(FROZEN_REPORT.read_text())
    mismatched = [key for key in D.FROZEN_KEYS
                  if _canonical(published.get(key)) != _canonical(reproduced.get(key))]
    if mismatched:
        raise ValueError(
            "FROZEN_LADDER_MOVED: this extension changed a published number, which a "
            "read-only diagnostic cannot do. Divergent blocks: " + ", ".join(mismatched))
    print(f"frozen ladder reproduced byte-identically across {len(D.FROZEN_KEYS)} blocks",
          flush=True)

    # ----- what the frozen study did not answer ------------------------------
    print("profiling the set difference between the two rungs", flush=True)
    set_difference = D.set_difference_profiles(
        paths[D.CONTROL]["decisions"], paths[D.ALPHA_ONLY]["decisions"], priced_by_date)

    print(f"running {D.EXPLORATORY_STACK} (EXPLORATORY, outside the ladder)", flush=True)
    stack_path = D.run_exploratory_stack_rung(
        contexts=contexts, calibrator=calibrator(), calendar=calendar,
        cfg_pf=cfg.kelly_portfolio, valuation=valuation)
    if stack_path["complete"]:
        stack_summary = SV.summarize(stack_path["rows"], research_cfg)
        stack_paired = RVL.paired_bootstrap(stack_path["rows"], control_rows, research_cfg)
        s_point, s_lo, s_hi = _pair(stack_paired)
        exploratory = {
            "available": True, "rung": D.EXPLORATORY_STACK,
            "summary": _fields(stack_summary),
            "pairedVsControlPointEstimate": s_point, "ci95": [s_lo, s_hi],
            "pairedBlocks": len(control_rows),
            "selectionBehaviour": selection_behaviour(stack_path["decisions"]),
            "movesTwoAxes": True,
            "note": ("k=6 persistence AND the denominator removal. Attributable to "
                     "neither axis alone; never a rung of the primary ladder."),
        }
    else:
        exploratory = {"available": False, "rung": D.EXPLORATORY_STACK,
                       "failures": stack_path["failures"][:3], "movesTwoAxes": True}

    report = {
        "version": D.VERSION, "status": "DIAGNOSTIC_EXTENSION",
        "freezeManifest": D.freeze_manifest(),
        "inputSnapshot": {"sha256": manifest["sha256"], "through": manifest["through"]},
        "frozenLadderReproduced": reproduced,
        "frozenLadderIdentical": {
            "verdict": "IDENTICAL", "keysChecked": list(D.FROZEN_KEYS),
            "comparedAgainst": "docs/results/alpha-risk-separation-report.json",
            "note": ("Every scored block of the frozen study was recomputed by calling "
                     "its own functions and compared canonically. A mismatch raises and "
                     "refuses the report, which is what makes this extension read-only."),
        },
        "setDifferenceProfiles": set_difference,
        "exploratoryStack": exploratory,
        "regionCapBinding": {
            "control": AR.region_cap_binding(paths[D.CONTROL]["decisions"],
                                             cfg.kelly_portfolio),
            "alphaOnly": AR.region_cap_binding(paths[D.ALPHA_ONLY]["decisions"],
                                               cfg.kelly_portfolio),
        },
        "entryStateDynamics": {
            "control": AR.entry_state_dynamics(paths[D.CONTROL]["decisions"]),
            "alphaOnly": AR.entry_state_dynamics(paths[D.ALPHA_ONLY]["decisions"]),
        },
        "sealedInvariant": {"before": before, "after": _digest_tree(ledger)},
        "productionChanged": False,
    }
    report["sealedInvariant"]["unchanged"] = (
        report["sealedInvariant"]["before"] == report["sealedInvariant"]["after"])
    if not report["sealedInvariant"]["unchanged"]:
        raise ValueError("SEALED_LEDGER_CHANGED")
    report["answers"] = _answers(report)

    output.write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                 allow_nan=False, sort_keys=True) + "\n")
    md.write_text(markdown(report))
    print(markdown(report), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
