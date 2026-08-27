"""Leakage, PIT quality and replay-integrity tests.

These are the tests that decide whether the historical evidence is worth
anything. A replay that reads the future is not "slightly optimistic" — it is
void, and every downstream number built on it is void too. So the assertions
here are hard equalities and explicit exceptions, not tolerance bands.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from pipeline import entry as entry_mod
from pipeline import features as F
from pipeline import historical_outcomes as HO
from pipeline import historical_replay as HR
from pipeline import longterm as LT
from pipeline import pit_data


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
def _frame(seed: int, periods: int = 1400, start: str = "2015-01-01") -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.bdate_range(start, periods=periods)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.014, periods)))
    return pd.DataFrame({
        "Open": close * (1 + rng.normal(0, 0.003, periods)),
        "High": close * 1.01, "Low": close * 0.99, "Close": close,
        "Volume": rng.lognormal(14, 0.4, periods),
    }, index=index)


@pytest.fixture(scope="module")
def prices() -> dict:
    out = {f"T{i:02d}": _frame(100 + i) for i in range(12)}
    out["SPY"] = _frame(999)
    return out


@pytest.fixture(scope="module")
def universe(prices) -> dict:
    return {"US": [t for t in prices if t.startswith("T")]}


# --------------------------------------------------------------------------- #
# 1. Look-ahead: prices
# --------------------------------------------------------------------------- #
def test_price_view_refuses_dates_after_as_of(prices):
    view = pit_data.PriceView(prices, "2018-06-01")
    with pytest.raises(pit_data.LookAheadError):
        view.require("2018-06-02")
    series = view.close("T00")
    assert series.index.max() <= pd.Timestamp("2018-06-01")


def test_price_view_truncates_every_accessor(prices):
    cutoff = pd.Timestamp("2017-03-15")
    view = pit_data.PriceView(prices, cutoff)
    for ticker in ("T00", "T05", "SPY"):
        pit_data.assert_no_future(view.frame(ticker), cutoff, ticker)
        pit_data.assert_no_future(view.close(ticker), cutoff, ticker)


def test_assert_no_future_raises_on_a_future_observation():
    index = pd.bdate_range("2020-01-01", periods=10)
    series = pd.Series(range(10), index=index)
    with pytest.raises(pit_data.LookAheadError):
        pit_data.assert_no_future(series, "2020-01-05")


def test_replay_metrics_equal_truncate_then_recompute(prices):
    """The precomputed NumPy panel must equal the pandas production functions.

    This is the load-bearing test for the whole engine: the replay is fast only
    because features are computed from trailing windows over a full-history
    array instead of re-slicing per date. That is valid only if every metric is
    backward-looking, and this pins it.
    """
    panel = HR.PricePanel(prices)
    history = panel.get("T03")
    frame = prices["T03"]
    for as_of in ("2016-08-15", "2018-02-28", "2019-11-29"):
        stamp = pd.Timestamp(as_of)
        position = history.position(np.datetime64(stamp, "ns"))
        truncated = frame.loc[:stamp]["Close"]
        pairs = [
            (HR.momentum_12_1(history, position), LT.momentum_12_1(truncated)),
            (HR.momentum_6m(history, position), LT.momentum_6m(truncated)),
            (HR.realized_vol_252(history, position), LT.realized_vol_252(truncated)),
            (HR.downside_vol_252(history, position), LT.downside_vol_252(truncated)),
            (HR.cvar_95(history, position), LT.cvar_95(truncated)),
            (HR.max_drawdown_252(history, position), LT.max_drawdown_252(truncated)),
        ]
        for replayed, production in pairs:
            assert replayed == pytest.approx(production, abs=1e-9), as_of


def test_replay_entry_features_equal_production_entry_features(prices):
    panel = HR.PricePanel(prices)
    history = panel.get("T07")
    stamp = pd.Timestamp("2018-09-28")
    position = history.position(np.datetime64(stamp, "ns"))
    replayed = HR.entry_features(history, position, None)
    production = entry_mod.entry_features(F.build_features(prices["T07"].loc[:stamp]))
    for key, value in production.items():
        if key in {"volumeSurge", "earningsInDays"}:
            continue
        assert replayed[key] == pytest.approx(value, abs=1e-6) if isinstance(value, float) \
            else replayed[key] == value, key


def test_replay_signal_prices_never_exceed_as_of(prices, universe):
    """Every frozen record's reference price must exist on or before its date."""
    replay = HR.run_replay(prices, universe, benchmarks={"US": "SPY"},
                           cfg_lt={"minFactorSleeves": 1, "minFinancialCoverage": 0.0},
                           start="2017-01-01", end="2018-01-01", frequency="M",
                           model_version="test")
    assert replay["signals"]
    for record in replay["signals"]:
        as_of = pd.Timestamp(record["asOf"])
        close = prices[record["ticker"]]["Close"]
        visible = close.loc[:as_of]
        assert record["refClose"] == pytest.approx(float(visible.iloc[-1]), abs=1e-5)
        assert record["futureDataUsed"] is False


