"""Invented forecasts and prices only; production control and dated costs reused."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from pipeline import decision_optionality as D
from pipeline import historical_calibration as HC
from pipeline import historical_store as HS
from pipeline import replay_valuation as RV
from pipeline import weekly_decision as W
from scripts.run_decision_optionality import run_synthetic, synthetic_frame


def decide(frame, policy="CURRENT"):
    return D.decide(frame, policy, scope="SYNTHETIC")


@pytest.mark.parametrize("scope", [None, "HISTORICAL", "PROSPECTIVE_PAPER"])
def test_scope_guard_before_inputs(scope, monkeypatch):
    monkeypatch.setattr(W, "decide", lambda *a, **k: pytest.fail("selector reached"))
    with pytest.raises(ValueError, match="NOT_AUTHORIZED"):
        D.decide(None, scope=scope)
    with pytest.raises(ValueError, match="NOT_AUTHORIZED"):
        D.evaluate(None, None, scope=scope, execution_date=None, end_date=None)


@pytest.mark.parametrize("market", ["KR", "US"])
@pytest.mark.parametrize("n", range(7))
def test_current_calls_production_and_matches_exact_weights(market, n, monkeypatch):
    f = synthetic_frame(n, market=market)
    expected = W.decide(market, list(f.candidates), f.calibration, f.signal_date, set())
    original, calls = W.decide, []

    def spy(*args, **kwargs):
        calls.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(W, "decide", spy)
    out = decide(f)
    assert calls == [True]
    assert out["target"] == expected["weights"]
    assert sum(out["target"].values()) == pytest.approx(1)


def test_no_side_effects_and_determinism():
    f = synthetic_frame()
    before = deepcopy(f)
    one = decide(f, "NO_CREDIT")
    assert f == before
    reverse = replace(f, candidates=tuple(reversed(f.candidates)), observations=tuple(reversed(f.observations)),
                      forecasts=tuple(reversed(f.forecasts)))
    two = decide(reverse, "NO_CREDIT")
    assert one["target"] == two["target"]
    assert one["informationSha256"] == two["informationSha256"]


@pytest.mark.parametrize("policy", D.POLICIES)
def test_caps_shared_by_all_policies(policy):
    f = synthetic_frame(7)
    obs = tuple(replace(o, industry_id="Same") for o in f.observations)
    cands = tuple({**c, "sector": "Same"} for c in f.candidates)
    out = decide(replace(f, candidates=cands, observations=obs), policy)
    assert out["stockCount"] <= 2
    assert all(w <= W.NAME_WEIGHT for t, w in out["target"].items() if t != "SPY")


def test_d1_removes_only_economic_entry_gate():
    f = synthetic_frame(expected=.05)
    current, forced = decide(f), decide(f, "FORCED_FIVE")
    assert current["stockCount"] == 0 and forced["stockCount"] == 5
    assert current["informationSha256"] == forced["informationSha256"]
    f = replace(f, calibration=None)
    assert decide(f, "FORCED_FIVE")["stockCount"] == 0
    assert decide(f, "FORCED_FIVE")["forcedFiveShortfall"]
    blocked = tuple({**c, "entry": {"entryState": "AVOID"}} for c in f.candidates)
    assert decide(replace(f, candidates=blocked), "FORCED_FIVE")["stockCount"] == 0


def test_d2_only_credit_changes_selection_at_boundary():
    f = synthetic_frame(before={**{f"SYN{i}": .15 for i in range(5)}, "SPY": .25})
    c = list(f.candidates)
    c[5] = {**c[5], "risk": {"downsideVolPct": 19.8}}
    f = replace(f, candidates=tuple(c))
    current, no_credit = decide(f), decide(f, "NO_CREDIT")
    assert "SYN5" not in current["target"] and "SYN5" in no_credit["target"]
    assert all(a["action"] == "HOLD" for a in current["actions"])
    swap = next(a for a in no_credit["actions"] if a["action"] == "REPLACE")
    audit = swap["marginalAudit"]
    assert audit["marginalNetPct"] == pytest.approx(-.163)
    assert audit["conservativeMarginalNetPct"] == pytest.approx(-.363)
    assert audit["capitalGainsTax"] is None
    assert decide(replace(f, forecasts=()), "NO_CREDIT")["actions"][0]["marginalAudit"]["available"] is False


@pytest.mark.parametrize("market", ["KR", "US"])
def test_d3_asymmetry_thesis_and_absence(market):
    bench = W.BENCHMARKS[market]
    f = synthetic_frame(1, market=market, before={"SYN0": .15, bench: .85}, remaining=.1)
    assert decide(f, "SYMMETRIC")["stockCount"] == 0
    assert decide(f, "ASYMMETRIC")["stockCount"] == 1
    assert decide(synthetic_frame(1, market=market, remaining=.1), "ASYMMETRIC")["stockCount"] == 0
    false_thesis = replace(f, forecasts=tuple(replace(x, thesis_valid=False) for x in f.forecasts))
    assert decide(false_thesis, "ASYMMETRIC")["stockCount"] == 0
    for forecasts in ((), tuple(replace(x, thesis_valid=None) for x in f.forecasts),
                      tuple(replace(x, expected_excess_pct=None, missing_reason="NO_SOURCE") for x in f.forecasts)):
        out = decide(replace(f, forecasts=forecasts), "ASYMMETRIC")
        assert out["status"] == "NOT_ESTIMABLE"
        assert not set(out) & {"actions", "before", "target", "positions", "weights", "ranking"}


def test_d3_does_not_recover_structural_ineligibility():
    f = synthetic_frame(1, before={"SYN0": .15, "SPY": .85}, remaining=.1)
    c = ({**f.candidates[0], "entry": {"entryState": "AVOID"}},)
    assert decide(replace(f, candidates=c), "ASYMMETRIC")["stockCount"] == 0


def test_d4_preserves_drift_but_enforces_cap_and_initial_funding():
    f = synthetic_frame(1, before={"SYN0": .14, "SPY": .86})
    assert decide(f)["target"]["SYN0"] == .15
    event = decide(f, "EVENT_ONLY")
    assert event["target"] == f.before
    assert event["actions"][0]["action"] == "HOLD"
    out = decide(replace(f, before={"SYN0": .16, "SPY": .84}), "EVENT_ONLY")
    assert out["target"]["SYN0"] == .15
    assert out["actions"][0] == {"action": "REDUCE", "ticker": "SYN0", "reason": "CAP_RESTORATION"}
    assert decide(synthetic_frame(0, before={}), "EVENT_ONLY")["target"] == {"SPY": 1}


def test_pool_exit_recorded_and_new_entry_distinct():
    f = synthetic_frame(0, before={"SYN9": .15, "SPY": .85})
    out = decide(f)
    assert {a["action"] for a in out["actions"]} == {"EXIT", "WAIT_ETF"}
    assert out["actions"][0]["reason"] == "POOL_EXIT"
    assert decide(synthetic_frame(1))["actions"][0]["action"] == "BUY"


def evaluate(out, returns=None, **kwargs):
    returns = returns if returns is not None else {**{t: .1 for t in out["evidence"]}, W.BENCHMARKS[out["market"]]: .02}
    return D.evaluate(out, returns, execution_date=out["nextTradingSession"], end_date="2026-10-16",
                      scope="SYNTHETIC", **kwargs)


def test_ledger_includes_etf_legs_and_target_restoration():
    out = decide(synthetic_frame(1))
    ev = evaluate(out)
    assert {(r["ticker"], r["side"]) for r in ev["legs"]} == {("SPY", "sell"), ("SYN0", "buy")}
    assert ev["costFraction"] == pytest.approx(.15 * (.00083 + .0008))
    assert ev["oneWayTurnover"] == pytest.approx(.15)
    assert ev["nameTrades"] == 1
    assert next(l for l in ev["legs"] if l["ticker"] == "SPY")["sellTaxBps"] == .3
    assert next(l for l in ev["legs"] if l["ticker"] == "SYN0")["sellTaxBps"] == 0
    assert ev["grossReturn"] == pytest.approx(.032)
    assert ev["netReturn"] == pytest.approx((1 - .0002445) * 1.032 - 1)
    assert ev["etfOpportunityReturn"] == pytest.approx(.003)
    assert sum(ev["stockExcessContributions"].values()) == pytest.approx(.012)
    drift = decide(synthetic_frame(1, before={"SYN0": .14, "SPY": .86}))
    retarget = evaluate(drift)
    assert retarget["nameTrades"] == 0
    assert retarget["stockOrderLegs"] == 1
    assert retarget["replacementCostFraction"] == 0
    assert sum(retarget["costByCategory"].values()) == pytest.approx(retarget["costFraction"])
    assert next(l for l in retarget["legs"] if l["ticker"] == "SYN0")["category"] == "WEIGHT_RETARGET"
    kr = decide(synthetic_frame(1, market="KR", before={"SYN0": .15, "069500.KS": .85}), "ETF")
    sell = next(l for l in evaluate(kr)["legs"] if l["ticker"] == "SYN0")
    assert sell["sellTaxBps"] == 20 and sell["commissionBps"] == 1.5 and sell["halfSpreadBps"] == 4


@pytest.mark.parametrize("market,day,expected_sell", [("KR", "2018-06-04", .00355), ("KR", "2025-06-02", .00205),
                                                     ("KR", "2026-06-01", .00255), ("US", "2026-06-01", .00083)])
def test_dated_tax_delegates_to_existing_cost_engine(market, day, expected_sell):
    assert W.trade_cost_fraction(market, day, is_benchmark=False, side="sell") == pytest.approx(expected_sell)
    if market == "KR":
        assert W.trade_cost_fraction(market, day, is_benchmark=True, side="sell") == pytest.approx(.00055)


@pytest.mark.parametrize("stress", [1, 2, 3])
def test_cost_stress_and_initial_funding_are_explicit(stress):
    out = decide(synthetic_frame(0, before={}), "ETF")
    ev = evaluate(out, cost_multiplier=stress)
    assert ev["initialFunding"] and ev["costFraction"] == pytest.approx(stress * .0008)
    assert ev["netActiveReturn"] == pytest.approx(0)


def test_no_trade_is_not_economic_gain():
    f = synthetic_frame(1, before={"SYN0": .14, "SPY": .86})
    current, event = decide(f), decide(f, "EVENT_ONLY")
    c, e = evaluate(current), evaluate(event)
    assert e["legs"] == [] and e["costFraction"] == 0
    assert e["netReturn"] < c["netReturn"]  # missed upside exceeds small fee savings
    c, e = evaluate(current, {"SYN0": -.1, "SPY": .02}), evaluate(event, {"SYN0": -.1, "SPY": .02})
    assert e["netReturn"] > c["netReturn"]  # same decisions, opposite path


def test_missing_unselected_return_blocks_shared_mask():
    out = decide(synthetic_frame(), "ETF")
    with pytest.raises(ValueError, match="COMMON_RETURN_MASK"):
        evaluate(out, {"SPY": .02})
    with pytest.raises(ValueError, match="NEXT_SESSION"):
        D.evaluate(out, {}, execution_date=out["signalDate"], end_date="2026-10-16", scope="SYNTHETIC")


def test_calendar_is_own_exchange_and_information_cannot_arrive_late():
    kr, us = decide(synthetic_frame(market="KR")), decide(synthetic_frame(market="US"))
    assert kr["signalDate"] == "2026-10-08" and kr["nextTradingSession"] == "2026-10-12"
    assert us["nextTradingSession"] == "2026-10-12"
    f = synthetic_frame(1)
    with pytest.raises(ValueError, match="FORECAST_NOT_PUBLIC"):
        decide(replace(f, forecasts=(replace(f.forecasts[0], available_at="2026-10-10T00:00:00Z"),)))
    with pytest.raises(ValueError, match="COMPLETED_OWN_MARKET"):
        decide(replace(f, decision_at="2026-10-09T19:00:00Z"))
    with pytest.raises(ValueError, match="DECISION_AFTER_NEXT_SESSION_OPEN"):
        decide(replace(f, decision_at="2026-10-12T20:30:00Z"))
    with pytest.raises(ValueError, match="SYNTHETIC_SECURITY"):
        decide(replace(f, observations=(replace(f.observations[0], key=EW_key_real(f)),)))


def EW_key_real(f):
    from pipeline.experiment_workbench import Key
    return Key(f.market, f.signal_date, "REAL_SECURITY")


def test_synthetic_runner_is_deterministic_and_never_calibrates_history(monkeypatch):
    attempts = []

    def forbidden(*args, **kwargs):
        attempts.append(True)
        raise AssertionError("historical reader/fitter reached")

    monkeypatch.setattr(HC, "calibrate", forbidden)
    monkeypatch.setattr(HS, "load", forbidden)
    monkeypatch.setattr(HS, "read_jsonl", forbidden)
    monkeypatch.setattr(RV.ValuationData, "window", forbidden)
    original = Path.read_bytes
    root = Path(__file__).resolve().parents[1]
    allowed = {"docs/decision-optionality/protocol-v1.json", "docs/decision-optionality/protocol-v1.sha256"}
    seen = []

    def guarded(path):
        resolved = path.resolve()
        if root in resolved.parents:
            rel = str(resolved.relative_to(root))
            assert rel in allowed or rel.startswith(("pipeline/", "scripts/")) and rel.endswith(".py")
            seen.append(rel)
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", guarded)
    a, b = run_synthetic(), run_synthetic()
    assert a == b and attempts == [] and seen
    assert a["historicalOutcomeReaderImplemented"] is a["historicalModelFitterImplemented"] is False
    assert a["syntheticNameCountFrequencies"] == {str(n): 1 for n in range(6)}
    assert len(a["scenarios"]) == 8
    observed_actions = {action["action"] for s in a["scenarios"] for d in s["decisions"].values() for action in d["actions"]}
    assert {"WAIT_ETF", "BUY", "HOLD", "EXIT", "REPLACE"} <= observed_actions


def test_protocol_freeze_and_real_subprocess_cli():
    root = Path(__file__).resolve().parents[1]
    raw = (root / "docs/decision-optionality/protocol-v1.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == (root / "docs/decision-optionality/protocol-v1.sha256").read_text().split()[0]
    run = subprocess.run([sys.executable, "-m", "scripts.run_decision_optionality"], cwd=root, capture_output=True, text=True, check=True)
    assert json.loads(run.stdout)["status"] == "SYNTHETIC_MECHANICS_ONLY"
    forbidden_cli = subprocess.run([sys.executable, "-m", "scripts.run_decision_optionality", "--historical"],
                                   cwd=root, capture_output=True, text=True)
    assert forbidden_cli.returncode != 0 and not forbidden_cli.stdout


def test_missing_and_nonfinite_forecast_fields_do_not_become_estimates():
    f = synthetic_frame(1)
    forecast = f.forecasts[0]
    for bad in (float("nan"), float("inf"), True):
        with pytest.raises(ValueError, match="INVALID_FORECAST"):
            replace(forecast, expected_excess_pct=bad)
    with pytest.raises(ValueError, match="NEGATIVE_UNCERTAINTY"):
        replace(forecast, radius_pct=-1)
    with pytest.raises(ValueError, match="ABSENCE_REASON"):
        replace(forecast, expected_excess_pct=None)
    out = decide(replace(f, forecasts=()))
    assert out["evidence"]["SYN0"]["remainingForecast"] is None
    assert out["evidence"]["SYN0"]["judgmentUnavailableReason"]


@pytest.mark.parametrize("policy", ["CURRENT", "FORCED_FIVE", "NO_CREDIT", "ASYMMETRIC"])
def test_uninvestable_observation_is_excluded_on_every_arm(policy):
    f = synthetic_frame(1)
    o = replace(f.observations[0], investable=False, eligibility_reason="SOURCE_BLOCKED")
    out = decide(replace(f, observations=(o,)), policy)
    assert out["stockCount"] == 0
    assert "OBSERVATION_NOT_INVESTABLE" in out["ranking"][0]["exclusionCodes"]


def test_information_changes_and_holdings_changes_have_distinct_identity():
    f = synthetic_frame(1)
    original = decide(f)
    drift = decide(replace(f, before={"SYN0": .14, "SPY": .86}))
    assert original["informationSha256"] == drift["informationSha256"]
    assert original["holdingsSha256"] != drift["holdingsSha256"]
    change = replace(f.forecasts[0], expected_excess_pct=4)
    assert original["informationSha256"] != decide(replace(f, forecasts=(change,)))["informationSha256"]


def test_unequal_swaps_not_reported_as_equal_weight_marginal_gains():
    f = synthetic_frame(before={**{f"SYN{i}": .14 for i in range(5)}, "SPY": .30})
    c = list(f.candidates)
    c[5] = {**c[5], "risk": {"downsideVolPct": 19.8}}
    out = decide(replace(f, candidates=tuple(c)), "NO_CREDIT")
    audit = next(a["marginalAudit"] for a in out["actions"] if a["action"] == "REPLACE")
    assert audit == {"available": False, "reason": "UNEQUAL_SWAP_WEIGHTS"}
