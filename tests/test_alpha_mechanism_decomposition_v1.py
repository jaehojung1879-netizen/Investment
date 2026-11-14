"""alpha-mechanism-decomposition-v1: synthetic tests for the attribution identity, the nulls and the matched controls.

No real price, label or outcome is read here."""
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
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


M = _load("amd_mechanism", D / "mechanism.py")


def _market(seed=3, n=60):
    rng = np.random.default_rng(seed)
    sessions = pd.bdate_range("2020-01-01", periods=n)
    tick = [M.ETF, "A", "B", "C", "D"]
    rets = rng.normal(0.0005, 0.02, (n, len(tick)))
    closes = pd.DataFrame(100 * np.cumprod(1 + rets, axis=0), index=sessions, columns=tick)
    rf = pd.Series(0.0001, index=sessions)
    cs = pd.DataFrame({"ticker": ["A", "B", "C", "D"], "industry": ["X", "X", "Y", "Y"], "_q": [True, True, True, False],
                       "_mcap": [3.0, 1.0, 2.0, 5.0], "F03_beta252": [1.2, 0.8, np.nan, 1.0]})
    return sessions, closes, rf, cs


def test_three_term_identity_holds_for_every_leg_type():
    sessions, closes, rf, cs = _market()
    pp = M.PeriodPrices(closes, sessions, rf)
    e, x = sessions[5], sessions[25]
    rows = M.attribute_book({"A": 0.3, "C": 0.3, M.ETF: 0.2, M.CASH: 0.2}, cs, pp, e, x)
    r_m = closes.at[x, M.ETF] / closes.at[e, M.ETF] - 1
    total = sum(r["weight"] * (r["R"] - r_m) for r in rows)
    assert abs(total - sum(r["MARKET_BETA"] + r["INDUSTRY_ALPHA"] + r["SELECTION_ALPHA"] for r in rows)) < 1e-12
    etf = [r for r in rows if r["asset"] == M.ETF][0]
    assert etf["MARKET_BETA"] == etf["INDUSTRY_ALPHA"] == etf["SELECTION_ALPHA"] == 0.0
    cash = [r for r in rows if r["asset"] == M.CASH][0]
    assert abs(cash["MARKET_BETA"] - 0.2 * (-1) * (r_m - cash["R_f"])) < 1e-12 and cash["INDUSTRY_ALPHA"] == 0 and cash["SELECTION_ALPHA"] == 0


def test_industry_basket_is_cap_weighted_over_eligible_members_only():
    _, _, _, cs = _market()
    assert M.industry_basket(cs, "X") == {"A": 0.75, "B": 0.25}
    assert M.industry_basket(cs, "Y") == {"C": 1.0}            # D is not quality-eligible
    assert M.industry_basket(cs, "X", equal=True) == {"A": 0.5, "B": 0.5}


def test_sole_member_of_its_industry_has_zero_selection():
    sessions, closes, rf, cs = _market()
    pp = M.PeriodPrices(closes, sessions, rf)
    rows = M.attribute_book({"C": 1.0}, cs, pp, sessions[1], sessions[30])
    assert abs(rows[0]["SELECTION_ALPHA"]) < 1e-12           # C's missing beta falls back to its basket's, and the basket is C


def test_missing_beta_falls_back_and_industry_beta_renormalises():
    betas = pd.Series({"A": 1.2, "B": np.nan})
    assert M.industry_beta({"A": 0.75, "B": 0.25}, betas) == pytest.approx(1.2)
    assert M.industry_beta({"B": 1.0}, betas) == 1.0


def test_terminal_name_is_written_off_and_recorded():
    sessions, closes, rf, cs = _market()
    closes.loc[sessions[20]:, "A"] = np.nan
    pp = M.PeriodPrices(closes, sessions, rf, terminal={"A": sessions[19]})
    assert pp.ret("A", sessions[5], sessions[30]) == -1.0 and pp.hits


