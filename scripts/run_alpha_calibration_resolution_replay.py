"""Run the alpha-calibration-resolution ladder, read-only on sealed inputs.

One axis: among candidates the expanding-bucket calibration has already
collapsed to ONE calibrated expected excess (same region, same
`calibrationBucket`), does restoring `alphaPercentile`'s discarded ordinal
information -- while never letting a name cross a DIFFERENT calibration
level -- improve stock selection? Everything else (the four-factor alpha,
the calibration table and its bucket edges, the selection score's downside-
volatility denominator, entry logic, region/sector caps, targetNames=5, cash
floor, inverse-vol sizing, transaction costs, benchmark construction, the
rebalance schedule) is unchanged and IDENTICAL on both rungs.

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

from pipeline import alpha_calibration_resolution as C               # noqa: E402
from pipeline import alpha_reliability as AR                          # noqa: E402
from pipeline import alpha_risk_separation_diagnostics as D           # noqa: E402
from pipeline import benchmark_alpha as BA                            # noqa: E402
from pipeline import historical_store as HS                           # noqa: E402
from pipeline import portfolio_validation as PV                       # noqa: E402
from pipeline import provenance                                       # noqa: E402
from pipeline import regional_validation as RVL                       # noqa: E402
from pipeline import replay_calendar as RC                            # noqa: E402
from pipeline import replay_inputs as RI                              # noqa: E402
from pipeline import replay_valuation as RV                           # noqa: E402
from pipeline import selection_value as SV                            # noqa: E402
from pipeline import switch_hurdle as SH                              # noqa: E402
from pipeline.config import load_config                               # noqa: E402


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
        "averageNamesHeld": round(sum(held) / n, 3),
        "averageRetained": round(sum(retained) / n, 3),
        "averageAdded": round(sum(added) / n, 3),
        "averageReplaced": round(sum(replaced) / n, 3),
        "incumbentRetentionRatePct": (round(kept / (kept + lost) * 100, 2)
                                      if kept + lost else None),
    }


def _verdict(sep) -> str:
    if sep is None:
        return "DIRECTIONAL_BUT_NOT_STATISTICALLY_SEPARATED"
    return ("SEPARATED_IN_FAVORABLE_DIRECTION" if sep["direction"] == "BETTER"
            else "REFUTED_SEPARATED_IN_UNFAVORABLE_DIRECTION")


def _combined_case(report: dict) -> dict:
    """Map the measured outcome onto the pre-specified Case A/B/C grid (section 21).

    The pre-registration named three cases: favourable-and-separated (A),
    doesn't-help (B), and directionally-GOOD-but-uncertain (C). It did not name
    a fourth case -- directionally UNFAVOURABLE but not statistically
    separated -- so that reading is routed to B on point-estimate sign rather
    than stretched to fit C, which would misrepresent a negative point
    estimate as "directionally good."
    """
    sep = report["separation"]
    point = _pair(report["pairedVsControl"])[0]
    stage_b = report["withinCalibrationInformation"]
    concordance = (stage_b["pairwiseConcordance"] or {}).get("higherPercentileRealisedBetterPct")
    near_chance = concordance is not None and 45.0 <= concordance <= 55.0
    concordance_note = (
        f" Stage B's pairwise concordance of {_fmt(concordance, '%')} is near chance, "
        "corroborating this reading: the discarded percentile does not appear to order "
        "forward outcomes even within a tied group." if near_chance else
        f" Stage B's pairwise concordance is {_fmt(concordance, '%')}.")

    if sep and sep["direction"] == "BETTER":
        case = "CASE A — ordinal rescue improves and separates"
        reading = (
            "The ordinal information the calibration discards is shown to carry value "
            "on this sample. `continuous-alpha-calibration-v1` is proposed as the next "
            "study, NOT run here. One sample with no multiplicity correction and no "
            "permutation null is a finding to replicate, not a promotion.")
    elif (sep and sep["direction"] == "WORSE") or (point is not None and point < 0):
        case = "CASE B — ordinal rescue does not help"
        separated_clause = (
            f", separated in the unfavourable direction (95% CI "
            f"[{_fmt(sep['ci95Pp'][0], 'pp')}, {_fmt(sep['ci95Pp'][1], 'pp')}])"
            if sep and sep["direction"] == "WORSE" else
            ", not statistically separated from control (the interval contains zero)")
        reading = (
            f"Point estimate {_fmt(point, 'pp')}{separated_clause}.{concordance_note} "
            "Finer bucketing is unlikely to be the answer either, since the ordinal "
            "information finer bucketing would expose is exactly what was restored "
            "here and tested directly. Research attention moves to alpha signal "
            "discrimination, persistence and entry structure rather than calibration "
            "resolution.")
    else:
        case = "CASE C — directionally suggestive but not statistically separated"
        reading = (
            f"Point estimate {_fmt(point, 'pp')}, favourable but the paired interval "
            f"contains zero.{concordance_note} Before proposing continuous or monotonic "
            "calibration, a prospective or independent-sample validation of this same "
            "axis is the next step, NOT a jump straight to a finer calibration built on "
            "the same historical sample that produced this estimate.")
    return {"case": case, "reading": reading,
            "note": ("Cases A/B/C were specified before the result was seen (section 21 "
                     "of the pre-registration); this maps the measured outcome onto that "
                     "grid on point-estimate sign and statistical separation, and does "
                     "not re-specify the grid itself.")}


def _q6(cascade: dict) -> str:
    total = cascade.get("totalNameDatesChanged") or 0
    if not total:
        return "No name-dates changed between the two rungs; there is nothing to attribute."
    direct = cascade.get("directWithinCalibrationReorder") or 0
    sector = cascade.get("sectorCapCascade") or 0
    region = cascade.get("regionCapCascade") or 0
    other = cascade.get("otherConstraintCascade") or 0
    return (
        f"Of {total} changed name-dates: {direct} ({direct/total*100:.1f}%) are the DIRECT "
        f"within-calibration reorder itself, {sector} ({sector/total*100:.1f}%) are a "
        f"downstream SECTOR-cap cascade the reorder triggered, and {other} are unattributed. "
        f"The region cap is structurally unable to cascade from this axis (a swap only ever "
        f"exchanges two eligible names from the SAME region) and this is measured directly: "
        f"the held set's regional shape differed on {region} of the rebalances that had at "
        f"least one swap.")


def _q9(report: dict) -> str:
    case = report["combinedCase"]["case"]
    fidelity_note = ("Read directly from production/sealed fields "
                     "(alphaPercentile, calibrationBucket, expectedGrossBenchmarkExcessPct) "
                     "with no reconstruction, so this study carries none of "
                     "lowvol-alpha-separation-v1's harness-fidelity gap.")
    return f"{fidelity_note} Combined interpretation: **{case}**."


def _answers(report: dict) -> list[dict]:
    ladder = report["ladder"]
    control, challenger = ladder[C.CONTROL], ladder[C.ORDINAL_RESCUE]
    point, lo, hi = _pair(report["pairedVsControl"])
    sep = report["separation"]
    c_edge = control.get("edgeDecomposition") or {}
    h_edge = challenger.get("edgeDecomposition") or {}
    diff = report["setDifferenceProfiles"]
    new_side = diff["selectedByChallengerNotControl"]
    old_side = diff["selectedByControlNotChallenger"]
    stage_a = report["informationLossDiagnostic"]
    stage_b = report["withinCalibrationInformation"]
    cascade = report["cascadeAttribution"]
    tied_before = report["tiedSwapOrdinalDetail"][C.CONTROL]
    tied_after = report["tiedSwapOrdinalDetail"][C.ORDINAL_RESCUE]
    boundary = report["boundaryInstability"]

    def _m(side, key):
        return (side.get(key) or {}).get("mean")

    return [
        {"q": "Q1. Calibration이 production의 alpha ordering을 얼마나 압축하는가?",
         "a": (f"{stage_a['totalEligibleNameDates']} eligible candidate name-dates fall "
               f"into {stage_a['distinctCalibrationLevels']} distinct (region, bucket) "
               f"levels; the largest single level holds "
               f"{_fmt(stage_a.get('largestLevelShare'), '%')} of them. Within a level, "
               f"alphaPercentile still ranges "
               f"{_fmt((stage_a['withinLevelPercentileRange'] or {}).get('mean'))} points "
               f"(sd {_fmt((stage_a['withinLevelPercentileSd'] or {}).get('mean'))}) on "
               "average — real ordinal spread the calibration throws away.")},
        {"q": "Q2. Tied group 내에서 더 높은 alphaPercentile이 실제 forward excess를 "
              "예측하는가?",
         "a": (f"Pairwise concordance (higher percentile realised better) "
               f"{_fmt((stage_b['pairwiseConcordance'] or {}).get('higherPercentileRealisedBetterPct'), '%')} "
               f"over {(stage_b['pairwiseConcordance'] or {}).get('pairsCompared')} "
               "within-group pairs; mean within-group Spearman "
               f"{_fmt((stage_b['withinGroupSpearman'] or {}).get('mean'))}; top-half minus "
               f"bottom-half (median rank split) forward excess "
               f"{_fmt(stage_b.get('topMinusBottomPp'), 'pp')}. Concordance near 50% and a "
               "near-zero Spearman would mean the discarded percentile is NOT informative "
               "even within a tied group, before the ladder is read at all.")},
        {"q": "Q3. Ordinal rescue가 net benchmark excess를 개선했는가?",
         "a": (f"{_fmt(control.get('annualizedExcessPct'), 'pp')} -> "
               f"{_fmt(challenger.get('annualizedExcessPct'), 'pp')}. Paired difference "
               f"{_fmt(point, 'pp')}, 95% CI [{_fmt(lo, 'pp')}, {_fmt(hi, 'pp')}] over "
               f"{report['pairedBlocks']} blocks. Verdict: **{_verdict(sep)}**.")},
        {"q": "Q4. 그 변화는 arithmetic stock selection 개선인가, volatility/compounding "
              "effect인가?",
         "a": (f"Arithmetic stock selection "
               f"{_fmt(c_edge.get('arithmeticSelectionEdgePp'), 'pp')} -> "
               f"{_fmt(h_edge.get('arithmeticSelectionEdgePp'), 'pp')}; compounding "
               f"{_fmt(c_edge.get('compoundingEdgePp'), 'pp')} -> "
               f"{_fmt(h_edge.get('compoundingEdgePp'), 'pp')}; block sd ratio "
               f"{_fmt(c_edge.get('blockSdRatio'), 'x')} -> "
               f"{_fmt(h_edge.get('blockSdRatio'), 'x')}. This is the primary mechanism "
               "metric in this line of studies.")},
        {"q": "Q5. Control/Challenger가 서로 다르게 선택한 종목들의 특징은 무엇인가?",
         "a": (f"On the {diff['heldNameDatesDisagreed']} disagreed name-dates — "
               f"challenger-only vs control-only: alpha percentile "
               f"{_fmt(_m(new_side,'alphaPercentile'))} vs "
               f"{_fmt(_m(old_side,'alphaPercentile'))}, calibrated expected excess "
               f"{_fmt(_m(new_side,'expectedGrossBenchmarkExcessPct'), 'pp')} vs "
               f"{_fmt(_m(old_side,'expectedGrossBenchmarkExcessPct'), 'pp')} (should be the "
               "SAME level unless cascade explains the gap — see Q6), downside volatility "
               f"{_fmt(_m(new_side,'downsideVolPct'), '%')} vs "
               f"{_fmt(_m(old_side,'downsideVolPct'), '%')}.")},
        {"q": "Q6. 이 결과 중 direct within-calibration reorder와 downstream cascade의 "
              "비중은 어떻게 되는가?",
         "a": _q6(cascade)},
        {"q": "Q7. alpha-reliability-v1이 측정한, calibration에서 tied된 채 손실을 낸 "
              "swap population이 줄어들었는가?",
         "a": (f"Same pairing definition, before vs after the rescue: "
               f"{tied_before.get('swapsMeasured')} tied swaps at "
               f"{_fmt((tied_before['realisedExcessDifferencePct'] or {}).get('mean'), '%')} "
               f"mean arriving-minus-departing excess (control) vs "
               f"{tied_after.get('swapsMeasured')} tied swaps at "
               f"{_fmt((tied_after['realisedExcessDifferencePct'] or {}).get('mean'), '%')} "
               "(rescue rung). `alpha-reliability-v1` published -2.601% on n=39 tied "
               "swaps as its own reference point for this population.")},
        {"q": "Q8. Turnover와 incumbent retention은 어떻게 변했는가?",
         "a": (f"Incumbent retention "
               f"{_fmt(report['selectionBehaviour'][C.CONTROL].get('incumbentRetentionRatePct'), '%')} "
               f"-> {_fmt(report['selectionBehaviour'][C.ORDINAL_RESCUE].get('incumbentRetentionRatePct'), '%')}; "
               f"one-way turnover {_fmt(control.get('annualOneWayTurnoverX'), 'x')} -> "
               f"{_fmt(challenger.get('annualOneWayTurnoverX'), 'x')}; cuts tied on expected "
               f"alpha {_fmt((boundary[C.CONTROL] or {}).get('tiedOnExpectedAlphaPct'), '%')} "
               f"-> {_fmt((boundary[C.ORDINAL_RESCUE] or {}).get('tiedOnExpectedAlphaPct'), '%')} "
               "(this rate is a property of the calibration's bucket edges, which this "
               "axis never touches, so it would be surprising for it to move much).")},
        {"q": "Q9. 이 결과가 continuous-alpha-calibration-v1을 정당화하는가?",
         "a": _q9(report)},
        {"q": "Q10. 현재 bottleneck은 calibration RESOLUTION인가, Alpha DISCRIMINATION "
              "자체인가?",
         "a": _q10_conclusion(stage_b)},
    ]


def _q10_conclusion(stage_b: dict) -> str:
    concordance = (stage_b["pairwiseConcordance"] or {}).get("higherPercentileRealisedBetterPct")
    near_chance = concordance is not None and 45.0 <= concordance <= 55.0
    if near_chance:
        conclusion = (
            "near chance. That points at ALPHA DISCRIMINATION rather than calibration "
            "resolution: the percentile itself does not order forward outcomes even "
            "where the calibration already agrees they are equal, so no amount of "
            "finer bucketing would recover value that is not there.")
    elif concordance is not None and concordance > 55.0:
        conclusion = (
            "materially above chance. That points at RESOLUTION: the information is "
            "there and a finer, monotonic calibration could plausibly use it.")
    elif concordance is not None:
        conclusion = (
            "materially BELOW chance, which is not the reading either hypothesis "
            "predicted and is not evidence for RESOLUTION and warrants independent "
            "replication before any interpretation is drawn from it.")
    else:
        conclusion = "unavailable on this sample."
    return (f"Stage B answers this before the ladder does: pairwise concordance "
            f"(higher percentile realised better) is {_fmt(concordance, '%')}, which is "
            f"{conclusion}")


def markdown(report: dict) -> str:
    ladder = report["ladder"]
    stage_a = report["informationLossDiagnostic"]
    stage_b = report["withinCalibrationInformation"]
    lines = [
        "# Alpha calibration resolution v1", "",
        "> Read-only research CHALLENGER on sealed replay-v16 inputs. The four-factor",
        "> alpha, the calibration table and its bucket edges, the selection score's",
        "> downside-volatility denominator, entry logic, region/sector caps,",
        "> `targetNames = 5`, the cash floor, inverse-vol sizing, transaction costs,",
        "> benchmark construction and the rebalance schedule are unchanged and",
        "> IDENTICAL on both rungs. `promotionEligible: false`, production unchanged.",
        "",
        "## The question", "",
        "Among names the expanding-bucket calibration scores IDENTICALLY (same region,",
        "same `calibrationBucket`, hence the same calibrated expected excess), does the",
        "`alphaPercentile` ordering it discards still carry value — restored WITHOUT",
        "ever letting a name cross a DIFFERENT calibration level?", "",
        "## The one axis", "",
        "| Rung | Ranking |", "|---|---|",
        f"| `{C.CONTROL}` | `alpha_reliability.CONTROL`, called directly |",
        f"| `{C.ORDINAL_RESCUE}` | Same score values at every position; within each "
        "(region, calibrationBucket) group only, the IDENTITY occupying a position is "
        "reassigned by `alphaPercentile` descending |", "",
        "## Stage A — information-loss diagnostic (read before the ladder)", "",
        f"- Total eligible candidate name-dates: **{stage_a['totalEligibleNameDates']}**",
        f"- Distinct (region, calibrationBucket) levels: "
        f"**{stage_a['distinctCalibrationLevels']}**",
        f"- Largest level's share of all eligible name-dates: "
        f"**{_fmt(stage_a.get('largestLevelShare'), '%')}**",
        f"- Within-level alphaPercentile range: mean "
        f"{_fmt((stage_a['withinLevelPercentileRange'] or {}).get('mean'))}, sd "
        f"{_fmt((stage_a['withinLevelPercentileSd'] or {}).get('mean'))}", "",
        "## Stage B — within-calibration information (evaluation only)", "",
        f"- Pairwise concordance (higher percentile realised better): "
        f"**{_fmt((stage_b['pairwiseConcordance'] or {}).get('higherPercentileRealisedBetterPct'), '%')}** "
        f"over {(stage_b['pairwiseConcordance'] or {}).get('pairsCompared')} pairs",
        f"- Mean within-group Spearman (percentile vs forward excess): "
        f"{_fmt((stage_b['withinGroupSpearman'] or {}).get('mean'))}",
        f"- Median-rank half split, top minus bottom forward excess: "
        f"{_fmt(stage_b.get('topMinusBottomPp'), 'pp')}", "",
        "## The ladder", "",
        "| Rung | Gross CAGR | Cost drag | Net CAGR | Benchmark | Net excess | Vol | "
        "Sharpe | MDD | Turnover | Avg cash | Names |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for rung in C.LADDER:
        row = ladder[rung]
        beh = report["selectionBehaviour"][rung]
        lines.append(
            f"| {rung} | {_fmt(row.get('grossCagrPct'), '%')} | "
            f"{_fmt(row.get('costDragCagrPp'), 'pp')} | {_fmt(row.get('cagrPct'), '%')} | "
            f"{_fmt(row.get('benchmarkCagrPct'), '%')} | "
            f"{_fmt(row.get('annualizedExcessPct'), 'pp')} | "
            f"{_fmt(row.get('annualizedRealizedVolPct'), '%')} | "
            f"{_fmt(row.get('sharpe'))} | {_fmt(row.get('mddPct'), '%')} | "
            f"{_fmt(row.get('annualOneWayTurnoverX'), 'x')} | "
            f"{_fmt(row.get('averageCashPct'), '%')} | "
            f"{_fmt(beh.get('averageNamesHeld'))} |")

    point, lo, hi = _pair(report["pairedVsControl"])
    sep = report["separation"]
    lines += ["", f"**Paired difference (ordinal rescue minus control): {_fmt(point, 'pp')}, "
              f"95% CI [{_fmt(lo, 'pp')}, {_fmt(hi, 'pp')}] over "
              f"{report['pairedBlocks']} paired blocks.**", "",
              f"Verdict: **{_verdict(sep)}**", "",
              "### Where the gross gap comes from", "",
              "| Rung | Arithmetic selection | Compounding | Geometric gross edge | Block sd ratio |",
              "|---|---:|---:|---:|---:|"]
    for rung in C.LADDER:
        edge = (ladder[rung].get("edgeDecomposition") or {})
        lines.append(f"| {rung} | {_fmt(edge.get('arithmeticSelectionEdgePp'), 'pp')} | "
                     f"{_fmt(edge.get('compoundingEdgePp'), 'pp')} | "
                     f"{_fmt(edge.get('geometricGrossEdgePp'), 'pp')} | "
                     f"{_fmt(edge.get('blockSdRatio'), 'x')} |")

    diff = report["setDifferenceProfiles"]
    new_side, old_side = (diff["selectedByChallengerNotControl"],
                          diff["selectedByControlNotChallenger"])
    lines += ["", "## Factor profile of the names the rungs disagree about", "",
              f"{diff['rebalancesMeasured']} rebalances; "
              f"{diff['heldNameDatesAgreed']} held name-dates agreed, "
              f"{diff['heldNameDatesDisagreed']} disagreed.", "",
              "| Metric | Challenger-only | Control-only |", "|---|---:|---:|"]
    for label, key in (("alpha percentile", "alphaPercentile"),
                       ("calibrated expected excess", "expectedGrossBenchmarkExcessPct"),
                       ("downside volatility", "downsideVolPct")):
        lines.append(f"| {label} | {_fmt((new_side.get(key) or {}).get('mean'))} | "
                     f"{_fmt((old_side.get(key) or {}).get('mean'))} |")

    lines += ["", "## Cascade attribution", "",
              "| Category | Name-dates |", "|---|---:|"]
    cascade = report["cascadeAttribution"]
    lines += [
        f"| Total changed | {cascade.get('totalNameDatesChanged')} |",
        f"| Direct within-calibration reorder | {cascade.get('directWithinCalibrationReorder')} |",
        f"| Sector cap cascade | {cascade.get('sectorCapCascade')} |",
        f"| Other | {cascade.get('otherConstraintCascade')} |",
        f"| Region cap cascade (rebalances) | {cascade.get('regionCapCascade')} |", ""]

    lines += ["## Boundary diagnostic", "",
              "| Reading | Control | Ordinal rescue |", "|---|---:|---:|"]
    boundary = report["boundaryInstability"]
    lines += [
        f"| Cuts tied on expected alpha | "
        f"{_fmt((boundary[C.CONTROL] or {}).get('tiedOnExpectedAlphaPct'), '%')} | "
        f"{_fmt((boundary[C.ORDINAL_RESCUE] or {}).get('tiedOnExpectedAlphaPct'), '%')} |",
        f"| Incumbent retention | "
        f"{_fmt(report['selectionBehaviour'][C.CONTROL].get('incumbentRetentionRatePct'), '%')} | "
        f"{_fmt(report['selectionBehaviour'][C.ORDINAL_RESCUE].get('incumbentRetentionRatePct'), '%')} |",
        ""]

    lines += ["## Tied-swap population — linkage to alpha-reliability-v1", "",
              "Same pairing definition (weakest arrival vs strongest departure by score,",
              "restricted to swaps tied on calibrated expected alpha), measured before",
              "(control) and after (rescue) the ordinal rescue.", "",
              "| Rung | Swaps measured | Mean realised excess difference |",
              "|---|---:|---:|"]
    for rung in C.LADDER:
        tied = report["tiedSwapOrdinalDetail"][rung]
        lines.append(
            f"| {rung} | {tied.get('swapsMeasured')} | "
            f"{_fmt((tied['realisedExcessDifferencePct'] or {}).get('mean'), '%')} |")

    lines += ["", "## EXPLORATORY stacks — outside the ladder", "",
              "Each row below moves MORE THAN ONE axis and is attributable to NONE of",
              "them individually. None is paired into the primary ladder and none is",
              "the ordinal rescue's independent effect.", "",
              "| Stacked path | Axes moved | Net excess | Arithmetic selection | Sharpe | "
              "MDD | Avg cash | vs control |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for blob in report["exploratoryStacks"]:
        if not blob.get("available"):
            lines.append(f"| {blob['rung']} | {blob.get('axesMoved')} | unavailable | | | | | |")
            continue
        row = blob["summary"]
        edge = (row.get("edgeDecomposition") or {})
        lines.append(
            f"| {blob['rung']} | {blob['axesMoved']} | "
            f"{_fmt(row.get('annualizedExcessPct'), 'pp')} | "
            f"{_fmt(edge.get('arithmeticSelectionEdgePp'), 'pp')} | "
            f"{_fmt(row.get('sharpe'))} | {_fmt(row.get('mddPct'), '%')} | "
            f"{_fmt(row.get('averageCashPct'), '%')} | "
            f"{_fmt(blob.get('pointEstimatePp'), 'pp')} "
            f"[{_fmt((blob.get('ci95Pp') or [None, None])[0], 'pp')}, "
            f"{_fmt((blob.get('ci95Pp') or [None, None])[1], 'pp')}] |")

    lines += ["", f"### Combined interpretation: **{report['combinedCase']['case']}**", "",
              report["combinedCase"]["reading"], ""]

    lines += ["## Q1–Q10", ""]
    for item in report["answers"]:
        lines += [f"**{item['q']}**", "", item["a"], ""]

    lines += ["## What this study does NOT establish", "",
              "- Not a promotion. `promotionEligible` is false and no permutation null",
              "  was run, so no rung here may be described as beating random.",
              "- Forward-return and Stage B readings are evaluation-only, fitted to",
              "  nothing, with no multiplicity correction.",
              "- Every stacked path moves more than one axis and settles none of them.",
              "- One historical sample, after ten studies on this ledger.",
              "- No bucket-count sweep, no percentile-coefficient optimisation, no",
              "  isotonic or spline fit, no threshold search — one binary mechanistic",
              "  test, specified before the result.", "",
              "## Next research (proposed, NOT run here)", "",
              "1. If Case A: `continuous-alpha-calibration-v1` — a monotonic calibration",
              "   replacing the discrete bucket edges, on an INDEPENDENT sample.",
              "2. If Case B: redirect toward alpha signal discrimination, persistence",
              "   and entry structure rather than calibration resolution.",
              "3. If Case C: a prospective or independent-sample validation of this same",
              "   axis before any finer calibration is attempted.",
              "4. Sealed ledgers should ideally store more production-computed",
              "   intermediate fields (sleeve z-scores, rawAlpha, evidence-adjusted",
              "   alpha) — proposed, not executed here; no historical ledger was",
              "   regenerated and no production code changed.", ""]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger_dir")
    parser.add_argument("--output", default="alpha-calibration-resolution-report.json")
    parser.add_argument("--markdown", default="alpha-calibration-resolution-report.md")
    parser.add_argument("--skip-exploratory", action="store_true",
                        help="primary ladder only; the stacks are explicitly optional")
    args = parser.parse_args(argv)
    ledger = Path(args.ledger_dir)
    output, md = _guard(args.output, ledger), _guard(args.markdown, ledger)
    before = _digest_tree(ledger)

    cfg, _ = load_config()
    store = RI.InputStore(ledger, provenance.REPLAY_VERSION, provenance.DATA_VERSION)
    manifest = store.manifest()
    if not manifest or provenance.REPLAY_VERSION != "replay-v16":
        raise ValueError("alpha-calibration-resolution-v1 requires sealed replay-v16 inputs")
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

    print(f"running {C.CONTROL} on {len(calendar)} blocks", flush=True)
    control_path = AR.run_rung(C.CONTROL, contexts=contexts, calibrator=calibrator(),
                               calendar=calendar, cfg_pf=cfg.kelly_portfolio,
                               valuation=valuation)
    if not control_path["complete"]:
        raise ValueError(f"{C.CONTROL} path incomplete: {control_path['failures'][:3]}")

    print(f"running {C.ORDINAL_RESCUE} on {len(calendar)} blocks", flush=True)
    rescue_path = C.run_rescue_rung(contexts=contexts, calibrator=calibrator(),
                                    calendar=calendar, cfg_pf=cfg.kelly_portfolio,
                                    valuation=valuation)
    if not rescue_path["complete"]:
        raise ValueError(f"{C.ORDINAL_RESCUE} path incomplete: {rescue_path['failures'][:3]}")

    print("verifying noop blocks reproduce control exactly", flush=True)
    C.assert_noop_blocks_match_control(control_path["decisions"], rescue_path["decisions"])

    paths = {C.CONTROL: control_path, C.ORDINAL_RESCUE: rescue_path}
    summaries = {rung: SV.summarize(paths[rung]["rows"], research_cfg) for rung in C.LADDER}
    control_rows = control_path["rows"]

    print("pricing the fixed cross-section", flush=True)
    by_date: dict[str, list[dict]] = {}
    for row in signals:
        if row.get("date"):
            by_date.setdefault(row["date"], []).append(row)
    shared = [row["date"] for row in control_rows]
    _, priced_by_date, _ = PV.priced_cross_section(
        contexts, by_date, calendar, shared, valuation)

    exploratory = []
    if not args.skip_exploratory:
        for persistence, entry_at_weight in ((True, False), (False, True), (True, True)):
            label = C.exploratory_label(persistence=persistence,
                                        entry_at_weight=entry_at_weight)
            print(f"running {label} (EXPLORATORY, outside the ladder)", flush=True)
            stack = C.run_exploratory_stack_rung(
                contexts=contexts, calibrator=calibrator(), calendar=calendar,
                cfg_pf=cfg.kelly_portfolio, valuation=valuation,
                persistence=persistence, entry_at_weight=entry_at_weight)
            if not stack["complete"]:
                exploratory.append({"rung": label, "available": False,
                                    "axesMoved": stack["axesMoved"],
                                    "failures": stack["failures"][:3]})
                continue
            stack_summary = SV.summarize(stack["rows"], research_cfg)
            paired = RVL.paired_bootstrap(stack["rows"], control_rows, research_cfg)
            s_point, s_lo, s_hi = _pair(paired)
            exploratory.append({
                "rung": label, "available": True, "axesMoved": stack["axesMoved"],
                "summary": _fields(stack_summary),
                "pointEstimatePp": s_point, "ci95Pp": [s_lo, s_hi],
                "selectionBehaviour": selection_behaviour(stack["decisions"]),
                "note": ("Moves more than one axis; attributable to none of them "
                         "individually and never paired into the primary ladder."),
            })

    report = {
        "version": C.VERSION, "status": "CHALLENGER",
        "freezeManifest": C.freeze_manifest(),
        "inputSnapshot": {"sha256": manifest["sha256"], "through": manifest["through"]},
        "ladder": {rung: _fields(summaries[rung]) for rung in C.LADDER},
        "selectionBehaviour": {rung: selection_behaviour(paths[rung]["decisions"])
                               for rung in C.LADDER},
        "regionalAttribution": {
            rung: SH.regional_attribution(
                paths[rung]["rows"], years=summaries[rung].get("calendarYears") or 0)
            for rung in C.LADDER},
        # Reused unmodified from alpha_reliability, never re-derived.
        "riskDominance": {rung: AR.risk_dominance(paths[rung]["decisions"])
                          for rung in C.LADDER},
        "boundaryInstability": {rung: AR.boundary_instability(paths[rung]["decisions"])
                                for rung in C.LADDER},
        "replacementAnatomy": {
            rung: AR.replacement_anatomy(paths[rung]["decisions"], priced_by_date)
            for rung in C.LADDER},
        "setDifferenceProfiles": D.set_difference_profiles(
            control_path["decisions"], rescue_path["decisions"], priced_by_date),
        "informationLossDiagnostic": C.information_loss_diagnostic(control_path["decisions"]),
        "withinCalibrationInformation": C.within_calibration_information(
            control_path["decisions"], priced_by_date),
        "tiedSwapOrdinalDetail": {
            rung: C.tied_swap_ordinal_detail(paths[rung]["decisions"], priced_by_date)
            for rung in C.LADDER},
        "cascadeAttribution": C.cascade_attribution(
            control_path["decisions"], rescue_path["decisions"]),
        "exploratoryStacks": exploratory,
        "pairedVsControl": RVL.paired_bootstrap(
            rescue_path["rows"], control_rows, research_cfg),
        "pairedBlocks": len(control_rows),
        "sealedInvariant": {"before": before, "after": _digest_tree(ledger)},
        "productionChanged": False,
    }
    report["separation"] = _separation(report["pairedVsControl"])
    report["verdict"] = _verdict(report["separation"])
    report["sealedInvariant"]["unchanged"] = (
        report["sealedInvariant"]["before"] == report["sealedInvariant"]["after"])
    if not report["sealedInvariant"]["unchanged"]:
        raise ValueError("SEALED_LEDGER_CHANGED")
    report["combinedCase"] = _combined_case(report)
    report["answers"] = _answers(report)

    output.write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                 allow_nan=False, sort_keys=True) + "\n")
    md.write_text(markdown(report))
    print(markdown(report), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
