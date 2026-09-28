import json
from pathlib import Path

import numpy as np

from pipeline.alpha_inference_calibration_v1 import (
    _bootstrap_means,
    _bootstrap_plan,
    simulate_null_date_statistics,
)
from pipeline.alpha_opportunity_model import block_sample_indices


SPEC_PATH = Path("research_specs/alpha-inference-calibration-v1.json")


def _spec():
    return json.loads(SPEC_PATH.read_text())


def test_frozen_protocol_has_review_candidate_grid_and_no_real_data_inputs():
    spec = _spec()
    assert spec["outcomeFree"] is True
    assert spec["bootstrapDraws"] == 10_000
    assert spec["horizons"]["21"]["candidateBlocks"] == [5, 10]
    assert spec["horizons"]["21"]["primaryBlock"] == 10
    assert spec["horizons"]["126"]["candidateBlocks"] == [26, 52, 104]
    assert spec["horizons"]["126"]["primaryBlock"] == 52
    assert spec["confidence"]["tailQuantile"] == 0.0125
    serialized = json.dumps(spec).lower()
    for forbidden in ("signal-history", "forwardreturn", "historical outcome"):
        assert forbidden not in serialized or forbidden in json.dumps(spec["prohibitions"]).lower()


def test_synthetic_date_statistics_are_deterministic_and_finite():
    spec = _spec()
    dgp = spec["dgps"][1]
    a = simulate_null_date_statistics(spec, dgp, horizon=21, weeks=20, replicate=7, dgp_index=1)
    b = simulate_null_date_statistics(spec, dgp, horizon=21, weeks=20, replicate=7, dgp_index=1)
    assert set(a) == set(spec["statistics"])
    for key in a:
        assert np.array_equal(a[key], b[key])
        assert len(a[key]) == 20
        assert np.isfinite(a[key]).all()


def test_fast_bootstrap_means_match_repository_block_sampling_exactly():
    n, block, draws = 17, 5, 11
    series = np.linspace(-3.0, 4.0, n)
    seed_parts = [123, 456]
    starts, final_length = _bootstrap_plan(n, block, draws, seed_parts)
    fast = _bootstrap_means(series, starts, block, final_length)

    rng = np.random.default_rng(np.random.SeedSequence(seed_parts))
    slow = []
    for _ in range(draws):
        indices = block_sample_indices(n, block, rng)
        slow.append(series[indices].mean())
    assert np.allclose(fast, slow)


def test_depth_contract_marks_104_week_sensitivity_unusable_on_312_weeks():
    spec = _spec()
    minimum = spec["minimumEffectiveBlocks"]
    assert 312 // 52 >= minimum
    assert 312 // 104 < minimum
    assert 624 // 104 >= minimum
