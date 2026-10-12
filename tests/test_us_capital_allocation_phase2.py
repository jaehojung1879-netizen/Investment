"""Phase 2: outcome-blind diagnostics, candidate source views, multifactor inputs, monitoring and the pilot preflight. Synthetic data only."""
from __future__ import annotations

import copy
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import price_adjustment as PA                         # noqa: E402
from pipeline import us_capital_allocation_diagnostics as DG        # noqa: E402
from pipeline import us_capital_allocation_monitoring as MO         # noqa: E402
from pipeline import us_capital_allocation_pilot as PI              # noqa: E402
from pipeline import us_capital_allocation_policy as P              # noqa: E402
from pipeline import us_capital_allocation_receipts as R            # noqa: E402
from pipeline import us_capital_allocation_source_views as V        # noqa: E402
from pipeline import us_capital_allocation_weekly as W              # noqa: E402
from pipeline import us_multifactor_inputs as M                     # noqa: E402
from pipeline import us_shareholder_distribution as U               # noqa: E402


# --------------------------------------------------------------------------- #
# Diagnostics
# --------------------------------------------------------------------------- #
def decision(date_, picks, passers=None, status="CANDIDATE_PORTFOLIO", skipped=()):
    selected = [{"ticker": t, "sector": s, "score": sc} for t, s, sc in picks]
    return date_, {"status": status, "selected": selected, "passers": passers if passers is not None else selected,
                   "skippedForSectorCap": list(skipped), "weights": {t: 0.15 for t, _, _ in picks} or None}


def test_decision_diagnostics_measures_turnover_persistence_and_concentration():
    a = [("AAA", "Industrials", .5), ("BBB", "Energy", .4), ("CCC", "Utilities", .3)]
    b = [("AAA", "Industrials", .5), ("BBB", "Energy", .4), ("DDD", "Utilities", .3)]
    decisions = [decision("2026-01-02", a), decision("2026-01-09", a), decision("2026-01-16", b), decision("2026-01-23", b),
                 decision("2026-01-30", [], status="BLOCKED")]
    out = DG.decision_diagnostics(decisions)
    assert out["weeks"] == 5 and out["status"] == {"BLOCKED": 1, "CANDIDATE_PORTFOLIO": 4} and out["blockedShare"] == 0.2
    assert out["participation"]["participationRate"] == 1.0
    assert out["turnover"]["consecutiveWeekPairs"] == 3 and out["turnover"]["weeksWithUnchangedSet"] == 2
    assert out["turnover"]["meanFractionReplaced"] == pytest.approx((0 + 1 / 3 + 0) / 3, abs=1e-4)
    assert out["distinctNames"]["everSelected"] == 4 and out["distinctNames"]["slotWeeks"] == 12
    assert out["persistence"]["holdingSpellsWeeks"]["max"] == 4          # AAA and BBB are held all four live weeks
    assert "mostFrequent" not in out["distinctNames"], "historical names are not published by default"
    assert "mostFrequent" in DG.decision_diagnostics(decisions, include_names=True)["distinctNames"]


def test_a_blocked_gap_is_not_counted_as_a_change_of_holdings():
    a = [("AAA", "Industrials", .5)]
    b = [("ZZZ", "Industrials", .5)]
    out = DG.decision_diagnostics([decision("2026-01-02", a), decision("2026-03-06", b)])      # more than ten days apart
    assert out["turnover"]["consecutiveWeekPairs"] == 0


def test_margins_report_how_close_the_fifth_name_is_to_the_first_excluded():
    picks = [("A%d" % i, "S%d" % i, 1.0 - 0.1 * i) for i in range(5)]
    passers = picks + [("X", "S9", 0.55), ("Y", "S9", 0.30)]
    out = DG.margins([decision("2026-01-02", picks, passers=[{"ticker": t, "sector": s, "score": sc} for t, s, sc in passers])])
    assert out["weeksWithFiveSelected"] == 1 and out["fifthOverFirst"]["p50"] == pytest.approx(0.6)
    assert out["excludedPassersWithin10PctOfFifth"]["median"] == 1.0          # X at 0.55 is within 10% of 0.60
    assert DG.margins([decision("2026-01-02", picks[:3])])["weeksWithFewerThanFive"] == 1


