import pandas as pd

from research.followup_round8_v1 import us_audit as UA


def test_cusip_link_uses_only_pairs_published_by_the_filing_date():
    pairs = pd.DataFrame({"cusip": ["C1", "C2", "C2"], "tk": ["AAA", "BBB", "CCC"],
                          "seen": pd.to_datetime(["2021-01-10", "2020-01-10", "2022-06-01"])})
    t = pd.DataFrame({"accession_number": ["a", "a", "b"], "issuer_cusip": ["C1", "C2", "C2"], "identifier_ticker": [None, "", None],
                      "currency_value": [1.0, 1.0, 1.0], "investment_country": ["US"] * 3})
    fdate = pd.Series(pd.to_datetime(["2021-03-01", "2023-01-01"]), index=["a", "b"])
    h = UA.link_pit(t, {"AAA", "BBB", "CCC"}, pairs, fdate)
    assert h.loc[0, "tk"] == "AAA"                         # pair seen before the filing
    assert h.loc[1, "tk"] == "BBB"                         # only BBB had been seen by 2021-03
    assert h.loc[2, "tk"] is None                          # by 2023 the CUSIP had two tickers: ambiguous, dropped


def test_direct_ticker_needs_no_history():
    t = pd.DataFrame({"accession_number": ["a"], "issuer_cusip": ["Z"], "identifier_ticker": ["brk.b"], "currency_value": [1.0],
                      "investment_country": ["US"]})
    h = UA.link_pit(t, {"BRK-B"}, pd.DataFrame(columns=["cusip", "tk", "seen"]), pd.Series([pd.Timestamp("2020-01-01")], index=["a"]))
    assert h.loc[0, "tk"] == "BRK-B" and h.loc[0, "linkBy"] == "TICKER"


def test_benchmark_must_be_published_no_later_than_the_fund():
    close = pd.DataFrame({"X": [1.0, 1.0]}, index=pd.to_datetime(["2024-03-31", "2024-06-30"]))
    w = pd.Series({"X": 1.0})
    ivv = {pd.Timestamp("2024-03-31"): (pd.Timestamp("2024-05-28"), w), pd.Timestamp("2024-06-30"): (pd.Timestamp("2024-08-29"), w)}
    assert UA.bench_for(pd.Timestamp("2024-06-30"), pd.Timestamp("2024-08-20"), ivv, close, {}) is not None
    cache = {}
    UA.bench_for(pd.Timestamp("2024-06-30"), pd.Timestamp("2024-08-20"), ivv, close, cache)
    assert list(cache) == [(pd.Timestamp("2024-03-31"), pd.Timestamp("2024-06-30"))]      # the 06-30 IVV report was not yet public
    assert UA.bench_for(pd.Timestamp("2024-06-30"), pd.Timestamp("2024-05-01"), ivv, close, {}) is None


def test_clone_removal_keeps_the_first_published_portfolio():
    F = pd.DataFrame({"accession": ["early_small", "late_big"], "report_date": pd.to_datetime(["2024-03-31"] * 2),
                      "filing_date": pd.to_datetime(["2024-05-20", "2024-05-29"]), "netAssets": [1e8, 9e9], "qualifies": [True, True]})
    w = {"early_small": pd.Series({"A": 0.5, "B": 0.5}), "late_big": pd.Series({"A": 0.5, "B": 0.5})}
    drop_pit, _ = UA.dedupe(F, w, pit=True)
    drop_size, late = UA.dedupe(F, w, pit=False)
    assert drop_pit == {"late_big"} and drop_size == {"early_small"} and late == 1


def test_kr_mix_keeps_capital_and_scales_the_stock_book():
    from research.followup_round8_v1 import kr_switch as KS
    b = KS.mix(0.6, {"A": 0.2, "B": 0.2, "C": 0.2, "D": 0.2, "E": 0.2})
    assert abs(sum(b.values()) - 1) < 1e-12 and abs(b[KS.M.ETF] - 0.6) < 1e-12 and abs(b["A"] - 0.08) < 1e-12
