"""The sealed prefix survives a vendor that answers differently on a second run.

Run #55 of replay-v14 died with::

    ERROR: corporate-events/2015-03: published input prefix changed/recovered;
           new DATA_VERSION/REPLAY_VERSION required

Nothing in the code had changed since the run that sealed it. Yahoo answers
differently on different days for the same delisted ticker — measured across two
production acquisitions one hour apart, `constituentsWithoutPriceHistoryCount`
moved 286 -> 282, four of the 326 former index members flipping with no code
change between the runs. A ticker that vanishes takes its whole decade out of
every monthly shard, so the byte-exact check refuses.

The check was right that the bytes moved and wrong about what it meant: no
published NUMBER moved. Left alone it is the v7-v10 disease in a new form,
because acquisition is how new replay dates enter a generation — the evidence
base would be frozen at its first cutoff forever.

These pin the three outcomes that matter: a missing name is restored, a
never-sealed name cannot write history, and a CONTRADICTED value still stops
the run.
"""
from __future__ import annotations

import pytest

from pipeline import replay_inputs as RI


def _rows(ticker, dates, close=100.0):
    return [{"date": d, "ticker": ticker, "Close": close} for d in dates]


MARCH = ["2015-03-02", "2015-03-03"]
SEALED = _rows("AAA", MARCH) + _rows("SIVB", MARCH) + _rows("ZZZ", MARCH)
SEALED_TICKERS = {"AAA", "SIVB", "ZZZ"}


def test_a_name_the_vendor_did_not_serve_is_restored_not_refused():
    """The exact shape of run #55: one delisted name simply absent."""
    fresh = _rows("AAA", MARCH) + _rows("ZZZ", MARCH)
    restored, ignored = RI.reconcile_prefix(
        "price/2015-03", SEALED, fresh, SEALED_TICKERS)
    assert restored == ["SIVB"]
    assert ignored == []


def test_a_name_that_was_never_sealed_cannot_write_a_published_month():
    fresh = SEALED + _rows("NEWCO", MARCH)
    restored, ignored = RI.reconcile_prefix(
        "price/2015-03", SEALED, fresh, SEALED_TICKERS)
    assert ignored == ["NEWCO"]
    assert restored == []


def test_a_contradicted_value_still_conflicts():
    """The teeth of the seal: a sealed number coming back different."""
    fresh = _rows("AAA", MARCH) + _rows("SIVB", MARCH, close=101.0) + _rows("ZZZ", MARCH)
    with pytest.raises(RI.InputVersionConflict, match="SIVB contradicts"):
        RI.reconcile_prefix("price/2015-03", SEALED, fresh, SEALED_TICKERS)


def test_an_extra_session_for_a_sealed_name_conflicts():
    """Not an availability flip: the vendor revised that name's history."""
    fresh = (_rows("AAA", MARCH) + _rows("SIVB", MARCH + ["2015-03-04"])
             + _rows("ZZZ", MARCH))
    with pytest.raises(RI.InputVersionConflict, match="SIVB contradicts"):
        RI.reconcile_prefix("price/2015-03", SEALED, fresh, SEALED_TICKERS)


def test_a_new_dividend_on_a_sealed_name_conflicts():
    """corporate-events is sparse: a sealed name with no row is not 'missing'."""
    sealed = [{"date": "2015-03-02", "ticker": "AAA", "dividend": 0.5, "split": 1.0}]
    fresh = sealed + [{"date": "2015-03-05", "ticker": "SIVB",
                       "dividend": 0.2, "split": 1.0}]
    with pytest.raises(RI.InputVersionConflict, match="SIVB contradicts"):
        RI.reconcile_prefix("corporate-events/2015-03", sealed, fresh,
                            SEALED_TICKERS)


@pytest.mark.parametrize("name,reconcilable", [
    ("price/2015-03", True), ("benchmark/2015-03", True),
    ("corporate-events/2015-03", True),
    # Frozen whole: a change in any of these is a change of policy, not of
    # which names a vendor felt like serving.
    ("macro", False), ("fx/USD_KRW", False), ("calendar", False),
    ("price/source", False), ("benchmark/source", False),
    ("corporate-events/source", False), ("universe", False),
])
def test_only_dated_ticker_panels_are_reconcilable(name, reconcilable):
    assert RI.is_reconcilable(name) is reconcilable


# --------------------------------------------------------------------------- #
# End to end through InputStore.commit
# --------------------------------------------------------------------------- #
import pandas as pd
from pipeline import pit_data


SESSIONS = ["2020-01-02", "2020-01-03", "2020-01-06",
            "2020-01-07", "2020-01-08", "2020-01-09"]


