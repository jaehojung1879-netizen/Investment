"""Synthetic economics/admission tests; genuine fixture tests never price returns."""
import hashlib
import json
from pathlib import Path

import pytest

from research.cross_market_foundation_v1 import economics as E

DIGEST = "a" * 64
ROOT = Path(__file__).resolve().parents[1]


def quote():
    spec = {"kind": "CD91", "seriesId": "SYNTHETIC_TABLE", "itemCode": "SYNTHETIC_CD91",
            "cycle": "D", "sourceStatus": "LIVE_VALIDATED_SOURCE"}
    row = {"STAT_CODE": spec["seriesId"], "ITEM_CODE1": spec["itemCode"], "TIME": "20200102",
           "DATA_VALUE": "2.00", "UNIT_NAME": "연%"}
    return spec, row


def envelope(rows):
    return json.dumps({"StatisticSearch": {"row": rows}}).encode()


def cash_row():
    return {"date": "2020-01-02", "periodStart": "2020-01-01", "availableOn": "2020-01-03",
            "currency": "KRW", "basis": "REALIZED_CASH_PAYOFF", "instrumentId": "SYNTHETIC_DEPOSIT",
            "termsEvidence": "synthetic-dated-deposit-contract", "costBasis": "NET_OF_INSTRUMENT_COSTS",
            "investorTaxBasis": "GROSS_PRE_INVESTOR_TAX",
            "rights": E.RIGHTS, "sourcePayloadSha256": DIGEST, "netReturn": 0.00001}


def event():
    return {"eventId": "SYNTHETIC:D1", "securityId": "SYNTHETIC_STOCK", "currency": "USD",
            "shareBasis": "PER_OLD_COMMON_SHARE", "amountBasis": "GROSS_CASH", "grossAmount": 1.0,
            "exDate": "2020-01-02", "exDateEvidence": "synthetic-exchange-notice",
            "sourcePayloadSha256": DIGEST}


def test_ecos_adapter_preserves_quote_not_investable_or_pit():
    spec, row = quote()
    raw = envelope([row])
    result = E.parse_ecos_benchmark_quotes(raw, spec=spec)
    assert result["observations"] == [{"date": "2020-01-02", "annualPercent": 2.0}]
    assert result["sourcePayloadSha256"] == hashlib.sha256(raw).hexdigest()
    assert result["investable"] is False
    assert result["vintageStatus"] == "REVISED_HISTORY"
    assert result["publicationAvailability"] == "UNVERIFIED"


@pytest.mark.parametrize("field,value,code", [
    ("ITEM_CODE1", "OTHER", "CASH_SELECTOR_MISMATCH"),
    ("ITEM_CODE2", "UNREQUESTED", "CASH_SELECTOR_MISMATCH"),
    ("STAT_CODE", "OTHER", "CASH_SELECTOR_MISMATCH"),
    ("UNIT_NAME", "%", "CASH_QUOTE_UNIT_UNVERIFIED"),
    ("DATA_VALUE", "-", "MISSING_CASH_QUOTE"),
    ("DATA_VALUE", "NaN", "MISSING_CASH_QUOTE"),
    ("TIME", "20201301", "INVALID_ECONOMIC_DATE"),
])
def test_ecos_rejects_wrong_identity_units_missing_or_invalid(field, value, code):
    spec, row = quote()
    row[field] = value
    with pytest.raises(E.EconomicInputError, match=code):
        E.parse_ecos_benchmark_quotes(envelope([row]), spec=spec)


def test_ecos_source_status_and_duplicate_gate():
    spec, row = quote()
    with pytest.raises(E.EconomicInputError, match="DUPLICATE_CASH_QUOTE"):
        E.parse_ecos_benchmark_quotes(envelope([row, row]), spec=spec)
    spec["sourceStatus"] = "ASSUMED"
    with pytest.raises(E.EconomicInputError, match="CASH_SERIES_IDENTITY_UNVERIFIED"):
        E.parse_ecos_benchmark_quotes(envelope([row]), spec=spec)


def test_ecos_missing_selected_secondary_item_is_not_an_aggregate_series():
    spec, row = quote()
    spec["itemCode2"] = "EXPLICIT_SECONDARY_SELECTOR"
    with pytest.raises(E.EconomicInputError, match="CASH_SELECTOR_MISMATCH"):
        E.parse_ecos_benchmark_quotes(envelope([row]), spec=spec)


def test_only_documented_investable_cash_inputs_admitted_without_execution():
    result = E.build_cash_input_contract([cash_row()], required_dates=["2020-01-02"], as_of="2020-01-03")
    assert result["rows"][0]["netReturn"] == 0.00001
    assert result["outcomeExecutionAuthorized"] is False


