"""kr-integrated-alpha-portfolio-v1 post-outcome concentration audit: synthetic fixtures for the arithmetic, plus checks of the committed diagnostic outputs.

No test reads the formal result artifact or the raw snapshot (neither is reachable from CI); the reconstruction half is exercised on the repository's invented
six-path world. Nothing here computes a historical portfolio outcome, touches an execution lock or reruns a sealed study."""
import ast
import json
import math
from pathlib import Path
import re

import numpy as np
import pandas as pd
import pytest
from pipeline import kr_integrated_alpha_portfolio as M
from pipeline import kr_integrated_alpha_portfolio_execution as E
from pipeline import kr_integrated_alpha_portfolio_postoutcome_audit as A
from pipeline import kr_integrated_alpha_portfolio_postoutcome_completed as C
from pipeline import kr_integrated_alpha_portfolio_postoutcome_full as FULL
from pipeline import kr_integrated_alpha_portfolio_replay as R

ROOT = Path(__file__).resolve().parents[1]
RESULT_JSON = ROOT / "docs/results/kr-integrated-alpha-portfolio-v1-postoutcome-concentration-audit.json"
REPORT_MD = ROOT / "docs/kr-integrated-alpha-portfolio-v1-postoutcome-concentration-audit.md"
COMPLETED_JSON = ROOT / "docs/results/kr-integrated-alpha-portfolio-v1-postoutcome-completed-audit.json"
STALE_HANDOFF_DIGEST_PREFIX = "b316a6ef11dcee"           # a transcription error in a handoff message; it must not appear in any new documentation
WORKFLOW = (ROOT / ".github/workflows/kr-integrated-alpha-portfolio-v1-postoutcome-audit.yml").read_text()
AUDIT_FILES = ("pipeline/kr_integrated_alpha_portfolio_postoutcome_audit.py", "pipeline/kr_integrated_alpha_portfolio_postoutcome_full.py",
               "pipeline/kr_integrated_alpha_portfolio_postoutcome_completed.py", "pipeline/kr_integrated_alpha_portfolio_postoutcome_report.py",
               "scripts/run_kr_integrated_alpha_portfolio_postoutcome_audit.py")


def sessions(start="2017-01-16", end="2026-09-14"):
    return [str(d.date()) for d in pd.bdate_range(start, end)]


def levels_with(daily_returns, days):
    return pd.Series(np.cumprod(1 + np.asarray(daily_returns)) * 100.0, index=days)


# ---------------------------------------------------------------------------------------------------------------------------------------
# Period arithmetic
# ---------------------------------------------------------------------------------------------------------------------------------------
def test_the_three_sub_spans_chain_into_the_full_window_and_the_shares_add_up():
    days = sessions()
    rng = np.random.default_rng(1)
    lv = levels_with(rng.normal(0.0005, 0.01, len(days)), days)
    rows = {r["period"]: r for r in A.period_decomposition(lv, days[0], days[-1])}
    chained = (1 + rows["A_2017_to_2024"]["cumulativeReturn"]) * (1 + rows["B_2025"]["cumulativeReturn"]) * (1 + rows["C_2026_to_cutoff"]["cumulativeReturn"])
    assert chained == pytest.approx(1 + rows["D_full_window"]["cumulativeReturn"], rel=1e-12)
    assert sum(rows[k]["logShareOfTerminalWealth"] for k in ("A_2017_to_2024", "B_2025", "C_2026_to_cutoff")) == pytest.approx(1.0, abs=1e-12)
    assert sum(rows[k]["shareOfTerminalGain"] for k in ("A_2017_to_2024", "B_2025", "C_2026_to_cutoff")) == pytest.approx(1.0, abs=1e-12)
    assert rows["D_full_window"]["logShareOfTerminalWealth"] == pytest.approx(1.0)
    assert rows["D_full_window"]["sessions"] == len(days) - 1


def test_the_span_boundaries_are_the_last_sessions_of_2024_and_2025_and_short_spans_are_not_annualized():
    days = [d for d in sessions() if d not in ("2024-12-31", "2025-12-31")]                 # a calendar whose year-ends are not sessions
    lv = pd.Series(np.linspace(100, 300, len(days)), index=days)
    spans = {s[0]: s for s in A.period_spans(days)}
    assert spans["A_2017_to_2024"][3] == "2024-12-30" and spans["B_2025"][2] == "2024-12-30" and spans["B_2025"][3] == "2025-12-30" and spans["C_2026_to_cutoff"][2] == "2025-12-30"
    rows = {r["period"]: r for r in A.period_decomposition(lv, days[0], days[-1])}
    assert rows["C_2026_to_cutoff"]["annualizedReturn"] is None and rows["C_2026_to_cutoff"]["annualizationNote"] == "SPAN_SHORTER_THAN_ONE_YEAR_NOT_ANNUALIZED"
    assert rows["A_2017_to_2024"]["annualizedReturn"] is not None and rows["B_2025"]["annualizedReturn"] is not None          # a year-end to year-end span is a year
    assert rows["B_2025"]["annualizedReturn"] == pytest.approx(rows["B_2025"]["cumulativeReturn"], abs=2e-3)
    formula = (lv[days[-1]] / lv[days[0]]) ** (1 / ((pd.Timestamp(days[-1]) - pd.Timestamp(days[0])).days / 365.2425)) - 1
    assert rows["D_full_window"]["annualizedReturn"] == pytest.approx(formula, rel=1e-12)


def test_calendar_year_returns_start_each_year_from_the_prior_year_end_and_the_first_from_the_window_start():
    days = sessions()
    lv = pd.Series(np.arange(1, len(days) + 1, dtype=float), index=days)
    out = A.calendar_year_returns(lv, days[0], days[-1])
    assert out["2017"]["fromSession"] == days[0] and out["2018"]["fromSession"] == "2017-12-29" and out["2026"]["toSession"] == days[-1]
    assert out["2019"]["return"] == pytest.approx(lv[out["2019"]["toSession"]] / lv["2018-12-31"] - 1)


# ---------------------------------------------------------------------------------------------------------------------------------------
# Benchmark integrity and the cross-check
# ---------------------------------------------------------------------------------------------------------------------------------------
def test_integrity_detects_missing_extra_and_extreme_sessions_without_editing_them():
    days = sessions("2017-01-02", "2017-03-31")
    lv = pd.Series(np.linspace(100, 110, len(days)), index=days)
    lv = lv.drop(days[10])
    lv["2017-03-05"] = 105.0                                                     # a weekend: not in the calendar
    lv[days[30]] = lv[days[29]] * 1.25
    report = A.benchmark_integrity(lv, days, start=days[0], cutoff=days[-1])
    assert report["sessionsMissingFromSeries"] == [days[10]] and report["sessionsNotInCalendar"] == ["2017-03-05"] and report["nonPositiveOrNonFiniteLevels"] == 0
    assert any(abs(m["return"] - 0.25) < 0.02 for m in report["dailyMovesAtLeast10Percent"])
    assert report["largestDailyMoveInWindow"]["return"] > 0.2


