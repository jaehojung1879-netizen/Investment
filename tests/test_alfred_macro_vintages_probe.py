"""What the ALFRED probe's answer MEANS, pinned without a vendor.

The network half only runs in CI. What is pinned here is the judgement: that a
series whose release history begins after the replay start is called out as
TRUNCATED rather than counted as a win, because opting it in would blank that
column on the early replay dates while UPGRADING the panel's PIT label — a
worse replay wearing a better badge. Row counts cannot see that; only
reconstructing the column on the date can, so the probe reconstructs it with
the same `vintage_column` the replay uses.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
_spec = importlib.util.spec_from_file_location(
    "probe_alfred_macro_vintages", ROOT / "scripts" / "probe_alfred_macro_vintages.py")
P = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = P
_spec.loader.exec_module(P)

START = "2013-01-01"


def _releases(rows) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["date", "realtime_start", "value"])


def _monthly(first_period, first_print, periods=36, lag_days=30):
    """A well-behaved monthly series: each period printed `lag_days` later."""
    rows = []
    for i in range(periods):
        period = pd.Timestamp(first_period) + pd.DateOffset(months=i)
        published = max(period + pd.Timedelta(days=lag_days), pd.Timestamp(first_print))
        rows.append((period, published, 100.0 + i))
    return _releases(rows)


# --------------------------------------------------------------------------- #
# The distinction the probe exists to make
# --------------------------------------------------------------------------- #
def test_history_reaching_back_before_the_replay_start_is_usable():
    summary = P.summarize_releases(_monthly("2009-01-01", "2009-02-01"),
                                   start=START, as_of_dates=[START])
    assert summary["verdict"] == P.USABLE
    assert summary["periodsVisibleAtReplayStart"] > 0
    assert summary["asOf"][0]["periodsServed"] > 0


def test_history_that_only_begins_later_is_truncated_not_usable():
    # Every print appeared in 2019; on the 2013 replay start this column would
    # be entirely NaN while pit_status called the panel PIT_EXACT.
    summary = P.summarize_releases(_monthly("2019-01-01", "2019-02-01"),
                                   start=START, as_of_dates=[START])
    assert summary["verdict"] == P.TRUNCATED
    assert summary["asOf"][0]["periodsServed"] == 0
    assert "blank this column" in summary["reason"]


def test_the_truncated_case_is_visible_against_what_revised_history_would_show():
    summary = P.summarize_releases(_monthly("2009-01-01", "2019-06-01"),
                                   start=START, as_of_dates=[START])
    served = summary["asOf"][0]
    # Periods exist before the replay start; none of them had been PUBLISHED,
    # which is exactly the trade the verdict has to make visible.
    assert served["periodsInRevisedHistory"] > 0
    assert served["periodsServed"] == 0
    assert summary["verdict"] == P.TRUNCATED


def test_no_releases_at_all_is_reported_not_crashed_on():
    assert P.summarize_releases(None, start=START, as_of_dates=[START])["verdict"] == P.EMPTY
    assert P.summarize_releases(_releases([]), start=START,
                                as_of_dates=[START])["verdict"] == P.EMPTY


def test_rows_without_a_publication_date_do_not_count_as_history():
    summary = P.summarize_releases(
        _releases([("2010-01-01", None, 1.0), (None, "2010-02-01", 2.0)]),
        start=START, as_of_dates=[START])
    assert summary["verdict"] == P.EMPTY


def test_revision_count_separates_a_revised_series_from_a_never_revised_one():
    once = _releases([("2010-01-01", "2010-02-01", 1.0)])
    twice = _releases([("2010-01-01", "2010-02-01", 1.0),
                       ("2010-01-01", "2010-03-01", 1.4)])
    assert P.summarize_releases(once, start=START,
                                as_of_dates=[START])["periodsEverRevised"] == 0
    assert P.summarize_releases(twice, start=START,
                                as_of_dates=[START])["periodsEverRevised"] == 1


# --------------------------------------------------------------------------- #
# Derived columns — no series id, so ALFRED can never answer for them directly
# --------------------------------------------------------------------------- #
def test_a_derived_column_inherits_the_worse_of_its_inputs():
    resolved = P.resolve_derived({"Treasury_10Y": {"verdict": P.USABLE},
                                  "Treasury_2Y": {"verdict": P.TRUNCATED}})
    assert resolved["Yield_Curve"]["verdict"] == P.TRUNCATED


def test_a_derived_column_is_usable_only_when_every_input_is():
    resolved = P.resolve_derived({"Treasury_10Y": {"verdict": P.USABLE},
                                  "Treasury_2Y": {"verdict": P.USABLE}})
    assert resolved["Yield_Curve"]["verdict"] == P.USABLE


def test_an_unmeasured_input_leaves_the_derived_column_unresolved():
    resolved = P.resolve_derived({"Treasury_10Y": {"verdict": P.USABLE}})
    assert resolved["Yield_Curve"]["verdict"] == P.FAILED
    assert "not measured" in resolved["Yield_Curve"]["reason"]


# --------------------------------------------------------------------------- #
# The panel verdict is all-or-nothing, because PIT_EXACT is
# --------------------------------------------------------------------------- #
def test_one_blocking_column_holds_the_whole_panel_below_exact():
    panel = P.panel_verdict({"A": {"verdict": P.USABLE}, "B": {"verdict": P.USABLE},
                             "C": {"verdict": P.TRUNCATED}})
    assert panel["pitExactReachable"] is False
    assert panel["blocking"] == ["C"]
    assert panel["wouldBe"] == "PIT_APPROXIMATE"


def test_every_column_usable_is_the_only_way_to_pit_exact():
    panel = P.panel_verdict({"A": {"verdict": P.USABLE}, "B": {"verdict": P.USABLE}})
    assert panel["pitExactReachable"] is True
    assert panel["wouldBe"] == "PIT_EXACT"