@pytest.mark.parametrize("field,value,code", [
    ("basis", "BOK_POLICY_RATE", "REFERENCE_RATE_NOT_INVESTABLE_CASH"),
    ("basis", "CD91", "REFERENCE_RATE_NOT_INVESTABLE_CASH"),
    ("basis", "KOFR", "REFERENCE_RATE_NOT_INVESTABLE_CASH"),
    ("currency", "USD", "CASH_CURRENCY_MISMATCH"),
    ("rights", "PUBLIC_ACCESS", "CASH_RIGHTS_UNVERIFIED"),
    ("termsEvidence", None, "INVESTABLE_TERMS_UNVERIFIED"),
    ("costBasis", "GROSS", "INVESTABLE_TERMS_UNVERIFIED"),
    ("investorTaxBasis", "ASSUMED", "CASH_TAX_BASIS_UNVERIFIED"),
    ("availableOn", "2020-01-04", "CASH_AVAILABILITY_MISMATCH"),
    ("availableOn", "2020-01-01", "CASH_AVAILABILITY_MISMATCH"),
    ("periodStart", "2019-12-31", "CASH_ACCRUAL_PERIOD_MISMATCH"),
    ("netReturn", None, "INVALID_ECONOMIC_NUMBER"),
    ("netReturn", float("inf"), "INVALID_ECONOMIC_NUMBER"),
    ("netReturn", True, "INVALID_ECONOMIC_NUMBER"),
    ("netReturn", -1, "INVALID_CASH_PAYOFF"),
    ("sourcePayloadSha256", "x" * 64, "SOURCE_DIGEST_REQUIRED"),
])
def test_cash_fails_closed(field, value, code):
    row = cash_row()
    row[field] = value
    with pytest.raises(E.EconomicInputError, match=code):
        E.build_cash_input_contract([row], required_dates=["2020-01-02"], as_of="2020-01-03")


def test_cash_no_fill_or_duplicate_or_future_period():
    with pytest.raises(E.EconomicInputError, match="CASH_PERIOD_COVERAGE_GAP"):
        E.build_cash_input_contract([], required_dates=["2020-01-02"], as_of="2020-01-03")
    with pytest.raises(E.EconomicInputError, match="DUPLICATE_CASH_PERIOD"):
        E.build_cash_input_contract([cash_row(), cash_row()], required_dates=["2020-01-02"], as_of="2020-01-03")
    with pytest.raises(E.EconomicInputError, match="FUTURE_CASH_PERIOD"):
        E.build_cash_input_contract([cash_row()], required_dates=["2020-01-02"], as_of="2020-01-01")


def test_cash_calendar_cannot_silently_skip_weekend_accrual():
    friday = dict(cash_row(), date="2020-01-03", periodStart="2020-01-02")
    monday = dict(cash_row(), date="2020-01-06", periodStart="2020-01-05", availableOn="2020-01-07")
    with pytest.raises(E.EconomicInputError, match="CASH_CALENDAR_GRID_GAP"):
        E.build_cash_input_contract([friday, monday], required_dates=["2020-01-03", "2020-01-06"], as_of="2020-01-07")


def test_cash_requires_explicit_calendar_day_payoffs_including_weekend():
    dates = ["2020-01-03", "2020-01-04", "2020-01-05", "2020-01-06"]
    starts = ["2020-01-02", "2020-01-03", "2020-01-04", "2020-01-05"]
    rows = [dict(cash_row(), date=end, periodStart=start, availableOn="2020-01-07")
            for start, end in zip(starts, dates)]
    result = E.build_cash_input_contract(rows, required_dates=dates, as_of="2020-01-07")
    assert len(result["rows"]) == 4
    with pytest.raises(E.EconomicInputError, match="CASH_PERIOD_COVERAGE_GAP"):
        E.build_cash_input_contract(rows[:1] + rows[2:], required_dates=dates, as_of="2020-01-07")


def test_real_existing_issuer_payload_hash_only_and_preserved_semantics():
    directory = ROOT / "docs/audits/kr-alpha-atlas-phase-c-integrity/sources"
    manifest = E.verify_existing_benchmark_snapshot(directory)
    raw = (directory / manifest["files"]["issuerDistributions"]["path"]).read_bytes()
    result = E.adapt_issuer_distributions(raw)
    assert result["sourcePayloadSha256"] == manifest["files"]["issuerDistributions"]["sha256"]
    assert len(result["events"]) == 20
    assert all(row["exDate"] is None and row["investorNetCash"] is None for row in result["events"])
    assert result["coverage"] == "SOURCE_WINDOW_ONLY_NOT_FULL_HISTORY"
    assert result["rights"] == "UNVERIFIED"


def test_synthetic_issuer_record_payment_taxable_and_duplicate():
    row = {"basicD": "20200131", "payD": "20200204", "dividA": 100, "taxDividA": 30}
    raw = json.dumps({"dividList": [row]}).encode()
    adapted = E.adapt_issuer_distributions(raw)["events"][0]
    assert adapted["recordDate"] == "2020-01-31"
    assert adapted["paymentDate"] == "2020-02-04"
    assert adapted["taxableAmount"] == 30
    assert adapted["grossAmount"] == 100
    with pytest.raises(E.EconomicInputError, match="DUPLICATE_DISTRIBUTION_EVENT"):
        E.adapt_issuer_distributions(json.dumps({"dividList": [row, row]}).encode())