def test_tracking_cross_check_recovers_a_known_constant_accrual_over_a_price_index():
    days = sessions("2017-01-02", "2026-09-14")
    rng = np.random.default_rng(3)
    index = levels_with(rng.normal(0.0004, 0.01, len(days)), days)
    accrual = 1.045 ** (np.arange(len(days)) / 252)
    bench = index * accrual
    out = A.tracking_cross_check(bench, index, {"ref": index * 1.018 ** (np.arange(len(days)) / 252)}, start=days[0], cutoff=days[-1])
    span = out["span2017To2024"]
    assert span["benchmarkOverIndexRelativePerYear"] == pytest.approx(0.045, abs=2e-3) and span["refOverIndexRelativePerYear"] == pytest.approx(0.018, abs=2e-3)
    assert out["byCalendarYear"]["2020"]["benchmarkOverIndexRelative"] == pytest.approx(0.045, abs=3e-3)


# ---------------------------------------------------------------------------------------------------------------------------------------
# Concentration shares and reference portfolios
# ---------------------------------------------------------------------------------------------------------------------------------------
def universe(dates, caps_by_date):
    rows = []
    for d, caps in zip(dates, caps_by_date):
        for rank, (ticker, cap) in enumerate(sorted(caps.items(), key=lambda kv: -kv[1]), start=1):
            rows.append({"date": d, "ticker": ticker, "marketCap": cap, "rank": rank})
    return pd.DataFrame(rows)


def test_snapshot_shares_use_only_the_top_n_and_threshold_runs_are_contiguous():
    caps = [{"005930.KS": 60, "000660.KS": 10, "X.KS": 30}, {"005930.KS": 60, "000660.KS": 30, "X.KS": 10}, {"005930.KS": 20, "000660.KS": 10, "X.KS": 70},
            {"005930.KS": 70, "000660.KS": 10, "X.KS": 20}]
    dates = ["2017-01-02", "2017-02-01", "2017-03-02", "2017-04-03"]
    snaps = A.concentration_snapshots(universe(dates, caps))
    assert list(snaps.combined.round(6)) == [0.7, 0.9, 0.3, 0.8]
    top2 = A.concentration_snapshots(universe(dates, caps), top_n=2)
    assert top2.combined.iloc[0] == pytest.approx(60 / 90) and top2.members.iloc[0] == 2          # SK Hynix (rank 3) is outside the top 2
    thr = A.share_thresholds(snaps, start="2017-01-01")["formalWindow"]
    assert thr["maximum"] == pytest.approx(0.9) and thr["maximumDate"] == "2017-02-01" and thr["median"] == pytest.approx(0.75)
    assert thr["thresholds"]["0.60"]["snapshotsAbove"] == 3 and [(r["from"], r["to"]) for r in thr["thresholds"]["0.60"]["runs"]] == [("2017-01-02", "2017-02-01"), ("2017-04-03", "2017-04-03")]
    assert thr["thresholds"]["0.60"]["first"] == "2017-01-02" and thr["thresholds"]["0.60"]["last"] == "2017-04-03"


def test_checkpoint_rows_never_use_a_later_snapshot():
    snaps = A.concentration_snapshots(universe(["2017-01-02", "2017-03-02"], [{"005930.KS": 1, "000660.KS": 1, "X.KS": 2}, {"005930.KS": 3, "000660.KS": 1, "X.KS": 0.0001}]))
    rows = A.snapshot_table(snaps, ["2017-02-28", "2016-12-31"])
    assert rows[0]["snapshot"] == "2017-01-02" and rows[1]["snapshot"] is None


def reference_world():
    days = sessions("2017-01-02", "2017-06-30")
    prices = pd.DataFrame({"005930.KS": 100 * np.cumprod(1 + np.full(len(days), 0.002)), "000660.KS": 100 * np.cumprod(1 + np.full(len(days), 0.004)),
                           "A.KS": 100 * np.cumprod(1 + np.full(len(days), 0.001)), "B.KS": 100 * np.cumprod(1 - np.full(len(days), 0.001))}, index=days)
    firsts = [next(d for d in days if d[:7] == m) for m in ("2017-01", "2017-02", "2017-03", "2017-04", "2017-05", "2017-06")]
    caps = [{"005930.KS": 50.0, "000660.KS": 20.0, "A.KS": 20.0, "B.KS": 10.0}] * len(firsts)
    return days, prices, universe(firsts, caps)


def test_cap_reference_follows_hand_arithmetic_and_its_contributions_close_to_the_gain():
    days, prices, uni = reference_world()
    ref = A.reference_portfolio("CAP", prices, uni, days, track=tuple(prices.columns))
    nav, contrib = ref["nav"], ref["contribution"]
    assert nav.iloc[0] == 1.0
    day1 = (0.5 * 1.002 + 0.2 * 1.004 + 0.2 * 1.001 + 0.1 * 0.999)
    assert nav.iloc[1] == pytest.approx(day1, rel=1e-12)
    assert sum(float(s.sum()) for s in contrib.values()) == pytest.approx(nav.iloc[-1] - 1.0, abs=1e-12)
    assert ref["rebalances"] == 6 and ref["namesWithoutPriceAtRebalance"] == 0


def test_exclusion_renormalises_and_touches_nothing_else_and_equal_weight_is_one_over_n():
    days, prices, uni = reference_world()
    ex = A.reference_portfolio("CAP", prices, uni, days, exclude=A.NAMED)
    cap = A.reference_portfolio("CAP", prices, uni, days)
    day1 = (0.5 * 1.001 + 0.25 * 0.999)                                            # A 20 and B 10 renormalised to 2/3 and 1/3 -> but both are 1.001 / 0.999
    assert ex["nav"].iloc[1] == pytest.approx((2 / 3) * 1.001 + (1 / 3) * 0.999, rel=1e-12) and day1 != ex["nav"].iloc[1]
    assert ex["contribution"]["005930.KS"].abs().sum() == 0 and cap["contribution"]["005930.KS"].abs().sum() > 0
    eq = A.reference_portfolio("EQUAL", prices, uni, days)
    assert eq["nav"].iloc[1] == pytest.approx(0.25 * (1.002 + 1.004 + 1.001 + 0.999), rel=1e-12)
    with pytest.raises(ValueError, match="UNREGISTERED_REFERENCE_KIND"):
        A.reference_portfolio("OTHER", prices, uni, days)


def test_a_name_without_a_price_at_the_rebalance_is_skipped_and_counted_never_filled():
    days, prices, uni = reference_world()
    prices = prices.copy()
    prices.loc[:, "B.KS"] = np.nan
    ref = A.reference_portfolio("CAP", prices, uni, days)
    assert ref["namesWithoutPriceAtRebalance"] == 6
    assert ref["nav"].iloc[1] == pytest.approx((0.5 * 1.002 + 0.2 * 1.004 + 0.2 * 1.001) / 0.9, rel=1e-12)


