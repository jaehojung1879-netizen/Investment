"""Cross-validating DART dividend rows against Yahoo's, on synthetic fixtures."""
from __future__ import annotations

from pipeline import kr_dividend_reconciliation as REC


def _dart(**overrides):
    base = {"ticker": "005930.KS", "recordDate": "2023-03-31",
           "amountPerShare": 361.0, "isStockDividend": False}
    base.update(overrides)
    return base


def _yahoo(**overrides):
    base = {"ticker": "005930.KS", "date": "2023-04-03",
           "amountPerShare": 361.0, "isStockDividend": False}
    base.update(overrides)
    return base


# --------------------------------------------------------------------------- #
# match_events
# --------------------------------------------------------------------------- #
def test_matches_within_the_date_tolerance():
    pairs = REC.match_events([_dart()], [_yahoo()])
    assert len(pairs) == 1
    assert pairs[0]["dart"] is not None and pairs[0]["yahoo"] is not None
    assert pairs[0]["dateGapDays"] == 3


def test_no_match_outside_the_tolerance_reports_both_sides_unmatched():
    far = _yahoo(date="2023-06-01")
    pairs = REC.match_events([_dart()], [far], date_tolerance_days=10)
    assert len(pairs) == 2
    kinds = {(p["dart"] is not None, p["yahoo"] is not None) for p in pairs}
    assert kinds == {(True, False), (False, True)}


def test_each_side_used_at_most_once():
    dart_rows = [_dart(recordDate="2023-03-31"), _dart(recordDate="2023-03-30")]
    yahoo_rows = [_yahoo(date="2023-04-01")]
    pairs = REC.match_events(dart_rows, yahoo_rows)
    matched = [p for p in pairs if p["dart"] and p["yahoo"]]
    assert len(matched) == 1, "one yahoo row cannot be matched twice"


# --------------------------------------------------------------------------- #
# classify_mismatch
# --------------------------------------------------------------------------- #
def test_agreeing_pair_has_no_mismatch_reason():
    pair = {"dart": _dart(), "yahoo": _yahoo(), "dateGapDays": 0}
    assert REC.classify_mismatch(pair, amount_tolerance_pct=1.0) is None


def test_missing_side_is_source_timing():
    pair = {"dart": _dart(), "yahoo": None, "dateGapDays": None}
    assert REC.classify_mismatch(pair, amount_tolerance_pct=1.0) == REC.SOURCE_TIMING


def test_identity_mismatch_when_tickers_disagree():
    pair = {"dart": _dart(ticker="005930.KS"), "yahoo": _yahoo(ticker="000660.KS"),
           "dateGapDays": 0}
    assert REC.classify_mismatch(pair, amount_tolerance_pct=1.0) == REC.IDENTITY_MISMATCH


def test_stock_vs_cash_classification_mismatch():
    pair = {"dart": _dart(isStockDividend=True), "yahoo": _yahoo(isStockDividend=False),
           "dateGapDays": 0}
    assert REC.classify_mismatch(pair, amount_tolerance_pct=1.0) == \
        REC.STOCK_VS_CASH_CLASSIFICATION


def test_amendment_flag_reported_as_amendment():
    pair = {"dart": _dart(isAmendment=True, amountPerShare=400.0),
           "yahoo": _yahoo(amountPerShare=361.0), "dateGapDays": 0}
    assert REC.classify_mismatch(pair, amount_tolerance_pct=1.0) == REC.AMENDMENT


def test_gross_net_representation_detected_at_the_withholding_ratio():
    # 361 * 0.846 =~ 305.4 -- the net-of-15.4%-withholding figure a vendor
    # might publish instead of the gross decision amount.
    pair = {"dart": _dart(amountPerShare=361.0), "yahoo": _yahoo(amountPerShare=305.4),
           "dateGapDays": 0}
    assert REC.classify_mismatch(pair, amount_tolerance_pct=1.0) == \
        REC.GROSS_NET_REPRESENTATION


def test_unexplained_amount_difference_is_unresolved_not_averaged_away():
    pair = {"dart": _dart(amountPerShare=361.0), "yahoo": _yahoo(amountPerShare=999.0),
           "dateGapDays": 0}
    assert REC.classify_mismatch(pair, amount_tolerance_pct=1.0) == REC.UNRESOLVED


def test_date_semantics_when_amounts_agree_but_dates_differ():
    pair = {"dart": _dart(), "yahoo": _yahoo(), "dateGapDays": 5}
    assert REC.classify_mismatch(pair, amount_tolerance_pct=1.0) == REC.DATE_SEMANTICS


def test_classify_mismatch_never_reads_a_stock_return():
    import inspect
    source = inspect.getsource(REC.classify_mismatch)
    for forbidden in ("fwdreturn", "excessreturn", "stockclose", "sharepricedata"):
        assert forbidden not in source.lower().replace(" ", "")
    # The only fields read are the two sides' own stated dividend rows.
    assert "dart_row.get" in source or 'dart_row["' in source


# --------------------------------------------------------------------------- #
# reconcile / reconcile_many
# --------------------------------------------------------------------------- #
def test_reconcile_reports_agreement_rate_and_every_reason_bucket():
    result = REC.reconcile([_dart()], [_yahoo(date="2023-03-31")])
    assert result["agreeingPairs"] == 1
    assert result["disagreeingPairs"] == 0
    assert set(result["mismatchReasonCounts"]) == REC.MISMATCH_REASONS


def test_reconcile_counts_a_date_semantics_disagreement_when_dates_differ():
    result = REC.reconcile([_dart()], [_yahoo()])  # default fixtures: 3-day gap
    assert result["agreeingPairs"] == 0
    assert result["mismatchReasonCounts"][REC.DATE_SEMANTICS] == 1


def test_reconcile_many_rolls_up_across_tickers():
    result = REC.reconcile_many(
        {"005930.KS": [_dart()], "000660.KS": [_dart(ticker="000660.KS")]},
        {"005930.KS": [_yahoo()], "000660.KS": []})
    assert result["tickers"] == 2
    assert result["totalPairs"] == 2
    assert 0.0 <= result["agreementRatePct"] <= 100.0


def test_reconcile_many_with_no_pairs_reports_no_rate_rather_than_dividing_by_zero():
    result = REC.reconcile_many({}, {})
    assert result["agreementRatePct"] is None
