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

# The real sessions around Samsung Electronics' one-for-fifty: 2018-05-01 is
# Labour Day and the stock was suspended 05-02 and 05-03 for the split, so the
# post-split price first printed on 05-04. A bdate_range would have put the
# split on 05-02, which is a date the event did not happen on.
SAMSUNG_SPLIT_SESSIONS = ["2018-04-30", "2018-05-02", "2018-05-04", "2018-05-08"]


def _frame(closes, shares, dates=None):
    dates = pd.to_datetime(dates or SAMSUNG_SPLIT_SESSIONS[:len(closes)])
    return pd.DataFrame({"Open": closes, "High": closes, "Low": closes,
                         "Close": closes, "Volume": [1000.0] * len(closes),
                         "ListedShares": shares}, index=pd.Index(dates, name="Date"))


def test_a_one_for_fifty_split_is_detected():
    """Samsung Electronics, 2018-05-04: 2,650,000 -> 53,000, shares x50."""
    frame = _frame([2650000.0, 2678000.0, 53000.0, 52900.0],
                   [128386494, 128386494, 6419324700, 6419324700])
    ratios = KP.detect_splits(frame)
    assert list(ratios.values) == [1.0, 1.0, 50.0, 1.0]


def test_a_reverse_split_is_detected_as_a_fraction():
    frame = _frame([1000.0, 1000.0, 5000.0, 5100.0],
                   [1000000, 1000000, 200000, 200000])
    assert KP.detect_splits(frame).iloc[2] == pytest.approx(0.2)


def test_a_rights_issue_is_not_a_split():
    """The share count rises and the price does NOT divide.

    Without the corroboration test this books a 1.3x split, and every session
    before it is multiplied by 1.3 — a 30% phantom decline across the name's
    whole history, in the direction that makes it look like a value stock.
    """
    frame = _frame([1000.0, 1000.0, 990.0, 995.0],
                   [1000000, 1000000, 1300000, 1300000])
    assert (KP.detect_splits(frame).values == 1.0).all()


def test_a_price_crash_without_a_share_change_is_not_a_split():
    frame = _frame([1000.0, 1000.0, 200.0, 210.0],
                   [1000000, 1000000, 1000000, 1000000])
    assert (KP.detect_splits(frame).values == 1.0).all()


def test_ordinary_share_drift_is_never_a_candidate():
    """Employee grants and small conversions move the count by fractions."""
    frame = _frame([1000.0, 999.0, 998.0, 997.0],
                   [1000000, 1001000, 1002000, 1003000])
    assert (KP.detect_splits(frame).values == 1.0).all()


def test_a_frame_without_share_counts_reports_no_splits():
    frame = _frame([1000.0, 500.0], [1, 1]).drop(columns=["ListedShares"])
    assert (KP.detect_splits(frame).values == 1.0).all()


# ------------------------------------------------------------ the round trip

def test_the_round_trip_returns_the_printed_prices_exactly():
    """The assertion this file exists for.

    KRX prints as-traded; `to_total_return` expects split-adjusted and undoes
    the adjustment. `to_vendor_basis` applies the adjustment the vendor never
    did, so the two cancel and what comes back is what printed.
    """
    printed = [2650000.0, 2678000.0, 53000.0, 52900.0]
    frame = _frame(printed, [128386494, 128386494, 6419324700, 6419324700])

    rebased, events = to_total_return(KP.to_vendor_basis(frame))

    assert list(np.round(rebased["Close"].to_numpy(), 6)) == pytest.approx(
        [2650000.0, 2678000.0, 2650000.0, 2645000.0])
    assert events == [{"date": "2018-05-04", "split": 50.0, "applied": True}]


def test_the_split_day_return_is_the_real_one_not_minus_ninety_eight_percent():
    printed = [2650000.0, 2678000.0, 53000.0, 52900.0]
    frame = _frame(printed, [128386494, 128386494, 6419324700, 6419324700])

    rebased, _ = to_total_return(KP.to_vendor_basis(frame))
    returns = rebased["Close"].pct_change().dropna().to_numpy()

    assert returns[1] == pytest.approx(-0.010456, abs=1e-6)   # the real move
    # What the same session looks like with no adjustment at all.
    assert pd.Series(printed).pct_change().iloc[2] == pytest.approx(
        -0.98021, abs=1e-5)


def test_the_vendor_basis_is_what_financedatareader_would_have_published():
    """Pre-split sessions divided down, so the frame matches FDR's shape."""
    frame = _frame([2650000.0, 2678000.0, 53000.0, 52900.0],
                   [128386494, 128386494, 6419324700, 6419324700])
    vendor = KP.to_vendor_basis(frame)
    assert vendor["Close"].to_numpy() == pytest.approx(
        [53000.0, 53560.0, 53000.0, 52900.0])
    assert list(vendor[SPLIT].to_numpy()) == [1.0, 1.0, 50.0, 1.0]


def test_volume_is_scaled_the_other_way_through_a_split():
    frame = _frame([1000.0, 100.0], [1000000, 10000000])
    vendor = KP.to_vendor_basis(frame)
    assert vendor["Volume"].to_numpy() == pytest.approx([10000.0, 1000.0])


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
    panel = KP.panel_from_rows(rows)
    assert set(panel) == {"A.KS", "B.KS"}
    assert list(panel["A.KS"]["Close"].to_numpy()) == [100.0, 101.0]
