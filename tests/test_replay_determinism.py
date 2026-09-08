"""The guard that would have caught two runs publishing different scorecards.

On 2026-09-05 the replay ran twice from commit 38a4951 over the same 714
dates. Challenger CAGR came out 19.47% and then 16.77%; max drawdown -13.35%
and then -9.85%; the paired difference -0.702%p and then -0.530%p. Diffing the
ledger commits: no existing row changed, 250 rows were ADDED across 60 monthly
files from 2013-01 to 2018-03, and three delisted US tickers accounted for all
of them (HAR 215, MHP 23, BMC 12). Of 104 rolling evaluation points, 29
survived.

Nothing in either report said they disagreed. These tests pin the checks that
now would.
"""
from __future__ import annotations

from pipeline import replay_determinism as D


def _sig(date, ticker):
    return {"date": date, "ticker": ticker}


def _sched(*pairs):
    return [{"date": d, "endDate": e} for d, e in pairs]


# --------------------------------------------------------------------------- #
# Growing is normal. Only the already-published past is under test.
# --------------------------------------------------------------------------- #
def test_appending_blocks_after_the_recorded_end_is_not_a_divergence():
    recorded = _sched(("2013-11-15", "2013-12-16"), ("2013-12-16", "2014-01-17"))
    current = recorded + _sched(("2014-01-17", "2014-02-18"))
    result = D.compare_schedule(recorded, current)
    assert result["verdict"] == D.EXTENDED
    assert result["appendedBlocks"] == 1


def test_an_unchanged_schedule_is_stable_not_extended():
    recorded = _sched(("2013-11-15", "2013-12-16"))
    assert D.compare_schedule(recorded, list(recorded))["verdict"] == D.STABLE


def test_the_first_run_has_no_baseline_and_does_not_fail():
    assert D.compare_schedule(None, _sched(("2013-11-15", "2013-12-16")))[
        "verdict"] == D.NO_BASELINE


# --------------------------------------------------------------------------- #
# A moved end date is the whole failure mode
#
# shared_block_dates anchors each block on the previous block's END, and takes
# the LATER of the two selectors' ends. So an end can move while the entry date
# does not — and every later block shifts. A fingerprint of entry dates alone
# would call that stable, which is exactly the report we already shipped.
# --------------------------------------------------------------------------- #
def test_a_block_whose_end_date_moved_is_a_divergence_even_with_the_same_entry():
    recorded = _sched(("2013-11-15", "2013-12-16"), ("2013-12-16", "2014-01-17"))
    current = _sched(("2013-11-15", "2013-12-17"), ("2013-12-16", "2014-01-17"))
    result = D.compare_schedule(recorded, current)
    assert result["verdict"] == D.DIVERGED
    assert result["firstDivergenceIndex"] == 0


def test_a_block_dropped_from_the_published_span_is_a_divergence():
    recorded = _sched(("2013-11-15", "2013-12-16"), ("2013-12-16", "2014-01-17"))
    current = _sched(("2013-11-15", "2013-12-16"))
    assert D.compare_schedule(recorded, current)["verdict"] == D.DIVERGED


def test_a_block_inserted_inside_the_published_span_is_a_divergence():
    recorded = _sched(("2013-11-15", "2013-12-16"), ("2014-01-17", "2014-02-18"))
    current = _sched(("2013-11-15", "2013-12-16"),
                     ("2013-12-20", "2014-01-21"),
                     ("2014-01-17", "2014-02-18"))
    result = D.compare_schedule(recorded, current)
    assert result["verdict"] == D.DIVERGED


# --------------------------------------------------------------------------- #
# The upstream cause: who was in the cross-section on a past date
# --------------------------------------------------------------------------- #
def test_a_delisted_name_appearing_in_a_past_cross_section_is_caught():
    # The measured 2026-09-05 failure, in miniature: HAR was absent from the
    # 2017-06 cross-section in one run and present in the next.
    before = D.cross_section_fingerprint(
        [_sig("2017-06-02", "AAPL"), _sig("2017-06-02", "MSFT")])
    after = D.cross_section_fingerprint(
        [_sig("2017-06-02", "AAPL"), _sig("2017-06-02", "MSFT"),
         _sig("2017-06-02", "HAR")])
    result = D.compare_cross_sections(before, after)
    assert result["verdict"] == D.DIVERGED
    assert result["driftedDates"] == 1
    assert result["netNameChange"] == 1
    assert result["firstDriftedDate"] == "2017-06-02"


def test_a_name_disappearing_from_a_past_cross_section_is_caught_too():
    before = D.cross_section_fingerprint(
        [_sig("2017-06-02", "AAPL"), _sig("2017-06-02", "HAR")])
    after = D.cross_section_fingerprint([_sig("2017-06-02", "AAPL")])
    result = D.compare_cross_sections(before, after)
    assert result["verdict"] == D.DIVERGED
    assert result["netNameChange"] == -1


def test_a_wholly_new_date_inside_the_published_span_is_a_divergence():
    before = D.cross_section_fingerprint(
        [_sig("2017-06-02", "AAPL"), _sig("2017-06-16", "AAPL")])
    after = D.cross_section_fingerprint(
        [_sig("2017-06-02", "AAPL"), _sig("2017-06-09", "AAPL"),
         _sig("2017-06-16", "AAPL")])
    assert D.compare_cross_sections(before, after)["verdict"] == D.DIVERGED


def test_new_dates_after_the_recorded_end_are_an_extension_not_a_divergence():
    before = D.cross_section_fingerprint([_sig("2017-06-02", "AAPL")])
    after = D.cross_section_fingerprint(
        [_sig("2017-06-02", "AAPL"), _sig("2017-06-09", "AAPL")])
    result = D.compare_cross_sections(before, after)
    assert result["verdict"] == D.EXTENDED
    assert result["appendedDates"] == 1


