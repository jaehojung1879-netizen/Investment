import json
from pathlib import Path

import pytest

from research.us_nonreliance_source_pilot_v1.scope import scope_history

rows = json.loads((Path(__file__).resolve().parents[1] / "research"
                   / "us_nonreliance_source_pilot_v1" / "observations.json").read_text(encoding="utf-8"))


def test_amendment():
    out = scope_history(rows, "2024-11-28T00:00:00+00:00")
    assert len(out) == 2
    assert len(out[1]["repeated_scope"]) == 3
    assert out[1]["new_scope"] == ["FY2024Q4_PRELIM", "FY2024_PRELIM"]


def test_review_not_confirmation():
    out = scope_history(rows, "2026-02-06T00:00:00+00:00")
    assert len(out[-1]["new_scope"]) == 3
    assert out[-1]["prior_review_now_confirmed"] == []


def test_review_later_confirmed():
    out = scope_history(rows, "2026-05-13T00:00:00+00:00")
    assert out[-1]["prior_review_now_confirmed"] == ["FY2023_10K", "FY2024_10K"]


def test_late_filing_not_backdated():
    assert len(scope_history(rows, "2026-06-01T00:00:00+00:00")) == 4
    assert len(scope_history(rows, "2026-09-10T00:00:00+00:00")) == 5


def test_duplicate():
    with pytest.raises(ValueError, match="duplicate"):
        scope_history(rows + [rows[0]], "2026-11-25T00:00:00+00:00")
