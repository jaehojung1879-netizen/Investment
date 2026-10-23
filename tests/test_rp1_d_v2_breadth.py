"""Synthetic acceptance matrix for rp1-d-v2-endogenous-breadth-v1 (issue #282).

Every number below is an INVENTED fixture value chosen to exercise a branch. None is a proposal for an owner parameter, and no realised
return is read anywhere.
"""
import inspect
from pathlib import Path
import random

import numpy as np
import pandas as pd
import pytest

from pipeline import rp1_d_composition_contract as V1
from pipeline import rp1_d_v2_breadth as D

ROOT = Path(__file__).resolve().parents[1]
SESSION = "2026-10-16"
# Friday 2026-10-16: the close is final (KR no earlier than 18:00 KST, US 17:00 ET) and the next open is Monday 2026-10-19.
CUTOFF = {"KR": "2026-10-16T19:00:00+09:00", "US": "2026-10-16T20:00:00-04:00"}
AVAILABLE = {"KR": "2026-10-16T18:30:00+09:00", "US": "2026-10-16T19:30:00-04:00"}
COMPUTED = {"KR": "2026-10-16T18:45:00+09:00", "US": "2026-10-16T19:45:00-04:00"}
LEGS = {"etfSell": 0.06, "stockBuy": 0.06, "stockSell": 0.26, "etfBuy": 0.06}      # C4 = 0.44
P = {"horizonSessions": 126, "uncertaintyMultiplierZ": 1.0, "edgeHurdlePct": 0.0, "riskAversionLambda": 2.0,
     "maxTrackingErrorPct": "NOT_USED", "maxNameFraction": 0.08, "maxSectorFraction": 1.0, "maxActiveFraction": 1.0,
     "minPositionFraction": 0.0}


def tick(region, i):
    return f"{100000 + i:06d}.KS" if region == "KR" else f"S{i:03d}"


def row(region, i, gross=6.0, se=1.0, sector=None, **kw):
    r = {"ticker": tick(region, i), "signalSession": SESSION, "availableAt": AVAILABLE[region], "excessBasis": D.EXCESS_BASIS,
         "grossExcessPct": gross, "standardErrorPct": se, "costLegsPct": dict(LEGS), "sector": sector or f"SEC{i}",
         "liquidityCapFraction": 1.0}
    r.update(kw)
    return r


def risk(tickers, var=196.0, corr=None, cb=0.0, region="KR", **provenance):
    n = len(tickers)
    c = np.eye(n) if corr is None else np.array(corr, dtype=float)
    s = c * var
    model = {"tickers": list(tickers), "matrix": s.tolist(), "benchmarkCovariance": {t: cb for t in tickers}, "horizonSessions": 126,
             "estimator": D.RISK_MODEL_ESTIMATOR, "lastObservationSession": SESSION, "computedAt": COMPUTED[region],
             "sourceDigestSha256": "a" * 64, "producerSha256": "b" * 64}
    model.update(provenance)
    return D.seal_risk_model(model)


def reseal(rec, **change):
    """Edit a fixture's risk model and seal it again, so a test reaches the check after the digest."""
    rec["riskModel"].update(change)
    rec["riskModel"] = D.seal_risk_model(rec["riskModel"])
    return rec


def record(rows, region="KR", **kw):
    rec = {"evidenceClass": D.SYNTHETIC, "region": region, "benchmark": D.REGIONAL_ETF[region], "horizonSessions": 126,
           "decisionSession": SESSION, "decisionCutoffAt": CUTOFF[region], "names": rows,
           "riskModel": risk([r["ticker"] for r in rows if isinstance(r, dict)], region=region)}
    rec.update(kw)
    return rec


def run(rec, region="KR", **params):
    return D.decide_region(rec, region, synthetic_owner_parameters={**P, **params})


def strong(n, region="KR", **kw):
    return [row(region, i, **kw) for i in range(n)]


