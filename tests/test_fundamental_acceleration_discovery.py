"""Unit tests for the fundamental-acceleration discovery study.

No portfolio is selected or valued anywhere in this module, so these tests
exercise pure composite-construction and statistical functions on small
synthetic cross-sections, mirroring
`tests/test_four_factor_signal_attribution_audit.py`'s own approach.
"""
from __future__ import annotations

import pandas as pd
import pytest

from pipeline import fundamental_acceleration as FA
from pipeline import fundamental_acceleration_discovery as D
from pipeline import pit_data


def _record(ticker, period, available_from, fields):
    return pit_data.FundamentalRecord(
        ticker=ticker, report_period=period, available_from=available_from,
        report_date=available_from, fields=dict(fields),
    )


# --------------------------------------------------------------------------- #
# build_readings -- joins signals to acceleration_reading via the store
# --------------------------------------------------------------------------- #
def test_build_readings_one_row_per_signal_with_status_and_deltas():
    store = pit_data.FundamentalStore({"A": [
        _record("A", "2019-Q1", "2019-05-01",
                {"roe": 0.10, "operatingMargin": 0.18, "profitMargin": 0.08}),
        _record("A", "2019-Q2", "2019-08-01",
                {"roe": 0.14, "operatingMargin": 0.20, "profitMargin": 0.10}),
    ]})
    signals = [{"id": "s1", "ticker": "A", "region": "US", "date": "2019-09-01",
               "sector": "Technology", "factorPercentiles": {"quality": 55}}]
    readings = D.build_readings(signals, store)
    assert len(readings) == 1
    row = readings.iloc[0]
    assert row["status"] == FA.OK
    assert bool(row["dataSufficient"]) is True
    assert row["deltaRoe"] == pytest.approx(0.04)
    assert row["qualityPercentile"] == 55


def test_build_readings_skips_rows_missing_identity_fields():
    store = pit_data.FundamentalStore({})
    signals = [{"id": "s1", "ticker": None, "region": "US", "date": "2019-09-01"},
              {"id": "s2", "ticker": "A", "region": "US", "date": "2019-09-01",
               "sector": "Technology"}]
    readings = D.build_readings(signals, store)
    assert len(readings) == 1
    assert readings.iloc[0]["id"] == "s2"


# --------------------------------------------------------------------------- #
# build_composite -- sector-neutral z, cross-sectional per (date, region)
# --------------------------------------------------------------------------- #
def _readings_frame(rows: list[dict]) -> pd.DataFrame:
    base = {"id": None, "date": pd.Timestamp("2019-09-01"), "ticker": None, "region": "US",
           "sector": "Technology", "qualityPercentile": None, "momentumPercentile": None,
           "valuePercentile": None, "lowvolPercentile": None, "alphaPercentile": None,
           "status": FA.OK, "dataSufficient": True, "primaryFieldsPresent": 4,
           "deltaRoe": None, "deltaOperatingMargin": None, "deltaProfitMargin": None,
           "deltaEarningsGrowth": None, "deltaDebtToEquity": None}
    return pd.DataFrame([{**base, **row} for row in rows])


def test_build_composite_ranks_higher_delta_names_higher():
    readings = _readings_frame([
        {"id": "a", "ticker": "A", "deltaRoe": 0.05, "deltaOperatingMargin": 0.05,
         "deltaProfitMargin": 0.05, "deltaEarningsGrowth": 0.05},
        {"id": "b", "ticker": "B", "deltaRoe": 0.01, "deltaOperatingMargin": 0.01,
         "deltaProfitMargin": 0.01, "deltaEarningsGrowth": 0.01},
        {"id": "c", "ticker": "C", "deltaRoe": -0.03, "deltaOperatingMargin": -0.03,
         "deltaProfitMargin": -0.03, "deltaEarningsGrowth": -0.03},
        {"id": "d", "ticker": "D", "deltaRoe": -0.08, "deltaOperatingMargin": -0.08,
         "deltaProfitMargin": -0.08, "deltaEarningsGrowth": -0.08},
        {"id": "e", "ticker": "E", "deltaRoe": 0.10, "deltaOperatingMargin": 0.10,
         "deltaProfitMargin": 0.10, "deltaEarningsGrowth": 0.10},
    ])
    out = D.build_composite(readings)
    ranked = out.set_index("ticker")["accelerationPercentile"]
    assert ranked["E"] > ranked["A"] > ranked["B"] > ranked["C"] > ranked["D"]


