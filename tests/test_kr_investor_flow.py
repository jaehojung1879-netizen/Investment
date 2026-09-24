"""What a stored KR investor-flow record has to mean.

Synthetic fixtures only — the network half runs solely in CI via
`scripts/probe_kr_investor_flow.py`. What is pinned here is the parsing,
the append-only identity, the never-fabricate-absent-fields rule, and the
backward-looking-only derivation.
"""
from __future__ import annotations

from pipeline import kr_investor_flow as KIF


# --------------------------------------------------------------------------- #
# Amount parsing
# --------------------------------------------------------------------------- #
def test_thousands_separators_and_minus_sign_negatives():
    assert KIF.parse_amount("1,234,567") == 1234567.0
    assert KIF.parse_amount("-1,234") == -1234.0


def test_a_blank_or_dash_cell_is_none_never_a_flat_zero():
    for blank in ("", "-", "—", "–", None):
        assert KIF.parse_amount(blank) is None
    assert KIF.parse_amount("0") == 0.0


def test_unparseable_text_is_refused():
    assert KIF.parse_amount("해당없음") is None


# --------------------------------------------------------------------------- #
# Record identity
# --------------------------------------------------------------------------- #
def test_record_id_is_ticker_and_date():
    assert KIF.record_id("005930.KS", "2024-01-05") == "kr-investor-flow:2024-01-05:005930.KS"


# --------------------------------------------------------------------------- #
# build_record
# --------------------------------------------------------------------------- #
def test_a_general_row_alone_yields_a_record_with_no_breakdown():
    row = {"FORN_NETBID_TRDVAL": "1,000", "ORGN_NETBID_TRDVAL": "-500",
           "PRSN_NETBID_TRDVAL": "-500"}
    record, reason = KIF.build_record(
        ticker="005930.KS", date="2024-01-05", row=row, detail_row=None,
        collected_at="2026-09-24T00:00:00Z")

    assert reason == ""
    assert record["foreignNetBuy"] == 1000.0
    assert record["institutionNetBuy"] == -500.0
    assert record["institutionBreakdown"] is None
    assert record["availableFrom"] == "2024-01-05", "settled EOD flow: the trading date IS the visibility date"
    assert record["programTrading"] is None, "never fabricated when the source does not carry it"


def test_a_detail_row_adds_the_institution_breakdown_only_when_it_has_values():
    row = {"FORN_NETBID_TRDVAL": "1,000", "ORGN_NETBID_TRDVAL": "-500", "PRSN_NETBID_TRDVAL": "-500"}
    detail = {"금융투자": "-200", "보험": "0", "연기금": "-300"}
    record, reason = KIF.build_record(
        ticker="005930.KS", date="2024-01-05", row=row, detail_row=detail,
        collected_at="2026-09-24T00:00:00Z")

    assert reason == ""
    assert record["institutionBreakdown"]["금융투자"] == -200.0
    assert record["institutionBreakdown"]["보험"] == 0.0
    # A sub-category the detail row never mentions is None, not summed away.
    assert record["institutionBreakdown"]["사모"] is None
    assert "MDCSTAT02303" in record["source"]


def test_an_empty_response_is_refused_with_its_reason():
    record, reason = KIF.build_record(
        ticker="005930.KS", date="2024-01-05", row={}, detail_row=None,
        collected_at="2026-09-24T00:00:00Z")
    assert record is None and reason == "EMPTY_RESPONSE"


def test_a_row_with_no_recognisable_flow_field_is_refused():
    record, reason = KIF.build_record(
        ticker="005930.KS", date="2024-01-05", row={"SOME_OTHER_COLUMN": "1"},
        detail_row=None, collected_at="2026-09-24T00:00:00Z")
    assert record is None and reason == "NO_FLOW_FIELDS"


# --------------------------------------------------------------------------- #
# Derivation — backward-looking only
# --------------------------------------------------------------------------- #
def _rows(ticker: str, values: list[tuple[str, float, float]]) -> list[dict]:
    return [{"ticker": ticker, "date": date, "foreignNetBuy": f, "institutionNetBuy": i}
            for date, f, i in values]


def test_cumulative_flow_needs_the_full_window_or_returns_none():
    rows = _rows("005930.KS", [(f"2024-01-{d:02d}", 10.0, -5.0) for d in range(1, 6)])
    derived = KIF.cumulative_flow(rows, windows=(5,))

    assert derived[3]["cumulativeFlow"]["foreignNet5d"] is None, "only 4 days of history so far"
    assert derived[4]["cumulativeFlow"]["foreignNet5d"] == 50.0
    assert derived[4]["cumulativeFlow"]["institutionNet5d"] == -25.0


def test_a_gap_inside_the_window_poisons_the_sum_rather_than_being_skipped():
    values = [(f"2024-01-{d:02d}", 10.0, -5.0) for d in range(1, 6)]
    rows = _rows("005930.KS", values)
    rows[2]["foreignNetBuy"] = None
    derived = KIF.cumulative_flow(rows, windows=(5,))
    assert derived[4]["cumulativeFlow"]["foreignNet5d"] is None


def test_derivation_never_reaches_forward_of_its_own_date():
    """The 5D window at row i must be unaffected by rows after i."""
    rows = _rows("005930.KS", [(f"2024-01-{d:02d}", float(d), 0.0) for d in range(1, 11)])
    derived_full = KIF.cumulative_flow(rows, windows=(5,))
    derived_truncated = KIF.cumulative_flow(rows[:5], windows=(5,))
    assert (derived_full[4]["cumulativeFlow"]["foreignNet5d"]
            == derived_truncated[4]["cumulativeFlow"]["foreignNet5d"])


def test_flow_acceleration_needs_two_full_windows():
    rows = _rows("005930.KS", [(f"2024-01-{d:02d}", 10.0, 0.0) for d in range(1, 11)])
    derived = KIF.flow_acceleration(rows, window=5)
    assert derived[3]["flowAcceleration"]["foreignNetAccel"] is None
    # Two full 5-day windows of steady +10/day: no acceleration, delta 0.
    assert derived[9]["flowAcceleration"]["foreignNetAccel"] == 0.0


def test_foreign_institution_agreement_labels():
    assert KIF.foreign_institution_agreement({"foreignNetBuy": 10, "institutionNetBuy": 5}) == "SAME_DIRECTION"
    assert KIF.foreign_institution_agreement({"foreignNetBuy": 10, "institutionNetBuy": -5}) == "OPPOSITE_DIRECTION"
    assert KIF.foreign_institution_agreement({"foreignNetBuy": 0, "institutionNetBuy": 5}) == "FLAT"
    assert KIF.foreign_institution_agreement({"foreignNetBuy": None, "institutionNetBuy": 5}) is None
