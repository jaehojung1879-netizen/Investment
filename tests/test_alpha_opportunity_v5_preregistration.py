"""alpha-opportunity-model-v5 preregistration: seals, inheritance, pins, decisions, gates.
Reads no label, score, return or outcome artifact."""
import builtins
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

import numpy as np
import pytest

from pipeline import alpha_inference_calibration_v4 as CAL4
from pipeline import alpha_opportunity_v5_spec as S
from pipeline import kr_repaired_accounting_snapshot as K
from scripts import run_alpha_opportunity_model_v5 as RUN

ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "research_specs/alpha-opportunity-model-v5.json"
SEAL = (ROOT / "research_specs/alpha-opportunity-model-v5.sha256").read_text().strip()
spec = S.read_json(SPEC_PATH)
v4 = S.read_json(ROOT / "research_specs/alpha-opportunity-model-v4.json")
v3 = S.read_json(ROOT / "research_specs/alpha-opportunity-model-v3.json")
cal5 = S.read_json(ROOT / "research_specs/alpha-inference-calibration-v5.json")


def test_the_sealed_spec_loads_and_any_change_is_refused(tmp_path):
    assert S.load_sealed(expected_hash=SEAL)["studyId"] == "alpha-opportunity-model-v5"
    with pytest.raises(ValueError, match="UNSEALED_SPEC"):
        S.load_sealed(expected_hash="x")
    altered = copy.deepcopy(spec)
    altered["claims"]["primary"]["name"] = "SOMETHING_ELSE"
    p = tmp_path / "alpha-opportunity-model-v5.json"
    p.write_text(json.dumps(altered))
    (tmp_path / "alpha-opportunity-model-v5.sha256").write_text(SEAL)
    with pytest.raises(ValueError, match="SEALED_SPEC_CHANGED"):
        S.load_sealed(p, expected_hash=SEAL)


def _reseal(tmp_path, mutate):
    altered = copy.deepcopy(spec)
    mutate(altered)
    p = tmp_path / "alpha-opportunity-model-v5.json"
    p.write_text(json.dumps(altered))
    digest = S.digest(S.read_json(p))
    (tmp_path / "alpha-opportunity-model-v5.sha256").write_text(digest)
    return p, digest


@pytest.mark.parametrize("mutate,message", [
    (lambda s: s.__setitem__("regions", ["US", "KR"]), "UNSUPPORTED_CONTRACT"),
    (lambda s: s.__setitem__("fixedTopN", 5), "FORBIDDEN_DECISION_PARAMETER"),
    (lambda s: s["inherited"]["models"]["value"]["ridge"].__setitem__("alpha", 1.0), "INHERITED_VALUE_CHANGED"),
    (lambda s: s["inputs"]["krAccounting"].__setitem__("snapshotContentSha256", "0" * 64), "SNAPSHOT_CONTENT_HASH_CHANGED"),
    (lambda s: s["inference"]["calibration"].__setitem__("U1CriticalValue", 50.0), "CALIBRATED_CONTRACT_DISAGREES"),
    (lambda s: s["dependencyHashes"].__setitem__("pipeline/kr_repaired_accounting_snapshot.py", "0" * 64), "SEALED_DEPENDENCY_CHANGED"),
])
def test_resealed_tampering_is_still_refused(tmp_path, mutate, message):
    p, digest = _reseal(tmp_path, mutate)
    with pytest.raises(ValueError, match=message):
        S.load_sealed(p, expected_hash=digest)


def test_inherited_values_equal_the_sealed_v4_and_v1_to_v4_seals_are_unchanged():
    for name, entry in spec["inherited"].items():
        node = v4
        for part in entry["sourcePointer"].split("."):
            node = node[part]
        assert node == entry["value"] and S.digest(node) == entry["valueSha256"], name
    for record in spec["priorVersions"]:
        path = ROOT / "research_specs" / f"{record['studyId']}.json"
        assert S.digest(S.read_json(path)) == path.with_suffix(".sha256").read_text().strip() == record["specSha256"]


def test_models_targets_and_horizons_are_the_frozen_design():
    models = spec["inherited"]["models"]["value"]
    assert models["ridge"]["alpha"] == 10.0 and models["logistic"]["C"] == 1.0 and models["search"] is False
    assert models["histGradientBoosting"]["max_leaf_nodes"] == 7 and models["histGradientBoosting"]["early_stopping"] is False
    assert spec["horizons"] == [21, 126] and spec["benchmarks"] == {"KR": "069500.KS"}
    assert "next regional exchange session CLOSE" in spec["inherited"]["targets"]["value"]["entry"]
    assert spec["dataCutoff"] == "2026-09-14"


