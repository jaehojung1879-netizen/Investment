"""Does the alpha test actually work — both directions.

A significance test is only worth publishing if it rejects at roughly its stated
rate under the null AND detects a real effect. These check both, because the
whole point of the null is to stop a number like "annualized excess +0.27%,
IR 0.004" being read as an edge.
"""
from __future__ import annotations

import numpy as np
import pytest

from pipeline import portfolio_validation as PV
from pipeline import selection_null as SN


# --------------------------------------------------------------------------- #
# Size and power
# --------------------------------------------------------------------------- #
def test_pure_noise_is_called_indistinguishable_at_about_the_stated_rate():
    """Size. The actual statistic is drawn from the null itself."""
    rng = np.random.default_rng(4)
    rejections = 0
    trials = 400
    for _ in range(trials):
        null = rng.normal(size=200)
        actual = float(rng.normal())
        if SN.summarize(actual, null, alpha=0.05)["verdict"] == SN.BEATS:
            rejections += 1
    rate = rejections / trials
    # 5% nominal; the +1 correction makes it very slightly conservative.
    assert 0.01 <= rate <= 0.09, rate


def test_a_real_effect_is_detected():
    """Power. A statistic well outside the null is called out."""
    rng = np.random.default_rng(5)
    null = rng.normal(size=200)
    assert SN.summarize(3.0, null)["verdict"] == SN.BEATS


def test_a_statistic_below_the_null_is_called_worse_not_merely_unproven():
    rng = np.random.default_rng(6)
    null = rng.normal(size=200)
    result = SN.summarize(-3.0, null)
    assert result["verdict"] == SN.WORSE
    assert result["percentileOfNull"] < 5


def test_the_p_value_is_never_zero():
    """The +1 correction: 200 draws cannot evidence p < 1/201."""
    result = SN.summarize(1e9, np.random.default_rng(7).normal(size=200))
    assert result["pValueBeatsRandom"] == round(1 / 201, 4)   # reported to 4dp
    assert result["pValueBeatsRandom"] > 0


def test_too_few_draws_is_not_assessed_rather_than_passed():
    result = SN.summarize(5.0, [0.1, 0.2, 0.3])
    assert result["verdict"] == SN.NOT_ASSESSED
    assert "insufficient_draws" in result["reason"]


def test_a_missing_statistic_is_not_assessed_rather_than_failed():
    assert SN.summarize(None, np.random.default_rng(8).normal(size=200)
                        )["verdict"] == SN.NOT_ASSESSED


# --------------------------------------------------------------------------- #
# The risk-adjusted requirement
# --------------------------------------------------------------------------- #
def _stat(verdict):
    return {"verdict": verdict}


def test_beating_the_null_on_raw_return_alone_is_not_an_edge():
    """Extra return bought with extra risk is not what a concentrated book is for."""
    overall = SN.overall_verdict({
        "annualizedExcessPct": _stat(SN.BEATS),
        "informationRatio": _stat(SN.INDISTINGUISHABLE),
        "sharpe": _stat(SN.INDISTINGUISHABLE),
    })
    assert overall["verdict"] == SN.INDISTINGUISHABLE
    assert overall["beatsRandomOn"] == ["annualizedExcessPct"]


def test_clearing_the_null_on_both_risk_adjusted_statistics_is_an_edge():
    overall = SN.overall_verdict({
        "annualizedExcessPct": _stat(SN.INDISTINGUISHABLE),
        "informationRatio": _stat(SN.BEATS),
        "sharpe": _stat(SN.BEATS),
    })
    assert overall["verdict"] == SN.BEATS


def test_nothing_assessable_is_reported_as_not_assessed():
    overall = SN.overall_verdict({"informationRatio": _stat(SN.NOT_ASSESSED)})
    assert overall["verdict"] == SN.NOT_ASSESSED


def test_the_null_states_that_it_does_not_test_the_research_screen():
    overall = SN.overall_verdict({"sharpe": _stat(SN.INDISTINGUISHABLE)})
    assert overall["scope"] == "RANDOM_RANK_WITHIN_RESEARCH_POOL"
    assert "후보군" in overall["scopeNoteKo"]


# --------------------------------------------------------------------------- #
# Random ranking preserves everything except the ordering
# --------------------------------------------------------------------------- #
def _scored(rows):
    return [{"ticker": t, "region": r, "sector": sec, "convictionScore": score,
             "score": score, "eligible": not codes, "exclusionCodes": list(codes)}
            for t, r, sec, score, codes in rows]


