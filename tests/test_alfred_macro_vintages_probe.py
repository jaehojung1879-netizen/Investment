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
AS_OF = [START, "2018-01-01"]


def _dates(first, periods, freq="MS"):
    return [d.date().isoformat()
            for d in pd.date_range(first, periods=periods, freq=freq)]


def _vintages(first, periods=24, freq="MS"):
    return _dates(first, periods, freq)


# --------------------------------------------------------------------------- #
# The distinction the probe exists to make
#
# It turns on the FIRST VINTAGE DATE against the replay start, and on nothing
# else. Row counts, observation counts and series length all look healthy on a
# series whose vintages only begin in 2019 — and that series serves an empty
# column on a 2013 replay date while `pit_status` upgrades the panel to
# PIT_EXACT. A better label over a worse replay is the failure being caught.
# --------------------------------------------------------------------------- #
def test_vintages_reaching_back_before_the_replay_start_are_usable():
    summary = P.summarize_series(
        _vintages("2009-01-01"), {START: _dates("2009-01-01", 40)},
        _dates("2009-01-01", 200), start=START, as_of_dates=[START])
    assert summary["verdict"] == P.USABLE
    assert summary["reason"] is None
    assert summary["asOf"][0]["periodsServed"] > 0


def test_vintages_that_only_begin_later_are_truncated_not_usable():
    summary = P.summarize_series(
        _vintages("2019-01-01"), {START: []},
        _dates("2009-01-01", 200), start=START, as_of_dates=[START])
    assert summary["verdict"] == P.TRUNCATED
    assert summary["asOf"][0]["periodsServed"] == 0
    assert "blank this column" in summary["reason"]


def test_a_long_observed_history_does_not_rescue_a_late_first_vintage():
    # The exact shape measured on HY_Spread: 795 periods of observations, no
    # vintage before 2023. Counting periods would call this rich.
    summary = P.summarize_series(
        _vintages("2023-09-05"), {START: []},
        _dates("1997-01-01", 795), start=START, as_of_dates=[START])
    assert summary["verdict"] == P.TRUNCATED
    served = summary["asOf"][0]
    assert served["periodsInRevisedHistory"] > 0
    assert served["periodsServed"] == 0


def test_no_vintage_dates_at_all_is_reported_not_crashed_on():
    summary = P.summarize_series([], {}, [], start=START, as_of_dates=[START])
    assert summary["verdict"] == P.EMPTY
    assert summary["vintages"] == 0


def test_observations_after_the_as_of_date_are_not_counted_as_served():
    # A vintage snapshot can carry a period stamped later than the as-of date;
    # counting it would credit the column with a period it could not have had.
    summary = P.summarize_series(
        _vintages("2009-01-01"), {START: _dates("2012-01-01", 36)},
        _dates("2012-01-01", 36), start=START, as_of_dates=[START])
    assert summary["asOf"][0]["periodsServed"] == 13


def test_the_vintage_count_is_published_beside_the_verdict():
    summary = P.summarize_series(
        _vintages("2009-01-01", periods=57), {START: []}, [],
        start=START, as_of_dates=[START])
    assert summary["vintages"] == 57
    assert summary["firstVintage"] == "2009-01-01"


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


# --------------------------------------------------------------------------- #
# A refusal keeps its reason
#
# The first real run recorded six failures as "the ALFRED call did not return".
# The actual message named a hard vintage-date cap and the fix that follows from
# it; discarding it cost a whole run to rediscover. An absence is an answer and
# is recorded, here as everywhere else in this repo.
# --------------------------------------------------------------------------- #
def test_a_failed_series_blocks_the_panel_and_keeps_what_the_vendor_said():
    summaries = {"A": {"verdict": P.USABLE},
                 "B": {"verdict": P.FAILED,
                       "reason": "HTTP 400: exceeds the maximum number of "
                                 "vintage dates allowed for this file type (2000)"}}
    panel = P.panel_verdict(summaries)
    assert panel["pitExactReachable"] is False
    assert panel["blocking"] == ["B"]
    assert "2000" in summaries["B"]["reason"]


def test_a_failed_input_leaves_the_derived_column_failed_too():
    # Yield_Curve went FAILED on the first run only because both Treasuries
    # did; the derived column must not invent a verdict of its own.
    resolved = P.resolve_derived({"Treasury_10Y": {"verdict": P.FAILED},
                                  "Treasury_2Y": {"verdict": P.FAILED}})
    assert resolved["Yield_Curve"]["verdict"] == P.FAILED


# --------------------------------------------------------------------------- #
# "Never vintaged" is an answer, and a different one from "not measured"
#
# ALFRED replies "The series does not exist in ALFRED but may exist in FRED"
# for 10 of the 28 panel columns. That is categorically worse than TRUNCATED
# and must be told apart from it: a truncated series is served by a later
# replay start, and this one is served by no start date at all. Filed as
# FETCH_FAILED it would keep looking like something a retry could fix.
# --------------------------------------------------------------------------- #
def test_not_vintaged_is_ranked_worse_than_truncated():
    order = P.VERDICT_ORDER
    assert order.index(P.NOT_VINTAGED) > order.index(P.TRUNCATED)
    assert order.index(P.TRUNCATED) > order.index(P.USABLE)


def test_a_derived_column_inherits_never_vintaged_from_an_input():
    resolved = P.resolve_derived({"Treasury_10Y": {"verdict": P.USABLE},
                                  "Treasury_2Y": {"verdict": P.NOT_VINTAGED}})
    assert resolved["Yield_Curve"]["verdict"] == P.NOT_VINTAGED


def test_a_never_vintaged_column_blocks_the_panel():
    panel = P.panel_verdict({"A": {"verdict": P.USABLE},
                             "B": {"verdict": P.NOT_VINTAGED}})
    assert panel["pitExactReachable"] is False
    assert panel["blocking"] == ["B"]


# --------------------------------------------------------------------------- #
# A vintage that outruns today's series is a redefinition, not a good column
# --------------------------------------------------------------------------- #
def test_a_vintage_carrying_more_than_todays_series_is_flagged():
    # Observed on TGA (WTREGEN): 1,408 periods served to 2013 against 524 in
    # today's frame. Unflagged it reads as a healthy column; it means the id
    # was reused for a different definition, and a replay conditioning on it
    # would be using a series that no longer exists.
    summary = P.summarize_series(
        _vintages("2008-12-18"), {START: _dates("2005-01-01", 2000, freq="D")},
        _dates("2005-01-01", 60, freq="MS"), start=START, as_of_dates=[START])
    cell = summary["asOf"][0]
    assert cell["periodsServed"] > cell["periodsInRevisedHistory"]
    assert cell["redefinedUnderSameId"] is True
    assert "different" in cell["note"]


def test_a_normal_column_carries_no_redefinition_flag():
    summary = P.summarize_series(
        _vintages("2009-01-01"), {START: _dates("2009-01-01", 20)},
        _dates("2009-01-01", 200), start=START, as_of_dates=[START])
    assert "redefinedUnderSameId" not in summary["asOf"][0]
