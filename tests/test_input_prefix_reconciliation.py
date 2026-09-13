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
# Far past the settling window, so these cases exercise the refusal, not the
# tolerance — the tolerance gets its own tests below.
CUTOFF = "2026-09-10"


def test_a_name_the_vendor_did_not_serve_is_restored_not_refused():
    """The exact shape of run #55: one delisted name simply absent."""
    fresh = _rows("AAA", MARCH) + _rows("ZZZ", MARCH)
    restored, ignored, _ = RI.reconcile_prefix(
        "price/2015-03", SEALED, fresh, SEALED_TICKERS, cutoff=CUTOFF)
    assert restored == ["SIVB"]
    assert ignored == []


def test_a_name_that_was_never_sealed_cannot_write_a_published_month():
    fresh = SEALED + _rows("NEWCO", MARCH)
    restored, ignored, _ = RI.reconcile_prefix(
        "price/2015-03", SEALED, fresh, SEALED_TICKERS, cutoff=CUTOFF)
    assert ignored == ["NEWCO"]
    assert restored == []


def test_a_contradicted_value_still_conflicts():
    """The teeth of the seal: a sealed number coming back different."""
    fresh = _rows("AAA", MARCH) + _rows("SIVB", MARCH, close=101.0) + _rows("ZZZ", MARCH)
    with pytest.raises(RI.InputVersionConflict,
                       match=r"1 of 3 sealed tickers contradict"):
        RI.reconcile_prefix("price/2015-03", SEALED, fresh, SEALED_TICKERS, cutoff=CUTOFF)


def test_an_extra_session_for_a_sealed_name_conflicts():
    """Not an availability flip: the vendor revised that name's history."""
    fresh = (_rows("AAA", MARCH) + _rows("SIVB", MARCH + ["2015-03-04"])
             + _rows("ZZZ", MARCH))
    with pytest.raises(RI.InputVersionConflict,
                       match=r"SIVB gained 2015-03-04"):
        RI.reconcile_prefix("price/2015-03", SEALED, fresh, SEALED_TICKERS, cutoff=CUTOFF)


def test_a_new_dividend_on_a_sealed_name_conflicts():
    """corporate-events is sparse: a sealed name with no row is not 'missing'."""
    sealed = [{"date": "2015-03-02", "ticker": "AAA", "dividend": 0.5, "split": 1.0}]
    fresh = sealed + [{"date": "2015-03-05", "ticker": "SIVB",
                       "dividend": 0.2, "split": 1.0}]
    with pytest.raises(RI.InputVersionConflict, match="SIVB gained 2015-03-05"):
        RI.reconcile_prefix("corporate-events/2015-03", sealed, fresh,
                            SEALED_TICKERS, cutoff=CUTOFF)


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


# December is here so the fixture has sessions far enough behind the cutoff to
# exercise the refusal; January straddles it and exercises the splice.
SESSIONS = ["2019-12-02", "2019-12-03",
            "2020-01-02", "2020-01-03", "2020-01-06",
            "2020-01-07", "2020-01-08", "2020-01-09"]
JANUARY = [d for d in SESSIONS if d.startswith("2020-01")]


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
    assert [r["date"] for r in sealed if r["ticker"] == "A"] == JANUARY
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
    # A December session is weeks behind the cutoff, so this is the evidence
    # moving, not the vendor settling its own tape.
    with pytest.raises(RI.InputVersionConflict,
                       match=r"2 of 2 sealed tickers contradict"):
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


# --------------------------------------------------------------------------- #
# The report has to say how BIG the contradiction is
#
# Run #57 failed with "price/2026-09: HUBB contradicts the sealed prefix" and
# that sentence cannot be acted on: one ticker is a corporate action to look up,
# hundreds is the vendor revising recent bars and needs the opposite response.
# The message named the alphabetically first offender and stopped.
# --------------------------------------------------------------------------- #
def test_the_conflict_names_every_contradicting_ticker_and_the_scope():
    fresh = (_rows("AAA", MARCH, close=101.0) + _rows("SIVB", MARCH, close=101.0)
             + _rows("ZZZ", MARCH))
    with pytest.raises(RI.InputVersionConflict) as caught:
        RI.reconcile_prefix("price/2015-03", SEALED, fresh, SEALED_TICKERS, cutoff=CUTOFF)

    message = str(caught.value)
    assert "2 of 3 sealed tickers contradict" in message
    assert "AAA" in message and "SIVB" in message
    # ...and what actually moved, so the cause is diagnosable from the record.
    assert "2015-03-02 Close 100.0 -> 101.0" in message


def test_the_conflict_summarises_rather_than_listing_hundreds():
    many = [t for t in (f"T{i:03d}" for i in range(40))]
    sealed = [r for t in many for r in _rows(t, MARCH)]
    fresh = [r for t in many for r in _rows(t, MARCH, close=101.0)]
    with pytest.raises(RI.InputVersionConflict) as caught:
        RI.reconcile_prefix("price/2015-03", sealed, fresh, set(many), cutoff=CUTOFF)

    message = str(caught.value)
    assert "40 of 40 sealed tickers contradict" in message
    assert "(+35 more)" in message


