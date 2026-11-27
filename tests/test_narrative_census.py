"""Source census regressions and matched packet invariants."""
import json
from copy import deepcopy

import pytest

from research.narrative_intelligence import census


def inputs():
    return (json.loads(census.PILOT.read_text(encoding="utf-8")),
            json.loads(census.PREVIOUS.read_text(encoding="utf-8")))


def test_fixed_census_and_stock_path():
    result = census.diagnostics(*inputs())
    assert result["calendar_coverage"] == result["calendar_expected"] == 8
    assert result["manual_claims"] == 26
    assert result["stock_release_count"] == 5
    assert [r["value"] for r in result["same_target_paths"]["2025-12-31"]] == [
        5088.2, 5824.6, 6489.9, 5801.7, 6830.0]
    assert result["independent_people_count"] is None
    assert not result["market_outcomes_read"]


def test_missing_meeting_rejected():
    a, b = inputs()
    a["meetings"].pop()
    with pytest.raises(ValueError, match="CALENDAR_CENSUS"):
        census.diagnostics(a, b)


def test_meeting_day_not_release():
    a, b = inputs()
    a["meetings"][0]["publication"] = a["meetings"][0]["meeting_end"]
    with pytest.raises(ValueError, match="PUBLICATION_OR_SOURCE"):
        census.diagnostics(a, b)


def test_no_numeric_population_share():
    a, b = inputs()
    a["meetings"][0]["claims"][0]["share"] = .9
    with pytest.raises(ValueError, match="CLAIM_SCHEMA"):
        census.diagnostics(a, b)


def test_duplicate_claim():
    a, b = inputs()
    a["meetings"][0]["claims"].append(deepcopy(a["meetings"][0]["claims"][0]))
    with pytest.raises(ValueError, match="DUPLICATE_CLAIM"):
        census.diagnostics(a, b)


def test_same_numeric_baseline():
    fact = {"id": "num", "source": "survey", "locator": "table 1", "publication": "2026-11-16"}
    text = {"id": "text", "source": "minutes", "locator": "outlook", "publication": "2026-11-18"}
    result = census.matched_packets(numeric_facts=[fact], mechanisms=[text], as_of="2026-11-28")
    assert result["A"]["numeric"] == result["B"]["numeric"]
    assert "mechanisms" not in result["A"]


@pytest.mark.parametrize("published", ["2026-11-28", "2026-11-29"])
def test_no_same_day_or_future_text(published):
    fact = {"id": "num", "source": "survey", "locator": "table", "publication": "2026-11-16"}
    text = {"id": "text", "source": "minutes", "locator": "outlook", "publication": published}
    with pytest.raises(ValueError, match="SAME_DAY_OR_FUTURE"):
        census.matched_packets(numeric_facts=[fact], mechanisms=[text], as_of="2026-11-28")


def test_no_raw_repo_write(tmp_path, monkeypatch):
    monkeypatch.setattr(census, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="EXTERNAL_OUTPUT"):
        census.acquire({}, tmp_path / "raw")
