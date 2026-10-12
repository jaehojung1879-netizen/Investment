"""US H63 inference calibration v1: the harness's mechanics and the committed result's consistency.

Pinned here: the residualised gross-2 weights are neutral to every sector and control rank; the calendar-time attribution
identity holds with missing names and unresolved terminal events; an unresolved terminal event voids exactly the cohorts that
held the name across it; replicates are reproducible from their seed key alone; the 90% Lobato critical value is the tabulated
one; the module reads no file and imports nothing that touches market data; and the committed result follows its frozen rule.
"""
from __future__ import annotations

import ast
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import alpha_inference_mc_decision as mc        # noqa: E402
from pipeline import us_h63_inference_calibration as U        # noqa: E402

PROTOCOL_PATH = ROOT / "docs/us-readiness/us-h63-inference-calibration-v1-protocol.json"
RESULT_PATH = ROOT / "docs/us-readiness/us-h63-inference-calibration-v1-result.json"
PROTOCOL = json.loads(PROTOCOL_PATH.read_text())
FROZEN_SHA = "8bb72a8a083125e6506dfeca82eb1def1607b443afab2dc96233b54f7cbcf1ba"


def small(name="BASE", **overrides):
    geometry, dgp = U.resolve_dgp(PROTOCOL, next(d for d in PROTOCOL["dgps"] if d["name"] == name))
    geometry = {**geometry, "universe": overrides.pop("universe", 60)}
    return geometry, {**dgp, **overrides}


def test_protocol_is_frozen_and_unchanged():
    assert hashlib.sha256(PROTOCOL_PATH.read_bytes()).hexdigest() == FROZEN_SHA
    assert PROTOCOL["status"] == "FROZEN_BEFORE_ANY_REPLICATE" and PROTOCOL["outcomeFree"] is True
    assert PROTOCOL["inferentialTarget"]["alpha"] == 0.05 and PROTOCOL["methods"]["primaryCandidate"] == "CT_SN"


def test_residual_weights_are_gross_two_and_neutral_to_sectors_and_controls():
    rng = np.random.default_rng(1)
    n = 80
    sectors = np.repeat(np.arange(4), 20)
    available = rng.random(n) > 0.1
    feature = U.centred_ranks(rng.standard_normal(n), available)
    controls = np.column_stack([U.centred_ranks(rng.standard_normal(n), available) for _ in range(4)])
    w = U.residual_weights(feature, controls, sectors, available)
    assert np.abs(w).sum() == pytest.approx(2.0)
    assert np.all(w[~available] == 0.0)
    for k in range(4):
        assert w[(sectors == k) & available].sum() == pytest.approx(0.0, abs=1e-12)
    assert np.abs(controls[available].T @ w[available]).max() < 1e-12


def test_centred_ranks_and_sector_assignment():
    ranks = U.centred_ranks(np.array([3.0, 1.0, 2.0, 9.0]), np.array([True, True, True, False]))
    assert ranks.tolist() == pytest.approx([1 / 3, -1 / 3, 0.0, 0.0])
    sectors = U.sector_assignment(330, PROTOCOL["geometry"]["sectorShares"])
    assert len(sectors) == 330 and sectors.max() == len(PROTOCOL["geometry"]["sectorShares"]) - 1


def test_innovation_correlation_reproduces_the_stationary_target():
    target = np.array(PROTOCOL["geometry"]["characteristicCorrelation"])
    phi = np.array([PROTOCOL["geometry"]["weeklyPersistence"][c] for c in U.CHARACTERISTICS])
    inner = U.innovation_correlation(target, phi)
    a = np.sqrt(1 - phi**2)
    stationary = inner * np.outer(a, a) / (1 - np.outer(phi, phi))
    np.fill_diagonal(stationary, 1.0)
    assert stationary == pytest.approx(target)


def test_replicates_are_reproducible_from_their_seed_key_alone():
    geometry, dgp = small()
    a = U.replicate_intervals(geometry, dgp, weeks=30, seed_key=(7, 1), methods_cfg=PROTOCOL["methods"])
    b = U.replicate_intervals(geometry, dgp, weeks=30, seed_key=(7, 1), methods_cfg=PROTOCOL["methods"])
    c = U.replicate_intervals(geometry, dgp, weeks=30, seed_key=(7, 2), methods_cfg=PROTOCOL["methods"])
    assert a == b and a != c


def test_attribution_identity_holds_with_missing_names_and_terminal_events():
    geometry, dgp = small(missingRate=0.3, unresolvedTerminalPerYear=6.0)
    record = U.replicate_intervals(geometry, dgp, weeks=40, seed_key=(3,), methods_cfg=PROTOCOL["methods"])
    assert record["_definedFraction"] < 1.0          # raises ATTRIBUTION_IDENTITY_BROKEN inside if the identity failed


