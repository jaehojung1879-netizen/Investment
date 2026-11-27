"""Narrative pilot validation; no investment or historical market backtest."""
import json

import pytest

from research.narrative_intelligence import ledger


def fixture():
    return json.loads(ledger.PILOT.read_text(encoding="utf-8"))


def test_actual_transcribed_pilot():
    result = ledger.diagnostics(fixture())
    assert result["sources"] == 16
    assert result["claims"] == 21
    assert len(result["revisions"]) == 10
    assert result["independent_year_blocks"] == 3
    assert result["jan_mae"] == pytest.approx((1.9 + 1.1 + .7) / 3)
    assert result["jul_mae"] == pytest.approx((.2 + .7 + .2) / 3)
    assert not result["market_context_joined"]
    assert not result["investment_evaluation_authorized"]
    assert result["raw_source_bytes_admitted"] == 0


def test_same_target_not_cross_unit():
    x = fixture()
    x["comparisons"][0] = ["imf22-jan", "imf23-jul"]
    with pytest.raises(ValueError, match="MISMATCHED_TARGET"):
        ledger.diagnostics(x)


def test_reported_prior_not_independently_attested():
    result = ledger.diagnostics(fixture())
    row = next(r for r in result["revisions"] if r["before"] == "spf-prev-gdp")
    assert row["delta"] == pytest.approx(.1)
    assert not row["prior_independently_attested"]


@pytest.mark.parametrize("field,value,reason", [
    ("actor", "Another actor", "ACTOR_MISMATCH"),
    ("value", float("nan"), "FINITE_NUMBER"),
    ("forecast_date", "2021-01-01", "UNSUPPORTED_HISTORICAL_VINTAGE"),
    ("available_date", "2026-11-28", "INVALID_VINTAGE_ORDER"),
    ("target", "2021", "NOT_A_FUTURE_TARGET"),
])
def test_invalid_claim(field, value, reason):
    x = fixture()
    x["claims"][0][field] = value
    with pytest.raises(ValueError, match=reason):
        ledger.diagnostics(x)


def test_prior_cannot_claim_early_availability():
    x = fixture()
    row = next(r for r in x["claims"] if r["id"] == "spf-prev-gdp")
    row["available_date"] = row["forecast_date"]
    with pytest.raises(ValueError, match="INVALID_VINTAGE_ORDER"):
        ledger.diagnostics(x)


def test_duplicate_claim_rejected():
    x = fixture()
    x["claims"].append(x["claims"][0])
    with pytest.raises(ValueError, match="DUPLICATE_OR_EMPTY_ID"):
        ledger.diagnostics(x)


def test_no_fabricated_raw_hash():
    x = fixture()
    x["sources"][0]["raw_sha256"] = "a" * 64
    with pytest.raises(ValueError, match="UNSUPPORTED_PROVENANCE"):
        ledger.diagnostics(x)


def test_no_same_year_resolution():
    x = fixture()
    next(s for s in x["sources"] if s["id"] == "bea22")["publication_date"] = "2022-12-30"
    with pytest.raises(ValueError, match="BAD_RESOLUTION"):
        ledger.diagnostics(x)
