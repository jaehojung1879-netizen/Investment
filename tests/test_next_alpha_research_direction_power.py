"""Outcome-free power arithmetic and the decisions file it reads (synthetic only)."""

import json
import math
from pathlib import Path

import pytest

from research.next_alpha_research_direction_v1 import power

DECISIONS = Path(power.__file__).with_name("priority-decisions-v1.json")


def test_critical_multiplier_matches_textbook_values():
    assert power.critical_multiplier() == pytest.approx(1.959964 + 0.841621, abs=1e-5)
    # Holm first step over three primaries is stricter than a single test.
    assert power.critical_multiplier(family=3) > power.critical_multiplier()


def test_time_series_mde_and_years_are_inverse():
    m = power.mde_time_series(13.0, 13.7)
    assert m == pytest.approx(power.critical_multiplier() * 13.0 / math.sqrt(13.7))
    assert power.years_needed(13.0, m) == pytest.approx(13.7)


def test_event_mde_shrinks_with_events_and_grows_with_clustering():
    base = power.mde_event(20.0, 400, 2.0)
    assert power.mde_event(20.0, 1600, 2.0) == pytest.approx(base / 2)
    assert power.mde_event(20.0, 400, 8.0) == pytest.approx(base * 2)


@pytest.mark.parametrize("args", [(0.0, 10), (5.0, 0)])
def test_time_series_rejects_degenerate_inputs(args):
    with pytest.raises(ValueError):
        power.mde_time_series(*args)


def test_event_rejects_design_effect_below_one():
    with pytest.raises(ValueError):
        power.mde_event(20.0, 100, 0.5)


def test_gate_boundaries():
    assert power.gate(3.0, 3.0) == "POWER_PASS"
    assert power.gate(6.0, 3.0) == "POWER_MARGINAL_PROSPECTIVE_OR_BROADER_UNIVERSE_FIRST"
    assert power.gate(6.01, 3.0) == "POWER_NO_GO"


def test_decisions_file_is_unregistered_and_carries_no_actionable_output():
    spec = json.loads(DECISIONS.read_text(encoding="utf-8"))
    assert spec["status"] == "PROPOSED_NOT_REGISTERED"
    text = json.dumps(spec)
    for key in ('"weights"', '"positions"', '"targetWeights"', '"holdings"', '"liveValidated"'):
        assert key not in text
    ranks = [s["rank"] for s in spec["studies"]]
    assert ranks == sorted(ranks) and len(ranks) == len(set(ranks)) and 3 <= len(ranks) <= 5


def test_planning_table_is_reproducible_from_stated_assumptions():
    spec = json.loads(DECISIONS.read_text(encoding="utf-8"))
    table = power.planning_table(spec["powerPlanning"]["assumptions"])
    assert table == power.planning_table(spec["powerPlanning"]["assumptions"])
    by_label = {r["label"]: r for r in table["events"]}
    # The decisive planning facts quoted in the report.
    assert by_label["cancellations only, Top120, H126"]["gate"] == "POWER_NO_GO"
    assert by_label["supply contracts, broad KOSPI, H126"]["gate"] == "POWER_PASS"
    ts = {r["label"]: r for r in table["timeSeries"]}
    assert ts["C2-like concentrated book, full history"]["yearsFor3ppAlpha"] > 100
