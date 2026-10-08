"""kr-alpha-signal-v2: signal contract, decision states and the prospective receipt, on synthetic fixtures only.

No real price, filing, label or outcome is read anywhere in this file.
"""
from __future__ import annotations

import copy
import json
import random
from pathlib import Path

import pytest

from pipeline import kr_alpha_signal_v2 as S
from pipeline import kr_alpha_signal_v2_receipts as R
from pipeline import prospective_receipt_core as C

ROOT = Path(__file__).resolve().parents[1]
SIGNAL = "2026-10-16"                       # a Friday KR session; the next session (Mon 2026-10-19) is in a later ISO week
CREATED = "2026-10-16T09:00:00+00:00"       # 18:00 KST, after the 15:30 close
NOW = "2026-10-16T09:05:00+00:00"
SPEC = "a" * 64
AUTH = {"specSha256": SPEC, "mergeCommitSha": "b" * 40, "mergedAtUtc": "2026-10-05T03:00:00+00:00"}
CODE = {"commitSha": "c" * 40, "files": {"pipeline/kr_alpha_signal_v2.py": "d" * 64}}
DATA = {"pitFeatureSnapshot": "e" * 64, "universeSnapshot": "f" * 64, "industryMembership": "1" * 64}


def _row(ticker, industry, bm, ep, ni=0.05, ocf=0.06, imp=0.01, **extra):
    row = {"ticker": ticker, "industry": industry, "isPreferredShare": False, "priceAsOf": SIGNAL, "positiveVolumeSessions20": 20,
           "medianTradedValue60Krw": 5e10, "fundamentalsAvailableFrom": "2026-08-14", "bookToMarketProxy": bm, "earningsYieldProxy": ep,
           "netIncomeToAssets": ni, "ocfToAssets": ocf, "ocfImprovementToAssets": imp, "relative126": 0.1, "downsideVol126": 0.2,
           "maxDrawdown252": -0.25}
    row.update(extra)
    return row


def rows():
    out = [_row("A%d" % i, "INDUSTRY_A", 0.1 * i, 0.01 * i) for i in range(1, 7)]
    out[4]["ocfImprovementToAssets"] = -0.02          # A5: cheap, measured, deteriorating -> CHEAP_UNCONFIRMED
    out += [_row("B%d" % i, "INDUSTRY_B", 0.2 * i, 0.02 * i) for i in range(1, 7)]
    out[11]["ocfImprovementToAssets"] = None          # B6: cheap, confirmation unmeasured
    out += [_row("C%d" % i, "INDUSTRY_C", 1.0, 0.1) for i in range(1, 4)]          # thin industry
    out.append(_row("A1P", "INDUSTRY_A", 9.0, 0.9, isPreferredShare=True))       # a preferred share is never ranked
    return out


def forecasts(**overrides):
    names = {}
    for t, mu in (("A6", 0.06), ("B5", 0.04)):
        names[t] = {"expectedExcessReturn": mu, "standardError": 0.01,
                    "contributions": {"withinIndustry": mu * 0.75, "industry": mu * 0.25}}
    block = {"modelId": "synthetic-state-calibration", "modelSha256": "2" * 64, "trainingCutoff": "2026-04-01",
             "trainingTargetLastExitDate": "2026-10-15", "calibrationStatus": "CALIBRATED", "names": names}
    block.update(overrides)
    return block


def receipt(**kw):
    args = dict(rows=rows(), signal_date=SIGNAL, created_at_utc=CREATED, now_utc=NOW, spec_sha256=SPEC, code_identity=CODE, data_identity=DATA,
                authorization=AUTH)
    args.update(kw)
    return R.build_receipt(**args)


# --------------------------------------------------------------------------- #
# Signal
# --------------------------------------------------------------------------- #
def test_states_follow_the_registered_rule():
    states = {r["ticker"]: r["state"] for r in S.cross_section(rows(), SIGNAL)}
    assert states["A6"] == "CHEAP_CONFIRMED" and states["A5"] == "CHEAP_UNCONFIRMED" and states["A4"] == "NOT_CHEAP"
    assert states["B6"] == "CHEAP_CONFIRMATION_UNMEASURED" and states["B5"] == "CHEAP_CONFIRMED"
    assert all(states["C%d" % i] == "INELIGIBLE" for i in range(1, 4)) and states["A1P"] == "INELIGIBLE"
    rec = {r["ticker"]: r for r in S.cross_section(rows(), SIGNAL)}
    assert rec["C1"]["ineligibility"] == ["INDUSTRY_BELOW_MIN_MEMBERS"] and rec["A1P"]["ineligibility"] == ["PREFERRED_SHARE"]
    assert rec["A6"]["valuePercentile"] == pytest.approx(11 / 12) and rec["A6"]["industryMembers"] == 6  # the preferred share is not a member


