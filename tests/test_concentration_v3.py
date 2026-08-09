"""Per-name invalidation levels and the concentrated portfolio selection.

Two v3 behaviours are pinned here:
  * a name's invalidation conditions come from ITS OWN readings and from levels
    derived per region — the old shared sentence is not allowed back;
  * the model portfolio is a concentrated 3–5 name book, not the whole research
    candidate list spread thin, whether or not Kelly is active.
"""
import numpy as np
import pandas as pd

from pipeline import kelly_portfolio as KP
from pipeline import longterm as LT


CFG_LT = {
    "rankBuffer": {"enterPct": 12, "exitPct": 28},
    "minFactorSleeves": 3,
    "minFinancialCoverage": 0.4,
}


def _table(n=8):
    rng = np.random.default_rng(5)
    idx = [f"T{i}" for i in range(n)]
    return pd.DataFrame({
        "sector": ["Technology"] * n,
        "momentum": rng.normal(0, 1, n), "value": rng.normal(0, 1, n),
        "quality": rng.normal(0, 1, n), "lowvol": rng.normal(0, 1, n),
        "alpha": np.linspace(1.0, 0.1, n), "rawAlpha": np.linspace(1.0, 0.1, n),
        "evidenceCoverage": 0.9, "dataCompleteness": 0.9, "sourceQuality": 0.8,
        "factorCoverage": 1.0, "financialCoverage": np.linspace(1.0, 0.3, n),
        "sleevesPresent": [4] * (n - 1) + [2],
        "valueTrap": [False] * (n - 1) + [True],
        "vol252": np.linspace(0.2, 0.5, n), "downsideVol": np.linspace(0.15, 0.4, n),
        "cvar95": np.linspace(2.0, 9.0, n), "maxDD252": np.linspace(-8.0, -60.0, n),
        "beta": 1.0, "mom121": np.linspace(0.5, -0.3, n), "marketCap": 1e11,
        "aboveMA200": [True] * (n - 2) + [False, False],
        "regime": "Bull", "dataInsufficient": False,
    }, index=idx)


def test_invalidation_levels_differ_per_name_and_carry_own_readings():
    table = _table()
    pct = table[["momentum", "value", "quality", "lowvol"]].rank(pct=True).mul(100).round(0)
    alpha_pct = table["alpha"].rank(pct=True).mul(100).round(0)
    limits = LT.region_risk_limits(table)

    strong = LT.invalidation_conditions(table.loc["T0"], pct.loc["T0"], float(alpha_pct.loc["T0"]), CFG_LT, limits)
    weak = LT.invalidation_conditions(table.loc["T7"], pct.loc["T7"], float(alpha_pct.loc["T7"]), CFG_LT, limits)

    # Same shape, different content: the current readings are the name's own.
    assert {c["key"] for c in strong} != {c["key"] for c in weak}
    assert [c["currentKo"] for c in strong] != [c["currentKo"] for c in weak]

    rank_strong = next(c for c in strong if c["key"] == "RANK_EXIT")
    rank_weak = next(c for c in weak if c["key"] == "RANK_EXIT")
    assert rank_strong["currentKo"] != rank_weak["currentKo"]
    # The exit level itself comes from the configured rank buffer (100 - 28).
    assert "72p" in rank_strong["triggerKo"] and "72p" in rank_weak["triggerKo"]
    assert rank_strong["state"] == "OK" and rank_weak["state"] == "BREACHED"


def test_breached_conditions_are_reported_not_softened():
    table = _table()
    pct = table[["momentum", "value", "quality", "lowvol"]].rank(pct=True).mul(100).round(0)
    alpha_pct = table["alpha"].rank(pct=True).mul(100).round(0)
    rows = LT.invalidation_conditions(table.loc["T7"], pct.loc["T7"], float(alpha_pct.loc["T7"]),
                                      CFG_LT, LT.region_risk_limits(table))
    keys = {c["key"]: c for c in rows}
    assert keys["VALUE_TRAP"]["state"] == "BREACHED"
    assert keys["DATA_FLOOR"]["state"] == "BREACHED"
    assert keys["TREND"]["state"] == "BREACHED"


def test_region_risk_limits_come_from_the_cross_section():
    table = _table()
    limits = LT.region_risk_limits(table)
    assert limits["cvar95Pct"] == float(np.quantile(table["cvar95"], 0.90))
    assert limits["maxDD252Pct"] == float(np.quantile(table["maxDD252"], 0.10))


