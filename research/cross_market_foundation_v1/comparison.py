"""Outcome-free P0--P5 input contract; only an explicitly synthetic scorer exists.

This implements the *proposed*, unregistered hierarchy comparison (§7), not an
execution authorization. No files, ledgers, network endpoints or outcome panels
are opened here. Existing receipt hashing/outcome exclusion and regional trading
calendars are reused. Validation of a provenance declaration is not admission of
its underlying source, ownership rights, or a study's execution permission.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import math

import pandas as pd

from pipeline import prospective_receipt_core as receipts
from pipeline import replay_calendar as calendar

CONTRACT = "hierarchical-vs-direct-selection-comparison-v1"
PATHS = ("P0", "P1", "P2", "P3", "P4", "P5")
SCORE_KINDS = {"P0": "ETF", "P1": "STOCK_MARKET", "P2": "INDUSTRY",
               "P3": "INDUSTRY_THEN_STOCK", "P4": "STOCK_WITHIN_INDUSTRY",
               "P5": "FIXED_UNIT_ADDITIVE"}
INPUT_ROLES = {"universe", "industry", "stock", "classification", "prices", "actions", "costs", "execution", "calendar"}
COST_COMPONENTS = {"commissionBps", "spreadBps", "slippageBps", "taxBps"}
TOLERANCE = 1e-9


def digest(value):
    return hashlib.sha256(receipts.canonical(value)).hexdigest()


def _require(condition, code):
    if not condition:
        raise ValueError(code)


def _finite(value):
    return receipts.finite(value)


def _validate_cost_model(model):
    _require(isinstance(model, dict) and model.get("basis") == "SELF_FINANCING_ENTRY_AND_TERMINAL_LIQUIDATION"
             and model.get("returnInputBasis") == "GROSS_BEFORE_TRANSACTION_COSTS"
             and model.get("interimTrades") is False
             and model.get("switchCostRule") == "FOUR_ACTUAL_LEGS_SHARED_TARIFF_NO_EXTRA_SURCHARGE", "SHARED_EXECUTION_COST_MODEL_REQUIRED")
    tariff = model.get("tariff", {})
    _require(set(tariff) == {"STOCK", "ETF"} and all(set(sides) == {"BUY", "SELL"} for sides in tariff.values()), "COMMON_INSTRUMENT_SIDE_TARIFF_REQUIRED")
    for sides in tariff.values():
        for charges in sides.values():
            _require(set(charges) == COST_COMPONENTS and all(_finite(v) and 0 <= v <= 10000 for v in charges.values())
                     and math.fsum(charges.values()) < 10000, "EXPLICIT_COMPLETE_COST_COMPONENTS_REQUIRED")
    _require(_date(model["validFrom"]) <= _date(model["validThrough"]), "TARIFF_VALIDITY_PERIOD_REQUIRED")


def price_execution_legs(common, legs, *, stress=1):
    """One shared tariff prices actual legs; no per-model costs are accepted.

    Notionals are in units of INITIAL NAV, not current portfolio weights. A
    stock→ETF→stock round trip has four ordinary legs, without a second switch
    surcharge. The caller must supply actual leg identities, sides and dates;
    this function is not a fill simulator or a source of real execution proof.
    """
    model = common["costModel"]
    _validate_cost_model(model)
    _require(type(stress) is int and stress in (1, 2, 3), "COMMON_COST_STRESS_REQUIRED")
    _require(isinstance(legs, list) and len({leg.get("legId") for leg in legs}) == len(legs)
             and all(isinstance(leg.get("legId"), str) and leg["legId"] for leg in legs), "UNIQUE_EXECUTION_LEGS_REQUIRED")
    priced = []
    for leg in legs:
        _require(leg.get("security") in set(common["universe"]) | {common["benchmarkTicker"]}
                 and leg.get("side") in ("BUY", "SELL")
                 and _finite(leg.get("notionalFractionOfInitialNav")) and leg["notionalFractionOfInitialNav"] >= 0, "EXECUTION_LEG_INVALID")
        _require(_date(model["validFrom"]) <= _date(leg["session"]) <= _date(model["validThrough"]), "EXECUTION_OUTSIDE_TARIFF_VALIDITY")
        kind = "ETF" if leg["security"] == common["benchmarkTicker"] else "STOCK"
        charges = {k: leg["notionalFractionOfInitialNav"] * bps * stress / 10000
                   for k, bps in model["tariff"][kind][leg["side"]].items()}
        priced.append({"legId": leg["legId"], "chargesFractionOfInitialNav": charges,
                       "totalCostFractionOfInitialNav": math.fsum(charges.values())})
    return {"legs": priced, "totalCostFractionOfInitialNav": math.fsum(r["totalCostFractionOfInitialNav"] for r in priced)}


def _date(value):
    day = pd.Timestamp(value)
    _require(day.tzinfo is None and day == day.normalize(), "SESSION_LABEL_REQUIRED")
    return day


def _session_bounds(region, day):
    if region == "KR":
        return day.tz_localize("UTC"), (day + receipts.KR_CLOSE_FINAL_UTC).tz_localize("UTC")
    import exchange_calendars as xc
    exchange = xc.get_calendar("XNYS", start="1990-01-01", end="2035-12-31")
    return exchange.session_open(day), exchange.session_close(day)


def _next_execution(region, signal):
    days = calendar.sessions(str(signal.date()), str((signal + pd.Timedelta(days=20)).date()), region)
    _require(len(days) >= 2 and days[0] == signal, "SIGNAL_NOT_REGIONAL_SESSION")
    return days[1]


def maturity_status(region, execution_date, horizon_sessions, as_of_utc):
    """Calendar maturity only; never invents a performance value for a pending block.

    Execution is session zero. US early closes and DST come from XNYS, KR final
    close uses the existing conservative receipt convention (09:00 UTC).
    """
    _require(region in ("KR", "US"), "REGION_REQUIRED")
    _require(type(horizon_sessions) is int and horizon_sessions in (126, 252), "HORIZON_NOT_H126_H252")
    execution = _date(execution_date)
    days = calendar.sessions(str(execution.date()), str((execution + pd.Timedelta(days=2 * horizon_sessions + 40)).date()), region)
    _require(len(days) > horizon_sessions and days[0] == execution, "EXECUTION_NOT_REGIONAL_SESSION")
    maturity = days[horizon_sessions]
    close = _session_bounds(region, maturity)[1]
    return {"horizonSessions": horizon_sessions, "maturitySession": str(maturity.date()),
            "maturityCloseUtc": close.isoformat(), "calendarVersion": calendar.CALENDAR_VERSION,
            "status": "MATURED" if receipts.utc(as_of_utc) >= close else "OBSERVATION_INCOMPLETE",
            "performance": None}


def _validate_common(common):
    receipts.scan_for_outcome_keys(common)
    _require(common.get("region") in ("KR", "US"), "REGION_REQUIRED")
    region = common["region"]
    benchmark = "069500.KS" if region == "KR" else "SPY"
    _require(common.get("benchmarkTicker") == benchmark, "REGIONAL_PRIMARY_ETF_REQUIRED")
    _require(common.get("currency") == ("KRW" if region == "KR" else "USD"), "LOCAL_CURRENCY_REQUIRED_NO_FX_MIX")
    _require(common.get("evidenceClass") in ("SYNTHETIC", "OUTCOME_EXPOSED_EXPLORATORY", "PROSPECTIVE_PAPER"), "EVIDENCE_CLASS_REQUIRED")
    _require(common.get("marketRiskMultiplier") == 1 and not isinstance(common.get("marketRiskMultiplier"), bool), "MARKET_MULTIPLIER_MUST_BE_ONE")
    signal = _date(common["signalDate"])
    execution = _next_execution(region, signal)
    _require(common.get("executionDate") == str(execution.date()), "EXECUTION_NOT_NEXT_REGIONAL_SESSION")
    signal_close = _session_bounds(region, signal)[1]
    decision = receipts.utc(common["decisionAtUtc"])
    _require(signal_close <= decision < _session_bounds(region, execution)[0], "DECISION_OUTSIDE_NO_BACKDATING_WINDOW")
    _require(receipts.utc(common["informationCutoffUtc"]) == signal_close, "COMMON_SIGNAL_CLOSE_CUTOFF_REQUIRED")
    _require(common.get("benchmarkStartDate") == common["executionDate"], "ETF_START_DATE_MISMATCH")
    _require(common.get("calendarVersion") == calendar.CALENDAR_VERSION, "CALENDAR_VERSION_MISMATCH")
    universe = common.get("universe", [])
    _require(isinstance(universe, list) and universe and all(isinstance(t, str) and t for t in universe)
             and universe == sorted(set(universe)) and benchmark not in universe, "UNIVERSE_MUST_BE_UNIQUE_SORTED_STOCK_IDS")
    industries = common.get("securityIndustries", {})
    _require(set(industries) == set(universe) and all(isinstance(i, str) and i for i in industries.values()), "COMMON_CLASSIFIED_UNIVERSE_REQUIRED")
    _require(common.get("missingnessPolicy") == "PRESEALED_COMMON_UNIVERSE_NO_POSTHOC_DROP", "SYMMETRIC_MISSINGNESS_POLICY_REQUIRED")
    basis = common.get("returnBasis", {})
    _require(basis == {"kind": "TOTAL_RETURN", "dividends": "REINVESTED_ON_EX_DATE", "splits": "ADJUSTED_ONCE",
                       "terminal": "CITED_CONSIDERATION_OR_BLOCK", "currency": common["currency"]}, "TOTAL_RETURN_BASIS_INCOMPLETE")
    inputs = common.get("inputEvidence", [])
    _require(isinstance(inputs, list) and len(inputs) == len(INPUT_ROLES)
             and {r.get("role") for r in inputs} == INPUT_ROLES, "ALL_UNIQUE_INPUT_ROLES_REQUIRED")
    for row in inputs:
        _require(receipts.is_sha256(row.get("sha256")) and receipts.is_sha256(row.get("payloadSha256"))
                 and receipts.is_git_sha(row.get("sourceCommit")), "INPUT_CONTENT_AND_SOURCE_IDENTITY_REQUIRED")
        _require(receipts.utc(row["availableAtUtc"]) <= signal_close
                 and receipts.utc(row["vintageAsOfUtc"]) <= signal_close, "FUTURE_OR_REVISED_INPUT_NOT_PIT")
        _require(row.get("rightsStatus") in ("VERIFIED_FOR_RESEARCH", "SYNTHETIC_ONLY"), "INPUT_RIGHTS_BLOCKED")
        _require(row.get("pitStatus") == "VERIFIED", "INPUT_PIT_NOT_VERIFIED")
        if common["evidenceClass"] != "SYNTHETIC":
            _require(row["rightsStatus"] == "VERIFIED_FOR_RESEARCH", "SYNTHETIC_SOURCE_IN_REAL_PLAN")
    for key in ("industryQualificationSha256", "stockQualificationSha256", "costPolicySha256", "executionPolicySha256", "scoreCombinationSha256"):
        _require(receipts.is_sha256(common.get(key)), "BLOCKED_NO_QUALIFIED_INPUT_OR_POLICY_" + key)
    risk = common.get("riskPolicy", {})
    _require(type(risk.get("maximumStockNames")) is int and risk["maximumStockNames"] > 0
             and all(_finite(risk.get(k)) and 0 < risk[k] <= 1 for k in ("maximumNameWeight", "maximumIndustryWeight")), "RISK_POLICY_REQUIRED")
    benchmark_weights = common.get("benchmarkIndustryWeights", {})
    _require(set(benchmark_weights) == set(industries.values())
             and all(_finite(w) and w > 0 for w in benchmark_weights.values())
             and math.isclose(math.fsum(benchmark_weights.values()), 1, abs_tol=TOLERANCE), "ETF_INDUSTRY_HISTORY_REQUIRED")
    caps = common.get("signalCapitalizations", {})
    _require(set(caps) == set(universe) and all(_finite(v) and v > 0 for v in caps.values()), "SIGNAL_CAPITALIZATIONS_REQUIRED")
    _require(common.get("costStressMultipliers") == [1, 2, 3], "COMMON_COST_STRESSES_REQUIRED")
    _validate_cost_model(common.get("costModel"))
    _require(common["costPolicySha256"] == digest(common["costModel"]), "COST_POLICY_CONTENT_HASH_MISMATCH")


def _industry_weights(weights, common):
    out = {i: weights.get(common["benchmarkTicker"], 0) * w for i, w in common["benchmarkIndustryWeights"].items()}
    for ticker, weight in weights.items():
        if ticker != common["benchmarkTicker"]:
            industry = common["securityIndustries"][ticker]
            out[industry] += weight
    return out


def prepare_comparison(common, paths):
    """Validate sealed inputs and targets; returns a non-deployable, outcome-free plan.

    Qualification hashes are references for an independent verifier, not proof
    of scientific admission. This API cannot authorize or evaluate any study.
    It rejects the complete paired block on a deficient path; it never creates
    actionable fallback weights for a blocked research artifact.
    """
    common, paths = deepcopy(common), deepcopy(paths)
    _validate_common(common)
    receipts.scan_for_outcome_keys(paths)
    _require(isinstance(paths, list) and len(paths) == 6 and {p.get("path") for p in paths} == set(PATHS), "ALL_SIX_UNIQUE_PATHS_REQUIRED")
    common_sha = digest(common)
    by_path = {p["path"]: p for p in paths}
    for label in PATHS:
        row = by_path[label]
        _require(row.get("commonSha256") == common_sha and row.get("universe") == common["universe"], "PATH_COMMON_INPUT_OR_UNIVERSE_MISMATCH")
        _require(row.get("scoreKind") == SCORE_KINDS[label], "PATH_SCORE_CONTRACT_MISMATCH")
        weights = row.get("weights", {})
        _require(isinstance(weights, dict) and weights and set(weights) <= set(common["universe"]) | {common["benchmarkTicker"]}
                 and all(_finite(w) and w > 0 for w in weights.values()) and math.isclose(math.fsum(weights.values()), 1, abs_tol=TOLERANCE), "FULLY_FUNDED_LONG_ONLY_WEIGHTS_REQUIRED")
        if label == "P0":
            _require(weights == {common["benchmarkTicker"]: 1}, "P0_MUST_BE_ETF_100")
            continue
        stocks = {t: w for t, w in weights.items() if t != common["benchmarkTicker"]}
        risk = common["riskPolicy"]
        _require(len(stocks) <= risk["maximumStockNames"] and all(w <= risk["maximumNameWeight"] + TOLERANCE for w in stocks.values()), "NAME_CONCENTRATION_LIMIT_EXCEEDED")
        industry_weights = _industry_weights(weights, common)
        _require(all(w <= risk["maximumIndustryWeight"] + TOLERANCE for w in industry_weights.values()), "INDUSTRY_CONCENTRATION_LIMIT_EXCEEDED")
        if label in ("P2", "P3"):
            selected = row.get("selectedIndustries", [])
            _require(isinstance(selected, list) and selected and len(selected) == len(set(selected))
                     and set(selected) <= set(common["benchmarkIndustryWeights"])
                     and all(common["securityIndustries"][t] in selected for t in stocks), "INDUSTRY_SELECTION_SCOPE_MISMATCH")
            if label == "P2":
                members = {t: c for t, c in common["signalCapitalizations"].items() if common["securityIndustries"][t] in selected}
                cap_total = math.fsum(members.values())
                _require(set(stocks) == set(members) and common["benchmarkTicker"] not in weights
                         and all(math.isclose(stocks[t], c / cap_total, abs_tol=TOLERANCE) for t, c in members.items()), "P2_NOT_SIGNAL_DATE_FIXED_CAP_BASKET")
        if label == "P4":
            _require(all(math.isclose(industry_weights[i], w, abs_tol=TOLERANCE) for i, w in common["benchmarkIndustryWeights"].items()), "P4_NOT_INDUSTRY_NEUTRAL")
    plan = {"contract": CONTRACT, "schemaVersion": 1, "executionEnabled": False, "deployable": False,
            "sourceAdmission": "DECLARATIONS_ONLY_INDEPENDENT_SOURCE_VERIFICATION_REQUIRED",
            "common": common, "paths": [by_path[p] for p in PATHS], "commonSha256": common_sha}
    plan["planSha256"] = digest(plan)
    return plan


def read_operational_receipt(receipt, *, expected_sha256):
    """Thin read-only adapter: verify bytes, retain identities, never infer source PIT.

    A code/sourceCommit alone is not the content identity of market payloads.
    It returns no target, verdict, performance, ledger write, or admission.
    """
    row = deepcopy(receipt)
    receipts.scan_for_outcome_keys(row)
    _require(receipts.is_sha256(expected_sha256) and row.get("receiptSha256") == expected_sha256
             and receipts.receipt_digest(row) == expected_sha256, "OPERATIONAL_RECEIPT_DIGEST_MISMATCH")
    identities = row.get("inputIdentities")
    _require(isinstance(identities, dict) and identities
             and all(receipts.is_sha256(v) for v in identities.values()), "OPERATIONAL_PAYLOAD_IDENTITIES_REQUIRED")
    return {"receiptSha256": expected_sha256, "signalDate": row.get("signalDate"),
            "executionDate": row.get("executionDate"), "inputIdentities": identities,
            "sourceAdmission": "NOT_INFERRED_FROM_CODE_COMMIT", "readOnly": True}


def read_portfolio_d_receipt(receipt, *, expected_record_sha256):
    """Read a #306 shadow decision without copying its sealed decision codec.

    The external pin is SHA-256 of the WHOLE canonical record (including its
    stored semantic digest and provenance), not the operational ``digest``.
    The latter intentionally excludes some provenance in its owner module.
    This adapter does not validate that semantic identity or PIT eligibility;
    callers must use the pinned operational owner's validator for admission.
    """
    row = deepcopy(receipt)
    _require(row.get("schema") == "ENTRY_STATE_SHADOW_DECISION_V1"
             and receipts.is_sha256(expected_record_sha256) and digest(row) == expected_record_sha256,
             "PORTFOLIO_D_WHOLE_RECORD_HASH_MISMATCH")
    hashes = row.get("sourceHashes")
    _require(isinstance(hashes, dict) and hashes and all(receipts.is_sha256(v) for v in hashes.values())
             and receipts.is_sha256(row.get("observationSha256"))
             and receipts.is_sha256(row.get("sourceArtifactSha256")), "PORTFOLIO_D_PAYLOAD_IDENTITIES_REQUIRED")
    _require(receipts.is_sha256(row.get("digest")) and receipts.is_sha256(row.get("receiptId")), "PORTFOLIO_D_DECISION_IDENTITIES_REQUIRED")
    return {"recordSha256": expected_record_sha256, "storedDecisionDigest": row["digest"], "receiptId": row["receiptId"],
            "signalDate": row.get("asOfDate"), "executionDate": row.get("executionSession"), "region": row.get("region"),
            "sourceHashes": hashes, "observationSha256": row["observationSha256"],
            "sourceArtifactSha256": row["sourceArtifactSha256"], "readOnly": True,
            "sourceAdmission": "NOT_INFERRED_FROM_CODE_COMMIT", "requiresOwningSemanticValidator": True}


def score_synthetic_fixture(plan, block):
    """Test arithmetic on an explicit synthetic joint block; REAL inputs refused.

    No price fetch, actual historical panel runner, model ranking or research
    verdict is implemented. The shared tariff determines self-financing entry
    funding and terminal liquidation costs from each path's actual notional;
    gross total returns must exclude transaction costs. ETF uses identical
    endpoints. Interim rebalances and overlapping-block annualization are absent.
    """
    _require(plan.get("common", {}).get("evidenceClass") == "SYNTHETIC"
             and isinstance(block.get("fixtureId"), str) and block["fixtureId"].startswith("synthetic:"), "REAL_OUTCOME_EXECUTION_PROHIBITED")
    body = {k: v for k, v in plan.items() if k != "planSha256"}
    _require(plan.get("planSha256") == digest(body), "PLAN_DIGEST_MISMATCH")
    rebuilt = prepare_comparison(plan["common"], plan["paths"])
    _require(rebuilt == plan and block.get("planSha256") == plan["planSha256"], "BLOCK_PLAN_IDENTITY_MISMATCH")
    common = plan["common"]
    _require(block.get("costPolicySha256") == common["costPolicySha256"]
             and block.get("executionPolicySha256") == common["executionPolicySha256"], "BLOCK_COST_OR_EXECUTION_POLICY_MISMATCH")
    _require("costsByPath" not in block and "tariffsByPath" not in block, "PATH_SPECIFIC_COST_OVERRIDE_PROHIBITED")
    maturity = maturity_status(common["region"], common["executionDate"], block["horizonSessions"], block["asOfUtc"])
    _require(maturity["status"] == "MATURED", "HORIZON_OBSERVATION_INCOMPLETE")
    rows = block.get("securityObservations", [])
    _require(isinstance(rows, list) and all(isinstance(r, dict) for r in rows)
             and len({r.get("security") for r in rows}) == len(rows), "DUPLICATE_SECURITY_OBSERVATION")
    observations = {r.get("security"): r for r in rows}
    needed = {t for p in plan["paths"] for t in p["weights"]}
    _require(needed <= set(observations), "NOT_EVALUABLE_BLOCKED_PATH_MISSING_PRICE")
    for ticker in needed:
        row = observations[ticker]
        _require(row.get("fixtureId") == block["fixtureId"] and row.get("dataKind") == "SYNTHETIC", "REAL_OUTCOME_EXECUTION_PROHIBITED")
        _require(row.get("entrySession") == common["executionDate"] and row.get("exitSession") == maturity["maturitySession"], "ETF_OR_SECURITY_ENDPOINT_MISMATCH")
        _require(row.get("returnBasisSha256") == digest(common["returnBasis"]) and row.get("currency") == common["currency"], "RETURN_BASIS_OR_CURRENCY_MISMATCH")
        _require(row.get("returnCostBasis") == "GROSS_BEFORE_TRANSACTION_COSTS", "ALREADY_NET_RETURN_DOUBLE_COST_PROHIBITED")
        _require(row.get("terminalStatus") in ("NOT_TERMINATED", "CITED_CONSIDERATION")
                 and (row["terminalStatus"] != "CITED_CONSIDERATION" or receipts.is_sha256(row.get("terminalEvidenceSha256"))), "NOT_EVALUABLE_BLOCKED_PATH_TERMINAL_UNRESOLVED")
        _require(receipts.utc(maturity["maturityCloseUtc"]) <= receipts.utc(row["availableAtUtc"])
                 <= receipts.utc(block["asOfUtc"]), "FUTURE_OBSERVATION_LEAK")
        _require(_finite(row.get("totalReturn")) and row["totalReturn"] >= -1, "VALID_TOTAL_RETURN_REQUIRED")
        _require(row["totalReturn"] != -1 or row["terminalStatus"] == "CITED_CONSIDERATION",
                 "TOTAL_LOSS_REQUIRES_CITED_TERMINAL")
    results = []
    for stress in common["costStressMultipliers"]:
        # This kernel reads positions and costs only; route labels never select
        # a pricing, missingness, return or execution branch.
        net, fees = {}, {}
        for row in plan["paths"]:
            buy = [{"legId": "entry:" + t, "security": t, "side": "BUY", "session": common["executionDate"],
                    "notionalFractionOfInitialNav": w} for t, w in sorted(row["weights"].items())]
            coefficient = price_execution_legs(common, buy, stress=stress)["totalCostFractionOfInitialNav"]
            funded = 1 / (1 + coefficient)
            for leg in buy:
                leg["notionalFractionOfInitialNav"] *= funded
            exit_legs = [{"legId": "exit:" + t, "security": t, "side": "SELL", "session": maturity["maturitySession"],
                          "notionalFractionOfInitialNav": funded * w * (1 + observations[t]["totalReturn"])}
                         for t, w in sorted(row["weights"].items())]
            priced = price_execution_legs(common, buy + exit_legs, stress=stress)
            sell_cost = math.fsum(r["totalCostFractionOfInitialNav"] for r in priced["legs"] if r["legId"].startswith("exit:"))
            final_gross_nav = math.fsum(leg["notionalFractionOfInitialNav"] for leg in exit_legs)
            net[row["path"]] = final_gross_nav - sell_cost - 1
            fees[row["path"]] = {"entryFundedFraction": funded, **priced}
        results.append({"costStress": stress, "netReturns": net, "modeledFees": fees,
                        "excessVsRegionalEtf": {p: v - net["P0"] for p, v in net.items()}})
    return {"fixtureId": block["fixtureId"], "evidenceClass": "SYNTHETIC_NOT_RESEARCH_EVIDENCE",
            "deployable": False, "planSha256": plan["planSha256"], "maturity": maturity, "scenarios": results}
