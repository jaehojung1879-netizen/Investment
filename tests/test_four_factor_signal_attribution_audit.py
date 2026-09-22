"""Unit tests for the four-factor signal attribution audit.

No portfolio is selected or valued anywhere in this module, so these tests
exercise pure statistical functions on small synthetic cross-sections rather
than a replay calendar.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pipeline import four_factor_signal_attribution_audit as C


# --------------------------------------------------------------------------- #
# Stage 0 -- provenance inventory
# --------------------------------------------------------------------------- #
def test_provenance_inventory_detects_sleeve_and_top_level_fields():
    signals = [
        {"factorPercentiles": {"momentum": 80, "value": 40, "quality": None, "lowvol": 60},
         "alphaPercentile": 90, "rawAlpha": 0.2, "alpha": 0.15,
         "features": {"evidenceCoverage": 0.8}, "risk": {"vol252Pct": 22.0}},
        {"factorPercentiles": {"momentum": 50, "value": None, "quality": 70, "lowvol": None},
         "alphaPercentile": None, "rawAlpha": None, "alpha": None,
         "features": {}, "risk": {}},
    ]
    report = C.provenance_inventory(signals)
    assert report["totalSignals"] == 2
    assert report["sleeveLevel"]["momentum"]["presentCount"] == 2
    assert report["sleeveLevel"]["value"]["presentCount"] == 1
    assert report["topLevel"]["alphaPercentile"]["presentCount"] == 1
    assert report["topLevel"]["evidenceCoverage"]["presentCount"] == 1


def test_provenance_inventory_marks_raw_momentum_and_value_unavailable():
    signals = [{"factorPercentiles": {"momentum": 80}, "risk": {"vol252Pct": 20.0}}]
    report = C.provenance_inventory(signals)
    assert report["subfactorLevel"]["momentum"]["mom121"]["status"] == \
        "UNAVAILABLE_PIT_INPUT_NOT_STORED"
    assert report["subfactorLevel"]["momentum"]["mom6"]["status"] == \
        "UNAVAILABLE_PIT_INPUT_NOT_STORED"
    assert report["subfactorLevel"]["value"]["earningsYield"]["status"] == \
        "UNAVAILABLE_PIT_INPUT_NOT_STORED"


def test_provenance_inventory_marks_lowvol_raw_input_available_via_risk_block():
    signals = [{"risk": {"vol252Pct": 18.5}}]
    report = C.provenance_inventory(signals)
    assert report["subfactorLevel"]["lowvol"]["vol252"]["status"] == "AVAILABLE"
    assert report["subfactorLevel"]["lowvol"]["vol252"]["presentCount"] == 1


def test_provenance_inventory_handles_empty_signals():
    report = C.provenance_inventory([])
    assert report["totalSignals"] == 0
    assert report["sleeveLevel"]["momentum"]["presentPct"] is None


# --------------------------------------------------------------------------- #
# build_frame
# --------------------------------------------------------------------------- #
def _outcome(oid, date, ticker, region, excess, end_date="2020-07-01"):
    return {
        "id": oid, "date": date, "ticker": ticker, "region": region, "sector": "Tech",
        "horizons": {"126": {"excessReturn": excess, "costAdjustedExcessReturn": excess - 0.001,
                             "endDate": end_date}},
    }


def _signal(sid, *, momentum=None, value=None, quality=None, lowvol=None,
           raw_alpha=None, alpha=None, evidence=None, vol252=None):
    return {
        "id": sid,
        "factorPercentiles": {"momentum": momentum, "value": value,
                              "quality": quality, "lowvol": lowvol},
        "rawAlpha": raw_alpha, "alpha": alpha,
        "features": {"evidenceCoverage": evidence},
        "risk": {"vol252Pct": vol252},
    }


def test_build_frame_joins_sleeve_and_extra_fields_by_id():
    outcomes = [_outcome("s1", "2020-01-01", "AAA", "US", 0.05)]
    signals = [_signal("s1", momentum=80, value=40, quality=60, lowvol=30,
                       raw_alpha=0.2, alpha=0.15, evidence=0.7, vol252=25.0)]
    frame = C.build_frame(signals, outcomes, 126)
    assert len(frame) == 1
    row = frame.iloc[0]
    assert row["momentum"] == 80
    assert row["value"] == 40
    assert row["rawAlpha"] == pytest.approx(0.2)
    assert row["alpha"] == pytest.approx(0.15)
    assert row["evidenceCoverage"] == pytest.approx(0.7)
    assert row["vol252Raw"] == pytest.approx(25.0)


def test_build_frame_on_empty_outcomes_returns_empty():
    frame = C.build_frame([], [], 126)
    assert frame.empty


# --------------------------------------------------------------------------- #
# standalone_ic_series
# --------------------------------------------------------------------------- #
def _monotonic_frame(n_dates=3, n_per_date=8, region="US", noise=0.0, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for d in range(n_dates):
        date = pd.Timestamp("2020-01-01") + pd.Timedelta(days=7 * d)
        momentum = rng.permutation(np.linspace(0, 100, n_per_date))
        excess = momentum / 100.0 + rng.normal(0, noise, n_per_date)
        for i in range(n_per_date):
            rows.append({"date": date, "region": region, "momentum": momentum[i],
                        "excessReturn": excess[i]})
    return pd.DataFrame(rows)


def test_standalone_ic_series_is_strongly_positive_on_a_monotonic_relationship():
    frame = _monotonic_frame()
    series = C.standalone_ic_series(frame, "US", "momentum")
    assert len(series) == 3
    assert (series > 0.9).all()


def test_standalone_ic_series_skips_dates_below_min_names():
    rows = [{"date": pd.Timestamp("2020-01-01"), "region": "US",
            "momentum": i, "excessReturn": i} for i in range(3)]
    frame = pd.DataFrame(rows)
    series = C.standalone_ic_series(frame, "US", "momentum")
    assert series.empty


def test_standalone_ic_series_never_mixes_regions():
    us = _monotonic_frame(region="US", seed=1)
    kr = _monotonic_frame(region="KR", seed=2)
    # Flip the KR relationship so a region leak would be visible immediately.
    kr = kr.assign(excessReturn=-kr["excessReturn"])
    frame = pd.concat([us, kr], ignore_index=True)
    us_series = C.standalone_ic_series(frame, "US", "momentum")
    kr_series = C.standalone_ic_series(frame, "KR", "momentum")
    assert (us_series > 0).all()
    assert (kr_series < 0).all()


# --------------------------------------------------------------------------- #
# pool_region_summaries
# --------------------------------------------------------------------------- #
def test_pool_region_summaries_inverse_variance_weights_the_tighter_region_more():
    summaries = {
        "US": {"mean": 0.10, "se": 0.01},   # tight -> dominates
        "KR": {"mean": -0.10, "se": 0.10},  # loose
    }
    pooled = C.pool_region_summaries(summaries)
    # Weight ratio (1/0.01^2) : (1/0.1^2) = 100:1, so the pooled mean sits
    # close to the tight region's own 0.10, not midway to KR's -0.10.
    assert pooled["mean"] == pytest.approx(0.098, abs=0.005)


def test_pool_region_summaries_matches_hand_computed_inverse_variance():
    summaries = {"A": {"mean": 0.2, "se": 0.1}, "B": {"mean": 0.4, "se": 0.2}}
    pooled = C.pool_region_summaries(summaries)
    w_a, w_b = 1 / 0.1 ** 2, 1 / 0.2 ** 2
    expected_mean = (0.2 * w_a + 0.4 * w_b) / (w_a + w_b)
    assert pooled["mean"] == pytest.approx(expected_mean, abs=1e-6)
    assert pooled["regionsUsed"] == 2


def test_pool_region_summaries_on_no_usable_regions_returns_none():
    pooled = C.pool_region_summaries({"US": {"mean": None, "se": None}})
    assert pooled["mean"] is None
    assert pooled["regionsUsed"] == 0


def test_pool_region_summaries_treats_zero_se_as_infinitely_informative():
    # A region whose IC series has zero sampling variance is the MOST
    # informative case, not an unusable one -- se == 0 must not be dropped
    # by a falsy check.
    pooled = C.pool_region_summaries({"US": {"mean": 1.0, "se": 0.0}})
    assert pooled["mean"] == pytest.approx(1.0)
    assert pooled["regionsUsed"] == 1


# --------------------------------------------------------------------------- #
# Holm-Bonferroni
# --------------------------------------------------------------------------- #
def test_holm_bonferroni_matches_hand_worked_example():
    # Classic textbook example: p = [.01, .02, .03, .04], m=4.
    pvalues = {"a": 0.01, "b": 0.02, "c": 0.03, "d": 0.04}
    adjusted = C.holm_bonferroni(pvalues)
    assert adjusted["a"] == pytest.approx(0.04)
    assert adjusted["b"] == pytest.approx(0.06)
    assert adjusted["c"] == pytest.approx(0.06)
    assert adjusted["d"] == pytest.approx(0.06)


def test_holm_bonferroni_is_monotone_nondecreasing_in_sorted_order():
    pvalues = {"a": 0.5, "b": 0.001, "c": 0.2, "d": 0.001}
    adjusted = C.holm_bonferroni(pvalues)
    ordered = sorted(pvalues.items(), key=lambda kv: kv[1])
    values = [adjusted[k] for k, _ in ordered]
    assert values == sorted(values)


def test_holm_bonferroni_passes_through_none():
    adjusted = C.holm_bonferroni({"a": 0.01, "b": None})
    assert adjusted["b"] is None
    assert adjusted["a"] is not None


# --------------------------------------------------------------------------- #
# cross_section_pass / redundancy_matrix
# --------------------------------------------------------------------------- #
def _redundant_frame(n_dates=4, n_per_date=15, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for d in range(n_dates):
        date = pd.Timestamp("2020-01-01") + pd.Timedelta(days=7 * d)
        base = rng.permutation(np.linspace(0, 100, n_per_date))
        momentum = base
        value = base + rng.normal(0, 1, n_per_date)  # near-duplicate of momentum
        quality = rng.permutation(np.linspace(0, 100, n_per_date))  # independent
        lowvol = 100 - base  # perfectly anti-correlated with momentum
        excess = base / 100.0 + rng.normal(0, 0.01, n_per_date)
        for i in range(n_per_date):
            rows.append({"date": date, "region": "US", "momentum": momentum[i],
                        "value": value[i], "quality": quality[i], "lowvol": lowvol[i],
                        "excessReturn": excess[i]})
    return pd.DataFrame(rows)


def test_redundancy_matrix_diagonal_is_one_and_detects_near_duplicate_sleeves():
    frame = _redundant_frame()
    artifacts = C.cross_section_pass(frame, "US")
    matrix = C.redundancy_matrix(artifacts["corrFrames"])
    assert matrix["available"]
    table = matrix["matrix"]
    assert table["momentum"]["momentum"]["mean"] == pytest.approx(1.0)
    assert table["momentum"]["value"]["mean"] > 0.9
    assert table["momentum"]["lowvol"]["mean"] < -0.9


def test_redundancy_matrix_on_no_frames_reports_unavailable():
    assert C.redundancy_matrix([]) == {"available": False}


def test_incremental_ic_table_attaches_se_so_pooling_does_not_silently_drop_it():
    # Regression: `_nw_summary` never returns `se` directly, and
    # `pool_region_summaries` reads a missing `se` as "no usable estimate".
    # incremental_ic_table (and quartile_spread_table) must attach `se`
    # themselves or a real, non-degenerate incremental IC vanishes from
    # every pooled reading with no error raised anywhere.
    frame = _redundant_frame(n_dates=6, n_per_date=20)
    artifacts = C.cross_section_pass(frame, "US")
    table = C.incremental_ic_table(artifacts["incrementalRows"], 126)
    # `quality` is independent noise in `_redundant_frame`, so its residual
    # against the other three sleeves is never degenerate.
    assert table["quality"]["se"] is not None
    pooled = C.pool_region_summaries({"US": table["quality"]})
    assert pooled["mean"] is not None


def test_quartile_spread_table_attaches_se_so_pooling_does_not_silently_drop_it():
    frame = _monotonic_frame(n_per_date=16, noise=0.1)
    artifacts = C.cross_section_pass(frame.assign(value=frame["momentum"],
                                                   quality=frame["momentum"],
                                                   lowvol=frame["momentum"]), "US")
    table = C.quartile_spread_table(artifacts["quartileRows"], 126)
    assert table["momentum"]["se"] is not None
    pooled = C.pool_region_summaries({"US": table["momentum"]})
    assert pooled["mean"] is not None


def test_incremental_ic_collapses_for_a_sleeve_fully_explained_by_others():
    frame = _redundant_frame()
    artifacts = C.cross_section_pass(frame, "US")
    incremental = C.incremental_ic_table(artifacts["incrementalRows"], 126)
    standalone_value = C.standalone_ic_series(frame, "US", "value")
    # `value` is momentum + noise, so once momentum/quality/lowvol are
    # controlled for, its incremental IC should be far smaller in magnitude
    # than its standalone IC (which is high, because it duplicates momentum).
    assert abs(standalone_value.mean()) > 0.8
    assert abs(incremental["value"]["mean"] or 0.0) < abs(standalone_value.mean())


def test_quartile_spread_table_is_positive_on_a_monotonic_relationship():
    frame = _monotonic_frame(n_per_date=16)
    artifacts = C.cross_section_pass(frame.assign(value=frame["momentum"],
                                                   quality=frame["momentum"],
                                                   lowvol=frame["momentum"]), "US")
    spreads = C.quartile_spread_table(artifacts["quartileRows"], 126)
    assert spreads["momentum"]["mean"] > 0


def test_quintile_monotonicity_table_is_fully_monotone_on_a_clean_relationship():
    frame = _monotonic_frame(n_per_date=20)
    artifacts = C.cross_section_pass(frame.assign(value=frame["momentum"],
                                                   quality=frame["momentum"],
                                                   lowvol=frame["momentum"]), "US")
    table = C.quintile_monotonicity_table(artifacts["quintileMeans"])
    assert table["momentum"]["monotonicityScore"] == pytest.approx(1.0)
    assert table["momentum"]["q5MinusQ1"] > 0


# --------------------------------------------------------------------------- #
# Time stability
# --------------------------------------------------------------------------- #
def test_half_split_dates_splits_evenly_and_chronologically():
    frame = _monotonic_frame(n_dates=4)
    first, second = C.half_split_dates(frame)
    assert len(first) == 2
    assert len(second) == 2
    assert max(first) < min(second)


def test_half_split_dates_on_empty_frame():
    first, second = C.half_split_dates(pd.DataFrame({"date": []}))
    assert first is None and second is None


# --------------------------------------------------------------------------- #
# classify_sleeve
# --------------------------------------------------------------------------- #
def test_classify_sleeve_case_a_independent_useful_signal():
    result = C.classify_sleeve(
        standalone_pooled={"mean": 0.05}, incremental_pooled={"mean": 0.04},
        region_signs=["POSITIVE", "POSITIVE"], half_signs=["POSITIVE", "POSITIVE"])
    assert result["case"] == "A_INDEPENDENT_USEFUL_SIGNAL"


def test_classify_sleeve_case_b_redundant_signal():
    result = C.classify_sleeve(
        standalone_pooled={"mean": 0.05}, incremental_pooled={"mean": 0.001},
        region_signs=["POSITIVE", "POSITIVE"], half_signs=["POSITIVE", "POSITIVE"])
    assert result["case"] == "B_REDUNDANT_SIGNAL"


def test_classify_sleeve_case_c_potentially_harmful():
    result = C.classify_sleeve(
        standalone_pooled={"mean": -0.05}, incremental_pooled={"mean": -0.04},
        region_signs=["NEGATIVE", "NEGATIVE"], half_signs=["NEGATIVE", "NEGATIVE"])
    assert result["case"] == "C_POTENTIALLY_HARMFUL_WRONG_SIGN"


def test_classify_sleeve_case_d_on_region_disagreement():
    result = C.classify_sleeve(
        standalone_pooled={"mean": 0.05}, incremental_pooled={"mean": 0.04},
        region_signs=["POSITIVE", "NEGATIVE"], half_signs=["POSITIVE", "POSITIVE"])
    assert result["case"] == "D_UNSTABLE_REGIME_DEPENDENT"


def test_classify_sleeve_case_d_on_half_sample_disagreement():
    result = C.classify_sleeve(
        standalone_pooled={"mean": 0.05}, incremental_pooled={"mean": 0.04},
        region_signs=["POSITIVE", "POSITIVE"], half_signs=["POSITIVE", "NEGATIVE"])
    assert result["case"] == "D_UNSTABLE_REGIME_DEPENDENT"


def test_classify_sleeve_never_recommends_deletion_in_its_rationale():
    result = C.classify_sleeve(
        standalone_pooled={"mean": -0.05}, incremental_pooled={"mean": -0.04},
        region_signs=["NEGATIVE", "NEGATIVE"], half_signs=["NEGATIVE", "NEGATIVE"])
    assert "remove" not in result["rationale"].lower() or "NOT a recommendation" in result["rationale"]


# --------------------------------------------------------------------------- #
# EvidenceCoverage audit
# --------------------------------------------------------------------------- #
def test_evidence_coverage_audit_reports_rank_correlation_and_distribution():
    rows = []
    for d in range(2):
        date = pd.Timestamp("2020-01-01") + pd.Timedelta(days=7 * d)
        for i in range(8):
            raw = float(i)
            coverage = 0.5 + 0.05 * i
            rows.append({"date": date, "region": "US", "rawAlpha": raw,
                        "alpha": raw * coverage, "evidenceCoverage": coverage,
                        "excessReturn": raw / 100.0})
    frame = pd.DataFrame(rows)
    report = C.evidence_coverage_audit(frame)
    assert report["rawAlphaVsAlphaRankSpearman"]["mean"] > 0.5
    assert report["evidenceCoverageDistribution"]["mean"] is not None


def test_evidence_coverage_audit_on_empty_frame():
    frame = pd.DataFrame({"rawAlpha": [], "alpha": [], "evidenceCoverage": [],
                          "date": [], "region": [], "excessReturn": []})
    report = C.evidence_coverage_audit(frame)
    assert report["rawAlphaVsAlphaRankSpearman"]["mean"] is None


# --------------------------------------------------------------------------- #
# Coverage report
# --------------------------------------------------------------------------- #
def test_coverage_report_counts_missing_rate_per_sleeve_and_region():
    frame = pd.DataFrame({
        "region": ["US", "US", "KR"],
        "momentum": [1.0, None, 2.0],
        "value": [None, None, 3.0],
        "quality": [1.0, 1.0, 1.0],
        "lowvol": [1.0, 1.0, 1.0],
    })
    report = C.coverage_report(frame)
    assert report["US"]["momentum"]["usableObservations"] == 1
    assert report["US"]["value"]["missingRatePct"] == pytest.approx(100.0)
    assert report["KR"]["quality"]["usableObservations"] == 1


# --------------------------------------------------------------------------- #
# sleeve_ic_table (integration of the primary pieces)
# --------------------------------------------------------------------------- #
def test_sleeve_ic_table_reports_by_region_and_pooled_with_p_values():
    us = _monotonic_frame(region="US", seed=3, noise=0.3)
    kr = _monotonic_frame(region="KR", seed=4, noise=0.3)
    frame = pd.concat([us, kr], ignore_index=True)
    table = C.sleeve_ic_table(frame, 126, column_map={"momentum": "momentum"})
    assert "US" in table["momentum"]["byRegion"]
    assert "KR" in table["momentum"]["byRegion"]
    assert table["momentum"]["pooled"]["mean"] is not None
    assert table["momentum"]["byRegion"]["US"]["rawPValue"] is not None