def test_entry_state_adds_a_timing_condition_separate_from_the_factor_case():
    assert LT.entry_invalidation(None) is None
    ok = LT.entry_invalidation("ACCUMULATE_GRADUALLY")
    bad = LT.entry_invalidation("AVOID")
    assert ok["state"] == "OK" and bad["state"] == "BREACHED"
    assert ok["key"] == bad["key"] == "ENTRY_STATE"


# --------------------------------------------------------------------------- #
# Portfolio concentration
# --------------------------------------------------------------------------- #
def _candidates(n=14):
    rows = []
    for i in range(n):
        rows.append({
            "ticker": f"C{i:02d}", "region": "US" if i % 2 else "KR",
            "sector": f"S{i % 4}", "alpha": 1000 - i,
            "alphaPercentile": 99 - i * 2,
            "longTermResearchView": "POSITIVE", "valueTrap": False,
            "modelSleeveWeightPct": 100 / n,
            "evidenceCoverage": 0.9, "dataCompleteness": 0.9,
            "risk": {"vol252Pct": 24 + i, "downsideVolPct": 18 + i},
            "entry": {"entryState": "ACCUMULATE_GRADUALLY"},
        })
    return rows


CFG_PF = {
    "enabled": True, "mode": "shadow", "minNames": 3, "maxNames": 5,
    "minNamesPerRegion": 1,
    "selection": {"targetNames": 5, "minNames": 3, "maxNamesPerSector": 2,
                  "maxNamesPerRegion": 3, "minAlphaPercentile": 66,
                  "convictionTiltRange": 1.0},
    "maxPositionWeight": 0.30, "maxSectorWeight": 0.45, "maxThemeWeight": 0.45,
    "minCashPct": 15, "regionCaps": {"KR": 0.65, "US": 0.65},
    "regimeMultipliers": {"Goldilocks": {"kellyMultiplier": 1.0, "minCashPct": 10}},
}


def test_portfolio_holds_the_target_count_not_the_whole_candidate_list():
    got = KP.build_model_portfolio({"regions": {"ALL": {"picks": _candidates(14)}}}, {}, [], CFG_PF,
                                   macro_regime={"regime": "Goldilocks", "confidence": 1.0})
    held = [p for p in got["positions"] if p["modelPortfolioWeightPct"] > 0]
    assert len(held) == 5
    assert got["selection"]["consideredCount"] == 14
    assert got["selection"]["selectedCount"] == 5
    assert got["baselineMethod"] == "CONVICTION_TILTED_RISK_PARITY"
    assert abs(sum(got["finalWeights"].values()) + got["cashPct"] / 100 - 1) <= 1e-8


def test_selection_keeps_the_reason_each_dropped_name_was_dropped():
    _, meta = KP.select_portfolio(_candidates(14), CFG_PF)
    dropped = [r for r in meta["ranking"] if not r["selected"]]
    assert dropped, "near misses must stay auditable"
    assert all(r["exclusionCodes"] for r in dropped)
    assert all(not r["exclusionCodes"] for r in meta["ranking"] if r["selected"])


def test_sector_and_region_name_limits_bind_the_cut():
    candidates = _candidates(14)
    for c in candidates:  # everything in one sector, alternating regions
        c["sector"] = "Technology"
    selected, meta = KP.select_portfolio(candidates, CFG_PF)
    assert len(selected) == 2  # maxNamesPerSector
    assert any("SECTOR_NAME_LIMIT" in r["exclusionCodes"] for r in meta["ranking"] if not r["selected"])


def test_conviction_score_orders_by_rank_edge_per_unit_of_downside_risk():
    rows = KP.conviction_scores([
        {"ticker": "SHARP", "region": "US", "alphaPercentile": 90, "evidenceCoverage": 1.0,
         "longTermResearchView": "POSITIVE", "entry": {"entryState": "ACCUMULATE_GRADUALLY"},
         "risk": {"downsideVolPct": 10.0}},
        {"ticker": "WILD", "region": "US", "alphaPercentile": 90, "evidenceCoverage": 1.0,
         "longTermResearchView": "POSITIVE", "entry": {"entryState": "ACCUMULATE_GRADUALLY"},
         "risk": {"downsideVolPct": 40.0}},
        {"ticker": "THIN", "region": "US", "alphaPercentile": 90, "evidenceCoverage": 0.2,
         "longTermResearchView": "POSITIVE", "entry": {"entryState": "ACCUMULATE_GRADUALLY"},
         "risk": {"downsideVolPct": 10.0}},
    ], CFG_PF)
    by_ticker = {r["ticker"]: r for r in rows}
    # Same rank edge, four times the downside risk -> a quarter of the score.
    assert by_ticker["SHARP"]["convictionScore"] == 4 * by_ticker["WILD"]["convictionScore"]
    # Weak evidence can only shrink the score, never raise it.
    assert by_ticker["THIN"]["convictionScore"] < by_ticker["SHARP"]["convictionScore"]
    assert [r["ticker"] for r in rows][0] == "SHARP"


