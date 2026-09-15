"""KOSPI bars from KRX: the basis, the splits, and the silent factor of fifty.

Membership put 139 departed names back into the Korean cross-section.
FinanceDataReader can price 34.55% of them, so the rest are described and
unpriceable, which `unvouched` counts exactly as it counts unknown. This module
fills that from the endpoint that already answered the membership question.

The failure mode worth the most care does not raise, does not look wrong, and
is enormous. `price_adjustment.to_total_return` expects a SPLIT-ADJUSTED frame
and multiplies each session by the splits that come after it, to recover the
price that printed. KRX quotes the printed price already. Hand its bars over
unchanged and every session before Samsung Electronics' 2018 one-for-fifty is
multiplied by fifty — which reads as a spectacular decade of momentum rather
than as a bug, and would be sealed into a generation before anyone asked.

So the round trip is pinned here, on the real split: as-traded in, vendor basis
out, `to_total_return` back, and the printed prices must return EXACTLY.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pipeline import krx_prices as KP
from pipeline.price_adjustment import SPLIT, to_total_return


def _payload(rows, key="OutBlock_1"):
    return {key: rows}


def _row(code, close, shares="1000", date="20130102", **extra):
    row = {"ISU_CD": code, "BAS_DD": date, "TDD_CLSPRC": close,
           "TDD_OPNPRC": close, "TDD_HGPRC": close, "TDD_LWPRC": close,
           "ACC_TRDVOL": "10", "LIST_SHRS": shares}
    row.update(extra)
    return row


# ---------------------------------------------------------------- parsing

def test_a_session_becomes_bars():
    bars, error = KP.parse_bars(_payload([_row("005930", "1,500,000",
                                               shares="147,299,337")]))
    assert error is None
    assert bars == [{"code": "005930", "open": 1500000.0, "high": 1500000.0,
                     "low": 1500000.0, "close": 1500000.0, "volume": 10.0,
                     "listedShares": 147299337.0}]


def test_a_row_without_a_close_is_not_a_session():
    """A NaN bar in the panel is worse than a missing one.

    `has_history` counts rows, not finite closes, so a priceless row would let
    a name into a cross-section it cannot be ranked in.
    """
    bars, error = KP.parse_bars(_payload([
        _row("000001", "100"), _row("000002", "-")]))
    assert error is None
    assert [b["code"] for b in bars] == ["000001"]


def test_a_missing_rows_key_is_an_error_not_a_closed_exchange():
    bars, error = KP.parse_bars({"respMsg": "Unauthorized API Call"})
    assert bars == [] and error and "no rows key" in error


def test_an_empty_rows_list_is_a_closed_exchange():
    assert KP.parse_bars(_payload([])) == ([], None)


def test_duplicate_codes_are_taken_once():
    bars, _ = KP.parse_bars(_payload([_row("000001", "100"),
                                      _row("000001", "999")]))
    assert len(bars) == 1 and bars[0]["close"] == 100.0


# ---------------------------------------------------------------- rows

def test_only_the_universe_tickers_are_kept():
    """The one collector-side policy, and it is a storage bound.

    The endpoint answers with the whole exchange; a decade of that daily is
    hundreds of megabytes. The membership names the only tickers that can ever
    enter the cross-section.
    """
    bars, _ = KP.parse_bars(_payload([_row("000001", "100"),
                                      _row("999999", "200")]))
    rows = KP.bar_rows("2013-01-02", bars, keep={"000001.KS"})
    assert [r["ticker"] for r in rows] == ["000001.KS"]


def test_no_keep_set_keeps_everything():
    bars, _ = KP.parse_bars(_payload([_row("000001", "100"),
                                      _row("999999", "200")]))
    assert len(KP.bar_rows("2013-01-02", bars, None)) == 2


def test_rows_carry_a_stable_id_and_the_store_s_sort_fields():
    bars, _ = KP.parse_bars(_payload([_row("005930", "100")]))
    row = KP.bar_rows("2013-01-02", bars, None)[0]
    assert row["id"] == "krx-price:2013-01-02:005930"
    assert row["date"] == "2013-01-02" and row["region"] == "KR"
    assert row["ticker"] == "005930.KS"


# ---------------------------------------------------------------- calendar

def test_weekends_are_never_asked_about():
    """Two calls in seven spent on a certain answer is two in seven wasted."""
    days = KP.calendar_days("2013-01-05", "2013-01-13")   # Sat .. Sun
    assert days == ["2013-01-07", "2013-01-08", "2013-01-09",
                    "2013-01-10", "2013-01-11"]


def test_the_whole_replay_span_is_a_few_thousand_weekdays():
    days = KP.calendar_days("2013-01-01", "2026-09-15")
    assert 3500 <= len(days) <= 3650, len(days)


def test_no_holiday_step_forward_unlike_the_monthly_walk():
    """A shut day has no nearest session to find — stepping would double-count.

    The membership walk asks about the 1st of a month and steps forward to the
    next open session, because it wants A session near that date. Here every
    session is wanted exactly once.
    """
    assert "2013-01-01" in KP.calendar_days("2013-01-01", "2013-01-03")


# ---------------------------------------------------------------- splits

SAMSUNG_SPLIT_SESSIONS = ["2018-04-30", "2018-05-02", "2018-05-04", "2018-05-08"]


def _frame(closes, shares, dates=None, volume=1000.0):
    if dates is None:
        dates = SAMSUNG_SPLIT_SESSIONS[:len(closes)]
    dates = pd.to_datetime(list(dates))
    return pd.DataFrame({"Open": closes, "High": closes, "Low": closes,
                         "Close": closes, "Volume": [volume] * len(closes),
                         "ListedShares": shares},
                        index=pd.Index(dates, name="Date"))


def _long(closes, shares, dates=None):
    """The given sessions, then quiet room after them.

    `detect_splits` books nothing in the last `LIQUIDATION_SESSIONS`, so a
    four-row fixture would silently exercise that guard instead of the rule
    under test. The padding keeps the real session dates on the real rows.
    """
    dates = list(pd.to_datetime(list(dates or SAMSUNG_SPLIT_SESSIONS[:len(closes)])))
    tail = pd.bdate_range(dates[-1] + pd.Timedelta(days=1),
                          periods=KP.LIQUIDATION_SESSIONS)
    return _frame(list(closes) + [closes[-1]] * KP.LIQUIDATION_SESSIONS,
                  list(shares) + [shares[-1]] * KP.LIQUIDATION_SESSIONS,
                  dates=dates + list(tail))


def test_a_one_for_fifty_split_is_detected():
    """Samsung Electronics, 2018-05-04: 2,650,000 -> 53,000, shares x50."""
    frame = _long([2650000.0, 2678000.0, 53000.0, 52900.0],
                  [128386494, 128386494, 6419324700, 6419324700])
    assert list(KP.detect_splits(frame).values[:4]) == [1.0, 1.0, 50.0, 1.0]


def test_a_reverse_split_is_detected_as_a_fraction():
    frame = _long([1000.0, 1000.0, 5000.0, 5100.0],
                  [1000000, 1000000, 200000, 200000])
    assert KP.detect_splits(frame).iloc[2] == pytest.approx(0.2)


def test_a_share_registry_that_lags_the_ex_date_by_a_month_still_confirms():
    """The finding that made run #3 refuse 150 tickers it should have kept.

    `064960.KS` went ex-split on 2025-01-24 — the close halved — and
    `LIST_SHRS` did not move until 2025-02-26, thirty-three days later, because
    the field updates when the new shares are formally listed. Same-session
    corroboration cannot see that at all.
    """
    dates = list(pd.bdate_range("2025-01-22", periods=40))
    closes = [51000.0, 51000.0] + [25500.0] * 38
    shares = [14623136.0] * 25 + [26540272.0] * 15     # registry moves on day 25
    frame = _frame(closes, shares, dates=dates)

    ratios = KP.detect_splits(frame)
    assert ratios.iloc[2] == pytest.approx(2.0)
    assert (ratios.drop(ratios.index[2]).values == 1.0).all()


def test_the_confirming_move_need_not_equal_the_ratio_exactly():
    """064960's share count printed 1.815, not 2.0 — an issuance settled too.

    Requiring the exact factor would refuse the very case this window exists
    for, so the test is whether the count moved TOWARDS the implied ratio.
    """
    dates = list(pd.bdate_range("2025-01-22", periods=40))
    frame = _frame([51000.0, 51000.0] + [25500.0] * 38,
                   [14623136.0] * 25 + [14623136.0 * 1.815] * 15, dates=dates)
    assert KP.detect_splits(frame).iloc[2] == pytest.approx(2.0)


def test_a_spin_off_halves_the_price_and_is_not_a_split():
    """The share count never moves, so nothing confirms the candidate.

    `267260.KS` printed exactly -50% on 2018-11-23 against a share count that
    was identical before, on and after. Booking that as a two-for-one doubles
    every earlier session.
    """
    frame = _long([45000.0, 44650.0, 22150.0, 23800.0],
                  [10205783, 10205783, 10205783, 10205783])
    assert (KP.detect_splits(frame).values == 1.0).all()


def test_a_small_issuance_near_a_spin_off_does_not_confirm_it():
    """The directional half of the confirmation, which no other test reaches.

    `test_a_spin_off_...` has no share movement at all, so it passes whether or
    not the confirmation asks WHICH WAY the count moved. Here the count moves
    2% inside the window — real, and nothing like the doubling a two-for-one
    needs. Accepting any nearby move books the spin-off as a split and doubles
    every earlier session.
    """
    dates = list(pd.bdate_range("2018-11-19", periods=40))
    closes = [45000.0] * 4 + [22150.0] * 36
    shares = [10205783.0] * 10 + [10205783.0 * 1.02] * 30
    assert (KP.detect_splits(_frame(closes, shares, dates=dates)).values == 1.0).all()


def test_a_rights_issue_is_not_a_split():
    """The share count rises and the price does NOT divide by a clean ratio."""
    frame = _long([1000.0, 1000.0, 990.0, 995.0],
                  [1000000, 1000000, 1300000, 1300000])
    assert (KP.detect_splits(frame).values == 1.0).all()


def test_a_twelve_percent_issuance_is_never_a_candidate():
    """`017800.KS 2013-01-10`: shares +12.1%, price +2.2%, booked x1.12113.

    The first version used a RELATIVE tolerance around the share ratio, which
    at 1.12 covers "the price did not move", so every issuance under a fifth
    became a split. A split ratio is a par-value ratio; 1.12113 is not one.
    """
    frame = _long([117500.0, 112500.0, 115000.0, 110000.0],
                  [10732513, 10732513, 12032513, 12032513])
    assert (KP.detect_splits(frame).values == 1.0).all()


def test_ordinary_share_drift_is_never_a_candidate():
    frame = _long([1000.0, 999.0, 998.0, 997.0],
                  [1000000, 1001000, 1002000, 1003000])
    assert (KP.detect_splits(frame).values == 1.0).all()


def test_nothing_is_booked_inside_the_liquidation_window():
    """정리매매 runs with no price limit, and that collapse is the signal.

    A -50% in the fortnight before a delisting is the survivorship return this
    whole exercise exists to recover; adjusting it away as a split would delete
    exactly what was being looked for.
    """
    dates = list(pd.bdate_range("2017-02-20", periods=6))
    frame = _frame([1000.0, 1000.0, 500.0, 480.0, 470.0, 460.0],
                   [1000000, 1000000, 2000000, 2000000, 2000000, 2000000],
                   dates=dates)
    assert (KP.detect_splits(frame).values == 1.0).all()


def test_a_frame_without_share_counts_reports_no_splits():
    frame = _long([1000.0, 1000.0, 500.0, 510.0],
                  [1, 1, 1, 1]).drop(columns=["ListedShares"])
    assert (KP.detect_splits(frame).values == 1.0).all()


@pytest.mark.parametrize("value,expected", [
    (50.0, 50.0), (2.0, 2.0), (0.2, 0.2), (10.4, 10.0), (1.9, 2.0)])
def test_clean_ratios_are_recognised(value, expected):
    assert KP.nearest_clean_ratio(value) == pytest.approx(expected)


@pytest.mark.parametrize("value", [1.0, 1.12113, 1.19822, 0.6849, 1.5, None, 0.0, -2.0])
def test_a_ratio_that_is_not_a_par_value_change_is_refused(value):
    assert KP.nearest_clean_ratio(value) is None


# ------------------------------------------------------------ the round trip

def test_the_round_trip_returns_the_printed_prices_exactly():
    """The assertion this file exists for.

    KRX prints as-traded; `to_total_return` expects split-adjusted and undoes
    the adjustment. `to_vendor_basis` applies the adjustment the vendor never
    did, so the two cancel and what comes back is what printed.
    """
    printed = [2650000.0, 2678000.0, 53000.0, 52900.0]
    frame = _long(printed, [128386494, 128386494, 6419324700, 6419324700])

    rebased, events = to_total_return(KP.to_vendor_basis(frame))
    rebased = rebased.iloc[:4]

    assert list(np.round(rebased["Close"].to_numpy(), 6)) == pytest.approx(
        [2650000.0, 2678000.0, 2650000.0, 2645000.0])
    assert events == [{"date": "2018-05-04", "split": 50.0, "applied": True}]


def test_the_split_day_return_is_the_real_one_not_minus_ninety_eight_percent():
    printed = [2650000.0, 2678000.0, 53000.0, 52900.0]
    frame = _long(printed, [128386494, 128386494, 6419324700, 6419324700])

    rebased, _ = to_total_return(KP.to_vendor_basis(frame))
    returns = rebased["Close"].pct_change().dropna().to_numpy()

    assert returns[1] == pytest.approx(-0.010456, abs=1e-6)   # the real move
    # What the same session looks like with no adjustment at all.
    assert pd.Series(printed).pct_change().iloc[2] == pytest.approx(
        -0.98021, abs=1e-5)


def test_the_vendor_basis_is_what_financedatareader_would_have_published():
    """Pre-split sessions divided down, so the frame matches FDR's shape."""
    frame = _long([2650000.0, 2678000.0, 53000.0, 52900.0],
                  [128386494, 128386494, 6419324700, 6419324700])
    vendor = KP.to_vendor_basis(frame)
    assert vendor["Close"].to_numpy()[:4] == pytest.approx(
        [53000.0, 53560.0, 53000.0, 52900.0])
    assert list(vendor[SPLIT].to_numpy()[:4]) == [1.0, 1.0, 50.0, 1.0]


