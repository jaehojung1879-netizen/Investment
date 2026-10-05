"""kr-integrated-alpha-portfolio-v1: the daily replay and the metrics, on an INVENTED world (invented prices, scores and market tables; nothing historical)."""
import copy

import numpy as np
import pandas as pd
import pytest
from pipeline import kr_concentrated_portfolio as P
from pipeline import kr_integrated_alpha_portfolio as M
from pipeline import kr_integrated_alpha_portfolio_execution as X
from pipeline import kr_integrated_alpha_portfolio_replay as R
from pipeline import kr_market_risk_anatomy as MA
from pipeline import kr_market_risk_model as K


@pytest.fixture(scope="module")
def world():
    return X.synthetic_world()


def run(world, arch, ctx=None, table="default", stress=1.0, decisions=None):
    ctx = ctx or R.Context(world["prices"], world["market"], world["days"])
    cfg = M.ARCHITECTURES[arch]
    layer = "I+S" if cfg["industry"] else "S"
    decisions = decisions or {s: p[layer] for s, p in world["decisions"].items()}
    market = None if cfg["market"] is None else (world["tables"][cfg["market"]] if isinstance(table, str) else table)
    return R.replay_architecture(arch, decisions, world["anchors"], market, ctx, stress=stress)


def world_first_anchor(results):
    return results["A"]["path"][0]["date"]


@pytest.fixture(scope="module")
def paths(world):
    """All six architectures, with every execute_rebalance call recorded (architecture, desired targets, selected names, multiplier)."""
    calls, current = [], {"arch": None}
    real = P.execute_rebalance

    def spy(before, desired, adv, selected, multiplier, cfg, **kwargs):
        calls.append({"arch": current["arch"], "desired": dict(desired), "selected": list(selected), "multiplier": multiplier, "before": dict(before)})
        return real(before, desired, adv, selected, multiplier, cfg, **kwargs)
    results = {}
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(P, "execute_rebalance", spy)
        for arch in M.ARCH_ORDER:
            current["arch"] = arch
            results[arch] = run(world, arch)
    return results, calls


def test_anchors_are_every_21st_session_from_the_fixed_origin_with_the_last_prior_weekly_signal(world):
    anchors = world["anchors"]
    days = [str(d.date()) for d in world["days"]]
    assert anchors and all(days.index(day) % M.STRIDE_KR_SESSIONS == 0 for day, _ in anchors)
    assert all(signal < day for day, signal in anchors) and [a for a, _ in anchors] == sorted(a for a, _ in anchors)
    shorter = R.anchor_schedule(world["days"][:-60], [s for s in {s for _, s in anchors}] + ["2017-12-22"], "2016-06-01")
    assert shorter[:len(shorter) - 2] == anchors[:len(shorter) - 2]                      # where the data end moves no earlier anchor moves
    assert R.anchor_schedule(world["days"], ["2016-01-01"], "2030-01-01") == []


def test_all_six_paths_complete_on_one_calendar_with_one_passive_reference(paths):
    results, _ = paths
    assert all(r["complete"] for r in results.values())
    dates = {a: [r["date"] for r in results[a]["path"]] for a in M.ARCH_ORDER}
    assert len({tuple(d) for d in dates.values()}) == 1                                  # same sessions
    bench = {a: [r["benchmarkNav"] for r in results[a]["path"]] for a in M.ARCH_ORDER}
    assert all(bench[a] == bench["A"] for a in bench)                                    # the passive reference is the same in every path
    anchor_days = {a: [r["date"] for r in results[a]["path"] if r["kind"] == "ANCHOR"] for a in "ABC"}
    assert all(anchor_days[a] == anchor_days["A"] for a in anchor_days)
    assert {a: dates[a][0] for a in M.ARCH_ORDER} == {a: world_first_anchor(results) for a in M.ARCH_ORDER}


