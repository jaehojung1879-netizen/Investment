"""What the US derivation builds, and what it refuses to build.

Every rule pinned here is one this repository has already paid for somewhere:

  * a trailing-twelve-month figure is a ROLLFORWARD, because the filings were
    measured to be cumulative from the fiscal year start — summing four
    quarters counts the first one four times;
  * a missing prior year yields None, never an annualisation — the absence is
    the one thing downstream can still act on correctly;
  * an account is a LIST of tags chosen by counting filings, because one tag
    covers 41.6% of them for revenue and the chain covers 93.7%;
  * nothing later than the filing is ever consulted, for any field.

The acceptance case is Apple's FY2012 10-K, checked against the published
statement rather than against this code's own output.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import finnhub_derive as FD  # noqa: E402
from pipeline import finnhub_fundamentals as FF  # noqa: E402

DAYS = {FF.Q1: 90, FF.Q2: 181, FF.Q3: 273, FF.FY: 365}


def _filing(ticker, year, stage, *, ic=(), bs=(), cf=(), available=None, form=None,
            period_end=None):
    def entries(pairs):
        return [{"concept": c, "unit": u, "value": v, "label": c}
                for c, v, u in pairs]
    return {
        "id": f"{ticker}-{year}-{stage}", "ticker": ticker, "fiscalYear": year,
        "form": form or ("10-K" if stage == FF.FY else "10-Q"),
        # The period end is real data, not a placeholder: the contract refuses a
        # row claiming to have been readable before the period it reports on had
        # ended, and a helper that stamped every filing 12-31 would make Apple's
        # October 10-K look like exactly that kind of lookahead.
        "periodDays": DAYS[stage], "periodEnd": period_end or f"{year}-12-31",
        "availableFrom": available or f"{year + 1}-02-15",
        "source": "finnhub/financials-reported", "collectedAt": "2026-09-14T00:00:00Z",
        "statements": {"ic": entries(ic), "bs": entries(bs), "cf": entries(cf)},
    }


def _money(concept, value):
    return (concept, value, "usd")


# --------------------------------------------------------------------------- #
# Apple FY2012, against the published 10-K
# --------------------------------------------------------------------------- #
# Period ended 2012-09-29, filed 2012-10-31, before the 2014 seven-for-one split.
AAPL = dict(ni=41_733e6, revenue=156_508e6, operating=55_241e6, equity=118_210e6,
            liabilities=57_854e6, ocf=50_856e6, capex=8_295e6, shares=945.355e6)


def _apple_annual():
    return _filing("AAPL", 2012, FF.FY, period_end="2012-09-29",
                   available="2012-10-31",
                   ic=[_money("us-gaap_NetIncomeLoss", AAPL["ni"]),
                       _money("us-gaap_Revenues", AAPL["revenue"]),
                       _money("us-gaap_OperatingIncomeLoss", AAPL["operating"]),
                       ("us-gaap_WeightedAverageNumberOfDilutedSharesOutstanding",
                        AAPL["shares"], "shares")],
                   bs=[_money("us-gaap_StockholdersEquity", AAPL["equity"]),
                       _money("us-gaap_Liabilities", AAPL["liabilities"])],
                   cf=[_money("us-gaap_NetCashProvidedByUsedInOperatingActivities",
                              AAPL["ocf"]),
                       _money("us-gaap_PaymentsToAcquirePropertyPlantAndEquipment",
                              AAPL["capex"])])


def test_the_seven_factors_match_apples_published_annual_report():
    """Not a self-consistency check: these are the ratios of the figures Apple
    filed, computed by hand from the 10-K."""
    rows = FD.build_for_ticker([_apple_annual()])
    assert len(rows) == 1
    got = rows[0]["fields"]
    assert round(got["roe"], 4) == round(AAPL["ni"] / AAPL["equity"], 4) == 0.353
    assert round(got["operatingMargin"], 4) == round(AAPL["operating"] / AAPL["revenue"], 4)
    assert round(got["profitMargin"], 4) == round(AAPL["ni"] / AAPL["revenue"], 4) == 0.2667
    assert round(got["debtToEquity"], 4) == round(AAPL["liabilities"] / AAPL["equity"], 4)
    assert round(got["epsTtm"], 2) == round(AAPL["ni"] / AAPL["shares"], 2) == 44.15
    assert round(got["bookValuePerShare"], 2) == round(AAPL["equity"] / AAPL["shares"], 2)
    assert round(got["fcfPerShare"], 2) == round(
        (AAPL["ocf"] - AAPL["capex"]) / AAPL["shares"], 2) == 45.02


def test_an_annual_filing_is_taken_as_filed_not_rolled_forward():
    rows = FD.build_for_ticker([_apple_annual()])
    assert rows[0]["derivation"]["netIncome"] == FD.BASIS_ANNUAL


def test_the_record_carries_the_publication_date_untouched():
    """`availableFrom` is the only thing that licenses use, and re-deriving it
    would be a second definition of the field the collection exists for."""
    row = FD.build_for_ticker([_apple_annual()])[0]
    assert row["availableFrom"] == row["filingDate"] == row["publicationDate"] \
        == "2012-10-31"
    assert row["currency"] == "USD"
    # The period the numbers describe, which the contract requires ALONGSIDE the
    # visibility date so it can refuse a filing claiming to have been readable
    # before that period had ended.
    assert row["reportDate"] == "2012-09-29"


# --------------------------------------------------------------------------- #
# The rollforward
# --------------------------------------------------------------------------- #
def _chain(ticker="T", *, prior_full, prior_stage, this_stage, stage=FF.Q2):
    """Three filings: last year's annual, last year's same stage, this one."""
    def flow(value):
        return [_money("us-gaap_NetIncomeLoss", value)]
    return [
        _filing(ticker, 2012, FF.FY, ic=flow(prior_full),
                bs=[_money("us-gaap_StockholdersEquity", 1_000.0)]),
        _filing(ticker, 2012, stage, ic=flow(prior_stage),
                bs=[_money("us-gaap_StockholdersEquity", 1_000.0)]),
        _filing(ticker, 2013, stage, ic=flow(this_stage),
                bs=[_money("us-gaap_StockholdersEquity", 1_000.0)]),
    ]


def test_a_quarterly_figure_is_rolled_forward_not_summed():
    """`FY(Y-1) - cum(Y-1,stage) + cum(Y,stage)`. With 100 last year, 40 by the
    half last year and 60 by the half this year, twelve months is 120."""
    by_key = FD.index_filings(_chain(prior_full=100.0, prior_stage=40.0,
                                     this_stage=60.0))
    value, basis = FD.trailing_twelve_months(by_key, 2013, FF.Q2, "netIncome")
    assert value == 120.0
    assert basis == FD.BASIS_ROLLFORWARD


def test_four_cumulative_quarters_are_never_added_together():
    """The failure this guards: adding the stages counts the first quarter four
    times. Here that would give 100 + 40 + 60 = 200 instead of 120."""
    by_key = FD.index_filings(_chain(prior_full=100.0, prior_stage=40.0,
                                     this_stage=60.0))
    value, _ = FD.trailing_twelve_months(by_key, 2013, FF.Q2, "netIncome")
    assert value != 200.0


def test_a_missing_prior_annual_yields_nothing_rather_than_an_annualisation():
    """Doubling a half-year is a number where there is no number. The absence
    is what the replay can still act on."""
    records = _chain(prior_full=100.0, prior_stage=40.0, this_stage=60.0)
    without_annual = [r for r in records if FF.quarter_stage(r) != FF.FY]
    by_key = FD.index_filings(without_annual)
    value, basis = FD.trailing_twelve_months(by_key, 2013, FF.Q2, "netIncome")
    assert value is None
    assert basis == FD.BASIS_INCOMPLETE


def test_a_missing_prior_same_stage_yields_nothing_either():
    records = _chain(prior_full=100.0, prior_stage=40.0, this_stage=60.0)
    without_stage = [r for r in records
                     if not (r["fiscalYear"] == 2012 and FF.quarter_stage(r) == FF.Q2)]
    by_key = FD.index_filings(without_stage)
    assert FD.trailing_twelve_months(by_key, 2013, FF.Q2, "netIncome")[0] is None


def test_growth_compares_the_same_stage_a_year_apart():
    """Twelve months against twelve months. Comparing a quarter with a year
    would report a collapse every Q1 and a boom every Q4."""
    records = _chain(prior_full=100.0, prior_stage=40.0, this_stage=60.0)
    records += [_filing("T", 2011, FF.FY,
                        ic=[_money("us-gaap_NetIncomeLoss", 80.0)],
                        bs=[_money("us-gaap_StockholdersEquity", 1_000.0)]),
                _filing("T", 2011, FF.Q2,
                        ic=[_money("us-gaap_NetIncomeLoss", 30.0)],
                        bs=[_money("us-gaap_StockholdersEquity", 1_000.0)])]
    by_key = FD.index_filings(records)
    fields, _ = FD.derive_fields(by_key, 2013, FF.Q2)
    # Twelve months to 2012 Q2 rolls forward from FY2011 — not from FY2012,
    # which had not happened yet at that filing.
    prior = 80.0 - 30.0 + 40.0
    assert round(fields["earningsGrowth"], 6) == round((120.0 - prior) / abs(prior), 6)


# --------------------------------------------------------------------------- #
# Accounts are a measured list, not a remembered name
# --------------------------------------------------------------------------- #
def test_revenue_is_found_under_the_newer_tag_too():
    """`Revenues` alone covers 41.6% of the store; the chain covers 93.7%."""
    filing = _filing("T", 2012, FF.FY,
                     ic=[_money("us-gaap_NetIncomeLoss", 10.0),
                         _money("us-gaap_RevenueFromContractWithCustomer"
                                "ExcludingAssessedTax", 100.0)],
                     bs=[_money("us-gaap_StockholdersEquity", 50.0)])
    fields, _ = FD.derive_fields(FD.index_filings([filing]), 2012, FF.FY)
    assert fields["profitMargin"] == 0.1


def test_the_first_tag_in_the_chain_wins_when_a_filer_states_several():
    """A filer stating both the old and the new revenue tag is read under the
    one this module ranks first, not under whichever the JSON happened to list
    first — otherwise the same company changes account between filings."""
    filing = _filing("T", 2012, FF.FY,
                     ic=[_money("us-gaap_SalesRevenueNet", 200.0),
                         _money("us-gaap_Revenues", 100.0),
                         _money("us-gaap_NetIncomeLoss", 10.0)],
                     bs=[_money("us-gaap_StockholdersEquity", 50.0)])
    fields, _ = FD.derive_fields(FD.index_filings([filing]), 2012, FF.FY)
    assert fields["profitMargin"] == 0.1, "체인의 첫 태그(Revenues)가 이겨야 한다"


def test_a_per_share_value_is_never_read_as_a_total():
    """EPS arrives under an income-statement tag too. Read as a total it is
    wrong by the share count and survives every check downstream."""
    filing = _filing("T", 2012, FF.FY,
                     ic=[("us-gaap_NetIncomeLoss", 2.5, "usd/shares")],
                     bs=[_money("us-gaap_StockholdersEquity", 50.0)])
    assert FD.amount(filing, "ic", FD.FLOWS["netIncome"][1]) is None


# --------------------------------------------------------------------------- #
# Levels, liabilities and share counts
# --------------------------------------------------------------------------- #
def test_liabilities_are_read_off_the_balance_sheet_when_not_stated():
    """68.5% of filings state `Liabilities`; 99.5% state `Assets` and 98.7%
    state equity, and a balance sheet balances by construction."""
    filing = _filing("T", 2012, FF.FY,
                     bs=[_money("us-gaap_Assets", 150.0),
                         _money("us-gaap_StockholdersEquity", 50.0)])
    value, basis = FD.total_liabilities(filing)
    assert value == 100.0
    assert basis == FD.LIABILITIES_FROM_BALANCE


def test_a_stated_liability_total_is_not_recomputed():
    filing = _filing("T", 2012, FF.FY,
                     bs=[_money("us-gaap_Assets", 150.0),
                         _money("us-gaap_Liabilities", 90.0),
                         _money("us-gaap_StockholdersEquity", 50.0)])
    value, basis = FD.total_liabilities(filing)
    assert value == 90.0
    assert basis == FD.LIABILITIES_AS_FILED


def test_negative_equity_yields_no_ratio_rather_than_a_flipped_sign():
    """A ROE on negative equity ranks a distressed company as a quality name."""
    filing = _filing("T", 2012, FF.FY,
                     ic=[_money("us-gaap_NetIncomeLoss", -10.0)],
                     bs=[_money("us-gaap_StockholdersEquity", -50.0)])
    fields, _ = FD.derive_fields(FD.index_filings([filing]), 2012, FF.FY)
    assert "roe" not in fields
    assert "debtToEquity" not in fields


def test_a_share_count_is_carried_forward_from_an_earlier_filing_only():
    """25.3% of filings state no count. The nearest EARLIER one is what a
    reader on this date knew; anything later is a look-ahead."""
    counts = {(2012, FF.Q1): 100.0, (2012, FF.Q3): 300.0}
    assert FD.carried_shares(counts, 2012, FF.Q2) == (100.0, FD.SHARES_CARRIED_FORWARD)
    assert FD.carried_shares(counts, 2012, FF.Q3) == (300.0, FD.SHARES_AS_FILED)


def test_a_share_count_is_never_carried_backwards():
    counts = {(2013, FF.Q3): 300.0}
    assert FD.carried_shares(counts, 2012, FF.Q1) == (None, None)


def test_a_zero_share_count_is_absent_rather_than_zero():
    filing = _filing("T", 2012, FF.FY,
                     ic=[("us-gaap_WeightedAverageNumberOfDilutedSharesOutstanding",
                          0, "shares")])
    assert FD.share_count(filing) is None


# --------------------------------------------------------------------------- #
# What is emitted, and what is not
# --------------------------------------------------------------------------- #
def test_an_amendment_does_not_replace_what_was_visible_first():
    """286 of 33,986 periods are filed twice. Letting the restatement win would
    put corrected numbers into a window that ended before the correction
    existed."""
    first = _filing("T", 2012, FF.FY, ic=[_money("us-gaap_NetIncomeLoss", 10.0)],
                    available="2013-02-15")
    amended = _filing("T", 2012, FF.FY, ic=[_money("us-gaap_NetIncomeLoss", 7.0)],
                      available="2013-08-01", form="10-K/A")
    by_key = FD.index_filings([amended, first])
    assert by_key[(2012, FF.FY)]["availableFrom"] == "2013-02-15"


def test_a_filing_yielding_nothing_is_dropped_rather_than_emitted_empty():
    """`FundamentalStore` returns the newest visible record. An empty one would
    hide an older filing that actually had numbers."""
    empty = _filing("T", 2012, FF.FY)
    assert FD.build_for_ticker([empty]) == []


def test_rows_come_back_oldest_visible_first():
    rows = FD.build_for_ticker(_chain(prior_full=100.0, prior_stage=40.0,
                                      this_stage=60.0))
    dates = [r["availableFrom"] for r in rows]
    assert dates == sorted(dates)


def test_a_filing_with_no_readable_period_is_not_given_a_stage():
    """A transition 10-K states a period that is not a year. Guessing puts a
    quarter into the rollforward as the annual term."""
    odd = _filing("T", 2012, FF.FY)
    odd["periodDays"] = 0
    assert FD.index_filings([odd]) == {}


def test_the_coverage_report_separates_quality_from_value():
    """"We collected fundamentals" must not be read as "the value sleeve
    works" — value needs a share count and quality does not."""
    rows = FD.build_for_ticker([_apple_annual()])
    report = FD.coverage(rows)
    assert report["qualityComplete"] and report["valueComplete"]

    no_shares = _apple_annual()
    no_shares["statements"]["ic"] = [
        e for e in no_shares["statements"]["ic"] if "Shares" not in e["concept"]]
    report = FD.coverage(FD.build_for_ticker([no_shares]))
    assert report["qualityComplete"] and not report["valueComplete"]


