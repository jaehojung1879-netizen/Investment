"""Invented accounting only: no real outcomes, prices, research runner or labels."""
from __future__ import annotations

import ast
import copy
import json
import sys
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import finnhub_derive as FD  # noqa: E402
from pipeline import us_shareholder_distribution as U  # noqa: E402

META = U.SourceMetadata(U.SOURCE, "SYNTHETIC", "synthetic fiscal-YTD source contract")


def filing(year, stage="FY", dividends=20, repurchases=30, ocf=100, shares=100, *, amendment="", available=None):
    end = date(year, {"Q1": 3, "Q2": 6, "Q3": 9, "FY": 12}[stage], {"Q1": 31, "Q2": 30, "Q3": 30, "FY": 31}[stage])
    start = date(year, 1, 1)
    cf = [{"concept": "us-gaap_" + c, "value": v, "unit": "usd"}
          for c, v in ((U.FLOW_CONCEPTS["cashDividendsPaidTTM"], dividends),
                       (U.FLOW_CONCEPTS["commonStockRepurchasesTTM"], repurchases),
                       (U.FLOW_CONCEPTS["operatingCashFlowTTM"], ocf),
                       (U.FLOW_CONCEPTS["capitalExpendituresTTM"], 10)) if v is not None]
    return dict(id=f"SYN-{year}-{stage}{amendment}", ticker="SYN", source=U.SOURCE,
                fiscalYear=year, fiscalQuarter={"Q1": 1, "Q2": 2, "Q3": 3, "FY": 0}[stage],
                form=("10-K" if stage == "FY" else "10-Q") + ("/A" if amendment else ""),
                periodStart=start.isoformat(), periodEnd=end.isoformat(), periodDays=(end-start).days,
                availableFrom=available or (end+timedelta(days=30)).isoformat(),
                collectedAt="2026-10-01T00:00:00Z", acceptedDate=None,
                statements={"cf": cf, "ic": [], "bs": [
                    {"concept": "us-gaap_CommonStockSharesOutstanding", "value": shares, "unit": "shares"},
                    {"concept": "us-gaap_CashAndCashEquivalentsAtCarryingValue", "value": 90, "unit": "usd"}]})


def query(rows, as_of="2025-11-01", meta=META):
    return U.derive_features("SYN", as_of, rows, meta)


@pytest.mark.parametrize("stage", ["Q1", "Q2", "Q3"])
def test_proven_rollforward_not_four_cumulative_quarters(stage, monkeypatch):
    rows = [filing(2024, "FY", 100), filing(2024, stage, 40), filing(2025, stage, 60)]
    calls = []
    original = FD.trailing_twelve_months
    def spy(*args):
        calls.append(args)
        return original(*args)
    monkeypatch.setattr(FD, "trailing_twelve_months", spy)
    got = query(rows).features["cashDividendsPaidTTM"]
    assert got.value == 120 and got.basis == FD.BASIS_ROLLFORWARD
    assert len(got.inputs) == 3 and calls
    assert FD.FLOWS.keys() == {"netIncome", "revenue", "operatingIncome", "operatingCashFlow", "capex"}


def test_yoy_same_stage_needs_two_years_of_anchors():
    rows = [filing(2023, "FY", 80), filing(2023, "Q2", 30), filing(2024, "Q2", 40),
            filing(2024, "FY", 100), filing(2025, "Q2", 60)]
    got = query(rows).features["cashDividendsPaidTTMChangeYoY"]
    assert got.value == pytest.approx(120 / 90 - 1)
    assert {r.stage for r in got.inputs} == {"Q2", "FY"}


def test_annual_and_missing_vs_reported_zero():
    zero = query([filing(2024, dividends=0)]).features
    missing = query([filing(2024, dividends=None)]).features
    assert zero["cashDividendsPaidTTM"].value == 0
    assert zero["cashDividendsPaidTTM"].state == U.State.ZERO
    assert zero["totalCashDistributionTTM"].value == 30
    assert missing["cashDividendsPaidTTM"].state == U.State.NOT_REPORTED
    assert missing["totalCashDistributionTTM"].value is None


def test_zero_prior_growth_is_undefined_and_zero_distribution_coverage_is_not_infinite():
    got = query([filing(2023, dividends=0, repurchases=0), filing(2024, dividends=0, repurchases=0)]).features
    assert got["cashDividendsPaidTTMChangeYoY"].state == U.State.NOT_APPLICABLE
    assert got["distributionToOCF"].value == 0
    assert got["distributionCoverageByOCF"].value is None


