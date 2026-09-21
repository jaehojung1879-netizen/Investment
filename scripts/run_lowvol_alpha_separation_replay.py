"""Run the lowvol-alpha-separation ladder, read-only on sealed inputs.

One axis: whether the `lowvol` sleeve sits inside the four-factor alpha. The
selection score's downside-volatility denominator, inverse-volatility sizing,
the entry multiplier, the research pool, every cap and `evidenceCoverage`
itself are held fixed and identical across both rungs.

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
from pipeline import alpha_risk_separation_diagnostics as D         # noqa: E402
from pipeline import benchmark_alpha as BA                          # noqa: E402
from pipeline import historical_store as HS                         # noqa: E402
from pipeline import lowvol_alpha_separation as L                   # noqa: E402
from pipeline import portfolio_validation as PV                     # noqa: E402
from pipeline import provenance                                     # noqa: E402
from pipeline import regional_validation as RVL                     # noqa: E402
from pipeline import replay_calendar as RC                          # noqa: E402
from pipeline import replay_inputs as RI                            # noqa: E402
from pipeline import replay_valuation as RV                         # noqa: E402
from pipeline import selection_value as SV                          # noqa: E402
from pipeline import switch_hurdle as SH                            # noqa: E402
from pipeline.config import load_config                             # noqa: E402


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


def _answers(report: dict) -> list[dict]:
    ladder = report["ladder"]
    control, challenger = ladder[L.CONTROL], ladder[L.NO_LOWVOL]
    point, lo, hi = _pair(report["pairedVsControl"])
    sep = report["separation"]
    c_edge = control.get("edgeDecomposition") or {}
    h_edge = challenger.get("edgeDecomposition") or {}
    diff = report["setDifferenceProfiles"]
    new_side = diff["selectedByChallengerNotControl"]
    old_side = diff["selectedByControlNotChallenger"]
    shift = report["sectorShift"]["sharePctDelta"]
    boundary = report["boundaryInstability"]
    fidelity = report["harnessFidelity"]

    def _m(side, key):
        return (side.get(key) or {}).get("mean")

    tech = shift.get("Technology")
    top_up = [f"{k} {v:+.2f}pp" for k, v in list(shift.items())[:3]]
    top_down = [f"{k} {v:+.2f}pp" for k, v in list(shift.items())[-3:]]

    return [
        {"q": "Q1. Lowvol sleeve를 alpha에서 제거했을 때 Net benchmark excess는 "
              "어떻게 변했는가?",
         "a": (f"{_fmt(control.get('annualizedExcessPct'), 'pp')} -> "
               f"{_fmt(challenger.get('annualizedExcessPct'), 'pp')}. Paired difference "
               f"{_fmt(point, 'pp')}, 95% CI [{_fmt(lo, 'pp')}, {_fmt(hi, 'pp')}] over "
               f"{report['pairedBlocks']} blocks. Verdict: **{_verdict(sep)}**.")},
        {"q": "Q2. 그 변화는 arithmetic stock selection 개선인가, compounding / "
              "volatility effect인가?",
         "a": (f"Arithmetic stock selection "
               f"{_fmt(c_edge.get('arithmeticSelectionEdgePp'), 'pp')} -> "
               f"{_fmt(h_edge.get('arithmeticSelectionEdgePp'), 'pp')}; compounding "
               f"{_fmt(c_edge.get('compoundingEdgePp'), 'pp')} -> "
               f"{_fmt(h_edge.get('compoundingEdgePp'), 'pp')}; block sd ratio "
               f"{_fmt(c_edge.get('blockSdRatio'), 'x')} -> "
               f"{_fmt(h_edge.get('blockSdRatio'), 'x')}. This is the primary mechanism "
               "metric: it separates picking better names from merely running a "
               "different volatility profile.")},
        {"q": "Q3. Control-only와 Challenger-only 종목의 Momentum / Value / Quality / "
              "Lowvol profile은 어떻게 달라졌는가?",
         "a": (f"On the {diff['heldNameDatesDisagreed']} disagreed name-dates — "
               f"challenger-only vs control-only: momentum {_fmt(_m(new_side,'momentum'))} "
               f"vs {_fmt(_m(old_side,'momentum'))}, value {_fmt(_m(new_side,'value'))} vs "
               f"{_fmt(_m(old_side,'value'))}, quality {_fmt(_m(new_side,'quality'))} vs "
               f"{_fmt(_m(old_side,'quality'))}, lowvol {_fmt(_m(new_side,'lowvol'))} vs "
               f"{_fmt(_m(old_side,'lowvol'))}, downside volatility "
               f"{_fmt(_m(new_side,'downsideVolPct'), '%')} vs "
               f"{_fmt(_m(old_side,'downsideVolPct'), '%')}.")},
        {"q": "Q4. Challenger가 더 많은 high-momentum / high-quality / high-volatility "
              "종목을 선택했는가?",
         "a": _q4(new_side, old_side, _m)},
        {"q": "Q5. Technology 및 growth-sensitive sectors의 selected exposure가 "
              "실제로 증가했는가?",
         "a": (f"Technology share moved "
               f"{('%+.2fpp' % tech) if tech is not None else 'n/a'}. Largest increases: "
               f"{', '.join(top_up)}. Largest decreases: {', '.join(reversed(top_down))}. "
               "A larger technology share DESCRIBES what removing the sleeve did; it is "
               "not evidence that holding more technology is better.")},
        {"q": "Q6. 새로 선택된 종목의 subsequent benchmark-relative return은 기존에 "
              "밀려난 종목보다 나았는가? (descriptive only)",
         "a": (f"Challenger-only names realised "
               f"{_fmt((new_side['realisedForwardBenchmarkExcessPct'] or {}).get('meanPct'), '%')} "
               f"mean forward block excess (win rate "
               f"{_fmt((new_side['realisedForwardBenchmarkExcessPct'] or {}).get('winRatePct'), '%')}, "
               f"n={new_side['nameDates']}) against control-only "
               f"{_fmt((old_side['realisedForwardBenchmarkExcessPct'] or {}).get('meanPct'), '%')} "
               f"(win rate "
               f"{_fmt((old_side['realisedForwardBenchmarkExcessPct'] or {}).get('winRatePct'), '%')}, "
               f"n={old_side['nameDates']}); difference of group means "
               f"{_fmt(diff.get('realisedForwardExcessDifferencePp'), 'pp')}. DESCRIPTIVE "
               "ONLY — a difference of two group means, not a paired test, fitted to "
               "nothing.")},
        {"q": "Q7. Portfolio volatility와 MDD는 얼마나 변했고, 기존 downside-risk "
              "denominator + inverse-vol sizing이 그 위험을 충분히 흡수했는가?",
         "a": (f"Held-name downside volatility is the input risk; portfolio realised "
               f"volatility {_fmt(control.get('annualizedRealizedVolPct'), '%')} -> "
               f"{_fmt(challenger.get('annualizedRealizedVolPct'), '%')}, MDD "
               f"{_fmt(control.get('mddPct'), '%')} -> {_fmt(challenger.get('mddPct'), '%')}, "
               f"Sharpe {_fmt(control.get('sharpe'))} -> {_fmt(challenger.get('sharpe'))}, "
               f"average cash {_fmt(control.get('averageCashPct'), '%')} -> "
               f"{_fmt(challenger.get('averageCashPct'), '%')}. The denominator and "
               "inverse-vol sizing are identical on both rungs, so whatever risk moved "
               "is what they did NOT absorb.")},
        {"q": "Q8. Lowvol sleeve 제거가 top-5 boundary의 tie / instability를 "
              "개선했는가?",
         "a": (f"Cuts tied on expected alpha "
               f"{_fmt((boundary[L.CONTROL] or {}).get('tiedOnExpectedAlphaPct'), '%')} -> "
               f"{_fmt((boundary[L.NO_LOWVOL] or {}).get('tiedOnExpectedAlphaPct'), '%')}; "
               f"median relative score gap at the cut "
               f"{_fmt(((boundary[L.CONTROL] or {}).get('relativeScoreGapAtCut') or {}).get('median'))} -> "
               f"{_fmt(((boundary[L.NO_LOWVOL] or {}).get('relativeScoreGapAtCut') or {}).get('median'))}; "
               f"incumbent retention "
               f"{_fmt(report['selectionBehaviour'][L.CONTROL].get('incumbentRetentionRatePct'), '%')} -> "
               f"{_fmt(report['selectionBehaviour'][L.NO_LOWVOL].get('incumbentRetentionRatePct'), '%')}; "
               f"one-way turnover {_fmt(control.get('annualOneWayTurnoverX'), 'x')} -> "
               f"{_fmt(challenger.get('annualOneWayTurnoverX'), 'x')}. The tie rate is a "
               "property of the CALIBRATION's coarse buckets, which this axis does not "
               "touch, so a large move here would be surprising rather than expected.")},
        {"q": "Q9. 이 결과를 근거로 lowvol을 production alpha에서 제거할 수 있는가?",
         "a": (f"No. Verdict is {_verdict(sep)}, and three separate caveats stack on top "
               f"of it. (1) This harness blends stored sleeve PERCENTILES because the "
               f"sealed ledger has no z-scores, so its own control reproduces the "
               f"published ranking at a rank correlation of only "
               f"{_fmt((fidelity.get('rankCorrelationToPublishedAlphaPercentile') or {}).get('mean'))} "
               "— the ladder is internally consistent but is not the production path. "
               "(2) This is one historical sample with no multiplicity correction, after "
               "nine studies on this ledger. (3) No permutation null was run, so no rung "
               "here may be described as beating random. A single favourable interval "
               "would still not be a promotion, and this one is not even that.")},
        {"q": "Q10. 현재까지 모든 연구를 종합했을 때 가장 유망한 구조는 무엇인가?",
         "a": _q10(report)},
    ]


def _q4(new_side, old_side, mean_of) -> str:
    gaps = {}
    for sleeve in ("momentum", "value", "quality", "lowvol"):
        left, right = mean_of(new_side, sleeve), mean_of(old_side, sleeve)
        gaps[sleeve] = None if left is None or right is None else left - right
    vol_left, vol_right = mean_of(new_side, "downsideVolPct"), mean_of(old_side, "downsideVolPct")
    vol_gap = None if vol_left is None or vol_right is None else vol_left - vol_right
    if gaps["momentum"] is None or vol_gap is None:
        return "The set difference could not be profiled on this sample."
    named = ", ".join(f"{k} {v:+.3f}" for k, v in gaps.items() if v is not None)
    direction = ("MORE" if vol_gap > 0 else "LESS")
    return (
        f"Sleeve gaps (challenger-only minus control-only): {named}; realised downside "
        f"volatility {vol_gap:+.3f}pp. So the names the challenger took are {direction} "
        f"volatile than the ones it dropped"
        + (f", and its momentum edge over them is {gaps['momentum']:+.3f} percentile "
           f"points with quality {gaps['quality']:+.3f}."
           if gaps.get("quality") is not None else ".")
        + " Whether that trade paid is Q6, and whether it paid for a reason this study "
        "tested is Q2 — the profile alone establishes neither.")


def _q10(report: dict) -> str:
    """Rank the programme's paths on mechanism clarity, not on CAGR."""
    rows = [
        ("Current control (four-factor, this harness)",
         report["ladder"][L.CONTROL].get("annualizedExcessPct"),
         (report["ladder"][L.CONTROL].get("edgeDecomposition") or {})
         .get("arithmeticSelectionEdgePp"), "1 (baseline)"),
        ("No-lowvol alpha (this study)",
         report["ladder"][L.NO_LOWVOL].get("annualizedExcessPct"),
         (report["ladder"][L.NO_LOWVOL].get("edgeDecomposition") or {})
         .get("arithmeticSelectionEdgePp"), "1"),
    ]
    for blob in report["exploratoryStacks"]:
        if blob.get("available"):
            rows.append((blob["rung"], (blob["summary"] or {}).get("annualizedExcessPct"),
                         ((blob["summary"] or {}).get("edgeDecomposition") or {})
                         .get("arithmeticSelectionEdgePp"), str(blob["axesMoved"])))
    listed = "; ".join(
        f"{name}: net excess {_fmt(excess, 'pp')}, arithmetic selection "
        f"{_fmt(arith, 'pp')} ({axes} axis/axes)" for name, excess, arith, axes in rows)
    return (
        f"{listed}. Published elsewhere on this same ledger: signal-persistence-v1's k=6 "
        "(favourable point estimate, CI contains zero) and entry-selection-separation-v1 "
        "(+2.069pp, 95% CI [-1.881, +6.061], contains zero, achieved partly by roughly "
        "doubling average cash to 56.0%). RANKING THESE BY CAGR WOULD BE THE WRONG "
        "READING. Every interval this programme has produced contains zero, so no path "
        "is statistically distinguished from the control; the multi-axis rows above are "
        "attributable to none of their axes individually; and the one path with a large "
        "point estimate bought it with a structurally different cash profile rather than "
        "with demonstrably better names. On mechanism clarity the honest summary is that "
        "the single-axis studies have repeatedly failed to separate, which points at the "
        "calibration's two-bucket resolution — named as the bottleneck by "
        "alpha-reliability-v1 — rather than at any of the axes tried since.")