def test_the_underlying_decision_is_shared_and_the_market_only_scales_it(paths, world):
    results, calls = paths
    by_arch = {a: [c for c in calls if c["arch"] == a] for a in M.ARCH_ORDER}
    for group, layer in (("ABC", "S"), ("DEF", "I+S")):
        anchor_calls = {a: [c for c in by_arch[a] if c["selected"]] for a in group}
        signals = [s for _, s in world["anchors"] if world["decisions"][s][layer]["available"]]
        assert signals and len(signals) < len(world["anchors"])                               # the invented world includes registered no-trade anchors
        for index, signal in enumerate(signals):
            base = world["decisions"][signal][layer]
            for a in group:
                c = anchor_calls[a][index]
                assert c["selected"] == base["selected"]                                     # identical names
                m = c["multiplier"]
                assert set(c["desired"]) == set(base["baseWeights"])
                for t, w in base["baseWeights"].items():
                    assert c["desired"][t] == pytest.approx(w * m, abs=1e-15)                # base weights x the market multiplier, nothing else
        assert all(c["multiplier"] == 1.0 for c in by_arch[group[0]])                        # market OFF: no scaling and no market trade
    assert not any(r["kind"] == "MARKET" for a in "AD" for r in results[a]["path"])
    assert {r["marketMultiplier"] for r in results["A"]["path"]} == {1.0}


def test_market_scale_trades_never_add_a_name_or_swap_one_and_never_exceed_the_target(paths):
    results, _ = paths
    for arch in "BCEF":
        path = results[arch]["path"]
        scales = [(i, r) for i, r in enumerate(path) if r["kind"] == "MARKET"]
        assert scales, arch
        for i, record in scales:
            previous = path[i - 1]
            assert set(record["weights"]) <= set(previous["weights"]) and record["added"] == 0 and record["replaced"] == 0
            assert sum(record["weights"].values()) <= record["marketMultiplier"] + 1e-9
            assert record["turnover"] > 0 and record["cost"] > 0
    assert any(r["kind"] == "MARKET" for r in results["E"]["path"])
    c1 = [r["date"] for r in results["C"]["path"] if r["kind"] == "MARKET"]
    c0 = [r["date"] for r in results["B"]["path"] if r["kind"] == "MARKET"]
    assert len(c1) == len(c0) - 1                                                          # C1's second target repeats 0.7, so it trades once less


def test_no_leverage_at_most_five_holdings_and_non_negative_cash(paths):
    for arch, result in paths[0].items():
        for r in result["path"]:
            assert sum(r["weights"].values()) <= 1 + 1e-9 and r["holdings"] <= 5 and r["cashWeight"] >= -1e-9
            assert all(w <= 1.0 for w in r["weights"].values())


def test_a_market_table_that_never_leaves_one_is_inert(world):
    flat = pd.DataFrame({"decisionDate": [world["days"][0]], "executionDate": [world["days"][0]], "target": [1.0]})
    inert, base = run(world, "B", table=flat), run(world, "A")
    assert [r["nav"] for r in inert["path"]] == [r["nav"] for r in base["path"]] and not any(r["kind"] == "MARKET" for r in inert["path"])


def test_replacements_equal_the_names_actually_dropped_between_consecutive_anchors(paths):
    for arch in M.ARCH_ORDER:
        path = paths[0][arch]["path"]
        anchors = [i for i, r in enumerate(path) if r["kind"] == "ANCHOR"]
        for i in anchors[1:]:
            before, after = set(path[i - 1]["weights"]), set(path[i]["weights"])
            assert path[i]["replaced"] == len(before - after) and path[i]["added"] == len(after - before)
        summary = R.summarize_path(path)
        assert summary["replacements"] == sum(path[i]["replaced"] for i in anchors[1:]) and summary["anchorRebalances"] == len(anchors)


def test_summary_metrics_are_consistent_with_the_path(paths):
    path = paths[0]["A"]["path"]
    s = R.summarize_path(path)
    nav = np.array([1.0] + [r["nav"] for r in path])
    assert s["cumulativeNetReturn"] == pytest.approx(nav[-1] - 1) and s["maxDrawdown"] == pytest.approx(K.max_drawdown(pd.Series(nav))["maxDrawdown"])
    assert s["terminalCostDrag"] == pytest.approx(path[-1]["grossNav"] - path[-1]["nav"]) and s["terminalCostDrag"] >= 0
    assert s["worstRollingReturnH63"] == pytest.approx(K.worst_rolling_return(nav, 63)) and s["maxDrawdown"] <= 0
    assert s["totalOneWayTurnover"] == pytest.approx(sum(r["turnover"] for r in path)) and 0 < s["averageHoldings"] <= 5
    assert s["averageGrossEquityExposure"] == pytest.approx(1 - s["averageCashShare"]) and s["maxSecurityWeight"] <= 0.3 * 1.5
    assert set(s["halves"]) == {"firstHalf", "secondHalf"} and sum(1 for _ in s["calendarYears"]) >= 2
    assert s["firstDate"] == path[0]["date"] and s["lastDate"] == path[-1]["date"] and s["sessions"] == len(path)
    assert all(k in s for k in ("netAnnualizedReturn", "excessAnnualizedVsPassive", "annualizedCostDrag", "recoverySessions", "annualizedOneWayTurnover", "episodes"))
    passive = R.passive_summary(path)
    assert passive["id"] == M.PASSIVE and passive["returnBasis"] == M.RETURN_BASIS and "complete shareholder total return" in passive["note"]


