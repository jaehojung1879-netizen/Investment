"""US dual-benchmark foundation: SPY + QQQ data, comparison, adapter, Nasdaq-100 PIT.

Synthetic tests pin the arithmetic and the refusals. The committed-artifact
tests pin what was actually built, and recompute the SPY/QQQ comparison from
the committed snapshot without network or signal-history.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import nasdaq100_membership as N        # noqa: E402
from pipeline import us_dual_benchmark_adapter as A   # noqa: E402
from pipeline import us_dual_benchmark_data as D      # noqa: E402
from pipeline import us_spy_qqq_comparison as C       # noqa: E402
from pipeline import us_universe_coverage as U        # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "build_us_dual_benchmark_foundation", ROOT / "scripts" / "build_us_dual_benchmark_foundation.py")
B = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = B
_spec.loader.exec_module(B)

AUDIT = json.loads((ROOT / "docs/us-readiness/us-dual-benchmark-v1-data-audit.json").read_text())
COMPARISON = json.loads((ROOT / "docs/us-readiness/us-spy-qqq-comparison-v1.json").read_text())
N100 = json.loads((ROOT / "docs/us-readiness/nasdaq100-pit-membership-v1.json").read_text())
COVERAGE = json.loads((ROOT / "docs/us-readiness/us-universe-coverage-gap-v1.json").read_text())


def _bdays(n, start="2020-01-01"):
    return pd.bdate_range(start, periods=n)


def _raw_with_dividends(n=300, seed=1):
    rng = np.random.default_rng(seed)
    idx = _bdays(n)
    raw = pd.Series(100 * np.cumprod(1 + rng.normal(0.0004, 0.01, n)), index=idx)
    events = pd.DataFrame({"dividend": 0.0, "split": 1.0}, index=idx)
    for i in (60, 120, 180, 240):
        events.iloc[i, 0] = 0.35
    return raw, events


# --------------------------------------------------------------------------- #
# QQQ return reconstruction and the double-count guard
# --------------------------------------------------------------------------- #
def test_total_return_reconstruction_round_trips_exactly():
    raw, events = _raw_with_dividends()
    tr = D.apply_distributions(raw, events, basis=D.BASIS_RAW)
    assert tr.iloc[0] == pytest.approx(raw.iloc[0])                # forward anchor
    back = D.reconstruct_raw_close(tr, events)
    assert np.allclose(back.to_numpy(), raw.to_numpy(), rtol=1e-12)
    multiples = D.distribution_application_multiples(tr, back, events)
    assert len(multiples) == 4
    assert all(m["multiple"] == pytest.approx(1.0, abs=1e-9) for m in multiples)
    # TR beats price-only by exactly the reinvested distributions.
    assert tr.iloc[-1] / tr.iloc[0] > raw.iloc[-1] / raw.iloc[0]


def test_already_adjusted_close_cannot_receive_distributions_again():
    raw, events = _raw_with_dividends()
    tr = D.apply_distributions(raw, events, basis=D.BASIS_RAW)
    with pytest.raises(D.DoubleCountRefused):
        D.apply_distributions(tr, events, basis=D.BASIS_TOTAL_RETURN)


def test_double_application_is_measured_as_multiple_two():
    raw, events = _raw_with_dividends()
    once = D.apply_distributions(raw, events, basis=D.BASIS_RAW)
    # The KODEX 200 defect: the vendor close already carried the factor.
    twice = D.apply_distributions(once, events, basis=D.BASIS_RAW)
    multiples = D.distribution_application_multiples(twice, raw, events)
    # ~2, not exactly: the second pass divides by the already-grown close.
    assert all(m["multiple"] == pytest.approx(2.0, abs=0.05) for m in multiples)


def test_split_in_span_is_refused_not_guessed():
    raw, events = _raw_with_dividends()
    events.iloc[100, 1] = 2.0
    with pytest.raises(ValueError, match="SPLIT_PRESENT"):
        D.reconstruct_raw_close(raw, events)


# --------------------------------------------------------------------------- #
# Session alignment, return basis, determinism
# --------------------------------------------------------------------------- #
def test_matched_sessions_use_only_the_intersection():
    idx = _bdays(30)
    spy = pd.Series(np.linspace(100, 110, 30), index=idx)
    qqq = pd.Series(np.linspace(50, 60, 30), index=idx).drop(idx[[3, 7]])
    frame = C.matched(spy, qqq, str(idx[0].date()), str(idx[-1].date()))
    assert len(frame) == 28 and idx[3] not in frame.index and idx[7] not in frame.index
    with pytest.raises(ValueError, match="MATCHED_WINDOW_EMPTY"):
        C.matched(spy, qqq, "2030-01-01", "2030-02-01")


def test_committed_series_share_one_basis_and_one_calendar():
    for ticker in ("SPY", "QQQ"):
        s = AUDIT["series"][ticker]
        assert s["duplicateSessions"] == 0 and s["nonPositiveOrMissingClose"] == 0
        assert s["splitsInSpan"] == 0
        assert AUDIT["calendar"][ticker]["missing"] == [] and AUDIT["calendar"][ticker]["extra"] == []
    qqq = AUDIT["series"]["QQQ"]
    assert qqq["distributions"] == 64 and qqq["distributionsDropped"] == 0
    assert qqq["distributionMultiple"] == {"min": 1.0, "max": 1.0}
    assert 0.3 < qqq["impliedDistributionDragPctPerYear"] < 1.5      # single, not doubled
    assert AUDIT["pair"]["onlySpy"] == [] and AUDIT["pair"]["onlyQqq"] == []
    assert AUDIT["spyDistributionApplication"]["status"] == "NOT_VERIFIABLE_FROM_SEALED_STORE"
    assert AUDIT["externalCorroboration"]["status"] == "NOT_PERFORMED"
    assert AUDIT["source"]["sha256"] == D.REPLAY_MANIFEST_SHA256
    assert {e["vendor"] for e in AUDIT["source"]["lineage"]["adjustment"]} == {"YAHOO_UNADJUSTED_WITH_ACTIONS"}


def test_snapshot_writer_is_byte_deterministic(tmp_path):
    rows = [{"ticker": "QQQ", "date": "2020-01-02", "totalReturnClose": 1.5, "rawClose": 1.5,
             "dividend": 0.0, "split": 1.0, "usdKrw": None}]
    assert D.write_snapshot(rows, tmp_path / "a.csv.gz") == D.write_snapshot(rows, tmp_path / "b.csv.gz")


def test_committed_snapshot_matches_manifest_and_comparison_recomputes():
    manifest = json.loads((ROOT / "data/research/us-dual-benchmark-v1/manifest.json").read_text())
    for rel, digest in manifest["files"].items():
        assert hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() == digest, rel
    assert COMPARISON["snapshot"]["sha256"] == AUDIT["snapshot"]["sha256"]
    assert B.comparison_payload() == COMPARISON


def test_snapshot_spy_reconciles_with_the_official_weekly_replay():
    rec = AUDIT["officialReplayReconciliation"]
    assert abs(rec["differencePctPt"]) <= 0.01
    assert AUDIT["spySnapshotCrossCheck"]["maxRelativeDifference"] == 0.0


def test_headline_window_is_the_existing_weekly_replay_window():
    replay = json.loads((ROOT / "docs/weekly-decision/weekly-passive-first-v1-weekly-replay.json").read_text())
    assert C.HEADLINE_WINDOW == (replay["calendar"]["first"]["date"], replay["calendar"]["last"]["endDate"])
    window = COMPARISON["headline"]["window"]
    assert (window["start"], window["end"]) == C.HEADLINE_WINDOW
    years = COMPARISON["headline"]["calendarYears"]
    assert [y["year"] for y in years] == list(range(2013, 2027))          # no year omitted
    assert COMPARISON["headline"]["spyAheadYears"] == [y["year"] for y in years if y["winner"] == "SPY"]


# --------------------------------------------------------------------------- #
# FX
# --------------------------------------------------------------------------- #
def test_fx_uses_latest_fixing_and_refuses_stale_values():
    obs = {"2020-01-02": 1150.0, "2020-01-03": 1160.0}
    sessions = pd.DatetimeIndex(["2020-01-01", "2020-01-03", "2020-01-06", "2020-01-20"])
    fx = D.fx_on_sessions(obs, sessions, max_age_days=7)
    assert np.isnan(fx.iloc[0])                      # nothing published yet
    assert fx.iloc[1] == 1160.0 and fx.iloc[2] == 1160.0
    assert np.isnan(fx.iloc[3])                      # 17 days stale: missing, not filled


def test_krw_view_cannot_change_the_relative_ranking_and_needs_fx_at_both_ends():
    idx = _bdays(400)
    rng = np.random.default_rng(3)
    spy = pd.Series(100 * np.cumprod(1 + rng.normal(0.0004, 0.01, 400)), index=idx)
    qqq = pd.Series(100 * np.cumprod(1 + rng.normal(0.0006, 0.013, 400)), index=idx)
    fx = pd.Series(1100 * np.cumprod(1 + rng.normal(0, 0.004, 400)), index=idx)
    rate = {"2019-01-01": 2.0}
    out = C.compare(spy, qqq, start=str(idx[0].date()), end=str(idx[-1].date()), fx=fx,
                    usd_rate=rate, krw_rate=rate, costs={"commissionBps": 5, "spreadBps": 10, "sellTaxBps": 3})
    assert out["krw"]["available"] and out["krw"]["relativeWealthIdentityError"] < 1e-12
    fx_missing = fx.copy()
    fx_missing.iloc[0] = np.nan
    out2 = C.compare(spy, qqq, start=str(idx[0].date()), end=str(idx[-1].date()), fx=fx_missing,
                     usd_rate=rate, krw_rate=rate, costs={"commissionBps": 5, "spreadBps": 10, "sellTaxBps": 3})
    assert out2["krw"] == {"available": False}
    assert out2["usd"] == out["usd"]


def test_trading_costs_are_identical_for_both_etfs_and_fees_not_double_counted():
    net = COMPARISON["headline"]["netOfTradingCosts"]
    assert net["expenseRatioDeducted"] is False
    assert net["entryCostPct"] == 0.15 and net["exitCostPct"] == 0.18


# --------------------------------------------------------------------------- #
# The SPY -> QQQ identity and what it leaves invariant
# --------------------------------------------------------------------------- #
def _cross_section(seed=7, dates=60, names=25):
    rng = np.random.default_rng(seed)
    idx = _bdays(dates)
    cols = [f"S{i:02d}" for i in range(names)]
    stock = pd.DataFrame(rng.normal(0.01, 0.08, (dates, names)), index=idx, columns=cols)
    preds = pd.DataFrame(rng.normal(0, 1, (dates, names)), index=idx, columns=cols)
    spy = pd.Series(rng.normal(0.01, 0.03, dates), index=idx)
    qqq = spy + pd.Series(rng.normal(0.005, 0.02, dates), index=idx)
    return preds, stock, spy, qqq


def test_alpha_identity_holds_cell_by_cell():
    _, stock, spy, qqq = _cross_section()
    assert A.identity_error(stock, spy, qqq) < 1e-15


def test_within_date_ranks_and_rank_ic_are_benchmark_invariant():
    preds, stock, spy, qqq = _cross_section()
    ic_spy = A.rank_ic_by_date(preds, A.relative_returns(stock, spy))
    ic_qqq = A.rank_ic_by_date(preds, A.relative_returns(stock, qqq))
    assert np.allclose(ic_spy.to_numpy(), ic_qqq.to_numpy(), atol=1e-12)
    a_spy, a_qqq = A.relative_returns(stock, spy), A.relative_returns(stock, qqq)
    for d in stock.index[:5]:
        assert list(a_spy.loc[d].rank()) == list(a_qqq.loc[d].rank())


def test_economic_hurdles_and_sign_shares_differ_by_benchmark():
    preds, stock, spy, qqq = _cross_section()
    design = A.StudyDesign("syn", "SYN", 21, "SPY", stockRoundTripCostBps=30, etfRoundTripCostBps=6)
    ident = dict(snapshotSha256="x", basis="TR", vendor="SYN", integrityStatus=A.INTEGRITY_PASS)
    result = A.paired_evaluation(design, A.BenchmarkIdentity(A.ROLE_MARKET, "SPY", **ident),
                                 A.BenchmarkIdentity(A.ROLE_GROWTH, "QQQ", **ident), preds, stock, spy, qqq)
    assert result["rankStatistics"]["benchmarkInvariant"]
    assert result["rankStatistics"]["maxAbsIcDifferenceAcrossBenchmarks"] < 1e-12
    econ = result["economics"]
    assert econ["SPY"]["meanNetExcess"] != pytest.approx(econ["QQQ"]["meanNetExcess"])
    assert econ["identityCheck"] < 1e-12                 # gap == mean benchmark spread
    assert econ["hurdle"] == pytest.approx(0.0024)
    assert result["headlineEligible"]


def test_unpassed_benchmark_integrity_blocks_the_headline_not_the_computation():
    preds, stock, spy, qqq = _cross_section()
    design = A.StudyDesign("syn", "SYN", 21, "SPY", 30, 6)
    ok = A.BenchmarkIdentity(A.ROLE_MARKET, "SPY", "x", "TR", "SYN", A.INTEGRITY_PASS)
    weak = A.BenchmarkIdentity(A.ROLE_GROWTH, "QQQ", "y", "TR", "SYN", "EXTERNAL_CORROBORATION_PENDING")
    result = A.paired_evaluation(design, ok, weak, preds, stock, spy, qqq)
    assert not result["headlineEligible"] and result["headlineBlockers"] == ["QQQ:EXTERNAL_CORROBORATION_PENDING"]


def test_roles_and_residual_policy_must_be_declared():
    with pytest.raises(ValueError, match="ROLE_MISMATCH"):
        A.BenchmarkIdentity(A.ROLE_MARKET, "QQQ", "x", "TR", "SYN", A.INTEGRITY_PASS)
    with pytest.raises(ValueError, match="RESIDUAL_ASSET_NOT_DECLARED"):
        A.StudyDesign("syn", "SYN", 21, "", 30, 6)
    with pytest.raises(ValueError, match="MAX_SELECTED"):
        A.StudyDesign("syn", "SYN", 21, "SPY", 30, 6, maxSelected=6)


def test_forward_returns_never_turn_missing_into_zero():
    idx = _bdays(10)
    close = pd.Series(np.arange(10, 20, dtype=float), index=idx)
    close.iloc[5] = np.nan
    fwd = A.forward_returns(close, idx[:9], 2, idx)
    assert np.isnan(fwd.loc[idx[3]]) and np.isnan(fwd.loc[idx[5]])      # either end missing
    assert np.isnan(fwd.loc[idx[8]])                                     # beyond the calendar
    assert fwd.loc[idx[0]] == pytest.approx(12 / 10 - 1)


# --------------------------------------------------------------------------- #
# Missing prices inside a selected book
# --------------------------------------------------------------------------- #
def test_missing_selected_name_makes_the_date_unmeasurable():
    idx = _bdays(4)
    book = pd.DataFrame({"a": [0.1, 0.1, np.nan, 0.1], "b": [0.0, 0.2, 0.1, 0.0]}, index=idx)
    spy = pd.Series(0.01, index=idx)
    qqq = pd.Series(0.02, index=idx)
    econ = A.per_benchmark_economics(book, spy, qqq, 0.0)
    assert econ["measurableDates"] == 3 and econ["unmeasurableDates"] == 1


def test_portfolio_alternatives_share_one_population_and_stop_on_a_missing_holding():
    idx = _bdays(3)
    rets = pd.DataFrame({"SPY": [0.01, 0.02, -0.01], "QQQ": [0.02, 0.03, -0.02], "USD_CASH": [0.0] * 3,
                         "AAA": [0.05, np.nan, 0.01]}, index=idx)
    design = A.StudyDesign("syn", "SYN", 5, "SPY", 30, 6)
    full = A.alternative_paths(design, idx[:1], rets, {idx[0]: ["AAA"]}, 0.5)
    assert full["status"] == "COMPLETE"
    assert full["finalNav"]["P1_STOCKS"] == pytest.approx(1 + 0.5 * 0.05 + 0.5 * 0.01)
    broken = A.alternative_paths(design, idx, rets, {idx[1]: ["AAA"]}, 0.5)
    assert broken["status"].startswith("UNMEASURABLE_HELD_NAME_AT")
    assert broken["finalNav"] == {"P0_SPY": None, "P0_QQQ": None, "P1_STOCKS": None}
    with pytest.raises(ValueError, match="TOO_MANY_SELECTED"):
        A.alternative_paths(design, idx[:1], rets, {idx[0]: list("ABCDEF")}, 0.5)


# --------------------------------------------------------------------------- #
# Nasdaq-100 point-in-time membership
# --------------------------------------------------------------------------- #
def _sec(t, status=N.STATUS_CONFIRMED):
    return N.Security(t, issuer="", identityStatus=status)


BASE = N.BaseSnapshot("syn", None, "2013-01-01", "2013-01-01", members=(_sec("AAA"), _sec("BBB")))


def test_change_is_used_only_once_announced_and_only_once_effective():
    event = N.MembershipEvent("e1", "syn", None, announcementDate="2014-12-12", effectiveDate="2014-12-22",
                              added=(_sec("CCC"),), removed=(_sec("BBB"),))
    before = N.membership_knowable_on("2014-12-10", BASE, [event])
    pending = N.membership_knowable_on("2014-12-15", BASE, [event])
    after = N.membership_knowable_on("2014-12-22", BASE, [event])
    assert before["members"] == ["AAA", "BBB"] and before["pending"] == []
    assert pending["members"] == ["AAA", "BBB"] and pending["pending"] == ["e1"]
    assert after["members"] == ["AAA", "CCC"]


def test_unknown_announcement_falls_back_to_effective_date():
    event = N.MembershipEvent("e2", "syn", None, None, "2015-03-23", added=(_sec("DDD"),))
    assert event.knowableFrom == "2015-03-23"
    assert "DDD" not in N.membership_knowable_on("2015-03-20", BASE, [event])["members"]
    assert N.membership_knowable_on("2015-03-20", BASE, [event])["pending"] == []


def test_effective_before_announcement_is_rejected():
    with pytest.raises(ValueError, match="EFFECTIVE_BEFORE_ANNOUNCEMENT"):
        N.MembershipEvent("bad", "syn", None, "2020-02-01", "2020-01-01")


def test_no_base_snapshot_means_no_membership_never_todays_list():
    out = N.membership_knowable_on("2013-06-01", None, [])
    assert out["status"] == N.NOT_RECONSTRUCTIBLE and out["members"] is None
    late = N.BaseSnapshot("syn", None, "2020-01-01", "2020-01-01", members=(_sec("ZZZ"),))
    assert N.membership_knowable_on("2013-06-01", late, [])["status"] == N.NOT_RECONSTRUCTIBLE


def test_ambiguous_identity_downgrades_to_partial_and_is_named():
    event = N.MembershipEvent("e3", "syn", None, None, "2016-01-04",
                              added=(_sec("NEWT", N.STATUS_AMBIGUOUS),), removed=(_sec("AAA"),))
    out = N.membership_knowable_on("2016-06-01", BASE, [event])
    assert out["status"] == N.PARTIAL and out["ambiguousIdentities"] == ["NEWT"]
    assert N.classify_reconstruction(BASE, [event], 2016, 2016)["openIdentities"] == ["NEWT"]


def test_departed_member_stays_in_history_no_survivorship_backfill():
    docs = {2013: N.parse_yearly_yaml("year: 2013\ntickers_on_Jan_1:\n  - AAA\n  - OLD\nchanges:\n"
                                      "  '2013-06-03':\n    difference:\n      - OLD\n    union:\n      - NEW\n"),
            2014: N.parse_yearly_yaml("year: 2014\ntickers_on_Jan_1:\n  - AAA\n  - NEW\n")}
    assert N.chain_consistency(docs)[0]["consistent"]
    spans = N.membership_intervals(docs, "2013-01-01", "2014-12-31")
    assert spans["OLD"] == [["2013-01-01", "2013-06-03"]]
    assert spans["NEW"] == [["2013-06-03", None]]


def test_vendored_n100_files_are_chain_consistent_and_pinned():
    assert N100["chainConsistency"]["inconsistentYears"] == []
    assert N100["verdict"] == "PARTIAL" and N100["reconstruction"]["status"] == N.PARTIAL
    assert N100["source"]["authority"] == "DERIVED_NON_AUTHORITATIVE"
    for year, digest in N100["fileSha256"].items():
        path = ROOT / f"data/research/us-dual-benchmark-v1/nasdaq100-n100tickers/n100-ticker-changes-{year}.yaml"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    assert all(check["agrees"] for check in N100["spotChecks"])
    assert all(100 <= n <= 107 for n in N100["memberCounts"].values())


# --------------------------------------------------------------------------- #
# Coverage-gap manifest
# --------------------------------------------------------------------------- #
def _cov(**overrides):
    base = dict(start="2013-01-01", end="2020-12-31",
                sp500={"LIVE": {"listed": "2012-12-27", "delisted": None},
                       "GONE": {"listed": "2012-12-27", "delisted": "2016-01-01"},
                       "REUSED": {"listed": "2012-12-27", "delisted": None}},
                sp500_identity={"REUSED": "TICKER_REUSE_DIFFERENT_ISSUER"}, sp500_unpriced={"GONE"},
                n100_spans={"NDXONLY": [["2015-01-01", None]], "LIVE": [["2013-01-01", None]]},
                prices={"LIVE": {"first": "2011-01-03", "last": "2020-12-31"},
                        "REUSED": {"first": "2019-01-02", "last": "2020-12-31"}},
                filings={"LIVE": 40}, ciks={"LIVE": "1"}, successors={})
    base.update(overrides)
    return {r["symbol"]: r for r in U.build_manifest(**base)}


def test_coverage_statuses_for_delisted_reused_and_index_only_names():
    rows = _cov()
    assert rows["LIVE"]["status"] == U.READY
    assert rows["GONE"]["status"] == U.BLOCKED_PAID_SOURCE              # departed, kept, not dropped
    assert rows["REUSED"]["status"] == U.NEEDS_IDENTITY_REPAIR
    assert rows["NDXONLY"]["status"] == U.NEEDS_PRICE_HISTORY
    assert set(rows["NDXONLY"]["gaps"]) >= {U.NEEDS_FUNDAMENTALS, U.NEEDS_MEMBERSHIP_EVIDENCE}


def test_panel_starting_after_membership_is_an_identity_question():
    rows = _cov(sp500_identity={}, prices={"LIVE": {"first": "2016-08-17", "last": "2020-12-31"}})
    assert rows["LIVE"]["status"] == U.NEEDS_IDENTITY_REPAIR


def test_committed_coverage_counts_reconcile_with_prior_audits():
    s = COVERAGE["summary"]
    assert s["sp500"]["symbols"] == 827                                  # v3 identity-resolved union
    assert COVERAGE["finnhubStoreMeasured"]["tickers"] == 782
    assert COVERAGE["finnhubStoreMeasured"]["filings"] == 34945          # 34,941 + 4 abnormal fiscal years
    assert sum(s["union"][k] for k in U.STATUSES) == s["union"]["symbols"]
    with gzip.open(ROOT / COVERAGE["manifest"]["path"], "rt") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == s["union"]["symbols"]
    assert {r["status"] for r in rows} <= set(U.STATUSES)


# --------------------------------------------------------------------------- #
# Production is untouched
# --------------------------------------------------------------------------- #
NEW_MODULES = ("us_dual_benchmark", "us_spy_qqq_comparison", "nasdaq100_membership", "us_universe_coverage")


def test_production_modules_do_not_import_research_code():
    for name in ("weekly_decision.py", "weekly_history.py", "weekly_publish.py", "build.py",
                 "benchmark_source.py", "historical_replay.py"):
        path = ROOT / "pipeline" / name
        if path.exists():
            text = path.read_text()
            assert not any(m in text for m in NEW_MODULES), name


def test_official_us_benchmark_and_weekly_receipts_unchanged():
    cfg = json.loads((ROOT / "config.json").read_text())
    assert cfg["benchmarks"]["US"] == "SPY" == D.OFFICIAL_US_BENCHMARK
    assert "QQQ" not in cfg["benchmarkSources"]
    recorded = AUDIT["protected"]["weeklyDecisionDocsSha256"]
    for name, digest in recorded.items():
        assert hashlib.sha256((ROOT / "docs/weekly-decision" / name).read_bytes()).hexdigest() == digest, name
    assert AUDIT["protected"]["configBenchmarksUS"] == "SPY"
