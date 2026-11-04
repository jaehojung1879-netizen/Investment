"""Synthetic contract regression only: never read a historical price panel."""
from copy import deepcopy

import pandas as pd
import pytest

from pipeline import prospective_receipt_core as receipts
from pipeline import replay_calendar as calendar
from research.cross_market_foundation_v1 import comparison as C

SHA = "a" * 64
GIT_SHA = "b" * 40


def inputs(region="KR", evidence="SYNTHETIC"):
    etf = "069500.KS" if region == "KR" else "SPY"
    close = "2025-01-02T09:00:00Z" if region == "KR" else "2025-01-02T21:00:00Z"
    common = {"region": region, "benchmarkTicker": etf, "currency": "KRW" if region == "KR" else "USD",
              "evidenceClass": evidence, "marketRiskMultiplier": 1, "signalDate": "2025-01-02",
              "decisionAtUtc": close, "informationCutoffUtc": close, "executionDate": "2025-01-03",
              "benchmarkStartDate": "2025-01-03", "calendarVersion": calendar.CALENDAR_VERSION,
              "universe": ["A", "B", "C", "D"], "securityIndustries": {"A": "I1", "B": "I1", "C": "I2", "D": "I2"},
              "missingnessPolicy": "PRESEALED_COMMON_UNIVERSE_NO_POSTHOC_DROP",
              "returnBasis": {"kind": "TOTAL_RETURN", "dividends": "REINVESTED_ON_EX_DATE", "splits": "ADJUSTED_ONCE",
                              "terminal": "CITED_CONSIDERATION_OR_BLOCK", "currency": "KRW" if region == "KR" else "USD"},
              "inputEvidence": [{"role": role, "sha256": SHA, "payloadSha256": SHA, "sourceCommit": GIT_SHA,
                                 "availableAtUtc": "2025-01-01T00:00:00Z", "vintageAsOfUtc": "2025-01-01T00:00:00Z",
                                 "rightsStatus": "SYNTHETIC_ONLY" if evidence == "SYNTHETIC" else "VERIFIED_FOR_RESEARCH",
                                 "pitStatus": "VERIFIED"} for role in sorted(C.INPUT_ROLES)],
              "industryQualificationSha256": SHA, "stockQualificationSha256": SHA,
              "costPolicySha256": SHA, "executionPolicySha256": SHA, "scoreCombinationSha256": SHA,
              "riskPolicy": {"maximumStockNames": 4, "maximumNameWeight": .5, "maximumIndustryWeight": .6},
              "benchmarkIndustryWeights": {"I1": .5, "I2": .5}, "signalCapitalizations": dict.fromkeys("ABCD", 1),
              "costStressMultipliers": [1, 2, 3]}
    common["costModel"] = {"basis": "SELF_FINANCING_ENTRY_AND_TERMINAL_LIQUIDATION",
                           "returnInputBasis": "GROSS_BEFORE_TRANSACTION_COSTS", "interimTrades": False,
                           "switchCostRule": "FOUR_ACTUAL_LEGS_SHARED_TARIFF_NO_EXTRA_SURCHARGE",
                           "validFrom": "2025-01-01", "validThrough": "2027-01-01",
                           "tariff": {kind: {side: {"commissionBps": 10, "spreadBps": 20, "slippageBps": 0, "taxBps": 0}
                                            for side in ("BUY", "SELL")} for kind in ("STOCK", "ETF")}}
    common["costPolicySha256"] = C.digest(common["costModel"])
    weights = [{etf: 1}, {"A": .5, "C": .5}, dict.fromkeys("ABCD", .25),
               {"B": .5, "D": .5}, {"A": .5, "D": .5}, dict.fromkeys("ABCD", .25)]
    paths = [{"path": label, "scoreKind": C.SCORE_KINDS[label], "commonSha256": C.digest(common),
              "universe": list(common["universe"]), "weights": w} for label, w in zip(C.PATHS, weights)]
    for row in (paths[2], paths[3]):
        row["selectedIndustries"] = ["I1", "I2"]
    return common, paths


def prepared(region="KR", evidence="SYNTHETIC"):
    return C.prepare_comparison(*inputs(region, evidence))