# --- N is an output: 0, 1, 2, 5, 10, 11+ -------------------------------------------------------------------------------------------
def test_no_qualified_a_is_etf_default_in_both_regions():
    out = D.decide({})
    for r in D.REGIONS:
        reg = out["regions"][r]
        assert reg["activeCount"] == 0 and reg["etfFraction"] == 1.0 and reg["etf"] == D.REGIONAL_ETF[r]
        assert reg["defaultPolicy"] == D.DEFAULT_POLICY and reg["productionAffected"] is False
    assert out["crossRegionTotal"] == "FX_AND_REGIONAL_CAPITAL_UNRESOLVED"


@pytest.mark.parametrize("n", [1, 2, 5, 10, 11, 12])
@pytest.mark.parametrize("region", D.REGIONS)
def test_count_follows_the_evidence(n, region):
    weak = [row(region, 100 + i, gross=0.5) for i in range(8)]          # 0.5 - 1.0 SE < 0: never held
    out = run(record(strong(n, region) + weak, region), region)
    assert out["status"] == "SYNTHETIC_SHADOW_BOOK" and out["stamp"] == D.SYNTHETIC_STAMP
    assert out["activeCount"] == n
    assert abs(out["activeFraction"] + out["etfFraction"] - 1.0) < 1e-12 and out["etfFraction"] >= -1e-9
    assert all(t not in out["shadowFractions"] for t in (r["ticker"] for r in weak))


def test_more_than_ten_is_not_capped():
    out = run(record(strong(30)), maxNameFraction=0.03)
    assert out["activeCount"] == 30 and out["largestNameFraction"] <= 0.03 + 1e-7


def test_legacy_v1_cap_blocks_what_v2_holds(monkeypatch):
    monkeypatch.setattr(V1, "EXPECTED_EXCESS_DEFINITION", "SINGLE_COST_DEDUCTION")
    names = [tick("KR", i) for i in range(12)]
    legacy = V1.compose({"KR": {"validated": True, "calibrated": True, "expectedNetExcessPct": 5.0, "uncertaintyPct": 1.0,
                                "roundTripCostPct": 0.44, "candidates": names, "excessCostBasis": V1.GROSS, "benchmark": "069500.KS"}})
    assert legacy["status"] == "BLOCKED_CAP_SELECTION_RULE_UNRESOLVED" and V1.MAX_NAMES == 5
    assert run(record(strong(12)))["activeCount"] == 12


def test_enough_names_but_poor_net_edge_is_etf():
    out = run(record([row("KR", i, gross=1.2, se=1.0) for i in range(20)]))   # 1.2 - 1.0 - 0.44 < 0
    assert out["activeCount"] == 0 and out["etfFraction"] == 1.0
    assert out["reasons"] == ["NO_NAME_CLEARS_EDGE_AFTER_UNCERTAINTY_COST_AND_HURDLE"]


def test_hurdle_is_charged_after_uncertainty_and_cost():
    out = run(record(strong(3, gross=2.0, se=0.5)), edgeHurdlePct=1.0)        # 2.0 - 0.5 - 0.44 = 1.06 > 1.0
    assert out["activeCount"] == 3
    assert run(record(strong(3, gross=2.0, se=0.5)), edgeHurdlePct=1.1)["activeCount"] == 0


# --- costs: one definition, four legs, charged once ------------------------------------------------------------------------------
def test_single_cost_deduction_and_stress():
    assert D.four_leg_cost_pct(LEGS) == pytest.approx(0.44)
    assert D.net_excess_pct(0.8, {"etfSell": 0.1, "stockBuy": 0.1, "stockSell": 0.2, "etfBuy": 0.1}) == pytest.approx(0.3)
    assert D.net_excess_pct(0.8, {"etfSell": 0.1, "stockBuy": 0.1, "stockSell": 0.2, "etfBuy": 0.1}, stress=2) == pytest.approx(-0.2)
    assert D.four_leg_cost_pct({"etfSell": 0.1, "stockBuy": 0.1, "stockSell": 0.2}) is None       # missing leg is never zero
    assert D.four_leg_cost_pct({**LEGS, "etfBuy": None}) is None


