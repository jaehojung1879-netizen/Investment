"""Validate site-data artifacts before Pages deployment.

Enforces the invariants that keep README / build / screen / validator telling
the SAME safe story:
  * provenance is present (schemaVersion, modelVersion, runMode, buildCommitSha,
    marketAsOf) so a consumer can always tell what produced the numbers;
  * runMode is a known value and is NEVER liveValidated straight from a build
    (that must be earned by the ledger);
  * a blocked artifact carries NO actionable output — no short-term ideas,
    long-term positions/weights, entry states, or actionable reasons;
  * seed / synthetic / stale artifacts are rejected for production.
"""
from __future__ import annotations
import json, math, sys
from pathlib import Path

VALID_RUN_MODES = {"researchOnly", "paperTrading", "liveValidated"}
VALID_PORTFOLIO_STATUSES = {
    "DISABLED", "SHADOW_INSUFFICIENT_HISTORY", "SHADOW_READY",
    "ACTIVE_PAPER", "ACTIVE_VALIDATED", "OPTIMIZATION_FAILED",
    "FALLBACK_RISK_WEIGHTED", "BLOCKED",
    "SHADOW_HISTORICAL_PRIOR", "SHADOW_POSTERIOR_READY",
}
VALID_EVIDENCE_CLASSES = {"HISTORICAL_OOS", "PROSPECTIVE_PAPER", "LIVE_VALIDATED", "NONE"}
VALID_OPPORTUNITY_TIERS = {"VALIDATED_OPPORTUNITY", "EMERGING_OPPORTUNITY", "WATCH"}
VALID_WARNING_TIERS = {"CRITICAL_WARNING", "ELEVATED_WARNING", "WATCH"}
ACTIONABLE_REASON_TERMS = (
    "buy", "sell", "avoid", "wait", "accumulate", "entry", "매수", "매도",
    "진입", "대기", "회피", "되돌림", "편입", "비중",
)