def test_cross_section_is_independent_of_input_order():
    shuffled = rows()
    random.Random(7).shuffle(shuffled)
    assert C.canonical(S.cross_section(shuffled, SIGNAL)) == C.canonical(S.cross_section(rows(), SIGNAL))


def test_a_rank_depends_only_on_the_same_industry_on_the_same_date():
    base = {r["ticker"]: r["valuePercentile"] for r in S.cross_section(rows(), SIGNAL)}
    moved = rows()
    for r in moved:
        if r["industry"] == "INDUSTRY_B":
            r["bookToMarketProxy"] *= 100
    after = {r["ticker"]: r["valuePercentile"] for r in S.cross_section(moved, SIGNAL)}
    assert all(after[t] == base[t] for t in base if t.startswith("A"))


def test_missing_is_never_negative_and_never_cheap():
    data = rows()
    data[5]["earningsYieldProxy"] = None                       # A6 loses one value input
    states = {r["ticker"]: r["state"] for r in S.cross_section(data, SIGNAL)}
    assert states["A6"] == "MISSING_VALUE_INPUT"
    assert states["B6"] == "CHEAP_CONFIRMATION_UNMEASURED"     # never folded into CHEAP_UNCONFIRMED


def test_ineligibility_reasons_are_signal_time_facts():
    data = rows()
    data[0].update(positiveVolumeSessions20=19)
    data[1].update(medianTradedValue60Krw=S.MIN_MEDIAN_TRADED_VALUE_KRW - 1)
    data[2].update(priceAsOf="2026-10-15")
    data[3].update(industry=None)
    rec = {r["ticker"]: r for r in S.cross_section(data, SIGNAL)}
    assert rec["A1"]["ineligibility"] == ["NOT_TRADED_EVERY_SESSION_20"] and rec["A2"]["ineligibility"] == ["BELOW_LIQUIDITY_FLOOR"]
    assert rec["A3"]["ineligibility"] == ["PRICE_NOT_ON_SIGNAL_DATE"] and rec["A4"]["ineligibility"] == ["INDUSTRY_UNCLASSIFIED"]


def test_design_digest_is_reproducible_and_moves_with_any_constant(monkeypatch):
    first = S.design_digest()
    assert first == S.design_digest() and C.is_sha256(first)
    monkeypatch.setattr(S, "CHEAP_PERCENTILE", 0.7)
    assert S.design_digest() != first


def test_the_liquidity_floor_and_costs_are_derived_not_chosen():
    config = json.loads((ROOT / "config.json").read_text())["kellyPortfolio"]
    kr = config["transactionCosts"]["KR"]
    assert S.EXPECTED_TRADE_NOTIONAL_KRW == kr["expectedTradeNotionalKrw"]
    assert S.MIN_MEDIAN_TRADED_VALUE_KRW == kr["expectedTradeNotionalKrw"] / S.MAX_SHARE_OF_MEDIAN_TRADED_VALUE
    assert S.STOCK_COSTS_BPS == {"buy": kr["commissionBps"] + kr["spreadBps"] / 2, "sell": kr["commissionBps"] + kr["sellTaxBps"] + kr["spreadBps"] / 2}
    assert S.MAX_NAMES_PER_INDUSTRY == config["selection"]["maxNamesPerSector"]
    assert S.MIN_MEASURED_SHARE == config["probabilityCalibration"]["integrity"]["minPitCoverage"]
    from pipeline import switch_hurdle
    assert S.SE_MULTIPLE == switch_hurdle.SE_MULTIPLE


# --------------------------------------------------------------------------- #
# Leakage refusals
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("field", ["forwardReturn126", "excessReturn", "label", "nextReturn", "close"])
def test_a_column_outside_the_input_contract_refuses_the_cross_section(field):
    data = rows()
    data[0][field] = 0.1
    with pytest.raises(ValueError, match="ROW_FIELD_NOT_IN_INPUT_CONTRACT"):
        S.cross_section(data, SIGNAL)


