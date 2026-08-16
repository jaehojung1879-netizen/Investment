import copy

import pandas as pd

from pipeline import kelly_portfolio as KP
from pipeline import historical_calibration as HC
from pipeline import probability_calibration as PC


HORIZON = 1


def _outcomes(*, periods=180, labels_mature=True):
    rows = []
    dates = pd.bdate_range("2020-01-02", periods=periods)
    for idx, date in enumerate(dates):
        macro = "Goldilocks" if idx % 2 == 0 else "Stagflation"
        for percentile, bucket in ((97.0, "HIGH"), (85.0, "MID")):
            for name in range(3):
                # The high bucket has a real macro interaction.  The mid bucket
                # supplies a different unconditional base rate.
                won = (macro == "Goldilocks") if bucket == "HIGH" else idx % 5 != 0
                value = 0.04 if won else -0.03
                end = (date + pd.offsets.BDay(HORIZON) if labels_mature
                       else date + pd.offsets.BDay(periods * 3))
                rows.append({
                    "id": f"{idx}-{bucket}-{name}",
                    "date": date.strftime("%Y-%m-%d"),
                    "ticker": f"{bucket}-{name}",
                    "region": "US", "sector": "Technology",
                    "alphaPercentile": percentile,
                    "macroRegime": macro, "entryState": "WATCH",
                    "pit": {"usableForCalibration": True, "pitCoverage": 0.8},
                    "horizons": {str(HORIZON): {
                        "excessReturn": value,
                        "costAdjustedExcessReturn": value,
                        "endDate": end.strftime("%Y-%m-%d"),
                    }},
                })
    return rows


def _cfg():
    return {
        "priorStrength": 5, "payoffPriorStrength": 5,
        "minTrainingDates": 10, "minAuditDates": 20,
        "minIndependentAuditDates": 10, "minConditionDates": 5,
        "selectionFraction": 0.6, "minConditionBrierImprovement": 0.001,
        "maxBrier": 0.30, "maxEce": 0.20, "maxLogLoss": 1.0,
        "minBrierSkill": -0.20,
    }


def test_probability_walk_forward_never_trains_on_unmatured_labels():
    matured = PC.calibrate(_outcomes(labels_mature=True), horizon=HORIZON,
                           cfg=_cfg(), require_pit=True)
    withheld = PC.calibrate(_outcomes(labels_mature=False), horizon=HORIZON,
                            cfg=_cfg(), require_pit=True)

    assert matured["regions"]["US"]["audit"]["predictions"] > 0
    assert matured["regions"]["US"]["labelAvailabilityPolicy"] == \
        "OUTCOME_END_DATE_LTE_PREDICTION_DATE"
    assert withheld["regions"]["US"]["audit"]["predictions"] == 0
    assert withheld["reliabilityGate"]["eligible"] is False


def test_macro_condition_is_used_only_after_separate_audit_passes():
    calibrated = PC.calibrate(_outcomes(), horizon=HORIZON, cfg=_cfg(), require_pit=True)
    region = calibrated["regions"]["US"]

    assert region["selectedVariant"] == "MACRO"
    assert region["reliabilityGate"]["eligible"] is True
    assert region["audit"]["brier"] < region["audit"]["baselineBrier"]

    goldilocks = PC.lookup_distribution(
        calibrated, "US", 97.0, macro_regime="Goldilocks", entry_state="WATCH")
    stagflation = PC.lookup_distribution(
        calibrated, "US", 97.0, macro_regime="Stagflation", entry_state="WATCH")
    assert goldilocks["contextUsed"] == "REGION_ALPHA_BUCKET_MACRO"
    assert stagflation["contextUsed"] == "REGION_ALPHA_BUCKET_MACRO"
    assert goldilocks["upProbabilityPct"] > stagflation["upProbabilityPct"]
    rebuilt = (goldilocks["upProbabilityPct"] / 100 * goldilocks["averageUpsidePct"]
               - goldilocks["downProbabilityPct"] / 100 * goldilocks["averageDownsidePct"])
    assert abs(rebuilt - goldilocks["distributionExpectedExcessReturnPct"]) < 0.03


def test_required_probability_gate_preserves_baseline_when_unreliable():
    candidates = [{"ticker": "A", "region": "US"}]
    reliable = {
        "ticker": "A", "region": "US",
        "probabilityDistribution": {
            "reliabilityEligible": True, "selectedVariant": "BASE",
            "audit": {"brier": 0.22}, "reliabilityGate": {"failures": []},
        },
    }
    passed = KP._probability_gate(
        [reliable], candidates,
        {"probabilityCalibration": {"requiredForKelly": True}})
    assert passed["eligible"] is True

    failed_estimate = copy.deepcopy(reliable)
    failed_estimate["probabilityDistribution"]["reliabilityEligible"] = False
    failed_estimate["probabilityDistribution"]["reliabilityGate"] = {"failures": ["ece"]}
    failed = KP._probability_gate(
        [failed_estimate], candidates,
        {"probabilityCalibration": {"requiredForKelly": True}})
    assert failed["eligible"] is False
    assert failed["byRegion"]["US"]["failures"] == ["ece"]


def test_good_brier_does_not_override_missing_point_in_time_inputs():
    probability_cfg = {
        **_cfg(),
        "integrity": {
            "minPitCoverage": 0.6,
            "requireHistoricalUniverse": True,
            "requirePointInTimeFundamentals": True,
            "requireVintageMacroForConditionalProbability": True,
        },
    }
    calibrated = HC.calibrate(
        _outcomes(), horizon=HORIZON, buckets=[0, 80, 90, 95, 100],
        cfg={"minEffectiveDates": 2, "shrinkagePriorStrength": 2,
             "probabilityCalibration": probability_cfg},
        diagnostics={"meanPitCoverage": 0.8, "survivorshipRisk": "HIGH",
                     "fundamentalsPit": False, "macroPitStatus": "REVISED_HISTORY"},
        cost_adjusted=True, require_pit=True)
    probability = calibrated["probabilityCalibration"]
    assert probability["reliabilityGate"]["statisticalEligible"] is True
    assert probability["integrityGate"]["eligible"] is False
    assert set(probability["integrityGate"]["failures"]) >= {
        "historicalUniverse", "pointInTimeFundamentals",
        "vintageMacroForConditionalProbability",
    }
    assert probability["reliabilityGate"]["eligible"] is False


def test_conditional_variant_must_improve_base_again_in_audit_window():
    cfg = _cfg()
    gate = PC._gate({
        "dates": 100, "independentDates": 100,
        "brier": .22, "baselineBrier": .25, "brierSkill": .12,
        "ece": .05, "logLoss": .60,
        "baseVariantBrier": .21, "conditionalBrierImprovement": -.01,
    }, cfg, selected_variant="MACRO")

    assert gate["eligible"] is False
    assert "conditionalAuditImprovement" in gate["failures"]


def test_one_prediction_date_fails_closed_instead_of_indexing_past_split():
    cfg = {**_cfg(), "minTrainingDates": 0, "minConditionDates": 0}
    calibrated = PC.calibrate(
        _outcomes(periods=1), horizon=HORIZON, cfg=cfg, require_pit=True)

    assert calibrated["regions"]["US"]["reliabilityGate"]["eligible"] is False