def test_distribution_reconciliation_reuses_existing_reader_without_claiming_completeness():
    result = E.reconcile_distribution_events([event()], [event()])
    assert result["status"] == "MATCHED_EVENTS_ONLY"
    assert result["completenessCertified"] is False
    assert result["pairs"] == 1


def test_same_date_different_event_or_security_cannot_match():
    other = dict(event(), eventId="OTHER")
    result = E.reconcile_distribution_events([event()], [other])
    assert result["status"] == "BLOCKED"
    assert result["pairs"] == 2
    assert result["unmatchedOfficialEvents"] == 1
    assert result["unmatchedVendorEvents"] == 1
    assert "UNMATCHED_DISTRIBUTION_EVENTS" in result["errors"]
    other = dict(event(), securityId="OTHER")
    with pytest.raises(E.EconomicInputError, match="DISTRIBUTION_IDENTITY_OR_BASIS_MISMATCH"):
        E.reconcile_distribution_events([event()], [other])


@pytest.mark.parametrize("field,value,code", [
    ("exDate", None, "INVALID_ECONOMIC_DATE"),
    ("exDateEvidence", None, "EX_DATE_EVIDENCE_REQUIRED"),
    ("amountBasis", "NET_CASH", "DISTRIBUTION_BASIS_UNVERIFIED"),
    ("shareBasis", None, "DISTRIBUTION_BASIS_UNVERIFIED"),
    ("sourcePayloadSha256", None, "SOURCE_DIGEST_REQUIRED"),
])
def test_distribution_rejects_ambiguous_source(field, value, code):
    row = event()
    row[field] = value
    with pytest.raises(E.EconomicInputError, match=code):
        E.reconcile_distribution_events([row], [event()])


def test_distribution_mismatch_never_averaged_away():
    result = E.reconcile_distribution_events([event()], [dict(event(), grossAmount=0.846)])
    assert result["status"] == "BLOCKED"
    assert result["bySecurity"][0]["mismatchReasonCounts"]["GROSS_NET_REPRESENTATION"] == 1


def test_no_distribution_double_counting_or_terminal_zero_assumption():
    result = E.total_return_input_gate(price_basis="TOTAL_RETURN_INDEX", distributions_complete=False,
                                       terminal_required=True, terminal_evidence=None,
                                       actions_complete=False, investor_tax_basis="UNKNOWN", raw_events_applied=True)
    assert result["status"] == "BLOCKED"
    assert set(result["errors"]) == {"DISTRIBUTION_DOUBLE_COUNTING", "DISTRIBUTION_COVERAGE_UNVERIFIED",
                                    "TERMINAL_CONSIDERATION_UNRESOLVED", "CORPORATE_ACTION_COVERAGE_UNVERIFIED",
                                    "INVESTOR_TAX_BASIS_UNVERIFIED"}
    assert result["outcomeExecutionAuthorized"] is False


def test_source_gate_does_not_authorize_outcome():
    result = E.total_return_input_gate(price_basis="AS_TRADED_CLOSE", distributions_complete=True,
                                       terminal_required=False, terminal_evidence=None,
                                       actions_complete=True, investor_tax_basis="GROSS_PRE_INVESTOR_TAX")
    assert result["status"] == "ADMISSIBLE_INPUT_CONTRACT"
    assert result["sourcePayloadVerified"] is False
    assert result["outcomeExecutionAuthorized"] is False


@pytest.mark.parametrize("evidence", [None, "last price", "0", "ASSUMED_ZERO", "x" * 64])
def test_terminal_consideration_cannot_be_inferred_from_truthy_text(evidence):
    result = E.total_return_input_gate(price_basis="AS_TRADED_CLOSE", distributions_complete=True,
                                       terminal_required=True, terminal_evidence=evidence,
                                       actions_complete=True, investor_tax_basis="GROSS_PRE_INVESTOR_TAX")
    assert result["status"] == "BLOCKED"
    assert "TERMINAL_CONSIDERATION_UNRESOLVED" in result["errors"]


def test_terminal_digest_is_a_reference_not_actual_source_verification():
    result = E.total_return_input_gate(price_basis="AS_TRADED_CLOSE", distributions_complete=True,
                                       terminal_required=True, terminal_evidence=DIGEST,
                                       actions_complete=True, investor_tax_basis="GROSS_PRE_INVESTOR_TAX")
    assert result["status"] == "ADMISSIBLE_INPUT_CONTRACT"
    assert result["sourcePayloadVerified"] is False
    assert result["evidenceLevel"] == "DECLARATION_AND_DIGEST_REFERENCE_ONLY"