def test_volume_is_scaled_the_other_way_through_a_split():
    frame = _long([1000.0, 1000.0, 100.0], [1000000, 1000000, 10000000])
    vendor = KP.to_vendor_basis(frame)
    assert vendor["Volume"].to_numpy()[:3] == pytest.approx([10000.0, 10000.0, 1000.0])


def test_dividends_are_written_as_zeros_because_krx_publishes_none():
    """An absent column and a column of zeros mean the same to the adjuster.

    They do not mean the same to a reader: the zeros say the question was
    asked, so the price-return basis of these names is on the record rather
    than inferred from a missing field.
    """
    from pipeline.price_adjustment import DIVIDEND

    vendor = KP.to_vendor_basis(_frame([100.0, 101.0], [10, 10]))
    assert (vendor[DIVIDEND].to_numpy() == 0.0).all()


def test_a_frame_with_no_split_passes_through_unchanged():
    frame = _frame([100.0, 101.0, 102.0], [10, 10, 10])
    vendor = KP.to_vendor_basis(frame)
    assert vendor["Close"].to_numpy() == pytest.approx([100.0, 101.0, 102.0])


# ---------------------------------------------------------------- the panel

def test_the_panel_splits_rows_by_ticker_and_sorts_each_by_date():
    rows = [
        {"date": "2013-01-03", "ticker": "A.KS", "close": 101.0, "open": 101.0,
         "volume": 1.0, "listedShares": 10.0},
        {"date": "2013-01-02", "ticker": "A.KS", "close": 100.0, "open": 100.0,
         "volume": 1.0, "listedShares": 10.0},
        {"date": "2013-01-02", "ticker": "B.KS", "close": 50.0, "open": 50.0,
         "volume": 1.0, "listedShares": 10.0},
    ]
    panel, refused = KP.panel_from_rows(rows)
    assert set(panel) == {"A.KS", "B.KS"} and refused == {}
    assert list(panel["A.KS"]["Close"].to_numpy()) == [100.0, 101.0]


