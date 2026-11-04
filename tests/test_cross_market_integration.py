"""Connect source, industry, economic and comparison contracts on synthetic data.

The numerical observations below are invented fixtures, never real research
outcomes. Genuine source tests elsewhere stop at bytes, dates and identities.
"""
from dataclasses import replace

import pytest

from pipeline import industry_foundation as F
from research.cross_market_foundation_v1 import comparison as C
from research.cross_market_foundation_v1 import economics as E
from research.cross_market_foundation_v1 import industry as I
from test_cross_market_comparison import inputs, observation_block

SHA = "a" * 64


@pytest.mark.parametrize("region", ["KR", "US"])
def test_qualified_synthetic_cohorts_feed_identical_funded_etf_comparison(region):
    common, paths = inputs(region)
    membership = [F.Membership(
        security_id=name, ticker=name, region=region, taxonomy_id="SYNTHETIC",
        taxonomy_version="v1", industry_id=industry, valid_from="2020-01-01", valid_to=None,
        source_date="2020-01-01", release_date="2020-01-01", known_to=None,
        source="synthetic://membership", source_sha256=SHA, evidence_kind="DATED_ASSIGNMENT",
        identity_provenance="synthetic security identity")
        for name, industry in common["securityIndustries"].items()]
    eligibility = {name: I.Investability(True, "2025-01-01", "2025-01-01", SHA,
                                        "2025-01-02", SHA) for name in common["universe"]}
    industries = [I.industry_plan(
        membership, common["universe"], common["signalDate"], region=region,
        taxonomy_id="SYNTHETIC", taxonomy_version="v1", industry_id=label,
        minimum_constituents=2, weighting="EQUAL_WEIGHT", currency=common["currency"],
        investability=eligibility) for label in ("I1", "I2")]
    assert all(row["status"] == "READY_RESEARCH_INPUT" for row in industries)
    assert all(row["hhi"] == .5 for row in industries)
    # Each industry receives 50%; its two equally weighted constituents 25%.
    paths[2]["weights"] = {name: .5 * weight for industry in industries
                            for name, weight in industry["weights"].items()}
    economics = E.total_return_input_gate(
        price_basis="AS_TRADED_CLOSE", distributions_complete=True,
        terminal_required=False, terminal_evidence=None, actions_complete=True,
        investor_tax_basis="GROSS_PRE_INVESTOR_TAX")
    assert economics["status"] == "ADMISSIBLE_INPUT_CONTRACT"
    assert economics["outcomeExecutionAuthorized"] is False
    common["industryQualificationSha256"] = C.digest(industries)
    for path in paths:
        path["commonSha256"] = C.digest(common)
    plan = C.prepare_comparison(common, paths)
    scored = C.score_synthetic_fixture(plan, observation_block(plan))
    assert plan["executionEnabled"] is False and scored["deployable"] is False
    # Independent closed-form check: 30bp buy + 30bp sell, +5% invented ETF.
    expected = 1.05 * (1 - .003) / (1 + .003) - 1
    assert scored["scenarios"][0]["netReturns"]["P0"] == pytest.approx(expected)
    assert scored["scenarios"][0]["excessVsRegionalEtf"]["P0"] == 0
    # Expiration blocks the cohort and emits no weights for an adapter to use.
    expired = {name: replace(row, valid_through="2025-01-01") for name, row in eligibility.items()}
    blocked = I.industry_plan(
        membership, common["universe"], common["signalDate"], region=region,
        taxonomy_id="SYNTHETIC", taxonomy_version="v1", industry_id="I1",
        minimum_constituents=2, weighting="EQUAL_WEIGHT", currency=common["currency"],
        investability=expired)
    assert blocked["status"] == "SOURCE_BLOCKED" and blocked["weights"] is None


def test_real_source_declarations_do_not_enable_the_synthetic_scorer():
    common, paths = inputs("US", "OUTCOME_EXPOSED_EXPLORATORY")
    plan = C.prepare_comparison(common, paths)
    with pytest.raises(ValueError, match="REAL_OUTCOME_EXECUTION_PROHIBITED"):
        C.score_synthetic_fixture(plan, observation_block(plan))
