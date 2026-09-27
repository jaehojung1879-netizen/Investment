"""HISTORICAL EXECUTION of the sealed, merged `alpha-opportunity-model-v4`
KR-only preregistration. Research only; no production import; no promotion.

THIS SCRIPT IS NOT THE PREREGISTRATION'S OWN SEALED ENTRY POINT.
`scripts/run_alpha_opportunity_model_v4.py` stays byte-identical to what PR
#159 merged (its hash is pinned in `research_specs/alpha-opportunity-model-v4
.json`'s own `dependencyHashes`, and `--execute` there still refuses
unconditionally) -- editing it to add real execution code would raise
`SEALED_DEPENDENCY_CHANGED` on every future `load_sealed()` call and would
retroactively rewrite what was reviewed. This script instead FIRST calls
`pipeline.alpha_opportunity_v4_spec.load_sealed()` as a read-only proof that
the preregistration it is about to execute is still exactly what was merged,
then performs the execution the preregistration explicitly deferred, using a
NEW module (`pipeline.alpha_opportunity_v4_execution`) that is not itself part
of the preregistration's sealed closure -- it only ever IMPORTS `pipeline.
alpha_opportunity_v4_eligibility`'s sealed functions, never edits them.

TWO-PHASE DISCIPLINE, ENFORCED BY CONTROL FLOW, NOT BY CONVENTION.
`--freeze-only` runs every step up to and including `verify_and_freeze_
foundation` (foundation-regression check, execution-snapshot hash) and
`--verify-inputs`-equivalent replay-manifest checks, then STOPS before
building a single label, printing the frozen provenance record. A real run
(`--execute`) performs that same freeze first, then proceeds; the frozen
hash is recorded in the OUTPUT REPORT and is never recomputed against a
later, possibly-different snapshot read partway through this same run
(`assert_snapshot_matches_frozen_hash` guards the one later re-read this
script does, of the reconstruction snapshot, before writing final output).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import alpha_opportunity_spec as S1  # noqa: E402
from pipeline import alpha_opportunity_v2_spec as S2  # noqa: E402
from pipeline import alpha_opportunity_v4_eligibility as ELIG  # noqa: E402
from pipeline import alpha_opportunity_v4_execution as X  # noqa: E402
from pipeline import alpha_opportunity_v4_spec as S4  # noqa: E402


class PreLabelStop(Exception):
    def __init__(self, status, detail):
        super().__init__(status)
        self.status, self.detail = status, detail


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def verify_replay_manifest(spec, input_root):
    manifest = S1.read_json(Path(input_root) / "ledger/historical/replay-v16/inputs.json")
    got = S1.digest({k: v for k, v in manifest.items() if k != "sha256"})
    cited = spec["citations"]["krTerminalActionCollectionFinalRetryRun"]
    expected = "f0781292f508a123c234ded6d28aa8e84a0dc3cc29500e14989dc0b68f53b4d2"
    if got != manifest["sha256"] or got != expected:
        raise ValueError("REPLAY_MANIFEST_HASH_MISMATCH: expected " + expected + " got " + got)
    _ = cited
    return manifest


def cited_foundation_snapshot(spec):
    """The `kr-terminal-action-reconstruction-v2.json` bytes AS CITED at seal
    time. If the current on-disk file's hash still equals the cited hash, the
    current file IS the cited one (this repository's file has not moved since
    the seal) and is returned directly -- no history search needed. Otherwise
    the exact cited blob is located by walking this repository's own git
    history for the file (a normal, git-tracked file, never on `signal-
    history`) until a revision whose content hash matches is found.
    """
    citation = spec["sourceFoundationCitation"]["krTerminalActionReconstructionV2"]
    path = ROOT / citation["path"]
    current_hash = S1.file_hash(path)
    if current_hash == citation["shaAsOfThisSeal"]:
        return S1.read_json(path), {"citedSnapshotSource": "CURRENT_FILE_UNCHANGED_SINCE_SEAL"}
    revisions = git("log", "--follow", "--format=%H", "--", str(citation["path"])).splitlines()
    for rev in revisions:
        blob = subprocess.check_output(["git", "show", f"{rev}:{citation['path']}"], cwd=ROOT)
        import hashlib
        if hashlib.sha256(blob).hexdigest() == citation["shaAsOfThisSeal"]:
            return json.loads(blob), {"citedSnapshotSource": "GIT_HISTORY", "citedSnapshotCommit": rev}
    raise ValueError("CITED_FOUNDATION_SNAPSHOT_NOT_FOUND_IN_HISTORY")


def freeze(spec, *, input_root):
    """Every step that must happen BEFORE any label is constructed."""
    manifest = verify_replay_manifest(spec, input_root)
    cited_snapshot, provenance = cited_foundation_snapshot(spec)
    current_path = ROOT / spec["sourceFoundationCitation"]["krTerminalActionReconstructionV2"]["path"]
    current_snapshot = S1.read_json(current_path)
    freeze_record = X.verify_and_freeze_foundation(cited_snapshot=cited_snapshot, current_snapshot=current_snapshot)
    return {
        "specSha256": S1.digest(spec), "immutableVersion": spec["immutableVersion"],
        "executionCodeCommitSha": git("rev-parse", "HEAD"),
        "executionCodeDirty": bool(git("status", "--porcelain", "--untracked-files=no")),
        "replayManifestSha256": manifest["sha256"], "replayVersion": manifest["replayVersion"],
        "dataCutoff": spec["dataCutoff"],
        "deterministicSeeds": {"inference": spec["carriedFromV3"]["inference"]["seed"],
                              "uncertainty": spec["carriedFromV3"]["uncertainty"]["seed"]},
        **freeze_record, **provenance,
        "currentFoundationSnapshotPath": str(current_path.relative_to(ROOT)),
    }, current_snapshot


def pre_label_gates(annotated_by_horizon, v2_spec):
    from pipeline import alpha_opportunity_features as F
    from pipeline import alpha_opportunity_v2_evaluation as E
    registry = S1.read_json(ROOT / "research_specs/alpha-opportunity-model-v1-features.json")
    cov_cfg = v2_spec["coverageGate"]
    any_horizon = next(iter(annotated_by_horizon.values()))
    eligible = any_horizon.loc[any_horizon.tradable].assign(region="KR")
    coverage = F.coverage(eligible, registry)
    failures = [c for c in coverage if c["region"] == "KR" and int(c["year"]) >= cov_cfg["firstEvaluationYear"]
                and c["coverage"] < (cov_cfg["price"] if c["feature"] in F.PRICE + F.ATTENTION else cov_cfg["accounting"])]
    if failures:
        raise PreLabelStop("BLOCKED_BY_DATA_INTEGRITY", {"coverageFailures": failures})
    dates = eligible.drop_duplicates("date")
    by_year = dates.date.str[:4].value_counts().to_dict()
    depth = E.calendar_depth(by_year, v2_spec)
    if depth["status"] != "SUFFICIENT_UPPER_BOUND":
        raise PreLabelStop("BLOCKED_BY_SAMPLE_DEPTH", {"calendarDepth": depth})
    return coverage, depth


def execute(v4_spec, v2_spec, *, input_root, output):
    import pandas as pd
    from pipeline import alpha_opportunity_v2_decision as D
    from pipeline import alpha_opportunity_v2_evaluation as E
    from pipeline import alpha_opportunity_v2_model as M
    from pipeline import regional_alpha_features as SOURCES
    from pipeline import replay_calendar as RC

    output = Path(output).resolve()
    if output.exists() or output.is_relative_to(ROOT):
        raise ValueError("OUTPUT_MUST_BE_NEW_AND_OUTSIDE_THE_REPOSITORY")

    freeze_record, current_snapshot = freeze(v4_spec, input_root=input_root)
    completeness_map = X.completeness_by_code(current_snapshot)
    terminated_codes = [r["code"] for r in S1.read_json(
        ROOT / "docs/results/alpha-opportunity-model-v3-survivorship-audit.json")["krTerminations"]]

    # ---- Everything above this line is outcome-free. ---------------------
    ledger = Path(input_root) / "ledger"
    manifest, prices, _, _ = SOURCES.load_inputs(ledger)
    if manifest["sha256"] != freeze_record["replayManifestSha256"]:
        raise ValueError("INPUT_MANIFEST_CHANGED_MID_RUN")
    memberships = X.load_kr_memberships(ledger)
    raw, shares = X.load_kr_raw(ledger)
    runtime_spec = X.build_runtime_spec(v4_spec, v2_spec)

    frame = X.build_kr_matrix(prices, memberships, raw, shares,
                              start=runtime_spec["walkForward"]["featureStart"], through=runtime_spec["dataCutoff"])
    window = runtime_spec["tradabilityGuard"]["windowSessions"]
    guard = X.tradability_frame_kr(prices, frame, window)
    frame = frame.merge(guard, on=["date", "region", "ticker"], how="left", validate="one_to_one")
    if frame.tradable.isna().any():
        raise ValueError("TRADABILITY_UNRESOLVED")
    frame["tradable"] = frame.tradable.astype(bool)
    frame["vouched"] = frame.vouched.astype(bool)
    unvouched_by_date = (1 - frame.groupby(["region", "date"]).vouched.mean()).to_dict()

    regional = frame.loc[frame.tradable].copy()
    regional["roundTripCost"] = [D.dated_round_trip_cost("KR", d, runtime_spec) for d in regional.date]
    schedule = sorted(regional.date.unique())
    sessions = RC.sessions("2012-01-01", "2027-12-31", "KR")

    annotated_by_horizon, predictions, fold_records, failures = {}, [], [], []
    for horizon in runtime_spec["horizons"]:
        labels = pd.DataFrame([E.target_from_sessions(sessions, prices, runtime_spec["benchmarks"]["KR"],
                                                       t, d, horizon, runtime_spec["dataCutoff"])
                               for t, d in zip(regional.ticker, regional.date)])
        data = E.attach_labels(regional, labels)
        annotated = X.attach_eligibility(data, prices, completeness_map)
        annotated_by_horizon[horizon] = annotated

    try:
        coverage, depth = pre_label_gates(annotated_by_horizon, v2_spec)
    except PreLabelStop as stop:
        report = _base_report(v4_spec, freeze_record, status=stop.status, stopped_before_labels=True,
                              detail=stop.detail, results=[], folds=[], coverage=None, depth=None,
                              diagnostics=None)
        _write(output, report, None)
        return report

    # ---- Labels are used past this line. ----------------------------------
    for horizon, annotated in annotated_by_horizon.items():
        for_modelling = annotated.copy()
        ineligible_matured = for_modelling.labelStatus.eq("MATURED") & ~for_modelling.eligibilityStatus.eq(ELIG.ELIGIBLE)
        for_modelling.loc[ineligible_matured, "labelStatus"] = "MISSING_FORWARD_PRICE_OR_DELISTING"
        for_modelling.loc[ineligible_matured, ["forwardRelativeReturn", "beatBenchmarkNet"]] = None
        out, folds, fails = M.predict_cell(for_modelling, schedule, "KR", horizon, runtime_spec, S1.digest(v4_spec))
        predictions.extend(out)
        fold_records.extend([{**f, "horizon": horizon} if "horizon" not in f else f for f in folds])
        failures.extend(fails)

    combined = pd.concat(predictions, ignore_index=True) if predictions else None
    results = []
    for horizon in runtime_spec["horizons"]:
        cell = (combined.loc[combined.region.eq("KR") & combined.horizon.eq(horizon) & combined.family.eq("LINEAR")]
                if combined is not None else None)
        results.append(E.evaluate_cell(
            cell, [f for f in fold_records if f.get("horizon") == horizon],
            [f for f in failures if f.get("horizon") == horizon],
            unvouched_by_date, runtime_spec, region="KR", horizon=horizon))

    full_annotated = pd.concat(annotated_by_horizon.values(), ignore_index=True)
    diagnostics = X.missingness_integrity_report(full_annotated, regional, prices, terminated_codes)

    # A later re-read of the snapshot, proven unchanged since the freeze
    # above -- guards a mid-run swap even though nothing between the freeze
    # and here re-reads the foundation for a DECISION.
    ELIG.assert_snapshot_matches_frozen_hash(
        reconstruction_snapshot=S1.read_json(
            ROOT / v4_spec["sourceFoundationCitation"]["krTerminalActionReconstructionV2"]["path"]),
        frozen_hash=freeze_record["frozenExecutionSnapshotHash"])

    report = _base_report(v4_spec, freeze_record, status="EXECUTED", stopped_before_labels=False,
                          detail=None, results=results, folds=fold_records, coverage=coverage, depth=depth,
                          diagnostics=diagnostics, numerical_failures=failures)
    _write(output, report, combined)
    return report


def _base_report(spec, freeze_record, *, status, stopped_before_labels, detail, results, folds,
                 coverage, depth, diagnostics, numerical_failures=None):
    return {
        "studyId": spec["studyId"], "specSha256": freeze_record["specSha256"],
        "evidenceClass": "HISTORICAL_OOS", "promotionEligible": False,
        "status": status, "stoppedBeforeLabels": stopped_before_labels, "detail": detail,
        "frozenExecutionProvenance": freeze_record,
        "results": results, "folds": folds, "coverage": coverage, "calendarDepth": depth,
        "missingnessIntegrityDiagnostics": diagnostics, "numericalFailures": numerical_failures or [],
    }


def _write(output, report, combined):
    output.mkdir(parents=True)
    (output / "alpha-opportunity-model-v4-execution-report.json").write_bytes(S1.canonical(report) + b"\n")
    if combined is not None:
        combined.to_json(output / "predictions.jsonl.gz", orient="records", lines=True,
                         compression={"method": "gzip", "mtime": 0})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=S4.DEFAULT_SPEC)
    parser.add_argument("--sealed-sha256", required=True)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--freeze-only", action="store_true",
                        help="Run every pre-label step and print the frozen provenance, then stop.")
    args = parser.parse_args(argv)

    v4_spec = S4.load_sealed(args.spec, expected_hash=args.sealed_sha256)
    v2_hash = "97c3727b37eeab71e31ffee17a2f81cac29f0333552ff04a5374ef48484b0e19"
    v2_spec, _ = S2.load_sealed(ROOT / "research_specs/alpha-opportunity-model-v2.json", expected_hash=v2_hash)

    if args.freeze_only:
        freeze_record, _ = freeze(v4_spec, input_root=args.input_root)
        print(json.dumps(freeze_record, sort_keys=True))
        return 0

    report = execute(v4_spec, v2_spec, input_root=args.input_root, output=args.output)
    print(json.dumps({"status": report["status"], "specSha256": report["specSha256"],
                      "frozenExecutionSnapshotHash":
                          report["frozenExecutionProvenance"]["frozenExecutionSnapshotHash"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