def row(ticker, growth, ratio, *, dividends=10.0, repurchases=40.0, dividend_yoy=0.0, repurchase_yoy=0.5, ocf=100.0):
    distribution = ratio * ocf
    score = P.incremental_over_ocf(ratio, growth)
    gate = None if growth >= P.MIN_DISTRIBUTION_GROWTH and score >= P.MIN_INCREMENTAL_OVER_OCF and ratio <= 1.0 else P.GATES[5]
    return {"ticker": ticker, "sector": "Industrials", "gate": gate, "score": score, "growth": growth, "ratio": ratio, "distribution": distribution,
            "ocf": ocf, "dividends": dividends, "repurchases": repurchases, "dividendYoY": dividend_yoy, "repurchaseYoY": repurchase_yoy}


def test_score_construction_states_hurdle_share_composition_and_payout_level():
    rows = [row("A", 0.50, 0.9), row("B", 0.20, 0.5), row("C", 0.02, 0.5), row("D", -0.2, 0.4), row("E", 0.15, 1.4)]
    week = {"date": "2026-01-02", "decision": {"selected": [{"ticker": "A"}]}, "rows": rows}
    out = DG.score_construction([week])
    assert out["measuredNameWeeks"] == 5
    assert out["hurdleVersusMedianGrowth"]["shareOfMeasuredAtOrAboveHurdle"] == pytest.approx(3 / 5)
    assert out["conditionalPass"]["growthAtLeastHurdle"] == pytest.approx(3 / 5)
    assert out["passers"]["nameWeeks"] == 2                                # E fails the cover gate (ratio > 1)
    assert out["passers"]["distributionAbove80PctOfOCF"] == pytest.approx(0.5)
    assert out["passers"]["increaseComposition"]["repurchaseLed"] == pytest.approx(1.0)
    assert DG.selected_composition([week])["repurchaseLed"] == pytest.approx(1.0)


def test_the_explainer_separates_accounting_characteristics_from_expected_return():
    text = DG.explainer()
    assert set(text) == {"A_accountingCharacteristic", "B_expectedReturnAdvantage", "verdict"}
    assert "no forecast" in text["verdict"]


# --------------------------------------------------------------------------- #
# Candidate source views: never zero, never an unverified guess
# --------------------------------------------------------------------------- #
def rec(cf, bs=(), ic=()):
    f = lambda rows: [{"concept": "us-gaap_" + c, "label": l, "unit": "usd", "value": v} for c, l, v in rows]      # noqa: E731
    return {"id": "X", "ticker": "X", "statements": {"cf": f(cf), "bs": f(bs), "ic": f(ic)}}


@pytest.mark.parametrize("cf,bs,expected", [
    ([("PaymentsOfDividendsCommonStock", "Dividends", 5)], [], "EXACT_CONCEPT_PRESENT"),
    ([("PaymentsOfDividends", "Payments for dividends", 5)], [], V.DIVIDEND_ACCEPT),
    ([("PaymentsOfDividends", "Payments for dividends", 5)], [("PreferredStockValue", "Preferred stock", 10)], "REJECT_PREFERRED_STOCK_OUTSTANDING"),
    ([("PaymentsOfDividends", "Payments for dividends", 5)], [("PreferredStockValue", "Preferred stock", 0)], V.DIVIDEND_ACCEPT),
    ([("PaymentsOfDividends", "Dividends paid to noncontrolling interests and preferred", 5)], [], "REJECT_OTHER_HOLDER_LABEL"),
    ([("PaymentsOfDividends", "Dividends", 5), ("PaymentsOfDividendsMinorityInterest", "Dividends to minority", 1)], [], "REJECT_OTHER_HOLDER_DIVIDEND_LINE"),
    ([("PaymentsOfDividends", "Dividends", 5), ("PaymentsOfOrdinaryDividends", "Ordinary", 4)], [], "REJECT_CONFLICTING_GENERAL_CONCEPTS"),
    ([("PaymentsOfOrdinaryDividends", "Ordinary dividends", 4)], [], "REJECT_ORDINARY_ONLY_EXCLUDES_SPECIAL_DIVIDENDS"),
    ([("NetIncomeLoss", "Net income", 3)], [], "NO_DIVIDEND_CONCEPT_IN_CASH_FLOW"),
])
def test_dividend_decisions_document_the_accepted_and_rejected_contexts(cf, bs, expected):
    assert V.dividend_decision(rec(cf, bs)) == expected


