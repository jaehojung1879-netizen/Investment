"""HISTORICAL EXECUTION of the sealed, merged `alpha-opportunity-model-v4`
KR-only preregistration. Research only; no production import; no promotion.

THIS SCRIPT IS NOT THE PREREGISTRATION'S OWN SEALED ENTRY POINT.
`scripts/run_alpha_opportunity_model_v4.py` stays byte-identical to what PR
#159 merged (its hash is pinned in the v4 spec's own `dependencyHashes`, and
`--execute` there still refuses unconditionally). This script first calls
`pipeline.alpha_opportunity_v4_spec.load_sealed()` as a read-only proof the
preregistration is still exactly what was merged.

ORDER, ENFORCED BY CONTROL FLOW. v2's sealed `runtimePreLabelGates` order,
narrowed to KR, with the one step the sealed v4 spec replaces removed:

  1. sealed spec identities (v4, and v2/v3 whose sealed JSON supplies runtime
     constants and the raw-input identity)
  2. SEALED_INPUT_IDENTITY: signal-history checkout commit, git-blob identity
     of every raw file read, replay manifest digest; KR terminal-action
     foundation checked for regression and frozen
  3. PIT features (`build_kr_matrix`)
  4. tradability guard (v2's own `tradability_frame`, called)
  5. FEATURE_COVERAGE and CALENDAR_SAMPLE_DEPTH on every tradable KR
     name-date (`alpha_opportunity_v4_execution.pre_label_gates`: v2's
     thresholds and `calendar_depth`, v4's denominator)
  6. only now: identity re-verified, then forward labels, v4 per-observation
     `label_eligibility`, walk-forward fits and evaluation.

There is NO region-year survivorship step. v2's
`REGION_YEAR_SURVIVORSHIP_ELIGIBILITY` (20% unvouched tolerance) is replaced
by v4's per-observation `label_eligibility`, per the sealed v4 spec's
`carriedFromV3.walkForward.survivorshipEligibility`.

Nothing before step 6 calls `target_from_sessions`, reads a price after a
signal date, builds `forwardRelativeReturn`/`beatBenchmarkNet`, or calls
`label_eligibility`. `--stop-before-labels` ends a run after step 5 whatever
the gates say.

Two earlier harness revisions in this PR broke the contract. Contract V1 built
forward labels and called `label_eligibility` BEFORE the coverage gate (raw
report kept as `docs/results/alpha-opportunity-model-v4-execution-run1-
defective.json`). Contract V2 fixed that but still applied v2's replaced
region-year tolerance (it excluded nothing: every KR year was under 0.13%
unvouched). This is contract V3.
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
from scripts import run_alpha_opportunity_model_v2 as V2  # noqa: E402

V2_SEAL = "97c3727b37eeab71e31ffee17a2f81cac29f0333552ff04a5374ef48484b0e19"
V3_SPEC = ROOT / "research_specs/alpha-opportunity-model-v3.json"
REGISTRY = ROOT / "research_specs/alpha-opportunity-model-v1-features.json"
SURVIVORSHIP_AUDIT = ROOT / "docs/results/alpha-opportunity-model-v3-survivorship-audit.json"

STOPPED_FOR_REVIEW = "PRE_LABEL_GATES_PASSED_STOPPED_BEFORE_LABELS"


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def load_v3_spec(v4_spec):
    """v3's JSON is one of v4's sealed inputs; `load_sealed` has already
    verified its bytes against v4's `dependencyHashes`."""
    v3 = S1.read_json(V3_SPEC)
    if S1.digest(v3) != next(p["specSha256"] for p in v4_spec["priorVersions"]
                             if p["studyId"] == "alpha-opportunity-model-v3"):
        raise ValueError("PRIOR_SEAL_CHANGED: alpha-opportunity-model-v3")
    return v3


