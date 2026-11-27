import csv
from pathlib import Path

import pytest

from research.guidance_source_pilot_v1.inspect_guidance import revisions


def sample():
    path = (Path(__file__).resolve().parents[1] / "research"
            / "guidance_source_pilot_v1" / "observations.csv")
    with path.open(encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def test_source_sample():
    result = revisions(sample())
    assert len(result) == 9
    assert [r["midpoint_change"] for r in result if r["midpoint_change"] is not None] == [
        "0.35", "0.095", "0.07"
    ]
    assert all(r["midpoint_change"] is None for r in result if r["issuer"] == "UPS")


def test_duplicate_refused():
    rows = sample()
    with pytest.raises(ValueError, match="duplicate"):
        revisions(rows + [rows[0]])


def test_no_bridge_after_missing():
    rows = [r for r in sample() if r["issuer"] == "UPS"]
    resumed = dict(rows[0], accession="synthetic", accepted_at="2025-10-01T12:00:00-04:00")
    assert revisions(rows + [resumed])[-1]["midpoint_change"] is None


def test_target_and_basis_separate():
    rows = sample()
    rows[3]["target"] = "FY2026"
    result = next(r for r in revisions(rows) if r["target"] == "FY2026")
    assert result["midpoint_change"] is None
    assert result["prior_accession"] is None
