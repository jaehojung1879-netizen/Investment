"""One generation, one universe — or the evidence quietly becomes two.

`alphaPercentile` is a rank WITHIN a date's cross-section, and selection puts
a floor on it. Restoring 219 names to the 2012-12-27 S&P 500 therefore changes
what every surviving name's 2013 record meant. The replay skips signals whose
id it already holds, so those old records would keep the ranks they were given
against a universe that no longer exists, sitting in the same generation as the
new ones and pooling into a single audit.

The failure has no error and no missing data. It reports a fuller universe, a
higher coverage and a lower survivorship risk, over a ledger that is half one
measurement and half another. So it is guarded here.
"""
from __future__ import annotations

import pytest

from pipeline import historical_store as HS
from pipeline import pit_data
from pipeline import provenance


GEN = "replay-test"


def _signal(ticker: str, date: str = "2015-01-30") -> dict:
    return {"id": f"{date}:{ticker}", "asOf": date, "ticker": ticker,
            "region": "US", "replayVersion": GEN}


def _seed(tmp_path, tickers=("AAA",)):
    HS.append_signals(tmp_path, [_signal(t) for t in tickers])
    return tmp_path


# --------------------------------------------------------------------------- #
# The guard
# --------------------------------------------------------------------------- #
def _sig(mode="pit-membership", **regions):
    return {"mode": mode, "regions": regions, "fingerprint": "irrelevant"}


def test_an_empty_generation_accepts_any_universe(tmp_path):
    """Nothing to contaminate: the first run defines the generation."""
    assert HS.universe_conflict(tmp_path, GEN, _sig(US=829)) is None


def test_extending_with_the_same_universe_is_allowed(tmp_path):
    _seed(tmp_path)
    HS.stamp_universe(tmp_path, GEN, _sig(US=829))

    assert HS.universe_conflict(tmp_path, GEN, _sig(US=829)) is None


def test_a_universe_that_grew_is_allowed(tmp_path):
    """The case that would have broken production on the second run.

    CI rebuilds the membership file every replay run and the index gains
    members every month. A guard keyed on the exact file contents would have
    refused the second run and every run after it — and a guard that has to be
    switched off to get any work done protects nothing.
    """
    _seed(tmp_path)
    HS.stamp_universe(tmp_path, GEN, _sig(US=829))

    assert HS.universe_conflict(tmp_path, GEN, _sig(US=834)) is None


def test_a_universe_that_shrank_is_refused(tmp_path):
    """The KR half comes from a live vendor call. A short day is not a refresh."""
    _seed(tmp_path)
    HS.stamp_universe(tmp_path, GEN, _sig(US=829, KR=2450))

    reason = HS.universe_conflict(tmp_path, GEN, _sig(US=829, KR=2100))

    assert reason is not None
    assert "KR" in reason and "REPLAY_VERSION" in reason


def test_losing_a_region_entirely_is_refused(tmp_path):
    """A US-only rebuild over a US+KR file empties the Korean cross-section."""
    _seed(tmp_path)
    HS.stamp_universe(tmp_path, GEN, _sig(US=829, KR=2450))

    reason = HS.universe_conflict(tmp_path, GEN, _sig(US=829))

    assert reason is not None
    assert "KR" in reason and "no longer has any" in reason


def test_a_new_region_gaining_coverage_is_allowed(tmp_path):
    """Korea gaining membership history does not invalidate the US records.

    Only the region that changed has its cross-section redefined, and a region
    going from no coverage to some is caught by the coverage measure, which
    reports it rather than pretending the file describes what it does not.
    """
    _seed(tmp_path)
    HS.stamp_universe(tmp_path, GEN, _sig(US=829))

    assert HS.universe_conflict(tmp_path, GEN, _sig(US=829, KR=2450)) is None


def test_switching_the_mode_is_refused(tmp_path):
    _seed(tmp_path)
    HS.stamp_universe(tmp_path, GEN, _sig(US=829))

    reason = HS.universe_conflict(tmp_path, GEN, _sig(mode="survivors-only"))

    assert reason is not None
    assert "survivors-only" in reason


def test_an_unstamped_generation_with_records_counts_as_survivors_only(tmp_path):
    """The case that actually happens: a ledger written before this stamp.

    Treating an absent stamp as "unknown, carry on" is what the guard exists to
    stop — every generation written before membership history existed resolved
    its names from today's list, whether or not it recorded that.
    """
    _seed(tmp_path)

    assert HS.universe_conflict(tmp_path, GEN, _sig(US=829)) is not None
    assert HS.universe_conflict(
        tmp_path, GEN, _sig(mode=pit_data.SURVIVORS_ONLY)) is None


def test_a_conflict_in_one_generation_does_not_block_another(tmp_path):
    HS.append_signals(tmp_path, [dict(_signal("AAA"), replayVersion="old-gen")])

    assert HS.universe_conflict(tmp_path, "old-gen", _sig(US=829)) is not None
    assert HS.universe_conflict(tmp_path, GEN, _sig(US=829)) is None


def test_an_unreadable_stamp_is_treated_as_absent_not_as_agreement(tmp_path):
    _seed(tmp_path)
    path = HS.universe_stamp_path(tmp_path, GEN)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")

    assert HS.universe_conflict(tmp_path, GEN, _sig(US=829)) is not None


