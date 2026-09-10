"""The Korean price vendor: exchange-native sessions, Yahoo's distributions."""
import numpy as np
import pandas as pd
import pytest

from pipeline import korea_prices as KR
from pipeline import price_adjustment as PA
from pipeline import replay_inputs as RI


def _sessions(dates, closes):
    index = pd.to_datetime(dates)
    return pd.DataFrame({"Open": closes, "High": closes, "Low": closes,
                         "Close": closes, "Volume": [1000.0] * len(closes)},
                        index=index)


def _yahoo(dates, closes, dividends=None, splits=None):
    frame = _sessions(dates, closes)
    frame["Dividends"] = dividends or [0.0] * len(closes)
    frame["Stock Splits"] = splits or [0.0] * len(closes)
    return frame


# The session Yahoo does not have for 42 of 68 active Korean names, and the
# reason both selectors reported continuous_nav_has_unknown_intervals through
# replay v9, v10 and v11.
SESSIONS = ["2025-09-17", "2025-09-18", "2025-09-19", "2025-09-22", "2025-09-23"]
YAHOO_SESSIONS = ["2025-09-17", "2025-09-18", "2025-09-22", "2025-09-23"]


def test_the_session_yahoo_is_missing_is_present_because_fdr_has_it():
    fdr = {"271560.KS": _sessions(SESSIONS, [103.0, 104.0, 103.5, 102.9, 101.9])}
    yahoo = {"271560.KS": _yahoo(YAHOO_SESSIONS, [103.0, 104.0, 101.7, 100.7])}

    result = KR.acquire(["271560.KS"], "2025-09-01",
                        session_fetcher=lambda names: fdr,
                        action_fetcher=lambda names: yahoo)

    close = result["prices"]["271560.KS"]["Close"]
    assert "2025-09-19" in close.index.strftime("%Y-%m-%d").tolist()
    assert len(close) == 5
    # No splicing: the price on every session is the exchange-native one, not a
    # bridge between two vendors that disagree.
    assert close.to_numpy() == pytest.approx([103.0, 104.0, 103.5, 102.9, 101.9])


def test_the_vendor_disagreement_is_recorded_not_preferred_away():
    """Yahoo's Korean closes differ from FDR's by a median 55 bps on the sealed
    2025-09-19 panel. That is evidence about the second vendor, and it belongs
    in the ledger — silently dropping it is how the gap survived three
    generations."""
    fdr = {"A.KS": _sessions(SESSIONS, [100.0, 100.0, 100.0, 100.0, 100.0])}
    yahoo = {"A.KS": _yahoo(YAHOO_SESSIONS, [100.0, 101.0, 100.0, 100.0])}

    result = KR.acquire(["A.KS"], "2025-09-01",
                        session_fetcher=lambda names: fdr,
                        action_fetcher=lambda names: yahoo)

    row = result["agreement"][0]
    assert row["ticker"] == "A.KS"
    assert row["sharedSessions"] == 4
    assert row["onlyPrimarySessions"] == 1          # 2025-09-19, only FDR has it
    assert row["maxDifferenceBps"] == pytest.approx(100.0, rel=1e-6)

    summary = KR.agreement_summary(result["agreement"])
    assert summary["sessionsOnlyInPrimary"] == 1
    assert summary["sessionsOnlyInSecondary"] == 0
    assert summary["worstTicker"] == "A.KS"


def test_distributions_come_from_yahoo_and_accrue_on_the_fdr_price():
    """FDR serves no dividends. Both vendors quote to the same split basis, so
    the event carries across and the total return is built on KRX prices."""
    fdr = {"A.KS": _sessions(SESSIONS, [100.0, 100.0, 98.0, 98.0, 98.0])}
    yahoo = {"A.KS": _yahoo(YAHOO_SESSIONS, [100.0, 100.0, 98.0, 98.0],
                            dividends=[0.0, 0.0, 0.0, 0.0])}
    # The ex-date falls on the session Yahoo does not quote at all.
    yahoo["A.KS"] = _yahoo(["2025-09-17", "2025-09-18", "2025-09-19", "2025-09-22"],
                           [100.0, 100.0, 98.0, 98.0],
                           dividends=[0.0, 0.0, 2.0, 0.0])

    result = KR.acquire(["A.KS"], "2025-09-01",
                        session_fetcher=lambda names: fdr,
                        action_fetcher=lambda names: yahoo)

    close = result["prices"]["A.KS"]["Close"].to_numpy()
    # A 2.0 dividend off a 100.0 close exactly offsets the 2% price drop.
    assert close[2] / close[1] == pytest.approx(1.0, rel=1e-12)
    assert [row for row in result["events"]["A.KS"] if row.get("applied")]


def test_a_name_with_no_korean_sessions_is_reported_not_invented():
    result = KR.acquire(["A.KS", "B.KS"], "2025-09-01",
                        session_fetcher=lambda names: {
                            "A.KS": _sessions(SESSIONS, [1.0] * 5)},
                        action_fetcher=lambda names: {})
    assert result["missing"] == ["B.KS"] and set(result["prices"]) == {"A.KS"}


