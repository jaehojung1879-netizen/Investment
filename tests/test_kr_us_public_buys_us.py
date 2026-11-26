from datetime import date

import numpy as np
import pandas as pd

from research.kr_us_public_buys_v1.us_study import (
    OPEN,
    build_books,
    covered_issuers,
    match,
    portfolio,
)


def test_coverage_intersects_issuer_subsets_and_carries_unknown_windows():
    a, b, c = (date(2024, 1, i) for i in range(2, 5))
    groups = [(a, b, frozenset({"1", "2"})), (c, c, frozenset({"2", "3"}))]
    assert covered_issuers(a, c, groups) == frozenset({"2"})
    assert covered_issuers(a, c, groups[:1]) == frozenset()
    assert covered_issuers(a, c, [(a, c, None)]) is None


def test_match_maximizes_cardinality_and_adjustment_keeps_business_state():
    panel = pd.DataFrame(
        {"marketCap": [100., 52., 98., 197.],
         "sector": ["Industrials"] * 4,
         "valueRank": [.5, .5, .5, .5],
         "trendRank": [.6, .6, .6, .6],
         "business": [0., 1., 1., 0.]},
        index=["A", "B", "X", "Y"],
    )
    matches, records = match(panel, ("A", "B"), {"X", "Y"}, adjusted=True)
    assert matches == {"A": "Y", "B": "X"}
    assert all(r["reason"] == "MATCHED" and .5 <= r["capRatio"] <= 2 for r in records)
    panel.loc["X", "trendRank"] = .2
    rejected, records = match(panel, ("A", "B"), {"X", "Y"}, adjusted=True)
    assert rejected is None
    assert records[1]["reason"] == "NO_SIGNAL_SIMILAR_PEER"


def test_after_half_day_close_excluded_until_next_decision(monkeypatch):
    from research.kr_us_public_buys_v1 import us_study

    dates = pd.DatetimeIndex(["2024-11-22", "2024-11-29", "2024-12-06"])
    panel = pd.DataFrame([
        {"date": d, "ticker": t, "identity": "MEMBERSHIP_CIK", "marketCap": 80. if t == "B" else 100.,
         "sector": "Industrials"}
        for d in dates for t in ("A", "B", "C")
    ])
    close = pd.DataFrame(100., index=dates, columns=["A", "B", "C", "SPY"])
    monkeypatch.setattr(us_study.frozen.ev, "common", lambda _: pd.DataFrame())
    events = pd.DataFrame([
        {"at": pd.Timestamp("2024-11-29T17:59:59Z"), "until": pd.NaT, "status": "INDETERMINATE_P",
         "issuerCIK": "3", "symbol": "C", "accession": "1", "blocksControl": True},
        {"at": pd.Timestamp("2024-11-29T18:00:01Z"), "until": pd.NaT, "status": OPEN,
         "issuerCIK": "1", "symbol": "A", "accession": "2", "blocksControl": False},
        {"at": pd.Timestamp("2024-12-06T21:00:00Z"), "until": pd.NaT, "status": "INDETERMINATE_P",
         "issuerCIK": "3", "symbol": "C", "accession": "3", "blocksControl": True},
    ])
    events["until"] = pd.to_datetime(events["until"], utc=True)
    names = {d: {"A": "1", "B": "2", "C": "3"} for d in dates}
    schedule, audit, _, positions = build_books(panel, close, dates, events, [(dates[0].date(), dates[-1].date(), None)], names)
    assert audit.selected.to_list() == [0, 1]
    assert schedule[dates[1]][0] == ()
    assert schedule[dates[2]][0] == ("A",)
    assert schedule[dates[2]][1] == {"A": "B"}
    assert positions.iloc[0].ticker == "A"
    assert portfolio(()) == {"SPY": 1.}
    assert np.isclose(sum(portfolio(("A", "B")).values()), 1.)


def test_confirmed_cash_purchase_and_unknown_venue_are_distinct():
    from research.kr_us_public_buys_v1.us_events import classify

    row = {"TRANS_CODE": "P", "TRANS_ACQUIRED_DISP_CD": "A", "SECURITY_TITLE": "Common Stock",
           "TRANS_SHARES": "100", "TRANS_PRICEPERSHARE": "10.00"}
    assert classify(row, "Bought on the open market.", ["Officer"])[0] == OPEN
    assert classify(row, "", ["Officer"])[0] == "INDETERMINATE_P"
    assert classify(row, "The acquisition was negotiated privately.", ["Officer"])[0] == "EXCLUDED_PRIVATE"
    assert classify({**row, "TRANS_CODE": "G"}, "", ["Officer"])[0] == "EXCLUDED_NON_PURCHASE_CODE"


def test_event_reader_quarantines_incomplete_fields_and_repeated_economics(tmp_path):
    from research.kr_us_public_buys_v1.us_study import read_events

    base = {"issuerCIK": "0001", "ticker": "ABC", "transactionDate": "2024-11-27",
            "status": OPEN, "securityTitle": "Common Stock", "quantity": "200", "price": "10.25"}
    rows = [
        {**base, "accession": "01", "eventId": "01|ND|1", "availableAt": "2024-11-29T18:00:00Z"},
        {**base, "accession": "02", "eventId": "02|ND|1", "availableAt": "2024-12-02T21:00:00Z"},
        {**base, "accession": "03", "eventId": "03|ND|1", "availableAt": "2024-12-02T21:00:00Z",
         "transactionDate": ""},
    ]
    source = tmp_path / "events.csv"
    pd.DataFrame(rows).to_csv(source, index=False)
    read = read_events(source)
    assert read.status.to_list() == [OPEN, "INDETERMINATE_LATER_IDENTICAL_ECONOMICS", "INDETERMINATE_EVENT_FIELDS"]
    assert read.blocksControl.to_list() == [False, True, True]