def test_an_unresolved_terminal_event_voids_exactly_the_cohorts_that_held_the_name():
    geometry, dgp = small(missingRate=0.0, unresolvedTerminalPerYear=0.0)
    assert U.simulate(geometry, dgp, weeks=40, seed_key=(5,))["defined"].all()
    geometry, dgp = small(missingRate=0.1, unresolvedTerminalPerYear=3.0)
    sim = U.simulate(geometry, dgp, weeks=40, seed_key=(5,))
    ends, available = sim["aliveUntil"], sim["available"]
    sessions = (40 - 1) * U.STEP + U.HORIZON
    assert (ends < sessions).any()
    for t in range(40):
        window = (ends >= t * U.STEP) & (ends < t * U.STEP + U.HORIZON)
        assert sim["defined"][t] == (not (window & available[t]).any())
        assert not available[t][ends <= t * U.STEP].any()          # a terminated name never enters a later cohort


def test_synthetic_effect_moves_the_estimand_by_about_the_stated_amount():
    geometry, dgp = small(universe=120)
    record = U.replicate_intervals(geometry, dgp, weeks=60, seed_key=(11,), methods_cfg=PROTOCOL["methods"], effect_annual=0.04)
    per_h63 = 0.04 * U.HORIZON / 252.0
    assert 0.5 * per_h63 < record["_effectTheta"] <= per_h63 * 1.0001


def test_lobato_90_percent_critical_value_matches_the_table():
    assert PROTOCOL["methods"]["snCriticalValue"] == 28.31
    assert U.lobato_u1_quantile(0.90, 20000, 400, 3) == pytest.approx(28.31, abs=2.0)


def test_decide_counts_errors_on_the_correct_sides():
    records = [{"CT_SN": {"lower": 0.1, "upper": 0.3}}] * 5 + [{"CT_SN": {"lower": -0.1, "upper": 0.1}}] * 95
    out = U.decide(records, "CT_SN", 0.0, PROTOCOL["acceptance"], PROTOCOL["monteCarloDecision"], 60)
    assert out["estimates"]["lowerBoundError"] == 0.05 and out["estimates"]["upperBoundError"] == 0.0
    assert out["estimates"]["coverage90"] == 0.95 and out["estimates"]["undefinedFrequency"] == 0.0


def test_module_reads_no_file_and_imports_nothing_that_touches_market_data():
    source = (ROOT / "pipeline/us_h63_inference_calibration.py").read_text()
    tree = ast.parse(source)
    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imported |= {(n.module or "") for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    allowed = {"__future__", "math", "typing", "numpy", "scipy.signal", "scipy.stats", "pipeline",
               "pipeline.alpha_inference_calibration_v3", "pipeline.alpha_inference_calibration_v4"}
    assert imported <= allowed, imported - allowed
    assert "open(" not in source and "read_text" not in source and "Path(" not in source


# --------------------------------------------------------------------------- #
# Committed result
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def result():
    if not RESULT_PATH.exists():
        pytest.skip("formal result not committed")
    return json.loads(RESULT_PATH.read_text())


def test_result_is_the_formal_run_of_the_frozen_protocol(result):
    assert result["protocolSha256"] == FROZEN_SHA and result["developmentOnly"] is False
    assert result["replicates"] == PROTOCOL["replicates"] and result["powerReplicates"] == PROTOCOL["power"]["replicates"]
    assert result["readsRealData"] is False and result["evidenceClass"] == "SYNTHETIC_INFERENCE_CALIBRATION_NOT_INVESTMENT_PERFORMANCE"


def test_p3_status_follows_the_frozen_rule(result):
    required = [c for c in result["cells"] if c["gating"] and c["weeks"] in (260, 700)]
    assert len(required) == 10
    expected = "PASS" if all(c["primaryState"] == mc.PASS for c in required) else "BLOCKED"
    assert result["p3Status"] == expected
    for cell in result["cells"]:
        assert cell["primaryState"] == cell["methods"][U.PRIMARY_METHOD]["state"]


def test_phase3_protocol_records_the_calibration_outcome(result):
    proposal = json.loads((ROOT / "docs/us-readiness/us-cash-profitability-study-protocol-v1.json").read_text())
    p3 = {p["id"]: p for p in proposal["prerequisitesBeforeRegistration"]}["P3_US_INFERENCE_CALIBRATION"]
    assert p3["calibrationResult"]["p3Status"] == result["p3Status"]
    assert proposal["registered"] is False and proposal["authorizes"] == "NOTHING"
