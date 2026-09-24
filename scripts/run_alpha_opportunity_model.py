"""Validate the sealed preregistration, or execute only after every gate passes.

No labels/prices are opened before the seal, main/review and design gates.
Phase 1 intentionally carries unresolved economic inputs: --execute fails closed.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import alpha_opportunity_spec as S  # noqa: E402


def verify_inputs(spec, root):
    """Inputs are committed identities, not an operator-provided PASS flag."""
    root = Path(root)
    for rel, blob in spec["inputFiles"].items():
        data = (root / rel).read_bytes()
        import hashlib
        got = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        if got != blob:
            raise ValueError("INPUT_SNAPSHOT_CHANGED: " + rel)
    manifest = S.read_json(root / "ledger/historical/replay-v16/inputs.json")
    payload = {k: v for k, v in manifest.items() if k != "sha256"}
    if S.digest(payload) != spec["snapshots"]["replayManifestSha256"]:
        raise ValueError("REPLAY_MANIFEST_CHANGED")
    # Prevent extra, unsealed raw shards from entering a glob-based loader.
    for folder, pattern in (("fundamentals/us", "finnhub-*.jsonl.gz"),
                            ("fundamentals/kr", "dart-*.jsonl.gz"),
                            ("universe/kr", "krx-universe-*.jsonl.gz")):
        for path in (root / "ledger" / folder).glob(pattern):
            if str(path.relative_to(root)) not in spec["inputFiles"]:
                raise ValueError("UNSEALED_RAW_SHARD")
    return {"snapshotFiles": True, "replayManifest": True}


def execute(spec, registry, input_root, us_membership, output):
    # Heavy imports follow the execution guard in main. This is a new model;
    # none of the closed study's model or evaluation entry points are invoked.
    from pipeline import alpha_opportunity_features as F
    from pipeline import alpha_opportunity_model as M
    from pipeline import alpha_opportunity_evaluation as E
    from pipeline import regional_alpha_features as sources
    import pandas as pd
    import numpy as np
    from pipeline.alpha_opportunity_overlay import calendar_gate
    output = Path(output).resolve()
    if output.exists() or output.is_relative_to(ROOT) or output.is_relative_to(Path(input_root).resolve()):
        raise ValueError("OUTPUT_MUST_BE_NEW_AND_OUTSIDE_SOURCE_AND_INPUTS")
    overlay = calendar_gate(spec)
    adv_path = Path(input_root) / "opportunity-adv.jsonl"
    if S.file_hash(adv_path) != spec["snapshots"]["advSnapshotSha256"]:
        raise ValueError("UNSEALED_ADV_SNAPSHOT")
    adv = pd.read_json(adv_path, lines=True, convert_dates=False)
    if adv.duplicated(["date", "region", "ticker"]).any():
        raise ValueError("DUPLICATE_ADV")
    if (adv.availableFrom > adv.date).any() or (adv.adv < 0).any():
        raise ValueError("PIT_INVALID_ADV")
    manifest, prices, _, _ = sources.load_inputs(Path(input_root)/"ledger")
    if manifest["sha256"] != spec["snapshots"]["replayManifestSha256"]:
        raise ValueError("INPUT_MANIFEST_MISMATCH")
    if S.file_hash(us_membership) != spec["snapshots"]["usMembershipSha256"]:
        raise ValueError("MEMBERSHIP_SNAPSHOT_CHANGED")
    memberships = sources.load_memberships(Path(input_root)/"ledger", us_membership)
    raw, shares = F.load_raw(Path(input_root)/"ledger")
    frame = F.build_matrix(prices, memberships, raw, shares,
                          start=spec["walkForward"]["featureStart"], through=spec["dataCutoff"])
    frame = frame.merge(adv[["date", "region", "ticker", "adv"]], on=["date", "region", "ticker"], how="left", validate="one_to_one")
    coverage = F.coverage(frame, registry)
    # No outcome-dependent changes to the allowlist; insufficient coverage stops.
    first_eval_year = int(spec["walkForward"]["featureStart"][:4]) + spec["walkForward"]["minimumHistoryMonths"]//12
    for entry in coverage:
        if int(entry["year"]) < first_eval_year:
            continue
        if entry["coverage"] < (.8 if entry["feature"] in F.PRICE + F.ATTENTION else .2):
            raise ValueError("BLOCKED_DATA_COVERAGE: " + str(entry))
    predictions, fold_records, failures = [], [], []
    for region in spec["regions"]:
        regional = frame.loc[frame.region.eq(region)].copy()
        for horizon in spec["horizons"]:
            labelled = regional.copy()
            labels = [F.target_at(prices, region, row.ticker, row.date, horizon, spec["dataCutoff"])
                      for row in regional.itertuples()]
            labelled = pd.concat([labelled.reset_index(drop=True), pd.DataFrame(labels)], axis=1)
            schedule = sources.weekly_grid(spec["walkForward"]["featureStart"], spec["dataCutoff"], region)
            history = []
            ready_fold = 0
            for fold in M.folds(labelled, schedule, spec):
                fold_records.append({k: v for k, v in fold.items() if k not in ("train", "validation")} | {"region": region, "horizon": horizon})
                if fold["status"] != "READY":
                    continue
                ready_fold += 1
                names = spec["allowedFeatures"][region][str(horizon)]
                for family in ("LINEAR", "SHALLOW_CHALLENGER"):
                    train, valid = fold["train"], fold["validation"]
                    from sklearn.exceptions import ConvergenceWarning
                    try:
                        fit = M.fit_heads(train, valid, names, family, spec)
                    except (ConvergenceWarning, FloatingPointError) as exc:
                        failures.append({"region": region, "horizon": horizon, "family": family,
                                         "year": fold["year"], "reason": type(exc).__name__})
                        continue
                    out = valid.copy()
                    for key in ("probability", "expectedRelativeReturn", "trainingBaseRate", "trainingMeanReturn"):
                        out[key] = fit[key]
                    out["family"], out["horizon"], out["trainingCutoff"] = family, horizon, fold["cutoff"]
                    out["modelVersion"] = spec["modelIds"][region]
                    out["specSha256"] = S.digest(spec)
                    out["missingFeatures"] = [[n for n in names if pd.isna(row.get(n))] for _, row in valid.iterrows()]
                    out["omittedFeatures"] = [fit["omittedFeatures"] for _ in range(len(out))]
                    out["opportunityEvaluationEligible"] = ready_fold >= 2
                    out["uncertaintyStatus"] = "NOT_PRIMARY"
                    out["gateStatus"] = "NOT_PRIMARY"
                    out["passesOpportunity"] = None
                    for key in ("meanLower", "meanUpper", "probabilityLower", "probabilityUpper"):
                        out[key] = np.nan
                    if family == "LINEAR":
                        try:
                            uncertainty = M.prediction_uncertainty(train, valid, names, spec)
                        except (ConvergenceWarning, FloatingPointError) as exc:
                            uncertainty = {"status": "MODEL_UNSTABLE_"+type(exc).__name__}
                        if uncertainty["status"].startswith("MODEL_UNSTABLE"):
                            failures.append({"region": region, "horizon": horizon, "family": family,
                                             "year": fold["year"], "reason": uncertainty["status"]})
                        out["uncertaintyStatus"] = uncertainty["status"]
                        for key, value in uncertainty.items():
                            if key != "status":
                                out[key] = value
                        gates = []
                        prior = pd.concat(history+[out], ignore_index=True)
                        for row in out.itertuples():
                            residual = M.matured_residual_scale(prior, row.date)
                            cost = M.dated_round_trip_cost(region, row.date, spec)
                            gate = M.opportunity_gate(row.expectedRelativeReturn, row.meanLower, cost,
                                residual if residual is not None else np.nan, row.adv, spec)
                            gates.append({"gateStatus": gate["status"], "passesOpportunity": gate["passes"],
                                          "roundTripCost": cost, "residualScale": residual})
                        for key in gates[0]:
                            out[key] = [g[key] for g in gates]
                        history.append(out)
                    predictions.append(out)
    results = []
    combined = None
    if predictions:
        combined = pd.concat(predictions, ignore_index=True)
        for (region, horizon, family), group in combined.groupby(["region", "horizon", "family"]):
            # Pending maturity is calendar-known. Missing MATURED endpoints
            # remain and invalidate the complete scheduled date, never survivors.
            measured = group.loc[group.outcomeEndDate.le(spec["dataCutoff"])]
            daily = E.daily_metrics(measured)
            opportunity = (E.selected_opportunity_evidence(
                measured.loc[measured.opportunityEvaluationEligible], spec) if family == "LINEAR"
                else {"evidence": None, "reason": "CHALLENGER_COMPLEMENT_ONLY"})
            stable = not any(f["region"] == region and f["horizon"] == horizon and f["family"] == family for f in failures)
            decision = E.verdict(daily, spec, pit_valid=True, opportunity_evidence=opportunity["evidence"], convergence_ok=stable)
            if any(f["region"] == region and f["horizon"] == horizon and f["status"] != "READY" for f in fold_records) and stable:
                decision = {"verdict": "DATA_INSUFFICIENT", "reason": "scheduled fold failed training requirements"}
            if family == "SHALLOW_CHALLENGER":
                decision["interpretation"] = "COMPLEMENTARY_ONLY_NOT_A_PRIMARY_CLAIM"
            results.append({"region": region, "horizon": int(horizon), "family": family,
                            "opportunity": opportunity,
                            "candidateChurn": E.candidate_churn(measured) if family == "LINEAR" else None,
                            "diagnosticBias": {k: float(daily[k].mean()) for k in ("expectedReturnBias", "probabilityBias") if k in daily},
                            **decision})
    # Execution cannot reach here with unresolved economic/design inputs. A new
    # reviewed version must supply those AND a completed opportunity audit.
    if spec["investability"]["minimumEdge"] is None:
        raise ValueError("BLOCKED_PREREGISTRATION")
    output = Path(output)
    if output.exists():
        raise ValueError("OUTPUT_MUST_BE_NEW")
    report = {"studyId": S.STUDY, "specSha256": S.digest(spec), "evidenceClass": "DISCOVERY_ONLY",
              "promotionEligible": False, "results": results, "folds": fold_records,
              "coverage": coverage, "ownershipOverlay": overlay, "numericalFailures": failures,
              "familyDisagreement": [{"region": region, "horizon": int(horizon), "diagnostics": E.family_disagreement(group)}
                  for (region, horizon), group in combined.groupby(["region", "horizon"])] if combined is not None else []}
    # Even if every fit failed, report explicit status for every registered cell.
    for region in spec["regions"]:
        for horizon in spec["horizons"]:
            for family in ("LINEAR", "SHALLOW_CHALLENGER"):
                if not any(r["region"] == region and r["horizon"] == horizon and r["family"] == family for r in results):
                    failed = any(f["region"] == region and f["horizon"] == horizon and f["family"] == family for f in failures)
                    results.append({"region": region, "horizon": horizon, "family": family,
                                    "verdict": "MODEL_UNSTABLE" if failed else "DATA_INSUFFICIENT"})
    S.validate_result(report, combined, spec)
    output.mkdir(parents=True)
    (output/"research-results.json").write_bytes(S.canonical(report)+b"\n")
    if predictions:
        combined.to_json(output/"predictions.jsonl", orient="records", lines=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=S.DEFAULT_SPEC)
    parser.add_argument("--sealed-sha256", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--reviewed", action="store_true")
    parser.add_argument("--input-root", type=Path)
    parser.add_argument("--us-membership", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    spec, registry = S.load_sealed(args.spec, expected_hash=args.sealed_sha256)
    report = S.readiness(spec, args.sealed_sha256)
    if not args.execute:
        print(json.dumps(report, sort_keys=True))
        return 0
    S.require_execution(spec, reviewed=args.reviewed, branch=os.environ.get("GITHUB_REF"),
                        prerequisites={"sealed": True})
    if any(x is None for x in (args.input_root, args.us_membership, args.output)):
        raise ValueError("EXECUTION_INPUTS_REQUIRED")
    subprocess.run(["git", "merge-base", "--is-ancestor", "HEAD", "origin/main"], cwd=ROOT, check=True)
    if subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT, text=True).strip():
        raise ValueError("DIRTY_EXECUTION_CHECKOUT")
    prerequisites = verify_inputs(spec, args.input_root)
    S.require_execution(spec, reviewed=args.reviewed, branch=os.environ.get("GITHUB_REF"), prerequisites=prerequisites)
    execute(spec, registry, args.input_root, args.us_membership, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
