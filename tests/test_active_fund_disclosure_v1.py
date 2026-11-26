import pandas as pd

from research.active_fund_disclosure_v1 import evaluate_us as E
from research.active_fund_disclosure_v1 import sample as SM


def test_passive_names_are_screened_and_active_names_are_not():
    for n in ("Vanguard 500 Index Fund", "iShares Core S&P 500 ETF", "Fidelity Nasdaq Composite Index", "Target Date 2045 Fund"):
        assert SM.PASSIVE.search(n)
    for n in ("Growth Fund of America", "T. Rowe Price Blue Chip Growth Fund, Inc.", "Fidelity Contrafund"):
        assert not SM.PASSIVE.search(n)


def test_tickers_are_normalised_to_the_price_panel_form():
    assert SM.norm_ticker("brk.b") == "BRK-B" and SM.norm_ticker("BF/B") == "BF-B" and SM.norm_ticker(" ") is None


def test_only_the_first_filing_per_series_and_report_date_is_used():
    f = pd.DataFrame({"series_id": ["S1", "S1", "S1"], "report_date": pd.to_datetime(["2024-03-31"] * 2 + ["2024-06-30"]),
                      "filing_date": pd.to_datetime(["2024-05-29", "2024-07-01", "2024-08-28"]), "accession_number": ["a", "b", "c"]})
    first, n = SM.originals(f)
    assert sorted(first["accession_number"]) == ["a", "c"] and n == 1


def test_ow_breadth_uses_only_public_unexpired_latest_filings_and_needs_enough_funds(monkeypatch):
    monkeypatch.setattr(E, "MIN_FUNDS", 2)
    meta = pd.DataFrame({"series_id": ["F1", "F1", "F2", "F3"],
                         "report_date": pd.to_datetime(["2023-12-31", "2024-03-31", "2024-03-31", "2023-01-31"]),
                         "filing_date": pd.to_datetime(["2024-02-28", "2024-05-29", "2024-05-30", "2023-03-30"])},
                        index=["f1old", "f1new", "f2", "f3stale"])
    active = {"f1old": pd.Series({"A": -0.01, "B": 0.02}), "f1new": pd.Series({"A": 0.01, "B": -0.02}),
              "f2": pd.Series({"A": 0.03, "B": 0.01}), "f3stale": pd.Series({"A": -0.05, "B": 0.05})}
    ow, n = E.ow_breadth(meta, active, pd.Timestamp("2024-06-03"), pd.Index(["A", "B", "C"]))
    assert n == 2                                   # F1's newest filing, F2; F3 is older than 200 days
    assert round(ow["A"], 6) == 1.0 and round(ow["B"], 6) == 0.5 and round(ow["C"], 6) == 0.0
    none, n2 = E.ow_breadth(meta, active, pd.Timestamp("2024-05-30"), pd.Index(["A"]))   # F2 filed that day: not yet usable
    assert none is None and n2 == 1


def test_matched_control_is_same_sector_nearest_cap_and_used_once():
    x = pd.DataFrame({"sector": ["T", "T", "T", "H"], "marketCap": [100.0, 90.0, 20.0, 95.0]}, index=["P1", "C1", "C2", "H1"])
    assert E.matched(x, ["P1"]) == ["C1"]
    assert E.matched(x, ["H1"]) is None