def test_replay_result_is_identical_when_future_data_is_removed(prices, universe):
    """Truncating the input at the last replay date must change nothing.

    If any code path reached past ``as_of``, deleting the future would move the
    numbers. Identical output over the same grid is the strongest available
    evidence that nothing did.
    """
    kwargs = dict(benchmarks={"US": "SPY"},
                  cfg_lt={"minFactorSleeves": 1, "minFinancialCoverage": 0.0},
                  start="2017-01-01", end="2017-06-30", frequency="M",
                  model_version="test")
    full = HR.run_replay(prices, universe, **kwargs)
    cutoff = pd.Timestamp("2017-06-30")
    truncated_prices = {t: f.loc[:cutoff] for t, f in prices.items()}
    truncated = HR.run_replay(truncated_prices, universe, **kwargs)

    assert len(full["signals"]) == len(truncated["signals"])
    for a, b in zip(full["signals"], truncated["signals"]):
        assert a["id"] == b["id"]
        assert a["alphaPercentile"] == b["alphaPercentile"]
        assert a["entryState"] == b["entryState"]
        assert a["features"] == b["features"]


def test_replay_grid_only_contains_real_trading_days(prices, universe):
    replay = HR.run_replay(prices, universe, benchmarks={"US": "SPY"},
                           cfg_lt={"minFactorSleeves": 1, "minFinancialCoverage": 0.0},
                           start="2017-01-01", end="2017-12-31", frequency="W",
                           model_version="test")
    sessions = set(prices["SPY"].index.normalize())
    for record in replay["signals"]:
        assert pd.Timestamp(record["asOf"]) in sessions


# --------------------------------------------------------------------------- #
# 2. Look-ahead: fundamentals
# --------------------------------------------------------------------------- #
def test_fundamentals_are_invisible_before_their_publication_date():
    store = pit_data.FundamentalStore({
        "AAA": [
            pit_data.FundamentalRecord("AAA", "2019Q4", "2020-02-14", {"roe": 0.10},
                                       filing_date="2020-02-12"),
            pit_data.FundamentalRecord("AAA", "2020Q1", "2020-05-14", {"roe": 0.20},
                                       filing_date="2020-05-12"),
        ]
    })
    # The quarter ENDED 2020-03-31, but nobody could read it on 2020-04-01.
    fields, status = store.visible_as_of("AAA", "2020-04-01")
    assert fields == {"roe": 0.10}
    assert status == pit_data.PIT_EXACT
    fields, _ = store.visible_as_of("AAA", "2020-05-15")
    assert fields == {"roe": 0.20}
    assert store.visible_as_of("AAA", "2019-01-01") == ({}, pit_data.UNAVAILABLE)


def test_current_snapshot_fundamentals_are_never_back_applied(prices, universe):
    """An empty PIT store must WITHHOLD fundamentals, not substitute today's."""
    store = pit_data.FundamentalStore({})
    fields, status = store.visible_as_of("AAA", "2016-01-01")
    assert fields == {}
    assert status == pit_data.CURRENT_SNAPSHOT_ONLY

    replay = HR.run_replay(prices, universe, benchmarks={"US": "SPY"},
                           cfg_lt={"minFactorSleeves": 1, "minFinancialCoverage": 0.0},
                           start="2017-01-01", end="2017-06-30", frequency="M",
                           fundamental_store=store, model_version="test")
    for record in replay["signals"]:
        assert record["factorPercentiles"]["value"] is None
        assert record["factorPercentiles"]["quality"] is None
        assert record["pit"]["fundamentalsSleeveUsed"] is False


def test_price_relative_fields_are_derived_against_the_price_of_the_day():
    """A filing states a numerator; only the day's price makes it a yield."""
    filing = {"epsTtm": 5.0, "bookValuePerShare": 40.0, "fcfPerShare": 2.0}
    cheap = pit_data.derive_price_relative(filing, 50.0)
    dear = pit_data.derive_price_relative(filing, 200.0)
    assert cheap["earningsYield"] == pytest.approx(0.10)
    assert cheap["bookYield"] == pytest.approx(0.80)
    assert cheap["fcfYield"] == pytest.approx(0.04)
    # Same filing, quadrupled price: the value sleeve must move, not sit still.
    assert dear["earningsYield"] == pytest.approx(0.025)
    assert dear["bookYield"] == pytest.approx(0.20)
    # The numerators themselves are left untouched for the record.
    assert cheap["epsTtm"] == 5.0