@pytest.mark.parametrize("region", D.REGIONS)
def test_schedule_legs_equal_the_existing_weekly_switch_cost(region):
    from pipeline import weekly_decision as W
    assert D.four_leg_cost_pct(D.schedule_cost_legs(region, SESSION)) == pytest.approx(W.cost_breakdown(region, SESSION)["switchCostPct"],
                                                                                     abs=1e-4)


def test_net_basis_is_refused_not_charged_twice():
    out = run(record([row("KR", 0, excessBasis="NET_OF_ROUND_TRIP_COST")]))
    assert out["activeCount"] == 0 and out["excluded"][tick("KR", 0)] == ["EXCESS_BASIS_NOT_GROSS_VS_REGIONAL_ETF"]


def test_cost_stress_lowers_the_count_and_extreme_cost_is_etf():
    rows = [row("KR", i, gross=1.0 + 0.3 * i, se=0.1) for i in range(6)]       # alpha - k*0.44 crosses zero at different k
    out = run(record(rows))
    counts = out["costStressActiveCount"]
    assert counts["1"] >= counts["2"] >= counts["3"] and counts["1"] > counts["3"]
    huge = {k: 30.0 for k in D.COST_LEGS}
    assert run(record(strong(5, costLegsPct=huge)))["activeCount"] == 0


def test_incumbent_keep_needs_no_entry_cost_but_adding_does():
    held = row("KR", 0, gross=1.3, se=1.0, incumbentFraction=0.05)            # alpha 0.3 > 0, alpha - 0.44 < 0
    new = row("KR", 1, gross=1.3, se=1.0)
    out = run(record([held, new]))
    assert out["shadowFractions"] == {tick("KR", 0): pytest.approx(0.05, abs=1e-7)}
    assert out["addedFractions"][tick("KR", 0)] == pytest.approx(0.0, abs=1e-7)
    assert out["excluded"][tick("KR", 1)] == ["EDGE_AFTER_UNCERTAINTY_AND_COST_NOT_ABOVE_HURDLE"]


# --- risk, concentration and constraints -----------------------------------------------------------------------------------------
def test_correlated_names_share_one_risk_budget():
    rows = [row("KR", i, gross=6.0, se=1.0) for i in range(3)]
    corr = [[1.0, 0.99, 0.0], [0.99, 1.0, 0.0], [0.0, 0.0, 1.0]]
    rec = record(rows, riskModel=risk([r["ticker"] for r in rows], var=2500.0, corr=corr))
    out = run(rec, maxNameFraction=1.0)
    w = out["shadowFractions"]
    assert w[tick("KR", 0)] + w[tick("KR", 1)] < 1.1 * w[tick("KR", 2)]
    assert out["effectiveNames"] < 3


def test_sector_constraint_binds():
    out = run(record([row("KR", i, sector="SAME") for i in range(4)]), maxNameFraction=0.15, maxSectorFraction=0.2)
    assert out["sectorFractions"]["SAME"] <= 0.2 + 1e-7 and out["activeCount"] >= 2


def test_tracking_error_budget_binds():
    out = run(record(strong(10)), maxTrackingErrorPct=2.0)
    assert out["activeTrackingErrorPct"] <= 2.0 + 1e-6


def test_liquidity_cap_and_minimum_position():
    rows = strong(3)
    rows[0]["liquidityCapFraction"] = 0.02
    out = run(record(rows))
    assert out["shadowFractions"][tick("KR", 0)] <= 0.02 + 1e-7
    out = run(record(rows), minPositionFraction=0.05)
    assert tick("KR", 0) not in out["shadowFractions"] and out["activeCount"] == 2


def test_active_fraction_never_exceeds_one_and_no_leverage():
    out = run(record(strong(20)), maxNameFraction=0.15)
    assert out["activeFraction"] <= 1.0 + 1e-7 and min(out["shadowFractions"].values()) > 0


def test_benchmark_covariance_enters_the_growth_objective():
    base = run(record(strong(1)), maxNameFraction=1.0)["activeFraction"]
    rec = record(strong(1))
    reseal(rec, benchmarkCovariance={tick("KR", 0): 150.0})
    assert run(rec, maxNameFraction=1.0)["activeFraction"] < base