def test_build_composite_excludes_data_insufficient_rows():
    readings = _readings_frame([
        {"id": "a", "ticker": "A", "dataSufficient": True, "deltaRoe": 0.05,
         "deltaOperatingMargin": 0.05, "deltaProfitMargin": 0.05, "deltaEarningsGrowth": 0.05},
        {"id": "b", "ticker": "B", "dataSufficient": False, "deltaRoe": None,
         "deltaOperatingMargin": None, "deltaProfitMargin": None, "deltaEarningsGrowth": None},
    ])
    out = D.build_composite(readings)
    row_b = out.set_index("ticker").loc["B"]
    assert pd.isna(row_b["compositeZ"])
    assert pd.isna(row_b["accelerationPercentile"])


def test_build_composite_averages_over_present_fields_only():
    # Only 3 of 4 fields present (minimum) for every name; the missing field
    # must not count as zero and drag the composite down. `longterm.zscore`
    # requires >= 3 names to compute a z-score at all, so a realistic
    # (5-name) cross-section is used rather than a 2-name one.
    readings = _readings_frame([
        {"id": "a", "ticker": "A", "deltaRoe": 0.10, "deltaOperatingMargin": 0.10,
         "deltaProfitMargin": 0.10, "deltaEarningsGrowth": None, "primaryFieldsPresent": 3},
        {"id": "b", "ticker": "B", "deltaRoe": -0.10, "deltaOperatingMargin": -0.10,
         "deltaProfitMargin": -0.10, "deltaEarningsGrowth": None, "primaryFieldsPresent": 3},
        {"id": "c", "ticker": "C", "deltaRoe": 0.02, "deltaOperatingMargin": 0.02,
         "deltaProfitMargin": 0.02, "deltaEarningsGrowth": None, "primaryFieldsPresent": 3},
        {"id": "d", "ticker": "D", "deltaRoe": -0.02, "deltaOperatingMargin": -0.02,
         "deltaProfitMargin": -0.02, "deltaEarningsGrowth": None, "primaryFieldsPresent": 3},
        {"id": "e", "ticker": "E", "deltaRoe": 0.05, "deltaOperatingMargin": 0.05,
         "deltaProfitMargin": 0.05, "deltaEarningsGrowth": None, "primaryFieldsPresent": 3},
    ])
    out = D.build_composite(readings)
    assert not out["compositeZ"].isna().any()


# --------------------------------------------------------------------------- #
# coverage_table
# --------------------------------------------------------------------------- #
def test_coverage_table_ratio_and_meets_threshold():
    readings = _readings_frame([
        {"id": "a", "ticker": "A", "status": FA.OK, "dataSufficient": True},
        {"id": "b", "ticker": "B", "status": FA.OK, "dataSufficient": True},
        {"id": "c", "ticker": "C", "status": FA.NO_PREVIOUS_FILING, "dataSufficient": False},
    ])
    report = D.coverage_table(readings)
    assert report["overall"]["total"] == 3
    assert report["overall"]["dataSufficient"] == 2
    assert report["overall"]["dataSufficientRatio"] == pytest.approx(2 / 3, abs=1e-4)
    assert report["meetsMinCoverageRatio"] is True


