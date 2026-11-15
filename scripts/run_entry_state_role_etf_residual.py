"""Run entry-state-role-etf-residual-v1 on the sealed replay-v16 inputs (read-only) and write JSON + CSV.

    python scripts/run_entry_state_role_etf_residual.py <ledger_dir> --source-commit <signal-history sha> --out-dir <dir>

The ledger is never written. The output directory must not exist yet (write-once). The spec digest printed first is the
comparison definition fixed before any path is valued; the run refuses if it differs from research_specs/<id>.json.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import entry_state_role_etf_residual as S          # noqa: E402
from pipeline import historical_store as HS                       # noqa: E402
from pipeline import portfolio_validation as PV                   # noqa: E402
from pipeline import provenance                                    # noqa: E402
from pipeline import replay_calendar as RC                        # noqa: E402
from pipeline import replay_inputs as RI                          # noqa: E402
from pipeline import replay_valuation as RV                       # noqa: E402
from pipeline import selection_value as SV                        # noqa: E402
from pipeline.config import load_config                           # noqa: E402

SEALED_INPUT_SHA256 = "f0781292f508a123c234ded6d28aa8e84a0dc3cc29500e14989dc0b68f53b4d2"


def _digest_tree(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file():
            digest.update(str(path.relative_to(root)).encode())
            with path.open("rb") as stream:
                digest.update(hashlib.file_digest(stream, "sha256").digest())
    return digest.hexdigest()


def check_spec_file(root: Path) -> str:
    frozen = json.loads((root / S.SPEC_PATH).read_text())
    if frozen.get("spec") != S.spec() or frozen.get("specSha256") != S.spec_sha256():
        raise ValueError("SPEC_CHANGED: the module's comparison definition differs from the frozen spec file")
    return frozen["specSha256"]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger_dir")
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--counts", default=",".join(str(n) for n in S.SCENARIO_NAME_COUNTS))
    args = parser.parse_args(argv)
    ledger, out = Path(args.ledger_dir), Path(args.out_dir)
    if out.exists():
        raise FileExistsError(f"refusing to overwrite {out}")
    counts = [int(x) for x in args.counts.split(",")]
    if not set(counts) <= set(S.SCENARIO_NAME_COUNTS):
        raise ValueError("counts outside the frozen scenario grid")
    spec_sha = check_spec_file(ROOT)
    print("spec", spec_sha, flush=True)
    code_commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True,
                                 text=True).stdout.strip() or None
    before = _digest_tree(ledger)

    cfg, _ = load_config()
    store = RI.InputStore(ledger, provenance.REPLAY_VERSION, provenance.DATA_VERSION)
    manifest = store.manifest()
    if provenance.REPLAY_VERSION != "replay-v16" or manifest["sha256"] != SEALED_INPUT_SHA256:
        raise ValueError("requires the sealed replay-v16 input snapshot the original entry-state study used")
    frozen = RI.unpack(store.load(manifest, valuation_only=True))
    through = manifest["through"]
    rf_through = frozen["risk_free_source"]["verifiedThrough"]
    benchmarks = dict(cfg.benchmarks)
    valuation = {
        "KR": RV.ValuationData(frozen["prices"], benchmarks, frozen["fx"], frozen["risk_free"], through=through,
                               risk_free_through=rf_through, corporate_actions=frozen.get("corporate_actions")),
        # USD book: a unit FX series keeps every US leg in dollars; no USD/KRW enters the US comparison.
        "US": RV.ValuationData(frozen["prices"], benchmarks,
                               pd.Series(1.0, index=pd.date_range("2000-01-01", through, freq="D")),
                               frozen["risk_free"], through=through, risk_free_through=rf_through,
                               corporate_actions=frozen.get("corporate_actions")),
    }
    signals = HS.load(ledger, HS.SIGNALS, provenance.REPLAY_VERSION, project=HS.audit_projection)
    outcomes = HS.load(ledger, HS.OUTCOMES, provenance.REPLAY_VERSION)
    replay_cfg = cfg.historical_replay or {}
    full = RC.schedule(replay_cfg.get("start", RC.ORIGIN), through, PV.HEADLINE_HORIZON,
                       replay_cfg.get("frequency", "W"))
    calendar = [b for b in full if b["endDate"] <= through]
    unmatured = [b for b in full if b["endDate"] > through]
    contexts = SV.contexts_from_signals(signals, cfg.longterm)

    def calibrator():
        return PV.ExpandingBucketCalibration(
            outcomes, horizon=int(cfg.kelly_portfolio.get("horizonDays", 126)),
            prior_strength=float(cfg.kelly_portfolio.get("shrinkagePriorStrength", 30)),
            min_dates=20, cost_adjusted=False)

    paths: dict[str, dict] = {}
    for region in ("KR", "US"):
        etf = S.REGIONAL_ETF[region]
        paths[f"{region}:ETF_ONLY"] = S.run_path(
            rung="PASSIVE", region=region, n=0, residual="ETF", contexts=contexts, calibrator=None, calendar=calendar,
            cfg_pf=cfg.kelly_portfolio, valuation=valuation[region], fixed_target={etf: 1.0},
            strategy_id=f"{region}:ETF_ONLY:{etf}")
        if region in S.SEPARATE_COMPARISON:
            other = S.SEPARATE_COMPARISON[region]
            paths[f"{region}:SEPARATE:{other}"] = S.run_path(
                rung="PASSIVE", region=region, n=0, residual="ETF", contexts=contexts, calibrator=None,
                calendar=calendar, cfg_pf=cfg.kelly_portfolio, valuation=valuation[region], fixed_target={other: 1.0},
                strategy_id=f"{region}:SEPARATE_COMPARISON:{other}")
        for n in counts:
            if n == 0:
                continue                 # N=0 is the ETF-only path on both rungs by construction
            for residual in S.RESIDUALS:
                for rung in S.RUNGS:
                    t0 = time.time()
                    path = S.run_path(rung=rung, region=region, n=n, residual=residual, contexts=contexts,
                                      calibrator=calibrator(), calendar=calendar, cfg_pf=cfg.kelly_portfolio,
                                      valuation=valuation[region])
                    paths[path["strategyId"]] = path
                    print(f"{path['strategyId']}: {path['status']} {len(path['blocks'])} blocks "
                          f"{time.time() - t0:.1f}s", flush=True)

    after = _digest_tree(ledger)
    if after != before:
        raise ValueError("SEALED_LEDGER_CHANGED")
    source = {"sourceCommit": args.source_commit, "inputSha256": manifest["sha256"], "specSha256": spec_sha,
              "codeCommit": code_commit, "codeSha256": S.code_sha256(ROOT)}
    results: dict = {"studyId": S.STUDY_ID, "evidenceClass": S.EVIDENCE_CLASS, "spec": S.spec(), "source": source,
                     "calendar": {"maturedBlocks": len(calendar), "unmaturedBlocksPending": len(unmatured),
                                  "first": calendar[0]["date"], "lastEnd": calendar[-1]["endDate"],
                                  "through": through, "sha256": RC.metadata(
                                      replay_cfg.get("start", RC.ORIGIN), through,
                                      replay_cfg.get("frequency", "W"))["sha256"]},
                     "regions": {}, "sealedLedgerUnchanged": True,
                     "promotionEligible": False, "liveValidated": False, "productionChanged": False}
    for region in ("KR", "US"):
        etf_path = paths[f"{region}:ETF_ONLY"]
        reg = {"etf": S.REGIONAL_ETF[region], "currency": S.CURRENCY[region],
               "etfOnly": S.path_metrics(etf_path, etf_path), "separateComparison": None, "scenarios": {}}
        if region in S.SEPARATE_COMPARISON:
            other = paths[f"{region}:SEPARATE:{S.SEPARATE_COMPARISON[region]}"]
            reg["separateComparison"] = {"ticker": S.SEPARATE_COMPARISON[region],
                                         "metrics": S.path_metrics(other, etf_path),
                                         "horizons": {h: S.horizon_windows(other, etf_path, s, len(calendar))
                                                      for h, s in S.HORIZONS.items()}}
        for n in counts:
            if n == 0:
                reg["scenarios"]["N0"] = {"note": "ETF_ONLY on both rungs by construction", "metrics": reg["etfOnly"]}
                continue
            entry = {}
            for residual in S.RESIDUALS:
                ids = {rung: f"{region}:{rung}:N{n}:{residual}" for rung in S.RUNGS}
                entry[residual] = {
                    rung: {"metrics": S.path_metrics(paths[i], etf_path),
                           "horizons": {h: S.horizon_windows(paths[i], etf_path, s, len(calendar))
                                        for h, s in S.HORIZONS.items()}}
                    for rung, i in ids.items()}
                entry[residual]["pairedAtWeightMinusInRank"] = S.paired_difference(
                    paths[ids[S.ENTRY_AT_WEIGHT]], paths[ids[S.ENTRY_IN_RANK]])
            for rung in S.RUNGS:
                entry.setdefault("residualEffectEtfMinusCash", {})[rung] = S.paired_difference(
                    paths[f"{region}:{rung}:N{n}:ETF"], paths[f"{region}:{rung}:N{n}:CASH"])
            reg["scenarios"][f"N{n}"] = entry
        results["regions"][region] = reg

    out.mkdir(parents=True)
    (out / "result.json").write_text(json.dumps(results, indent=2, sort_keys=True, allow_nan=False) + "\n")
    fields = ["region", "strategyId", "currency", "frequency", "returnBasis", "costBasis", "evidenceClass",
              "sourceCommit", "inputSha256", "specSha256", "codeCommit", "codeSha256", "date", "nav"]
    with (out / "nav-daily.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for key, path in paths.items():
            if path["n"] not in (0, S.PRIMARY_NAME_COUNT) and ":SEPARATE" not in key and ":ETF_ONLY" not in key:
                continue                 # the full daily file carries N=5 and the passive lines; blocks carry all N
            passive = path["rung"] == "PASSIVE"
            writer.writerows(S.nav_rows(path, currency=S.CURRENCY[path["region"]],
                                        cost_basis=S.NO_COST if passive and ":ETF_ONLY" in key else S.NET_ALREADY_CHARGED,
                                        source=source))
    with (out / "decisions.jsonl").open("w") as stream:
        for key, path in paths.items():
            for block in path["blocks"]:
                stream.write(json.dumps({"strategyId": key, "region": path["region"], **block}, sort_keys=True) + "\n")
            if path["stoppedAt"]:
                stream.write(json.dumps({"strategyId": key, "region": path["region"], "status": path["status"],
                                         "stoppedAt": path["stoppedAt"]}, sort_keys=True) + "\n")
    print(json.dumps({r: {k: v.get("ETF", {}).get("pairedAtWeightMinusInRank") if isinstance(v, dict) else None
                          for k, v in results["regions"][r]["scenarios"].items()} for r in results["regions"]},
                     indent=1), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
