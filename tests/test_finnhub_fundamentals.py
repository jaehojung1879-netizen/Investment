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

_spec = importlib.util.spec_from_file_location(
    "collect_finnhub_fundamentals", ROOT / "scripts" / "collect_finnhub_fundamentals.py")
C = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = C
_spec.loader.exec_module(C)


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
    assert C.load_done_windows(tmp_path) == {("AAPL", "2012-01-01", "2013-06-30")}


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
    done = {("AAPL", spans[0][0], spans[0][1])}
    assert FF.work_list(["AAPL", "KO"], spans, done) == [("KO", spans[0][0], spans[0][1])]


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