def cited_foundation_snapshot(spec):
    """The KR terminal-action reconstruction bytes AS CITED at seal time: the
    current file if its hash still equals the citation, otherwise the exact
    blob found in this repository's own git history."""
    import hashlib
    citation = spec["sourceFoundationCitation"]["krTerminalActionReconstructionV2"]
    path = ROOT / citation["path"]
    if S1.file_hash(path) == citation["shaAsOfThisSeal"]:
        return S1.read_json(path), {"citedSnapshotSource": "CURRENT_FILE_UNCHANGED_SINCE_SEAL"}
    for rev in git("log", "--follow", "--format=%H", "--", citation["path"]).splitlines():
        blob = subprocess.check_output(["git", "show", f"{rev}:{citation['path']}"], cwd=ROOT)
        if hashlib.sha256(blob).hexdigest() == citation["shaAsOfThisSeal"]:
            return json.loads(blob), {"citedSnapshotSource": "GIT_HISTORY", "citedSnapshotCommit": rev}
    raise ValueError("CITED_FOUNDATION_SNAPSHOT_NOT_FOUND_IN_HISTORY")


def foundation_path(spec):
    return ROOT / spec["sourceFoundationCitation"]["krTerminalActionReconstructionV2"]["path"]


def freeze(v4_spec, v3_spec, *, input_root, expected_signal_history_sha=None,
           expected_input_identity_sha256=None):
    """Every byte-level identity check, before any row is read."""
    identity = X.verify_input_identity(X.sealed_input_identity(v3_spec), input_root,
                                       expected_signal_history_sha=expected_signal_history_sha)
    if (expected_input_identity_sha256 is not None
            and identity["inputIdentitySha256"] != expected_input_identity_sha256):
        raise ValueError("INPUT_IDENTITY_DIFFERS_FROM_FREEZE")
    cited_snapshot, provenance = cited_foundation_snapshot(v4_spec)
    current_snapshot = S1.read_json(foundation_path(v4_spec))
    foundation = X.verify_and_freeze_foundation(cited_snapshot=cited_snapshot,
                                                current_snapshot=current_snapshot)
    record = {
        "harnessContract": X.CONTRACT,
        "specSha256": S1.digest(v4_spec), "immutableVersion": v4_spec["immutableVersion"],
        "executionCodeCommitSha": git("rev-parse", "HEAD"),
        "executionCodeDirty": bool(git("status", "--porcelain", "--untracked-files=no")),
        "dataCutoff": v4_spec["dataCutoff"],
        "deterministicSeeds": {"inference": v4_spec["carriedFromV3"]["inference"]["seed"],
                               "uncertainty": v4_spec["carriedFromV3"]["uncertainty"]["seed"]},
        "inputIdentity": identity, **foundation, **provenance,
        "currentFoundationSnapshotPath": str(foundation_path(v4_spec).relative_to(ROOT)),
    }
    return record, current_snapshot


def _counters():
    return {"targetFromSessionsCalls": 0, "labelEligibilityCalls": 0, "predictCellCalls": 0,
            "evaluateCellCalls": 0}


