"""Artifact and UI contracts for the two evidence classes.

The single failure this file exists to prevent: a reader looking at the
dashboard and coming away believing a backtest was a live track record. Every
assertion below is about that boundary staying legible — in the payload, in the
validator, and on screen.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline import evidence as EV
from pipeline import ledger as LG
from pipeline import provenance as prov_mod
from pipeline import validate as V

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "app.js").read_text(encoding="utf-8")
HTML = (ROOT / "index.html").read_text(encoding="utf-8")
CSS = (ROOT / "styles.css").read_text(encoding="utf-8")
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


def _write(tmp_path, payload) -> str:
    path = tmp_path / "artifact.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return str(path)


def _base_payload(**overrides) -> dict:
    payload = {
        "portfolioName": "t", "meta": {"modelsTrained": 1, "coveragePct": 100,
                                       "coverageFloor": 95, "latestDataDate": "2026-01-02"},
        "generatedAt": "2026-01-02T00:00:00Z", "core": [], "screened": [],
        "tradeIdeas": {"KR": [], "US": []}, "runMode": "paperTrading",
        "dataMode": "live", "schemaVersion": prov_mod.SCHEMA_VERSION,
        "modelVersion": prov_mod.MODEL_VERSION,
        "provenance": {"schemaVersion": prov_mod.SCHEMA_VERSION,
                       "modelVersion": prov_mod.MODEL_VERSION,
                       "runMode": "paperTrading", "marketAsOf": "2026-01-02",
                       "dataMode": "live"},
        "marketDataHealth": {"missingCritical": [], "staleCritical": []},
        "recommendationsBlocked": False,
    }
    payload.update(overrides)
    return payload


# --------------------------------------------------------------------------- #
# Schema
# --------------------------------------------------------------------------- #
def test_schema_version_was_raised_for_the_new_evidence_sections():
    assert prov_mod.SCHEMA_VERSION == "2.5.0"
    assert prov_mod.REPLAY_VERSION and prov_mod.FEATURE_VERSION and prov_mod.DATA_VERSION


def test_provenance_stamps_the_replay_and_feature_versions():
    payload = {"meta": {"latestDataDate": "2026-01-02"}}
    provenance = prov_mod.stamp(payload, "paperTrading")
    for key in ("replayVersion", "featureVersion", "dataVersion"):
        assert provenance[key]
    from pipeline import historical_replay as replay
    assert replay.REPLAY_VERSION == prov_mod.REPLAY_VERSION
    assert replay.FEATURE_VERSION == prov_mod.FEATURE_VERSION


def test_config_carries_the_new_blocks_with_a_sealed_holdout():
    assert CONFIG["historicalReplay"]["enabled"] is True
    assert CONFIG["evidence"]["priorScalePct"] > 0
    assert CONFIG["opportunity"]["finalHoldoutStart"]
    acceptance = CONFIG["opportunity"]["acceptance"]
    for key in ("minDecileMonotonicity", "minTopBucketNetExcessPct", "minPitCoverage",
                "maxRegimeSharePct", "maxSectorSharePct"):
        assert key in acceptance


# --------------------------------------------------------------------------- #
# Validator
# --------------------------------------------------------------------------- #
def test_validator_rejects_historical_evidence_labelled_as_live(tmp_path):
    payload = _base_payload(historicalValidation={
        "evidenceClass": "PROSPECTIVE_PAPER", "available": True})
    assert "historical_validation_evidence_class_mismatch" in V.validate(_write(tmp_path, payload))

    payload = _base_payload(historicalValidation={
        "evidenceClass": "HISTORICAL_OOS", "available": True, "liveValidated": True})
    assert "historical_evidence_claims_live_validation" in V.validate(_write(tmp_path, payload))


def test_validator_rejects_signals_recorded_with_zero_tracking_days(tmp_path):
    """The exact bug this work fixes: a ledger full of signals reporting 0 days."""
    payload = _base_payload(prospectiveValidation={
        "evidenceClass": "PROSPECTIVE_PAPER", "trackingDays": 0,
        "signalsRecorded": 4200, "maturedObservationDays": 0})
    assert "signals_recorded_but_tracking_days_zero" in V.validate(_write(tmp_path, payload))


def test_validator_rejects_matured_days_exceeding_tracking_days(tmp_path):
    payload = _base_payload(prospectiveValidation={
        "evidenceClass": "PROSPECTIVE_PAPER", "trackingDays": 100,
        "signalsRecorded": 10, "maturedObservationDays": 400})
    assert "matured_days_exceed_tracking_days" in V.validate(_write(tmp_path, payload))


def test_validator_rejects_mixed_prospective_model_generation(tmp_path):
    payload = _base_payload(prospectiveValidation={
        "evidenceClass": "PROSPECTIVE_PAPER", "trackingDays": 1,
        "maturedObservationDays": 0, "modelVersion": "old-model",
        "generationIsolated": False,
    })
    errors = V.validate(_write(tmp_path, payload))
    assert "prospective_model_generation_mismatch" in errors
    assert "prospective_model_generations_not_isolated" in errors


def test_validator_rejects_evidence_weights_that_do_not_sum_to_100(tmp_path):
    payload = _base_payload(kellyEvidence={"byRegion": {"US": {
        "posterior": {"historicalWeightPct": 80.0, "prospectiveWeightPct": 40.0}}}})
    errors = V.validate(_write(tmp_path, payload))
    assert any(e.startswith("kelly_evidence_weights_do_not_sum_to_100") for e in errors)


def test_validator_rejects_drift_that_increases_the_kelly_fraction(tmp_path):
    payload = _base_payload(kellyEvidence={"byRegion": {"US": {
        "posterior": {"historicalWeightPct": 100.0, "prospectiveWeightPct": 0.0},
        "drift": {"detected": True, "kellyMultiplier": 1.4}}}})
    errors = V.validate(_write(tmp_path, payload))
    assert any(e.startswith("drift_increased_kelly_fraction") for e in errors)


def test_validator_rejects_kelly_when_probability_audit_failed(tmp_path):
    payload = _base_payload(modelPortfolio={
        "status": "SHADOW_READY", "finalWeights": {"AAA": 0.5}, "cashPct": 50,
        "kellyApplied": True, "constrainedKellyWeights": {"AAA": 0.5},
        "kellyAllocationImpactPct": 1.0,
        "constraints": {"maxPositionWeight": 0.8},
        "covariance": {"returnBasis": "REGIONAL_ACTIVE", "crossRegionCovarianceUsed": False},
        "currencyPolicy": {"baseCurrency": "KRW"},
        "probabilityGate": {"requiredForKelly": True, "eligible": False},
        "positions": [],
    })
    assert "kelly_applied_without_reliable_probability_calibration" in \
        V.validate(_write(tmp_path, payload), production=False)


def test_validator_rejects_a_validated_tier_without_an_accepted_model(tmp_path):
    payload = _base_payload(opportunityRadar={
        "mlStatus": "NOT_TRAINED", "evidenceClass": "NONE",
        "regions": {"US": [{"ticker": "AAA", "tier": "VALIDATED_OPPORTUNITY"}]}})
    errors = V.validate(_write(tmp_path, payload))
    assert "opportunityRadar_validated_tier_without_accepted_model" in errors


def test_validator_rejects_radar_output_in_a_blocked_artifact(tmp_path):
    payload = _base_payload(
        recommendationsBlocked=True,
        opportunityRadar={"mlStatus": "ACTIVE", "evidenceClass": "HISTORICAL_OOS",
                          "regions": {"US": [{"ticker": "AAA", "tier": "WATCH"}]}})
    errors = V.validate(_write(tmp_path, payload))
    assert "blocked_artifact_contains_opportunityRadar" in errors


def test_validator_accepts_a_well_formed_evidence_block(tmp_path):
    payload = _base_payload(
        historicalValidation={"evidenceClass": "HISTORICAL_OOS", "available": True},
        prospectiveValidation={"evidenceClass": "PROSPECTIVE_PAPER", "trackingDays": 120,
                               "signalsRecorded": 900, "maturedObservationDays": 40},
        kellyEvidence={"byRegion": {"US": {
            "posterior": {"historicalWeightPct": 100.0, "prospectiveWeightPct": 0.0},
            "drift": {"detected": False, "kellyMultiplier": 1.0}}}},
        opportunityRadar={"mlStatus": "NOT_TRAINED", "evidenceClass": "NONE",
                          "regions": {"US": [{"ticker": "AAA", "tier": "EMERGING_OPPORTUNITY"}]}},
        warningRadar={"mlStatus": "NOT_TRAINED", "evidenceClass": "NONE",
                      "regions": {"US": [{"ticker": "BBB", "tier": "ELEVATED_WARNING"}]}})
    assert V.validate(_write(tmp_path, payload), production=False) == []


def test_new_kelly_statuses_are_accepted_by_the_validator():
    assert "SHADOW_HISTORICAL_PRIOR" in V.VALID_PORTFOLIO_STATUSES
    from pipeline import kelly_portfolio as KP
    assert V.VALID_PORTFOLIO_STATUSES >= KP.STATUSES


# --------------------------------------------------------------------------- #
# Prospective ledger: tracking vs maturity
# --------------------------------------------------------------------------- #
def test_tracking_days_are_reported_before_any_signal_matures():
    signals = [{"id": f"s{i}", "date": d.strftime("%Y-%m-%d"), "ticker": "A"}
               for i, d in enumerate(__import__("pandas").bdate_range("2026-01-02", periods=60))]
    status = LG.validation_status([], min_paper_days=252, signals=signals)
    assert status["signalsRecorded"] == 60
    assert status["trackingDays"] >= 60
    assert status["paperDays"] == status["trackingDays"]
    assert status["maturedSignals"] == 0
    assert status["maturedObservationDays"] == 0
    assert status["evidenceClass"] == "PROSPECTIVE_PAPER"
    assert status["liveValidated"] is False


# --------------------------------------------------------------------------- #
# UI contract
# --------------------------------------------------------------------------- #
def test_dashboard_has_the_radar_and_validation_lab_sections():
    for element_id in ("radar", "opportunityRadarPanel", "warningRadarPanel",
                       "validationLab", "validationLabPanel"):
        assert f'id="{element_id}"' in HTML
    # Core Portfolio comes first; the radar is a separate layer after it.
    assert HTML.index('id="holdingsPanel"') < HTML.index('id="opportunityRadarPanel"')
    assert HTML.index('id="opportunityRadarPanel"') < HTML.index('id="ltKR"')
    assert "renderRadar" in APP and "renderValidationLab" in APP


def test_ui_labels_historical_and_prospective_evidence_separately():
    assert "HISTORICAL_OOS" in APP and "PROSPECTIVE_PAPER" in APP
    assert "과거 OOS" in APP and "실시간" in APP
    # Both panels exist and are rendered from their own payload sections.
    assert "d.historicalValidation" in APP and "d.prospectiveValidation" in APP
    assert "historicalWeightPct" in APP and "prospectiveWeightPct" in APP


def test_ui_shows_tracking_days_and_matured_days_as_separate_rows():
    assert "'추적 일수'" in APP and "'만기 관측 일수'" in APP
    assert "pv.trackingDays" in APP and "pv.maturedObservationDays" in APP
    assert "신호가 쌓인 기간 — 만기 여부와 무관" in APP


def test_ui_translates_the_activation_ladder_into_plain_korean():
    for code, label in EV.ACTIVATION_KO.items():
        assert code in APP, code
        assert label in APP, label


def test_ui_never_presents_analogues_as_a_guarantee():
    import re
    assert "보장하지 않습니다" in APP
    assert "과거 유사 사례" in APP
    # Every occurrence of "보장" (guarantee) must be part of a denial. Searching
    # for the bare word would flag "미래를 보장하지 않습니다", which is the copy we
    # want, so each hit is checked against an explicit allowlist of negations.
    allowed_negations = ("보장하지 않", "보장이 아닙니다", "보장이 아니")
    offenders = [
        APP[m.start():m.start() + 24]
        for m in re.finditer("보장", APP)
        if not any(APP.startswith(ok, m.start()) for ok in allowed_negations)
    ]
    assert not offenders, offenders
    for forbidden in ("반드시 반복", "확실한 수익"):
        assert forbidden not in APP


def test_ui_states_when_the_ml_model_was_not_used():
    for code in ("NOT_TRAINED", "REJECTED_BY_ACCEPTANCE_GATE",
                 "DATASET_INSUFFICIENT_FOR_REFIT", "NO_MODEL_FOR_THIS_RADAR"):
        assert code in APP, code
    assert "규칙 기반 변화 점수 사용" in APP


def test_daily_change_bar_is_transition_based():
    assert "opportunityTransitions" in APP
    assert "신규 기회" in APP and "신규 경고" in APP
    assert "change-alerts" in APP and ".change-alerts" in CSS
    assert "ENTRY_RANK" in APP


def test_radar_and_validation_lab_have_styles():
    for selector in (".radar-card", ".rd-score", ".rd-sig", ".vl-card",
                     ".vl-table", ".vl-chall", ".ca-opp"):
        assert selector in CSS, selector


def test_radar_explanations_state_the_core_separation():
    assert "하나의 점수로 합치지 않습니다" in APP
    assert "validationlab" in APP and "radar" in APP


def test_single_global_disclaimer_is_still_unique():
    assert HTML.count('id="globalDisclaimer"') == 1
    assert APP.count("투자 조언이나 개인화 추천") == 1


# --------------------------------------------------------------------------- #
# Daily change transitions
# --------------------------------------------------------------------------- #
def _transitions(previous_opp, current_opp, previous_warn=None, current_warn=None):
    from pipeline import build as B
    current = {
        "opportunityRadar": {"regions": {"US": [
            {"ticker": t, "tier": tier} for t, tier in (current_opp or {}).items()]}},
        "warningRadar": {"regions": {"US": [
            {"ticker": t, "tier": tier} for t, tier in (current_warn or {}).items()]}},
    }
    prior = {"opportunityTiersByTicker": previous_opp or {},
             "warningTiersByTicker": previous_warn or {}}
    return B._opportunity_transitions(current, prior, {"available": True})


def test_a_tier_that_did_not_change_is_not_re_announced():
    """Yesterday's HIGH must not fire again today, or the alert becomes noise."""
    result = _transitions({"AAA": "VALIDATED_OPPORTUNITY"},
                          {"AAA": "VALIDATED_OPPORTUNITY"})
    assert result["newOpportunities"] == []
    assert result["hasChanges"] is False