def test_a_stated_yield_is_never_overwritten_by_a_derived_one():
    out = pit_data.derive_price_relative(
        {"epsTtm": 5.0, "earningsYield": 0.031, "bookValuePerShare": 40.0}, 50.0)
    assert out["earningsYield"] == 0.031
    assert out["bookYield"] == pytest.approx(0.80)


def test_yields_production_withholds_are_not_invented_from_a_filing():
    """Production has no trailingPE for a loss and no priceToBook below zero."""
    out = pit_data.derive_price_relative(
        {"epsTtm": -3.0, "bookValuePerShare": -10.0, "fcfPerShare": -1.5}, 50.0)
    assert "earningsYield" not in out
    assert "bookYield" not in out
    # Free cash flow carries no such guard in production, so neither here.
    assert out["fcfYield"] == pytest.approx(-0.03)


def test_nothing_is_derived_without_a_usable_price():
    filing = {"epsTtm": 5.0, "bookValuePerShare": 40.0}
    for price in (None, 0.0, -12.0, float("nan"), "n/a"):
        assert pit_data.derive_price_relative(filing, price) == filing


def test_contract_accepts_per_share_numerators_at_the_top_level(tmp_path):
    path = tmp_path / "fundamentals.jsonl"
    path.write_text(json.dumps({
        "ticker": "AAA", "fiscalPeriod": "2020Q1", "reportDate": "2020-03-31",
        "publicationDate": "2020-05-14", "availableFrom": "2020-05-14",
        "currency": "USD", "source": "sec-xbrl", "sourceAsOf": "2020-05-14",
        "revisionStatus": "ORIGINAL",
        "epsTtm": 5.0, "bookValuePerShare": 40.0, "fcfPerShare": 2.0,
    }) + "\n", encoding="utf-8")
    store = pit_data.FundamentalStore.from_jsonl(path)
    assert store.diagnostics["rowsAccepted"] == 1
    fields, status = store.visible_as_of("AAA", "2020-06-01")
    assert fields["epsTtm"] == 5.0
    assert fields["bookValuePerShare"] == 40.0
    assert status == pit_data.PIT_EXACT
    # Still no yield in the store itself — that is the consumer's job.
    assert "earningsYield" not in fields


def test_replay_builds_a_value_sleeve_from_per_share_numerators(prices, universe):
    """The gap this closes: filings alone used to leave value permanently null."""
    records = {}
    for idx, ticker in enumerate(sorted(universe["US"])):
        records[ticker] = [pit_data.FundamentalRecord(
            ticker, "2016Q4", "2017-01-02",
            {"epsTtm": 2.0 + idx, "bookValuePerShare": 20.0 + 4 * idx,
             "fcfPerShare": 1.0 + idx * 0.5, "roe": 0.05 + idx * 0.01,
             "operatingMargin": 0.1, "profitMargin": 0.08,
             "debtToEquity": 40.0, "earningsGrowth": 0.03},
            filing_date="2016-12-30")]
    store = pit_data.FundamentalStore(records)
    replay = HR.run_replay(prices, universe, benchmarks={"US": "SPY"},
                           cfg_lt={"minFactorSleeves": 1, "minFinancialCoverage": 0.0},
                           start="2017-01-01", end="2017-06-30", frequency="M",
                           fundamental_store=store, model_version="test")
    scored = [r for r in replay["signals"] if r["factorPercentiles"]["value"] is not None]
    assert scored, "value sleeve stayed empty despite point-in-time numerators"
    assert any(r["pit"]["fundamentalsSleeveUsed"] for r in replay["signals"])


# --------------------------------------------------------------------------- #
# 3. Look-ahead: macro vintages
# --------------------------------------------------------------------------- #
def _releases(rows) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["date", "realtime_start", "value"])


def test_macro_view_truncates_and_declares_revised_history():
    index = pd.bdate_range("2015-01-01", periods=800)
    macro = pd.DataFrame({"Treasury_10Y": np.linspace(2.0, 4.0, 800)}, index=index)
    view = pit_data.MacroVintageView(macro, None)
    truncated, _ = view.as_of("2016-06-30")
    assert truncated.index.max() <= pd.Timestamp("2016-06-30")
    # No ALFRED vintages -> the value is a later revision, and says so.
    assert view.pit_status() == pit_data.REVISED_HISTORY
    assert view.pit_status("Treasury_10Y") == pit_data.REVISED_HISTORY


