"""Regression tests for source-grounded narrative contrasts."""
import json

import pytest

from research.narrative_intelligence import mechanisms


def fixture():
    return json.loads(mechanisms.PILOT.read_text(encoding="utf-8"))


def test_pilot():
    result = mechanisms.diagnostics(fixture())
    assert result["releases"] == 4
    assert result["stock_table_releases"] == 3
    assert result["mechanism_claims"] == 7
    assert result["candidate_count"] == 2
    revisions = [r for r in result["revisions"] if r["metric"] == "stocks" and r["target"] == "2026-12-31"]
    assert len(revisions) == 2
    assert revisions[0]["delta"] == pytest.approx(-710.6)
    assert revisions[1]["delta"] == pytest.approx(779.7)
    assert not result["market_outcomes_read"]
    assert all(not r["same_panel_verified"] for r in revisions)


def test_minutes_not_available_on_meeting_day():
    data = fixture()
    data["docs"][0]["public"] = data["docs"][0]["event"]
    with pytest.raises(ValueError, match="PUBLICATION_CLOCK"):
        mechanisms.diagnostics(data)


def test_verbal_quantifier_not_numeric_share():
    data = fixture()
    data["claims"][0]["population_share"] = .2
    with pytest.raises(ValueError, match="UNOBSERVED_PROBABILITY"):
        mechanisms.diagnostics(data)


def test_staff_not_committee():
    data = fixture()
    data["claims"][5]["actor"] = "FOMC participants"
    with pytest.raises(ValueError, match="ACTOR_SCOPE"):
        mechanisms.diagnostics(data)


def test_no_stock_estimate_imputed_for_missing_report():
    data = fixture()
    data["releases"][-1]["stocks"] = {"2026-12-31": 7000}
    with pytest.raises(ValueError, match="STOCK_SAMPLE_COUNT"):
        mechanisms.diagnostics(data)


def test_no_unapproved_candidate():
    data = fixture()
    data["prospective_candidates"][0]["kind"] = "REGISTERED"
    with pytest.raises(ValueError, match="UNAUTHORIZED_FORECAST"):
        mechanisms.diagnostics(data)
