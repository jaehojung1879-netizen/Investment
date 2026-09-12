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
import collections
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
from pipeline import korea_prices as KR            # noqa: E402
from pipeline import replay_calendar as RC
from pipeline import replay_inputs as RI
from pipeline import replay_recovery as RR
from pipeline import replay_rates
from pipeline import pit_data                       # noqa: E402
from pipeline import provenance as prov_mod         # noqa: E402
from pipeline import universe as universe_mod       # noqa: E402
from pipeline.config import load_config             # noqa: E402
from pipeline.datafeed import (  # noqa: E402
    fetch_macro, fetch_macro_vintages, fetch_regional_prices, fetch_vix, fetch_prices)


def former_member_recovery(historical_only: dict, prices: dict,
                           memberships: dict) -> dict:
    """How much of the survivorship fix actually landed, and WHERE.

    A former member the price panel cannot serve is dropped by the snapshot, so
    membership alone proves nothing. But a single percentage hides the thing
    that decides whether the fix helped: the year the recovered names left.
    2013 needs 219 of the 326 departed US names and 2023 needs 71, so a vendor
    that serves only recent delistings can report 40% recovered while leaving
    the early cross-sections exactly as biased as before.
    """
    out: dict[str, dict] = {}
    for region, extra in sorted((historical_only or {}).items()):
        total = len(extra)
        if not total:
            continue
        priced = sum(1 for ticker in extra if ticker in prices)
        by_year: dict[str, list[int]] = {}
        for ticker in extra:
            left = (memberships.get(ticker) or {}).get("delisted")
            if not left:
                continue
            row = by_year.setdefault(str(left)[:4], [0, 0])
            row[1] += 1
            if ticker in prices:
                row[0] += 1
        out[region] = {
            "describedFormerMembers": total,
            "priced": priced,
            "pricedPct": round(priced / total * 100, 2),
            "byYearLeft": {year: {"priced": got, "described": want}
                           for year, (got, want) in sorted(by_year.items())},
        }
    return out


