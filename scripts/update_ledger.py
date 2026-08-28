"""Append today's signals to the immutable paper-signal ledger and refresh
matured outcomes. Intended to run in CI against a checked-out `signal-history`
branch so history accumulates WITHOUT touching main (no recursive Pages build).

Usage:
    python scripts/update_ledger.py <site-data.json> <ledger-dir>

The ledger dir holds:
    signals.jsonl   append-only immutable signals (never rewritten)
    outcomes.jsonl  recomputed forward returns (derived, safe to refresh)
    summary.json    rolling evaluation metrics
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import ledger as LG  # noqa: E402
from pipeline import provenance as PROV  # noqa: E402


def main(argv=None) -> int:
    argv = argv or sys.argv[1:]
    if len(argv) < 2:
        print("usage: python scripts/update_ledger.py <site-data.json> <ledger-dir>")
        return 2
    data = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    current_model_version = (data.get("modelVersion")
                             or (data.get("provenance") or {}).get("modelVersion"))
    current_data_version = ((data.get("provenance") or {}).get("dataVersion")
                            or data.get("dataVersion"))
    ledger_dir = Path(argv[1])
    sig_path = ledger_dir / "signals.jsonl"
    out_path = ledger_dir / "outcomes.jsonl"
    summ_path = ledger_dir / "summary.json"
    portfolio_sig_path = ledger_dir / "portfolio-signals.jsonl"
    portfolio_out_path = ledger_dir / "portfolio-outcomes.jsonl"

    # Refuse to record synthetic/seed data into the real ledger.
    data_mode = data.get("dataMode") or (data.get("provenance") or {}).get("dataMode")
    if data.get("seed") or data_mode in {"seed", "synthetic", "stale"} or (data.get("meta") or {}).get("syntheticData"):
        print("refusing to append seed/synthetic data to the ledger")
        return 0
    if not current_model_version:
        print("refusing to append an unversioned signal generation")
        return 1

    today = (data.get("audit") or {}).get("todaySignals") or LG.records_from_payload(data)
    existing = LG.load_jsonl(sig_path)
    merged, appended, skipped = LG.append_signals(existing, today)
    LG.write_jsonl(sig_path, merged)
    print(f"signals: +{appended} appended, {skipped} already present, {len(merged)} total")

    portfolio_record = LG.portfolio_record_from_payload(data)
    portfolio_existing = LG.load_jsonl(portfolio_sig_path)
    portfolio_new = [portfolio_record] if portfolio_record else []
    portfolio_merged, portfolio_appended, portfolio_skipped = LG.append_portfolio_signals(
        portfolio_existing, portfolio_new)
    LG.write_jsonl(portfolio_sig_path, portfolio_merged)
    print(f"portfolio signals: +{portfolio_appended} appended, {portfolio_skipped} already present, {len(portfolio_merged)} total")

    # Best-effort outcome refresh (needs price history for tracked tickers).
    try:
        from pipeline.datafeed import fetch_prices
        from pipeline.config import load_config
        cfg, _ = load_config()
        tickers = sorted({r["ticker"] for r in merged} |
                         {ticker for row in portfolio_merged for ticker in (row.get("finalWeights") or {})})
        prices = fetch_prices(tickers, cfg.model.screen_history_start)
        benches = {}
        benchmark_tickers = ({r.get("benchmark") for r in merged if r.get("benchmark")} |
                             {b for row in portfolio_merged for b in (row.get("benchmarks") or {}).values() if b})
        for b in benchmark_tickers:
            bp = fetch_prices([b], cfg.model.screen_history_start).get(b)
            if bp is not None:
                benches[b] = bp["Close"]
        outcomes = LG.compute_outcomes(merged, prices, benches)
        LG.write_jsonl(out_path, outcomes)
        portfolio_outcomes = LG.compute_portfolio_outcomes(portfolio_merged, prices, benches)
        LG.write_jsonl(portfolio_out_path, portfolio_outcomes)
        current_outcomes, excluded_outcomes = LG.filter_model_generation(
            outcomes, current_model_version)
        current_portfolio_outcomes, excluded_portfolios = LG.filter_model_generation(
            portfolio_outcomes, current_model_version)
        summary = {
            "modelVersion": current_model_version,
            "dataVersion": current_data_version,
            "generationIsolation": {
                "method": "EXACT_SCORING_VERSION",
                "scoringVersion": PROV.scoring_identity(current_model_version),
                "plumbingComponentsIgnored": list(PROV.PLUMBING_COMPONENTS),
                "excludedPriorModelOutcomes": excluded_outcomes,
                "excludedPriorModelPortfolioOutcomes": excluded_portfolios,
            },
            "validationStatus": LG.validation_status(
                outcomes, min_paper_days=int(cfg.validation.get("minPaperDays", 126)),
                signals=merged, model_version=current_model_version),
            "horizons": {str(h): LG.evaluate(current_outcomes, horizon=h) for h in LG.HORIZONS},
            "portfolioHorizons": {str(h): LG.evaluate_portfolios(current_portfolio_outcomes, horizon=h)
                                   for h in LG.HORIZONS},
        }
        summ_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"outcomes: {len(current_outcomes)} current signals / "
              f"{len(current_portfolio_outcomes)} current portfolios matured; "
              f"{excluded_outcomes + excluded_portfolios} prior-generation rows excluded from summary")
    except Exception as exc:  # pragma: no cover - network dependent
        print(f"outcome refresh skipped (network/data): {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