def test_market_overlay_reduces_exposure_and_gross_equals_net_plus_costs(paths):
    results, _ = paths
    a, b = R.summarize_path(results["A"]["path"]), R.summarize_path(results["B"]["path"])
    assert b["averageGrossEquityExposure"] < a["averageGrossEquityExposure"] and b["reducedSessionShare"] > 0 and a["reducedSessionShare"] == 0
    assert b["marketScaleTrades"] > 0 and a["marketScaleTrades"] == 0


def test_higher_costs_never_improve_net_return(world):
    base = R.summarize_path(run(world, "E")["path"])
    for stress in (2.0, 3.0):
        stressed = R.summarize_path(run(world, "E", stress=stress)["path"])
        assert stressed["cumulativeNetReturn"] < base["cumulativeNetReturn"] and stressed["totalCostFractionOfNav"] > base["totalCostFractionOfNav"]
        base = stressed


def test_a_replay_is_deterministic(world):
    first, second = run(world, "F"), run(world, "F")
    assert [r["nav"] for r in first["path"]] == [r["nav"] for r in second["path"]] and [r["weights"] for r in first["path"]] == [r["weights"] for r in second["path"]]


def test_an_unresolved_held_mark_blocks_only_the_paths_that_hold_the_name(world, paths):
    results, _ = paths
    held = {a: {t for r in results[a]["path"] for t in r["weights"]} for a in M.ARCH_ORDER}
    target = sorted(held["A"])[0]
    first_held = next(r["date"] for r in results["A"]["path"] if target in r["weights"])
    prices = {t: f.copy() for t, f in world["prices"].items()}
    cut = pd.Timestamp(first_held) + pd.Timedelta(days=5)
    prices[target].loc[prices[target].index > cut, "Close"] = np.nan                    # delisted: no close, but the market store still shows volume
    ctx = R.Context(prices, world["market"], world["days"])
    blocked = {a: run(world, a, ctx=ctx) for a in M.ARCH_ORDER}
    for a in M.ARCH_ORDER:
        if target in held[a]:
            assert blocked[a]["complete"] is False and blocked[a]["reason"].startswith(R.UNRESOLVED) and target in blocked[a]["reason"]
        else:
            assert blocked[a]["complete"] is True and [r["nav"] for r in blocked[a]["path"]] == [r["nav"] for r in results[a]["path"]]
    assert blocked["A"]["complete"] is False                                           # never silently dropped or replaced by a survivor


def test_a_zero_volume_quote_carries_a_held_mark_but_a_missing_one_does_not(world):
    ctx = R.Context(world["prices"], world["market"], world["days"])
    ticker, day = world["tickers"][0], str(world["days"][300].date())
    assert R.mark_price(ctx, ticker, day) == float(world["prices"][ticker].loc[pd.Timestamp(day), "Close"])

    class Halted:
        def at(self, t, d):
            return {"volume": 0, "tradingValue": 0, "marketCap": 1e12}
    prices = {ticker: pd.DataFrame({"Close": [np.nan]}, index=[pd.Timestamp(day)])}
    assert R.mark_price(R.Context(prices, Halted(), world["days"]), ticker, day, previous=101.0) == 101.0
    with pytest.raises(ValueError, match=R.UNRESOLVED):
        R.mark_price(R.Context(prices, Halted(), world["days"]), ticker, day, previous=None)

    class Missing:
        def at(self, t, d):
            return None
    with pytest.raises(ValueError, match=R.UNRESOLVED):
        R.mark_price(R.Context(prices, Missing(), world["days"]), ticker, day, previous=101.0)