def test_the_alpha_floor_is_dropped_because_it_is_itself_a_score_decision():
    """A null bound by the alpha floor could only pick names alpha approved."""
    scored = _scored([("A", "US", "Tech", 5.0, []),
                      ("B", "US", "Tech", 0.0, ["ALPHA_BELOW_SELECTION_FLOOR"])])

    out = SN.permuted_scores(scored, np.random.default_rng(1))

    assert all(row["eligible"] for row in out)
    assert out[1]["exclusionCodes"] == []


def test_data_and_state_exclusions_are_still_honoured():
    """Those are facts about the name, true whatever the ranking says."""
    scored = _scored([("A", "US", "Tech", 5.0, []),
                      ("B", "US", "Tech", 1.0, ["ENTRY_OR_RESEARCH_STATE_BLOCKS_SIZING"]),
                      ("C", "US", "Tech", 2.0, ["NO_FACTOR_EVIDENCE"])])

    out = {row["ticker"]: row for row in SN.permuted_scores(scored, np.random.default_rng(1))}

    assert out["A"]["eligible"] is True
    assert out["B"]["eligible"] is False
    assert out["C"]["eligible"] is False


def test_the_multiset_of_scores_is_preserved_only_reattached():
    scored = _scored([(f"T{i}", "US", "S", float(i), []) for i in range(12)])

    out = SN.permuted_scores(scored, np.random.default_rng(2))

    assert sorted(r["score"] for r in out) == sorted(float(i) for i in range(12))
    assert [r["ticker"] for r in out] == [f"T{i}" for i in range(12)]
    assert [r["score"] for r in out] != [float(i) for i in range(12)]


def test_an_excluded_name_never_receives_a_permuted_score():
    scored = _scored([("A", "US", "S", 9.0, []),
                      ("B", "US", "S", 0.0, ["NO_FACTOR_EVIDENCE"])])

    out = {row["ticker"]: row for row in SN.permuted_scores(scored, np.random.default_rng(3))}

    assert out["A"]["score"] == 9.0     # sole eligible name keeps its own score
    assert out["B"]["score"] == 0.0


def test_the_input_rows_are_not_mutated():
    scored = _scored([(f"T{i}", "US", "S", float(i), []) for i in range(8)])
    before = [row["score"] for row in scored]

    SN.permuted_scores(scored, np.random.default_rng(4))

    assert [row["score"] for row in scored] == before


def test_two_draws_produce_different_orderings():
    scored = _scored([(f"T{i}", "US", "S", float(i), []) for i in range(20)])
    order = lambda seed: [r["ticker"] for r in sorted(
        SN.permuted_scores(scored, np.random.default_rng(seed)), key=lambda x: -x["score"])]
    assert order(1) != order(2)


def test_the_permutation_matches_production_selection_shape():
    """A permuted row must be accepted by the real selector unchanged."""
    from pipeline import kelly_portfolio as KP
    candidates = [{"ticker": f"T{i}", "region": "US", "sector": f"S{i % 3}",
                   "alphaPercentile": 70 + i, "evidenceCoverage": 0.8,
                   "risk": {"downsideVolPct": 20.0}, "entryState": "ACCUMULATE_GRADUALLY",
                   # Without this the entry-state multiplier is 0 and every name
                   # is excluded before the ranking is ever consulted.
                   "longTermResearchView": "POSITIVE"}
                  for i in range(10)]
    cfg = {"selection": {"targetNames": 5, "minNames": 3, "maxNamesPerSector": 2,
                         "maxNamesPerRegion": 5, "minAlphaPercentile": 66}}

    scored = KP.conviction_scores(candidates, cfg)
    selected, meta = KP.select_portfolio_by_scores(
        candidates, SN.permuted_scores(scored, np.random.default_rng(5)),
        cfg, method=SN.NULL_METHOD)

    assert 0 < len(selected) <= 5
    assert meta["maxNamesPerSector"] == 2


# --------------------------------------------------------------------------- #
# Like-for-like comparison
# --------------------------------------------------------------------------- #
def _rows(dates, excess, horizon=21):
    import pandas as pd
    return [{"date": d,
             "endDate": (pd.Timestamp(d) + pd.offsets.BDay(horizon)).strftime("%Y-%m-%d"),
             "costAdjustedExcessReturn": e,
             "costAdjustedReturn": e, "benchmarkReturn": 0.0,
             "grossExcessReturn": e, "grossReturn": e,
             "weights": {"A": 1.0}, "regionByTicker": {"A": "US"},
             "turnover": 0.0, "transactionCost": 0.0,
             "top1": 1.0, "top3": 1.0, "effectiveNames": 1.0}
            for d, e in zip(dates, excess)]