def observation_block(plan, horizon=126):
    common = plan["common"]
    maturity = C.maturity_status(common["region"], common["executionDate"], horizon, "2027-01-01T00:00:00Z")
    symbols = common["universe"] + [common["benchmarkTicker"]]
    values = dict(zip(symbols, [.1, -.1, .2, 0, .05]))
    return {"fixtureId": "synthetic:fair-paired-block", "planSha256": plan["planSha256"],
            "costPolicySha256": common["costPolicySha256"], "executionPolicySha256": common["executionPolicySha256"],
            "horizonSessions": horizon, "asOfUtc": maturity["maturityCloseUtc"],
            "securityObservations": [{"fixtureId": "synthetic:fair-paired-block", "dataKind": "SYNTHETIC", "security": s,
                                      "entrySession": common["executionDate"], "exitSession": maturity["maturitySession"],
                                      "availableAtUtc": maturity["maturityCloseUtc"], "returnBasisSha256": C.digest(common["returnBasis"]),
                                      "currency": common["currency"], "returnCostBasis": "GROSS_BEFORE_TRANSACTION_COSTS",
                                      "terminalStatus": "NOT_TERMINATED", "totalReturn": values[s]} for s in symbols]}


def test_deterministic_outcome_free_input_contract_without_mutating_sources():
    common, paths = inputs()
    original = deepcopy((common, paths))
    first = C.prepare_comparison(common, paths)
    assert first == C.prepare_comparison(common, list(reversed(paths)))
    assert (common, paths) == original
    assert first["executionEnabled"] is False and first["deployable"] is False
    receipts.scan_for_outcome_keys(first)


@pytest.mark.parametrize(("key", "value", "code"), [
    ("benchmarkTicker", "QQQ", "REGIONAL_PRIMARY_ETF"),
    ("currency", "USD", "LOCAL_CURRENCY"),
    ("marketRiskMultiplier", .5, "MARKET_MULTIPLIER"),
    ("benchmarkStartDate", "2025-01-02", "ETF_START_DATE"),
    ("executionDate", "2025-01-06", "EXECUTION_NOT_NEXT"),
    ("missingnessPolicy", "DROP_FOR_EACH_MODEL", "SYMMETRIC_MISSINGNESS"),
    ("stockQualificationSha256", None, "BLOCKED_NO_QUALIFIED_INPUT"),
    ("costPolicySha256", None, "BLOCKED_NO_QUALIFIED_INPUT"),
    ("scoreCombinationSha256", None, "BLOCKED_NO_QUALIFIED_INPUT"),
    ("calendarVersion", "price-rows-as-calendar", "CALENDAR_VERSION"),
    ("costStressMultipliers", [1], "COMMON_COST_STRESSES"),
    ("decisionAtUtc", "2025-01-03T00:00:00Z", "NO_BACKDATING"),
])
def test_common_input_failure_is_not_an_actionable_fallback(key, value, code):
    common, paths = inputs()
    common[key] = value
    with pytest.raises(ValueError, match=code):
        C.prepare_comparison(common, paths)


def test_future_availability_and_vendor_revision_not_hidden_by_early_code_commit():
    for field in ("availableAtUtc", "vintageAsOfUtc"):
        common, paths = inputs()
        common["inputEvidence"][0][field] = "2025-01-02T09:00:01Z"
        with pytest.raises(ValueError, match="FUTURE_OR_REVISED"):
            C.prepare_comparison(common, paths)


def test_source_commit_is_not_payload_identity_and_unknown_rights_refused():
    for key, value, code in (("payloadSha256", None, "CONTENT_AND_SOURCE"),
                             ("pitStatus", "CURRENT_SIC_BACKDATED", "PIT_NOT_VERIFIED"),
                             ("rightsStatus", "UNKNOWN", "RIGHTS_BLOCKED")):
        common, paths = inputs()
        common["inputEvidence"][0][key] = value
        with pytest.raises(ValueError, match=code):
            C.prepare_comparison(common, paths)


def test_unclassified_names_cannot_be_dropped_only_for_industry_model():
    common, paths = inputs()
    del common["securityIndustries"]["A"]
    with pytest.raises(ValueError, match="COMMON_CLASSIFIED_UNIVERSE"):
        C.prepare_comparison(common, paths)
    common, paths = inputs()
    paths[3]["universe"] = ["B", "C", "D"]
    with pytest.raises(ValueError, match="UNIVERSE_MISMATCH"):
        C.prepare_comparison(common, paths)


def test_full_path_set_no_duplicate_or_selective_posthoc_removal():
    common, paths = inputs()
    paths[-1] = deepcopy(paths[0])
    with pytest.raises(ValueError, match="SIX_UNIQUE_PATHS"):
        C.prepare_comparison(common, paths)


