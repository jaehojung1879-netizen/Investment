"""Report interpretation preserves stage evidence under the frozen benchmark gate.

All numbers below are invented decision fixtures, not historical outcomes.
"""

from copy import deepcopy
import json
import re

import pytest

from pipeline.kr_alpha_atlas_phase_c import contract, executor


def test_documented_result_paths_exist_in_frozen_schema():
    """The five-layer interpretation table must point to actual schema fields."""
    document = (contract.ROOT / "docs/kr-alpha-atlas-phase-c-interpretation-ko.md").read_text()
    schema = json.loads((contract.ROOT / contract.RESULT_SCHEMA).read_text())
    rows = [line for line in document.splitlines() if re.match(r"\| [1-5]\. ", line)]
    assert len(rows) == 5

    def resolve(node):
        while "$ref" in node:
            target = schema
            for key in node["$ref"].removeprefix("#/").split("/"):
                target = target[key]
            node = target
        return node

    def walk(node, parts):
        if not parts:
            return
        node = resolve(node)
        key, *rest = parts
        if key.startswith("{") and key.endswith("}"):
            if isinstance(node.get("additionalProperties"), dict):
                children = [node["additionalProperties"]]
            else:
                children = list(node.get("properties", {}).values())
            assert children, f"No registered keyed objects for {key}"
            for child in children:
                walk(child, rest)
        else:
            if key in node.get("properties", {}):
                child = node["properties"][key]
            else:
                assert key in node.get("required", []) and not rest, f"Undocumented schema path: {parts}"
                child = {}
            walk(child, rest)

    for row in rows:
        paths = re.findall(r"`([^`]+)`", row.split("|")[2])
        assert paths
        for path in paths:
            walk(schema, path.split("."))


@pytest.mark.parametrize(
    "net_excess,selection,expected",
    [(0.02, 0.01, "BLOCKED"), (-0.01, 0.01, "NOT_ECONOMIC"), (0.02, -0.01, "NOT_ECONOMIC")],
)
def test_positive_development_evidence_survives_blocked_nomination(net_excess, selection, expected):
    spec = contract.load()
    # Deliberately decisive, invented stage readings: no labels, fitting or p-value calculation.
    reading = {
        "statistics": {
            "tercileSpread": {
                "inferenceStatus": "DEVELOPMENT_ASYMPTOTIC_SN",
                "estimate": 0.04,
                "interval": {"lower": 0.01},
            }
        },
        "adjustedP": 0.01,
        "stability": {"stable": True},
    }
    paired_statistic = {
        "inferenceStatus": "DEVELOPMENT_ASYMPTOTIC_SN",
        "estimate": 0.01,
        "nDates": 104,
        "evaluableShare": 1.0,
    }
    comparison = {
        "pairedMseImprovement": deepcopy(paired_statistic),
        "pairedRankWeightedSpreadImprovement": deepcopy(paired_statistic),
        "identicalPredictionsOnCommonSample": False,
        "identicalEvaluationPopulation": True,
        "commonObservations": 104 * 30,
        "adjustedP": 0.01,
        "positive": True,
    }
    residual = {"residualized": {"statistics": {"tercileSpread": deepcopy(paired_statistic)}}}
    policy = {
        "status": "DEVELOPMENT_DIAGNOSTIC",
        "claimStatus": spec["benchmarkIntegrity"]["claimGate"],
        "netExcess": net_excess,
        "arithmeticAttribution": {"C_stockSelection": selection},
    }
    economic = {
        "policies": {"SLOTS_CASH": deepcopy(policy), "SLOTS_PASSIVE_BENCHMARK": deepcopy(policy)},
        "benchmarkClaimStatus": spec["benchmarkIntegrity"]["claimGate"],
    }
    preserved = deepcopy((reading, comparison, residual, economic))
    assert economic["benchmarkClaimStatus"] == "BLOCKED_UNVERIFIED"
    assert executor.earlier_verdict(reading, comparison, residual) is None
    assert executor.economic_verdict(economic) == expected
    # A final blocker or adverse economic reading must leave earlier positive evidence intact.
    assert (reading, comparison, residual, economic) == preserved
