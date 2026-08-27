import json
from pathlib import Path

import pandas as pd

from pipeline import kelly_portfolio as KP
from pipeline import longterm as LT
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


def test_portfolio_outcome_explains_missing_benchmark_instead_of_silent_drop():
    decision = {"date": "2020-01-02", "selector": PV.CHAMPION,
                "weights": {"005930.KS": .8}, "cashPct": 20,
                "transactionCost": 0, "turnover": 0,
                "regionByTicker": {"005930.KS": "KR"}}
    signals = {("2020-01-02", "005930.KS"): {"id": "kr"}}
    outcomes = {"kr": {"horizons": {"126": {
        "absoluteReturn": .1, "benchmarkReturn": None,
        "endDate": "2020-07-01"}}}}

    result, diagnostic = PV._outcome_for_decision_with_diagnostics(
        decision, outcomes, signals, 126)

    assert result is None
    assert diagnostic["reasons"] == ["MISSING_BENCHMARK_RETURN"]
    assert diagnostic["tickersByReason"] == {
        "MISSING_BENCHMARK_RETURN": ["005930.KS"]}
    assert diagnostic["affectedRegions"] == ["KR"]


def test_validation_report_fails_closed_without_current_signals_or_coverage_gate():
    report = PV.build_report(
        [], [], cfg_lt=CFG_LT, cfg_pf=CFG_PF, diagnostics={},
        replay_version="r", model_version="m")
    assert report["contractValidation"]["status"] == "BLOCKED"
    assert report["contractValidation"]["failures"] == [
        "no_current_generation_signals", "benchmark_coverage_gate_not_assessed"]


def test_missing_historical_constituents_fails_integrity_and_promotion():
    result = PV.data_integrity({"survivorshipRisk": "HIGH", "fundamentalsPit": False,
                                "macroPitStatus": "REVISED_HISTORY"},
                               [{"region": "US"}, {"region": "KR"}])
    assert result["historicalUniverseAvailable"] is False
    assert result["integrityGate"]["eligible"] is False
    assert result["historicalResultLabel"] == "SURVIVORSHIP_BIAS_UNRESOLVED"
    assert result["impactOnPromotionEligibility"] == "KELLY_AND_SELECTOR_PROMOTION_BLOCKED"
    assert result["integrityGate"]["checks"]["benchmarkCoverage"] is None
    assert "benchmarkCoverage" in result["integrityGate"]["unassessable"]


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
    assert "유효독립" in app
    # The HAC lag is derived from the replay grid, not fixed at horizon-1: on a
    # weekly grid a 126-session overlap spans ~26 observations. The UI has to
    # say that rather than quoting a lag of 125 it no longer uses.
    assert "HAC lag" in app and "재현 그리드 간격" in app
    assert "HAC lag 125" not in app
    assert "PRICE_SLEEVES_ONLY_AUDIT_PROXY" in app
    assert "Value/Quality" in app


def test_bucket_diagnostics_separate_carry_from_the_ranking_contribution():
    """Every bucket beating the benchmark is not every bucket being good.

    On the production ledger the bottom 60% shows +1.6% to +2.2% against the
    benchmark, which is carry, not a reason to trust the ranking. The panel has
    to show the contribution column or a reader draws the wrong conclusion.
    """
    import numpy as np
    import pandas as pd
    rng = np.random.default_rng(3)
    rows = []
    for date in pd.bdate_range("2015-01-02", periods=80, freq="5B"):
        carry = float(rng.normal(0.025, 0.03))          # the whole universe rises
        for percentile in rng.uniform(0, 100, 50):
            edge = 0.05 if percentile >= 95 else 0.0    # only the top 5% adds
            noise = float(rng.normal(0, 0.04))
            rows.append({
                "date": date, "alphaPercentile": float(percentile),
                "excessReturn": carry + edge + noise,
                "costAdjustedExcessReturn": carry + edge + noise - 0.005,
            })
    buckets, monotonicity = PV._bucket_diagnostics(
        pd.DataFrame(rows), 126, (0, 60, 80, 90, 95, 100))

    by_label = {b["bucket"]: b for b in buckets}
    bottom, top = by_label["0-60"], by_label["95-100"]

    assert monotonicity["universeCarryPct"] > 1.0
    # The bottom bucket looks good against the benchmark and contributes nothing.
    assert bottom["meanCostAdjustedExcessPct"] > 1.0
    assert abs(bottom["costAdjustedSpreadVsUniversePct"]) < 1.0
    # The top bucket's contribution is real and smaller than its raw excess.
    assert top["costAdjustedSpreadVsUniversePct"] > 2.0
    assert top["costAdjustedSpreadVsUniversePct"] < top["meanCostAdjustedExcessPct"]
    assert top["spreadHitRatePct"] > bottom["spreadHitRatePct"]


def test_frontend_shows_the_contribution_column_not_only_benchmark_excess():
    app = Path("app.js").read_text(encoding="utf-8")
    assert "유니버스 캐리" in app
    assert "유니버스 대비(기여)" in app
    assert "하위 버킷도 양수로 보일 수 있습니다" in app


def test_frontend_separates_universe_carry_from_selection_alpha():
    app = Path("app.js").read_text(encoding="utf-8")
    assert "알파 귀속" in app
    assert "유니버스 캐리" in app and "알파 스프레드" in app
    assert "정렬 미확인" in app


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


