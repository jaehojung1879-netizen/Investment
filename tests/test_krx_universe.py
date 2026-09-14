"""Reconstructing a dated Korean universe, and the ways it goes silently wrong.

Korea has been survivors-only for the whole life of the replay: with no
membership rows, `snapshot` keeps today's names on every date, and replay-v15's
`survivorshipBound` came back REVERSES_UNDER_MEASURED_GAP with KR stressed at
100%. Probes run #4 found the source that closes it — `sto/stk_bydd_trd`,
POINT_IN_TIME, 210 departed issues between 2013 and today.

Getting it wrong is worse than leaving it open, which is why two earlier
Korean attempts were deleted. The failures that produce no error at all:

  * an unreadable market cap ranked as zero, which sorts a real company to the
    bottom of the exchange and silently evicts it from the universe;
  * a holiday recorded under the date we ASKED for, putting two snapshots on
    one date and none on the other;
  * a response that was not understood read as "nothing traded", which would
    delist the entire exchange for that date;
  * the market-cap rule alone, which gives every configured name outside
    today's top-N a `delisted` date and shrinks the live universe.

Each has its own test here, because each would look like a working build.
"""
from __future__ import annotations

import pytest

from pipeline import krx_universe as KU


def _payload(rows, key="OutBlock_1"):
    return {key: rows}


def _row(code, cap, name="이름", shares="1000", date="20130102"):
    return {"ISU_CD": code, "ISU_NM": name, "MKTCAP": cap,
            "LIST_SHRS": shares, "BAS_DD": date}


# ---------------------------------------------------------------- numbers

@pytest.mark.parametrize("raw,expected", [
    ("1,234,567", 1234567.0),
    ("  42 ", 42.0),
    ("0", 0.0),
])
def test_krx_numeric_strings_are_read(raw, expected):
    assert KU.parse_number(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "   ", "-", "--", "n/a"])
def test_unreadable_figures_are_none_not_zero(raw):
    """None, never 0.0 — the distinction decides who is in the universe.

    A zero market cap is a legitimate sort key: it puts the issue below every
    real company. So reading "we could not parse this" as zero does not raise,
    does not look wrong, and quietly drops the issue out of the top-N while
    keeping it in the ranking — which is exactly the shape of bug that costs a
    name its place in the cross-section.
    """
    assert KU.parse_number(raw) is None


# ---------------------------------------------------------------- parsing

def test_a_payload_without_a_rows_key_is_an_error_not_an_empty_market():
    issues, error = KU.parse_issues({"respMsg": "Unauthorized API Call"})
    assert issues == []
    assert error and "no rows key" in error


def test_an_empty_rows_list_is_a_closed_exchange_not_an_error():
    issues, error = KU.parse_issues(_payload([]))
    assert (issues, error) == ([], None)


def test_the_two_are_distinguishable_which_is_the_whole_point():
    """The collector branches on this: step forward, or stop the run.

    Reading a refused request as a holiday would walk the calendar forward
    seven days, find seven more refusals, and record the month as closed.
    """
    _, holiday = KU.parse_issues(_payload([]))
    _, refusal = KU.parse_issues({"respCode": "401"})
    assert holiday is None and refusal is not None


def test_duplicate_codes_are_taken_once():
    issues, error = KU.parse_issues(_payload([
        _row("005930", "100"), _row("005930", "999"), _row("000660", "50")]))
    assert error is None
    assert [i["code"] for i in issues] == ["005930", "000660"]
    assert issues[0]["marketCap"] == 100.0


def test_issue_fields_survive_the_parse():
    issues, _ = KU.parse_issues(_payload(
        [_row("005930", "1,000", name="삼성전자", shares="5,969,782,550")]))
    assert issues == [{"code": "005930", "name": "삼성전자",
                       "marketCap": 1000.0, "listedShares": 5969782550.0}]


# ---------------------------------------------------------------- dating

def test_the_snapshot_is_dated_by_the_session_krx_served():
    payload = _payload([_row("005930", "1", date="20130103")])
    assert KU.served_date(payload, "2013-01-01") == "2013-01-03"


def test_a_response_without_a_date_falls_back_to_what_was_asked():
    payload = _payload([{"ISU_CD": "005930", "MKTCAP": "1"}])
    assert KU.served_date(payload, "2013-01-02") == "2013-01-02"


# ---------------------------------------------------------------- ranking

def test_issues_rank_by_market_cap_descending():
    ranked = KU.rank_issues([
        {"code": "b", "marketCap": 10.0},
        {"code": "a", "marketCap": 30.0},
        {"code": "c", "marketCap": 20.0}])
    assert [i["code"] for i in ranked] == ["a", "c", "b"]
    assert [i["rank"] for i in ranked] == [1, 2, 3]


def test_an_unreadable_cap_is_dropped_rather_than_ranked_last():
    ranked = KU.rank_issues([
        {"code": "big", "marketCap": 100.0},
        {"code": "unknown", "marketCap": None}])
    assert [i["code"] for i in ranked] == ["big"]


