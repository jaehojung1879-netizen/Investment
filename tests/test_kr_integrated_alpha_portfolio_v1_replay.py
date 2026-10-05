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
    anchor_days = {a: [r["date"] for r in results[a]["path"] if r["kind"] == "ANCHOR"] for a in M.ARCH_ORDER}
    assert all(anchor_days[a] == anchor_days["A"] for a in anchor_days) and anchor_days["A"][0] == dates["A"][0]


def test_the_underlying_decision_is_shared_and_the_market_only_scales_it(paths, world):
    results, calls = paths
    by_arch = {a: [c for c in calls if c["arch"] == a] for a in M.ARCH_ORDER}
    for group, layer in (("ABC", "S"), ("DEF", "I+S")):
        anchor_calls = {a: [c for c in by_arch[a] if c["selected"]] for a in group}
        signals = [s for _, s in world["anchors"]]
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
    first_day, signal = world["anchors"][0]
    wanted = world["decisions"][signal]["S"]["selected"][0]

    class Suspended(X.SyntheticMarket):
        def at(self, ticker, day):
            return {"volume": 0, "tradingValue": 0, "marketCap": 1e12} if (ticker, day) == (wanted, first_day) else super().at(ticker, day)
    ctx = R.Context(world["prices"], Suspended(world["days"]), world["days"])
    result = run(world, "A", ctx=ctx)
    assert result["complete"] and wanted not in result["path"][0]["weights"]
    assert len(result["path"][0]["weights"]) == len(world["decisions"][signal]["S"]["selected"]) - 1


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
