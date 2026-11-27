"""Checks actual candidate evidence packet; not an experiment."""
import json
from pathlib import Path

from research.narrative_intelligence import census


def test_real_candidate_packet_is_design_only():
    path = Path(census.PILOT).with_name("matched_packet_candidate.json")
    candidate = json.loads(path.read_text(encoding="utf-8"))
    result = census.matched_packets(numeric_facts=candidate["numeric_facts"],
                                    mechanisms=candidate["mechanisms"],
                                    as_of=candidate["as_of_date"])
    assert result["A"]["numeric"] == result["B"]["numeric"]
    facts = {row["id"]: row for row in result["A"]["numeric"]}
    baseline = facts[candidate["baseline_id"]]
    assert baseline["value"] == 2.2
    assert baseline["target"] == candidate["target"]["period"]
    assert baseline["unit"] == candidate["target"]["unit"]
    assert facts["spf-q3-US_REAL_GDP"]["value"] == 2.1
    assert facts["spf-q3-US_PAYROLL_GAINS"]["value"] == 80.4
    assert facts["spf-q4-US_PAYROLL_GAINS"]["value"] == 49.3
    assert candidate["protocol"]["actual_predictions"] == 0
    assert not candidate["protocol"]["forecast_registration_authorized"]
