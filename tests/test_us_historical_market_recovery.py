"""Invented prices only. No real research labels, raw vendor data, or network."""
import pandas as pd
import pytest
import hashlib
import json
from decimal import Decimal

from research.us_historical_market_recovery_v1.engine import (
    Series, Unresolved, fractional_stock_terms, frame_series, holding, ranges, required_old_quote_end, whole_window_source,
)
from research.us_historical_market_recovery_v1.collect import private_root


def source(days, values, *, good=None):
    x = pd.Series(values, index=pd.to_datetime(days), dtype=float)
    return Series("SYN", x, x.copy(), set(good or days), "SYNTHETIC_FIXTURE", "0" * 64, True, True)


def test_cash_merger_uses_cited_consideration_and_keeps_cash():
    days = ["2020-01-02", "2020-01-03", "2020-01-06", "2020-01-07"]
    series = source(days[:2], [100, 110])
    terminal = {"date": days[2], "last_trading_date": days[1], "cash": 120, "verified": True, "citation": "synthetic"}
    assert holding(series, days[0], days[-1], days, terminal=terminal) == pytest.approx(.2)


def test_whole_publisher_can_end_at_last_trade_for_terminal_holding():
    days = ["2020-01-02", "2020-01-03", "2020-01-06", "2020-01-07"]
    old = source(days[:1], [100])
    extension = source(days[:2], [100, 110])
    terminal = {"date": days[2], "last_trading_date": days[1], "cash": 120,
                "verified": True, "citation": "synthetic"}
    quote_end = required_old_quote_end(days[0], days[-1], terminal)
    assert whole_window_source(extension, old, days[0], quote_end) is extension
    assert required_old_quote_end(days[0], days[1], terminal) == days[1]
    assert holding(extension, days[0], days[-1], days, terminal=terminal) == pytest.approx(.2)


def test_fractional_payment_uses_documented_position_and_stock_carries_forward():
    assert fractional_stock_terms(100, .255, 113.1311) == (25, Decimal("56.57"))
    assert fractional_stock_terms(200, .255, 113.1311) == (51, Decimal("0.00"))
    days = ["2020-01-02", "2020-01-03", "2020-01-06"]
    original = source(days[:1], [100])
    successor = source(days[1:], [110, 120])
    terminal = {"date": days[1], "last_trading_date": days[0], "shares": .255,
                "successor": "NEW", "verified": True, "citation": "synthetic",
                "cash_in_lieu_required": True, "cash_in_lieu_price": 113.1311,
                "cash_in_lieu_citation": "synthetic settlement", "cash_in_lieu_known_on": days[1]}
    kwargs = {"terminal": terminal, "successors": {"NEW": successor}}
    with pytest.raises(Unresolved, match="FRACTIONAL_SHARE_SETTLEMENT_UNRESOLVED"):
        holding(original, days[0], days[-1], days, **kwargs)
    value = holding(original, days[0], days[-1], days, terminal_position_shares=100, **kwargs)
    assert value == pytest.approx((25 * 120 + 56.57) / (100 * 100) - 1)
    single = holding(original, days[0], days[-1], days, terminal=terminal, terminal_position_shares=1)
    assert single == pytest.approx(28.85 / 100 - 1)
    with pytest.raises(Unresolved, match="FRACTIONAL_SETTLEMENT_POSITION_QUANTITY_UNVERIFIED"):
        holding(original, days[0], days[-1], days, terminal_position_shares=1.5, **kwargs)
    terminal["cash_in_lieu_known_on"] = "2020-01-07"
    with pytest.raises(Unresolved, match="FRACTIONAL_SETTLEMENT_RATE_NOT_KNOWN_AT_HORIZON"):
        holding(original, days[0], days[-1], days, terminal_position_shares=100, **kwargs)