def test_information_dated_after_the_signal_refuses_the_cross_section():
    data = rows()
    data[0]["fundamentalsAvailableFrom"] = "2026-10-19"
    with pytest.raises(ValueError, match="FUNDAMENTALS_AVAILABLE_AFTER_SIGNAL_DATE"):
        S.cross_section(data, SIGNAL)
    data = rows()
    data[0]["priceAsOf"] = "2026-10-19"
    with pytest.raises(ValueError, match="PRICE_AFTER_SIGNAL_DATE"):
        S.cross_section(data, SIGNAL)


def test_a_forecast_trained_on_an_unmatured_label_is_refused():
    with pytest.raises(ValueError, match="NOT_AVAILABLE_AT_THE_SIGNAL_DATE"):
        receipt(forecasts=forecasts(trainingTargetLastExitDate=SIGNAL))
    with pytest.raises(ValueError, match="FORECAST_NOT_CALIBRATED"):
        receipt(forecasts=forecasts(calibrationStatus="UNCALIBRATED"))


def test_a_forecast_whose_contributions_do_not_add_up_is_refused():
    bad = forecasts()
    bad["names"]["A6"]["contributions"] = {"withinIndustry": 0.01}
    with pytest.raises(ValueError, match="CONTRIBUTIONS_NOT_ADDITIVE"):
        receipt(forecasts=bad)


def test_an_outcome_key_anywhere_in_a_receipt_fails_validation():
    r = receipt()
    r["signal"][0]["realizedExcess"] = 0.1
    r["receiptSha256"] = C.receipt_digest(r)
    with pytest.raises(ValueError, match="OUTCOME_FIELD_IN_RECEIPT"):
        R.validate_receipt(r)


# --------------------------------------------------------------------------- #
# Decision states
# --------------------------------------------------------------------------- #
def test_without_an_authorized_forecast_the_receipt_is_not_ready_and_holds_nothing():
    r = receipt()
    assert r["decision"]["status"] == "NOT_READY" and r["decision"]["reasons"] == ["NO_AUTHORIZED_CALIBRATED_FORECAST"]
    assert r["decision"]["weights"] is None and r["decision"]["fallbackWeight"] is None and r["forecast"] is None
    assert r["signal"] is not None and r["researchOnly"] is True and r["productionEffect"] == "NONE"


def test_coverage_below_the_floor_blocks_with_no_signal_and_no_weights():
    data = rows()
    for row in data:
        row["ocfImprovementToAssets"] = None
    r = receipt(rows=data, forecasts=forecasts())
    assert r["decision"]["status"] == "BLOCKED" and "CONFIRMATION_COVERAGE_BELOW_FLOOR" in r["decision"]["reasons"]
    assert r["signal"] is None and r["forecast"] is None and r["decision"]["weights"] is None and r["decision"]["candidates"] == []
    assert r["coverage"]["confirmationMeasured"] == 0 and r["coverage"]["cheap"] == 4   # the share travels with its denominator


def test_a_blocked_receipt_that_is_edited_to_carry_weights_is_refused():
    data = rows()
    for row in data:
        row["ocfImprovementToAssets"] = None
    r = receipt(rows=data)
    r["decision"]["weights"] = {"A6": 0.2}
    r["receiptSha256"] = C.receipt_digest(r)
    with pytest.raises(ValueError, match="NON_ACTIONABLE_RECEIPT_CARRIES_A_DECISION"):
        R.validate_receipt(r)


def test_names_enter_only_when_the_forecast_clears_cost_and_uncertainty():
    r = receipt(forecasts=forecasts())
    assert r["decision"]["status"] == "CANDIDATE_PORTFOLIO" and r["decision"]["weights"] == {"A6": 0.2, "B5": 0.2}
    assert r["decision"]["fallback"] == "PASSIVE_BENCHMARK" and r["decision"]["fallbackWeight"] == pytest.approx(0.6)
    assert r["trainingCutoff"] == "2026-04-01"


def test_zero_names_is_a_valid_answer_and_the_book_stays_in_the_fallback():
    low = forecasts()
    for f in low["names"].values():
        f["expectedExcessReturn"] = 0.012
        f["contributions"] = {"withinIndustry": 0.012}
    r = receipt(forecasts=low)
    assert r["decision"]["status"] == "NO_ELIGIBLE_OPPORTUNITY" and r["decision"]["weights"] == {} and r["decision"]["fallbackWeight"] == 1.0