def test_operating_cash_flow_alias_is_refused_when_discontinued_operations_exist():
    assert V.ocf_decision(rec([("NetCashProvidedByUsedInOperatingActivitiesContinuingOperations", "Continuing", 9)])) == V.OCF_ACCEPT
    both = rec([("NetCashProvidedByUsedInOperatingActivitiesContinuingOperations", "Continuing", 9),
                ("CashProvidedByUsedInOperatingActivitiesDiscontinuedOperations", "Discontinued", 1)])
    assert V.ocf_decision(both) == "REJECT_DISCONTINUED_OPERATIONS_LINE"
    assert V.ocf_decision(rec([])) == "NO_OPERATING_CASH_FLOW_CONCEPT"


def annual(ticker, year, dividend_concept, dividends=20, repurchases=30, ocf=100):
    end = date(year, 12, 31)
    cf = [{"concept": "us-gaap_" + dividend_concept, "label": "Payments for dividends", "value": dividends, "unit": "usd"},
          {"concept": "us-gaap_PaymentsForRepurchaseOfCommonStock", "label": "Repurchases", "value": repurchases, "unit": "usd"},
          {"concept": "us-gaap_NetCashProvidedByUsedInOperatingActivities", "label": "OCF", "value": ocf, "unit": "usd"},
          {"concept": "us-gaap_PaymentsToAcquirePropertyPlantAndEquipment", "label": "Capex", "value": 10, "unit": "usd"}]
    return dict(id=f"{ticker}-{year}", ticker=ticker, source=U.SOURCE, fiscalYear=year, fiscalQuarter=0, form="10-K",
                periodStart=date(year, 1, 1).isoformat(), periodEnd=end.isoformat(), periodDays=(end - date(year, 1, 1)).days,
                availableFrom=(end + timedelta(days=30)).isoformat(), collectedAt="2026-02-01T00:00:00Z", acceptedDate=None,
                statements={"cf": cf, "ic": [], "bs": [{"concept": "us-gaap_CommonStockSharesOutstanding", "value": 100, "unit": "shares"}]})


def test_the_view_makes_a_general_dividend_measurable_without_touching_v1_or_inventing_a_zero():
    meta = U.SourceMetadata(U.SOURCE, "SYNTHETIC", "synthetic fiscal-YTD source contract")
    rows = [annual("GEN", 2023, "PaymentsOfDividends", 18), annual("GEN", 2024, "PaymentsOfDividends", 20)]
    v1 = U.derive_features("GEN", "2025-06-01", rows, meta)
    assert v1.features["cashDividendsPaidTTM"].state == U.State.AMBIGUOUS and v1.features["totalCashDistributionTTM"].value is None
    before = copy.deepcopy(rows)
    viewed = [V.candidate_view(r)[0] for r in rows]
    assert rows == before, "the view must not mutate its input"
    v2 = U.derive_features("GEN", "2025-06-01", viewed, meta)
    assert v2.features["cashDividendsPaidTTM"].value == 20 and v2.features["totalCashDistributionTTM"].value == 50
    # a rejected context stays ambiguous: nothing is filled
    pref = [annual("PRF", 2023, "PaymentsOfDividends", 18), annual("PRF", 2024, "PaymentsOfDividends", 20)]
    for r in pref:
        r["statements"]["bs"].append({"concept": "us-gaap_PreferredStockValue", "value": 100, "unit": "usd"})
    out = U.derive_features("PRF", "2025-06-01", [V.candidate_view(r)[0] for r in pref], meta)
    assert out.features["cashDividendsPaidTTM"].state == U.State.AMBIGUOUS and out.features["totalCashDistributionTTM"].value is None
    # the real v1 meaning of the exact-concept filing is untouched by the view
    exact = [annual("EXA", 2023, "PaymentsOfDividendsCommonStock", 18), annual("EXA", 2024, "PaymentsOfDividendsCommonStock", 20)]
    assert V.candidate_view(exact[0])[0] == exact[0]


