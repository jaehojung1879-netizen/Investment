"""Where and when the survivorship gap is, not just how big it is on average.

Two separate gaps decide whether a historical cross-section is trustworthy: the
names the membership file describes but the price vendor cannot serve, and the
names the file says nothing about at all. Reporting only the first is how a
replay comes to publish a HIGH survivorship risk beside 0.0% affected
observations, and how the integrity gate turns green for a book whose Korean
half nobody can vouch for.

These tests pin the cases where a pooled number and a per-region or per-year one
tell opposite stories.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pipeline import historical_replay as HR
from pipeline import pit_data
from pipeline import portfolio_validation as PV


def _frame(seed: int, periods: int = 1400, start: str = "2015-01-01") -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.bdate_range(start, periods=periods)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.014, periods)))
    return pd.DataFrame({
        "Open": close * (1 + rng.normal(0, 0.003, periods)),
        "High": close * 1.01, "Low": close * 0.99, "Close": close,
        "Volume": rng.lognormal(14, 0.4, periods),
    }, index=index)


class _AllPriced:
    def has_history(self, ticker: str, rows: int) -> bool:
        return True


@pytest.fixture(scope="module")
def two_region_prices() -> dict:
    out = {f"US{i:02d}": _frame(200 + i) for i in range(6)}
    out.update({f"KR{i:02d}": _frame(300 + i) for i in range(6)})
    out["SPY"] = _frame(998)
    out["^KS200"] = _frame(997)
    return out


@pytest.fixture(scope="module")
def two_region_universe(two_region_prices) -> dict:
    return {"US": [t for t in two_region_prices if t.startswith("US")],
            "KR": [t for t in two_region_prices if t.startswith("KR")]}


# --------------------------------------------------------------------------- #
# 1. The false all-clear: one region priced perfectly, the other undescribed
# --------------------------------------------------------------------------- #
def test_undescribed_region_is_not_zero_affected_observations(two_region_universe):
    """The exact shape of the live membership file: US rows, no KR rows.

    Every US name is described and priceable, so the pricing gap is nil and the
    old `100 - constituentCoveragePct` reported 0.0% affected. Half the book
    was membership-unknown at the time.
    """
    memberships = {t: {"listed": "2010-01-01", "delisted": None, "region": "US"}
                   for t in two_region_universe["US"]}
    snapshot = pit_data.UniverseHistory(memberships).snapshot(
        "2019-01-02", two_region_universe, view=_AllPriced(), min_history=1)

    assert snapshot.coverage_pct == 100.0           # the pricing half is clean
    assert snapshot.missing_prices == []
    assert snapshot.survivorship_risk == "HIGH"     # and the risk is still HIGH
    # The number published beside that risk must agree with it.
    assert snapshot.unvouched == len(two_region_universe["KR"])
    assert snapshot.unvouched_pct == 50.0
    assert snapshot.regions["KR"]["membershipKnown"] == 0
    assert snapshot.regions["US"]["unvouched"] == 0


def test_worst_region_decides_the_risk_not_the_pooled_average(two_region_universe):
    """A large clean region must not pay for a small unresolved one."""
    memberships = {t: {"listed": "2010-01-01", "delisted": None, "region": "US"}
                   for t in two_region_universe["US"]}
    # 100 US names described against 6 Korean ones that are not: pooled
    # membership coverage is 94.3%, which reads as a partial gap. The Korean
    # cross-section is 0% described.
    wide = dict(two_region_universe)
    wide["US"] = wide["US"] + [f"US{i:02d}" for i in range(6, 100)]
    memberships.update({t: {"listed": "2010-01-01", "delisted": None, "region": "US"}
                        for t in wide["US"]})
    snapshot = pit_data.UniverseHistory(memberships).snapshot(
        "2019-01-02", wide, view=_AllPriced(), min_history=1)

    assert snapshot.membership_coverage_pct > 94.0  # pooled: looks like a nick
    assert snapshot.regions["KR"]["unvouched"] == 6  # per region: a whole sleeve
    assert snapshot.survivorship_risk == "HIGH"


def test_a_name_both_unpriced_and_unknown_is_counted_once(two_region_universe):
    """The union, not the sum. Adding the gaps overstates as surely as hiding one."""
    memberships = {t: {"listed": "2010-01-01", "delisted": None, "region": "US"}
                   for t in two_region_universe["US"]}

    class NothingPriced:
        def has_history(self, ticker: str, rows: int) -> bool:
            return False

    snapshot = pit_data.UniverseHistory(memberships).snapshot(
        "2019-01-02", two_region_universe, view=NothingPriced(), min_history=1)
    # Every Korean name is unpriced AND membership-unknown.
    assert snapshot.regions["KR"]["missingPrices"] == 6
    assert snapshot.regions["KR"]["membershipUnknown"] == 6
    assert snapshot.regions["KR"]["unvouched"] == 6
    assert snapshot.unvouched_pct == 100.0


# --------------------------------------------------------------------------- #
# 2. The replay publishes where and when
# --------------------------------------------------------------------------- #
def test_replay_reports_the_gap_by_region(two_region_prices, two_region_universe):
    memberships = {t: {"listed": "2010-01-01", "delisted": None, "region": "US"}
                   for t in two_region_universe["US"]}
    replay = HR.run_replay(
        two_region_prices, two_region_universe,
        benchmarks={"US": "SPY", "KR": "^KS200"},
        cfg_lt={"minFactorSleeves": 1, "minFinancialCoverage": 0.0},
        start="2018-01-01", end="2018-06-30", frequency="M",
        universe_history=pit_data.UniverseHistory(memberships), model_version="test")
    diagnostics = replay["diagnostics"]

    by_region = diagnostics["universeCoverageByRegion"]
    assert by_region["US"]["survivorshipRisk"] == "LOW"
    assert by_region["KR"]["survivorshipRisk"] == "HIGH"
    assert by_region["KR"]["membershipCoveragePct"] == 0.0
    assert by_region["US"]["affectedObservationsPct"] == 0.0
    assert by_region["KR"]["affectedObservationsPct"] == 100.0

    assert diagnostics["survivorshipRisk"] == "HIGH"
    assert diagnostics["worstCoveredRegion"] == "KR"
    # The headline agrees with the risk instead of contradicting it, and names
    # only the region that actually carries the gap.
    assert diagnostics["affectedObservationsPct"] > 0
    assert diagnostics["affectedRegions"] == ["KR"]


def test_two_runs_with_the_same_pooled_coverage_and_opposite_shapes():
    """The point of the per-year split.

    The need is front-loaded: the 2013 S&P 500 is missing 219 of 500 names
    before any vendor is asked, the 2025 one 34. A vendor serving only recent
    delistings and one serving only old ones can report the same pooled
    coverage; only the year each name left tells them apart.
    """
    early_then_fixed = [{"expected": 100, "priced": 50, "membershipKnown": 100, "unvouched": 50},
                        {"expected": 100, "priced": 100, "membershipKnown": 100, "unvouched": 0}]
    fine_then_broken = [{"expected": 100, "priced": 100, "membershipKnown": 100, "unvouched": 0},
                        {"expected": 100, "priced": 50, "membershipKnown": 100, "unvouched": 50}]

    def pooled(rows):
        total = HR._empty_coverage()
        for row in rows:
            HR._accumulate_coverage(total, row)
        return HR._coverage_report(total)["constituentCoveragePct"]

    assert pooled(early_then_fixed) == pooled(fine_then_broken) == 75.0
    assert (HR._coverage_report(early_then_fixed[0])["constituentCoveragePct"]
            != HR._coverage_report(fine_then_broken[0])["constituentCoveragePct"])


def test_replay_reports_the_gap_by_year(two_region_prices, two_region_universe):
    us_only = {"US": two_region_universe["US"]}
    memberships = {t: {"listed": "2010-01-01", "delisted": None, "region": "US"}
                   for t in us_only["US"]}
    # One name leaves the index mid-2018 and the price panel keeps serving it,
    # so 2018 is fully covered and 2019 is short one describable name.
    memberships["GONE"] = {"listed": "2010-01-01", "delisted": "2018-07-01", "region": "US"}
    replay = HR.run_replay(
        two_region_prices, us_only, benchmarks={"US": "SPY"},
        cfg_lt={"minFactorSleeves": 1, "minFinancialCoverage": 0.0},
        start="2018-01-01", end="2019-06-30", frequency="Q",
        universe_history=pit_data.UniverseHistory(memberships), model_version="test")
    by_year = {row["year"]: row for row in replay["diagnostics"]["universeCoverageByYear"]}

    assert set(by_year) == {2018, 2019}
    # GONE is listed in the first half of 2018 and unpriceable, so that year
    # carries a gap the later one does not.
    assert by_year[2018]["affectedObservationsPct"] > 0
    assert by_year[2019]["affectedObservationsPct"] == 0.0
    assert replay["diagnostics"]["worstCoveredYear"] == 2018


def test_headline_and_breakdown_are_the_same_measurement(two_region_prices,
                                                        two_region_universe):
    """One accumulator, two resolutions — not two numbers that can drift.

    The pooled figure and the per-region one used to be weighted differently
    (a share of names against an average over dates), which is how a gate and
    the panel beside it come to disagree about the same ledger.
    """
    memberships = {t: {"listed": "2010-01-01", "delisted": None, "region": "US"}
                   for t in two_region_universe["US"]}
    diagnostics = HR.run_replay(
        two_region_prices, two_region_universe,
        benchmarks={"US": "SPY", "KR": "^KS200"},
        cfg_lt={"minFactorSleeves": 1, "minFinancialCoverage": 0.0},
        start="2018-01-01", end="2018-06-30", frequency="M",
        universe_history=pit_data.UniverseHistory(memberships),
        model_version="test")["diagnostics"]

    by_region = diagnostics["universeCoverageByRegion"]
    by_year = diagnostics["universeCoverageByYear"]
    name_dates = sum(row["nameDates"] for row in by_region.values())
    assert name_dates == sum(row["nameDates"] for row in by_year)

    for key in ("affectedObservationsPct", "membershipCoveragePct",
                "constituentCoveragePct"):
        weighted = sum(row["nameDates"] * row[key] for row in by_region.values()) / name_dates
        assert diagnostics[key] == pytest.approx(weighted, abs=1e-4)


# --------------------------------------------------------------------------- #
# 3. The gate has to clear both gaps
# --------------------------------------------------------------------------- #
def _diagnostics(**overrides) -> dict:
    base = {"historicalUniverseAvailable": True, "constituentCoveragePct": 100.0,
            "membershipCoveragePct": 100.0, "survivorshipRisk": "LOW",
            "fundamentalsPit": True, "macroPitStatus": pit_data.PIT_EXACT,
            "benchmarkCoverageGate": {"eligible": True}}
    base.update(overrides)
    return base


def test_priced_but_undescribed_does_not_pass_the_integrity_gate():
    """The false all-clear this change exists to remove.

    Every described name priced, one region undescribed. Before this, the gate
    read `constituentCoveragePct == 100.0`, passed, and labelled the result
    HISTORICAL_OOS while `survivorshipRisk` in the same dict said HIGH.
    """
    gate = PV.data_integrity(
        _diagnostics(membershipCoveragePct=81.14, survivorshipRisk="HIGH",
                     affectedObservationsPct=18.86, affectedRegions=["KR"]),
        [{"region": "US"}, {"region": "KR"}])
    assert gate["integrityGate"]["checks"]["historicalUniverse"] is False
    assert gate["integrityGate"]["eligible"] is False
    assert gate["historicalResultLabel"] == "SURVIVORSHIP_BIAS_UNRESOLVED"
    assert gate["impactOnPromotionEligibility"] == "KELLY_AND_SELECTOR_PROMOTION_BLOCKED"
    assert gate["affectedRegions"] == ["KR"]


def test_both_gaps_closed_still_passes():
    gate = PV.data_integrity(_diagnostics(), [{"region": "US"}])
    assert gate["integrityGate"]["checks"]["historicalUniverse"] is True
    assert gate["historicalResultLabel"] == "HISTORICAL_OOS"


def test_an_unmeasured_membership_gap_is_unassessable_not_a_pass():
    """A check that could not be assessed is None, never True."""
    diagnostics = _diagnostics()
    diagnostics.pop("membershipCoveragePct")
    gate = PV.data_integrity(diagnostics, [{"region": "US"}])
    assert gate["integrityGate"]["checks"]["historicalUniverse"] is None
    assert gate["integrityGate"]["unassessable"] == ["historicalUniverse"]
    assert gate["integrityGate"]["failures"] == []
    assert gate["integrityGate"]["eligible"] is False
    assert gate["historicalResultLabel"] == "SURVIVORSHIP_BIAS_UNRESOLVED"


def test_full_fidelity_and_the_gate_read_the_same_predicate():
    """One definition of "the cross-section can be vouched for", not two.

    `portfolio_replay` gates the full-fidelity claim on it and `data_integrity`
    gates promotion on it. Two copies of a four-clause condition is how one of
    them comes to be fixed and the other not.
    """
    assert PV.universe_ready(_diagnostics()) is True
    assert PV.universe_ready(_diagnostics(membershipCoveragePct=81.14)) is False
    assert PV.universe_ready(_diagnostics(constituentCoveragePct=72.41)) is False
    assert PV.universe_ready(_diagnostics(historicalUniverseAvailable=False)) is False

    unmeasured = _diagnostics()
    unmeasured.pop("membershipCoveragePct")
    assert PV.universe_ready(unmeasured) is None