# --- data integrity: stale, missing, look-ahead, outcome, identity ---------------------------------------------------------------
def test_stale_and_missing_forecasts_are_excluded_never_carried():
    rows = [row("KR", 0, signalSession="2026-10-09"), row("KR", 1, standardErrorPct=None), row("KR", 2, liquidityCapFraction=None),
            row("KR", 3, sector=""), row("KR", 4)]
    rows[3]["sector"] = ""
    out = run(record(rows))
    assert out["excluded"][tick("KR", 0)] == ["FORECAST_STALE_OR_UNDATED"]
    assert "STANDARD_ERROR_UNAVAILABLE" in out["excluded"][tick("KR", 1)]
    assert "LIQUIDITY_UNMEASURED" in out["excluded"][tick("KR", 2)]
    assert "SECTOR_UNAVAILABLE" in out["excluded"][tick("KR", 3)]
    assert list(out["shadowFractions"]) == [tick("KR", 4)]


@pytest.mark.parametrize("region,available,reason", [
    ("KR", "2026-10-16T18:59:59+09:00", None),                                    # before the cutoff
    ("KR", "2026-10-16T19:00:00+09:00", None),                                    # at the cutoff
    ("KR", "2026-10-16T10:00:00Z", None),                                         # 19:00 KST written in UTC: the same instant
    ("KR", "2026-10-16T19:00:01+09:00", "LOOK_AHEAD_AVAILABLE_AFTER_DECISION_CUTOFF"),
    ("KR", "2026-10-16T12:00:00+01:00", "LOOK_AHEAD_AVAILABLE_AFTER_DECISION_CUTOFF"),  # 19:00 KST + 1 h in another offset
    ("KR", "2026-10-19T08:00:00+09:00", "LOOK_AHEAD_AVAILABLE_AFTER_DECISION_CUTOFF"),
    ("US", "2026-10-16T19:59:00-04:00", None),
    ("US", "2026-10-17T00:00:00Z", None),                                         # 20:00 EDT
    ("US", "2026-10-16T21:00:00-04:00", "LOOK_AHEAD_AVAILABLE_AFTER_DECISION_CUTOFF"),
    ("KR", "2026-10-16", "AVAILABILITY_NOT_A_TIMEZONE_AWARE_INSTANT"),             # the old date-only form: ambiguous, refused
    ("KR", "2026-10-15", "AVAILABILITY_NOT_A_TIMEZONE_AWARE_INSTANT"),             # even an earlier bare date proves no instant
    ("KR", "2026-10-16T18:30:00", "AVAILABILITY_NOT_A_TIMEZONE_AWARE_INSTANT"),    # naive timestamp
    ("KR", "2026-10-16 18:30:00+09:00", "AVAILABILITY_NOT_A_TIMEZONE_AWARE_INSTANT"),
    ("KR", "2026-13-16T18:30:00+09:00", "AVAILABILITY_NOT_A_TIMEZONE_AWARE_INSTANT"),
    ("KR", "yesterday", "AVAILABILITY_NOT_A_TIMEZONE_AWARE_INSTANT"),
    ("KR", None, "AVAILABILITY_NOT_A_TIMEZONE_AWARE_INSTANT")])
def test_availability_is_an_instant_compared_with_the_decision_cutoff(region, available, reason):
    rows = strong(3, region)
    rows[1]["availableAt"] = available
    out = run(record(rows, region), region)
    if reason is None:
        assert out["status"] == "SYNTHETIC_SHADOW_BOOK" and out["activeCount"] == 3
    else:
        assert out["activeCount"] == 0 and out["reasons"] == [reason]       # leakage in one row voids the whole region


