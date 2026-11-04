"""Synthetic tests for the KR insider construction. The XML below is invented; it copies only the
attribute layout DART uses (measured on an original filing on 2026-11-03), never real values."""
import pytest

from research.alpha_evidence_sprint_v2 import kr_insider as K


def row(label, code, day, kind, change, price):
    return (f'<TR><TU AUNIT="RPT_RSN" AUNITVALUE="{code}">{label}</TU>'
            f'<TU AUNIT="MDF_DM" AUNITVALUE="{day}">x</TU>'
            f'<TU AUNIT="STR_KND" AUNITVALUE="1">{kind}</TU>'
            f'<TE ACODE="BFR_STK_CNT">1,000</TE><TE ACODE="MDF_STK_CNT">{change}</TE>'
            f'<TE ACODE="AFR_STK_CNT">1,000</TE><TE ACODE="ACI_AMT2">{price}</TE></TR>')


def doc(*rows):
    head = '<TR><TH>보고사유</TH><TH>변동일*</TH></TR>'
    total = '<TR><TD COLSPAN="3">합 계</TD><TE ACODE="MDF_STK_SUM">0</TE></TR>'
    return ('<DOCUMENT><TABLE-GROUP ACLASS="RPT_RSN" ADELETETABLE="N"><TABLE>'
            + head + "".join(rows) + total + "</TABLE></TABLE-GROUP></DOCUMENT>")


def test_parser_reads_machine_attributes_and_skips_header_and_total_rows():
    rows = K.parse_transactions(doc(row("장내매수(+)", "01", "20200102", "보통주", "1,500", "10,000"),
                                    row("장내매도(-)", "02", "20200103", "보통주", "-500", "11,000")))
    assert [r["shareChange"] for r in rows] == [1500, -500]
    assert rows[0]["date"] == "2020-01-02" and rows[0]["price"] == 10000 and rows[0]["reasonCode"] == "01"


def test_only_exact_open_market_common_rows_count():
    rows = K.parse_transactions(doc(
        row("장내매수(+)", "01", "20200102", "보통주", "1,000", "100"),
        row("장내매수(+)", "01", "20200102", "우선주", "9,000", "100"),         # preferred: not counted
        row("증여(+)", "11", "20200102", "보통주", "50,000", "-"),            # gift: not counted
        row("주식매수선택권행사(+)", "33", "20200102", "보통주", "7,000", "50"),  # option: not counted
        row("장내매도(-)", "02", "20200103", "보통주", "-400", "120")))
    net = K.open_market_net(rows)
    assert net["buyShares"] == 1000 and net["sellShares"] == 400 and net["netShares"] == 600
    assert net["netKrw"] == 1000 * 100 - 400 * 120 and net["otherRows"] == 2


def test_unreadable_filing_is_an_error_never_a_zero_trade_filing():
    with pytest.raises(K.ParseError, match="NO_DETAIL_TABLE"):
        K.parse_transactions("<DOCUMENT>no table</DOCUMENT>")
    broken = doc('<TR><TU AUNIT="RPT_RSN" AUNITVALUE="01">장내매수(+)</TU></TR>')
    with pytest.raises(K.ParseError, match="INCOMPLETE"):
        K.parse_transactions(broken)
    with pytest.raises(K.ParseError, match="NOT_AN_INTEGER"):
        K.parse_transactions(doc(row("장내매수(+)", "01", "20200102", "보통주", "1.5e3", "1")))


def test_price_cells_tolerate_units_and_decimals_but_share_counts_stay_strict():
    rows = K.parse_transactions(doc(row("장내매수(+)", "01", "20200102", "보통주", "10", "139600(원)"),
                                    row("장내매수(+)", "01", "20200102", "보통주", "5", "109374.16()"),
                                    row("장내매수(+)", "01", "20200102", "보통주", "5", "미정")))
    assert [r["price"] for r in rows] == [139600.0, 109374.16, None]
    assert K.open_market_net(rows)["netKrw"] is None and K.open_market_net(rows)["netShares"] == 20


def test_missing_price_makes_value_unknown_but_shares_still_count():
    net = K.open_market_net(K.parse_transactions(doc(row("장내매수(+)", "01", "20200102", "보통주", "10", "-"))))
    assert net["netShares"] == 10 and net["netKrw"] is None and net["allPriced"] is False


def test_cp949_documents_decode():
    raw = '<?xml version="1.0" encoding="utf-8"?>장내매수(+)'.encode("cp949")
    assert "장내매수(+)" in K.decode(raw)


SESSIONS = [f"2020-01-{d:02d}" for d in (2, 3, 6, 7, 8, 9, 10, 13)]


def test_availability_is_strictly_after_receipt_even_on_a_session_day():
    assert K.available_session("2020-01-03", SESSIONS) == "2020-01-06"
    assert K.available_session("2020-01-04", SESSIONS) == "2020-01-06"   # weekend receipt
    assert K.available_session("2020-01-13", SESSIONS) is None


