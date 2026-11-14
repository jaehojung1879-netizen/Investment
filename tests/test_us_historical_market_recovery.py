"""Invented prices only. No real research labels, raw vendor data, or network."""
import pandas as pd
import pytest
import hashlib
import json

from research.us_historical_market_recovery_v1.engine import Series, Unresolved, frame_series, holding, ranges, whole_window_source
from research.us_historical_market_recovery_v1.collect import private_root


def source(days, values, *, good=None):
    x = pd.Series(values, index=pd.to_datetime(days), dtype=float)
    return Series("SYN", x, x.copy(), set(good or days), "SYNTHETIC_FIXTURE", "0" * 64, True, True)


def test_cash_merger_uses_cited_consideration_and_keeps_cash():
    days = ["2020-01-02", "2020-01-03", "2020-01-06", "2020-01-07"]
    series = source(days[:2], [100, 110])
    terminal = {"date": days[2], "last_trading_date": days[1], "cash": 120, "verified": True, "citation": "synthetic"}
    assert holding(series, days[0], days[-1], days, terminal=terminal) == pytest.approx(.2)


def test_unknown_terminal_is_not_last_close_or_zero():
    days = ["2020-01-02", "2020-01-03", "2020-01-06"]
    series = source(days[:2], [100, 110])
    with pytest.raises(Unresolved, match="PRICE_PATH_GAP"):
        holding(series, days[0], days[-1], days)
    terminal = {"date": days[2], "last_trading_date": days[1], "verified": True, "citation": "synthetic"}
    with pytest.raises(Unresolved, match="TERMINAL_CONSIDERATION_MISSING"):
        holding(series, days[0], days[-1], days, terminal=terminal)


def test_missing_cvr_cannot_be_replaced_by_zero():
    days = ["2020-01-02", "2020-01-03", "2020-01-06"]
    terminal = {"date": days[1], "last_trading_date": days[0], "cash": 50, "cvr": True, "verified": True, "citation": "synthetic"}
    with pytest.raises(Unresolved, match="CVR_MARK_OR_PAYOFF_MISSING"):
        holding(source(days[:1], [100]), days[0], days[-1], days, terminal=terminal)


def test_successor_cash_and_stock_are_carried_to_same_horizon():
    days = ["2020-01-02", "2020-01-03", "2020-01-06"]
    original = source(days[:1], [100])
    successor = source(days[1:], [200, 220])
    terminal = {"date": days[1], "last_trading_date": days[0], "cash": 20, "shares": 1.5,
                "successor": "NEW", "verified": True, "citation": "synthetic", "cash_in_lieu_required": True}
    with pytest.raises(Unresolved, match="FRACTIONAL_SHARE_SETTLEMENT_UNRESOLVED"):
        holding(original, days[0], days[-1], days, terminal=terminal, successors={"NEW": successor})
    terminal["fractional_reference_shares_authorized"] = True
    assert holding(original, days[0], days[-1], days, terminal=terminal, successors={"NEW": successor}) == pytest.approx(2.5)


def test_cited_old_common_cancellation_is_separate_from_missing_payoff():
    days = ["2020-01-02", "2020-01-03"]
    terminal = {"date": days[1], "last_trading_date": days[0], "zero_confirmed": True, "verified": True, "citation": "synthetic cancellation"}
    assert holding(source(days[:1], [100]), days[0], days[-1], days, terminal=terminal) == -1


def test_nontrading_carried_quote_does_not_fill_a_halt():
    days = ["2020-01-02", "2020-01-03", "2020-01-06"]
    series = source(days, [100, 100, 110], good=[days[0], days[-1]])
    with pytest.raises(Unresolved, match="PRICE_PATH_GAP"):
        holding(series, days[0], days[-1], days)


def test_adjusted_series_cannot_receive_distributions_again():
    frame = pd.DataFrame({"Close": [100., 101.]}, index=pd.to_datetime(["2020-01-02", "2020-01-03"]))
    with pytest.raises(Unresolved, match="ALREADY_ADJUSTED_OR_UNKNOWN_BASIS"):
        frame_series("SYN", frame, source="SYNTHETIC", receipt="0" * 64, basis="TOTAL_RETURN_ADJUSTED")


def test_raw_output_rejects_a_real_git_directory(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git/HEAD").write_text("ref: refs/heads/synthetic")
    with pytest.raises(ValueError, match="RAW_DATA_MUST_STAY_OUTSIDE"):
        private_root(tmp_path / "prices")


def test_identity_admission_is_required_before_a_return():
    days = ["2020-01-02", "2020-01-03"]
    s = source(days, [100, 200])
    s.identity_verified = False
    with pytest.raises(Unresolved, match="SECURITY_OR_ACTION_ADMISSION_UNRESOLVED"):
        holding(s, *days, days)


def test_gap_ranges_never_include_an_observed_exchange_session():
    calendar = ["2020-01-02", "2020-01-03", "2020-01-06", "2020-01-07"]
    assert ranges([calendar[0], calendar[2], calendar[3]], calendar) == [
        {"from": calendar[0], "through": calendar[0]}, {"from": calendar[2], "through": calendar[3]}]


def test_whole_window_selection_never_splices_or_hides_an_internal_gap():
    days = ["2020-01-02", "2020-01-03", "2020-01-06"]
    old = source(days, [100, 101, 102])
    recent = source(days[1:], [201, 202])
    assert whole_window_source(recent, old, days[0], days[-1]) is old
    recent.good_days.remove(days[1])
    chosen = whole_window_source(recent, old, days[1], days[-1])
    assert chosen is recent
    with pytest.raises(Unresolved, match="ENTRY_PRICE_MISSING_OR_NOT_TRADABLE"):
        holding(chosen, days[1], days[-1], days)


def test_scoped_ex_date_keeps_its_previous_close_and_rejects_missing_in_scope(tmp_path):
    from research.us_historical_market_recovery_v1.audit import chart_series
    days = pd.to_datetime(["2020-01-02", "2020-01-03", "2020-01-06"], utc=True)
    stamp = [int(d.timestamp()) for d in days]
    row = {"meta": {"currency": "USD"}, "timestamp": stamp,
           "indicators": {"quote": [{"open": [100, 99, 100], "high": [100, 99, 100],
                            "low": [100, 99, 100], "close": [100, 99, 100], "volume": [1, 1, 1]}],
                          "adjclose": [{"adjclose": [99, 99, 100]}]},
           "events": {"dividends": {"ex": {"date": stamp[1], "amount": 1}}}}
    raw = json.dumps({"chart": {"result": [row]}}).encode()
    (tmp_path / "synthetic.json").write_bytes(raw)
    record = {"ticker": "SYN", "object": "synthetic.json", "sha256": hashlib.sha256(raw).hexdigest()}
    series, _, _ = chart_series(record, tmp_path, from_day="2020-01-03")
    assert "2020-01-02" in series.good_days
    assert series.tr.loc["2020-01-03"] == pytest.approx(series.tr.loc["2020-01-02"])
    row["events"]["dividends"]["missing"] = {"date": int(pd.Timestamp("2020-01-04", tz="UTC").timestamp()), "amount": 1}
    raw = json.dumps({"chart": {"result": [row]}}).encode()
    (tmp_path / "synthetic.json").write_bytes(raw)
    record["sha256"] = hashlib.sha256(raw).hexdigest()
    with pytest.raises(Unresolved, match="CORPORATE_ACTION_ON_ABSENT_PRICE_SESSION"):
        chart_series(record, tmp_path, from_day="2020-01-03")
