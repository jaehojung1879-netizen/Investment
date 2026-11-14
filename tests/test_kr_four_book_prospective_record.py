"""kr-four-book-prospective-record-v1 (prepared, not authorized): synthetic tests only; no real price, label or outcome is read."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "research" / "alpha_mechanism_decomposition_v1"


def _load(name, path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


R = _load("kr_four_book_recorder", D / "prospective" / "recorder.py")
CLOCK = pd.Timestamp("2026-11-13T10:00:00Z")          # after the 2026-11-13 KR close is final (09:00 UTC)


def cross_section(confirmed=True, n=12, seed=0):
    rng = np.random.default_rng(seed)
    inds = ["AA", "AA", "AA", "BB", "BB", "BB", "CC", "CC", "CC", "DD", "DD", "DD"][:n]
    g = pd.DataFrame({"ticker": [f"{i:06d}.KS" for i in range(1, n + 1)], "industry": inds,
                      "tradableAtSignal": True, "isPreferredShare": False, "E04_tradabilityGuard20": 20.0, "E07_suspensionStaleRisk": 0.0,
                      "E03_capacityMedianTradedValue60": 1e10, "B08_valueBusinessConfirmation": rng.uniform(0, 1, n),
                      "b08Confirmed": 1.0 if confirmed else 0.0, "b08State": "CHEAP_CONFIRMED" if confirmed else "CHEAP_UNCONFIRMED",
                      "A09_industryRelativeMomentum126": rng.normal(0, 0.1, n), "_mcap": rng.uniform(1e11, 1e13, n)})
    g["H01_industryRelMom126"] = g["industry"].map({"AA": 0.3, "BB": 0.2, "CC": -0.1, "DD": -0.2})
    return g


def test_every_book_sums_to_one_and_holds_at_most_five_stocks():
    out = R.decide(cross_section())
    for b in R.BOOKS:
        assert abs(sum(out[b]["weights"].values()) - 1.0) < 1e-12
    assert out["B0_069500_ONLY"]["weights"] == {R.ETF: 1.0}
    assert out["B1_S2_ORIGINAL"]["stockNames"] == 5 and out["B3_H01_INDUSTRIES_S2_SELECTION"]["stockNames"] <= 5


def test_zero_eligible_names_falls_back_to_069500_only():
    out = R.decide(cross_section(confirmed=False))
    assert out["B1_S2_ORIGINAL"]["weights"] == {R.ETF: 1.0} and out["B1_S2_ORIGINAL"]["state"] == "FALLBACK_ONLY_069500"
    assert out["B3_H01_INDUSTRIES_S2_SELECTION"]["weights"] == {R.ETF: 1.0}
    assert out["B1_S2_ORIGINAL"]["selection"]["excludedCounts"] == {"NOT_CONFIRMED": 12}


def test_fewer_than_five_eligible_leaves_the_unused_slots_in_069500():
    g = cross_section()
    g.loc[2:, "b08Confirmed"] = 0.0
    out = R.decide(g)
    assert out["B1_S2_ORIGINAL"]["stockNames"] == 2 and abs(out["B1_S2_ORIGINAL"]["fallbackWeight"] - 0.6) < 1e-12


def test_b3_stays_inside_the_h01_industries_and_b2_is_their_cap_basket():
    g = cross_section()
    out = R.decide(g)
    inds = set(out["B2_H01_CAP_INDUSTRY_BASKET"]["selection"]["industries"])
    held = [t for t in out["B3_H01_INDUSTRIES_S2_SELECTION"]["weights"] if t != R.ETF]
    assert set(g.set_index("ticker").loc[held, "industry"]) <= inds
    assert all(x["reason"] == "OUTSIDE_H01_INDUSTRIES" for x in out["B3_H01_INDUSTRIES_S2_SELECTION"]["selection"]["excluded"].get("OUTSIDE_H01_INDUSTRIES", []))
    assert set(g.set_index("ticker").loc[[t for t in out["B2_H01_CAP_INDUSTRY_BASKET"]["weights"] if t != R.ETF], "industry"]) == inds


def test_exclusion_reasons_name_the_first_failing_gate_and_match_the_frozen_mask():
    g = cross_section()
    g.loc[0, "E03_capacityMedianTradedValue60"] = 1e9
    g.loc[1, "tradableAtSignal"] = False
    g.loc[2, "B08_valueBusinessConfirmation"] = np.nan
    g.loc[2, "b08State"] = "MISSING_VALUE_INPUT"
    ex = R.decide(g)["B1_S2_ORIGINAL"]["selection"]["excluded"]
    assert ex["QUALITY"][0]["reason"] == "QUALITY:MEDIAN_TRADED_VALUE_BELOW_5BN_KRW"
    assert ex["QUALITY"][1]["reason"] == "QUALITY:NOT_TRADABLE_AT_SIGNAL"
    assert ex["S2_MISSING_VALUE_INPUT"][0]["ticker"] == "000003.KS"
    assert {x["reason"].split("_")[0] for x in ex["OUTRANKED"]} == {"OUTRANKED:rank"}


def test_decision_is_input_order_invariant_bit_for_bit():
    g = cross_section()
    a = R.decide(g)
    for seed in range(25):
        b = R.decide(g.sample(frac=1.0, random_state=seed))
        assert {k: v["weights"] for k, v in a.items()} == {k: v["weights"] for k, v in b.items()}, seed


def test_live_receipt_is_refused_while_not_authorized():
    assert R.REGISTERED_AUTHORIZATION is None
    with pytest.raises(ValueError, match="NOT_AUTHORIZED"):
        R.build_live_receipt(g=cross_section(), signal_date="2026-11-13", data_identity={"x": "y"})


def test_receipts_carry_no_outcome_and_pathways_never_mix(tmp_path):
    r = R.build_synthetic_receipt(g=cross_section(), signal_date="2026-11-13", test_clock_utc=CLOCK, data_identity={"x": "y"})
    assert r["evidenceClass"] == "SYNTHETIC_FIXTURE" and r["executionDate"] == "2026-11-16"
    R.append_synthetic(tmp_path / "s.jsonl", r)
    with pytest.raises(ValueError, match="RECEIPT_ALREADY_EXISTS"):
        R.append_synthetic(tmp_path / "s.jsonl", r)
    with pytest.raises(ValueError, match="PATHWAY_MISMATCH"):
        R.append_live(tmp_path / "l.jsonl", r)
    p = R.build_preview_receipt(g=cross_section(), signal_date="2026-09-11", execution_date="2026-09-14", data_identity={}, clock_utc=CLOCK)
    assert p["evidenceClass"] == "NOT_PROSPECTIVE_EVIDENCE"
    with pytest.raises(ValueError, match="PATHWAY_MISMATCH"):
        R.append_live(tmp_path / "l.jsonl", p)
    tampered = json.loads(json.dumps(r))
    tampered["books"]["B1_S2_ORIGINAL"]["weights"][R.ETF] = 0.5
    with pytest.raises(ValueError, match="DIGEST"):
        R.validate(tampered, pathway=R.SYNTHETIC)


def test_book_outcome_is_unresolved_when_a_held_name_has_no_terminal_consideration():
    g = cross_section()
    r = R.build_synthetic_receipt(g=g, signal_date="2026-01-09", test_clock_utc="2026-01-09T10:00:00Z", data_identity={})
    held = r["books"]["B1_S2_ORIGINAL"]["weights"]
    names = {t: {"state": "PRICED", "excessReturn": 0.01} for t in held}
    exit_session = str(R.CORE.maturity_session(r["executionDate"], 21).date())
    for v in names.values():
        v["exitSession"] = exit_session
    first = sorted(t for t in held if t != R.ETF)[0]
    names[first] = {"state": "TERMINAL_ECONOMICS_UNRESOLVED", "excessReturn": None}
    rec = R.book_outcome(r, "B1_S2_ORIGINAL", horizon=21, name_outcomes=names, now_utc="2026-03-31T10:00:00Z", pathway=R.SYNTHETIC)
    assert rec["portfolio"]["heldExcessReturn"] is None and rec["portfolio"]["status"] == "TERMINAL_ECONOMICS_UNRESOLVED"


def test_spec_freezes_the_rules_and_names_the_live_input_blocker():
    s = json.loads((D / "prospective" / "spec.json").read_text())
    assert s["status"] == "PREPARED_NOT_AUTHORIZED"
    assert s["zeroAndMaximum"] == {"minimumNames": 0, "maximumNames": 5, "weightPerName": 0.2, "fallback": "069500.KS",
                                   "cashTarget": "NONE (the fallback is the ETF, never cash)"}
    assert set(s["books"]) == set(R.BOOKS)
    assert "COMMIT_IS_NOT_THE_PINNED_SOURCE_COMMIT" in s["liveInputBlocker"]