def _panel(tickers, through, bump=0.0):
    frames = {}
    for offset, ticker in enumerate(tickers):
        dates = [d for d in SESSIONS if d <= through]
        series = pd.Series([100.0 + offset * 10 + i + bump
                            for i in range(len(dates))],
                           index=pd.to_datetime(dates), dtype=float)
        frames[ticker] = series.to_frame("Close")
    return frames


# The download list comes from point-in-time index membership, never from which
# names the vendor happened to serve, so it is held fixed across these runs.
UNIVERSE = ["A", "SIVB", "LATE"]


def _pack(tickers, through, bump=0.0, universe=None):
    return RI.pack(prices=_panel(tickers, through, bump), benchmarks={},
                   universe={"US": list(universe or UNIVERSE)},
                   universe_history=pit_data.UniverseHistory({}),
                   fundamentals=pit_data.FundamentalStore(), macro=None,
                   vix=None, vintages={}, fx=None,
                   rates={"events": [], "verifiedThrough": through},
                   through=through, calendar_rows=[])


def test_a_second_acquisition_missing_a_name_extends_instead_of_refusing(tmp_path):
    """Run #55's exact failure, end to end: it must now seal and move on."""
    store = RI.InputStore(tmp_path, "r", "d")
    store.commit(_pack(["A", "SIVB"], "2020-01-06"),
                 through="2020-01-06", policy={})
    # The vendor drops SIVB entirely on the next run, as Yahoo does.
    store.commit(_pack(["A"], "2020-01-09"), through="2020-01-09", policy={})

    sealed = store.load()["price/2020-01"]
    kept = [r for r in sealed if r["ticker"] == "SIVB"]
    assert [r["date"] for r in kept] == ["2020-01-02", "2020-01-03", "2020-01-06"]
    # ...and the name that WAS served carried the generation forward.
    assert [r["date"] for r in sealed if r["ticker"] == "A"] == SESSIONS
    assert store.reconciliation["restored"] == {"SIVB"}


def test_the_spliced_month_keeps_the_order_pack_would_have_produced(tmp_path):
    """January straddles the cutoff, so sealed rows and fresh rows share a shard.

    If the splice returned them prefix-block-then-suffix-block, the NEXT run's
    byte-exact check would fail on ordering alone and the seal would be right
    back where it started.
    """
    store = RI.InputStore(tmp_path, "r", "d")
    store.commit(_pack(["A", "SIVB"], "2020-01-06"),
                 through="2020-01-06", policy={})
    store.commit(_pack(["A"], "2020-01-09"), through="2020-01-09", policy={})

    sealed = store.load()["price/2020-01"]
    assert sealed == sorted(sealed, key=lambda r: (r["ticker"], r["date"]))
    # The splice sorts by (ticker, date) on the assumption that this is the
    # order pack itself emits. Pin the assumption against pack directly, or the
    # splice is only consistent with itself.
    emitted = _pack(["A", "SIVB"], "2020-01-06")["price/2020-01"]
    assert emitted == sorted(emitted, key=lambda r: (r["ticker"], r["date"]))
    # And a repeat run on the same cutoff changes nothing.
    store.commit(_pack(["A"], "2020-01-09"), through="2020-01-09", policy={})
    assert store.load()["price/2020-01"] == sealed


def test_a_name_returning_with_different_numbers_still_stops_the_run(tmp_path):
    store = RI.InputStore(tmp_path, "r", "d")
    store.commit(_pack(["A", "SIVB"], "2020-01-06"),
                 through="2020-01-06", policy={})
    with pytest.raises(RI.InputVersionConflict, match="contradicts the sealed prefix"):
        store.commit(_pack(["A", "SIVB"], "2020-01-09", bump=5.0),
                     through="2020-01-09", policy={})


def test_a_name_absent_from_the_seal_does_not_enter_a_published_month(tmp_path):
    store = RI.InputStore(tmp_path, "r", "d")
    store.commit(_pack(["A"], "2020-01-06"), through="2020-01-06", policy={})
    store.commit(_pack(["A", "LATE"], "2020-01-09"),
                 through="2020-01-09", policy={})

    sealed = store.load()["price/2020-01"]
    late = [r["date"] for r in sealed if r["ticker"] == "LATE"]
    # It may join at the frontier, but it may not write the published past.
    assert late == ["2020-01-07", "2020-01-08", "2020-01-09"]
    assert store.reconciliation["ignored"] == {"LATE"}


def test_a_static_component_is_still_frozen_whole(tmp_path):
    """Reconciliation is for vendor availability, never for policy drift."""
    store = RI.InputStore(tmp_path, "r", "d")
    first = _pack(["A"], "2020-01-06")
    store.commit(first, through="2020-01-06", policy={})
    with pytest.raises(RI.InputVersionConflict, match="universe: published input prefix"):
        store.commit(_pack(["A"], "2020-01-09", universe=["A", "B"]),
                     through="2020-01-09", policy={})