@pytest.mark.parametrize("ocf", [0, -100])
def test_nonpositive_ocf_is_observed_but_does_not_support_a_ratio(ocf):
    got = query([filing(2024, ocf=ocf)]).features
    assert got["operatingCashFlowTTM"].value == ocf
    assert got["distributionToOCF"].value is None
    assert got["distributionCoverageByOCF"].value is None


def test_distribution_and_coverage_use_matching_ttm_not_cash_balance():
    got = query([filing(2024)]).features
    assert got["totalCashDistributionTTM"].value == 50
    assert got["distributionToOCF"].value == .5
    assert got["distributionCoverageByOCF"].value == 2
    assert got["cashAndCashEquivalents"].value == 90


def test_delayed_anchor_and_strict_same_day_rule():
    rows = [filing(2024, "Q2", 40), filing(2024, "FY", 100, available="2025-09-01"), filing(2025, "Q2", 60)]
    before = query(rows, "2025-09-01")
    assert before.features["cashDividendsPaidTTM"].state == U.State.INSUFFICIENT_HISTORY
    after = query(rows, "2025-09-02")
    assert after.features["cashDividendsPaidTTM"].value == 120
    assert after.report_period == "2025-Q2"  # delayed older report cannot become the current period


def test_acceptance_later_than_available_from_delays_visibility():
    row = filing(2024, available="2025-01-30")
    row["acceptedDate"] = "2025-02-02 17:00:00"
    assert query([row], "2025-02-02").features["cashDividendsPaidTTM"].value is None
    assert query([row], "2025-02-03").features["cashDividendsPaidTTM"].value == 20


def test_amendments_change_only_later_as_of_queries_and_never_fall_back_on_missing_amendment():
    original = filing(2024, dividends=20)
    amended = filing(2024, dividends=25, amendment="-A", available="2025-06-01")
    before = query([original], "2025-03-01")
    assert query([original, amended], "2025-03-01").to_dict() == before.to_dict()
    after = query([original, amended], "2025-06-02").features["cashDividendsPaidTTM"]
    assert after.value == 25 and after.inputs[0].filing_id == amended["id"]
    amended["statements"]["cf"] = []
    assert query([original, amended], "2025-06-02").features["cashDividendsPaidTTM"].value is None


def test_future_insertion_order_and_new_snapshot_do_not_change_historical_digest():
    old = [filing(2023), filing(2024)]
    expected = query(old, "2025-03-01")
    future = filing(2025, "FY", 999999)
    actual = query([future, *reversed(old)], "2025-03-01", replace(META, snapshot_id="NEW_SNAPSHOT"))
    assert actual.features == expected.features
    assert actual.feature_digest == expected.feature_digest
    assert query(old, "2025-03-01").to_dict() == expected.to_dict()


def test_amended_prior_anchor_does_not_rewrite_earlier_ttm():
    rows = [filing(2024, "FY", 100), filing(2024, "Q2", 40), filing(2025, "Q2", 60)]
    amendment = filing(2024, "FY", 200, amendment="-A", available="2025-10-01")
    assert query(rows, "2025-09-01").to_dict() == query([*rows, amendment], "2025-09-01").to_dict()
    assert query([*rows, amendment], "2025-10-02").features["cashDividendsPaidTTM"].value == 220


def test_buyback_expenditure_does_not_imply_share_reduction():
    rows = [filing(2023, shares=100), filing(2024, repurchases=100, shares=110)]
    default = query(rows).features
    assert default["commonStockRepurchasesTTM"].value == 100
    assert default["sharesOutstandingChangeYoY"].state == U.State.BLOCKED
    proof = (U.SharesBasisEvidence(rows[0]["id"], rows[1]["id"], "2025-02-01",
                                   "synthetic verified period end, one class and unchanged split basis"),)
    got = query(rows, meta=replace(META, shares_basis_evidence=proof)).features
    assert got["sharesOutstandingChangeYoY"].value == .1
    assert got["shareCountReductionIndicator"].value is False