def test_the_view_is_labelled_as_store_evidence_not_context_verification():
    assert V.EVIDENCE_LABEL == "STORE_EVIDENCE_NOT_CONTEXT_VERIFIED" and V.CANDIDATE_VERSION != U.FEATURE_VERSION


# --------------------------------------------------------------------------- #
# Multifactor inputs
# --------------------------------------------------------------------------- #
def vendor_frame(seed=3, n=300):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2020-01-01", periods=n)
    close = 100 * np.cumprod(1 + rng.normal(0, 0.01, n))
    frame = pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": close, "Volume": 1e6, "Dividends": 0.0, "Stock Splits": 0.0}, index=idx)
    for i, a in ((50, 0.5), (120, 0.8), (200, 0.6)):
        frame.iloc[i, frame.columns.get_loc("Dividends")] = a
    frame.iloc[150, frame.columns.get_loc("Stock Splits")] = 4.0
    return frame


def test_as_traded_close_is_recovered_exactly_from_the_total_return_index():
    frame = vendor_frame()
    result, _ = PA.to_total_return(frame)
    expected = frame["Close"].to_numpy() * PA.future_split_factor(frame["Stock Splits"].where(frame["Stock Splits"] > 0, 1.0))
    events = [(d, float(r["Dividends"]), float(r["Stock Splits"])) for d, r in result.iterrows()
              if r["Dividends"] > 0 or r["Stock Splits"] not in (0.0, 1.0)]
    rebuilt = M.as_traded_from_total_return(result.index.values, result["Close"].values, events)
    assert np.max(np.abs(rebuilt / expected - 1.0)) < 1e-12
    # without events the index IS the price
    assert np.array_equal(M.as_traded_from_total_return(result.index.values, result["Close"].values, []), result["Close"].values)


@pytest.mark.parametrize("fields,price,avail,splits,key,expected", [
    ({"epsTtm": 5.0}, 100.0, "2026-01-30", [], "earningsYield", 0.05),
    ({"epsTtm": -1.0}, 100.0, "2026-01-30", [], "earningsYield", None),
    ({"epsTtm": 5.0}, 100.0, "2026-01-30", [np.datetime64("2026-02-10")], "earningsYield", None),
    ({"epsTtm": 5.0}, 100.0, "2025-01-30", [], "earningsYield", None),
    ({"epsTtm": 5.0}, None, "2026-01-30", [], "earningsYield", None),
    ({"fcfPerShare": -2.0}, 100.0, "2026-01-30", [], "fcfYield", -0.02),
    ({}, 100.0, "2026-01-30", [], "bookYield", None),
])
def test_value_yields_withhold_rather_than_guess(fields, price, avail, splits, key, expected):
    out = M.value_yields(fields, price, avail, "2026-03-06", splits)
    assert (out[key] is None) if expected is None else out[key] == pytest.approx(expected)


def test_a_filing_that_is_not_yet_visible_is_refused():
    with pytest.raises(ValueError, match="FILING_NOT_VISIBLE"):
        M.value_yields({"epsTtm": 5.0}, 100.0, "2026-03-07", "2026-03-06")


# --------------------------------------------------------------------------- #
# Monitoring and schedule
# --------------------------------------------------------------------------- #
def synthetic_receipt():
    ctx, snapshot = PI.synthetic_world()
    return PI._build(W.observe_week(ctx, snapshot, PI.SIGNAL))      # noqa: SLF001


