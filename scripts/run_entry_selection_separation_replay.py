"""Run the entry-selection-separation ladder, read-only on sealed inputs.

`alpha-reliability-v1` pre-registered the separation: alpha decides the held
set, entry state decides how fast the target weight is approached. Today's
production shape does the opposite -- the entry-state multiplier discounts
the SELECTION score directly, so a WATCH name's score is halved before it is
ever ranked against an ACCUMULATE name's. This measures what changes when
that continuous throttle moves from the ranking step to a post-selection
weight throttle, leaving every eligibility fact (including a fully blocking
state) exactly as production computes it.

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

from pipeline import alpha_reliability as AR                  # noqa: E402
from pipeline import benchmark_alpha as BA                    # noqa: E402
from pipeline import entry_selection_separation as ES         # noqa: E402
from pipeline import historical_store as HS                   # noqa: E402
from pipeline import portfolio_validation as PV               # noqa: E402
from pipeline import provenance                                # noqa: E402
from pipeline import regional_validation as RVL               # noqa: E402
from pipeline import replay_calendar as RC                    # noqa: E402
from pipeline import replay_inputs as RI                      # noqa: E402
from pipeline import replay_valuation as RV                   # noqa: E402
from pipeline import selection_value as SV                    # noqa: E402
from pipeline import switch_hurdle as SH                      # noqa: E402
from pipeline.config import load_config                       # noqa: E402


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
        "# Entry selection separation v1", "",
        "> Read-only research CHALLENGER on sealed replay-v16 inputs. Alpha/risk",
        "> score, targetNames, sector/region caps, cash floor and every cost",
        "> assumption are unchanged, no selector is promoted and production is",
        "> unchanged.", "",
        "## The question", "",
        "The entry-state multiplier (1.0 ACCUMULATE, 0.5 WATCH, 0.25",
        "WAIT_FOR_PULLBACK, 0.0 fully blocking) is baked directly into the",
        "SELECTION score today, so a WATCH name's score is halved before it is",
        "ever ranked. The pre-registration's separation says alpha should decide",
        "the held set and entry state should decide how fast the target weight is",
        "approached. This moves the CONTINUOUS throttle (never the 0.0 blocking",
        "case, which stays a full eligibility exclusion on both rungs) from the",
        "ranking step to a post-selection weight throttle.", "",
        "## Before the ladder: does this axis have any bite?", ""]
    inc = report["entryStateIncidence"]
    lines += [f"Measured on the control's own {inc['measuredRebalances']} rebalances.",
              "", f"- Eligible names by state: `{inc['eligibleByState']}`",
              f"- Held names by state: `{inc['heldByState']}`",
              f"- Rebalances where an alpha-only selection would choose a "
              f"DIFFERENT set: **{inc['rebalancesWhereSelectionWouldChange']}** "
              f"({_fmt(inc['rebalancesWhereSelectionWouldChangePct'], '%')})",
              f"- Names the discount kept OUT that alpha-only would hold: "
              f"**{inc['namesTheDiscountKeptOutOfTheBook']}**",
              f"- Names the discount let IN that alpha-only would drop: "
              f"**{inc['namesTheDiscountLetIntoTheBook']}**", ""]

    lines += ["## The axis", "", "| Rung | Entry-state role |", "|---|---|",
              f"| `{ES.CONTROL}` | multiplies the selection score |",
              f"| `{ES.ENTRY_AT_WEIGHT}` | removed from selection/tilt, applied once "
              "to the held name's weight |", "", "## The ladder", "",
              "| Rung | Gross CAGR | Cost drag | Net CAGR | Matched benchmark | Net excess | "
              "Vol | Sharpe | MDD | Turnover | Avg cash |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for rung in ES.LADDER:
        row = report["ladder"][rung]
        lines.append(
            f"| {rung} | {_fmt(row.get('grossCagrPct'), '%')} | "
            f"{_fmt(row.get('costDragCagrPp'), 'pp')} | {_fmt(row.get('cagrPct'), '%')} | "
            f"{_fmt(row.get('benchmarkCagrPct'), '%')} | "
            f"{_fmt(row.get('annualizedExcessPct'), 'pp')} | "
            f"{_fmt(row.get('annualizedRealizedVolPct'), '%')} | "
            f"{_fmt(row.get('sharpe'))} | {_fmt(row.get('mddPct'), '%')} | "
            f"{_fmt(row.get('annualOneWayTurnoverX'), 'x')} | "
            f"{_fmt(row.get('averageCashPct'), '%')} |")

    lines += ["", "### Where the gross gap comes from", "",
              "| Rung | Arithmetic selection | Compounding | Geometric gross edge | Block sd ratio |",
              "|---|---:|---:|---:|---:|"]
    for rung in ES.LADDER:
        edge = (report["ladder"][rung].get("edgeDecomposition") or {})
        lines.append(f"| {rung} | {_fmt(edge.get('arithmeticSelectionEdgePp'), 'pp')} | "
                     f"{_fmt(edge.get('compoundingEdgePp'), 'pp')} | "
                     f"{_fmt(edge.get('geometricGrossEdgePp'), 'pp')} | "
                     f"{_fmt(edge.get('blockSdRatio'), 'x')} |")

    lines += ["", "### Turnover and selection behaviour", "",
              "| Rung | One-way turnover | Name share | Names held (mean) | Incumbent retention |",
              "|---|---:|---:|---:|---:|"]
    for rung in ES.LADDER:
        turn = (report["ladder"][rung].get("turnoverDecomposition") or {})
        beh = report["selectionBehaviour"][rung]
        lines.append(f"| {rung} | {_fmt(turn.get('averageOneWayTurnoverPct'), '%')} | "
                     f"{_fmt(turn.get('nameReplacementSharePct'), '%')} | "
                     f"{_fmt(beh.get('averageNamesHeld'))} | "
                     f"{_fmt(beh.get('incumbentRetentionRatePct'), '%')} |")

    throttle = report["weightThrottle"]
    lines += ["", "### The throttle's own footprint, on the new rung", "",
              f"- Held name-dates: {throttle['heldNameDates']}",
              f"- Throttled below full weight: **{throttle['throttledNameDates']}** "
              f"({_fmt(throttle['throttledNameDatesPct'], '%')})",
              f"- Unapproached weight when throttled (pp of target, mean): "
              f"{_fmt((throttle['unapproachedWeightPctWhenThrottled'] or {}).get('mean'))}",
              ""]

    lines += ["### Regional contribution to gross excess", "",
              "| Rung | US contribution | US 95% CI | KR contribution | KR 95% CI |",
              "|---|---:|---:|---:|---:|"]
    for rung in ES.LADDER:
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
              "after several rungs across eight studies, with no multiplicity correction.",
              "It is not evidence to promote a selector.", ""]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger_dir")
    parser.add_argument("--output", default="entry-selection-separation-report.json")
    parser.add_argument("--markdown", default="entry-selection-separation-report.md")
    args = parser.parse_args(argv)
    ledger = Path(args.ledger_dir)
    output, md = _guard(args.output, ledger), _guard(args.markdown, ledger)
    before = _digest_tree(ledger)

    cfg, _ = load_config()
    store = RI.InputStore(ledger, provenance.REPLAY_VERSION, provenance.DATA_VERSION)
    manifest = store.manifest()
    if not manifest or provenance.REPLAY_VERSION != "replay-v16":
        raise ValueError("entry-selection-separation-v1 requires sealed replay-v16 inputs")
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

    print(f"running {ES.CONTROL} (alpha_reliability's own control, called directly) "
          f"on {len(calendar)} blocks", flush=True)
    control_path = AR.run_rung(ES.CONTROL, contexts=contexts, calibrator=calibrator(),
                               calendar=calendar, cfg_pf=cfg.kelly_portfolio,
                               valuation=valuation)
    if not control_path["complete"]:
        raise ValueError(f"control path incomplete: {control_path['failures'][:3]}")

    print(f"running {ES.ENTRY_AT_WEIGHT} on {len(calendar)} blocks", flush=True)
    entry_path = ES.run_entry_at_weight_rung(
        contexts=contexts, calibrator=calibrator(), calendar=calendar,
        cfg_pf=cfg.kelly_portfolio, valuation=valuation)
    if not entry_path["complete"]:
        raise ValueError(f"entry-at-weight path incomplete: {entry_path['failures'][:3]}")

    paths = {ES.CONTROL: control_path, ES.ENTRY_AT_WEIGHT: entry_path}
    summaries = {rung: SV.summarize(paths[rung]["rows"], research_cfg) for rung in ES.LADDER}
    control_rows = paths[ES.CONTROL]["rows"]

    report = {
        "version": ES.VERSION, "status": "CHALLENGER",
        "freezeManifest": ES.freeze_manifest(),
        "inputSnapshot": {"sha256": manifest["sha256"], "through": manifest["through"]},
        "entryStateIncidence": ES.entry_state_incidence(control_path["decisions"], research_cfg),
        "ladder": {rung: _fields(summaries[rung]) for rung in ES.LADDER},
        "selectionBehaviour": {rung: selection_behaviour(paths[rung]["decisions"])
                               for rung in ES.LADDER},
        "weightThrottle": ES.weight_throttle_summary(entry_path["decisions"]),
        "regionalAttribution": {
            rung: SH.regional_attribution(
                paths[rung]["rows"], years=summaries[rung].get("calendarYears") or 0)
            for rung in ES.LADDER},
        "pairedVsControl": RVL.paired_bootstrap(
            paths[ES.ENTRY_AT_WEIGHT]["rows"], control_rows, research_cfg),
        "pairedBlocks": len(control_rows),
        "sealedInvariant": {"before": before, "after": _digest_tree(ledger)},
        "productionChanged": False,
    }
    report["separation"] = _separation(report["pairedVsControl"])
    report["sealedInvariant"]["unchanged"] = (
        report["sealedInvariant"]["before"] == report["sealedInvariant"]["after"])
    if not report["sealedInvariant"]["unchanged"]:
        raise ValueError("SEALED_LEDGER_CHANGED")

    control_excess = summaries[ES.CONTROL].get("annualizedExcessPct")
    challenger_excess = summaries[ES.ENTRY_AT_WEIGHT].get("annualizedExcessPct")
    sep = report["separation"]
    refuted = []
    if sep and sep["direction"] == "WORSE":
        refuted.append(
            f"Moving the throttle from selection to weight: the paired interval "
            f"against the control EXCLUDES zero in the WORSE direction, "
            f"{_fmt(sep['pointEstimatePp'], 'pp')}, 95% CI "
            f"[{_fmt(sep['ci95Pp'][0], 'pp')}, {_fmt(sep['ci95Pp'][1], 'pp')}]. The "
            "hypothesis that separating the roles loses nothing is refuted by its "
            "own pre-specified test on this sample.")

    inc = report["entryStateIncidence"]
    throttle = report["weightThrottle"]
    control_cash = report["ladder"][ES.CONTROL].get("averageCashPct")
    entry_cash = report["ladder"][ES.ENTRY_AT_WEIGHT].get("averageCashPct")
    control_edge = (report["ladder"][ES.CONTROL].get("edgeDecomposition") or {})
    entry_edge = (report["ladder"][ES.ENTRY_AT_WEIGHT].get("edgeDecomposition") or {})
    report["finding"] = {
        "verdict": ("BENCHMARK_BEATEN" if (challenger_excess or 0) > 0
                    else "BENCHMARK_NOT_BEATEN"),
        "controlNetExcessPp": control_excess,
        "entryAtWeightNetExcessPp": challenger_excess,
        "controlAverageCashPct": control_cash,
        "entryAtWeightAverageCashPct": entry_cash,
        "separated": bool(sep),
        "separationDirection": (sep or {}).get("direction"),
        "promotionEligible": False,
        "refuted": refuted,
        "summary": (
            f"The discount changed which names were held on "
            f"{inc['rebalancesWhereSelectionWouldChangePct']}% of control rebalances "
            f"({inc['rebalancesWhereSelectionWouldChange']} of {inc['measuredRebalances']}). "
            f"On the new rung, {_fmt(throttle['throttledNameDatesPct'], '%')} of held "
            f"name-dates carried a throttled weight, and average cash held rose from "
            f"{_fmt(control_cash, '%')} to {_fmt(entry_cash, '%')} -- a much larger share "
            f"of the book than the throttle's own direct effect, since alpha-only "
            f"selection also holds many more of the WATCH/WAIT_FOR_PULLBACK names the "
            f"discount used to keep out, and most of those are the ones then throttled. "
            f"Net excess moves from {_fmt(control_excess, 'pp')} (state discounts "
            f"selection) to {_fmt(challenger_excess, 'pp')} (state throttles weight "
            f"only). Paired difference {_fmt((_pair(report['pairedVsControl'])[0]), 'pp')}, "
            f"95% CI [{_fmt((_pair(report['pairedVsControl'])[1]), 'pp')}, "
            f"{_fmt((_pair(report['pairedVsControl'])[2]), 'pp')}], which "
            + ("EXCLUDES zero." if sep else "CONTAINS zero.")
            + f" The gross gap is overwhelmingly arithmetic stock selection "
            f"({_fmt(control_edge.get('arithmeticSelectionEdgePp'), 'pp')} -> "
            f"{_fmt(entry_edge.get('arithmeticSelectionEdgePp'), 'pp')}), not "
            f"compounding ({_fmt(control_edge.get('compoundingEdgePp'), 'pp')} -> "
            f"{_fmt(entry_edge.get('compoundingEdgePp'), 'pp')}): on this sample the "
            f"names the discount used to exclude realised BETTER excess returns than "
            f"the ones it favoured, not merely lower volatility from holding more "
            f"cash. That is a claim about THIS historical sample's realised outcomes, "
            f"not a mechanism this study tested."),
        "nextDirection": (
            "This axis is the continuous throttle only; a state whose multiplier is "
            "0 stays a full eligibility exclusion on both rungs, for incumbents and "
            "new entries alike. Whether an incumbent should be forced out on a "
            "blocking state at all is a separate claim about exits and was explicitly "
            "left for its own test by the pre-registration -- this was the fourth and "
            "last of the four studies alpha-reliability-v1 pre-registered."),
    }

    output.write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                 allow_nan=False, sort_keys=True) + "\n")
    md.write_text(markdown(report))
    print(markdown(report), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
