"""Deterministic, entirely synthetic safety checks for null calibration."""
import numpy as np
import pytest

from . import null_calibration as C


def test_null_series_has_correct_length_and_finite_observations():
    rng = np.random.default_rng(9)
    for overlap, ar in ((1, 0.0), (6, 0.0), (12, 0.5)):
        x = C._synthetic_null(rng, 48, overlap, ar)
        assert x.shape == (48,) and np.isfinite(x).all()


def test_null_calibration_reports_no_source_access_and_is_reproducible():
    kw = {"replications": 7, "draws": 39, "seed": 17,
          "grid": ((48, 1, 0.0), (48, 12, 0.5))}
    first, again = C.calibrate(**kw), C.calibrate(**kw)
    assert first == again
    assert first["historicalOutcomesRead"] == 0
    assert first["newHistoricalStudyExecuted"] is False
    assert first["registeredAlgorithmUnchanged"] is True
    assert first["status"] == "DIAGNOSTIC_NOT_VALIDATION"
    assert len(first["cells"]) == 2
    for row in first["cells"]:
        assert row["replications"] == 7
        assert 0 <= row["rejections"] <= 7
        assert 0 <= row["wilson95"][0] <= row["wilson95"][1] <= 1
        assert row["diagnosis"] in ("ANTI_CONSERVATIVE", "INSUFFICIENT_TO_ESTABLISH_CALIBRATION")


@pytest.mark.parametrize("kw", [
    {"replications": 1}, {"replications": True}, {"draws": 0},
    {"seed": -1}, {"grid": ((1, 12, 0.0),)},
    {"grid": ((48, 12, 1.0),)}, {"grid": ((48, 1, float("nan")),)},
])
def test_invalid_calibration_parameters_fail_closed(kw):
    with pytest.raises(ValueError, match="INVALID_"):
        C.calibrate(replications=3, draws=19, **kw)