@pytest.mark.parametrize("region,cutoff,reason", [
    ("KR", "2026-10-16T18:00:00+09:00", None),                                    # KR finality boundary
    ("KR", "2026-10-19T08:59:59+09:00", None),                                    # last instant before Monday's open
    ("KR", "2026-10-16T17:59:59+09:00", "DECISION_CUTOFF_BEFORE_THE_SESSION_CLOSE_IS_FINAL"),
    ("KR", "2026-10-16T12:00:00+09:00", "DECISION_CUTOFF_BEFORE_THE_SESSION_CLOSE_IS_FINAL"),
    ("KR", "2026-10-19T09:00:00+09:00", "DECISION_CUTOFF_AT_OR_AFTER_THE_NEXT_OPEN"),
    ("KR", "2026-10-20T09:00:00+09:00", "DECISION_CUTOFF_AFTER_A_LATER_SESSION"),
    ("US", "2026-10-16T17:00:00-04:00", None),                                    # close + settlement buffer
    ("US", "2026-10-16T16:59:59-04:00", "DECISION_CUTOFF_BEFORE_THE_SESSION_CLOSE_IS_FINAL"),
    ("US", "2026-10-19T13:30:00Z", "DECISION_CUTOFF_AT_OR_AFTER_THE_NEXT_OPEN"),   # 09:30 EDT Monday
    ("KR", "2026-10-16", "DECISION_CUTOFF_NOT_A_TIMEZONE_AWARE_INSTANT"),
    ("KR", "2026-10-16T19:00:00", "DECISION_CUTOFF_NOT_A_TIMEZONE_AWARE_INSTANT"),
    ("KR", "not-a-time", "DECISION_CUTOFF_NOT_A_TIMEZONE_AWARE_INSTANT"),
    ("KR", None, "DECISION_CUTOFF_NOT_A_TIMEZONE_AWARE_INSTANT")])
def test_decision_cutoff_lies_between_the_final_close_and_the_next_open(region, cutoff, reason):
    rows = strong(2, region, availableAt="2026-10-16T08:00:00Z")
    rec = record(rows, region, decisionCutoffAt=cutoff)
    rec["riskModel"] = risk([r["ticker"] for r in rows], region=region, computedAt="2026-10-16T09:00:00Z" if region == "KR"
                            else "2026-10-16T21:00:00Z")
    out = run(rec, region)
    if reason is None:
        assert out["status"] == "SYNTHETIC_SHADOW_BOOK"
    else:
        assert out["activeCount"] == 0 and out["reasons"] == [reason]


@pytest.mark.parametrize("change,reason", [
    ({"lastObservationSession": "2026-10-19"}, "RISK_MODEL_OBSERVATIONS_AFTER_DECISION_SESSION"),
    ({"lastObservationSession": None}, "RISK_MODEL_UNDATED"),
    ({"lastObservationSession": "unknown"}, "RISK_MODEL_UNDATED"),
    ({"computedAt": "2026-10-16"}, "RISK_MODEL_UNDATED"),
    ({"computedAt": "2026-10-16T18:45:00"}, "RISK_MODEL_UNDATED"),
    ({"computedAt": "2026-10-16T19:00:01+09:00"}, "RISK_MODEL_COMPUTED_AFTER_DECISION_CUTOFF"),
    ({"computedAt": "2026-10-16T14:00:00+09:00"}, "RISK_MODEL_COMPUTED_BEFORE_ITS_LAST_OBSERVATION_WAS_FINAL"),
    ({"sourceDigestSha256": "not-a-digest"}, "RISK_MODEL_PROVENANCE_MALFORMED")])
def test_a_valid_psd_matrix_with_future_or_unknown_provenance_is_refused(change, reason):
    rec = reseal(record(strong(3)), **change)       # sealed honestly, so only the stated provenance can refuse it
    assert np.linalg.eigvalsh(np.array(rec["riskModel"]["matrix"])).min() > 0
    out = run(rec)
    assert out["activeCount"] == 0 and out["reasons"] == [reason]


@pytest.mark.parametrize("key", D.RISK_PROVENANCE_KEYS)
def test_risk_model_without_provenance_is_refused(key):
    rec = record(strong(3))
    del rec["riskModel"][key]
    assert run(rec)["reasons"] == ["RISK_MODEL_PROVENANCE_MISSING"]


