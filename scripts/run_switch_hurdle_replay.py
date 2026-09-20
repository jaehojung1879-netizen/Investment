"""Run the regional switch-hurdle ladder from sealed replay-v16 inputs, read-only.

`selection_value` established that the deficit to the matched benchmark is an
implementation cost rather than an ordering failure, and that breadth is not the
remedy. This tests the one remaining lever: replace an incumbent only when the
improvement covers what the swap costs — in the region where it is being paid,
because a Korean round trip costs 1.6x to 2.5x an American one.

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
from pipeline import switch_hurdle as SH                    # noqa: E402
from pipeline.config import load_config                     # noqa: E402

BASELINE = "PUBLISHED_CHALLENGER_NO_HURDLE"


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
                "sumTransactionCostPct", "grossBenchmarkGapPp",
                "edgeDecomposition", "turnoverDecomposition")


def _fields(row: dict) -> dict:
    return {key: row.get(key) for key in SUMMARY_KEYS}


def _fmt(value, suffix=""):
    return "n/a" if value is None else f"{value:.3f}{suffix}"


def markdown(report: dict) -> str:
    rungs = report["ladder"]
    lines = [
        "# Regional switch hurdle v1", "",
        "> Read-only research CHALLENGER on sealed replay-v16 inputs. No selector is",
        "> promoted and production is unchanged.", "",
        "## What this isolates", "",
        "One thing: the replacement decision. Cadence stays at every 21-session block,",
        "caps and the cash floor stay production, and there is no positive-alpha cash",
        "gate. An incumbent is credited the sell cost of its own region and a challenger",
        "charged the buy cost of its own region, so Korean positions become stickier",
        "than American ones without anyone choosing that ratio — the sell tax does it.", "",
        "## Cost of a swap, by region and year", "",
        "| Year | US round trip | KR round trip | KR / US |",
        "|---|---:|---:|---:|"]
    for row in report["costSchedule"]:
        lines.append(f"| {row['year']} | {_fmt(row['usRoundTripPct'], '%')} | "
                     f"{_fmt(row['krRoundTripPct'], '%')} | {_fmt(row['ratio'], 'x')} |")
    lines += ["", "## Ladder", "",
              "| Path | Gross CAGR | Cost drag | Net CAGR | Matched benchmark | Net excess | Sharpe | MDD | Annual turnover | Avg cash |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for name, row in rungs.items():
        lines.append(
            f"| {name} | {_fmt(row.get('grossCagrPct'), '%')} | "
            f"{_fmt(row.get('costDragCagrPp'), 'pp')} | {_fmt(row.get('cagrPct'), '%')} | "
            f"{_fmt(row.get('benchmarkCagrPct'), '%')} | "
            f"{_fmt(row.get('annualizedExcessPct'), 'pp')} | {_fmt(row.get('sharpe'))} | "
            f"{_fmt(row.get('mddPct'), '%')} | "
            f"{_fmt(row.get('annualOneWayTurnoverX'), 'x')} | "
            f"{_fmt(row.get('averageCashPct'), '%')} |")
    lines += ["", "## Did the hurdle bite harder where it costs more?", "",
              "| Path | US retention | KR retention |", "|---|---:|---:|"]
    for name, blob in report["retentionByRegion"].items():
        us = (blob.get("US") or {}).get("retentionRatePct")
        kr = (blob.get("KR") or {}).get("retentionRatePct")
        lines.append(f"| {name} | {_fmt(us, '%')} | {_fmt(kr, '%')} |")
    lines += ["", "## Where the gain came from", "",
              "The rule was designed to save the fees a swap costs. Against the control:", "",
              "| Path | Cost drag saved | Arithmetic selection gained |", "|---|---:|---:|"]
    for name, blob in report["finding"]["mechanism"].items():
        lines.append(f"| {name} | {_fmt(blob['costDragSavedPp'], 'pp')} | "
                     f"{_fmt(blob['arithmeticSelectionGainedPp'], 'pp')} |")
    lines += ["", "## Where the gross gap comes from", "",
              "| Path | Arithmetic selection | Compounding | Geometric gross edge |",
              "|---|---:|---:|---:|"]
    for name, row in rungs.items():
        edge = row.get("edgeDecomposition") or {}
        lines.append(f"| {name} | {_fmt(edge.get('arithmeticSelectionEdgePp'), 'pp')} | "
                     f"{_fmt(edge.get('compoundingEdgePp'), 'pp')} | "
                     f"{_fmt(edge.get('geometricGrossEdgePp'), 'pp')} |")
    lines += ["", "## Regional attribution", "",
              "`excessByRegion` sums to `grossExcessReturn`, so the contributions rebuild",
              "the headline. Sleeve figures are weight-normalised. Both carry wide",
              "intervals on 155 blocks split two ways — they locate the question.", "",
              "| Path | Region | Avg weight | Contribution | 95% CI | Sleeve excess | 95% CI |",
              "|---|---|---:|---:|---|---:|---|"]
    for name, blob in report["regionalAttribution"].items():
        for region, row in (blob.get("byRegion") or {}).items():
            ci = row.get("contributionCi95Pp") or [None, None]
            sci = row.get("sleeveExcessCi95Pp") or [None, None]
            lines.append(
                f"| {name} | {region} | {_fmt(row.get('averageWeightPct'), '%')} | "
                f"{_fmt(row.get('contributionPpPerYear'), 'pp')} | "
                f"[{_fmt(ci[0], 'pp')}, {_fmt(ci[1], 'pp')}] | "
                f"{_fmt(row.get('sleeveExcessPpPerYear'), 'pp')} | "
                f"[{_fmt(sci[0], 'pp')}, {_fmt(sci[1], 'pp')}] |")
    fid = report["controlFidelity"]
    lines += ["", "## Control fidelity", "",
              f"The no-hurdle control through this loop lands at "
              f"{_fmt(fid['controlNetExcessPp'], 'pp')} against the published challenger's "
              f"{_fmt(fid['publishedNetExcessPp'], 'pp')}. It is NOT expected to match:", "",
              fid["knownCause"], "",
              "The hurdle is therefore measured against the control, never against the",
              "published path.", "",
              "## Paired differences against the no-hurdle control", ""]
    for name, comparison in report["pairedComparisons"].items():
        delta = comparison["pathDifferenceCI"]["annualizedExcessPct"]
        lines.append(f"- {name}: Δ annualized excess {_fmt(delta['pointEstimate'], 'pp')}, "
                     f"95% CI [{_fmt(delta['ci95'][0], 'pp')}, {_fmt(delta['ci95'][1], 'pp')}].")
    finding = report["finding"]
    lines += ["", "## Reading", "", f"**{finding['verdict']}**", "",
              finding["summary"], "", finding["nextDirection"], "",
              "A rung ending higher than another is a point estimate on sealed history.",
              "It is not evidence to promote a selector.", ""]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger_dir")
    parser.add_argument("--output", default="switch-hurdle-report.json")
    parser.add_argument("--markdown", default="switch-hurdle-report.md")
    args = parser.parse_args(argv)
    ledger = Path(args.ledger_dir)
    output, md = _guard(args.output, ledger), _guard(args.markdown, ledger)
    before = _digest_tree(ledger)

    cfg, _ = load_config()
    store = RI.InputStore(ledger, provenance.REPLAY_VERSION, provenance.DATA_VERSION)
    manifest = store.manifest()
    if not manifest or provenance.REPLAY_VERSION != "replay-v16":
        raise ValueError("switch-hurdle-v1 requires sealed replay-v16 inputs")
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

    paths: dict[str, dict] = {}
    for rung in SH.LADDER:
        print(f"running {rung} on {len(calendar)} fixed blocks", flush=True)
        calibrator = PV.ExpandingBucketCalibration(
            outcomes, horizon=int(cfg.kelly_portfolio.get("horizonDays", 126)),
            prior_strength=float(cfg.kelly_portfolio.get("shrinkagePriorStrength", 30)),
            min_dates=20, cost_adjusted=False)
        result = SH.run_rung(rung, contexts=contexts, calibrator=calibrator,
                             calendar=calendar, cfg_pf=cfg.kelly_portfolio,
                             valuation=valuation)
        if not result["complete"]:
            raise ValueError(f"{rung} path incomplete: {result['failures'][:3]}")
        paths[rung] = result

    baseline_rows = SH.published_challenger_rows(sealed)
    ladder = {BASELINE: SV.summarize(baseline_rows, research_cfg)}
    rows_by_name = {BASELINE: baseline_rows}
    for rung, result in paths.items():
        ladder[rung] = SV.summarize(result["rows"], research_cfg)
        rows_by_name[rung] = result["rows"]

    years = ladder[BASELINE].get("calendarYears") or 0
    report = {
        "version": SH.VERSION, "status": "CHALLENGER",
        "freezeManifest": SH.freeze_manifest(),
        "inputSnapshot": {"sha256": manifest["sha256"], "through": manifest["through"]},
        "costSchedule": [
            {"year": year,
             "usRoundTripPct": BA._round_trip_cost_pct("US", f"{year}-06-30", research_cfg),
             "krRoundTripPct": BA._round_trip_cost_pct("KR", f"{year}-06-30", research_cfg),
             "ratio": (BA._round_trip_cost_pct("KR", f"{year}-06-30", research_cfg)
                       / BA._round_trip_cost_pct("US", f"{year}-06-30", research_cfg))}
            for year in (2013, 2019, 2021, 2023, 2025, 2026)],
        "ladder": {name: _fields(ladder[name]) for name in ladder},
        "retentionByRegion": {rung: SH.turnover_by_region(result["decisions"])
                              for rung, result in paths.items()},
        "regionalAttribution": {name: SH.regional_attribution(rows, years=years)
                                for name, rows in rows_by_name.items()},
        # Each hurdle rung is paired against the CONTROL, not against the
        # published path: the control differs from the rungs in exactly one
        # thing — the hurdle — while the published path also differs in how its
        # calibration was built, so pairing against it would credit the hurdle
        # with a scoring change it did not make.
        "pairedComparisons": {
            f"{rung} minus {SH.CONTROL}": RVL.paired_bootstrap(
                rows_by_name[rung], rows_by_name[SH.CONTROL], research_cfg)
            for rung in SH.LADDER if rung != SH.CONTROL},
        "controlFidelity": {
            "measured": RVL.paired_bootstrap(
                rows_by_name[SH.CONTROL], baseline_rows, research_cfg),
            "controlNetExcessPp": ladder[SH.CONTROL].get("annualizedExcessPct"),
            "publishedNetExcessPp": ladder[BASELINE].get("annualizedExcessPct"),
            "reproducesPublished": False,
            "knownCause": (
                "`portfolio_replay` builds its ExpandingBucketCalibration on "
                "cost-adjusted excess returns (the constructor default); this runner "
                "follows `benchmark_alpha` and builds it on GROSS excess returns, "
                "because a rule that subtracts costs itself must not be handed an "
                "alpha that already has them removed. The two therefore rank on "
                "different quantities and the control is NOT expected to reproduce the "
                "published path byte for byte. It is the baseline for the hurdle "
                "regardless, and the gap below is what a reader must not attribute to "
                "the hurdle."),
        },
        "sealedInvariant": {"before": before, "after": _digest_tree(ledger)},
        "productionChanged": False,
    }
    report["sealedInvariant"]["unchanged"] = (
        report["sealedInvariant"]["before"] == report["sealedInvariant"]["after"])
    if not report["sealedInvariant"]["unchanged"]:
        raise ValueError("SEALED_LEDGER_CHANGED")

    base_net = ladder[SH.CONTROL].get("annualizedExcessPct")
    hurdled = [r for r in SH.LADDER if r != SH.CONTROL]
    best = max(hurdled, key=lambda n: ladder[n].get("annualizedExcessPct") or -1e9)
    beaten = bool((ladder[best].get("annualizedExcessPct") or 0) > 0)
    separated = [
        r for r in hurdled
        if (report["pairedComparisons"][f"{r} minus {SH.CONTROL}"]
            ["pathDifferenceCI"]["annualizedExcessPct"]["ci95"][0] or 0) > 0]
    report["finding"] = {
        "verdict": "BENCHMARK_BEATEN" if beaten else "BENCHMARK_NOT_BEATEN",
        "bestPath": best,
        "bestNetExcessPp": ladder[best].get("annualizedExcessPct"),
        "baselineNetExcessPp": base_net,
        "separatedFromControl": separated,
        # Where the gain actually came from. The rule was designed to save the
        # fees a swap costs; if most of the improvement is arithmetic stock
        # selection instead, it is working for a reason nobody predicted and is
        # weaker evidence than its headline suggests.
        "mechanism": {
            rung: {
                "costDragSavedPp": round(
                    (ladder[SH.CONTROL].get("costDragCagrPp") or 0)
                    - (ladder[rung].get("costDragCagrPp") or 0), 4),
                "arithmeticSelectionGainedPp": round(
                    ((ladder[rung].get("edgeDecomposition") or {}).get("arithmeticSelectionEdgePp") or 0)
                    - ((ladder[SH.CONTROL].get("edgeDecomposition") or {}).get("arithmeticSelectionEdgePp") or 0), 4),
            } for rung in hurdled},
        "summary": (
            "Against its own no-hurdle control, which shares every other part of this "
            f"loop, hurdling the replacement decision moves net excess from "
            f"{_fmt(base_net, 'pp')} to "
            + ", ".join(f"{_fmt(ladder[r].get('annualizedExcessPct'), 'pp')} ({r})"
                        for r in hurdled)
            + ", with annual one-way turnover going from "
            f"{_fmt(ladder[SH.CONTROL].get('annualOneWayTurnoverX'), 'x')} to "
            + ", ".join(f"{_fmt(ladder[r].get('annualOneWayTurnoverX'), 'x')}"
                        for r in hurdled)
            + ". The published challenger sits at "
            f"{_fmt(ladder[BASELINE].get('annualizedExcessPct'), 'pp')}, but it is not "
            "the baseline for this comparison: see controlFidelity."),
        "nextDirection": (
            "Read every ordering against its paired interval before acting on it. The "
            "regional attribution locates where the book is losing; on 155 blocks split "
            "two ways it does not establish that one region's ranking works and the "
            "other's does not, and no selection rule may be changed on an interval that "
            "spans zero."
            if not beaten else
            "A path with positive net excess on sealed history is a hypothesis for "
            "prospective shadow collection, not a promotion. Freeze it and judge forward."),
    }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                 allow_nan=False, sort_keys=True) + "\n")
    md.write_text(markdown(report))
    print(markdown(report), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