@pytest.mark.parametrize(("index", "weights", "code"), [
    (0, {"A": .5, "C": .5}, "ETF_100"),
    (1, {"A": .7, "C": .3}, "NAME_CONCENTRATION"),
    (1, {"A": .5, "B": .5}, "INDUSTRY_CONCENTRATION"),
    (2, {"A": .5, "C": .5}, "SIGNAL_DATE_FIXED_CAP"),
    (4, {"A": .3, "B": .3, "C": .4}, "INDUSTRY_NEUTRAL"),
    (5, {"A": .4, "C": .4}, "FULLY_FUNDED"),
])
def test_route_semantics_and_shared_risk_contract(index, weights, code):
    common, paths = inputs()
    paths[index]["weights"] = weights
    with pytest.raises(ValueError, match=code):
        C.prepare_comparison(common, paths)


def test_industry_hierarchy_cannot_hold_outside_selected_industries():
    common, paths = inputs()
    paths[3]["selectedIndustries"] = ["I1"]
    with pytest.raises(ValueError, match="SELECTION_SCOPE"):
        C.prepare_comparison(common, paths)


def test_synthetic_arithmetic_etf_excess_and_cost_stress():
    plan = prepared()
    result = C.score_synthetic_fixture(plan, observation_block(plan))
    base, twice, thrice = result["scenarios"]
    assert base["netReturns"]["P1"] == pytest.approx(1.15 * (1 - .003) / (1 + .003) - 1)
    assert base["netReturns"]["P0"] == pytest.approx(1.05 * (1 - .003) / (1 + .003) - 1)
    assert base["excessVsRegionalEtf"]["P1"] == pytest.approx(.10 * (1 - .003) / (1 + .003))
    assert base["netReturns"]["P2"] == base["netReturns"]["P5"]
    assert twice["netReturns"]["P1"] == pytest.approx(1.15 * (1 - .006) / (1 + .006) - 1)
    assert thrice["netReturns"]["P1"] == pytest.approx(1.15 * (1 - .009) / (1 + .009) - 1)
    assert base["modeledFees"]["P1"]["entryFundedFraction"] == pytest.approx(1 / 1.003)
    assert result["evidenceClass"] == "SYNTHETIC_NOT_RESEARCH_EVIDENCE"


def test_cost_components_cannot_be_silently_omitted():
    common, paths = inputs()
    del common["costModel"]["tariff"]["STOCK"]["SELL"]["slippageBps"]
    with pytest.raises(ValueError, match="COMPLETE_COST_COMPONENTS"):
        C.prepare_comparison(common, paths)


def test_path_specific_cost_discount_and_already_net_returns_rejected():
    plan = prepared()
    block = observation_block(plan)
    block["costsByPath"] = {"P1": 0}
    with pytest.raises(ValueError, match="PATH_SPECIFIC_COST_OVERRIDE"):
        C.score_synthetic_fixture(plan, block)
    del block["costsByPath"]
    block["securityObservations"][0]["returnCostBasis"] = "NET_OF_FEES"
    with pytest.raises(ValueError, match="ALREADY_NET_RETURN_DOUBLE_COST"):
        C.score_synthetic_fixture(plan, block)


def test_four_switch_legs_share_one_tariff_and_no_extra_surcharge():
    common, _ = inputs()
    legs = [{"legId": "stock-out", "security": "A", "side": "SELL", "session": "2025-01-03", "notionalFractionOfInitialNav": .5},
            {"legId": "etf-in", "security": "069500.KS", "side": "BUY", "session": "2025-01-03", "notionalFractionOfInitialNav": .5},
            {"legId": "etf-out", "security": "069500.KS", "side": "SELL", "session": "2025-01-06", "notionalFractionOfInitialNav": .5},
            {"legId": "stock-in", "security": "A", "side": "BUY", "session": "2025-01-06", "notionalFractionOfInitialNav": .5}]
    assert C.price_execution_legs(common, legs)["totalCostFractionOfInitialNav"] == pytest.approx(4 * .5 * .003)
    assert C.price_execution_legs(common, legs, stress=3)["totalCostFractionOfInitialNav"] == pytest.approx(4 * .5 * .009)
    legs.append(deepcopy(legs[0]))
    with pytest.raises(ValueError, match="UNIQUE_EXECUTION_LEGS"):
        C.price_execution_legs(common, legs)


