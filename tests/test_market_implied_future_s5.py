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


def test_dispersion_zero_does_not_block_live_publisher_file():
    raw = b"DATE,DSPX\n02/08/2018,0.000000\n01/02/2024,15.75\n"
    data = load(raw, symbol="DSPX", url=s5.CBOE + "DSPX_History.csv")
    assert data["excludedPreLiveEraRows"] == 1
    assert data["rows"] == {"2024-01-02": 15.75}


def test_futures_validate_contract_and_keep_reported_zero_counts():
    from datetime import date

    from research.market_implied_future_s5.futures import parse_contract

    raw = (b"Trade Date,Futures,Settle,Total Volume,Open Interest\n"
           b"2026-11-17,X (Nov 2026),0,0,0\n2026-11-18,X (Nov 2026),20.10,1,2\n")
    parsed = parse_contract(raw, "2026-11-18", "2026-11-18T17:00:00Z")
    assert parsed[date(2026, 11, 17)] == {"settlement_index_points": None, "total_volume_contracts": 0,
                                        "open_interest_contracts": 0}
    assert parsed[date(2026, 11, 18)]["settlement_index_points"] == 20.1
    with pytest.raises(ValueError, match="DATE_OR_CONTRACT"):
        parse_contract(raw, "2026-12-16", "2026-11-18T17:00:00Z")


def test_snapshot_counts_missing_reference_days_without_using_union():
    from datetime import date, timedelta

    from research.market_implied_future_s5.snapshot import coverage, power_row, spaced_windows

    first = date(2026, 11, 23)
    second, third, fourth = (first + timedelta(days=i) for i in range(1, 4))
    result = coverage({first: 20., second: None, fourth: 20.}, [first, second, third], first, fourth)
    assert result["referenceSessions"] == 3
    assert result["absentOnReference"] == result["explicitMissingOnReference"] == result["nonmissingOffReference"] == 1
    assert spaced_windows([(first, third), (second, fourth)], third) == 1
    assert power_row(0)["mdeSdFor80PctPower"] is None
    assert power_row(7)["mdeSdFor80PctPower"] == pytest.approx(1.2725667)


def test_response_receipt_rejects_doctored_bytes(tmp_path):
    from datetime import datetime

    from research.market_implied_future_s5.snapshot import bytes_from_receipt

    f = tmp_path / "data.csv"
    f.write_bytes(b"123")
    row = {"path": "different-archive-path/data.csv", "bytes": 3,
           "sha256": hashlib.sha256(b"124").hexdigest(), "retrievedAtUtc": "2026-11-24T18:00:00Z"}
    with pytest.raises(ValueError, match="HASH"):
        bytes_from_receipt(tmp_path, row, datetime.fromisoformat("2026-11-25T18:00:00+00:00"))


def test_rate_limit_stops_requests_to_same_host(tmp_path):
    from urllib.error import HTTPError

    from research.market_implied_future_s5.acquire import acquire

    class RateLimited:
        def open(self, request, timeout):
            raise HTTPError(request.full_url, 429, "Too Many Requests", None, None)

    result = acquire(tmp_path / "raw", opener=RateLimited())
    assert result["admitted"] == 0
    assert sum(row["status"] == "HTTP_ERROR" for row in result["attempts"]) == 3
    assert sum(row["status"] == "NOT_REQUESTED_AFTER_HOST_RATE_LIMIT" for row in result["attempts"]) == 15


def test_state_prices_admit_exact_finite_quotes_and_reject_negative_butterfly():
    from research.market_implied_future_s5.state_prices import state_model, synthetic_witnesses

    result = state_model({("C", 100.): (10., 10.), ("P", 100.): (10., 10.), ("P", 80.): (0., 20.)},
                         200, (1., 1.), (80., 100.))
    assert result["riskNeutralTerminalForwardIndexPoints"] == pytest.approx([100., 100.])
    lo, hi = result["riskNeutralPutSpreadExpectation"]
    assert 0 <= lo < hi <= 1
    assert synthetic_witnesses()["negativeButterfly"]["status"] == "NO_FEASIBLE_SINGLE_EXPIRY_MODEL"


def test_expected_variance_requires_prior_observation_and_keeps_signed_difference():
    from datetime import datetime, timedelta, timezone

    from research.market_implied_future_s5.causal import ewma_expected_daily_variation, integrated_q_minus_expected_p

    day = datetime(2026, 10, 1, tzinfo=timezone.utc)
    rows = [((day + timedelta(days=i)).isoformat(), (day + timedelta(days=i, minutes=10)).isoformat(), .0002)
            for i in range(22)]
    decision = (day + timedelta(days=22)).isoformat()
    assert ewma_expected_daily_variation(rows, decision_at=decision) == pytest.approx(.0002)
    with pytest.raises(ValueError, match="CLOCK"):
        ewma_expected_daily_variation([*rows, (decision, decision, .001)], decision_at=decision)
    assert integrated_q_minus_expected_p(.003, .010, .0002, 40) == pytest.approx(-.001)
