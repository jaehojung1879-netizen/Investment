"""Candidate eligibility under open proposals: the committed report and the ex-date invariance rule. No outcome."""
import json

import pandas as pd

from . import kr22_candidate_eligibility as C

REPORT = json.loads(C.REPORT.read_text())


def test_frozen_gates_are_reported_unchanged_and_nothing_is_adopted():
    s = REPORT["summary"]
    assert REPORT["frozenGatesChanged"] is False and REPORT["historicalOutcomesRead"] == 0 and REPORT["pricesRead"] == 0
    assert s["industryEligible"]["frozen"] == 0 and s["totalReturnLabelEligible"]["frozen"] == 0 and s["exDate"]["frozen"] == 0
    assert s["eligibleMemberMonths"]["frozen"] == {"H126": 0, "H252": 0}
    assert s["terminalEconomicsComplete"]["frozen"] == 5


def test_candidate_counts_follow_from_the_rows():
    s, rows = REPORT["summary"], REPORT["securities"]
    assert s["terminalEconomicsComplete"]["candidateT"] == sum(r["terminalEconomicsComplete"]["candidateT"] for r in rows)
    assert s["totalReturnLabelEligible"]["securities"]["A_E"] == ["012510.KS"]
    assert all(r["terminalEconomicsComplete"]["candidateT"] for r in rows if r["terminalEconomicsComplete"]["frozen"])


def _days():
    return pd.DatetimeIndex(pd.bdate_range("2020-01-01", "2020-03-31"))


def test_a_record_date_at_the_entry_boundary_is_ambiguous_and_one_inside_is_not():
    days = _days()
    entry, exit_ = days[10], days[40]
    # Record session = entry + 1: the ex-date may be entry+1 (included) or entry/entry-1 (excluded).
    assert C.ex_date_invariance([str(days[11].date())], [(entry, exit_)], days) == 1
    # Well inside the window every candidate is included.
    assert C.ex_date_invariance([str(days[25].date())], [(entry, exit_)], days) == 0
    # Exit boundary: record two sessions after exit makes the candidate set straddle it.
    assert C.ex_date_invariance([str(days[42].date())], [(entry, exit_)], days) == 1


def test_ex_date_candidates_are_the_record_session_and_two_before():
    days = _days()
    assert C.ex_date_candidates("2020-01-18", days) == [days[12], days[11], days[10]]  # a Saturday maps to Friday