# ------------------------------------------------- suspensions and refusals

def test_a_zero_volume_row_is_not_a_session():
    """KRX carries a suspended issue's last close forward.

    `071970.KS` printed 2,765 on four consecutive days it did not trade and
    then 55,300 on four more. Keeping those rows puts flat bars into the panel
    and dumps the whole suspension into one printed return — which is what made
    run #3's audit report +1,900%.
    """
    rows = [{"date": "2017-03-27", "close": 2765.0, "open": 2765.0,
             "volume": 0.0, "listedShares": 10.0},
            {"date": "2017-03-28", "close": 2765.0, "open": 2765.0,
             "volume": 100.0, "listedShares": 10.0}]
    frame = KP.frame_from_rows(rows)
    assert list(frame.index.strftime("%Y-%m-%d")) == ["2017-03-28"]


def test_the_suspended_rows_are_still_kept_in_the_store():
    """Dropping them at DERIVATION time keeps the record of the suspension."""
    rows = [{"date": "2017-03-27", "close": 2765.0, "open": 2765.0,
             "volume": 0.0, "listedShares": 10.0}]
    assert len(KP.frame_from_rows(rows, traded_only=False)) == 1
    assert len(KP.frame_from_rows(rows)) == 0


def _session_frame(closes, dates, shares=10.0):
    return _frame(closes, [shares] * len(closes), dates=dates)