def test_identical_targets_pay_identical_costs_regardless_of_model_label():
    common, paths = inputs()
    paths[3]["weights"] = deepcopy(paths[1]["weights"])
    plan = C.prepare_comparison(common, paths)
    result = C.score_synthetic_fixture(plan, observation_block(plan))
    for scenario in result["scenarios"]:
        assert scenario["netReturns"]["P1"] == scenario["netReturns"]["P3"]
        assert scenario["modeledFees"]["P1"] == scenario["modeledFees"]["P3"]


@pytest.mark.parametrize(("commission_bps", "stress"), [(4000, 3), (5000, 2)])
def test_stressed_sell_fee_cannot_consume_or_exceed_liquidation_proceeds(commission_bps, stress):
    common, _ = inputs()
    common["costModel"]["tariff"]["STOCK"]["SELL"] = {
        "commissionBps": commission_bps, "spreadBps": 0, "slippageBps": 0, "taxBps": 0}
    sell = {"legId": "synthetic-sale", "security": "A", "side": "SELL", "session": "2025-01-03",
            "notionalFractionOfInitialNav": 1}
    with pytest.raises(ValueError, match="STRESSED_SELL_COST_NOT_SELF_FINANCING"):
        C.price_execution_legs(common, [sell], stress=stress)
    # High BUY costs remain valid: entry funding accounts for their consumption.
    common["costModel"]["tariff"]["STOCK"]["BUY"] = deepcopy(common["costModel"]["tariff"]["STOCK"]["SELL"])
    buy = {**sell, "legId": "synthetic-buy", "side": "BUY"}
    assert C.price_execution_legs(common, [buy], stress=stress)["totalCostFractionOfInitialNav"] == pytest.approx(commission_bps * stress / 10000)


def test_scorer_rejects_stress_that_would_create_negative_long_only_nav():
    common, paths = inputs()
    for sides in common["costModel"]["tariff"].values():
        for side in sides:
            sides[side] = {"commissionBps": 4000, "spreadBps": 0, "slippageBps": 0, "taxBps": 0}
    common["costPolicySha256"] = C.digest(common["costModel"])
    for path in paths:
        path["commonSha256"] = C.digest(common)
    plan = C.prepare_comparison(common, paths)
    with pytest.raises(ValueError, match="STRESSED_SELL_COST_NOT_SELF_FINANCING"):
        C.score_synthetic_fixture(plan, observation_block(plan))


def test_terminal_omission_blocks_entire_paired_comparison_not_only_losing_model():
    plan = prepared()
    block = observation_block(plan)
    block["securityObservations"][0]["terminalStatus"] = "LAST_PRICE_CARRIED_FORWARD"
    block["securityObservations"][0]["totalReturn"] = 0
    with pytest.raises(ValueError, match="BLOCKED_PATH_TERMINAL"):
        C.score_synthetic_fixture(plan, block)


def test_total_loss_requires_explicit_cited_terminal_consideration():
    plan = prepared()
    block = observation_block(plan)
    row = block["securityObservations"][0]
    row["totalReturn"] = -1
    with pytest.raises(ValueError, match="TOTAL_LOSS_REQUIRES_CITED_TERMINAL"):
        C.score_synthetic_fixture(plan, block)
    row.update(terminalStatus="CITED_CONSIDERATION", totalReturn=-1)
    with pytest.raises(ValueError, match="TERMINAL_UNRESOLVED"):
        C.score_synthetic_fixture(plan, block)
    row["terminalEvidenceSha256"] = SHA
    assert C.score_synthetic_fixture(plan, block)["scenarios"][0]["netReturns"]["P1"] == pytest.approx(.6 * (1 - .003) / (1 + .003) - 1)


@pytest.mark.parametrize("horizon", [126, 252])
@pytest.mark.parametrize("region", ["KR", "US"])
def test_horizon_not_measured_before_local_exchange_close(region, horizon):
    plan = prepared(region)
    block = observation_block(plan, horizon)
    before = receipts.utc(block["asOfUtc"]) - pd.Timedelta(seconds=1)
    assert C.maturity_status(region, "2025-01-03", horizon, before)["performance"] is None
    block["asOfUtc"] = before.isoformat()
    with pytest.raises(ValueError, match="OBSERVATION_INCOMPLETE"):
        C.score_synthetic_fixture(plan, block)


def test_xnys_holiday_early_close_and_dst_are_not_weekday_guesses():
    status = C.maturity_status("US", "2024-05-24", 126, "2026-01-01T00:00:00Z")
    assert status["maturitySession"] == "2024-11-22"
    # Direct bounds is shared with maturity: July 3 was an official early close.
    _, early = C._session_bounds("US", C._date("2024-07-03"))
    assert str(early) == "2024-07-03 17:00:00+00:00"


