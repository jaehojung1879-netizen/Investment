"""Leakage, PIT quality and replay-integrity tests.

These are the tests that decide whether the historical evidence is worth
anything. A replay that reads the future is not "slightly optimistic" — it is
void, and every downstream number built on it is void too. So the assertions
here are hard equalities and explicit exceptions, not tolerance bands.
"""
from __future__ import annotations

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


# --------------------------------------------------------------------------- #
# 3. Look-ahead: macro vintages
# --------------------------------------------------------------------------- #
def test_macro_view_truncates_and_declares_revised_history():
    index = pd.bdate_range("2015-01-01", periods=800)
    macro = pd.DataFrame({"Treasury_10Y": np.linspace(2.0, 4.0, 800)}, index=index)
    view = pit_data.MacroVintageView(macro, None)
    truncated, _ = view.as_of("2016-06-30")
    assert truncated.index.max() <= pd.Timestamp("2016-06-30")
    # No ALFRED vintages -> the value is a later revision, and says so.
    assert view.pit_status() == pit_data.REVISED_HISTORY
    assert view.pit_status("Treasury_10Y") == pit_data.REVISED_HISTORY

    vintaged = pit_data.MacroVintageView(macro, None, vintage_series={"Treasury_10Y"})
    assert vintaged.pit_status("Treasury_10Y") == pit_data.PIT_EXACT


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
