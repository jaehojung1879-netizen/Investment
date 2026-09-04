"""The survivorship bound: what it claims, and the three ways it must refuse.

`historicalUniverse` cannot be opened by collecting more — `universe_ready`
wants both coverages at exactly 100.0 and neither half reaches it on the free
vendors. So the question the gate stands for is answered directly: does the
paired selector difference keep its sign when the measured gap takes its worst
plausible outcome. These tests pin that the bound reduces to the published
number at zero stress (otherwise the sweep stresses a different statistic),
that it uses each region's OWN measured gap, that it refuses rather than
substitutes where a tail cannot be measured, and — the one that matters most —
that it never reports itself as opening the gate.
"""
from __future__ import annotations

import numpy as np
import pytest

from pipeline import portfolio_validation as PV

CH, CL = PV.CHAMPION, PV.CHALLENGER
DATES = [f"2020-{month:02d}-01" for month in range(1, 13)]


def _row(date, *, excess_by_region, weight_by_region, cost=0.001):
    gross_excess = sum(excess_by_region.values())
    return {"date": date, "endDate": date, "transactionCost": cost,
            "weightByRegion": dict(weight_by_region),
            "excessByRegion": dict(excess_by_region),
            "grossExcessReturn": gross_excess,
            "costAdjustedExcessReturn": gross_excess - cost}


def _rows(per_date_excess, *, region="US", weight=0.9, cost=0.001):
    return [_row(date, excess_by_region={region: value},
                 weight_by_region={region: weight}, cost=cost)
            for date, value in zip(DATES, per_date_excess)]


def _outcomes(regions=("US",), tail=-0.20, n=20):
    """A cross-section wide enough to have a tail, ending at `tail`."""
    out = []
    for date in DATES:
        for region in regions:
            for i in range(n):
                out.append({
                    "id": f"{date}-{region}-{i}", "date": date,
                    "ticker": f"{region}{i}", "region": region,
                    "horizons": {"21": {"endDate": date,
                                        "excessReturn": tail + i * 0.02,
                                        "absoluteReturn": tail + i * 0.02,
                                        "benchmarkReturn": 0.0}},
                })
    return out


def _diagnostics(gap_by_region):
    return {"universeCoverageByRegion": {
        region: {"affectedObservationsPct": pct}
        for region, pct in gap_by_region.items()}}


# --------------------------------------------------------------------------- #
# The property the whole sweep rests on
# --------------------------------------------------------------------------- #
def test_zero_stress_reproduces_the_published_number_exactly():
    # If it did not, the sweep would be stressing a different statistic from
    # the one the report publishes, and its verdict would not be about it.
    row = _row("2020-01-01", excess_by_region={"US": 0.02, "KR": -0.01},
               weight_by_region={"US": 0.6, "KR": 0.3}, cost=0.004)
    value = PV._stressed_excess(row, {"US": 0.17, "KR": 1.0}, {}, 0.0)
    assert value == pytest.approx(row["costAdjustedExcessReturn"])


def test_a_region_with_no_measured_gap_is_left_untouched():
    row = _row("2020-01-01", excess_by_region={"US": 0.02},
               weight_by_region={"US": 0.9})
    # No gap for US at all -> nothing is replaced, and no tail is needed.
    assert PV._stressed_excess(row, {}, {}, 1.0) == pytest.approx(
        row["costAdjustedExcessReturn"])


def test_each_region_is_stressed_by_its_own_gap_not_a_pooled_one():
    row = _row("2020-01-01", excess_by_region={"US": 0.02, "KR": 0.02},
               weight_by_region={"US": 0.45, "KR": 0.45}, cost=0.0)
    worst = {("2020-01-01", "US"): -0.10, ("2020-01-01", "KR"): -0.10}
    # KR is entirely unvouched and US only 17%: the KR sleeve must take far
    # more damage than the US one, which a pooled gap would flatten.
    only_us = PV._stressed_excess(row, {"US": 0.17, "KR": 0.0}, worst, 1.0)
    only_kr = PV._stressed_excess(row, {"US": 0.0, "KR": 1.0}, worst, 1.0)
    assert only_kr < only_us < row["costAdjustedExcessReturn"]


def test_a_region_date_without_a_measurable_tail_is_refused_not_substituted():
    row = _row("2020-01-01", excess_by_region={"US": 0.02},
               weight_by_region={"US": 0.9})
    assert PV._stressed_excess(row, {"US": 0.17}, {}, 1.0) is None


def test_a_thin_cross_section_has_no_tail_to_take_a_quantile_of():
    thin = [{"id": f"x{i}", "date": "2020-01-01", "ticker": f"t{i}",
             "region": "KR",
             "horizons": {"21": {"endDate": "2020-01-01", "excessReturn": -0.1 + i}}}
            for i in range(PV.MIN_TAIL_CROSS_SECTION - 1)]
    assert PV.worst_case_excess(thin, horizon=21) == {}


def test_the_tail_comes_from_observed_returns_not_an_invented_number():
    worst = PV.worst_case_excess(_outcomes(tail=-0.20, n=20), horizon=21,
                                 quantile=0.05)
    observed = {-0.20 + i * 0.02 for i in range(20)}
    value = worst[("2020-01-01", "US")]
    assert min(observed) <= value <= max(observed)