def test_an_incumbent_does_not_pay_the_entry_cost_again():
    mid = forecasts()
    for f in mid["names"].values():                 # 0.017 - 0.01 = 0.007 clears the hold bar, not the 0.0072 round trip + SE entry bar
        f["expectedExcessReturn"] = 0.017
        f["contributions"] = {"withinIndustry": 0.017}
    assert receipt(forecasts=mid)["decision"]["weights"] == {}
    assert receipt(forecasts=mid, previous_holdings=("A6",))["decision"]["weights"] == {"A6": 0.2}


def test_cash_and_passive_fallbacks_are_different_policies():
    cash = receipt(forecasts=forecasts(), fallback="CASH")
    passive = receipt(forecasts=forecasts())
    assert cash["decision"]["fallback"] == "CASH" and passive["decision"]["fallback"] == "PASSIVE_BENCHMARK"
    assert cash["costsAssumedBps"]["roundTripUsedForEntry"] < passive["costsAssumedBps"]["roundTripUsedForEntry"]
    assert cash["receiptSha256"] != passive["receiptSha256"]


def test_only_cheap_confirmed_names_can_be_held_and_at_most_two_per_industry():
    many = rows() + [_row("A%d" % i, "INDUSTRY_A", 0.1 * i, 0.01 * i) for i in range(7, 13)]
    names = {t: {"expectedExcessReturn": 0.08, "standardError": 0.01, "contributions": {"x": 0.08}}
             for t in ("A9", "A10", "A11", "A12", "A5")}
    decision = R.build_receipt(rows=many, signal_date=SIGNAL, created_at_utc=CREATED, now_utc=NOW, spec_sha256=SPEC, code_identity=CODE,
                               data_identity=DATA, authorization=AUTH, forecasts=forecasts(names=names))["decision"]
    assert sorted(decision["weights"]) == ["A10", "A11"]       # equal margins break ties by ticker; the industry cap stops at two
    assert {c["ticker"] for c in decision["candidates"]} == {"A9", "A10", "A11", "A12"}  # A5 is no longer cheap and is never a candidate


# --------------------------------------------------------------------------- #
# Identity, timing and the prospective boundary
# --------------------------------------------------------------------------- #
def test_identical_inputs_give_an_identical_receipt():
    assert receipt(forecasts=forecasts()) == receipt(forecasts=forecasts())


@pytest.mark.parametrize("kw,code", [
    ({"spec_sha256": "x"}, "SPEC_IDENTITY_REQUIRED"),
    ({"code_identity": {"commitSha": "c" * 40, "files": {}}}, "CODE_IDENTITY_REQUIRED"),
    ({"data_identity": {"pitFeatureSnapshot": "e" * 64}}, "DATA_SNAPSHOT_IDENTITY_REQUIRED"),
    ({"authorization": dict(AUTH, specSha256="9" * 64)}, "AUTHORIZATION_DOES_NOT_MATCH_THE_SPEC"),
    ({"authorization": None}, "AUTHORIZATION_DOES_NOT_MATCH_THE_SPEC"),
])
def test_a_receipt_without_its_identities_is_refused(kw, code):
    with pytest.raises(ValueError, match=code):
        receipt(**kw)


@pytest.mark.parametrize("created,now,code", [
    ("2026-10-16T06:00:00+00:00", "2026-10-16T06:05:00+00:00", "RECEIPT_CREATED_BEFORE_SIGNAL_CLOSE"),
    ("2026-10-19T00:00:00+00:00", "2026-10-19T00:05:00+00:00", "RECEIPT_CREATED_AFTER_EXECUTION_OPEN_BACKDATED"),
    ("2026-11-02T09:00:00+00:00", "2026-11-02T09:00:00+00:00", "RECEIPT_CREATED_AFTER_EXECUTION_OPEN_BACKDATED"),
    ("2026-10-16T09:00:00+00:00", "2026-10-16T08:00:00+00:00", "RECEIPT_CREATED_IN_THE_FUTURE"),
    ("2026-10-16T09:00:00", "2026-10-16T09:05:00+00:00", "TIMESTAMP_WITHOUT_TIMEZONE"),
])
def test_the_no_backdating_window(created, now, code):
    with pytest.raises(ValueError, match=code):
        receipt(created_at_utc=created, now_utc=now)


def test_the_window_reaches_up_to_the_next_open_across_a_weekend():
    assert receipt(created_at_utc="2026-10-18T23:59:00+00:00", now_utc="2026-10-18T23:59:30+00:00")["executionDate"] == "2026-10-19"


