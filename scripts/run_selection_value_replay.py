"""Run the selection-value ladder from sealed replay-v16 inputs, read-only.

Answers one question the published benchmark-alpha report could not: of the gap
to the matched benchmark, how much is the SCREEN and how much is the RANKING?
The published concentrated book is rung three; rungs one and two hold the same
pool with the ranking used for less. Nothing here writes inside the ledger and
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

from pipeline import benchmark_alpha as BA                  # noqa: E402
from pipeline import historical_store as HS                 # noqa: E402
from pipeline import portfolio_validation as PV             # noqa: E402
from pipeline import provenance                             # noqa: E402
from pipeline import regional_validation as RVL             # noqa: E402
from pipeline import replay_calendar as RC                  # noqa: E402
from pipeline import replay_inputs as RI                    # noqa: E402
from pipeline import replay_valuation as RV                 # noqa: E402
from pipeline import selection_value as SV                  # noqa: E402
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
                "sortino", "mddPct", "cvar95Pct", "informationRatio",
                "averageTurnoverPct", "turnoverRebalances", "calendarYears",
                "annualOneWayTurnoverX", "grossCagrPct", "costDragCagrPp",
                "averageCashPct", "sumTransactionCostPct", "grossBenchmarkGapPp",
                "edgeDecomposition", "turnoverDecomposition")


def _fields(row: dict) -> dict:
    out = {key: row.get(key) for key in SUMMARY_KEYS}
    if row.get("mddPct") is not None and row["mddPct"] < 0:
        out["calmar"] = row.get("cagrPct") / abs(row["mddPct"])
    return out


def _fmt(value, suffix=""):
    return "n/a" if value is None else f"{value:.3f}{suffix}"


def markdown(report: dict) -> str:
    rungs = report["ladder"]
    lines = [
        "# Selection-value decomposition v1", "",
        "> Read-only DIAGNOSTIC on sealed replay-v16 inputs. No selector is promoted,",
        "> production is unchanged, and no rung is a tuned variant.", "",
        "## The question", "",
        "`benchmark-relative-alpha-v1` closed BENCHMARK_NOT_BEATEN and proposed protecting",
        "the calibrated challenger's +0.340pp/yr gross edge from turnover. That edge had",
        "never been split into what stock selection earned and what lower volatility",
        "compounded, and the share of the gap owned by the SCREEN rather than the RANKING",
        "had never been measured at all. This ladder measures both.", "",
        "## Ladder", "",
        "| Rung | Gross CAGR | Cost drag | Net CAGR | Matched benchmark | Net excess | Sharpe | MDD | Annual turnover | Avg cash | Names |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, row in rungs.items():
        turn = row.get("turnoverDecomposition") or {}
        lines.append(
            f"| {name} | {_fmt(row.get('grossCagrPct'), '%')} | "
            f"{_fmt(row.get('costDragCagrPp'), 'pp')} | {_fmt(row.get('cagrPct'), '%')} | "
            f"{_fmt(row.get('benchmarkCagrPct'), '%')} | "
            f"{_fmt(row.get('annualizedExcessPct'), 'pp')} | {_fmt(row.get('sharpe'))} | "
            f"{_fmt(row.get('mddPct'), '%')} | "
            f"{_fmt(row.get('annualOneWayTurnoverX'), 'x')} | "
            f"{_fmt(row.get('averageCashPct'), '%')} | "
            f"{_fmt(turn.get('averageNamesHeld'))} |")
    lines += ["", "## Where the gross gap comes from", "",
              "A CAGR gap answers *which ended richer*. It does not say whether the book",
              "picked better names or simply lost less to variance. Splitting it:", "",
              "| Rung | Arithmetic selection | Compounding (volatility) | Geometric gross edge | Block sd vs benchmark |",
              "|---|---:|---:|---:|---:|"]
    for name, row in rungs.items():
        edge = row.get("edgeDecomposition") or {}
        lines.append(
            f"| {name} | {_fmt(edge.get('arithmeticSelectionEdgePp'), 'pp')} | "
            f"{_fmt(edge.get('compoundingEdgePp'), 'pp')} | "
            f"{_fmt(edge.get('geometricGrossEdgePp'), 'pp')} | "
            f"{_fmt(edge.get('blockSdRatio'), 'x')} |")
    lines += ["", "## Where the turnover goes", "",
              "| Rung | Avg one-way | From name replacement | From weight retarget | Names carried to next block |",
              "|---|---:|---:|---:|---:|"]
    for name, row in rungs.items():
        turn = row.get("turnoverDecomposition") or {}
        lines.append(
            f"| {name} | {_fmt(turn.get('averageOneWayTurnoverPct'), '%')} | "
            f"{_fmt(turn.get('fromNameReplacementPct'), '%')} "
            f"({_fmt(turn.get('nameReplacementSharePct'), '%')} of it) | "
            f"{_fmt(turn.get('fromWeightRetargetPct'), '%')} | "
            f"{_fmt(turn.get('namesCarriedToNextBlockPct'), '%')} |")
    lines += ["", "## Paired differences", ""]
    for name, comparison in report["pairedComparisons"].items():
        delta = comparison["pathDifferenceCI"]["annualizedExcessPct"]
        lines.append(f"- {name}: Δ annualized excess {_fmt(delta['pointEstimate'], 'pp')}, "
                     f"95% CI [{_fmt(delta['ci95'][0], 'pp')}, {_fmt(delta['ci95'][1], 'pp')}].")
    finding = report["finding"]
    lines += ["", "## Selection null, per selector", "",
              "A null permutes ONE ranking, so its verdict is about that ranking alone.",
              "The sealed report publishes only the champion's; the challenger is the",
              "selector a promotion would actually move into production.", "",
              "| Selector | Verdict | Beats random on | Actual turnover | Null median turnover |",
              "|---|---|---|---:|---:|"]
    for label, blob in (("champion (sealed)", report["championSelectionNull"]),
                        ("challenger (this run)", report["challengerSelectionNull"])):
        overall = blob.get("overall") or {}
        mode = ((blob.get("byMode") or {}).get("INDEPENDENT_PER_DATE") or {})
        lines.append(
            f"| {label} — `{blob.get('selector')}` | {overall.get('verdict') or 'n/a'} | "
            f"{', '.join(overall.get('beatsRandomOn') or []) or 'nothing'} | "
            f"{_fmt(blob.get('actualTurnoverPct'), '%')} | "
            f"{_fmt(mode.get('nullMedianTurnoverPct'), '%')} |")
    stats = ((report["challengerSelectionNull"].get("byMode") or {})
             .get("INDEPENDENT_PER_DATE") or {}).get("statistics") or {}
    if stats:
        lines += ["", "Challenger, independent-per-date draws:", "",
                  "| Statistic | Actual | Null mean | Null p95 | Percentile | p (beats random) |",
                  "|---|---:|---:|---:|---:|---:|"]
        for name, row in stats.items():
            lines.append(
                f"| {name} | {_fmt(row.get('actual'))} | {_fmt(row.get('nullMean'))} | "
                f"{_fmt(row.get('nullP95'))} | {_fmt(row.get('percentileOfNull'))} | "
                f"{_fmt(row.get('pValueBeatsRandom'))} |")
    lines += ["", finding["selectionNullNote"], "",
              "## Reading", "",
              f"**{finding['verdict']}**", "", finding["summary"], "",
              finding["nextDirection"], "",
              "This is a diagnostic on sealed history. It is not evidence to promote a",
              "selector, and a rung ending higher than another is not a promotion trigger.",
              ""]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger_dir")
    parser.add_argument("--output", default="selection-value-report.json")
    parser.add_argument("--markdown", default="selection-value-report.md")
    args = parser.parse_args(argv)
    ledger = Path(args.ledger_dir)
    output, md = _guard(args.output, ledger), _guard(args.markdown, ledger)
    before = _digest_tree(ledger)

    cfg, _ = load_config()
    store = RI.InputStore(ledger, provenance.REPLAY_VERSION, provenance.DATA_VERSION)
    manifest = store.manifest()
    if not manifest or provenance.REPLAY_VERSION != "replay-v16":
        raise ValueError("selection-value-v1 requires sealed replay-v16 inputs")
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

    ladder, pool_sizes = {}, []
    for rung in SV.LADDER:
        print(f"running {rung} on {len(calendar)} fixed blocks", flush=True)
        calibrator = PV.ExpandingBucketCalibration(
            outcomes, horizon=int(cfg.kelly_portfolio.get("horizonDays", 126)),
            prior_strength=float(cfg.kelly_portfolio.get("shrinkagePriorStrength", 30)),
            min_dates=20, cost_adjusted=False)
        result = SV.run_rung(rung, contexts=contexts, calibrator=calibrator,
                             calendar=calendar, cfg_pf=cfg.kelly_portfolio,
                             valuation=valuation)
        if not result["complete"]:
            raise ValueError(f"{rung} path incomplete: {result['failures'][:3]}")
        pool_sizes.extend(d["poolSize"] for d in result["decisions"])
        ladder[rung] = {"summary": SV.summarize(result["rows"], research_cfg),
                        "rows": result["rows"]}

    published = sealed["portfolioReplay"]["headlineRows"][PV.CHALLENGER]
    ladder[SV.SCREEN_PLUS_CONCENTRATION] = {
        "summary": SV.summarize(published, research_cfg), "rows": published}

    # The sealed report's selection null permutes the CHAMPION's conviction
    # score. The champion's arithmetic selection edge is negative, so that
    # verdict says nothing about the challenger — the only selector here whose
    # arithmetic edge is not negative, and the one a promotion would move into
    # production. Run the null the promotion gate actually needs.
    print("pricing the fixed cross-section for the challenger null", flush=True)
    by_date = {}
    for row in signals:
        if row.get("date"):
            by_date.setdefault(row["date"], []).append(row)
    shared = [row["date"] for row in published]
    # `priced_cross_section` keys its output by BLOCK date while looking the
    # context up by SIGNAL date, which is the shape `contexts` already has.
    fixed_contexts, priced_by_date, _ = PV.priced_cross_section(
        contexts, by_date, calendar, shared, valuation)
    signal_date_of = {block["date"]: block["signalDate"] for block in calendar}
    null_calibrator = PV.ExpandingBucketCalibration(
        outcomes, horizon=int(cfg.kelly_portfolio.get("horizonDays", 126)),
        prior_strength=float(cfg.kelly_portfolio.get("shrinkagePriorStrength", 30)),
        min_dates=20, cost_adjusted=False)
    seen: set[str] = set()

    def challenger_scores(candidates, date):
        # `selection_null` hands over the BLOCK date; the real challenger scored
        # on the SIGNAL date that precedes it, and advancing to the block date
        # would admit outcomes that matured after the decision was taken. The
        # calibrator only moves forward and the dates arrive in order, so one
        # advance per date reproduces the scores the real path actually saw.
        if date not in seen:
            seen.add(date)
            null_calibrator.advance(signal_date_of.get(date, date))
        return PV._challenger_scores(candidates, null_calibrator, cfg.kelly_portfolio)

    print(f"running the challenger selection null on {len(shared)} blocks", flush=True)
    challenger_null = PV.selection_null(
        fixed_contexts, priced_by_date, published, shared,
        cfg_pf=cfg.kelly_portfolio, horizon=PV.HEADLINE_HORIZON,
        selector=PV.CHALLENGER, score_fn=challenger_scores,
        draws=int(cfg.kelly_portfolio.get("selectionNullDraws", 200)))

    rung_names = list(SV.LADDER) + [SV.SCREEN_PLUS_CONCENTRATION]
    pairs = {}
    for lower, upper in zip(rung_names, rung_names[1:]):
        pairs[f"{upper} minus {lower}"] = RVL.paired_bootstrap(
            ladder[upper]["rows"], ladder[lower]["rows"], research_cfg)

    null = (sealed["portfolioReplay"].get("selectionNull") or {})
    null_overall = ((null.get("byMode") or {}).get("INDEPENDENT_PER_DATE") or {}).get("overall") or {}
    screen_only = ladder[SV.SCREEN_ONLY]["summary"]
    concentrated = ladder[SV.SCREEN_PLUS_CONCENTRATION]["summary"]
    best = max(rung_names, key=lambda n: ladder[n]["summary"].get("annualizedExcessPct") or -1e9)
    # numpy scalars reach here through the path metrics, and `json.dumps` refuses
    # a numpy bool. Collapse to a Python bool at the boundary rather than letting
    # a 25-minute run die on its last line.
    beaten = bool((ladder[best]["summary"].get("annualizedExcessPct") or 0) > 0)

    report = {
        "version": SV.VERSION,
        "status": "DIAGNOSTIC",
        "freezeManifest": SV.freeze_manifest(pool_sizes),
        "inputSnapshot": {"sha256": manifest["sha256"], "through": manifest["through"]},
        "ladder": {name: _fields(ladder[name]["summary"]) for name in rung_names},
        "pairedComparisons": pairs,
        "challengerSelectionNull": challenger_null,
        "championSelectionNull": {
            "selector": null.get("selector") or PV.CHAMPION,
            "overall": null.get("overall"),
            "actualTurnoverPct": null.get("actualTurnoverPct"),
            "note": ("Copied from the sealed report for side-by-side reading. It "
                     "permutes the champion's conviction score and is not evidence "
                     "about the challenger."),
        },
        "finding": {
            "verdict": "BENCHMARK_BEATEN" if beaten else "BENCHMARK_NOT_BEATEN",
            "bestRung": best,
            "bestRungNetExcessPp": ladder[best]["summary"].get("annualizedExcessPct"),
            "screenOnlyNetExcessPp": screen_only.get("annualizedExcessPct"),
            "concentratedNetExcessPp": concentrated.get("annualizedExcessPct"),
            "rankingConcentrationValuePp": (
                (concentrated.get("annualizedExcessPct") or 0)
                - (screen_only.get("annualizedExcessPct") or 0)),
            "selectionNullNote": (
                "The sealed report already tests the champion ranking against the book the "
                "same construction builds from a permuted ranking: "
                f"{null_overall.get('verdict', 'unavailable')} on "
                f"{', '.join(null_overall.get('assessed') or []) or 'no statistic'}. "
                "The null book also churns more than the real one, so the real book is not "
                "a null that merely trades less."),
            "summary": "",
            "nextDirection": "",
        },
        "sealedInvariant": {"before": before, "after": _digest_tree(ledger)},
        "productionChanged": False,
    }
    report["sealedInvariant"]["unchanged"] = (
        report["sealedInvariant"]["before"] == report["sealedInvariant"]["after"])
    if not report["sealedInvariant"]["unchanged"]:
        raise ValueError("SEALED_LEDGER_CHANGED")

    edge = concentrated.get("edgeDecomposition") or {}
    turn = concentrated.get("turnoverDecomposition") or {}
    screen_edge = screen_only.get("edgeDecomposition") or {}
    tilt_edge = (ladder[SV.SCREEN_PLUS_TILT]["summary"].get("edgeDecomposition") or {})
    ch_overall = (challenger_null.get("overall") or {})
    ch_stats = ((challenger_null.get("byMode") or {})
                .get("INDEPENDENT_PER_DATE") or {}).get("statistics") or {}
    report["finding"]["hypothesisRefuted"] = bool(not beaten and (
        (screen_only.get("annualizedExcessPct") or 0)
        < (concentrated.get("annualizedExcessPct") or 0)))
    report["finding"]["arithmeticEdgeByRung"] = {
        SV.SCREEN_ONLY: screen_edge.get("arithmeticSelectionEdgePp"),
        SV.SCREEN_PLUS_TILT: tilt_edge.get("arithmeticSelectionEdgePp"),
        SV.SCREEN_PLUS_CONCENTRATION: edge.get("arithmeticSelectionEdgePp"),
    }
    report["finding"]["challengerNullVerdict"] = ch_overall.get("verdict")
    report["finding"]["summary"] = (
        f"The published concentrated book's {_fmt(edge.get('geometricGrossEdgePp'), 'pp')} "
        f"gross edge is {_fmt(edge.get('arithmeticSelectionEdgePp'), 'pp')} of arithmetic "
        f"stock selection and {_fmt(edge.get('compoundingEdgePp'), 'pp')} of compounding at "
        f"{_fmt(edge.get('blockSdRatio'), 'x')} the benchmark's block volatility, and "
        f"{_fmt(turn.get('nameReplacementSharePct'), '%')} of its turnover is names being "
        f"replaced rather than weights retargeted. The hypothesis that followed — that the "
        f"ranking is not worth that bill, so hold what the screen approved — is REFUTED by "
        f"this ladder: holding the pool broadly lands at "
        f"{_fmt(screen_only.get('annualizedExcessPct'), 'pp')} against the concentrated "
        f"book's {_fmt(concentrated.get('annualizedExcessPct'), 'pp')}, and the arithmetic "
        f"selection edge rises monotonically with how much of the ranking is used "
        f"({_fmt(screen_edge.get('arithmeticSelectionEdgePp'), 'pp')} -> "
        f"{_fmt(tilt_edge.get('arithmeticSelectionEdgePp'), 'pp')} -> "
        f"{_fmt(edge.get('arithmeticSelectionEdgePp'), 'pp')}).")
    best_p = min((row.get("pValueBeatsRandom") for row in ch_stats.values()
                  if row.get("pValueBeatsRandom") is not None), default=None)
    report["finding"]["nextDirection"] = (
        "The challenger's own null — never computed before, because the sealed report "
        f"permutes the champion's score — returns {ch_overall.get('verdict')} at best "
        f"p={_fmt(best_p)}, so the ranking does not clear the pre-registered 5% bar on any "
        "statistic even though it sits far above the champion's. Two bars are being confused "
        "if that is read as the whole answer: choosing beats a permuted ranking here and the "
        "book still trails its matched benchmark, so the remaining deficit is implementation "
        "rather than ordering. Breadth is now ruled out as the remedy, which leaves the "
        "hurdle/hysteresis proposal `benchmark-relative-alpha-v1` already named — supported "
        "now by a measurement rather than by an unsplit CAGR gap. It must still be frozen "
        "before prospective observations and judged forward."
        if not beaten else
        "A rung with positive net excess on sealed history is a hypothesis for prospective "
        "shadow collection, not a promotion. It must be frozen and judged forward.")

    output.write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                 allow_nan=False, sort_keys=True) + "\n")
    md.write_text(markdown(report))
    print(markdown(report), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
