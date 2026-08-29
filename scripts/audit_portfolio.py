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
    # Linux reports kilobytes, macOS bytes.
    scale = 1024**2 if sys.platform == "darwin" else 1024
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
    report = PV.build_report(
        signals, outcomes, cfg_lt=cfg.longterm, cfg_pf=cfg.kelly_portfolio,
        diagnostics=diagnostics, replay_version=replay_version,
        model_version=model_version)
    output = Path(args.output) if args.output else ledger / "historical-portfolio-validation.json"
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
    contract = report.get("contractValidation") or {}
    if not contract.get("eligible", False):
        print("ERROR: portfolio validation contract failed; report is BLOCKED")
        for failure in contract.get("failures") or []:
            print(f"  {failure}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