def test_naming_a_series_vintaged_without_releases_proves_nothing():
    """A label is not evidence — only a release history is."""
    index = pd.bdate_range("2015-01-01", periods=50)
    macro = pd.DataFrame({"Treasury_10Y": np.linspace(2.0, 4.0, 50)}, index=index)
    claimed = pit_data.MacroVintageView(macro, None, vintage_series={"Treasury_10Y"})
    assert claimed.pit_status("Treasury_10Y") == pit_data.REVISED_HISTORY
    assert claimed.pit_status() == pit_data.REVISED_HISTORY
    assert claimed.vintage_series == set()


def test_vintage_column_returns_the_print_available_then_not_the_revision():
    releases = _releases([
        ("2015-01-01", "2015-02-10", 1.0),   # first print of January
        ("2015-01-01", "2015-03-15", 1.8),   # revised a month later
        ("2015-02-01", "2015-03-10", 2.0),
        ("2015-03-01", "2015-04-12", 3.0),   # not published yet on 2015-03-20
    ])
    early = pit_data.vintage_column(releases, "2015-03-01")
    assert early.loc[pd.Timestamp("2015-01-01")] == 1.0   # the number they had
    assert pd.Timestamp("2015-03-01") not in early.index  # unpublished, unseen

    later = pit_data.vintage_column(releases, "2015-03-20")
    assert later.loc[pd.Timestamp("2015-01-01")] == 1.8   # the revision, once out
    assert later.loc[pd.Timestamp("2015-02-01")] == 2.0
    assert pd.Timestamp("2015-03-01") not in later.index


def test_as_of_rebuilds_a_vintaged_column_and_leaves_the_others_alone():
    index = pd.to_datetime(["2015-01-01", "2015-02-01", "2015-03-01"])
    macro = pd.DataFrame({"Headline_CPI": [1.8, 2.0, 3.0],
                          "Treasury_10Y": [2.1, 2.2, 2.3]}, index=index)
    view = pit_data.MacroVintageView(macro, None, vintages={"Headline_CPI": _releases([
        ("2015-01-01", "2015-02-10", 1.0),
        ("2015-01-01", "2015-03-15", 1.8),
        ("2015-02-01", "2015-03-10", 2.0),
    ])})
    rebuilt, _ = view.as_of("2015-03-01")
    # The revised frame says 1.8 for January; on 2015-03-01 the print was 1.0.
    assert rebuilt.loc[pd.Timestamp("2015-01-01"), "Headline_CPI"] == 1.0
    assert rebuilt.loc[pd.Timestamp("2015-01-01"), "Treasury_10Y"] == 2.1
    assert view.pit_status("Headline_CPI") == pit_data.PIT_EXACT
    # One vintaged column out of two is not a vintage-clean panel.
    assert view.pit_status() == pit_data.PIT_APPROXIMATE


def test_aggregate_is_exact_only_when_every_column_is_vintaged():
    index = pd.to_datetime(["2015-01-01", "2015-02-01"])
    macro = pd.DataFrame({"Headline_CPI": [1.0, 2.0]}, index=index)
    view = pit_data.MacroVintageView(macro, None, vintages={"Headline_CPI": _releases([
        ("2015-01-01", "2015-01-20", 1.0),
        ("2015-02-01", "2015-02-20", 2.0),
    ])})
    assert view.pit_status() == pit_data.PIT_EXACT
    # And that is what the integrity gate is asking for.
    from pipeline import portfolio_validation as PV
    gate = PV.data_integrity({"macroPitStatus": view.pit_status()}, [])
    assert gate["integrityGate"]["checks"]["vintageMacro"] is True


def test_macro_view_reports_unavailable_when_absent():
    assert pit_data.MacroVintageView(None, None).pit_status() == pit_data.UNAVAILABLE


# --------------------------------------------------------------------------- #
# 4. Look-ahead: universe membership
# --------------------------------------------------------------------------- #
def test_universe_excludes_names_not_yet_listed_and_already_delisted():
    history = pit_data.UniverseHistory({
        "OLD": {"listed": "2010-01-01", "delisted": "2016-06-30", "region": "US"},
        "MID": {"listed": "2010-01-01", "delisted": None, "region": "US"},
        "NEW": {"listed": "2019-01-01", "delisted": None, "region": "US"},
    })
    snapshot = history.snapshot("2017-01-01", {"US": ["OLD", "MID", "NEW"]})
    assert snapshot.by_region["US"] == ["MID"]
    assert snapshot.survivorship_risk == "LOW"
    assert snapshot.reconstructed is True

    # A delisted name must reappear when the replay date precedes its delisting.
    earlier = history.snapshot("2015-01-01", {"US": ["OLD", "MID", "NEW"]})
    assert earlier.by_region["US"] == ["MID", "OLD"]