def markdown(report: dict) -> str:
    ladder = report["ladder"]
    fidelity = report["harnessFidelity"]
    lines = [
        "# Lowvol alpha separation v1", "",
        "> Read-only research CHALLENGER on sealed replay-v16 inputs. The selection",
        "> score's downside-volatility denominator, inverse-volatility sizing, the entry",
        "> multiplier, the research pool, every cap and `evidenceCoverage` itself are",
        "> unchanged and IDENTICAL on both rungs. `promotionEligible: false`,",
        "> production unchanged.", "",
        "## The one axis", "",
        "| Rung | Alpha |", "|---|---|",
        f"| `{L.CONTROL}` | {' + '.join(f'{v:g} {k}' for k, v in L.FOUR_FACTOR.items())} |",
        f"| `{L.NO_LOWVOL}` | "
        f"{' + '.join(f'{v:.4g} {k}' for k, v in L.THREE_FACTOR.items())} |", "",
        "The challenger's weights are production's own 30:25:25 renormalized to sum to",
        "one — derived from `longterm.FACTOR_WEIGHTS` at import, not fitted. No weight",
        "sweep was performed.", "",
        "## Read this first: the harness difference", "",
        "Production blends sleeve **z-scores**. The sealed ledger stores only each",
        "sleeve's **percentile**, so production's exact alpha arithmetic is unreachable",
        "from sealed inputs — verified, not assumed. Both rungs therefore blend",
        "percentiles, which keeps the axis between them exactly one thing but means this",
        "harness's control is **not** the published path:", "",
        f"- Rank correlation of this control's `alphaPercentile` to the published one: "
        f"**{_fmt((fidelity.get('rankCorrelationToPublishedAlphaPercentile') or {}).get('mean'))}** "
        f"(median "
        f"{_fmt((fidelity.get('rankCorrelationToPublishedAlphaPercentile') or {}).get('median'))}, "
        f"p10 "
        f"{_fmt((fidelity.get('rankCorrelationToPublishedAlphaPercentile') or {}).get('p10'))}) "
        f"over {fidelity.get('crossSectionsMeasured')} cross-sections",
        f"- Exact percentile match: "
        f"**{_fmt((fidelity.get('exactPercentileMatchPct') or {}).get('mean'), '%')}**", "",
        "Per `switch-hurdle-v1`: a ladder carries its own control, and the control's own",
        "gap to the published path is published beside it. That is this section.", "",
        "## The ladder", "",
        "| Rung | Gross CAGR | Cost drag | Net CAGR | Benchmark | Net excess | Vol | "
        "Sharpe | MDD | Turnover | Avg cash | Names |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for rung in L.LADDER:
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
    lines += ["", f"**Paired difference (no-lowvol minus control): {_fmt(point, 'pp')}, "
              f"95% CI [{_fmt(lo, 'pp')}, {_fmt(hi, 'pp')}] over "
              f"{report['pairedBlocks']} paired blocks.**", "",
              f"Verdict: **{_verdict(sep)}**", "",
              "### Where the gross gap comes from", "",
              "| Rung | Arithmetic selection | Compounding | Geometric gross edge | Block sd ratio |",
              "|---|---:|---:|---:|---:|"]
    for rung in L.LADDER:
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
              "| Sleeve / metric | Challenger-only | Control-only |", "|---|---:|---:|"]
    for label, key in (("momentum", "momentum"), ("value", "value"),
                       ("quality", "quality"), ("lowvol", "lowvol"),
                       ("downside volatility", "downsideVolPct"),
                       ("alpha percentile", "alphaPercentile"),
                       ("calibrated expected excess", "expectedGrossBenchmarkExcessPct")):
        lines.append(f"| {label} | {_fmt((new_side.get(key) or {}).get('mean'))} | "
                     f"{_fmt((old_side.get(key) or {}).get('mean'))} |")

    left_out = new_side["realisedForwardBenchmarkExcessPct"]
    right_out = old_side["realisedForwardBenchmarkExcessPct"]
    lines += ["", "### Realised forward benchmark excess — EVALUATION ONLY", "",
              "| | Challenger-only | Control-only |", "|---|---:|---:|",
              f"| Name-dates | {new_side['nameDates']} | {old_side['nameDates']} |",
              f"| Mean block excess | {_fmt(left_out.get('meanPct'), '%')} | "
              f"{_fmt(right_out.get('meanPct'), '%')} |",
              f"| Win rate | {_fmt(left_out.get('winRatePct'), '%')} | "
              f"{_fmt(right_out.get('winRatePct'), '%')} |",
              f"| 95% CI | {left_out.get('ci95Pct')} | {right_out.get('ci95Pct')} |", "",
              "Fitted to nothing. No rule, score or ranking reads it.", "",
              "## Sector exposure", "",
              "| Sector | Control share | Challenger share | Delta |", "|---|---:|---:|---:|"]
    control_share = report["sectorExposure"][L.CONTROL]["sharePct"]
    challenger_share = report["sectorExposure"][L.NO_LOWVOL]["sharePct"]
    for sector, delta in report["sectorShift"]["sharePctDelta"].items():
        lines.append(f"| {sector} | {_fmt(control_share.get(sector, 0.0), '%')} | "
                     f"{_fmt(challenger_share.get(sector, 0.0), '%')} | {delta:+.2f}pp |")

    lines += ["", "## Boundary diagnostic", "",
              "| Reading | Control | No-lowvol |", "|---|---:|---:|"]
    boundary = report["boundaryInstability"]
    lines += [
        f"| Cuts tied on expected alpha | "
        f"{_fmt((boundary[L.CONTROL] or {}).get('tiedOnExpectedAlphaPct'), '%')} | "
        f"{_fmt((boundary[L.NO_LOWVOL] or {}).get('tiedOnExpectedAlphaPct'), '%')} |",
        f"| Median relative score gap at cut | "
        f"{_fmt(((boundary[L.CONTROL] or {}).get('relativeScoreGapAtCut') or {}).get('median'))} | "
        f"{_fmt(((boundary[L.NO_LOWVOL] or {}).get('relativeScoreGapAtCut') or {}).get('median'))} |",
        f"| Median expected-alpha gap at cut | "
        f"{_fmt(((boundary[L.CONTROL] or {}).get('expectedAlphaGapAtCutPp') or {}).get('median'), 'pp')} | "
        f"{_fmt(((boundary[L.NO_LOWVOL] or {}).get('expectedAlphaGapAtCutPp') or {}).get('median'), 'pp')} |",
        f"| Incumbent retention | "
        f"{_fmt(report['selectionBehaviour'][L.CONTROL].get('incumbentRetentionRatePct'), '%')} | "
        f"{_fmt(report['selectionBehaviour'][L.NO_LOWVOL].get('incumbentRetentionRatePct'), '%')} |",
        ""]

    lines += ["## EXPLORATORY stacks — outside the ladder", "",
              "Each row below moves MORE THAN ONE axis and is attributable to NONE of",
              "them individually. None is paired into the primary ladder and none is",
              "the lowvol sleeve's independent effect.", "",
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
              "- The harness blends percentiles, not the z-scores production blends. The",
              "  ladder is internally consistent; it is not the production path.",
              "- The forward-return and sector readings are descriptive, fitted to",
              "  nothing, with no multiplicity correction.",
              "- Every stacked path moves more than one axis and settles none of them.",
              "- One historical sample, after nine studies on this ledger.", "",
              "## Next research (proposed, NOT run here)", "",
              "1. A clean two-axis study of persistence k=6 + entry-selection separation.",
              "2. Whether a blocking entry state should force an incumbent EXIT at all.",
              "3. A cross-region common expected-return scale.",
              "4. Calibration bucket RESOLUTION — `alpha-reliability-v1` named the",
              "   two-occupied-bucket map as the bottleneck, and four single-axis studies",
              "   have now failed to separate downstream of it.",
              "5. If `lowvol` stays, whether the calibration layer rather than the factor",
              "   definition is what limits it.", ""]
    return "\n".join(lines)