def test_actual_share_reduction_requires_exact_pair_evidence():
    rows = [filing(2023), filing(2024, shares=90)]
    proof = (U.SharesBasisEvidence(rows[0]["id"], rows[1]["id"], "2025-02-01", "synthetic verified basis"),)
    assert query(rows, meta=replace(META, shares_basis_evidence=proof)).features["shareCountReductionIndicator"].value is True
    wrong = (U.SharesBasisEvidence("other", rows[1]["id"], "2025-02-01", "wrong pair"),)
    assert query(rows, meta=replace(META, shares_basis_evidence=wrong)).features["sharesOutstandingChangeYoY"].value is None


@pytest.mark.parametrize("unit", ["eur", "usd/shares", "pure", "unit_unknown"])
def test_invalid_or_unresolved_currency_unit(unit):
    row = filing(2024)
    row["statements"]["cf"][0]["unit"] = unit
    got = query([row]).features["cashDividendsPaidTTM"]
    assert got.value is None and got.state == U.State.INVALID


@pytest.mark.parametrize("value", [-5, float("nan"), float("inf"), True, "20"])
def test_invalid_outflow_sign_and_number(value):
    row = filing(2024)
    row["statements"]["cf"][0]["value"] = value
    got = query([row]).features["cashDividendsPaidTTM"]
    assert got.value is None and got.state == U.State.INVALID
    json.dumps(query([row]).to_dict(), allow_nan=False)


def test_local_generated_unit_resolution_is_reused():
    row = filing(2024)
    for entry in row["statements"]["cf"]:
        entry["unit"] = "unit12"
    assert query([row]).features["cashDividendsPaidTTM"].value == 20  # OCF anchors the label inside this filing


def test_duplicate_records_are_idempotent_and_conflicts_fail_closed():
    row = filing(2024)
    assert query([row, copy.deepcopy(row)]).to_dict() == query([row]).to_dict()
    conflicting = copy.deepcopy(row)
    conflicting["statements"]["cf"][0]["value"] = 999
    assert query([row, conflicting]).features["cashDividendsPaidTTM"].state == U.State.INVALID
    assert query([row, conflicting]).feature_digest == query([conflicting, row]).feature_digest


def test_duplicate_concept_rows_are_not_summed():
    row = filing(2024)
    row["statements"]["cf"].append(dict(row["statements"]["cf"][0], value=999))
    assert query([row]).features["cashDividendsPaidTTM"].state == U.State.AMBIGUOUS


def test_same_time_distinct_filings_are_not_arbitrarily_ordered_by_id():
    a, b = filing(2024), filing(2024, dividends=999, amendment="-A")
    assert query([a, b]).features["cashDividendsPaidTTM"].state == U.State.INVALID
    assert query([a, b]).feature_digest == query([b, a]).feature_digest


def test_structural_missingness_and_related_concepts_are_not_aliases():
    row = filing(2024)
    row["statements"]["cf"][0]["concept"] = "us-gaap_PaymentsOfDividends"
    row["statements"]["cf"][2]["concept"] += "ContinuingOperations"
    got = query([row]).features
    assert got["cashDividendsPaidTTM"].state == U.State.AMBIGUOUS
    assert got["operatingCashFlowTTM"].state == U.State.AMBIGUOUS
    assert got["totalCashDistributionTTM"].value is None


def test_missing_fiscal_history_is_not_annualized():
    got = query([filing(2025, "Q2", dividends=60)]).features
    assert got["cashDividendsPaidTTM"].state == U.State.INSUFFICIENT_HISTORY
    assert got["cashDividendsPaidTTMChangeYoY"].value is None


def test_fiscal_transition_and_discrete_quarter_metadata_fail_closed():
    rows = [filing(2024, "FY", 100), filing(2024, "Q2", 40), filing(2025, "Q2", 60)]
    rows[-1]["periodStart"] = "2025-04-01"
    rows[-1]["periodDays"] = 90
    assert query(rows).features["cashDividendsPaidTTM"].state == U.State.INVALID


def test_fiscal_year_change_and_unverified_convention():
    rows = [filing(2024, "FY"), filing(2024, "Q2"), filing(2025, "Q2")]
    rows[0]["periodEnd"] = "2024-12-15"
    rows[0]["periodDays"] = 349
    assert query(rows).features["cashDividendsPaidTTM"].state == U.State.INVALID
    got = query([filing(2024)], meta=replace(META, cumulative_evidence="")).features
    assert got["cashDividendsPaidTTM"].state == U.State.BLOCKED


