"""Run the signal-persistence diagnostic and ladder, read-only on sealed inputs.

`regional-switch-hurdle-v1` gained eight times more from holding names longer
than from the fees it saved, which is a statement about the signal rather than
about costs. This asks it directly: are the ranking's newest picks its worst
ones, and does averaging the signal over the span it forecasts do what the
hurdle did indirectly?

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

from pipeline import benchmark_alpha as BA                  # noqa: E402
from pipeline import historical_store as HS                 # noqa: E402
from pipeline import portfolio_validation as PV             # noqa: E402
from pipeline import provenance                             # noqa: E402
from pipeline import regional_validation as RVL             # noqa: E402
from pipeline import replay_calendar as RC                  # noqa: E402
from pipeline import replay_inputs as RI                    # noqa: E402
from pipeline import replay_valuation as RV                 # noqa: E402
from pipeline import selection_value as SV                  # noqa: E402
from pipeline import signal_persistence as SP               # noqa: E402
from pipeline.config import load_config                     # noqa: E402


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
                "grossBenchmarkGapPp", "edgeDecomposition", "turnoverDecomposition")


def _fields(row: dict) -> dict:
    return {key: row.get(key) for key in SUMMARY_KEYS}


def _fmt(value, suffix=""):
    return "n/a" if value is None else f"{value:.3f}{suffix}"


def markdown(report: dict) -> str:
    diag = report["incumbencyDiagnostic"]
    lines = [
        "# Signal persistence v1", "",
        "> Read-only research CHALLENGER on sealed replay-v16 inputs. No selector is",
        "> promoted and production is unchanged.", "",
        "## The question", "",
        "`regional-switch-hurdle-v1` saved 0.270pp of cost drag and gained 2.157pp of",
        "arithmetic stock selection. Holding a name longer cannot make the name better,",
        "so the finding was about the SIGNAL: chasing each block's top-ranked name was",
        "destroying gross return. This asks that directly.", "",
        "## Diagnostic: are the ranking's newest picks its worst ones?", "",
        "At every rebalance the book's names divide into those it just ADDED and those",
        "it RETAINED. Both were chosen by the same ranking on the same date under the",
        "same constraints; only incumbency separates them. The paired figure is the",
        "within-rebalance difference, so it carries no market-timing term.", "",
        f"- ADDED realised **{_fmt(diag.get('addedMeanExcessPct'), '%')}** mean 21-session "
        f"benchmark excess over {diag.get('addedObservations')} name-blocks.",
        f"- RETAINED realised **{_fmt(diag.get('retainedMeanExcessPct'), '%')}** over "
        f"{diag.get('retainedObservations')}.",
        f"- Paired ADDED minus RETAINED: **{_fmt(diag.get('addedMinusRetainedPct'), '%')}** "
        f"per block, 95% CI "
        f"[{_fmt((diag.get('addedMinusRetainedCi95Pct') or [None, None])[0], '%')}, "
        f"{_fmt((diag.get('addedMinusRetainedCi95Pct') or [None, None])[1], '%')}] "
        f"over {diag.get('pairedRebalances')} rebalances.", "",
        "| Region | ADDED mean | RETAINED mean | Difference |", "|---|---:|---:|---:|"]
    for region, blob in (diag.get("byRegion") or {}).items():
        lines.append(f"| {region} | {_fmt(blob.get('addedMeanExcessPct'), '%')} | "
                     f"{_fmt(blob.get('retainedMeanExcessPct'), '%')} | "
                     f"{_fmt(blob.get('differencePct'), '%')} |")
    move = report["percentileMovement"]
    lines += ["", "## Is there room to smooth?", "",
              f"A name's alpha percentile moves a mean of "
              f"**{_fmt(move.get('meanAbsoluteMove'))}** points between consecutive blocks "
              f"it appears in (median {_fmt(move.get('medianAbsoluteMove'))}, p90 "
              f"{_fmt(move.get('p90AbsoluteMove'))}, {move.get('observations')} "
              "observations). A ranking that barely moves leaves smoothing nothing to do.", "",
              "## Ladder: rank on the signal averaged over the span it forecasts", "",
              "One axis. No hurdle, same cadence, same caps, same cash floor, same costs.",
              "`k=6` is the forecast horizon in blocks (126 sessions / 21); `k=3` is the",
              "midpoint to the control. Neither is swept.", "",
              "| Rung | k | Gross CAGR | Cost drag | Net CAGR | Matched benchmark | Net excess | Sharpe | MDD | Turnover |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for name, row in report["ladder"].items():
        window = report["windows"].get(name)
        lines.append(
            f"| {name} | {window if window is not None else '—'} | "
            f"{_fmt(row.get('grossCagrPct'), '%')} | {_fmt(row.get('costDragCagrPp'), 'pp')} | "
            f"{_fmt(row.get('cagrPct'), '%')} | {_fmt(row.get('benchmarkCagrPct'), '%')} | "
            f"{_fmt(row.get('annualizedExcessPct'), 'pp')} | {_fmt(row.get('sharpe'))} | "
            f"{_fmt(row.get('mddPct'), '%')} | "
            f"{_fmt(row.get('annualOneWayTurnoverX'), 'x')} |")
    lines += ["", "### Where the gross gap comes from", "",
              "| Rung | Arithmetic selection | Compounding | Geometric gross edge |",
              "|---|---:|---:|---:|"]
    for name, row in report["ladder"].items():
        edge = row.get("edgeDecomposition") or {}
        lines.append(f"| {name} | {_fmt(edge.get('arithmeticSelectionEdgePp'), 'pp')} | "
                     f"{_fmt(edge.get('compoundingEdgePp'), 'pp')} | "
                     f"{_fmt(edge.get('geometricGrossEdgePp'), 'pp')} |")
    lines += ["", "### Paired differences against the control", ""]
    for name, comparison in report["pairedComparisons"].items():
        delta = comparison["pathDifferenceCI"]["annualizedExcessPct"]
        lines.append(f"- {name}: Δ annualized excess {_fmt(delta['pointEstimate'], 'pp')}, "
                     f"95% CI [{_fmt(delta['ci95'][0], 'pp')}, {_fmt(delta['ci95'][1], 'pp')}].")
    combined = report.get("combined") or {}
    if combined.get("summary"):
        row = combined["summary"]
        lines += ["", "## Smoothing AND the switch hurdle, reported separately", "",
                  "This moves TWO axes at once, so its number cannot be attributed to",
                  "either. It is here because the combination is what a production rule",
                  "would actually be, not because it belongs in the ladder.", "",
                  f"- Net excess **{_fmt(row.get('annualizedExcessPct'), 'pp')}**, "
                  f"Sharpe {_fmt(row.get('sharpe'))}, MDD {_fmt(row.get('mddPct'), '%')}, "
                  f"turnover {_fmt(row.get('annualOneWayTurnoverX'), 'x')}.",
                  f"- Against the ladder control: Δ "
                  f"{_fmt(combined['vsControl']['pathDifferenceCI']['annualizedExcessPct']['pointEstimate'], 'pp')}, "
                  f"95% CI [{_fmt(combined['vsControl']['pathDifferenceCI']['annualizedExcessPct']['ci95'][0], 'pp')}, "
                  f"{_fmt(combined['vsControl']['pathDifferenceCI']['annualizedExcessPct']['ci95'][1], 'pp')}]."]
    finding = report["finding"]
    lines += ["", "## Reading", "", f"**{finding['verdict']}**", "",
              finding["summary"], "", finding["nextDirection"], "",
              "A rung ending higher than another is a point estimate on sealed history.",
              "It is not evidence to promote a selector.", ""]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger_dir")
    parser.add_argument("--output", default="signal-persistence-report.json")
    parser.add_argument("--markdown", default="signal-persistence-report.md")
    args = parser.parse_args(argv)
    ledger = Path(args.ledger_dir)
    output, md = _guard(args.output, ledger), _guard(args.markdown, ledger)
    before = _digest_tree(ledger)

    cfg, _ = load_config()
    store = RI.InputStore(ledger, provenance.REPLAY_VERSION, provenance.DATA_VERSION)
    manifest = store.manifest()
    if not manifest or provenance.REPLAY_VERSION != "replay-v16":
        raise ValueError("signal-persistence-v1 requires sealed replay-v16 inputs")
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
    for rung in SP.LADDER:
        print(f"running {rung} (k={SP.WINDOW[rung]}) on {len(calendar)} blocks", flush=True)
        result = SP.run_rung(rung, contexts=contexts, calibrator=calibrator(),
                             calendar=calendar, cfg_pf=cfg.kelly_portfolio,
                             valuation=valuation)
        if not result["complete"]:
            raise ValueError(f"{rung} path incomplete: {result['failures'][:3]}")
        paths[rung] = result

    print(f"running {SP.COMBINED} (two axes, reported separately)", flush=True)
    combined_result = SP.run_rung(SP.COMBINED, contexts=contexts, calibrator=calibrator(),
                                  calendar=calendar, cfg_pf=cfg.kelly_portfolio,
                                  valuation=valuation, hurdle=True)
    if not combined_result["complete"]:
        raise ValueError("combined path incomplete")

    print("pricing the fixed cross-section for the incumbency diagnostic", flush=True)
    by_date = {}
    for row in signals:
        if row.get("date"):
            by_date.setdefault(row["date"], []).append(row)
    shared = [row["date"] for row in paths[SP.LATEST]["rows"]]
    _, priced_by_date, _ = PV.priced_cross_section(
        contexts, by_date, calendar, shared, valuation)

    ladder = {rung: SV.summarize(paths[rung]["rows"], research_cfg) for rung in SP.LADDER}
    combined_summary = SV.summarize(combined_result["rows"], research_cfg)
    control_rows = paths[SP.LATEST]["rows"]

    report = {
        "version": SP.VERSION, "status": "CHALLENGER",
        "freezeManifest": SP.freeze_manifest(),
        "inputSnapshot": {"sha256": manifest["sha256"], "through": manifest["through"]},
        "windows": {**SP.WINDOW, SP.COMBINED: SP.HORIZON_BLOCKS},
        "incumbencyDiagnostic": SP.incumbency_outcomes(
            paths[SP.LATEST]["decisions"], priced_by_date),
        "percentileMovement": SP.percentile_movement(contexts, calendar),
        "ladder": {rung: _fields(ladder[rung]) for rung in SP.LADDER},
        "pairedComparisons": {
            f"{rung} minus {SP.LATEST}": RVL.paired_bootstrap(
                paths[rung]["rows"], control_rows, research_cfg)
            for rung in SP.LADDER if rung != SP.LATEST},
        "combined": {
            "summary": _fields(combined_summary),
            "vsControl": RVL.paired_bootstrap(combined_result["rows"], control_rows,
                                              research_cfg),
            "note": ("Moves both the smoothing window and the switch hurdle, so its "
                     "result cannot be attributed to either axis. Not a ladder rung."),
        },
        "sealedInvariant": {"before": before, "after": _digest_tree(ledger)},
        "productionChanged": False,
    }
    report["sealedInvariant"]["unchanged"] = (
        report["sealedInvariant"]["before"] == report["sealedInvariant"]["after"])
    if not report["sealedInvariant"]["unchanged"]:
        raise ValueError("SEALED_LEDGER_CHANGED")

    diag = report["incumbencyDiagnostic"]
    lo, hi = (diag.get("addedMinusRetainedCi95Pct") or [None, None])
    diagnostic_separated = bool(lo is not None and hi is not None and (lo > 0 or hi < 0))
    control_net = ladder[SP.LATEST].get("annualizedExcessPct")
    best = max(SP.LADDER, key=lambda r: ladder[r].get("annualizedExcessPct") or -1e9)
    beaten = bool((ladder[best].get("annualizedExcessPct") or 0) > 0)
    separated = [r for r in SP.LADDER if r != SP.LATEST
                 and (report["pairedComparisons"][f"{r} minus {SP.LATEST}"]
                      ["pathDifferenceCI"]["annualizedExcessPct"]["ci95"][0] or 0) > 0]
    report["finding"] = {
        "verdict": "BENCHMARK_BEATEN" if beaten else "BENCHMARK_NOT_BEATEN",
        "bestRung": best,
        "bestNetExcessPp": ladder[best].get("annualizedExcessPct"),
        "controlNetExcessPp": control_net,
        "separatedFromControl": separated,
        "diagnosticSeparatedFromZero": diagnostic_separated,
        "hypothesisSupported": diagnostic_separated and (diag.get("addedMinusRetainedPct") or 0) < 0,
        "summary": (
            f"Newly added names realised {_fmt(diag.get('addedMeanExcessPct'), '%')} against "
            f"{_fmt(diag.get('retainedMeanExcessPct'), '%')} for names the book already held; "
            f"paired within rebalance the difference is "
            f"{_fmt(diag.get('addedMinusRetainedPct'), '%')} with 95% CI "
            f"[{_fmt(lo, '%')}, {_fmt(hi, '%')}], which "
            + ("EXCLUDES zero." if diagnostic_separated else "contains zero.")
            + " Averaging the ranking over the span it forecasts moves net excess from "
            f"{_fmt(control_net, 'pp')} (k=1) to "
            + ", ".join(f"{_fmt(ladder[r].get('annualizedExcessPct'), 'pp')} (k={SP.WINDOW[r]})"
                        for r in SP.LADDER if r != SP.LATEST) + "."),
        "nextDirection": (
            "Every ordering is read against its paired interval; one that spans zero is "
            "not a finding. The diagnostic and the ladder are separate claims — the first "
            "is about the ranking's newest opinions and holds whatever the ladder does, "
            "the second is about a rule and does not. Nothing here is prospective "
            "evidence, and the smoothing-plus-hurdle number moves two axes and is "
            "attributable to neither."),
    }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                 allow_nan=False, sort_keys=True) + "\n")
    md.write_text(markdown(report))
    print(markdown(report), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
