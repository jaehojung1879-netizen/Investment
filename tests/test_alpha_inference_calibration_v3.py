import json
from pathlib import Path
import subprocess
import sys

import numpy as np

from pipeline.alpha_inference_calibration_v3 import _self_normalized_interval


V2_SPEC_PATH = Path("research_specs/alpha-inference-calibration-v2.json")
V3_SPEC_PATH = Path("research_specs/alpha-inference-calibration-v3.json")


def _spec(path: Path):
    return json.loads(path.read_text())


def test_v3_preserves_v2_synthetic_null_contract_except_interval_and_seed():
    v2 = _spec(V2_SPEC_PATH)
    v3 = _spec(V3_SPEC_PATH)
    for key in (
        "simulationReplicates",
        "namesPerDate",
        "signalStepSessions",
        "dgps",
        "nullConstruction",
        "statistics",
        "selectionFraction",
        "syntheticForecastScale",
    ):
        assert v3[key] == v2[key]
    for key in (
        "familywiseAlpha",
        "primaryExpectedReturnClaims",
        "cellTwoSidedAlpha",
        "nominalCoverage",
    ):
        assert v3["confidence"][key] == v2["confidence"][key]
    assert "tailQuantile" not in v3["confidence"]
    for key in (
        "materialCoverageFloor",
        "directionalFalsePositiveCeiling",
        "undefinedFrequencyCeiling",
        "maximumMonteCarlo95HalfWidth",
    ):
        assert v3["acceptance"][key] == v2["acceptance"][key]
    for horizon in ("21", "126"):
        assert v3["horizons"][horizon]["forwardSessions"] == v2["horizons"][horizon]["forwardSessions"]
        assert v3["horizons"][horizon]["calendarWeeks"] == v2["horizons"][horizon]["calendarWeeks"]
    assert v3["seed"] != v2["seed"]
    assert v3["intervalConstruction"]["method"] == "SELF_NORMALIZED_FIXED_B_BARTLETT_B1"
    assert v3["intervalConstruction"]["blockLength"] == "NONE"
    assert v3["intervalConstruction"]["bootstrapDraws"] == 0
    assert v3["v2FailureReference"]["primaryStatus"] == "FAIL"


def test_self_normalizer_matches_manual_prefix_formula_exactly():
    series = np.asarray([-2.0, -1.0, 0.5, 1.0, 3.0, 4.0])
    critical = 66.57
    interval = _self_normalized_interval(series, critical)
    assert interval is not None

    n = len(series)
    prefix = np.cumsum(series)
    t = np.arange(1, n + 1, dtype=float)
    centered = prefix - (t / n) * prefix[-1]
    w_n = np.sum(centered**2) / n**2
    estimate = series.mean()
    half = np.sqrt(critical * w_n / n)

    assert np.isclose(interval["selfNormalizer"], w_n)
    assert np.isclose(interval["estimate"], estimate)
    assert np.isclose(interval["lower"], estimate - half)
    assert np.isclose(interval["upper"], estimate + half)
    assert np.isclose(interval["width"], 2 * half)


def test_self_normalized_interval_is_location_and_scale_equivariant():
    series = np.asarray([-1.5, 0.2, 1.0, 2.4, -0.7, 3.1, 0.8])
    critical = 66.57
    base = _self_normalized_interval(series, critical)
    moved = _self_normalized_interval(3.0 + 2.5 * series, critical)
    assert base is not None and moved is not None
    assert np.isclose(moved["estimate"], 3.0 + 2.5 * base["estimate"])
    assert np.isclose(moved["width"], 2.5 * base["width"])
    assert np.isclose(moved["lower"], 3.0 + 2.5 * base["lower"])
    assert np.isclose(moved["upper"], 3.0 + 2.5 * base["upper"])


def test_zero_self_normalizer_is_undefined_not_false_certainty():
    interval = _self_normalized_interval(np.ones(20), 66.57)
    assert interval is None


def test_v3_protocol_uses_published_pivotal_value_and_has_no_block_selection():
    spec = _spec(V3_SPEC_PATH)
    cfg = spec["intervalConstruction"]
    assert cfg["criticalPercentile"] == 0.975
    assert cfg["U1CriticalValue"] == 66.57
    serialized = json.dumps(spec).lower()
    assert "candidateblocks" not in serialized
    assert "primaryblock" not in serialized
    assert "historical return" in " ".join(spec["prohibitions"]).lower()


def test_v3_runner_can_be_invoked_directly_from_repo_root():
    completed = subprocess.run(
        [sys.executable, "scripts/run_alpha_inference_calibration_v3.py", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "self-normalized calibration protocol" in completed.stdout
