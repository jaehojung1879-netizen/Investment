"""The registered design and the deterministic 0-5 name candidate rule. Synthetic inputs only; no return, price or outcome is read."""
from __future__ import annotations

import ast
import json
import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import us_capital_allocation_policy as P   # noqa: E402

CONFIG = json.loads((ROOT / "config.json").read_text())
SPEC = ROOT / "docs/us-capital-allocation/us-capital-allocation-alpha-v1-registration.json"


def feat(value, state="VALID"):
    return {"value": value, "state": state}


def candidate(ticker, *, sector="Industrials", growth=0.30, ratio=0.40, ocf=1_000.0, price_ok=True, age=30, dist=None, **override):
    dist = ratio * ocf if dist is None else dist
    features = {"totalCashDistributionTTM": feat(dist), "totalCashDistributionChangeYoY": feat(growth),
                "operatingCashFlowTTM": feat(ocf), "distributionToOCF": feat(ratio)}
    features.update(override)
    return {"ticker": ticker, "sector": sector, "priceOk": price_ok, "reportAgeDays": age, "features": features}


# --------------------------------------------------------------------------- #
# Registration: every number has a source and none was tuned
# --------------------------------------------------------------------------- #
def test_inherited_parameters_equal_the_repository_settings_they_name():
    assert P.SLOT_WEIGHT == CONFIG["longterm"]["maxNameWeight"]
    assert P.MAX_NAMES_PER_SECTOR == round(CONFIG["longterm"]["maxSectorWeight"] / CONFIG["longterm"]["maxNameWeight"])
    assert P.HORIZON_SESSIONS == CONFIG["historicalReplay"]["horizonDays"]
    gate = P.registration()["maturityGate"]
    activation = CONFIG["kellyPortfolio"]["activation"]
    assert (gate["minMaturedSignals"], gate["minPaperDays"]) == (activation["minMaturedSignals"], activation["minPaperDays"])
    assert gate["minIndependentWindows"] == CONFIG["historicalReplay"]["minOrderingEffectiveDates"]
    weekly = json.loads((ROOT / "docs/weekly-decision/weekly-passive-first-v1.json").read_text())
    assert "5" in json.dumps(weekly["rule"]) and P.MAX_NAMES == 5


def test_costs_come_from_the_dated_table_the_official_weekly_policy_uses():
    costs = P.costs_bps()
    assert costs["stockRoundTripBps"] == pytest.approx(2 * 5.0 + 6.0 + 0.30)
    assert costs["switchBpsPerUnitStockWeight"] == pytest.approx(2 * costs["stockRoundTripBps"])


def test_registration_is_pure_data_stable_and_declares_the_residual_before_any_return():
    r = P.registration()
    assert json.loads(json.dumps(r)) == r                                   # no objects, no NaN, no functions
    assert P.design_digest() == P.design_digest()
    assert r["selection"]["residualAsset"] == "SPY" and r["selection"]["optimizedParameters"] == []
    assert r["benchmarks"] == {"official": "SPY", "alternative": "QQQ", "residual": "SPY"}
    assert r["status"] == "REGISTERED_PENDING_OWNER_APPROVAL" and r["authorization"] is None
    assert r["scheduledPublication"] == "NOT_STARTED" and r["promotionEligible"] is False and r["productionEffect"] == "NONE"
    assert r["features"]["dilution"]["gate"] is False and r["features"]["dilution"]["status"] == P.DILUTION_STATUS


def test_committed_registration_file_is_exactly_what_the_code_registers():
    assert json.loads(SPEC.read_text()) == P.registration()


def test_primary_claim_is_one_intersection_test_so_no_multiplicity_correction_is_needed():
    verdicts = P.registration()["verdicts"]
    assert "intersection" in verdicts["multiplicity"] and "no correction applies" in verdicts["multiplicity"]
    assert P.registration()["hypothesis"]["primaryHorizonSessions"] == 126


