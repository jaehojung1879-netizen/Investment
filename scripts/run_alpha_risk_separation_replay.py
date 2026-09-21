"""Run the alpha-risk-separation ladder, read-only on sealed inputs.

`alpha-reliability-v1` measured that a five-name book is decided at its
margin, where most cuts are between names the calibration scores identically,
and that the risk-and-entry product in the score's denominator is what
decides those cuts — visible as a tilt in what is held. This asks the
pre-registered follow-up directly: remove ONLY that denominator from the
selection ranking, leave the `lowvol` sleeve and inverse-vol sizing exactly as
they are, and measure whether the tilt survives.

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

from pipeline import alpha_reliability as AR              # noqa: E402
from pipeline import alpha_risk_separation as ARS         # noqa: E402
from pipeline import benchmark_alpha as BA                # noqa: E402
from pipeline import historical_store as HS               # noqa: E402
from pipeline import portfolio_validation as PV           # noqa: E402
from pipeline import provenance                           # noqa: E402
from pipeline import regional_validation as RVL           # noqa: E402
from pipeline import replay_calendar as RC                # noqa: E402
from pipeline import replay_inputs as RI                  # noqa: E402
from pipeline import replay_valuation as RV               # noqa: E402
from pipeline import selection_value as SV                # noqa: E402
from pipeline import switch_hurdle as SH                  # noqa: E402
from pipeline.config import load_config                   # noqa: E402


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

    `alpha-reliability-v1` found that reading separation as "the lower bound
    cleared zero" hides a downside separation. Both directions are reported.
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


def markdown(report: dict) -> str:
    lines = [
        "# Alpha risk separation v1", "",
        "> Read-only research CHALLENGER on sealed replay-v16 inputs. No factor is",
        "> added, the `lowvol` sleeve weight and inverse-vol sizing are unchanged, no",
        "> selector is promoted and production is unchanged.", "",
        "## The question", "",
        "`alpha-reliability-v1` measured a score/calibrated-alpha rank correlation of",
        "0.758 against 0.075 with downside volatility across the whole cross-section —",
        "alpha orders most pairs — but 86.71% of top-5 cuts are between names the",
        "calibration scores IDENTICALLY, where what remains ordering the cut is the",
        "risk-and-entry product in the score's denominator. This removes ONLY that",
        "denominator from the selection ranking and asks whether the defensive tilt",
        "measured there survives.", "",
        "## The axis", "",
        "| Rung | Score formula |", "|---|---|",
        f"| `{ARS.CONTROL}` | calibrated alpha / (downside vol x 100) x entry multiplier |",
        f"| `{ARS.ALPHA_ONLY}` | calibrated alpha x entry multiplier |", "",
        "The control is `alpha_reliability.run_rung(alpha_reliability.CONTROL, ...)`",
        "called directly — not reproduced — so there is no second implementation of it",
        "to drift from the first. `DOWNSIDE_RISK_UNAVAILABLE` still excludes a name on",
        "both rungs: sizing needs a risk unit whatever the ranking divides by.", "",
        "## The ladder", "",
        "| Rung | Gross CAGR | Cost drag | Net CAGR | Matched benchmark | Net excess | "
        "Vol | Sharpe | MDD | Turnover |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for rung in ARS.LADDER:
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
    for rung in ARS.LADDER:
        edge = (report["ladder"][rung].get("edgeDecomposition") or {})
        lines.append(f"| {rung} | {_fmt(edge.get('arithmeticSelectionEdgePp'), 'pp')} | "
                     f"{_fmt(edge.get('compoundingEdgePp'), 'pp')} | "
                     f"{_fmt(edge.get('geometricGrossEdgePp'), 'pp')} | "
                     f"{_fmt(edge.get('blockSdRatio'), 'x')} |")

    lines += ["", "### Turnover and selection behaviour", "",
              "| Rung | One-way turnover | Name share | Names held | Incumbent retention |",
              "|---|---:|---:|---:|---:|"]
    for rung in ARS.LADDER:
        turn = (report["ladder"][rung].get("turnoverDecomposition") or {})
        beh = report["selectionBehaviour"][rung]
        lines.append(f"| {rung} | {_fmt(turn.get('averageOneWayTurnoverPct'), '%')} | "
                     f"{_fmt(turn.get('nameReplacementSharePct'), '%')} | "
                     f"{_fmt(beh.get('averageNamesHeld'))} | "
                     f"{_fmt(beh.get('incumbentRetentionRatePct'), '%')} |")

    lines += ["", "### Regional contribution to gross excess", "",
              "| Rung | US contribution | US 95% CI | KR contribution | KR 95% CI |",
              "|---|---:|---:|---:|---:|"]
    for rung in ARS.LADDER:
        blob = (report["regionalAttribution"][rung].get("byRegion") or {})
        cells = []
        for region in ("US", "KR"):
            entry = blob.get(region) or {}
            ci = entry.get("contributionCi95Pp") or [None, None]
            cells.append(f"{_fmt(entry.get('contributionPpPerYear'), 'pp')}")
            cells.append(f"[{_fmt(ci[0], 'pp')}, {_fmt(ci[1], 'pp')}]")
        lines.append(f"| {rung} | " + " | ".join(cells) + " |")

    point, lo, hi = _pair(report["pairedVsControl"])
    sep = report["separation"]
    lines += ["", "### Paired difference against the control", "",
              f"Δ annualized net excess: **{_fmt(point, 'pp')}**, 95% CI "
              f"[{_fmt(lo, 'pp')}, {_fmt(hi, 'pp')}], over "
              f"{report['pairedBlocks']} paired blocks.", ""]
    if sep:
        lines.append(f"This interval EXCLUDES zero, **{sep['direction']}**.")
    else:
        lines.append("This interval CONTAINS zero.")

    lines += ["", "## Did the defensive tilt survive?", "",
              "`risk_dominance` (`alpha_reliability`) run unmodified on each rung's own",
              "decisions — nothing here re-derives that instrument, it only reads it",
              "twice.", "",
              "| Reading | Control | Alpha-only |", "|---|---:|---:|"]
    rd_c = report["riskDominance"]["control"]
    rd_a = report["riskDominance"]["alphaOnly"]
    for label, key in (
            ("Spearman(score, downside vol)", "scoreVsDownsideVolSpearman"),
            ("Downside vol of names held (%)", "downsideVolPctSelected"),
            ("Downside vol of names rejected (%)", "downsideVolPctRejected"),
            ("`lowvol` sleeve percentile, held", "lowvolSleevePercentileSelected"),
            ("`lowvol` sleeve percentile, rejected", "lowvolSleevePercentileRejected")):
        lines.append(f"| {label} | {_fmt((rd_c.get(key) or {}).get('mean'))} | "
                     f"{_fmt((rd_a.get(key) or {}).get('mean'))} |")
    for label, key in (("`lowvol` is the highest sleeve (%)", "lowvolIsTheHighestSleevePct"),
                       ("`lowvol` is in the top two sleeves (%)",
                        "lowvolIsInTheTopTwoSleevesPct"),
                       ("Held matches an alpha-only top-N (%)",
                        "heldMatchingAlphaOnlyTopNPct")):
        lines.append(f"| {label} | {_fmt(rd_c.get(key))} | {_fmt(rd_a.get(key))} |")

    survival = report["tiltSurvival"]
    lines += ["", f"- Δ downside vol held: **{_fmt(survival.get('downsideVolPctSelectedDelta'), 'pp')}**"
              f" (alpha-only minus control).",
              f"- Δ `lowvol` sleeve percentile held: "
              f"**{_fmt(survival.get('lowvolSleevePercentileSelectedDelta'))}**.",
              f"- Δ `lowvol` is the highest sleeve: "
              f"**{_fmt(survival.get('lowvolIsTheHighestSleevePctDelta'), 'pp')}**.",
              ""]

    bi_c, bi_a = report["boundaryInstability"]["control"], report["boundaryInstability"]["alphaOnly"]
    ra_c, ra_a = report["replacementAnatomy"]["control"], report["replacementAnatomy"]["alphaOnly"]
    lines += ["## Why did turnover move?", "",
              "`boundary_instability` and `replacement_anatomy` (`alpha_reliability`), run",
              "unmodified on each rung's own decisions. The calibration already hands most",
              "of the pool one alpha; removing the score's one continuously-varying term",
              "(downside volatility) can only make ties at the margin MORE common, never",
              "less — this measures whether it did.", "",
              "| Reading | Control | Alpha-only |", "|---|---:|---:|",
              f"| Cuts tied on expected alpha (%) | "
              f"{_fmt(bi_c.get('tiedOnExpectedAlphaPct'), '%')} | "
              f"{_fmt(bi_a.get('tiedOnExpectedAlphaPct'), '%')} |",
              f"| Relative score gap at the cut, median | "
              f"{_fmt((bi_c.get('relativeScoreGapAtCut') or {}).get('median'))} | "
              f"{_fmt((bi_a.get('relativeScoreGapAtCut') or {}).get('median'))} |",
              f"| Swaps tied on expected alpha (%) | "
              f"{_fmt(ra_c.get('tiedOnExpectedAlphaPct'), '%')} | "
              f"{_fmt(ra_a.get('tiedOnExpectedAlphaPct'), '%')} |",
              f"| Held names whose percentile moved ≤1pt and were replaced anyway (%) | "
              f"{_fmt(ra_c.get('ofThoseReplacedPct'), '%')} | "
              f"{_fmt(ra_a.get('ofThoseReplacedPct'), '%')} |", ""]

    finding = report["finding"]
    lines += ["## Reading", "", f"**{finding['verdict']}**", "", finding["summary"], "",
              "### Refuted", ""]
    for item in finding.get("refuted") or ["Nothing was refuted by its own pre-specified test."]:
        lines.append(f"- {item}")
    lines += ["", "### Next direction", "", finding["nextDirection"], "",
              "A rung ending higher than another is a point estimate on sealed history,",
              "after several rungs across five studies, with no multiplicity correction.",
              "It is not evidence to promote a selector.", ""]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger_dir")
    parser.add_argument("--output", default="alpha-risk-separation-report.json")
    parser.add_argument("--markdown", default="alpha-risk-separation-report.md")
    args = parser.parse_args(argv)
    ledger = Path(args.ledger_dir)
    output, md = _guard(args.output, ledger), _guard(args.markdown, ledger)
    before = _digest_tree(ledger)

    cfg, _ = load_config()
    store = RI.InputStore(ledger, provenance.REPLAY_VERSION, provenance.DATA_VERSION)
    manifest = store.manifest()
    if not manifest or provenance.REPLAY_VERSION != "replay-v16":
        raise ValueError("alpha-risk-separation-v1 requires sealed replay-v16 inputs")
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

    print(f"running {ARS.CONTROL} (alpha_reliability's own control, called directly) "
          f"on {len(calendar)} blocks", flush=True)
    control_path = AR.run_rung(ARS.CONTROL, contexts=contexts, calibrator=calibrator(),
                               calendar=calendar, cfg_pf=cfg.kelly_portfolio,
                               valuation=valuation)
    if not control_path["complete"]:
        raise ValueError(f"control path incomplete: {control_path['failures'][:3]}")

    print(f"running {ARS.ALPHA_ONLY} on {len(calendar)} blocks", flush=True)
    alpha_only_path = ARS.run_alpha_only_rung(
        contexts=contexts, calibrator=calibrator(), calendar=calendar,
        cfg_pf=cfg.kelly_portfolio, valuation=valuation)
    if not alpha_only_path["complete"]:
        raise ValueError(f"alpha-only path incomplete: {alpha_only_path['failures'][:3]}")

    paths = {ARS.CONTROL: control_path, ARS.ALPHA_ONLY: alpha_only_path}
    summaries = {rung: SV.summarize(paths[rung]["rows"], research_cfg) for rung in ARS.LADDER}
    control_rows = paths[ARS.CONTROL]["rows"]

    print("pricing the fixed cross-section for the replacement diagnostic", flush=True)
    by_date: dict[str, list[dict]] = {}
    for row in signals:
        if row.get("date"):
            by_date.setdefault(row["date"], []).append(row)
    shared = [row["date"] for row in control_rows]
    _, priced_by_date, _ = PV.priced_cross_section(
        contexts, by_date, calendar, shared, valuation)

    report = {
        "version": ARS.VERSION, "status": "CHALLENGER",
        "freezeManifest": ARS.freeze_manifest(),
        "inputSnapshot": {"sha256": manifest["sha256"], "through": manifest["through"]},
        "ladder": {rung: _fields(summaries[rung]) for rung in ARS.LADDER},
        "selectionBehaviour": {rung: selection_behaviour(paths[rung]["decisions"])
                               for rung in ARS.LADDER},
        "regionalAttribution": {
            rung: SH.regional_attribution(
                paths[rung]["rows"], years=summaries[rung].get("calendarYears") or 0)
            for rung in ARS.LADDER},
        "riskDominance": {
            "control": AR.risk_dominance(paths[ARS.CONTROL]["decisions"]),
            "alphaOnly": AR.risk_dominance(paths[ARS.ALPHA_ONLY]["decisions"]),
        },
        # Reused unmodified, exactly like `riskDominance` above: this explains
        # a turnover change if one appears, rather than leaving it unexplained.
        # `expectedAlphaGapAtCutPp`/`tiedOnExpectedAlphaPct` measure how often
        # the calibration cannot tell the marginal held name from the first
        # excluded one — a quantity that can only get WORSE when the score's
        # one continuously-varying term (downside volatility) is removed,
        # since the calibration already hands most of the pool one alpha.
        "boundaryInstability": {
            "control": AR.boundary_instability(paths[ARS.CONTROL]["decisions"]),
            "alphaOnly": AR.boundary_instability(paths[ARS.ALPHA_ONLY]["decisions"]),
        },
        "replacementAnatomy": {
            "control": AR.replacement_anatomy(paths[ARS.CONTROL]["decisions"], priced_by_date),
            "alphaOnly": AR.replacement_anatomy(paths[ARS.ALPHA_ONLY]["decisions"],
                                                priced_by_date),
        },
        "pairedVsControl": RVL.paired_bootstrap(
            paths[ARS.ALPHA_ONLY]["rows"], control_rows, research_cfg),
        "pairedBlocks": len(control_rows),
        "sealedInvariant": {"before": before, "after": _digest_tree(ledger)},
        "productionChanged": False,
    }
    report["tiltSurvival"] = ARS.tilt_survival(
        report["riskDominance"]["control"], report["riskDominance"]["alphaOnly"])
    report["separation"] = _separation(report["pairedVsControl"])
    report["sealedInvariant"]["unchanged"] = (
        report["sealedInvariant"]["before"] == report["sealedInvariant"]["after"])
    if not report["sealedInvariant"]["unchanged"]:
        raise ValueError("SEALED_LEDGER_CHANGED")

    control_excess = summaries[ARS.CONTROL].get("annualizedExcessPct")
    challenger_excess = summaries[ARS.ALPHA_ONLY].get("annualizedExcessPct")
    sep = report["separation"]
    refuted = []
    if sep and sep["direction"] == "WORSE":
        refuted.append(
            f"Removing the risk denominator: the paired interval against the control "
            f"EXCLUDES zero in the WORSE direction, {_fmt(sep['pointEstimatePp'], 'pp')}, "
            f"95% CI [{_fmt(sep['ci95Pp'][0], 'pp')}, {_fmt(sep['ci95Pp'][1], 'pp')}]. The "
            "hypothesis that the denominator was purely a source of noise is refuted by "
            "its own pre-specified test.")

    tilt = report["tiltSurvival"]
    survives = (tilt.get("available")
                and (tilt.get("downsideVolPctSelectedDelta") or 0) > -2.0
                and (tilt.get("lowvolIsTheHighestSleevePctDelta") or 0) > -10.0)

    report["finding"] = {
        "verdict": ("BENCHMARK_BEATEN" if (challenger_excess or 0) > 0
                    else "BENCHMARK_NOT_BEATEN"),
        "controlNetExcessPp": control_excess,
        "alphaOnlyNetExcessPp": challenger_excess,
        "separated": bool(sep),
        "separationDirection": (sep or {}).get("direction"),
        "promotionEligible": False,
        "tiltSurvived": survives,
        "refuted": refuted,
        "summary": (
            f"Net excess moves from {_fmt(control_excess, 'pp')} (control, risk in the "
            f"denominator) to {_fmt(challenger_excess, 'pp')} (alpha only). Paired "
            f"difference {_fmt((_pair(report['pairedVsControl'])[0]), 'pp')}, 95% CI "
            f"[{_fmt((_pair(report['pairedVsControl'])[1]), 'pp')}, "
            f"{_fmt((_pair(report['pairedVsControl'])[2]), 'pp')}], which "
            + ("EXCLUDES zero." if sep else "CONTAINS zero.") + " On the defensive-tilt "
            "question named by `alpha-reliability-v1`: downside volatility held moves by "
            f"{_fmt(tilt.get('downsideVolPctSelectedDelta'), 'pp')} and `lowvol` being the "
            f"highest sleeve moves by {_fmt(tilt.get('lowvolIsTheHighestSleevePctDelta'), 'pp')} "
            "when the denominator is removed — "
            + ("the tilt largely SURVIVES, which points at the alpha term (the `lowvol` "
               "sleeve) rather than the ranking denominator, and is the next study's axis."
               if survives else
               "the tilt LARGELY DID NOT SURVIVE, which points at the ranking denominator "
               "as the channel rather than the alpha term.")
            + f" Cuts tied on expected alpha move from "
            f"{_fmt(report['boundaryInstability']['control'].get('tiedOnExpectedAlphaPct'), '%')} "
            f"to {_fmt(report['boundaryInstability']['alphaOnly'].get('tiedOnExpectedAlphaPct'), '%')} "
            "once the one continuously-varying term in the score is removed, which is the "
            "mechanism behind any turnover change measured above."),
        "nextDirection": (
            "If the tilt survives, the open question is whether the `lowvol` sleeve "
            "itself belongs in the alpha layer or the risk layer — that two-risk-channel "
            "move is explicitly out of scope here and belongs to its own study, per the "
            "pre-registration. If the tilt does not survive, the denominator was the "
            "channel and the sleeve question is less urgent. Either way, `dynamic-"
            "breadth-v1`, `region-quota-removal-v1` and `entry-selection-separation-v1` "
            "remain pre-registered and untouched by this result."),
    }

    output.write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                 allow_nan=False, sort_keys=True) + "\n")
    md.write_text(markdown(report))
    print(markdown(report), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