def test_entry_and_research_state_block_selection_entirely():
    candidates = _candidates(6)
    candidates[0]["entry"] = {"entryState": "AVOID"}
    candidates[1]["longTermResearchView"] = "NEUTRAL"
    candidates[2]["valueTrap"] = True
    _, meta = KP.select_portfolio(candidates, CFG_PF)
    blocked = {r["ticker"] for r in meta["ranking"]
               if "ENTRY_OR_RESEARCH_STATE_BLOCKS_SIZING" in r["exclusionCodes"]}
    assert {"C00", "C01", "C02"} <= blocked


def test_baseline_weights_tilt_by_conviction_and_respect_caps_and_cash():
    selected, _ = KP.select_portfolio(_candidates(14), CFG_PF)
    weights = KP.baseline_weights(selected, CFG_PF)
    assert len(weights) == 5
    assert max(weights.values()) <= CFG_PF["maxPositionWeight"] + 1e-9
    assert sum(weights.values()) <= 1.0 - CFG_PF["minCashPct"] / 100 + 1e-9
    ranked = [r["ticker"] for r in KP.conviction_scores(selected, CFG_PF)]
    assert weights[ranked[0]] > weights[ranked[-1]]


def test_macro_equity_budget_binds_the_cash_floor():
    macro = {"regime": "Goldilocks", "confidence": 1.0,
             "riskBudget": {"equityRangePct": [20, 45], "cashRangePct": [55, 80]}}
    got = KP.build_model_portfolio({"regions": {"ALL": {"picks": _candidates(14)}}}, {}, [],
                                   CFG_PF, macro_regime=macro)
    assert got["macroEquityRangePct"] == [20, 45]
    assert got["appliedMinCashPct"] == 55.0
    # The published macro budget and the portfolio cannot disagree on screen.
    # Tolerance is the 6-decimal weight serialization, not allocation slack.
    assert sum(got["finalWeights"].values()) <= 0.45 + 1e-5
    assert got["cashPct"] >= 55.0 - 1e-3
    assert "CASH_FLOOR_SET_BY_MACRO_EQUITY_BUDGET" in got["warnings"]


def test_concentration_cost_is_published_with_warnings():
    weights = pd.Series({"A": 0.5, "B": 0.2, "C": 0.15})
    diag = KP.concentration_diagnostics(weights, CFG_PF)
    assert diag["names"] == 3
    assert diag["effectiveNames"] == round(1 / ((0.5 / 0.85) ** 2 + (0.2 / 0.85) ** 2 + (0.15 / 0.85) ** 2), 2)
    assert "SINGLE_DIGIT_NAME_COUNT_IDIOSYNCRATIC_RISK" in diag["warnings"]
    assert "TOP_NAME_ABOVE_40PCT_OF_EQUITY" in diag["warnings"]


def test_turnover_is_labelled_as_an_initial_build_without_a_prior_state():
    got = KP.build_model_portfolio({"regions": {"ALL": {"picks": _candidates(14)}}}, {}, [], CFG_PF,
                                   macro_regime={"regime": "Goldilocks", "confidence": 1.0})
    assert got["turnoverBasis"] == "INITIAL_BUILD"
    priored = KP.build_model_portfolio({"regions": {"ALL": {"picks": _candidates(14)}}}, {}, [], CFG_PF,
                                       macro_regime={"regime": "Goldilocks", "confidence": 1.0},
                                       prior_weights={"C00": 0.1})
    assert priored["turnoverBasis"] == "VS_PRIOR_STATE"


def test_blocked_build_publishes_no_selection_or_weights():
    got = KP.build_model_portfolio({"regions": {"ALL": {"picks": _candidates(14)}}}, {}, [],
                                   CFG_PF, blocked=True)
    assert got["status"] == "BLOCKED"
    assert got["positions"] == [] and got["finalWeights"] == {}
    assert "selection" not in got
