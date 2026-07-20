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


def main(argv=None) -> int:
    argv = argv or sys.argv[1:]
    if len(argv) < 2:
        print("usage: python scripts/update_ledger.py <site-data.json> <ledger-dir>")
        return 2
    data = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    ledger_dir = Path(argv[1])
    sig_path = ledger_dir / "signals.jsonl"
    out_path = ledger_dir / "outcomes.jsonl"
    summ_path = ledger_dir / "summary.json"

    # Refuse to record synthetic/seed data into the real ledger.
    data_mode = data.get("dataMode") or (data.get("provenance") or {}).get("dataMode")
    if data.get("seed") or data_mode in {"seed", "synthetic", "stale"} or (data.get("meta") or {}).get("syntheticData"):
        print("refusing to append seed/synthetic data to the ledger")
        return 0

    today = (data.get("audit") or {}).get("todaySignals") or LG.records_from_payload(data)
    existing = LG.load_jsonl(sig_path)
    merged, appended, skipped = LG.append_signals(existing, today)
    LG.write_jsonl(sig_path, merged)
    print(f"signals: +{appended} appended, {skipped} already present, {len(merged)} total")

    # Best-effort outcome refresh (needs price history for tracked tickers).
    try:
        from pipeline.datafeed import fetch_prices
        from pipeline.config import load_config
        cfg, _ = load_config()
        tickers = sorted({r["ticker"] for r in merged})
        prices = fetch_prices(tickers, cfg.model.screen_history_start)
        benches = {}
        for b in {r.get("benchmark") for r in merged if r.get("benchmark")}:
            bp = fetch_prices([b], cfg.model.screen_history_start).get(b)
            if bp is not None:
                benches[b] = bp["Close"]
        outcomes = LG.compute_outcomes(merged, prices, benches)
        LG.write_jsonl(out_path, outcomes)
        summary = {
            "validationStatus": LG.validation_status(
                outcomes, min_paper_days=int(cfg.validation.get("minPaperDays", 126))),
            "horizons": {str(h): LG.evaluate(outcomes, horizon=h) for h in LG.HORIZONS},
        }
        summ_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"outcomes: {len(outcomes)} matured; summary written")
    except Exception as exc:  # pragma: no cover - network dependent
        print(f"outcome refresh skipped (network/data): {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