def test_regions_are_separate_us_is_blocked_and_never_substituted():
    assert spec["regions"] == ["KR"] and spec["modelIds"] == {"KR": "KR_OPPORTUNITY_MODEL_V5"}
    us = spec["blockedRegions"]["US"]
    assert us["status"] == "BLOCKED_BY_DATA_INTEGRITY" and "never pooled" in us["rule"] and "region feature" in us["rule"]
    assert us["notSubstituted"].startswith("No other US dataset")
    assert not any("us" == k.lower() for k in spec["inputs"])


def test_features_only_shrink_and_nothing_is_added():
    registry = spec["modifiedFromV4"]["features"]["KR"]
    old = v4["carriedFromV3"]["allowedFeatures"]["KR"]
    assert registry["21"] == old["21"]
    assert set(registry["126"]) < set(old["126"]) and set(old["126"]) - set(registry["126"]) == {"ocfToNetIncomePct"}
    assert "ocfToNetIncomePct" not in registry["126"]


def test_rank_weighted_spread_is_confirmatory_and_rank_ic_descriptive_and_calibrated():
    pin = spec["inference"]["calibration"]
    assert "rankWeightedSpread" in pin["confirmatoryStatistics"] and pin["descriptiveStatistics"] == ["rankIC"]
    assert cal5["statistics"]["confirmatory"] == pin["confirmatoryStatistics"]
    ordering = spec["orderingStatistic"]
    assert ordering["status"] == "EXPLICIT_PRE_OUTCOME_REVISION" and "rankIC" in ordering["decision"]
    assert "DESCRIPTIVE ONLY" in ordering["decision"] and "before any historical label" in ordering["chronology"]
    assert any("rankWeightedSpread" in c for c in spec["claims"]["primary"]["conjuncts"])
    assert not any("rankIC" in c for c in spec["claims"]["primary"]["conjuncts"])


def test_rank_weights_are_dollar_neutral_with_a_unit_long_leg():
    score = np.random.default_rng(1).normal(size=(6, 40))
    w = CAL4._centred_rank_weights(score)
    assert np.allclose(w.sum(axis=1), 0.0) and np.allclose(np.where(w > 0, w, 0).sum(axis=1), 1.0)


def test_claims_multiplicity_depth_and_status_semantics():
    conf = spec["inference"]["confidence"]
    assert conf["primaryClaims"] == 2 and conf["claimTwoSidedAlpha"] == 0.025 == 0.05 / 2 and conf["nominalCoverage"] == 0.975
    depth = spec["inference"]["minimumConfirmatoryDepth"]
    assert depth["21"]["signalWeeks"] == 78 and depth["126"]["signalWeeks"] == 312
    assert cal5["intervalConstruction"]["U1CriticalValue"] == spec["inference"]["calibration"]["U1CriticalValue"] == 66.57
    status = spec["claims"]["primary"]["status"]
    assert set(status) == {"PASS", "FAIL", "INCONCLUSIVE", "DATA_INSUFFICIENT", "INFRASTRUCTURE_ERROR"}
    assert len(spec["claims"]["primary"]["conjuncts"]) == 3 and spec["claims"]["economicCandidate"]["evaluatedOnlyIf"].startswith("the primary claim is PASS")
    assert "bootstrap" not in json.dumps(spec["inference"]["calibration"]).lower().replace("moving-block bootstrap", "")


def test_snapshot_and_raw_input_pins():
    pin = spec["inputs"]["krAccounting"]
    assert pin["snapshotContentSha256"] == "e0199d98679357f405de9a95a4091045db814d65af61e2c698af1a70d54fda58" == K.FROZEN_CONTENT_SHA256
    assert pin["candidateIdentitySha256"] == K.CANDIDATE_SHA256 and pin["recordCount"] == 9351 and pin["rebuildOrAlter"].startswith("FORBIDDEN")
    raw = spec["inputs"]["sealedRaw"]
    assert raw["signalHistoryCommit"] == v3["futureExecutionInputs"]["signalHistoryCommit"] and len(raw["gitBlobSha1"]) == 16
    for rel, sha in raw["gitBlobSha1"].items():
        assert v3["futureExecutionInputs"]["gitBlobSha1"][rel] == sha
        assert not rel.startswith("ledger/fundamentals/kr/dart-")