@pytest.mark.parametrize("sealed_rows,fresh_rows,expected", [
    (_rows("A", MARCH), _rows("A", MARCH + ["2015-03-04"]), "gained 2015-03-04"),
    (_rows("A", MARCH + ["2015-03-04"]), _rows("A", MARCH), "lost 2015-03-04"),
    (_rows("A", MARCH), _rows("A", MARCH, close=1.0), "2015-03-02 Close 100.0 -> 1.0"),
])
def test_first_difference_names_the_session_and_the_field(sealed_rows, fresh_rows, expected):
    assert RI.first_difference(sealed_rows, fresh_rows) == expected


# --------------------------------------------------------------------------- #
# A vendor settling its own record is not the evidence changing
#
# Run #58, the first conflict to report scope:
#
#     price/2026-09: 2 of 749 sealed tickers contradict the sealed prefix:
#       HUBB 2026-09-10 Volume 569872.0 -> 570129.0;
#       UA   2026-09-10 Volume 2386964.3272054954 -> 2400827.9233997087
#
# Two of 749, one field, both on the cutoff date itself, no price moved: the
# consolidated tape folding in late and off-exchange prints. Against that, the
# failure the seal exists to catch moved every one of 567 names in JANUARY 2011.
# A basis change reaches the whole history; a revision sits at the tail.
# --------------------------------------------------------------------------- #
TAPE = [{"date": "2026-09-10", "ticker": "HUBB", "Close": 626.46, "Volume": 569872.0}]


def test_a_volume_settled_on_the_cutoff_date_is_kept_not_refused():
    fresh = [{**TAPE[0], "Volume": 570129.0}]
    restored, ignored, revised = RI.reconcile_prefix(
        "price/2026-09", TAPE, fresh, {"HUBB"}, cutoff="2026-09-10")

    assert revised == [("HUBB", "2026-09-10 Volume 569872.0 -> 570129.0")]
    assert restored == [] and ignored == []


def test_a_revision_deep_in_the_published_history_still_refuses():
    """January 2011 moving is the v9->v10 basis change, not a late print."""
    sealed = [{"date": "2011-01-03", "ticker": "SWK", "Close": 100.0}]
    fresh = [{"date": "2011-01-03", "ticker": "SWK", "Close": 100.86}]
    with pytest.raises(RI.InputVersionConflict, match="1 of 1 sealed tickers contradict"):
        RI.reconcile_prefix("price/2011-01", sealed, fresh, {"SWK"},
                            cutoff="2026-09-10")


def test_a_ticker_settling_recently_and_revised_deeply_still_refuses():
    """One old session is enough; the tolerance is not a per-ticker amnesty."""
    sealed = [{"date": "2026-06-01", "ticker": "X", "Close": 10.0},
              {"date": "2026-09-10", "ticker": "X", "Close": 11.0, "Volume": 5.0}]
    fresh = [{"date": "2026-06-01", "ticker": "X", "Close": 10.5},
             {"date": "2026-09-10", "ticker": "X", "Close": 11.0, "Volume": 6.0}]
    with pytest.raises(RI.InputVersionConflict, match="contradict"):
        RI.reconcile_prefix("price/2026", sealed, fresh, {"X"}, cutoff="2026-09-10")


@pytest.mark.parametrize("date,settling", [
    ("2026-09-10", True),    # the cutoff itself — run #58's case
    ("2026-09-05", True),    # the far edge of the window
    ("2026-09-04", False),   # one day past it
    ("2011-01-03", False),   # the v9 -> v10 basis change
])
def test_the_settling_window_is_anchored_on_the_sealed_cutoff(date, settling):
    assert RI._settling(date, "2026-09-10") is settling


def test_a_session_after_the_cutoff_is_not_settling():
    """Only the sealed prefix is at stake; the suffix is fetched fresh anyway."""
    assert RI._settling("2026-09-11", "2026-09-10") is False


def test_the_sealed_row_is_what_survives_a_settled_revision(tmp_path):
    """End to end: the run continues, and on the POINT-IN-TIME value."""
    store = RI.InputStore(tmp_path, "r", "d")
    store.commit(_pack(["A", "SIVB"], "2020-01-06"), through="2020-01-06", policy={})
    sealed_before = store.load()["price/2020-01"]

    revised = _pack(["A", "SIVB"], "2020-01-09")
    for row in revised["price/2020-01"]:
        if row["date"] == "2020-01-06":
            row["Close"] = row["Close"] + 1.0        # settled on the cutoff
    store.commit(revised, through="2020-01-09", policy={})

    after = store.load()["price/2020-01"]
    kept = {(r["ticker"], r["date"]): r["Close"] for r in after}
    for row in sealed_before:
        assert kept[(row["ticker"], row["date"])] == row["Close"]
    assert len(store.reconciliation["revised"]) == 2
