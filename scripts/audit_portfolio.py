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
    signals = HS.load(ledger, HS.SIGNALS, replay_version)
    outcomes = HS.load(ledger, HS.OUTCOMES, replay_version)
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