def _ic_row(mean, ci, effective=140):
    return {"claimEligible": True, "availableObservations": 1000,
            "rankIC": {"mean": mean, "ci95": list(ci), "positiveRate": .4,
                       "effectiveIndependentDates": effective}}


def test_sleeve_contradicting_its_live_weight_at_two_horizons_is_flagged():
    attribution = {
        "US:21": {"lowvol": _ic_row(-.04, (-.07, -.01)),
                  "momentum": _ic_row(.005, (-.017, .027))},
        "US:63": {"lowvol": _ic_row(-.066, (-.113, -.019), 54),
                  "momentum": _ic_row(.008, (-.021, .038), 54)},
    }
    result = PV._sleeve_sign_consistency(attribution)
    assert result["status"] == "CONTRADICTED"
    assert result["contradicted"] == ["US:lowvol"]
    flagged = result["byRegionSleeve"]["US:lowvol"]
    assert flagged["status"] == "CONTRADICTED"
    assert flagged["contradictedHorizons"] == [21, 63]
    # The weight production is actually paying for is reported alongside it.
    assert flagged["liveWeight"] == LT.FACTOR_WEIGHTS["lowvol"]
    assert result["byRegionSleeve"]["US:momentum"]["status"] == "INCONCLUSIVE"


def test_sleeve_sign_check_stays_silent_on_straddling_or_thin_evidence():
    attribution = {
        # Interval contains zero: weak, not contradicting.
        "KR:21": {"lowvol": _ic_row(-.03, (-.07, .01))},
        # Interval is below zero but rests on too few independent dates.
        "KR:63": {"lowvol": _ic_row(-.09, (-.15, -.02), 4)},
        # A sleeve the evidence actually supports.
        "KR:126": {"lowvol": _ic_row(.05, (.02, .08), 27)},
    }
    result = PV._sleeve_sign_consistency(attribution)
    assert result["status"] == "NO_CONTRADICTION_DETECTED"
    assert result["contradicted"] == []
    row = result["byRegionSleeve"]["KR:lowvol"]
    assert row["contradictedHorizons"] == []
    assert row["inconclusiveHorizons"] == [21, 63]
    assert row["consistentHorizons"] == [126]
    assert row["status"] == "CONSISTENT"


def test_a_withheld_sleeve_is_never_judged_against_its_live_weight():
    attribution = {"US:21": {"lowvol": {
        "claimEligible": False, "availableObservations": 0,
        "withheldReason": "PIT_FUNDAMENTALS_REQUIRED_FOR_FULL_LIVE_COMPOSITE",
        "rankIC": {"mean": -.5, "ci95": [-.6, -.4], "effectiveIndependentDates": 140}}}}
    assert PV._sleeve_sign_consistency(attribution)["byRegionSleeve"] == {}


def _multi_horizon_outcome(identifier, date, ticker, alpha, excess, end_date):
    return {
        "id": identifier, "date": date, "region": "US", "ticker": ticker,
        "sector": "Technology", "alphaPercentile": alpha,
        "modelVersion": "m", "replayVersion": "r",
        "pit": {"usableForCalibration": True, "pitCoverage": .8},
        "horizons": {str(h): {
            "absoluteReturn": excess + .01, "benchmarkReturn": .01,
            "excessReturn": excess, "costAdjustedExcessReturn": excess - .001,
            "endDate": end_date,
        } for h in (21, 63)},
    }


def test_report_names_a_sign_contradicted_sleeve_in_not_validated_claims():
    signals, outcomes = [], []
    date = pd.Timestamp("2014-01-02")
    for step in range(16):
        flip = step % 2 == 0
        stamp = date.strftime("%Y-%m-%d")
        end = (date + pd.offsets.BDay(63)).strftime("%Y-%m-%d")
        for idx in range(6):
            identifier = f"{stamp}-{idx}"
            # lowvol runs against realized excess every date; momentum flips
            # its ordering date to date, so it averages out and stays unjudged.
            signals.append({
                "id": identifier, "modelVersion": "m", "replayVersion": "r",
                "factorPercentiles": {
                    "lowvol": idx * 20,
                    "momentum": idx * 20 if flip else 100 - idx * 20}})
            outcomes.append(_multi_horizon_outcome(
                identifier, stamp, f"T{idx}", idx * 20, .05 - idx * .02, end))
        date += pd.offsets.BDay(70)

    report = PV.build_report(signals, outcomes, cfg_lt=CFG_LT, cfg_pf=CFG_PF,
                             diagnostics={}, replay_version="r", model_version="m")
    consistency = report["alphaDiagnostics"]["sleeveSignConsistency"]
    assert consistency["contradicted"] == ["US:lowvol"]
    assert consistency["actionPolicy"] == "REPORT_ONLY_NEVER_REWEIGHT_ON_THIS_SAMPLE"
    claim = [row for row in report["claims"]["notValidated"] if "lowvol" in row]
    assert len(claim) == 1
    assert "contradicts its assumed positive sign" in claim[0]
    # Detecting it must not quietly turn into acting on it.
    assert report["claims"]["noModelShopping"] is True
    assert LT.FACTOR_WEIGHTS["lowvol"] == .20
