"""alpha-opportunity-model-v5 execution-harness tests. SYNTHETIC FIXTURES ONLY.

Nothing here reads a real replay price, KR ledger shard, label or Alpha outcome, and nothing here executes
the frozen v5 protocol. The harness under test is outside the sealed preregistration's dependency closure;
these tests prove it wires the frozen contract up correctly and fails closed where it cannot.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import v5_harness_fixtures as W  # noqa: E402

from pipeline import alpha_inference_calibration_v4 as ENGINE  # noqa: E402
from pipeline import alpha_opportunity_model as V1  # noqa: E402
from pipeline import alpha_opportunity_v2_evaluation as E  # noqa: E402
from pipeline import alpha_opportunity_v2_model as M  # noqa: E402
from pipeline import alpha_opportunity_v4_eligibility as ELIG  # noqa: E402
from pipeline import alpha_opportunity_v5_evidence as EV  # noqa: E402
from pipeline import alpha_opportunity_v5_execution as X  # noqa: E402
from pipeline import alpha_opportunity_v5_spec as S5  # noqa: E402
from pipeline import kr_repaired_accounting_snapshot as K  # noqa: E402
from pipeline.alpha_opportunity_spec import canonical, digest  # noqa: E402
from scripts import execute_alpha_opportunity_model_v5 as CLI  # noqa: E402
from scripts import run_alpha_opportunity_model_v5 as RUN  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "research_specs/alpha-opportunity-model-v5.json"
SEAL = W.SPEC_SHA
FROZEN_FILE_SHA256 = "8a0a42a3f9414dbefa3ab8ec47f00ad71f8d7436febb125dff150f3c1e50d54c"
FROZEN_DOC_SHA256 = hashlib.sha256((ROOT / "docs/alpha-opportunity-model-v5-preregistration.md").read_bytes()).hexdigest()
spec = W.sealed_spec()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def file_guard(path):
    guard = X.IdentityGuard({"input": lambda: sha(path)})
    guard.freeze()
    return guard


class Spy:
    """Replaces an outcome-reading or model-consuming function and records that it was reached."""

    def __init__(self):
        self.calls = []

    def raising(self, name):
        def fn(*a, **k):
            self.calls.append(name)
            raise AssertionError(f"{name} was reached")
        return fn


@pytest.fixture(scope="module")
def leaky():
    """One full synthetic run with every training frame, fit call and evaluation input captured."""
    world = W.make_world(seed=7, leak=True)
    captured = {"fits": [], "evaluations": [], "checksAtFirstLabel": [], "modelling": {}}
    real_fit, real_eval, real_target = X._fit_predict, X.evaluate_cell, E.target_from_sessions
    real_labels = X.build_labels
    guard = X.IdentityGuard({"constant": lambda: "fixed"})
    guard.freeze()

    def fit(kind, train, valid, names, runtime_spec):
        captured["fits"].append({"kind": kind, "train": train, "valid": valid, "names": list(names)})
        return real_fit(kind, train, valid, names, runtime_spec)

    def evaluate(table, cell, horizon, *a, **k):
        out = real_eval(table, cell, horizon, *a, **k)
        captured["evaluations"].append({"table": table, "cell": cell, "horizon": horizon, "args": (a[1:], k)})
        return out

    def labels(permit, regional, prices, sessions, runtime_spec, completeness, counters, horizon):
        annotated, modelling = real_labels(permit, regional, prices, sessions, runtime_spec, completeness, counters, horizon)
        captured["modelling"][horizon] = modelling
        return annotated, modelling

    def target(*a, **k):
        if not captured["checksAtFirstLabel"]:
            captured["checksAtFirstLabel"] = [c["at"] for c in guard.checks]
        return real_target(*a, **k)

    mp = pytest.MonkeyPatch()
    mp.setattr(X, "_fit_predict", fit)
    mp.setattr(X, "evaluate_cell", evaluate)
    mp.setattr(X, "build_labels", labels)
    mp.setattr(E, "target_from_sessions", target)
    try:
        result = W.run_world(world, guard=guard)
    finally:
        mp.undo()
    return {"world": world, "result": result, "captured": captured, "guard": guard}


# --------------------------------------------------------------------------- #
# Seal protection and the frozen-file audit
# --------------------------------------------------------------------------- #
def test_preregistration_is_byte_identical_and_digest_unchanged():
    assert sha(SPEC_PATH) == FROZEN_FILE_SHA256
    assert digest(json.loads(SPEC_PATH.read_text())) == SEAL == (ROOT / "research_specs/alpha-opportunity-model-v5.sha256").read_text().strip()
    assert spec["executionHarness"]["status"] == "NOT_BUILT_IN_THIS_PR"
    assert spec["executionHarness"]["expectedFiles"] == ["pipeline/alpha_opportunity_v5_execution.py",
                                                         "scripts/execute_alpha_opportunity_model_v5.py"]


def test_frozen_files_match_the_preregistration_merge_when_history_is_available():
    base = "f0166783cb72e47557663fa87abec57c8a25536d"
    if subprocess.run(["git", "cat-file", "-e", base], cwd=ROOT, capture_output=True).returncode != 0:
        pytest.skip("base commit not fetched")
    for rel in ("research_specs/alpha-opportunity-model-v5.json", "research_specs/alpha-opportunity-model-v5.sha256",
                "docs/alpha-opportunity-model-v5-preregistration.md", "pipeline/alpha_opportunity_v5_spec.py",
                "scripts/run_alpha_opportunity_model_v5.py"):
        merged = subprocess.check_output(["git", "show", f"{base}:{rel}"], cwd=ROOT)
        assert (ROOT / rel).read_bytes() == merged, rel


def test_harness_is_outside_the_sealed_closure_and_the_sealed_runner_still_refuses():
    sealed = set(S5.sealed_file_set(spec))
    assert sealed == set(spec["dependencyHashes"])
    for rel in X.HARNESS_FILES:
        assert rel not in sealed
    with pytest.raises(RuntimeError, match="NO_V5_EXECUTION_HARNESS_IN_THIS_PR"):
        RUN.main(["--sealed-sha256", SEAL, "--execute"])


def test_predecessor_seals_and_inherited_values_verify_and_a_wrong_digest_is_refused():
    assert S5.verify_prior_versions(spec) is True and S5.verify_inherited(spec) is True
    with pytest.raises(ValueError, match="SEALED_SPEC_CHANGED"):
        S5.load_sealed(expected_hash="0" * 64)


def test_a_changed_spec_file_is_refused_by_the_identity_component(tmp_path):
    copy = tmp_path / "alpha-opportunity-model-v5.json"
    copy.write_bytes(SPEC_PATH.read_bytes())
    (tmp_path / "alpha-opportunity-model-v5.sha256").write_text(SEAL)
    assert X.spec_identity(copy, SEAL)["specSha256"] == SEAL
    data = json.loads(copy.read_text())
    data["dataCutoff"] = "2026-09-15"
    copy.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="SEALED_SPEC_CHANGED"):
        X.spec_identity(copy, SEAL)


def test_authorization_and_result_artifacts_do_not_exist_in_this_change():
    assert not list((ROOT / "docs/results").glob("alpha-opportunity-model-v5*"))
    assert not list(ROOT.glob("**/alpha-opportunity-model-v5-result*"))


def test_frozen_scientific_contract_read_by_the_harness():
    rt = X.build_runtime_spec(spec)
    assert rt["regions"] == ["KR"] and rt["horizons"] == [21, 126] and rt["benchmarks"] == {"KR": "069500.KS"}
    assert rt["minimumConfirmatoryDepth"] == {"21": 78, "126": 312}
    assert rt["models"]["ridge"]["alpha"] == 10.0 and rt["models"]["logistic"]["C"] == 1.0
    assert rt["models"]["histGradientBoosting"] == {"early_stopping": False, "l2_regularization": 10.0,
                                                    "learning_rate": 0.05, "max_depth": None, "max_iter": 100,
                                                    "max_leaf_nodes": 7, "min_samples_leaf": 50, "random_state": 42}
    assert rt["models"]["search"] is False and rt["models"]["threads"] == 1
    assert rt["allowedFeatures"]["KR"]["21"] == ["relative126", "acceleration21", "vol63", "logVolumeShock60",
                                                  "shockPersistence5d", "volumePriceAlignment"]
    assert rt["allowedFeatures"]["KR"]["126"][-2:] == ["assetGrowthPct", "debtGrowthPct"]
    assert "ocfToNetIncomePct" not in rt["allowedFeatures"]["KR"]["126"]
    assert rt["walkForward"]["minimumNamesPerDate"] == 10 and rt["walkForward"]["minimumMaturedDates"] == 104
    assert rt["tradabilityGuard"]["windowSessions"] == 20
    assert rt["coverageGate"]["price"] == 0.8 and rt["coverageGate"]["accounting"] == 0.2 and rt["coverageGate"]["firstGateYear"] == 2016
    assert rt["dataCutoff"] == "2026-09-14"


# --------------------------------------------------------------------------- #
# Outcome sequencing: pre-label failure means zero outcome-reading calls
# --------------------------------------------------------------------------- #
def install_spies(monkeypatch):
    spy = Spy()
    monkeypatch.setattr(E, "target_from_sessions", spy.raising("target_from_sessions"))
    monkeypatch.setattr(E, "attach_labels", spy.raising("attach_labels"))
    monkeypatch.setattr(ELIG, "label_eligibility", spy.raising("label_eligibility"))
    monkeypatch.setattr(X, "_fit_predict", spy.raising("fit_predict"))
    monkeypatch.setattr(V1, "estimator_pair", spy.raising("estimator_pair"))
    monkeypatch.setattr(M, "prediction_uncertainty", spy.raising("prediction_uncertainty"))
    monkeypatch.setattr(EV, "horizon_evidence", spy.raising("horizon_evidence"))
    monkeypatch.setattr(X, "evaluate_cell", spy.raising("evaluate_cell"))
    return spy


def assert_no_outcome_reached(result, spy):
    assert spy.calls == []
    assert result["ordering"]["counters"] == dict.fromkeys(X.Counters.NAMES, 0)
    assert result["ordering"]["labelsBuilt"] is False and result["ordering"]["stoppedBeforeLabels"] is True
    assert result["cells"] == {}


@pytest.fixture(scope="module")
def small_world():
    return W.make_world(seed=5, n=12)


def test_coverage_gate_failure_stops_before_any_label_fit_prediction_or_evaluation(small_world, monkeypatch):
    spy = install_spies(monkeypatch)

    def break_2020_accounting(frame):
        frame.loc[frame.date.str[:4].eq("2020"), "assetGrowthPct"] = np.nan
        return frame

    result = W.run_world(small_world, frame_mutator=break_2020_accounting)
    assert_no_outcome_reached(result, spy)
    assert result["overallStatus"] == "DATA_INSUFFICIENT" and result["phaseReached"] == "PRE_LABEL_GATES"
    assert result["stop"]["status"] == X.GATE_INTEGRITY
    assert result["claims"]["126"]["reason"] == "PRE_LABEL_GATE_FAILED"
    # H21 has no accounting field, so its own gate passed; it is still not evaluated once a gate has failed.
    assert result["claims"]["21"]["reason"] == "RUN_STOPPED_BEFORE_LABELS_BY_ANOTHER_CELLS_GATE"
    assert result["substantiveResult"] is True  # a gate stop in the formal run is a registered, closing result
    assert result["promotionEligible"] is False


def test_depth_gate_failure_stops_before_any_label(small_world, monkeypatch):
    spy = install_spies(monkeypatch)
    rt = W.runtime(depth={"21": 30, "126": 10_000})
    result = W.run_world(small_world, rt=rt)
    assert_no_outcome_reached(result, spy)
    assert result["stop"]["status"] == X.GATE_DEPTH and result["claims"]["126"]["reason"] == "PRE_LABEL_GATE_FAILED"
    assert any(f["reason"] == "CALENDAR_DEPTH_UPPER_BOUND_BELOW_FLOOR"
               for f in result["preLabelGates"] or result["stop"]["detail"]["cells"]["126"]["failures"])


def test_gates_only_mode_builds_no_label_and_is_never_substantive(small_world, monkeypatch):
    spy = install_spies(monkeypatch)
    result = W.run_world(small_world, mode=X.GATES_ONLY)
    assert spy.calls == [] and result["ordering"]["stoppedBeforeLabels"] is True
    assert result["overallStatus"] == "NOT_EVALUATED" and result["substantiveResult"] is False
    assert result["closesPreregistration"] is False and result["phaseReached"] == "PRE_LABEL_GATES"
    assert all(c["status"] == "NOT_EVALUATED" for c in result["claims"].values())
    assert set(result["preLabelGates"]) == {"21", "126"}


def test_no_coverage_year_and_low_price_coverage_are_gate_failures(small_world):
    def sparse_price(frame):
        mask = frame.date.str[:4].eq("2019") & (np.arange(len(frame)) % 3 != 0)
        frame.loc[mask, "logVolumeShock60"] = np.nan
        return frame

    result = W.run_world(small_world, frame_mutator=sparse_price, mode=X.GATES_ONLY)
    assert result["stop"]["status"] == X.GATE_INTEGRITY
    cell = result["stop"]["detail"]["cells"]["21"]
    assert cell["failures"][0]["reason"] == "COVERAGE_BELOW_FLOOR_AFTER_START" and cell["failures"][0]["year"] == "2019"


def test_labels_cannot_be_built_without_gates_and_a_permit(small_world):
    counters = X.Counters()
    with pytest.raises(X.OrderingViolation, match="LABELS_REQUIRE_A_LABEL_PERMIT"):
        X.build_labels(object(), pd.DataFrame(), {}, W.DAYS, W.runtime(), {}, counters, 21)
    with pytest.raises(X.OrderingViolation, match="LABELS_REQUIRE_PASSED_PRE_LABEL_GATES"):
        X.issue_label_permit({"cells": {}}, file_guard(__file__), counters)
    assert counters.snapshot() == dict.fromkeys(X.Counters.NAMES, 0)
    counters.bump("targetFromSessionsCalls")
    with pytest.raises(X.OrderingViolation, match="OUTCOME_CALL_BEFORE_PERMIT"):
        X.issue_label_permit(X.GatesPassed({}), file_guard(__file__), counters)


def test_stopped_before_labels_is_derived_from_counters_not_asserted():
    counters = X.Counters()
    guard = file_guard(__file__)
    common = dict(spec=spec, spec_sha=SEAL, mode=X.FORMAL, runtime_spec=W.runtime(), guard=guard, phase="X",
                  provenance={"attempt": {}})
    assert X.build_result(counters=counters, **common)["ordering"]["stoppedBeforeLabels"] is True
    counters.bump("targetFromSessionsCalls", 3)
    ordering = X.build_result(counters=counters, **common)["ordering"]
    assert ordering["stoppedBeforeLabels"] is False and ordering["labelsBuilt"] is True


def test_identities_are_rechecked_immediately_before_the_first_label(leaky):
    checks = leaky["captured"]["checksAtFirstLabel"]
    assert checks[0] == "FROZEN" and checks[-1] == "IMMEDIATELY_BEFORE_FIRST_LABEL"
    assert leaky["result"]["identity"]["checks"][-1]["at"] == "END_OF_RUN"
    assert leaky["result"]["identity"]["unchangedThroughout"] is True


def test_counters_show_the_ordering_of_a_complete_run(leaky):
    counters = leaky["result"]["ordering"]["counters"]
    assert counters["targetFromSessionsCalls"] == counters["labelEligibilityCalls"] > 0
    assert counters["evaluateCalls"] == 2 and counters["fitCalls"] == counters["predictCalls"] > 0
    assert leaky["result"]["phaseReached"] == "COMPLETE"


# --------------------------------------------------------------------------- #
# Mid-run mutation: a same-run input swap fails
# --------------------------------------------------------------------------- #
def test_mutation_between_the_gates_and_the_labels_is_detected_before_any_label(small_world, monkeypatch, tmp_path):
    spy = install_spies(monkeypatch)
    watched = tmp_path / "frozen-input.bin"
    watched.write_bytes(b"frozen")
    guard = file_guard(watched)
    real_gates = X.pre_label_gates

    def gates_then_swap(*a, **k):
        passed = real_gates(*a, **k)
        watched.write_bytes(b"swapped after the gates passed")
        return passed

    monkeypatch.setattr(X, "pre_label_gates", gates_then_swap)
    result = W.run_world(small_world, guard=guard)
    assert_no_outcome_reached(result, spy)
    assert result["overallStatus"] == "INFRASTRUCTURE_ERROR" and result["error"]["code"] == "INPUT_IDENTITY_CHANGED"
    assert "IMMEDIATELY_BEFORE_FIRST_LABEL" in result["error"]["message"]
    assert result["identity"]["unchangedThroughout"] is False
    assert all(c["status"] == "INFRASTRUCTURE_ERROR" for c in result["claims"].values())
    assert result["substantiveResult"] is False


def test_mutation_after_evaluation_is_detected_at_the_end_of_the_run(small_world, monkeypatch, tmp_path):
    watched = tmp_path / "frozen-input.bin"
    watched.write_bytes(b"frozen")
    real_eval = X.evaluate_cell
    counter = {"n": 0}

    def eval_then_swap(*a, **k):
        counter["n"] += 1
        if counter["n"] == 2:
            watched.write_bytes(b"swapped during evaluation")
        return real_eval(*a, **k)

    monkeypatch.setattr(X, "evaluate_cell", eval_then_swap)
    result = W.run_world(small_world, guard=file_guard(watched))
    assert result["overallStatus"] == "INFRASTRUCTURE_ERROR" and result["error"]["code"] == "INPUT_IDENTITY_CHANGED"
    assert "END_OF_RUN" in result["error"]["message"] and result["substantiveResult"] is False


def write_shard(directory, name, records):
    with gzip.open(Path(directory) / name, "wt", encoding="utf-8") as stream:
        for record in records:
            stream.write(K.canonical_line(record) + "\n")


def synthetic_snapshot(tmp_path):
    directory = tmp_path / "merged"
    directory.mkdir()
    shards = {"dart-2020.jsonl.gz": [{"id": "a", "ticker": "1.KS", "v": 1}, {"id": "b", "ticker": "2.KS", "v": 2}],
              "dart-2021.jsonl.gz": [{"id": "c", "ticker": "1.KS", "v": 3}]}
    for name, records in shards.items():
        write_shard(directory, name, records)
    blobs = {p.name: K.git_blob_sha1(p.read_bytes()) for p in K.shard_files(directory)}
    pin = {"gitBlobSha1": blobs, "candidateIdentitySha256": K.candidate_identity(blobs),
           "snapshotContentSha256": K.content_sha256(shards), "recordCount": 3}
    return directory, pin


def test_accounting_snapshot_mutation_is_detected(tmp_path):
    directory, pin = synthetic_snapshot(tmp_path)
    assert X.verify_snapshot_dir(pin, directory)["recordCount"] == 3
    guard = X.IdentityGuard({"krAccountingSnapshot": lambda: X.verify_snapshot_dir(pin, directory)})
    guard.freeze()
    write_shard(directory, "dart-2021.jsonl.gz", [{"id": "c", "ticker": "1.KS", "v": 999}])
    with pytest.raises(ValueError, match="SNAPSHOT_SHARD_IDENTITY_CHANGED"):
        guard.assert_unchanged("IMMEDIATELY_BEFORE_FIRST_LABEL")


def test_accounting_snapshot_added_removed_or_recompressed_shards_are_refused(tmp_path):
    directory, pin = synthetic_snapshot(tmp_path)
    write_shard(directory, "dart-2022.jsonl.gz", [{"id": "z", "ticker": "9.KS"}])
    with pytest.raises(ValueError, match="SNAPSHOT_SHARD_IDENTITY_CHANGED"):
        X.verify_snapshot_dir(pin, directory)
    (directory / "dart-2022.jsonl.gz").unlink()
    (directory / "dart-2020.jsonl.gz").unlink()
    with pytest.raises(ValueError, match="SNAPSHOT_SHARD_IDENTITY_CHANGED"):
        X.verify_snapshot_dir(pin, directory)


def test_snapshot_pin_disagreements_are_refused(tmp_path):
    directory, pin = synthetic_snapshot(tmp_path)
    for key, message in (("candidateIdentitySha256", "SNAPSHOT_IDENTITY_CHANGED"),
                         ("snapshotContentSha256", "SNAPSHOT_CONTENT_CHANGED"),
                         ("recordCount", "SNAPSHOT_RECORD_COUNT_CHANGED")):
        wrong = dict(pin, **{key: "0" * 64 if key != "recordCount" else 4})
        with pytest.raises(ValueError, match=message):
            X.verify_snapshot_dir(wrong, directory)


def test_terminal_action_snapshot_mutation_is_detected(tmp_path):
    snapshot = {"foundationStatus": "PARTIALLY_REPAIRED",
                "securities": [{"code": "000030.KS", "completeness": {"exDateSemanticsResolved": "BLOCKED"}}]}
    path = tmp_path / "docs/foundation.json"
    path.parent.mkdir()
    path.write_text(json.dumps(snapshot))
    v4_stub = {"sourceFoundationCitation": {"krTerminalActionReconstructionV2": {"path": "docs/foundation.json"}}}
    frozen = ELIG.freeze_execution_snapshot(snapshot)
    guard = X.IdentityGuard({"terminalActionExecutionSnapshot": X.foundation_identity_fn(v4_stub, tmp_path, frozen)})
    guard.freeze()
    guard.assert_unchanged("MID_RUN")
    snapshot["securities"][0]["completeness"]["exDateSemanticsResolved"] = "READY"  # an "improvement" mid-run
    path.write_text(json.dumps(snapshot))
    with pytest.raises(ValueError):
        guard.assert_unchanged("IMMEDIATELY_BEFORE_FIRST_LABEL")


def synthetic_raw_inputs(tmp_path):
    root = tmp_path / "inputs"
    files = {"ledger/universe/kr/krx-universe-2013.jsonl.gz": b"universe-2013", "ledger/fundamentals/kr/shares.jsonl.gz": b"shares"}
    manifest = {"components": {}, "note": "synthetic"}
    manifest["sha256"] = digest(manifest)
    files[X.REPLAY_MANIFEST] = json.dumps(manifest).encode()
    blobs = {}
    for rel, data in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        blobs[rel] = X.git_blob_sha1(path)
    fake = {"inputs": {"sealedRaw": {"signalHistoryCommit": "0" * 40, "replayManifestSha256": manifest["sha256"],
                                     "gitBlobSha1": blobs}}}
    return root, fake


def test_raw_input_swap_extra_shard_and_manifest_change_are_refused(tmp_path):
    root, fake = synthetic_raw_inputs(tmp_path)
    assert X.verify_raw_inputs(fake, root)["blobsVerified"] == 3
    (root / "ledger/universe/kr/krx-universe-2014.jsonl.gz").write_bytes(b"extra")
    with pytest.raises(ValueError, match="UNSEALED_RAW_SHARD"):
        X.verify_raw_inputs(fake, root)
    (root / "ledger/universe/kr/krx-universe-2014.jsonl.gz").unlink()
    (root / "ledger/fundamentals/kr/shares.jsonl.gz").write_bytes(b"swapped")
    with pytest.raises(ValueError, match="INPUT_SNAPSHOT_CHANGED"):
        X.verify_raw_inputs(fake, root)
    with pytest.raises(ValueError, match="SIGNAL_HISTORY_COMMIT_MISMATCH"):
        X.verify_raw_inputs(fake, root, expected_signal_history_sha="1" * 40)


def test_replay_manifest_digest_mismatch_is_refused(tmp_path):
    root, fake = synthetic_raw_inputs(tmp_path)
    fake["inputs"]["sealedRaw"]["replayManifestSha256"] = "0" * 64
    with pytest.raises(ValueError, match="REPLAY_MANIFEST_CHANGED"):
        X.verify_raw_inputs(fake, root)


def test_guard_freezes_once_and_names_the_component_that_moved(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.write_text("1")
    b.write_text("1")
    guard = X.IdentityGuard({"alpha": lambda: sha(a), "beta": lambda: sha(b)})
    with pytest.raises(X.OrderingViolation):
        guard.assert_unchanged("BEFORE_FREEZE")
    guard.freeze()
    with pytest.raises(X.OrderingViolation, match="IDENTITY_ALREADY_FROZEN"):
        guard.freeze()
    b.write_text("2")
    with pytest.raises(X.InputIdentityChanged, match="beta"):
        guard.assert_unchanged("LATER")


# --------------------------------------------------------------------------- #
# Walk-forward
# --------------------------------------------------------------------------- #
def test_only_matured_past_labels_enter_training_and_the_purge_is_exact(leaky):
    fits = leaky["captured"]["fits"]
    assert fits
    checked_purge = 0
    for fit in fits:
        train, valid = fit["train"], fit["valid"]
        assert set(train.labelStatus) == {"MATURED"} and set(train.region) == {"KR"} and set(valid.region) == {"KR"}
        cutoff = pd.Timestamp(min(valid.date))
        assert pd.to_datetime(train.outcomeEndDate).max() < cutoff        # strictly before: no label ends ON the cutoff
        assert pd.to_datetime(train.date).max() < cutoff
        assert train.beatBenchmark.notna().all() and train.forwardRelativeReturn.notna().all()
    for horizon, modelling in leaky["captured"]["modelling"].items():
        for fit in (f for f in fits if f["kind"] == "ridge" and f["names"] == ["relative126"]
                    and f["valid"].horizon.iloc[0] == horizon):
            cutoff = pd.Timestamp(min(fit["valid"].date))
            started_before = modelling.loc[(pd.to_datetime(modelling.date) < cutoff)
                                           & (pd.to_datetime(modelling.outcomeEndDate) >= cutoff)]
            if len(started_before):
                keys = set(zip(fit["train"].date, fit["train"].ticker))
                assert not keys & set(zip(started_before.date, started_before.ticker))
                checked_purge += 1
    assert checked_purge > 0     # the purge actually had rows to refuse (H126 windows straddle every cutoff)


def test_purge_is_strictly_earlier_than_the_fold_cutoff():
    rows = []
    dates = [str(d.date()) for d in pd.date_range("2013-01-04", "2015-12-25", freq="7D")][:130]
    for date in dates + ["2015-12-24", "2015-12-31"]:
        end = {"2015-12-24": "2016-01-05", "2015-12-31": "2016-01-08"}.get(date, str((pd.Timestamp(date) + pd.Timedelta(days=15)).date()))
        for i in range(10):
            rows.append({"date": date, "region": "KR", "ticker": f"T{i:02d}", "outcomeEndDate": end,
                         "labelStatus": "MATURED", "beatBenchmarkNet": i % 2, "forwardRelativeReturn": 0.01 * (i - 4)})
    data = pd.DataFrame(rows).drop_duplicates(["date", "ticker"])
    folds = list(V1.folds(M.as_v1_target(data), ["2016-01-08"], W.runtime()))
    assert len(folds) == 1 and folds[0]["status"] == "READY"
    train_dates = set(folds[0]["train"].date)
    assert "2015-12-24" in train_dates          # matured on 2016-01-05, strictly before the cutoff
    assert "2015-12-31" not in train_dates      # its label ends ON the cutoff: not mature
    assert pd.to_datetime(folds[0]["train"].outcomeEndDate).max() < pd.Timestamp("2016-01-08")


def test_transforms_are_fitted_on_training_data_only(leaky):
    fit = next(f for f in leaky["captured"]["fits"] if f["kind"] == "ridge" and len(f["names"]) > 1)
    rt = W.runtime()
    base, _ = X._fit_predict("ridge", fit["train"], fit["valid"], fit["names"], rt)
    tampered = fit["valid"].copy()
    tampered.iloc[: len(tampered) // 2, tampered.columns.get_loc(fit["names"][0])] += 1e6
    other, _ = X._fit_predict("ridge", fit["train"], tampered, fit["names"], rt)
    half = len(tampered) // 2
    assert np.allclose(base[half:], other[half:], rtol=0, atol=1e-12)  # untouched rows are unaffected


def test_training_transformer_fit_never_receives_validation_rows(leaky, monkeypatch):
    seen = []
    real = V1.TrainTransformer.fit

    def spy(self, frame, weights):
        seen.append((set(zip(frame.date, frame.ticker)), len(weights)))
        return real(self, frame, weights)

    monkeypatch.setattr(V1.TrainTransformer, "fit", spy)
    fit = leaky["captured"]["fits"][0]
    X._fit_predict("ridge", fit["train"], fit["valid"], fit["names"], W.runtime())
    valid_keys = set(zip(fit["valid"].date, fit["valid"].ticker))
    assert seen and not (seen[0][0] & valid_keys)


def test_each_date_has_equal_total_influence_in_every_fit(leaky, monkeypatch):
    from sklearn.linear_model import Ridge
    captured = []
    real = Ridge.fit

    def spy(self, x, y, sample_weight=None):
        captured.append(sample_weight)
        return real(self, x, y, sample_weight=sample_weight)

    monkeypatch.setattr(Ridge, "fit", spy)
    fit = next(f for f in leaky["captured"]["fits"] if f["kind"] == "ridge")
    train = fit["train"].copy()
    train = pd.concat([train, train.loc[train.date.eq(train.date.iloc[0])].assign(ticker="EXTRA.KS")], ignore_index=True)
    X._fit_predict("ridge", train.sort_values(["date", "ticker"]).reset_index(drop=True), fit["valid"], fit["names"],
                   W.runtime())
    weights = np.asarray(captured[0])
    per_date = pd.Series(weights).groupby(train.sort_values(["date", "ticker"]).reset_index(drop=True).date).sum()
    assert np.allclose(per_date.to_numpy(), 1.0)


def test_us_data_cannot_enter_kr_training():
    train = pd.DataFrame({"date": ["2015-01-02"] * 3, "region": ["KR", "KR", "US"], "ticker": list("abc"),
                          "outcomeEndDate": "2015-02-01", "beatBenchmark": [1, 0, 1],
                          "forwardRelativeReturn": [0.1, -0.1, 0.2], "relative126": [0.0, 1.0, 2.0]})
    valid = train.assign(date="2016-01-08", region="KR").iloc[:2]
    with pytest.raises(ValueError, match="EMPTY_OR_MIXED_REGION"):
        X._fit_predict("ridge", train, valid, ["relative126"], W.runtime())
    with pytest.raises(ValueError, match="REGIONS_MUST_BE_SEPARATE"):
        list(V1.folds(train.assign(labelStatus="MATURED"), ["2016-01-08"], W.runtime()))
    assert spec["regions"] == ["KR"] and spec["blockedRegions"]["US"]["status"] == "BLOCKED_BY_DATA_INTEGRITY"


def test_us_rows_in_the_feature_frame_are_refused_not_silently_used(small_world):
    def add_us(frame):
        us = frame.iloc[:5].copy()
        us["region"] = "US"
        return pd.concat([frame, us], ignore_index=True)

    result = W.run_world(small_world, frame_mutator=add_us)
    assert result["overallStatus"] == "INFRASTRUCTURE_ERROR" and result["error"]["code"] == "ValueError"
    assert result["ordering"]["counters"]["targetFromSessionsCalls"] == 0


# --------------------------------------------------------------------------- #
# Models: fixed, no search, B4 primary, B5 cannot rescue
# --------------------------------------------------------------------------- #
def test_estimator_hyperparameters_are_the_frozen_ones_and_no_search_path_exists():
    rt = W.runtime()
    logistic, ridge = V1.estimator_pair("LINEAR", rt)
    classifier, hgb = V1.estimator_pair("SHALLOW_CHALLENGER", rt)
    assert ridge.alpha == 10.0 and ridge.solver == "lsqr" and logistic.C == 1.0 and logistic.penalty == "l2"
    assert hgb.max_leaf_nodes == 7 and hgb.max_iter == 100 and hgb.learning_rate == 0.05 and hgb.random_state == 42
    for path in ("pipeline/alpha_opportunity_v5_execution.py", "pipeline/alpha_opportunity_v5_evidence.py",
                 "scripts/execute_alpha_opportunity_model_v5.py"):
        code = (ROOT / path).read_text()
        for forbidden in ("GridSearchCV", "RandomizedSearchCV", "cross_val", "optuna", "hyperopt", "KFold",
                          "TimeSeriesSplit", "BayesSearch"):
            assert forbidden not in code, (path, forbidden)


def test_fit_predict_reproduces_the_sealed_v1_heads_exactly(leaky):
    rt = W.runtime()
    fit = next(f for f in leaky["captured"]["fits"] if f["kind"] == "ridge" and len(f["names"]) == 8)
    train, valid, names = fit["train"], fit["valid"], fit["names"]
    linear = M.fit_heads(train, valid, names, "LINEAR", rt)
    challenger = M.fit_heads(train, valid, names, "SHALLOW_CHALLENGER", rt)
    ridge, _ = X._fit_predict("ridge", train, valid, names, rt)
    logistic, _ = X._fit_predict("logistic", train, valid, names, rt)
    hgb, _ = X._fit_predict("hgb", train, valid, names, rt)
    assert np.array_equal(ridge, linear["expectedRelativeReturn"])
    assert np.array_equal(logistic, linear["probability"])
    assert np.array_equal(hgb, challenger["expectedRelativeReturn"])


def test_ladder_definitions_b0_to_b5(leaky):
    fits = leaky["captured"]["fits"]
    six = ["relative126", "acceleration21", "vol63", "logVolumeShock60", "shockPersistence5d", "volumePriceAlignment"]
    full = six + ["assetGrowthPct", "debtGrowthPct"]
    by_horizon = {h: [f for f in fits if f["valid"].horizon.iloc[0] == h] for h in (21, 126)}
    for horizon, group in by_horizon.items():
        first_year = min(f["valid"].date.min() for f in group)
        first = [f for f in group if f["valid"].date.min() == first_year]
        ridge_inputs = sorted(tuple(f["names"]) for f in first if f["kind"] == "ridge")
        b4 = tuple(six if horizon == 21 else full)
        expected = [("relative126",), b4] if horizon == 21 else sorted([("relative126",), tuple(six), b4])
        assert ridge_inputs == sorted(expected), horizon                    # B2 (+B3 at H126) and B4
        for f in first:
            if f["kind"] in ("hgb", "logistic"):
                assert tuple(f["names"]) == b4                                # B5 / Logistic use exactly B4's inputs
        assert {f["kind"] for f in first} == {"ridge", "hgb", "logistic"}
    # At H21 B3 and B4 are ONE predictor: exactly one six-feature Ridge fit per fold, never a duplicate.
    first_h21 = min(f["valid"].date.min() for f in by_horizon[21])
    assert sum(1 for f in by_horizon[21] if f["kind"] == "ridge" and f["names"] == six
               and f["valid"].date.min() == first_h21) == 1
    cells = {e["horizon"]: e["cell"] for e in leaky["captured"]["evaluations"]}
    assert cells[21]["rungs"]["b3Applicable"] is False and cells[126]["rungs"]["b3Applicable"] is True


def test_b1_b3_and_the_rung_columns_in_the_evaluation_tables(leaky):
    for entry in leaky["captured"]["evaluations"]:
        table = entry["table"]
        assert (table.pB1 == 0.0).all()
        assert table.groupby("foldYear").pB0.nunique().max() == 1            # one training mean per fold
        assert np.isfinite(table[["pB0", "pB2", "pB4"]].to_numpy(float)).all()
        assert entry["cell"]["rungs"]["B2"] == ["relative126"]
        if entry["horizon"] == 21:
            assert table.pB3.isna().all()                                    # no duplicate B3 at H21
        else:
            assert np.isfinite(table.pB3.to_numpy(float)).all()


def test_b0_is_the_training_date_weighted_mean_of_gross_relative_return(leaky):
    for fit in leaky["captured"]["fits"]:
        if fit["kind"] == "ridge" and fit["names"] == ["relative126"]:
            weights = V1.date_weights(fit["train"].date)
            expected = float(np.average(fit["train"].forwardRelativeReturn, weights=weights))
            table = next(e["table"] for e in leaky["captured"]["evaluations"]
                         if fit["valid"].date.min() in set(e["table"].date))
            got = table.loc[table.date.isin(set(fit["valid"].date)), "pB0"].iloc[0]
            assert got == pytest.approx(expected, abs=1e-15)
            return
    raise AssertionError("no B2 fit captured")


def test_b2_uses_only_relative126_and_b3_ignores_accounting_fields(leaky):
    rt = W.runtime()
    fits = leaky["captured"]["fits"]
    b2 = next(f for f in fits if f["names"] == ["relative126"])
    base, _ = X._fit_predict("ridge", b2["train"], b2["valid"], b2["names"], rt)
    train, valid = b2["train"].copy(), b2["valid"].copy()
    for column in ("acceleration21", "vol63", "assetGrowthPct", "debtGrowthPct"):
        train[column], valid[column] = 123.0, -5.0
    again, _ = X._fit_predict("ridge", train, valid, b2["names"], rt)
    assert np.array_equal(base, again)
    names = X.rung_names(rt, 126)
    assert names["B3"] == names["B4"][:6] and "assetGrowthPct" not in names["B3"] and names["b3Applicable"] is True
    assert X.rung_names(rt, 21)["b3Applicable"] is False


def test_b5_cannot_rescue_b4_and_descriptive_heads_never_gate(leaky):
    entry = next(e for e in leaky["captured"]["evaluations"] if e["horizon"] == 126)
    table, cell = entry["table"], entry["cell"]
    a, k = entry["args"]
    rt = W.runtime()
    rigged = table.assign(pB5=table.forwardRelativeReturn, prob=(table.forwardRelativeReturn > 0).astype(float))
    junk = table.assign(pB5=1e3, prob=np.nan)
    outs = []
    for variant in (rigged, junk):
        outs.append(X.evaluate_cell(variant, cell, 126, rt, *a, **k)[0])
    assert outs[0]["conjuncts"] == outs[1]["conjuncts"] and outs[0]["status"] == outs[1]["status"]
    assert outs[0]["descriptive"]["logisticHead"]["status"] == "MEASURED"
    assert outs[1]["descriptive"]["logisticHead"]["status"] == "UNAVAILABLE"
    assert set(EV.CONJUNCTS) == {"pairedMseImprovement_B4_vs_B0", "pairedMseImprovement_B4_vs_B2", "rankWeightedSpread_B4"}


def test_a_descriptive_head_failure_is_recorded_and_never_changes_the_claim(small_world, monkeypatch):
    real = X._fit_predict

    def flaky(kind, *a, **k):
        if kind in ("logistic", "hgb"):
            raise FloatingPointError("MODEL_UNSTABLE_NONFINITE")
        return real(kind, *a, **k)

    baseline = W.run_world(small_world)
    monkeypatch.setattr(X, "_fit_predict", flaky)
    degraded = W.run_world(small_world)
    assert degraded["overallStatus"] == baseline["overallStatus"] != "INFRASTRUCTURE_ERROR"
    for h in ("21", "126"):
        assert degraded["cells"][h]["conjuncts"] == baseline["cells"][h]["conjuncts"]
        assert degraded["cells"][h]["descriptiveModelFailures"]
        assert degraded["cells"][h]["descriptive"]["logisticHead"]["status"] == "UNAVAILABLE"


def test_a_primary_model_failure_is_an_infrastructure_error_not_a_verdict(small_world, monkeypatch):
    real = X._fit_predict

    def broken(kind, train, valid, names, rt):
        if kind == "ridge" and len(names) > 1:
            raise FloatingPointError("MODEL_UNSTABLE_NONFINITE")
        return real(kind, train, valid, names, rt)

    monkeypatch.setattr(X, "_fit_predict", broken)
    result = W.run_world(small_world)
    assert result["overallStatus"] == "INFRASTRUCTURE_ERROR" and result["error"]["code"] == "ModelFitFailure"
    assert all(c["status"] == "INFRASTRUCTURE_ERROR" for c in result["claims"].values())
    assert result["substantiveResult"] is False and result["closesPreregistration"] is False


# --------------------------------------------------------------------------- #
# Inference: the calibrated engine is reused; the statistics are the registered ones
# --------------------------------------------------------------------------- #
def test_calendar_time_attribution_equals_the_calibrated_engines_on_additive_data():
    rng = np.random.default_rng(3)
    weeks, names, step, horizon = 40, 6, 5, 21
    daily = rng.normal(size=((weeks - 1) * step + horizon, names))
    weights = rng.normal(size=(weeks, names))
    term = rng.normal(size=weeks)
    series, exposure = ENGINE.calendar_time_series(daily, weights, horizon, step, term)
    session_week = np.arange(daily.shape[0]) // step
    cohorts = [EV.Cohort(step * t, weights[t] @ daily[step * t:step * t + horizon].T, float(term[t]), t, True)
               for t in range(weeks)]
    d, x = EV.calendar_time_attribution(cohorts, session_week, horizon, len(series))
    assert np.allclose(d, series, rtol=0, atol=1e-12) and np.allclose(x, exposure, rtol=0, atol=1e-12)
    assert x.sum() == pytest.approx(weeks)


def test_undefined_dates_contribute_no_weight_term_or_exposure():
    weeks, horizon = 12, 5
    session_week = np.arange(weeks * horizon + horizon) // 5
    cohorts = [EV.Cohort(5 * t, np.ones(horizon), 1.0, t, t % 2 == 0) for t in range(weeks)]
    d, x = EV.calendar_time_attribution(cohorts, session_week, horizon, int(session_week.max()) + 1)
    assert x.sum() == pytest.approx(6.0) and d.sum() == pytest.approx(6 * (horizon + 1))


def test_compounded_increments_telescope_to_the_label_exactly_even_with_a_missing_interior_close():
    rng = np.random.default_rng(1)
    horizon = 21
    close = 100 * np.cumprod(1 + rng.normal(0, 0.02, horizon + 1))
    bench = 50 * np.cumprod(1 + rng.normal(0, 0.01, horizon + 1))
    label = (close[-1] / close[0] - 1) - (bench[-1] / bench[0] - 1)
    increments = EV.cohort_increments([close], bench, 0, horizon)
    assert increments.sum() == pytest.approx(label, abs=1e-12)
    gapped = close.copy()
    gapped[7:11] = np.nan
    again = EV.cohort_increments([gapped], bench, 0, horizon)
    assert again.sum() == pytest.approx(label, abs=1e-12) and (again[0, 6:10] == -np.diff(bench)[6:10] / bench[0]).all()
    broken = close.copy()
    broken[-1] = np.nan
    with pytest.raises(ValueError, match="ENDPOINT_MISSING"):
        EV.cohort_increments([broken], bench, 0, horizon)


def test_the_calibrated_engine_interval_function_is_the_one_called(leaky, monkeypatch):
    entry = next(e for e in leaky["captured"]["evaluations"] if e["horizon"] == 21)
    calls = []
    real = ENGINE.calendar_time_sn_interval

    def spy(series, exposure, critical, tolerance):
        calls.append((len(series), critical, tolerance))
        return real(series, exposure, critical, tolerance)

    monkeypatch.setattr(ENGINE, "calendar_time_sn_interval", spy)
    a, k = entry["args"]
    X.evaluate_cell(entry["table"], entry["cell"], 21, W.runtime(), *a, **k)
    assert len(calls) >= 9 and {c[1] for c in calls} == {66.57} and {c[2] for c in calls} == {1e-12}
    assert X.calibration_params(ROOT) == {"critical": 66.57, "tolerance": 1e-12}
    import inspect
    assert "calendar_time_sn_interval" in inspect.getsource(EV.calendar_interval)


def test_paired_mse_design_equals_the_direct_squared_error_difference():
    rng = np.random.default_rng(2)
    y, base, alt = rng.normal(size=30), rng.normal(size=30), rng.normal(size=30)
    design = EV.paired_mse_design(base, alt)
    assert design.weights @ y + design.signal_term == pytest.approx(np.mean((base - y) ** 2 - (alt - y) ** 2))


def test_rank_weighted_spread_weights_are_dollar_neutral_and_break_ties_by_ticker():
    tickers = np.array(list("edcba"))
    score = np.zeros(5)
    design = EV.rank_weighted_spread_design(score, tickers)
    assert design.weights.sum() == pytest.approx(0.0) and design.weights[design.weights > 0].sum() == pytest.approx(1.0)
    by_ticker = dict(zip(tickers, design.weights))
    assert by_ticker["a"] < by_ticker["b"] < by_ticker["c"] < by_ticker["d"] < by_ticker["e"]
    order = np.random.default_rng(0).permutation(5)
    again = EV.rank_weighted_spread_design(score[order], tickers[order])
    assert dict(zip(tickers[order], again.weights)) == by_ticker
    strong = EV.rank_weighted_spread_design(np.array([5.0, 1, 2, 4, 3]), np.array(list("abcde")))
    assert np.argmax(strong.weights) == 0 and np.argmin(strong.weights) == 1


def test_selected_set_uses_the_strict_cost_hurdle_and_empty_dates_are_undefined():
    chosen, mean, minus, x2 = EV.selected_designs(np.array([0.01, 0.005, -0.02, 0.0049]), 0.005, 4)
    assert chosen.tolist() == [True, False, False, False] and mean.defined and mean.signal_term == -0.005
    assert minus.weights.tolist() == [0.75, -0.25, -0.25, -0.25] and x2.signal_term == -0.01
    _, empty, _, _ = EV.selected_designs(np.array([0.001, -0.02]), 0.005, 2)
    assert empty.defined is False and not empty.weights.any()


def test_rank_ic_is_descriptive_only_and_cannot_move_a_claim(leaky):
    cell = leaky["result"]["cells"]["126"]
    assert cell["descriptive"]["rankIC"]["role"] == "DESCRIPTIVE_ONLY_NEVER_A_GATE"
    assert not any("rankIC" in name for name in EV.CONJUNCTS) and "rankIC" not in cell["conjuncts"]
    assert "DESCRIPTIVE ONLY" in spec["orderingStatistic"]["decision"]
    for states in ((EV.LOWER_ABOVE_ZERO,) * 3, (EV.CONTAINS_ZERO, EV.LOWER_ABOVE_ZERO, EV.LOWER_ABOVE_ZERO)):
        assert EV.claim_status(states) == (EV.PASS if EV.CONTAINS_ZERO not in states else EV.INCONCLUSIVE)


INTERVALS = [
    ({"lower": 0.0001, "upper": 1.0}, EV.LOWER_ABOVE_ZERO),
    ({"lower": 0.0, "upper": 1.0}, EV.CONTAINS_ZERO),
    ({"lower": -1.0, "upper": 0.0}, EV.CONTAINS_ZERO),
    ({"lower": -1.0, "upper": 1.0}, EV.CONTAINS_ZERO),
    ({"lower": -1.0, "upper": -1e-9}, EV.REFUTED),
    (None, EV.UNDEFINED), ({}, EV.UNDEFINED), ({"lower": None, "upper": 1.0}, EV.UNDEFINED),
    ({"lower": float("nan"), "upper": 1.0}, EV.UNDEFINED), ({"lower": -1.0, "upper": float("inf")}, EV.UNDEFINED),
]


@pytest.mark.parametrize("interval,state", INTERVALS)
def test_interval_state_boundaries(interval, state):
    assert EV.interval_state(interval) == state


def test_claim_status_boundaries_and_precedence():
    L, C, R, U = EV.LOWER_ABOVE_ZERO, EV.CONTAINS_ZERO, EV.REFUTED, EV.UNDEFINED
    assert EV.claim_status([L, L, L]) == EV.PASS
    assert EV.claim_status([L, C, L]) == EV.INCONCLUSIVE
    assert EV.claim_status([C, C, C]) == EV.INCONCLUSIVE
    assert EV.claim_status([L, L, R]) == EV.FAIL and EV.claim_status([C, R, L]) == EV.FAIL
    assert EV.claim_status([L, L, U]) == EV.DATA_INSUFFICIENT
    assert EV.claim_status([R, R, U]) == EV.DATA_INSUFFICIENT          # undefined outranks refuted within a claim
    assert EV.claim_status([L, L, L], data_insufficient_reason="DEPTH") == EV.DATA_INSUFFICIENT
    assert EV.claim_status([R, R, R], data_insufficient_reason="DEPTH") == EV.DATA_INSUFFICIENT
    assert EV.claim_status([R, R, R], infrastructure_reason="X") == EV.INFRASTRUCTURE_ERROR
    assert EV.claim_status([L, L]) == EV.DATA_INSUFFICIENT and EV.claim_status([]) == EV.DATA_INSUFFICIENT
    assert EV.CLAIM_PRECEDENCE == tuple(spec["claims"]["primary"]["precedenceWithinClaim"])


def test_overall_status_precedence_is_exhaustive_and_pass_needs_both_claims():
    order = ["INFRASTRUCTURE_ERROR", "FAIL", "INCONCLUSIVE", "DATA_INSUFFICIENT", "PASS"]
    for a in order:
        for b in order:
            expected = order[min(order.index(a), order.index(b))]
            assert EV.overall_status([a, b]) == expected, (a, b)
    assert EV.overall_status([EV.PASS, EV.PASS]) == EV.PASS and EV.overall_status([EV.PASS]) == EV.PASS
    assert EV.overall_status([EV.PASS, EV.DATA_INSUFFICIENT]) == EV.DATA_INSUFFICIENT
    assert EV.overall_status([]) == EV.DATA_INSUFFICIENT
    rule = spec["claims"]["overall"]["rule"]
    positions = [rule.index(label) for label in order]
    assert positions == sorted(positions) and EV.OVERALL_PRECEDENCE == tuple(order)


def test_confirmatory_depth_floor_boundary(leaky):
    entry = next(e for e in leaky["captured"]["evaluations"] if e["horizon"] == 126)
    a, k = entry["args"]
    n = entry["table"].date.nunique()
    at_floor = W.runtime(depth={"21": 30, "126": n})
    below = W.runtime(depth={"21": 30, "126": n + 1})
    ok, _ = X.evaluate_cell(entry["table"], entry["cell"], 126, at_floor, *a, **k)
    short, _ = X.evaluate_cell(entry["table"], entry["cell"], 126, below, *a, **k)
    assert ok["status"] != EV.DATA_INSUFFICIENT and ok["reason"] is None
    assert short["status"] == EV.DATA_INSUFFICIENT and short["reason"] == "SIGNAL_WEEKS_BELOW_CONFIRMATORY_FLOOR"
    assert short["signalWeeksRequired"] == n + 1 and short["economicTier"]["status"] == "NOT_EVALUATED"


def test_unready_later_fold_and_no_ready_fold_are_data_insufficient(leaky):
    entry = next(e for e in leaky["captured"]["evaluations"] if e["horizon"] == 21)
    a, k = entry["args"]
    cell = dict(entry["cell"], unreadyEvaluationFolds=[{"year": 2020, "status": "DATA_INSUFFICIENT_ONE_CLASS"}])
    out, _ = X.evaluate_cell(entry["table"], cell, 21, W.runtime(), *a, **k)
    assert out["status"] == EV.DATA_INSUFFICIENT and out["reason"] == "A_LATER_SCHEDULED_FOLD_IS_NOT_READY"
    out, _ = X.evaluate_cell(None, dict(entry["cell"], started=False), 21, W.runtime(), *a, **k)
    assert out["reason"] == "NO_READY_EVALUATION_FOLD" and out["status"] == EV.DATA_INSUFFICIENT


def test_economic_tier_is_conditional_and_uses_the_registered_requirements():
    good = {"lower": 0.001, "upper": 0.01}
    bad = {"lower": -0.001, "upper": 0.01}
    call = lambda claim=EV.PASS, sel=good, minus=good, n=60, halves=(0.01, 0.02): EV.economic_tier(  # noqa: E731
        claim, selected_minus_universe=minus, selected_mean=sel, selected_dates=n, half_estimates=list(halves))
    assert call()["status"] == "ECONOMIC_CANDIDATE_SUPPORTED"
    for claim in (EV.FAIL, EV.INCONCLUSIVE, EV.DATA_INSUFFICIENT, EV.INFRASTRUCTURE_ERROR):
        assert call(claim=claim)["status"] == "NOT_EVALUATED"
    assert call(n=52)["status"] == "ECONOMIC_CANDIDATE_SUPPORTED"
    assert call(n=51)["status"] == "DATA_INSUFFICIENT_SELECTED_DATES"
    assert call(sel=None)["status"] == "DATA_INSUFFICIENT_SELECTED_DATES"
    assert call(sel=bad)["status"] == "NOT_SUPPORTED" and call(minus=bad)["status"] == "NOT_SUPPORTED"
    assert call(halves=(0.01, -0.001))["status"] == "PERIOD_CONCENTRATED"
    assert call(halves=(0.01, 0.0))["status"] == "PERIOD_CONCENTRATED" and call(halves=(None, 0.01))["status"] == "PERIOD_CONCENTRATED"
    tier = call()
    assert tier["portfolioEvidence"] is False and "margin" in tier["limits"]
    assert not {"positions", "weights", "kellyFraction", "NAV", "orderNotional", "capacity"} & set(tier)
    assert EV.half_estimates([("2020-01-03", 1.0), ("2020-01-10", None), ("2020-01-17", 3.0), ("2020-01-24", -1.0)],
                             ["2020-01-03", "2020-01-10", "2020-01-17", "2020-01-24"]) == [1.0, 1.0]


def test_primary_claim_pass_path_and_null_path_on_synthetic_worlds(leaky):
    result = leaky["result"]
    assert result["overallStatus"] == "PASS" and result["substantiveResult"] is True
    assert all(c["status"] == "PASS" for c in result["claims"].values())
    for cell in result["cells"].values():
        assert set(cell["conjuncts"]) == set(EV.CONJUNCTS)
        assert all(v["interval"]["lower"] > 0 for v in cell["conjuncts"].values())
        assert cell["economicTier"]["status"] in EV.ECONOMIC_STATUSES
    assert result["cells"]["21"]["descriptive"]["contrasts"]["pairedMseImprovement_B4_vs_B3"]["status"] == "NOT_APPLICABLE"
    assert "pairedMseImprovement_B4_vs_B3" in result["cells"]["126"]["descriptive"]["contrasts"]
    null = W.run_world(W.make_world(seed=11, leak=False), mode=X.FORMAL)
    assert null["overallStatus"] in ("INCONCLUSIVE", "FAIL") and null["substantiveResult"] is True
    assert null["overallStatus"] != "PASS"


# --------------------------------------------------------------------------- #
# Determinism
# --------------------------------------------------------------------------- #
def test_identical_frozen_input_gives_byte_identical_results(leaky):
    first = X.finalize(leaky["result"])
    again = X.finalize(W.run_world(leaky["world"]))
    assert first == again
    assert json.loads(first)["resultDigests"]["substantiveResultSha256"] == X.substantive_digest(json.loads(first))


def test_input_row_and_panel_order_cannot_change_the_substantive_result(leaky):
    baseline = json.loads(X.finalize(leaky["result"]))
    shuffled = json.loads(X.finalize(W.run_world(leaky["world"], shuffle=True)))
    assert shuffled == baseline


def test_attempt_identity_is_provenance_and_outside_the_substantive_digest(leaky):
    one = json.loads(X.finalize(leaky["result"]))
    two = json.loads(X.finalize(W.run_world(leaky["world"], attempt="another-attempt")))
    assert one["provenance"]["attempt"] != two["provenance"]["attempt"]
    assert one["resultDigests"] == two["resultDigests"]


def test_result_artifact_is_complete_and_carries_no_portfolio_field(leaky):
    result = json.loads(X.finalize(leaky["result"]))
    for key in ("studyId", "specSha256", "overallStatus", "claims", "cells", "ordering", "identity", "preLabelGates",
                "foundation", "sample", "missingnessIntegrityDiagnostics", "provenance", "blockedRegions",
                "executionMode", "phaseReached", "substantiveResult", "promotionEligible"):
        assert key in result
    assert result["promotionEligible"] is False and result["blockedRegions"] == {"US": "BLOCKED_BY_DATA_INTEGRITY"}
    forbidden = set(spec["outputSchema"]["noPortfolioFields"]) | {"topN", "regionQuota", "capital", "notional"}

    def keys(node):
        if isinstance(node, dict):
            for k, v in node.items():
                yield k
                yield from keys(v)
        elif isinstance(node, list):
            for v in node:
                yield from keys(v)
    assert not forbidden & set(keys(result))
    assert result["sample"]["evaluation"]["21"]["signalWeeks"] > 0


def test_jsonable_removes_non_finite_and_numpy_types():
    out = X.jsonable({"a": np.float64("nan"), "b": np.int64(3), "c": np.array([1.0, np.inf]), "d": np.bool_(True)})
    assert out == {"a": None, "b": 3, "c": [1.0, None], "d": True}
    canonical(out)


# --------------------------------------------------------------------------- #
# Operator authorization and the CLI's own refusals
# --------------------------------------------------------------------------- #
def authorization(tmp_path, **override):
    identity = X.code_identity(ROOT)["harnessFiles"]
    record = {"studyId": "alpha-opportunity-model-v5", "specSha256": SEAL, "authorizedExecutions": 1,
              "authorizedBy": "operator", "harnessFiles": identity, "diagnosticSpecSha256": W.DIAG_SHA, **override}
    path = tmp_path / "authorization.json"
    path.write_text(json.dumps(record))
    return path, identity


def test_authorization_is_required_and_tied_to_spec_digest_and_harness_bytes(tmp_path):
    missing = tmp_path / "absent.json"
    none_committed = tmp_path / "no-committed-result.json"
    with pytest.raises(CLI.Refusal, match="AUTHORIZATION_MISSING"):
        CLI.verify_authorization(missing, spec_sha256=SEAL, harness_files={}, diagnostic_spec_sha256=W.DIAG_SHA,
                                 committed_result=none_committed)
    path, identity = authorization(tmp_path)
    assert CLI.verify_authorization(path, spec_sha256=SEAL, harness_files=identity, diagnostic_spec_sha256=W.DIAG_SHA,
                                    committed_result=none_committed)["authorizedExecutions"] == 1
    for override in ({"specSha256": "0" * 64}, {"authorizedExecutions": 2}, {"authorizedBy": " "},
                     {"studyId": "alpha-opportunity-model-v4"}, {"harnessFiles": {"x": "y"}},
                     {"diagnosticSpecSha256": "0" * 64}, {"diagnosticSpecSha256": None}):
        bad, _ = authorization(tmp_path, **override)
        with pytest.raises(CLI.Refusal, match="AUTHORIZATION_DOES_NOT_MATCH"):
            CLI.verify_authorization(bad, spec_sha256=SEAL, harness_files=identity, diagnostic_spec_sha256=W.DIAG_SHA,
                                     committed_result=none_committed)
    with pytest.raises(CLI.Refusal, match="AUTHORIZATION_DOES_NOT_MATCH"):
        CLI.verify_authorization(path, spec_sha256=SEAL, harness_files=dict(identity, extra="00"),
                                 diagnostic_spec_sha256=W.DIAG_SHA, committed_result=none_committed)


def test_a_committed_result_makes_the_run_one_shot(tmp_path):
    path, identity = authorization(tmp_path)
    committed = tmp_path / "alpha-opportunity-model-v5-result.json"
    committed.write_text("{}")
    with pytest.raises(CLI.Refusal, match="A_COMMITTED_V5_RESULT_ALREADY_EXISTS"):
        CLI.verify_authorization(path, spec_sha256=SEAL, harness_files=identity, diagnostic_spec_sha256=W.DIAG_SHA,
                                 committed_result=committed)


def test_formal_execution_is_refused_outside_actions_and_outside_main():
    with pytest.raises(CLI.Refusal, match="ONLY_FROM_THE_ACTIONS_WORKFLOW"):
        CLI.require_actions_main({})
    with pytest.raises(CLI.Refusal, match="ONLY_FROM_MAIN"):
        CLI.require_actions_main({"GITHUB_ACTIONS": "true", "GITHUB_REF": "refs/heads/feature"})
    CLI.require_actions_main({"GITHUB_ACTIONS": "true", "GITHUB_REF": "refs/heads/main"})


def test_execute_without_authorization_refuses_before_reading_any_input(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    spy = Spy()
    monkeypatch.setattr(X, "run_execution", spy.raising("run_execution"))
    monkeypatch.setattr(X, "freeze_foundation", spy.raising("freeze_foundation"))
    with pytest.raises(CLI.Refusal, match="AUTHORIZATION_MISSING"):
        CLI.main(["--sealed-sha256", SEAL, "--diagnostic-sha256", W.DIAG_SHA, "--input-root", str(tmp_path), "--output", str(tmp_path / "out"), "--authorization", str(tmp_path / "absent-authorization.json"), "--execute"])
    assert spy.calls == [] and not (tmp_path / "out").exists()


def test_execute_from_a_non_main_ref_is_refused_before_authorization_is_read(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_REF", "refs/heads/some-branch")
    with pytest.raises(CLI.Refusal, match="ONLY_FROM_MAIN"):
        CLI.main(["--sealed-sha256", SEAL, "--diagnostic-sha256", W.DIAG_SHA, "--input-root", str(tmp_path), "--output", str(tmp_path / "out"), "--execute"])


def test_a_wrong_sealed_digest_is_refused_before_anything_else(tmp_path):
    with pytest.raises(ValueError, match="SEALED_SPEC_CHANGED"):
        CLI.main(["--sealed-sha256", "0" * 64, "--diagnostic-sha256", W.DIAG_SHA, "--input-root", str(tmp_path), "--output", str(tmp_path / "o"), "--stop-before-labels"])


def test_print_code_identity_reads_nothing_but_the_harness_files(capsys):
    assert CLI.main(["--print-code-identity"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert set(printed["harnessFiles"]) == set(X.HARNESS_FILES) and all(len(v) == 64 for v in printed["harnessFiles"].values())
    assert printed["diagnosticSpecSha256"] == W.DIAG_SHA


def test_code_identity_records_the_full_import_closure_for_audit():
    identity = X.code_identity(ROOT)
    assert "pipeline/alpha_opportunity_v4_eligibility.py" in identity["importClosure"]
    assert "pipeline/alpha_inference_calibration_v4.py" in identity["importClosure"]
    assert set(X.HARNESS_FILES) <= set(identity["importClosure"])


def test_output_must_be_new_and_outside_the_repository(tmp_path):
    for target in (ROOT / "docs/results/x-out", tmp_path):
        with pytest.raises(CLI.Refusal, match="OUTPUT_MUST_BE_NEW_AND_OUTSIDE_THE_REPOSITORY"):
            CLI.execute(type("A", (), {"execute": False, "spec": S5.DEFAULT_SPEC, "sealed_sha256": SEAL,
                                       "output": target, "authorization": None,
                                       "diagnostic_sha256": W.DIAG_SHA})())


def materialize_sealed_raw_inputs(target):
    sealed = spec["inputs"]["sealedRaw"]
    commit = sealed["signalHistoryCommit"]
    needed = (spec["inputs"]["krAccounting"]["sourceCommit"], commit)
    if not all(subprocess.run(["git", "cat-file", "-e", c], cwd=ROOT, capture_output=True).returncode == 0
               for c in needed):
        if os.environ.get("CI"):
            pytest.fail("pinned commits are not fetched in CI")
        pytest.skip("pinned commits not present locally")
    for rel in sealed["gitBlobSha1"]:
        path = Path(target) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(subprocess.check_output(["git", "show", f"{commit}:{rel}"], cwd=ROOT))
    return Path(target)


def test_freeze_only_on_the_real_sealed_identities_reads_no_outcome(tmp_path, capsys, monkeypatch):
    root = materialize_sealed_raw_inputs(tmp_path / "inputs")
    spy = install_spies(monkeypatch)
    assert CLI.main(["--sealed-sha256", SEAL, "--diagnostic-sha256", W.DIAG_SHA, "--input-root", str(root), "--freeze-only"]) == 0
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["outcomeAccess"] == "NONE" and spy.calls == []
    assert set(out["frozenIdentity"]) == {"spec", "sealedClosureAndPriors", "krAccountingSnapshot", "sealedRawInputs",
                                          "calibratedInference", "terminalActionExecutionSnapshot", "harnessCode", "diagnosticSpec"}
    assert out["frozenIdentity"]["krAccountingSnapshot"]["snapshotContentSha256"] == K.FROZEN_CONTENT_SHA256
    assert out["frozenIdentity"]["sealedRawInputs"]["blobsVerified"] == 16
    assert out["foundation"]["foundationStatusAtExecution"] == "PARTIALLY_REPAIRED"


def test_freeze_only_refuses_a_swapped_real_raw_input(tmp_path):
    root = materialize_sealed_raw_inputs(tmp_path / "inputs")
    (root / "ledger/fundamentals/kr/shares.jsonl.gz").write_bytes(b"swapped")
    with pytest.raises(ValueError, match="INPUT_SNAPSHOT_CHANGED"):
        CLI.main(["--sealed-sha256", SEAL, "--diagnostic-sha256", W.DIAG_SHA, "--input-root", str(root), "--freeze-only"])


# --------------------------------------------------------------------------- #
# Workflow (parsed with regexes: PyYAML is not a declared dependency)
# --------------------------------------------------------------------------- #
WORKFLOW = (ROOT / ".github/workflows/alpha-opportunity-model-v5-execution.yml").read_text()


def steps():
    parts = re.split(r"^      - ", WORKFLOW.split("    steps:\n", 1)[1], flags=re.M)
    return [p for p in parts if p.strip()]


def step_named(fragment):
    return next(s for s in steps() if fragment in s)


def test_workflow_is_dispatch_only_main_only_and_keeps_the_frozen_digest():
    triggers = re.search(r"^on:\n((?:  .*\n|\n)+)", WORKFLOW, re.M).group(1)
    assert "workflow_dispatch" in triggers and "pull_request" not in triggers and "schedule" not in triggers
    assert re.search(r"^permissions:\n  contents: read\n  actions: read\n", WORKFLOW, re.M)
    assert "pull_request_target" not in WORKFLOW and "secrets." not in WORKFLOW
    assert "github.ref != 'refs/heads/main'" in step_named("Refuse any ref other than main")
    assert re.search(r"SEALED_SHA256: ([0-9a-f]{64})", WORKFLOW).group(1) == SEAL
    assert re.search(r"options: \[verify, gates-only, execute\]", WORKFLOW)


def test_verify_mode_never_enters_historical_execution():
    verify = step_named("Verify every frozen identity")
    assert "run_alpha_opportunity_model_v5.py" in verify and "--verify-only" in verify and "execute_alpha" not in verify
    assert "if:" not in verify.split("run:")[0]          # verify runs in every mode, before anything else
    for step in steps():
        if "execute_alpha_opportunity_model_v5.py" in step:
            assert re.search(r"if: inputs\.mode == '(gates-only|execute)'", step)
            assert "inputs.mode == 'verify'" not in step
    text_before_inputs = WORKFLOW.split("    steps:\n", 1)[1].split("uses: actions/checkout@v5\n        if: inputs.mode != 'verify'")[0]
    assert "execute_alpha_opportunity_model_v5.py" not in text_before_inputs
    assert "if: inputs.mode != 'verify'" in WORKFLOW


def test_gates_only_mode_uses_stop_before_labels_and_never_the_formal_flag():
    step = step_named("Pre-label gates on the sealed inputs")
    assert "inputs.mode == 'gates-only'" in step and "--stop-before-labels" in step and "--execute" not in step
    assert "authorization" not in step


def test_execute_mode_requires_authorization_and_the_one_shot_guard_before_running():
    gate = step_named("Execution gate")
    assert "inputs.mode == 'execute'" in gate and "authorization.json" in gate
    assert "alpha-opportunity-model-v5-result" in gate and "expired==false" in gate and "one-shot" in gate
    execute = step_named("Execute the frozen v5 protocol")
    assert "inputs.mode == 'execute'" in execute and "--execute" in execute and "execute_alpha_opportunity_model_v5.py" in execute
    assert WORKFLOW.index("Execution gate") < WORKFLOW.index("Execute the frozen v5 protocol")
    assert WORKFLOW.index("Synthetic contract tests") < WORKFLOW.index("Execute the frozen v5 protocol")


def test_verdict_artifacts_close_the_guard_and_attempt_artifacts_do_not():
    text = WORKFLOW
    assert "name: alpha-opportunity-model-v5-result\n" in text
    assert "steps.classify.outputs.substantive == 'true'" in text and "steps.classify.outputs.substantive != 'true'" in text
    assert re.search(r"name: alpha-opportunity-model-v5-attempt-\$\{\{ github\.run_id \}\}", text)
    assert "INFRASTRUCTURE_ERROR" in step_named("Fail the job only when the machinery failed")
    assert "gates-only-${{ github.run_id }}" in text          # a dry run can never masquerade as the result


def test_no_authorization_file_or_result_is_created_by_the_workflow_or_docs():
    assert "git add" not in WORKFLOW and "git commit" not in WORKFLOW and "git push" not in WORKFLOW
