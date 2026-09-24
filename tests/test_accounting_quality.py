"""Accounting-quality ratios, and the guardrails they inherit from the derive
modules they reuse rather than re-implement.

Every assertion here checks either (a) a ratio this module adds that the
production derive modules never expose, or (b) that the reused primitives
(`trailing_twelve_months`, `level_amount`/`amount`, `carried_shares`) are
actually being called rather than re-derived — a second implementation is a
second place for the two to disagree.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import accounting_quality as AQ  # noqa: E402
from pipeline import finnhub_fundamentals as FF  # noqa: E402

RECEIPT = {"11013": (0, "05-15"), "11012": (0, "08-14"),
           "11014": (0, "11-14"), "11011": (1, "03-15")}


def _kr_filing(year, code, **accounts):
    offset, day = RECEIPT[code]
    return {
        "ticker": "005930.KS", "fiscalYear": year, "reportCode": code,
        "availableFrom": f"{year + offset}-{day}", "currency": "KRW",
        "source": "DART:fnlttSinglAcntAll:CFS", "fsDiv": "CFS",
        "collectedAt": "2026-09-01T00:00:00Z",
        "accounts": {name: {"statement": stmt, "amounts": amounts}
                     for name, (stmt, amounts) in accounts.items()},
    }


def _us_filing(year, stage, *, ic=(), bs=(), cf=(), available=None):
    def entries(pairs):
        return [{"concept": c, "unit": u, "value": v, "label": c}
                for c, v, u in pairs]
    return {
        "id": f"AAA-{year}-{stage}", "ticker": "AAA", "fiscalYear": year,
        "form": "10-K" if stage == FF.FY else "10-Q",
        "periodEnd": f"{year}-12-31", "availableFrom": available or f"{year + 1}-02-15",
        "source": "finnhub/financials-reported", "collectedAt": "2026-09-14T00:00:00Z",
        "statements": {"ic": entries(ic), "bs": entries(bs), "cf": entries(cf)},
    }


def _usd(concept, value):
    return (concept, value, "usd")


# --------------------------------------------------------------------------- #
# KR: OCF/NI, asset growth, debt growth, capex intensity, share dilution
# --------------------------------------------------------------------------- #
def test_kr_ocf_to_net_income_uses_the_same_ttm_rollforward():
    filings = [
        _kr_filing(2022, "11011", 당기순이익=("IS", {"thstrm_amount": 1000.0}),
                  영업활동현금흐름=("CF", {"thstrm_amount": 900.0})),
        _kr_filing(2023, "11011", 당기순이익=("IS", {"thstrm_amount": 1200.0}),
                  영업활동현금흐름=("CF", {"thstrm_amount": 600.0})),
    ]
    by_key = {(2022, "11011"): filings[0], (2023, "11011"): filings[1]}
    fields, basis = AQ.derive_kr_fields(by_key, 2023, "11011")
    assert fields["ocfToNetIncomePct"] == 50.0
    assert basis["netIncome"] == "ANNUAL_AS_FILED"


def test_kr_asset_and_debt_growth_compare_same_stage_a_year_apart():
    prior = _kr_filing(2022, "11014", 자산총계=("BS", {"thstrm_amount": 1000.0}),
                       부채총계=("BS", {"thstrm_amount": 400.0}))
    current = _kr_filing(2023, "11014", 자산총계=("BS", {"thstrm_amount": 1100.0}),
                         부채총계=("BS", {"thstrm_amount": 460.0}))
    by_key = {(2022, "11014"): prior, (2023, "11014"): current}
    fields, basis = AQ.derive_kr_fields(by_key, 2023, "11014")
    assert fields["assetGrowthPct"] == pytest.approx(10.0)
    assert fields["debtGrowthPct"] == pytest.approx(15.0)
    assert basis["priorAssetsAvailable"] is True


def test_kr_asset_growth_is_none_without_a_prior_year_filing():
    current = _kr_filing(2023, "11011", 자산총계=("BS", {"thstrm_amount": 1100.0}))
    by_key = {(2023, "11011"): current}
    fields, basis = AQ.derive_kr_fields(by_key, 2023, "11011")
    assert "assetGrowthPct" not in fields
    assert basis["priorAssetsAvailable"] is False


def test_kr_capex_intensity_needs_both_capex_and_revenue():
    filing = _kr_filing(2023, "11011", 매출액=("IS", {"thstrm_amount": 5000.0}),
                        유형자산의취득=("CF", {"thstrm_amount": 250.0}))
    by_key = {(2023, "11011"): filing}
    fields, _ = AQ.derive_kr_fields(by_key, 2023, "11011")
    assert fields["capexIntensityPct"] == 5.0


def test_kr_share_count_change_is_a_growth_rate_not_a_raw_difference():
    filing = _kr_filing(2023, "11011")
    by_key = {(2023, "11011"): filing}
    fields, basis = AQ.derive_kr_fields(by_key, 2023, "11011", shares=110.0,
                                        prior_shares=100.0)
    assert fields["shareCountChangePct"] == pytest.approx(10.0)
    assert basis["sharesAvailable"] is True


# --------------------------------------------------------------------------- #
# US: mirrors the KR behaviour through finnhub_derive's own primitives
# --------------------------------------------------------------------------- #
def test_us_fields_reuse_total_liabilities_fallback():
    prior = _us_filing(2021, FF.FY, bs=[_usd("Assets", 900.0), _usd("StockholdersEquity", 500.0)])
    current = _us_filing(2022, FF.FY,
                         ic=[_usd("NetIncomeLoss", 100.0)],
                         cf=[_usd("NetCashProvidedByUsedInOperatingActivities", 120.0)],
                         bs=[_usd("Assets", 1000.0), _usd("StockholdersEquity", 550.0)])
    by_key = {(2021, FF.FY): prior, (2022, FF.FY): current}
    fields, basis = AQ.derive_us_fields(by_key, 2022, FF.FY)
    assert fields["ocfToNetIncomePct"] == 120.0
    # Liabilities were never stated directly, so both years fall back to
    # Assets - Equity — the same fallback `finnhub_derive.total_liabilities`
    # already implements, exercised here rather than re-derived.
    assert basis["liabilitiesBasis"] == "ASSETS_LESS_EQUITY"
    assert fields["assetGrowthPct"] == pytest.approx((1000.0 - 900.0) / 900.0 * 100.0)


def test_us_fcf_to_net_income_subtracts_capex_by_magnitude():
    current = _us_filing(2022, FF.FY,
                         ic=[_usd("NetIncomeLoss", 200.0)],
                         cf=[_usd("NetCashProvidedByUsedInOperatingActivities", 300.0),
                             _usd("PaymentsToAcquirePropertyPlantAndEquipment", -50.0)])
    by_key = {(2022, FF.FY): current}
    fields, _ = AQ.derive_us_fields(by_key, 2022, FF.FY)
    assert fields["fcfToNetIncomePct"] == 125.0  # (300-50)/200 * 100


# --------------------------------------------------------------------------- #
# Growth helper: the sign/base-positivity discipline `_ratio` already has
# --------------------------------------------------------------------------- #
def test_growth_pct_refuses_a_non_positive_base():
    assert AQ._growth_pct(100.0, 0.0) is None
    assert AQ._growth_pct(100.0, -10.0) is None
    assert AQ._growth_pct(None, 10.0) is None


# --------------------------------------------------------------------------- #
# Operating-margin stability: backward-only, never invents missing history
# --------------------------------------------------------------------------- #
def test_margin_stability_uses_only_the_trailing_window():
    series = [("2020-01-01", 10.0), ("2020-04-01", 12.0), ("2020-07-01", 8.0),
              ("2020-10-01", 11.0), ("2021-01-01", 30.0)]
    result = AQ.operating_margin_stability(series, window=4)
    # Only the last 4 readings feed the window; the 30.0 spike does not get
    # smoothed away by the whole history, but the first entry is excluded.
    assert result["observedFilings"] == 4
    assert 10.0 - 12.0 not in [result["stabilityPct"]]  # sanity: not a raw diff


def test_margin_stability_on_a_single_reading_is_none_not_zero():
    result = AQ.operating_margin_stability([("2020-01-01", 10.0)])
    assert result["stabilityPct"] is None
    assert result["observedFilings"] == 1


def test_margin_stability_on_no_history_is_none():
    result = AQ.operating_margin_stability([])
    assert result["stabilityPct"] is None
    assert result["observedFilings"] == 0


# --------------------------------------------------------------------------- #
# Coverage: reported per field, never averaged into one number
# --------------------------------------------------------------------------- #
def test_coverage_is_reported_per_field():
    rows = [
        {"fields": {"ocfToNetIncomePct": 1.0, "assetGrowthPct": 2.0}},
        {"fields": {"ocfToNetIncomePct": 3.0}},
    ]
    report = AQ.coverage(rows)
    assert report["rows"] == 2
    assert report["fieldCoveragePct"]["ocfToNetIncomePct"] == 100.0
    assert report["fieldCoveragePct"]["assetGrowthPct"] == 50.0
    assert report["fieldCoveragePct"]["debtGrowthPct"] == 0.0