def run_from_features(frame, prices, *, runtime_spec, registry, completeness_map, terminated_codes,
                      spec_hash, stop_before_labels, before_labels=lambda: None):
    """Steps 4-7 on an already-built PIT feature frame.

    Returns a result dict; never raises on a registered pre-label stop. The
    `counts` it returns are incremented at the call sites themselves, so a
    stopped run reports the zeros it actually observed rather than asserting
    them.
    """
    import pandas as pd
    from pipeline import alpha_opportunity_v2_decision as D
    from pipeline import alpha_opportunity_v2_evaluation as E
    from pipeline import alpha_opportunity_v2_model as M
    from pipeline import replay_calendar as RC

    counts = _counters()
    base = {"counts": counts}
    window = runtime_spec["tradabilityGuard"]["windowSessions"]
    guard = V2.tradability_frame(prices, frame, "KR", window)
    frame = frame.merge(guard, on=["date", "region", "ticker"], how="left", validate="one_to_one")
    if frame.tradable.isna().any():
        raise ValueError("TRADABILITY_UNRESOLVED")
    frame["tradable"] = frame.tradable.astype(bool)
    frame["vouched"] = frame.vouched.astype(bool)
    # Counts only; no price after a signal date enters any of them.
    base["preLabelFrame"] = {"memberDates": int(len(frame)), "tradable": int(frame.tradable.sum()),
                             "horizons": list(runtime_spec["horizons"])}
    try:
        coverage, depth = X.pre_label_gates(frame, registry, runtime_spec)
    except X.PreLabelStop as stop:
        return {**base, "status": stop.status, "stoppedBeforeLabels": True, "detail": stop.detail}
    base.update(coverage=coverage, calendarDepth=depth)
    if stop_before_labels:
        return {**base, "status": STOPPED_FOR_REVIEW, "stoppedBeforeLabels": True, "detail": None}

    # ---- Step 7. Labels exist only past this line. ----------------------
    before_labels()
    # A per-DATE share for evaluate_cell's own endpoint stress, not a gate.
    unvouched_by_date = (1 - frame.groupby(["region", "date"]).vouched.mean()).to_dict()
    regional = frame.loc[frame.tradable].copy()
    regional["roundTripCost"] = [D.dated_round_trip_cost("KR", d, runtime_spec) for d in regional.date]
    schedule = sorted(regional.date.unique())
    sessions = RC.sessions("2012-01-01", "2027-12-31", "KR")
    annotated_by_horizon, predictions, fold_records, failures = {}, [], [], []
    for horizon in runtime_spec["horizons"]:
        label_rows = []
        for t, d in zip(regional.ticker, regional.date):
            counts["targetFromSessionsCalls"] += 1
            label_rows.append(E.target_from_sessions(sessions, prices, runtime_spec["benchmarks"]["KR"],
                                                     t, d, horizon, runtime_spec["dataCutoff"]))
        data = E.attach_labels(regional, pd.DataFrame(label_rows))
        counts["labelEligibilityCalls"] += len(data)
        annotated = X.attach_eligibility(data, prices, completeness_map)
        annotated_by_horizon[horizon] = annotated.assign(horizon=horizon)
        for_modelling = annotated.copy()
        ineligible = for_modelling.labelStatus.eq("MATURED") & ~for_modelling.eligibilityStatus.eq(ELIG.ELIGIBLE)
        for_modelling.loc[ineligible, "labelStatus"] = "MISSING_FORWARD_PRICE_OR_DELISTING"
        for_modelling.loc[ineligible, ["forwardRelativeReturn", "beatBenchmarkNet"]] = None
        counts["predictCellCalls"] += 1
        out, folds, fails = M.predict_cell(for_modelling, schedule, "KR", horizon, runtime_spec, spec_hash)
        predictions.extend(out)
        fold_records.extend(folds)
        failures.extend(fails)
    combined = pd.concat(predictions, ignore_index=True) if predictions else None
    results = []
    for horizon in runtime_spec["horizons"]:
        cell = (combined.loc[combined.horizon.eq(horizon) & combined.family.eq("LINEAR")]
                if combined is not None else None)
        counts["evaluateCellCalls"] += 1
        results.append(E.evaluate_cell(cell, [f for f in fold_records if f["horizon"] == horizon],
                                       [f for f in failures if f["horizon"] == horizon],
                                       unvouched_by_date, runtime_spec, region="KR", horizon=horizon))
    diagnostics = X.missingness_integrity_report(pd.concat(annotated_by_horizon.values(), ignore_index=True),
                                                 regional, prices, terminated_codes)
    return {**base, "status": "EXECUTED", "stoppedBeforeLabels": False, "detail": None,
            "results": results, "folds": fold_records, "numericalFailures": failures,
            "missingnessIntegrityDiagnostics": diagnostics, "predictions": combined}


