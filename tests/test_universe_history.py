"""Point-in-time index membership, and the ways it can go silently wrong.

The replay resolved its universe from TODAY's constituent list and applied it to
2013. Against the 2012-12-27 S&P 500 that drops 219 of 500 names — Alcoa,
Anadarko, Aetna, Allergan — which left the index mostly by being acquired or
shrinking out of it. Restoring them is the single largest available improvement
to the evidence, and it has two failure modes that produce no error at all:

  * a membership file that covers one region DELETES the other region, because
    "no row for this ticker" read as "not a member on this date";
  * coverage reported as 100% because a file merely exists, which turns on
    full-fidelity claims the data has not earned.

Both are tested here, because both would look like success.
"""
from __future__ import annotations

import json

import pytest

from pipeline import pit_data


class _Panel:
    """Stands in for the price panel: has_history decides tradability."""

    def __init__(self, tradable):
        self._tradable = set(tradable)

    def has_history(self, ticker, min_rows):
        return ticker in self._tradable


def _history(**rows):
    return pit_data.UniverseHistory(rows)


# --------------------------------------------------------------------------- #
# Membership by date
# --------------------------------------------------------------------------- #
def test_a_name_that_left_the_index_is_present_before_it_left():
    """The whole point: 2014 must see a name that was dropped in 2016."""
    history = _history(
        AA={"listed": "2012-12-27", "delisted": "2016-11-01", "region": "US"},
        MSFT={"listed": "2012-12-27", "delisted": None, "region": "US"})
    panel = _Panel(["AA", "MSFT"])

    early = history.snapshot("2014-06-02", {"US": ["MSFT"]}, view=panel)
    late = history.snapshot("2017-06-02", {"US": ["MSFT"]}, view=panel)

    assert "AA" in early.by_region["US"]     # restored, though absent from today
    assert "AA" not in late.by_region["US"]  # correctly gone after removal


def test_a_name_added_later_is_absent_from_earlier_dates():
    history = _history(
        NEW={"listed": "2020-03-02", "delisted": None, "region": "US"},
        MSFT={"listed": "2012-12-27", "delisted": None, "region": "US"})
    panel = _Panel(["NEW", "MSFT"])

    early = history.snapshot("2014-06-02", {"US": ["NEW", "MSFT"]}, view=panel)

    assert "NEW" not in early.by_region["US"]
    assert "MSFT" in early.by_region["US"]


def test_a_former_member_without_prices_cannot_be_restored():
    """Membership alone is not the fix; the price panel has to serve the name."""
    history = _history(
        AA={"listed": "2012-12-27", "delisted": "2016-11-01", "region": "US"},
        MSFT={"listed": "2012-12-27", "delisted": None, "region": "US"})

    snap = history.snapshot("2014-06-02", {"US": ["MSFT"]}, view=_Panel(["MSFT"]))

    assert snap.by_region["US"] == ["MSFT"]


# --------------------------------------------------------------------------- #
# The trap: a file that covers one region must not delete the other
# --------------------------------------------------------------------------- #
def test_a_us_only_file_does_not_empty_the_korean_universe():
    """`_listed_on` returning False for an unknown ticker erased whole regions.

    A US-only membership file would have left the KR sleeve as an empty list,
    and the replay would have carried on publishing a Korean book made of
    nothing.
    """
    history = _history(MSFT={"listed": "2012-12-27", "delisted": None, "region": "US"})
    panel = _Panel(["MSFT", "005930.KS"])

    snap = history.snapshot("2014-06-02",
                            {"US": ["MSFT"], "KR": ["005930.KS"]}, view=panel)

    assert snap.by_region["KR"] == ["005930.KS"]
    assert snap.membership_unknown == 1
    assert any("membership_unknown" in note for note in snap.notes)


def test_an_unknown_name_that_is_not_in_todays_list_is_still_excluded():
    """Keeping it would invent a membership the file never claimed."""
    history = _history(MSFT={"listed": "2012-12-27", "delisted": None, "region": "US"})

    snap = history.snapshot("2014-06-02", {"US": ["MSFT"]},
                            view=_Panel(["MSFT", "GHOST"]))

    assert "GHOST" not in snap.by_region["US"]


# --------------------------------------------------------------------------- #
# Coverage is measured, not asserted
# --------------------------------------------------------------------------- #
def test_coverage_reflects_the_share_actually_covered():
    history = _history(MSFT={"listed": "2012-12-27", "delisted": None, "region": "US"})
    panel = _Panel(["MSFT", "005930.KS"])

    snap = history.snapshot("2014-06-02",
                            {"US": ["MSFT"], "KR": ["005930.KS"]}, view=panel)

    assert snap.membership_known == 1
    assert snap.membership_coverage_pct == pytest.approx(50.0)
    # Half the cross-section unresolved is HIGH, not MEDIUM: the risk takes the
    # worse of the two gaps, and a 50% hole is far past the 5% MEDIUM band.
    assert snap.survivorship_risk == "HIGH"


def test_full_coverage_reports_low_risk():
    history = _history(
        MSFT={"listed": "2012-12-27", "delisted": None, "region": "US"},
        **{"005930.KS": {"listed": None, "delisted": None, "region": "KR"}})
    panel = _Panel(["MSFT", "005930.KS"])

    snap = history.snapshot("2014-06-02",
                            {"US": ["MSFT"], "KR": ["005930.KS"]}, view=panel)

    assert snap.membership_coverage_pct == 100.0
    assert snap.membership_unknown == 0
    assert snap.survivorship_risk == "LOW"


def test_a_null_listed_date_means_no_lower_bound_not_unknown():
    """KR rows carry listed=None: present throughout, and COUNTED as known."""
    history = _history(**{"005930.KS": {"listed": None, "delisted": None,
                                        "region": "KR"}})

    snap = history.snapshot("2014-06-02", {"KR": ["005930.KS"]},
                            view=_Panel(["005930.KS"]))

    assert snap.by_region["KR"] == ["005930.KS"]
    assert snap.membership_known == 1 and snap.membership_unknown == 0


def test_no_file_at_all_still_reports_the_survivorship_warning():
    snap = pit_data.UniverseHistory({}).snapshot(
        "2014-06-02", {"US": ["MSFT"]}, view=_Panel(["MSFT"]))

    assert snap.survivorship_risk == "HIGH"
    assert pit_data.SURVIVORSHIP_UNRESOLVED in snap.notes
    assert snap.membership_coverage_pct is None


# --------------------------------------------------------------------------- #
# The shipped file
# --------------------------------------------------------------------------- #
def test_the_committed_membership_file_loads_and_covers_the_replay_start():
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "data" / "universe-history.json"
    if not path.exists():
        pytest.skip("membership file not built in this checkout")

    history = pit_data.UniverseHistory.from_json(path)
    rows = history.memberships

    assert history.available
    departed = [t for t, r in rows.items()
                if r.get("region") == "US" and r.get("delisted")]
    assert len(departed) > 100, "a US file with no departures is survivors-only"

    # Every US row must be dated at or before the replay start, or the first
    # replay date would see an empty cross-section.
    listed = [r["listed"] for r in rows.values()
              if r.get("region") == "US" and r.get("listed")]
    assert min(listed) <= "2013-01-01"
