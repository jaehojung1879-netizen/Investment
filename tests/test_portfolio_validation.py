import json
from pathlib import Path

import pandas as pd

from pipeline import kelly_portfolio as KP
from pipeline import pit_data
from pipeline import portfolio_validation as PV
from pipeline import validate as V


CFG_LT = {
    "minNames": 3, "maxNames": 6,
    "rankBuffer": {"enterPct": 50, "exitPct": 60},
}
CFG_PF = {
    "horizonDays": 126, "shrinkagePriorStrength": 2,
    "minCashPct": 15, "maxPositionWeight": .4, "maxSectorWeight": .8,
    "maxThemeWeight": .8, "regionCaps": {"KR": .8, "US": .8},
    "watchWeightMultiplier": .5, "waitForPullbackWeightMultiplier": .25,
    "selection": {"targetNames": 3, "minNames": 2, "maxNamesPerSector": 2,
                  "maxNamesPerRegion": 3, "minAlphaPercentile": 66,
                  "convictionTiltRange": 1.0},
    "transactionCosts": {
        "US": {"commissionBps": 5, "sellTaxBps": 3, "spreadBps": 10},
        "KR": {"commissionBps": 5, "sellTaxBps": 20, "spreadBps": 12},
    },
    "regimeMultipliers": {
        "Transition/Low confidence": {"kellyMultiplier": .5, "minCashPct": 20},
    },
}


def _candidate(ticker, percentile, region="US", sector="Technology", risk=20):
    return {
        "ticker": ticker, "region": region, "sector": sector,
        "alphaPercentile": percentile, "longTermResearchView": "POSITIVE",
        "dataInsufficient": False, "valueTrap": False, "evidenceCoverage": .8,
        "risk": {"downsideVolPct": risk}, "entryState": "ACCUMULATE_GRADUALLY",
    }


def _outcome(identifier, date, region, ticker, alpha, value, end_date, model="m", replay="r"):
    return {
        "id": identifier, "date": date, "region": region, "ticker": ticker,
        "sector": "Technology", "alphaPercentile": alpha,
        "modelVersion": model, "replayVersion": replay,
        "pit": {"usableForCalibration": True, "pitCoverage": .8},
        "horizons": {"126": {
            "absoluteReturn": value + .01, "benchmarkReturn": .01,
            "excessReturn": value, "costAdjustedExcessReturn": value - .001,
            "endDate": end_date,
        }},
    }


def test_shared_portfolio_decision_matches_production_functions():
    candidates = [_candidate("A", 99), _candidate("B", 95), _candidate("C", 90)]
    macro = {"regime": "Transition/Low confidence", "confidence": .5}
    shared = KP.selection_and_baseline(candidates, CFG_PF, macro)
    local = dict(CFG_PF, minCashPct=20)
    selected, meta = KP.select_portfolio(candidates, local)
    weights = KP.baseline_weights(selected, local, ranking_rows=meta["ranking"])

    assert [row["ticker"] for row in shared["selected"]] == [row["ticker"] for row in selected]
    assert shared["weights"] == {key: round(value, 6) for key, value in weights.items()}
    assert shared["cashPct"] >= 20


def test_input_order_cannot_change_champion_or_challenger_portfolio():
    candidates = [_candidate("A", 99), _candidate("B", 95), _candidate("C", 90)]
    scores = [{"ticker": c["ticker"], "region": c["region"], "sector": c["sector"],
               "score": score, "eligible": True, "exclusionCodes": []}
              for c, score in zip(candidates, [3, 2, 1])]
    first = KP.selection_and_baseline(candidates, CFG_PF)
    second = KP.selection_and_baseline(list(reversed(candidates)), CFG_PF)
    ch1 = KP.selection_and_baseline(candidates, CFG_PF, scored=scores, method=PV.CHALLENGER)
    ch2 = KP.selection_and_baseline(list(reversed(candidates)), CFG_PF,
                                    scored=list(reversed(scores)), method=PV.CHALLENGER)
    assert first["weights"] == second["weights"]
    assert ch1["weights"] == ch2["weights"]


def test_challenger_calibration_uses_only_labels_matured_by_replay_date():
    outcomes = [
        _outcome("old", "2020-01-02", "US", "A", 97, .10, "2020-07-01"),
        _outcome("future", "2020-02-02", "US", "B", 97, -.90, "2021-01-01"),
    ]
    cal = PV.ExpandingBucketCalibration(outcomes, horizon=126, prior_strength=1, min_dates=1)
    cal.advance("2020-08-01")
    before = cal.expected("US", 97)
    assert before["rawMeanExcessReturnPct"] == 9.9  # cost-adjusted old row only
    cal.advance("2021-02-01")
    after = cal.expected("US", 97)
    assert after["rawMeanExcessReturnPct"] < before["rawMeanExcessReturnPct"]