@pytest.mark.parametrize(("field", "value", "code"), [
    ("entrySession", "2025-01-02", "ENDPOINT_MISMATCH"),
    ("exitSession", "2025-01-03", "ENDPOINT_MISMATCH"),
    ("currency", "USD", "BASIS_OR_CURRENCY"),
    ("availableAtUtc", "2025-01-03T00:00:00Z", "FUTURE_OBSERVATION"),
    ("totalReturn", float("nan"), "VALID_TOTAL_RETURN"),
    ("dataKind", "REAL", "REAL_OUTCOME_EXECUTION"),
])
def test_security_and_etf_inputs_cannot_gain_different_treatment(field, value, code):
    plan = prepared()
    block = observation_block(plan)
    block["securityObservations"][-1][field] = value
    with pytest.raises(ValueError, match=code):
        C.score_synthetic_fixture(plan, block)


def test_duplicate_observations_and_plan_tampering_rejected():
    plan = prepared()
    block = observation_block(plan)
    block["securityObservations"].append(deepcopy(block["securityObservations"][0]))
    with pytest.raises(ValueError, match="DUPLICATE_SECURITY"):
        C.score_synthetic_fixture(plan, block)
    plan["paths"][1]["weights"]["A"] = .9
    with pytest.raises(ValueError, match="PLAN_DIGEST"):
        C.score_synthetic_fixture(plan, block)


def test_real_input_plans_never_have_an_outcome_execution_path():
    for evidence in ("OUTCOME_EXPOSED_EXPLORATORY", "PROSPECTIVE_PAPER"):
        plan = prepared(evidence=evidence)
        with pytest.raises(ValueError, match="REAL_OUTCOME_EXECUTION_PROHIBITED"):
            C.score_synthetic_fixture(plan, observation_block(plan))


def test_operational_adapter_verifies_receipt_without_mutation_or_target_copy():
    row = {"signalDate": "2025-01-02", "executionDate": "2025-01-03", "inputIdentities": {"marketPayload": SHA},
           "targets": {"A": .5}, "sourceCommit": GIT_SHA}
    row["receiptSha256"] = receipts.receipt_digest(row)
    original = deepcopy(row)
    adapted = C.read_operational_receipt(row, expected_sha256=row["receiptSha256"])
    assert row == original and adapted["readOnly"] is True and "targets" not in adapted
    assert adapted["inputIdentities"] == row["inputIdentities"]
    row["inputIdentities"]["marketPayload"] = "c" * 64
    with pytest.raises(ValueError, match="DIGEST_MISMATCH"):
        C.read_operational_receipt(row, expected_sha256=original["receiptSha256"])


def test_actual_portfolio_d_schema_adapter_uses_whole_record_pin_not_decision_digest():
    row = {"schema": "ENTRY_STATE_SHADOW_DECISION_V1", "region": "KR", "asOfDate": "2025-01-02",
           "executionSession": "2025-01-03", "sourceHashes": {"weekly": SHA}, "observationSha256": SHA,
           "sourceArtifactSha256": SHA, "sourceCommit": GIT_SHA, "digest": SHA, "receiptId": SHA,
           "targetWeights": {"A": .5, "069500.KS": .5}}
    pin = C.digest(row)
    result = C.read_portfolio_d_receipt(row, expected_record_sha256=pin)
    assert result["requiresOwningSemanticValidator"] is True and "targetWeights" not in result
    assert result["sourceHashes"] == row["sourceHashes"]
    row["sourceCommit"] = "c" * 40
    with pytest.raises(ValueError, match="WHOLE_RECORD_HASH"):
        C.read_portfolio_d_receipt(row, expected_record_sha256=pin)


def test_portfolio_d_code_commit_alone_never_establishes_actual_data_identity():
    row = {"schema": "ENTRY_STATE_SHADOW_DECISION_V1", "sourceCommit": GIT_SHA,
           "sourceHashes": None, "observationSha256": SHA, "sourceArtifactSha256": SHA,
           "digest": SHA, "receiptId": SHA}
    with pytest.raises(ValueError, match="PAYLOAD_IDENTITIES"):
        C.read_portfolio_d_receipt(row, expected_record_sha256=C.digest(row))


def test_outcomes_cannot_be_smuggled_into_input_receipt():
    common, paths = inputs()
    common["nested"] = {"realizedReturn": .5}
    with pytest.raises(ValueError, match="OUTCOME_FIELD_IN_RECEIPT"):
        C.prepare_comparison(common, paths)