def test_coverage_table_below_threshold_fails():
    readings = _readings_frame([
        {"id": "a", "ticker": "A", "status": FA.NO_FILING_VISIBLE, "dataSufficient": False},
        {"id": "b", "ticker": "B", "status": FA.NO_FILING_VISIBLE, "dataSufficient": False},
        {"id": "c", "ticker": "C", "status": FA.OK, "dataSufficient": True},
    ])
    report = D.coverage_table(readings)
    assert report["meetsMinCoverageRatio"] is False


# --------------------------------------------------------------------------- #
# orthogonality_table
# --------------------------------------------------------------------------- #
def test_orthogonality_fails_redundancy_when_correlation_high():
    rows = []
    for i in range(10):
        rows.append({"id": f"n{i}", "ticker": f"T{i}",
                     "accelerationPercentile": float(i * 10),
                     "qualityPercentile": float(i * 10)})
    readings = _readings_frame(rows)
    report = D.orthogonality_table(readings)
    assert report["qualityAbsRho"] == pytest.approx(1.0, abs=1e-6)
    assert report["failsRedundancy"] is True


def test_orthogonality_passes_when_uncorrelated():
    rows = []
    # A pattern with ~zero rank correlation between acceleration and quality.
    accel = [10, 90, 30, 70, 50, 20, 80, 40, 60, 0]
    quality = [0, 10, 90, 20, 80, 30, 70, 40, 60, 50]
    for i, (a, q) in enumerate(zip(accel, quality, strict=True)):
        rows.append({"id": f"n{i}", "ticker": f"T{i}",
                     "accelerationPercentile": float(a), "qualityPercentile": float(q)})
    readings = _readings_frame(rows)
    report = D.orthogonality_table(readings)
    assert abs(report["qualityAbsRho"]) < D.MAX_ORTHOGONALITY_ABS_RHO
    assert report["failsRedundancy"] is False


# --------------------------------------------------------------------------- #
# classify_outcome -- five-case decision tree, fixed priority order
# --------------------------------------------------------------------------- #
def _coverage(ratio, passes):
    return {"overall": {"dataSufficientRatio": ratio}, "meetsMinCoverageRatio": passes}


def _orthogonality(rho, fails):
    return {"qualityAbsRho": rho, "failsRedundancy": fails}


def test_classify_fail_coverage_takes_priority():
    result = D.classify_outcome(
        coverage=_coverage(0.30, False),
        orthogonality=_orthogonality(0.90, True),
        standalone_pooled={"mean": 0.10, "ci95": [0.01, 0.20]},
        incremental_pooled={"mean": 0.10, "ci95": [0.01, 0.20]},
    )
    assert result["case"] == D.CASE_C


def test_classify_fail_redundancy_when_coverage_passes():
    result = D.classify_outcome(
        coverage=_coverage(0.80, True),
        orthogonality=_orthogonality(0.85, True),
        standalone_pooled={"mean": 0.10, "ci95": [0.01, 0.20]},
        incremental_pooled={"mean": 0.10, "ci95": [0.01, 0.20]},
    )
    assert result["case"] == D.CASE_B


def test_classify_case_a_both_positive_and_separated():
    result = D.classify_outcome(
        coverage=_coverage(0.80, True),
        orthogonality=_orthogonality(0.20, False),
        standalone_pooled={"mean": 0.05, "ci95": [0.01, 0.09]},
        incremental_pooled={"mean": 0.04, "ci95": [0.005, 0.075]},
    )
    assert result["case"] == D.CASE_A


def test_classify_case_e_positive_but_ci_contains_zero():
    result = D.classify_outcome(
        coverage=_coverage(0.80, True),
        orthogonality=_orthogonality(0.20, False),
        standalone_pooled={"mean": 0.05, "ci95": [-0.02, 0.12]},
        incremental_pooled={"mean": 0.03, "ci95": [-0.01, 0.07]},
    )
    assert result["case"] == D.CASE_E


