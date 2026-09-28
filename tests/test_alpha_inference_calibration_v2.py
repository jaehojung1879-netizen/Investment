import json
from pathlib import Path
import subprocess
import sys

import numpy as np

from pipeline.alpha_inference_calibration_v2 import (
    _basic_interval,
    _circular_bootstrap_means,
    _circular_bootstrap_plan,
)


V1_SPEC_PATH = Path("research_specs/alpha-inference-calibration-v1.json")
V2_SPEC_PATH = Path("research_specs/alpha-inference-calibration-v2.json")


def _spec(path: Path):
    return json.loads(path.read_text())


def test_v2_changes_only_registered_interval_mechanics_and_seed():
    v1 = _spec(V1_SPEC_PATH)
    v2 = _spec(V2_SPEC_PATH)
    for key in (
        "simulationReplicates",
        "bootstrapDraws",
        "namesPerDate",
        "signalStepSessions",
        "minimumEffectiveBlocks",
        "confidence",
        "horizons",
        "dgps",
        "nullConstruction",
        "statistics",
        "selectionFraction",
        "syntheticForecastScale",
        "acceptance",
    ):
        assert v2[key] == v1[key]
    assert v2["seed"] != v1["seed"]
    assert v2["intervalConstruction"]["resampler"] == "CIRCULAR_MOVING_BLOCK_BOOTSTRAP"
    assert v2["intervalConstruction"]["interval"] == "BASIC_CENTERED_ERROR"
    assert v2["v1FailureReference"]["primaryStatus"] == "FAIL"


def test_v2_protocol_forbids_real_outcome_inputs_and_sensitivity_promotion():
    spec = _spec(V2_SPEC_PATH)
    assert spec["outcomeFree"] is True
    assert spec["horizons"]["21"]["primaryBlock"] == 10
    assert spec["horizons"]["126"]["primaryBlock"] == 52
    prohibitions = " ".join(spec["prohibitions"]).lower()
    assert "historical return" in prohibitions
    assert "v1 sensitivity" in prohibitions
    assert "may not select" in prohibitions


def test_circular_bootstrap_means_match_explicit_wrapped_indices():
    n, block, draws = 17, 5, 11
    series = np.linspace(-3.0, 4.0, n)
    starts, final_length = _circular_bootstrap_plan(n, block, draws, [123, 456])
    fast = _circular_bootstrap_means(series, starts, block, final_length)

    slow = []
    for row in starts:
        indices = []
        for start in row:
            indices.extend(((int(start) + np.arange(block)) % n).tolist())
        slow.append(series[np.asarray(indices[:n], dtype=int)].mean())
    assert np.allclose(fast, slow)


def test_circular_blocks_wrap_across_the_end_without_endpoint_loss():
    series = np.arange(6, dtype=float)
    starts = np.asarray([[5, 4]], dtype=np.int32)
    observed = _circular_bootstrap_means(series, starts, block=4, final_length=2)
    expected_indices = np.asarray([5, 0, 1, 2, 4, 5])
    assert np.allclose(observed, [series[expected_indices].mean()])


def test_basic_interval_uses_centered_bootstrap_errors_exactly():
    series = np.asarray([-2.0, -1.0, 0.5, 1.0, 3.0, 4.0])
    starts = np.asarray([[0, 2], [1, 3], [4, 5], [5, 1]], dtype=np.int32)
    block = 4
    final_length = 2
    tail = 0.25
    interval = _basic_interval(series, starts, block, final_length, tail)
    assert interval is not None

    estimate = series.mean()
    draws = _circular_bootstrap_means(series, starts, block, final_length)
    errors = draws - estimate
    q_lo, q_hi = np.quantile(errors, [tail, 1.0 - tail])
    assert np.isclose(interval["estimate"], estimate)
    assert np.isclose(interval["lower"], estimate - q_hi)
    assert np.isclose(interval["upper"], estimate - q_lo)


def test_depth_contract_is_unchanged_from_v1():
    spec = _spec(V2_SPEC_PATH)
    minimum = spec["minimumEffectiveBlocks"]
    assert 78 // 10 >= minimum
    assert 312 // 52 >= minimum
    assert 312 // 104 < minimum
    assert 624 // 104 >= minimum


def test_v2_runner_can_be_invoked_directly_from_repo_root():
    completed = subprocess.run(
        [sys.executable, "scripts/run_alpha_inference_calibration_v2.py", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "Frozen synthetic-only v2 calibration protocol" in completed.stdout
