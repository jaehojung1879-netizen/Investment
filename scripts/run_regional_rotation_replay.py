"""Validate frozen regional-rotation-v1 against static controls, from read-only replay-v16.

No vendor calls, no sealed writes, no production promotion. Outputs are research
artifacts outside the ledger. A content-checked standalone-path checkpoint avoids
re-running unchanged regional selection during report development.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
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
from pipeline import regional_validation as VALIDATION
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
    parser.add_argument("--markdown", default="regional-rotation-report.md")
    parser.add_argument("--paths-output", default=None)
    parser.add_argument("--paths-input", default=None)
    return parser


def ledger_digest(ledger_dir):
    """Hash ALL sealed ledger bytes, not only the input manifest."""
    digest = hashlib.sha256()
    for path in sorted(ledger_dir.rglob("*")):
        if path.is_file():
            digest.update(str(path.relative_to(ledger_dir)).encode())
            with path.open("rb") as stream:
                digest.update(hashlib.file_digest(stream, "sha256").digest())
    return digest.hexdigest()


def guard_output(path, ledger_dir):
    resolved = Path(path).resolve()
    if resolved == ledger_dir.resolve() or ledger_dir.resolve() in resolved.parents:
        raise ValueError("research output must be outside sealed ledger")
    if resolved.exists():
        raise FileExistsError(f"refusing to overwrite existing artifact: {resolved}")
    return resolved


def _engine_hash():
    files = [ROOT / "pipeline" / f for f in (
        "historical_replay.py", "historical_outcomes.py", "portfolio_validation.py",
        "replay_valuation.py", "replay_calendar.py", "longterm.py", "kelly_portfolio.py")]
    return RI.digest({str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files})


def main(argv=None) -> int:
    args = build_arg_parser().parse_args(argv)
    params = dict(lookback_days=args.lookback_days, temperature=args.temperature, floor=args.floor)
    if params != dict(VALIDATION.BASELINE):
        raise ValueError("v1 is frozen; use only the pre-specified OFAT diagnostics")
    ledger_dir = Path(args.ledger_dir)
    output = guard_output(args.output,ledger_dir)
    markdown = guard_output(args.markdown,ledger_dir)
    checkpoint = guard_output(args.paths_output,ledger_dir) if args.paths_output else None
    cfg, _config_warnings = load_config()
    replay_cfg = cfg.historical_replay or {}
    before = ledger_digest(ledger_dir)
    store = RI.InputStore(ledger_dir, prov_mod.REPLAY_VERSION, prov_mod.DATA_VERSION)
    manifest = store.manifest()
    if not manifest:
        raise RI.InputVersionConflict("no frozen inputs; validation never acquires them")
    if prov_mod.REPLAY_VERSION != "replay-v16":
        raise ValueError("this v1 validation is pinned to replay-v16")
    through = manifest["through"]
    print(f"frozen replay-v16 through {through}, input {manifest['sha256']}", flush=True)
    sealed_path = ledger_dir / "historical-portfolio-validation.json"
    sealed = json.loads(sealed_path.read_text())
    if (sealed.get("inputSnapshot",{}).get("sha256") != manifest["sha256"] or
            sealed.get("replayVersion") != prov_mod.REPLAY_VERSION):
        raise ValueError("sealed CHAMPION and frozen inputs have different lineage")
    combined = sealed["portfolioReplay"].get("headlineRows",{}).get(PV.CHAMPION)
    if not combined:
        raise ValueError("sealed CHAMPION daily rows unavailable; never regenerate sealed report")
    provenance = dict(inputSha256=manifest["sha256"], configSha256=RI.digest(
        dict(longterm=cfg.longterm,kelly=cfg.kelly_portfolio,replay=replay_cfg,benchmarks=cfg.benchmarks)),
        engineSha256=_engine_hash())
    if args.paths_input:
        cached = json.loads(gzip.decompress(Path(args.paths_input).read_bytes()))
        content = {k:v for k,v in cached.items() if k != "sha256"}
        if RI.digest(content) != cached["sha256"] or cached["provenance"] != provenance:
            raise ValueError("standalone path checkpoint hash or lineage mismatch")
        regional, diagnostics = cached["regional"],cached["diagnostics"]
    else:
        _, frozen = _load_frozen(ledger_dir)
        valuation = RV.ValuationData(
            frozen["prices"], cfg.benchmarks, frozen["fx"], frozen["risk_free"],
            through=through, risk_free_through=frozen["risk_free_source"]["verifiedThrough"],
            corporate_actions=frozen.get("corporate_actions"))
        regional, diagnostics = {}, {}
        for region in REGIONS:
            names = frozen["universe"].get(region) or []
            if not names:
                raise ValueError("frozen universe missing region: " + region)
            print(f"=== {region}-only replay ===",flush=True)
            rows, diag = _region_champion_rows(region,names,frozen,cfg=cfg,replay_cfg=replay_cfg,
                                               through=through,valuation=valuation)
            regional[region] = rows
            diagnostics[region] = {k:diag.get(k) for k in (
                "survivorshipRisk", "fundamentalsPit", "macroPitStatus", "replayDates")}
        if checkpoint:
            cached = dict(provenance=provenance,regional=regional,diagnostics=diagnostics)
            cached["sha256"] = RI.digest(cached)
            checkpoint.parent.mkdir(parents=True,exist_ok=True)
            checkpoint.write_bytes(gzip.compress(RI.canonical(cached),mtime=0))
    # Fresh and cached paths use identical key order, including multi-name
    # sums. The checkpoint's canonical JSON must not change floating reduction order.
    regional = json.loads(RI.canonical(regional))
    calendar = [r for r in RC.schedule(replay_cfg.get("start",RC.ORIGIN),through,PV.HEADLINE_HORIZON,
                                      replay_cfg.get("frequency","W")) if r["endDate"] <= through]
    report = VALIDATION.build_validation(regional,combined,calendar,cfg.kelly_portfolio)
    report["inputSnapshot"] = dict(sha256=manifest["sha256"],through=through)
    report["regionDiagnostics"] = diagnostics
    report["sourceProvenance"] = provenance
    report["regionalPathHashes"] = {r:RI.digest(rows) for r,rows in regional.items()}
    report["sameRegionalPathsForStaticAndDynamic"] = True
    report["sealedCombinedPublishedSummary"] = sealed["portfolioReplay"]["selectors"][PV.CHAMPION]["summary"]
    # Recalculation must reproduce the published CHAMPION; keep original result intact.
    original = report["sealedCombinedPublishedSummary"]
    recalculated = report["baselineComparison"][VALIDATION.PORTFOLIOS[0]]
    if report["matching"]["complete"]:
        for key in VALIDATION.METRICS:
            if key == "calmar":
                continue
            if original.get(key) != recalculated.get(key):
                raise ValueError(f"sealed CHAMPION metric mismatch: {key}")
    report["sealedCombinedPublishedSummary"] = {k:v for k,v in original.items()
        if k not in ("nav","rolling3YAnnualizedExcess","rolling5YAnnualizedExcess")}
    after = ledger_digest(ledger_dir)
    if before != after:
        raise ValueError("SEALED_LEDGER_CHANGED")
    report["sealedInvariant"] = dict(before=before,after=after,unchanged=True)
    for path in (output,markdown):
        path.parent.mkdir(parents=True,exist_ok=True)
    report = VALIDATION.report_values(report)
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False,sort_keys=True)+"\n")
    markdown.write_text(VALIDATION.markdown_report(report))
    for name,m in report["baselineComparison"].items():
        print(name, {k:m.get(k) for k in VALIDATION.METRICS},flush=True)
    print(f"wrote {output} and {markdown}; sealed bytes unchanged",flush=True)
    return 0 if report["matching"]["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