def test_summary_compounding_closes_the_gap():
    sessions, closes, rf, cs = _market(n=120)
    pp = M.PeriodPrices(closes, sessions, rf)
    legs = []
    per = M.periods([sessions[i] for i in (0, 20, 40, 60, 80, 100)], sessions, sessions[-1])
    for k, (d, e, x) in enumerate(per):
        for r in M.attribute_book({"A": 0.5, "C": 0.5}, cs, pp, e, x):
            legs.append({**r, "period": k})
    s = M.summarise(pd.DataFrame(legs), 1.0, "T")
    assert abs(s["geometricGap"] - s["arithmeticExcess"] - s["compounding"]) < 1e-12
    assert abs(s["arithmeticExcess"] - (s["MARKET_BETA"] + s["INDUSTRY_ALPHA"] + s["SELECTION_ALPHA"])) < 1e-12


def test_choice_value_is_zero_on_average_under_uniform_choice():
    rng = np.random.default_rng(1)
    R = pd.DataFrame(rng.normal(0, 0.05, (400, 4)), columns=list("abcd"))
    v = [M.choice_value(R, pd.Series(rng.choice(list("abcd"), 400), index=R.index)).mean() for _ in range(200)]
    assert abs(np.mean(v)) < 0.002


def test_permutation_null_detects_a_planted_oracle_and_not_noise():
    rng = np.random.default_rng(2)
    R = pd.DataFrame(rng.normal(0.005, 0.05, (100, 4)), columns=list("abcd"))
    oracle = R.idxmax(axis=1)
    noise = pd.Series(rng.choice(list("abcd"), 100), index=R.index)
    assert M.permutation_null(R, oracle, 8.0, draws=500)["uniform"]["pValue"] < 0.01
    assert M.permutation_null(R, noise, 8.0, draws=500)["uniform"]["pValue"] > 0.01


def test_matched_controls_stay_in_industry_and_are_used_once():
    cs = pd.DataFrame({"ticker": list("ABCDEF"), "industry": list("XXXXYY"), "_q": [True] * 6,
                       "size": [1, 2, 3, 4, 5, 6], "mom": [1, 2, 3, 4, 5, 6]})
    out = M.matched_controls(cs, ["B", "C", "E"], ["size", "mom"])
    assert out["B"] in {"A", "D"} and out["C"] in {"A", "D"} and out["B"] != out["C"]
    assert out["E"] == "F"
    assert M.matched_controls(cs, ["F", "E"], ["size"])["E"] is None


def test_block_bootstrap_and_holm():
    rng = np.random.default_rng(4)
    assert M.block_bootstrap_mean(rng.normal(0.01, 0.01, 300), 5, reps=500)["ci95"][0] > 0
    assert list(M.holm([0.01, 0.04, 0.03])) == pytest.approx([0.03, 0.06, 0.06])


def test_vendored_files_are_byte_identical_to_their_recorded_sources():
    import hashlib
    prov = json.loads((D / "vendor" / "PROVENANCE.json").read_text())
    for rel, meta in prov["files"].items():
        raw = (D / "vendor" / rel).read_bytes()
        sha1 = hashlib.sha1(b"blob %d\0" % len(raw) + raw).hexdigest()
        assert sha1 == meta["gitBlobSha1"], rel


def test_published_outputs_exist_and_carry_their_evidence_class():
    if not (D / "results" / "verification.json").exists():
        pytest.skip("results not generated")
    v = json.loads((D / "results" / "verification.json").read_text())
    assert v["evidenceClass"] == "POST_HOC_EXPLORATORY_DECOMPOSITION_ON_OUTCOME_EXPOSED_KR_HISTORY"
    assert v["reproduction"]["status"] in ("REPRODUCED", "REPRODUCED_WITHIN_TOLERANCE")
    for name in ("mechanism-attribution.csv", "s2-ablation.csv", "industry-momentum-diagnostics.csv"):
        assert (D / name).exists()