def _run(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger_dir")
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    parser.add_argument("--frequency", default=None, choices=["D", "W", "M"])
    parser.add_argument("--full", action="store_true",
                        help="recompute every date instead of only new ones")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--frozen-inputs", action="store_true", help="reproduce committed inputs without any network access")
    parser.add_argument("--pit-fundamentals", default=None,
                        help="PIT_FUNDAMENTALS_V1 jsonl (없으면 config 값)")
    args = parser.parse_args(argv)

    cfg, _ = load_config()
    corporate_actions = RR.load_corporate_actions()
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

    start = args.start or replay_cfg.get("start", "2013-01-01")
    frequency = args.frequency or replay_cfg.get("frequency", "W")
    store = RI.InputStore(ledger_dir, prov_mod.REPLAY_VERSION, prov_mod.DATA_VERSION)
    prior_inputs = store.manifest()
    prior_benchmark_lineage = {
        row["ticker"]: row
        for row in (store.load_component("benchmark/source", prior_inputs)
                    if prior_inputs else [])
        if row.get("ticker") and row.get("source") and row.get("symbol")
    }
    if current_ids and not prior_inputs:
        raise RI.InputVersionConflict("existing signals have no input snapshot; new DATA_VERSION/REPLAY_VERSION required")
    through = args.end or (pd.Timestamp.now(tz="UTC").normalize() - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    policy = {"start":start, "frequency":frequency, "calendarVersion":RC.CALENDAR_VERSION,
              "modelVersion":prov_mod.MODEL_VERSION, "featureVersion":prov_mod.FEATURE_VERSION,
              "configSha256":RI.digest(json.loads((ROOT / "config.json").read_text())),
              "recoveryVersion":RR.RECOVERY_VERSION,
              "corporateActionsSha256":RI.digest(corporate_actions)}
    if args.frozen_inputs:
        if not prior_inputs:
            raise RI.InputVersionConflict("no frozen inputs; first run must acquire a snapshot")
        if args.end and args.end != prior_inputs["through"]:
            raise RI.InputVersionConflict("--frozen-inputs must use its recorded cutoff")
        if policy != prior_inputs["policy"]:
            raise RI.InputVersionConflict("frozen replay policy/config differs from snapshot")
        through = prior_inputs["through"]
        manifest = prior_inputs
        frozen = RI.unpack(store.load(manifest))
        benchmark_diagnostics = {"byRegion":{}, "degradedRegions":[], "unavailableRegions":[],
                                 "policy":"FROZEN_INPUT_SNAPSHOT", "snapshotsUpdated":[]}
        historical_only = {}
    else:
        # Read and checked before the first network call. Widening the universe is
        # not an extension of this generation, it is a new one: `alphaPercentile`
        # is a rank inside the date's cross-section and selection floors it, so
        # restoring 219 names to 2013 changes what every surviving name's 2013
        # score meant — while those old records are skipped by id and keep the
        # ranks they were given against a universe that no longer exists. Refusing
        # after a forty-minute fetch would teach the same lesson at forty times
        # the price.
        universe_history = pit_data.UniverseHistory.from_json(
            replay_cfg.get("universeHistoryPath"))
        universe_signature = universe_history.signature
        conflict = HS.universe_conflict(
            ledger_dir, prov_mod.REPLAY_VERSION, universe_signature,
            existing=len(current_ids), survivors_only=pit_data.SURVIVORS_ONLY)
        if conflict:
            # Not bypassable by --full. Signals are immutable (`append_signals`
            # skips an id already on disk), so --full recomputes the old dates and
            # then discards every one of them as a duplicate: it cannot rewrite the
            # existing records under the new universe, only hide the check that
            # says they are stale. The one cure is a new generation.
            print(f"error: {conflict}", file=sys.stderr)
            return 1

        universe, _ = universe_mod.resolve(cfg)

        # Names that were index members at some point but are not today's list. The
        # replay resolves its universe from TODAY, so without these it can only ever
        # see survivors: 326 of the 829 names that have been in the S&P 500 since
        # 2012 are absent from the current list, and they left mostly by being
        # acquired or shrinking out of it. `UniverseHistory` decides membership per
        # date, but it can only include a name the PRICE PANEL can serve, so the
        # historical members have to be downloaded too or the fix is cosmetic.
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
            + list(cfg.benchmarks.values())
            + [t for names in RR.successor_dependencies(corporate_actions).values()
               for t in names]))
        # Fetch from well before the replay start: the first replay date still needs
        # 273 sessions of trailing history behind it, or every name is unrankable.
        fetch_start = (str(int(str(start)[:4]) - 2) + str(start)[4:]) if start else "2010-01-01"
        print(f"fetching {len(download)} tickers by region from {fetch_start} ...")
        # Korean sessions come from the exchange-native vendor; every other
        # region stays on Yahoo. See pipeline/korea_prices.py for the measured
        # reason, and note the two are NOT spliced into one panel per ticker:
        # a name is served whole by one vendor or not at all.
        yahoo_regions = {region: names for region, names in fetch_universe.items()
                         if region != "KR"}
        prices = fetch_regional_prices(yahoo_regions, fetch_start, total_return=True)
        korea = KR.acquire(fetch_universe.get("KR") or [], fetch_start)
        prices.update(korea["prices"])
        korea_agreement = KR.agreement_summary(korea["agreement"])
        if korea["prices"]:
            print(f"  KR sessions via {korea['source']}: {len(korea['prices'])} tickers, "
                  f"vendor cross-check median {korea_agreement.get('medianOfMedianDifferenceBps')} bps, "
                  f"worst {korea_agreement.get('worstTicker')} "
                  f"{korea_agreement.get('worstDifferenceBps')} bps")
        # Fail where the failure is, not fifteen minutes later in a message
        # about the benchmark. replay-v13's first attempt lost every Korean
        # ticker to `400 Bad Request` and reported it as
        # "benchmark preflight KR 126D: None% (0/0)".
        unusable = KR.acquisition_failure(korea)
        if unusable:
            print(f"ERROR: {unusable}. Refusing to start a replay without the "
                  f"Korean cross-section.")
            for ticker in korea["missing"][:8]:
                print(f"    no sessions: {ticker}")
            return 1
        if korea["missing"]:
            print(f"  warning: no Korean sessions for {len(korea['missing'])} "
                  f"tickers (e.g. {korea['missing'][:5]})")
        # A vendor that answers with a short window answers successfully, and
        # replay-v12 sealed 46,356 fewer Korean rows than v11 without one error
        # — the contract still passed on 154/154 matured blocks. Refuse to seal
        # a primary the cross-check proves is truncated.
        shortfall = KR.coverage_shortfall(korea["agreement"])
        for row in shortfall["lateStartsWithoutSharedBoundary"]:
            # One name, its own date: a listing, not a cut-off. Said out loud
            # because the cross-check vendor quoting it earlier is worth seeing.
            print(f"  note: {row['ticker']} starts {row['primaryFirstSession']}, "
                  f"{row['sessions']} sessions after the cross-check vendor's "
                  f"{row['secondaryFirstSession']} — no shared boundary, read as "
                  f"a listing date")
        if shortfall["tickers"]:
            print(f"ERROR: the Korean primary vendor returned a truncated history for "
                  f"{shortfall['tickers']} tickers sharing "
                  f"{shortfall['sharedStartDates']} as a start date "
                  f"({shortfall['missingSessions']} sessions short of the "
                  f"cross-check vendor). A shared boundary is a capped download, "
                  f"not a listing. Refusing to seal it.")
            for row in shortfall["worst"]:
                print(f"    {row['ticker']}: starts {row['primaryFirstSession']} "
                      f"vs {row['secondaryFirstSession']} "
                      f"({row['sessions']} sessions late)")
            return 1
        # Successor securities value a held pre-merger position but must never
        # be added to the historical selection universe merely for that reason.
        by_region = RR.successor_dependencies(corporate_actions)
        dependencies = {region: [t for t in names if t not in prices]
                        for region, names in by_region.items()}
        dependencies = {region: names for region, names in dependencies.items() if names}
        if dependencies:
            total = sum(len(names) for names in dependencies.values())
            print(f"  fetching {total} corporate-action price dependencies ...")
            for region, names in dependencies.items():
                # A successor is valued on the same vendor as the region it
                # trades in, or the held position's terminal mark comes from a
                # different price basis than the position itself.
                if region == "KR":
                    prices.update(KR.acquire(names, fetch_start)["prices"])
                else:
                    prices.update(fetch_prices(names, fetch_start, total_return=True))

        # Benchmarks go through their own path: vendor redundancy, a plausibility
        # check against the session calendar already on record, and the committed
        # snapshot as the last resort. A truncated index panel is what silently
        # erased the KR half of this ledger on 08-20, 08-23 and 08-24.
        print("resolving regional benchmarks ...")
        benchmark_series, benchmark_diagnostics = BS.resolve(
            cfg.benchmarks, cfg.benchmark_sources, start=fetch_start,
            ledger_dir=ledger_dir, pinned_sources=prior_benchmark_lineage,
            persist=False)
        for line in BS.describe(benchmark_diagnostics):
            print(line)
        if not prior_inputs and any(
                row.get("status") == BS.STATUS_SNAPSHOT
                for row in benchmark_diagnostics["byRegion"].values()):
            print("ERROR: a new replay generation must establish its own benchmark "
                  "vendor lineage; an older generation's shared snapshot is fallback "
                  "evidence, not a bootstrap source.")
            return 1
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

        # The recovery existed to bridge Yahoo's market-wide Korean holes. The
        # exchange-native vendor does not have them, so the detector still runs
        # — a market-wide hole in the PRIMARY must be visible — but nothing is
        # reconstructed. A genuine outage now fails the coverage gate loudly
        # instead of being bridged from a vendor that disagrees with it.
        price_recovery = RR.detect_systemic_kr_gaps(
            prices, fetch_universe.get("KR") or [], cfg.benchmarks["KR"],
            start=start, through=through)
        print(f"  KR market-wide gap dates in the primary vendor: "
              f"{len(price_recovery['systemicDates'])}")
        for row in price_recovery["systemicDates"]:
            print(f"    {row['date']}: {row['missingNames']}/{row['activeNames']} names")

        horizon = int(replay_cfg.get("horizonDays", 126))
        minimum_benchmark_coverage = float(
            replay_cfg.get("minBenchmarkCoveragePct", 95.0))
        preflight = HO.benchmark_session_preflight(
            prices, fetch_universe, cfg.benchmarks, start=start, end=through,
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
        # The PIT fundamentals file is derived from the collected filings on
        # signal-history, so its path is known to the job rather than to config.
        # An explicit argument wins; config remains the fallback for a local run.
        fundamental_store = pit_data.FundamentalStore.from_jsonl(
            args.pit_fundamentals or replay_cfg.get("pitFundamentalsPath"))
        if fundamental_store.available:
            print(f"PIT 재무 {len(fundamental_store):,}건 · "
                  f"{len(fundamental_store.tickers())}종목")
        else:
            print("PIT 재무 없음 — 밸류·퀄리티 슬리브는 이번에도 비어 있습니다 "
                  f"({(fundamental_store.diagnostics.get('errors') or ['-'])[0]})")
        if not fundamental_store.available:
            print("  PIT fundamentals unavailable -> value/quality sleeves WITHHELD "
                  "from the replay (today's snapshot is never back-applied)")
        if not universe_history.available:
            print(f"  historical constituents unavailable -> {pit_data.SURVIVORSHIP_UNRESOLVED} "
                  "recorded on every observation")

        fx_observations = RR.fetch_fred_usdkrw(cfg.fred_api_key, fetch_start)
        fx, fx_source_map = RR.resolve_fx_fixings(
            fx_observations, RC.sessions(start, through, "UNION"))
        rates = replay_rates.fetch_rates(through)
        calendar_rows = [{"date":d.strftime("%Y-%m-%d"), "KR":d in RC.sessions(start, through,"KR"),
                          "US":d in RC.sessions(start, through,"US")}
                         for d in RC.sessions(start, through,"UNION")]
        components = RI.pack(prices=prices, benchmarks=cfg.benchmarks, universe=fetch_universe,
            universe_history=universe_history, fundamentals=fundamental_store, macro=macro,
            vix=vix, vintages=macro_vintages, fx=fx, rates=rates, through=through,
            calendar_rows=calendar_rows, fx_observations=fx_observations,
            fx_source_map=fx_source_map, price_recovery=price_recovery,
            corporate_actions=corporate_actions,
            benchmark_lineage=BS.source_lineage(benchmark_diagnostics),
            price_lineage=[
                {"region":"KR", "vendor":"FINANCE_DATA_READER",
                 "distributions":"YAHOO_ACTIONS", "source":korea["source"],
                 "crossCheck":korea_agreement, "coverageShortfall":shortfall,
                 "routes":dict(collections.Counter(
                     (korea.get("routes") or {}).values()))},
                {"region":"US", "vendor":"YAHOO_UNADJUSTED_WITH_ACTIONS",
                 "distributions":"YAHOO_ACTIONS", "crossCheck":None},
            ])
        if args.dry_run:
            frozen = RI.unpack(components)
            manifest = {"sha256":RI.digest(components), "through":through, "policy":policy}
        else:
            manifest = store.commit(components, through=through, policy=policy)
            # Benchmark cache/index are operational state shared across replay
            # generations.  Update them only after the immutable generation
            # snapshot accepted the candidate; a conflict must leave no side
            # effect for the next run to inherit.
            BS.persist_selected(ledger_dir, benchmark_series, benchmark_diagnostics)
            # Always consume the canonical snapshot, including on the acquisition run.
            frozen = RI.unpack(store.load(manifest))
        del components
    prices, macro, vix = frozen["prices"], frozen["macro"], frozen["vix"]
    macro_vintages = frozen["macro_vintages"]
    fundamental_store, universe_history = frozen["fundamental_store"], frozen["universe_history"]
    fetch_universe = frozen["universe"]
    universe_signature = universe_history.signature
    horizon = int(replay_cfg.get("horizonDays", 126))
    minimum_benchmark_coverage = float(replay_cfg.get("minBenchmarkCoveragePct", 95.0))
    calendar = RC.metadata(start, through, frequency)
    started = time.time()
    # How much of the survivorship fix actually landed: a former member with no
    # price data is dropped by the snapshot, so membership alone proves nothing.
    recovery = former_member_recovery(
        historical_only, prices, universe_history.memberships)
    for region, row in sorted(recovery.items()):
        print(f"  former members with price history {region}: "
              f"{row['priced']}/{row['describedFormerMembers']} ({row['pricedPct']}%)")
        if row["byYearLeft"]:
            print("    by year left: " + ", ".join(
                f"{year} {cell['priced']}/{cell['described']}"
                for year, cell in row["byYearLeft"].items()))

    replay = HR.run_replay(
        prices, fetch_universe, benchmarks=cfg.benchmarks, cfg_lt=cfg.longterm,
        start=start, end=through,
        fixed_grid=RC.signal_grid(start, through, frequency),
        frequency=args.frequency or replay_cfg.get("frequency", "W"),
        fundamental_store=fundamental_store, macro=macro, vix=vix,
        macro_vintages=macro_vintages,
        universe_history=universe_history, model_version=prov_mod.MODEL_VERSION,
        existing_ids=existing_ids, progress=True,
    )
    diagnostics = replay["diagnostics"]
    diagnostics["evaluationCalendar"] = calendar
    diagnostics["evaluationAsOf"] = through
    diagnostics["inputSnapshot"] = {"sha256":manifest["sha256"], "through":through,
        "manifest":str(store.path.relative_to(ledger_dir)), "schema":RI.SCHEMA,
        "componentHashes":manifest.get("componentHashes", {}),
        # What the seal had to repair because the vendor answered differently
        # this run than at the generation's first acquisition. Never silent: a
        # restored name is one whose sealed rows were used because the vendor
        # declined to serve it, an ignored one is a name that was never sealed
        # and so may not write into an already-published month.
        "prefixReconciliation":{
            "restoredTickers":sorted(store.reconciliation["restored"]),
            "ignoredTickers":sorted(t for t in store.reconciliation["ignored"] if t),
            "components":len(store.reconciliation["components"]),
            "policy":"SEALED_ROWS_ARE_AUTHORITATIVE; "
                     "A_CONTRADICTED_VALUE_STILL_CONFLICTS"}}
    kr_recovery_rows = frozen.get("price_recovery") or []
    recovered_rows = [row for row in kr_recovery_rows if row.get("kind") == "accepted"]
    diagnostics["inputRecovery"] = {
        "version":RR.RECOVERY_VERSION,
        "fx":frozen.get("fx_source"),
        "benchmarkLineage":frozen.get("benchmark_lineage") or [],
        "krPriceRows":kr_recovery_rows,
        "krPriceSummary": {
            "accepted":len(recovered_rows),
            "rejected":sum(row.get("kind") == "rejected" for row in kr_recovery_rows),
            "targetedYahooRetries":sum(row.get("fallbackVendor") == "YAHOO_TARGETED_RETRY"
                                       for row in recovered_rows),
            "basisBoundReconstructions":sum(
                row.get("method") == "FDR_RAW_RETURN_WITH_OBSERVED_ADJUSTMENT_BOUNDS_LOWER_NAV"
                for row in recovered_rows),
            "maximumPathUncertaintyBps":max(
                [float(row.get("pathUncertaintyBps") or 0) for row in recovered_rows],
                default=0.0),
            "valuationPolicy":"LOWER_OBSERVED_ADJUSTMENT_BOUND_FOR_LONG_ONLY_NAV",
        },
        "corporateActionVersion":(frozen.get("corporate_actions") or {}).get("version"),
    }
    diagnostics["priceLineage"] = frozen.get("price_lineage") or []
    events = frozen.get("corporate_events") or []
    diagnostics["inputAdjustment"] = {
        **(frozen.get("adjustment") or {}),
        "dividends":sum(1 for row in events if float(row.get("dividend") or 0) > 0),
        "splits":sum(1 for row in events if float(row.get("split") or 1) != 1.0),
        "tickersWithEvents":len({row.get("ticker") for row in events}),
        "firstEvent":min((row["date"] for row in events), default=None),
        "lastEvent":max((row["date"] for row in events), default=None),
        # The point of the basis change: a dividend paid after the cutoff
        # appends, it does not rewrite a published session.
        "sealedPrefixStableUnderNewDistributions":True,
    }
    for row in replay["signals"]:
        row["inputSnapshotSha256"] = manifest["sha256"]
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
    HS.stamp_universe(
        ledger_dir, prov_mod.REPLAY_VERSION, universe_signature,
        source=replay_cfg.get("universeHistoryPath"))

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
    # Recorded, not only logged: whether the survivorship fix reached the years
    # that need it is an evidence-quality fact, and a log line scrolls away.
    diagnostics["formerMemberRecovery"] = recovery

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
          f"survivorship risk {diagnostics['survivorshipRisk']} "
          f"({diagnostics['affectedObservationsPct']}% of name-dates unvouched)")
    # A pooled coverage figure describes no cross-section in the span. The gap is
    # concentrated in one region and front-loaded in time, and an operator
    # deciding whether the evidence is usable needs to see which and when.
    for region, row in (diagnostics.get("universeCoverageByRegion") or {}).items():
        print(f"  universe {region}: priced {row['constituentCoveragePct']}%, "
              f"membership known {row['membershipCoveragePct']}%, "
              f"unvouched {row['affectedObservationsPct']}% "
              f"({row['survivorshipRisk']}, {row['nameDates']} name-dates)")
    worst_year = diagnostics.get("worstCoveredYear")
    if worst_year is not None:
        by_year = {row["year"]: row for row in diagnostics.get("universeCoverageByYear") or []}
        best = min(by_year.values(), key=lambda r: r["affectedObservationsPct"] or 0.0)
        print(f"  universe worst year {worst_year}: "
              f"{by_year[worst_year]['affectedObservationsPct']}% unvouched "
              f"vs best {best['year']}: {best['affectedObservationsPct']}%")
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


def main(argv=None) -> int:
    try:
        return _run(argv)
    except (RI.InputVersionConflict, RR.RecoveryError) as exc:
        arguments = list(sys.argv[1:] if argv is None else argv)
        if arguments:
            ledger = Path(arguments[0])
            conflict = isinstance(exc, RI.InputVersionConflict)
            record = {"status":("INPUT_VERSION_CONFLICT" if conflict
                                else "INPUT_RECOVERY_FAILED"),
                      "replayVersion":prov_mod.REPLAY_VERSION,
                      "dataVersion":prov_mod.DATA_VERSION, "reason":str(exc),
                      "requiresNewExperiment":conflict,
                      "retrySameGeneration":not conflict}
            folder = ledger / "replay-input-conflicts"
            folder.mkdir(parents=True, exist_ok=True)
            (folder / (RI.digest(record) + ".json")).write_text(json.dumps(record, indent=2) + "\n")
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