def test_same_day_merge_observations_are_excluded():
    same_day = dict(AUTH, mergedAtUtc="2026-10-16T01:00:00+00:00")   # 10:00 KST, before the close of the signal session
    with pytest.raises(ValueError, match="SIGNAL_BEFORE_PROSPECTIVE_ELIGIBILITY"):
        receipt(authorization=same_day)
    assert C.first_prospective_session("2026-10-16T01:00:00+00:00").strftime("%Y-%m-%d") == "2026-10-19"
    assert C.first_prospective_session("2026-10-16T16:00:00+00:00").strftime("%Y-%m-%d") == "2026-10-19"  # Saturday 01:00 KST


def test_only_weekly_decision_sessions_carry_a_receipt():
    with pytest.raises(ValueError, match="NOT_A_WEEKLY_DECISION_SESSION"):
        receipt(signal_date="2026-10-15", created_at_utc="2026-10-15T09:00:00+00:00", now_utc="2026-10-15T09:01:00+00:00")
    assert C.is_weekly_decision_session("2026-10-08")         # 2026-10-09 is a KR holiday, so Thursday closes that week
    assert not C.is_weekly_decision_session("2026-10-09")


def test_no_authorization_is_registered_so_no_live_receipt_can_be_written():
    assert R.REGISTERED_AUTHORIZATION is None
    with pytest.raises(ValueError, match="KR_ALPHA_SIGNAL_V2_NOT_AUTHORIZED"):
        R.require_registered_authorization()


# --------------------------------------------------------------------------- #
# Append-only ledger
# --------------------------------------------------------------------------- #
def _second():
    return receipt(signal_date="2026-10-23", created_at_utc="2026-10-23T09:00:00+00:00", now_utc="2026-10-23T09:01:00+00:00")


def test_append_refuses_a_duplicate_an_earlier_date_and_a_changed_spec(tmp_path):
    ledger = tmp_path / "receipts.jsonl"
    first = receipt()
    R.append_receipt(ledger, first)
    with pytest.raises(ValueError, match="RECEIPT_ALREADY_EXISTS"):
        R.append_receipt(ledger, receipt(forecasts=forecasts()))
    R.append_receipt(ledger, _second())
    with pytest.raises(ValueError, match="RECEIPT_ALREADY_EXISTS"):
        R.append_receipt(ledger, first)
    other_spec = "3" * 64
    later = receipt(signal_date="2026-10-30", created_at_utc="2026-10-30T09:00:00+00:00", now_utc="2026-10-30T09:01:00+00:00",
                    spec_sha256=other_spec, authorization=dict(AUTH, specSha256=other_spec))
    with pytest.raises(ValueError, match="RECEIPT_SPEC_CHANGED_WITHIN_A_LEDGER"):
        R.append_receipt(ledger, later)
    assert [r["signalDate"] for r in R.read_ledger(ledger)] == [SIGNAL, "2026-10-23"]


def test_append_refuses_out_of_order(tmp_path):
    ledger = tmp_path / "receipts.jsonl"
    R.append_receipt(ledger, _second())
    with pytest.raises(ValueError, match="RECEIPT_OUT_OF_ORDER"):
        R.append_receipt(ledger, receipt())


def test_appending_never_rewrites_existing_bytes_and_a_tampered_row_stops_the_ledger(tmp_path):
    ledger = tmp_path / "receipts.jsonl"
    R.append_receipt(ledger, receipt())
    before = ledger.read_bytes()
    R.append_receipt(ledger, _second())
    assert ledger.read_bytes().startswith(before)
    tampered = ledger.read_text().replace('"A6"', '"Z9"', 1)
    ledger.write_text(tampered)
    with pytest.raises(ValueError, match="RECEIPT_DIGEST_MISMATCH"):
        R.read_ledger(ledger)