def execute(v4_spec, v2_spec, v3_spec, *, input_root, output, stop_before_labels,
            expected_signal_history_sha=None, expected_input_identity_sha256=None):
    from pipeline import regional_alpha_features as SOURCES

    output = Path(output).resolve()
    if output.exists() or output.is_relative_to(ROOT):
        raise ValueError("OUTPUT_MUST_BE_NEW_AND_OUTSIDE_THE_REPOSITORY")
    freeze_record, current_snapshot = freeze(
        v4_spec, v3_spec, input_root=input_root, expected_signal_history_sha=expected_signal_history_sha,
        expected_input_identity_sha256=expected_input_identity_sha256)
    sealed = X.sealed_input_identity(v3_spec)

    ledger = Path(input_root) / "ledger"
    manifest, prices, _, _ = SOURCES.load_inputs(ledger)
    if manifest["sha256"] != freeze_record["inputIdentity"]["replayManifestSha256"]:
        raise ValueError("INPUT_MANIFEST_CHANGED_MID_RUN")
    runtime_spec = X.build_runtime_spec(v4_spec, v2_spec)
    raw, shares = X.load_kr_raw(ledger)
    frame = X.build_kr_matrix(prices, X.load_kr_memberships(ledger), raw, shares,
                              start=runtime_spec["walkForward"]["featureStart"],
                              through=runtime_spec["dataCutoff"])

    def before_labels():
        # The snapshot this run froze, and the bytes it froze, are still
        # the ones on disk -- checked after the gates, before any label.
        ELIG.assert_snapshot_matches_frozen_hash(
            reconstruction_snapshot=S1.read_json(foundation_path(v4_spec)),
            frozen_hash=freeze_record["frozenExecutionSnapshotHash"])
        again = X.verify_input_identity(sealed, input_root,
                                        expected_signal_history_sha=freeze_record["inputIdentity"]["signalHistoryCommit"])
        if again["inputIdentitySha256"] != freeze_record["inputIdentity"]["inputIdentitySha256"]:
            raise ValueError("INPUT_IDENTITY_CHANGED_MID_RUN")

    result = run_from_features(
        frame, prices, runtime_spec=runtime_spec, registry=S1.read_json(REGISTRY),
        completeness_map=X.completeness_by_code(current_snapshot),
        terminated_codes=[r["code"] for r in S1.read_json(SURVIVORSHIP_AUDIT)["krTerminations"]],
        spec_hash=S1.digest(v4_spec), stop_before_labels=stop_before_labels, before_labels=before_labels)
    predictions = result.pop("predictions", None)
    report = {"studyId": v4_spec["studyId"], "specSha256": freeze_record["specSha256"],
              "evidenceClass": "HISTORICAL_OOS", "promotionEligible": False,
              "stopBeforeLabelsRequested": stop_before_labels,
              "frozenExecutionProvenance": freeze_record,
              "featureFrame": {"memberDates": int(len(frame)), "firstDate": str(frame.date.min()),
                               "lastDate": str(frame.date.max())},
              "results": [], "folds": [], "numericalFailures": [], "coverage": None,
              "calendarDepth": None, "missingnessIntegrityDiagnostics": None, **result}
    output.mkdir(parents=True)
    (output / "alpha-opportunity-model-v4-execution-report.json").write_bytes(S1.canonical(report) + b"\n")
    if predictions is not None:
        predictions.to_json(output / "predictions.jsonl.gz", orient="records", lines=True,
                            compression={"method": "gzip", "mtime": 0})
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=S4.DEFAULT_SPEC)
    parser.add_argument("--sealed-sha256", required=True)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--freeze-only", action="store_true",
                        help="Verify and print the frozen input/foundation identity; read no row.")
    parser.add_argument("--stop-before-labels", action="store_true",
                        help="End after the pre-label gates whatever they say.")
    parser.add_argument("--expected-signal-history-sha")
    parser.add_argument("--expected-input-identity-sha256")
    args = parser.parse_args(argv)

    v4_spec = S4.load_sealed(args.spec, expected_hash=args.sealed_sha256)
    v2_spec, _ = S2.load_sealed(ROOT / "research_specs/alpha-opportunity-model-v2.json", expected_hash=V2_SEAL)
    v3_spec = load_v3_spec(v4_spec)
    if args.freeze_only:
        record, _ = freeze(v4_spec, v3_spec, input_root=args.input_root,
                           expected_signal_history_sha=args.expected_signal_history_sha,
                           expected_input_identity_sha256=args.expected_input_identity_sha256)
        print(json.dumps(record, sort_keys=True))
        return 0
    if args.output is None:
        raise ValueError("OUTPUT_REQUIRED")
    report = execute(v4_spec, v2_spec, v3_spec, input_root=args.input_root, output=args.output,
                     stop_before_labels=args.stop_before_labels,
                     expected_signal_history_sha=args.expected_signal_history_sha,
                     expected_input_identity_sha256=args.expected_input_identity_sha256)
    print(json.dumps({"status": report["status"], "stoppedBeforeLabels": report["stoppedBeforeLabels"],
                      "counts": report["counts"], "specSha256": report["specSha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