def test_missing_constituent_history_records_survivorship_risk(prices, universe):
    snapshot = pit_data.UniverseHistory({}).snapshot("2017-01-01", universe)
    assert snapshot.survivorship_risk == "HIGH"
    assert pit_data.SURVIVORSHIP_UNRESOLVED in snapshot.notes

    replay = HR.run_replay(prices, universe, benchmarks={"US": "SPY"},
                           cfg_lt={"minFactorSleeves": 1, "minFinancialCoverage": 0.0},
                           start="2017-01-01", end="2017-03-31", frequency="M",
                           model_version="test")
    assert replay["diagnostics"]["survivorshipNote"] == pit_data.SURVIVORSHIP_UNRESOLVED
    assert all(r["pit"]["survivorshipRisk"] == "HIGH" for r in replay["signals"])


def test_membership_file_without_prices_does_not_clear_survivorship(prices, universe):
    """The trap: a file the replay cannot price used to report coverage 100%."""
    memberships = {t: {"listed": "2010-01-01", "delisted": None, "region": "US"}
                   for t in universe["US"]}
    # Two names that were listed then and died before today, so the price panel
    # — which is fetched from the CURRENT universe — has nothing for them.
    memberships["DEAD1"] = {"listed": "2010-01-01", "delisted": "2018-01-01", "region": "US"}
    memberships["DEAD2"] = {"listed": "2010-01-01", "delisted": "2018-01-01", "region": "US"}
    history = pit_data.UniverseHistory(memberships)

    snapshot = history.snapshot("2017-01-01", universe,
                                view=HR.PricePanel(prices).membership_view("2017-01-01"),
                                min_history=HR.MIN_HISTORY_ROWS)
    assert "DEAD1" not in snapshot.by_region["US"]
    assert snapshot.missing_prices == ["DEAD1", "DEAD2"]
    assert snapshot.coverage_pct is not None and snapshot.coverage_pct < 100.0
    assert snapshot.survivorship_risk != "LOW"

    replay = HR.run_replay(prices, universe, benchmarks={"US": "SPY"},
                           cfg_lt={"minFactorSleeves": 1, "minFinancialCoverage": 0.0},
                           start="2017-01-01", end="2017-03-31", frequency="M",
                           universe_history=history, model_version="test")
    diagnostics = replay["diagnostics"]
    assert diagnostics["constituentCoveragePct"] < 100.0
    assert diagnostics["constituentsWithoutPriceHistoryCount"] == 2
    assert diagnostics["survivorshipRisk"] != "LOW"
    assert diagnostics["survivorshipNote"] == pit_data.SURVIVORSHIP_UNRESOLVED
    assert diagnostics["impactOnPromotionEligibility"] == "KELLY_AND_SELECTOR_PROMOTION_BLOCKED"

    from pipeline import portfolio_validation as PV
    gate = PV.data_integrity(diagnostics, [{"region": "US"}])
    assert gate["integrityGate"]["checks"]["historicalUniverse"] is False
    assert gate["historicalResultLabel"] == "SURVIVORSHIP_BIAS_UNRESOLVED"


def test_fully_priced_membership_file_does_clear_survivorship(prices, universe):
    memberships = {t: {"listed": "2010-01-01", "delisted": None, "region": "US"}
                   for t in universe["US"]}
    history = pit_data.UniverseHistory(memberships)
    replay = HR.run_replay(prices, universe, benchmarks={"US": "SPY"},
                           cfg_lt={"minFactorSleeves": 1, "minFinancialCoverage": 0.0},
                           start="2017-01-01", end="2017-03-31", frequency="M",
                           universe_history=history, model_version="test")
    diagnostics = replay["diagnostics"]
    assert diagnostics["constituentCoveragePct"] == 100.0
    assert diagnostics["survivorshipRisk"] == "LOW"
    assert diagnostics["survivorshipNote"] is None
    assert diagnostics["affectedObservationsPct"] == 0.0

    from pipeline import portfolio_validation as PV
    gate = PV.data_integrity(diagnostics, [{"region": "US"}])
    assert gate["integrityGate"]["checks"]["historicalUniverse"] is True