def test_missing_date_and_wrong_source_never_license_data():
    row = filing(2024)
    row["availableFrom"] = None
    assert query([row]).report_period is None
    row = filing(2024)
    row["source"] = "another_vendor"
    assert all(f.value is None for f in query([row]).features.values())
    with pytest.raises(ValueError):
        query([row], meta=replace(META, currency="EUR"))


def test_digests_change_with_observable_values_but_not_unread_outcome_fields():
    row = filing(2024)
    first = query([row])
    class Spy(dict):
        def get(self, key, default=None):
            assert key not in {"forwardReturn", "label", "price", "outcomes"}
            return super().get(key, default)
    same = Spy(row, forwardReturn=999, label="never read")
    assert query([same]).feature_digest == first.feature_digest
    row["statements"]["cf"][0]["value"] = 21
    assert query([row]).feature_digest != first.feature_digest


def test_only_accounting_imports_and_no_file_network_model_or_return_access():
    tree = ast.parse((ROOT / "pipeline/us_shareholder_distribution.py").read_text())
    imports = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert imports <= {"__future__", "dataclasses", "datetime", "enum", "typing", "pipeline"}
    modules = {alias.name for n in ast.walk(tree) if isinstance(n, ast.Import) for alias in n.names}
    assert modules <= {"hashlib", "json", "math"}
    assert {alias.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module == "pipeline"
            for alias in n.names} == {"finnhub_derive", "finnhub_fundamentals"}
    assert not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in {"open", "eval", "exec"}
                   for n in ast.walk(tree))


def test_engine_owns_copies_and_repeated_queries_are_consistent():
    row = filing(2024)
    engine = U.FeatureEngine("SYN", [row], META)
    expected = engine.as_of("2025-03-01")
    row["statements"]["cf"][0]["value"] = 999
    assert engine.as_of("2025-03-01").to_dict() == expected.to_dict()


def test_future_share_basis_evidence_cannot_license_a_past_dilution_feature():
    rows = [filing(2023), filing(2024, shares=90)]
    proof = (U.SharesBasisEvidence(rows[0]["id"], rows[1]["id"], "2025-06-01", "later verification"),)
    before = query(rows, "2025-03-01")
    actual = query(rows, "2025-03-01", replace(META, shares_basis_evidence=proof))
    assert before.feature_digest == actual.feature_digest
    assert actual.features["sharesOutstandingChangeYoY"].state == U.State.BLOCKED
    assert query(rows, "2025-06-02", replace(META, shares_basis_evidence=proof)).features["shareCountReductionIndicator"].value is True


def test_share_units_are_not_promoted_by_the_tag_over_currency():
    rows = [filing(2023), filing(2024)]
    rows[-1]["statements"]["bs"][0]["unit"] = "usd"
    proof = (U.SharesBasisEvidence(rows[0]["id"], rows[1]["id"], "2025-02-01", "synthetic verified basis"),)
    assert query(rows, meta=replace(META, shares_basis_evidence=proof)).features["sharesOutstandingChangeYoY"].state == U.State.INVALID


def test_evidenced_share_change_does_not_substitute_weighted_average_shares():
    rows = [filing(2023), filing(2024)]
    rows[-1]["statements"]["bs"][0]["concept"] = "us-gaap_WeightedAverageNumberOfDilutedSharesOutstanding"
    proof = (U.SharesBasisEvidence(rows[0]["id"], rows[1]["id"], "2025-02-01", "synthetic verified basis"),)
    assert query(rows, meta=replace(META, shares_basis_evidence=proof)).features["sharesOutstandingChangeYoY"].state == U.State.NOT_REPORTED


def test_unverified_family_blocks_every_downstream_ratio_and_growth():
    meta = replace(META, unverified_flow_concepts=(U.FLOW_CONCEPTS["cashDividendsPaidTTM"],))
    features = query([filing(2023), filing(2024)], meta=meta).features
    for name in ("cashDividendsPaidTTM", "cashDividendsPaidTTMChangeYoY", "totalCashDistributionTTM",
                 "totalCashDistributionChangeYoY", "distributionToOCF", "distributionCoverageByOCF"):
        assert features[name].value is None and features[name].state == U.State.BLOCKED


