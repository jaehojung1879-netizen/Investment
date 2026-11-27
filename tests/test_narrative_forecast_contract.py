"""Synthetic checks only; never claim forward skill from these tests."""
from copy import deepcopy

import pytest

from research.narrative_intelligence import forecast_contract as fc


def payload():
    return {
        "id": "synthetic-1", "model": "SYNTHETIC_TEST", "as_of": "2026-11-28T00:00:00Z",
        "target_end": "2027-06-30T00:00:00Z", "target": "synthetic GDP", "unit": "percent",
        "kind": "POINT", "prediction": 2.4, "baseline": 2.0, "baseline_source": "baseline",
        "evidence": [{"id": "baseline", "available_at": "2026-11-27T00:00:00Z"}],
        "resolution": {"source": "synthetic", "vintage": "first", "definition": "test"},
        "mechanism": "test mechanism", "alternative": "test counterexample",
        "missing_policy": "UNRESOLVED_NO_IMPUTATION",
    }


def outcome(value=2.5):
    return {"synthetic": True, "forecast_id": "synthetic-1", "target": "synthetic GDP",
            "unit": "percent", "source": "synthetic", "vintage": "first",
            "available_at": "2027-07-30T00:00:00Z", "value": value}


def test_point_score_against_same_target():
    result = fc.score_synthetic(fc.candidate_receipt(payload()), outcome())
    assert result["model_loss"] == pytest.approx(.1)
    assert result["baseline_loss"] == pytest.approx(.5)
    assert result["improvement"] == pytest.approx(.4)


def test_probability_brier():
    p = payload()
    p.update(kind="BINARY_PROBABILITY", prediction=.7, baseline=.5)
    result = fc.score_synthetic(fc.candidate_receipt(p), outcome(1))
    assert result["metric"] == "BRIER"
    assert result["model_loss"] == pytest.approx(.09)


def test_missing_not_zero():
    result = fc.score_synthetic(fc.candidate_receipt(payload()), outcome(None))
    assert result["status"] == "UNRESOLVED"
    assert result["model_loss"] is None


def test_mutation_detected():
    receipt = fc.candidate_receipt(deepcopy(payload()))
    receipt["payload"]["prediction"] = 2.9
    with pytest.raises(ValueError, match="FORECAST_HASH"):
        fc.score_synthetic(receipt, outcome())


def test_future_evidence_rejected():
    p = payload()
    p["evidence"][0]["available_at"] = "2026-11-29T00:00:00Z"
    with pytest.raises(ValueError, match="FUTURE_EVIDENCE"):
        fc.candidate_receipt(p)


def test_no_fake_baseline():
    p = payload()
    p["baseline_source"] = "missing"
    with pytest.raises(ValueError, match="BASELINE_EVIDENCE_REQUIRED"):
        fc.candidate_receipt(p)


@pytest.mark.parametrize("field,value,reason", [
    ("unit", "basis points", "UNMATCHED_TARGET"),
    ("vintage", "revised", "UNMATCHED_RESOLUTION"),
    ("available_at", "2027-01-01T00:00:00Z", "PREMATURE_RESOLUTION"),
    ("synthetic", False, "SYNTHETIC_ONLY"),
])
def test_bad_resolution(field, value, reason):
    a = outcome()
    a[field] = value
    with pytest.raises(ValueError, match=reason):
        fc.score_synthetic(fc.candidate_receipt(payload()), a)
