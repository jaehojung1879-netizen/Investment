from copy import deepcopy

import pytest

from research.master_integration_preflight_v1 import adapters as A
from test_master_integration_receipt import inputs


def test_metadata_identity_adapter_does_not_promote_or_mutate():
    observation, arms = inputs()
    original = deepcopy((observation, arms))
    value = A.adapt_synthetic_inputs(observation, arms)
    assert value == observation and (observation, arms) == original
    assert A.contract_reference()["status"] == "PREPARED"
    assert A.contract_reference()["scientificAdmission"] is False


@pytest.mark.parametrize("key", A.IDENTITIES)
def test_cross_arm_common_inputs_cannot_diverge(key):
    observation, arms = inputs()
    arms[3][key] = "different"
    with pytest.raises(ValueError, match="CROSS_ARM"):
        A.adapt_synthetic_inputs(observation, arms)


@pytest.mark.parametrize("field,value,code", [
    ("raw", b"changed", "SOURCE_BYTES"),
    ("sha256", "0" * 64, "SOURCE_BYTES"),
    ("sourceCommit", "main", "SOURCE_COMMIT"),
    ("rightsStatus", "PUBLIC_URL_ACCESSIBLE", "RIGHTS"),
    ("pitStatus", "CURRENT_BACKFILLED", "PIT"),
    ("availableAtUtc", "2026-11-01T00:00:00Z", "CUTOFF"),
    ("vintageAtUtc", "2026-11-01T00:00:00Z", "CUTOFF"),
])
def test_revision_rights_and_pit_are_not_admission(field,value,code):
    observation, arms = inputs()
    observation["sourceEvidence"][0][field] = value
    with pytest.raises(ValueError, match=code):
        A.adapt_synthetic_inputs(observation, arms)


def test_invalid_score_and_missing_qualification_refused():
    observation, arms = inputs()
    observation["stockQualification"]["S1"] = "ADMITTED"
    with pytest.raises(ValueError, match="ADMISSION"):
        A.adapt_synthetic_inputs(observation, arms)
    del observation["stockQualification"]["S1"]
    with pytest.raises(ValueError, match="ADMISSION"):
        A.adapt_synthetic_inputs(observation, arms)


@pytest.mark.parametrize("field", ["weights","positions","scores","nav","performance","forwardReturn"])
def test_no_action_or_result_payload(field):
    observation, arms = inputs()
    observation[field] = {"SYN_A": 1}
    with pytest.raises(ValueError):
        A.adapt_synthetic_inputs(observation, arms)


def foundation_plan():
    common = {"universe": ["SYN_A"], "costModel": {"fixture": "synthetic-only"},
              "executionPolicySha256": "a" * 64}
    common["costPolicySha256"] = A.digest(common["costModel"])
    plan = {"contract":"hierarchical-vs-direct-selection-comparison-v1", "schemaVersion":1,
            "executionEnabled":False,"deployable":False,"common":common,"commonSha256":A.digest(common),
            "paths":[{"path":p,"universe":common["universe"],"commonSha256":A.digest(common),
                      "weights":{"SYN_A":1}} for p in A.ARMS]}
    plan["planSha256"] = A.digest(plan)
    return plan


def test_foundation_identity_projection_refuses_engine_conversion():
    value = A.adapt_foundation_plan(foundation_plan())
    assert value["status"] == "INCOMPATIBLE"
    assert value["receiptPreparationAllowed"] is False
    assert len(value["blockers"]) == 3
    assert "weights" not in str(value) and "SYN_A" not in str(value)


def test_foundation_tamper_or_missing_arm_refused():
    plan = foundation_plan()
    plan["common"]["universe"] = ["SYN_CHANGED"]
    with pytest.raises(ValueError,match="DIGEST"):
        A.adapt_foundation_plan(plan)
    plan = foundation_plan()
    plan["paths"].pop()
    plan["planSha256"] = A.digest({k:v for k,v in plan.items() if k != "planSha256"})
    with pytest.raises(ValueError,match="SIX_UNIQUE"):
        A.adapt_foundation_plan(plan)


def test_contract_pin_not_source_licence_or_edited_spec():
    with pytest.raises(ValueError,match="CONTRACT_BYTES"):
        A.verify_contract_bytes(b'{"studyId":"portfolio-d-p0-p5-comparison-v1"}')


def test_operational_codec_is_reused_without_emitting_its_targets():
    import hashlib
    from pipeline import weekly_decision as W
    row = W.build_receipt({"region":"KR","asOfDate":"2026-10-30","holdings":[],"weights":{"069500.KS":1}},
                          generated_at="2026-10-30T10:00:00Z",inputs={},evidence={},week_status="FINAL_WEEKLY")
    raw = W.canonical(row)
    view = A.inspect_operational_receipt(raw,expected_sha256=hashlib.sha256(raw).hexdigest())
    assert view["digest"] == W.receipt_digest(row) and view["activationEnabled"] is False
    assert "holdings" not in str(view) and "weights" not in str(view)
    with pytest.raises(ValueError,match="BYTES"):
        A.inspect_operational_receipt(raw+b" ",expected_sha256=hashlib.sha256(raw).hexdigest())
    row["weekStatus"]="INTRA_WEEK_PREVIEW"
    row["digest"]=W.receipt_digest(row)
    raw=W.canonical(row)
    with pytest.raises(ValueError,match="FINAL"):
        A.inspect_operational_receipt(raw,expected_sha256=hashlib.sha256(raw).hexdigest())