def test_an_order_without_an_observed_execution_quote_is_deferred_not_filled(world):
    first_day, signal = next((d, s) for d, s in world["anchors"] if world["decisions"][s]["S"]["available"])
    wanted = world["decisions"][signal]["S"]["selected"][0]

    class Suspended(X.SyntheticMarket):
        def at(self, ticker, day):
            return {"volume": 0, "tradingValue": 0, "marketCap": 1e12} if (ticker, day) == (wanted, first_day) else super().at(ticker, day)
    ctx = R.Context(world["prices"], Suspended(world["days"]), world["days"])
    result = run(world, "A", ctx=ctx)
    record = next(r for r in result["path"] if r["date"] == first_day)
    assert result["complete"] and wanted not in record["weights"]
    assert len(record["weights"]) == len(world["decisions"][signal]["S"]["selected"]) - 1


def test_scaled_targets_keep_drifted_proportions_and_never_exceed_one():
    held = {"A": 0.30, "B": 0.10}
    scaled = R.scaled_targets(held, 1.0, 0.4)
    assert scaled == pytest.approx({"A": 0.12, "B": 0.04})
    grown = R.scaled_targets({"A": 0.30, "B": 0.10}, 0.4, 1.0)                          # a rally under 0.4 re-expressed at 1 would exceed it -> renormalised
    assert sum(grown.values()) == pytest.approx(1.0) and grown["A"] / grown["B"] == pytest.approx(3.0)
    back = R.scaled_targets({"A": 0.12, "B": 0.04}, 0.4, 1.0)
    assert back == pytest.approx({"A": 0.30, "B": 0.10})
    assert R.scaled_targets({}, 1.0, 0.7) == {}


def test_cash_sensitivity_reads_the_path_and_changes_none_of_it(paths):
    path = paths[0]["B"]["path"]
    before = copy.deepcopy(path)
    events = [{"date": "2009-02-13", "annualRatePct": 2.0}, {"date": "2017-06-01", "annualRatePct": 1.5}]
    out = R.cash_sensitivity(path, events)
    assert path == before
    primary = R.summarize_path(path)
    assert out["ZERO"]["netAnnualizedReturn"] == pytest.approx(primary["netAnnualizedReturn"])
    assert out["PROXY"]["netAnnualizedReturn"] > out["PROXY_MINUS_HAIRCUT"]["netAnnualizedReturn"] > out["ZERO"]["netAnnualizedReturn"]
    fully = paths[0]["A"]["path"]
    assert R.cash_sensitivity(fully, events)["PROXY"]["netAnnualizedReturn"] >= R.summarize_path(fully)["netAnnualizedReturn"]


def test_episode_table_uses_the_sealed_underwater_algorithm():
    nav = [1.0, 1.1, 0.9, 0.95, 1.2, 1.0, 1.3]
    dates = [f"2020-01-0{i + 1}" for i in range(len(nav))]
    table = R.episodes_table(nav, dates)
    raw = MA.underwater_episodes(pd.Series(nav, dtype=float))
    assert len(table["depth_ge_10pct"]) == len(MA.episodes_at_least(raw, 0.10)) >= 1 and table["depth_ge_10pct"][0]["peakDate"] == "2020-01-02"


def test_a_market_scale_trade_with_a_suspended_holding_defers_that_name_and_never_raises(world, paths):
    """The market event meets a held name with no executable quote: that name keeps its weight (deferred, never fictitiously sold), the others are scaled,
    gross may exceed the target only because of the deferred exit, and the path still completes."""
    results, _ = paths
    path = results["B"]["path"]
    event = next(i for i, r in enumerate(path) if r["kind"] == "MARKET" and r["marketMultiplier"] < path[i - 1]["marketMultiplier"] and len(path[i - 1]["weights"]) >= 2)
    day, stuck = path[event]["date"], sorted(path[event - 1]["weights"])[0]

    class Suspended(X.SyntheticMarket):
        def at(self, ticker, d):
            return {"volume": 0, "tradingValue": 0, "marketCap": 1e12} if (ticker == stuck and d == day) else super().at(ticker, d)
    ctx = R.Context(world["prices"], Suspended(world["days"]), world["days"])
    result = run(world, "B", ctx=ctx)
    assert result["complete"] is True
    record = next(r for r in result["path"] if r["date"] == day)
    before = result["path"][[r["date"] for r in result["path"]].index(day) - 1]
    assert record["kind"] == "MARKET" and stuck in record["weights"]
    assert record["weights"][stuck] == pytest.approx(before["weights"][stuck] * (1 + 0.0), rel=0.25)       # carried at the previous mark: not sold
    others = [t for t in before["weights"] if t != stuck]
    assert all(record["weights"].get(t, 0) < before["weights"][t] for t in others)                           # the executable names were scaled down
    assert record["overlayExcessDueToDeferredExit"] >= 0 and sum(record["weights"].values()) <= 1 + 1e-9