def test_the_sealed_price_lineage_is_not_mistaken_for_a_price_panel(tmp_path):
    """`price/source` shares the panels' prefix and carries no date or Close.

    The identical shape in `benchmark/source` killed the first replay-v10 audit
    with KeyError: 'date' because one prefix test had not been taught about it.
    """
    assert not RI.is_price_panel(RI.PRICE_SOURCE)
    lineage = [{"region": "KR", "vendor": "FINANCE_DATA_READER",
                "source": KR.SOURCE_VERSION}]
    store = RI.InputStore(tmp_path, "r", "d")
    manifest = store.commit(
        {RI.PRICE_SOURCE: lineage,
         "price/2025-09": [{"date": "2025-09-19", "ticker": "A.KS", "Close": 1.0}]},
        through="2025-09-30", policy={})
    assert store.load(manifest, valuation_only=True)[RI.PRICE_SOURCE] == lineage


def test_fdr_bars_take_the_same_forward_total_return_treatment_as_yahoo():
    """Naver quotes split-adjusted, dividend-unadjusted closes — the same shape
    as Yahoo's unadjusted close — so one adjustment serves both vendors."""
    dates = ["2025-09-17", "2025-09-18", "2025-09-19", "2025-09-22"]
    events = pd.DataFrame({PA.DIVIDEND: [0.0, 0.0, 0.0, 0.0],
                           PA.SPLIT: [0.0, 0.0, 2.0, 0.0]},
                          index=pd.to_datetime(dates))
    fdr = _sessions(dates, [50.0, 50.5, 51.0, 51.5])
    rebased, rows = PA.to_total_return(fdr, events)
    assert rebased["Close"].to_numpy() == pytest.approx(
        [100.0, 101.0, 102.0, 103.0], rel=1e-12)
    assert any(row.get("split") == 2.0 for row in rows)


def test_a_truncated_primary_download_is_caught_by_the_cross_check():
    """The check replay-v12 did not have.

    FinanceDataReader's default Naver endpoint takes no date argument: it
    returns a fixed trailing window and the reader slices it, so `start` is
    ignored. v12 sealed a Korean panel where 56 of 68 names began on 2014-06-23
    instead of 2011-01-03 — 46,356 rows gone — and nothing failed, because a
    short answer is still a successful answer. Only the other vendor knows.
    """
    full = pd.bdate_range("2011-01-03", periods=400)
    truncated = full[300:]
    primary = {"A.KS": _sessions(full.strftime("%Y-%m-%d"), [100.0] * len(full)),
               "B.KS": _sessions(truncated.strftime("%Y-%m-%d"),
                                 [100.0] * len(truncated))}
    yahoo = {ticker: _yahoo(full.strftime("%Y-%m-%d"), [100.0] * len(full))
             for ticker in primary}

    result = KR.acquire(["A.KS", "B.KS"], "2011-01-01",
                        session_fetcher=lambda names: primary,
                        action_fetcher=lambda names: yahoo)
    shortfall = KR.coverage_shortfall(result["agreement"])

    assert shortfall["tickers"] == 1
    assert shortfall["worst"][0]["ticker"] == "B.KS"
    assert shortfall["worst"][0]["sessions"] == 300
    assert shortfall["worst"][0]["secondaryFirstSession"] == "2011-01-03"


def test_a_genuinely_late_listing_is_not_a_truncated_download():
    """Both vendors start late together, so the difference is zero."""
    late = pd.bdate_range("2020-01-01", periods=100).strftime("%Y-%m-%d")
    result = KR.acquire(["A.KS"], "2011-01-01",
                        session_fetcher=lambda names: {
                            "A.KS": _sessions(late, [100.0] * len(late))},
                        action_fetcher=lambda names: {
                            "A.KS": _yahoo(late, [100.0] * len(late))})
    assert KR.coverage_shortfall(result["agreement"])["tickers"] == 0


def test_only_the_bar_is_sealed_not_the_vendors_derived_columns():
    """KRX serves Change, MarCap and Shares beside the bar; Naver serves Change.

    v12 sealed that Change column into every Korean price row — a pct_change
    computed on the pre-adjustment basis, stored next to a Close that no longer
    matches it, and absent from the US rows.
    """
    from pipeline import datafeed

    dates = pd.bdate_range("2025-09-01", periods=3)
    served = pd.DataFrame({"Open": 1.0, "High": 1.0, "Low": 1.0, "Close": 1.0,
                           "Volume": 10.0, "Change": 0.01, "MarCap": 1e12,
                           "Shares": 1e8}, index=dates)

    class _Reader:
        @staticmethod
        def DataReader(symbol, start, end=None):
            assert symbol.startswith("KRX:"), "must ask KRX, not the capped default"
            return served

    import sys
    sys.modules["FinanceDataReader"] = _Reader
    try:
        out = datafeed.fetch_fdr_prices(["005930.KS"], "2011-01-01")
    finally:
        del sys.modules["FinanceDataReader"]

    assert sorted(out["005930.KS"].columns) == sorted(datafeed.OHLCV)
