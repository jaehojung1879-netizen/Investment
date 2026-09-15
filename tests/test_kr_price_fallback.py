"""The KRX fallback inside the Korean acquisition: when it fills, and when it must not.

FinanceDataReader serves 34.55% of delisted Korean names. The 139 names that
left the top-120 universe between 2013 and today are exactly the ones a
survivorship correction needs, and the KRX Open API lists what TRADED, so it
has all of them. This is where the two meet.

Three properties decide whether that is a fix or a new defect:

  * a name is served WHOLE by one vendor. Splicing two vendors' sessions into
    one ticker puts two price bases in one series and the seam reads as a
    return — the rule the existing Yahoo/FDR split already follows;
  * a SHORT history is not a gap. `coverage_shortfall` exists to catch a
    truncated primary, and quietly replacing one would hide exactly what it
    was built to refuse;
  * the fallback's own splits travel with it. `to_total_return` prefers
    explicit events over the frame's columns and Yahoo publishes nothing for a
    delisted Korean name, so passing only Yahoo's would discard every split
    the share counts established.
"""
from __future__ import annotations

import pandas as pd
import pytest

from pipeline import korea_prices as KR
from pipeline import krx_prices as KP
from pipeline import price_adjustment as PA


def _bars(closes, dates=None, shares=None):
    dates = pd.to_datetime(list(dates or pd.bdate_range("2013-01-02",
                                                        periods=len(closes))))
    return pd.DataFrame({"Open": closes, "High": closes, "Low": closes,
                         "Close": closes, "Volume": [10.0] * len(closes),
                         "ListedShares": shares or [100.0] * len(closes)},
                        index=pd.Index(dates, name="Date"))


def _acquire(tickers, sessions, fallback=None, actions=None):
    return KR.acquire(tickers, "2013-01-01",
                      session_fetcher=lambda names: dict(sessions),
                      action_fetcher=lambda names: dict(actions or {}),
                      fallback=fallback)


def test_a_name_the_primary_served_is_untouched():
    primary = _bars([100.0, 101.0, 102.0])
    spare = _bars([900.0, 900.0, 900.0])
    out = _acquire(["A.KS"], {"A.KS": primary}, {"A.KS": spare})
    assert out["fallbackTickers"] == []
    assert out["prices"]["A.KS"]["Close"].iloc[0] == pytest.approx(100.0)


def test_a_name_the_primary_served_nothing_for_is_filled():
    """The 139 departed names, and the reason this exists."""
    out = _acquire(["GONE.KS"], {}, {"GONE.KS": _bars([50.0, 51.0, 52.0])})
    assert out["fallbackTickers"] == ["GONE.KS"]
    assert out["routes"]["GONE.KS"] == "krx-open-api"
    assert out["missing"] == []


def test_an_empty_primary_frame_counts_as_nothing_served():
    out = _acquire(["GONE.KS"], {"GONE.KS": _bars([]).iloc[0:0]},
                   {"GONE.KS": _bars([50.0, 51.0])})
    assert out["fallbackTickers"] == ["GONE.KS"]


def test_a_short_primary_history_is_not_topped_up():
    """A truncated vendor is `coverage_shortfall`'s to refuse, not this one's.

    replay-v12 sealed 46,356 fewer Korean rows than v11 without one error
    because a vendor answered with a capped window. Filling that from a second
    source would have made it invisible instead of fatal.
    """
    short = _bars([100.0, 101.0])                      # two sessions
    long = _bars([50.0] * 200)                         # two hundred
    out = _acquire(["A.KS"], {"A.KS": short}, {"A.KS": long})
    assert out["fallbackTickers"] == []
    assert len(out["prices"]["A.KS"]) == 2


def test_no_fallback_leaves_the_acquisition_exactly_as_it_was():
    out = _acquire(["GONE.KS"], {}, None)
    assert out["missing"] == ["GONE.KS"] and out["prices"] == {}
    assert out.get("fallbackTickers") == []