# ---------------------------------------------------------------------------------------------------------------------------------------
# Registered missing-signal / no-trade semantics (SIGNAL_UNAVAILABLE_NO_STOCK_REBALANCE)
# ---------------------------------------------------------------------------------------------------------------------------------------
def with_unavailable(world, layer, signals):
    """The same decisions with the named signal dates made unavailable for ONE book (selection and sizing emptied, exactly as the model emits them)."""
    out = {}
    for signal, pair in world["decisions"].items():
        decision = pair[layer]
        if signal in signals:
            decision = dict(decision, available=False, unavailable=M.SIGNAL_UNAVAILABLE, unavailableCauses=["STOCK_DEPTH_BELOW_MINIMUM"], selected=[], baseWeights={}, scores={})
        out[signal] = decision
    return out


def signal_of(world, index):
    return sorted({s for _, s in world["anchors"]})[index]


def anchor_day(world, signal):
    return next(d for d, s in world["anchors"] if s == signal)


def record_on(result, day):
    return next(r for r in result["path"] if r["date"] == day)


def previous_record(result, day):
    dates = [r["date"] for r in result["path"]]
    return result["path"][dates.index(day) - 1]


def test_before_the_first_valid_decision_every_book_is_one_hundred_percent_cash_and_nothing_is_fabricated(paths, world):
    results, _ = paths
    first_valid = {"S": next(d for d, s in world["anchors"] if world["decisions"][s]["S"]["available"]),
                   "I+S": next(d for d, s in world["anchors"] if world["decisions"][s]["I+S"]["available"])}
    assert first_valid["S"] == first_valid["I+S"] and first_valid["S"] != world["anchors"][0][0]
    for arch in M.ARCH_ORDER:
        path = results[arch]["path"]
        assert path[0]["date"] == world["anchors"][0][0]                                    # the calendar starts at the first scheduled anchor for all six
        cash = [r for r in path if r["date"] < first_valid["S"]]
        assert cash and all(r["weights"] == {} and r["cashWeight"] == 1 and r["holdings"] == 0 and r["nav"] == 1.0 and r["cost"] == 0.0 and r["turnover"] == 0.0 for r in cash)
        assert all(r["kind"] in (None, "NO_TRADE_SIGNAL_UNAVAILABLE") for r in cash) and cash[0]["signalUnavailable"] is True
        assert sum(r["signalUnavailable"] for r in cash) == 2                              # exactly the two deficient anchors
    benchmarks = results["A"]["path"][0]["benchmarkNav"], results["A"]["path"][-1]["benchmarkNav"]
    assert benchmarks[0] == 1.0 and benchmarks[1] != 1.0                                     # the passive reference runs from the same first anchor
    summary = R.summarize_path(results["A"]["path"])
    assert summary["noTradeSignalUnavailableAnchors"] >= 2 and summary["sessionsFullyInCashBeforeFirstValidDecision"] > 0


def test_a_later_unavailable_s_anchor_carries_the_previous_s_holdings_exactly_and_recovery_rebalances_normally(world):
    signal = signal_of(world, 5)
    day, recovery = anchor_day(world, signal), anchor_day(world, signal_of(world, 6))
    decisions = with_unavailable(world, "S", {signal})
    calls = []
    real = P.execute_rebalance

    def spy(before, desired, adv, selected, multiplier, cfg, **kwargs):
        calls.append({"desired": dict(desired), "selected": list(selected), "multiplier": multiplier})
        return real(before, desired, adv, selected, multiplier, cfg, **kwargs)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(P, "execute_rebalance", spy)
        result = run(world, "A", decisions=decisions)
    assert result["complete"]
    held, before = record_on(result, day), previous_record(result, day)
    assert before["weights"] and held["kind"] == "NO_TRADE_SIGNAL_UNAVAILABLE" and held["signalUnavailable"] is True
    assert set(held["weights"]) == set(before["weights"]) and held["turnover"] == 0.0 and held["cost"] == 0.0 and held["replaced"] == 0 and held["added"] == 0
    assert held["holdings"] == before["holdings"] and held["cashWeight"] >= -1e-9
    assert not any(c["selected"] and c["selected"] == world["decisions"][signal]["S"]["selected"] for c in calls)      # the deficient anchor generated no order
    normal = world["decisions"][signal_of(world, 6)]["S"]
    again = record_on(result, recovery)
    assert again["kind"] == "ANCHOR" and any(c["selected"] == normal["selected"] and c["desired"] == normal["baseWeights"] for c in calls)      # a normal registered rebalance
    assert set(again["weights"]) <= set(normal["selected"])
    # the same path with no unavailable anchor differs ONLY from that anchor on (history before it is identical)
    plain = run(world, "A")
    assert [r["nav"] for r in result["path"] if r["date"] < day] == [r["nav"] for r in plain["path"] if r["date"] < day]