def test_policy_imports_no_outcome_price_or_model_code():
    tree = ast.parse((ROOT / "pipeline/us_capital_allocation_policy.py").read_text())
    imported = {n.names[0].name if isinstance(n, ast.Import) else n.module for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))}
    imported |= {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names}
    forbidden = {"historical_replay", "replay_valuation", "price_adjustment", "weekly_decision", "weekly_publish", "kelly_portfolio",
                 "historical_calibration", "outcomes", "datafeed", "benchmark_source"}
    assert not (imported & forbidden)


# --------------------------------------------------------------------------- #
# Gates, in registered order
# --------------------------------------------------------------------------- #
def test_a_qualifying_name_passes_with_the_registered_score():
    e = P.evaluate(candidate("AAA", growth=0.25, ratio=0.5))
    assert e["gate"] is None
    assert e["score"] == pytest.approx(0.5 * 0.25 / 1.25)


def test_score_equals_the_newly_committed_distribution_over_operating_cash_flow():
    dist, prior, ocf = 600.0, 450.0, 2_000.0
    growth, ratio = dist / prior - 1.0, dist / ocf
    assert P.incremental_over_ocf(ratio, growth) == pytest.approx((dist - prior) / ocf)


@pytest.mark.parametrize("override,gate", [
    ({"price_ok": False}, "NOT_PRICED_OR_STALE_PRICE"),
    ({"sector": None}, "SECTOR_UNKNOWN"), ({"sector": "UNCLASSIFIED"}, "SECTOR_UNKNOWN"),
    ({"sector": "Financials"}, "SECTOR_EXCLUDED"), ({"sector": "Real Estate"}, "SECTOR_EXCLUDED"),
    ({"age": None}, "REPORT_ABSENT_OR_STALE"), ({"age": 181}, "REPORT_ABSENT_OR_STALE"),
    ({"growth": 0.09}, "DISTRIBUTION_INCREASE_NOT_MATERIAL"),
    ({"growth": 0.10, "ratio": 0.10}, "DISTRIBUTION_INCREASE_NOT_MATERIAL"),        # 10% growth but only 0.9% of OCF newly committed
    ({"ratio": 1.01}, "DISTRIBUTION_NOT_COVERED_BY_OPERATING_CASH_FLOW"),
])
def test_each_gate_fails_where_registered(override, gate):
    assert P.evaluate(candidate("AAA", **override))["gate"] == gate


def test_gate_order_is_the_registered_order_and_the_first_failure_is_reported():
    e = P.evaluate(candidate("AAA", sector="Financials", price_ok=False, growth=-0.5))
    assert e["gate"] == "NOT_PRICED_OR_STALE_PRICE"
    assert P.GATES == tuple(g["id"] for g in P.registration()["gates"])


@pytest.mark.parametrize("state", ["NOT_REPORTED", "AMBIGUOUS_ACCOUNTING", "INSUFFICIENT_HISTORY", "NOT_APPLICABLE", "INVALID", "BLOCKED"])
def test_an_unmeasured_feature_is_never_read_as_zero_or_as_a_pass(state):
    for name in P.MEASURED_FEATURES:
        c = candidate("AAA", **{name: feat(None, state)})
        assert P.evaluate(c)["gate"] == "FEATURES_NOT_MEASURED"
    # even a numeric value does not rescue a state that is not a usable measurement
    assert P.evaluate(candidate("AAA", totalCashDistributionTTM=feat(5.0, state)))["gate"] == "FEATURES_NOT_MEASURED"


def test_a_reported_zero_distribution_is_a_measurement_but_cannot_be_an_increase():
    e = P.evaluate(candidate("AAA", dist=0.0, ratio=0.0, growth=0.5, totalCashDistributionTTM=feat(0.0, "REPORTED_ZERO")))
    assert e["gate"] == "DISTRIBUTION_INCREASE_NOT_MATERIAL"


def test_a_distribution_that_fell_to_zero_does_not_divide_by_zero():
    """growth = -1 (prior positive, now zero) made 1 + growth zero in the first real run; the growth gate must come first."""
    e = P.evaluate(candidate("AAA", growth=-1.0, ratio=0.0, dist=0.0))
    assert e["gate"] == "DISTRIBUTION_INCREASE_NOT_MATERIAL" and e["score"] is None


