"""Regression tests for the v2.1 integrity patch."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline import ledger as LG
from pipeline import longterm as LT
from pipeline import provenance as PV
from pipeline import regime as RG
from pipeline.validate import validate


ROOT = Path(__file__).resolve().parents[1]


def _artifact(**overrides):
    payload = {
        "portfolioName": "test",
        "meta": {"modelsTrained": 1, "coveragePct": 100, "coverageFloor": 95},
        "generatedAt": "2026-01-02T00:00:00+00:00",
        "core": [],
        "screened": [],
        "tradeIdeas": {"KR": [], "US": []},
        "recommendationsBlocked": False,
        "runMode": "paperTrading",
        "dataMode": "live",
        "stale": False,
        "seed": False,
    }
    payload.update(overrides)
    PV.stamp(payload, "paperTrading")
    return payload


def _write(tmp_path, payload):
    path = tmp_path / "artifact.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_production_validator_rejects_explicit_synthetic_mode(tmp_path):
    payload = _artifact(dataMode="synthetic")
    payload["provenance"]["dataMode"] = "synthetic"
    assert "synthetic_artifact_not_allowed_for_production" in validate(_write(tmp_path, payload))


def test_prior_state_accepts_only_last_validated_live_snapshot(tmp_path):
    from pipeline import state as ST

    payload = _artifact(
        meta={"latestDataDate": "2026-01-02", "modelsTrained": 1,
              "coveragePct": 100, "coverageFloor": 95},
        longTerm={"regions": {"US": {"holdings": ["AAA"]}, "KR": {"holdings": ["005930.KS"]}}},
        macroRegime={"regime": "Goldilocks"},
    )
    snapshot = ST.snapshot_from_payload(payload, validation_passed=True)
    path = tmp_path / "latest.json"
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    prior, status = ST.load_prior_state(
        path, expected_schema_version=PV.SCHEMA_VERSION,
        expected_model_version=PV.MODEL_VERSION,
    )
    assert status["available"] is True
    assert prior["holdingsByRegion"]["US"] == ["AAA"]
    assert prior["macroRegime"] == "Goldilocks"

    snapshot["dataMode"] = "synthetic"
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    prior2, status2 = ST.load_prior_state(
        path, expected_schema_version=PV.SCHEMA_VERSION,
        expected_model_version=PV.MODEL_VERSION,
    )
    assert prior2 == {}
    assert status2["available"] is False and status2["reason"] == "non_live_state"


def test_prior_state_missing_and_version_mismatch_are_explicit(tmp_path):
    from pipeline import state as ST

    missing = tmp_path / "missing.json"
    prior, status = ST.load_prior_state(
        missing, expected_schema_version=PV.SCHEMA_VERSION,
        expected_model_version=PV.MODEL_VERSION,
    )
    assert prior == {} and status == {"available": False, "reason": "state_file_missing"}

    bad = {
        "schemaVersion": "1.0.0", "modelVersion": "old", "dataMode": "live",
        "productionValidation": {"passed": True}, "holdingsByRegion": {},
    }
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    _, mismatch = ST.load_prior_state(
        path, expected_schema_version=PV.SCHEMA_VERSION,
        expected_model_version=PV.MODEL_VERSION,
    )
    assert mismatch["reason"] == "schema_version_mismatch"
    bad["schemaVersion"] = PV.SCHEMA_VERSION
    path.write_text(json.dumps(bad), encoding="utf-8")
    _, model_mismatch = ST.load_prior_state(
        path, expected_schema_version=PV.SCHEMA_VERSION,
        expected_model_version=PV.MODEL_VERSION,
    )
    assert model_mismatch["reason"] == "model_version_mismatch"


def test_rank_buffer_uses_different_incumbent_and_new_entry_floors():
    names = [f"T{i}" for i in range(10)]
    table = pd.DataFrame({
        "alpha": np.arange(10, dtype=float),
        "aboveMA200": True,
        "dataInsufficient": False,
        "sector": "Technology",
    }, index=names)
    cfg = {"minNames": 1, "maxNames": 10, "rankBuffer": {"enterPct": 10, "exitPct": 40}}
    chosen = LT.select_names(table, cfg, prior_holdings={"T6"})
    assert "T6" in chosen  # incumbent clears the looser 60th-percentile hold floor
    assert "T7" not in chosen  # identical non-incumbent does not clear the 90th-percentile entry floor
    assert "T9" in chosen


def _ledger_payload(n=20):
    rows = []
    details = {}
    for i in range(n):
        ticker = f"T{i:02d}"
        rows.append({
            "ticker": ticker, "region": "KR" if i % 2 else "US",
            "longTermResearchView": ["POSITIVE", "NEUTRAL", "NEGATIVE"][i % 3],
            "alpha": float(i), "alphaPercentile": i + 1,
        })
        details[ticker] = {"asOf": "2026-01-02", "lastClose": 100 + i}
    payload = _artifact(
        meta={"latestDataDate": "2026-01-03", "modelsTrained": 1,
              "coveragePct": 100, "coverageFloor": 95},
        benchmarks={"US": "SPY", "KR": "^KS200"},
        details=details,
        longTerm={"regions": {
            "ALL": {"researchTable": rows[:15], "validationCrossSection": rows}
        }},
    )
    return payload


def test_ledger_records_full_cross_section_after_provenance_stamp():
    payload = _ledger_payload()
    records = LG.records_from_payload(payload)
    assert len(records) == 20
    assert all(r["modelVersion"] and r["schemaVersion"] for r in records)
    assert all(r["date"] == "2026-01-02" and r["refClose"] is not None for r in records)
    assert {r["benchmark"] for r in records if r["region"] == "KR"} == {"^KS200"}
    assert {r["benchmark"] for r in records if r["region"] == "US"} == {"SPY"}


def test_new_model_version_does_not_overwrite_same_historical_signal():
    payload = _ledger_payload(1)
    old = LG.records_from_payload(payload)
    payload["modelVersion"] = payload["provenance"]["modelVersion"] = "new-model"
    new = LG.records_from_payload(payload)
    assert old[0]["id"] != new[0]["id"]
    merged, appended, _ = LG.append_signals(old, new)
    assert appended == 1 and len(merged) == 2


def test_unblocked_paper_research_keeps_entry_view():
    payload = {"weightsWithheld": False, "regions": {"US": {
        "picks": [], "researchTable": [{"ticker": "AAA", "sector": "Technology",
                                          "longTermResearchView": "POSITIVE"}],
        "validationCrossSection": [], "sectorExposure": {},
    }}}
    from pipeline import build as B
    B._attach_entry_states(
        payload, {"AAA": {"aboveMA50": True, "aboveMA200": True, "mom63Pct": 3}},
        {"maxSectorWeight": 0.30},
    )
    row = payload["regions"]["US"]["researchTable"][0]
    assert row["longTermResearchView"] == "POSITIVE"
    assert row["entry"]["entryState"]


def test_outcomes_use_exact_regional_benchmark_calendar_dates():
    dates = pd.bdate_range("2026-01-02", periods=30)
    stock = pd.DataFrame({"Close": np.linspace(100, 130, 30)}, index=dates)
    kr_benchmark = pd.Series(np.linspace(100, 110, 30), index=dates)
    signal = [{
        "id": "s", "date": dates[0].strftime("%Y-%m-%d"), "ticker": "005930.KS",
        "region": "KR", "benchmark": "^KS200", "alpha": 1.0,
        "longTermResearchView": "POSITIVE",
    }]
    outcome = LG.compute_outcomes(signal, {"005930.KS": stock}, {"^KS200": kr_benchmark})[0]
    expected = (stock["Close"].iloc[21] / 100 - 1) - (kr_benchmark.iloc[21] / 100 - 1)
    assert outcome["horizons"]["21"]["excessReturn"] == round(float(expected), 4)


def test_synthetic_signal_is_not_written_to_real_ledger(tmp_path):
    from scripts import update_ledger

    payload = _artifact(meta={"syntheticData": True}, seed=True)
    artifact = _write(tmp_path, payload)
    ledger_dir = tmp_path / "real-ledger"
    assert update_ledger.main([str(artifact), str(ledger_dir)]) == 0
    assert not ledger_dir.exists()


def _outcome(date, region, ticker, alpha, fwd):
    return {
        "id": f"{date}|{region}|{ticker}|m", "date": date, "region": region,
        "ticker": ticker, "alpha": alpha, "longTermResearchView": "POSITIVE",
        "horizons": {"21": {"fwdReturn": fwd, "excessReturn": fwd - 0.01}},
    }


def test_rank_ic_is_computed_by_date_and_region_cross_section():
    rows = []
    for i in range(3):
        rows.append(_outcome("2026-01-02", "US", f"U{i}", i, i / 10))
        rows.append(_outcome("2026-03-02", "KR", f"K{i}", i, -i / 10))
    metrics = LG.evaluate(rows, horizon=21)
    assert metrics["crossSections"] == 2
    assert metrics["rankIC"] == 0.0
    assert metrics["regionIC"]["US"]["mean"] == 1.0
    assert metrics["regionIC"]["KR"]["mean"] == -1.0


def test_live_validation_never_eligible_before_126_paper_days():
    rows = [_outcome("2026-01-02", "US", "AAA", 1, 0.1)]
    status = LG.validation_status(rows, min_paper_days=126)
    assert status["paperDays"] < 126
    assert status["liveValidationEligible"] is False
    assert status["liveValidated"] is False
    assert status["reasons"]


def test_cpi_level_can_rise_while_inflation_rate_decelerates():
    idx = pd.date_range("2020-01-31", periods=30, freq="ME")
    # Fast level gains first, then smaller gains: level still rises but YoY rate slows.
    values = np.r_[100 * (1.015 ** np.arange(18)),
                   100 * (1.015 ** 17) * (1.002 ** np.arange(1, 13))]
    read = RG.indicator_read("Core_CPI", pd.Series(values, index=idx), asof=idx[-1] + pd.Timedelta(days=30))
    assert read["latestValue"] > values[0]
    assert read["direction"] == -1
    assert "inflation_rate" in read["transformation"]


def test_flat_or_opposing_growth_inflation_is_transition():
    growth = {"value": 0.0, "confidence": 1.0}
    inflation = {"value": 0.0, "confidence": 1.0}
    assert RG._regime_label(growth, inflation)[0] == "Transition/Low confidence"
    inflation_tied = RG._axis_summary([
        {"axisContribution": 1, "stale": False},
        {"axisContribution": -1, "stale": False},
    ], expected_count=2)
    assert inflation_tied["direction"] == "flat"
    assert RG._regime_label({"value": -1.0, "confidence": 1.0}, inflation_tied)[0] == "Transition/Low confidence"


def test_historical_asof_excludes_future_release_and_drives_freshness():
    idx = pd.date_range("2020-01-31", periods=30, freq="ME")
    values = pd.Series(np.arange(30, dtype=float) + 100, index=idx)
    asof = idx[20] + pd.offsets.BDay(15)
    read = RG.indicator_read("Core_CPI", values, asof=asof)
    assert pd.Timestamp(read["observationDate"]) <= asof
    assert read["latestValue"] < values.iloc[-1]
    assert 0 <= read["freshnessDays"] < 60


def test_single_indicator_axis_cannot_receive_high_confidence():
    axis = RG._axis_summary([{"axisContribution": 1, "stale": False}], expected_count=4)
    assert axis["coverage"] == 0.25
    assert axis["confidence"] < 0.5


def test_longterm_exposes_evidence_quality_not_prediction_confidence():
    frame = pd.DataFrame({
        "alpha": range(8), "rawAlpha": range(8), "sector": "Technology",
        "confidence": 0.96, "factorCoverage": 1.0, "financialCoverage": 1.0,
        "sourceQuality": 0.9, "sleevesPresent": 4, "valueTrap": False,
        "momentum": 1.0, "value": 1.0, "quality": 1.0, "lowvol": 1.0,
        "vol252": 0.2, "downsideVol": 0.2, "cvar95": 0.03, "maxDD252": -0.1,
        "beta": 1.0, "mom121": 0.1, "aboveMA200": True, "regime": "Bull",
        "dataInsufficient": False,
    }, index=[f"T{i}" for i in range(8)])
    pct = frame[["momentum", "value", "quality", "lowvol"]] * 100
    alpha_pct = frame["alpha"].rank(pct=True).mul(100)
    row = LT._row(frame, pct, alpha_pct, "US", "T7")
    assert "confidence" not in row and "statisticalConfidence" not in row
    assert row["evidenceCoverage"] == 1.0
    assert row["dataCompleteness"] == 1.0
    assert row["empiricalValidationStatus"] == "PENDING_PAPER_HISTORY"


def test_frontend_labels_completeness_as_data_quality_with_legacy_fallback():
    app = (ROOT / "app.js").read_text(encoding="utf-8")
    assert "근거 커버리지" in app
    assert "p.dataCompleteness ?? p.financialCoverage" in app
    assert "신뢰도 <b>${Math.round((p.confidence" not in app


def test_pages_state_workflow_is_post_deploy_and_non_recursive():
    pages = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
    assert "branches: [main]" in pages
    assert "origin/signal-history:state/latest.json" in pages
    assert pages.index("Deploy to GitHub Pages") < pages.index("Publish last successful state")
    assert "state/latest.json" in pages


def test_synthetic_fixture_is_explicit_and_generated_artifact_is_ignored():
    fixture = ROOT / "tests" / "fixtures" / "site-data.synthetic.json"
    assert fixture.exists()
    data = json.loads(fixture.read_text(encoding="utf-8"))
    assert data["dataMode"] == "synthetic"
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "data/site-data.json" in ignored
