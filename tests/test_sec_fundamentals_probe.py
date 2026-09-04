"""The SEC probe's parsing, which must hold without a vendor.

The network half can only run in CI. What is pinned here is the part that
decides what the probe's answer MEANS: which US-GAAP tag a concept resolved
to, that a `dei:` share-count tag is looked up in a different namespace than
the `us-gaap:` financial-statement tags, and that a quarterly duration fact's
period length is read from its own `start`/`end` rather than assumed.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "probe_sec_fundamentals", ROOT / "scripts" / "probe_sec_fundamentals.py")
P = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = P
_spec.loader.exec_module(P)


def _facts(**tags):
    """A minimal companyfacts payload: {tag: [fact, ...]} under us-gaap."""
    return {"entityName": "Test Co", "facts": {
        "us-gaap": {tag: {"units": {"USD": rows}} for tag, rows in tags.items()},
        "dei": {},
    }}


# --------------------------------------------------------------------------- #
# Tag resolution — filers do not agree on tags the way DART filers mostly
# agree on Korean labels
# --------------------------------------------------------------------------- #
def test_the_first_candidate_tag_present_is_used():
    payload = _facts(NetIncomeLoss=[{"val": 100, "form": "10-K", "filed": "2024-02-01",
                                     "fy": 2023, "start": "2023-01-01", "end": "2023-12-31"}])
    entry = P.parse_companyfacts(payload)
    assert entry["accounts"]["netIncome"]["tag"] == "NetIncomeLoss"


def test_a_later_alias_is_used_when_the_first_candidate_is_absent():
    """`Revenues` is the first candidate; a filer using the newer ASC 606 tag
    must still resolve, not read as revenue-less."""
    payload = _facts(RevenueFromContractWithCustomerExcludingAssessedTax=[
        {"val": 500, "form": "10-K", "filed": "2024-02-01", "fy": 2023}])
    entry = P.parse_companyfacts(payload)
    assert entry["accounts"]["revenue"]["tag"] == \
        "RevenueFromContractWithCustomerExcludingAssessedTax"


def test_a_concept_with_no_matching_tag_is_reported_missing_not_guessed():
    entry = P.parse_companyfacts(_facts())
    assert entry["accounts"]["equity"]["tag"] is None
    assert entry["accounts"]["equity"]["candidatesChecked"] == P.CANDIDATE_TAGS["equity"]


# --------------------------------------------------------------------------- #
# Share counts live in a different namespace than the financial statements
# --------------------------------------------------------------------------- #
def test_share_counts_are_read_from_the_dei_namespace_not_us_gaap():
    payload = _facts(NetIncomeLoss=[{"val": 100, "form": "10-K",
                                     "filed": "2024-02-01", "fy": 2023}])
    payload["facts"]["dei"] = {
        "EntityCommonStockSharesOutstanding": {
            "units": {"shares": [{"val": 1_000_000, "end": "2024-01-01"}]}}}
    entry = P.parse_companyfacts(payload)
    assert entry["sharesTag"] == "EntityCommonStockSharesOutstanding"
    assert entry["sharesFactCount"] == 1


def test_no_dei_share_tag_is_reported_rather_than_falling_back_to_us_gaap():
    entry = P.parse_companyfacts(_facts())
    assert entry["sharesTag"] is None
    assert "sharesFactCount" not in entry


# --------------------------------------------------------------------------- #
# Filed dates — the field the whole plan hangs on, same as DART's receipt date
# --------------------------------------------------------------------------- #
def test_filed_date_coverage_is_counted_against_every_fact_not_just_some():
    payload = _facts(NetIncomeLoss=[
        {"val": 100, "form": "10-K", "filed": "2024-02-01", "fy": 2023},
        {"val": 90, "form": "10-K", "fy": 2022},  # no filed date
    ])
    entry = P.parse_companyfacts(payload)
    assert entry["factCount"] == 2
    assert entry["hasFiledDate"] == 1, "누락된 filed는 있는 것으로 세면 안 된다"


# --------------------------------------------------------------------------- #
# Quarterly duration is arithmetic on start/end, not a guessed column
# --------------------------------------------------------------------------- #
def test_the_quarterly_period_length_is_computed_from_its_own_start_and_end():
    payload = _facts(NetIncomeLoss=[
        {"val": 30, "form": "10-Q", "filed": "2023-11-01",
         "start": "2023-07-01", "end": "2023-09-30", "fy": 2023},
    ])
    entry = P.parse_companyfacts(payload)
    assert entry["sampleQuarterlyFact"]["days"] == 91
    assert entry["sampleQuarterlyFact"]["filed"] == "2023-11-01"


def test_an_annual_only_company_reports_no_quarterly_sample_rather_than_a_guess():
    payload = _facts(NetIncomeLoss=[
        {"val": 100, "form": "10-K", "filed": "2024-02-01", "fy": 2023}])
    entry = P.parse_companyfacts(payload)
    assert "sampleQuarterlyFact" not in entry


# --------------------------------------------------------------------------- #
# What the model actually reads
# --------------------------------------------------------------------------- #
def test_every_factor_input_the_production_model_needs_is_probed():
    covered = {item for inputs in P.FACTOR_INPUTS.values() for item in inputs}
    for needed in ("netIncome", "equity", "revenue", "operatingIncome",
                  "liabilities", "operatingCashFlow", "capex", "sharesOutstanding"):
        assert needed in covered, f"{needed} 없이는 만들 수 없는 팩터가 있다"


def test_multiple_tag_aliases_are_checked_where_filers_disagree():
    assert len(P.CANDIDATE_TAGS["revenue"]) > 1
    assert len(P.CANDIDATE_TAGS["netIncome"]) > 1