def test_ties_break_on_code_so_the_shard_is_byte_deterministic():
    """Two issues at the same cap must not swap places between runs.

    `write_shard` returns False when the bytes are unchanged, and the
    collector only commits what changed. An unstable tiebreak would rewrite
    the shard on every run and commit a decade of noise to `signal-history`.
    """
    first = KU.rank_issues([{"code": "zz", "marketCap": 5.0},
                            {"code": "aa", "marketCap": 5.0}])
    second = KU.rank_issues([{"code": "aa", "marketCap": 5.0},
                             {"code": "zz", "marketCap": 5.0}])
    assert [i["code"] for i in first] == [i["code"] for i in second] == ["aa", "zz"]


def test_top_caps_the_ranking_without_renumbering_it():
    ranked = KU.rank_issues(
        [{"code": f"{n:06d}", "marketCap": float(100 - n)} for n in range(10)],
        top=3)
    assert [i["rank"] for i in ranked] == [1, 2, 3]
    assert len(ranked) == 3


# ---------------------------------------------------------------- rows

def test_rows_carry_the_pipeline_ticker_and_a_stable_id():
    rows = KU.snapshot_rows("2013-01-02", KU.rank_issues(
        [{"code": "005930", "name": "삼성전자", "marketCap": 1.0,
          "listedShares": 2.0}]))
    assert rows[0]["ticker"] == "005930.KS"
    assert rows[0]["id"] == "krx-universe:2013-01-02:005930"
    assert rows[0]["date"] == "2013-01-02" and rows[0]["region"] == "KR"


def test_every_code_gets_the_kospi_suffix_the_price_vendor_answers_to():
    assert KU.to_pipeline_ticker("005930") == "005930.KS"
    assert KU.to_pipeline_ticker("") == ""


# ---------------------------------------------------------------- membership

def _rows(date, ranked):
    """ranked: [(code, rank)] -> store rows."""
    return [{"date": date, "ticker": KU.to_pipeline_ticker(code),
             "code": code, "rank": rank} for code, rank in ranked]


def test_membership_is_the_top_n_by_market_cap():
    rows = _rows("2013-01-02", [("000001", 1), ("000002", 2), ("000003", 3)])
    assert KU.members_on_date(rows, 2) == {"000001.KS", "000002.KS"}


def test_a_configured_name_below_the_cut_is_still_a_member():
    """Otherwise the rule DELETES names from the live universe.

    `UniverseHistory.snapshot` drops any ticker its row says was delisted, so
    a configured name that ranks outside today's top-N — a preferred share, at
    a fraction of its common's cap — would be given a removal date and vanish
    from the cross-section the system actually trades. Shrinking the live
    universe is a second bias, not a survivorship fix.
    """
    rows = _rows("2013-01-02", [("000001", 1), ("000002", 2), ("000003", 3)])
    assert KU.members_on_date(rows, 2, ["000003.KS"]) == {
        "000001.KS", "000002.KS", "000003.KS"}


def test_a_configured_name_that_did_not_trade_is_not_readmitted():
    """The configured half can only vouch for a name KRX says was trading.

    Without this the rule would put a 2020 listing into the 2013
    cross-section — a look-ahead, which is the failure the previous Korean
    attempt was deleted for.
    """
    rows = _rows("2013-01-02", [("000001", 1)])
    assert KU.members_on_date(rows, 1, ["999999.KS"]) == {"000001.KS"}


def test_snapshots_group_by_date_oldest_first():
    rows = (_rows("2016-01-04", [("000001", 1), ("000009", 2)])
            + _rows("2013-01-02", [("000001", 1), ("000002", 2)]))
    snaps = KU.snapshots_from_rows(rows, 2)
    assert [d for d, _ in snaps] == ["2013-01-02", "2016-01-04"]
    assert snaps[0][1] == {"000001.KS", "000002.KS"}


def test_a_date_with_no_rows_produces_no_snapshot_rather_than_an_empty_one():
    """An empty snapshot delists the whole exchange for that date.

    `memberships_from_snapshots` reads absence from a snapshot as removal, so
    a month the collector never reached must produce no snapshot at all — not
    one holding nobody.
    """
    assert KU.snapshots_from_rows([], 10) == []


# ---------------------------------------------------------------- calendar

def test_monthly_targets_are_the_first_of_each_month_inclusive():
    dates = KU.month_starts("2013-01-01", "2013-04-15")
    assert dates == ["2013-01-01", "2013-02-01", "2013-03-01", "2013-04-01"]


def test_monthly_targets_cross_a_year_boundary():
    assert KU.month_starts("2013-11-05", "2014-02-01") == [
        "2013-11-01", "2013-12-01", "2014-01-01", "2014-02-01"]


def test_monthly_spacing_over_thirteen_years_is_a_bounded_number_of_calls():
    """The error bound on the delisted side IS the spacing, so it is stated.

    A month here against the seven the US constituent history reaches between
    commits — the same direction of error, smaller, and 165 calls rather than
    a quota problem.
    """
    dates = KU.month_starts("2013-01-01", "2026-09-14")
    assert len(dates) == 165


def test_weekly_targets_are_mondays_within_the_window():
    dates = KU.week_starts("2013-01-01", "2013-01-31")
    assert dates == ["2013-01-07", "2013-01-14", "2013-01-21", "2013-01-28"]


def test_an_unknown_frequency_is_refused_by_name():
    with pytest.raises(ValueError, match="unknown frequency"):
        KU.target_dates("2013-01-01", "2013-02-01", "fortnightly")
