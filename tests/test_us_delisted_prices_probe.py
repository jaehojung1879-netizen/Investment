"""The scoring the US delisted-price probe hangs its verdicts on.

No network: every test feeds the parsers and classifiers the shapes the vendors
actually return, because the part of a probe that can silently be wrong is not
the request, it is what it decides the answer meant.
"""
import json
from pathlib import Path

import pytest

from scripts import probe_us_delisted_prices as P


ROOT = Path(__file__).resolve().parent.parent


def _span(dates, listed="2013-01-02", delisted="2018-01-02"):
    return P.classify_rows(dates, listed, delisted)


def _daily(start, end):
    """Every calendar day in [start, end] — the shape a daily vendor returns."""
    import datetime as dt
    first = dt.date.fromisoformat(start)
    last = dt.date.fromisoformat(end)
    return [(first + dt.timedelta(days=i)).isoformat()
            for i in range((last - first).days + 1)]


def test_a_vendor_spanning_the_whole_membership_is_full():
    status, share = _span(_daily("2013-01-02", "2018-01-02"))
    assert status == P.SERVED_FULL
    assert share == pytest.approx(1.0)


def test_a_two_year_window_inside_a_five_year_membership_is_partial_not_served():
    # The failure this exists for: a vendor answers, the ticker looks covered,
    # and three of the five years the replay needs are missing.
    status, share = _span(_daily("2016-01-01", "2017-12-31"))
    assert status == P.SERVED_PARTIAL
    assert 0.10 <= share < 1.0


def test_history_entirely_outside_the_membership_span_counts_as_empty():
    status, share = _span(_daily("2020-01-01", "2024-12-31"))
    assert status == P.SERVED_EMPTY
    assert share == 0.0


def test_no_rows_is_empty_not_an_error():
    assert _span([]) == (P.SERVED_EMPTY, 0.0)


def test_coverage_is_measured_against_the_name_not_the_replay():
    # A name that was only a member for 2017 is fully served by 2017 alone,
    # even though the replay itself runs from 2013.
    status, _ = P.classify_rows(_daily("2017-01-02", "2017-12-29"),
                                "2017-01-02", "2017-12-29")
    assert status == P.SERVED_FULL


def test_the_edge_tolerance_means_the_same_thing_at_every_membership_length():
    # The rule this replaced was a share of the span, which silently tightened
    # as memberships got shorter: a vendor starting a week late passed on a
    # decade and failed on a single year. The cohort holds both.
    short = P.classify_rows(_daily("2017-01-09", "2017-12-29"),
                            "2017-01-02", "2017-12-29")
    long = P.classify_rows(_daily("2013-01-09", "2023-01-02"),
                           "2013-01-02", "2023-01-02")
    assert short[0] == P.SERVED_FULL
    assert long[0] == P.SERVED_FULL


def test_a_vendor_that_stops_well_before_the_name_left_is_not_full():
    # Missing the delisting itself is the expensive end to miss: the last
    # months of a departing name are where the survivorship signal lives.
    status, share = P.classify_rows(_daily("2013-01-02", "2017-06-01"),
                                    "2013-01-02", "2018-01-02")
    assert status == P.SERVED_PARTIAL
    assert share > 0.10


def test_a_vendor_that_misses_the_control_proves_nothing_about_delisting():
    control = [{"ticker": "AAPL", "status": P.SERVED_EMPTY}]
    departed = [{"ticker": "YHOO", "status": P.SERVED_EMPTY}]
    assert P.vendor_verdict(departed, control) == "VENDOR_UNUSABLE"


def test_serving_the_control_but_no_departed_name_is_a_real_finding():
    control = [{"ticker": "AAPL", "status": P.SERVED_FULL}]
    departed = [{"ticker": "YHOO", "status": P.SERVED_EMPTY},
                {"ticker": "ATVI", "status": P.SERVED_EMPTY}]
    assert P.vendor_verdict(departed, control) == "DEPARTED_REFUSED"


def test_one_partially_served_departed_name_opens_the_vendor():
    control = [{"ticker": "AAPL", "status": P.SERVED_FULL}]
    departed = [{"ticker": "YHOO", "status": P.SERVED_PARTIAL},
                {"ticker": "ATVI", "status": P.SERVED_EMPTY}]
    assert P.vendor_verdict(departed, control) == "OPEN"