def test_generation_filter_never_pools_model_or_replay_versions():
    rows = [
        {"id": "ok", "modelVersion": "m", "replayVersion": "r"},
        {"id": "old-model", "modelVersion": "old", "replayVersion": "r"},
        {"id": "old-replay", "modelVersion": "m", "replayVersion": "old"},
    ]
    kept, rejected = PV._generation_filter(rows, replay_version="r", model_version="m")
    assert [row["id"] for row in kept] == ["ok"]
    assert rejected == 2


def test_rank_ic_is_computed_inside_date_and_region_not_on_pooled_rows():
    signals = []
    outcomes = []
    for region, sign in (("US", 1), ("KR", -1)):
        for idx in range(6):
            identifier = f"{region}-{idx}"
            signals.append({"id": identifier, "factorPercentiles": {
                "momentum": idx * 10, "lowvol": idx * 10,
                "value": None, "quality": None}})
            outcomes.append(_outcome(identifier, "2020-01-02", region, identifier,
                                     idx * 10, sign * idx / 100, "2020-07-01"))
    diag = PV.alpha_diagnostics(signals, outcomes)
    assert diag["regions"]["US:126"]["rankIC"]["mean"] == 1.0
    assert diag["regions"]["KR:126"]["rankIC"]["mean"] == -1.0
    assert "POOLED:126" not in diag["regions"]
    assert diag["poolingPolicy"] == "DATE_X_REGION_ONLY; KR_US_NEVER_POOLED"


def test_full_live_factor_attribution_is_withheld_without_pit_fundamentals():
    signals = []
    outcomes = []
    for idx in range(6):
        identifier = f"US-{idx}"
        signals.append({"id": identifier, "factorPercentiles": {
            "momentum": idx * 10, "lowvol": idx * 10,
            "value": idx * 10, "quality": idx * 10}})
        outcomes.append(_outcome(identifier, "2020-01-02", "US", identifier,
                                 idx * 10, idx / 100, "2020-07-01"))
    withheld = PV.alpha_diagnostics(signals, outcomes, pit_fundamentals=False)
    ready = PV.alpha_diagnostics(signals, outcomes, pit_fundamentals=True)
    assert withheld["factorAttribution"]["US:126"]["fullComposite"]["claimEligible"] is False
    assert ready["factorAttribution"]["US:126"]["fullComposite"]["claimEligible"] is True


def test_overlapping_forward_returns_are_not_chained_as_sequential_nav():
    rows = [
        {"date": "2020-01-02", "endDate": "2020-07-01", "costAdjustedReturn": .10,
         "benchmarkReturn": 0, "costAdjustedExcessReturn": .10, "turnover": .1,
         "top1": .3, "top3": .8, "effectiveNames": 3},
        {"date": "2020-02-03", "endDate": "2020-08-03", "costAdjustedReturn": .10,
         "benchmarkReturn": 0, "costAdjustedExcessReturn": .10, "turnover": .1,
         "top1": .3, "top3": .8, "effectiveNames": 3},
        {"date": "2020-07-02", "endDate": "2021-01-04", "costAdjustedReturn": .10,
         "benchmarkReturn": 0, "costAdjustedExcessReturn": .10, "turnover": .1,
         "top1": .3, "top3": .8, "effectiveNames": 3},
    ]
    for row in rows:
        row["weights"] = {"A": .8}
        row["regionByTicker"] = {"A": "US"}
        row["grossReturn"] = row["costAdjustedReturn"]
        row["grossExcessReturn"] = row["costAdjustedExcessReturn"]
    no_cost = dict(CFG_PF, transactionCosts={"US": {}})
    path = PV._path_metrics(rows, 126, no_cost)
    assert path["periods"] == 2
    assert path["nav"][-1]["nav"] == 1.21


def test_turnover_and_transaction_cost_use_actual_weight_changes():
    candidates = [_candidate("A", 99, "US"), _candidate("B", 95, "KR")]
    detail = PV._turnover_cost({"A": .4, "B": .2}, {"A": .2, "B": .3},
                               candidates, CFG_PF)
    assert detail["buys"] == .2
    assert round(detail["sells"], 10) == .1
    assert round(detail["turnover"], 10) == .2  # stock changes plus cash change
    assert detail["cost"] > 0


def test_missing_historical_constituents_fails_integrity_and_promotion():
    result = PV.data_integrity({"survivorshipRisk": "HIGH", "fundamentalsPit": False,
                                "macroPitStatus": "REVISED_HISTORY"},
                               [{"region": "US"}, {"region": "KR"}])
    assert result["historicalUniverseAvailable"] is False
    assert result["integrityGate"]["eligible"] is False
    assert result["historicalResultLabel"] == "SURVIVORSHIP_BIAS_UNRESOLVED"
    assert result["impactOnPromotionEligibility"] == "KELLY_AND_SELECTOR_PROMOTION_BLOCKED"