def test_an_unexplained_move_between_adjacent_sessions_is_reported():
    dates = list(pd.bdate_range("2018-01-01", periods=40))
    closes = [1000.0] * 20 + [300.0] * 20          # -70% on one session
    found = KP.unexplained_moves(KP.to_vendor_basis(_session_frame(closes, dates)))
    assert [m["movePct"] for m in found] == [pytest.approx(-70.0)]


def test_a_move_across_a_suspension_is_not_unexplained():
    """The gap is months, so the move is a cumulative return, not one day's."""
    dates = ["2018-01-02", "2018-01-03", "2018-07-02"] + list(
        pd.bdate_range("2018-07-03", periods=KP.LIQUIDATION_SESSIONS + 2))
    closes = [1000.0, 1000.0, 300.0] + [300.0] * (KP.LIQUIDATION_SESSIONS + 2)
    assert KP.unexplained_moves(KP.to_vendor_basis(
        _session_frame(closes, dates))) == []


def test_a_collapse_in_the_liquidation_window_is_not_unexplained():
    """정리매매 runs with the price limit lifted, and that is the signal.

    한진해운 printed -68% there in March 2017. Refusing the ticker over it
    would delete exactly the survivorship return this exercise is for.
    """
    dates = list(pd.bdate_range("2017-01-02", periods=25))
    closes = [1000.0] * 20 + [320.0] * 5           # collapse near the end
    assert KP.unexplained_moves(KP.to_vendor_basis(
        _session_frame(closes, dates))) == []


