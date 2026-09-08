"""Build alpha-ranking and concentrated-portfolio validation for the active replay."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import historical_store as HS  # noqa: E402
from pipeline import portfolio_validation as PV  # noqa: E402
from pipeline import replay_inputs as RI
from pipeline import replay_valuation as RV
from pipeline import provenance  # noqa: E402
from pipeline.config import load_config  # noqa: E402


def _peak_gb() -> float | None:
    """Peak resident memory so far, in GB, or None where it is unavailable.

    The ledger is loaded whole, so this step's footprint scales with the
    cross-section. Restoring former index members widens it, and an audit
    that OOMs on a hosted runner fails the whole replay after the expensive
    part has already run. Printing the number every run makes the trend
    visible in the logs before it becomes a crash.
    """
    try:
        import resource
    except ImportError:  # pragma: no cover - not POSIX
        return None
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # ru_maxrss is KILOBYTES on Linux and BYTES on macOS. Both divisors here
    # were one factor of 1024 short, so the first real run logged
    # "peak RSS 6949.93 GB" for a 6.79 GB process. A number that wrong is not
    # a rounding slip — it is the observability this was added for, reporting
    # something no one can act on.
    scale = 1024**3 if sys.platform == "darwin" else 1024**2
    return peak / scale


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger_dir")
    parser.add_argument("--output", default=None)
    args = parser.parse_args(argv)

    cfg, _ = load_config()
    ledger = Path(args.ledger_dir)
    diagnostics_path = HS.diagnostics_path(ledger)
    diagnostics = (json.loads(diagnostics_path.read_text(encoding="utf-8"))
                   if diagnostics_path.exists() else {})
    replay_version = provenance.REPLAY_VERSION
    model_version = provenance.MODEL_VERSION
    # Projected: this path reads one key inside `features` and the block is 28
    # of a signal's 37 keys. Keeping it whole costs ~1.7 GB on the current
    # ledger and more once former index members widen the cross-section.
    signals = HS.load(ledger, HS.SIGNALS, replay_version,
                      project=HS.audit_projection)
    outcomes = HS.load(ledger, HS.OUTCOMES, replay_version)
    peak = _peak_gb()
    if peak is not None:
        print(f"  ledger loaded: {len(signals):,} signals, "
              f"{len(outcomes):,} outcomes, peak RSS {peak:.2f} GB")
    output = Path(args.output) if args.output else ledger / "historical-portfolio-validation.json"
    # The report this run is about to overwrite is the only record of the
    # evaluation calendar the last run graded on — the ledger stores outcomes,
    # never the schedule. Read it BEFORE writing, or the baseline is gone.
    previous = None
    if output.exists():
        try:
            previous = json.loads(output.read_text(encoding="utf-8"))
        except ValueError:
            print(f"  WARNING: {output} is not readable JSON; "
                  f"determinism has no baseline this run")
    valuation = None
    store = RI.InputStore(ledger, replay_version, provenance.DATA_VERSION)
    manifest = store.manifest()
    if manifest:
        config_hash = RI.digest(json.loads((ROOT / "config.json").read_text()))
        if manifest["policy"].get("configSha256") != config_hash:
            raise RI.InputVersionConflict("audit config differs from frozen replay config")
        frozen = RI.unpack(store.load(manifest, valuation_only=True))
        if (diagnostics.get("inputSnapshot") or {}).get("sha256") != manifest["sha256"]:
            raise RI.InputVersionConflict("diagnostics and input manifest disagree")
        valuation = RV.ValuationData(frozen["prices"], cfg.benchmarks, frozen["fx"], frozen["risk_free"],
            through=manifest["through"], risk_free_through=frozen["risk_free_source"]["verifiedThrough"],
            corporate_actions=frozen.get("corporate_actions"))
    if previous and previous.get("replayVersion") != replay_version:
        archive = ledger / "historical" / previous["replayVersion"] / "portfolio-validation.json"
        archive.parent.mkdir(parents=True, exist_ok=True)
        if not archive.exists():
            archive.write_text(json.dumps(previous, ensure_ascii=False, indent=2) + "\n")
    report = PV.build_report(
        signals, outcomes, cfg_lt=cfg.longterm, cfg_pf=cfg.kelly_portfolio,
        diagnostics=diagnostics, replay_version=replay_version,
        model_version=model_version, previous_report=previous, valuation=valuation)
    archived = ledger / "historical" / replay_version / "reports"
    archived.mkdir(parents=True, exist_ok=True)
    (archived / (RI.digest(report) + ".json")).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    alpha = report["alphaDiagnostics"]["regions"]
    portfolio = report["portfolioReplay"]["selectors"]
    print(f"validation report: {output}")
    for region in ("KR", "US"):
        row = alpha.get(f"{region}:126") or {}
        ic = row.get("rankIC") or {}
        mono = row.get("monotonicity") or {}
        print(f"{region} 126D Rank IC {ic.get('mean')} | IR {ic.get('ir')} | "
              f"top5-bottom50 {mono.get('top5MinusBottom50Pct')}%p | "
              f"monotonicity {mono.get('status')}")
    for method, blob in portfolio.items():
        summary = blob.get("summary") or {}
        print(f"{method}: CAGR {summary.get('cagrPct')}% | excess "
              f"{summary.get('annualizedExcessPct')}%p | MDD {summary.get('mddPct')}% | "
              f"Sharpe {summary.get('sharpe')} | turnover {summary.get('averageTurnoverPct')}%")
    determinism = report.get("replayDeterminism") or {}
    print(f"determinism: {determinism.get('verdict')} "
          f"(schedule {(determinism.get('scheduleCheck') or {}).get('verdict')}, "
          f"cross-section {(determinism.get('crossSectionCheck') or {}).get('verdict')})")
    if not determinism.get("reproducible", True):
        sched = determinism.get("scheduleCheck") or {}
        cross = determinism.get("crossSectionCheck") or {}
        print("ERROR: the replay is not reproducible — the already-published "
              "past changed under this run")
        if sched.get("verdict") == "SCHEDULE_DIVERGED":
            print(f"  schedule: block #{sched.get('firstDivergenceIndex')} "
                  f"expected {sched.get('expected')} got {sched.get('actual')}")
        if cross.get("verdict") == "SCHEDULE_DIVERGED":
            print(f"  cross-section: {cross.get('driftedDates')} past dates "
                  f"changed membership from {cross.get('firstDriftedDate')} "
                  f"(net {cross.get('netNameChange'):+d} names)")
            for row in (cross.get("driftedSample") or [])[:5]:
                print(f"    {row['date']}: {row['was']} -> {row['now']} names")

    contract = report.get("contractValidation") or {}
    if not contract.get("eligible", False):
        print("ERROR: portfolio validation contract failed; report is BLOCKED")
        for failure in contract.get("failures") or []:
            print(f"  {failure}")
        for method, blob in portfolio.items():
            coverage = ((blob.get("horizons") or {}).get("21") or {}).get("outcomeCoverage") or {}
            print(f"  {method}: {coverage.get('completeOutcomes', 0)}/{coverage.get('eligibleDecisions', 0)} "
                  f"matured blocks complete; {coverage.get('notMaturedDecisions', 0)} pending")
            for block in [b for b in coverage.get("blocks", []) if b.get("status") == "INCOMPLETE"][:8]:
                print(f"    {block['date']}..{block['endDate']}: {', '.join(block.get('reasons', []))}")
                for gap in block.get("inputGaps", []):
                    print(f"      {gap['input']} {gap['ticker']}: {', '.join(gap['dates'][:8])} "
                          f"({len(gap['dates'])} missing sessions)")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