def test_the_stamp_round_trips_with_its_detail(tmp_path):
    HS.stamp_universe(tmp_path, GEN, _sig(US=829),
                      source="data/universe-history.json")
    stamp = HS.read_universe_stamp(tmp_path, GEN)

    assert stamp["mode"] == "pit-membership"
    assert stamp["regions"] == {"US": 829}
    assert stamp["source"] == "data/universe-history.json"


def test_the_shipped_history_produces_an_enforceable_signature():
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "data" / "universe-history.json"
    if not path.exists():
        pytest.skip("membership file not built in this checkout")

    signature = pit_data.UniverseHistory.from_json(path).signature

    assert signature["mode"] == pit_data.PIT_MEMBERSHIP
    assert signature["regions"].get("US", 0) > 500


# --------------------------------------------------------------------------- #
# The fingerprint it guards on
# --------------------------------------------------------------------------- #
def test_the_fingerprint_is_stable_across_reads():
    rows = {"AA": {"listed": "2012-12-27", "delisted": "2016-11-01", "region": "US"}}
    assert (pit_data.UniverseHistory(rows).fingerprint
            == pit_data.UniverseHistory(dict(rows)).fingerprint)


def test_the_fingerprint_ignores_dict_ordering():
    a = {"AA": {"listed": "2012-12-27", "delisted": None, "region": "US"},
         "MSFT": {"listed": "2013-01-02", "delisted": None, "region": "US"}}
    b = {"MSFT": a["MSFT"], "AA": a["AA"]}

    assert (pit_data.UniverseHistory(a).fingerprint
            == pit_data.UniverseHistory(b).fingerprint)


def test_adding_a_name_changes_the_fingerprint():
    a = {"AA": {"listed": "2012-12-27", "delisted": None, "region": "US"}}
    b = dict(a, GHOST={"listed": "2013-01-02", "delisted": None, "region": "US"})

    assert (pit_data.UniverseHistory(a).fingerprint
            != pit_data.UniverseHistory(b).fingerprint)


def test_changing_a_delisting_date_changes_the_fingerprint():
    a = {"AA": {"listed": "2012-12-27", "delisted": "2016-11-01", "region": "US"}}
    b = {"AA": {"listed": "2012-12-27", "delisted": "2017-11-01", "region": "US"}}

    assert (pit_data.UniverseHistory(a).fingerprint
            != pit_data.UniverseHistory(b).fingerprint)


def test_an_unrelated_key_does_not_change_the_fingerprint():
    """It covers the universe DEFINITION, not whatever else the file carries.

    A fingerprint that moves on cosmetic file changes would force a needless
    generation bump, and a decade of evidence discarded for a formatting edit
    is its own kind of failure.
    """
    a = {"AA": {"listed": "2012-12-27", "delisted": None, "region": "US"}}
    b = {"AA": dict(a["AA"], name="Alcoa Inc", sector="Materials")}

    assert (pit_data.UniverseHistory(a).fingerprint
            == pit_data.UniverseHistory(b).fingerprint)


def test_no_membership_file_is_the_survivors_only_identity():
    assert (pit_data.UniverseHistory({}).fingerprint
            == pit_data.SURVIVORS_ONLY_FINGERPRINT)


# --------------------------------------------------------------------------- #
# The bump this shipped with
# --------------------------------------------------------------------------- #
def test_the_shipped_universe_is_not_survivors_only():
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "data" / "universe-history.json"
    if not path.exists():
        pytest.skip("membership file not built in this checkout")

    history = pit_data.UniverseHistory.from_json(path)
    assert history.fingerprint != pit_data.SURVIVORS_ONLY_FINGERPRINT


def test_the_replay_left_v4_behind():
    """The PIT universe must not be appended to the survivors-only ledger.

    If this ever reads replay-v4 again, the guard above will refuse the run —
    but the point is to not need the guard.
    """
    assert provenance.REPLAY_VERSION != "replay-v4"


def test_the_replay_module_and_provenance_agree():
    from pipeline import historical_replay as HR
    assert HR.REPLAY_VERSION == provenance.REPLAY_VERSION
    assert HR.FEATURE_VERSION == provenance.FEATURE_VERSION
    assert HR.DATA_VERSION == provenance.DATA_VERSION


def test_a_recomputed_signal_cannot_overwrite_the_record_on_disk(tmp_path):
    """Why the guard is not bypassable by --full.

    --full clears `existing_ids` so the replay computes every date instead of
    skipping. But `append_signals` skips an id already on disk, so those
    recomputed records are discarded as duplicates. --full therefore cannot
    rewrite the old records under a new universe — it can only hide the check
    that says they are stale. The one cure is a new generation.
    """
    first = dict(_signal("AAA"), alphaPercentile=91.0)
    HS.append_signals(tmp_path, [first])

    recomputed = dict(_signal("AAA"), alphaPercentile=54.0)
    appended, skipped = HS.append_signals(tmp_path, [recomputed])

    assert (appended, skipped) == (0, 1)
    rows = HS.load(tmp_path, HS.SIGNALS, GEN)
    assert [row["alphaPercentile"] for row in rows] == [91.0]
