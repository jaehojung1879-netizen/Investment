"""Opening the seal: the US half enters the value and quality sleeves.

Through replay-v14 the only fundamentals file the replay read was
`pit-kr.jsonl`. `fullComposite` had zero observations on any US name and
`claimEligible` was false there, so half the production weight — value 0.3 plus
quality 0.2 — had never been computed on a US ticker in thirteen years.

What is pinned here is the discipline that makes that change safe to make:

  * the two regions are loaded APART, because they come from different vendors
    and fail separately — one total would let DART going quiet read as a US
    coverage number;
  * changing what the replay reads changes what every US signal MEANS, so it
    needs a new generation, and the version and the wiring are checked against
    each other rather than each being remembered separately.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import pit_data  # noqa: E402
from pipeline import provenance  # noqa: E402


def _row(ticker, available, **fields):
    return {
        "ticker": ticker, "reportPeriod": "2013-FY", "reportDate": "2013-12-31",
        "availableFrom": available, "filingDate": available,
        "publicationDate": available, "currency": "USD",
        "source": "finnhub/financials-reported", "sourceAsOf": "2026-09-14T00:00:00Z",
        "revisionStatus": "10-K", "fields": fields or {"roe": 0.2},
    }


def _write(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# Two regions, loaded apart
# --------------------------------------------------------------------------- #
def test_both_regions_are_visible_through_one_store(tmp_path):
    kr = _write(tmp_path / "pit-kr.jsonl", [_row("005930.KS", "2014-03-31")])
    us = _write(tmp_path / "pit-us.jsonl", [_row("AAPL", "2014-01-27")])
    store = pit_data.FundamentalStore.from_many([kr, us])
    assert store.tickers() == ["005930.KS", "AAPL"]
    assert len(store) == 2


def test_each_file_keeps_its_own_counts(tmp_path):
    """One total would let a Korean parse failure read as US coverage."""
    kr = _write(tmp_path / "pit-kr.jsonl",
                [_row("005930.KS", "2014-03-31"), {"ticker": "BROKEN"}])
    us = _write(tmp_path / "pit-us.jsonl", [_row("AAPL", "2014-01-27")])
    store = pit_data.FundamentalStore.from_many([kr, us])
    per_source = store.diagnostics["perSource"]
    assert per_source["pit-kr"]["rowsAccepted"] == 1
    assert per_source["pit-kr"]["rowsRejected"] == 1
    assert per_source["pit-us"]["rowsAccepted"] == 1
    assert per_source["pit-us"]["rowsRejected"] == 0


def test_the_totals_are_the_sum_of_the_files(tmp_path):
    kr = _write(tmp_path / "pit-kr.jsonl", [_row("005930.KS", "2014-03-31")])
    us = _write(tmp_path / "pit-us.jsonl",
                [_row("AAPL", "2014-01-27"), _row("KO", "2014-02-25")])
    store = pit_data.FundamentalStore.from_many([kr, us])
    assert store.diagnostics["rowsAccepted"] == 3
    assert store.diagnostics["rowsRead"] == 3


def test_a_ticker_in_both_files_is_reported_rather_than_buried(tmp_path):
    """Korean names carry a `.KS`/`.KQ` suffix and US ones do not, so this
    cannot happen today. It is checked so that it cannot start happening
    silently — one region's history burying the other's is invisible from the
    outside."""
    a = _write(tmp_path / "pit-kr.jsonl", [_row("AAPL", "2014-01-27")])
    b = _write(tmp_path / "pit-us.jsonl", [_row("AAPL", "2014-04-23")])
    store = pit_data.FundamentalStore.from_many([a, b])
    assert store.diagnostics["overlappingTickers"] == ["AAPL"]
    assert any("tickers_in_more_than_one_source" in e
               for e in store.diagnostics["errors"])
    # Both rows survive: dropping one silently is the failure being guarded.
    assert len(store) == 2


def test_one_file_still_loads_exactly_as_before(tmp_path):
    """The Korean half must not change shape because the US half arrived."""
    kr = _write(tmp_path / "pit-kr.jsonl", [_row("005930.KS", "2014-03-31")])
    assert pit_data.FundamentalStore.from_many([kr]).diagnostics == \
        pit_data.FundamentalStore.from_jsonl(kr).diagnostics


def test_no_files_is_not_an_error():
    """The collection runs on its own schedule; a replay that failed because a
    file had not arrived would be a daily red build."""
    store = pit_data.FundamentalStore.from_many([])
    assert not store.available
    assert store.diagnostics["contract"] == "PIT_FUNDAMENTALS_V1"


def test_publication_dates_still_gate_both_regions(tmp_path):
    """Merging must not weaken the one rule the whole collection exists for."""
    kr = _write(tmp_path / "pit-kr.jsonl", [_row("005930.KS", "2014-03-31")])
    us = _write(tmp_path / "pit-us.jsonl", [_row("AAPL", "2014-01-27")])
    store = pit_data.FundamentalStore.from_many([kr, us])
    assert store.visible_as_of("AAPL", "2014-01-26")[0] == {}
    assert store.visible_as_of("AAPL", "2014-01-27")[0] != {}
    assert store.visible_as_of("005930.KS", "2014-01-27")[0] == {}


# --------------------------------------------------------------------------- #
# The seal
# --------------------------------------------------------------------------- #
def _replay_workflow() -> str:
    return (ROOT / ".github" / "workflows" / "replay.yml").read_text(encoding="utf-8")


def test_the_replay_reads_both_regions():
    workflow = _replay_workflow()
    for region in ("kr", "us"):
        assert f"--pit-fundamentals replay-work/ledger/fundamentals/pit-{region}.jsonl" \
            in workflow
        assert f"--region {region}" in workflow


def test_reading_the_us_filings_is_recorded_in_the_data_version():
    """The version and the wiring are checked against each other rather than
    each being remembered separately. A replay that reads new inputs under an
    unchanged DATA_VERSION would publish signals that are not comparable with
    the generation they were filed under, and nothing downstream could tell."""
    if "pit-us.jsonl" in _replay_workflow():
        assert "finnhub-pit-fundamentals-us-v1" in provenance.DATA_VERSION, \
            "미국 재무를 읽기 시작했으면 DATA_VERSION 이 그것을 말해야 한다"


def test_the_generation_moved_past_the_one_that_had_no_us_fundamentals():
    """v14 is the generation in which no US name ever had a value or quality
    score. Its records stay sealed; this is a different experiment."""
    assert provenance.REPLAY_VERSION != "replay-v14"
    assert provenance.REPLAY_VERSION.startswith("replay-v")


def test_the_version_bump_is_explained_where_the_versions_live():
    """Every prior generation says in `provenance.py` why it could not extend
    the last one. A bump without that is a number nobody can audit."""
    text = (ROOT / "pipeline" / "provenance.py").read_text(encoding="utf-8")
    head = text[:text.index("REPLAY_VERSION = ")]
    assert "v15" in head
    assert "pit-us.jsonl" in head or "pit-us" in head