# --------------------------------------------------------------------------- #
# The builder, which both regions share
# --------------------------------------------------------------------------- #
def _builder():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "build_pit_fundamentals", ROOT / "scripts" / "build_pit_fundamentals.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_each_region_reads_only_its_own_vendors_shards():
    """A region given the other vendor's shards would be reading Korean
    account names out of US filings and finding nothing — silently, as a store
    with no coverage rather than as an error."""
    builder = _builder()
    assert builder.REGIONS == {"kr": "dart-*.jsonl.gz", "us": "finnhub-*.jsonl.gz"}


def test_the_builder_writes_a_contract_the_store_accepts(tmp_path):
    """The acceptance test that matters: `FundamentalStore.from_jsonl` is the
    consumer, and a row it rejects is a row the replay never sees."""
    from pipeline import historical_store as HS
    from pipeline import pit_data

    store = tmp_path / "us"
    store.mkdir()
    HS.write_shard(store / "finnhub-2012.jsonl.gz", [_apple_annual()])
    out = tmp_path / "pit-us.jsonl"
    assert _builder().main([str(store), "--region", "us", "--output", str(out)]) == 0

    loaded = pit_data.FundamentalStore.from_jsonl(out)
    assert loaded.diagnostics["rowsAccepted"] == 1
    assert loaded.diagnostics["rowsRejected"] == 0
    assert loaded.tickers() == ["AAPL"]