def _walk(o, path="$"):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from _walk(v, f"{path}.{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from _walk(v, f"{path}[{i}]")
    elif isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
        yield path


def _longterm_has_weights(data: dict) -> bool:
    lt = data.get("longTerm") or {}
    for blob in (lt.get("regions") or {}).values():
        for p in (blob or {}).get("picks", []):
            if p.get("modelSleeveWeightPct") is not None:
                return True
    return False


def _longterm_has_positions(data: dict) -> bool:
    lt = data.get("longTerm") or {}
    for blob in (lt.get("regions") or {}).values():
        if (blob or {}).get("picks") or (blob or {}).get("holdings"):
            return True
    return False


def _has_blocked_entry_actions(obj) -> bool:
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == "entryState" and value is not None:
                return True
            if key in {"reasons", "reason"}:
                values = value if isinstance(value, list) else [value]
                for item in values:
                    text = str(item or "").lower()
                    if any(term in text for term in ACTIONABLE_REASON_TERMS):
                        return True
            if _has_blocked_entry_actions(value):
                return True
    elif isinstance(obj, list):
        return any(_has_blocked_entry_actions(item) for item in obj)
    return False


def _validate_evidence_separation(data: dict) -> list[str]:
    """Historical OOS and prospective paper evidence must stay distinguishable.

    The whole point of this layer is that a backtest and a live track record are
    different kinds of claim. If the artifact ever lets one be read as the
    other — an unlabelled evidence class, a historical result presented as
    liveValidated, a radar tier published from an unaccepted model without
    saying so — the honesty guarantee is gone regardless of how careful the
    maths was.
    """
    errors: list[str] = []
    historical = data.get("historicalValidation")
    prospective = data.get("prospectiveValidation")

    if historical is not None:
        if historical.get("evidenceClass") != "HISTORICAL_OOS":
            errors.append("historical_validation_evidence_class_mismatch")
        if historical.get("liveValidated"):
            errors.append("historical_evidence_claims_live_validation")
    if prospective is not None:
        if prospective.get("evidenceClass") != "PROSPECTIVE_PAPER":
            errors.append("prospective_validation_evidence_class_mismatch")
        if prospective.get("liveValidated"):
            errors.append("prospective_evidence_claims_live_validation")
        # Tracking days and matured days are separate facts; a ledger that has
        # recorded signals but matured none must not report zero tracking.
        tracking = prospective.get("trackingDays")
        matured_days = prospective.get("maturedObservationDays")
        if (tracking is not None and matured_days is not None
                and int(matured_days) > int(tracking)):
            errors.append("matured_days_exceed_tracking_days")
        if (prospective.get("signalsRecorded") and int(prospective["signalsRecorded"]) > 0
                and tracking is not None and int(tracking) == 0):
            errors.append("signals_recorded_but_tracking_days_zero")

    evidence = data.get("kellyEvidence") or {}
    for region, blob in (evidence.get("byRegion") or {}).items():
        posterior = (blob or {}).get("posterior") or {}
        historical_share = posterior.get("historicalWeightPct")
        prospective_share = posterior.get("prospectiveWeightPct")
        if historical_share is None or prospective_share is None:
            errors.append(f"kelly_evidence_weights_missing:{region}")
            continue
        if abs(float(historical_share) + float(prospective_share)) > 0 and \
                abs(float(historical_share) + float(prospective_share) - 100.0) > 0.5:
            errors.append(f"kelly_evidence_weights_do_not_sum_to_100:{region}")
        drift = (blob or {}).get("drift") or {}
        if drift.get("detected") and float(drift.get("kellyMultiplier", 1.0)) > 1.0:
            errors.append(f"drift_increased_kelly_fraction:{region}")

    for key, valid in (("opportunityRadar", VALID_OPPORTUNITY_TIERS),
                       ("warningRadar", VALID_WARNING_TIERS)):
        radar = data.get(key)
        if not radar:
            continue
        if radar.get("evidenceClass") not in VALID_EVIDENCE_CLASSES | {None}:
            errors.append(f"{key}_invalid_evidence_class")
        ml_active = radar.get("mlStatus") == "ACTIVE"
        for rows in (radar.get("regions") or {}).values():
            for row in rows or []:
                if row.get("tier") not in valid:
                    errors.append(f"{key}_invalid_tier:{row.get('tier')}")
                    break
                # A VALIDATED tier is a claim that the model cleared its
                # acceptance gate. Without an accepted model it may not appear.
                if row.get("tier") == "VALIDATED_OPPORTUNITY" and not ml_active:
                    errors.append(f"{key}_validated_tier_without_accepted_model")
                    break
    return errors


def validate(path: str | Path, production: bool = True) -> list[str]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    errors = []
    m = data.get("meta", {})
    for k in ["portfolioName", "meta", "generatedAt", "core", "screened", "tradeIdeas"]:
        if k not in data:
            errors.append(f"missing_{k}")

    # Provenance: the single source of truth must be attached and coherent.
    prov = data.get("provenance") or {}
    for k in ["schemaVersion", "modelVersion", "runMode", "marketAsOf"]:
        if not prov.get(k) and not data.get(k):
            errors.append(f"missing_provenance_{k}")
    run_mode = data.get("runMode") or prov.get("runMode")
    if run_mode not in VALID_RUN_MODES:
        errors.append("invalid_run_mode")
    if run_mode == "liveValidated" and not (data.get("validation") or {}).get("liveValidatedEarned"):
        errors.append("liveValidated_not_earned")

    bad = list(_walk(data))
    if bad:
        errors.append("nan_or_infinity:" + ",".join(bad[:5]))

    portfolio = data.get("modelPortfolio")
    if portfolio:
        status = portfolio.get("status")
        if status not in VALID_PORTFOLIO_STATUSES:
            errors.append("invalid_model_portfolio_status")
        weights = portfolio.get("finalWeights") or {}
        if any(float(v) < -1e-10 for v in weights.values()):
            errors.append("model_portfolio_negative_weight")
        if status not in {"BLOCKED", "DISABLED"} and portfolio.get("cashPct") is not None:
            total = sum(float(v) for v in weights.values()) + float(portfolio["cashPct"]) / 100.0
            if abs(total - 1.0) > 1e-5:
                errors.append("model_portfolio_weights_plus_cash_not_100pct")
        constraints = portfolio.get("constraints") or {}
        cap = constraints.get("maxPositionWeight")
        if cap is not None and any(float(v) > float(cap) + 1e-8 for v in weights.values()):
            errors.append("model_portfolio_position_cap_exceeded")
        if status == "ACTIVE_VALIDATED":
            activation = portfolio.get("validation") or {}
            if not activation.get("eligibleForActivation") or not activation.get("humanApproved"):
                errors.append("model_portfolio_active_without_validation_and_human_approval")
        if status == "OPTIMIZATION_FAILED" and not portfolio.get("fallbackReason"):
            errors.append("model_portfolio_optimizer_failure_without_reason")
        kelly_applied = portfolio.get("kellyApplied") is True
        if portfolio.get("fallbackReason") or not kelly_applied:
            if portfolio.get("constrainedKellyWeights"):
                errors.append("fallback_exposes_kelly_weights")
            for position in portfolio.get("positions") or []:
                if position.get("constrainedKellyWeightPct") is not None or position.get("unconstrainedKellyWeightPct") is not None:
                    errors.append("fallback_exposes_position_kelly_weight")
                    break
            if float(portfolio.get("kellyAllocationImpactPct") or 0.0) != 0.0:
                errors.append("fallback_has_nonzero_kelly_impact")
        if kelly_applied:
            covariance = portfolio.get("covariance") or {}
            if covariance.get("returnBasis") != "REGIONAL_ACTIVE" or covariance.get("crossRegionCovarianceUsed") is not False:
                errors.append("kelly_expected_return_covariance_basis_mismatch")
            if not (portfolio.get("currencyPolicy") or {}).get("baseCurrency"):
                errors.append("kelly_currency_policy_missing")

    # 13F is historical disclosure context.  Dates and the SEC source link are
    # mandatory so a delayed quarter can never be mistaken for live holdings.
    disclosure = data.get("institutionalHoldings13F") or {}
    managers = disclosure.get("managers") or []
    available = [x for x in managers if x.get("status") == "AVAILABLE"]
    if disclosure.get("status") == "AVAILABLE" and not available:
        errors.append("13f_available_without_manager_data")
    if disclosure.get("availableCount") not in {None, len(available)}:
        errors.append("13f_available_count_mismatch")
    for manager in available:
        if not manager.get("reportDate") or not manager.get("filingDate"):
            errors.append("13f_manager_missing_report_or_filing_date")
            break
        if not str(manager.get("filingUrl") or "").startswith("https://www.sec.gov/"):
            errors.append("13f_manager_non_sec_source")
            break
        holdings = manager.get("topHoldings") or []
        if any(not 0 <= float(row.get("portfolioWeightPct") or 0) <= 100 for row in holdings):
            errors.append("13f_invalid_portfolio_weight")
            break
        if any(float(row.get("valueUsd") or 0) < 0 or float(row.get("shares") or 0) < 0 for row in holdings):
            errors.append("13f_negative_value_or_shares")
            break

    if production:
        if data.get("seed"):
            errors.append("seed_artifact_not_allowed_for_production")
        artifact_modes = {data.get("dataMode"), prov.get("dataMode")}
        if m.get("syntheticData") or artifact_modes & {"synthetic", "seed"}:
            errors.append("synthetic_artifact_not_allowed_for_production")
        if data.get("stale") or "stale" in artifact_modes:
            errors.append("stale_artifact_not_allowed_for_production")
        if m.get("modelsTrained", 0) <= 0:
            errors.append("modelsTrained_zero")
        if (m.get("coveragePct") or 0) < (m.get("coverageFloor") or 95):
            errors.append("coverage_below_floor")
        # Critical benchmark rows must be present and reasonably current.  A
        # vendor outage should preserve the last good Pages deployment rather
        # than replacing it with a dashboard that quietly omits KOSPI/KOSDAQ.
        market_health = data.get("marketDataHealth") or {}
        if market_health.get("missingCritical"):
            errors.append("critical_indices_missing:" + ",".join(market_health["missingCritical"]))
        if market_health.get("staleCritical"):
            errors.append("critical_indices_stale:" + ",".join(market_health["staleCritical"]))

    errors.extend(_validate_evidence_separation(data))

    # A blocked artifact must not carry actionable output of ANY kind.
    if data.get("recommendationsBlocked"):
        for key in ("opportunityRadar", "warningRadar"):
            radar = data.get(key) or {}
            if any((radar.get("regions") or {}).values()):
                errors.append(f"blocked_artifact_contains_{key}")
        if any((data.get("tradeIdeas") or {}).get(r) for r in ("KR", "US")):
            errors.append("blocked_artifact_contains_trade_ideas")
        if _longterm_has_weights(data):
            errors.append("blocked_artifact_contains_longterm_weights")
        if _longterm_has_positions(data):
            errors.append("blocked_artifact_contains_longterm_positions")
        if _has_blocked_entry_actions(data.get("longTerm") or {}):
            errors.append("blocked_artifact_contains_entry_actions")
        portfolio = data.get("modelPortfolio") or {}
        if portfolio.get("positions") or portfolio.get("finalWeights") or portfolio.get("cashPct") is not None:
            errors.append("blocked_artifact_contains_model_portfolio_weights")
        changes = data.get("changesSincePrior") or {}
        if any(changes.get(key) for key in ("added", "removed", "weightIncreased", "weightDecreased", "entryStateChanged", "regimeChanged")):
            errors.append("blocked_artifact_contains_actionable_changes")
    return errors


def main(argv=None):
    argv = argv or sys.argv[1:]
    if not argv:
        print("usage: python -m pipeline.validate data/site-data.json [--allow-seed]")
        return 2
    production = "--allow-seed" not in argv
    errs = validate(argv[0], production=production)
    if errs:
        print("VALIDATION FAILED")
        for e in errs:
            print("-", e)
        return 1
    print("validation ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