def test_rate_limited_names_never_count_as_served():
    control = [{"ticker": "AAPL", "status": P.SERVED_FULL}]
    departed = [{"ticker": "YHOO", "status": P.RATE_LIMITED}]
    # Probes run #2 read a rate-limited cohort as a vendor verdict. It is not
    # one, and it must not be read as evidence the vendor has the name either.
    assert P.vendor_verdict(departed, control) == "DEPARTED_REFUSED"


def test_csv_parser_reads_stooq_shape_and_refuses_an_error_page():
    body = (b"Date,Open,High,Low,Close,Volume\n"
            b"2013-01-02,10,11,9,10.5,1000\n"
            b"2013-01-03,10.5,11,10,10.8,900\n")
    assert P._dates_from_csv(body) == ["2013-01-02", "2013-01-03"]
    assert P._dates_from_csv(b"Exceeded the daily hits limit") == []
    assert P._dates_from_csv(b"") == []


def test_csv_parser_refuses_a_multi_line_page_that_is_not_a_price_csv():
    # The single-line limit message is the easy case. A vendor that answers
    # with an HTML page — or with any multi-line body whose first column
    # happens to parse as a date — must not be read as served history, or an
    # error page becomes evidence that a dead ticker has bars.
    html = (b"<html>\n<head><title>Stooq</title></head>\n"
            b"<body>2013-01-02, no data</body>\n</html>")
    assert P._dates_from_csv(html) == []
    headerless = b"2013-01-02,10,11\n2013-01-03,10,11\n"
    assert P._dates_from_csv(headerless) == []


def test_sample_spreads_across_the_departure_era_not_the_alphabet():
    members = [{"ticker": f"T{i:03d}", "listed": "2013-01-02",
                "delisted": f"{2013 + i // 20}-06-01"} for i in range(100)]
    picked = P.pick_sample(members, 10)
    assert len(picked) == 10
    years = {row["delisted"][:4] for row in picked}
    # The 2013-2016 departures are the ones the coverage table says hurt most;
    # an alphabetical head would have been all one era.
    assert len(years) >= 4
    assert P.pick_sample(members, 10) == picked, "sampling must be deterministic"


def test_asking_for_more_than_the_cohort_returns_the_cohort():
    members = [{"ticker": "A", "listed": "2013-01-02", "delisted": "2014-01-02"}]
    assert P.pick_sample(members, 50) == members


def test_cohort_file_is_shaped_the_way_the_probe_reads_it():
    cohort = json.loads((ROOT / "data" / "us-unpriced-members.json").read_text(encoding="utf-8"))
    assert cohort["schema"] == "US_UNPRICED_MEMBERS_V1"
    assert cohort["unpriced"] == len(cohort["members"])
    for row in cohort["members"]:
        assert row["listed"] and row["delisted"], row
        assert " " not in row["ticker"], "a company name is not a ticker"
        assert row["listed"] < row["delisted"], row


def test_every_cohort_member_left_the_index_which_is_what_makes_this_survivorship():
    cohort = json.loads((ROOT / "data" / "us-unpriced-members.json").read_text(encoding="utf-8"))
    # If a still-listed member were unpriced, the gap would be a download bug
    # rather than a survivorship gap, and this probe would be asking the wrong
    # question of the wrong vendors.
    assert cohort["unpricedAllHaveDelistedDate"] is True
    assert all(row["delisted"] for row in cohort["members"])


def test_the_probe_is_registered_in_the_workflow_with_its_keys():
    # A probe CI cannot run is a measurement that never gets taken.
    workflow = (ROOT / ".github" / "workflows" / "probes.yml").read_text(encoding="utf-8")
    assert "- us-delisted-prices" in workflow
    assert "us-delisted-prices)    script=probe_us_delisted_prices.py" in workflow
    for env in ("POLYGON_API_KEY", "FINNHUB_API_KEY", "FMP_API_KEY", "ALPHAVANTAGE_API_KEY"):
        line = next(row for row in workflow.splitlines() if row.strip().startswith(env))
        assert "us-delisted-prices" in line, f"{env} is not passed to this probe"


@pytest.mark.parametrize("vendor", sorted(P.VENDORS))
def test_every_vendor_declares_whether_it_needs_a_credential(vendor):
    fetch, env = P.VENDORS[vendor]
    assert callable(fetch)
    assert env is None or env.endswith("_API_KEY")