def test_contribution_periods_sum_to_the_whole_and_split_the_gain_between_named_and_residual():
    days = sessions("2017-01-16", "2026-09-14")
    n = len(days)
    prices = pd.DataFrame({"005930.KS": 100 * np.cumprod(1 + np.full(n, 0.001)), "000660.KS": 100 * np.cumprod(1 + np.full(n, 0.0015)), "A.KS": 100 * np.cumprod(1 + np.full(n, 0.0005))},
                          index=days)
    firsts = sorted({next(d for d in days if d[:7] == d2[:7]) for d2 in days})
    uni = universe(firsts, [{"005930.KS": 5.0, "000660.KS": 3.0, "A.KS": 2.0}] * len(firsts))
    ref = A.reference_portfolio("CAP", prices, uni, days)
    parts = A.contribution_by_period(ref, days[0], days[-1])
    gains = sum(parts[k]["gain"] for k in ("A_2017_to_2024", "B_2025", "C_2026_to_cutoff"))
    assert gains == pytest.approx(parts["D_full_window"]["gain"], rel=1e-12)
    for p in parts.values():
        assert p["combined"]["contributionNavUnits"] + p["residual"]["contributionNavUnits"] == pytest.approx(p["gain"], rel=1e-9)
        assert sum(s["shareOfSpanGain"] for s in p["securities"].values()) == pytest.approx(p["combined"]["shareOfSpanGain"])


# ---------------------------------------------------------------------------------------------------------------------------------------
# External evidence contract
# ---------------------------------------------------------------------------------------------------------------------------------------
def test_an_external_record_needs_every_field_and_a_labelled_basis_and_unlike_bases_are_never_compared_silently():
    good = dict(sourceId="S", url="https://x", issuer="I", publicationDate="2026-09-30", measurementDate="2026-09-14", metricName="YTD", basis="DISTRIBUTION_REINVESTED_RETURN",
                retrievalDate="2026-10-05", basisLimitations="none", value=0.7)
    assert A.external_source_record(**good)["value"] == 0.7
    with pytest.raises(ValueError, match="EXTERNAL_SOURCE_FIELD_MISSING"):
        A.external_source_record(**{k: v for k, v in good.items() if k != "publicationDate"})
    with pytest.raises(ValueError, match="BASIS_UNLABELLED"):
        A.external_source_record(**dict(good, basis="PRICE"))
    with pytest.raises(ValueError, match="VALUE_MISSING"):
        A.external_source_record(**dict(good, value=None))
    assert A.external_source_record(**dict(good, value=None, retrievalStatus="UNREACHABLE"))["value"] is None
    assert A.reconcile_checkpoint(0.75, None, "TOTAL_RETURN", None)["status"] == A.EXTERNAL_UNRESOLVED
    assert A.reconcile_checkpoint(0.75, 0.70, "TOTAL_RETURN", "MARKET_PRICE_RETURN")["status"] == "BASIS_DIFFERS"
    assert A.reconcile_checkpoint(0.75, 0.7497, "TOTAL_RETURN", "TOTAL_RETURN")["status"] == "MATCHES_WITHIN_REPORTING_TOLERANCE"
    assert A.reconcile_checkpoint(0.75, 0.70, "TOTAL_RETURN", "TOTAL_RETURN")["status"] == A.EXTERNAL_UNRESOLVED


# ---------------------------------------------------------------------------------------------------------------------------------------
# Reproduction gate
# ---------------------------------------------------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def world():
    return E.synthetic_world()


@pytest.fixture(scope="module")
def replayed(world):
    ctx = R.Context(world["prices"], world["market"], world["days"])
    decisions = {"S": {s: p["S"] for s, p in world["decisions"].items()}, "I+S": {s: p["I+S"] for s, p in world["decisions"].items()}}
    paths = {"A": R.replay_architecture("A", decisions["S"], world["anchors"], None, ctx), "D": R.replay_architecture("D", decisions["I+S"], world["anchors"], None, ctx)}
    assert paths["A"]["complete"] and paths["D"]["complete"]
    return {"ctx": ctx, "decisions": decisions, "paths": {k: v["path"] for k, v in paths.items()}}


def test_a_path_reproduces_itself_and_any_perturbation_is_reported_with_its_path(replayed):
    path = replayed["paths"]["D"]
    summary = R.summarize_path(path)
    nav = E.month_end_nav(path)
    formal = {k: summary[k] for k in A.SUMMARY_KEYS}
    ok = A.reproduction_check(formal, nav, R.summarize_path(path), E.month_end_nav(path))
    assert ok["reproduced"] is True and ok["firstDivergence"] is None and ok["divergenceCount"] == 0
    bad_nav = dict(nav)
    first = sorted(bad_nav)[3]
    bad_nav[first] = bad_nav[first] * (1 + 1e-6)
    broken = A.reproduction_check(formal, nav, summary, bad_nav)
    assert broken["reproduced"] is False and broken["firstDivergence"]["path"] == "monthEndNav/" + first
    tweaked = dict(summary, maxDrawdown=summary["maxDrawdown"] - 0.01)
    assert A.reproduction_check(formal, nav, tweaked, nav)["firstDivergence"]["path"] == "summary/maxDrawdown"
    within = A.reproduction_check(formal, nav, dict(summary, cumulativeNetReturn=summary["cumulativeNetReturn"] * (1 + 1e-12)), nav)
    assert within["reproduced"] is True                                           # float noise inside the stated tolerance is not a mismatch


