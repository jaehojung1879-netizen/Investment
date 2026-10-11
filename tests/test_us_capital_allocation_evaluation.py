"""H126 outcomes and the paired SPY / QQQ comparison. Synthetic prices and synthetic outcome records only; nothing is fabricated as evidence."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import us_capital_allocation_evaluation as E   # noqa: E402
from pipeline import us_capital_allocation_policy as P       # noqa: E402
from pipeline import us_capital_allocation_receipts as R     # noqa: E402

SWITCH = P.costs_bps()["switchBpsPerUnitStockWeight"] / 1e4


def frame(sessions, closes, dividends=None):
    f = pd.DataFrame({"Close": closes, "Dividends": 0.0, "Stock Splits": 0.0}, index=pd.DatetimeIndex(sessions))
    for day, amount in (dividends or {}).items():
        f.loc[pd.Timestamp(day), "Dividends"] = amount
    return f


# --------------------------------------------------------------------------- #
# Returns: distributions once, nothing filled
# --------------------------------------------------------------------------- #
def test_total_return_reinvests_a_distribution_exactly_once():
    days = pd.bdate_range("2026-10-26", periods=5)
    flat = frame(days, [100.0] * 5, {days[2]: 1.0})
    value, reason = E.total_return_between(flat, days[0], days[-1])
    assert reason is None and value == pytest.approx(1.0 / (1.0 - 1.0 / 100.0) - 1.0)
    # an already-adjusted close must not be fed the same distribution again: no dividend column, no growth from nowhere
    assert E.total_return_between(frame(days, [100.0] * 5), days[0], days[-1])[0] == pytest.approx(0.0)


def test_a_missing_entry_or_exit_session_is_never_filled():
    days = pd.bdate_range("2026-10-26", periods=6)
    f = frame(days, [100, 101, 102, 103, 104, 105.0])
    assert E.total_return_between(f.drop(days[-1]), days[0], days[-1]) == (None, "NO_EXIT_SESSION_PRICE")
    assert E.total_return_between(f.drop(days[0]), days[0], days[-1]) == (None, "NO_ENTRY_SESSION_PRICE")
    assert E.total_return_between(None, days[0], days[-1])[0] is None
    bad = f.copy()
    bad.loc[days[2], "Close"] = 0.0
    assert E.total_return_between(bad, days[0], days[-1]) == (None, "NON_POSITIVE_OR_MISSING_CLOSE_IN_WINDOW")


def test_a_name_with_no_exit_is_unresolved_never_zero_never_a_last_price():
    days = pd.bdate_range("2026-10-26", periods=6)
    delisted = frame(days[:4], [100, 90, 80, 70.0])
    out = E.name_outcome(delisted, days[0], days[-1])
    assert out["state"] == "TERMINAL_ECONOMICS_UNRESOLVED" and out["totalReturn"] is None
    cited = E.name_outcome(delisted, days[0], days[-1], {"citation": "merger proxy, cash $75.00 per share", "totalReturn": -0.25})
    assert cited["state"] == "TERMINAL_CONSIDERATION_CITED" and cited["totalReturn"] == -0.25
    assert E.name_outcome(delisted, days[0], days[-1], {"totalReturn": -0.25})["state"] == "TERMINAL_ECONOMICS_UNRESOLVED"   # no citation, no value


# --------------------------------------------------------------------------- #
# The portfolio and the SPY / QQQ identity
# --------------------------------------------------------------------------- #
def names(**returns):
    return {t: {"state": "PRICED", "totalReturn": r} for t, r in returns.items()}


def test_portfolio_excess_vs_qqq_is_excess_vs_spy_minus_the_passive_spread_exactly():
    out = E.portfolio_outcome({"AAA": 0.15, "BBB": 0.15}, 0.70, names(AAA=0.20, BBB=-0.05), spy=0.04, qqq=0.09)
    assert out["status"] == "COMPLETE"
    assert out["switchCost"] == pytest.approx(0.30 * SWITCH)
    gross = 0.15 * 0.20 + 0.15 * -0.05 + 0.70 * 0.04
    assert out["netReturn"] == pytest.approx(gross - 0.30 * SWITCH)
    assert out["excessVsQQQ"] == pytest.approx(out["excessVsSPY"] - (0.09 - 0.04), abs=1e-15)
    assert out["selectionContributionGross"] == pytest.approx(0.15 * (0.20 - 0.04) + 0.15 * (-0.05 - 0.04))


def test_an_all_residual_book_equals_spy_with_no_cost_and_loses_to_qqq_by_exactly_the_spread():
    out = E.portfolio_outcome({}, 1.0, {}, spy=0.03, qqq=0.08)
    assert out["excessVsSPY"] == pytest.approx(0.0) and out["switchCost"] == 0.0
    assert out["excessVsQQQ"] == pytest.approx(-0.05)


def test_one_unresolved_held_name_makes_the_whole_portfolio_unresolved():
    held = {"AAA": {"state": "PRICED", "totalReturn": 0.1}, "BBB": {"state": "TERMINAL_ECONOMICS_UNRESOLVED", "totalReturn": None}}
    out = E.portfolio_outcome({"AAA": 0.15, "BBB": 0.15}, 0.70, held, spy=0.0, qqq=0.0)
    assert out["status"] == "TERMINAL_ECONOMICS_UNRESOLVED" and out["unresolvedTickers"] == ["BBB"] and out["netReturn"] is None
    assert E.portfolio_outcome({"AAA": 0.15, "ZZZ": 0.15}, 0.70, names(AAA=0.1), spy=0.0, qqq=0.0)["status"] == "NAME_OUTCOME_MISSING"


def test_the_benchmark_changes_the_level_of_the_excess_not_the_selected_names_or_their_ranks():
    book = {"AAA": 0.15, "BBB": 0.15, "CCC": 0.15}
    r = names(AAA=0.30, BBB=0.10, CCC=-0.02)
    a = E.portfolio_outcome(book, 0.55, r, spy=0.04, qqq=0.04)
    b = E.portfolio_outcome(book, 0.55, r, spy=0.04, qqq=0.12)
    assert a["selectionContributionGross"] == b["selectionContributionGross"] and a["netReturn"] == b["netReturn"]
    assert a["excessVsQQQ"] - b["excessVsQQQ"] == pytest.approx(0.08)


# --------------------------------------------------------------------------- #
# The outcome record: separate, matured, digest-sealed
# --------------------------------------------------------------------------- #
SIGNAL = "2026-10-23"
EXECUTION = "2026-10-26"


def sealed_receipt():
    f = lambda v: {"value": v, "state": "VALID"}      # noqa: E731
    cand = lambda t, s, g: {"ticker": t, "sector": s, "priceOk": True, "reportAgeDays": 10,        # noqa: E731
                            "features": {"totalCashDistributionTTM": f(400.0), "totalCashDistributionChangeYoY": f(g),
                                         "operatingCashFlowTTM": f(1000.0), "distributionToOCF": f(0.4)}}
    dec = P.select([P.evaluate(cand("AAA", "Industrials", 0.3)), P.evaluate(cand("BBB", "Utilities", 0.4))], min_measured=1)
    prices = {t: {"session": SIGNAL, "asTradedClose": 10.0, "totalReturnIndexClose": 10.0, "vendor": "SYNTHETIC",
                  "retrievedAtUtc": "2026-10-23T23:10:00+00:00", "basis": "as-traded-forward-total-return-v1"} for t in ("SPY", "QQQ", "AAA", "BBB")}
    return R.build_synthetic_receipt(
        signal_date=SIGNAL, created_at_utc="2026-10-23T23:30:00+00:00", test_clock_utc="2026-10-23T23:31:00+00:00", spec_sha256="a" * 64,
        code_identity={"commitSha": "b" * 40, "files": {"x.py": "c" * 64}}, data_identity={k: "d" * 64 for k in R.DATA_IDENTITY_KEYS},
        authorization={"specSha256": "a" * 64, "mergeCommitSha": "e" * 40, "mergedAtUtc": "2026-10-14T15:00:00+00:00"}, decision=dec, coverage={},
        membership={"snapshotDate": "2026-10-18"}, observation_prices=prices, pit_evidence={t: {"asOf": SIGNAL, "featureVersion": "US_SHAREHOLDER_DISTRIBUTION_V1", "featureDigest": "9" * 64, "features": {}} for t in ("AAA", "BBB")},
        measured_tickers=["AAA", "BBB"])


def price_frames(receipt, drift):
    exit_session = R.maturity_session(receipt["executionDate"], receipt["horizonSessions"])
    days = R._sessions(receipt["executionDate"], (exit_session - pd.Timestamp(receipt["executionDate"])).days)
    return {t: frame(days, 100.0 * np.cumprod(np.full(len(days), 1.0 + d))) for t, d in drift.items()}, exit_session


def test_an_outcome_cannot_be_built_before_the_maturity_session_is_final():
    receipt = sealed_receipt()
    frames, exit_session = price_frames(receipt, {"SPY": 0.0003, "QQQ": 0.0004, "AAA": 0.0006, "BBB": 0.0002})
    too_early = (exit_session + pd.Timedelta(hours=20)).tz_localize("UTC")                 # 20:00 UTC on the maturity date: close not yet final
    with pytest.raises(ValueError, match="HORIZON_NOT_MATURED"):
        E.build_synthetic_outcome_record(receipt, price_frames=frames, test_clock_utc=too_early)
    record = E.build_synthetic_outcome_record(receipt, price_frames=frames, test_clock_utc=(exit_session + pd.Timedelta(hours=23, minutes=1)).tz_localize("UTC"))
    assert record["maturitySession"] == str(exit_session.date()) and record["receiptSha256"] == receipt["receiptSha256"]
    assert record["portfolio"]["status"] == "COMPLETE" and record["evidenceClass"] == "SYNTHETIC_FIXTURE"
    assert record["portfolio"]["excessVsQQQ"] == pytest.approx(record["portfolio"]["excessVsSPY"] - (record["benchmarkReturns"]["QQQ"] - record["benchmarkReturns"]["SPY"]))
    again = E.build_synthetic_outcome_record(receipt, price_frames=frames, test_clock_utc=(exit_session + pd.Timedelta(hours=23, minutes=1)).tz_localize("UTC"))
    assert again["recordSha256"] == record["recordSha256"]
    assert "outcome" not in " ".join(receipt)                                              # the receipt itself carries no outcome key


def test_the_outcome_exit_is_exactly_126_us_sessions_after_the_execution_session():
    exit_session = R.maturity_session(EXECUTION, 126)
    sessions = R._sessions(EXECUTION, (exit_session - pd.Timestamp(EXECUTION)).days)
    assert len(sessions) == 127 and sessions[0] == pd.Timestamp(EXECUTION) and sessions[-1] == exit_session


def test_a_missing_benchmark_price_blocks_the_outcome_rather_than_substituting_one():
    receipt = sealed_receipt()
    frames, exit_session = price_frames(receipt, {"SPY": 0.0003, "AAA": 0.0006, "BBB": 0.0002})
    with pytest.raises(ValueError, match="BENCHMARK_OUTCOME_UNAVAILABLE: QQQ"):
        E.build_synthetic_outcome_record(receipt, price_frames=frames, test_clock_utc=(exit_session + pd.Timedelta(days=2)).tz_localize("UTC"))


def test_a_delisted_held_name_leaves_an_unresolved_outcome_not_a_filled_one():
    receipt = sealed_receipt()
    frames, exit_session = price_frames(receipt, {"SPY": 0.0003, "QQQ": 0.0004, "AAA": 0.0006, "BBB": 0.0002})
    frames["BBB"] = frames["BBB"].iloc[:60]
    record = E.build_synthetic_outcome_record(receipt, price_frames=frames, test_clock_utc=(exit_session + pd.Timedelta(days=2)).tz_localize("UTC"))
    assert record["portfolio"]["status"] == "TERMINAL_ECONOMICS_UNRESOLVED" and record["portfolio"]["netReturn"] is None
    assert record["nameOutcomes"]["BBB"]["state"] == "TERMINAL_ECONOMICS_UNRESOLVED"


# --------------------------------------------------------------------------- #
# Overlap-corrected inference and the verdict
# --------------------------------------------------------------------------- #
def synthetic_records(excess_spy, spread, *, held=True, start="2026-10-23"):
    """One outcome record per weekly signal with chosen excess-vs-SPY and passive spread; dates are real Fridays."""
    weeks = pd.date_range(start, periods=len(excess_spy), freq="7D")
    out = []
    for i, day in enumerate(weeks):
        execution = day + pd.Timedelta(days=3)
        spy = 0.04
        qqq = spy + spread[i]
        net = spy + excess_spy[i]
        out.append({"signalDate": str(day.date()), "executionDate": str(execution.date()), "maturitySession": str((execution + pd.Timedelta(days=180)).date()),
                    "benchmarkReturns": {"SPY": spy, "QQQ": qqq},
                    "nameOutcomes": {"AAA": {"state": "PRICED"}} if held else {},
                    "portfolio": {"status": "COMPLETE", "netReturn": net, "excessVsSPY": excess_spy[i], "excessVsQQQ": net - qqq,
                                  "switchCost": 0.0, "selectionContributionGross": excess_spy[i]}})
    return out


PASS = {"SPY": "PASS", "QQQ": "PASS"}


def test_before_the_maturity_gate_there_is_no_verdict_only_descriptive_numbers():
    rows = synthetic_records([0.05] * 60, [0.0] * 60)
    out = E.evaluate_program(rows, benchmark_integrity=PASS)
    assert out["verdict"] == "NOT_YET_EVALUABLE" and out["reasons"] == ["MATURITY_GATE_NOT_MEASURED_YET"] or out["reasons"] == ["MATURITY_GATE_NOT_MET"]
    assert "bounds" not in out and out["independentWindows"] == 60 // 26
    assert E.evaluate_program([], benchmark_integrity=PASS)["verdict"] == "NOT_YET_EVALUABLE"


def test_a_clear_and_stable_advantage_over_both_passive_alternatives_is_a_success():
    rng = np.random.default_rng(1)
    n = 330
    rows = synthetic_records(list(0.03 + rng.normal(0, 0.004, n)), list(rng.normal(0.0, 0.002, n)))
    out = E.evaluate_program(rows, benchmark_integrity=PASS)
    assert out["verdict"] == "SUCCESS" and out["bounds"]["SPY"]["lower"] > 0 and out["bounds"]["QQQ"]["lower"] > 0
    assert out["independentWindows"] == n // 26 >= 12 and out["heldShare"] == 1.0


def test_beating_spy_but_not_qqq_is_not_a_success():
    """The passive spread is +3%: the selection adds 2% over SPY, so the policy is still BEHIND QQQ."""
    n = 330
    rows = synthetic_records([0.02] * n, [0.03] * n)
    out = E.evaluate_program(rows, benchmark_integrity=PASS)
    assert out["bounds"]["SPY"]["lower"] > 0 and out["bounds"]["QQQ"]["upper"] < 0
    assert out["verdict"] == "FAILURE"                                                    # statistically worse than the QQQ it would replace


def test_a_clear_loss_to_a_passive_alternative_is_a_failure():
    out = E.evaluate_program(synthetic_records([-0.02] * 330, [0.0] * 330), benchmark_integrity=PASS)
    assert out["verdict"] == "FAILURE" and out["bounds"]["SPY"]["upper"] < 0


def test_noise_around_zero_is_inconclusive_not_a_discovery():
    noise = np.random.default_rng(7).normal(0.0, 0.05, 330)
    noise -= noise.mean()                      # mean exactly zero: a sample that is neither better nor worse than the passive alternative
    out = E.evaluate_program(synthetic_records(list(noise), [0.0] * 330), benchmark_integrity=PASS)
    assert out["verdict"] == "INCONCLUSIVE" and out["bounds"]["SPY"]["lower"] < 0 < out["bounds"]["SPY"]["upper"]


def test_under_no_true_difference_a_one_sided_failure_or_success_appears_at_about_the_nominal_rate():
    """The rule is a 5% one-sided test each way, so over many zero-mean samples about 5% fall in each tail (checked loosely)."""
    outcomes = {"SUCCESS": 0, "FAILURE": 0, "INCONCLUSIVE": 0}
    for seed in range(60):
        noise = np.random.default_rng(100 + seed).normal(0.0, 0.05, 330)
        outcomes[E.evaluate_program(synthetic_records(list(noise), [0.0] * 330), benchmark_integrity=PASS)["verdict"]] += 1
    assert outcomes["SUCCESS"] <= 10 and outcomes["FAILURE"] <= 10


def test_unresolved_terminal_outcomes_or_failed_benchmark_integrity_withhold_the_verdict():
    rows = synthetic_records([0.03] * 330, [0.0] * 330)
    rows[5]["portfolio"] = {"status": "TERMINAL_ECONOMICS_UNRESOLVED", "netReturn": None, "excessVsSPY": None, "excessVsQQQ": None}
    bad = E.evaluate_program(rows, benchmark_integrity=PASS)
    assert bad["verdict"] == "INCONCLUSIVE" and "UNRESOLVED_TERMINAL_OUTCOME" in bad["reasons"]
    clean = synthetic_records([0.03] * 330, [0.0] * 330)
    assert E.evaluate_program(clean, benchmark_integrity={"SPY": "PASS", "QQQ": "EXTERNAL_CORROBORATION_PENDING"})["verdict"] == "INCONCLUSIVE"
    assert E.evaluate_program(clean, benchmark_integrity=None)["verdict"] == "INCONCLUSIVE"


def test_a_policy_that_never_holds_a_name_cannot_succeed():
    rows = synthetic_records([0.0] * 330, [-0.01] * 330, held=False)      # always 100% SPY, QQQ always behind SPY
    out = E.evaluate_program(rows, benchmark_integrity=PASS)
    assert out["heldShare"] == 0.0 and out["verdict"] != "SUCCESS"


def test_blocked_weeks_are_evaluated_as_the_all_spy_book_not_dropped():
    rows = synthetic_records([0.03] * 330, [0.0] * 330)
    for r in rows[:30]:
        r["nameOutcomes"] = {}
        r["portfolio"] = {"status": "BLOCKED_RECEIPT", "netReturn": None, "excessVsSPY": None, "excessVsQQQ": None}
    out = E.evaluate_program(rows, benchmark_integrity=PASS)
    assert out["maturedWeeks"] == 330 and out["blockedWeeksHeldAsResidual"] == 30
    assert out["bounds"]["SPY"]["mean"] == pytest.approx(0.03 * 300 / 330)


def test_duplicate_signal_weeks_are_refused():
    rows = synthetic_records([0.01] * 4, [0.0] * 4)
    with pytest.raises(ValueError, match="DUPLICATE_SIGNAL_WEEK"):
        E.evaluate_program(rows + [rows[0]], benchmark_integrity=PASS)


def test_block_bootstrap_widens_the_interval_for_overlapping_windows_and_is_deterministic():
    """Weekly series built from overlapping 26-week sums are strongly autocorrelated; an iid interval would be far too narrow."""
    rng = np.random.default_rng(3)
    base = rng.normal(0.0, 0.02, 400)
    overlapping = np.convolve(base, np.ones(26), mode="valid") / 26
    n = len(overlapping)
    iid = E.one_sided_bounds(overlapping, np.random.default_rng(0).integers(0, n, size=(4000, n)))
    blocked = E.one_sided_bounds(overlapping, E.block_indices(n, 26, 4000, seed=11))
    assert (blocked["upper"] - blocked["lower"]) > 1.6 * (iid["upper"] - iid["lower"])
    assert np.array_equal(E.block_indices(50, 26, 10, seed=5), E.block_indices(50, 26, 10, seed=5))
    assert not np.array_equal(E.block_indices(50, 26, 10, seed=5), E.block_indices(50, 26, 10, seed=6))


def test_the_same_resampled_weeks_feed_both_benchmarks_so_the_difference_is_exactly_the_spread():
    n = 330
    rng = np.random.default_rng(9)
    spread = list(rng.normal(0.01, 0.02, n))
    rows = synthetic_records(list(rng.normal(0.01, 0.03, n)), spread)
    out = E.evaluate_program(rows, benchmark_integrity=PASS)
    assert out["bounds"]["SPY"]["mean"] - out["bounds"]["QQQ"]["mean"] == pytest.approx(float(np.mean(spread)), abs=1e-12)


def test_growth_loading_separates_a_growth_tilt_from_selection():
    rng = np.random.default_rng(5)
    n = 330
    spread = rng.normal(0.0, 0.03, n)
    d_spy = 0.01 + 0.8 * spread + rng.normal(0, 0.002, n)               # excess that is mostly a growth tilt
    out = E.growth_loading(d_spy, spread, E.block_indices(n, 26, 500, seed=2))
    assert out["status"] == "MEASURED" and out["slope"] == pytest.approx(0.8, abs=0.1) and out["intercept"] == pytest.approx(0.01, abs=0.005)
    assert E.growth_loading([0.1, 0.2], [0.0, 0.0], np.zeros((3, 2), int))["status"] == "SPREAD_HAS_NO_VARIATION"


def test_selection_null_is_deterministic_has_a_corrected_pvalue_and_respects_the_pool():
    pool = ["P%02d" % i for i in range(12)]
    returns = {t: 0.01 * i for i, t in enumerate(pool)}
    sectors = {t: "A" if i < 6 else "B" for i, t in enumerate(pool)}
    weeks = [{"selected": ["P11", "P10"], "pool": pool, "returns": returns, "sector": sectors, "spy": 0.02} for _ in range(4)]
    a, b = E.selection_null(weeks, draws=300, seed=1), E.selection_null(weeks, draws=300, seed=1)
    assert a == b and a["realMean"] > a["nullMean"] and 1 / 301 <= a["pValueOneSided"] < 0.05
    assert E.selection_null([], draws=10)["realMean"] is None


def test_evaluation_module_has_no_import_of_the_official_weekly_machinery_or_model_code():
    text = (ROOT / "pipeline/us_capital_allocation_evaluation.py").read_text()
    for name in ("weekly_decision", "weekly_publish", "weekly_history", "historical_calibration", "kelly_portfolio", "lightgbm", "sklearn"):
        assert name not in text.replace("`%s`" % name, "")