def test_the_same_names_in_a_different_order_are_the_same_cross_section():
    a = D.cross_section_fingerprint([_sig("2017-06-02", "AAPL"),
                                     _sig("2017-06-02", "MSFT")])
    b = D.cross_section_fingerprint([_sig("2017-06-02", "MSFT"),
                                     _sig("2017-06-02", "AAPL")])
    assert D.compare_cross_sections(a, b)["verdict"] == D.STABLE


# --------------------------------------------------------------------------- #
# assess(): what the report carries, and what blocks it
# --------------------------------------------------------------------------- #
def _previous(schedule, cross, version="replay-v6"):
    return {"replayDeterminism": {"replayVersion": version,
                                  "schedule": schedule, "crossSection": cross}}


def test_a_diverged_run_is_reported_as_not_reproducible():
    sched = _sched(("2013-11-15", "2013-12-16"))
    cross = D.cross_section_fingerprint([_sig("2013-11-15", "AAPL")])
    moved = _sched(("2013-11-15", "2013-12-17"))
    block = D.assess(_previous(sched, cross), schedule=moved,
                     cross_section=cross, replay_version="replay-v6")
    assert block["verdict"] == D.DIVERGED
    assert block["reproducible"] is False


def test_a_clean_extension_stays_reproducible():
    sched = _sched(("2013-11-15", "2013-12-16"))
    cross = D.cross_section_fingerprint([_sig("2013-11-15", "AAPL")])
    grown = sched + _sched(("2013-12-16", "2014-01-17"))
    block = D.assess(_previous(sched, cross), schedule=grown,
                     cross_section=cross, replay_version="replay-v6")
    assert block["verdict"] == D.EXTENDED
    assert block["reproducible"] is True


def test_a_replay_version_bump_is_a_new_experiment_not_a_divergence():
    # v7 is allowed to disagree with v6 about everything. Holding a new
    # generation to the old one's calendar would fail every version bump.
    sched = _sched(("2013-11-15", "2013-12-16"))
    cross = D.cross_section_fingerprint([_sig("2013-11-15", "AAPL")])
    block = D.assess(_previous(sched, cross, version="replay-v6"),
                     schedule=_sched(("2013-11-20", "2013-12-20")),
                     cross_section=D.cross_section_fingerprint(
                         [_sig("2013-11-20", "AAPL")]),
                     replay_version="replay-v7")
    assert block["verdict"] == D.VERSION_CHANGED
    assert block["reproducible"] is True
    assert block["previousReplayVersion"] == "replay-v6"


def test_the_first_ever_run_is_reproducible_with_no_baseline():
    block = D.assess(None, schedule=_sched(("2013-11-15", "2013-12-16")),
                     cross_section={}, replay_version="replay-v6")
    assert block["verdict"] == D.NO_BASELINE
    assert block["reproducible"] is True


def test_the_block_carries_the_fingerprint_forward_for_the_next_run():
    # Without this the next run has nothing to compare against, which is the
    # state that let two disagreeing scorecards both publish.
    sched = _sched(("2013-11-15", "2013-12-16"))
    cross = D.cross_section_fingerprint([_sig("2013-11-15", "AAPL")])
    block = D.assess(None, schedule=sched, cross_section=cross,
                     replay_version="replay-v6")
    assert block["schedule"] == sched
    assert block["crossSection"] == cross
    assert D.assess(_previous(block["schedule"], block["crossSection"]),
                    schedule=sched, cross_section=cross,
                    replay_version="replay-v6")["verdict"] == D.STABLE


# --------------------------------------------------------------------------- #
# The shared schedule must expose end dates, or the guard checks half the thing
# --------------------------------------------------------------------------- #
def test_shared_block_schedule_ignores_actual_ends_of_both_selectors():
    from pipeline import portfolio_validation as PV
    rows = {
        "champion": [{"date": "2013-11-15", "endDate": "2013-12-16"}],
        "challenger": [{"date": "2013-11-15", "endDate": "2013-12-18"}],
    }
    schedule = PV.shared_block_schedule(rows, 21)
    rows["challenger"][0]["endDate"] = "2014-06-30"
    assert schedule == PV.shared_block_schedule(rows, 21)
    assert schedule[0]["date"] == "2013-01-07"


def test_shared_block_schedule_agrees_with_shared_block_dates():
    from pipeline import portfolio_validation as PV
    rows = {
        "champion": [{"date": "2013-11-15", "endDate": "2013-12-16"},
                     {"date": "2013-12-16", "endDate": "2014-01-17"},
                     {"date": "2013-11-20", "endDate": "2013-12-20"}],
        "challenger": [{"date": "2013-11-15", "endDate": "2013-12-16"},
                       {"date": "2013-12-16", "endDate": "2014-01-17"},
                       {"date": "2013-11-20", "endDate": "2013-12-20"}],
    }
    dates = PV.shared_block_dates(rows, 21)
    assert [row["date"] for row in PV.shared_block_schedule(rows, 21)] == dates


def test_shared_block_schedule_exists_when_selectors_share_no_measurable_dates():
    from pipeline import portfolio_validation as PV
    rows = {"champion": [{"date": "2013-11-15", "endDate": "2013-12-16"}],
            "challenger": [{"date": "2014-01-02", "endDate": "2014-02-03"}]}
    assert PV.shared_block_schedule(rows, 21)
    assert PV.shared_block_schedule(rows, 21) == PV.shared_block_schedule({}, 21, through="2014-01-02")