# ---------------------------------------------------------------------------------------------------------------------------------------
# Attribution on a replayed path
# ---------------------------------------------------------------------------------------------------------------------------------------
def membership_for(world):
    tickers = world["tickers"]
    return {s: {t: "X%d" % (i // 2) for i, t in enumerate(tickers)} for s in world["decisions"]}


def test_security_attribution_closes_to_the_path_nav_and_cost_is_never_allocated_to_a_name(world, replayed):
    path = replayed["paths"]["D"]
    spans = A.record_spans(path)
    contributions, daily = A.security_contributions(path, lambda t, day, prev: R.mark_price(replayed["ctx"], t, day, prev), spans)
    full = contributions["D_full_window"]
    assert full["grossContributionNavUnits"] - full["transactionCostNavUnits"] == pytest.approx(path[-1]["nav"] - 1.0, abs=1e-9)
    assert full["cashContributionNavUnits"] == 0.0 and full["transactionCostNavUnits"] > 0
    assert sum(c["grossContributionNavUnits"] for k, c in contributions.items() if k != "D_full_window") == pytest.approx(full["grossContributionNavUnits"], abs=1e-9)
    assert sum(full["bySecurity"].values()) == pytest.approx(full["grossContributionNavUnits"], abs=1e-12) and len(full["top10Contributors"]) <= 10
    assert full["top10Contributors"][0]["contribution"] >= full["top10Detractors"][0]["contribution"]
    tampered = [dict(r) for r in path]
    tampered[-1] = dict(tampered[-1], nav=tampered[-1]["nav"] + 0.01)
    with pytest.raises(ValueError, match="ATTRIBUTION_DOES_NOT_CLOSE"):
        A.security_contributions(tampered, lambda t, day, prev: R.mark_price(replayed["ctx"], t, day, prev), spans)


def test_holdings_concentration_and_named_exposure_are_counted_from_the_records(world, replayed):
    path = replayed["paths"]["D"]
    industry_of = A.industry_map_provider(membership_for(world), world["anchors"], path)
    conc = A.holdings_concentration(path, industry_of)
    full = conc["D_full_window"]
    assert full["sessions"] == len(path) and sum(full["holdingsHistogram"].values()) == len(path)
    assert full["holdingsHistogram"]["0"] > 0                                    # the invented world starts in cash (registered no-trade anchors)
    assert 0 < full["meanHhi"] <= 1 and full["maximumLargestNameWeightOfNav"] <= 0.3 + 1e-9 and 0 < full["meanTopIndustryShareOfInvested"] <= 1
    tickers = tuple(world["tickers"][:2])
    exposure = A.named_exposure(path, tickers)["D_full_window"]
    held = sum(1 for r in path if any(r["weights"].get(t, 0) > 0 for t in tickers))
    assert exposure["sessionsEitherHeld"] == held and exposure["sessionsBothHeld"] <= held
    assert exposure["maximumCombinedWeight"] <= 0.6 + 1e-9
    spans = A.record_spans(path)
    contributions, daily = A.security_contributions(path, lambda t, day, prev: R.mark_price(replayed["ctx"], t, day, prev), spans)
    by_industry = A.industry_contributions(daily, industry_of, spans)["D_full_window"]["byIndustry"]
    assert sum(by_industry.values()) == pytest.approx(contributions["D_full_window"]["grossContributionNavUnits"], abs=1e-12)


def test_the_industry_a_holding_carries_is_the_one_at_the_decision_that_selected_it(world, replayed):
    path = replayed["paths"]["D"]
    tickers = world["tickers"]
    first_signal = {day: s for day, s in world["anchors"]}
    table = {s: {t: "OLD" for t in tickers} for s in world["decisions"]}
    changed = sorted(world["decisions"])[-3]
    table[changed] = {t: "NEW" for t in tickers}
    provider = A.industry_map_provider(table, world["anchors"], path)
    anchor_days = [r["date"] for r in path if r["kind"] == "ANCHOR"]
    day = next(d for d in anchor_days if first_signal[d] == changed)
    newly = [t for t in path[[r["date"] for r in path].index(day)]["weights"] if t not in path[[r["date"] for r in path].index(day) - 1]["weights"]]
    for t in newly:
        assert provider(day, t) == "NEW"
    carried = [t for t in path[[r["date"] for r in path].index(day)]["weights"] if t in path[[r["date"] for r in path].index(day) - 1]["weights"]]
    for t in carried:
        assert provider(day, t) == "OLD"                                         # a retained name keeps the identity it was selected under
    assert provider(path[0]["date"], "NOT.HELD") == "UNCLASSIFIED"


def test_d_minus_a_names_overlap_returns_and_costs_are_reported_by_fixed_span(world, replayed):
    pa, pd_ = replayed["paths"]["A"], replayed["paths"]["D"]
    spans = A.record_spans(pd_)
    cont = {}
    for arch, path in (("A", pa), ("D", pd_)):
        cont[arch], _ = A.security_contributions(path, lambda t, day, prev: R.mark_price(replayed["ctx"], t, day, prev), spans)
    out = A.d_minus_a(replayed["decisions"]["S"], replayed["decisions"]["I+S"], world["anchors"], pa, pd_, cont["A"], cont["D"], spans)["D_full_window"]
    assert out["returnDMinusA"] == pytest.approx(pd_[-1]["nav"] - pa[-1]["nav"], abs=1e-9)
    assert 0 <= out["meanSameNameShare"] <= 1 and out["anchorsBothBooksHadAValidDecision"] < len(world["anchors"])          # no-trade anchors are excluded from overlap
    assert out["grossContributionDifferenceNavUnits"] == pytest.approx(cont["D"]["D_full_window"]["grossContributionNavUnits"] - cont["A"]["D_full_window"]["grossContributionNavUnits"])
    diff_sum = sum(v["difference"] for v in out["topNamesAddingToDMinusA"]) + sum(v["difference"] for v in out["topNamesSubtractingFromDMinusA"])
    assert math.isfinite(diff_sum)


# ---------------------------------------------------------------------------------------------------------------------------------------
# The one authorised counterfactual
# ---------------------------------------------------------------------------------------------------------------------------------------
def test_the_exclusion_drops_the_named_names_after_scoring_before_selection_and_restores_the_frozen_function():
    original = M.decision_rows
    frame = pd.DataFrame([{"date": "2020-01-03", "industry": "X", "ticker": t, "bookToMarketProxy": 1.0 + i, "earningsYieldProxy": 0.1 * i, "negativeDownsideVol126": -0.2 + 0.01 * i,
                           "tradable": True, "adv60": 6e9, "downsideVol126": 0.2} for i, t in enumerate(["005930.KS", "000660.KS", "A.KS", "B.KS", "C.KS", "D.KS", "E.KS", "F.KS"])])
    scored = M.stock_scores(frame)
    industry_map = {"X": {"INDUSTRY_SCORE": 0.6}}
    before = M.decision_rows(scored, industry_map)
    with A.exclude_named_from_selection():
        during = M.decision_rows(scored, industry_map)
    assert M.decision_rows is original
    assert {r["ticker"] for r in before} - {r["ticker"] for r in during} == set(A.NAMED)
    assert [r for r in before if r["ticker"] not in A.NAMED] == during                 # every remaining score is exactly what the frozen model computed
    try:
        with A.exclude_named_from_selection():
            raise RuntimeError("x")
    except RuntimeError:
        pass
    assert M.decision_rows is original                                               # restored even on error


def test_the_named_securities_are_exactly_the_two_registered_ones():
    assert A.NAMED == ("005930.KS", "000660.KS") and set(A.NAMED_SECURITIES.values()) == {"Samsung Electronics", "SK Hynix"}


# ---------------------------------------------------------------------------------------------------------------------------------------
# The local result and its language discipline
# ---------------------------------------------------------------------------------------------------------------------------------------
def tiny_local_result():
    days = sessions("2016-12-01", "2026-09-14")
    n = len(days)
    rng = np.random.default_rng(5)
    prices = pd.DataFrame({t: 100 * np.cumprod(1 + rng.normal(0.0004, 0.01, n)) for t in ("005930.KS", "000660.KS", "A.KS", "B.KS")}, index=days)
    firsts = sorted({next(d for d in days if d[:7] == x[:7]) for x in days})
    uni = universe(firsts, [{"005930.KS": 5.0, "000660.KS": 3.0, "A.KS": 1.5, "B.KS": 1.0}] * len(firsts))
    bench = levels_with(rng.normal(0.0006, 0.009, n), days)
    index = levels_with(rng.normal(0.0004, 0.009, n), days)
    evidence = A.sealed_anatomy_evidence((ROOT / "docs/results/kr-industry-opportunity-anatomy-v1-report.md").read_text(),
                                         (ROOT / "docs/results/kr-stock-within-industry-anatomy-v1-report.md").read_text(), {})
    window = [d for d in days if A.WINDOW_START <= d <= A.CUTOFF]
    result = A.build_local_result(benchmark=bench, index_levels=index, close=prices, universe=uni, sessions=window, calendar_sessions=days, identities={"synthetic": True},
                                  sealed_evidence=evidence, observed_github_state={"synthetic": True})
    result["notRunSections"] = A.not_run_sections()
    result["questionMatrix"] = A.question_matrix(result)
    return result


def test_the_local_result_is_complete_clean_and_renders_without_recomputing():
    result = tiny_local_result()
    A.assert_clean_language(result)
    text = A.markdown_report(json.loads(json.dumps(result)))
    assert text.startswith("# KR integrated alpha portfolio v1") and "POST-OUTCOME DESCRIPTIVE DIAGNOSTIC ONLY" in text
    assert len(result["questionMatrix"]) == 10 and all(q["classification"] in A.CLASSIFICATIONS for q in result["questionMatrix"])
    assert set(result["notRunSections"]) >= {"dPathReconstruction", "dExcludeSamsungHynixSensitivity", "dMinusAChronology"}
    assert all(v["status"] == A.NOT_RUN for v in result["notRunSections"].values())
    assert result["externalReconciliation"]["status"] == A.EXTERNAL_UNRESOLVED and all(s["value"] is None for s in result["externalReconciliation"]["sourcesAttempted"])
    assert [r["period"] for r in result["benchmarkPeriods"]["levels"]] == [p for p, _ in A.PERIOD_LABELS]


def test_language_discipline_rejects_promotion_and_pass_fail_vocabulary():
    for key in ("winnerArchitecture", "bestFactor", "promotionEligible", "passFail", "recommendedPortfolio", "validatedModel"):
        with pytest.raises(ValueError, match="FORBIDDEN_LANGUAGE_IN_KEY"):
            A.assert_clean_language({"a": [{key: 1}]})
    with pytest.raises(ValueError, match="UNREGISTERED_CLASSIFICATION"):
        A.question_entry("q", "PASS", "e", "b")
    assert set(A.CLASSIFICATIONS) == {"SUPPORTED_BY_AUDIT", "PARTIALLY_SUPPORTED", "NOT_SUPPORTED", "UNRESOLVED_DATA_LIMITATION"}


def test_sealed_anatomy_facts_are_parsed_from_the_committed_reports_and_keep_the_two_questions_apart():
    ev = A.sealed_anatomy_evidence((ROOT / "docs/results/kr-industry-opportunity-anatomy-v1-report.md").read_text(),
                                   (ROOT / "docs/results/kr-stock-within-industry-anatomy-v1-report.md").read_text(), {})
    rel = ev["industryAnatomy_FULL_vs_EXCLUDE_vs_LEAVE_LARGEST_OUT"]["features"]["REL_MOM_126"]
    assert rel["FULL"] == {"icMean": 0.066, "tercileSpreadPp": 5.4, "icDates": 404, "tercileDates": 294}
    assert rel["EXCLUDE_SAMSUNG_ELECTRONICS_AND_SK_HYNIX"]["tercileSpreadPp"] == 5.4 and rel["LEAVE_LARGEST_CONSTITUENT_OUT"]["tercileSpreadPp"] == 0.1
    breadth = ev["industryAnatomy_FULL_vs_EXCLUDE_vs_LEAVE_LARGEST_OUT"]["features"]["BREADTH_ABOVE_MA_126"]
    assert breadth["FULL"]["tercileSpreadPp"] == 3.2 and breadth["EXCLUDE_SAMSUNG_ELECTRONICS_AND_SK_HYNIX"]["icMean"] == 0.042
    stock = ev["stockWithinIndustryAnatomy_FULL_vs_EXCLUDE"]["features"]
    assert stock["bookToMarketProxy"] == {"FULL_CAP_H126": 0.086, "EXCLUDE_SAMSUNG_ELECTRONICS_AND_SK_HYNIX_CAP_H126": 0.087}
    assert stock["negativeDownsideVol126"]["FULL_CAP_H126"] == 0.062 and set(stock) == set(A.STOCK_FEATURES)
    assert "NOT ANSWERED" in ev["interpretation"]["B_implementedConcentratedPortfolioDependsOnThem"]
    assert ev["provenance"]["studiesRerun"] is False


# ---------------------------------------------------------------------------------------------------------------------------------------
# Safety: the audit cannot touch the one-shot machinery
# ---------------------------------------------------------------------------------------------------------------------------------------
FORBIDDEN_NAMES = {"claim_execution_lock", "write_execution_marker", "load_market_values", "authorize_execution", "execute", "ExecutionLock", "ExecutionPermit", "github_api",
                   "lock_exists", "write_outputs", "atomic_write"}


@pytest.mark.parametrize("rel", AUDIT_FILES)
def test_no_audit_file_references_the_lock_marker_permit_execute_or_github_write_machinery(rel):
    tree = ast.parse((ROOT / rel).read_text())
    used = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)} | {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert not (used & FORBIDDEN_NAMES), used & FORBIDDEN_NAMES
    source = (ROOT / rel).read_text()
    assert "docs/results/kr-integrated-alpha-portfolio-v1-result" not in source and "git/refs" not in source and '"POST"' not in source and "'POST'" not in source


def test_full_mode_refuses_a_formal_result_whose_bytes_differ(tmp_path):
    bogus = tmp_path / "integrated-alpha-portfolio.json"
    bogus.write_text("{}\n")
    with pytest.raises(ValueError, match="FORMAL_RESULT_BYTES_DIFFER"):
        FULL.verify_formal_result(bogus)
    with pytest.raises(ValueError, match="FULL_MODE_REQUIRES_INPUTS_AND_FORMAL_RESULT"):
        FULL.run(None, None, tmp_path)


def test_the_frozen_integrated_spec_and_model_files_are_unchanged():
    spec, sha = E.load_spec(ROOT)                                                    # raises if any pinned byte moved
    assert sha == A.FORMAL["specSha256"] and spec["studyId"] == M.STUDY
    assert A.FORMAL["lockRefs"][1].endswith(sha)


def test_the_audit_reads_the_formal_run_constants_the_task_pinned():
    assert A.FORMAL["workflowRunId"] == 37374530672 and A.FORMAL["executionSha"] == "33237df6d69e31a396959529378a0f881af9a58e"
    assert A.FORMAL["resultArtifactId"] == 11371812532 and A.FORMAL["rawInputArtifactId"] == 11157875265
    assert A.FORMAL["resultArtifactDigest"].endswith("bb29676403068b8330b12808ff30f6a5766fee35d4e66e96594591eaae766722")
    assert A.FORMAL["rawInputArtifactDigest"].endswith(E.load_spec(ROOT)[0]["input"]["artifactArchiveSha256"])           # the same digest the frozen spec pins for the raw input
    assert E.load_spec(ROOT)[0]["input"]["artifactId"] == A.FORMAL["rawInputArtifactId"] and E.load_spec(ROOT)[0]["input"]["artifactName"] == A.FORMAL["rawInputArtifactName"]


# ---------------------------------------------------------------------------------------------------------------------------------------
# The workflow
# ---------------------------------------------------------------------------------------------------------------------------------------
def test_the_audit_workflow_is_manual_read_only_and_cannot_write_a_lock_result_or_commit():
    on_block = WORKFLOW.split("\non:\n", 1)[1].split("\npermissions:", 1)[0]
    assert "workflow_dispatch" in on_block and "pull_request" not in on_block and "push:" not in on_block and "schedule" not in on_block
    perms = WORKFLOW.split("\npermissions:\n", 1)[1].split("\nconcurrency:", 1)[0]
    assert "contents: read" in perms and "actions: read" in perms and "write" not in perms
    assert "contents: write" not in WORKFLOW and "pull-requests: write" not in WORKFLOW
    for forbidden in ("git push", "git commit", "git tag", "createRef", "git.createRef", "deleteRef", "updateRef", "--mode execute", "run_kr_integrated_alpha_portfolio_v1.py", "POST /git/refs"):
        assert forbidden not in WORKFLOW, forbidden
    for pinned in ("37374530672", "33237df6d69e31a396959529378a0f881af9a58e", "11371812532", "sha256:bb29676403068b8330b12808ff30f6a5766fee35d4e66e96594591eaae766722",
                   "11157875265", "sha256:42eeb18b7a5c88816629036f472a93057b6a9be4768ad47292ba0d2750b4cce7", "36844599518"):
        assert pinned in WORKFLOW
    assert "listMatchingRefs" in WORKFLOW and "LOCK_REF_MISSING_OR_MOVED" in WORKFLOW and "FROZEN_FILES_CHANGED_SINCE_THE_EXECUTION_COMMIT" in WORKFLOW
    assert "--mode full" in WORKFLOW and "retention-days: 90" in WORKFLOW


# ---------------------------------------------------------------------------------------------------------------------------------------
# The committed diagnostic outputs
# ---------------------------------------------------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def committed():
    return json.loads(RESULT_JSON.read_text())


def test_the_committed_result_is_the_labelled_post_outcome_diagnostic_and_names_what_it_did_not_run(committed):
    assert committed["studyId"] == A.STUDY and committed["scientificStatus"] == A.SCIENTIFIC_STATUS and committed["statement"] == A.STATEMENT
    assert committed["formalIdentity"]["workflowRunId"] == 37374530672 and committed["formalIdentity"]["specSha256"] == A.FORMAL["specSha256"]
    A.assert_clean_language(committed)
    for section in ("benchmarkIntegrity", "benchmarkPassiveReproduction", "benchmarkPeriods", "priceIndexPeriods", "trackingCrossCheck", "concentrationProxy", "referencePortfolios",
                    "approximateBenchmarkContribution"):
        assert committed[section]["evidenceClass"] in A.EVIDENCE_CLASSES
    assert committed["concentrationProxy"]["label"] == "MARKET_CAP_SHARE_INSIDE_THE_PIT_TOP120_NOT_KODEX200_OR_KOSPI200_WEIGHT"
    assert committed["approximateBenchmarkContribution"]["label"] == "APPROXIMATE_WEIGHTED_CONTRIBUTION_USING_MONTHLY_WEIGHT_SNAPSHOTS"
    assert committed["referencePortfolios"]["notTheFormalBenchmark"] is True
    assert "notRunSections" not in committed and committed["completedAudit"]["evidenceClass"] == A.RECONSTRUCTION      # the artifact-dependent sections ran in Actions
    assert committed["externalReconciliation"]["status"] == A.EXTERNAL_UNRESOLVED
    assert committed["benchmarkIntegrity"]["sessionsMissingFromSeries"] == [] and committed["benchmarkIntegrity"]["nonPositiveOrNonFiniteLevels"] == 0
    assert committed["inputsVerified"]["universeShardsVerifiedAgainstPinnedGitBlobs"] == 14 and committed["inputsVerified"]["benchmarkDuplicateSessions"] == 0


def test_the_committed_benchmark_reproduces_the_quoted_passive_figure_and_the_fixed_spans_chain(committed):
    rep = committed["benchmarkPassiveReproduction"]
    assert rep["reproducesTheQuotedFormalFigureToFourDecimals"] is True and round(rep["reproducedPassiveAnnualizedReturn"], 4) == 0.2024
    assert rep["windowFirstSession"] == "2017-01-16" and rep["windowLastSession"] == "2026-09-14"
    rows = {r["period"]: r for r in committed["benchmarkPeriods"]["levels"]}
    chained = (1 + rows["A_2017_to_2024"]["cumulativeReturn"]) * (1 + rows["B_2025"]["cumulativeReturn"]) * (1 + rows["C_2026_to_cutoff"]["cumulativeReturn"]) - 1
    assert chained == pytest.approx(rows["D_full_window"]["cumulativeReturn"], rel=1e-9)
    assert rows["A_2017_to_2024"]["fromSession"] == "2017-01-16" and rows["A_2017_to_2024"]["toSession"] == "2024-12-30" and rows["B_2025"]["toSession"] == "2025-12-30"
    assert sum(rows[k]["logShareOfTerminalWealth"] for k in ("A_2017_to_2024", "B_2025", "C_2026_to_cutoff")) == pytest.approx(1.0, abs=1e-9)
    years = committed["benchmarkPeriods"]["calendarYears"]
    assert sorted(years) == [str(y) for y in range(2017, 2027)]
    assert (1 + years["2025"]["return"]) == pytest.approx(rows["B_2025"]["endLevel"] / rows["B_2025"]["startLevel"], rel=1e-9)


def test_the_committed_question_matrix_answers_q1_to_q10_with_only_the_four_registered_labels(committed):
    matrix = committed["questionMatrix"]
    assert len(matrix) == 10 and all(q["classification"] in A.CLASSIFICATIONS for q in matrix)
    by = {q["question"][:3].strip(". "): q["classification"] for q in matrix}
    assert by == {"Q1": A.SUPPORTED, "Q2": A.PARTIAL, "Q3": A.UNRESOLVED, "Q4": A.PARTIAL, "Q5": A.PARTIAL, "Q6": A.SUPPORTED, "Q7": A.PARTIAL, "Q8": A.SUPPORTED, "Q9": A.SUPPORTED, "Q10": A.SUPPORTED}
    assert not any(q["classification"] == A.UNRESOLVED and q["basis"] == A.NOT_RUN for q in matrix)           # nothing is left unresolved merely for want of the artifacts


def test_the_committed_report_is_exactly_rendered_from_the_committed_result(committed):
    assert REPORT_MD.read_text() == A.markdown_report(committed)
    text = REPORT_MD.read_text()
    assert "POST-OUTCOME DESCRIPTIVE DIAGNOSTIC ONLY" in text and "BENCHMARK_EXTERNAL_RECONCILIATION_UNRESOLVED" in text and "NOT_RUN_IN_THIS_ENVIRONMENT" not in text
    headings = re.findall(r"^## (\d+)\. ", text, re.M)
    assert headings == [str(i) for i in range(1, 15)]
    assert C.COMPLETED_RUN["fullAuditJsonSha256"] in text and "539,839 bytes" in text and "RECONSTRUCTION_REPRODUCES_THE_FORMAL_A_AND_D_PATHS" in text
    assert STALE_HANDOFF_DIGEST_PREFIX not in text and STALE_HANDOFF_DIGEST_PREFIX not in COMPLETED_JSON.read_text() and STALE_HANDOFF_DIGEST_PREFIX not in RESULT_JSON.read_text()
    assert "INDUSTRY_LAYER_DEVELOPMENT_SUPPORTED" in text and "NO_UNAMBIGUOUS_FINAL_ARCHITECTURE" in text and "MARKET_LAYER_PARETO_TRADE_OFF" in text
    assert "POST_OUTCOME_DESCRIPTIVE_SENSITIVITY" in text and "NOT_CONFIRMATORY" in text and "NOT_ELIGIBLE_FOR_MODEL_SELECTION" in text


def test_no_existing_result_file_and_no_frozen_artifact_is_touched_by_this_audit():
    sealed = ROOT / "docs/results"
    new = {RESULT_JSON.name, COMPLETED_JSON.name}
    existing = {p.name for p in sealed.glob("kr-integrated-alpha-portfolio-v1-*")}
    assert existing - new <= {"kr-integrated-alpha-portfolio-v1-readiness.json", "kr-integrated-alpha-portfolio-v1-prelock-availability-profile.json"}
    assert not (sealed / "kr-integrated-alpha-portfolio-v1-result.json").exists()           # the formal result was never committed by this audit


# ---------------------------------------------------------------------------------------------------------------------------------------
# The full-mode orchestration, on the invented world with the artifact-dependent steps replaced
# ---------------------------------------------------------------------------------------------------------------------------------------
def orchestration_setup(monkeypatch, world, replayed, tamper=False):
    summaries, nav = {}, {}
    for arch in ("A", "D"):
        summaries[arch] = dict(R.summarize_path(replayed["paths"][arch]), complete=True)
        nav[arch] = E.month_end_nav(replayed["paths"][arch])
    if tamper:
        key = sorted(nav["D"])[4]
        nav["D"] = dict(nav["D"], **{key: nav["D"][key] * (1 + 1e-5)})
    formal = {"specSha256": A.FORMAL["specSha256"], "summaries": summaries, "monthEndNav": nav, "window": {"anchors": len(world["anchors"])}}
    depth = {s: {"industriesRanked": p["I+S"]["industriesRanked"], "eligibleS": p["S"]["eligibleCount"], "eligibleIS": p["I+S"]["eligibleCount"]} for s, p in world["decisions"].items()}
    bundle = {"anchors": world["anchors"], "decisions": world["decisions"], "prices": world["prices"], "market": world["market"], "days": world["days"], "schedule": {}, "depth": depth}
    spec = {"benchmark": M.BENCHMARK, "input": {"identitySha256": "x" * 64}}
    monkeypatch.setattr(FULL, "verify_formal_result", lambda path, root=ROOT: (formal, spec, A.FORMAL["specSha256"]))
    monkeypatch.setattr(E.X, "input_identity", lambda root: {"sha256": "x" * 64})
    monkeypatch.setattr(E, "build_signal_bundle", lambda input_root, spec_, root, counters: bundle)
    monkeypatch.setattr(FULL, "membership_by_signal", lambda b, root: membership_for(world))


def test_full_mode_attributes_only_after_the_replay_reproduces_the_formal_a_and_d_paths(monkeypatch, tmp_path, world, replayed):
    orchestration_setup(monkeypatch, world, replayed)
    out = FULL.run("raw", "formal.json", tmp_path)
    assert out["status"] == "RECONSTRUCTION_REPRODUCES_THE_FORMAL_A_AND_D_PATHS"
    report = json.loads(Path(out["file"]).read_text())
    assert report["reproduction"]["architectures"]["A"]["reproduced"] and report["reproduction"]["architectures"]["D"]["reproduced"]
    assert set(report["attribution"]["architectures"]) == {"A", "D"} and "dMinusA" in report["attribution"]
    cf = report["counterfactual"]
    assert cf["name"] == "D_EXCLUDE_SAMSUNG_HYNIX" and cf["evidenceClass"] == A.COUNTERFACTUAL and cf["formalDecisionsUnchanged"] is True and cf["excluded"] == list(A.NAMED)
    assert cf["differenceVersusD"]["cumulativeNetReturn"] == pytest.approx(0.0, abs=1e-12)            # the stub bundle ignores the exclusion, so the sensitivity equals D here
    assert report["attribution"]["architectures"]["D"]["securityContributions"]["D_full_window"]["cashContributionNavUnits"] == 0.0
    d = report["attribution"]["architectures"]["D"]
    assert {"periodMetrics", "namedSecurities", "gainConcentration", "holdingSpells", "spellSummary"} <= set(d)
    assert set(d["namedSecurities"]["securities"]) == set(A.NAMED) and d["spellSummary"]["spells"] == len(d["holdingSpells"]) > 0
    pm = d["periodMetrics"]["D_full_window"]
    assert pm["cumulativeNetReturn"] == pytest.approx(d["periods"]["periods"][-1]["cumulativeReturn"], abs=1e-9)
    by = d["securityContributions"]["D_full_window"]
    assert sum(by["costAllocatedProportionalToTradedNotional"].values()) == pytest.approx(by["transactionCostNavUnits"], abs=1e-9)
    assert sum(sp["grossContributionNavUnits"] for sp in d["holdingSpells"]) == pytest.approx(by["grossContributionNavUnits"], abs=1e-9)
    assert "anchorsWithIdenticalSelection" in report["attribution"]["dMinusA"]["D_full_window"] and "consistencyWithPriorAuditFacts" in report["attribution"]
    assert not (tmp_path.parent / "docs").exists() and sorted(p.name for p in tmp_path.iterdir()) == ["postoutcome-audit-full.json"]


def test_full_mode_stops_with_the_first_divergence_and_attributes_nothing_when_the_replay_does_not_reproduce(monkeypatch, tmp_path, world, replayed):
    orchestration_setup(monkeypatch, world, replayed, tamper=True)
    out = FULL.run("raw", "formal.json", tmp_path)
    assert out["status"] == A.D_PATH_RECONSTRUCTION_MISMATCH
    report = json.loads(Path(out["file"]).read_text())
    assert report["attribution"] == A.NOT_RUN and "counterfactual" not in report
    assert report["firstDivergence"]["architecture"] == "D" and report["firstDivergence"]["path"].startswith("monthEndNav/")


# ---------------------------------------------------------------------------------------------------------------------------------------
# The completed audit: compact record, benchmark event audit, internal consistency of the committed numbers
# ---------------------------------------------------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def completed():
    return json.loads(COMPLETED_JSON.read_text())


def test_the_compact_record_refuses_any_file_that_is_not_the_completed_runs_exact_bytes():
    with pytest.raises(ValueError, match="FULL_AUDIT_JSON_DIFFERS_FROM_THE_COMPLETED_RUN"):
        C.verify_full_bytes(b"{}")
    with pytest.raises(ValueError, match="FULL_AUDIT_JSON_DIFFERS_FROM_THE_COMPLETED_RUN"):
        C.verify_full_bytes(b"x" * C.COMPLETED_RUN["fullAuditJsonBytes"])
    with pytest.raises(ValueError, match="AUDIT_DID_NOT_REPRODUCE_THE_FORMAL_PATHS"):
        C.compact({"status": A.D_PATH_RECONSTRUCTION_MISMATCH})


def test_the_compact_record_carries_the_runs_own_digest_and_no_stale_digest(completed):
    prov = completed["provenance"]
    assert prov == C.COMPLETED_RUN
    assert prov["workflowRunId"] == 37451761441 and prov["artifactId"] == 11406929754 and prov["fullAuditJsonBytes"] == 539839
    assert prov["fullAuditJsonSha256"] == "b316a6ef2ffbf77a0b4ce5646df5b7b6b0bfc079aa3a9e795727d0e7f7e39bbc"
    rec = completed["reconstruction"]
    assert rec["status"] == "RECONSTRUCTION_REPRODUCES_THE_FORMAL_A_AND_D_PATHS" and rec["tolerance"] == 1e-9
    assert all(r["reproduced"] and r["divergenceCount"] == 0 and r["monthEndNavDates"] == 117 for r in rec["architectures"].values())
    assert rec["priorAuditFacts"]["agrees"] is True and rec["sideEffectCounters"]["markerWrites"] == 0 and rec["sideEffectCounters"]["replayCalls"] == 0


def test_the_committed_attribution_chains_and_reconciles(completed):
    for arch in ("A", "D"):
        pm = completed["books"][arch]["periodMetrics"]
        chained = (1 + pm["A_2017_to_2024"]["cumulativeNetReturn"]) * (1 + pm["B_2025"]["cumulativeNetReturn"]) * (1 + pm["C_2026_to_cutoff"]["cumulativeNetReturn"]) - 1
        assert chained == pytest.approx(pm["D_full_window"]["cumulativeNetReturn"], abs=1e-9)
        formal = completed["formalReported"]["summaries"][arch]
        assert pm["D_full_window"]["cumulativeNetReturn"] == pytest.approx(formal["cumulativeNetReturn"], abs=1e-9)           # reconstruction == formal
        assert pm["D_full_window"]["annualizedNetReturn"] == pytest.approx(formal["netAnnualizedReturn"], abs=1e-9)
        assert pm["D_full_window"]["maxDrawdownWithinSpan"] == pytest.approx(formal["maxDrawdown"], abs=1e-9)
        sc = completed["books"][arch]["securityContribution"]
        for span in ("A_2017_to_2024", "B_2025", "C_2026_to_cutoff", "D_full_window"):
            assert sc[span]["grossContributionNavUnits"] - sc[span]["transactionCostNavUnits"] == pytest.approx(sc[span]["netChangeNavUnits"], abs=1e-9)
        spans = [sc[k]["netChangeNavUnits"] for k in ("A_2017_to_2024", "B_2025", "C_2026_to_cutoff")]
        assert sum(spans) == pytest.approx(sc["D_full_window"]["netChangeNavUnits"], abs=1e-9)
        assert sc["D_full_window"]["netChangeNavUnits"] == pytest.approx(formal["cumulativeNetReturn"], abs=1e-9)             # nav_T - 1 = gross - cost
        named = completed["books"][arch]["namedSecurities"]["bySpan"]["D_full_window"]
        assert named["combinedGrossContributionNavUnits"] == pytest.approx(named["005930.KS"]["grossContributionNavUnits"] + named["000660.KS"]["grossContributionNavUnits"], abs=1e-9)
    d_a = completed["dMinusA"]["D_full_window"]
    assert d_a["returnDMinusA"] == pytest.approx(completed["formalReported"]["summaries"]["D"]["cumulativeNetReturn"] - completed["formalReported"]["summaries"]["A"]["cumulativeNetReturn"], abs=1e-9)
    assert d_a["anchorsBothBooksHadAValidDecision"] == 108 and d_a["anchorsWithIdenticalSelection"] == 0 and round(d_a["meanDifferingNames"], 4) == 3.2407


def test_the_one_sensitivity_is_the_registered_one_and_removes_exactly_the_two_names(completed):
    cf = completed["counterfactual"]
    assert cf["name"] == "D_EXCLUDE_SAMSUNG_HYNIX" and cf["excluded"] == ["005930.KS", "000660.KS"] and cf["formalDecisionsUnchanged"] is True
    assert cf["labels"] == ["POST_OUTCOME_DESCRIPTIVE_SENSITIVITY", "NOT_CONFIRMATORY", "NOT_ELIGIBLE_FOR_MODEL_SELECTION"]
    assert all(v["sessionsHeld"] == 0 and v["decisionsSelected"] == 0 for v in cf["namedSecurities"].values())
    assert cf["formalD"]["cumulativeNetReturn"] == pytest.approx(completed["formalReported"]["summaries"]["D"]["cumulativeNetReturn"], abs=1e-9)
    assert cf["differenceVersusD"]["cumulativeNetReturn"] == pytest.approx(cf["summary"]["cumulativeNetReturn"] - cf["formalD"]["cumulativeNetReturn"], abs=1e-9)
    assert cf["summary"]["averageHoldings"] == pytest.approx(cf["formalD"]["averageHoldings"], abs=1e-12)           # the frozen portfolio rules imply no change in holdings


def test_the_formal_decisions_are_carried_unchanged(completed):
    f = completed["formalReported"]
    assert f["industryLayerDecision"] == "INDUSTRY_LAYER_DEVELOPMENT_SUPPORTED" and f["finalArchitecture"] == "NO_UNAMBIGUOUS_FINAL_ARCHITECTURE" and f["reason"] == "MARKET_LAYER_PARETO_TRADE_OFF"
    assert round(f["summaries"]["A"]["netAnnualizedReturn"], 4) == 0.0579 and round(f["summaries"]["D"]["netAnnualizedReturn"], 4) == 0.1501 and round(f["passive"]["annualizedReturn"], 4) == 0.2024


def test_benchmark_event_audit_lists_jumps_splits_the_excess_and_flags_a_reversal():
    days = sessions("2017-01-02", "2026-09-14")
    n = len(days)
    index_ret = np.full(n, 0.0002)
    bench_ret = index_ret.copy()
    k = days.index("2025-04-29")
    bench_ret[k] += 0.015
    j = days.index("2026-07-31")
    bench_ret[j] += 0.035
    bench_ret[j + 1] -= 0.034
    bench, idx = levels_with(bench_ret, days), levels_with(index_ret, days)
    out = A.benchmark_event_audit(bench, idx, 0.027)
    dates = [r["date"] for r in out["eventDays"]]
    assert dates == ["2025-04-29", "2026-07-31", "2026-08-03"]
    assert out["eventDaysInAReversingPair"] == ["2026-07-31", "2026-08-03"] and out["eventDaysInLateAprilOrLateDecember"] == ["2025-04-29"]
    assert out["byCalendarYear"]["2025"]["eventDays"] == 1 and out["byCalendarYear"]["2025"]["eventDayRelativeExcess"] == pytest.approx(0.015, abs=1e-3)
    assert out["status"] == A.INTERNAL_CONSTRUCTION_ANOMALY_FOUND
    assert A.benchmark_event_audit(bench, idx, 0.004)["status"] == A.INTERNAL_CONSTRUCTION_VERIFIED
    assert "NOT testable" in out["whatThisCannotSay"]


def test_the_committed_benchmark_event_audit_matches_the_report_and_changes_no_benchmark_value(committed):
    ev = committed["benchmarkEventAudit"]
    assert ev["status"] == A.INTERNAL_CONSTRUCTION_ANOMALY_FOUND and len(ev["eventDays"]) == 15 and len(ev["eventDaysInLateAprilOrLateDecember"]) == 13
    assert ev["eventDaysInAReversingPair"] == ["2026-07-31", "2026-08-03"]
    assert all(r["sameDirection"] for r in ev["largeBenchmarkMovesAgainstTheIndex"]) and len(ev["largeBenchmarkMovesAgainstTheIndex"]) == 5
    assert committed["externalReconciliation"]["status"] == A.EXTERNAL_UNRESOLVED
