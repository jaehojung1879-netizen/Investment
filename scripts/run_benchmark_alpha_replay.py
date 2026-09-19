"""Run benchmark-relative-alpha-v1 from sealed replay-v16 inputs, read-only."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import benchmark_alpha as BA                 # noqa: E402
from pipeline import historical_store as HS                # noqa: E402
from pipeline import portfolio_validation as PV             # noqa: E402
from pipeline import provenance                            # noqa: E402
from pipeline import regional_validation as RVL             # noqa: E402
from pipeline import replay_calendar as RC                  # noqa: E402
from pipeline import replay_inputs as RI                    # noqa: E402
from pipeline import replay_valuation as RV                 # noqa: E402
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


def _summary_fields(row: dict) -> dict:
    keys = ("cagrPct", "benchmarkCagrPct", "annualizedExcessPct", "sharpe", "sortino",
            "mddPct", "cvar95Pct", "informationRatio", "averageTurnoverPct",
            "turnoverRebalances", "calendarYears", "annualOneWayTurnoverX",
            "grossCagrPct", "costDragCagrPp", "averageCashPct")
    out = {key: row.get(key) for key in keys}
    if row.get("mddPct") is not None and row["mddPct"] < 0:
        out["calmar"] = row.get("cagrPct") / abs(row["mddPct"])
    out["sumTransactionCostPct"] = row.get("sumTransactionCostPct")
    out["grossBenchmarkGapPp"] = (
        row.get("grossCagrPct") - row.get("benchmarkCagrPct")
        if row.get("grossCagrPct") is not None and row.get("benchmarkCagrPct") is not None
        else None)
    return out


def _annotate_costs(summary: dict, rows: list[dict], cfg_pf: dict) -> dict:
    copied = deepcopy(rows)
    measured = PV._path_metrics(copied, PV.HEADLINE_HORIZON, cfg_pf,
                                only_dates=[r["date"] for r in copied])
    measured["sumTransactionCostPct"] = sum(r["transactionCost"] for r in copied) * 100
    years = measured.get("calendarYears") or 0
    measured["annualOneWayTurnoverX"] = (
        (measured.get("averageTurnoverPct") or 0) / 100
        * (measured.get("turnoverRebalances") or 0) / years if years else None)
    gross = deepcopy(copied)
    for row in gross:
        row["transactionCost"] = 0
    # The gross CAGR is a direct chain of the already-valued stock path.
    growth = np.prod([1 + r["grossReturn"] for r in gross])
    measured["grossCagrPct"] = ((growth ** (1 / years) - 1) * 100
                                if years and growth > 0 else None)
    measured["costDragCagrPp"] = (
        measured["grossCagrPct"] - measured["cagrPct"]
        if measured["grossCagrPct"] is not None and measured.get("cagrPct") is not None else None)
    measured["averageCashPct"] = float(np.mean([
        1 - sum(float(weight) for weight in row["weights"].values()) for row in copied])) * 100
    return measured


def _block_alpha_ci(rows: list[dict], cfg_pf: dict) -> dict:
    copied = deepcopy(rows)
    PV._path_metrics(copied, PV.HEADLINE_HORIZON, cfg_pf,
                     only_dates=[r["date"] for r in copied])
    values = np.asarray([r["costAdjustedExcessReturn"] for r in copied], dtype=float)
    ci = PV._bootstrap_ci(values, draws=2000, seed=11)
    years = RV.span_years(copied[0]["date"], copied[-1]["endDate"])
    periods = len(values) / years
    annualized = [v * periods for v in ci]
    return {"pairedBlocks": len(values), "seed": 11, "samples": 2000,
            "meanBlockExcessPct": float(values.mean() * 100),
            "meanBlockExcessCi95Pct": ci,
            "annualizedArithmeticExcessPct": float(values.mean() * periods * 100),
            "annualizedArithmeticExcessCi95Pct": annualized,
            "method": "PAIRED_ACTIVE_MINUS_ITS_MATCHED_BENCHMARK_BLOCK_BOOTSTRAP"}


def _fmt(value, suffix=""):
    return "n/a" if value is None else f"{value:.3f}{suffix}"


def markdown(report: dict) -> str:
    lines = ["# Benchmark-relative alpha v1", "",
             "> Research-only CHALLENGER. Production selector and sealed replay are unchanged.", "",
             "## Headline", "",
             "| Portfolio | Gross CAGR | Cost drag | Net CAGR | Matched benchmark | Net excess | Sharpe | MDD | Avg turnover | Annual turnover |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for name, row in report["comparison"].items():
        lines.append(f"| {name} | {_fmt(row.get('grossCagrPct'), '%')} | "
                     f"{_fmt(row.get('costDragCagrPp'), 'pp')} | "
                     f"{_fmt(row.get('cagrPct'), '%')} | "
                     f"{_fmt(row.get('benchmarkCagrPct'), '%')} | "
                     f"{_fmt(row.get('annualizedExcessPct'), 'pp')} | "
                     f"{_fmt(row.get('sharpe'))} | {_fmt(row.get('mddPct'), '%')} | "
                     f"{_fmt(row.get('averageTurnoverPct'), '%')} | "
                     f"{_fmt(row.get('annualOneWayTurnoverX'), 'x')} |")
    costs = report["costDiagnosis"]
    lines += ["", "## Why costs were high", "",
              f"The Combined CHAMPION was evaluated every 21 sessions and made "
              f"{costs['realistic']['turnoverRebalances']} rebalances. Average one-way turnover was "
              f"{_fmt(costs['realistic']['averageTurnoverPct'], '%')}, approximately "
              f"{_fmt(costs['realistic'].get('annualOneWayTurnoverX'), 'x')} NAV per year.", "",
              f"Correcting the cost model changes estimated CAGR drag from "
              f"{_fmt(costs['legacy'].get('costDragCagrPp'), 'pp')} to "
              f"{_fmt(costs['realistic'].get('costDragCagrPp'), 'pp')}; it does not rescue a selector "
              "whose gross stock picks trail the matched index.", "",
              f"Before costs, Combined CHAMPION trails its matched index by "
              f"{_fmt(costs['realistic'].get('grossBenchmarkGapPp'), 'pp')} per year. "
              "That is a stock-selection problem, not a fee-estimation problem.", "",
              "## New rule", "",
              "- Rank on matured, shrunk regional-benchmark excess return after a realistic round-trip cost.",
              "- Require expected net benchmark alpha to be positive.",
              "- Make regular replacement decisions quarterly; carry drifted holdings between decisions.",
              "- Keep an incumbent unless the replacement overcomes the immediate sell-plus-buy friction.",
              "- No production promotion; prospective shadow evidence is still absent.", "",
              "## Uncertainty", ""]
    alpha = report["newChallengerVsBenchmarkBootstrap"]
    lines.append(f"Mean matched-block net alpha is {_fmt(alpha['meanBlockExcessPct'], '%')} "
                 f"with 95% CI [{_fmt(alpha['meanBlockExcessCi95Pct'][0], '%')}, "
                 f"{_fmt(alpha['meanBlockExcessCi95Pct'][1], '%')}], based on "
                 f"{alpha['pairedBlocks']} paired blocks. A CI containing zero is inconclusive.")
    lines += ["", "## Pairwise path differences", ""]
    for name, comparison in report["pairedComparisons"].items():
        d = comparison["pathDifferenceCI"]["annualizedExcessPct"]
        lines.append(f"- {name}: Δ annualized excess {_fmt(d['pointEstimate'], 'pp')}, "
                     f"95% CI [{_fmt(d['ci95'][0], 'pp')}, {_fmt(d['ci95'][1], 'pp')}].")
    lines += ["", "## Cost-model scope", "",
              "The matched benchmark is deliberately frictionless, while the active book pays costs. "
              "This is conservative for the alpha claim. ETF expense drag is already embedded in total-return prices. "
              "Broker-specific FX conversion is excluded because ordinary same-currency name replacement does not "
              "require converting the whole sleeve; cross-region FX implementation should be evaluated separately.", "",
              "US Section 31 fees vary over time; the base case uses a conservative 0.30bp sell levy. "
              "KR statutory sell tax is applied by historical effective-date schedule. Commissions/spreads are "
              "explicit research assumptions, not a claim about every broker.", "",
              "## Decision", ""]
    finding = report["finding"]
    lines += [
        f"**{finding['verdict']}** — {finding['summary']}", "",
        finding["nextDirection"], "",
        "This is a historical design diagnostic, not evidence to promote a selector. "
        "The next rule must be frozen before prospective shadow observations arrive.", ""]
    return "\n".join(lines)


def _compact_decisions(decisions: list[dict]) -> list[dict]:
    """Keep quarterly auditability without publishing repeated monthly bulk."""
    fields = ("ticker", "region", "sector", "score", "alphaPercentile",
              "expectedGrossBenchmarkExcessPct", "estimatedRoundTripCostPct",
              "expectedNetBenchmarkExcessPct", "incumbent", "retentionCreditPct",
              "eligible", "exclusionCodes")
    compact = []
    for decision in decisions:
        if not decision["rebalanceDecision"]:
            continue
        compact.append({
            "date": decision["date"], "signalDate": decision["signalDate"],
            "selectedTickers": decision["selectedTickers"],
            "weights": decision["weights"],
            "topScores": [{key: row.get(key) for key in fields}
                          for row in decision["topScores"][:8]],
            "valuationStatus": decision["valuationStatus"],
        })
    return compact


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger_dir")
    parser.add_argument("--output", default="benchmark-alpha-report.json")
    parser.add_argument("--markdown", default="benchmark-alpha-report.md")
    args = parser.parse_args(argv)
    ledger = Path(args.ledger_dir)
    output, md = _guard(args.output, ledger), _guard(args.markdown, ledger)
    before = _digest_tree(ledger)
    cfg, _ = load_config()
    store = RI.InputStore(ledger, provenance.REPLAY_VERSION, provenance.DATA_VERSION)
    manifest = store.manifest()
    if not manifest or provenance.REPLAY_VERSION != "replay-v16":
        raise ValueError("benchmark-alpha-v1 requires sealed replay-v16 inputs")
    frozen = RI.unpack(store.load(manifest, valuation_only=True))
    valuation = RV.ValuationData(
        frozen["prices"], cfg.benchmarks, frozen["fx"], frozen["risk_free"],
        through=manifest["through"], risk_free_through=frozen["risk_free_source"]["verifiedThrough"],
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
    print(f"running {BA.VERSION} on {len(calendar)} fixed blocks", flush=True)
    new = BA.run_challenger(signals, outcomes, cfg_lt=cfg.longterm,
                            cfg_pf=cfg.kelly_portfolio, calendar=calendar,
                            valuation=valuation)
    if not new["complete"]:
        raise ValueError(f"challenger path incomplete: {new['failures'][:3]}")
    headline = sealed["portfolioReplay"]["headlineRows"]
    champion_rows = headline[PV.CHAMPION]
    old_challenger_rows = headline[PV.CHALLENGER]
    research_cfg = BA.cost_config(cfg.kelly_portfolio)
    legacy = _annotate_costs({}, champion_rows, cfg.kelly_portfolio)
    champion = _annotate_costs({}, champion_rows, research_cfg)
    old = _annotate_costs({}, old_challenger_rows, research_cfg)
    fresh = _annotate_costs({}, new["rows"], research_cfg)
    pairs = {
        "New minus Combined CHAMPION": RVL.paired_bootstrap(
            new["rows"], champion_rows, research_cfg),
        "New minus Existing calibrated challenger": RVL.paired_bootstrap(
            new["rows"], old_challenger_rows, research_cfg),
    }
    old_gross_gap = old["grossCagrPct"] - old["benchmarkCagrPct"]
    report = {
        "version": BA.VERSION, "status": "CHALLENGER",
        "freezeManifest": BA.freeze_manifest(),
        "inputSnapshot": {"sha256": manifest["sha256"], "through": manifest["through"]},
        "comparison": {
            "Combined CHAMPION — realistic costs": _summary_fields(champion),
            "Existing calibrated challenger — realistic costs": _summary_fields(old),
            "Benchmark-relative alpha v1": _summary_fields(fresh),
        },
        "costDiagnosis": {"legacy": _summary_fields(legacy),
                          "realistic": _summary_fields(champion)},
        "newChallengerVsBenchmarkBootstrap": _block_alpha_ci(new["rows"], research_cfg),
        "pairedComparisons": pairs,
        "decisionDiagnostics": {
            "quarterlyDecisions": sum(d["rebalanceDecision"] for d in new["decisions"]),
            "emptyQuarterlyDecisions": sum(
                d["rebalanceDecision"] and not d["selectedTickers"] for d in new["decisions"]),
            "averageCashPct": fresh.get("averageCashPct"),
        },
        "decisionAudit": _compact_decisions(new["decisions"]),
        "finding": {
            "verdict": "BENCHMARK_NOT_BEATEN",
            "summary": (
                "Realistic costs improve every active path, but no tested selector has positive "
                "net annualized excess. The quarterly integrated rule reduces implementation drag "
                "but gives up too much gross selection return."),
            "existingChallengerGrossBenchmarkGapPp": old_gross_gap,
            "existingChallengerNetBenchmarkGapPp": old["annualizedExcessPct"],
            "newChallengerGrossBenchmarkGapPp": fresh["grossCagrPct"] - fresh["benchmarkCagrPct"],
            "newChallengerNetBenchmarkGapPp": fresh["annualizedExcessPct"],
            "nextDirection": (
                "The evidence points to retaining the existing calibrated benchmark-relative signal "
                "and adding a pre-frozen incumbent replacement hurdle/hysteresis, rather than a blunt "
                "quarterly freeze or another factor search. This is a prospective challenger proposal, "
                "not a winner selected from this history."),
        },
        "sealedInvariant": {"before": before, "after": _digest_tree(ledger)},
        "productionChanged": False,
    }
    report["sealedInvariant"]["unchanged"] = (
        report["sealedInvariant"]["before"] == report["sealedInvariant"]["after"])
    if not report["sealedInvariant"]["unchanged"]:
        raise ValueError("SEALED_LEDGER_CHANGED")
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                 allow_nan=False, sort_keys=True) + "\n")
    md.write_text(markdown(report))
    print(markdown(report), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