def test_audit_is_bounded_source_hashed_and_fails_instead_of_reporting_empty_success(tmp_path):
    import gzip
    import hashlib
    from scripts import audit_us_shareholder_distribution as A
    rows = [filing(2023), filing(2024), filing(2024)]
    blob = gzip.compress(("\n".join(json.dumps(r) for r in rows) + "\n").encode(), mtime=0)
    (tmp_path / "finnhub-2024.jsonl.gz").write_bytes(blob)
    manifest = {"commit": "a" * 40, "files": [{"path": "finnhub-2024.jsonl.gz",
                  "gitBlob": hashlib.sha1(b"blob " + str(len(blob)).encode() + b"\0" + blob).hexdigest()}]}
    (tmp_path / "source-manifest.json").write_text(json.dumps(manifest))
    report = A.build_report(tmp_path, source_commit="a" * 40, cutoff="2025-03-01")
    assert report["rawFilingsRead"] == 3 and report["companies"] == 1
    assert report["duplicateSourceIDs"] == 1 and report["conflictingSourceIDs"] == 0
    assert report["jointReadyCompanyDates"] == 0  # tiny sample has no verified convention
    assert report["featureStates"]["totalCashDistributionTTM"]["BLOCKED"] == 2
    assert not any(report[key] for key in ("readsReturns", "readsLabels", "readsPrices", "fitsModels", "writesSignalHistory"))
    assert report == A.build_report(tmp_path, source_commit="a" * 40, cutoff="2025-03-01")
    with pytest.raises(ValueError, match="bounded audit"):
        A.build_report(tmp_path, source_commit="a" * 40, cutoff="2025-03-01", max_filings=1)
    with pytest.raises(ValueError, match="SOURCE_COMMIT_MISMATCH"):
        A.build_report(tmp_path, source_commit="b" * 40, cutoff="2025-03-01")
    (tmp_path / "finnhub-2024.jsonl.gz").write_bytes(blob + b"different")
    with pytest.raises(ValueError, match="SOURCE_BLOB_MISMATCH"):
        A.build_report(tmp_path, source_commit="a" * 40, cutoff="2025-03-01")


def test_audit_has_no_outcome_or_research_dependencies():
    tree = ast.parse((ROOT / "scripts/audit_us_shareholder_distribution.py").read_text())
    assert {alias.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module == "pipeline"
            for alias in n.names} == {"finnhub_fundamentals", "us_shareholder_distribution"}


def test_invalid_publication_chronology_is_refused_even_when_acceptance_is_later():
    row = filing(2024, available="2024-12-01")
    row["acceptedDate"] = "2025-02-01 10:00:00"
    assert query([row]).features["cashDividendsPaidTTM"].state == U.State.INVALID


def test_repurchase_authorization_is_never_an_executed_outflow():
    row = filing(2024, repurchases=None)
    row["statements"]["cf"].append({"concept": "Company_RepurchaseAuthorization", "value": 999, "unit": "usd"})
    assert query([row]).features["commonStockRepurchasesTTM"].state == U.State.NOT_REPORTED


def test_annual_yoy_rejects_a_changed_fiscal_year_boundary():
    prior = filing(2023)
    current = filing(2024)
    current.update(periodStart="2024-02-01", periodEnd="2025-01-31", periodDays=365, availableFrom="2025-03-01")
    assert query([prior, current]).features["cashDividendsPaidTTMChangeYoY"].state == U.State.INVALID


def test_known_timestamp_does_not_rank_above_an_unknown_same_day_timestamp():
    original = filing(2024)
    amended = filing(2024, dividends=999, amendment="-A")
    original["acceptedDate"] = original["availableFrom"] + " 10:00:00"
    assert query([original, amended]).features["cashDividendsPaidTTM"].state == U.State.INVALID
    amended["acceptedDate"] = amended["availableFrom"] + " 11:00:00"
    assert query([original, amended]).features["cashDividendsPaidTTM"].value == 999


def test_empty_input_preserves_declared_units_and_never_emits_a_fabricated_zero():
    features = query([]).features
    assert all(f.value is None and f.state == U.State.INSUFFICIENT_HISTORY for f in features.values())
    assert features["cashDividendsPaidTTM"].unit == "USD"
    assert features["cashDividendsPaidTTMChangeYoY"].unit == "ratio"
    assert features["shareCountReductionIndicator"].unit == "boolean"