def test_names_without_history_before_as_of_are_dropped(prices):
    late = _frame(555, periods=300, start="2019-01-01")
    combined = {**prices, "LATE": late}
    snapshot = pit_data.UniverseHistory({}).snapshot(
        "2017-01-01", {"US": ["T00", "LATE"]},
        view=HR.PricePanel(combined).membership_view("2017-01-01"),
        min_history=HR.MIN_HISTORY_ROWS)
    assert snapshot.by_region["US"] == ["T00"]


# --------------------------------------------------------------------------- #
# 5. PIT quality scoring
# --------------------------------------------------------------------------- #
def test_pit_coverage_ignores_sources_that_contributed_nothing():
    """A withheld sleeve is a coverage gap, not a leak, and must not be scored
    as one — otherwise a clean price-only replay is permanently unusable."""
    price_only = pit_data.coverage_score(
        {"price": pit_data.PIT_APPROXIMATE, "fundamentals": pit_data.UNAVAILABLE,
         "universe": pit_data.REVISED_HISTORY, "macro": pit_data.UNAVAILABLE},
        HR.PIT_SOURCE_WEIGHTS_PRICE_ONLY)
    assert price_only == pytest.approx(0.7975, abs=1e-4)
    assert price_only >= pit_data.MIN_CALIBRATION_COVERAGE


def test_pit_coverage_rises_when_real_pit_fundamentals_exist():
    with_fundamentals = pit_data.coverage_score(
        {"price": pit_data.PIT_APPROXIMATE, "fundamentals": pit_data.PIT_EXACT,
         "universe": pit_data.PIT_EXACT, "macro": pit_data.REVISED_HISTORY},
        HR.PIT_SOURCE_WEIGHTS_WITH_FUNDAMENTALS)
    price_only = pit_data.coverage_score(
        {"price": pit_data.PIT_APPROXIMATE, "universe": pit_data.REVISED_HISTORY},
        HR.PIT_SOURCE_WEIGHTS_PRICE_ONLY)
    assert with_fundamentals > price_only
    assert pit_data.quality_label(with_fundamentals) in {"HIGH", "MEDIUM"}


def test_low_pit_observations_are_excluded_from_calibration():
    good = {"pit": {"pitCoverage": 0.9, "lookAheadCheckPassed": True,
                    "usableForCalibration": True}}
    poor = {"pit": {"pitCoverage": 0.2, "lookAheadCheckPassed": True,
                    "usableForCalibration": False}}
    leaked = {"pit": {"pitCoverage": 0.99, "lookAheadCheckPassed": False}}
    assert pit_data.usable_for_calibration(good) is True
    assert pit_data.usable_for_calibration(poor) is False
    assert pit_data.usable_for_calibration(leaked) is False


def test_current_snapshot_only_carries_zero_pit_weight():
    assert pit_data.PIT_WEIGHT[pit_data.CURRENT_SNAPSHOT_ONLY] == 0.0
    assert pit_data.PIT_WEIGHT[pit_data.REVISED_HISTORY] < pit_data.PIT_WEIGHT[pit_data.PIT_EXACT]


# --------------------------------------------------------------------------- #
# 6. Outcomes use only post-signal data
# --------------------------------------------------------------------------- #
def test_outcomes_only_use_prices_after_the_signal_date(prices):
    signal = {"id": "x", "date": "2017-01-04", "ticker": "T00", "region": "US",
              "benchmark": "SPY", "alphaPercentile": 90}
    outcomes = HO.compute_outcomes([signal], prices, {"SPY": prices["SPY"]["Close"]})
    assert outcomes
    horizon = outcomes[0]["horizons"]["21"]
    close = prices["T00"]["Close"]
    start = close.index.get_indexer([pd.Timestamp("2017-01-04")], method="ffill")[0]
    expected = float(close.iloc[start + 21] / close.iloc[start] - 1)
    assert horizon["absoluteReturn"] == pytest.approx(expected, abs=1e-6)


def test_immature_horizons_produce_no_partial_outcome(prices):
    last = prices["T00"].index[-1]
    signal = {"id": "y", "date": last.strftime("%Y-%m-%d"), "ticker": "T00",
              "region": "US", "benchmark": "SPY"}
    assert HO.compute_outcomes([signal], prices, {"SPY": prices["SPY"]["Close"]}) == []