def test_data_backed_verification_against_the_pinned_git_objects():
    needed = (spec["inputs"]["krAccounting"]["sourceCommit"], spec["inputs"]["sealedRaw"]["signalHistoryCommit"])
    have = all(subprocess.run(["git", "cat-file", "-e", c], cwd=ROOT, capture_output=True).returncode == 0 for c in needed)
    if not have:
        if os.environ.get("CI"):
            pytest.fail("pinned commits are not fetched in CI")
        pytest.skip("pinned commits not present locally")
    assert RUN.verify_snapshot_from_git(spec)["regenerationByteIdentical"] is True
    assert RUN.verify_raw_inputs_from_git(spec)["blobsVerified"] == 16


def test_runner_verifies_and_refuses_to_execute(capsys):
    assert RUN.main(["--sealed-sha256", SEAL, "--verify-only"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["outcomeAccess"] == "NONE" and report["sealedIdentity"] == "VERIFIED"
    with pytest.raises(RuntimeError, match="NO_V5_EXECUTION_HARNESS_IN_THIS_PR"):
        RUN.main(["--sealed-sha256", SEAL, "--execute"])
    with pytest.raises(ValueError, match="SEALED_SPEC_CHANGED"):
        RUN.main(["--sealed-sha256", "0" * 64, "--verify-only"])


def test_no_execution_harness_result_or_authorization_exists_in_this_change():
    assert spec["executionHarness"]["status"] == "NOT_BUILT_IN_THIS_PR"
    assert not [p for p in spec["dependencyHashes"] if "v5_execution" in p or "execute_alpha_opportunity_model_v5" in p]


def test_loading_and_verifying_opens_no_outcome_or_result_artifact(monkeypatch):
    seen = []
    real = builtins.open

    def spy(path, *a, **k):
        seen.append(str(path))
        return real(path, *a, **k)

    monkeypatch.setattr(builtins, "open", spy)
    S.load_sealed(expected_hash=SEAL)
    forbidden = ("execution-report", "defective", "region-year-mismatch", "calibration-v4-report",
                 "development-diagnostics", "ledger/historical", "outcome")
    assert not [p for p in seen if any(f in p for f in forbidden)]


def test_code_reads_no_outcome_module():
    for name in ("pipeline/alpha_opportunity_v5_spec.py", "scripts/run_alpha_opportunity_model_v5.py"):
        code = (ROOT / name).read_text()
        for forbidden in ("kelly_portfolio", "portfolio_validation", "replay_valuation", "historical_outcomes",
                          "alpha_opportunity_v2_evaluation", "alpha_opportunity_v2_model", "alpha_opportunity_v4_execution"):
            assert forbidden not in code, (name, forbidden)


def test_workflow_is_main_only_dispatch_only_read_only_and_pinned():
    text = (ROOT / ".github/workflows/alpha-opportunity-model-v5-execution.yml").read_text()
    triggers = re.search(r"^on:\n((?:  .*\n|\n)+)", text, re.M).group(1)
    assert "workflow_dispatch" in triggers and "pull_request" not in triggers and "schedule" not in triggers
    assert re.search(r"^permissions:\n  contents: read\n  actions: read\n", text, re.M)
    assert "pull_request_target" not in text and "secrets." not in text
    assert "github.ref != 'refs/heads/main'" in text
    assert re.search(r"SEALED_SHA256: ([0-9a-f]{64})", text).group(1) == SEAL
    assert "--verify-snapshot-from-git" in text and "--verify-raw-inputs-from-git" in text
    assert "authorization.json" in text and "alpha-opportunity-model-v5-result" in text
    # The reviewed harness (a later change) adds steps after the execute step (classification, artifact upload,
    # the fail-only-on-infrastructure-error step), so the execute step is no longer the LAST step; it must still
    # exist, be gated on execute mode, and be the only step that passes --execute.
    execute_steps = [step for step in text.split("      - name:")[1:] if "--execute" in step]
    assert len(execute_steps) == 1 and "inputs.mode == 'execute'" in execute_steps[0]


def test_calibration_and_snapshot_inputs_are_unchanged():
    assert hashlib.sha256((ROOT / "research_specs/alpha-inference-calibration-v5.json").read_bytes()).hexdigest() == \
        "b32e1fad5f06ad61e11fb80801b8ba833f1b26d1a3a95233e48395d50a6bf5cc"
    assert hashlib.sha256((ROOT / "research_specs/alpha-inference-calibration-v4.json").read_bytes()).hexdigest() == \
        "012e43177b8e8ec7143eff30d7280c4cf8015b32b464bcddd87c09f75c984a5d"
    assert spec["inference"]["calibration"]["formalResult"]["primaryStatus"] == "PASS"
    assert spec["inference"]["calibration"]["formalResult"]["cells"] == 24
