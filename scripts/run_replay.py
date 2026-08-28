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

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import benchmark_source as BS         # noqa: E402
from pipeline import historical_outcomes as HO      # noqa: E402
from pipeline import historical_replay as HR        # noqa: E402
from pipeline import historical_store as HS         # noqa: E402
from pipeline import pit_data                       # noqa: E402
from pipeline import provenance as prov_mod         # noqa: E402
from pipeline import universe as universe_mod       # noqa: E402
from pipeline.config import load_config             # noqa: E402
from pipeline.datafeed import (  # noqa: E402
    fetch_macro, fetch_macro_vintages, fetch_regional_prices, fetch_vix)


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
    start = args.start or replay_cfg.get("start", "2013-01-01")

    # Names that were index members at some point but are not today's list. The
    # replay resolves its universe from TODAY, so without these it can only ever
    # see survivors: 326 of the 829 names that have been in the S&P 500 since
    # 2012 are absent from the current list, and they left mostly by being
    # acquired or shrinking out of it. `UniverseHistory` decides membership per
    # date, but it can only include a name the PRICE PANEL can serve, so the
    # historical members have to be downloaded too or the fix is cosmetic.
    universe_history = pit_data.UniverseHistory.from_json(
        replay_cfg.get("universeHistoryPath"))
    fetch_universe = {region: list(names) for region, names in universe.items()}
    historical_only: dict[str, list[str]] = {}
    if universe_history.available:
        for ticker, row in universe_history.memberships.items():
            region = row.get("region")
            if not region or region not in fetch_universe:
                continue
            if ticker not in fetch_universe[region]:
                fetch_universe[region].append(ticker)
                historical_only.setdefault(region, []).append(ticker)
        for region, extra in sorted(historical_only.items()):
            print(f"  {region}: +{len(extra)} former index members to download "
                  f"alongside {len(universe.get(region) or [])} current")

    download = list(dict.fromkeys(
        [t for names in fetch_universe.values() for t in names]
        + list(cfg.benchmarks.values())))
    # Fetch from well before the replay start: the first replay date still needs
    # 273 sessions of trailing history behind it, or every name is unrankable.
    fetch_start = (str(int(str(start)[:4]) - 2) + str(start)[4:]) if start else "2010-01-01"
    print(f"fetching {len(download)} tickers by region from {fetch_start} ...")
    prices = fetch_regional_prices(fetch_universe, fetch_start)

    # Benchmarks go through their own path: vendor redundancy, a plausibility
    # check against the session calendar already on record, and the committed
    # snapshot as the last resort. A truncated index panel is what silently
    # erased the KR half of this ledger on 08-20, 08-23 and 08-24.
    print("resolving regional benchmarks ...")
    benchmark_series, benchmark_diagnostics = BS.resolve(
        cfg.benchmarks, cfg.benchmark_sources, start=fetch_start, ledger_dir=ledger_dir)
    for line in BS.describe(benchmark_diagnostics):
        print(line)
    for ticker, series in benchmark_series.items():
        prices[ticker] = pd.DataFrame({"Close": series})

    missing = [t for t in download if t not in prices]
    if missing:
        print(f"  warning: no price data for {len(missing)} tickers (e.g. {missing[:5]})")
    for region, ticker in cfg.benchmarks.items():
        if ticker not in prices:
            print(f"ERROR: benchmark {ticker} for {region} unavailable from every "
                  f"configured vendor and no snapshot is on record; excess returns "
                  f"would be undefined. Refusing to write a ledger.")
            return 1
    if benchmark_diagnostics["degradedRegions"]:
        print(f"  NOTE: {', '.join(benchmark_diagnostics['degradedRegions'])} running on "
              f"the committed snapshot; the newest grid dates will not extend until the "
              f"vendor recovers. This is recorded as {BS.STATUS_SNAPSHOT} in diagnostics.")

    horizon = int(replay_cfg.get("horizonDays", 126))
    minimum_benchmark_coverage = float(
        replay_cfg.get("minBenchmarkCoveragePct", 95.0))
    preflight = HO.benchmark_session_preflight(
        prices, fetch_universe, cfg.benchmarks, start=start, end=args.end,
        horizon=horizon, min_history_rows=HR.MIN_HISTORY_ROWS,
        min_coverage_pct=minimum_benchmark_coverage,
    )
    for region, row in preflight["regions"].items():
        print(f"benchmark preflight {region} {horizon}D: "
              f"{row['coveragePct']}% ({row['matchedWindows']}/"
              f"{row['candidateWindows']}; {row['benchmarkSessions']} benchmark sessions)")
    if not preflight["eligible"]:
        print("ERROR: benchmark session preflight failed; replay not started.")
        for failure in preflight["failures"]:
            print(f"  {failure['region']}: {failure['reason']} "
                  f"({failure['coveragePct']}% < "
                  f"{failure['minimumCoveragePct']}%)")
            for sample in failure["missingSamples"]:
                print(f"    {sample}")
        return 1

    vix = fetch_vix(fetch_start)
    macro = fetch_macro(cfg, fetch_start)
    macro_vintages = fetch_macro_vintages(cfg, replay_cfg.get("macroVintageSeries") or [])
    if macro is not None and not macro_vintages:
        print("  macro vintages unavailable -> regime conditioning reads REVISED_HISTORY "
              "(the numbers as revised since, not as printed at the time)")
    fundamental_store = pit_data.FundamentalStore.from_jsonl(
        replay_cfg.get("pitFundamentalsPath"))
    if not fundamental_store.available:
        print("  PIT fundamentals unavailable -> value/quality sleeves WITHHELD "
              "from the replay (today's snapshot is never back-applied)")
    if not universe_history.available:
        print(f"  historical constituents unavailable -> {pit_data.SURVIVORSHIP_UNRESOLVED} "
              "recorded on every observation")

    started = time.time()
    # How much of the survivorship fix actually landed: a former member with no
    # price data is dropped by the snapshot, so membership alone proves nothing.
    if historical_only:
        priced = {region: sum(1 for t in extra if t in prices)
                  for region, extra in historical_only.items()}
        for region, count in sorted(priced.items()):
            total = len(historical_only[region])
            print(f"  former members with price history {region}: {count}/{total} "
                  f"({round(count / total * 100, 1)}%)")

    replay = HR.run_replay(
        prices, fetch_universe, benchmarks=cfg.benchmarks, cfg_lt=cfg.longterm,
        start=start, end=args.end,
        frequency=args.frequency or replay_cfg.get("frequency", "W"),
        fundamental_store=fundamental_store, macro=macro, vix=vix,
        macro_vintages=macro_vintages,
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
    coverage_acc = HO.CoverageAccumulator(horizon)
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
        horizon=horizon,
        min_coverage_pct=minimum_benchmark_coverage,
    )
    diagnostics["benchmarkCoverageGate"] = coverage_gate
    diagnostics["benchmarkPanel"] = benchmark_diagnostics

    # A coverage trend, committed. The 08-19 -> 08-20 collapse left no trace in
    # any artifact: finding it afterwards meant rewinding the branch and
    # recounting shards by hand. From here it is a one-line diff per day.
    run_date = str(diagnostics.get("lastDate")
                   or coverage.get("lastSignalDate") or "")
    history = BS.record_coverage(
        ledger_dir, run_date=run_date, horizon=horizon,
        coverage=coverage, benchmark_diagnostics=benchmark_diagnostics)
    regressions = [r for r in (BS.coverage_regression(history, region=region)
                               for region in coverage_gate["assessedRegions"]) if r]
    diagnostics["benchmarkCoverageRegressions"] = regressions
    for row in regressions:
        print(f"  WARNING: {row['region']} benchmark coverage fell "
              f"{row['dropPctPoints']}%p since {row['previousDate']} "
              f"({row['previousCoveragePct']}% -> {row['coveragePct']}%)")

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