def test_selectors_are_compared_on_one_shared_block_schedule():
    """The 08-22 defect: champion from 2013-01, challenger from 2013-11."""
    import pandas as pd
    all_dates = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2020-01-01", periods=200)]
    champion = _rows(all_dates, np.zeros(len(all_dates)))
    challenger = _rows(all_dates[40:], np.zeros(len(all_dates) - 40))

    shared = PV.shared_block_dates({"C": champion, "H": challenger}, 21)

    assert shared[0] == all_dates[40]          # starts where BOTH are measurable
    assert set(shared) <= set(d["date"] for d in challenger)


def test_a_tiny_edge_on_130_blocks_is_reported_as_indistinguishable():
    import pandas as pd
    dates = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2014-01-01", periods=130)]
    rng = np.random.default_rng(3)
    # Each selector carries its own idiosyncratic noise. Pairing removes only
    # the COMMON component, so the difference still has real variance — giving
    # both series the identical noise track would make a constant offset
    # detectable at any size, which is not the situation being tested.
    champion = _rows(dates, rng.normal(0, 0.05, len(dates)) + 0.0002)
    challenger = _rows(dates, rng.normal(0, 0.05, len(dates)))

    result = PV.paired_comparison({PV.CHAMPION: champion, PV.CHALLENGER: challenger},
                                  dates, horizon=21)

    assert result["available"] is True
    assert result["verdict"] == "INDISTINGUISHABLE"
    low, high = result["championMinusChallengerCi95Pct"]
    assert low < 0 < high


def test_a_large_consistent_edge_does_separate():
    import pandas as pd
    dates = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2014-01-01", periods=130)]
    rng = np.random.default_rng(3)
    result = PV.paired_comparison(
        {PV.CHAMPION: _rows(dates, rng.normal(0, 0.01, len(dates)) + 0.02),
         PV.CHALLENGER: _rows(dates, rng.normal(0, 0.01, len(dates)))},
        dates, horizon=21)

    assert result["verdict"] == "CHAMPION_BETTER"
    assert result["championMinusChallengerCi95Pct"][0] > 0


def test_comparison_refuses_when_one_selector_is_not_measurable_on_a_block():
    import pandas as pd
    dates = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2014-01-01", periods=10)]
    result = PV.paired_comparison(
        {PV.CHAMPION: _rows(dates, np.zeros(10)),
         PV.CHALLENGER: _rows(dates[:5], np.zeros(5))},
        dates, horizon=21)

    assert result["available"] is False
    assert result["reason"] == "selectors_not_measurable_on_same_blocks"


# --------------------------------------------------------------------------- #
# Cost accounting
# --------------------------------------------------------------------------- #
def test_selling_a_name_out_of_the_book_is_charged_not_free():
    """The exit leg was costing nothing whenever a name left the portfolio.

    `_turnover_cost` looks the region up per ticker; building that list from the
    surviving weights alone leaves a sold name region-less, and every bps
    default is 0. KR sells carry a 20bp tax, so this was not a rounding error.
    """
    import pandas as pd
    cfg = {"transactionCosts": {"KR": {"commissionBps": 5, "sellTaxBps": 20,
                                       "spreadBps": 12}}}
    rows = []
    for index, (date, held) in enumerate([("2020-01-06", "A"), ("2020-02-06", "B")]):
        rows.append({
            "date": date,
            "endDate": (pd.Timestamp(date) + pd.offsets.BDay(21)).strftime("%Y-%m-%d"),
            "weights": {held: 1.0}, "regionByTicker": {held: "KR"},
            "grossReturn": 0.0, "benchmarkReturn": 0.0, "grossExcessReturn": 0.0,
            "costAdjustedReturn": 0.0, "costAdjustedExcessReturn": 0.0,
            "turnover": 0.0, "transactionCost": 0.0,
            "top1": 1.0, "top3": 1.0, "effectiveNames": 1.0,
        })

    PV._path_metrics(rows, 21, cfg)

    # Block 2 sells all of A and buys all of B: both legs must be charged.
    buy = (5 + 12 / 2) / 10000
    sell = (5 + 20 + 12 / 2) / 10000
    assert rows[1]["transactionCost"] == pytest.approx(buy + sell, rel=1e-9)
    assert rows[1]["transactionCost"] > buy
