"""Run the region-quota-removal ladder, read-only on sealed inputs.

`alpha-reliability-v1` measured that the region cap stops a name on 93.10% of
rebalances and that 134 of 145 stopped names outscored one the book took.
`dynamic-breadth-v1` then found the same cap binding even in a study that was
not asking about regions at all. This asks directly: what does the ranking
want, left alone, and is the existing calibrated score comparable enough
across regions to let it answer.

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
from pipeline import benchmark_alpha as BA                # noqa: E402
from pipeline import historical_store as HS               # noqa: E402
from pipeline import portfolio_validation as PV           # noqa: E402
from pipeline import provenance                           # noqa: E402
from pipeline import region_quota_removal as RQ           # noqa: E402
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
        "# Region quota removal v1", "",
        "> Read-only research CHALLENGER on sealed replay-v16 inputs. Score formula,",
        "> targetNames, maxNamesPerSector, cash floor and position sizing are",
        "> unchanged, no selector is promoted and production is unchanged.", "",
        "## The question", "",
        "`alpha-reliability-v1` measured the region cap stopping a name on 93.10% of",
        "rebalances, 134 of 145 times against one that outscored what the book took.",
        "This removes ONLY that cap — `maxNamesPerRegion` opened to `targetNames` — and",
        "asks what the ranking wants when it is left to decide the regional mix itself.",
        "", "## The prerequisite: is the existing scale comparable across regions?", "",
        "Alpha percentiles are a within-region rank, so this is answered by the",
        "CALIBRATED score every rung already ranks on — a region-specific expected",
        "benchmark excess in percentage points, read from the CONTROL path's own",
        "candidates, never re-derived.", ""]
    comp = report["calibrationComparability"]["byRegion"]
    lines += ["| Region | Alpha mean | Alpha sd | Shrink mean | Effective dates mean | n |",
              "|---|---:|---:|---:|---:|---:|"]
    for region, blob in comp.items():
        lines.append(f"| {region} | {_fmt((blob['alpha']).get('mean'), 'pp')} | "
                     f"{_fmt((blob['alpha']).get('sd'), 'pp')} | "
                     f"{_fmt((blob['shrink']).get('mean'))} | "
                     f"{_fmt((blob['effectiveDates']).get('mean'))} | "
                     f"{blob['alpha'].get('observations')} |")

    lines += ["", "## The axis", "",
              "| Rung | Region cap |", "|---|---|",
              f"| `{RQ.CONTROL}` | `maxNamesPerRegion = 3` |",
              f"| `{RQ.NO_REGION_QUOTA}` | opened to `targetNames` (never itself binding) |",
              "", "## The ladder", "",
              "| Rung | Gross CAGR | Cost drag | Net CAGR | Matched benchmark | Net excess | "
              "Vol | Sharpe | MDD | Turnover |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for rung in RQ.LADDER:
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
    for rung in RQ.LADDER:
        edge = (report["ladder"][rung].get("edgeDecomposition") or {})
        lines.append(f"| {rung} | {_fmt(edge.get('arithmeticSelectionEdgePp'), 'pp')} | "
                     f"{_fmt(edge.get('compoundingEdgePp'), 'pp')} | "
                     f"{_fmt(edge.get('geometricGrossEdgePp'), 'pp')} | "
                     f"{_fmt(edge.get('blockSdRatio'), 'x')} |")

    lines += ["", "### Turnover and selection behaviour", "",
              "| Rung | One-way turnover | Name share | Names held (mean) | Incumbent retention |",
              "|---|---:|---:|---:|---:|"]
    for rung in RQ.LADDER:
        turn = (report["ladder"][rung].get("turnoverDecomposition") or {})
        beh = report["selectionBehaviour"][rung]
        lines.append(f"| {rung} | {_fmt(turn.get('averageOneWayTurnoverPct'), '%')} | "
                     f"{_fmt(turn.get('nameReplacementSharePct'), '%')} | "
                     f"{_fmt(beh.get('averageNamesHeld'))} | "
                     f"{_fmt(beh.get('incumbentRetentionRatePct'), '%')} |")

    lines += ["", "### Regional mix: what the ranking held once the cap could not stop it", "",
              "| Rung | Held name-dates by region | Most common shapes |",
              "|---|---|---|"]
    for rung in RQ.LADDER:
        mix = report["regionMix"][rung]
        top_shapes = dict(list(mix["regionShapeCounts"].items())[:4])
        lines.append(f"| {rung} | `{mix['heldNameDatesByRegion']}` | `{top_shapes}` |")

    lines += ["", "### Regional contribution to gross excess", "",
              "| Rung | US contribution | US 95% CI | KR contribution | KR 95% CI |",
              "|---|---:|---:|---:|---:|"]
    for rung in RQ.LADDER:
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
    lines.append("This interval EXCLUDES zero, **" + sep["direction"] + "**."
                 if sep else "This interval CONTAINS zero.")

    finding = report["finding"]
    lines += ["", "## Reading", "", f"**{finding['verdict']}**", "", finding["summary"], "",
              "### Refuted", ""]
    for item in finding.get("refuted") or ["Nothing was refuted by its own pre-specified test."]:
        lines.append(f"- {item}")
    lines += ["", "### Next direction", "", finding["nextDirection"], "",
              "A rung ending higher than another is a point estimate on sealed history,",
              "after several rungs across seven studies, with no multiplicity correction.",
              "It is not evidence to promote a selector.", ""]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger_dir")
    parser.add_argument("--output", default="region-quota-removal-report.json")
    parser.add_argument("--markdown", default="region-quota-removal-report.md")
    args = parser.parse_args(argv)
    ledger = Path(args.ledger_dir)
    output, md = _guard(args.output, ledger), _guard(args.markdown, ledger)
    before = _digest_tree(ledger)

    cfg, _ = load_config()
    store = RI.InputStore(ledger, provenance.REPLAY_VERSION, provenance.DATA_VERSION)
    manifest = store.manifest()
    if not manifest or provenance.REPLAY_VERSION != "replay-v16":
        raise ValueError("region-quota-removal-v1 requires sealed replay-v16 inputs")
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

    print(f"running {RQ.CONTROL} (alpha_reliability's own control, called directly) "
          f"on {len(calendar)} blocks", flush=True)
    control_path = AR.run_rung(RQ.CONTROL, contexts=contexts, calibrator=calibrator(),
                               calendar=calendar, cfg_pf=cfg.kelly_portfolio,
                               valuation=valuation)
    if not control_path["complete"]:
        raise ValueError(f"control path incomplete: {control_path['failures'][:3]}")

    print(f"running {RQ.NO_REGION_QUOTA} on {len(calendar)} blocks", flush=True)
    open_path = RQ.run_no_quota_rung(
        contexts=contexts, calibrator=calibrator(), calendar=calendar,
        cfg_pf=cfg.kelly_portfolio, valuation=valuation)
    if not open_path["complete"]:
        raise ValueError(f"no-quota path incomplete: {open_path['failures'][:3]}")

    paths = {RQ.CONTROL: control_path, RQ.NO_REGION_QUOTA: open_path}
    summaries = {rung: SV.summarize(paths[rung]["rows"], research_cfg) for rung in RQ.LADDER}
    control_rows = paths[RQ.CONTROL]["rows"]

    report = {
        "version": RQ.VERSION, "status": "CHALLENGER",
        "freezeManifest": RQ.freeze_manifest(),
        "inputSnapshot": {"sha256": manifest["sha256"], "through": manifest["through"]},
        "calibrationComparability": RQ.calibration_comparability(control_path["decisions"]),
        "ladder": {rung: _fields(summaries[rung]) for rung in RQ.LADDER},
        "selectionBehaviour": {rung: selection_behaviour(paths[rung]["decisions"])
                               for rung in RQ.LADDER},
        "regionMix": {rung: RQ.region_mix(paths[rung]["decisions"]) for rung in RQ.LADDER},
        "regionalAttribution": {
            rung: SH.regional_attribution(
                paths[rung]["rows"], years=summaries[rung].get("calendarYears") or 0)
            for rung in RQ.LADDER},
        "pairedVsControl": RVL.paired_bootstrap(
            paths[RQ.NO_REGION_QUOTA]["rows"], control_rows, research_cfg),
        "pairedBlocks": len(control_rows),
        "sealedInvariant": {"before": before, "after": _digest_tree(ledger)},
        "productionChanged": False,
    }
    report["separation"] = _separation(report["pairedVsControl"])
    report["sealedInvariant"]["unchanged"] = (
        report["sealedInvariant"]["before"] == report["sealedInvariant"]["after"])
    if not report["sealedInvariant"]["unchanged"]:
        raise ValueError("SEALED_LEDGER_CHANGED")

    control_excess = summaries[RQ.CONTROL].get("annualizedExcessPct")
    challenger_excess = summaries[RQ.NO_REGION_QUOTA].get("annualizedExcessPct")
    sep = report["separation"]
    refuted = []
    if sep and sep["direction"] == "WORSE":
        refuted.append(
            f"Removing the region quota: the paired interval against the control "
            f"EXCLUDES zero in the WORSE direction, {_fmt(sep['pointEstimatePp'], 'pp')}, "
            f"95% CI [{_fmt(sep['ci95Pp'][0], 'pp')}, {_fmt(sep['ci95Pp'][1], 'pp')}]. The "
            "hypothesis that the quota was purely a cost with no diversification benefit "
            "is refuted by its own pre-specified test on this sample.")

    comp = report["calibrationComparability"].get("byRegion") or {}
    shrink_gap = None
    if "US" in comp and "KR" in comp:
        us_shrink = (comp["US"].get("shrink") or {}).get("mean")
        kr_shrink = (comp["KR"].get("shrink") or {}).get("mean")
        if us_shrink is not None and kr_shrink is not None:
            shrink_gap = round(us_shrink - kr_shrink, 4)

    mix_control = report["regionMix"][RQ.CONTROL]["heldNameDatesByRegion"]
    mix_open = report["regionMix"][RQ.NO_REGION_QUOTA]["heldNameDatesByRegion"]
    report["finding"] = {
        "verdict": ("BENCHMARK_BEATEN" if (challenger_excess or 0) > 0
                    else "BENCHMARK_NOT_BEATEN"),
        "controlNetExcessPp": control_excess,
        "noQuotaNetExcessPp": challenger_excess,
        "separated": bool(sep),
        "separationDirection": (sep or {}).get("direction"),
        "promotionEligible": False,
        "refuted": refuted,
        "usMinusKrShrinkGap": shrink_gap,
        "summary": (
            f"Net excess moves from {_fmt(control_excess, 'pp')} (3-cap) to "
            f"{_fmt(challenger_excess, 'pp')} (quota opened). Paired difference "
            f"{_fmt((_pair(report['pairedVsControl'])[0]), 'pp')}, 95% CI "
            f"[{_fmt((_pair(report['pairedVsControl'])[1]), 'pp')}, "
            f"{_fmt((_pair(report['pairedVsControl'])[2]), 'pp')}], which "
            + ("EXCLUDES zero." if sep else "CONTAINS zero.")
            + f" Held name-dates move from {mix_control} under the cap to {mix_open} once "
            "it is opened. The US-minus-KR shrinkage gap on the control's own candidates is "
            f"{_fmt(shrink_gap)} — " + (
                "a positive gap means KR estimates are pulled harder toward zero by their "
                "shorter effective history, which is the comparability artefact the "
                "pre-registration's prerequisite named, and it is a limit on how much "
                "weight this result can bear rather than something this study corrects."
                if shrink_gap is not None and shrink_gap > 0 else
                "the two regions' calibrations are not systematically different in "
                "shrinkage on this sample.")),
        "nextDirection": (
            "This rung tested only whether the COUNT quota binds; it did not build the "
            "portfolio-level risk or covariance budget the pre-registration named as the "
            "eventual replacement, and does not claim to. `entry-selection-separation-v1` "
            "remains pre-registered and untouched by this result."),
    }

    output.write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                 allow_nan=False, sort_keys=True) + "\n")
    md.write_text(markdown(report))
    print(markdown(report), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