def test_state_uses_only_events_available_by_the_anchor():
    e = [K.Event("A", "r1", "2020-01-02", "2020-01-03", 100, None),
         K.Event("A", "r2", "2020-01-08", "2020-01-09", -300, None)]
    assert K.state_at(e, "A", "2020-01-08", SESSIONS) == "NET_BUYER"       # r2 not yet available
    assert K.state_at(e, "A", "2020-01-09", SESSIONS) == "NET_SELLER"
    assert K.state_at(e, "B", "2020-01-09", SESSIONS) == "NO_OPEN_MARKET_TRADE"
    assert K.state_at(e, "A", "2020-01-13", SESSIONS, trailing=3) == "NET_SELLER"
    assert K.state_at(e, "A", "2020-01-13", SESSIONS, trailing=2) == "NO_OPEN_MARKET_TRADE"


def test_future_filing_cannot_change_a_past_state():
    base = [K.Event("A", "r1", "2020-01-02", "2020-01-03", 100, None)]
    future = base + [K.Event("A", "r9", "2020-01-10", "2020-01-13", -10_000, None)]
    assert K.state_at(base, "A", "2020-01-09", SESSIONS) == K.state_at(future, "A", "2020-01-09", SESSIONS)


def test_anchor_spread_drops_ineligible_labels_symmetrically():
    states = {"A": "NET_BUYER", "B": "NET_BUYER", "C": "NO_OPEN_MARKET_TRADE", "D": "NO_OPEN_MARKET_TRADE",
              "E": "NET_SELLER"}
    out = K.anchor_spread({"A": 0.10, "B": None, "C": 0.02, "D": 0.04, "E": -0.5}, states, set(states))
    assert out["spread"] == pytest.approx(0.10 - 0.03) and out["labelIneligible"] == 1
    assert K.anchor_spread({"C": 0.0}, {"C": "NO_OPEN_MARKET_TRADE"}, {"C"})["spread"] is None


def test_frozen_registration_matches_module_constants():
    import json
    from pathlib import Path
    spec = json.loads((Path(K.__file__).parent / "kr-insider-open-market-purchase-v1.json").read_text())
    assert "63 KRX sessions" in spec["state"]["definition"] and K.TRAILING_SESSIONS == 63
    assert K.BUY_LABEL in spec["information"]["openMarket"] and K.SELL_LABEL in spec["information"]["openMarket"]
    assert spec["status"] == "PREREGISTERED_NOT_EXECUTED" and spec["parser"]["revision"] == "v2"


# --- quarantine rule (owner, 2026-11-04): any detail row dated after the DART receipt date ---

def test_row_dated_after_receipt_quarantines_the_whole_filing():
    # the observed shape: one row dated 212 days after a 2019-03-04 receipt (2019-10-02)
    rows = K.parse_transactions(doc(row("장내매수(+)", "01", "20190228", "보통주", "1,000", "100"),
                                    row("장내매수(+)", "01", "20191002", "보통주", "500", "100")))
    out = K.build_event("A", "r1", "2019-03-04", rows, ["2019-03-04", "2019-03-05"])
    assert isinstance(out, K.Quarantine)
    assert out.reason == K.QUARANTINE_ROW_DATED_AFTER_RECEIPT
    assert out.rows_after_receipt == 1 and out.max_days_after_receipt == 212


def test_row_on_the_receipt_date_is_not_quarantined():
    rows = K.parse_transactions(doc(row("장내매수(+)", "01", "20200103", "보통주", "10", "1")))
    out = K.build_event("A", "r1", "2020-01-03", rows, SESSIONS)
    assert isinstance(out, K.Event) and out.available == "2020-01-06" and out.net_shares == 10


def test_quarantined_filing_never_contributes_to_state_and_is_counted():
    good = K.build_event("A", "r1", "2020-01-02", K.parse_transactions(
        doc(row("장내매도(-)", "01", "20200102", "보통주", "-5", "1"))), SESSIONS)
    bad = K.build_event("A", "r2", "2020-01-02", K.parse_transactions(
        doc(row("장내매수(+)", "01", "20200110", "보통주", "1,000,000", "1"))), SESSIONS)
    events, counts = K.split_events([good, bad, None])
    assert counts == {"quarantined": 1, "byReason": {K.QUARANTINE_ROW_DATED_AFTER_RECEIPT: 1}}
    assert K.state_at(events, "A", "2020-01-13", SESSIONS) == "NET_SELLER"
    with pytest.raises(TypeError, match="EVENTS_ONLY"):
        K.state_at([good, bad], "A", "2020-01-13", SESSIONS)


def test_receipt_after_last_session_is_not_yet_usable():
    rows = K.parse_transactions(doc(row("장내매수(+)", "01", "20200113", "보통주", "1", "1")))
    assert K.build_event("A", "r1", "2020-01-13", rows, SESSIONS) is None