@pytest.mark.parametrize("edit", [{"lastObservationSession": "2026-10-15"}, {"computedAt": "2026-10-16T18:40:00+09:00"},
                                  {"matrix": (np.eye(3) * 100.0).tolist()}, {"benchmarkCovariance": {}}])
def test_editing_a_sealed_risk_model_breaks_its_digest(edit):
    rec = record(strong(3))
    rec["riskModel"].update(edit)                    # edited after sealing, digest left stale
    assert run(rec)["reasons"] == ["RISK_MODEL_CONTENT_DIGEST_MISMATCH"]


def test_provenance_is_checked_even_when_no_name_passes():
    rec = reseal(record(strong(3, gross=0.0)), lastObservationSession="2026-10-19")
    assert run(rec)["reasons"] == ["RISK_MODEL_OBSERVATIONS_AFTER_DECISION_SESSION"]


@pytest.mark.parametrize("key", ["realizedReturnPct", "forward_excess", "outcome", "maturedExcess", "label"])
def test_outcome_fields_are_refused(key):
    rows = strong(2)
    rows[0][key] = 1.0
    out = run(record(rows))
    assert out["activeCount"] == 0 and out["reasons"][0].startswith("OUTCOME_FIELD_IN_FORECAST_INPUT")


@pytest.mark.parametrize("region,ticker", [("KR", "069500.KS"), ("US", "SPY"), ("US", "QQQ")])
def test_passive_instruments_are_not_active_names(region, ticker):
    rows = [row(region, 0, ticker=ticker), row(region, 1)]
    rec = record(rows, region)
    rec["riskModel"] = risk([ticker, tick(region, 1)], region=region)
    out = run(rec, region)
    assert out["excluded"][ticker] == ["PASSIVE_INSTRUMENT_IS_NOT_AN_ACTIVE_NAME"] and ticker not in out["shadowFractions"]
    assert out["separateComparisons"] == list(D.SEPARATE_COMPARISONS.get(region, ()))


@pytest.mark.parametrize("change,reason", [({"benchmark": "QQQ"}, "BENCHMARK_NOT_THE_REGIONAL_ETF"),
                                           ({"horizonSessions": 63}, "HORIZON_NOT_REGISTERED"),
                                           ({"horizonSessions": 252}, "FORECAST_HORIZON_DIFFERS_FROM_REGISTERED_HORIZON"),
                                           ({"region": "KR"}, "REGION_MISMATCH"), ({"decisionSession": None}, "DECISION_SESSION_UNDATED")])
def test_record_level_refusals(change, reason):
    rec = record(strong(2, "US"), "US")
    rec.update(change)
    out = run(rec, "US")
    assert out["activeCount"] == 0 and out["reasons"] == [reason]


def test_risk_model_must_cover_and_be_psd():
    rec = record(strong(3))
    rec["riskModel"] = risk([tick("KR", 0), tick("KR", 1)])
    assert run(rec)["reasons"] == ["RISK_MODEL_DOES_NOT_COVER_GATED_NAMES"]
    rec = record(strong(2))
    reseal(rec, matrix=[[1.0, 5.0], [5.0, 1.0]])
    assert run(rec)["reasons"] == ["RISK_MODEL_NOT_SYMMETRIC_PSD"]
    rec = record(strong(2))
    reseal(rec, horizonSessions=252)
    assert run(rec)["reasons"] == ["RISK_MODEL_HORIZON_MISMATCH"]


# --- overlays, FX, activation and inactivity -------------------------------------------------------------------------------------
def test_c_unapproved_and_b_context_only():
    out = run(record(strong(2), cOverlay={"ownerApprovalArtifactSha256": "0" * 64, "multiplier": 0.4}))
    assert out["c"] == {"used": False, "approved": False, "reasons": ["C_OWNER_APPROVAL_NOT_REGISTERED"]}
    assert out["b"] == {"used": False, "role": "CONTEXT_ONLY"}
    assert out["activeFraction"] > 0                                          # no multiplier was applied