def test_classify_case_d_negative_point_estimate():
    result = D.classify_outcome(
        coverage=_coverage(0.80, True),
        orthogonality=_orthogonality(0.20, False),
        standalone_pooled={"mean": -0.02, "ci95": [-0.08, 0.04]},
        incremental_pooled={"mean": -0.01, "ci95": [-0.06, 0.04]},
    )
    assert result["case"] == D.CASE_D


def test_classify_case_d_when_signs_disagree():
    result = D.classify_outcome(
        coverage=_coverage(0.80, True),
        orthogonality=_orthogonality(0.20, False),
        standalone_pooled={"mean": 0.05, "ci95": [0.01, 0.09]},
        incremental_pooled={"mean": -0.01, "ci95": [-0.05, 0.03]},
    )
    assert result["case"] == D.CASE_D


def test_classify_case_d_when_means_are_none():
    result = D.classify_outcome(
        coverage=_coverage(0.80, True),
        orthogonality=_orthogonality(0.20, False),
        standalone_pooled={"mean": None, "ci95": None},
        incremental_pooled={"mean": None, "ci95": None},
    )
    assert result["case"] == D.CASE_D


# --------------------------------------------------------------------------- #
# quintile_table -- monotonicity and spread on a single column/horizon
# --------------------------------------------------------------------------- #
def test_quintile_table_monotone_increasing_relationship():
    rows = []
    for date_i in range(3):
        date = pd.Timestamp("2019-01-01") + pd.Timedelta(days=date_i)
        for i in range(20):
            rows.append({
                "date": date, "region": "US",
                "accelerationPercentile": float(i * 5),
                "excessReturn": float(i) * 0.001,
            })
    frame = pd.DataFrame(rows)
    report = D.quintile_table(frame)
    assert report["q5MinusQ1"] is not None
    assert report["q5MinusQ1"] > 0
    assert report["monotonicityScore"] == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# region_stability
# --------------------------------------------------------------------------- #
def test_region_stability_flags_disagreement():
    standalone = {"byRegion": {"KR": {"mean": 0.05}, "US": {"mean": -0.03}}}
    report = D.region_stability(standalone)
    assert report["agree"] is False
    assert report["label"] == "REGION_SIGN_UNSTABLE"


def test_debt_acceleration_diagnostic_masks_exempt_sectors():
    readings = _readings_frame([
        {"id": "a", "ticker": "A", "sector": "Financials", "deltaDebtToEquity": 5.0},
        {"id": "b", "ticker": "B", "sector": "Technology", "deltaDebtToEquity": 0.2},
        {"id": "c", "ticker": "C", "sector": "Technology", "deltaDebtToEquity": -0.4},
        {"id": "d", "ticker": "D", "sector": "Real Estate", "deltaDebtToEquity": 3.0},
    ])
    report = D.debt_acceleration_diagnostic(readings)
    assert report["exemptObservationsMasked"] == 2  # Financials + Real Estate
    assert report["nonExemptObservations"] == 2
    # Mean over only the two Technology names: (0.2 + -0.4) / 2 = -0.1
    assert report["meanDeltaDebtToEquityNonExempt"] == pytest.approx(-0.1)
    assert "Financials" in report["exemptSectors"]
    assert "Real Estate" in report["exemptSectors"]


def test_debt_acceleration_diagnostic_excludes_non_ok_status_rows():
    readings = _readings_frame([
        {"id": "a", "ticker": "A", "sector": "Technology", "status": FA.NOT_CONSECUTIVE,
         "deltaDebtToEquity": None},
        {"id": "b", "ticker": "B", "sector": "Technology", "status": FA.OK,
         "deltaDebtToEquity": 1.0},
    ])
    report = D.debt_acceleration_diagnostic(readings)
    assert report["nonExemptObservations"] == 1


def test_region_stability_agreement():
    standalone = {"byRegion": {"KR": {"mean": 0.05}, "US": {"mean": 0.02}}}
    report = D.region_stability(standalone)
    assert report["agree"] is True
    assert report["label"] is None