def test_excess_return_requires_the_exact_same_benchmark_sessions(prices):
    """A nearby session on a different calendar is not a valid comparison.

    A KR name whose 126-day window is measured against US sessions that merely
    fall close by would produce an "excess return" that is partly a timezone
    artifact. The benchmark leg must land on the exact same two dates or the
    excess return is withheld.
    """
    # A benchmark trading only on Mondays: a Wednesday signal date has no match.
    weekly = prices["SPY"]["Close"]
    weekly = weekly[weekly.index.dayofweek == 0]
    signal = {"id": "z", "date": "2017-01-04", "ticker": "T00", "region": "KR",
              "benchmark": "SPY"}
    outcomes = HO.compute_outcomes([signal], prices, {"SPY": weekly})
    horizon = outcomes[0]["horizons"]["21"]
    assert pd.Timestamp("2017-01-04").dayofweek != 0
    assert horizon["benchmarkReturn"] is None
    assert horizon["excessReturn"] is None
    assert horizon["costAdjustedExcessReturn"] is None
    # The absolute return is still computed — only the comparison is withheld.
    assert horizon["absoluteReturn"] is not None


def test_daily_session_normalization_preserves_asian_wall_dates():
    dates = pd.bdate_range("2025-01-02", periods=40)
    stock_dates = dates.tz_localize("Asia/Seoul")
    stock = pd.DataFrame({"Close": np.arange(40, dtype=float) + 100}, index=stock_dates)
    benchmark = pd.Series(np.arange(40, dtype=float) + 200, index=dates)
    signal = {"id": "kr-tz", "date": "2025-01-02", "ticker": "005930.KS",
              "region": "KR", "benchmark": "^KS200"}

    outcome = HO.compute_outcomes(
        [signal], {"005930.KS": stock}, {"^KS200": benchmark}, horizons=(21,))[0]

    assert outcome["benchmark"] == "^KS200"
    assert outcome["horizons"]["21"]["benchmarkReturn"] is not None
    assert outcome["horizons"]["21"]["excessReturn"] is not None


def test_outcome_metrics_cover_path_risk_not_just_the_endpoint(prices):
    signal = {"id": "w", "date": "2017-01-04", "ticker": "T00", "region": "US",
              "benchmark": "SPY"}
    horizon = HO.compute_outcomes([signal], prices,
                                  {"SPY": prices["SPY"]["Close"]})[0]["horizons"]["126"]
    for key in ("mfe", "mae", "maxDrawdown", "realizedVol", "downsideVol",
                "cvar95", "costAdjustedExcessReturn"):
        assert key in horizon
    assert horizon["mfe"] >= horizon["absoluteReturn"] >= horizon["mae"]
    assert horizon["maxDrawdown"] <= 0


def test_transaction_cost_reduces_excess_return(prices):
    signal = {"id": "c", "date": "2017-01-04", "ticker": "T00", "region": "KR",
              "benchmark": "SPY"}
    policy = {"KR": {"commissionBps": 5, "spreadBps": 12, "sellTaxBps": 20}}
    horizon = HO.compute_outcomes([signal], prices, {"SPY": prices["SPY"]["Close"]},
                                  cost_policy=policy)[0]["horizons"]["126"]
    assert horizon["costAdjustedExcessReturn"] < horizon["excessReturn"]


# --------------------------------------------------------------------------- #
# 7. Ledger immutability and versioning
# --------------------------------------------------------------------------- #
def test_incremental_replay_never_regenerates_an_existing_signal(prices, universe):
    kwargs = dict(benchmarks={"US": "SPY"},
                  cfg_lt={"minFactorSleeves": 1, "minFinancialCoverage": 0.0},
                  start="2017-01-01", end="2017-06-30", frequency="M",
                  model_version="test")
    first = HR.run_replay(prices, universe, **kwargs)
    ids = {r["id"] for r in first["signals"]}
    second = HR.run_replay(prices, universe, existing_ids=ids, **kwargs)
    assert second["signals"] == []
    assert second["diagnostics"]["signalsSkippedAlreadyPresent"] == len(ids)


def test_signal_id_separates_model_and_replay_generations():
    a = HR.signal_id("2019-05-15", "US", "NVDA", "replay-v1", "model-a")
    b = HR.signal_id("2019-05-15", "US", "NVDA", "replay-v1", "model-b")
    c = HR.signal_id("2019-05-15", "US", "NVDA", "replay-v2", "model-a")
    assert len({a, b, c}) == 3


def test_appending_refuses_to_mutate_existing_records(tmp_path):
    from pipeline import historical_store as HS
    stamps = {"replayVersion": "replay-v1", "date": "2019-05-15"}
    HS.append_signals(tmp_path, [{"id": "1", "alphaPercentile": 90, **stamps}])
    appended, skipped = HS.append_signals(tmp_path, [
        {"id": "1", "alphaPercentile": 10, **stamps},
        {"id": "2", "alphaPercentile": 55, **stamps},
    ])
    assert appended == 1 and skipped == 1
    stored = {row["id"]: row for row in HS.load(tmp_path, HS.SIGNALS)}
    # The original record keeps the value the model actually produced that day.
    assert stored["1"]["alphaPercentile"] == 90
    assert stored["2"]["alphaPercentile"] == 55


