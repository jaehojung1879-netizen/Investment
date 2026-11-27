"""Synthetic counterexamples and separately labelled observed FRED table arithmetic."""
import hashlib
import math

import pytest

from research.market_implied_future_s5 import foundation as s5


def load(raw, **over):
    args = dict(symbol="VIX3M", url=s5.FRED + "VXVCLS", sha256=hashlib.sha256(raw).hexdigest(),
                retrieved_at="2026-11-26T12:00:00Z", as_of="2026-11-27T12:00:00Z")
    args.update(over)
    return s5.admit(raw, **args)


def test_backfill_and_missing_not_forward_filled():
    raw = b"observation_date,VXVCLS\n2013-12-31,16\n2014-01-02,17\n2014-01-03,.\n"
    item = load(raw)
    assert item["excludedPreLiveEraRows"] == 1
    assert item["rows"] == {"2014-01-02": 17.0, "2014-01-03": None}
    assert item["evidenceClass"] == "CURRENT_HISTORY_NOT_VERIFIED_PIT"


@pytest.mark.parametrize("raw,reason", [
    (b"observation_date,VXVCLS\n2026-11-23,20\n2026-11-23,21\n", "DUPLICATE"),
    (b"observation_date,VXVCLS\n2026-11-27,20\n", "FUTURE_DATE"),
    (b"observation_date,VXVCLS\n2026-11-23,nan\n", "FINITE"),
    (b"observation_date,VXVCLS\n2026-11-23,-1\n", "FINITE"),
    (b"observation_date,VXVCLS\n2026-11-23,20,extra\n", "MALFORMED"),
    (b"observation_date,SP500\n2026-11-23,20\n", "HEADER"),
    (b"observation_date,VXVCLS\n2013-01-02,20\n", "NO_LIVE"),
])
def test_rejects_bad_source_rows(raw, reason):
    with pytest.raises(ValueError, match=reason):
        load(raw)


@pytest.mark.parametrize("changes,reason", [
    ({"sha256": "0" * 64}, "HASH"),
    ({"retrieved_at": "2026-11-28T00:00:00Z"}, "FUTURE_RETRIEVAL"),
    ({"retrieved_at": "2026-11-26T12:00:00"}, "AWARE"),
    ({"url": "https://example.org/data.csv"}, "UNREGISTERED"),
    ({"symbol": "VIX6M"}, "UNREGISTERED"),
])
def test_provenance_rejects(changes, reason):
    with pytest.raises(ValueError, match=reason):
        load(b"observation_date,VXVCLS\n2026-11-23,20\n", **changes)


def test_flat_curve_telescopes_in_decimal_units():
    curve = s5.term_curve(dict.fromkeys(s5.TERMS, 20.0))
    assert all(row["annualizedForwardVolPct"] == pytest.approx(20) for row in curve["segments"])
    assert sum((r["endDays"] - r["startDays"]) / 365 * r["annualizedForwardVariance"]
               for r in curve["segments"]) == pytest.approx(curve["totalVariance"]["VIX1Y"])


def test_negative_and_missing_are_never_zero_or_interpolated():
    curve = s5.term_curve({"VIX": 50, "VIX3M": 10, "VIX1Y": 20})
    segments = {r["to"]: r for r in curve["segments"]}
    assert segments["VIX3M"]["status"] == "NEGATIVE_FORWARD_PROXY"
    assert segments["VIX3M"]["annualizedForwardVariance"] < 0
    assert segments["VIX3M"]["annualizedForwardVolPct"] is None
    assert segments["VIX"]["status"] == segments["VIX1Y"]["status"] == "MISSING_ENDPOINT"
    assert segments["VIX1Y"]["annualizedForwardVariance"] is None


@pytest.mark.parametrize("vix,vix3m,expected", [(24.56, 24.29, 24.16), (35.89, 30.94, 28.28), (26.36, 25.47, 25.04)])
def test_observed_fred_table_transcription_not_raw_csv(vix, vix3m, expected):
    row = s5.term_curve({"VIX": vix, "VIX3M": vix3m})["segments"][2]
    assert round(row["annualizedForwardVolPct"], 2) == expected


def test_census_partial_panel_does_not_invent_common_days():
    r = s5.census({"VIX": {"2026-11-20": 35.89}, "VIX3M": {"2026-11-20": 30.94, "2026-11-23": 25.5}})
    assert r["allFiveCommonDays"] == 0
    assert r["observedUnionDays"] == 2
    assert r["series"]["VIX"]["missingOnObservedUnion"] == 1
    assert r["series"]["VIX6M"]["nonmissing"] == 0


def test_variance_premium_units_not_vol_difference():
    assert s5.risk_premium_proxy(30, .20**2) == pytest.approx(.05)
    with pytest.raises(ValueError):
        s5.risk_premium_proxy(30, math.inf)


def test_same_state_prices_opposite_physical_return():
    q, p1, p2, x, discount = [.25, .5, .25], [.1, .5, .4], [.4, .5, .1], [70, 100, 130], .98
    m1, m2 = s5.state_discount_witness(q, p1, discount), s5.state_discount_witness(q, p2, discount)
    assert [p * m for p, m in zip(p1, m1)] == pytest.approx([p * m for p, m in zip(p2, m2)])
    price = sum(p * m * payoff for p, m, payoff in zip(p1, m1, x))
    assert price == pytest.approx(98)
    assert sum(p * payoff for p, payoff in zip(p1, x)) > price
    assert sum(p * payoff for p, payoff in zip(p2, x)) < price
