"""A recovery percentage that hides WHEN the names left says almost nothing.

The first real run reported "former members with price history US: 130/326
(39.9%)". Whether that helped depends entirely on which 130. The 2013
cross-section needs 219 of the 326 departed names and the 2023 one needs 71,
so a vendor that serves only recent delistings can report 40% while leaving
the early years — where the bias is largest — untouched.

So the split by the year a name left is measured, printed, and written into
the diagnostics rather than left in a log line that scrolls away.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.run_replay import former_member_recovery  # noqa: E402


def _members(**rows):
    return {t: {"listed": None, "delisted": d, "region": "US"}
            for t, d in rows.items()}


def test_recovery_is_split_by_the_year_the_name_left():
    recovery = former_member_recovery(
        {"US": ["OLD_A", "OLD_B", "NEW_A", "NEW_B"]},
        prices={"NEW_A": object(), "NEW_B": object()},
        memberships=_members(OLD_A="2013-06-01", OLD_B="2014-06-01",
                             NEW_A="2024-06-01", NEW_B="2025-06-01"))

    row = recovery["US"]
    assert row["priced"] == 2 and row["pricedPct"] == 50.0
    # The headline says half. The split says the half that matters is missing.
    assert row["byYearLeft"]["2013"] == {"priced": 0, "described": 1}
    assert row["byYearLeft"]["2014"] == {"priced": 0, "described": 1}
    assert row["byYearLeft"]["2024"] == {"priced": 1, "described": 1}


def test_full_recovery_in_the_early_years_reads_differently():
    """Same headline number, opposite conclusion."""
    recovery = former_member_recovery(
        {"US": ["OLD_A", "OLD_B", "NEW_A", "NEW_B"]},
        prices={"OLD_A": object(), "OLD_B": object()},
        memberships=_members(OLD_A="2013-06-01", OLD_B="2014-06-01",
                             NEW_A="2024-06-01", NEW_B="2025-06-01"))

    row = recovery["US"]
    assert row["pricedPct"] == 50.0
    assert row["byYearLeft"]["2013"] == {"priced": 1, "described": 1}
    assert row["byYearLeft"]["2024"] == {"priced": 0, "described": 1}


def test_a_name_with_no_departure_date_is_counted_but_not_binned():
    """It is still a name the panel had to serve; it just has no year."""
    recovery = former_member_recovery(
        {"US": ["NO_DATE", "OLD_A"]},
        prices={"NO_DATE": object()},
        memberships={"NO_DATE": {"listed": None, "delisted": None, "region": "US"},
                     **_members(OLD_A="2013-06-01")})

    row = recovery["US"]
    assert row["describedFormerMembers"] == 2 and row["priced"] == 1
    assert set(row["byYearLeft"]) == {"2013"}


def test_a_region_with_nothing_to_restore_is_absent():
    assert former_member_recovery({"KR": []}, {}, {}) == {}
    assert former_member_recovery({}, {}, {}) == {}


def test_no_price_for_anything_reports_zero_not_an_error():
    recovery = former_member_recovery(
        {"US": ["OLD_A"]}, prices={}, memberships=_members(OLD_A="2013-06-01"))

    assert recovery["US"]["pricedPct"] == 0.0
    assert recovery["US"]["byYearLeft"]["2013"] == {"priced": 0, "described": 1}


def test_years_come_back_in_order():
    recovery = former_member_recovery(
        {"US": ["C", "A", "B"]}, prices={},
        memberships=_members(C="2020-01-01", A="2013-01-01", B="2016-01-01"))

    assert list(recovery["US"]["byYearLeft"]) == ["2013", "2016", "2020"]