def test_cross_region_total_needs_fx():
    out = D.decide({"KR": record(strong(2)), "US": record(strong(2, "US"), "US")}, synthetic_owner_parameters=P)
    assert out["crossRegionTotal"] == "FX_AND_REGIONAL_CAPITAL_UNRESOLVED"
    assert out["regions"]["KR"]["currency"] == "KRW" and out["regions"]["US"]["currency"] == "USD"


def test_real_inputs_are_inactive_today():
    rec = record(strong(5), evidenceClass="PROSPECTIVE_FORECAST", admissionSha256="a" * 64)
    out = D.decide_region(rec, "KR")
    assert out["activeCount"] == 0 and out["reasons"] == ["NO_ADMITTED_PER_NAME_FORECAST_PRODUCER"]
    assert D.decide_region(rec, "KR", synthetic_owner_parameters=P)["status"] == "ETF_DEFAULT_REFUSED"
    assert D.decide_region(record(strong(5)), "KR")["status"] == "ETF_DEFAULT_REFUSED"
    assert D.REGISTERED_A_ADMISSIONS == frozenset() and D.OWNER_PARAMETERS is None


def test_valid_evidence_registered_later_activates_a_shadow_record_only(monkeypatch):
    digest = "b" * 64
    monkeypatch.setattr(D, "REGISTERED_A_ADMISSIONS", frozenset({digest}))
    rec = record(strong(4), evidenceClass="PROSPECTIVE_FORECAST", admissionSha256=digest)
    assert D.decide_region(rec, "KR")["reasons"] == ["OWNER_PARAMETERS_UNSET_OR_INCOMPLETE"]
    monkeypatch.setattr(D, "OWNER_PARAMETERS", dict(P))
    assert D.decide_region(rec, "KR")["reasons"] == ["RISK_MODEL_PRODUCER_NOT_REGISTERED"]
    monkeypatch.setattr(D, "REGISTERED_RISK_MODEL_PRODUCERS", frozenset({rec["riskModel"]["producerSha256"]}))
    out = D.decide_region(rec, "KR")
    assert out["status"] == "PROSPECTIVE_SHADOW_BOOK" and out["activeCount"] == 4 and out["productionAffected"] is False
    assert "stamp" not in out


@pytest.mark.parametrize("bad", [{"riskAversionLambda": 0.5}, {"maxActiveFraction": 1.5}, {"horizonSessions": 63},
                                 {"uncertaintyMultiplierZ": -1}, {"maxTrackingErrorPct": 0}, {"minPositionFraction": float("nan")}])
def test_owner_parameter_domain(bad):
    out = run(record(strong(2)), **bad)
    assert out["status"] == "ETF_DEFAULT_NO_ADMITTED_EDGE" and out["reasons"][0].startswith("OWNER_")


def test_deterministic_and_input_order_invariant():
    rows = [row("KR", i, gross=3.0 + i % 4, se=0.5 + 0.1 * (i % 3), sector=f"S{i % 3}") for i in range(14)]
    base = run(record(rows), maxSectorFraction=0.4)
    shuffled = rows[:]
    random.Random(7).shuffle(shuffled)
    again = run(record(shuffled), maxSectorFraction=0.4)
    assert again["shadowFractions"].keys() == base["shadowFractions"].keys()
    assert all(abs(again["shadowFractions"][t] - v) < 1e-8 for t, v in base["shadowFractions"].items())
    assert run(record(rows), maxSectorFraction=0.4) == base


def test_no_order_fields_and_no_production_import():
    out = run(record(strong(3)))
    assert D.assert_inactive(out)
    with pytest.raises(ValueError):
        D.assert_inactive({"orders": []})
    with pytest.raises(ValueError):
        D.assert_inactive({"productionAffected": True})
    users = [p for p in list((ROOT / "pipeline").glob("*.py")) + list((ROOT / "scripts").glob("*.py"))
             if p.name != "rp1_d_v2_breadth.py" and "rp1_d_v2_breadth" in p.read_text(encoding="utf-8")]
    assert users == []