# --------------------------------------------------------------------------- #
# Forecasts and outcomes stay apart
# --------------------------------------------------------------------------- #
def test_an_outcome_record_needs_maturity_and_never_touches_the_receipt():
    r = receipt(forecasts=forecasts())
    frozen = copy.deepcopy(r)
    outcomes = {"A6": {"state": "PRICED", "excessReturn": 0.05}, "B5": {"state": "PRICED", "excessReturn": -0.01}}
    with pytest.raises(ValueError, match="HORIZON_NOT_MATURED"):
        R.build_outcome_record(r, horizon=126, as_of="2027-01-15", name_outcomes=outcomes, created_at_utc="2027-01-15T09:00:00+00:00")
    record = R.build_outcome_record(r, horizon=126, as_of="2027-06-30", name_outcomes=outcomes, created_at_utc="2027-06-30T09:00:00+00:00")
    assert r == frozen and record["receiptSha256"] == r["receiptSha256"] and record["evidenceClass"] == "PROSPECTIVE_OUTCOME"
    assert record["portfolio"] == {"status": "COMPLETE", "unresolvedTickers": [], "heldExcessReturn": pytest.approx(0.2 * 0.05 + 0.2 * -0.01)}
    with pytest.raises(ValueError, match="UNREGISTERED_HORIZON"):
        R.build_outcome_record(r, horizon=63, as_of="2027-06-30", name_outcomes=outcomes, created_at_utc="2027-06-30T09:00:00+00:00")


def test_a_held_name_without_terminal_economics_is_never_marked():
    r = receipt(forecasts=forecasts())
    outcomes = {"A6": {"state": "TERMINAL_ECONOMICS_UNRESOLVED", "excessReturn": None}, "B5": {"state": "PRICED", "excessReturn": 0.02}}
    record = R.build_outcome_record(r, horizon=126, as_of="2027-06-30", name_outcomes=outcomes, created_at_utc="2027-06-30T09:00:00+00:00")
    assert record["portfolio"] == {"status": "TERMINAL_ECONOMICS_UNRESOLVED", "unresolvedTickers": ["A6"], "heldExcessReturn": None}
    missing = R.build_outcome_record(r, horizon=126, as_of="2027-06-30", name_outcomes={"B5": outcomes["B5"]},
                                     created_at_utc="2027-06-30T09:00:00+00:00")
    assert missing["portfolio"]["status"] == "NAME_OUTCOME_MISSING" and missing["portfolio"]["heldExcessReturn"] is None


def test_an_outcome_record_cannot_be_built_from_an_altered_receipt():
    r = receipt(forecasts=forecasts())
    r["decision"]["weights"] = {"A6": 0.2}
    with pytest.raises(ValueError):
        R.build_outcome_record(r, horizon=126, as_of="2027-06-30", name_outcomes={}, created_at_utc="2027-06-30T09:00:00+00:00")


# --------------------------------------------------------------------------- #
# Compatibility with the existing receipt infrastructure, and the schema file
# --------------------------------------------------------------------------- #
def test_storage_format_is_byte_compatible_with_the_existing_receipt_modules():
    from pipeline import kr_alpha_tournament_receipts as T
    from pipeline import kr_integrated_alpha_portfolio_receipts as I
    from pipeline import kr_market_risk_model_receipts as M
    payload = {"b": [1, 2.5, None, "한글"], "a": {"z": True, "y": "x"}, "receiptSha256": "ignored"}
    for module in (T, I, M):
        assert module.canonical(payload) == C.canonical(payload)
    assert C.receipt_digest(payload) == T.seal(payload) == I.receipt_digest(payload) == M.receipt_digest(payload)
    assert R.EVIDENCE_CLASS == I.EVIDENCE_CLASS == M.EVIDENCE_CLASS == "PROSPECTIVE_PAPER"
    assert set(I.FORBIDDEN_RECEIPT_KEY_FRAGMENTS) <= set(C.FORBIDDEN_KEY_FRAGMENTS)


def test_receipt_schema_names_exactly_the_contract_fields():
    schema = json.loads((ROOT / "research_specs/kr-alpha-signal-v2-receipt.schema.json").read_text())
    assert sorted(schema["required"]) == sorted(R.REQUIRED + ("receiptSha256",)) == sorted(schema["properties"])
    assert schema["properties"]["decision"]["properties"]["status"]["enum"] == list(R.DECISION_STATES)
    assert sorted(receipt(forecasts=forecasts())) == sorted(schema["properties"])


def test_the_new_modules_import_nothing_from_a_sealed_study():
    import ast
    for name in ("prospective_receipt_core", "kr_alpha_signal_v2", "kr_alpha_signal_v2_receipts"):
        tree = ast.parse((ROOT / "pipeline" / (name + ".py")).read_text())
        local = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.level for a in n.names}
        assert local <= {"replay_calendar", "prospective_receipt_core", "kr_alpha_signal_v2"}, (name, local)