def test_the_numbers_are_invisible_until_the_filing_date(tmp_path):
    """The whole point of the collection. A reader the day before the 10-K was
    filed had none of it."""
    from pipeline import historical_store as HS
    from pipeline import pit_data

    filing = _apple_annual()
    store = tmp_path / "us"
    store.mkdir()
    HS.write_shard(store / "finnhub-2012.jsonl.gz", [filing])
    out = tmp_path / "pit-us.jsonl"
    _builder().main([str(store), "--region", "us", "--output", str(out)])
    loaded = pit_data.FundamentalStore.from_jsonl(out)

    before, _ = loaded.visible_as_of("AAPL", "2012-10-30")
    after, _ = loaded.visible_as_of("AAPL", "2012-10-31")
    assert not before
    assert round(after["epsTtm"], 2) == 44.15


def test_an_empty_store_is_not_a_failed_build(tmp_path):
    """The collection runs on its own schedule. A replay that went red because
    the fundamentals had not arrived would be a daily red build over a file
    nobody promised for today."""
    store = tmp_path / "us"
    store.mkdir()
    assert _builder().main([str(store), "--region", "us",
                            "--output", str(tmp_path / "x.jsonl")]) == 0


def test_a_row_readable_before_its_period_ended_is_refused_by_the_contract(tmp_path):
    """Found by the contract while writing these tests, not by reasoning: a
    helper stamped every filing 12-31 and Apple's October 10-K then claimed to
    have been readable two months before its own period closed. The store
    dropped it, which is the check doing its job."""
    from pipeline import historical_store as HS
    from pipeline import pit_data

    impossible = _apple_annual()
    impossible["periodEnd"] = "2012-12-31"          # filed 2012-10-31
    store = tmp_path / "us"
    store.mkdir()
    HS.write_shard(store / "finnhub-2012.jsonl.gz", [impossible])
    out = tmp_path / "pit-us.jsonl"
    _builder().main([str(store), "--region", "us", "--output", str(out)])

    loaded = pit_data.FundamentalStore.from_jsonl(out)
    assert loaded.diagnostics["rowsAccepted"] == 0
    assert loaded.visible_as_of("AAPL", "2013-06-30") == ({}, "CURRENT_SNAPSHOT_ONLY")