def test_decision_takes_no_outcome_argument():
    params = set(inspect.signature(D.decide_region).parameters) | set(inspect.signature(D.decide).parameters)
    assert params == {"record", "region", "records", "synthetic_owner_parameters"}


# --- risk model and liquidity helpers --------------------------------------------------------------------------------------------
def test_active_covariance_is_past_only_and_psd():
    days = pd.bdate_range("2025-01-01", SESSION)
    rng = np.random.default_rng(3)
    stocks = pd.DataFrame(rng.normal(0, 0.02, (len(days), 3)), index=days, columns=["B", "A", "C"])
    etf = pd.Series(rng.normal(0, 0.01, len(days)), index=days)
    out = D.active_covariance(stocks, etf, SESSION, 126, region="KR", computed_at=COMPUTED["KR"])
    assert out["tickers"] == ["A", "B", "C"] and np.linalg.eigvalsh(np.array(out["matrix"])).min() > 0
    assert out["lastObservationSession"] == SESSION and out["computedAt"] == COMPUTED["KR"]
    assert out["producerSha256"] == D.producer_sha256() and out["contentSha256"] == D.risk_model_content_sha256(out)
    again = D.active_covariance(stocks, etf, SESSION, 126, region="KR", computed_at=COMPUTED["KR"])
    assert again == out                                                         # deterministic, including every digest
    shifted = stocks.copy()
    shifted.iloc[0, 0] += 1e-6
    assert D.active_covariance(shifted, etf, SESSION, 126, region="KR", computed_at=COMPUTED["KR"])["sourceDigestSha256"] != \
        out["sourceDigestSha256"]
    late = pd.concat([etf, pd.Series([0.0], index=[pd.Timestamp("2026-10-19")])])
    with pytest.raises(D.Refused, match="AFTER_DECISION_SESSION"):
        D.active_covariance(stocks, late, SESSION, 126, region="KR", computed_at=COMPUTED["KR"])
    with pytest.raises(D.Refused, match="COMPUTED_BEFORE_ITS_LAST_OBSERVATION_WAS_FINAL"):
        D.active_covariance(stocks, etf, SESSION, 126, region="KR", computed_at="2026-10-16T14:00:00+09:00")
    for bad in ("2026-10-16", "2026-10-16T18:45:00", None):
        with pytest.raises(D.Refused, match="COMPUTED_AT_NOT_A_TIMEZONE_AWARE_INSTANT"):
            D.active_covariance(stocks, etf, SESSION, 126, region="KR", computed_at=bad)


def test_a_produced_risk_model_passes_the_decision_path():
    days = pd.bdate_range("2025-01-01", SESSION)
    rng = np.random.default_rng(5)
    names = [tick("KR", i) for i in range(3)]
    stocks = pd.DataFrame(rng.normal(0, 0.02, (len(days), 3)), index=days, columns=names)
    etf = pd.Series(rng.normal(0, 0.01, len(days)), index=days)
    rec = record(strong(3), riskModel=D.active_covariance(stocks, etf, SESSION, 126, region="KR", computed_at=COMPUTED["KR"]))
    assert run(rec)["status"] == "SYNTHETIC_SHADOW_BOOK"


def test_liquidity_cap_fraction():
    assert D.liquidity_cap_fraction(1e9, 1e8, 0.01) == pytest.approx(0.1)
    assert D.liquidity_cap_fraction(1e12, 1e8, 0.5) == 1.0
    assert D.liquidity_cap_fraction(None, 1e8, 0.01) is None and D.liquidity_cap_fraction(1e9, 1e8, 0) is None


def test_spec_agrees_and_owner_numbers_stay_unset():
    spec = D.load_spec(ROOT)
    assert spec["authorizes"] == "NOTHING" and spec["productionEffect"] == "NONE"
    assert all(spec["ownerDecisionsRequired"][k] is None for k in D.OWNER_PARAMETER_KEYS)
    assert spec["objective"]["competingAsset"] == {"KR": "069500.KS", "US": "SPY"}