def test_a_promotion_is_announced_once():
    result = _transitions({"AAA": "WATCH"}, {"AAA": "EMERGING_OPPORTUNITY"})
    assert result["newOpportunities"] == [
        {"ticker": "AAA", "before": "WATCH", "after": "EMERGING_OPPORTUNITY"}]
    assert result["hasChanges"] is True


def test_a_demotion_is_not_reported_as_a_new_opportunity():
    result = _transitions({"AAA": "VALIDATED_OPPORTUNITY"}, {"AAA": "WATCH"})
    assert result["newOpportunities"] == []
    assert result["resolvedOpportunities"] == [
        {"ticker": "AAA", "before": "VALIDATED_OPPORTUNITY"}]


def test_a_name_that_was_only_ever_watch_is_not_a_resolution():
    """Operator precedence bug guard: `A or B and C` grouped the wrong way here."""
    result = _transitions({"AAA": "WATCH"}, {})
    assert result["resolvedOpportunities"] == []
    assert result["hasChanges"] is False


def test_new_warnings_are_tracked_separately_from_opportunities():
    result = _transitions({}, {}, previous_warn={"BBB": "WATCH"},
                          current_warn={"BBB": "CRITICAL_WARNING"})
    assert result["newWarnings"] == [
        {"ticker": "BBB", "before": "WATCH", "after": "CRITICAL_WARNING"}]
    assert result["newOpportunities"] == []


def test_transitions_are_withheld_without_a_prior_production_state():
    from pipeline import build as B
    result = B._opportunity_transitions({}, {}, {"available": False,
                                                 "reason": "state_file_missing"})
    assert result["available"] is False
    assert result["hasChanges"] is False
