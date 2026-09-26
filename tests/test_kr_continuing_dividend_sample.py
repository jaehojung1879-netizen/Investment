"""The continuing-name pool for KR dividend cross-validation is drawn
deterministically from real universe rows, never hand-picked."""
from __future__ import annotations

from pipeline import kr_continuing_dividend_sample as SAMPLE


def _row(date, ticker, rank, name):
    return {"date": date, "ticker": ticker, "rank": rank, "name": name}


# --------------------------------------------------------------------------- #
# is_likely_common_share
# --------------------------------------------------------------------------- #
def test_preferred_share_names_are_excluded():
    assert SAMPLE.is_likely_common_share("삼성전자") is True
    assert SAMPLE.is_likely_common_share("삼성전자우") is False
    assert SAMPLE.is_likely_common_share("현대차2우B") is False
    assert SAMPLE.is_likely_common_share("LG") is True


def test_a_missing_name_is_treated_as_common_rather_than_dropped_silently():
    assert SAMPLE.is_likely_common_share(None) is True


# --------------------------------------------------------------------------- #
# rank_persistence
# --------------------------------------------------------------------------- #
def test_rank_persistence_counts_days_inside_the_cutoff_only():
    rows = [
        _row("2020-01-01", "005930.KS", 1, "삼성전자"),
        _row("2020-01-02", "005930.KS", 1, "삼성전자"),
        _row("2020-01-01", "999999.KS", 150, "밖순위"),
    ]
    persistence = SAMPLE.rank_persistence(rows, top_rank=120)
    assert persistence["005930"]["days"] == 2
    assert "999999" not in persistence


def test_rank_value_decides_inclusion_never_row_position():
    # A sparse fixture where the only row present for a date has rank 200 --
    # must NOT be included just because it's the sole/first row that date.
    rows = [_row("2020-01-01", "000001.KS", 200, "밖순위")]
    persistence = SAMPLE.rank_persistence(rows, top_rank=120)
    assert persistence == {}


# --------------------------------------------------------------------------- #
# select_continuing_sample
# --------------------------------------------------------------------------- #
def test_terminated_codes_are_excluded_from_the_pool():
    rows = [
        _row("2020-01-01", "005930.KS", 1, "삼성전자"),
        _row("2020-01-01", "000030.KS", 2, "우리은행"),
    ]
    pool = SAMPLE.select_continuing_sample(rows, terminated_codes={"000030"})
    codes = {r["code"] for r in pool}
    assert "000030" not in codes
    assert "005930" in codes


def test_pool_is_ordered_most_persistent_first_then_by_code():
    rows = (
        [_row(f"2020-01-{d:02d}", "000001.KS", 1, "A") for d in range(1, 4)]
        + [_row(f"2020-01-{d:02d}", "000002.KS", 1, "B") for d in range(1, 6)]
    )
    pool = SAMPLE.select_continuing_sample(rows, terminated_codes=set(), sample_size=10)
    assert [r["code"] for r in pool] == ["000002", "000001"]


def test_pool_is_truncated_to_sample_size():
    rows = [_row("2020-01-01", f"{i:06d}.KS", 1, f"name{i}") for i in range(50)]
    pool = SAMPLE.select_continuing_sample(rows, terminated_codes=set(), sample_size=25)
    assert len(pool) == 25


def test_preferred_shares_never_enter_the_pool_even_when_highly_ranked():
    rows = [_row("2020-01-01", "005935.KS", 1, "삼성전자우")]
    pool = SAMPLE.select_continuing_sample(rows, terminated_codes=set())
    assert pool == []


def test_selection_is_reproducible_from_the_same_rows():
    rows = [_row("2020-01-01", "005930.KS", 1, "삼성전자"),
           _row("2020-01-01", "000660.KS", 2, "SK하이닉스")]
    first = SAMPLE.select_continuing_sample(rows, terminated_codes=set())
    second = SAMPLE.select_continuing_sample(rows, terminated_codes=set())
    assert first == second
