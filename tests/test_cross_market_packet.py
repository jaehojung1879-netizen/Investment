"""A complete readiness table cannot silently grant a historical execution."""
from copy import deepcopy

from research.cross_market_foundation_v1.audit import validate_readiness


def matrix_fixture(tmp_path):
    (tmp_path / "source.json").write_text("{}")
    return {"historicalOutcomeExecuted": False, "executionAuthorized": False, "cells": [
        {"region": region, "layer": layer, "scope": "synthetic input contract only",
         "status": "SOURCE_BLOCKED", "newOutcomeRunnable": False,
         "availableWithoutOutcome": ["source identity verification"],
         "blockers": [{"code": "MISSING_PIT_DATA", "priority": "P0", "evidence": ["source.json"],
                       "recoveryCondition": "retain dated source payload, identity, and rights evidence"}]}
        for region in ("KR", "US") for layer in ("Market", "Industry", "Stock", "Portfolio")]}


def test_readiness_cannot_omit_a_market_or_repeat_one_cell(tmp_path):
    matrix = matrix_fixture(tmp_path)
    assert validate_readiness(matrix, tmp_path) == []
    matrix["cells"][-1] = deepcopy(matrix["cells"][0])
    assert "EIGHT_UNIQUE_MARKET_LAYER_CELLS_REQUIRED" in validate_readiness(matrix, tmp_path)


def test_sources_not_permission_and_blockers_must_have_evidence(tmp_path):
    matrix = matrix_fixture(tmp_path)
    matrix["executionAuthorized"] = True
    matrix["cells"][0]["newOutcomeRunnable"] = True
    matrix["cells"][0]["blockers"][0]["recoveryCondition"] = ""
    matrix["cells"][0]["blockers"][0]["evidence"] = ["missing.json"]
    errors = validate_readiness(matrix, tmp_path)
    assert "SPRINT_OUTCOME_BOUNDARY_VIOLATED" in errors
    assert any(e.startswith("NO_SPRINT_OUTCOME_EXECUTION_PERMISSION:") for e in errors)
    assert any(e.startswith("UNVERIFIABLE_BLOCKER:") for e in errors)
    assert any(e.startswith("BLOCKER_EVIDENCE_UNAVAILABLE:") for e in errors)


def test_blocked_sources_cannot_be_relabelled_ready(tmp_path):
    matrix = matrix_fixture(tmp_path)
    matrix["cells"][0]["status"] = "READY"
    assert any(e.startswith("READY_WITH_UNRESOLVED_BLOCKER:") for e in validate_readiness(matrix, tmp_path))