def test_every_record_carries_its_version_stamps(prices, universe):
    replay = HR.run_replay(prices, universe, benchmarks={"US": "SPY"},
                           cfg_lt={"minFactorSleeves": 1, "minFinancialCoverage": 0.0},
                           start="2017-01-01", end="2017-03-31", frequency="M",
                           model_version="model-x")
    for record in replay["signals"]:
        assert record["replayVersion"] == HR.REPLAY_VERSION
        assert record["featureVersion"] == HR.FEATURE_VERSION
        assert record["dataVersion"] == HR.DATA_VERSION
        assert record["modelVersion"] == "model-x"
        assert record["evidenceClass"] == "HISTORICAL_OOS"


# --------------------------------------------------------------------------- #
# 8. Change features are backward-looking
# --------------------------------------------------------------------------- #
def test_change_features_compare_against_the_previous_grid_date_only(prices, universe):
    replay = HR.run_replay(prices, universe, benchmarks={"US": "SPY"},
                           cfg_lt={"minFactorSleeves": 1, "minFinancialCoverage": 0.0},
                           start="2017-01-01", end="2017-12-31", frequency="M",
                           model_version="test")
    by_date: dict[str, list[dict]] = {}
    for record in replay["signals"]:
        by_date.setdefault(record["asOf"], []).append(record)
    dates = sorted(by_date)
    # The very first grid date has no predecessor, so every delta is null.
    for record in by_date[dates[0]]:
        assert record["features"]["alphaPercentileDelta"] is None
        assert record["features"]["entryStateImproved"] is None
    # A later date's delta reproduces the difference against the prior date.
    previous = {r["ticker"]: r for r in by_date[dates[1]]}
    for record in by_date[dates[2]]:
        prior = previous.get(record["ticker"])
        if prior is None or record["features"]["alphaPercentileDelta"] is None:
            continue
        expected = record["features"]["alphaPercentile"] - prior["features"]["alphaPercentile"]
        assert record["features"]["alphaPercentileDelta"] == pytest.approx(expected)


def test_coverage_summary_separates_tracking_from_maturity(prices, universe):
    replay = HR.run_replay(prices, universe, benchmarks={"US": "SPY"},
                           cfg_lt={"minFactorSleeves": 1, "minFinancialCoverage": 0.0},
                           start="2017-01-01", end="2018-12-31", frequency="M",
                           model_version="test")
    outcomes = HO.compute_outcomes(replay["signals"], prices,
                                   {"SPY": prices["SPY"]["Close"]})
    summary = HO.coverage_summary(replay["signals"], outcomes, horizon=126)
    assert summary["trackingDays"] > 0
    assert summary["signalsRecorded"] == len(replay["signals"])
    # Tracking spans the whole signal ledger; maturity only the resolved part.
    assert summary["maturedObservationDays"] <= summary["trackingDays"]
    assert summary["maturedSignals"] <= summary["signalsRecorded"]


def test_benchmark_coverage_gate_is_regional_and_fail_closed():
    outcomes = [{
        "id": "kr-1", "date": "2020-01-02", "ticker": "005930.KS",
        "region": "KR", "benchmark": "^KS200",
        "horizons": {"126": {"absoluteReturn": .1, "benchmarkReturn": None,
                              "endDate": "2020-07-01"}},
    }, {
        "id": "us-1", "date": "2020-01-02", "ticker": "AAPL",
        "region": "US", "benchmark": "SPY",
        "horizons": {"126": {"absoluteReturn": .1, "benchmarkReturn": .05,
                              "endDate": "2020-07-01"}},
    }]
    coverage = HO.CoverageAccumulator(126).add_outcomes(outcomes).summary()
    gate = HO.benchmark_coverage_gate(coverage, horizon=126, min_coverage_pct=95)

    assert coverage["benchmarkCoverageByRegion"]["KR"]["126"]["coveragePct"] == 0
    assert coverage["benchmarkCoverageByRegion"]["US"]["126"]["coveragePct"] == 100
    assert gate["eligible"] is False
    assert [row["region"] for row in gate["failures"]] == ["KR"]

    no_outcomes = HO.coverage_summary(
        [{"id": "kr-new", "date": "2025-01-02", "region": "KR"}], [], 126)
    no_outcomes_gate = HO.benchmark_coverage_gate(no_outcomes, horizon=126)
    assert no_outcomes_gate["eligible"] is False
    assert no_outcomes_gate["failures"][0]["reason"] == "no_matured_absolute_returns"
