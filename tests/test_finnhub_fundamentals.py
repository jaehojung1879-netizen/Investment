"""What the US collection stores, and what it refuses to.

The network half runs in CI. What is pinned here is every rule that decides
whether a stored row is usable — and each one is a mistake this repository has
already paid for somewhere else:

  * a filing that cannot say when it became visible is not coverage, it is a
    row that looks like coverage (the DART receipt-date rule);
  * a rate limit is not an absence (polygon, probe run #2);
  * a tag vocabulary is measured, not normalised at collection time, because a
    normalisation cannot be revisited without re-fetching (polygon again);
  * period length is counted PER FORM, because a pooled count cannot say
    whether a Q3 income figure is three months or nine — which is the number a
    trailing-twelve-month figure is built from.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import finnhub_fundamentals as FF  # noqa: E402
from pipeline import historical_store as HS  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "collect_finnhub_fundamentals", ROOT / "scripts" / "collect_finnhub_fundamentals.py")
C = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = C
_spec.loader.exec_module(C)

_mspec = importlib.util.spec_from_file_location(
    "measure_us_period_semantics", ROOT / "scripts" / "measure_us_period_semantics.py")
M = importlib.util.module_from_spec(_mspec)
sys.modules[_mspec.name] = M
_mspec.loader.exec_module(M)


def _filing(**kw):
    base = {
        "accessNumber": "0000320193-12-000105", "symbol": "AAPL", "cik": "320193",
        "year": 2012, "quarter": 4, "form": "10-K",
        "startDate": "2011-09-25 00:00:00", "endDate": "2012-09-29 00:00:00",
        "filedDate": "2012-10-31 00:00:00", "acceptedDate": "2012-10-31 16:30:00",
        "report": {"ic": [{"concept": "NetIncomeLoss", "label": "Net income",
                           "unit": "usd", "value": 41733000000}],
                   "bs": [{"concept": "Assets", "label": "Total assets",
                           "unit": "usd", "value": 176064000000}],
                   "cf": []},
    }
    base.update(kw)
    return base


# --------------------------------------------------------------------------- #
# The publication date is the whole reason this collection exists
# --------------------------------------------------------------------------- #
def test_a_filing_with_no_filed_date_is_refused():
    record, reason = FF.build_record("AAPL", _filing(filedDate=""), "2026-09-13T00:00:00Z")
    assert record is None
    assert reason == FF.NO_FILING_DATE


def test_the_filed_date_becomes_available_from_untouched():
    record, _ = FF.build_record("AAPL", _filing(), "2026-09-13T00:00:00Z")
    assert record["availableFrom"] == "2012-10-31"
    assert record["acceptedDate"] == "2012-10-31 16:30:00", \
        "타임스탬프는 날짜 옆에 남되 날짜를 대체하지 않는다"


def test_a_filing_with_no_accession_has_no_identity_and_is_refused():
    record, reason = FF.build_record("AAPL", _filing(accessNumber=""), "z")
    assert record is None and reason == FF.NO_ACCESSION


def test_a_filing_with_no_period_end_is_refused():
    record, reason = FF.build_record("AAPL", _filing(endDate=""), "z")
    assert record is None and reason == FF.NO_PERIOD


def test_the_same_filing_from_two_windows_has_one_identity():
    a, _ = FF.build_record("AAPL", _filing(), "z")
    b, _ = FF.build_record("AAPL", _filing(), "z")
    assert a["id"] == b["id"] == FF.filing_id("AAPL", "0000320193-12-000105")


# --------------------------------------------------------------------------- #
# Stored as the filer stated it — a normalisation applied here cannot be
# revisited without re-fetching
# --------------------------------------------------------------------------- #
def test_concepts_are_kept_under_the_filers_own_tags():
    record, _ = FF.build_record("AAPL", _filing(), "z")
    assert record["statements"]["ic"][0]["concept"] == "NetIncomeLoss"
    assert record["statements"]["bs"][0]["concept"] == "Assets"


def test_the_value_and_unit_ride_along_with_every_concept():
    entry = FF.build_record("AAPL", _filing(), "z")[0]["statements"]["ic"][0]
    assert entry["value"] == 41733000000 and entry["unit"] == "usd"


def test_a_missing_statement_section_is_empty_not_absent():
    record, _ = FF.build_record("AAPL", _filing(report={"ic": []}), "z")
    assert record["statements"] == {"bs": [], "ic": [], "cf": []}


# --------------------------------------------------------------------------- #
# The period is stated by the filing, and is what the derivation turns on
# --------------------------------------------------------------------------- #
def test_period_length_is_read_from_the_filings_own_dates():
    assert FF.period_days("2011-09-25", "2012-09-29") == 370
    assert FF.period_days("2012-06-30", "2012-09-29") == 91


def test_a_period_with_no_dates_is_unstated_rather_than_guessed():
    assert FF.period_days(None, "2012-09-29") is None
    assert FF.period_bucket(None) == "unstated"


def test_period_buckets_separate_a_quarter_from_a_year():
    assert FF.period_bucket(91) == "quarter (46-135d)"
    assert FF.period_bucket(273) == "three quarters (226-315d)"
    assert FF.period_bucket(365) == "year (316-400d)"


def test_the_inventory_counts_period_length_per_form_not_pooled():
    """A pooled count told the Korean collector nothing about WHICH rows
    carried a year-to-date column, and that was the number the TTM needed."""
    records = [
        FF.build_record("AAPL", _filing(form="10-K", startDate="2011-09-25",
                                        endDate="2012-09-29"), "z")[0],
        FF.build_record("AAPL", _filing(form="10-Q", accessNumber="a2",
                                        startDate="2012-06-30",
                                        endDate="2012-09-29"), "z")[0],
        FF.build_record("AAPL", _filing(form="10-Q", accessNumber="a3",
                                        startDate="2012-01-01",
                                        endDate="2012-09-29"), "z")[0],
    ]
    report = FF.inventory(records)
    assert report["periodLengthByForm"]["10-K"] == {"year (316-400d)": 1}
    tenq = report["periodLengthByForm"]["10-Q"]
    assert tenq["quarter (46-135d)"] == 1
    assert tenq["three quarters (226-315d)"] == 1, \
        "같은 10-Q 안에 분기와 누계가 섞여 있다는 것이 파생이 물어야 할 질문이다"


def test_the_inventory_names_the_concepts_that_actually_arrived():
    records = [FF.build_record("AAPL", _filing(), "z")[0]]
    report = FF.inventory(records)
    assert "NetIncomeLoss" in report["topConcepts"]["ic"]
    assert "Assets" in report["topConcepts"]["bs"]
    assert report["units"] == {"usd": 2}


# --------------------------------------------------------------------------- #
# A rate limit is not an absence
# --------------------------------------------------------------------------- #
def test_a_rate_limit_is_recognised_by_status_and_by_sentence():
    assert FF.is_rate_limited(429, "")
    assert FF.is_rate_limited(200, "You've exceeded the maximum requests per minute")
    assert FF.is_rate_limited(403, "API limit reached")


def test_an_ordinary_refusal_is_not_read_as_a_rate_limit():
    assert not FF.is_rate_limited(401, "Please use an API key.")
    assert not FF.is_rate_limited(200, '{"data": []}')


def test_a_rate_limited_window_is_not_marked_done(monkeypatch, tmp_path):
    """polygon refused three of four samples this way and the verdict read it
    as missing coverage. A window we were told to slow down on has not been
    asked, and the next run has to ask it."""
    monkeypatch.setenv("FINNHUB_API_KEY", "k")
    monkeypatch.setattr(C.time, "sleep", lambda *_: None)
    monkeypatch.setattr(C, "fetch_window", lambda *a, **k: ([], "RATE_LIMITED"))
    assert C.main([str(tmp_path), "--tickers", "AAPL", "--from-year", "2012",
                   "--through", "2013-06-30", "--pace", "0"]) == 0
    assert C.load_done_windows(tmp_path) == set(), \
        "속도 제한을 받은 창을 완료로 적으면 영원히 다시 묻지 않는다"


def test_a_served_window_is_marked_done_even_when_it_held_nothing(monkeypatch, tmp_path):
    """An empty window that was genuinely asked must not be re-bought every
    run; the shards alone cannot tell it from one never asked."""
    monkeypatch.setenv("FINNHUB_API_KEY", "k")
    monkeypatch.setattr(C.time, "sleep", lambda *_: None)
    monkeypatch.setattr(C, "fetch_window", lambda *a, **k: ([], "SERVED"))
    C.main([str(tmp_path), "--tickers", "AAPL", "--from-year", "2012",
            "--through", "2013-06-30", "--pace", "0"])
    assert C.load_done_windows(tmp_path) == {
        ("AAPL", "2012-01-01", "2013-06-30", FF.QUARTERLY),
        ("AAPL", "2012-01-01", "2013-06-30", FF.ANNUAL),
    }


# --------------------------------------------------------------------------- #
# Windows, work list, shards
# --------------------------------------------------------------------------- #
def test_windows_are_gapless_and_do_not_overlap():
    spans = FF.windows(2012, "2026-09-13")
    for (_, end), (start, _) in zip(spans, spans[1:]):
        assert date.fromisoformat(start) == date.fromisoformat(end) + timedelta(days=1)


def test_windows_start_a_year_before_the_replay_so_the_first_ttm_exists():
    assert FF.FIRST_YEAR == 2012
    assert FF.windows(FF.FIRST_YEAR, "2013-06-30")[0][0] == "2012-01-01"


def test_windows_are_the_same_list_on_two_runs():
    assert FF.windows(2012, "2026-09-13") == FF.windows(2012, "2026-09-13")


def test_the_work_list_spends_the_budget_on_the_oldest_windows_first():
    spans = FF.windows(2012, "2015-12-31")
    work = FF.work_list(["AAPL", "KO"], spans, set())
    assert work[0][1] == spans[0][0], "리플레이가 못 채우는 초기 단면부터 사야 한다"
    assert [w[1] for w in work] == sorted(w[1] for w in work)


def test_the_work_list_skips_windows_already_asked():
    spans = FF.windows(2012, "2013-06-30")
    done = {("AAPL", spans[0][0], spans[0][1], freq) for freq in FF.FREQUENCIES}
    assert FF.work_list(["AAPL", "KO"], spans, done) == [
        ("KO", spans[0][0], spans[0][1], FF.ANNUAL),
        ("KO", spans[0][0], spans[0][1], FF.QUARTERLY),
    ]


def test_a_shard_is_keyed_by_the_period_reported_on_not_the_filing_date():
    """A January filing about last year belongs with the year it describes."""
    record, _ = FF.build_record("AAPL", _filing(year=2012, filedDate="2013-01-30"), "z")
    assert FF.shard_year(record) == 2012


def test_a_shard_year_falls_back_to_the_period_end_when_the_year_is_absent():
    record, _ = FF.build_record("AAPL", _filing(year=None), "z")
    assert FF.shard_year(record) == 2012


# --------------------------------------------------------------------------- #
# The universe is every name that was ever a member
# --------------------------------------------------------------------------- #
def test_the_collection_universe_includes_the_names_that_have_left(tmp_path):
    history = tmp_path / "universe-history.json"
    history.write_text(json.dumps({
        "AAPL": {"listed": "2012-12-27", "delisted": None, "region": "US"},
        "ANR": {"listed": "2012-12-27", "delisted": "2013-05-05", "region": "US"},
        "005930.KS": {"listed": "2012-12-27", "delisted": None, "region": "KR"},
    }))
    members = C.us_members(history)
    assert members == ["AAPL", "ANR"], \
        "떠난 이름을 빼면 미국 재무에 생존 편향을 다시 만든다"


def test_the_real_universe_is_every_us_member_not_todays_list():
    assert len(C.us_members()) > 500


# --------------------------------------------------------------------------- #
# Two tag spellings, one account
# --------------------------------------------------------------------------- #
def test_the_two_spellings_of_a_gaap_tag_are_the_same_account():
    """`us-gaap_Assets` and `Assets` both arrive from this vendor."""
    assert FF.strip_namespace("us-gaap_Assets") == "Assets"
    assert FF.strip_namespace("us-gaap:NetIncomeLoss") == "NetIncomeLoss"
    assert FF.strip_namespace("Assets") == "Assets"


def test_a_filers_own_extension_tag_is_not_collapsed():
    """The failure this guards is silent: `AcmeCorp_SpecialCharge` collapsed to
    `SpecialCharge` merges one company's bespoke line into an account that
    means something else, and nothing downstream can tell."""
    assert FF.strip_namespace("AcmeCorp_SpecialCharge") == "AcmeCorp_SpecialCharge"
    assert FF.strip_namespace("XYZ_Revenues") == "XYZ_Revenues"


def test_the_other_real_namespaces_are_stripped_too():
    assert FF.strip_namespace("dei_EntityCommonStockSharesOutstanding") == \
        "EntityCommonStockSharesOutstanding"
    assert FF.strip_namespace("ifrs-full_Assets") == "Assets"


def test_a_missing_concept_survives_stripping():
    assert FF.strip_namespace(None) == ""


# --------------------------------------------------------------------------- #
# Eight unit spellings, three meanings
# --------------------------------------------------------------------------- #
def test_every_currency_spelling_seen_classifies_as_currency():
    for unit in ("usd", "USD", "_usd", "usdollar"):
        assert FF.unit_class(unit) == FF.CURRENCY, unit


def test_every_per_share_spelling_classifies_as_per_share_not_currency():
    """Per-share is tested before currency on purpose: `usd/shares` contains
    `usd`, and reading an EPS as a dollar amount produces a number nothing
    downstream can tell apart from a real one."""
    for unit in ("usd/shares", "usd/share", "_usd_/_shares", "USD/shares"):
        assert FF.unit_class(unit) == FF.PER_SHARE, unit


def test_a_share_count_is_neither_money_nor_per_share():
    assert FF.unit_class("shares") == FF.SHARES


def test_an_unrecognised_unit_is_named_rather_than_guessed():
    assert FF.unit_class("unit12") == FF.UNCLASSIFIED
    assert FF.unit_class(None) == FF.UNCLASSIFIED


# --------------------------------------------------------------------------- #
# The annual pass, and not re-buying the quarterly one
# --------------------------------------------------------------------------- #
def test_the_work_list_covers_both_frequencies():
    work = FF.work_list(["AAPL"], [("2012-01-01", "2013-06-30")], set())
    assert [item[3] for item in work] == [FF.ANNUAL, FF.QUARTERLY], \
        "FY 항이 없으면 rollforward TTM 자체가 불가능하므로 연간이 먼저다"


def test_a_window_already_bought_quarterly_is_not_re_bought(tmp_path):
    """The 1,500 quarterly calls of the first slice are already paid for."""
    # Through the migration, not around it: in the real run the done set is
    # whatever `windows.json` from the first slice normalises to.
    done = FF.normalise_done([["AAPL", "2012-01-01", "2013-06-30"]])
    work = FF.work_list(["AAPL"], [("2012-01-01", "2013-06-30")], done)
    assert [item[3] for item in work] == [FF.ANNUAL]


def test_a_legacy_done_entry_means_the_pass_it_was_written_by():
    """`windows.json` from the first slice holds three-item entries. Reading
    them as 'both frequencies done' would skip every annual call; reading them
    as 'nothing done' would re-buy 1,500 windows."""
    migrated = FF.normalise_done([["AAPL", "2012-01-01", "2013-06-30"]])
    assert migrated == {("AAPL", "2012-01-01", "2013-06-30", FF.QUARTERLY)}


def test_a_record_remembers_which_pass_fetched_it():
    record, _ = FF.build_record("AAPL", _filing(), "z", FF.ANNUAL)
    assert record["requestedFreq"] == FF.ANNUAL


# --------------------------------------------------------------------------- #
# Is a 10-Q's income statement the quarter, or the year to date?
# --------------------------------------------------------------------------- #
def _flow(ticker, year, stage, value, concept="us-gaap_NetIncomeLoss",
          unit="usd", section="ic"):
    days = {"Q1": 90, "Q2": 181, "Q3": 273, "FY": 365}[stage]
    statements = {"ic": [], "bs": [], "cf": []}
    statements[section] = [{"concept": concept, "unit": unit, "value": value,
                            "label": "x"}]
    return {"id": f"{ticker}-{year}-{stage}", "ticker": ticker, "fiscalYear": year,
            "form": "10-K" if stage == "FY" else "10-Q", "periodDays": days,
            "statements": statements}


def _year_of(ticker, year, quarters, cumulative, **kw):
    running, rows = 0.0, []
    for stage, amount in zip(("Q1", "Q2", "Q3"), quarters[:3]):
        running += amount
        rows.append(_flow(ticker, year, stage, running if cumulative else amount, **kw))
    rows.append(_flow(ticker, year, "FY", sum(quarters), **kw))
    return rows


def _population(cumulative, n=40, seasonal=True, **kw):
    rows = []
    for i in range(n):
        # Deliberately uneven quarters, and a DIFFERENT shape per company: a
        # method that only works on firms earning evenly through the year is
        # not a method, and one shared seasonal shape would give every firm the
        # identical ratio, which a median cannot then improve on.
        shape = [0.6, 1.4, 0.8, 1.2] if seasonal else [1.0] * 4
        turn = i % 4
        swing = shape[turn:] + shape[:turn]
        quarters = [100e6 * s * (1 + i / 50) for s in swing]
        rows += _year_of(f"T{i:03d}", 2012, quarters, cumulative, **kw)
    return rows


def test_cumulative_filings_are_read_as_cumulative():
    result = FF.period_semantics(_population(cumulative=True))
    assert result["verdict"] == FF.CUMULATIVE
    assert 1.6 <= result["medians"]["halfOverFirst"] <= 2.4


def test_independent_quarters_are_read_as_independent_quarters():
    """The same instrument has to be able to return the other answer, or it is
    not measuring anything."""
    result = FF.period_semantics(_population(cumulative=False))
    assert result["verdict"] == FF.DISCRETE_QUARTERS
    assert 0.7 <= result["medians"]["halfOverFirst"] <= 1.3


def test_a_seasonal_company_does_not_decide_on_its_own():
    """One firm earning everything in Q4 sits opposite whichever reading it
    happens to contradict. The median across companies is the statistic."""
    rows = _year_of("SEASONAL", 2012, [1e6, 1e6, 1e6, 400e6], cumulative=True)
    result = FF.period_semantics(rows)
    assert result["verdict"] == FF.INCONCLUSIVE
    assert "표본" in result["meaning"]


def test_a_handful_of_companies_does_not_earn_a_verdict():
    """Ratios dead on 2.0 and 3.0, so the only thing that can withhold the
    verdict is the sample floor itself."""
    rows = _population(cumulative=True, n=FF.MIN_RATIOS - 1, seasonal=False)
    result = FF.period_semantics(rows)
    assert result["medians"]["halfOverFirst"] == 2.0
    assert result["verdict"] == FF.INCONCLUSIVE, \
        "벤더 전체를 판정하는 답이 소수 기업에 얹혀서는 안 된다"


def test_enough_companies_does():
    """The same population one company larger — seasonal, as real ones are."""
    result = FF.period_semantics(_population(cumulative=True, n=FF.MIN_RATIOS))
    assert result["verdict"] == FF.CUMULATIVE


def test_one_wild_company_cannot_move_the_answer():
    """Why the statistic is a median and not a mean. Five companies whose first
    quarter was near break-even produce ratios in the thousands; a mean of the
    whole population is then a number no company has, and the verdict flips."""
    rows = _population(cumulative=True, seasonal=False)
    for i in range(5):
        rows += _year_of(f"WILD{i}", 2012, [100.0, 1e6, 1e6, 1e6], cumulative=True)
    result = FF.period_semantics(rows)
    assert result["medians"]["halfOverFirst"] == 2.0
    assert result["verdict"] == FF.CUMULATIVE


def test_ratios_that_land_between_the_two_readings_decide_nothing():
    """1.5 is neither 2.0 nor 1.0. Naming that is the point; picking the
    nearer band would turn an unexplained result into a confident sentence."""
    rows = []
    for i in range(40):
        rows += _year_of(f"T{i:03d}", 2012, [100e6, 50e6, 0.0, 100e6],
                         cumulative=True)
    result = FF.period_semantics(rows)
    assert result["verdict"] == FF.INCONCLUSIVE


def test_a_near_zero_first_quarter_is_not_used_as_a_denominator():
    """A company that broke even in Q1 produces a ratio in the millions, and a
    median is moved by enough of them."""
    rows = _population(cumulative=True)
    rows += _year_of("BREAKEVEN", 2012, [0.4, 200e6, 200e6, 200e6], cumulative=True)
    result = FF.period_semantics(rows)
    assert result["counts"]["halfOverFirst"] == 40
    assert result["verdict"] == FF.CUMULATIVE


def test_a_balance_sheet_level_is_not_asked_the_question():
    """Total assets is a stock at a date; its ratio across quarters says
    nothing about whether an income statement is cumulative."""
    assert "assets" not in FF.FLOW_CONCEPTS
    rows = _population(cumulative=True, concept="us-gaap_Assets", section="bs")
    assert FF.period_semantics(rows)["counts"]["tickerYears"] == 0


def test_the_account_is_found_under_either_tag_spelling():
    plain = FF.period_semantics(_population(True, concept="NetIncomeLoss"))
    prefixed = FF.period_semantics(_population(True, concept="us-gaap_NetIncomeLoss"))
    assert plain["verdict"] == prefixed["verdict"] == FF.CUMULATIVE


def test_a_per_share_figure_is_never_divided_by_a_dollar_one():
    """EPS arrives under an income-statement tag too. Mixing the two produces a
    ratio that is not a ratio of anything."""
    rows = _population(cumulative=True, unit="usd/shares")
    assert FF.period_semantics(rows)["counts"]["tickerYears"] == 0


def test_the_stage_comes_from_the_period_length_not_the_quarter_number():
    """`fiscalQuarter` says which report it is; what decides the ratio is how
    much of the year the numbers cover."""
    record = _flow("AAPL", 2012, "Q3", 1.0)
    record["fiscalQuarter"] = 1
    assert FF.quarter_stage(record) == FF.Q3


def test_an_annual_report_is_the_full_year_stage():
    assert FF.quarter_stage(_flow("AAPL", 2012, "FY", 1.0)) == FF.FY


# --------------------------------------------------------------------------- #
# The measurement, read across accounts
# --------------------------------------------------------------------------- #
def test_accounts_that_disagree_are_reported_as_a_finding_not_averaged():
    """Net income cumulative and cash flow quarterly would mean the vendor
    flattens the two statements differently. Averaging that into one verdict
    would produce a confident sentence over a contradiction."""
    rows = _population(cumulative=True)
    rows += _population(cumulative=False,
                        concept="NetCashProvidedByUsedInOperatingActivities",
                        section="cf")
    result = M.report(rows)
    assert result["verdict"] == FF.INCONCLUSIVE
    assert result["byConcept"]["netIncome"]["verdict"] == FF.CUMULATIVE
    assert result["byConcept"]["operatingCashFlow"]["verdict"] == FF.DISCRETE_QUARTERS
    assert "평균" in result["agreement"]


def test_agreement_counts_the_accounts_that_decided_not_all_of_them():
    """Two of the four accounts here have no data at all. Calling that
    unanimity would make one measurement read like four."""
    result = M.report(_population(cumulative=True))
    assert result["verdict"] == FF.CUMULATIVE
    assert "1개 계정" in result["agreement"]


def test_a_run_that_could_not_decide_does_not_exit_green(tmp_path, capsys):
    """A green check on an undecided measurement is a green check that implies
    an answer."""
    store = tmp_path / "us"
    store.mkdir()
    HS.write_shard(store / "finnhub-2012.jsonl.gz",
                   _year_of("SOLO", 2012, [1e6, 2e6, 3e6, 4e6], cumulative=True))
    assert M.main([str(store)]) == 2


def test_a_decided_run_exits_green(tmp_path):
    store = tmp_path / "us"
    store.mkdir()
    HS.write_shard(store / "finnhub-2012.jsonl.gz", _population(cumulative=True))
    assert M.main([str(store)]) == 0


def test_an_empty_store_is_an_error_rather_than_a_verdict(tmp_path):
    store = tmp_path / "us"
    store.mkdir()
    assert M.main([str(store)]) == 1