def test_a_move_inside_the_daily_limit_is_never_reported():
    dates = list(pd.bdate_range("2018-01-01", periods=40))
    closes = [1000.0] * 20 + [750.0] * 20          # -25%, within the limit
    assert KP.unexplained_moves(KP.to_vendor_basis(
        _session_frame(closes, dates))) == []


def test_the_panel_refuses_a_ticker_it_cannot_account_for(): 
    """A named gap beats a fabricated return inside a momentum signal."""
    dates = list(pd.bdate_range("2018-01-01", periods=40))
    rows = []
    for name, closes in (("OK.KS", [1000.0] * 40),
                         ("BAD.KS", [1000.0] * 20 + [300.0] * 20)):
        for date, close in zip(dates, closes):
            rows.append({"date": date.strftime("%Y-%m-%d"), "ticker": name,
                         "close": close, "open": close, "volume": 10.0,
                         "listedShares": 10.0})
    panel, refused = KP.panel_from_rows(rows)
    assert set(panel) == {"OK.KS"}
    assert set(refused) == {"BAD.KS"}
    assert refused["BAD.KS"][0]["movePct"] == pytest.approx(-70.0)


def test_refusal_can_be_switched_off_for_inspection():
    dates = list(pd.bdate_range("2018-01-01", periods=40))
    closes = [1000.0] * 20 + [300.0] * 20
    rows = [{"date": d.strftime("%Y-%m-%d"), "ticker": "BAD.KS", "close": c,
             "open": c, "volume": 10.0, "listedShares": 10.0}
            for d, c in zip(dates, closes)]
    panel, refused = KP.panel_from_rows(rows, refuse_unexplained=False)
    assert set(panel) == {"BAD.KS"} and refused == {}