def test_nonpositive_operating_cash_flow_is_not_a_candidate_even_with_a_huge_ratio():
    assert P.evaluate(candidate("AAA", ocf=-5.0))["gate"] == "FEATURES_NOT_MEASURED"
    assert P.evaluate(candidate("AAA", ocf=0.0))["gate"] == "FEATURES_NOT_MEASURED"


def test_dilution_is_not_a_gate_and_is_never_asserted_as_checked():
    assert "DILUTION" not in " ".join(P.GATES)
    assert P.DILUTION_STATUS == "UNVERIFIED_SOURCE_BLOCKED"


# --------------------------------------------------------------------------- #
# Selection: 0-5 names, deterministic, sector-capped
# --------------------------------------------------------------------------- #
def names(n, sector="Industrials", start=0, growth=0.3):
    return [candidate("T%02d" % (start + i), sector=sector, growth=growth + 0.01 * i, ratio=0.4) for i in range(n)]


def test_zero_passers_means_the_whole_book_is_the_residual_asset():
    out = P.select([P.evaluate(candidate("AAA", growth=0.0))], min_measured=1)
    assert out["status"] == "NO_ELIGIBLE_OPPORTUNITY" and out["weights"] == {} and out["fallbackWeight"] == 1.0 and out["selected"] == []


def test_at_most_five_names_at_fifteen_percent_and_the_rest_in_spy():
    sectors = ["Industrials", "Health Care", "Utilities", "Energy", "Materials", "Consumer Staples", "Information Technology"]
    pool = [candidate("T%02d" % i, sector=sectors[i], growth=0.2 + 0.05 * i) for i in range(7)]
    out = P.select([P.evaluate(c) for c in pool], min_measured=1)
    assert out["status"] == "CANDIDATE_PORTFOLIO" and len(out["weights"]) == 5
    assert set(out["weights"].values()) == {0.15} and out["fallbackWeight"] == pytest.approx(0.25)
    assert [s["ticker"] for s in out["selected"]] == ["T06", "T05", "T04", "T03", "T02"]          # highest score first
    assert len(out["passers"]) == 7


def test_two_names_per_sector_at_most_and_the_skipped_are_recorded():
    pool = names(4) + [candidate("U01", sector="Health Care", growth=0.20)]
    out = P.select([P.evaluate(c) for c in pool], min_measured=1)
    chosen = [s["ticker"] for s in out["selected"]]
    assert chosen == ["T03", "T02", "U01"]
    assert out["skippedForSectorCap"] == ["T01", "T00"]


def test_ties_break_by_ticker_and_input_order_never_matters():
    pool = [candidate(t, sector=s, growth=0.3) for t, s in [("ZZ", "Energy"), ("AA", "Utilities"), ("MM", "Materials")]]
    results = set()
    for seed in range(8):
        shuffled = pool[:]
        random.Random(seed).shuffle(shuffled)
        out = P.select([P.evaluate(c) for c in shuffled], min_measured=1)
        results.add(json.dumps(out, sort_keys=True))
    assert len(results) == 1
    assert json.loads(results.pop())["weights"] == {"AA": 0.15, "MM": 0.15, "ZZ": 0.15}


def test_below_the_measured_floor_the_week_is_blocked_with_no_signal():
    pool = [P.evaluate(c) for c in names(3)]
    out = P.select(pool, min_measured=4)
    assert out["status"] == "BLOCKED" and out["weights"] is None and out["selected"] == [] and out["passers"] == []
    assert out["reasons"][0].startswith("MEASURED_NAMES_BELOW_FLOOR")


def test_the_floor_counts_names_with_a_measured_record_not_names_that_passed():
    measured_but_failing = [P.evaluate(candidate("F%02d" % i, growth=0.0)) for i in range(5)]
    assert P.funnel(measured_but_failing)["measured"] == 5
    assert P.select(measured_but_failing, min_measured=5)["status"] == "NO_ELIGIBLE_OPPORTUNITY"


def test_the_rule_has_no_benchmark_argument_so_spy_and_qqq_see_the_same_names():
    import inspect
    params = set(inspect.signature(P.select).parameters) | set(inspect.signature(P.evaluate).parameters)
    assert not any("bench" in p or "qqq" in p.lower() or "spy" in p.lower() for p in params)
