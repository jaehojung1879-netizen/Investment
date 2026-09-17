"""Two standalone replays — US-only, KR-only — from the ALREADY-SEALED
`replay-v16` frozen inputs, blended by `pipeline.regional_rotation` into a
walk-forward rotated portfolio, scored against the real combined-region
CHAMPION path with the exact same cost/CAGR/drawdown machinery.

WHY FROZEN-ONLY. This is an exploratory analysis of an already-sealed
generation, not a new experiment: it must never fetch vendors, never touch
`ledger/historical/replay-v16/signals-*.jsonl.gz` (append-only, immutable,
one universe per REPLAY_VERSION — writing signals for a US-ONLY or KR-ONLY
universe under that REPLAY_VERSION would violate the exact invariant this
project enforces everywhere else), and never write anything back to the
ledger. Its own report is a separate file, `regional-rotation-report.json`,
that carries the frozen input's own hash so it can always be tied back to
the exact snapshot it was computed from.

WHY TWO FRESH RUNS RATHER THAN READING THE SEALED SIGNALS. The sealed
combined-region signals rank US and KR names in ONE cross-section together
(`alphaPercentile` is a rank inside that combined pool). A US-only or
KR-only "what if we had only ever invested here" question needs each
region's names ranked in a pool of ONLY that region — a different
cross-section, and therefore a different (freshly computed, never persisted)
set of signals from the same underlying prices/fundamentals/macro.

WHAT THIS PRODUCES. For each region: a CHAMPION-only path (the production
selector, applied to a single-region universe). The two paths are combined
by `regional_rotation`'s quarterly walk-forward blend and scored through
`portfolio_validation._path_metrics` — the same function the sealed report
scores every other path with. Printed and written alongside the sealed
combined-region CHAMPION path (from the ledger's own committed report, no
recomputation) as the comparison baseline this is trying to beat.

WHAT THIS DOES NOT ESTABLISH. Whether a CAGR or Sharpe gap here is real or
noise — no bootstrap confidence interval is computed for the
rotated-vs-combined comparison the way `portfolio_validation.paired_comparison`
does for champion-vs-challenger. Point estimates only; treat a difference
smaller than the champion-vs-challenger CI width this project already
measures elsewhere as not yet a finding.

Usage: python scripts/run_regional_rotation_replay.py <ledger_dir>
       [--output regional-rotation-report.json]
       [--lookback-days 252] [--temperature 0.05] [--floor 0.15]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import historical_outcomes as HO         # noqa: E402
from pipeline import historical_replay as HR           # noqa: E402
from pipeline import portfolio_validation as PV         # noqa: E402
from pipeline import provenance as prov_mod             # noqa: E402
from pipeline import regional_rotation as RR            # noqa: E402
from pipeline import replay_calendar as RC               # noqa: E402
from pipeline import replay_inputs as RI                # noqa: E402
from pipeline import replay_valuation as RV              # noqa: E402
from pipeline.config import load_config                 # noqa: E402

REGIONS = ("US", "KR")


def _load_frozen(ledger_dir: Path):
    store = RI.InputStore(ledger_dir, prov_mod.REPLAY_VERSION, prov_mod.DATA_VERSION)
    manifest = store.manifest()
    if not manifest:
        raise RI.InputVersionConflict(
            f"no frozen inputs for generation {prov_mod.REPLAY_VERSION} in {ledger_dir} "
            "— this script only reproduces an already-sealed snapshot, it never acquires one")
    return manifest, RI.unpack(store.load(manifest))


def _region_champion_rows(region: str, names: list[str], frozen: dict, *, cfg, replay_cfg,
                          through: str, valuation: RV.ValuationData) -> tuple[list[dict], dict]:
    """One region's standalone CHAMPION path — full historical fidelity for
    THAT region alone, ranked only against itself, matched to production."""
    universe = {region: list(names)}
    start = replay_cfg.get("start", "2013-01-01")
    frequency = replay_cfg.get("frequency", "W")
    # Same explicit grid `run_replay.py`'s production path uses (rather than
    # letting each call derive its own) — so the US-only run, the KR-only
    # run, and the sealed combined-region run this is compared against all
    # walk identical calendar dates, and `regional_rotation`'s per-date
    # matching is never silently comparing two different calendars.
    replay = HR.run_replay(
        frozen["prices"], universe, benchmarks=cfg.benchmarks, cfg_lt=cfg.longterm,
        start=start, end=through, frequency=frequency,
        fixed_grid=RC.signal_grid(start, through, frequency),
        fundamental_store=frozen["fundamental_store"], macro=frozen["macro"], vix=frozen["vix"],
        macro_vintages=frozen["macro_vintages"], universe_history=frozen["universe_history"],
        model_version=prov_mod.MODEL_VERSION, progress=True)
    signals, diagnostics = replay["signals"], replay["diagnostics"]
    print(f"  {region}-only: {len(names)} names, {len(signals)} signals, "
         f"{diagnostics['replayDates']} replay dates")

    bench_closes = {ticker: frozen["prices"][ticker]["Close"]
                    for ticker in cfg.benchmarks.values() if ticker in frozen["prices"]}
    cost_policy = (cfg.kelly_portfolio or {}).get("transactionCosts") or {}
    outcomes = HO.compute_outcomes(signals, frozen["prices"], bench_closes, cost_policy=cost_policy)
    portfolio = PV.portfolio_replay(signals, outcomes, cfg_lt=cfg.longterm,
                                    cfg_pf=cfg.kelly_portfolio, diagnostics=diagnostics,
                                    valuation=valuation)
    rows = portfolio["headlineRows"].get(PV.CHAMPION) or []
    print(f"    CHAMPION headline path: {len(rows)} matured {PV.HEADLINE_HORIZON}D blocks, "
         f"summary CAGR {portfolio['selectors'][PV.CHAMPION]['summary'].get('cagrPct')}%")
    return rows, diagnostics


def _int_from_possibly_float_string(value: str) -> int:
    """GitHub Actions' workflow_dispatch `type: number` inputs arrive as
    strings shaped like "252.0", not "252" — plain `int(value)` rejects that
    (observed in run #1: "invalid int value: '252.0'"). `int(float(value))`
    reads both shapes."""
    return int(float(value))


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("ledger_dir")
    parser.add_argument("--output", default="regional-rotation-report.json")
    parser.add_argument("--lookback-days", type=_int_from_possibly_float_string,
                        default=RR.DEFAULT_LOOKBACK_DAYS)
    parser.add_argument("--temperature", type=float, default=RR.DEFAULT_TEMPERATURE)
    parser.add_argument("--floor", type=float, default=RR.DEFAULT_FLOOR)
    return parser


def main(argv=None) -> int:
    args = build_arg_parser().parse_args(argv)

    ledger_dir = Path(args.ledger_dir)
    cfg = load_config()
    replay_cfg = cfg.historical_replay or {}

    manifest, frozen = _load_frozen(ledger_dir)
    through = manifest["through"]
    print(f"frozen inputs: replay-v16 through {through}, sha256 {manifest['sha256'][:12]}...")

    valuation = RV.ValuationData(
        frozen["prices"], cfg.benchmarks, frozen["fx"], frozen["risk_free"],
        through=through, risk_free_through=frozen["risk_free_source"]["verifiedThrough"],
        corporate_actions=frozen.get("corporate_actions"))

    fetch_universe = frozen["universe"]
    decisions_by_region: dict[str, list[dict]] = {}
    region_diagnostics: dict[str, dict] = {}
    for region in REGIONS:
        names = fetch_universe.get(region) or []
        if not names:
            print(f"  {region}: no names in the frozen universe, skipping")
            continue
        print(f"=== {region}-only replay ===")
        rows, diagnostics = _region_champion_rows(
            region, names, frozen, cfg=cfg, replay_cfg=replay_cfg,
            through=through, valuation=valuation)
        decisions_by_region[region] = rows
        region_diagnostics[region] = {
            "names": len(names), "matureBlocks": len(rows),
            "survivorshipRisk": diagnostics.get("survivorshipRisk"),
        }

    if len(decisions_by_region) < 2:
        print("ERROR: fewer than two regions produced a CHAMPION path; nothing to blend",
             file=sys.stderr)
        return 1

    print("=== standalone single-region paths ===")
    standalone_metrics = {}
    for region, rows in decisions_by_region.items():
        metrics = PV._path_metrics(rows, PV.HEADLINE_HORIZON, cfg.kelly_portfolio)
        standalone_metrics[region] = metrics
        if metrics.get("available"):
            print(f"  {region} alone: CAGR {metrics['cagrPct']}% | excess "
                 f"{metrics['annualizedExcessPct']}%p | Sharpe {metrics['sharpe']} | "
                 f"MDD {metrics['mddPct']}%")
        else:
            print(f"  {region} alone: unavailable ({metrics.get('reason')})")

    print("=== walk-forward regional rotation ===")
    schedule = RR.regional_weight_schedule(
        decisions_by_region, lookback_days=args.lookback_days,
        temperature=args.temperature, floor=args.floor)
    blended = RR.apply_schedule(decisions_by_region, schedule)
    rotated_metrics = (PV._path_metrics(blended, PV.HEADLINE_HORIZON, cfg.kelly_portfolio)
                       if blended else {"available": False, "reason": "no_blended_blocks"})
    if rotated_metrics.get("available"):
        print(f"  rotated: CAGR {rotated_metrics['cagrPct']}% | excess "
             f"{rotated_metrics['annualizedExcessPct']}%p | Sharpe {rotated_metrics['sharpe']} | "
             f"MDD {rotated_metrics['mddPct']}%")
    else:
        print(f"  rotated: unavailable ({rotated_metrics.get('reason')})")
    print(f"  {len(schedule)} quarterly decisions, {len(blended)} blended blocks")
    for row in schedule[:4] + (["..."] if len(schedule) > 8 else []) + schedule[-4:]:
        if row == "...":
            print("    ...")
            continue
        print(f"    {row['date']}  trailing {row['trailingExcessPct']}  -> weights {row['weights']}")

    print("=== sealed combined-region CHAMPION path (comparison baseline) ===")
    sealed_path = ledger_dir / "historical-portfolio-validation.json"
    combined_metrics = None
    if sealed_path.exists():
        try:
            sealed = json.loads(sealed_path.read_text(encoding="utf-8"))
            combined_metrics = (((sealed.get("portfolioReplay") or {}).get("selectors") or {})
                                .get(PV.CHAMPION, {}).get("summary"))
        except ValueError:
            print(f"  WARNING: {sealed_path} is not readable JSON")
    if combined_metrics and combined_metrics.get("available"):
        print(f"  sealed combined: CAGR {combined_metrics['cagrPct']}% | excess "
             f"{combined_metrics['annualizedExcessPct']}%p | Sharpe {combined_metrics['sharpe']} | "
             f"MDD {combined_metrics['mddPct']}%")
    else:
        print(f"  sealed combined path not available at {sealed_path} — "
             "run scripts/audit_portfolio.py first if a comparison baseline is needed")

    report = {
        "reportVersion": "regional-rotation-v1",
        "replayVersion": prov_mod.REPLAY_VERSION,
        "inputSnapshot": {"sha256": manifest["sha256"], "through": through},
        "parameters": {"lookbackDays": args.lookback_days, "temperature": args.temperature,
                       "floor": args.floor},
        "regionDiagnostics": region_diagnostics,
        "standalone": standalone_metrics,
        "rotated": rotated_metrics,
        "rotationSchedule": schedule,
        "sealedCombinedChampion": combined_metrics,
        "caveat": ("Point estimates only — no bootstrap confidence interval computed for "
                  "rotated-vs-combined. A difference smaller than this project's own "
                  "champion-vs-challenger paired CI width is not yet a finding."),
    }
    output = Path(args.output)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