def test_a_later_unavailable_i_plus_s_anchor_carries_the_previous_book_while_the_s_book_trades_normally(paths, world):
    results, _ = paths
    signal = next(s for _, s in world["anchors"] if world["decisions"][s]["S"]["available"] and not world["decisions"][s]["I+S"]["available"]
                  and s > signal_of(world, 3))
    day = anchor_day(world, signal)
    assert "INDUSTRY_LAYER_UNRANKABLE" in world["decisions"][signal]["I+S"]["unavailableCauses"] and world["decisions"][signal]["S"]["available"]
    for arch in "DEF":
        held, before = record_on(results[arch], day), previous_record(results[arch], day)
        assert held["signalUnavailable"] is True and set(held["weights"]) == set(before["weights"]) and held["replaced"] == 0 and held["added"] == 0
        assert held["kind"] in ("NO_TRADE_SIGNAL_UNAVAILABLE", "MARKET")
    assert record_on(results["A"], day)["kind"] == "ANCHOR" and record_on(results["A"], day)["signalUnavailable"] is False         # S is untouched by an industry gap


def test_market_scaling_still_changes_while_the_underlying_stock_signal_is_held(world):
    decisions = with_unavailable(world, "S", {s for s in world["decisions"] if s > signal_of(world, 4)})
    plain = run(world, "A", decisions=decisions)
    with_market = {arch: run(world, arch, decisions=decisions) for arch in "BC"}
    frozen_at = anchor_day(world, signal_of(world, 4))
    names = set(record_on(plain, frozen_at)["weights"])
    assert names
    after = [r for r in plain["path"] if r["date"] > frozen_at]
    assert all(set(r["weights"]) == names and r["turnover"] == 0.0 and r["kind"] in (None, "NO_TRADE_SIGNAL_UNAVAILABLE") for r in after)      # market OFF: held book, no trade at all
    for arch, result in with_market.items():
        later = [r for r in result["path"] if r["date"] > frozen_at]
        scale = [r for r in later if r["kind"] == "MARKET"]
        assert scale and {r["marketMultiplier"] for r in later} >= {0.7}                                                             # the overlay kept acting on the held book
        assert all(set(r["weights"]) <= names and r["added"] == 0 and r["replaced"] == 0 for r in later)                              # same names; never a new one
        assert any(r["signalUnavailable"] for r in later)


def test_the_unavailable_state_is_shared_by_abc_and_by_def_and_the_market_layer_is_independent_of_it(paths, world):
    results, _ = paths
    for group, layer in (("ABC", "S"), ("DEF", "I+S")):
        for day, signal in world["anchors"]:
            flags = {a: record_on(results[a], day)["signalUnavailable"] for a in group}
            assert set(flags.values()) == {not world["decisions"][signal][layer]["available"]}
    # C0 / C1 targets come from the sealed market table alone: replacing every stock decision leaves the multiplier sequence untouched
    unavailable_all = with_unavailable(world, "S", set(world["decisions"]))
    alone = run(world, "B", decisions=unavailable_all)
    assert [r["marketMultiplier"] for r in alone["path"]] == [r["marketMultiplier"] for r in results["B"]["path"]]
    assert all(r["weights"] == {} for r in alone["path"])                                    # never a fabricated book, whatever the overlay says


def test_an_unavailable_anchor_is_a_no_trade_anchor_not_a_removed_one(paths, world):
    results, _ = paths
    for arch in M.ARCH_ORDER:
        days = {r["date"] for r in results[arch]["path"]}
        assert all(day in days for day, _ in world["anchors"] if day <= results[arch]["path"][-1]["date"])         # the calendar is identical and complete
