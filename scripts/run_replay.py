"""Run (or extend) the historical point-in-time replay ledger.

Intended for CI against a checked-out ``signal-history`` branch, exactly like
``scripts/update_ledger.py`` — but writing to SEPARATE files, because historical
OOS evidence and prospective paper evidence are different claims and must never
share a file:

    ledger/historical/<replayVersion>/signals-<YYYY-MM>.jsonl.gz
        append-only, immutable, one shard per signal month
    ledger/historical/<replayVersion>/outcomes-<YYYY-MM>.jsonl.gz
        derived, recomputed as more future arrives
    ledger/historical/manifest.json    shard index: counts and bytes
    ledger/historical-diagnostics.json PIT coverage, survivorship, deviations

See ``pipeline/historical_store.py`` for why the ledger is sharded and gzipped:
a decade of weekly cross-sections is far past the 100 MB blob limit as a single
file, and a monolith would also have to be rewritten in full every night.

INCREMENTAL BY DEFAULT
----------------------
A full decade replay is expensive; re-running it daily would be wasteful and
would risk rewriting frozen records. So the script reads the existing signal ids
first and skips anything already present. New dates are appended; old records are
never touched. A ``--full`` run is only needed when the replay logic itself
changes, and even then the old generation is preserved — the new one lands under
a new ``replayVersion`` and the two are never pooled.

Usage:
    python scripts/run_replay.py <ledger-dir> [--start 2013-01-01] [--frequency W]
                                 [--full] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import historical_outcomes as HO      # noqa: E402
from pipeline import historical_replay as HR        # noqa: E402
from pipeline import historical_store as HS         # noqa: E402
from pipeline import pit_data                       # noqa: E402
from pipeline import provenance as prov_mod         # noqa: E402
from pipeline import universe as universe_mod       # noqa: E402
from pipeline.config import load_config             # noqa: E402
from pipeline.datafeed import fetch_macro, fetch_prices, fetch_vix  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger_dir")
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    parser.add_argument("--frequency", default=None, choices=["D", "W", "M"])
    parser.add_argument("--full", action="store_true",
                        help="recompute every date instead of only new ones")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    cfg, _ = load_config()
    replay_cfg = cfg.historical_replay or {}
    if not replay_cfg.get("enabled", True):
        print("historical replay disabled in config")
        return 0

    ledger_dir = Path(args.ledger_dir)
    ledger_dir.mkdir(parents=True, exist_ok=True)
    diagnostics_path = HS.diagnostics_path(ledger_dir)

    # A ledger written by the pre-shard layout is re-filed, not rewritten, so an
    # existing decade of evidence survives the change intact.
    migrated = HS.migrate_legacy(ledger_dir)
    if any(migrated.values()):
        print(f"migrated legacy ledger into shards: {migrated}")

    ids = HS.ids_by_generation(ledger_dir, HS.SIGNALS)
    current_ids = ids.get(prov_mod.REPLAY_VERSION, set())
    stale_generation = sum(len(v) for k, v in ids.items() if k != prov_mod.REPLAY_VERSION)
    existing_ids = set() if args.full else set(current_ids)
    print(f"existing signals: {len(current_ids) + stale_generation} "
          f"({len(current_ids)} current generation, {stale_generation} earlier)")

    universe, _ = universe_mod.resolve(cfg)
    download = list(dict.fromkeys(
        [t for names in universe.values() for t in names] + list(cfg.benchmarks.values())))
    start = args.start or replay_cfg.get("start", "2013-01-01")
    # Fetch from well before the replay start: the first replay date still needs
    # 273 sessions of trailing history behind it, or every name is unrankable.
    fetch_start = (str(int(str(start)[:4]) - 2) + str(start)[4:]) if start else "2010-01-01"
    print(f"fetching {len(download)} tickers from {fetch_start} ...")
    prices = fetch_prices(download, fetch_start)
    missing = [t for t in download if t not in prices]
    if missing:
        print(f"  warning: no price data for {len(missing)} tickers (e.g. {missing[:5]})")
    for region, ticker in cfg.benchmarks.items():
        if ticker not in prices:
            print(f"ERROR: benchmark {ticker} for {region} unavailable; "
                  f"excess returns would be undefined. Refusing to write a ledger.")
            return 1

    vix = fetch_vix(fetch_start)
    macro = fetch_macro(cfg, fetch_start)
    fundamental_store = pit_data.FundamentalStore.from_jsonl(
        replay_cfg.get("pitFundamentalsPath"))
    universe_history = pit_data.UniverseHistory.from_json(
        replay_cfg.get("universeHistoryPath"))
    if not fundamental_store.available:
        print("  PIT fundamentals unavailable -> value/quality sleeves WITHHELD "
              "from the replay (today's snapshot is never back-applied)")
    if not universe_history.available:
        print(f"  historical constituents unavailable -> {pit_data.SURVIVORSHIP_UNRESOLVED} "
              "recorded on every observation")

    started = time.time()
    replay = HR.run_replay(
        prices, universe, benchmarks=cfg.benchmarks, cfg_lt=cfg.longterm,
        start=start, end=args.end,
        frequency=args.frequency or replay_cfg.get("frequency", "W"),
        fundamental_store=fundamental_store, macro=macro, vix=vix,
        universe_history=universe_history, model_version=prov_mod.MODEL_VERSION,
        existing_ids=existing_ids, progress=True,
    )
    diagnostics = replay["diagnostics"]
    print(f"replay finished in {time.time() - started:.0f}s: "
          f"{diagnostics['signalsGenerated']} new, "
          f"{diagnostics['signalsSkippedAlreadyPresent']} already present")

    if args.dry_run:
        fresh = sum(1 for row in replay["signals"] if row.get("id") not in existing_ids)
        print(f"dry run: would append {fresh} signals "
              f"({len(replay['signals']) - fresh} skipped)")
        return 0

    appended, skipped = HS.append_signals(ledger_dir, replay["signals"])
    print(f"signals: +{appended} appended, {skipped} skipped")

    # Outcomes are derived and safe to recompute — more future has arrived since
    # the last run, so previously immature signals may now resolve. Recomputing
    # shard by shard bounds memory to one month of records and leaves fully
    # matured shards byte-identical, so git records no change for them.
    bench_closes = {ticker: prices[ticker]["Close"]
                    for ticker in cfg.benchmarks.values() if ticker in prices}
    cost_policy = (cfg.kelly_portfolio or {}).get("transactionCosts") or {}
    coverage_acc = HO.CoverageAccumulator(int(replay_cfg.get("horizonDays", 126)))
    shards = HS.iter_shards(ledger_dir, HS.SIGNALS, prov_mod.REPLAY_VERSION)
    outcome_records = rewritten = 0
    for _, key, path in shards:
        shard_signals = HS.read_jsonl(path)
        shard_outcomes = HO.compute_outcomes(shard_signals, prices, bench_closes,
                                             cost_policy=cost_policy)
        if HS.write_outcomes_shard(ledger_dir, prov_mod.REPLAY_VERSION, key, shard_outcomes):
            rewritten += 1
        outcome_records += len(shard_outcomes)
        coverage_acc.add_signals(shard_signals).add_outcomes(shard_outcomes)
    HS.prune_orphan_outcomes(ledger_dir, prov_mod.REPLAY_VERSION,
                             keep={key for _, key, _ in shards})

    coverage = coverage_acc.summary()
    diagnostics["coverage"] = coverage
    coverage_gate = HO.benchmark_coverage_gate(
        coverage,
        horizon=int(replay_cfg.get("horizonDays", 126)),
        min_coverage_pct=float(replay_cfg.get("minBenchmarkCoveragePct", 95.0)),
    )
    diagnostics["benchmarkCoverageGate"] = coverage_gate
    diagnostics_path.write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8")
    manifest = HS.write_manifest(ledger_dir, diagnostics=diagnostics)
    print(f"outcomes: {outcome_records} records; "
          f"{coverage['maturedByHorizon'].get('126', 0)} matured at 126D "
          f"({rewritten}/{len(shards)} shards rewritten)")
    print(f"ledger: {len(shards)} signal shards, "
          f"{manifest['totalBytes'] / 1024 / 1024:.1f} MB on disk")
    print(f"PIT coverage {diagnostics['meanPitCoverage']} "
          f"({pit_data.quality_label(diagnostics['meanPitCoverage'])}), "
          f"survivorship risk {diagnostics['survivorshipRisk']}")
    for region in coverage_gate["assessedRegions"]:
        row = ((coverage.get("benchmarkCoverageByRegion") or {}).get(region) or {}).get(
            str(coverage_gate["horizon"]), {})
        print(f"benchmark coverage {region} {coverage_gate['horizon']}D: "
              f"{row.get('coveragePct')}% "
              f"({row.get('matchedBenchmarkReturns')}/"
              f"{row.get('maturedAbsoluteReturns')})")

    if not coverage_gate["eligible"]:
        print("ERROR: historical benchmark coverage gate failed; "
              "refusing to publish misleading excess-return evidence.")
        for failure in coverage_gate["failures"]:
            print(f"  {failure['region']} {failure['horizon']}D: "
                  f"{failure['coveragePct']}% < {failure['minimumCoveragePct']}% "
                  f"({failure['missingBenchmarkReturns']} missing)")
        if not coverage_gate["failures"]:
            print(f"  {coverage_gate['reason']}")
        return 1

    # Fail here — with the offending shard named — rather than at GitHub's
    # pre-receive hook after the expensive half of the job has already run.
    HS.assert_pushable(ledger_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