def test_pit_fundamental_contract_blocks_publication_date_leakage(tmp_path):
    path = tmp_path / "fundamentals.jsonl"
    path.write_text(json.dumps({
        "ticker": "A", "fiscalPeriod": "2020Q1", "reportDate": "2020-03-31",
        "publicationDate": "2020-05-10", "availableFrom": "2020-05-11",
        "currency": "USD", "trailingPE": 10, "source": "filing",
        "sourceAsOf": "2020-05-11", "revisionStatus": "ORIGINAL",
    }) + "\n", encoding="utf-8")
    store = pit_data.FundamentalStore.from_jsonl(path)
    assert store.visible_as_of("A", "2020-05-10")[0] == {}
    fields, status = store.visible_as_of("A", "2020-05-11")
    assert fields["earningsYield"] == .1
    assert status == pit_data.PIT_EXACT
    assert store.diagnostics["rowsRejected"] == 0


def test_pit_contract_rejects_available_from_before_publication(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text(json.dumps({
        "ticker": "A", "fiscalPeriod": "2020Q1", "reportDate": "2020-03-31",
        "publicationDate": "2020-05-10", "availableFrom": "2020-05-01",
        "source": "filing",
    }) + "\n", encoding="utf-8")
    store = pit_data.FundamentalStore.from_jsonl(path)
    assert not store.available
    assert store.diagnostics["rowsRejected"] == 1


def test_pit_contract_accepts_named_roe_and_fcf_fields_without_backfill(tmp_path):
    path = tmp_path / "aliases.jsonl"
    path.write_text(json.dumps({
        "ticker": "A", "fiscalPeriod": "2020Q1", "reportDate": "2020-03-31",
        "publicationDate": "2020-05-10", "availableFrom": "2020-05-11",
        "currency": "USD", "ROE": .2, "FCF": 100, "source": "filing",
        "sourceAsOf": "2020-05-11", "revisionStatus": "ORIGINAL",
    }) + "\n", encoding="utf-8")
    store = pit_data.FundamentalStore.from_jsonl(path)
    fields, _ = store.visible_as_of("A", "2020-05-11")
    assert fields["roe"] == .2 and fields["fcf"] == 100
    assert store.visible_as_of("A", "2020-05-10")[0] == {}


def test_frontend_keeps_historical_and_prospective_gaps_visibly_separate():
    app = Path("app.js").read_text(encoding="utf-8")
    for text in ("Historical OOS audit gap", "Prospective paper gap",
                 "NOT_YET_MATURED", "Historical와 prospective를 하나의 성과로 합산하지 않습니다"):
        assert text in app


def test_frontend_shows_effective_sample_and_price_sleeve_limitation():
    app = Path("app.js").read_text(encoding="utf-8")
    assert "유효독립" in app and "HAC lag 125" in app
    assert "PRICE_SLEEVES_ONLY_AUDIT_PROXY" in app
    assert "Value/Quality" in app


def test_challenger_never_changes_production_selector():
    assert KP.SELECTION_METHOD == "ALPHA_RANK_PER_DOWNSIDE_RISK"
    app = Path("app.js").read_text(encoding="utf-8")
    assert "Champion" in app and "Challenger" in app
    assert "production" in KP.challenger_selection.__doc__


def test_validator_rejects_full_fidelity_or_promotion_without_integrity(tmp_path):
    payload = {
        "historicalValidation": {
            "evidenceClass": "HISTORICAL_OOS",
            "portfolioReplay": {"fullProductionFidelity": True,
                                "promotionEvidence": {"promotionEligible": True,
                                                      "humanApprovalRequired": True}},
            "dataIntegrity": {"historicalUniverseAvailable": False,
                              "pitFundamentals": {"available": False},
                              "integrityGate": {"eligible": False}},
        },
        "prospectiveValidation": {"evidenceClass": "PROSPECTIVE_PAPER"},
    }
    path = tmp_path / "artifact.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    errors = V.validate(path)
    assert "full_fidelity_claim_without_pit_inputs" in errors
    assert "selector_promotion_without_integrity_gate" in errors
    assert "automatic_selector_promotion_forbidden" in errors


def test_validator_rejects_fake_zero_prospective_gap_before_126d_maturity(tmp_path):
    payload = {
        "historicalValidation": {"evidenceClass": "HISTORICAL_OOS"},
        "prospectiveValidation": {
            "evidenceClass": "PROSPECTIVE_PAPER", "trackingDays": 10,
            "maturedObservationDays": 0, "maturedByHorizon": {"126": 0},
            "forecastGap": {"status": "AVAILABLE", "ece": 0.0},
        },
    }
    path = tmp_path / "artifact.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert "prospective_126d_gap_fabricated_before_maturity" in V.validate(path)