def test_the_fallback_s_own_split_survives_into_the_rebased_series():
    """Yahoo has nothing for a delisted name, so its events must not win.

    `to_total_return` takes explicit events in preference to the frame's
    columns. Passing `event_columns(None)` — which is what a name Yahoo does
    not carry produces — would silently drop every split `detect_splits` found.
    """
    dates = list(pd.bdate_range("2018-04-30", periods=40))
    closes = [2650000.0, 2678000.0] + [53000.0] * 38
    shares = [128386494.0] * 2 + [6419324700.0] * 38
    vendor = KP.to_vendor_basis(_bars(closes, dates, shares))

    out = _acquire(["005930.KS"], {}, {"005930.KS": vendor})

    assert out["events"]["005930.KS"] == [
        {"date": "2018-05-02", "split": 50.0, "applied": True}]
    # As-traded levels, on the same basis as every primary-served name.
    assert out["prices"]["005930.KS"]["Close"].iloc[0] == pytest.approx(2650000.0)


def test_a_yahoo_dividend_still_applies_to_a_fallback_name():
    """KRX publishes no distributions; Yahoo's are taken when it has the name.

    Without this the fallback would be a price return even for a name whose
    dividends are perfectly well known.
    """
    dates = list(pd.bdate_range("2013-01-02", periods=4))
    vendor = KP.to_vendor_basis(_bars([100.0, 100.0, 100.0, 100.0], dates))
    actions = pd.DataFrame({PA.DIVIDEND: [0.0, 0.0, 5.0, 0.0],
                            PA.SPLIT: [0.0, 0.0, 0.0, 0.0]},
                           index=pd.Index(pd.to_datetime(dates), name="Date"))

    out = _acquire(["A.KS"], {}, {"A.KS": vendor}, actions={"A.KS": actions})

    assert [e for e in out["events"]["A.KS"] if e.get("dividend")] == [
        {"date": "2013-01-04", "dividend": 5.0, "applied": True}]


def test_a_yahoo_split_does_not_double_apply_on_a_fallback_name():
    """The share counts already established it; applying Yahoo's too squares it.

    Yahoo carries a living Korean name's splits, and a fallback name is one the
    PRIMARY could not serve — which is not the same as one Yahoo has never
    heard of. Taking its dividends without stripping its splits books the same
    fifty-for-one twice, and every session before it is off by 2,500.
    """
    dates = list(pd.bdate_range("2018-04-30", periods=40))
    closes = [2650000.0, 2678000.0] + [53000.0] * 38
    shares = [128386494.0] * 2 + [6419324700.0] * 38
    vendor = KP.to_vendor_basis(_bars(closes, dates, shares))
    yahoo = pd.DataFrame(
        {PA.DIVIDEND: [0.0] * 40,
         PA.SPLIT: [0.0, 0.0, 50.0] + [0.0] * 37},
        index=pd.Index(pd.to_datetime(dates), name="Date"))

    out = _acquire(["005930.KS"], {}, {"005930.KS": vendor},
                   actions={"005930.KS": yahoo})

    splits = [e for e in out["events"]["005930.KS"] if "split" in e]
    assert splits == [{"date": "2018-05-02", "split": 50.0, "applied": True}]
    assert out["prices"]["005930.KS"]["Close"].iloc[0] == pytest.approx(2650000.0)


def test_the_source_version_records_that_a_fallback_exists():
    """Provenance: a run that could reach the store is not the run that could not."""
    assert "open-api-fallback" in KR.SOURCE_VERSION


# ------------------------------------------------------------- the store

def test_the_panel_is_read_filtered_to_the_names_asked_for(tmp_path):
    """1.7 million rows; building 624 frames to keep twenty is 90 seconds wasted."""
    from pipeline import historical_store as HS

    rows = []
    for ticker in ("A.KS", "B.KS"):
        for date in pd.bdate_range("2013-01-02", periods=3):
            rows.append({"id": f"krx-price:{date:%Y-%m-%d}:{ticker[:1]}",
                         "date": date.strftime("%Y-%m-%d"), "region": "KR",
                         "ticker": ticker, "open": 10.0, "close": 10.0,
                         "volume": 1.0, "listedShares": 100.0})
    HS.write_shard(tmp_path / "krx-prices-2013.jsonl.gz", rows)

    panel, refused = KP.load_panel(tmp_path, ["A.KS"])
    assert set(panel) == {"A.KS"} and refused == {}


def test_an_absent_store_is_empty_rather_than_an_error(tmp_path):
    assert KP.load_panel(tmp_path / "nothing", ["A.KS"]) == ({}, {})