def test_reused_para_provider_identity_is_refused_even_with_matching_symbol(tmp_path):
    from research.us_historical_market_recovery_v1.audit import chart_series, check_paramount_class_b_chart
    metadata = {"symbol": "PARA", "longName": "Parabolic Technologies, Inc.", "instrumentType": "EQUITY"}
    raw = json.dumps({"chart": {"result": [{"meta": metadata}]}}).encode()
    (tmp_path / "reused.json").write_bytes(raw)
    record = {"ticker": "PARA", "audit_identifier": "VIAC", "object": "reused.json",
              "sha256": hashlib.sha256(raw).hexdigest()}
    with pytest.raises(Unresolved, match="PARA_VENDOR_ISSUER_MISMATCH_OR_UNVERIFIED"):
        chart_series(record, tmp_path)
    check_paramount_class_b_chart(record, dict(metadata, longName="Paramount Global"))


def test_recovery_rejects_accounting_calculated_from_a_different_issuer(tmp_path):
    from types import SimpleNamespace

    from pipeline.us_decision_pilot import ACCOUNTING
    from research.us_historical_market_recovery_v1.audit import accounting_conflicts

    snap = {"date": "2020-01-02", "sourceCommit": "test", "members": ["SYN"],
            "publishedAt": "2020-01-02T14:00:00Z"}
    (tmp_path / "members.json").write_text(json.dumps({"snapshots": [snap]}))
    sectors = {**snap, "rows": {"SYN": {"cik": "123", "sector": "Industrials"}}}
    (tmp_path / "sectors.json").write_text(json.dumps({"snapshots": [sectors]}))
    identity = {"regions": {"US": {"identity": {"malformed": {}, "renames": {}}}}}
    (tmp_path / "identity.json").write_text(json.dumps(identity))
    values = dict.fromkeys(ACCOUNTING, 1.0)
    frame = {pd.Timestamp("2020-01-03"): pd.DataFrame([values], index=["SYN"])}
    records = {"SYN": [{"cik": "000123", "factors": values}, {"cik": "456", "factors": values}]}

    class Cache:
        def __init__(self, rows):
            self.row = rows[0]

        def at(self, day):
            return self.row["factors"], {self.row["cik"]}

    pilot = SimpleNamespace(MEMBERSHIP="members.json", SECTORS="sectors.json",
                            IDENTITY="identity.json", AccountingCache=Cache)
    assert accounting_conflicts(frame, records, pilot, root=tmp_path) == []
    records["SYN"][0]["factors"] = {**values, "assetGrowthPct": None}
    assert accounting_conflicts(frame, records, pilot, root=tmp_path) == [["2020-01-03", "SYN"]]


def test_recovery_index_guard_respects_session_timing_and_later_episodes(tmp_path):
    from types import SimpleNamespace

    from research.us_historical_market_recovery_v1.audit import membership_conflicts

    def put(name, rows):
        (tmp_path / name).write_text(json.dumps(rows))

    put("members.json", {"snapshots": [
        {"date": "2020-01-02", "members": ["AT_OPEN", "AFTER_CLOSE"]},
        {"date": "2020-01-09", "members": []},
        {"date": "2020-01-14", "members": ["AFTER_CLOSE"]},
    ]})
    put("identity.json", {"regions": {"US": {"identity": {"malformed": {}, "renames": {}}}}})
    put("departed-public-evidence.json", {"rows": [
        {"audit_identifier": "AT_OPEN", "index_removals": [{"date": "2020-01-03", "timing": "before_open"}]},
    ]})
    put("departed-public-evidence-supplement.json", {"rows": [
        {"audit_identifier": "AFTER_CLOSE", "index_timing_evidence": {
            "reported_change_date": "2020-01-03", "reported_timing": "after_close",
        }},
    ]})
    frames = {pd.Timestamp(day): pd.DataFrame(index=tickers) for day, tickers in (
        ("2020-01-03", ["AT_OPEN", "AFTER_CLOSE"]),
        ("2020-01-06", ["AT_OPEN", "AFTER_CLOSE"]),
        ("2020-01-17", ["AFTER_CLOSE"]),
    )}
    pilot = SimpleNamespace(MEMBERSHIP="members.json", IDENTITY="identity.json")
    assert membership_conflicts(frames, pilot, root=tmp_path, inputs=tmp_path) == [
        ["2020-01-03", "AT_OPEN"], ["2020-01-06", "AFTER_CLOSE"], ["2020-01-06", "AT_OPEN"],
    ]


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