def frames_for(receipt, drift):
    entry = pd.Timestamp(receipt["executionDate"])
    days = R._sessions(entry, 200)                                    # noqa: SLF001
    out = {}
    for ticker, d in drift.items():
        out[ticker] = pd.DataFrame({"Close": 100.0 * np.cumprod(np.full(len(days), 1 + d)), "Dividends": 0.0, "Stock Splits": 0.0}, index=days)
    return out


def test_signal_monitor_is_descriptive_and_flags_synthetic_receipts_as_not_evidence():
    out = MO.signal_monitor([synthetic_receipt()])
    assert out["receipts"] == 1 and out["evidenceClass"] == "MIXED_OR_SYNTHETIC_NOT_EVIDENCE"
    assert out["participation"]["participationRate"] == 1.0 and "mostFrequent" in out["distinctNames"]
    assert MO.signal_monitor([]) == {"receipts": 0, "label": "NO_RECEIPTS_YET"}


def test_h21_is_refused_before_its_own_maturity_and_carries_no_inference():
    receipt = synthetic_receipt()
    drift = {t: 0.0004 for t in ("SPY", "QQQ", *receipt["decision"]["weights"])}
    drift["QQQ"] = 0.0006
    frames = frames_for(receipt, drift)
    maturity = R.maturity_session(receipt["executionDate"], MO.DESCRIPTIVE_HORIZON)
    with pytest.raises(ValueError, match="H21_NOT_MATURED"):
        MO.descriptive_h21_record(receipt, price_frames=frames, now_utc=(maturity + pd.Timedelta(hours=22)).tz_localize("UTC"))
    record = MO.descriptive_h21_record(receipt, price_frames=frames, now_utc=(maturity + pd.Timedelta(days=2)).tz_localize("UTC"))
    assert record["label"] == MO.DESCRIPTIVE_LABEL and record["portfolio"]["status"] == "COMPLETE"
    summary = MO.summarize_h21([record])
    assert summary["complete"] == 1 and summary["passiveSpreadQQQMinusSPY"] > 0
    assert not {"ci", "interval", "pValue", "tStat", "verdict", "lower", "upper"} & set(summary)
    assert summary["inference"].startswith("NONE")


def test_h126_progress_reads_no_return_and_counts_independent_windows():
    outcomes = [{"portfolio": {"status": "COMPLETE", "excessVsSPY": 0.5}} for _ in range(60)]
    progress = MO.h126_progress(outcomes)
    assert progress["maturedSignalWeeks"] == 60 and progress["independentWindows"] == 2 and progress["primaryStatisticComputed"] is False
    assert progress["weeksRemainingToGate"] == 312 - 60
    assert "excessVsSPY" not in str(progress) and "mean" not in progress


def test_evidence_schedule_is_calendar_only_and_not_accelerated():
    schedule = MO.evidence_schedule("2026-10-19T15:00:00+00:00")
    assert schedule["firstProspectiveSession"] == "2026-10-20" and schedule["firstSignalSession"] == "2026-10-23"
    assert schedule["gate"]["maturedSignalWeeksRequired"] == 312 and schedule["gate"]["independentWindowsRequired"] == 12
    assert schedule["gate"]["earliestSingleLookVerdictSession"] > schedule["firstH126Maturity"] > schedule["firstH21Maturity"]
    assert schedule["gate"]["earliestSingleLookVerdictSession"] < "2036-01-01"
    assert "neither bring the gate forward" in schedule["notAccelerated"]


# --------------------------------------------------------------------------- #
# Pilot preflight
# --------------------------------------------------------------------------- #
def test_the_twelve_operational_preflight_checks_all_pass(tmp_path):
    results = PI.preflight(tmp_path)
    assert len(results) == 12
    assert [r for r in results if r["status"] != "PASS"] == []
    assert not list(tmp_path.glob("**/weekly-decisions/**")), "nothing may be written to the official namespace"
    assert R.REGISTERED_AUTHORIZATION is None