def _combined_case(report: dict) -> dict:
    """Map the measured outcome onto the pre-specified Case A-E grid."""
    sep = report["separation"]
    point = _pair(report["pairedVsControl"])[0]
    control_arith = ((report["ladder"][L.CONTROL].get("edgeDecomposition") or {})
                     .get("arithmeticSelectionEdgePp"))
    challenger_arith = ((report["ladder"][L.NO_LOWVOL].get("edgeDecomposition") or {})
                        .get("arithmeticSelectionEdgePp"))
    arith_up = (control_arith is not None and challenger_arith is not None
                and challenger_arith > control_arith)
    mdd_worse = ((report["ladder"][L.NO_LOWVOL].get("mddPct") or 0)
                 < (report["ladder"][L.CONTROL].get("mddPct") or 0))
    stacks = {b["rung"]: b for b in report["exploratoryStacks"] if b.get("available")}
    persistence_stack = next((b for r, b in stacks.items() if "PERSISTENCE" in r
                              and "ENTRY" not in r), None)
    stack_better = (persistence_stack is not None
                    and (persistence_stack.get("pointEstimatePp") or 0) > 0)

    if sep and sep["direction"] == "BETTER":
        case = "CASE A — no-lowvol alone improves and separates"
        reading = (
            "The lowvol sleeve is shown to suppress stock-selection alpha on this "
            "sample. Even so this is one sample with no multiplicity correction and no "
            "permutation null, so it is a finding to replicate, not a promotion.")
    elif arith_up and mdd_worse:
        case = "CASE E — arithmetic selection improves while drawdown worsens"
        reading = (
            f"Arithmetic stock selection moves {_fmt(control_arith, 'pp')} -> "
            f"{_fmt(challenger_arith, 'pp')} while MDD deepens. Whether risk SIZING can "
            "absorb the incremental risk is a separate study, and this result is not "
            "permission to run the sleeve removal in production meanwhile — the paired "
            "interval on net excess still does not separate.")
    elif not arith_up and stack_better:
        case = "CASE B — no-lowvol alone does not pay, the persistence stack looks better"
        reading = (
            "Removing the sleeve alone does not improve selection, but the stacked path "
            "with k=6 persistence lands higher. That is an INTERACTION HYPOTHESIS only: "
            "the stack moves two axes and is attributable to neither, so it is a reason "
            "to design a clean two-axis study, not to conclude anything about the "
            "sleeve.")
    else:
        case = "CASE D — keep the lowvol sleeve for now"
        reading = (
            f"Net excess moves {_fmt(point, 'pp')} and the paired interval contains "
            "zero, arithmetic stock selection does not improve, and no stacked path "
            "changes that reading in a way attributable to this axis. The sleeve is not "
            "shown to be suppressing selection alpha. Research attention belongs on "
            "signal persistence and role separation, and above all on the calibration "
            "resolution `alpha-reliability-v1` named as the bottleneck.")
    return {"case": case, "reading": reading,
            "arithmeticSelectionImproved": arith_up, "mddWorsened": mdd_worse,
            "note": ("Cases were specified before the result was seen; this maps the "
                     "measured outcome onto that grid and does not re-specify it.")}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger_dir")
    parser.add_argument("--output", default="lowvol-alpha-separation-report.json")
    parser.add_argument("--markdown", default="lowvol-alpha-separation-report.md")
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
        raise ValueError("lowvol-alpha-separation-v1 requires sealed replay-v16 inputs")
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

    print("rebuilding alpha percentiles under both sleeve sets", flush=True)
    percentiles = {rung: L.rebuild_percentiles(signals, rung) for rung in L.LADDER}

    paths = {}
    for rung in L.LADDER:
        print(f"running {rung} on {len(calendar)} blocks", flush=True)
        path = L.run_rung(rung, contexts=contexts, percentiles=percentiles[rung],
                          calibrator=calibrator(), calendar=calendar,
                          cfg_pf=cfg.kelly_portfolio, valuation=valuation)
        if not path["complete"]:
            raise ValueError(f"{rung} path incomplete: {path['failures'][:3]}")
        paths[rung] = path

    summaries = {rung: SV.summarize(paths[rung]["rows"], research_cfg) for rung in L.LADDER}
    control_rows = paths[L.CONTROL]["rows"]

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
            label = L.exploratory_label(persistence=persistence,
                                        entry_at_weight=entry_at_weight)
            print(f"running {label} (EXPLORATORY, outside the ladder)", flush=True)
            stack = L.run_exploratory_rung(
                contexts=contexts, percentiles=percentiles[L.NO_LOWVOL],
                calibrator=calibrator(), calendar=calendar,
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

    sector = {rung: L.sector_exposure(paths[rung]["decisions"]) for rung in L.LADDER}
    report = {
        "version": L.VERSION, "status": "CHALLENGER",
        "freezeManifest": L.freeze_manifest(),
        "inputSnapshot": {"sha256": manifest["sha256"], "through": manifest["through"]},
        "harnessFidelity": L.harness_fidelity(signals, percentiles[L.CONTROL]),
        "ladder": {rung: _fields(summaries[rung]) for rung in L.LADDER},
        "selectionBehaviour": {rung: selection_behaviour(paths[rung]["decisions"])
                               for rung in L.LADDER},
        "regionalAttribution": {
            rung: SH.regional_attribution(
                paths[rung]["rows"], years=summaries[rung].get("calendarYears") or 0)
            for rung in L.LADDER},
        # Reused unmodified from the studies that built them, never re-derived.
        "riskDominance": {rung: AR.risk_dominance(paths[rung]["decisions"])
                          for rung in L.LADDER},
        "boundaryInstability": {rung: AR.boundary_instability(paths[rung]["decisions"])
                                for rung in L.LADDER},
        "replacementAnatomy": {
            rung: AR.replacement_anatomy(paths[rung]["decisions"], priced_by_date)
            for rung in L.LADDER},
        "setDifferenceProfiles": D.set_difference_profiles(
            paths[L.CONTROL]["decisions"], paths[L.NO_LOWVOL]["decisions"], priced_by_date),
        "sectorExposure": sector,
        "sectorShift": L.sector_shift(sector[L.CONTROL], sector[L.NO_LOWVOL]),
        "exploratoryStacks": exploratory,
        "pairedVsControl": RVL.paired_bootstrap(
            paths[L.NO_LOWVOL]["rows"], control_rows, research_cfg),
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