# --------------------------------------------------------------------------- #
# End to end: survives, fails, and nothing to bound
# --------------------------------------------------------------------------- #
def _bound(champion, challenger, gap, *, regions=("US",), weight=0.9, tail=-0.20):
    return PV.survivorship_bound(
        {CH: _rows(champion, region=regions[0], weight=weight),
         CL: _rows(challenger, region=regions[0], weight=weight)},
        DATES, _outcomes(regions, tail=tail), _diagnostics(gap), horizon=21)


def test_a_wide_separation_survives_the_measured_gap():
    # The challenger is far ahead on every block, and both books sit in the
    # same region, so the stress hits them almost equally.
    report = _bound([0.00] * 12, [0.08] * 12, {"US": 17.2})
    assert report["available"] is True
    assert report["baseline"]["verdict"] == "CHALLENGER_BETTER"
    assert report["verdict"] == "SURVIVES_MEASURED_GAP"
    assert report["breakdownScale"] is None


def test_no_separation_to_begin_with_is_reported_as_nothing_to_bound():
    rng = np.random.default_rng(3)
    noise = rng.normal(0, 0.05, 12)
    report = _bound(list(noise), list(-noise), {"US": 17.2})
    assert report["verdict"] == "NOTHING_TO_BOUND"
    assert report["breakdownScale"] is None


def test_an_unmeasured_regional_gap_refuses_rather_than_assuming_zero():
    report = PV.survivorship_bound(
        {CH: _rows([0.0] * 12), CL: _rows([0.08] * 12)}, DATES, _outcomes(),
        {"universeCoverageByRegion": {"US": {"affectedObservationsPct": None}}},
        horizon=21)
    assert report["available"] is False
    assert report["reason"] == "universe_gap_not_measured"


def test_the_sweep_runs_from_zero_to_the_whole_measured_gap():
    report = _bound([0.0] * 12, [0.08] * 12, {"US": 17.2})
    scales = [step["stressScale"] for step in report["sweep"]]
    assert scales[0] == 0.0 and scales[-1] == 1.0
    assert report["gapByRegion"] == {"US": 17.2}


# --------------------------------------------------------------------------- #
# The claim it must never make
# --------------------------------------------------------------------------- #
def test_the_bound_never_reports_itself_as_opening_the_integrity_gate():
    report = _bound([0.0] * 12, [0.08] * 12, {"US": 17.2})
    assert report["verdict"] == "SURVIVES_MEASURED_GAP"
    assert report["opensIntegrityGate"] is False
    assert "integrityGate" not in report


def test_the_quantile_behind_the_verdict_is_published_with_it():
    report = _bound([0.0] * 12, [0.08] * 12, {"US": 17.2})
    # A bound is a claim under a stated assumption; the assumption travels with
    # it or the verdict reads as unconditional.
    assert report["worstCaseQuantile"] == 0.05
    assert report["gapByRegion"]


def test_a_narrow_separation_in_the_unvouched_region_does_not_survive():
    """The case the bound exists for, and the one it must not wave through.

    The challenger's edge sits entirely in KR, which is 100% unvouched, while
    the champion sits in US at 17%. Unstressed the challenger separates; once
    the Korean sleeve is replaced by what Korean names in that cross-section
    actually delivered at the 5th percentile, the edge is gone. A bound that
    reported SURVIVES here would be a rubber stamp.
    """
    champion = [_row(date, excess_by_region={"US": 0.005},
                     weight_by_region={"US": 0.9}, cost=0.0) for date in DATES]
    challenger = [_row(date, excess_by_region={"KR": 0.02},
                       weight_by_region={"KR": 0.9}, cost=0.0) for date in DATES]
    report = PV.survivorship_bound(
        {CH: champion, CL: challenger}, DATES,
        _outcomes(regions=("US", "KR"), tail=-0.20),
        _diagnostics({"US": 17.2, "KR": 100.0}), horizon=21)
    assert report["baseline"]["verdict"] == "CHALLENGER_BETTER"
    assert report["verdict"] in {"FAILS_MEASURED_GAP", "REVERSES_UNDER_MEASURED_GAP"}
    assert report["breakdownScale"] is not None
    assert 0.0 < report["breakdownScale"] <= 1.0


def test_a_reversal_is_a_breakdown_and_not_reported_as_never_broke():
    """Keying the breakdown on `separated` alone hid the worst case.

    A stress that flips the sign while the interval still clears zero has
    broken the finding harder than one that merely widens it past zero. Reading
    only `separated`, that reversal produced `breakdownScale: None` — the same
    value a finding that held at every scale reports.
    """
    champion = [_row(date, excess_by_region={"US": 0.005},
                     weight_by_region={"US": 0.9}, cost=0.0) for date in DATES]
    challenger = [_row(date, excess_by_region={"KR": 0.02},
                       weight_by_region={"KR": 0.9}, cost=0.0) for date in DATES]
    report = PV.survivorship_bound(
        {CH: champion, CL: challenger}, DATES,
        _outcomes(regions=("US", "KR"), tail=-0.20),
        _diagnostics({"US": 17.2, "KR": 100.0}), horizon=21)
    assert report["atMeasuredGap"]["verdict"] == "CHAMPION_BETTER"
    assert report["atMeasuredGap"]["separated"] is True
    assert report["breakdownScale"] is not None
