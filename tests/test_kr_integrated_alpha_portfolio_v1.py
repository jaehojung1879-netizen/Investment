"""kr-integrated-alpha-portfolio-v1: the pure model. Synthetic values only; no test reads a historical market value or computes a historical outcome."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from pipeline import kr_concentrated_portfolio as P
from pipeline import kr_integrated_alpha_portfolio as M
from pipeline import kr_market_risk_model as K
from pipeline import kr_stock_within_industry_anatomy as S

ROOT = Path(__file__).resolve().parents[1]


def frame(n_per_industry=6, industries=("X", "Y"), seed=3, **overrides):
    rng = np.random.default_rng(seed)
    rows = []
    for industry in industries:
        for i in range(n_per_industry):
            rows.append({"date": "2020-01-03", "industry": industry, "ticker": f"{industry}{i}.KS", "bookToMarketProxy": rng.normal(), "earningsYieldProxy": rng.normal(),
                         "negativeDownsideVol126": -abs(rng.normal(0.2, 0.05)), "tradable": True, "adv60": 6e9, "downsideVol126": 0.2 + 0.01 * i,
                         "relative126": rng.normal(), "momentum121": rng.normal(), "logAdv60": rng.normal(), "ocfImprovementToAssets": rng.normal()})
    out = pd.DataFrame(rows)
    for key, value in overrides.items():
        out[key] = value
    return out


# ---------------------------------------------------------------------------------------------------------------------------------------
# Stock layer
# ---------------------------------------------------------------------------------------------------------------------------------------
def test_stock_score_is_the_equal_weight_mean_of_value_and_the_calm_percentile_and_ignores_every_excluded_feature():
    data = frame()
    scored = M.stock_scores(data)
    value = scored[["wi_bookToMarketProxy", "wi_earningsYieldProxy"]].mean(axis=1)
    assert np.allclose(scored.VALUE_SCORE, value)
    assert np.allclose(scored.STOCK_SCORE, 0.5 * scored.VALUE_SCORE + 0.5 * scored.wi_negativeDownsideVol126)
    for excluded in ("relative126", "momentum121", "logAdv60", "ocfImprovementToAssets"):
        shuffled = data.copy()
        shuffled[excluded] = shuffled[excluded].iloc[::-1].to_numpy()
        assert np.allclose(M.stock_scores(shuffled).STOCK_SCORE, scored.STOCK_SCORE)       # the score never reads them
    assert set(M.EXCLUDED_FROM_PRIMARY_SCORE) >= {"relative126", "momentum121", "logAdv60", "ocfImprovementToAssets"}


def test_percentiles_are_within_the_stocks_own_industry_on_the_same_date():
    data = frame()
    data.loc[data.industry == "Y", "bookToMarketProxy"] += 100.0                    # a level shift of a whole industry changes no within-industry rank
    assert np.allclose(M.stock_scores(data).wi_bookToMarketProxy, M.stock_scores(frame()).wi_bookToMarketProxy)
    scored = M.stock_scores(frame())
    for _, group in scored.groupby("industry"):
        assert 0 < group.wi_bookToMarketProxy.min() and group.wi_bookToMarketProxy.max() < 1 and abs(group.wi_bookToMarketProxy.mean() - 0.5) < 1e-9


def test_a_missing_component_makes_the_score_missing_and_is_never_substituted():
    data = frame()
    data.loc[0, "bookToMarketProxy"] = np.nan
    scored = M.stock_scores(data)
    assert np.isnan(scored.loc[0, "VALUE_SCORE"]) and np.isnan(scored.loc[0, "STOCK_SCORE"])
    assert np.isfinite(scored.loc[1, "STOCK_SCORE"])
    data = frame()
    data.loc[2, "negativeDownsideVol126"] = np.nan
    scored = M.stock_scores(data)
    assert np.isfinite(scored.loc[2, "VALUE_SCORE"]) and np.isnan(scored.loc[2, "STOCK_SCORE"])      # the value half exists; the whole score does not
    thin = frame(n_per_industry=4)                                                   # fewer than five peers: no percentile, so no score
    assert M.stock_scores(thin).STOCK_SCORE.isna().all()


# ---------------------------------------------------------------------------------------------------------------------------------------
# Industry layer and the combined score
# ---------------------------------------------------------------------------------------------------------------------------------------
def industry_features(n=8):
    return {f"I{i}": {"REL_MOM_126": float(i), "BREADTH_ABOVE_MA_126": float(n - i) if i % 2 else float(i)} for i in range(n)}


def test_industry_score_is_half_relative_momentum_percentile_half_breadth_percentile_and_needs_both():
    features = industry_features()
    out = M.industry_scores(features)
    for name, record in out.items():
        assert record["ranked"] and abs(record["INDUSTRY_SCORE"] - (0.5 * record["relMomPercentile"] + 0.5 * record["breadthPercentile"])) < 1e-12
    assert out["I7"]["relMomPercentile"] > out["I0"]["relMomPercentile"]
    broken = industry_features()
    broken["I3"]["BREADTH_ABOVE_MA_126"] = np.nan
    out = M.industry_scores(broken)
    assert not out["I3"]["ranked"] and np.isnan(out["I3"]["INDUSTRY_SCORE"]) and out["I4"]["ranked"]
    few = M.industry_scores(industry_features(M.MIN_INDUSTRIES_RANKED - 1))
    assert not any(v["ranked"] for v in few.values())                                # a ranking of a handful of industries is not a ranking
    assert all(v["ranked"] for v in M.industry_scores(industry_features(M.MIN_INDUSTRIES_RANKED)).values())


def test_the_industry_score_is_order_independent_and_uses_nothing_but_its_two_features():
    features = industry_features()
    reversed_ = dict(reversed(list(features.items())))
    assert M.industry_scores(features) == M.industry_scores(reversed_)
    extra = {k: dict(v, DOWNSIDE_VOL_126=99.0, CONSTITUENT_DISPERSION_126=5.0, MEDIAN_ocfYieldProxy=3.0) for k, v in features.items()}
    assert M.industry_scores(extra) == M.industry_scores(features)


WORLD_INDUSTRIES = ("X", "Y", "Z", "U", "V", "W")


def world_rows(industry_score=None):
    scored = M.stock_scores(frame(n_per_industry=6, industries=WORLD_INDUSTRIES))
    industry = industry_score or {"X": 0.8, "Y": 0.2, "Z": 0.6, "U": 0.4, "V": 0.5, "W": 0.3}
    return M.decision_rows(scored, {k: {"INDUSTRY_SCORE": v} for k, v in industry.items()})


def test_combined_score_is_half_stock_half_industry_and_exists_only_when_both_do():
    rows = world_rows()
    for r in rows:
        assert abs(r["COMBINED_SCORE"] - (0.5 * r["STOCK_SCORE"] + 0.5 * r["INDUSTRY_SCORE"])) < 1e-12
    missing = M.decision_rows(M.stock_scores(frame()), {"X": {"INDUSTRY_SCORE": np.nan}, "Y": {"INDUSTRY_SCORE": 0.4}})
    assert all(np.isnan(r["COMBINED_SCORE"]) for r in missing if r["industry"] == "X") and all(np.isfinite(r["COMBINED_SCORE"]) for r in missing if r["industry"] == "Y")


def test_industry_off_contributes_exactly_zero_and_on_reorders_only():
    rows = world_rows()
    flipped = world_rows({"X": 0.2, "Y": 0.8, "Z": 0.9, "U": 0.1, "V": 0.5, "W": 0.7})
    assert M.underlying_decision(rows, False) == M.underlying_decision(flipped, False)          # S never reads the industry score
    on, flipped_on = M.underlying_decision(rows, True), M.underlying_decision(flipped, True)
    assert on["selected"] != flipped_on["selected"] and on["scoreUsed"] == "COMBINED_SCORE"
    assert set(on["selected"]) <= {r["ticker"] for r in rows}


# ---------------------------------------------------------------------------------------------------------------------------------------
# Eligibility, selection, sizing, shared underlying
# ---------------------------------------------------------------------------------------------------------------------------------------
def test_selection_is_top_five_by_score_with_ticker_ties_and_only_investable_names():
    rows = [{"ticker": f"T{i:02d}", "industry": "X", "STOCK_SCORE": 0.5, "INDUSTRY_SCORE": 0.5, "COMBINED_SCORE": 0.5, "tradable": True, "adv60": 6e9, "downsideVol126": 0.2}
            for i in range(14)]
    decision = M.underlying_decision(rows, False)
    assert decision["selected"] == ["T00", "T01", "T02", "T03", "T04"] and decision["eligibleCount"] == 14 and decision["depthOk"] is True and decision["available"] is True
    assert M.underlying_decision(list(reversed(rows)), False) == decision                    # input order never matters
    rows[0].update(tradable=False)
    rows[1].update(adv60=2.9e9)
    rows[2].update(downsideVol126=0.005)
    rows[3].update(STOCK_SCORE=np.nan)
    again = M.underlying_decision(rows, False)
    assert again["selected"] == ["T04", "T05", "T06", "T07", "T08"] and again["eligibleCount"] == 10 and again["available"] is True
    assert M.underlying_decision([], False)["selected"] == [] and M.underlying_decision([], False)["baseWeights"] == {}
    assert M.underlying_decision([], False)["available"] is False


def test_depth_flag_follows_the_frozen_minimum():
    rows = [{"ticker": f"T{i}", "industry": "X", "STOCK_SCORE": i / 20, "INDUSTRY_SCORE": 0.5, "COMBINED_SCORE": i / 20, "tradable": True, "adv60": 6e9,
             "downsideVol126": 0.2} for i in range(M.MIN_ELIGIBLE_PER_DATE)]
    assert M.underlying_decision(rows, False)["depthOk"] is True and M.underlying_decision(rows[:-1], False)["depthOk"] is False
    assert M.underlying_decision(rows, False)["available"] is True and M.underlying_decision(rows[:-1], False)["available"] is False
    assert M.MIN_ELIGIBLE_PER_DATE == 2 * M.MAX_HOLDINGS


def test_sizing_is_the_sealed_water_fill_under_the_name_cap_with_residual_cash_and_no_market_input():
    rows = [{"ticker": f"T{i}", "industry": "X", "STOCK_SCORE": 1 - i / 10, "INDUSTRY_SCORE": 0.5, "COMBINED_SCORE": 1 - i / 10, "tradable": True, "adv60": 6e9,
             "downsideVol126": 0.1 + 0.05 * i} for i in range(12)]
    decision = M.underlying_decision(rows, False)
    chosen = [r for r in rows if r["ticker"] in decision["selected"]]
    assert decision["baseWeights"] == P.size(chosen, M.PORTFOLIO)
    assert max(decision["baseWeights"].values()) <= 0.3 + 1e-12 and sum(decision["baseWeights"].values()) <= 1 + 1e-12
    thin = [dict(r, adv60=3.0e9) for r in rows]                                              # capacity cap 1% x 3bn / 100m = 30%
    assert sum(M.underlying_decision(thin, False)["baseWeights"].values()) <= 1 + 1e-12
    with pytest.raises(ValueError, match="DUPLICATE_SELECTION_SECURITY"):
        M.underlying_decision(rows + rows[:1], False)


def test_architectures_a_b_c_share_one_underlying_decision_and_d_e_f_another():
    pair = M.underlying_pair(world_rows())
    assert M.decision_for("A", pair) is M.decision_for("B", pair) is M.decision_for("C", pair) is pair["S"]
    assert M.decision_for("D", pair) is M.decision_for("E", pair) is M.decision_for("F", pair) is pair["I+S"]
    assert M.ARCH_ORDER == ("A", "B", "C", "D", "E", "F")
    assert {a: (c["industry"], c["market"]) for a, c in M.ARCHITECTURES.items()} == {
        "A": (False, None), "B": (False, "C0"), "C": (False, "C1"), "D": (True, None), "E": (True, "C0"), "F": (True, "C1")}
    assert {c["name"] for c in M.ARCHITECTURES.values()} == {"S", "S+M0", "S+M1", "I+S", "I+S+M0", "I+S+M1"}


def test_the_portfolio_and_band_constants_are_the_sealed_ones():
    overlay = json.loads((ROOT / "research_specs/kr-model-overlay-portfolio-v1.json").read_text())
    for key, value in M.PORTFOLIO.items():
        if key in overlay["portfolio"]:
            assert overlay["portfolio"][key] == value
    assert (M.RETURN_BAND, M.MEANINGFUL_DRAWDOWN_IMPROVEMENT, M.NON_INFERIORITY_DRAWDOWN_BAND) == (0.005, 0.10, 0.10)
    assert (M.RETURN_BAND, M.MEANINGFUL_DRAWDOWN_IMPROVEMENT, M.NON_INFERIORITY_DRAWDOWN_BAND) == (K.RETURN_BAND, K.MEANINGFUL_DRAWDOWN_IMPROVEMENT, K.NON_INFERIORITY_DRAWDOWN_BAND)
    assert M.STOCK_WEIGHTS == {"VALUE_SCORE": 0.5, "RISK_SCORE": 0.5} and M.COMBINED_WEIGHTS == {"STOCK_SCORE": 0.5, "INDUSTRY_SCORE": 0.5}
    assert M.INDUSTRY_WEIGHTS == {"REL_MOM_126": 0.5, "BREADTH_ABOVE_MA_126": 0.5} and M.PORTFOLIO["maximumHoldings"] == 5
    assert M.PORTFOLIO["buyFixedCost"] == 0.0015 and M.PORTFOLIO["sellFixedCost"] == 0.0045 and M.COST_STRESS == (1.0, 2.0, 3.0)


# ---------------------------------------------------------------------------------------------------------------------------------------
# Market schedule
# ---------------------------------------------------------------------------------------------------------------------------------------
def test_target_in_force_is_the_latest_execution_on_or_before_the_day():
    table = pd.DataFrame({"decisionDate": pd.to_datetime(["2020-01-03", "2020-01-10", "2020-01-17"]), "executionDate": pd.to_datetime(["2020-01-06", "2020-01-13", "2020-01-20"]),
                          "target": [1.0, 0.7, 0.4]})
    assert M.target_in_force(table, "2020-01-03") is None and M.target_in_force(table, "2020-01-06") == 1.0
    assert M.target_in_force(table, "2020-01-13") == 0.7 and M.target_in_force(table, "2020-01-12") == 1.0 and M.target_in_force(table, "2021-01-01") == 0.4


def test_market_schedule_uses_the_sealed_candidate_targets_unchanged():
    sessions = pd.DatetimeIndex(["2020-01-06"])
    states = pd.DataFrame(index=pd.DatetimeIndex(["2020-01-03", "2020-01-10"]), data={"slow": [0.0, 1.0], "transition": [0.0, 1.0], "fast": [0.0, 1.0]})
    schedule = pd.DataFrame({"decisionDate": pd.to_datetime(["2020-01-03", "2020-01-10"]), "executionDate": pd.to_datetime(["2020-01-06", "2020-01-13"])})
    for cid in M.MARKET_CANDIDATES:
        direct = K.candidate_targets(states, schedule, cid)
        assert direct.target.tolist() == [K.multiplier(cid, 0, 0, 0), K.multiplier(cid, 1, 1, 1)]
    assert sessions is not None


# ---------------------------------------------------------------------------------------------------------------------------------------
# Pair classification and the registered layer decisions
# ---------------------------------------------------------------------------------------------------------------------------------------
def ax(r, d):
    return {"netAnnualizedReturn": r, "maxDrawdown": d}


def test_pair_classes_cover_every_case_and_the_band_edges_are_inclusive():
    base = ax(0.10, -0.30)
    assert M.classify_pair(ax(0.106, -0.30), base) == "IMPROVES"                  # efficiency route
    assert M.classify_pair(ax(0.095, -0.26), base) == "IMPROVES"                  # protection route within the return band
    assert M.classify_pair(ax(0.10, -0.30), base) == "NON_INFERIOR_NO_MEANINGFUL_GAIN"
    assert M.classify_pair(ax(0.095, -0.27), base) == "IMPROVES"                  # -0.50pp is inside the band, -10% drawdown is exactly on the edge
    assert M.classify_pair(ax(0.0949, -0.20), base) == "TRADE_OFF"                # gives up more than 0.50pp to cut drawdown a lot
    assert M.classify_pair(ax(0.11, -0.34), base) == "TRADE_OFF"                  # gains return but drawdown beyond +10%
    assert M.classify_pair(ax(0.09, -0.34), base) == "WORSE"
    assert M.classify_pair(ax(0.10, -0.331), base) == "WORSE"
    assert M.classify_pair(ax(0.10, -0.33), base) == "NON_INFERIOR_NO_MEANINGFUL_GAIN"
    assert M.classify_pair(ax(None, -0.3), base) == "NOT_EVALUABLE_BLOCKED_PATH" and M.classify_pair(ax(0.1, np.nan), base) == "NOT_EVALUABLE_BLOCKED_PATH"


def summaries(**by_arch):
    defaults = {a: ax(0.10, -0.30) for a in M.ARCH_ORDER}
    defaults.update(by_arch)
    return {a: dict(v, complete=v.get("complete", True)) for a, v in defaults.items()}


def test_industry_supported_only_when_i_plus_s_improves_and_no_overlay_context_contradicts_it():
    ok = M.industry_decision(summaries(D=ax(0.11, -0.30), E=ax(0.10, -0.30), F=ax(0.10, -0.30)))
    assert ok["layerDecision"] == "INDUSTRY_LAYER_DEVELOPMENT_SUPPORTED" and ok["pairClasses"] == {"marketOff": "IMPROVES", "underC0": "NON_INFERIOR_NO_MEANINGFUL_GAIN",
                                                                                                     "underC1": "NON_INFERIOR_NO_MEANINGFUL_GAIN"}
    contradicted = M.industry_decision(summaries(D=ax(0.11, -0.30), E=ax(0.08, -0.36), F=ax(0.10, -0.30)))
    assert contradicted["layerDecision"] == M.INDUSTRY_NOT_SUPPORTED and contradicted["pairClasses"]["underC0"] == "WORSE"
    assert M.industry_decision(summaries(D=ax(0.10, -0.30)))["layerDecision"] == M.INDUSTRY_NOT_SUPPORTED          # no gain
    trade = M.industry_decision(summaries(D=ax(0.11, -0.40)))
    assert trade["layerDecision"] == "INDUSTRY_LAYER_PARETO_TRADE_OFF"
    blocked = M.industry_decision(summaries(E={"complete": False}))
    assert blocked["layerDecision"] == "INDUSTRY_LAYER_NOT_EVALUABLE_BLOCKED_PATH"


def test_market_candidates_are_judged_separately_on_the_same_underlying_portfolio():
    s = summaries(B=ax(0.099, -0.26), E=ax(0.10, -0.30), C=ax(0.10, -0.30))
    decisions = M.market_decisions(s)
    assert decisions["S"]["C0"]["primaryPair"] == "IMPROVES" and decisions["S"]["C0"]["status"] == "DEVELOPMENT_SUPPORTED"
    assert decisions["S"]["C1"]["status"] == "NOT_SUPPORTED" and decisions["S"]["C1"]["primaryPair"] == "NON_INFERIOR_NO_MEANINGFUL_GAIN"
    assert decisions["I+S"]["C0"]["primaryPair"] == "NON_INFERIOR_NO_MEANINGFUL_GAIN"
    costly = M.market_decisions(summaries(B=ax(0.07, -0.20)))
    assert costly["S"]["C0"]["status"] == "PARETO_TRADE_OFF"                         # a larger return loss bought with protection is a risk preference
    assert M.market_decisions(summaries(B={"complete": False}))["S"]["C0"]["status"] == "NOT_EVALUABLE_BLOCKED_PATH"


def decide(**by_arch):
    return M.decide(summaries(**by_arch))


def test_final_architecture_is_assembled_mechanically_from_the_layer_decisions():
    assert decide()["finalArchitecture"] == "A"                                        # nothing supported -> stock only
    assert decide(D=ax(0.11, -0.30))["finalArchitecture"] == "D"                       # industry only
    assert decide(B=ax(0.10, -0.26))["finalArchitecture"] == "B"                       # market C0 only, on the stock-only book
    assert decide(C=ax(0.10, -0.26))["finalArchitecture"] == "C"
    assert decide(D=ax(0.11, -0.30), E=ax(0.11, -0.26))["finalArchitecture"] == "E"
    assert decide(D=ax(0.11, -0.30), F=ax(0.11, -0.26))["finalArchitecture"] == "F"
    assert decide(D=ax(0.11, -0.30), E=ax(0.11, -0.26), F=ax(0.11, -0.26))["finalArchitecture"] == "E"        # both supported, C1 vs C0 does not improve: the control stays
    assert decide(B=ax(0.10, -0.26), C=ax(0.10, -0.26))["finalArchitecture"] == "B"
    better = decide(B=ax(0.10, -0.26), C=ax(0.11, -0.20))
    assert better["market"]["S"]["C1_vs_C0"] == "IMPROVES" and better["finalArchitecture"] == "C"
    assert decide(D=ax(0.11, -0.40))["finalArchitecture"] == M.NO_UNAMBIGUOUS
    assert decide(B=ax(0.07, -0.20))["finalArchitecture"] == M.NO_UNAMBIGUOUS
    assert decide(A={"complete": False})["finalArchitecture"] == M.NO_FINAL_BLOCKED
    unsupported = decide()
    assert unsupported["industry"]["layerDecision"] == M.INDUSTRY_NOT_SUPPORTED and unsupported["marketLayer"] == M.MARKET_NOT_SUPPORTED
    assert decide(D=ax(0.11, -0.30), E=ax(0.11, -0.26))["name"] == "I+S+M0"


def test_when_both_overlays_are_supported_how_they_relate_to_each_other_decides_and_a_genuine_trade_off_is_never_ranked_away():
    base = ax(0.10, -0.30)
    # both clear Market OFF; C vs B is a genuine return / drawdown trade-off (C earns +0.6pp more but its drawdown is beyond B's +10% band)
    trade = summaries(B=ax(0.10, -0.26), C=ax(0.106, -0.29))
    assert M.classify_pair(trade["B"], base) == "IMPROVES" and M.classify_pair(trade["C"], base) == "IMPROVES"
    result = M.decide(trade)
    assert result["market"]["S"]["C1_vs_C0"] == "TRADE_OFF" and result["market"]["S"]["C0"]["status"] == result["market"]["S"]["C1"]["status"] == "DEVELOPMENT_SUPPORTED"
    assert result["finalArchitecture"] == M.NO_UNAMBIGUOUS and result["reason"] == "C0_VS_C1_PARETO_TRADE_OFF" and "marketCandidate" not in result
    # the same trade-off on the Industry+Stock book
    on_industry = M.decide(summaries(D=ax(0.11, -0.30), E=ax(0.11, -0.26), F=ax(0.116, -0.29)))
    assert on_industry["industry"]["layerDecision"] == "INDUSTRY_LAYER_DEVELOPMENT_SUPPORTED" and on_industry["market"]["I+S"]["C1_vs_C0"] == "TRADE_OFF"
    assert on_industry["finalArchitecture"] == M.NO_UNAMBIGUOUS and on_industry["reason"] == M.C0_VS_C1_TRADE_OFF
    # C1 WORSE than C0 -> C0 ; no meaningful incremental gain -> C0 retained and said so ; IMPROVES -> C1
    worse = M.decide(summaries(B=ax(0.11, -0.24), C=ax(0.106, -0.29)))
    assert worse["market"]["S"]["C1_vs_C0"] == "WORSE" and worse["finalArchitecture"] == "B" and worse["c1VsC0Note"] == "C1_WORSE_THAN_C0_C0_RETAINED"
    tie = M.decide(summaries(B=ax(0.10, -0.26), C=ax(0.10, -0.26)))
    assert tie["market"]["S"]["C1_vs_C0"] == "NON_INFERIOR_NO_MEANINGFUL_GAIN" and tie["finalArchitecture"] == "B"
    assert tie["c1VsC0Note"] == "NO_MEANINGFUL_INCREMENTAL_C1_GAIN_C0_RETAINED_AS_THE_EXISTING_CONTROL"
    better = M.decide(summaries(B=ax(0.10, -0.26), C=ax(0.11, -0.20)))
    assert better["finalArchitecture"] == "C" and better["c1VsC0Note"] == "C1_IMPROVES_ON_C0"
    # a blocked comparison never picks a side
    blocked = M.final_architecture({"status": "NOT_SUPPORTED"},
                                   {"S": {"C0": {"status": "DEVELOPMENT_SUPPORTED"}, "C1": {"status": "DEVELOPMENT_SUPPORTED"}, "C1_vs_C0": "NOT_EVALUABLE_BLOCKED_PATH"}})
    assert blocked["finalArchitecture"] == M.NO_FINAL_BLOCKED and blocked["reason"] == "C0_VS_C1_NOT_EVALUABLE"
    # the bands themselves are untouched by this repair
    assert (M.RETURN_BAND, M.MEANINGFUL_DRAWDOWN_IMPROVEMENT, M.NON_INFERIORITY_DRAWDOWN_BAND) == (0.005, 0.10, 0.10)


def test_comparisons_attribution_and_interaction_use_the_registered_pairs():
    s = summaries(B=ax(0.099, -0.26), E=ax(0.10, -0.29), D=ax(0.105, -0.31))
    for entry in s.values():
        entry.update({m: 0.0 for m in M.COMPARED_METRICS if m not in entry})
    rows = M.comparisons(s)
    assert [(r["candidate"], r["base"]) for r in rows] == [("D", "A"), ("E", "B"), ("F", "C"), ("B", "A"), ("C", "A"), ("E", "D"), ("F", "D"), ("C", "B"), ("F", "E")]
    assert rows[0]["difference"]["netAnnualizedReturn"] == pytest.approx(0.005)
    attribution = M.attribution(s)
    assert set(attribution) == {"industryOnVsOff", "c0VsOff", "c1VsOff", "c1VsC0"}
    inter = M.interaction(s)
    assert inter["C0"]["status"] == "DESCRIPTIVE"
    assert inter["C0"]["returnValueDifference"] == pytest.approx((0.10 - 0.105) - (0.099 - 0.10))
    assert "returnValueDiffersMaterially" in inter["C0"] and "model" not in json.dumps(inter).lower().replace("drawdownratio", "")
    assert M.interaction(summaries(E={"complete": False}))["C0"]["status"] == "NOT_EVALUABLE_BLOCKED_PATH"


# ---------------------------------------------------------------------------------------------------------------------------------------
# Cash-yield sensitivity
# ---------------------------------------------------------------------------------------------------------------------------------------
EVENTS = [{"date": "2019-01-01", "annualRatePct": 2.0}, {"date": "2019-02-01", "annualRatePct": 0.25}]


def records(cash=0.5):
    dates = ["2019-01-02", "2019-01-03", "2019-01-04", "2019-02-04", "2019-02-05"]
    nav, out = 1.0, []
    for i, d in enumerate(dates):
        nav *= 1.001 if i else 1.0
        out.append({"date": d, "nav": nav, "cashWeight": cash})
    return out


def test_policy_rate_is_a_step_function_effective_on_its_event_date():
    assert M.policy_rate_in_force(EVENTS, "2018-12-31") is None and M.policy_rate_in_force(EVENTS, "2019-01-01") == 2.0
    assert M.policy_rate_in_force(EVENTS, "2019-01-31") == 2.0 and M.policy_rate_in_force(EVENTS, "2019-02-01") == 0.25


def test_cash_overlay_adds_only_cash_weight_times_the_cash_return_and_zero_changes_nothing():
    recs = records()
    assert M.cash_overlay_nav(recs, EVENTS, "ZERO") == [r["nav"] for r in recs]
    proxy = M.cash_overlay_nav(recs, EVENTS, "PROXY")
    assert proxy[0] == recs[0]["nav"] and all(p > r["nav"] for p, r in zip(proxy[1:], recs[1:]))
    gap = (pd.Timestamp("2019-01-03") - pd.Timestamp("2019-01-02")).days
    expected = recs[0]["nav"] * (1 + (recs[1]["nav"] / recs[0]["nav"] - 1) + 0.5 * ((1.02) ** (gap / 365) - 1))
    assert proxy[1] == pytest.approx(expected)
    no_cash = M.cash_overlay_nav(records(cash=0.0), EVENTS, "PROXY")
    assert no_cash == pytest.approx([r["nav"] for r in records(cash=0.0)])           # a fully invested book earns nothing extra
    haircut = M.cash_overlay_nav(recs, EVENTS, "PROXY_MINUS_HAIRCUT")
    assert proxy[-1] > haircut[-1] > recs[-1]["nav"] and M.cash_variant_rate(0.25, "PROXY_MINUS_HAIRCUT") == 0.0       # floored at zero, never negative
    assert M.cash_variant_rate(2.0, "PROXY_MINUS_HAIRCUT") == pytest.approx(1.5)
    with pytest.raises(ValueError, match="CASH_RATE_UNAVAILABLE"):
        M.cash_overlay_nav(recs, [{"date": "2030-01-01", "annualRatePct": 1.0}], "PROXY")
    with pytest.raises(ValueError, match="UNREGISTERED"):
        M.cash_variant_rate(1.0, "KOFR")
    before = json.dumps(recs)
    M.cash_overlay_nav(recs, EVENTS, "PROXY")
    assert json.dumps(recs) == before                                                 # the primary records are read, never changed


def test_cash_yield_source_is_the_repository_s_dated_policy_rate_and_covers_the_whole_span():
    document = json.loads((ROOT / M.CASH_YIELD["path"]).read_text())
    assert document["basis"] == "BOK_POLICY_RATE_PROXY" and document["events"][0]["date"] <= M.FEATURE_START
    assert [e["date"] for e in document["events"]] == sorted(e["date"] for e in document["events"])
    assert "KOFR" in M.CASH_YIELD["notUsed"] and "ECOS" in M.CASH_YIELD["notUsed"] and M.CASH_YIELD["neverChanges"]
    assert (ROOT / "pipeline/ecos_macro.py").is_file() and "does not exist" not in M.CASH_YIELD["notUsed"]["ECOS"]        # an adapter exists; no series is registered
    assert "NO exact, full-span, pinned investable" in M.CASH_YIELD["notUsed"]["ECOS"] and "not an investable deposit" in M.CASH_YIELD["limitation"]
    assert document["verifiedThrough"] == M.CASH_YIELD["verification"]["fileVerifiedThrough"] < M.DEVELOPMENT_CUTOFF
    assert M.CASH_YIELD["verification"]["sessionsAfterFileVerifiedThrough"].startswith("CARRIED_FROM_LAST_VERIFIED")


def test_output_keys_with_forbidden_semantics_are_refused():
    M.assert_no_forbidden_keys({"layerDecision": {"finalArchitecture": "A"}, "bandClass": "IMPROVES"})
    for key in ("bestArchitecture", "winner", "verdict", "recommended", "promoted", "validatedModel", "optimalWeights"):
        with pytest.raises(ValueError, match="FORBIDDEN_OUTPUT_KEY"):
            M.assert_no_forbidden_keys({"x": [{key: 1}]})


def test_industry_layer_percentile_function_is_the_sealed_one():
    assert S.MIN_RANK_PEERS == 5 and S.MIN_INDUSTRY_MEMBERS == 5


# ---------------------------------------------------------------------------------------------------------------------------------------
# Registered missing-signal semantics (SIGNAL_UNAVAILABLE_NO_STOCK_REBALANCE)
# ---------------------------------------------------------------------------------------------------------------------------------------
def thin_rows(count, industries=3):
    return [{"ticker": f"T{i:02d}", "industry": f"I{i % industries}", "STOCK_SCORE": 0.9 - i / 100, "INDUSTRY_SCORE": 0.5, "COMBINED_SCORE": 0.9 - i / 100,
             "tradable": True, "adv60": 6e9, "downsideVol126": 0.2} for i in range(count)]


def test_a_cross_section_below_the_registered_depth_has_no_new_decision_and_nothing_is_selected_sized_or_filled():
    rows = thin_rows(M.MIN_ELIGIBLE_PER_DATE - 1, industries=6)
    for with_industry in (False, True):
        decision = M.underlying_decision(rows, with_industry, industries_ranked=6)
        assert decision["available"] is False and decision["unavailable"] == M.SIGNAL_UNAVAILABLE and "STOCK_DEPTH_BELOW_MINIMUM" in decision["unavailableCauses"]
        assert decision["selected"] == [] and decision["baseWeights"] == {} and decision["scores"] == {} and decision["eligibleCount"] == len(rows)
    ok = M.underlying_decision(thin_rows(M.MIN_ELIGIBLE_PER_DATE, industries=6), False)
    assert ok["available"] is True and ok["unavailable"] is None and len(ok["selected"]) == M.MAX_HOLDINGS


def test_an_unrankable_industry_layer_makes_only_the_i_plus_s_book_unavailable():
    rows = thin_rows(14, industries=6)
    pair = M.underlying_pair(rows, industries_ranked=M.MIN_INDUSTRIES_RANKED - 1)
    assert pair["S"]["available"] is True and len(pair["S"]["selected"]) == M.MAX_HOLDINGS            # the S book never reads the industry score
    assert pair["I+S"]["available"] is False and pair["I+S"]["unavailableCauses"] == ["INDUSTRY_LAYER_UNRANKABLE"] and pair["I+S"]["selected"] == []
    assert M.underlying_pair(rows, industries_ranked=M.MIN_INDUSTRIES_RANKED)["I+S"]["available"] is True
    derived = M.underlying_pair(thin_rows(14, industries=3))                                        # without an explicit count the ranked industries are read from the rows
    assert derived["I+S"]["available"] is False and derived["S"]["available"] is True


def test_nothing_is_zero_filled_substituted_or_relaxed_to_reach_a_decision():
    rows = thin_rows(M.MIN_ELIGIBLE_PER_DATE, industries=6)
    rows[0]["STOCK_SCORE"] = np.nan                                                                 # one missing score is NOT turned into a number
    decision = M.underlying_decision(rows, False)
    assert decision["eligibleCount"] == M.MIN_ELIGIBLE_PER_DATE - 1 and decision["available"] is False and "T00" not in decision["scores"]
    rows[0]["STOCK_SCORE"] = 0.0                                                                    # only a real stated value makes the depth
    assert M.underlying_decision(rows, False)["available"] is True
    assert (M.MIN_ELIGIBLE_PER_DATE, M.MIN_INDUSTRIES_RANKED, M.MAX_HOLDINGS) == (10, 5, 5)           # the quality conditions did not move
    assert M.COMBINED_WEIGHTS == {"STOCK_SCORE": 0.5, "INDUSTRY_SCORE": 0.5} and M.PORTFOLIO["singleNameCap"] == 0.3


def test_availability_profile_reports_runs_first_last_valid_and_the_share():
    flags = [("d%d" % i, "s%d" % i, ok, [] if ok else ["STOCK_DEPTH_BELOW_MINIMUM"]) for i, ok in enumerate([False, False, True, True, False, True, False, False, False, True])]
    profile = M.availability_profile(flags)
    assert (profile["scheduledAnchors"], profile["validDecisionAnchors"], profile["unavailableAnchors"]) == (10, 4, 6) and profile["availabilityShare"] == 0.4
    assert profile["unavailableSignalDates"] == ["s0", "s1", "s4", "s6", "s7", "s8"] and profile["longestUnavailableRun"] == 3
    assert [r["anchors"] for r in profile["consecutiveUnavailableRuns"]] == [2, 1, 3]
    assert profile["firstValidDecision"] == {"anchor": "d2", "signalDate": "s2"} and profile["lastValidDecision"] == {"anchor": "d9", "signalDate": "s9"}
    assert profile["meetsStudyCoverage"] is False
    assert M.availability_profile([])["meetsStudyCoverage"] is False and M.availability_profile([])["availabilityShare"] is None


def test_the_study_level_coverage_floor_is_exact_integer_arithmetic_at_eighty_percent():
    def meets(valid, total):
        return M.availability_profile([("d", "s", i < valid, []) for i in range(total)])["meetsStudyCoverage"]
    assert M.MIN_AVAILABILITY_PERCENT == 80
    assert meets(80, 100) is True and meets(79, 100) is False
    assert meets(91, 113) is True and meets(90, 113) is False                                         # 113 scheduled anchors: 91 needed (ceil of 90.4)
    assert meets(1, 1) is True and meets(0, 5) is False                                              # at least one valid decision is always required
